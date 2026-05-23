from __future__ import annotations

import unittest

from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.strategies.mixins import StrategyMixin
from vidbyte.strategies.multi_agent import MultiAgentConsensusStrategy


class FakeStrategy(BaseStrategy):
    name = "fake"

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=prompt, strategy_name=self.name)


class StrategyHost(StrategyMixin):
    def __init__(self) -> None:
        super().__init__()


class StrategyMixinTests(unittest.TestCase):
    def test_with_strategy_stores_strategy(self) -> None:
        harness = StrategyHost()
        strategy = FakeStrategy()
        self.assertIs(harness.with_strategy(strategy), harness)
        self.assertIs(harness._strategy, strategy)

    def test_with_strategies_wraps_consensus(self) -> None:
        harness = StrategyHost()
        harness.with_strategies([FakeStrategy()])
        self.assertIsInstance(harness._strategy, MultiAgentConsensusStrategy)

    def test_empty_with_strategies_fails(self) -> None:
        with self.assertRaises(ValueError):
            StrategyHost().with_strategies([])


if __name__ == "__main__":
    unittest.main()
