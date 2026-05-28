"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Supermemory managed memory API.
Purpose:
    Lets agents add, search, and delete semantic memories via Supermemory
    without any provider SDK dependency — only stdlib HttpTransport.
Architecture:
    - SupermemoryAddMemoryTool: POST /v3/documents
    - SupermemorySearchMemoryTool: POST /v3/search
    - SupermemoryDeleteMemoryTool: DELETE /v3/documents/{id}
Relations:
    Extends BaseMemoryTool from vidbyte.tools.builtins.memory.base.
"""

from __future__ import annotations

from vidbyte.tools.builtins.memory.base import BaseMemoryTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolPermission, ToolResult, ToolSpec

_BASE_URL = "https://api.supermemory.ai"


class SupermemoryAddMemoryTool(BaseMemoryTool):
    """Stores a text passage in Supermemory with optional container tags and metadata."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Supermemory managed cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the supermemory_add_memory tool.
        return ToolSpec(
            name="supermemory_add_memory",
            description=(
                "Store a text passage in Supermemory. "
                "Optionally scope it to one or more container tags (e.g. user IDs or project names) "
                "and attach arbitrary metadata. Returns the created document ID."
            ),
            parameters=(
                ToolParameter("content", "string", "The text content to store as a memory."),
                ToolParameter("container_tags", "array", "Container tag strings to scope this memory (e.g. ['user_123']).", required=False),
                ToolParameter("metadata", "object", "Arbitrary key-value metadata to attach.", required=False),
                ToolParameter("custom_id", "string", "Optional caller-supplied ID; updates existing doc if it matches.", required=False),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "supermemory"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Builds and POSTs the document payload, returning the created document ID.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        content: str = str(call.arguments["content"])
        container_tags: list = list(call.arguments.get("container_tags") or [])
        metadata: dict = dict(call.arguments.get("metadata") or {})
        custom_id: str | None = call.arguments.get("custom_id") or None

        body: dict = {"content": content, "containerTags": container_tags, "metadata": metadata}
        if custom_id:
            body["customId"] = custom_id

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/v3/documents",
                headers=self._auth_headers("Bearer"),
                body=body,
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "supermemory"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "supermemory"})
        return ToolResult.success(self.name, self._success_output(data), metadata={"provider": "supermemory"})


class SupermemorySearchMemoryTool(BaseMemoryTool):
    """Searches Supermemory using a semantic query, optionally scoped to a container tag."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Supermemory managed cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the supermemory_search_memory tool.
        return ToolSpec(
            name="supermemory_search_memory",
            description=(
                "Search Supermemory for passages matching a semantic query. "
                "Optionally filter by container_tag to scope results to a user or project. "
                "Returns an array of matching document excerpts."
            ),
            parameters=(
                ToolParameter("query", "string", "The semantic search query."),
                ToolParameter("container_tag", "string", "Optional container tag to scope results.", required=False),
                ToolParameter("top_k", "integer", "Maximum number of results to return (default 10).", required=False, default=10),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "supermemory"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # POSTs a search query and returns the matching results array.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        query: str = str(call.arguments["query"])
        container_tag: str | None = call.arguments.get("container_tag") or None
        top_k: int = int(call.arguments.get("top_k") or 10)

        body: dict = {"query": query, "limit": top_k}
        if container_tag:
            body["containerTag"] = container_tag

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/v3/search",
                headers=self._auth_headers("Bearer"),
                body=body,
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "supermemory"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "supermemory"})

        results = data.get("results", data)
        return ToolResult.success(self.name, self._success_output(results), metadata={"provider": "supermemory", "count": len(results) if isinstance(results, list) else 0})


class SupermemoryDeleteMemoryTool(BaseMemoryTool):
    """Deletes a Supermemory document by its document ID."""

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        # Initializes with the Supermemory managed cloud base URL.
        super().__init__(api_key=api_key, base_url=_BASE_URL, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the supermemory_delete_memory tool.
        return ToolSpec(
            name="supermemory_delete_memory",
            description="Delete a Supermemory document by its document ID. This is permanent.",
            parameters=(
                ToolParameter("document_id", "string", "The Supermemory document ID to delete."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "supermemory"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Sends DELETE for the given document ID and surfaces any HTTP error.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        document_id: str = str(call.arguments["document_id"])

        try:
            status, data = await self._json_delete(
                url=f"{self._base_url}/v3/documents/{document_id}",
                headers=self._auth_headers("Bearer"),
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "supermemory"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "supermemory"})
        return ToolResult.success(self.name, self._success_output({"deleted": True, "document_id": document_id}), metadata={"provider": "supermemory"})


__all__ = [
    "SupermemoryAddMemoryTool",
    "SupermemorySearchMemoryTool",
    "SupermemoryDeleteMemoryTool",
]
