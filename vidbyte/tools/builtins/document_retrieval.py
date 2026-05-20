# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the built-in DocumentRetrievalTool class for the Vidbyte SDK.
# Purpose: Simulates a vector search or index retrieval capability for agentic knowledge.
# Architecture & Functions:
#   - DocumentRetrievalTool (subclass of BaseTool): Mock query database retriever.
#   - DocumentRetrievalTool.spec(): Defines 'query' and optional 'top_k' parameters.
#   - DocumentRetrievalTool.execute(call): Performs matching and returns structured content.
# Codebase Relation:
#   - Fits into the builtins namespace as the main data lookup tool.
# Similar Files:
#   - vidbyte/tools/builtins/web_search.py (general web lookup)
# ==============================================================================

from __future__ import annotations

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec, ToolStatus


class DocumentRetrievalTool(BaseTool):
    """
    Simulates a vector-based document retriever (RAG).
    Queries a local mock repository and returns document extracts.
    """

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="document_retrieval",
            description="Queries the Vidbyte internal document base to fetch design specs and technical reports.",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search concepts or keywords to match against documents.",
                    required=True
                ),
                ToolParameter(
                    name="top_k",
                    type="int",
                    description="Maximum number of documents to return.",
                    required=False,
                    default=2
                )
            ]
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        query = call.arguments.get("query", "").lower()
        top_k = call.arguments.get("top_k", 2)

        # Mocked technical design library
        mock_library = [
            {
                "id": "doc_001",
                "title": "Vidbyte SDK System Prompts v1",
                "content": "All default strategy system prompts must reside inside the internal service layers. The client SDK ships with standard overridable classes mapped by PromptKey."
            },
            {
                "id": "doc_002",
                "title": "Vidbyte Tools Registry Specification",
                "content": "The Tools Abstraction consists of a thread-safe ToolRegistry mapping unique BaseTool names to tool instances. Executor acts as the dispatch controller."
            },
            {
                "id": "doc_003",
                "title": "ReAct Design Architecture",
                "content": "Reasoning and Acting (ReAct) strategy implements an iterative loop of Thought -> Action -> Observation -> Final Answer to solve user tasks using tools."
            }
        ]

        matches = []
        for doc in mock_library:
            if query in doc["title"].lower() or query in doc["content"].lower():
                matches.append(f"Document ID: {doc['id']}\nTitle: {doc['title']}\nExcerpt: {doc['content']}")

        # Truncate to top_k
        results = matches[:top_k]

        if not results:
            output = f"No documents matched: '{query}'. Try 'prompts', 'tools', or 'react'."
        else:
            output = "\n---\n".join(results)

        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output=output,
            metadata={"query": query, "matches_found": len(matches), "returned_count": len(results)}
        )
