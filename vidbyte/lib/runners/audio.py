from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.config import AudioModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import AudioModelResponse
from vidbyte.providers import ModelProviders


class AudioModelRunner:
    """Semantic runner for text-to-speech and speech-to-text models."""

    def __init__(self, config: AudioModelConfig | None = None, *, provider: ModelProvider | str | None = None, model: str | None = None, transport: HttpTransport | None = None, **config_options: Any) -> None:
        # Coerce config from kwargs if not supplied directly, then validate and build provider.
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        config.validate()
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.audio(config)

    def text_to_speech(self, text: str) -> AudioModelResponse:
        # Call the provider TTS endpoint and return binary audio bytes plus metadata.
        return self._provider.run_tts(text=text, transport=self._transport)

    def speech_to_text(self, audio: bytes, *, format: str = "mp3") -> AudioModelResponse:
        # Upload audio bytes to the provider STT endpoint and return the transcript.
        if not audio:
            raise ConfigurationError("audio bytes must be non-empty.")
        return self._provider.run_stt(audio=audio, format=format, transport=self._transport)

    def model_name(self) -> str:
        # Return the configured model identifier string.
        return self._config.model

    def _coerce_config(self, config: AudioModelConfig | None, *, provider: ModelProvider | str | None, model: str | None, config_options: Mapping[str, Any]) -> AudioModelConfig:
        # Return config as-is if supplied; otherwise build one from provider+model kwargs.
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("AudioModelRunner requires either config or provider and model.")
        return AudioModelConfig(provider=provider, model=model, **dict(config_options))
