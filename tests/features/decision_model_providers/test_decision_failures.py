"""FILE: tests/features/decision_model_providers/test_decision_failures.py

PURPOSE: Pins how decision calls fail on every adapter: the shared status table worded for the host and its env var, non-JSON bodies with a bounded excerpt, unexpected exceptions wrapped and cancellation passed through, list_models and close_run refused without a network call, the per-call config guard, SystemOneProvider construction guards, and the rule that the key never leaves the authorization header.
ROLE IN CODEBASE: Covers spec INV-5, INV-13, INV-16, INV-17, INV-28, AC-10, AC-13, AC-19, EC-12, EC-13, EC-14, EC-20, EC-23, EC-25, EC-28, NFR-5 and FR-6, FR-11 of docs/spec/decision-model-providers/spec.md.
ARCHITECTURE NOTE: Runner-level tests go through DecisionModelRunner; the guard and mapper tests call SystemOneProvider, OpenAIDecisionsProvider, and DecisionFailures directly, because those seams are public per spec section 8.5.
COMMON MODIFICATION PATTERNS: A new documented status adds one row to STATUS_CASES; a new capability refusal adds one case to the list_models/close_run test.
KNOWN EDGE CASES: A scripted ProviderRequestError without a status code stands in for a network failure or timeout; KeyboardInterrupt is not exercised because it would stop the test runner.
RELATED DOCS: docs/spec/decision-model-providers/spec.md sections 6.1, 6.2, 6.3, 8.5, 10; tests/features/decision_model_providers/FEATURE.md.
TESTS: python -m pytest tests/features/decision_model_providers/test_decision_failures.py
"""

from __future__ import annotations

import asyncio
import json
import unittest

from tests.features.decision_model_providers import decision_fixtures as fx
from vidbyte.lib.config import DecisionModelConfig, DecisionModelMode
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderConfigurationError, ProviderRequestError, ProviderResponseError
from vidbyte.lib.http import HttpResponseParser
from vidbyte.providers import ModelProviders

NO_RESPONSE = "HTTP request failed before receiving a provider response."
STATUS_CASES = (
    (401, "{label} rejected the API key (401); check {env_var} or DecisionModelConfig.api_key"),
    (422, "{label} rejected the request body as invalid (422); the response excerpt names the offending field"),
    (429, "{label}'s rate limit was exceeded (429) after 2 retries; back off or raise DecisionModelConfig.retry_count"),
    (529, "{label} is overloaded or failing (529) after 2 retries; retry after a short delay"),
    (503, "{label} is overloaded or failing (503) after 2 retries; retry after a short delay"),
    (408, "{label} timed out the request (408) after 2 retries"),
    (418, "{label} returned HTTP 418"),
)
NO_RESPONSE_REASON = "no response arrived (network failure or the 30.0s timeout elapsed); raise DecisionModelConfig.timeout_seconds or retry_count if this recurs"


def _expected(label: str, env_var: str, status: int | None, reason: str, underlying: str) -> str:
    # Renders the shared failure template the way TypeSafe renders it today.
    return f"{label} decision request failed: {reason.format(label=label, env_var=env_var)}. Underlying error: {underlying}"


class StatusMappingTests(unittest.IsolatedAsyncioTestCase):
    """Pins the shared status table on a System One host, Baseten, and OpenAI."""

    async def test_http_statuses_map_to_host_named_messages(self) -> None:
        # [Hidden Failure] INV-13/AC-10/EC-12/EC-13/EC-23: each status names the host that answered and the env var to fix.
        for name in ("PERPLEXITY", "BASETEN", "OPENAI"):
            row = fx.HOST_ROWS[name]
            for status, reason in STATUS_CASES:
                with self.subTest(provider=name, status=status):
                    runner, _ = fx.scripted_runner(name, fx.response({"error": f"status {status}"}, status), retry_count=2, timeout_seconds=30.0)
                    with self.assertRaises(ProviderRequestError) as caught:
                        await runner.arun(fx.customer_request())
                    self.assertEqual(caught.exception.message, _expected(row.display_name, row.env_var, status, reason, f"status {status}"))
                    self.assertEqual(caught.exception.status_code, status)
                    self.assertEqual(caught.exception.provider, name.lower())
                    self.assertEqual(caught.exception.details["response_excerpt"], json.dumps({"error": f"status {status}"}))
            with self.subTest(provider=name, status=None):
                runner, _ = fx.scripted_runner(name, ProviderRequestError(NO_RESPONSE, provider="http"), retry_count=2, timeout_seconds=30.0)
                with self.assertRaises(ProviderRequestError) as caught:
                    await runner.arun(fx.customer_request())
                self.assertEqual(caught.exception.message, _expected(row.display_name, row.env_var, None, NO_RESPONSE_REASON, NO_RESPONSE))
                self.assertIsNone(caught.exception.status_code)
                self.assertEqual(caught.exception.provider, name.lower())

    async def test_error_envelope_objects_and_the_401_prefix(self) -> None:
        # [Hidden Failure] AC-10: the message starts with the documented sentence, and an {error: {message}} envelope is read.
        runner, _ = fx.scripted_runner("PERPLEXITY", fx.response({"error": {"message": "invalid api key", "type": "auth"}}, 401))
        with self.assertRaises(ProviderRequestError) as caught:
            await runner.arun(fx.customer_request())
        self.assertTrue(caught.exception.message.startswith("Perplexity decision request failed: Perplexity rejected the API key (401); check PERPLEXITY_API_KEY or DecisionModelConfig.api_key."))
        self.assertTrue(caught.exception.message.endswith("Underlying error: invalid api key"))
        self.assertEqual((caught.exception.status_code, caught.exception.provider), (401, "perplexity"))

    async def test_non_json_gateway_page_is_rewritten_with_a_truncated_excerpt(self) -> None:
        # [Hidden Failure] EC-14/NFR-5: an HTML 504 becomes the overloaded message with the excerpt bounded to 500 characters.
        page = "<html>" + "x" * 2_000 + "</html>"
        runner, _ = fx.scripted_runner("PERPLEXITY", fx.raw_response(page, 504), retry_count=2)
        with self.assertRaises(ProviderRequestError) as caught:
            await runner.arun(fx.customer_request())
        self.assertIn("Perplexity is overloaded or failing (504) after 2 retries", caught.exception.message)
        self.assertTrue(caught.exception.message.endswith("Underlying error: Provider returned invalid JSON."))
        self.assertEqual(caught.exception.status_code, 504)
        self.assertEqual(len(caught.exception.details["response_excerpt"]), 500)

    async def test_unexpected_errors_are_wrapped_and_cancellation_propagates(self) -> None:
        # [Hidden Failure] INV-16/EC-25: a stray exception becomes ProviderResponseError; cancellation is never swallowed.
        for name in ("PERPLEXITY", "OPENAI"):
            with self.subTest(provider=name):
                runner, _ = fx.scripted_runner(name, RuntimeError("boom"))
                with self.assertRaises(ProviderResponseError) as caught:
                    await runner.arun(fx.customer_request())
                self.assertEqual(caught.exception.message, f"{name.lower()} decision failed with an unexpected RuntimeError: boom")
                self.assertEqual(caught.exception.provider, name.lower())
                self.assertNotIn("usage", caught.exception.details)
                runner, _ = fx.scripted_runner(name, asyncio.CancelledError())
                with self.assertRaises(asyncio.CancelledError):
                    await runner.arun(fx.customer_request())

    async def test_decision_failures_mapper_is_shared_by_every_adapter(self) -> None:
        # [Hidden Assumption] FR-6/INV-13: the mapper takes the provider and label, so all three adapters produce one wording.
        from vidbyte.providers.decisions import DecisionFailures

        config = fx.decision_config("PERPLEXITY", retry_count=2, timeout_seconds=30.0)
        raw = ProviderRequestError("bad key", provider="perplexity", status_code=401, response_excerpt="{}")
        mapped = DecisionFailures.transport_error(raw, operation="decision", provider=fx.provider_member("PERPLEXITY"), label="Perplexity", config=config)
        self.assertIsInstance(mapped, ProviderRequestError)
        self.assertEqual(mapped.message, _expected("Perplexity", "PERPLEXITY_API_KEY", 401, STATUS_CASES[0][1], "bad key"))
        self.assertEqual((mapped.provider, mapped.status_code, mapped.response_excerpt), ("perplexity", 401, "{}"))
        wrapped = DecisionFailures.unexpected(RuntimeError("boom"), operation="decision", provider=fx.provider_member("LIQUID"), usage=fx.USAGE)
        self.assertIsInstance(wrapped, ProviderResponseError)
        self.assertEqual(wrapped.message, "liquid decision failed with an unexpected RuntimeError: boom")
        self.assertEqual((wrapped.provider, wrapped.details["usage"]), ("liquid", fx.USAGE))
        overridden = DecisionFailures.unexpected(RuntimeError("secret"), operation="decision", provider=ModelProvider.TYPESAFE, usage=None, message="[redacted]")
        self.assertEqual(overridden.message, "typesafe decision failed with an unexpected RuntimeError: [redacted]")
        self.assertNotIn("usage", overridden.details)


class CapabilityAndGuardTests(unittest.IsolatedAsyncioTestCase):
    """Pins list_models/close_run refusals, the per-call config guard, and SystemOneProvider construction."""

    async def test_list_models_and_close_run_raise_without_a_transport_call(self) -> None:
        # [Hidden Failure] AC-13/INV-17/FR-11: no host but TypeSafe has these endpoints; refusing beats an empty tuple or a 404.
        for name in ("PERPLEXITY", "BASETEN", "OPENAI"):
            label = fx.HOST_ROWS[name].display_name
            with self.subTest(provider=name):
                runner, transport = fx.scripted_runner(name)
                with self.assertRaises(ProviderConfigurationError) as models:
                    await runner.alist_models()
                self.assertEqual(models.exception.message, f"{label} publishes no model-list endpoint; pass DecisionModelConfig.model explicitly.")
                self.assertEqual(models.exception.provider, name.lower())
                with self.assertRaises(ProviderConfigurationError) as close:
                    await runner.aclose_run("r1")
                self.assertEqual(close.exception.message, f"{label} decisions have no managed runs to close.")
                self.assertEqual(close.exception.provider, name.lower())
                self.assertEqual(transport.requests, [])

    async def test_adapter_refuses_a_config_for_another_provider_before_any_call(self) -> None:
        # [Hidden Failure] AC-19/INV-28/EC-28: without the guard "Api-Key <perplexity key>" would be posted to Perplexity's host.
        baseten = ModelProviders.decision(fx.decision_config("BASETEN"))
        transport = fx.ScriptedTransport()
        with self.assertRaises(ProviderConfigurationError) as caught:
            await baseten.run_decision(request=fx.customer_request(), transport=transport, config=fx.decision_config("PERPLEXITY"))
        self.assertEqual(caught.exception.provider, "baseten")
        self.assertEqual(caught.exception.message, "Baseten adapter received a config for provider 'perplexity'.")
        self.assertEqual(transport.requests, [])
        openai = ModelProviders.decision(fx.decision_config("OPENAI"))
        with self.assertRaises(ProviderConfigurationError) as mirror:
            await openai.run_decision(request=fx.customer_request(), transport=transport, config=fx.decision_config("PERPLEXITY"))
        self.assertEqual(mirror.exception.provider, "openai")
        self.assertEqual(mirror.exception.message, "OpenAI adapter received a config for provider 'perplexity'.")
        self.assertEqual(transport.requests, [])
        same_provider = fx.decision_config("BASETEN", model="inception/mercury-decide-v2")
        self.assertIs(baseten._config_for(same_provider), same_provider)
        self.assertEqual(baseten._config_for(None).resolved_model(), "inception/mercury-decide")

    def test_system_one_provider_construction_guards(self) -> None:
        # [Hidden Failure] EC-20/D-5: no config, no HOSTS row, or a managed config is a typed error at construction, not a KeyError later.
        from vidbyte.providers.systemone import SystemOneProvider

        with self.assertRaises(ProviderConfigurationError):
            SystemOneProvider(decision_config=None)
        with self.assertRaises(ProviderConfigurationError) as no_row:
            SystemOneProvider(decision_config=fx.decision_config("OPENAI"))
        self.assertEqual(no_row.exception.provider, "openai")
        managed = DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key="vb_live_" + "a" * 32)
        with self.assertRaises(ProviderConfigurationError) as managed_refused:
            SystemOneProvider(decision_config=managed)
        self.assertEqual(managed_refused.exception.provider, "typesafe")
        adapter = SystemOneProvider(decision_config=fx.decision_config("PERPLEXITY"), response_parser=HttpResponseParser())
        self.assertIs(adapter.provider, fx.provider_member("PERPLEXITY"))
        typesafe_direct = SystemOneProvider(decision_config=DecisionModelConfig(api_key=fx.KEY))
        self.assertIs(typesafe_direct.provider, ModelProvider.TYPESAFE)


class CredentialHygieneTests(unittest.IsolatedAsyncioTestCase):
    """Pins that the key appears only in the authorization header value."""

    async def test_key_never_leaves_the_authorization_header(self) -> None:
        # [Silent Failure] INV-5/T-3/NFR-5: not in the URL, body, message, details, or the call record's repr.
        from vidbyte.providers.decisions import DecisionHttpCall

        for name in fx.HOST_ROWS:
            with self.subTest(provider=name):
                runner, transport = fx.scripted_runner(name, fx.response({"error": "bad key"}, 401))
                with self.assertRaises(ProviderRequestError) as caught:
                    await runner.arun(fx.customer_request())
                sent = transport.requests[0]
                self.assertNotIn(fx.KEY, sent["url"])
                self.assertNotIn(fx.KEY, json.dumps(sent["json_body"]))
                self.assertTrue(sent["headers"]["authorization"].endswith(f" {fx.KEY}"))
                self.assertEqual([header for header, value in sent["headers"].items() if fx.KEY in value], ["authorization"])
                self.assertNotIn(fx.KEY, caught.exception.message)
                self.assertNotIn(fx.KEY, repr(caught.exception.details))
                self.assertNotIn(fx.KEY, repr(runner))
        call = DecisionHttpCall(method="POST", url="https://api.perplexity.ai/v1/decisions", headers={"authorization": f"Bearer {fx.KEY}"}, timeout_seconds=1.0)
        self.assertNotIn(fx.KEY, repr(call))
        self.assertEqual(call.headers["authorization"], f"Bearer {fx.KEY}")
        self.assertEqual((call.retry_count, call.idempotency_key, call.json_body), (0, None, None))


if __name__ == "__main__":
    unittest.main()
