"""FILE: tests/test_compatible_provider_text.py

PURPOSE: Regression tests for OpenAICompatibleProvider chat-completion text extraction.
ROLE IN CODEBASE: Keeps a plain text turn sent with "tool_calls": [] from losing its text.
ARCHITECTURE NOTE: Drives run_text() through an async scripted transport with one canned body.
FUNCTION INVENTORY: _ScriptedTransport fakes HTTP; CompatibleToolCallTextTests checks text vs tool-call turns.
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

from vidbyte.lib.http import HttpResponse
from vidbyte.providers.compatible import MistralProvider
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


if __name__ == "__main__":
    unittest.main()
