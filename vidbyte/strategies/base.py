from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.types import StrategyResult
from vidbyte.tools.mixins import ToolMixin


class BaseStrategy(ToolMixin, ABC):
    """Async-first strategy base with optional local tools."""

    name: ClassVar[str] = "base"

    @abstractmethod
    async def arun(self, prompt: str, **options: Any) -> StrategyResult:
        """Run the strategy."""

    def run(self, prompt: str, **options: Any) -> StrategyResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(prompt, **options))
        raise StrategyExecutionError("Use 'await strategy.arun(...)' inside an active event loop.")

