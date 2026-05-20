"""Context Protocol Header

Description:
    Exports MCP bridge client, transport, and wrapper utilities.
Purpose:
    Provides a stable public surface for connecting external MCP tools to the
    Vidbyte SDK registry.
Architecture:
    - McpClient: JSON-RPC operations.
    - McpStdioTransport: Subprocess stdio transport.
    - McpBridgedTool: Native wrapper for remote tools.
Relations:
    Related to vidbyte.tools.registry and vidbyte.tools.executor.
"""

from __future__ import annotations

from vidbyte.tools.mcp.bridge import McpBridgedTool
from vidbyte.tools.mcp.client import McpClient
from vidbyte.tools.mcp.transport import McpStdioTransport, McpTransport
from vidbyte.tools.mcp.types import McpToolDefinition

__all__ = [
    "McpBridgedTool",
    "McpClient",
    "McpStdioTransport",
    "McpToolDefinition",
    "McpTransport",
]
