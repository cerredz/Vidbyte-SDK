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
Relations:
    Used through vidbyte.middleware.builtins and AgentRuntime before_tool_call.
"""

from __future__ import annotations

import collections
import hashlib
import json
from typing import Any

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware


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
        self._call_history: collections.deque[str] = collections.deque(maxlen=window)

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Clear loop history so this instance is safe to reuse across runs."""
        del ctx
        self._call_history.clear()
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Record the current tool call and abort if a repetition loop is detected."""
        if ctx.tool_call is None:
            return MiddlewareDecision.continue_()
        if self.skip_internal_tools and ctx.tool_is_internal:
            return MiddlewareDecision.continue_()
        key = self._make_key(ctx.tool_call.tool_name, ctx.tool_call.arguments)
        self._call_history.append(key)
        consecutive = self._count_consecutive_tail(key)
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

    def _count_consecutive_tail(self, key: str) -> int:
        """Count how many entries at the end of the history deque match key."""
        count = 0
        for entry in reversed(self._call_history):
            if entry == key:
                count += 1
            else:
                break
        return count


__all__ = ["LoopDetectionMiddleware"]
