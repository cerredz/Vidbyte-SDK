from __future__ import annotations

import unittest

from vidbyte.agents import AgentRegistry, BaseAgent
from vidbyte.lib.errors import AgentRegistryError
from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.tools import ToolSpec


class FakeStrategy(BaseStrategy):
    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=prompt, strategy_name="fake")


class FakeTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(name="calculator", description="Math")


class AgentRegistryTests(unittest.TestCase):
    def test_lookup_and_filtering(self) -> None:
        registry = AgentRegistry()
        worker = BaseAgent(
            name="worker",
            strategy=FakeStrategy(),
            tools=[FakeTool()],
            role="worker",
            capabilities=["math"],
        )
        evaluator = BaseAgent(name="judge", strategy=FakeStrategy(), role="evaluator")
        registry.register(worker)
        registry.register(evaluator)

        self.assertIs(registry.get("worker"), worker)
        self.assertEqual(registry.find(role="worker"), (worker,))
        self.assertEqual(registry.find(capability="math"), (worker,))
        self.assertEqual(registry.find(tool_name="calculator"), (worker,))
        self.assertEqual(len(registry.cards()), 2)

    def test_duplicate_and_missing_errors(self) -> None:
        registry = AgentRegistry()
        agent = BaseAgent(name="worker", strategy=FakeStrategy())
        registry.register(agent)
        with self.assertRaises(AgentRegistryError):
            registry.register(agent)
        with self.assertRaises(AgentRegistryError):
            registry.get("missing")


if __name__ == "__main__":
    unittest.main()
