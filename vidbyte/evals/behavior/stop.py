"""Context Protocol Header

Description:
    Implements StopBehavior — predicates over run-level stop conditions (D).
Purpose:
    Exposes boolean methods checking the stop reason, iteration count, token
    usage, and whether the agent hit any runtime budget limits.
Architecture:
    - StopBehavior: reads probe.stop_reason, probe.iteration_count,
      probe.tokens_used, and probe.tool_call_count.
    - Compares against AgentStopReason enum values for budget-stop detection.
Relations:
    Instantiated by Behavior facade and accessed via agent.behavior.stop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vidbyte.lib.dataclasses.agents import AgentStopReason

if TYPE_CHECKING:
    from vidbyte.evals.behavior.behavior import Behavior


class StopBehavior:
    """Predicates over run-level stop conditions for a completed agent run."""

    def __init__(self, behavior: Behavior) -> None:
        # Stores a reference to the parent Behavior facade for lazy probe access.
        self._behavior = behavior

    @property
    def _probe(self) -> Any:
        # Returns the RunProbe from the parent Behavior facade.
        return self._behavior.probe

    def stop_reason(self) -> str:
        # Returns the raw stop reason string from the probe.
        return self._probe.stop_reason

    def stopped_on(self, reason: str) -> bool:
        # Returns True if the stop reason matches the given reason string.
        return self._probe.stop_reason == reason

    def stopped_normally(self) -> bool:
        # Returns True if the agent stopped with final_response (normal completion).
        return self._probe.stop_reason == AgentStopReason.FINAL_RESPONSE.value

    def did_not_hit_max_iterations(self) -> bool:
        # Returns True if the agent did not stop due to reaching max_iterations.
        return self._probe.stop_reason != AgentStopReason.MAX_ITERATIONS.value

    def did_not_hit_max_tool_calls(self) -> bool:
        # Returns True if the agent did not stop due to reaching max_tool_calls.
        return self._probe.stop_reason != AgentStopReason.MAX_TOOL_CALLS.value

    def did_not_hit_max_tokens(self) -> bool:
        # Returns True if the agent did not stop due to reaching max_tokens.
        return self._probe.stop_reason != AgentStopReason.MAX_TOKENS.value

    def iteration_count(self) -> int:
        # Returns the total iteration count from the probe.
        return self._probe.iteration_count

    def total_tool_calls(self) -> int:
        # Returns the total tool call count from the probe.
        return self._probe.tool_call_count

    def tokens_used(self) -> int | None:
        # Returns the total tokens used, or None when the provider did not report usage.
        return self._probe.tokens_used

    def did_not_exceed_tokens(self, limit: int) -> bool:
        # Returns True if tokens_used is None or did not exceed the given limit.
        used = self._probe.tokens_used
        if used is None:
            return True
        return used <= limit


__all__ = ["StopBehavior"]
