"""Typed usage rollups for durable sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentUsage:
    """Usage totals for one agent within a durable session."""

    agent_name: str
    tokens: int
    tool_calls: int
    turns: int
    cost: float | None = None


@dataclass(frozen=True, slots=True)
class UsageRollup:
    """Usage totals for a durable session, with a per-agent breakdown."""

    tokens: int
    tool_calls: int
    turns: int
    latency: float | None
    cost: float | None
    per_agent: tuple[AgentUsage, ...]

    @classmethod
    def empty(cls) -> "UsageRollup":
        # Return the zero-value rollup for sessions with no head checkpoint.
        return cls(tokens=0, tool_calls=0, turns=0, latency=None, cost=None, per_agent=())


class _UsageRollupBuilder:
    """Builds a UsageRollup from the head checkpoint's cumulative history."""

    def __init__(self, history: Sequence[Mapping[str, Any]], *, model_name: str | None, latency: float | None, prices: Mapping[str, float] | None) -> None:
        # Bind the persisted history and pricing context used by build().
        self._history = history
        self._model_name = model_name
        self._latency = latency
        self._prices = prices
        self._agents: dict[str, dict[str, int]] = {}

    def build(self) -> UsageRollup:
        # Fold usage-bearing messages into a stable typed session rollup.
        for message in self._history:
            if self._message_has_usage(message):
                self._record_message(message)
        per_agent = tuple(self._agent_usage(agent_name, totals) for agent_name, totals in self._agents.items())
        return UsageRollup(
            tokens=sum(agent.tokens for agent in per_agent),
            tool_calls=sum(agent.tool_calls for agent in per_agent),
            turns=sum(agent.turns for agent in per_agent),
            latency=self._latency,
            cost=_sum_or_none(tuple(agent.cost for agent in per_agent)) if self._prices is not None else None,
            per_agent=per_agent,
        )

    def _message_has_usage(self, message: Mapping[str, Any]) -> bool:
        # Return true when a persisted message carries runtime usage metadata.
        metadata = message.get("metadata")
        if not isinstance(metadata, Mapping):
            return False
        return "tokens_used" in metadata or "tool_call_count" in metadata

    def _record_message(self, message: Mapping[str, Any]) -> None:
        # Add one usage-bearing message into the per-agent accumulator.
        metadata = message.get("metadata")
        if not isinstance(metadata, Mapping):
            return
        agent_name = str(message.get("sender", ""))
        totals = self._agents.setdefault(agent_name, {"tokens": 0, "tool_calls": 0, "turns": 0})
        totals["tokens"] += _int_or_zero(metadata.get("tokens_used"))
        totals["tool_calls"] += _int_or_zero(metadata.get("tool_call_count"))
        totals["turns"] += 1

    def _agent_usage(self, agent_name: str, totals: Mapping[str, int]) -> AgentUsage:
        # Materialize one accumulated agent entry with an optional cost.
        tokens = totals["tokens"]
        price = _price(self._model_name, self._prices)
        return AgentUsage(
            agent_name=agent_name,
            tokens=tokens,
            tool_calls=totals["tool_calls"],
            turns=totals["turns"],
            cost=(tokens * price) if price is not None else None,
        )


def _int_or_zero(value: Any) -> int:
    # Coerce numeric metadata to int, treating missing or malformed values as zero.
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _price(model_name: str | None, prices: Mapping[str, float] | None) -> float | None:
    # Return the caller-supplied per-token price for the model, if available.
    if prices is None or model_name is None or model_name not in prices:
        return None
    try:
        return float(prices[model_name])
    except (TypeError, ValueError):
        return None


def _sum_or_none(values: Sequence[float | None]) -> float | None:
    # Sum costs only when every entry has a known cost.
    if any(value is None for value in values):
        return None
    return sum(float(value) for value in values)


__all__ = ["AgentUsage", "UsageRollup"]
