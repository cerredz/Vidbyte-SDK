"""Context Protocol Header

Description:
    Executing client for the Brave Search web-search operation.
Purpose:
    Turns one query into a normalized SearchPayload, applying Brave's documented
    request limits and reporting the attempts the retry policy consumed.
Architecture:
    - BraveClient: WebOperationClient subclass owning the Brave endpoint, its
      subscription-token header, and vendor result normalization.
Relations:
    Injected into vidbyte.tools.builtins.operations.search.BraveSearchTool and
    priced against ("search", "brave") in the operation pricing registry.
Similar Files:
    - vidbyte/tools/builtins/operations/clients/firecrawl.py
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from vidbyte.lib.dataclasses.operations import OperationCharge, SearchHit, SearchPayload
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient

_MAX_RESULTS = 20
_MAX_QUERY_WORDS = 50
_MAX_QUERY_CHARS = 400


class BraveClient(WebOperationClient):
    """Brave Search client returning provider-neutral ranked web results."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.search.brave.com/res/v1", timeout_seconds: float = 15.0, retry: RetryPolicy | None = None, max_response_bytes: int = 2_000_000, transport: HttpTransport | None = None) -> None:
        # Configures the Brave endpoint and credential on the shared transport policy.
        super().__init__(api_key, provider="brave", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)

    async def search(self, query: str, *, count: int = 10, language: str = "en") -> SearchPayload:
        """Run one Brave web search and return normalized hits with billing counts."""
        payload, attempts = await self.request_json("search", "GET", path="web/search", headers=self._headers(), query=self._query_params(query, count, language))
        return SearchPayload(provider=self.provider, query=query, hits=self._hits_from_payload(payload), attempts=attempts, billable_units=1, charges=(OperationCharge("search", self.provider, meter="request", units=1),))

    def _headers(self) -> dict[str, str]:
        # Builds the Brave subscription-token header; the key never leaves this mapping.
        return {"Accept": "application/json", "X-Subscription-Token": self._api_key}

    def _query_params(self, query: str, count: int, language: str) -> dict[str, str]:
        # Clamps the query and result count to Brave's documented request limits.
        words = " ".join(query.split()[:_MAX_QUERY_WORDS])[:_MAX_QUERY_CHARS]
        bounded = min(max(1, count), _MAX_RESULTS)
        return {"q": words, "count": str(bounded), "offset": "0", "search_lang": language.split("-", 1)[0].lower(), "safesearch": "moderate"}

    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]:
        # Reads the web result block, raising when Brave returns it in an unusable shape.
        web = payload.get("web")
        if web is None:
            return ()
        if not isinstance(web, Mapping):
            raise ProviderResponseError("brave search returned a non-object web block.", provider=self.provider)
        results = web.get("results")
        if not isinstance(results, (list, tuple)):
            return ()
        hits = (self._hit_from_result(item) for item in results if isinstance(item, Mapping))
        return tuple(hit for hit in hits if hit is not None)

    def _hit_from_result(self, item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes one Brave result, skipping any entry without a usable URL.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        title = item.get("title")
        snippet = item.get("description")
        return SearchHit(
            title=title if isinstance(title, str) and title.strip() else url,
            url=url,
            snippet=snippet if isinstance(snippet, str) and snippet.strip() else None,
            published_at=self._published_date(item.get("page_age") or item.get("age")),
            language=None,
            raw=dict(item),
        )

    @staticmethod
    def _published_date(value: object) -> str | None:
        # Returns the leading ISO date of a Brave age string, or None when unparseable.
        if not isinstance(value, str) or len(value) < 10:
            return None
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return None


__all__ = [
    "BraveClient",
]
