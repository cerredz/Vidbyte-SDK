"""Context Protocol Header

Description:
    Vidbyte built-in tools for the Cognee knowledge-graph memory API.
Purpose:
    Lets agents ingest data, build knowledge graphs, search, and delete
    datasets via the Cognee REST API (self-hosted or Cognee Cloud).
Architecture & Key Functions:
    - CogneeAddTool: Ingests text chunks into designated staging datasets.
    - CogneeCognifyTool: Builds a semantic knowledge graph from raw staged text.
    - CogneeSearchTool: Queries the knowledge graph using vector/traversal search.
    - CogneeDeleteTool: Permanently deletes Cognee datasets and their graph nodes.
Relation to Codebase:
    Exposed under the vidbyte.tools.builtins namespace, enabling agents to leverage
    external structured knowledge graph memory for relational mapping.
Similar Files:
    - vidbyte/tools/builtins/memory/supermemory.py
    - vidbyte/tools/builtins/memory/mem0.py
    - vidbyte/tools/builtins/memory/zep.py
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

_DEFAULT_BASE_URL = "http://localhost:8000"


class CogneeAddTool(BaseMemoryTool):
    """Ingests text content into a Cognee dataset for knowledge graph construction."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 30.0) -> None:
        # Initializes with a configurable base URL for self-hosted or cloud Cognee.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the cognee_add tool.
        return ToolSpec(
            name="cognee_add",
            description=(
                "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. "
                "Use this tool to ingest unstructured text content into a Cognee dataset to prepare it for knowledge graph construction. "
                "The ingested text is staged in Cognee's database under a specific dataset identifier, which defaults to 'default' if not specified. "
                "This tool represents the ingestion phase and must be followed by a cognify call to build the graph."
            ),
            parameters=(
                ToolParameter("content", "string", "The text content to ingest into Cognee."),
                ToolParameter("dataset_id", "string", "Dataset name to ingest into (default: 'default').", required=False, default="default"),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "cognee"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # POSTs the content and dataset_id to Cognee's add endpoint.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        content: str = str(call.arguments["content"])
        dataset_id: str = str(call.arguments.get("dataset_id") or "default")

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/api/v1/add",
                headers=self._auth_headers("Bearer"),
                body={"data": content, "datasetId": dataset_id},
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "cognee"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "cognee"})
        return ToolResult.success(self.name, self._success_output(data), metadata={"provider": "cognee", "dataset_id": dataset_id})


class CogneeCognifyTool(BaseMemoryTool):
    """Triggers Cognee knowledge graph construction from previously ingested data."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 60.0) -> None:
        # Uses a longer default timeout since graph construction can take time.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the cognee_cognify tool.
        return ToolSpec(
            name="cognee_cognify",
            description=(
                "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. "
                "Use this tool to trigger the knowledge graph construction process on a previously ingested Cognee dataset. "
                "The cognification process extracts entities, complex relationships, and hierarchical facts from the staged raw text, creating a queryable semantic graph. "
                "This step is a prerequisite for executing graph-based queries or searches on the ingested data."
            ),
            parameters=(
                ToolParameter("dataset_id", "string", "Dataset to cognify (default: 'default').", required=False, default="default"),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "cognee"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # POSTs the cognify request to trigger async knowledge graph construction.
        dataset_id: str = str(call.arguments.get("dataset_id") or "default")

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/api/v1/cognify",
                headers=self._auth_headers("Bearer"),
                body={"datasetId": dataset_id},
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "cognee"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "cognee"})
        return ToolResult.success(self.name, self._success_output(data), metadata={"provider": "cognee", "dataset_id": dataset_id})


class CogneeSearchTool(BaseMemoryTool):
    """Queries the Cognee knowledge graph using semantic or graph-completion search."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 30.0) -> None:
        # Initializes with a configurable base URL for self-hosted or cloud Cognee.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the cognee_search tool.
        return ToolSpec(
            name="cognee_search",
            description=(
                "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. "
                "Use this tool to search a Cognee dataset using semantic or graph-completion search modes. "
                "The search queries the built knowledge graph, returning structured relationships and facts relevant to the search query. "
                "You must ensure that the dataset has been successfully cognified prior to calling this search tool."
            ),
            parameters=(
                ToolParameter("query", "string", "The search query."),
                ToolParameter("search_type", "string", "Search mode: 'GRAPH_COMPLETION' or 'SEMANTIC' (default: 'GRAPH_COMPLETION').", required=False, default="GRAPH_COMPLETION"),
                ToolParameter("dataset_id", "string", "Dataset to search within (default: 'default').", required=False, default="default"),
            ),
            permission=ToolPermission.READ,
            metadata={"provider": "cognee"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # POSTs the search query to Cognee and returns the results array.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        query: str = str(call.arguments["query"])
        search_type: str = str(call.arguments.get("search_type") or "GRAPH_COMPLETION").upper()
        dataset_id: str = str(call.arguments.get("dataset_id") or "default")

        try:
            status, data = await self._json_post(
                url=f"{self._base_url}/api/v1/search",
                headers=self._auth_headers("Bearer"),
                body={"query": query, "searchType": search_type, "datasetId": dataset_id},
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "cognee"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "cognee"})

        results = data if isinstance(data, list) else data.get("results", data)
        return ToolResult.success(self.name, self._success_output(results), metadata={"provider": "cognee"})


class CogneeDeleteTool(BaseMemoryTool):
    """Deletes a Cognee dataset and all of its ingested data and graph nodes."""

    def __init__(self, api_key: str, base_url: str = _DEFAULT_BASE_URL, timeout_seconds: float = 30.0) -> None:
        # Initializes with a configurable base URL for self-hosted or cloud Cognee.
        super().__init__(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def spec(self) -> ToolSpec:
        # Returns the model-facing declaration for the cognee_delete tool.
        return ToolSpec(
            name="cognee_delete",
            description=(
                "Cognee is a state-of-the-art knowledge-graph memory platform that structures unstructured data into semantic graphs for AI agents. "
                "Use this tool to permanently delete a Cognee dataset and all of its ingested text and generated graph nodes. "
                "Deleting the dataset immediately removes all of its associated nodes, edges, and raw chunks from the Cognee server. "
                "This is a permanent administrative operation that cannot be undone, reclaiming local or cloud storage."
            ),
            parameters=(
                ToolParameter("dataset_id", "string", "The Cognee dataset ID to delete."),
            ),
            permission=ToolPermission.WRITE,
            metadata={"provider": "cognee"},
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Sends DELETE for the given dataset_id.
        error = self.validate_call(call)
        if error:
            return ToolResult.error(self.name, error)

        dataset_id: str = str(call.arguments["dataset_id"])

        try:
            status, data = await self._json_delete(
                url=f"{self._base_url}/api/v1/datasets/{dataset_id}/",
                headers=self._auth_headers("Bearer"),
            )
        except Exception as exc:
            return ToolResult.error(self.name, f"Request failed: {exc}", metadata={"provider": "cognee"})

        if not self._ok(status):
            return ToolResult.error(self.name, self._error_output(status, data), metadata={"provider": "cognee"})
        return ToolResult.success(self.name, self._success_output({"deleted": True, "dataset_id": dataset_id}), metadata={"provider": "cognee"})


__all__ = [
    "CogneeAddTool",
    "CogneeCognifyTool",
    "CogneeSearchTool",
    "CogneeDeleteTool",
]
