"""FILE: tests/features/sdk_managed_text/test_managed_text_error_surfacing.py

PURPOSE: Proves a paying developer sees why a gateway call failed and does not pay retries for a call that cannot succeed: a known gateway error code picks the SDK's own wording for its cause, the raised ProviderRequestError says whether a fresh call can succeed, an Agent's AgentExecutionError repeats the gateway's SDK-written reason (and never another provider's raw text), and the retry middlewares send a final refusal once while still retrying a transient one.
ROLE IN CODEBASE: Error-surfacing layer of tests/features/sdk_managed_text/. Exercises VidbyteGatewayTransport (vidbyte/lib/http/vidbyte_gateway.py) through TextModelRunner and Agent, AgentExecutionError wording in vidbyte/agents/base.py, and ModelRetryMiddleware / ExponentialBackoffRetryMiddleware in vidbyte/middleware/builtins/.
ARCHITECTURE NOTE: Gateway refusals are scripted in the backend's exact public shape, DomainError.public_payload() ({"error": true, "title", "subtitle", "description", "code", "incident_id"}), with a canary and a key-shaped string in the free-text fields, so finding either in an error means body text leaked. The codes are spelled as the strings the backend sends, so this module imports nothing the fix adds and each test fails on its own on a commit without the fix.
COMMON MODIFICATION PATTERNS: When the backend adds a code, add its row to CODE_FACTS when its status alone cannot name the cause, and its verdict to FreshCallVerdictTests.
WHAT NOT TO DO IN THIS FILE: 1. Do not import VidbyteGatewayErrorCode or the new constants at module level (see managed_text_fixtures.py). 2. Do not let the real asyncio.sleep run in a gateway re-send. 3. Do not assert whole messages; assert the facts the developer needs, so wording can improve.
KNOWN EDGE CASES: The API-key gatekeeper refuses a wrong key or a missing scope with {"error": true, "title", "subtitle"} and no code, so finality there comes from the status. retryable is the verdict for a fresh call (a new Idempotency-Key), so a reused-key refusal is True even though the transport does not re-send it.
RELATED DOCS: tests/features/sdk_managed_text/FEATURE.md; backend/lib/errors/model_gateway.py and backend/lib/errors/domain.py in cerredz/Vidbyte (the codes and the body shape).
TESTS: python -m pytest tests/features/sdk_managed_text/test_managed_text_error_surfacing.py
"""

from __future__ import annotations

import os
import re
import traceback
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from tests.features.sdk_managed_text.managed_text_fixtures import (
    BODY_CANARY,
    LEAKED_KEY,
    RUNNER_TRANSPORT_TARGET,
    SLEEP_TARGET,
    VIDBYTE_KEY,
    BackoffRecorder,
    ScriptedGateway,
    answer,
    edge_page,
    gateway_error,
    provider_answer,
    relayed_provider_error,
)
from vidbyte import Agent
from vidbyte.lib.config import TextModelConfig, TextModelMode
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import (
    AgentExecutionError,
    ProviderRequestError,
    ProviderResponseError,
)
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.runners import TextModelRunner
from vidbyte.middleware.builtins import ModelRetryMiddleware
from vidbyte.middleware.builtins.exponential_backoff_retry import (
    ExponentialBackoffRetryMiddleware,
)

MANAGED_ONLY = {"VIDBYTE_API_KEY": VIDBYTE_KEY}
MODEL = "gpt-5.5"
INCIDENT_ID = "0123456789ab"
NOT_SET = "attribute missing"
AGENT_NAME = "support-bot"
OPENAI_KEY = "sk-proj-" + "o" * 24


def backend_refusal(status: int, code: str) -> HttpResponse:
    # The backend's DomainError.public_payload() for one gateway refusal, its free text carrying a canary and a key.
    return answer(status, {"error": True, "title": f"{BODY_CANARY} title", "subtitle": f"{BODY_CANARY} echoed Bearer {LEAKED_KEY}", "description": f"{BODY_CANARY} description", "code": code, "incident_id": INCIDENT_ID})


def gatekeeper_refusal(status: int) -> HttpResponse:
    # The API-key gatekeeper's refusal (wrong key, missing scope, spent quota): "error": true with no code.
    return answer(status, {"error": True, "title": f"{BODY_CANARY} refused", "subtitle": f"{BODY_CANARY} {LEAKED_KEY}"})


# code -> (status, facts its message must state, facts it must not state); codes whose status already names the remedy are left out.
CODE_FACTS: dict[str, tuple[int, tuple[str, ...], tuple[str, ...]]] = {
    "model_gateway_unsupported_model": (422, (f"'{MODEL}'", "price", "TextModelMode.DIRECT", "billed nothing"), ("snake.?case", "service.?tier")),
    "model_gateway_unbillable_request": (422, ("stream", "max_output_tokens", "function tools", "TextModelMode.DIRECT", "billed nothing"), ("no price for that model",)),
    "model_gateway_daily_spend_cap_reached": (429, ("daily cap", "00:00 UTC", "max_output_tokens", "api_keys"), ("quota",)),
    "model_gateway_upstream_failed": (502, ("unavailable", "did not bill", "re-sent"), ("not known",)),
    "model_gateway_unavailable": (503, ("wallet", "did not call", "billed nothing", "retry after"), ("not known",)),
    "model_gateway_idempotency_key_reused": (422, ("Idempotency-Key", "fresh key"), ("snake.?case",)),
}


class GatewayCall:
    """One TextModelRunner call with only VIDBYTE_API_KEY set, against a scripted gateway."""

    def __init__(self, *steps: HttpResponse | BaseException) -> None:
        # Holds the script; the call itself runs in run().
        self.transport = ScriptedGateway(*steps)
        self.backoff = BackoffRecorder()

    def run(self) -> Any:
        # Runs the call and returns the response, or the ProviderRequestError it raised.
        with patch.dict(os.environ, MANAGED_ONLY, clear=True), patch(SLEEP_TARGET, new=self.backoff):
            runner = TextModelRunner(TextModelConfig(provider="openai", model=MODEL), transport=self.transport)
            try:
                return runner.run("Hi")
            except ProviderRequestError as error:
                return error


class AgentCall:
    """One Agent run whose runner's transport is scripted; returns the reply or the error the run raised."""

    def __init__(self, *steps: HttpResponse | BaseException, middleware: tuple[Any, ...] = (), env: dict[str, str] | None = None, **agent_options: Any) -> None:
        # Holds the script, the middleware, and the agent's own options.
        self.transport = ScriptedGateway(*steps)
        self.middleware = list(middleware)
        self.env = MANAGED_ONLY if env is None else env
        self.agent_options = agent_options

    def run(self) -> Any:
        # Builds the agent inside the patched environment, so its runner picks up the scripted transport.
        with patch.dict(os.environ, self.env, clear=True), patch(RUNNER_TRANSPORT_TARGET, new=self.transport), patch(SLEEP_TARGET, new=BackoffRecorder()):
            agent = Agent(name=AGENT_NAME, system_prompt="Answer briefly.", provider="openai", model_name=MODEL, middleware=self.middleware, **self.agent_options)
            try:
                return agent.run("Say hi.")
            except AgentExecutionError as error:
                return error


class LeakAssertions(unittest.TestCase):
    """Shared checks that no body text, key, or incident id reached an error; holds no tests of its own."""

    def assert_no_body_text(self, error: BaseException) -> str:
        # The message, the details, and the formatted traceback must hold none of what the scripted bodies carried.
        message = str(error)
        details = repr(getattr(error, "details", {}))
        rendered = message + details + "".join(traceback.format_exception(type(error), error, error.__traceback__))
        for secret in (BODY_CANARY, LEAKED_KEY, VIDBYTE_KEY, INCIDENT_ID):
            self.assertNotIn(secret, rendered)
        return message


class GatewayCodeWordingTests(LeakAssertions):
    """A known gateway code names its own cause in SDK wording; an unknown one keeps the status wording."""

    def test_each_known_code_states_its_cause_and_remedy_without_copying_the_body(self) -> None:
        # Before the fix a 422 printed one eleven-cause list, a 429 blamed "quota or daily cap", and 502/503 said "the cause is not known".
        for code, (status, facts, wrong_facts) in CODE_FACTS.items():
            with self.subTest(code=code):
                call = GatewayCall(backend_refusal(status, code))
                error = call.run()
                self.assertIsInstance(error, ProviderRequestError)
                self.assertEqual((error.provider, error.status_code), ("vidbyte", status))
                message = self.assert_no_body_text(error)
                # The code is matched against the SDK's own list and never copied into the message.
                self.assertNotIn(code, message)
                for fact in facts:
                    self.assertRegex(message, re.compile(fact, re.IGNORECASE))
                for wrong in wrong_facts:
                    self.assertNotRegex(message, re.compile(wrong, re.IGNORECASE))
                self.assertEqual(len(call.transport.requests), 3 if status == 502 else 1)

    def test_an_unknown_code_keeps_the_status_wording(self) -> None:
        # A code the SDK does not know (or a future one) must fall back to the status, not to a guess.
        error = GatewayCall(gateway_error(422)).run()
        message = self.assert_no_body_text(error)
        for fact in ("stream", "service.?tier", "snake.?case"):
            self.assertRegex(message, re.compile(fact, re.IGNORECASE))
        self.assertNotIn("model_gateway_refused", message)


class FreshCallVerdictTests(unittest.TestCase):
    """The raised error's retryable says whether a fresh call can succeed, and only a gateway refusal may say False."""

    def test_known_codes_carry_the_backends_verdict(self) -> None:
        # Final refusals (wallet, price, request shape, cap, auth, size) are False; transient ones are True.
        verdicts = {
            ("model_gateway_payment_required", 402): False,
            ("model_gateway_unsupported_model", 422): False,
            ("model_gateway_unbillable_request", 422): False,
            ("model_gateway_daily_spend_cap_reached", 429): False,
            ("model_gateway_authentication_required", 401): False,
            ("model_gateway_request_too_large", 413): False,
            ("model_gateway_upstream_failed", 502): True,
            ("model_gateway_unavailable", 503): True,
            ("model_gateway_idempotency_in_progress", 409): True,
            ("model_gateway_idempotency_key_reused", 422): True,
        }
        for (code, status), expected in verdicts.items():
            with self.subTest(code=code):
                error = GatewayCall(backend_refusal(status, code)).run()
                self.assertIs(getattr(error, "retryable", NOT_SET), expected)
                self.assertEqual(error.details.get("retryable", NOT_SET), expected)

    def test_answers_without_a_known_code_are_judged_by_who_sent_them(self) -> None:
        # A codeless gatekeeper 401/403 or an unknown-code 422 is final; anything not from the gateway itself stays unknown.
        cases = (
            ("gatekeeper 401 (wrong key)", gatekeeper_refusal(401), False),
            ("gatekeeper 403 (missing scope)", gatekeeper_refusal(403), False),
            ("unknown code at 422", gateway_error(422), False),
            ("gatekeeper 429 (request quota)", gatekeeper_refusal(429), None),
            ("unknown code at 500", gateway_error(500), None),
            ("relayed provider 401", relayed_provider_error(ModelProvider.OPENAI, 401), None),
            ("edge page 502", edge_page(502, "<html>bad gateway</html>"), None),
            ("no response", ProviderRequestError("connection reset", provider="http"), None),
        )
        for label, step, expected in cases:
            with self.subTest(label):
                error = GatewayCall(step).run()
                self.assertIsInstance(error, ProviderRequestError)
                self.assertIs(getattr(error, "retryable", NOT_SET), expected)


class AgentReplyFailureTests(LeakAssertions):
    """An Agent's reply failure repeats the gateway's SDK-written reason, keeps its type and cause, and never copies other text."""

    def test_the_agent_error_carries_the_gateway_reason_for_402_422_and_502(self) -> None:
        # Before the fix all three read only "Agent 'support-bot' failed to generate a reply."; the reason sat on __cause__.
        cases = (
            (backend_refusal(402, "model_gateway_payment_required"), 402, ("wallet", "top up")),
            (backend_refusal(422, "model_gateway_unsupported_model"), 422, (f"'{MODEL}'", "price")),
            (backend_refusal(502, "model_gateway_upstream_failed"), 502, ("unavailable", "did not bill")),
        )
        for step, status, facts in cases:
            with self.subTest(status=status):
                error = AgentCall(step).run()
                self.assertIsInstance(error, AgentExecutionError)
                cause = error.__cause__
                self.assertIsInstance(cause, ProviderRequestError)
                self.assertEqual((cause.provider, cause.status_code), ("vidbyte", status))
                message = self.assert_no_body_text(error)
                self.assertTrue(message.startswith(f"Agent '{AGENT_NAME}' failed to generate a reply."))
                self.assertIn(cause.message, message)
                for fact in facts:
                    self.assertRegex(message, re.compile(fact, re.IGNORECASE))

    def test_the_agent_error_never_copies_a_direct_providers_own_message(self) -> None:
        # In DIRECT mode the vendor's error message is response text that can echo request content; it stays on __cause__.
        direct = AgentCall(relayed_provider_error(ModelProvider.OPENAI, 400), env={}, api_keys=[OPENAI_KEY], model_mode=TextModelMode.DIRECT)
        error = direct.run()
        self.assertIsInstance(error, AgentExecutionError)
        self.assertIsInstance(error.__cause__, ProviderRequestError)
        self.assertNotEqual(error.__cause__.provider, "vidbyte")
        self.assertIn(BODY_CANARY, str(error.__cause__))
        self.assertEqual(str(error), f"Agent '{AGENT_NAME}' failed to generate a reply.")

    def test_the_agent_error_never_copies_other_errors_labelled_vidbyte(self) -> None:
        # Only a ProviderRequestError from the gateway transport is SDK-worded; a ProviderResponseError can hold raw exception text.
        raw = f"{BODY_CANARY} payload {LEAKED_KEY}"
        causes = (
            ProviderResponseError(f"vidbyte decide failed with an unexpected TypeError: {raw}", provider="vidbyte"),
            ProviderRequestError(f"OpenAI said: {raw}", provider="openai", status_code=400),
        )
        for cause in causes:
            with self.subTest(cause=type(cause).__name__, provider=cause.provider):
                with patch.object(TextModelRunner, "arun", new=AsyncMock(side_effect=cause)):
                    error = AgentCall(provider_answer(ModelProvider.OPENAI)).run()
                self.assertIsInstance(error, AgentExecutionError)
                self.assertIs(error.__cause__, cause)
                self.assertEqual(str(error), f"Agent '{AGENT_NAME}' failed to generate a reply.")


class RetryMiddlewareTests(unittest.TestCase):
    """Retry middleware sends a final gateway refusal once and raises its reason, but still retries a transient failure."""

    @staticmethod
    def retry_middlewares() -> tuple[tuple[str, Any], ...]:
        # Fresh instances per case, with a three-attempt budget that would show any retry.
        return (
            ("ModelRetryMiddleware", ModelRetryMiddleware(max_attempts=3)),
            ("ExponentialBackoffRetryMiddleware", ExponentialBackoffRetryMiddleware(max_attempts=3, base_seconds=0.001, jitter=False)),
            ("ExponentialBackoffRetryMiddleware(retry_on=ProviderRequestError)", ExponentialBackoffRetryMiddleware(max_attempts=3, base_seconds=0.001, jitter=False, retry_on=ProviderRequestError)),
        )

    def test_a_final_refusal_is_sent_once_and_raised_with_its_reason(self) -> None:
        # Before the fix each was sent max_attempts times and the run returned "stopped by middleware: model_retry_exhausted".
        refusals = (
            ("402 wallet empty", backend_refusal(402, "model_gateway_payment_required"), "wallet"),
            ("422 unpriced model", backend_refusal(422, "model_gateway_unsupported_model"), "price"),
            ("401 wrong key", gatekeeper_refusal(401), "VIDBYTE_API_KEY"),
        )
        for label, step, fact in refusals:
            for name, middleware in self.retry_middlewares():
                with self.subTest(refusal=label, middleware=name):
                    call = AgentCall(step, middleware=(middleware,))
                    error = call.run()
                    self.assertEqual(len(call.transport.requests), 1)
                    self.assertIsInstance(error, AgentExecutionError)
                    self.assertIs(error.__cause__.retryable, False)
                    self.assertRegex(str(error), re.compile(fact, re.IGNORECASE))

    def test_a_transient_failure_is_still_retried_until_it_succeeds(self) -> None:
        # A 502 is re-sent by the transport (three POSTs), then the middleware's fresh call succeeds on its first POST.
        recovered = {"id": "resp_1", "output": [{"type": "function_call", "name": "isDone", "arguments": '{"final_answer": "Recovered"}', "call_id": "call_1"}], "usage": {"input_tokens": 40, "output_tokens": 5}}
        outage = backend_refusal(502, "model_gateway_upstream_failed")
        for name, middleware in self.retry_middlewares():
            with self.subTest(middleware=name):
                call = AgentCall(outage, outage, outage, answer(200, recovered), middleware=(middleware,))
                reply = call.run()
                self.assertNotIsInstance(reply, AgentExecutionError)
                self.assertEqual(reply.content, "Recovered")
                self.assertEqual(len(call.transport.requests), 4)

    def test_an_error_without_a_verdict_keeps_the_old_retry_behavior(self) -> None:
        # A relayed provider 429 says nothing about the next call, so the middleware still spends its budget on it.
        throttled = relayed_provider_error(ModelProvider.OPENAI, 429)
        call = AgentCall(throttled, middleware=(ModelRetryMiddleware(max_attempts=2),))
        reply = call.run()
        self.assertEqual(len(call.transport.requests), 2)
        self.assertNotIsInstance(reply, AgentExecutionError)
        self.assertIn("model_retry_exhausted", reply.content)


if __name__ == "__main__":
    unittest.main()
