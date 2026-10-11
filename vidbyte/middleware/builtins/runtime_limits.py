"""Context Protocol Header

Description:
    Provides runtime boundary middleware for direct text agent loops.
Purpose:
    Lets developers abort runs at middleware hook boundaries using elapsed,
    model-call, or tool-call limits.
Architecture:
    - RuntimeLimitMiddleware: Boundary checks against MiddlewareContext stats.
Relations:
    Used through vidbyte.middleware.builtins.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.middleware.builtins.limit_validation import positive_integer, positive_real


class RuntimeLimitMiddleware(AgentMiddleware):
    """Abort when elapsed time, model calls, or tool calls exceed configured limits."""

    def __init__(
        self,
        *,
        max_elapsed_seconds: float | None = None,
        max_model_calls: int | None = None,
        max_tool_calls: int | None = None,
    ) -> None:
        self.max_elapsed_seconds = positive_real(max_elapsed_seconds, "max_elapsed_seconds") if max_elapsed_seconds is not None else None
        self.max_model_calls = positive_integer(max_model_calls, "max_model_calls") if max_model_calls is not None else None
        self.max_tool_calls = positive_integer(max_tool_calls, "max_tool_calls") if max_tool_calls is not None else None

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Abort before another iteration when any limit is reached."""
        if self.max_elapsed_seconds is not None and ctx.elapsed_seconds >= self.max_elapsed_seconds:
            return MiddlewareDecision.abort(
                "runtime_elapsed_limit",
                metadata={"max_elapsed_seconds": self.max_elapsed_seconds},
            )
        if self.max_model_calls is not None and ctx.model_call_count >= self.max_model_calls:
            return MiddlewareDecision.abort(
                "runtime_model_call_limit",
                metadata={"max_model_calls": self.max_model_calls},
            )
        if self.max_tool_calls is not None and ctx.tool_call_count >= self.max_tool_calls:
            return MiddlewareDecision.abort(
                "runtime_tool_call_limit",
                metadata={"max_tool_calls": self.max_tool_calls},
            )
        return MiddlewareDecision.continue_()

__all__ = ["RuntimeLimitMiddleware"]
