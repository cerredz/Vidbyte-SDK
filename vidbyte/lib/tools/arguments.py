"""FILE: vidbyte/lib/tools/arguments.py

PURPOSE: Defines ToolArguments, the canonical way to read a model's tool argument that is a list of JSON objects into validated dataclass records: each object must use exactly the record's fields, JSON lists become tuples, and the record's own __post_init__ checks every value.
ROLE IN CODEBASE: Called by InfiniteLaunchTool (vidbyte/agents/infinite/launch.py) to turn the tasks of a launch_subagent call into InfiniteTaskCard records. Any tool whose argument is a list of structured items should read it here instead of walking the JSON itself.
ARCHITECTURE NOTE: A static method over any frozen dataclass type. Field names and which fields are required come from dataclasses.fields, so the record stays the one place that defines the shape. A refusal raises ConfigurationError with a message written for the model: it names the argument, the item's index, and the fields to use, so the tool can return it as what to fix. The record's own checks raise ConfigurationError the same way.
FUNCTION INVENTORY: records(value, record_type, argument) -> tuple of records, one per object, in order.
COMMON MODIFICATION PATTERNS: Another argument shape, such as one object rather than a list, is one more static method here that reuses the same field rules.
WHAT NOT TO DO IN THIS FILE: 1. Do not coerce values beyond JSON lists to tuples; the record decides what it accepts. 2. Do not drop unknown fields silently; a misspelled field would lose an instruction. 3. Do not import from a layer above vidbyte/lib.
KNOWN EDGE CASES: An empty list is refused, because a call that carries nothing is a mistake. A field with a default or a default factory is optional; a field with init=False is never accepted from the model. A nested list inside a list stays a list inside the tuple.
RELATED DOCS: vidbyte/agents/infinite/README.md (launch_subagent); vidbyte/lib/README.md
TESTS: tests/test_tool_arguments.py; and through launch_subagent, tests/features/infinite_memory_agent/test_infinite_memory_delegation.py
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, TypeVar

from vidbyte.lib.errors import ConfigurationError

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

RecordT = TypeVar("RecordT", bound="DataclassInstance")


class ToolArguments:
    """Static-method home for reading a model's tool arguments into validated records."""

    @staticmethod
    def records(value: object, record_type: type[RecordT], *, argument: str) -> tuple[RecordT, ...]:
        """Return one record per JSON object in value, in order, or raise ConfigurationError saying what to fix."""
        # @intent model-objects-become-checked-records
        # Each object must use exactly the record's fields: an unknown
        # field is refused, so a misspelled one never drops an
        # instruction silently, and each missing required field is
        # named. JSON lists become the tuples records require.
        if not isinstance(value, list) or not value:
            raise ConfigurationError(f"{argument} must be a non-empty list of objects.", details={"argument": argument})
        fields = [field for field in dataclasses.fields(record_type) if field.init]
        names = [field.name for field in fields]
        required = [field.name for field in fields if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING]
        records: list[RecordT] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise ConfigurationError(f"{argument}[{index}] must be an object with the fields {', '.join(names)}; got {item!r}.", details={"argument": argument, "index": index})
            unknown = [name for name in item if name not in names]
            missing = [name for name in required if name not in item]
            if unknown or missing:
                raise ConfigurationError(f"{argument}[{index}] has unknown fields {unknown} and lacks the fields {missing}; use exactly {', '.join(names)}.", details={"argument": argument, "index": index})
            given: dict[str, Any] = {name: tuple(raw) if isinstance(raw, list) else raw for name, raw in item.items()}
            records.append(record_type(**given))
        return tuple(records)


__all__ = ["ToolArguments"]
