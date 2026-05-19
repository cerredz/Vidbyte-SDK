from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import TextModelResponse
from vidbyte.providers.base import parse_json_response


class GeminiProvider:
    provider = ModelProvider.GEMINI

    def run_text(
        self,
        *,
        config: TextModelConfig,
        prompt: str,
        system: str | None,
        metadata: Mapping[str, object] | None,
        transport: HttpTransport,
    ) -> TextModelResponse:
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        instructions = system or config.system
        if instructions:
            payload["systemInstruction"] = {"parts": [{"text": instructions}]}
        generation_config: dict[str, Any] = {}
        if config.temperature is not None:
            generation_config["temperature"] = config.temperature
        if config.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = config.max_output_tokens
        if config.response_format is not None:
            generation_config["responseMimeType"] = "application/json"
        if generation_config:
            payload["generationConfig"] = generation_config

        model = quote(config.model, safe="")
        response = transport.request(
            method="POST",
            url=f"{config.resolved_endpoint()}/models/{model}:generateContent?key={config.resolved_api_key()}",
            headers={"content-type": "application/json"},
            json_body=payload,
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(
            provider=self.provider,
            model=config.model,
            text=_extract_text(parsed),
            raw=parsed,
            usage=(
                parsed.get("usageMetadata")
                if isinstance(parsed.get("usageMetadata"), dict)
                else None
            ),
        )


def _extract_text(parsed: Mapping[str, Any]) -> str:
    candidates = parsed.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ProviderRequestError(
            "Gemini response did not include candidates.",
            provider=ModelProvider.GEMINI.value,
            response_excerpt=str(parsed),
        )
    first = candidates[0]
    if not isinstance(first, dict):
        raise ProviderRequestError(
            "Gemini candidate was malformed.",
            provider=ModelProvider.GEMINI.value,
            response_excerpt=str(parsed),
        )
    content = first.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise ProviderRequestError(
            "Gemini response did not include text parts.",
            provider=ModelProvider.GEMINI.value,
            response_excerpt=str(parsed),
        )
    chunks = [part["text"] for part in parts if isinstance(part, dict) and isinstance(part.get("text"), str)]
    if not chunks:
        raise ProviderRequestError(
            "Gemini response did not include text.",
            provider=ModelProvider.GEMINI.value,
            response_excerpt=str(parsed),
        )
    return "\n".join(chunks)
