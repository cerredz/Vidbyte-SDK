"""Context Protocol Header

Description:
    Provides the lightweight namespace client for constructing Vidbyte agent facades.
Purpose:
    Keeps `sdk.agents` ergonomic while deferring feature imports until their constructor is requested.
Architecture:
    AgentClient routes base, handoff, continual-trace, aggregate, and ledger-driven multi-agent constructors.
Relations:
    Constructed by `VidbyteSDK`; feature implementations remain owned by their packages under `vidbyte.agents`.
"""

from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.handoff import HandoffAgent
from vidbyte.context.handoff import Handoff


class AgentClient:
    """Namespace client for agent constructors."""

    def base(self, **kwargs: Any) -> BaseAgent:
        # Construct a standard base agent from keyword configuration.
        return BaseAgent(**kwargs)

    def handoff(self, handoff: Handoff | None = None, **kwargs: Any) -> HandoffAgent:
        # Construct a handoff agent for a given handoff spec, defaulting to MinimalHandoff.
        return HandoffAgent(handoff, **kwargs)

    def continual_trace(self, schema: Any, **kwargs: Any) -> Any:
        # Construct a continual trace agent that fills the given trace schema.
        from vidbyte.agents.continual_trace import ContinualTraceAgent
        return ContinualTraceAgent(schema, **kwargs)

    def aggregate(self, **kwargs: Any) -> Any:
        # Construct an AggregateAgent that fans out to multiple proposer models and synthesizes one answer.
        from vidbyte.agents.aggregation import AggregateAgent
        return AggregateAgent(**kwargs)

    def multi(self, **kwargs: Any) -> Any:
        # Construct a ledger-driven MultiAgent team with explicit manager and worker controls.
        from vidbyte.agents.multi import MultiAgent
        return MultiAgent(**kwargs)


__all__ = [
    "AgentClient",
]
