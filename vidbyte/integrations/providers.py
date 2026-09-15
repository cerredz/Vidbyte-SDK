"""FILE: vidbyte/integrations/providers.py

PURPOSE: Resolves a validated source configuration to its concrete provider client.
ROLE IN CODEBASE: Keeps provider selection in one explicit class-bound switch.
ARCHITECTURE NOTE: There is no shared provider protocol because future providers may expose different context shapes.
COMMON MODIFICATION PATTERNS: Add one enum member, client config, and match branch together when a provider is real.
KNOWN EDGE CASES: Unknown providers fail before a client or network boundary is created.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.integrations import GitHubClientConfig, SourceConfig
from vidbyte.lib.enums.integrations import SourceProvider
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.integrations.github import GitHubClient


class SourceProviderFactory:
    """Constructs the concrete client for one validated provider selection."""

    @staticmethod
    def create(config: SourceConfig, *, client_config: GitHubClientConfig | None = None) -> GitHubClient:
        """Select a provider with an explicit switch and return its configured client."""
        # @intent external boundaries
        # Provider selection is closed over validated enum values, so raw caller strings cannot import arbitrary code.
        match config.provider:
            case SourceProvider.GITHUB:
                from vidbyte.integrations.github import GitHubClient

                return GitHubClient(client_config or GitHubClientConfig(api_key=config.api_key))
            case _:
                raise ConfigurationError(f"Unknown source provider {config.provider.value!r}.")


__all__ = ["SourceProviderFactory"]
