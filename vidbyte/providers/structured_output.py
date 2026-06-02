"""Context Protocol Header

Description:
    Maps SDK output schemas to provider-native structured output request shapes.
Purpose:
    Keeps provider-specific response-format contracts outside AgentRuntime.
Architecture:
    - StructuredOutputPlan: Immutable result of provider planning.
    - ProviderStructuredOutputPlanner: Resolver for native formats and prompt fallback.
Relations:
    Used by vidbyte.agents.runtime when BaseAgent.output_schema is set.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from vidbyte.lib.enums import StructuredOutputMode
from vidbyte.lib.errors import ConfigurationError
from vidbyte.tools.output_schema import OutputSchemaValidator


@dataclass(frozen=True, slots=True)
class StructuredOutputPlan:
    """Provider call plan for one declared output schema."""

    response_format: Mapping[str, Any] | None = None
    use_prompt_hint: bool = False
    native_supported: bool = False
    provider: str = ""


class ProviderStructuredOutputPlanner:
    """Builds provider-native response formats or prompt fallback plans."""

    _COMPATIBLE_PROVIDERS = frozenset({"xai", "openrouter", "deepseek", "glm", "minimax"})

    def plan(self, *, provider: str, schema: type | Mapping[str, Any] | None, mode: StructuredOutputMode) -> StructuredOutputPlan:
        # Builds a provider-native response format when supported, otherwise chooses fallback behavior.
        if schema is None:
            return StructuredOutputPlan(provider=str(provider or ""))
        if mode is StructuredOutputMode.PROMPT:
            return StructuredOutputPlan(use_prompt_hint=True, provider=str(provider or ""))
        resolved = copy.deepcopy(dict(OutputSchemaValidator.resolve(schema)))
        response_format = self._response_format_for_provider(str(provider or ""), resolved)
        if response_format is None:
            return self._unsupported_plan(provider=str(provider or ""), mode=mode)
        return StructuredOutputPlan(response_format=response_format, native_supported=True, provider=str(provider or ""))

    def _unsupported_plan(self, *, provider: str, mode: StructuredOutputMode) -> StructuredOutputPlan:
        # Returns prompt fallback for AUTO mode and raises when native mode is explicitly required.
        if mode is StructuredOutputMode.NATIVE:
            raise ConfigurationError(f"Provider {provider!r} does not support native structured outputs.")
        return StructuredOutputPlan(use_prompt_hint=True, provider=provider)

    def _response_format_for_provider(self, provider: str, schema: Mapping[str, Any]) -> Mapping[str, Any] | None:
        # Dispatches to the provider-specific structured output shape.
        normalized = provider.lower()
        if "openai" in normalized or normalized.startswith("gpt"):
            return self._openai_response_format(schema)
        if "anthropic" in normalized or "claude" in normalized:
            return self._anthropic_response_format(schema)
        if "gemini" in normalized or "google" in normalized:
            return self._gemini_response_format(schema)
        if normalized in self._COMPATIBLE_PROVIDERS or "grok" in normalized:
            return self._compatible_response_format(schema)
        return None

    def _openai_response_format(self, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        # Builds the OpenAI Responses API text.format payload.
        return {"type": "json_schema", "name": "agent_output", "schema": copy.deepcopy(dict(schema)), "strict": True}

    def _compatible_response_format(self, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        # Builds the OpenAI-compatible chat completions response_format payload.
        return {"type": "json_schema", "json_schema": {"name": "agent_output", "schema": copy.deepcopy(dict(schema)), "strict": True}}

    def _anthropic_response_format(self, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        # Builds the Anthropic output_config.format payload.
        return {"type": "json_schema", "schema": copy.deepcopy(dict(schema))}

    def _gemini_response_format(self, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        # Builds the Gemini responseSchema payload value.
        return copy.deepcopy(dict(schema))


__all__ = ["ProviderStructuredOutputPlanner", "StructuredOutputPlan"]
