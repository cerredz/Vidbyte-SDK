"""
FILE: vidbyte/middleware/pipeline.py

PURPOSE:
    Implements ordered middleware hook dispatch for agent runtime middleware. Centralizes middleware decision handling, sleeps, exception policy, and metadata events so AgentRuntime remains focused on the model/tool loop.
    This header is the agentic-engineering navigation point for future agents that open this file cold.

ROLE IN CODEBASE:
    This file sits in the vidbyte/middleware layer, which owns deterministic runtime policy, lifecycle hooks, compaction, retry, and safety controls.
    It should be read with `vidbyte/middleware/README.md` before broad edits so folder-level non-goals and routing rules are visible.

FILE DEPENDENCIES:
    - vidbyte.lib.dataclasses.middleware: imported by this file.
    - vidbyte.middleware.base: imported by this file.

FUNCTION INVENTORY:
    - MiddlewarePipeline (class): public or navigational symbol owned here.
    - MiddlewarePipeline (export): public or navigational symbol owned here.

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
    - None observed in this file; preserve this when adding new failure paths.

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

    @property
    def events(self) -> tuple[MiddlewareEvent, ...]:
        """Return middleware events recorded so far."""
        return tuple(self._events)

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
            try:
                raw_decision = await getattr(middleware, hook.value)(ctx)
                decision = raw_decision or MiddlewareDecision.continue_()
            except Exception as exc:
                decision = self._exception_decision(middleware, hook, exc)

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
        # Fail-closed middleware protects runtime invariants; fail-open middleware records context and preserves progress.
        metadata = {"error_type": type(exc).__name__, "error": str(exc)}
        if middleware.fail_closed:
            return MiddlewareDecision.abort("middleware_error", metadata=metadata)
        decision = MiddlewareDecision.continue_(metadata=metadata)
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


__all__ = ["MiddlewarePipeline"]
