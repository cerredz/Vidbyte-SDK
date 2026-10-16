"""FILE: vidbyte/agents/skills/inline.py

PURPOSE: Defines InlineSkillResolver, which turns an InlineSkill entry (description and text written in the settings) into a SkillDocument labelled "inline".
ROLE IN CODEBASE: Registered for SkillSourceType.INLINE in SkillLoader (loader.py). It is the only source that never reads a file or the network.
ARCHITECTURE NOTE: The entry was validated at construction, so resolving it cannot fail; the text is copied exactly.
FUNCTION INVENTORY: InlineSkillResolver.resolve(entries) -> tuple[SkillResolution, ...].
COMMON MODIFICATION PATTERNS: None expected; a change to what an inline skill holds belongs to InlineSkill in vidbyte/lib/dataclasses/skills.py.
WHAT NOT TO DO IN THIS FILE: Do not trim or rewrite the text, and do not parse it as a SKILL.md: inline text has no frontmatter.
KNOWN EDGE CASES: The label is SkillSourceType.INLINE.value, the same label the settings give a plain string.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-21)
TESTS: tests/features/jev_skills_preload/test_skill_sources_jev_wiring.py; tests/features/jev_skills_preload/test_skill_sources_memory.py
"""

from __future__ import annotations

from vidbyte.agents.skills.resolver import SkillResolver
from vidbyte.lib.dataclasses.skills import InlineSkill, SkillDocument, SkillResolution
from vidbyte.lib.enums.skills import SkillSourceType


class InlineSkillResolver(SkillResolver[InlineSkill]):
    """Copies an inline entry's description and text into a document; no I/O."""

    async def resolve(self, entries: tuple[InlineSkill, ...]) -> tuple[SkillResolution, ...]:
        # The entry already holds everything a document needs.
        return tuple(SkillResolution(document=SkillDocument(name=entry.name, description=entry.description, text=entry.text, source=SkillSourceType.INLINE.value)) for entry in entries)


__all__ = ["InlineSkillResolver"]
