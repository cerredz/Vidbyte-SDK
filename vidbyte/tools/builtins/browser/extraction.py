"""Context Protocol Header

Description:
    Browser content extraction and action tools for scraping and AI-driven
    agentic browser actions.
Purpose:
    Provides tools to extract structured data from pages or execute free-form
    natural language actions in the browser.
Architecture:
    - Uses PlaywrightBrowserBackend as the primary backend.
    - Falls back to BrowserbaseBrowserBackend if Playwright is unavailable.
    - Each tool is an async function decorated with @tool.
Relations:
    Related to vidbyte.lib.providers.browser and vidbyte.tools.builtins.browser.
"""

from __future__ import annotations

from vidbyte.lib.providers.browser.browserbase_backend import BrowserbaseBrowserBackend
from vidbyte.lib.providers.browser.playwright_backend import PlaywrightBrowserBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


def _get_backend():
    backend = PlaywrightBrowserBackend()
    return backend


@tool(permission=ToolPermission.READ)
async def browser_extract(instruction: str, schema: dict | None = None) -> str:
    """Extract content from the current page based on natural language instruction.

    Args:
        instruction: Description of what to extract from the page
        schema: Optional JSON schema for structured extraction
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.extract(instruction, schema)
    except Exception as exc:
        return f"Extract error: {exc}"


@tool(permission=ToolPermission.WRITE)
async def browser_act(instruction: str) -> str:
    """Execute a natural language action in the browser.

    Args:
        instruction: Description of the action to perform
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.act(instruction)
    except Exception as exc:
        return f"Act error: {exc}"
