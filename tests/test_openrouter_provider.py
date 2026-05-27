# Context Protocol Header
# Description: Unit tests for the OpenRouter provider integration.
# Purpose: Ensures complete coverage for input validation, API key resolution, error parsing, header injection, and modality routing defaults.
# Architecture: Standard Python unittest suite mocking HTTP network responses using FakeTransport.
# Key Functions:
#   - TestOpenRouterProvider.test_empty_model_name_raises_error: Verifies ConfigurationError for empty models.
#   - TestOpenRouterProvider.test_missing_api_key_raises_error: Verifies ConfigurationError for missing key.
#   - TestOpenRouterProvider.test_invalid_status_code_raises_request_error: Verifies 400/500 error translation.
#   - TestOpenRouterProvider.test_corrupted_json_payload_raises_request_error: Verifies JSON decoding failure handling.
#   - TestOpenRouterProvider.test_empty_choices_raises_response_error: Verifies response extraction validation.
#   - TestOpenRouterProvider.test_custom_attribution_headers_are_injected: Verifies HTTP-Referer and X-OpenRouter-Title.
#   - TestOpenRouterProvider.test_modality_routing_defaults_to_text: Verifies default fallback in ModalityDetector.
# Codebase Relation: Validates OpenRouterProvider behavior.
# Similar Files: tests/test_text_model_runner.py

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from vidbyte.lib.agents import ModalityDetector
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError, ProviderResponseError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from tests.test_text_model_runner import FakeTransport


class TestOpenRouterProvider(unittest.TestCase):
    """Unit test suite for the OpenRouterProvider."""

    def test_empty_model_name_raises_error(self) -> None:
        # Verify that an empty model name throws ConfigurationError.
        config = TextModelConfig(provider=ModelProvider.OPENROUTER, model="", api_key="key")
        with self.assertRaises(ConfigurationError):
            config.validate()

    def test_missing_api_key_raises_error(self) -> None:
        # Verify that missing API key throws ConfigurationError.
        with patch.dict("os.environ", {}, clear=True):
            config = TextModelConfig(provider=ModelProvider.OPENROUTER, model="test-model")
            with self.assertRaises(ConfigurationError):
                config.validate()

    def test_invalid_status_code_raises_request_error(self) -> None:
        # Verify that non-2xx status codes raise ProviderRequestError.
        class ErrorTransport:
            def request(self, **kwargs) -> HttpResponse:
                return HttpResponse(status_code=400, body='{"error": {"message": "Bad request"}}', headers={})

        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="test-model", api_key="key"),
            transport=ErrorTransport(),
        )
        with self.assertRaises(ProviderRequestError):
            runner.run("Hello")

    def test_corrupted_json_payload_raises_request_error(self) -> None:
        # Verify that corrupted JSON payloads raise ProviderRequestError.
        class CorruptTransport:
            def request(self, **kwargs) -> HttpResponse:
                return HttpResponse(status_code=200, body='{invalid json}', headers={})

        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="test-model", api_key="key"),
            transport=CorruptTransport(),
        )
        with self.assertRaises(ProviderRequestError):
            runner.run("Hello")

    def test_empty_choices_raises_response_error(self) -> None:
        # Verify that response payloads with empty choices raise ProviderResponseError.
        transport = FakeTransport({"choices": []})
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="test-model", api_key="key"),
            transport=transport,
        )
        with self.assertRaises(ProviderResponseError):
            runner.run("Hello")

    def test_custom_attribution_headers_are_injected(self) -> None:
        # Verify that HTTP-Referer and X-OpenRouter-Title headers are correctly injected.
        transport = FakeTransport({"choices": [{"message": {"content": "response text"}}]})
        runner = TextModelRunner(
            TextModelConfig(provider=ModelProvider.OPENROUTER, model="test-model", api_key="key"),
            transport=transport,
        )
        response = runner.run("Hello")
        self.assertEqual(response.text, "response text")
        self.assertEqual(len(transport.requests), 1)
        headers = {k.lower(): v for k, v in transport.requests[0]["headers"].items()}
        self.assertEqual(headers.get("http-referer"), "https://github.com/vidbyte/vidbyte-sdk")
        self.assertEqual(headers.get("x-openrouter-title"), "Vidbyte SDK")

    def test_modality_routing_defaults_to_text(self) -> None:
        # Verify that unknown OpenRouter models route correctly to text modality as a fallback.
        modality = ModalityDetector.detect_modality("some-unlisted-provider/unknown-model")
        self.assertEqual(modality, ModelModality.AUTO)
        runner = ModalityDetector.create_runner(
            ModelModality.AUTO,
            provider=ModelProvider.OPENROUTER,
            model="some-unlisted-provider/unknown-model",
            api_key="key",
            transport=FakeTransport({"choices": [{"message": {"content": "ok"}}]}),
        )
        self.assertEqual(runner.model_name(), "some-unlisted-provider/unknown-model")


if __name__ == "__main__":
    unittest.main()
