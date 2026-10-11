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
    - LoopBoundMcpTransport / SyncRunMcpLoopTests: a transport that only works on the loop it
      started on, proving sync run() and pipeline run_sync() reconnect instead of reusing a closed
      loop's pipes, while one long-lived loop keeps its connection.
    - GatedMcpTransport / OverlappingLazyAttachTests: an attach held open by a gate, proving overlapping
      first runs on one agent wait for the in-flight lazy attach and all see its tools, and that a run
      cancelled mid-attach re-queues its servers (closing any it started) so a later run attaches them.
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
from vidbyte.pipelines import SequentialPipeline
from vidbyte.tools import ToolCall, ToolPermission, Tools
from vidbyte.tools.executor import ToolExecutor
from vidbyte.tools.mcp.types import McpServerConfig, McpToolPermission
from vidbyte.tools.security import PermissionPolicy


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
        self.methods: list[str] = []
        MockMcpStdioTransport.instances.append(self)

    async def start(self) -> None:
        self._started = True

    async def request(self, method: str, params: dict[str, any] | None = None) -> dict[str, any]:
        self.methods.append(method)
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

    async def test_close_drops_bridged_tools_from_agent_tool_items(self) -> None:
        """Closed MCP tools must not linger in the agent tool list, forks, or exported state."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner())
        await agent.attach_mcp_server(command=["closer"])
        bridged = agent.mcp_servers()[0].bridged_tools
        self.assertTrue(bridged)
        self.assertTrue(all(any(t is b for t in agent._agent_tool_items) for b in bridged))

        await agent.close_mcp_servers()

        self.assertFalse(any(t is b for t in agent._agent_tool_items for b in bridged))
        child = agent.fork()
        self.assertFalse(any(t is b for t in child._agent_tool_items for b in bridged))
        self.assertNotIn("remote_closer", agent.export_state().tool_names)

    async def test_disabled_server_exposes_no_runnable_tools(self) -> None:
        """A DISABLED server bridges nothing, so its tool cannot run even under allow_all."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner())
        await agent.attach_mcp_server(command=["off"], permission=McpToolPermission.DISABLED)
        await agent.attach_mcp_server(command=["ro"], permission=McpToolPermission.READONLY)
        await agent.attach_mcp_server(command=["rw"], permission=McpToolPermission.EXECUTE)
        disabled, readonly, execute = agent.mcp_servers()

        # The disabled server stays attached but contributes no tools anywhere the model looks.
        self.assertEqual(disabled.bridged_tools, ())
        self.assertEqual(agent.mcp_tool_names(), ("remote_ro", "remote_rw"))
        self.assertNotIn("remote_off", [tool.name for tool in agent.tools])
        self.assertEqual(readonly.bridged_tools[0].spec().permission, ToolPermission.READ)
        self.assertEqual(execute.bridged_tools[0].spec().permission, ToolPermission.EXECUTE)

        # Even a policy that allows every risk level cannot reach the disabled server's tool.
        allow_all = ToolExecutor(Tools(agent.tools), permission_policy=PermissionPolicy.allow_all())
        blocked = await allow_all.execute_call(ToolCall("remote_off", {"text": "hi"}))
        self.assertEqual(blocked.metadata.get("error"), "unknown_tool")
        self.assertNotIn("tools/call", disabled.transport.methods)
        for name in ("remote_ro", "remote_rw"):
            result = await allow_all.execute_call(ToolCall(name, {"text": "hi"}))
            self.assertEqual(result.output, "mocked_response")

        # The default policy still runs readonly tools and denies execute tools, as before.
        default = ToolExecutor(Tools(agent.tools))
        self.assertEqual((await default.execute_call(ToolCall("remote_ro", {"text": "hi"}))).output, "mocked_response")
        denied = await default.execute_call(ToolCall("remote_rw", {"text": "hi"}))
        self.assertEqual(denied.metadata.get("error"), "permission_denied")

        await agent.close_mcp_servers()
        self.assertTrue(disabled.transport.closed)

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

    async def test_bare_string_command_is_refused_instead_of_split_into_characters(self) -> None:
        """A bare-string command raises a clear error rather than spawning its first character."""
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=DoneRunner())

        with self.assertRaisesRegex(ValueError, r"list of program arguments .* not a single string"):
            agent.with_mcp_server("server")
        self.assertEqual(agent._pending_mcp_configs, [])
        with self.assertRaisesRegex(ValueError, r"list of program arguments .* not a single string"):
            await agent.attach_mcp_server("server")
        self.assertEqual(len(MockMcpStdioTransport.instances), 0)

        # The list form is still accepted and stored as one argument.
        agent.with_mcp_server(["server"])
        self.assertEqual(agent._pending_mcp_configs[0].command, ("server",))

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

class LoopBoundMcpTransport(MockMcpStdioTransport):
    """Mock transport that, like real subprocess pipes, only works on the loop it started on."""

    served_calls: list[asyncio.AbstractEventLoop] = []

    def __init__(self, command: list[str], **options: object) -> None:
        super().__init__(command, **options)
        # Real pipes are created on, and stay bound to, the loop that opens them.
        self.loop = asyncio.get_running_loop()
        self.abandoned = False

    def is_bound_to_running_loop(self) -> bool:
        return asyncio.get_running_loop() is self.loop and not self.loop.is_closed()

    def abandon(self) -> None:
        self.abandoned = True
        self.closed = True

    async def request(self, method: str, params: dict[str, any] | None = None) -> dict[str, any]:
        if asyncio.get_running_loop() is not self.loop or self.loop.is_closed():
            raise RuntimeError("'NoneType' object has no attribute 'send'")
        result = await super().request(method, params)
        if method == "tools/call":
            LoopBoundMcpTransport.served_calls.append(self.loop)
        return result


class McpThenDoneRunner:
    """Runner that calls the MCP tool once per run, then finishes."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        self.turn = 0

    async def arun(self, prompt: str, **kwargs: object) -> object:
        self.turn += 1
        if self.turn % 2:
            item = {"type": "function_call", "name": self.tool_name, "arguments": '{"text": "hi"}', "call_id": f"call_{self.turn}"}
        else:
            item = {"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": f"call_{self.turn}"}
        return type("_Resp", (), {"text": "", "raw": {"output": [item]}})()


@patch("vidbyte.tools.mcp.attach.McpStdioTransport", LoopBoundMcpTransport)
class SyncRunMcpLoopTests(unittest.TestCase):
    """Sync run() owns a fresh event loop per call, so MCP servers must not outlive it."""

    def setUp(self) -> None:
        MockMcpStdioTransport.instances.clear()
        LoopBoundMcpTransport.served_calls.clear()

    def test_consecutive_sync_runs_each_reach_the_mcp_tool(self) -> None:
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=McpThenDoneRunner("remote_mini"))
        agent.with_mcp_server(command=["mini"], permission=McpToolPermission.READONLY)
        config = agent._pending_mcp_configs[0]

        agent.run("question 1")
        agent.run("question 2")

        # Each run connected its own server on its own loop and the tool call succeeded there.
        first, second = MockMcpStdioTransport.instances
        self.assertEqual(LoopBoundMcpTransport.served_calls, [first.loop, second.loop])
        self.assertIsNot(first.loop, second.loop)
        # Nothing is left running, no stale tools remain, and the server waits to reconnect.
        self.assertTrue(first.closed and second.closed)
        self.assertEqual(agent.mcp_servers(), ())
        self.assertNotIn("remote_mini", [tool.name for tool in agent.tools])
        self.assertEqual(agent._pending_mcp_configs, [config])

    def test_pipeline_run_sync_twice_reconnects_the_mcp_server_on_each_loop(self) -> None:
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=McpThenDoneRunner("remote_mini"))
        agent.with_mcp_server(command=["mini"], permission=McpToolPermission.READONLY)
        config = agent._pending_mcp_configs[0]
        pipeline = SequentialPipeline([agent])

        pipeline.run_sync("batch 1")
        pipeline.run_sync("batch 2")

        # Each batch connected its own server on its own loop and closed it before that loop ended.
        first, second = MockMcpStdioTransport.instances
        self.assertEqual(LoopBoundMcpTransport.served_calls, [first.loop, second.loop])
        self.assertIsNot(first.loop, second.loop)
        self.assertTrue(first.closed and second.closed)
        self.assertFalse(first.abandoned or second.abandoned)
        # Nothing is left running, no stale tools remain, and the server waits to reconnect.
        self.assertEqual(agent.mcp_servers(), ())
        self.assertNotIn("remote_mini", [tool.name for tool in agent.tools])
        self.assertEqual(agent._pending_mcp_configs, [config])

    def test_async_runs_on_one_loop_keep_their_mcp_connection(self) -> None:
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=McpThenDoneRunner("remote_mini"))
        agent.with_mcp_server(command=["mini"], permission=McpToolPermission.READONLY)

        async def run_twice() -> None:
            await agent.arun("question 1")
            await agent.arun("question 2")

        asyncio.run(run_twice())

        # One long-lived loop connects once and reuses the same server for both runs.
        (only,) = MockMcpStdioTransport.instances
        self.assertEqual(LoopBoundMcpTransport.served_calls, [only.loop, only.loop])
        self.assertFalse(only.abandoned)


class GatedMcpTransport(MockMcpStdioTransport):
    """Mock transport whose initialize handshake blocks on a gate, like a slow server booting."""

    gate: asyncio.Event

    async def request(self, method: str, params: dict[str, any] | None = None) -> dict[str, any]:
        # The client never calls start() on its own, so hold the handshake itself open.
        # An "ungated" server answers at once, so a batch can hold one started server while another waits.
        if method == "initialize" and self.command[0] != "ungated":
            await GatedMcpTransport.gate.wait()
        return await super().request(method, params)


class ToolsOfferedRunner:
    """Runner that records the tools offered to each run's first model call, then finishes."""

    def __init__(self) -> None:
        self.offered: dict[str, tuple[str, ...]] = {}

    async def arun(self, prompt: str, **kwargs: object) -> object:
        tools = kwargs.get("tools") or ()
        self.offered.setdefault(prompt, tuple(spec["function"]["name"] for spec in tools))
        item = {"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "done"}', "call_id": f"call_{prompt}"}
        return type("_Resp", (), {"text": "", "raw": {"output": [item]}})()


@patch("vidbyte.tools.mcp.attach.McpStdioTransport", GatedMcpTransport)
class OverlappingLazyAttachTests(unittest.IsolatedAsyncioTestCase):
    """Overlapping runs on one agent must not skip a lazy MCP attach another run has in flight."""

    async def asyncSetUp(self) -> None:
        MockMcpStdioTransport.instances.clear()
        GatedMcpTransport.gate = asyncio.Event()

    async def _overlap_two_runs(self, agent: BaseAgent) -> list[object]:
        # Start run 1 and hold its attach open, then start run 2 while that attach is still in flight.
        first = asyncio.ensure_future(agent.arun("request 1"))
        while not MockMcpStdioTransport.instances:
            await asyncio.sleep(0)
        second = asyncio.ensure_future(agent.arun("request 2"))
        for _ in range(20):
            await asyncio.sleep(0)
        GatedMcpTransport.gate.set()
        return await asyncio.gather(first, second, return_exceptions=True)

    async def test_overlapping_first_runs_both_see_the_lazily_attached_tool(self) -> None:
        runner = ToolsOfferedRunner()
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner)
        agent.with_mcp_server(command=["mini"], permission=McpToolPermission.READONLY)

        results = await self._overlap_two_runs(agent)

        self.assertFalse([r for r in results if isinstance(r, BaseException)])
        # The server was attached exactly once, and both runs were offered its tool.
        self.assertEqual(len(MockMcpStdioTransport.instances), 1)
        self.assertEqual({prompt: "remote_mini" in names for prompt, names in runner.offered.items()}, {"request 1": True, "request 2": True})
        self.assertEqual(agent._pending_mcp_configs, [])
        self.assertIsNone(agent._mcp_attach_in_flight)

    async def test_overlapping_run_retries_after_the_in_flight_attach_fails(self) -> None:
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=ToolsOfferedRunner())
        agent.with_mcp_server(command=["fail"])
        config = agent._pending_mcp_configs[0]

        results = await self._overlap_two_runs(agent)

        # Each run surfaces an attach failure: the waiting run retried once the first attach failed.
        self.assertTrue(all(isinstance(r, McpAttachmentError) for r in results))
        self.assertEqual(len(MockMcpStdioTransport.instances), 2)
        self.assertEqual(agent._pending_mcp_configs, [config])
        self.assertIsNone(agent._mcp_attach_in_flight)

    async def test_cancelled_attach_requeues_its_servers_for_the_next_run(self) -> None:
        runner = ToolsOfferedRunner()
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner)
        agent.with_mcp_server(command=["ungated"], permission=McpToolPermission.READONLY)
        agent.with_mcp_server(command=["mini"], permission=McpToolPermission.READONLY)
        configs = list(agent._pending_mcp_configs)

        # Cancel the first run while "mini" is still starting and "ungated" has already started.
        first = asyncio.ensure_future(agent.arun("request 1"))
        while len(MockMcpStdioTransport.instances) < 2:
            await asyncio.sleep(0)
        for _ in range(20):
            await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first

        # Both servers wait to connect again in order, none is attached, and nothing started is left running.
        self.assertEqual(agent._pending_mcp_configs, configs)
        self.assertEqual(agent.mcp_servers(), ())
        self.assertIsNone(agent._mcp_attach_in_flight)
        self.assertTrue(all(inst.closed for inst in MockMcpStdioTransport.instances))

        # A later run attaches both servers and is offered their tools.
        GatedMcpTransport.gate.set()
        await agent.arun("request 2")
        self.assertEqual([handle.config for handle in agent.mcp_servers()], configs)
        self.assertEqual(agent._pending_mcp_configs, [])
        self.assertTrue({"remote_ungated", "remote_mini"} <= set(runner.offered["request 2"]))

    async def test_waiting_run_attaches_after_the_in_flight_attach_is_cancelled(self) -> None:
        runner = ToolsOfferedRunner()
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner)
        agent.with_mcp_server(command=["mini"], permission=McpToolPermission.READONLY)

        # Run 2 waits on run 1's attach; run 1 is cancelled before the server finishes starting.
        first = asyncio.ensure_future(agent.arun("request 1"))
        while not MockMcpStdioTransport.instances:
            await asyncio.sleep(0)
        second = asyncio.ensure_future(agent.arun("request 2"))
        for _ in range(20):
            await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        GatedMcpTransport.gate.set()
        await second

        # The waiting run picked up the re-queued server, attached it, and was offered its tool.
        self.assertEqual(len(agent.mcp_servers()), 1)
        self.assertEqual(agent._pending_mcp_configs, [])
        self.assertIn("remote_mini", runner.offered["request 2"])

    async def test_sequential_first_runs_still_attach_once(self) -> None:
        GatedMcpTransport.gate.set()
        runner = ToolsOfferedRunner()
        agent = build_test_agent(name="worker", system_prompt="Work.", runner=runner)
        agent.with_mcp_server(command=["mini"], permission=McpToolPermission.READONLY)

        await agent.arun("request 1")
        await agent.arun("request 2")

        self.assertEqual(len(MockMcpStdioTransport.instances), 1)
        self.assertEqual({prompt: "remote_mini" in names for prompt, names in runner.offered.items()}, {"request 1": True, "request 2": True})


if __name__ == "__main__":
    unittest.main()
