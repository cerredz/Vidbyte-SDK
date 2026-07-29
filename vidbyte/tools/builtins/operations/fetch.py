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

from vidbyte.lib.dataclasses.operations import FetchPayload
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError, SourceFetchError
from vidbyte.tools.builtins.operations.api import ProviderApiTool
from vidbyte.tools.builtins.operations.base import PricedOperationTool
from vidbyte.tools.types import ToolCall, ToolParameter, ToolResult, ToolSpec


def _urls_count(call: ToolCall) -> int:
    # Counts the pages a fetch call targets, from a urls list or a single url.
    urls = call.arguments.get("urls")
    if isinstance(urls, (list, tuple)):
        return len(urls)
    return 1 if call.arguments.get("url") else 0


def _url_list(call: ToolCall) -> list[str]:
    # Resolves the concrete page URLs a fetch call targets, dropping blank entries.
    urls = call.arguments.get("urls")
    if isinstance(urls, (list, tuple)):
        return [str(url) for url in urls if isinstance(url, str) and url.strip()]
    single = call.arguments.get("url")
    return [single] if isinstance(single, str) and single.strip() else []


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
        lines = [f"{index}. {page.final_url} ({len(page.content)} chars)" for index, page in enumerate(payload.pages, start=1)]
        return f"firecrawl scrape: {len(payload.pages)} pages.\n" + "\n".join(lines)


class BrowserbaseFetchTool(PricedOperationTool):
    """Browserbase raw page fetch with optional proxy billing."""

    operation = "fetch"
    provider = "browserbase"

    def spec(self) -> ToolSpec:
        # Declares Browserbase Fetch's URL, redirect, SSL, and proxy controls.
        return ToolSpec(name="browserbase_fetch", description="Fetches or extracts a web page through Browserbase infrastructure without requiring a browser session.", parameters=(ToolParameter("url", "string", "Page URL to fetch."), ToolParameter("proxies", "bool", "Use Browserbase proxies; this selects a higher pricebook mode.", required=False, default=False), ToolParameter("extract", "bool", "Return Browserbase Extract output.", required=False, default=False), ToolParameter("allow_redirects", "bool", "Follow redirects.", required=False, default=True), ToolParameter("allow_insecure_ssl", "bool", "Allow insecure TLS certificates.", required=False, default=False)))

    async def execute(self, call: ToolCall) -> ToolResult:
        # Runs Browserbase Fetch through the injected client and records proxy mode.
        url = str(call.arguments.get("url", ""))
        proxies = call.arguments.get("proxies") is True
        extract = call.arguments.get("extract") is True
        mode = "proxy" if proxies else "default"
        operation = "extract" if extract else "fetch"
        if self._client is None:
            return self._contract_result("browserbase fetch", units=1, mode=mode)
        try:
            payload = await self._client.fetch(url, proxies=proxies, extract=extract, allow_redirects=call.arguments.get("allow_redirects") is not False, allow_insecure_ssl=call.arguments.get("allow_insecure_ssl") is True)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result(f"browserbase {operation} failed.", units=1, mode=mode, attempts=self._client.max_attempts, error="fetch_failed", operation=operation)
        return self._executed_result(self._render(payload), payload, units=1, mode=mode, attempts=payload.attempts)

    def _render(self, payload: FetchPayload) -> str:
        # Renders page identities and sizes while the bounded content stays in payload metadata.
        lines = [f"{index}. {page.final_url} ({len(page.content)} chars)" for index, page in enumerate(payload.pages, start=1)]
        return f"browserbase fetch: {len(payload.pages)} pages.\n" + "\n".join(lines)


class ExaContentsTool(ProviderApiTool):
    """Retrieve Exa page contents, highlights, and summaries."""

    operation = "fetch"
    provider = "exa"
    tool_name = "exa_contents"
    description = "Retrieves known URLs from Exa with markdown text, summaries, highlights, and livecrawl controls."
    charge_operation = None
    parameters = (ToolParameter("urls", "array", "Known URLs to retrieve."), ToolParameter("text", "object", "Text retrieval options or true.", required=False, default=True), ToolParameter("summary", "object", "Optional summary options.", required=False), ToolParameter("highlights", "object", "Optional highlight options.", required=False), ToolParameter("livecrawl", "string", "Optional livecrawl policy.", required=False))

    async def _request(self, call: ToolCall):
        # Retrieves Exa contents through the provider client so page and summary meters are explicit.
        urls = call.arguments.get("urls", ())
        if not isinstance(urls, (list, tuple)):
            urls = ()
        return await self._client.contents(urls, text=call.arguments.get("text", True), summary=call.arguments.get("summary"), highlights=call.arguments.get("highlights"), livecrawl=call.arguments.get("livecrawl"))


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
        # Runs Parallel Extract and prices each requested URL through the provider client.
        urls = call.arguments.get("urls", ())
        if not isinstance(urls, (list, tuple)):
            urls = ()
        if self._client is None:
            return self._contract_result("parallel extract", units=len(urls))
        try:
            payload = await self._client.extract(urls)
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("parallel extract failed.", units=len(urls), mode="default", attempts=self._client.max_attempts, error="fetch_failed")
        return self._payload_result("parallel extract completed.", payload)


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
                ToolParameter(name="format", type="string", description="Output format: markdown or text.", required=False, default="markdown"),
            ),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        # Runs Tavily Extract and bills only successful URL extractions.
        urls = call.arguments.get("urls", ())
        if not isinstance(urls, (list, tuple)):
            urls = ()
        depth = call.arguments.get("extract_depth")
        mode = depth if depth in ("basic", "advanced") else "basic"
        if self._client is None:
            return self._contract_result("tavily extract", units=len(urls), mode=mode)
        try:
            payload = await self._client.extract(urls, extract_depth=mode, format=str(call.arguments.get("format", "markdown")))
        except (ProviderRequestError, ProviderResponseError):
            return self._failed_result("tavily extract failed.", units=len(urls), mode=mode, attempts=self._client.max_attempts, error="fetch_failed")
        return self._payload_result("tavily extract completed.", payload)


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
    "BrowserbaseFetchTool",
    "ExaContentsTool",
    "FirecrawlFetchTool",
    "LinkupFetchTool",
    "ParallelExtractTool",
    "TavilyExtractTool",
]
