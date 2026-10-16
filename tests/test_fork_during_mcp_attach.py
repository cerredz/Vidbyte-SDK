"""FILE: tests/test_fork_during_mcp_attach.py

PURPOSE: Regression tests for a fork taken while its parent is lazily connecting MCP servers.
ROLE IN CODEBASE: Keeps McpAttachableMixin._mcp_configs_for_fork listing the batch a lazy attach is still booting.
ARCHITECTURE NOTE: Replaces attach_mcp_servers with a fake held open on an asyncio.Event; no subprocess is started.
FUNCTION INVENTORY: ForkDuringMcpAttachTests forks mid-attach, then lets the attach finish or fail.
COMMON MODIFICATION PATTERNS: Add a case per attach outcome (success, failure, cancel) a fork must survive.
WHAT NOT TO DO: Do not start real MCP servers or sleep; the gate makes the in-flight window deterministic.
KNOWN EDGE CASES: The batch leaves the pending queue before the servers boot and joins the handles only on success.
RELATED DOCS: vidbyte/agents/README.md
TESTS: Run with python -m pytest -q tests/test_fork_during_mcp_attach.py.
"""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Sequence

from tests.agent_test_support import build_test_agent
from vidbyte.agents import AgentForkSettings, BaseAgent
from vidbyte.tools.mcp.types import McpServerConfig


class _UnusedRunner:
    """Runner placeholder; these tests never run the agent."""


class ForkDuringMcpAttachTests(unittest.IsolatedAsyncioTestCase):
    """A fork taken mid lazy attach inherits the servers that are still connecting."""

    def _agent_held_mid_attach(self, *, fail: bool) -> tuple[BaseAgent, asyncio.Event]:
        # Builds an agent with one queued server whose attach waits on a gate, then connects nothing or fails.
        agent = build_test_agent(name="template", system_prompt="Work.", runner=_UnusedRunner())
        agent.with_mcp_server(command=["slow-server"], name="slow")
        gate = asyncio.Event()

        async def held_attach(servers: Sequence[McpServerConfig]) -> BaseAgent:
            await gate.wait()
            if fail:
                raise RuntimeError("server failed to boot")
            return agent

        agent.attach_mcp_servers = held_attach  # type: ignore[method-assign]
        return agent, gate

    async def _start_attach(self, agent: BaseAgent) -> asyncio.Task[None]:
        # Starts the lazy attach and yields so it takes its batch out of the queue and waits on the gate.
        task = asyncio.ensure_future(agent._ensure_mcp_connected())
        await asyncio.sleep(0)
        self.assertEqual(agent._pending_mcp_configs, [])
        return task

    async def test_fork_mid_attach_inherits_the_connecting_server(self) -> None:
        agent, gate = self._agent_held_mid_attach(fail=False)
        config = agent._pending_mcp_configs[0]
        task = await self._start_attach(agent)

        child = agent.fork(AgentForkSettings(name="child"))
        self.assertEqual(child._pending_mcp_configs, [config])

        gate.set()
        await task
        # The fake connected nothing, so the parent lists the config zero times, never twice.
        self.assertEqual(agent._mcp_configs_for_fork().count(config), 0)
        self.assertEqual(agent._mcp_attaching_configs, ())

    async def test_failed_attach_requeues_its_server_once(self) -> None:
        agent, gate = self._agent_held_mid_attach(fail=True)
        config = agent._pending_mcp_configs[0]
        task = await self._start_attach(agent)

        gate.set()
        with self.assertRaises(RuntimeError):
            await task
        self.assertEqual(agent._pending_mcp_configs, [config])
        self.assertEqual(agent._mcp_configs_for_fork(), (config,))
        self.assertEqual(agent._mcp_attaching_configs, ())


if __name__ == "__main__":
    unittest.main()
