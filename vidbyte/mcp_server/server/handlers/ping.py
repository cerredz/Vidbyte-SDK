"""FILE: vidbyte/mcp_server/server/handlers/ping.py

PURPOSE:
    Handles the MCP base-protocol ping request (method: "ping") so MCP hosts can
    check that the Vidbyte studio server is still alive.
ROLE IN CODEBASE:
    One JSON-RPC handler registered in McpStudioServer._handler_map inside
    vidbyte/mcp_server/server/core.py, next to initialize/tools/prompts handlers.
ARCHITECTURE NOTE:
    PingHandler returns an empty JSON-RPC result through McpSchema, matching the
    MCP specification: the receiver of a ping MUST reply promptly with {}.
FUNCTION INVENTORY:
    PingHandler.handle(request_id, params) -> dict: empty result response.
COMMON MODIFICATION PATTERNS:
    Keep the reply empty; liveness metadata belongs in initialize, not ping.
WHAT NOT TO DO IN THIS FILE:
    Do not perform I/O or call agents here; ping must answer immediately.
KNOWN EDGE CASES:
    Ping may arrive before initialize; it is answered regardless of state.
RELATED DOCS:
    docs/design/mcp-stdin-windows-pipe.md
TESTS:
    tests/test_mcp_studio_server.py
"""

from __future__ import annotations

from typing import Any

from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler


class PingHandler(_BaseHandler):
    """Handles the MCP ping request."""

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Returns an empty result, as the MCP specification requires."""
        # @intent ping-is-a-liveness-check
        # MCP hosts send ping as a keep-alive; anything but an immediate empty result
        # (such as the old "Method not found") can make a host treat the server as dead.
        return McpSchema.mcp_result_response(request_id, {})
