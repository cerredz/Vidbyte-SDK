from __future__ import annotations

import unittest

from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.strategies.sampling import (
    AnswerConvergenceStrategy,
    BudgetForcingStrategy,
    SelfConsistencyStrategy,
)


class SequenceRunner:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def run(self, prompt: str, **kwargs: object) -> TextModelResponse:
        self.prompts.append(prompt)
        text = self.responses.pop(0)
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


class SamplingStrategyTests(unittest.TestCase):
    def test_self_consistency_votes_for_majority_answer(self) -> None:
        runner = SequenceRunner(
            [
                "Final answer: A",
                "Final answer: B",
                "Final answer: A",
            ]
        )

        result = SelfConsistencyStrategy(samples=3, runner=runner).run("task")

        self.assertEqual(result.metadata["winner"], "a")
        self.assertEqual(result.metadata["votes"], 2)
        self.assertEqual(result.output, "Final answer: A")

    def test_budget_forcing_continues_until_final_answer(self) -> None:
        runner = SequenceRunner(
            [
                "Too short",
                "This answer has enough words to count as substantial after checking the assumptions carefully. Final answer: done",
            ]
        )

        result = BudgetForcingStrategy(max_rounds=3, runner=runner).run("task")

        self.assertEqual(len(result.calls), 2)
        self.assertIn("done", result.output)

    def test_answer_convergence_stops_when_window_matches(self) -> None:
        runner = SequenceRunner(
            [
                "Final answer: A",
                "Final answer: B",
                "Final answer: B",
                "Final answer: B",
                "Final answer: C",
            ]
        )

        result = AnswerConvergenceStrategy(max_samples=5, window=3, runner=runner).run("task")

        self.assertEqual(len(result.calls), 4)
        self.assertEqual(result.metadata["winner"], "b")


if __name__ == "__main__":
    unittest.main()
