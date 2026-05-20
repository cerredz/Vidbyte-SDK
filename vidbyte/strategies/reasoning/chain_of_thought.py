from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.runners import TextModelResponse, TextModelRunner
from vidbyte.prompts.strategies import ChainOfThoughtPrompts
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyResult


class ChainOfThoughtStrategy(BaseStrategy):
    name: ClassVar[str] = "chain_of_thought"
    prompts: ClassVar[dict[str, str]] = ChainOfThoughtPrompts().export()

    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        response = self._reason(prompt, runner=runner)
        return StrategyResult(output=response.text, strategy_name=self.name, calls=(response,), metadata={"style": "sequential_reasoning"})

    def _reason(self, prompt: str, *, runner: TextModelRunner) -> TextModelResponse:
        # Build the single chain-of-thought call from the configured reason prompt.
        return runner.run(f"{self.prompts['reason_prompt']}\n\n{prompt}")


__all__ = [
    "ChainOfThoughtStrategy",
]
