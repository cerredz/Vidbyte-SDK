"""Context Protocol Header

Description:
    Provides structured audit logging middleware for agent runtime hooks.
Purpose:
    Lets developers observe direct text runtime lifecycle events without
    coupling application logging to AgentRuntime internals.
Architecture:
    - AuditLogMiddleware: Emits MiddlewareEvent objects to a callable or list.
Relations:
    Used through vidbyte.middleware.builtins.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareEvent,
    MiddlewareHook,
)
from vidbyte.middleware.base import AgentMiddleware


class AuditLogMiddleware(AgentMiddleware):
    """Emit structured events for configured middleware hooks."""

    def __init__(
        self,
        sink: Callable[[MiddlewareEvent], object] | list[MiddlewareEvent],
        *,
        hooks: Iterable[MiddlewareHook] | None = None,
    ) -> None:
        self.sink = sink
        self.hooks = None if hooks is None else frozenset(hooks)

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return self._emit(ctx)

    def _emit(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        if self.hooks is not None and ctx.hook not in self.hooks:
            return MiddlewareDecision.continue_()
        event = MiddlewareEvent(
            middleware_name=self.middleware_name,
            hook=ctx.hook,
            action=MiddlewareAction.CONTINUE,
            metadata=self._metadata(ctx),
        )
        if isinstance(self.sink, list):
            self.sink.append(event)
        else:
            self.sink(event)
        return MiddlewareDecision.continue_()

    @staticmethod
    def _metadata(ctx: MiddlewareContext) -> dict[str, Any]:
        return {
            "agent_name": ctx.agent_name,
            "iteration_count": ctx.iteration_count,
            "model_call_count": ctx.model_call_count,
            "tool_call_count": ctx.tool_call_count,
            "tokens_used": ctx.tokens_used,
            "tool_name": ctx.tool_call.tool_name if ctx.tool_call else None,
            "tool_is_internal": ctx.tool_is_internal,
            "error_type": type(ctx.error).__name__ if ctx.error else None,
        }


__all__ = ["AuditLogMiddleware"]
