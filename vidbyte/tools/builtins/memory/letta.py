"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Letta (MemGPT) stateful agent memory API.
Purpose:
    Lets agents insert, search, and delete archival memory passages for a
    Letta agent, and read named in-context memory blocks.
Architecture:
    - LettaAddArchivalMemoryTool: POST /v1/agents/{agent_id}/archival-memory
    - LettaSearchArchivalMemoryTool: GET /v1/agents/{agent_id}/archival-memory?query=
    - LettaDeleteArchivalMemoryTool: DELETE /v1/agents/{agent_id}/archival-memory/{id}
    - LettaGetMemoryBlockTool: GET /v1/agents/{agent_id}/memory/block/{block_name}
Relations:
    Extends BaseMemoryTool from vidbyte.tools.builtins.memory.base.
    base_url defaults to https://api.letta.com for Letta Cloud.
"""

from __future__ import annotations

from vidbyte.tools.builtins.memory.base import BaseMemoryTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

_DEFAULT_BASE_URL = "https://api.letta.com"


class LettaAddArchivalMemoryTool(BaseMemoryTool):
    """Inserts a text passage into a Letta agent's archival (long-term) memory store."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 30.0) -> None:
        # Initializes with a configurable base URL for Letta Cloud or self-hosted.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the letta_add_archival_memory tool.
        return ToolSpec(
            name="letta_add_archival_memory",
            description=(
                "Insert a text passage into a Letta agent's archival memory. "
                "Archival memory persists across sessions and can be searched later. "
                "Requires the Letta agent_id and the text to store."
            ),
            parameters=(
                ToolParameter("agent_id", "string", "The Letta agent ID to add archival memory to."),
                ToolParameter("text", "string", "The text passage to store in archival memory."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "letta"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # POSTs the text passage to the agent's archival memory endpoint.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        agent_id: str = str(call.arguments["agent_id"])
        text: str = str(call.arguments["text"])

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/v1/agents/{agent_id}/archival-memory",
                headers=self._auth_headers("Bearer"),
                body={"text": text},
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "letta"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "letta"})
        return ToolResult.success(self.name, self._success_output(data), metadata={"provider": "letta", "agent_id": agent_id})


class LettaSearchArchivalMemoryTool(BaseMemoryTool):
    """Searches a Letta agent's archival memory for passages matching a query."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 30.0) -> None:
        # Initializes with a configurable base URL for Letta Cloud or self-hosted.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the letta_search_archival_memory tool.
        return ToolSpec(
            name="letta_search_archival_memory",
            description=(
                "Search a Letta agent's archival memory for passages matching a query. "
                "Returns the most relevant stored passages with their IDs."
            ),
            parameters=(
                ToolParameter("agent_id", "string", "The Letta agent ID to search archival memory for."),
                ToolParameter("query", "string", "The search query."),
                ToolParameter("limit", "integer", "Maximum passages to return (default 10).", required=False, default=10),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "letta"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # GETs archival memory passages filtered by query string.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        agent_id: str = str(call.arguments["agent_id"])
        query: str = str(call.arguments["query"])
        limit: int = int(call.arguments.get("limit") or 10)

        try:
            status, data = await self._json_get(
                url=f"{self._base_url}/v1/agents/{agent_id}/archival-memory",
                headers=self._auth_headers("Bearer"),
                params={"query": query, "limit": limit},
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "letta"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "letta"})

        results = data if isinstance(data, list) else data.get("results", data)
        return ToolResult.success(self.name, self._success_output(results), metadata={"provider": "letta", "agent_id": agent_id})


class LettaDeleteArchivalMemoryTool(BaseMemoryTool):
    """Permanently deletes a specific archival memory passage from a Letta agent."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 30.0) -> None:
        # Initializes with a configurable base URL for Letta Cloud or self-hosted.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the letta_delete_archival_memory tool.
        return ToolSpec(
            name="letta_delete_archival_memory",
            description=(
                "Permanently delete a specific archival memory passage from a Letta agent. "
                "Requires the agent_id and the memory_id returned by letta_search_archival_memory."
            ),
            parameters=(
                ToolParameter("agent_id", "string", "The Letta agent ID."),
                ToolParameter("memory_id", "string", "The archival memory passage ID to delete."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "letta"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Sends DELETE for the given archival memory ID on the given agent.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        agent_id: str = str(call.arguments["agent_id"])
        memory_id: str = str(call.arguments["memory_id"])

        try:
            status, data = await self._json_delete(
                url=f"{self._base_url}/v1/agents/{agent_id}/archival-memory/{memory_id}",
                headers=self._auth_headers("Bearer"),
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "letta"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "letta"})
        return ToolResult.success(
            self.name,
            self._success_output({"deleted": True, "agent_id": agent_id, "memory_id": memory_id}),
            metadata={"provider": "letta"},
        )


class LettaGetMemoryBlockTool(BaseMemoryTool):
    """Reads a named in-context memory block (e.g. 'persona' or 'human') from a Letta agent."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 30.0) -> None:
        # Initializes with a configurable base URL for Letta Cloud or self-hosted.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the letta_get_memory_block tool.
        return ToolSpec(
            name="letta_get_memory_block",
            description=(
                "Read a named in-context memory block from a Letta agent. "
                "Common block names: 'persona' (agent identity) and 'human' (user facts). "
                "Returns the block label and its current text value."
            ),
            parameters=(
                ToolParameter("agent_id", "string", "The Letta agent ID."),
                ToolParameter("block_name", "string", "The memory block name (e.g. 'persona', 'human')."),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "letta"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # GETs the named memory block and returns its label and value.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        agent_id: str = str(call.arguments["agent_id"])
        block_name: str = str(call.arguments["block_name"])

        try:
            status, data = await self._json_get(
                url=f"{self._base_url}/v1/agents/{agent_id}/memory/block/{block_name}",
                headers=self._auth_headers("Bearer"),
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "letta"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "letta"})
        return ToolResult.success(self.name, self._success_output(data), metadata={"provider": "letta", "agent_id": agent_id, "block_name": block_name})


__all__ = [
    "LettaAddArchivalMemoryTool",
    "LettaSearchArchivalMemoryTool",
    "LettaDeleteArchivalMemoryTool",
    "LettaGetMemoryBlockTool",
]
