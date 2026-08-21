"""Context Protocol Header

Description:
    Defines the public base class for agent runtime middleware.
Purpose:
    Lets SDK users create middleware by subclassing one class and overriding
    only the runtime lifecycle hooks they need.
Architecture:
    - AgentMiddleware: Optional async hook methods matching AgentRuntime breakpoints.
    - after_run: Terminal hook for returned results and raise-path exits (ctx.error set).
Relations:
    Used by vidbyte.middleware.pipeline and vidbyte.agents.runtime.
"""

from __future__ import annotations

from abc import ABC

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision


class AgentMiddleware(ABC):
    """Base class for deterministic agent runtime middleware."""

    name: str | None = None
    fail_closed: bool = True

    @property
    def middleware_name(self) -> str:
        """Return a stable display name for metadata and audit events."""
        return self.name or self.__class__.__name__

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run before the direct text runtime starts."""
        del ctx
        return MiddlewareDecision.continue_()

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run before each direct text runtime iteration."""
        del ctx
        return MiddlewareDecision.continue_()

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run immediately before invoking the model runner."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run after a successful model response has been received."""
        del ctx
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run when model invocation raises an exception."""
        del ctx
        return MiddlewareDecision.continue_()

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run before permission checks, validation, and local tool execution."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run after a tool call was executed or denied."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run after one direct text runtime iteration completes."""
        del ctx
        return MiddlewareDecision.continue_()

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Run at the end of one direct runtime attempt, including terminal exceptions.

        Result-returning exits leave ctx.error unset. Raise-path exits set ctx.error
        to the exception that will propagate; abort/retry/deny decisions are ignored.
        """
        del ctx
        return MiddlewareDecision.continue_()


__all__ = ["AgentMiddleware"]
