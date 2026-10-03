"""FILE: vidbyte/lib/dataclasses/harnesses.py

PURPOSE:
    Defines the immutable, JSON-oriented contracts shared by harness loading,
    execution, and trajectory collection. This file owns record shapes and the
    run-lifecycle enum only; it must not perform I/O or execute harness logic.

ROLE IN CODEBASE:
    Imported by vidbyte.harnesses contracts, config, execution, and dataset
    modules. The public root package re-exports selected types. It depends only
    on Python dataclasses, enums, and typing so every adapter can import it.

ARCHITECTURE NOTE:
    A deterministic HarnessSpec identifies resolved behavior (config + code
    version), a unique HarnessRun is the operational manifest for one execution,
    and a TrajectoryRecord is the self-contained, redacted export unit joined
    from the durable Session stream. Capture is not reinvented here: per-agent
    evidence comes from vidbyte.sessions checkpoints, not a bespoke event stream.
    See docs/design/harness-execution-contract.md.

PUBLIC API INVENTORY:
    HARNESS_SCHEMA_VERSION; HarnessRunStatus; HarnessSpec; HarnessRun;
    TrajectoryRecord; HarnessExecutionResult.

COMMON MODIFICATION PATTERNS:
    Add persisted fields here first, then update the redaction/collector pass,
    package exports, the harness README, and the schema-version policy.

WHAT NOT TO DO IN THIS FILE:
    1. Do not parse configuration; vidbyte/harnesses/config.py owns loading.
    2. Do not mutate lifecycle state; vidbyte/harnesses/execution.py owns it.
    3. Do not re-introduce a bespoke event/store contract; Sessions own capture.

KNOWN EDGE CASES:
    Frozen dataclasses do not recursively freeze caller-provided mappings. All
    SDK construction paths copy and redact mappings before export.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    No dedicated test files were added under the approved no-tests workflow;
    verification uses the repository suite and the documented harness smoke run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

HARNESS_SCHEMA_VERSION: int = 1


class HarnessRunStatus(str, Enum):
    """Lifecycle states for one harness execution."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class HarnessSpec:
    """Exact requested and resolved behavior configuration for a harness variant.

    Identity (spec_id) folds the code-supplied version together with the resolved
    agents/orchestration behavior, so a code change and a config change each fork
    a new variant. Descriptive `metadata` is carried through but excluded from
    spec_id, exactly like run metadata, so renaming a harness never forks identity.
    """

    schema_version: int
    spec_id: str
    harness_type: str
    harness_version: str
    agents: tuple[Mapping[str, Any], ...]
    orchestration: Mapping[str, Any]
    metadata: Mapping[str, Any]
    requested_config: Mapping[str, Any]
    resolved_config: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class HarnessRun:
    """Operational manifest for one harness execution.

    This is the lightweight index into the durable Session stream, not the export
    unit. The self-contained, sellable record is TrajectoryRecord.
    """

    schema_version: int
    run_id: str
    spec_id: str
    status: HarnessRunStatus
    started_at: str
    ended_at: str | None
    session_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TrajectoryRecord:
    """Self-contained, redacted, versioned export unit for one harness run.

    The resolved specification is inlined (not referenced by id) so a downstream
    consumer needs no access to our store: config, prompts, tools, and
    orchestration all travel with the record. `reward` is an optional eval label.
    """

    schema_version: int
    run_id: str
    task: Any
    spec: Mapping[str, Any]
    agents: tuple[Mapping[str, Any], ...]
    output: Any
    status: str
    reward: float | None
    created_at: str


@dataclass(frozen=True, slots=True)
class HarnessExecutionResult:
    """Raw implementation output paired with its operational run manifest."""

    output: Any
    run: HarnessRun


@dataclass(frozen=True, slots=True)
class SinkFailureEvent:
    """Credential-free record of one swallowed collection/sink failure.

    Built by Harness._report_sink_failure() and handed to the optional
    on_sink_error callback. `message` has already passed through
    HarnessRedactor.safe_error_message(); `sink_type`/`error_type` are class
    names only, never instance state, so nothing sink-instance-specific
    (bucket name, endpoint, credentials) can leak through this event.
    """

    run_id: str
    sink_type: str
    error_type: str
    message: str
    occurred_at: str


__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "HarnessExecutionResult",
    "HarnessRun",
    "HarnessRunStatus",
    "HarnessSpec",
    "SinkFailureEvent",
    "TrajectoryRecord",
]
