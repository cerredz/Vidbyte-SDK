"""Context Protocol Header

Description:
    Re-exports web search backend implementations.
Purpose:
    Provides a stable import surface for web search provider backends without
    exposing internal implementation details.
Architecture:
    - BaseWebSearchBackend: Abstract contract.
    - DuckDuckGoBackend: Zero-config fallback using duckduckgo_search.
    - TavilyWebSearchBackend: API-key-backed search via Tavily.
    - BraveWebSearchBackend: API-key-backed search via Brave.
    - AutoWebSearchBackend: Cascading auto-selector.
    - SearchResult: Data transfer object for search hits.
Relations:
    Related to vidbyte.tools.builtins.web_search.
"""

from __future__ import annotations

from vidbyte.lib.providers.web_search.auto import AutoWebSearchBackend
from vidbyte.lib.providers.web_search.base import BaseWebSearchBackend, SearchResult
from vidbyte.lib.providers.web_search.brave import BraveWebSearchBackend
from vidbyte.lib.providers.web_search.duckduckgo import DuckDuckGoBackend
from vidbyte.lib.providers.web_search.tavily import TavilyWebSearchBackend

__all__ = [
    "AutoWebSearchBackend",
    "BaseWebSearchBackend",
    "BraveWebSearchBackend",
    "DuckDuckGoBackend",
    "SearchResult",
    "TavilyWebSearchBackend",
]
