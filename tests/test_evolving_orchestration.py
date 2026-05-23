from __future__ import annotations

import unittest

from vidbyte.agents import BaseAgent
from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.strategies.multi_agent import EvolvingOrchestrationStrategy


class StaticStrategy(BaseStrategy):
    def __init__(self, output: str) -> None:
        self.output = output

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=self.output, strategy_name="static")


class EvolvingTests(unittest.IsolatedAsyncioTestCase):
    async def test_heuristic_policy_runs_worker_then_evaluator(self) -> None:
        worker = BaseAgent(
            name="worker",
            system_prompt="Work.",
            strategy=StaticStrategy("draft"),
            metadata={"role": "worker"},
        )
        evaluator = BaseAgent(
            name="judge",
            system_prompt="Judge.",
            strategy=StaticStrategy("final"),
            metadata={"role": "evaluator"},
        )
        strategy = EvolvingOrchestrationStrategy(agents=[worker, evaluator], max_turns=4)

        result = await strategy.arun("task")
        self.assertEqual(result.output, "final")
        self.assertEqual(result.metadata["turns"], 2)


if __name__ == "__main__":
    unittest.main()
