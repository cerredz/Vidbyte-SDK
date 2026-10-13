"""Context Protocol Header

Description:
    Tests MCP client and bridge behavior with a fake transport.
Purpose:
    Verifies dynamic remote schema conversion and native ToolResult normalization.
Architecture:
    - FakeTransport: Deterministic MCP transport.
    - PagedFakeTransport / McpClientPaginationTests: tools/list follows nextCursor across pages.
    - RaisingFakeTransport / McpClientProtocolErrorTests: a JSON-RPC error's message reaches the model.
    - McpBridgeTests: Discovery, registration, execution, and permission tests.
    - McpBridgeSchemaTests: Remote input schemas reach provider tool declarations intact.
Relations:
    Related to vidbyte.tools.mcp.client and bridge.
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import McpProtocolError
from vidbyte.tools import ToolCall, ToolPermission, ToolRegistry, ToolsFormatter, ToolStatus
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.mcp import McpBridgedTool, McpClient, McpToolBridge, McpToolDefinition
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


class PagedFakeTransport(FakeTransport):
    """Fake transport whose tools/list follows a cursor map; other methods fall back to FakeTransport."""

    def __init__(self, pages: Mapping[str | None, Mapping[str, Any]]) -> None:
        """Store one tools/list page per cursor (None is the first page)."""
        super().__init__()
        self.pages = pages
        self.list_params: list[Mapping[str, Any] | None] = []

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Serve the page for the requested cursor."""
        if method != "tools/list":
            return await super().request(method, params)
        self.methods.append(method)
        self.list_params.append(params)
        return self.pages[(params or {}).get("cursor")]


class RaisingFakeTransport(FakeTransport):
    """Fake transport whose tools/call raises a given error; other methods fall back to FakeTransport."""

    def __init__(self, error: Exception) -> None:
        """Store the error that tools/call raises."""
        super().__init__()
        self.error = error

    async def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Raise the stored error for tools/call."""
        if method == "tools/call":
            raise self.error
        return await super().request(method, params)


class McpClientProtocolErrorTests(unittest.IsolatedAsyncioTestCase):
    """A JSON-RPC error's message reaches the model; other transport failures read as before."""

    async def test_protocol_error_reason_reaches_the_model(self) -> None:
        reason = "MCP error -32602: Invalid arguments for tool lookup: order_id: Expected string, received number"
        error = McpProtocolError(
            "MCP server returned an error",
            details={"error": {"code": -32602, "message": reason}},
        )
        result = await McpClient(RaisingFakeTransport(error)).call_tool("lookup", {"order_id": 42})
        self.assertIs(result.status, ToolStatus.ERROR)
        self.assertIn("MCP server returned an error", result.output)
        self.assertIn("order_id: Expected string, received number", result.output)
        self.assertEqual(result.metadata.get("error"), "mcp_error")

    async def test_error_without_server_message_is_unchanged(self) -> None:
        error = McpProtocolError("MCP request timed out", details={"reason": "timeout"})
        result = await McpClient(RaisingFakeTransport(error)).call_tool("lookup", {"order_id": "A1"})
        self.assertIs(result.status, ToolStatus.ERROR)
        self.assertEqual(result.output, "MCP tool call failed: MCP request timed out")


class McpClientPaginationTests(unittest.IsolatedAsyncioTestCase):
    """tools/list discovery reads every page a paginating server offers."""

    async def test_list_tools_follows_next_cursor_across_pages(self) -> None:
        transport = PagedFakeTransport(
            {
                None: {"tools": [{"name": "echo"}], "nextCursor": "p2"},
                "p2": {"tools": [{"name": "image"}], "nextCursor": "p3"},
                "p3": {"tools": [{"name": "ping"}]},
            }
        )
        tools = await McpClient(transport).list_tools()
        self.assertEqual([tool.name for tool in tools], ["echo", "image", "ping"])
        # The first request is unchanged (no params); later ones carry the server's cursor.
        self.assertEqual(transport.list_params, [None, {"cursor": "p2"}, {"cursor": "p3"}])

    async def test_list_tools_stops_on_a_repeated_cursor(self) -> None:
        transport = PagedFakeTransport(
            {
                None: {"tools": [{"name": "echo"}], "nextCursor": "loop"},
                "loop": {"tools": [{"name": "ping"}], "nextCursor": "loop"},
            }
        )
        tools = await McpClient(transport).list_tools()
        self.assertEqual([tool.name for tool in tools], ["echo", "ping"])
        self.assertEqual(len(transport.list_params), 2)


class McpBridgeTests(unittest.IsolatedAsyncioTestCase):
    """Verifies MCP bridge behavior."""

    async def test_bridge_registers_and_executes_remote_tool(self) -> None:
        """Remote tools are exposed as native registry entries."""
        registry = ToolRegistry()
        client = McpClient(FakeTransport())
        tools = await McpToolBridge(registry, client, permission=ToolPermission.READ).bridge()
        self.assertEqual(len(tools), 1)
        self.assertEqual(registry.get("remote_echo").spec().parameters[0].name, "text")
        result = await ToolExecutor(
            registry,
            permission_policy=PermissionPolicy.allow_all(),
        ).execute_call(ToolCall("remote_echo", {"text": "hello"}))
        self.assertEqual(result.output, "hello")

    def test_binary_content_is_replaced_by_placeholder(self) -> None:
        """Image base64 payloads never reach the prompt; text parts survive."""
        client = McpClient(FakeTransport())
        text = client._content_to_text(
            {
                "content": [
                    {"type": "text", "text": "part one"},
                    {"type": "text", "text": "part two"},
                    {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"},
                ]
            }
        )
        self.assertEqual(text, "part one\npart two\n[image: image/png, 12 base64 chars omitted]")
        self.assertNotIn("iVBORw0KGgo=", text)

    def test_binary_embedded_resource_is_replaced_by_placeholder(self) -> None:
        """An embedded resource's base64 blob never reaches the prompt; uri and mimeType do."""
        client = McpClient(FakeTransport())
        blob = "JVBERi0xLjQKJcfsj6IKBLOBPAYLOAD=="
        text = client._content_to_text(
            {
                "content": [
                    {"type": "text", "text": "exported"},
                    {
                        "type": "resource",
                        "resource": {"uri": "file:///r.pdf", "mimeType": "application/pdf", "blob": blob},
                    },
                ]
            }
        )
        self.assertEqual(text, f"exported\n[resource: file:///r.pdf, application/pdf, {len(blob)} base64 chars omitted]")
        self.assertNotIn(blob, text)

    def test_text_embedded_resource_is_shown_as_its_text(self) -> None:
        """An embedded resource's text reaches the prompt under its uri, not as a dict repr."""
        client = McpClient(FakeTransport())
        text = client._content_to_text(
            {
                "content": [
                    {"type": "text", "text": "fetched"},
                    {
                        "type": "resource",
                        "resource": {
                            "uri": "file:///notes.md",
                            "mimeType": "text/markdown",
                            "text": "# Notes\n- it's \"quoted\"",
                        },
                    },
                ]
            }
        )
        self.assertEqual(text, "fetched\n[resource: file:///notes.md, text/markdown]\n# Notes\n- it's \"quoted\"")


class McpBridgeSchemaTests(unittest.TestCase):
    """Verifies the remote input schema survives into provider tool declarations."""

    _RICH_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {
            "labels": {"type": "array", "items": {"type": "string"}, "description": "Labels to apply."},
            "severity": {"type": "string", "enum": ["low", "high"], "description": "Issue severity."},
            "meta": {
                "type": "object",
                "properties": {"source": {"type": "string"}},
                "required": ["source"],
            },
        },
        "required": ["labels", "severity"],
    }

    def _bridged(self, schema: Mapping[str, Any]) -> McpBridgedTool:
        remote = McpToolDefinition(name="file_issue", description="File an issue.", input_schema=schema)
        return McpBridgedTool(McpClient(FakeTransport()), remote)

    def test_items_enum_and_nested_properties_reach_the_provider(self) -> None:
        """Array items, enums, and nested objects are not flattened away."""
        tool = self._bridged(self._RICH_SCHEMA)
        openai = ToolsFormatter.to_openai_tool(tool.spec())["function"]["parameters"]
        self.assertEqual(openai, self._RICH_SCHEMA)
        gemini = ToolsFormatter.to_gemini_tool(tool.spec())["function_declarations"][0]["parameters"]
        self.assertEqual(gemini["properties"]["labels"]["items"], {"type": "string"})
        self.assertEqual(gemini["properties"]["severity"]["enum"], ["low", "high"])
        self.assertEqual(gemini["properties"]["meta"]["required"], ["source"])
        self.assertEqual(tool.validate_call(ToolCall("file_issue", {"labels": []})), "Missing required parameters: severity")

    def test_spec_schema_is_a_copy_of_the_remote_definition(self) -> None:
        """Mutating the remote schema later does not change an already built spec."""
        schema = {"type": "object", "properties": {"labels": {"type": "array", "items": {"type": "string"}}}}
        spec = self._bridged(schema).spec()
        schema["properties"]["labels"]["items"]["type"] = "integer"
        self.assertEqual(spec.input_schema["properties"]["labels"]["items"], {"type": "string"})

    def test_schema_without_properties_still_yields_an_object_schema(self) -> None:
        """Degenerate remote schemas fall back to a valid empty object schema."""
        for schema in ({}, {"type": "object", "additionalProperties": False}, {"type": "string"}):
            with self.subTest(schema=schema):
                spec = self._bridged(schema).spec()
                self.assertIsNone(spec.input_schema)
                parameters = ToolsFormatter.to_openai_tool(spec)["function"]["parameters"]
                self.assertEqual(parameters["type"], "object")
                self.assertEqual(parameters["properties"], {})
