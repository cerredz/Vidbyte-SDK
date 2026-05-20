from __future__ import annotations

from typing import Self

from vidbyte.strategies.base import BaseStrategy


class StrategyMixin:
    """Mixin for objects that attach a strategy by composition."""

    _strategy: BaseStrategy | None = None

    def with_strategy(self, strategy: BaseStrategy) -> Self:
        self._strategy = strategy
        return self

    @property
    def strategy(self) -> BaseStrategy | None:
        return self._strategy

    def _require_strategy(self) -> BaseStrategy:
        if self._strategy is None:
            raise ValueError("A strategy must be attached before execution.")
        return self._strategy

