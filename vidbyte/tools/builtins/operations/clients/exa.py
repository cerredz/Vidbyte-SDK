"""Context Protocol Header

Description:
    Exa API client for search, contents retrieval, answers, and web research APIs.
Purpose:
    Centralizes Exa request construction and converts vendor usage dimensions into
    SDK pricebook charges without hardcoding cost arithmetic in tools.
Architecture:
    ExaClient extends WebOperationClient and exposes typed common operations plus a
    generic documented endpoint method for new Exa API capabilities.
Relations:
    Consumed by Exa tools and priced through OperationPricingRegistry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from vidbyte.lib.dataclasses.operations import OperationCharge, ProviderOperationPayload, SearchHit, SearchPayload
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient


class ExaClient(WebOperationClient):
    """Credentialed Exa Search and content-retrieval client."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.exa.ai", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, transport: Any = None) -> None:
        # Configures Exa's API host and bounded request policy.
        super().__init__(api_key, provider="exa", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)

    def request_headers(self) -> dict[str, str]:
        # Builds Exa's API-key header without exposing credentials to the tool result.
        return {"x-api-key": self._api_key, "Content-Type": "application/json"}

    async def search(self, query: str, *, num_results: int = 10, search_type: str = "auto", contents: Mapping[str, object] | None = None, category: str | None = None, options: Mapping[str, object] | None = None) -> SearchPayload:
        # Runs Exa search with optional contents, category, and documented search modes.
        body: dict[str, object] = {"query": query, "numResults": min(max(1, num_results), 100), "type": search_type}
        if contents is not None:
            body["contents"] = dict(contents)
        if category:
            body["category"] = category
        if options:
            body.update(options)
        charges = self._search_charges(search_type, num_results, contents)
        payload = await self.request_operation("search", "POST", path="search", headers=self.request_headers(), json_body=body, charges=charges)
        return self._search_payload(query, payload)

    async def contents(self, urls: Sequence[str], *, text: Mapping[str, object] | bool = True, summary: Mapping[str, object] | bool | None = None, highlights: Mapping[str, object] | None = None, livecrawl: str | None = None, options: Mapping[str, object] | None = None) -> ProviderOperationPayload:
        # Retrieves known URLs with Exa text, summaries, highlights, and livecrawl controls.
        body: dict[str, object] = {"ids": [url for url in urls if isinstance(url, str) and url.strip()], "text": text}
        if summary is not None:
            body["summary"] = summary
        if highlights is not None:
            body["highlights"] = dict(highlights)
        if livecrawl:
            body["livecrawl"] = livecrawl
        if options:
            body.update(options)
        count = len(body["ids"])
        charges = [OperationCharge("fetch", self.provider, meter="page", units=count)]
        if summary is not None:
            charges.append(OperationCharge("content_summary", self.provider, meter="page", units=count))
        return await self.request_operation("contents", "POST", path="contents", headers=self.request_headers(), json_body=body, charges=tuple(charges))

    async def answer(self, query: str, *, search_type: str = "auto", output_schema: Mapping[str, object] | None = None) -> ProviderOperationPayload:
        # Requests an Exa-grounded answer with optional structured output.
        body: dict[str, object] = {"query": query, "type": search_type}
        if output_schema is not None:
            body["outputSchema"] = dict(output_schema)
        charge = OperationCharge("answer", self.provider, mode=search_type, meter="request", units=1)
        return await self.request_operation("answer", "POST", path="answer", headers=self.request_headers(), json_body=body, charges=(charge,))

    async def api(self, operation: str, *, method: str, path: str, body: Mapping[str, object] | None = None, charges: tuple[OperationCharge, ...] = ()) -> ProviderOperationPayload:
        # Sends a documented Exa endpoint request for extensible webset and monitor tools.
        return await self.request_operation(operation, method, path=path, headers=self.request_headers(), json_body=body, charges=charges)

    def _search_charges(self, search_type: str, num_results: int, contents: Mapping[str, object] | None) -> tuple[OperationCharge, ...]:
        # Builds separate pricebook components for Exa base, extra-result, and summary usage.
        charges = [OperationCharge("search", self.provider, mode=search_type, meter="request", units=1)]
        extra = max(0, num_results - 10)
        if extra:
            charges.append(OperationCharge("search_extra_result", self.provider, mode=search_type, meter="result", units=extra))
        if contents and contents.get("summary"):
            charges.append(OperationCharge("content_summary", self.provider, meter="page", units=num_results))
        return tuple(charges)

    def _search_payload(self, query: str, payload: ProviderOperationPayload) -> SearchPayload:
        # Converts Exa result records to provider-neutral ranked search hits.
        raw_results = payload.data.get("results", ())
        hits = tuple(self._search_hit(item) for item in raw_results if isinstance(item, Mapping))
        return SearchPayload(provider=self.provider, query=query, hits=tuple(hit for hit in hits if hit is not None), attempts=payload.attempts, billable_units=1, request_id=payload.request_id, charges=payload.charges, provider_usage=payload.provider_usage, provider_reported_cost_usd=payload.provider_reported_cost_usd)

    @staticmethod
    def _search_hit(item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes an Exa result while dropping records without usable URLs.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        snippet = item.get("text") or item.get("highlight") or item.get("summary")
        return SearchHit(title=str(item.get("title") or url), url=url, snippet=str(snippet)[:500] if snippet else None, published_at=str(item.get("publishedDate")) if item.get("publishedDate") else None, raw=item)


__all__ = ["ExaClient"]
