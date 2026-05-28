"""Verification script for AudioModelRunner, EmbeddingModelRunner, and StreamingTextModelRunner.

Runs all test cases from design doc Section 10 using FakeTransport/FakeStreamingTransport.
Exits non-zero if any test case fails.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Iterator
from typing import Mapping

# ---------------------------------------------------------------------------
# Fake transports
# ---------------------------------------------------------------------------

from vidbyte.lib.http import HttpResponse


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._json_q: list[dict] = []
        self._bytes_q: list[bytes] = []
        self._multipart_q: list[dict] = []

    def push_json(self, r: dict) -> "FakeTransport":
        self._json_q.append(r)
        return self

    def push_bytes(self, b: bytes) -> "FakeTransport":
        self._bytes_q.append(b)
        return self

    def push_multipart(self, r: dict) -> "FakeTransport":
        self._multipart_q.append(r)
        return self

    def request(self, *, method, url, headers, json_body=None, timeout_seconds=60.0) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        return HttpResponse(status_code=200, body=json.dumps(self._json_q.pop(0)), headers={})

    def request_bytes(self, *, method, url, headers, json_body=None, timeout_seconds=120.0) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        raw = self._bytes_q.pop(0)
        return HttpResponse(status_code=200, body="", headers={}, raw_bytes=raw)

    def upload_multipart(self, *, url, headers, fields, file_field, file_bytes, file_name, file_content_type, timeout_seconds=120.0) -> HttpResponse:
        self.requests.append({"method": "POST", "url": url, "headers": dict(headers), "fields": dict(fields), "file_field": file_field, "file_name": file_name})
        return HttpResponse(status_code=200, body=json.dumps(self._multipart_q.pop(0)), headers={})


class FakeStreamingTransport:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.requests: list[dict] = []

    def stream_request(self, *, method, url, headers, json_body=None, timeout_seconds=120.0) -> Iterator[str]:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        yield from self._lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _oai_embed(vectors: list[list[float]]) -> dict:
    return {"data": [{"index": i, "embedding": v} for i, v in enumerate(vectors)], "usage": {"total_tokens": 5}}


def _gemini_embed(vectors: list[list[float]]) -> dict:
    return {"embeddings": [{"values": v} for v in vectors]}


def _oai_delta(text: str) -> str:
    return json.dumps({"type": "response.text.delta", "delta": text})


def _anthropic_delta(text: str) -> str:
    return json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
_results: list[tuple[str, bool, str]] = []


def test(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        _results.append((name, True, ""))
        PASS += 1
    except Exception:
        _results.append((name, False, traceback.format_exc()))
        FAIL += 1


def assert_equal(a, b, msg=""):
    if a != b:
        raise AssertionError(f"{msg}: expected {b!r}, got {a!r}")


def assert_true(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "Expected True, got False")


def assert_raises(exc_type, fn):
    try:
        fn()
    except exc_type:
        return
    except Exception as e:
        raise AssertionError(f"Expected {exc_type.__name__} but got {type(e).__name__}: {e}")
    raise AssertionError(f"Expected {exc_type.__name__} but no exception was raised")


# ---------------------------------------------------------------------------
# AudioModelRunner tests
# ---------------------------------------------------------------------------

from vidbyte.lib.config import AudioModelConfig, EmbeddingModelConfig, TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, UnsupportedProviderError
from vidbyte.lib.runners import AudioModelRunner, EmbeddingModelRunner, StreamingTextModelRunner


def test_openai_tts_happy_path():
    t = FakeTransport().push_bytes(b"mp3_data")
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.OPENAI, model="tts-1", api_key="key", voice="alloy"), transport=t)
    resp = r.text_to_speech("Hello world")
    assert_equal(resp.audio_bytes, b"mp3_data")
    assert_equal(resp.transcript, None)
    assert_equal(resp.raw, {})
    assert_equal(t.requests[0]["url"], "https://api.openai.com/v1/audio/speech")
    assert_equal(t.requests[0]["json_body"]["voice"], "alloy")


def test_openai_tts_default_voice():
    t = FakeTransport().push_bytes(b"audio")
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.OPENAI, model="tts-1", api_key="key"), transport=t)
    r.text_to_speech("test")
    assert_equal(t.requests[0]["json_body"]["voice"], "alloy")


def test_openai_stt_happy_path():
    t = FakeTransport().push_multipart({"text": "hello world"})
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.OPENAI, model="whisper-1", api_key="key"), transport=t)
    resp = r.speech_to_text(b"audio_bytes", format="mp3")
    assert_equal(resp.transcript, "hello world")
    assert_equal(resp.audio_bytes, None)
    assert_true("/audio/transcriptions" in t.requests[0]["url"])


def test_openai_stt_sends_correct_file_name():
    t = FakeTransport().push_multipart({"text": "ok"})
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.OPENAI, model="whisper-1", api_key="key"), transport=t)
    r.speech_to_text(b"audio", format="wav")
    assert_equal(t.requests[0]["file_name"], "audio.wav")


def test_empty_audio_raises():
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.OPENAI, model="whisper-1", api_key="key"), transport=FakeTransport())
    assert_raises(ConfigurationError, lambda: r.speech_to_text(b""))


def test_elevenlabs_tts_uses_xi_api_key():
    t = FakeTransport().push_bytes(b"el_audio")
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="xi_key", voice="v1"), transport=t)
    resp = r.text_to_speech("EL test")
    assert_equal(resp.audio_bytes, b"el_audio")
    assert_equal(t.requests[0]["headers"].get("xi-api-key"), "xi_key")
    assert_true("xi-api-key" in t.requests[0]["headers"])


def test_elevenlabs_voice_in_url():
    t = FakeTransport().push_bytes(b"audio")
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="key", voice="abc123"), transport=t)
    r.text_to_speech("Test")
    assert_true("abc123" in t.requests[0]["url"])


def test_elevenlabs_missing_voice_raises():
    t = FakeTransport().push_bytes(b"audio")
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="key"), transport=t)
    assert_raises(ConfigurationError, lambda: r.text_to_speech("Test"))


def test_elevenlabs_stt_raises():
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.ELEVENLABS, model="eleven_multilingual_v2", api_key="key", voice="v1"), transport=FakeTransport())
    assert_raises(ConfigurationError, lambda: r.speech_to_text(b"audio"))


def test_playai_tts_uses_bearer_auth():
    t = FakeTransport().push_bytes(b"pa_audio")
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.PLAYAI, model="PlayDialog", api_key="pa_key", voice="speaker"), transport=t)
    resp = r.text_to_speech("PlayAI test")
    assert_equal(resp.audio_bytes, b"pa_audio")
    assert_true("Bearer" in t.requests[0]["headers"].get("authorization", ""))


def test_playai_missing_voice_raises():
    t = FakeTransport().push_bytes(b"audio")
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.PLAYAI, model="PlayDialog", api_key="key"), transport=t)
    assert_raises(ConfigurationError, lambda: r.text_to_speech("Test"))


def test_playai_stt_raises():
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.PLAYAI, model="PlayDialog", api_key="key", voice="v1"), transport=FakeTransport())
    assert_raises(ConfigurationError, lambda: r.speech_to_text(b"audio"))


def test_audio_runner_missing_config_raises():
    assert_raises(ConfigurationError, lambda: AudioModelRunner(transport=FakeTransport()))


def test_audio_runner_model_name():
    r = AudioModelRunner(AudioModelConfig(provider=ModelProvider.OPENAI, model="tts-1", api_key="key"), transport=FakeTransport())
    assert_equal(r.model_name(), "tts-1")


# ---------------------------------------------------------------------------
# EmbeddingModelRunner tests
# ---------------------------------------------------------------------------

def test_openai_embedding_single_text():
    t = FakeTransport().push_json(_oai_embed([[0.1, 0.2]]))
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    resp = r.run("hello")
    assert_equal(len(resp.embeddings), 1)
    assert_equal(round(resp.embeddings[0][0], 5), round(0.1, 5))


def test_openai_embedding_multi_text():
    t = FakeTransport().push_json(_oai_embed([[1.0], [2.0], [3.0]]))
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    resp = r.run(["a", "b", "c"])
    assert_equal(len(resp.embeddings), 3)


def test_openai_embedding_sorted_by_index():
    # Items deliberately out of order in response
    out_of_order = {"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}], "usage": {}}
    t = FakeTransport().push_json(out_of_order)
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    resp = r.run(["x", "y"])
    assert_equal(round(resp.embeddings[0][0], 5), 1.0)
    assert_equal(round(resp.embeddings[1][0], 5), 2.0)


def test_openai_embedding_url():
    t = FakeTransport().push_json(_oai_embed([[0.1]]))
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    r.run("test")
    assert_equal(t.requests[0]["url"], "https://api.openai.com/v1/embeddings")


def test_openai_embedding_dimensions_in_payload():
    t = FakeTransport().push_json(_oai_embed([[0.1]]))
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key", dimensions=256), transport=t)
    r.run("test")
    assert_equal(t.requests[0]["json_body"]["dimensions"], 256)


def test_gemini_embedding_happy_path():
    t = FakeTransport().push_json(_gemini_embed([[0.5, 0.5], [0.3, 0.7]]))
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="text-embedding-004", api_key="key"), transport=t)
    resp = r.run(["doc1", "doc2"])
    assert_equal(len(resp.embeddings), 2)
    assert_true("batchEmbedContents" in t.requests[0]["url"])


def test_gemini_embedding_x_goog_header():
    t = FakeTransport().push_json(_gemini_embed([[0.1]]))
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.GEMINI, model="text-embedding-004", api_key="goog123"), transport=t)
    r.run("hello")
    assert_equal(t.requests[0]["headers"].get("x-goog-api-key"), "goog123")


def test_embedding_empty_list_raises():
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=FakeTransport())
    assert_raises(ConfigurationError, lambda: r.run([]))


def test_embedding_string_normalized():
    t = FakeTransport().push_json(_oai_embed([[0.1]]))
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    resp = r.run("single")
    assert_equal(len(resp.embeddings), 1)
    assert_equal(t.requests[0]["json_body"]["input"], ["single"])


def test_embedding_missing_config_raises():
    assert_raises(ConfigurationError, lambda: EmbeddingModelRunner(transport=FakeTransport()))


def test_embedding_model_name():
    r = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-large", api_key="key"), transport=FakeTransport())
    assert_equal(r.model_name(), "text-embedding-3-large")


# ---------------------------------------------------------------------------
# StreamingTextModelRunner tests
# ---------------------------------------------------------------------------

def test_openai_stream_yields_deltas():
    t = FakeStreamingTransport([_oai_delta("Hello"), _oai_delta(" world")])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"), transport=t)
    chunks = list(r.stream("Hi"))
    assert_equal(chunks, ["Hello", " world"])


def test_openai_stream_url():
    t = FakeStreamingTransport([_oai_delta("ok")])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"), transport=t)
    list(r.stream("Test"))
    assert_true("/responses" in t.requests[0]["url"])


def test_openai_stream_stream_flag():
    t = FakeStreamingTransport([_oai_delta("ok")])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"), transport=t)
    list(r.stream("Test"))
    assert_true(t.requests[0]["json_body"].get("stream") is True)


def test_openai_stream_system_as_instructions():
    t = FakeStreamingTransport([_oai_delta("ok")])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"), transport=t)
    list(r.stream("Test", system="Be brief"))
    assert_equal(t.requests[0]["json_body"].get("instructions"), "Be brief")


def test_openai_stream_filters_non_delta_events():
    lines = [
        json.dumps({"type": "response.created"}),
        _oai_delta("chunk1"),
        json.dumps({"type": "response.done", "response": {}}),
        _oai_delta("chunk2"),
    ]
    t = FakeStreamingTransport(lines)
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"), transport=t)
    chunks = list(r.stream("Test"))
    assert_equal(chunks, ["chunk1", "chunk2"])


def test_openai_stream_empty():
    t = FakeStreamingTransport([])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"), transport=t)
    chunks = list(r.stream("Test"))
    assert_equal(chunks, [])


def test_anthropic_stream_yields_deltas():
    t = FakeStreamingTransport([_anthropic_delta("Hello"), _anthropic_delta(" Anthropic")])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="key"), transport=t)
    chunks = list(r.stream("Hi"))
    assert_equal(chunks, ["Hello", " Anthropic"])


def test_anthropic_stream_url():
    t = FakeStreamingTransport([_anthropic_delta("ok")])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="key"), transport=t)
    list(r.stream("Test"))
    assert_true("/messages" in t.requests[0]["url"])


def test_anthropic_stream_x_api_key_header():
    t = FakeStreamingTransport([_anthropic_delta("ok")])
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="anthro_key"), transport=t)
    list(r.stream("Test"))
    assert_equal(t.requests[0]["headers"].get("x-api-key"), "anthro_key")


def test_anthropic_stream_filters_non_text_delta_events():
    lines = [
        json.dumps({"type": "message_start"}),
        _anthropic_delta("good"),
        json.dumps({"type": "content_block_stop"}),
        _anthropic_delta("also_good"),
    ]
    t = FakeStreamingTransport(lines)
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="key"), transport=t)
    chunks = list(r.stream("Test"))
    assert_equal(chunks, ["good", "also_good"])


def test_gemini_provider_rejected_at_init():
    assert_raises(UnsupportedProviderError, lambda: StreamingTextModelRunner(
        TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-2.0-flash", api_key="key"),
        transport=FakeStreamingTransport([]),
    ))


def test_xai_provider_rejected_at_init():
    assert_raises(UnsupportedProviderError, lambda: StreamingTextModelRunner(
        TextModelConfig(provider=ModelProvider.XAI, model="grok-2", api_key="key"),
        transport=FakeStreamingTransport([]),
    ))


def test_streaming_missing_config_raises():
    assert_raises(ConfigurationError, lambda: StreamingTextModelRunner(transport=FakeStreamingTransport([])))


def test_streaming_model_name():
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o-mini", api_key="key"), transport=FakeStreamingTransport([]))
    assert_equal(r.model_name(), "gpt-4o-mini")


def test_malformed_sse_lines_skipped():
    lines = ["not-json", _oai_delta("valid"), "{broken"]
    t = FakeStreamingTransport(lines)
    r = StreamingTextModelRunner(TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"), transport=t)
    chunks = list(r.stream("Test"))
    assert_equal(chunks, ["valid"])


# ---------------------------------------------------------------------------
# EmbeddingModelRunnerProvider bridge tests
# ---------------------------------------------------------------------------

from vidbyte.tools.builtins.code_search.semantic import EmbeddingModelRunnerProvider


def test_embedding_provider_bridge_embed():
    t = FakeTransport().push_json(_oai_embed([[0.1, 0.2], [0.3, 0.4]]))
    runner = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    provider = EmbeddingModelRunnerProvider(runner)
    result = provider.embed(["doc1", "doc2"])
    assert_equal(len(result), 2)
    assert_equal(round(result[0][0], 5), round(0.1, 5))
    assert_equal(round(result[1][0], 5), round(0.3, 5))


def test_embedding_provider_bridge_single_text():
    t = FakeTransport().push_json(_oai_embed([[0.5, 0.6]]))
    runner = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    provider = EmbeddingModelRunnerProvider(runner)
    result = provider.embed(["hello"])
    assert_equal(len(result), 1)
    assert_equal(len(result[0]), 2)


def test_embedding_provider_bridge_returns_lists_not_tuples():
    t = FakeTransport().push_json(_oai_embed([[0.1]]))
    runner = EmbeddingModelRunner(EmbeddingModelConfig(provider=ModelProvider.OPENAI, model="text-embedding-3-small", api_key="key"), transport=t)
    provider = EmbeddingModelRunnerProvider(runner)
    result = provider.embed(["x"])
    assert_true(isinstance(result[0], list), "Expected inner type to be list")


# ---------------------------------------------------------------------------
# Register all tests and run
# ---------------------------------------------------------------------------

ALL_TESTS = [
    # Audio
    ("Audio: OpenAI TTS happy path", test_openai_tts_happy_path),
    ("Audio: OpenAI TTS defaults voice to alloy", test_openai_tts_default_voice),
    ("Audio: OpenAI STT happy path", test_openai_stt_happy_path),
    ("Audio: OpenAI STT correct file name", test_openai_stt_sends_correct_file_name),
    ("Audio: Empty audio raises ConfigurationError", test_empty_audio_raises),
    ("Audio: ElevenLabs TTS uses xi-api-key", test_elevenlabs_tts_uses_xi_api_key),
    ("Audio: ElevenLabs voice in URL", test_elevenlabs_voice_in_url),
    ("Audio: ElevenLabs missing voice raises", test_elevenlabs_missing_voice_raises),
    ("Audio: ElevenLabs STT raises ConfigurationError", test_elevenlabs_stt_raises),
    ("Audio: PlayAI TTS uses Bearer auth", test_playai_tts_uses_bearer_auth),
    ("Audio: PlayAI missing voice raises", test_playai_missing_voice_raises),
    ("Audio: PlayAI STT raises ConfigurationError", test_playai_stt_raises),
    ("Audio: Missing config raises ConfigurationError", test_audio_runner_missing_config_raises),
    ("Audio: model_name()", test_audio_runner_model_name),
    # Embedding
    ("Embedding: OpenAI single text", test_openai_embedding_single_text),
    ("Embedding: OpenAI multi text", test_openai_embedding_multi_text),
    ("Embedding: OpenAI items sorted by index", test_openai_embedding_sorted_by_index),
    ("Embedding: OpenAI correct URL", test_openai_embedding_url),
    ("Embedding: OpenAI dimensions in payload", test_openai_embedding_dimensions_in_payload),
    ("Embedding: Gemini batch happy path", test_gemini_embedding_happy_path),
    ("Embedding: Gemini x-goog-api-key header", test_gemini_embedding_x_goog_header),
    ("Embedding: Empty list raises ConfigurationError", test_embedding_empty_list_raises),
    ("Embedding: String input normalized to list", test_embedding_string_normalized),
    ("Embedding: Missing config raises ConfigurationError", test_embedding_missing_config_raises),
    ("Embedding: model_name()", test_embedding_model_name),
    # Streaming
    ("Streaming: OpenAI yields text deltas", test_openai_stream_yields_deltas),
    ("Streaming: OpenAI correct URL", test_openai_stream_url),
    ("Streaming: OpenAI stream=True in payload", test_openai_stream_stream_flag),
    ("Streaming: OpenAI system as instructions", test_openai_stream_system_as_instructions),
    ("Streaming: OpenAI filters non-delta events", test_openai_stream_filters_non_delta_events),
    ("Streaming: OpenAI empty stream yields nothing", test_openai_stream_empty),
    ("Streaming: Anthropic yields text deltas", test_anthropic_stream_yields_deltas),
    ("Streaming: Anthropic correct URL", test_anthropic_stream_url),
    ("Streaming: Anthropic x-api-key header", test_anthropic_stream_x_api_key_header),
    ("Streaming: Anthropic filters non-text-delta events", test_anthropic_stream_filters_non_text_delta_events),
    ("Streaming: Gemini rejected at init", test_gemini_provider_rejected_at_init),
    ("Streaming: XAI rejected at init", test_xai_provider_rejected_at_init),
    ("Streaming: Missing config raises ConfigurationError", test_streaming_missing_config_raises),
    ("Streaming: model_name()", test_streaming_model_name),
    ("Streaming: Malformed SSE lines silently skipped", test_malformed_sse_lines_skipped),
    # Bridge
    ("Bridge: EmbeddingModelRunnerProvider embed multi", test_embedding_provider_bridge_embed),
    ("Bridge: EmbeddingModelRunnerProvider embed single", test_embedding_provider_bridge_single_text),
    ("Bridge: EmbeddingModelRunnerProvider returns lists", test_embedding_provider_bridge_returns_lists_not_tuples),
]

if __name__ == "__main__":
    for name, fn in ALL_TESTS:
        test(name, fn)

    print()
    for name, passed, tb in _results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            for line in tb.strip().splitlines():
                print(f"         {line}")

    print()
    total = PASS + FAIL
    print(f"{PASS}/{total} tests passed.")

    sys.exit(0 if FAIL == 0 else 1)
