"""Context Protocol Header

Description:
    Provides confused deputy attack detection middleware for agent tool calls.
Purpose:
    Lets developers detect indirect prompt injection where adversarial content
    in prior tool results drives subsequent tool call arguments instead of
    the original user instruction.
Architecture:
    - ConfusedDeputyGuardMiddleware: Tracks tool result outputs and computes
      verbatim overlap ratios against tool call arguments.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime middleware hooks.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


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
        self._user_message: str = ""
        self._tool_outputs: list[str] = []

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Captures user message fingerprint and resets accumulated tool results.
        self._user_message = ctx.message
        self._tool_outputs.clear()
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Accumulates tool result outputs for subsequent overlap analysis.
        if ctx.tool_result is not None and ctx.tool_result.output:
            self._tool_outputs.append(ctx.tool_result.output)
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Checks whether tool call arguments are driven by external tool results.
        if ctx.tool_call is None or ctx.tool_is_internal or not self._tool_outputs:
            return MiddlewareDecision.continue_()
        return self._check_arguments(ctx)

    def _check_arguments(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        # Scans each string argument for verbatim overlap with prior tool results.
        for arg_name, arg_value in ctx.tool_call.arguments.items():
            if not isinstance(arg_value, str) or len(arg_value) < self._min_arg_length:
                continue
            ratio = self._max_overlap_ratio(arg_value)
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

    def _max_overlap_ratio(self, arg_value: str) -> float:
        # Returns the maximum overlap ratio between the argument and any tool result.
        best_ratio = 0.0
        for output in self._tool_outputs:
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
