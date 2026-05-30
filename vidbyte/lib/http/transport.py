from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx

from vidbyte.lib.errors import ProviderRequestError


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str
    headers: Mapping[str, str]


class HttpTransport:
    """Async HTTP transport using httpx; releases the event loop during all I/O."""

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504)) -> HttpResponse:
        # Send one async HTTP request with optional non-blocking exponential backoff.
        attempts = max(0, retry_count) + 1
        delay = max(0.0, backoff_seconds)
        try:
            async with httpx.AsyncClient() as client:
                for attempt in range(attempts):
                    response = await self._send_once(client, method=method, url=url, headers=headers, json_body=json_body, timeout_seconds=timeout_seconds)
                    if response.status_code not in retry_status_codes or attempt == attempts - 1:
                        return response
                    await asyncio.sleep(delay)
                    delay *= max(1.0, backoff_multiplier)
        except ProviderRequestError:
            raise
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc)) from exc
        raise ProviderRequestError("HTTP retry loop exited unexpectedly.", provider="http")

    async def _send_once(self, client: httpx.AsyncClient, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None, timeout_seconds: float) -> HttpResponse:
        # Execute a single httpx request and return HTTP errors as responses rather than exceptions.
        request_headers = dict(headers)
        content: bytes | None = None
        if json_body is not None:
            content = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")
        request = client.build_request(method, url, headers=request_headers, content=content)
        try:
            response = await client.send(request, timeout=timeout_seconds)
            return HttpResponse(status_code=response.status_code, body=response.text, headers=dict(response.headers))
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc)) from exc


class SyncHttpTransport:
    """Synchronous urllib-based transport; use only for test injection or non-async contexts."""

    def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504)) -> HttpResponse:
        # Send one blocking HTTP request with optional exponential backoff.
        attempts = max(0, retry_count) + 1
        delay = max(0.0, backoff_seconds)
        for attempt in range(attempts):
            response = self._send_once(method=method, url=url, headers=headers, json_body=json_body, timeout_seconds=timeout_seconds)
            if response.status_code not in retry_status_codes or attempt == attempts - 1:
                return response
            time.sleep(delay)
            delay *= max(1.0, backoff_multiplier)
        raise ProviderRequestError("HTTP retry loop exited unexpectedly.", provider="http")

    def _send_once(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None, timeout_seconds: float) -> HttpResponse:
        # Execute a single stdlib urllib request and return HTTP errors as responses.
        body: bytes | None = None
        request_headers = dict(headers)
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")
        request = Request(url=url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return HttpResponse(status_code=response.status, body=response.read().decode("utf-8"), headers=dict(response.headers.items()))
        except HTTPError as exc:
            return HttpResponse(status_code=exc.code, body=exc.read().decode("utf-8", errors="replace"), headers=dict(exc.headers.items()) if exc.headers else {})
        except URLError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc.reason)) from exc


__all__ = [
    "HttpResponse",
    "HttpTransport",
    "SyncHttpTransport",
]
