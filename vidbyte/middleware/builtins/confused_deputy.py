"""
FILE: vidbyte/middleware/builtins/confused_deputy.py

PURPOSE:
    Provides confused deputy attack detection middleware for agent tool calls. Lets developers detect indirect prompt injection where adversarial content in prior tool results drives subsequent tool call arguments instead of the original user instruction.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - ConfusedDeputyGuardMiddleware (class): public or navigational symbol owned here.
    - ConfusedDeputyGuardMiddleware (export): public or navigational symbol owned here.

COMMON MODIFICATION PATTERNS:
    - When adding or removing a public symbol, update this header, the local `__all__` if present, and the nearest folder README file index.
    - When changing runtime behavior, update related docs or examples that describe the same contract before opening a PR.
    - When adding a new failure path, keep the error message safe for logs and include enough context for a future agent to route the fix.

WHAT NOT TO DO IN THIS FILE:
    1. Do not move responsibilities across SDK layers without updating the corresponding folder README and public exports.
    2. Do not add provider credentials, API keys, or unredacted prompt payloads to errors, metadata, traces, or comments.
    3. Do not edit generated cache files or make unrelated refactors while touching this file.

KNOWN EDGE CASES:
    - This SDK is in alpha and several files preserve compatibility exports; check `README.md` and `vidbyte/__init__.py` before renaming public symbols.
    - Agentic headers are living documentation. Re-run a header/code cross-check after changing imports, exports, errors, or concurrency behavior.

COMMON ERRORS RAISED BY THIS FILE:
    - ValueError: raised, returned, or imported by this file. Keep context safe and grepable.

RELATED DOCS:
    - https://github.com/cerredz/Vidbyte-SDK/blob/main/vidbyte/prompts/prompts/agentic_engineering/system_prompt.md: source prompt for the agentic-engineering principles applied to this file.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/file_headers.md: file-header anatomy used for this header.
    - https://raw.githubusercontent.com/cerredz/Vidbyte-SDK/main/vidbyte/prompts/prompts/agentic_engineering/function_design.md: function design guidance for future edits.
    - docs/design/agentic-engineering-principles-agents-middleware-tools.md: design record for this documentation pass.

TESTS:
    - python -m compileall vidbyte; scripts/test-security-middleware.py and compaction-related scripts when changing middleware behavior.

CONCURRENCY MODEL:
    - Review async/task state carefully; this file participates in agent, middleware, tool, or actor execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


@dataclass
class _ConfusedDeputyRunState:
    # Accumulates per-run user message and prior tool outputs for overlap analysis.
    user_message: str = ""
    tool_outputs: list[str] = field(default_factory=list)


class ConfusedDeputyGuardMiddleware(AgentMiddleware):
    """Detect when tool call arguments are driven by external tool results."""

    def __init__(self, *, max_external_content_ratio: float = 0.6, min_argument_length: int = 20, abort_reason: str = "confused_deputy_detected") -> None:
        # Configures overlap threshold and minimum argument length for analysis.
        if max_external_content_ratio <= 0.0 or max_external_content_ratio > 1.0:
            raise ValueError("max_external_content_ratio must be in (0.0, 1.0].")
        if min_argument_length < 1:
            raise ValueError("min_argument_length must be at least 1.")
        self._max_ratio = max_external_content_ratio
        self._min_arg_length = min_argument_length
        self._abort_reason = abort_reason

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Initializes fresh per-run state keyed by this class in ctx.run_state.
        ctx.run_state[self.__class__] = _ConfusedDeputyRunState(user_message=ctx.message)
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Accumulates tool result outputs in per-run state for subsequent overlap analysis.
        if ctx.tool_result is not None and ctx.tool_result.output:
            state: _ConfusedDeputyRunState = ctx.run_state.get(self.__class__) or _ConfusedDeputyRunState()
            state.tool_outputs.append(ctx.tool_result.output)
            ctx.run_state[self.__class__] = state
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Checks whether tool call arguments are driven by external tool results.
        state: _ConfusedDeputyRunState = ctx.run_state.get(self.__class__) or _ConfusedDeputyRunState()
        if ctx.tool_call is None or ctx.tool_is_internal or not state.tool_outputs:
            return MiddlewareDecision.continue_()
        return self._check_arguments(ctx, state.tool_outputs)

    def _check_arguments(self, ctx: MiddlewareContext, tool_outputs: list[str]) -> MiddlewareDecision:
        # Scans each string argument for verbatim overlap with prior tool results.
        for arg_name, arg_value in ctx.tool_call.arguments.items():
            if not isinstance(arg_value, str) or len(arg_value) < self._min_arg_length:
                continue
            ratio = self._max_overlap_ratio(arg_value, tool_outputs)
            if ratio > self._max_ratio:
                return MiddlewareDecision.abort(
                    self._abort_reason,
                    metadata={
                        "tool_name": ctx.tool_call.tool_name,
                        "argument_name": arg_name,
                        "overlap_ratio": round(ratio, 4),
                        "threshold": self._max_ratio,
                    },
                )
        return MiddlewareDecision.continue_()

    def _max_overlap_ratio(self, arg_value: str, tool_outputs: list[str]) -> float:
        # Returns the maximum overlap ratio between the argument and any tool result.
        best_ratio = 0.0
        for output in tool_outputs:
            length = self._longest_common_substring_length(arg_value, output)
            ratio = length / len(arg_value) if arg_value else 0.0
            best_ratio = max(best_ratio, ratio)
        return best_ratio

    @staticmethod
    def _longest_common_substring_length(needle: str, haystack: str) -> int:
        # Finds the longest substring of needle that appears verbatim in haystack.
        if not needle or not haystack:
            return 0
        n = len(needle)
        low, high, best = 0, n, 0
        while low <= high:
            mid = (low + high) // 2
            if mid == 0:
                low = mid + 1
                continue
            found = False
            for start in range(n - mid + 1):
                if needle[start : start + mid] in haystack:
                    found = True
                    break
            if found:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best


__all__ = ["ConfusedDeputyGuardMiddleware"]
