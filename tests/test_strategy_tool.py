"""Tests for StrategyTool and BaseStrategy.as_tool()."""

from __future__ import annotations

import unittest

from vidbyte.agents.base import BaseAgent
from vidbyte.lib.dataclasses.agents import AgentMetadata
from vidbyte.lib.errors import AgentExecutionError
from vidbyte.strategies.base import BaseStrategy, StrategyResult
from vidbyte.tools.strategy_tool import StrategyTool
from vidbyte.tools.types import ToolCall, ToolPermission


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeRunner:
    """Minimal runner that echoes without calling a real model API."""

    async def arun(self, message: str, **kwargs: object) -> _FakeResult:
        return _FakeResult(f"reply: {message}")


class EchoStrategy(BaseStrategy):
    name = "echo"
    description = "Echoes the prompt back."

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=f"echo: {prompt}", strategy_name=self.name)


class ErrorStrategy(BaseStrategy):
    name = "error_strategy"

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        raise RuntimeError("strategy exploded")


def _make_agent(strategy: BaseStrategy | None = None) -> BaseAgent:
    return BaseAgent(
        name="worker",
        system_prompt="You are a helpful assistant.",
        runner=FakeRunner(),
        strategy=strategy,
        description="A test agent.",
    )


class StrategyToolInitTests(unittest.TestCase):
    def test_raises_when_agent_has_no_strategy(self) -> None:
        agent = _make_agent(strategy=None)
        with self.assertRaises(AgentExecutionError):
            StrategyTool(agent)

    def test_accepts_agent_with_strategy(self) -> None:
        agent = _make_agent(strategy=EchoStrategy())
        tool = StrategyTool(agent)
        self.assertIsInstance(tool, StrategyTool)


class StrategyToolSpecTests(unittest.TestCase):
    def _tool(self, **kwargs: object) -> StrategyTool:
        return StrategyTool(_make_agent(strategy=EchoStrategy()), **kwargs)  # type: ignore[arg-type]

    def test_spec_has_zero_parameters(self) -> None:
        tool = self._tool()
        self.assertEqual(tool.spec().parameters, ())

    def test_spec_name_defaults_to_agent_name_strategy(self) -> None:
        tool = self._tool()
        self.assertEqual(tool.spec().name, "worker_strategy")

    def test_spec_name_override(self) -> None:
        tool = self._tool(name="custom_strategy")
        self.assertEqual(tool.spec().name, "custom_strategy")

    def test_spec_description_uses_strategy_description(self) -> None:
        tool = self._tool()
        self.assertEqual(tool.spec().description, "Echoes the prompt back.")

    def test_spec_description_override(self) -> None:
        tool = self._tool(description="custom desc")
        self.assertEqual(tool.spec().description, "custom desc")

    def test_spec_permission_is_safe(self) -> None:
        tool = self._tool()
        self.assertEqual(tool.spec().permission, ToolPermission.SAFE)

    def test_name_property_matches_spec(self) -> None:
        tool = self._tool()
        self.assertEqual(tool.name, "worker_strategy")

    def test_metadata_contains_strategy_and_agent_names(self) -> None:
        tool = self._tool()
        self.assertEqual(tool.spec().metadata.get("strategy_name"), "echo")
        self.assertEqual(tool.spec().metadata.get("agent_name"), "worker")


class StrategyToolExecuteTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_returns_strategy_output(self) -> None:
        agent = _make_agent(strategy=EchoStrategy())
        tool = StrategyTool(agent)
        result = await tool.execute(ToolCall("worker_strategy", {}))
        self.assertEqual(result.status.value, "success")
        self.assertIn("echo:", result.output)

    async def test_execute_with_context_getter_passes_context_to_strategy(self) -> None:
        captured: list[str] = []

        class CapturingStrategy(BaseStrategy):
            name = "capturing"
            description = "Captures the prompt."

            async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
                captured.append(prompt)
                return StrategyResult(output="captured", strategy_name=self.name)

        agent = _make_agent(strategy=CapturingStrategy())
        tool = StrategyTool(agent)
        tool.bind_context_getter(lambda: ("my request", []))
        await tool.execute(ToolCall("worker_strategy", {}))

        self.assertEqual(len(captured), 1)
        self.assertIn("my request", captured[0])

    async def test_execute_metadata_contains_strategy_name(self) -> None:
        agent = _make_agent(strategy=EchoStrategy())
        tool = StrategyTool(agent)
        result = await tool.execute(ToolCall("worker_strategy", {}))
        self.assertEqual(result.metadata.get("strategy_name"), "echo")

    async def test_execute_returns_failure_on_strategy_error(self) -> None:
        agent = _make_agent(strategy=ErrorStrategy())
        tool = StrategyTool(agent)
        result = await tool.execute(ToolCall("worker_strategy", {}))
        self.assertEqual(result.status.value, "error")
        self.assertIn("strategy exploded", result.output)

    async def test_execute_returns_failure_when_no_real_runner(self) -> None:
        from vidbyte.agents.base import ConfiguredAgentRunner
        from vidbyte.lib.dataclasses.agents import AgentRunnerConfig

        agent = BaseAgent(
            name="no_runner",
            system_prompt="test",
            strategy=EchoStrategy(),
        )
        agent.runner = ConfiguredAgentRunner(AgentRunnerConfig())
        tool = StrategyTool(agent)
        result = await tool.execute(ToolCall("no_runner_strategy", {}))
        self.assertEqual(result.status.value, "error")
        self.assertIn("no real runner", result.output.lower())


class BaseStrategyAsToolTests(unittest.TestCase):
    def test_as_tool_returns_strategy_tool_instance(self) -> None:
        agent = _make_agent(strategy=EchoStrategy())
        tool = agent.strategy.as_tool(agent)
        self.assertIsInstance(tool, StrategyTool)

    def test_as_tool_name_override(self) -> None:
        agent = _make_agent(strategy=EchoStrategy())
        tool = agent.strategy.as_tool(agent, name="my_tool")
        self.assertEqual(tool.spec().name, "my_tool")

    def test_as_tool_description_override(self) -> None:
        agent = _make_agent(strategy=EchoStrategy())
        tool = agent.strategy.as_tool(agent, description="custom")
        self.assertEqual(tool.spec().description, "custom")

    def test_as_tool_raises_when_agent_has_no_strategy(self) -> None:
        strategy = EchoStrategy()
        agent = _make_agent(strategy=None)
        with self.assertRaises(AgentExecutionError):
            strategy.as_tool(agent)

    def test_strategy_description_classvar_in_spec(self) -> None:
        agent = _make_agent(strategy=EchoStrategy())
        tool = StrategyTool(agent)
        self.assertEqual(tool.spec().description, EchoStrategy.description)


class BaseStrategyDescriptionTests(unittest.TestCase):
    def test_description_classvar_defaults_to_empty_string(self) -> None:
        self.assertEqual(BaseStrategy.description, "")

    def test_subclass_can_override_description(self) -> None:
        self.assertEqual(EchoStrategy.description, "Echoes the prompt back.")


if __name__ == "__main__":
    unittest.main()
