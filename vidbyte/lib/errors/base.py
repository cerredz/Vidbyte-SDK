"""Context Protocol Header

PURPOSE: Defines the canonical typed SDK exception hierarchy and safe structured failure details.
ROLE IN CODEBASE: Provider, tool, runner, registry, source, and agent boundaries translate failures into these stable caller-facing types.
ARCHITECTURE NOTE: Error classes remain dependency-light and carry safe fields without importing their higher-level boundary owners.
COMMON MODIFICATION PATTERNS: Add one type for a distinct remediation category, export it from errors.__init__, and preserve chained causes.
KNOWN EDGE CASES: Public details must exclude secrets and raw payloads; aggregate errors retain causes only for programmatic inspection.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md and field-guide/vidbyte-sdk/model-facing-tool-contracts.md.
TESTS: Existing error-path tests and the source/package stages in scripts/run_ci.py.

Description:
    Defines the shared SDK exception hierarchy used by public Vidbyte SDK modules.
Purpose:
    Keeps error types lightweight, printable, and safe to expose from tool, MCP,
    registry, and security layers without owning business-domain failures.
Architecture:
    - VidbyteSdkError: Root SDK exception with optional safe detail metadata.
    - ToolRegistryError: Raised when registry state or lookups are invalid.
    - ToolExecutionError: Raised for tool execution pipeline failures.
    - ReasoningTraceArgumentError: Raised when a reasoning trace argument violates its declared contract.
    - PermissionDeniedError: Raised when a policy refuses a tool call.
    - McpProtocolError: Raised when an MCP transport returns malformed data.
    - AgentExecutionError: Raised when an agent cannot generate a reply.
    - AllModelsFailedError: Raised when every model in a fallback chain has failed.
    - MultiAgentExecutionError: Base exception for team controller failures.
    - TaskLedgerError: Raised when a ledger invariant or transition is rejected.
    - AgentTransferError: Raised at developer-defined worker transfer boundaries.
    - AgentRegistryError: Raised when local agent discovery fails.
    - AgentForkError: Base exception for agent fork pipeline failures.
    - AgentForkConfigurationError: Raised when fork settings are invalid or out of range.
    - McpError: Base exception for all developer attachment and execution failures.
    - McpConnectionError: Raised when an MCP server subprocess fails to start.
    - McpInitializeError: Raised when an MCP connection handshake fails or times out.
    - McpToolDiscoveryError: Raised when remote tools/list discovery returns an invalid response.
    - McpToolExecutionError: Raised when a remote MCP tool execution returns an error result.
    - ReasoningTraceDefinitionError: Raised when a reasoning trace definition is invalid.
    - McpAttachmentError: Composite error tracking failures from concurrent server startup.
    - ProviderRequestError: Raised when a provider request fails or returns an invalid response.
    - ProviderConfigurationError: Raised when a provider adapter is missing required configuration.
    - ProviderResponseError: Raised when a provider response cannot be normalized.
    - SourceError: Base exception for artifact-source loader failures.
    - SourceFetchError: Raised when fetching a remote artifact fails or returns a non-2xx response.
    - SourcePinMismatchError: Raised when fetched content does not match the pinned hash.
    - SourceParseError: Raised when an artifact cannot be parsed into a valid typed IR.
    - SourceSecurityError: Raised when a URL is disallowed or a response violates a guard.
    - AgentSpeedError: Base exception for agent speed-tracking failures.
    - AgentSpeedValidationError: Raised when a speed-tracking dataclass has an invalid shape.
Relations:
    Related to vidbyte.tools.executor, vidbyte.tools.registry, and vidbyte.tools.mcp.client.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class VidbyteSdkError(Exception):
    """Base class for SDK exceptions with safe structured details."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        """Store a human-readable message and optional safe metadata."""
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})


class ToolRegistryError(VidbyteSdkError):
    """Signals duplicate tool registration or missing registry entries."""


class ToolExecutionError(VidbyteSdkError):
    """Signals failures in the generic tool execution pipeline."""


class ReasoningTraceArgumentError(ToolExecutionError):
    """Signals a model argument that violates a reasoning trace parameter contract."""

    DIAGNOSTIC_FIELDS = (
        "error_kind",
        "expected",
        "actual",
        "safe_runtime_details",
        "likely_causes",
        "repair_approaches",
        "related_docs",
        "relevant_tests",
    )

    def __init__(self, parameter_name: str, expected: str) -> None:
        # Exposes only SDK-authored contract data; the rejected model value is intentionally omitted.
        self.parameter_name = parameter_name
        self.error_kind = "reasoning_trace_argument"
        self.expected = expected
        self.actual = "invalid or missing model-provided value"
        self.safe_runtime_details = {"parameter_name": parameter_name}
        self.likely_causes = ("The model supplied a value outside the parameter contract.",)
        self.repair_approaches = ("Retry with a value matching the declared tool parameter.",)
        self.related_docs = ("docs/design/reasoning-deep-observability-tools.md",)
        self.relevant_tests = ("scripts/check_reasoning_trace_contracts.py",)
        super().__init__(
            f"Invalid reasoning trace parameter '{parameter_name}': expected {expected}.",
            details={
                "error_kind": self.error_kind,
                "expected": self.expected,
                "actual": self.actual,
                "safe_runtime_details": self.safe_runtime_details,
                "likely_causes": self.likely_causes,
                "repair_approaches": self.repair_approaches,
                "related_docs": self.related_docs,
                "relevant_tests": self.relevant_tests,
            },
        )


class PermissionDeniedError(VidbyteSdkError):
    """Signals that a tool call was rejected before execution."""


class McpProtocolError(VidbyteSdkError):
    """Signals malformed JSON-RPC/MCP messages or remote protocol errors."""


class AgentExecutionError(VidbyteSdkError):
    """Raised when an agent cannot generate a reply."""


class AllModelsFailedError(AgentExecutionError):
    """Raised when every model in an agent's fallback chain has failed."""

    def __init__(self, message: str, *, attempts: Sequence[Mapping[str, str]], errors: Sequence[BaseException]) -> None:
        # Records the ordered per-model attempt log and the matching errors, without any credential material.
        self.attempts = tuple(dict(attempt) for attempt in attempts)
        self.errors = tuple(errors)
        super().__init__(message, details={"attempts": list(self.attempts), "attempt_count": len(self.attempts)})


class OutputSchemaViolationError(AgentExecutionError):
    """Raised when an agent declared an output_schema but could not produce a valid instance."""

    def __init__(self, message: str, *, raw_output: str, validation_error: str | None = None, stop_reason: str | None = None) -> None:
        # Records what the model actually returned and why it failed, so the caller never has to re-parse.
        self.raw_output = raw_output
        self.validation_error = validation_error
        self.stop_reason = stop_reason
        super().__init__(message, details={"validation_error": validation_error, "stop_reason": stop_reason, "output_chars": len(raw_output)})


class MultiAgentExecutionError(AgentExecutionError):
    """Raised when a multi-agent controller cannot safely continue or finalize."""


class TaskLedgerError(MultiAgentExecutionError):
    """Raised when a TaskLedger plan or state transition violates an invariant."""


class AgentTransferError(MultiAgentExecutionError):
    """Raised when a worker request, report, validator, or lifecycle seam fails."""


class AgentRegistryError(VidbyteSdkError):
    """Raised when local agent discovery fails."""


class AggregateExecutionError(AgentExecutionError):
    """Raised when an aggregate (mixture-of-agents) run cannot produce a synthesis."""


class AgentForkError(VidbyteSdkError):
    """Base class for agent fork failures raised by the fork pipeline."""


class AgentForkConfigurationError(AgentForkError):
    """Raised when fork settings are internally inconsistent or out of range."""


class McpError(VidbyteSdkError):
    """Base class for all MCP errors."""


class McpConnectionError(McpError):
    """Raised when an MCP subprocess fails to start."""


class McpInitializeError(McpError):
    """Raised when an MCP handshake fails or times out."""


class McpToolDiscoveryError(McpError):
    """Raised when remote MCP tools/list returns an unexpected response."""


class McpToolExecutionError(McpError):
    """Raised when a remote MCP tool execution returns an error result."""


class McpAttachmentError(McpError):
    """Tracks composite attachment errors in batch connections."""

    def __init__(self, message: str, *, causes: list[Exception], details: Mapping[str, Any] | None = None) -> None:
        """Store the message, list of cause exceptions, and optional details."""
        super().__init__(message, details=details)
        self.causes = causes


class ConfigurationError(VidbyteSdkError):
    """Raised when runner or provider configuration is invalid."""


class UnsupportedProviderError(VidbyteSdkError):
    """Raised when a provider does not support a requested capability."""


class HarnessSinkError(VidbyteSdkError):
    """Base error for trajectory sink failures with a complete safe diagnostic packet."""

    DIAGNOSTIC_FIELDS = (
        "error_kind",
        "expected",
        "actual",
        "safe_runtime_details",
        "likely_causes",
        "repair_approaches",
        "related_docs",
        "relevant_tests",
    )
    description: str = "A trajectory sink could not publish one redacted trajectory record."
    expected_vs_actual: str = "Expected: the record is encoded and published to the configured destination. Actual: the sink rejected or could not complete that operation."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/stores",)
    possible_causes: tuple[str, ...] = ("The destination or provider rejected the request.", "The record or sink configuration violated a provider contract.")
    fix_approaches: tuple[str, ...] = ("Inspect the safe details and the provider-specific configuration.", "Retry only when the error packet identifies a transient provider failure.")
    doc_links: tuple[str, ...] = ("https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/cloud-trajectory-sinks.md",)
    test_files: tuple[str, ...] = ("tests/test_cloud_trajectory_sinks.py",)

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        self.error_kind = "harness_sink"
        self.expected = self.expected_vs_actual
        self.actual = message
        self.safe_runtime_details = dict(details or {})
        self.likely_causes = tuple(self.possible_causes)
        self.repair_approaches = tuple(self.fix_approaches)
        self.related_docs = tuple(self.doc_links)
        self.relevant_tests = tuple(self.test_files)
        super().__init__(
            message,
            details=details,
        )

    def to_context_packet(self) -> dict[str, Any]:
        """Return all caller-actionable fields without raw exception or credential material."""
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "details": dict(self.details),
            "error_kind": self.error_kind,
            "expected": self.expected,
            "actual": self.actual,
            "safe_runtime_details": dict(self.safe_runtime_details),
            "likely_causes": tuple(self.likely_causes),
            "repair_approaches": tuple(self.repair_approaches),
            "related_docs": tuple(self.related_docs),
            "relevant_tests": tuple(self.relevant_tests),
            "description": self.description,
            "expected_vs_actual": self.expected_vs_actual,
            "blast_radius": tuple(self.blast_radius),
            "possible_causes": tuple(self.possible_causes),
            "fix_approaches": tuple(self.fix_approaches),
            "doc_links": tuple(self.doc_links),
            "test_files": tuple(self.test_files),
        }


class HarnessSinkSetupError(HarnessSinkError):
    """Raised when a bucket or container cannot be resolved or reached."""

    description = "The configured cloud destination could not be resolved before the object write."
    expected_vs_actual = "Expected: the bucket/container exists and is reachable at the configured account, region, and endpoint. Actual: the provider could not resolve that destination."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes: tuple[str, ...] = ("The bucket/container does not exist.", "The configured region, endpoint, or account is wrong.", "The identity can authenticate but cannot discover the destination.")
    fix_approaches: tuple[str, ...] = ("Verify the destination exists in the account and region used by the credentials.", "For S3-compatible services, confirm endpoint_url and region match the vendor.", "Call sink.verify() before a long harness run.")


class HarnessSinkAuthenticationError(HarnessSinkError):
    """Raised when a provider identity cannot be established."""

    description = "The sink could not establish a usable provider identity."
    expected_vs_actual = "Expected: static credentials, a default credential chain, managed identity, or an assumed role resolves to an identity. Actual: authentication failed before a permission decision."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes: tuple[str, ...] = ("No default or explicit credential source is available.", "A static key, token, SAS, or service-account file is invalid or expired.", "S3 role assumption failed because the trust policy or external ID is wrong.")
    fix_approaches: tuple[str, ...] = ("Supply a valid credential or enable the provider's default identity chain.", "Check role trust and external_id for cross-account S3.", "Distinguish this from authorization: here the identity itself was not established.")


class HarnessSinkAuthorizationError(HarnessSinkError):
    """Raised when an established identity is denied a sink operation."""

    description = "The provider recognized the identity but rejected the destination or object operation by policy."
    expected_vs_actual = "Expected: the identity can write this object, including its encryption, tag, ACL, retention, and condition headers. Actual: the provider denied the requested operation."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes: tuple[str, ...] = ("The identity lacks write permission on the bucket/container or prefix.", "A required KMS/CMEK, customer-key, ACL, tag, or retention permission is missing.", "A precondition or object policy rejected the request.")
    fix_approaches: tuple[str, ...] = ("Grant the exact object-write permission for the configured prefix.", "Grant the required KMS/CMEK key usage or object-governance permission.", "If this is a condition failure, refresh the expected ETag/generation before retrying.")


class HarnessSinkUnavailableError(HarnessSinkError):
    """Raised after provider retry/backoff is exhausted for a transient failure."""

    description = "The provider endpoint remained unavailable after its configured retry policy was exhausted."
    expected_vs_actual = "Expected: the provider responds within the retry budget. Actual: transport, throttling, or server failures persisted across the provider's retries."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes: tuple[str, ...] = ("Network egress or endpoint connectivity is blocked.", "The provider is throttling the identity or destination.", "A provider-side 5xx outage persisted through retries.")
    fix_approaches: tuple[str, ...] = ("Confirm network access from the harness runtime.", "Adjust max_retries only when the failure is expected to be transient.", "Do not add a second retry loop around this error.")


class HarnessSinkPayloadError(HarnessSinkError):
    """Raised when a record cannot be encoded or exceeds the single-PUT size guard."""

    description = "The redacted trajectory record could not be encoded safely or exceeded the configured single-upload size guard."
    expected_vs_actual = "Expected: JSON encoding succeeds and the payload is at most MAX_TRAJECTORY_RECORD_BYTES. Actual: encoding failed or the payload exceeded that bound before provider I/O."
    blast_radius: tuple[str, ...] = ("vidbyte/harnesses/stores/_sink_support.py", "vidbyte/harnesses/stores/file.py", "vidbyte/harnesses/stores/s3.py", "vidbyte/harnesses/stores/gcs.py", "vidbyte/harnesses/stores/azure_blob.py")
    possible_causes: tuple[str, ...] = ("A redacted value is not JSON serializable.", "A captured tool output made the record larger than the single-PUT guard.", "Compression was requested but the compressed representation still exceeded the guard.")
    fix_approaches: tuple[str, ...] = ("Fix the redaction/serialization boundary for non-JSON values.", "Trim the unusually large captured output or raise the guard only after confirming every provider's single-PUT ceiling.", "Multipart upload is intentionally not implemented for this KB-to-low-MB trajectory shape.")


class ProviderSelectionError(VidbyteSdkError):
    """Raised when no SDK provider adapter matches a requested capability."""


class ProviderRequestError(VidbyteSdkError):
    """Raised when a provider request fails or returns an invalid response."""

    def __init__(self, message: str, *, provider: str, status_code: int | None = None, response_excerpt: str | None = None) -> None:
        details: dict[str, Any] = {"provider": provider}
        if status_code is not None:
            details["status_code"] = status_code
        if response_excerpt:
            details["response_excerpt"] = response_excerpt[:500]
        super().__init__(message, details=details)
        self.provider = provider
        self.status_code = status_code
        self.response_excerpt = response_excerpt


class ProviderConfigurationError(VidbyteSdkError):
    """Raised when a provider adapter is missing required configuration."""

    def __init__(self, message: str, *, provider: str) -> None:
        # Initializes the error with a message and the associated provider.
        super().__init__(message, details={"provider": provider})
        self.provider = provider


class ProviderResponseError(VidbyteSdkError):
    """Raised when a provider response cannot be normalized."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        response_excerpt: str | None = None,
    ) -> None:
        # Initializes the error with response failure context, including status code and response body excerpt.
        details: dict[str, Any] = {"provider": provider}
        if status_code is not None:
            details["status_code"] = status_code
        if response_excerpt:
            details["response_excerpt"] = response_excerpt[:500]
        super().__init__(message, details=details)
        self.provider = provider
        self.status_code = status_code
        self.response_excerpt = response_excerpt


class ToolRegistrationError(ToolRegistryError):
    """Raised when a tool cannot be registered due to validation or conflict."""


class ReasoningTraceDefinitionError(ToolRegistrationError):
    """Signals an invalid immutable reasoning trace definition."""

    DIAGNOSTIC_FIELDS = (
        "error_kind",
        "expected",
        "actual",
        "safe_runtime_details",
        "likely_causes",
        "repair_approaches",
        "related_docs",
        "relevant_tests",
    )

    def __init__(self, reason: str, *, skill_name: str = "") -> None:
        # Keeps source-authored definition identity available without including model input.
        self.reason = reason
        self.skill_name = skill_name
        self.error_kind = "reasoning_trace_definition"
        self.expected = "a complete definition with unique parameters"
        self.actual = reason
        self.safe_runtime_details = {"skill_name": skill_name}
        self.likely_causes = ("A built-in trace definition violates its construction invariant.",)
        self.repair_approaches = ("Correct the named trace definition and rerun its contract check.",)
        self.related_docs = ("docs/design/reasoning-deep-observability-tools.md",)
        self.relevant_tests = ("scripts/check_reasoning_trace_contracts.py",)
        label = f" for '{skill_name}'" if skill_name else ""
        super().__init__(
            f"Invalid reasoning trace definition{label}: {reason}.",
            details={
                "error_kind": self.error_kind,
                "expected": self.expected,
                "actual": self.actual,
                "safe_runtime_details": self.safe_runtime_details,
                "likely_causes": self.likely_causes,
                "repair_approaches": self.repair_approaches,
                "related_docs": self.related_docs,
                "relevant_tests": self.relevant_tests,
            },
        )


class PipelineExecutionError(VidbyteSdkError):
    """Raised when a pipeline cannot complete execution."""


class TracerConfigurationError(VidbyteSdkError):
    """Raised when a tracing provider cannot be configured (missing credentials or SDK)."""


class SessionUsageError(VidbyteSdkError):
    """Raised when durable-session usage rollup data cannot be interpreted."""


class SessionUsageValidationError(SessionUsageError):
    """Raised when persisted usage rollup inputs have an invalid shape."""


class AgentSpeedError(VidbyteSdkError):
    """Base class for agent speed-tracking failures."""

    DIAGNOSTIC_FIELDS = (
        "error_kind",
        "expected",
        "actual",
        "safe_runtime_details",
        "likely_causes",
        "repair_approaches",
        "related_docs",
        "relevant_tests",
    )

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        """Populate the shared speed-tracking diagnostic packet from message/details alone."""
        super().__init__(message, details=details)
        self.error_kind = "agent_speed_tracking"
        self.expected = "AgentSpeedTracker recording/rollup completing without an internal contract violation."
        self.actual = message
        self.safe_runtime_details = dict(self.details)
        self.likely_causes = ("An internal AgentSpeedTracker invariant was violated; see subclasses for specifics.",)
        self.repair_approaches = ("Inspect safe_runtime_details, then fix the AgentSpeedTracker call site that produced it.",)
        self.related_docs = ("https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md",)
        self.relevant_tests = ("tests/test_agent_speed.py",)


class AgentSpeedValidationError(AgentSpeedError):
    """Raised when a speed-tracking dataclass receives an invalid shape."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        """Populate the diagnostic packet with the specific field/value that failed validation."""
        super().__init__(message, details=details)
        self.error_kind = "agent_speed_validation"
        self.expected = (
            "A speed-tracking dataclass field within its documented range: non-negative timestamps, "
            "first_token_at no earlier than dispatched_at, non-empty tool names, and ordered percentiles."
        )
        self.actual = message
        self.likely_causes = (
            "A caller assembled a speed dataclass from a raw timestamp/count computed incorrectly, e.g. "
            "first_token_at captured before dispatched_at, or a negative duration from a non-monotonic "
            "clock override in a test.",
        )
        self.repair_approaches = (
            "Inspect safe_runtime_details for the offending field and value, then fix the call site in "
            "vidbyte/agents/runtime.py or vidbyte/agents/base.py that assembled the dataclass.",
        )


class SourceError(VidbyteSdkError):
    """Base class for all artifact-source loader failures."""


class SourceFetchError(SourceError):
    """Raised when fetching a remote artifact fails or returns a non-2xx response."""


class SourcePinMismatchError(SourceError):
    """Raised when fetched content hash does not match the pinned expected hash."""


class SourceParseError(SourceError):
    """Raised when an artifact cannot be parsed into a valid typed IR (fail closed)."""


class SourceSecurityError(SourceError):
    """Raised when a URL is disallowed or a response violates a size/scheme guard."""
