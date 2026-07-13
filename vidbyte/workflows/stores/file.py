"""FILE: vidbyte/workflows/stores/file.py
PURPOSE: Persists inspectable workflow definitions, events, and checkpoints on disk.
ROLE IN CODEBASE: Caller-owned durable WorkflowStore used by StateMachine resume/inspect.

ARCHITECTURE NOTE:
    Each record is immutable JSON. Writes use a same-directory temporary file and
    publish it through an atomic no-overwrite hard link. Deterministic sequence
    filenames prevent competing writers from silently publishing the same boundary;
    a database adapter is still required for transactional distributed coordination.

PUBLIC API INVENTORY:
    FileWorkflowStore: Implements WorkflowStore under definitions/ and runs/ layout.

COMMON MODIFICATION PATTERNS:
    Keep filenames sortable by numeric sequence and keep JSON schema readers strict.

WHAT NOT TO DO IN THIS FILE:
    1. Do not edit or prune caller records automatically.
    2. Do not place secrets outside caller-controlled storage protections.
    3. Do not claim rollback of external workspace effects.

KNOWN EDGE CASES:
    A process crash may leave a .tmp file, which readers ignore. Cross-process writers
    have optimistic rather than transactional locking guarantees.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke performs cold resume and time travel.

CONCURRENCY MODEL:
    One asyncio.Lock serializes operations through this adapter instance. Filesystem
    existence and expected sequence checks provide best-effort cross-process conflict detection.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

from ..errors import WorkflowPersistenceError
from ..events import WorkflowEvent
from ..persistence import WorkflowCheckpoint, WorkflowDefinitionRecord


class FileWorkflowStore:
    """Atomic JSON-file workflow store with append-only record semantics."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        # Resolves the caller-owned storage root without creating records eagerly.
        self.root = Path(root).expanduser().resolve()
        self._lock = asyncio.Lock()

    @property
    def durable(self) -> bool:
        # Declares that records survive process exit and require graph versioning.
        return True

    async def put_definition(self, definition: WorkflowDefinitionRecord) -> WorkflowDefinitionRecord:
        # Creates or verifies the immutable definition JSON record.
        async with self._lock:
            path = self.root / "definitions" / f"{definition.definition_id}.json"
            if path.exists():
                current = WorkflowDefinitionRecord.from_dict(self._read_json(path))
                if current != definition:
                    raise WorkflowPersistenceError("Workflow definition ID collision on disk.", details={"definition_id": definition.definition_id, "path": str(path)})
                return current
            self._atomic_create(path, definition.to_dict())
            return definition

    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRecord | None:
        # Reads one stored definition without creating directories or records.
        async with self._lock:
            path = self.root / "definitions" / f"{definition_id}.json"
            return WorkflowDefinitionRecord.from_dict(self._read_json(path)) if path.exists() else None

    async def begin_run(self, event: WorkflowEvent) -> WorkflowEvent:
        # Creates one run directory and its required sequence-one event atomically enough.
        async with self._lock:
            if event.sequence != 1:
                raise WorkflowPersistenceError("A workflow run must begin at event sequence one.", details={"run_id": event.run_id, "sequence": event.sequence})
            event_dir = self._event_dir(event.run_id)
            if event_dir.exists() and any(event_dir.glob("*.json")):
                raise WorkflowPersistenceError("Workflow run already exists on disk.", details={"run_id": event.run_id, "path": str(event_dir)})
            self._atomic_create(self._event_path(event), event.to_dict())
            return event

    async def append(self, event: WorkflowEvent, *, expected_sequence: int) -> WorkflowEvent:
        # Appends one next immutable event after verifying the current disk sequence.
        async with self._lock:
            existing = self._read_events(event.run_id)
            if not existing:
                raise WorkflowPersistenceError("Workflow run does not exist for file append.", details={"run_id": event.run_id})
            actual = existing[-1].sequence
            if actual != expected_sequence or event.sequence != expected_sequence + 1:
                raise WorkflowPersistenceError("Workflow file event optimistic sequence conflict.", details={"run_id": event.run_id, "expected_sequence": expected_sequence, "actual_sequence": actual, "event_sequence": event.sequence})
            if any(item.event_id == event.event_id for item in existing):
                raise WorkflowPersistenceError("Duplicate workflow event ID on disk.", details={"event_id": event.event_id, "run_id": event.run_id})
            self._atomic_create(self._event_path(event), event.to_dict())
            return event

    async def events(self, run_id: str, *, after_sequence: int = 0, through_sequence: int | None = None) -> tuple[WorkflowEvent, ...]:
        # Reads canonical event files in numeric sequence order and filters boundaries.
        async with self._lock:
            events = self._read_events(run_id)
            return tuple(event for event in events if event.sequence > after_sequence and (through_sequence is None or event.sequence <= through_sequence))

    async def put_checkpoint(self, checkpoint: WorkflowCheckpoint) -> WorkflowCheckpoint:
        # Creates an immutable checkpoint after verifying event and sequence boundaries.
        async with self._lock:
            events = self._read_events(checkpoint.run_id)
            if not events or checkpoint.event_sequence > events[-1].sequence:
                raise WorkflowPersistenceError("File checkpoint references a missing future event.", details={"run_id": checkpoint.run_id, "event_sequence": checkpoint.event_sequence})
            existing = self._read_checkpoints(checkpoint.run_id)
            if existing and checkpoint.event_sequence <= existing[-1].event_sequence:
                raise WorkflowPersistenceError("File checkpoint sequence must increase.", details={"run_id": checkpoint.run_id, "event_sequence": checkpoint.event_sequence, "latest": existing[-1].event_sequence})
            self._atomic_create(self._checkpoint_path(checkpoint), checkpoint.to_dict())
            return checkpoint

    async def latest_checkpoint(self, run_id: str, *, through_sequence: int | None = None) -> WorkflowCheckpoint | None:
        # Returns the newest valid checkpoint at or before an optional sequence.
        async with self._lock:
            checkpoints = self._read_checkpoints(run_id)
            eligible = [item for item in checkpoints if through_sequence is None or item.event_sequence <= through_sequence]
            return eligible[-1] if eligible else None

    def _read_events(self, run_id: str) -> tuple[WorkflowEvent, ...]:
        # Parses sorted event files and verifies contiguous canonical sequences.
        paths = sorted(self._event_dir(run_id).glob("*.json")) if self._event_dir(run_id).exists() else []
        events = tuple(WorkflowEvent.from_dict(self._read_json(path)) for path in paths)
        expected = tuple(range(1, len(events) + 1))
        actual = tuple(event.sequence for event in events)
        if actual != expected:
            raise WorkflowPersistenceError("Workflow file event sequence is corrupt or non-contiguous.", details={"run_id": run_id, "actual_sequences": actual[:50]})
        return events

    def _read_checkpoints(self, run_id: str) -> tuple[WorkflowCheckpoint, ...]:
        # Parses checkpoint files in event-sequence order without projecting them.
        directory = self._checkpoint_dir(run_id)
        paths = sorted(directory.glob("*.json")) if directory.exists() else []
        return tuple(WorkflowCheckpoint.from_dict(self._read_json(path)) for path in paths)

    def _atomic_create(self, path: Path, value: dict[str, object]) -> None:
        # Writes one same-directory temporary JSON file and never intentionally overwrites.
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise WorkflowPersistenceError("Workflow store record already exists.", details={"path": str(path)})
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise WorkflowPersistenceError("Workflow store record appeared during atomic create.", details={"path": str(path)}) from exc
        except WorkflowPersistenceError:
            raise
        except Exception as exc:
            raise WorkflowPersistenceError("Workflow file store could not create a record.", details={"path": str(path), "temporary": str(temporary)}) from exc
        finally:
            if temporary.exists():
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    # Cleanup failure must not replace the canonical persistence error.
                    pass

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        # Parses one JSON object and wraps filesystem/shape failures with path context.
        try:
            with path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, dict):
                raise TypeError("Stored JSON root must be an object.")
            return value
        except Exception as exc:
            raise WorkflowPersistenceError("Workflow file store record is unreadable or corrupt.", details={"path": str(path)}) from exc

    def _event_dir(self, run_id: str) -> Path:
        # Resolves the immutable event directory for one run ID.
        return self.root / "runs" / run_id / "events"

    def _checkpoint_dir(self, run_id: str) -> Path:
        # Resolves the immutable checkpoint directory for one run ID.
        return self.root / "runs" / run_id / "checkpoints"

    def _event_path(self, event: WorkflowEvent) -> Path:
        # Builds a lexically sequence-sorted event filename.
        return self._event_dir(event.run_id) / f"{event.sequence:020d}.json"

    def _checkpoint_path(self, checkpoint: WorkflowCheckpoint) -> Path:
        # Builds a lexically event-sequence-sorted checkpoint filename.
        return self._checkpoint_dir(checkpoint.run_id) / f"{checkpoint.event_sequence:020d}.json"


__all__ = ["FileWorkflowStore"]
