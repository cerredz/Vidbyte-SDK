"""Context Protocol Header

Description:
    Handles the MCP prompts/get request (method: "prompts/get").
Purpose:
    Returns the text content of a named prompt template so clients can
    inject it into their model context.
Architecture:
    - PromptsGetHandler: Looks up prompt content by name from StudioToolRegistry.
Relations:
    Registered in McpStudioServer._handler_map inside core.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.mcp_server.handlers import StudioToolRegistry
from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler

JSONRPC_INVALID_PARAMS = -32602


class PromptsGetHandler(_BaseHandler):
    """Handles the MCP prompts/get request."""

    def __init__(self, registry: StudioToolRegistry) -> None:
        """Stores the registry whose prompt_content map is queried by name."""
        self._registry = registry

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Returns the content of the requested prompt, or empty text if not found."""
        if not isinstance(params, Mapping):
            return McpSchema.mcp_error_response(request_id, JSONRPC_INVALID_PARAMS, "Invalid params")
        name = str(params.get("name") or "")
        content = self._registry._prompt_content.get(name, "")
        return McpSchema.mcp_result_response(
            request_id,
            {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": content}}
                ]
            },
        )
