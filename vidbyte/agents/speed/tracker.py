"""Context Protocol Header

Description:
    Per-run accumulator turning timed model calls and tool calls into a speed
    rollup, mirroring UsageTracker's role for cost.
Purpose:
    Owns the run's timing ledger so the agent runtime can record each model
    call and tool call once and BaseAgent.get_speed_stats() can expose live or
    final speed statistics.
Architecture:
    - AgentSpeedTracker: mutable per-run store holding three ledgers (model
      calls, tool calls, loop steps) plus the run's start/end wall-clock marks.
    - rollup() is a thin orchestrator over four private _build_*_stats helpers,
      each producing one nested stats dataclass; no aggregation math lives in
      rollup() itself.
Key Functions:
    - record_call: Duck-types provider/model off the response, prices nothing,
      stores one CallSpeedRecord. Returns None and marks corrupted when the
      response is unusable, exactly like UsageTracker.record_call.
    - record_tool_call: Stores one ToolCallSpeedRecord.
    - record_step: Stores one StepSpeedRecord. Not yet called by runtime.py.
    - rollup: Folds all three ledgers into an immutable AgentSpeedRollup.
Relations:
    Created by BaseAgent, consumed by AgentRuntime; dataclasses from
    vidbyte/lib/dataclasses/speed.py, math from vidbyte/lib/util/math.py.
Similar Files:
    - vidbyte/agents/pricing/tracker.py (UsageTracker)
"""

from __future__ import annotations

import time
from collections.abc import Callable

from vidbyte.lib.dataclasses.speed import (
    AgentSpeedRollup,
    CallSpeedRecord,
    CallSpeedStats,
    RecordModelCallInput,
    RecordStepInput,
    RecordToolCallInput,
    RunSpeedStats,
    StepSpeedRecord,
    StepSpeedStats,
    ToolCallSpeedRecord,
    ToolCallSpeedStats,
)
from vidbyte.lib.enums.speed import AgentSpeedRecordingIntegrity
from vidbyte.lib.errors import AgentSpeedValidationError
from vidbyte.lib.util.math import MathHelper


class AgentSpeedTracker:
    """Accumulates timed model-call, tool-call, and run-boundary records for one agent run."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        # `clock` defaults to time.monotonic but accepts an override so a caller can bind
        # the same clock AgentRuntime already uses for elapsed_seconds (self.middleware.clock),
        # keeping every timestamp in a run comparable and letting tests inject a fake clock.
        self._clock = clock or time.monotonic
        self._calls: list[CallSpeedRecord] = []
        self._tool_calls: list[ToolCallSpeedRecord] = []
        self._steps: list[StepSpeedRecord] = []
        self._run_started_at: float | None = None
        self._run_completed_at: float | None = None
        self._recording_corrupted = False

    def now(self) -> float:
        """Return the tracker's clock reading. Call before awaiting the thing being timed."""
        return self._clock()

    def record_run_start(self) -> None:
        """Mark the run's wall-clock start. Call once at the top of generate_reply."""
        self._run_started_at = self._clock()

    def record_run_end(self) -> None:
        """Mark the run's wall-clock end. Call on every exit path of generate_reply."""
        self._run_completed_at = self._clock()

    def mark_recording_corrupted(self) -> None:
        """Flag that a real timing record was lost to an internal error, not a legitimate skip."""
        self._recording_corrupted = True

    @property
    def recording_corrupted(self) -> bool:
        """Return whether any call this run swallowed an exception while recording timing."""
        return self._recording_corrupted

    def record_call(self, call_input: RecordModelCallInput) -> CallSpeedRecord | None:
        """Time one model call and store it. Returns None when the response is unusable."""
        provider = getattr(call_input.response, "provider", None)
        model = getattr(call_input.response, "model", None)
        if provider is None or model is None:
            self.mark_recording_corrupted()
            return None
        try:
            record = CallSpeedRecord(
                call_index=len(self._calls) + 1,
                provider=str(provider),
                model=str(model),
                dispatched_at=call_input.dispatched_at,
                completed_at=self._clock(),
                first_token_at=call_input.first_token_at,
                output_tokens=call_input.output_tokens,
                retry_count=call_input.retry_count,
                fallback_index=call_input.fallback_index,
            )
        except AgentSpeedValidationError:
            # A malformed response (e.g. provider/model that stringify to "") must not
            # crash the agent loop; treat it the same as an unusable response.
            self.mark_recording_corrupted()
            return None
        self._calls.append(record)
        return record

    def record_tool_call(self, call_input: RecordToolCallInput) -> ToolCallSpeedRecord:
        """Time one tool call and store it."""
        record = ToolCallSpeedRecord(
            call_index=len(self._tool_calls) + 1,
            tool_name=call_input.tool_name,
            started_at=call_input.started_at,
            completed_at=self._clock(),
            timed_out=call_input.timed_out,
        )
        self._tool_calls.append(record)
        return record

    def record_step(self, step_input: RecordStepInput) -> StepSpeedRecord:
        """Time one loop iteration and store it. Not yet called from vidbyte/agents/runtime.py."""
        record = StepSpeedRecord(
            iteration_index=len(self._steps) + 1,
            started_at=step_input.started_at,
            completed_at=self._clock(),
            model_call_index=step_input.model_call_index,
            tool_call_indices=step_input.tool_call_indices,
        )
        self._steps.append(record)
        return record

    def rollup(self) -> AgentSpeedRollup:
        """Fold every ledger into an immutable whole-run speed rollup."""
        calls, tool_calls, steps = tuple(self._calls), tuple(self._tool_calls), tuple(self._steps)
        return AgentSpeedRollup(
            calls=calls,
            tool_calls=tool_calls,
            steps=steps,
            call_stats=self._build_call_stats(calls),
            tool_call_stats=self._build_tool_call_stats(tool_calls),
            step_stats=self._build_step_stats(steps),
            run_stats=self._build_run_stats(calls, tool_calls),
            recording_integrity=(
                AgentSpeedRecordingIntegrity.CORRUPTED
                if self._recording_corrupted
                else AgentSpeedRecordingIntegrity.INTACT
            ),
        )

    def reset(self) -> None:
        """Clear every ledger and both run-boundary marks for a fresh run."""
        self._calls.clear()
        self._tool_calls.clear()
        self._steps.clear()
        self._run_started_at = None
        self._run_completed_at = None
        self._recording_corrupted = False

    @property
    def calls(self) -> tuple[CallSpeedRecord, ...]:
        """Return the immutable model-call ledger recorded so far."""
        return tuple(self._calls)

    @property
    def tool_calls(self) -> tuple[ToolCallSpeedRecord, ...]:
        """Return the immutable tool-call ledger recorded so far."""
        return tuple(self._tool_calls)

    @property
    def steps(self) -> tuple[StepSpeedRecord, ...]:
        """Return the immutable loop-iteration ledger recorded so far."""
        return tuple(self._steps)

    def _build_call_stats(self, calls: tuple[CallSpeedRecord, ...]) -> CallSpeedStats:
        # Aggregates every CallSpeedRecord field into one CallSpeedStats via MathHelper.
        if not calls:
            return CallSpeedStats.empty()
        durations = [call.duration_ms for call in calls]
        ttfts = [call.ttft_ms for call in calls if call.ttft_ms is not None]
        rates = [call.tokens_per_second for call in calls if call.tokens_per_second is not None]
        return CallSpeedStats(
            call_count=len(calls),
            ttft_ms_mean=MathHelper.mean_or_none(ttfts),
            ttft_ms_p50=MathHelper.percentile_or_none(ttfts, 0.50),
            ttft_ms_p95=MathHelper.percentile_or_none(ttfts, 0.95),
            ttft_ms_p99=MathHelper.percentile_or_none(ttfts, 0.99),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p50=MathHelper.percentile_or_none(durations, 0.50),
            duration_ms_p95=MathHelper.percentile_or_none(durations, 0.95),
            duration_ms_p99=MathHelper.percentile_or_none(durations, 0.99),
            duration_ms_max=MathHelper.max_or_none(durations),
            slowest_call_index=MathHelper.argmax_index({call.call_index: call.duration_ms for call in calls}),
            tokens_per_second_mean=MathHelper.mean_or_none(rates),
        )

    def _build_tool_call_stats(self, tool_calls: tuple[ToolCallSpeedRecord, ...]) -> ToolCallSpeedStats:
        # Aggregates every ToolCallSpeedRecord field into one ToolCallSpeedStats via MathHelper.
        if not tool_calls:
            return ToolCallSpeedStats.empty()
        durations = [call.duration_ms for call in tool_calls]
        return ToolCallSpeedStats(
            tool_call_count=len(tool_calls),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p95=MathHelper.percentile_or_none(durations, 0.95),
            duration_ms_max=MathHelper.max_or_none(durations),
            slowest_tool_call_index=MathHelper.argmax_index(
                {call.call_index: call.duration_ms for call in tool_calls}
            ),
        )

    def _build_step_stats(self, steps: tuple[StepSpeedRecord, ...]) -> StepSpeedStats:
        # Aggregates every StepSpeedRecord field into one StepSpeedStats via MathHelper.
        # Always .empty() today: nothing calls record_step() from runtime.py yet.
        if not steps:
            return StepSpeedStats.empty()
        durations = [step.duration_ms for step in steps]
        return StepSpeedStats(
            step_count=len(steps),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p95=MathHelper.percentile_or_none(durations, 0.95),
        )

    def _build_run_stats(
        self,
        calls: tuple[CallSpeedRecord, ...],
        tool_calls: tuple[ToolCallSpeedRecord, ...],
    ) -> RunSpeedStats:
        # Derives whole-run overhead figures from the run boundary marks plus the
        # already-computed call/tool-call ledgers. Needs neither steps nor MathHelper
        # for anything beyond the mean used in cold_start_overhead_ms.
        total_duration_ms = self._total_duration_ms()
        return RunSpeedStats(
            total_duration_ms=total_duration_ms,
            cold_start_overhead_ms=self._cold_start_overhead_ms(calls),
            framework_overhead_ms=self._framework_overhead_ms(total_duration_ms, calls, tool_calls),
            parallelism_efficiency=self._parallelism_efficiency(tool_calls),
        )

    def _total_duration_ms(self) -> float | None:
        # None until both run boundary marks are set (e.g. a live mid-run read).
        if self._run_started_at is None or self._run_completed_at is None:
            return None
        return (self._run_completed_at - self._run_started_at) * 1000

    @staticmethod
    def _cold_start_overhead_ms(calls: tuple[CallSpeedRecord, ...]) -> float | None:
        # First call's duration minus the mean of every call after it; needs at least
        # two calls to have a "rest" to compare against.
        if len(calls) < 2:
            return None
        rest_mean = MathHelper.mean_or_none([call.duration_ms for call in calls[1:]])
        return calls[0].duration_ms - rest_mean if rest_mean is not None else None

    @staticmethod
    def _framework_overhead_ms(
        total_duration_ms: float | None,
        calls: tuple[CallSpeedRecord, ...],
        tool_calls: tuple[ToolCallSpeedRecord, ...],
    ) -> float | None:
        # Total run time minus every known model-call and tool-call duration; what's
        # left is the runtime's own bookkeeping, middleware hooks, and context assembly.
        if total_duration_ms is None:
            return None
        known_ms = sum(call.duration_ms for call in calls) + sum(call.duration_ms for call in tool_calls)
        return total_duration_ms - known_ms

    @staticmethod
    def _parallelism_efficiency(tool_calls: tuple[ToolCallSpeedRecord, ...]) -> float | None:
        # sum(individual durations) / actual wall-clock elapsed across overlapping tool
        # calls; > 1 means concurrency is actually buying back wall-clock time.
        if len(tool_calls) < 2:
            return None
        wall_clock_seconds = max(call.completed_at for call in tool_calls) - min(call.started_at for call in tool_calls)
        if wall_clock_seconds <= 0:
            return None
        return sum(call.duration_ms for call in tool_calls) / 1000 / wall_clock_seconds


__all__ = ["AgentSpeedTracker"]
