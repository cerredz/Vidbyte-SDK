from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import ModelProvider, TextModelConfig
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import TextModelResponse
from vidbyte.providers.base import parse_json_response


class AnthropicProvider:
    provider = ModelProvider.ANTHROPIC

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
            "model": config.model,
            "max_tokens": config.max_output_tokens or 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        instructions = system or config.system
        if instructions:
            payload["system"] = instructions
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if metadata:
            payload["metadata"] = dict(metadata)

        response = transport.request(
            method="POST",
            url=f"{config.resolved_endpoint()}/messages",
            headers={
                "x-api-key": config.resolved_api_key(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json_body=payload,
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(
            provider=self.provider,
            model=config.model,
            text=_extract_text(parsed),
            raw=parsed,
            usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None,
        )


def _extract_text(parsed: Mapping[str, Any]) -> str:
    content = parsed.get("content")
    if not isinstance(content, list):
        raise ProviderRequestError(
            "Anthropic response did not include content.",
            provider=ModelProvider.ANTHROPIC.value,
            response_excerpt=str(parsed),
        )
    chunks = [
        item["text"]
        for item in content
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
    ]
    if not chunks:
        raise ProviderRequestError(
            "Anthropic response did not include text content.",
            provider=ModelProvider.ANTHROPIC.value,
            response_excerpt=str(parsed),
        )
    return "\n".join(chunks)
