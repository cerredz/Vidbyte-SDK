from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import StrategyConfigurationError, StrategyExecutionError, VidbyteSdkError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners import TextModelRunner
from vidbyte.strategies.types import StrategyResult


class BaseStrategy(ABC):
    """Base class for prompt/API-implementable reasoning strategies."""

    name: ClassVar[str]

    def __init__(
        self,
        *,
        runner: TextModelRunner | None = None,
        text_config: TextModelConfig | None = None,
        provider: ModelProvider | str | None = None,
        model: str | None = None,
        transport: HttpTransport | None = None,
        **runner_options: Any,
    ) -> None:
        self._runner = runner or self._build_runner(
            text_config=text_config,
            provider=provider,
            model=model,
            transport=transport,
            runner_options=runner_options,
        )

    @abstractmethod
    def run(self, prompt: str, **options: object) -> StrategyResult:
        """Run the strategy using a text model runner."""

    def _resolve_runner(self, runner: TextModelRunner | None = None) -> TextModelRunner:
        resolved = runner or self._runner
        if resolved is None:
            raise StrategyConfigurationError("Strategy requires a runner or provider/model constructor arguments.")
        return resolved

    def _run_model(self, runner: TextModelRunner, prompt: str) -> object:
        try:
            return runner.run(prompt)
        except VidbyteSdkError:
            raise
        except Exception as exc:
            raise StrategyExecutionError(f"{self.name} strategy failed while running the model.") from exc

    def _build_runner(
        self,
        *,
        text_config: TextModelConfig | None,
        provider: ModelProvider | str | None,
        model: str | None,
        transport: HttpTransport | None,
        runner_options: dict[str, Any],
    ) -> TextModelRunner | None:
        if text_config is None and provider is None and model is None:
            return None
        return TextModelRunner(text_config, provider=provider, model=model, transport=transport, **runner_options)


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


__all__ = [
    "BaseStrategy",
    "BaseStrategyUtils",
]
