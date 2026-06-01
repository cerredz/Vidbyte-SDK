from __future__ import annotations

import json
import unittest
from typing import Mapping

from vidbyte.lib.config import AudioModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import AudioModelRunner


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._json_responses: list[dict] = []
        self._bytes_responses: list[bytes] = []
        self._multipart_responses: list[dict] = []

    def push_json(self, response: dict) -> None:
        self._json_responses.append(response)

    def push_bytes(self, data: bytes) -> None:
        self._bytes_responses.append(data)

    def push_multipart(self, response: dict) -> None:
        self._multipart_responses.append(response)

    def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        return HttpResponse(status_code=200, body=json.dumps(self._json_responses.pop(0)), headers={})

    def request_bytes(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 120.0) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        raw = self._bytes_responses.pop(0)
        return HttpResponse(status_code=200, body="", headers={}, raw_bytes=raw)

    def upload_multipart(self, *, url: str, headers: Mapping[str, str], fields: Mapping[str, str], file_field: str, file_bytes: bytes, file_name: str, file_content_type: str, timeout_seconds: float = 120.0) -> HttpResponse:
        self.requests.append({"method": "POST", "url": url, "headers": dict(headers), "fields": dict(fields), "file_field": file_field, "file_name": file_name})
        return HttpResponse(status_code=200, body=json.dumps(self._multipart_responses.pop(0)), headers={})


class AudioRunnerTests(unittest.TestCase):
    # --- OpenAI TTS ---

    def test_openai_tts_returns_audio_bytes(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"audio_data")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.OPENAI, model="tts-1", api_key="key", voice="alloy"),
            transport=transport,
        )

        response = runner.text_to_speech("Hello world")

        self.assertEqual(response.audio_bytes, b"audio_data")
        self.assertIsNone(response.transcript)
        self.assertEqual(response.raw, {})

    def test_openai_tts_sends_correct_url_and_payload(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"audio")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.OPENAI, model="tts-1", api_key="key", voice="nova"),
            transport=transport,
        )

        runner.text_to_speech("Speak this")

        req = transport.requests[0]
        self.assertEqual(req["url"], "https://api.openai.com/v1/audio/speech")
        self.assertEqual(req["json_body"]["input"], "Speak this")
        self.assertEqual(req["json_body"]["voice"], "nova")
        self.assertEqual(req["json_body"]["model"], "tts-1")

    def test_openai_tts_defaults_voice_to_alloy_when_not_set(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"audio")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.OPENAI, model="tts-1", api_key="key"),
            transport=transport,
        )

        runner.text_to_speech("Hello")

        self.assertEqual(transport.requests[0]["json_body"]["voice"], "alloy")

    # --- OpenAI STT ---

    def test_openai_stt_returns_transcript(self) -> None:
        transport = FakeTransport()
        transport.push_multipart({"text": "hello world"})
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.OPENAI, model="whisper-1", api_key="key"),
            transport=transport,
        )

        response = runner.speech_to_text(b"fake_audio_bytes", format="mp3")

        self.assertEqual(response.transcript, "hello world")
        self.assertIsNone(response.audio_bytes)

    def test_openai_stt_sends_multipart_to_transcriptions_url(self) -> None:
        transport = FakeTransport()
        transport.push_multipart({"text": "ok"})
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.OPENAI, model="whisper-1", api_key="key"),
            transport=transport,
        )

        runner.speech_to_text(b"audio", format="wav")

        req = transport.requests[0]
        self.assertIn("/audio/transcriptions", req["url"])
        self.assertEqual(req["file_name"], "audio.wav")
        self.assertEqual(req["fields"]["model"], "whisper-1")

    def test_openai_stt_empty_audio_raises_configuration_error(self) -> None:
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.OPENAI, model="whisper-1", api_key="key"),
            transport=FakeTransport(),
        )

        with self.assertRaises(ConfigurationError):
            runner.speech_to_text(b"")

    # --- ElevenLabs TTS ---

    def test_elevenlabs_tts_returns_audio_bytes(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"el_audio")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="el_key", voice="voice123"),
            transport=transport,
        )

        response = runner.text_to_speech("Hello from ElevenLabs")

        self.assertEqual(response.audio_bytes, b"el_audio")
        self.assertEqual(response.provider, ModelProvider.ELEVENLABS)

    def test_elevenlabs_tts_uses_xi_api_key_header(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"audio")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="my_xi_key", voice="v123"),
            transport=transport,
        )

        runner.text_to_speech("Test")

        headers = transport.requests[0]["headers"]
        self.assertEqual(headers.get("xi-api-key"), "my_xi_key")
        self.assertNotIn("authorization", headers)

    def test_elevenlabs_tts_includes_voice_in_url(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"audio")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="key", voice="abc123"),
            transport=transport,
        )

        runner.text_to_speech("Test")

        self.assertIn("abc123", transport.requests[0]["url"])

    def test_elevenlabs_tts_raises_when_voice_missing(self) -> None:
        with self.assertRaises(ConfigurationError):
            runner = AudioModelRunner(
                AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="key"),
                transport=FakeTransport(),
            )
            runner.text_to_speech("Test")

    def test_elevenlabs_stt_raises_configuration_error(self) -> None:
        transport = FakeTransport()
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="key", voice="v1"),
            transport=transport,
        )

        with self.assertRaises(ConfigurationError):
            runner.speech_to_text(b"audio")

    # --- PlayAI TTS ---

    def test_playai_tts_returns_audio_bytes(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"playai_audio")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.PLAYAI, model="PlayDialog", api_key="pa_key", voice="speaker_1"),
            transport=transport,
        )

        response = runner.text_to_speech("Play this")

        self.assertEqual(response.audio_bytes, b"playai_audio")
        self.assertEqual(response.provider, ModelProvider.PLAYAI)

    def test_playai_tts_uses_bearer_auth_header(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"audio")
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.PLAYAI, model="PlayDialog", api_key="secret", voice="speaker"),
            transport=transport,
        )

        runner.text_to_speech("Test")

        headers = transport.requests[0]["headers"]
        self.assertIn("Bearer", headers.get("authorization", ""))

    def test_playai_tts_raises_when_voice_missing(self) -> None:
        with self.assertRaises(ConfigurationError):
            runner = AudioModelRunner(
                AudioModelConfig(provider=ModelProvider.PLAYAI, model="PlayDialog", api_key="key"),
                transport=FakeTransport(),
            )
            runner.text_to_speech("Test")

    def test_playai_stt_raises_configuration_error(self) -> None:
        transport = FakeTransport()
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.PLAYAI, model="PlayDialog", api_key="key", voice="v1"),
            transport=transport,
        )

        with self.assertRaises(ConfigurationError):
            runner.speech_to_text(b"audio")

    # --- Config coercion ---

    def test_missing_provider_and_model_raises_configuration_error(self) -> None:
        with self.assertRaises(ConfigurationError):
            AudioModelRunner(transport=FakeTransport())

    def test_model_name_returns_configured_model(self) -> None:
        runner = AudioModelRunner(
            AudioModelConfig(provider=ModelProvider.OPENAI, model="tts-1", api_key="key"),
            transport=FakeTransport(),
        )

        self.assertEqual(runner.model_name(), "tts-1")

    def test_kwargs_construction_without_explicit_config(self) -> None:
        transport = FakeTransport()
        transport.push_bytes(b"audio")
        runner = AudioModelRunner(
            provider=ModelProvider.OPENAI,
            model="tts-1",
            api_key="key",
            voice="alloy",
            transport=transport,
        )

        response = runner.text_to_speech("Hello")

        self.assertIsNotNone(response.audio_bytes)


if __name__ == "__main__":
    unittest.main()
