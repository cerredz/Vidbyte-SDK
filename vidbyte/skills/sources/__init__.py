"""FILE: vidbyte/skills/sources/__init__.py

PURPOSE: Exposes the closed class-first resolver for explicit Jev skill sources.
ROLE IN CODEBASE: JevSkillsPreload calls this facade at run time; it never fetches during agent construction.
ARCHITECTURE NOTE: New source kinds are added as explicit match arms, not registered callbacks.
COMMON MODIFICATION PATTERNS: Update the finite resolver dispatch when a named source kind is added.
KNOWN EDGE CASES: Expected provider failures become indexed source failures; cancellation propagates unchanged.
RELATED DOCS: docs/design/jev-skill-providers.md and docs/jev-skill-providers.md.
TESTS: tests/test_jev_skill_providers.py and scripts/test-jev-skill-providers.py.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.lib.errors import SkillSourceError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.skills.sources.base import SkillSourceAdapter
from vidbyte.skills.sources.claude import ClaudeSkillSourceAdapter
from vidbyte.skills.sources.file import FileSkillSourceAdapter
from vidbyte.skills.sources.github import GitHubSkillSourceAdapter
from vidbyte.skills.sources.skills_sh import SkillsShSkillSourceAdapter


class SkillSourceResolver:
    """Dispatches one source through the SDK's finite adapter set."""

    def __init__(self, *, transport: HttpTransport | None = None, response_parser: HttpResponseParser | None = None, claude_api_key: str | None = None) -> None:
        # @intent keep-source-dispatch-closed-and-lazy
        # One fixed adapter exists per supported source kind and construction performs no requests, avoiding arbitrary callbacks and eager network effects.
        self._file_adapter: SkillSourceAdapter = FileSkillSourceAdapter()
        self._github_adapter: SkillSourceAdapter = GitHubSkillSourceAdapter(transport=transport, response_parser=response_parser)
        self._skills_sh_adapter: SkillSourceAdapter = SkillsShSkillSourceAdapter(transport=transport, response_parser=response_parser)
        self._claude_adapter: SkillSourceAdapter = ClaudeSkillSourceAdapter(transport, response_parser, default_api_key=claude_api_key)

    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Resolves one source by its explicit kind and keeps the adapter set closed.
        if not isinstance(source, SkillSource):
            raise SkillSourceError("Skill source must be a SkillSource descriptor.")
        if source.kind is SkillSourceKind.FILE:
            return await self._file_adapter.resolve(source)
        if source.kind is SkillSourceKind.GITHUB:
            return await self._github_adapter.resolve(source)
        if source.kind is SkillSourceKind.SKILLS_SH:
            return await self._skills_sh_adapter.resolve(source)
        if source.kind is SkillSourceKind.CLAUDE:
            return await self._claude_adapter.resolve(source)
        raise SkillSourceError("Skill source kind is not supported.")


__all__ = ["SkillSourceAdapter", "SkillSourceError", "SkillSourceResolver"]
