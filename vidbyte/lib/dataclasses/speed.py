"""FILE: vidbyte/lib/dataclasses/speed.py

PURPOSE: Defines validated speed records, aggregates, grouping summaries, and bounded-history snapshots.
ROLE IN CODEBASE: AgentSpeedTracker constructs these immutable contracts for BaseAgent and AgentRuntime callers.
ARCHITECTURE NOTE: Dataclasses validate shapes and timestamps; timing state and numerical aggregation live elsewhere.
COMMON MODIFICATION PATTERNS: Add a field here with validation, then compute it in the matching tracker helper.
KNOWN EDGE CASES: Unknown token denominators remain None, while failed and cancelled records remain countable.
RELATED DOCS: docs/design/agent-speed-stats-expansion.md
TESTS: Covered by tests/test_agent_speed.py, tests/test_agent_runtime.py, and scripts/run_ci.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.constants.speed import AGENT_SPEED_FIRST_INDEX, AGENT_SPEED_FIRST_RETRY_INDEX, AGENT_SPEED_ZERO_COUNT, AGENT_SPEED_ZERO_SECONDS
from vidbyte.lib.enums.speed import AgentSpeedRecordingIntegrity
from vidbyte.lib.errors import AgentSpeedValidationError

_MILLISECONDS_PER_SECOND = 1000


def _require_non_negative_float(value: float, *, field_name: str) -> None:
    # Reject invalid timestamp and metric values while allowing integer-like floats.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < AGENT_SPEED_ZERO_COUNT:
        raise AgentSpeedValidationError(f"{field_name} must be a non-negative number.", details={"field": field_name, "value": value})


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    # Reject bool because it is an int subclass but not a meaningful count.
    if isinstance(value, bool) or not isinstance(value, int) or value < AGENT_SPEED_ZERO_COUNT:
        raise AgentSpeedValidationError(f"{field_name} must be a non-negative int.", details={"field": field_name, "value": value})


def _require_at_least_one(value: int, *, field_name: str) -> None:
    # Validate the one-based indexes used by the ledgers.
    if isinstance(value, bool) or not isinstance(value, int) or value < AGENT_SPEED_FIRST_INDEX:
        raise AgentSpeedValidationError(f"{field_name} must be an int >= 1.", details={"field": field_name, "value": value})


def _require_non_empty_str(value: str, *, field_name: str) -> None:
    # Keep grouping keys and error labels useful to downstream reports.
    if not isinstance(value, str) or not value.strip():
        raise AgentSpeedValidationError(f"{field_name} must be a non-empty string.", details={"field": field_name, "value": value})


def _require_bool(value: bool, *, field_name: str) -> None:
    # Validate flags explicitly instead of accepting truthy values.
    if not isinstance(value, bool):
        raise AgentSpeedValidationError(f"{field_name} must be a bool.", details={"field": field_name, "value": value})


def _require_optional_metric(value: float | None, *, field_name: str) -> None:
    # Apply the common non-negative check to optional aggregate values.
    if value is not None:
        _require_non_negative_float(value, field_name=field_name)


def _require_ordered_percentiles(p50: float | None, p95: float | None, p99: float | None, *, field_prefix: str) -> None:
    # Catch impossible percentile ordering at the immutable contract boundary.
    if p50 is not None and p95 is not None and p50 > p95:
        raise AgentSpeedValidationError(f"{field_prefix}_p50 cannot exceed {field_prefix}_p95.")
    if p95 is not None and p99 is not None and p95 > p99:
        raise AgentSpeedValidationError(f"{field_prefix}_p95 cannot exceed {field_prefix}_p99.")


def _validate_interval(started_at: float, completed_at: float) -> None:
    # Ensure every duration-bearing record has a forward-moving interval.
    _require_non_negative_float(started_at, field_name="started_at")
    _require_non_negative_float(completed_at, field_name="completed_at")
    if completed_at < started_at:
        raise AgentSpeedValidationError("completed_at cannot precede started_at.")


@dataclass(frozen=True, slots=True)
class RecordModelCallInput:
    """Input for a successful model-call speed record."""

    response: object
    dispatched_at: float
    first_token_at: float | None = None
    output_tokens: int | None = None
    retry_count: int = AGENT_SPEED_ZERO_COUNT
    fallback_index: int | None = None
    input_tokens: int | None = None
    iteration_index: int | None = None

    def __post_init__(self) -> None:
        # @intent validate-retry-and-fallback-contract
        # Validate provider response timing and optional speed denominators.
        if self.response is None:
            raise AgentSpeedValidationError("response must not be None.")
        _require_non_negative_float(self.dispatched_at, field_name="dispatched_at")
        if self.first_token_at is not None:
            _require_non_negative_float(self.first_token_at, field_name="first_token_at")
            if self.first_token_at < self.dispatched_at:
                raise AgentSpeedValidationError("first_token_at cannot precede dispatched_at.")
        for name, value in (("input_tokens", self.input_tokens), ("output_tokens", self.output_tokens)):
            if value is not None:
                _require_non_negative_int(value, field_name=name)
        _require_non_negative_int(self.retry_count, field_name="retry_count")
        if self.fallback_index is not None:
            _require_non_negative_int(self.fallback_index, field_name="fallback_index")
        if self.iteration_index is not None:
            _require_at_least_one(self.iteration_index, field_name="iteration_index")


@dataclass(frozen=True, slots=True)
class RecordModelCallFailureInput:
    """Input for a failed or cancelled model-call attempt."""

    provider: str
    model: str
    dispatched_at: float
    retry_count: int = AGENT_SPEED_ZERO_COUNT
    fallback_index: int | None = None
    iteration_index: int | None = None
    error_type: str = "ModelCallError"
    cancelled: bool = False

    def __post_init__(self) -> None:
        # @intent validate-model-failure-boundary
        # Validate failure metadata without requiring a provider response object.
        _require_non_empty_str(self.provider, field_name="provider")
        _require_non_empty_str(self.model, field_name="model")
        _require_non_negative_float(self.dispatched_at, field_name="dispatched_at")
        _require_non_negative_int(self.retry_count, field_name="retry_count")
        if self.fallback_index is not None:
            _require_non_negative_int(self.fallback_index, field_name="fallback_index")
        if self.iteration_index is not None:
            _require_at_least_one(self.iteration_index, field_name="iteration_index")
        _require_non_empty_str(self.error_type, field_name="error_type")
        _require_bool(self.cancelled, field_name="cancelled")


@dataclass(frozen=True, slots=True)
class CallSpeedRecord:
    """One successful, failed, or cancelled model-call attempt."""

    call_index: int
    provider: str
    model: str
    dispatched_at: float
    completed_at: float
    first_token_at: float | None = None
    output_tokens: int | None = None
    retry_count: int = AGENT_SPEED_ZERO_COUNT
    fallback_index: int | None = None
    input_tokens: int | None = None
    succeeded: bool = True
    error_type: str | None = None
    iteration_index: int | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        # @intent validate-model-speed-outcome
        # Validate identity, timing, outcome, and optional token denominators.
        _require_at_least_one(self.call_index, field_name="call_index")
        _require_non_empty_str(self.provider, field_name="provider")
        _require_non_empty_str(self.model, field_name="model")
        _validate_interval(self.dispatched_at, self.completed_at)
        if self.first_token_at is not None:
            _require_non_negative_float(self.first_token_at, field_name="first_token_at")
            if not self.dispatched_at <= self.first_token_at <= self.completed_at:
                raise AgentSpeedValidationError("first_token_at must fall within the call interval.")
        for name, value in (("input_tokens", self.input_tokens), ("output_tokens", self.output_tokens)):
            if value is not None:
                _require_non_negative_int(value, field_name=name)
        _require_non_negative_int(self.retry_count, field_name="retry_count")
        if self.fallback_index is not None:
            _require_non_negative_int(self.fallback_index, field_name="fallback_index")
        if self.iteration_index is not None:
            _require_at_least_one(self.iteration_index, field_name="iteration_index")
        _require_bool(self.succeeded, field_name="succeeded")
        _require_bool(self.cancelled, field_name="cancelled")
        if self.error_type is not None:
            _require_non_empty_str(self.error_type, field_name="error_type")
        if self.succeeded and self.error_type is not None:
            raise AgentSpeedValidationError("successful calls cannot have an error_type.")
        if self.succeeded and self.cancelled:
            raise AgentSpeedValidationError("successful calls cannot be cancelled.")

    @property
    def duration_ms(self) -> float:
        """Return total wall-clock time from dispatch to completion."""
        return (self.completed_at - self.dispatched_at) * _MILLISECONDS_PER_SECOND

    @property
    def ttft_ms(self) -> float | None:
        """Return dispatch-to-first-token latency when a first token was observed."""
        if self.first_token_at is None:
            return None
        return (self.first_token_at - self.dispatched_at) * _MILLISECONDS_PER_SECOND

    @property
    def generation_duration_ms(self) -> float | None:
        """Return the post-first-token generation window in milliseconds."""
        if self.first_token_at is None:
            return None
        return (self.completed_at - self.first_token_at) * _MILLISECONDS_PER_SECOND

    @property
    def tokens_per_second(self) -> float | None:
        """Return output tokens per second over the generation window."""
        if self.output_tokens is None:
            return None
        start = self.first_token_at if self.first_token_at is not None else self.dispatched_at
        seconds = self.completed_at - start
        return self.output_tokens / seconds if seconds > 0 else None

    @property
    def prompt_tokens_per_second(self) -> float | None:
        """Return input tokens per second when TTFT provides a prompt-time denominator."""
        if self.input_tokens is None or self.first_token_at is None:
            return None
        seconds = self.first_token_at - self.dispatched_at
        return self.input_tokens / seconds if seconds > 0 else None

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation, rather than an ordinary error, ended the call."""
        return self.cancelled


@dataclass(frozen=True, slots=True)
class RecordToolCallInput:
    """Input for a complete tool-call boundary record."""

    tool_name: str
    started_at: float
    timed_out: bool = False
    succeeded: bool = True
    error_type: str | None = None
    iteration_index: int | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        # @intent validate-tool-retry-boundary
        # Validate the full tool boundary outcome, including lookup and policy failures.
        _require_non_empty_str(self.tool_name, field_name="tool_name")
        _require_non_negative_float(self.started_at, field_name="started_at")
        _require_bool(self.timed_out, field_name="timed_out")
        _require_bool(self.succeeded, field_name="succeeded")
        _require_bool(self.cancelled, field_name="cancelled")
        if self.error_type is not None:
            _require_non_empty_str(self.error_type, field_name="error_type")
        if self.succeeded and self.error_type is not None:
            raise AgentSpeedValidationError("successful tools cannot have an error_type.")
        if self.iteration_index is not None:
            _require_at_least_one(self.iteration_index, field_name="iteration_index")


@dataclass(frozen=True, slots=True)
class ToolCallSpeedRecord:
    """One timed tool call, including resolution, policy, validation, and execution."""

    call_index: int
    tool_name: str
    started_at: float
    completed_at: float
    timed_out: bool = False
    succeeded: bool = True
    error_type: str | None = None
    iteration_index: int | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        # @intent validate-tool-speed-outcome
        # Validate the full interval and outcome flags.
        _require_at_least_one(self.call_index, field_name="call_index")
        _require_non_empty_str(self.tool_name, field_name="tool_name")
        _validate_interval(self.started_at, self.completed_at)
        _require_bool(self.timed_out, field_name="timed_out")
        _require_bool(self.succeeded, field_name="succeeded")
        _require_bool(self.cancelled, field_name="cancelled")
        if self.error_type is not None:
            _require_non_empty_str(self.error_type, field_name="error_type")
        if self.succeeded and self.error_type is not None:
            raise AgentSpeedValidationError("successful tools cannot have an error_type.")
        if self.iteration_index is not None:
            _require_at_least_one(self.iteration_index, field_name="iteration_index")

    @property
    def duration_ms(self) -> float:
        """Return total wall-clock time for the complete tool boundary."""
        return (self.completed_at - self.started_at) * _MILLISECONDS_PER_SECOND


def _validate_tool_call_indices(indices: tuple[int, ...]) -> None:
    # Keep step-to-tool references unique and one-based.
    if len(set(indices)) != len(indices):
        raise AgentSpeedValidationError("tool_call_indices cannot contain duplicates.")
    for index in indices:
        _require_at_least_one(index, field_name="tool_call_indices item")


@dataclass(frozen=True, slots=True)
class RecordStepInput:
    """Input for one agent loop step."""

    started_at: float
    model_call_index: int | None = None
    tool_call_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        # Validate optional references to the model and tool ledgers.
        _require_non_negative_float(self.started_at, field_name="started_at")
        if self.model_call_index is not None:
            _require_at_least_one(self.model_call_index, field_name="model_call_index")
        _validate_tool_call_indices(self.tool_call_indices)


@dataclass(frozen=True, slots=True)
class StepSpeedRecord:
    """One timed loop step."""

    iteration_index: int
    started_at: float
    completed_at: float
    model_call_index: int | None = None
    tool_call_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        # Validate step identity, interval, and ledger references.
        _require_at_least_one(self.iteration_index, field_name="iteration_index")
        _validate_interval(self.started_at, self.completed_at)
        if self.model_call_index is not None:
            _require_at_least_one(self.model_call_index, field_name="model_call_index")
        _validate_tool_call_indices(self.tool_call_indices)

    @property
    def duration_ms(self) -> float:
        """Return the step duration in milliseconds."""
        return (self.completed_at - self.started_at) * _MILLISECONDS_PER_SECOND


@dataclass(frozen=True, slots=True)
class RecordRetryWaitInput:
    """Input for time spent waiting before a model retry."""

    started_at: float
    retry_index: int = AGENT_SPEED_FIRST_RETRY_INDEX

    def __post_init__(self) -> None:
        # @intent validate-retry-wait-boundary
        # Validate retry wait timing and ordinal.
        _require_non_negative_float(self.started_at, field_name="started_at")
        _require_at_least_one(self.retry_index, field_name="retry_index")


@dataclass(frozen=True, slots=True)
class RetryWaitSpeedRecord:
    """One retry backoff interval."""

    retry_index: int
    started_at: float
    completed_at: float

    def __post_init__(self) -> None:
        # @intent validate-retry-wait-record
        # Validate retry wait identity and interval.
        _require_at_least_one(self.retry_index, field_name="retry_index")
        _validate_interval(self.started_at, self.completed_at)

    @property
    def duration_ms(self) -> float:
        """Return the retry wait duration in milliseconds."""
        return (self.completed_at - self.started_at) * _MILLISECONDS_PER_SECOND


@dataclass(frozen=True, slots=True)
class RecordStreamInput:
    """Input for measuring an existing synchronous text-chunk iterator."""

    provider: str
    model: str
    source: Any
    dispatched_at: float

    def __post_init__(self) -> None:
        # @intent validate-stream-provider-boundary
        # Validate stream identity and dispatch timestamp without owning the iterator.
        _require_non_empty_str(self.provider, field_name="provider")
        _require_non_empty_str(self.model, field_name="model")
        if self.source is None or not hasattr(self.source, "__iter__"):
            raise AgentSpeedValidationError("source must be iterable.")
        _require_non_negative_float(self.dispatched_at, field_name="dispatched_at")


@dataclass(frozen=True, slots=True)
class StreamSpeedRecord:
    """Timing record for one chunk stream; chunks are measured, not tokenized."""

    stream_index: int
    provider: str
    model: str
    dispatched_at: float
    completed_at: float
    first_chunk_at: float | None = None
    chunk_timestamps: tuple[float, ...] = ()
    succeeded: bool = True
    error_type: str | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        # @intent validate-stream-speed-outcome
        # Validate stream interval, chunk ordering, and completion outcome.
        _require_at_least_one(self.stream_index, field_name="stream_index")
        _require_non_empty_str(self.provider, field_name="provider")
        _require_non_empty_str(self.model, field_name="model")
        _validate_interval(self.dispatched_at, self.completed_at)
        if self.first_chunk_at is not None:
            _require_non_negative_float(self.first_chunk_at, field_name="first_chunk_at")
            if not self.dispatched_at <= self.first_chunk_at <= self.completed_at:
                raise AgentSpeedValidationError("first_chunk_at must fall within the stream interval.")
        previous = self.dispatched_at
        for timestamp in self.chunk_timestamps:
            _require_non_negative_float(timestamp, field_name="chunk_timestamps item")
            if timestamp < previous or timestamp > self.completed_at:
                raise AgentSpeedValidationError("chunk timestamps must be ordered within the stream interval.")
            previous = timestamp
        if self.chunk_timestamps and self.first_chunk_at != self.chunk_timestamps[0]:
            raise AgentSpeedValidationError("first_chunk_at must match the first chunk timestamp.")
        _require_bool(self.succeeded, field_name="succeeded")
        _require_bool(self.cancelled, field_name="cancelled")
        if self.error_type is not None:
            _require_non_empty_str(self.error_type, field_name="error_type")
        if self.succeeded and self.error_type is not None:
            raise AgentSpeedValidationError("successful streams cannot have an error_type.")

    @property
    def duration_ms(self) -> float:
        """Return dispatch-to-stream-completion time in milliseconds."""
        return (self.completed_at - self.dispatched_at) * _MILLISECONDS_PER_SECOND

    @property
    def ttft_ms(self) -> float | None:
        """Return dispatch-to-first-chunk time in milliseconds."""
        if self.first_chunk_at is None:
            return None
        return (self.first_chunk_at - self.dispatched_at) * _MILLISECONDS_PER_SECOND

    @property
    def inter_chunk_gaps_ms(self) -> tuple[float, ...]:
        """Return elapsed milliseconds between each pair of observed chunks."""
        return tuple((right - left) * _MILLISECONDS_PER_SECOND for left, right in zip(self.chunk_timestamps, self.chunk_timestamps[1:], strict=True))

    @property
    def chunk_rate_per_second(self) -> float | None:
        """Return observed chunks per second after the first chunk."""
        if len(self.chunk_timestamps) < 2:
            return None
        seconds = self.chunk_timestamps[-1] - self.chunk_timestamps[0]
        return (len(self.chunk_timestamps) - 1) / seconds if seconds > 0 else None


@dataclass(frozen=True, slots=True)
class CallSpeedStats:
    """Aggregate speed metrics for model-call attempts."""

    call_count: int = 0
    ttft_ms_mean: float | None = None
    ttft_ms_p50: float | None = None
    ttft_ms_p95: float | None = None
    ttft_ms_p99: float | None = None
    duration_ms_mean: float | None = None
    duration_ms_p50: float | None = None
    duration_ms_p95: float | None = None
    duration_ms_p99: float | None = None
    duration_ms_max: float | None = None
    slowest_call_index: int | None = None
    tokens_per_second_mean: float | None = None
    successful_call_count: int = 0
    failed_call_count: int = 0
    failure_rate: float = 0.0
    duration_ms_min: float | None = None
    duration_ms_stdev: float | None = None
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    weighted_output_tokens_per_second: float | None = None
    prompt_tokens_per_second: float | None = None
    retry_count_total: int = AGENT_SPEED_ZERO_COUNT
    fallback_call_count: int = 0
    ttft_ms_p90: float | None = None
    ttft_ms_min: float | None = None
    ttft_ms_stdev: float | None = None
    tokens_per_second_p90: float | None = None
    tokens_per_second_min: float | None = None
    tokens_per_second_stdev: float | None = None
    cancelled_call_count: int = 0
    cancellation_rate: float = 0.0

    def __post_init__(self) -> None:
        # Validate counts, rates, and ordered latency summaries.
        _require_non_negative_int(self.call_count, field_name="call_count")
        for name in ("successful_call_count", "failed_call_count", "retry_count_total", "fallback_call_count", "cancelled_call_count"):
            _require_non_negative_int(getattr(self, name), field_name=name)
        if self.successful_call_count + self.failed_call_count != self.call_count:
            raise AgentSpeedValidationError("successful_call_count plus failed_call_count must equal call_count.")
        if self.cancelled_call_count > self.failed_call_count:
            raise AgentSpeedValidationError("cancelled_call_count cannot exceed failed_call_count.")
        _require_non_negative_float(self.failure_rate, field_name="failure_rate")
        _require_non_negative_float(self.cancellation_rate, field_name="cancellation_rate")
        for name in ("ttft_ms_mean", "ttft_ms_p50", "ttft_ms_p90", "ttft_ms_p95", "ttft_ms_p99", "ttft_ms_min", "ttft_ms_stdev", "duration_ms_mean", "duration_ms_p50", "duration_ms_p95", "duration_ms_p99", "duration_ms_max", "tokens_per_second_mean", "tokens_per_second_p90", "tokens_per_second_min", "tokens_per_second_stdev", "duration_ms_min", "duration_ms_stdev", "weighted_output_tokens_per_second", "prompt_tokens_per_second"):
            _require_optional_metric(getattr(self, name), field_name=name)
        for name, value in (("input_tokens_total", self.input_tokens_total), ("output_tokens_total", self.output_tokens_total)):
            if value is not None:
                _require_non_negative_int(value, field_name=name)
        if self.slowest_call_index is not None:
            _require_at_least_one(self.slowest_call_index, field_name="slowest_call_index")
        _require_ordered_percentiles(self.ttft_ms_p50, self.ttft_ms_p95, self.ttft_ms_p99, field_prefix="ttft_ms")
        _require_ordered_percentiles(self.duration_ms_p50, self.duration_ms_p95, self.duration_ms_p99, field_prefix="duration_ms")

    @classmethod
    def empty(cls) -> CallSpeedStats:
        # Return a valid no-call aggregate with zero outcome counts.
        return cls()


@dataclass(frozen=True, slots=True)
class ToolCallSpeedStats:
    """Aggregate speed metrics for tool-call attempts."""

    tool_call_count: int = 0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None
    duration_ms_max: float | None = None
    slowest_tool_call_index: int | None = None
    successful_tool_call_count: int = 0
    failed_tool_call_count: int = 0
    failure_rate: float = 0.0
    duration_ms_min: float | None = None
    duration_ms_stdev: float | None = None
    timed_out_count: int = 0
    duration_ms_p90: float | None = None
    timeout_rate: float = AGENT_SPEED_ZERO_SECONDS
    cancelled_tool_call_count: int = 0
    cancellation_rate: float = 0.0

    def __post_init__(self) -> None:
        # Validate tool counts and duration summaries.
        _require_non_negative_int(self.tool_call_count, field_name="tool_call_count")
        for name in ("successful_tool_call_count", "failed_tool_call_count", "timed_out_count", "cancelled_tool_call_count"):
            _require_non_negative_int(getattr(self, name), field_name=name)
        if self.successful_tool_call_count + self.failed_tool_call_count != self.tool_call_count:
            raise AgentSpeedValidationError("successful_tool_call_count plus failed_tool_call_count must equal tool_call_count.")
        if self.timed_out_count > self.failed_tool_call_count or self.cancelled_tool_call_count > self.failed_tool_call_count:
            raise AgentSpeedValidationError("tool timeout and cancellation counts cannot exceed failed_tool_call_count.")
        _require_non_negative_float(self.failure_rate, field_name="failure_rate")
        _require_non_negative_float(self.timeout_rate, field_name="timeout_rate")
        _require_non_negative_float(self.cancellation_rate, field_name="cancellation_rate")
        for name in ("duration_ms_mean", "duration_ms_p90", "duration_ms_p95", "duration_ms_max", "duration_ms_min", "duration_ms_stdev"):
            _require_optional_metric(getattr(self, name), field_name=name)
        if self.slowest_tool_call_index is not None:
            _require_at_least_one(self.slowest_tool_call_index, field_name="slowest_tool_call_index")

    @classmethod
    def empty(cls) -> ToolCallSpeedStats:
        # Return a valid no-tool aggregate.
        return cls()


@dataclass(frozen=True, slots=True)
class StepSpeedStats:
    """Aggregate speed metrics for loop steps."""

    step_count: int = 0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None
    duration_ms_min: float | None = None
    duration_ms_max: float | None = None
    duration_ms_stdev: float | None = None
    duration_ms_p50: float | None = None
    duration_ms_p90: float | None = None
    duration_ms_p99: float | None = None
    slowest_step_index: int | None = None

    def __post_init__(self) -> None:
        # Validate step count and duration summaries.
        _require_non_negative_int(self.step_count, field_name="step_count")
        for name in ("duration_ms_mean", "duration_ms_p50", "duration_ms_p90", "duration_ms_p95", "duration_ms_p99", "duration_ms_min", "duration_ms_max", "duration_ms_stdev"):
            _require_optional_metric(getattr(self, name), field_name=name)
        if self.slowest_step_index is not None:
            _require_at_least_one(self.slowest_step_index, field_name="slowest_step_index")

    @classmethod
    def empty(cls) -> StepSpeedStats:
        # Return a valid no-step aggregate.
        return cls()


@dataclass(frozen=True, slots=True)
class StreamSpeedStats:
    """Aggregate speed metrics for measured text chunk streams."""

    stream_count: int = 0
    successful_stream_count: int = 0
    failed_stream_count: int = 0
    failure_rate: float = 0.0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None
    ttft_ms_mean: float | None = None
    ttft_ms_p95: float | None = None
    inter_chunk_gap_ms_mean: float | None = None
    inter_chunk_gap_ms_p95: float | None = None
    inter_chunk_gap_ms_max: float | None = None
    chunk_rate_per_second_mean: float | None = None
    chunk_count: int = 0
    duration_ms_p50: float | None = None
    duration_ms_p90: float | None = None
    duration_ms_p99: float | None = None
    duration_ms_min: float | None = None
    duration_ms_stdev: float | None = None
    ttft_ms_p50: float | None = None
    ttft_ms_p90: float | None = None
    ttft_ms_p99: float | None = None
    ttft_ms_min: float | None = None
    ttft_ms_stdev: float | None = None
    inter_chunk_gap_ms_p50: float | None = None
    inter_chunk_gap_ms_p90: float | None = None
    inter_chunk_gap_ms_p99: float | None = None
    inter_chunk_gap_ms_min: float | None = None
    inter_chunk_gap_ms_stdev: float | None = None
    chunk_rate_per_second_p50: float | None = None
    chunk_rate_per_second_p90: float | None = None
    chunk_rate_per_second_p95: float | None = None
    chunk_rate_per_second_p99: float | None = None
    chunk_rate_per_second_min: float | None = None
    chunk_rate_per_second_stdev: float | None = None
    cancelled_stream_count: int = 0
    cancellation_rate: float = 0.0

    def __post_init__(self) -> None:
        # Validate stream counts and latency/rate summaries.
        _require_non_negative_int(self.stream_count, field_name="stream_count")
        _require_non_negative_int(self.successful_stream_count, field_name="successful_stream_count")
        _require_non_negative_int(self.failed_stream_count, field_name="failed_stream_count")
        _require_non_negative_int(self.chunk_count, field_name="chunk_count")
        _require_non_negative_int(self.cancelled_stream_count, field_name="cancelled_stream_count")
        if self.successful_stream_count + self.failed_stream_count != self.stream_count:
            raise AgentSpeedValidationError("successful_stream_count plus failed_stream_count must equal stream_count.")
        if self.cancelled_stream_count > self.failed_stream_count:
            raise AgentSpeedValidationError("cancelled_stream_count cannot exceed failed_stream_count.")
        _require_non_negative_float(self.failure_rate, field_name="failure_rate")
        _require_non_negative_float(self.cancellation_rate, field_name="cancellation_rate")
        for name in ("duration_ms_mean", "duration_ms_p50", "duration_ms_p90", "duration_ms_p95", "duration_ms_p99", "duration_ms_min", "duration_ms_stdev", "ttft_ms_mean", "ttft_ms_p50", "ttft_ms_p90", "ttft_ms_p95", "ttft_ms_p99", "ttft_ms_min", "ttft_ms_stdev", "inter_chunk_gap_ms_mean", "inter_chunk_gap_ms_p50", "inter_chunk_gap_ms_p90", "inter_chunk_gap_ms_p95", "inter_chunk_gap_ms_p99", "inter_chunk_gap_ms_min", "inter_chunk_gap_ms_stdev", "inter_chunk_gap_ms_max", "chunk_rate_per_second_mean", "chunk_rate_per_second_p50", "chunk_rate_per_second_p90", "chunk_rate_per_second_p95", "chunk_rate_per_second_p99", "chunk_rate_per_second_min", "chunk_rate_per_second_stdev"):
            _require_optional_metric(getattr(self, name), field_name=name)

    @classmethod
    def empty(cls) -> StreamSpeedStats:
        # Return a valid no-stream aggregate.
        return cls()


@dataclass(frozen=True, slots=True)
class ModelSpeedStats:
    """Speed rollup for one provider/model pair."""

    provider: str
    model: str
    call_count: int = 0
    successful_call_count: int = 0
    failed_call_count: int = 0
    duration_ms_mean: float | None = None
    ttft_ms_mean: float | None = None
    weighted_output_tokens_per_second: float | None = None
    prompt_tokens_per_second: float | None = None
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None
    duration_ms_p90: float | None = None
    duration_ms_p95: float | None = None
    duration_ms_min: float | None = None
    duration_ms_stdev: float | None = None
    ttft_ms_p90: float | None = None
    ttft_ms_p95: float | None = None
    output_tokens_per_second_p90: float | None = None
    output_tokens_per_second_min: float | None = None
    output_tokens_per_second_stdev: float | None = None
    retry_count_total: int = AGENT_SPEED_ZERO_COUNT
    fallback_call_count: int = AGENT_SPEED_ZERO_COUNT
    cancelled_call_count: int = 0
    cancellation_rate: float = 0.0

    def __post_init__(self) -> None:
        # @intent validate-model-speed-group
        # Validate grouping identity and model outcome counts.
        _require_non_empty_str(self.provider, field_name="provider")
        _require_non_empty_str(self.model, field_name="model")
        _require_non_negative_int(self.call_count, field_name="call_count")
        _require_non_negative_int(self.successful_call_count, field_name="successful_call_count")
        _require_non_negative_int(self.failed_call_count, field_name="failed_call_count")
        _require_non_negative_int(self.retry_count_total, field_name="retry_count_total")
        _require_non_negative_int(self.fallback_call_count, field_name="fallback_call_count")
        _require_non_negative_int(self.cancelled_call_count, field_name="cancelled_call_count")
        if self.successful_call_count + self.failed_call_count != self.call_count:
            raise AgentSpeedValidationError("model outcome counts must equal call_count.")
        if self.cancelled_call_count > self.failed_call_count:
            raise AgentSpeedValidationError("cancelled_call_count cannot exceed failed_call_count.")
        _require_non_negative_float(self.cancellation_rate, field_name="cancellation_rate")
        for name in ("duration_ms_mean", "duration_ms_p90", "duration_ms_p95", "duration_ms_min", "duration_ms_stdev", "ttft_ms_mean", "ttft_ms_p90", "ttft_ms_p95", "weighted_output_tokens_per_second", "output_tokens_per_second_p90", "output_tokens_per_second_min", "output_tokens_per_second_stdev", "prompt_tokens_per_second"):
            _require_optional_metric(getattr(self, name), field_name=name)
        for name, value in (("input_tokens_total", self.input_tokens_total), ("output_tokens_total", self.output_tokens_total)):
            if value is not None:
                _require_non_negative_int(value, field_name=name)


@dataclass(frozen=True, slots=True)
class ToolSpeedStats:
    """Speed rollup for one tool name."""

    tool_name: str
    tool_call_count: int = 0
    successful_tool_call_count: int = 0
    failed_tool_call_count: int = 0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None
    failure_rate: float = 0.0
    timed_out_count: int = 0
    timeout_rate: float = AGENT_SPEED_ZERO_SECONDS
    cancelled_tool_call_count: int = 0
    cancellation_rate: float = 0.0
    duration_ms_p90: float | None = None
    duration_ms_min: float | None = None
    duration_ms_stdev: float | None = None

    def __post_init__(self) -> None:
        # Validate grouping identity and tool outcome counts.
        _require_non_empty_str(self.tool_name, field_name="tool_name")
        _require_non_negative_int(self.tool_call_count, field_name="tool_call_count")
        _require_non_negative_int(self.successful_tool_call_count, field_name="successful_tool_call_count")
        _require_non_negative_int(self.failed_tool_call_count, field_name="failed_tool_call_count")
        _require_non_negative_int(self.cancelled_tool_call_count, field_name="cancelled_tool_call_count")
        if self.successful_tool_call_count + self.failed_tool_call_count != self.tool_call_count:
            raise AgentSpeedValidationError("tool outcome counts must equal tool_call_count.")
        if self.timed_out_count > self.failed_tool_call_count or self.cancelled_tool_call_count > self.failed_tool_call_count:
            raise AgentSpeedValidationError("tool timeout and cancellation counts cannot exceed failed_tool_call_count.")
        _require_non_negative_float(self.failure_rate, field_name="failure_rate")
        _require_non_negative_int(self.timed_out_count, field_name="timed_out_count")
        _require_non_negative_float(self.timeout_rate, field_name="timeout_rate")
        _require_non_negative_float(self.cancellation_rate, field_name="cancellation_rate")
        for name in ("duration_ms_mean", "duration_ms_p90", "duration_ms_p95", "duration_ms_min", "duration_ms_stdev"):
            _require_optional_metric(getattr(self, name), field_name=name)


@dataclass(frozen=True, slots=True)
class RunSpeedStats:
    """Whole-run speed metrics and overlap/concurrency breakdowns."""

    total_duration_ms: float | None = None
    cold_start_overhead_ms: float | None = None
    framework_overhead_ms: float | None = None
    parallelism_efficiency: float | None = None
    time_to_first_tool_ms: float | None = None
    time_to_result_ready_ms: float | None = None
    active_work_ms: float | None = None
    overlap_ms: float | None = None
    max_concurrency: int | None = None
    average_concurrency: float | None = None
    retry_wait_ms_total: float | None = None
    fallback_overhead_ms: float | None = None
    fallback_switch_count: int = AGENT_SPEED_ZERO_COUNT
    input_tokens_total: int | None = None
    output_tokens_total: int | None = None

    def __post_init__(self) -> None:
        # @intent validate-fallback-speed-aggregate
        # Validate run durations, concurrency, switch counts, and token totals.
        for name in ("total_duration_ms", "framework_overhead_ms", "time_to_first_tool_ms", "time_to_result_ready_ms", "active_work_ms", "overlap_ms", "average_concurrency", "retry_wait_ms_total", "fallback_overhead_ms"):
            _require_optional_metric(getattr(self, name), field_name=name)
        if self.cold_start_overhead_ms is not None and (isinstance(self.cold_start_overhead_ms, bool) or not isinstance(self.cold_start_overhead_ms, (int, float))):
            raise AgentSpeedValidationError("cold_start_overhead_ms must be numeric.")
        if self.parallelism_efficiency is not None:
            _require_non_negative_float(self.parallelism_efficiency, field_name="parallelism_efficiency")
        if self.max_concurrency is not None:
            _require_at_least_one(self.max_concurrency, field_name="max_concurrency")
        _require_non_negative_int(self.fallback_switch_count, field_name="fallback_switch_count")
        for name, value in (("input_tokens_total", self.input_tokens_total), ("output_tokens_total", self.output_tokens_total)):
            if value is not None:
                _require_non_negative_int(value, field_name=name)

    @classmethod
    def empty(cls) -> RunSpeedStats:
        # Return a valid aggregate before run boundaries are closed.
        return cls()


@dataclass(frozen=True, slots=True)
class RunSpeedSnapshot:
    """Bounded-history copy of the speed summaries from one completed run."""

    run_stats: RunSpeedStats
    call_stats: CallSpeedStats
    tool_call_stats: ToolCallSpeedStats
    is_cold_start: bool
    first_call_duration_ms: float | None = None
    subsequent_call_duration_ms: float | None = None

    def __post_init__(self) -> None:
        # Validate the history outcome flag.
        _require_bool(self.is_cold_start, field_name="is_cold_start")
        _require_optional_metric(self.first_call_duration_ms, field_name="first_call_duration_ms")
        _require_optional_metric(self.subsequent_call_duration_ms, field_name="subsequent_call_duration_ms")


@dataclass(frozen=True, slots=True)
class AgentSpeedHistory:
    """Aggregates over the bounded completed-run history."""

    runs: tuple[RunSpeedSnapshot, ...] = field(default_factory=tuple)
    run_count: int = 0
    cold_run_count: int = 0
    warm_run_count: int = 0
    first_call_duration_ms_mean: float | None = None
    subsequent_call_duration_ms_mean: float | None = None
    run_duration_ms_mean: float | None = None
    run_duration_ms_p95: float | None = None

    def __post_init__(self) -> None:
        # Validate history counts and optional summaries.
        _require_non_negative_int(self.run_count, field_name="run_count")
        _require_non_negative_int(self.cold_run_count, field_name="cold_run_count")
        _require_non_negative_int(self.warm_run_count, field_name="warm_run_count")
        if self.cold_run_count + self.warm_run_count != self.run_count:
            raise AgentSpeedValidationError("cold_run_count plus warm_run_count must equal run_count.")
        if len(self.runs) != self.run_count:
            raise AgentSpeedValidationError("runs length must equal run_count.")
        for name in ("first_call_duration_ms_mean", "subsequent_call_duration_ms_mean", "run_duration_ms_mean", "run_duration_ms_p95"):
            _require_optional_metric(getattr(self, name), field_name=name)

    @classmethod
    def empty(cls) -> AgentSpeedHistory:
        # Return a valid empty history aggregate.
        return cls()


@dataclass(frozen=True, slots=True)
class AgentSpeedRollup:
    """Complete speed ledger plus run, grouping, stream, and history summaries."""

    calls: tuple[CallSpeedRecord, ...] = field(default_factory=tuple)
    tool_calls: tuple[ToolCallSpeedRecord, ...] = field(default_factory=tuple)
    steps: tuple[StepSpeedRecord, ...] = field(default_factory=tuple)
    call_stats: CallSpeedStats = field(default_factory=CallSpeedStats.empty)
    tool_call_stats: ToolCallSpeedStats = field(default_factory=ToolCallSpeedStats.empty)
    step_stats: StepSpeedStats = field(default_factory=StepSpeedStats.empty)
    run_stats: RunSpeedStats = field(default_factory=RunSpeedStats.empty)
    recording_integrity: AgentSpeedRecordingIntegrity = AgentSpeedRecordingIntegrity.INTACT
    streams: tuple[StreamSpeedRecord, ...] = field(default_factory=tuple)
    retry_waits: tuple[RetryWaitSpeedRecord, ...] = field(default_factory=tuple)
    stream_stats: StreamSpeedStats = field(default_factory=StreamSpeedStats.empty)
    model_stats: tuple[ModelSpeedStats, ...] = field(default_factory=tuple)
    tool_stats: tuple[ToolSpeedStats, ...] = field(default_factory=tuple)
    history_stats: AgentSpeedHistory = field(default_factory=AgentSpeedHistory.empty)

    @classmethod
    def empty(cls) -> AgentSpeedRollup:
        # Return the valid no-activity rollup.
        return cls()


__all__ = [
    "AgentSpeedHistory",
    "AgentSpeedRollup",
    "CallSpeedRecord",
    "CallSpeedStats",
    "ModelSpeedStats",
    "RecordModelCallFailureInput",
    "RecordModelCallInput",
    "RecordRetryWaitInput",
    "RecordStepInput",
    "RecordStreamInput",
    "RecordToolCallInput",
    "RetryWaitSpeedRecord",
    "RunSpeedSnapshot",
    "RunSpeedStats",
    "StepSpeedRecord",
    "StepSpeedStats",
    "StreamSpeedRecord",
    "StreamSpeedStats",
    "ToolCallSpeedRecord",
    "ToolCallSpeedStats",
    "ToolSpeedStats",
]
