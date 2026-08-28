from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import TextModelResponse


class AnthropicProvider:
    provider = ModelProvider.ANTHROPIC

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._parser = response_parser or HttpResponseParser()

    async def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute an Anthropic Messages API request with optional tools/history.
        config = self._config(config)
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/messages", headers=self._create_headers(config), json_body=self._create_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(provider=self.provider, model=config.model, text=self._extract_text(parsed), raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None)

    def _config(self, config: TextModelConfig | None) -> TextModelConfig:
        resolved = config or self._text_config
        if resolved is None:
            raise ProviderConfigurationError("AnthropicProvider requires a TextModelConfig.", provider=self.provider.value)
        return resolved

    def _build_text_config(self, *, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig | None:
        if model is None:
            return None
        return TextModelConfig(provider=self.provider, model=model, **dict(config_options))

    def _create_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build Anthropic's top-level system plus stateless messages payload.
        payload: dict[str, Any] = {"model": config.model, "max_tokens": config.max_output_tokens or 1024, "messages": self._create_messages(config, prompt)}
        self._attach_instructions(payload, config, system)
        self._attach_sampling(payload, config)
        self._attach_tools(payload, config)
        self._attach_response_format(payload, config)
        self._attach_metadata(payload, config, metadata)
        self._attach_extra_body(payload, config)
        return payload

    def _attach_response_format(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Anthropic carries the schema under output_config.format rather than a response_format field.
        if config.response_format is not None:
            payload["output_config"] = {"format": {"type": "json_schema", "schema": dict(config.response_format)}}

    def _create_headers(self, config: TextModelConfig) -> dict[str, str]:
        # Include the required Anthropic version and API key headers.
        return {"x-api-key": config.resolved_api_key(), "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def _create_messages(self, config: TextModelConfig, prompt: str) -> list[Mapping[str, Any]]:
        # Preserve multi-turn history and append the current user prompt.
        return [dict(message) for message in config.messages] + [{"role": "user", "content": prompt}]

    def _attach_instructions(self, payload: dict[str, Any], config: TextModelConfig, system: str | None) -> None:
        # Anthropic uses a top-level system parameter rather than a system role.
        instructions = system or config.system
        if instructions:
            payload["system"] = instructions

    def _attach_sampling(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Add shared generation controls only when users configure them.
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if config.top_p is not None:
            payload["top_p"] = config.top_p
        if config.stop_sequences:
            payload["stop_sequences"] = list(config.stop_sequences)

    def _attach_tools(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Anthropic tools and tool_choice pass through to the Messages API.
        if config.tools:
            payload["tools"] = [dict(tool) for tool in config.tools]
        if config.tool_choice is not None:
            payload["tool_choice"] = config.tool_choice
        if config.thinking_config:
            payload["thinking"] = dict(config.thinking_config)

    def _attach_metadata(self, payload: dict[str, Any], config: TextModelConfig, metadata: Mapping[str, object] | None) -> None:
        # Merge runner-call metadata with static config metadata.
        combined = {**dict(config.metadata or {}), **dict(metadata or {})}
        if combined:
            payload["metadata"] = combined

    def _attach_extra_body(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Allow new Anthropic fields without changing the SDK surface each time.
        if config.extra_body:
            payload.update(dict(config.extra_body))

    def stream_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> Iterator[str]:
        # POST to /messages with stream=True and yield text from content_block_delta events.
        config = self._config(config)
        payload = self._create_payload(config, prompt, system, metadata)
        payload["stream"] = True
        for raw_line in transport.stream_request(method="POST", url=f"{config.resolved_endpoint()}/messages", headers=self._create_headers(config), json_body=payload, timeout_seconds=config.timeout_seconds):
            chunk = self._extract_stream_delta(raw_line)
            if chunk is not None:
                yield chunk

    def _extract_stream_delta(self, raw_line: str) -> str | None:
        # Parse one SSE JSON line and return the text delta, or None for non-delta events.
        try:
            event = json.loads(raw_line)
        except (json.JSONDecodeError, ValueError):
            return None
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                text = delta.get("text")
                return text if isinstance(text, str) else None
        return None

    def _extract_text(self, parsed: Mapping[str, Any]) -> str:
        # Collect text content blocks while leaving tool_use blocks in raw output.
        content = parsed.get("content")
        if not isinstance(content, list):
            raise ProviderResponseError("Anthropic response did not include content.", provider=self.provider.value, response_excerpt=str(parsed))
        chunks = [item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)]
        if not chunks:
            if any(isinstance(item, dict) and item.get("type") == "tool_use" for item in content):
                return ""
            raise ProviderResponseError("Anthropic response did not include text content.", provider=self.provider.value, response_excerpt=str(parsed))
        return "\n".join(chunks)


__all__ = [
    "AnthropicProvider",
]
