"""FILE: vidbyte/lib/dataclasses/skills.py

PURPOSE: Defines immutable caller-facing contracts for explicit skill sources, resolved text, and Claude-native references.
ROLE IN CODEBASE: JevAlignmentSettings accepts these records; provider adapters resolve sources and JevSkillsPreload selects candidates before the main loop.
ARCHITECTURE NOTE: Source descriptors do not fetch during construction; resolution belongs to the explicit provider adapter boundary.
FUNCTION INVENTORY:
    SkillSource.__post_init__() -> None: validates named descriptor fields and options compatible with its closed source kind.
    SkillDocument.__post_init__() -> None: validates text-backed or native-reference content while retaining accepted text exactly.
COMMON MODIFICATION PATTERNS: Keep skill retrieval in vidbyte.skills.sources and model API calls in vidbyte.providers.
WHAT NOT TO DO:
    1. Do not normalize, trim, or rewrite the supplied body.
    2. Do not fetch source locations from these dataclasses.
    3. Do not put provider request logic in this data-only module.
KNOWN EDGE CASES: Nonblank validation uses whitespace only to reject empty values; the exact accepted strings remain stored for prompt injection and provenance.
RELATED DOCS: `docs/design/jev-skills-preload.md` and `tests/features/jev_skills_preload/FEATURE.md`.
TESTS: `tests/test_jev_skill_preload.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.lib.enums.skills import ClaudeSkillType, SkillSourceKind
from vidbyte.lib.errors import ConfigurationError


class _ClaudeSessionDefault(Enum):
    CONFIG = "config"


_USE_CONFIGURED_CLAUDE_SESSION = _ClaudeSessionDefault.CONFIG


@dataclass(frozen=True, slots=True)
class SkillSource:
    """One explicit source descriptor; provider-specific validity is checked during run-time resolution."""

    kind: SkillSourceKind
    location: str = field(repr=False)
    skill_name: str | None = None
    revision: str | None = None
    version: str | None = None
    api_key: str | None = field(default=None, repr=False)
    workspace_id: str | None = None

    def __post_init__(self) -> None:
        # Reject malformed contracts before source lookup can perform I/O.
        if not isinstance(self.kind, SkillSourceKind):
            raise ConfigurationError("SkillSource.kind must be a SkillSourceKind.")
        if not isinstance(self.location, str) or not self.location.strip():
            raise ConfigurationError("SkillSource.location must be non-blank text.")
        for field_name in ("skill_name", "revision", "version", "api_key", "workspace_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ConfigurationError(f"SkillSource.{field_name} must be None or non-blank text.")
        allowed = {
            SkillSourceKind.FILE: frozenset({"skill_name"}),
            SkillSourceKind.GITHUB: frozenset({"skill_name", "revision", "api_key"}),
            SkillSourceKind.SKILLS_SH: frozenset({"skill_name", "revision", "api_key"}),
            SkillSourceKind.CLAUDE: frozenset({"skill_name", "version", "api_key", "workspace_id"}),
        }[self.kind]
        incompatible = tuple(
            name for name in ("revision", "version", "api_key", "workspace_id")
            if getattr(self, name) is not None and name not in allowed
        )
        if incompatible:
            raise ConfigurationError("SkillSource options are incompatible with its kind.", details={"fields": incompatible, "kind": self.kind.value})


@dataclass(frozen=True, slots=True)
class ClaudeSkillReference:
    """Opaque Claude Skill identity mounted through the Anthropic container API."""

    skill_id: str
    version: str
    type: ClaudeSkillType

    def __post_init__(self) -> None:
        # Reject malformed native IDs before they enter provider call options.
        if not isinstance(self.skill_id, str) or not self.skill_id.strip():
            raise ConfigurationError("ClaudeSkillReference.skill_id must be non-blank text.")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ConfigurationError("ClaudeSkillReference.version must be non-blank text.")
        if not isinstance(self.type, ClaudeSkillType):
            raise ConfigurationError("ClaudeSkillReference.type must be a ClaudeSkillType.")


@dataclass(frozen=True, slots=True)
class ClaudeSkillSession:
    """Container identity and exact paused exchange history returned by Anthropic."""

    container_id: str
    paused: bool
    resume_messages: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        # Preserve an isolated, exact replay snapshot only while Anthropic is paused.
        if not isinstance(self.container_id, str) or not self.container_id.strip():
            raise ConfigurationError("ClaudeSkillSession.container_id must be non-blank text.")
        if not isinstance(self.paused, bool):
            raise ConfigurationError("ClaudeSkillSession.paused must be True or False.")
        if not isinstance(self.resume_messages, tuple) or not all(isinstance(message, Mapping) for message in self.resume_messages):
            raise ConfigurationError("ClaudeSkillSession.resume_messages must be a tuple of message mappings.")
        snapshot = tuple(deepcopy(dict(message)) for message in self.resume_messages)
        if self.paused:
            if not snapshot or snapshot[-1].get("role") != "assistant" or "content" not in snapshot[-1]:
                raise ConfigurationError("A paused ClaudeSkillSession requires full assistant content in resume_messages.")
        elif snapshot:
            raise ConfigurationError("A completed ClaudeSkillSession cannot retain resume_messages.")
        object.__setattr__(self, "resume_messages", snapshot)


@dataclass(frozen=True, slots=True)
class SkillDocument:
    """Resolved skill metadata with either exact text or an opaque Claude reference."""

    name: str
    description: str
    text: str | None
    source: str | None = None
    claude_reference: ClaudeSkillReference | None = None

    def __post_init__(self) -> None:
        # @intent preserve-caller-skill-text
        # Relevance scoring and prompt injection must see the exact body the caller configured. Trimming may
        # silently change code blocks, indentation-sensitive examples, or meaningful leading/trailing text.
        """Validate metadata and enforce exactly one usable content mode."""
        for field_name in ("name", "description"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"SkillDocument.{field_name} must be non-blank text.")
        if self.text is None:
            if not isinstance(self.claude_reference, ClaudeSkillReference):
                raise ConfigurationError("SkillDocument.text may be None only with a ClaudeSkillReference.")
        elif not isinstance(self.text, str) or not self.text.strip() or self.claude_reference is not None:
            raise ConfigurationError("SkillDocument requires non-blank text without a Claude reference, or a bodyless native reference.")
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            raise ConfigurationError("SkillDocument.source must be None or non-blank text.")


__all__ = ["ClaudeSkillReference", "ClaudeSkillSession", "SkillDocument", "SkillSource"]
