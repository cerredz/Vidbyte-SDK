"""Context Protocol Header

Description:
    Pre-built priced fetch tools for the supported page-fetch providers.
Purpose:
    Give agents first-class fetch tools whose calls the runtime prices as fetch
    operations, each declaring its (operation, provider) and deriving its billing
    mode and units (pages / URLs) from the call arguments.
Architecture:
    - Firecrawl/Parallel/Tavily: per-page fetch, units from the pages returned.
    - Browserbase/Linkup: single-page fetch, a mode flag selects the billing rate.
    - DirectHttp: the SDK's own zero-cost HTTP fetcher; performs a live GET.
Relations:
    Subclass PricedOperationTool (this package's base) and are exported through
    vidbyte/tools/builtins/operations/__init__.py.
Similar Files:
    - vidbyte/tools/builtins/operations/search.py
"""

from __future__ import annotations

import asyncio

from vidbyte.lib.dataclasses.operations import FetchPayload
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError, SourceFetchError
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


def _url_list(call: ToolCall) -> list[str]:
    # Resolves the concrete page URLs a fetch call targets, dropping blank entries.
    urls = call.arguments.get("urls")
    if isinstance(urls, (list, tuple)):
        return [str(url) for url in urls if isinstance(url, str) and url.strip()]
    single = call.arguments.get("url")
    return [single] if isinstance(single, str) and single.strip() else []


def _render_fetched_pages(label: str, payload: FetchPayload) -> str:
    # Renders one line per page; page bodies travel in the payload, not the summary.
    lines = [f"{index}. {page.final_url} ({len(page.content)} chars)" for index, page in enumerate(payload.pages, start=1)]
    return f"{label}: {len(payload.pages)} pages.\n" + "\n".join(lines)


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
        # Scrapes every requested page through the injected FirecrawlClient, or prices a stub.
        urls = _url_list(call)
        if not urls:
            return self._failed_result("firecrawl fetch requires a url or urls argument.", units=0, mode="scrape", attempts=0, error="missing_url")
        if self._client is None:
            return self._contract_result("firecrawl scrape", units=len(urls), mode="scrape")
        try:
            payload = await self._client.scrape(urls)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("firecrawl fetch failed.", units=len(urls), mode="scrape", attempts=self._client.max_attempts, error="fetch_failed")
        return self._executed_result(self._render(payload), payload, units=payload.billable_units, mode="scrape", attempts=payload.attempts)

    def _render(self, payload: FetchPayload) -> str:
        # Renders one line per scraped page; page bodies travel in the payload, not the summary.
        return _render_fetched_pages("firecrawl scrape", payload)


class BrowserbaseFetchTool(PricedOperationTool):
    """Browserbase fetch — single-page billing, proxies select the higher rate."""

    operation = "fetch"
    provider = "browserbase"

    def spec(self) -> ToolSpec:
        # Declares the Browserbase fetch tool over a single URL with a proxy flag.
        return ToolSpec(
            name="browserbase_fetch",
            description="Fetches a single web page's content through Browserbase infrastructure.",
            parameters=(
                ToolParameter(name="url", type="string", description="The page URL to fetch.", required=True),
                ToolParameter(name="proxies", type="bool", description="Route through Browserbase proxies at the higher rate.", required=False, default=False),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Fetches the page through the injected BrowserbaseClient, or prices a contract stub.
        url = str(call.arguments.get("url", ""))
        proxies = call.arguments.get("proxies") is True
        mode = "proxy" if proxies else "default"
        if not url.strip():
            return self._failed_result("browserbase fetch requires a url argument.", units=0, mode=mode, attempts=0, error="missing_url")
        if self._client is None:
            return self._contract_result("browserbase fetch", units=1, mode=mode)
        try:
            payload = await self._client.fetch(url, proxies=proxies)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("browserbase fetch failed.", units=1, mode=mode, attempts=self._client.max_attempts, error="fetch_failed")
        return self._executed_result(_render_fetched_pages("browserbase fetch", payload), payload, units=payload.billable_units, mode=mode, attempts=payload.attempts)


class ParallelExtractTool(PricedOperationTool):
    """Parallel extract — per-page billing."""

    operation = "fetch"
    provider = "parallel"

    def spec(self) -> ToolSpec:
        # Declares the Parallel extract tool over a list of URLs.
        return ToolSpec(
            name="parallel_extract",
            description="Extracts LLM-ready content from web pages via the Parallel Extract API.",
            parameters=(
                ToolParameter(name="urls", type="array", description="Page URLs to extract (max 20).", required=True),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Extracts every requested page through the injected ParallelClient, or prices a stub.
        urls = _url_list(call)
        if not urls:
            return self._failed_result("parallel extract requires a urls argument.", units=0, mode="default", attempts=0, error="missing_url")
        if self._client is None:
            return self._contract_result("parallel extract", units=len(urls))
        try:
            payload = await self._client.extract(urls)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("parallel extract failed.", units=len(urls), mode="default", attempts=self._client.max_attempts, error="fetch_failed")
        return self._executed_result(_render_fetched_pages("parallel extract", payload), payload, units=payload.billable_units, mode="default", attempts=payload.attempts)


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
        # Extracts every requested page through the injected TavilyClient, or prices a stub.
        urls = _url_list(call)
        depth = call.arguments.get("extract_depth")
        mode = depth if depth in ("basic", "advanced") else "basic"
        if not urls:
            return self._failed_result("tavily extract requires a urls argument.", units=0, mode=mode, attempts=0, error="missing_url")
        if self._client is None:
            return self._contract_result("tavily extract", units=len(urls), mode=mode)
        try:
            payload = await self._client.extract(urls, extract_depth=mode)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("tavily extract failed.", units=len(urls), mode=mode, attempts=self._client.max_attempts, error="fetch_failed")
        return self._executed_result(_render_fetched_pages("tavily extract", payload), payload, units=payload.billable_units, mode=mode, attempts=payload.attempts)


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
    "BrowserbaseFetchTool",
    "DirectHttpFetchTool",
    "FirecrawlFetchTool",
    "LinkupFetchTool",
    "ParallelExtractTool",
    "TavilyExtractTool",
]
