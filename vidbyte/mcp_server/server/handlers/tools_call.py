"""Context Protocol Header

Description:
    Handles the MCP tools/call request (method: "tools/call").
Purpose:
    Validates the incoming params, delegates execution to the StudioToolRegistry,
    and converts the SDK ToolResult into a JSON-RPC MCP response.
Architecture:
    - ToolsCallHandler: Validates params -> executes via registry -> serializes result.
Relations:
    Registered in McpStudioServer._handler_map inside core.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.mcp_server.handlers import StudioToolRegistry
from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler

JSONRPC_INVALID_PARAMS = -32602


class ToolsCallHandler(_BaseHandler):
    """Handles the MCP tools/call request."""

    def __init__(self, registry: StudioToolRegistry) -> None:
        """Stores the registry used to find and execute tools by name."""
        self._registry = registry

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Validates params, executes the named tool, and returns its result."""
        if not isinstance(params, Mapping):
            return McpSchema.mcp_error_response(request_id, JSONRPC_INVALID_PARAMS, "Invalid params")
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments")
        if not isinstance(arguments, Mapping):
            arguments = {}
        if not tool_name:
            return McpSchema.mcp_error_response(request_id, JSONRPC_INVALID_PARAMS, "Missing tool name")
        try:
            result = await self._registry.execute(tool_name, dict(arguments))
        except Exception as exc:
            return McpSchema.mcp_tool_error_result(request_id, f"Tool execution failed: {exc}")
        content = McpSchema.tool_result_to_mcp_content(result)
        if result.status == "error" or result.output.startswith("Error:"):
            return McpSchema.mcp_tool_error_result(request_id, result.output)
        return McpSchema.mcp_tool_success_result(request_id, content)
