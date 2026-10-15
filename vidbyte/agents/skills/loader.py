"""FILE: vidbyte/agents/skills/loader.py

PURPOSE: Defines SkillLoader, which turns a fixed tuple of skill entries into one SkillResolution per entry, resolving lazily on load(), grouping entries that share lookups, resolving every group at the same time, and remembering each document or permanent failure for its own lifetime so later loads cost nothing.
ROLE IN CODEBASE: Built once per agent by JevSkillsPreload.__init__ (vidbyte/agents/jev/alignment/skills.py), which calls load() at the start of every run and reads documents() to batch skills for Jev; and by any SDK caller through the root export vidbyte.SkillLoader, such as vidbyte-cli, which awaits load() and reads each SkillResolution. Dispatches each source type to its resolver module in this package.
ARCHITECTURE NOTE: The memory is resolved configuration, not run state: it is built only from the frozen entries, holds no message, answer, or usage, and lives per loader (per agent, for JevAgent), never at module level (spec D-28, INV-6). There is no lock (asyncio.Lock is banned by TID251); overlapping loads may repeat requests, but the first remembered resolution is never replaced and every load returns it (INV-10).
FUNCTION INVENTORY: SkillLoader.__init__(entries) (turns the caller's sequence into a tuple and validates it through SkillEntries; no I/O; SkillDocument entries are remembered at once); SkillLoader.load() -> tuple[SkillResolution, ...]; SkillLoader.documents() -> tuple[SkillDocument | None, ...]; SkillLoader._pending_groups() -> dict[tuple[SkillSourceType, Hashable], list[SkillEntry]].
COMMON MODIFICATION PATTERNS: A new source adds one entry to the resolver map in __init__. A change to what is remembered changes SKILL_TRANSIENT_REASONS, not this file.
WHAT NOT TO DO IN THIS FILE: 1. Do not resolve in __init__; construction must do no I/O. 2. Do not catch an exception from a resolver: a crash is a programming error and propagates before anything is remembered. 3. Do not replace a remembered resolution. 4. Do not keep memory at module level, or one tenant's private skill text would reach another tenant's agent.
KNOWN EDGE CASES: Transient reasons (RATE_LIMITED, FETCH_FAILED) are never remembered, so a blocked host costs up to one deadline per step on every run. A crash or a cancellation in any group leaves every group of that load unremembered, healthy siblings included. Results come back in settings order whatever the grouping. Construction raises ConfigurationError for text, a non-collection, a non-entry element, or a repeated name; a generator is consumed once.
RELATED DOCS: vidbyte/agents/skills/README.md; docs/spec/jev-skill-sources/spec.md (D-5, D-6, D-22, D-24, D-28, INV-4 to INV-10); docs/spec/public-skill-loader/spec.md (D-3, D-14, INV-2 to INV-5)
TESTS: tests/features/jev_skills_preload/test_skill_sources_memory.py; tests/features/jev_skills_preload/test_skill_sources_acceptance.py; tests/features/public_skill_loader/ (boundary, acceptance, security, both_doors, contract)
"""

from __future__ import annotations

import asyncio
from collections.abc import Hashable, Iterable, Sequence
from typing import Any

from vidbyte.agents.skills.anthropic import AnthropicSkillResolver
from vidbyte.agents.skills.github import GitHubSkillResolver
from vidbyte.agents.skills.inline import InlineSkillResolver
from vidbyte.agents.skills.local import LocalSkillResolver
from vidbyte.agents.skills.openai import OpenAISkillResolver
from vidbyte.agents.skills.resolver import SkillResolver
from vidbyte.agents.skills.skills_sh import SkillsShSkillResolver
from vidbyte.lib.dataclasses.skills import (
    SkillDocument,
    SkillEntries,
    SkillEntry,
    SkillResolution,
)
from vidbyte.lib.enums.skills import SkillSourceType


class SkillLoader:
    """Resolves a fixed tuple of entries lazily and remembers every non-transient result."""

    def __init__(self, entries: Sequence[SkillEntry | SkillDocument]) -> None:
        # Take the entries as a tuple, in the caller's order, and check
        # them once, here, so a wrong value fails when the loader is
        # built, before any file, key, or URL is read. Text stays
        # whole, so the check rejects it instead of reading it letter
        # by letter.
        self.entries = SkillEntries(entries=tuple(entries) if isinstance(entries, Iterable) and not isinstance(entries, (str, bytes)) else entries).entries
        # Nothing is read here. A caller's SkillDocument
        # is already resolved, so it is remembered at
        # once and can be batched before any run.
        self.memory: dict[SkillEntry | SkillDocument, SkillResolution] = {entry: SkillResolution(document=entry) for entry in self.entries if isinstance(entry, SkillDocument)}
        self.resolvers: dict[SkillSourceType, SkillResolver[Any]] = {
            SkillSourceType.INLINE: InlineSkillResolver(),
            SkillSourceType.LOCAL: LocalSkillResolver(),
            SkillSourceType.SKILLS_SH: SkillsShSkillResolver(),
            SkillSourceType.GITHUB: GitHubSkillResolver(),
            SkillSourceType.ANTHROPIC: AnthropicSkillResolver(),
            SkillSourceType.OPENAI: OpenAISkillResolver(),
        }

    async def load(self) -> tuple[SkillResolution, ...]:
        # @intent skill-loader-memory
        # Remembered entries cost nothing; only transient
        # failures are asked again. A crash or cancellation
        # propagates before anything is remembered, and a
        # remembered resolution is never replaced, so every
        # load agrees with documents() even when loads overlap.
        # Group the entries not yet remembered, so
        # entries that share lookups (one GitHub
        # repository, ref, and token) resolve together.
        groups = self._pending_groups()
        # Resolve every group at the same time.
        answers = await asyncio.gather(*(self.resolvers[kind].resolve(tuple(group)) for (kind, _), group in groups.items()), return_exceptions=True)
        # Pair each result with its entry, re-raising any crash first.
        fresh: dict[SkillEntry | SkillDocument, SkillResolution] = {}
        for group, answer in zip(groups.values(), answers, strict=True):
            if isinstance(answer, BaseException):
                raise answer
            fresh.update(zip(group, answer, strict=True))
        # Remember documents and permanent failures, keeping any value
        # an overlapping load remembered first.
        for entry, resolution in fresh.items():
            if not resolution.transient:
                self.memory.setdefault(entry, resolution)
        # Answer in settings order: the remembered resolution where one
        # exists, this load's own otherwise.
        return tuple(self.memory[entry] if entry in self.memory else fresh[entry] for entry in self.entries)

    def documents(self) -> tuple[SkillDocument | None, ...]:
        # The remembered documents in settings order; None for an entry
        # with no document yet.
        return tuple(self.memory[entry].document if entry in self.memory else None for entry in self.entries)

    def _pending_groups(self) -> dict[tuple[SkillSourceType, Hashable], list[SkillEntry]]:
        # Entries keep settings order inside each group, and groups keep
        # the order of their first entry.
        groups: dict[tuple[SkillSourceType, Hashable], list[SkillEntry]] = {}
        for entry in self.entries:
            if isinstance(entry, SkillEntry) and entry not in self.memory:
                groups.setdefault((entry.type, self.resolvers[entry.type].group_key(entry)), []).append(entry)
        return groups


__all__ = ["SkillLoader"]
