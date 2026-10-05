"""FILE: tests/test_jev_compute_situations.py

PURPOSE: Verifies mid-run compute situation recognition without network calls: the fixed sign questions and their house-style shape, each situation's policy and registry, the code-side state builders, the recognizer's scoring, and the checkpoint that runs it after a verified brief refresh.
ROLE IN CODEBASE: Covers vidbyte/lib/jev/compute/, vidbyte/agents/jev/compute/states.py and recognizer.py, the recognition step of JevComputeController, and JevComputeSettings.situations.
ARCHITECTURE NOTE: A scripted stand-in replaces DecisionModelHelper's request while its real scoring stays in use; the brief writer's model is patched; the loop, states, recognizer, and records run for real.
COMMON MODIFICATION PATTERNS: Add a case when a situation gains a sign, a precondition changes, or the scoring policy changes.
KNOWN EDGE CASES: A situation the brief cannot show asks Jev nothing; an unavailable answer never passes; the gate must pass on its own.
RELATED DOCS: docs/design/jev-compute-situations.md.
TESTS: python -m pytest tests/test_jev_compute_situations.py.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from lint.core.discovery import SourceFile
from lint.rules.s062_no_implicit_string_concatenation import ImplicitConcatenationScanner
from tests.agent_test_support import bind_test_runner
from vidbyte import tool
from vidbyte.agents.jev import JevAgent, JevAgentSettings, JevComputeSettings, JevRuntimeSettings
from vidbyte.agents.jev.brief import JevRunBriefEvents
from vidbyte.agents.jev.compute.recognizer import JevComputeRecognizer
from vidbyte.agents.jev.compute.states import JevComputeStates
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_COMPUTE_EACH_OF_SEVERAL_THRESHOLD,
    JEV_COMPUTE_EACH_OF_SEVERAL_VETO,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevComputeDecision,
    JevComputeQuestion,
    JevComputeSituationResult,
    JevDecisionRequest,
    JevRunBrief,
    JevRunBriefApproach,
    JevRunBriefItem,
    JevRunBriefPayload,
    JevRunBriefQuote,
)
from vidbyte.lib.enums import JevComputeQuestionKey, JevComputeSituation, JevQuestionType, JevRunBriefItemStatus, JevRunBriefOutcome, ModelProvider
from vidbyte.lib.errors import ConfigurationError, VidbyteSdkError
from vidbyte.lib.jev.compute import JevComputeRegistry, JevComputeSituations
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.types import DecisionModelResponse

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_HELPER = "vidbyte.agents.jev.compute.recognizer.DecisionModelHelper"
REQUEST = "Audit each file under src/api for SQL injection."
Q = JevRunBriefQuote


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


class ScriptedJev:
    """Answers every question of each request from P(yes) values keyed by question name, with a default for the rest."""

    def __init__(self, yes: Mapping[str, float] | None = None, *, default: float = 0.9, error: Exception | None = None, missing: tuple[str, ...] = ()) -> None:
        self.yes = dict(yes or {})
        self.default = default
        self.error = error
        self.missing = missing
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        answers = {question.name: _answer(question.name, self.yes.get(question.name, self.default)) for question in request.questions if question.name not in self.missing}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 200, "output_tokens": 12})


def _helper(scripted: ScriptedJev) -> type:
    # Stands in for DecisionModelHelper: construction returns the scripted runner, while score_noul stays real.
    class ScriptedHelper:
        score_noul = staticmethod(DecisionModelHelper.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedJev:  # type: ignore[misc]
            return scripted

    return ScriptedHelper


def _brief(**overrides: Any) -> JevRunBrief:
    values: dict[str, Any] = {
        "goal": "Audit the API files",
        "iteration": 3,
        "through_event": 6,
        "next_steps": (Q("E4", "I will audit each of these files"),),
        "items": (
            JevRunBriefItem("a_py", "src/api/a.py", "src/api files", JevRunBriefItemStatus.PENDING, (Q("E3", "a.py"),)),
            JevRunBriefItem("b_py", "src/api/b.py", "src/api files", JevRunBriefItemStatus.PENDING, (Q("E3", "b.py"),)),
            JevRunBriefItem("notes", "NOTES.md", "docs", JevRunBriefItemStatus.PENDING, (Q("E3", "NOTES.md"),)),
        ),
    }
    values.update(overrides)
    return JevRunBrief(**values)


def _events() -> JevRunBriefEvents:
    return JevRunBriefEvents.from_run(REQUEST, ["I will list the files.", "I will audit each of these files: a.py, b.py."], [])


class JevComputeQuestionTests(unittest.TestCase):
    def test_every_situation_lists_registered_questions_with_a_gate_among_them(self) -> None:
        listed = [key for situation in JevComputeSituation for key in JevComputeSituations.definition(situation).question_keys]
        self.assertEqual(sorted(listed), sorted(JevComputeQuestionKey))
        for situation in JevComputeSituation:
            definition = JevComputeSituations.definition(situation)
            self.assertIn(definition.gate, definition.question_keys)
            for key in definition.question_keys:
                self.assertTrue(key.value.startswith(f"{situation.value}."))
                self.assertIsInstance(JevComputeRegistry.get(key), JevComputeQuestion)

    def test_each_question_is_a_noul_question_about_fields_its_state_describes(self) -> None:
        for key in JevComputeQuestionKey:
            question = JevComputeRegistry.get(key)
            with self.subTest(key=key.value):
                rendered = question.to_question()
                self.assertEqual((rendered.name, rendered.question_type), (key.value, JevQuestionType.NOUL))
                self.assertEqual([option.name for option in rendered.options], ["true", "false"])
                self.assertTrue(question.when_true.what.startswith("Choose true when"))
                self.assertTrue(question.when_false.what.startswith("Choose false when"))
                fields = set(re.findall(r"`([a-z_]+)`", question.instructions.question))
                self.assertTrue(fields)
                for name in fields:
                    self.assertIn(f"`{name}`", question.instructions.state)

    @unittest.skipUnless(importlib.util.find_spec("tiktoken"), "tiktoken is not installed")
    def test_each_question_carries_at_least_five_hundred_tokens(self) -> None:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        for key in JevComputeQuestionKey:
            question = JevComputeRegistry.get(key)
            parts = [question.instructions.render()]
            for criterion in (question.when_true, question.when_false):
                parts += [criterion.what, criterion.not_for, *criterion.easy, *criterion.boundary]
            with self.subTest(key=key.value):
                self.assertGreaterEqual(len(encoding.encode("\n".join(parts))), 500)

    def test_question_text_is_one_string_literal_each(self) -> None:
        scanner = ImplicitConcatenationScanner()
        for module in ("state", "repeating", "each_of_several", "self_contained_step"):
            rel = f"vidbyte/lib/jev/compute/{module}.py"
            text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(module=module):
                self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])


class JevComputeSettingsSituationTests(unittest.TestCase):
    def test_situations_default_to_all_and_normalize_into_priority_order(self) -> None:
        self.assertEqual(JevComputeSettings().situations, tuple(JevComputeSituation))
        normalized = JevComputeSettings(situations=("self_contained_step", JevComputeSituation.REPEATING, "repeating")).situations
        self.assertEqual(normalized, (JevComputeSituation.REPEATING, JevComputeSituation.SELF_CONTAINED_STEP))
        self.assertEqual(JevComputeSettings(situations=()).situations, ())

    def test_unknown_situations_and_strings_are_refused(self) -> None:
        for value in (("nope",), "repeating"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                JevComputeSettings(situations=value)  # type: ignore[arg-type]


class JevComputeStatesTests(unittest.TestCase):
    def test_each_of_several_picks_the_group_with_the_most_pending_items(self) -> None:
        state = JevComputeStates.build(JevComputeSituation.EACH_OF_SEVERAL, REQUEST, _brief(current_step=Q("E5", "Starting with a.py")), _events())
        assert state is not None
        group = state["group"]
        self.assertEqual(group["name"], "src/api files")  # type: ignore[index]
        self.assertEqual([item["name"] for item in group["items"]], ["src/api/a.py", "src/api/b.py"])  # type: ignore[index]
        self.assertEqual(state["plan"], ("E5: Starting with a.py", "E4: I will audit each of these files"))
        self.assertIn("E3 ASSISTANT", state["recent"])  # type: ignore[operator]
        self.assertEqual(state["request"], REQUEST)

    def test_each_of_several_needs_enough_pending_items_in_one_group(self) -> None:
        done = JevRunBriefItem("a_py", "src/api/a.py", "src/api files", JevRunBriefItemStatus.DONE, (Q("E3", "a.py"),))
        pending = JevRunBriefItem("b_py", "src/api/b.py", "src/api files", JevRunBriefItemStatus.PENDING, (Q("E3", "b.py"),))
        self.assertIsNone(JevComputeStates.build(JevComputeSituation.EACH_OF_SEVERAL, REQUEST, _brief(items=(done, pending)), _events()))
        self.assertIsNone(JevComputeStates.build(JevComputeSituation.EACH_OF_SEVERAL, REQUEST, _brief(items=()), _events()))

    def test_repeating_picks_a_failed_problem_no_approach_has_solved(self) -> None:
        def approach(identifier: str, target: str, outcome: JevRunBriefOutcome) -> JevRunBriefApproach:
            return JevRunBriefApproach(identifier, target, f"tried {identifier}", outcome, (Q("E3", "a.py"),))

        solved = (approach("first", "import error", JevRunBriefOutcome.FAILED), approach("second", "import error", JevRunBriefOutcome.WORKED))
        self.assertIsNone(JevComputeStates.build(JevComputeSituation.REPEATING, REQUEST, _brief(approaches=solved), _events()))
        stuck = (approach("reinstall", "test failure", JevRunBriefOutcome.FAILED), approach("rerun", "test failure", JevRunBriefOutcome.UNRESOLVED))
        state = JevComputeStates.build(JevComputeSituation.REPEATING, REQUEST, _brief(approaches=stuck, open_failures=(Q("E3", "a.py"),)), _events())
        assert state is not None
        self.assertEqual(state["problem"], "test failure")
        self.assertEqual([attempt["outcome"] for attempt in state["attempts"]], ["failed", "unresolved"])  # type: ignore[union-attr]
        self.assertEqual(state["failures"], ("E3: a.py",))

    def test_self_contained_step_needs_a_stated_next_step(self) -> None:
        state = JevComputeStates.build(JevComputeSituation.SELF_CONTAINED_STEP, REQUEST, _brief(), _events())
        assert state is not None
        self.assertEqual(state["next_step"], "E4: I will audit each of these files")
        self.assertEqual(json.loads(state["brief"])["goal"], "Audit the API files")  # type: ignore[arg-type]
        self.assertIsNone(JevComputeStates.build(JevComputeSituation.SELF_CONTAINED_STEP, REQUEST, _brief(next_steps=()), _events()))


class JevComputeRecognizerTests(unittest.IsolatedAsyncioTestCase):
    async def _recognize(self, scripted: ScriptedJev, brief: JevRunBrief | None = None, situations: tuple[JevComputeSituation, ...] = tuple(JevComputeSituation)) -> JevComputeDecision:
        recognizer = JevComputeRecognizer(DecisionModelConfig(api_key="typesafe-key"), situations)
        with patch(_HELPER, new=_helper(scripted)):
            return await recognizer.recognize(3, REQUEST, brief or _brief(), _events())

    async def test_asks_only_eligible_situations_and_chooses_the_first_that_passes(self) -> None:
        scripted = ScriptedJev(default=0.9)
        decision = await self._recognize(scripted)
        by_situation = {result.situation: result for result in decision.results}
        self.assertFalse(by_situation[JevComputeSituation.REPEATING].eligible)
        self.assertTrue(by_situation[JevComputeSituation.EACH_OF_SEVERAL].passed)
        self.assertTrue(by_situation[JevComputeSituation.SELF_CONTAINED_STEP].passed)
        self.assertIs(decision.situation, JevComputeSituation.EACH_OF_SEVERAL)
        self.assertEqual(len(scripted.requests), 2)
        self.assertEqual({question.name for question in scripted.requests[0].questions}, {key.value for key in JevComputeSituations.definition(JevComputeSituation.EACH_OF_SEVERAL).question_keys})
        self.assertEqual(by_situation[JevComputeSituation.EACH_OF_SEVERAL].usage.input_tokens, 200)  # type: ignore[union-attr]

    async def test_one_clear_no_vetoes_a_strong_mean(self) -> None:
        veto = JEV_COMPUTE_EACH_OF_SEVERAL_VETO - 0.05
        decision = await self._recognize(ScriptedJev({JevComputeQuestionKey.EACH_OF_SEVERAL_INDEPENDENT.value: veto}, default=0.99), situations=(JevComputeSituation.EACH_OF_SEVERAL,))
        self.assertFalse(decision.results[0].passed)
        self.assertIsNone(decision.situation)

    async def test_the_gate_must_pass_on_its_own(self) -> None:
        gate = JevComputeQuestionKey.EACH_OF_SEVERAL_SAME_WORK.value
        below = await self._recognize(ScriptedJev({gate: JEV_COMPUTE_EACH_OF_SEVERAL_THRESHOLD - 0.01}, default=1.0), situations=(JevComputeSituation.EACH_OF_SEVERAL,))
        at = await self._recognize(ScriptedJev({gate: JEV_COMPUTE_EACH_OF_SEVERAL_THRESHOLD}, default=1.0), situations=(JevComputeSituation.EACH_OF_SEVERAL,))
        self.assertGreater(below.results[0].score or 0.0, JEV_COMPUTE_EACH_OF_SEVERAL_THRESHOLD)
        self.assertFalse(below.results[0].passed)
        self.assertTrue(at.results[0].passed)

    async def test_an_outage_or_a_missing_answer_recognizes_nothing(self) -> None:
        outage = await self._recognize(ScriptedJev(error=VidbyteSdkError("down")))
        missing = await self._recognize(ScriptedJev(missing=(JevComputeQuestionKey.SELF_CONTAINED_STEP_REQUESTED.value,)), situations=(JevComputeSituation.SELF_CONTAINED_STEP,))
        self.assertIsNone(outage.situation)
        self.assertTrue(all(not result.passed for result in outage.results))
        self.assertFalse(missing.results[0].available)

    def test_records_refuse_a_pass_jev_never_made_and_a_wrong_choice(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevComputeSituationResult(JevComputeSituation.REPEATING, available=False, passed=True)
        passed = JevComputeSituationResult(JevComputeSituation.EACH_OF_SEVERAL, score=0.9, passed=True)
        with self.assertRaises(ConfigurationError):
            JevComputeDecision(iteration=1, results=(passed,), situation=None)


@tool
def lookup(topic: str) -> str:
    """Look up one topic and return what was found about it."""
    return f"found:{topic}"


class ScriptedRunner:
    """Minimal synchronous generative runner that returns scripted model responses in order."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)

    def run(self, prompt: str, **kwargs: Any) -> object:
        return self.responses.pop(0)


def _call(name: str, arguments: dict[str, Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(text="", raw={"output": [{"type": "function_call", "name": name, "arguments": json.dumps(arguments), "call_id": call_id}]})


class JevComputeCheckpointRecognitionTests(unittest.IsolatedAsyncioTestCase):
    def _agent(self, situations: tuple[JevComputeSituation, ...] = tuple(JevComputeSituation)) -> JevAgent:
        settings = JevAgentSettings(name="researcher", system_prompt="Research.", provider="openai", model_name="gpt-4.1", api_key="main-key", tools=(lookup,))
        runtime = JevRuntimeSettings(decision=DecisionModelConfig(api_key="typesafe-key"), compute=JevComputeSettings(situations=situations))
        runner = ScriptedRunner(*(_call("lookup", {"topic": topic}, f"c{index}") for index, topic in enumerate(("a", "b", "c", "d"))), _call("isDone", {"final_answer": "done"}, "end"))
        return bind_test_runner(JevAgent(settings, runtime), runner)

    def _payload(self) -> JevRunBriefPayload:
        return JevRunBriefPayload.model_validate({
            "goal": "Look up each topic", "goal_evidence": [], "current_step": None,
            "next_steps": [{"event": "E1", "quote": "Audit each file under src/api"}],
            "items": [], "approaches": [], "open_failures": [],
        })

    async def test_recognition_runs_after_a_verified_refresh_and_is_reported(self) -> None:
        agent = self._agent()
        scripted = ScriptedJev(default=0.9)
        assert agent.compute is not None
        with patch.object(agent.compute.keeper.writer, "arun", new=AsyncMock(return_value=SimpleNamespace(structured=self._payload()))), patch(_HELPER, new=_helper(scripted)):
            reply = await agent.arun(REQUEST)
        self.assertEqual(reply.content, "done")
        decisions = agent.response.compute_decisions
        self.assertEqual([(decision.iteration, decision.situation) for decision in decisions], [(3, JevComputeSituation.SELF_CONTAINED_STEP)])
        self.assertEqual(len(scripted.requests), 1)

    async def test_no_recognition_without_a_verified_refresh_or_without_situations(self) -> None:
        for situations, writer in ((tuple(JevComputeSituation), AsyncMock(side_effect=VidbyteSdkError("down"))), ((), AsyncMock(return_value=SimpleNamespace(structured=self._payload())))):
            agent = self._agent(situations)
            scripted = ScriptedJev()
            assert agent.compute is not None
            with self.subTest(situations=situations), patch.object(agent.compute.keeper.writer, "arun", new=writer), patch(_HELPER, new=_helper(scripted)):
                await agent.arun(REQUEST)
                self.assertEqual(agent.response.compute_decisions, [])
                self.assertEqual(scripted.requests, [])


if __name__ == "__main__":
    unittest.main()
