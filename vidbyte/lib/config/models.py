from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vidbyte.lib.config.base import (
    ModelProvider,
    coerce_provider,
    default_endpoint,
    resolve_api_key,
    validate_positive_float,
    validate_positive_int,
    validate_temperature,
)
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError


@dataclass(frozen=True, slots=True)
class TextModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    system: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    response_format: dict[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 60.0

    def normalized_provider(self) -> ModelProvider:
        return coerce_provider(self.provider)

    def validate(self) -> None:
        provider = self.normalized_provider()
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        validate_temperature(self.temperature)
        validate_positive_int(self.max_output_tokens, field_name="max_output_tokens")
        validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        resolve_api_key(provider, self.api_key)

    def resolved_api_key(self) -> str:
        return resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        return default_endpoint(self.normalized_provider(), self.endpoint)


@dataclass(frozen=True, slots=True)
class ImageModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    size: str | None = None
    quality: str | None = None
    response_format: str | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        return coerce_provider(self.provider)

    def validate(self) -> None:
        provider = self.normalized_provider()
        if provider not in {ModelProvider.OPENAI, ModelProvider.XAI}:
            raise UnsupportedProviderError(
                "ImageModelRunner currently supports OpenAI and xAI image APIs.",
                details={"provider": provider.value},
            )
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        resolve_api_key(provider, self.api_key)

    def resolved_api_key(self) -> str:
        return resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        return default_endpoint(self.normalized_provider(), self.endpoint)


@dataclass(frozen=True, slots=True)
class VideoModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    size: str | None = None
    seconds: int | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        return coerce_provider(self.provider)

    def validate(self) -> None:
        provider = self.normalized_provider()
        if provider != ModelProvider.OPENAI:
            raise UnsupportedProviderError(
                "VideoModelRunner currently supports OpenAI video jobs only.",
                details={"provider": provider.value},
            )
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        validate_positive_int(self.seconds, field_name="seconds")
        validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        resolve_api_key(provider, self.api_key)

    def resolved_api_key(self) -> str:
        return resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        return default_endpoint(self.normalized_provider(), self.endpoint)
