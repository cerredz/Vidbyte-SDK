from __future__ import annotations

import unittest

from vidbyte.harnesses import BaseHarness
from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.strategies.multi_agent import MultiAgentConsensusStrategy


class FakeStrategy(BaseStrategy):
    name = "fake"

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=prompt, strategy_name=self.name)


class StrategyMixinTests(unittest.TestCase):
    def test_with_strategy_stores_strategy(self) -> None:
        harness = BaseHarness()
        strategy = FakeStrategy()
        self.assertIs(harness.with_strategy(strategy), harness)
        self.assertIs(harness._strategy, strategy)

    def test_with_strategies_wraps_consensus(self) -> None:
        harness = BaseHarness()
        harness.with_strategies([FakeStrategy()])
        self.assertIsInstance(harness._strategy, MultiAgentConsensusStrategy)

    def test_empty_with_strategies_fails(self) -> None:
        with self.assertRaises(ValueError):
            BaseHarness().with_strategies([])


if __name__ == "__main__":
    unittest.main()
