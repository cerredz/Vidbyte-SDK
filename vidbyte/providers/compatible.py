from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import TextModelResponse


class OpenAICompatibleProvider:
    """Base adapter for OpenAI-compatible chat completion providers."""

    provider: ModelProvider

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._parser = response_parser or HttpResponseParser()

    def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute an OpenAI-compatible chat completion request.
        config = self._config(config)
        response = transport.request(method="POST", url=f"{config.resolved_endpoint()}/chat/completions", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=self._create_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(provider=self.provider, model=config.model, text=self._extract_chat_text(parsed), raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None)

    def _config(self, config: TextModelConfig | None) -> TextModelConfig:
        resolved = config or self._text_config
        if resolved is None:
            raise ProviderConfigurationError(f"{self.__class__.__name__} requires a TextModelConfig.", provider=self.provider.value)
        return resolved

    def _build_text_config(self, *, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig | None:
        if model is None:
            return None
        return TextModelConfig(provider=self.provider, model=model, **dict(config_options))

    def _create_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build chat payloads while preserving caller-supplied history.
        payload: dict[str, Any] = {"model": config.model, "messages": self._create_messages(config, prompt, system)}
        self._attach_sampling(payload, config)
        self._attach_tools(payload, config)
        self._attach_response_format(payload, config)
        self._attach_metadata(payload, config, metadata)
        self._attach_extra_body(payload, config)
        return payload

    def _create_messages(self, config: TextModelConfig, prompt: str, system: str | None) -> list[Mapping[str, Any]]:
        # Use explicit history when provided, otherwise synthesize system/user turns.
        if config.messages:
            return [dict(message) for message in config.messages] + [{"role": "user", "content": prompt}]
        messages: list[Mapping[str, Any]] = []
        instructions = system or config.system
        if instructions:
            messages.append({"role": "system", "content": instructions})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _attach_sampling(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Add shared generation controls only when users configure them.
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if config.top_p is not None:
            payload["top_p"] = config.top_p
        if config.max_output_tokens is not None:
            payload["max_tokens"] = config.max_output_tokens
        if config.stop_sequences:
            payload["stop"] = list(config.stop_sequences)

    def _attach_tools(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Pass compatible function/tool definitions through for providers that support them.
        if config.tools:
            payload["tools"] = [dict(tool) for tool in config.tools]
        if config.tool_choice is not None:
            payload["tool_choice"] = config.tool_choice

    def _attach_response_format(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Preserve structured output options for compatible chat APIs.
        if config.response_format is not None:
            payload["response_format"] = dict(config.response_format)

    def _attach_metadata(self, payload: dict[str, Any], config: TextModelConfig, metadata: Mapping[str, object] | None) -> None:
        # Merge runner-call metadata with static config metadata.
        combined = {**dict(config.metadata or {}), **dict(metadata or {})}
        if combined:
            payload["metadata"] = combined

    def _attach_extra_body(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Allow new compatible API fields without changing the SDK surface each time.
        if config.extra_body:
            payload.update(dict(config.extra_body))

    def _extract_chat_text(self, parsed: Mapping[str, Any]) -> str:
        # Normalize the first assistant message text from chat completion responses.
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseError(f"{self.provider.value} response did not include choices.", provider=self.provider.value, response_excerpt=str(parsed))
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderResponseError(f"{self.provider.value} response did not include message content.", provider=self.provider.value, response_excerpt=str(parsed))
        return content


class DeepSeekProvider(OpenAICompatibleProvider):
    provider = ModelProvider.DEEPSEEK


class GLMProvider(OpenAICompatibleProvider):
    provider = ModelProvider.GLM


class MiniMaxProvider(OpenAICompatibleProvider):
    provider = ModelProvider.MINIMAX


__all__ = [
    "DeepSeekProvider",
    "GLMProvider",
    "MiniMaxProvider",
    "OpenAICompatibleProvider",
]
