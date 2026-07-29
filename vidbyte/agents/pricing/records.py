"""Context Protocol Header

Description:
    Immutable per-call and per-run usage records for agent usage tracking.
Purpose:
    Gives the runtime, middleware, and agent API stable typed shapes for one
    priced model call (UsageRecord) and a whole run (UsageRollup).
Architecture:
    - UsageRecord: One model call with its provider-native usage and USD cost.
    - OperationUsageRecord: One priced search/fetch operation and its USD cost.
    - UsageRollup: The per-call and per-operation ledgers plus None-aware totals.
Relations:
    Built by vidbyte/agents/pricing/tracker.py; surfaced on
    AgentMessage.metadata["usage_rollup"] and BaseAgent.get_usage().
Similar Files:
    - vidbyte/agents/pricing/base.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vidbyte.agents.pricing.base import ProviderUsage


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """One priced model call: provider-native usage plus its USD cost or None."""

    call_index: int
    provider: str
    model: str
    usage: ProviderUsage
    cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class OperationUsageRecord:
    """One priced search/fetch operation: its billed units plus USD cost or None."""

    call_index: int
    operation: str
    provider: str
    mode: str = "default"
    units: int | float = 1
    meter: str = "unit"
    cost_usd: float | None = None
    provider_reported_cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class UsageRollup:
    """Whole-run usage ledger; cost_complete is False when any call is unpriced."""

    calls: tuple[UsageRecord, ...] = field(default_factory=tuple)
    model_call_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    cost_complete: bool = False
    operations: tuple[OperationUsageRecord, ...] = field(default_factory=tuple)
    operation_count: int = 0


__all__ = [
    "OperationUsageRecord",
    "UsageRecord",
    "UsageRollup",
]
