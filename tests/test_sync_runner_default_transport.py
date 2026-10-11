"""FILE: tests/test_sync_runner_default_transport.py

PURPOSE: Prove the audio, embedding and streaming runners work with their default transport rather than the async HttpTransport.
ROLE IN CODEBASE: Drives vidbyte.lib.runners AudioModelRunner, EmbeddingModelRunner and StreamingTextModelRunner with no injected transport.
ARCHITECTURE NOTE: urlopen inside vidbyte.lib.http.transport is replaced, so SyncHttpTransport runs for real without opening a socket.
COMMON MODIFICATION PATTERNS: Add a case when another sync runner or provider sync method is added; never inject a transport here.
KNOWN EDGE CASES: Embedding vectors come back as tuples; SSE bodies stop at the [DONE] line.
RELATED DOCS: docs/design/builtin-tool-transport-and-builder-fixes.md
TESTS: This module; full source gate via scripts/run_ci.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from email.message import Message
from typing import Any

import pytest

from vidbyte.lib.http import transport as transport_module
from vidbyte.lib.runners.audio import AudioModelRunner
from vidbyte.lib.runners.embedding import EmbeddingModelRunner
from vidbyte.lib.runners.streaming_text import StreamingTextModelRunner


class _FakeUrlResponse:
    """Stands in for the urllib response context manager; serves a fixed body."""

    def __init__(self, body: bytes) -> None:
        self.status = 200
        self.headers = Message()
        self._body = body

    def __enter__(self) -> _FakeUrlResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body

    def __iter__(self) -> Iterator[bytes]:
        return iter(self._body.splitlines(keepends=True))


def _fake_urlopen(monkeypatch: pytest.MonkeyPatch, body: bytes) -> list[str]:
    # Replaces urllib's urlopen inside the transport so no socket opens, recording each URL.
    urls: list[str] = []

    def fake(request: Any, timeout: float) -> _FakeUrlResponse:
        urls.append(request.full_url)
        return _FakeUrlResponse(body)

    monkeypatch.setattr(transport_module, "urlopen", fake)
    return urls


def test_default_audio_runner_text_to_speech_returns_audio_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    urls = _fake_urlopen(monkeypatch, b"ID3-audio")

    response = AudioModelRunner(provider="openai", model="gpt-4o-mini-tts", api_key="k").text_to_speech("hi")

    assert response.audio_bytes == b"ID3-audio"
    assert urls[0].endswith("/audio/speech")


def test_default_audio_runner_speech_to_text_returns_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    urls = _fake_urlopen(monkeypatch, json.dumps({"text": "hello"}).encode())

    response = AudioModelRunner(provider="openai", model="gpt-4o-mini-tts", api_key="k").speech_to_text(b"\x00\x01")

    assert response.transcript == "hello"
    assert urls[0].endswith("/audio/transcriptions")


def test_default_embedding_runner_returns_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 1}}
    urls = _fake_urlopen(monkeypatch, json.dumps(body).encode())

    response = EmbeddingModelRunner(provider="openai", model="text-embedding-3-small", api_key="k").run("hello")

    assert response.embeddings == ((0.1, 0.2),)
    assert urls[0].endswith("/embeddings")


@pytest.mark.parametrize(
    ("provider", "model", "event"),
    [
        ("anthropic", "claude-sonnet-4-5", {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}}),
        ("openai", "gpt-4o", {"type": "response.output_text.delta", "delta": "hi"}),
    ],
)
def test_default_streaming_runner_yields_chunks(monkeypatch: pytest.MonkeyPatch, provider: str, model: str, event: dict[str, Any]) -> None:
    _fake_urlopen(monkeypatch, f"data: {json.dumps(event)}\n\ndata: [DONE]\n".encode())

    chunks = list(StreamingTextModelRunner(provider=provider, model=model, api_key="k").stream("hi"))

    assert chunks == ["hi"]
