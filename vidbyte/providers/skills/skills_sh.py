"""FILE: vidbyte/providers/skills/skills_sh.py

PURPOSE: Resolves explicit skills.sh owner/repository/skill-slug references through GitHub.
ROLE IN CODEBASE: Converts a skills.sh catalog selection to the shared GitHub skill-document adapter.
ARCHITECTURE NOTE: skills.sh is a reference format here; no skills.sh content endpoint or installer is used.
COMMON MODIFICATION PATTERNS: Normalize only explicit owner/repo/slug inputs, then delegate content lookup to GitHubSkillSourceAdapter.
KNOWN EDGE CASES: Missing or ambiguous slugs are unavailable; this adapter never installs or guesses a skill.
RELATED DOCS: docs/design/jev-skill-providers.md and docs/jev-skill-providers.md.
TESTS: tests/test_jev_skill_remote_sources.py and scripts/test-jev-skill-providers.py.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from vidbyte.lib.dataclasses.skills import SkillDocument, SkillSource
from vidbyte.lib.enums.skills import SkillSourceKind
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.parser import HttpResponseParser
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.providers.skills.base import (
    SkillDocumentParser,
    SkillSourceAdapter,
    SkillSourceError,
)
from vidbyte.providers.skills.github import GitHubSkillSourceAdapter

_SKILL_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SkillsShSkillSourceAdapter(SkillSourceAdapter):
    """Resolves a skills.sh source slug using the GitHub repository catalog."""

    def __init__(self, *, transport: HttpTransport | None = None, response_parser: HttpResponseParser | None = None, document_parser: SkillDocumentParser | None = None) -> None:
        # @intent reuse-github-catalog-for-skills-sh
        # Slugs resolve through the bounded GitHub catalog adapter; no installer or undocumented content endpoint is invoked.
        self.github_adapter = GitHubSkillSourceAdapter(transport=transport, response_parser=response_parser, document_parser=document_parser)

    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Resolves the selected owner/repository/slug without calling or installing through skills.sh.
        if not isinstance(source, SkillSource) or source.kind is not SkillSourceKind.SKILLS_SH:
            raise SkillSourceError("skills.sh adapter requires a SKILLS_SH SkillSource.")
        owner, repo, slug = self._parse_location(source)
        try:
            github_source = SkillSource(
                kind=SkillSourceKind.GITHUB,
                location=f"{owner}/{repo}",
                revision=source.revision,
                api_key=source.api_key,
                skill_name=source.skill_name,
            )
        except (TypeError, ValueError) as exc:
            raise SkillSourceError("skills.sh source could not be resolved.") from exc
        try:
            return await self.github_adapter._resolve_repository_path(github_source, slug)
        except ProviderRequestError:
            raise SkillSourceError("skills.sh source could not be resolved.") from None

    def _parse_location(self, source: SkillSource) -> tuple[str, str, str]:
        # Accepts only owner/repo/slug or its public skills.sh URL form.
        location = source.location
        if "://" not in location:
            parts = location.split("/")
        else:
            try:
                parsed = urlsplit(location)
                port = parsed.port
            except ValueError:
                raise SkillSourceError("skills.sh source URL is invalid.") from None
            if parsed.scheme != "https" or parsed.hostname != "skills.sh" or parsed.username is not None or parsed.password is not None or port not in (None, 443):
                raise SkillSourceError("skills.sh sources must use an approved HTTPS URL without user information.")
            if parsed.query or parsed.fragment:
                raise SkillSourceError("skills.sh source URLs cannot include query parameters or fragments.")
            parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 3:
            raise SkillSourceError("skills.sh source must identify owner, repository, and skill slug.")
        owner, repo, slug = parts
        if not _SKILL_SLUG.fullmatch(owner) or not _SKILL_SLUG.fullmatch(repo) or not _SKILL_SLUG.fullmatch(slug):
            raise SkillSourceError("skills.sh owner, repository, or skill slug is invalid.")
        return owner, repo.removesuffix(".git"), slug


__all__ = ["SkillsShSkillSourceAdapter"]
