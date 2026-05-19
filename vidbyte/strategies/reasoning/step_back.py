from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyResult


class StepBackStrategy(BaseStrategy):
    name: ClassVar[str] = "step_back"

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        principle_response = runner.run(
            "\n".join(
                [
                    "Step back from the specific task.",
                    "Identify the general principles, abstractions, or concepts needed.",
                    "Do not solve the original task yet.",
                    "",
                    prompt,
                ]
            )
        )
        answer_response = runner.run(
            "\n".join(
                [
                    "Use these general principles to solve the original task.",
                    "",
                    "Principles:",
                    principle_response.text,
                    "",
                    "Original task:",
                    prompt,
                    "",
                    "Final answer:",
                ]
            )
        )
        return StrategyResult(
            output=answer_response.text,
            strategy_name=self.name,
            calls=(principle_response, answer_response),
            metadata={"principles": principle_response.text},
        )
