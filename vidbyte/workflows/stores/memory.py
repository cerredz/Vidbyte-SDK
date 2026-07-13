"""FILE: vidbyte/workflows/stores/memory.py
PURPOSE: Provides the default process-local canonical workflow event store.
ROLE IN CODEBASE: StateMachine uses it when no caller-owned WorkflowStore is supplied.

ARCHITECTURE NOTE:
    One asyncio lock serializes definition, event, and checkpoint changes. Returned
    records are immutable, so readers cannot mutate canonical in-memory truth.

PUBLIC API INVENTORY:
    InMemoryWorkflowStore: Implements every WorkflowStore operation with optimistic
        sequence checks and immutable append-only collections.

COMMON MODIFICATION PATTERNS:
    Keep behavior aligned with file.py, especially collision and sequence failures.

WHAT NOT TO DO IN THIS FILE:
    1. Do not claim durability across process exit.
    2. Do not expose internal lists or dictionaries to callers.
    3. Do not overwrite definitions, events, or checkpoints.

KNOWN EDGE CASES:
    Multiple compiled machines may share one store safely inside one event loop.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke covers conflicts and replay.

CONCURRENCY MODEL:
    A single asyncio.Lock covers all mutable collections and sequence allocation.
"""

from __future__ import annotations

import asyncio

from ..errors import WorkflowPersistenceError
from ..events import WorkflowEvent
from ..persistence import WorkflowCheckpoint, WorkflowDefinitionRecord


class InMemoryWorkflowStore:
    """Process-local append-only store used by default for every workflow run."""

    def __init__(self) -> None:
        # Initializes isolated collections and one lock for atomic store operations.
        self._definitions: dict[str, WorkflowDefinitionRecord] = {}
        self._events: dict[str, tuple[WorkflowEvent, ...]] = {}
        self._checkpoints: dict[str, tuple[WorkflowCheckpoint, ...]] = {}
        self._event_ids: set[str] = set()
        self._checkpoint_ids: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def durable(self) -> bool:
        # Declares that process exit discards records and graph version is optional.
        return False

    async def put_definition(self, definition: WorkflowDefinitionRecord) -> WorkflowDefinitionRecord:
        # Creates a definition or verifies an identical record already exists.
        async with self._lock:
            current = self._definitions.get(definition.definition_id)
            if current is not None and current != definition:
                raise WorkflowPersistenceError("Workflow definition ID collision.", details={"definition_id": definition.definition_id})
            self._definitions[definition.definition_id] = definition
            return definition

    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRecord | None:
        # Reads one immutable definition under the store lock.
        async with self._lock:
            return self._definitions.get(definition_id)

    async def begin_run(self, event: WorkflowEvent) -> WorkflowEvent:
        # Atomically creates one run with an unused sequence-one event.
        async with self._lock:
            if event.sequence != 1:
                raise WorkflowPersistenceError("A workflow run must begin at event sequence one.", details={"run_id": event.run_id, "sequence": event.sequence})
            if event.run_id in self._events:
                raise WorkflowPersistenceError("Workflow run already exists.", details={"run_id": event.run_id})
            self._assert_new_event_id(event)
            self._events[event.run_id] = (event,)
            return event

    async def append(self, event: WorkflowEvent, *, expected_sequence: int) -> WorkflowEvent:
        # Appends exactly one next event when the caller's sequence view is current.
        async with self._lock:
            existing = self._events.get(event.run_id)
            if existing is None:
                raise WorkflowPersistenceError("Workflow run does not exist for append.", details={"run_id": event.run_id})
            actual = existing[-1].sequence
            if actual != expected_sequence or event.sequence != expected_sequence + 1:
                raise WorkflowPersistenceError("Workflow event optimistic sequence conflict.", details={"run_id": event.run_id, "expected_sequence": expected_sequence, "actual_sequence": actual, "event_sequence": event.sequence})
            self._assert_new_event_id(event)
            self._events[event.run_id] = (*existing, event)
            return event

    async def events(self, run_id: str, *, after_sequence: int = 0, through_sequence: int | None = None) -> tuple[WorkflowEvent, ...]:
        # Returns a filtered immutable event tuple in canonical order.
        async with self._lock:
            events = self._events.get(run_id, ())
            return tuple(event for event in events if event.sequence > after_sequence and (through_sequence is None or event.sequence <= through_sequence))

    async def put_checkpoint(self, checkpoint: WorkflowCheckpoint) -> WorkflowCheckpoint:
        # Appends an immutable checkpoint only after its referenced event exists.
        async with self._lock:
            events = self._events.get(checkpoint.run_id)
            if not events or checkpoint.event_sequence > events[-1].sequence:
                raise WorkflowPersistenceError("Checkpoint references a missing future event.", details={"run_id": checkpoint.run_id, "event_sequence": checkpoint.event_sequence})
            if checkpoint.checkpoint_id in self._checkpoint_ids:
                raise WorkflowPersistenceError("Duplicate workflow checkpoint ID.", details={"checkpoint_id": checkpoint.checkpoint_id})
            existing = self._checkpoints.get(checkpoint.run_id, ())
            if existing and checkpoint.event_sequence <= existing[-1].event_sequence:
                raise WorkflowPersistenceError("Workflow checkpoint sequence must increase.", details={"run_id": checkpoint.run_id, "event_sequence": checkpoint.event_sequence, "latest": existing[-1].event_sequence})
            self._checkpoint_ids.add(checkpoint.checkpoint_id)
            self._checkpoints[checkpoint.run_id] = (*existing, checkpoint)
            return checkpoint

    async def latest_checkpoint(self, run_id: str, *, through_sequence: int | None = None) -> WorkflowCheckpoint | None:
        # Returns the newest checkpoint not newer than an optional inspection boundary.
        async with self._lock:
            checkpoints = self._checkpoints.get(run_id, ())
            eligible = [item for item in checkpoints if through_sequence is None or item.event_sequence <= through_sequence]
            return eligible[-1] if eligible else None

    def _assert_new_event_id(self, event: WorkflowEvent) -> None:
        # Rejects event identity reuse across all runs in this store instance.
        if event.event_id in self._event_ids:
            raise WorkflowPersistenceError("Duplicate workflow event ID.", details={"event_id": event.event_id, "run_id": event.run_id})
        self._event_ids.add(event.event_id)


__all__ = ["InMemoryWorkflowStore"]
