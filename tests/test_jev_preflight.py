"""FILE: tests/test_jev_preflight.py

PURPOSE: Verifies JevAgent's preflight gate and clarity preset deterministically without live model calls.
ROLE IN CODEBASE: Covers the question dataclasses and their brief and criterion layout, the JevPresets flags, the JevPreflightRegistry, DecisionModelRunner.score_noul, the JevPreflightGate (combine and pass_), JevClarificationAgent and its structured reply, the JevResponse record on JevAgent.response, and JevRuntime's stop and fail-open behavior.
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
    JevClarification,
    JevPreflightPreset,
    tool,
)
from vidbyte.agents.jev.gate import JevClarificationAgent, JevPreflightGate
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import (
    JEV_CLARIFICATION_MAX_ITERATIONS,
    JEV_CLARIFICATION_MAX_TOKENS,
    JEV_CLARITY_THRESHOLD,
    JEV_PREFLIGHT_REQUEST_FIELD,
    JEV_PREFLIGHT_STRATEGY_NAME,
)
from vidbyte.lib.dataclasses.jev import (
    JevAnswer,
    JevBrief,
    JevClarificationPayload,
    JevCriterion,
    JevDecisionRequest,
    JevPreflightQuestion,
)
from vidbyte.lib.enums import JevPreflightQuestionKey, JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError
from vidbyte.lib.jev import JevPreflightRegistry, JevPresets
from vidbyte.lib.jev.preflight import CLARITY_QUESTIONS
from vidbyte.lib.jev.preflight.clarity import IGNORE_CLAIMS, REQUEST_STATE
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse

_RUNNER_PATH = "vidbyte.agents.jev.gate.gate.DecisionModelRunner"
_TOOL_SELECTOR_RUNNER_PATH = "vidbyte.agents.jev.preflight.DecisionModelRunner"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SENTENCE_END = re.compile(r"[.?]'?(?=\s+[A-Z`]|$)")
# A quoted example inside prose: a quote that is not an apostrophe inside a word.
_QUOTED = re.compile(r"(?<![A-Za-z])['\"][^'\"]+['\"](?![A-Za-z])")
_CLARITY_KEYS = tuple(key for key in JevPreflightQuestionKey if key.value.startswith("clarity."))
_PAYLOAD = {
    "questions": [
        {"question": "What should I build?", "recommendations": ["A login page", "A signup form"]},
        {"question": "Which project is it for?", "recommendations": ["The web app", "The mobile app", "The admin console"]},
    ]
}
_RENDERED = "1. What should I build?\n   - A login page\n   - A signup form\n2. Which project is it for?\n   - The web app\n   - The mobile app\n   - The admin console"


class ScriptedGenerativeRunner:
    """Small runner that records every prompt and system prompt it receives, or raises when told to."""

    def __init__(self, text: str = "completed", *, error: Exception | None = None) -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})
        self.error = error
        self.calls: list[str] = []
        self.systems: list[str] = []

    def run(self, prompt: str, system: str = "", **kwargs: Any) -> TextModelResponse:
        self.calls.append(prompt)
        self.systems.append(system)
        if self.error is not None:
            raise self.error
        return self.response


class ScriptedDecisionRunner:
    """Records every decision request and returns fixed P(yes) values per question name."""

    def __init__(self, probabilities: Mapping[str, float], *, omit: str | None = None) -> None:
        self.probabilities = probabilities
        self.omit = omit
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        answers = {question.name: _answer(question.name, self.probabilities.get(question.name, 0.9)) for question in request.questions if question.name != self.omit}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model="jev-1.13.0", answers=answers, raw={}, usage={"input_tokens": 120, "output_tokens": 18})


def _runner_class(scripted: ScriptedDecisionRunner) -> type:
    # Stands in for DecisionModelRunner: construction returns the scripted runner, while score_noul stays real.
    class ScriptedRunnerClass:
        score_noul = staticmethod(DecisionModelRunner.score_noul)

        def __new__(cls, *args: Any, **kwargs: Any) -> ScriptedDecisionRunner:  # type: ignore[misc]
            return scripted

    return ScriptedRunnerClass


def _answer(name: str, yes: float) -> JevAnswer:
    return JevAnswer(question_name=name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {"name": "jev", "system_prompt": "Work carefully.", "provider": "openai", "model_name": "gpt-4.1-mini", "preflight": (JevPreflightPreset.CLARITY,)}
    values.update(overrides)
    return JevAgentSettings(**values)


def _sentences(text: str) -> int:
    return len(_SENTENCE_END.findall(text))


def _unclear() -> dict[str, float]:
    # The object check is the weakest, the target check also fails, and every other check is middling.
    return {"clarity.object": 0.1, "clarity.target": 0.3, **{key.value: 0.6 for key in _CLARITY_KEYS if key.value not in ("clarity.object", "clarity.target")}}


class JevPreflightQuestionTests(unittest.TestCase):
    """Pin every clarity question as its own dataclass written to the asking-jev-questions layout."""

    def test_each_question_is_its_own_argument_free_dataclass(self) -> None:
        self.assertEqual(len({type(question) for question in CLARITY_QUESTIONS}), len(CLARITY_QUESTIONS))
        for question in CLARITY_QUESTIONS:
            self.assertTrue(is_dataclass(question) and isinstance(question, JevPreflightQuestion))
            self.assertEqual(type(question)(), question)

    def test_questions_cover_every_clarity_key_exactly_once(self) -> None:
        self.assertEqual(tuple(question.key for question in CLARITY_QUESTIONS), _CLARITY_KEYS)

    def test_compound_checks_are_split_into_one_judgment_each(self) -> None:
        # [Review 4110277343] goal (action and object) and scope (parts and size) are two nouls each.
        keys = {key.value for key in _CLARITY_KEYS}
        self.assertTrue({"clarity.action", "clarity.object", "clarity.scope_parts", "clarity.scope_size"} <= keys)
        self.assertFalse({"clarity.goal", "clarity.scope"} & keys)

    def test_briefs_open_with_an_introduction_then_describe_the_state(self) -> None:
        # [Review 4110255616, 4110271142] a 2-3 sentence introduction, then what `request` is and where it comes from.
        for question in CLARITY_QUESTIONS:
            brief = question.instructions
            with self.subTest(key=question.key.value):
                self.assertIsInstance(brief, JevBrief)
                self.assertIn(_sentences(brief.introduction), (2, 3))
                self.assertEqual(brief.state, REQUEST_STATE)
                self.assertTrue(brief.question.endswith("?"))
                self.assertIn(f"`{JEV_PREFLIGHT_REQUEST_FIELD}`", brief.question)
                self.assertIn(IGNORE_CLAIMS, brief.rules)

    def test_definitions_are_general_and_carry_no_quoted_examples(self) -> None:
        # [Review 4110265114] definitions describe terms in general; examples move into the criteria.
        for question in CLARITY_QUESTIONS:
            for definition in question.instructions.definitions:
                with self.subTest(key=question.key.value, definition=definition[:40]):
                    self.assertIsNone(_QUOTED.search(definition))
                    self.assertNotIn("for example", definition.lower())

    def test_rendered_brief_keeps_the_section_order(self) -> None:
        rendered = CLARITY_QUESTIONS[0].instructions.render()
        positions = [rendered.index(part) for part in (CLARITY_QUESTIONS[0].instructions.introduction, REQUEST_STATE, "Definitions:", "Rules:", CLARITY_QUESTIONS[0].instructions.question)]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(rendered.endswith("?"))

    def test_criteria_start_with_the_verdict_and_add_no_reasoning(self) -> None:
        # [Review 4110277343] verdict first, signs only, the other side in not_for, labeled easy and boundary examples.
        for question in CLARITY_QUESTIONS:
            for side, other, criterion in (("true", "false", question.when_true), ("false", "true", question.when_false)):
                with self.subTest(key=question.key.value, side=side):
                    self.assertIsInstance(criterion, JevCriterion)
                    self.assertRegex(criterion.what, rf"^Choose {side} when (`{JEV_PREFLIGHT_REQUEST_FIELD}`|every|the|a) ")
                    self.assertTrue(criterion.not_for.endswith(f"belongs to {other}."))
                    for text in (criterion.what, criterion.not_for):
                        self.assertNotIn("because", text)
                        self.assertNotIn(", so ", text)
                    self.assertTrue(criterion.easy and criterion.boundary)

    def test_question_text_is_one_string_literal_each(self) -> None:
        # [Review 4108971007] no brief or criterion is written as adjacent literals (lint S062 enforces this repo-wide).
        scanner = ImplicitConcatenationScanner()
        rel = "vidbyte/lib/jev/preflight/clarity.py"
        text = (_REPOSITORY_ROOT / rel).read_text(encoding="utf-8")
        self.assertEqual(scanner.scan(SourceFile(path=_REPOSITORY_ROOT / rel, rel=rel, text=text, tree=ast.parse(text))), [])

    def test_each_question_names_the_gap_its_no_answer_leaves(self) -> None:
        # [Review 4110277343] the gap makes sense on its own to the clarification agent, which never sees the brief.
        for question in CLARITY_QUESTIONS:
            with self.subTest(key=question.key.value):
                self.assertEqual(_sentences(question.gap), 1)
                self.assertTrue(question.gap.endswith("."))
                self.assertNotIn("`", question.gap)

    def test_questions_become_noul_questions_with_structured_criteria(self) -> None:
        for question in CLARITY_QUESTIONS:
            built = question.to_question()
            self.assertEqual(built.name, question.key.value)
            self.assertIs(built.question_type, JevQuestionType.NOUL)
            self.assertEqual(built.instructions, question.instructions.render())
            self.assertEqual(built.option_names(), ("true", "false"))
            for option in built.options:
                self.assertEqual(set(option.description), {"what", "not_for", "examples"})
                self.assertEqual(set(option.description["examples"]), {"easy", "boundary"})

    def test_question_parts_reject_blank_or_wrong_values(self) -> None:
        brief = CLARITY_QUESTIONS[0].instructions
        criterion = CLARITY_QUESTIONS[0].when_true
        with self.assertRaises(ConfigurationError):
            JevBrief(introduction="Intro.", state="State.", definitions=(), rules=("Rule.",), question="Q?")
        with self.assertRaises(ConfigurationError):
            JevCriterion(what="Choose true.", not_for="Other.", easy=(" ",), boundary=("B.",))
        with self.assertRaises(ConfigurationError):
            JevPreflightQuestion(key=JevPreflightQuestionKey.CLARITY_ACTION, instructions="text", when_true=criterion, when_false=criterion, gap="Missing.")  # type: ignore[arg-type]
        with self.assertRaises(ConfigurationError):
            JevPreflightQuestion(key=JevPreflightQuestionKey.CLARITY_ACTION, instructions=brief, when_true=criterion, when_false=criterion, gap=" ")


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
        self.assertIs(JevPreflightRegistry.get(JevPreflightQuestionKey.CLARITY_SCOPE_PARTS), JevPreflightRegistry.get("clarity.scope_parts"))
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


class DecisionModelRunnerScoreTests(unittest.TestCase):
    """Pin the noul scoring that turns a set of answers into a yes or no against a threshold."""

    # [Review 4110233707] scoring against the threshold lives on DecisionModelRunner.

    def test_mean_probability_is_compared_to_the_threshold(self) -> None:
        answers = {"a": _answer("a", 0.9), "b": _answer("b", 0.6)}
        verdict = DecisionModelRunner.score_noul(answers, ("a", "b"), 0.75)
        assert verdict is not None
        self.assertAlmostEqual(verdict.score, 0.75)
        self.assertTrue(verdict.passed)
        self.assertEqual(tuple(verdict.answers), ("a", "b"))
        failing = DecisionModelRunner.score_noul(answers, ("a", "b"), 0.76)
        assert failing is not None
        self.assertFalse(failing.passed)

    def test_missing_or_non_noul_answers_make_no_verdict(self) -> None:
        choice = JevAnswer(question_name="b", question_type=JevQuestionType.CHOICE, choice="x", probabilities={"x": 1.0}, confidence=1.0)
        self.assertIsNone(DecisionModelRunner.score_noul({"a": _answer("a", 0.9)}, ("a", "b"), 0.5))
        self.assertIsNone(DecisionModelRunner.score_noul({"a": _answer("a", 0.9), "b": choice}, ("a", "b"), 0.5))
        self.assertIsNone(DecisionModelRunner.score_noul(None, ("a",), 0.5))
        self.assertIsNone(DecisionModelRunner.score_noul({}, (), 0.5))


class JevPreflightGateTests(unittest.TestCase):
    """Pin the gate's construction and its one combined Jev request."""

    def test_gate_is_built_once_in_the_agent_constructor(self) -> None:
        # [Review 4108937660] every preset and preflight input is fixed when JevAgent is built.
        agent = JevAgent(_settings())
        self.assertIsInstance(agent.preflight, JevPreflightGate)
        self.assertEqual(agent.preflight.presets, (JevPreflightPreset.CLARITY,))
        self.assertIsInstance(agent.preflight.clarification, JevClarificationAgent)
        self.assertIsNone(JevAgent(_settings(preflight=())).preflight.clarification)

    def test_gate_holds_no_tool_selector_logic(self) -> None:
        # [Review 4110242769, 4110245164] the tool selector keeps its own path; the gate only runs fixed-question presets.
        gate = JevAgent(_settings(preflight=("clarity", "tool_selector"))).preflight
        self.assertEqual(gate.presets, (JevPreflightPreset.CLARITY,))
        self.assertFalse(hasattr(gate, "tools"))
        self.assertIsNone(JevAgent(_settings(preflight=("tool_selector",))).preflight.combine("Hello."))

    def test_combine_puts_every_enabled_preset_into_one_request(self) -> None:
        request = JevAgent(_settings()).preflight.combine("Find the notes.")
        assert request is not None
        self.assertEqual(dict(request.state), {JEV_PREFLIGHT_REQUEST_FIELD: "Find the notes."})
        self.assertEqual(tuple(question.name for question in request.questions), tuple(key.value for key in _CLARITY_KEYS))

    def test_combine_asks_nothing_when_no_preset_is_enabled(self) -> None:
        self.assertIsNone(JevAgent(_settings(preflight=())).preflight.combine("Hello."))


class JevClarificationAgentTests(unittest.TestCase):
    """Pin the clarification agent's fixed limits, schema, and context."""

    def test_agent_uses_the_requested_limits_and_structured_output(self) -> None:
        # [Review 4110223154] max tokens 100,000, max iterations 25, and questions with a few recommendations each.
        agent = JevAgent(_settings()).preflight.clarification
        assert agent is not None
        self.assertEqual(agent.runtime_config.max_iterations, JEV_CLARIFICATION_MAX_ITERATIONS)
        self.assertEqual(JEV_CLARIFICATION_MAX_ITERATIONS, 25)
        self.assertEqual(agent.runtime_config.max_tokens, JEV_CLARIFICATION_MAX_TOKENS)
        self.assertEqual(JEV_CLARIFICATION_MAX_TOKENS, 100_000)
        self.assertIs(agent.output_schema, JevClarificationPayload)

    def test_missing_checks_are_passed_through_a_context_manager(self) -> None:
        # [Review 4109941324] the message is built with vidbyte.context, not json.dumps.
        gaps = (JevPreflightQuestionKey.CLARITY_OBJECT, JevPreflightQuestionKey.CLARITY_TARGET)
        items = JevClarificationAgent.context(gaps).items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Missing from the request")
        self.assertEqual(items[0].content, "\n".join(f"- {JevPreflightRegistry.get(key).gap}" for key in gaps))

    def test_clarification_renders_numbered_questions_with_recommendations(self) -> None:
        clarification = JevClarification.from_payload(JevClarificationPayload.model_validate(_PAYLOAD), (JevPreflightQuestionKey.CLARITY_OBJECT,))
        self.assertEqual(clarification.render(), _RENDERED)
        self.assertEqual(clarification.questions[1].recommendations, ("The web app", "The mobile app", "The admin console"))

    def test_payload_requires_a_few_recommendations_per_question(self) -> None:
        for bad in ({"questions": []}, {"questions": [{"question": "Which one?", "recommendations": ["Only one"]}]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                JevClarificationPayload.model_validate(bad)


class JevPreflightRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify one-call classification, the clarification route, and fail-open behavior through JevAgent."""

    def _agent(self, generative: ScriptedGenerativeRunner, clarifier: ScriptedGenerativeRunner | None = None, **overrides: Any) -> JevAgent:
        overrides.setdefault("decision", DecisionModelConfig(api_key="test-key"))
        agent = bind_test_runner(JevAgent(_settings(**overrides)), generative)
        if agent.preflight.clarification is not None:
            bind_test_runner(agent.preflight.clarification, clarifier or ScriptedGenerativeRunner(json.dumps(_PAYLOAD)))
        return agent

    async def test_unclear_request_is_routed_to_the_clarification_agent_and_stops(self) -> None:
        # [Review 4109005129] an unclear request returns the clarification agent's questions and never runs the main agent.
        decision = ScriptedDecisionRunner(_unclear())
        generative = ScriptedGenerativeRunner()
        clarifier = ScriptedGenerativeRunner(json.dumps(_PAYLOAD))
        agent = self._agent(generative, clarifier)
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            reply = await agent.arun("Build it")

        self.assertEqual(reply.content, _RENDERED)
        self.assertIsInstance(reply.structured, JevClarification)
        self.assertEqual(reply.metadata["strategy"], JEV_PREFLIGHT_STRATEGY_NAME)
        self.assertEqual(generative.calls, [])
        self.assertEqual(len(decision.requests), 1)
        self.assertEqual(len(decision.requests[0].questions), len(_CLARITY_KEYS))
        self.assertEqual(clarifier.calls[0], "Build it")
        for key in ("clarity.object", "clarity.target"):
            self.assertIn(JevPreflightRegistry.get(key).gap, clarifier.systems[0])
        response = agent.response
        self.assertTrue(response.needs_clarification)
        self.assertEqual(response.output, _RENDERED)
        self.assertEqual(response.clarification.gaps, (JevPreflightQuestionKey.CLARITY_OBJECT, JevPreflightQuestionKey.CLARITY_TARGET))
        self.assertEqual(response.clarification.questions[0].recommendations, ("A login page", "A signup form"))
        result = response.results[JevPreflightPreset.CLARITY]
        self.assertFalse(result.passed)
        self.assertAlmostEqual(result.score, (0.1 + 0.3 + 0.6 * (len(_CLARITY_KEYS) - 2)) / len(_CLARITY_KEYS))
        self.assertEqual((response.usage.input_tokens, response.usage.output_tokens), (120, 18))

    async def test_feature_data_is_on_the_agent_response_not_in_metadata(self) -> None:
        # [PR #445 review 4108892263] opinionated feature data lives on JevAgent.response.
        with patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner(_unclear()))):
            agent = self._agent(ScriptedGenerativeRunner())
            reply = await agent.arun("Build it")

        self.assertIsInstance(agent.response, JevAgentResponse)
        self.assertFalse(any(key.startswith("jev") for key in reply.metadata))

    async def test_weakest_check_is_sent_when_no_check_falls_below_one_half(self) -> None:
        decision = ScriptedDecisionRunner({**{key.value: 0.7 for key in _CLARITY_KEYS}, "clarity.scope_size": 0.55})
        clarifier = ScriptedGenerativeRunner(json.dumps(_PAYLOAD))
        agent = self._agent(ScriptedGenerativeRunner(), clarifier)
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            await agent.arun("Improve the docs.")

        self.assertIn(JevPreflightRegistry.get("clarity.scope_size").gap, clarifier.systems[0])
        self.assertNotIn(JevPreflightRegistry.get("clarity.scope_parts").gap, clarifier.systems[0])
        self.assertEqual(agent.response.clarification.gaps, (JevPreflightQuestionKey.CLARITY_SCOPE_SIZE,))

    async def test_threshold_score_continues_into_main_loop(self) -> None:
        decision = ScriptedDecisionRunner({key.value: JEV_CLARITY_THRESHOLD for key in _CLARITY_KEYS})
        generative = ScriptedGenerativeRunner("ordinary answer")
        clarifier = ScriptedGenerativeRunner(json.dumps(_PAYLOAD))
        agent = self._agent(generative, clarifier)
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
            reply = await agent.arun("Summarize the attached report in five bullets.")

        self.assertEqual(reply.content, "ordinary answer")
        self.assertEqual(len(generative.calls), 1)
        self.assertEqual(clarifier.calls, [])
        self.assertFalse(agent.response.needs_clarification)
        self.assertEqual(agent.response.output, "ordinary answer")
        self.assertTrue(agent.response.results[JevPreflightPreset.CLARITY].passed)
        self.assertAlmostEqual(agent.response.results[JevPreflightPreset.CLARITY].score, JEV_CLARITY_THRESHOLD)

    async def test_clarification_agent_failure_fails_open(self) -> None:
        for clarifier in (ScriptedGenerativeRunner(error=ProviderRequestError("down", provider="openai")), ScriptedGenerativeRunner("not json")):
            generative = ScriptedGenerativeRunner("fallback answer")
            agent = self._agent(generative, clarifier)
            with self.subTest(clarifier=clarifier.response.text), patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner(_unclear()))):
                reply = await agent.arun("Build it")
                self.assertEqual(reply.content, "fallback answer")
                self.assertFalse(agent.response.needs_clarification)
                self.assertFalse(agent.response.results[JevPreflightPreset.CLARITY].passed)

    async def test_clarification_agent_sees_only_the_current_request(self) -> None:
        clarifier = ScriptedGenerativeRunner(json.dumps(_PAYLOAD))
        agent = self._agent(ScriptedGenerativeRunner(), clarifier)
        with patch(_RUNNER_PATH, new=_runner_class(ScriptedDecisionRunner(_unclear()))):
            await agent.arun("Build it")
            await agent.arun("Fix that")

        self.assertEqual(len(agent.preflight.clarification.history), 1)
        self.assertEqual(clarifier.calls[1], "Fix that")
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
        decision = ScriptedDecisionRunner(_unclear(), omit="clarity.scope_parts")
        generative = ScriptedGenerativeRunner("fallback answer")
        agent = self._agent(generative)
        with patch(_RUNNER_PATH, new=_runner_class(decision)):
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

    async def test_tool_selector_keeps_its_own_path_after_the_gate(self) -> None:
        # [Review 4110245164] the gate asks only clarity questions; the tool selector runs as it does on main.
        @tool
        def keep(query: str) -> str:
            """Search relevant records."""
            return query

        @tool
        def hide(query: str) -> str:
            """Search unrelated records."""
            return query

        gate_decision = ScriptedDecisionRunner({})
        selector_decision = ScriptedDecisionRunner({"tool_selector.0": 0.9, "tool_selector.1": 0.05})
        agent = self._agent(ScriptedGenerativeRunner("done"), preflight=("clarity", "tool_selector"), tools=(keep, hide))
        with patch(_RUNNER_PATH, new=_runner_class(gate_decision)), patch(_TOOL_SELECTOR_RUNNER_PATH, return_value=selector_decision):
            reply = await agent.arun("Search the relevant records for the March invoice.")

        self.assertEqual(tuple(question.name for question in gate_decision.requests[0].questions), tuple(key.value for key in _CLARITY_KEYS))
        self.assertEqual(len(selector_decision.requests), 1)
        self.assertEqual(tuple(agent.response.results), (JevPreflightPreset.CLARITY,))
        self.assertEqual(reply.metadata["jev_tool_selector"]["selected_tool_count"], 1)


if __name__ == "__main__":
    unittest.main()
