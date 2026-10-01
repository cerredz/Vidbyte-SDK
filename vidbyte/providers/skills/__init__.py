"""FILE: vidbyte/providers/skills/__init__.py

PURPOSE: Exposes the closed class-first resolver for explicit Jev skill sources.
ROLE IN CODEBASE: JevSkillsPreload calls this facade at run time; it never fetches during agent construction.
ARCHITECTURE NOTE: New source kinds are added as explicit match arms, not registered callbacks.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.providers.skills.base import SkillSourceAdapter, SkillSourceError
from vidbyte.providers.skills.file import FileSkillSourceAdapter


class SkillSourceResolver:
    """Dispatches one source through the SDK's finite adapter set."""

    def __init__(self) -> None:
        # The resolver owns fixed adapters and performs no construction-time I/O.
        self._file_adapter: SkillSourceAdapter = FileSkillSourceAdapter()

    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Resolves one source by its explicit kind and keeps the adapter set closed.
        if not isinstance(source, SkillSource):
            raise SkillSourceError("Skill source must be a SkillSource descriptor.")
        if source.kind is SkillSourceKind.FILE:
            return await self._file_adapter.resolve(source)
        if source.kind in (SkillSourceKind.GITHUB, SkillSourceKind.SKILLS_SH, SkillSourceKind.CLAUDE):
            raise SkillSourceError("Skill source could not be resolved.")
        raise SkillSourceError("Skill source kind is not supported.")


__all__ = ["SkillSourceAdapter", "SkillSourceError", "SkillSourceResolver"]
