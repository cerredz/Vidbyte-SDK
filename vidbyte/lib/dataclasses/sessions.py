"""Context Protocol Header

Description:
    Defines serializable data contracts for durable agent sessions.
Purpose:
    Keeps session checkpoint, metadata, policy, and run-state dataclasses in the
    SDK-wide dataclass namespace while allowing session modules to re-export them.
Architecture:
    - CheckpointPolicy / SessionStatus / TraceCapture: behavior and lifecycle enums.
    - RunState: serializable agent snapshot with current BaseAgent configuration.
    - Checkpoint: one node in an append-only session checkpoint DAG.
    - SessionMeta: per-session head pointer, lineage, and listing metadata.
Relations:
    Re-exported by vidbyte.sessions.contracts and consumed by BaseAgent, stores,
    serializers, and built-in session tools.
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
    """Serializable snapshot of an agent's resumable state without live objects or secrets."""

    schema_version: int
    agent_name: str
    system_prompt: str
    description: str
    capabilities: tuple[str, ...]
    provider: str | None
    model_name: str | None
    temperature: float | None
    runtime_type: str
    runtime_config: Mapping[str, Any]
    algorithm: str
    metadata: Mapping[str, Any]
    agent_metadata: Mapping[str, Any]
    tool_names: tuple[str, ...]
    history: tuple[Mapping[str, Any], ...]
    run_id: str | None = None
    runner_options: Mapping[str, Any] = field(default_factory=dict)
    loop_settings: Mapping[str, Any] = field(default_factory=dict)
    aggregate_plan: Mapping[str, Any] = field(default_factory=dict)
    context_summary: Mapping[str, Any] = field(default_factory=dict)
    trace_option: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] | None = None


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


@dataclass(frozen=True, slots=True)
class AgentUsage:
    """Usage totals for one agent within a durable session."""

    agent_name: str
    tokens: int
    tool_calls: int
    turns: int
    cost: float | None = None


@dataclass(frozen=True, slots=True)
class UsageRollup:
    """Usage totals for a durable session, with a per-agent breakdown."""

    tokens: int
    tool_calls: int
    turns: int
    latency: float | None
    cost: float | None
    per_agent: tuple[AgentUsage, ...]

    @classmethod
    def empty(cls) -> "UsageRollup":
        """Return the zero-value rollup for sessions with no head checkpoint."""
        return cls(tokens=0, tool_calls=0, turns=0, latency=None, cost=None, per_agent=())


__all__ = [
    "SESSION_SCHEMA_VERSION",
    "CheckpointPolicy",
    "SessionStatus",
    "TraceCapture",
    "RunState",
    "Checkpoint",
    "SessionMeta",
    "AgentUsage",
    "UsageRollup",
]
