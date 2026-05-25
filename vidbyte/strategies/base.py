from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any, ClassVar, Sequence

from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.types import StrategyContext, StrategyResult


class BaseStrategy:
    """Async-first strategy contract."""

    name: ClassVar[str] = "base"
    description: ClassVar[str] = ""

    def __init__(self, *, runner: object | None = None, **kwargs: Any) -> None:
        self._runner = runner

    async def arun(self, prompt: str, *, runner: object | None = None, context: StrategyContext | None = None, tools: Sequence[object] = (), **options: Any) -> StrategyResult:
        if type(self).run is BaseStrategy.run:
            raise NotImplementedError(f"{self.__class__.__name__}.arun() is not implemented")
        result = self._call_run_from_async(
            prompt,
            {
                "runner": runner,
                "context": context,
                "tools": tools,
                **options,
            },
        )
        if inspect.isawaitable(result):
            result = await result
        return result

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

    def _resolve_runner(self, runner: object | None) -> object:
        resolved = runner or self._runner
        if resolved is None:
            raise StrategyExecutionError(
                f"{self.__class__.__name__} requires a runner. Pass one to run() or set it in __init__."
            )
        return resolved

    def as_tool(
        self,
        agent: object,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> object:
        """Return a StrategyTool wrapping this strategy bound to *agent*."""
        from vidbyte.tools.strategy_tool import StrategyTool

        return StrategyTool(agent, name=name, description=description)  # type: ignore[arg-type]

    def _run_model(self, runner: object, prompt: str, **kwargs: Any) -> Any:
        return runner.run(prompt, **dict(kwargs))  # type: ignore[union-attr]

    def _call_run_from_async(self, prompt: str, call_options: dict[str, Any]) -> Any:
        run = self.run
        try:
            signature = inspect.signature(run)
        except (TypeError, ValueError):
            return run(prompt, **call_options)
        if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return run(prompt, **call_options)
        accepted = {
            name
            for name, param in signature.parameters.items()
            if param.kind in {inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        }
        filtered = {key: value for key, value in call_options.items() if key in accepted}
        return run(prompt, **filtered)


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
