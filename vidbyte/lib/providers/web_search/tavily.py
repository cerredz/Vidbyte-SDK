"""Context Protocol Header

Description:
    Implements a web search backend using the Tavily search API.
Purpose:
    Provides API-key-authenticated web search via Tavily for high-quality
    real-time search results.
Architecture:
    - TavilyWebSearchBackend: Uses HttpTransport for POST to Tavily API.
    - Reads TAVILY_API_KEY from os.environ.
Relations:
    Related to vidbyte.lib.providers.web_search.base and vidbyte.lib.http.transport.
"""

from __future__ import annotations

import json
import logging
import os

from vidbyte.lib.http.transport import HttpTransport
from vidbyte.lib.providers.web_search.base import BaseWebSearchBackend, SearchResult

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


class TavilyWebSearchBackend(BaseWebSearchBackend):
    def __init__(self) -> None:
        self._transport = HttpTransport()

    def _api_key(self) -> str | None:
        return os.environ.get("TAVILY_API_KEY")

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        api_key = self._api_key()
        if not api_key:
            logger.warning("Tavily search skipped: TAVILY_API_KEY not set")
            return []

        try:
            response = self._transport.request(
                method="POST",
                url=TAVILY_API_URL,
                headers={},
                json_body={
                    "query": query,
                    "max_results": max_results,
                    "api_key": api_key,
                },
            )
        except Exception:
            logger.exception("Tavily search request failed for query: %s", query)
            return []

        if response.status_code != 200:
            logger.warning("Tavily returned status %s", response.status_code)
            return []

        try:
            data = json.loads(response.body)
        except json.JSONDecodeError:
            logger.warning("Tavily returned non-JSON response")
            return []

        results = data.get("results", [])
        if not isinstance(results, list):
            return []

        return [
            SearchResult(
                title=str(r.get("title", "")),
                url=str(r.get("url", "")),
                snippet=str(r.get("content", "")),
            )
            for r in results
        ]

    async def is_available(self) -> bool:
        return bool(self._api_key())


__all__ = [
    "TavilyWebSearchBackend",
]
