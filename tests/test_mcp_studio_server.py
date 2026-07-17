"""Context Protocol Header

Description:
    Tests the McpStudioServer MCP server lifecycle, tool dispatch, and error handling.
Purpose:
    Verifies that the server correctly handles MCP protocol messages (initialize,
    tools/list, tools/call, prompts/list, prompts/get), validates JSON-RPC error
    responses, and properly executes studio tools against injected agents.
Architecture:
    - Tests call _dispatch directly with parsed request dicts for deterministic results.
    - McpStudioServerTests: IsolatedAsyncioTestCase covering the full protocol.
Relations:
    Related to vidbyte.mcp_server.server, vidbyte.mcp_server.handlers, and
    vidbyte.mcp_server.schema.
"""

from __future__ import annotations

import json
import unittest

from tests.agent_test_support import build_test_agent
from vidbyte.agents import BaseAgent
from vidbyte.mcp_server import McpStudioServer
from vidbyte.mcp_server.server import (
    JSONRPC_METHOD_NOT_FOUND,
)
from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolPermission, ToolResult, ToolSpec


class FakeEchoTool(BaseTool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="echo",
            description="Returns caller arguments.",
            parameters=(),
            permission=ToolPermission.EXECUTE,
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        text = call.arguments.get("text", "")
        return ToolResult.success("echo", f"ECHO: {text}")


class FakeRunner:
    """A fake runner with arun method for BaseAgent to invoke."""
    async def arun(self, message: str, **kwargs: object) -> object:
        return FakeRunnerResult(text=f"ECHO: {message}")


class FakeRunnerResult:
    def __init__(self, text: str) -> None:
        self.text = text


class McpStudioServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        pass

    def _make_agent(self, name: str) -> BaseAgent:
        return build_test_agent(
            name=name,
            system_prompt="You are a test agent.",
            runner=FakeRunner(),
            max_tool_rounds=1,
            max_iterations=1,
        )

    async def _dispatch(self, server: McpStudioServer, method: str, params: dict | None = None, request_id: int = 1) -> dict:
        request: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            request["params"] = params
        return await server._dispatch(request)

    async def test_initialize_handshake(self) -> None:
        server = McpStudioServer()
        response = await self._dispatch(server, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        })
        self.assertIn("result", response)
        self.assertEqual(response["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", response["result"]["capabilities"])
        self.assertEqual(response["result"]["serverInfo"]["name"], "vidbyte-sdk-studio")

    async def test_tools_list_returns_studio_tools(self) -> None:
        server = McpStudioServer(tools=[FakeEchoTool()])
        response = await self._dispatch(server, "tools/list")
        tools = response["result"]["tools"]
        tool_names = {t["name"] for t in tools}
        self.assertIn("studio.agents.list", tool_names)
        self.assertIn("studio.agents.run", tool_names)
        self.assertIn("studio.tools.list", tool_names)
        self.assertIn("studio.strategies.list", tool_names)
        self.assertIn("studio.strategies.run", tool_names)
        self.assertIn("studio.prompts.list", tool_names)
        self.assertIn("studio.prompts.get", tool_names)
        self.assertIn("studio.pipelines.list", tool_names)
        self.assertIn("echo", tool_names)

    async def test_tools_call_agents_list(self) -> None:
        agent = self._make_agent("test-agent")
        server = McpStudioServer(agents={"test-agent": agent})
        response = await self._dispatch(server, "tools/call", {
            "name": "studio.agents.list", "arguments": {},
        })
        self.assertIn("result", response)
        content = response["result"]["content"]
        self.assertEqual(len(content), 1)
        data = json.loads(content[0]["text"])
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "test-agent")

    async def test_tools_call_agents_run(self) -> None:
        agent = self._make_agent("test-agent")
        server = McpStudioServer(agents={"test-agent": agent})
        response = await self._dispatch(server, "tools/call", {
            "name": "studio.agents.run",
            "arguments": {"agent_name": "test-agent", "prompt": "echo hello"},
        })
        self.assertIn("result", response)
        self.assertNotIn("isError", response["result"])

    async def test_tools_call_unknown_agent(self) -> None:
        agent = self._make_agent("test-agent")
        server = McpStudioServer(agents={"test-agent": agent})
        response = await self._dispatch(server, "tools/call", {
            "name": "studio.agents.run",
            "arguments": {"agent_name": "nonexistent", "prompt": "hi"},
        })
        self.assertTrue(response["result"].get("isError", False))

    async def test_tools_call_strategies_list(self) -> None:
        server = McpStudioServer(strategy_names=["chain_of_thought", "react"])
        response = await self._dispatch(server, "tools/call", {
            "name": "studio.strategies.list", "arguments": {},
        })
        content_text = response["result"]["content"][0]["text"]
        data = json.loads(content_text)
        names = {s["name"] for s in data}
        self.assertIn("chain_of_thought", names)
        self.assertIn("react", names)

    async def test_tools_call_echo_tool(self) -> None:
        server = McpStudioServer(tools=[FakeEchoTool()])
        response = await self._dispatch(server, "tools/call", {
            "name": "echo",
            "arguments": {"text": "hello"},
        })
        self.assertIn("result", response)
        content_text = response["result"]["content"][0]["text"]
        self.assertIn("ECHO: hello", content_text)

    async def test_unknown_method_returns_error(self) -> None:
        server = McpStudioServer()
        response = await self._dispatch(server, "bogus/method")
        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], JSONRPC_METHOD_NOT_FOUND)

    async def test_tools_call_unknown_tool(self) -> None:
        server = McpStudioServer()
        response = await self._dispatch(server, "tools/call", {
            "name": "nonexistent_tool", "arguments": {},
        })
        self.assertTrue(response["result"].get("isError", False))

    async def test_prompts_list(self) -> None:
        server = McpStudioServer()
        response = await self._dispatch(server, "prompts/list")
        self.assertIn("result", response)
        self.assertIn("prompts", response["result"])

    async def test_prompts_get(self) -> None:
        server = McpStudioServer(prompt_content={"greeting": "Hello, world!"})
        response = await self._dispatch(server, "prompts/get", {"name": "greeting"})
        self.assertIn("result", response)
        messages = response["result"]["messages"]
        self.assertGreater(len(messages), 0)
        self.assertEqual(messages[0]["content"]["text"], "Hello, world!")

    async def test_pipelines_list(self) -> None:
        server = McpStudioServer(pipeline_names=["sequential", "parallel", "map_reduce"])
        response = await self._dispatch(server, "tools/call", {
            "name": "studio.pipelines.list", "arguments": {},
        })
        content_text = response["result"]["content"][0]["text"]
        data = json.loads(content_text)
        names = {p["name"] for p in data}
        self.assertIn("sequential", names)
        self.assertIn("parallel", names)
        self.assertIn("map_reduce", names)

    async def test_agents_list_with_filter(self) -> None:
        agent_a = self._make_agent("agent-alpha")
        agent_b = self._make_agent("agent-beta")
        server = McpStudioServer(agents={
            "agent-alpha": agent_a,
            "agent-beta": agent_b,
        })
        response = await self._dispatch(server, "tools/call", {
            "name": "studio.agents.list",
            "arguments": {"filter_name": "alpha"},
        })
        content_text = response["result"]["content"][0]["text"]
        data = json.loads(content_text)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "agent-alpha")

    async def test_server_close_sets_shutdown_flag(self) -> None:
        server = McpStudioServer()
        self.assertFalse(server._shutdown)
        await server.close()
        self.assertTrue(server._shutdown)


if __name__ == "__main__":
    unittest.main()
