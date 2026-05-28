"""Context Protocol Header

Description:
    Central registry mapping model providers to their default text models and configurations.
Purpose:
    Eliminates one-off provider-model dicts and environment resolution scattered across the SDK.
Architecture:
    - ProviderModelRegistry: Centralized model definitions, endpoints, API keys, and lookup methods.
Key Functions:
    - default_model: Returns the default model string for a given provider enum.
    - get_api_key_env_var: Retrieves the API key environment variable name.
    - get_default_endpoint: Retrieves the default endpoint for a provider.
    - resolve_api_key: Resolves explicit API key or retrieves environment variable.
    - resolve_endpoint: Resolves explicit endpoint or defaults to standard URL.
    - get_supported_providers: Gets list of supported provider strings.
    - get_supported_models: Gets list of default model strings.
    - resolve_active: Returns the set of providers and models to use for a run.
    - validate_provider: Raises ConfigurationError if a provider string is unrecognized.
    - validate_model: Raises ConfigurationError if a model string is empty.
    - validate_provider_models_map: Validates all entries in a provider_models mapping.
Relations:
    Used by MultiProviderAgenticGraderRuntimeAlgorithm, MultiProviderAgenticGraderAlgorithm,
    and client configurations (TextModelConfig, ImageModelConfig, VideoModelConfig).
Similar Files:
    - vidbyte/lib/config/constants.py
    - vidbyte/lib/dataclasses/model_configs.py
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, ClassVar

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
        ModelProvider.OPENROUTER: "openrouter/auto",
    }

    API_KEY_ENV_VARS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "OPENAI_API_KEY",
        ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        ModelProvider.GEMINI: "GEMINI_API_KEY",
        ModelProvider.XAI: "XAI_API_KEY",
        ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        ModelProvider.GLM: "GLM_API_KEY",
        ModelProvider.MINIMAX: "MINIMAX_API_KEY",
        ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
    }

    DEFAULT_ENDPOINTS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.ANTHROPIC: "https://api.anthropic.com/v1",
        ModelProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
        ModelProvider.XAI: "https://api.x.ai/v1",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
        ModelProvider.GLM: "https://open.bigmodel.cn/api/paas/v4",
        ModelProvider.MINIMAX: "https://api.minimax.io/v1",
        ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    }

    @classmethod
    def default_model(cls, provider: ModelProvider) -> str:
        # Returns the canonical default model string for the given provider enum member.
        model = cls.DEFAULT_PROVIDER_MODELS.get(provider)
        if model is None:
            raise ConfigurationError(f"No default model registered for provider '{provider.value}'.")
        return model

    @classmethod
    def get_api_key_env_var(cls, provider: ModelProvider | str) -> str:
        # Returns the environment variable name configured for the given provider.
        try:
            p_enum = provider if isinstance(provider, ModelProvider) else ModelProvider(provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unrecognized provider '{provider}'.") from exc
        env_var = cls.API_KEY_ENV_VARS.get(p_enum)
        if not env_var:
            raise ConfigurationError(f"No API key environment variable registered for provider '{p_enum.value}'.")
        return env_var

    @classmethod
    def get_default_endpoint(cls, provider: ModelProvider | str) -> str:
        # Returns the default HTTP endpoint URL configured for the given provider.
        try:
            p_enum = provider if isinstance(provider, ModelProvider) else ModelProvider(provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unrecognized provider '{provider}'.") from exc
        endpoint = cls.DEFAULT_ENDPOINTS.get(p_enum)
        if not endpoint:
            raise ConfigurationError(f"No default endpoint registered for provider '{p_enum.value}'.")
        return endpoint

    @classmethod
    def resolve_api_key(cls, provider: ModelProvider | str, explicit_key: str | None) -> str:
        # Resolves and returns the explicit key or resolves the env-var key if missing.
        if explicit_key and explicit_key.strip():
            return explicit_key.strip()
        env_var = cls.get_api_key_env_var(provider)
        env_value = os.environ.get(env_var)
        if env_value and env_value.strip():
            return env_value.strip()
        p_name = provider.value if isinstance(provider, ModelProvider) else provider
        raise ConfigurationError(f"Missing API key for provider {p_name}. Pass api_key or set {env_var}.")

    @classmethod
    def resolve_endpoint(cls, provider: ModelProvider | str, explicit_endpoint: str | None) -> str:
        # Resolves and returns the explicit endpoint or falls back to the default provider endpoint.
        if explicit_endpoint and explicit_endpoint.strip():
            return explicit_endpoint.strip().rstrip("/")
        return cls.get_default_endpoint(provider)

    @classmethod
    def get_supported_providers(cls) -> list[str]:
        # Returns the list of all supported provider string values in the registry.
        return sorted(p.value for p in ModelProvider)

    @classmethod
    def get_supported_models(cls) -> list[str]:
        # Returns the list of default model identifiers across all registered providers.
        return sorted(list(cls.DEFAULT_PROVIDER_MODELS.values()))

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
            known = cls.get_supported_providers()
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
            env_var = cls.API_KEY_ENV_VARS.get(p_enum)
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
            env_var = cls.API_KEY_ENV_VARS.get(provider_enum)
            if env_var and os.environ.get(env_var):
                active[provider_enum.value] = model_name
        if not active:
            raise ConfigurationError("No model providers have API keys configured in the environment.")
        return active


__all__ = [
    "ProviderModelRegistry",
]

