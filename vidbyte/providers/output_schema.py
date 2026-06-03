"""Context Protocol Header

Description:
    Maps SDK output schemas to provider-native structured output request shapes.
Purpose:
    Keeps provider-specific response-format contracts out of AgentRuntime and centralises
    schema resolution plus post-execution validation in one place.
Architecture:
    - OutputSchemaFormatter: Resolves schemas, builds provider formats, validates outputs.
Relations:
    Used by vidbyte.agents.runtime when BaseAgent.output_schema or ToolSpec.output_schema is set.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.errors import ConfigurationError


class OutputSchemaFormatter:
    """Resolves output schemas, builds provider-native response formats, and validates outputs."""

    def resolve_schema(self, schema: type | Mapping[str, Any]) -> dict[str, Any]:
        # Convert a Pydantic BaseModel subclass or a raw dict into a plain JSON schema dict.
        try:
            from pydantic import BaseModel
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return dict(schema.model_json_schema())
        except ImportError:
            pass
        if isinstance(schema, Mapping):
            return dict(schema)
        raise ConfigurationError(
            f"output_schema must be a Pydantic BaseModel subclass or a dict, got {type(schema).__name__!r}."
        )

    def build_response_format(self, provider: str, schema: type | Mapping[str, Any]) -> Mapping[str, Any] | None:
        # Build the provider-native response_format dict, or return None for unsupported providers.
        resolved = self.resolve_schema(schema)
        normalized = (provider or "").lower()
        if "anthropic" in normalized or "claude" in normalized:
            return None
        if "gemini" in normalized or "google" in normalized:
            return self._gemini_format(resolved)
        if "openai" in normalized or "gpt" in normalized:
            return self._openai_format(resolved)
        return self._compatible_format(resolved)

    def validate(self, output: str, schema: type | Mapping[str, Any]) -> tuple[Any, str | None]:
        # Parse output as JSON and validate against the schema; returns (parsed, error_message).
        try:
            parsed = json.loads(output)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, f"output is not valid JSON: {exc}"
        try:
            from pydantic import BaseModel, ValidationError
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                try:
                    instance = schema.model_validate(parsed)
                    return instance, None
                except ValidationError as exc:
                    return None, str(exc)
        except ImportError:
            pass
        return parsed, None

    def _openai_format(self, schema: dict[str, Any]) -> dict[str, Any]:
        # Builds the OpenAI Responses API text.format payload shape.
        return {"type": "json_schema", "name": "agent_output", "schema": copy.deepcopy(schema), "strict": True}

    def _compatible_format(self, schema: dict[str, Any]) -> dict[str, Any]:
        # Builds the OpenAI-compatible chat completions response_format payload shape.
        return {
            "type": "json_schema",
            "json_schema": {"name": "agent_output", "schema": copy.deepcopy(schema), "strict": True},
        }

    def _gemini_format(self, schema: dict[str, Any]) -> dict[str, Any]:
        # Gemini's GeminiProvider reads response_format as the raw responseSchema value.
        return copy.deepcopy(schema)


__all__ = ["OutputSchemaFormatter"]
