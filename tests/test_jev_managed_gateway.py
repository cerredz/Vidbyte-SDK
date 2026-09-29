"""FILE: tests/test_jev_managed_gateway.py

PURPOSE: Verifies JevAgent's Vidbyte managed gateway configuration, credential handling, request paths, error policy, and direct TypeSafe compatibility without live network calls.
ROLE IN CODEBASE: Pins the SDK contract to the Vidbyte product gateway's live-key format and models:invoke routes.
ARCHITECTURE NOTE: Scripted transports and patched decision runners replace only external service boundaries; production config and Jev call sites remain under test.
COMMON MODIFICATION PATTERNS: Extend this module when the gateway endpoint, key contract, access statuses, or Jev failure policy changes.
KNOWN EDGE CASES: Managed credentials are read only when a decision feature calls Jev; no test contacts Vidbyte or TypeSafe.
RELATED DOCS: docs/design/jev-managed-gateway-credentials.md and skills/jev-agent/SKILL.md.
TESTS: python -m pytest tests/test_jev_managed_gateway.py and python scripts/test-jev-managed-gateway.py.
"""

from __future__ import annotations

import inspect
import json
import os
import traceback
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from vidbyte.agents.jev.decision_failures import JevDecisionFailurePolicy
from vidbyte.agents.jev.done.run_state import JevRunState
from vidbyte.agents.jev.gate.gate import JevPreflightGate
from vidbyte.agents.jev.preflight import JevPreflightTools
from vidbyte.agents.jev.response import JevResponse
from vidbyte.agents.jev.settings import JevAgentSettings, JevRuntimeSettings
from vidbyte.lib.config import DecisionModelConfig, DecisionModelMode
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevQuestion
from vidbyte.lib.enums import JevPreflightPreset, JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError, ProviderRequestError, ProviderResponseError
from vidbyte.lib.http import HttpResponse, HttpResponseParser, HttpTransport
from vidbyte.lib.runners.decision import DecisionModelRunner
from vidbyte.tools.catalog import Tools
from vidbyte import tool
from vidbyte.providers.typesafe import _TypeSafeCallBuilder

VIDBYTE_KEY = "vb_live_" + "a" * 32
DIRECT_KEY = "typesafe-test-key"


class ScriptedTransport:
    """Records requests and returns one scripted HTTP response."""

    def __init__(self, response: HttpResponse) -> None:
        # Keeps one deterministic response for an offline provider call.
        self.response = response
        self.requests: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> HttpResponse:
        # Captures transport arguments and returns the scripted response.
        self.requests.append(kwargs)
        return self.response


def managed_response(status: int, payload: object) -> HttpResponse:
    # Encodes a deterministic JSON response for the provider adapter.
    return HttpResponse(status_code=status, body=json.dumps(payload), headers={})


def decision_request() -> JevDecisionRequest:
    # Builds one valid Noul request shared by the provider contract tests.
    question = JevQuestion(name="decision", question_type=JevQuestionType.NOUL, instructions="Does the request meet the stated rule?")
    return JevDecisionRequest(state="A synthetic request.", questions=(question,))


def jev_settings() -> JevAgentSettings:
    # Builds a minimal generative configuration without resolving its provider key.
    return JevAgentSettings(name="managed-jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini")


class DecisionConfigTests(unittest.TestCase):
    """Checks mode defaults, key resolution, endpoint pinning, and credential redaction."""

    def test_general_config_stays_direct_and_jev_defaults_managed(self) -> None:
        # [Silent Failure] A default mode drift would either bypass Vidbyte or break standalone runners.
        self.assertIs(DecisionModelConfig().mode, DecisionModelMode.TYPESAFE)
        self.assertIs(JevRuntimeSettings().decision.mode, DecisionModelMode.VIDBYTE_MANAGED)

    def test_managed_key_source_does_not_fall_back_to_typesafe(self) -> None:
        # [Hidden Assumption] A configured TypeSafe key must not satisfy managed authentication.
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": DIRECT_KEY}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "VIDBYTE_API_KEY"):
                DecisionModelConfig.vidbyte_managed().resolved_api_key()

    def test_managed_key_matches_product_live_format(self) -> None:
        # [Edge Case] The product accepts live keys with at least 32 base64url suffix characters.
        for invalid in ("", "   ", "vb_live_short", "vb_test_" + "a" * 32, DIRECT_KEY):
            with self.subTest(invalid=invalid[:14]), patch.dict(os.environ, {"VIDBYTE_API_KEY": invalid}, clear=True):
                with self.assertRaises(ConfigurationError):
                    DecisionModelConfig.vidbyte_managed().resolved_api_key()
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            self.assertEqual(DecisionModelConfig.vidbyte_managed().resolved_api_key(), VIDBYTE_KEY)
        with self.assertRaises(ConfigurationError) as caught:
            DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key=object()).resolved_api_key()  # type: ignore[arg-type]
        self.assertTrue(JevDecisionFailurePolicy.should_fail_closed(caught.exception, DecisionModelConfig.vidbyte_managed()))

    def test_managed_endpoint_is_fixed_and_custom_urls_are_rejected(self) -> None:
        # [Hidden Assumption] No managed config may redirect its bearer credential to caller-selected hosts.
        config = DecisionModelConfig.vidbyte_managed()
        self.assertEqual(config.resolved_endpoint(), "https://api.vidbyte.pro/api/v1/models/typesafe")
        for endpoint in ("https://attacker.example", "https://api.vidbyte.pro/other", object()):
            with self.subTest(endpoint=endpoint), self.assertRaises(ConfigurationError):
                DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, endpoint=endpoint)  # type: ignore[arg-type]

    def test_direct_mode_keeps_environment_endpoint_and_positional_compatibility(self) -> None:
        # [Hidden Failure] Adding the mode field must not shift existing positional config arguments.
        config = DecisionModelConfig(ModelProvider.TYPESAFE, "jev-latest", DIRECT_KEY, "https://proxy.example/v1", 30.0, 1)
        self.assertIs(config.mode, DecisionModelMode.TYPESAFE)
        self.assertEqual(config.resolved_api_key(), DIRECT_KEY)
        self.assertEqual(config.resolved_endpoint(), "https://proxy.example/v1")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": DIRECT_KEY}, clear=True):
            self.assertEqual(DecisionModelConfig().resolved_api_key(), DIRECT_KEY)

    def test_credentials_are_hidden_from_config_settings_and_call_repr(self) -> None:
        # [Silent Failure] A repr leak can put the managed key into debug logs or exception reports.
        config = DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, api_key=VIDBYTE_KEY)
        settings = JevRuntimeSettings(decision=config)
        call = _TypeSafeCallBuilder(HttpResponseParser()).decision(config, decision_request())
        for rendered in (repr(config), repr(settings), repr(call)):
            self.assertNotIn(VIDBYTE_KEY, rendered)


class ManagedTransportTests(unittest.IsolatedAsyncioTestCase):
    """Checks gateway routes, credential headers, upstream errors, and direct mode."""

    async def test_decision_request_uses_product_systemone_path(self) -> None:
        # [Silent Failure] A successful answer must come from the managed systemone route with the Vidbyte key.
        body = {"model": "jev-1.13.0", "answers": {"decision": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": 2, "output_tokens": 1}}
        transport = ScriptedTransport(managed_response(200, body))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            result = await DecisionModelRunner(DecisionModelConfig.vidbyte_managed(), transport=transport).arun(decision_request())
        sent = transport.requests[0]
        self.assertEqual(result.answer("decision").noul, 0.9)
        self.assertEqual(sent["url"], "https://api.vidbyte.pro/api/v1/models/typesafe/systemone")
        self.assertEqual(sent["headers"]["authorization"], f"Bearer {VIDBYTE_KEY}")

    async def test_model_listing_uses_product_models_route(self) -> None:
        # [Edge Case] An empty, valid model collection stays an empty tuple on the managed route.
        transport = ScriptedTransport(managed_response(200, {"models": []}))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            models = await DecisionModelRunner(DecisionModelConfig.vidbyte_managed(), transport=transport).alist_models()
        self.assertEqual(models, ())
        self.assertEqual(transport.requests[0]["url"], "https://api.vidbyte.pro/api/v1/models/typesafe/models")

    async def test_managed_access_errors_keep_status_and_drop_echoed_credentials(self) -> None:
        # [Hidden Failure] A gateway response that repeats the bearer key must not disclose it in an exception.
        for status in (401, 402, 403, 429):
            with self.subTest(status=status), patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
                transport = ScriptedTransport(managed_response(status, {"error": {"message": VIDBYTE_KEY}}))
                runner = DecisionModelRunner(DecisionModelConfig(mode=DecisionModelMode.VIDBYTE_MANAGED, retry_count=0), transport=transport)
                with self.assertRaises(ProviderRequestError) as caught:
                    await runner.arun(decision_request())
                self.assertEqual(caught.exception.status_code, status)
                self.assertEqual(caught.exception.provider, "vidbyte")
                self.assertNotIn(VIDBYTE_KEY, str(caught.exception))
                self.assertNotIn(VIDBYTE_KEY, repr(caught.exception.details))
                formatted = "".join(traceback.format_exception(type(caught.exception), caught.exception, caught.exception.__traceback__))
                self.assertNotIn(VIDBYTE_KEY, formatted)

    async def test_managed_malformed_response_redacts_echoed_credentials(self) -> None:
        # [Silent Failure] Normalization details remain useful without preserving a credential echoed in the body.
        payload = {"model": "jev-1.13.0", "answers": {"decision": {"type": "noul", "noul": VIDBYTE_KEY}}}
        transport = ScriptedTransport(managed_response(200, payload))
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            runner = DecisionModelRunner(DecisionModelConfig.vidbyte_managed(), transport=transport)
            with self.assertRaises(ProviderResponseError) as caught:
                await runner.arun(decision_request())
        self.assertNotIn(VIDBYTE_KEY, str(caught.exception))
        self.assertNotIn(VIDBYTE_KEY, repr(caught.exception.details))
        formatted = "".join(traceback.format_exception(type(caught.exception), caught.exception, caught.exception.__traceback__))
        self.assertNotIn(VIDBYTE_KEY, formatted)

    async def test_direct_mode_stays_on_typesafe_and_redirects_remain_disabled(self) -> None:
        # [Hidden Assumption] Managed routing must not silently replace the explicit direct-provider mode.
        body = {"model": "jev-1.13.0", "answers": {"decision": {"type": "noul", "noul": 0.8}}}
        transport = ScriptedTransport(managed_response(200, body))
        config = DecisionModelConfig(api_key=DIRECT_KEY)
        await DecisionModelRunner(config, transport=transport).arun(decision_request())
        self.assertEqual(transport.requests[0]["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertFalse(inspect.signature(HttpTransport.request).parameters["follow_redirects"].default)


class JevFailurePolicyTests(unittest.IsolatedAsyncioTestCase):
    """Checks managed access-denial propagation and the advisory transient fallback at every decision boundary."""

    async def test_access_statuses_fail_closed_but_transient_failures_remain_advisory(self) -> None:
        # [Edge Case] Access and quota responses stop managed use, while transient statuses preserve resilience.
        managed = DecisionModelConfig.vidbyte_managed()
        direct = DecisionModelConfig()
        for status in (401, 402, 403, 429):
            with self.subTest(status=status):
                self.assertTrue(JevDecisionFailurePolicy.should_fail_closed(ProviderRequestError("denied", provider="vidbyte", status_code=status), managed))
        for error in (ProviderRequestError("busy", provider="vidbyte"), ProviderRequestError("busy", provider="vidbyte", status_code=408), ProviderRequestError("busy", provider="vidbyte", status_code=503), ProviderResponseError("malformed", provider="vidbyte"), ConfigurationError("invalid output")):
            with self.subTest(error=type(error).__name__, status=getattr(error, "status_code", None)):
                self.assertFalse(JevDecisionFailurePolicy.should_fail_closed(error, managed))
        self.assertFalse(JevDecisionFailurePolicy.should_fail_closed(ProviderRequestError("denied", provider="typesafe", status_code=403), direct))
        self.assertTrue(JevDecisionFailurePolicy.should_fail_closed(ConfigurationError("missing key", details={"error_kind": "vidbyte_managed_credentials"}), managed))

    async def test_gate_propagates_managed_denial_and_keeps_transient_failure_open(self) -> None:
        # [Hidden Failure] The fixed-question gate must distinguish denied managed access from an outage.
        settings = jev_settings()
        runtime = JevRuntimeSettings(decision=DecisionModelConfig.vidbyte_managed(), preflight=(JevPreflightPreset.CLARITY,))
        gate = JevPreflightGate(settings, runtime, JevResponse())
        for error, denied in ((ProviderRequestError("denied", provider="vidbyte", status_code=403), True), (ProviderRequestError("busy", provider="vidbyte", status_code=503), False)):
            with self.subTest(error=error.status_code), patch("vidbyte.agents.jev.gate.gate.DecisionModelRunner", side_effect=error):
                if denied:
                    with self.assertRaises(ProviderRequestError):
                        await gate._ask("A request")
                else:
                    self.assertIsNone(await gate._ask("A request"))

    async def test_tool_selector_propagates_managed_denial_and_keeps_transient_failure_open(self) -> None:
        # [Hidden Failure] Tool filtering cannot silently turn a managed access denial into the full catalog.
        @tool
        def lookup(query: str) -> str:
            """Look up one record."""
            return query

        catalog = Tools((lookup,))
        selector = JevPreflightTools(DecisionModelConfig.vidbyte_managed(), 0.2)
        for error, denied in ((ProviderRequestError("denied", provider="vidbyte", status_code=402), True), (ProviderRequestError("busy", provider="vidbyte", status_code=503), False)):
            with self.subTest(error=error.status_code), patch("vidbyte.agents.jev.preflight.DecisionModelRunner", side_effect=error):
                if denied:
                    with self.assertRaises(ProviderRequestError):
                        await selector.run("Find a record", catalog)
                else:
                    self.assertIs(await selector.run("Find a record", catalog), catalog)

    async def test_done_check_propagates_managed_denial_and_keeps_transient_failure_open(self) -> None:
        # [Hidden Failure] A done check cannot mark a denied managed decision as merely unavailable.
        fake_state = SimpleNamespace(decision=DecisionModelConfig.vidbyte_managed(), combine=lambda _: decision_request())
        for error, denied in ((ProviderRequestError("denied", provider="vidbyte", status_code=401), True), (ProviderRequestError("busy", provider="vidbyte", status_code=503), False)):
            with self.subTest(error=error.status_code), patch("vidbyte.agents.jev.done.run_state.DecisionModelRunner", side_effect=error):
                if denied:
                    with self.assertRaises(ProviderRequestError):
                        await JevRunState._ask(fake_state, object())  # type: ignore[arg-type]
                else:
                    self.assertIsNone(await JevRunState._ask(fake_state, object()))  # type: ignore[arg-type]

    async def test_disabled_decision_features_do_not_require_a_key(self) -> None:
        # [Hidden Assumption] Constructing or running a disabled decision feature must not resolve credentials.
        with patch.dict(os.environ, {}, clear=True):
            gate = JevPreflightGate(jev_settings(), JevRuntimeSettings(), JevResponse())
            self.assertEqual(await gate._ask("No enabled gate"), {})
            selector = JevPreflightTools(DecisionModelConfig.vidbyte_managed(), 0.2)
            catalog = Tools()
            self.assertIs(await selector.run("No tools", catalog), catalog)
            self.assertIsNone(await JevRunState._ask(SimpleNamespace(decision=DecisionModelConfig.vidbyte_managed()), None))  # type: ignore[arg-type]

    async def test_missing_managed_key_propagates_at_all_decision_boundaries(self) -> None:
        # [Hidden Failure] Missing managed credentials cannot turn any enabled Jev feature into a silent bypass.
        managed = DecisionModelConfig.vidbyte_managed()
        runtime = JevRuntimeSettings(decision=managed, preflight=(JevPreflightPreset.CLARITY,))
        gate = JevPreflightGate(jev_settings(), runtime, JevResponse())

        @tool
        def lookup(query: str) -> str:
            """Look up one record."""
            return query

        selector = JevPreflightTools(managed, 0.2)
        catalog = Tools((lookup,))
        state = SimpleNamespace(decision=managed, combine=lambda _: decision_request())
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "VIDBYTE_API_KEY"):
                await gate._ask("A request")
            with self.assertRaisesRegex(ConfigurationError, "VIDBYTE_API_KEY"):
                await selector.run("Find a record", catalog)
            with self.assertRaisesRegex(ConfigurationError, "VIDBYTE_API_KEY"):
                await JevRunState._ask(state, object())  # type: ignore[arg-type]


__all__ = ["DecisionConfigTests", "JevFailurePolicyTests", "ManagedTransportTests"]
