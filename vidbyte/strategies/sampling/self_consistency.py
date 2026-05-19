from __future__ import annotations

from collections import Counter
from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy, normalize_answer, require_positive
from vidbyte.strategies.types import StrategyResult


class SelfConsistencyStrategy(BaseStrategy):
    name: ClassVar[str] = "self_consistency"

    def __init__(self, *, samples: int = 5) -> None:
        require_positive(samples, field_name="samples")
        self.samples = samples

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        calls = tuple(
            runner.run(
                "\n".join(
                    [
                        "Solve independently. End with 'Final answer:'.",
                        f"Sample {index + 1} of {self.samples}.",
                        "",
                        prompt,
                    ]
                )
            )
            for index in range(self.samples)
        )
        normalized = [normalize_answer(call.text) for call in calls]
        counts = Counter(normalized)
        winner, votes = counts.most_common(1)[0]
        winner_index = normalized.index(winner)
        return StrategyResult(
            output=calls[winner_index].text,
            strategy_name=self.name,
            calls=calls,
            metadata={"winner": winner, "votes": votes, "counts": dict(counts)},
        )
