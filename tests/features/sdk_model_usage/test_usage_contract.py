"""FILE: tests/features/sdk_model_usage/test_usage_contract.py

PURPOSE: Probe malformed provider usage through the real per-run model usage ledger, without issuing model calls.
ROLE IN CODEBASE: Exercises vidbyte/agents/pricing/base.py and openrouter.py via UsageTracker; complements tests/test_agent_pricing.py.
ARCHITECTURE NOTE: A SimpleNamespace stands in for response metadata, while parsing, pricing and rollup all remain production code.
FUNCTION INVENTORY: test_negative_count_corrupts_ledger tests primary and nested counters; test_negative_billed_failure_corrupts_ledger tests failed calls; test_invalid_marketplace_cost_falls_back tests a tariff; test_invalid_marketplace_cost_without_tariff_stays_unpriced tests integrity; test_zero_values_are_valid tests valid boundaries.
COMMON MODIFICATION PATTERNS: Add provider-shaped payloads when a new model usage parser is added; assert both call records and rollup integrity.
WHAT NOT TO DO IN THIS FILE: 1. Do not call providers; vidbyte/providers/ owns HTTP. 2. Do not add rates; vidbyte/lib/registries/pricing.py owns the table.
KNOWN EDGE CASES: Nested negative cached counts can lower billed cost despite positive total input; invalid marketplace cost can bypass a missing table price.
RELATED DOCS: tests/features/sdk_model_usage/FEATURE.md documents this accounting contract.
TESTS: This module and scripts/run_ci.py source gate.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from vidbyte.agents.pricing import UsageTracker
from vidbyte.lib.enums import ModelProvider, UsageKind
from vidbyte.lib.registries.pricing import ModelPricing, ModelPricingRegistry


@pytest.mark.parametrize("payload", [
    {"input_tokens": -1_000_000, "output_tokens": 1},
    {"input_tokens": 100, "output_tokens": 1, "input_tokens_details": {"cached_tokens": -5}},
    {"input_tokens": 100, "output_tokens": 1, "total_tokens": -1},
])
def test_negative_count_corrupts_ledger(payload: dict[str, object]) -> None:
    tracker = UsageTracker()
    response = SimpleNamespace(provider=ModelProvider.OPENAI, model="gpt-5.4-mini", usage=payload)
    assert tracker.record_call(response) is None
    assert tracker.recording_corrupted
    assert tracker.rollup().model_call_count == 0


def test_negative_billed_failure_corrupts_ledger() -> None:
    tracker = UsageTracker()
    assert tracker.record_billed_failure(
        ModelProvider.OPENAI, "gpt-5.4-mini", {"input_tokens": 5, "output_tokens": -2}, kind=UsageKind.GENERATIVE
    ) is None
    assert tracker.recording_corrupted


@pytest.mark.parametrize("reported", [-1.0, math.nan, math.inf, -math.inf, True, "0.25"])
def test_invalid_marketplace_cost_falls_back(reported: object) -> None:
    registry = ModelPricingRegistry.default()
    registry.register(ModelProvider.OPENROUTER, "test-model", ModelPricing(input_per_million=1, output_per_million=2))
    tracker = UsageTracker(pricing=registry)
    response = SimpleNamespace(provider=ModelProvider.OPENROUTER, model="test-model", usage={"prompt_tokens": 100, "completion_tokens": 20, "cost": reported})
    record = tracker.record_call(response)
    assert record is not None
    assert record.cost_usd == pytest.approx(0.00014)
    assert tracker.rollup().cost_complete


def test_invalid_marketplace_cost_without_tariff_stays_unpriced() -> None:
    tracker = UsageTracker()
    response = SimpleNamespace(provider=ModelProvider.OPENROUTER, model="unknown-model", usage={"prompt_tokens": 1, "completion_tokens": 1, "cost": math.inf})
    record = tracker.record_call(response)
    assert record is not None
    assert record.cost_usd is None
    assert tracker.rollup().cost_complete is False


def test_zero_values_are_valid() -> None:
    tracker = UsageTracker()
    response = SimpleNamespace(provider=ModelProvider.OPENROUTER, model="unknown-model", usage={"prompt_tokens": 0, "completion_tokens": 0, "cost": 0})
    record = tracker.record_call(response)
    assert record is not None
    assert record.cost_usd == 0
    assert tracker.rollup().cost_complete
