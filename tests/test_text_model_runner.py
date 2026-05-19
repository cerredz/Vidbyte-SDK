from __future__ import annotations

import json
import unittest
from typing import Mapping

from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner


class FakeTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
        timeout_seconds: float = 60.0,
    ) -> HttpResponse:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "json_body": dict(json_body or {}),
                "timeout_seconds": timeout_seconds,
            }
        )
        return HttpResponse(status_code=200, body=json.dumps(self.response), headers={})


class TextModelRunnerTests(unittest.TestCase):
    def test_openai_responses_request_and_text_normalization(self) -> None:
        transport = FakeTransport({"output_text": "ok", "usage": {"output_tokens": 1}})
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENAI, model="gpt-test", api_key="key"),
            transport=transport,
        )

        response = runner.run("Hello", system="System")

        self.assertEqual(response.text, "ok")
        self.assertEqual(transport.requests[0]["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(transport.requests[0]["json_body"]["input"], "Hello")
        self.assertEqual(transport.requests[0]["json_body"]["instructions"], "System")

    def test_anthropic_messages_request_and_text_normalization(self) -> None:
        transport = FakeTransport({"content": [{"type": "text", "text": "ok"}]})
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.ANTHROPIC, model="claude-test", api_key="key"),
            transport=transport,
        )

        response = runner.run("Hello")

        self.assertEqual(response.text, "ok")
        self.assertEqual(transport.requests[0]["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(transport.requests[0]["json_body"]["max_tokens"], 1024)

    def test_gemini_generate_content_request_and_text_normalization(self) -> None:
        transport = FakeTransport(
            {"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": {"x": 1}}
        )
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.GEMINI, model="gemini-test", api_key="key"),
            transport=transport,
        )

        response = runner.run("Hello")

        self.assertEqual(response.text, "ok")
        self.assertIn("models/gemini-test:generateContent?key=key", transport.requests[0]["url"])

    def test_xai_chat_completions_request_and_text_normalization(self) -> None:
        transport = FakeTransport({"choices": [{"message": {"content": "ok"}}]})
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.XAI, model="grok-test", api_key="key"),
            transport=transport,
        )

        response = runner.run("Hello")

        self.assertEqual(response.text, "ok")
        self.assertEqual(transport.requests[0]["url"], "https://api.x.ai/v1/chat/completions")
        self.assertEqual(transport.requests[0]["json_body"]["messages"][-1]["content"], "Hello")


if __name__ == "__main__":
    unittest.main()
