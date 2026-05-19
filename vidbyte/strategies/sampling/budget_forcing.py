from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy, require_positive
from vidbyte.strategies.types import StrategyResult


class BudgetForcingStrategy(BaseStrategy):
    name: ClassVar[str] = "budget_forcing"

    def __init__(self, *, max_rounds: int = 3) -> None:
        require_positive(max_rounds, field_name="max_rounds")
        self.max_rounds = max_rounds

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        calls = [
            runner.run(
                "\n".join(
                    [
                        "Solve the task carefully.",
                        "If the answer seems premature, continue checking before finalizing.",
                        "End with 'Final answer:'.",
                        "",
                        prompt,
                    ]
                )
            )
        ]
        current = calls[0].text
        for round_index in range(1, self.max_rounds):
            if "final answer:" in current.lower():
                break
            response = runner.run(
                "\n".join(
                    [
                        "Continue from the previous attempt.",
                        "Double-check assumptions, fix mistakes, and provide a final answer.",
                        "",
                        "Original task:",
                        prompt,
                        "",
                        "Previous attempt:",
                        current,
                        "",
                        f"Continuation round {round_index + 1}:",
                    ]
                )
            )
            calls.append(response)
            current = response.text

        return StrategyResult(
            output=current,
            strategy_name=self.name,
            calls=tuple(calls),
            metadata={"rounds": len(calls), "max_rounds": self.max_rounds},
        )
