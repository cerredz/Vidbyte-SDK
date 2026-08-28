"""FILE: vidbyte/harnesses/__init__.py

PURPOSE:
    Exposes the public harness execution-contract surface from one stable package
    import while preserving the HarnessClient namespace entry.

ROLE IN CODEBASE:
    SDK callers import the Harness base class, contracts, configuration, registry,
    trajectory collection/sinks, redaction, and typed failures from vidbyte.harnesses.

ARCHITECTURE NOTE:
    Imports here are export shims only. They must not create stores, register
    implementations, parse configuration, or execute harness code. Persistence is
    provided by vidbyte.sessions; this package owns only the run envelope and the
    consented, redacted trajectory export.

PUBLIC API INVENTORY:
    HarnessClient; the Harness base class and wrap_implementation; contracts/enums;
    HarnessConfigLoader; structural registry; TrajectoryCollector and the
    TrajectorySink family; redaction helpers; and the harness error family.

WHAT NOT TO DO IN THIS FILE:
    1. Do not instantiate a client or backend at import time.
    2. Do not import optional provider/database dependencies.
    3. Do not hide a public typed error from package callers.

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
    HarnessExecutionResult,
    HarnessRun,
    HarnessRunStatus,
    HarnessSpec,
    TrajectoryRecord,
)
from vidbyte.harnesses.dataset import TrajectoryCollector
from vidbyte.harnesses.errors import (
    HarnessConfigurationError,
    HarnessCredentialConfigError,
    HarnessDuplicateRegistrationError,
    HarnessError,
    HarnessExecutionError,
    HarnessFileReferenceError,
    HarnessRegistrationError,
    HarnessSinkError,
    HarnessTimeoutError,
    HarnessVersionError,
)
from vidbyte.harnesses.execution import Harness, wrap_implementation
from vidbyte.harnesses.registry import (
    HarnessFactory,
    HarnessImplementation,
    HarnessRegistry,
)
from vidbyte.harnesses.serialization import HarnessRedactor, HarnessSecretPolicy
from vidbyte.harnesses.stores import (
    FileTrajectorySink,
    InMemoryTrajectorySink,
    TrajectorySink,
)

__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "FileTrajectorySink",
    "Harness",
    "HarnessClient",
    "HarnessConfigLoader",
    "HarnessConfigurationError",
    "HarnessCredentialConfigError",
    "HarnessDuplicateRegistrationError",
    "HarnessError",
    "HarnessExecutionError",
    "HarnessExecutionResult",
    "HarnessFactory",
    "HarnessFileReferenceError",
    "HarnessImplementation",
    "HarnessRedactor",
    "HarnessRegistrationError",
    "HarnessRegistry",
    "HarnessRun",
    "HarnessRunStatus",
    "HarnessSecretPolicy",
    "HarnessSinkError",
    "HarnessSpec",
    "HarnessTimeoutError",
    "HarnessVersionError",
    "InMemoryTrajectorySink",
    "TrajectoryCollector",
    "TrajectoryRecord",
    "TrajectorySink",
    "wrap_implementation",
]
