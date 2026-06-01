"""Context Protocol Header

Description:
    Provides agent tool-call loop detection middleware.
Purpose:
    Lets developers abort agent runs when the same tool is called with identical
    arguments consecutively more times than a configured threshold, preventing
    infinite action loops that exhaust iteration or token limits slowly.
Architecture:
    - LoopDetectionMiddleware: Maintains a bounded deque of recent (tool, args)
      keys and aborts when the tail contains max_repeated_calls identical entries.
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


class LoopDetectionMiddleware(AgentMiddleware):
    """Abort when the same tool call is repeated consecutively beyond the configured threshold."""

    def __init__(
        self,
        *,
        max_repeated_calls: int = 3,
        window: int = 10,
        skip_internal_tools: bool = True,
    ) -> None:
        # Validates that the window is large enough to hold a full repeat sequence.
        if max_repeated_calls < 2:
            raise ValueError("max_repeated_calls must be at least 2.")
        if window < max_repeated_calls:
            raise ValueError("window must be greater than or equal to max_repeated_calls.")
        self.max_repeated_calls = max_repeated_calls
        self.window = window
        self.skip_internal_tools = skip_internal_tools

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Initialize a fresh per-run call history deque in ctx.run_state."""
        ctx.run_state[self.__class__] = _LoopDetectionRunState(
            call_history=collections.deque(maxlen=self.window)
        )
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record the current tool call and abort if a repetition loop is detected."""
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

    def _make_key(self, tool_name: str, arguments: Any) -> str:
        """Produce a stable string key from the tool name and its arguments."""
        try:
            serialized = json.dumps(arguments, sort_keys=True, default=str)
        except Exception:
            serialized = str(arguments)
        arg_hash = hashlib.sha256(serialized.encode()).hexdigest()[:16]
        return f"{tool_name}:{arg_hash}"

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
