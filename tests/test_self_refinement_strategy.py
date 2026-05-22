from __future__ import annotations

import unittest

from vidbyte.lib.config import ModelProvider
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.prompts.strategies import SelfRefinementFeedbackPrompt, SelfRefinementRefinePrompt
from vidbyte.strategies.agent_loops import SelfRefinementStrategy


class SequenceRunner:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def run(self, prompt: str, *, system: str | None = None, **kwargs: object) -> TextModelResponse:
        """Record prompt calls and return the next fake model response."""
        self.prompts.append(prompt)
        self.systems.append(system)
        text = self.responses.pop(0)
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


class SelfRefinementStrategyTests(unittest.TestCase):
    def test_runs_create_feedback_refine_for_n_iterations(self) -> None:
        runner = SequenceRunner(
            [
                "draft 0",
                "feedback 1",
                "draft 1",
                "feedback 2",
                "draft 2",
            ]
        )
        strategy = SelfRefinementStrategy(
            create_system_prompt="create",
            refine_system_prompt="refine",
            iterations=2,
        )

        result = strategy.run("task", runner=runner)

        self.assertEqual(result.output, "draft 2")
        self.assertEqual(len(result.calls), 5)
        self.assertEqual(result.metadata["iterations_completed"], 2)
        self.assertFalse(result.metadata["stopped_early"])

    def test_passes_configured_system_prompts(self) -> None:
        runner = SequenceRunner(["draft 0", "feedback 1", "draft 1"])
        strategy = SelfRefinementStrategy(
            create_system_prompt="create system",
            feedback_system_prompt="feedback system",
            refine_system_prompt="refine system",
            iterations=1,
        )

        strategy.run("task", runner=runner)

        self.assertEqual(runner.systems, ["create system", "feedback system", "refine system"])

    def test_metadata_contains_iteration_history(self) -> None:
        runner = SequenceRunner(["draft 0", "feedback 1", "draft 1"])
        strategy = SelfRefinementStrategy(
            create_system_prompt="create",
            refine_system_prompt="refine",
            iterations=1,
        )

        result = strategy.run("task", runner=runner)
        steps = result.metadata["steps"]

        self.assertEqual(steps[0]["iteration"], 1)
        self.assertEqual(steps[0]["draft"], "draft 0")
        self.assertEqual(steps[0]["feedback"], "feedback 1")
        self.assertEqual(steps[0]["refined"], "draft 1")
        self.assertFalse(steps[0]["stopped"])

    def test_exposes_prompt_classes_for_reuse(self) -> None:
        self.assertIs(SelfRefinementStrategy.prompts["feedback_prompt"], SelfRefinementFeedbackPrompt)

        prompt = SelfRefinementRefinePrompt(
            original_task="task",
            initial_draft="draft 0",
            current_draft="draft 1",
            latest_feedback="feedback",
            prior_history=("Iteration 1: feedback='feedback'; refined='draft 1'",),
        ).export()

        self.assertIn("Original task:\ntask", prompt)
        self.assertIn("Prior refinement history:", prompt)

    def test_stops_early_when_feedback_says_no_changes_needed(self) -> None:
        runner = SequenceRunner(["draft 0", "No changes needed."])
        strategy = SelfRefinementStrategy(
            create_system_prompt="create",
            refine_system_prompt="refine",
            iterations=3,
        )

        result = strategy.run("task", runner=runner)

        self.assertEqual(result.output, "draft 0")
        self.assertEqual(len(result.calls), 2)
        self.assertTrue(result.metadata["stopped_early"])
        self.assertTrue(result.metadata["steps"][0]["stopped"])

    def test_rejects_empty_required_prompts(self) -> None:
        with self.assertRaises(StrategyExecutionError):
            SelfRefinementStrategy(
                create_system_prompt="",
                refine_system_prompt="refine",
                iterations=1,
            )

        with self.assertRaises(StrategyExecutionError):
            SelfRefinementStrategy(
                create_system_prompt="create",
                refine_system_prompt="",
                iterations=1,
            )

    def test_rejects_non_positive_iterations(self) -> None:
        with self.assertRaises(StrategyExecutionError):
            SelfRefinementStrategy(
                create_system_prompt="create",
                refine_system_prompt="refine",
                iterations=0,
            )

    def test_raises_on_empty_feedback(self) -> None:
        runner = SequenceRunner(["draft 0", " "])
        strategy = SelfRefinementStrategy(
            create_system_prompt="create",
            refine_system_prompt="refine",
            iterations=1,
        )

        with self.assertRaises(StrategyExecutionError):
            strategy.run("task", runner=runner)

    def test_raises_on_empty_refined_output(self) -> None:
        runner = SequenceRunner(["draft 0", "feedback", " "])
        strategy = SelfRefinementStrategy(
            create_system_prompt="create",
            refine_system_prompt="refine",
            iterations=1,
        )

        with self.assertRaises(StrategyExecutionError):
            strategy.run("task", runner=runner)


if __name__ == "__main__":
    unittest.main()
