"""Context Protocol Header

Description:
    Executing client for the Browserbase Search and Fetch web operations.
Purpose:
    Turns one query or page URL into a normalized SearchPayload or FetchPayload,
    applying Browserbase's documented request limits and reporting the attempts
    the retry policy consumed.
Architecture:
    - BrowserbaseClient: WebOperationClient subclass owning the Browserbase
      endpoints, its API-key header, and vendor result normalization.
Relations:
    Injected into vidbyte.tools.builtins.operations.search.BrowserbaseSearchTool
    and fetch.BrowserbaseFetchTool; priced against ("search", "browserbase") and
    ("fetch", "browserbase") in the operation pricing registry.
Similar Files:
    - vidbyte/tools/builtins/operations/clients/brave.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.operations import (
    FetchedPage,
    FetchPayload,
    SearchHit,
    SearchPayload,
)
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.builtins.operations.clients._base import (
    RetryPolicy,
    WebOperationClient,
)

_MAX_RESULTS = 25


class BrowserbaseClient(WebOperationClient):
    """Browserbase client returning provider-neutral search results and page content."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.browserbase.com/v1", timeout_seconds: float = 30.0, retry: RetryPolicy | None = None, max_response_bytes: int = 4_000_000, transport: HttpTransport | None = None) -> None:
        # Configures the Browserbase endpoints and credential on the shared transport policy.
        super().__init__(api_key, provider="browserbase", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)

    async def search(self, query: str, *, num_results: int = 10) -> SearchPayload:
        """Run one Browserbase search and return normalized hits with billing counts."""
        payload, attempts = await self.request_json("search", "POST", path="search", headers=self._headers(), json_body=self._search_body(query, num_results))
        return SearchPayload(provider=self.provider, query=query, hits=self._hits_from_payload(payload), attempts=attempts, billable_units=1)

    async def fetch(self, url: str, *, proxies: bool = False) -> FetchPayload:
        """Fetch one page through Browserbase and return it with billing counts."""
        payload, attempts = await self.request_json("fetch", "POST", path="fetch", headers=self._headers(), json_body={"url": url, "proxies": proxies})
        return FetchPayload(provider=self.provider, pages=(self._page_from_payload(url, payload),), attempts=attempts, billable_units=1)

    def _headers(self) -> dict[str, str]:
        # Builds the Browserbase API-key header; the key never leaves this mapping.
        return {"X-BB-API-Key": self._api_key, "Content-Type": "application/json"}

    @staticmethod
    def _search_body(query: str, num_results: int) -> dict[str, object]:
        # Clamps the requested result count to Browserbase's documented maximum.
        return {"query": query, "numResults": min(max(1, num_results), _MAX_RESULTS)}

    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]:
        # Reads the results array, raising when Browserbase returns it in an unusable shape.
        results = payload.get("results")
        if results is None:
            return ()
        if not isinstance(results, (list, tuple)):
            raise ProviderResponseError("browserbase search returned a non-list results block.", provider=self.provider)
        hits = (self._hit_from_result(item) for item in results if isinstance(item, Mapping))
        return tuple(hit for hit in hits if hit is not None)

    @staticmethod
    def _hit_from_result(item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes one Browserbase result, skipping any entry without a usable URL.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        title = item.get("title")
        snippet = item.get("description") or item.get("snippet")
        return SearchHit(
            title=title if isinstance(title, str) and title.strip() else url,
            url=url,
            snippet=snippet if isinstance(snippet, str) and snippet.strip() else None,
            raw=dict(item),
        )

    def _page_from_payload(self, url: str, payload: Mapping[str, Any]) -> FetchedPage:
        # Normalizes one Browserbase fetch, treating blank content as a provider failure.
        content = payload.get("content") or payload.get("text")
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("browserbase fetch returned empty content.", provider=self.provider)
        return FetchedPage(url=url, final_url=self._final_url(url, payload), content=content, content_type=self._content_type(payload), raw=dict(payload))

    @staticmethod
    def _final_url(url: str, payload: Mapping[str, Any]) -> str:
        # Prefers the vendor's resolved URL, falling back to the requested URL.
        resolved = payload.get("url")
        return resolved if isinstance(resolved, str) and resolved.strip() else url

    @staticmethod
    def _content_type(payload: Mapping[str, Any]) -> str:
        # Prefers the vendor's reported content type, defaulting to HTML.
        value = payload.get("contentType")
        return value if isinstance(value, str) and value.strip() else "text/html"


__all__ = [
    "BrowserbaseClient",
]
