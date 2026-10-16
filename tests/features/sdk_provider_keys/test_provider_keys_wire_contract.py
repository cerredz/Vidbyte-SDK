"""FILE: tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py

PURPOSE: Proves what a relay call puts on the wire: the X-Vidbyte-Provider-Key header carries exactly the call provider's stripped key and nothing else does; a call with no provider key sends exactly the base_commit managed request; relay calls keep the 32,768 cap and the 630 s floor; and every re-send of one call, and every concurrent call, carries its own Idempotency-Key with identical headers.
ROLE IN CODEBASE: Wire-contract layer of tests/features/sdk_provider_keys/ (spec AC-2, AC-3; INV-2, INV-3, INV-16, INV-20, INV-21; EC-9, EC-14, EC-28, EC-37, EC-38; FR-7). Exercises vidbyte/lib/http/vidbyte_gateway.py (VidbyteGatewayTransport) and vidbyte/lib/runners/text.py through the real adapters in vidbyte/providers/.
ARCHITECTURE NOTE: Each test runs TextModelRunner against a scripted inner transport (managed_text_fixtures.ScriptedGateway), the only fake, and reads what the gateway transport handed it. Retry waits are replaced at SLEEP_TARGET by BackoffRecorder, so re-sends take no wall-clock time.
COMMON MODIFICATION PATTERNS: When the gateway serves a new provider, add its fake key to RELAY_KEYS and its cap field to CAP_FIELD. Keep header comparisons case-insensitive.
WHAT NOT TO DO IN THIS FILE: 1. Do not import the new constants or TextModelMode.DIRECT at module level. 2. Do not compare the relay header with the unstripped input; INV-2 says the value is the stripped key.
KNOWN EDGE CASES: A provider variable holding another vendor's key shape is still that provider's key (EC-14). A NaN timeout must become the 630 s floor on a relay call as on a paid one.
RELATED DOCS: tests/features/sdk_provider_keys/FEATURE.md; docs/spec/byok-api-keys/spec.md sections 6.1 (INV-2, INV-16, INV-20, INV-21) and 9.2 ("Wire").
TESTS: python -m pytest tests/features/sdk_provider_keys/test_provider_keys_wire_contract.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import unittest
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    GATEWAY_URL,
    MANAGED_MODELS,
    SLEEP_TARGET,
    VIDBYTE_KEY,
    BackoffRecorder,
    ScriptedGateway,
    edge_page,
    gateway_error,
    header,
    idempotency_key,
    provider_answer,
    relayed_provider_error,
)
from tests.features.sdk_provider_keys.provider_keys_fixtures import (
    K_ANTHROPIC,
    K_GEMINI_AQ,
    K_OPENAI,
    K_UNPROVEN,
    K_UNPROVEN_2,
    K_XAI,
    RELAY_HEADER,
    flat,
    provider_key_header,
)
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner

PAID_HEADERS = {"authorization", "content-type", "idempotency-key"}
RELAY_HEADERS = PAID_HEADERS | {RELAY_HEADER.lower()}
KEY_PATTERN = re.compile(r"[0-9a-f]{32}")
# One fake key per served provider; deepseek and kimi keys are unproven and bind as the list's only key (D-29).
RELAY_KEYS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI: K_OPENAI,
    ModelProvider.ANTHROPIC: K_ANTHROPIC,
    ModelProvider.GEMINI: K_GEMINI_AQ,
    ModelProvider.XAI: K_XAI,
    ModelProvider.DEEPSEEK: K_UNPROVEN,
    ModelProvider.KIMI: K_UNPROVEN_2,
}
# The cap field each dialect uses (managed-generative-models spec section 9.2), Gemini's sits in generationConfig.
CAP_FIELD = {ModelProvider.OPENAI: "max_output_tokens", ModelProvider.ANTHROPIC: "max_tokens", ModelProvider.XAI: "max_tokens", ModelProvider.DEEPSEEK: "max_tokens", ModelProvider.KIMI: "max_tokens"}


def gateway_call(provider: ModelProvider, environment: dict[str, str], *steps: HttpResponse, run_options: dict[str, Any] | None = None, **config_options: Any) -> tuple[ScriptedGateway, BackoffRecorder, Any]:
    # Runs one default-mode call with a cleared environment and returns the recorder, the waits, and the answer or the raised error.
    transport = ScriptedGateway(*(steps or (provider_answer(provider),)))
    backoff = BackoffRecorder()
    with patch.dict(os.environ, environment, clear=True), patch(SLEEP_TARGET, new=backoff):
        runner = TextModelRunner(TextModelConfig(provider=provider.value, model=MANAGED_MODELS[provider], **config_options), transport=transport)
        try:
            result: Any = runner.run("Hi", **(run_options or {}))
        except ProviderRequestError as error:
            result = error
    return transport, backoff, result


def direct_body(provider: ModelProvider, **config_options: Any) -> dict[str, Any]:
    # The body the same config sends straight to the vendor in DIRECT: the oracle for the relay envelope's body (AC-2).
    from vidbyte.lib.config import TextModelMode

    transport = ScriptedGateway(provider_answer(provider))
    with patch.dict(os.environ, {}, clear=True):
        TextModelRunner(TextModelConfig(provider=provider.value, model=MANAGED_MODELS[provider], api_keys=[RELAY_KEYS[provider]], mode=TextModelMode.DIRECT, **config_options), transport=transport).run("Hi")
    return transport.requests[0]["json_body"]


def with_cap(provider: ModelProvider, body: dict[str, Any], cap: int) -> dict[str, Any]:
    # The DIRECT body with the gateway's output cap set in the dialect's own field.
    capped = json.loads(json.dumps(body))
    if provider is ModelProvider.GEMINI:
        capped.setdefault("generationConfig", {})["maxOutputTokens"] = cap
    else:
        capped[CAP_FIELD[provider]] = cap
    return capped


def header_names(request: dict[str, Any]) -> set[str]:
    # The request's header names, lower-cased, since HTTP header names are case-insensitive.
    return {name.lower() for name in request["headers"]}


class RelayHeaderTests(unittest.TestCase):
    """AC-2, AC-3, INV-2, INV-3, INV-16: the header is present exactly when the call has a provider key, and the key goes nowhere else."""

    def test_each_served_provider_relays_its_own_key_in_the_header_and_nowhere_else(self) -> None:
        # INV-2, FR-7: one POST to the gateway; the key is absent from the URL, the envelope, Authorization and Idempotency-Key.
        for provider, key in RELAY_KEYS.items():
            with self.subTest(provider=provider.value):
                transport, _, _ = gateway_call(provider, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, api_keys=[key])
                [sent] = transport.requests
                self.assertEqual(sent["method"], "POST")
                self.assertEqual(sent["url"], GATEWAY_URL)
                self.assertEqual(header_names(sent), RELAY_HEADERS)
                self.assertEqual(provider_key_header(sent), key)
                self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
                self.assertEqual(sent["json_body"]["provider"], provider.value)
                elsewhere = {name: value for name, value in sent["headers"].items() if name.lower() != RELAY_HEADER.lower()}
                self.assertNotIn(key, flat({"url": sent["url"], "headers": elsewhere, "json_body": sent["json_body"], "idempotency_key": sent.get("idempotency_key")}))

    def test_the_relay_envelope_body_is_the_direct_body_with_the_gateway_cap(self) -> None:
        # AC-2, INV-20: the provider key changes only the header; the body is what DIRECT sends plus the 32,768 cap, as a Vidbyte-paid call's is.
        for provider, key in RELAY_KEYS.items():
            with self.subTest(provider=provider.value):
                relay, _, _ = gateway_call(provider, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, api_keys=[key])
                paid, _, _ = gateway_call(provider, {"VIDBYTE_API_KEY": VIDBYTE_KEY})
                expected = with_cap(provider, direct_body(provider), 32768)
                self.assertEqual(relay.requests[0]["json_body"], {"provider": provider.value, "model": MANAGED_MODELS[provider], "body": expected})
                self.assertEqual(relay.requests[0]["json_body"], paid.requests[0]["json_body"])

    def test_the_header_carries_the_stripped_key_from_the_list_or_the_environment(self) -> None:
        # INV-2, EC-9: padding and a trailing newline are removed before the value reaches the header.
        cases = (
            ("list entry", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {"api_keys": [f"  {K_OPENAI}\n"]}),
            ("environment", {"VIDBYTE_API_KEY": VIDBYTE_KEY, "OPENAI_API_KEY": f"\t{K_OPENAI}  \n"}, {}),
        )
        for label, environment, options in cases:
            with self.subTest(source=label):
                transport, _, _ = gateway_call(ModelProvider.OPENAI, environment, **options)
                self.assertEqual(provider_key_header(transport.requests[0]), K_OPENAI)

    def test_a_call_without_a_provider_key_sends_exactly_the_three_base_commit_headers(self) -> None:
        # AC-3, INV-16: no key, a blank variable, or only another provider's key all give the Vidbyte-paid request; the header is never empty.
        cases = (
            ("no key", {"VIDBYTE_API_KEY": VIDBYTE_KEY}, {}),
            ("blank variable", {"VIDBYTE_API_KEY": VIDBYTE_KEY, "OPENAI_API_KEY": "   "}, {}),
            ("Vidbyte entry only", {}, {"api_keys": [VIDBYTE_KEY]}),
        )
        for label, environment, options in cases:
            with self.subTest(case=label):
                transport, _, _ = gateway_call(ModelProvider.OPENAI, environment, **options)
                [sent] = transport.requests
                self.assertEqual(sent["url"], GATEWAY_URL)
                self.assertEqual(header_names(sent), PAID_HEADERS)
                self.assertEqual(header(sent, "authorization"), f"Bearer {VIDBYTE_KEY}")
                self.assertRegex(idempotency_key(sent) or "", KEY_PATTERN)
                self.assertEqual(sent["timeout_seconds"], 630.0)

    def test_a_key_for_another_provider_is_never_sent_with_this_call(self) -> None:
        # INV-3: a proven xAI key in the list binds to xai, so an openai call relays only the OpenAI key.
        transport, _, _ = gateway_call(ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, api_keys=[K_XAI, K_OPENAI, K_ANTHROPIC])
        [sent] = transport.requests
        self.assertEqual(provider_key_header(sent), K_OPENAI)
        self.assertNotIn(K_XAI, flat(sent))
        self.assertNotIn(K_ANTHROPIC, flat(sent))

    def test_a_provider_variable_is_trusted_by_its_name(self) -> None:
        # EC-14: OPENAI_API_KEY holding an xAI-shaped value is relayed as the OpenAI key; environment values are never matched.
        transport, _, _ = gateway_call(ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY, "OPENAI_API_KEY": K_XAI})
        self.assertEqual(provider_key_header(transport.requests[0]), K_XAI)
        self.assertEqual(transport.requests[0]["json_body"]["provider"], "openai")

    def test_an_adapter_called_directly_in_auto_sees_only_the_placeholder(self) -> None:
        # EC-37, INV-4, D-8: outside a runner, a gateway-mode adapter builds its own headers from the non-secret placeholder.
        from vidbyte.providers.anthropic import AnthropicProvider

        transport = ScriptedGateway(provider_answer(ModelProvider.ANTHROPIC))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": K_ANTHROPIC, "VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            adapter = AnthropicProvider(model="claude-sonnet-5", api_keys=[K_ANTHROPIC])
            asyncio.run(adapter.run_text(prompt="Hi", system=None, metadata=None, transport=transport))
        [sent] = transport.requests
        self.assertEqual(header(sent, "x-api-key"), "vidbyte-managed")
        self.assertNotIn(K_ANTHROPIC, flat(sent))
        self.assertNotIn(VIDBYTE_KEY, flat(sent))


class RelayCapAndFloorTests(unittest.TestCase):
    """INV-20: a relay call gets the same output cap and timeout floor as a Vidbyte-paid call."""

    def test_a_relay_body_carries_the_default_cap_or_the_callers_exact_value(self) -> None:
        # INV-20: 100 catches max(N, 32768) and 40,000 catches min(N, 32768), in each dialect's own field.
        for provider, key in RELAY_KEYS.items():
            for requested, expected in ((None, 32768), (100, 100), (40_000, 40_000)):
                with self.subTest(provider=provider.value, max_output_tokens=requested):
                    transport, _, _ = gateway_call(provider, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, api_keys=[key], max_output_tokens=requested)
                    body = transport.requests[0]["json_body"]["body"]
                    cap = body.get("generationConfig", {}).get("maxOutputTokens") if provider is ModelProvider.GEMINI else body.get(CAP_FIELD[provider])
                    self.assertIs(type(cap), int)
                    self.assertEqual(cap, expected)
                    self.assertEqual(provider_key_header(transport.requests[0]), key)

    def test_each_relay_attempt_gets_the_630_second_floor_and_a_nan_timeout_becomes_the_floor(self) -> None:
        # INV-20, INV-16: the floor is keyed on the gateway, not on who pays.
        for requested, expected in ((60.0, 630.0), (30.0, 630.0), (900.0, 900.0), (float("nan"), 630.0)):
            with self.subTest(timeout_seconds=requested):
                transport, _, _ = gateway_call(ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, api_keys=[K_OPENAI], timeout_seconds=requested)
                self.assertEqual(provider_key_header(transport.requests[0]), K_OPENAI)
                self.assertEqual(transport.requests[0]["timeout_seconds"], expected)


class RelayResendTests(unittest.TestCase):
    """INV-21, EC-28: every attempt of one relay call carries the same Idempotency-Key and identical headers."""

    def assert_one_call(self, transport: ScriptedGateway, attempts: int) -> None:
        # The same key, the same headers (the provider key among them), and the same envelope on every attempt.
        self.assertEqual(len(transport.requests), attempts)
        first = transport.requests[0]
        self.assertRegex(idempotency_key(first) or "", KEY_PATTERN)
        for request in transport.requests:
            self.assertEqual(request["url"], GATEWAY_URL)
            self.assertEqual(request["headers"], first["headers"])
            self.assertEqual(provider_key_header(request), K_OPENAI)
            self.assertEqual(json.dumps(request["json_body"], sort_keys=True), json.dumps(first["json_body"], sort_keys=True))
            self.assertEqual(request.get("retry_count", 0), 0)

    def test_a_retried_relay_call_re_sends_the_same_key_and_headers(self) -> None:
        # EC-28: a 502, a 409 and an edge page are each re-sent; a header that changed between attempts would bill or refuse a replay.
        scripts = (
            ("502 then 200", (gateway_error(502), provider_answer(ModelProvider.OPENAI, "Recovered")), 2, [0.5]),
            ("edge page then 409 then 200", (edge_page(503, "<html>busy</html>"), gateway_error(409), provider_answer(ModelProvider.OPENAI, "Recovered")), 3, [0.5, 1.0]),
            ("relayed 502 then 200", (relayed_provider_error(ModelProvider.OPENAI, 502), provider_answer(ModelProvider.OPENAI, "Recovered")), 2, [0.5]),
        )
        for label, steps, attempts, delays in scripts:
            with self.subTest(label):
                transport, backoff, result = gateway_call(ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, *steps, api_keys=[K_OPENAI])
                self.assertNotIsInstance(result, ProviderRequestError)
                self.assertEqual(result.text, "Recovered")
                self.assert_one_call(transport, attempts)
                self.assertEqual(backoff.delays, delays)

    def test_a_relay_502_that_never_recovers_is_sent_three_times_with_one_key(self) -> None:
        # INV-21, EC-27: the existing re-send policy, unchanged by the relay.
        transport, backoff, result = gateway_call(ModelProvider.OPENAI, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, gateway_error(502), api_keys=[K_OPENAI])
        self.assertIsInstance(result, ProviderRequestError)
        self.assert_one_call(transport, 3)
        self.assertEqual(backoff.delays, [0.5, 1.0])


class PerCallGateway:
    """Answers 502 to the first attempt of each Idempotency-Key and 200 to the second, echoing that call's prompt."""

    def __init__(self) -> None:
        # Records every attempt; the answer depends only on how often its key was seen.
        self.requests: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> HttpResponse:
        # A key seen once before gets the success answer, so a key shared across calls changes what callers receive.
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        seen = sum(1 for request in self.requests if idempotency_key(request) == idempotency_key(kwargs))
        if seen == 1:
            return gateway_error(502)
        return provider_answer(ModelProvider.OPENAI, kwargs["json_body"]["body"]["input"])


class ConcurrentRelayTests(unittest.IsolatedAsyncioTestCase):
    """EC-38, INV-21: concurrent relay calls on one runner share no state."""

    async def test_concurrent_relay_calls_keep_their_own_idempotency_keys_and_the_same_provider_key(self) -> None:
        # EC-38: a key stored on the runner would let one call's retry carry another call's Idempotency-Key.
        transport = PerCallGateway()
        prompts = [f"prompt-{index}" for index in range(4)]
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True), patch(SLEEP_TARGET, new=BackoffRecorder()):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5", api_keys=[K_OPENAI]), transport=transport)
            responses = await asyncio.gather(*(runner.arun(prompt) for prompt in prompts))
        self.assertEqual([response.text for response in responses], prompts)
        self.assertEqual(len(transport.requests), 8)
        self.assertEqual(len({idempotency_key(request) for request in transport.requests[:4]}), 4)
        groups: dict[str, list[dict[str, Any]]] = {}
        for request in transport.requests:
            self.assertEqual(provider_key_header(request), K_OPENAI)
            groups.setdefault(idempotency_key(request) or "", []).append(request)
        self.assertEqual(len(groups), 4)
        for group in groups.values():
            self.assertEqual(len(group), 2)
            self.assertEqual(group[0]["headers"], group[1]["headers"])
            self.assertEqual(group[0]["json_body"], group[1]["json_body"])


if __name__ == "__main__":
    unittest.main()
