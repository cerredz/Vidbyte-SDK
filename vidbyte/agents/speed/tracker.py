"""FILE: vidbyte/agents/speed/tracker.py

PURPOSE: Owns fail-open timing ledgers for model, tool, stream, step, retry, and run speed.
ROLE IN CODEBASE: BaseAgent and AgentRuntime use this mutable accumulator to expose speed rollups.
ARCHITECTURE NOTE: Records are immutable dataclasses; this class owns lifecycle state and aggregation.
COMMON MODIFICATION PATTERNS: Add a validated record first, then wire one runtime boundary and one aggregate helper.
KNOWN EDGE CASES: Recording errors never replace an agent result, and history survives current-run reset.
RELATED DOCS: docs/design/agent-speed-stats-expansion.md
TESTS: Covered by tests/test_agent_speed.py, tests/test_agent_runtime.py, and scripts/run_ci.py.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator

from vidbyte.lib.constants.speed import (
    AGENT_SPEED_FIRST_INDEX,
    AGENT_SPEED_MILLISECONDS_PER_SECOND,
    AGENT_SPEED_MIN_PARALLEL_CALLS,
    AGENT_SPEED_P50,
    AGENT_SPEED_P90,
    AGENT_SPEED_P95,
    AGENT_SPEED_P99,
    AGENT_SPEED_ZERO_COUNT,
    AGENT_SPEED_ZERO_SECONDS,
    MAX_AGENT_SPEED_HISTORY_RUNS,
)
from vidbyte.lib.dataclasses.speed import (
    AgentSpeedHistory,
    AgentSpeedRollup,
    CallSpeedRecord,
    CallSpeedStats,
    ModelSpeedStats,
    RecordModelCallFailureInput,
    RecordModelCallInput,
    RecordRetryWaitInput,
    RecordStepInput,
    RecordStreamInput,
    RecordToolCallInput,
    RetryWaitSpeedRecord,
    RunSpeedSnapshot,
    RunSpeedStats,
    StepSpeedRecord,
    StepSpeedStats,
    StreamSpeedRecord,
    StreamSpeedStats,
    ToolCallSpeedRecord,
    ToolCallSpeedStats,
    ToolSpeedStats,
)
from vidbyte.lib.enums.speed import AgentSpeedRecordingIntegrity
from vidbyte.lib.util.math import MathHelper

_FIRST_INDEX = AGENT_SPEED_FIRST_INDEX


class AgentSpeedTracker:
    """Accumulate speed records for one current run and a bounded run history."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        # @intent isolate-speed-run-state
        # Keep all ledgers local to this tracker so concurrent agents do not share state.
        self._clock = clock or time.monotonic
        self._calls: list[CallSpeedRecord] = []
        self._tool_calls: list[ToolCallSpeedRecord] = []
        self._steps: list[StepSpeedRecord] = []
        self._streams: list[StreamSpeedRecord] = []
        self._retry_waits: list[RetryWaitSpeedRecord] = []
        self._completed_runs: list[RunSpeedSnapshot] = []
        self._run_started_at: float | None = None
        self._run_completed_at: float | None = None
        self._result_ready_at: float | None = None
        self._active_step_started_at: float | None = None
        self._recording_corrupted = False
        self._run_archived = False

    def now(self) -> float:
        """Return the tracker's monotonic clock reading."""
        # Callers use this boundary timestamp immediately before awaited work.
        return self._clock()

    def record_run_start(self) -> None:
        """Mark the start of the current run and clear its completion markers."""
        # BaseAgent resets ledgers before this call, while history remains bounded and intact.
        self._run_started_at = self._clock()
        self._run_completed_at = None
        self._result_ready_at = None
        self._active_step_started_at = None
        self._run_archived = False

    def record_run_end(self) -> None:
        """Mark and archive the current run once."""
        # Close an open step before taking the final run boundary timestamp.
        self.end_step()
        self._run_completed_at = self._clock()
        if self._run_started_at is not None and not self._run_archived:
            snapshot = RunSpeedSnapshot(
                run_stats=self._build_run_stats(tuple(self._calls), tuple(self._tool_calls)),
                call_stats=self._build_call_stats(tuple(self._calls)),
                tool_call_stats=self._build_tool_call_stats(tuple(self._tool_calls)),
                is_cold_start=not self._completed_runs,
                first_call_duration_ms=(self._calls[0].duration_ms if self._calls else None),
                subsequent_call_duration_ms=(MathHelper.mean_or_none([call.duration_ms for call in self._calls[1:]]) if len(self._calls) > 1 else None),
            )
            self._completed_runs.append(snapshot)
            del self._completed_runs[:-MAX_AGENT_SPEED_HISTORY_RUNS]
            self._run_archived = True

    def record_result_ready(self) -> None:
        """Mark the first time the runtime has a result ready for its caller."""
        # Only the first final-result boundary is useful for time-to-result-ready.
        if self._result_ready_at is None:
            self._result_ready_at = self._clock()

    def mark_recording_corrupted(self) -> None:
        """Mark a lost speed record without interrupting agent execution."""
        # Speed instrumentation is deliberately fail-open at every runtime boundary.
        self._recording_corrupted = True

    @property
    def recording_corrupted(self) -> bool:
        """Return whether an instrumentation error caused a missing record."""
        # The rollup exposes this as an integrity enum for callers and reports.
        return self._recording_corrupted

    def record_call(self, call_input: RecordModelCallInput) -> CallSpeedRecord | None:
        # @intent fail-open-model-boundary
        """Record one successful model response, returning None on metering failure."""
        # Response identity is duck-typed so providers remain independent of the tracker.
        provider = getattr(call_input.response, "provider", None)
        model = getattr(call_input.response, "model", None)
        provider = getattr(provider, "value", provider)
        if provider is None or model is None:
            self.mark_recording_corrupted()
            return None
        try:
            record = CallSpeedRecord(
                call_index=len(self._calls) + _FIRST_INDEX,
                provider=str(provider),
                model=str(model),
                dispatched_at=call_input.dispatched_at,
                completed_at=self._clock(),
                first_token_at=call_input.first_token_at,
                output_tokens=call_input.output_tokens,
                retry_count=call_input.retry_count,
                fallback_index=call_input.fallback_index,
                input_tokens=call_input.input_tokens,
                iteration_index=call_input.iteration_index,
            )
        except Exception:
            self.mark_recording_corrupted()
            return None
        self._calls.append(record)
        return record

    def record_call_failure(self, failure: RecordModelCallFailureInput) -> CallSpeedRecord | None:
        # @intent preserve-model-failure-history
        """Record one failed or cancelled model attempt, returning None on metering failure."""
        # Failures use the same ledger as successes so latency and failure rates share indexes.
        try:
            record = CallSpeedRecord(
                call_index=len(self._calls) + _FIRST_INDEX,
                provider=failure.provider,
                model=failure.model,
                dispatched_at=failure.dispatched_at,
                completed_at=self._clock(),
                retry_count=failure.retry_count,
                fallback_index=failure.fallback_index,
                succeeded=False,
                error_type=failure.error_type,
                iteration_index=failure.iteration_index,
                cancelled=failure.cancelled,
            )
        except Exception:
            self.mark_recording_corrupted()
            return None
        self._calls.append(record)
        return record

    def record_tool_call(self, call_input: RecordToolCallInput) -> ToolCallSpeedRecord | None:
        """Record one complete tool boundary, returning None on metering failure."""
        # This method is safe to call from a finally block after any tool failure.
        try:
            record = ToolCallSpeedRecord(
                call_index=len(self._tool_calls) + _FIRST_INDEX,
                tool_name=call_input.tool_name,
                started_at=call_input.started_at,
                completed_at=self._clock(),
                timed_out=call_input.timed_out,
                succeeded=call_input.succeeded,
                error_type=call_input.error_type,
                iteration_index=call_input.iteration_index,
                cancelled=call_input.cancelled,
            )
        except Exception:
            self.mark_recording_corrupted()
            return None
        self._tool_calls.append(record)
        return record

    def record_step(self, step_input: RecordStepInput) -> StepSpeedRecord | None:
        """Record one completed loop step, returning None on metering failure."""
        # Step timing is best-effort because it must never replace the agent's result/error.
        try:
            record = StepSpeedRecord(
                iteration_index=len(self._steps) + _FIRST_INDEX,
                started_at=step_input.started_at,
                completed_at=self._clock(),
                model_call_index=step_input.model_call_index,
                tool_call_indices=step_input.tool_call_indices,
            )
        except Exception:
            self.mark_recording_corrupted()
            return None
        self._steps.append(record)
        return record

    def begin_step(self) -> None:
        """Start a step and close a previous unclosed step if one exists."""
        # The next loop turn closes a prior turn, covering continue and fallback branches.
        self.end_step()
        try:
            self._active_step_started_at = self._clock()
        except Exception:
            self.mark_recording_corrupted()
            self._active_step_started_at = None

    def end_step(self) -> StepSpeedRecord | None:
        """Close the active step and return its record when recording succeeds."""
        # Clearing the marker first makes repeated cleanup calls idempotent.
        started_at = self._active_step_started_at
        self._active_step_started_at = None
        if started_at is None:
            return None
        return self.record_step(RecordStepInput(started_at=started_at))

    def record_retry_wait(self, wait_input: RecordRetryWaitInput) -> RetryWaitSpeedRecord | None:
        # @intent isolate-retry-backoff-time
        """Record one retry backoff interval, returning None on metering failure."""
        # Backoff is kept separate from model latency so retry overhead is visible.
        try:
            record = RetryWaitSpeedRecord(
                retry_index=wait_input.retry_index,
                started_at=wait_input.started_at,
                completed_at=self._clock(),
            )
        except Exception:
            self.mark_recording_corrupted()
            return None
        self._retry_waits.append(record)
        return record

    def measure_stream(self, stream_input: RecordStreamInput) -> Iterator[str]:
        # @intent preserve-stream-boundary
        """Yield an existing text stream unchanged while recording chunk timing."""
        # This wrapper measures chunks only and does not force BaseAgent into streaming mode.
        timestamps: list[float] = []
        succeeded = False
        error_type: str | None = None
        cancelled = False
        try:
            for chunk in stream_input.source:
                timestamps.append(self._clock())
                yield chunk
            succeeded = True
        except BaseException as exc:
            error_type = type(exc).__name__
            cancelled = type(exc).__name__ in {"CancelledError", "GeneratorExit", "KeyboardInterrupt"}
            raise
        finally:
            try:
                completed_at = self._clock()
                first_chunk_at = timestamps[0] if timestamps else None
                record = StreamSpeedRecord(
                    stream_index=len(self._streams) + _FIRST_INDEX,
                    provider=stream_input.provider,
                    model=stream_input.model,
                    dispatched_at=stream_input.dispatched_at,
                    completed_at=completed_at,
                    first_chunk_at=first_chunk_at,
                    chunk_timestamps=tuple(timestamps),
                    succeeded=succeeded,
                    error_type=error_type,
                    cancelled=cancelled,
                )
                self._streams.append(record)
            except Exception:
                self.mark_recording_corrupted()

    def rollup(self) -> AgentSpeedRollup:
        # @intent build-speed-rollup-without-mutation
        """Return an immutable snapshot of current ledgers and speed aggregates."""
        # Build all aggregates from tuple snapshots so repeated reads are idempotent.
        calls = tuple(self._calls)
        tool_calls = tuple(self._tool_calls)
        steps = tuple(self._steps)
        streams = tuple(self._streams)
        retry_waits = tuple(self._retry_waits)
        return AgentSpeedRollup(
            calls=calls,
            tool_calls=tool_calls,
            steps=steps,
            streams=streams,
            retry_waits=retry_waits,
            call_stats=self._build_call_stats(calls),
            tool_call_stats=self._build_tool_call_stats(tool_calls),
            step_stats=self._build_step_stats(steps),
            stream_stats=self._build_stream_stats(streams),
            model_stats=self._build_model_stats(calls),
            tool_stats=self._build_tool_stats(tool_calls),
            run_stats=self._build_run_stats(calls, tool_calls),
            history_stats=self.history(),
            recording_integrity=(AgentSpeedRecordingIntegrity.CORRUPTED if self._recording_corrupted else AgentSpeedRecordingIntegrity.INTACT),
        )

    def history(self) -> AgentSpeedHistory:
        """Return bounded completed-run history and its warm/cold speed summaries."""
        # History remains available after reset and is capped at the public constant.
        runs = tuple(self._completed_runs[-MAX_AGENT_SPEED_HISTORY_RUNS:])
        first_calls = [run.first_call_duration_ms for run in runs if run.first_call_duration_ms is not None]
        subsequent = [run.subsequent_call_duration_ms for run in runs if run.subsequent_call_duration_ms is not None]
        durations = [run.run_stats.total_duration_ms for run in runs if run.run_stats.total_duration_ms is not None]
        return AgentSpeedHistory(
            runs=runs,
            run_count=len(runs),
            cold_run_count=sum(1 for run in runs if run.is_cold_start),
            warm_run_count=sum(1 for run in runs if not run.is_cold_start),
            first_call_duration_ms_mean=MathHelper.mean_or_none(first_calls),
            subsequent_call_duration_ms_mean=MathHelper.mean_or_none(subsequent),
            run_duration_ms_mean=MathHelper.mean_or_none(durations),
            run_duration_ms_p95=MathHelper.percentile_or_none(durations, AGENT_SPEED_P95),
        )

    def reset(self) -> None:
        # @intent reset-current-speed-run-only
        """Clear current-run ledgers while retaining bounded history."""
        # BaseAgent calls this at the start of every run; completed snapshots are immutable.
        self._calls.clear()
        self._tool_calls.clear()
        self._steps.clear()
        self._streams.clear()
        self._retry_waits.clear()
        self._run_started_at = None
        self._run_completed_at = None
        self._result_ready_at = None
        self._active_step_started_at = None
        self._recording_corrupted = False
        self._run_archived = False

    @property
    def calls(self) -> tuple[CallSpeedRecord, ...]:
        """Return the immutable current model-call ledger."""
        # A tuple prevents callers from mutating tracker state.
        return tuple(self._calls)

    @property
    def tool_calls(self) -> tuple[ToolCallSpeedRecord, ...]:
        """Return the immutable current tool-call ledger."""
        # A tuple prevents callers from mutating tracker state.
        return tuple(self._tool_calls)

    @property
    def steps(self) -> tuple[StepSpeedRecord, ...]:
        """Return the immutable current step ledger."""
        # A tuple prevents callers from mutating tracker state.
        return tuple(self._steps)

    @property
    def streams(self) -> tuple[StreamSpeedRecord, ...]:
        """Return the immutable current stream ledger."""
        # A tuple prevents callers from mutating tracker state.
        return tuple(self._streams)

    def _build_call_stats(self, calls: tuple[CallSpeedRecord, ...]) -> CallSpeedStats:
        # @intent aggregate-retry-and-fallback-speed
        # Aggregate attempt outcomes, latency percentiles, token totals, and weighted rates.
        if not calls:
            return CallSpeedStats.empty()
        durations = [call.duration_ms for call in calls]
        ttfts = [call.ttft_ms for call in calls if call.ttft_ms is not None]
        rates = [call.tokens_per_second for call in calls if call.tokens_per_second is not None]
        output_records = [call for call in calls if call.output_tokens is not None]
        prompt_records = [call for call in calls if call.input_tokens is not None and call.ttft_ms is not None]
        return CallSpeedStats(
            call_count=len(calls),
            successful_call_count=sum(AGENT_SPEED_FIRST_INDEX for call in calls if call.succeeded),
            failed_call_count=sum(AGENT_SPEED_FIRST_INDEX for call in calls if not call.succeeded),
            failure_rate=sum(AGENT_SPEED_FIRST_INDEX for call in calls if not call.succeeded) / len(calls),
            ttft_ms_mean=MathHelper.mean_or_none(ttfts),
            ttft_ms_p50=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P50),
            ttft_ms_p90=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P90),
            ttft_ms_p95=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P95),
            ttft_ms_p99=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P99),
            ttft_ms_min=MathHelper.min_or_none(ttfts),
            ttft_ms_stdev=MathHelper.stdev_or_none(ttfts),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p50=MathHelper.percentile_or_none(durations, AGENT_SPEED_P50),
            duration_ms_p95=MathHelper.percentile_or_none(durations, AGENT_SPEED_P95),
            duration_ms_p99=MathHelper.percentile_or_none(durations, AGENT_SPEED_P99),
            duration_ms_min=MathHelper.min_or_none(durations),
            duration_ms_max=MathHelper.max_or_none(durations),
            duration_ms_stdev=MathHelper.stdev_or_none(durations),
            slowest_call_index=MathHelper.argmax_index({call.call_index: call.duration_ms for call in calls}),
            tokens_per_second_mean=MathHelper.mean_or_none(rates),
            tokens_per_second_p90=MathHelper.percentile_or_none(rates, AGENT_SPEED_P90),
            tokens_per_second_min=MathHelper.min_or_none(rates),
            tokens_per_second_stdev=MathHelper.stdev_or_none(rates),
            input_tokens_total=_sum_ints(call.input_tokens for call in calls),
            output_tokens_total=_sum_ints(call.output_tokens for call in calls),
            weighted_output_tokens_per_second=MathHelper.weighted_rate_or_none(
                [float(call.output_tokens or AGENT_SPEED_ZERO_COUNT) for call in output_records],
                [_generation_seconds(call) for call in output_records],
            ),
            prompt_tokens_per_second=MathHelper.weighted_rate_or_none(
                [float(call.input_tokens or AGENT_SPEED_ZERO_COUNT) for call in prompt_records],
                [_ttft_seconds(call) for call in prompt_records],
            ),
            retry_count_total=sum(call.retry_count for call in calls),
            fallback_call_count=sum(AGENT_SPEED_FIRST_INDEX for call in calls if (call.fallback_index or AGENT_SPEED_ZERO_COUNT) > AGENT_SPEED_ZERO_COUNT),
            cancelled_call_count=sum(AGENT_SPEED_FIRST_INDEX for call in calls if call.cancelled),
            cancellation_rate=sum(AGENT_SPEED_FIRST_INDEX for call in calls if call.cancelled) / len(calls),
        )

    def _build_tool_call_stats(self, tool_calls: tuple[ToolCallSpeedRecord, ...]) -> ToolCallSpeedStats:
        # Aggregate complete tool-boundary durations and failure/timeout outcomes.
        if not tool_calls:
            return ToolCallSpeedStats.empty()
        durations = [call.duration_ms for call in tool_calls]
        failed = sum(AGENT_SPEED_FIRST_INDEX for call in tool_calls if not call.succeeded)
        return ToolCallSpeedStats(
            tool_call_count=len(tool_calls),
            successful_tool_call_count=len(tool_calls) - failed,
            failed_tool_call_count=failed,
            failure_rate=failed / len(tool_calls),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p90=MathHelper.percentile_or_none(durations, AGENT_SPEED_P90),
            duration_ms_p95=MathHelper.percentile_or_none(durations, AGENT_SPEED_P95),
            duration_ms_min=MathHelper.min_or_none(durations),
            duration_ms_max=MathHelper.max_or_none(durations),
            duration_ms_stdev=MathHelper.stdev_or_none(durations),
            slowest_tool_call_index=MathHelper.argmax_index({call.call_index: call.duration_ms for call in tool_calls}),
            timed_out_count=sum(AGENT_SPEED_FIRST_INDEX for call in tool_calls if call.timed_out),
            timeout_rate=sum(AGENT_SPEED_FIRST_INDEX for call in tool_calls if call.timed_out) / len(tool_calls),
            cancelled_tool_call_count=sum(AGENT_SPEED_FIRST_INDEX for call in tool_calls if call.cancelled),
            cancellation_rate=sum(AGENT_SPEED_FIRST_INDEX for call in tool_calls if call.cancelled) / len(tool_calls),
        )

    def _build_step_stats(self, steps: tuple[StepSpeedRecord, ...]) -> StepSpeedStats:
        # Aggregate the loop-step durations recorded around runtime iterations.
        if not steps:
            return StepSpeedStats.empty()
        durations = [step.duration_ms for step in steps]
        return StepSpeedStats(
            step_count=len(steps),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p50=MathHelper.percentile_or_none(durations, AGENT_SPEED_P50),
            duration_ms_p90=MathHelper.percentile_or_none(durations, AGENT_SPEED_P90),
            duration_ms_p95=MathHelper.percentile_or_none(durations, AGENT_SPEED_P95),
            duration_ms_p99=MathHelper.percentile_or_none(durations, AGENT_SPEED_P99),
            duration_ms_min=MathHelper.min_or_none(durations),
            duration_ms_max=MathHelper.max_or_none(durations),
            duration_ms_stdev=MathHelper.stdev_or_none(durations),
            slowest_step_index=MathHelper.argmax_index({step.iteration_index: step.duration_ms for step in steps}),
        )

    def _build_stream_stats(self, streams: tuple[StreamSpeedRecord, ...]) -> StreamSpeedStats:
        # Aggregate first-chunk latency, inter-chunk gaps, and chunk rates.
        if not streams:
            return StreamSpeedStats.empty()
        durations = [stream.duration_ms for stream in streams]
        ttfts = [stream.ttft_ms for stream in streams if stream.ttft_ms is not None]
        gaps = [gap for stream in streams for gap in stream.inter_chunk_gaps_ms]
        rates = [stream.chunk_rate_per_second for stream in streams if stream.chunk_rate_per_second is not None]
        failed = sum(AGENT_SPEED_FIRST_INDEX for stream in streams if not stream.succeeded)
        return StreamSpeedStats(
            stream_count=len(streams),
            successful_stream_count=len(streams) - failed,
            failed_stream_count=failed,
            failure_rate=failed / len(streams),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p50=MathHelper.percentile_or_none(durations, AGENT_SPEED_P50),
            duration_ms_p90=MathHelper.percentile_or_none(durations, AGENT_SPEED_P90),
            duration_ms_p95=MathHelper.percentile_or_none(durations, AGENT_SPEED_P95),
            duration_ms_p99=MathHelper.percentile_or_none(durations, AGENT_SPEED_P99),
            duration_ms_min=MathHelper.min_or_none(durations),
            duration_ms_stdev=MathHelper.stdev_or_none(durations),
            ttft_ms_mean=MathHelper.mean_or_none(ttfts),
            ttft_ms_p50=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P50),
            ttft_ms_p90=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P90),
            ttft_ms_p95=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P95),
            ttft_ms_p99=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P99),
            ttft_ms_min=MathHelper.min_or_none(ttfts),
            ttft_ms_stdev=MathHelper.stdev_or_none(ttfts),
            inter_chunk_gap_ms_mean=MathHelper.mean_or_none(gaps),
            inter_chunk_gap_ms_p50=MathHelper.percentile_or_none(gaps, AGENT_SPEED_P50),
            inter_chunk_gap_ms_p90=MathHelper.percentile_or_none(gaps, AGENT_SPEED_P90),
            inter_chunk_gap_ms_p95=MathHelper.percentile_or_none(gaps, AGENT_SPEED_P95),
            inter_chunk_gap_ms_p99=MathHelper.percentile_or_none(gaps, AGENT_SPEED_P99),
            inter_chunk_gap_ms_min=MathHelper.min_or_none(gaps),
            inter_chunk_gap_ms_stdev=MathHelper.stdev_or_none(gaps),
            inter_chunk_gap_ms_max=MathHelper.max_or_none(gaps),
            chunk_count=sum(len(stream.chunk_timestamps) for stream in streams),
            chunk_rate_per_second_mean=MathHelper.mean_or_none(rates),
            chunk_rate_per_second_p50=MathHelper.percentile_or_none(rates, AGENT_SPEED_P50),
            chunk_rate_per_second_p90=MathHelper.percentile_or_none(rates, AGENT_SPEED_P90),
            chunk_rate_per_second_p95=MathHelper.percentile_or_none(rates, AGENT_SPEED_P95),
            chunk_rate_per_second_p99=MathHelper.percentile_or_none(rates, AGENT_SPEED_P99),
            chunk_rate_per_second_min=MathHelper.min_or_none(rates),
            chunk_rate_per_second_stdev=MathHelper.stdev_or_none(rates),
            cancelled_stream_count=sum(AGENT_SPEED_FIRST_INDEX for stream in streams if stream.cancelled),
            cancellation_rate=sum(AGENT_SPEED_FIRST_INDEX for stream in streams if stream.cancelled) / len(streams),
        )

    def _build_model_stats(self, calls: tuple[CallSpeedRecord, ...]) -> tuple[ModelSpeedStats, ...]:
        # @intent group-speed-by-provider-and-model
        # Group model attempts by provider/model using deterministic key ordering.
        grouped: dict[tuple[str, str], list[CallSpeedRecord]] = defaultdict(list)
        for call in calls:
            grouped[(call.provider, call.model)].append(call)
        return tuple(self._model_group_stats(key, tuple(grouped[key])) for key in sorted(grouped))

    def _model_group_stats(self, key: tuple[str, str], calls: tuple[CallSpeedRecord, ...]) -> ModelSpeedStats:
        # @intent summarize-speed-by-model
        # Build one provider/model summary using the same weighted-rate definitions as the global rollup.
        successes = [call for call in calls if call.succeeded]
        durations = [call.duration_ms for call in calls]
        ttfts = [call.ttft_ms for call in calls if call.ttft_ms is not None]
        token_calls = [call for call in calls if call.output_tokens is not None]
        rates = [call.tokens_per_second for call in token_calls if call.tokens_per_second is not None]
        prompt_calls = [call for call in calls if call.input_tokens is not None and call.ttft_ms is not None]
        provider, model = key
        return ModelSpeedStats(
            provider=provider,
            model=model,
            call_count=len(calls),
            successful_call_count=len(successes),
            failed_call_count=len(calls) - len(successes),
            duration_ms_mean=MathHelper.mean_or_none(durations),
            duration_ms_p90=MathHelper.percentile_or_none(durations, AGENT_SPEED_P90),
            duration_ms_p95=MathHelper.percentile_or_none(durations, AGENT_SPEED_P95),
            duration_ms_min=MathHelper.min_or_none(durations),
            duration_ms_stdev=MathHelper.stdev_or_none(durations),
            ttft_ms_mean=MathHelper.mean_or_none(ttfts),
            ttft_ms_p90=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P90),
            ttft_ms_p95=MathHelper.percentile_or_none(ttfts, AGENT_SPEED_P95),
            weighted_output_tokens_per_second=MathHelper.weighted_rate_or_none([float(call.output_tokens or AGENT_SPEED_ZERO_COUNT) for call in token_calls], [_generation_seconds(call) for call in token_calls]),
            output_tokens_per_second_p90=MathHelper.percentile_or_none(rates, AGENT_SPEED_P90),
            output_tokens_per_second_min=MathHelper.min_or_none(rates),
            output_tokens_per_second_stdev=MathHelper.stdev_or_none(rates),
            prompt_tokens_per_second=MathHelper.weighted_rate_or_none([float(call.input_tokens or AGENT_SPEED_ZERO_COUNT) for call in prompt_calls], [_ttft_seconds(call) for call in prompt_calls]),
            input_tokens_total=_sum_ints(call.input_tokens for call in calls),
            output_tokens_total=_sum_ints(call.output_tokens for call in calls),
            retry_count_total=sum(call.retry_count for call in calls),
            fallback_call_count=sum(AGENT_SPEED_FIRST_INDEX for call in calls if (call.fallback_index or AGENT_SPEED_ZERO_COUNT) > AGENT_SPEED_ZERO_COUNT),
            cancelled_call_count=sum(AGENT_SPEED_FIRST_INDEX for call in calls if call.cancelled),
            cancellation_rate=sum(AGENT_SPEED_FIRST_INDEX for call in calls if call.cancelled) / len(calls),
        )

    def _build_tool_stats(self, tool_calls: tuple[ToolCallSpeedRecord, ...]) -> tuple[ToolSpeedStats, ...]:
        # Group complete tool-boundary attempts by tool name in deterministic order.
        grouped: dict[str, list[ToolCallSpeedRecord]] = defaultdict(list)
        for call in tool_calls:
            grouped[call.tool_name].append(call)
        result: list[ToolSpeedStats] = []
        for name in sorted(grouped):
            calls = tuple(grouped[name])
            failed = sum(AGENT_SPEED_FIRST_INDEX for call in calls if not call.succeeded)
            durations = [call.duration_ms for call in calls]
            timed_out = sum(AGENT_SPEED_FIRST_INDEX for call in calls if call.timed_out)
            cancelled = sum(AGENT_SPEED_FIRST_INDEX for call in calls if call.cancelled)
            result.append(
                ToolSpeedStats(
                    tool_name=name,
                    tool_call_count=len(calls),
                    successful_tool_call_count=len(calls) - failed,
                    failed_tool_call_count=failed,
                    duration_ms_mean=MathHelper.mean_or_none(durations),
                    duration_ms_p90=MathHelper.percentile_or_none(durations, AGENT_SPEED_P90),
                    duration_ms_p95=MathHelper.percentile_or_none(durations, AGENT_SPEED_P95),
                    duration_ms_min=MathHelper.min_or_none(durations),
                    duration_ms_stdev=MathHelper.stdev_or_none(durations),
                    failure_rate=failed / len(calls),
                    timed_out_count=timed_out,
                    timeout_rate=timed_out / len(calls),
                    cancelled_tool_call_count=cancelled,
                    cancellation_rate=cancelled / len(calls),
                )
            )
        return tuple(result)

    def _build_run_stats(self, calls: tuple[CallSpeedRecord, ...], tool_calls: tuple[ToolCallSpeedRecord, ...]) -> RunSpeedStats:
        # @intent derive-overlap-and-fallback-speed
        # Derive total, active-work, overlap, retry, fallback, and result-boundary metrics.
        total_duration_ms = self._total_duration_ms()
        intervals = [(call.dispatched_at, call.completed_at) for call in calls] + [(call.started_at, call.completed_at) for call in tool_calls]
        active_seconds = MathHelper.interval_union_seconds(intervals)
        child_seconds = sum(end - start for start, end in intervals) if intervals else None
        tool_intervals = [(call.started_at, call.completed_at) for call in tool_calls]
        tool_union_seconds = MathHelper.interval_union_seconds(tool_intervals)
        first_tool = min((call.started_at for call in tool_calls), default=None)
        return RunSpeedStats(
            total_duration_ms=total_duration_ms,
            cold_start_overhead_ms=self._cold_start_overhead_ms(calls),
            framework_overhead_ms=(max(AGENT_SPEED_ZERO_SECONDS, total_duration_ms - active_seconds * AGENT_SPEED_MILLISECONDS_PER_SECOND) if total_duration_ms is not None and active_seconds is not None else None),
            parallelism_efficiency=(sum(call.duration_ms for call in tool_calls) / (tool_union_seconds * AGENT_SPEED_MILLISECONDS_PER_SECOND) if len(tool_calls) >= AGENT_SPEED_MIN_PARALLEL_CALLS and tool_union_seconds and tool_union_seconds > AGENT_SPEED_ZERO_SECONDS else None),
            time_to_first_tool_ms=((first_tool - self._run_started_at) * AGENT_SPEED_MILLISECONDS_PER_SECOND if first_tool is not None and self._run_started_at is not None else None),
            time_to_result_ready_ms=((self._result_ready_at - self._run_started_at) * AGENT_SPEED_MILLISECONDS_PER_SECOND if self._result_ready_at is not None and self._run_started_at is not None else None),
            active_work_ms=(active_seconds * AGENT_SPEED_MILLISECONDS_PER_SECOND if active_seconds is not None else None),
            overlap_ms=(max(AGENT_SPEED_ZERO_SECONDS, (child_seconds - active_seconds) * AGENT_SPEED_MILLISECONDS_PER_SECOND) if child_seconds is not None and active_seconds is not None else None),
            max_concurrency=MathHelper.max_concurrency(tool_intervals),
            average_concurrency=(sum(call.duration_ms for call in tool_calls) / (tool_union_seconds * AGENT_SPEED_MILLISECONDS_PER_SECOND) if tool_union_seconds and tool_union_seconds > AGENT_SPEED_ZERO_SECONDS else None),
            retry_wait_ms_total=MathHelper.sum_or_none([wait.duration_ms for wait in self._retry_waits]),
            fallback_overhead_ms=MathHelper.sum_or_none([call.duration_ms for call in calls if not call.succeeded and any((later.fallback_index or AGENT_SPEED_ZERO_COUNT) > AGENT_SPEED_ZERO_COUNT for later in calls)]),
            fallback_switch_count=max((call.fallback_index or AGENT_SPEED_ZERO_COUNT for call in calls), default=AGENT_SPEED_ZERO_COUNT),
            input_tokens_total=_sum_ints(call.input_tokens for call in calls),
            output_tokens_total=_sum_ints(call.output_tokens for call in calls),
        )

    def _total_duration_ms(self) -> float | None:
        # Return None while either run boundary is unavailable or invalid.
        if self._run_started_at is None or self._run_completed_at is None or self._run_completed_at < self._run_started_at:
            return None
        return (self._run_completed_at - self._run_started_at) * AGENT_SPEED_MILLISECONDS_PER_SECOND

    @staticmethod
    def _cold_start_overhead_ms(calls: tuple[CallSpeedRecord, ...]) -> float | None:
        # Compare the first call with later calls when at least two attempts exist.
        if len(calls) < 2:
            return None
        rest_mean = MathHelper.mean_or_none([call.duration_ms for call in calls[1:]])
        return calls[0].duration_ms - rest_mean if rest_mean is not None else None


def _sum_ints(values: Iterable[int | None]) -> int | None:
    # Sum known integer token counts while preserving None when no count is known.
    seen = False
    total = 0
    for value in values:
        if value is not None:
            total += int(value)
            seen = True
    return total if seen else None


def _generation_seconds(call: CallSpeedRecord) -> float:
    # Use the generation window after the first token, or the full call as fallback.
    return max(AGENT_SPEED_ZERO_SECONDS, (call.completed_at - (call.first_token_at or call.dispatched_at)))


def _ttft_seconds(call: CallSpeedRecord) -> float:
    # Use TTFT as the prompt processing denominator.
    return max(AGENT_SPEED_ZERO_SECONDS, (call.first_token_at or call.dispatched_at) - call.dispatched_at)


__all__ = ["AgentSpeedTracker"]
