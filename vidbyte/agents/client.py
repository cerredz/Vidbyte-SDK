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


__all__ = [
    "AgentClient",
]
