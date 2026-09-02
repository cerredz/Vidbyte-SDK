from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import AudioModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import AudioModelResponse


class ElevenLabsProvider:
    """TTS-only provider adapter for ElevenLabs."""

    provider = ModelProvider.ELEVENLABS

    def __init__(self, *, audio_config: AudioModelConfig | None = None, **_: Any) -> None:
        # Store the audio config; other kwargs are accepted but ignored for compat with factory.
        self._audio_config = audio_config

    def run_tts(self, *, text: str, transport: HttpTransport, config: AudioModelConfig | None = None) -> AudioModelResponse:
        # POST to /text-to-speech/{voice_id} and return binary audio bytes.
        config = self._config(config)
        voice_id = self._require_voice(config)
        url = f"{config.resolved_endpoint()}/text-to-speech/{voice_id}"
        headers = self._create_headers(config)
        headers["accept"] = "audio/mpeg"
        payload = self._create_tts_payload(config, text)
        response = transport.request_bytes(method="POST", url=url, headers=headers, json_body=payload, timeout_seconds=config.timeout_seconds)
        if not response.raw_bytes:
            raise ProviderResponseError("ElevenLabs TTS returned empty audio bytes.", provider=self.provider.value)
        return AudioModelResponse(provider=self.provider, model=config.model, audio_bytes=response.raw_bytes, transcript=None, raw={})

    def run_stt(self, *, audio: bytes, format: str, transport: HttpTransport, config: AudioModelConfig | None = None) -> AudioModelResponse:
        # ElevenLabs does not provide a public STT API; raise to signal unsupported operation.
        raise ConfigurationError("ElevenLabs does not support speech-to-text.")

    def _config(self, config: AudioModelConfig | None) -> AudioModelConfig:
        # Resolve the active config, raising if neither was supplied.
        resolved = config or self._audio_config
        if resolved is None:
            raise ProviderConfigurationError("ElevenLabsProvider requires an AudioModelConfig.", provider=self.provider.value)
        return resolved

    def _require_voice(self, config: AudioModelConfig) -> str:
        # ElevenLabs requires a voice_id; raise ConfigurationError when absent.
        if not config.voice:
            raise ConfigurationError("ElevenLabs TTS requires a voice identifier in AudioModelConfig.voice.")
        return config.voice

    def _create_headers(self, config: AudioModelConfig) -> dict[str, str]:
        # Build ElevenLabs auth headers using xi-api-key (not Authorization: Bearer).
        return {"xi-api-key": config.resolved_api_key(), "content-type": "application/json"}

    def _create_tts_payload(self, config: AudioModelConfig, text: str) -> dict[str, Any]:
        # Build the ElevenLabs TTS request body with model and optional output format.
        payload: dict[str, Any] = {"text": text, "model_id": config.model}
        if config.response_format:
            payload["output_format"] = config.response_format
        if config.extra_body:
            payload.update(dict(config.extra_body))
        return payload


__all__ = [
    "ElevenLabsProvider",
]
