"""Context Protocol Header

Description:
    Handles the MCP initialize handshake (method: "initialize").
Purpose:
    Registers the server as initialized and returns protocol version,
    capabilities, and server identity to the connecting MCP client.
Architecture:
    - InitializeHandler: Sets initialized flag via callback, builds capability response.
Relations:
    Registered in McpStudioServer._handler_map inside core.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler


class InitializeHandler(_BaseHandler):
    """Handles the MCP initialize handshake."""

    def __init__(self, name: str, version: str, on_initialized: Callable[[], None]) -> None:
        """Stores server identity and the callback that flips the initialized flag."""
        self._name = name
        self._version = version
        self._on_initialized = on_initialized

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Marks the server as initialized and returns capabilities to the client."""
        self._on_initialized()
        return McpSchema.mcp_result_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "prompts": {}},
                "serverInfo": {"name": self._name, "version": self._version},
            },
        )
