"""Context Protocol Header

Description:
    Smithery registry search client and tool for discovering MCP servers globally.
Purpose:
    Allows agents to query the Smithery MCP registry by keyword and receive
    structured server metadata, including the remote Streamable HTTP url that
    attach_mcp_server can connect to without running anything locally.
Architecture:
    - SmitheryServerResult: One search hit with its remote url and required config keys.
    - SmitheryRegistryClient: Async client over vidbyte.providers.tool_catalogs.SmitheryCatalog
      that searches, then reads each hit's detail for its http connection.
    - SearchMcpServersTool: BaseTool wrapper that formats results for the model.
Relations:
    Used by agents that include SearchMcpServersTool in their tool list.
    Pairs with AttachMcpServerTool in vidbyte.tools.builtins.mcp.attach_tool.
    The earlier version derived `npx -y <qualifiedName>` from each hit; Smithery names such
    as "github" are not npm packages, so that command ran unrelated packages. Results now
    carry the url Smithery publishes and no command.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from vidbyte.lib.dataclasses.tool_catalogs import ToolCatalogEntry
from vidbyte.lib.enums.tool_catalogs import ToolInstallKind
from vidbyte.lib.errors import VidbyteSdkError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.providers.tool_catalogs import SmitheryCatalog
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

_MIN_LIMIT = 1
_MAX_LIMIT = 25
_DEFAULT_LIMIT = 10


@dataclass(frozen=True, slots=True)
class SmitheryServerResult:
    """One Smithery search hit, with the remote endpoint to attach when Smithery publishes one."""

    name: str
    description: str
    qualified_name: str
    url: str | None = None
    verified: bool = False
    required_config: tuple[str, ...] = ()


class SmitheryRegistryClient:
    """Async client for the Smithery registry that returns attachable search results."""

    def __init__(self, catalog: SmitheryCatalog | None = None, *, transport: HttpTransport | None = None) -> None:
        """Store the Smithery catalog adapter, building one on the given transport when none is passed."""
        # @intent smithery-reads-go-through-the-catalog-adapter
        # All Smithery HTTP goes through SmitheryCatalog, which bounds, times out, and types every response.
        self._catalog = catalog or SmitheryCatalog(transport=transport)

    async def search(self, query: str, *, limit: int = _DEFAULT_LIMIT) -> list[SmitheryServerResult]:
        """Search Smithery, then read every hit's detail concurrently for its remote url and required config."""
        clamped_limit = max(_MIN_LIMIT, min(limit, _MAX_LIMIT))
        entries = await self._catalog.search(query, limit=clamped_limit)
        details = await asyncio.gather(*(self._describe(entry) for entry in entries))
        return [_result(entry) for entry in details]

    async def _describe(self, entry: ToolCatalogEntry) -> ToolCatalogEntry:
        # A failed detail read keeps the summary, so one broken listing never hides the others.
        try:
            return await self._catalog.describe(entry)
        except VidbyteSdkError:
            return entry


def _result(entry: ToolCatalogEntry) -> SmitheryServerResult:
    # Picks the first remote install, if any, and lists the config keys it requires.
    # @intent results-name-config-keys-not-values
    # Only the names of required config keys are shown; the tool never holds or prints their values.
    remote = next((install for install in entry.installs if install.kind is ToolInstallKind.REMOTE_HTTP), None)
    return SmitheryServerResult(
        name=entry.name,
        description=entry.description,
        qualified_name=entry.entry_id,
        url=remote.url if remote is not None else None,
        verified=entry.verified,
        required_config=tuple(secret.name for secret in remote.required_secrets) if remote is not None else (),
    )


class SearchMcpServersTool(BaseTool):
    """Searches the global Smithery MCP registry and returns structured server metadata."""

    def __init__(self, *, client: SmitheryRegistryClient | None = None) -> None:
        """Store the registry client, creating a default one if not provided."""
        self._client = client or SmitheryRegistryClient()

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for the search_mcp_servers tool."""
        return ToolSpec(
            name="search_mcp_servers",
            description=(
                "Search the global Smithery MCP server registry for servers matching a keyword query. "
                "Returns a JSON array of matching servers, each with a 'name', 'description', 'qualified_name', 'verified', 'url', and 'required_config' field. "
                "When 'url' is present, pass it to attach_mcp_server to connect to the remote server without running anything locally. "
                "Servers listing 'required_config' keys or needing a login may refuse the connection until those are configured."
            ),
            parameters=(
                ToolParameter(
                    name="query",
                    type="string",
                    description=(
                        "Keywords to search for in the Smithery registry, such as 'filesystem', 'github', or 'database'. "
                        "Short product or capability names match best. "
                        "The search is semantic, so a phrase describing the job also works. "
                        "An empty query is refused before any request is sent."
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description=(
                        "Maximum number of results to return. "
                        "Defaults to 10 and is clamped to at most 25. "
                        "Each result costs one extra detail request to find its url. "
                        "Ask for fewer results when you only need the best match."
                    ),
                    required=False,
                    default=_DEFAULT_LIMIT,
                ),
            ),
            permission=ToolPermission.SAFE,
            metadata={"source": "smithery"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the Smithery search and return formatted JSON results."""
        query = str(call.arguments.get("query", "")).strip()
        if not query:
            return ToolResult.error(self.name, "query parameter cannot be empty.", metadata={"source": "smithery"})
        raw_limit = call.arguments.get("limit", _DEFAULT_LIMIT)
        try:
            limit = max(_MIN_LIMIT, min(int(raw_limit), _MAX_LIMIT))
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT
        try:
            results = await self._client.search(query, limit=limit)
        except VidbyteSdkError as exc:
            # The SDK error's own message is safe to show; raw transport text is never echoed.
            return ToolResult.error(self.name, f"Smithery search failed: {exc.message}", metadata={"source": "smithery"})
        return ToolResult.success(self.name, self._format_results(results), metadata={"source": "smithery", "result_count": len(results)})

    def _format_results(self, results: list[SmitheryServerResult]) -> str:
        """Serialize results to a JSON string the model can parse and act on."""
        return json.dumps(
            [
                {
                    "name": result.name,
                    "description": result.description,
                    "qualified_name": result.qualified_name,
                    "verified": result.verified,
                    "url": result.url,
                    "required_config": list(result.required_config),
                }
                for result in results
            ],
            indent=2,
        )


__all__ = [
    "SearchMcpServersTool",
    "SmitheryRegistryClient",
    "SmitheryServerResult",
]
