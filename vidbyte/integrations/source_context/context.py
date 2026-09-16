"""FILE: vidbyte/integrations/source_context/context.py

PURPOSE: Loads one validated pull-request resource into bounded context items.
ROLE IN CODEBASE: Public SourceContext pipeline between provider sections and Agent context.
ARCHITECTURE NOTE: Configuration is validated once; provider selection and budget admission stay behind class boundaries.
COMMON MODIFICATION PATTERNS: Add context conversion metadata here, and add provider retrieval behavior in its client.
KNOWN EDGE CASES: Zero budgets return no items, empty sections stay explicit, and fetch failures are raised.
RELATED DOCS: docs/design/source-context-tools.md and vidbyte/integrations/source_context/README.md
TESTS: tests/test_source_context_tools.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.integrations.providers import SourceProviderFactory
from vidbyte.lib.constants.integrations import SOURCES_DEFAULT_MAX_TOKENS
from vidbyte.lib.dataclasses.integrations import (
    GitHubClientConfig,
    LoadedSection,
    SourceConfig,
)
from vidbyte.lib.enums.integrations import SourceKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.integrations_budget import ContextAdmission


class SourceContext:
    """Loads one external pull request into bounded agent context items."""

    def __init__(self, source: Mapping[str, Any], *, max_tokens: int = SOURCES_DEFAULT_MAX_TOKENS) -> None:
        """Validate the source mapping and approximate token budget."""
        self._config = SourceConfig.from_mapping(source)
        self._max_tokens = self._coerce_budget(max_tokens)
        self._require_pull_request()
        self._client_config = GitHubClientConfig(api_key=self._config.api_key)

    @property
    def config(self) -> SourceConfig:
        """Return the validated source configuration."""
        return self._config

    @property
    def max_tokens(self) -> int:
        """Return the approximate token ceiling for one load."""
        return self._max_tokens

    async def load(self) -> list[DocumentContextItem]:
        """Fetch, normalize, and admit all pull-request sections."""
        # @intent external boundaries
        # The provider completes before admission so a failed section can never look like a complete load.
        sections = await SourceProviderFactory.create(self._config, client_config=self._client_config).load_context(self._config)
        items = tuple(self._to_item(section) for section in sections)
        return list(ContextAdmission(max_tokens=self._max_tokens).admit(items).items)

    def _to_item(self, section: LoadedSection) -> DocumentContextItem:
        """Convert one provider section into a provenance-carrying context item."""
        # @intent external boundaries
        # Provider and revision metadata travel with the text so downstream reasoning can attribute claims.
        return DocumentContextItem(
            source=section.source_url,
            content=section.body,
            title=section.title,
            document_id=self._document_id(),
            metadata={
                "provider": self._config.provider.value,
                "resource": self._config.resource,
                "revision": section.revision,
                "transport": section.transport,
                "truncated": False,
            },
        )

    def _document_id(self) -> str:
        """Derive a stable identifier from the validated pull-request scope."""
        return f"github-pr-{self._config.owner}-{self._config.repo}-{self._config.number}"

    # @intent provider-boundary
    def _require_pull_request(self) -> None:
        """Reject repository sources before any provider client is invoked."""
        if self._config.kind != SourceKind.PULL_REQUEST:
            raise ConfigurationError("SourceContext requires a pull-request resource.")

    @staticmethod
    def _coerce_budget(max_tokens: int) -> int:
        """Accept one nonnegative integer budget and reject loose values."""
        try:
            ContextAdmission.validate_budget(max_tokens)
        except ValueError as exc:
            raise ConfigurationError("SourceContext 'max_tokens' must be a nonnegative integer.") from exc
        return max_tokens


__all__ = ["SourceContext"]
