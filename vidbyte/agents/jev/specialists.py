"""FILE: vidbyte/agents/jev/specialists.py

PURPOSE: Defines decision-only specialist descriptions used as options in Jev's preflight question.
ROLE IN CODEBASE: JevAgentSettings validates a sequence of JevSpecialist records; JevPreflightGate sends their descriptive metadata to TypeSafe and stores the selected title.
ARCHITECTURE NOTE: These records intentionally contain no BaseAgent or execution settings. The configured JevAgent remains the one linear generative agent after preflight.
FUNCTION INVENTORY: JevSpecialist(title, description, metadata) validates a profile label and freezes its JSON-compatible metadata.
COMMON MODIFICATION PATTERNS: Add only fields useful for choosing among profile scopes; keep question construction in gate.py and prompt vocabularies in lib/enums/jev.py.
WHAT NOT TO DO IN THIS FILE: 1. Do not import BaseAgent or provider runners. 2. Do not add profile execution configuration; Jev runs its existing linear agent.
KNOWN EDGE CASES: Profile order is preserved and breaks probability ties deterministically.
RELATED DOCS: https://github.com/cerredz/Vidbyte-SDK/blob/main/skills/jev-agent/SKILL.md
TESTS: tests/test_jev_agent.py and tests/test_jev_preflight.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from vidbyte.lib.dataclasses.jev import JevJson, JevValidation


@dataclass(frozen=True, slots=True)
class JevSpecialist:
    """A named scope description used by Jev to choose a task label, not an executable agent."""

    title: str
    description: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.title, str) or not self.title.strip() or self.title != self.title.strip():
            raise JevValidation.error("JevSpecialist.title", "a trimmed, non-blank string", self.title)
        if not isinstance(self.description, str) or not self.description.strip() or self.description != self.description.strip():
            raise JevValidation.error("JevSpecialist.description", "a trimmed, non-blank string", self.description)
        if not isinstance(self.metadata, Mapping):
            raise JevValidation.error("JevSpecialist.metadata", "a JSON object", self.metadata)
        frozen = JevJson.freeze(self.metadata, field_name="JevSpecialist.metadata")
        if not isinstance(frozen, Mapping):
            raise JevValidation.error("JevSpecialist.metadata", "a JSON object", self.metadata)
        object.__setattr__(self, "metadata", frozen)


__all__ = ["JevSpecialist"]
