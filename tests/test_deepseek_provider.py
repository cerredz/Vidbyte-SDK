"""FILE: tests/test_deepseek_provider.py

PURPOSE: Regression tests for DeepSeekProvider chat-completion text extraction.
ROLE IN CODEBASE: Keeps a valid DeepSeek tool-call turn from aborting an agent run.
ARCHITECTURE NOTE: Drives run_text() through an async scripted transport with one canned body.
FUNCTION INVENTORY: _ScriptedTransport fakes HTTP; DeepSeekToolCallTextTests checks tool-call text.
COMMON MODIFICATION PATTERNS: Add a canned message per DeepSeek response shape worth pinning.
WHAT NOT TO DO: Do not call real DeepSeek endpoints or require API keys from the environment.
KNOWN EDGE CASES: A zero-parameter tool call arrives with arguments set to an empty string.
RELATED DOCS: docs/design/core-schema-yaml-deepseek-fixes.md
TESTS: Run with python -m pytest -q tests/test_deepseek_provider.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping

from vidbyte.lib.http import HttpResponse
from vidbyte.providers.compatible import DeepSeekProvider


class _ScriptedTransport:
    def __init__(self, body: Mapping[str, object]) -> None:
        self._body = body

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], json_body: Mapping[str, object] | None = None, timeout_seconds: float = 60.0) -> HttpResponse:
        return HttpResponse(status_code=200, body=json.dumps(self._body), headers={})


class DeepSeekToolCallTextTests(unittest.TestCase):
    """Verify DeepSeek tool-call turns never fail for missing text."""

    def test_zero_argument_tool_call_returns_empty_text(self) -> None:
        """A tool call whose arguments are "" yields "" text instead of a ProviderResponseError."""
        message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "ping", "arguments": ""}}]}
        transport = _ScriptedTransport({"choices": [{"message": message}]})
        provider = DeepSeekProvider(model="deepseek-v4-pro", api_key="test-key")

        response = asyncio.run(provider.run_text(prompt="ping", system=None, metadata=None, transport=transport))

        self.assertEqual(response.text, "")


if __name__ == "__main__":
    unittest.main()
