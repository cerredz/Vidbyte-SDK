"""Context Protocol Header

Description:
    Re-exports browser backend implementations.
Purpose:
    Provides a stable import surface for browser provider backends without
    exposing internal implementation details.
Architecture:
    - BaseBrowserBackend: Abstract contract.
    - PlaywrightBrowserBackend: Local Playwright-based implementation.
    - BrowserbaseBrowserBackend: Cloud Browserbase API implementation.
Relations:
    Related to vidbyte.tools.builtins.browser.
"""

from __future__ import annotations

from vidbyte.lib.providers.browser.base import BaseBrowserBackend
from vidbyte.lib.providers.browser.browserbase_backend import BrowserbaseBrowserBackend
from vidbyte.lib.providers.browser.playwright_backend import PlaywrightBrowserBackend

__all__ = [
    "BaseBrowserBackend",
    "BrowserbaseBrowserBackend",
    "PlaywrightBrowserBackend",
]
