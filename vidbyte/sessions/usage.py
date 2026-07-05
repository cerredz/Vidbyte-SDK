"""Session usage rollup builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.sessions import AgentUsage, UsageRollup
from vidbyte.lib.errors import SessionUsageValidationError


class SessionUsageBuilder:
    """Builds a UsageRollup from the head checkpoint's cumulative history."""

    def __init__(self, history: Sequence[Mapping[str, Any]], *, model_name: str | None, latency: float | None, prices: Mapping[str, float] | None) -> None:
        # Bind validated persisted history and pricing context used by build().
        self._validate_history(history)
        self._validate_latency(latency)
        if prices is not None and not isinstance(prices, Mapping):
            raise SessionUsageValidationError("Session usage prices must be a mapping.", details={"field": "prices", "type": type(prices).__name__})
        self._history = history
        self._model_name = model_name
        self._latency = latency
        self._prices = prices
        self._agents: dict[str, dict[str, int]] = {}

    def build(self) -> UsageRollup:
        """Fold usage-bearing messages into a stable typed session rollup."""
        for message in self._history:
            self._validate_message(message)
            if self._message_has_usage(message):
                self._record_message(message)
        per_agent = tuple(self._agent_usage(agent_name, totals) for agent_name, totals in self._agents.items())
        return UsageRollup(
            tokens=sum(agent.tokens for agent in per_agent),
            tool_calls=sum(agent.tool_calls for agent in per_agent),
            turns=sum(agent.turns for agent in per_agent),
            latency=self._latency,
            cost=self._sum_costs(tuple(agent.cost for agent in per_agent)) if self._prices is not None else None,
            per_agent=per_agent,
        )

    @staticmethod
    def _validate_history(history: Sequence[Mapping[str, Any]]) -> None:
        if isinstance(history, (str, bytes)) or not isinstance(history, Sequence):
            raise SessionUsageValidationError("Session usage history must be a sequence of messages.", details={"field": "history", "type": type(history).__name__})

    @staticmethod
    def _validate_latency(latency: float | None) -> None:
        if latency is None:
            return
        if isinstance(latency, bool) or not isinstance(latency, (int, float)):
            raise SessionUsageValidationError("Session usage latency must be numeric or None.", details={"field": "latency", "type": type(latency).__name__})
        if latency < 0:
            raise SessionUsageValidationError("Session usage latency cannot be negative.", details={"field": "latency", "value": latency})

    @staticmethod
    def _validate_message(message: Mapping[str, Any]) -> None:
        if not isinstance(message, Mapping):
            raise SessionUsageValidationError("Session usage history entries must be mappings.", details={"field": "history", "type": type(message).__name__})
        metadata = message.get("metadata")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise SessionUsageValidationError("Session usage message metadata must be a mapping.", details={"field": "metadata", "type": type(metadata).__name__})

    @staticmethod
    def _message_has_usage(message: Mapping[str, Any]) -> bool:
        metadata = message.get("metadata")
        if not isinstance(metadata, Mapping):
            return False
        return "tokens_used" in metadata or "tool_call_count" in metadata

    def _record_message(self, message: Mapping[str, Any]) -> None:
        metadata = message.get("metadata")
        if not isinstance(metadata, Mapping):
            return
        agent_name = str(message.get("sender", ""))
        totals = self._agents.setdefault(agent_name, {"tokens": 0, "tool_calls": 0, "turns": 0})
        totals["tokens"] += self._int_or_zero(metadata.get("tokens_used"), field="tokens_used")
        totals["tool_calls"] += self._int_or_zero(metadata.get("tool_call_count"), field="tool_call_count")
        totals["turns"] += 1

    def _agent_usage(self, agent_name: str, totals: Mapping[str, int]) -> AgentUsage:
        tokens = totals["tokens"]
        price = self._price()
        return AgentUsage(
            agent_name=agent_name,
            tokens=tokens,
            tool_calls=totals["tool_calls"],
            turns=totals["turns"],
            cost=(tokens * price) if price is not None else None,
        )

    @staticmethod
    def _int_or_zero(value: Any, *, field: str) -> int:
        if value is None:
            return 0
        if isinstance(value, bool):
            raise SessionUsageValidationError("Session usage metadata must be numeric.", details={"field": field, "type": type(value).__name__})
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise SessionUsageValidationError("Session usage metadata must be numeric.", details={"field": field, "type": type(value).__name__}) from exc
        if parsed < 0:
            raise SessionUsageValidationError("Session usage metadata cannot be negative.", details={"field": field, "value": parsed})
        return parsed

    def _price(self) -> float | None:
        if self._prices is None or self._model_name is None or self._model_name not in self._prices:
            return None
        raw_price = self._prices[self._model_name]
        if isinstance(raw_price, bool):
            raise SessionUsageValidationError("Session usage price must be numeric.", details={"field": "prices", "model_name": self._model_name, "type": type(raw_price).__name__})
        try:
            price = float(raw_price)
        except (TypeError, ValueError) as exc:
            raise SessionUsageValidationError("Session usage price must be numeric.", details={"field": "prices", "model_name": self._model_name, "type": type(raw_price).__name__}) from exc
        if price < 0:
            raise SessionUsageValidationError("Session usage price cannot be negative.", details={"field": "prices", "model_name": self._model_name, "value": price})
        return price

    @staticmethod
    def _sum_costs(values: Sequence[float | None]) -> float | None:
        if any(value is None for value in values):
            return None
        return sum(float(value) for value in values)


__all__ = ["AgentUsage", "SessionUsageBuilder", "UsageRollup"]
