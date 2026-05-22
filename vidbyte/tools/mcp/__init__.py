"""Context Protocol Header

Description:
    Exports MCP bridge client, transport, configuration, and state handles.
Purpose:
    Provides a stable public surface for connecting external MCP tools and configuring
    automatic lifecycle attachments in the Vidbyte SDK.
Architecture:
    - McpClient: JSON-RPC operations.
    - McpStdioTransport: Subprocess stdio transport.
    - McpBridgedTool and McpToolBridge: Native wrappers for remote tools.
    - McpServerConfig: Immutable server configuration.
    - McpServerHandle: Live process connection wrapper.
    - McpToolPermission: Remote execution permissions.
Relations:
    Related to vidbyte.tools.registry, vidbyte.tools.executor, and agent mixins.
"""

from __future__ import annotations

from vidbyte.tools.mcp.bridge import McpBridgedTool, McpToolBridge
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.transport import McpStdioTransport, McpTransport
from vidbyte.tools.mcp.types import (
    McpServerConfig,
    McpServerHandle,
    McpToolDefinition,
    McpToolPermission,
)

__all__ = [
    "McpBridgedTool",
    "McpClient",
    "McpServerConfig",
    "McpServerHandle",
    "McpStdioTransport",
    "McpToolBridge",
    "McpToolDefinition",
    "McpToolPermission",
    "McpTransport",
]
