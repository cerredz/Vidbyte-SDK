"""FILE: tests/features/sdk_provider_keys/test_provider_keys_failures.py

PURPOSE: Proves that every gateway failure is worded for the mode it ran in (section 9.2 table G): a Vidbyte-paid call keeps its remedies, a relay call never suggests adding a provider key it already sent and never blames a daily cap or Vidbyte's own account, a relayed provider 401/402/403 says the caller's own key was refused, and 413 and 422 name TextModelMode.DIRECT; and that no failure carries a key, a body, or a chained exception.
ROLE IN CODEBASE: Failure layer of tests/features/sdk_provider_keys/ (spec AC-14, AC-15; INV-17; D-15; EC-24 to EC-27; FR-7). Exercises vidbyte/lib/http/vidbyte_gateway.py (_GatewayAnswer.failure_reason and gateway_reason) through TextModelRunner.
ARCHITECTURE NOTE: The inner transport is scripted with gateway and provider bodies that carry BODY_CANARY and a key-shaped LEAKED_KEY (managed_text_fixtures); finding either, the Vidbyte key, or the relayed provider key in an error's message, details or formatted traceback means a leak. The retry wait is replaced at SLEEP_TARGET by BackoffRecorder.
COMMON MODIFICATION PATTERNS: When table G gains a row, add its facts to PAID_FACTS and RELAY_FACTS from the spec's "Facts the tests bind" column, never from the current wording.
WHAT NOT TO DO IN THIS FILE: 1. Do not pin whole sentences; the wording is the implementer's and only the facts are bound. 2. Do not import TextModelMode.DIRECT at module level.
KNOWN EDGE CASES: 409 and 502 are re-sent before they are raised, so they take three attempts. A relayed provider 401/402/403 cannot reach a Vidbyte-paid call (the backend remaps it), so it is tested in relay mode only.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 6.1 (INV-17) and 9.2 (table G).
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_failures.py
"""

from __future__ import annotations

import os
import re
import traceback
import unittest
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    BODY_CANARY,
    LEAKED_KEY,
    MANAGED_MODELS,
    SLEEP_TARGET,
    VIDBYTE_KEY,
    BackoffRecorder,
    ScriptedGateway,
    gateway_error,
    relayed_provider_error,
)
from tests.features.sdk_provider_keys.provider_keys_fixtures import K_ANTHROPIC, K_GEMINI_AQ, K_OPENAI, K_XAI, provider_key_header
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner

PROVIDER_KEYS = {ModelProvider.OPENAI: K_OPENAI, ModelProvider.ANTHROPIC: K_ANTHROPIC, ModelProvider.XAI: K_XAI, ModelProvider.GEMINI: K_GEMINI_AQ}
STATUSES = (401, 402, 403, 409, 413, 422, 429, 500, 502, 503)
RESENT = (409, 502)
# Section 9.2 table G, "Facts the tests bind"; rows the table leaves unchanged keep the managed pack's facts (403, 409).
COMMON_FACTS: dict[int, tuple[str, ...]] = {
    401: ("VIDBYTE_API_KEY",),
    403: ("models:invoke",),
    409: ("still", "bill", "wait"),
    413: ("2,000,000", r"TextModelMode\.DIRECT"),
    422: ("stream", r"service.?tier", r"snake.?case", r"TextModelMode\.DIRECT"),
    500: ("unavailable",),
    502: ("unavailable",),
    503: ("unavailable",),
}
PAID_FACTS: dict[int, tuple[str, ...]] = {402: ("wallet", "provider key"), 429: ("quota", "daily")}
RELAY_FACTS: dict[int, tuple[str, ...]] = {402: ("wallet",), 429: ("quota",)}
# What a relay message must not say, because the facts differ under relay (D-15).
RELAY_FORBIDDEN: dict[int, tuple[str, ...]] = {402: ("provider key",), 429: ("daily",), 500: ("Vidbyte's own account",), 502: ("Vidbyte's own account",), 503: ("Vidbyte's own account",)}


class GatewayCall:
    """One default-mode call to the gateway, Vidbyte-paid or relaying, with its scripted transport and recorded waits."""

    def __init__(self, *steps: HttpResponse | BaseException, relay: bool, provider: ModelProvider = ModelProvider.OPENAI) -> None:
        # Holds the script; relay decides whether the call carries the provider's key.
        self.transport = ScriptedGateway(*steps)
        self.backoff = BackoffRecorder()
        self.relay = relay
        self.provider = provider

    def run(self) -> Any:
        # Runs the call with a cleared environment and returns the response or the ProviderRequestError it raised.
        from vidbyte.lib.config import TextModelConfig

        options: dict[str, Any] = {"api_keys": [PROVIDER_KEYS[self.provider]]} if self.relay else {}
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True), patch(SLEEP_TARGET, new=self.backoff):
            runner = TextModelRunner(TextModelConfig(provider=self.provider.value, model=MANAGED_MODELS[self.provider], **options), transport=self.transport)
            try:
                return runner.run("Hi")
            except ProviderRequestError as error:
                return error


class FailureAssertions(unittest.TestCase):
    """Shared INV-17 assertions; holds no tests of its own."""

    def assert_credential_safe(self, error: Any, *, status: int | None, provider: ModelProvider) -> str:
        # INV-17: provider "vidbyte", the status, no excerpt, nothing chained, and no key or body text anywhere a log could print.
        self.assertIsInstance(error, ProviderRequestError)
        self.assertEqual(error.provider, "vidbyte")
        self.assertEqual(error.status_code, status)
        self.assertIsNone(error.response_excerpt)
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        message = str(error)
        rendered = message + repr(error.details) + "".join(traceback.format_exception(type(error), error, error.__traceback__))
        for secret in (BODY_CANARY, LEAKED_KEY, VIDBYTE_KEY, *PROVIDER_KEYS.values(), "model_gateway_refused"):
            self.assertNotIn(secret, rendered)
        # FR-7, D-15: the new prefix names the gateway and the call's provider.
        self.assertTrue(message.startswith(f"Vidbyte gateway {provider.value} request failed: "), message[:80])
        return message


class GatewayErrorWordingTests(FailureAssertions):
    """AC-15, D-15, EC-25 to EC-27: each gateway status states table G's facts for the mode the call ran in."""

    def test_each_gateway_status_states_the_facts_for_a_paid_call_and_for_a_relay_call(self) -> None:
        # AC-15: ten statuses in both modes; the relay call is proven to relay before its message is judged.
        for relay in (False, True):
            for status in STATUSES:
                with self.subTest(relay=relay, status=status):
                    call = GatewayCall(gateway_error(status), relay=relay)
                    message = self.assert_credential_safe(call.run(), status=status, provider=ModelProvider.OPENAI)
                    self.assertEqual(provider_key_header(call.transport.requests[0]), K_OPENAI if relay else None)
                    facts = COMMON_FACTS.get(status, ()) + (RELAY_FACTS if relay else PAID_FACTS).get(status, ())
                    self.assertTrue(facts, status)
                    for fact in facts:
                        self.assertRegex(message, re.compile(fact, re.IGNORECASE))
                    if relay:
                        for forbidden in RELAY_FORBIDDEN.get(status, ()):
                            self.assertNotIn(forbidden.lower(), message.lower())
                    self.assertEqual(len(call.transport.requests), 3 if status in RESENT else 1)


class RelayedProviderRefusalTests(FailureAssertions):
    """AC-14, EC-24: a relayed provider 401, 402 or 403 says the caller's own key or account was refused."""

    def test_a_relayed_provider_refusal_names_the_provider_and_status_and_is_never_re_sent(self) -> None:
        # AC-14: the provider's message is withheld, Vidbyte did not bill, and nothing is re-sent.
        for provider in (ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.XAI, ModelProvider.GEMINI):
            for status in (401, 402, 403):
                with self.subTest(provider=provider.value, status=status):
                    call = GatewayCall(relayed_provider_error(provider, status), relay=True, provider=provider)
                    message = self.assert_credential_safe(call.run(), status=status, provider=provider)
                    self.assertEqual(provider_key_header(call.transport.requests[0]), PROVIDER_KEYS[provider])
                    self.assertIn(str(status), message)
                    self.assertGreaterEqual(message.count(provider.value), 2, "names the provider as the refuser, not only in the prefix")
                    self.assertRegex(message, re.compile(r"your own", re.IGNORECASE))
                    self.assertRegex(message, re.compile("withheld", re.IGNORECASE))
                    self.assertRegex(message, re.compile(r"(not|n't)\b[^.;]{0,20}bill", re.IGNORECASE))
                    self.assertNotRegex(message, re.compile("quota|daily|wallet", re.IGNORECASE))
                    self.assertEqual(len(call.transport.requests), 1)
                    self.assertEqual(call.backoff.delays, [])

    def test_another_relayed_provider_status_keeps_its_unchanged_wording(self) -> None:
        # Table G last row: a relayed 400 or 429 is still the provider's answer, withheld, with no gateway remedy.
        for status in (400, 429):
            with self.subTest(status=status):
                call = GatewayCall(relayed_provider_error(ModelProvider.OPENAI, status), relay=True)
                message = self.assert_credential_safe(call.run(), status=status, provider=ModelProvider.OPENAI)
                self.assertRegex(message, re.compile("withheld", re.IGNORECASE))
                self.assertNotRegex(message, re.compile("quota|daily|wallet", re.IGNORECASE))
                self.assertEqual(len(call.transport.requests), 1)

    def test_a_relay_call_with_no_response_names_no_key(self) -> None:
        # INV-17, AC-21: a transport failure whose excerpt echoes the relayed key is raised without it.
        dropped = ProviderRequestError("connection reset", provider="http", response_excerpt=f"{BODY_CANARY} {K_OPENAI}")
        call = GatewayCall(dropped, relay=True)
        self.assert_credential_safe(call.run(), status=None, provider=ModelProvider.OPENAI)
        self.assertEqual(len(call.transport.requests), 1)


if __name__ == "__main__":
    unittest.main()
