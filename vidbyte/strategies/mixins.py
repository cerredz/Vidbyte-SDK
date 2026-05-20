from __future__ import annotations

from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyResult


class StrategyMixin:
    """Mixin for harness-style classes that want to compose a strategy."""

    strategy: BaseStrategy | None = None

    def run_with_strategy(
        self,
        prompt: str,
        *,
        runner: TextModelRunner,
        strategy: BaseStrategy | None = None,
        **options: object,
    ) -> StrategyResult:
        selected_strategy = strategy or self.strategy
        if selected_strategy is None:
            raise ValueError("A strategy must be provided.")
        return selected_strategy.run(prompt, runner=runner, **options)
