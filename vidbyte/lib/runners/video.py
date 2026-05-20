from __future__ import annotations

from vidbyte.lib.config import VideoModelConfig
from vidbyte.lib.http import HttpTransport
from vidbyte.lib.runners.types import VideoModelJob
from vidbyte.providers import get_video_provider


class VideoModelRunner:
    """Semantic runner for asynchronous video generation jobs."""

    def __init__(
        self,
        config: VideoModelConfig,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._transport = transport or HttpTransport()
        self._provider = get_video_provider(config.normalized_provider())

    def run(self, prompt: str) -> VideoModelJob:
        return self._provider.create_video(
            config=self._config,
            prompt=prompt,
            transport=self._transport,
        )

    def status(self, job_id: str) -> VideoModelJob:
        return self._provider.get_video_status(
            config=self._config,
            job_id=job_id,
            transport=self._transport,
        )

    def model_name(self) -> str:
        return self._config.model

    def print(self, response: VideoModelJob) -> None:
        print(f"{response.job_id}: {response.status}")
