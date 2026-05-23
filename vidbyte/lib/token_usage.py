from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def token_usage_from_response(response: object, metadata: Mapping[str, Any]) -> int | None:
    """Extract provider-reported token usage from response metadata or raw payloads."""
    metadata_usage = _usage_total(metadata)
    if metadata_usage is not None:
        return metadata_usage
    raw = getattr(response, "raw", None)
    if isinstance(raw, Mapping):
        return _usage_total(raw)
    return None


def _usage_total(payload: Mapping[str, Any]) -> int | None:
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        for key in ("total_tokens", "total"):
            value = usage.get(key)
            if isinstance(value, int):
                return value
        parts = [
            usage.get(key)
            for key in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens")
            if isinstance(usage.get(key), int)
        ]
        if parts:
            return sum(parts)
    for key in ("total_tokens", "tokens_used"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


__all__ = [
    "token_usage_from_response",
]
