"""Context Protocol Header

Description:
    Defines the per-hop fallback policy classes: LatencyPolicy and CostBudgetPolicy.
Purpose:
    Lets a developer declare a deadline or a cost ceiling for each transition in a
    fallback chain, so the runtime can advance to the next model proactively instead
    of only reacting to a raised provider exception. Policies that can vote at the
    runtime's top-of-iteration checkpoint expose triggered(), which FallbackPolicyMode
    composes into ANY/ALL trigger semantics.
Architecture:
    - LatencyPolicy: One deadline per hop, enforced by wrapping the model call.
    - CostBudgetPolicy: One USD ceiling per hop, checked against live usage.
    - FallbackSignals: Frozen usage snapshot a checkpoint policy votes against.
    - Both per-hop policies expose hop_values() so AgentFallbackSettings can validate
      array length and element values without knowing about either class by name.
Relations:
    Consumed by vidbyte.agents.fallback.chain.AgentFallback (deadline_for,
    advance_after_checkpoint) and validated by vidbyte.agents.fallback.settings.
Similar Files:
    - vidbyte/agents/fallback/chain.py: Folds these policies into per-index lookups.
    - vidbyte/agents/fallback/settings.py: Validates hop_values() against chain length.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FallbackSignals:
    """Usage snapshot a checkpoint policy votes against; a None signal is unmeasurable, never a trigger."""

    cost_usd: float | None = None
    total_tokens: int | None = None


class LatencyPolicy:
    """Per-hop call deadline; exceeding hop i's timeout advances the chain past model i.

    timeout_seconds_by_hop must have exactly one entry per transition the chain can
    take -- len(models) as declared on AgentFallbackSettings, not len(models) + 1.
    Index i is the deadline enforced while chain index i is in flight. The last
    model in the chain never gets one: there's nowhere left to fall back to.
    """

    def __init__(self, timeout_seconds_by_hop: Sequence[float]) -> None:
        # Stores one deadline per transition, indexed the same as the resolved model chain.
        self.timeout_seconds_by_hop = tuple(timeout_seconds_by_hop)

    def hop_values(self) -> tuple[float, ...]:
        # Returns the raw per-hop values for AgentFallbackSettings' length/value validation.
        return self.timeout_seconds_by_hop

    def deadline_for(self, index: int) -> float | None:
        # Returns the deadline enforced while chain index `index` is in flight, or None past the array.
        return self.timeout_seconds_by_hop[index] if index < len(self.timeout_seconds_by_hop) else None

    def __repr__(self) -> str:
        # Returns a compact developer-readable string of the configured deadlines.
        return f"LatencyPolicy({list(self.timeout_seconds_by_hop)!r})"


class CostBudgetPolicy:
    """Per-hop cumulative-cost ceiling; crossing hop i's ceiling advances the chain past model i.

    cost_ceiling_usd_by_hop must have exactly one entry per transition the chain can
    take -- len(models) as declared on AgentFallbackSettings, not len(models) + 1.
    Index i is the ceiling in effect while chain index i is in flight. The last
    model in the chain never gets one: there's nowhere cheaper left to go.
    """

    def __init__(self, cost_ceiling_usd_by_hop: Sequence[float]) -> None:
        # Stores one USD ceiling per transition, indexed the same as the resolved model chain.
        self.cost_ceiling_usd_by_hop = tuple(cost_ceiling_usd_by_hop)

    def hop_values(self) -> tuple[float, ...]:
        # Returns the raw per-hop values for AgentFallbackSettings' length/value validation.
        return self.cost_ceiling_usd_by_hop

    def budget_for(self, index: int) -> float | None:
        # Returns the ceiling in effect while chain index `index` is in flight, or None past the array.
        return self.cost_ceiling_usd_by_hop[index] if index < len(self.cost_ceiling_usd_by_hop) else None

    reason = "cost_budget_exceeded"

    def triggered(self, index: int, signals: FallbackSignals) -> bool:
        # Votes True when run cost is known and at/above this hop's ceiling; unmeasurable votes False.
        return signals.cost_usd is not None and signals.cost_usd >= self.budget_for(index)

    def __repr__(self) -> str:
        # Returns a compact developer-readable string of the configured ceilings.
        return f"CostBudgetPolicy({list(self.cost_ceiling_usd_by_hop)!r})"


__all__ = ["CostBudgetPolicy", "FallbackSignals", "LatencyPolicy"]
