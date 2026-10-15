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
    - find_vidbyte_api_key: Returns the Vidbyte key the text key fall-through selects, or None for BYOK.
    - vidbyte_key_follows_provider: Reports whether a key is a Vidbyte key the gateway serves for a provider.
    - resolve_vidbyte_api_key: Resolves and checks the live Vidbyte key a managed call sends.
    - resolve_endpoint: Resolves explicit endpoint or defaults to standard URL.
    - get_supported_providers: Gets list of supported provider strings.
    - is_valid_provider: Reports whether a provider string is one the SDK offers.
    - resolve_provider: Coerces a provider string to ModelProvider, or None.
    - get_supported_models: Gets the default model strings or one provider's catalog.
    - normalize_model: Resolves provider-scoped model aliases for lookup callers.
    - is_supported_model: Reports whether a provider/model pair is catalogued.
    - resolve_active: Returns the set of providers and models to use for a run.
    - validate_provider: Raises ConfigurationError if a provider string is unrecognized.
    - validate_model: Raises ConfigurationError if a model string is empty or unrecognized.
    - validate_provider_models_map: Validates all entries in a provider_models mapping.
    - known_models: Returns every model identifier the SDK has a registered runner for.
    - models_for_provider: Returns the catalogued model identifiers for one provider.
    - provider_for_model: Returns the provider a catalogued model belongs to, or None.
    - validate_provider_model_pair: Raises unless a model is catalogued under its provider.
    - require_openrouter_for_routed_model: Raises when an 'openrouter/<vendor>/<model>' slug names another provider.
Relations:
    Used by MultiProviderAgenticGraderRuntimeAlgorithm, MultiProviderAgenticGraderAlgorithm,
    and client configurations (TextModelConfig, ImageModelConfig, VideoModelConfig).
Similar Files:
    - vidbyte/lib/config/constants.py
    - vidbyte/lib/dataclasses/model_configs.py
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any, ClassVar

from vidbyte.lib.agents.modality_detector import ModalityDetector
from vidbyte.lib.constants.jev import (
    VIDBYTE_API_KEY_ENV_VAR,
    VIDBYTE_API_KEY_PATTERN,
    VIDBYTE_API_KEY_PREFIX,
    VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND,
    VIDBYTE_MANAGED_TEXT_PROVIDERS,
)
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
        ModelProvider.TYPESAFE: "jev-latest",
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
        ModelProvider.TYPESAFE: "TYPESAFE_API_KEY",
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
        ModelProvider.TYPESAFE: "https://api.typesafe.ai/v1",
    }

    MODEL_ALIASES: ClassVar[dict[ModelProvider, dict[str, str]]] = {
        ModelProvider.OPENAI: {"gpt-5.6": "gpt-5.6-sol"},
    }

    OPENAI_CATALOG: ClassVar[tuple[str, ...]] = (
        "gpt-5.5",
        "gpt-5.6",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-6-astra",
        "gpt-6.1-sol",
        "gpt-6-sol",
        "gpt-6-luna",
    )

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
    def find_vidbyte_api_key(cls, provider: ModelProvider | str, explicit_key: str | None) -> str | None:
        """Return the Vidbyte key the text key fall-through selects, or None when the call stays on the caller's own provider key."""
        # @intent byok-key-wins-and-vidbyte-key-fills-in-last
        # A provider key the caller holds keeps that provider
        # unbilled, so steps 1-2 are managed only for a
        # Vidbyte-prefixed key, and VIDBYTE_API_KEY fills in
        # only for a provider the gateway serves.
        if explicit_key is not None and not isinstance(explicit_key, str):
            return None
        explicit = (explicit_key or "").strip()
        if explicit:
            return explicit if explicit.startswith(VIDBYTE_API_KEY_PREFIX) else None
        env_value = os.environ.get(cls.get_api_key_env_var(provider), "").strip()
        if env_value:
            return env_value if env_value.startswith(VIDBYTE_API_KEY_PREFIX) else None
        p_enum = provider if isinstance(provider, ModelProvider) else ModelProvider(provider)
        if p_enum not in VIDBYTE_MANAGED_TEXT_PROVIDERS:
            return None
        return os.environ.get(VIDBYTE_API_KEY_ENV_VAR, "").strip() or None

    @classmethod
    def vidbyte_key_follows_provider(cls, api_key: object, provider: str) -> bool:
        """Return True when api_key is a Vidbyte key and the Vidbyte gateway serves provider, so the key may follow a vendor switch."""
        # @intent vidbyte-key-may-cross-to-a-managed-provider
        # A Vidbyte key is not a vendor secret: it only ever goes to the
        # gateway, which serves every managed provider with it. A vendor
        # key, or any key for a provider the gateway does not serve, stays put.
        if not isinstance(api_key, str) or not api_key.strip().startswith(VIDBYTE_API_KEY_PREFIX):
            return False
        return cls.resolve_provider(provider) in VIDBYTE_MANAGED_TEXT_PROVIDERS

    @classmethod
    def resolve_vidbyte_api_key(cls, explicit_key: str | None) -> str:
        """Return the live Vidbyte key a managed call sends: the explicit key, otherwise VIDBYTE_API_KEY, both stripped."""
        # @intent managed-key-is-a-checked-live-vidbyte-key
        # The gateway admits only live keys, so a missing or malformed
        # key fails here, before any request, with the messages the
        # managed Jev path has always raised; text and Jev share it.
        key = ((explicit_key or "").strip() or os.environ.get(VIDBYTE_API_KEY_ENV_VAR, "")).strip()
        details = {"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND}
        if not key:
            raise ConfigurationError(f"Missing Vidbyte API key. Pass api_key or set {VIDBYTE_API_KEY_ENV_VAR}.", details=details)
        if re.fullmatch(VIDBYTE_API_KEY_PATTERN, key) is None:
            raise ConfigurationError(f"The managed Vidbyte API key must be a live key in the {VIDBYTE_API_KEY_PREFIX} format.", details=details)
        return key

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
    def is_valid_provider(cls, provider: str) -> bool:
        # Non-raising counterpart to validate_provider, for callers that branch on
        # provider support rather than failing. Accepts the same surrounding
        # whitespace and casing that resolve_provider tolerates.
        return cls.resolve_provider(provider) is not None

    @classmethod
    def resolve_provider(cls, provider: str) -> ModelProvider | None:
        # Coerces a provider string to the enum the pricing registries key on, or
        # None. Centralizing the coercion keeps every caller from re-deciding how
        # to normalize, which is how a raw string silently misses a price lookup.
        try:
            return ModelProvider(str(provider).strip().lower())
        except ValueError:
            return None

    @classmethod
    def get_supported_models(cls, provider: ModelProvider | str | None = None) -> list[str]:
        # Returns default models or the catalogued identifiers for one provider.
        if provider is not None:
            return list(cls.models_for_provider(provider))
        return sorted(set(cls.DEFAULT_PROVIDER_MODELS.values()) | set(cls.OPENAI_CATALOG))

    @classmethod
    def normalize_model(cls, provider: ModelProvider | str, model: str) -> str:
        # Resolves a provider-scoped alias without changing the caller's request config.
        p_enum = cls._require_provider(provider)
        if not isinstance(model, str) or not model.strip():
            raise ConfigurationError("model must be a non-empty string.")
        raw_model = model.strip()
        provider_prefix = f"{p_enum.value}/"
        lookup_model = raw_model[len(provider_prefix):] if raw_model.lower().startswith(provider_prefix) else raw_model
        # @intent normalized-model-drops-its-own-provider-prefix
        # The provider's catalog holds bare names, so an unaliased 'openai/gpt-5.5' must come back as
        # 'gpt-5.5' too, or is_supported_model rejects it (and 'openrouter/auto', the provider's own default).
        return cls.MODEL_ALIASES.get(p_enum, {}).get(lookup_model.lower(), lookup_model)

    @classmethod
    def is_supported_model(cls, provider: ModelProvider | str, model: str) -> bool:
        # Reports whether the provider owns the model after alias normalization.
        try:
            p_enum = cls._require_provider(provider)
            normalized = cls.normalize_model(p_enum, model)
        except ConfigurationError:
            return False
        return normalized.lower() in {name.lower() for name in cls.models_for_provider(p_enum)}

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
        # Delegates coercion so this and is_valid_provider can never disagree.
        if cls.resolve_provider(provider) is None:
            known = cls.get_supported_providers()
            raise ConfigurationError(
                f"Unrecognized provider '{provider}'. Known providers: {known}."
            )

    @classmethod
    def _require_provider(cls, provider: ModelProvider | str) -> ModelProvider:
        # Coerces a provider for alias and catalog helpers, raising one shared error shape.
        resolved = cls.resolve_provider(provider.value if isinstance(provider, ModelProvider) else str(provider))
        if resolved is None:
            raise ConfigurationError(
                f"Unrecognized provider '{provider}'.",
                details={"provider": str(provider), "known_providers": cls.get_supported_providers()},
            )
        return resolved

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
        # @intent openrouter-slugs-pass-ownership-check
        # OpenRouter routes to other vendors, so its 'anthropic/claude-sonnet-5' style ids name a model
        # another provider owns; the runner accepts them, so the vendor prefix is not a conflict here.
        if name == ModelProvider.OPENROUTER.value and "/" in model:
            return
        # Refuse an 'openrouter/<vendor>/<model>' slug declared under another vendor, which would reach that vendor verbatim.
        cls.require_openrouter_for_routed_model(name, model)
        owner = cls.provider_for_model(model)
        if owner is not None and owner != name:
            raise ConfigurationError(
                f"Model '{model.strip()}' is registered under provider '{owner}', not '{name}'.",
                details={"model": model.strip(), "declared_provider": name, "registered_provider": owner},
            )

    @classmethod
    def require_openrouter_for_routed_model(cls, provider: ModelProvider | str, model: str) -> None:
        """Raise when an 'openrouter/<vendor>/<model>' slug is declared under any provider other than OpenRouter."""
        # @intent openrouter-routed-ids-stay-with-openrouter
        # Validation now accepts 'openrouter/<vendor>/<model>', but only OpenRouter strips that prefix;
        # declared under another vendor the Runner would send the prefixed id to it, so it stays rejected.
        name = (provider.value if isinstance(provider, ModelProvider) else str(provider)).strip().lower()
        openrouter = ModelProvider.OPENROUTER.value
        lowered = str(model or "").strip().lower()
        if name != openrouter and lowered.startswith(f"{openrouter}/") and "/" in lowered[len(openrouter) + 1:]:
            raise ConfigurationError(
                f"Model '{model.strip()}' is registered under provider '{openrouter}', not '{name}'.",
                details={"model": model.strip(), "declared_provider": name, "registered_provider": openrouter},
            )

    @staticmethod
    def _catalog_name(model: str) -> str:
        # Normalizes a model identifier to its catalog form, matching ModalityDetector's convention.
        name = (model or "").strip().lower()
        # @intent openrouter-slug-validates-as-its-vendor-model
        # Like the Runner, drop 'openrouter/' only when a vendor/model slug follows it, so
        # 'openrouter/anthropic/claude-sonnet-5' checks as 'claude-sonnet-5' while 'openrouter/auto' stays whole.
        openrouter_prefix = f"{ModelProvider.OPENROUTER.value}/"
        if name.startswith(openrouter_prefix) and "/" in name[len(openrouter_prefix):]:
            name = name[len(openrouter_prefix):]
        return name.split("/", 1)[1] if "/" in name and not name.startswith(openrouter_prefix) else name

    @classmethod
    def validate_provider_models_map(cls, provider_models: Mapping[str, str]) -> None:
        # Raises ConfigurationError if any key is unrecognized or any value is empty.
        for provider, model in provider_models.items():
            cls.validate_provider(provider)
            cls.validate_model(model)
            # Keep an 'openrouter/<vendor>/<model>' slug from being mapped to another vendor's runner.
            cls.require_openrouter_for_routed_model(provider, model)

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

