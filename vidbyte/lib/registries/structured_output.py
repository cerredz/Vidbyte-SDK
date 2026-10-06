"""Context Protocol Header

Description:
    Resolves configured structured-output support for a provider and model.
Purpose:
    Converts the fixed capability data in vidbyte.lib.configs.structured_output into a stable
    lookup API for providers and developer tooling. This module owns resolution and discovery,
    not capability declarations or provider-specific request payloads.
Architecture:
    - StructuredOutputRegistry.resolve: Resolves a provider/model to its declared enforcement tier.
    - StructuredOutputRegistry.describe: Returns the developer-facing description for that tier.
    - StructuredOutputRegistry.descriptions: Returns the complete documented tier catalog.
Key Functions:
    - resolve: Never raises for an unknown provider; it returns PROMPT_ONLY.
    - describe: Supplies a typed explanation and safe lower-tier fallback.
Relations:
    Consumed by vidbyte.providers.compatible; declarations live in vidbyte.lib.configs.structured_output.
Similar Files:
    - vidbyte/lib/registries/pricing.py: Same fixed-table, prefix-matched lookup shape.
"""

from __future__ import annotations

from typing import ClassVar

from vidbyte.lib.configs.structured_output import (
    MODEL_SUPPORT,
    PROVIDER_SUPPORT,
    STRUCTURED_OUTPUT_AS_OF,
    STRUCTURED_OUTPUT_DESCRIPTIONS,
    StructuredOutputDescription,
)
from vidbyte.lib.enums import ModelProvider, StructuredOutputSupport


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
    def describe(cls, provider: ModelProvider | str | None, model: str | None = None) -> StructuredOutputDescription:
        # Return the complete developer-facing explanation for an endpoint's resolved support tier.
        return STRUCTURED_OUTPUT_DESCRIPTIONS[cls.resolve(provider, model)]

    @classmethod
    def descriptions(cls) -> tuple[StructuredOutputDescription, ...]:
        # Return every supported tier so developer tooling can present capability choices consistently.
        return tuple(STRUCTURED_OUTPUT_DESCRIPTIONS[support] for support in StructuredOutputSupport)

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


__all__ = [
    "StructuredOutputRegistry",
    "StructuredOutputDescription",
    "PROVIDER_SUPPORT",
    "MODEL_SUPPORT",
    "STRUCTURED_OUTPUT_AS_OF",
    "STRUCTURED_OUTPUT_DESCRIPTIONS",
]
