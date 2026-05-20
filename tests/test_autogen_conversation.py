from __future__ import annotations

import unittest

from vidbyte.agents import AgentMessage, AgentRegistry, BaseAgent
from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.strategies.multi_agent import AutoGenConversationStrategy


class NamedStrategy(BaseStrategy):
    def __init__(self, output: str) -> None:
        self.output = output

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=self.output, strategy_name="named")


class AutoGenTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_until_policy_stops(self) -> None:
        a = BaseAgent(name="a", strategy=NamedStrategy("from-a"))
        b = BaseAgent(name="b", strategy=NamedStrategy("from-b"))

        def transition(transcript: tuple[AgentMessage, ...], registry: AgentRegistry) -> str | None:
            return "b" if len(transcript) == 1 else None

        strategy = AutoGenConversationStrategy(
            agents=[a, b],
            initial_agent="a",
            transition_policy=transition,
            max_turns=4,
        )
        result = await strategy.arun("start")
        self.assertEqual(result.output, "from-b")
        self.assertEqual(result.metadata["turns"], 2)
        self.assertEqual(result.metadata["stopped_by"], "policy")


if __name__ == "__main__":
    unittest.main()
