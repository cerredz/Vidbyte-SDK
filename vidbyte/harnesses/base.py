from __future__ import annotations

from typing import Any, Sequence

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.mixins import StrategyMixin
from vidbyte.strategies.types import StrategyContext, StrategyResult


class BaseHarness(StrategyMixin):
    """Minimal harness that delegates execution to a composed strategy."""

    def __init__(self) -> None:
        super().__init__()

    async def arun(self, prompt: str, *, runner: object | None = None, context: StrategyContext | None = None, tools: Sequence[object] = (), **options: Any) -> StrategyResult:
        if self._strategy is None:
            raise StrategyExecutionError("No strategy has been attached to this harness.")
        return await self._strategy.arun(
            prompt,
            runner=runner,
            context=context,
            tools=tools,
            **options,
        )

    def run(self, prompt: str, **options: Any) -> StrategyResult:
        if self._strategy is None:
            raise StrategyExecutionError("No strategy has been attached to this harness.")
        return self._strategy.run(prompt, **options)
