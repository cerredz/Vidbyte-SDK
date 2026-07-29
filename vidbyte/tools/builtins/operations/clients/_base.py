"""Context Protocol Header

Description:
    Shared transport policy for the executing search and fetch operation clients.
Purpose:
    Holds the retry, timeout, and response-ceiling configuration and the single
    JSON request helper both vendor clients use, so neither reimplements HTTP.
Architecture:
    - RetryPolicy: Immutable attempt budget and backoff configuration.
    - WebOperationClient: Credentialed base issuing bounded JSON requests over
      HttpTransport and reporting the attempts each request consumed.
Relations:
    Subclassed by brave.BraveClient and firecrawl.FirecrawlClient; consumed by
    the priced tools in vidbyte/tools/builtins/operations.
Similar Files:
    - vidbyte/lib/http/transport.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from json import JSONDecodeError, loads
from typing import Any
from urllib.parse import urlencode

from vidbyte.lib.dataclasses.operations import OperationCharge, ProviderOperationPayload
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Attempt budget and backoff applied to one provider request."""

    max_attempts: int = 3
    backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504)


class WebOperationClient:
    """Credentialed JSON client for one priced search or fetch provider."""

    def __init__(self, api_key: str, *, provider: str, base_url: str, timeout_seconds: float = 15.0, retry: RetryPolicy | None = None, max_response_bytes: int = 2_000_000, transport: HttpTransport | None = None) -> None:
        # Stores vendor endpoint, credential, and transport policy for every later request.
        self._api_key = api_key
        self._provider = provider
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._retry = retry or RetryPolicy()
        self._max_response_bytes = max(1_024, max_response_bytes)
        self._transport = transport or HttpTransport()

    @property
    def provider(self) -> str:
        """Return the pricebook provider key this client bills against."""
        return self._provider

    @property
    def max_attempts(self) -> int:
        """Return the attempt budget a failed request is assumed to have spent."""
        return max(1, self._retry.max_attempts)

    async def request_json(self, operation: str, method: str, *, path: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, query: Mapping[str, str] | None = None) -> tuple[Mapping[str, Any], int]:
        """Issue one bounded provider request and return its JSON object with the attempts used."""
        response = await self._transport.request(
            method=method,
            url=self._absolute_url(path, query),
            headers=headers,
            json_body=json_body,
            timeout_seconds=self._timeout_seconds,
            retry_count=self.max_attempts - 1,
            backoff_seconds=self._retry.backoff_seconds,
            backoff_multiplier=self._retry.backoff_multiplier,
            retry_status_codes=self._retry.retry_status_codes,
            max_response_bytes=self._max_response_bytes,
        )
        self._require_ok(operation, response)
        return self._decode_object(operation, response), response.attempts

    async def request_operation(self, operation: str, method: str, *, path: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, charges: tuple[OperationCharge, ...] = (), async_id: str | None = None) -> ProviderOperationPayload:
        # Executes an endpoint and wraps its JSON, request identity, and pricebook charges.
        payload, attempts = await self.request_json(operation, method, path=path, headers=headers, json_body=json_body)
        return ProviderOperationPayload(provider=self.provider, operation=operation, data=payload, attempts=attempts, request_id=self._request_id(payload), async_id=async_id or self._async_id(payload), charges=charges, provider_usage=self._provider_usage(payload), provider_reported_cost_usd=self._reported_cost(payload))

    async def stream_operation(self, operation: str, *, path: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, charges: tuple[OperationCharge, ...] = ()) -> ProviderOperationPayload:
        # Collects provider SSE events into one bounded operation payload for runtime accounting.
        events: list[Mapping[str, Any]] = []
        async for chunk in self._transport.stream_request(method="POST", url=self._absolute_url(path, None), headers=headers, json_body=json_body, timeout_seconds=self._timeout_seconds):
            try:
                event = loads(chunk)
            except (JSONDecodeError, TypeError, ValueError):
                continue
            if isinstance(event, Mapping):
                events.append(dict(event))
        data = events[-1] if events else {"events": events}
        return ProviderOperationPayload(provider=self.provider, operation=operation, data=data, attempts=1, request_id=self._request_id(data), async_id=self._async_id(data), charges=charges, provider_usage=self._provider_usage(data), provider_reported_cost_usd=self._reported_cost(data))

    def request_headers(self) -> dict[str, str]:
        # Returns the default bearer-authenticated JSON headers for provider APIs.
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _absolute_url(self, path: str, query: Mapping[str, str] | None) -> str:
        # Joins the configured base URL with the path and an encoded query string.
        url = f"{self._base_url}/{path.lstrip('/')}"
        return f"{url}?{urlencode(dict(query))}" if query else url

    def _require_ok(self, operation: str, response: HttpResponse) -> None:
        # Rejects any non-2xx provider status without echoing the response body.
        if not 200 <= response.status_code < 300:
            raise ProviderRequestError(f"{self._provider} {operation} returned a failing status.", provider=self._provider, status_code=response.status_code)

    def _decode_object(self, operation: str, response: HttpResponse) -> Mapping[str, Any]:
        # Parses the body as a JSON object, raising rather than falling back to an empty mapping.
        try:
            payload = loads(response.body)
        except (JSONDecodeError, TypeError, ValueError) as exc:
            raise ProviderResponseError(f"{self._provider} {operation} returned a non-JSON body.", provider=self._provider, status_code=response.status_code) from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError(f"{self._provider} {operation} returned a non-object JSON body.", provider=self._provider, status_code=response.status_code)
        return payload

    @staticmethod
    def _request_id(payload: Mapping[str, Any]) -> str | None:
        # Extracts common request identifiers without assuming a provider schema.
        for key in ("requestId", "request_id", "id", "search_id", "extract_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _async_id(payload: Mapping[str, Any]) -> str | None:
        # Extracts common asynchronous job identifiers for resumable operations.
        for key in ("task_id", "taskId", "webset_id", "websetId", "research_id", "monitor_id", "find_all_id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _provider_usage(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        # Keeps provider usage counters while avoiding a second vendor-specific envelope.
        value = payload.get("usage")
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _reported_cost(payload: Mapping[str, Any]) -> float | None:
        # Reads a vendor cost estimate for reconciliation while the pricebook remains authoritative.
        value = payload.get("costDollars", payload.get("cost_dollars"))
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


__all__ = [
    "RetryPolicy",
    "WebOperationClient",
]
