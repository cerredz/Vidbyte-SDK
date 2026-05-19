from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vidbyte.lib.errors import ProviderRequestError


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str
    headers: Mapping[str, str]


class HttpTransport:
    """Small stdlib HTTP transport with a test-friendly request surface."""

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
        timeout_seconds: float = 60.0,
    ) -> HttpResponse:
        body: bytes | None = None
        request_headers = dict(headers)
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")

        request = Request(url=url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
                return HttpResponse(
                    status_code=response.status,
                    body=response_body,
                    headers=dict(response.headers.items()),
                )
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            return HttpResponse(
                status_code=exc.code,
                body=response_body,
                headers=dict(exc.headers.items()) if exc.headers else {},
            )
        except URLError as exc:
            raise ProviderRequestError(
                "HTTP request failed before receiving a provider response.",
                provider="http",
                response_excerpt=str(exc.reason),
            ) from exc
