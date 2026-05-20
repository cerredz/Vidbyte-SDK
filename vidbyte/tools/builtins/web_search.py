# ==============================================================================
# CONTEXT PROTOCOL HEADER
# Description: Defines the built-in WebSearchTool class for the Vidbyte SDK.
# Purpose: Simulates a web search utility to provide agents with external search capabilities.
# Architecture & Functions:
#   - WebSearchTool (subclass of BaseTool): Executes mock search queries.
#   - WebSearchTool.spec(): Defines 'query' parameter.
#   - WebSearchTool.execute(call): Resolves search results from structured mock database.
# Codebase Relation:
#   - Standard builtin tool for agentic research strategies.
# Similar Files:
#   - vidbyte/tools/builtins/document_retrieval.py (other information retrieval tool)
# ==============================================================================

from __future__ import annotations

from vidbyte.tools.base import BaseTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec, ToolStatus


class WebSearchTool(BaseTool):
    """
    Simulates a web search tool.
    Returns highly structured informational snippets based on the input query keywords.
    """

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="web_search",
            description="Searches the web for articles, documentations, and general information.",
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search query or keywords to look up.",
                    required=True
                )
            ]
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        query = call.arguments.get("query", "").lower()

        # Database of mocked search results
        mock_database = {
            "python": "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability.",
            "react": "React (also known as React.js) is a free and open-source front-end JavaScript library for building user interfaces based on components.",
            "vidbyte": "Vidbyte is a cutting-edge developer platform building advanced agentic coding systems and model coordination SDKs.",
            "gradient descent": "Gradient descent is a first-order iterative optimization algorithm for finding a local minimum of a differentiable function.",
            "ai": "Artificial Intelligence refers to the simulation of human intelligence processes by machines, especially computer systems.",
        }

        # Check for matches
        matched_results = []
        for key, text in mock_database.items():
            if key in query:
                matched_results.append(f"[{key.title()}]: {text}")

        if not matched_results:
            output = f"Search returned 0 results for: '{query}'. Try using generic keywords like 'python', 'react', 'gradient descent', or 'vidbyte'."
        else:
            output = "\n\n".join(matched_results)

        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            output=output,
            metadata={"query": query, "results_count": len(matched_results)}
        )
