from __future__ import annotations

from typing import Any, ClassVar

from vidbyte.strategies.base import BaseStrategy
from vidbyte.strategies.types import StrategyResult


class ReActStrategy(BaseStrategy):
    """Tool-aware ReAct integration point for custom function tools."""

    name: ClassVar[str] = "react"

    async def arun(self, prompt: str, **options: Any) -> StrategyResult:
        model_output = options.get("model_output")
        if isinstance(model_output, str):
            result = await self.tool_executor.execute(model_output)
            return StrategyResult(
                output=result.to_observation_str(),
                strategy_name=self.name,
                metadata={"tool_result": result},
            )
        return StrategyResult(
            output=prompt,
            strategy_name=self.name,
            metadata={"tools": self.tool_registry.specs_as_prompt_str()},
        )

