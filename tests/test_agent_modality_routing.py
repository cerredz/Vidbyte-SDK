from __future__ import annotations

import unittest

import vidbyte
from vidbyte import ModelModality, VidbyteSDK
from vidbyte.agents import AgentInput, BaseAgent
from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import GeneratedImage, ImageModelResponse, VideoModelJob
from vidbyte.strategies import BaseStrategy, StrategyResult


class RecordingRunner:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def run(self, prompt: str, **options: object) -> object:
        self.calls.append((prompt, dict(options)))
        return self.response


class RunnerCapturingStrategy(BaseStrategy):
    name = "capture"

    def __init__(self) -> None:
        self.runner: object | None = None

    async def arun(self, prompt: str, **kwargs: object) -> StrategyResult:
        self.runner = kwargs["runner"]
        return StrategyResult(output=f"strategy:{prompt}", strategy_name=self.name)


class AgentModalityRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_agent_modality_routes_to_image_runner(self) -> None:
        image_runner = RecordingRunner(
            ImageModelResponse(
                provider=ModelProvider.OPENAI,
                model="image-test",
                images=(GeneratedImage(url="https://example.test/image.png"),),
                raw={},
            )
        )
        text_runner = RecordingRunner("text")
        agent = BaseAgent(
            name="asset-agent",
            system_prompt="Create assets.",
            runners={"text": text_runner, "image": image_runner},
            modality=ModelModality.IMAGE,
        )

        reply = await agent.generate_reply("draw this")

        self.assertEqual(reply.content, "https://example.test/image.png")
        self.assertEqual(reply.metadata["modality"], "image")
        self.assertEqual(len(image_runner.calls), 1)
        self.assertEqual(len(text_runner.calls), 0)

    async def test_call_modality_override_wins(self) -> None:
        image_runner = RecordingRunner("image")
        text_runner = RecordingRunner("text")
        agent = BaseAgent(
            name="writer",
            system_prompt="Write clearly.",
            runners={"text": text_runner, "image": image_runner},
            modality="image",
        )

        reply = await agent.generate_reply("plain text", modality="text")

        self.assertEqual(reply.content, "text")
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertEqual(len(text_runner.calls), 1)
        self.assertEqual(len(image_runner.calls), 0)

    async def test_typed_input_modality_routes_without_prompt_guessing(self) -> None:
        video_runner = RecordingRunner(
            VideoModelJob(
                provider=ModelProvider.OPENAI,
                model="video-test",
                job_id="job_1",
                status="queued",
                raw={},
            )
        )
        text_runner = RecordingRunner("text")
        agent = BaseAgent(
            name="video-agent",
            system_prompt="Create videos.",
            runners={"text": text_runner, "video": video_runner},
        )

        reply = await agent.generate_reply(
            AgentInput("make a clip", modality=ModelModality.VIDEO, metadata={"request_id": "req_1"})
        )

        self.assertEqual(reply.content, "job_1: queued")
        self.assertEqual(reply.metadata["modality"], "video")
        self.assertEqual(reply.metadata["request_id"], "req_1")
        self.assertEqual(len(video_runner.calls), 1)
        self.assertEqual(len(text_runner.calls), 0)

    async def test_plain_string_defaults_to_text_runner(self) -> None:
        text_runner = RecordingRunner("text")
        image_runner = RecordingRunner("image")
        agent = BaseAgent(
            name="auto-agent",
            system_prompt="Route conservatively.",
            runners={"text": text_runner, "image": image_runner},
        )

        reply = await agent.generate_reply("draw an icon")

        self.assertEqual(reply.content, "text")
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertEqual(len(text_runner.calls), 1)
        self.assertEqual(len(image_runner.calls), 0)

    async def test_strategy_receives_selected_runner(self) -> None:
        strategy = RunnerCapturingStrategy()
        image_runner = RecordingRunner("image")
        agent = BaseAgent(
            name="strategist",
            system_prompt="Use the selected runner.",
            strategy=strategy,
            runners={"image": image_runner},
            modality="image",
        )

        reply = await agent.generate_reply("asset brief")

        self.assertEqual(reply.content, "strategy:asset brief")
        self.assertIs(strategy.runner, image_runner)
        self.assertEqual(reply.metadata["modality"], "image")

    async def test_agent_card_exposes_modalities_not_runner_classes(self) -> None:
        agent = BaseAgent(
            name="asset-agent",
            system_prompt="Create assets.",
            runners={"image": RecordingRunner("image")},
            modality="image",
        )

        card = agent.card()

        self.assertEqual(card.modalities, (ModelModality.IMAGE,))
        self.assertNotIn("ImageModelRunner", card.capabilities)

    def test_sdk_agent_client_constructs_base_agent(self) -> None:
        sdk = VidbyteSDK()

        agent = sdk.agents.base(name="writer", system_prompt="Write clearly.", modality="text")

        self.assertIsInstance(agent, BaseAgent)

    def test_runner_classes_are_not_top_level_exports(self) -> None:
        self.assertNotIn("TextModelRunner", vidbyte.__all__)
        self.assertNotIn("ImageModelRunner", vidbyte.__all__)
        self.assertNotIn("VideoModelRunner", vidbyte.__all__)


if __name__ == "__main__":
    unittest.main()
