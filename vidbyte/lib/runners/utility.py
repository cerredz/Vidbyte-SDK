from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any

from vidbyte.lib.config import (
    AudioModelConfig,
    EmbeddingModelConfig,
    ImageModelConfig,
    TextModelConfig,
    VideoModelConfig,
)
from vidbyte.lib.constants import (
    MODEL_PREFIX_RUNNER_TYPE_MAP,
    MODEL_PROVIDER_RUNNER_TYPE_MAP,
    MODEL_RUNNER_TYPE_MAP,
    PROVIDER_DEFAULT_RUNNER_TYPE_MAP,
    RUNNER_TYPE_AUDIO,
    RUNNER_TYPE_EMBEDDING,
    RUNNER_TYPE_IMAGE,
    RUNNER_TYPE_TEXT,
    RUNNER_TYPE_VIDEO,
)
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError


class Runner:
    """Resolves model/provider identifiers into executable SDK model runners."""

    def __init__(self, *, provider: ModelProvider | str | None, model_name: str | None, api_key: str | None = None, temperature: float | None = None, options: Mapping[str, Any] | None = None) -> None:
        # Store primitive model/provider configuration for runner inference and construction.
        self.provider, self.model_name, self._model_lookup = self._normalize_provider_and_model(provider, model_name)
        self.api_key = api_key
        self.temperature = temperature
        self.options = dict(options or {})

    @classmethod
    def from_model(cls, *, provider: ModelProvider | str | None, model_name: str | None, **kwargs: Any) -> "Runner":
        # Build a Runner utility from primitive model/provider values.
        return cls(provider=provider, model_name=model_name, **kwargs)

    def resolve_runner_type(self) -> str:
        # Resolve the internal runner type from exact provider/model, exact model, prefix, then provider defaults.
        provider = self.provider
        model = self._model_lookup
        if not provider and not model:
            raise ConfigurationError("Agent runner inference requires provider and model_name.")
        if model:
            key = f"{provider}/{model}" if provider else None
            if key and key in MODEL_PROVIDER_RUNNER_TYPE_MAP:
                return MODEL_PROVIDER_RUNNER_TYPE_MAP[key]
            if model in MODEL_RUNNER_TYPE_MAP:
                return MODEL_RUNNER_TYPE_MAP[model]
            for prefix, runner_type in MODEL_PREFIX_RUNNER_TYPE_MAP.items():
                if model.startswith(prefix):
                    return runner_type
            if provider:
                raise ConfigurationError(f"No runner mapping for provider/model '{provider}/{model}'.")
            raise ConfigurationError(f"No runner mapping for model '{model}'.")
        if provider and provider in PROVIDER_DEFAULT_RUNNER_TYPE_MAP:
            return PROVIDER_DEFAULT_RUNNER_TYPE_MAP[provider]
        raise ConfigurationError(f"No runner mapping for provider '{provider}'.")

    def build(self, *, transport: object | None = None) -> object:
        # Build and return the concrete runner for the resolved runner type.
        if not self.provider or not self.model_name:
            raise ConfigurationError("Runner.build() requires both provider and model_name.")
        runner_type = self.resolve_runner_type()
        config_options = self._config_options_for(runner_type)
        if runner_type == RUNNER_TYPE_TEXT:
            from vidbyte.lib.runners.text import TextModelRunner
            return TextModelRunner(TextModelConfig(provider=self.provider, model=self.model_name, **config_options), transport=transport)
        if runner_type == RUNNER_TYPE_IMAGE:
            from vidbyte.lib.runners.image import ImageModelRunner
            return ImageModelRunner(ImageModelConfig(provider=self.provider, model=self.model_name, **config_options), transport=transport)
        if runner_type == RUNNER_TYPE_VIDEO:
            from vidbyte.lib.runners.video import VideoModelRunner
            return VideoModelRunner(VideoModelConfig(provider=self.provider, model=self.model_name, **config_options), transport=transport)
        if runner_type == RUNNER_TYPE_AUDIO:
            from vidbyte.lib.runners.audio import AudioModelRunner
            return AudioModelRunner(AudioModelConfig(provider=self.provider, model=self.model_name, **config_options), transport=transport)
        if runner_type == RUNNER_TYPE_EMBEDDING:
            from vidbyte.lib.runners.embedding import EmbeddingModelRunner
            return EmbeddingModelRunner(EmbeddingModelConfig(provider=self.provider, model=self.model_name, **config_options), transport=transport)
        raise ConfigurationError(f"Unsupported runner type: {runner_type!r}.")

    def _config_options_for(self, runner_type: str) -> dict[str, Any]:
        # Filter primitive options to fields supported by the target config dataclass.
        config_type = self._config_type_for(runner_type)
        allowed = {field.name for field in fields(config_type)}
        options = dict(self.options)
        if self.api_key is not None:
            options["api_key"] = self.api_key
        if self.temperature is not None and runner_type == RUNNER_TYPE_TEXT:
            options["temperature"] = self.temperature
        return {key: value for key, value in options.items() if key in allowed}

    @staticmethod
    def _config_type_for(runner_type: str) -> type:
        # Return the config dataclass for a runner type.
        if runner_type == RUNNER_TYPE_TEXT:
            return TextModelConfig
        if runner_type == RUNNER_TYPE_IMAGE:
            return ImageModelConfig
        if runner_type == RUNNER_TYPE_VIDEO:
            return VideoModelConfig
        if runner_type == RUNNER_TYPE_AUDIO:
            return AudioModelConfig
        if runner_type == RUNNER_TYPE_EMBEDDING:
            return EmbeddingModelConfig
        raise ConfigurationError(f"Unsupported runner type: {runner_type!r}.")

    @staticmethod
    def _normalize_provider_and_model(provider: ModelProvider | str | None, model_name: str | None) -> tuple[str | None, str | None, str | None]:
        # Normalize provider/model strings and split provider-prefixed model names when useful.
        normalized_provider = Runner._normalize_provider(provider)
        normalized_model = str(model_name).strip() if model_name is not None else None
        normalized_model = normalized_model or None
        if normalized_model and "/" in normalized_model:
            first, rest = normalized_model.split("/", 1)
            if first and rest:
                try:
                    model_provider = Runner._normalize_provider(first)
                except ConfigurationError:
                    model_provider = None
                if model_provider and (normalized_provider is None or normalized_provider == model_provider):
                    normalized_provider = model_provider
                    normalized_model = rest
        model_lookup = normalized_model.lower() if normalized_model else None
        return normalized_provider, normalized_model, model_lookup

    @staticmethod
    def _normalize_provider(provider: ModelProvider | str | None) -> str | None:
        # Convert provider enum or string values to canonical lowercase provider keys.
        if provider is None:
            return None
        value = provider.value if isinstance(provider, ModelProvider) else str(provider)
        value = value.strip().lower()
        if not value:
            return None
        try:
            return ModelProvider(value).value
        except ValueError as exc:
            raise ConfigurationError(f"Unsupported model provider: {value!r}") from exc


__all__ = ["Runner"]
