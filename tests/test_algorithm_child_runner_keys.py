"""FILE: tests/test_algorithm_child_runner_keys.py

PURPOSE:
    Proves a RunnerHandle keeps the agent's matched api_keys record and
    model_mode through with_runner and wrap_text, that the independent
    critic's explicit reviewer runner is built with them, and that a critic
    whose producer failed over reviews on the fallback model.
ROLE IN CODEBASE:
    Regression tests for vidbyte/lib/dataclasses/runner.py and for
    IndependentCriticRuntimeAlgorithm._reviewer_handle and arun in
    vidbyte/agents/algorithms/independent_critic.py.
ARCHITECTURE NOTE:
    A real TextModelRunner is built offline from dummy, format-valid keys with
    every key variable hidden; no request is sent and no real key is read.
COMMON MODIFICATION PATTERNS:
    Add a case here when RunnerHandle gains a new way to derive a handle, so
    the derived handle is checked to keep the keys and mode.
KNOWN EDGE CASES:
    In the default AUTO mode the reviewer runner would need a Vidbyte key and
    fail to build; only DIRECT with the reviewer provider's key in the record
    builds, and another provider's key never stands in for it.
RELATED DOCS:
    vidbyte/lib/dataclasses/runner.py and vidbyte/agents/fallback.py
    (@intent children-carry-the-matched-keys).
TESTS:
    Run with python -m pytest tests/test_algorithm_child_runner_keys.py.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from vidbyte import ContextWindow
from vidbyte.agents import AgentFallback, AgentRuntime, FallbackModel
from vidbyte.agents.algorithms.independent_critic import IndependentCriticRuntimeAlgorithm
from vidbyte.context.algorithms import IndependentCriticAlgorithm
from vidbyte.lib.agents.prosecutor_defender_judge import runner_model_name
from vidbyte.lib.constants.jev import PROVIDER_API_KEY_ENV_VARS, VIDBYTE_API_KEY_ENV_VAR
from vidbyte.lib.dataclasses.agents import ProviderKeys
from vidbyte.lib.dataclasses.runner import RunnerHandle
from vidbyte.lib.enums import TextModelMode
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.tools import Tools
from vidbyte.tools.security import PermissionPolicy

# Dummy, format-valid provider keys; nothing here is a real credential.
_KEYS = ProviderKeys(providers=("deepseek", "gemini"), keys=("sk-test-deepseek", "AIza" + "t" * 35))


def _handle(api_keys: ProviderKeys | None = _KEYS, model_mode: TextModelMode = TextModelMode.DIRECT) -> RunnerHandle:
    # A producer handle as BaseAgent builds it, carrying the agent's matched keys and mode.
    return RunnerHandle(runner=object(), provider="deepseek", invoke=lambda *args, **kwargs: None, extract_text=str, extract_metadata=lambda result: {}, api_keys=api_keys, model_mode=model_mode)


class RunnerHandleKeysTests(unittest.TestCase):
    def test_a_bare_handle_defaults_to_no_keys_and_auto(self) -> None:
        handle = RunnerHandle(runner=object(), provider="deepseek", invoke=lambda *args, **kwargs: None, extract_text=str, extract_metadata=lambda result: {})
        self.assertIsNone(handle.api_keys)
        self.assertIs(handle.model_mode, TextModelMode.AUTO)

    def test_derived_handles_keep_the_keys_and_mode(self) -> None:
        captured: list[str] = []
        derived = _handle().with_runner(object(), "gemini").wrap_text(captured.append)
        self.assertIs(derived.api_keys, _KEYS)
        self.assertIs(derived.model_mode, TextModelMode.DIRECT)
        self.assertEqual(derived.provider, "gemini")
        self.assertEqual(derived.extract_text("seen"), "seen")
        self.assertEqual(captured, ["seen"])


class CriticReviewerKeysTests(unittest.TestCase):
    def setUp(self) -> None:
        # Hide every key variable, so the reviewer runner can only build from the agent's record in DIRECT mode.
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for env_var in (*PROVIDER_API_KEY_ENV_VARS.values(), VIDBYTE_API_KEY_ENV_VAR, "GOOGLE_API_KEY"):
            os.environ.pop(env_var, None)
        algorithm = IndependentCriticAlgorithm(reviewer_provider="gemini", reviewer_model="gemini-3.5-flash")
        self.critic = IndependentCriticRuntimeAlgorithm(runtime=None, algorithm=algorithm)  # type: ignore[arg-type]

    def test_explicit_reviewer_runner_carries_the_agents_keys_and_mode(self) -> None:
        reviewer = self.critic._reviewer_handle(_handle())
        self.assertEqual(reviewer.provider, "gemini")
        self.assertEqual(runner_model_name(reviewer.runner), "gemini-3.5-flash")
        self.assertIs(reviewer.api_keys, _KEYS)
        self.assertIs(reviewer.model_mode, TextModelMode.DIRECT)

    def test_explicit_reviewer_never_borrows_another_providers_key(self) -> None:
        deepseek_only = ProviderKeys(providers=("deepseek",), keys=("sk-test-deepseek",))
        with self.assertRaises(ConfigurationError) as ctx:
            self.critic._reviewer_handle(_handle(api_keys=deepseek_only))
        self.assertIn("Missing API key for provider gemini", str(ctx.exception))


class _ScriptedRunner:
    """A model that answers from a script, or raises a provider outage on every call when it is down."""

    def __init__(self, model: str, replies: tuple[str, ...] = (), *, down: bool = False) -> None:
        self.model, self.replies, self.down = model, list(replies), down
        self.prompts: list[str] = []

    def model_name(self) -> str:
        return self.model


async def _invoke(runner: _ScriptedRunner, prompt: str, **kwargs: object) -> str:
    runner.prompts.append(prompt)
    if runner.down:
        raise ProviderRequestError("primary is down", provider="deepseek", status_code=503)
    return runner.replies.pop(0)


class _BackupChain(AgentFallback):
    """A deepseek -> openai chain whose backup is a scripted runner, so no real runner is built."""

    def __init__(self, backup: _ScriptedRunner) -> None:
        super().__init__([FallbackModel(provider="deepseek", model="deepseek-chat"), FallbackModel(provider="openai", model=backup.model)])
        self.backup = backup

    def build_runner(self, index: int) -> object:
        return self.backup


class CriticAfterFailoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_runs_on_the_fallback_model_the_producer_switched_to(self) -> None:
        primary = _ScriptedRunner("deepseek-chat", down=True)
        backup = _ScriptedRunner("gpt-backup", ("FINAL Paris.", '{"verdict": "pass", "summary": "Checked.", "findings": []}'))
        runtime = AgentRuntime(agent_name="worker", system_prompt="Work.", tools=Tools(), permission_policy=PermissionPolicy(), algorithm=ContextWindow.preset.independent_critic, fallback=_BackupChain(backup))
        context = runtime.build_context("Look up Paris.", base_context=None, history=(), agent_history=(), agent_metadata={}, existing_tool_calls=())
        handle = RunnerHandle(runner=primary, provider="deepseek", invoke=_invoke, extract_text=str, extract_metadata=lambda result: {})

        # The default failure policy raises when the review fails, so completing proves the review ran.
        result = await runtime.arun("Look up Paris.", handle=handle, context=context)

        self.assertEqual(result.output, "FINAL Paris.")
        self.assertEqual(len(primary.prompts), 1)
        self.assertEqual(len(backup.prompts), 2)
        self.assertIn("FINAL Paris.", backup.prompts[1])
        review = result.metadata["independent_critic"]
        self.assertEqual(review["status"], "reviewed")
        self.assertEqual((review["reviewer"]["provider"], review["reviewer"]["model"]), ("openai", "gpt-backup"))


if __name__ == "__main__":
    unittest.main()
