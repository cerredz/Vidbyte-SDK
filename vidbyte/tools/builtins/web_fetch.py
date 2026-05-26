"""Context Protocol Header

Description:
    Built-in web fetch tool that retrieves web page content and converts it.
Purpose:
    Enables agents to fetch and read web page content, converting HTML to
    markdown or returning plain text.
Architecture:
    - Uses the @tool decorator with ToolPermission.READ.
    - Delegates to HttpxFetchBackend for HTTP fetching and conversion.
    - Truncates output to 100000 characters if needed.
Relations:
    Related to vidbyte.lib.providers.web_fetch and vidbyte.tools.decorators.
"""

from __future__ import annotations

from vidbyte.lib.providers.web_fetch.httpx_backend import HttpxFetchBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission

MAX_OUTPUT_CHARS = 100000


@tool(permission=ToolPermission.READ)
async def web_fetch(url: str, format: str = "markdown", timeout_ms: int = 30000) -> str:
    """Fetch content from a URL and return it as markdown or plain text.

    Args:
        url: The URL to fetch
        format: 'markdown' (default) or 'text'
        timeout_ms: Request timeout in milliseconds
    """
    backend = HttpxFetchBackend()
    try:
        result = await backend.fetch(url, format, timeout_ms)
    except Exception as exc:
        return f"Error fetching URL: {exc}"

    content = result.content
    if len(content) > MAX_OUTPUT_CHARS:
        content = content[:MAX_OUTPUT_CHARS] + (
            f"\n\n[Content truncated at {MAX_OUTPUT_CHARS} characters. "
            f"Original was {len(result.content)} chars.]"
        )

    return content
