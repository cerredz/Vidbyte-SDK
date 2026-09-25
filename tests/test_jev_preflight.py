"""FILE: tests/test_jev_preflight.py

PURPOSE: Verifies JevAgent's preflight gate and clarity preset deterministically without live model calls.
ROLE IN CODEBASE: Covers the question dataclasses, the JevPresets flags, the JevPreflightRegistry, the JevPreflight gate (combine and pass_), JevClarificationAgent, the JevResponse record on JevAgent.response, and JevRuntime's stop and fail-open behavior.
ARCHITECTURE NOTE: Scripted decision and generative runners replace only the external boundaries while production settings, registry, gate, and runtime wiring stay active.
COMMON MODIFICATION PATTERNS: Add a case for every new preset, question, threshold boundary, match case, and availability policy.
KNOWN EDGE CASES: The TypeSafe credential is cleared explicitly and no test may contact TypeSafe or a generative provider.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: python -m unittest tests.test_jev_preflight and python scripts/test-jev-preflight.py.
"""

from __future__ import annotations

import ast
import json
import os
import re
import unittest
from collections.abc import Mapping
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lint.core.discovery import SourceFile
from lint.rules.s062_no_implicit_string_concatenation import (
    ImplicitConcatenationScanner,
)
from tests.agent_test_support import bind_test_runner
from vidbyte import (
    JevAgent,
    JevAgentResponse,
    JevAgentSettings,
    JevPreflightPreset,
    JevPresetResult,
    JevToolSelection,
    tool,
)
from vidbyte.agents.jev.preflight import JevClarificationAgent, JevPreflight
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_CLARITY_THRESHOLD,
    JEV_PREFLIGHT_REQUEST_FIELD,
    JEV_PREFLIGHT_STRATEGY_NAME,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevDecisionRequest,
    JevPreflightQuestion,
    JevPreflightRun,
)
from vidbyte.lib.enums import JevPreflightQuestionKey, JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.jev.preflight import CLARITY_QUESTIONS
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.tools.catalog import Tools

_RUNNER_PATH = "vidbyte.agents.jev.preflight.preflight.DecisionModelRunner"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SENTENCE_END = re.compile(r"[.?]'?(?=\s+[A-Z`]|$)")
_CLARITY_KEYS = tuple(key for key in JevPreflightQuestionKey if key.value.startswith("clarity."))
_QUESTIONS = "1. What should I build?\n2. Which project is it for?"


class ScriptedGenerativeRunner:
    """Small runner that records every prompt it receives, or raises when told to."""

    def __init__(self, text: str = "completed", *, error: Exception | None = None) -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})
        self.error = error
        self.calls: list[str] = []

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response


class ScriptedDecisionRunner:
    """Records the single preflight request and returns fixed P(yes) values per question name."""

    def __init__(self, probabilities: Mapping[str, float], *, omit: str | None = None) -> None:
        self.probabilities = probabilities
        self.omit = omit
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        answers = {question.name: _answer(question.name, self.probabilities.get(question.name, 0.9)) for question in request.questions if question.name != self.omit}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 120, "output_tokens": 18})


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "jev", "system_prompt": "Work carefully.", "provider": "openai", "model_name": "gpt-4.1-mini", "preflight": (JevPreflightPreset.CLARITY,)}
    values.update(overrides)
    return JevAgentSettings(**values)


def _sentences(text: str) -> int:
    return len(_SENTENCE_END.findall(text))


def _unclear() -> dict[str, float]:
    # The goal check is the weakest, the target check also fails, and every other check is middling.
    return {"clarity.goal": 0.1, "clarity.target": 0.3, **{key.value: 0.6 for key in _CLARITY_KEYS if key.value not in ("clarity.goal", "clarity.target")}}


class JevPreflightQuestionTests(unittest.TestCase):
    """Pin every clarity question as its own dataclass written to the asking-jev-questions standard."""

    def test_each_question_is_its_own_argument_free_dataclass(self) -> None:
        self.assertEqual(len({type(question) for question in CLARITY_QUESTIONS}), len(CLARITY_QUESTIONS))
        for question in CLARITY_QUESTIONS:
            self.assertTrue(is_dataclass(question) and isinstance(question, JevPreflightQuestion))
            self.assertEqual(type(question)(), question)

    def test_questions_cover_every_clarity_key_exactly_once(self) -> None:
        self.assertEqual(tuple(question.key for question in CLARITY_QUESTIONS), _CLARITY_KEYS)

    def test_questions_are_four_to_five_sentence_briefs_about_the_request_field(self) -> None:
        for question in CLARITY_QUESTIONS:
            with self.subTest(key=question.key.value):
                self.assertIn(_sentences(question.instructions), (4, 5))
                self.assertIn(f"`{JEV_PREFLIGHT_REQUEST_FIELD}`", question.instructions)
                self.assertTrue(question.instructions.endswith("?"))

    def test_criteria_are_in_depth_briefs_like_the_instructions(self) -> None:
        # [Review 4108972879] each side says what it covers, where it stops, an easy example, and a boundary example.
        for question in CLARITY_QUESTIONS:
            for side, text in (("true", question.when_true), ("false", question.when_false)):
                with self.subTest(key=question.key.value, side=side):
                    self.assertEqual(_sentences(text), 4)
                    self.assertTrue(text.startswith(f"Choose {side} when "))
                    self.assertIn(f"`{JEV_PREFLIGHT_REQUEST_FIELD}`", text)
                    self.assertIn("For example,", text)

    def test_each_question_names_the_gap_its_no_answer_leaves(self) -> None:
        for question in CLARITY_QUESTIONS:
            with self.subTest(key=question.key.value):
                self.assertEqual(_sentences(question.gap), 1)
                self.assertTrue(question.gap.endswith("."))

    def test_question_text_is_one_string_literal_each(self) -> None:
        # [Review 4108971007] no brief or criterion is written as adjacent literals (lint S062 enforces this repo-wide).
        scanner = ImplicitConcatenationScanner()
        for rel in ("vidbyte/lib/jev/preflight/clarity.py", "vidbyte/agents/jev/preflight/tools.py"):
            text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

    def test_questions_become_noul_questions_with_true_and_false_criteria(self) -> None:
        for question in CLARITY_QUESTIONS:
            built = question.to_question()
            self.assertEqual(built.name, question.key.value)
            self.assertIs(built.question_type, JevQuestionType.NOUL)
            self.assertEqual(built.option_names(), ("true", "false"))

    def test_question_rejects_blank_text(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevPreflightQuestion(key=JevPreflightQuestionKey.CLARITY_GOAL, instructions=" ", when_true="yes", when_false="no", gap="Missing.")


class JevPresetsTests(unittest.TestCase):
    """Pin the user-enableable flags and the policy each fixed-question flag turns on."""

    def test_clarity_flag_asks_every_clarity_question_at_the_named_threshold(self) -> None:
        self.assertEqual(JevPresets.available(), (JevPreflightPreset.CLARITY, JevPreflightPreset.TOOL_SELECTOR))
        definition = JevPresets.definition(JevPreflightPreset.CLARITY)
        self.assertEqual(definition.question_keys, _CLARITY_KEYS)
        self.assertEqual(definition.threshold, JEV_CLARITY_THRESHOLD)

    def test_tool_selector_is_a_flag_without_fixed_questions(self) -> None:
        self.assertFalse(JevPresets.has_fixed_questions(JevPreflightPreset.TOOL_SELECTOR))
        with self.assertRaises(ConfigurationError):
            JevPresets.definition(JevPreflightPreset.TOOL_SELECTOR)

    def test_normalize_accepts_strings_and_rejects_bad_flags(self) -> None:
        self.assertEqual(JevPresets.normalize(["clarity", "tool_selector"]), (JevPreflightPreset.CLARITY, JevPreflightPreset.TOOL_SELECTOR))
        for bad in ("clarity", ("clarity", "clarity"), ("unknown",), 5):
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                JevPresets.normalize(bad)  # type: ignore[arg-type]


class JevPreflightRegistryTests(unittest.TestCase):
    """Pin get, questions, and validate on the lib-level question registry."""

    def test_get_resolves_enum_and_string_keys(self) -> None:
        self.assertIs(JevPreflightRegistry.get(JevPreflightQuestionKey.CLARITY_SCOPE), JevPreflightRegistry.get("clarity.scope"))
        with self.assertRaises(ConfigurationError):
            JevPreflightRegistry.get("clarity.missing")

    def test_questions_are_returned_in_preset_order(self) -> None:
        names = tuple(question.name for question in JevPreflightRegistry.questions(JevPreflightPreset.CLARITY))
        self.assertEqual(names, tuple(key.value for key in _CLARITY_KEYS))

    def test_validate_normalizes_flags_for_settings(self) -> None:
        self.assertEqual(JevPreflightRegistry.validate(("clarity",)), (JevPreflightPreset.CLARITY,))
        self.assertEqual(_settings(preflight=("clarity",)).preflight, (JevPreflightPreset.CLARITY,))
        with self.assertRaises(ConfigurationError):
            _settings(preflight=("clarity", JevPreflightPreset.CLARITY))


class JevPreflightGateTests(unittest.TestCase):
    """Pin the gate's construction and its one combined Jev request."""

    def test_gate_is_built_once_in_the_agent_constructor(self) -> None:
        # [Review 4108937660] every preset and preflight input is fixed when JevAgent is built.
        agent = JevAgent(_settings(preflight=("clarity", "tool_selector"), tool_selector_threshold=0.4))
        self.assertIsInstance(agent.preflight, JevPreflight)
        self.assertEqual(agent.preflight.presets, (JevPreflightPreset.CLARITY, JevPreflightPreset.TOOL_SELECTOR))
        self.assertEqual(agent.preflight.tools.threshold, 0.4)
        self.assertIsInstance(agent.preflight.clarification, JevClarificationAgent)
        self.assertIsNone(JevAgent(_settings(preflight=())).preflight.clarification)

    def test_combine_puts_every_enabled_preset_into_one_request(self) -> None:
        @tool
        def search(query: str) -> str:
            """Search documents for a query."""
            return query

        agent = JevAgent(_settings(preflight=("clarity", "tool_selector"), tools=(search,)))
        request = agent.preflight.combine(JevPreflightRun(message="Find the notes.", tools=Tools((search,))))
        assert request is not None
        self.assertEqual(dict(request.state), {JEV_PREFLIGHT_REQUEST_FIELD: "Find the notes."})
        self.assertEqual(tuple(question.name for question in request.questions), (*(key.value for key in _CLARITY_KEYS), "tool_selector.0"))

    def test_combine_asks_nothing_when_no_preset_has_a_question(self) -> None:
        run = JevPreflightRun(message="Hello.", tools=Tools(()))
        self.assertIsNone(JevAgent(_settings(preflight=())).preflight.combine(run))
        self.assertIsNone(JevAgent(_settings(preflight=("tool_selector",))).preflight.combine(run))


class JevPreflightRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify one-call classification, the clarification route, and fail-open behavior through JevAgent."""

    def _agent(self, generative: ScriptedGenerativeRunner, clarifier: ScriptedGenerativeRunner | None = None, **overrides: Any) -> JevAgent:
        overrides.setdefault("decision", DecisionModelConfig(api_key="test-key"))
        agent = bind_test_runner(JevAgent(_settings(**overrides)), generative)
        if agent.preflight.clarification is not None:
            bind_test_runner(agent.preflight.clarification, clarifier or ScriptedGenerativeRunner(_QUESTIONS))
        return agent

    async def test_unclear_request_is_routed_to_the_clarification_agent_and_stops(self) -> None:
        # [Review 4109005129] an unclear request returns the clarification agent's questions and never runs the main agent.
        decision = ScriptedDecisionRunner(_unclear())
        generative = ScriptedGenerativeRunner()
        clarifier = ScriptedGenerativeRunner(_QUESTIONS)
        agent = self._agent(generative, clarifier)
        with patch(_RUNNER_PATH, return_value=decision):
            reply = await agent.arun("Build it")

        self.assertEqual(reply.content, _QUESTIONS)
        self.assertEqual(reply.metadata["strategy"], JEV_PREFLIGHT_STRATEGY_NAME)
        self.assertEqual(generative.calls, [])
        self.assertEqual(len(decision.requests), 1)
        self.assertEqual(len(decision.requests[0].questions), len(_CLARITY_KEYS))
        sent = json.loads(clarifier.calls[0])
        self.assertEqual(sent["request"], "Build it")
        self.assertEqual(sent["missing"], [JevPreflightRegistry.get("clarity.goal").gap, JevPreflightRegistry.get("clarity.target").gap])
        response = agent.response
        self.assertTrue(response.needs_clarification)
        self.assertEqual(response.output, _QUESTIONS)
        self.assertEqual(response.clarification.gaps, (JevPreflightQuestionKey.CLARITY_GOAL, JevPreflightQuestionKey.CLARITY_TARGET))
        result = response.results[JevPreflightPreset.CLARITY]
        self.assertFalse(result.passed)
        self.assertAlmostEqual(result.score, (0.1 + 0.3 + 0.6 * (len(_CLARITY_KEYS) - 2)) / len(_CLARITY_KEYS))
        self.assertEqual((response.usage.input_tokens, response.usage.output_tokens), (120, 18))

    async def test_feature_data_is_on_the_agent_response_not_in_metadata(self) -> None:
        # [PR #445 review 4108892263] opinionated feature data lives on JevAgent.response.
        with patch(_RUNNER_PATH, return_value=ScriptedDecisionRunner(_unclear())):
            agent = self._agent(ScriptedGenerativeRunner())
            reply = await agent.arun("Build it")

        self.assertIsInstance(agent.response, JevAgentResponse)
        self.assertFalse(any(key.startswith("jev") for key in reply.metadata))

    async def test_weakest_check_is_sent_when_no_check_falls_below_one_half(self) -> None:
        decision = ScriptedDecisionRunner({**{key.value: 0.7 for key in _CLARITY_KEYS}, "clarity.scope": 0.55})
        clarifier = ScriptedGenerativeRunner(_QUESTIONS)
        agent = self._agent(ScriptedGenerativeRunner(), clarifier)
        with patch(_RUNNER_PATH, return_value=decision):
            await agent.arun("Improve the docs.")

        self.assertEqual(json.loads(clarifier.calls[0])["missing"], [JevPreflightRegistry.get("clarity.scope").gap])
        self.assertEqual(agent.response.clarification.gaps, (JevPreflightQuestionKey.CLARITY_SCOPE,))

    async def test_threshold_score_continues_into_main_loop(self) -> None:
        decision = ScriptedDecisionRunner({key.value: JEV_CLARITY_THRESHOLD for key in _CLARITY_KEYS})
        generative = ScriptedGenerativeRunner("ordinary answer")
        clarifier = ScriptedGenerativeRunner(_QUESTIONS)
        agent = self._agent(generative, clarifier)
        with patch(_RUNNER_PATH, return_value=decision):
            reply = await agent.arun("Summarize the attached report in five bullets.")

        self.assertEqual(reply.content, "ordinary answer")
        self.assertEqual(len(generative.calls), 1)
        self.assertEqual(clarifier.calls, [])
        self.assertFalse(agent.response.needs_clarification)
        self.assertEqual(agent.response.output, "ordinary answer")
        self.assertTrue(agent.response.results[JevPreflightPreset.CLARITY].passed)
        self.assertAlmostEqual(agent.response.results[JevPreflightPreset.CLARITY].score, JEV_CLARITY_THRESHOLD)

    async def test_clarification_agent_failure_fails_open(self) -> None:
        for clarifier in (ScriptedGenerativeRunner(error=ProviderRequestError("down", provider="openai")), ScriptedGenerativeRunner("   ")):
            generative = ScriptedGenerativeRunner("fallback answer")
            agent = self._agent(generative, clarifier)
            with self.subTest(clarifier=clarifier.response.text), patch(_RUNNER_PATH, return_value=ScriptedDecisionRunner(_unclear())):
                reply = await agent.arun("Build it")
                self.assertEqual(reply.content, "fallback answer")
                self.assertFalse(agent.response.needs_clarification)
                self.assertFalse(agent.response.results[JevPreflightPreset.CLARITY].passed)

    async def test_clarification_agent_sees_only_the_current_request(self) -> None:
        clarifier = ScriptedGenerativeRunner(_QUESTIONS)
        agent = self._agent(ScriptedGenerativeRunner(), clarifier)
        with patch(_RUNNER_PATH, return_value=ScriptedDecisionRunner(_unclear())):
            await agent.arun("Build it")
            await agent.arun("Fix that")

        self.assertEqual(len(agent.preflight.clarification.history), 1)
        self.assertEqual(json.loads(clarifier.calls[1])["request"], "Fix that")
        self.assertEqual(agent.response.input, "Fix that")

    async def test_missing_decision_credentials_fail_open(self) -> None:
        generative = ScriptedGenerativeRunner("available answer")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            agent = self._agent(generative, decision=DecisionModelConfig())
            reply = await agent.arun("Do the requested work.")

        self.assertEqual(reply.content, "available answer")
        self.assertFalse(agent.response.needs_clarification)
        self.assertFalse(agent.response.results[JevPreflightPreset.CLARITY].available)
        self.assertIsNone(agent.response.usage)

    async def test_missing_answer_fails_open(self) -> None:
        decision = ScriptedDecisionRunner(_unclear(), omit="clarity.scope")
        generative = ScriptedGenerativeRunner("fallback answer")
        agent = self._agent(generative)
        with patch(_RUNNER_PATH, return_value=decision):
            reply = await agent.arun("Rename the userId field to user_id.")

        self.assertEqual(reply.content, "fallback answer")
        self.assertFalse(agent.response.results[JevPreflightPreset.CLARITY].available)

    async def test_disabled_preflight_makes_no_decision_call(self) -> None:
        generative = ScriptedGenerativeRunner("plain answer")
        agent = self._agent(generative, preflight=())
        with patch(_RUNNER_PATH) as runner_class:
            reply = await agent.arun("question")

        runner_class.assert_not_called()
        self.assertEqual(reply.content, "plain answer")
        self.assertEqual(agent.response.results, {})

    async def test_clarity_and_tool_selector_share_one_request(self) -> None:
        # [Review 4108989808] every enabled preset is asked in one Jev request, then each case acts on its answers.
        @tool
        def keep(query: str) -> str:
            """Search relevant records."""
            return query

        @tool
        def hide(query: str) -> str:
            """Search unrelated records."""
            return query

        decision = ScriptedDecisionRunner({"tool_selector.0": 0.9, "tool_selector.1": 0.05})
        generative = ScriptedGenerativeRunner("done")
        agent = self._agent(generative, preflight=("clarity", "tool_selector"), tools=(keep, hide))
        with patch(_RUNNER_PATH, return_value=decision):
            await agent.arun("Search the relevant records for the March invoice.")

        self.assertEqual(len(decision.requests), 1)
        self.assertEqual(len(decision.requests[0].questions), len(_CLARITY_KEYS) + 2)
        selection = agent.response.results[JevPreflightPreset.TOOL_SELECTOR]
        self.assertIsInstance(selection, JevToolSelection)
        self.assertEqual(selection.selected, ("keep",))
        self.assertIsInstance(agent.response.results[JevPreflightPreset.CLARITY], JevPresetResult)


if __name__ == "__main__":
    unittest.main()
