"""FILE: vidbyte/providers/tool_catalogs/smithery.py

PURPOSE: Adapts the Smithery registry (registry.smithery.ai) into ToolCatalogEntry records: search summaries first, then per-server detail with tools and HTTP connections.
ROLE IN CODEBASE: ToolCatalogs builds SmitheryCatalog for ToolCatalogName.SMITHERY; SearchMcpServersTool and JevAgentAlignment both search and describe through it.
ARCHITECTURE NOTE: Search returns summaries without installs; describe() reads `GET /servers/{qualifiedName}` and turns each `http` connection's deploymentUrl plus its configSchema `x-from` locations into a REMOTE_HTTP install.
COMMON MODIFICATION PATTERNS: Map a new `x-from` location in _config_requirement; keep stdio connections unsupported, since Smithery runs those through its own CLI.
KNOWN EDGE CASES: The Smithery API key is sent only to registry.smithery.ai, never to a server's deploymentUrl, which may belong to a third party. Deployments that need OAuth fail at connect time and are reported, not retried. A server that names no deploymentUrl has no install.
RELATED DOCS: https://smithery.ai/docs/concepts/registry_search_servers, https://smithery.ai/docs/use/connect, and vidbyte/providers/tool_catalogs/README.md.
TESTS: tests/test_tool_catalogs.py and tests/test_mcp_discovery_tools.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar
from urllib.parse import quote

from vidbyte.lib.constants.tool_catalogs import SMITHERY_REGISTRY_BASE_URL
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

_HTTP_CONNECTION = "http"


class SmitheryCatalog(ToolCatalogProvider):
    """Smithery's registry of hosted and community MCP servers."""

    name: ClassVar[ToolCatalogName] = ToolCatalogName.SMITHERY
    base_url: ClassVar[str] = SMITHERY_REGISTRY_BASE_URL

    async def search(self, query: str, *, limit: int) -> tuple[ToolCatalogEntry, ...]:
        """Run Smithery's semantic search and return summaries; describe() adds tools and installs."""
        payload = await self.get_json(f"{self.base_url}/servers", params={"q": query, "pageSize": limit}, headers=self._auth_headers())
        entries: list[ToolCatalogEntry] = []
        for raw in items(mapping(payload).get("servers")):
            server = mapping(raw)
            qualified_name = text(server.get("qualifiedName"))
            if not qualified_name:
                continue
            entries.append(
                ToolCatalogEntry(
                    catalog=self.name,
                    entry_id=qualified_name,
                    name=text(server.get("displayName")) or qualified_name,
                    description=text(server.get("description")),
                    publisher=text(server.get("namespace")) or None,
                    verified=server.get("verified") is True,
                    repository_url=text(server.get("homepage")) or None,
                )
            )
        return tuple(entries[:limit])

    async def describe(self, entry: ToolCatalogEntry) -> ToolCatalogEntry:
        """Read the server detail and return the entry with its tools and HTTP installs."""
        payload = mapping(await self.get_json(f"{self.base_url}/servers/{quote(entry.entry_id, safe='@/')}", headers=self._auth_headers()))
        installs = tuple(install for install in (_connection_install(connection) for connection in items(payload.get("connections"))) if install is not None)
        tools = tuple(tool for tool in (_catalog_tool(raw) for raw in items(payload.get("tools"))) if tool is not None)
        return ToolCatalogEntry(
            catalog=self.name,
            entry_id=entry.entry_id,
            name=text(payload.get("displayName")) or entry.name,
            description=text(payload.get("description")) or entry.description,
            installs=installs,
            tools=tools,
            version=entry.version,
            publisher=entry.publisher,
            verified=entry.verified,
            repository_url=entry.repository_url,
        )

    def _auth_headers(self) -> Mapping[str, str]:
        # Sends the Smithery key to the registry only; it is optional for reads today.
        # @intent smithery-key-stays-with-smithery
        # A deploymentUrl can be a third-party host, so the key is added here and never to an install's headers.
        api_key = self.credentials.api_key
        return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _connection_install(raw: object) -> ToolInstall | None:
    # Converts one `http` connection into a REMOTE_HTTP install with its config requirements.
    connection = mapping(raw)
    url = text(connection.get("deploymentUrl"))
    if text(connection.get("type")) != _HTTP_CONNECTION or not url:
        return None
    schema = mapping(connection.get("configSchema"))
    required = {text(name) for name in items(schema.get("required"))}
    secrets = tuple(
        requirement
        for requirement in (_config_requirement(text(key), mapping(value), text(key) in required) for key, value in mapping(schema.get("properties")).items())
        if requirement is not None
    )
    return ToolInstall(kind=ToolInstallKind.REMOTE_HTTP, url=url, secrets=secrets)


def _config_requirement(name: str, prop: Mapping[str, object], required: bool) -> ToolSecretRequirement | None:
    # Reads `x-from` ({"query": key} or {"header": name}); a property with no location is sent as a query parameter.
    if not name:
        return None
    source = mapping(prop.get("x-from"))
    header = text(source.get("header"))
    if header:
        return ToolSecretRequirement(name=name, location=ToolSecretLocation.HEADER, target=header, required=required, description=text(prop.get("description")))
    return ToolSecretRequirement(name=name, location=ToolSecretLocation.QUERY, target=text(source.get("query")) or name, required=required, description=text(prop.get("description")))


def _catalog_tool(raw: object) -> CatalogTool | None:
    # Converts one detail tool, keeping the MCP annotations Smithery passes through.
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


__all__ = ["SmitheryCatalog"]
