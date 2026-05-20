from __future__ import annotations

from typing import Any

from vidbyte.strategies.mixins import StrategyMixin
from vidbyte.strategies.types import StrategyResult
from vidbyte.tools.mixins import ToolMixin


class BaseHarness(StrategyMixin, ToolMixin):
    """Base harness that cascades attached tools into its strategy."""

    async def arun(self, prompt: str, **options: Any) -> StrategyResult:
        strategy = self._require_strategy()
        self._copy_tools_to(strategy)
        return await strategy.arun(prompt, **options)

    def run(self, prompt: str, **options: Any) -> StrategyResult:
        strategy = self._require_strategy()
        self._copy_tools_to(strategy)
        return strategy.run(prompt, **options)

