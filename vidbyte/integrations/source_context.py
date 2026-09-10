"""FILE: vidbyte/integrations/source_context.py

PURPOSE: Defines SourceContext, the public fetch-and-convert path from one external resource to agent context.
ROLE IN CODEBASE: Front door for loading a GitHub pull request into DocumentContextItem lists an Agent accepts directly.
ARCHITECTURE NOTE: __init__ only coerces the public dict into SourceConfig; load() owns fetch, convert, and budget steps.
COMMON MODIFICATION PATTERNS: Extend PR coverage by adding a section in the provider, never by branching here.
KNOWN EDGE CASES: Empty sections stay explicit, zero budgets admit nothing, and auth failures raise instead of empty lists.
RELATED DOCS: docs/design/source-context-tools.md
TESTS: tests/test_source_context_tools.py and scripts/test-source-context-tools.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.context.primitives.documents import DocumentContextItem
from vidbyte.integrations.budget import ContextAdmission
from vidbyte.integrations.providers import LoadedSection, create_client
from vidbyte.lib.constants.integrations import SOURCES_DEFAULT_MAX_TOKENS, SOURCES_MIN_TOKENS
from vidbyte.lib.dataclasses.integrations import SourceConfig
from vidbyte.lib.enums.integrations import SourceKind
from vidbyte.lib.errors import ConfigurationError


class SourceContext:
    """Loads one external resource into bounded agent context items."""

    def __init__(self, source: Mapping[str, Any], *, max_tokens: int = SOURCES_DEFAULT_MAX_TOKENS) -> None:
        """Coerce the public source dict and token budget into validated state."""
        self._config = SourceConfig.from_mapping(source)
        self._max_tokens = self._coerce_budget(max_tokens)

    @property
    def config(self) -> SourceConfig:
        """Return the validated source this object loads from."""
        return self._config

    @property
    def max_tokens(self) -> int:
        """Return the approximate token ceiling one load fits within."""
        return self._max_tokens

    async def load(self) -> list[DocumentContextItem]:
        """Fetch the resource, convert sections to items, and fit them to the budget."""
        self._require_pull_request()
        sections = await create_client(self._config).load_context(self._config)
        return self._fit_items(sections)

    def _require_pull_request(self) -> None:
        """Reject repository resources before any network use."""
        if self._config.kind != SourceKind.PULL_REQUEST:
            raise ConfigurationError("SourceContext requires a pull-request resource.")

    def _fit_items(self, sections: tuple[LoadedSection, ...]) -> list[DocumentContextItem]:
        """Convert raw sections into items admitted under the token ceiling."""
        items = tuple(self._to_item(section) for section in sections)
        return list(ContextAdmission(max_tokens=self._max_tokens).admit(items).items)

    def _to_item(self, section: LoadedSection) -> DocumentContextItem:
        """Convert one fetched section into a provenance-carrying context item."""
        return DocumentContextItem(source=section.source_url, content=section.body, title=section.title, document_id=self._document_id(), metadata={"provider": self._config.provider.value, "resource": self._config.resource, "revision": section.revision, "truncated": False})

    def _document_id(self) -> str | None:
        """Derive a stable external identifier for the bound resource."""
        if self._config.kind == SourceKind.PULL_REQUEST:
            return f"github-pr-{self._config.owner}-{self._config.repo}-{self._config.number}"
        return None

    @staticmethod
    def _coerce_budget(max_tokens: int) -> int:
        """Accept one nonnegative integer budget, rejecting loose or negative values."""
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < SOURCES_MIN_TOKENS:
            raise ConfigurationError("SourceContext 'max_tokens' must be a nonnegative integer.")
        return max_tokens


__all__ = [
    "SourceContext",
]
