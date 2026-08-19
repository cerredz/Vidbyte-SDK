"""Context Protocol Header

Description:
    Defines the fallback policy classes: LatencyPolicy, CostBudgetPolicy,
    ErrorRatePolicy, and ToolCallLoopPolicy.
Purpose:
    Lets a developer declare a deadline, a cost ceiling, or an error-ratio ceiling
    for each transition in a fallback chain, or a repeated-tool-call detector for
    the chain as a whole, so the runtime can advance to the next model proactively
    instead of only reacting to a raised provider exception.
Architecture:
    - LatencyPolicy: One deadline per hop, enforced by wrapping the model call.
    - CostBudgetPolicy: One USD ceiling per hop, checked against live usage.
    - ErrorRatePolicy: One cumulative failure-ratio ceiling per hop, checked against
      a per-run attempt tally recorded at the model-call site.
    - The three per-hop policies expose hop_values() so AgentFallbackSettings can
      validate array length and element values without knowing about any class by name.
    - ToolCallLoopPolicy: Chain-wide (not per-hop) -- tolerance for a stuck
      tool-calling pattern doesn't vary by which model is currently active, the
      same way fallback_on's exception set doesn't. Deliberately omits
      hop_values(), so AgentFallbackSettings' per-hop validation skips it.
Relations:
    Consumed by vidbyte.agents.fallback.chain.AgentFallback (deadline_for/budget_for/
    advance_after_error_rate for the per-hop policies, is_stuck for ToolCallLoopPolicy)
    and validated by vidbyte.agents.fallback.settings.AgentFallbackSettings.
Similar Files:
    - vidbyte/agents/fallback/chain.py: Folds these policies into per-index lookups.
    - vidbyte/agents/fallback/settings.py: Validates hop_values() against chain length.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.tools import fingerprint_tool_call
from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from vidbyte.lib.dataclasses.tools import ToolCallContext

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


class ToolCallLoopPolicy:
    """Chain-wide repeated-tool-call detector; advances the chain when the agent looks stuck.

    Not per-hop: unlike LatencyPolicy/CostBudgetPolicy, tolerance for a stuck tool-calling
    pattern isn't a property of which model in the chain is currently active, so this class
    has no hop_values() and is skipped by AgentFallbackSettings' per-hop validation.
    """

    def __init__(self, *, window_size: int = 8, repeat_threshold: int = 3, ignored_argument_keys: frozenset[str] = frozenset()) -> None:
        # Stores the detection window/threshold/ignored-keys, then validates them immediately.
        self.window_size = window_size
        self.repeat_threshold = repeat_threshold
        self.ignored_argument_keys = frozenset(ignored_argument_keys)
        self._validate()

    def is_stuck(self, call_contexts: Sequence["ToolCallContext"]) -> bool:
        # Reports whether any fingerprint repeats across repeat_threshold distinct iterations in the window.
        window = call_contexts[-self.window_size :]
        iterations_by_fingerprint = self._iterations_by_fingerprint(window)
        return any(len(iterations) >= self.repeat_threshold for iterations in iterations_by_fingerprint.values())

    def _iterations_by_fingerprint(self, window: Sequence["ToolCallContext"]) -> dict[str, set[int | None]]:
        # Groups the window by tool-call fingerprint, counting distinct iteration_counts per group so
        # same-iteration parallel fan-out (a legitimate concurrent identical call) doesn't count as
        # repetition on its own -- only recurrence across separate iterations does. Denied and internal
        # calls are deliberately not excluded here (unlike ToolSettings' own identical-call budget):
        # a call the agent keeps retrying after it was denied is itself evidence of a stuck pattern,
        # not noise to filter out.
        grouped: dict[str, set[int | None]] = {}
        for call in window:
            fingerprint = fingerprint_tool_call(call.tool_name, call.arguments, ignored_keys=self.ignored_argument_keys)
            grouped.setdefault(fingerprint, set()).add(call.iteration_count)
        return grouped

    def _validate(self) -> None:
        # Raises ConfigurationError for any constraint violation found on this policy.
        self._validate_positive_int("window_size", self.window_size)
        self._validate_positive_int("repeat_threshold", self.repeat_threshold)
        if self.repeat_threshold > self.window_size:
            raise ConfigurationError(
                f"ToolCallLoopPolicy.repeat_threshold ({self.repeat_threshold}) cannot exceed "
                f"window_size ({self.window_size}); the trigger could never fire."
            )

    @staticmethod
    def _validate_positive_int(field_name: str, value: int) -> None:
        # Rejects a non-positive, non-integer, or bool value -- none can express a real window/threshold.
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ConfigurationError(f"ToolCallLoopPolicy.{field_name} must be a positive integer, got {value!r}.")

    def __repr__(self) -> str:
        # Returns a compact developer-readable string of the configured window and threshold.
        return f"ToolCallLoopPolicy(window_size={self.window_size}, repeat_threshold={self.repeat_threshold})"


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




__all__ = ["CostBudgetPolicy", "ErrorRatePolicy", "LatencyPolicy", "ToolCallLoopPolicy"]
