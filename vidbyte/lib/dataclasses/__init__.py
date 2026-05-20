"""Context Protocol Header

Description:
    Exports SDK dataclass contracts from the central Vidbyte lib namespace.
Purpose:
    Keeps reusable immutable data contracts in one package while feature
    packages provide compatibility import shims.
Architecture:
    - Tool contracts from tools.
    - Context, MCP, security, and sandbox contracts.
Relations:
    Related to vidbyte.tools and built-in tool packages.
"""

from __future__ import annotations

from vidbyte.lib.dataclasses.context import ContextMessage, ContextState, ProgressLog
from vidbyte.lib.dataclasses.mcp import McpToolDefinition
from vidbyte.lib.dataclasses.sandbox import SandboxRequest, SandboxResult, SandboxTransport
from vidbyte.lib.dataclasses.security import PermissionDecision, PermissionPolicy
from vidbyte.lib.dataclasses.tools import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
    ToolStatus,
)

__all__ = [
    "ContextMessage",
    "ContextState",
    "McpToolDefinition",
    "PermissionDecision",
    "PermissionPolicy",
    "ProgressLog",
    "SandboxRequest",
    "SandboxResult",
    "SandboxTransport",
    "ToolCall",
    "ToolParameter",
    "ToolPermission",
    "ToolResult",
    "ToolSpec",
    "ToolStatus",
]
