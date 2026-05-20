from __future__ import annotations

import unittest

from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.strategies.multi_agent import EconomicGateStrategy


class StaticStrategy(BaseStrategy):
    def __init__(self, name: str) -> None:
        self.name = name

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=self.name, strategy_name=self.name)


class EconomicGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_low_score_routes_baseline(self) -> None:
        strategy = EconomicGateStrategy(
            baseline_strategy=StaticStrategy("base"),
            orchestration_strategy=StaticStrategy("orchestrated"),
            scorer=lambda prompt, context: 0.1,
            threshold=0.5,
        )
        result = await strategy.arun("simple")
        self.assertEqual(result.output, "base")
        self.assertEqual(result.metadata["route"], "baseline")

    async def test_high_score_routes_orchestration(self) -> None:
        strategy = EconomicGateStrategy(
            baseline_strategy=StaticStrategy("base"),
            orchestration_strategy=StaticStrategy("orchestrated"),
            scorer=lambda prompt, context: 0.9,
            threshold=0.5,
        )
        result = await strategy.arun("complex")
        self.assertEqual(result.output, "orchestrated")
        self.assertEqual(result.metadata["route"], "orchestration")


if __name__ == "__main__":
    unittest.main()
