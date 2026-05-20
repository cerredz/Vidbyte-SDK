from __future__ import annotations

from collections import Counter
from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import AnswerConvergencePrompts
from vidbyte.strategies.base import BaseStrategy, BaseStrategyUtils
from vidbyte.strategies.types import StrategyResult


class AnswerConvergenceStrategy(BaseStrategy):
    name: ClassVar[str] = "answer_convergence"
    prompts: ClassVar[dict[str, str]] = AnswerConvergencePrompts().export()

    def __init__(self, *, max_samples: int = 7, window: int = 3, **runner_options: object) -> None:
        super().__init__(**runner_options)
        BaseStrategyUtils.require_positive(max_samples, field_name="max_samples")
        BaseStrategyUtils.require_positive(window, field_name="window")
        self.max_samples = max_samples
        self.window = window

    def run(self, prompt: str, *, runner: TextModelRunner | None = None, **options: object) -> StrategyResult:
        runner = self._resolve_runner(runner)
        calls, normalized = self._sample_until_convergence(prompt, runner=runner)
        counts = Counter(normalized)
        winner, votes = counts.most_common(1)[0]
        winner_index = normalized.index(winner)
        return StrategyResult(output=calls[winner_index].text, strategy_name=self.name, calls=tuple(calls), metadata={"winner": winner, "votes": votes, "counts": dict(counts)})

    def _sample_until_convergence(self, prompt: str, *, runner: TextModelRunner) -> tuple[list[TextModelResponse], list[str]]:
        # Draw samples until the last window answers agree or max_samples is reached.
        calls: list[TextModelResponse] = []
        normalized: list[str] = []
        for index in range(self.max_samples):
            response = self._attempt(prompt, index, runner=runner)
            calls.append(response)
            normalized.append(BaseStrategyUtils.normalize_answer(response.text))
            if self._has_converged(normalized):
                break
        return calls, normalized

    def _attempt(self, prompt: str, index: int, *, runner: TextModelRunner) -> TextModelResponse:
        # Run one independent attempt with the attempt index embedded.
        return self._run_model(runner, self.prompts["attempt_prompt"].format(index=index + 1) + f"\n\n{prompt}")

    def _has_converged(self, normalized: list[str]) -> bool:
        # Convergence means the last window answers are all identical.
        return len(normalized) >= self.window and len(set(normalized[-self.window :])) == 1


__all__ = [
    "AnswerConvergenceStrategy",
]
