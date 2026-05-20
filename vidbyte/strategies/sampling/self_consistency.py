from __future__ import annotations

from collections import Counter
from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import SelfConsistencyPrompts
from vidbyte.strategies.base import BaseStrategy, normalize_answer, require_positive
from vidbyte.strategies.types import StrategyResult


class SelfConsistencyStrategy(BaseStrategy):
    name: ClassVar[str] = "self_consistency"
    prompts: ClassVar[dict[str, str]] = SelfConsistencyPrompts().export()

    def __init__(self, *, samples: int = 5) -> None:
        require_positive(samples, field_name="samples")
        self.samples = samples

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        calls = self._sample_independently(prompt, runner=runner)
        return self._vote(calls)

    def _sample_independently(self, prompt: str, *, runner: TextModelRunner) -> tuple[TextModelResponse, ...]:
        # Draw N independent completions for majority-vote aggregation.
        return tuple(
            runner.run(self.prompts["sample_prompt"].format(index=i + 1, samples=self.samples) + f"\n\n{prompt}")
            for i in range(self.samples)
        )

    def _vote(self, calls: tuple[TextModelResponse, ...]) -> StrategyResult:
        # Pick the answer that appears most often across all sampled completions.
        normalized = [normalize_answer(call.text) for call in calls]
        counts = Counter(normalized)
        winner, votes = counts.most_common(1)[0]
        winner_index = normalized.index(winner)
        return StrategyResult(output=calls[winner_index].text, strategy_name=self.name, calls=calls, metadata={"winner": winner, "votes": votes, "counts": dict(counts)})


__all__ = [
    "SelfConsistencyStrategy",
]
