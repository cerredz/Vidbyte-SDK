"""Context Protocol Header

Description:
    Tavily API client for search, extraction, mapping, crawling, and research.
Purpose:
    Centralizes Tavily credit dimensions and endpoint request shapes while keeping
    provider-specific controls available to typed SDK tools.
Architecture:
    TavilyClient extends WebOperationClient and returns normalized search or generic
    operation payloads with credit-based pricebook charges.
Relations:
    Consumed by Tavily tools and priced through OperationPricingRegistry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.lib.dataclasses.operations import OperationCharge, ProviderOperationPayload, SearchHit, SearchPayload
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient


class TavilyClient(WebOperationClient):
    """Credentialed Tavily Search, Extract, Map, Crawl, and Research client."""

    def __init__(self, api_key: str, *, project_id: str | None = None, base_url: str = "https://api.tavily.com", timeout_seconds: float = 120.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, transport: Any = None) -> None:
        # Configures Tavily's API host, optional project attribution, and request policy.
        super().__init__(api_key, provider="tavily", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)
        self._project_id = project_id

    def request_headers(self) -> dict[str, str]:
        # Builds Tavily bearer and optional project headers for every endpoint.
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        if self._project_id:
            headers["X-Project-ID"] = self._project_id
        return headers

    async def search(self, query: str, *, search_depth: str = "basic", max_results: int = 5, topic: str = "general", include_answer: bool = False, include_raw_content: bool = False) -> SearchPayload:
        # Runs Tavily search with depth, topic, filtering, answer, and content controls.
        depth = search_depth if search_depth in {"basic", "advanced", "fast", "ultra-fast"} else "basic"
        body = {"query": query, "search_depth": depth, "max_results": min(max(1, max_results), 20), "topic": topic, "include_answer": include_answer, "include_raw_content": include_raw_content}
        credits = 2 if depth == "advanced" else 1
        charge = OperationCharge("search", self.provider, mode=depth, meter="credit", units=credits)
        payload = await self.request_operation("search", "POST", path="search", headers=self.request_headers(), json_body=body, charges=(charge,))
        return self._search_payload(query, payload)

    async def extract(self, urls: Sequence[str], *, extract_depth: str = "basic", format: str = "markdown", include_images: bool = False, include_favicon: bool = False) -> ProviderOperationPayload:
        # Extracts bounded content from known URLs using Tavily's success-based credit meter.
        body = {"urls": [url for url in urls if isinstance(url, str) and url.strip()], "extract_depth": extract_depth, "format": format, "include_images": include_images, "include_favicon": include_favicon}
        payload = await self.request_operation("fetch", "POST", path="extract", headers=self.request_headers(), json_body=body, charges=())
        successes = self._successful_count(payload.data)
        mode = "advanced" if extract_depth == "advanced" else "basic"
        return replace(payload, charges=(OperationCharge("fetch", self.provider, mode=mode, meter="successful_url", units=successes),))

    async def map(self, url: str, *, instructions: str | None = None, max_depth: int = 1, max_breadth: int = 20, limit: int = 50) -> ProviderOperationPayload:
        # Maps a site's link graph with explicit depth, breadth, and page limits.
        body: dict[str, object] = {"url": url, "max_depth": min(max(1, max_depth), 5), "max_breadth": min(max(1, max_breadth), 500), "limit": max(1, limit)}
        if instructions:
            body["instructions"] = instructions
        mode = "instructions" if instructions else "default"
        payload = await self.request_operation("map", "POST", path="map", headers=self.request_headers(), json_body=body, charges=())
        pages = self._result_count(payload.data)
        return replace(payload, charges=(OperationCharge("map", self.provider, mode=mode, meter="successful_page", units=pages),))

    async def crawl(self, url: str, *, instructions: str | None = None, max_depth: int = 1, max_breadth: int = 20, limit: int = 50, extract_depth: str = "basic", format: str = "markdown") -> ProviderOperationPayload:
        # Crawls and extracts a site while preserving separate map and extraction charges.
        body: dict[str, object] = {"url": url, "max_depth": min(max(1, max_depth), 5), "max_breadth": min(max(1, max_breadth), 500), "limit": max(1, limit), "extract_depth": extract_depth, "format": format}
        if instructions:
            body["instructions"] = instructions
        payload = await self.request_operation("crawl", "POST", path="crawl", headers=self.request_headers(), json_body=body, charges=())
        pages = self._result_count(payload.data)
        map_mode = "instructions" if instructions else "default"
        extract_mode = "advanced" if extract_depth == "advanced" else "basic"
        charges = (OperationCharge("map", self.provider, mode=map_mode, meter="successful_page", units=pages), OperationCharge("fetch", self.provider, mode=extract_mode, meter="successful_url", units=pages))
        return replace(payload, charges=charges)

    async def research(self, input: str, *, model: str = "mini", output_schema: Mapping[str, object] | None = None, stream: bool = False) -> ProviderOperationPayload:
        # Starts Tavily research and prices the provider-reported credit quantity through the pricebook.
        body: dict[str, object] = {"input": input, "model": model, "stream": stream}
        if output_schema is not None:
            body["output_schema"] = dict(output_schema)
        payload = await self.request_operation("research", "POST", path="research", headers=self.request_headers(), json_body=body, charges=())
        credits = self._credit_count(payload.provider_usage) or 1
        return replace(payload, charges=(OperationCharge("research", self.provider, meter="credit", units=credits),))

    async def api(self, operation: str, *, method: str, path: str, body: Mapping[str, object] | None = None, charges: tuple[OperationCharge, ...] = ()) -> ProviderOperationPayload:
        # Sends a documented Tavily endpoint request for project and lifecycle extensions.
        return await self.request_operation(operation, method, path=path, headers=self.request_headers(), json_body=body, charges=charges)

    def _search_payload(self, query: str, payload: ProviderOperationPayload) -> SearchPayload:
        # Converts Tavily result records into provider-neutral search hits.
        raw_results = payload.data.get("results", ())
        hits = tuple(self._search_hit(item) for item in raw_results if isinstance(item, Mapping))
        return SearchPayload(provider=self.provider, query=query, hits=tuple(hit for hit in hits if hit is not None), attempts=payload.attempts, billable_units=1, request_id=payload.request_id, charges=payload.charges, provider_usage=payload.provider_usage)

    @staticmethod
    def _search_hit(item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes a Tavily result while dropping entries without source URLs.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        return SearchHit(title=str(item.get("title") or url), url=url, snippet=str(item.get("content") or "")[:500] or None, raw=item)

    @staticmethod
    def _successful_count(data: Mapping[str, Any]) -> int:
        # Counts successful extraction records without billing failed URLs.
        results = data.get("results")
        return sum(1 for item in results if isinstance(item, Mapping) and not item.get("error")) if isinstance(results, Sequence) and not isinstance(results, (str, bytes)) else 0

    @staticmethod
    def _result_count(data: Mapping[str, Any]) -> int:
        # Counts mapped or crawled pages returned by the provider.
        for key in ("results", "pages"):
            value = data.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return len(value)
        return 0

    @staticmethod
    def _credit_count(usage: Mapping[str, Any]) -> int:
        # Reads Tavily's credit counter when the research response supplies one.
        for key in ("credits", "credit_count", "api_credits"):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
        return 0


__all__ = ["TavilyClient"]
