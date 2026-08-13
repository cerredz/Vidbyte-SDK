from __future__ import annotations

import unittest
from unittest.mock import patch

import vidbyte
from vidbyte import VidbyteSDK
from vidbyte.agents import AgentInput, BaseAgent
from vidbyte.lib.enums import ModelModality, ModelProvider
from vidbyte.lib.runners import GeneratedImage, ImageModelResponse, ModalityDetector, Runner, VideoModelJob


class RecordingRunner:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def run(self, prompt: str, **options: object) -> object:
        self.calls.append((prompt, dict(options)))
        return self.response


class DoneResponse:
    def __init__(self, answer: str) -> None:
        self.text = ""
        self.raw = {
            "output": [
                {
                    "type": "function_call",
                    "name": "isDone",
                    "arguments": f'{{"final_answer": "{answer}"}}',
                }
            ]
        }


class StubRunnerUtility:
    def __init__(self, runner_type: str, runner: object) -> None:
        self.runner_type = runner_type
        self.runner = runner
        self.build_calls = 0

    def resolve_runner_type(self) -> str:
        return self.runner_type

    def build(self, *, transport: object | None = None) -> object:
        self.build_calls += 1
        return self.runner


class AgentModalityRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_identity_routes_to_image_runner(self) -> None:
        image_runner = RecordingRunner(
            ImageModelResponse(
                provider=ModelProvider.OPENAI,
                model="gpt-image-1",
                images=(GeneratedImage(url="https://example.test/image.png"),),
                raw={},
            )
        )
        utility = StubRunnerUtility("image", image_runner)
        agent = BaseAgent(
            name="asset-agent",
            system_prompt="Create assets.",
            provider=ModelProvider.OPENAI,
            model_name="gpt-image-1",
        )

        with patch("vidbyte.agents.base.Runner.from_model", return_value=utility) as from_model:
            reply = await agent.generate_reply("draw this")

        from_model.assert_called_once_with(
            provider="openai",
            model_name="gpt-image-1",
            api_key=None,
            temperature=None,
            options={},
        )
        self.assertEqual(reply.content, "https://example.test/image.png")
        self.assertEqual(reply.metadata["runner_type"], "image")
        self.assertEqual(reply.metadata["provider"], "openai")
        self.assertEqual(reply.metadata["model_name"], "gpt-image-1")
        self.assertEqual(len(image_runner.calls), 1)

    async def test_model_identity_routes_to_video_runner_with_agent_input_metadata(self) -> None:
        video_runner = RecordingRunner(
            VideoModelJob(
                provider=ModelProvider.OPENAI,
                model="sora-2",
                job_id="job_1",
                status="queued",
                raw={},
            )
        )
        utility = StubRunnerUtility("video", video_runner)
        agent = BaseAgent(
            name="video-agent",
            system_prompt="Create videos.",
            provider=ModelProvider.OPENAI,
            model_name="sora-2",
        )

        with patch("vidbyte.agents.base.Runner.from_model", return_value=utility):
            reply = await agent.generate_reply(AgentInput("make a clip", metadata={"request_id": "req_1"}))

        self.assertEqual(reply.content, "job_1: queued")
        self.assertEqual(reply.metadata["runner_type"], "video")
        self.assertEqual(reply.metadata["request_id"], "req_1")
        self.assertEqual(len(video_runner.calls), 1)

    async def test_plain_string_uses_text_runner_for_text_model(self) -> None:
        text_runner = RecordingRunner(DoneResponse("text"))
        utility = StubRunnerUtility("text", text_runner)
        agent = BaseAgent(
            name="writer",
            system_prompt="Write clearly.",
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.5",
        )

        with patch("vidbyte.agents.base.Runner.from_model", return_value=utility):
            reply = await agent.generate_reply("hello")

        self.assertEqual(reply.content, "text")
        self.assertEqual(reply.metadata["runner_type"], "text")
        self.assertEqual(len(text_runner.calls), 1)

    async def test_runner_cache_reuses_built_runner_by_type(self) -> None:
        text_runner = RecordingRunner(DoneResponse("text"))
        utility = StubRunnerUtility("text", text_runner)
        agent = BaseAgent(
            name="writer",
            system_prompt="Write clearly.",
            provider=ModelProvider.OPENAI,
            model_name="gpt-5.5",
        )

        with patch("vidbyte.agents.base.Runner.from_model", return_value=utility):
            first = await agent.generate_reply("first")
            second = await agent.generate_reply("second")

        self.assertEqual(first.content, "text")
        self.assertEqual(second.content, "text")
        self.assertEqual(utility.build_calls, 1)
        self.assertEqual(len(text_runner.calls), 2)

    async def test_agent_card_no_longer_exposes_modalities(self) -> None:
        agent = BaseAgent(
            name="asset-agent",
            system_prompt="Create assets.",
            provider=ModelProvider.OPENAI,
            model_name="gpt-image-1",
        )

        card = agent.card()

        self.assertFalse(hasattr(card, "modalities"))
        self.assertNotIn("ImageModelRunner", card.capabilities)

    def test_sdk_agent_client_constructs_base_agent_with_provider_model(self) -> None:
        sdk = VidbyteSDK()

        agent = sdk.agents.base(
            name="writer",
            system_prompt="Write clearly.",
            provider="openai",
            model_name="gpt-5.5",
        )

        self.assertIsInstance(agent, BaseAgent)

    def test_runner_utility_resolves_recent_provider_models(self) -> None:
        cases = [
            ("openai", "gpt-5.5", "text"),
            ("anthropic", "claude-sonnet-5", "text"),
            ("gemini", "gemini-3.5-flash", "text"),
            ("deepseek", "deepseek-v4-pro", "text"),
            ("glm", "glm-5.2", "text"),
            ("minimax", "MiniMax-M3", "text"),
            ("kimi", "kimi-k2.7-code", "text"),
            ("gemini", "gemini-omni-flash-preview", "video"),
            ("gemini", "gemini-embedding-2", "embedding"),
        ]

        for provider, model_name, expected in cases:
            with self.subTest(provider=provider, model_name=model_name):
                self.assertEqual(
                    Runner.from_model(provider=provider, model_name=model_name).resolve_runner_type(),
                    expected,
                )

    def test_runner_classes_are_not_top_level_exports(self) -> None:
        self.assertNotIn("TextModelRunner", vidbyte.__all__)
        self.assertNotIn("ImageModelRunner", vidbyte.__all__)
        self.assertNotIn("VideoModelRunner", vidbyte.__all__)


class ModalityDetectorTests(unittest.TestCase):
    def test_is_text_for_known_text_models(self) -> None:
        self.assertTrue(ModalityDetector.is_text("gpt-4o"))
        self.assertTrue(ModalityDetector.is_text("gpt-5.5"))
        self.assertTrue(ModalityDetector.is_text("gpt-5.4-mini"))
        self.assertTrue(ModalityDetector.is_text("claude-sonnet-5"))
        self.assertTrue(ModalityDetector.is_text("claude-opus-4-8"))
        self.assertTrue(ModalityDetector.is_text("gemini-3.5-flash"))
        self.assertTrue(ModalityDetector.is_text("grok-4"))
        self.assertTrue(ModalityDetector.is_text("deepseek-v4-pro"))
        self.assertTrue(ModalityDetector.is_text("glm-5.2"))
        self.assertTrue(ModalityDetector.is_text("minimax-m3"))
        self.assertTrue(ModalityDetector.is_text("kimi-k2.7-code"))

    def test_is_image_for_known_image_models(self) -> None:
        self.assertTrue(ModalityDetector.is_image("dall-e-3"))
        self.assertTrue(ModalityDetector.is_image("gpt-image-1"))
        self.assertTrue(ModalityDetector.is_image("gpt-image-2"))
        self.assertTrue(ModalityDetector.is_image("imagen-3.0-generate-001"))
        self.assertTrue(ModalityDetector.is_image("imagen-4"))
        self.assertTrue(ModalityDetector.is_image("nano-banana-pro"))

    def test_is_video_for_known_video_models(self) -> None:
        self.assertTrue(ModalityDetector.is_video("sora"))
        self.assertTrue(ModalityDetector.is_video("sora-2-pro"))
        self.assertTrue(ModalityDetector.is_video("sora-turbo"))
        self.assertTrue(ModalityDetector.is_video("veo-3.1-lite-preview"))
        self.assertTrue(ModalityDetector.is_video("gemini-omni-flash-preview"))

    def test_detect_modality_exact_match(self) -> None:
        self.assertEqual(ModalityDetector.detect_modality("gpt-4o-mini"), ModelModality.TEXT)
        self.assertEqual(ModalityDetector.detect_modality("dall-e-3"), ModelModality.IMAGE)
        self.assertEqual(ModalityDetector.detect_modality("sora"), ModelModality.VIDEO)

    def test_detect_modality_pattern_fallback(self) -> None:
        self.assertEqual(ModalityDetector.detect_modality("dall-e-4-future"), ModelModality.IMAGE)
        self.assertEqual(ModalityDetector.detect_modality("imagen-v5"), ModelModality.IMAGE)
        self.assertEqual(ModalityDetector.detect_modality("kling-v2"), ModelModality.VIDEO)
        self.assertEqual(ModalityDetector.detect_modality("gpt-5.6-experimental"), ModelModality.TEXT)
        self.assertEqual(ModalityDetector.detect_modality("claude-opus-4-8"), ModelModality.TEXT)
        self.assertEqual(ModalityDetector.detect_modality("gemini-4-pro"), ModelModality.TEXT)

    def test_boundary_helpers_live_on_detector(self) -> None:
        self.assertEqual(ModalityDetector.coerce("image"), ModelModality.IMAGE)
        self.assertEqual(
            ModalityDetector.resolve(requested=None, input_modality="auto", default="video"),
            ModelModality.VIDEO,
        )

    def test_detect_modality_unknown_returns_auto(self) -> None:
        self.assertEqual(ModalityDetector.detect_modality("completely-unknown-model"), ModelModality.AUTO)

    def test_detect_modality_empty_string_returns_auto(self) -> None:
        self.assertEqual(ModalityDetector.detect_modality(""), ModelModality.AUTO)
        self.assertEqual(ModalityDetector.detect_modality("   "), ModelModality.AUTO)

    def test_detect_modality_from_model_alias(self) -> None:
        self.assertEqual(ModalityDetector.detect_modality_from_model("gpt-4o"), ModelModality.TEXT)
        self.assertEqual(ModalityDetector.detect_modality_from_model("dall-e-3"), ModelModality.IMAGE)

    def test_false_positives_not_reported(self) -> None:
        self.assertFalse(ModalityDetector.is_image("gpt-4o"))
        self.assertFalse(ModalityDetector.is_video("gpt-4o"))
        self.assertFalse(ModalityDetector.is_text("dall-e-3"))
        self.assertFalse(ModalityDetector.is_video("dall-e-3"))
        self.assertFalse(ModalityDetector.is_text("sora"))
        self.assertFalse(ModalityDetector.is_image("sora"))

    def test_case_insensitive_detection(self) -> None:
        self.assertEqual(ModalityDetector.detect_modality("GPT-4O"), ModelModality.TEXT)
        self.assertEqual(ModalityDetector.detect_modality("Dall-E-3"), ModelModality.IMAGE)
        self.assertEqual(ModalityDetector.detect_modality("SORA"), ModelModality.VIDEO)


if __name__ == "__main__":
    unittest.main()
