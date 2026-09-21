"""Context Protocol Header

Description:
    Model execution configuration dataclasses for text, image, and video models.
Purpose:
    Stores model configurations and delegates API key and endpoint validation and resolution to ProviderModelRegistry.
Architecture:
    - TextModelConfig: dataclass for text/chat completions.
    - ImageModelConfig: dataclass for image generation.
    - VideoModelConfig: dataclass for video generation tasks.
    - DecisionModelConfig: dataclass for calibrated decision models (TypeSafe Jev).
Key Functions:
    - resolved_api_key: Resolves provider key by delegating to ProviderModelRegistry.
    - resolved_endpoint: Resolves provider endpoint by delegating to ProviderModelRegistry.
Relations:
    Used by runners, agents, and strategies to initialize model executions.
Similar Files:
    - vidbyte/lib/models/registry.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from vidbyte.lib.constants.jev import JEV_DEFAULT_MODEL, JEV_DEFAULT_RETRY_COUNT, JEV_DEFAULT_TIMEOUT_SECONDS, JEV_NO_RETRIES, JEV_TIMEOUT_FLOOR_SECONDS
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.registries.models import ProviderModelRegistry


@dataclass(frozen=True, slots=True)
class TextModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    system: str | None = None
    messages: tuple[Mapping[str, Any], ...] = ()
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    stop_sequences: tuple[str, ...] = ()
    response_format: Mapping[str, Any] | None = None
    tools: tuple[Mapping[str, Any], ...] = ()
    tool_choice: str | Mapping[str, Any] | None = None
    tool_config: Mapping[str, Any] | None = None
    safety_settings: tuple[Mapping[str, Any], ...] = ()
    cached_content: str | None = None
    thinking_config: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 60.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate request shape before provider code builds API payloads.
        self._require_model()
        self._validate_temperature()
        self._validate_top_p()
        self._validate_positive_int(self.max_output_tokens, field_name="max_output_tokens")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _require_model(self) -> None:
        # Model names are required by every provider adapter.
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")

    def _validate_temperature(self) -> None:
        # Most provider APIs accept temperature values in the inclusive 0-2 range.
        if self.temperature is not None and (self.temperature < 0 or self.temperature > 2):
            raise ConfigurationError("temperature must be between 0 and 2.")

    def _validate_top_p(self) -> None:
        # Keep nucleus sampling probability in its expected 0-1 range.
        if self.top_p is not None and (self.top_p < 0 or self.top_p > 1):
            raise ConfigurationError("top_p must be between 0 and 1.")

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


@dataclass(frozen=True, slots=True)
class ImageModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    size: str | None = None
    quality: str | None = None
    response_format: str | None = None
    n: int | None = None
    background: str | None = None
    output_format: str | None = None
    output_compression: int | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate image generation support and shared model fields.
        provider = self.normalized_provider()
        if provider not in {ModelProvider.OPENAI, ModelProvider.XAI}:
            raise UnsupportedProviderError("ImageModelRunner currently supports OpenAI and xAI image APIs.", details={"provider": provider.value})
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_positive_int(self.n, field_name="n")
        self._validate_positive_int(self.output_compression, field_name="output_compression")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


@dataclass(frozen=True, slots=True)
class VideoModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    size: str | None = None
    seconds: int | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate video job support and shared model fields.
        provider = self.normalized_provider()
        if provider != ModelProvider.OPENAI:
            raise UnsupportedProviderError("VideoModelRunner currently supports OpenAI video jobs only.", details={"provider": provider.value})
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_positive_int(self.seconds, field_name="seconds")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


AUDIO_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
    ModelProvider.OPENAI,
    ModelProvider.ELEVENLABS,
    ModelProvider.PLAYAI,
})

EMBEDDING_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
    ModelProvider.OPENAI,
    ModelProvider.GEMINI,
})


@dataclass(frozen=True, slots=True)
class AudioModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    voice: str | None = None
    speed: float | None = None
    response_format: str | None = None
    language: str | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 120.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate audio support and shared model fields.
        provider = self.normalized_provider()
        if provider not in AUDIO_SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"AudioModelRunner supports: {', '.join(p.value for p in AUDIO_SUPPORTED_PROVIDERS)}.",
                details={"provider": provider.value},
            )
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_speed()
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_speed(self) -> None:
        # OpenAI TTS accepts speed in the 0.25–4.0 range; enforce globally.
        if self.speed is not None and (self.speed < 0.25 or self.speed > 4.0):
            raise ConfigurationError("speed must be between 0.25 and 4.0.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


@dataclass(frozen=True, slots=True)
class EmbeddingModelConfig:
    provider: ModelProvider | str
    model: str
    api_key: str | None = None
    dimensions: int | None = None
    input_type: str | None = None
    extra_body: Mapping[str, Any] | None = None
    endpoint: str | None = None
    timeout_seconds: float = 60.0

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Validate embedding support and shared model fields.
        provider = self.normalized_provider()
        if provider not in EMBEDDING_SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"EmbeddingModelRunner supports: {', '.join(p.value for p in EMBEDDING_SUPPORTED_PROVIDERS)}.",
                details={"provider": provider.value},
            )
        if not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        self._validate_positive_int(self.dimensions, field_name="dimensions")
        self._validate_positive_float(self.timeout_seconds, field_name="timeout_seconds")
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def _validate_positive_int(self, value: int | None, *, field_name: str) -> None:
        # Optional integer limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")

    def _validate_positive_float(self, value: float | None, *, field_name: str) -> None:
        # Optional floating-point limits must be positive when supplied.
        if value is not None and value <= 0:
            raise ConfigurationError(f"{field_name} must be greater than zero.")


DECISION_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset({
    ModelProvider.TYPESAFE,
})


@dataclass(frozen=True, slots=True)
class DecisionModelConfig:
    """Configuration for one calibrated decision model; the API key resolves lazily at validate()."""

    provider: ModelProvider | str = ModelProvider.TYPESAFE
    model: str = JEV_DEFAULT_MODEL
    api_key: str | None = None
    endpoint: str | None = None
    timeout_seconds: float = JEV_DEFAULT_TIMEOUT_SECONDS
    retry_count: int = JEV_DEFAULT_RETRY_COUNT

    def __post_init__(self) -> None:
        # Rejects shape errors at construction so a bad config never waits for its first call.
        # @intent decision-config-shape-fails-at-construction
        # The API key is deliberately not resolved here: a decision tool must be constructable
        # without a key and fail open at call time, while a wrong timeout or retry count is a
        # programming error that should surface immediately rather than as a silent skip.
        provider = self.normalized_provider()
        if provider not in DECISION_SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"DecisionModelRunner supports: {', '.join(p.value for p in DECISION_SUPPORTED_PROVIDERS)}.",
                details={"provider": provider.value},
            )
        if not isinstance(self.model, str) or not self.model.strip():
            raise ConfigurationError("model must be non-empty.")
        if not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= JEV_TIMEOUT_FLOOR_SECONDS:
            raise ConfigurationError("timeout_seconds must be greater than zero.")
        if isinstance(self.retry_count, bool) or not isinstance(self.retry_count, int) or self.retry_count < JEV_NO_RETRIES:
            raise ConfigurationError("retry_count must be a non-negative integer.")

    def normalized_provider(self) -> ModelProvider:
        # Convert strings to the canonical provider enum at the SDK boundary.
        # @intent decision-provider-coerced-once
        # Callers may pass the provider as a string; coercing here keeps every later lookup
        # (support check, key, endpoint) keyed on the enum's frozen set of providers.
        try:
            return self.provider if isinstance(self.provider, ModelProvider) else ModelProvider(self.provider)
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {self.provider!r}") from exc

    def validate(self) -> None:
        # Resolves the API key; shape checks already ran when the config was constructed.
        self.resolved_api_key()

    def resolved_api_key(self) -> str:
        # Resolve explicit keys before provider-specific environment variables.
        # @intent explicit-key-wins-over-environment
        # An explicit key lets tests and multi-tenant callers override TYPESAFE_API_KEY; a
        # missing key raises ConfigurationError, which decision tools treat as "disabled".
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Prefer caller-provided endpoints for tests, proxies, and compatible APIs.
        # @intent explicit-endpoint-wins-over-default
        # Proxies and test servers replace the public TypeSafe endpoint without code changes.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)


__all__ = [
    "AUDIO_SUPPORTED_PROVIDERS",
    "DECISION_SUPPORTED_PROVIDERS",
    "DecisionModelConfig",
    "EMBEDDING_SUPPORTED_PROVIDERS",
    "AudioModelConfig",
    "EmbeddingModelConfig",
    "ImageModelConfig",
    "TextModelConfig",
    "VideoModelConfig",
]
