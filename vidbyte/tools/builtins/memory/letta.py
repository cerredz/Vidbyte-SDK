"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Letta (MemGPT) stateful agent memory API.
Purpose:
    Lets agents insert, search, and delete archival memory passages for a
    Letta agent, and read named in-context memory blocks.
Architecture & Key Functions:
    - LettaAddArchivalMemoryTool: Inserts a text passage into Letta's long-term archival store.
    - LettaSearchArchivalMemoryTool: Searches an agent's archival memory via query string.
    - LettaDeleteArchivalMemoryTool: Deletes an archival passage by unique passage ID.
    - LettaGetMemoryBlockTool: Reads named core blocks (e.g., persona, human) from agent context.
Relation to Codebase:
    Exposed under the vidbyte.tools.builtins namespace, enabling agents to leverage
    dynamic stateful contexts and archival persistence during model execution.
Similar Files:
    - vidbyte/tools/builtins/memory/supermemory.py
    - vidbyte/tools/builtins/memory/mem0.py
    - vidbyte/tools/builtins/memory/zep.py
    - vidbyte/tools/builtins/memory/cognee.py
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
                "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. "
                "Use this tool to insert a text passage into a Letta agent's long-term archival memory store. "
                "Archival memory acts as an infinite-horizon repository that persists across distinct conversation sessions and agent lifetimes. "
                "The stored passage is automatically indexed via vector embeddings, making it discoverable through future semantic search queries."
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
                "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. "
                "Use this tool to search a Letta agent's archival memory for passages matching a natural language query. "
                "The search returns a ranked list of relevant memory passages along with their unique identifiers and text contents. "
                "This allows agents to recall precise past facts and interactions on demand during their reasoning loop."
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
                "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. "
                "Use this tool to permanently delete a specific archival memory passage from a Letta agent's store using its passage ID. "
                "Deleting a passage immediately removes it from the agent's long-term index, ensuring it will not be returned by future search queries. "
                "This tool requires both the target agent identifier and the passage identifier to execute."
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
                "Letta is a state-of-the-art stateful memory platform that equips agents with persistent archival memory and dynamic in-context blocks. "
                "Use this tool to read the current text value of a named in-context memory block, such as 'persona' or 'human'. "
                "In-context blocks represent the active working memory of a Letta agent that is directly appended to the model's system instructions. "
                "Reading a block allows the system to inspect the agent's self-concept or known facts about the user."
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
