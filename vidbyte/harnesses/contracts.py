"""FILE: vidbyte/harnesses/contracts.py

PURPOSE:
    Provides the feature-local public import path for harness specification, run
    manifest, trajectory-record, and lifecycle contracts. Contract definitions
    remain centralized in vidbyte.lib.dataclasses.harnesses.

ROLE IN CODEBASE:
    Imported by all vidbyte.harnesses modules and by users who prefer the feature
    namespace. It calls no code and only re-exports the central contract module.

ARCHITECTURE NOTE:
    This compatibility shim mirrors vidbyte.sessions.contracts so shared data has
    one definition while feature imports remain stable. The bespoke capture
    contracts (events, artifact refs, capture/persistence enums) were removed when
    persistence pivoted onto durable Sessions; only the survivors are re-exported.

PUBLIC API INVENTORY:
    Re-exports HARNESS_SCHEMA_VERSION, HarnessRunStatus, HarnessSpec, HarnessRun,
    TrajectoryRecord, HarnessExecutionResult, and SinkFailureEvent.

WHAT NOT TO DO IN THIS FILE:
    1. Do not duplicate dataclass definitions.
    2. Do not add loader, execution, or storage behavior.
    3. Do not re-export the removed event/store contracts.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Covered by public import and harness smoke verification; no dedicated test file
    was added under the approved no-tests workflow.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.harnesses import (
    HARNESS_SCHEMA_VERSION,
    HarnessExecutionResult,
    HarnessRun,
    HarnessRunStatus,
    HarnessSpec,
    SinkFailureEvent,
    TrajectoryRecord,
)

__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "HarnessExecutionResult",
    "HarnessRun",
    "HarnessRunStatus",
    "HarnessSpec",
    "SinkFailureEvent",
    "TrajectoryRecord",
]
