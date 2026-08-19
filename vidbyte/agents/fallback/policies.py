"""Context Protocol Header

Description:
    Defines the per-hop fallback policy classes: LatencyPolicy, CostBudgetPolicy, and ErrorRatePolicy.
Purpose:
    Lets a developer declare a deadline, a cost ceiling, or an error-ratio ceiling for each
    transition in a fallback chain, so the runtime can advance to the next model proactively
    instead of only reacting to a raised provider exception.
Architecture:
    - LatencyPolicy: One deadline per hop, enforced by wrapping the model call.
    - CostBudgetPolicy: One USD ceiling per hop, checked against live usage.
    - ErrorRatePolicy: One cumulative failure-ratio ceiling per hop, checked against a
      per-run attempt tally recorded at the model-call site.
    - All three expose hop_values() so AgentFallbackSettings can validate array length
      and element values without knowing about any class by name.
Relations:
    Consumed by vidbyte.agents.fallback.chain.AgentFallback (deadline_for/budget_for/
    advance_after_error_rate) and validated by vidbyte.agents.fallback.settings.AgentFallbackSettings.
Similar Files:
    - vidbyte/agents/fallback/chain.py: Folds these policies into per-index lookups.
    - vidbyte/agents/fallback/settings.py: Validates hop_values() against chain length.
"""

from __future__ import annotations

from collections.abc import Sequence

from vidbyte.lib.errors import ConfigurationError


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

    def __repr__(self) -> str:
        # Returns a compact developer-readable string of the configured ceilings.
        return f"CostBudgetPolicy({list(self.cost_ceiling_usd_by_hop)!r})"


class ErrorRatePolicy:
    """Per-hop cumulative error-ratio ceiling; a model whose share of failed calls crosses hop i's ceiling is skipped on the next iteration.

    max_error_ratio_by_hop must have exactly one entry per transition the chain can
    take -- len(models) as declared on AgentFallbackSettings, not len(models) + 1.
    Index i is the ceiling in effect while chain index i is in flight. The last
    model in the chain never gets one: there's nowhere else to go.

    The ratio counts every invoke attempt on the model since the run reached it,
    including attempts a retry recovered -- those recovered failures are exactly
    the "retry tax" this policy exists to detect. A provider failing one call in
    five with one retry each shows 2 failures in 4 attempts (0.5), not 0.2: read
    the ceiling as "how much retry tax am I willing to pay", not the provider's
    raw error rate. min_attempts is the number of attempts required before the
    ratio is trusted at all.
    """

    def __init__(self, max_error_ratio_by_hop: Sequence[float], *, min_attempts: int = 3) -> None:
        # Stores one ratio ceiling per transition plus a global warm-up floor, validated eagerly.
        if min_attempts < 1:
            raise ConfigurationError(f"ErrorRatePolicy min_attempts must be >= 1, got {min_attempts}.")
        for position, ratio in enumerate(max_error_ratio_by_hop):
            if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 < ratio <= 1:
                raise ConfigurationError(
                    f"ErrorRatePolicy max_error_ratio_by_hop[{position}] must be a ratio in (0, 1], got {ratio!r}."
                )
        self.max_error_ratio_by_hop = tuple(max_error_ratio_by_hop)
        self.min_attempts = min_attempts

    def hop_values(self) -> tuple[float, ...]:
        # Returns the raw per-hop values for AgentFallbackSettings' length/value validation.
        return self.max_error_ratio_by_hop

    def error_ratio_for(self, index: int) -> float | None:
        # Returns the ceiling in effect while chain index `index` is in flight, or None past the array.
        return self.max_error_ratio_by_hop[index] if index < len(self.max_error_ratio_by_hop) else None

    def __repr__(self) -> str:
        # Returns a compact developer-readable string of the configured ceilings.
        return f"ErrorRatePolicy({list(self.max_error_ratio_by_hop)!r}, min_attempts={self.min_attempts})"


__all__ = ["CostBudgetPolicy", "ErrorRatePolicy", "LatencyPolicy"]
