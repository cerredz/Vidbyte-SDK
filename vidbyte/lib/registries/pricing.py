"""Context Protocol Header

Description:
    Source-of-truth pricing table and lookup registry for provider text models.
Purpose:
    Centralizes per-model USD token rates so agent usage tracking can price model
    calls without scattering rate constants across providers or agents.
Architecture:
    - ModelPricing: Immutable per-model rate record (USD per million tokens).
    - PROVIDER_PRICING: Built-in rate table keyed by provider then model string.
    - ModelPricingRegistry: Resolves (provider, model) to rates with prefix
      matching and supports caller overrides.
Key Functions:
    - default: Builds a registry over the built-in PROVIDER_PRICING table.
    - resolve: Returns the ModelPricing for a provider/model, or None.
    - register: Adds or overrides rates for one provider/model entry.
Relations:
    Consumed by vidbyte/agents/pricing (per-provider cost formulas) and by
    BaseAgent(pricing=...) for caller-supplied overrides.
Similar Files:
    - vidbyte/lib/registries/models.py
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Per-model USD rates per million tokens; None marks unpriced components."""

    input_per_million: float
    output_per_million: float
    cache_read_per_million: float | None = None
    cache_write_per_million: float | None = None
    threshold_tokens: int | None = None
    input_over_threshold_per_million: float | None = None
    output_over_threshold_per_million: float | None = None


PRICING_AS_OF: str = "2026-07-22"

# Rates verified against official provider pricing pages on PRICING_AS_OF.
# Providers/models with unverifiable rates are omitted so cost resolves to None
# instead of a guessed number (GLM, MiniMax, OpenRouter marketplace models, and
# alias-only names such as grok-4).
PROVIDER_PRICING: dict[ModelProvider, dict[str, ModelPricing]] = {
    ModelProvider.OPENAI: {
        "gpt-5.6-sol": ModelPricing(input_per_million=5.0, output_per_million=30.0, cache_read_per_million=0.5),
        "gpt-5.6-terra": ModelPricing(input_per_million=2.5, output_per_million=15.0, cache_read_per_million=0.25),
        "gpt-5.6-luna": ModelPricing(input_per_million=1.0, output_per_million=6.0, cache_read_per_million=0.1),
        "gpt-5.5": ModelPricing(input_per_million=5.0, output_per_million=30.0, cache_read_per_million=0.5),
        "gpt-5.5-pro": ModelPricing(input_per_million=30.0, output_per_million=180.0),
        "gpt-5.4": ModelPricing(input_per_million=2.5, output_per_million=15.0, cache_read_per_million=0.25),
        "gpt-5.4-mini": ModelPricing(input_per_million=0.75, output_per_million=4.5, cache_read_per_million=0.075),
        "gpt-5.4-nano": ModelPricing(input_per_million=0.2, output_per_million=1.25, cache_read_per_million=0.02),
        "gpt-5.4-pro": ModelPricing(input_per_million=30.0, output_per_million=180.0),
    },
    ModelProvider.ANTHROPIC: {
        # claude-sonnet-5 introductory pricing, in effect through 2026-08-31.
        "claude-sonnet-5": ModelPricing(input_per_million=2.0, output_per_million=10.0, cache_read_per_million=0.2, cache_write_per_million=2.5),
        "claude-sonnet-4-6": ModelPricing(input_per_million=3.0, output_per_million=15.0, cache_read_per_million=0.3, cache_write_per_million=3.75),
        "claude-sonnet-4-5": ModelPricing(input_per_million=3.0, output_per_million=15.0, cache_read_per_million=0.3, cache_write_per_million=3.75),
        "claude-opus-4-8": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-opus-4-7": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-opus-4-6": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-opus-4-5": ModelPricing(input_per_million=5.0, output_per_million=25.0, cache_read_per_million=0.5, cache_write_per_million=6.25),
        "claude-haiku-4-5": ModelPricing(input_per_million=1.0, output_per_million=5.0, cache_read_per_million=0.1, cache_write_per_million=1.25),
    },
    ModelProvider.GEMINI: {
        "gemini-3.5-flash": ModelPricing(input_per_million=1.5, output_per_million=9.0, cache_read_per_million=0.15),
        "gemini-3.6-flash": ModelPricing(input_per_million=1.5, output_per_million=7.5, cache_read_per_million=0.15),
        "gemini-3.1-pro-preview": ModelPricing(input_per_million=2.0, output_per_million=12.0, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=18.0),
    },
    ModelProvider.XAI: {
        "grok-4.5": ModelPricing(input_per_million=2.0, output_per_million=6.0, cache_read_per_million=0.3, threshold_tokens=200_000, input_over_threshold_per_million=4.0, output_over_threshold_per_million=12.0),
        "grok-4.3": ModelPricing(input_per_million=1.25, output_per_million=2.5, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=2.5, output_over_threshold_per_million=5.0),
        "grok-build-0.1": ModelPricing(input_per_million=1.0, output_per_million=2.0, cache_read_per_million=0.2, threshold_tokens=200_000, input_over_threshold_per_million=2.0, output_over_threshold_per_million=4.0),
    },
    ModelProvider.DEEPSEEK: {
        "deepseek-v4-pro": ModelPricing(input_per_million=0.435, output_per_million=0.87, cache_read_per_million=0.003625),
        "deepseek-v4-flash": ModelPricing(input_per_million=0.14, output_per_million=0.28, cache_read_per_million=0.0028),
    },
    ModelProvider.GLM: {},
    ModelProvider.MINIMAX: {},
    ModelProvider.KIMI: {
        "kimi-k2.7-code": ModelPricing(input_per_million=0.95, output_per_million=4.0, cache_read_per_million=0.19),
        "kimi-k2.7-code-highspeed": ModelPricing(input_per_million=1.9, output_per_million=8.0, cache_read_per_million=0.38),
    },
    # OpenRouter models are priced per-generation by the marketplace; the SDK
    # prefers the provider-reported usage.cost over table math for this provider.
    ModelProvider.OPENROUTER: {},
}


class ModelPricingRegistry:
    """Resolves (provider, model) pairs to ModelPricing with override support."""

    _EMPTY_TABLE: ClassVar[dict[str, ModelPricing]] = {}

    def __init__(self, table: Mapping[ModelProvider, Mapping[str, ModelPricing]] | None = None) -> None:
        # Copy the source table so register() never mutates shared class state.
        source = table if table is not None else PROVIDER_PRICING
        self._table: dict[ModelProvider, dict[str, ModelPricing]] = {provider: dict(models) for provider, models in source.items()}

    @classmethod
    def default(cls) -> "ModelPricingRegistry":
        # Returns an independent registry over the built-in PROVIDER_PRICING table.
        return cls(PROVIDER_PRICING)

    def resolve(self, provider: ModelProvider | str, model: str) -> ModelPricing | None:
        # Returns exact or longest-prefix pricing for the model, else None.
        provider_enum = self._coerce_provider(provider)
        if provider_enum is None or not isinstance(model, str) or not model:
            return None
        models = self._table.get(provider_enum, self._EMPTY_TABLE)
        exact = models.get(model)
        if exact is not None:
            return exact
        prefix_matches = [(key, pricing) for key, pricing in models.items() if model.startswith(key)]
        if not prefix_matches:
            return None
        return max(prefix_matches, key=lambda item: len(item[0]))[1]

    def register(self, provider: ModelProvider | str, model: str, pricing: ModelPricing) -> None:
        # Adds or overrides one provider/model entry after validating inputs.
        provider_enum = self._coerce_provider(provider)
        if provider_enum is None:
            raise ConfigurationError(f"Unrecognized provider '{provider}'.")
        if not isinstance(model, str) or not model.strip():
            raise ConfigurationError("model must be a non-empty string.")
        if not isinstance(pricing, ModelPricing):
            raise ConfigurationError("pricing must be a ModelPricing instance.")
        self._table.setdefault(provider_enum, {})[model] = pricing

    @staticmethod
    def _coerce_provider(provider: ModelProvider | str) -> ModelProvider | None:
        # Converts provider strings to ModelProvider, returning None when unknown.
        if isinstance(provider, ModelProvider):
            return provider
        try:
            return ModelProvider(str(provider))
        except ValueError:
            return None


__all__ = [
    "ModelPricing",
    "ModelPricingRegistry",
    "PRICING_AS_OF",
    "PROVIDER_PRICING",
]
