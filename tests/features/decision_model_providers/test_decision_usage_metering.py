"""FILE: tests/features/decision_model_providers/test_decision_usage_metering.py

PURPOSE: Pins what each decision call leaves in the run's usage ledger: the pricebook key and cost per host, OpenRouter's reported cost and System One usage keys, billed failures recorded once with usage, usage-free responses counted as unaccounted, nothing recorded on transport failure or cancellation, per-provider records inside one scope, and adapters that never touch the ledger.
ROLE IN CODEBASE: Covers spec INV-10, INV-11, INV-12, INV-18, INV-19, AC-4, AC-6, AC-12, EC-17, EC-18, EC-21 and FR-5, FR-16 of docs/spec/decision-model-providers/spec.md.
ARCHITECTURE NOTE: A real UsageTracker is made active with usage_ledger_scope; DecisionModelRunner.arun is the only writer, so records are read back from tracker.records and tracker.rollup().
COMMON MODIFICATION PATTERNS: A new priced provider adds one PRICING_CASES row; a new unpriced provider adds a row whose expected cost is None.
KNOWN EDGE CASES: Cloudflare's echo (@cf/cloudflare/clef) and OpenAI's differing echo are scripted on purpose so a record priced on the echo would show up as cost_usd None; the OpenAI usage shape is parsed by OpenAIUsage, which also reads input_tokens/output_tokens.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1, 6.2, 9.1; docs/design/jev-run-usage-ledger.md; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_usage_metering.py
"""

from __future__ import annotations

import asyncio
import unittest

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.agents.pricing import OpenRouterUsage, UsageTracker
from vidbyte.lib.enums import UsageKind
from vidbyte.lib.errors import ProviderRequestError, ProviderResponseError
from vidbyte.lib.usage_ledger import usage_ledger_scope

MILLION_IN = {"input_tokens": 1_000_000, "output_tokens": 0}
# (provider, requested model override, scripted echo, expected record.model, expected cost_usd)
PRICING_CASES = (
    ("TYPESAFE", None, "jev-1.13.0", "jev-1.13.0", 0.042),
    ("PERPLEXITY", None, "pplx-decider-v1.1-27b", "pplx-decider-v1.1-27b", 0.02),
    ("CLOUDFLARE", None, "@cf/cloudflare/clef", "clef", 0.24),
    ("CLOUDFLARE", "clef-flash", "@cf/cloudflare/clef", "clef-flash", 0.038),
    ("FOUNDRY", None, fx.OMIT_MODEL, "microsoft-decision-1", 0.042),
    ("OPENAI", None, "decisions-2026-10-01", "gpt-6-luna", 0.10),
    ("LIQUID", None, "d1-2026-09-01", "d1", None),
    ("BASETEN", None, fx.OMIT_MODEL, "inception/mercury-decide", None),
    ("MERAGPT", None, fx.OMIT_MODEL, "sd-1", None),
)


def _answers() -> dict[str, object]:
    # The System One answers map for the section 4 request.
    return {"refund": fx.systemone_noul(0.8), "team": fx.systemone_choice()}


def _openai_answers() -> list[dict[str, object]]:
    # The OpenAI answers array for the section 4 request.
    return [fx.openai_predicate("refund", 0.8), fx.openai_choice()]


def _success(name: str, echo: object, usage: object) -> object:
    # Scripts one successful response in the host's wire shape.
    if name == "OPENAI":
        return fx.response(fx.openai_body(_openai_answers(), model=echo, usage=usage))
    return fx.response(fx.systemone_body(_answers(), model=echo, usage=usage))


class PricingTests(unittest.IsolatedAsyncioTestCase):
    """Pins the pricebook key and cost each host's record carries."""

    async def test_every_host_is_priced_from_the_pricebook_key(self) -> None:
        # [Silent Failure] AC-12/INV-12/INV-18/INV-27/EC-27: the record's model is the pricebook key, priced or explicitly unpriced.
        for name, requested, echo, expected_model, expected_cost in PRICING_CASES:
            with self.subTest(provider=name, model=expected_model):
                overrides = {} if requested is None else {"model": requested}
                runner, _ = fx.scripted_runner(name, _success(name, echo, MILLION_IN), **overrides)
                tracker = UsageTracker()
                with usage_ledger_scope(tracker):
                    response = await runner.arun(fx.customer_request())
                self.assertEqual(response.model, expected_model)
                self.assertEqual(len(tracker.records), 1)
                record = tracker.records[0]
                self.assertEqual((record.provider, record.model, record.kind, record.failed), (name.lower(), expected_model, UsageKind.DECISION, False))
                self.assertEqual(record.usage.input_tokens, 1_000_000)
                if expected_cost is None:
                    self.assertIsNone(record.cost_usd)
                else:
                    self.assertAlmostEqual(record.cost_usd, expected_cost)
                self.assertEqual(tracker.rollup().unaccounted_call_count, 0)
                self.assertEqual(tracker.rollup(UsageKind.DECISION).model_call_count, 1)

    async def test_openrouter_reported_cost_wins_and_system_one_usage_keys_parse(self) -> None:
        # [Silent Failure] AC-4/INV-19/FR-5: OpenRouter decisions report input_tokens/output_tokens plus cost; cost wins, keys parse.
        with_cost = {"input_tokens": 300, "output_tokens": 2, "cost": 0.0000126}
        runner, _ = fx.scripted_runner("OPENROUTER", fx.response(fx.systemone_body(_answers(), model=fx.OMIT_MODEL, usage=with_cost)))
        tracker = UsageTracker()
        with usage_ledger_scope(tracker):
            await runner.arun(fx.customer_request())
        record = tracker.records[0]
        self.assertEqual((record.provider, record.model), ("openrouter", "typesafe/jev-1.13"))
        self.assertEqual((record.usage.input_tokens, record.usage.output_tokens), (300, 2))
        self.assertEqual(record.cost_usd, 0.0000126)
        without_cost = OpenRouterUsage.from_usage_payload({"input_tokens": 300, "output_tokens": 2})
        self.assertIsNotNone(without_cost)
        self.assertEqual((without_cost.input_tokens, without_cost.output_tokens, without_cost.total_tokens, without_cost.reported_cost), (300, 2, 302, None))
        chat_keys = OpenRouterUsage.from_usage_payload({"prompt_tokens": 10, "completion_tokens": 1, "cost": 0.5})
        self.assertEqual((chat_keys.input_tokens, chat_keys.reported_cost), (10, 0.5))
        self.assertIsNone(OpenRouterUsage.from_usage_payload({"cost": 0.1}))

    async def test_liquid_zero_output_tokens_price_input_only(self) -> None:
        # [Edge Case] EC-17/INV-18: output is free everywhere, and Liquid's always-zero output does not disturb the record.
        runner, _ = fx.scripted_runner("LIQUID", fx.response(fx.systemone_body(_answers(), model="d1", usage={"input_tokens": 512, "output_tokens": 0})))
        tracker = UsageTracker()
        with usage_ledger_scope(tracker):
            await runner.arun(fx.customer_request())
        record = tracker.records[0]
        self.assertEqual((record.usage.input_tokens, record.usage.output_tokens, record.cost_usd), (512, 0, None))
        self.assertEqual(tracker.rollup().cost_complete, False)


class LedgerBehaviourTests(unittest.IsolatedAsyncioTestCase):
    """Pins billed failures, unaccounted calls, transport failures, concurrency, and adapter neutrality."""

    async def test_billed_failures_are_recorded_once_with_their_usage(self) -> None:
        # [Hidden Failure] AC-6/INV-10/INV-11: a refusal or a mismatched answer map is still a paid call and is recorded exactly once.
        cases = (
            ("OPENAI", fx.response(fx.openai_body([{"type": "refusal", "name": "refund"}, fx.openai_choice()])), "gpt-6-luna", 0.10 * 300 / 1_000_000),
            ("BASETEN", fx.response(fx.systemone_body({"refund": fx.systemone_noul(0.8)}, model=fx.OMIT_MODEL)), "inception/mercury-decide", None),
            ("PERPLEXITY", fx.response(fx.systemone_body({"refund": fx.systemone_noul(0.8)}, model="pplx-decider-v1.1-27b")), "pplx-decider-v1.1-27b", 0.02 * 300 / 1_000_000),
        )
        for name, scripted, model, cost in cases:
            with self.subTest(provider=name):
                runner, _ = fx.scripted_runner(name, scripted)
                tracker = UsageTracker()
                with usage_ledger_scope(tracker), self.assertRaises(ProviderResponseError) as caught:
                    await runner.arun(fx.customer_request())
                self.assertEqual(caught.exception.details["usage"], fx.USAGE)
                self.assertEqual(len(tracker.records), 1)
                record = tracker.records[0]
                self.assertEqual((record.provider, record.model, record.kind, record.failed), (name.lower(), model, UsageKind.DECISION, True))
                self.assertEqual(record.usage.input_tokens, 300)
                if cost is None:
                    self.assertIsNone(record.cost_usd)
                else:
                    self.assertAlmostEqual(record.cost_usd, cost)

    async def test_a_response_without_usage_is_counted_unaccounted(self) -> None:
        # [Silent Failure] EC-18: the call is counted, not dropped, when a vendor omits usage.
        for name, scripted in (("LIQUID", fx.response(fx.systemone_body(_answers(), model="d1", usage=fx.OMIT_MODEL))), ("OPENAI", fx.response(fx.openai_body(_openai_answers(), usage=fx.OMIT_MODEL)))):
            with self.subTest(provider=name):
                runner, _ = fx.scripted_runner(name, scripted)
                tracker = UsageTracker()
                with usage_ledger_scope(tracker):
                    response = await runner.arun(fx.customer_request())
                self.assertIsNone(response.usage)
                self.assertEqual(tracker.records, ())
                self.assertEqual(tracker.rollup().unaccounted_call_count, 1)

    async def test_transport_failures_and_cancellation_record_nothing(self) -> None:
        # [Hidden Assumption] INV-11/INV-16/EC-25: a 401 or a cancelled task bills nothing, so the ledger must stay empty.
        for name in ("PERPLEXITY", "OPENAI"):
            with self.subTest(provider=name):
                tracker = UsageTracker()
                with usage_ledger_scope(tracker):
                    runner, _ = fx.scripted_runner(name, fx.response({"error": "bad key"}, 401))
                    with self.assertRaises(ProviderRequestError):
                        await runner.arun(fx.customer_request())
                    runner, _ = fx.scripted_runner(name, asyncio.CancelledError())
                    with self.assertRaises(asyncio.CancelledError):
                        await runner.arun(fx.customer_request())
                self.assertEqual(tracker.records, ())
                self.assertEqual(tracker.rollup().unaccounted_call_count, 0)
                self.assertFalse(tracker.recording_corrupted)

    async def test_two_providers_in_one_scope_keep_their_own_records(self) -> None:
        # [Silent Failure] EC-21/INV-12: concurrent runners for different providers are priced per record, never cross-wired.
        perplexity, _ = fx.scripted_runner("PERPLEXITY", _success("PERPLEXITY", "pplx-decider-v1.1-27b", MILLION_IN))
        openai, _ = fx.scripted_runner("OPENAI", _success("OPENAI", "gpt-6-luna", MILLION_IN))
        tracker = UsageTracker()
        with usage_ledger_scope(tracker):
            await asyncio.gather(perplexity.arun(fx.customer_request()), openai.arun(fx.customer_request()))
        by_provider = {record.provider: record for record in tracker.records}
        self.assertEqual(set(by_provider), {"perplexity", "openai"})
        self.assertAlmostEqual(by_provider["perplexity"].cost_usd, 0.02)
        self.assertAlmostEqual(by_provider["openai"].cost_usd, 0.10)
        self.assertEqual(by_provider["perplexity"].model, "pplx-decider-v1.1-27b")
        self.assertEqual(by_provider["openai"].model, "gpt-6-luna")
        rollup = tracker.rollup(UsageKind.DECISION)
        self.assertEqual(rollup.model_call_count, 2)
        self.assertTrue(rollup.cost_complete)
        self.assertAlmostEqual(rollup.cost_usd, 0.12)

    async def test_adapters_never_touch_the_ledger(self) -> None:
        # [Hidden Assumption] INV-11/FR-16: calling an adapter directly inside a scope records nothing; only the runner meters.
        from vidbyte.providers.openai_decisions import OpenAIDecisionsProvider
        from vidbyte.providers.systemone import SystemOneProvider

        tracker = UsageTracker()
        with usage_ledger_scope(tracker):
            system_one = SystemOneProvider(decision_config=fx.decision_config("PERPLEXITY"))
            await system_one.run_decision(request=fx.customer_request(), transport=fx.ScriptedTransport(_success("PERPLEXITY", "pplx-decider-v1.1-27b", fx.USAGE)))
            openai = OpenAIDecisionsProvider(decision_config=fx.decision_config("OPENAI"))
            await openai.run_decision(request=fx.customer_request(), transport=fx.ScriptedTransport(_success("OPENAI", "gpt-6-luna", fx.USAGE)))
            self.assertEqual(tracker.records, ())
            self.assertEqual(tracker.rollup().unaccounted_call_count, 0)
            runner, _ = fx.scripted_runner("PERPLEXITY", _success("PERPLEXITY", "pplx-decider-v1.1-27b", fx.USAGE))
            await runner.arun(fx.customer_request())
        self.assertEqual(len(tracker.records), 1)


if __name__ == "__main__":
    unittest.main()
