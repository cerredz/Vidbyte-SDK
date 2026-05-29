"""Context Protocol Header

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
    AgentRegistryError,
    ConfigurationError,
    McpAttachmentError,
    McpConnectionError,
    McpError,
    McpInitializeError,
    McpProtocolError,
    McpToolDiscoveryError,
    McpToolExecutionError,
    PermissionDeniedError,
    PipelineExecutionError,
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderResponseError,
    ProviderSelectionError,

    ToolExecutionError,
    ToolRegistrationError,
    ToolRegistryError,
    TracerConfigurationError,
    UnsupportedProviderError,
    VidbyteSdkError,
)

__all__ = [
    "AgentExecutionError",
    "AgentRegistryError",
    "ConfigurationError",
    "McpAttachmentError",
    "McpConnectionError",
    "McpError",
    "McpInitializeError",
    "McpProtocolError",
    "McpToolDiscoveryError",
    "McpToolExecutionError",
    "PermissionDeniedError",
    "PipelineExecutionError",
    "ProviderConfigurationError",
    "ProviderRequestError",
    "ProviderResponseError",
    "ProviderSelectionError",
    "StrategyExecutionError",
    "ToolExecutionError",
    "ToolRegistrationError",
    "ToolRegistryError",
    "TracerConfigurationError",
    "UnsupportedProviderError",
    "VidbyteSdkError",
]
