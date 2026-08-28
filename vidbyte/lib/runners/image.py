from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.config import ImageModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import ImageModelResponse
from vidbyte.providers import ModelProviders


class ImageModelRunner:
    """Semantic runner for image generation models."""

    def __init__(
        self,
        config: ImageModelConfig | None = None,
        *,
        provider: ModelProvider | str | None = None,
        model: str | None = None,
        transport: HttpTransport | None = None,
        **config_options: Any,
    ) -> None:
        config = self._coerce_config(config, provider=provider, model=model, config_options=config_options)
        config.validate()
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = ModelProviders.image(config)

    async def arun(self, prompt: str) -> ImageModelResponse:
        # Async entry point; awaits the provider's HTTP call without blocking the event loop.
        return await self._provider.run_image(prompt=prompt, transport=self._transport)

    def run(self, prompt: str) -> ImageModelResponse:
        # Synchronous wrapper; raises if called from inside a running event loop.
        try:
            asyncio.get_running_loop()
            raise AgentExecutionError("ImageModelRunner.run() cannot be called from an active event loop; use await arun().")
        except RuntimeError:
            pass
        return asyncio.run(self.arun(prompt))

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: ImageModelResponse) -> None:
        for image in response.images:
            print(image.url or image.b64_json or "")

    def _coerce_config(self, config: ImageModelConfig | None, *, provider: ModelProvider | str | None, model: str | None, config_options: Mapping[str, Any]) -> ImageModelConfig:
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("ImageModelRunner requires either config or provider and model.")
        return ImageModelConfig(provider=provider, model=model, **dict(config_options))
