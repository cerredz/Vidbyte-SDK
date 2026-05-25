from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyContext, StrategyResult


class StrategyChain(BaseStrategy):
    """Run strategies sequentially, passing only output text between stages."""

    name: ClassVar[str] = "strategy_chain"
    description: ClassVar[str] = "Run multiple strategies in sequence."

    def __init__(self, strategies: Sequence[BaseStrategy]) -> None:
        if not strategies:
            raise StrategyExecutionError("StrategyChain requires at least one strategy.")
        self.strategies = tuple(strategies)

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult:
        current = prompt
        results: list[StrategyResult] = []
        stages: list[dict[str, object]] = []
        for index, strategy in enumerate(self.strategies):
            result = await strategy.arun(
                current,
                runner=runner,
                context=context,
                tools=tools,
                **options,
            )
            results.append(result)
            stages.append(
                {
                    "index": index,
                    "strategy_name": result.strategy_name,
                    "metadata": dict(result.metadata),
                }
            )
            current = result.output
        return StrategyResult(
            output=current,
            strategy_name=self.name,
            calls=tuple(results),
            metadata={
                "stage_count": len(results),
                "stage_names": tuple(result.strategy_name for result in results),
                "stages": tuple(stages),
            },
        )


__all__ = ["StrategyChain"]
