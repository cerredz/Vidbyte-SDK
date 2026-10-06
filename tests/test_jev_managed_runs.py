"""FILE: tests/test_jev_managed_runs.py

PURPOSE: Proves that a JevAgent run shares one managed gateway run ID and closes it once.
ROLE IN CODEBASE: Covers vidbyte/providers/typesafe.py (run headers and close) and vidbyte/lib/jev/managed.py.
ARCHITECTURE NOTE: A scripted transport stands in for the gateway and answers every decision with clear noul answers, so the real adapter, runner, and runtime run unmocked.
COMMON MODIFICATION PATTERNS: Add a case when the gateway's header or close contract changes.
KNOWN EDGE CASES: A run that sent no call is not closed; a nested run joins its parent; a failed close is logged, never raised.
RELATED DOCS: docs/design/jev-managed-runs.md.
TESTS: Run this module with pytest.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest.mock import patch

from tests.agent_test_support import bind_test_runner
from vidbyte import JevAgent, JevAgentSettings, JevPreflightPreset, JevRuntimeSettings
from vidbyte.lib.config import DecisionModelConfig
from vidbyte.lib.constants.jev import VIDBYTE_JEV_GATEWAY_ENDPOINT
from vidbyte.lib.dataclasses.jev import JevDecisionRequest, JevManagedRunScope, JevQuestion
from vidbyte.lib.enums import DecisionModelMode, JevQuestionType, ModelProvider
from vidbyte.lib.errors import ConfigurationError
from vidbyte.lib.http import HttpResponse
from vidbyte.lib.jev import JevManagedRun
from vidbyte.lib.runners import DecisionModelRunner, TextModelResponse
from vidbyte.providers.typesafe import TypeSafeManagedRunContext

GATEWAY = VIDBYTE_JEV_GATEWAY_ENDPOINT
VB_KEY = "vb_live_" + ("x" * 32)
RUN_HEADER, IDEMPOTENCY_HEADER = "X-Vidbyte-Run-Id", "Idempotency-Key"
_TRANSPORT_PATH = "vidbyte.lib.runners.decision.HttpTransport"


class GatewayTransport:
    """Scripted gateway: clear noul answers for every decision, a summary for every close, all requests recorded."""

    def __init__(self, *, close_status: int = 200) -> None:
        self.requests: list[dict[str, Any]] = []
        self.close_status = close_status

    def __call__(self) -> GatewayTransport:
        # Stands in for the HttpTransport class, so every runner the run builds shares this recorder.
        return self

    async def request(self, **kwargs: Any) -> HttpResponse:
        self.requests.append(kwargs)
        if kwargs["url"].endswith("/close"):
            return HttpResponse(status_code=self.close_status, body=json.dumps({"run_id": "x", "billed_cents": 1}), headers={})
        questions = kwargs["json_body"]["questions"]
        answers = {name: {"type": "noul", "noul": 0.95} for name in questions}
        return HttpResponse(status_code=200, body=json.dumps({"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 10, "output_tokens": 1}}), headers={})

    def decisions(self) -> list[dict[str, Any]]:
        return [request for request in self.requests if request["url"].endswith("/systemone")]

    def closes(self) -> list[dict[str, Any]]:
        return [request for request in self.requests if request["url"].endswith("/close")]


class ScriptedGenerativeRunner:
    """Generative runner that answers every prompt with fixed text."""

    def run(self, prompt: str, system: str = "", **kwargs: Any) -> TextModelResponse:
        return TextModelResponse(provider=ModelProvider.OPENAI, model="fake", text="done", raw={})


def _request() -> JevDecisionRequest:
    return JevDecisionRequest(state="ticket", questions=(JevQuestion(name="ok", question_type=JevQuestionType.NOUL, instructions="Is it fine?"),))


def _managed(**overrides: Any) -> DecisionModelConfig:
    values: dict[str, Any] = {"mode": DecisionModelMode.VIDBYTE_MANAGED, "api_key": VB_KEY, "retry_count": 0}
    values.update(overrides)
    return DecisionModelConfig(**values)


class ManagedConfigTests(unittest.TestCase):
    """Run-ID validation and close-route derivation complement the existing gateway config."""

    def test_managed_mode_locates_the_close_route(self) -> None:
        self.assertEqual(_managed().resolved_run_close_url("jev:abc"), f"{GATEWAY.removesuffix('/typesafe')}/runs/jev:abc/close")
        with self.assertRaises(ConfigurationError):
            DecisionModelConfig(api_key="ts").resolved_run_close_url("jev:abc")

    def test_run_scope_rejects_ids_the_gateway_would_refuse(self) -> None:
        with self.assertRaises(ConfigurationError):
            JevManagedRunScope(run_id="has space")


class ManagedRunTests(unittest.IsolatedAsyncioTestCase):
    """Calls in one managed run share an ID; the run is closed once, after a call, and never fails the caller."""

    async def test_direct_typesafe_calls_send_no_vidbyte_headers(self) -> None:
        transport = GatewayTransport()
        config = DecisionModelConfig(api_key="ts_key", retry_count=2)
        with patch(_TRANSPORT_PATH, new=transport):
            async with JevManagedRun(config):
                await DecisionModelRunner(config).arun(_request())
        headers = transport.decisions()[0]["headers"]
        self.assertNotIn(RUN_HEADER, headers)
        self.assertNotIn(IDEMPOTENCY_HEADER, headers)
        self.assertEqual(transport.closes(), [])

    async def test_every_call_in_a_run_shares_its_id_and_the_run_closes_once(self) -> None:
        transport = GatewayTransport()
        config = _managed()
        with patch(_TRANSPORT_PATH, new=transport):
            async with JevManagedRun(config) as scope:
                await asyncio.gather(DecisionModelRunner(config).arun(_request()), DecisionModelRunner(config).arun(_request()))
            async with JevManagedRun(config) as second:
                await DecisionModelRunner(config).arun(_request())
        assert scope is not None and second is not None
        ids = [request["headers"][RUN_HEADER] for request in transport.decisions()]
        self.assertEqual(ids, [scope.run_id, scope.run_id, second.run_id])
        self.assertNotEqual(scope.run_id, second.run_id)
        self.assertTrue(scope.run_id.startswith("jev:"))
        close_root = GATEWAY.removesuffix("/typesafe")
        self.assertEqual([request["url"] for request in transport.closes()], [f"{close_root}/runs/{run_id}/close" for run_id in (scope.run_id, second.run_id)])
        self.assertEqual(transport.closes()[0]["headers"]["authorization"], f"Bearer {VB_KEY}")
        self.assertIsNone(TypeSafeManagedRunContext.current())

    async def test_retried_managed_calls_send_an_idempotency_key(self) -> None:
        transport = GatewayTransport()
        with patch(_TRANSPORT_PATH, new=transport):
            await DecisionModelRunner(_managed(retry_count=2)).arun(_request())
            await DecisionModelRunner(_managed()).arun(_request())
        retried, single = transport.decisions()
        self.assertEqual(len(retried["headers"][IDEMPOTENCY_HEADER]), 32)
        self.assertEqual(retried["headers"][IDEMPOTENCY_HEADER], retried["idempotency_key"])
        self.assertNotIn(IDEMPOTENCY_HEADER, single["headers"])
        self.assertNotIn(RUN_HEADER, single["headers"])

    async def test_a_run_with_no_call_is_not_closed_and_a_nested_run_joins_its_parent(self) -> None:
        transport = GatewayTransport()
        config = _managed()
        with patch(_TRANSPORT_PATH, new=transport):
            async with JevManagedRun(config):
                pass
            async with JevManagedRun(config) as outer:
                async with JevManagedRun(config) as inner:
                    await DecisionModelRunner(config).arun(_request())
                self.assertEqual(transport.closes(), [])
        self.assertIs(inner, outer)
        self.assertEqual(len(transport.closes()), 1)

    async def test_a_failed_close_is_logged_and_never_raised(self) -> None:
        transport = GatewayTransport(close_status=503)
        config = _managed()
        with patch(_TRANSPORT_PATH, new=transport), self.assertLogs("vidbyte.lib.jev.managed", level="WARNING"):
            async with JevManagedRun(config):
                await DecisionModelRunner(config).arun(_request())
        self.assertEqual(len(transport.closes()), 1)


class JevAgentManagedRunTests(unittest.IsolatedAsyncioTestCase):
    """Each JevAgent.arun is one managed run: its gate calls share one ID and the run closes when arun returns."""

    async def test_each_agent_run_is_one_closed_managed_run(self) -> None:
        transport = GatewayTransport()
        settings = JevAgentSettings(name="jev", system_prompt="Work carefully.", provider="openai", model_name="gpt-4.1-mini")
        agent = bind_test_runner(JevAgent(settings, JevRuntimeSettings(decision=_managed(), preflight=(JevPreflightPreset.CLARITY,))), ScriptedGenerativeRunner())
        with patch(_TRANSPORT_PATH, new=transport):
            await agent.arun("Add a login page to the web app.")
            await agent.arun("Add a signup form to the web app.")
        first, second = (request["headers"][RUN_HEADER] for request in transport.decisions())
        self.assertNotEqual(first, second)
        self.assertEqual([request["url"].rsplit("/", 2)[-2] for request in transport.closes()], [first, second])


if __name__ == "__main__":
    unittest.main()
