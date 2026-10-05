"""Context Protocol Header

PURPOSE: Exports the canonical typed SDK exception hierarchy through one stable import surface.
ROLE IN CODEBASE: Runtime boundaries import error types from this package instead of depending on the base module's layout.
ARCHITECTURE NOTE: This module re-exports errors; shared types live in base.py and domain errors live beside their owning boundary.
COMMON MODIFICATION PATTERNS: Re-export a new error here while keeping its behavior in base.py or a focused domain module.
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
    CodexAgentError,
    AgentSpeedError,
    AgentSpeedValidationError,
    AllModelsFailedError,
    AgentTransferError,
    AgentForkConfigurationError,
    AgentForkError,
    AgentRegistryError,
    AggregateExecutionError,
    ConfigurationError,
    FailureRaisedError,
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
from vidbyte.lib.errors.skills import SkillSourceError

__all__ = [
    "AgentExecutionError",
    "CodexAgentError",
    "AgentSpeedError",
    "AgentSpeedValidationError",
    "AllModelsFailedError",
    "AgentTransferError",
    "AgentForkConfigurationError",
    "AgentForkError",
    "AgentRegistryError",
    "AggregateExecutionError",
    "ConfigurationError",
    "FailureRaisedError",
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
    "SkillSourceError",
    "ToolExecutionError",
    "ToolRegistrationError",
    "ToolRegistryError",
    "TaskLedgerError",
    "TracerConfigurationError",
    "UnsupportedProviderError",
    "VidbyteSdkError",
]
