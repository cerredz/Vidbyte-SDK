"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Mem0 managed memory API.
Purpose:
    Lets agents add, search, retrieve, and delete memories via Mem0 with
    user/agent/run scoping — no provider SDK dependency required.
Architecture:
    - Mem0AddMemoryTool: POST /v3/memories/add/
    - Mem0SearchMemoryTool: POST /v1/memories/search/
    - Mem0GetMemoriesTool: GET /v1/memories/
    - Mem0DeleteMemoryTool: DELETE /v1/memories/{id}/
Relations:
    Extends BaseMemoryTool from vidbyte.tools.builtins.memory.base.
"""

from __future__ import annotations

from vidbyte.tools.builtins.memory.base import BaseMemoryTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

_BASE_URL = "https://api.mem0.ai"


class Mem0AddMemoryTool(BaseMemoryTool):
    """Sends conversation messages to Mem0 for memory extraction, scoped by entity ID."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Mem0 managed cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the mem0_add_memory tool.
        return ToolSpec(
            name="mem0_add_memory",
            description=(
                "Send conversation messages to Mem0 for automatic memory extraction. "
                "Mem0 identifies and stores key facts from the messages. "
                "Provide at least one of user_id, agent_id, or run_id to scope the memory."
            ),
            parameters=(
                ToolParameter("messages", "array", "List of message dicts with 'role' and 'content' keys."),
                ToolParameter("user_id", "string", "Scope memories to this user.", required=False),
                ToolParameter("agent_id", "string", "Scope memories to this agent.", required=False),
                ToolParameter("run_id", "string", "Scope memories to this run.", required=False),
                ToolParameter("app_id", "string", "Scope memories to this application.", required=False),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "mem0"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Validates and POSTs messages to Mem0's memory extraction endpoint.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        messages = call.arguments.get("messages")
        if not messages or not isinstance(messages, list) or len(messages) == 0:
            return ToolResult.error(self.name, "messages must be a non-empty list.", metadata={"provider": "mem0"})

        body: dict = {"messages": list(messages)}
        for key in ("user_id", "agent_id", "run_id", "app_id"):
            value = call.arguments.get(key)
            if value:
                body[key] = str(value)

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/v3/memories/add/",
                headers={**self._auth_headers("Token"), "content-type": "application/json"},
                body=body,
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "mem0"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "mem0"})
        return ToolResult.success(self.name, self._success_output(data), metadata={"provider": "mem0"})


class Mem0SearchMemoryTool(BaseMemoryTool):
    """Searches Mem0 memories using a natural language query, scoped by entity ID."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Mem0 managed cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the mem0_search_memory tool.
        return ToolSpec(
            name="mem0_search_memory",
            description=(
                "Search Mem0 memories using a natural language query. "
                "Provide user_id, agent_id, or run_id to scope results. "
                "Returns the most relevant memory entries with similarity scores."
            ),
            parameters=(
                ToolParameter("query", "string", "The natural language search query."),
                ToolParameter("user_id", "string", "Scope search to this user.", required=False),
                ToolParameter("agent_id", "string", "Scope search to this agent.", required=False),
                ToolParameter("run_id", "string", "Scope search to this run.", required=False),
                ToolParameter("limit", "integer", "Maximum results to return (default 10).", required=False, default=10),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "mem0"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # POSTs a search query and returns matching memory entries.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        body: dict = {
            "query": str(call.arguments["query"]),
            "limit": int(call.arguments.get("limit") or 10),
        }
        for key in ("user_id", "agent_id", "run_id"):
            value = call.arguments.get(key)
            if value:
                body[key] = str(value)

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/v1/memories/search/",
                headers={**self._auth_headers("Token"), "content-type": "application/json"},
                body=body,
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "mem0"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "mem0"})

        results = data.get("results", data if isinstance(data, list) else [])
        return ToolResult.success(self.name, self._success_output(results), metadata={"provider": "mem0", "count": len(results)})


class Mem0GetMemoriesTool(BaseMemoryTool):
    """Retrieves all memories for a given user from Mem0 with optional pagination."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Mem0 managed cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the mem0_get_memories tool.
        return ToolSpec(
            name="mem0_get_memories",
            description=(
                "Retrieve all stored memories for a given user from Mem0. "
                "Supports pagination via page and page_size parameters."
            ),
            parameters=(
                ToolParameter("user_id", "string", "Retrieve memories for this user ID."),
                ToolParameter("page", "integer", "Page number for pagination (default 1).", required=False, default=1),
                ToolParameter("page_size", "integer", "Entries per page (default 10).", required=False, default=10),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "mem0"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # GETs paginated memories for the given user_id.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        params: dict = {
            "user_id": str(call.arguments["user_id"]),
            "page": int(call.arguments.get("page") or 1),
            "page_size": int(call.arguments.get("page_size") or 10),
        }

        try:
            status, data = await self._json_get(
                url=f"{self._base_url}/v1/memories/",
                headers=self._auth_headers("Token"),
                params=params,
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "mem0"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "mem0"})
        return ToolResult.success(self.name, self._success_output(data), metadata={"provider": "mem0"})


class Mem0DeleteMemoryTool(BaseMemoryTool):
    """Permanently deletes a Mem0 memory entry by its memory ID."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Mem0 managed cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the mem0_delete_memory tool.
        return ToolSpec(
            name="mem0_delete_memory",
            description="Permanently delete a Mem0 memory entry by its memory ID.",
            parameters=(
                ToolParameter("memory_id", "string", "The Mem0 memory ID to delete."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "mem0"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Sends DELETE for the given memory ID.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        memory_id: str = str(call.arguments["memory_id"])

        try:
            status, data = await self._json_delete(
                url=f"{self._base_url}/v1/memories/{memory_id}/",
                headers=self._auth_headers("Token"),
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "mem0"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "mem0"})
        return ToolResult.success(self.name, self._success_output({"deleted": True, "memory_id": memory_id}), metadata={"provider": "mem0"})


__all__ = [
    "Mem0AddMemoryTool",
    "Mem0SearchMemoryTool",
    "Mem0GetMemoriesTool",
    "Mem0DeleteMemoryTool",
]
