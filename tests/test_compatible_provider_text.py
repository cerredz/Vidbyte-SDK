"""FILE: tests/test_compatible_provider_text.py

PURPOSE: Regression tests for OpenAICompatibleProvider chat-completion text extraction and error messages.
ROLE IN CODEBASE: Keeps a plain text turn sent with "tool_calls": [] from losing its text, and Mistral's error message from being dropped.
ARCHITECTURE NOTE: Drives run_text() through an async scripted transport with one canned body.
FUNCTION INVENTORY: _ScriptedTransport fakes HTTP; CompatibleToolCallTextTests checks text vs tool-call turns; CompatibleErrorMessageTests checks error bodies.
COMMON MODIFICATION PATTERNS: Add a canned message per OpenAI-compatible response shape worth pinning.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: vLLM-style servers and some OpenRouter upstreams send "tool_calls": [] on text turns.
RELATED DOCS: vidbyte/providers/README.md
TESTS: Run with python -m pytest -q tests/test_compatible_provider_text.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping

from vidbyte.lib.config import TextModelMode
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.lib.http import HttpResponse, HttpResponseParser
from vidbyte.providers.compatible import GLMProvider, MiniMaxProvider, MistralProvider
from vidbyte.providers.openrouter import OpenRouterProvider
from vidbyte.providers.xai import XAIProvider

_PROVIDERS = (XAIProvider, OpenRouterProvider, MistralProvider)
# Each fake key carries the prefix its provider's keys use, so the key matcher binds it to that provider.
_PROVIDER_TEST_KEYS = {XAIProvider: "xai-test-key", OpenRouterProvider: "sk-or-v1-test-key", MistralProvider: "test-key", MiniMaxProvider: "test-key"}


class _ScriptedTransport:
    def __init__(self, body: Mapping[str, object]) -> None:
        self._body = body

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse:
        return HttpResponse(status_code=200, body=json.dumps(self._body), headers={})


class CompatibleToolCallTextTests(unittest.TestCase):
    """Verify only a turn with real tool calls is treated as carrying no text."""

    def _text(self, provider_type: type, message: Mapping[str, object]) -> str:
        transport = _ScriptedTransport({"choices": [{"message": message, "finish_reason": "stop"}]})
        provider = provider_type(model="test-model", api_keys=[_PROVIDER_TEST_KEYS[provider_type]], mode=TextModelMode.DIRECT)
        return asyncio.run(provider.run_text(prompt="q", system=None, metadata=None, transport=transport)).text

    def test_empty_tool_calls_list_keeps_the_text(self) -> None:
        """A text turn with "tool_calls": [] yields its text, while a real tool-call turn still yields ""."""
        text_turn = {"role": "assistant", "content": "The answer is 42.", "tool_calls": []}
        call_turn = {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]}
        for provider_type in _PROVIDERS:
            with self.subTest(provider=provider_type.__name__):
                self.assertEqual(self._text(provider_type, text_turn), "The answer is 42.")
                self.assertEqual(self._text(provider_type, call_turn), "")

    def test_chunked_content_answers_with_its_text_chunks(self) -> None:
        """A Mistral reasoning reply's chunk list yields only its text chunks; a plain string is unchanged."""
        thinking = {"type": "thinking", "thinking": [{"type": "text", "text": "Recall the capital of France."}]}
        reasoning_turn = {"role": "assistant", "content": [thinking, {"type": "text", "text": "Paris"}]}
        two_text_turn = {"role": "assistant", "content": [{"type": "text", "text": "Par"}, {"type": "text", "text": "is"}]}
        plain_turn = {"role": "assistant", "content": "Paris"}
        self.assertEqual(self._text(MistralProvider, reasoning_turn), "Paris")
        self.assertEqual(self._text(MistralProvider, two_text_turn), "Paris")
        self.assertEqual(self._text(MistralProvider, plain_turn), "Paris")

    def test_minimax_inline_thinking_is_not_the_answer(self) -> None:
        """A MiniMax reply's leading <think> block is dropped; other text and tool-call turns are unchanged."""
        think = "<think>\nRecall the capital of France.\n</think>\n\n"
        mid_answer = "Wrap reasoning in <think>...</think> tags."
        call_turn = {"role": "assistant", "content": think, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]}
        self.assertEqual(self._text(MiniMaxProvider, {"role": "assistant", "content": think + "Paris"}), "Paris")
        self.assertEqual(self._text(MiniMaxProvider, {"role": "assistant", "content": think + '{"city": "Paris"}'}), '{"city": "Paris"}')
        self.assertEqual(self._text(MiniMaxProvider, {"role": "assistant", "content": "Paris"}), "Paris")
        self.assertEqual(self._text(MiniMaxProvider, {"role": "assistant", "content": mid_answer}), mid_answer)
        self.assertEqual(self._text(MiniMaxProvider, call_turn), "")

    def test_glm_network_error_reply_raises_and_keeps_usage(self) -> None:
        """A GLM reply cut off by network_error raises with its billed usage; "stop" and "model_context_window_exceeded" return the text."""
        usage = {"prompt_tokens": 1200, "completion_tokens": 6}
        message = {"role": "assistant", "content": "The refund window is "}
        provider = GLMProvider(model="glm-5", api_keys=["test-key"], mode=TextModelMode.DIRECT)
        with self.assertRaises(ProviderResponseError) as caught:
            asyncio.run(provider.run_text(prompt="q", system=None, metadata=None, transport=_ScriptedTransport({"choices": [{"message": message, "finish_reason": "network_error"}], "usage": usage})))
        self.assertIn("network_error", caught.exception.message)
        self.assertEqual(caught.exception.details["usage"], usage)
        for finish_reason in ("stop", "model_context_window_exceeded"):
            with self.subTest(finish_reason=finish_reason):
                transport = _ScriptedTransport({"choices": [{"message": message, "finish_reason": finish_reason}], "usage": usage})
                self.assertEqual(asyncio.run(provider.run_text(prompt="q", system=None, metadata=None, transport=transport)).text, "The refund window is ")


class CompatibleErrorMessageTests(unittest.TestCase):
    """Verify a failed response's vendor message reaches ProviderRequestError."""

    def _message(self, body: Mapping[str, object]) -> str:
        response = HttpResponse(status_code=400, body=json.dumps(body), headers={})
        with self.assertRaises(ProviderRequestError) as caught:
            HttpResponseParser().parse_json_response(response, provider="mistral")
        return caught.exception.message

    def test_mistral_top_level_error_message_is_reported(self) -> None:
        """Mistral's documented top-level message is reported; an "error" envelope still wins; a non-string message stays generic."""
        mistral = {"object": "error", "message": "Invalid model: mistral-nope", "type": "invalid_request_error", "param": "model", "code": "unknown_model"}
        self.assertEqual(self._message(mistral), "Invalid model: mistral-nope")
        self.assertEqual(self._message({"error": {"message": "X"}, "message": "Y"}), "X")
        self.assertEqual(self._message({"message": {"detail": []}}), "Provider request failed.")


if __name__ == "__main__":
    unittest.main()
