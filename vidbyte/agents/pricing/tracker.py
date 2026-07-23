"""Context Protocol Header

Description:
    Per-run accumulator turning model responses into priced usage records.
Purpose:
    Owns the run's usage ledger so the agent runtime can record each model call
    once and the agent API can expose live and final usage/cost rollups.
Architecture:
    - UsageTracker: Mutable per-run store; defensively parses duck-typed
      responses and prices them via ModelPricingRegistry.
Key Functions:
    - record_call: Parses, prices, and stores one model call.
    - rollup: Folds the ledger into an immutable UsageRollup.
    - reset: Clears the ledger at the start of a new run.
Relations:
    Created by BaseAgent, consumed by AgentRuntime; pricing from
    vidbyte/lib/registries/pricing.py.
Similar Files:
    - vidbyte/agents/pricing/records.py
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from vidbyte.agents.pricing.base import parse_usage
from vidbyte.agents.pricing.records import UsageRecord, UsageRollup
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricingRegistry


class UsageTracker:
    """Accumulates priced usage records for one agent run."""

    def __init__(self, *, pricing: ModelPricingRegistry | None = None) -> None:
        # Bind the pricing registry for this tracker; defaults to the built-in table.
        self._pricing = pricing or ModelPricingRegistry.default()
        self._records: list[UsageRecord] = []

    def record_call(self, response: object) -> UsageRecord | None:
        # Parses, prices, and stores one model call; returns None when unusable.
        # The duck-typed response.provider is coerced to a ModelProvider once here,
        # so the pricing registry and parser downstream take only the strict enum.
        provider = _as_provider(getattr(response, "provider", None))
        model = getattr(response, "model", "")
        payload = getattr(response, "usage", None)
        usage = parse_usage(provider, payload if isinstance(payload, Mapping) else None)
        if usage is None or provider is None:
            return None
        record = UsageRecord(
            call_index=len(self._records) + 1,
            provider=provider.value,
            model=str(model),
            usage=usage,
            cost_usd=usage.cost_usd(self._pricing.resolve(provider, str(model))),
        )
        self._records.append(record)
        return record

    def rollup(self) -> UsageRollup:
        # Folds the recorded calls into an immutable None-aware rollup.
        records = tuple(self._records)
        return UsageRollup(
            calls=records,
            model_call_count=len(records),
            input_tokens=_sum_or_none(record.usage.input_tokens for record in records),
            output_tokens=_sum_or_none(record.usage.output_tokens for record in records),
            total_tokens=_sum_or_none(record.usage.total_tokens for record in records),
            cost_usd=_sum_or_none(record.cost_usd for record in records),
            cost_complete=bool(records) and all(record.cost_usd is not None for record in records),
        )

    def reset(self) -> None:
        # Clears all recorded calls for a fresh run.
        self._records.clear()

    @property
    def records(self) -> tuple[UsageRecord, ...]:
        # Returns the immutable per-call ledger recorded so far.
        return tuple(self._records)


def _as_provider(value: object) -> ModelProvider | None:
    # Normalizes a duck-typed response.provider onto the ModelProvider frozen set,
    # returning None when the value names no known provider.
    if isinstance(value, ModelProvider):
        return value
    try:
        return ModelProvider(str(value))
    except (ValueError, TypeError):
        return None


def _sum_or_none(values: Iterable[int | float | None]) -> int | float | None:
    # Sums numeric values, returning None when every value is None.
    total: int | float = 0
    seen = False
    for value in values:
        if value is None:
            continue
        total += value
        seen = True
    return total if seen else None


__all__ = ["UsageTracker"]
