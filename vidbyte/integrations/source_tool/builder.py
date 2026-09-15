"""FILE: vidbyte/integrations/source_tool/builder.py

PURPOSE: Builds repository-scoped GitHub tools from one validated source mapping.
ROLE IN CODEBASE: Public SourceTool adapter between source configuration and provider tool implementations.
ARCHITECTURE NOTE: Build is synchronous and side-effect free; owner/repo scope closes over each tool instance.
COMMON MODIFICATION PATTERNS: Add a provider-specific tool to the provider tool package and compose it here in stable order.
KNOWN EDGE CASES: Pull-request resources are rejected, and output bounds must be positive integers.
RELATED DOCS: docs/design/source-context-tools.md and vidbyte/integrations/source_tool/README.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.integrations.providers import SourceProviderFactory
from vidbyte.lib.cli import CliRequest
from vidbyte.lib.constants.integrations import SOURCES_DEFAULT_MAX_OUTPUT_BYTES
from vidbyte.lib.dataclasses.integrations import GitHubClientConfig, SourceConfig
from vidbyte.lib.enums.integrations import SourceKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.base import BaseTool
from vidbyte.tools.integrations.github import (
    GitHubListFilesTool,
    GitHubReadFileTool,
    GitHubSearchCodeTool,
)


class SourceTool:
    """Builds repository-scoped tools from one external source mapping."""

    def __init__(self, source: Mapping[str, Any], *, max_output_bytes: int = SOURCES_DEFAULT_MAX_OUTPUT_BYTES) -> None:
        """Validate the public source mapping and output ceiling without I/O."""
        self._config = SourceConfig.from_mapping(source)
        self._max_output_bytes = self._coerce_bound(max_output_bytes)
        self._require_repository()
        self._client_config = GitHubClientConfig(api_key=self._config.api_key)

    @property
    def config(self) -> SourceConfig:
        """Return the validated source configuration."""
        return self._config

    @property
    def max_output_bytes(self) -> int:
        """Return the per-response UTF-8 byte ceiling."""
        return self._max_output_bytes

    def build(self) -> list[BaseTool]:
        """Construct list, read, and search tools in deterministic order."""
        client = SourceProviderFactory.create(self._config, client_config=self._client_config)
        return [
            GitHubListFilesTool(client, self._config, self._max_output_bytes),
            GitHubReadFileTool(client, self._config, self._max_output_bytes),
            GitHubSearchCodeTool(client, self._config, self._max_output_bytes),
        ]

    def _require_repository(self) -> None:
        """Reject pull-request resources before a tool list can be constructed."""
        if self._config.kind != SourceKind.REPOSITORY:
            raise ConfigurationError("SourceTool requires a repository resource, not a pull request.")

    @staticmethod
    def _coerce_bound(max_output_bytes: int) -> int:
        """Accept one positive integer byte bound and reject loose values."""
        try:
            CliRequest.validate_output_limit(max_output_bytes)
        except ValueError as exc:
            raise ConfigurationError("SourceTool 'max_output_bytes' must be a positive integer.") from exc
        return max_output_bytes


__all__ = ["SourceTool"]
