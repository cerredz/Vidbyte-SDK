"""FILE: vidbyte/lib/dataclasses/skills.py

PURPOSE: Defines the immutable caller-facing data contract for plain skill text selected by JevAgent before its main loop.
ROLE IN CODEBASE: JevAlignmentSettings normalizes strings and accepts these records; JevSkillsPreload sends their fields as decision state and injects selected text into one run's context.
ARCHITECTURE NOTE: This is resolved content only. It does not fetch `source`, interpret metadata as instructions, or attach provider-specific native references.
FUNCTION INVENTORY:
    SkillDocument.__post_init__() -> None: validates required text and optional source while leaving every accepted string unchanged.
COMMON MODIFICATION PATTERNS: Extend this plain document contract only for caller-resolved skill content; source adapters and provider-native references belong in separate follow-on work.
WHAT NOT TO DO:
    1. Do not normalize, trim, or rewrite the supplied body.
    2. Do not fetch the optional source value from this dataclass.
    3. Do not add provider-specific behavior to this data-only module.
KNOWN EDGE CASES: Nonblank validation uses whitespace only to reject empty values; the exact accepted strings remain stored for prompt injection and provenance.
RELATED DOCS: `docs/design/jev-skills-preload.md` and `tests/features/jev_skills_preload/FEATURE.md`.
TESTS: `tests/test_jev_skill_preload.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class SkillDocument:
    """One caller-supplied skill body and the metadata used to identify it."""

    name: str
    description: str
    text: str
    source: str | None = None

    def __post_init__(self) -> None:
        # @intent preserve-caller-skill-text
        # Relevance scoring and prompt injection must see the exact body the caller configured. Trimming may
        # silently change code blocks, indentation-sensitive examples, or meaningful leading/trailing text.
        """Validate metadata while retaining every supplied string exactly."""
        for field_name in ("name", "description", "text"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"SkillDocument.{field_name} must be non-blank text.")
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            raise ConfigurationError("SkillDocument.source must be None or non-blank text.")


__all__ = ["SkillDocument"]
