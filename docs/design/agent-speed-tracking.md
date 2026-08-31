# Design Doc: Agent Speed Tracking

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-31
**Last Updated:** 2026-08-31

---

## 1. Overview

This adds speed/latency instrumentation to the Vidbyte SDK's agent runtime, mirroring the existing `UsageTracker` (cost) architecture exactly: a new `AgentSpeedTracker` class accumulates per-call and per-tool-call timing records during one agent run, and a new `BaseAgent.get_speed_stats()` method exposes the rolled-up statistics (mean/p50/p95/p99 durations, time-to-first-token where available, tokens-per-second, cold-start overhead, and tool-call parallelism efficiency). Every dataclass and enum the feature introduces lives in `vidbyte/lib/`, all general-purpose statistics math (mean, percentile, max, argmax) is centralized in a new `MathHelper` static-method class at `vidbyte/lib/util/math.py`, and every public method on `AgentSpeedTracker` takes a validated dataclass as input and returns a validated dataclass as output. This is the "speed" counterpart to the cost-tracking work that shipped in `vidbyte/agents/pricing/`, and is a prerequisite for a future combined cost/speed/quality report on top of harnesses such as the research harness.

---

## 2. Goals & Non-Goals

### Goals

- Add `AgentSpeedTracker` (`vidbyte/agents/speed/tracker.py`), instantiated once per `BaseAgent` and reset at the top of every `generate_reply()` call, exactly mirroring `UsageTracker`'s lifecycle.
- Track, per model call: dispatch time, completion time, optional time-to-first-token, output tokens (for tokens/second), retry/fallback context where available.
- Track, per tool call: dispatch time, completion time, whether it was a timeout.
- Track, per run: run start/end wall-clock, even when the run raises.
- Compute, on demand via `AgentSpeedTracker.rollup()`: mean/p50/p95/p99 call duration, mean/p50/p95/p99 TTFT, mean tokens/second, mean/max/slowest-index tool-call duration, cold-start overhead, framework overhead, and tool-call parallelism efficiency.
- Expose the rollup on `BaseAgent.get_speed_stats() -> AgentSpeedRollup`, mirroring `get_usage() -> UsageRollup`.
- Put every enum and dataclass this feature introduces under `vidbyte/lib/enums/` and `vidbyte/lib/dataclasses/`, per explicit instruction, rather than co-locating them next to the tracker (which is where the existing `UsageRecord`/`UsageRollup` live today, in `vidbyte/agents/pricing/records.py`).
- Centralize mean/percentile/max/argmax math in a `MathHelper` static-method class at `vidbyte/lib/util/math.py` so `AgentSpeedTracker` never inlines statistics logic.
- Give every `AgentSpeedTracker` method a single dataclass input (when it has meaningful inputs to bundle) and a dataclass output, with `__post_init__` validation on every new dataclass, raising a new `AgentSpeedValidationError`.
- Split `AgentSpeedTracker.rollup()` into small named helpers (`_build_call_stats`, `_build_tool_call_stats`, `_build_step_stats`, `_build_run_stats`) that each build one nested stats dataclass, rather than one large function.
- Wire model-call and tool-call timing into `AgentRuntime` (`vidbyte/agents/runtime.py`) and run-boundary timing into `BaseAgent.generate_reply()` (`vidbyte/agents/base.py`), at the same call sites `UsageTracker` already hooks into.
- Fail open: a bug inside speed tracking must never break an agent run. Mirrors `UsageTracker.mark_recording_corrupted()` / `UsageRecordingIntegrity`.

### Non-Goals

- **True per-step (one loop iteration) timing is not wired into `AgentRuntime` in this PR.** The dataclasses, enum member, and `AgentSpeedTracker.record_step()` method are fully built and unit-testable, but nothing in `runtime.py`'s model/tool loop calls `record_step()` yet. See §14 Alternative 3 for why this is deferred rather than force-fit.
- **Time-to-first-token is not populated from a real streaming call in this PR.** `AgentRuntime` has no streaming call path today (verified: no `stream` references in `vidbyte/agents/runtime.py`). `RecordModelCallInput.first_token_at` exists and is honored end-to-end, but every real call site passes `None` until a streaming invocation path exists. `CallSpeedStats.ttft_ms_*` fields are `None` until then.
- **Precise separate `retry_count` accounting is not implemented.** `_invoke_with_middleware`'s own `on_model_error` retry loop is internal retry time that is already folded into one call's measured `duration_ms` by construction (the outer loop only calls `record_call()` once a usable response comes back). The `retry_count` field exists on `RecordModelCallInput`/`CallSpeedRecord` for forward compatibility, defaults to `0` at the real call site, and is not asserted to be accurate in this PR.
- No changes to `UsageTracker`, `UsageRollup`, or any billing/cost code.
- No changes to non-`LINEAR` `AgentRuntimeType`s (actor-model runtimes). This mirrors the existing scope limit on `usage_tracker` threading in `BaseAgent._runtime()` (`vidbyte/agents/base.py:976-979`), which only injects `usage_tracker` for `AgentRuntimeType.LINEAR`.
- No customer-facing report, harness-level aggregation, or research-harness wiring. This PR is the SDK primitive only; the combined cost/speed/quality report is a separate, later PR against `vidbyte/backend/services/harnesses/research/`.
- No new public exports beyond mirroring exactly what `UsageTracker`/`UsageRollup` already export at the package root.

---

## 3. Background & Context

### Why now

A prior conversation in this session audited how cost, speed, and quality are reported for the research harness, following AWS's documented pattern of bundling cost + latency + quality into one report because that combination is what actually drives a model/approach decision. That audit found cost fully solved as a reusable SDK primitive (`vidbyte/agents/pricing/`), but found no SDK-level speed/latency primitive at all — only a coarse whole-session wall-clock derived from checkpoint timestamps (`vidbyte/sessions/usage.py`), and a per-run `HarnessRun.started_at`/`ended_at` that isn't threaded into any product-facing result. The user then asked for a full checklist of speed metrics and an interface sketch mirroring `UsageTracker`. This design doc is the follow-up: turn that sketch into an implementable design that also satisfies three pieces of explicit feedback:

1. Every enum/dataclass this feature introduces must live under `vidbyte/lib/`, in the same `enums/`/`dataclasses/` subfolders every other SDK contract already uses (e.g. `vidbyte/lib/dataclasses/sessions.py`, `vidbyte/lib/dataclasses/harnesses.py`).
2. General statistics helpers (percentile, argmax, mean, max) must live in one `MathHelper` static-method class at `vidbyte/lib/util/math.py`, not inlined in the tracker.
3. The tracker class — renamed `AgentSpeedTracker` — must take and return validated dataclasses on every method that has meaningful inputs, and `rollup()` must be split into smaller helpers rather than one large function.

### Current state

- **Cost tracking** (the pattern being mirrored): `vidbyte/agents/pricing/tracker.py` defines `UsageTracker`, a per-run accumulator with `record_call()`/`record_operation()`/`rollup()`/`reset()`. Its records (`UsageRecord`, `OperationUsageRecord`, `UsageRollup`) live in `vidbyte/agents/pricing/records.py` — next to the tracker, not in `vidbyte/lib/`. `BaseAgent.__init__` creates `self._usage_tracker = UsageTracker()` (`vidbyte/agents/base.py:224`); `generate_reply()` calls `self._usage_tracker.reset()` at the top of every run (`base.py:595`); `get_usage()`/`get_cost_usd()` read it back (`base.py:720-726`); and `BaseAgent._runtime()` passes `kwargs["usage_tracker"] = self._usage_tracker` into the constructed `AgentRuntime`, but **only** for `AgentRuntimeType.LINEAR` (`base.py:976-979`). `AgentRuntime.__init__` accepts `usage_tracker: UsageTracker | None = None` and defaults to a fresh one (`vidbyte/agents/runtime.py:186`). Inside the model/tool loop, `usage_tracker.record_call(raw_result)` fires once per successful model response (`runtime.py:412`).
- **No speed primitive exists.** `grep` for `stream`/`time to first token`/`ttft` inside `vidbyte/agents/runtime.py` returns nothing. The only timing signal already flowing through the runtime is `MiddlewareContext.elapsed_seconds`, computed as `self.middleware.clock() - state.started_at` (`runtime.py:873`) — a cumulative run-elapsed figure, not a per-call or per-tool-call duration. `self.middleware` here is a `MiddlewarePipeline` instance (`vidbyte/middleware/pipeline.py:36`) whose `clock` attribute defaults to `time.monotonic` and is constructor-injectable — the existing precedent this design reuses for `AgentSpeedTracker`'s own injectable clock.
- **Where enums/dataclasses live today:** `vidbyte/lib/dataclasses/*.py` holds ~29 files of frozen dataclasses (e.g. `sessions.py` defines `AgentUsage`/`UsageRollup` for the *session*-level usage rollup — a different, coexisting `UsageRollup` from the pricing one, re-exported from the package root at `vidbyte/__init__.py`). `vidbyte/lib/enums/*.py` holds 11 files of enums, all re-exported through `vidbyte/lib/enums/__init__.py`. Neither folder validates its dataclasses via `__post_init__` today — validation, where it exists (e.g. `SessionUsageBuilder` in `vidbyte/sessions/usage.py`), lives in a separate builder class that validates before constructing an unvalidated dataclass. This design deliberately adds `__post_init__` validation directly on the new dataclasses instead, per explicit instruction #3.
- **No `vidbyte/lib/util/` folder exists yet.** Confirmed via directory listing. This PR creates it.
- **Error hierarchy:** `vidbyte/lib/errors/base.py` defines one root `VidbyteSdkError(message: str, *, details: Mapping[str, Any] | None = None)` and ~30 subclasses, each a one-line-docstring class with no fields of its own (e.g. `SessionUsageError` / `SessionUsageValidationError` at `errors/base.py:225-230`). Raise sites pass a free-form `details` mapping. This is the pattern this design follows for `AgentSpeedError`/`AgentSpeedValidationError` — not the heavier "context-packet" error-class shape sketched generically in this repo's `agentic-engineering` skill reference, which does not match how this specific SDK's error hierarchy is actually built today. Repository convention wins.
- **Test convention:** `vidbyte-sdk/tests/` is a flat directory of `test_*.py` files (`unittest.TestCase` style), not the `tests/features/<slug>/FEATURE.md` pack structure. `tests/test_agent_pricing.py` is the closest existing analog for this feature and is the template this design follows.

---

## 4. Requirements

### Functional Requirements

1. `AgentSpeedTracker.record_call(RecordModelCallInput) -> CallSpeedRecord | None` records one model call's timing, duck-typing `provider`/`model` off the response the same way `UsageTracker.record_call` does, returning `None` and marking the tracker corrupted when the response is unusable.
2. `AgentSpeedTracker.record_tool_call(RecordToolCallInput) -> ToolCallSpeedRecord` records one tool call's timing and whether it timed out.
3. `AgentSpeedTracker.record_step(RecordStepInput) -> StepSpeedRecord` records one loop iteration's timing; implemented and unit-tested, not yet called from `runtime.py` (Non-Goal).
4. `AgentSpeedTracker.record_run_start()` / `record_run_end()` mark the run's outer wall-clock boundary, called from `BaseAgent.generate_reply()` on every exit path (success, `Exception`, `BaseException`).
5. `AgentSpeedTracker.now() -> float` returns a raw monotonic timestamp from the tracker's injectable clock, for callers to capture `dispatched_at`/`started_at` before an awaited operation. This is the one method that intentionally does **not** wrap its output in a dataclass — see §6.2 for the justification.
6. `AgentSpeedTracker.rollup() -> AgentSpeedRollup` returns the full immutable rollup, built from four private helpers, each producing one nested stats dataclass.
7. `AgentSpeedTracker.reset()` clears every ledger and the run-boundary marks; called at the top of every `generate_reply()`.
8. Every new dataclass validates its own fields in `__post_init__`, raising `AgentSpeedValidationError` (via a shared `AgentSpeedError` base) on an invalid shape — negative timestamps, `first_token_at` before `dispatched_at`, empty tool names, inconsistent percentile ordering, etc.
9. `MathHelper` (`vidbyte/lib/util/math.py`) provides `mean_or_none`, `percentile_or_none`, `max_or_none`, and `argmax_index` as `@staticmethod`s, taking plain sequences/mappings — no dependency on any speed-specific type — and returning `None` on empty input rather than raising.
10. `BaseAgent.get_speed_stats() -> AgentSpeedRollup` returns the tracker's rollup, mirroring `get_usage()`.
11. `AgentRuntime` records one `CallSpeedRecord` per successful model response and one `ToolCallSpeedRecord` per tool execution (success, error, or timeout), using the same `speed_tracker` instance `BaseAgent` owns.
12. Every new/changed public symbol is exported from `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/enums/__init__.py`, `vidbyte/agents/speed/__init__.py`, and the package root `vidbyte/__init__.py`, mirroring exactly how `UsageTracker`/`UsageRollup` are exported today.

### Non-Functional Requirements

- **Performance:** All tracking is in-memory list appends and read-time aggregation; no I/O, no network. Bounded by the number of calls/tool-calls in one run (typically single/low-double digits).
- **Reliability / fail-open:** A speed-tracking failure must never raise out of the agent loop and must never abort a run. `record_call` returns `None` + marks corrupted on unusable input, exactly like `UsageTracker.record_call`; the tool-call and run-boundary integration points use `try`/`finally` so a raised `ToolExecutionError` or any other exception still gets its timing recorded before propagating.
- **Correctness:** `rollup()` must never double-count and must be idempotent — calling it twice without new records returns the same values.
- **Observability:** `AgentSpeedRollup.recording_integrity` mirrors `UsageRecordingIntegrity`, so a caller can distinguish "no calls happened" from "calls happened but a metering bug lost data."
- **Consistency with cost tracking:** Field names, method names, and lifecycle (construct in `__init__`, reset in `generate_reply`, read via a `get_*` method) intentionally parallel `UsageTracker` so a reader who already understands cost tracking needs zero new mental model for speed tracking.

---

## 5. High-Level Design

`AgentSpeedTracker` is a new class in `vidbyte/agents/speed/tracker.py`, structurally identical in role to `UsageTracker`: a per-run mutable accumulator holding three ledgers (model calls, tool calls, loop steps) plus two run-boundary timestamps, all read back through one `rollup()` call that produces an immutable `AgentSpeedRollup`. Every dataclass it consumes or produces — the three `Record*Input` input types, the three `*SpeedRecord` stored-record types, the four `*Stats` computed-stats types, and the top-level `AgentSpeedRollup` — lives in one new file, `vidbyte/lib/dataclasses/speed.py`, each validating its own fields in `__post_init__` and raising the new `AgentSpeedValidationError`. A new `AgentSpeedRecordingIntegrity` enum lives in `vidbyte/lib/enums/speed.py`, mirroring `UsageRecordingIntegrity`'s two-value shape. All percentile/mean/max/argmax math used by `rollup()`'s four private helper methods is delegated to a new `MathHelper` static-method class at `vidbyte/lib/util/math.py`, which knows nothing about speed, calls, or agents — it operates on plain `Sequence[float]` and `Mapping[int, float]`.

`BaseAgent` owns one `AgentSpeedTracker` instance for its whole lifetime (constructed once in `__init__`, reset at the top of every `generate_reply()`, exactly mirroring `_usage_tracker`), and hands that same instance to the `AgentRuntime` it builds for a `LINEAR` run via a new `speed_tracker` constructor kwarg, exactly mirroring how `usage_tracker` is threaded through today. Inside `AgentRuntime`'s model/tool loop, one `self.speed_tracker.now()` call captures a dispatch timestamp immediately before the existing `_invoke_with_middleware()` call, and one `self.speed_tracker.record_call(...)` call sits immediately beside the existing `self.usage_tracker.record_call(raw_result)` line, reusing that same call's parsed `output_tokens` for the tokens-per-second calculation. Tool-call timing wraps the existing `_execute_tool()` method in a `try`/`finally` so timing is captured on every exit path, including a timeout. Run-boundary timing wraps `generate_reply()`'s three exit paths (success, `except Exception`, `except BaseException`) the same way `self._tracer.end_trace(...)` already does.

```
BaseAgent.__init__()
    self._speed_tracker = AgentSpeedTracker()

BaseAgent.generate_reply()
    self._speed_tracker.reset()
    self._speed_tracker.record_run_start()
    ... existing try/except/except BaseException, each branch now also calls
        self._speed_tracker.record_run_end() beside its existing end_trace() call ...

BaseAgent._runtime()  (AgentRuntimeType.LINEAR only)
    kwargs["speed_tracker"] = self._speed_tracker   # beside kwargs["usage_tracker"]

AgentRuntime.__init__(..., speed_tracker: AgentSpeedTracker | None = None)
    self.speed_tracker = speed_tracker or AgentSpeedTracker()

AgentRuntime's model/tool loop
    dispatched_at = self.speed_tracker.now()
    raw_result, ... = await self._invoke_with_middleware(...)     # unchanged
    usage_record = self.usage_tracker.record_call(raw_result)     # unchanged
    self.speed_tracker.record_call(RecordModelCallInput(
        response=raw_result, dispatched_at=dispatched_at,
        output_tokens=usage_record.usage.output_tokens if usage_record else None,
        fallback_index=fallback_index if fallback_index else None,
    ))

AgentRuntime._execute_tool()
    started_at = self.speed_tracker.now()
    timed_out = False
    try:
        return await self._run_tool_execute(...)                  # unchanged
    except ToolExecutionError as exc:
        timed_out = exc.details.get("error") == "timeout"
        raise
    finally:
        self.speed_tracker.record_tool_call(RecordToolCallInput(
            tool_name=call.tool_name, started_at=started_at, timed_out=timed_out,
        ))

BaseAgent.get_speed_stats() -> AgentSpeedRollup
    return self._speed_tracker.rollup()
```

The key design decisions: (1) speed and cost recording happen at the same two call sites so they always describe the same set of calls; (2) `AgentSpeedTracker.rollup()` never needs to touch `runtime.py`'s complex model/tool loop control flow (which has ~10 scattered `return`/`continue` exit points) because model-call and tool-call timing are captured at method boundaries that already exist as single choke points (`_invoke_with_middleware`'s single call site in the outer loop, and `_execute_tool`'s single method body) — this is exactly why per-step timing is deferred rather than force-fit into that loop in this PR; (3) every dataclass is independently validated, so a caller assembling a `RecordModelCallInput` gets an immediate, specific error rather than a rollup silently containing nonsense.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/enums/speed.py` (NEW)

**File(s):** `vidbyte-sdk/vidbyte/lib/enums/speed.py`
**Type:** New file

#### What it does
Defines `AgentSpeedRecordingIntegrity`, the speed-tracking analog of `UsageRecordingIntegrity`.

#### Interface / API
```python
class AgentSpeedRecordingIntegrity(str, Enum):
    INTACT = "intact"
    CORRUPTED = "corrupted"
```

#### Logic / Algorithm
No behavior — a two-value enum, identical shape to `UsageRecordingIntegrity` (`vidbyte/agents/pricing/records.py:28-32`).

#### Edge Cases & Error Handling
None — enums cannot be constructed invalidly.

---

### 6.2 `vidbyte/lib/dataclasses/speed.py` (NEW)

**File(s):** `vidbyte-sdk/vidbyte/lib/dataclasses/speed.py`
**Type:** New file

#### What it does
Defines every input, record, stats, and rollup dataclass `AgentSpeedTracker` uses. All are `@dataclass(frozen=True, slots=True)` with a `__post_init__` that raises `AgentSpeedValidationError` on an invalid shape, matching the numeric-validation idiom already used in `vidbyte/sessions/usage.py` (`isinstance(value, bool)` guards before range checks, since `bool` is an `int` subclass in Python).

#### Interface / API
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from vidbyte.lib.enums.speed import AgentSpeedRecordingIntegrity
from vidbyte.lib.errors import AgentSpeedValidationError


@dataclass(frozen=True, slots=True)
class RecordModelCallInput:
    """Caller-assembled input to AgentSpeedTracker.record_call."""
    response: object
    dispatched_at: float
    first_token_at: float | None = None
    output_tokens: int | None = None
    retry_count: int = 0
    fallback_index: int | None = None

    def __post_init__(self) -> None: ...  # see Logic/Algorithm


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
    retry_count: int = 0
    fallback_index: int | None = None

    def __post_init__(self) -> None: ...

    @property
    def duration_ms(self) -> float: ...
    @property
    def ttft_ms(self) -> float | None: ...
    @property
    def tokens_per_second(self) -> float | None: ...


@dataclass(frozen=True, slots=True)
class RecordToolCallInput:
    """Caller-assembled input to AgentSpeedTracker.record_tool_call."""
    tool_name: str
    started_at: float
    timed_out: bool = False

    def __post_init__(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ToolCallSpeedRecord:
    """One timed tool call, stored by AgentSpeedTracker and returned by record_tool_call."""
    call_index: int
    tool_name: str
    started_at: float
    completed_at: float
    timed_out: bool = False

    def __post_init__(self) -> None: ...

    @property
    def duration_ms(self) -> float: ...


@dataclass(frozen=True, slots=True)
class RecordStepInput:
    """Caller-assembled input to AgentSpeedTracker.record_step. Not yet wired into runtime.py."""
    started_at: float
    model_call_index: int | None = None
    tool_call_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None: ...


@dataclass(frozen=True, slots=True)
class StepSpeedRecord:
    """One timed loop iteration. Not yet produced by runtime.py in this PR."""
    iteration_index: int
    started_at: float
    completed_at: float
    model_call_index: int | None = None
    tool_call_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None: ...

    @property
    def duration_ms(self) -> float: ...


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

    def __post_init__(self) -> None: ...

    @classmethod
    def empty(cls) -> "CallSpeedStats": return cls()


@dataclass(frozen=True, slots=True)
class ToolCallSpeedStats:
    """Aggregate statistics over one run's ToolCallSpeedRecords."""
    tool_call_count: int = 0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None
    duration_ms_max: float | None = None
    slowest_tool_call_index: int | None = None

    def __post_init__(self) -> None: ...

    @classmethod
    def empty(cls) -> "ToolCallSpeedStats": return cls()


@dataclass(frozen=True, slots=True)
class StepSpeedStats:
    """Aggregate statistics over one run's StepSpeedRecords. Empty until step wiring lands."""
    step_count: int = 0
    duration_ms_mean: float | None = None
    duration_ms_p95: float | None = None

    def __post_init__(self) -> None: ...

    @classmethod
    def empty(cls) -> "StepSpeedStats": return cls()


@dataclass(frozen=True, slots=True)
class RunSpeedStats:
    """Whole-run-level derived statistics: total duration and overhead breakdowns."""
    total_duration_ms: float | None = None
    cold_start_overhead_ms: float | None = None
    framework_overhead_ms: float | None = None
    parallelism_efficiency: float | None = None

    def __post_init__(self) -> None: ...

    @classmethod
    def empty(cls) -> "RunSpeedStats": return cls()


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
    def empty(cls) -> "AgentSpeedRollup": return cls()
```

#### Logic / Algorithm — validation rules

A shared set of private module-level guards (`_require_non_negative_float`, `_require_non_negative_int`, `_require_non_empty_str`, `_require_ordered`) implements the repeated numeric checks, called from each `__post_init__`:

- `RecordModelCallInput` / `CallSpeedRecord`: `response`/timestamps must not be `None`; `dispatched_at`, `first_token_at`, `output_tokens`, `retry_count`, `fallback_index` must be non-negative when present and never `bool` (mirrors the `isinstance(value, bool)` guard pattern in `vidbyte/sessions/usage.py:97,111`); on `CallSpeedRecord` additionally, `completed_at >= dispatched_at`, and `first_token_at` (if set) must fall within `[dispatched_at, completed_at]`; `provider`/`model` must be non-empty strings; `call_index >= 1`.
- `RecordToolCallInput` / `ToolCallSpeedRecord`: `tool_name` non-empty after `.strip()`; `started_at`/`completed_at` non-negative; `completed_at >= started_at`; `call_index >= 1`.
- `RecordStepInput` / `StepSpeedRecord`: `started_at` non-negative; `model_call_index` (if set) `>= 1`; every entry in `tool_call_indices` `>= 1` with no duplicates; on the record, `completed_at >= started_at`, `iteration_index >= 1`.
- The four `*Stats` dataclasses and `AgentSpeedRollup`: every `*_count` field `>= 0`; every populated `*_ms` field `>= 0`; where a mean/p50/p95/p99 triple is all populated, `p50 <= p95 <= p99` (raises `AgentSpeedValidationError` otherwise — a real ordering violation means the percentile math itself is broken, and this is the cheapest place to catch that).

#### Edge Cases & Error Handling
- Constructing any of these dataclasses with a negative timestamp, an empty tool name, `first_token_at` before `dispatched_at`, or out-of-order percentiles raises `AgentSpeedValidationError` immediately at construction — never at read time.
- `response: object` on `RecordModelCallInput` is checked only for `is not None`; it is intentionally duck-typed (matching `UsageTracker.record_call`'s own `getattr(response, "provider", None)` pattern) because the SDK supports many provider response shapes and must not import any of them into `vidbyte/lib/dataclasses`.

---

### 6.3 `vidbyte/lib/util/math.py` (NEW)

**File(s):** `vidbyte-sdk/vidbyte/lib/util/math.py`, `vidbyte-sdk/vidbyte/lib/util/__init__.py`
**Type:** New file, new package

#### What it does
Provides general-purpose statistics as `@staticmethod`s on one `MathHelper` class. Knows nothing about agents, calls, or speed — every input is a plain `Sequence[float]` or `Mapping[int, float]`.

#### Interface / API
```python
from __future__ import annotations
from collections.abc import Mapping, Sequence
import statistics


class MathHelper:
    """Static-method home for general numeric aggregation used across the SDK."""

    @staticmethod
    def mean_or_none(values: Sequence[float]) -> float | None:
        """Returns the arithmetic mean, or None when values is empty."""
        return statistics.mean(values) if values else None

    @staticmethod
    def percentile_or_none(values: Sequence[float], fraction: float) -> float | None:
        """Returns the nearest-rank percentile at `fraction` in [0, 1], or None when values is empty."""
        if not values:
            return None
        if not (0.0 <= fraction <= 1.0):
            raise ValueError(f"fraction must be within [0, 1], got {fraction}.")
        ordered = sorted(values)
        index = int(len(ordered) * fraction)
        return ordered[min(index, len(ordered) - 1)]

    @staticmethod
    def max_or_none(values: Sequence[float]) -> float | None:
        """Returns the maximum value, or None when values is empty."""
        return max(values) if values else None

    @staticmethod
    def argmax_index(scored: Mapping[int, float]) -> int | None:
        """Returns the key with the largest value in `scored`, or None when scored is empty."""
        return max(scored, key=scored.get) if scored else None
```

#### Logic / Algorithm
`percentile_or_none` uses the exact nearest-rank method already established in `vidbyte/evals/types.py:87-93` (`EvalSuiteResult.p95_latency_ms`) — `sorted()` then `int(len * fraction)` clamped to the last index — so "p95" means the same thing everywhere in the SDK rather than introducing a second percentile convention (e.g. linear interpolation) alongside the existing one.

#### Edge Cases & Error Handling
- Empty input returns `None` for all four functions except `argmax_index`, which also returns `None` on empty input (not a raised error) — this graceful-degradation-to-`None` idiom matches `UsageRollup.cost_usd`'s existing `None`-when-unknown convention rather than introducing exceptions for a state (no data yet) that is normal, not exceptional.
- `percentile_or_none` raises a plain `ValueError` (not an SDK error class) for an out-of-range `fraction`, because this is a programmer error at the call site inside the SDK itself, not a runtime condition an agent-facing caller can hit — every caller in this PR passes a literal `0.50`/`0.95`/`0.99`.
- `MathHelper` deliberately does **not** validate its inputs via a wrapping dataclass (unlike `AgentSpeedTracker`'s methods) — its inputs are bare numeric sequences with no cross-field relationships to validate, and it has no callers outside this SDK's own internals.

---

### 6.4 `vidbyte/lib/errors/base.py` (MODIFY)

**File(s):** `vidbyte-sdk/vidbyte/lib/errors/base.py`, `vidbyte-sdk/vidbyte/lib/errors/__init__.py`
**Type:** Modified

#### What it does
Adds two error classes, following the file's existing one-line-docstring convention exactly:

```python
class AgentSpeedError(VidbyteSdkError):
    """Base class for agent speed-tracking failures."""


class AgentSpeedValidationError(AgentSpeedError):
    """Raised when a speed-tracking dataclass receives an invalid shape."""
```

Both are exported from `errors/__init__.py` alongside `SessionUsageError`/`SessionUsageValidationError`.

#### Edge Cases & Error Handling
N/A — these are the error types other files raise; see §6.2 for every raise site's `details` payload (field name, offending value, and — where applicable — the other field it conflicts with, e.g. `{"field": "first_token_at", "first_token_at": ..., "dispatched_at": ...}`).

---

### 6.5 `vidbyte/agents/speed/tracker.py` (NEW)

**File(s):** `vidbyte-sdk/vidbyte/agents/speed/tracker.py`, `vidbyte-sdk/vidbyte/agents/speed/__init__.py`
**Type:** New file, new package

#### What it does
`AgentSpeedTracker`: the mutable per-run accumulator, structurally mirroring `UsageTracker`.

#### Interface / API
```python
from __future__ import annotations
import time
from collections.abc import Callable

from vidbyte.lib.dataclasses.speed import (
    AgentSpeedRollup, CallSpeedRecord, CallSpeedStats, RecordModelCallInput,
    RecordStepInput, RecordToolCallInput, RunSpeedStats, StepSpeedRecord,
    StepSpeedStats, ToolCallSpeedRecord, ToolCallSpeedStats,
)
from vidbyte.lib.enums.speed import AgentSpeedRecordingIntegrity
from vidbyte.lib.util.math import MathHelper


class AgentSpeedTracker:
    """Accumulates timed model-call, tool-call, and run-boundary records for one agent run."""

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None: ...
    def now(self) -> float: ...
    def record_run_start(self) -> None: ...
    def record_run_end(self) -> None: ...
    def record_call(self, call_input: RecordModelCallInput) -> CallSpeedRecord | None: ...
    def record_tool_call(self, call_input: RecordToolCallInput) -> ToolCallSpeedRecord: ...
    def record_step(self, step_input: RecordStepInput) -> StepSpeedRecord: ...
    def rollup(self) -> AgentSpeedRollup: ...
    def reset(self) -> None: ...
    def mark_recording_corrupted(self) -> None: ...

    @property
    def recording_corrupted(self) -> bool: ...
    @property
    def calls(self) -> tuple[CallSpeedRecord, ...]: ...
    @property
    def tool_calls(self) -> tuple[ToolCallSpeedRecord, ...]: ...
    @property
    def steps(self) -> tuple[StepSpeedRecord, ...]: ...

    # --- rollup() is composed from these, per explicit instruction to split it ---
    def _build_call_stats(self, calls: tuple[CallSpeedRecord, ...]) -> CallSpeedStats: ...
    def _build_tool_call_stats(self, tool_calls: tuple[ToolCallSpeedRecord, ...]) -> ToolCallSpeedStats: ...
    def _build_step_stats(self, steps: tuple[StepSpeedRecord, ...]) -> StepSpeedStats: ...
    def _build_run_stats(
        self,
        calls: tuple[CallSpeedRecord, ...],
        tool_calls: tuple[ToolCallSpeedRecord, ...],
    ) -> RunSpeedStats: ...
```

#### Logic / Algorithm

1. `now()` returns `self._clock()` — a bare `float`, not a dataclass. This is a deliberate, documented exception to "every input and output is a dataclass": `now()` takes no input, and its output is a primitive clock reading with no internal structure to validate, exactly mirroring `MiddlewarePipeline.clock()` (`vidbyte/middleware/pipeline.py:48`), which returns a bare `float` for the same reason. Wrapping a lone timestamp in a one-field dataclass would validate nothing (a raw monotonic float from `time.monotonic()` cannot be "invalid" in any way `__post_init__` could check) and would only add ceremony at every call site. The three `record_*` methods, whose inputs genuinely have multiple related fields with cross-field validation (e.g. `first_token_at >= dispatched_at`), are where the dataclass-wrapping requirement pays for itself.
2. `record_run_start()`/`record_run_end()` store `self._run_started_at`/`self._run_completed_at` (private floats, read only by `_build_run_stats`) — not returned to the caller, since `BaseAgent` has no use for the raw value.
3. `record_call(call_input)` duck-types `provider = getattr(call_input.response, "provider", None)` / `model = getattr(call_input.response, "model", None)`; if either is missing, calls `self.mark_recording_corrupted()` and returns `None` — identical failure handling to `UsageTracker.record_call`. Otherwise constructs and appends a `CallSpeedRecord` with `completed_at=self.now()`.
4. `record_tool_call(call_input)` always succeeds (tool name and timestamps are already validated by `RecordToolCallInput`); appends and returns a `ToolCallSpeedRecord`.
5. `record_step(step_input)` always succeeds; appends and returns a `StepSpeedRecord`. (Not called by `runtime.py` yet — Non-Goal.)
6. `rollup()` is a 6-line orchestrator: snapshot the three ledgers into tuples, call each `_build_*_stats` helper, assemble `AgentSpeedRollup`. No aggregation math lives in `rollup()` itself.
7. `_build_call_stats(calls)`: builds parallel lists of `duration_ms`/`ttft_ms`(filtered `None`)/`tokens_per_second`(filtered `None`), calls `MathHelper.mean_or_none`/`percentile_or_none`/`max_or_none` on each, and `MathHelper.argmax_index({c.call_index: c.duration_ms for c in calls})` for `slowest_call_index`. Returns `CallSpeedStats.empty()` when `calls` is empty.
8. `_build_tool_call_stats(tool_calls)`: same pattern, narrower field set.
9. `_build_step_stats(steps)`: same pattern; always `.empty()` today since nothing populates `steps` yet.
10. `_build_run_stats(calls, tool_calls)`: `total_duration_ms` from `self._run_started_at`/`self._run_completed_at` (both must be set — returns `.empty()` otherwise); `cold_start_overhead_ms = calls[0].duration_ms - MathHelper.mean_or_none([c.duration_ms for c in calls[1:]])` when `len(calls) > 1`, else `None`; `framework_overhead_ms = total_duration_ms - sum(call durations) - sum(tool durations)`; `parallelism_efficiency = sum(tool durations, in seconds) / actual tool-phase wall-clock` when `len(tool_calls) > 1`, else `None`.
11. `reset()` clears all three ledgers, both run-boundary timestamps, and `_recording_corrupted`.

#### Edge Cases & Error Handling
- `record_call` on an unusable response: returns `None`, marks corrupted, does not raise — the agent run must continue.
- `rollup()` with zero calls/tool-calls/steps: every `*Stats` field is `.empty()`; no division by zero, no `MathHelper` call ever sees an empty sequence do anything but return `None`.
- `rollup()` called before `record_run_end()` (e.g. mid-run introspection): `RunSpeedStats.total_duration_ms` is `None` — the caller is reading a live, incomplete rollup, exactly as `UsageTracker.rollup()` supports live reads mid-run today.
- A caller calling `record_call`/`record_tool_call`/`record_step` with an already-invalid dataclass never reaches the tracker — the dataclass's own `__post_init__` raised before construction completed.

---

### 6.6 `vidbyte/agents/base.py` (MODIFY)

**File(s):** `vidbyte-sdk/vidbyte/agents/base.py`
**Type:** Modified

#### What it does / Logic
- `__init__` (near `base.py:224`): add `self._speed_tracker = AgentSpeedTracker()` beside `self._usage_tracker = UsageTracker()`.
- `generate_reply` (near `base.py:595`): add `self._speed_tracker.reset()` and `self._speed_tracker.record_run_start()` beside `self._usage_tracker.reset()`.
- `generate_reply`'s three exit paths — success (`base.py:630`), `except Exception` (`base.py:633`), `except BaseException` (`base.py:643`) — each add `self._speed_tracker.record_run_end()` immediately beside the existing `self._tracer.end_trace(...)` call in that branch, so the run boundary closes on every exit, including a cancellation.
- New method, beside `get_usage()`/`get_cost_usd()` (`base.py:720-726`):
  ```python
  def get_speed_stats(self) -> AgentSpeedRollup:
      """Return the live or final speed rollup for the current or most recent run."""
      return self._speed_tracker.rollup()
  ```
- `_runtime()` (near `base.py:978`), inside the existing `if self.runtime_type is AgentRuntimeType.LINEAR:` block: add `kwargs["speed_tracker"] = self._speed_tracker` beside `kwargs["usage_tracker"] = self._usage_tracker`.

#### Edge Cases & Error Handling
- If `generate_reply` raises before `record_run_start()` runs (impossible in the current control flow — `reset()`/`record_run_start()` are the first two lines after entering the `try`), `record_run_end()` in the exception handlers would close a run that never started; `AgentSpeedTracker.record_run_end()` is written to tolerate this (sets `_run_completed_at` regardless — `_build_run_stats` only computes `total_duration_ms` when *both* marks are set, so a missing start still degrades to `None` rather than a negative duration).

---

### 6.7 `vidbyte/agents/runtime.py` (MODIFY)

**File(s):** `vidbyte-sdk/vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does / Logic
- `AgentRuntime.__init__` (near `runtime.py:186`): add `speed_tracker: AgentSpeedTracker | None = None` to the signature; `self.speed_tracker = speed_tracker or AgentSpeedTracker()`, beside `self.usage_tracker = usage_tracker or UsageTracker()`.
- Model-call site (outer loop, near `runtime.py:360-412`): capture `call_dispatched_at = self.speed_tracker.now()` immediately before the existing `await self._invoke_with_middleware(...)` call; immediately after the existing `usage_record = self.usage_tracker.record_call(raw_result)` line, add:
  ```python
  self.speed_tracker.record_call(RecordModelCallInput(
      response=raw_result,
      dispatched_at=call_dispatched_at,
      output_tokens=usage_record.usage.output_tokens if usage_record is not None else None,
      fallback_index=fallback_index if fallback_index else None,
  ))
  ```
  `fallback_index` is the outer loop's own existing local (assigned at `runtime.py:391` inside the fallback-transition branch); the implementer must confirm its initial value/scope by reading the full method top before wiring this line, per the audit note in §3 — this design intentionally does not assert an unverified line number for that initialization.
- Tool-call site (`_execute_tool`, `runtime.py:1091-1101`): wrap in `try`/`finally`:
  ```python
  async def _execute_tool(self, tool: object, call: ToolCall, *, tool_is_internal: bool = False) -> ToolResult:
      # Executes the tool, optionally under tool_timeout_seconds, raising ToolExecutionError on failure.
      started_at = self.speed_tracker.now()
      timed_out = False
      try:
          return await self._run_tool_execute(tool, call, tool_is_internal=tool_is_internal)
      except ToolExecutionError as exc:
          timed_out = exc.details.get("error") == "timeout"
          raise
      except Exception as exc:
          raise ToolExecutionError(
              f"Tool execution failed: {exc}",
              details={"tool_name": call.tool_name, "error_type": type(exc).__name__},
          ) from exc
      finally:
          self.speed_tracker.record_tool_call(RecordToolCallInput(
              tool_name=call.tool_name, started_at=started_at, timed_out=timed_out,
          ))
  ```
  This reuses the timeout marker `_run_tool_execute` already sets at `runtime.py:1114` (`details={"tool_name": ..., "error": "timeout", ...}`) — no new timeout-detection logic is introduced.

#### Edge Cases & Error Handling
- A tool call that raises a non-`ToolExecutionError` exception still gets timed (the `finally` runs regardless of which `except` branch — or neither — fired).
- A model call inside `_invoke_with_middleware`'s own internal retry loop (`on_model_error`) is measured as one single, longer `duration_ms` by the outer loop's `record_call` — see Non-Goals for why retry time is folded in rather than separately attributed in this PR.
- `AgentRuntime` instances constructed directly by algorithm code (`vidbyte/agents/algorithms/independent_critic.py:110`, `prosecutor_defender_judge.py`) that do **not** pass `speed_tracker=` simply get a private, throwaway `AgentSpeedTracker()` (the `speed_tracker or AgentSpeedTracker()` default) — timing still gets recorded, just not surfaced anywhere, exactly matching how those same call sites already behave for `usage_tracker` today.

---

### 6.8 Package exports (MODIFY)

**File(s):** `vidbyte-sdk/vidbyte/lib/dataclasses/__init__.py`, `vidbyte-sdk/vidbyte/lib/enums/__init__.py`, `vidbyte-sdk/vidbyte/agents/speed/__init__.py` (NEW), `vidbyte-sdk/vidbyte/__init__.py`
**Type:** Modified / one new file

#### What it does
- `lib/dataclasses/__init__.py`: import and add to `__all__` every dataclass from §6.2.
- `lib/enums/__init__.py`: import and add `AgentSpeedRecordingIntegrity` to `__all__`.
- `agents/speed/__init__.py` (new, mirrors `agents/pricing/__init__.py`): re-exports `AgentSpeedTracker` from `.tracker`.
- Root `vidbyte/__init__.py`: add `AgentSpeedTracker` (from `vidbyte.agents.speed`) and `AgentSpeedRollup` (from `vidbyte.lib.dataclasses.speed`) to the existing import block and `__all__`, beside the existing `UsageTracker`/`UsageRollup` entries (`vidbyte/__init__.py:86-87`, `587-588`).

#### Edge Cases & Error Handling
N/A — pure re-export wiring.

---

## 7. Data Model Changes

N/A — no database, no persisted schema. Every new type in this PR is an in-memory dataclass that exists only for the duration of one agent run (or one test). Nothing here is serialized to a `Checkpoint`, a `Session`, or any store.

---

## 8. API Changes

N/A — this is an SDK library change, not an HTTP API. The "public API" surface changed is the Python package surface, fully enumerated in §6.8 and §9.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte-sdk/vidbyte/lib/enums/speed.py` | `AgentSpeedRecordingIntegrity` enum |
| CREATE | `vidbyte-sdk/vidbyte/lib/dataclasses/speed.py` | All speed input/record/stats/rollup dataclasses, validated |
| CREATE | `vidbyte-sdk/vidbyte/lib/util/__init__.py` | New `lib/util` package |
| CREATE | `vidbyte-sdk/vidbyte/lib/util/math.py` | `MathHelper` static-method class |
| CREATE | `vidbyte-sdk/vidbyte/agents/speed/__init__.py` | Package export of `AgentSpeedTracker` |
| CREATE | `vidbyte-sdk/vidbyte/agents/speed/tracker.py` | `AgentSpeedTracker` implementation |
| MODIFY | `vidbyte-sdk/vidbyte/lib/errors/base.py` | Add `AgentSpeedError`, `AgentSpeedValidationError` |
| MODIFY | `vidbyte-sdk/vidbyte/lib/errors/__init__.py` | Export the two new error classes |
| MODIFY | `vidbyte-sdk/vidbyte/lib/dataclasses/__init__.py` | Export new speed dataclasses |
| MODIFY | `vidbyte-sdk/vidbyte/lib/enums/__init__.py` | Export `AgentSpeedRecordingIntegrity` |
| MODIFY | `vidbyte-sdk/vidbyte/agents/base.py` | Own `_speed_tracker`; reset/start/end on every exit path; `get_speed_stats()`; thread into `_runtime()` |
| MODIFY | `vidbyte-sdk/vidbyte/agents/runtime.py` | Accept `speed_tracker`; time model calls and tool calls |
| MODIFY | `vidbyte-sdk/vidbyte/__init__.py` | Export `AgentSpeedTracker`, `AgentSpeedRollup` at package root |
| CREATE | `vidbyte-sdk/tests/test_agent_speed.py` | Feature tests for the tracker, dataclasses, and `MathHelper` |
| MODIFY | `vidbyte-sdk/tests/test_agent_runtime.py` | Integration tests for the `runtime.py` wiring |
| CREATE | `vidbyte-sdk/scripts/test-agent-speed-tracking.py` | Phase-5 standalone verification script |

No files are deleted.

---

## 10. Testing Plan

Per the observed repository convention (flat `unittest.TestCase` files, not `tests/features/<slug>/` packs — see §3), tests live in `tests/test_agent_speed.py` (tracker/dataclass/MathHelper unit level) and additions to `tests/test_agent_runtime.py` (integration with the real loop), following `tests/test_agent_pricing.py`'s shape.

### Unit Tests (`tests/test_agent_speed.py`)

- `describe('MathHelperTests')` -> `test_mean_or_none_returns_none_for_empty_sequence` — [Edge Case]
- `-> test_mean_or_none_returns_mean_for_populated_sequence` — [Silent Failure] (catches a wrong-axis or wrong-divisor mean)
- `-> test_percentile_or_none_matches_eval_suite_result_p95_algorithm` — [Hidden Assumption] (asserts the exact nearest-rank formula matches `EvalSuiteResult.p95_latency_ms`'s existing algorithm on the same input, not just "a" percentile)
- `-> test_percentile_or_none_rejects_fraction_outside_zero_one` — [Hidden Failure] (silently clamping instead of raising would hide a caller bug)
- `-> test_percentile_or_none_returns_none_for_empty_sequence` — [Edge Case]
- `-> test_max_or_none_returns_none_for_empty_sequence` — [Edge Case]
- `-> test_argmax_index_returns_key_of_largest_value` — [Silent Failure] (catches an off-by-one or reversed comparison)
- `-> test_argmax_index_returns_none_for_empty_mapping` — [Edge Case]
- `-> test_argmax_index_breaks_ties_deterministically` — [Hidden Failure] (two equal max values must not make the result flap across runs)

- `describe('RecordModelCallInputValidationTests')` -> `test_negative_dispatched_at_raises_agent_speed_validation_error` — [Hidden Assumption]
- `-> test_first_token_at_before_dispatched_at_raises` — [Silent Failure] (a caller passing swapped timestamps must not silently produce a negative TTFT)
- `-> test_none_response_raises` — [Hidden Assumption]
- `-> test_negative_output_tokens_raises` — [Edge Case]
- `-> test_bool_retry_count_raises` — [Hidden Assumption] (bool is an int subclass in Python; must not silently accept `True` as `1`)

- `describe('CallSpeedRecordTests')` -> `test_duration_ms_is_completed_minus_dispatched_in_milliseconds` — [Silent Failure]
- `-> test_ttft_ms_is_none_when_first_token_at_is_none` — [Edge Case]
- `-> test_tokens_per_second_is_none_when_output_tokens_is_none` — [Edge Case]
- `-> test_tokens_per_second_uses_post_ttft_window_not_full_duration` — [Silent Failure] (catches a regression that divides by total duration instead of the generation-only window)
- `-> test_completed_at_before_dispatched_at_raises` — [Hidden Assumption]

- `describe('ToolCallSpeedRecordTests')` -> `test_empty_tool_name_raises` — [Edge Case]
- `-> test_whitespace_only_tool_name_raises` — [Edge Case]

- `describe('AgentSpeedTrackerRecordCallTests')` -> `test_record_call_returns_none_and_marks_corrupted_when_response_has_no_provider` — [Silent Failure] (mirrors `UsageTracker.record_call`'s exact failure contract; a test asserting only `is None` without checking `recording_corrupted` would miss a regression that silently drops data without flagging it)
- `-> test_record_call_assigns_sequential_call_index_starting_at_one` — [Hidden Assumption]
- `-> test_record_call_never_raises_for_a_malformed_but_non_none_response` — [Hidden Failure] (a response object with a `provider` attribute that raises on `str()` must not crash the agent loop)

- `describe('AgentSpeedTrackerRecordToolCallTests')` -> `test_record_tool_call_marks_timed_out_true_when_flagged` — [Silent Failure]
- `-> test_record_tool_call_assigns_sequential_call_index_starting_at_one` — [Hidden Assumption]

- `describe('AgentSpeedTrackerRollupTests')` -> `test_rollup_with_zero_calls_returns_empty_stats_not_error` — [Edge Case]
- `-> test_rollup_is_idempotent_when_called_twice_without_new_records` — [Silent Failure] (catches accidental mutation-on-read)
- `-> test_rollup_call_duration_p95_matches_manually_computed_value` — [Silent Failure]
- `-> test_rollup_slowest_call_index_points_at_the_actual_slowest_call` — [Silent Failure] (catches an argmax wired to the wrong field)
- `-> test_rollup_cold_start_overhead_is_none_with_only_one_call` — [Edge Case]
- `-> test_rollup_cold_start_overhead_positive_when_first_call_is_slower` — [Silent Failure]
- `-> test_rollup_framework_overhead_accounts_for_total_minus_call_and_tool_time` — [Silent Failure]
- `-> test_rollup_parallelism_efficiency_reflects_overlapping_tool_calls` — [Silent Failure] (two tool calls that ran concurrently must report efficiency > 1, not exactly 1)
- `-> test_rollup_recording_integrity_is_corrupted_after_an_unusable_call` — [Silent Failure]
- `-> test_reset_clears_every_ledger_and_run_boundary` — [Hidden Assumption] (mirrors the real `generate_reply` behavior of resetting between runs — a stale tracker would silently blend two runs' stats)

### Integration Tests (`tests/test_agent_runtime.py` additions)

- What flows must be tested end-to-end: a real (mocked-provider) `BaseAgent.generate_reply()` call through to `get_speed_stats()`, verifying at least one `CallSpeedRecord` and, when a tool is used, at least one `ToolCallSpeedRecord` appear with plausible non-negative durations.
- External dependencies mocked: the model provider response (as `test_agent_pricing.py` and `test_agent_runtime.py` already do); the tool implementation itself is real (in-process), only its I/O is stubbed.
- Silent failure paths in the integrated flow: (a) `speed_tracker` never getting threaded from `BaseAgent` into the `AgentRuntime` it builds — would silently produce two disconnected trackers, so `get_speed_stats()` would report zero calls even though calls happened; a test must assert `agent.get_speed_stats().call_stats.call_count >= 1` after a real run, not just that the method doesn't raise. (b) A tool timeout that raises `ToolExecutionError` but is never recorded — a test must force a timeout and assert exactly one `ToolCallSpeedRecord` with `timed_out=True` exists afterward.
- Hidden assumptions integration surfaces that unit tests cannot catch: that `usage_record.usage.output_tokens` is actually available at the exact point `speed_tracker.record_call` is invoked (a unit test can fabricate this; only a real loop run proves the ordering is correct); that `generate_reply`'s three exit branches (success/`Exception`/`BaseException`) all actually reach `record_run_end()` — a test must force each of the three paths (success, a raised `Exception` from the mocked provider, and a `CancelledError`) and assert `get_speed_stats().run_stats.total_duration_ms is not None` after each one, including the two failure paths.

### Manual / QA Test Cases

1. Given a `BaseAgent` configured with a real (non-mocked) Anthropic/OpenAI provider and no tools, when `generate_reply()` is called once, then `get_speed_stats().call_stats.call_count == 1` and `duration_ms_mean` is a plausible positive number of milliseconds (not zero, not absurdly large). — [Edge Case]
2. Given the same agent run twice in sequence, when `get_speed_stats()` is read after the second run, then it reflects only the second run's calls, not both runs combined. — [Silent Failure]
3. Given an agent with a tool configured to sleep past its `tool_timeout_seconds`, when `generate_reply()` runs, then `get_speed_stats().tool_call_stats` shows one record with `timed_out=True` and the run itself still completes (does not crash) after the surrounding `AgentExecutionError`/retry policy handles the timeout. — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `statistics` (stdlib) | 3.11+ (per `pyproject.toml` `requires-python`) | `MathHelper.mean_or_none` | None — stdlib, already used elsewhere in the SDK (`vidbyte/evals/types.py`) |
| Python `time` (stdlib) | 3.11+ | Default clock (`time.monotonic`) | None — same default `MiddlewarePipeline.clock` already uses |

No new third-party packages, no new network calls, no new environment variables.

---

## 12. Rollout & Deployment

- No feature flag: this is additive, in-process instrumentation with no behavior change to existing agent output. `get_speed_stats()` is a new method; nothing existing calls it, so nothing existing changes behavior.
- Not a breaking change: `AgentRuntime.__init__`'s new `speed_tracker` parameter is optional and keyword-only-compatible with existing positional/keyword call sites (defaults to `None` → a fresh tracker), matching how `usage_tracker` was added without breaking `reflexion.py`/`multi_provider_agentic_grader.py`'s direct calls to `_invoke_with_middleware` (whose signature this PR does not touch at all).
- Deployment order: single package (`vidbyte-sdk`), single PR, no coordinated multi-service deploy.
- Rollback: revert the PR. No persisted data, no schema, no migration to reverse.

---

## 13. Open Questions

- [ ] Should `fallback_index`'s exact source variable/initialization in `runtime.py`'s outer loop be double-checked against the full method body before wiring §6.7's snippet, since this design doc audited it from a partial read? (Flagged explicitly in §6.7; resolve during implementation by reading the full method top before editing.)
- [ ] Should step-level timing (Non-Goal #1) be a fast-follow PR that wraps the *entire* outer while-loop body in `try`/`finally` (the only correctness-preserving way to catch every one of its ~10 `continue`/`return` exit points without touching each individually), or should it wait until/unless a customer-facing report actually needs per-step granularity? No action needed now; recorded so it isn't rediscovered as a surprise later.
- [ ] Should `retry_count`'s real accounting (Non-Goal #3) require changing `_invoke_with_middleware`'s return contract, given it's called directly by `reflexion.py` and `multi_provider_agentic_grader.py`? If so, that is cross-cutting enough to warrant its own design doc rather than folding into this one.

---

## 14. Alternatives Considered

### Alternative 1: Co-locate dataclasses next to the tracker (mirror `agents/pricing/records.py` exactly)
- What: Define `CallSpeedRecord`/`AgentSpeedRollup`/etc. inside `vidbyte/agents/speed/records.py`, exactly matching where `UsageRecord`/`UsageRollup` live today.
- Why rejected: Explicit user instruction #1 requires every enum/dataclass to live under `vidbyte/lib/`. This is also arguably a correction of an existing inconsistency in the codebase (there are already two differently-shaped `UsageRollup` classes — one in `lib/dataclasses/sessions.py`, one in `agents/pricing/records.py` — a duplication this design doesn't fix, but also doesn't repeat).

### Alternative 2: Inline percentile/mean/argmax math directly in `AgentSpeedTracker`'s private helpers
- What: Skip `MathHelper` entirely; compute `statistics.mean(...)` and the percentile formula inline inside `_build_call_stats` etc., as the original conversational sketch did.
- Why rejected: Explicit user instruction #2. Centralizing in `MathHelper` also means the percentile formula is defined exactly once for the whole SDK, so it can be reused by any future SDK code (e.g. a future quality-metrics tracker) without copy-pasting the nearest-rank formula a third time.

### Alternative 3: Wire full per-step timing into `runtime.py` in this PR by wrapping the entire outer while-loop body in `try`/`finally`
- What: Restructure the ~230-line outer model/tool loop body (`runtime.py`, roughly lines 300-536) inside one `try`/`finally` so every one of its ~10 scattered `continue`/`return` exit points automatically triggers step-close timing, with zero per-branch edits.
- Why rejected (for this PR): This is the only correctness-preserving way to do it without touching every individual exit branch, but it is a large, high-risk structural diff to a file whose own header explicitly warns "Do not... put private service logic... in this runtime" beyond its documented contract, and whose `_invoke_with_middleware` method is called directly by two other files. `framework_overhead_ms`/`cold_start_overhead_ms`/`parallelism_efficiency` — the highest-value derived speed metrics — do not actually require step records to compute (they only need `calls` and `tool_calls`), so deferring step-level wiring costs only `StepSpeedStats` staying empty in v1, not the metrics that matter most. Revisit as a focused fast-follow PR once the base tracker has shipped and been used.

### Alternative 4: Attach speed timing via a `WalletModelUsageMiddleware`-style middleware instead of direct calls in `runtime.py`
- What: Mirror the backend's `WalletModelUsageMiddleware` pattern (attached to `agent.middleware` after `build_agent`) instead of adding direct `self.speed_tracker.record_call(...)` calls inside `AgentRuntime`.
- Why rejected: `WalletModelUsageMiddleware` is a **backend** (`vidbyte/backend/services/harnesses/research/`) pattern layered on top of the SDK's own internal, non-middleware `usage_tracker.record_call(raw_result)` call, which lives directly inside `AgentRuntime` (`runtime.py:412`) — not as middleware. Cost tracking itself is not middleware-based at the SDK level, so making speed tracking middleware-based would put the two trackers on inconsistent architectures for no benefit, and would require a `before_model_call`/`after_model_response` middleware hook to carry the dispatch timestamp across the awaited call, which the existing `MiddlewareContext` shape doesn't currently support without its own change.
