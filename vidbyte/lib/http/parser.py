from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse


class HttpResponseParser:
    """Parse provider HTTP responses into SDK-safe structured values."""

    def parse_json_response(self, response: HttpResponse, *, provider: str) -> dict[str, Any]:
        # Decode JSON and convert provider error envelopes into SDK exceptions.
        parsed = self._decode_json(response, provider=provider)
        if response.status_code < 200 or response.status_code >= 300:
            message = self._extract_error_message(parsed) or "Provider request failed."
            raise ProviderRequestError(message, provider=provider, status_code=response.status_code, response_excerpt=response.body)
        return parsed

    def bearer_headers(self, api_key: str) -> dict[str, str]:
        # Build the common bearer-auth JSON headers used by compatible APIs.
        return {"authorization": f"Bearer {api_key}", "content-type": "application/json"}

    def _decode_json(self, response: HttpResponse, *, provider: str) -> dict[str, Any]:
        # Keep invalid JSON failures tied to the provider response that caused them.
        try:
            parsed = json.loads(response.body) if response.body else {}
        except json.JSONDecodeError as exc:
            raise ProviderRequestError("Provider returned invalid JSON.", provider=provider, status_code=response.status_code, response_excerpt=response.body) from exc
        if not isinstance(parsed, dict):
            raise ProviderRequestError("Provider returned non-object JSON.", provider=provider, status_code=response.status_code, response_excerpt=response.body)
        return parsed

    def _extract_error_message(self, parsed: Mapping[str, Any]) -> str | None:
        # Support common provider error envelope variants without leaking headers.
        error = parsed.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            return message if isinstance(message, str) else None
        if isinstance(error, str):
            return error
        return None


__all__ = [
    "HttpResponseParser",
]
