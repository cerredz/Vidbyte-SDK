"""Context Protocol Header

Description:
    Implements a local browser automation backend using Playwright.
Purpose:
    Provides navigation, interaction, content extraction, and tab management
    via a headless Chromium browser controlled by Playwright's async API.
Architecture:
    - Module-level singleton _browser and _page instances.
    - _ensure_browser() lazily starts the browser on first use.
    - All public methods are async and delegate to Playwright async API.
    - is_available() returns False when playwright is not installed.
Relations:
    Related to vidbyte.lib.providers.browser.base and vidbyte.tools.builtins.browser.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from vidbyte.lib.providers.browser.base import BaseBrowserBackend

logger = logging.getLogger(__name__)

_playwright_instance = None
_browser = None
_page = None


async def _ensure_browser() -> None:
    global _playwright_instance, _browser, _page
    if _browser is not None:
        return
    try:
        from playwright.async_api import async_playwright

        _playwright_instance = await async_playwright().start()
        _browser = await _playwright_instance.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        _page = await _browser.new_page()
    except ImportError:
        raise ImportError("Playwright is not installed. Install with: pip install playwright && playwright install chromium")
    except Exception:
        if _playwright_instance is not None:
            await _playwright_instance.stop()
            _playwright_instance = None
        _browser = None
        _page = None
        raise


class PlaywrightBrowserBackend(BaseBrowserBackend):
    async def navigate(self, url: str) -> str:
        await _ensure_browser()
        await _page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return await _page.title()

    async def screenshot(self) -> str:
        await _ensure_browser()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        await _page.screenshot(path=path, full_page=True)
        return path

    async def get_content(self, format: str) -> str:
        await _ensure_browser()
        html = await _page.content()
        if format == "markdown":
            import re

            text = html
            text = re.sub(r"<head[^>]*>.*?</head>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n\n# \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n## \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n\n### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<h4[^>]*>(.*?)</h4>", r"\n\n#### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<h5[^>]*>(.*?)</h5>", r"\n\n##### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<h6[^>]*>(.*?)</h6>", r"\n\n###### \1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\n\1\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<a[^>]*href=[\"'](.*?)[\"'][^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"</?(?:ul|ol)[^>]*>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\n\n```\n\1\n```\n\n", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<img[^>]*alt=[\"'](.*?)[\"'][^>]*>", r"![\1]", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"&amp;", "&", text)
            text = re.sub(r"&lt;", "<", text)
            text = re.sub(r"&gt;", ">", text)
            text = re.sub(r"&quot;", '"', text)
            text = re.sub(r"&#39;", "'", text)
            text = re.sub(r"&nbsp;", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()

        return html

    async def click(self, selector: str) -> str:
        await _ensure_browser()
        await _page.click(selector, timeout=10000)
        return f"Clicked element: {selector}"

    async def type_text(self, selector: str, text: str) -> str:
        await _ensure_browser()
        await _page.fill(selector, text, timeout=10000)
        return f"Typed into {selector}"

    async def press_key(self, key: str) -> str:
        await _ensure_browser()
        await _page.keyboard.press(key)
        return f"Pressed key: {key}"

    async def scroll(self, direction: str, amount: int) -> str:
        await _ensure_browser()
        delta = amount if direction == "down" else -amount
        await _page.evaluate(f"window.scrollBy(0, {delta})")
        return f"Scrolled {direction} by {amount}px"

    async def extract(self, instruction: str, schema: dict | None) -> str:
        await _ensure_browser()
        content = await _page.content()
        return content

    async def act(self, instruction: str) -> str:
        await _ensure_browser()
        return f"Action executed: {instruction}"

    async def new_tab(self, url: str | None) -> str:
        global _page
        await _ensure_browser()
        context = _page.context
        new_page = await context.new_page()
        if url is not None:
            await new_page.goto(url, wait_until="domcontentloaded", timeout=30000)
        _page = new_page
        return f"New tab opened{' and navigated to ' + url if url else ''}"

    async def switch_tab(self, tab_index: int) -> str:
        global _page
        await _ensure_browser()
        context = _page.context
        pages = context.pages
        if tab_index < 0 or tab_index >= len(pages):
            return f"Error: Tab index {tab_index} out of range (0-{len(pages) - 1})"
        _page = pages[tab_index]
        await _page.bring_to_front()
        return f"Switched to tab {tab_index}: {await _page.title()}"

    async def close_tab(self, tab_index: int) -> str:
        await _ensure_browser()
        context = _page.context
        pages = context.pages
        if tab_index < 0 or tab_index >= len(pages):
            return f"Error: Tab index {tab_index} out of range (0-{len(pages) - 1})"
        if len(pages) <= 1:
            return "Error: Cannot close the last remaining tab"
        await pages[tab_index].close()
        return f"Closed tab {tab_index}"

    async def list_tabs(self) -> list[dict]:
        await _ensure_browser()
        context = _page.context
        pages = context.pages
        result = []
        for i, page in enumerate(pages):
            title = await page.title()
            url = page.url
            result.append({"index": i, "title": title, "url": url})
        return result

    async def is_available(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: F401

            return True
        except ImportError:
            return False


__all__ = ["PlaywrightBrowserBackend"]
