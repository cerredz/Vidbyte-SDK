from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.continual_trace import ContinualTraceAgent


class AgentClient:
    """Namespace client for agent constructors."""

    def base(self, **kwargs: Any) -> BaseAgent:
        # Constructs a normal BaseAgent from keyword options.
        return BaseAgent(**kwargs)

    def continual_trace(self, **kwargs: Any) -> ContinualTraceAgent:
        # Constructs the built-in continual trace wrapper agent.
        return ContinualTraceAgent(**kwargs)


__all__ = [
    "AgentClient",
]
