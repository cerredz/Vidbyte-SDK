from __future__ import annotations

from typing import Any, Mapping

from vidbyte.tools.types import ToolSpec


def tool_spec_to_provider_schema(spec: ToolSpec, provider: str) -> Mapping[str, Any]:
    """Translate a Vidbyte tool spec into a provider-facing schema shape."""
    if provider in {"openai", "xai"}:
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": dict(spec.input_schema),
            },
        }
    if provider == "anthropic":
        return {
            "name": spec.name,
            "description": spec.description,
            "input_schema": dict(spec.input_schema),
        }
    if provider == "gemini":
        return {
            "name": spec.name,
            "description": spec.description,
            "parameters": dict(spec.input_schema),
        }
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": dict(spec.input_schema),
    }

