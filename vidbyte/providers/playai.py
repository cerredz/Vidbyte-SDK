from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.config import AudioModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderConfigurationError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import AudioModelResponse


class PlayAIProvider:
    """TTS-only provider adapter for Play.ai.

    NOTE: Play.ai's synchronous TTS endpoint returns binary audio inline for the
    PlayDialog model family. If Play.ai changes to a job-based async API in the
    future, run_tts() will need to be updated to poll for completion.
    """

    provider = ModelProvider.PLAYAI

    def __init__(self, *, audio_config: AudioModelConfig | None = None, **_: Any) -> None:
        # Store the audio config; other kwargs are accepted but ignored for factory compat.
        self._audio_config = audio_config

    def run_tts(self, *, text: str, transport: HttpTransport, config: AudioModelConfig | None = None) -> AudioModelResponse:
        # POST to /tts and return binary audio bytes from the synchronous response.
        config = self._config(config)
        voice = self._require_voice(config)
        url = f"{config.resolved_endpoint()}/tts"
        payload = self._create_tts_payload(config, text, voice)
        response = transport.request_bytes(method="POST", url=url, headers=self._create_headers(config), json_body=payload, timeout_seconds=config.timeout_seconds)
        if not response.raw_bytes:
            raise ProviderResponseError("Play.ai TTS returned empty audio bytes.", provider=self.provider.value)
        return AudioModelResponse(provider=self.provider, model=config.model, audio_bytes=response.raw_bytes, transcript=None, raw={})

    def run_stt(self, *, audio: bytes, format: str, transport: HttpTransport, config: AudioModelConfig | None = None) -> AudioModelResponse:
        # Play.ai does not provide a public STT API; raise to signal unsupported operation.
        raise ConfigurationError("Play.ai does not support speech-to-text.")

    def _config(self, config: AudioModelConfig | None) -> AudioModelConfig:
        # Resolve the active config, raising if neither was supplied.
        resolved = config or self._audio_config
        if resolved is None:
            raise ProviderConfigurationError("PlayAIProvider requires an AudioModelConfig.", provider=self.provider.value)
        return resolved

    def _require_voice(self, config: AudioModelConfig) -> str:
        # Play.ai requires a voice identifier; raise ConfigurationError when absent.
        if not config.voice:
            raise ConfigurationError("Play.ai TTS requires a voice identifier in AudioModelConfig.voice.")
        return config.voice

    def _create_headers(self, config: AudioModelConfig) -> dict[str, str]:
        # Build Play.ai auth headers using Authorization: Bearer pattern.
        return {"authorization": f"Bearer {config.resolved_api_key()}", "content-type": "application/json"}

    def _create_tts_payload(self, config: AudioModelConfig, text: str, voice: str) -> dict[str, Any]:
        # Build the Play.ai TTS request body with model, voice, text, and output format.
        payload: dict[str, Any] = {
            "model": config.model,
            "voice": voice,
            "text": text,
            "outputFormat": config.response_format or "mp3",
        }
        if config.extra_body:
            payload.update(dict(config.extra_body))
        return payload


__all__ = [
    "PlayAIProvider",
]
