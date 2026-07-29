"""Context Protocol Header

Description:
    Browserbase API client for web search, fetch, and browser lifecycle requests.
Purpose:
    Owns Browserbase authentication, endpoint paths, and normalization so tools
    can expose the vendor API without duplicating HTTP or billing logic.
Architecture:
    BrowserbaseClient extends WebOperationClient and returns normalized SearchPayload,
    FetchPayload, or ProviderOperationPayload values with pricebook charge dimensions.
Relations:
    Consumed by Browserbase tools in vidbyte.tools.builtins.operations and priced by
    vidbyte.lib.registries.operation_pricing through AgentRuntime usage metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.dataclasses.operations import FetchedPage, FetchPayload, OperationCharge, ProviderOperationPayload, SearchHit, SearchPayload
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient


class BrowserbaseClient(WebOperationClient):
    """Credentialed Browserbase Search, Fetch, and lifecycle client."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.browserbase.com/v1", timeout_seconds: float = 60.0, retry: RetryPolicy | None = None, max_response_bytes: int = 2_000_000, transport: Any = None) -> None:
        # Configures Browserbase's API host and bounded request policy.
        super().__init__(api_key, provider="browserbase", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)

    def request_headers(self) -> dict[str, str]:
        # Builds Browserbase's API-key header without exposing the key to results.
        return {"x-bb-api-key": self._api_key, "Content-Type": "application/json"}

    async def search(self, query: str, *, num_results: int = 10) -> SearchPayload:
        # Searches Browserbase and normalizes ranked web results for the model.
        body = {"query": query, "numResults": min(max(1, num_results), 25)}
        payload = await self.request_operation("search", "POST", path="search", headers=self.request_headers(), json_body=body, charges=(OperationCharge("search", self.provider, units=1, meter="request"),))
        return self._search_payload(query, payload)

    async def fetch(self, url: str, *, proxies: bool = False, extract: bool = False, allow_redirects: bool = True, allow_insecure_ssl: bool = False) -> FetchPayload:
        # Fetches or extracts one page through Browserbase's raw HTTP infrastructure.
        body = {"url": url, "allowRedirects": allow_redirects, "allowInsecureSsl": allow_insecure_ssl, "proxies": proxies, "extract": extract}
        mode = "proxy" if proxies else "default"
        operation = "extract" if extract else "fetch"
        charge = OperationCharge(operation, self.provider, mode=mode, units=1, meter="request")
        payload = await self.request_operation(operation, "POST", path="fetch", headers=self.request_headers(), json_body=body, charges=(charge,))
        return self._fetch_payload(url, payload)

    async def api(self, operation: str, *, method: str, path: str, body: Mapping[str, object] | None = None, charges: tuple[OperationCharge, ...] = ()) -> ProviderOperationPayload:
        # Sends a documented Browserbase lifecycle request for extensible endpoint tools.
        return await self.request_operation(operation, method, path=path, headers=self.request_headers(), json_body=body, charges=charges)

    def _search_payload(self, query: str, payload: ProviderOperationPayload) -> SearchPayload:
        # Converts Browserbase result records into the shared search contract.
        raw_results = payload.data.get("results", ())
        hits = tuple(self._search_hit(item) for item in raw_results if isinstance(item, Mapping))
        return SearchPayload(provider=self.provider, query=query, hits=tuple(hit for hit in hits if hit is not None), attempts=payload.attempts, billable_units=1, request_id=payload.request_id, charges=payload.charges, provider_usage=payload.provider_usage)

    @staticmethod
    def _search_hit(item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes a Browserbase result while dropping records without URLs.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        return SearchHit(title=str(item.get("title") or url), url=url, snippet=str(item.get("description") or item.get("snippet") or "")[:500] or None, published_at=str(item.get("publishedDate")) if item.get("publishedDate") else None, raw=item)

    def _fetch_payload(self, url: str, payload: ProviderOperationPayload) -> FetchPayload:
        # Converts Browserbase fetch output into the shared page contract.
        data = payload.data
        content = str(data.get("content") or "")
        final_url = str(data.get("url") or url)
        page = FetchedPage(url=url, final_url=final_url, content=content, content_type=str(data.get("contentType") or "text/html"), raw=data)
        return FetchPayload(provider=self.provider, pages=(page,), attempts=payload.attempts, billable_units=1, request_id=payload.request_id, charges=payload.charges, provider_usage=payload.provider_usage)


__all__ = ["BrowserbaseClient"]
