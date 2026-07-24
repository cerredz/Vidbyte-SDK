from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def token_usage_from_response(response: object, metadata: Mapping[str, Any]) -> int | None:
    """Extract provider-reported token usage from response metadata or raw payloads."""
    metadata_usage = _usage_total(metadata)
    if metadata_usage is not None:
        return metadata_usage
    usage_attr = getattr(response, "usage", None)
    if isinstance(usage_attr, Mapping):
        attr_total = _usage_mapping_total(usage_attr)
        if attr_total is not None:
            return attr_total
    raw = getattr(response, "raw", None)
    if isinstance(raw, Mapping):
        return _usage_total(raw)
    return None


def _usage_total(payload: Mapping[str, Any]) -> int | None:
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        total = _usage_mapping_total(usage)
        if total is not None:
            return total
    for key in ("total_tokens", "tokens_used"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def _usage_mapping_total(usage: Mapping[str, Any]) -> int | None:
    # Totals one provider usage mapping across OpenAI, chat-completions, and Gemini shapes.
    for key in ("total_tokens", "total", "totalTokenCount"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
    parts = [
        usage.get(key)
        for key in ("input_tokens", "prompt_tokens", "output_tokens", "completion_tokens", "promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount")
        if isinstance(usage.get(key), int)
    ]
    if parts:
        return sum(parts)
    return None


__all__ = [
    "token_usage_from_response",
]
