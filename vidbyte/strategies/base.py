from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import ClassVar

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.types import StrategyResult


class BaseStrategy(ABC):
    """Base class for prompt/API-implementable reasoning strategies."""

    name: ClassVar[str]

    @abstractmethod
    def run(self, prompt: str, *, runner: TextModelRunner, **options: object) -> StrategyResult:
        """Run the strategy using a text model runner."""


class BaseStrategyUtils:
    """Shared utility functions for prompt/API strategy implementations."""

    @staticmethod
    def extract_final_answer(text: str) -> str:
        # Extract the final answer segment when a strategy asks for an answer marker.
        markers = ("final answer:", "final:", "answer:")
        lower = text.lower()
        for marker in markers:
            index = lower.rfind(marker)
            if index >= 0:
                return text[index + len(marker) :].strip()
        return text.strip()

    @staticmethod
    def normalize_answer(text: str) -> str:
        # Normalize answers for voting/convergence without changing stored raw calls.
        answer = BaseStrategyUtils.extract_final_answer(text).lower()
        answer = re.sub(r"\s+", " ", answer)
        answer = re.sub(r"[^a-z0-9 ._:/+-]", "", answer)
        return answer.strip()

    @staticmethod
    def parse_numbered_lines(text: str) -> tuple[str, ...]:
        # Parse numbered or bulleted plan/skeleton lines into clean step text.
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
        # Keep user-configurable strategy fanout and budgets positive.
        if value <= 0:
            raise StrategyExecutionError(f"{field_name} must be greater than zero.")


def extract_final_answer(text: str) -> str:
    # Back-compatible wrapper around BaseStrategyUtils.
    return BaseStrategyUtils.extract_final_answer(text)


def normalize_answer(text: str) -> str:
    # Back-compatible wrapper around BaseStrategyUtils.
    return BaseStrategyUtils.normalize_answer(text)


def parse_numbered_lines(text: str) -> tuple[str, ...]:
    # Back-compatible wrapper around BaseStrategyUtils.
    return BaseStrategyUtils.parse_numbered_lines(text)


def require_positive(value: int, *, field_name: str) -> None:
    # Back-compatible wrapper around BaseStrategyUtils.
    BaseStrategyUtils.require_positive(value, field_name=field_name)


__all__ = [
    "BaseStrategy",
    "BaseStrategyUtils",
    "extract_final_answer",
    "normalize_answer",
    "parse_numbered_lines",
    "require_positive",
]
