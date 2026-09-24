"""Context Protocol Header

Description:
    Wraps remote MCP tools as native Vidbyte SDK BaseTool instances.
Purpose:
    Allows dynamically discovered MCP tools to participate in the same registry,
    permission, validation, and execution pipeline as local tools.
Architecture:
    - McpBridgedTool: Converts one McpToolDefinition into a BaseTool, optionally
      under an exposed name that differs from the remote name.
    - McpToolBridge: Discovers remote tools and registers wrappers, optionally
      limited to an allowlist and prefixed so two servers cannot collide.
Relations:
    Related to vidbyte.tools.mcp.client, vidbyte.tools.registry, and tool types.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.registries.tools import ToolRegistry
from vidbyte.tools.base import BaseTool
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.types import McpToolDefinition
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)


class McpBridgedTool(BaseTool):
    """Native wrapper around one remote MCP tool."""

    def __init__(
        self,
        mcp_client: McpClient,
        remote_tool: McpToolDefinition,
        *,
        permission: ToolPermission = ToolPermission.EXECUTE,
        exposed_name: str | None = None,
    ) -> None:
        """Store the client, the remote tool metadata, and the name the model sees (the remote name by default)."""
        # @intent exposed-name-is-local-remote-name-is-wire
        # The model calls the exposed name, but the server is always called by its own remote name, so a prefix
        # added to avoid collisions can never reach the remote server.
        self.mcp_client = mcp_client
        self.remote_tool = remote_tool
        self.permission = permission
        self.exposed_name = exposed_name or remote_tool.name

    def spec(self) -> ToolSpec:
        """Convert MCP JSON Schema metadata into a native ToolSpec."""
        return ToolSpec(
            name=self.exposed_name,
            description=self.remote_tool.description,
            parameters=self._parameters(self.remote_tool.input_schema),
            permission=self.permission,
            metadata={"source": "mcp", "mcp_tool": self.remote_tool.name},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        """Forward the tool call to the remote MCP server under the tool's remote name."""
        result = await self.mcp_client.call_tool(self.remote_tool.name, call.arguments)
        return ToolResult(
            tool_name=self.exposed_name,
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

    async def bridge(self, *, allowlist: tuple[str, ...] | None = None, prefix: str = "") -> tuple[McpBridgedTool, ...]:
        """Discover remote MCP tools, register wrappers, and return them."""
        return self.bridge_definitions(await self.client.list_tools(), allowlist=allowlist, prefix=prefix)

    def bridge_definitions(
        self,
        definitions: tuple[McpToolDefinition, ...],
        *,
        allowlist: tuple[str, ...] | None = None,
        prefix: str = "",
    ) -> tuple[McpBridgedTool, ...]:
        """Wrap already-discovered definitions, keeping only allowlisted names when an allowlist is given."""
        # @intent allowlist-bounds-what-is-bridged
        # An allowlist bridges only the named tools, so a server that lists extra tools cannot slip them into the
        # agent; an empty allowlist bridges none, which is how callers read tools without exposing them.
        allowed = None if allowlist is None else set(allowlist)
        bridged: list[McpBridgedTool] = []
        for remote_tool in definitions:
            if allowed is not None and remote_tool.name not in allowed:
                continue
            tool = McpBridgedTool(self.client, remote_tool, permission=self.permission, exposed_name=f"{prefix}{remote_tool.name}")
            self.registry.register(tool)
            bridged.append(tool)
        return tuple(bridged)
