"""Context Protocol Header

Description:
    Shared transport policy for the executing search and fetch operation clients.
Purpose:
    Holds the retry, timeout, and response-ceiling configuration, the single JSON
    request helper both vendor clients use so neither reimplements HTTP, and the
    one date normalizer that keeps SearchHit.published_at a single format.
Architecture:
    - RetryPolicy: Immutable attempt budget and backoff configuration.
    - WebOperationClient: Credentialed base issuing bounded JSON requests over
      HttpTransport, reporting the attempts each request consumed, and exposing
      iso_date for vendor publication timestamps.
Relations:
    Subclassed by every vendor client in this package; brave, exa, and tavily
    additionally route their publication dates through iso_date. Consumed by the
    priced tools in vidbyte/tools/builtins/operations.
Similar Files:
    - vidbyte/lib/http/transport.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from json import JSONDecodeError, loads
from typing import Any
from urllib.parse import urlencode

from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.lib.http.transport import HttpResponse, HttpTransport

_ISO_DATE_CHARS = 10


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
    def iso_date(value: object) -> str | None:
        """Return the leading calendar date of a vendor date string as YYYY-MM-DD, else None."""
        # @intent one-published-at-format-across-every-search-client
        # SearchHit.published_at is consumed with date.fromisoformat, which rejects a
        # full timestamp on the supported Python floor. Vendors disagree on the shape
        # they emit, so every client normalizes here rather than passing its own
        # through and leaving the consumer to guess which client produced the hit.
        if not isinstance(value, str) or len(value) < _ISO_DATE_CHARS:
            return None
        try:
            return date.fromisoformat(value[:_ISO_DATE_CHARS]).isoformat()
        except ValueError:
            return None


__all__ = [
    "RetryPolicy",
    "WebOperationClient",
]
