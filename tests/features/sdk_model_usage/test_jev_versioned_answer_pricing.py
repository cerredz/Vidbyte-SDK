"""FILE: tests/features/sdk_model_usage/test_jev_versioned_answer_pricing.py

PURPOSE: Prove that a Jev decision answered by a TypeSafe release the pricebook has not caught up with is still priced, so a JevAgent run is not failed closed after TypeSafe already billed it, and that genuinely unpriced requests still fail closed.
ROLE IN CODEBASE: Exercises ModelPricingRegistry.resolve_answered (vidbyte/lib/registries/pricing.py), UsageTracker.record_call's requested_model (vidbyte/agents/pricing/tracker.py), the DecisionModelRunner recording hook (vidbyte/lib/runners/decision.py), and JevUsageAccount's fail-closed check through a real JevAgent run.
ARCHITECTURE NOTE: Decision calls are faked at TypeSafeProvider.run_decision, below DecisionModelRunner, so the real runner, ledger, pricebook, and JevUsageAccount all run; generative calls use an offline runner that reports a priced OpenAI model.
FUNCTION INVENTORY: Registry and tracker tests pin the jev-1.14 row and the fallback's scope (TypeSafe only, versioned answers only, priced requests only); the runner test pins that the requested model reaches the ledger; the JevAgent tests replay the 2026-10-25 failure and its fail-closed boundary.
COMMON MODIFICATION PATTERNS: When TypeSafe ships a release, add its row in pricing.py and its ID to the priced-release test; keep a hypothetical later release in the fallback tests so they never depend on today's newest version.
WHAT NOT TO DO IN THIS FILE: 1. Do not call TypeSafe or Vidbyte; tests stay offline and keyless. 2. Do not add rates here; vidbyte/lib/registries/pricing.py owns the table.
KNOWN EDGE CASES: The fallback prices a later release at the requested alias's row, so a release with a new price stays under-reported until its own row is added; only an answer ID of the documented jev-<major>.<minor>.<patch> shape falls back.
RELATED DOCS: tests/features/sdk_model_usage/FEATURE.md, docs/design/jev-run-usage-ledger.md, https://docs.typesafe.ai/models.md.
TESTS: This module and the scripts/run_ci.py source gate.
"""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent, JevAgentSettings, JevPreflightPreset, JevRuntimeSettings
from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevQuestion
from vidbyte.lib.enums import DecisionModelMode, JevQuestionType, ModelProvider, UsageAccountingFailure, UsageKind
from vidbyte.lib.errors import UsageAccountingError
from vidbyte.lib.registries.pricing import PROVIDER_PRICING, ModelPricing, ModelPricingRegistry
from vidbyte.lib.runners import TextModelResponse
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.types import DecisionModelResponse
from vidbyte.lib.usage_ledger import usage_ledger_scope

_RUN_DECISION = "vidbyte.providers.typesafe.TypeSafeProvider.run_decision"
_PRICED_MODEL = "gpt-5.4-mini"
_JEV_1_14 = "jev-1.14.0"
# A release no pricebook row covers, standing in for whatever TypeSafe ships after the table was last updated.
_FUTURE_RELEASE = "jev-1.15.0"
_JEV_RATE_PER_MILLION = 0.042
_DECISION_USAGE = {"input_tokens": 300, "output_tokens": 20}
_EXPECTED_DECISION_COST = 300 * _JEV_RATE_PER_MILLION / 1_000_000


def _jev_response(model: str, usage: Mapping[str, int] | None = None) -> SimpleNamespace:
    return SimpleNamespace(provider=ModelProvider.TYPESAFE, model=model, usage=dict(usage or {"input_tokens": 1_000_000, "output_tokens": 500_000}))


class _ScriptedGenerativeRunner:
    """Returns one priced text response per call, so only the decision call can leave the ledger unpriced."""

    def __init__(self) -> None:
        self.response = TextModelResponse(provider=ModelProvider.OPENAI, model=_PRICED_MODEL, text="done", raw={}, usage={"input_tokens": 100, "output_tokens": 20})

    def run(self, prompt: str, system: str = "", **kwargs: Any) -> TextModelResponse:
        return self.response


def _clear_answer(question: JevQuestion) -> JevAnswer:
    # Answers every question as a confident noul "true", which lets the clarity gate pass.
    return JevAnswer(question_name=question.name, question_type=JevQuestionType.NOUL, choice="true", probabilities={"true": 0.95, "false": 0.05}, noul=0.95)


def _answered_by(model: str) -> Any:
    # Fakes TypeSafeProvider.run_decision so the answer names `model`, the way TypeSafe names the release that served it.
    async def run_decision(self: object, *, request: JevDecisionRequest, transport: object, config: object = None) -> DecisionModelResponse:
        answers = {question.name: _clear_answer(question) for question in request.questions}
        return DecisionModelResponse(provider=ModelProvider.TYPESAFE, model=model, answers=answers, raw={}, usage=dict(_DECISION_USAGE))

    return run_decision


def _jev_agent(decision_model: str = "jev-latest") -> JevAgent:
    settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name=_PRICED_MODEL)
    decision = DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, model=decision_model, api_key="vb_live_" + "x" * 32)
    agent = bind_test_runner(JevAgent(settings, JevRuntimeSettings(preflight=(JevPreflightPreset.CLARITY,), decision=decision)), _ScriptedGenerativeRunner())
    if agent.preflight.clarification is not None:
        bind_test_runner(agent.preflight.clarification, _ScriptedGenerativeRunner())
    return agent


class VersionedAnswerPricebookTests(unittest.TestCase):
    """The pricebook prices today's Jev release on its own row and later releases as the requested model."""

    def test_jev_1_14_answer_is_priced_on_its_own_row_at_the_published_rate(self) -> None:
        # [Regression] 2026-10-25: TypeSafe answered jev-1.14.0 and the pricebook had only jev-1.13, so it resolved to None.
        record = UsageTracker().record_call(_jev_response(_JEV_1_14), kind=UsageKind.DECISION)
        self.assertIs(ModelPricingRegistry.default().resolve(ModelProvider.TYPESAFE, _JEV_1_14), PROVIDER_PRICING[ModelProvider.TYPESAFE]["jev-1.14"])
        self.assertIsNotNone(record)
        self.assertAlmostEqual(record.cost_usd, _JEV_RATE_PER_MILLION)

    def test_later_release_answering_jev_latest_is_priced_at_jev_latest_rate(self) -> None:
        # A distinct jev-latest rate proves the price comes from the requested model's row, not from a neighbouring release.
        registry = ModelPricingRegistry.default()
        registry.register(ModelProvider.TYPESAFE, "jev-latest", ModelPricing(input_per_million=0.5, output_per_million=0.0))
        record = UsageTracker(pricing=registry).record_call(_jev_response(_FUTURE_RELEASE), kind=UsageKind.DECISION, requested_model="jev-latest")
        self.assertIsNotNone(record)
        self.assertEqual(record.model, _FUTURE_RELEASE)
        self.assertAlmostEqual(record.cost_usd, 0.5)

    def test_later_release_answering_jev_latest_uses_the_default_table_rate(self) -> None:
        record = UsageTracker().record_call(_jev_response(_FUTURE_RELEASE), kind=UsageKind.DECISION, requested_model="jev-latest")
        self.assertIsNotNone(record)
        self.assertAlmostEqual(record.cost_usd, _JEV_RATE_PER_MILLION)

    def test_request_for_an_unpriced_release_stays_unpriced(self) -> None:
        # Fail closed: the fallback never invents a price when the caller asked for a model the table lacks.
        record = UsageTracker().record_call(_jev_response(_FUTURE_RELEASE), kind=UsageKind.DECISION, requested_model=_FUTURE_RELEASE)
        self.assertIsNotNone(record)
        self.assertIsNone(record.cost_usd)

    def test_without_a_requested_model_an_unknown_release_stays_unpriced(self) -> None:
        # Only DecisionModelRunner passes the requested model; any other recording keeps the strict lookup.
        record = UsageTracker().record_call(_jev_response(_FUTURE_RELEASE), kind=UsageKind.DECISION)
        self.assertIsNone(record.cost_usd)

    def test_answer_ids_that_are_not_versioned_releases_do_not_fall_back(self) -> None:
        registry = ModelPricingRegistry.default()
        for answered in ("jev-1.15.0-experimental", "jev-2", "jev-max", "other-1.15.0", ""):
            with self.subTest(answered=answered):
                self.assertIsNone(registry.resolve_answered(ModelProvider.TYPESAFE, answered, "jev-latest"))

    def test_other_providers_never_fall_back_to_the_requested_model(self) -> None:
        # Scope: the fallback is for TypeSafe's versioned answers only; an unpriced generative model still fails closed.
        registry = ModelPricingRegistry.default()
        self.assertIsNotNone(registry.resolve(ModelProvider.OPENAI, _PRICED_MODEL))
        for provider, answered in ((ModelProvider.OPENAI, "gpt-9.9.9"), (ModelProvider.OPENAI, "jev-1.15.0"), (ModelProvider.ANTHROPIC, "claude-9-9")):
            with self.subTest(provider=provider.value, answered=answered):
                self.assertIsNone(registry.resolve_answered(provider, answered, _PRICED_MODEL))

    def test_a_priced_answer_keeps_its_own_rate_over_the_requested_model(self) -> None:
        registry = ModelPricingRegistry.default()
        registry.register(ModelProvider.TYPESAFE, "jev-latest", ModelPricing(input_per_million=0.5, output_per_million=0.0))
        self.assertIs(registry.resolve_answered(ModelProvider.TYPESAFE, _JEV_1_14, "jev-latest"), PROVIDER_PRICING[ModelProvider.TYPESAFE]["jev-1.14"])


class DecisionRunnerRecordingTests(unittest.IsolatedAsyncioTestCase):
    """DecisionModelRunner tells the run's ledger which model it requested."""

    async def test_runner_prices_a_later_release_as_its_configured_model(self) -> None:
        tracker = UsageTracker()
        request = JevDecisionRequest(state="s", questions=(JevQuestion(name="q", question_type=JevQuestionType.NOUL, instructions="Is it?"),))
        with usage_ledger_scope(tracker), patch(_RUN_DECISION, new=_answered_by(_FUTURE_RELEASE)):
            await DecisionModelRunner(DecisionModelConfig(model="jev-latest", api_key="test-key")).arun(request)

        (record,) = tracker.records
        self.assertEqual((record.kind, record.model), (UsageKind.DECISION, _FUTURE_RELEASE))
        self.assertAlmostEqual(record.cost_usd, _EXPECTED_DECISION_COST)
        self.assertTrue(tracker.rollup().cost_complete)


class JevAgentVersionedAnswerTests(unittest.IsolatedAsyncioTestCase):
    """A JevAgent run answered by a new Jev release returns its answer with the decision priced."""

    async def test_run_answered_by_jev_1_14_settles_with_the_decision_priced(self) -> None:
        # [Regression] 2026-10-25: every JevAgent run raised UsageAccountingError (unpriced_call, typesafe:jev-1.14.0)
        # in usage.settle() after its decision call had been billed.
        agent = _jev_agent()
        with patch(_RUN_DECISION, new=_answered_by(_JEV_1_14)):
            reply = await agent.arun("Add a login page to the web app.")

        decision = agent.response.usage.decision
        self.assertEqual(reply.content, "done")
        self.assertEqual([record.model for record in decision.calls], [_JEV_1_14])
        self.assertAlmostEqual(decision.cost_usd, _EXPECTED_DECISION_COST)
        self.assertTrue(agent.response.usage.total.cost_complete)

    async def test_run_answered_by_a_later_release_is_priced_as_jev_latest(self) -> None:
        agent = _jev_agent()
        with patch(_RUN_DECISION, new=_answered_by(_FUTURE_RELEASE)):
            await agent.arun("Add a login page to the web app.")

        decision = agent.response.usage.decision
        self.assertEqual([record.model for record in decision.calls], [_FUTURE_RELEASE])
        self.assertAlmostEqual(decision.cost_usd, _EXPECTED_DECISION_COST)

    async def test_run_pinned_to_an_unpriced_release_still_fails_closed(self) -> None:
        agent = _jev_agent(decision_model=_FUTURE_RELEASE)
        with patch(_RUN_DECISION, new=_answered_by(_FUTURE_RELEASE)), self.assertRaises(UsageAccountingError) as caught:
            await agent.arun("Add a login page to the web app.")

        self.assertEqual(caught.exception.details["failures"], [UsageAccountingFailure.UNPRICED_CALL.value])
        self.assertEqual(caught.exception.details["unpriced"], [f"typesafe:{_FUTURE_RELEASE}"])


if __name__ == "__main__":
    unittest.main()
