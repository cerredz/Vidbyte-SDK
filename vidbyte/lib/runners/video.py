from __future__ import annotations

from typing import Any, Mapping

from vidbyte.lib.config import VideoModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import VideoModelJob
from vidbyte.providers import ModelProviders


class VideoModelRunner:
    """Semantic runner for asynchronous video generation jobs."""

    def __init__(
        self,
        config: VideoModelConfig | None = None,
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
        self._provider = ModelProviders.video(config)

    def run(self, prompt: str) -> VideoModelJob:
        return self._provider.create_video(
            prompt=prompt,
            transport=self._transport,
        )

    def status(self, job_id: str) -> VideoModelJob:
        return self._provider.get_video_status(
            job_id=job_id,
            transport=self._transport,
        )

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: VideoModelJob) -> None:
        print(f"{response.job_id}: {response.status}")

    def _coerce_config(
        self,
        config: VideoModelConfig | None,
        *,
        provider: ModelProvider | str | None,
        model: str | None,
        config_options: Mapping[str, Any],
    ) -> VideoModelConfig:
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("VideoModelRunner requires either config or provider and model.")
        return VideoModelConfig(provider=provider, model=model, **dict(config_options))
