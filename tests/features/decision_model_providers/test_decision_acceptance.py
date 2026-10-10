"""FILE: tests/features/decision_model_providers/test_decision_acceptance.py

PURPOSE: Runs the developer-usage snippet of spec section 4 over scripted transports (Perplexity from PERPLEXITY_API_KEY, OpenAI's Decisions wire, Cloudflare with a tenant endpoint) and proves the "change provider and nothing else" promise over all nine providers: same request, same JevAnswer records, same DecisionModelHelper.score_noul, same ledger.
ROLE IN CODEBASE: Covers AC-1 and the prose of section 4 of docs/spec/decision-model-providers/spec.md; the detailed wire and failure behaviour lives in the sibling files.
ARCHITECTURE NOTE: The snippet is reproduced line for line with the transport injected; keys come from patch.dict(os.environ, ...), never from a real environment.
COMMON MODIFICATION PATTERNS: When section 4 of the spec changes, change the snippet test to match; keep the nine-provider property in step with HOST_ROWS.
KNOWN EDGE CASES: The Cloudflare line of the snippet uses a placeholder account id in the endpoint; the test only checks the URL it produces.
RELATED DOCS: docs/spec/decision-model-providers/spec.md section 4; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_acceptance.py
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.dataclasses.jev import JevAnswer, JevDecisionRequest, JevOption, JevQuestion
from vidbyte.lib.enums import JevQuestionType, ModelProvider, UsageKind
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.jev.decision import DecisionModelHelper
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.lib.usage_ledger import usage_ledger_scope

SNIPPET_ENV = {"PERPLEXITY_API_KEY": "perplexity-test-key", "OPENAI_API_KEY": "openai-test-key", "CLOUDFLARE_API_TOKEN": "cloudflare-test-token"}


def _section_4_request() -> JevDecisionRequest:
    # The request exactly as spec section 4 writes it.
    return JevDecisionRequest(
        state="Customer: my order arrived broken and support ignored two emails.",
        questions=(
            JevQuestion(name="refund", question_type=JevQuestionType.NOUL, instructions="Should this customer receive a refund?"),
            JevQuestion(name="team", question_type=JevQuestionType.CHOICE, instructions="Which team owns the next step?", options=(JevOption("billing"), JevOption("logistics"), JevOption("support"))),
        ),
    )


def _system_one_success(name: str) -> object:
    # One successful System One response for the section 4 request in the host's echo convention.
    echo = {"TYPESAFE": "jev-1.13.0", "PERPLEXITY": "pplx-decider-v1.1-27b"}.get(name, fx.OMIT_MODEL)
    return fx.response(fx.systemone_body({"refund": fx.systemone_noul(0.8), "team": fx.systemone_choice()}, model=echo))


class DeveloperUsageTests(unittest.IsolatedAsyncioTestCase):
    """Runs the section 4 snippet and the nine-provider property."""

    async def test_section_4_snippet_runs_over_scripted_transports(self) -> None:
        # [Silent Failure] AC-1: the snippet produces exactly the shown result on each of its three providers.
        request = _section_4_request()
        with patch.dict(os.environ, SNIPPET_ENV, clear=False):
            perplexity_transport = fx.ScriptedTransport(_system_one_success("PERPLEXITY"))
            perplexity = DecisionModelRunner(DecisionModelConfig(provider=ModelProvider.PERPLEXITY), transport=perplexity_transport)
            response = await perplexity.arun(request)
            self.assertEqual(response.answer("refund").noul, 0.8)
            self.assertTrue(0.0 <= response.answer("refund").noul <= 1.0)
            self.assertIn(response.answer("team").choice, {"billing", "logistics", "support"})
            self.assertEqual(response.answer("team").choice, "billing")
            self.assertEqual((response.provider, response.model), (ModelProvider.PERPLEXITY, "pplx-decider-v1.1-27b"))
            self.assertEqual(perplexity_transport.requests[0]["headers"]["authorization"], "Bearer perplexity-test-key")
            self.assertEqual(perplexity_transport.requests[0]["json_body"]["model"], "pplx-decider-v1.1-27b")

            openai_transport = fx.ScriptedTransport(fx.response(fx.openai_body([fx.openai_predicate("refund", 0.8), fx.openai_choice()])))
            openai = DecisionModelRunner(DecisionModelConfig(provider=ModelProvider.OPENAI), transport=openai_transport)
            response = await openai.arun(request)
            self.assertEqual(response.answer("refund").probabilities["true"], 0.8)
            self.assertAlmostEqual(response.answer("refund").probabilities["false"], 0.2)
            self.assertEqual((response.provider, response.model), (ModelProvider.OPENAI, "gpt-6-luna"))
            self.assertEqual(openai_transport.requests[0]["url"], "https://api.openai.com/v1/decisions")
            self.assertEqual(openai_transport.requests[0]["json_body"]["model"], "gpt-6-luna")

            cloudflare_transport = fx.ScriptedTransport(_system_one_success("CLOUDFLARE"))
            cloudflare = DecisionModelRunner(DecisionModelConfig(provider=ModelProvider.CLOUDFLARE, model="clef-flash", endpoint="https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai"), transport=cloudflare_transport)
            response = await cloudflare.arun(request)
            self.assertEqual(cloudflare_transport.requests[0]["url"], "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/run/@cf/cloudflare/clef")
            self.assertEqual(cloudflare_transport.requests[0]["headers"]["authorization"], "Bearer cloudflare-test-token")
            self.assertEqual((response.provider, response.model), (ModelProvider.CLOUDFLARE, "clef-flash"))
            with self.assertRaises(ConfigurationError):
                DecisionModelRunner(DecisionModelConfig(provider=ModelProvider.CLOUDFLARE, model="clef-flash"), transport=fx.ScriptedTransport())

    async def test_changing_the_provider_changes_nothing_else(self) -> None:
        # [Hidden Assumption] section 4 prose: same request, same JevAnswer records, same score_noul, same ledger on all nine providers.
        request = _section_4_request()
        tracker = UsageTracker()
        with usage_ledger_scope(tracker):
            for name, row in fx.HOST_ROWS.items():
                with self.subTest(provider=name):
                    scripted = fx.response(fx.openai_body([fx.openai_predicate("refund", 0.8), fx.openai_choice()])) if name == "OPENAI" else _system_one_success(name)
                    runner, transport = fx.scripted_runner(name, scripted)
                    response = await runner.arun(request)
                    self.assertEqual(set(response.answers), {"refund", "team"})
                    self.assertTrue(all(isinstance(answer, JevAnswer) for answer in response.answers.values()))
                    self.assertEqual(response.answer("refund").noul, 0.8)
                    self.assertEqual(response.answer("team").choice, "billing")
                    verdict = DecisionModelHelper.score_noul(response.answers, ("refund",), 0.5)
                    self.assertIsNotNone(verdict)
                    self.assertTrue(verdict.passed)
                    self.assertEqual(verdict.score, 0.8)
                    self.assertIs(response.provider, fx.provider_member(name))
                    self.assertEqual(transport.requests[0]["url"], fx.expected_url(name))
                    self.assertEqual(runner.model_name(), row.default_model)
        self.assertEqual(len(tracker.records), len(fx.HOST_ROWS))
        self.assertEqual({record.kind for record in tracker.records}, {UsageKind.DECISION})
        self.assertEqual([record.provider for record in tracker.records], [name.lower() for name in fx.HOST_ROWS])


if __name__ == "__main__":
    unittest.main()
