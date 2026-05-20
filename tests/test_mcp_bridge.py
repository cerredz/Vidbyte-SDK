"""Context Protocol Header

Description:
    Tests MCP client and bridge behavior with a fake transport.
Purpose:
    Verifies dynamic remote schema conversion and native ToolResult normalization.
Architecture:
    - FakeTransport: Deterministic MCP transport.
    - McpBridgeTests: Discovery, registration, execution, and permission tests.
Relations:
    Related to vidbyte.tools.mcp.client and bridge.
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any

from vidbyte.tools import ToolCall, ToolPermission, ToolRegistry
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.mcp import McpBridgedTool, McpClient
from vidbyte.tools.security import PermissionPolicy


class FakeTransport:
    """Fake JSON-RPC transport for MCP tests."""

    def __init__(self) -> None:
        """Initialize request tracking."""
        self.methods: list[str] = []

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Return canned MCP responses."""
        self.methods.append(method)
        if method == "initialize":
            return {"ok": True}
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "remote_echo",
                        "description": "Remote echo.",
                        "inputSchema": {
                            "type": "object",
                            "required": ["text"],
                            "properties": {
                                "text": {"type": "string", "description": "Text."}
                            },
                        },
                    }
                ]
            }
        if method == "tools/call":
            args = dict((params or {}).get("arguments", {}))
            return {"content": [{"type": "text", "text": args.get("text", "")}]}
        raise AssertionError(method)


class McpBridgeTests(unittest.IsolatedAsyncioTestCase):
    """Verifies MCP bridge behavior."""

    async def test_bridge_registers_and_executes_remote_tool(self) -> None:
        """Remote tools are exposed as native registry entries."""
        registry = ToolRegistry()
        client = McpClient(FakeTransport())
        tools = tuple(
            McpBridgedTool(client, remote_tool, permission=ToolPermission.READ)
            for remote_tool in await client.list_tools()
        )
        for tool in tools:
            registry.register(tool)
        self.assertEqual(len(tools), 1)
        self.assertEqual(registry.get("remote_echo").spec().parameters[0].name, "text")
        result = await ToolExecutor(
            registry,
            permission_policy=PermissionPolicy.allow_all(),
        ).execute_call(ToolCall("remote_echo", {"text": "hello"}))
        self.assertEqual(result.output, "hello")
