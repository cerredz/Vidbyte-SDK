"""Context Protocol Header

Description:
    Implements ToolBehavior — predicates over tool presence (A) and outcome/state (B).
Purpose:
    Exposes boolean methods checking which tools were called, their call states,
    and their result outputs during a completed agent run.
Architecture:
    - ToolBehavior: reads probe.tool_calls and each call's .state / .result.
    - Category A methods: presence, set membership, ordering, counting.
    - Category B methods: succeeded/failed/denied states, result content checks.
Relations:
    Instantiated by Behavior facade and accessed via agent.behavior.tool.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from vidbyte.lib.dataclasses.tools import ToolCallState

if TYPE_CHECKING:
    from vidbyte.evals.behavior.behavior import Behavior


class ToolBehavior:
    """Predicates over tool presence and outcome for a completed agent run."""

    def __init__(self, behavior: Behavior) -> None:
        # Stores a reference to the parent Behavior facade for lazy probe access.
        self._behavior = behavior

    @property
    def _calls(self) -> tuple[Any, ...]:
        # Returns the tool call contexts from the probe.
        return self._behavior.probe.tool_calls

    def called_tool(self, name: str) -> bool:
        # Returns True if at least one call to the named tool was made.
        return any(c.tool_name == name for c in self._calls)

    def not_called_tool(self, name: str) -> bool:
        # Returns True if no call to the named tool was made.
        return not self.called_tool(name)

    def called_all_tools(self, names: Sequence[str]) -> bool:
        # Returns True if every tool in names was called at least once.
        called_names = {c.tool_name for c in self._calls}
        return all(n in called_names for n in names)

    def called_any_tool(self, names: Sequence[str]) -> bool:
        # Returns True if at least one tool in names was called.
        called_names = {c.tool_name for c in self._calls}
        return any(n in called_names for n in names)

    def called_no_tools(self) -> bool:
        # Returns True if no tool calls were made during the run.
        return len(self._calls) == 0

    def called_only_tools(self, names: Sequence[str]) -> bool:
        # Returns True if every call was to a tool in names (no extras outside the set).
        allowed = set(names)
        return all(c.tool_name in allowed for c in self._calls)

    def called_tools_in_order(self, names: Sequence[str]) -> bool:
        # Returns True if the call names contain names as a subsequence (order preserved).
        call_names = [c.tool_name for c in self._calls]
        idx = 0
        for target in names:
            while idx < len(call_names) and call_names[idx] != target:
                idx += 1
            if idx >= len(call_names):
                return False
            idx += 1
        return True

    def tool_call_count(self, name: str) -> int:
        # Returns the number of times the named tool was called.
        return sum(1 for c in self._calls if c.tool_name == name)

    def called_tool_names(self) -> tuple[str, ...]:
        # Returns ordered unique tool names preserving first-occurrence order.
        seen: dict[str, None] = {}
        for c in self._calls:
            seen.setdefault(c.tool_name, None)
        return tuple(seen.keys())

    def tool_succeeded(self, name: str) -> bool:
        # Returns True if at least one call to the named tool has state SUCCEEDED.
        return any(c.tool_name == name and c.state == ToolCallState.SUCCEEDED for c in self._calls)

    def tool_failed(self, name: str) -> bool:
        # Returns True if at least one call to the named tool has state FAILED.
        return any(c.tool_name == name and c.state == ToolCallState.FAILED for c in self._calls)

    def tool_denied(self, name: str) -> bool:
        # Returns True if at least one call to the named tool has state DENIED.
        return any(c.tool_name == name and c.state == ToolCallState.DENIED for c in self._calls)

    def all_tool_calls_succeeded(self) -> bool:
        # Returns True if every tool call has state SUCCEEDED (vacuously True when empty).
        return all(c.state == ToolCallState.SUCCEEDED for c in self._calls)

    def tool_returned_containing(self, name: str, substring: str) -> bool:
        # Returns True if any call to the named tool has a result whose output contains substring.
        for c in self._calls:
            if c.tool_name != name or c.result is None:
                continue
            if substring in c.result.output:
                return True
        return False

    def tool_returned_matching(self, name: str, pattern: str) -> bool:
        # Returns True if any call to the named tool has a result whose output matches the regex.
        for c in self._calls:
            if c.tool_name != name or c.result is None:
                continue
            if re.search(pattern, c.result.output):
                return True
        return False


__all__ = ["ToolBehavior"]
