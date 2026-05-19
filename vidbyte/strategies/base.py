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


def extract_final_answer(text: str) -> str:
    markers = ("final answer:", "final:", "answer:")
    lower = text.lower()
    for marker in markers:
        index = lower.rfind(marker)
        if index >= 0:
            return text[index + len(marker) :].strip()
    return text.strip()


def normalize_answer(text: str) -> str:
    answer = extract_final_answer(text).lower()
    answer = re.sub(r"\s+", " ", answer)
    answer = re.sub(r"[^a-z0-9 ._:/+-]", "", answer)
    return answer.strip()


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


def require_positive(value: int, *, field_name: str) -> None:
    if value <= 0:
        raise StrategyExecutionError(f"{field_name} must be greater than zero.")
