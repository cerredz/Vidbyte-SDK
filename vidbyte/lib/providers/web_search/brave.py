"""Context Protocol Header

Description:
    Implements a web search backend using the Brave search API.
Purpose:
    Provides API-key-authenticated web search via Brave for privacy-respecting
    search results.
Architecture:
    - BraveWebSearchBackend: Uses HttpTransport for GET to Brave API.
    - Reads BRAVE_API_KEY from os.environ.
Relations:
    Related to vidbyte.lib.providers.web_search.base and vidbyte.lib.http.transport.
"""

from __future__ import annotations

import json
import logging
import os
from urllib.parse import quote

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.lib.providers.web_search.base import BaseWebSearchBackend, SearchResult

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveWebSearchBackend(BaseWebSearchBackend):
    def __init__(self) -> None:
        self._transport = HttpTransport()

    def _api_key(self) -> str | None:
        return os.environ.get("BRAVE_API_KEY")

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        api_key = self._api_key()
        if not api_key:
            logger.warning("Brave search skipped: BRAVE_API_KEY not set")
            return []

        encoded_query = quote(query)
        url = f"{BRAVE_SEARCH_URL}?q={encoded_query}&count={max_results}"

        try:
            response = self._transport.request(
                method="GET",
                url=url,
                headers={
                    "X-Subscription-Token": api_key,
                    "Accept": "application/json",
                },
            )
        except Exception:
            logger.exception("Brave search request failed for query: %s", query)
            return []

        if response.status_code != 200:
            logger.warning("Brave returned status %s", response.status_code)
            return []

        try:
            data = json.loads(response.body)
        except json.JSONDecodeError:
            logger.warning("Brave returned non-JSON response")
            return []

        web = data.get("web", {})
        results = web.get("results", []) if isinstance(web, dict) else []
        if not isinstance(results, list):
            return []

        return [
            SearchResult(
                title=str(r.get("title", "")),
                url=str(r.get("url", "")),
                snippet=str(r.get("description", "")),
            )
            for r in results
        ]

    async def is_available(self) -> bool:
        return bool(self._api_key())


__all__ = [
    "BraveWebSearchBackend",
]
