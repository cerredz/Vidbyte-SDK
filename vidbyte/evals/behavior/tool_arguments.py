"""Context Protocol Header

Description:
    Implements ToolArgumentBehavior — predicates over tool call arguments (C).
Purpose:
    Exposes boolean methods checking whether tools were called with specific
    argument values, exact argument sets, or arguments matching a predicate.
Architecture:
    - ToolArgumentBehavior: reads probe.tool_calls and each call's .arguments mapping.
    - Subset match (tool_called_with), exact match (tool_called_with_exact),
      negation (tool_never_called_with), and predicate match (tool_called_with_matching).
Relations:
    Instantiated by Behavior facade and accessed via agent.behavior.tool_args.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from vidbyte.evals.behavior.behavior import Behavior


class ToolArgumentBehavior:
    """Predicates over tool call arguments for a completed agent run."""

    def __init__(self, behavior: Behavior) -> None:
        # Stores a reference to the parent Behavior facade for lazy probe access.
        self._behavior = behavior

    @property
    def _calls(self) -> tuple[Any, ...]:
        # Returns the tool call contexts from the probe.
        return self._behavior.probe.tool_calls

    def tool_called_with(self, name: str, **args: Any) -> bool:
        # Returns True if any call to name has args as a subset of its arguments.
        for c in self._calls:
            if c.tool_name != name:
                continue
            if all(c.arguments.get(k) == v for k, v in args.items()):
                return True
        return False

    def tool_called_with_exact(self, name: str, args: Mapping[str, Any]) -> bool:
        # Returns True if any call to name has arguments exactly matching the args dict.
        target = dict(args)
        for c in self._calls:
            if c.tool_name != name:
                continue
            if dict(c.arguments) == target:
                return True
        return False

    def tool_never_called_with(self, name: str, **args: Any) -> bool:
        # Returns True if no call to name has args as a subset of its arguments.
        return not self.tool_called_with(name, **args)

    def tool_called_with_matching(self, name: str, arg_name: str, predicate: Callable[[Any], bool]) -> bool:
        # Returns True if any call to name has arg_name present and predicate(value) is True.
        for c in self._calls:
            if c.tool_name != name:
                continue
            if arg_name in c.arguments and predicate(c.arguments[arg_name]):
                return True
        return False


__all__ = ["ToolArgumentBehavior"]
