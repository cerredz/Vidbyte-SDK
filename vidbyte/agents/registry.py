from __future__ import annotations

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentCard, AgentRole
from vidbyte.lib.errors import AgentRegistryError


class AgentRegistry:
    """Local in-process registry for agent discovery."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        if agent.name in self._agents:
            raise AgentRegistryError(f"Agent '{agent.name}' is already registered.")
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise AgentRegistryError(f"Agent '{name}' is not registered.") from exc

    def all(self) -> tuple[BaseAgent, ...]:
        return tuple(self._agents.values())

    def cards(self) -> tuple[AgentCard, ...]:
        return tuple(agent.card() for agent in self._agents.values())

    def find(
        self,
        *,
        role: AgentRole | None = None,
        capability: str | None = None,
        tool_name: str | None = None,
    ) -> tuple[BaseAgent, ...]:
        matches: list[BaseAgent] = []
        for agent in self._agents.values():
            card = agent.card()
            if role is not None and card.role != role:
                continue
            if capability is not None and capability not in card.capabilities:
                continue
            if tool_name is not None and tool_name not in card.tool_names:
                continue
            matches.append(agent)
        return tuple(matches)
