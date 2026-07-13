"""FILE: vidbyte/workflows/events.py
PURPOSE: Defines the canonical append-only workflow event schema and serialization.
ROLE IN CODEBASE: machine.py creates events; stores persist them; projection.py replays them.

ARCHITECTURE NOTE:
    Events are workflow truth. Checkpoints cache a projection but never replace or
    edit this stream. Every payload is bounded, JSON-convertible data; executable
    callbacks, live agents, coroutine frames, and credentials never belong here.

PUBLIC API INVENTORY:
    WORKFLOW_SCHEMA_VERSION: Current durable event schema number.
    WorkflowEventType: Stable names for lifecycle, execution, policy, and child facts.
    WorkflowEventPayload: Typed immutable payload wrapper.
    WorkflowEvent: Canonical durable envelope with run/definition/sequence identity.
    WorkflowEventFactory: Creates correctly sequenced event envelopes.
    workflow_json_value: Converts supported typed values to durable JSON data.

COMMON MODIFICATION PATTERNS:
    Add an event type, teach projection.py how it changes the projection, emit it at
    one machine boundary, and document resume compatibility before shipping.

WHAT NOT TO DO IN THIS FILE:
    1. Do not mutate or supersede an existing event.
    2. Do not project control flow; projection.py owns replay semantics.
    3. Do not serialize secrets or arbitrary repr() output automatically.

KNOWN EDGE CASES:
    Events created by old in-memory PR #268 are not durable and require no migration.
    Sets are encoded in stable repr-sorted order because JSON has no set primitive.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-harness-state-machine-runtime.md

TESTS:
    No new test file by approved design; inline smoke round-trips every emitted event.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from .errors import WorkflowPersistenceError


WORKFLOW_SCHEMA_VERSION = 1


class WorkflowEventType(str, Enum):
    """Stable event names that fully describe workflow state and control changes."""

    DEFINITION_STORED = "definition_stored"
    RUN_STARTED = "run_started"
    LIFECYCLE_CHANGED = "lifecycle_changed"
    STAGE_STARTED = "stage_started"
    STAGE_RESTARTED = "stage_restarted"
    STAGE_FINISHED = "stage_finished"
    STAGE_FAILED = "stage_failed"
    OBSERVATION_RECORDED = "observation_recorded"
    USAGE_RECORDED = "usage_recorded"
    VALIDATION_FINISHED = "validation_finished"
    TRANSITION_SELECTED = "transition_selected"
    TRANSITION_REJECTED = "transition_rejected"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESPONDED = "approval_responded"
    INTERRUPT_REQUESTED = "interrupt_requested"
    INTERRUPT_RESPONDED = "interrupt_responded"
    SIGNAL_RECORDED = "signal_recorded"
    DETOUR_ENTERED = "detour_entered"
    DETOUR_RETURNED = "detour_returned"
    SENDS_STARTED = "sends_started"
    CHILD_SUSPENDED = "child_suspended"
    CHILD_FINISHED = "child_finished"
    STATE_COMMITTED = "state_committed"
    STUCK_DETECTED = "stuck_detected"
    ACTION_AUTHORIZED = "action_authorized"
    ACTION_DENIED = "action_denied"
    CHECKPOINT_WRITTEN = "checkpoint_written"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


@dataclass(frozen=True, slots=True)
class WorkflowEventPayload:
    """Immutable typed wrapper around one event's bounded JSON-ready fields."""

    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Converts and recursively freezes every durable payload container.
        converted = workflow_json_value(dict(self.data))
        object.__setattr__(self, "data", _freeze_workflow_json(converted))

    def to_dict(self) -> dict[str, Any]:
        # Returns a recursively mutable JSON-ready copy for projection/serialization.
        value = _thaw_workflow_json(self.data)
        return value if isinstance(value, dict) else {}


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """Canonical append-only workflow fact with optimistic sequence identity."""

    schema_version: int
    event_id: str
    definition_id: str
    run_id: str
    sequence: int
    super_step: int
    event_type: WorkflowEventType
    occurred_at: str
    payload: WorkflowEventPayload = field(default_factory=WorkflowEventPayload)
    stage: str | None = None
    elapsed_ms: float = 0.0

    def __post_init__(self) -> None:
        # Validates durable identity and normalizes enum/payload instances.
        if self.schema_version != WORKFLOW_SCHEMA_VERSION:
            raise WorkflowPersistenceError("Unsupported workflow event schema version.", details={"schema_version": self.schema_version, "supported": WORKFLOW_SCHEMA_VERSION})
        for name in ("event_id", "definition_id", "run_id"):
            object.__setattr__(self, name, _required_text(getattr(self, name), f"WorkflowEvent.{name}"))
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence <= 0:
            raise WorkflowPersistenceError("Workflow event sequence must be a positive integer.", details={"sequence": self.sequence})
        if not isinstance(self.super_step, int) or isinstance(self.super_step, bool) or self.super_step < 0:
            raise WorkflowPersistenceError("Workflow event super_step must be non-negative.", details={"super_step": self.super_step})
        event_type = self.event_type if isinstance(self.event_type, WorkflowEventType) else WorkflowEventType(self.event_type)
        payload = self.payload if isinstance(self.payload, WorkflowEventPayload) else WorkflowEventPayload(self.payload)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "payload", payload)
        object.__setattr__(self, "stage", _optional_text(self.stage))
        if self.elapsed_ms < 0:
            raise WorkflowPersistenceError("Workflow event elapsed_ms cannot be negative.", details={"elapsed_ms": self.elapsed_ms})

    def to_dict(self) -> dict[str, Any]:
        # Serializes the exact durable envelope without executable values.
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "definition_id": self.definition_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "super_step": self.super_step,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at,
            "stage": self.stage,
            "elapsed_ms": self.elapsed_ms,
            "payload": self.payload.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WorkflowEvent":
        # Reconstructs one event and rejects missing/corrupt durable fields.
        try:
            return cls(
                schema_version=int(value["schema_version"]),
                event_id=str(value["event_id"]),
                definition_id=str(value["definition_id"]),
                run_id=str(value["run_id"]),
                sequence=int(value["sequence"]),
                super_step=int(value["super_step"]),
                event_type=WorkflowEventType(value["event_type"]),
                occurred_at=str(value["occurred_at"]),
                stage=value.get("stage"),
                elapsed_ms=float(value.get("elapsed_ms", 0.0)),
                payload=WorkflowEventPayload(value.get("payload", {})),
            )
        except WorkflowPersistenceError:
            raise
        except Exception as exc:
            raise WorkflowPersistenceError("Stored workflow event is corrupt or incomplete.", details={"available_fields": sorted(map(str, value))}) from exc


class WorkflowEventFactory:
    """Creates event envelopes while the store remains authoritative for appends."""

    def __init__(self, definition_id: str, run_id: str, *, started_at: datetime | None = None) -> None:
        # Captures stable run identity and wall-clock origin for event evidence.
        self.definition_id = _required_text(definition_id, "definition_id")
        self.run_id = _required_text(run_id, "run_id")
        self.started_at = started_at or datetime.now(timezone.utc)

    def create(self, event_type: WorkflowEventType, *, sequence: int, super_step: int, stage: str | None = None, payload: Mapping[str, Any] | None = None) -> WorkflowEvent:
        # Builds one immutable event using caller-supplied expected sequence counters.
        now = datetime.now(timezone.utc)
        return WorkflowEvent(
            schema_version=WORKFLOW_SCHEMA_VERSION,
            event_id=f"wevt_{uuid4().hex}",
            definition_id=self.definition_id,
            run_id=self.run_id,
            sequence=sequence,
            super_step=super_step,
            event_type=event_type,
            occurred_at=now.isoformat(),
            stage=stage,
            elapsed_ms=max(0.0, (now - self.started_at).total_seconds() * 1000),
            payload=WorkflowEventPayload(payload or {}),
        )


def workflow_json_value(value: Any) -> Any:
    # Recursively converts supported typed state/evidence into deterministic JSON data.
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise WorkflowPersistenceError("Workflow event payload contains a non-finite float.", details={"value": str(value)})
        return value
    if isinstance(value, Enum):
        return workflow_json_value(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return workflow_json_value(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return workflow_json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): workflow_json_value(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [workflow_json_value(item) for item in sorted(value, key=repr)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [workflow_json_value(item) for item in value]
    raise WorkflowPersistenceError("Workflow event payload contains a non-serializable value.", details={"value_type": type(value).__name__})


def _freeze_workflow_json(value: Any) -> Any:
    # Recursively removes mutation handles from already validated JSON-ready data.
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_workflow_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_workflow_json(item) for item in value)
    return value


def _thaw_workflow_json(value: Any) -> Any:
    # Returns detached built-in containers suitable for reducers and JSON encoders.
    if isinstance(value, Mapping):
        return {str(key): _thaw_workflow_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw_workflow_json(item) for item in value]
    return value


def _required_text(value: str, field_name: str) -> str:
    # Normalizes required durable identifiers with field-specific diagnostics.
    text = str(value).strip()
    if not text:
        raise WorkflowPersistenceError(f"{field_name} cannot be empty.", details={"field": field_name})
    return text


def _optional_text(value: str | None) -> str | None:
    # Normalizes optional stage names without inventing empty identifiers.
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "WORKFLOW_SCHEMA_VERSION",
    "WorkflowEvent",
    "WorkflowEventFactory",
    "WorkflowEventPayload",
    "WorkflowEventType",
    "workflow_json_value",
]
