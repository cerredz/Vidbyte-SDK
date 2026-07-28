from __future__ import annotations

import json
from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider, StructuredOutputSupport
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.registries.structured_output import StructuredOutputRegistry
from vidbyte.lib.runners.types import TextModelResponse


class OpenAICompatibleProvider:
    """Base adapter for OpenAI-compatible chat completion providers."""

    provider: ModelProvider

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._parser = response_parser or HttpResponseParser()

    async def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute an OpenAI-compatible chat completion request.
        config = self._config(config)
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/chat/completions", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=self._create_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
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
        # Preserves system instructions even when explicit conversation history is present.
        messages: list[Mapping[str, Any]] = []
        instructions = system or config.system
        if instructions:
            messages.append({"role": "system", "content": instructions})
        messages.extend(dict(message) for message in config.messages)
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
        # Sends the strongest structured-output request this endpoint is declared to support.
        if config.response_format is None:
            return
        schema = dict(config.response_format)
        tier = StructuredOutputRegistry.resolve(self.provider, config.model)
        if tier is StructuredOutputSupport.NATIVE_SCHEMA:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "agent_output", "schema": schema, "strict": True}}
            return
        if tier is StructuredOutputSupport.JSON_MODE:
            payload["response_format"] = {"type": "json_object"}
        self._describe_schema_in_system(payload, schema)

    def _describe_schema_in_system(self, payload: dict[str, Any], schema: dict[str, Any]) -> None:
        # @intent below-native-the-fields-only-reach-the-model-as-text
        # json_object promises parseable JSON and nothing about the declared fields, so their names
        # and types have to arrive some other way. DeepSeek additionally requires the word "json" in
        # the prompt before JSON mode engages at all, which this description satisfies.
        description = (
            "\n\nYou MUST respond with ONLY a valid JSON object matching this exact schema."
            " Use these exact field names and types:\n"
            f"```json\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n```"
        )
        messages = payload.get("messages", [])
        if not messages:
            return
        first = messages[0]
        if first.get("role") == "system":
            first["content"] += description
        else:
            messages.insert(0, {"role": "system", "content": description.strip()})

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
        if isinstance(message, dict) and isinstance(message.get("tool_calls"), list):
            return ""
        if not isinstance(content, str):
            raise ProviderResponseError(f"{self.provider.value} response did not include message content.", provider=self.provider.value, response_excerpt=str(parsed))
        return content


class DeepSeekProvider(OpenAICompatibleProvider):
    provider = ModelProvider.DEEPSEEK

    def _extract_chat_text(self, parsed: Mapping[str, Any]) -> str:
        # DeepSeek may return tool_calls even when no tools are configured,
        # and may wrap JSON in markdown code fences.
        # Always prefer text content; strip markdown wrappers.
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseError(f"{self.provider.value} response did not include choices.", provider=self.provider.value, response_excerpt=str(parsed))
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            import re
            return re.sub(r'\A\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*\Z', r'\1', content.strip(), flags=re.DOTALL)
        if not isinstance(content, str):
            raise ProviderResponseError(f"{self.provider.value} response did not include message content.", provider=self.provider.value, response_excerpt=str(parsed))
        return content

    def _extract_chat_text(self, parsed: Mapping[str, Any]) -> str:
        import re

        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseError(f"{self.provider.value} response did not include choices.", provider=self.provider.value, response_excerpt=str(parsed))
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        has_tool_calls = isinstance(message, dict) and isinstance(message.get("tool_calls"), list) and len(message["tool_calls"]) > 0
        if isinstance(content, str) and content.strip():
            text = content
        elif has_tool_calls:
            tool_args = message["tool_calls"][0].get("function", {}).get("arguments", "")
            text = tool_args if isinstance(tool_args, str) else ""
        else:
            text = content if isinstance(content, str) else ""
        if not text or not text.strip():
            raise ProviderResponseError(f"{self.provider.value} response did not include message content.", provider=self.provider.value, response_excerpt=str(parsed))
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        return text


class GLMProvider(OpenAICompatibleProvider):
    provider = ModelProvider.GLM


class MiniMaxProvider(OpenAICompatibleProvider):
    provider = ModelProvider.MINIMAX


class KimiProvider(OpenAICompatibleProvider):
    provider = ModelProvider.KIMI


class MetaProvider(OpenAICompatibleProvider):
    provider = ModelProvider.META


class MistralProvider(OpenAICompatibleProvider):
    provider = ModelProvider.MISTRAL


__all__ = [
    "DeepSeekProvider",
    "GLMProvider",
    "KimiProvider",
    "MetaProvider",
    "MiniMaxProvider",
    "MistralProvider",
    "OpenAICompatibleProvider",
]
