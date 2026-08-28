"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Mem0 managed memory API.
Purpose:
    Lets agents add, search, retrieve, and delete memories via Mem0 with
    user/agent/run scoping — no provider SDK dependency required.
Architecture & Key Functions:
    - Mem0AddMemoryTool: Extracts and adds memories from messages.
    - Mem0SearchMemoryTool: Searches Mem0 memory via natural language queries.
    - Mem0GetMemoriesTool: Retrieves all memories for a user/entity with pagination.
    - Mem0DeleteMemoryTool: Deletes memory records by unique ID.
Relation to Codebase:
    Exposed under the vidbyte.tools.builtins namespace, enabling agents to leverage
    external synthesized graph/semantic memories for persistence across distinct run sessions.
Similar Files:
    - vidbyte/tools/builtins/memory/supermemory.py
    - vidbyte/tools/builtins/memory/zep.py
    - vidbyte/tools/builtins/memory/cognee.py
    - vidbyte/tools/builtins/memory/letta.py
"""

from __future__ import annotations

from vidbyte.tools.builtins.memory.base import BaseMemoryTool
from vidbyte.tools.types import (
    ToolCall,
    ToolParameter,
    ToolPermission,
    ToolResult,
    ToolSpec,
)

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
                "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. "
                "Use this tool to send a list of conversation messages to Mem0 for automatic extraction of key facts, preferences, and long-term context. "
                "The extracted facts are dynamically synthesized, resolved against existing memories, and saved under the specified entity scopes such as user ID or agent ID. "
                "This allows agents to maintain persistent personalization without manual memory modeling or database management."
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
                "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. "
                "Use this tool to search for relevant memories using a natural language query under a specific entity scope. "
                "The search is executed across the synthesized facts associated with the user, agent, or run, returning ranked matches with similarity scores. "
                "This allows the agent to dynamically retrieve relevant personalization context at runtime to guide its responses."
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
                "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. "
                "Use this tool to retrieve a comprehensive list of all synthesized facts stored for a given user or entity scope. "
                "The retrieved memories are returned in a structured list containing their unique identifiers, text values, and timestamp metadata. "
                "The tool supports pagination parameters, enabling efficient traversal of large memory histories without overloading the context window."
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
            description=(
                "Mem0 is a state-of-the-art managed memory platform that provides intelligent, self-improving memory scoped by user, agent, and run. "
                "Use this tool to permanently delete a specific memory entry from the Mem0 platform using its unique memory identifier. "
                "Deleting an entry immediately removes that synthesized fact from the entity's profile, preventing it from appearing in subsequent searches or retrievals. "
                "This allows agents or users to prune outdated, incorrect, or sensitive facts from their history."
            ),
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
