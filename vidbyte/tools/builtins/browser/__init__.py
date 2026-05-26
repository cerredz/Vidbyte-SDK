"""Context Protocol Header

Description:
    Re-exports all built-in browser automation tools.
Purpose:
    Provides a single import surface for browser navigation, interaction,
    content extraction, and session management tools.
Architecture:
    - Function-based tools using the @tool decorator.
    - Navigation tools: navigate, screenshot, get_content.
    - Interaction tools: click, type, press_key, scroll.
    - Extraction tools: extract, act.
    - Session tools: list_tabs, new_tab, switch_tab, close_tab.
Relations:
    Related to vidbyte.lib.providers.browser and vidbyte.tools.builtins.
"""

from __future__ import annotations

from vidbyte.tools.builtins.browser.extraction import browser_act, browser_extract
from vidbyte.tools.builtins.browser.interaction import browser_click, browser_press_key, browser_scroll, browser_type
from vidbyte.tools.builtins.browser.navigate import browser_get_content, browser_navigate, browser_screenshot
from vidbyte.tools.builtins.browser.session import browser_close_tab, browser_list_tabs, browser_new_tab, browser_switch_tab

__all__ = [
    "browser_act",
    "browser_click",
    "browser_close_tab",
    "browser_extract",
    "browser_get_content",
    "browser_list_tabs",
    "browser_navigate",
    "browser_new_tab",
    "browser_press_key",
    "browser_screenshot",
    "browser_scroll",
    "browser_switch_tab",
    "browser_type",
]
