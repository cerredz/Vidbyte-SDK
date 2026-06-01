"""Context Protocol Header

Description:
    Applies context-window algorithm iteration hooks after normal runtime iterations.
Purpose:
    Keeps iteration-hook dispatch logic out of AgentRuntime so the runtime file
    stays focused on the main execution loop.
Architecture:
    - IterationHookExecutor: Stateless applier for AgentRuntimeIterationHook callbacks.
Relations:
    Used by AgentRuntime._arun_once to delegate post-iteration hook execution.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from vidbyte.lib.dataclasses.agents import AgentRuntimeIterationState, AgentRuntimeIterationUpdate
from vidbyte.lib.dataclasses.context import BaseAgentContext
from vidbyte.lib.dataclasses.strategies import AgentResult
from vidbyte.tools.types import ToolCallContext

AgentRuntimeIterationHook = Callable[
    [AgentRuntimeIterationState],
    Awaitable[AgentRuntimeIterationUpdate | AgentResult | None],
]


class IterationHookExecutor:
    """Applies an optional context-window algorithm hook after each completed iteration."""

    async def apply(
        self,
        hook: AgentRuntimeIterationHook | None,
        *,
        message: str,
        context: BaseAgentContext,
        provider: str,
        iteration_count: int,
        model_call_count: int,
        tokens_used: int | None,
        call_contexts: list[ToolCallContext],
        model_response: object | None,
    ) -> tuple[BaseAgentContext, AgentResult | None]:
        # Pass through immediately when no algorithm hook is registered.
        if hook is None:
            return context, None
        update = await hook(
            AgentRuntimeIterationState(
                message=message,
                context=context,
                provider=provider,
                iteration_count=iteration_count,
                model_call_count=model_call_count,
                tool_call_count=len(call_contexts),
                tokens_used=tokens_used,
                call_contexts=tuple(call_contexts),
                model_response=model_response,
            )
        )
        return self._apply_update(update, context=context, call_contexts=call_contexts)

    def _apply_update(
        self,
        update: AgentRuntimeIterationUpdate | AgentResult | None,
        *,
        context: BaseAgentContext,
        call_contexts: list[ToolCallContext],
    ) -> tuple[BaseAgentContext, AgentResult | None]:
        # Propagate a terminal result, or merge context and tool-call updates into local state.
        if isinstance(update, AgentResult):
            return context, update
        if update is None:
            return context, None
        call_contexts.extend(
            ctx for ctx in update.tool_contexts if isinstance(ctx, ToolCallContext)
        )
        updated_context = update.context if isinstance(update.context, BaseAgentContext) else context
        return updated_context, None


__all__ = [
    "AgentRuntimeIterationHook",
    "IterationHookExecutor",
]
