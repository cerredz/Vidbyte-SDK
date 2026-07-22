"""Context Protocol Header

Description:
    Per-run accumulator turning model responses into priced usage records.
Purpose:
    Owns the run's usage ledger so the agent runtime can record each model call
    once and the agent API can expose live and final usage/cost rollups.
Architecture:
    - UsageTracker: Mutable per-run store; defensively parses duck-typed
      responses, prices via ModelPricingRegistry, notifies on_usage callbacks.
Key Functions:
    - record_call: Parses, prices, stores, and broadcasts one model call.
    - rollup: Folds the ledger into an immutable UsageRollup.
    - reset: Clears the ledger at the start of a new run.
Relations:
    Created by BaseAgent, consumed by AgentRuntime; pricing from
    vidbyte/lib/registries/pricing.py.
Similar Files:
    - vidbyte/agents/pricing/records.py
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from vidbyte.agents.pricing.base import parse_usage
from vidbyte.agents.pricing.records import UsageRecord, UsageRollup
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.pricing import ModelPricingRegistry


class UsageTracker:
    """Accumulates priced usage records for one agent run."""

    def __init__(self, *, pricing: ModelPricingRegistry | None = None, on_usage: Callable[[UsageRecord], None] | None = None) -> None:
        # Bind the pricing registry and optional per-call callback for this tracker.
        self._pricing = pricing or ModelPricingRegistry.default()
        self._on_usage = on_usage
        self._records: list[UsageRecord] = []
        self._callback_errors: list[Exception] = []

    def record_call(self, response: object) -> UsageRecord | None:
        # Parses, prices, and stores one model call; returns None when unusable.
        provider = getattr(response, "provider", None)
        model = getattr(response, "model", "")
        payload = getattr(response, "usage", None)
        usage = parse_usage(provider, payload if isinstance(payload, Mapping) else None)
        if usage is None:
            return None
        record = UsageRecord(
            call_index=len(self._records) + 1,
            provider=provider.value if isinstance(provider, ModelProvider) else str(provider),
            model=str(model),
            usage=usage,
            cost_usd=usage.cost_usd(self._pricing.resolve(provider, str(model))),
        )
        self._records.append(record)
        self._notify(record)
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
        # Clears all recorded calls and callback errors for a fresh run.
        self._records.clear()
        self._callback_errors.clear()

    @property
    def records(self) -> tuple[UsageRecord, ...]:
        # Returns the immutable per-call ledger recorded so far.
        return tuple(self._records)

    @property
    def callback_errors(self) -> tuple[Exception, ...]:
        # Returns exceptions raised by the on_usage callback, captured not raised.
        return tuple(self._callback_errors)

    def _notify(self, record: UsageRecord) -> None:
        # Invokes the on_usage callback, capturing failures instead of breaking runs.
        if self._on_usage is None:
            return
        try:
            self._on_usage(record)
        except Exception as exc:
            self._callback_errors.append(exc)


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
