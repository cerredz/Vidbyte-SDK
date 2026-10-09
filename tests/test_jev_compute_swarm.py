"""FILE: tests/test_jev_compute_swarm.py

PURPOSE: Verifies the SWARM dynamic-compute option: its setting, its plan questions, the plan reader, the helpers, and the launch_swarm tool the checkpoint offers when Jev selects SWARM.
ROLE IN CODEBASE: Covers JevComputeSettings.swarm_agents, JevSwarmPlanRegistry, JevSwarmPlanReader, JevSwarmAgent, JevSwarmTool, and the SWARM branch of JevComputeController through real JevAgent loops.
ARCHITECTURE NOTE: The main loop uses a recording runner, recognition and plan checks each use a scripted Jev, and helper replies are scripted on JevSwarmAgent.arun.
COMMON MODIFICATION PATTERNS: Add a case when the plan rules, the attempt budget, the helper prompt, or the results text changes.
KNOWN EDGE CASES: A rejected plan costs an attempt and the last rejection closes the tool; a failed helper is reported as failed; an unavailable plan check passes the plan; other selections add no tool.
RELATED DOCS: docs/design/jev-compute-swarm.md.
TESTS: python -m pytest tests/test_jev_compute_swarm.py.
"""

from __future__ import annotations

import json
import re
import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from tests.test_jev_compute_situations import REQUEST, ScriptedJev, _call, lookup
from vidbyte.agents.jev import (
    JevAgent,
    JevAgentSettings,
    JevComputeSettings,
    JevRuntimeSettings,
)
from vidbyte.agents.jev.compute.swarm import JevSwarmAgent
from vidbyte.agents.jev.compute.swarm_plan import JevSwarmPlanReader
from vidbyte.agents.jev.settings import JevRunBriefSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import (
    JevDecisionRequest,
    JevRunBriefAppendPayload,
    JevSwarmAssignment,
)
from vidbyte.lib.enums import DecisionModelMode, JevDynamicComputeOption
from vidbyte.lib.enums.jev import JevSwarmPlanQuestionKey
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.compute import JevComputeRegistry, JevSwarmPlanRegistry
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse

_RECOGNIZER = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
_PLAN_CHECK = "vidbyte.agents.jev.compute.swarm_plan.DecisionModelHelper"
SWARM_KEYS = {key.value for key in JevComputeRegistry.question_keys(JevDynamicComputeOption.SWARM)}
TOOL = "launch_swarm"


def _assignment(name: str) -> dict[str, str]:
    return {
        "name": name,
        "objective": f"Audit {name} for SQL injection.",
        "inputs": f"src/api/{name}.py",
        "deliverable": "A list of findings with line numbers.",
        "boundaries": f"Only read src/api/{name}.py.",
        "verification": "Re-read every flagged line.",
    }


def _plan(*names: str) -> dict[str, Any]:
    return {"conventions": "Report findings as `path:line - issue`.", "assignments": [_assignment(name) for name in names]}


class RecordingRunner:
    """Scripted main-agent runner: three lookups, the given launch_swarm calls, then isDone; it keeps every call's keyword arguments."""

    def __init__(self, *plans: Mapping[str, Any]) -> None:
        self.responses: list[object] = [_call("lookup", {"topic": f"t{index}"}, f"c{index}") for index in range(3)]
        self.responses.extend(_call(TOOL, dict(plan), f"s{index}") for index, plan in enumerate(plans))
        self.responses.append(_call("isDone", {"final_answer": "done"}, "end"))
        self.calls: list[dict[str, Any]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)

    def tool_names(self, index: int) -> set[str]:
        # Returns the tool names the model was offered on one call, whatever the provider schema shape.
        return {schema.get("name") or schema.get("function", {}).get("name") for schema in self.calls[index].get("tools", ())}

    def sent(self, index: int = -1) -> str:
        # Returns every message of one call as text, including tool outputs.
        return json.dumps(self.calls[index]["messages"], default=str)


class RoundsJev(ScriptedJev):
    """Scripted plan check whose P(true) overrides change per request, in order."""

    def __init__(self, *rounds: Mapping[str, float], error: Exception | None = None) -> None:
        super().__init__(default=0.9, error=error)
        self.rounds = list(rounds)

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        if self.rounds:
            self.yes = dict(self.rounds.pop(0))
        return await super().arun(request)


def _plan_helper(scripted: ScriptedJev) -> type:
    class ScriptedPlanHelper:
        noul_passes = DecisionModelHelper.noul_passes

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedJev:  # type: ignore[misc]
            return scripted

    return ScriptedPlanHelper


def _recognizer_helper(scripted: ScriptedJev) -> type:
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedJev:  # type: ignore[misc]
            return scripted

    return ScriptedHelper


def _swarm_jev() -> ScriptedJev:
    # Only SWARM's questions clear the threshold, so every recognition selects SWARM.
    return ScriptedJev({key: 0.95 for key in SWARM_KEYS}, default=0.1)


def _settings(*tools: object) -> JevAgentSettings:
    return JevAgentSettings(name="researcher", system_prompt="Research.", provider="openai", model_name="gpt-4.1", api_key="main-key", tools=tools or (lookup,))


def _agent(runner: RecordingRunner, *, swarm_agents: int = 4) -> JevAgent:
    compute = JevComputeSettings(brief=JevRunBriefSettings(every_iterations=3), dynamic_compute=tuple(JevDynamicComputeOption), swarm_agents=swarm_agents)
    runtime = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED), compute=compute)
    return bind_test_runner(JevAgent(_settings(), runtime), runner)


class JevSwarmSettingsTests(unittest.TestCase):
    def test_swarm_is_opt_in_and_the_team_size_is_bounded(self) -> None:
        self.assertNotIn(JevDynamicComputeOption.SWARM, JevComputeSettings().dynamic_compute)
        self.assertEqual(JevComputeSettings().swarm_agents, 10)
        self.assertEqual(JevComputeSettings(swarm_agents=2).swarm_agents, 2)
        for invalid in (1, 11, True, 4.0):
            with self.assertRaises(ConfigurationError):
                JevComputeSettings(swarm_agents=invalid)  # type: ignore[arg-type]

    def test_a_helper_copies_the_main_agent_configuration_without_the_launch_tool(self) -> None:
        assignment = JevSwarmAssignment(id="A2", **_assignment("users"))
        helper = JevSwarmAgent(_settings(), assignment)
        self.assertEqual(helper.name, "researcher-swarm-A2")
        self.assertEqual(helper.system_prompt, "Research.")
        self.assertEqual(helper.tools.names(), JevAgent(_settings()).tools.names())
        self.assertNotIn(TOOL, helper.tools.names())

    def test_a_caller_tool_named_launch_swarm_is_refused_only_when_swarm_is_enabled(self) -> None:
        def launch_swarm(task: str) -> str:
            """Caller tool whose name the SWARM option reserves."""
            return task

        decision = DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED)
        with self.assertRaises(ConfigurationError):
            JevAgent(_settings(launch_swarm), JevRuntimeSettings(decision=decision, compute=JevComputeSettings(dynamic_compute=("swarm",))))
        JevAgent(_settings(launch_swarm), JevRuntimeSettings(decision=decision, compute=JevComputeSettings()))


class JevSwarmPlanQuestionTests(unittest.TestCase):
    def test_four_plan_questions_are_asked_once_per_assignment(self) -> None:
        self.assertEqual(JevSwarmPlanRegistry.question_keys(), tuple(JevSwarmPlanQuestionKey))
        questions = JevSwarmPlanRegistry.questions(("A1", "A2"))
        self.assertEqual([question.name for question in questions[:4]], [f"{key.value}.A1" for key in JevSwarmPlanQuestionKey])
        self.assertEqual(len(questions), 8)
        for key in JevSwarmPlanQuestionKey:
            question = JevSwarmPlanRegistry.get(key)
            wire = question.to_question("A7")
            self.assertIn("assignment with id A7", wire.instructions)
            sentences = re.split(r"(?<=[.!?])\s+", wire.instructions.strip())
            self.assertEqual(len(sentences), 10, key.value)
            self.assertTrue(all(sentence.endswith("?") for sentence in sentences[3:8]), key.value)
            for criterion in (question.when_true, question.when_false):
                self.assertEqual(len(re.split(r"(?<=\.)\s+", criterion.strip())), 3, key.value)
            self.assertTrue(question.gap.strip())


class JevSwarmPlanReaderTests(unittest.TestCase):
    def test_a_valid_plan_gets_ids_in_plan_order(self) -> None:
        plan = JevSwarmPlanReader.read(_plan("users", "orders", "billing"), limit=4)
        self.assertEqual([assignment.id for assignment in plan.assignments], ["A1", "A2", "A3"])
        self.assertEqual(plan.assignments[1].inputs, "src/api/orders.py")

    def test_malformed_plans_raise_errors_the_main_agent_can_act_on(self) -> None:
        missing = _plan("users", "orders")
        del missing["assignments"][1]["verification"]
        cases = {
            "from 2 through 4": _plan("users"),
            "received 5": _plan("a", "b", "c", "d", "e"),
            "must be a list": {"conventions": "x", "assignments": "users"},
            "must be an object": {"conventions": "x", "assignments": [_assignment("users"), "orders"]},
            "verification": missing,
            "conventions must be non-blank": {"conventions": " ", "assignments": [_assignment("a"), _assignment("b")]},
            "different name": _plan("users", "Users"),
        }
        for expected, arguments in cases.items():
            with self.subTest(expected=expected), self.assertRaisesRegex(ConfigurationError, expected):
                JevSwarmPlanReader.read(arguments, limit=4)


class JevSwarmLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, agent: JevAgent, recognition: ScriptedJev, plan_check: ScriptedJev, replies: list[object]) -> AsyncMock:
        helper_run = AsyncMock(side_effect=replies)
        payload = JevRunBriefAppendPayload.model_validate({"notes": []})
        assert agent.compute is not None
        with (
            patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=payload))),
            patch(_RECOGNIZER, new=_recognizer_helper(recognition)),
            patch(_PLAN_CHECK, new=_plan_helper(plan_check)),
            patch.object(JevSwarmAgent, "arun", new=helper_run),
        ):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "done")
        return helper_run

    async def test_a_swarm_selection_offers_the_tool_and_a_passing_plan_launches_every_helper(self) -> None:
        runner = RecordingRunner(_plan("users", "orders", "billing"))
        agent = _agent(runner)
        replies = [SimpleNamespace(content=f"findings for {name}") for name in ("users", "orders", "billing")]
        plan_check = RoundsJev()
        helper_run = await self._run(agent, _swarm_jev(), plan_check, replies)

        self.assertNotIn(TOOL, runner.tool_names(2))
        self.assertIn(TOOL, runner.tool_names(3))
        self.assertIn("call the launch_swarm tool once", runner.sent(3))
        self.assertEqual(len(plan_check.requests), 1)
        self.assertEqual(len(plan_check.requests[0].questions), 12)
        self.assertEqual(helper_run.await_count, 3)
        first = helper_run.await_args_list[0].args[0]
        self.assertIn("Audit users for SQL injection.", first.prompt)
        self.assertIn("Report findings as `path:line - issue`.", first.prompt)
        self.assertEqual([item.content for item in first.context_items][0], REQUEST)

        swarm = agent.response.swarm
        assert swarm is not None
        self.assertEqual(swarm.attempts, 1)
        self.assertEqual(swarm.iteration, 3)
        self.assertEqual([output.content for output in swarm.outputs], ["findings for users", "findings for orders", "findings for billing"])
        self.assertIn("A3: billing (completed)", runner.sent())
        self.assertIn("findings for billing", runner.sent())

    async def test_a_rejected_plan_returns_its_gaps_and_a_corrected_plan_launches(self) -> None:
        runner = RecordingRunner(_plan("users", "orders"), _plan("users", "orders"))
        agent = _agent(runner)
        rejection = {f"{JevSwarmPlanQuestionKey.DISJOINT.value}.A2": 0.1}
        helper_run = await self._run(agent, _swarm_jev(), RoundsJev(rejection, {}), [SimpleNamespace(content="a"), SimpleNamespace(content="b")])
        rejected = runner.sent(4)
        self.assertIn("A2 (orders): This assignment overlaps another assignment.", rejected)
        self.assertIn("You can submit 2 more plan(s)", rejected)
        self.assertEqual(helper_run.await_count, 2)
        assert agent.response.swarm is not None
        self.assertEqual(agent.response.swarm.attempts, 2)

    async def test_the_last_rejected_plan_closes_the_tool(self) -> None:
        runner = RecordingRunner(_plan("users"), _plan("users"), _plan("users"), _plan("users", "orders"))
        agent = _agent(runner)
        helper_run = await self._run(agent, _swarm_jev(), RoundsJev(), [])
        self.assertIn("from 2 through 4 assignments; received 1", runner.sent(4))
        self.assertEqual(runner.sent(5).count("no longer available"), 0)
        self.assertEqual(runner.sent(6).count("no longer available"), 1)
        self.assertEqual(runner.sent(7).count("no longer available"), 2)
        helper_run.assert_not_awaited()
        self.assertIsNone(agent.response.swarm)

    async def test_a_failed_helper_is_reported_and_an_unavailable_check_passes_the_plan(self) -> None:
        runner = RecordingRunner(_plan("users", "orders"))
        agent = _agent(runner)
        plan_check = RoundsJev(error=VidbyteSdkError("jev down"))
        await self._run(agent, _swarm_jev(), plan_check, [VidbyteSdkError("provider down"), SimpleNamespace(content="kept")])
        swarm = agent.response.swarm
        assert swarm is not None
        self.assertEqual([output.completed for output in swarm.outputs], [False, True])
        self.assertEqual(swarm.outputs[0].content, "")
        self.assertIn("A1: users (failed)", runner.sent())

    async def test_another_selection_offers_no_launch_tool(self) -> None:
        runner = RecordingRunner()
        agent = _agent(runner)
        helper_run = await self._run(agent, ScriptedJev(default=0.9), RoundsJev(), [])
        self.assertIs(agent.response.compute_decisions[0].option, JevDynamicComputeOption.FRESH_AGENT)
        self.assertTrue(all(TOOL not in runner.tool_names(index) for index in range(len(runner.calls))))
        helper_run.assert_not_awaited()
        self.assertIsNone(agent.response.swarm)


if __name__ == "__main__":
    unittest.main()
