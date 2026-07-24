"""Context Protocol Header

Description:
    Tests for SearchMcpServersTool, AttachMcpServerTool, and agent binding integration.
Purpose:
    Verifies search result formatting, HTTP failure handling, command validation,
    permission mapping, agent binding lifecycle, and agent constructor binding.
Architecture:
    - FakeSmitheryTransport: Deterministic HTTP transport for search tests.
    - MockMcpAttachable: Minimal McpAttachableMixin stand-in for attach tests.
    - SearchMcpServersToolTests: All search tool scenarios.
    - AttachMcpServerToolTests: All attach tool scenarios.
    - AgentBindingTests: Integration tests for add_tool() and constructor binding.
Relations:
    vidbyte/tools/builtins/mcp/search.py
    vidbyte/tools/builtins/mcp/attach_tool.py
    vidbyte/agents/base.py
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from vidbyte.agents import BaseAgent
from vidbyte.lib.errors import McpConnectionError
from vidbyte.tools import ToolCall, ToolStatus
from vidbyte.tools.builtins.mcp import AttachMcpServerTool, SearchMcpServersTool
from vidbyte.tools.builtins.mcp.search import SmitheryRegistryClient, SmitheryServerResult
from vidbyte.tools.mcp.types import McpServerHandle, McpToolPermission


# ---------------------------------------------------------------------------
# Fake HTTP transport for SmitheryRegistryClient
# ---------------------------------------------------------------------------


class FakeSmitheryTransport:
    """Deterministic HTTP transport that returns configurable Smithery-shaped responses."""

    def __init__(self, status_code: int = 200, body: str = "", raise_exc: Exception | None = None) -> None:
        """Configure the response this transport will return."""
        self.status_code = status_code
        self.body = body
        self.raise_exc = raise_exc
        self.last_url: str = ""

    def request(self, *, method: str, url: str, headers: Mapping[str, str], timeout_seconds: float = 10.0, **kwargs: Any) -> object:
        """Return a fake HTTP response or raise a configured exception."""
        self.last_url = url
        if self.raise_exc is not None:
            raise self.raise_exc
        response = MagicMock()
        response.status_code = self.status_code
        response.body = self.body
        return response


def _smithery_body(servers: list[dict[str, Any]]) -> str:
    """Produce a minimal Smithery API response body."""
    return json.dumps({"servers": servers})


def _make_server_entry(qualified_name: str, display_name: str = "", description: str = "A tool.") -> dict[str, Any]:
    """Build one Smithery server dict."""
    return {
        "qualifiedName": qualified_name,
        "displayName": display_name or qualified_name,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Fake MCP transport and agent for AttachMcpServerTool tests
# ---------------------------------------------------------------------------


class MockMcpStdioTransport:
    """Minimal MCP transport mock for attach tests."""

    def __init__(
        self,
        command: list[str],
        *,
        env: dict | None = None,
        request_timeout: float = 30.0,
        shutdown_timeout: float = 5.0,
        stderr_max_bytes: int = 64 * 1024,
        **_: object,
    ) -> None:
        """Store command and track closed state."""
        self.command = command
        self.env = env
        self.request_timeout = request_timeout
        self.shutdown_timeout = shutdown_timeout
        self.stderr_max_bytes = stderr_max_bytes
        self.closed = False

    async def start(self) -> None:
        """No-op start."""

    async def request(self, method: str, params: dict | None = None) -> dict:
        """Return canned MCP protocol responses."""
        if method == "initialize":
            return {"ok": True}
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": f"remote_{self.command[0]}",
                        "description": "A remote tool.",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            }
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "ok"}]}
        raise ValueError(f"Unknown method {method}")

    async def close(self) -> None:
        """Mark transport as closed."""
        self.closed = True




# ---------------------------------------------------------------------------
# SearchMcpServersTool tests
# ---------------------------------------------------------------------------


class SearchMcpServersToolTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for SearchMcpServersTool and SmitheryRegistryClient."""

    def _make_tool(self, status_code: int = 200, body: str = "", raise_exc: Exception | None = None) -> SearchMcpServersTool:
        transport = FakeSmitheryTransport(status_code=status_code, body=body, raise_exc=raise_exc)
        client = SmitheryRegistryClient(transport=transport)
        return SearchMcpServersTool(client=client)

    async def test_returns_empty_list_when_smithery_returns_no_servers(self) -> None:
        """[Edge Case] Zero Smithery results produce a success with empty JSON array, not an error."""
        tool = self._make_tool(body=_smithery_body([]))
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": "filesystem"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        parsed = json.loads(result.output)
        self.assertEqual(parsed, [])

    async def test_blank_query_returns_error_before_http_call(self) -> None:
        """[Hidden Assumption] Empty query must return error immediately without making HTTP request."""
        transport = FakeSmitheryTransport(body=_smithery_body([]))
        client = SmitheryRegistryClient(transport=transport)
        tool = SearchMcpServersTool(client=client)
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": ""}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertEqual(transport.last_url, "", "HTTP request must not be sent for blank query.")

    async def test_smithery_http_failure_returns_tool_result_error_not_exception(self) -> None:
        """[Silent Failure] ProviderRequestError from transport must surface as ToolResult.error."""
        from vidbyte.lib.errors import ProviderRequestError
        exc = ProviderRequestError("connection refused", provider="http")
        tool = self._make_tool(raise_exc=exc)
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": "database"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("Smithery search failed", result.output)

    async def test_smithery_non_200_returns_error(self) -> None:
        """[Hidden Failure] Non-200 status code must yield ToolResult.error, not a silent empty list."""
        tool = self._make_tool(status_code=429, body='{"error": "rate limited"}')
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": "filesystem"}))
        self.assertEqual(result.status, ToolStatus.ERROR)

    async def test_command_field_is_json_encoded_npx_string(self) -> None:
        """[Silent Failure] command field must be a JSON-encoded string, not a raw Python list."""
        body = _smithery_body([_make_server_entry("@modelcontextprotocol/server-filesystem", "Filesystem")])
        tool = self._make_tool(body=body)
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": "filesystem"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        items = json.loads(result.output)
        self.assertEqual(len(items), 1)
        # command must be a string, parseable as JSON
        self.assertIsInstance(items[0]["command"], str)
        parsed_command = json.loads(items[0]["command"])
        self.assertEqual(parsed_command, ["npx", "-y", "@modelcontextprotocol/server-filesystem"])

    async def test_limit_clamped_to_25(self) -> None:
        """[Edge Case] limit=100 must send pageSize=25 in the HTTP request."""
        transport = FakeSmitheryTransport(body=_smithery_body([]))
        client = SmitheryRegistryClient(transport=transport)
        tool = SearchMcpServersTool(client=client)
        await tool.execute(ToolCall("search_mcp_servers", {"query": "x", "limit": 100}))
        self.assertIn("pageSize=25", transport.last_url)

    async def test_entries_with_empty_qualified_name_skipped(self) -> None:
        """[Hidden Failure] Entries where qualifiedName is empty must be excluded from results."""
        servers = [
            _make_server_entry("@mcp/valid-server", "Valid"),
            {"qualifiedName": "", "displayName": "Bad", "description": "No name."},
        ]
        tool = self._make_tool(body=_smithery_body(servers))
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": "anything"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        items = json.loads(result.output)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["qualified_name"], "@mcp/valid-server")

    def test_malformed_json_response_raises_value_error(self) -> None:
        """[Hidden Assumption] SmitheryRegistryClient.search raises ValueError on malformed JSON."""
        transport = FakeSmitheryTransport(body="not json at all")
        client = SmitheryRegistryClient(transport=transport)
        with self.assertRaises(ValueError):
            client.search("something")

    async def test_missing_displayname_falls_back_to_qualified_name(self) -> None:
        """[Silent Failure] Missing displayName must fall back to qualifiedName, not return None or empty."""
        servers = [{"qualifiedName": "@mcp/server-x", "description": "Desc."}]
        tool = self._make_tool(body=_smithery_body(servers))
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": "x"}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        items = json.loads(result.output)
        self.assertNotEqual(items[0]["name"], "")
        self.assertIsNotNone(items[0]["name"])

    async def test_result_metadata_includes_source_and_count(self) -> None:
        """[Silent Failure] Result metadata must include source=smithery and correct result_count."""
        body = _smithery_body([_make_server_entry("@mcp/a"), _make_server_entry("@mcp/b")])
        tool = self._make_tool(body=body)
        result = await tool.execute(ToolCall("search_mcp_servers", {"query": "something"}))
        self.assertEqual(result.metadata.get("source"), "smithery")
        self.assertEqual(result.metadata.get("result_count"), 2)


# ---------------------------------------------------------------------------
# AttachMcpServerTool tests
# ---------------------------------------------------------------------------


@patch("vidbyte.tools.mcp.attach.McpStdioTransport", MockMcpStdioTransport)
class AttachMcpServerToolTests(unittest.IsolatedAsyncioTestCase):
    """Unit tests for AttachMcpServerTool."""

    async def test_execute_without_bind_returns_error(self) -> None:
        """[Hidden Assumption] Calling execute() before bind_agent() must return ToolResult.error."""
        tool = AttachMcpServerTool()
        result = await tool.execute(ToolCall("attach_mcp_server", {"command": '["npx", "myserver"]'}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("No agent bound", result.output)

    async def test_invalid_json_command_returns_error(self) -> None:
        """[Edge Case] Non-JSON command string must return ToolResult.error."""
        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)
        result = await tool.execute(ToolCall("attach_mcp_server", {"command": "not json"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("not valid JSON", result.output)

    async def test_empty_command_list_returns_error(self) -> None:
        """[Edge Case] command=[] must return ToolResult.error before any attachment attempt."""
        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)
        result = await tool.execute(ToolCall("attach_mcp_server", {"command": "[]"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("non-empty", result.output)

    async def test_non_string_elements_in_command_returns_error(self) -> None:
        """[Hidden Assumption] Command array with integers must be rejected."""
        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)
        result = await tool.execute(ToolCall("attach_mcp_server", {"command": "[1, 2, 3]"}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("strings", result.output)

    async def test_successful_attach_returns_tool_names_in_summary(self) -> None:
        """[Silent Failure] Summary must include all bridged tool names, not a truncated list."""
        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)
        result = await tool.execute(ToolCall("attach_mcp_server", {"command": '["myserver"]'}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        summary = json.loads(result.output)
        self.assertTrue(summary["attached"])
        self.assertIn("remote_myserver", summary["tools_added"])

    async def test_mcp_connection_error_returns_tool_result_error_not_exception(self) -> None:
        """[Silent Failure] McpConnectionError must surface as ToolResult.error, not propagate."""
        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)
        with patch.object(agent, "attach_mcp_server", side_effect=McpConnectionError("fail")):
            result = await tool.execute(ToolCall("attach_mcp_server", {"command": '["npx", "x"]'}))
        self.assertEqual(result.status, ToolStatus.ERROR)
        self.assertIn("attachment failed", result.output)

    async def test_permission_string_maps_correctly(self) -> None:
        """[Silent Failure] 'readonly' and 'disabled' must map to correct McpToolPermission values."""
        captured_permissions: list[McpToolPermission] = []

        async def capture_attach(command, *, name=None, permission=McpToolPermission.EXECUTE, timeout=30.0):
            captured_permissions.append(permission)
            # Simulate adding a handle so the tool can read mcp_servers()[-1]
            mock_handle = MagicMock()
            mock_handle.name = "mock"
            mock_handle.tool_names = ()
            agent._mcp_handles.append(mock_handle)
            return agent

        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)

        with patch.object(agent, "attach_mcp_server", side_effect=capture_attach):
            await tool.execute(ToolCall("attach_mcp_server", {"command": '["x"]', "permission": "readonly"}))
            await tool.execute(ToolCall("attach_mcp_server", {"command": '["x"]', "permission": "disabled"}))
            await tool.execute(ToolCall("attach_mcp_server", {"command": '["x"]', "permission": "invalid"}))

        self.assertEqual(captured_permissions[0], McpToolPermission.READONLY)
        self.assertEqual(captured_permissions[1], McpToolPermission.DISABLED)
        self.assertEqual(captured_permissions[2], McpToolPermission.EXECUTE)

    async def test_result_metadata_includes_source_and_tool_count(self) -> None:
        """[Silent Failure] Metadata must include source=mcp_attach and correct tool_count."""
        agent = BaseAgent(name="a", system_prompt=".")
        tool = AttachMcpServerTool()
        tool.bind_agent(agent)
        result = await tool.execute(ToolCall("attach_mcp_server", {"command": '["myserver"]'}))
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.metadata.get("source"), "mcp_attach")
        self.assertIsInstance(result.metadata.get("tool_count"), int)


# ---------------------------------------------------------------------------
# Agent binding integration tests
# ---------------------------------------------------------------------------


class AgentBindingTests(unittest.IsolatedAsyncioTestCase):
    """Integration tests verifying agent binding via add_tool() and constructor."""

    def test_add_tool_binds_agent_to_attach_tool(self) -> None:
        """[Hidden Assumption] After add_tool(AttachMcpServerTool()), tool._agent must be the agent."""
        agent = BaseAgent(name="a", system_prompt=".")
        attach_tool = AttachMcpServerTool()
        self.assertIsNone(attach_tool._agent)
        agent.add_tool(attach_tool)
        self.assertIs(attach_tool._agent, agent)

    def test_search_tool_does_not_require_binding(self) -> None:
        """[Hidden Assumption] SearchMcpServersTool can be added to an agent without error."""
        agent = BaseAgent(name="a", system_prompt=".")
        search_tool = SearchMcpServersTool()
        agent.add_tool(search_tool)
        self.assertIn("search_mcp_servers", [t.name for t in agent._agent_tool_items])

    def test_constructor_tools_list_also_binds_agent(self) -> None:
        """[Hidden Failure] Tools passed via tools= constructor arg must also be bound at init time."""
        attach_tool = AttachMcpServerTool()
        agent = BaseAgent(name="a", system_prompt=".", tools=[attach_tool])
        self.assertIs(attach_tool._agent, agent)

    def test_both_tools_appear_in_agent_tool_items(self) -> None:
        """[Edge Case] Both search and attach tools must appear in agent._agent_tool_items after add_tool."""
        agent = BaseAgent(name="a", system_prompt=".")
        agent.add_tool(SearchMcpServersTool())
        agent.add_tool(AttachMcpServerTool())
        names = {t.name for t in agent._agent_tool_items}
        self.assertIn("search_mcp_servers", names)
        self.assertIn("attach_mcp_server", names)


if __name__ == "__main__":
    unittest.main()

