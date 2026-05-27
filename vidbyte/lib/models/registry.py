"""Context Protocol Header

Description:
    Central registry mapping model providers to their default text models.
Purpose:
    Eliminates one-off provider-model dicts scattered across the SDK by providing
    a single authoritative source for default models and active model resolution.
Architecture:
    - ProviderModelRegistry: Class-level dict and helper methods for provider/model lookups.
Key Functions:
    - default_model: Returns the default model string for a given provider enum.
    - resolve_active: Returns the set of providers and models to use for a run.
    - validate_provider: Raises ConfigurationError if a provider string is unrecognized.
    - validate_model: Raises ConfigurationError if a model string is empty.
    - validate_provider_models_map: Validates all entries in a provider_models mapping.
Relations:
    Used by MultiProviderAgenticGraderRuntimeAlgorithm and
    MultiProviderAgenticGraderAlgorithm for model resolution and config validation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, ClassVar

from vidbyte.lib.config.constants import API_KEY_ENV_VARS
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError


class ProviderModelRegistry:
    """Central registry for default provider-to-model mappings and validation helpers."""

    DEFAULT_PROVIDER_MODELS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "gpt-5.5",
        ModelProvider.ANTHROPIC: "claude-sonnet-4-6",
        ModelProvider.GEMINI: "gemini-2.5-pro",
        ModelProvider.XAI: "grok-3",
        ModelProvider.DEEPSEEK: "deepseek-v3",
        ModelProvider.GLM: "glm-4-plus",
        ModelProvider.MINIMAX: "minimax-text-01",
    }

    @classmethod
    def default_model(cls, provider: ModelProvider) -> str:
        # Returns the canonical default model string for the given provider enum member.
        model = cls.DEFAULT_PROVIDER_MODELS.get(provider)
        if model is None:
            raise ConfigurationError(f"No default model registered for provider '{provider.value}'.")
        return model

    @classmethod
    def resolve_active(cls, provider_models: Mapping[str, str] | None, options: Mapping[str, Any] | None) -> dict[str, str]:
        # Returns {provider_name: model_name} for all providers with valid credentials.
        opts = options or {}
        if provider_models is not None:
            return cls._resolve_explicit(provider_models, opts)
        return cls._resolve_from_environment()

    @classmethod
    def validate_provider(cls, provider: str) -> None:
        # Raises ConfigurationError if provider is not a recognized ModelProvider value.
        try:
            ModelProvider(provider)
        except ValueError as exc:
            known = sorted(p.value for p in ModelProvider)
            raise ConfigurationError(
                f"Unrecognized provider '{provider}'. Known providers: {known}."
            ) from exc

    @classmethod
    def validate_model(cls, model: str) -> None:
        # Raises ConfigurationError if model is an empty or whitespace-only string.
        if not model or not model.strip():
            raise ConfigurationError("model must be a non-empty string.")

    @classmethod
    def validate_provider_models_map(cls, provider_models: Mapping[str, str]) -> None:
        # Raises ConfigurationError if any key is unrecognized or any value is empty.
        for provider, model in provider_models.items():
            cls.validate_provider(provider)
            cls.validate_model(model)

    @classmethod
    def _resolve_explicit(cls, provider_models: Mapping[str, str], opts: Mapping[str, Any]) -> dict[str, str]:
        # Builds the active-models dict for an explicit user-supplied provider_models mapping.
        active: dict[str, str] = {}
        for provider_name, model_name in provider_models.items():
            p_enum = ModelProvider(provider_name)
            env_var = API_KEY_ENV_VARS.get(p_enum)
            if env_var and not os.environ.get(env_var) and not opts.get("api_key"):
                raise ConfigurationError(
                    f"Missing API key for explicitly requested provider '{provider_name}'. Set {env_var}."
                )
            active[provider_name] = model_name
        return active

    @classmethod
    def _resolve_from_environment(cls) -> dict[str, str]:
        # Builds the active-models dict from all providers that have env-var API keys set.
        active: dict[str, str] = {}
        for provider_enum, model_name in cls.DEFAULT_PROVIDER_MODELS.items():
            env_var = API_KEY_ENV_VARS.get(provider_enum)
            if env_var and os.environ.get(env_var):
                active[provider_enum.value] = model_name
        if not active:
            raise ConfigurationError("No model providers have API keys configured in the environment.")
        return active


__all__ = [
    "ProviderModelRegistry",
]
