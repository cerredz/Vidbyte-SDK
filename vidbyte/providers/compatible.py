from __future__ import annotations

import json
import re
from typing import Any, Mapping

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider, StructuredOutputSupport
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.registries.structured_output import StructuredOutputRegistry
from vidbyte.lib.runners.types import TextModelResponse
from vidbyte.lib.util import PromptPlacement
from vidbyte.providers.output_schema import OutputSchemaFormatter

# A reply that is one markdown fence from start to end; its body is unwrapped only when it is JSON.
_WHOLE_FENCE = re.compile(r"\A\s*```(?:json)?[ \t]*\n?(.*?)\n?[ \t]*```\s*\Z", re.DOTALL | re.IGNORECASE)
# One complete reasoning block at the very start of a reply, plus the whitespace after it.
_LEADING_THINK = re.compile(r"\A\s*<think>.*?</think>\s*", re.DOTALL)


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
        usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None
        try:
            text = self._extract_chat_text(parsed)
        except ProviderResponseError as exc:
            # A billed 200 with no usable text keeps its usage on the error so the caller can still bill it.
            if usage is not None:
                exc.details["usage"] = dict(usage)
            raise
        return TextModelResponse(provider=self.provider, model=config.model, text=text, raw=parsed, usage=usage)

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
        # Put the prompt in front of the tool exchange it provoked, so the newest turn is the work, not the task again.
        history = [dict(message) for message in config.messages]
        history.insert(PromptPlacement.index(history, is_call_turn=PromptPlacement.is_chat_call_turn, boundary=config.prompt_index), {"role": "user", "content": prompt})
        messages.extend(history)
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
        match tier:
            case StructuredOutputSupport.NATIVE_SCHEMA:
                strict_schema = OutputSchemaFormatter().strict(schema)
                payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "agent_output", "schema": strict_schema, "strict": True}}
                return
            case StructuredOutputSupport.JSON_MODE:
                payload["response_format"] = {"type": "json_object"}
            case StructuredOutputSupport.STRICT_TOOLS | StructuredOutputSupport.PROMPT_ONLY:
                pass
            case _:
                raise ProviderConfigurationError(f"{self.provider.value} resolved unsupported structured-output tier {tier!r}.", provider=self.provider.value)
        # @intent below-native-the-fields-only-reach-the-model-as-text
        # JSON mode guarantees parseable JSON rather than field conformance, so each lower tier needs
        # schema guidance in the system prompt; DeepSeek also requires the word "JSON" before enabling it.
        description = StructuredOutputRegistry.describe(self.provider, config.model).schema_instruction(schema)
        messages = payload["messages"]
        if messages[0].get("role") == "system":
            messages[0]["content"] += description
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
        # @intent error-finish-reason-is-not-an-answer
        # OpenRouter reports a failure after its 200 as finish_reason "error" beside the partial text, which is
        # not the answer, so raise like the streaming error events (#999) and keep the billed usage.
        if isinstance(first, dict) and first.get("finish_reason") == "error":
            raw_error = first.get("error")
            error = raw_error if isinstance(raw_error, dict) else {}
            reason = ": ".join(str(part) for part in (error.get("code"), error.get("message")) if isinstance(part, (int, str)) and not isinstance(part, bool))
            raise ProviderResponseError(f"{self.provider.value} reply ended with an error{': ' + reason if reason else '.'}", provider=self.provider.value, response_excerpt=str(parsed))
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        # @intent empty-tool-calls-is-a-text-turn
        # vLLM-style servers send "tool_calls": [] on plain text turns; only real calls carry no text.
        if isinstance(message, dict) and isinstance(message.get("tool_calls"), list) and len(message["tool_calls"]) > 0:
            return ""
        # @intent chunked-content-answers-with-its-text-chunks
        # Mistral reasoning models send content as a list of chunks; the answer is the text chunks, never the thinking.
        if isinstance(content, list):
            return "".join(chunk["text"] for chunk in content if isinstance(chunk, dict) and chunk.get("type") == "text" and isinstance(chunk.get("text"), str))
        if not isinstance(content, str):
            raise ProviderResponseError(f"{self.provider.value} response did not include message content.", provider=self.provider.value, response_excerpt=str(parsed))
        return content

    def _raise_if_interrupted(self, parsed: Mapping[str, Any], interrupted_reason: str) -> None:
        # @intent interrupted-reply-is-not-an-answer
        # DeepSeek ("insufficient_system_resource") and GLM ("network_error") report a reply their servers cut off after
        # the 200 under their own finish_reason; the text is not the answer, so raise like OpenRouter's "error" (#1012) and keep the billed usage.
        choices = parsed.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        finish_reason = first.get("finish_reason") if isinstance(first, dict) else None
        if finish_reason == interrupted_reason:
            raise ProviderResponseError(f"{self.provider.value} reply was interrupted: {finish_reason}", provider=self.provider.value, response_excerpt=str(parsed))


class DeepSeekProvider(OpenAICompatibleProvider):
    provider = ModelProvider.DEEPSEEK

    def _extract_chat_text(self, parsed: Mapping[str, Any]) -> str:
        # DeepSeek may hallucinate tool calls and wrap JSON in markdown fences, so prefer text
        # content, fall back to the first call's arguments, and unwrap a fence only around pure JSON.
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderResponseError(f"{self.provider.value} response did not include choices.", provider=self.provider.value, response_excerpt=str(parsed))
        first = choices[0]
        self._raise_if_interrupted(parsed, "insufficient_system_resource")
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
            # @intent tool-calls-need-no-text
            # A real tool-call turn (e.g. a zero-parameter tool with arguments "") carries no text,
            # and the base provider returns "" for it; only a reply with neither text nor calls is invalid.
            if has_tool_calls:
                return ""
            raise ProviderResponseError(f"{self.provider.value} response did not include message content.", provider=self.provider.value, response_excerpt=str(parsed))
        # @intent fence-unwrap-json-only
        # Prose and code replies pass through untouched; only a reply that is entirely one fence
        # around a JSON value is unwrapped, which is the DeepSeek habit PR #169 guarded against.
        return self._unwrap_whole_json_fence(text)

    def _unwrap_whole_json_fence(self, text: str) -> str:
        match = _WHOLE_FENCE.match(text)
        if match is None:
            return text
        inner = match.group(1).strip()
        try:
            json.loads(inner)
        except ValueError:
            return text
        return inner


class GLMProvider(OpenAICompatibleProvider):
    provider = ModelProvider.GLM

    def _extract_chat_text(self, parsed: Mapping[str, Any]) -> str:
        self._raise_if_interrupted(parsed, "network_error")
        return super()._extract_chat_text(parsed)


class MiniMaxProvider(OpenAICompatibleProvider):
    provider = ModelProvider.MINIMAX

    def _extract_chat_text(self, parsed: Mapping[str, Any]) -> str:
        # @intent inline-thinking-is-not-the-answer
        # MiniMax M2/M3 put their reasoning inside content as one leading <think>...</think> block; the
        # answer is what follows. Tool-call turns are echoed from the raw message, so the reasoning
        # MiniMax requires in history stays intact.
        return _LEADING_THINK.sub("", super()._extract_chat_text(parsed), count=1)


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
