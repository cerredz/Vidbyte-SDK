from __future__ import annotations

import unittest

from vidbyte.agents import BaseAgent
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


if __name__ == "__main__":
    unittest.main()
