"""Context Protocol Header

Description:
    Model execution configuration dataclasses for text, image, and video models.
Purpose:
    Stores model configurations and delegates API key and endpoint validation and resolution to ProviderModelRegistry.
Architecture:
    - TextModelConfig: dataclass for text/chat completions.
    - ImageModelConfig: dataclass for image generation.
    - VideoModelConfig: dataclass for video generation tasks.
    - DecisionModelConfig: dataclass for calibrated decision models: TypeSafe Jev and every
      other System One or OpenAI Decisions host in ProviderModelRegistry.DECISION_DEFAULT_MODELS.
Key Functions:
    - resolved_api_key: Resolves provider key by delegating to ProviderModelRegistry.
    - resolved_endpoint: Resolves provider endpoint by delegating to ProviderModelRegistry.
    - DecisionModelConfig.resolved_model: Returns the decision model id, filled from the
      provider's decision default when the caller omitted it.
Relations:
    Used by runners, agents, and strategies to initialize model executions.
Similar Files:
    - vidbyte/lib/models/registry.py
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.constants.jev import (
    JEV_DEFAULT_RETRY_COUNT,
    JEV_DEFAULT_TIMEOUT_SECONDS,
    JEV_MANAGED_GATEWAY_SUFFIX,
    JEV_MANAGED_RUN_CLOSE_PATH,
    JEV_NO_RETRIES,
    JEV_TIMEOUT_FLOOR_SECONDS,
    VIDBYTE_JEV_GATEWAY_ENDPOINT,
    VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND,
)
from vidbyte.lib.enums import DecisionModelMode, ModelProvider
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


DECISION_SUPPORTED_PROVIDERS: frozenset[ModelProvider] = frozenset(ProviderModelRegistry.DECISION_DEFAULT_MODELS)


@dataclass(frozen=True, slots=True)
class DecisionModelConfig:
    """Configuration for one decision model: any decision provider directly, or TypeSafe through Vidbyte's managed gateway.

    `model` is `str | None` because its default depends on `provider`, so no single literal default
    exists: None selects `ProviderModelRegistry.DECISION_DEFAULT_MODELS[provider]` during
    `__post_init__`, after which the field always holds a non-blank string. Production code reads it
    through `resolved_model()`, which is typed `str`.
    """

    provider: ModelProvider | str = ModelProvider.TYPESAFE
    model: str | None = None
    api_key: str | None = field(default=None, repr=False)
    endpoint: str | None = None
    timeout_seconds: float = JEV_DEFAULT_TIMEOUT_SECONDS
    retry_count: int = JEV_DEFAULT_RETRY_COUNT
    mode: DecisionModelMode = DecisionModelMode.TYPESAFE

    def __post_init__(self) -> None:
        # Rejects shape errors at construction so a bad config never waits for its first call.
        # @intent decision-config-shape-fails-at-construction
        # The API key is deliberately not resolved here so disabled Jev features need no credential;
        # active callers validate it when they build the decision runner and apply their failure policy.
        provider = self.normalized_provider()
        if provider not in DECISION_SUPPORTED_PROVIDERS:
            raise UnsupportedProviderError(
                f"DecisionModelRunner supports: {', '.join(sorted(p.value for p in DECISION_SUPPORTED_PROVIDERS))}.",
                details={"provider": provider.value},
            )
        if not isinstance(self.mode, DecisionModelMode):
            raise ConfigurationError("mode must be a DecisionModelMode value.")
        # @intent managed-mode-is-typesafe-only
        # The managed gateway proxies only TypeSafe; any other provider in managed mode would send the
        # Vidbyte key to that vendor's host, so it fails here before any credential is read.
        if self.mode is DecisionModelMode.VIDBYTE_MANAGED and provider is not ModelProvider.TYPESAFE:
            raise ConfigurationError("VIDBYTE_MANAGED decision mode is available only for provider typesafe.")
        if self.mode is DecisionModelMode.VIDBYTE_MANAGED and self.endpoint is not None:
            if not isinstance(self.endpoint, str) or self.endpoint.strip():
                raise ConfigurationError("A custom endpoint is not allowed for VIDBYTE_MANAGED decision mode.")
        # @intent omitted-model-means-the-provider-decision-default
        # Each provider names its decision models differently, so an omitted model takes that provider's
        # registered default instead of a TypeSafe id another vendor would reject.
        if self.model is None:
            object.__setattr__(self, "model", ProviderModelRegistry.decision_default_model(provider))
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
        # Resolves the API key, then the endpoint; shape checks already ran when the config was constructed.
        # @intent tenant-endpoints-fail-before-the-first-call
        # Cloudflare and Foundry have no shared default endpoint, so a missing one must fail when the
        # runner is built, not as a 404 after the first billed call.
        self.resolved_api_key()
        self.resolved_endpoint()

    def resolved_model(self) -> str:
        # Returns the model id as a str; __post_init__ already filled it, so None is unreachable.
        if self.model is None:
            raise ConfigurationError("DecisionModelConfig.model was not resolved.")
        return self.model

    def resolved_api_key(self) -> str:
        # Resolves the selected mode's key source without exposing the credential in errors.
        # @intent managed-mode-never-falls-back-to-typesafe-key
        # A managed call must use a Vidbyte live key; only direct mode may resolve TYPESAFE_API_KEY.
        if self.mode is DecisionModelMode.VIDBYTE_MANAGED:
            if self.api_key is not None and not isinstance(self.api_key, str):
                raise ConfigurationError("api_key must be a string in VIDBYTE_MANAGED decision mode.", details={"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND})
            explicit_key = self.api_key.strip() if self.api_key is not None else ""
            key = (explicit_key or os.environ.get("VIDBYTE_API_KEY", "")).strip()
            if not key:
                raise ConfigurationError("Missing Vidbyte API key. Pass api_key or set VIDBYTE_API_KEY.", details={"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND})
            if re.fullmatch(r"vb_live_[A-Za-z0-9_-]{32,}", key) is None:
                raise ConfigurationError("The managed Vidbyte API key must be a live key in the vb_live_ format.", details={"error_kind": VIDBYTE_MANAGED_CREDENTIAL_ERROR_KIND})
            return key
        # Resolves explicit TypeSafe keys before the provider-specific environment variable.
        # @intent explicit-key-wins-over-environment
        # Direct mode preserves the existing TypeSafe key resolution for standalone runners.
        return ProviderModelRegistry.resolve_api_key(self.normalized_provider(), self.api_key)

    def resolved_endpoint(self) -> str:
        # Pins managed credentials to Vidbyte while preserving direct provider endpoint overrides.
        # @intent managed-key-stays-on-vidbyte-host
        # Direct TypeSafe proxies remain configurable, but the Vidbyte bearer credential never follows a caller URL.
        if self.mode is DecisionModelMode.VIDBYTE_MANAGED:
            return VIDBYTE_JEV_GATEWAY_ENDPOINT
        # @intent explicit-endpoint-wins-over-default
        # Proxies and test servers remain available for direct TypeSafe calls.
        return ProviderModelRegistry.resolve_endpoint(self.normalized_provider(), self.endpoint)

    def resolved_run_close_url(self, run_id: str) -> str:
        """Return the gateway close URL for one managed Jev run."""
        if self.mode is not DecisionModelMode.VIDBYTE_MANAGED:
            raise ConfigurationError("Only a managed DecisionModelConfig has runs to close.")
        root = self.resolved_endpoint().removesuffix(JEV_MANAGED_GATEWAY_SUFFIX)
        return f"{root}{JEV_MANAGED_RUN_CLOSE_PATH.format(run_id=run_id)}"

    @classmethod
    def vidbyte_managed(cls) -> DecisionModelConfig:
        # Builds the pinned Vidbyte gateway configuration used by JevAgent by default.
        # @intent jev-defaults-to-managed-gateway
        # Keeping this factory separate leaves standalone DecisionModelConfig defaulted to direct TypeSafe access.
        return cls(mode=DecisionModelMode.VIDBYTE_MANAGED)


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
