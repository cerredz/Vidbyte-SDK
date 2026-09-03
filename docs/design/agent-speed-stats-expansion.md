# Design Doc: Agent Speed Stats Expansion

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-02
**Last Updated:** 2026-09-02

---

## 1. Overview

This change expands the speed-only telemetry introduced by PR #394. The SDK will retain the existing per-call and per-tool timing records while adding failure and retry timing, stream first-chunk and inter-chunk timing, weighted token throughput, provider/model and tool-name breakdowns, complete step timing, tool timeout/error rates, fallback overhead, concurrency-aware run breakdowns, and bounded warm/cold run history. The data remains in-memory and agent-owned, so `BaseAgent.get_speed_stats()` continues to return the current run and a new `get_speed_history()` exposes completed-run warmup trends without adding cost, quality, persistence, or service-specific reporting.

---

## 2. Goals & Non-Goals

### Goals

- Record every model attempt that reaches the runner, including failed and cancelled attempts, without changing agent behavior.
- Record complete tool-call lifecycle timing and outcome, including timeouts, execution failures, permission failures, and unknown-tool failures that reach the runtime tool boundary.
- Provide stream timing hooks for existing `StreamingTextModelRunner` iterators so callers can measure time to first chunk and inter-chunk pauses without making the lower-level runner depend on `AgentSpeedTracker`.
- Add weighted output-token throughput and prompt-token throughput when provider usage and timing are available. Token counts are supporting denominators for speed calculations, not a new cost or usage tracker.
- Add p90, minimum, standard deviation, weighted rates, retry/fallback counts, and failure rates to model, tool, step, and stream rollups.
- Add deterministic per-provider/model and per-tool-name speed rollups.
- Wire step timing through every direct linear-runtime exit path by opening and closing a run-local step scope at loop boundaries.
- Add time-to-first-tool and time-to-result-ready milestones.
- Replace residual-only framework overhead interpretation with active-work, overlap, and concurrency statistics that remain meaningful when tool intervals overlap.
- Preserve a bounded history of completed runs so callers can compare the first cold run with later warm runs and inspect rolling recent-run latency.
- Keep all new speed tracking fail-open: telemetry errors must not abort the agent run or mask the original model/tool exception.

### Non-Goals

- No cost, price, billing, quality, evaluation, or correctness metrics.
- No change to provider billing parsers or `UsageTracker`; existing usage records are read only to obtain token denominators.
- No automatic streaming mode is added to `BaseAgent.generate_reply()`. The existing agent loop consumes complete runner responses; stream timing is exposed through `AgentSpeedTracker.measure_stream()` for the existing streaming runner API.
- No provider-specific streaming response reconstruction, tokenizer integration, or claim that text chunks are individual tokens. The stream metric is explicitly chunk-based unless a caller separately supplies token counts to a completed model-call record.
- No cross-process persistence, database schema, dashboard, histogram service, or harness-level aggregation.
- No changes to actor-model and other non-linear runtime implementations; they retain the existing PR #394 scope unless they already route through the linear `AgentRuntime` speed tracker.
- No new feature test files. Existing tests, lint, package checks, and the canonical CI gate remain required and will be run after implementation.

---

## 3. Background & Context

PR #394 added `AgentSpeedTracker` to the SDK. It records successful model-call duration, optional TTFT fields, average output tokens per second, tool-call duration and timeout state, run duration, cold-start overhead, framework overhead, and tool parallelism. `BaseAgent` owns the tracker, resets it at the start of each run, and exposes `get_speed_stats()`; the linear `AgentRuntime` shares that instance.

The current tracker has several gaps for a production speed report. Model failures are not recorded because the current model record is created only after a successful response. Tool timing begins inside `_execute_tool()`, so permission, lookup, validation, and output-schema failures are absent from tool latency statistics. The tracker has fields for step records and TTFT, but the linear loop does not populate steps and the complete-response runtime has no streaming callback. The current tokens-per-second field is an unweighted mean of per-call rates, and the current framework-overhead subtraction can become misleading when intervals overlap.

The runtime already provides the needed choke points. `_invoke_with_middleware()` is the only awaited model invocation path for the linear loop and owns middleware retries. `execute_tool_call()` is the complete tool boundary with one return shape and all tool error translations. `_finish_result()` is the final result boundary. `BaseAgent.generate_reply()` owns the run boundary. The existing `MathHelper` class is the correct home for reusable numeric and interval calculations, and the field guide requires fallback state to remain coordinated by `AgentFallback` rather than adding policy logic to the runtime.

---

## 4. Requirements

### Functional Requirements

1. `CallSpeedRecord` must represent both successful and failed model attempts, including provider, model, duration, safe error type, retry ordinal, and fallback index when known.
2. `AgentSpeedTracker.record_call()` must preserve its current successful-call behavior while accepting input/output token counts and producing the existing duration, TTFT, and output-rate properties.
3. `AgentSpeedTracker.record_call_failure()` must record a failed or cancelled model attempt and return `None` only when speed-record construction fails internally.
4. `_invoke_with_middleware()` must record each provider invocation that raises before middleware retry handling, including attempts that are later retried or followed by a fallback transition.
5. The successful model-call record must include provider-reported input and output tokens when `UsageTracker` can parse them, plus the number of middleware retries observed for that outer invocation.
6. `AgentSpeedTracker.measure_stream()` must wrap an iterable of text chunks, record dispatch-to-first-chunk time, every observed inter-chunk gap, completion duration, and stream failure state, and re-raise the original stream exception.
7. `ToolCallSpeedRecord` must include success/failure state and safe error type in addition to timeout state. `execute_tool_call()` must measure its complete lifecycle so lookup, permission, validation, execution, timeout, and output-schema failures are represented.
8. `AgentSpeedTracker` must calculate model-call, tool-call, step, and stream rollups with minimum, mean, p50, p90, p95, p99, maximum, standard deviation where meaningful, failure/timeout counts and rates where meaningful, and deterministic slowest-item indexes.
9. Model-call rollups must expose total input/output tokens, weighted output tokens per second, weighted prompt tokens per second when TTFT exists, retry totals, fallback-attempt totals, and a deterministic tuple of per-provider/model rollups.
10. Tool-call rollups must expose total failed and timed-out calls, failure and timeout rates, a deterministic tuple of per-tool-name rollups, and the existing duration statistics.
11. Step timing must cover the full direct linear-runtime loop interval, including model work, tool work, middleware, fallback transitions, and all `continue`, result, exception, and cancellation paths.
12. Run rollups must expose time to first tool, time to result-ready, active work on the critical wall-clock path, overlap time, maximum and average tool concurrency, retry wait time, fallback overhead, fallback switch count, and the existing total/cold-start fields.
13. Framework overhead must be derived from total run duration minus the union of known model/tool intervals, clamped to zero when clock noise would otherwise create a negative residual. Overlap must be reported separately rather than hidden inside framework overhead.
14. Completed-run history must retain at most 100 lightweight summaries and expose cold-run count, warm-run count, first-call latency, later-call latency, and recent run-latency percentiles through `get_speed_history()` and the current rollup.
15. All new dataclasses must validate timestamps, counts, rates, enum values, and ordered percentile fields using `AgentSpeedValidationError`.
16. All speed tracking call sites must fail open. A speed-recording failure must mark recording integrity as corrupted but must not replace a model/tool exception or change the agent result.
17. All newly public dataclasses, helpers, and APIs must be exported through their owning `__init__.py` modules and the package root where PR #394 exposes the corresponding speed surface.

### Non-Functional Requirements

- **Performance:** Recording adds only monotonic clock reads, bounded in-memory appends, and read-time aggregation. Stream measurement stores one timestamp per observed chunk. Completed-run history stores lightweight summaries only and is capped at 100 runs.
- **Concurrency:** Interval statistics must support overlapping tool calls and must never assume that the sum of child durations equals wall-clock run duration.
- **Reliability:** Speed instrumentation is best-effort and fail-open at model, tool, stream, step, run, and history boundaries. Original exceptions must be re-raised unchanged after telemetry attempts.
- **Determinism:** Grouped rollups are sorted by provider/model or tool name. Tie-breaking for slowest items is stable and percentile math continues to use the SDK-wide `MathHelper` formula.
- **Privacy:** Store only provider/model/tool identifiers, counts, durations, cancellation/error type names, and numeric usage denominators. Do not store prompts, tool arguments, raw responses, exception messages, API keys, or credentials.
- **Compatibility:** Existing speed fields and imports remain valid. New dataclass fields are appended with defaults where possible, and new methods are additive.

---

## 5. High-Level Design

The existing `AgentSpeedTracker` remains the single mutable owner for the current run. Its ledgers expand from model calls, tool calls, and steps to include measured streams and retry waits. The immutable `AgentSpeedRollup` gains nested model, tool, stream, and history summaries. The tracker continues to use monotonic timestamps and computes all derived values only when `rollup()` is requested.

Model timing moves to the actual provider invocation inside `_invoke_with_middleware()`. Every failed provider attempt is recorded immediately; the successful response is recorded at the existing usage-accounting point so its parsed input/output tokens and observed retry count are available. Tool timing moves to `execute_tool_call()`, which is the complete runtime boundary and already translates all tool failures into a stable result. Step timing uses a tracker-owned active-step scope: the runtime starts a step at the top of each loop pass, the next loop pass closes the previous one, `_finish_result()` closes a normal final path, and `AgentRuntime.arun()` closes exceptional paths in `finally`.

Streaming remains a reusable tracker-side wrapper rather than a dependency from `vidbyte/lib/runners` back into `vidbyte/agents`. A caller passes an existing streaming iterator to `measure_stream()`, which yields chunks unchanged while recording chunk timestamps and preserving the original exception behavior. This supplies real first-chunk and inter-chunk metrics without changing the complete-response agent loop.

```text
[BaseAgent run boundary]
          |
          v
[AgentSpeedTracker]
   | model attempts  <--- _invoke_with_middleware + UsageTracker token fields
   | tool attempts   <--- execute_tool_call complete lifecycle
   | steps           <--- active loop-step scope
   | streams         <--- measure_stream(existing chunk iterator)
   | retry waits     <--- middleware retry sleep
          |
          v
[AgentSpeedRollup]
   call/tool/step/stream stats + run breakdown + grouped stats + history
```

The run breakdown uses interval union math. Known model and tool intervals produce active work; the difference between their summed durations and their union is overlap; total run duration minus active work is framework overhead. Tool intervals additionally produce maximum concurrency, average concurrency, and parallelism efficiency. This keeps the report interpretable for both sequential and concurrent execution.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/dataclasses/speed.py`

**File(s):** `vidbyte/lib/dataclasses/speed.py`
**Type:** Modified

#### What it does

Extends the existing validated speed contracts without moving the public names introduced by PR #394.

#### Interface / API

Add or extend these dataclasses:

- `RecordModelCallInput`: add optional `input_tokens` and `iteration_index` fields.
- `RecordModelCallFailureInput`: provider, model, dispatch timestamp, safe error type, retry ordinal, optional fallback index, and optional iteration index.
- `CallSpeedRecord`: add `input_tokens`, `succeeded`, `error_type`, and `iteration_index`; add `generation_duration_ms`, `prompt_tokens_per_second`, and `is_cancelled` properties.
- `RecordStreamInput`: provider, model, source iterable of text chunks, and dispatch timestamp.
- `StreamSpeedRecord`: stream index, provider, model, dispatch/first-chunk/completion timestamps, observed chunk timestamps, success state, and safe error type; expose duration, TTFT, inter-chunk gaps, chunk-gap statistics, and cancellation state.
- `RecordToolCallInput` and `ToolCallSpeedRecord`: add `succeeded` and optional `error_type` fields.
- `CallSpeedStats`: add success/failure/cancellation counts and rate, p90/min/stddev duration, p90/min/stddev TTFT and output rate, total input/output tokens, weighted output and prompt rates, retry/fallback totals, and `by_model`.
- `ModelSpeedStats`: immutable provider/model group rollup.
- `ToolCallSpeedStats`: add failure/timeout/cancellation counts and rates, p90/min/stddev duration, and `by_tool`.
- `ToolSpeedStats`: immutable tool-name group rollup.
- `StepSpeedStats`: add p50/p90/p95/p99/min/max/stddev and slowest-step index.
- `StreamSpeedStats`: aggregate stream count, failed count/rate, chunk count, TTFT, inter-chunk gap, and chunk-throughput statistics.
- `RunSpeedStats`: add time-to-first-tool, time-to-result-ready, active work, overlap, max/average concurrency, retry wait, fallback overhead, and fallback switch count.
- `RunSpeedSnapshot` and `AgentSpeedHistory`: lightweight completed-run history contracts.
- `AgentSpeedRollup`: add `streams`, `stream_stats`, `history_stats`, and grouped stats while retaining all existing fields.

#### Logic / Algorithm

1. Preserve `None` for unavailable measurements. A stream without chunks has no TTFT; a call without provider usage has no token rate; a run without a complete boundary has no final run duration.
2. Treat model-call `call_count` as attempted calls, with explicit successful and failed counts. Existing successful-only cases therefore retain their current values.
3. Validate safe error type strings as non-empty when supplied and validate every timestamp relationship, including ordered stream chunks and first chunk within the stream interval.
4. Calculate output throughput from output tokens divided by the post-first-token generation interval, or the full call interval when no TTFT exists. Calculate weighted rollup throughput from total output tokens divided by total generation seconds, not from the mean of per-call rates.
5. Calculate prompt throughput only when both input tokens and TTFT are available and TTFT is positive.
6. Calculate stream inter-chunk gaps from adjacent monotonic chunk timestamps. The public names say `chunk`, not `token`, because the existing streaming runner yields text chunks and does not expose token boundaries.
7. Keep grouped rollups as sorted tuples so callers receive immutable, deterministic results.

#### Edge Cases & Error Handling

- Empty ledgers return valid empty stats with `None` for unavailable numeric fields.
- A failed model/tool/stream record still contributes duration and failure counts but never contributes successful-token throughput.
- A zero-length generation window produces `None` throughput rather than division by zero.
- A caller-supplied invalid record raises `AgentSpeedValidationError`; tracker integration catches that error, marks the recording corrupted, and preserves the original runtime behavior.

### 6.2 `vidbyte/lib/util/math.py`

**File(s):** `vidbyte/lib/util/math.py`
**Type:** Modified

#### What it does

Keeps general statistics and interval math in the existing static helper class.

#### Interface / API

Add static methods:

```python
MathHelper.min_or_none(values) -> float | None
MathHelper.stdev_or_none(values) -> float | None
MathHelper.sum_or_none(values) -> float | int | None
MathHelper.weighted_rate_or_none(numerators, denominators) -> float | None
MathHelper.interval_union_seconds(intervals) -> float | None
MathHelper.max_concurrency(intervals) -> int | None
```

#### Logic / Algorithm

1. Return `None` for empty input, matching the existing helper contract.
2. Use population standard deviation so a one-item sample returns zero.
3. Return `None` for a weighted rate when no positive denominator exists.
4. Compute interval union by sorting valid `(start, end)` pairs and merging overlaps.
5. Compute maximum concurrency with deterministic start-before-end tie handling for equal timestamps.

#### Edge Cases & Error Handling

- These helpers remain provider- and agent-independent.
- Empty intervals return `None`; zero-length intervals do not create false positive overlap.
- The tracker validates its own records before passing intervals to the helper.

### 6.3 `vidbyte/lib/constants/speed.py`

**File(s):** `vidbyte/lib/constants/speed.py`
**Type:** New file

#### What it does

Defines the bounded history size used by the tracker.

#### Interface / API

```python
MAX_AGENT_SPEED_HISTORY_RUNS = 100
```

#### Logic / Algorithm

The tracker keeps only the newest 100 lightweight completed-run summaries. This provides rolling history without allowing a long-lived agent to grow an unbounded speed ledger.

#### Edge Cases & Error Handling

The current run ledger is unaffected by the history cap. A history read with no completed runs returns empty history stats.

### 6.4 `vidbyte/agents/speed/tracker.py`

**File(s):** `vidbyte/agents/speed/tracker.py`
**Type:** Modified

#### What it does

Expands `AgentSpeedTracker` into the complete speed-only accumulator and keeps aggregation behind named helpers.

#### Interface / API

Add these methods and properties, with existing methods retained:

```python
def record_call_failure(self, call_input: RecordModelCallFailureInput) -> CallSpeedRecord | None: ...
def measure_stream(self, stream_input: RecordStreamInput) -> Iterator[str]: ...
def record_retry_wait(self, wait_input: RecordRetryWaitInput) -> RetryWaitSpeedRecord | None: ...
def begin_step(self) -> None: ...
def end_step(self) -> StepSpeedRecord | None: ...
def record_result_ready(self) -> None: ...
def history(self) -> AgentSpeedHistory: ...
```

The tracker adds ledgers for streams and retry waits, an active-step start timestamp, a result-ready timestamp, and bounded completed-run snapshots. All new recording methods are fail-open.

#### Logic / Algorithm

1. `record_call_failure()` creates a failed `CallSpeedRecord` with the tracker's current completion time and appends it to the same model-call ledger as successful records.
2. `measure_stream()` yields each source chunk unchanged, captures a timestamp after each yielded chunk is observed, records success on normal exhaustion, records failure on any `BaseException`, and re-raises the source exception.
3. `begin_step()` closes an existing active step before opening a new one. `end_step()` records one step using the current timestamp and clears the active marker. This lets `continue` and `return` boundaries be handled by the runtime without duplicating record calls at every branch.
4. `record_result_ready()` stores the first result-ready timestamp. `_build_run_stats()` derives time-to-result from the run start.
5. `record_run_end()` closes any active step, records the run end, and archives a lightweight snapshot once. `reset()` clears only the current-run ledgers and markers; completed history remains.
6. `_build_call_stats()` calculates global call stats and delegates grouped provider/model construction to `_build_model_stats()`.
7. `_build_tool_call_stats()` calculates global tool stats and delegates grouped tool-name construction to `_build_tool_stats()`.
8. `_build_step_stats()` and `_build_stream_stats()` calculate their complete distribution and outcome fields using `MathHelper`.
9. `_build_run_stats()` calculates known interval union, overlap, concurrency, milestone durations, retry wait, and fallback overhead. Failed attempts preceding a later higher fallback index count as fallback overhead; retry wait records count separately.
10. `_build_history_stats()` summarizes the bounded completed-run snapshots, classifying the first completed run as cold and later completed runs as warm.

#### Edge Cases & Error Handling

- A malformed provider/model or invalid clock result marks the tracker corrupted and returns `None`.
- Stream failures are recorded before their original exception is re-raised.
- `end_step()` is safe when no step is active and never masks an exception from a runtime `finally` block.
- History archival failures affect only `recording_integrity`; current agent execution continues.

### 6.5 `vidbyte/agents/runtime.py`

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Wires the tracker to actual model attempts, tool lifecycles, retry waits, steps, and final result readiness without changing the runner or fallback contracts.

#### Interface / API

No public runtime signature changes are required except importing the new speed input dataclasses. `_invoke_with_middleware()` keeps its existing keyword signature because external runtime algorithms call it directly.

#### Logic / Algorithm

1. In `_invoke_with_middleware()`, capture a dispatch timestamp immediately before each `handle.invoke()` call. On exceptions, call `record_call_failure()` with the current provider/model, safe exception type, and retry ordinal before invoking middleware error handling.
2. When middleware asks for a retry, time its sleep with `record_retry_wait()` and continue the existing loop.
3. In the outer successful-response path, retain the existing usage record and speed record but pass input tokens, output tokens, iteration index, and the number of internal retries observed during that invocation.
4. Start an active step at the top of every `_arun_once()` loop pass. Close it when the next pass begins. Wrap `AgentRuntime.arun()` in `finally` so an unhandled exception or cancellation closes the active step.
5. Move tool timing from `_execute_tool()` to `execute_tool_call()`. Start before lookup and finish in `finally` after every existing catch branch, preserving timeout detection and adding safe success/error state.
6. Call `record_result_ready()` at the end of `_finish_result()` after middleware and run-state metadata have been applied.

#### Edge Cases & Error Handling

- The runtime continues to re-raise provider/tool exceptions according to existing middleware and fallback policy.
- Telemetry recording is best-effort and cannot replace a provider, tool, cancellation, or middleware exception.
- Fallback policy decisions remain delegated to `AgentFallback`; speed tracking only records the attempt and transition indexes it is given.
- Direct callers of `_invoke_with_middleware()` continue to work because its signature and return tuple remain unchanged.

### 6.6 `vidbyte/agents/base.py`

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Exposes completed-run history next to the existing current-run speed API.

#### Interface / API

```python
def get_speed_history(self) -> AgentSpeedHistory: ...
```

#### Logic / Algorithm

Return `self._speed_tracker.history()` without resetting or mutating the current-run ledger.

#### Edge Cases & Error Handling

An agent with no completed runs returns empty history stats. Existing `get_speed_stats()` behavior is unchanged.

### 6.7 Public exports and documentation

**File(s):** `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/constants/__init__.py`, `vidbyte/agents/speed/__init__.py`, `vidbyte/__init__.py`, `README.md`
**Type:** Modified

#### What it does

Exports the new speed contracts and documents how callers use current-run, history, and stream measurements.

#### Interface / API

The package root will expose `AgentSpeedHistory`, `ModelSpeedStats`, `ToolSpeedStats`, `StreamSpeedStats`, `RecordModelCallFailureInput`, `RecordStreamInput`, `RunSpeedSnapshot`, and the other new speed dataclasses alongside PR #394's existing symbols. `MAX_AGENT_SPEED_HISTORY_RUNS` is exported from `vidbyte.lib.constants` but is not required at the package root.

#### Logic / Algorithm

Update README speed-tracking documentation with a short example showing `agent.get_speed_stats()`, `agent.get_speed_history()`, and `tracker.measure_stream()` for an existing streaming iterator. Keep the example free of secrets and provider network calls.

#### Edge Cases & Error Handling

Exports are pure import wiring and must not create runtime instances or side effects.

---

## 7. Data Model Changes

N/A - this feature has no database, checkpoint, session, or persisted schema changes. New dataclasses are in-memory speed contracts only. Completed history stores bounded lightweight summaries inside the agent process.

---

## 8. API Changes

N/A - there are no HTTP endpoints. The additive Python API changes are `BaseAgent.get_speed_history()`, `AgentSpeedTracker.measure_stream()`, `AgentSpeedTracker.record_call_failure()`, retry/step/result timing helpers, and the new immutable speed dataclasses described in Section 6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-speed-stats-expansion.md` | Source-of-truth design for the complete speed-stat expansion |
| CREATE | `vidbyte/lib/constants/speed.py` | Bound completed-run history to a named SDK constant |
| MODIFY | `vidbyte/lib/dataclasses/speed.py` | Add outcome, stream, grouped, distribution, run-breakdown, and history contracts |
| MODIFY | `vidbyte/lib/util/math.py` | Add reusable min, standard deviation, weighted-rate, interval-union, and concurrency math |
| MODIFY | `vidbyte/agents/speed/tracker.py` | Record and roll up all new speed ledgers and history |
| MODIFY | `vidbyte/agents/runtime.py` | Wire model failures/retries, complete tool timing, steps, retry waits, and result readiness |
| MODIFY | `vidbyte/agents/base.py` | Expose completed-run speed history |
| MODIFY | `vidbyte/lib/constants/__init__.py` | Export the history bound |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export new speed dataclasses |
| MODIFY | `vidbyte/agents/speed/__init__.py` | Export new speed dataclasses through the compatibility namespace |
| MODIFY | `vidbyte/__init__.py` | Export new public speed APIs at the package root |
| MODIFY | `README.md` | Document current-run, history, and stream speed usage |

No test files are created or modified. Existing tests and all repository gates remain required verification.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python `statistics` | stdlib, Python 3.11+ | Population standard deviation and existing mean math | None |
| Python `time` | stdlib | Monotonic duration timestamps | None |
| Existing `UsageTracker` | Current SDK implementation | Read provider-normalized token denominators | No billing behavior changes |
| Existing `StreamingTextModelRunner` | Current SDK implementation | Supplies iterable text chunks to `measure_stream()` | No runner dependency on agent speed code |

No new third-party dependency, network call, environment variable, or service integration is introduced.

---

## 11. Rollout & Deployment

- Additive in-process instrumentation; no feature flag is needed.
- Existing speed fields and current-run APIs remain available.
- No migration or deployment ordering is required because nothing is persisted.
- Rollback is a normal code revert. It removes new in-memory fields and methods without requiring data cleanup.
- The canonical verification command is `python scripts/run_ci.py`; from the isolated worktree, source verification must use the worktree import path as documented by the SDK field guide.

---

## 12. Open Questions

- [ ] Should a future release add a caller-supplied token counter to `measure_stream()`, or should stream throughput remain chunk-based until provider response objects expose token deltas consistently?
- [ ] Should bounded history become configurable per agent after real usage shows that 100 runs is too small or too large?
- [ ] Should non-linear runtimes receive their own tracker threading in a separate design, given their different concurrency and ownership model?

---

## 13. Alternatives Considered

### Alternative 1: Add only more aggregate fields to the current successful-call ledger

- **What:** Keep the current runtime hooks and calculate p90, standard deviation, and more rates from successful model and tool records only.
- **Why rejected:** It would make failure, retry, timeout, and fallback latency invisible, which is exactly the latency users need when diagnosing slow agents.

### Alternative 2: Put speed tracking in middleware

- **What:** Add a middleware that wraps model and tool hooks and owns all timestamps.
- **Why rejected:** The SDK's authoritative usage accounting is directly owned by `AgentRuntime`, and the complete tool boundary and fallback attempt boundaries are not all represented by one middleware hook. Direct choke-point instrumentation keeps speed and usage ledgers aligned without adding a second ownership model.

### Alternative 3: Make the lower-level streaming runner import `AgentSpeedTracker`

- **What:** Add an agent tracker parameter directly to `StreamingTextModelRunner`.
- **Why rejected:** `vidbyte/lib/runners` is below `vidbyte/agents` in the SDK layering. The tracker-side iterable wrapper measures the same stream while preserving that dependency direction.

### Alternative 4: Define framework overhead as total duration minus summed child durations

- **What:** Preserve the existing residual calculation unchanged.
- **Why rejected:** Concurrent child intervals can sum to more than wall-clock time, producing negative or misleading framework overhead. Interval union and explicit overlap separate runtime work from concurrency effects.

### Alternative 5: Store every completed run in full

- **What:** Keep every historical rollup and all raw records for the agent lifetime.
- **Why rejected:** Long-lived agents would accumulate unbounded memory and duplicate raw ledgers. Lightweight snapshots capped at 100 runs provide the requested warm/cold and rolling statistics at predictable cost.

