"""FILE: tests/test_jev_preflight.py

PURPOSE: Verifies JevAgent's clarity preflight and caller-written custom questions deterministically without live model calls.
ROLE IN CODEBASE: Covers the preset definition, JevPreflight validation, single-call classification of presets plus custom questions, runtime actions, response state, and fail-open policy.
ARCHITECTURE NOTE: Scripted decision and generative runners replace only external boundaries while production settings and runtime wiring remain active.
COMMON MODIFICATION PATTERNS: Add a case for every new preset outcome, threshold boundary, and availability policy.
KNOWN EDGE CASES: Environment credentials are cleared explicitly and no test may contact TypeSafe or a generative provider.
RELATED DOCS: docs/design/jev-preflight-clarity.md, docs/design/jev-preflight-custom-questions.md, and skills/jev-agent/SKILL.md.
TESTS: python -m unittest tests.test_jev_preflight and python scripts/test-jev-preflight.py.
"""

from __future__ import annotations

import os
import unittest
from collections.abc import Mapping
from dataclasses import fields
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import (
    JevAgent,
    JevAgentSettings,
    JevCustomQuestion,
    JevPreflight,
    JevPreflightPreset,
    JevPreflightRegistry,
    JevResponse,
)
from vidbyte.agents.jev.presets import CLARITY_QUESTIONS
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_MAX_QUESTIONS
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse


class ScriptedGenerativeRunner:
    """Small runner that records whether the ordinary agent loop was entered."""

    def __init__(self, text: str = "completed") -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text=text, raw={})
        self.calls: list[str] = []

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        self.calls.append(prompt)
        return self.response


class ScriptedDecisionRunner:
    """Records the single preflight request and returns fixed probabilities."""

    def __init__(self, probabilities: Mapping[str, float]) -> None:
        self.probabilities = probabilities
        self.requests: list[JevDecisionRequest] = []

    async def arun(self, request: JevDecisionRequest) -> DecisionModelResponse:
        self.requests.append(request)
        answers = {
            question.name: _answer(question.name, self.probabilities.get(question.name, 0.9))
            for question in request.questions
        }
        return DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-latest",
            answers=answers,
            raw={},
            usage={"input_tokens": 120, "output_tokens": 18},
        )


def _answer(name: str, true_probability: float) -> JevAnswer:
    false_probability = 1.0 - true_probability
    return JevAnswer(
        question_name=name,
        question_type=JevQuestionType.NOUL,
        choice="true" if true_probability >= false_probability else "false",
        probabilities={"true": true_probability, "false": false_probability},
        noul=true_probability,
    )


_PII = JevCustomQuestion(name="touches_pii", question="Does the request involve personal or customer data?")
_DESTRUCTIVE = JevCustomQuestion(name="is_destructive", question="Would completing the request delete or overwrite existing data?")


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {
        "name": "jev",
        "system_prompt": "Work carefully.",
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "preflight": JevPreflight(preset=(JevPreflightPreset.CLARITY,)),
    }
    values.update(overrides)
    return JevAgentSettings(**values)


class JevPreflightDefinitionTests(unittest.TestCase):
    """Pin the public setting and the fixed clarity classifier contract."""

    def test_clarity_preset_contains_eighteen_positive_noul_questions(self) -> None:
        self.assertEqual(len(CLARITY_QUESTIONS), 18)
        self.assertEqual(len({question.name for question in CLARITY_QUESTIONS}), 18)
        self.assertTrue(all(question.question_type is JevQuestionType.NOUL for question in CLARITY_QUESTIONS))
        self.assertTrue(all(question.option_names() == ("true", "false") for question in CLARITY_QUESTIONS))
        self.assertGreaterEqual(JEV_MAX_QUESTIONS, len(CLARITY_QUESTIONS))

    def test_preflight_normalizes_and_validates_presets(self) -> None:
        self.assertEqual(JevPreflight(preset=("clarity",)).preset, (JevPreflightPreset.CLARITY,))
        self.assertEqual(JevPreflightRegistry.presets(), (JevPreflightPreset.CLARITY,))
        for invalid in (("clarity", "clarity"), ("unknown",), ("custom",), "clarity"):
            with self.subTest(preset=invalid), self.assertRaises(ConfigurationError):
                JevPreflight(preset=invalid)

    def test_settings_require_a_preflight_object(self) -> None:
        self.assertEqual(_settings().preflight.preset, (JevPreflightPreset.CLARITY,))
        self.assertEqual(JevAgentSettings(name="jev", system_prompt="s", provider="openai", model_name="m").preflight, JevPreflight())
        with self.assertRaises(ConfigurationError):
            _settings(preflight=(JevPreflightPreset.CLARITY,))

    def test_custom_questions_validate_at_construction(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevCustomQuestion(name="", question="Is this valid?")
        with self.assertRaises(ConfigurationError):
            JevCustomQuestion(name="blank", question="  ")
        with self.assertRaises(ConfigurationError):
            JevPreflight(custom=(_PII, JevCustomQuestion(name="touches_pii", question="Another wording?")))
        with self.assertRaises(ConfigurationError):
            JevPreflight(custom=("Is this a question?",))

    def test_custom_questions_become_one_zero_threshold_definition(self) -> None:
        definitions = JevPreflight(preset=(JevPreflightPreset.CLARITY,), custom=(_PII, _DESTRUCTIVE)).definitions()
        self.assertEqual([definition.preset for definition in definitions], [JevPreflightPreset.CLARITY, JevPreflightPreset.CUSTOM])
        custom = definitions[1]
        self.assertEqual(custom.threshold, 0.0)
        self.assertEqual([question.name for question in custom.questions], ["custom.touches_pii", "custom.is_destructive"])
        self.assertTrue(all(question.question_type is JevQuestionType.NOUL for question in custom.questions))

    def test_combined_question_count_is_checked_before_any_run(self) -> None:
        # Main's real cap is 10,000, so a lowered cap keeps the boundary check fast.
        with patch("vidbyte.agents.jev.presets.JEV_MAX_QUESTIONS", len(CLARITY_QUESTIONS) + 2):
            JevPreflight(preset=(JevPreflightPreset.CLARITY,), custom=(_PII, _DESTRUCTIVE))
            with self.assertRaises(ConfigurationError):
                JevPreflight(
                    preset=(JevPreflightPreset.CLARITY,),
                    custom=(_PII, _DESTRUCTIVE, JevCustomQuestion(name="extra", question="Is this one too many?")),
                )

    def test_response_surface_has_only_the_requested_fields(self) -> None:
        self.assertEqual(
            tuple(field.name for field in fields(JevResponse)),
            ("input", "output", "results", "needs_clarification", "usage"),
        )


class JevPreflightRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify one-call classification, scoring, short-circuiting, and fail-open behavior."""

    async def test_unclear_request_returns_focused_clarification_without_main_loop(self) -> None:
        decision_runner = ScriptedDecisionRunner({"clarity.goal": 0.1, **{question.name: 0.5 for question in CLARITY_QUESTIONS[1:]}})
        generative_runner = ScriptedGenerativeRunner()
        agent = bind_test_runner(JevAgent(_settings(decision=DecisionModelConfig(api_key="test-key"))), generative_runner)

        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decision_runner):
            reply = await agent.arun("Build it")

        self.assertEqual(reply.content, "What is the primary goal you want me to accomplish?")
        self.assertEqual(generative_runner.calls, [])
        self.assertEqual(len(decision_runner.requests), 1)
        request = decision_runner.requests[0]
        self.assertEqual(len(request.questions), 18)
        self.assertTrue(request.state.endswith("USER REQUEST:\nBuild it"))
        self.assertEqual(request.state.count(". "), 3)
        response = reply.metadata["jev_response"]
        self.assertTrue(response.needs_clarification)
        self.assertAlmostEqual(response.results["clarity"].score, 0.5 - (0.4 / 18))
        self.assertEqual((response.usage.input_tokens, response.usage.output_tokens), (120, 18))

    async def test_threshold_score_continues_into_main_loop(self) -> None:
        decision_runner = ScriptedDecisionRunner({question.name: 0.75 for question in CLARITY_QUESTIONS})
        generative_runner = ScriptedGenerativeRunner("ordinary answer")
        agent = bind_test_runner(JevAgent(_settings(decision=DecisionModelConfig(api_key="test-key"))), generative_runner)

        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decision_runner):
            reply = await agent.arun("Summarize the attached report in five bullets.")

        self.assertEqual(reply.content, "ordinary answer")
        self.assertEqual(len(generative_runner.calls), 1)
        response = reply.metadata["jev_response"]
        self.assertFalse(response.needs_clarification)
        self.assertEqual(response.output, "ordinary answer")
        self.assertEqual(response.results["clarity"].score, 0.75)

    async def test_missing_decision_credentials_fail_open_with_unavailable_result(self) -> None:
        generative_runner = ScriptedGenerativeRunner("available answer")
        agent = bind_test_runner(JevAgent(_settings()), generative_runner)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            reply = await agent.arun("Do the requested work.")

        self.assertEqual(reply.content, "available answer")
        self.assertFalse(reply.metadata["jev_response"].needs_clarification)
        self.assertFalse(reply.metadata["jev_response"].results["clarity"].available)

    async def test_disabled_preflight_makes_no_decision_call(self) -> None:
        generative_runner = ScriptedGenerativeRunner("plain answer")
        agent = bind_test_runner(JevAgent(_settings(preflight=JevPreflight())), generative_runner)
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner") as decision_runner_class:
            reply = await agent.arun("question")

        decision_runner_class.assert_not_called()
        self.assertEqual(reply.metadata["jev_response"].results, {})

    async def test_presets_and_custom_questions_share_one_request(self) -> None:
        decision_runner = ScriptedDecisionRunner({"custom.touches_pii": 0.8, "custom.is_destructive": 0.1})
        generative_runner = ScriptedGenerativeRunner("ordinary answer")
        settings = _settings(
            preflight=JevPreflight(preset=(JevPreflightPreset.CLARITY,), custom=(_PII, _DESTRUCTIVE)),
            decision=DecisionModelConfig(api_key="test-key"),
        )
        agent = bind_test_runner(JevAgent(settings), generative_runner)

        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decision_runner):
            reply = await agent.arun("Export last month's orders to CSV.")

        self.assertEqual(len(decision_runner.requests), 1)
        names = [question.name for question in decision_runner.requests[0].questions]
        self.assertEqual(len(names), 20)
        self.assertEqual(names[-2:], ["custom.touches_pii", "custom.is_destructive"])
        response = reply.metadata["jev_response"]
        self.assertFalse(response.needs_clarification)
        self.assertEqual(set(response.results), {"clarity", "custom"})
        custom = response.results["custom"]
        self.assertEqual(custom.answers["custom.touches_pii"].noul, 0.8)
        self.assertEqual(custom.answers["custom.is_destructive"].choice, "false")

    async def test_low_custom_answers_never_trigger_clarification(self) -> None:
        decision_runner = ScriptedDecisionRunner({"custom.touches_pii": 0.0, "custom.is_destructive": 0.0})
        generative_runner = ScriptedGenerativeRunner("custom only answer")
        settings = _settings(preflight=JevPreflight(custom=(_PII, _DESTRUCTIVE)), decision=DecisionModelConfig(api_key="test-key"))
        agent = bind_test_runner(JevAgent(settings), generative_runner)

        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decision_runner):
            reply = await agent.arun("Summarize this ticket.")

        self.assertEqual(reply.content, "custom only answer")
        self.assertEqual(len(decision_runner.requests[0].questions), 2)
        response = reply.metadata["jev_response"]
        self.assertFalse(response.needs_clarification)
        self.assertEqual(response.results["custom"].score, 0.0)

    async def test_custom_answers_are_attached_when_clarity_short_circuits(self) -> None:
        decision_runner = ScriptedDecisionRunner({question.name: 0.1 for question in CLARITY_QUESTIONS})
        generative_runner = ScriptedGenerativeRunner()
        settings = _settings(
            preflight=JevPreflight(preset=(JevPreflightPreset.CLARITY,), custom=(_PII,)),
            decision=DecisionModelConfig(api_key="test-key"),
        )
        agent = bind_test_runner(JevAgent(settings), generative_runner)

        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", return_value=decision_runner):
            reply = await agent.arun("Do the thing")

        self.assertEqual(generative_runner.calls, [])
        response = reply.metadata["jev_response"]
        self.assertTrue(response.needs_clarification)
        self.assertEqual(response.results["custom"].answers["custom.touches_pii"].noul, 0.9)

    async def test_unavailable_jev_marks_custom_results_unavailable(self) -> None:
        generative_runner = ScriptedGenerativeRunner("available answer")
        settings = _settings(preflight=JevPreflight(preset=(JevPreflightPreset.CLARITY,), custom=(_PII,)))
        agent = bind_test_runner(JevAgent(settings), generative_runner)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TYPESAFE_API_KEY", None)
            reply = await agent.arun("Do the requested work.")

        self.assertEqual(reply.content, "available answer")
        results = reply.metadata["jev_response"].results
        self.assertFalse(results["clarity"].available)
        self.assertFalse(results["custom"].available)


if __name__ == "__main__":
    unittest.main()
