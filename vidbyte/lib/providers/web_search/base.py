"""Context Protocol Header

Description:
    Defines the abstract base class and data transfer object for web search backends.
Purpose:
    Provides a typed contract that all web search provider backends must implement,
    along with the shared SearchResult dataclass.
Architecture:
    - SearchResult: Lightweight frozen dataclass for search hits.
    - BaseWebSearchBackend: ABC requiring search() and is_available().
Relations:
    Related to vidbyte.lib.providers.web_search and vidbyte.tools.builtins.web_search.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class BaseWebSearchBackend(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


__all__ = [
    "BaseWebSearchBackend",
    "SearchResult",
]
