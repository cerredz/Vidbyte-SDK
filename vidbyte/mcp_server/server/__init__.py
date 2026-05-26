"""Context Protocol Header

Description:
    Re-exports McpStudioServer from the server package so the import path
    vidbyte.mcp_server.server.McpStudioServer remains stable after server.py
    was converted to a package.
Purpose:
    Preserves backward-compatible imports for all consumers.
Relations:
    Consumed by vidbyte.mcp_server.__init__ and vidbyte.mcp_server.__main__.
"""

from __future__ import annotations

from vidbyte.mcp_server.server.core import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    McpStudioServer,
)

__all__ = [
    "McpStudioServer",
    "JSONRPC_PARSE_ERROR",
    "JSONRPC_INVALID_REQUEST",
    "JSONRPC_METHOD_NOT_FOUND",
    "JSONRPC_INVALID_PARAMS",
    "JSONRPC_INTERNAL_ERROR",
]
