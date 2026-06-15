"""Context Protocol Header

Description:
    Provides agent tool-call loop detection middleware.
Purpose:
    Lets developers abort agent runs when the same tool is called with identical
    arguments consecutively more times than a configured threshold, or when any
    single tool produces the same output more than a total-count threshold, preventing
    infinite action loops that exhaust iteration or token limits slowly.
Architecture:
    - LoopDetectionMiddleware: Maintains a bounded deque of recent (tool, args)
      keys and aborts when the tail contains max_repeated_calls identical entries.
      Optionally tracks (tool, output) repetition counts via max_repeated_outputs.
    - _LoopDetectionRunState: Per-run dataclass stored in MiddlewareContext.run_state.
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime before_tool_call.
"""

from __future__ import annotations

import collections
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


@dataclass
class _LoopDetectionRunState:
    # Per-run bounded call history deque; maxlen is set during before_run.
    call_history: collections.deque[str] = field(default_factory=collections.deque)
    # Per-run total-count dict for (tool_name, output_hash) pairs.
    output_counts: dict[str, int] = field(default_factory=dict)


class LoopDetectionMiddleware(AgentMiddleware):
    """Abort when tool-call input or output repetition exceeds configured thresholds.

    max_repeated_calls: abort when the same (tool, args) key appears consecutively.
    max_repeated_outputs: abort when any (tool, output) pair is seen this many times total.
    """

    def __init__(
        self,
        *,
        max_repeated_calls: int = 3,
        window: int = 10,
        skip_internal_tools: bool = True,
        max_repeated_outputs: int | None = None,
    ) -> None:
        # Validates thresholds and window before storing configuration.
        if max_repeated_calls < 2:
            raise ValueError("max_repeated_calls must be at least 2.")
        if window < max_repeated_calls:
            raise ValueError("window must be greater than or equal to max_repeated_calls.")
        if max_repeated_outputs is not None and max_repeated_outputs < 2:
            raise ValueError("max_repeated_outputs must be at least 2.")
        self.max_repeated_calls = max_repeated_calls
        self.window = window
        self.skip_internal_tools = skip_internal_tools
        self.max_repeated_outputs = max_repeated_outputs

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
        """Increment per-run output counts and abort if any (tool, output) pair repeats too often."""
        if self.max_repeated_outputs is None:
            return MiddlewareDecision.continue_()
        if ctx.tool_result is None:
            return MiddlewareDecision.continue_()
        if self.skip_internal_tools and ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        state: _LoopDetectionRunState = ctx.run_state.get(self.__class__) or _LoopDetectionRunState(
            call_history=collections.deque(maxlen=self.window)
        )
        output_key = self._make_output_key(ctx.tool_result.tool_name, ctx.tool_result.output)
        count = state.output_counts.get(output_key, 0) + 1
        state.output_counts[output_key] = count
        ctx.run_state[self.__class__] = state
        if count >= self.max_repeated_outputs:
            return MiddlewareDecision.abort(
                "tool_output_loop_detected",
                metadata={
                    "tool_name": ctx.tool_result.tool_name,
                    "output_hash": output_key.split(":", 1)[1] if ":" in output_key else output_key,
                    "repeated_count": count,
                    "max_repeated_outputs": self.max_repeated_outputs,
                },
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


__all__ = ["LoopDetectionMiddleware"]
