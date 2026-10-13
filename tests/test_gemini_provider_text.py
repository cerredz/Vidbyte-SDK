"""FILE: tests/test_gemini_provider_text.py

PURPOSE: Regression tests for GeminiProvider candidate text extraction.
ROLE IN CODEBASE: Keeps Gemini thought-summary parts out of the answer text.
ARCHITECTURE NOTE: Drives run_text() through an async scripted transport with one canned body.
FUNCTION INVENTORY: _ScriptedTransport fakes HTTP; GeminiThoughtPartTextTests checks thought vs answer parts.
COMMON MODIFICATION PATTERNS: Add a canned parts list per Gemini response shape worth pinning.
WHAT NOT TO DO: Do not call real provider endpoints or require API keys from the environment.
KNOWN EDGE CASES: thinkingConfig.includeThoughts puts "thought": true parts ahead of the answer part.
RELATED DOCS: vidbyte/providers/README.md
TESTS: Run with python -m pytest -q tests/test_gemini_provider_text.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping

from vidbyte.lib.config import TextModelMode
from vidbyte.lib.http import HttpResponse
from vidbyte.providers.gemini import GeminiProvider

# byok-api-keys: gemini takes only a proven key (table A), so the fake carries the AQ. prefix, built at runtime.
GEMINI_TEST_KEY = "AQ" + "." + "x" * 40
_THOUGHT = {"text": "**Recalling the capital**\nThe user wants the capital of France.", "thought": True}


class _ScriptedTransport:
    def __init__(self, body: Mapping[str, object]) -> None:
        self._body = body

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0, **kwargs: object) -> HttpResponse:
        return HttpResponse(status_code=200, body=json.dumps(self._body), headers={})


class GeminiThoughtPartTextTests(unittest.TestCase):
    """Verify thought-summary parts are never returned as the answer text."""

    def _text(self, parts: list[Mapping[str, object]]) -> str:
        transport = _ScriptedTransport({"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}]})
        provider = GeminiProvider(model="test-model", api_keys=[GEMINI_TEST_KEY], mode=TextModelMode.DIRECT)
        return asyncio.run(provider.run_text(prompt="q", system=None, metadata=None, transport=transport)).text

    def test_thought_parts_are_not_the_answer(self) -> None:
        """A thought part ahead of the answer is dropped; plain and tool-call replies are unchanged."""
        self.assertEqual(self._text([_THOUGHT, {"text": "Paris"}]), "Paris")
        self.assertEqual(self._text([_THOUGHT, {"text": '{"city": "Paris"}'}]), '{"city": "Paris"}')
        self.assertEqual(self._text([{"text": "Paris"}]), "Paris")
        self.assertEqual(self._text([_THOUGHT, {"functionCall": {"name": "lookup", "args": {}}}]), "")


if __name__ == "__main__":
    unittest.main()
