"""FILE: tests/test_jev_compute_delegate.py

PURPOSE: Verifies the delegate compute move without network calls: which step it hands off, what the helper is told, the message that brings its report back, and the controller's budget, failure, and once-per-step rules.
ROLE IN CODEBASE: Covers vidbyte/agents/jev/compute/delegate.py and the delegate step of JevComputeController.
ARCHITECTURE NOTE: Scripted runners replace the main agent's model, a patched arun replaces the brief writer, a scripted stand-in replaces Jev's request, and helper runs are patched; the loop, controller, budget, and records run for real.
COMMON MODIFICATION PATTERNS: Add a case when the delegated step, the helper's input, or the message the main agent reads changes.
KNOWN EDGE CASES: The helper sees only the request and the step; a step is delegated once per run; a failed helper is charged and adds nothing to the loop.
RELATED DOCS: docs/design/jev-compute-delegate.md.
TESTS: python -m pytest tests/test_jev_compute_delegate.py.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.agent_test_support import bind_test_runner
from vidbyte import tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRunBriefSettings, JevRuntimeSettings
from vidbyte.agents.jev.compute.delegate import JevComputeDelegate
from vidbyte.agents.jev.compute.helpers import JevComputeHelpers
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_COMPUTE_DELEGATE_SOURCE, JEV_COMPUTE_HELPER_REPORT_MAX_CHARS
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevComputeHelperResult,
    JevContinuationEvidence,
    JevDecisionRequest,
    JevRunBrief,
    JevRunBriefPayload,
    JevRunBriefQuote,
)
from vidbyte.lib.enums import JevComputeMoveStatus, JevComputeSituation, JevQuestionType, ModelProvider
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse

REQUEST = "Add rate limiting to our public API."
STEP = "Next I'll find out which rate limiting libraries support Redis-backed counters in Python."
_JEV = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
Q = JevRunBriefQuote


@tool
def search(query: str) -> str:
    """Search the web for the query and return the most relevant results as text."""
    return "results"


def _settings() -> JevAgentSettings:
    return JevAgentSettings(name="builder", system_prompt="Build features.", provider="openai", model_name="gpt-4.1", api_key="main-key", tools=(search,))


def _result(text: str) -> JevComputeHelperResult:
    return JevComputeHelperResult(output=text, evidence=JevContinuationEvidence(source=JEV_COMPUTE_DELEGATE_SOURCE, responses=(text,), tool_calls=()))


class JevComputeDelegateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.helpers = JevComputeHelpers(_settings(), JevComputeSettings())
        self.delegate = JevComputeDelegate(self.helpers)
        self.brief = JevRunBrief(goal="Add rate limiting", iteration=3, through_event=5, next_steps=(Q("E4", STEP), Q("E4", "Then wire it in.")))

    async def test_the_helper_gets_only_the_request_and_the_soonest_step(self) -> None:
        step = self.delegate.subject(self.brief)
        assert step is not None
        with patch.object(self.helpers, "run", new=AsyncMock(return_value=_result("redis-rate-limit and limits both do"))) as run:
            result = await self.delegate.run(REQUEST, step)
        self.assertEqual(result.output, "redis-rate-limit and limits both do")  # type: ignore[union-attr]
        prompt = run.await_args.args[1]
        self.assertIn(f"<request>\n{REQUEST}\n</request>", prompt)
        self.assertIn(f"<step>\n{STEP}\n</step>", prompt)
        self.assertNotIn("Then wire it in.", prompt)
        self.assertNotIn('"goal":', prompt)
        self.assertEqual(run.await_args.kwargs["source"], JEV_COMPUTE_DELEGATE_SOURCE)

    async def test_a_step_is_delegated_once_per_run_whatever_its_outcome(self) -> None:
        step = self.delegate.subject(self.brief)
        assert step is not None
        with patch.object(self.helpers, "run", new=AsyncMock(return_value=None)):
            await self.delegate.run(REQUEST, step)
        self.assertIsNone(self.delegate.subject(self.brief))
        self.delegate.begin()
        self.assertEqual(self.delegate.subject(self.brief), step)

    def test_no_stated_step_gives_no_subject_and_the_report_is_clipped(self) -> None:
        self.assertIsNone(self.delegate.subject(JevRunBrief(goal="g", iteration=1, through_event=2)))
        message = self.delegate.message(Q("E4", STEP), "x" * (JEV_COMPUTE_HELPER_REPORT_MAX_CHARS * 2))
        self.assertIn(f"<step>\n{STEP}\n</step>", message)
        self.assertIn("characters left out", message)


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
    return JevRunBriefPayload.model_validate({
        "goal": "Add rate limiting to the public API",
        "goal_evidence": [{"event": "E1", "quote": REQUEST}],
        "current_step": None,
        "next_steps": [{"event": "E1", "quote": "Add rate limiting to our public API."}],
        "items": [],
        "approaches": [],
        "open_failures": [],
    })


class JevComputeControllerDelegateTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, compute: JevComputeSettings, run: AsyncMock, iterations: int = 4) -> tuple[JevAgent, ScriptedRunner]:
        runner = ScriptedRunner(*(_call("search", {"query": "rate limiting"}, f"c{index}") for index in range(iterations)), _call("isDone", {"final_answer": "rate limiting added"}, "end"))
        agent = bind_test_runner(JevAgent(_settings(), JevRuntimeSettings(decision=DecisionModelConfig(api_key="typesafe-key"), compute=compute)), runner)
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=_payload()))), patch(_JEV, new=_jev()), patch.object(agent.compute.delegate.helpers, "run", new=run):
            await agent.arun(REQUEST)
        return agent, runner

    async def test_a_self_contained_step_goes_to_a_helper_and_its_report_reaches_the_main_agent(self) -> None:
        run = AsyncMock(return_value=_result("Use the limits package with its Redis storage backend."))
        agent, runner = await self._run(JevComputeSettings(situations=(JevComputeSituation.SELF_CONTAINED_STEP,)), run)
        run.assert_awaited_once()
        move = agent.response.compute_moves[0]
        self.assertEqual((move.situation, move.status, move.helpers, move.iteration), (JevComputeSituation.SELF_CONTAINED_STEP, JevComputeMoveStatus.COMPLETED, 1, 3))
        delivered = [message["content"] for message in runner.messages[3] if message.get("role") == "user"]
        self.assertEqual(len(delivered), 1)
        self.assertIn("Use the limits package with its Redis storage backend.", delivered[0])
        self.assertEqual(agent.compute.budget.helpers, 1)

    async def test_a_failed_helper_is_charged_and_adds_nothing_to_the_loop(self) -> None:
        agent, runner = await self._run(JevComputeSettings(situations=(JevComputeSituation.SELF_CONTAINED_STEP,)), AsyncMock(return_value=None))
        self.assertEqual([(move.status, move.helpers) for move in agent.response.compute_moves], [(JevComputeMoveStatus.FAILED, 1)])
        self.assertFalse(any(message.get("role") == "user" for call in runner.messages for message in call))

    async def test_the_same_step_recognized_again_finds_no_work_and_a_blocked_move_starts_no_helper(self) -> None:
        compute = JevComputeSettings(situations=(JevComputeSituation.SELF_CONTAINED_STEP,), cooldown_iterations=0, brief=JevRunBriefSettings(every_iterations=3, min_gap=3))
        run = AsyncMock(return_value=_result("done"))
        agent, _ = await self._run(compute, run, iterations=7)
        self.assertEqual([move.status for move in agent.response.compute_moves], [JevComputeMoveStatus.COMPLETED, JevComputeMoveStatus.NO_WORK])
        run.assert_awaited_once()
        blocked_run = AsyncMock()
        blocked, _ = await self._run(JevComputeSettings(situations=(JevComputeSituation.SELF_CONTAINED_STEP,), max_moves=0), blocked_run)
        blocked_run.assert_not_awaited()
        self.assertEqual([move.status for move in blocked.response.compute_moves], [JevComputeMoveStatus.MOVE_LIMIT])


if __name__ == "__main__":
    unittest.main()
