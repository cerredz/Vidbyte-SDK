"""Context Protocol Header

Description:
    Built-in web search tool that queries the internet via cascading providers.
Purpose:
    Enables agents to retrieve real-time web search results formatted as JSON
    using Tavily, Brave, or DuckDuckGo backends.
Architecture:
    - Uses the @tool decorator with ToolPermission.READ.
    - Delegates to AutoWebSearchBackend for provider selection.
    - Returns a JSON string of SearchResult objects or an error.
Relations:
    Related to vidbyte.lib.providers.web_search and vidbyte.tools.decorators.
"""

from __future__ import annotations

import json

from vidbyte.lib.providers.web_search.auto import AutoWebSearchBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission, ToolResult


@tool(permission=ToolPermission.READ)
async def web_search(query: str, max_results: int = 10) -> str:
    """Search the web and return results with title, url, and snippet.

    Returns a JSON array of objects with 'title', 'url', and 'snippet' fields.
    Use this to find current information from the internet.
    """
    backend = AutoWebSearchBackend()
    try:
        results = await backend.search(query, max_results)
        output = json.dumps(
            [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in results
            ],
            default=str,
        )
        return output
    except Exception as exc:
        return str(exc)
