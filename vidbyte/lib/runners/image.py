from __future__ import annotations

from vidbyte.lib.config import ImageModelConfig
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import ImageModelResponse
from vidbyte.providers import get_image_provider


class ImageModelRunner:
    """Semantic runner for image generation models."""

    def __init__(
        self,
        config: ImageModelConfig,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = get_image_provider(config.normalized_provider())

    def run(self, prompt: str) -> ImageModelResponse:
        return self._provider.run_image(
            config=self._config,
            prompt=prompt,
            transport=self._transport,
        )

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: ImageModelResponse) -> None:
        for image in response.images:
            print(image.url or image.b64_json or "")
