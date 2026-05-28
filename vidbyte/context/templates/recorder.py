"""Context Protocol Header

Description:
    Implements the ContextWindowRecorder and NullRecorder for slot-level
    context window tracing during algorithm execution.
Purpose:
    Accumulates an ordered list of structural slot events emitted by algorithm
    implementations so templates can validate the exact slot sequence produced
    by a run.
Architecture:
    - SlotEvent: Immutable record of one emitted slot.
    - RecorderBase: Abstract interface all recorder implementations must satisfy.
    - ContextWindowRecorder: Live recorder that stores SlotEvent instances.
    - NullRecorder: Zero-overhead no-op used when template testing is not active.
Relations:
    Used by AgentRuntime and algorithm implementations such as
    ReflexionRuntimeAlgorithm. Consumed by ContextWindowTemplate in
    vidbyte.lib.templates.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SlotEvent:
    """Immutable record of one structural slot emitted during an agent run."""

    slot_type: str
    iteration: int
    metadata: dict[str, Any]


class RecorderBase(ABC):
    """Abstract interface that all context window recorder implementations must satisfy."""

    @abstractmethod
    def append(self, slot_type: str, *, iteration: int = 0, **metadata: Any) -> None:
        # Record one structural slot event at the current point in the run.
        ...

    @abstractmethod
    def slots(self) -> tuple[str, ...]:
        # Return the ordered sequence of slot type strings recorded so far.
        ...


class ContextWindowRecorder(RecorderBase):
    """Live recorder that accumulates SlotEvent instances in insertion order."""

    def __init__(self) -> None:
        # Initialize an empty event list for this recording session.
        self._events: list[SlotEvent] = []

    def append(self, slot_type: str, *, iteration: int = 0, **metadata: Any) -> None:
        # Construct and store a new SlotEvent for the given slot type and iteration.
        self._events.append(SlotEvent(slot_type=slot_type, iteration=iteration, metadata=dict(metadata)))

    def slots(self) -> tuple[str, ...]:
        # Return the slot_type string for each recorded event in insertion order.
        return tuple(event.slot_type for event in self._events)

    def events(self) -> tuple[SlotEvent, ...]:
        # Return an immutable snapshot of all recorded SlotEvent instances.
        return tuple(self._events)

    def reset(self) -> None:
        # Clear all recorded events to allow recorder reuse between test cases.
        self._events.clear()


class NullRecorder(RecorderBase):
    """Zero-overhead no-op recorder used when template testing is not active."""

    def append(self, slot_type: str, *, iteration: int = 0, **metadata: Any) -> None:
        # No-op: discard all slot events when no template testing is configured.
        pass

    def slots(self) -> tuple[str, ...]:
        # Always returns an empty tuple since no events are recorded.
        return ()


__all__ = [
    "ContextWindowRecorder",
    "NullRecorder",
    "RecorderBase",
    "SlotEvent",
]
