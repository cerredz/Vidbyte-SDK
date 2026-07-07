"""
FILE: vidbyte/middleware/builtins/loop_detection.py

PURPOSE:
    Provides agent tool-call loop detection middleware. Lets developers react when the same tool is called with identical arguments consecutively more times than a configured threshold, or when any single tool produces the same output more than a total-count threshold, preventing infinite action loops that exhaust iteration or token limits slowly. Repeated-output detection supports a soft threshold (warn the agent in-context) and a hard threshold (abort the run).
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/builtins/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.lib.dataclasses.tools: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - LoopDetectionMiddleware (class): public or navigational symbol owned here.
    - LoopDetectionMiddleware (export): public or navigational symbol owned here.
    - REPEATED_OUTPUT_LOOP_NOTICE (export): public or navigational symbol owned here.

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

import collections
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.dataclasses.middleware import (
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareTransform,
)
from vidbyte.lib.dataclasses.tools import ToolResult
from vidbyte.middleware.base import AgentMiddleware

# Constant description injected into the agent's context window when the soft
# repeated-output threshold is reached. It is appended to the offending tool's
# model-visible output so the agent is told, in-band, that it appears stuck and
# should change course instead of repeating the same action.
REPEATED_OUTPUT_LOOP_NOTICE = (
    "Loop detection: this tool has returned the same output repeatedly, which "
    "usually means the current approach is not making progress. Stop repeating "
    "this action — re-examine the task, try a different tool or different "
    "arguments, or conclude the run if the task is already complete."
)


@dataclass
class _LoopDetectionRunState:
    # Per-run bounded call history deque; maxlen is set during before_run.
    call_history: collections.deque[str] = field(default_factory=collections.deque)
    # Per-run total-count dict for (tool_name, output_hash) pairs.
    output_counts: dict[str, int] = field(default_factory=dict)


class LoopDetectionMiddleware(AgentMiddleware):
    """React when tool-call input or output repetition exceeds configured thresholds.

    max_repeated_calls: abort when the same (tool, args) key appears consecutively.
    soft_max_repeated_outputs: when any (tool, output) pair is seen this many times
        total, inject REPEATED_OUTPUT_LOOP_NOTICE into the agent's context window and
        continue the run (a soft nudge, no abort).
    hard_max_repeated_outputs: when any (tool, output) pair is seen this many times
        total, abort the run.
    """

    def __init__(
        self,
        *,
        max_repeated_calls: int = 3,
        window: int = 10,
        skip_internal_tools: bool = True,
        soft_max_repeated_outputs: int | None = None,
        hard_max_repeated_outputs: int | None = None,
    ) -> None:
        # Validates thresholds and window before storing configuration.
        if max_repeated_calls < 2:
            raise ValueError("max_repeated_calls must be at least 2.")
        if window < max_repeated_calls:
            raise ValueError("window must be greater than or equal to max_repeated_calls.")
        if soft_max_repeated_outputs is not None and soft_max_repeated_outputs < 2:
            raise ValueError("soft_max_repeated_outputs must be at least 2.")
        if hard_max_repeated_outputs is not None and hard_max_repeated_outputs < 2:
            raise ValueError("hard_max_repeated_outputs must be at least 2.")
        if (
            soft_max_repeated_outputs is not None
            and hard_max_repeated_outputs is not None
            and soft_max_repeated_outputs >= hard_max_repeated_outputs
        ):
            raise ValueError(
                "soft_max_repeated_outputs must be less than hard_max_repeated_outputs "
                "so the soft nudge fires before the hard abort."
            )
        self.max_repeated_calls = max_repeated_calls
        self.window = window
        self.skip_internal_tools = skip_internal_tools
        self.soft_max_repeated_outputs = soft_max_repeated_outputs
        self.hard_max_repeated_outputs = hard_max_repeated_outputs

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Initialize a fresh per-run call history deque and output-count dict in ctx.run_state."""
        ctx.run_state[self.__class__] = _LoopDetectionRunState(
            call_history=collections.deque(maxlen=self.window),
            output_counts={},
        )
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record the current tool call and abort if a consecutive repetition loop is detected."""
        if ctx.tool_call is None:
            return MiddlewareDecision.continue_()
        if self.skip_internal_tools and ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        state: _LoopDetectionRunState = ctx.run_state.get(self.__class__) or _LoopDetectionRunState(
            call_history=collections.deque(maxlen=self.window)
        )
        key = self._make_key(ctx.tool_call.tool_name, ctx.tool_call.arguments)
        state.call_history.append(key)
        ctx.run_state[self.__class__] = state
        consecutive = self._count_consecutive_tail(key, state.call_history)
        if consecutive >= self.max_repeated_calls:
            return MiddlewareDecision.abort(
                "tool_loop_detected",
                metadata={
                    "tool_name": ctx.tool_call.tool_name,
                    "repeated_count": consecutive,
                    "max_repeated_calls": self.max_repeated_calls,
                },
            )
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Track per-run output counts, nudging at the soft threshold and aborting at the hard one."""
        if self.soft_max_repeated_outputs is None and self.hard_max_repeated_outputs is None:
            return MiddlewareDecision.continue_()
        if ctx.tool_result is None:
            return MiddlewareDecision.continue_()
        if self.skip_internal_tools and ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        state: _LoopDetectionRunState = ctx.run_state.get(self.__class__) or _LoopDetectionRunState(
            call_history=collections.deque(maxlen=self.window)
        )
        result = ctx.tool_result
        output_key = self._make_output_key(result.tool_name, result.output)
        count = state.output_counts.get(output_key, 0) + 1
        state.output_counts[output_key] = count
        ctx.run_state[self.__class__] = state
        output_hash = output_key.split(":", 1)[1] if ":" in output_key else output_key
        metadata = {
            "tool_name": result.tool_name,
            "output_hash": output_hash,
            "repeated_count": count,
            "description": REPEATED_OUTPUT_LOOP_NOTICE,
        }
        # Hard threshold aborts the run (checked first so it wins when both fire).
        if self.hard_max_repeated_outputs is not None and count >= self.hard_max_repeated_outputs:
            return MiddlewareDecision.abort(
                "tool_output_loop_detected",
                metadata={**metadata, "hard_max_repeated_outputs": self.hard_max_repeated_outputs},
            )
        # Soft threshold injects the notice into the agent's context window and continues.
        if self.soft_max_repeated_outputs is not None and count >= self.soft_max_repeated_outputs:
            visible_result = ToolResult(
                tool_name=result.tool_name,
                status=result.status,
                output=f"{result.output}\n\n[{REPEATED_OUTPUT_LOOP_NOTICE} (observed {count} times)]",
                metadata={
                    **dict(result.metadata),
                    "loop_detection_notice": True,
                    "repeated_count": count,
                },
            )
            return MiddlewareDecision.continue_(
                metadata={**metadata, "soft_max_repeated_outputs": self.soft_max_repeated_outputs},
                transform=MiddlewareTransform(model_visible_tool_result=visible_result),
            )
        return MiddlewareDecision.continue_()

    def _make_key(self, tool_name: str, arguments: Any) -> str:
        """Produce a stable string key from the tool name and its arguments."""
        try:
            serialized = json.dumps(arguments, sort_keys=True, default=str)
        except Exception:
            serialized = str(arguments)
        arg_hash = hashlib.sha256(serialized.encode()).hexdigest()[:16]
        return f"{tool_name}:{arg_hash}"

    def _make_output_key(self, tool_name: str, output: str) -> str:
        """Produce a stable string key from the tool name and its output text."""
        output_hash = hashlib.sha256(output.encode()).hexdigest()[:16]
        return f"{tool_name}:{output_hash}"

    @staticmethod
    def _count_consecutive_tail(key: str, history: collections.deque[str]) -> int:
        """Count how many entries at the end of the history deque match key."""
        count = 0
        for entry in reversed(history):
            if entry == key:
                count += 1
            else:
                break
        return count


__all__ = ["LoopDetectionMiddleware", "REPEATED_OUTPUT_LOOP_NOTICE"]
