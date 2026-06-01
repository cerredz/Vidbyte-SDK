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
    - AgentRegistryError: Raised when local agent discovery fails.
    - McpError: Base exception for all developer attachment and execution failures.
    - McpConnectionError: Raised when an MCP server subprocess fails to start.
    - McpInitializeError: Raised when an MCP connection handshake fails or times out.
    - McpToolDiscoveryError: Raised when remote tools/list discovery returns an invalid response.
    - McpToolExecutionError: Raised when a remote MCP tool execution returns an error result.
    - McpAttachmentError: Composite error tracking failures from concurrent server startup.
    - ProviderRequestError: Raised when a provider request fails or returns an invalid response.
    - ProviderConfigurationError: Raised when a provider adapter is missing required configuration.
    - ProviderResponseError: Raised when a provider response cannot be normalized.
Relations:
    Related to vidbyte.tools.executor, vidbyte.tools.registry, and vidbyte.tools.mcp.client.
"""

from __future__ import annotations

from collections.abc import Mapping
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


class AgentRegistryError(VidbyteSdkError):
    """Raised when local agent discovery fails."""


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
