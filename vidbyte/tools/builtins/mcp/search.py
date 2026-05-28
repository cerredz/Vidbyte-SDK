"""Context Protocol Header

Description:
    Smithery registry client and search tool for discovering MCP servers globally.
Purpose:
    Allows agents to query the Smithery MCP registry by keyword and receive
    structured server metadata including ready-to-use subprocess commands.
Architecture:
    - SmitheryServerResult: Parsed record from one Smithery API entry.
    - SmitheryRegistryClient: Synchronous HTTP client for registry.smithery.ai.
    - SearchMcpServersTool: BaseTool wrapper that offloads HTTP to a thread pool.
Relations:
    Used by agents that include SearchMcpServersTool in their tool list.
    Pairs with AttachMcpServerTool in vidbyte.tools.builtins.mcp.attach_tool.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

_MAX_LIMIT = 25
_DEFAULT_LIMIT = 10
_DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True, slots=True)
class SmitheryServerResult:
    """Parsed record representing one MCP server entry from the Smithery registry."""

    name: str
    description: str
    command: list[str]
    qualified_name: str


class SmitheryRegistryClient:
    """Synchronous HTTP client for the Smithery MCP server registry."""

    REGISTRY_URL = "https://registry.smithery.ai/servers"

    def __init__(self, transport: HttpTransport | None = None, *, timeout: float = _DEFAULT_TIMEOUT) -> None:
        """Store the HTTP transport and request timeout."""
        self._transport = transport or HttpTransport()
        self._timeout = timeout

    def search(self, query: str, *, limit: int = _DEFAULT_LIMIT) -> list[SmitheryServerResult]:
        """Query Smithery for MCP servers matching query and return parsed results."""
        clamped_limit = max(1, min(limit, _MAX_LIMIT))
        url = self._build_url(query, clamped_limit)
        data = self._send_request(url)
        return self._parse_servers(data)

    def _build_url(self, query: str, limit: int) -> str:
        """Construct the Smithery search URL with encoded query parameters."""
        params = urlencode({"q": query, "pageSize": limit})
        return f"{self.REGISTRY_URL}?{params}"

    def _send_request(self, url: str) -> dict[str, Any]:
        """Send GET request to Smithery and return the parsed JSON body."""
        response = self._transport.request(
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            timeout_seconds=self._timeout,
        )
        if response.status_code != 200:
            raise ValueError(f"Smithery registry returned status {response.status_code}")
        return json.loads(response.body)

    def _parse_servers(self, data: dict[str, Any]) -> list[SmitheryServerResult]:
        """Extract and normalize server entries from the Smithery response payload."""
        raw_servers = data.get("servers", [])
        if not isinstance(raw_servers, list):
            return []
        results: list[SmitheryServerResult] = []
        for item in raw_servers:
            if not isinstance(item, dict):
                continue
            qualified_name = str(item.get("qualifiedName", "")).strip()
            if not qualified_name:
                continue
            name = str(item.get("displayName", "") or qualified_name).strip()
            description = str(item.get("description", "") or "").strip()
            results.append(
                SmitheryServerResult(
                    name=name,
                    description=description,
                    command=self._derive_command(qualified_name),
                    qualified_name=qualified_name,
                )
            )
        return results

    def _derive_command(self, qualified_name: str) -> list[str]:
        """Build a runnable npx command list from a Smithery qualifiedName."""
        return ["npx", "-y", qualified_name]


class SearchMcpServersTool(BaseTool):
    """Searches the global Smithery MCP registry and returns structured server metadata."""

    def __init__(self, *, client: SmitheryRegistryClient | None = None, timeout: float = _DEFAULT_TIMEOUT) -> None:
        """Store the registry client, creating a default one if not provided."""
        self._client = client or SmitheryRegistryClient(timeout=timeout)

    def spec(self) -> ToolSpec:
        """Return the model-facing declaration for the search_mcp_servers tool."""
        return ToolSpec(
            name="search_mcp_servers",
            description=(
                "Search the global Smithery MCP server registry for servers matching a keyword query. "
                "Returns a JSON array of matching servers, each with a 'name', 'description', "
                "'qualified_name', and 'command' field. The 'command' field is a JSON-encoded string "
                "that can be passed directly to attach_mcp_server."
            ),
            parameters=(
                ToolParameter(
                    name="query",
                    type="string",
                    description="Keywords to search for in the Smithery registry (e.g. 'filesystem', 'github', 'database').",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results to return. Defaults to 10, clamped to 25.",
                    required=False,
                    default=_DEFAULT_LIMIT,
                ),
            ),
            permission=ToolPermission.SAFE,
            metadata={"source": "smithery"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run the Smithery search in a thread pool and return formatted JSON results."""
        query = str(call.arguments.get("query", "")).strip()
        if not query:
            return ToolResult.error(
                self.name,
                "query parameter cannot be empty.",
                metadata={"source": "smithery"},
            )
        raw_limit = call.arguments.get("limit", _DEFAULT_LIMIT)
        try:
            limit = max(1, min(int(raw_limit), _MAX_LIMIT))
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT

        results = await self._run_search(query, limit)
        if results is None:
            return ToolResult.error(
                self.name,
                self._last_error,
                metadata={"source": "smithery"},
            )
        formatted = self._format_results(results)
        return ToolResult.success(
            self.name,
            formatted,
            metadata={"source": "smithery", "result_count": len(results)},
        )

    async def _run_search(self, query: str, limit: int) -> list[SmitheryServerResult] | None:
        """Offload the synchronous HTTP search to a thread pool; return None on failure."""
        try:
            return await asyncio.to_thread(self._client.search, query, limit=limit)
        except Exception as exc:
            self._last_error = f"Smithery search failed: {exc}"
            return None

    def _format_results(self, results: list[SmitheryServerResult]) -> str:
        """Serialize results to a JSON string the model can parse and act on."""
        return json.dumps(
            [
                {
                    "name": r.name,
                    "description": r.description,
                    "qualified_name": r.qualified_name,
                    "command": json.dumps(r.command),
                }
                for r in results
            ],
            indent=2,
        )


__all__ = [
    "SearchMcpServersTool",
    "SmitheryRegistryClient",
    "SmitheryServerResult",
]
