from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import TextModelResponse


class GeminiProvider:
    provider = ModelProvider.GEMINI

    def __init__(self, *, text_config: TextModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        # Keep response parsing injectable for tests and alternate transports.
        self._text_config = text_config or self._build_text_config(model=model, config_options=config_options)
        self._parser = response_parser or HttpResponseParser()

    def run_text(self, *, prompt: str, system: str | None, metadata: Mapping[str, object] | None, transport: HttpTransport, config: TextModelConfig | None = None) -> TextModelResponse:
        # Execute Gemini generateContent with contents, tools, safety, and cache options.
        config = self._config(config)
        model = quote(config.model, safe="")
        response = transport.request(method="POST", url=f"{config.resolved_endpoint()}/models/{model}:generateContent", headers=self._create_headers(config), json_body=self._create_payload(config, prompt, system, metadata), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(provider=self.provider, model=config.model, text=self._extract_text(parsed), raw=parsed, usage=parsed.get("usageMetadata") if isinstance(parsed.get("usageMetadata"), dict) else None)

    def _config(self, config: TextModelConfig | None) -> TextModelConfig:
        resolved = config or self._text_config
        if resolved is None:
            raise ProviderConfigurationError("GeminiProvider requires a TextModelConfig.", provider=self.provider.value)
        return resolved

    def _build_text_config(self, *, model: str | None, config_options: Mapping[str, Any]) -> TextModelConfig | None:
        if model is None:
            return None
        return TextModelConfig(provider=self.provider, model=model, **dict(config_options))

    def _create_headers(self, config: TextModelConfig) -> dict[str, str]:
        # Prefer the x-goog-api-key header so the key is not embedded in URLs.
        return {"x-goog-api-key": config.resolved_api_key(), "content-type": "application/json"}

    def _create_payload(self, config: TextModelConfig, prompt: str, system: str | None, metadata: Mapping[str, object] | None) -> dict[str, Any]:
        # Build the Gemini request body around its contents array contract.
        payload: dict[str, Any] = {"contents": self._create_contents(config, prompt)}
        self._attach_instructions(payload, config, system)
        self._attach_generation_config(payload, config)
        self._attach_tools(payload, config)
        self._attach_safety(payload, config)
        self._attach_cache(payload, config)
        self._attach_extra_body(payload, config, metadata)
        return payload

    def _create_contents(self, config: TextModelConfig, prompt: str) -> list[Mapping[str, Any]]:
        # Gemini supports alternating user/model turns through the contents array.
        if config.messages:
            return [dict(message) for message in config.messages] + [{"role": "user", "parts": [{"text": prompt}]}]
        return [{"role": "user", "parts": [{"text": prompt}]}]

    def _attach_instructions(self, payload: dict[str, Any], config: TextModelConfig, system: str | None) -> None:
        # Gemini uses systemInstruction for developer-provided instructions.
        instructions = system or config.system
        if instructions:
            payload["systemInstruction"] = {"parts": [{"text": instructions}]}

    def _attach_generation_config(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Collect Gemini generation options under generationConfig.
        generation_config: dict[str, Any] = {}
        if config.temperature is not None:
            generation_config["temperature"] = config.temperature
        if config.top_p is not None:
            generation_config["topP"] = config.top_p
        if config.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = config.max_output_tokens
        if config.response_format is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = dict(config.response_format)
        if config.thinking_config is not None:
            generation_config["thinkingConfig"] = dict(config.thinking_config)
        if generation_config:
            payload["generationConfig"] = generation_config

    def _attach_tools(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Gemini supports function tools, code execution, and toolConfig.
        if config.tools:
            payload["tools"] = [dict(tool) for tool in config.tools]
        if config.tool_config is not None:
            payload["toolConfig"] = dict(config.tool_config)

    def _attach_safety(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # Safety settings override Gemini defaults per harm category.
        if config.safety_settings:
            payload["safetySettings"] = [dict(setting) for setting in config.safety_settings]

    def _attach_cache(self, payload: dict[str, Any], config: TextModelConfig) -> None:
        # cachedContent lets callers reuse long context already cached with Gemini.
        if config.cached_content:
            payload["cachedContent"] = config.cached_content

    def _attach_extra_body(self, payload: dict[str, Any], config: TextModelConfig, metadata: Mapping[str, object] | None) -> None:
        # Preserve forward compatibility for new Gemini fields and caller metadata.
        if metadata:
            payload.setdefault("labels", {}).update({str(key): str(value) for key, value in metadata.items()})
        if config.extra_body:
            payload.update(dict(config.extra_body))

    def _extract_text(self, parsed: Mapping[str, Any]) -> str:
        # Normalize text parts from the first Gemini candidate.
        candidates = parsed.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProviderResponseError("Gemini response did not include candidates.", provider=self.provider.value, response_excerpt=str(parsed))
        first = candidates[0]
        content = first.get("content") if isinstance(first, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            raise ProviderResponseError("Gemini response did not include text parts.", provider=self.provider.value, response_excerpt=str(parsed))
        chunks = [part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)]
        if not chunks:
            raise ProviderResponseError("Gemini response did not include text.", provider=self.provider.value, response_excerpt=str(parsed))
        return "\n".join(chunks)


__all__ = [
    "GeminiProvider",
]
