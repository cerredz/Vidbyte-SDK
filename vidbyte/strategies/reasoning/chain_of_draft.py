from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy, require_positive
from vidbyte.strategies.types import StrategyResult


class ChainOfDraftStrategy(BaseStrategy):
    name: ClassVar[str] = "chain_of_draft"

    def __init__(self, *, max_words_per_step: int = 5) -> None:
        require_positive(max_words_per_step, field_name="max_words_per_step")
        self.max_words_per_step = max_words_per_step

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        response = runner.run(
            "\n".join(
                [
                    "Solve the task using concise draft reasoning.",
                    f"Each intermediate reasoning step must be at most {self.max_words_per_step} words.",
                    "After the terse draft, provide a clear final answer.",
                    "",
                    prompt,
                ]
            )
        )
        return StrategyResult(
            output=response.text,
            strategy_name=self.name,
            calls=(response,),
            metadata={"max_words_per_step": self.max_words_per_step},
        )
