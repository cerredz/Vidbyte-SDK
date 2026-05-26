"""Context Protocol Header

Description:
    Browser navigation tools for navigating to URLs, taking screenshots, and
    reading page content in various formats.
Purpose:
    Provides read-only browser tools for agents to fetch and view web pages.
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
async def browser_navigate(url: str) -> str:
    """Navigate the browser to a given URL.

    Args:
        url: The URL to navigate to
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.navigate(url)
    except Exception as exc:
        return f"Navigation error: {exc}"


@tool(permission=ToolPermission.READ)
async def browser_screenshot() -> str:
    """Take a screenshot of the current page.

    Returns the path to the saved screenshot file.
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.screenshot()
    except Exception as exc:
        return f"Screenshot error: {exc}"


@tool(permission=ToolPermission.READ)
async def browser_get_content(format: str = "markdown") -> str:
    """Get the current page content as markdown or HTML.

    Args:
        format: 'markdown' (default) or 'html'
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.get_content(format)
    except Exception as exc:
        return f"Get content error: {exc}"
