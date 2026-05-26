"""Context Protocol Header

Description:
    Implements a web search backend using DuckDuckGo's instant answer API.
Purpose:
    Provides a zero-configuration web search fallback that works without any
    API keys or authentication.
Architecture:
    - DuckDuckGoBackend: Uses the duckduckgo_search library to perform text searches.
    - Handles import errors gracefully when the optional dependency is missing.
Relations:
    Related to vidbyte.lib.providers.web_search.base and auto.
"""

from __future__ import annotations

import logging

from vidbyte.lib.providers.web_search.base import BaseWebSearchBackend, SearchResult

logger = logging.getLogger(__name__)


class DuckDuckGoBackend(BaseWebSearchBackend):
    def __init__(self) -> None:
        self._ddgs = None
        self._import_error: str | None = None
        try:
            from duckduckgo_search import DDGS

            self._ddgs = DDGS
        except ImportError as exc:
            self._import_error = str(exc)

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if self._ddgs is None:
            logger.warning(
                "DuckDuckGo backend unavailable: duckduckgo_search not installed (%s)",
                self._import_error or "unknown error",
            )
            return []

        try:
            ddgs = self._ddgs()
            results = ddgs.text(query, max_results=max_results)
        except Exception:
            logger.exception("DuckDuckGo search failed for query: %s", query)
            return []

        return [
            SearchResult(
                title=str(r.get("title", "")),
                url=str(r.get("href", "")),
                snippet=str(r.get("body", "")),
            )
            for r in results
        ]

    async def is_available(self) -> bool:
        return self._ddgs is not None


__all__ = [
    "DuckDuckGoBackend",
]
