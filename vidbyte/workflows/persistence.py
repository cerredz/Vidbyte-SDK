"""FILE: vidbyte/workflows/persistence.py
PURPOSE: Defines durable workflow definitions, checkpoints, store protocol, and validation.
ROLE IN CODEBASE: graph.py creates definitions; machine.py uses stores; store adapters implement this contract.

ARCHITECTURE NOTE:
    Definitions bind executable structure to a stable ID. Events remain canonical;
    checkpoints are immutable projection caches that may be discarded and rebuilt.
    Workflow persistence is deliberately separate from agent Session persistence.

PUBLIC API INVENTORY:
    WorkflowCheckpointPolicy: Per-step or caller-managed checkpoint behavior.
    WorkflowDefinitionRecord: Versioned canonical graph identity and structure.
    WorkflowCheckpoint: Immutable state/projection cache at one event sequence.
    WorkflowStore: Async append/read/checkpoint persistence protocol.
    assert_checkpoint_compatible: Cold-resume definition/schema guard.

COMMON MODIFICATION PATTERNS:
    Add durable fields additively, include them in to_dict/from_dict, and bump the
    schema version when older readers cannot safely ignore the change.

WHAT NOT TO DO IN THIS FILE:
    1. Do not execute callbacks or reduce events.
    2. Do not reuse SessionStore for graph state.
    3. Do not treat checkpoints as replacements for retained events.

KNOWN EDGE CASES:
    Durable stores require explicit graph versions because live Python callables,
    prompt text, and credentials cannot be fingerprinted safely from object reprs.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke covers compatibility and corruption.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeVar, runtime_checkable

from .errors import WorkflowResumeError
from .events import WORKFLOW_SCHEMA_VERSION, WorkflowEvent, _freeze_workflow_json, _thaw_workflow_json, workflow_json_value


StateT = TypeVar("StateT")


class WorkflowCheckpointPolicy(str, Enum):
    """Controls whether the runtime checkpoints every completed durable boundary."""

    PER_STEP = "per_step"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class WorkflowDefinitionRecord:
    """Canonical graph identity stored before a run begins."""

    definition_id: str
    name: str
    version: str | None
    structure: Mapping[str, Any]
    schema_version: int = WORKFLOW_SCHEMA_VERSION
    state_schema_id: str = ""

    def __post_init__(self) -> None:
        # Freezes JSON-ready definition data and validates durable version fields.
        if self.schema_version != WORKFLOW_SCHEMA_VERSION:
            raise ValueError(f"Unsupported workflow definition schema version: {self.schema_version}.")
        object.__setattr__(self, "definition_id", _required_text(self.definition_id, "WorkflowDefinitionRecord.definition_id"))
        object.__setattr__(self, "name", _required_text(self.name, "WorkflowDefinitionRecord.name"))
        object.__setattr__(self, "version", _optional_text(self.version))
        object.__setattr__(self, "state_schema_id", _required_text(self.state_schema_id, "WorkflowDefinitionRecord.state_schema_id"))
        object.__setattr__(self, "structure", _freeze_workflow_json(workflow_json_value(dict(self.structure))))

    def to_dict(self) -> dict[str, Any]:
        # Returns the complete JSON-ready definition record used by stores.
        return {
            "schema_version": self.schema_version,
            "definition_id": self.definition_id,
            "name": self.name,
            "version": self.version,
            "state_schema_id": self.state_schema_id,
            "structure": _thaw_workflow_json(self.structure),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkflowDefinitionRecord":
        # Reconstructs a stored definition and reports malformed required fields.
        try:
            return cls(
                schema_version=int(value["schema_version"]),
                definition_id=str(value["definition_id"]),
                name=str(value["name"]),
                version=value.get("version"),
                state_schema_id=str(value["state_schema_id"]),
                structure=value["structure"],
            )
        except Exception as exc:
            raise WorkflowResumeError("Stored workflow definition is corrupt or incomplete.", details={"available_fields": sorted(map(str, value))}) from exc


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    """Immutable projection cache written at a canonical event boundary."""

    checkpoint_id: str
    definition_id: str
    run_id: str
    event_sequence: int
    super_step: int
    state_payload: Mapping[str, Any]
    projection_payload: Mapping[str, Any]
    created_at: str
    schema_version: int = WORKFLOW_SCHEMA_VERSION
    state_schema_id: str = ""

    def __post_init__(self) -> None:
        # Validates checkpoint identity and freezes JSON-ready state/projection payloads.
        if self.schema_version != WORKFLOW_SCHEMA_VERSION:
            raise ValueError(f"Unsupported workflow checkpoint schema version: {self.schema_version}.")
        for name in ("checkpoint_id", "definition_id", "run_id", "created_at", "state_schema_id"):
            object.__setattr__(self, name, _required_text(getattr(self, name), f"WorkflowCheckpoint.{name}"))
        if self.event_sequence <= 0 or self.super_step < 0:
            raise ValueError("WorkflowCheckpoint event_sequence must be positive and super_step non-negative.")
        object.__setattr__(self, "state_payload", _freeze_workflow_json(workflow_json_value(dict(self.state_payload))))
        object.__setattr__(self, "projection_payload", _freeze_workflow_json(workflow_json_value(dict(self.projection_payload))))

    def to_dict(self) -> dict[str, Any]:
        # Returns the exact durable checkpoint envelope used by store adapters.
        return {
            "schema_version": self.schema_version,
            "checkpoint_id": self.checkpoint_id,
            "definition_id": self.definition_id,
            "run_id": self.run_id,
            "event_sequence": self.event_sequence,
            "super_step": self.super_step,
            "state_schema_id": self.state_schema_id,
            "state_payload": _thaw_workflow_json(self.state_payload),
            "projection_payload": _thaw_workflow_json(self.projection_payload),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkflowCheckpoint":
        # Reconstructs a stored checkpoint and reports malformed required fields.
        try:
            return cls(
                schema_version=int(value["schema_version"]),
                checkpoint_id=str(value["checkpoint_id"]),
                definition_id=str(value["definition_id"]),
                run_id=str(value["run_id"]),
                event_sequence=int(value["event_sequence"]),
                super_step=int(value["super_step"]),
                state_schema_id=str(value["state_schema_id"]),
                state_payload=value["state_payload"],
                projection_payload=value["projection_payload"],
                created_at=str(value["created_at"]),
            )
        except Exception as exc:
            raise WorkflowResumeError("Stored workflow checkpoint is corrupt or incomplete.", details={"available_fields": sorted(map(str, value))}) from exc


@runtime_checkable
class WorkflowStore(Protocol):
    """Append-only persistence boundary for definitions, events, and checkpoints."""

    @property
    def durable(self) -> bool:
        # Reports whether cold resume requires an explicit graph version.
        ...

    async def put_definition(self, definition: WorkflowDefinitionRecord) -> WorkflowDefinitionRecord:
        # Creates or verifies an identical definition record.
        ...

    async def get_definition(self, definition_id: str) -> WorkflowDefinitionRecord | None:
        # Reads one stored definition without mutating it.
        ...

    async def begin_run(self, event: WorkflowEvent) -> WorkflowEvent:
        # Atomically creates a run whose first event has sequence one.
        ...

    async def append(self, event: WorkflowEvent, *, expected_sequence: int) -> WorkflowEvent:
        # Appends exactly the next event under optimistic sequence checking.
        ...

    async def events(self, run_id: str, *, after_sequence: int = 0, through_sequence: int | None = None) -> tuple[WorkflowEvent, ...]:
        # Returns canonical events in ascending sequence order.
        ...

    async def put_checkpoint(self, checkpoint: WorkflowCheckpoint) -> WorkflowCheckpoint:
        # Creates one immutable checkpoint after its event boundary exists.
        ...

    async def latest_checkpoint(self, run_id: str, *, through_sequence: int | None = None) -> WorkflowCheckpoint | None:
        # Returns the newest checkpoint at or before an optional sequence.
        ...


def assert_checkpoint_compatible(checkpoint: WorkflowCheckpoint, definition: WorkflowDefinitionRecord) -> None:
    # Rejects cold resume when executable definition or state reducer identity changed.
    if checkpoint.definition_id != definition.definition_id:
        raise WorkflowResumeError("Checkpoint definition does not match the compiled workflow.", details={"checkpoint_definition_id": checkpoint.definition_id, "definition_id": definition.definition_id})
    if checkpoint.state_schema_id != definition.state_schema_id:
        raise WorkflowResumeError("Checkpoint state schema does not match the compiled workflow.", details={"checkpoint_state_schema_id": checkpoint.state_schema_id, "state_schema_id": definition.state_schema_id})
    if checkpoint.schema_version != definition.schema_version:
        raise WorkflowResumeError("Checkpoint schema version does not match the compiled workflow.", details={"checkpoint_schema_version": checkpoint.schema_version, "definition_schema_version": definition.schema_version})


def _required_text(value: str, field_name: str) -> str:
    # Normalizes durable identifiers and rejects empty values early.
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty.")
    return text


def _optional_text(value: str | None) -> str | None:
    # Normalizes optional definition versions without inventing one.
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "WorkflowCheckpoint",
    "WorkflowCheckpointPolicy",
    "WorkflowDefinitionRecord",
    "WorkflowStore",
    "assert_checkpoint_compatible",
]
