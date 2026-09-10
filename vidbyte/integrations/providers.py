"""FILE: vidbyte/integrations/providers.py

PURPOSE: Defines the provider seam between validated source configs and concrete external APIs.
ROLE IN CODEBASE: SourceContext and SourceTool resolve their client here so adding a provider never touches either class.
ARCHITECTURE NOTE: A small built-in factory replaces a public registry until a second provider proves one earns its keep.
COMMON MODIFICATION PATTERNS: Add a client module plus one factory branch and one SourceProvider member together.
KNOWN EDGE CASES: Unknown provider names fail at construction with the accepted list, never with an import error.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vidbyte.lib.dataclasses.integrations import SourceConfig
from vidbyte.lib.enums.integrations import SourceProvider
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class LoadedSection:
    """One fetched content section with its provenance attached."""

    title: str
    source_url: str
    body: str
    revision: str | None = None


class SourceProviderClient(Protocol):
    """Contract every external source provider implements."""

    async def load_context(self, config: SourceConfig) -> tuple[LoadedSection, ...]:
        """Fetch every section one resource contributes to agent context."""
        ...

    async def read_repo_file(self, config: SourceConfig, path: str, ref: str | None, *, max_bytes: int) -> str:
        """Return one repo-relative file's decoded text bounded by max_bytes."""
        ...

    async def list_repo_files(self, config: SourceConfig, path: str, ref: str | None, *, max_entries: int) -> str:
        """Return a newline listing of one repo-relative directory bounded by max_entries."""
        ...

    async def search_repo_code(self, config: SourceConfig, query: str, ref: str | None, *, max_items: int) -> str:
        """Return code matches for a query confined to the bound repository."""
        ...


def create_client(config: SourceConfig) -> SourceProviderClient:
    """Resolve the built-in provider client for one validated config."""
    if config.provider == SourceProvider.GITHUB:
        from vidbyte.integrations.github import GitHubClient

        return GitHubClient(api_key=config.api_key)
    raise ConfigurationError(f"Unknown source provider {config.provider.value!r}.")


__all__ = [
    "LoadedSection",
    "SourceProviderClient",
    "create_client",
]
