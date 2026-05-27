# Context Protocol Header
# Description: This file implements the OpenRouter provider adapter.
# Purpose: OpenRouter acts as a single API gateway to route requests to hundreds of models from different providers (OpenAI, Anthropic, Gemini, DeepSeek, etc.).
# Architecture: This class inherits from OpenAICompatibleProvider since OpenRouter's REST API is OpenAI-compatible. It customizes the HTTP headers with app attribution.
# Key Functions:
#   - OpenRouterProvider.run_text: Orchestrates the OpenRouter completion request.
#   - OpenRouterProvider._build_request_headers: Builds Bearer auth & client attribution headers.
#   - OpenRouterProvider._execute_http_call: Performs the synchronous REST request.
# Codebase Relation: Integrated as one of the canonical ModelProvider types in ModelProviders.text.
# Similar Files: vidbyte/providers/compatible.py, vidbyte/providers/xai.py

from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpResponse, HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import TextModelResponse
from vidbyte.providers.compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """SDK adapter for the OpenRouter API."""

    provider = ModelProvider.OPENROUTER

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Initialize the OpenRouter provider adapter.
        super().__init__(text_config=text_config, model=model, response_parser=response_parser, **config_options)

    def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute an OpenRouter chat completion request.
        config = self._config(config)
        headers = self._build_request_headers(config)
        payload = self._create_payload(config, prompt, system, metadata)
        response = self._execute_http_call(config, headers, payload, transport)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(provider=self.provider, model=config.model, text=self._extract_chat_text(parsed), raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None)

    def _build_request_headers(self, config: TextModelConfig) -> dict[str, str]:
        # Build OpenRouter custom HTTP headers including client attribution.
        headers = self._parser.bearer_headers(config.resolved_api_key())
        headers["HTTP-Referer"] = "https://github.com/vidbyte/vidbyte-sdk"
        headers["X-OpenRouter-Title"] = "Vidbyte SDK"
        return headers

    def _execute_http_call(self, config: TextModelConfig, headers: dict[str, str], payload: dict[str, Any], transport: HttpTransport) -> HttpResponse:
        # Perform the actual network request over the standard http transport.
        return transport.request(method="POST", url=f"{config.resolved_endpoint()}/chat/completions", headers=headers, json_body=payload, timeout_seconds=config.timeout_seconds)


__all__ = [
    "OpenRouterProvider",
]
