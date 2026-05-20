from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import StepBackPrompts
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyResult


class StepBackStrategy(BaseStrategy):
    name: ClassVar[str] = "step_back"
    prompts: ClassVar[dict[str, str]] = StepBackPrompts().export()

    def run(self, prompt: str, *, runner: TextModelRunner | None = None, **options: object) -> StrategyResult:
        runner = self._resolve_runner(runner)
        principle_response = self._extract_principles(prompt, runner=runner)
        answer_response = self._apply_principles(prompt, principle_response.text, runner=runner)
        return StrategyResult(output=answer_response.text, strategy_name=self.name, calls=(principle_response, answer_response), metadata={"principles": principle_response.text})

    def _extract_principles(self, prompt: str, *, runner: TextModelRunner) -> TextModelResponse:
        # Step back from the task to surface reusable principles before solving.
        return self._run_model(runner, f"{self.prompts['principle_prompt']}\n\n{prompt}")

    def _apply_principles(self, prompt: str, principles: str, *, runner: TextModelRunner) -> TextModelResponse:
        # Ground the final answer in the principles extracted in the first call.
        return self._run_model(runner, f"{self.prompts['answer_prompt']}\n\nPrinciples:\n{principles}\n\nOriginal task:\n{prompt}\n\nFinal answer:")


__all__ = [
    "StepBackStrategy",
]
