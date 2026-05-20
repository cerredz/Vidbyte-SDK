"""Context Protocol Header

Description:
    Tests MCP server attachment, lifecycle management, and lazy builder execution
    on BaseAgent and BaseHarness.
Purpose:
    Verifies that developers can attach single/multiple MCP servers, clean up resources,
    defer subprocess initialization via with_mcp_server, and inspect capability cards.
Architecture:
    - MockMcpStdioTransport: Mocked stdio transport returning custom remote tool specs.
    - McpAttachmentTests: IsolatedAsyncioTestCase containing all scenarios described in the plan.
Relations:
    - vidbyte/agents/mixins.py
    - vidbyte/agents/base.py
    - vidbyte/harnesses/base.py
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from vidbyte.agents import BaseAgent
from vidbyte.harnesses import BaseHarness
from vidbyte.lib.errors import McpAttachmentError, McpInitializeError
from vidbyte.strategies import BaseStrategy, StrategyResult, StrategyContext
from vidbyte.tools.mcp.types import McpServerConfig, McpToolPermission


class MockMcpStdioTransport:
    """Mocked transport class for testing MCP server interaction."""

    instances: list[MockMcpStdioTransport] = []

    def __init__(self, command: list[str], *, env: dict[str, str] | None = None) -> None:
        self.command = command
        self.env = env
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


class EchoStrategy(BaseStrategy):
    """Simple strategy that saves tools and context parameters for inspection."""

    name = "echo"

    def __init__(self) -> None:
        self.last_tools = ()
        self.last_context = None

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        self.last_tools = tuple(kwargs.get("tools", ()))
        self.last_context = kwargs.get("context")
        return StrategyResult(output=f"reply:{prompt}", strategy_name=self.name)


@patch("vidbyte.tools.mcp.attach.McpStdioTransport", MockMcpStdioTransport)
class McpAttachmentTests(unittest.IsolatedAsyncioTestCase):
    """Covers single-server, concurrent, rollback, lazy connection, and agent card parity."""

    def setUp(self) -> None:
        MockMcpStdioTransport.instances.clear()

    async def test_single_server_async_attach(self) -> None:
        """Verify dynamic tool bridged list mapping and basic handle creation."""
        agent = BaseAgent(name="worker", strategy=EchoStrategy())

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
        agent = BaseAgent(name="worker", strategy=EchoStrategy())
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
        strategy = EchoStrategy()
        agent = BaseAgent(name="worker", strategy=strategy)

        # Register server lazily
        agent.with_mcp_server(command=["lazyserver"])

        # Assert not connected yet
        self.assertEqual(len(agent.mcp_servers()), 0)
        self.assertEqual(len(MockMcpStdioTransport.instances), 0)

        # Run model/strategy execution
        reply = await agent.generate_reply("task-a")
        self.assertEqual(reply.content, "reply:task-a")

        # Verify connected automatically
        self.assertEqual(len(agent.mcp_servers()), 1)
        self.assertEqual(agent.mcp_servers()[0].config.command, ("lazyserver",))
        self.assertEqual(len(agent.tools), 1)
        self.assertEqual(agent.tools[0].name, "remote_lazyserver")

    async def test_context_manager_cleanup(self) -> None:
        """Verify context manager guarantees cleanup of all subprocess handles."""
        strategy = EchoStrategy()
        async with BaseAgent(name="worker", strategy=strategy) as agent:
            await agent.attach_mcp_server(command=["ctx-server"])
            self.assertEqual(len(agent.mcp_servers()), 1)
            self.assertFalse(MockMcpStdioTransport.instances[-1].closed)

        # Outside context, should be cleanly closed and removed from self.tools
        self.assertEqual(len(agent.mcp_servers()), 0)
        self.assertTrue(MockMcpStdioTransport.instances[-1].closed)
        self.assertEqual(len(agent.tools), 0)

    async def test_agent_card_mcp_parity(self) -> None:
        """Verify that AgentCard correctly aggregates mcp tool names and server names."""
        agent = BaseAgent(name="card-agent", strategy=EchoStrategy())
        await agent.attach_mcp_server(command=["server1"])
        await agent.attach_mcp_server(command=["server2"])

        card = agent.card()
        self.assertEqual(card.mcp_server_names, ("server1", "server2"))
        self.assertEqual(card.mcp_tool_names, ("remote_server1", "remote_server2"))

    async def test_harness_lazy_and_parity(self) -> None:
        """Verify that BaseHarness correctly inherits McpAttachableMixin and connects lazily."""
        strategy = EchoStrategy()
        harness = BaseHarness()
        harness.with_strategy(strategy)
        harness.with_mcp_server(command=["harness-server"])

        # Not started
        self.assertEqual(len(harness.mcp_servers()), 0)

        # Execute
        res = await harness.arun("prompt-msg")
        self.assertEqual(res.output, "reply:prompt-msg")

        # Verify it started
        self.assertEqual(len(harness.mcp_servers()), 1)
        self.assertEqual(harness.mcp_servers()[0].config.command, ("harness-server",))
        self.assertEqual(harness.tools[0].name, "remote_harness-server")
        self.assertEqual(strategy.last_tools[0].name, "remote_harness-server")


if __name__ == "__main__":
    unittest.main()
