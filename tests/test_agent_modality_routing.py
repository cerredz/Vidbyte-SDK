from __future__ import annotations

import unittest

import vidbyte
from vidbyte import ModelModality, VidbyteSDK
from vidbyte.agents import AgentInput, BaseAgent
from vidbyte.lib.config import ModelProvider
from vidbyte.lib.runners import GeneratedImage, ImageModelResponse, ModalityDetector, VideoModelJob
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
        text_runner = RecordingRunner(DoneResponse("text"))
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
        text_runner = RecordingRunner(DoneResponse("text"))
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
        text_runner = RecordingRunner(DoneResponse("text"))
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
        text_runner = RecordingRunner(DoneResponse("text"))
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

    async def test_model_name_auto_detection_routes_to_image(self) -> None:
        image_runner = RecordingRunner(
            ImageModelResponse(
                provider=ModelProvider.OPENAI,
                model="gpt-image-1",
                images=(GeneratedImage(url="https://example.test/icon.png"),),
                raw={},
            )
        )
        agent = BaseAgent(
            name="auto-detector",
            system_prompt="Detect modality from model name.",
            runners={"image": image_runner},
            provider=ModelProvider.OPENAI,
            model_name="gpt-image-1",
        )

        reply = await agent.generate_reply("create an icon")

        self.assertEqual(reply.content, "https://example.test/icon.png")
        self.assertEqual(reply.metadata["modality"], "image")
        self.assertEqual(len(image_runner.calls), 1)

    async def test_model_name_auto_detection_defaults_to_text_for_unknown(self) -> None:
        text_runner = RecordingRunner(DoneResponse("text"))
        image_runner = RecordingRunner("image")
        agent = BaseAgent(
            name="unknown-model-agent",
            system_prompt="Default to text.",
            runners={"text": text_runner, "image": image_runner},
            provider=ModelProvider.OPENAI,
            model_name="some-future-gpt-model",
        )

        reply = await agent.generate_reply("hello")

        self.assertEqual(reply.content, "text")
        self.assertEqual(reply.metadata["modality"], "text")
        self.assertEqual(len(text_runner.calls), 1)
        self.assertEqual(len(image_runner.calls), 0)

    async def test_auto_detection_with_provider_and_model_creates_runner(self) -> None:
        agent = BaseAgent(
            name="lazy-agent",
            system_prompt="Auto-detect from model name and create runner.",
            provider=ModelProvider.OPENAI,
            model_name="gpt-image-1",
        )

        self.assertFalse(agent.runners)
        self.assertEqual(agent.modality, ModelModality.AUTO)


class ModalityDetectorTests(unittest.TestCase):
    def test_is_text_for_known_text_models(self) -> None:
        self.assertTrue(ModalityDetector.is_text("gpt-4o"))
        self.assertTrue(ModalityDetector.is_text("gpt-5.5"))
        self.assertTrue(ModalityDetector.is_text("gpt-5.4-mini"))
        self.assertTrue(ModalityDetector.is_text("claude-3-5-sonnet-20241022"))
        self.assertTrue(ModalityDetector.is_text("claude-opus-4-7"))
        self.assertTrue(ModalityDetector.is_text("gemini-2.5-pro"))
        self.assertTrue(ModalityDetector.is_text("gemini-3.5-flash"))
        self.assertTrue(ModalityDetector.is_text("grok-4.3"))
        self.assertTrue(ModalityDetector.is_text("grok-3"))
        self.assertTrue(ModalityDetector.is_text("deepseek-chat"))
        self.assertTrue(ModalityDetector.is_text("glm-4"))

    def test_is_image_for_known_image_models(self) -> None:
        self.assertTrue(ModalityDetector.is_image("dall-e-3"))
        self.assertTrue(ModalityDetector.is_image("gpt-image-1"))
        self.assertTrue(ModalityDetector.is_image("gpt-image-2"))
        self.assertTrue(ModalityDetector.is_image("imagen-3.0-generate-001"))
        self.assertTrue(ModalityDetector.is_image("imagen-4"))
        self.assertTrue(ModalityDetector.is_image("nano-banana-pro-preview"))

    def test_is_video_for_known_video_models(self) -> None:
        self.assertTrue(ModalityDetector.is_video("sora"))
        self.assertTrue(ModalityDetector.is_video("sora-2-pro"))
        self.assertTrue(ModalityDetector.is_video("sora-turbo"))
        self.assertTrue(ModalityDetector.is_video("veo-3.1-lite-preview"))

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
