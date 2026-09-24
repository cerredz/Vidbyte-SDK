"""FILE: tests/test_mcp_http_transport.py

PURPOSE: Verifies the MCP Streamable HTTP transport, remote MCP configs, and allowlisted, prefixed bridging without network access.
ROLE IN CODEBASE: Covers vidbyte/tools/mcp/transport.py (McpStreamableHttpTransport), vidbyte/tools/mcp/types.py, vidbyte/tools/mcp/attach.py, vidbyte/tools/mcp/bridge.py, and AttachMcpServerTool's url path for docs/design/jev-tool-alignment.md.
ARCHITECTURE NOTE: A scripted fake replaces vidbyte.lib.http.HttpTransport, returning JSON or text/event-stream bodies, so the transport's own session, header, and parsing logic stays under test.
COMMON MODIFICATION PATTERNS: Add a case whenever the transport learns a new status code, header, or reply shape.
KNOWN EDGE CASES: Header names are compared case-insensitively because httpx lowercases them.
RELATED DOCS: docs/design/jev-tool-alignment.md and vidbyte/tools/mcp/README.md.
TESTS: python -m pytest tests/test_mcp_http_transport.py.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from vidbyte.agents import BaseAgent
from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.lib.errors import ConfigurationError, McpProtocolError, ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse
from vidbyte.tools import ToolCall, ToolStatus
from vidbyte.tools.builtins.mcp import AttachMcpServerTool
from vidbyte.tools.mcp.attach import attach_mcp_server
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.transport import McpNotifyingTransport, McpStreamableHttpTransport
from vidbyte.tools.mcp.types import McpServerConfig

URL = "https://mcp.example.com/mcp"
TOOLS_LIST = {"tools": [
    {"name": "search", "description": "Search docs.", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}, "annotations": {"readOnlyHint": True}},
    {"name": "delete_page", "description": "Delete a page.", "inputSchema": {"type": "object"}, "annotations": {"destructiveHint": True}},
]}


class ScriptedHttp:
    """Fake HttpTransport that answers JSON-RPC by method and records every request."""

    def __init__(self, *, sse: bool = False, fail: bool = False, status: int = 200, rpc_error: bool = False) -> None:
        self.sse, self.fail, self.status, self.rpc_error = sse, fail, status, rpc_error
        self.requests: list[dict[str, Any]] = []

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, **kwargs: Any) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "body": json_body, **kwargs})
        if self.fail:
            raise ProviderRequestError("connection refused", provider="http")
        if method == "DELETE" or json_body is None or "id" not in json_body:
            return HttpResponse(status_code=202, body="", headers={})
        return self._reply(json_body)

    def _reply(self, body: Mapping[str, object]) -> HttpResponse:
        # Answers initialize with a session id, tools/list with two tools, and anything else with an empty result.
        result: object = {"protocolVersion": "2025-06-18", "capabilities": {}} if body["method"] == "initialize" else TOOLS_LIST if body["method"] == "tools/list" else {"content": [{"type": "text", "text": "ok"}]}
        message: dict[str, object] = {"jsonrpc": "2.0", "id": body["id"]}
        message.update({"error": {"code": -32601, "message": "no such method"}} if self.rpc_error else {"result": result})
        headers = {"mcp-session-id": "session-1"} if body["method"] == "initialize" else {}
        if self.sse:
            other = json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}})
            text = f"event: message\ndata: {other}\n\nevent: message\ndata: {json.dumps(message)}\n\n"
            return HttpResponse(status_code=self.status, body=text, headers={**headers, "content-type": "text/event-stream"})
        return HttpResponse(status_code=self.status, body=json.dumps(message), headers={**headers, "content-type": "application/json"})


class StreamableHttpTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_and_protocol_headers_follow_initialize(self) -> None:
        # [Hidden Failure] servers reject later requests that omit the session id or protocol version they assigned.
        http = ScriptedHttp()
        transport = McpStreamableHttpTransport(URL, headers={"Authorization": "Bearer k"}, http=http)  # type: ignore[arg-type]
        client = McpClient(transport)
        tools = await client.list_tools()
        methods = [request["body"].get("method") for request in http.requests]
        self.assertEqual(methods, ["initialize", "notifications/initialized", "tools/list"])
        self.assertNotIn("Mcp-Session-Id", http.requests[0]["headers"])
        self.assertEqual(http.requests[2]["headers"]["Mcp-Session-Id"], "session-1")
        self.assertEqual(http.requests[2]["headers"]["MCP-Protocol-Version"], "2025-06-18")
        self.assertEqual(http.requests[2]["headers"]["Authorization"], "Bearer k")
        self.assertNotIn("id", http.requests[1]["body"])
        # [Hidden Failure] HttpTransport adds a lowercase content-type; a mixed-case duplicate made servers answer 415.
        self.assertEqual(http.requests[0]["headers"]["content-type"], "application/json")
        self.assertNotIn("Content-Type", http.requests[0]["headers"])
        self.assertTrue(all(request["max_response_bytes"] > 0 for request in http.requests))
        self.assertEqual([tool.name for tool in tools], ["search", "delete_page"])
        self.assertTrue(tools[0].read_only)
        self.assertTrue(tools[1].destructive)
        self.assertIsInstance(transport, McpNotifyingTransport)

    async def test_event_stream_reply_is_matched_by_request_id(self) -> None:
        # [Edge Case] a server notification sharing the stream is skipped; the response with this id is returned.
        transport = McpStreamableHttpTransport(URL, http=ScriptedHttp(sse=True))  # type: ignore[arg-type]
        result = await transport.request("tools/list")
        self.assertEqual(result, TOOLS_LIST)

    async def test_failures_surface_as_mcp_protocol_errors(self) -> None:
        cases = [
            (ScriptedHttp(rpc_error=True), "rpc_error"),
            (ScriptedHttp(status=500), "http_status"),
            (ScriptedHttp(fail=True), "http_error"),
        ]
        for http, reason in cases:
            with self.subTest(reason=reason):
                transport = McpStreamableHttpTransport(URL, http=http)  # type: ignore[arg-type]
                with self.assertRaises(McpProtocolError) as caught:
                    await transport.request("tools/list")
                self.assertEqual(caught.exception.details["reason"], reason)

    async def test_close_ends_the_session_and_refuses_later_requests(self) -> None:
        http = ScriptedHttp()
        transport = McpStreamableHttpTransport(URL, http=http)  # type: ignore[arg-type]
        await transport.request("initialize", {})
        await transport.close()
        await transport.close()
        self.assertEqual([request["method"] for request in http.requests], ["POST", "DELETE"])
        with self.assertRaises(McpProtocolError):
            await transport.request("tools/list")

    def test_invalid_bounds_are_refused(self) -> None:
        with self.assertRaises(ConfigurationError):
            McpStreamableHttpTransport("", http=ScriptedHttp())  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            McpStreamableHttpTransport(URL, request_timeout=0, http=ScriptedHttp())  # type: ignore[arg-type]


class RemoteConfigAndBridgeTests(unittest.IsolatedAsyncioTestCase):
    def test_config_needs_exactly_one_target_and_hides_headers(self) -> None:
        with self.assertRaises(ConfigurationError):
            McpServerConfig()
        with self.assertRaises(ConfigurationError):
            McpServerConfig(command=("npx", "x"), url=URL)
        config = McpServerConfig(url=URL, headers={"Authorization": "Bearer secret-value"})
        self.assertNotIn("secret-value", repr(config))
        self.assertEqual(config.target, URL)

    async def test_attach_by_url_bridges_only_allowlisted_tools_under_a_prefix(self) -> None:
        # [Security] an allowlist keeps extra server tools out, and the server is still called by its own name.
        http = ScriptedHttp()

        def build(url: str, *, headers: Mapping[str, str] | None = None, request_timeout: float = 30.0) -> McpStreamableHttpTransport:
            return McpStreamableHttpTransport(url, headers=headers, request_timeout=request_timeout, http=http)  # type: ignore[arg-type]

        with patch("vidbyte.tools.mcp.attach.McpStreamableHttpTransport", build):
            handle = await attach_mcp_server(McpServerConfig(url=URL, tool_allowlist=("search",), tool_prefix="docs__"))
        self.assertEqual(handle.tool_names, ("docs__search",))
        self.assertEqual([definition.name for definition in handle.definitions], ["search", "delete_page"])
        result = await handle.bridged_tools[0].execute(ToolCall("docs__search", {"q": "x"}))
        self.assertEqual(result.tool_name, "docs__search")
        self.assertEqual(http.requests[-1]["body"]["params"]["name"], "search")
        await handle.close()

    def test_tool_definition_hints_are_optional(self) -> None:
        definition = McpToolDefinition(name="t", description="d")
        self.assertIsNone(definition.read_only)
        self.assertIsNone(definition.destructive)


class AttachToolUrlTests(unittest.IsolatedAsyncioTestCase):
    async def test_url_attach_and_target_validation(self) -> None:
        captured: list[dict[str, Any]] = []
        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)

        async def fake_attach(command: Any = (), **kwargs: Any) -> BaseAgent:
            captured.append({"command": command, **kwargs})
            return agent

        with patch.object(agent, "attach_mcp_server", side_effect=fake_attach):
            ok = await tool.execute(ToolCall("attach_mcp_server", {"url": URL}))
            both = await tool.execute(ToolCall("attach_mcp_server", {"url": URL, "command": '["npx", "x"]'}))
            insecure = await tool.execute(ToolCall("attach_mcp_server", {"url": "http://mcp.example.com/mcp"}))
        self.assertEqual(ok.status, ToolStatus.SUCCESS)
        self.assertEqual(captured[0]["url"], URL)
        self.assertEqual(both.status, ToolStatus.ERROR)
        self.assertEqual(insecure.status, ToolStatus.ERROR)
        self.assertEqual(len(captured), 1)


if __name__ == "__main__":
    unittest.main()
