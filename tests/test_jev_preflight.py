"""FILE: tests/test_jev_preflight.py

PURPOSE: Verifies JevAgent's clarity preflight deterministically without live model calls.
ROLE IN CODEBASE: Covers the question dataclasses, the JevPresets flags, the JevPreflight registry (get, validate, combine, run), the settings boundary, and JevRuntime's short-circuit and fail-open behavior.
ARCHITECTURE NOTE: Scripted decision and generative runners replace only the external boundaries while production settings, registry, and runtime wiring stay active.
COMMON MODIFICATION PATTERNS: Add a case for every new preset, question, threshold boundary, and availability policy.
KNOWN EDGE CASES: The TypeSafe credential is cleared explicitly and no test may contact TypeSafe or a generative provider.
RELATED DOCS: docs/design/jev-preflight-clarity.md, skills/jev-agent/SKILL.md, and skills/asking-jev-questions/SKILL.md.
TESTS: python -m unittest tests.test_jev_preflight and python scripts/test-jev-preflight.py.
"""

from __future__ import annotations

import os
import re
import unittest
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent, JevAgentSettings, JevPreflightPreset, JevPresetResult, JevResponse
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_CLARITY_THRESHOLD, JEV_PREFLIGHT_REQUEST_FIELD
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevPreflightQuestion
from vidbyte.lib.enums import JevPreflightQuestionKey, JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev import JevPreflight, JevPresets
from vidbyte.lib.jev.preflight import CLARITY_QUESTIONS
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse

_RUNNER_PATH = "vidbyte.lib.jev.preflight.preflight.DecisionModelRunner"
_SENTENCE_END = re.compile(r"[.?]'?(?=\s+[A-Z]|$)")
_CLARITY_KEYS = tuple(key for key in JevPreflightQuestionKey if key.value.startswith("clarity."))


class ScriptedGenerativeRunner:
    """Small runner that records whether the ordinary agent loop was entered."""

    def __init__(self, text: str = "completed") -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})
        self.calls: list[str] = []

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        self.calls.append(prompt)
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
                sentences = len(_SENTENCE_END.findall(question.instructions))
                self.assertIn(sentences, (4, 5))
                self.assertIn(f"`{JEV_PREFLIGHT_REQUEST_FIELD}`", question.instructions)
                self.assertTrue(question.instructions.endswith("?"))
                self.assertTrue(question.clarification.endswith("?"))

    def test_questions_become_noul_questions_with_true_and_false_criteria(self) -> None:
        for question in CLARITY_QUESTIONS:
            built = question.to_question()
            self.assertEqual(built.name, question.key.value)
            self.assertIs(built.question_type, JevQuestionType.NOUL)
            self.assertEqual(built.option_names(), ("true", "false"))

    def test_question_rejects_blank_text(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevPreflightQuestion(key=JevPreflightQuestionKey.CLARITY_GOAL, instructions=" ", when_true="yes", when_false="no", clarification="What?")


class JevPresetsTests(unittest.TestCase):
    """Pin the user-enableable flags and the policy each one turns on."""

    def test_clarity_flag_asks_every_clarity_question_at_the_named_threshold(self) -> None:
        self.assertEqual(JevPresets.available(), (JevPreflightPreset.CLARITY,))
        definition = JevPresets.definition(JevPreflightPreset.CLARITY)
        self.assertEqual(definition.question_keys, _CLARITY_KEYS)
        self.assertEqual(definition.threshold, JEV_CLARITY_THRESHOLD)

    def test_normalize_accepts_strings_and_rejects_bad_flags(self) -> None:
        self.assertEqual(JevPresets.normalize(["clarity"]), (JevPreflightPreset.CLARITY,))
        for bad in ("clarity", ("clarity", "clarity"), ("unknown",), 5):
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                JevPresets.normalize(bad)  # type: ignore[arg-type]


class JevPreflightRegistryTests(unittest.TestCase):
    """Pin get, validate, and combine on the central preflight class."""

    def test_get_resolves_enum_and_string_keys(self) -> None:
        self.assertIs(JevPreflight.get(JevPreflightQuestionKey.CLARITY_SCOPE), JevPreflight.get("clarity.scope"))
        with self.assertRaises(ConfigurationError):
            JevPreflight.get("clarity.missing")

    def test_validate_normalizes_flags_for_settings(self) -> None:
        self.assertEqual(JevPreflight.validate(("clarity",)), (JevPreflightPreset.CLARITY,))
        self.assertEqual(_settings(preflight=("clarity",)).preflight, (JevPreflightPreset.CLARITY,))
        with self.assertRaises(ConfigurationError):
            _settings(preflight=("clarity", JevPreflightPreset.CLARITY))

    def test_combine_orders_questions_for_one_request(self) -> None:
        combined = JevPreflight.combine((JevPreflightPreset.CLARITY,))
        self.assertEqual(tuple(question.name for question in combined), tuple(key.value for key in _CLARITY_KEYS))
        self.assertEqual(JevPreflight.combine(()), ())

    def test_records_live_in_lib_with_the_requested_response_fields(self) -> None:
        self.assertEqual(tuple(item.name for item in fields(JevResponse)), ("input", "output", "results", "needs_clarification", "usage"))
        result = JevPresetResult(score=0.5, answers={})
        with self.assertRaises(TypeError):
            result.answers[JevPreflightQuestionKey.CLARITY_GOAL] = _answer("clarity.goal", 0.5)  # type: ignore[index]


class JevPreflightRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify one-call classification, scoring, short-circuiting, and fail-open behavior through JevAgent."""

    def _agent(self, generative: ScriptedGenerativeRunner, **overrides: Any) -> JevAgent:
        overrides.setdefault("decision", DecisionModelConfig(api_key="test-key"))
        return bind_test_runner(JevAgent(_settings(**overrides)), generative)

    async def test_unclear_request_returns_weakest_clarification_without_main_loop(self) -> None:
        decision = ScriptedDecisionRunner({"clarity.goal": 0.1, **{key.value: 0.5 for key in _CLARITY_KEYS[1:]}})
        generative = ScriptedGenerativeRunner()
        with patch(_RUNNER_PATH, return_value=decision):
            reply = await self._agent(generative).arun("Build it")

        self.assertEqual(reply.content, "What would you like me to do, and what should I do it to?")
        self.assertEqual(generative.calls, [])
        self.assertEqual(len(decision.requests), 1)
        self.assertEqual(dict(decision.requests[0].state), {JEV_PREFLIGHT_REQUEST_FIELD: "Build it"})
        self.assertEqual(len(decision.requests[0].questions), len(_CLARITY_KEYS))
        response = reply.metadata["jev_response"]
        self.assertTrue(response.needs_clarification)
        self.assertAlmostEqual(response.results[JevPreflightPreset.CLARITY].score, (0.1 + 0.5 * (len(_CLARITY_KEYS) - 1)) / len(_CLARITY_KEYS))
        self.assertEqual((response.usage.input_tokens, response.usage.output_tokens), (120, 18))

    async def test_threshold_score_continues_into_main_loop(self) -> None:
        decision = ScriptedDecisionRunner({key.value: JEV_CLARITY_THRESHOLD for key in _CLARITY_KEYS})
        generative = ScriptedGenerativeRunner("ordinary answer")
        with patch(_RUNNER_PATH, return_value=decision):
            reply = await self._agent(generative).arun("Summarize the attached report in five bullets.")

        self.assertEqual(reply.content, "ordinary answer")
        self.assertEqual(len(generative.calls), 1)
        response = reply.metadata["jev_response"]
        self.assertFalse(response.needs_clarification)
        self.assertEqual(response.output, "ordinary answer")
        self.assertAlmostEqual(response.results[JevPreflightPreset.CLARITY].score, JEV_CLARITY_THRESHOLD)

    async def test_missing_decision_credentials_fail_open(self) -> None:
        generative = ScriptedGenerativeRunner("available answer")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            reply = await self._agent(generative, decision=DecisionModelConfig()).arun("Do the requested work.")

        self.assertEqual(reply.content, "available answer")
        response = reply.metadata["jev_response"]
        self.assertFalse(response.needs_clarification)
        self.assertFalse(response.results[JevPreflightPreset.CLARITY].available)

    async def test_missing_answer_fails_open(self) -> None:
        decision = ScriptedDecisionRunner({}, omit="clarity.scope")
        generative = ScriptedGenerativeRunner("fallback answer")
        with patch(_RUNNER_PATH, return_value=decision):
            reply = await self._agent(generative).arun("Rename the userId field to user_id.")

        self.assertEqual(reply.content, "fallback answer")
        self.assertFalse(reply.metadata["jev_response"].results[JevPreflightPreset.CLARITY].available)

    async def test_disabled_preflight_makes_no_decision_call(self) -> None:
        generative = ScriptedGenerativeRunner("plain answer")
        with patch(_RUNNER_PATH) as runner_class:
            reply = await self._agent(generative, preflight=()).arun("question")

        runner_class.assert_not_called()
        self.assertEqual(reply.metadata["jev_response"].results, {})


if __name__ == "__main__":
    unittest.main()
