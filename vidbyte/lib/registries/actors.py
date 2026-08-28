"""Context Protocol Header

Description:
    Actor registry mapping prebuilt and custom actor roles to their classes.
Purpose:
    Allows developers to discover, list, and instantiate prebuilt and custom actors.
Architecture:
    - ActorRegistry: Centralized registry managing prebuilt actor classes.
Key Functions:
    - register: Registers a prebuilt or custom actor class.
    - get: Returns the actor class for a role name.
    - list: Returns a list of all registered role names.
    - all: Returns the entire dictionary of registered actor classes.
Relations:
    Located in vidbyte/lib/registries/actors.py. Imported by ActorRuntime and BaseAgent.
Similar Files:
    - vidbyte/lib/registries/agents.py: Agent registry.
    - vidbyte/lib/registries/tools.py: Tools registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.runtimes.actor.actor import PrebuiltActor


class ActorRegistry:
    """Registry for discovering and managing prebuilt agent actors."""

    def __init__(self) -> None:
        # Dictionary storing registered prebuilt actor classes mapped by lower role name.
        self._actors: dict[str, type[PrebuiltActor]] = {}

    def register(self, role_name: str, actor_cls: type[PrebuiltActor]) -> None:
        # Registers a prebuilt or custom actor class to the internal catalog.
        self._actors[role_name.strip().lower()] = actor_cls

    def get(self, role_name: str) -> type[PrebuiltActor]:
        # Returns a registered actor class by its role name.
        key = role_name.strip().lower()
        if key not in self._actors:
            raise ConfigurationError(f"Actor '{role_name}' is not registered in the catalog.")
        return self._actors[key]

    def list(self) -> list[str]:
        # Returns a sorted list of all registered actor role names.
        return sorted(list(self._actors.keys()))

    def all(self) -> dict[str, type[PrebuiltActor]]:
        # Returns a dictionary copy of all registered actor classes.
        return dict(self._actors)


# Global shared instance of the actor registry.
actor_registry = ActorRegistry()
