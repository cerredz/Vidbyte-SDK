"""FILE: tests/features/sdk_model_usage/test_anthropic_price_modifiers.py

PURPOSE: Prove an Anthropic call is billed at the speed and inference geography its response's usage reports: fast mode at the fast rates, US-only inference at 1.1x every bucket, and an unpriceable value left unpriced rather than billed at standard rates.
ROLE IN CODEBASE: Exercises AnthropicUsage.cost_usd (vidbyte/agents/pricing/anthropic.py), the Opus fast tiers in vidbyte/lib/registries/pricing.py, UsageTracker, and one AnthropicProvider agent run.
ARCHITECTURE NOTE: Expected prices are typed by hand in Decimal from https://platform.claude.com/docs/en/about-claude/pricing (fetched 2026-10-27), never derived from PROVIDER_PRICING; the agent run scripts HttpTransport.request, so nothing reaches the network.
FUNCTION INVENTORY: live-payload tests; stacking tests (fast + geo + cache + Haiku 5.5 tier); 1x tests (global, not_available, absent, null); fail-safe tests (unknown speed, unknown geo, fast without a fast rate); pricebook pins; tracker and agent-run integration tests.
COMMON MODIFICATION PATTERNS: When Anthropic changes a fast rate or the residency multiplier, change the expected price here and the pricebook together, citing the page.
WHAT NOT TO DO IN THIS FILE: 1. Do not call providers. 2. Do not compute expected prices from PROVIDER_PRICING; that would make every price test vacuous. 3. Do not loosen PRICE_REL_TOLERANCE.
KNOWN EDGE CASES: Models before Claude 4.6 report inference_geo "not_available"; Opus 4.6 reports speed "standard" for a fast request; the Haiku 5.5 tier counts cache reads and writes in the prompt.
RELATED DOCS: docs/design/anthropic-usage-price-modifiers.md and tests/features/sdk_model_usage/FEATURE.md.
TESTS: python -m pytest -q tests/features/sdk_model_usage/test_anthropic_price_modifiers.py
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
from vidbyte.lib.registries.pricing import PROVIDER_PRICING, ModelPricing, ModelPricingRegistry

ANTHROPIC = ModelProvider.ANTHROPIC

# The SDK prices in binary floats, which cannot hold most decimal prices
# exactly and land up to one unit in the last place away from them. A
# relative tolerance of 1e-12 is exact to the cent on any bill under $10
# billion and a million times tighter than pytest.approx's default.
PRICE_REL_TOLERANCE = 1e-12

# Real usage from claude-opus-5-5 on 2026-10-27 (billing-readiness run).
LIVE_FAST = {"input_tokens": 13, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}, "output_tokens": 6, "output_tokens_details": {"thinking_tokens": 0}, "service_tier": "standard", "inference_geo": "global", "speed": "fast"}
LIVE_US = {**LIVE_FAST, "inference_geo": "us", "speed": "standard"}


def _usage(input_tokens: int = 0, output_tokens: int = 0, read: int = 0, write_5m: int = 0, write_1h: int = 0, **modifiers: object) -> dict[str, object]:
    # Builds an Anthropic usage payload; modifiers adds speed and
    # inference_geo.
    buckets = {"ephemeral_5m_input_tokens": write_5m, "ephemeral_1h_input_tokens": write_1h}
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "cache_read_input_tokens": read, "cache_creation_input_tokens": write_5m + write_1h, "cache_creation": buckets, **modifiers}


def _price(model: str, payload: dict[str, object]) -> float | None:
    # Prices one payload against UsageTracker's default pricebook.
    usage = AnthropicUsage.from_usage_payload(payload)
    assert usage is not None
    return usage.cost_usd(ModelPricingRegistry.default().resolve(ANTHROPIC, model))


def _assert_documented_price(cost: float | None, truth: str) -> None:
    # Asserts the SDK's cost equals Anthropic's documented price.
    assert cost is not None, f"unpriced, expected ${truth}"
    assert cost == pytest.approx(float(Decimal(truth)), rel=PRICE_REL_TOLERANCE, abs=0.0)


# The two live payloads.


def test_live_opus_5_5_fast_payload_bills_the_fast_rate() -> None:
    # [Silent Failure] 13 x $8 + 6 x $40 per MTok. The SDK billed
    # $0.000172, the standard rate, on 2026-10-27.
    _assert_documented_price(_price("claude-opus-5-5", LIVE_FAST), "0.000344")


def test_live_opus_5_5_us_payload_bills_1_1x() -> None:
    # [Silent Failure] (13 x $4 + 6 x $20) x 1.1 per MTok. The SDK
    # billed $0.000172, without the residency multiplier, on 2026-10-27.
    _assert_documented_price(_price("claude-opus-5-5", LIVE_US), "0.0001892")


# Stacking.


def test_fast_and_us_stack_on_the_same_call() -> None:
    # [Silent Failure] Data residency applies on top of fast mode:
    # (13 x $8 + 6 x $40) x 1.1 per MTok.
    _assert_documented_price(_price("claude-opus-5-5", {**LIVE_FAST, "inference_geo": "us"}), "0.0003784")


def test_fast_cache_buckets_apply_caching_multipliers_on_the_fast_rate() -> None:
    # [Silent Failure] Opus 5.5 fast input is $8: 100 x $8, 1,000 5m
    # writes x $10 (1.25x), 1,000 1h writes x $16 (2x), 10,000 reads x
    # $0.40 (0.05x), 500 x $40 output.
    payload = _usage(100, 500, read=10_000, write_5m=1_000, write_1h=1_000, speed="fast", inference_geo="global")
    _assert_documented_price(_price("claude-opus-5-5", payload), "0.0508")


def test_fast_us_and_cache_all_stack() -> None:
    # [Silent Failure] The previous call, US-only: $0.0508 x 1.1.
    payload = _usage(100, 500, read=10_000, write_5m=1_000, write_1h=1_000, speed="fast", inference_geo="us")
    _assert_documented_price(_price("claude-opus-5-5", payload), "0.05588")


def test_us_applies_to_haiku_5_5_over_100k_tier() -> None:
    # [Edge Case] 121,000-token prompt bills the high tier: (1,000 x
    # $0.50 + 120,000 reads x $0.05 + 100 x $2.50) x 1.1 per MTok.
    payload = _usage(1_000, 100, read=120_000, speed="standard", inference_geo="us")
    _assert_documented_price(_price("claude-haiku-5-5", payload), "0.007425")


def test_us_applies_to_haiku_5_5_1h_writes_over_100k() -> None:
    # [Edge Case] Cache writes count toward the tier: (1,000 x $0.50 +
    # 110,000 1h writes x $1 + 100 x $2.50) x 1.1 per MTok.
    payload = _usage(1_000, 100, write_1h=110_000, speed="standard", inference_geo="us")
    _assert_documented_price(_price("claude-haiku-5-5", payload), "0.121825")


def test_us_on_haiku_5_5_at_exactly_100k_stays_on_the_base_tier() -> None:
    # [Edge Case] Only a prompt over 100,000 tokens bills the high tier:
    # (100,000 x $0.10 + 100 x $0.50) x 1.1 per MTok.
    payload = _usage(100_000, 100, speed="standard", inference_geo="us")
    _assert_documented_price(_price("claude-haiku-5-5", payload), "0.011055")


@pytest.mark.parametrize("model", ["claude-opus-5", "claude-opus-4-8"])
def test_opus_5_and_4_8_fast_bill_10_and_50(model: str) -> None:
    # [Silent Failure] 13 x $10 + 6 x $50 per MTok.
    _assert_documented_price(_price(model, _usage(13, 6, speed="fast", inference_geo="global")), "0.00043")


def test_opus_5_fast_cache_uses_its_own_0_1x_read_multiplier() -> None:
    # [Silent Failure] Opus 5 reads at 0.1x, not Opus 5.5's 0.05x:
    # 1,000 5m writes x $12.50 + 1,000 reads x $1.00 per MTok.
    _assert_documented_price(_price("claude-opus-5", _usage(read=1_000, write_5m=1_000, speed="fast")), "0.0135")


def test_a_dated_opus_5_5_id_prices_fast_at_the_fast_rate() -> None:
    # [Edge Case] A dated snapshot resolves to the base row's tier.
    _assert_documented_price(_price("claude-opus-5-5-20261101", LIVE_FAST), "0.000344")


# Standard rates stay exactly as they were.


def test_not_available_geo_bills_1x_identical_to_no_field() -> None:
    # [Hidden Assumption] Models before 4.6 report "not_available" and
    # always bill standard: 13 x $5 + 6 x $25 per MTok.
    cost = _price("claude-opus-4-5", _usage(13, 6, speed="standard", inference_geo="not_available"))
    _assert_documented_price(cost, "0.000215")
    assert cost == _price("claude-opus-4-5", _usage(13, 6))


@pytest.mark.parametrize("modifiers", [{"inference_geo": "global"}, {"inference_geo": None}, {"speed": "standard"}, {"speed": None}, {"speed": "standard", "inference_geo": "global"}])
def test_standard_reports_are_bit_identical_to_no_report(modifiers: dict[str, object]) -> None:
    # [Hidden Assumption] Global routing, standard speed, and an absent
    # or null report all bill exactly what a payload without them bills.
    payload = _usage(1_000, 200, read=5_000, write_5m=300, write_1h=400)
    assert _price("claude-opus-5-5", {**payload, **modifiers}) == _price("claude-opus-5-5", payload)


# Fail safe: never bill an unpriceable modifier at standard.


@pytest.mark.parametrize("model", ["claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-5-5", "claude-haiku-5-5"])
def test_fast_on_a_model_without_a_fast_rate_is_unpriced(model: str) -> None:
    # [Hidden Failure] A fast report the pricebook cannot price must not
    # bill at standard rates.
    assert _price(model, _usage(13, 6, speed="fast", inference_geo="global")) is None


@pytest.mark.parametrize("speed", ["turbo", "FAST", "", 1, True, {}])
def test_an_unknown_speed_is_unpriced(speed: object) -> None:
    # [Hidden Failure] A speed Anthropic adds later may carry a premium.
    assert _price("claude-opus-5-5", _usage(13, 6, speed=speed, inference_geo="global")) is None


@pytest.mark.parametrize("geo", ["eu", "US", "", 0, []])
def test_an_unknown_inference_geo_is_unpriced(geo: object) -> None:
    # [Hidden Failure] A geography Anthropic adds later may carry its
    # own multiplier.
    assert _price("claude-opus-5-5", _usage(13, 6, speed="standard", inference_geo=geo)) is None


def test_a_fast_tier_without_cache_rates_bills_cache_at_the_fast_input_rate() -> None:
    # [Hidden Assumption] A caller-registered fast tier follows
    # ModelPricing's rule: an unset cache rate bills at the input rate.
    registry = ModelPricingRegistry.default()
    registry.register(ANTHROPIC, "claude-custom", ModelPricing(input_per_million=4.0, output_per_million=20.0, cache_read_per_million=0.2, cache_write_per_million=5.0, tier_rates={"fast": {"input_per_million": 8.0, "output_per_million": 40.0}}))
    usage = AnthropicUsage.from_usage_payload(_usage(read=1_000, write_5m=1_000, speed="fast"))
    assert usage is not None
    _assert_documented_price(usage.cost_usd(registry.resolve(ANTHROPIC, "claude-custom")), "0.016")


# Pricebook pins.

# Fast input, cache read, 5m cache write and output per MTok. Anthropic
# publishes fast input and output; the cache rates are that model's
# caching multipliers applied on top (0.05x or 0.1x read, 1.25x write).
EXPECTED_FAST_RATES = {
    "claude-opus-5-5": (8.0, 0.4, 10.0, 40.0),
    "claude-opus-5": (10.0, 1.0, 12.5, 50.0),
    "claude-opus-4-8": (10.0, 1.0, 12.5, 50.0),
}


@pytest.mark.parametrize(("model", "rates"), EXPECTED_FAST_RATES.items())
def test_each_fast_capable_opus_row_carries_its_published_fast_rate(model: str, rates: tuple[float, float, float, float]) -> None:
    # [Silent Failure] The fast tier holds the published numbers.
    fast = (PROVIDER_PRICING[ANTHROPIC][model].tier_rates or {}).get("fast")
    assert fast is not None
    assert (fast["input_per_million"], fast["cached_input_per_million"], fast["cache_write_per_million"], fast["output_per_million"]) == rates


@pytest.mark.parametrize("model", EXPECTED_FAST_RATES)
def test_fast_cache_rates_keep_the_rows_own_caching_multipliers(model: str) -> None:
    # [Silent Failure] Fast cache rates are derived, so each must keep
    # the ratio to input that the row's standard rates publish.
    row = PROVIDER_PRICING[ANTHROPIC][model]
    fast = (row.tier_rates or {}).get("fast")
    assert fast is not None and row.cache_read_per_million is not None and row.cache_write_per_million is not None
    assert fast["cached_input_per_million"] / fast["input_per_million"] == pytest.approx(row.cache_read_per_million / row.input_per_million, rel=PRICE_REL_TOLERANCE)
    assert fast["cache_write_per_million"] / fast["input_per_million"] == pytest.approx(row.cache_write_per_million / row.input_per_million, rel=PRICE_REL_TOLERANCE)


def test_no_other_anthropic_row_offers_fast_mode() -> None:
    # [Hidden Assumption] Fast mode exists only on Opus 5.5, 5 and 4.8.
    assert {model for model, row in PROVIDER_PRICING[ANTHROPIC].items() if row.tier_rates} == set(EXPECTED_FAST_RATES)


# Integration.


def test_tracker_records_the_live_fast_call_at_the_fast_rate() -> None:
    # [Silent Failure] The tracker's ledger, not just the parser,
    # carries the fast price, and the rollup stays complete.
    tracker = UsageTracker()
    record = tracker.record_call(SimpleNamespace(provider="anthropic", model="claude-opus-5-5", usage=LIVE_FAST))
    assert record is not None
    _assert_documented_price(record.cost_usd, "0.000344")
    assert tracker.rollup().cost_complete is True


def test_tracker_keeps_an_unpriceable_call_visible_and_incomplete() -> None:
    # [Hidden Failure] An unknown speed keeps the call and its tokens on
    # the ledger, unpriced, so a fail-closed owner can refuse the bill.
    tracker = UsageTracker()
    record = tracker.record_call(SimpleNamespace(provider="anthropic", model="claude-opus-5-5", usage={**LIVE_FAST, "speed": "turbo"}))
    rollup = tracker.rollup()
    assert record is not None and record.cost_usd is None
    assert (rollup.model_call_count, rollup.input_tokens, rollup.output_tokens) == (1, 13, 6)
    assert rollup.cost_complete is False
    assert rollup.recording_integrity is UsageRecordingIntegrity.INTACT


def test_agent_run_bills_a_fast_us_anthropic_reply_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    # [Hidden Assumption] The Anthropic adapter forwards speed and
    # inference_geo to the tracker: (13 x $8 + 6 x $40) x 1.1 per MTok.
    body = {"id": "m1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [{"type": "text", "text": "ready"}], "stop_reason": "end_turn", "usage": {**LIVE_FAST, "inference_geo": "us"}}

    async def scripted(_transport: object, **_: Any) -> HttpResponse:
        return HttpResponse(status_code=200, body=json.dumps(body), headers={"content-type": "application/json"})

    monkeypatch.setattr(HttpTransport, "request", scripted)
    agent = Agent(name="a", system_prompt="Answer.", max_iterations=3, provider="anthropic", model_name="claude-opus-5-5", api_keys=["sk-ant-mock"], model_mode=TextModelMode.DIRECT)
    asyncio.run(agent.arun("hi"))
    rollup = agent.get_usage()
    assert rollup.model_call_count == 1
    _assert_documented_price(rollup.cost_usd, "0.0003784")
    assert rollup.cost_complete is True
