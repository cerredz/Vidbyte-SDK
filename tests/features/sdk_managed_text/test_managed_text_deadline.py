"""FILE: tests/features/sdk_managed_text/test_managed_text_deadline.py

PURPOSE: Proves the r5 retry deadline and the last-attempt rule of a managed call: re-sends share one cumulative deadline taken from the event-loop clock before the first POST, each attempt keeps the full 630 s timeout, the error states how many re-sends the call made, and the last attempt's outcome decides the error. Also proves that a direct TextModelConfig.validate() refuses the managed shapes the gateway cannot serve.
ROLE IN CODEBASE: Deadline layer of tests/features/sdk_managed_text/ (spec INV-10, INV-16, EC-38, section 9.2 "Retries"; EC-3 and EC-7 for the direct validate() calls). Drives VidbyteGatewayTransport in vidbyte/lib/http/vidbyte_gateway.py directly, without the runner, and TextModelConfig.validate in vidbyte/lib/dataclasses/model_configs.py.
ARCHITECTURE NOTE: For one call, the gateway module's asyncio name is replaced by a namespace whose get_running_loop returns FakeLoopClock. Its time() is the loop time the deadline reads, its sleep() records each retry wait and advances the clock by it, and SlowGateway advances the clock by a fixed step per attempt. Against the 630 s timeout, steps of 0, 600 and 629.5 s give 3, 2 and 1 POSTs. 629.5 + 0.5 lands exactly on the deadline in binary floating point, so the last case pins the >= comparison.
COMMON MODIFICATION PATTERNS: When the retry waits or the 630 s floor change, move the step values so each case still lands on its boundary, and keep one case exactly on the deadline. Keep message checks to the facts section 9.2 binds: the re-send count, or that no re-send was made.
WHAT NOT TO DO IN THIS FILE: 1. Do not patch asyncio globally or asyncio.get_running_loop itself; asyncio.run in this file needs the real loop, so patch only the gateway module's asyncio attribute. 2. Do not swap the fake clock for a real one with short timeouts; no real step lands exactly on the deadline, so a > comparison, a deadline taken after the first POST and a shortened attempt would all pass. 3. Do not import feature symbols at module level (see managed_text_fixtures.py).
KNOWN EDGE CASES: A deadline taken after the first POST gives the 600 s case a third POST. A > comparison gives the 629.5 s case a second POST. A deadline that ignores the loop clock is caught because the clock starts at 1000 s, not 0. A shortened attempt shows as a timeout_seconds below 630.0. Since byok-api-keys (D-23), AUTO always means the gateway, so TextModelConfig refuses an endpoint or an unserved provider when it is built, before any environment is read.
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; docs/spec/managed-generative-models/spec.md INV-10, INV-16, EC-3, EC-7, EC-38 and section 9.2 ("Retries").
TESTS: python -m pytest tests/features/sdk_managed_text/test_managed_text_deadline.py
"""

from __future__ import annotations

import asyncio
import os
import re
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    GATEWAY_URL,
    VIDBYTE_KEY,
    ScriptedGateway,
    gateway_error,
    idempotency_key,
)
from vidbyte.lib.config import TextModelConfig
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import (
    ConfigurationError,
    ProviderRequestError,
    UnsupportedProviderError,
)
from vidbyte.lib.http import HttpResponse

# The floored per-attempt timeout the runner hands the gateway transport (INV-10).
FLOOR_TIMEOUT = 630.0
# The loop time at the first POST; not 0, so a deadline that ignores the loop clock fails.
CLOCK_START = 1000.0
# What the OpenAI adapter would have sent to its vendor; the gateway transport must drop the URL and headers.
VENDOR_URL = "https://api.openai.com/v1/responses"
VENDOR_HEADERS = {"authorization": "Bearer vidbyte-managed"}
ADAPTER_BODY = {"model": "gpt-5.5", "input": "Hi", "max_output_tokens": 8192}
MANAGED_PROVIDERS = ("openai", "anthropic", "gemini", "xai", "deepseek", "kimi")


class FakeLoopClock:
    """Stands in for the event loop the gateway reads: time() is the loop clock, and sleep() records each retry wait and moves the clock past it."""

    def __init__(self) -> None:
        # Starts the clock away from zero and with no waits recorded.
        self.now = CLOCK_START
        self.waits: list[float] = []

    def time(self) -> float:
        # The loop time the gateway reads for its deadline and before each wait.
        return self.now

    async def sleep(self, delay: float, result: object = None) -> object:
        # Records the wait and advances the clock by it, without waiting.
        self.waits.append(delay)
        self.now += delay
        return result


class SlowGateway(ScriptedGateway):
    """ScriptedGateway whose every attempt spends `step` seconds of loop time before it answers."""

    def __init__(self, clock: FakeLoopClock, step: float, *steps: HttpResponse | BaseException) -> None:
        # Keeps the clock to advance and the script to answer from.
        super().__init__(*steps)
        self.clock = clock
        self.step = step

    async def request(self, **kwargs: Any) -> HttpResponse:
        # The attempt takes its step of loop time, then records and answers like ScriptedGateway.
        self.clock.now += self.step
        return await super().request(**kwargs)


class GatewayCall:
    """One call straight into VidbyteGatewayTransport under the fake loop clock, with its recorded attempts and waits."""

    def __init__(self, step: float, *steps: HttpResponse | BaseException) -> None:
        # Builds the clock and the slow scripted inner transport; the call itself runs in run().
        self.clock = FakeLoopClock()
        self.transport = SlowGateway(self.clock, step, *steps)

    def run(self) -> Any:
        # Runs the call with the floored timeout and returns the response, or the ProviderRequestError it raised.
        import vidbyte.lib.http.vidbyte_gateway as gateway_module

        gateway = gateway_module.VidbyteGatewayTransport(self.transport, provider=ModelProvider.OPENAI, model="gpt-5.5", api_key=VIDBYTE_KEY)
        fake_asyncio = SimpleNamespace(get_running_loop=lambda: self.clock, sleep=self.clock.sleep)
        with patch.object(gateway_module, "asyncio", fake_asyncio):
            try:
                return asyncio.run(gateway.request(method="POST", url=VENDOR_URL, headers=VENDOR_HEADERS, json_body=ADAPTER_BODY, timeout_seconds=FLOOR_TIMEOUT))
            except ProviderRequestError as error:
                return error


class DeadlineAssertions(unittest.TestCase):
    """Shared assertions for attempts of one managed call; holds no tests of its own."""

    def assert_vidbyte_error(self, error: Any, *, status: int | None) -> str:
        # The gateway's own credential-safe error, not the inner transport's, with the last attempt's status.
        self.assertIsInstance(error, ProviderRequestError)
        self.assertEqual(error.provider, "vidbyte")
        self.assertEqual(error.status_code, status)
        return str(error)

    def assert_full_timeout_and_one_key(self, call: GatewayCall, attempts: int) -> None:
        # INV-10, INV-16: every attempt is the gateway POST with one key and the full 630 s timeout, never the time left.
        requests = call.transport.requests
        self.assertEqual(len(requests), attempts)
        key = idempotency_key(requests[0])
        self.assertIsNotNone(key)
        for request in requests:
            self.assertEqual(request["url"], GATEWAY_URL)
            self.assertEqual(idempotency_key(request), key)
            self.assertEqual(request.get("idempotency_key"), key)
            self.assertEqual(request["timeout_seconds"], 630.0)


class CumulativeDeadlineTests(DeadlineAssertions):
    """Checks INV-10, INV-16 and EC-38: re-sends share one deadline counted from the first POST, and each attempt keeps its full timeout."""

    def test_a_fast_502_is_re_sent_twice_and_the_error_counts_two_re_sends(self) -> None:
        # Step 0: both waits fit inside the deadline, so the call makes three POSTs and its message says two re-sends.
        call = GatewayCall(0.0, gateway_error(502))
        message = self.assert_vidbyte_error(call.run(), status=502)
        self.assertIn("re-sends in this call: 2", message)
        self.assert_full_timeout_and_one_key(call, 3)
        self.assertEqual(call.clock.waits, [0.5, 1.0])

    def test_a_502_after_600_s_is_re_sent_once_with_the_full_630_s_timeout(self) -> None:
        # EC-38: a slow 502 gets at most one re-send. A deadline taken after the first POST would allow a second, and a cut-short re-send would carry 629.5 s.
        call = GatewayCall(600.0, gateway_error(502))
        message = self.assert_vidbyte_error(call.run(), status=502)
        self.assertIn("re-sends in this call: 1", message)
        self.assert_full_timeout_and_one_key(call, 2)
        self.assertEqual(call.clock.waits, [0.5])

    def test_a_502_that_leaves_exactly_the_first_wait_is_not_re_sent(self) -> None:
        # 629.5 s plus the 0.5 s wait reaches the deadline exactly, and the loop stops there (loop.time() + wait >= deadline).
        call = GatewayCall(629.5, gateway_error(502))
        message = self.assert_vidbyte_error(call.run(), status=502)
        self.assertIn("did not re-send", message)
        self.assertNotIn("re-sends in this call", message)
        self.assertIn("630", message)
        self.assert_full_timeout_and_one_key(call, 1)
        self.assertEqual(call.clock.waits, [])


class LastAttemptTests(DeadlineAssertions):
    """Checks section 9.2 "Retries": after a re-send, the last attempt's outcome decides the error, its status and its message."""

    def test_a_422_after_a_502_raises_the_422_and_its_remedy(self) -> None:
        # Reporting the first answer would give the 502 "unavailable" message instead of the 422 remedy.
        call = GatewayCall(0.0, gateway_error(502), gateway_error(422))
        message = self.assert_vidbyte_error(call.run(), status=422)
        self.assertRegex(message, re.compile("stream", re.IGNORECASE))
        self.assertNotRegex(message, re.compile("unavailable", re.IGNORECASE))
        self.assert_full_timeout_and_one_key(call, 2)
        self.assertEqual(call.clock.waits, [0.5])

    def test_a_missing_response_after_a_502_raises_the_no_response_error(self) -> None:
        # A re-send that gets no answer is raised as no response (row 1), with no status, and is not re-sent again.
        dropped = ProviderRequestError("connection reset", provider="http")
        call = GatewayCall(0.0, gateway_error(502), dropped)
        message = self.assert_vidbyte_error(call.run(), status=None)
        self.assertRegex(message, re.compile(r"no (response|answer)", re.IGNORECASE))
        self.assertIn("630", message)
        self.assert_full_timeout_and_one_key(call, 2)
        self.assertEqual(call.clock.waits, [0.5])


class DirectValidateTests(unittest.TestCase):
    """Checks EC-3 and EC-7 on a TextModelConfig a direct caller builds; since byok-api-keys D-23 the gateway-shape checks run when the config is built."""

    def test_validate_refuses_an_endpoint_when_auto_selects_the_vidbyte_key(self) -> None:
        # EC-7, INV-7; byok-api-keys D-23, M-13: AUTO always uses the gateway, so building the config refuses the endpoint before a caller can send the key to a caller URL.
        with patch.dict(os.environ, {"VIDBYTE_API_KEY": VIDBYTE_KEY}, clear=True):
            with self.assertRaises(ConfigurationError) as caught:
                TextModelConfig(provider="openai", model="gpt-5.5", endpoint="https://proxy.example/v1")
        self.assertRegex(str(caught.exception), re.compile("endpoint", re.IGNORECASE))
        self.assertIn("TextModelMode.DIRECT", str(caught.exception))

    def test_validate_refuses_an_explicit_vidbyte_key_for_a_provider_the_gateway_does_not_serve(self) -> None:
        # EC-3, INV-8; byok-api-keys D-25, D-23, M-12: the Vidbyte key is now vidbyte_api_key, and building the config refuses openrouter before the key can reach it.
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(UnsupportedProviderError) as caught:
                TextModelConfig(provider="openrouter", model="openrouter/auto", vidbyte_api_key=VIDBYTE_KEY)
        for provider in MANAGED_PROVIDERS:
            self.assertIn(provider, str(caught.exception))
        self.assertIn("TextModelMode.DIRECT", str(caught.exception))
        self.assertNotIn(VIDBYTE_KEY, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
