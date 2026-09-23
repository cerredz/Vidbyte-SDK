"""FILE: vidbyte/agents/jev/specialists.py

PURPOSE: Defines strictly validated metadata and limits for Jev specialist routing.
ROLE IN CODEBASE: JevAgentSettings stores these immutable entries; JevRuntime uses their descriptions to ask one fixed TypeSafe Choice question and their agent templates to execute a selected task.
ARCHITECTURE NOTE: The template is an already configured BaseAgent and is forked for every selected run, keeping the catalog reusable and run state isolated.
COMMON MODIFICATION PATTERNS: Add only matching metadata required by the fixed Jev question; keep caller-defined questions and decision policies private.
KNOWN EDGE CASES: One option is reserved for no match, so the specialist count is lower than TypeSafe's maximum option count by one.
RELATED DOCS: docs/design/jev-specialist-routing.md and skills/jev-agent/SKILL.md.
TESTS: Existing Jev-agent verification covers this public configuration surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.jev import JevProbability
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.agents.base import BaseAgent


JEV_SPECIALIST_NO_MATCH_ID = "no_suitable_agent"
JEV_SPECIALIST_MAX_COUNT = 254
JEV_SPECIALIST_MAX_DESCRIPTION_CHARS = 4_096
JEV_SPECIALIST_MAX_ROUTING_CHARS = 32_000
JEV_SPECIALIST_DEFAULT_MATCH_THRESHOLD = 0.6


@dataclass(frozen=True, slots=True)
class JevSpecialist:
    """One registered specialist's stable choice ID, matching description, and configured agent template."""

    id: str
    description: str
    agent: BaseAgent

    def __post_init__(self) -> None:
        # Rejects ambiguous metadata and configurations that cannot be routed or executed safely.
        self._validate_identity()
        self._validate_description()
        self._validate_agent()

    def _validate_identity(self) -> None:
        # Enforces the TypeSafe option label bound and keeps the no-match label reserved.
        from vidbyte.lib.constants.jev import JEV_MAX_OPTION_NAME_CHARS

        if not isinstance(self.id, str) or not self.id.strip():
            raise ConfigurationError("JevSpecialist.id must be a non-blank string.")
        if self.id != self.id.strip() or len(self.id) > JEV_MAX_OPTION_NAME_CHARS:
            raise ConfigurationError(f"JevSpecialist.id must be trimmed and at most {JEV_MAX_OPTION_NAME_CHARS} characters.")
        if self.id == JEV_SPECIALIST_NO_MATCH_ID:
            raise ConfigurationError(f"JevSpecialist.id {JEV_SPECIALIST_NO_MATCH_ID!r} is reserved for the no-match option.")

    def _validate_description(self) -> None:
        # Requires a bounded description because it is sent to the decision model on every routed run.
        if not isinstance(self.description, str) or not self.description.strip() or self.description != self.description.strip():
            raise ConfigurationError("JevSpecialist.description must be a trimmed, non-blank string.")
        if len(self.description) > JEV_SPECIALIST_MAX_DESCRIPTION_CHARS:
            raise ConfigurationError(f"JevSpecialist.description must be at most {JEV_SPECIALIST_MAX_DESCRIPTION_CHARS} characters.")

    def _validate_agent(self) -> None:
        # Requires a configured agent template and disallows recursively nested Jev routing.
        from vidbyte.agents.base import BaseAgent
        from vidbyte.lib.enums import AgentRuntimeType

        if not isinstance(self.agent, BaseAgent):
            raise ConfigurationError("JevSpecialist.agent must be a configured BaseAgent instance.")
        if self.agent.runtime_type is AgentRuntimeType.JEV:
            raise ConfigurationError("JevSpecialist.agent cannot use the jev runtime.")


class JevSpecialistCatalog:
    """Validates specialist collection invariants before JevAgent construction."""

    @staticmethod
    def validate(agents: tuple[JevSpecialist, ...], threshold: float) -> float:
        """Validates catalog invariants and returns the normalized probability threshold."""
        if len(agents) > JEV_SPECIALIST_MAX_COUNT:
            raise ConfigurationError(f"JevAgentSettings.agents supports at most {JEV_SPECIALIST_MAX_COUNT} specialists.")
        identifiers = tuple(agent.id for agent in agents)
        if len(set(identifiers)) != len(identifiers):
            raise ConfigurationError("JevAgentSettings.agents must have unique specialist IDs.")
        catalog_chars = sum(len(agent.id) + len(agent.description) for agent in agents)
        if catalog_chars > JEV_SPECIALIST_MAX_ROUTING_CHARS:
            raise ConfigurationError(f"JevAgentSettings.agents metadata must fit within {JEV_SPECIALIST_MAX_ROUTING_CHARS} characters in total.")
        try:
            return JevProbability.require(threshold, field_name="JevAgentSettings.specialist_match_threshold")
        except OverflowError as exc:
            raise ConfigurationError("JevAgentSettings.specialist_match_threshold must be a finite number between 0 and 1.") from exc


__all__ = [
    "JEV_SPECIALIST_DEFAULT_MATCH_THRESHOLD",
    "JEV_SPECIALIST_MAX_COUNT",
    "JEV_SPECIALIST_MAX_DESCRIPTION_CHARS",
    "JEV_SPECIALIST_MAX_ROUTING_CHARS",
    "JEV_SPECIALIST_NO_MATCH_ID",
    "JevSpecialist",
    "JevSpecialistCatalog",
]
