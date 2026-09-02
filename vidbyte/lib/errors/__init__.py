"""Context Protocol Header

PURPOSE: Exports the canonical typed SDK exception hierarchy through one stable import surface.
ROLE IN CODEBASE: Runtime boundaries import error types from this package instead of depending on the base module's layout.
ARCHITECTURE NOTE: This module re-exports only; error behavior and safe fields remain owned by vidbyte.lib.errors.base.
COMMON MODIFICATION PATTERNS: Add a new base error to both the import tuple and __all__ in alphabetical family order.
KNOWN EDGE CASES: Missing re-exports break public imports even when the underlying class exists.
RELATED DOCS: field-guide/vidbyte-sdk/runtime-boundaries.md.
TESTS: Existing error-path tests and the source/package stages in scripts/run_ci.py.

Description:
    Exports the shared SDK exception hierarchy.
Purpose:
    Provides a stable public import surface for errors without embedding module
    internals into calling code.
Architecture:
    - Re-exports typed errors from vidbyte.lib.errors.base.
Relations:
    Related to vidbyte.lib.errors.base and tool modules that normalize failures.
"""

from __future__ import annotations

from vidbyte.lib.errors.base import (
    AgentExecutionError,
    AgentSpeedError,
    AgentSpeedValidationError,
    AllModelsFailedError,
    AgentTransferError,
    AgentForkConfigurationError,
    AgentForkError,
    AgentRegistryError,
    AggregateExecutionError,
    ConfigurationError,
    HarnessSinkAuthenticationError,
    HarnessSinkAuthorizationError,
    HarnessSinkError,
    HarnessSinkPayloadError,
    HarnessSinkSetupError,
    HarnessSinkUnavailableError,
    McpAttachmentError,
    McpConnectionError,
    McpError,
    McpInitializeError,
    McpProtocolError,
    McpToolDiscoveryError,
    McpToolExecutionError,
    MultiAgentExecutionError,
    OutputSchemaViolationError,
    PermissionDeniedError,
    PipelineExecutionError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderSelectionError,
    ReasoningTraceArgumentError,
    ReasoningTraceDefinitionError,
    SessionUsageError,
    SessionUsageValidationError,
    SourceError,
    SourceFetchError,
    SourceParseError,
    SourcePinMismatchError,
    SourceSecurityError,
    ToolExecutionError,
    ToolRegistrationError,
    ToolRegistryError,
    TaskLedgerError,
    TracerConfigurationError,
    UnsupportedProviderError,
    VidbyteSdkError,
)

__all__ = [
    "AgentExecutionError",
    "AgentSpeedError",
    "AgentSpeedValidationError",
    "AllModelsFailedError",
    "AgentTransferError",
    "AgentForkConfigurationError",
    "AgentForkError",
    "AgentRegistryError",
    "AggregateExecutionError",
    "ConfigurationError",
    "HarnessSinkAuthenticationError",
    "HarnessSinkAuthorizationError",
    "HarnessSinkError",
    "HarnessSinkPayloadError",
    "HarnessSinkSetupError",
    "HarnessSinkUnavailableError",
    "McpAttachmentError",
    "McpConnectionError",
    "McpError",
    "McpInitializeError",
    "McpProtocolError",
    "McpToolDiscoveryError",
    "McpToolExecutionError",
    "MultiAgentExecutionError",
    "OutputSchemaViolationError",
    "PermissionDeniedError",
    "PipelineExecutionError",
    "ProviderConfigurationError",
    "ProviderRequestError",
    "ProviderResponseError",
    "ProviderSelectionError",
    "ReasoningTraceArgumentError",
    "ReasoningTraceDefinitionError",
    "SessionUsageError",
    "SessionUsageValidationError",
    "SourceError",
    "SourceFetchError",
    "SourceParseError",
    "SourcePinMismatchError",
    "SourceSecurityError",
    "ToolExecutionError",
    "ToolRegistrationError",
    "ToolRegistryError",
    "TaskLedgerError",
    "TracerConfigurationError",
    "UnsupportedProviderError",
    "VidbyteSdkError",
]
