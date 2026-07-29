"""Context Protocol Header

Description:
    Per-run accumulator turning model responses into priced usage records.
Purpose:
    Owns the run's usage ledger so the agent runtime can record each model call
    once and the agent API can expose live and final usage/cost rollups.
Architecture:
    - UsageTracker: Mutable per-run store holding two ledgers — priced model
      calls (token axis) and priced search/fetch operations (operation axis) —
      priced via ModelPricingRegistry and OperationPricingRegistry.
Key Functions:
    - record_call: Parses, prices, and stores one model call.
    - record_operation: Prices and stores one search/fetch operation.
    - rollup: Folds both ledgers into an immutable UsageRollup.
    - reset: Clears both ledgers at the start of a new run.
Relations:
    Created by BaseAgent, consumed by AgentRuntime; token pricing from
    vidbyte/lib/registries/pricing.py, operation pricing from
    vidbyte/lib/registries/operation_pricing.py.
Similar Files:
    - vidbyte/agents/pricing/records.py
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from vidbyte.agents.pricing.records import OperationUsageRecord, UsageRecord, UsageRollup
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.registries.operation_pricing import OperationPricingRegistry
from vidbyte.lib.registries.pricing import ModelPricingRegistry

if TYPE_CHECKING:
    from vidbyte.agents.pricing.base import ProviderUsage


class UsageTracker:
    """Accumulates priced usage records for one agent run."""

    def __init__(self, *, pricing: ModelPricingRegistry | None = None, operation_pricing: OperationPricingRegistry | None = None) -> None:
        # Bind both pricing registries for this tracker; each defaults to its built-in table.
        self._pricing = pricing or ModelPricingRegistry.default()
        self._operation_pricing = operation_pricing or OperationPricingRegistry.default()
        self._records: list[UsageRecord] = []
        self._operations: list[OperationUsageRecord] = []

    def record_call(self, response: object) -> UsageRecord | None:
        # Parses, prices, and stores one model call; returns None when unusable.
        # The duck-typed response.provider is coerced to a ModelProvider once here,
        # so the pricing registry and parser downstream take only the strict enum.
        provider = _as_provider(getattr(response, "provider", None))
        model = getattr(response, "model", "")
        payload = getattr(response, "usage", None)
        usage = _parse_usage(provider, payload)
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

    def record_operation(self, operation: str, provider: str, *, mode: str = "default", units: int | float = 1, meter: str = "unit", reported_cost_usd: float | None = None, provider_reported_cost_usd: float | None = None) -> OperationUsageRecord | None:
        # Prices one operation strictly from the configured SDK pricebook.
        if not _is_billable_key(operation, provider) or not _is_numeric_units(units) or not isinstance(meter, str) or not meter.strip():
            return None
        provider_cost = provider_reported_cost_usd if provider_reported_cost_usd is not None else reported_cost_usd
        pricing = self._operation_pricing.resolve(operation, provider, mode)
        record = OperationUsageRecord(
            call_index=len(self._operations) + 1,
            operation=operation,
            provider=provider,
            mode=mode,
            units=units,
            meter=meter,
            cost_usd=_pricebook_cost(pricing, units),
            provider_reported_cost_usd=_valid_reported_cost(provider_cost),
        )
        self._operations.append(record)
        return record

    def rollup(self) -> UsageRollup:
        # Folds both ledgers into an immutable None-aware rollup whose cost spans
        # the token and operation axes and whose cost_complete requires every
        # recorded item on both axes to be priced.
        records = tuple(self._records)
        operations = tuple(self._operations)
        token_costs = [record.cost_usd for record in records]
        operation_costs = [operation.cost_usd for operation in operations]
        return UsageRollup(
            calls=records,
            model_call_count=len(records),
            input_tokens=_sum_or_none(record.usage.input_tokens for record in records),
            output_tokens=_sum_or_none(record.usage.output_tokens for record in records),
            total_tokens=_sum_or_none(record.usage.total_tokens for record in records),
            cost_usd=_sum_or_none(token_costs + operation_costs),
            cost_complete=bool(records or operations) and all(cost is not None for cost in token_costs + operation_costs),
            operations=operations,
            operation_count=len(operations),
        )

    def reset(self) -> None:
        # Clears both the model-call and operation ledgers for a fresh run.
        self._records.clear()
        self._operations.clear()

    @property
    def records(self) -> tuple[UsageRecord, ...]:
        # Returns the immutable per-call ledger recorded so far.
        return tuple(self._records)

    @property
    def operations(self) -> tuple[OperationUsageRecord, ...]:
        # Returns the immutable per-operation ledger recorded so far.
        return tuple(self._operations)


def _parse_usage(provider: ModelProvider | None, payload: object) -> ProviderUsage | None:
    # Resolves the provider's usage parser off the enum and applies it defensively;
    # never raises, returning None for an unknown provider or an unusable payload.
    if provider is None or not isinstance(payload, Mapping):
        return None
    usage_cls = provider.usage_class()
    if usage_cls is None:
        return None
    try:
        return usage_cls.from_usage_payload(payload)
    except Exception:
        return None


def _as_provider(value: object) -> ModelProvider | None:
    # Normalizes a duck-typed response.provider onto the ModelProvider frozen set,
    # returning None when the value names no known provider.
    if isinstance(value, ModelProvider):
        return value
    try:
        return ModelProvider(str(value))
    except (ValueError, TypeError):
        return None


def _is_billable_key(operation: str, provider: str) -> bool:
    # True when both operation and provider are non-empty strings worth pricing.
    return isinstance(operation, str) and bool(operation.strip()) and isinstance(provider, str) and bool(provider.strip())


def _pricebook_cost(pricing: object, units: int | float) -> float | None:
    # Computes cost only from the pricebook so vendor-reported dollars cannot alter SDK billing.
    if pricing is None:
        return None
    return pricing.cost_usd(units)


def _valid_reported_cost(value: object) -> float | None:
    # Preserves a non-negative provider estimate for reconciliation without billing from it.
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _is_numeric_units(value: object) -> bool:
    # Accepts finite non-negative quantities for request, page, credit, or time meters.
    import math

    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and value >= 0


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
