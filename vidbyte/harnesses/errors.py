"""FILE: vidbyte/harnesses/errors.py

PURPOSE:
    Defines typed, agent-readable failures for harness configuration, registry,
    file references, trajectory sinks, execution, and timeout boundaries. This
    file owns diagnostic context, not validation or persistence behavior.

ROLE IN CODEBASE:
    Raised by every module under vidbyte.harnesses and consumed by SDK callers.
    It extends vidbyte.lib.errors.VidbyteSdkError and references HarnessRun only
    for execution failures that must carry their finalized record.

ARCHITECTURE NOTE:
    Static diagnostic guidance lives on each error class; raise sites pass only
    safe invocation-specific details. See docs/design/harness-execution-contract.md.

PUBLIC API INVENTORY:
    HarnessError and specialized configuration, credential, file-reference,
    version, registration, sink, execution, and timeout subclasses.
    HarnessError.to_context_packet() returns a self-contained safe diagnostic mapping.

COMMON MODIFICATION PATTERNS:
    Add one subclass per distinct failure mode, then reference it in the source
    file header and export it from vidbyte.harnesses when callers should catch it.

WHAT NOT TO DO IN THIS FILE:
    1. Do not include secrets, raw config payloads, or connection strings.
    2. Do not perform recovery; the raising boundary owns recovery semantics.
    3. Do not collapse distinct state failures into an untyped Exception.

KNOWN EDGE CASES:
    Execution errors carry a HarnessRun; configuration and setup failures occur
    before a run exists and therefore expose only safe details.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md

TESTS:
    No dedicated test files were added under the approved no-tests workflow;
    error packets are exercised by the documented inline smoke verification.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.harnesses import HarnessRun
from vidbyte.lib.errors import VidbyteSdkError

_DESIGN_URL = "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md"
_NO_TESTS = ("Approved no-tests workflow: run the repository suite and harness smoke verification.",)


class HarnessError(VidbyteSdkError):
    """Base class for harness failures with durable diagnostic context."""

    description = "A harness execution-contract boundary rejected unsafe or inconsistent state."
    expected_vs_actual = "Expected: the documented harness contract remains valid. Actual: a boundary observed state that violates it."
    blast_radius = ("vidbyte/harnesses",)
    possible_causes = ("Invalid caller input", "Corrupt or conflicting persisted state")
    fix_approaches = ("Inspect the safe details and reproduce at the named boundary.", "Correct the caller input or backend record before retrying.")
    doc_links = (_DESIGN_URL,)
    test_files = _NO_TESTS

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        # Stores only caller-supplied safe details alongside static repair guidance.
        super().__init__(message, details=details)

    def to_context_packet(self) -> dict[str, Any]:
        # Returns the typed failure, safe state, blast radius, and repair guidance.
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "details": dict(self.details),
            "description": self.description,
            "expected_vs_actual": self.expected_vs_actual,
            "blast_radius": tuple(self.blast_radius),
            "possible_causes": tuple(self.possible_causes),
            "fix_approaches": tuple(self.fix_approaches),
            "doc_links": tuple(self.doc_links),
            "test_files": tuple(self.test_files),
        }


class HarnessConfigurationError(HarnessError):
    """Raised when the common harness configuration envelope is invalid."""

    description = "Harness configuration could not be validated before implementation construction."
    expected_vs_actual = "Expected: schema_version, harness, and agents follow the public envelope (metadata/orchestration optional). Actual: a required field, type, or value is invalid."
    blast_radius = ("vidbyte/harnesses/config.py", "vidbyte/harnesses/execution.py")


class HarnessCredentialConfigError(HarnessConfigurationError):
    """Raised when a persistable behavior config contains a credential-like key."""

    description = "A credential-like key was found in configuration that is fingerprinted and persisted."
    expected_vs_actual = "Expected: credentials arrive through environment or provider construction. Actual: config contains a key that could persist a secret."
    possible_causes = ("API credentials were placed beside behavior parameters", "An authentication option was named like a secret")
    fix_approaches = ("Move credentials to environment or injected provider objects.", "Keep only non-secret provider/model identifiers in the harness config.")


class HarnessFileReferenceError(HarnessConfigurationError):
    """Raised when a $file config reference cannot be resolved safely."""

    description = "A local UTF-8 content reference used for specification identity could not be resolved."
    expected_vs_actual = "Expected: $file is the only mapping key and points to a readable file. Actual: its shape or target is invalid."
    blast_radius = ("vidbyte/harnesses/config.py",)


class HarnessVersionError(HarnessError):
    """Raised when configuration or persisted data uses an unsupported schema version."""

    description = "The SDK refuses to guess how to interpret an unknown harness schema."
    expected_vs_actual = "Expected: schema_version equals the SDK-supported version. Actual: the payload is missing a version or uses another value."
    fix_approaches = ("Use a matching SDK version or migrate the payload explicitly.", "Do not edit stored version numbers without migrating their fields.")


class HarnessRegistrationError(HarnessError):
    """Raised when an exact harness implementation factory cannot be resolved."""

    description = "No valid registered factory can build the requested harness type/version."
    expected_vs_actual = "Expected: a direct implementation or exact registered factory. Actual: the registry cannot supply one."
    blast_radius = ("vidbyte/harnesses/registry.py", "vidbyte/harnesses/client.py")


class HarnessDuplicateRegistrationError(HarnessRegistrationError):
    """Raised when a registry key is registered more than once."""

    description = "A client-local registry already owns the exact harness type/version key."
    expected_vs_actual = "Expected: one factory per exact key. Actual: a second factory attempted to replace it implicitly."
    fix_approaches = ("Remove the duplicate registration.", "Use a distinct implementation version for changed behavior.")


class HarnessSinkError(HarnessError):
    """Raised when a trajectory sink cannot durably write a redacted export record."""

    description = "A TrajectorySink could not atomically publish one redacted trajectory record."
    expected_vs_actual = "Expected: the sink can encode the record and write its destination. Actual: encoding or destination I/O failed."
    blast_radius = ("vidbyte/harnesses/sinks.py",)
    fix_approaches = ("Confirm the destination path is writable.", "Inspect the safe error type; collection is fail-open inside execute() and never fails the run.")


class HarnessExecutionError(HarnessError):
    """Raised after arbitrary implementation failure has been recorded as a run."""

    description = "The harness implementation failed after the SDK established its canonical run envelope."
    expected_vs_actual = "Expected: execute returns a value or awaitable result. Actual: implementation code raised and the run was finalized FAILED."
    blast_radius = ("vidbyte/harnesses/execution.py", "caller-provided harness implementation")

    def __init__(self, message: str, *, run: HarnessRun) -> None:
        # Attaches the finalized failed run so callers can inspect or query it directly.
        self.run = run
        super().__init__(message, details={"run_id": run.run_id, "spec_id": run.spec_id, "status": run.status.value})

    def to_context_packet(self) -> dict[str, Any]:
        # Extends the base packet with safe canonical run identity.
        packet = super().to_context_packet()
        packet["run"] = {"run_id": self.run.run_id, "spec_id": self.run.spec_id, "status": self.run.status.value}
        return packet


class HarnessTimeoutError(HarnessExecutionError):
    """Raised after a configured execution timeout is recorded."""

    description = "The implementation exceeded the caller's explicit execution deadline."
    expected_vs_actual = "Expected: implementation finishes within timeout_seconds. Actual: the deadline elapsed and the run was finalized TIMED_OUT."
    fix_approaches = ("Inspect run events to identify the slow stage.", "Increase the explicit timeout only when the longer budget is intentional.")


__all__ = [
    "HarnessConfigurationError",
    "HarnessCredentialConfigError",
    "HarnessDuplicateRegistrationError",
    "HarnessError",
    "HarnessExecutionError",
    "HarnessFileReferenceError",
    "HarnessRegistrationError",
    "HarnessSinkError",
    "HarnessTimeoutError",
    "HarnessVersionError",
]
