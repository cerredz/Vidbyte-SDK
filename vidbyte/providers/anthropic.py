from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import TextModelResponse


class AnthropicProvider:
    provider = ModelProvider.ANTHROPIC

    def __init__(self, *, response_parser: HttpResponseParser | None = None) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._parser = response_parser or HttpResponseParser()

    def run_text(self, *, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport) -> TextModelResponse:
        # Execute an Anthropic Messages API request with optional tools/history.
        response = transport.request(method="POST", url=f"{config.resolved_endpoint()}/messages", headers=self._create_headers(config), json_body=self._create_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(provider=self.provider, model=config.model, text=self._extract_text(parsed), raw=parsed, usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None)

    def _create_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build Anthropic's top-level system plus stateless messages payload.
        payload: dict[str, Any] = {"model": config.model, "max_tokens": config.max_output_tokens or 1024, "messages": self._create_messages(config, prompt)}
        self._attach_instructions(payload, config, system)
        self._attach_sampling(payload, config)
        self._attach_tools(payload, config)
        self._attach_metadata(payload, config, metadata)
        self._attach_extra_body(payload, config)
        return payload

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

    def _extract_text(self, parsed: Mapping[str, Any]) -> str:
        # Collect text content blocks while leaving tool_use blocks in raw output.
        content = parsed.get("content")
        if not isinstance(content, list):
            raise ProviderRequestError("Anthropic response did not include content.", provider=self.provider.value, response_excerpt=str(parsed))
        chunks = [item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)]
        if not chunks:
            raise ProviderRequestError("Anthropic response did not include text content.", provider=self.provider.value, response_excerpt=str(parsed))
        return "\n".join(chunks)


__all__ = [
    "AnthropicProvider",
]
