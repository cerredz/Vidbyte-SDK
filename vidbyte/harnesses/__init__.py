"""FILE: vidbyte/harnesses/__init__.py

PURPOSE:
    Exposes the complete public harness execution-contract surface from one
    stable package import while preserving the HarnessClient namespace entry.

ROLE IN CODEBASE:
    SDK callers import contracts, configuration, registry, execution, stores,
    serialization, dataset export, and typed failures from vidbyte.harnesses.

ARCHITECTURE NOTE:
    Imports here are export shims only. They must not create stores, register
    implementations, parse configuration, or execute harness code.

PUBLIC API INVENTORY:
    HarnessClient; contracts/enums; HarnessConfigLoader; structural registry;
    HarnessContext/LoadedHarness; HarnessStore and local stores; serializer;
    dataset exporter; and the complete harness error family.

COMMON MODIFICATION PATTERNS:
    Add imports and __all__ entries when a public contract is introduced, then
    decide separately whether the root vidbyte package should re-export it.

WHAT NOT TO DO IN THIS FILE:
    1. Do not instantiate a client or backend at import time.
    2. Do not import optional provider/database dependencies.
    3. Do not hide a public typed error from package callers.

KNOWN EDGE CASES:
    TYPE_CHECKING indirection in registry.py prevents its HarnessContext annotation
    from introducing an import cycle through this package surface.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    Covered by package/root public-import smoke verification; no dedicated test
    file was added under the approved no-tests workflow.
"""

from __future__ import annotations

from vidbyte.harnesses.client import HarnessClient
from vidbyte.harnesses.config import HarnessConfigLoader
from vidbyte.harnesses.contracts import (
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
from vidbyte.harnesses.dataset import HarnessDatasetExporter
from vidbyte.harnesses.errors import (
    HarnessConfigurationError,
    HarnessCredentialConfigError,
    HarnessDatasetExportError,
    HarnessDuplicateRegistrationError,
    HarnessError,
    HarnessEventSequenceError,
    HarnessExecutionError,
    HarnessFileReferenceError,
    HarnessRegistrationError,
    HarnessRunConflictError,
    HarnessRunTransitionError,
    HarnessSerializationError,
    HarnessSpecCollisionError,
    HarnessStoreError,
    HarnessTimeoutError,
    HarnessVersionError,
)
from vidbyte.harnesses.execution import HarnessContext, LoadedHarness
from vidbyte.harnesses.registry import HarnessFactory, HarnessImplementation, HarnessRegistry
from vidbyte.harnesses.serialization import HarnessSecretPolicy, HarnessSerializer
from vidbyte.harnesses.store import BaseHarnessStore, HarnessStore
from vidbyte.harnesses.stores import FileHarnessStore, InMemoryHarnessStore

__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "BaseHarnessStore",
    "FileHarnessStore",
    "HarnessArtifactRef",
    "HarnessCaptureLevel",
    "HarnessCaptureScope",
    "HarnessClient",
    "HarnessConfigLoader",
    "HarnessConfigurationError",
    "HarnessContext",
    "HarnessCredentialConfigError",
    "HarnessDatasetExportError",
    "HarnessDatasetExporter",
    "HarnessDuplicateRegistrationError",
    "HarnessError",
    "HarnessErrorRecord",
    "HarnessEvent",
    "HarnessEventSequenceError",
    "HarnessExecutionError",
    "HarnessExecutionResult",
    "HarnessFactory",
    "HarnessFileReferenceError",
    "HarnessImplementation",
    "HarnessPersistenceMode",
    "HarnessRegistrationError",
    "HarnessRegistry",
    "HarnessRun",
    "HarnessRunConflictError",
    "HarnessRunStatus",
    "HarnessRunTransitionError",
    "HarnessSecretPolicy",
    "HarnessSerializationError",
    "HarnessSerializer",
    "HarnessSpec",
    "HarnessSpecCollisionError",
    "HarnessStore",
    "HarnessStoreError",
    "HarnessTimeoutError",
    "HarnessVersionError",
    "InMemoryHarnessStore",
    "LoadedHarness",
]
