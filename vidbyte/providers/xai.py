from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import ImageModelConfig, ModelProvider, TextModelConfig
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import GeneratedImage, ImageModelResponse, TextModelResponse
from vidbyte.providers.base import bearer_headers, parse_json_response


class XAIProvider:
    provider = ModelProvider.XAI

    def run_text(
        self,
        *,
        config: TextModelConfig,
        prompt: str,
        system: str | None,
        metadata: Mapping[str, object] | None,
        transport: HttpTransport,
    ) -> TextModelResponse:
        messages: list[dict[str, str]] = []
        instructions = system or config.system
        if instructions:
            messages.append({"role": "system", "content": instructions})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
        }
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        if config.max_output_tokens is not None:
            payload["max_tokens"] = config.max_output_tokens
        if config.response_format is not None:
            payload["response_format"] = config.response_format
        if metadata:
            payload["metadata"] = dict(metadata)

        response = transport.request(
            method="POST",
            url=f"{config.resolved_endpoint()}/chat/completions",
            headers=bearer_headers(config.resolved_api_key()),
            json_body=payload,
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return TextModelResponse(
            provider=self.provider,
            model=config.model,
            text=_extract_chat_text(parsed),
            raw=parsed,
            usage=parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None,
        )

    def run_image(
        self,
        *,
        config: ImageModelConfig,
        prompt: str,
        transport: HttpTransport,
    ) -> ImageModelResponse:
        payload: dict[str, Any] = {"model": config.model, "prompt": prompt}
        if config.size:
            payload["size"] = config.size
        if config.response_format:
            payload["response_format"] = config.response_format

        response = transport.request(
            method="POST",
            url=f"{config.resolved_endpoint()}/images/generations",
            headers=bearer_headers(config.resolved_api_key()),
            json_body=payload,
            timeout_seconds=config.timeout_seconds,
        )
        parsed = parse_json_response(response, provider=self.provider.value)
        return ImageModelResponse(
            provider=self.provider,
            model=config.model,
            images=_extract_images(parsed),
            raw=parsed,
        )


def _extract_chat_text(parsed: Mapping[str, Any]) -> str:
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderRequestError(
            "xAI response did not include choices.",
            provider=ModelProvider.XAI.value,
            response_excerpt=str(parsed),
        )
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ProviderRequestError(
            "xAI response did not include message content.",
            provider=ModelProvider.XAI.value,
            response_excerpt=str(parsed),
        )
    return content


def _extract_images(parsed: Mapping[str, Any]) -> tuple[GeneratedImage, ...]:
    data = parsed.get("data")
    if not isinstance(data, list):
        raise ProviderRequestError(
            "xAI image response did not include image data.",
            provider=ModelProvider.XAI.value,
            response_excerpt=str(parsed),
        )
    images: list[GeneratedImage] = []
    for item in data:
        if isinstance(item, dict):
            images.append(
                GeneratedImage(
                    url=item.get("url") if isinstance(item.get("url"), str) else None,
                    b64_json=item.get("b64_json") if isinstance(item.get("b64_json"), str) else None,
                    revised_prompt=(
                        item.get("revised_prompt")
                        if isinstance(item.get("revised_prompt"), str)
                        else None
                    ),
                )
            )
    return tuple(images)
