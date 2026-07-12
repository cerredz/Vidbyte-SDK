"""FILE: vidbyte/harnesses/contracts.py

PURPOSE:
    Provides the feature-local public import path for harness specification,
    execution, event, artifact, error-record, and policy dataclasses. Contract
    definitions remain centralized in vidbyte.lib.dataclasses.harnesses.

ROLE IN CODEBASE:
    Imported by all vidbyte.harnesses modules and by users who prefer the feature
    namespace. It calls no code and only re-exports the central contract module.

ARCHITECTURE NOTE:
    This compatibility shim mirrors vidbyte.sessions.contracts so shared data has
    one definition while feature imports remain stable.

PUBLIC API INVENTORY:
    Re-exports HARNESS_SCHEMA_VERSION and every public harness dataclass/enum.

COMMON MODIFICATION PATTERNS:
    When adding a central contract, add its import and __all__ entry here and in
    vidbyte/lib/dataclasses/__init__.py.

WHAT NOT TO DO IN THIS FILE:
    1. Do not duplicate dataclass definitions.
    2. Do not add loader, execution, or storage behavior.
    3. Do not import concrete stores or implementations.

KNOWN EDGE CASES:
    Import order must stay dependency-light because errors and serializers load
    this module near package initialization.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Covered by public import and harness smoke verification; no dedicated test file
    was added under the approved no-tests workflow.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.harnesses import (
    HARNESS_SCHEMA_VERSION,
    HarnessArtifactRef,
    HarnessCaptureLevel,
    HarnessCaptureScope,
    HarnessErrorRecord,
    HarnessEvent,
    HarnessExecutionResult,
    HarnessPersistenceMode,
    HarnessRun,
    HarnessRunStatus,
    HarnessSpec,
)

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
