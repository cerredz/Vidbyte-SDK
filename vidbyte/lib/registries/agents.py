"""Context Protocol Header

Description:
    Agent registry for local discovery, capability matching, and tool exposure.
Purpose:
    Allows modular systems to register and find active agent instances by capabilities,
    tool names, or metadata without hardcoding linkages.
Architecture:
    - AgentRegistry: In-memory registry containing BaseAgent cards and search methods.
Key Functions:
    - register: Registers a live agent instance.
    - get: Retrieves an agent by its unique name.
    - find: Searches for agents matching capabilities, tools, or metadata.
Relations:
    Located in vidbyte/lib/registries/agents.py. Consumed by BaseAgent.
Similar Files:
    - vidbyte/lib/registries/actors.py: Prebuilt actor class registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from vidbyte.agents.types import AgentCard
from vidbyte.lib.errors import AgentRegistryError

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


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
        capability: str | None = None,
        tool_name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[BaseAgent, ...]:
        matches: list[BaseAgent] = []
        for agent in self._agents.values():
            card = agent.card()
            if capability is not None and capability not in card.capabilities:
                continue
            if tool_name is not None and tool_name not in card.tool_names:
                continue
            if metadata is not None and any(card.metadata.get(key) != value for key, value in metadata.items()):
                continue
            matches.append(agent)
        return tuple(matches)
