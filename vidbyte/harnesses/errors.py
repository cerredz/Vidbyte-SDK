"""Typed harness errors and compatibility exports for the shared SDK errors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.harnesses import HarnessRun
from vidbyte.lib.errors import (
    HarnessSinkAuthenticationError,
    HarnessSinkAuthorizationError,
    HarnessSinkError,
    HarnessSinkPayloadError,
    HarnessSinkSetupError,
    HarnessSinkUnavailableError,
    VidbyteSdkError,
)

_DESIGN_URL = "https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/harness-execution-contract.md"
_NO_TESTS = ("Approved no-tests workflow: run the repository suite and harness smoke verification.",)


class HarnessError(VidbyteSdkError):
    """Base class for harness failures with durable diagnostic context."""

    description: str = "A harness execution-contract boundary rejected unsafe or inconsistent state."
    expected_vs_actual: str = "Expected: the documented harness contract remains valid. Actual: a boundary observed state that violates it."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses",)
    possible_causes: tuple[str, ...] = ("Invalid caller input", "Corrupt or conflicting persisted state")
    fix_approaches: tuple[str, ...] = ("Inspect the safe details and reproduce at the named boundary.", "Correct the caller input or backend record before retrying.")
    doc_links: tuple[str, ...] = (_DESIGN_URL,)
    test_files: tuple[str, ...] = _NO_TESTS

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, details=details)

    def to_context_packet(self) -> dict[str, Any]:
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
    expected_vs_actual = "Expected: schema_version, harness, and agents follow the public envelope. Actual: a required field, type, or value is invalid."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/config.py", "vidbyte/harnesses/execution.py")


class HarnessCredentialConfigError(HarnessConfigurationError):
    """Raised when a persistable behavior config contains a credential-like key."""

    description = "A credential-like key was found in configuration that is fingerprinted and persisted."
    expected_vs_actual = "Expected: credentials arrive through environment or provider construction. Actual: configuration contains a key that could persist a secret."
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


class HarnessExecutionError(HarnessError):
    """Raised after arbitrary implementation failure has been recorded as a run."""

    description = "The harness implementation failed after the SDK established its canonical run envelope."
    expected_vs_actual = "Expected: execute returns a value or awaitable result. Actual: implementation code raised and the run was finalized FAILED."
    blast_radius = ("vidbyte/harnesses/execution.py", "caller-provided harness implementation")

    def __init__(self, message: str, *, run: HarnessRun) -> None:
        self.run = run
        super().__init__(message, details={"run_id": run.run_id, "spec_id": run.spec_id, "status": run.status.value})

    def to_context_packet(self) -> dict[str, Any]:
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
    "HarnessSinkAuthenticationError",
    "HarnessSinkAuthorizationError",
    "HarnessSinkError",
    "HarnessSinkPayloadError",
    "HarnessSinkSetupError",
    "HarnessSinkUnavailableError",
    "HarnessTimeoutError",
    "HarnessVersionError",
]
