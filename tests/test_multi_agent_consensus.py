from __future__ import annotations

import json
import unittest

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies import BaseStrategy, StrategyResult
from vidbyte.strategies.multi_agent import MultiAgentConsensusStrategy


class StaticStrategy(BaseStrategy):
    def __init__(self, name: str, output: str) -> None:
        self.name = name
        self.output = output

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(output=self.output, strategy_name=self.name)


class FailingStrategy(BaseStrategy):
    name = "failing"

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        raise RuntimeError("boom")


class EvaluatorStrategy(BaseStrategy):
    name = "evaluator"

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        return StrategyResult(
            output=json.dumps(
                {
                    "selected_index": 2,
                    "final_output": "winner",
                    "grades": {"2": "best"},
                    "rationale": "candidate 2 wins",
                }
            ),
            strategy_name=self.name,
        )


class ConsensusTests(unittest.IsolatedAsyncioTestCase):
    async def test_selects_evaluator_choice_and_keeps_failures(self) -> None:
        strategy = MultiAgentConsensusStrategy(
            strategies=[
                StaticStrategy("a", "first"),
                StaticStrategy("b", "second"),
                FailingStrategy(),
            ],
            evaluator_strategy=EvaluatorStrategy(),
        )
        result = await strategy.arun("question")
        self.assertEqual(result.output, "winner")
        self.assertEqual(result.metadata["selected_index"], 2)
        self.assertEqual(len(result.metadata["failures"]), 1)

    async def test_all_failed_candidates_raise(self) -> None:
        strategy = MultiAgentConsensusStrategy(strategies=[FailingStrategy()])
        with self.assertRaises(StrategyExecutionError):
            await strategy.arun("question")

    async def test_invalid_json_falls_back_to_raw_evaluator_output(self) -> None:
        strategy = MultiAgentConsensusStrategy(
            strategies=[StaticStrategy("a", "first")],
            evaluator_strategy=StaticStrategy("eval", "raw evaluation"),
        )
        result = await strategy.arun("question")
        self.assertEqual(result.output, "raw evaluation")


if __name__ == "__main__":
    unittest.main()
