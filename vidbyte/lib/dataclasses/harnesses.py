"""FILE: vidbyte/lib/dataclasses/harnesses.py

PURPOSE:
    Defines the immutable, JSON-oriented contracts shared by harness loading,
    execution, persistence, and dataset export. This file owns record shapes and
    lifecycle enums only; it must not perform I/O or execute harness logic.

ROLE IN CODEBASE:
    Imported by vidbyte.harnesses contracts, serializers, stores, execution, and
    dataset modules. The public root package re-exports selected types. It depends
    only on Python dataclasses, enums, and typing so every adapter can import it.

ARCHITECTURE NOTE:
    A deterministic HarnessSpec identifies resolved behavior, while a unique
    HarnessRun identifies one execution and HarnessEvent records ordered evidence.
    See docs/design/harness-execution-contract.md.

PUBLIC API INVENTORY:
    HARNESS_SCHEMA_VERSION; HarnessRunStatus; HarnessCaptureLevel;
    HarnessCaptureScope; HarnessPersistenceMode; HarnessSpec;
    HarnessErrorRecord; HarnessArtifactRef; HarnessEvent; HarnessRun;
    HarnessExecutionResult.

COMMON MODIFICATION PATTERNS:
    Add persisted fields here first, then update HarnessSerializer, local stores,
    package exports, the harness README, and the schema-version migration policy.

WHAT NOT TO DO IN THIS FILE:
    1. Do not parse configuration; vidbyte/harnesses/config.py owns loading.
    2. Do not mutate lifecycle state; vidbyte/harnesses/execution.py owns it.
    3. Do not add backend behavior; vidbyte/harnesses/store.py owns persistence.

KNOWN EDGE CASES:
    Frozen dataclasses do not recursively freeze caller-provided mappings. All
    SDK construction paths copy and serialize mappings before persistence.

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


class HarnessCaptureLevel(str, Enum):
    """Amount of dataset payload stored for one execution."""

    MINIMAL = "minimal"
    FULL = "full"


class HarnessCaptureScope(str, Enum):
    """Whether capture covers only the boundary or instrumented internal work."""

    BOUNDARY = "boundary"
    INSTRUMENTED = "instrumented"


class HarnessPersistenceMode(str, Enum):
    """Whether storage failures are recorded or raised to the caller."""

    BEST_EFFORT = "best_effort"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class HarnessSpec:
    """Exact requested and resolved behavior configuration for a harness variant."""

    schema_version: int
    spec_id: str
    harness_type: str
    harness_version: str
    agents: tuple[Mapping[str, Any], ...]
    params: Mapping[str, Any]
    requested_config: Mapping[str, Any]
    resolved_config: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class HarnessErrorRecord:
    """Safe persisted projection of an execution failure."""

    exception_type: str
    message: str


@dataclass(frozen=True, slots=True)
class HarnessArtifactRef:
    """Reference to an artifact retained outside the run record."""

    artifact_id: str
    uri: str
    media_type: str | None = None
    sha256: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HarnessEvent:
    """One ordered lifecycle or implementation event within a run."""

    schema_version: int
    event_id: str
    run_id: str
    sequence: int
    event_type: str
    created_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HarnessRun:
    """Canonical safe record for one harness execution."""

    schema_version: int
    run_id: str
    spec_id: str
    status: HarnessRunStatus
    started_at: str
    ended_at: str | None
    capture_level: HarnessCaptureLevel
    capture_scope: HarnessCaptureScope
    request: Any = None
    response: Any = None
    error: HarnessErrorRecord | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[HarnessArtifactRef, ...] = ()
    session_ids: tuple[str, ...] = ()
    event_count: int = 0
    persistence_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HarnessExecutionResult:
    """Raw implementation output paired with its canonical terminal run."""

    output: Any
    run: HarnessRun


__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "HarnessArtifactRef",
    "HarnessCaptureLevel",
    "HarnessCaptureScope",
    "HarnessErrorRecord",
    "HarnessEvent",
    "HarnessExecutionResult",
    "HarnessPersistenceMode",
    "HarnessRun",
    "HarnessRunStatus",
    "HarnessSpec",
]
