from __future__ import annotations

import unittest

from vidbyte.agents import BaseAgent
from vidbyte.agents.base import ConfiguredAgentRunner
from vidbyte.strategies import BaseAgentContext, BaseStrategy, StrategyContext, StrategyResult
from vidbyte.tools import ToolSpec


class FakeTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(name="lookup", description="Lookup things")


class EchoStrategy(BaseStrategy):
    name = "echo"

    def __init__(self) -> None:
        self.last_tools = ()
        self.last_context: StrategyContext | None = None

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        self.last_tools = tuple(kwargs.get("tools", ()))
        self.last_context = kwargs.get("context")  # type: ignore[assignment]
        return StrategyResult(output=f"reply:{prompt}", strategy_name=self.name)


class EchoRunner:
    def __init__(self) -> None:
        self.system = None

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> object:
        self.system = system
        return FakeResponse(
            "",
            {"output": [{"type": "function_call", "name": "isDone", "arguments": f'{{"final_answer": "direct:{prompt}"}}'}]},
        )


class FakeResponse:
    def __init__(self, text: str, raw: dict) -> None:
        self.text = text
        self.raw = raw


class AgentBaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_card_and_generate_reply_pass_tools_and_context(self) -> None:
        strategy = EchoStrategy()
        tool = FakeTool()
        agent = BaseAgent(
            name="worker",
            system_prompt="Work carefully.",
            strategy=strategy,
            runner=object(),
            tools=[tool],
            capabilities=["search"],
        )

        card = agent.card()
        self.assertEqual(card.name, "worker")
        self.assertEqual(card.tool_names, ("lookup",))
        self.assertEqual(card.capabilities, ("search",))

        reply = await agent.generate_reply("task")
        self.assertEqual(reply.content, "reply:task")
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertEqual(strategy.last_tools, (tool,))
        self.assertIsNotNone(strategy.last_context)
        self.assertIsInstance(strategy.last_context, BaseAgentContext)
        self.assertEqual(strategy.last_context.agent_name, None)
        self.assertEqual(strategy.last_context.strategy_metadata, {})
        self.assertEqual(tuple(tool.name for tool in strategy.last_context.tools), ("lookup", "isDone"))

    async def test_runner_config_tool_helpers_and_fork(self) -> None:
        strategy = EchoStrategy()
        tool = FakeTool()
        agent = BaseAgent.from_run_id(
            "run-123",
            name="researcher",
            system_prompt="Research carefully.",
            strategy=strategy,
            model_name="model-a",
            temperature=0.2,
            tools=[tool],
            metadata={"role": "custom_researcher"},
        )

        self.assertIsInstance(agent.runner, ConfiguredAgentRunner)
        self.assertEqual(agent.tool_specs()[0].name, "lookup")
        agent.add_tool(object())
        self.assertEqual(agent.card().tool_names, ("lookup", "object"))

        forked = agent.fork(name="researcher-copy", metadata={"branch": "copy"})
        self.assertEqual(forked.name, "researcher-copy")
        self.assertEqual(forked.metadata["role"], "custom_researcher")
        self.assertEqual(forked.metadata["branch"], "copy")

    async def test_agent_without_strategy_calls_runner_once(self) -> None:
        runner = EchoRunner()
        agent = BaseAgent(name="direct", system_prompt="Direct system.", runner=runner)

        reply = await agent.generate_reply("task")

        self.assertEqual(reply.content, "direct:task")
        self.assertEqual(reply.metadata["strategy"], "direct_runner")
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertIn("Direct system.", runner.system)
        self.assertIn("agentic loop", runner.system)


if __name__ == "__main__":
    unittest.main()
