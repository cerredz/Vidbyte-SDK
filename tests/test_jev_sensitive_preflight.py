"""FILE: tests/test_jev_sensitive_preflight.py

PURPOSE: Verifies JevAgent's sensitive-data preflight and action policy without provider calls.
ROLE IN CODEBASE: Covers fixed questions, public settings, response flags, and block/pause/report outcomes.
ARCHITECTURE NOTE: Scripted decision and generative runners replace only the external model boundaries.
COMMON MODIFICATION PATTERNS: Add behavior coverage for every new security category and action change.
KNOWN EDGE CASES: Unavailable classification fails closed for BLOCK and PAUSE, while REPORT continues with unknown flags.
RELATED DOCS: docs/design/jev-preflight-sensitive-data.md and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_sensitive_preflight.py.
"""

from __future__ import annotations

import re
import unittest
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent, JevAgentSettings, Preset, SecurityAction
from vidbyte.agents.jev.presets import SECURITY_FLAGS, SECURITY_QUESTIONS
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevAnswer
from vidbyte.lib.enums import JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.types import DecisionModelResponse


class ScriptedGenerativeRunner:
    """Records whether the regular agent loop was entered."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, prompt: str, **kwargs: Any) -> TextModelResponse:
        self.calls.append(prompt)
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="completed", raw={})


class ScriptedDecisionRunner:
    """Returns the configured yes/no probabilities for the fixed security questions."""

    def __init__(self, positives: frozenset[str] = frozenset(), *, missing: frozenset[str] = frozenset()) -> None:
        self.positives = positives
        self.missing = missing
        self.requests: list[Any] = []

    async def arun(self, request: Any) -> DecisionModelResponse:
        self.requests.append(request)
        answers = {
            question.name: _answer(question.name, question.name.removeprefix("security.") in self.positives)
            for question in request.questions
            if question.name.removeprefix("security.") not in self.missing
        }
        return DecisionModelResponse(
            provider=ModelProvider.TYPESAFE,
            model="jev-latest",
            answers=answers,
            raw={},
            usage={"input_tokens": 90, "output_tokens": 20},
        )


def _answer(name: str, positive: bool) -> JevAnswer:
    true_probability = 0.9 if positive else 0.1
    false_probability = 1.0 - true_probability
    return JevAnswer(
        question_name=name,
        question_type=JevQuestionType.NOUL,
        choice="true" if positive else "false",
        probabilities={"true": true_probability, "false": false_probability},
        noul=true_probability,
    )


def _settings(action: SecurityAction = SecurityAction.BLOCK, **overrides: Any) -> JevAgentSettings:
    values: dict[str, Any] = {
        "name": "jev",
        "system_prompt": "Work carefully.",
        "provider": "openai",
        "model_name": "gpt-4.1-mini",
        "decision": DecisionModelConfig(api_key="test-key"),
        "preflight": (Preset.Security(on_detected=action),),
    }
    values.update(overrides)
    return JevAgentSettings(**values)


class JevSensitivePreflightDefinitionTests(unittest.TestCase):
    """Pin the public setting and fixed question/flag contract."""

    def test_twenty_positive_questions_have_three_sentence_instructions(self) -> None:
        self.assertEqual(len(SECURITY_QUESTIONS), 20)
        self.assertEqual(tuple(question.name.removeprefix("security.") for question in SECURITY_QUESTIONS), SECURITY_FLAGS)
        self.assertTrue(all(question.question_type is JevQuestionType.NOUL for question in SECURITY_QUESTIONS))
        self.assertTrue(all(question.option_names() == ("true", "false") for question in SECURITY_QUESTIONS))
        self.assertTrue(all(len(re.split(r"(?<=[.!?])\s+", question.instructions)) == 3 for question in SECURITY_QUESTIONS))

    def test_settings_normalize_action_and_reject_unknown_or_duplicate_presets(self) -> None:
        self.assertEqual(_settings("pause").preflight[0].on_detected, SecurityAction.PAUSE)
        with self.assertRaises(ConfigurationError):
            _settings("unknown")
        with self.assertRaises(ConfigurationError):
            _settings(preflight=(Preset.Security(), Preset.Security()))


class JevSensitivePreflightRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify each action, positive flags, incomplete answers, and provider failures."""

    async def _run(self, action: SecurityAction, *, positives: frozenset[str] = frozenset(), failure: Exception | None = None, missing: frozenset[str] = frozenset()) -> tuple[Any, ScriptedGenerativeRunner, ScriptedDecisionRunner | None]:
        generated = ScriptedGenerativeRunner()
        agent = bind_test_runner(JevAgent(_settings(action)), generated)
        decision_runner = None if failure is not None else ScriptedDecisionRunner(positives, missing=missing)
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", side_effect=failure, return_value=decision_runner):
            reply = await agent.arun("Please review this input.")
        return reply, generated, decision_runner

    async def test_block_stops_and_names_only_detected_categories(self) -> None:
        reply, generated, decision = await self._run(SecurityAction.BLOCK, positives=frozenset({"api_service_secrets", "health"}))
        self.assertEqual(generated.calls, [])
        self.assertIn("api service secrets", reply.content)
        self.assertIn("health", reply.content)
        self.assertNotIn("test-key", reply.content)
        result = reply.metadata["jev_response"].results["security"]
        self.assertTrue(result.flags["api_service_secrets"])
        self.assertFalse(result.flags["passwords_pins"])
        self.assertTrue(result.any_sensitive)
        self.assertTrue(result.available)
        self.assertEqual(len(decision.requests[0].questions), 20)
        self.assertNotIn("Please review", repr(reply.metadata["jev_response"]))

    async def test_pause_returns_review_state_without_entering_model_loop(self) -> None:
        reply, generated, _ = await self._run(SecurityAction.PAUSE, positives=frozenset({"personal_contact"}))
        self.assertEqual(generated.calls, [])
        self.assertIn("Review is required", reply.content)
        self.assertEqual(reply.metadata["stop_reason"], "sensitive_data_review_required")

    async def test_report_continues_and_attaches_flags(self) -> None:
        reply, generated, _ = await self._run(SecurityAction.REPORT, positives=frozenset({"internal_business"}))
        self.assertEqual(reply.content, "completed")
        self.assertEqual(generated.calls, ["Please review this input."])
        result = reply.metadata["jev_response"].results["security"]
        self.assertTrue(result.flags["internal_business"])
        self.assertTrue(result.any_sensitive)

    async def test_clear_request_continues_under_block_policy(self) -> None:
        reply, generated, _ = await self._run(SecurityAction.BLOCK)
        self.assertEqual(reply.content, "completed")
        self.assertEqual(len(generated.calls), 1)
        result = reply.metadata["jev_response"].results["security"]
        self.assertFalse(result.any_sensitive)
        self.assertTrue(result.available)

    async def test_incomplete_answers_are_unknown_and_block_fails_closed(self) -> None:
        reply, generated, _ = await self._run(SecurityAction.BLOCK, missing=frozenset({"health"}))
        self.assertEqual(generated.calls, [])
        result = reply.metadata["jev_response"].results["security"]
        self.assertIsNone(result.flags["health"])
        self.assertIsNone(result.any_sensitive)
        self.assertFalse(result.available)

    async def test_provider_failure_blocks_or_reports_and_continues(self) -> None:
        block_agent = bind_test_runner(JevAgent(_settings(SecurityAction.BLOCK)), ScriptedGenerativeRunner())
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", side_effect=ConfigurationError("missing key")):
            blocked = await block_agent.arun("input")
        self.assertEqual(blocked.metadata["stop_reason"], "sensitive_data_blocked")
        self.assertIn("could not be checked", blocked.content)

        generated = ScriptedGenerativeRunner()
        report_agent = bind_test_runner(JevAgent(_settings(SecurityAction.REPORT)), generated)
        with patch("vidbyte.agents.jev.runtime.DecisionModelRunner", side_effect=ConfigurationError("missing key")):
            reported = await report_agent.arun("input")
        self.assertEqual(reported.content, "completed")
        self.assertEqual(len(generated.calls), 1)
        result = reported.metadata["jev_response"].results["security"]
        self.assertFalse(result.available)
        self.assertTrue(all(flag is None for flag in result.flags.values()))

    async def test_positive_partial_result_triggers_protection(self) -> None:
        reply, generated, _ = await self._run(
            SecurityAction.BLOCK,
            positives=frozenset({"government_ids"}),
            missing=frozenset({"health"}),
        )
        self.assertEqual(generated.calls, [])
        result = reply.metadata["jev_response"].results["security"]
        self.assertTrue(result.any_sensitive)
        self.assertTrue(result.flags["government_ids"])
        self.assertIsNone(result.flags["health"])


if __name__ == "__main__":
    unittest.main()
