"""Context Protocol Header

Description:
    Browser session management tools for tab control.
Purpose:
    Provides tools for listing, creating, switching, and closing browser tabs,
    enabling agents to manage multi-tab browsing sessions.
Architecture:
    - Uses PlaywrightBrowserBackend as the primary backend.
    - Falls back to BrowserbaseBrowserBackend if Playwright is unavailable.
    - Each tool is an async function decorated with @tool.
Relations:
    Related to vidbyte.lib.providers.browser and vidbyte.tools.builtins.browser.
"""

from __future__ import annotations

import json

from vidbyte.lib.providers.browser.browserbase_backend import BrowserbaseBrowserBackend
from vidbyte.lib.providers.browser.playwright_backend import PlaywrightBrowserBackend
from vidbyte.tools.decorators import tool
from vidbyte.tools.types import ToolPermission


def _get_backend():
    backend = PlaywrightBrowserBackend()
    return backend


@tool(permission=ToolPermission.READ)
async def browser_list_tabs() -> str:
    """List all open browser tabs with their titles and URLs."""
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        tabs = await backend.list_tabs()
        if not tabs:
            return "No tabs open"
        return json.dumps(tabs, indent=2)
    except Exception as exc:
        return f"List tabs error: {exc}"


@tool(permission=ToolPermission.WRITE)
async def browser_new_tab(url: str | None = None) -> str:
    """Open a new browser tab, optionally navigating to a URL.

    Args:
        url: Optional URL to navigate to in the new tab
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.new_tab(url)
    except Exception as exc:
        return f"New tab error: {exc}"


@tool(permission=ToolPermission.WRITE)
async def browser_switch_tab(tab_index: int) -> str:
    """Switch to a specific browser tab by index.

    Args:
        tab_index: The index of the tab to switch to (0-based)
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.switch_tab(tab_index)
    except Exception as exc:
        return f"Switch tab error: {exc}"


@tool(permission=ToolPermission.WRITE)
async def browser_close_tab(tab_index: int) -> str:
    """Close a specific browser tab by index.

    Args:
        tab_index: The index of the tab to close (0-based)
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.close_tab(tab_index)
    except Exception as exc:
        return f"Close tab error: {exc}"
