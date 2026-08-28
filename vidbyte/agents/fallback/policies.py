"""Context Protocol Header

FILE: vidbyte/agents/fallback/policies.py
ROLE IN CODEBASE: Public fallback declarations consumed by AgentFallbackSettings
                  and validated by AgentFallbackConfig before runtime use.
FUNCTION INVENTORY: LatencyPolicy and CostBudgetPolicy expose hop_values() plus
    their corresponding deadline_for() or budget_for() lookup.
COMMON MODIFICATION PATTERNS: Add new policy kinds to the shared enum/dataclass
    contract and preserve the one-value-per-transition shape.
WHAT NOT TO DO: Do not duplicate chain-length validation in this declaration module.
KNOWN EDGE CASES: The terminal model has no policy value because it has nowhere
    left to fall back to.
COMMON ERRORS: FallbackConfigurationError is raised by the shared config contract.
PURPOSE: Defines the public per-hop latency and cumulative-cost policy values
         used to trigger proactive model-to-model fallback transitions.
ARCHITECTURE NOTE: Policies are intentionally small declarations. Cross-field
                    validation belongs to vidbyte.lib.dataclasses, not here.
RELATIONS: AgentFallbackSettings accepts these objects; AgentFallbackConfig
           validates their kind, dimensions, numeric values, and lookup method.
RELATED FILES: vidbyte/agents/fallback/chain.py and
               vidbyte/agents/fallback/settings.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.lib.enums import FallbackPolicyType


class LatencyPolicy:
    """Per-hop call deadline; exceeding hop i's timeout advances the chain past model i.

    timeout_seconds_by_hop must have exactly one entry per transition the chain can
    take -- len(models) as declared on AgentFallbackSettings, not len(models) + 1.
    Index i is the deadline enforced while chain index i is in flight. The last
    model in the chain never gets one: there's nowhere left to fall back to.
    """

    policy_type = FallbackPolicyType.LATENCY

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

    policy_type = FallbackPolicyType.COST_BUDGET

    def __init__(self, cost_ceiling_usd_by_hop: Sequence[float]) -> None:
        # Stores one USD ceiling per transition, indexed the same as the resolved model chain.
        self.cost_ceiling_usd_by_hop = tuple(cost_ceiling_usd_by_hop)

    def hop_values(self) -> tuple[float, ...]:
        # Returns the raw per-hop values for AgentFallbackSettings' length/value validation.
        return self.cost_ceiling_usd_by_hop

    def budget_for(self, index: int) -> float | None:
        # Returns the ceiling in effect while chain index `index` is in flight, or None past the array.
        return self.cost_ceiling_usd_by_hop[index] if index < len(self.cost_ceiling_usd_by_hop) else None

    def __repr__(self) -> str:
        # Returns a compact developer-readable string of the configured ceilings.
        return f"CostBudgetPolicy({list(self.cost_ceiling_usd_by_hop)!r})"


__all__ = ["CostBudgetPolicy", "LatencyPolicy"]
