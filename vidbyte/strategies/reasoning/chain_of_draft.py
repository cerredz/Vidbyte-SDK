from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import ChainOfDraftPrompts
from vidbyte.strategies.base import BaseStrategy, BaseStrategyUtils
from vidbyte.strategies.types import StrategyResult


class ChainOfDraftStrategy(BaseStrategy):
    name: ClassVar[str] = "chain_of_draft"
    prompts: ClassVar[dict[str, str]] = ChainOfDraftPrompts().export()

    def __init__(self, *, max_words_per_step: int = 5, **runner_options: object) -> None:
        super().__init__(**runner_options)
        BaseStrategyUtils.require_positive(max_words_per_step, field_name="max_words_per_step")
        self.max_words_per_step = max_words_per_step

    def run(self, prompt: str, *, runner: TextModelRunner | None = None, **options: object) -> StrategyResult:
        runner = self._resolve_runner(runner)
        response = self._draft_reason(prompt, runner=runner)
        return StrategyResult(output=response.text, strategy_name=self.name, calls=(response,), metadata={"max_words_per_step": self.max_words_per_step})

    def _draft_reason(self, prompt: str, *, runner: TextModelRunner) -> TextModelResponse:
        # Format the draft prompt with the configured per-step word budget.
        instruction = self.prompts["draft_prompt"].format(max_words_per_step=self.max_words_per_step)
        return self._run_model(runner, f"{instruction}\n\n{prompt}")


__all__ = [
    "ChainOfDraftStrategy",
]
