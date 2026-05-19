from __future__ import annotations

import os
from enum import Enum

from vidbyte.lib.errors import ConfigurationError


class ModelProvider(str, Enum):
    """Supported model providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    XAI = "xai"


API_KEY_ENV_VARS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "OPENAI_API_KEY",
    ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    ModelProvider.GEMINI: "GEMINI_API_KEY",
    ModelProvider.XAI: "XAI_API_KEY",
}

DEFAULT_ENDPOINTS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: "https://api.openai.com/v1",
    ModelProvider.ANTHROPIC: "https://api.anthropic.com/v1",
    ModelProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta",
    ModelProvider.XAI: "https://api.x.ai/v1",
}


def coerce_provider(provider: ModelProvider | str) -> ModelProvider:
    try:
        return provider if isinstance(provider, ModelProvider) else ModelProvider(provider)
    except ValueError as exc:
        raise ConfigurationError(f"Unsupported model provider: {provider!r}") from exc


def resolve_api_key(provider: ModelProvider, explicit_api_key: str | None) -> str:
    if explicit_api_key and explicit_api_key.strip():
        return explicit_api_key.strip()

    env_var = API_KEY_ENV_VARS[provider]
    env_value = os.environ.get(env_var)
    if env_value and env_value.strip():
        return env_value.strip()

    raise ConfigurationError(
        f"Missing API key for provider {provider.value}. Pass api_key or set {env_var}."
    )


def default_endpoint(provider: ModelProvider, endpoint: str | None) -> str:
    if endpoint and endpoint.strip():
        return endpoint.strip().rstrip("/")
    return DEFAULT_ENDPOINTS[provider]


def validate_temperature(temperature: float | None) -> None:
    if temperature is None:
        return
    if temperature < 0 or temperature > 2:
        raise ConfigurationError("temperature must be between 0 and 2.")


def validate_positive_int(value: int | None, *, field_name: str) -> None:
    if value is None:
        return
    if value <= 0:
        raise ConfigurationError(f"{field_name} must be greater than zero.")


def validate_positive_float(value: float | None, *, field_name: str) -> None:
    if value is None:
        return
    if value <= 0:
        raise ConfigurationError(f"{field_name} must be greater than zero.")
