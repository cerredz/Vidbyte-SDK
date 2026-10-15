from __future__ import annotations

import unittest
from types import SimpleNamespace

from vidbyte.agents.algorithms.prosecutor_defender_judge import DebateStageRuntimeFactory
from vidbyte.context.algorithms.prosecutor_defender_judge import DebateStageSettings
from vidbyte.lib.agents.prosecutor_defender_judge import runner_model_name
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.runners.text import TextModelRunner


def _text_runner() -> TextModelRunner:
    # A dummy provider key keeps the runner on BYOK, so nothing reads the environment or the network.
    return TextModelRunner(TextModelConfig(provider="deepseek", model="deepseek-chat", api_key="test-deepseek-key"))


class _RaisingModelNameRunner:
    def model_name(self) -> str:
        raise RuntimeError("model unknown")


class RunnerModelNameTests(unittest.TestCase):
    def test_reads_the_model_from_the_sdk_text_runner(self) -> None:
        self.assertEqual(runner_model_name(_text_runner()), "deepseek-chat")

    def test_keeps_reading_public_config_and_model_attribute_shapes(self) -> None:
        self.assertEqual(runner_model_name(SimpleNamespace(config=SimpleNamespace(model="gpt-4o"))), "gpt-4o")
        self.assertEqual(runner_model_name(SimpleNamespace(config=SimpleNamespace(model_name="claude-x"))), "claude-x")
        self.assertEqual(runner_model_name(SimpleNamespace(model="gemini-y")), "gemini-y")

    def test_returns_none_when_the_runner_names_no_model(self) -> None:
        self.assertIsNone(runner_model_name(object()))
        self.assertIsNone(runner_model_name(_RaisingModelNameRunner()))


class InheritedStageModelTests(unittest.TestCase):
    def test_inherited_transport_stage_records_the_producer_model(self) -> None:
        runner = _text_runner()
        handle = RunnerHandle(runner=runner, provider="deepseek", invoke=lambda *args, **kwargs: None, extract_text=str, extract_metadata=lambda result: {})
        stage_handle, provider, model = DebateStageRuntimeFactory(parent_runtime=None)._stage_handle(DebateStageSettings(), handle)  # type: ignore[arg-type]
        self.assertIs(stage_handle, handle)
        self.assertEqual((provider, model), ("deepseek", "deepseek-chat"))


if __name__ == "__main__":
    unittest.main()
