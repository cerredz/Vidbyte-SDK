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
    before a run exists and therefore expose only safe details. Any class-level
    tuple field (blast_radius, possible_causes, fix_approaches) that a subclass
    re-declares needs an explicit `: tuple[str, ...]` annotation at that
    re-declaration — mypy otherwise infers the field's type from the literal's
    exact length, so a base class assigning a 1-tuple and a subclass assigning
    a 3-tuple to the "same" field become incompatible types.

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

    description: str = "A harness execution-contract boundary rejected unsafe or inconsistent state."
    expected_vs_actual: str = "Expected: the documented harness contract remains valid. Actual: a boundary observed state that violates it."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses",)
    possible_causes: tuple[str, ...] = ("Invalid caller input", "Corrupt or conflicting persisted state")
    fix_approaches: tuple[str, ...] = ("Inspect the safe details and reproduce at the named boundary.", "Correct the caller input or backend record before retrying.")
    doc_links: tuple[str, ...] = (_DESIGN_URL,)
    test_files: tuple[str, ...] = _NO_TESTS

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
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/config.py", "vidbyte/harnesses/execution.py")


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
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/stores/file.py", "vidbyte/harnesses/stores/memory.py")
    fix_approaches: tuple[str, ...] = ("Confirm the destination path is writable.", "Inspect the safe error type; collection is fail-open inside execute() and never fails the run.")


class HarnessSinkSetupError(HarnessSinkError):
    """Raised when a cloud sink's destination cannot be resolved before any write is attempted."""

    description = "A cloud TrajectorySink's configured bucket/container could not be resolved: it does not exist, sits in a different region than configured, or the endpoint is unreachable at the address given."
    expected_vs_actual = "Expected: the configured bucket/container exists and is reachable at the configured region/endpoint. Actual: the provider reported the destination itself could not be resolved."
    blast_radius = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes = ("The bucket/container name is syntactically valid but does not exist.", "The bucket exists in a different region than the configured `region`.", "`endpoint_url`/`account_url` points at the wrong host or a host requiring different signing.")
    fix_approaches = (
        "Confirm the bucket/container exists in the account and region the credentials resolve to.",
        "For S3-compatible vendors (R2, MinIO, B2, Spaces), confirm `endpoint_url` and `region` match that vendor's documented values — R2 in particular requires region='auto'.",
        "Call sink.verify() explicitly before running a long harness to fail fast on this rather than discovering it only after execute() swallows the failure.",
    )


class HarnessSinkAuthenticationError(HarnessSinkError):
    """Raised when a cloud sink cannot establish who it is."""

    description = "A cloud TrajectorySink could not resolve any usable credentials: none were supplied and the provider's default/keyless credential chain came up empty, a supplied credential was invalid or expired, or cross-account role assumption failed."
    expected_vs_actual = "Expected: static credentials, a keyless default chain (AWS default chain / GCP Application Default Credentials / Azure DefaultAzureCredential), or a role-assumption grant resolves to a usable identity. Actual: the provider could not establish who the sink is at all, before ever reaching a permissions check."
    blast_radius = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes = (
        "No static credentials were supplied and no keyless credential source is available in this environment.",
        "A supplied static credential, session token, or SAS token is invalid or has expired.",
        "S3 cross-account `role_arn` assumption failed: the trust policy does not list the caller, or `external_id` does not match.",
    )
    fix_approaches = (
        "Supply valid static credentials, or run in an environment where the keyless default chain resolves (an attached IAM role, Application Default Credentials, or a managed identity).",
        "If using `role_arn`, confirm the target role's trust policy lists this caller's principal and, if set, that `external_id` matches exactly.",
        "This is distinct from HarnessSinkAuthorizationError: this error means identity could not be established at all, not that an established identity lacks permission.",
    )


class HarnessSinkAuthorizationError(HarnessSinkError):
    """Raised when a cloud sink is identified but not permitted to write."""

    description = "A cloud TrajectorySink established a valid identity, but the provider rejected the write as a policy/permission denial — including the case where a bucket requires server-side encryption and the sink's request did not include the matching encryption header, which surfaces as a permission denial rather than a distinct encryption error."
    expected_vs_actual = "Expected: the resolved identity has write permission on the configured bucket/container/prefix, including any required encryption grant. Actual: the provider accepted the identity but denied the specific write."
    blast_radius = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes = (
        "The bucket/container policy does not grant PutObject/upload on this prefix to this identity.",
        "The bucket requires customer-managed encryption (aws:kms SSE, GCS CMEK) but `sse`/`kms_key_id` (S3) or `kms_key_name` (GCS) was not set, or the identity lacks Encrypt/Decrypt on that key.",
        "An Azure SAS token has expired — Azure reports an expired SAS as a 403 authorization failure, not a distinct expiry code.",
    )
    fix_approaches = (
        "Confirm the bucket/container policy grants write on the exact prefix used, not just the bucket as a whole.",
        "If this bucket requires server-side encryption, confirm `sse`/`kms_key_id` (S3) or `kms_key_name` (GCS) is set and the identity has the matching key-usage grant (S3: the KMS key policy; GCS: roles/cloudkms.cryptoKeyEncrypterDecrypter) — a missing encryption header surfaces as a permission denial, not an encryption error.",
        "This is distinct from HarnessSinkAuthenticationError: this error means the identity is valid but not permitted, not that identity itself could not be established.",
    )


class HarnessSinkUnavailableError(HarnessSinkError):
    """Raised when a cloud sink's destination could not be reached after the vendor SDK's own retries were exhausted."""

    description = "A cloud TrajectorySink's network call failed after the vendor SDK's own retry/backoff policy was exhausted — a timeout, a dropped connection, throttling, or a 5xx response from the provider."
    expected_vs_actual = "Expected: the provider's endpoint is reachable and responds within the configured retry budget. Actual: every attempt failed for a transport- or availability-level reason, not a policy or identity reason."
    blast_radius = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes = (
        "A corporate firewall or VPC egress rule blocks the provider's endpoint entirely.",
        "The provider is throttling this identity/bucket (S3 SlowDown, GCS TooManyRequests, Azure 429).",
        "A transient provider-side outage returned a 5xx after every retry.",
    )
    fix_approaches = (
        "Confirm outbound network access to the provider's endpoint from wherever the harness runs.",
        "Raise `max_retries` on the sink's Config if throttling is expected and transient, rather than treating every occurrence as a hard failure.",
        "Do not add a second retry loop around this error; the vendor SDK's own retry/backoff already ran before this was raised.",
    )


class HarnessSinkPayloadError(HarnessSinkError):
    """Raised when a trajectory record cannot be encoded, or exceeds the sink's size guard, before any I/O is attempted."""

    description = "A TrajectoryRecord could not be turned into bytes safe to write, or the encoded payload exceeded the sink's size guard — caught locally, before any network or disk write was attempted."
    expected_vs_actual = "Expected: json.dumps(asdict(record), ...) succeeds and the encoded payload stays within MAX_TRAJECTORY_RECORD_BYTES. Actual: encoding raised, or the payload exceeded the guard."
    blast_radius = ("vidbyte/harnesses/stores/file.py", "vidbyte/harnesses/stores/_sink_support.py", "vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes = (
        "A value in the record is not JSON-serializable — this should not happen post-redaction, but HarnessRedactor cannot guarantee every possible object type.",
        "The record's encoded payload exceeds MAX_TRAJECTORY_RECORD_BYTES, most likely because of an unusually large captured tool output.",
    )
    fix_approaches = (
        "If the redactor let through a non-JSON-safe value, treat it as a redactor bug and file it there rather than widening this guard.",
        "If a genuinely large record is expected, this sink deliberately does not implement multipart upload; raise the guard only if you also confirm the destination provider's single-PUT size ceiling can hold it.",
    )


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
    "HarnessSinkAuthenticationError",
    "HarnessSinkAuthorizationError",
    "HarnessSinkError",
    "HarnessSinkPayloadError",
    "HarnessSinkSetupError",
    "HarnessSinkUnavailableError",
    "HarnessTimeoutError",
    "HarnessVersionError",
]
