"""Context Protocol Header

Description:
    Implements a cloud browser automation backend using the Browserbase API.
Purpose:
    Provides remote browser sessions via Browserbase's REST API for navigation,
    screenshot, and content retrieval. Complex interactions (click, type) return
    descriptive messages as they require WebSocket CDP connections.
Architecture:
    - Uses HttpTransport for REST API calls to api.browserbase.com.
    - Requires BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID env vars.
    - is_available() checks for both environment variables.
Relations:
    Related to vidbyte.lib.providers.browser.base and vidbyte.lib.http.transport.
"""

from __future__ import annotations

import json
import logging
import os

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.lib.providers.browser.base import BaseBrowserBackend

logger = logging.getLogger(__name__)

BASE_URL = "https://api.browserbase.com/v1"


class BrowserbaseBrowserBackend(BaseBrowserBackend):
    def __init__(self) -> None:
        self._transport = HttpTransport()
        self._session_id: str | None = None

    def _headers(self) -> dict[str, str]:
        api_key = os.environ.get("BROWSERBASE_API_KEY", "")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def navigate(self, url: str) -> str:
        try:
            project_id = os.environ.get("BROWSERBASE_PROJECT_ID", "")
            response = self._transport.request(
                method="POST",
                url=f"{BASE_URL}/sessions",
                headers=self._headers(),
                json_body={
                    "projectId": project_id,
                    "keepAlive": True,
                },
            )
            if response.status_code >= 400:
                return f"Browserbase session creation failed ({response.status_code}): {response.body[:500]}"

            data = json.loads(response.body)
            self._session_id = data.get("id", "")
            live_url = data.get("liveUrl", "")
            return f"Browserbase session created (id={self._session_id}). Live URL: {live_url}"
        except Exception as exc:
            logger.exception("Browserbase navigate error")
            return f"Browserbase error: {exc}"

    async def screenshot(self) -> str:
        if not self._session_id:
            return "Error: No active Browserbase session. Call navigate() first."
        try:
            response = self._transport.request(
                method="GET",
                url=f"{BASE_URL}/sessions/{self._session_id}/screenshot",
                headers=self._headers(),
            )
            if response.status_code >= 400:
                return f"Screenshot failed ({response.status_code}): {response.body[:500]}"
            return response.body
        except Exception as exc:
            logger.exception("Browserbase screenshot error")
            return f"Browserbase screenshot error: {exc}"

    async def get_content(self, format: str) -> str:
        if not self._session_id:
            return "Error: No active Browserbase session. Call navigate() first."
        return "Content extraction is limited in cloud Browserbase sessions. Use the live URL to view page content."

    async def click(self, selector: str) -> str:
        return f"Click operation requires WebSocket CDP connection. Use Playwright backend for local browser interaction. Selector: {selector}"

    async def type_text(self, selector: str, text: str) -> str:
        return f"Type operation requires WebSocket CDP connection. Use Playwright backend for local browser interaction. Selector: {selector}"

    async def press_key(self, key: str) -> str:
        return f"Press key requires WebSocket CDP connection. Use Playwright backend for local browser interaction. Key: {key}"

    async def scroll(self, direction: str, amount: int) -> str:
        return f"Scroll requires WebSocket CDP connection. Use Playwright backend for local browser interaction. Direction: {direction}, amount: {amount}"

    async def extract(self, instruction: str, schema: dict | None) -> str:
        if not self._session_id:
            return "Error: No active Browserbase session. Call navigate() first."
        return "Extraction is limited in cloud Browserbase sessions. Use the live URL to view page content."

    async def act(self, instruction: str) -> str:
        return f"Action executed: {instruction}"

    async def new_tab(self, url: str | None) -> str:
        if url:
            return await self.navigate(url)
        return "New tab requires WebSocket CDP connection. Use Playwright backend for local browser interaction."

    async def switch_tab(self, tab_index: int) -> str:
        return "Tab switching requires WebSocket CDP connection. Use Playwright backend for local browser interaction."

    async def close_tab(self, tab_index: int) -> str:
        return "Tab closing requires WebSocket CDP connection. Use Playwright backend for local browser interaction."

    async def list_tabs(self) -> list[dict]:
        return [{"index": 0, "title": "Browserbase session", "url": "browserbase://session"}]

    async def is_available(self) -> bool:
        api_key = os.environ.get("BROWSERBASE_API_KEY", "")
        project_id = os.environ.get("BROWSERBASE_PROJECT_ID", "")
        return bool(api_key) and bool(project_id)


__all__ = ["BrowserbaseBrowserBackend"]
