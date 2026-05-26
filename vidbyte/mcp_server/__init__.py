"""Context Protocol Header

Description:
    Exports the McpStudioServer class and supporting types from the mcp_server package.
Purpose:
    Provides a clean public import surface for creating and running an MCP server
    that exposes Vidbyte SDK capabilities.
Architecture:
    - McpStudioServer: The primary server class.
    - Studio tool classes available for programmatic construction.
Relations:
    Imported by vidbyte.__init__ for root-level SDK exports.
"""

from __future__ import annotations

from vidbyte.mcp_server.server import McpStudioServer

__all__ = [
    "McpStudioServer",
]
