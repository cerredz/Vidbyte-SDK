"""Context Protocol Header

Description:
    Implements minimal MCP JSON-RPC client operations used by the bridge.
Purpose:
    Owns initialize, tools/list, and tools/call behavior while leaving native
    registry integration to McpBridgedTool.
Architecture:
    - McpClient: High-level MCP client over an injected transport.
Relations:
    Related to vidbyte.tools.mcp.transport and vidbyte.tools.mcp.bridge.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.tools.mcp.types import McpToolDefinition
from vidbyte.tools.mcp.transport import McpTransport
from vidbyte.tools.types import ToolResult


class McpClient:
    """Minimal MCP client for tool discovery and calls."""

    def __init__(self, transport: McpTransport, *, max_output_chars: int = 8000) -> None:
        """Store transport and output limit settings."""
        self.transport = transport
        self.max_output_chars = max_output_chars
        self.initialized = False

    async def initialize(self) -> None:
        """Send MCP initialize once."""
        if self.initialized:
            return
        await self.transport.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "vidbyte-sdk", "version": "0.1.0"},
            },
        )
        self.initialized = True

    async def list_tools(self) -> tuple[McpToolDefinition, ...]:
        """Return remote tool definitions from tools/list."""
        await self.initialize()
        result = await self.transport.request("tools/list")
        raw_tools = result.get("tools", ())
        tools: list[McpToolDefinition] = []
        if not isinstance(raw_tools, list):
            return ()
        for item in raw_tools:
            if not isinstance(item, Mapping):
                continue
            tools.append(
                McpToolDefinition(
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")) or "MCP bridged tool.",
                    input_schema=self._schema(item),
                )
            )
        return tuple(tool for tool in tools if tool.name)

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> ToolResult:
        """Call one remote MCP tool and normalize content into ToolResult."""
        await self.initialize()
        try:
            result = await self.transport.request(
                "tools/call",
                {"name": name, "arguments": dict(arguments)},
            )
        except Exception as exc:
            return ToolResult.error(name, f"MCP tool call failed: {exc}", metadata={"error": "mcp_error"})
        text = self._content_to_text(result)
        if len(text) > self.max_output_chars:
            text = text[: self.max_output_chars] + "\n...[truncated]"
        is_error = bool(result.get("isError", False))
        if is_error:
            return ToolResult.error(name, text, metadata={"remote_error": True})
        return ToolResult.success(name, text, metadata={"remote_error": False})

    def _schema(self, item: Mapping[str, Any]) -> Mapping[str, Any]:
        """Extract the input schema field from a remote tool definition."""
        schema = item.get("inputSchema") or item.get("input_schema") or {}
        if isinstance(schema, Mapping):
            return schema
        return {}

    def _content_to_text(self, result: Mapping[str, Any]) -> str:
        """Convert MCP content parts into prompt-safe text."""
        content = result.get("content", ())
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(result)
        parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
