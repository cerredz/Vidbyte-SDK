"""Context Protocol Header

Description:
    Implements EfficiencyBehavior - predicates over loop efficiency and redundant tool usage.
Purpose:
    Exposes deterministic post-run checks for tool repetition, duplicate arguments/results,
    consecutive calls, budget stops, failure thrash, and token density.
Architecture:
    - EfficiencyBehavior reads RunProbe fields through the parent Behavior facade.
    - All predicates are read-only and use exact equality over existing tool-call metadata.
Relations:
    Instantiated by Behavior facade and accessed via agent.behavior.efficiency.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.agents import AgentStopReason
from vidbyte.lib.dataclasses.tools import ToolCallState

if TYPE_CHECKING:
    from vidbyte.evals.behavior.behavior import Behavior


class EfficiencyBehavior:
    """Predicates over tool-loop efficiency for a completed agent run."""

    _BUDGET_STOP_REASONS = {
        AgentStopReason.MAX_ITERATIONS.value,
        AgentStopReason.MAX_TOOL_CALLS.value,
        AgentStopReason.MAX_TOKENS.value,
    }
    _UNSUCCESSFUL_STATES = {ToolCallState.FAILED, ToolCallState.DENIED}

    def __init__(self, behavior: Behavior) -> None:
        # Stores a reference to the parent Behavior facade for lazy probe access.
        self._behavior = behavior

    @property
    def _probe(self) -> Any:
        # Returns the RunProbe from the parent Behavior facade.
        return self._behavior.probe

    @property
    def _calls(self) -> tuple[Any, ...]:
        # Returns the tool call contexts from the probe.
        return self._behavior.probe.tool_calls

    def max_tool_repetitions(self, name: str, max_count: int) -> bool:
        # Returns True if the named tool was called no more than max_count times.
        return self._tool_call_count(name) <= max_count

    def max_any_tool_repetitions(self, max_count: int) -> bool:
        # Returns True if no individual tool name exceeds max_count calls.
        return all(self._tool_call_count(name) <= max_count for name in self._ordered_tool_names())

    def completed_within_iterations(self, max_iterations: int) -> bool:
        # Returns True if the run's iteration count is within the inclusive limit.
        return self._probe.iteration_count <= max_iterations

    def completed_within_tool_calls(self, max_calls: int) -> bool:
        # Returns True if the run's tool-call count is within the inclusive limit.
        return self._probe.tool_call_count <= max_calls

    def tool_calls_between(self, minimum: int, maximum: int) -> bool:
        # Returns True if the run's tool-call count is inside the inclusive range.
        count = self._probe.tool_call_count
        return minimum <= count <= maximum

    def no_duplicate_tool_args(self, name: str) -> bool:
        # Returns True if no two calls to the named tool used equal arguments.
        return self.duplicate_tool_arg_count(name) == 0

    def no_duplicate_tool_calls(self) -> bool:
        # Returns True if no exact (tool_name, arguments) pair was repeated.
        return self.duplicate_tool_call_count() == 0

    def duplicate_tool_arg_count(self, name: str) -> int:
        # Counts repeated argument mappings for one tool after their first occurrence.
        calls = [call for call in self._calls if call.tool_name == name]
        return self._duplicate_count(calls, compare_arguments_only=True)

    def duplicate_tool_call_count(self) -> int:
        # Counts repeated exact tool calls after their first occurrence.
        return self._duplicate_count(self._calls)

    def unique_tool_call_count(self) -> int:
        # Returns the number of unique exact (tool_name, arguments) pairs.
        unique: list[Any] = []
        for call in self._calls:
            if not any(self._same_call(call, seen) for seen in unique):
                unique.append(call)
        return len(unique)

    def unique_tool_ratio_at_least(self, min_ratio: float) -> bool:
        # Returns True if unique exact calls divided by total calls meets min_ratio.
        total = self._probe.tool_call_count
        if total == 0:
            return 1.0 >= min_ratio
        return (self.unique_tool_call_count() / total) >= min_ratio

    def no_consecutive_identical_calls(self) -> bool:
        # Returns True if adjacent calls never repeat the same tool name and arguments.
        return self.consecutive_identical_call_count() == 0

    def no_consecutive_same_tool(self) -> bool:
        # Returns True if adjacent calls never use the same tool name.
        return self.consecutive_same_tool_count() == 0

    def consecutive_identical_call_count(self) -> int:
        # Counts adjacent repeated exact tool calls.
        return sum(1 for left, right in zip(self._calls, self._calls[1:]) if self._same_call(left, right))

    def consecutive_same_tool_count(self) -> int:
        # Counts adjacent calls to the same tool name regardless of arguments.
        return sum(1 for left, right in zip(self._calls, self._calls[1:]) if left.tool_name == right.tool_name)

    def max_consecutive_tool_calls(self, name: str, max_count: int) -> bool:
        # Returns True if the longest adjacent run for name is within max_count.
        return self._longest_tool_run(name) <= max_count

    def max_any_consecutive_tool_repetitions(self, max_count: int) -> bool:
        # Returns True if every adjacent same-tool run is within max_count.
        if not self._calls:
            return True
        return max(self._longest_tool_run(name) for name in self._ordered_tool_names()) <= max_count

    def repeated_tool_names(self) -> tuple[str, ...]:
        # Returns ordered unique tool names that appear more than once.
        repeated: list[str] = []
        for name in self._ordered_tool_names():
            if self._tool_call_count(name) > 1:
                repeated.append(name)
        return tuple(repeated)

    def no_repeated_tool_results(self, name: str | None = None) -> bool:
        # Returns True if no non-empty scoped tool result output repeats.
        return self.repeated_tool_result_count(name) == 0

    def repeated_tool_result_count(self, name: str | None = None) -> int:
        # Counts repeated scoped tool result outputs after their first occurrence.
        outputs = self._result_outputs(name)
        seen: list[str] = []
        duplicates = 0
        for output in outputs:
            if output in seen:
                duplicates += 1
            else:
                seen.append(output)
        return duplicates

    def max_result_repetitions(self, max_count: int, name: str | None = None) -> bool:
        # Returns True if every scoped tool result output appears within max_count.
        outputs = self._result_outputs(name)
        return all(outputs.count(output) <= max_count for output in set(outputs))

    def failed_tool_calls_at_most(self, max_count: int) -> bool:
        # Returns True if FAILED tool calls are within max_count.
        return self._state_count(ToolCallState.FAILED) <= max_count

    def denied_tool_calls_at_most(self, max_count: int) -> bool:
        # Returns True if DENIED tool calls are within max_count.
        return self._state_count(ToolCallState.DENIED) <= max_count

    def unsuccessful_tool_calls_at_most(self, max_count: int) -> bool:
        # Returns True if FAILED and DENIED tool calls are within max_count.
        return sum(1 for call in self._calls if call.state in self._UNSUCCESSFUL_STATES) <= max_count

    def successful_tool_call_ratio_at_least(self, min_ratio: float) -> bool:
        # Returns True if succeeded calls divided by total calls meets min_ratio.
        total = self._probe.tool_call_count
        if total == 0:
            return 1.0 >= min_ratio
        succeeded = self._state_count(ToolCallState.SUCCEEDED)
        return (succeeded / total) >= min_ratio

    def no_failed_tool_retries(self, name: str | None = None) -> bool:
        # Returns True if unsuccessful exact attempts were not repeated.
        return self.failed_tool_retry_count(name) == 0

    def failed_tool_retry_count(self, name: str | None = None) -> int:
        # Counts repeated unsuccessful exact attempts after their first occurrence.
        calls = [call for call in self._calls if call.state in self._UNSUCCESSFUL_STATES]
        if name is not None:
            calls = [call for call in calls if call.tool_name == name]
        return self._duplicate_count(tuple(calls))

    def did_not_stop_on_budget(self) -> bool:
        # Returns True if the run did not stop due to a runtime budget limit.
        return self._probe.stop_reason not in self._BUDGET_STOP_REASONS

    def stopped_normally_within_iterations(self, max_iterations: int) -> bool:
        # Returns True if the run stopped normally and stayed within the iteration limit.
        return self._stopped_normally() and self.completed_within_iterations(max_iterations)

    def stopped_normally_within_tool_calls(self, max_calls: int) -> bool:
        # Returns True if the run stopped normally and stayed within the tool-call limit.
        return self._stopped_normally() and self.completed_within_tool_calls(max_calls)

    def tokens_per_tool_call(self) -> float | None:
        # Returns average tokens per tool call, or None when unavailable.
        if self._probe.tokens_used is None or self._probe.tool_call_count == 0:
            return None
        return float(self._probe.tokens_used) / self._probe.tool_call_count

    def tokens_per_tool_call_at_most(self, max_tokens: float) -> bool:
        # Returns True if known average tokens per tool call is within max_tokens.
        value = self.tokens_per_tool_call()
        return True if value is None else value <= max_tokens

    def tokens_per_iteration(self) -> float | None:
        # Returns average tokens per iteration, or None when unavailable.
        if self._probe.tokens_used is None or self._probe.iteration_count == 0:
            return None
        return float(self._probe.tokens_used) / self._probe.iteration_count

    def tokens_per_iteration_at_most(self, max_tokens: float) -> bool:
        # Returns True if known average tokens per iteration is within max_tokens.
        value = self.tokens_per_iteration()
        return True if value is None else value <= max_tokens

    def _duplicate_count(self, calls: tuple[Any, ...] | list[Any], *, compare_arguments_only: bool = False) -> int:
        # Counts entries that match an earlier entry by arguments or exact call identity.
        seen: list[Any] = []
        duplicates = 0
        for call in calls:
            matched = self._seen_arguments(call, seen) if compare_arguments_only else any(self._same_call(call, item) for item in seen)
            if matched:
                duplicates += 1
            else:
                seen.append(call)
        return duplicates

    def _seen_arguments(self, call: Any, seen: list[Any]) -> bool:
        # Returns True if call arguments match an earlier call's arguments.
        return any(self._same_arguments(call.arguments, item.arguments) for item in seen)

    def _same_call(self, left: Any, right: Any) -> bool:
        # Returns True if two call contexts have the same tool name and arguments.
        return left.tool_name == right.tool_name and self._same_arguments(left.arguments, right.arguments)

    def _same_arguments(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        # Compares argument mappings exactly without requiring hashable nested values.
        return dict(left) == dict(right)

    def _ordered_tool_names(self) -> tuple[str, ...]:
        # Returns ordered unique tool names preserving first occurrence.
        seen: dict[str, None] = {}
        for call in self._calls:
            seen.setdefault(call.tool_name, None)
        return tuple(seen.keys())

    def _tool_call_count(self, name: str) -> int:
        # Counts calls to one tool name.
        return sum(1 for call in self._calls if call.tool_name == name)

    def _longest_tool_run(self, name: str) -> int:
        # Returns the longest adjacent run length for one tool name.
        longest = 0
        current = 0
        for call in self._calls:
            if call.tool_name == name:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        return longest

    def _result_outputs(self, name: str | None) -> list[str]:
        # Returns non-None result outputs, optionally scoped to one tool name.
        outputs: list[str] = []
        for call in self._calls:
            if name is not None and call.tool_name != name:
                continue
            if call.result is not None:
                outputs.append(call.result.output)
        return outputs

    def _state_count(self, state: ToolCallState) -> int:
        # Counts calls in one lifecycle state.
        return sum(1 for call in self._calls if call.state == state)

    def _stopped_normally(self) -> bool:
        # Returns True if the run stopped with a final response.
        return self._probe.stop_reason == AgentStopReason.FINAL_RESPONSE.value


__all__ = ["EfficiencyBehavior"]
