"""FILE: vidbyte/agents/jev/documentation/search.py

PURPOSE: Binds the chosen web search provider to a real priced search tool, and records every URL that search returns during one lookup.
ROLE IN CODEBASE: JevDocumentation builds its single tool with build_search_tool() and its single middleware SearchHitRecorder; agent.py binds a SearchHits collector around each search run.
ARCHITECTURE NOTE: The provider table is the only place that maps a JevDocumentationProvider to a tool, a client, and an API key variable. The recorder reads the typed SearchPayload that priced search tools attach to their results, so link verification never parses rendered text.
COMMON MODIFICATION PATTERNS: Support a new provider by adding its enum member and one table row, using an existing priced search tool whose client takes the API key first.
KNOWN EDGE CASES: Without an API key no tool is built, because a priced tool without a client returns a contract stub instead of search results. Hits recorded outside a bound lookup are dropped.
RELATED DOCS: docs/design/jev-documentation.md and vidbyte/tools/builtins/operations/search.py.
TESTS: tests/test_jev_documentation.py.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from vidbyte.lib.dataclasses.middleware import MiddlewareContext, MiddlewareDecision
from vidbyte.lib.dataclasses.operations import SearchPayload
from vidbyte.lib.enums import JevDocumentationProvider
from vidbyte.middleware.base import AgentMiddleware
from vidbyte.tools.builtins.operations import (
    BraveClient,
    BraveSearchTool,
    ExaClient,
    ExaSearchTool,
    ParallelClient,
    ParallelSearchTool,
    PricedOperationTool,
    TavilyClient,
    TavilySearchTool,
    WebOperationClient,
)

# The metadata key priced operation tools use for their typed payload.
_PAYLOAD_KEY = "operation_payload"


@dataclass(frozen=True, slots=True)
class _ProviderBinding:
    """How one documentation search provider becomes an executing search tool."""

    api_key_env: str
    client: Callable[[str], WebOperationClient]
    tool: Callable[..., PricedOperationTool]


_PROVIDERS: dict[JevDocumentationProvider, _ProviderBinding] = {
    JevDocumentationProvider.EXA: _ProviderBinding("EXA_API_KEY", ExaClient, ExaSearchTool),
    JevDocumentationProvider.TAVILY: _ProviderBinding("TAVILY_API_KEY", TavilyClient, TavilySearchTool),
    JevDocumentationProvider.BRAVE: _ProviderBinding("BRAVE_API_KEY", BraveClient, BraveSearchTool),
    JevDocumentationProvider.PARALLEL: _ProviderBinding("PARALLEL_API_KEY", ParallelClient, ParallelSearchTool),
}


def search_api_key_env(provider: JevDocumentationProvider) -> str:
    """Return the environment variable that holds the provider's API key."""
    return _PROVIDERS[provider].api_key_env


def build_search_tool(provider: JevDocumentationProvider) -> PricedOperationTool | None:
    """Return the provider's search tool bound to a real client, or None when its API key is not set."""
    # @intent never-search-with-a-contract-stub
    # A priced tool without a client returns a priced stub, not results, so a missing key must mean no tool at all.
    binding = _PROVIDERS[provider]
    api_key = os.environ.get(binding.api_key_env, "").strip()
    if not api_key:
        return None
    return binding.tool(client=binding.client(api_key))


@dataclass(slots=True)
class SearchHits:
    """The URLs search returned during one lookup, in the order they first appeared."""

    urls: dict[str, None] = field(default_factory=dict)

    def add(self, payload: SearchPayload) -> None:
        """Record every hit URL in one search payload."""
        for hit in payload.hits:
            self.urls.setdefault(hit.url, None)


_ACTIVE_HITS: ContextVar[SearchHits | None] = ContextVar("jev_documentation_active_hits", default=None)


@contextmanager
def bind_search_hits(hits: SearchHits) -> Iterator[None]:
    """Bind the collector the recorder writes to for the duration of one search run."""
    token = _ACTIVE_HITS.set(hits)
    try:
        yield
    finally:
        _ACTIVE_HITS.reset(token)


class SearchHitRecorder(AgentMiddleware):
    """Records the URLs in every search result, so only links search really returned can reach the main agent."""

    name = "jev_documentation_search_hits"

    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        """Add the hits of a successful search result to the bound collector."""
        hits = _ACTIVE_HITS.get()
        result = ctx.tool_result
        if hits is not None and result is not None:
            payload = dict(result.metadata).get(_PAYLOAD_KEY)
            if isinstance(payload, SearchPayload):
                hits.add(payload)
        return MiddlewareDecision.continue_()


__all__ = ["SearchHitRecorder", "SearchHits", "bind_search_hits", "build_search_tool", "search_api_key_env"]
