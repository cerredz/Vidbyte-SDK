"""FILE: tests/test_jev_preflight.py

PURPOSE: Verifies JevAgent's clarity preflight deterministically without live model calls.
ROLE IN CODEBASE: Covers the preset definition, settings boundary, single-call classification, runtime actions, response state, and fail-open policy.
ARCHITECTURE NOTE: Scripted decision and generative runners replace only external boundaries while production settings and runtime wiring remain active.
COMMON MODIFICATION PATTERNS: Add a case for every new preset outcome, threshold boundary, and availability policy.
KNOWN EDGE CASES: Environment credentials are cleared explicitly and no test may contact TypeSafe or a generative provider.
RELATED DOCS: docs/design/jev-preflight-clarity.md and skills/jev-agent/SKILL.md.
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
        confidence=max(true_probability, false_probability),
    )


def _settings(**overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {
        "name": "jev",
        "system_prompt": "Work carefully.",
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "preflight": (JevPreflightPreset.CLARITY,),
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

    def test_settings_normalize_and_validate_presets(self) -> None:
        settings = _settings(preflight=("clarity",))
        self.assertEqual(settings.preflight, (JevPreflightPreset.CLARITY,))
        self.assertEqual(JevPreflightRegistry.presets(), (JevPreflightPreset.CLARITY,))
        with self.assertRaises(ConfigurationError):
            _settings(preflight=("clarity", "clarity"))
        with self.assertRaises(ConfigurationError):
            _settings(preflight=("unknown",))

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
        agent = bind_test_runner(JevAgent(_settings(preflight=())), generative_runner)
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner") as decision_runner_class:
            reply = await agent.arun("question")

        decision_runner_class.assert_not_called()
        self.assertEqual(reply.metadata["jev_response"].results, {})


if __name__ == "__main__":
    unittest.main()
