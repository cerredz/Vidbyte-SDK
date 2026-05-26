"""Context Protocol Header

Description:
    Handles the MCP tools/list request (method: "tools/list").
Purpose:
    Returns all registered studio tool definitions converted to MCP tool format
    so clients can discover and invoke them.
Architecture:
    - ToolsListHandler: Reads tool specs from StudioToolRegistry and serializes them.
Relations:
    Registered in McpStudioServer._handler_map inside core.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.mcp_server.handlers import StudioToolRegistry
from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler


class ToolsListHandler(_BaseHandler):
    """Handles the MCP tools/list request."""

    def __init__(self, registry: StudioToolRegistry) -> None:
        """Stores the registry used to enumerate tool specs."""
        self._registry = registry

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Returns all registered tool definitions in MCP format."""
        tools = [McpSchema.tool_spec_to_mcp_tool(spec) for spec in self._registry.tool_specs()]
        return McpSchema.mcp_result_response(request_id, {"tools": tools})
