from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Sequence

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.types import StrategyContext, StrategyResult


class BaseStrategy:
    """Async-first strategy contract."""

    name: ClassVar[str] = "base"

    async def arun(
        self,
        prompt: str,
        *,
        runner: object | None = None,
        context: StrategyContext | None = None,
        tools: Sequence[object] = (),
        **options: Any,
    ) -> StrategyResult:
        raise NotImplementedError(f"{self.__class__.__name__}.arun() is not implemented")

    def run(self, prompt: str, **kwargs: Any) -> StrategyResult:
        """Run a strategy from synchronous code."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(prompt, **kwargs))
        raise StrategyExecutionError(
            "BaseStrategy.run() cannot be called from an active event loop; use await arun()."
        )

    @property
    def strategy_name(self) -> str:
        return getattr(self, "name", self.__class__.__name__)
