from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from vidbyte.strategies.base import BaseStrategy


class StrategyMixin:
    """Composition helpers for SDK classes that delegate to strategies."""

    def __init__(self) -> None:
        self._strategy: BaseStrategy | None = None

    def with_strategy(self, strategy: BaseStrategy) -> "StrategyMixin":
        self._strategy = strategy
        return self

    def with_strategies(self, strategies: Sequence[BaseStrategy], *, evaluator_agent: object | None = None, evaluator_strategy: BaseStrategy | None = None, **options: Any) -> "StrategyMixin":
        from vidbyte.strategies.multi_agent.consensus import MultiAgentConsensusStrategy

        self._strategy = MultiAgentConsensusStrategy(
            strategies=strategies,
            evaluator_agent=evaluator_agent,
            evaluator_strategy=evaluator_strategy,
            **options,
        )
        return self
