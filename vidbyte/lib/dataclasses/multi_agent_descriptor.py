"""Context Protocol Header

Description:
    Defines the MultiAgentDescriptor dataclass — a thin composition wrapper for
    YAML-loaded multi-agent team configurations. Composes the existing
    MultiAgentSettings class and nested AgentDescriptor objects for the
    orchestrator and worker agents.
Purpose:
    Provides a typed configuration object that the YamlLoader produces from a
    multi-agent YAML document. Validates team uniqueness constraints and delegates
    budget validation to MultiAgentSettings.
Architecture:
    - MultiAgentDescriptor: frozen dataclass composing MultiAgentSettings and
      AgentDescriptor instances.
    - __post_init__ validates identity, orchestrator/worker presence, name uniqueness.
    - to_agent_kwargs() maps to MultiAgent.__init__ keyword arguments.
Relations:
    - Produced by vidbyte/lib/config/loader.py.
    - Composes AgentDescriptor from vidbyte/lib/dataclasses/agent_descriptor.py.
    - Composes MultiAgentSettings from vidbyte/lib/dataclasses/multi_agent.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from vidbyte.lib.dataclasses.multi_agent import MultiAgentSettings
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.agent_descriptor import AgentDescriptor

_MAX_NAME_CHARS = 256
_MAX_SYSTEM_PROMPT_CHARS = 500_000
_MAX_DESCRIPTION_CHARS = 2000


@dataclass(frozen=True, slots=True)
class MultiAgentDescriptor:
    """Typed multi-agent team configuration loaded from a YAML document."""

    name: str = ""
    system_prompt: str = ""
    description: str = ""
    orchestrator: "AgentDescriptor | None" = None
    agents: tuple["AgentDescriptor", ...] = ()
    settings: MultiAgentSettings = field(default_factory=MultiAgentSettings)
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validates team identity, orchestrator presence, and worker name uniqueness.
        self._validate_identity()
        self._validate_orchestrator()
        self._validate_workers()

    def to_agent_kwargs(self, *, orchestrator_instance: Any = None, worker_instances: Sequence[Any] = ()) -> dict[str, Any]:
        # Returns keyword arguments for MultiAgent.__init__ after the caller supplies live agent instances.
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "description": self.description,
            "orchestrator": orchestrator_instance,
            "agents": tuple(worker_instances),
            "settings": self.settings,
            "capabilities": self.capabilities,
            "metadata": dict(self.metadata),
        }

    def _validate_identity(self) -> None:
        # Validates name and system_prompt are non-empty and within length limits.
        if not self.name or not self.name.strip():
            raise ConfigurationError(
                "Multi-agent team name must be a non-empty string.",
                details={"field": "name", "expected": "non-empty string"},
            )
        if len(self.name) > _MAX_NAME_CHARS:
            raise ConfigurationError(
                f"Multi-agent team name must be at most {_MAX_NAME_CHARS} characters.",
                details={"field": "name", "max_chars": _MAX_NAME_CHARS, "actual_chars": len(self.name)},
            )
        if not self.system_prompt or not self.system_prompt.strip():
            raise ConfigurationError(
                "Multi-agent team system_prompt must be a non-empty string.",
                details={"field": "system_prompt", "expected": "non-empty string"},
            )
        if len(self.system_prompt) > _MAX_SYSTEM_PROMPT_CHARS:
            raise ConfigurationError(
                f"Multi-agent team system_prompt must be at most {_MAX_SYSTEM_PROMPT_CHARS} characters.",
                details={"field": "system_prompt", "max_chars": _MAX_SYSTEM_PROMPT_CHARS, "actual_chars": len(self.system_prompt)},
            )
        if len(self.description) > _MAX_DESCRIPTION_CHARS:
            raise ConfigurationError(
                f"Multi-agent team description must be at most {_MAX_DESCRIPTION_CHARS} characters.",
                details={"field": "description", "max_chars": _MAX_DESCRIPTION_CHARS, "actual_chars": len(self.description)},
            )

    def _validate_orchestrator(self) -> None:
        # Validates the orchestrator agent is present and has a non-empty name.
        if self.orchestrator is None:
            raise ConfigurationError(
                "Multi-agent team must have an orchestrator agent.",
                details={"field": "orchestrator", "expected": "non-null AgentDescriptor"},
            )
        if not self.orchestrator.name or not self.orchestrator.name.strip():
            raise ConfigurationError(
                "Multi-agent team orchestrator must have a non-empty name.",
                details={"field": "orchestrator.name", "expected": "non-empty string"},
            )
        if not self.orchestrator.system_prompt or not self.orchestrator.system_prompt.strip():
            raise ConfigurationError(
                "Multi-agent team orchestrator must have a non-empty system_prompt.",
                details={"field": "orchestrator.system_prompt", "expected": "non-empty string"},
            )

    def _validate_workers(self) -> None:
        # Validates at least one worker agent, unique names, and no name collisions with team or orchestrator.
        if not self.agents:
            raise ConfigurationError(
                "Multi-agent team must have at least one worker agent.",
                details={"field": "agents", "expected": "at least one AgentDescriptor"},
            )
        seen: set[str] = set()
        orchestrator_name = self.orchestrator.name if self.orchestrator else ""
        for index, agent in enumerate(self.agents):
            if not agent.name or not agent.name.strip():
                raise ConfigurationError(
                    f"Worker agent at index {index} must have a non-empty name.",
                    details={"field": f"agents[{index}].name", "expected": "non-empty string"},
                )
            if not agent.system_prompt or not agent.system_prompt.strip():
                raise ConfigurationError(
                    f"Worker agent '{agent.name}' at index {index} must have a non-empty system_prompt.",
                    details={"field": f"agents[{index}].system_prompt", "expected": "non-empty string"},
                )
            if agent.name == self.name:
                raise ConfigurationError(
                    f"Worker agent name '{agent.name}' must not match the team name.",
                    details={"field": f"agents[{index}].name", "actual": agent.name, "team_name": self.name},
                )
            if orchestrator_name and agent.name == orchestrator_name:
                raise ConfigurationError(
                    f"Worker agent name '{agent.name}' must not match the orchestrator name.",
                    details={"field": f"agents[{index}].name", "actual": agent.name, "orchestrator": orchestrator_name},
                )
            if agent.name in seen:
                raise ConfigurationError(
                    f"Duplicate worker agent name '{agent.name}' at index {index}.",
                    details={"field": f"agents[{index}].name", "actual": agent.name},
                )
            seen.add(agent.name)


__all__ = ["MultiAgentDescriptor"]
