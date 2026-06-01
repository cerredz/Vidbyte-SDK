"""Context Protocol Header

Description:
    Wraps remote MCP tools as native Vidbyte SDK BaseTool instances.
Purpose:
    Allows dynamically discovered MCP tools to participate in the same registry,
    permission, validation, and execution pipeline as local tools.
Architecture:
    - McpBridgedTool: Converts one McpToolDefinition into a BaseTool.
    - McpToolBridge: Discovers all remote tools and registers wrappers.
Relations:
    Related to vidbyte.tools.mcp.client, vidbyte.tools.registry, and tool types.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.tools.base import BaseTool
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.types import McpToolDefinition
from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec


class McpBridgedTool(BaseTool):
    """Native wrapper around one remote MCP tool."""

    def __init__(
        self,
        mcp_client: McpClient,
        remote_tool: McpToolDefinition,
        *,
        permission: ToolPermission = ToolPermission.EXECUTE,
    ) -> None:
        """Store the client and remote tool metadata."""
        self.mcp_client = mcp_client
        self.remote_tool = remote_tool
        self.permission = permission

    def spec(self) -> ToolSpec:
        """Convert MCP JSON Schema metadata into a native ToolSpec."""
        return ToolSpec(
            name=self.remote_tool.name,
            description=self.remote_tool.description,
            parameters=self._parameters(self.remote_tool.input_schema),
            permission=self.permission,
            metadata={"source": "mcp"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Forward the tool call to the remote MCP server."""
        result = await self.mcp_client.call_tool(self.remote_tool.name, call.arguments)
        return ToolResult(
            tool_name=self.name,
            status=result.status,
            output=result.output,
            metadata=dict(result.metadata),
        )

    def _parameters(self, schema: Mapping[str, Any]) -> tuple[ToolParameter, ...]:
        """Translate basic JSON Schema properties into ToolParameter values."""
        properties = schema.get("properties", {})
        required = set(schema.get("required", ()))
        if not isinstance(properties, Mapping):
            return ()
        parameters: list[ToolParameter] = []
        for name, raw_property in properties.items():
            if not isinstance(raw_property, Mapping):
                raw_property = {}
            parameters.append(
                ToolParameter(
                    name=str(name),
                    type=str(raw_property.get("type", "object")),
                    description=str(raw_property.get("description", "")) or "MCP tool parameter.",
                    required=str(name) in required,
                )
            )
        return tuple(parameters)


class McpToolBridge:
    """Async bridge that discovers remote MCP tools and registers native wrappers."""

    def __init__(
        self,
        registry: ToolRegistry,
        client: McpClient,
        *,
        permission: ToolPermission = ToolPermission.EXECUTE,
    ) -> None:
        self.registry = registry
        self.client = client
        self.permission = permission

    async def bridge(self) -> tuple[McpBridgedTool, ...]:
        """Discover remote MCP tools, register wrappers, and return them."""
        bridged: list[McpBridgedTool] = []
        for remote_tool in await self.client.list_tools():
            tool = McpBridgedTool(self.client, remote_tool, permission=self.permission)
            self.registry.register(tool)
            bridged.append(tool)
        return tuple(bridged)
