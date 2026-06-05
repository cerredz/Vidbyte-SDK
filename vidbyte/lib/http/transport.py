"""Context Protocol Header

Description:
    HTTP transport utilities for the Vidbyte SDK, providing async (httpx-based)
    and sync (urllib-based) request executors with retry/backoff mechanisms.
Purpose:
    Abstracts downstream HTTP request processing, ensuring consistent timing, timeout
    controls, and error categorization across all model and API providers.
Architecture:
    - HttpResponse: Standard response wrapper structure.
    - HttpTransport: Async HTTP transporter with retry loop.
    - SyncHttpTransport: Synchronous urllib-based request processor.
Relation to Codebase:
    Core network I/O layer used by all LLM providers and integration systems.
Similar Files:
    - None (central transport module)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
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
    raw_bytes: bytes | None = None


class HttpTransport:
    """Async HTTP transport using httpx; releases the event loop during all I/O."""

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, retry_count: int = 0, backoff_seconds: float = 0.5, backoff_multiplier: float = 2.0, retry_status_codes: tuple[int, ...] = (408, 409, 425, 429, 500, 502, 503, 504)) -> HttpResponse:
        # Send one async HTTP request with optional non-blocking exponential backoff.
        attempts = max(0, retry_count) + 1
        delay = max(0.0, backoff_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                for attempt in range(attempts):
                    response = await self._send_once(client, method=method, url=url, headers=headers, json_body=json_body)
                    if response.status_code not in retry_status_codes or attempt == attempts - 1:
                        return response
                    sleep_time = delay
                    if response.status_code == 429 and response.body:
                        import re
                        match = re.search(r"Please retry in\s+([0-9.]+)\s*s", response.body, re.IGNORECASE)
                        if match:
                            sleep_time = float(match.group(1)) + 1.0
                    await asyncio.sleep(sleep_time)
                    delay *= max(1.0, backoff_multiplier)
        except ProviderRequestError:
            raise
        except httpx.RequestError as exc:
            raise ProviderRequestError("HTTP request failed before receiving a provider response.", provider="http", response_excerpt=str(exc)) from exc
        raise ProviderRequestError("HTTP retry loop exited unexpectedly.", provider="http")

    async def _send_once(self, client: httpx.AsyncClient, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None) -> HttpResponse:
        # Execute a single httpx request and return HTTP errors as responses rather than exceptions.
        request_headers = dict(headers)
        content: bytes | None = None
        if json_body is not None:
            content = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")
        request = client.build_request(method, url, headers=request_headers, content=content)
        try:
            response = await client.send(request)
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
            sleep_time = delay
            if response.status_code == 429 and response.body:
                import re
                match = re.search(r"Please retry in\s+([0-9.]+)\s*s", response.body, re.IGNORECASE)
                if match:
                    sleep_time = float(match.group(1)) + 1.0
            time.sleep(sleep_time)
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
