"""FILE: vidbyte/providers/tool_catalogs/__init__.py

PURPOSE: Exposes the public tool-catalog adapters and ToolCatalogs, the factory that builds them by name and fans one query out across several catalogs.
ROLE IN CODEBASE: JevAgentAlignment builds its catalog providers with ToolCatalogs.build() from JevToolAlignmentSettings and searches them with ToolCatalogs.search_all(); SearchMcpServersTool uses SmitheryCatalog directly.
ARCHITECTURE NOTE: search_all() gives every catalog its own timeout and error slot, interleaves results round-robin so each catalog's best entry comes first, and removes duplicates that several catalogs mirror (same remote URL, image, or package).
COMMON MODIFICATION PATTERNS: Register a new adapter in _ADAPTERS next to its ToolCatalogName member; keep ranking inside each adapter and only interleaving here.
KNOWN EDGE CASES: A catalog that fails or times out is reported in ToolCatalogSearch.errors while the other catalogs' entries are still returned. Cancellation of the caller is never swallowed.
RELATED DOCS: docs/design/jev-tool-alignment.md and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

from vidbyte.lib.dataclasses.tool_catalogs import (
    ToolCatalogCredentials,
    ToolCatalogEntry,
    ToolCatalogSearch,
)
from vidbyte.lib.enums.tool_catalogs import ToolCatalogName, ToolInstallKind
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.providers.tool_catalogs.apis_guru import ApisGuruCatalog
from vidbyte.providers.tool_catalogs.arcade import ArcadeCatalog
from vidbyte.providers.tool_catalogs.base import (
    IndexedToolCatalogProvider,
    ToolCatalogProvider,
)
from vidbyte.providers.tool_catalogs.composio import ComposioCatalog
from vidbyte.providers.tool_catalogs.docker import DockerMcpCatalog
from vidbyte.providers.tool_catalogs.glama import GlamaCatalog
from vidbyte.providers.tool_catalogs.mcp_registry import (
    GitHubMcpRegistryCatalog,
    McpRegistryCatalog,
)
from vidbyte.providers.tool_catalogs.pipedream import PipedreamCatalog
from vidbyte.providers.tool_catalogs.smithery import SmitheryCatalog
from vidbyte.providers.tool_catalogs.toolsdk import ToolSdkCatalog

_ADAPTERS: Mapping[ToolCatalogName, type[ToolCatalogProvider]] = {
    ToolCatalogName.MCP_REGISTRY: McpRegistryCatalog,
    ToolCatalogName.GITHUB_MCP_REGISTRY: GitHubMcpRegistryCatalog,
    ToolCatalogName.SMITHERY: SmitheryCatalog,
    ToolCatalogName.GLAMA: GlamaCatalog,
    ToolCatalogName.DOCKER_MCP_CATALOG: DockerMcpCatalog,
    ToolCatalogName.TOOLSDK: ToolSdkCatalog,
    ToolCatalogName.COMPOSIO: ComposioCatalog,
    ToolCatalogName.PIPEDREAM: PipedreamCatalog,
    ToolCatalogName.ARCADE: ArcadeCatalog,
    ToolCatalogName.APIS_GURU: ApisGuruCatalog,
}


class ToolCatalogs:
    """Factory and fan-out search over the public tool-catalog adapters."""

    @staticmethod
    def build(name: ToolCatalogName | str, *, credentials: ToolCatalogCredentials | None = None, transport: HttpTransport | None = None) -> ToolCatalogProvider:
        """Return the adapter for one catalog, refusing unknown names."""
        try:
            catalog = ToolCatalogName(name)
        except ValueError as exc:
            raise ConfigurationError(f"Unknown tool catalog {name!r}; use one of {sorted(item.value for item in ToolCatalogName)}.") from exc
        return _ADAPTERS[catalog](credentials=credentials, transport=transport)

    @staticmethod
    async def search_all(providers: Sequence[ToolCatalogProvider], query: str, *, limit_per_catalog: int, merged_limit: int, timeout_seconds: float) -> ToolCatalogSearch:
        """Search every provider concurrently and return the interleaved, de-duplicated entries plus each failure."""
        # Each catalog gets its own deadline and error slot, so one slow or broken catalog never empties the result.
        outcomes = await asyncio.gather(*(ToolCatalogs._search_one(provider, query, limit_per_catalog, timeout_seconds) for provider in providers))
        errors = {provider.name: error for provider, (_, error) in zip(providers, outcomes, strict=True) if error is not None}
        return ToolCatalogSearch(entries=_interleave_unique([entries for entries, _ in outcomes], merged_limit), errors=errors)

    @staticmethod
    async def _search_one(provider: ToolCatalogProvider, query: str, limit: int, timeout_seconds: float) -> tuple[tuple[ToolCatalogEntry, ...], str | None]:
        # Returns (entries, None) on success or ((), safe error text) on a catalog failure or timeout.
        # @intent one-catalog-failure-is-that-catalogs-error
        # A catalog outage, bad credential, or malformed body must not stop the other catalogs from answering,
        # and the recorded text is the SDK error's own message, never a raw exception string.
        try:
            async with asyncio.timeout(timeout_seconds):
                return await provider.search(query, limit=limit), None
        except TimeoutError:
            return (), f"The {provider.name.value} catalog did not answer within {timeout_seconds:g} seconds."
        except VidbyteSdkError as exc:
            return (), exc.message
        except Exception as exc:
            # Any adapter defect is recorded as that catalog's failure, not the search's.
            return (), f"The {provider.name.value} catalog failed unexpectedly ({type(exc).__name__})."


def _interleave_unique(results: Sequence[Sequence[ToolCatalogEntry]], limit: int) -> tuple[ToolCatalogEntry, ...]:
    # Takes the first entry from each catalog, then the second, and so on, skipping entries already seen elsewhere.
    merged: list[ToolCatalogEntry] = []
    seen: set[str] = set()
    depth = max((len(entries) for entries in results), default=0)
    for index in range(depth):
        for entries in results:
            if index >= len(entries) or len(merged) >= limit:
                continue
            keys = _dedupe_keys(entries[index])
            if keys & seen:
                continue
            seen.update(keys)
            merged.append(entries[index])
    return tuple(merged)


def _dedupe_keys(entry: ToolCatalogEntry) -> set[str]:
    # Identifies the same server across catalogs by where it runs, not by its catalog-specific id.
    keys = {entry.key}
    for install in entry.installs:
        if install.kind is ToolInstallKind.REMOTE_HTTP and install.url:
            keys.add(f"url:{install.url.lower().rstrip('/')}")
        elif install.command:
            keys.add(f"command:{install.command[-1].split('@sha256:', 1)[0].lower()}")
    # Repository URLs are deliberately not keys: one monorepo (such as awslabs/mcp) publishes many distinct servers.
    return keys


__all__ = [
    "ApisGuruCatalog",
    "ArcadeCatalog",
    "ComposioCatalog",
    "DockerMcpCatalog",
    "GitHubMcpRegistryCatalog",
    "GlamaCatalog",
    "IndexedToolCatalogProvider",
    "McpRegistryCatalog",
    "PipedreamCatalog",
    "SmitheryCatalog",
    "ToolCatalogProvider",
    "ToolCatalogs",
    "ToolSdkCatalog",
]
