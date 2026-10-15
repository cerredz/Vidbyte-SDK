"""FILE: tests/test_compatible_provider_text.py

PURPOSE: Regression tests for OpenAICompatibleProvider chat-completion text extraction and error messages.
ROLE IN CODEBASE: Keeps a plain text turn sent with "tool_calls": [] from losing its text, and Mistral's error message from being dropped.
ARCHITECTURE NOTE: Drives run_text() through an async scripted transport with one canned body.
FUNCTION INVENTORY: _ScriptedTransport fakes HTTP; CompatibleToolCallTextTests checks text vs tool-call turns; CompatibleErrorMessageTests checks error bodies, including non-JSON error pages.
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

from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.lib.http import HttpResponse, HttpResponseParser
from vidbyte.providers.compatible import GLMProvider, MiniMaxProvider, MistralProvider
from vidbyte.providers.openrouter import OpenRouterProvider
from vidbyte.providers.xai import XAIProvider

_PROVIDERS = (XAIProvider, OpenRouterProvider, MistralProvider)


class _ScriptedTransport:
    def __init__(self, body: Mapping[str, object]) -> None:
        self._body = body

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse:
        return HttpResponse(status_code=200, body=json.dumps(self._body), headers={})


class CompatibleToolCallTextTests(unittest.TestCase):
    """Verify only a turn with real tool calls is treated as carrying no text."""

    def _text(self, provider_type: type, message: Mapping[str, object]) -> str:
        transport = _ScriptedTransport({"choices": [{"message": message, "finish_reason": "stop"}]})
        provider = provider_type(model="test-model", api_key="test-key")
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
        provider = GLMProvider(model="glm-5", api_key="test-key")
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

    def test_non_json_error_page_is_a_failed_request_not_invalid_json(self) -> None:
        """An HTML 503 or a text/plain 400 is a failed request with its status; a 200 HTML body is still invalid JSON."""
        error_pages = (
            HttpResponse(status_code=503, body="<html><body><h1>503 Service Temporarily Unavailable</h1></body></html>", headers={"content-type": "text/html"}),
            HttpResponse(status_code=400, body="Failed to parse the request body as JSON: messages[3].content: lone leading surrogate in hex escape", headers={"content-type": "text/plain"}),
        )
        for response in error_pages:
            with self.subTest(status_code=response.status_code):
                with self.assertRaises(ProviderRequestError) as caught:
                    HttpResponseParser().parse_json_response(response, provider="xai")
                self.assertEqual(caught.exception.message, "Provider request failed.")
                self.assertEqual(caught.exception.status_code, response.status_code)
        ok_html = HttpResponse(status_code=200, body="<html><body>hello</body></html>", headers={"content-type": "text/html"})
        with self.assertRaises(ProviderRequestError) as caught:
            HttpResponseParser().parse_json_response(ok_html, provider="xai")
        self.assertEqual(caught.exception.message, "Provider returned invalid JSON.")


if __name__ == "__main__":
    unittest.main()
