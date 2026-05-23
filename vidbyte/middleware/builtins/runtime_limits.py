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


class RuntimeLimitMiddleware(AgentMiddleware):
    """Abort when elapsed time, model calls, or tool calls exceed configured limits."""

    def __init__(
        self,
        *,
        max_elapsed_seconds: float | None = None,
        max_model_calls: int | None = None,
        max_tool_calls: int | None = None,
    ) -> None:
        self.max_elapsed_seconds = self._positive_float(max_elapsed_seconds, "max_elapsed_seconds")
        self.max_model_calls = self._positive_int(max_model_calls, "max_model_calls")
        self.max_tool_calls = self._positive_int(max_tool_calls, "max_tool_calls")

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

    @staticmethod
    def _positive_int(value: int | None, name: str) -> int | None:
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be greater than zero when provided.")
        return value

    @staticmethod
    def _positive_float(value: float | None, name: str) -> float | None:
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be greater than zero when provided.")
        return value


__all__ = ["RuntimeLimitMiddleware"]
