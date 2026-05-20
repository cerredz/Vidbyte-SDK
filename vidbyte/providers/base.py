from __future__ import annotations

from typing import Any

from vidbyte.lib.http import HttpResponse, HttpResponseParser


def parse_json_response(response: HttpResponse, *, provider: str) -> dict[str, Any]:
    # Back-compatible wrapper; provider classes should prefer HttpResponseParser.
    return HttpResponseParser().parse_json_response(response, provider=provider)


def bearer_headers(api_key: str) -> dict[str, str]:
    # Back-compatible wrapper; provider classes should prefer HttpResponseParser.
    return HttpResponseParser().bearer_headers(api_key)


__all__ = [
    "bearer_headers",
    "parse_json_response",
]
