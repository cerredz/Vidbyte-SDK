"""FILE: vidbyte/lib/dataclasses/speed.py

PURPOSE:
    Defines every input, record, stats, and rollup dataclass AgentSpeedTracker
    reads or produces: one timed model call, one timed tool call, one timed
    loop iteration, and the aggregate statistics folded over a whole run.
    Every dataclass validates its own fields in __post_init__ and raises
    AgentSpeedValidationError on an invalid shape, so a caller never builds a
    rollup out of nonsense timestamps.

ROLE IN CODEBASE:
    Built by vidbyte/agents/speed/tracker.py (AgentSpeedTracker.record_call,
    record_tool_call, record_step, and rollup) using vidbyte/lib/util/math.py
    for aggregation. AgentSpeedRollup is surfaced on
    BaseAgent.get_speed_stats() (vidbyte/agents/base.py). Re-exported from
    vidbyte/lib/dataclasses/__init__.py, vidbyte/agents/speed/__init__.py, and
    the package root vidbyte/__init__.py.

ARCHITECTURE NOTE:
    RecordModelCallInput / CallSpeedRecord time one model call.
    RecordToolCallInput / ToolCallSpeedRecord time one tool call.
    RecordStepInput / StepSpeedRecord time one loop iteration (not yet
    produced by vidbyte/agents/runtime.py; see
    docs/design/agent-speed-tracking.md Non-Goals). CallSpeedStats /
    ToolCallSpeedStats / StepSpeedStats / RunSpeedStats are the four nested
    aggregate dataclasses AgentSpeedTracker.rollup() assembles.
    AgentSpeedRollup is the whole-run ledger plus every stats dataclass. Every
    enum/dataclass this feature introduces lives under vidbyte/lib/ rather
    than beside the tracker (unlike vidbyte/agents/pricing/records.py's
    UsageRecord/UsageRollup), per explicit design decision recorded in the
    design doc's Alternatives Considered.

FUNCTION INVENTORY:
    RecordModelCallInput, CallSpeedRecord, RecordToolCallInput,
    ToolCallSpeedRecord, RecordStepInput, StepSpeedRecord: frozen, validated
    dataclasses; CallSpeedRecord/ToolCallSpeedRecord/StepSpeedRecord also
    expose duration_ms (and ttft_ms/tokens_per_second on CallSpeedRecord) as
    properties. CallSpeedStats, ToolCallSpeedStats, StepSpeedStats,
    RunSpeedStats, AgentSpeedRollup: frozen, validated aggregate dataclasses,
    each with an .empty() classmethod for the no-data case. Tests:
    tests/test_agent_speed.py (RecordModelCallInputValidationTests,
    CallSpeedRecordTests, ToolCallSpeedRecordTests).

COMMON MODIFICATION PATTERNS:
    Add a new speed metric by adding a field to the relevant *Stats
    dataclass here, then computing it in the matching
    AgentSpeedTracker._build_*_stats helper in vidbyte/agents/speed/tracker.py
    in the same change. Add validation for any new field in that dataclass's
    __post_init__ using the shared _require_* helpers at the top of this file.

WHAT NOT TO DO IN THIS FILE:
    1. Do not add mutable state or tracking logic; that belongs in
       AgentSpeedTracker (vidbyte/agents/speed/tracker.py).
    2. Do not add general numeric aggregation (percentile, mean, max,
       argmax); that belongs in MathHelper (vidbyte/lib/util/math.py).
    3. Do not import provider-specific response types to type `response` on
       RecordModelCallInput; it is intentionally duck-typed with only an
       is-not-None check, matching UsageTracker.record_call's own contract.

KNOWN EDGE CASES:
    A CallSpeedStats/ToolCallSpeedStats/StepSpeedStats/RunSpeedStats/
    AgentSpeedRollup with all-None optional fields (via .empty()) is the
    valid, expected shape for a run with no recorded activity of that kind —
    not an error state. cold_start_overhead_ms and framework_overhead_ms on
    RunSpeedStats may legitimately be negative (e.g. the first call was
    faster than average) and are only type-checked, not sign-checked.

RELATED DOCS:
    https://github.com/cerredz/Vidbyte-SDK/blob/main/docs/design/agent-speed-tracking.md

TESTS:
    tests/test_agent_speed.py (RecordModelCallInputValidationTests,
    CallSpeedRecordTests, ToolCallSpeedRecordTests, and indirectly every
    AgentSpeedTrackerRollupTests case).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.speed import AgentSpeedRecordingIntegrity
from vidbyte.lib.errors import AgentSpeedValidationError

_MILLISECONDS_PER_SECOND = 1000
_DEFAULT_RETRY_COUNT = 0


def _require_not_none(value: Any, *, field_name: str) -> None:
    # Shared guard: a dataclass field that must never be None (e.g. a raw provider response).
    if value is None:
        raise AgentSpeedValidationError(
            f"{field_name} must not be None.", details={"field": field_name}
        )


def _require_non_negative_float(value: float, *, field_name: str) -> None:
    # bool is an int/float subclass in Python, so it is excluded explicitly here and
    # everywhere else this guard is used in this file.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentSpeedValidationError(
            f"{field_name} must be numeric.", details={"field": field_name, "type": type(value).__name__}
        )
    if value < 0:
        raise AgentSpeedValidationError(
            f"{field_name} cannot be negative.", details={"field": field_name, "value": value}
        )


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentSpeedValidationError(
            f"{field_name} must be an int.", details={"field": field_name, "type": type(value).__name__}
        )
    if value < 0:
        raise AgentSpeedValidationError(
            f"{field_name} cannot be negative.", details={"field": field_name, "value": value}
        )


def _require_non_empty_str(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AgentSpeedValidationError(
            f"{field_name} must be a non-empty string.", details={"field": field_name, "value": value}
        )


def _require_bool(value: bool, *, field_name: str) -> None:
    # One shared owner for the timed_out identity so RecordToolCallInput and
    # ToolCallSpeedRecord can never drift onto different accepted shapes.
    if not isinstance(value, bool):
        raise AgentSpeedValidationError(
            f"{field_name} must be a bool.", details={"field": field_name, "type": type(value).__name__}
        )


def _require_at_least_one(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AgentSpeedValidationError(
            f"{field_name} must be an int >= 1.", details={"field": field_name, "value": value}
        )


def _require_ordered_percentiles(p50: float | None, p95: float | None, p99: float | None, *, field_prefix: str) -> None:
    # A real percentile inversion means the aggregation math itself is broken;
    # catching it here is cheaper than discovering it downstream in a report.
    if p50 is not None and p95 is not None and p50 > p95:
        raise AgentSpeedValidationError(
            f"{field_prefix}_p50 cannot exceed {field_prefix}_p95.",
            details={"field": f"{field_prefix}_p50", "p50": p50, "p95": p95},
        )
    if p95 is not None and p99 is not None and p95 > p99:
        raise AgentSpeedValidationError(
            f"{field_prefix}_p95 cannot exceed {field_prefix}_p99.",
            details={"field": f"{field_prefix}_p95", "p95": p95, "p99": p99},
        )


@dataclass(frozen=True, slots=True)
class RecordModelCallInput:
    """Caller-assembled input to AgentSpeedTracker.record_call."""

    response: object
    dispatched_at: float
    first_token_at: float | None = None
    output_tokens: int | None = None
    retry_count: int = _DEFAULT_RETRY_COUNT
    fallback_index: int | None = None

    def __post_init__(self) -> None:
        # @intent retry-and-fallback-fields-are-best-effort-not-authoritative
        # retry_count/fallback_index describe what AgentRuntime's fallback chain observed
        # at the call site, not a separately-metered retry duration (that time is already
        # folded into duration_ms by construction — see docs/design/agent-speed-tracking.md
        # Non-Goals). Only their shape is validated here; a caller across the
        # AgentRuntime/provider boundary cannot make them negative or non-numeric.
        _require_not_none(self.response, field_name="response")
        _require_non_negative_float(self.dispatched_at, field_name="dispatched_at")
        if self.first_token_at is not None:
            _require_non_negative_float(self.first_token_at, field_name="first_token_at")
            if self.first_token_at < self.dispatched_at:
                raise AgentSpeedValidationError(
                    "first_token_at cannot precede dispatched_at.",
                    details={"first_token_at": self.first_token_at, "dispatched_at": self.dispatched_at},
                )
        if self.output_tokens is not None:
            _require_non_negative_int(self.output_tokens, field_name="output_tokens")
        _require_non_negative_int(self.retry_count, field_name="retry_count")
        if self.fallback_index is not None:
            _require_non_negative_int(self.fallback_index, field_name="fallback_index")


@dataclass(frozen=True, slots=True)
class CallSpeedRecord:
    """One timed model call, stored by AgentSpeedTracker and returned by record_call."""

    call_index: int
    provider: str
    model: str
    dispatched_at: float
    completed_at: float
    first_token_at: float | None = None
    output_tokens: int | None = None
    retry_count: int = _DEFAULT_RETRY_COUNT
    fallback_index: int | None = None

    def __post_init__(self) -> None:
        # @intent provider-and-model-are-the-fallback-chains-real-answer
        # A fallback transition can replace the provider mid-run (AgentRuntime's outer
        # loop reassigns state.provider and restarts from the top), so provider/model on
        # this record must reflect whichever attempt actually produced a usable response,
        # not the run's original provider. fallback_index carries which attempt that was.
        _require_at_least_one(self.call_index, field_name="call_index")
        _require_non_empty_str(self.provider, field_name="provider")
        _require_non_empty_str(self.model, field_name="model")
        _require_non_negative_float(self.dispatched_at, field_name="dispatched_at")
        _require_non_negative_float(self.completed_at, field_name="completed_at")
        if self.completed_at < self.dispatched_at:
            raise AgentSpeedValidationError(
                "completed_at cannot precede dispatched_at.",
                details={"completed_at": self.completed_at, "dispatched_at": self.dispatched_at},
            )
        if self.first_token_at is not None:
            _require_non_negative_float(self.first_token_at, field_name="first_token_at")
            if not (self.dispatched_at <= self.first_token_at <= self.completed_at):
                raise AgentSpeedValidationError(
                    "first_token_at must fall within [dispatched_at, completed_at].",
                    details={
                        "first_token_at": self.first_token_at,
                        "dispatched_at": self.dispatched_at,
                        "completed_at": self.completed_at,
                    },
                )
        if self.output_tokens is not None:
            _require_non_negative_int(self.output_tokens, field_name="output_tokens")
        _require_non_negative_int(self.retry_count, field_name="retry_count")
        if self.fallback_index is not None:
            _require_non_negative_int(self.fallback_index, field_name="fallback_index")

    @property
    def duration_ms(self) -> float:
        """Total wall-clock time from dispatch to a completed response, in milliseconds."""
        return (self.completed_at - self.dispatched_at) * _MILLISECONDS_PER_SECOND

    @property
    def ttft_ms(self) -> float | None:
        """Time from dispatch to the first streamed token, or None when the call was not streamed."""
        if self.first_token_at is None:
            return None
        return (self.first_token_at - self.dispatched_at) * _MILLISECONDS_PER_SECOND

    @property
    def tokens_per_second(self) -> float | None:
        """Output-token generation rate over the post-first-token window, or None when tokens are unknown."""
        if self.output_tokens is None:
            return None
        generation_start = self.first_token_at if self.first_token_at is not None else self.dispatched_at
        generation_seconds = self.completed_at - generation_start
        return self.output_tokens / generation_seconds if generation_seconds > 0 else None


@dataclass(frozen=True, slots=True)
class RecordToolCallInput:
    """Caller-assembled input to AgentSpeedTracker.record_tool_call."""

    tool_name: str
    started_at: float
    timed_out: bool = False

    def __post_init__(self) -> None:
        _require_non_empty_str(self.tool_name, field_name="tool_name")
        _require_non_negative_float(self.started_at, field_name="started_at")
        _require_bool(self.timed_out, field_name="timed_out")


@dataclass(frozen=True, slots=True)
class ToolCallSpeedRecord:
    """One timed tool call, stored by AgentSpeedTracker and returned by record_tool_call."""

    call_index: int
    tool_name: str
    started_at: float
    completed_at: float
    timed_out: bool = False

    def __post_init__(self) -> None:
        _require_at_least_one(self.call_index, field_name="call_index")
        _require_non_empty_str(self.tool_name, field_name="tool_name")
        _require_non_negative_float(self.started_at, field_name="started_at")
        _require_non_negative_float(self.completed_at, field_name="completed_at")
        if self.completed_at < self.started_at:
            raise AgentSpeedValidationError(
                "completed_at cannot precede started_at.",
                details={"completed_at": self.completed_at, "started_at": self.started_at},
            )
        _require_bool(self.timed_out, field_name="timed_out")

    @property
    def duration_ms(self) -> float:
        """Total wall-clock time from dispatch to completion, in milliseconds."""
        return (self.completed_at - self.started_at) * _MILLISECONDS_PER_SECOND


@dataclass(frozen=True, slots=True)
class RecordStepInput:
    """Caller-assembled input to AgentSpeedTracker.record_step. Not yet wired into runtime.py."""

    started_at: float
    model_call_index: int | None = None
    tool_call_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _require_non_negative_float(self.started_at, field_name="started_at")
        if self.model_call_index is not None:
            _require_at_least_one(self.model_call_index, field_name="model_call_index")
        _validate_tool_call_indices(self.tool_call_indices)


@dataclass(frozen=True, slots=True)
class StepSpeedRecord:
    """One timed loop iteration. Not yet produced by runtime.py in this PR."""

    iteration_index: int
    started_at: float
    completed_at: float
    model_call_index: int | None = None
    tool_call_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        _require_at_least_one(self.iteration_index, field_name="iteration_index")
        _require_non_negative_float(self.started_at, field_name="started_at")
        _require_non_negative_float(self.completed_at, field_name="completed_at")
        if self.completed_at < self.started_at:
            raise AgentSpeedValidationError(
                "completed_at cannot precede started_at.",
                details={"completed_at": self.completed_at, "started_at": self.started_at},
            )
        if self.model_call_index is not None:
            _require_at_least_one(self.model_call_index, field_name="model_call_index")
        _validate_tool_call_indices(self.tool_call_indices)

    @property
    def duration_ms(self) -> float:
        """Total wall-clock time for this loop iteration, in milliseconds."""
        return (self.completed_at - self.started_at) * _MILLISECONDS_PER_SECOND


def _validate_tool_call_indices(indices: tuple[int, ...]) -> None:
    # Shared by RecordStepInput and StepSpeedRecord: every index must be a real
    # 1-based ToolCallSpeedRecord.call_index, with no duplicates.
    if len(set(indices)) != len(indices):
        raise AgentSpeedValidationError(
            "tool_call_indices cannot contain duplicates.", details={"tool_call_indices": indices}
        )
    for index in indices:
        _require_at_least_one(index, field_name="tool_call_indices item")


@dataclass(frozen=True, slots=True)
class CallSpeedStats:
    """Aggregate statistics over one run's CallSpeedRecords. Built by AgentSpeedTracker._build_call_stats."""

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

    def __post_init__(self) -> None:
        _require_non_negative_int(self.call_count, field_name="call_count")
        for name in ("ttft_ms_mean", "ttft_ms_p50", "ttft_ms_p95", "ttft_ms_p99", "duration_ms_mean", "duration_ms_p50", "duration_ms_p95", "duration_ms_p99", "duration_ms_max", "tokens_per_second_mean"):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_float(value, field_name=name)
        if self.slowest_call_index is not None:
            _require_at_least_one(self.slowest_call_index, field_name="slowest_call_index")
        _require_ordered_percentiles(self.ttft_ms_p50, self.ttft_ms_p95, self.ttft_ms_p99, field_prefix="ttft_ms")
        _require_ordered_percentiles(self.duration_ms_p50, self.duration_ms_p95, self.duration_ms_p99, field_prefix="duration_ms")

    @classmethod
    def empty(cls) -> "CallSpeedStats":
        """Return the zero-value stats for a run with no recorded model calls."""
        return cls()


@dataclass(frozen=True, slots=True)
class ToolCallSpeedStats:
    """Aggregate statistics over one run's ToolCallSpeedRecords."""

    tool_call_count: int = 0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None
    duration_ms_max: float | None = None
    slowest_tool_call_index: int | None = None

    def __post_init__(self) -> None:
        _require_non_negative_int(self.tool_call_count, field_name="tool_call_count")
        for name in ("duration_ms_mean", "duration_ms_p95", "duration_ms_max"):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_float(value, field_name=name)
        if self.slowest_tool_call_index is not None:
            _require_at_least_one(self.slowest_tool_call_index, field_name="slowest_tool_call_index")

    @classmethod
    def empty(cls) -> "ToolCallSpeedStats":
        """Return the zero-value stats for a run with no recorded tool calls."""
        return cls()


@dataclass(frozen=True, slots=True)
class StepSpeedStats:
    """Aggregate statistics over one run's StepSpeedRecords. Empty until step wiring lands."""

    step_count: int = 0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None

    def __post_init__(self) -> None:
        _require_non_negative_int(self.step_count, field_name="step_count")
        for name in ("duration_ms_mean", "duration_ms_p95"):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_float(value, field_name=name)

    @classmethod
    def empty(cls) -> "StepSpeedStats":
        """Return the zero-value stats for a run with no recorded loop iterations."""
        return cls()


@dataclass(frozen=True, slots=True)
class RunSpeedStats:
    """Whole-run-level derived statistics: total duration and overhead breakdowns."""

    total_duration_ms: float | None = None
    cold_start_overhead_ms: float | None = None
    framework_overhead_ms: float | None = None
    parallelism_efficiency: float | None = None

    def __post_init__(self) -> None:
        if self.total_duration_ms is not None:
            _require_non_negative_float(self.total_duration_ms, field_name="total_duration_ms")
        if self.parallelism_efficiency is not None:
            _require_non_negative_float(self.parallelism_efficiency, field_name="parallelism_efficiency")
        # cold_start_overhead_ms and framework_overhead_ms may legitimately be negative
        # (e.g. the first call was faster than average, or overhead rounds below zero),
        # so only their numeric type is checked, not their sign.
        for name in ("cold_start_overhead_ms", "framework_overhead_ms"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise AgentSpeedValidationError(
                    f"{name} must be numeric.", details={"field": name, "type": type(value).__name__}
                )

    @classmethod
    def empty(cls) -> "RunSpeedStats":
        """Return the zero-value stats for a run with no recorded boundary marks."""
        return cls()


@dataclass(frozen=True, slots=True)
class AgentSpeedRollup:
    """Whole-run speed ledger and derived statistics. Returned by AgentSpeedTracker.rollup()."""

    calls: tuple[CallSpeedRecord, ...] = field(default_factory=tuple)
    tool_calls: tuple[ToolCallSpeedRecord, ...] = field(default_factory=tuple)
    steps: tuple[StepSpeedRecord, ...] = field(default_factory=tuple)
    call_stats: CallSpeedStats = field(default_factory=CallSpeedStats.empty)
    tool_call_stats: ToolCallSpeedStats = field(default_factory=ToolCallSpeedStats.empty)
    step_stats: StepSpeedStats = field(default_factory=StepSpeedStats.empty)
    run_stats: RunSpeedStats = field(default_factory=RunSpeedStats.empty)
    recording_integrity: AgentSpeedRecordingIntegrity = AgentSpeedRecordingIntegrity.INTACT

    @classmethod
    def empty(cls) -> "AgentSpeedRollup":
        """Return the zero-value rollup for a run with no recorded activity."""
        return cls()


__all__ = [
    "AgentSpeedRollup",
    "CallSpeedRecord",
    "CallSpeedStats",
    "RecordModelCallInput",
    "RecordStepInput",
    "RecordToolCallInput",
    "RunSpeedStats",
    "StepSpeedRecord",
    "StepSpeedStats",
    "ToolCallSpeedRecord",
    "ToolCallSpeedStats",
]
