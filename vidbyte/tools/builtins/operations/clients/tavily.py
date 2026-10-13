"""Context Protocol Header

Description:
    Executing client for the Tavily Search and Extract web operations.
Purpose:
    Turns one query into a normalized SearchPayload and a URL batch into a
    normalized FetchPayload, sent at most 20 URLs per request (Tavily's cap),
    counting only successfully extracted pages so the credit-batched extract
    tariff bills what Tavily actually served.
Architecture:
    - TavilyClient: WebOperationClient subclass owning the Tavily endpoints, its
      bearer header, the depth tiers, and vendor result normalization.
Relations:
    Injected into vidbyte.tools.builtins.operations.search.TavilySearchTool and
    fetch.TavilyExtractTool; priced against ("search", "tavily") and
    ("fetch", "tavily") in the operation pricing registry.
Similar Files:
    - vidbyte/tools/builtins/operations/clients/firecrawl.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.operations import FetchedPage, FetchPayload, SearchHit, SearchPayload
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient

_MAX_RESULTS = 20
# Tavily Extract accepts at most this many URLs in one request.
_MAX_URLS = 20
_MAX_SNIPPET_CHARS = 500


class TavilyClient(WebOperationClient):
    """Tavily client returning provider-neutral search hits and extracted page content."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.tavily.com", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, transport: HttpTransport | None = None) -> None:
        # Configures the Tavily endpoints and credential on the shared transport policy.
        super().__init__(api_key, provider="tavily", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)

    async def search(self, query: str, *, max_results: int = 5, search_depth: str = "basic") -> SearchPayload:
        """Run one Tavily search and return normalized hits with billing counts."""
        body = {"query": query, "search_depth": search_depth, "max_results": min(max(1, max_results), _MAX_RESULTS)}
        payload, attempts = await self.request_json("search", "POST", path="search", headers=self._headers(), json_body=body)
        return SearchPayload(provider=self.provider, query=query, hits=self._hits_from_payload(payload), attempts=attempts, billable_units=1)

    async def extract(self, urls: Sequence[str], *, extract_depth: str = "basic") -> FetchPayload:
        """Extract every URL and return the pages Tavily successfully retrieved."""
        pages: list[FetchedPage] = []
        attempts = 1
        # @intent tavily-extract-batches-stay-under-the-cap
        # Tavily's help center: "You can extract content from a single URL or multiple URLs (up to 20) in one
        # request", and a larger request is rejected, so the URLs go out in consecutive slices of at most that many.
        for batch in self._url_batches(urls):
            # Each slice is one ordinary Extract request, built exactly as a single request always was.
            body = {"urls": batch, "extract_depth": extract_depth}
            payload, used = await self.request_json("fetch", "POST", path="extract", headers=self._headers(), json_body=body)
            # Keep the slice's pages in input order, and report the most attempts any one request needed.
            pages.extend(self._pages_from_payload(payload))
            attempts = max(attempts, used)
        # Bill only the pages Tavily actually returned, as before.
        return FetchPayload(provider=self.provider, pages=tuple(pages), attempts=attempts, billable_units=len(pages))

    @staticmethod
    def _url_batches(urls: Sequence[str]) -> list[list[str]]:
        # Consecutive slices of at most the vendor cap; an empty input stays one empty request, as before.
        url_list = list(urls)
        return [url_list[start : start + _MAX_URLS] for start in range(len(url_list))[::_MAX_URLS]] or [url_list]

    def _headers(self) -> dict[str, str]:
        # Builds the Tavily bearer header; the key never leaves this mapping.
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]:
        # Reads the results array, raising when Tavily returns it in an unusable shape.
        results = payload.get("results")
        if results is None:
            return ()
        if not isinstance(results, (list, tuple)):
            raise ProviderResponseError("tavily search returned a non-list results block.", provider=self.provider)
        hits = (self._hit_from_result(item) for item in results if isinstance(item, Mapping))
        return tuple(hit for hit in hits if hit is not None)

    def _hit_from_result(self, item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes one Tavily result, skipping any entry without a usable URL.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        title = item.get("title")
        content = item.get("content")
        return SearchHit(
            title=title if isinstance(title, str) and title.strip() else url,
            url=url,
            snippet=content[:_MAX_SNIPPET_CHARS] if isinstance(content, str) and content.strip() else None,
            published_at=self.iso_date(item.get("published_date")),
            raw=dict(item),
        )

    def _pages_from_payload(self, payload: Mapping[str, Any]) -> tuple[FetchedPage, ...]:
        # Reads the results array, raising when Tavily returns it in an unusable shape.
        results = payload.get("results")
        if results is None:
            return ()
        if not isinstance(results, (list, tuple)):
            raise ProviderResponseError("tavily extract returned a non-list results block.", provider=self.provider)
        pages = (self._page_from_result(item) for item in results if isinstance(item, Mapping))
        return tuple(page for page in pages if page is not None)

    @staticmethod
    def _page_from_result(item: Mapping[str, Any]) -> FetchedPage | None:
        # Normalizes one extracted page; entries without content never bill.
        url = item.get("url")
        content = item.get("raw_content") or item.get("content")
        if not isinstance(url, str) or not url.strip() or not isinstance(content, str) or not content.strip():
            return None
        return FetchedPage(url=url, final_url=url, content=content, content_type="text/markdown", raw=dict(item))


__all__ = [
    "TavilyClient",
]
