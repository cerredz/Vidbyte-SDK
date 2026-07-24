"""Context Protocol Header

Description:
    Tests MCP server attachment, lifecycle management, and lazy builder execution
    on BaseAgent.
Purpose:
    Verifies that developers can attach single/multiple MCP servers, clean up resources,
    defer subprocess initialization via with_mcp_server, and inspect capability cards.
Architecture:
    - MockMcpStdioTransport: Mocked stdio transport returning custom remote tool specs.
    - McpAttachmentTests: IsolatedAsyncioTestCase containing all scenarios described in the plan.
Relations:
    - vidbyte/agents/mixins.py
    - vidbyte/agents/base.py
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from tests.agent_test_support import build_test_agent
from vidbyte.agents import BaseAgent
from vidbyte.lib.errors import McpAttachmentError, McpInitializeError
from vidbyte.tools.mcp.types import McpServerConfig, McpToolPermission


class MockMcpStdioTransport:
    """Mocked transport class for testing MCP server interaction."""

    instances: list[MockMcpStdioTransport] = []

    def __init__(
        self,
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        request_timeout: float = 30.0,
        shutdown_timeout: float = 5.0,
        stderr_max_bytes: int = 64 * 1024,
        **_: object,
    ) -> None:
        self.command = command
        self.env = env
        self.request_timeout = request_timeout
        self.shutdown_timeout = shutdown_timeout
        self.stderr_max_bytes = stderr_max_bytes
        self.closed = False
        self._started = False
        MockMcpStdioTransport.instances.append(self)

    async def start(self) -> None:
        self._started = True

    async def request(self, method: str, params: dict[str, any] | None = None) -> dict[str, any]:
        if self.closed:
            raise RuntimeError("Transport is closed")
        if self.command[0] == "fail":
            raise RuntimeError("Simulated connection/handshake failure")

        if method == "initialize":
            return {"ok": True}
        elif method == "tools/list":
            return {
                "tools": [
                    {
                        "name": f"remote_{self.command[0]}",
                        "description": f"Mock tool for {self.command[0]}.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string", "description": "input parameter"}
                            },
                        },
                    }
                ]
            }
        elif method == "tools/call":
            return {"content": [{"type": "text", "text": "mocked_response"}]}
        raise ValueError(f"Unknown method {method}")

    async def close(self) -> None:
        self.closed = True


class DoneRunner:
    """Runner that immediately returns an isDone response."""

    async def arun(self, prompt: str, **kwargs: object) -> object:
        class _Resp:
            text = ""
            raw = {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "reply:{prompt}"}}'}]}
        return _Resp()


@patch("vidbyte.tools.mcp.attach.McpStdioTransport", MockMcpStdioTransport)
class McpAttachmentTests(unittest.IsolatedAsyncioTestCase):
    """Covers single-server, concurrent, rollback, lazy connection, and agent card parity."""

    def setUp(self) -> None:
        MockMcpStdioTransport.instances.clear()

    async def test_single_server_async_attach(self) -> None:
        """Verify dynamic tool bridged list mapping and basic handle creation."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner())

        # Assert no servers before attach
        self.assertEqual(len(agent.mcp_servers()), 0)

        # Attach single server
        await agent.attach_mcp_server(command=["myserver"])

        # Check handles and bridged tool list
        self.assertEqual(len(agent.mcp_servers()), 1)
        self.assertEqual(agent.mcp_servers()[0].config.command, ("myserver",))
        self.assertEqual(agent.mcp_tool_names(), ("remote_myserver",))
        self.assertEqual(len(agent.tools), 1)
        self.assertEqual(agent.tools[0].name, "remote_myserver")

        # Clean up
        await agent.close_mcp_servers()
        self.assertEqual(len(agent.mcp_servers()), 0)
        self.assertEqual(len(agent.tools), 0)

    async def test_batch_attach_concurrency_and_fail_safe(self) -> None:
        """Concurrent attachments roll back successfully started servers if one fails."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner())
        configs = [
            McpServerConfig(command=("success1",)),
            McpServerConfig(command=("fail",)),
            McpServerConfig(command=("success2",)),
        ]

        with self.assertRaises(McpAttachmentError):
            await agent.attach_mcp_servers(configs)

        # 3 transports were instantiated
        self.assertEqual(len(MockMcpStdioTransport.instances), 3)

        # Verify that successful ones (success1, success2) were closed automatically during rollback
        for inst in MockMcpStdioTransport.instances:
            if inst.command[0] != "fail":
                self.assertTrue(inst.closed)

        # Verify no tools/handles were registered
        self.assertEqual(len(agent.mcp_servers()), 0)
        self.assertEqual(len(agent.tools), 0)

    async def test_lazy_builder_pattern(self) -> None:
        """Verify that with_mcp_server defers execution until first execution."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner())

        # Register server lazily
        agent.with_mcp_server(command=["lazyserver"])

        # Assert not connected yet
        self.assertEqual(len(agent.mcp_servers()), 0)
        self.assertEqual(len(MockMcpStdioTransport.instances), 0)

        # Run agent execution
        reply = await agent.generate_reply("task-a")
        self.assertIn("task-a", reply.content)

        # Verify connected automatically
        self.assertEqual(len(agent.mcp_servers()), 1)
        self.assertEqual(agent.mcp_servers()[0].config.command, ("lazyserver",))

    async def test_context_manager_cleanup(self) -> None:
        """Verify context manager guarantees cleanup of all subprocess handles."""
        async with build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner()) as agent:
            await agent.attach_mcp_server(command=["ctx-server"])
            self.assertEqual(len(agent.mcp_servers()), 1)
            self.assertFalse(MockMcpStdioTransport.instances[-1].closed)

        # Outside context, should be cleanly closed and removed from self.tools
        self.assertEqual(len(agent.mcp_servers()), 0)
        self.assertTrue(MockMcpStdioTransport.instances[-1].closed)
        self.assertEqual(len(agent.tools), 0)

    async def test_agent_card_mcp_parity(self) -> None:
        """Verify that AgentCard correctly aggregates mcp tool names and server names."""
        agent = build_test_agent(name="card-agent", system_prompt="Work.", runner=DoneRunner())
        await agent.attach_mcp_server(command=["server1"])
        await agent.attach_mcp_server(command=["server2"])

        card = agent.card()
        self.assertEqual(card.mcp_server_names, ("server1", "server2"))
        self.assertEqual(card.mcp_tool_names, ("remote_server1", "remote_server2"))

if __name__ == "__main__":
    unittest.main()
