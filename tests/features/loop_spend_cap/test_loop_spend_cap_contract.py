"""FILE: tests/features/loop_spend_cap/test_loop_spend_cap_contract.py

PURPOSE: Pin the public shapes of the loop spend cap: which cap values the settings
and the runtime config accept, the derived UsageRollup.cost_measured flag, the new
stop reason, and the stateless AgentSpendCap policy's exact stop texts and boundaries.
ROLE IN CODEBASE: Covers spec AC-2, AC-3, AC-19, INV-2, INV-4, INV-9, INV-14, T-3,
EC-1 to EC-4, EC-25, D-7 and D-16 for vidbyte/agents/settings/loop.py,
vidbyte/lib/dataclasses/agents.py, vidbyte/agents/pricing/records.py and
vidbyte/agents/spend_cap.py.
ARCHITECTURE NOTE: Pure constructor, record and policy checks with no agent run.
Rollups come from a real UsageTracker over the default pricebook, so every record is
one the ledger can actually produce; AgentSpendCap is imported inside the tests that
use it, so the other tests fail on their own missing name before the module exists.
FUNCTION INVENTORY: test_settings_reject_each_invalid_cap_and_name_the_field;
test_settings_accept_valid_caps_unchanged; test_cap_error_never_echoes_a_long_value;
test_runtime_config_carries_the_cap_and_repr_shows_it;
test_runtime_config_rejects_each_invalid_cap;
test_cost_measured_follows_inv2_for_every_combination;
test_empty_rollup_is_measured_although_cost_is_not_complete;
test_cost_measured_is_derived_and_read_only;
test_max_spend_stop_reason_is_not_a_deliverable_answer;
test_spend_cap_policy_is_exported_from_its_own_module_only;
test_stop_output_is_reached_at_exactly_the_cap_and_not_one_step_below;
test_stop_output_reports_reached_before_blind;
test_stop_output_names_every_blind_cause_in_spec_order;
test_stop_output_names_a_lone_cause_without_separators.
COMMON MODIFICATION PATTERNS: A new blind-meter cause adds one case to the
every-cause test in the spec's order; a new accepted or rejected cap value joins
INVALID_CAPS or the valid parametrization.
WHAT NOT TO DO IN THIS FILE: 1. Do not hard-code a dollar figure; take costs from a
tracker. 2. Do not compare against FailureCode order or the public API contract;
the harness pins and lint C016 own them. 3. Do not import AgentSpendCap at module
level.
KNOWN EDGE CASES: 5e-324, the smallest positive float, is a valid cap (INV-14). An
int beyond float range raises OverflowError inside the shared validator, a quirk the
spec documents and this file deliberately does not pin.
RELATED DOCS: docs/spec/loop-spend-cap/spec.md sections 6.1, 6.2, 8.5 and 9.2;
tests/features/loop_spend_cap/FEATURE.md.
TESTS: PYTHONPATH=$(pwd) py -3.11 -m pytest -q tests/features/loop_spend_cap/test_loop_spend_cap_contract.py
"""

from __future__ import annotations

import dataclasses
import importlib
import itertools
import math
import sys

import pytest

from tests.features.loop_spend_cap.loop_spend_cap_fixtures import (
    PRICED_MODEL,
    REACHED_TEXT,
    UNPRICED_MODEL,
    assert_price_preconditions,
    blind_text,
    text_response,
    usage,
)
from vidbyte.agents.pricing import UsageTracker
from vidbyte.agents.pricing.records import UsageRecordingIntegrity
from vidbyte.agents.settings import AgentLoopSettings
from vidbyte.lib.constants.outputs import OUTPUT_DELIVERABLE_STOP_REASONS
from vidbyte.lib.dataclasses.agents import AgentRuntimeConfig, AgentStopReason
from vidbyte.lib.enums import ModelProvider
from vidbyte.lib.errors import ConfigurationError

# AC-2's rejected values, in the spec's order.
INVALID_CAPS = (True, float("nan"), float("inf"), -float("inf"), 0, -1, "5")


def _spend_cap() -> type:
    # Imported here so the other tests still fail on their own missing name before the module exists.
    from vidbyte.agents.spend_cap import AgentSpendCap

    return AgentSpendCap


def _ledger_parts() -> tuple:
    # One priced call, one unpriced call, one priced operation, and one unpriced operation, as a real ledger records them.
    assert_price_preconditions()
    tracker = UsageTracker()
    tracker.record_call(text_response("a", usage=usage(100, 10)))
    tracker.record_call(text_response("b", usage=usage(100, 10), model=UNPRICED_MODEL))
    tracker.record_operation("search", "brave", reported_cost_usd=0.01)
    tracker.record_operation("search", "unpriced-probe")
    rollup = tracker.rollup()
    (priced_call, unpriced_call), (priced_op, unpriced_op) = (
        rollup.calls,
        rollup.operations,
    )
    assert priced_call.cost_usd is not None and unpriced_call.cost_usd is None
    assert priced_op.cost_usd is not None and unpriced_op.cost_usd is None
    return rollup, priced_call, unpriced_call, priced_op, unpriced_op


@pytest.mark.parametrize("value", INVALID_CAPS)
def test_settings_reject_each_invalid_cap_and_name_the_field(value: object) -> None:
    # AC-2, EC-1 to EC-4, INV-14: NaN would make `spend >= cap` always False and silently uncap the run.
    with pytest.raises(
        ConfigurationError, match=r"AgentLoopSettings\.max_spend_usd"
    ) as caught:
        AgentLoopSettings(max_spend_usd=value)
    assert caught.value.details["field"] == "AgentLoopSettings.max_spend_usd"


@pytest.mark.parametrize("value", [1, 0.25, None, 5e-324, sys.float_info.max])
def test_settings_accept_valid_caps_unchanged(value: float | None) -> None:
    settings = AgentLoopSettings(max_spend_usd=value)
    assert settings.max_spend_usd == value
    assert settings.to_runtime_config().max_spend_usd == value


def test_cap_error_never_echoes_a_long_value() -> None:
    # T-3: refusal messages name the field, never a long or secret-looking value.
    value = "x" * 400
    with pytest.raises(
        ConfigurationError, match=r"AgentLoopSettings\.max_spend_usd"
    ) as caught:
        AgentLoopSettings(max_spend_usd=value)
    assert value not in str(caught.value)


def test_runtime_config_carries_the_cap_and_repr_shows_it() -> None:
    # AC-3, FR-2: to_runtime_config() is how the runtime learns the cap; a dropped field means an uncapped run.
    settings = AgentLoopSettings(max_spend_usd=2.5)
    assert settings.to_runtime_config().max_spend_usd == 2.5
    assert "max_spend_usd=2.5" in repr(settings)
    assert AgentRuntimeConfig().max_spend_usd is None


@pytest.mark.parametrize("value", INVALID_CAPS)
def test_runtime_config_rejects_each_invalid_cap(value: object) -> None:
    # AC-3: AgentRuntime can be built without AgentLoopSettings, so its config validates on its own.
    with pytest.raises(
        ConfigurationError, match=r"AgentRuntimeConfig\.max_spend_usd"
    ) as caught:
        AgentRuntimeConfig(max_spend_usd=value)
    assert caught.value.details["field"] == "AgentRuntimeConfig.max_spend_usd"


@pytest.mark.parametrize(
    ("calls_priced", "operations_priced", "unaccounted", "integrity"),
    list(
        itertools.product(
            (True, False), (True, False), (0, 1), tuple(UsageRecordingIntegrity)
        )
    ),
)
def test_cost_measured_follows_inv2_for_every_combination(
    calls_priced: bool,
    operations_priced: bool,
    unaccounted: int,
    integrity: UsageRecordingIntegrity,
) -> None:
    # AC-19, INV-2: exhaustive over the four conditions; any single gap must read as unmeasured.
    rollup, priced_call, unpriced_call, priced_op, unpriced_op = _ledger_parts()
    case = dataclasses.replace(
        rollup,
        calls=(priced_call,) if calls_priced else (priced_call, unpriced_call),
        operations=(priced_op,) if operations_priced else (priced_op, unpriced_op),
        unaccounted_call_count=unaccounted,
        recording_integrity=integrity,
    )
    expected = (
        calls_priced
        and operations_priced
        and unaccounted == 0
        and integrity is UsageRecordingIntegrity.INTACT
    )
    assert case.cost_measured is expected


def test_empty_rollup_is_measured_although_cost_is_not_complete() -> None:
    # INV-2, D-7: an empty ledger spent nothing, so it is measured; cost_complete keeps its old meaning (False).
    rollup = UsageTracker().rollup()
    assert rollup.cost_measured is True
    assert rollup.cost_complete is False


def test_cost_measured_is_derived_and_read_only() -> None:
    # INV-2, section 9.1: a stored flag could disagree with the records; a derived one cannot.
    rollup = _ledger_parts()[0]
    assert rollup.cost_measured is False
    assert "cost_measured" not in {field.name for field in dataclasses.fields(rollup)}
    # A frozen slots dataclass refuses the write with AttributeError or, for a non-field name, TypeError.
    with pytest.raises((AttributeError, TypeError)):
        rollup.cost_measured = True  # type: ignore[misc]
    assert rollup.cost_measured is False


def test_max_spend_stop_reason_is_not_a_deliverable_answer() -> None:
    # FR-5, INV-9: callers match the value "max_spend"; a cap stop never reaches output connectors as an answer.
    assert AgentStopReason.MAX_SPEND.value == "max_spend"
    assert AgentStopReason("max_spend") is AgentStopReason.MAX_SPEND
    assert AgentStopReason.MAX_SPEND.value not in OUTPUT_DELIVERABLE_STOP_REASONS


def test_spend_cap_policy_is_exported_from_its_own_module_only() -> None:
    # D-16, AC-24: the policy adds no root or package export, so the public API contract stays unchanged.
    spend_cap = importlib.import_module("vidbyte.agents.spend_cap")
    assert spend_cap.__all__ == ["AgentSpendCap"]
    for path in ("vidbyte", "vidbyte.agents"):
        package = importlib.import_module(path)
        assert "AgentSpendCap" not in getattr(package, "__all__", ()), path
        assert not hasattr(package, "AgentSpendCap"), path


def test_stop_output_is_reached_at_exactly_the_cap_and_not_one_step_below() -> None:
    # EC-25, INV-4(a): ">=" stops at exactly the cap; a strict ">" would let one more segment spend.
    spend_cap = _spend_cap()
    tracker = UsageTracker()
    tracker.record_call(text_response("a", usage=usage(1_000, 100)))
    rollup = tracker.rollup()
    spent = rollup.cost_usd
    assert spent is not None and spent > 0
    assert spend_cap.stop_output(spent, rollup) == REACHED_TEXT
    assert spend_cap.stop_output(spent / 2, rollup) == REACHED_TEXT
    assert spend_cap.stop_output(math.nextafter(spent, math.inf), rollup) is None
    assert spend_cap.stop_output(1.0, UsageTracker().rollup()) is None


def test_stop_output_reports_reached_before_blind() -> None:
    # INV-4: condition (a) is evaluated first, so a run that reached the cap says so even when the meter is also blind.
    spend_cap = _spend_cap()
    tracker = UsageTracker()
    tracker.record_call(text_response("a", usage=usage(1_000, 100)))
    tracker.record_call(text_response("b", usage=None))
    rollup = tracker.rollup()
    spent = rollup.cost_usd
    assert spent is not None
    assert spend_cap.stop_output(spent, rollup) == REACHED_TEXT
    assert spend_cap.stop_output(math.nextafter(spent, math.inf), rollup) == blind_text(
        "1 model calls reported no usage"
    )


def test_stop_output_names_every_blind_cause_in_spec_order() -> None:
    # INV-9: unpriced models (distinct, sorted), then unpriced operations (distinct, sorted), then the
    # unaccounted count, then the corruption flag, joined by "; " - names and counts only (T-3).
    spend_cap = _spend_cap()
    assert_price_preconditions()
    second_unpriced = UNPRICED_MODEL + "-b"
    tracker = UsageTracker()
    tracker.record_call(
        text_response("priced", usage=usage(100, 10), model=PRICED_MODEL)
    )
    tracker.record_call(text_response("b", usage=usage(10, 1), model=second_unpriced))
    tracker.record_call(text_response("a", usage=usage(10, 1), model=UNPRICED_MODEL))
    tracker.record_call(
        text_response("a again", usage=usage(10, 1), model=UNPRICED_MODEL)
    )
    tracker.record_call(
        text_response(
            "routed",
            usage={"prompt_tokens": 10, "completion_tokens": 1},
            provider=ModelProvider.OPENROUTER,
            model="vendor/model-a",
        )
    )
    tracker.record_operation("search", "zeta-probe")
    tracker.record_operation("fetch", "alpha-probe")
    tracker.record_operation("search", "zeta-probe")
    tracker.record_call(text_response("no usage", usage=None))
    tracker.record_call(text_response("no usage again", usage=None))
    tracker.mark_recording_corrupted()
    rollup = tracker.rollup()
    assert rollup.cost_usd is not None and rollup.cost_usd < 1.0

    assert spend_cap.stop_output(1.0, rollup) == blind_text(
        f"no price for openai:{UNPRICED_MODEL}, openai:{second_unpriced}, openrouter:vendor/model-a",
        "no price for operation alpha-probe:fetch, zeta-probe:search",
        "2 model calls reported no usage",
        "usage recording failed",
    )


@pytest.mark.parametrize("cause", ["corrupted", "operation"])
def test_stop_output_names_a_lone_cause_without_separators(cause: str) -> None:
    # INV-9: each cause stands alone when it is the only one; the corrupted ledger is otherwise invisible in cost_usd.
    spend_cap = _spend_cap()
    tracker = UsageTracker()
    tracker.record_call(text_response("priced", usage=usage(100, 10)))
    if cause == "corrupted":
        tracker.mark_recording_corrupted()
        expected = blind_text("usage recording failed")
    else:
        tracker.record_operation("search", "unpriced-probe")
        expected = blind_text("no price for operation unpriced-probe:search")
    assert spend_cap.stop_output(1.0, tracker.rollup()) == expected
