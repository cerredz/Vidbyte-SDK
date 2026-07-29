"""Context Protocol Header

Description:
    Executing client for the Firecrawl v2 page-scrape fetch operation.
Purpose:
    Turns one or more URLs into a normalized FetchPayload of markdown pages and
    reports the attempts the retry policy consumed across the batch.
Architecture:
    - FirecrawlClient: WebOperationClient subclass owning the Firecrawl endpoint,
      its bearer header, the deterministic scrape options, and normalization.
Relations:
    Injected into vidbyte.tools.builtins.operations.fetch.FirecrawlFetchTool and
    priced against ("fetch", "firecrawl") in the operation pricing registry.
Similar Files:
    - vidbyte/tools/builtins/operations/clients/brave.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.operations import FetchedPage, FetchPayload, OperationCharge
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient

_DEFAULT_CACHE_MS = 172_800_000


class FirecrawlClient(WebOperationClient):
    """Firecrawl client returning provider-neutral markdown page content."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.firecrawl.dev/v2", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, cache_ms: int = _DEFAULT_CACHE_MS, only_main_content: bool = True, transport: HttpTransport | None = None) -> None:
        # Configures the Firecrawl endpoint, credential, and deterministic scrape options.
        super().__init__(api_key, provider="firecrawl", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)
        self._cache_ms = max(0, cache_ms)
        self._only_main_content = only_main_content

    async def scrape(self, urls: Sequence[str]) -> FetchPayload:
        """Scrape every URL into markdown and return the pages with billing counts."""
        pages: list[FetchedPage] = []
        attempts = 1
        for url in urls:
            page, used = await self._scrape_one(url)
            pages.append(page)
            attempts = max(attempts, used)
        return FetchPayload(provider=self.provider, pages=tuple(pages), attempts=attempts, billable_units=len(pages), charges=(OperationCharge("fetch", self.provider, mode="scrape", meter="page", units=len(pages)),))

    def _headers(self) -> dict[str, str]:
        # Builds the Firecrawl bearer header; the key never leaves this mapping.
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _scrape_body(self, url: str) -> dict[str, object]:
        # Builds the deterministic markdown scrape request for one page.
        return {"url": url, "formats": ["markdown"], "onlyMainContent": self._only_main_content, "maxAge": self._cache_ms, "blockAds": True}

    async def _scrape_one(self, url: str) -> tuple[FetchedPage, int]:
        # Scrapes one URL and returns the normalized page with that request's attempt count.
        payload, attempts = await self.request_json("fetch", "POST", path="scrape", headers=self._headers(), json_body=self._scrape_body(url))
        return self._page_from_payload(url, payload), attempts

    def _page_from_payload(self, url: str, payload: Mapping[str, Any]) -> FetchedPage:
        # Normalizes one Firecrawl scrape, treating blank markdown as a provider failure.
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ProviderResponseError("firecrawl fetch returned no data object.", provider=self.provider)
        content = data.get("markdown")
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("firecrawl fetch returned empty markdown.", provider=self.provider)
        return FetchedPage(url=url, final_url=self._final_url(url, data), content=content, content_type="text/markdown", raw=dict(data))

    @staticmethod
    def _final_url(url: str, data: Mapping[str, Any]) -> str:
        # Prefers the vendor's resolved source URL, falling back to the requested URL.
        metadata = data.get("metadata")
        if not isinstance(metadata, Mapping):
            return url
        resolved = metadata.get("sourceURL") or metadata.get("url")
        return resolved if isinstance(resolved, str) and resolved.strip() else url


__all__ = [
    "FirecrawlClient",
]
