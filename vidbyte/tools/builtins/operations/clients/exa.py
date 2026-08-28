"""Context Protocol Header

Description:
    Executing client for the Exa neural web-search operation.
Purpose:
    Turns one query into a normalized SearchPayload under a documented search
    type, reporting the returned result count the pricebook bills above Exa's
    ten-result allowance.
Architecture:
    - ExaClient: WebOperationClient subclass owning the Exa search endpoint, its
      API-key header, vendor result normalization, and the caller-supplied result
      ceiling and contents policy.
Relations:
    Injected into vidbyte.tools.builtins.operations.search.ExaSearchTool and
    priced against ("search", "exa") in the operation pricing registry. Requesting
    highlights bills a second Exa meter, so it is opt-in and moves the tool's
    billing mode to the matching "<type>+highlights" pricebook entry.
Similar Files:
    - vidbyte/tools/builtins/operations/clients/brave.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.operations import SearchHit, SearchPayload
from vidbyte.lib.errors import ProviderResponseError
from vidbyte.lib.http.transport import HttpTransport
from vidbyte.tools.builtins.operations.clients._base import (
    RetryPolicy,
    WebOperationClient,
)

_MAX_RESULTS = 100
_MAX_SNIPPET_CHARS = 500
_HIGHLIGHT_SENTENCES = 3
_HIGHLIGHTS_PER_URL = 2
_HIGHLIGHT_JOINER = " … "


class ExaClient(WebOperationClient):
    """Exa client returning provider-neutral ranked web results."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.exa.ai", timeout_seconds: float = 30.0, retry: RetryPolicy | None = None, max_response_bytes: int = 4_000_000, max_results: int = _MAX_RESULTS, include_highlights: bool = False, transport: HttpTransport | None = None) -> None:
        # Configures the Exa endpoint, credential, and result/contents policy on the shared transport.
        super().__init__(api_key, provider="exa", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)
        self._max_results = min(max(1, int(max_results)), _MAX_RESULTS)
        self._include_highlights = bool(include_highlights)

    @property
    def includes_highlights(self) -> bool:
        """Return whether this client requests the billable contents.highlights block."""
        return self._include_highlights

    async def search(self, query: str, *, num_results: int = 10, search_type: str = "auto") -> SearchPayload:
        """Run one Exa search and return normalized hits with billing counts."""
        payload, attempts = await self.request_json("search", "POST", path="search", headers=self._headers(), json_body=self._search_body(query, num_results, search_type))
        hits = self._hits_from_payload(payload)
        return SearchPayload(provider=self.provider, query=query, hits=hits, attempts=attempts, billable_units=max(1, len(hits)))

    def _headers(self) -> dict[str, str]:
        # Builds the Exa API-key header; the key never leaves this mapping.
        return {"x-api-key": self._api_key, "Content-Type": "application/json"}

    def _search_body(self, query: str, num_results: int, search_type: str) -> dict[str, object]:
        # Requests results, adding a contents block only when the caller accepted its charge.
        body: dict[str, object] = {"query": query, "numResults": min(max(1, num_results), self._max_results), "type": search_type}
        if self._include_highlights:
            body["contents"] = {"highlights": {"numSentences": _HIGHLIGHT_SENTENCES, "highlightsPerUrl": _HIGHLIGHTS_PER_URL}}
        return body

    def _hits_from_payload(self, payload: Mapping[str, Any]) -> tuple[SearchHit, ...]:
        # Reads the results array, raising when Exa returns it in an unusable shape.
        results = payload.get("results")
        if results is None:
            return ()
        if not isinstance(results, (list, tuple)):
            raise ProviderResponseError("exa search returned a non-list results block.", provider=self.provider)
        hits = (self._hit_from_result(item) for item in results if isinstance(item, Mapping))
        return tuple(hit for hit in hits if hit is not None)

    def _hit_from_result(self, item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes one Exa result, skipping any entry without a usable URL.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        title = item.get("title")
        return SearchHit(
            title=title if isinstance(title, str) and title.strip() else url,
            url=url,
            snippet=self._snippet_from_result(item),
            published_at=self.iso_date(item.get("publishedDate")),
            raw=dict(item),
        )

    def _snippet_from_result(self, item: Mapping[str, Any]) -> str | None:
        # Prefers query-relevant highlights, falling back to whatever body text Exa returned.
        highlights = self._joined_highlights(item.get("highlights"))
        if highlights:
            return highlights[:_MAX_SNIPPET_CHARS]
        text = item.get("text") or item.get("snippet")
        return text[:_MAX_SNIPPET_CHARS] if isinstance(text, str) and text.strip() else None

    @staticmethod
    def _joined_highlights(value: object) -> str | None:
        # Joins the highlight excerpts into one snippet, tolerating any non-list vendor shape.
        if not isinstance(value, (list, tuple)):
            return None
        excerpts = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return _HIGHLIGHT_JOINER.join(excerpts) if excerpts else None


__all__ = [
    "ExaClient",
]
