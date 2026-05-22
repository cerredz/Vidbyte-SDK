from __future__ import annotations

from typing import Any

from vidbyte.agents.base import BaseAgent
from vidbyte.agents.types import AgentMessage
from vidbyte.lib.errors import StrategyExecutionError
from vidbyte.strategies.base import BaseStrategy


class BaseMultiAgentStrategy(BaseStrategy):
    """Shared helpers for local multi-agent orchestration strategies."""

    name = "multi_agent.base"

    def __init__(self, *, max_calls: int = 20) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1.")
        self.max_calls = max_calls
        self._call_count = 0

    def _reset_calls(self) -> None:
        self._call_count = 0

    def _count_call(self) -> None:
        self._call_count += 1
        if self._call_count > self.max_calls:
            raise StrategyExecutionError("Multi-agent strategy exceeded max_calls.")

    def _safe_error(self, exc: BaseException) -> str:
        message = str(exc)
        if len(message) > 500:
            message = message[:497] + "..."
        return message

    async def _run_agent(self, agent: BaseAgent, prompt: str, **options: Any) -> AgentMessage:
        self._count_call()
        return await agent.generate_reply(prompt, **options)
