"""Context Protocol Header

Description:
    Builds and renders multi-agent orchestration context through ContextManager.
Purpose:
    Provides one context-layer abstraction for controller snapshots and manager
    prompt primitives so agent runtimes do not implement custom context logic.
Architecture:
    - build creates the immutable OrchestrationContext boundary.
    - render_orchestration composes standard multi-agent primitives.
    - render_finalization appends terminal primitives to the same base view.
Relations:
    Used by vidbyte.agents.multi runtime collaborators and MagenticOneOrchestrator.
"""

from __future__ import annotations

from collections.abc import Sequence
from vidbyte.agents.types import AgentCard, AgentInput, AgentMessage
from vidbyte.context.manager import ContextManager
from vidbyte.context.primitives.base import ContextItem
from vidbyte.context.primitives.multi_agent import (
    MultiAgentLedgerContextItem,
    MultiAgentLimitsContextItem,
    MultiAgentReportContextItem,
    MultiAgentRequestContextItem,
    MultiAgentTeamContextItem,
    MultiAgentTerminalContextItem,
)
from vidbyte.context.runtime import ContextWindowPlacement
from vidbyte.lib.dataclasses.context import BaseContext
from vidbyte.lib.dataclasses.multi_agent import AgentReport, FinalizationContext, MultiAgentSettings, OrchestrationContext, TaskLedgerSnapshot


class MultiAgentContext:
    """Owns multi-agent context construction and primitive composition."""

    def build(
        self,
        *,
        request: AgentInput,
        team_instructions: str,
        team: Sequence[AgentCard],
        ledger: TaskLedgerSnapshot,
        settings: MultiAgentSettings,
        context: BaseContext | None,
        history: Sequence[AgentMessage],
        round: int,
        replans: int,
        stalls: int,
        last_report: AgentReport | None,
    ) -> OrchestrationContext:
        # One constructor path keeps every manager phase on the same immutable contract.
        return OrchestrationContext(
            request=request,
            team_instructions=team_instructions,
            team=tuple(team),
            ledger=ledger,
            settings=settings,
            context=context,
            history=tuple(history),
            round=round,
            replans=replans,
            stalls=stalls,
            last_report=last_report,
        )

    @classmethod
    def render_orchestration(cls, context: OrchestrationContext) -> str:
        # ContextManager preserves primitive ordering and keeps rendering policy centralized.
        manager = ContextManager()
        for item in cls._orchestration_items(context):
            manager.upsert(item, placement=ContextWindowPlacement.END_OF_CONVERSATION)
        messages = manager.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)
        return "\n".join(message["content"] for message in messages)

    @classmethod
    def render_finalization(cls, context: FinalizationContext) -> str:
        # Terminal synthesis extends the exact same primitive sequence used for planning.
        manager = ContextManager()
        items = (*cls._orchestration_items(context.orchestration), MultiAgentTerminalContextItem(context))
        for item in items:
            manager.upsert(item, placement=ContextWindowPlacement.END_OF_CONVERSATION)
        messages = manager.render_conversation_messages(ContextWindowPlacement.END_OF_CONVERSATION)
        return "\n".join(message["content"] for message in messages)

    @classmethod
    def _orchestration_items(cls, context: OrchestrationContext) -> tuple[ContextItem, ...]:
        # Stable ordering places trust instructions before mutable ledger/report state and budgets.
        return (
            MultiAgentRequestContextItem(context.request.prompt),
            MultiAgentTeamContextItem(context.team_instructions, context.team),
            MultiAgentLedgerContextItem(context.ledger),
            MultiAgentReportContextItem(context.last_report),
            MultiAgentLimitsContextItem(context.settings, context.round, context.replans, context.stalls),
        )


__all__ = ["MultiAgentContext"]
