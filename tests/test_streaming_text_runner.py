from __future__ import annotations

import json
import unittest
from collections.abc import Iterator
from typing import Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import UnsupportedProviderError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import StreamingTextModelRunner


class FakeStreamingTransport:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.requests: list[dict] = []

    def stream_request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 120.0) -> Iterator[str]:
        self.requests.append({"method": method, "url": url, "headers": dict(headers), "json_body": dict(json_body or {})})
        yield from self._lines


def _openai_delta(text: str) -> str:
    return json.dumps({"type": "response.text.delta", "delta": text})


def _anthropic_delta(text: str) -> str:
    return json.dumps({"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


class StreamingTextRunnerTests(unittest.TestCase):
    # --- OpenAI streaming ---

    def test_openai_stream_yields_text_deltas(self) -> None:
        lines = [_openai_delta("Hello"), _openai_delta(" world")]
        transport = FakeStreamingTransport(lines)
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=transport,
        )

        chunks = list(runner.stream("Say hello"))

        self.assertEqual(chunks, ["Hello", " world"])

    def test_openai_stream_sends_to_responses_endpoint(self) -> None:
        transport = FakeStreamingTransport([_openai_delta("hi")])
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=transport,
        )

        list(runner.stream("Test"))

        self.assertIn("/responses", transport.requests[0]["url"])

    def test_openai_stream_sends_stream_true_in_payload(self) -> None:
        transport = FakeStreamingTransport([_openai_delta("ok")])
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=transport,
        )

        list(runner.stream("Test"))

        self.assertTrue(transport.requests[0]["json_body"].get("stream"))

    def test_openai_stream_filters_non_delta_events(self) -> None:
        lines = [
            json.dumps({"type": "response.created"}),
            _openai_delta("chunk1"),
            json.dumps({"type": "response.done"}),
            _openai_delta("chunk2"),
        ]
        transport = FakeStreamingTransport(lines)
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=transport,
        )

        chunks = list(runner.stream("Test"))

        self.assertEqual(chunks, ["chunk1", "chunk2"])

    def test_openai_stream_empty_response_yields_nothing(self) -> None:
        transport = FakeStreamingTransport([])
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=transport,
        )

        chunks = list(runner.stream("Test"))

        self.assertEqual(chunks, [])

    def test_openai_stream_includes_system_prompt_as_instructions(self) -> None:
        transport = FakeStreamingTransport([_openai_delta("hi")])
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=transport,
        )

        list(runner.stream("Test", system="Be concise"))

        self.assertEqual(transport.requests[0]["json_body"].get("instructions"), "Be concise")

    def test_openai_stream_preserves_runner_level_call_options(self) -> None:
        transport = FakeStreamingTransport([_openai_delta("hi")])
        runner = StreamingTextModelRunner(
            TextModelConfig(
                provider=ModelProvider.OPENAI,
                model="gpt-4o",
                api_key="key",
                tools=({"type": "function", "name": "lookup"},),
                tool_choice="auto",
                messages=({"role": "user", "content": "prior"},),
                response_format={"type": "json_object"},
            ),
            transport=transport,
        )

        list(runner.stream("Test"))

        payload = transport.requests[0]["json_body"]
        self.assertEqual(payload["tools"], [{"type": "function", "name": "lookup"}])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertIsInstance(payload["input"], list)
        self.assertEqual(payload["text"]["format"], {"type": "json_object"})

    # --- Anthropic streaming ---

    def test_anthropic_stream_yields_text_deltas(self) -> None:
        lines = [_anthropic_delta("Hello"), _anthropic_delta(" Claude")]
        transport = FakeStreamingTransport(lines)
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="key"),
            transport=transport,
        )

        chunks = list(runner.stream("Say hello"))

        self.assertEqual(chunks, ["Hello", " Claude"])

    def test_anthropic_stream_sends_to_messages_endpoint(self) -> None:
        transport = FakeStreamingTransport([_anthropic_delta("hi")])
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="key"),
            transport=transport,
        )

        list(runner.stream("Test"))

        self.assertIn("/messages", transport.requests[0]["url"])

    def test_anthropic_stream_sends_stream_true_in_payload(self) -> None:
        transport = FakeStreamingTransport([_anthropic_delta("ok")])
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="key"),
            transport=transport,
        )

        list(runner.stream("Test"))

        self.assertTrue(transport.requests[0]["json_body"].get("stream"))

    def test_anthropic_stream_filters_non_text_delta_events(self) -> None:
        lines = [
            json.dumps({"type": "message_start", "message": {}}),
            _anthropic_delta("chunk1"),
            json.dumps({"type": "message_stop"}),
            _anthropic_delta("chunk2"),
        ]
        transport = FakeStreamingTransport(lines)
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="key"),
            transport=transport,
        )

        chunks = list(runner.stream("Test"))

        self.assertEqual(chunks, ["chunk1", "chunk2"])

    def test_anthropic_stream_uses_x_api_key_header(self) -> None:
        transport = FakeStreamingTransport([_anthropic_delta("hi")])
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-3-haiku-20240307", api_key="anthro_key"),
            transport=transport,
        )

        list(runner.stream("Test"))

        self.assertEqual(transport.requests[0]["headers"].get("x-api-key"), "anthro_key")

    # --- Unsupported providers ---

    def test_gemini_provider_raises_unsupported_provider_error_at_init(self) -> None:
        with self.assertRaises(UnsupportedProviderError):
            StreamingTextModelRunner(
                TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-2.0-flash", api_key="key"),
                transport=FakeStreamingTransport([]),
            )

    def test_xai_provider_raises_unsupported_provider_error_at_init(self) -> None:
        with self.assertRaises(UnsupportedProviderError):
            StreamingTextModelRunner(
                TextModelConfig(provider=ModelProvider.XAI, model="grok-2", api_key="key"),
                transport=FakeStreamingTransport([]),
            )

    # --- Config coercion ---

    def test_missing_provider_and_model_raises_configuration_error(self) -> None:
        from vidbyte.lib.errors import ConfigurationError
        with self.assertRaises(ConfigurationError):
            StreamingTextModelRunner(transport=FakeStreamingTransport([]))

    def test_model_name_returns_configured_model(self) -> None:
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=FakeStreamingTransport([]),
        )

        self.assertEqual(runner.model_name(), "gpt-4o")

    def test_kwargs_construction_without_explicit_config(self) -> None:
        transport = FakeStreamingTransport([_openai_delta("hello")])
        runner = StreamingTextModelRunner(
            provider=ModelProvider.OPENAI,
            model="gpt-4o",
            api_key="key",
            transport=transport,
        )

        chunks = list(runner.stream("Test"))

        self.assertEqual(chunks, ["hello"])

    def test_malformed_json_lines_are_silently_skipped(self) -> None:
        # Hidden failure: malformed SSE JSON must not crash the stream
        lines = ["not-json", _openai_delta("valid"), "{broken"]
        transport = FakeStreamingTransport(lines)
        runner = StreamingTextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-4o", api_key="key"),
            transport=transport,
        )

        chunks = list(runner.stream("Test"))

        self.assertEqual(chunks, ["valid"])


if __name__ == "__main__":
    unittest.main()
