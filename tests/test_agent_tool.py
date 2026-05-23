"""Tests for AgentTool and BaseAgent.as_tool()."""

from __future__ import annotations

import unittest

from vidbyte.agents.base import BaseAgent
from vidbyte.strategies.base import BaseStrategy, StrategyResult
from vidbyte.tools.agent_tool import AgentTool
from vidbyte.tools.types import ToolCall, ToolPermission


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeRunner:
    """Minimal runner that echoes the message without calling any model API."""

    async def arun(self, message: str, **kwargs: object) -> _FakeResult:
        return _FakeResult(f"reply: {message}")


class FakeStrategy(BaseStrategy):
    name = "fake"

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=f"strategy: {prompt}", strategy_name=self.name)


def _make_agent(name: str = "worker", strategy: BaseStrategy | None = None) -> BaseAgent:
    return BaseAgent(
        name=name,
        system_prompt="You are a helpful assistant.",
        runner=FakeRunner(),
        strategy=strategy,
        description="A test agent.",
    )


class AgentToolSpecTests(unittest.TestCase):
    def test_spec_name_defaults_to_agent_name(self) -> None:
        agent = _make_agent("alpha")
        tool = AgentTool(agent)
        self.assertEqual(tool.spec().name, "alpha")

    def test_spec_name_override(self) -> None:
        agent = _make_agent("alpha")
        tool = AgentTool(agent, name="custom_name")
        self.assertEqual(tool.spec().name, "custom_name")

    def test_spec_description_defaults_to_agent_description(self) -> None:
        agent = _make_agent()
        tool = AgentTool(agent)
        self.assertEqual(tool.spec().description, "A test agent.")

    def test_spec_description_override(self) -> None:
        agent = _make_agent()
        tool = AgentTool(agent, description="overridden")
        self.assertEqual(tool.spec().description, "overridden")

    def test_spec_has_three_parameters(self) -> None:
        tool = AgentTool(_make_agent())
        params = {p.name: p for p in tool.spec().parameters}
        self.assertIn("message", params)
        self.assertIn("recipient", params)
        self.assertIn("modality", params)

    def test_message_parameter_is_required(self) -> None:
        tool = AgentTool(_make_agent())
        params = {p.name: p for p in tool.spec().parameters}
        self.assertTrue(params["message"].required)

    def test_recipient_and_modality_are_optional(self) -> None:
        tool = AgentTool(_make_agent())
        params = {p.name: p for p in tool.spec().parameters}
        self.assertFalse(params["recipient"].required)
        self.assertFalse(params["modality"].required)

    def test_spec_permission_is_safe(self) -> None:
        tool = AgentTool(_make_agent())
        self.assertEqual(tool.spec().permission, ToolPermission.SAFE)

    def test_name_property_matches_spec(self) -> None:
        tool = AgentTool(_make_agent("bravo"))
        self.assertEqual(tool.name, "bravo")


class AgentToolExecuteTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_returns_success_with_agent_reply(self) -> None:
        tool = AgentTool(_make_agent())
        result = await tool.execute(ToolCall("worker", {"message": "hello"}))
        self.assertEqual(result.status.value, "success")
        self.assertIn("hello", result.output)

    async def test_execute_passes_recipient_through(self) -> None:
        tool = AgentTool(_make_agent())
        result = await tool.execute(ToolCall("worker", {"message": "hi", "recipient": "planner"}))
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.metadata.get("recipient"), "planner")

    async def test_execute_auto_modality_maps_to_none(self) -> None:
        # "auto" should not cause an error — it maps to None internally
        tool = AgentTool(_make_agent())
        result = await tool.execute(ToolCall("worker", {"message": "test", "modality": "auto"}))
        self.assertEqual(result.status.value, "success")

    async def test_execute_explicit_modality_passes_through(self) -> None:
        tool = AgentTool(_make_agent())
        result = await tool.execute(ToolCall("worker", {"message": "test", "modality": "text"}))
        self.assertEqual(result.status.value, "success")

    async def test_execute_returns_failure_on_agent_error(self) -> None:
        class BrokenRunner:
            async def arun(self, *args: object, **kwargs: object) -> object:
                raise RuntimeError("runner failed")

        agent = BaseAgent(
            name="broken",
            system_prompt="broken",
            runner=BrokenRunner(),
        )
        tool = AgentTool(agent)
        result = await tool.execute(ToolCall("broken", {"message": "anything"}))
        self.assertEqual(result.status.value, "error")
        # AgentExecutionError wraps the inner error — just verify it's a failure with agent context
        self.assertIn("broken", result.metadata.get("agent_name", ""))

    async def test_execute_isolates_history_across_calls(self) -> None:
        agent = _make_agent()
        tool = AgentTool(agent)
        initial_history_len = len(agent.history)

        await tool.execute(ToolCall("worker", {"message": "first"}))
        await tool.execute(ToolCall("worker", {"message": "second"}))

        # Original agent's history must not grow — fork() isolates each call
        self.assertEqual(len(agent.history), initial_history_len)

    async def test_execute_metadata_contains_agent_name(self) -> None:
        tool = AgentTool(_make_agent("named_agent"))
        result = await tool.execute(ToolCall("named_agent", {"message": "ping"}))
        self.assertEqual(result.metadata.get("agent_name"), "named_agent")


class BaseAgentAsToolTests(unittest.TestCase):
    def test_as_tool_returns_agent_tool_instance(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool()
        self.assertIsInstance(tool, AgentTool)

    def test_as_tool_name_defaults_to_agent_name(self) -> None:
        agent = _make_agent("my_agent")
        tool = agent.as_tool()
        self.assertEqual(tool.spec().name, "my_agent")

    def test_as_tool_name_override(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool(name="overridden_name")
        self.assertEqual(tool.spec().name, "overridden_name")

    def test_as_tool_description_override(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool(description="custom description")
        self.assertEqual(tool.spec().description, "custom description")

    def test_as_tool_wraps_same_agent(self) -> None:
        agent = _make_agent()
        tool = agent.as_tool()
        self.assertIs(tool._agent, agent)


if __name__ == "__main__":
    unittest.main()
