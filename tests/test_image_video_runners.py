from __future__ import annotations

import json
import unittest
from typing import Mapping

from vidbyte.lib.config import ImageModelConfig, ModelProvider, VideoModelConfig
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import ImageModelRunner, VideoModelRunner


class FakeTransport:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
        timeout_seconds: float = 60.0,
        **kwargs: object,
    ) -> HttpResponse:
        self.requests.append({"method": method, "url": url, "json_body": dict(json_body or {})})
        return HttpResponse(status_code=200, body=json.dumps(self.responses.pop(0)), headers={})


class ImageVideoRunnerTests(unittest.TestCase):
    def test_openai_image_runner_normalizes_urls(self) -> None:
        transport = FakeTransport([{"data": [{"url": "https://example.test/image.png"}]}])
        runner = ImageModelRunner(
            ImageModelConfig(provider=ModelProvider.OPENAI, model="gpt-image-test", api_key="key"),
            transport=transport,
        )

        response = runner.run("draw")

        self.assertEqual(response.images[0].url, "https://example.test/image.png")
        self.assertEqual(transport.requests[0]["url"], "https://api.openai.com/v1/images/generations")

    def test_xai_image_runner_normalizes_base64(self) -> None:
        transport = FakeTransport([{"data": [{"b64_json": "abc"}]}])
        runner = ImageModelRunner(
            ImageModelConfig(provider=ModelProvider.XAI, model="grok-image-test", api_key="key"),
            transport=transport,
        )

        response = runner.run("draw")

        self.assertEqual(response.images[0].b64_json, "abc")
        self.assertEqual(transport.requests[0]["url"], "https://api.x.ai/v1/images/generations")

    def test_openai_video_runner_creates_and_checks_jobs(self) -> None:
        transport = FakeTransport(
            [
                {"id": "job_1", "status": "queued"},
                {"id": "job_1", "status": "completed"},
            ]
        )
        runner = VideoModelRunner(
            VideoModelConfig(provider=ModelProvider.OPENAI, model="sora-test", api_key="key"),
            transport=transport,
        )

        created = runner.run("make a video")
        checked = runner.status(created.job_id)

        self.assertEqual(created.status, "queued")
        self.assertEqual(checked.status, "completed")
        self.assertEqual(transport.requests[0]["url"], "https://api.openai.com/v1/videos")
        self.assertEqual(transport.requests[1]["url"], "https://api.openai.com/v1/videos/job_1")


if __name__ == "__main__":
    unittest.main()
