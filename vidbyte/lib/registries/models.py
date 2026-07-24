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
    - validate_model: Raises ConfigurationError if a model string is empty or unrecognized.
    - validate_provider_models_map: Validates all entries in a provider_models mapping.
    - known_models: Returns every model identifier the SDK has a registered runner for.
    - models_for_provider: Returns the catalogued model identifiers for one provider.
    - provider_for_model: Returns the provider a catalogued model belongs to, or None.
    - validate_provider_model_pair: Raises unless a model is catalogued under its provider.
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

from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.constants.runners import MODEL_PROVIDER_RUNNER_TYPE_MAP, MODEL_RUNNER_TYPE_MAP
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import ConfigurationError


class ProviderModelRegistry:
    """Central registry for default provider-to-model mappings and validation helpers."""

    # Single switch governing whether an uncatalogued model is rejected or passed through.
    # Set False to accept any non-blank model name, e.g. to use a model released after this pin.
    STRICT_MODEL_VALIDATION: ClassVar[bool] = True

    DEFAULT_PROVIDER_MODELS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "gpt-5.6-sol",
        ModelProvider.ANTHROPIC: "claude-sonnet-5",
        ModelProvider.GEMINI: "gemini-3.5-flash",
        ModelProvider.XAI: "grok-4.5",
        ModelProvider.DEEPSEEK: "deepseek-v4-pro",
        ModelProvider.GLM: "glm-5.2",
        ModelProvider.MINIMAX: "MiniMax-M3",
        ModelProvider.KIMI: "kimi-k2.7-code",
        ModelProvider.META: "muse-spark-1.1",
        ModelProvider.MISTRAL: "mistral-medium-latest",
        ModelProvider.OPENROUTER: "openrouter/auto",
        ModelProvider.ELEVENLABS: "eleven_multilingual_v2",
        ModelProvider.PLAYAI: "PlayDialog",
    }

    API_KEY_ENV_VARS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "OPENAI_API_KEY",
        ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        ModelProvider.GEMINI: "GEMINI_API_KEY",
        ModelProvider.XAI: "XAI_API_KEY",
        ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        ModelProvider.GLM: "GLM_API_KEY",
        ModelProvider.MINIMAX: "MINIMAX_API_KEY",
        ModelProvider.KIMI: "MOONSHOT_API_KEY",
        ModelProvider.META: "META_API_KEY",
        ModelProvider.MISTRAL: "MISTRAL_API_KEY",
        ModelProvider.OPENROUTER: "OPENROUTER_API_KEY",
        ModelProvider.ELEVENLABS: "ELEVENLABS_API_KEY",
        ModelProvider.PLAYAI: "PLAYAI_API_KEY",
    }

    DEFAULT_ENDPOINTS: ClassVar[dict[ModelProvider, str]] = {
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.ANTHROPIC: "https://api.anthropic.com/v1",
        ModelProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
        ModelProvider.XAI: "https://api.x.ai/v1",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
        ModelProvider.GLM: "https://open.bigmodel.cn/api/paas/v4",
        ModelProvider.MINIMAX: "https://api.minimax.io/v1",
        ModelProvider.KIMI: "https://api.moonshot.ai/v1",
        ModelProvider.META: "https://api.meta.ai/v1",
        ModelProvider.MISTRAL: "https://api.mistral.ai/v1",
        ModelProvider.OPENROUTER: "https://openrouter.ai/api/v1",
        ModelProvider.ELEVENLABS: "https://api.elevenlabs.io/v1",
        ModelProvider.PLAYAI: "https://api.play.ai/api/v1",
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
    def known_models(cls) -> frozenset[str]:
        # Returns every normalized model identifier the SDK has a registered runner for.
        bare = {name.strip().lower() for name in MODEL_RUNNER_TYPE_MAP}
        qualified = {key.split("/", 1)[1] for key in MODEL_PROVIDER_RUNNER_TYPE_MAP if "/" in key}
        return frozenset(bare | {name.strip().lower() for name in qualified})

    @classmethod
    def models_for_provider(cls, provider: ModelProvider | str) -> tuple[str, ...]:
        # Returns the catalogued model identifiers registered under one provider, sorted.
        name = (provider.value if isinstance(provider, ModelProvider) else str(provider)).strip().lower()
        prefix = f"{name}/"
        return tuple(sorted(key.split("/", 1)[1] for key in MODEL_PROVIDER_RUNNER_TYPE_MAP if key.lower().startswith(prefix)))

    @classmethod
    def provider_for_model(cls, model: str) -> str | None:
        # Returns the provider a catalogued model is registered under, or None when uncatalogued.
        target = (model or "").strip().lower()
        if not target:
            return None
        for key in MODEL_PROVIDER_RUNNER_TYPE_MAP:
            provider, _, name = key.lower().partition("/")
            if name == target or key.lower() == target:
                return provider
        return None

    @classmethod
    def validate_model(cls, model: str) -> None:
        # @intent strict-model-allowlist
        # Rejecting an uncatalogued model at validation time turns a late provider 400 into an
        # actionable error naming the model; flip STRICT_MODEL_VALIDATION to restore name-only checks.
        if not model or not model.strip():
            raise ConfigurationError("model must be a non-empty string.")
        if not cls.STRICT_MODEL_VALIDATION:
            return
        if cls._catalog_name(model) not in cls.known_models():
            raise ConfigurationError(
                f"Unrecognized model '{model.strip()}'. The SDK has no registered runner for it.",
                details={"model": model.strip(), "known_model_count": len(cls.known_models())},
            )

    @classmethod
    def validate_provider_model_pair(cls, provider: ModelProvider | str, model: str) -> None:
        # Raises unless the model is catalogued under the provider the caller declared alongside it.
        cls.validate_model(model)
        if not cls.STRICT_MODEL_VALIDATION:
            return
        name = (provider.value if isinstance(provider, ModelProvider) else str(provider)).strip().lower()
        owner = cls.provider_for_model(model)
        if owner is not None and owner != name:
            raise ConfigurationError(
                f"Model '{model.strip()}' is registered under provider '{owner}', not '{name}'.",
                details={"model": model.strip(), "declared_provider": name, "registered_provider": owner},
            )

    @staticmethod
    def _catalog_name(model: str) -> str:
        # Normalizes a model identifier to its catalog form, matching ModalityDetector's convention.
        name = (model or "").strip().lower()
        return name.split("/", 1)[1] if "/" in name and not name.startswith("openrouter/") else name

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
            if ModalityDetector.detect_modality(model_name) is not ModelModality.TEXT:
                continue
            env_var = cls.API_KEY_ENV_VARS.get(provider_enum)
            if env_var and os.environ.get(env_var):
                active[provider_enum.value] = model_name
        if not active:
            raise ConfigurationError("No model providers have API keys configured in the environment.")
        return active


__all__ = [
    "ProviderModelRegistry",
]

