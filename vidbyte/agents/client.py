from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent


class AgentClient:
    """Namespace client for agent constructors."""

    def base(self, **kwargs: Any) -> BaseAgent:
        return BaseAgent(**kwargs)


__all__ = [
    "AgentClient",
]
