from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import ImageModelConfig, TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser, HttpTransport
from vidbyte.lib.runners.types import GeneratedImage, ImageModelResponse, TextModelResponse
from vidbyte.providers.compatible import OpenAICompatibleProvider


class XAIProvider(OpenAICompatibleProvider):
    provider = ModelProvider.XAI

    def __init__(self, *, text_config: TextModelConfig | None = None, image_config: ImageModelConfig | None = None, model: str | None = None, response_parser: HttpResponseParser | None = None, **config_options: Any) -> None:
        super().__init__(text_config=text_config, model=model, response_parser=response_parser, **config_options)
        self._image_config = image_config

    async def run_image(self, *, prompt: str, transport: HttpTransport, config: ImageModelConfig | None = None) -> ImageModelResponse:
        # Execute xAI's image generation endpoint and normalize image outputs.
        config = self._image_config_for(config)
        response = await transport.request(method="POST", url=f"{config.resolved_endpoint()}/images/generations", headers=self._parser.bearer_headers(config.resolved_api_key()), json_body=self._create_image_payload(config, prompt), timeout_seconds=config.timeout_seconds)
        parsed = self._parser.parse_json_response(response, provider=self.provider.value)
        return ImageModelResponse(provider=self.provider, model=config.model, images=self._extract_images(parsed), raw=parsed)

    def _image_config_for(self, config: ImageModelConfig | None) -> ImageModelConfig:
        resolved = config or self._image_config
        if resolved is None:
            raise ProviderConfigurationError("XAIProvider requires an ImageModelConfig.", provider=self.provider.value)
        return resolved

    def _create_image_payload(self, config: ImageModelConfig, prompt: str) -> dict[str, Any]:
        # Build xAI image payloads while preserving compatible optional fields.
        payload: dict[str, Any] = {"model": config.model, "prompt": prompt}
        if config.size:
            payload["size"] = config.size
        if config.response_format:
            payload["response_format"] = config.response_format
        if config.extra_body:
            payload.update(dict(config.extra_body))
        return payload

    def _extract_images(self, parsed: Mapping[str, Any]) -> tuple[GeneratedImage, ...]:
        # Normalize xAI image data entries into SDK image objects.
        data = parsed.get("data")
        if not isinstance(data, list):
            raise ProviderResponseError("xAI image response did not include image data.", provider=self.provider.value, response_excerpt=str(parsed))
        return tuple(self._image_from_item(item) for item in data if isinstance(item, dict))

    def _image_from_item(self, item: Mapping[str, Any]) -> GeneratedImage:
        # Convert one provider image record into the SDK image dataclass.
        return GeneratedImage(url=item.get("url") if isinstance(item.get("url"), str) else None, b64_json=item.get("b64_json") if isinstance(item.get("b64_json"), str) else None, revised_prompt=item.get("revised_prompt") if isinstance(item.get("revised_prompt"), str) else None)


__all__ = [
    "XAIProvider",
]
