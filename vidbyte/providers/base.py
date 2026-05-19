from __future__ import annotations

import json
from typing import Any, Mapping

from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpResponse


def parse_json_response(response: HttpResponse, *, provider: str) -> dict[str, Any]:
    try:
        parsed = json.loads(response.body) if response.body else {}
    except json.JSONDecodeError as exc:
        raise ProviderRequestError(
            "Provider returned invalid JSON.",
            provider=provider,
            status_code=response.status_code,
            response_excerpt=response.body,
        ) from exc

    if response.status_code < 200 or response.status_code >= 300:
        message = _extract_error_message(parsed) or "Provider request failed."
        raise ProviderRequestError(
            message,
            provider=provider,
            status_code=response.status_code,
            response_excerpt=response.body,
        )

    return parsed


def bearer_headers(api_key: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }


def _extract_error_message(parsed: Mapping[str, Any]) -> str | None:
    error = parsed.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        return message if isinstance(message, str) else None
    if isinstance(error, str):
        return error
    return None
