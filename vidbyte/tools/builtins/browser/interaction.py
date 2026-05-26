"""Context Protocol Header

Description:
    Browser interaction tools for clicking, typing, pressing keys, and scrolling.
Purpose:
    Provides write-level browser tools for agents to interact with web pages.
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


@tool(permission=ToolPermission.WRITE)
async def browser_click(selector: str) -> str:
    """Click an element on the page by CSS selector.

    Args:
        selector: CSS selector for the element to click
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.click(selector)
    except Exception as exc:
        return f"Click error: {exc}"


@tool(permission=ToolPermission.WRITE)
async def browser_type(selector: str, text: str) -> str:
    """Type text into an input element.

    Args:
        selector: CSS selector for the input element
        text: The text to type
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.type_text(selector, text)
    except Exception as exc:
        return f"Type error: {exc}"


@tool(permission=ToolPermission.WRITE)
async def browser_press_key(key: str) -> str:
    """Press a keyboard key.

    Args:
        key: The key to press (e.g. 'Enter', 'Tab', 'ArrowDown', 'Escape')
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.press_key(key)
    except Exception as exc:
        return f"Press key error: {exc}"


@tool(permission=ToolPermission.WRITE)
async def browser_scroll(direction: str = "down", amount: int = 300) -> str:
    """Scroll the page up or down.

    Args:
        direction: 'down' (default) or 'up'
        amount: Number of pixels to scroll (default: 300)
    """
    backend = _get_backend()
    try:
        if not await backend.is_available():
            backend = BrowserbaseBrowserBackend()
            if not await backend.is_available():
                return "Error: No browser backend available. Install Playwright or set BROWSERBASE_API_KEY."
        return await backend.scroll(direction, amount)
    except Exception as exc:
        return f"Scroll error: {exc}"
