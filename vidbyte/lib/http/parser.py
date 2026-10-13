from __future__ import annotations

import json
from typing import Any, Mapping

from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http.transport import HttpResponse


class HttpResponseParser:
    """Parse provider HTTP responses into SDK-safe structured values."""

    def parse_json_response(self, response: HttpResponse, *, provider: str) -> dict[str, Any]:
        # @intent failing-status-is-reported-before-the-body-format: a non-2xx answer is a failed request whatever its
        # body format (proxies and some vendors send HTML or plain-text errors), so it is reported like one, never as a provider that "returned invalid JSON".
        if response.status_code < 200 or response.status_code >= 300:
            # Read the vendor's error envelope when the body is a JSON object; any other body carries no message to read.
            try:
                parsed = self._decode_json(response, provider=provider)
            except ProviderRequestError:
                parsed = {}
            # Report the failed request with the vendor's message, or a generic one when there is none.
            message = self._extract_error_message(parsed) or "Provider request failed."
            raise ProviderRequestError(message, provider=provider, status_code=response.status_code, response_excerpt=response.body)
        # A successful answer must be a JSON object; anything else is reported as invalid JSON.
        return self._decode_json(response, provider=provider)

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
        # @intent mistral-top-level-error-message: Mistral documents every error body as
        # {"object": "error", "message": ...} with the message at top level, so read it when there is no "error" envelope.
        message = parsed.get("message")
        return message if isinstance(message, str) and message.strip() else None


__all__ = [
    "HttpResponseParser",
]
