"""Context Protocol Header

Description:
    Source-of-truth table and lookup registry for per-endpoint structured-output support.
Purpose:
    Centralizes which enforcement tier each (provider, model) pair actually offers, so the runtime
    picks a request shape a provider accepts instead of inferring one from the provider's name.
Architecture:
    - PROVIDER_SUPPORT: Built-in per-provider default tier.
    - MODEL_SUPPORT: Per-model prefix overrides where support depends on the model's vintage.
    - StructuredOutputRegistry: Resolves (provider, model) to a tier, defaulting to PROMPT_ONLY.
Key Functions:
    - resolve: Returns the StructuredOutputSupport tier for a provider/model pair.
Relations:
    Consumed by vidbyte.agents.runtime when an agent declares an output_schema, and by
    vidbyte.providers.output_schema when deciding which constraints survive onto the wire.
Similar Files:
    - vidbyte/lib/registries/pricing.py: Same fixed-table, prefix-matched lookup shape.
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.enums import ModelProvider, StructuredOutputSupport

STRUCTURED_OUTPUT_AS_OF: str = "2026-07-28"

# @intent declare-support-never-infer-it
# Substring-matching a provider's name silently produced a payload DeepSeek rejects and one Mistral
# happens to accept. Tiers below were verified against each vendor's own documentation on
# STRUCTURED_OUTPUT_AS_OF; a provider whose support could not be verified is deliberately omitted so
# it resolves to PROMPT_ONLY (degraded but working) instead of a request the endpoint would reject.
PROVIDER_SUPPORT: dict[ModelProvider, StructuredOutputSupport] = {
    ModelProvider.OPENAI: StructuredOutputSupport.NATIVE_SCHEMA,
    ModelProvider.GEMINI: StructuredOutputSupport.NATIVE_SCHEMA,
    ModelProvider.MISTRAL: StructuredOutputSupport.NATIVE_SCHEMA,
    # Native JSON outputs are GA on Claude 4.5 and later; older models are handled in MODEL_SUPPORT.
    ModelProvider.ANTHROPIC: StructuredOutputSupport.NATIVE_SCHEMA,
    # DeepSeek rejects response_format.type=json_schema but honours json_object JSON mode.
    ModelProvider.DEEPSEEK: StructuredOutputSupport.JSON_MODE,
    ModelProvider.XAI: StructuredOutputSupport.JSON_MODE,
    ModelProvider.GLM: StructuredOutputSupport.JSON_MODE,
    ModelProvider.KIMI: StructuredOutputSupport.JSON_MODE,
    ModelProvider.MINIMAX: StructuredOutputSupport.JSON_MODE,
    # Llama exposes no structured-output API of its own; support belongs to whoever serves it.
    ModelProvider.META: StructuredOutputSupport.PROMPT_ONLY,
    # A marketplace route resolves to an arbitrary upstream, so no tier can be promised.
    ModelProvider.OPENROUTER: StructuredOutputSupport.PROMPT_ONLY,
}

# Model-prefix overrides, checked longest-first, for endpoints whose tier depends on model vintage.
MODEL_SUPPORT: dict[ModelProvider, dict[str, StructuredOutputSupport]] = {
    ModelProvider.ANTHROPIC: {
        "claude-3": StructuredOutputSupport.STRICT_TOOLS,
        "claude-4-opus": StructuredOutputSupport.STRICT_TOOLS,
        "claude-4-sonnet": StructuredOutputSupport.STRICT_TOOLS,
        "claude-4-haiku": StructuredOutputSupport.STRICT_TOOLS,
    },
}


class StructuredOutputRegistry:
    """Resolves how strongly a given provider and model can enforce a declared output schema."""

    _PROVIDER_SUPPORT: ClassVar[dict[ModelProvider, StructuredOutputSupport]] = PROVIDER_SUPPORT
    _MODEL_SUPPORT: ClassVar[dict[ModelProvider, dict[str, StructuredOutputSupport]]] = MODEL_SUPPORT

    @classmethod
    def resolve(cls, provider: ModelProvider | str | None, model: str | None = None) -> StructuredOutputSupport:
        # Returns the strongest tier this endpoint is known to support, never raising on an unknown one.
        resolved = cls._provider(provider)
        if resolved is None:
            return StructuredOutputSupport.PROMPT_ONLY
        override = cls._model_override(resolved, model)
        if override is not None:
            return override
        return cls._PROVIDER_SUPPORT.get(resolved, StructuredOutputSupport.PROMPT_ONLY)

    @classmethod
    def _provider(cls, provider: ModelProvider | str | None) -> ModelProvider | None:
        # Coerces a provider value to the enum, returning None for anything this SDK does not know.
        if isinstance(provider, ModelProvider):
            return provider
        if not provider:
            return None
        try:
            return ModelProvider(str(provider).lower())
        except ValueError:
            return None

    @classmethod
    def _model_override(cls, provider: ModelProvider, model: str | None) -> StructuredOutputSupport | None:
        # Returns the tier for the longest registered model prefix this model name starts with.
        overrides = cls._MODEL_SUPPORT.get(provider)
        if not overrides or not model:
            return None
        normalized = str(model).lower()
        matches = [prefix for prefix in overrides if normalized.startswith(prefix)]
        if not matches:
            return None
        return overrides[max(matches, key=len)]


__all__ = ["StructuredOutputRegistry", "PROVIDER_SUPPORT", "MODEL_SUPPORT", "STRUCTURED_OUTPUT_AS_OF"]
