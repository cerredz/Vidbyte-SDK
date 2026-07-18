"""Context Protocol Header

Description:
    The prebuilt deterministic effort-floor output contracts.
Purpose:
    Each floor requires a runtime counter to reach a minimum before the agent may stop.
    Most floors are pure declaration (key / ceiling_key / unit); a few override
    satisfied()/error() when the counter shape is not a single scalar.
Architecture:
    - Scalar floors: MinToolCalls, MinTokens, MinIterations, MinElapsedSeconds/MinTimeTaken,
      MinSuccessfulToolCalls, MinDistinctTools, MinFinalOutputChars/Tokens, MinCompactions.
    - Custom floors: MinToolCallsById (per-name map), MinCostSpent (USD estimate).
Relations:
    Subclasses of vidbyte.agents.contracts.OutputContract; validated against AgentLoopSettings
    ceilings by vidbyte.agents.settings.loop.AgentLoopSettings at construction.
Similar Files:
    - vidbyte/agents/contracts/__init__.py: OutputContract base with satisfied()/error().
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.agents.contracts import OutputContract
from vidbyte.lib.errors import ConfigurationError


class MinToolCalls(OutputContract):
    """Requires at least `minimum` tool calls before the agent may stop."""

    key = "tool_call_count"
    ceiling_key = "max_tool_calls"
    unit = "tool calls"


class MinTokens(OutputContract):
    """Requires at least `minimum` tokens consumed before the agent may stop."""

    key = "tokens_used"
    ceiling_key = "max_tokens"
    unit = "tokens"


class MinIterations(OutputContract):
    """Requires at least `minimum` loop iterations before the agent may stop."""

    key = "iteration_count"
    ceiling_key = "max_iterations"
    unit = "iterations"


class MinElapsedSeconds(OutputContract):
    """Requires at least `minimum` elapsed seconds before the agent may stop."""

    key = "elapsed_seconds"
    ceiling_key = "timeout_seconds"
    unit = "seconds"


class MinTimeTaken(MinElapsedSeconds):
    """Alias floor: require minimum wall-clock seconds before stop (same counters as MinElapsedSeconds)."""


class MinSuccessfulToolCalls(OutputContract):
    """Requires at least `minimum` non-internal tools that finished with SUCCEEDED state."""

    key = "successful_tool_call_count"
    ceiling_key = "max_tool_calls"
    unit = "successful tool calls"


class MinDistinctTools(OutputContract):
    """Requires at least `minimum` unique non-internal tool names used in the run."""

    key = "distinct_tool_count"
    ceiling_key = None
    unit = "distinct tools"


class MinFinalOutputChars(OutputContract):
    """Requires the candidate final assistant text to be at least `minimum` characters."""

    key = "final_output_chars"
    ceiling_key = None
    unit = "final output characters"


class MinFinalOutputTokens(OutputContract):
    """Requires the candidate final assistant text to be at least `minimum` approx tokens."""

    key = "final_output_tokens"
    ceiling_key = None
    unit = "final output tokens"


class MinCompactions(OutputContract):
    """Requires at least `minimum` mutating context-history compaction events before stop."""

    key = "compaction_count"
    ceiling_key = None
    unit = "compactions"


class MinToolCallsById(OutputContract):
    """Requires at least `minimum` non-internal calls to one named tool."""

    key = "tool_calls_by_name"
    ceiling_key = None
    unit = "calls"

    def __init__(self, tool_name: str, minimum: int) -> None:
        # Validates the target tool name and minimum, then stores the identity used at evaluation.
        super().__init__(minimum)
        normalized = tool_name.strip() if isinstance(tool_name, str) else ""
        if not normalized:
            raise ConfigurationError(f"{type(self).__name__}: tool_name must be a non-empty string.")
        self.tool_name = normalized

    def satisfied(self, counters: Mapping[str, Any]) -> bool:
        # Returns whether the named tool's non-internal call count has reached the minimum.
        return self.observed(counters) >= self.minimum

    def error(self, counters: Mapping[str, Any]) -> str:
        # Builds corrective feedback naming the tool and its observed call count.
        observed = self.observed(counters)
        return (
            f"Only {observed} calls to '{self.tool_name}' so far; "
            f"at least {self.minimum} are required before finishing. Keep working."
        )

    def observed(self, counters: Mapping[str, Any]) -> int:
        # Reads this tool's count from the tool_calls_by_name histogram in the counters snapshot.
        counts = counters.get(self.key) or {}
        if not isinstance(counts, Mapping):
            return 0
        return int(counts.get(self.tool_name, 0) or 0)


class MinCostSpent(OutputContract):
    """Requires estimated USD spend to reach `minimum` before the agent may stop."""

    key = "cost_spent_usd"
    ceiling_key = None
    unit = "USD"

    def __init__(self, minimum: float, *, cost_per_million_tokens: float | None = None) -> None:
        # Validates the spend floor and optional fallback rate used when cost middleware is absent.
        super().__init__(minimum)
        if cost_per_million_tokens is not None and cost_per_million_tokens <= 0:
            raise ConfigurationError(
                f"{self.name}: cost_per_million_tokens must be greater than zero when provided, "
                f"got {cost_per_million_tokens}."
            )
        self.cost_per_million_tokens = cost_per_million_tokens

    def satisfied(self, counters: Mapping[str, Any]) -> bool:
        # Returns whether estimated USD spend has reached the configured minimum.
        return self.observed(counters) >= self.minimum

    def error(self, counters: Mapping[str, Any]) -> str:
        # Builds corrective feedback with observed USD spend versus the required floor.
        observed = self.observed(counters)
        return (
            f"Only ${observed:.6f} {self.unit} spent so far; "
            f"at least ${float(self.minimum):.6f} are required before finishing. Keep working."
        )

    def observed(self, counters: Mapping[str, Any]) -> float:
        # Prefers the runtime cost middleware counter; falls back to rate × tokens when configured.
        middleware_spend = counters.get(self.key)
        if middleware_spend is not None:
            spend = float(middleware_spend or 0.0)
            if spend > 0 or self.cost_per_million_tokens is None:
                return spend
        if self.cost_per_million_tokens is None:
            return 0.0
        tokens = float(counters.get("tokens_used") or 0)
        return tokens / 1_000_000 * self.cost_per_million_tokens
