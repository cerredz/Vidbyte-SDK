"""FILE: tests/features/sdk_model_usage/test_actor_in_flight_failure_usage.py

PURPOSE: Prove an actor-model model call that fails after it was sent stays on the run's ledger: lost in flight (cancelled when another actor finished the run, or timed out) it counts as unmeasured spend, and a billed unusable reply is recorded.
ROLE IN CODEBASE: Exercises BaseActorRuntime.invoke_actor_completion and _record_failed_actor_call in vidbyte/agents/runtimes/actor/broker.py through the real Anthropic adapter, transport error mapping, pricing and usage ledger.
ARCHITECTURE NOTE: Only HttpTransport._send_once is scripted. The root actor's request carries ROOT (its role instructions) and is answered at once; every other actor's request waits, so in broadcast mode the root's answer completes the run while the others are in flight and the broker cancels them. No socket opens.
FUNCTION INVENTORY: test_broadcast_cancelled_actor_calls_are_unmeasured; test_parent_ledger_receives_the_unmeasured_calls; test_point_to_point_run_stays_measured; test_timed_out_actor_call_is_unmeasured; test_status_error_actor_call_stays_measured; test_billed_unusable_actor_reply_is_recorded.
COMMON MODIFICATION PATTERNS: A new way an actor call can fail after it was sent adds one scripted case here and asserts unaccounted_call_count or the failed record.
WHAT NOT TO DO IN THIS FILE: 1. Do not reach the network. 2. Do not hard-code tariff rates; compare against UsageTracker pricing of the same usage.
KNOWN EDGE CASES: An actor that is idle (waiting on its inbox) when the run ends is cancelled without a request in flight and counts nothing; only cancellations inside a model call count.
RELATED DOCS: tests/features/sdk_model_usage/FEATURE.md; docs/design/actor-cancelled-calls-unmeasured.md.
TESTS: PYTHONPATH=$(pwd) python -m pytest -q tests/features/sdk_model_usage/test_actor_in_flight_failure_usage.py
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from vidbyte import Agent
from vidbyte.agents.pricing.tracker import UsageTracker
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpResponse, HttpTransport
from vidbyte.lib.usage_ledger import usage_ledger_scope

MODEL = "claude-haiku-5-5"
ROOT = "ROOT-ACTOR-PROMPT"
ANSWER_USAGE = {"input_tokens": 1000, "output_tokens": 5, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
THINKING_USAGE = {"input_tokens": 700, "output_tokens": 8, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
# Built at runtime so no key-shaped literal sits in the source; the scripted send never reads it.
ANTHROPIC_TEST_KEY = "sk-ant-" + "api03-" + "x" * 40
NON_ROOT_DELAY_SECONDS = 0.5


def _reply(content: list[dict[str, Any]], usage: dict[str, int], stop_reason: str = "end_turn") -> HttpResponse:
    body = {"id": "m1", "type": "message", "role": "assistant", "model": MODEL, "content": content, "stop_reason": stop_reason, "usage": usage}
    return HttpResponse(status_code=200, body=json.dumps(body), headers={"content-type": "application/json"})


def _script(monkeypatch: pytest.MonkeyPatch, root_outcome: object = None) -> list[str]:
    # Answers the root actor with root_outcome (an answer by default), and holds every other actor's request.
    sent: list[str] = []

    async def scripted_send(self: HttpTransport, client: object, *, json_body: dict[str, Any] | None = None, **_: Any) -> HttpResponse:
        body = json_body or {}
        # The actor runtime sends each actor's role instructions inside its user message, so look in the whole request.
        is_root = ROOT in json.dumps(body)
        sent.append("root" if is_root else "actor")
        if not is_root:
            await asyncio.sleep(NON_ROOT_DELAY_SECONDS)
            return _reply([{"type": "text", "text": "late"}], ANSWER_USAGE)
        if isinstance(root_outcome, BaseException):
            raise root_outcome
        if isinstance(root_outcome, HttpResponse):
            return root_outcome
        return _reply([{"type": "text", "text": "ready"}], ANSWER_USAGE)

    monkeypatch.setattr(HttpTransport, "_send_once", scripted_send)
    return sent


def _agent(runtime: str) -> Agent:
    return Agent(name="actors", system_prompt=f"{ROOT} Answer.", runtime=runtime, max_iterations=2, provider="anthropic", model_name=MODEL, api_keys=[ANTHROPIC_TEST_KEY], model_mode=TextModelMode.DIRECT)


def _price(usage: dict[str, int]) -> float:
    record = UsageTracker().record_call(SimpleNamespace(provider=ModelProvider.ANTHROPIC, model=MODEL, usage=usage))
    assert record is not None and record.cost_usd is not None
    return record.cost_usd


def _run(agent: Agent, parent: UsageTracker | None = None) -> BaseException | None:
    # Runs the agent (under a parent ledger when given) and returns the error it raised, if any.
    async def go() -> None:
        if parent is None:
            await agent.arun("Say ready.")
            return
        with usage_ledger_scope(parent):
            await agent.arun("Say ready.")

    try:
        asyncio.run(go())
    except Exception as exc:  # the run may fail; the ledger is what these tests read
        return exc
    return None


def test_broadcast_cancelled_actor_calls_are_unmeasured(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Silent Failure] The root's answer ends the run and the broker cancels five in-flight requests; before the fix
    # the run reported one call, fully measured, while six requests had reached the provider.
    sent = _script(monkeypatch)
    agent = _agent("actor_model_broadcast")
    assert _run(agent) is None
    rollup = agent.get_usage()
    in_flight = sent.count("actor")
    assert sent.count("root") == 1 and in_flight >= 1
    assert rollup.model_call_count == 1
    assert rollup.unaccounted_call_count == in_flight
    assert rollup.cost_measured is False
    assert rollup.cost_usd == pytest.approx(_price(ANSWER_USAGE), abs=1e-12)


def test_parent_ledger_receives_the_unmeasured_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] A capped parent reads the child's merged rollup; the cancelled calls must reach it too.
    sent = _script(monkeypatch)
    parent = UsageTracker()
    assert _run(_agent("actor_model_broadcast"), parent) is None
    rollup = parent.rollup()
    assert rollup.model_call_count == 1
    assert rollup.unaccounted_call_count == sent.count("actor")
    assert rollup.cost_measured is False


def test_point_to_point_run_stays_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Edge Case] Point-to-point sends only to the root, so nothing is cancelled in flight and the run stays measured.
    sent = _script(monkeypatch)
    agent = _agent("actor_model_p2p")
    assert _run(agent) is None
    rollup = agent.get_usage()
    assert sent == ["root"]
    assert (rollup.model_call_count, rollup.unaccounted_call_count, rollup.cost_measured) == (1, 0, True)


def test_timed_out_actor_call_is_unmeasured(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Failure] A status-less timeout may have been billed: it counts as unmeasured, as in the linear runtime.
    _script(monkeypatch, httpx.ReadTimeout("timed out"))
    agent = _agent("actor_model_p2p")
    assert _run(agent) is not None
    rollup = agent.get_usage()
    assert (rollup.model_call_count, rollup.unaccounted_call_count, rollup.cost_measured) == (0, 1, False)


def test_status_error_actor_call_stays_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Assumption] A provider error with an HTTP status (529 overloaded) is not billed and must not blind the meter.
    overloaded = HttpResponse(status_code=529, body=json.dumps({"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}), headers={"content-type": "application/json"})
    _script(monkeypatch, overloaded)
    agent = _agent("actor_model_p2p")
    assert _run(agent) is not None
    rollup = agent.get_usage()
    assert (rollup.model_call_count, rollup.unaccounted_call_count, rollup.cost_measured) == (0, 0, True)


def test_billed_unusable_actor_reply_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Silent Failure] A billed 200 that holds only thinking has no text; its usage is recorded once, as a failed call.
    thinking_only = _reply([{"type": "thinking", "thinking": "hmm", "signature": "sig"}], THINKING_USAGE, stop_reason="max_tokens")
    _script(monkeypatch, thinking_only)
    agent = _agent("actor_model_p2p")
    assert _run(agent) is not None
    rollup = agent.get_usage()
    assert rollup.model_call_count == 1 and rollup.calls[0].failed is True
    assert rollup.unaccounted_call_count == 0 and rollup.cost_measured is True
    assert rollup.cost_usd == pytest.approx(_price(THINKING_USAGE), abs=1e-12)
