"""FILE: tests/test_pdj_stage_model_provenance.py

PURPOSE:
    Proves a prosecutor/defender/judge stage that inherits the producer's
    transport records the producer's model, not None, in its stage record,
    and that a stage on its own provider and model builds its runner with the
    agent's matched keys and mode.
ROLE IN CODEBASE:
    Regression tests for runner_model_name in
    vidbyte/lib/agents/prosecutor_defender_judge.py and for
    DebateStageRuntimeFactory._stage_handle, which passes its result on.
ARCHITECTURE NOTE:
    A real TextModelRunner with a dummy BYOK key is built offline; no request
    is sent, so no provider network call or real key is needed.
COMMON MODIFICATION PATTERNS:
    Add a case here when runner_model_name learns a new runner shape.
KNOWN EDGE CASES:
    A runner whose model_name() raises must still yield None, not an error.
    With every key variable hidden, an explicit stage runner builds only in
    DIRECT mode with its provider's key in the record; the default AUTO mode
    would need a Vidbyte key and fail.
RELATED DOCS:
    vidbyte/lib/agents/prosecutor_defender_judge.py header.
TESTS:
    Run with python -m pytest tests/test_pdj_stage_model_provenance.py.
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from vidbyte.agents.algorithms.prosecutor_defender_judge import DebateStageRuntimeFactory, _StageInvocationCounter
from vidbyte.context.algorithms.prosecutor_defender_judge import DebateStageSettings
from vidbyte.lib.agents.prosecutor_defender_judge import runner_model_name
from vidbyte.lib.config import TextModelConfig, TextModelMode
from vidbyte.lib.constants.jev import PROVIDER_API_KEY_ENV_VARS, VIDBYTE_API_KEY_ENV_VAR
from vidbyte.lib.dataclasses.agents import ProviderKeys
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.runners.text import TextModelRunner


def _text_runner() -> TextModelRunner:
    # A dummy provider key in DIRECT mode keeps the runner off the gateway, so nothing reads the environment or the network.
    return TextModelRunner(TextModelConfig(provider="deepseek", model="deepseek-chat", api_keys=["test-deepseek-key"], mode=TextModelMode.DIRECT))


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


class ExplicitStageKeysTests(unittest.TestCase):
    def setUp(self) -> None:
        # Hide every key variable, so the stage runner can only build from the agent's record in DIRECT mode.
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for env_var in (*PROVIDER_API_KEY_ENV_VARS.values(), VIDBYTE_API_KEY_ENV_VAR, "GOOGLE_API_KEY"):
            os.environ.pop(env_var, None)
        # Dummy, format-valid keys; nothing here is a real credential and no request is sent.
        self.keys = ProviderKeys(providers=("deepseek", "gemini"), keys=("test-deepseek-key", "AIza" + "t" * 35))
        self.handle = RunnerHandle(runner=_text_runner(), provider="deepseek", invoke=lambda *args, **kwargs: None, extract_text=str, extract_metadata=lambda result: {}, api_keys=self.keys, model_mode=TextModelMode.DIRECT)

    def test_explicit_stage_runner_carries_the_agents_keys_and_mode(self) -> None:
        settings = DebateStageSettings(provider="gemini", model="gemini-3.5-flash")
        stage_handle, provider, model = DebateStageRuntimeFactory(parent_runtime=None)._stage_handle(settings, self.handle)  # type: ignore[arg-type]
        self.assertEqual((provider, model), ("gemini", "gemini-3.5-flash"))
        self.assertEqual(runner_model_name(stage_handle.runner), "gemini-3.5-flash")
        self.assertIs(stage_handle.api_keys, self.keys)
        self.assertIs(stage_handle.model_mode, TextModelMode.DIRECT)

    def test_stage_counting_handle_keeps_the_keys_and_mode(self) -> None:
        counted = _StageInvocationCounter(self.handle).handle()
        self.assertIs(counted.api_keys, self.keys)
        self.assertIs(counted.model_mode, TextModelMode.DIRECT)


if __name__ == "__main__":
    unittest.main()
