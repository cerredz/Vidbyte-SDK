"""Context Protocol Header

Description:
    Parallel web API client for search, extract, chat, tasks, FindAll, and monitors.
Purpose:
    Owns Parallel request headers and processor-aware pricebook dimensions while
    keeping synchronous and asynchronous API results resumable.
Architecture:
    ParallelClient extends WebOperationClient and exposes typed common methods plus
    a generic documented endpoint method used by provider-specific tools.
Relations:
    Consumed by Parallel tools and priced through OperationPricingRegistry.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from vidbyte.lib.dataclasses.operations import OperationCharge, ProviderOperationPayload, SearchHit, SearchPayload
from vidbyte.tools.builtins.operations.clients._base import RetryPolicy, WebOperationClient


class ParallelClient(WebOperationClient):
    """Credentialed Parallel Search, Extract, and web-agent API client."""

    def __init__(self, api_key: str, *, base_url: str = "https://api.parallel.ai", timeout_seconds: float = 120.0, retry: RetryPolicy | None = None, max_response_bytes: int = 8_000_000, transport: Any = None) -> None:
        # Configures Parallel's API host and bounded request policy.
        super().__init__(api_key, provider="parallel", base_url=base_url, timeout_seconds=timeout_seconds, retry=retry, max_response_bytes=max_response_bytes, transport=transport)

    def request_headers(self) -> dict[str, str]:
        # Builds Parallel's API-key header without exposing credentials to tool output.
        return {"x-api-key": self._api_key, "Content-Type": "application/json"}

    async def search(self, objective: str, *, search_queries: Sequence[str] = (), mode: str = "turbo", max_chars_total: int = 10_000) -> SearchPayload:
        # Runs Parallel Search with natural-language objective and optional keyword queries.
        queries = [query for query in search_queries if isinstance(query, str) and query.strip()][:3]
        body: dict[str, object] = {"objective": objective, "search_queries": queries, "mode": mode, "max_chars_total": max(1, max_chars_total)}
        payload = await self.request_operation("search", "POST", path="v1/search", headers=self.request_headers(), json_body=body, charges=(OperationCharge("search", self.provider, mode=mode, meter="request", units=1),))
        return self._search_payload(objective, payload)

    async def extract(self, urls: Sequence[str], *, objective: str | None = None, max_chars_total: int = 20_000) -> ProviderOperationPayload:
        # Extracts clean content from up to twenty known URLs through Parallel.
        body: dict[str, object] = {"urls": [url for url in urls if isinstance(url, str) and url.strip()][:20], "max_chars_total": max(1, max_chars_total)}
        if objective:
            body["objective"] = objective
        count = len(body["urls"])
        charge = OperationCharge("fetch", self.provider, mode="default", meter="url", units=count)
        return await self.request_operation("fetch", "POST", path="v1/extract", headers=self.request_headers(), json_body=body, charges=(charge,))

    async def chat(self, input: str, *, model: str = "speed", system: str | None = None) -> ProviderOperationPayload:
        # Requests a grounded Parallel Chat completion at the selected model tier.
        body: dict[str, object] = {"input": input, "model": model}
        if system:
            body["system"] = system
        charge = OperationCharge("chat", self.provider, mode=model, meter="request", units=1)
        return await self.request_operation("chat", "POST", path="v1/chat", headers=self.request_headers(), json_body=body, charges=(charge,))

    async def task(self, input: str, *, processor: str = "base", output_schema: Mapping[str, object] | None = None) -> ProviderOperationPayload:
        # Starts an asynchronous Parallel Task research or enrichment run.
        body: dict[str, object] = {"input": input, "processor": processor}
        if output_schema is not None:
            body["output_schema"] = dict(output_schema)
        charge = OperationCharge("task", self.provider, mode=processor, meter="run", units=1)
        return await self.request_operation("task", "POST", path="v1/tasks", headers=self.request_headers(), json_body=body, charges=(charge,))

    async def find_all(self, objective: str, *, generator: str = "preview", output_schema: Mapping[str, object] | None = None) -> ProviderOperationPayload:
        # Starts a Parallel FindAll list-building run with explicit generator pricing.
        body: dict[str, object] = {"objective": objective, "generator": generator}
        if output_schema is not None:
            body["output_schema"] = dict(output_schema)
        payload = await self.request_operation("find_all", "POST", path="v1/findall", headers=self.request_headers(), json_body=body, charges=())
        matches = self._match_count(payload.data)
        charges = (OperationCharge("find_all_request", self.provider, mode=generator, meter="run", units=1), OperationCharge("find_all_match", self.provider, mode=generator, meter="match", units=matches))
        return replace(payload, charges=charges)

    async def monitor(self, objective: str, *, processor: str = "lite", schedule: str | None = None) -> ProviderOperationPayload:
        # Creates a Parallel Monitor that runs a natural-language query on a schedule.
        body: dict[str, object] = {"objective": objective, "processor": processor}
        if schedule:
            body["schedule"] = schedule
        charge = OperationCharge("monitor", self.provider, mode=processor, meter="execution", units=1)
        return await self.request_operation("monitor", "POST", path="v1/monitors", headers=self.request_headers(), json_body=body, charges=(charge,))

    async def api(self, operation: str, *, method: str, path: str, body: Mapping[str, object] | None = None, charges: tuple[OperationCharge, ...] = ()) -> ProviderOperationPayload:
        # Sends a documented Parallel lifecycle request for status, cancel, or webhook tools.
        return await self.request_operation(operation, method, path=path, headers=self.request_headers(), json_body=body, charges=charges)

    def _search_payload(self, objective: str, payload: ProviderOperationPayload) -> SearchPayload:
        # Converts Parallel result records into provider-neutral search hits.
        raw_results = payload.data.get("results", ())
        hits = tuple(self._search_hit(item) for item in raw_results if isinstance(item, Mapping))
        valid_hits = tuple(hit for hit in hits if hit is not None)
        extra = max(0, len(valid_hits) - 10)
        charges = payload.charges + ((OperationCharge("search_extra_result", self.provider, mode="default", meter="result", units=extra),) if extra else ())
        return SearchPayload(provider=self.provider, query=objective, hits=valid_hits, attempts=payload.attempts, billable_units=1, request_id=payload.request_id, charges=charges, provider_usage=payload.provider_usage)

    @staticmethod
    def _match_count(data: Mapping[str, Any]) -> int:
        # Counts FindAll matches for the provider's per-match pricebook component.
        for key in ("matches", "results", "items"):
            value = data.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return len(value)
        return 0

    @staticmethod
    def _search_hit(item: Mapping[str, Any]) -> SearchHit | None:
        # Normalizes a Parallel result while dropping entries without usable URLs.
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        excerpt = item.get("excerpt") or item.get("content") or item.get("snippet")
        return SearchHit(title=str(item.get("title") or url), url=url, snippet=str(excerpt)[:500] if excerpt else None, raw=item)


__all__ = ["ParallelClient"]
