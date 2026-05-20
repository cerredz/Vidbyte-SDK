from __future__ import annotations

import asyncio
import re
from typing import Any, ClassVar, Sequence

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.types import StrategyContext, StrategyResult


class BaseStrategy:
    """Async-first strategy contract."""

    name: ClassVar[str] = "base"

    async def arun(self, prompt: str, *, runner: object | None = None, context: StrategyContext | None = None, tools: Sequence[object] = (), **options: Any) -> StrategyResult:
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


class BaseStrategyUtils:
    """Shared utility functions for prompt/API strategy implementations."""

    @staticmethod
    def extract_final_answer(text: str) -> str:
        markers = ("final answer:", "final:", "answer:")
        lower = text.lower()
        for marker in markers:
            index = lower.rfind(marker)
            if index >= 0:
                return text[index + len(marker):].strip()
        return text.strip()

    @staticmethod
    def normalize_answer(text: str) -> str:
        answer = BaseStrategyUtils.extract_final_answer(text).lower()
        answer = re.sub(r"\s+", " ", answer)
        answer = re.sub(r"[^a-z0-9 ._:/+-]", "", answer)
        return answer.strip()

    @staticmethod
    def parse_numbered_lines(text: str) -> tuple[str, ...]:
        items: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            item = re.sub(r"^[-*]\s+", "", stripped)
            item = re.sub(r"^\d+[.)]\s+", "", item)
            if item:
                items.append(item)
        return tuple(items)

    @staticmethod
    def require_positive(value: int, *, field_name: str) -> None:
        if value <= 0:
            raise StrategyExecutionError(f"{field_name} must be greater than zero.")

    @staticmethod
    def require_non_empty(value: str, *, field_name: str) -> str:
        if not value or not value.strip():
            raise StrategyExecutionError(f"{field_name} must not be empty.")
        return value


__all__ = [
    "BaseStrategy",
    "BaseStrategyUtils",
]
