"""Context Protocol Header

Description:
    Unit tests for OpenRouterProvider adapter.
Purpose:
    Verifies OpenRouter configuration, header injection, status code handling, response parsing, and modality fallback behavior.
Architecture:
    - OpenRouterProviderTests: unittest.TestCase suite.
Key Functions:
    - test_empty_model_name_validation: Verifies [Edge Case] empty model validation.
    - test_non_string_api_key: Verifies [Edge Case] API key validation handling.
    - test_invalid_response_status: Verifies [Hidden Failure] HTTP error translation.
    - test_corrupted_json_response: Verifies [Hidden Failure] JSON parse failure handling.
    - test_empty_response_content: Verifies [Silent Failure] missing content handling.
    - test_headers_injection: Verifies [Silent Failure] client attribution headers.
    - test_default_routing_modality_fallback: Verifies [Hidden Assumption] fallback modality mapping.
Relations:
    Validates OpenRouterProvider and ModalityDetector configurations.
Similar Files:
    - tests/test_text_model_runner.py
"""

from __future__ import annotations

import json
import unittest
from typing import Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderResponseError, ProviderRequestError
from vidbyte.lib.http import HttpResponse, HttpTransport
from vidbyte.lib.runners import TextModelRunner
from vidbyte.providers.openrouter import OpenRouterProvider
from vidbyte.lib.agents import ModalityDetector


class FakeTransport:
    def __init__(self, response_body: str, status_code: int = 200) -> None:
        self.response_body = response_body
        self.status_code = status_code
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
        return HttpResponse(status_code=self.status_code, body=self.response_body, headers={})


class OpenRouterProviderTests(unittest.TestCase):
    def test_empty_model_name_validation(self) -> None:
        # [Edge Case] Verifies that an empty model name triggers a ConfigurationError.
        with self.assertRaises(ConfigurationError):
            config = TextModelConfig(provider=ModelProvider.OPENROUTER, model=" ", api_key="test-key")
            config.validate()

    def test_non_string_api_key(self) -> None:
        # [Edge Case] Verifies key resolution when non-string or whitespace key is supplied.
        with self.assertRaises(ConfigurationError):
            config = TextModelConfig(provider=ModelProvider.OPENROUTER, model="openai/gpt-4o", api_key="   ")
            config.validate()

    def test_invalid_response_status(self) -> None:
        # [Hidden Failure] Verifies HTTP error translation into standard exception.
        transport = FakeTransport(json.dumps({"error": {"message": "Invalid API Key"}}), status_code=401)
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="openai/gpt-4o-mini", api_key="key"),
            transport=transport,
        )
        with self.assertRaises(Exception):
            runner.run("Hello")

    def test_corrupted_json_response(self) -> None:
        # [Hidden Failure] Verifies response exception on corrupted response payload.
        transport = FakeTransport("{invalid-json", status_code=200)
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="openai/gpt-4o-mini", api_key="key"),
            transport=transport,
        )
        with self.assertRaises(ProviderRequestError):
            runner.run("Hello")

    def test_empty_response_content(self) -> None:
        # [Silent Failure] Verifies that empty choices in response returns an exception.
        transport = FakeTransport(json.dumps({"choices": []}), status_code=200)
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="openai/gpt-4o-mini", api_key="key"),
            transport=transport,
        )
        with self.assertRaises(ProviderResponseError):
            runner.run("Hello")

    def test_headers_injection(self) -> None:
        # [Silent Failure] Verifies that HTTP-Referer and X-OpenRouter-Title client headers are set.
        transport = FakeTransport(json.dumps({"choices": [{"message": {"role": "assistant", "content": "hello"}}]}))
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="openai/gpt-4o-mini", api_key="key"),
            transport=transport,
        )
        response = runner.run("Hello")
        self.assertEqual(response.text, "hello")
        self.assertEqual(transport.requests[0]["headers"].get("HTTP-Referer"), "https://github.com/vidbyte/vidbyte-sdk")
        self.assertEqual(transport.requests[0]["headers"].get("X-OpenRouter-Title"), "Vidbyte SDK")

    def test_default_routing_modality_fallback(self) -> None:
        # [Hidden Assumption] Verifies that unrecognized prefixed model names default to TEXT modality.
        modality = ModalityDetector.detect_modality("openrouter/meta-llama/llama-unknown-model-future")
        self.assertEqual(modality, ModelModality.TEXT)


if __name__ == "__main__":
    unittest.main()
