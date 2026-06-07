"""Context Protocol Header

Description:
    Defines the serializable data contracts for durable agent sessions.
Purpose:
    Provides the RunState snapshot, Checkpoint DAG node, and SessionMeta records
    persisted by the sessions abstraction, plus the policy/status enums.
Architecture:
    - CheckpointPolicy / SessionStatus / TraceCapture: behavior + lifecycle enums.
    - RunState: serializable agent snapshot (config-by-value + history, no secrets).
    - Checkpoint: one node in the append-only checkpoint DAG.
    - SessionMeta: per-session head pointer, lineage, and listing metadata.
Relations:
    Consumed by vidbyte.sessions (serialization, stores, session facade) and by
    vidbyte.agents.base export_state()/restore().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

SESSION_SCHEMA_VERSION: int = 1


class CheckpointPolicy(str, Enum):
    """When a session writes checkpoints during execution."""

    PER_TURN = "per_turn"
    PER_STEP = "per_step"
    MANUAL = "manual"


class SessionStatus(str, Enum):
    """Lifecycle status recorded on a session and its checkpoints."""

    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class TraceCapture(str, Enum):
    """How much trace data a session persists alongside each checkpoint."""

    OFF = "off"
    AUTO = "auto"
    ARTIFACT = "artifact"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class RunState:
    """Serializable snapshot of an agent's resumable state (no live objects, no secrets)."""

    schema_version: int
    agent_name: str
    system_prompt: str
    description: str
    capabilities: tuple[str, ...]
    provider: str | None
    model_name: str | None
    modality: str
    temperature: float | None
    runner_options: Mapping[str, Any]
    runtime_type: str
    runtime_config: Mapping[str, Any]
    algorithm: str
    metadata: Mapping[str, Any]
    agent_metadata: Mapping[str, Any]
    tool_names: tuple[str, ...]
    history: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """One node in a session's append-only checkpoint DAG."""

    id: str
    session_id: str
    parent_id: str | None
    seq: int
    created_at: str
    run_state: RunState
    label: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    trace_artifact: Mapping[str, Any] | None = None
    trace_summary: Mapping[str, Any] | None = None
    trace_events: tuple[Mapping[str, Any], ...] | None = None


@dataclass(frozen=True, slots=True)
class SessionMeta:
    """Per-session head pointer, lineage, and listing metadata."""

    session_id: str
    head_id: str | None
    parent_session_id: str | None
    agent_name: str
    status: SessionStatus
    created_at: str
    updated_at: str
    tags: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "SESSION_SCHEMA_VERSION",
    "CheckpointPolicy",
    "SessionStatus",
    "TraceCapture",
    "RunState",
    "Checkpoint",
    "SessionMeta",
]
