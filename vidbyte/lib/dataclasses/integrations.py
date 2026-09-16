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
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.cli import CliRequest, CliRunner
from vidbyte.lib.constants.integrations import (
    SOURCES_GITHUB_TOKEN_PREFIXES,
    SOURCES_HTTP_TIMEOUT_SECONDS,
    SOURCES_KNOWN_FIELDS,
    SOURCES_MAX_CONTROL_CODE,
)
from vidbyte.lib.enums.integrations import SourceKind, SourceProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http.transport import HttpTransport

_GITHUB_NAME = r"[A-Za-z0-9_.-]+"
_PR_URL_PATTERN = re.compile(rf"^https://github\.com/(?P<owner>{_GITHUB_NAME})/(?P<repo>{_GITHUB_NAME})/pull/(?P<number>[1-9]\d*)/?$")
_REPO_URL_PATTERN = re.compile(rf"^https://github\.com/(?P<owner>{_GITHUB_NAME})/(?P<repo>{_GITHUB_NAME})(?:\.git)?/?$")
_SHORTHAND_PATTERN = re.compile(rf"^(?P<owner>{_GITHUB_NAME})/(?P<repo>{_GITHUB_NAME})$")


@dataclass(frozen=True, slots=True)
class LoadedSection:
    """One fetched content section with its provenance attached."""

    title: str
    source_url: str
    body: str
    revision: str | None = None
    transport: str = "rest"


@dataclass(frozen=True, slots=True)
class GitHubClientConfig:
    """Strict runtime configuration for one GitHub client and its transports."""

    api_key: str
    transport: HttpTransport = field(default_factory=HttpTransport)
    runner: CliRunner = field(default_factory=CliRunner)
    timeout_seconds: float = SOURCES_HTTP_TIMEOUT_SECONDS

    # @intent external-boundary-validation
    def __post_init__(self) -> None:
        """Validate the credential shape, transport types, and timeout bounds."""
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ConfigurationError("GitHubClientConfig.api_key must be a nonempty string.")
        if not self.api_key.startswith(SOURCES_GITHUB_TOKEN_PREFIXES):
            raise ConfigurationError("GitHubClientConfig.api_key must use a recognized GitHub token prefix.")
        if not isinstance(self.transport, HttpTransport):
            raise ConfigurationError("GitHubClientConfig.transport must be an HttpTransport.")
        if not isinstance(self.runner, CliRunner):
            raise ConfigurationError("GitHubClientConfig.runner must be a CliRunner.")
        try:
            CliRequest.validate_timeout(self.timeout_seconds)
        except ValueError as exc:
            raise ConfigurationError("GitHubClientConfig.timeout_seconds is outside the approved range.") from exc


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
        # @intent external boundaries
        # Validation owns the whole public shape here so no downstream consumer re-checks provider scope.
        if not isinstance(self.provider, SourceProvider):
            raise ConfigurationError("SourceConfig.provider must be a SourceProvider.")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ConfigurationError("Source 'api_key' must be a nonempty string.")
        if not isinstance(self.resource, str) or not self.resource.strip():
            raise ConfigurationError("Source 'resource' must be a nonempty string.")
        if any(ord(char) <= SOURCES_MAX_CONTROL_CODE for char in self.resource):
            raise ConfigurationError("Source 'resource' must not contain control characters.")
        if not isinstance(self.kind, SourceKind):
            raise ConfigurationError("SourceConfig.kind must be a SourceKind.")
        if not re.fullmatch(_GITHUB_NAME, self.owner) or not re.fullmatch(_GITHUB_NAME, self.repo):
            raise ConfigurationError("SourceConfig must carry a resolved owner and repo.")
        if self.kind == SourceKind.PULL_REQUEST and self.number is None:
            raise ConfigurationError("A pull-request source must carry its pull number.")
        if self.kind == SourceKind.REPOSITORY and self.number is not None:
            raise ConfigurationError("A repository source must not carry a pull number.")

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> SourceConfig:
        """Coerce a public source dictionary into a validated SourceConfig."""
        # @intent external boundaries
        # Unknown fields fail here so a typo can never slip a forged option past validation.
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
        # @intent external boundaries
        # Only the closed enum vocabulary survives coercion; anything else names its accepted values.
        if isinstance(raw, SourceProvider):
            return raw
        if isinstance(raw, str) and raw.strip().lower() in SourceProvider.values():
            return SourceProvider(raw.strip().lower())
        raise ConfigurationError(f"Unknown source provider {raw!r}; expected one of {', '.join(SourceProvider.values())}.")

    @staticmethod
    def _parse_resource(resource: str) -> tuple[SourceKind, str, str, int | None]:
        """Split a resource address into its kind, owner, repo, and optional pull number."""
        # @intent external boundaries
        # Resource syntax decides kind and scope, and unrecognized shapes fail before any client exists.
        pr_match = _PR_URL_PATTERN.match(resource.strip())
        if pr_match is not None:
            return (SourceKind.PULL_REQUEST, pr_match.group("owner"), pr_match.group("repo"), int(pr_match.group("number")))
        repo_match = _REPO_URL_PATTERN.match(resource.strip()) or _SHORTHAND_PATTERN.match(resource.strip())
        if repo_match is not None:
            return (SourceKind.REPOSITORY, repo_match.group("owner"), repo_match.group("repo"), None)
        raise ConfigurationError(f"Unrecognized github resource {resource!r}; use a pull URL or owner/repo.")


__all__ = [
    "GitHubClientConfig",
    "LoadedSection",
    "SourceConfig",
]
