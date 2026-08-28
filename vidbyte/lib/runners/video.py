from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from vidbyte.lib.config import VideoModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import AgentExecutionError, ConfigurationError
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

    async def arun(self, prompt: str) -> VideoModelJob:
        # Async entry point for video job creation; awaits the provider call without blocking.
        return await self._provider.create_video(prompt=prompt, transport=self._transport)

    async def astatus(self, job_id: str) -> VideoModelJob:
        # Async entry point for job status polling; awaits the provider call without blocking.
        return await self._provider.get_video_status(job_id=job_id, transport=self._transport)

    def run(self, prompt: str) -> VideoModelJob:
        # Synchronous wrapper for video job creation; raises if called from a running event loop.
        try:
            asyncio.get_running_loop()
            raise AgentExecutionError("VideoModelRunner.run() cannot be called from an active event loop; use await arun().")
        except RuntimeError:
            pass
        return asyncio.run(self.arun(prompt))

    def status(self, job_id: str) -> VideoModelJob:
        # Synchronous wrapper for job status polling; raises if called from a running event loop.
        try:
            asyncio.get_running_loop()
            raise AgentExecutionError("VideoModelRunner.status() cannot be called from an active event loop; use await astatus().")
        except RuntimeError:
            pass
        return asyncio.run(self.astatus(job_id))

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: VideoModelJob) -> None:
        print(f"{response.job_id}: {response.status}")

    def _coerce_config(self, config: VideoModelConfig | None, *, provider: ModelProvider | str | None, model: str | None, config_options: Mapping[str, Any]) -> VideoModelConfig:
        if config is not None:
            return config
        if provider is None or model is None:
            raise ConfigurationError("VideoModelRunner requires either config or provider and model.")
        return VideoModelConfig(provider=provider, model=model, **dict(config_options))
