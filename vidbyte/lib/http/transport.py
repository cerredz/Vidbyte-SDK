from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass, replace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import httpx

from vidbyte.lib.errors import ProviderRequestError


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str
    headers: Mapping[str, str]
    raw_bytes: bytes | None = None
    attempts: int = 1


class HttpTransport:
    """Async HTTP transport using httpx; releases the event loop during all I/O."""

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504), max_response_bytes: int | None = None) -> HttpResponse:
        # Send one async HTTP request with optional non-blocking exponential backoff.
        attempts = max(0, retry_count) + 1
        delay = max(0.0, backoff_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                for attempt in range(attempts):
                    response = await self._send_once(client, method=method, url=url, headers=headers, json_body=json_body, timeout_seconds=timeout_seconds, max_response_bytes=max_response_bytes)
                    if response.status_code not in retry_status_codes or attempt == attempts - 1:
                        return replace(response, attempts=attempt + 1)
                    await asyncio.sleep(delay)
                    delay *= max(1.0, backoff_multiplier)
        except ProviderRequestError:
            raise
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc)) from exc
        raise ProviderRequestError("HTTP retry loop exited unexpectedly.", provider="http")

    async def stream_request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 120.0) -> AsyncIterator[str]:
        # Streams bounded SSE data lines for providers that expose research progress.
        request_headers = dict(headers)
        request_headers["accept"] = "text/event-stream"
        content = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        if content is not None:
            request_headers.setdefault("content-type", "application/json")
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                async with client.stream(method, url, headers=request_headers, content=content) as response:
                    if not 200 <= response.status_code < 300:
                        raise ProviderRequestError("Provider SSE request returned a failing status.", provider="http", status_code=response.status_code)
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            payload = line[6:]
                            if payload == "[DONE]":
                                return
                            yield payload
        except ProviderRequestError:
            raise
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP SSE connection failed.", provider="http", response_excerpt=str(exc)) from exc

    async def _send_once(self, client: httpx.AsyncClient, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None, timeout_seconds: float, max_response_bytes: int | None = None) -> HttpResponse:
        # Execute a single httpx request and return HTTP errors as responses rather than exceptions.
        request_headers = dict(headers)
        content: bytes | None = None
        if json_body is not None:
            content = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")
        request = client.build_request(method, url, headers=request_headers, content=content)
        if max_response_bytes is not None:
            return await self._send_bounded(client, request, max_response_bytes=max_response_bytes)
        try:
            response = await client.send(request)
            return HttpResponse(status_code=response.status_code, body=response.text, headers=dict(response.headers))
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc)) from exc

    async def _send_bounded(self, client: httpx.AsyncClient, request: httpx.Request, *, max_response_bytes: int) -> HttpResponse:
        # Stream one response and refuse any body above the ceiling without buffering it whole.
        ceiling = max(1, max_response_bytes)
        try:
            response = await client.send(request, stream=True)
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc)) from exc
        try:
            declared = response.headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > ceiling:
                raise ProviderRequestError("Provider response exceeded the configured size ceiling.", provider="http", status_code=response.status_code)
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > ceiling:
                    raise ProviderRequestError("Provider response exceeded the configured size ceiling.", provider="http", status_code=response.status_code)
                body.extend(chunk)
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP response stream failed before completion.", provider="http", response_excerpt=str(exc)) from exc
        finally:
            await response.aclose()
        return HttpResponse(status_code=response.status_code, body=bytes(body).decode("utf-8", errors="replace"), headers=dict(response.headers), raw_bytes=bytes(body))


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

    def request_bytes(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 120.0) -> HttpResponse:
        # Send a request and store the response body as raw bytes instead of decoded text.
        request_headers = dict(headers)
        body_data: bytes | None = None
        if json_body is not None:
            body_data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")
        request = Request(url=url, data=body_data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
                if response.status < 200 or response.status >= 300:
                    raise ProviderRequestError("Provider returned non-2xx for binary request.", provider="http", status_code=response.status, response_excerpt=raw.decode("utf-8", errors="replace")[:500])
                return HttpResponse(status_code=response.status, body="", headers=dict(response.headers.items()), raw_bytes=raw)
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ProviderRequestError("Provider request failed.", provider="http", status_code=exc.code, response_excerpt=error_body[:500]) from exc
        except URLError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc.reason)) from exc

    def upload_multipart(self, *, url: str, headers: Mapping[str, str], fields: Mapping[str, str], file_field: str, file_bytes: bytes, file_name: str, file_content_type: str, timeout_seconds: float = 120.0) -> HttpResponse:
        # Send a multipart/form-data POST with text fields and one binary file field.
        boundary = uuid.uuid4().hex
        body = self._build_multipart_body(boundary=boundary, fields=fields, file_field=file_field, file_bytes=file_bytes, file_name=file_name, file_content_type=file_content_type)
        request_headers = dict(headers)
        request_headers["content-type"] = f"multipart/form-data; boundary={boundary}"
        request = Request(url=url, data=body, headers=request_headers, method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return HttpResponse(status_code=response.status, body=response.read().decode("utf-8"), headers=dict(response.headers.items()))
        except HTTPError as exc:
            return HttpResponse(status_code=exc.code, body=exc.read().decode("utf-8", errors="replace"), headers=dict(exc.headers.items()) if exc.headers else {})
        except URLError as exc:
            raise ProviderRequestError("HTTP multipart upload failed.", provider="http", response_excerpt=str(exc.reason)) from exc

    def stream_request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 120.0) -> Iterator[str]:
        # Open an SSE connection and yield each data-line payload, stopping at [DONE].
        request_headers = dict(headers)
        request_headers["accept"] = "text/event-stream"
        body_data: bytes | None = None
        if json_body is not None:
            body_data = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")
        request = Request(url=url, data=body_data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                yield from self._iter_sse_lines(response)
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ProviderRequestError("Provider SSE request failed.", provider="http", status_code=exc.code, response_excerpt=error_body[:500]) from exc
        except URLError as exc:
            raise ProviderRequestError("HTTP SSE connection failed.", provider="http", response_excerpt=str(exc.reason)) from exc

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

    def _build_multipart_body(self, *, boundary: str, fields: Mapping[str, str], file_field: str, file_bytes: bytes, file_name: str, file_content_type: str) -> bytes:
        # Build an RFC 2046 multipart/form-data body from text fields and one file.
        parts: list[bytes] = []
        for name, value in fields.items():
            if value:
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\nContent-Type: {file_content_type}\r\n\r\n'.encode("utf-8"))
        parts.append(file_bytes)
        parts.append(f'\r\n--{boundary}--\r\n'.encode("utf-8"))
        return b"".join(parts)

    def _iter_sse_lines(self, response: object) -> Iterator[str]:
        # Read the SSE response line by line, yielding data payloads and stopping at [DONE].
        for raw_line in response:
            line = raw_line.decode("utf-8").rstrip("\r\n") if isinstance(raw_line, bytes) else raw_line.rstrip("\r\n")
            if not line or line.startswith(":") or line.startswith("event:"):
                continue
            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    return
                yield payload


__all__ = [
    "HttpResponse",
    "HttpTransport",
    "SyncHttpTransport",
]
