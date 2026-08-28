"""Context Protocol Header

Description:
    Defines the shared SDK exception hierarchy used by public Vidbyte SDK modules.
Purpose:
    Keeps error types lightweight, printable, and safe to expose from tool, MCP,
    registry, and security layers without owning business-domain failures.
Architecture:
    - VidbyteSdkError: Root SDK exception with optional safe detail metadata.
    - ToolRegistryError: Raised when registry state or lookups are invalid.
    - ToolExecutionError: Raised for tool execution pipeline failures.
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
    - McpAttachmentError: Composite error tracking failures from concurrent server startup.
    - ProviderRequestError: Raised when a provider request fails or returns an invalid response.
    - ProviderConfigurationError: Raised when a provider adapter is missing required configuration.
    - ProviderResponseError: Raised when a provider response cannot be normalized.
    - SourceError: Base exception for artifact-source loader failures.
    - SourceFetchError: Raised when fetching a remote artifact fails or returns a non-2xx response.
    - SourcePinMismatchError: Raised when fetched content does not match the pinned hash.
    - SourceParseError: Raised when an artifact cannot be parsed into a valid typed IR.
    - SourceSecurityError: Raised when a URL is disallowed or a response violates a guard.
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


class AgentKeyNotFoundError(VidbyteSdkError):
    """Raised when AgentKeys.decode() is given a digest that was never recorded or has been evicted."""


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


class ProviderSelectionError(VidbyteSdkError):
    """Raised when no SDK provider adapter matches a requested capability."""


class ProviderRequestError(VidbyteSdkError):
    """Raised when a provider request fails or returns an invalid response."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        response_excerpt: str | None = None,
    ) -> None:
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

    def __init__(self, message: str, *, provider: str, status_code: int | None = None, response_excerpt: str | None = None) -> None:
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


class PipelineExecutionError(VidbyteSdkError):
    """Raised when a pipeline cannot complete execution."""


class TracerConfigurationError(VidbyteSdkError):
    """Raised when a tracing provider cannot be configured (missing credentials or SDK)."""


class SessionUsageError(VidbyteSdkError):
    """Raised when durable-session usage rollup data cannot be interpreted."""


class SessionUsageValidationError(SessionUsageError):
    """Raised when persisted usage rollup inputs have an invalid shape."""


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
