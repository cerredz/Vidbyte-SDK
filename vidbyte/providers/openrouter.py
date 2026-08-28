"""Context Protocol Header

Description:
    Model execution provider adapter for OpenRouter text models.
Purpose:
    Subclasses OpenAICompatibleProvider to route request payloads to OpenRouter's unified endpoint with custom attribution headers.
Architecture:
    - OpenRouterProvider: Subclass of OpenAICompatibleProvider.
Key Functions:
    - run_text: Executes an OpenRouter chat completion request with HTTP-Referer and X-OpenRouter-Title.
Relations:
    Registered under central factory ModelProviders in vidbyte/providers/__init__.py.
Similar Files:
    - vidbyte/providers/compatible.py
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import TextModelResponse
from vidbyte.providers.compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """Concrete provider adapter for the OpenRouter unified API service."""

    provider = ModelProvider.OPENROUTER

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Initialize the OpenRouter provider adapter.
        super().__init__(text_config=text_config, model=model, response_parser=response_parser, **config_options)

    async def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute an OpenRouter chat completion request with custom headers for client attribution.
        config = self._config(config)
        headers = self._parser.bearer_headers(config.resolved_api_key())
        headers["HTTP-Referer"] = "https://github.com/vidbyte/vidbyte-sdk"
        headers["X-OpenRouter-Title"] = "Vidbyte SDK"
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/chat/completions", headers=headers, json_body=self._create_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(provider=self.provider, model=config.model, text=self._extract_chat_text(parsed), raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None)

    def _create_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build the chat payload and ask OpenRouter to report per-generation cost.
        payload = super()._create_payload(config, prompt, system, metadata)
        payload["usage"] = {"include": True}
        return payload
