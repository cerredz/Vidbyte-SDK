"""Context Protocol Header

Description:
    Verification script for Asynchronous Actor Model Runtime.
Purpose:
    Executes and validates all redesigned actor runtime test cases described in the design
    doc, ensuring strict fail-fast validation, routing topologies, dynamic spawning,
    and termination safeguards.
Architecture:
    Independent Python test script utilizing unittest assertions to verify components.
Relations:
    Located in scripts/. Used to certify PR readiness in Phase 5.
Similar Files:
    - scripts/test-non-linear-agent-runtimes.py: Previous stubs validator.
"""

from __future__ import annotations
import asyncio
import sys
import unittest
from typing import Any, Mapping

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.enums import AgentRuntimeType
from vidbyte.lib.errors import ConfigurationError
from vidbyte.agents.runtimes.actor.broker import PointToPointActorRuntime, BroadcastActorRuntime
from vidbyte.agents.runtimes.actor.actor import AgentActor
from vidbyte.agents.runtimes.actor.message import ActorMessage
from vidbyte.tools.dynamic_actor import DynamicActorTool
from vidbyte.tools.catalog import Tools
from vidbyte.tools.types import ToolCall


class MockRunner:
    """Mock runner simulating LLM responses."""
    def __init__(self, reply: str = "Test response") -> None:
        self.reply = reply


async def mock_invoke_runner(runner: Any, prompt: str, **kwargs: Any) -> MockRunner:
    return MockRunner(reply=f"Response to: {prompt[:30]}")


def mock_runner_output_text(raw_result: Any) -> str:
    return getattr(raw_result, "reply", "Success")


def mock_runner_output_metadata(raw_result: Any) -> Mapping[str, Any]:
    return {}


class TestActorModelRuntimeRedesign(unittest.IsolatedAsyncioTestCase):
    """Exhaustive test suite verifying the Asynchronous Actor Model Runtime redesign."""

    async def test_middleware_and_algorithms_fail_fast(self) -> None:
        # [Hidden Failure] Verifies that custom middleware or algorithms raise ConfigurationError.
        class DummyMiddleware:
            pass

        with self.assertRaises(ConfigurationError) as ctx:
            BaseAgent(
                name="bad_agent",
                system_prompt="Helpful",
                runtime=AgentRuntimeType.ACTOR_MODEL_P2P,
                middleware=[DummyMiddleware()],
            )
        self.assertIn("does not support middleware", str(ctx.exception))

    async def test_p2p_broker_message_routing(self) -> None:
        # [Edge Case] Verify that a P2P broker delivers messages strictly to the designated actor's inbox.
        broker = PointToPointActorRuntime(
            agent_name="coordinator",
            system_prompt="Helpful",
            tools=Tools(),
            permission_policy=None,
        )

        actor1 = await broker.spawn("actor_1", "System prompt 1")
        actor2 = await broker.spawn("actor_2", "System prompt 2")

        await broker.send("coordinator", "actor_1", "Message to actor 1")

        # Verify actor1 inbox got the message
        self.assertFalse(actor1.inbox.empty())
        msg = await actor1.inbox.get()
        self.assertEqual(msg.content, "Message to actor 1")
        self.assertEqual(msg.sender, "coordinator")

        # Verify actor2 inbox remains empty
        self.assertTrue(actor2.inbox.empty())

        # Clean up background tasks
        for task in broker._tasks:
            task.cancel()

    async def test_broadcast_broker_message_replication(self) -> None:
        # [Edge Case] Verify that a broadcast broker replicates and delivers messages to all active actor inboxes.
        broker = BroadcastActorRuntime(
            agent_name="coordinator",
            system_prompt="Helpful",
            tools=Tools(),
            permission_policy=None,
        )

        actor1 = await broker.spawn("actor_1", "System prompt 1")
        actor2 = await broker.spawn("actor_2", "System prompt 2")

        await broker.send("coordinator", "all", "Broadcast to all")

        # Both actors should receive the message
        self.assertFalse(actor1.inbox.empty())
        self.assertFalse(actor2.inbox.empty())

        msg1 = await actor1.inbox.get()
        msg2 = await actor2.inbox.get()

        self.assertEqual(msg1.content, "Broadcast to all")
        self.assertEqual(msg2.content, "Broadcast to all")

        # Clean up background tasks
        for task in broker._tasks:
            task.cancel()

    async def test_max_loop_budget_forcing(self) -> None:
        # [Hidden Failure] Verify that executing messages past max_loop forces termination.
        broker = PointToPointActorRuntime(
            agent_name="coordinator",
            system_prompt="Helpful",
            tools=Tools(),
            permission_policy=None,
            max_loop=3,
        )
        broker._completion_future = asyncio.get_running_loop().create_future()

        # Send 3 messages sequentially
        await broker.send("system", "coordinator", "Msg 1")
        await broker.send("system", "coordinator", "Msg 2")
        await broker.send("system", "coordinator", "Msg 3")

        self.assertTrue(broker._completion_future.done())
        result = broker._completion_future.result()
        self.assertIn("Max loops (3) reached", result)

    async def test_coordinator_termination_trigger(self) -> None:
        # [Silent Failure] Verify that coordinator mode terminates immediately upon coordinator final reply.
        broker = PointToPointActorRuntime(
            agent_name="coordinator",
            system_prompt="Helpful",
            tools=Tools(),
            permission_policy=None,
            termination_mode="coordinator",
        )
        broker._completion_future = asyncio.get_running_loop().create_future()

        # Sending a message to "system" from a worker represents task completion
        await broker.send("planner", "system", "Planner final result")

        self.assertTrue(broker._completion_future.done())
        self.assertEqual(broker._completion_future.result(), "Planner final result")

    async def test_worker_model_runner_resolution(self) -> None:
        # [Hidden Assumption] Verify worker actor resolves specialized worker_model configurations.
        broker = PointToPointActorRuntime(
            agent_name="coordinator",
            system_prompt="Helpful",
            tools=Tools(),
            permission_policy=None,
            worker_model="gpt-4o-mini",
        )
        broker._runner = MockRunner()
        broker._invoke_runner = mock_invoke_runner
        broker._runner_output_text = mock_runner_output_text
        broker._options = {"temperature": 0.5}

        # Actor without model_name override resolves to broker's worker_model
        actor = AgentActor(actor_id="actor_1", system_prompt="Tester", broker=broker)
        
        # Capture raw invoke_runner behavior
        async def capture_invoke(runner: Any, prompt: str, **kwargs: Any) -> MockRunner:
            self.assertEqual(kwargs.get("model_name"), "gpt-4o-mini")
            self.assertEqual(kwargs.get("temperature"), 0.5)
            return MockRunner(reply="Resolution check pass")

        broker._invoke_runner = capture_invoke
        reply = await actor.on_receive(ActorMessage(message_id="1", sender="system", recipient="actor_1", content="Hello"))
        self.assertEqual(reply, "Resolution check pass")

    async def test_dynamic_actor_spawning_via_tool(self) -> None:
        # [Hidden Assumption] Verify DynamicActorTool registers and instantiates dynamic actors in the broker.
        broker = PointToPointActorRuntime(
            agent_name="coordinator",
            system_prompt="Helpful",
            tools=Tools(),
            permission_policy=None,
        )
        tool = DynamicActorTool(broker)

        # Call spawn_actor tool
        call = ToolCall(
            call_id="c1",
            tool_name="spawn_actor",
            arguments={"actor_name": "regex_parser", "system_prompt": "Sanitize input", "model_name": "gpt-3.5-turbo"},
        )
        result = await tool.execute(call)
        
        self.assertEqual(result.status.value, "success")
        self.assertIn("regex_parser", broker._actors)
        
        actor = broker._actors["regex_parser"]
        self.assertEqual(actor.system_prompt, "Sanitize input")
        self.assertEqual(actor.model_name, "gpt-3.5-turbo")

        # Clean up background tasks
        for task in broker._tasks:
            task.cancel()


def main() -> None:
    # Run the test suite synchronously
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestActorModelRuntimeRedesign)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
