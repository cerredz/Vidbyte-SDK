"""FILE: tests/features/sdk_managed_text/test_managed_text_failures.py

PURPOSE: Proves how a managed call fails and retries: every failure is a credential-safe ProviderRequestError(provider="vidbyte") carrying no body text, and only a 409, a 502 or a non-JSON-object answer is re-sent, at most twice, with one Idempotency-Key and one envelope.
ROLE IN CODEBASE: Failure and retry layer of tests/features/sdk_managed_text/ (spec INV-11, INV-16, D-10, D-17; AC-10..AC-12, AC-20, AC-25, AC-27; EC-10..EC-15, EC-24, EC-25). Exercises VidbyteGatewayTransport in vidbyte/lib/http/vidbyte_gateway.py through TextModelRunner.
ARCHITECTURE NOTE: The inner transport is scripted with gateway and provider bodies that carry BODY_CANARY and a key-shaped LEAKED_KEY; finding either in an error's message, details or formatted traceback means body text leaked. The retry wait is replaced at SLEEP_TARGET by BackoffRecorder, so retries take no wall-clock time and their delays are recorded.
COMMON MODIFICATION PATTERNS: Add a status to the tables when the gateway gains one; keep remedy patterns to the facts section 9.2 binds, because the exact wording is the implementer's.
WHAT NOT TO DO IN THIS FILE: 1. Do not import feature symbols at module level (see managed_text_fixtures.py). 2. Do not let the real asyncio.sleep run in a retry test; it would add 1.5 s per case. 3. Do not catch BaseException in a helper; cancellation must reach the assertion.
KNOWN EDGE CASES: A 200 whose body is an HTML page, an empty string, a JSON array, null or truncated JSON is an edge failure, not a success. A relayed vendor body nests an object under "error", which is not the gateway's "error": true.
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; docs/spec/managed-generative-models/spec.md section 9.2 ("Failure mapping", "Retries", "Raise shape").
TESTS: python -m pytest tests/features/sdk_managed_text/test_managed_text_failures.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import traceback
import unittest
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    BODY_CANARY,
    GATEWAY_URL,
    LEAKED_KEY,
    MANAGED_MODELS,
    SLEEP_TARGET,
    VIDBYTE_KEY,
    BackoffRecorder,
    ScriptedGateway,
    edge_page,
    gateway_error,
    idempotency_key,
    provider_answer,
    provider_usage,
    relayed_provider_error,
)
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner

MANAGED_ONLY = {"VIDBYTE_API_KEY": VIDBYTE_KEY}
KEY_PATTERN = re.compile(r"[0-9a-f]{32}")
NO_WAITS: list[float] = []
RETRY_WAITS = [0.5, 1.0]
HTML_PAGE = f"<html><body><h1>502 Bad Gateway</h1>{BODY_CANARY} {LEAKED_KEY}</body></html>"


class ManagedCall:
    """One managed call with only VIDBYTE_API_KEY set, its scripted inner transport, and its recorded retry waits."""

    def __init__(self, *steps: HttpResponse | BaseException, provider: ModelProvider = ModelProvider.OPENAI) -> None:
        # Holds the script and the provider; the call itself runs in run().
        self.transport = ScriptedGateway(*steps)
        self.backoff = BackoffRecorder()
        self.provider = provider

    def run(self) -> Any:
        # Runs the call and returns the response, or the ProviderRequestError it raised.
        with patch.dict(os.environ, MANAGED_ONLY, clear=True), patch(SLEEP_TARGET, new=self.backoff):
            runner = TextModelRunner(TextModelConfig(provider=self.provider.value, model=MANAGED_MODELS[self.provider]), transport=self.transport)
            try:
                return runner.run("Hi")
            except ProviderRequestError as error:
                return error


class CredentialSafeAssertions(unittest.TestCase):
    """Shared assertions for the D-17 raise shape; holds no tests of its own."""

    def assert_credential_safe(self, error: Any, *, status: int | None, provider: ModelProvider = ModelProvider.OPENAI) -> str:
        # INV-6, INV-11, D-17: provider "vidbyte", the status, no excerpt, no chained exception, and no body text anywhere a log could print.
        self.assertIsInstance(error, ProviderRequestError)
        self.assertEqual(error.provider, "vidbyte")
        self.assertEqual(error.status_code, status)
        self.assertIsNone(error.response_excerpt)
        self.assertNotIn("response_excerpt", error.details)
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        message = str(error)
        rendered = message + repr(error.details) + "".join(traceback.format_exception(type(error), error, error.__traceback__))
        for secret in (BODY_CANARY, LEAKED_KEY, VIDBYTE_KEY, "model_gateway_refused"):
            self.assertNotIn(secret, rendered)
        # INV-11: the SDK's own message names the provider and, when an answer arrived, its status.
        self.assertIn(provider.value, message)
        if status is not None:
            self.assertIn(str(status), message)
        return message

    def assert_one_key_and_one_envelope(self, transport: ScriptedGateway, attempts: int) -> None:
        # INV-16, AC-27: every attempt of one call is the same POST with the same key in header and argument, the floor timeout, and no inner retries.
        self.assertEqual(len(transport.requests), attempts)
        first = transport.requests[0]
        key = idempotency_key(first)
        self.assertIsNotNone(key)
        self.assertRegex(key or "", KEY_PATTERN)
        self.assertEqual(len(key or ""), 32)
        for request in transport.requests:
            self.assertEqual(request["method"], "POST")
            self.assertEqual(request["url"], GATEWAY_URL)
            self.assertEqual(idempotency_key(request), key)
            self.assertEqual(request["headers"], first["headers"])
            self.assertEqual(request.get("idempotency_key"), key)
            self.assertEqual(json.dumps(request["json_body"], sort_keys=True), json.dumps(first["json_body"], sort_keys=True))
            self.assertEqual(request.get("retry_count", 0), 0)
            self.assertEqual(request["timeout_seconds"], 630.0)


class GatewayErrorTests(CredentialSafeAssertions):
    """Checks INV-11 rows 5 and 6: gateway errors and relayed provider errors, with the facts each message must state."""

    def test_gateway_errors_raise_credential_safe_errors_after_one_post_or_three_for_a_502(self) -> None:
        # AC-10, AC-27 (c)(d), EC-13: the body echoes a key and a canary; only 502 is re-sent, twice, after 0.5 s and 1.0 s.
        for status in (401, 402, 403, 413, 422, 429, 500, 502, 503):
            with self.subTest(status=status):
                call = ManagedCall(gateway_error(status))
                self.assert_credential_safe(call.run(), status=status)
                attempts = 3 if status == 502 else 1
                self.assert_one_key_and_one_envelope(call.transport, attempts)
                self.assertEqual(call.backoff.delays, RETRY_WAITS if status == 502 else NO_WAITS)

    def test_gateway_error_messages_state_the_remedy_section_9_2_binds_for_each_status(self) -> None:
        # Section 9.2 row 5, EC-10, EC-11, EC-13: the wording is the implementer's, these facts are not; 409 is re-sent before it is raised.
        remedies = {
            401: ("VIDBYTE_API_KEY",),
            402: ("wallet", "provider key"),
            403: ("models:invoke",),
            409: ("still", "bill", "wait"),
            413: ("2,?000,?000",),
            422: ("stream", "service.?tier", "snake.?case"),
            429: ("quota", "daily"),
            500: ("unavailable",),
            502: ("unavailable", "re-?sent|retr"),
            503: ("unavailable",),
        }
        for status, patterns in remedies.items():
            with self.subTest(status=status):
                call = ManagedCall(gateway_error(status))
                message = self.assert_credential_safe(call.run(), status=status)
                for pattern in patterns:
                    self.assertRegex(message, re.compile(pattern, re.IGNORECASE))
                self.assertEqual(len(call.transport.requests), 3 if status in (409, 502) else 1)

    def test_relayed_provider_errors_name_the_provider_and_status_and_withhold_its_message(self) -> None:
        # AC-11, EC-12, AC-27 (d): a vendor {"error": {...}} is not the gateway's "error": true, so it must not get a gateway remedy (a quota message for 429).
        for provider, status in ((ModelProvider.ANTHROPIC, 400), (ModelProvider.OPENAI, 429), (ModelProvider.GEMINI, 400)):
            with self.subTest(provider=provider.value, status=status):
                call = ManagedCall(relayed_provider_error(provider, status), provider=provider)
                message = self.assert_credential_safe(call.run(), status=status, provider=provider)
                self.assertRegex(message, re.compile("withheld", re.IGNORECASE))
                self.assertRegex(message, re.compile(r"(not|n't)\b[^.]{0,20}bill", re.IGNORECASE))
                self.assertNotRegex(message, re.compile("quota|daily|wallet", re.IGNORECASE))
                self.assert_one_key_and_one_envelope(call.transport, 1)
                self.assertEqual(call.backoff.delays, NO_WAITS)


class TransportFailureTests(CredentialSafeAssertions):
    """Checks INV-11 rows 1 to 3: no response, an unexpected exception, and an answer from the hosting edge."""

    def test_a_missing_response_is_raised_after_one_post_and_says_vidbyte_may_already_have_billed(self) -> None:
        # AC-12 (a), AC-27 (e), EC-14: a network failure is never retried (a retry could stack a second 630 s wait); its excerpt must not leak.
        dropped = ProviderRequestError("connection reset", provider="http", response_excerpt=f"{BODY_CANARY} {LEAKED_KEY}")
        call = ManagedCall(dropped)
        message = self.assert_credential_safe(call.run(), status=None)
        self.assertRegex(message, re.compile(r"no (response|answer)|did ?n[o']t (receive|get) (a|an|any) (response|answer)", re.IGNORECASE))
        self.assertRegex(message, re.compile("bill", re.IGNORECASE))
        self.assertIn("630", message)
        self.assert_one_key_and_one_envelope(call.transport, 1)
        self.assertEqual(call.backoff.delays, NO_WAITS)

    def test_an_unexpected_exception_is_raised_once_without_any_of_its_text(self) -> None:
        # AC-25 (a): a TypeError from encoding a body value could carry user data; neither its text nor the exception may survive.
        call = ManagedCall(TypeError(f"Object of type bytes is not JSON serializable: {BODY_CANARY} {LEAKED_KEY}"))
        message = self.assert_credential_safe(call.run(), status=None)
        self.assertNotIn("JSON serializable", message)
        self.assertNotIn("TypeError", message)
        self.assert_one_key_and_one_envelope(call.transport, 1)
        self.assertEqual(call.backoff.delays, NO_WAITS)

    def test_an_answer_that_is_not_a_json_object_is_retried_then_raised_as_a_transient_edge_failure(self) -> None:
        # AC-12 (b), EC-15: a 200 HTML page must never reach the adapter, whose parse error would copy the page into response_excerpt.
        pages = (
            (200, HTML_PAGE),
            (502, HTML_PAGE),
            (503, HTML_PAGE),
            (200, ""),
            (200, json.dumps([BODY_CANARY, LEAKED_KEY])),
            (200, "null"),
            (200, '{"error": true, "message": "' + BODY_CANARY),
            (504, f"{BODY_CANARY} upstream request timeout"),
        )
        for status, body in pages:
            with self.subTest(status=status, body=body[:16]):
                call = ManagedCall(edge_page(status, body))
                message = self.assert_credential_safe(call.run(), status=status)
                for pattern in ("edge", "re-?sent|retr", "transient"):
                    self.assertRegex(message, re.compile(pattern, re.IGNORECASE))
                self.assertNotIn("<html", message.lower())
                self.assert_one_key_and_one_envelope(call.transport, 3)
                self.assertEqual(call.backoff.delays, RETRY_WAITS)


class SameKeyRetryTests(CredentialSafeAssertions):
    """Checks INV-16 and D-10: a retryable answer is re-sent with the same key until a 2xx JSON object comes back."""

    def test_a_retryable_answer_followed_by_success_returns_the_provider_answer_unchanged(self) -> None:
        # AC-27 (a)(b): a fresh key per attempt would make the gateway bill each attempt; the 200 must reach the adapter untouched.
        scripts = (
            ("502 gateway error, then 200", (gateway_error(502), provider_answer(ModelProvider.OPENAI, "Recovered")), 2, [0.5]),
            ("503 HTML page, then 409 gateway error, then 200", (edge_page(503, HTML_PAGE), gateway_error(409), provider_answer(ModelProvider.OPENAI, "Recovered")), 3, RETRY_WAITS),
            ("relayed provider 409, then 200", (relayed_provider_error(ModelProvider.OPENAI, 409), provider_answer(ModelProvider.OPENAI, "Recovered")), 2, [0.5]),
            ("relayed provider 502, then 200", (relayed_provider_error(ModelProvider.OPENAI, 502), provider_answer(ModelProvider.OPENAI, "Recovered")), 2, [0.5]),
        )
        for label, steps, attempts, delays in scripts:
            with self.subTest(label):
                call = ManagedCall(*steps)
                response = call.run()
                self.assertNotIsInstance(response, ProviderRequestError)
                self.assertEqual(response.text, "Recovered")
                self.assertEqual(response.usage, provider_usage(ModelProvider.OPENAI))
                self.assert_one_key_and_one_envelope(call.transport, attempts)
                self.assertEqual(call.backoff.delays, delays)


class PerKeyGateway:
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


class OneKeyPerCallTests(unittest.IsolatedAsyncioTestCase):
    """Checks INV-16 across calls: separate calls never share a key, and cancellation is never turned into a provider error."""

    async def test_two_identical_calls_on_one_runner_send_two_different_keys(self) -> None:
        # AC-20, EC-25: content-addressed or runner-level keys would replay the first answer for the second, deliberate call.
        transport = ScriptedGateway(provider_answer(ModelProvider.OPENAI, "first"), provider_answer(ModelProvider.OPENAI, "second"))
        with patch.dict(os.environ, MANAGED_ONLY, clear=True), patch(SLEEP_TARGET, new=BackoffRecorder()):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport)
            texts = [(await runner.arun("Same prompt")).text, (await runner.arun("Same prompt")).text]
        self.assertEqual(texts, ["first", "second"])
        keys = [idempotency_key(request) for request in transport.requests]
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[0], keys[1])
        for request, key in zip(transport.requests, keys, strict=True):
            self.assertRegex(key or "", KEY_PATTERN)
            self.assertEqual(request.get("idempotency_key"), key)

    async def test_concurrent_calls_each_keep_their_own_key_across_their_own_retries(self) -> None:
        # EC-24: a key stored on the runner or a shared transport would let one call's retry carry another call's key.
        transport = PerKeyGateway()
        prompts = [f"prompt-{index}" for index in range(4)]
        with patch.dict(os.environ, MANAGED_ONLY, clear=True), patch(SLEEP_TARGET, new=BackoffRecorder()):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport)
            responses = await asyncio.gather(*(runner.arun(prompt) for prompt in prompts))
        self.assertEqual([response.text for response in responses], prompts)
        self.assertEqual(len(transport.requests), 8)
        # The first four POSTs come from four different calls, which proves the calls overlapped at the retry wait.
        self.assertEqual(len({idempotency_key(request) for request in transport.requests[:4]}), 4)
        by_key: dict[str, list[dict[str, Any]]] = {}
        for request in transport.requests:
            by_key.setdefault(idempotency_key(request) or "", []).append(request)
        self.assertEqual(len(by_key), 4)
        self.assertEqual(sorted(group[0]["json_body"]["body"]["input"] for group in by_key.values()), prompts)
        for group in by_key.values():
            self.assertEqual(len(group), 2)
            self.assertEqual(group[0]["json_body"], group[1]["json_body"])

    async def test_cancellation_from_the_send_or_the_retry_wait_propagates_unchanged(self) -> None:
        # AC-25 (b), S019: catching BaseException would turn an agent's cancellation into a provider error and keep a cancelled task alive.
        cancelled = asyncio.CancelledError()
        transport = ScriptedGateway(cancelled)
        with patch.dict(os.environ, MANAGED_ONLY, clear=True), patch(SLEEP_TARGET, new=BackoffRecorder()):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport)
            with self.assertRaises(asyncio.CancelledError) as caught:
                await runner.arun("Hi")
        self.assertIs(caught.exception, cancelled)
        self.assertEqual(len(transport.requests), 1)

        during_wait = asyncio.CancelledError()
        backoff = BackoffRecorder(cancel_with=during_wait)
        transport = ScriptedGateway(gateway_error(502), provider_answer(ModelProvider.OPENAI))
        with patch.dict(os.environ, MANAGED_ONLY, clear=True), patch(SLEEP_TARGET, new=backoff):
            runner = TextModelRunner(TextModelConfig(provider="openai", model="gpt-5.5"), transport=transport)
            with self.assertRaises(asyncio.CancelledError) as caught:
                await runner.arun("Hi")
        self.assertIs(caught.exception, during_wait)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(backoff.delays, [0.5])


if __name__ == "__main__":
    unittest.main()
