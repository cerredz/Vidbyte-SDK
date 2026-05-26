"""Context Protocol Header

Description:
    Implements an auto-selecting web search backend that cascades through providers.
Purpose:
    Provides a zero-configuration search experience by trying premium API-key
    backends first and falling back to DuckDuckGo.
Architecture:
    - AutoWebSearchBackend: Tries Tavily → Brave → DuckDuckGo.
    - Each provider checked via is_available() and exception-handled.
Relations:
    Related to vidbyte.lib.providers.web_search and vidbyte.tools.builtins.web_search.
"""

from __future__ import annotations

import logging

from vidbyte.lib.providers.web_search.base import BaseWebSearchBackend, SearchResult
from vidbyte.lib.providers.web_search.brave import BraveWebSearchBackend
from vidbyte.lib.providers.web_search.duckduckgo import DuckDuckGoBackend
from vidbyte.lib.providers.web_search.tavily import TavilyWebSearchBackend

logger = logging.getLogger(__name__)


class AutoWebSearchBackend(BaseWebSearchBackend):
    def __init__(self) -> None:
        self._tavily = TavilyWebSearchBackend()
        self._brave = BraveWebSearchBackend()
        self._duckduckgo = DuckDuckGoBackend()

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if await self._tavily.is_available():
            try:
                results = await self._tavily.search(query, max_results)
                if results:
                    return results
            except Exception:
                logger.exception("Tavily search failed, trying next provider")

        if await self._brave.is_available():
            try:
                results = await self._brave.search(query, max_results)
                if results:
                    return results
            except Exception:
                logger.exception("Brave search failed, trying next provider")

        try:
            return await self._duckduckgo.search(query, max_results)
        except Exception:
            logger.exception("DuckDuckGo search failed")
            return []

    async def is_available(self) -> bool:
        return (
            await self._tavily.is_available()
            or await self._brave.is_available()
            or await self._duckduckgo.is_available()
        )


__all__ = [
    "AutoWebSearchBackend",
]
