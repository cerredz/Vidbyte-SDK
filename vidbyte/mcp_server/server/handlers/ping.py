"""Context Protocol Header

Description:
    Handles the MCP ping request (method: "ping").
Purpose:
    The MCP base protocol requires the receiver of a ping to reply promptly with an
    empty result, so clients can check that the server is still alive.
Architecture:
    - PingHandler: Returns an empty JSON-RPC result.
Relations:
    Registered in McpStudioServer._handler_map inside core.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler


class PingHandler(_BaseHandler):
    """Handles the MCP ping request."""

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Returns an empty result, as the MCP specification requires."""
        return McpSchema.mcp_result_response(request_id, {})
