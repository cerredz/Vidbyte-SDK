"""Context Protocol Header

Description:
    Executing client for the Parallel Search and Extract web operations.
Purpose:
    Turns one objective into a normalized SearchPayload under a processor tier
    and a URL batch into a normalized FetchPayload, clamping both to Parallel's
    documented request maximums before any paid call.
Architecture:
    - ParallelClient: WebOperationClient subclass owning the Parallel endpoints,
      its API-key header, and vendor result normalization.
Relations:
    Injected into vidbyte.tools.builtins.operations.search.ParallelSearchTool and
    fetch.ParallelExtractTool; priced against ("search", "parallel") and
    ("fetch", "parallel") in the operation pricing registry.
Similar Files:
    - vidbyte/tools/builtins/operations/clients/tavily.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.operations import FetchedPage, FetchPayload, SearchHit, SearchPayload
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient

_MAX_RESULTS = 40
_MAX_URLS = 20
_MAX_SNIPPET_CHARS = 500


class ParallelClient(WebOperationClient):
    """Parallel client returning provider-neutral search results and extracted pages."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.parallel.ai/v1beta", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, transport: HttpTransport | None = None) -> None:
        # Configures the Parallel endpoints and credential on the shared transport policy.
        super().__init__(api_key, provider="parallel", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)

    async def search(self, objective: str, *, max_results: int = 10, processor: str = "turbo") -> SearchPayload:
        """Run one Parallel search and return normalized hits with billing counts."""
        body = {"objective": objective, "processor": processor, "max_results": min(max(1, max_results), _MAX_RESULTS)}
        payload, attempts = await self.request_json("search", "POST", path="search", headers=self._headers(), json_body=body)
        hits = self._hits_from_payload(payload)
        return SearchPayload(provider=self.provider, query=objective, hits=hits, attempts=attempts, billable_units=max(1, len(hits)))

    async def extract(self, urls: Sequence[str]) -> FetchPayload:
        """Extract a bounded URL batch and return the pages Parallel retrieved."""
        payload, attempts = await self.request_json("fetch", "POST", path="extract", headers=self._headers(), json_body={"urls": list(urls)[:_MAX_URLS]})
        pages = self._pages_from_payload(payload)
        return FetchPayload(provider=self.provider, pages=pages, attempts=attempts, billable_units=len(pages))

    def _headers(self) -> dict[str, str]:
        # Builds the Parallel API-key header; the key never leaves this mapping.
        return {"x-api-key": self._api_key, "Content-Type": "application/json"}

    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]:
        # Reads the results array, raising when Parallel returns it in an unusable shape.
        results = payload.get("results")
        if results is None:
            return ()
        if not isinstance(results, (list, tuple)):
            raise ProviderResponseError("parallel search returned a non-list results block.", provider=self.provider)
        hits = (self._hit_from_result(item) for item in results if isinstance(item, Mapping))
        return tuple(hit for hit in hits if hit is not None)

    @classmethod
    def _hit_from_result(cls, item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes one Parallel result, skipping any entry without a usable URL.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        title = item.get("title")
        snippet = cls._first_excerpt(item)
        return SearchHit(
            title=title if isinstance(title, str) and title.strip() else url,
            url=url,
            snippet=snippet[:_MAX_SNIPPET_CHARS] if snippet else None,
            raw=dict(item),
        )

    @staticmethod
    def _first_excerpt(item: Mapping[str, Any]) -> str | None:
        # Returns the first usable excerpt Parallel supplied for a result.
        excerpts = item.get("excerpts")
        if isinstance(excerpts, (list, tuple)):
            for excerpt in excerpts:
                if isinstance(excerpt, str) and excerpt.strip():
                    return excerpt
        content = item.get("content")
        return content if isinstance(content, str) and content.strip() else None

    def _pages_from_payload(self, payload: Mapping[str, Any]) -> tuple[FetchedPage, ...]:
        # Reads the results array, raising when Parallel returns it in an unusable shape.
        results = payload.get("results")
        if results is None:
            return ()
        if not isinstance(results, (list, tuple)):
            raise ProviderResponseError("parallel extract returned a non-list results block.", provider=self.provider)
        pages = (self._page_from_result(item) for item in results if isinstance(item, Mapping))
        return tuple(page for page in pages if page is not None)

    @staticmethod
    def _page_from_result(item: Mapping[str, Any]) -> FetchedPage | None:
        # Normalizes one extracted page; entries without content never bill.
        url = item.get("url")
        content = item.get("full_content") or item.get("content")
        if not isinstance(url, str) or not url.strip() or not isinstance(content, str) or not content.strip():
            return None
        return FetchedPage(url=url, final_url=url, content=content, content_type="text/markdown", raw=dict(item))


__all__ = [
    "ParallelClient",
]
