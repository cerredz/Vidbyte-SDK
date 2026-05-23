from __future__ import annotations

import unittest

from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.strategies.reasoning import (
    ChainOfDraftStrategy,
    ChainOfThoughtStrategy,
    SkeletonOfThoughtStrategy,
    StepBackStrategy,
)


class FakeRunner:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(self, prompt: str, **kwargs: object) -> TextModelResponse:
        self.prompts.append(prompt)
        if "numbered skeleton" in prompt:
            text = "1. Alpha\n2. Beta"
        else:
            text = "Reasoning\nFinal answer: OK"
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


class ReasoningStrategyTests(unittest.TestCase):
    def test_chain_of_thought_uses_single_runner_call(self) -> None:
        runner = FakeRunner()

        result = ChainOfThoughtStrategy(runner=runner).run("task")

        self.assertEqual(len(result.calls), 1)
        self.assertIn("reasoning step by step", runner.prompts[0])

    def test_step_back_uses_principles_then_answer(self) -> None:
        runner = FakeRunner()

        result = StepBackStrategy(runner=runner).run("task")

        self.assertEqual(len(result.calls), 2)
        self.assertIn("Step back", runner.prompts[0])
        self.assertIn("Principles:", runner.prompts[1])

    def test_chain_of_draft_includes_word_budget(self) -> None:
        runner = FakeRunner()

        ChainOfDraftStrategy(max_words_per_step=4, runner=runner).run("task")

        self.assertIn("at most 4 words", runner.prompts[0])

    def test_skeleton_of_thought_expands_points(self) -> None:
        runner = FakeRunner()

        result = SkeletonOfThoughtStrategy(max_workers=1, runner=runner).run("task")

        self.assertEqual(len(result.calls), 3)
        self.assertEqual(result.metadata["points"], ("Alpha", "Beta"))


if __name__ == "__main__":
    unittest.main()
