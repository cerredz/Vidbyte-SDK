"""FILE: tests/features/sdk_model_usage/test_in_flight_failure_usage.py

PURPOSE: Prove a model call that fails with no HTTP status (a timeout: the provider may still have billed it) leaves the run's ledger unmeasured, so a spend cap fails closed.
ROLE IN CODEBASE: Exercises UsageTracker.record_unaccounted_call and the failed-call branch of vidbyte/agents/runtime.py through the real Anthropic adapter, transport error mapping, fallback and pricing.
ARCHITECTURE NOTE: Only HttpTransport._send_once is scripted; it raises httpx.ReadTimeout, which HttpTransport.request maps to a status-less ProviderRequestError exactly as a real timeout is mapped. No socket opens.
FUNCTION INVENTORY: test_record_unaccounted_call_leaves_cost_but_clears_cost_measured; test_a_timed_out_call_then_fallback_is_unmeasured; test_a_capped_run_stops_blind_after_a_timeout; test_a_provider_error_with_a_status_stays_measured; test_billed_usage_on_a_status_less_error_is_recorded_once; test_each_timed_out_attempt_counts.
COMMON MODIFICATION PATTERNS: A new failure shape that can be billed without usage adds one scripted case here and asserts unaccounted_call_count.
WHAT NOT TO DO IN THIS FILE: 1. Do not reach the network. 2. Do not hard-code tariff rates; compare against UsageTracker pricing of the same usage.
KNOWN EDGE CASES: A connect failure is mapped to the same status-less error as a read timeout, so it also counts as unmeasured (fail closed). An error that carries billed usage is recorded as a failed call and is not also counted.
RELATED DOCS: tests/features/sdk_model_usage/FEATURE.md; docs/design/timeout-spend-unmeasured.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/sdk_model_usage/test_in_flight_failure_usage.py
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from vidbyte import Agent, AgentLoopSettings
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.dataclasses.agents import FallbackModel
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ProviderRequestError
from vidbyte.lib.http import HttpResponse, HttpTransport

ANSWER_USAGE = {"input_tokens": 1000, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
# Built at runtime so no key-shaped literal sits in the source; the scripted send never reads it.
ANTHROPIC_TEST_KEY = "sk-ant-" + "api03-" + "x" * 40
TIMEOUT = "timeout"


def _answer(model: str) -> HttpResponse:
    body = {"id": "m1", "type": "message", "role": "assistant", "model": model, "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": ANSWER_USAGE}
    return HttpResponse(status_code=200, body=json.dumps(body), headers={"content-type": "application/json"})


def _script(monkeypatch: pytest.MonkeyPatch, outcomes: dict[str, object]) -> list[str]:
    # Answers each request by the model it names: a timeout, an HttpResponse, an exception, or a normal answer.
    sent: list[str] = []

    async def scripted_send(self: HttpTransport, client: object, *, json_body: dict[str, Any] | None = None, **_: Any) -> HttpResponse:
        model = str((json_body or {}).get("model"))
        sent.append(model)
        outcome = outcomes.get(model)
        if outcome == TIMEOUT:
            raise httpx.ReadTimeout("timed out")
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, HttpResponse):
            return outcome
        return _answer(model)

    monkeypatch.setattr(HttpTransport, "_send_once", scripted_send)
    return sent


def _agent(*fallback_models: str, loop: AgentLoopSettings | None = None) -> Agent:
    return Agent(
        name="a",
        system_prompt="Answer.",
        provider="anthropic",
        model_name="claude-haiku-5-5",
        api_keys=[ANTHROPIC_TEST_KEY],
        model_mode=TextModelMode.DIRECT,
        fallback=[FallbackModel(provider="anthropic", model=model) for model in fallback_models],
        agent_loop_settings=loop or AgentLoopSettings(max_iterations=2),
    )


def _answer_cost(model: str) -> float:
    record = UsageTracker().record_call(SimpleNamespace(provider=ModelProvider.ANTHROPIC, model=model, usage=ANSWER_USAGE))
    assert record is not None and record.cost_usd is not None
    return record.cost_usd


def test_record_unaccounted_call_leaves_cost_but_clears_cost_measured() -> None:
    # [Silent Failure] The count must change only the measured flag,
    # never invent a cost for the lost call.
    tracker = UsageTracker()
    tracker.record_call(SimpleNamespace(provider=ModelProvider.ANTHROPIC, model="claude-sonnet-5-5", usage=ANSWER_USAGE))
    before = tracker.rollup()

    tracker.record_unaccounted_call()

    after = tracker.rollup()
    assert before.cost_measured is True
    assert after.unaccounted_call_count == 1
    assert after.cost_measured is False
    assert after.cost_usd == before.cost_usd
    assert after.model_call_count == 1


def test_a_timed_out_call_then_fallback_is_unmeasured(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Silent Failure] Haiku times out (it may be billed), Sonnet answers;
    # the ledger must not call the run fully measured.
    sent = _script(monkeypatch, {"claude-haiku-5-5": TIMEOUT})
    agent = _agent("claude-sonnet-5-5")

    asyncio.run(agent.arun("q"))

    rollup = agent.get_usage()
    assert sent == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert rollup.unaccounted_call_count == 1
    assert rollup.cost_measured is False
    assert [(record.model, record.failed) for record in rollup.calls] == [("claude-sonnet-5-5", False)]
    assert rollup.cost_usd == pytest.approx(_answer_cost("claude-sonnet-5-5"))


def test_a_capped_run_stops_blind_after_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] The spend cap reads the same ledger, so a timeout
    # makes a capped run stop as unmeasured instead of spending on.
    _script(monkeypatch, {"claude-haiku-5-5": TIMEOUT})
    agent = _agent("claude-sonnet-5-5", loop=AgentLoopSettings(max_iterations=2, max_spend_usd=1.0))

    reply = asyncio.run(agent.arun("q"))

    assert reply.metadata.get("stop_reason") == "max_spend"
    assert "1 model calls reported no usage" in str(reply.content)


def test_a_provider_error_with_a_status_stays_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Assumption] A status means the provider answered and
    # reported the outcome, so a 429 adds nothing unmeasured.
    rate_limited = HttpResponse(status_code=429, body=json.dumps({"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}), headers={"content-type": "application/json"})
    _script(monkeypatch, {"claude-haiku-5-5": rate_limited})
    agent = _agent("claude-sonnet-5-5")

    asyncio.run(agent.arun("q"))

    rollup = agent.get_usage()
    assert rollup.unaccounted_call_count == 0
    assert rollup.cost_measured is True


def test_billed_usage_on_a_status_less_error_is_recorded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] An error that carries its billed usage is already
    # on the bill; counting it unaccounted too would double count it.
    billed = ProviderRequestError("stream broke after the reply was billed", provider="anthropic")
    billed.details["usage"] = ANSWER_USAGE
    _script(monkeypatch, {"claude-haiku-5-5": billed})
    agent = _agent("claude-sonnet-5-5")

    asyncio.run(agent.arun("q"))

    rollup = agent.get_usage()
    assert [(record.model, record.failed) for record in rollup.calls] == [("claude-haiku-5-5", True), ("claude-sonnet-5-5", False)]
    assert rollup.unaccounted_call_count == 0
    assert rollup.cost_measured is True


def test_each_timed_out_attempt_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Edge Case] Two sent requests that both time out are two unknown
    # bills, not one.
    sent = _script(monkeypatch, {"claude-haiku-5-5": TIMEOUT, "claude-sonnet-5": TIMEOUT})
    agent = _agent("claude-sonnet-5", "claude-sonnet-5-5")

    asyncio.run(agent.arun("q"))

    rollup = agent.get_usage()
    assert sent == ["claude-haiku-5-5", "claude-sonnet-5", "claude-sonnet-5-5"]
    assert rollup.unaccounted_call_count == 2
    assert rollup.model_call_count == 1
