"""FILE: tests/test_tool_arguments.py

PURPOSE: Proves ToolArguments.records reads a model's list-of-objects argument into validated records: each object uses exactly the record's init fields, JSON lists become tuples, the record's own checks still run, and every refusal names the argument and the item's index.
ROLE IN CODEBASE: Unit tests for vidbyte/lib/tools/arguments.py. launch_subagent's use of it is proven by tests/features/infinite_memory_agent/test_infinite_memory_delegation.py.
ARCHITECTURE NOTE: Ticket is a test-only frozen record shaped like InfiniteTaskCard: required fields, tuple fields with a default and a default factory, a field with init=False, and its own __post_init__ check, so every branch of ToolArguments.records is reached without the agent.
COMMON MODIFICATION PATTERNS: A new argument shape in ToolArguments gets its own test beside these, reusing Ticket; a new refusal adds one parametrized row naming the text the message must contain.
KNOWN EDGE CASES: A field with init=False is reported as unknown, never set. An empty list is refused like a non-list. Values other than lists reach the record unchanged, so the record's own checks decide.
RELATED DOCS: vidbyte/lib/README.md (tools/); vidbyte/agents/infinite/README.md (launch_subagent).
TESTS: PYTHONPATH=$(pwd) python -m pytest tests/test_tool_arguments.py -q
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.tools import ToolArguments


@dataclass(frozen=True, slots=True)
class Ticket:
    """A small record shaped like a task card: required text, optional tuples, and a field the model may never set."""

    name: str
    steps: tuple[str, ...]
    tags: tuple[str, ...] = ()
    labels: tuple[str, ...] = field(default_factory=tuple)
    internal: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if not isinstance(self.steps, tuple) or not self.steps:
            raise ConfigurationError("Ticket.steps must be a non-empty tuple.", details={"field": "Ticket.steps"})


def test_objects_become_records_in_order_with_lists_as_tuples() -> None:
    """Each JSON object becomes one record, in order; list values become tuples and optional fields may be left out."""
    tickets = ToolArguments.records([{"name": "a", "steps": ["x", "y"]}, {"name": "b", "steps": ["z"], "tags": ["t"], "labels": []}], Ticket, argument="tickets")
    assert tickets == (Ticket("a", ("x", "y")), Ticket("b", ("z",), ("t",), ()))
    assert all(isinstance(ticket.steps, tuple) for ticket in tickets)


@pytest.mark.parametrize("value", [None, "a ticket", {"name": "a"}, []])
def test_anything_but_a_non_empty_list_is_refused(value: object) -> None:
    """A call that carries nothing, or one object not wrapped in a list, is a mistake to fix."""
    with pytest.raises(ConfigurationError, match="tickets must be a non-empty list of objects") as raised:
        ToolArguments.records(value, Ticket, argument="tickets")
    assert raised.value.details == {"argument": "tickets"}


def test_an_item_that_is_not_an_object_names_its_index_and_the_fields() -> None:
    """The message points at the bad item and lists the fields to use."""
    with pytest.raises(ConfigurationError, match=r"tickets\[1\] must be an object with the fields name, steps, tags, labels") as raised:
        ToolArguments.records([{"name": "a", "steps": ["x"]}, "b"], Ticket, argument="tickets")
    assert raised.value.details == {"argument": "tickets", "index": 1}


@pytest.mark.parametrize(
    ("item", "unknown", "missing"),
    [
        pytest.param({"name": "a", "steps": ["x"], "stepz": ["y"]}, "['stepz']", "[]", id="misspelled-field"),
        pytest.param({"name": "a"}, "[]", "['steps']", id="missing-required"),
        pytest.param({"name": "a", "steps": ["x"], "internal": 3}, "['internal']", "[]", id="init-false-field"),
    ],
)
def test_unknown_and_missing_fields_are_named(item: dict[str, object], unknown: str, missing: str) -> None:
    """A misspelled field never drops an instruction silently, a required field is never assumed, and a non-init field is never set by the model."""
    with pytest.raises(ConfigurationError) as raised:
        ToolArguments.records([item], Ticket, argument="tickets")
    message = str(raised.value)
    assert f"unknown fields {unknown}" in message and f"lacks the fields {missing}" in message and "tickets[0]" in message


def test_the_records_own_checks_still_run() -> None:
    """Values are not coerced beyond lists to tuples; the record decides what it accepts."""
    with pytest.raises(ConfigurationError, match="Ticket.steps"):
        ToolArguments.records([{"name": "a", "steps": []}], Ticket, argument="tickets")
