"""FILE: tests/test_jev_usage_ledger.py

PURPOSE: Proves a JevAgent run records every generative and decision call, from itself and every agent it spawns, in one priced ledger, reports it on JevAgent.response.usage, and fails closed when any usage cannot be recorded or priced.
ROLE IN CODEBASE: Covers vidbyte/lib/usage_ledger.py, the DecisionModelRunner and BaseAgent.generate_reply hooks, UsageTracker's kind/failure/unaccounted bookkeeping, and JevUsageAccount.
ARCHITECTURE NOTE: Decision calls are faked at TypeSafeProvider.run_decision, below DecisionModelRunner, so the real recording hook runs; generative calls use offline runners bound to each agent.
COMMON MODIFICATION PATTERNS: A new model call site in JevAgent gets one test here proving its usage reaches response.usage.total.
KNOWN EDGE CASES: Generative fakes report a pricebook model (gpt-5.4-mini); an unpriced or usage-free fake is how the fail-closed paths are exercised.
RELATED DOCS: docs/design/jev-run-usage-ledger.md.
TESTS: This file.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import BaseAgent, JevAgent, JevAgentSettings, JevPreflightPreset, JevRuntimeSettings, JevSpecialist
from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import JEV_SPECIALIST_NONE
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevQuestion
from vidbyte.lib.enums import JevQuestionType, ModelProvider, UsageAccountingFailure, UsageKind
from vidbyte.lib.errors import ConfigurationError, ProviderResponseError, UsageAccountingError
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.lib.usage_ledger import active_usage_ledger, usage_ledger_scope

_RUN_DECISION = "vidbyte.providers.typesafe.TypeSafeProvider.run_decision"
_PRICED_MODEL = "gpt-5.4-mini"
_JEV_VERSION = "jev-1.13.0"
_CLEAR = 0.95
_UNCLEAR = 0.05
_CLARIFICATION = json.dumps({"questions": [{"question": "What should I build?", "recommendations": ["A login page", "A signup form"]}]})


class ScriptedGenerativeRunner:
    """Returns one scripted text response per call, with configurable model and usage."""

    def __init__(self, text: str = "done", *, model: str = _PRICED_MODEL, usage: Mapping[str, int] | None = None) -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model=model, text=text, raw={}, usage=dict(usage) if usage is not None else None)
        self.calls = 0

    def run(self, prompt: str, system: str = "", **kwargs: Any) -> TextModelResponse:
        self.calls += 1
        return self.response


def _usage(input_tokens: int, output_tokens: int) -> dict[str, int]:
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def _answer(question: JevQuestion, yes: float, choice: str) -> JevAnswer:
    # Answers a Choice question with all mass on `choice` and every other question as a noul at `yes`.
    if question.question_type is JevQuestionType.CHOICE:
        probabilities = {name: 1.0 if name == choice else 0.0 for name in question.option_names()}
        return JevAnswer(question_name=question.name, question_type=JevQuestionType.CHOICE, choice=choice, probabilities=probabilities, confidence=1.0)
    return JevAnswer(question_name=question.name, question_type=JevQuestionType.NOUL, choice="true" if yes >= 0.5 else "false", probabilities={"true": yes, "false": 1.0 - yes}, noul=yes)


def _decision(yes: float = _CLEAR, *, choice: str = JEV_SPECIALIST_NONE, usage: Mapping[str, int] | None = None, error: Exception | None = None) -> Any:
    # Fakes TypeSafeProvider.run_decision, so DecisionModelRunner's own recording hook still runs.
    async def run_decision(self: object, *, request: JevDecisionRequest, transport: object, config: object = None) -> DecisionModelResponse:
        if error is not None:
            raise error
        answers = {question.name: _answer(question, yes, choice) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model=_JEV_VERSION, answers=answers, raw={}, usage=dict(usage or _usage(300, 20)))

    return run_decision


def _agent(generative: ScriptedGenerativeRunner, *, preflight: tuple[JevPreflightPreset, ...] = (JevPreflightPreset.CLARITY,), agents: tuple[JevSpecialist, ...] = ()) -> JevAgent:
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name=_PRICED_MODEL, agents=agents)
    runtime = JevRuntimeSettings(preflight=preflight, decision=DecisionModelConfig(api_key="test-key"))
    agent = bind_test_runner(JevAgent(settings, runtime), generative)
    if agent.preflight.clarification is not None:
        bind_test_runner(agent.preflight.clarification, ScriptedGenerativeRunner(_CLARIFICATION, usage=_usage(50, 10)))
    return agent


class JevRunUsageTotalTests(unittest.IsolatedAsyncioTestCase):
    """One JevAgent run reports one total across every model and agent it used."""

    async def test_main_loop_and_decision_call_share_one_total(self) -> None:
        agent = _agent(ScriptedGenerativeRunner(usage=_usage(100, 20)))
        with patch(_RUN_DECISION, new=_decision()):
            reply = await agent.arun("Add a login page to the web app.")

        usage = agent.response.usage
        self.assertIsNotNone(usage)
        self.assertEqual(usage.total.model_call_count, 2)
        self.assertEqual((usage.generative.input_tokens, usage.generative.output_tokens), (100, 20))
        self.assertEqual((usage.decision.input_tokens, usage.decision.output_tokens), (300, 20))
        self.assertEqual(usage.total.input_tokens, 400)
        self.assertEqual([record.model for record in usage.decision.calls], [_JEV_VERSION])
        self.assertTrue(usage.total.cost_complete)
        self.assertEqual(agent.get_usage(), usage.total)
        self.assertEqual(reply.metadata["usage_rollup"], usage.total)
        self.assertEqual(agent.response.preflight_usage.input_tokens, 300)

    async def test_clarification_agent_usage_counts_when_the_gate_stops(self) -> None:
        main = ScriptedGenerativeRunner()
        agent = _agent(main)
        with patch(_RUN_DECISION, new=_decision(_UNCLEAR)):
            await agent.arun("Build it")

        usage = agent.response.usage
        self.assertEqual(main.calls, 0)
        self.assertEqual(usage.decision.model_call_count, 1)
        self.assertEqual((usage.generative.model_call_count, usage.generative.input_tokens), (1, 50))
        self.assertEqual(agent.preflight.clarification.get_usage().input_tokens, 50)

    async def test_specialist_usage_counts_toward_the_jev_agent_total(self) -> None:
        specialist_agent = bind_test_runner(BaseAgent(name="database", system_prompt="Change the schema.", provider="openai", model_name=_PRICED_MODEL), ScriptedGenerativeRunner(usage=_usage(70, 7)))
        specialist = JevSpecialist("database", "Changes to the database schema and its migrations.", specialist_agent)
        agent = _agent(ScriptedGenerativeRunner(), preflight=(), agents=(specialist,))
        with patch(_RUN_DECISION, new=_decision(choice="database")):
            reply = await agent.arun("Add a migration for the users table.")

        usage = agent.response.usage
        self.assertEqual(agent.response.specialist, "database")
        self.assertEqual((usage.generative.input_tokens, usage.decision.model_call_count), (70, 1))
        self.assertEqual(specialist_agent.get_usage().model_call_count, 1)
        self.assertEqual(reply.metadata["usage_rollup"], usage.total)

    async def test_billed_jev_failure_is_recorded_and_the_gate_still_fails_open(self) -> None:
        error = ProviderResponseError("TypeSafe answers do not match the questions sent.", provider="typesafe")
        error.details["usage"] = _usage(40, 2)
        agent = _agent(ScriptedGenerativeRunner(usage=_usage(100, 20)))
        with patch(_RUN_DECISION, new=_decision(error=error)):
            reply = await agent.arun("Add a login page to the web app.")

        self.assertEqual(reply.content, "done")
        decision = agent.response.usage.decision
        self.assertEqual(decision.input_tokens, 40)
        self.assertTrue(all(record.failed for record in decision.calls))
        self.assertIsNotNone(decision.cost_usd)


class JevRunUsageFailClosedTests(unittest.IsolatedAsyncioTestCase):
    """A gap in the ledger stops the run with an error that says the failure is Vidbyte's."""

    async def _failure(self, generative: ScriptedGenerativeRunner) -> UsageAccountingError:
        agent = _agent(generative)
        with patch(_RUN_DECISION, new=_decision()), self.assertRaises(UsageAccountingError) as caught:
            await agent.arun("Add a login page to the web app.")
        self.assertIn("error on our side", caught.exception.message)
        return caught.exception

    async def test_unpriced_model_fails_closed(self) -> None:
        error = await self._failure(ScriptedGenerativeRunner(model="not-in-the-pricebook", usage=_usage(10, 1)))
        self.assertEqual(error.details["failures"], [UsageAccountingFailure.UNPRICED_CALL.value])
        self.assertEqual(error.details["unpriced"], ["openai:not-in-the-pricebook"])

    async def test_unreported_usage_fails_closed(self) -> None:
        error = await self._failure(ScriptedGenerativeRunner(usage=None))
        self.assertEqual(error.details["failures"], [UsageAccountingFailure.UNREPORTED_USAGE.value])
        self.assertEqual(error.details["unaccounted_call_count"], 1)

    async def test_recording_error_fails_closed(self) -> None:
        with patch("vidbyte.agents.pricing.openai.OpenAIUsage.cost_usd", side_effect=RuntimeError("pricing bug")):
            error = await self._failure(ScriptedGenerativeRunner(usage=_usage(10, 1)))
        self.assertIn(UsageAccountingFailure.RECORDING_ERROR.value, error.details["failures"])

    def test_specialist_that_cannot_be_metered_is_rejected(self) -> None:
        class OwnReplyAgent(BaseAgent):
            async def generate_reply(self, message: Any, **options: Any) -> Any:
                raise AssertionError("never called")

        for unmetered in (OwnReplyAgent(name="own", system_prompt="x", provider="openai", model_name=_PRICED_MODEL), _ArunOnly()):
            with self.subTest(agent=type(unmetered).__name__), self.assertRaises(ConfigurationError):
                _agent(ScriptedGenerativeRunner(), agents=(JevSpecialist("other", "Anything else entirely.", unmetered),))


class _ArunOnly:
    """An agent-shaped object with an async arun but no BaseAgent usage tracking."""

    async def arun(self, message: str) -> Any:
        raise AssertionError("never called")


class UsageLedgerMechanismTests(unittest.IsolatedAsyncioTestCase):
    """The lib ledger, the nested-agent hook, and the tracker bookkeeping behave the same outside JevAgent."""

    async def test_nested_agent_merges_each_run_into_the_active_ledger(self) -> None:
        helper = bind_test_runner(BaseAgent(name="helper", system_prompt="Help.", provider="openai", model_name=_PRICED_MODEL), ScriptedGenerativeRunner(usage=_usage(10, 1)))
        parent = UsageTracker()
        with usage_ledger_scope(parent):
            await helper.arun("first")
            await helper.arun("second")
            self.assertIs(active_usage_ledger(), parent)

        self.assertEqual(parent.rollup().input_tokens, 20)
        self.assertEqual(helper.get_usage().input_tokens, 10)
        self.assertIsNone(active_usage_ledger())

    async def test_agents_and_runners_outside_a_metered_run_are_unchanged(self) -> None:
        plain = bind_test_runner(BaseAgent(name="plain", system_prompt="Help.", provider="openai", model_name=_PRICED_MODEL), ScriptedGenerativeRunner(model="fake", usage=None))
        reply = await plain.arun("hello")
        with patch(_RUN_DECISION, new=_decision()):
            await DecisionModelRunner(DecisionModelConfig(api_key="test-key")).arun(JevDecisionRequest(state="s", questions=(JevQuestion(name="q", question_type=JevQuestionType.NOUL, instructions="Is it?"),)))

        self.assertEqual(reply.content, "done")
        self.assertEqual(plain.get_usage().unaccounted_call_count, 1)

    def test_merge_and_kind_filter_keep_kind_failure_and_unaccounted_count(self) -> None:
        child = UsageTracker()
        child.record_call(TextModelResponse(provider=ModelProvider.OPENAI, model=_PRICED_MODEL, text="", raw={}, usage=_usage(10, 1)))
        child.record_billed_failure(ModelProvider.TYPESAFE, "jev-latest", _usage(5, 0), kind=UsageKind.DECISION)
        child.record_call(TextModelResponse(provider=ModelProvider.OPENAI, model=_PRICED_MODEL, text="", raw={}))
        parent = UsageTracker()
        parent.merge(child.rollup())

        merged = parent.rollup()
        self.assertEqual([(record.kind, record.failed) for record in merged.calls], [(UsageKind.GENERATIVE, False), (UsageKind.DECISION, True)])
        self.assertEqual(merged.unaccounted_call_count, 1)
        self.assertEqual(parent.rollup(UsageKind.DECISION).input_tokens, 5)
        self.assertEqual(parent.rollup(UsageKind.GENERATIVE).input_tokens, 10)


if __name__ == "__main__":
    unittest.main()
