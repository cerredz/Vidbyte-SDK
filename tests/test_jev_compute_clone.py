"""FILE: tests/test_jev_compute_clone.py

PURPOSE: Verifies the CLONE dynamic-compute option: its setting, the clone agents it builds, and the launch the checkpoint runs when Jev selects it.
ROLE IN CODEBASE: Covers JevComputeSettings.clones, JevCloneAgent, and the CLONE branch of JevComputeController.checkpoint through real JevAgent loops.
ARCHITECTURE NOTE: The main loop uses a scripted runner and Jev uses the scripted decision helper from the compute-situation tests; clone replies are scripted on JevCloneAgent.arun.
COMMON MODIFICATION PATTERNS: Add a case when the launch policy, the clone prompt, or the results message changes.
KNOWN EDGE CASES: A failed clone is dropped, a launch with no replies appends nothing, and only the first CLONE selection in a run launches.
RELATED DOCS: docs/design/jev-compute-clone.md.
TESTS: python -m pytest tests/test_jev_compute_clone.py.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from tests.test_jev_compute_situations import REQUEST, ScriptedJev, _call, _helper, lookup
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRuntimeSettings
from vidbyte.agents.jev.compute.clone import JevCloneAgent
from vidbyte.agents.jev.settings import JevRunBriefSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevRunBriefAppendPayload
from vidbyte.lib.enums import DecisionModelMode, JevDynamicComputeOption
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.compute import JevComputeRegistry

_HELPER = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
CLONE_KEYS = {key.value for key in JevComputeRegistry.question_keys(JevDynamicComputeOption.CLONE)}


class RecordingRunner:
    """Scripted main-agent runner that keeps every call's keyword arguments, so tests can read the messages sent."""

    def __init__(self, lookups: int) -> None:
        self.responses: list[object] = [_call("lookup", {"topic": f"t{index}"}, f"c{index}") for index in range(lookups)]
        self.responses.append(_call("isDone", {"final_answer": "done"}, "end"))
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _settings() -> JevAgentSettings:
    return JevAgentSettings(name="researcher", system_prompt="Research.", provider="openai", model_name="gpt-4.1", api_key="main-key", tools=(lookup,))


def _agent(runner: RecordingRunner, *, clones: int = 2, every: int = 3) -> JevAgent:
    compute = JevComputeSettings(brief=JevRunBriefSettings(every_iterations=every), dynamic_compute=tuple(JevDynamicComputeOption), clones=clones)
    runtime = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), compute=compute)
    return bind_test_runner(JevAgent(_settings(), runtime), runner)


def _contents(runner: RecordingRunner) -> str:
    # Joins every message the main agent sent on its last model call.
    return "\n".join(str(message.get("content", "")) for message in runner.calls[-1]["messages"])


def _clone_jev() -> ScriptedJev:
    # Only CLONE's questions clear the threshold, so every recognition selects CLONE.
    return ScriptedJev({key: 0.95 for key in CLONE_KEYS}, default=0.1)


class JevCloneSettingsTests(unittest.TestCase):
    def test_clone_is_opt_in_and_the_count_is_bounded(self) -> None:
        self.assertNotIn(JevDynamicComputeOption.CLONE, JevComputeSettings().dynamic_compute)
        self.assertEqual(JevComputeSettings().clones, 2)
        self.assertEqual(JevComputeSettings(clones=4).clones, 4)
        for invalid in (0, 5, True, 2.0):
            with self.assertRaises(ConfigurationError):
                JevComputeSettings(clones=invalid)  # type: ignore[arg-type]

    def test_a_clone_copies_the_main_agent_configuration_with_its_own_name(self) -> None:
        clone = JevCloneAgent(_settings(), 2)
        self.assertEqual(clone.name, "researcher-clone-2")
        self.assertEqual(clone.system_prompt, "Research.")
        self.assertEqual(clone.tools.names(), JevAgent(_settings()).tools.names())


class JevCloneLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, agent: JevAgent, scripted: ScriptedJev, replies: list[object]) -> AsyncMock:
        clone_run = AsyncMock(side_effect=replies)
        payload = JevRunBriefAppendPayload.model_validate({"notes": []})
        assert agent.compute is not None
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=payload))),
            patch(_HELPER, new=_helper(scripted)),
            patch.object(JevCloneAgent, "arun", new=clone_run),
        ):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "done")
        return clone_run

    async def test_a_clone_selection_runs_the_clones_and_returns_their_results_to_the_main_loop(self) -> None:
        runner = RecordingRunner(lookups=4)
        agent = _agent(runner, clones=3)
        replies = [SimpleNamespace(content=f"result {index}") for index in (1, 2, 3)]
        clone_run = await self._run(agent, _clone_jev(), replies)
        self.assertEqual(clone_run.await_count, 3)
        prompt = clone_run.await_args_list[0].args[0].prompt
        self.assertIn(REQUEST, prompt)
        self.assertIs(agent.response.compute_decisions[0].option, JevDynamicComputeOption.CLONE)
        assert agent.response.clone is not None
        self.assertEqual(agent.response.clone.outputs, ("result 1", "result 2", "result 3"))
        self.assertIn("# Attempt 3\n\nresult 3", _contents(runner))

    async def test_only_the_first_clone_selection_in_a_run_launches(self) -> None:
        agent = _agent(RecordingRunner(lookups=6), every=1)
        clone_run = await self._run(agent, _clone_jev(), [SimpleNamespace(content="a"), SimpleNamespace(content="b")])
        self.assertGreater(len(agent.response.compute_decisions), 1)
        self.assertTrue(all(decision.option is JevDynamicComputeOption.CLONE for decision in agent.response.compute_decisions))
        self.assertEqual(clone_run.await_count, 2)

    async def test_a_failed_clone_is_dropped_and_an_empty_launch_appends_nothing(self) -> None:
        agent = _agent(RecordingRunner(lookups=4))
        await self._run(agent, _clone_jev(), [VidbyteSdkError("provider down"), SimpleNamespace(content="kept")])
        assert agent.response.clone is not None
        self.assertEqual(agent.response.clone.outputs, ("kept",))

        runner = RecordingRunner(lookups=4)
        agent = _agent(runner)
        await self._run(agent, _clone_jev(), [VidbyteSdkError("down"), SimpleNamespace(content="  ")])
        self.assertIsNone(agent.response.clone)
        self.assertNotIn("# Attempt", _contents(runner))

    async def test_another_selection_launches_no_clone(self) -> None:
        agent = _agent(RecordingRunner(lookups=4))
        clone_run = await self._run(agent, ScriptedJev(default=0.9), [])
        self.assertIs(agent.response.compute_decisions[0].option, JevDynamicComputeOption.FRESH_AGENT)
        clone_run.assert_not_awaited()
        self.assertIsNone(agent.response.clone)


if __name__ == "__main__":
    unittest.main()
