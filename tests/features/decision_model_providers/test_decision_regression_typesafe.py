"""FILE: tests/features/decision_model_providers/test_decision_regression_typesafe.py

PURPOSE: Pins what must not change about TypeSafe while the System One pieces move into shared modules: the default runner, the shared failure template instantiated for TypeSafe, _TypeSafeCallBuilder.decision returning a header-free DecisionHttpCall, run_decision signature parity across the three adapters, JevRuntimeSettings' managed-only rule against other providers, Runner.build refusing decision providers for agents, and DecisionModelHelper over another provider's answers.
ROLE IN CODEBASE: Covers spec INV-13, INV-21 to INV-25, AC-14, AC-15, EC-22, D-14 and NFR-7 of docs/spec/decision-model-providers/spec.md; the existing tests/test_jev_*.py files remain the byte-level pin and must pass unmodified.
ARCHITECTURE NOTE: Every test binds a TypeSafe expectation to a new symbol or a new provider, so it is red before the implementation and still guards the old behaviour after it.
COMMON MODIFICATION PATTERNS: A TypeSafe message or path that the spec promises to keep gets one assertion here next to its non-TypeSafe twin.
KNOWN EDGE CASES: The managed-gateway call carries the Idempotency-Key header; the direct call does not; both are checked on the same builder.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1 (must not regress), 6.2, 6.3; tests/test_jev_agent.py; tests/test_jev_managed_gateway.py; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_regression_typesafe.py
"""

from __future__ import annotations

import inspect
import os
import unittest
from unittest.mock import patch

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.agents.jev import JevAgentSettings, JevRuntimeSettings
from vidbyte.lib.config import DecisionModelConfig, DecisionModelMode
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.runners.utility import Runner
from vidbyte.providers.typesafe import TypeSafeProvider, _TypeSafeCallBuilder

TYPESAFE_401 = "TypeSafe decision request failed: TypeSafe rejected the API key (401); check TYPESAFE_API_KEY or DecisionModelConfig.api_key. Underlying error: bad key"
TYPESAFE_MISMATCH = "TypeSafe answers do not match the questions sent: missing ['team'], unexpected ['extra']."
MANAGED_ONLY = "JevRuntimeSettings.decision must use VIDBYTE_MANAGED mode; direct TypeSafe configurations are supported only with standalone DecisionModelRunner."
DECISION_REFUSAL = "Model '{model}' is a decision model and cannot drive an agent loop; call it through DecisionModelRunner."
VIDBYTE_KEY = "vb_live_" + "a" * 32


def _typesafe_body(model: object = "jev-1.13.0") -> object:
    # A successful TypeSafe response for the section 4 request.
    return fx.response(fx.systemone_body({"refund": fx.systemone_noul(0.8), "team": fx.systemone_choice()}, model=model))


class TypeSafeRunnerTests(unittest.IsolatedAsyncioTestCase):
    """Pins the default TypeSafe runner and the shared failure wording."""

    async def test_default_runner_still_posts_to_typesafe_with_the_echoed_version(self) -> None:
        # [Hidden Failure] INV-21/INV-25/AC-14: DecisionModelConfig() is direct TypeSafe; model_name() is the typed reader's value.
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": fx.KEY}, clear=False):
            transport = fx.ScriptedTransport(_typesafe_body())
            runner = DecisionModelRunner(DecisionModelConfig(), transport=transport)
            response = await runner.arun(fx.customer_request())
            self.assertEqual(runner.model_name(), "jev-latest")
            self.assertEqual(runner.model_name(), DecisionModelConfig().resolved_model())
            self.assertEqual(transport.requests[0]["url"], "https://api.typesafe.ai/v1/systemone")
            self.assertEqual(transport.requests[0]["headers"]["authorization"], f"Bearer {fx.KEY}")
            self.assertEqual((response.provider, response.model), (ModelProvider.TYPESAFE, "jev-1.13.0"))
            self.assertNotIn("criteria", transport.requests[0]["json_body"]["questions"]["refund"])

    async def test_typesafe_messages_are_the_shared_template_for_typesafe(self) -> None:
        # [Hidden Failure] INV-23/INV-13: TypeSafe's wording is byte-identical, and Perplexity's differs only by label and env var.
        typesafe, _ = fx.scripted_runner("TYPESAFE", fx.response({"error": "bad key"}, 401))
        with self.assertRaises(ProviderRequestError) as typesafe_401:
            await typesafe.arun(fx.customer_request())
        self.assertEqual(typesafe_401.exception.message, TYPESAFE_401)
        perplexity, _ = fx.scripted_runner("PERPLEXITY", fx.response({"error": "bad key"}, 401))
        with self.assertRaises(ProviderRequestError) as perplexity_401:
            await perplexity.arun(fx.customer_request())
        self.assertEqual(perplexity_401.exception.message, TYPESAFE_401.replace("TypeSafe", "Perplexity").replace("TYPESAFE_API_KEY", "PERPLEXITY_API_KEY"))
        drift = {"refund": fx.systemone_noul(0.8), "extra": fx.systemone_noul(0.1)}
        typesafe, _ = fx.scripted_runner("TYPESAFE", fx.response(fx.systemone_body(drift, model="jev-1.13.0")))
        with self.assertRaises(ProviderResponseError) as typesafe_drift:
            await typesafe.arun(fx.customer_request())
        self.assertEqual(typesafe_drift.exception.message, TYPESAFE_MISMATCH)
        self.assertEqual(typesafe_drift.exception.details["usage"], fx.USAGE)
        baseten, _ = fx.scripted_runner("BASETEN", fx.response(fx.systemone_body(drift, model=fx.OMIT_MODEL)))
        with self.assertRaises(ProviderResponseError) as baseten_drift:
            await baseten.arun(fx.customer_request())
        self.assertEqual(baseten_drift.exception.message, TYPESAFE_MISMATCH.replace("TypeSafe", "Baseten"))
        typesafe, _ = fx.scripted_runner("TYPESAFE", _typesafe_body(model=fx.OMIT_MODEL))
        with self.assertRaises(ProviderResponseError) as no_model:
            await typesafe.arun(fx.customer_request())
        self.assertEqual(no_model.exception.message, "TypeSafe response has no `model` string naming the version that answered; received NoneType None.")

    async def test_call_builder_returns_a_header_free_decision_http_call(self) -> None:
        # [Silent Failure] INV-24: the builder keeps its name, positional order, DecisionHttpCall type, and key-free repr.
        from vidbyte.providers.decisions import DecisionHttpCall

        builder = _TypeSafeCallBuilder(HttpResponseParser())
        direct = builder.decision(DecisionModelConfig(api_key=fx.KEY), fx.customer_request())
        self.assertIsInstance(direct, DecisionHttpCall)
        self.assertNotIn(fx.KEY, repr(direct))
        self.assertEqual((direct.method, direct.url), ("POST", "https://api.typesafe.ai/v1/systemone"))
        self.assertEqual(direct.headers["authorization"], f"Bearer {fx.KEY}")
        self.assertNotIn("Idempotency-Key", direct.headers)
        self.assertRegex(direct.idempotency_key, r"^[0-9a-f]{32}$")
        self.assertEqual(direct.json_body["model"], "jev-latest")
        managed = builder.decision(DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key=VIDBYTE_KEY), fx.customer_request(), run_id="jev:run-1")
        self.assertIsInstance(managed, DecisionHttpCall)
        self.assertNotIn(VIDBYTE_KEY, repr(managed))
        self.assertEqual(managed.url, "https://api.vidbyte.pro/api/v1/models/typesafe/systemone")
        self.assertEqual(managed.headers["Idempotency-Key"], managed.idempotency_key)
        self.assertEqual(managed.headers["X-Vidbyte-Run-Id"], "jev:run-1")
        parameters = list(inspect.signature(_TypeSafeCallBuilder.decision).parameters)
        self.assertEqual(parameters, ["self", "config", "request", "run_id"])
        self.assertIs(inspect.signature(_TypeSafeCallBuilder.decision).parameters["run_id"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_three_adapters_share_the_run_decision_signature(self) -> None:
        # [Hidden Assumption] INV-24/NFR-7: tests/test_jev_usage_ledger.py patches TypeSafeProvider.run_decision by path; the twins match it.
        from vidbyte.providers.openai_decisions import OpenAIDecisionsProvider
        from vidbyte.providers.systemone import SystemOneProvider

        expected = inspect.signature(TypeSafeProvider.run_decision)
        self.assertEqual([(name, parameter.kind) for name, parameter in expected.parameters.items()], [("self", inspect.Parameter.POSITIONAL_OR_KEYWORD), ("request", inspect.Parameter.KEYWORD_ONLY), ("transport", inspect.Parameter.KEYWORD_ONLY), ("config", inspect.Parameter.KEYWORD_ONLY)])
        for adapter in (SystemOneProvider, OpenAIDecisionsProvider):
            with self.subTest(adapter=adapter.__name__):
                for method in ("run_decision", "list_models", "close_run"):
                    self.assertEqual(list(inspect.signature(getattr(adapter, method)).parameters), list(inspect.signature(getattr(TypeSafeProvider, method)).parameters))
                self.assertTrue(inspect.iscoroutinefunction(adapter.run_decision))
        self.assertIs(OpenAIDecisionsProvider.provider, ModelProvider.OPENAI)


class AgentBoundaryTests(unittest.TestCase):
    """Pins that JevAgent and agent runners do not gain the new providers."""

    def test_jev_runtime_settings_still_rejects_direct_configs(self) -> None:
        # [Hidden Failure] AC-15/INV-22: the managed-only rule and its message are unchanged for every direct provider.
        for name in ("PERPLEXITY", "OPENAI", "TYPESAFE"):
            with self.subTest(provider=name), self.assertRaises(ConfigurationError) as caught:
                JevRuntimeSettings(decision=fx.decision_config(name))
            self.assertEqual(caught.exception.message, MANAGED_ONLY)
        settings = JevRuntimeSettings(decision=DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key=VIDBYTE_KEY))
        self.assertIs(settings.decision.normalized_provider(), ModelProvider.TYPESAFE)

    def test_agent_settings_accept_decision_providers_but_runner_build_refuses_them(self) -> None:
        # [Hidden Failure] EC-22/D-14: settings pass (modality AUTO); the first runner build names DecisionModelRunner instead.
        cases = (("perplexity", "pplx-decider-v1.1-27b"), ("baseten", "mercury-decide"), ("meragpt", "sd-1"), ("cloudflare", "clef-flash"))
        for provider, model in cases:
            with self.subTest(provider=provider, model=model):
                settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider=provider, model_name=model)
                self.assertEqual((settings.provider, settings.model_name), (provider, model))
                with self.assertRaises(ConfigurationError) as caught:
                    Runner(provider=provider, model_name=model).build()
                self.assertEqual(caught.exception.message, DECISION_REFUSAL.format(model=model))
                self.assertEqual(caught.exception.details["runner_type"], "decision")
        self.assertEqual(Runner(provider=None, model_name="perplexity/pplx-decider-v1-27b").resolve_runner_type(), "decision")
        self.assertEqual(Runner(provider="foundry", model_name="microsoft-decision-2").resolve_runner_type(), "decision")

    def test_helper_scores_noul_answers_from_any_provider(self) -> None:
        # [Silent Failure] INV-25: score_noul and noul_passes read JevAnswer records, not the provider that produced them.
        from vidbyte.providers.systemone import SystemOneAnswers, SystemOneProvider

        host = SystemOneProvider.HOSTS[fx.provider_member("PERPLEXITY")]
        parsed = fx.systemone_body({"refund": fx.systemone_noul(0.8), "urgent": fx.systemone_noul(0.3)})
        request = fx.customer_request(fx.noul_question(), fx.noul_question(name="urgent", instructions="Is this urgent?"))
        normalizer = SystemOneAnswers(parsed["usage"], provider=fx.provider_member("PERPLEXITY"), label=host.display_name)
        answers = normalizer.normalize(request, parsed)
        self.assertEqual(normalizer.model(parsed, host=host, fallback="pplx-decider-v1.1-27b"), "pplx-decider-v1.1-27b")
        verdict = DecisionModelHelper.score_noul(answers, ("refund", "urgent"), 0.5)
        self.assertIsNotNone(verdict)
        self.assertAlmostEqual(verdict.score, 0.55)
        self.assertTrue(verdict.passed)
        self.assertFalse(DecisionModelHelper.score_noul(answers, ("refund", "urgent"), 0.5, veto=0.4).passed)
        self.assertIs(DecisionModelHelper.noul_passes(answers, "refund", 0.5), True)
        self.assertIs(DecisionModelHelper.noul_passes(answers, "urgent", 0.5), False)
        self.assertEqual(normalizer.error("x").details["usage"], fx.USAGE)
        self.assertEqual(normalizer.error("x").provider, "perplexity")


if __name__ == "__main__":
    unittest.main()
