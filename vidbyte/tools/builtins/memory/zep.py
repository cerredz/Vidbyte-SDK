"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Zep Cloud memory API.
Purpose:
    Lets agents add messages, retrieve context strings, search, and delete
    Zep sessions — all organized around the session-scoped memory model.
Architecture & Key Functions:
    - ZepAddMemoryTool: Appends chat history to a Zep session's buffer.
    - ZepGetMemoryTool: Fetches formatted context summary strings for prompts.
    - ZepSearchMemoryTool: Searches session history via hybrid semantic/graph search.
    - ZepDeleteSessionTool: Removes sessions and all memory permanently.
Relation to Codebase:
    Exposed under the vidbyte.tools.builtins namespace, enabling agents to leverage
    external temporal facts and graphs for prompt enrichment across sessions.
Similar Files:
    - vidbyte/tools/builtins/memory/supermemory.py
    - vidbyte/tools/builtins/memory/mem0.py
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
                "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. "
                "Use this tool to add new conversation messages to a specific Zep session's memory buffer. "
                "The tool automatically handles session creation if the session ID does not already exist on the Zep platform. "
                "Added messages are processed asynchronously by Zep to update the session's temporal facts, summary, and memory graph nodes."
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
                "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. "
                "Use this tool to retrieve a pre-formatted context string of relevant facts and recent messages for a Zep session. "
                "The returned context string is optimized for direct injection into the agent's prompt, providing immediate continuity. "
                "You can customize the retrieval by specifying the number of recent messages to include alongside the summarized facts."
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
                "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. "
                "Use this tool to perform a hybrid semantic and graph-based search against a Zep session's memory history. "
                "The tool queries the session's memory graph using natural language text, returning ranked excerpts of historical messages and extracted facts. "
                "This allows the agent to retrieve precise, long-term context from earlier parts of the conversation."
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
                "Zep is a state-of-the-art managed memory platform that provides temporal memory graphs and session history context for AI applications. "
                "Use this tool to permanently and irreversibly delete a Zep session and all of its accumulated conversation history and facts. "
                "Deleting a session purges all associated messages, summaries, and graph nodes from Zep's servers, reclaiming storage. "
                "Future requests for the same session ID will require a new session creation flow."
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
