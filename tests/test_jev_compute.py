"""FILE: tests/test_jev_compute.py

PURPOSE: Verifies JevAgent's mid-run compute checkpoint without network calls: the AgentRuntime hook it runs on, the JevComputeSettings switch, and the run brief and facts it keeps and reports.
ROLE IN CODEBASE: Covers vidbyte/agents/jev/compute/, JevRuntime's begin and hook forwarding, AgentRuntime._after_tool_iteration, and the compute fields of JevAgentResponse.
ARCHITECTURE NOTE: Scripted runners replace the main agent's model and a patched arun replaces the brief writer's model; the loop, the runtime, the controller, the keeper, and verification run for real.
COMMON MODIFICATION PATTERNS: Add a case here when the checkpoint gains a step, when the hook's call site moves, or when a new response field reports a checkpoint outcome.
KNOWN EDGE CASES: The hook runs only after an iteration that ran tools and continues, never on a finishing iteration, and a chosen specialist runs without a checkpoint.
RELATED DOCS: docs/design/jev-compute-checkpoint.md and docs/design/jev-run-brief.md.
TESTS: python -m pytest tests/test_jev_compute.py.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevComputeSettings as RootJevComputeSettings
from vidbyte import JevRunBriefSettings as RootJevRunBriefSettings
from vidbyte import tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRunBriefSettings, JevRuntimeSettings, JevSpecialist
from vidbyte.agents.jev.compute import JevComputeController
from vidbyte.lib.dataclasses.jev import JevRunBriefPayload
from vidbyte.lib.enums import JevRunBriefUpdateStatus, ModelProvider
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.runners import TextModelResponse

REQUEST = "Look up each topic: alpha, beta, gamma, delta."


class ScriptedRunner:
    """Minimal synchronous generative runner that returns scripted model responses in order."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls = 0

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.calls += 1
        return self.responses.pop(0)


class RawResponse:
    """OpenAI-shaped raw response carrying one scripted function call."""

    def __init__(self, name: str, arguments: dict[str, Any], call_id: str) -> None:
        self.text = ""
        self.raw = {"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]}


@tool
def lookup(topic: str) -> str:
    """Look up one topic and return what was found about it."""
    return f"found:{topic}"


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "researcher", "system_prompt": "Research carefully.", "provider": "openai", "model_name": "gpt-4.1", "api_key": "main-key", "tools": (lookup,)}
    values.update(overrides)
    return JevAgentSettings(**values)


def _compute(**brief: Any) -> JevRuntimeSettings:
    return JevRuntimeSettings(compute=JevComputeSettings(brief=JevRunBriefSettings(**brief)))


def _lookups_then_done(topics: tuple[str, ...]) -> ScriptedRunner:
    calls = [RawResponse("lookup", {"topic": topic}, f"c{index}") for index, topic in enumerate(topics)]
    return ScriptedRunner(*calls, RawResponse("isDone", {"final_answer": "all topics found"}, "done"))


def _payload() -> JevRunBriefPayload:
    return JevRunBriefPayload.model_validate({
        "goal": "Look up each of the four topics",
        "goal_evidence": [{"event": "E1", "quote": "Look up each topic: alpha, beta, gamma, delta."}],
        "current_step": None,
        "next_steps": [],
        "items": [
            {"id": "alpha", "name": "alpha", "group": "topics", "status": "done", "evidence": [{"event": "E2", "quote": "found:alpha"}]},
            {"id": "delta", "name": "delta", "group": "topics", "status": "pending", "evidence": [{"event": "E1", "quote": "delta"}]},
        ],
        "approaches": [],
        "open_failures": [],
    })


class JevComputeSettingsTests(unittest.TestCase):
    def test_compute_is_off_by_default_and_validated_when_set(self) -> None:
        self.assertIsNone(JevRuntimeSettings().compute)
        self.assertIsInstance(JevRuntimeSettings(compute=JevComputeSettings()).compute.brief, JevRunBriefSettings)  # type: ignore[union-attr]
        with self.assertRaises(ConfigurationError):
            JevRuntimeSettings(compute=object())  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            JevComputeSettings(brief=object())  # type: ignore[arg-type]

    def test_settings_are_exported_from_the_root_namespace(self) -> None:
        self.assertIs(RootJevComputeSettings, JevComputeSettings)
        self.assertIs(RootJevRunBriefSettings, JevRunBriefSettings)


class JevComputeHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_checkpoint_runs_after_each_continuing_tool_iteration_only(self) -> None:
        # [Edge Case] three tool iterations continue the loop; the fourth finishes, so it gets no checkpoint.
        agent = bind_test_runner(JevAgent(_settings(), _compute()), _lookups_then_done(("alpha", "beta", "gamma")))
        seen: list[tuple[int, int]] = []

        async def record(state: Any) -> None:
            # The loop state is one mutable object, so read it at call time rather than after the run.
            seen.append((state.iteration_count, len(state.call_contexts)))

        with patch.object(JevComputeController, "checkpoint", new=AsyncMock(side_effect=record)):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "all topics found")
        self.assertEqual(seen, [(1, 1), (2, 2), (3, 3)])

    async def test_a_plain_final_answer_runs_no_checkpoint(self) -> None:
        runner = ScriptedRunner(TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="direct answer", raw={}))
        agent = bind_test_runner(JevAgent(_settings(), _compute()), runner)
        with patch.object(JevComputeController, "checkpoint", new=AsyncMock()) as checkpoint:
            await agent.arun(REQUEST)
        checkpoint.assert_not_awaited()

    async def test_disabled_compute_builds_and_reports_nothing(self) -> None:
        agent = bind_test_runner(JevAgent(_settings()), _lookups_then_done(("alpha", "beta", "gamma", "delta")))
        self.assertIsNone(agent.compute)
        reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "all topics found")
        self.assertIsNone(agent.response.run_facts)
        self.assertIsNone(agent.response.run_brief)
        self.assertEqual(agent.response.run_brief_updates, [])


class JevComputeCheckpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_brief_refreshes_on_cadence_and_is_reported_with_facts(self) -> None:
        # [Happy Path] the first brief is due at iteration 3; facts are reported from the last checkpoint.
        agent = bind_test_runner(JevAgent(_settings(), _compute()), _lookups_then_done(("alpha", "beta", "gamma", "delta")))
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=_payload()))) as writer:
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "all topics found")
        writer.assert_awaited_once()
        self.assertIn('first="E2" last="E4"', writer.await_args.args[0].prompt)
        updates = agent.response.run_brief_updates
        self.assertEqual([(update.status, update.iteration) for update in updates], [(JevRunBriefUpdateStatus.UPDATED, 3)])
        self.assertEqual([item.id for item in agent.response.run_brief.items], ["alpha", "delta"])  # type: ignore[union-attr]
        self.assertEqual((agent.response.run_facts.iteration, agent.response.run_facts.tool_calls), (4, 4))  # type: ignore[union-attr]

    async def test_a_writer_outage_never_changes_the_run(self) -> None:
        agent = bind_test_runner(JevAgent(_settings(), _compute()), _lookups_then_done(("alpha", "beta", "gamma")))
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(side_effect=VidbyteSdkError("writer down"))):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "all topics found")
        self.assertIsNone(agent.response.run_brief)
        self.assertEqual([update.status for update in agent.response.run_brief_updates], [JevRunBriefUpdateStatus.UNAVAILABLE])

    async def test_each_run_starts_a_new_brief(self) -> None:
        agent = JevAgent(_settings(), _compute())
        assert agent.compute is not None
        writer = AsyncMock(return_value=SimpleNamespace(structured=_payload()))
        with patch.object(agent.compute.keeper.writer, "arun", new=writer):
            await bind_test_runner(agent, _lookups_then_done(("alpha", "beta", "gamma"))).arun(REQUEST)
            await bind_test_runner(agent, _lookups_then_done(("alpha", "beta"))).arun("Look up alpha and beta.")
        self.assertEqual(writer.await_count, 1)
        self.assertIsNone(agent.response.run_brief)
        self.assertEqual(agent.compute.keeper.request, "Look up alpha and beta.")

    async def test_a_chosen_specialist_runs_without_a_checkpoint(self) -> None:
        specialist_agent = SimpleNamespace(arun=AsyncMock(return_value=SimpleNamespace(content="specialist answer", metadata={}, structured=None)))
        specialist = Mock(spec=JevSpecialist, agent=specialist_agent, title="schema")
        agent = JevAgent(_settings(), _compute())
        assert agent.compute is not None
        with (
            patch.object(agent.preflight, "pass_", new=AsyncMock(return_value=True)),
            patch.object(agent.preflight, "specialist", new=specialist),
            patch.object(agent.compute, "begin") as begin,
        ):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "specialist answer")
        begin.assert_not_called()


if __name__ == "__main__":
    unittest.main()
