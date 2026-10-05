"""FILE: tests/test_jev_compute_fan_out.py

PURPOSE: Verifies the fan-out compute move without network calls: which items it hands out, how it runs one helper per item in bounded parallel, the message that brings every report back, and the controller's budget cut, partial failure, and once-per-item rule.
ROLE IN CODEBASE: Covers vidbyte/agents/jev/compute/fan_out.py, the fan-out step of JevComputeController, JevComputeFanOutPlan, combined helper usage, and JevComputeSettings.max_parallel_helpers.
ARCHITECTURE NOTE: Scripted runners replace the main agent's model, a patched arun replaces the brief writer, a scripted stand-in replaces Jev's request, and helper runs are patched; the loop, controller, budget, and records run for real.
COMMON MODIFICATION PATTERNS: Add a case when the items handed out, the parallelism, or the message the main agent reads changes.
KNOWN EDGE CASES: An item is handed out once per run; a failed helper's item goes back to the main agent; items beyond the budget stay with it.
RELATED DOCS: docs/design/jev-compute-fan-out.md.
TESTS: python -m pytest tests/test_jev_compute_fan_out.py.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from vidbyte import tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRunBriefSettings, JevRuntimeSettings
from vidbyte.agents.jev.compute.fan_out import JevComputeFanOut
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_COMPUTE_FAN_OUT_SOURCE
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevComputeFanOutPlan,
    JevComputeFanOutReport,
    JevComputeHelperResult,
    JevContinuationEvidence,
    JevDecisionRequest,
    JevRunBrief,
    JevRunBriefItem,
    JevRunBriefPayload,
    JevRunBriefQuote,
)
from vidbyte.lib.enums import JevComputeMoveStatus, JevComputeSituation, JevQuestionType, JevRunBriefItemStatus, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse

REQUEST = "Audit each file for SQL injection: a.py, b.py, c.py."
_JEV = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
Q = JevRunBriefQuote


@tool
def read_file(path: str) -> str:
    """Read the file at the given path and return its full text content."""
    return "print('hello')"


def _settings() -> JevAgentSettings:
    return JevAgentSettings(name="auditor", system_prompt="Audit code.", provider="openai", model_name="gpt-4.1", api_key="main-key", tools=(read_file,))


def _item(name: str, status: JevRunBriefItemStatus = JevRunBriefItemStatus.PENDING, group: str = "files") -> JevRunBriefItem:
    return JevRunBriefItem(name.replace(".", "_"), name, group, status, (Q("E1", name),))


def _brief(*items: JevRunBriefItem) -> JevRunBrief:
    return JevRunBrief(goal="Audit each file", iteration=3, through_event=5, next_steps=(Q("E1", "Audit each file for SQL injection"),), items=items)


def _result(text: str) -> JevComputeHelperResult:
    return JevComputeHelperResult(output=text, evidence=JevContinuationEvidence(source=JEV_COMPUTE_FAN_OUT_SOURCE, responses=(text,), tool_calls=()))


class JevComputeFanOutSubjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fan_out = JevComputeFanOut(JevComputeHelpers(_settings(), JevComputeSettings()), JevComputeSettings())

    def test_the_subject_is_every_pending_item_of_the_busiest_group(self) -> None:
        brief = _brief(_item("a.py"), _item("b.py"), _item("c.py", JevRunBriefItemStatus.DONE), _item("x.md", group="docs"))
        subject = self.fan_out.subject(brief)
        assert subject is not None
        self.assertEqual((subject.group, [item.name for item in subject.items]), ("files", ["a.py", "b.py"]))
        self.assertEqual([quote.quote for quote in subject.plan], ["Audit each file for SQL injection"])

    def test_items_already_handed_out_are_never_handed_out_again(self) -> None:
        brief = _brief(_item("a.py"), _item("b.py"), _item("c.py"))
        self.fan_out._handed.update({("files", "a.py"), ("files", "b.py")})
        self.assertIsNone(self.fan_out.subject(brief))
        self.fan_out.begin()
        self.assertIsNotNone(self.fan_out.subject(brief))

    def test_a_plan_cut_to_the_budget_leaves_the_rest_to_the_main_agent(self) -> None:
        plan = JevComputeFanOutPlan("files", (_item("a.py"), _item("b.py"), _item("c.py")), (Q("E1", "Audit"),)).first(2)
        self.assertEqual(([item.name for item in plan.items], [item.name for item in plan.left]), (["a.py", "b.py"], ["c.py"]))
        with self.assertRaises(ConfigurationError):
            JevComputeFanOutPlan("files", (), (Q("E1", "Audit"),))


class JevComputeFanOutRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_helper_per_item_runs_in_bounded_parallel_with_its_own_prompt_and_source(self) -> None:
        helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        fan_out = JevComputeFanOut(helpers, JevComputeSettings(max_parallel_helpers=2))
        running, peak, prompts, sources = 0, 0, {}, {}

        async def run(role: str, prompt: str, *, source: str) -> JevComputeHelperResult:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            item = next(name for name in ("a.py", "b.py", "c.py", "d.py") if f"<your_item>\n{name}\n</your_item>" in prompt)
            prompts[item], sources[item] = prompt, source
            return _result(f"{item} is clean")

        brief = _brief(*(_item(name) for name in ("a.py", "b.py", "c.py", "d.py")))
        plan = fan_out.subject(brief)
        assert plan is not None
        with patch.object(helpers, "run", new=run):
            reports = await fan_out.run(REQUEST, brief, plan)
        self.assertEqual([report.item.name for report in reports], ["a.py", "b.py", "c.py", "d.py"])
        self.assertEqual(peak, 2)
        self.assertIn("Audit each file for SQL injection", prompts["a.py"])
        self.assertIn(REQUEST, prompts["a.py"])
        self.assertIn('"goal":"Audit each file"', prompts["a.py"])
        self.assertEqual(sources["c.py"], f"{JEV_COMPUTE_FAN_OUT_SOURCE}:c_py")
        self.assertEqual(fan_out._handed, {("files", name) for name in ("a.py", "b.py", "c.py", "d.py")})

    def test_the_message_names_each_report_the_failed_items_and_the_items_left(self) -> None:
        fan_out = JevComputeFanOut(JevComputeHelpers(_settings(), JevComputeSettings()), JevComputeSettings())
        plan = JevComputeFanOutPlan("files", (_item("a.py"), _item("b.py")), (Q("E1", "Audit"),), left=(_item("c.py"),))
        message = fan_out.message(plan, (JevComputeFanOutReport(_item("a.py"), _result("a.py is clean")), JevComputeFanOutReport(_item("b.py"))))
        self.assertIn("with 2 helper agents", message)
        self.assertIn("### a.py\na.py is clean", message)
        self.assertIn("### b.py\nThe helper for this item failed", message)
        self.assertIn("<items_still_yours>\n- c.py\n</items_still_yours>", message)

    def test_helper_usage_is_combined_without_repricing(self) -> None:
        tracker = UsageTracker()
        empty = tracker.rollup()
        self.assertIsNone(JevComputeHelpers.combined_usage((_result("a"),)))
        combined = JevComputeHelpers.combined_usage((JevComputeHelperResult("a", _result("a").evidence, empty), JevComputeHelperResult("b", _result("b").evidence, empty)))
        self.assertIsNotNone(combined)


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


class ScriptedJev:
    """Answers every question yes with high confidence."""

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        answers: Mapping[str, JevAnswer] = {question.name: _answer(question.name, 0.95) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 50, "output_tokens": 5})


def _jev() -> type:
    scripted = ScriptedJev()

    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedJev:  # type: ignore[misc]
            return scripted

    return ScriptedHelper


class ScriptedRunner:
    """Main-agent runner that returns scripted responses and keeps each call's messages."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.messages: list[tuple[Any, ...]] = []

    def run(self, prompt: str, **kwargs: Any) -> object:
        self.messages.append(tuple(kwargs.get("messages") or ()))
        return self.responses.pop(0)


def _call(name: str, arguments: dict[str, Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(text="", raw={"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


def _payload() -> JevRunBriefPayload:
    item = {"group": "files to audit", "status": "pending"}
    return JevRunBriefPayload.model_validate({
        "goal": "Audit each file for SQL injection",
        "goal_evidence": [],
        "current_step": None,
        "next_steps": [{"event": "E1", "quote": "Audit each file for SQL injection"}],
        "items": [{**item, "id": name.replace(".", "_"), "name": name, "evidence": [{"event": "E1", "quote": name}]} for name in ("a.py", "b.py", "c.py")],
        "approaches": [],
        "open_failures": [],
    })


class JevComputeControllerFanOutTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, compute: JevComputeSettings, run: AsyncMock, iterations: int = 4) -> tuple[JevAgent, ScriptedRunner]:
        runner = ScriptedRunner(*(_call("read_file", {"path": "a.py"}, f"c{index}") for index in range(iterations)), _call("isDone", {"final_answer": "audit done"}, "end"))
        agent = bind_test_runner(JevAgent(_settings(), JevRuntimeSettings(decision=DecisionModelConfig(api_key="typesafe-key"), compute=compute)), runner)
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=_payload()))), patch(_JEV, new=_jev()), patch.object(agent.compute.fan_out.helpers, "run", new=run):
            await agent.arun(REQUEST)
        return agent, runner

    async def test_each_item_goes_to_a_helper_and_every_report_reaches_the_main_agent(self) -> None:
        run = AsyncMock(side_effect=[_result("a.py: clean"), None, _result("c.py: injection on line 4")])
        agent, runner = await self._run(JevComputeSettings(situations=(JevComputeSituation.EACH_OF_SEVERAL,)), run)
        self.assertEqual(run.await_count, 3)
        move = agent.response.compute_moves[0]
        self.assertEqual((move.situation, move.status, move.helpers, move.iteration), (JevComputeSituation.EACH_OF_SEVERAL, JevComputeMoveStatus.COMPLETED, 3, 3))
        delivered = [message for message in runner.messages[3] if message.get("role") == "user"]
        self.assertEqual(len(delivered), 1)
        self.assertIn("c.py: injection on line 4", delivered[0]["content"])
        self.assertIn("### b.py\nThe helper for this item failed", delivered[0]["content"])
        self.assertEqual(agent.compute.budget.helpers, 3)

    async def test_items_beyond_the_helper_budget_stay_with_the_main_agent(self) -> None:
        run = AsyncMock(side_effect=[_result("a.py: clean"), _result("b.py: clean")])
        agent, runner = await self._run(JevComputeSettings(situations=(JevComputeSituation.EACH_OF_SEVERAL,), max_helpers=2), run)
        move = agent.response.compute_moves[0]
        self.assertEqual((move.status, move.helpers), (JevComputeMoveStatus.COMPLETED, 2))
        delivered = next(message["content"] for message in runner.messages[3] if message.get("role") == "user")
        self.assertIn("<items_still_yours>\n- c.py\n</items_still_yours>", delivered)

    async def test_a_budget_too_small_to_split_starts_no_helper(self) -> None:
        run = AsyncMock()
        agent, _ = await self._run(JevComputeSettings(situations=(JevComputeSituation.EACH_OF_SEVERAL,), max_helpers=1), run)
        run.assert_not_awaited()
        self.assertEqual([move.status for move in agent.response.compute_moves], [JevComputeMoveStatus.HELPER_LIMIT])

    async def test_all_helpers_failing_is_charged_and_adds_nothing_to_the_loop(self) -> None:
        agent, runner = await self._run(JevComputeSettings(situations=(JevComputeSituation.EACH_OF_SEVERAL,)), AsyncMock(return_value=None))
        self.assertEqual([(move.status, move.helpers) for move in agent.response.compute_moves], [(JevComputeMoveStatus.FAILED, 3)])
        self.assertFalse(any(message.get("role") == "user" for call in runner.messages for message in call))

    async def test_a_second_recognition_of_the_same_items_finds_no_work(self) -> None:
        compute = JevComputeSettings(situations=(JevComputeSituation.EACH_OF_SEVERAL,), cooldown_iterations=0, brief=JevRunBriefSettings(every_iterations=3, min_gap=3))
        run = AsyncMock(side_effect=[_result("a"), _result("b"), _result("c")])
        agent, _ = await self._run(compute, run, iterations=7)
        self.assertEqual([move.status for move in agent.response.compute_moves], [JevComputeMoveStatus.COMPLETED, JevComputeMoveStatus.NO_WORK])
        self.assertEqual(run.await_count, 3)


if __name__ == "__main__":
    unittest.main()
