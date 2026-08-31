"""Context Protocol Header

Description:
    Feature tests for agent speed tracking: MathHelper, the speed dataclasses'
    validation, AgentSpeedTracker's accumulation/rollup logic, and BaseAgent's
    reset/run-boundary/get_speed_stats() wiring.
Purpose:
    Locks the behavior docs/design/agent-speed-tracking.md specifies: fail-open
    recording, validated dataclasses, a rollup that never double-counts, and a
    tracker lifecycle that mirrors UsageTracker's (reset every run, closed on
    every exit path including exceptions).
Architecture:
    - MathHelperTests: mean/percentile/max/argmax on plain sequences.
    - RecordModelCallInputValidationTests / CallSpeedRecordTests /
      ToolCallSpeedRecordTests: dataclass __post_init__ validation.
    - AgentSpeedTrackerRecordCallTests / AgentSpeedTrackerRecordToolCallTests:
      the tracker's fail-open recording contract.
    - AgentSpeedTrackerRollupTests: rollup composition and derived statistics.
    - AgentSpeedTrackerBaseAgentIntegrationTests: the real generate_reply()
      lifecycle through get_speed_stats().
Relations:
    Exercises vidbyte/lib/util/math.py, vidbyte/lib/dataclasses/speed.py,
    vidbyte/agents/speed/tracker.py, and vidbyte/agents/base.py.
Similar Files:
    - tests/test_agent_pricing.py
"""

from __future__ import annotations

import unittest

from tests.agent_test_support import build_test_agent
from vidbyte.agents.speed import AgentSpeedTracker
from vidbyte.lib.dataclasses.speed import (
    CallSpeedRecord,
    RecordModelCallInput,
    RecordToolCallInput,
    ToolCallSpeedRecord,
)
from vidbyte.lib.enums import AgentSpeedRecordingIntegrity
from vidbyte.lib.errors import AgentSpeedValidationError
from vidbyte.lib.util.math import MathHelper


class MathHelperTests(unittest.TestCase):
    def test_mean_or_none_returns_none_for_empty_sequence(self) -> None:
        self.assertIsNone(MathHelper.mean_or_none([]))

    def test_mean_or_none_returns_mean_for_populated_sequence(self) -> None:
        self.assertEqual(MathHelper.mean_or_none([10.0, 20.0, 30.0]), 20.0)

    def test_percentile_or_none_matches_nearest_rank_formula(self) -> None:
        values = [float(v) for v in range(1, 21)]  # 1..20
        # Nearest-rank at 0.95 over 20 sorted values: index = int(20 * 0.95) = 19 -> values[19] = 20.
        self.assertEqual(MathHelper.percentile_or_none(values, 0.95), 20.0)
        # At 0.0 the formula selects the smallest value.
        self.assertEqual(MathHelper.percentile_or_none(values, 0.0), 1.0)

    def test_percentile_or_none_rejects_fraction_outside_zero_one(self) -> None:
        with self.assertRaises(ValueError):
            MathHelper.percentile_or_none([1.0, 2.0], 1.5)

    def test_percentile_or_none_returns_none_for_empty_sequence(self) -> None:
        self.assertIsNone(MathHelper.percentile_or_none([], 0.95))

    def test_max_or_none_returns_none_for_empty_sequence(self) -> None:
        self.assertIsNone(MathHelper.max_or_none([]))

    def test_max_or_none_returns_the_largest_value(self) -> None:
        self.assertEqual(MathHelper.max_or_none([3.0, 9.0, 1.0]), 9.0)

    def test_argmax_index_returns_key_of_largest_value(self) -> None:
        self.assertEqual(MathHelper.argmax_index({1: 10.0, 2: 50.0, 3: 20.0}), 2)

    def test_argmax_index_returns_none_for_empty_mapping(self) -> None:
        self.assertIsNone(MathHelper.argmax_index({}))


class RecordModelCallInputValidationTests(unittest.TestCase):
    def test_negative_dispatched_at_raises(self) -> None:
        with self.assertRaises(AgentSpeedValidationError):
            RecordModelCallInput(response=object(), dispatched_at=-1.0)

    def test_first_token_at_before_dispatched_at_raises(self) -> None:
        with self.assertRaises(AgentSpeedValidationError):
            RecordModelCallInput(response=object(), dispatched_at=1.0, first_token_at=0.5)

    def test_none_response_raises(self) -> None:
        with self.assertRaises(AgentSpeedValidationError):
            RecordModelCallInput(response=None, dispatched_at=0.0)

    def test_negative_output_tokens_raises(self) -> None:
        with self.assertRaises(AgentSpeedValidationError):
            RecordModelCallInput(response=object(), dispatched_at=0.0, output_tokens=-5)

    def test_bool_retry_count_raises(self) -> None:
        # bool is an int subclass in Python; True must not silently pass as 1.
        with self.assertRaises(AgentSpeedValidationError):
            RecordModelCallInput(response=object(), dispatched_at=0.0, retry_count=True)


class CallSpeedRecordTests(unittest.TestCase):
    def test_duration_ms_is_completed_minus_dispatched_in_milliseconds(self) -> None:
        record = CallSpeedRecord(call_index=1, provider="anthropic", model="claude", dispatched_at=1.0, completed_at=1.25)
        self.assertAlmostEqual(record.duration_ms, 250.0)

    def test_ttft_ms_is_none_when_first_token_at_is_none(self) -> None:
        record = CallSpeedRecord(call_index=1, provider="anthropic", model="claude", dispatched_at=1.0, completed_at=1.5)
        self.assertIsNone(record.ttft_ms)

    def test_tokens_per_second_is_none_when_output_tokens_is_none(self) -> None:
        record = CallSpeedRecord(call_index=1, provider="anthropic", model="claude", dispatched_at=1.0, completed_at=1.5)
        self.assertIsNone(record.tokens_per_second)

    def test_tokens_per_second_uses_post_ttft_window_not_full_duration(self) -> None:
        # Prefill takes 1s (dispatched_at=0 -> first_token_at=1), then 50 tokens generate over 1s.
        # tokens/sec must be 50/1, not 50/2 (which would use the full dispatch-to-completion span).
        record = CallSpeedRecord(
            call_index=1, provider="anthropic", model="claude",
            dispatched_at=0.0, first_token_at=1.0, completed_at=2.0, output_tokens=50,
        )
        self.assertAlmostEqual(record.tokens_per_second, 50.0)

    def test_completed_at_before_dispatched_at_raises(self) -> None:
        with self.assertRaises(AgentSpeedValidationError):
            CallSpeedRecord(call_index=1, provider="anthropic", model="claude", dispatched_at=2.0, completed_at=1.0)


class ToolCallSpeedRecordTests(unittest.TestCase):
    def test_empty_tool_name_raises(self) -> None:
        with self.assertRaises(AgentSpeedValidationError):
            ToolCallSpeedRecord(call_index=1, tool_name="", started_at=0.0, completed_at=0.1)

    def test_whitespace_only_tool_name_raises(self) -> None:
        with self.assertRaises(AgentSpeedValidationError):
            ToolCallSpeedRecord(call_index=1, tool_name="   ", started_at=0.0, completed_at=0.1)


class _FakeModelResponse:
    """Minimal duck-typed model response carrying only provider/model, like UsageTracker expects."""

    def __init__(self, provider: str = "anthropic", model: str = "claude-sonnet-5") -> None:
        self.provider = provider
        self.model = model


class _NoProviderResponse:
    """A response with neither provider nor model set, to exercise the fail-open path."""


class AgentSpeedTrackerRecordCallTests(unittest.TestCase):
    def test_record_call_returns_none_and_marks_corrupted_when_response_has_no_provider(self) -> None:
        tracker = AgentSpeedTracker()
        record = tracker.record_call(RecordModelCallInput(response=_NoProviderResponse(), dispatched_at=0.0))
        self.assertIsNone(record)
        self.assertTrue(tracker.recording_corrupted)

    def test_record_call_assigns_sequential_call_index_starting_at_one(self) -> None:
        tracker = AgentSpeedTracker()
        first = tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=0.0))
        second = tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=0.0))
        self.assertEqual(first.call_index, 1)
        self.assertEqual(second.call_index, 2)

    def test_record_call_never_raises_when_stringifying_provider_would_be_empty(self) -> None:
        # A response whose provider/model attributes exist but stringify to "" must be
        # treated as unusable, not allowed to raise AgentSpeedValidationError out of record_call.
        tracker = AgentSpeedTracker()
        record = tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(provider="", model=""), dispatched_at=0.0))
        self.assertIsNone(record)
        self.assertTrue(tracker.recording_corrupted)


class AgentSpeedTrackerRecordToolCallTests(unittest.TestCase):
    def test_record_tool_call_marks_timed_out_true_when_flagged(self) -> None:
        tracker = AgentSpeedTracker()
        record = tracker.record_tool_call(RecordToolCallInput(tool_name="search", started_at=0.0, timed_out=True))
        self.assertTrue(record.timed_out)

    def test_record_tool_call_assigns_sequential_call_index_starting_at_one(self) -> None:
        tracker = AgentSpeedTracker()
        first = tracker.record_tool_call(RecordToolCallInput(tool_name="search", started_at=0.0))
        second = tracker.record_tool_call(RecordToolCallInput(tool_name="search", started_at=0.0))
        self.assertEqual(first.call_index, 1)
        self.assertEqual(second.call_index, 2)


class AgentSpeedTrackerRollupTests(unittest.TestCase):
    def setUp(self) -> None:
        # A fake, manually-advanced clock keeps every duration deterministic.
        self._now = 0.0
        self.tracker = AgentSpeedTracker(clock=self._clock)

    def _clock(self) -> float:
        return self._now

    def _advance(self, seconds: float) -> None:
        self._now += seconds

    def test_rollup_with_zero_calls_returns_empty_stats_not_error(self) -> None:
        rollup = self.tracker.rollup()
        self.assertEqual(rollup.call_stats.call_count, 0)
        self.assertEqual(rollup.tool_call_stats.tool_call_count, 0)
        self.assertIsNone(rollup.call_stats.duration_ms_mean)

    def test_rollup_is_idempotent_when_called_twice_without_new_records(self) -> None:
        dispatched_at = self.tracker.now()
        self._advance(0.01)
        self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        first = self.tracker.rollup()
        second = self.tracker.rollup()
        self.assertEqual(first.call_stats, second.call_stats)

    def test_rollup_call_duration_percentiles_match_manually_computed_values(self) -> None:
        for duration_seconds in (0.01, 0.02, 0.03, 0.04, 0.05):
            dispatched_at = self.tracker.now()
            self._advance(duration_seconds)
            self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        stats = self.tracker.rollup().call_stats
        durations_ms = sorted(call.duration_ms for call in self.tracker.calls)
        expected_p50 = durations_ms[int(len(durations_ms) * 0.50)]
        self.assertAlmostEqual(stats.duration_ms_p50, expected_p50)

    def test_rollup_slowest_call_index_points_at_the_actual_slowest_call(self) -> None:
        for duration_seconds in (0.01, 0.05, 0.02):
            dispatched_at = self.tracker.now()
            self._advance(duration_seconds)
            self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        stats = self.tracker.rollup().call_stats
        self.assertEqual(stats.slowest_call_index, 2)

    def test_rollup_cold_start_overhead_is_none_with_only_one_call(self) -> None:
        dispatched_at = self.tracker.now()
        self._advance(0.01)
        self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        self.assertIsNone(self.tracker.rollup().run_stats.cold_start_overhead_ms)

    def test_rollup_cold_start_overhead_positive_when_first_call_is_slower(self) -> None:
        dispatched_at = self.tracker.now()
        self._advance(0.05)
        self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        for _ in range(2):
            dispatched_at = self.tracker.now()
            self._advance(0.01)
            self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        overhead = self.tracker.rollup().run_stats.cold_start_overhead_ms
        self.assertGreater(overhead, 0)

    def test_rollup_framework_overhead_accounts_for_total_minus_call_and_tool_time(self) -> None:
        self.tracker.record_run_start()
        dispatched_at = self.tracker.now()
        self._advance(0.01)
        self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        self._advance(0.005)  # framework-only time between the call and the run ending
        self.tracker.record_run_end()
        stats = self.tracker.rollup().run_stats
        self.assertAlmostEqual(stats.framework_overhead_ms, 5.0, delta=0.5)

    def test_rollup_parallelism_efficiency_reflects_overlapping_tool_calls(self) -> None:
        # Two tool calls that fully overlap: each takes 0.02s, but wall-clock is only 0.02s.
        first_started_at = self.tracker.now()
        second_started_at = self.tracker.now()
        self._advance(0.02)
        self.tracker.record_tool_call(RecordToolCallInput(tool_name="a", started_at=first_started_at))
        self.tracker.record_tool_call(RecordToolCallInput(tool_name="b", started_at=second_started_at))
        efficiency = self.tracker.rollup().run_stats.parallelism_efficiency
        self.assertGreater(efficiency, 1.5)  # ~2x: two 0.02s calls finished within one 0.02s window

    def test_rollup_recording_integrity_is_corrupted_after_an_unusable_call(self) -> None:
        self.tracker.record_call(RecordModelCallInput(response=_NoProviderResponse(), dispatched_at=0.0))
        self.assertEqual(self.tracker.rollup().recording_integrity, AgentSpeedRecordingIntegrity.CORRUPTED)

    def test_reset_clears_every_ledger_and_run_boundary(self) -> None:
        self.tracker.record_run_start()
        dispatched_at = self.tracker.now()
        self._advance(0.01)
        self.tracker.record_call(RecordModelCallInput(response=_FakeModelResponse(), dispatched_at=dispatched_at))
        self.tracker.record_run_end()
        self.tracker.reset()
        rollup = self.tracker.rollup()
        self.assertEqual(rollup.call_stats.call_count, 0)
        self.assertIsNone(rollup.run_stats.total_duration_ms)


class _FinalAnswerRunner:
    """Offline runner returning one TextModelResponse-shaped final answer."""

    def __init__(self, provider: str = "openai", model: str = "fake") -> None:
        self._provider = provider
        self._model = model

    def run(self, prompt: str, *, system: str | None = None, **_: object) -> object:
        return _FakeModelResponse(provider=self._provider, model=self._model)


class _FailingRunner:
    """Offline runner that always raises, to exercise the exception exit path."""

    def run(self, prompt: str, **_: object) -> object:
        raise RuntimeError("simulated provider failure")


class AgentSpeedTrackerBaseAgentIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_reply_populates_get_speed_stats_with_a_real_call(self) -> None:
        agent = build_test_agent(
            name="worker",
            system_prompt="Work carefully.",
            runner=_FinalAnswerRunner(),
        )
        await agent.generate_reply("task")
        stats = agent.get_speed_stats()
        self.assertGreaterEqual(stats.call_stats.call_count, 1)
        self.assertIsNotNone(stats.run_stats.total_duration_ms)

    async def test_second_run_does_not_blend_stats_from_the_first(self) -> None:
        agent = build_test_agent(
            name="worker",
            system_prompt="Work carefully.",
            runner=_FinalAnswerRunner(),
        )
        await agent.generate_reply("first task")
        first_call_count = agent.get_speed_stats().call_stats.call_count
        await agent.generate_reply("second task")
        second_call_count = agent.get_speed_stats().call_stats.call_count
        self.assertEqual(first_call_count, second_call_count)

    async def test_run_that_raises_still_records_run_end(self) -> None:
        from vidbyte.lib.errors import AgentExecutionError

        agent = build_test_agent(
            name="worker",
            system_prompt="Work carefully.",
            runner=_FailingRunner(),
        )
        with self.assertRaises(AgentExecutionError):
            await agent.generate_reply("task")
        stats = agent.get_speed_stats()
        self.assertIsNotNone(stats.run_stats.total_duration_ms)


if __name__ == "__main__":
    unittest.main()
