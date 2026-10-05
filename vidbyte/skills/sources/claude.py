"""FILE: vidbyte/skills/sources/claude.py

PURPOSE: Resolves explicit Claude Skills identifiers into safe metadata and concrete native references.
ROLE IN CODEBASE: SkillSourceResolver uses this adapter during Jev preload; the Messages provider later mounts selected opaque references.
ARCHITECTURE NOTE: The Skills API exposes metadata, not the original SKILL.md body, so this adapter never turns descriptions into prompt text.
COMMON MODIFICATION PATTERNS: Keep list/retrieve request shapes and version pinning in this adapter; the resolver owns only closed dispatch.
KNOWN EDGE CASES: Pagination is bounded, credentials follow source/Anthropic-agent/environment precedence, and a missing concrete version fails resolution.
RELATED DOCS: docs/design/jev-skill-providers.md and docs/jev-skill-providers.md.
TESTS: tests/test_jev_skill_providers.py and scripts/test-jev-skill-providers.py.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import yaml

from vidbyte.lib.dataclasses.skills import (
    ClaudeSkillReference,
    SkillDocument,
    SkillSource,
)
from vidbyte.lib.enums.skills import ClaudeSkillType, SkillSourceKind
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    SkillSourceError,
)
from vidbyte.lib.errors.skills import provider_failure_reason
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.skills.sources.base import SkillSourceAdapter

_CLAUDE_API_ROOT = "https://api.anthropic.com/v1"
_CLAUDE_API_VERSION = "2023-06-01"
_MAX_RESPONSE_BYTES = 1_000_000
_MAX_SKILL_PAGES = 10
_PAGE_SIZE = 1000
_REQUEST_TIMEOUT_SECONDS = 20.0
_EXPECTED_UNIQUE_SKILL_MATCHES = 1


class ClaudeSkillSourceAdapter(SkillSourceAdapter):
    """Looks up one Claude Skill and pins the concrete version returned by its API."""

    def __init__(self, transport: HttpTransport | None = None, response_parser: HttpResponseParser | None = None, *, default_api_key: str | None = None) -> None:
        # @intent restrict-fallback-key-to-anthropic-owned-calls
        # The fallback key comes only from the owning Anthropic agent; explicit source keys take precedence and construction stays offline.
        self._transport = transport or HttpTransport()
        self._parser = response_parser or HttpResponseParser()
        self._default_api_key = default_api_key

    async def resolve(self, source: SkillSource) -> SkillDocument:
        # Resolves identity and version, with one boundary for safe source-specific diagnostics.
        try:
            if not isinstance(source, SkillSource) or source.kind is not SkillSourceKind.CLAUDE:
                raise SkillSourceError("Claude adapter requires a CLAUDE SkillSource.")
            headers = self._headers(source)
            skill = await self._find_skill(source, headers)
            skill_id = skill.get("id")
            latest_version_id = skill.get("latest_version_id")
            if not isinstance(skill_id, str) or not skill_id.strip() or not isinstance(latest_version_id, str) or not latest_version_id.strip():
                raise SkillSourceError("Claude skill metadata did not include a usable skill and version ID.")
            version_id = latest_version_id if source.version in (None, "latest") else source.version
            version_record = await self._get_json(
                f"{_CLAUDE_API_ROOT}/skills/{quote(skill_id, safe='')}/versions/{quote(version_id, safe='')}",
                headers,
            )
            return self._document(source, skill, version_record, skill_id)
        except SkillSourceError as exc:
            raise SkillSourceError(exc.reason, source_kind="claude", status_code=exc.status_code) from exc
        except ProviderRequestError as exc:
            raise SkillSourceError(provider_failure_reason(exc.status_code, message=exc.message), source_kind="claude", status_code=exc.status_code) from exc
        except TimeoutError as exc:
            raise SkillSourceError("the Anthropic metadata request timed out", source_kind="claude") from exc
        except OSError as exc:
            raise SkillSourceError("the Anthropic metadata service could not be reached", source_kind="claude") from exc
        except UnicodeError as exc:
            raise SkillSourceError("the metadata response contains invalid text encoding", source_kind="claude") from exc
        except yaml.YAMLError as exc:
            raise SkillSourceError("the metadata response could not be parsed", source_kind="claude") from exc
        except (ConfigurationError, ValueError, TypeError) as exc:
            raise SkillSourceError("the skill metadata or version did not satisfy the SDK contract", source_kind="claude") from exc

    def _headers(self, source: SkillSource) -> dict[str, str]:
        # Sends credentials only to api.anthropic.com and never reads credentials from source locations.
        api_key = source.api_key or self._default_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not isinstance(api_key, str) or not api_key.strip():
            raise SkillSourceError("Claude skill source requires an Anthropic API key.")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": _CLAUDE_API_VERSION,
            "accept": "application/json",
        }
        if source.workspace_id is not None:
            headers["anthropic-workspace-id"] = source.workspace_id
        return headers

    async def _find_skill(self, source: SkillSource, headers: Mapping[str, str]) -> Mapping[str, Any]:
        # Searches bounded paginated metadata and refuses absent or ambiguous display-name selectors.
        matches: list[Mapping[str, Any]] = []
        page_token: str | None = None
        visited: set[str] = set()
        for _ in range(_MAX_SKILL_PAGES):
            url = f"{_CLAUDE_API_ROOT}/skills?limit={_PAGE_SIZE}"
            if page_token is not None:
                url += f"&page={quote(page_token, safe='')}"
            page = await self._get_json(url, headers)
            data = page.get("data")
            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                raise SkillSourceError("Claude Skills API returned an invalid metadata page.")
            matches.extend(item for item in data if self._matches(source, item))
            if len(matches) > _EXPECTED_UNIQUE_SKILL_MATCHES:
                raise SkillSourceError("Claude skill selector is ambiguous.")
            next_page = page.get("next_page")
            if next_page is None:
                break
            if not isinstance(next_page, str) or not next_page or next_page in visited:
                raise SkillSourceError("Claude Skills API returned an invalid pagination token.")
            visited.add(next_page)
            page_token = next_page
        else:
            raise SkillSourceError("Claude Skills API exceeded its pagination limit.")
        if len(matches) != _EXPECTED_UNIQUE_SKILL_MATCHES:
            raise SkillSourceError("Claude skill selector did not identify one skill.")
        return matches[0]

    def _matches(self, source: SkillSource, item: Mapping[str, Any]) -> bool:
        # Matches a stable skill ID or exact display label without guessing from URL-like input.
        identifier = item.get("id")
        display_name = item.get("display_name")
        return identifier == source.location or display_name == source.location

    async def _get_json(self, url: str, headers: Mapping[str, str]) -> dict[str, Any]:
        # @intent bound-and-redact-claude-metadata-requests
        # Fixed-host bounded requests replace upstream error details so credentials and provider response bodies never escape resolution.
        response = await self._transport.request(
            method="GET",
            url=url,
            headers=headers,
            timeout_seconds=_REQUEST_TIMEOUT_SECONDS,
            max_response_bytes=_MAX_RESPONSE_BYTES,
        )
        return self._parser.parse_json_response(response, provider="anthropic")

    def _document(self, source: SkillSource, skill: Mapping[str, Any], version: Mapping[str, Any], skill_id: str) -> SkillDocument:
        # Builds metadata-only output and pins the exact version ID returned by Claude.
        skill_source = skill.get("source")
        source_kind = skill_source.get("type") if isinstance(skill_source, Mapping) else None
        native_type = ClaudeSkillType(source_kind)
        resolved_id = version.get("id")
        resolved_skill_id = version.get("skill_id")
        name = version.get("name")
        description = version.get("description")
        if (
            not isinstance(resolved_id, str)
            or not resolved_id.strip()
            or resolved_skill_id != skill_id
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(description, str)
            or not description.strip()
        ):
            raise SkillSourceError("Claude skill version metadata did not include usable identity fields.")
        if source.skill_name is not None and source.skill_name != name:
            raise SkillSourceError("Claude skill name did not match the requested name.")
        reference = ClaudeSkillReference(skill_id=skill_id, version=resolved_id, type=native_type)
        return SkillDocument(
            name=name,
            description=description,
            text=None,
            source=f"claude:{skill_id}@{resolved_id}",
            claude_reference=reference,
        )


__all__ = ["ClaudeSkillSourceAdapter"]
