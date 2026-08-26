"""Context Protocol Header

Description:
    Implements ordered middleware hook dispatch and diagnostic invocation recording.
Purpose:
    Centralizes middleware decision handling, sleeps, exception policy, and
    metadata events so AgentRuntime remains focused on the model/tool loop. It
    records every hook invocation separately from consumer-facing policy events.
Architecture:
    - MiddlewarePipeline: Runs middleware hooks in configured order.
    - hook_invocations: Captures elapsed time and outcome for diagnostic tracing.
Relations:
    Used by vidbyte.agents.runtime, which turns hook invocations into diagnostic
    semantic spans before the enclosing agent trace closes.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from vidbyte.lib.dataclasses.middleware import (
    MiddlewareAction,
    MiddlewareContext,
    MiddlewareDecision,
    MiddlewareEvent,
    MiddlewareHook,
    MiddlewareHookInvocation,
    MiddlewareTransform,
)
from vidbyte.middleware.base import AgentMiddleware


class MiddlewarePipeline:
    """Run middleware hooks in order and interpret structured decisions."""

    def __init__(
        self,
        middleware: Sequence[AgentMiddleware] = (),
        *,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.middleware = tuple(middleware)
        self._sleeper = sleeper or asyncio.sleep
        self.clock = clock or time.monotonic
        self._events: list[MiddlewareEvent] = []
        self._hook_invocations: list[MiddlewareHookInvocation] = []

    @property
    def events(self) -> tuple[MiddlewareEvent, ...]:
        """Return middleware events recorded so far."""
        return tuple(self._events)

    @property
    def hook_invocations(self) -> tuple[MiddlewareHookInvocation, ...]:
        """Return diagnostic records for every middleware hook invocation."""
        return tuple(self._hook_invocations)

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.BEFORE_RUN, ctx)

    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.BEFORE_ITERATION, ctx)

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.BEFORE_MODEL_CALL, ctx)

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.AFTER_MODEL_RESPONSE, ctx)

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.ON_MODEL_ERROR, ctx)

    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.BEFORE_TOOL_CALL, ctx)

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.AFTER_TOOL_CALL, ctx)

    async def after_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.AFTER_ITERATION, ctx)

    async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        return await self._run(MiddlewareHook.AFTER_RUN, ctx)

    def metadata(self) -> dict[str, Any]:
        """Return bounded serializable metadata for final agent results."""
        return {
            "event_count": len(self._events),
            "events": tuple(
                {
                    "middleware_name": event.middleware_name,
                    "hook": event.hook.value,
                    "action": event.action.value,
                    "reason": event.reason,
                    "metadata": dict(event.metadata),
                }
                for event in self._events
            ),
        }

    async def sleep(self, seconds: float) -> None:
        """Sleep through the pipeline's configured sleeper."""
        await self._sleeper(seconds)

    async def _run(
        self,
        hook: MiddlewareHook,
        ctx: MiddlewareContext,
    ) -> MiddlewareDecision:
        aggregate = MiddlewareDecision.continue_()
        for middleware in self.middleware:
            started_at = self.clock()
            error_type: str | None = None
            try:
                raw_decision = await getattr(middleware, hook.value)(ctx)
                decision = raw_decision or MiddlewareDecision.continue_()
            except Exception as exc:
                error_type = type(exc).__name__
                decision = self._exception_decision(middleware, hook, exc)
            self._record_hook_invocation(
                middleware,
                hook,
                decision,
                duration_seconds=max(0, self.clock() - started_at),
                error_type=error_type,
            )

            if decision.action is MiddlewareAction.CONTINUE:
                aggregate = self._merge_continue_decisions(aggregate, decision)
                continue

            if decision.action is not MiddlewareAction.CONTINUE:
                self._record(middleware, hook, decision)

            if decision.action is MiddlewareAction.SLEEP:
                await self._sleeper(decision.sleep_seconds)
                continue
            if decision.action is not MiddlewareAction.CONTINUE:
                return decision
        return aggregate

    def _merge_continue_decisions(self, current: MiddlewareDecision, next_decision: MiddlewareDecision) -> MiddlewareDecision:
        """Merge continue-decision metadata and transforms in middleware order."""
        metadata = {**dict(current.metadata), **dict(next_decision.metadata)}
        transform = self._merge_transforms(current.transform, next_decision.transform)
        return MiddlewareDecision.continue_(metadata=metadata, transform=transform)

    def _merge_transforms(self, current: MiddlewareTransform | None, next_transform: MiddlewareTransform | None) -> MiddlewareTransform | None:
        """Merge transform fields, letting later middleware override earlier fields."""
        if current is None:
            return next_transform
        if next_transform is None:
            return current
        metadata = {**dict(current.metadata), **dict(next_transform.metadata)}
        return MiddlewareTransform(
            model_visible_tool_result=next_transform.model_visible_tool_result or current.model_visible_tool_result,
            provider_messages=next_transform.provider_messages if next_transform.provider_messages is not None else current.provider_messages,
            system=next_transform.system if next_transform.system is not None else current.system,
            metadata=metadata,
        )

    def _exception_decision(
        self,
        middleware: AgentMiddleware,
        hook: MiddlewareHook,
        exc: Exception,
    ) -> MiddlewareDecision:
        metadata = {"error_type": type(exc).__name__, "error": str(exc)}
        if middleware.fail_closed:
            return MiddlewareDecision.abort("middleware_error", metadata=metadata)
        decision = MiddlewareDecision(
            action=MiddlewareAction.CONTINUE,
            reason="middleware_error_fail_open",
            metadata=metadata,
        )
        self._events.append(
            MiddlewareEvent(
                middleware_name=middleware.middleware_name,
                hook=hook,
                action=MiddlewareAction.CONTINUE,
                reason="middleware_error_fail_open",
                metadata=metadata,
            )
        )
        return decision

    def _record(
        self,
        middleware: AgentMiddleware,
        hook: MiddlewareHook,
        decision: MiddlewareDecision,
    ) -> None:
        self._events.append(
            MiddlewareEvent(
                middleware_name=middleware.middleware_name,
                hook=hook,
                action=decision.action,
                reason=decision.reason,
                metadata=dict(decision.metadata),
            )
        )

    def _record_hook_invocation(
        self,
        middleware: AgentMiddleware,
        hook: MiddlewareHook,
        decision: MiddlewareDecision,
        *,
        duration_seconds: float,
        error_type: str | None,
    ) -> None:
        # Exception text may include provider payloads, so diagnostics retain only the exception class.
        metadata = {key: value for key, value in dict(decision.metadata).items() if key != "error"}
        self._hook_invocations.append(
            MiddlewareHookInvocation(
                middleware_name=middleware.middleware_name,
                hook=hook,
                action=decision.action,
                duration_seconds=duration_seconds,
                reason=decision.reason,
                metadata=metadata,
                error_type=error_type,
            )
        )


__all__ = ["MiddlewarePipeline"]
