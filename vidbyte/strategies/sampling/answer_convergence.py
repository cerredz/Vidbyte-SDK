from __future__ import annotations

from collections import Counter
from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy, normalize_answer, require_positive
from vidbyte.strategies.types import StrategyResult


class AnswerConvergenceStrategy(BaseStrategy):
    name: ClassVar[str] = "answer_convergence"

    def __init__(self, *, max_samples: int = 7, window: int = 3) -> None:
        require_positive(max_samples, field_name="max_samples")
        require_positive(window, field_name="window")
        self.max_samples = max_samples
        self.window = window

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        calls = []
        normalized: list[str] = []
        for index in range(self.max_samples):
            response = runner.run(
                "\n".join(
                    [
                        "Solve independently and end with 'Final answer:'.",
                        f"Attempt {index + 1}.",
                        "",
                        prompt,
                    ]
                )
            )
            calls.append(response)
            normalized.append(normalize_answer(response.text))
            if len(normalized) >= self.window and len(set(normalized[-self.window :])) == 1:
                break

        counts = Counter(normalized)
        winner, votes = counts.most_common(1)[0]
        winner_index = normalized.index(winner)
        return StrategyResult(
            output=calls[winner_index].text,
            strategy_name=self.name,
            calls=tuple(calls),
            metadata={"winner": winner, "votes": votes, "counts": dict(counts)},
        )
