"""Context Protocol Header

Description:
    Handles the MCP prompts/list request (method: "prompts/list").
Purpose:
    Returns a list of available prompt names from the registry's prompt content map
    so clients can discover which prompts are available for retrieval.
Architecture:
    - PromptsListHandler: Reads prompt_content keys from StudioToolRegistry.
Relations:
    Registered in McpStudioServer._handler_map inside core.py.
"""

from __future__ import annotations

from typing import Any

from vidbyte.mcp_server.handlers import StudioToolRegistry
from vidbyte.mcp_server.schema import McpSchema
from vidbyte.mcp_server.server.handlers import _BaseHandler


class PromptsListHandler(_BaseHandler):
    """Handles the MCP prompts/list request."""

    def __init__(self, registry: StudioToolRegistry) -> None:
        """Stores the registry whose prompt_content map is enumerated."""
        self._registry = registry

    async def handle(self, request_id: int | str | None, params: Any) -> dict[str, Any]:
        """Returns all available prompt names and brief descriptions."""
        prompts_list = [
            {"name": key, "description": f"Prompt template: {key[:60]}"}
            for key in self._registry._prompt_content
        ]
        return McpSchema.mcp_result_response(request_id, {"prompts": prompts_list})
