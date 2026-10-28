"""FILE: tests/features/sdk_model_usage/test_anthropic_web_search_pricing.py

PURPOSE: Prove an Anthropic call that ran server-side web searches bills $10 per 1,000 searches on top of its tokens, as usage.server_tool_use.web_search_requests reports.
ROLE IN CODEBASE: Exercises AnthropicUsage.cost_usd (vidbyte/agents/pricing/anthropic.py), UsageTracker, and one AnthropicProvider agent run.
ARCHITECTURE NOTE: Expected prices are typed by hand in Decimal from the "Web search tool" section of https://platform.claude.com/docs/en/about-claude/pricing (fetched 2026-10-27), never derived from PROVIDER_PRICING; the agent run scripts HttpTransport.request, so nothing reaches the network.
FUNCTION INVENTORY: documented-example test; per-search fee tests on token, cache, tier, fast and US prices; no-fee tests (no searches, null server_tool_use, web fetch only); negative-count, tracker and agent-run tests.
COMMON MODIFICATION PATTERNS: When Anthropic changes the search fee, change the expected prices here and ANTHROPIC_WEB_SEARCH_USD_PER_REQUEST together, citing the page.
WHAT NOT TO DO IN THIS FILE: 1. Do not call providers. 2. Do not compute expected prices from PROVIDER_PRICING or the constant under test. 3. Do not loosen PRICE_REL_TOLERANCE.
KNOWN EDGE CASES: The search fee is not a token price, so data residency (1.1x), fast mode and the Haiku 5.5 tier never scale it; server_tool_use is null when no server tool ran; web fetch has no fee.
RELATED DOCS: tests/features/sdk_model_usage/FEATURE.md.
TESTS: python -m pytest -q tests/features/sdk_model_usage/test_anthropic_web_search_pricing.py
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from vidbyte import Agent
from vidbyte.agents.pricing import AnthropicUsage, UsageTracker
from vidbyte.agents.pricing.records import UsageRecordingIntegrity
from vidbyte.lib.config import TextModelMode
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.http import HttpResponse, HttpTransport
from vidbyte.lib.registries.pricing import ModelPricingRegistry

ANTHROPIC = ModelProvider.ANTHROPIC

# A float cost matched to 12 significant digits is exact to the cent on
# any bill under $10 billion; see test_anthropic_price_modifiers.py.
PRICE_REL_TOLERANCE = 1e-12

# The usage example in the pricing page's "Web search tool" section.
DOCUMENTED_EXAMPLE = {"input_tokens": 105, "output_tokens": 6039, "cache_read_input_tokens": 7123, "cache_creation_input_tokens": 7345, "server_tool_use": {"web_search_requests": 1}}


def _price(model: str, payload: dict[str, object]) -> float | None:
    # Prices one payload against UsageTracker's default pricebook.
    usage = AnthropicUsage.from_usage_payload(payload)
    assert usage is not None
    return usage.cost_usd(ModelPricingRegistry.default().resolve(ANTHROPIC, model))


def _assert_documented_price(cost: float | None, truth: str) -> None:
    # Asserts the SDK's cost equals Anthropic's documented price.
    assert cost is not None, f"unpriced, expected ${truth}"
    assert cost == pytest.approx(float(Decimal(truth)), rel=PRICE_REL_TOLERANCE, abs=0.0)


def test_documented_example_bills_one_search_on_top_of_its_tokens() -> None:
    # [Silent Failure] Sonnet 4.6: 105 x $3 + 6,039 x $15 + 7,123
    # reads x $0.30 + 7,345 5m writes x $3.75 per MTok, plus 1 x $0.01.
    _assert_documented_price(_price("claude-sonnet-4-6", DOCUMENTED_EXAMPLE), "0.13058065")


@pytest.mark.parametrize(("model", "truth"), [("claude-opus-5-5", "0.036"), ("claude-haiku-5-5", "0.03015")])
def test_three_searches_bill_three_cents_on_any_model(model: str, truth: str) -> None:
    # [Silent Failure] 1,000 in and 100 out at the model's rate, plus
    # 3 x $0.01; on Haiku 5.5 the fee is 99.5% of the call.
    payload = {"input_tokens": 1_000, "output_tokens": 100, "server_tool_use": {"web_search_requests": 3}}
    _assert_documented_price(_price(model, payload), truth)


def test_the_search_fee_is_not_scaled_by_fast_mode_or_us_inference() -> None:
    # [Hidden Assumption] Fast mode and the 1.1x apply to token prices
    # only: (13 x $8 + 6 x $40) x 1.1 per MTok, plus 2 x $0.01.
    payload = {"input_tokens": 13, "output_tokens": 6, "speed": "fast", "inference_geo": "us", "server_tool_use": {"web_search_requests": 2}}
    _assert_documented_price(_price("claude-opus-5-5", payload), "0.0203784")


def test_the_search_fee_is_not_scaled_by_the_haiku_5_5_tier() -> None:
    # [Hidden Assumption] 120,000 x $0.50 + 100 x $2.50 per MTok on the
    # high tier, plus a flat 1 x $0.01.
    payload = {"input_tokens": 120_000, "output_tokens": 100, "server_tool_use": {"web_search_requests": 1}}
    _assert_documented_price(_price("claude-haiku-5-5", payload), "0.07025")


@pytest.mark.parametrize("server_tool_use", [{"web_search_requests": 0}, None, {"web_fetch_requests": 4}, {}])
def test_no_search_adds_nothing(server_tool_use: object) -> None:
    # [Hidden Assumption] No searches, a null server_tool_use (no
    # server tool ran), and web fetch (no fee) bill exactly the tokens.
    tokens = {"input_tokens": 1_000, "output_tokens": 200, "cache_read_input_tokens": 5_000}
    assert _price("claude-opus-5-5", {**tokens, "server_tool_use": server_tool_use}) == _price("claude-opus-5-5", tokens)


def test_tracker_records_the_search_fee_in_the_call_cost() -> None:
    # [Silent Failure] The ledger, which spend caps read, carries the
    # fee and stays complete.
    tracker = UsageTracker()
    record = tracker.record_call(SimpleNamespace(provider="anthropic", model="claude-sonnet-4-6", usage=DOCUMENTED_EXAMPLE))
    assert record is not None
    _assert_documented_price(record.cost_usd, "0.13058065")
    _assert_documented_price(tracker.rollup().cost_usd, "0.13058065")
    assert tracker.rollup().cost_complete is True


def test_a_negative_search_count_corrupts_the_ledger() -> None:
    # [Hidden Failure] A negative count would make the call cheaper than
    # its tokens; like a negative token count, it fails recording.
    tracker = UsageTracker()
    record = tracker.record_call(SimpleNamespace(provider="anthropic", model="claude-opus-5-5", usage={"input_tokens": 10, "output_tokens": 1, "server_tool_use": {"web_search_requests": -1}}))
    assert record is None
    assert tracker.rollup().recording_integrity is UsageRecordingIntegrity.CORRUPTED


def test_agent_run_bills_a_web_search_reply_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Assumption] The Anthropic adapter forwards server_tool_use
    # to the tracker: 13 x $4 + 6 x $20 per MTok, plus 1 x $0.01.
    usage = {"input_tokens": 13, "output_tokens": 6, "server_tool_use": {"web_search_requests": 1}}
    body = {"id": "m1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "ready"}], "stop_reason": "end_turn", "usage": usage}

    async def scripted(_transport: object, **_: Any) -> HttpResponse:
        return HttpResponse(status_code=200, body=json.dumps(body), headers={"content-type": "application/json"})

    monkeypatch.setattr(HttpTransport, "request", scripted)
    agent = Agent(name="a", system_prompt="Answer.", max_iterations=3, provider="anthropic", model_name="claude-opus-5-5", api_keys=["sk-ant-mock"], model_mode=TextModelMode.DIRECT)
    asyncio.run(agent.arun("hi"))
    rollup = agent.get_usage()
    assert rollup.model_call_count == 1
    _assert_documented_price(rollup.cost_usd, "0.010172")
