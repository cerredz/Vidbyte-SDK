from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import BudgetForcingPrompts
from vidbyte.strategies.base import BaseStrategy, BaseStrategyUtils
from vidbyte.strategies.types import StrategyResult


class BudgetForcingStrategy(BaseStrategy):
    name: ClassVar[str] = "budget_forcing"
    prompts: ClassVar[dict[str, str]] = BudgetForcingPrompts().export()

    def __init__(self, *, max_rounds: int = 3, **runner_options: object) -> None:
        super().__init__(**runner_options)
        BaseStrategyUtils.require_positive(max_rounds, field_name="max_rounds")
        self.max_rounds = max_rounds

    def run(self, prompt: str, *, runner: TextModelRunner | None = None, **options: object) -> StrategyResult:
        runner = self._resolve_runner(runner)
        calls = [self._initial_attempt(prompt, runner=runner)]
        current = calls[0].text
        for round_index in range(1, self.max_rounds):
            if self._has_final_answer(current):
                break
            response = self._continue_attempt(prompt, current, round_index, runner=runner)
            calls.append(response)
            current = response.text
        return StrategyResult(output=current, strategy_name=self.name, calls=tuple(calls), metadata={"rounds": len(calls), "max_rounds": self.max_rounds})

    def _initial_attempt(self, prompt: str, *, runner: TextModelRunner) -> TextModelResponse:
        # Make the first attempt with the budget-aware initial prompt.
        return self._run_model(runner, f"{self.prompts['initial_prompt']}\n\n{prompt}")

    def _continue_attempt(self, prompt: str, previous: str, round_index: int, *, runner: TextModelRunner) -> TextModelResponse:
        # Continue from the previous round when no final answer was detected.
        return self._run_model(runner, f"{self.prompts['continue_prompt']}\n\nOriginal task:\n{prompt}\n\nPrevious attempt:\n{previous}\n\nContinuation round {round_index + 1}:")

    def _has_final_answer(self, text: str) -> bool:
        # Detect a finalized answer to avoid burning unnecessary budget rounds.
        return "final answer:" in text.lower()


__all__ = [
    "BudgetForcingStrategy",
]
