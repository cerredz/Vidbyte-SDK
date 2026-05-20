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
