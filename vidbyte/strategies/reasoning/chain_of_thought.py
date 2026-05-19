from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyResult


class ChainOfThoughtStrategy(BaseStrategy):
    name: ClassVar[str] = "chain_of_thought"

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        response = runner.run(
            "\n".join(
                [
                    "Solve the task carefully.",
                    "Reason step by step before giving the final answer.",
                    "End with a section labeled 'Final answer:'.",
                    "",
                    prompt,
                ]
            )
        )
        return StrategyResult(
            output=response.text,
            strategy_name=self.name,
            calls=(response,),
            metadata={"style": "sequential_reasoning"},
        )
