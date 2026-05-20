from __future__ import annotations

import unittest

from vidbyte.agents import BaseAgent
from vidbyte.agents.base import ConfiguredAgentRunner
from vidbyte.strategies import BaseStrategy, StrategyContext, StrategyResult
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


class AgentBaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_card_and_generate_reply_pass_tools_and_context(self) -> None:
        strategy = EchoStrategy()
        tool = FakeTool()
        agent = BaseAgent(
            name="worker",
            strategy=strategy,
            runner=object(),
            tools=[tool],
            role="worker",
            capabilities=["search"],
        )

        card = agent.card()
        self.assertEqual(card.name, "worker")
        self.assertEqual(card.tool_names, ("lookup",))
        self.assertEqual(card.capabilities, ("search",))

        reply = await agent.generate_reply("task")
        self.assertEqual(reply.content, "reply:task")
        self.assertEqual(strategy.last_tools, (tool,))
        self.assertIsNotNone(strategy.last_context)
        self.assertEqual(strategy.last_context.agent_name, "worker")
        self.assertEqual(strategy.last_context.role, "worker")
        self.assertIn("current_agent", strategy.last_context.strategy_metadata)

    async def test_runner_config_tool_helpers_and_fork(self) -> None:
        strategy = EchoStrategy()
        tool = FakeTool()
        agent = BaseAgent.from_run_id(
            "run-123",
            name="researcher",
            strategy=strategy,
            model_name="model-a",
            temperature=0.2,
            tools=[tool],
            role="custom_researcher",
            system_prompt="Research carefully.",
        )

        self.assertIsInstance(agent.runner, ConfiguredAgentRunner)
        self.assertEqual(agent.tool_specs()[0].name, "lookup")
        agent.add_tool(object())
        self.assertEqual(agent.card().tool_names, ("lookup", "object"))

        forked = agent.fork(name="researcher-copy", metadata={"branch": "copy"})
        self.assertEqual(forked.name, "researcher-copy")
        self.assertEqual(forked.role, "custom_researcher")
        self.assertEqual(forked.metadata["branch"], "copy")


if __name__ == "__main__":
    unittest.main()
