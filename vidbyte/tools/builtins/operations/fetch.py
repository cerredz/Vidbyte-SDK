"""Context Protocol Header

Description:
    Pre-built priced fetch tools for the supported page-fetch providers.
Purpose:
    Give agents first-class fetch tools whose calls the runtime prices as fetch
    operations, each declaring its (operation, provider) and deriving its billing
    mode and units (pages / URLs) from the call arguments.
Architecture:
    - Firecrawl/Parallel/Tavily: per-URL (page) fetch, units from the URL count.
    - Linkup: single-page fetch, JS vs no-JS selects the billing mode.
    - DirectHttp: the SDK's own zero-cost HTTP fetcher; performs a live GET.
Relations:
    Subclass PricedOperationTool (this package's base) and are exported through
    vidbyte/tools/builtins/operations/__init__.py.
Similar Files:
    - vidbyte/tools/builtins/operations/search.py
"""

from __future__ import annotations

import asyncio

from vidbyte.lib.errors import SourceFetchError
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


def _urls_count(call: ToolCall) -> int:
    # Counts the pages a fetch call targets, from a urls list or a single url.
    urls = call.arguments.get("urls")
    if isinstance(urls, (list, tuple)):
        return len(urls)
    return 1 if call.arguments.get("url") else 0


class FirecrawlFetchTool(PricedOperationTool):
    """Firecrawl scrape — per-page billing."""

    operation = "fetch"
    provider = "firecrawl"

    def spec(self) -> ToolSpec:
        # Declares the Firecrawl scrape tool over one or many URLs.
        return ToolSpec(
            name="firecrawl_fetch",
            description="Scrapes one or more web pages into clean markdown via Firecrawl.",
            parameters=(
                ToolParameter(name="url", type="string", description="A single page URL to scrape.", required=False),
                ToolParameter(name="urls", type="array", description="Multiple page URLs to scrape.", required=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Prices one Firecrawl scrape by the number of pages fetched.
        return self._contract_result("firecrawl scrape", units=_urls_count(call), mode="scrape")


class ParallelExtractTool(PricedOperationTool):
    """Parallel extract — per-URL billing."""

    operation = "fetch"
    provider = "parallel"

    def spec(self) -> ToolSpec:
        # Declares the Parallel extract tool over a list of URLs.
        return ToolSpec(
            name="parallel_extract",
            description="Extracts LLM-ready content from web pages via the Parallel Extract API.",
            parameters=(
                ToolParameter(name="urls", type="array", description="Page URLs to extract.", required=True),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Prices one Parallel extract by the number of URLs.
        return self._contract_result("parallel extract", units=_urls_count(call))


class TavilyExtractTool(PricedOperationTool):
    """Tavily extract — per-URL billing at a depth tier, billed per 5-URL batch."""

    operation = "fetch"
    provider = "tavily"

    def spec(self) -> ToolSpec:
        # Declares the Tavily extract tool over a list of URLs with an extract depth.
        return ToolSpec(
            name="tavily_extract",
            description="Extracts cleaned content from web pages via Tavily.",
            parameters=(
                ToolParameter(name="urls", type="array", description="Page URLs to extract.", required=True),
                ToolParameter(name="extract_depth", type="string", description="Extract depth: 'basic' or 'advanced'.", required=False, default="basic"),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Prices one Tavily extract by URL count at the basic/advanced tier.
        depth = call.arguments.get("extract_depth")
        mode = depth if depth in ("basic", "advanced") else "basic"
        return self._contract_result("tavily extract", units=_urls_count(call), mode=mode)


class LinkupFetchTool(PricedOperationTool):
    """Linkup fetch — single-page fetch, JS vs no-JS selects the billing mode."""

    operation = "fetch"
    provider = "linkup"

    def spec(self) -> ToolSpec:
        # Declares the Linkup fetch tool over a single URL with a JS-render flag.
        return ToolSpec(
            name="linkup_fetch",
            description="Fetches a single web page's content via Linkup.",
            parameters=(
                ToolParameter(name="url", type="string", description="The page URL to fetch.", required=True),
                ToolParameter(name="render_js", type="bool", description="Render JavaScript before extraction.", required=False, default=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Prices one Linkup fetch at the js/nojs rate for a single page.
        mode = "js" if call.arguments.get("render_js") is True else "nojs"
        return self._contract_result("linkup fetch", units=1, mode=mode)


class DirectHttpFetchTool(PricedOperationTool):
    """Direct HTTP fetch — the SDK's own zero-cost fetcher; performs a live GET."""

    operation = "fetch"
    provider = "direct_http"

    def spec(self) -> ToolSpec:
        # Declares the direct HTTP fetch tool over a single URL.
        return ToolSpec(
            name="direct_http_fetch",
            description="Fetches a single URL over plain HTTP with no third-party provider cost.",
            parameters=(
                ToolParameter(name="url", type="string", description="The URL to fetch.", required=True),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Fetches the URL with the built-in HttpFetcher and prices it at zero.
        url = str(call.arguments.get("url", ""))
        try:
            body = await asyncio.to_thread(self._fetch_body, url)
        except SourceFetchError as exc:
            return ToolResult.error(self.name, f"direct_http fetch failed: {exc}", metadata={"error": "fetch_failed", "url": url})
        return self._contract_result(body, units=1)

    def _fetch_body(self, url: str) -> str:
        # Performs the blocking GET and returns decoded page text.
        from vidbyte.sources.fetches.http import HttpFetcher

        response = HttpFetcher().fetch(url)
        return response.body_bytes.decode("utf-8", errors="replace")


__all__ = [
    "DirectHttpFetchTool",
    "FirecrawlFetchTool",
    "LinkupFetchTool",
    "ParallelExtractTool",
    "TavilyExtractTool",
]
