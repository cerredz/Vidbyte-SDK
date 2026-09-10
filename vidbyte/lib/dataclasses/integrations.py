"""FILE: vidbyte/lib/dataclasses/integrations.py

PURPOSE: Defines the single validated configuration for one external source selection.
ROLE IN CODEBASE: SourceContext and SourceTool coerce their public dictionary into SourceConfig and store nothing else.
ARCHITECTURE NOTE: Every validation rule lives in __post_init__ so a constructed instance is provably valid downstream.
COMMON MODIFICATION PATTERNS: Add a provider by widening the resource grammar here and the factory in providers.py together.
KNOWN EDGE CASES: Resource keeps original case, api_key is never echoed, and PR versus repository kind derives from syntax alone.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.constants.integrations import SOURCES_KNOWN_FIELDS
from vidbyte.lib.enums.integrations import SourceKind, SourceProvider
from vidbyte.lib.errors import ConfigurationError

_PR_URL_PATTERN = re.compile(r"^https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)/?$")
_REPO_URL_PATTERN = re.compile(r"^https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$")
_SHORTHAND_PATTERN = re.compile(r"^(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)$")
_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/-]{1,64}$")


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Validated address and credential for one external source selection."""

    provider: SourceProvider
    api_key: str
    resource: str
    kind: SourceKind
    owner: str
    repo: str
    number: int | None = None

    def __post_init__(self) -> None:
        """Enforce every invariant a constructed config guarantees downstream."""
        if not isinstance(self.provider, SourceProvider):
            raise ConfigurationError("SourceConfig.provider must be a SourceProvider.")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ConfigurationError("Source 'api_key' must be a nonempty string.")
        if not isinstance(self.resource, str) or not self.resource.strip():
            raise ConfigurationError("Source 'resource' must be a nonempty string.")
        if any(ord(char) < 32 for char in self.resource):
            raise ConfigurationError("Source 'resource' must not contain control characters.")
        if not isinstance(self.kind, SourceKind):
            raise ConfigurationError("SourceConfig.kind must be a SourceKind.")
        if not self.owner or not self.repo:
            raise ConfigurationError("SourceConfig must carry a resolved owner and repo.")
        if self.kind == SourceKind.PULL_REQUEST and self.number is None:
            raise ConfigurationError("A pull-request source must carry its pull number.")
        if self.kind == SourceKind.REPOSITORY and self.number is not None:
            raise ConfigurationError("A repository source must not carry a pull number.")

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "SourceConfig":
        """Coerce a public source dictionary into a validated SourceConfig."""
        if not isinstance(source, Mapping):
            raise ConfigurationError("A source must be a mapping with provider, api_key, and resource.")
        unknown = sorted(set(source) - SOURCES_KNOWN_FIELDS)
        if unknown:
            raise ConfigurationError(f"Unknown source field(s): {', '.join(unknown)}.")
        provider = cls._coerce_provider(source.get("provider"))
        api_key = source.get("api_key")
        resource = source.get("resource")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ConfigurationError("Source 'api_key' must be a nonempty string.")
        if not isinstance(resource, str) or not resource.strip():
            raise ConfigurationError("Source 'resource' must be a nonempty string.")
        kind, owner, repo, number = cls._parse_resource(resource)
        return cls(provider=provider, api_key=api_key, resource=resource, kind=kind, owner=owner, repo=repo, number=number)

    @staticmethod
    def _coerce_provider(raw: Any) -> SourceProvider:
        """Convert a public provider string into its internal enum member."""
        if isinstance(raw, SourceProvider):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in SourceProvider.values():
            return SourceProvider(raw.strip().lower())
        raise ConfigurationError(f"Unknown source provider {raw!r}; expected one of {', '.join(SourceProvider.values())}.")

    @staticmethod
    def _parse_resource(resource: str) -> tuple[SourceKind, str, str, int | None]:
        """Split a resource address into its kind, owner, repo, and optional pull number."""
        pr_match = _PR_URL_PATTERN.match(resource.strip())
        if pr_match is not None:
            return (SourceKind.PULL_REQUEST, pr_match.group("owner"), pr_match.group("repo"), int(pr_match.group("number")))
        repo_match = _REPO_URL_PATTERN.match(resource.strip()) or _SHORTHAND_PATTERN.match(resource.strip())
        if repo_match is not None:
            return (SourceKind.REPOSITORY, repo_match.group("owner"), repo_match.group("repo"), None)
        raise ConfigurationError(f"Unrecognized github resource {resource!r}; use a pull URL or owner/repo.")


def validate_ref(raw: Any) -> str:
    """Accept one branch or commit ref the model may supply, rejecting scope-widening values."""
    if not isinstance(raw, str) or not _REF_PATTERN.match(raw):
        raise ConfigurationError("Tool 'ref' must be 1-64 chars of letters, digits, dot, underscore, slash, or hyphen.")
    return raw


__all__ = [
    "SourceConfig",
    "validate_ref",
]
