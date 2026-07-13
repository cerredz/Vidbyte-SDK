"""Context Protocol Header

PURPOSE:
    Defines AgentClient, a small namespace that exposes ergonomic constructors for
    the SDK's agent types so callers can build a base or handoff agent through one
    discoverable entry point instead of importing each class directly.
ROLE IN CODEBASE:
    Thin façade over vidbyte.agents.base.BaseAgent and
    vidbyte.agents.handoff.HandoffAgent; consumed by the top-level SDK client.
ARCHITECTURE:
    - AgentClient: stateless namespace whose methods forward keyword configuration
      to the underlying agent constructors.
FUNCTION INVENTORY:
    - AgentClient.base(**kwargs): construct a standard BaseAgent.
    - AgentClient.handoff(handoff, **kwargs): construct a HandoffAgent.
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


__all__ = [
    "AgentClient",
]
