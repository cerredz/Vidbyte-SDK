"""FILE: tests/features/sdk_operation_costs/test_operation_cost_contract.py

PURPOSE: Exercise public operation-accounting inputs through UsageTracker; do not verify vendor pricing publications here.
ROLE IN CODEBASE: Calls vidbyte.agents.pricing.UsageTracker with the default registry in vidbyte/lib/registries/operation_pricing.py.
ARCHITECTURE NOTE: No provider calls; the operation ledger and its rollup remain real rather than mocked.
FUNCTION INVENTORY: test_invalid_units_never_enter_usage tests counts; test_reported_cost_must_be_finite tests fallback and unpriced outcomes; test_finite_reported_cost_overrides_table tests precedence. Run this file with pytest.
COMMON MODIFICATION PATTERNS: Add a malformed provider result as a parametrized case and assert both the record and the rollup.
WHAT NOT TO DO IN THIS FILE: 1. Do not add vendor tariff rates; vidbyte/lib/registries/operation_pricing.py owns those. 2. Do not issue network calls; vidbyte/providers/ owns adapters.
KNOWN EDGE CASES: Infinity compares as non-negative; bool inherits int; malformed reported costs must not poison an otherwise valid table rate.
RELATED DOCS: tests/features/sdk_operation_costs/FEATURE.md defines the public operation-cost contract for these probes.
TESTS: This module; scripts/run_ci.py runs the full suite.
"""

from __future__ import annotations

import math

import pytest

from vidbyte.agents.pricing import UsageTracker


@pytest.mark.parametrize("units", [-3, 0, True, 1.5, "2"])
def test_invalid_units_never_enter_usage(units: object) -> None:
    usage = UsageTracker()
    assert usage.record_operation("fetch", "firecrawl", units=units) is None
    assert usage.rollup().operation_count == 0


@pytest.mark.parametrize("reported", [float("inf"), -math.inf, float("nan"), -1, True, "0.01"])
def test_reported_cost_must_be_finite(reported: object) -> None:
    usage = UsageTracker()
    record = usage.record_operation("fetch", "firecrawl", units=2, reported_cost_usd=reported)
    assert record is not None
    assert record.cost_usd == pytest.approx(0.00166)
    assert usage.rollup().cost_usd == record.cost_usd
    assert usage.rollup().cost_complete


def test_invalid_reported_cost_with_no_tariff_stays_unpriced() -> None:
    usage = UsageTracker()
    record = usage.record_operation("fetch", "unknown_provider", reported_cost_usd=math.inf)
    assert record is not None
    assert record.cost_usd is None
    assert usage.rollup().cost_complete is False


def test_finite_reported_cost_overrides_table() -> None:
    usage = UsageTracker()
    record = usage.record_operation("fetch", "firecrawl", units=2, reported_cost_usd=0.0)
    assert record is not None
    assert record.cost_usd == 0.0
    assert usage.rollup().cost_complete
