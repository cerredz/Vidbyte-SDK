from __future__ import annotations

import unittest

from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import TextModelResponse
from vidbyte.strategies.routing import ParadigmRouterStrategy


class FakeRunner:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(self, prompt: str, **kwargs: object) -> TextModelResponse:
        self.prompts.append(prompt)
        if "Return only the exact strategy name" in prompt:
            text = "step_back"
        else:
            text = "Final answer: OK"
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})


class StrategyRouterTests(unittest.TestCase):
    def test_heuristic_router_selects_skeleton_for_report_prompt(self) -> None:
        runner = FakeRunner()

        result = ParadigmRouterStrategy().run("Write a report with sections", runner=runner)

        self.assertEqual(result.metadata["selected_strategy"], "skeleton_of_thought")

    def test_model_router_selects_reported_strategy(self) -> None:
        runner = FakeRunner()

        result = ParadigmRouterStrategy().run("task", runner=runner, use_model_router=True)

        self.assertEqual(result.metadata["selected_strategy"], "step_back")
        self.assertIn("Return only the exact strategy name", runner.prompts[0])


if __name__ == "__main__":
    unittest.main()
