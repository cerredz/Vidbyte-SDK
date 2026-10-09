"""FILE: tests/test_deepseek_provider.py

PURPOSE: Regression tests for DeepSeekProvider chat-completion text extraction.
ROLE IN CODEBASE: Keeps tool-call turns from aborting runs and code-fenced replies from being corrupted.
ARCHITECTURE NOTE: Drives run_text() through an async scripted transport with one canned body.
FUNCTION INVENTORY: _ScriptedTransport fakes HTTP; DeepSeekToolCallTextTests checks tool-call text;
    DeepSeekFenceTests checks only a whole-reply JSON fence is unwrapped, at provider and agent level.
COMMON MODIFICATION PATTERNS: Add a canned message per DeepSeek response shape worth pinning.
WHAT NOT TO DO: Do not call real DeepSeek endpoints or require API keys from the environment.
KNOWN EDGE CASES: A zero-parameter tool call arrives with arguments set to an empty string; DeepSeek
    sometimes wraps a JSON answer in a json fence, while fences in code answers must survive untouched.
RELATED DOCS: docs/design/core-schema-yaml-deepseek-fixes.md, docs/design/deepseek-code-fences.md
TESTS: Run with python -m pytest -q tests/test_deepseek_provider.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping

from tests.agent_test_support import build_test_agent
from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from vidbyte.providers.compatible import DeepSeekProvider, GLMProvider

_CODE_REPLY = "Here is the fix:\n```python\nprint('x')\n```"
_TWO_FENCE_REPLY = "```bash\nls -la\n```\nRun that, then:\n```python\nprint(1)\n```"


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


class DeepSeekFenceTests(unittest.TestCase):
    """Verify DeepSeek leaves code fences alone and unwraps only a whole-reply JSON fence."""

    def _text(self, content: str, provider_type: type = DeepSeekProvider) -> str:
        transport = _ScriptedTransport({"choices": [{"message": {"role": "assistant", "content": content}}]})
        provider = provider_type(model="test-model", api_key="test-key")
        return asyncio.run(provider.run_text(prompt="q", system=None, metadata=None, transport=transport)).text

    def _agent(self, content: str, **options: object) -> object:
        transport = _ScriptedTransport({"choices": [{"message": {"role": "assistant", "content": content}}]})
        runner = TextModelRunner(TextModelConfig(provider=ModelProvider.DEEPSEEK, model="deepseek-chat", api_key="test-key"), transport=transport)
        return build_test_agent(name="worker", system_prompt="Answer.", runner=runner, provider="deepseek", model_name="deepseek-chat", **options)

    def test_code_replies_come_back_byte_identical(self) -> None:
        """Prose with fenced code keeps every fence, exactly as the base compatible provider does."""
        for content in (_CODE_REPLY, _TWO_FENCE_REPLY):
            with self.subTest(content=content):
                self.assertEqual(self._text(content), content)
                self.assertEqual(self._text(content, GLMProvider), content)

    def test_reply_that_only_ends_with_a_fence_is_untouched(self) -> None:
        """A trailing fence around JSON is still part of a prose reply, so nothing is stripped."""
        content = 'The result is:\n```json\n{"a": 1}\n```'
        self.assertEqual(self._text(content), content)

    def test_whole_reply_fence_around_non_json_is_untouched(self) -> None:
        """A reply that is only a code block keeps its fence because its body is not JSON."""
        content = "```python\nprint('x')\n```"
        self.assertEqual(self._text(content), content)

    def test_whole_reply_json_fence_is_unwrapped(self) -> None:
        """The PR #169 case: a reply that is one fence around JSON comes back as the bare JSON."""
        self.assertEqual(self._text('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(self._text("```\n[1, 2]\n```\n"), "[1, 2]")

    def test_output_schema_agent_parses_a_fenced_json_reply(self) -> None:
        """An output_schema agent on DeepSeek still gets structured output from a json-fenced reply."""
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

        reply = self._agent('```json\n{"answer": "42"}\n```', output_schema=schema).run("question")

        self.assertEqual(json.loads(reply.content), {"answer": "42"})
        self.assertEqual(reply.metadata.get("structured"), {"answer": "42"})

    def test_agent_reply_keeps_code_fences(self) -> None:
        """A plain DeepSeek agent returns a multi-fence code answer byte-identical."""
        self.assertEqual(self._agent(_TWO_FENCE_REPLY).run("question").content, _TWO_FENCE_REPLY)


if __name__ == "__main__":
    unittest.main()
