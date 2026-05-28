"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Zep Cloud memory API.
Purpose:
    Lets agents add messages, retrieve context strings, search, and delete
    Zep sessions — all organized around the session-scoped memory model.
Architecture:
    - ZepAddMemoryTool: POST /api/v2/sessions/{session_id}/memory
    - ZepGetMemoryTool: GET /api/v2/sessions/{session_id}/memory
    - ZepSearchMemoryTool: POST /api/v2/sessions/{session_id}/memory/search
    - ZepDeleteSessionTool: DELETE /api/v2/sessions/{session_id}
Relations:
    Extends BaseMemoryTool from vidbyte.tools.builtins.memory.base.
    Zep uses "Authorization: Api-Key <key>" instead of Bearer.
"""

from __future__ import annotations

from vidbyte.tools.builtins.memory.base import BaseMemoryTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

_BASE_URL = "https://api.getzep.com"


class ZepAddMemoryTool(BaseMemoryTool):
    """Adds conversation messages to a Zep session; auto-creates the session if absent."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Zep Cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the zep_add_memory tool.
        return ToolSpec(
            name="zep_add_memory",
            description=(
                "Add conversation messages to a Zep session's memory. "
                "Zep auto-creates the session if it does not exist. "
                "Each message must have 'role' (ai/human/tool), 'role_type', and 'content'."
            ),
            parameters=(
                ToolParameter("session_id", "string", "The Zep session ID to add messages to."),
                ToolParameter("messages", "array", "List of message dicts with role, role_type, and content."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "zep"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validates messages list and POSTs to the session memory endpoint.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        session_id: str = str(call.arguments["session_id"])
        messages = call.arguments.get("messages")
        if not messages or not isinstance(messages, list) or len(messages) == 0:
            return ToolResult.error(self.name, "messages must be a non-empty list.", metadata={"provider": "zep"})

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/api/v2/sessions/{session_id}/memory",
                headers=self._auth_headers("Api-Key"),
                body={"messages": list(messages)},
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "zep"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "zep"})
        return ToolResult.success(
            self.name,
            self._success_output({"session_id": session_id, "messages_added": len(messages)}),
            metadata={"provider": "zep"},
        )


class ZepGetMemoryTool(BaseMemoryTool):
    """Retrieves the memory context string for a Zep session, ready for prompt injection."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Zep Cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the zep_get_memory tool.
        return ToolSpec(
            name="zep_get_memory",
            description=(
                "Retrieve the memory context string for a Zep session. "
                "Zep returns a pre-formatted context string of relevant facts "
                "derived from the session's history — ready for prompt injection."
            ),
            parameters=(
                ToolParameter("session_id", "string", "The Zep session ID to retrieve context for."),
                ToolParameter("lastn", "integer", "Number of recent messages to consider (optional).", required=False),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "zep"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # GETs session memory and extracts the context string from the response.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        session_id: str = str(call.arguments["session_id"])
        params: dict = {}
        lastn = call.arguments.get("lastn")
        if lastn is not None:
            params["lastn"] = int(lastn)

        try:
            status, data = await self._json_get(
                url=f"{self._base_url}/api/v2/sessions/{session_id}/memory",
                headers=self._auth_headers("Api-Key"),
                params=params or None,
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "zep"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "zep"})

        context = data.get("context", self._success_output(data))
        return ToolResult.success(self.name, str(context), metadata={"provider": "zep", "session_id": session_id})


class ZepSearchMemoryTool(BaseMemoryTool):
    """Searches a Zep session's memory graph using a text query."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Zep Cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the zep_search_memory tool.
        return ToolSpec(
            name="zep_search_memory",
            description=(
                "Search a Zep session's memory for passages matching the query text. "
                "Zep performs hybrid vector + graph search and returns ranked results."
            ),
            parameters=(
                ToolParameter("session_id", "string", "The Zep session ID to search within."),
                ToolParameter("text", "string", "The search query text."),
                ToolParameter("limit", "integer", "Maximum results to return (default 5).", required=False, default=5),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "zep"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # POSTs a search request to the session memory search endpoint.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        session_id: str = str(call.arguments["session_id"])
        text: str = str(call.arguments["text"])
        limit: int = int(call.arguments.get("limit") or 5)

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/api/v2/sessions/{session_id}/memory/search",
                headers=self._auth_headers("Api-Key"),
                body={"text": text, "limit": limit},
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "zep"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "zep"})

        results = data.get("results", data if isinstance(data, list) else [])
        return ToolResult.success(self.name, self._success_output(results), metadata={"provider": "zep", "count": len(results)})


class ZepDeleteSessionTool(BaseMemoryTool):
    """Deletes a Zep session and all associated memory permanently."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Zep Cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the zep_delete_session tool.
        return ToolSpec(
            name="zep_delete_session",
            description=(
                "Delete a Zep session and all of its accumulated memory. "
                "This is a permanent, irreversible operation."
            ),
            parameters=(
                ToolParameter("session_id", "string", "The Zep session ID to delete."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "zep"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Sends DELETE for the given session ID.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        session_id: str = str(call.arguments["session_id"])

        try:
            status, data = await self._json_delete(
                url=f"{self._base_url}/api/v2/sessions/{session_id}",
                headers=self._auth_headers("Api-Key"),
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "zep"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "zep"})
        return ToolResult.success(self.name, self._success_output({"deleted": True, "session_id": session_id}), metadata={"provider": "zep"})


__all__ = [
    "ZepAddMemoryTool",
    "ZepGetMemoryTool",
    "ZepSearchMemoryTool",
    "ZepDeleteSessionTool",
]
