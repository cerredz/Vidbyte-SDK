"""FILE: vidbyte/providers/tool_catalogs/glama.py

PURPOSE: Adapts Glama's MCP API connectors (remote MCP servers Glama has scanned and tested) into ToolCatalogEntry records.
ROLE IN CODEBASE: ToolCatalogs builds GlamaCatalog for ToolCatalogName.GLAMA when the owner supplies a Glama API key; JevAgentAlignment searches and describes through it.
ARCHITECTURE NOTE: Only connectors are used, because a connector carries a connectable Streamable HTTP URL and an auth type; Glama's server listings describe repositories without an install.
COMMON MODIFICATION PATTERNS: Map a new `authType` in _connector_install; keep OAuth and basic-auth connectors reported as unattachable until the SDK can run those flows.
KNOWN EDGE CASES: Every directory read needs `Authorization: Bearer <key>` (401 without one). An `api_key` connector declares no header name, so the owner's secret is sent as a bearer token under the connector's own name. Deprecated and unhealthy connectors are skipped.
RELATED DOCS: https://glama.ai/mcp/reference, https://glama.ai/api/mcp/openapi.json, and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar
from urllib.parse import quote

from vidbyte.lib.constants.tool_catalogs import GLAMA_API_BASE_URL
from vidbyte.lib.dataclasses.tool_catalogs import (
    CatalogTool,
    ToolCatalogEntry,
    ToolInstall,
    ToolSecretRequirement,
)
from vidbyte.lib.enums.tool_catalogs import (
    ToolCatalogName,
    ToolInstallKind,
    ToolSecretLocation,
)
from vidbyte.providers.tool_catalogs.base import (
    ToolCatalogProvider,
    items,
    mapping,
    optional_bool,
    text,
    tool_text,
)

GLAMA_SORT = "search-relevance:desc"
_AUTH_NONE = "none"
_AUTH_API_KEY = "api_key"
_STREAMABLE_HTTP = "streamable_http"


class GlamaCatalog(ToolCatalogProvider):
    """Glama's directory of scanned remote MCP connectors."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.GLAMA
    base_url: ClassVar[str] = GLAMA_API_BASE_URL

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Search connectors by free text, most relevant first."""
        payload = await self.get_json(f"{self.base_url}/v1/connectors", params={"query": query, "first": limit, "sort": GLAMA_SORT}, headers=self._auth_headers())
        entries = (self._entry(mapping(raw)) for raw in items(mapping(payload).get("connectors")))
        return tuple(entry for entry in entries if entry is not None)[:limit]

    async def describe(self, entry: ToolCatalogEntry) -> ToolCatalogEntry:
        """Read the connector detail, which adds its tools and their annotations."""
        payload = mapping(await self.get_json(f"{self.base_url}/v1/connectors/{quote(entry.entry_id, safe='/')}", headers=self._auth_headers()))
        detailed = self._entry(payload)
        if detailed is None:
            return entry
        tools = tuple(tool for tool in (_catalog_tool(raw) for raw in items(payload.get("tools"))) if tool is not None)
        return ToolCatalogEntry(
            catalog=self.name,
            entry_id=detailed.entry_id,
            name=detailed.name,
            description=detailed.description,
            installs=detailed.installs,
            tools=tools,
            publisher=detailed.publisher,
            verified=detailed.verified,
            repository_url=detailed.repository_url,
        )

    def _entry(self, connector: Mapping[str, object]) -> ToolCatalogEntry | None:
        # Builds one entry from a connector summary or detail, skipping deprecated and unhealthy connectors.
        namespace, slug = text(connector.get("namespace")), text(connector.get("slug"))
        if not namespace or not slug or text(connector.get("deprecatedAt")) or connector.get("healthy") is False:
            return None
        install = _connector_install(mapping(connector.get("connection")), f"{namespace}_{slug}")
        return ToolCatalogEntry(
            catalog=self.name,
            entry_id=f"{namespace}/{slug}",
            name=text(connector.get("name")) or slug,
            description=text(connector.get("description")),
            installs=(install,) if install is not None else (),
            publisher=namespace,
            # Glama lists only connectors it has connected to and scanned.
            verified=connector.get("healthy") is True,
            repository_url=text(mapping(connector.get("repository")).get("url")) or None,
        )

    def _auth_headers(self) -> Mapping[str, str]:
        # Glama reads require the owner's key; ToolCatalogs never builds this adapter without one.
        credentials = self.require_credentials("api_key")
        return {"Authorization": f"Bearer {credentials.api_key}"}


def _connector_install(connection: Mapping[str, object], secret_name: str) -> ToolInstall | None:
    # Converts a connection into a REMOTE_HTTP install; OAuth and basic auth cannot be attached yet.
    url = text(connection.get("url"))
    auth_type = text(connection.get("authType"))
    if text(connection.get("transport")) != _STREAMABLE_HTTP or not url or auth_type not in (_AUTH_NONE, _AUTH_API_KEY):
        return None
    if auth_type == _AUTH_NONE:
        return ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url=url)
    secret = ToolSecretRequirement(
        name=secret_name.upper().replace("-", "_"),
        location=ToolSecretLocation.HEADER,
        target="Authorization",
        template="Bearer {value}",
        description="API key for this connector.",
    )
    return ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url=url, secrets=(secret,))


def _catalog_tool(raw: object) -> CatalogTool | None:
    # Converts one connector tool, keeping its MCP annotations.
    tool = mapping(raw)
    name = text(tool.get("name"))
    if not name:
        return None
    annotations = mapping(tool.get("annotations"))
    return CatalogTool(
        name=name,
        description=tool_text(tool.get("description")),
        input_schema=mapping(tool.get("inputSchema")),
        read_only=optional_bool(annotations.get("readOnlyHint")),
        destructive=optional_bool(annotations.get("destructiveHint")),
    )


__all__ = ["GlamaCatalog"]
