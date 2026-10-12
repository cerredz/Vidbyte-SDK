"""FILE: vidbyte/agents/skills/resolver.py

PURPOSE: Defines SkillResolver, the base every skill source implements: it turns a group of entries of one source into one SkillResolution per entry, and says which entries may share lookups.
ROLE IN CODEBASE: Subclassed once per source in this package (inline, local, skills_sh, github, and the vendor base for anthropic and openai); SkillLoader in loader.py groups pending entries by (entry.type, resolver.group_key(entry)) and calls resolve once per group.
ARCHITECTURE NOTE: Generic over the entry type so each subclass's resolve signature names its own entry class and mypy (S009) sees no override errors. The base holds no state and does no I/O.
FUNCTION INVENTORY: SkillResolver.group_key(entry) -> Hashable (default: the entry itself); SkillResolver.resolve(entries) -> tuple[SkillResolution, ...] (abstract).
COMMON MODIFICATION PATTERNS: A source whose entries can share requests overrides group_key, as GitHubSkillResolver does with (repo, ref, token). Every other source keeps the default, so each of its groups holds exactly one entry.
WHAT NOT TO DO IN THIS FILE: Do not add a per-entry fan-out helper to the base; each resolver's resolve is its one narrated main (spec D-22). Do not catch broad exceptions here.
KNOWN EDGE CASES: Entries are frozen, hashable dataclasses with unique names, so the default key never merges two entries.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md
TESTS: tests/features/jev_skills_preload/test_skill_sources_memory.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import Generic, TypeVar

from vidbyte.lib.dataclasses.skills import SkillEntry, SkillResolution

SkillEntryT = TypeVar("SkillEntryT", bound=SkillEntry)


class SkillResolver(ABC, Generic[SkillEntryT]):
    """Turns a group of one source's entries into one SkillResolution per entry, in order."""

    def group_key(self, entry: SkillEntryT) -> Hashable:
        # Entries with equal keys share lookups;
        # by default each entry is its own group.
        return entry

    @abstractmethod
    async def resolve(self, entries: tuple[SkillEntryT, ...]) -> tuple[SkillResolution, ...]:
        """Resolve entries that share one group key; return one resolution per entry, in order."""


__all__ = ["SkillEntryT", "SkillResolver"]
