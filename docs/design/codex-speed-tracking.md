# Design Doc: Codex Speed Tracking

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

`AgentSpeedTracker` is a complete latency ledger the SDK already owns — run boundaries, per-call timing, rollups, and bounded cross-run history — and `CodexHarnessAgent` calls none of it. A Codex turn therefore reports no latency at all, even though the adapter has both wall-clock boundaries and the provider's own `duration_ms`. This change measures each native turn locally, records it as one model call, and exposes `get_speed_stats()` and `get_speed_history()` with the same semantics `BaseAgent` documents. It deliberately reports no time-to-first-token, because streaming is not implemented and a fabricated zero would read as "instant" in every rollup that consumes it.

---

## 2. Goals & Non-Goals

### Goals

- Measure each `arun()` between run-start and run-end boundaries owned by the agent, on every exit path including failure and cancellation.
- Record one `CallSpeedRecord` per turn, timed with the tracker's own monotonic clock.
- Record a failed turn as a failed call rather than dropping it, so a timeout's latency is visible.
- Expose `CodexHarnessAgent.get_speed_stats()` and `.get_speed_history()`.
- Leave `first_token_at` absent, never zero, because no streaming boundary exists to measure.
- Label the provider honestly as `codex`, which the speed tracker permits and the usage tracker does not.

### Non-Goals

- Streaming and time-to-first-token. Both require `AsyncThread.turn()` and `AsyncTurnHandle.stream()`, which is roadmap task T01 and its own design.
- Per-tool timing. Codex owns its internal tool loop and a completed `TurnResult` exposes no per-tool intervals; inventing them from item ordering would be a guess presented as a measurement.
- Step, retry-wait, and concurrency instrumentation. Those measure a Vidbyte-owned loop that does not exist here; the corresponding rollup fields stay empty rather than being filled with turn-level values under step-level names.
- Trusting the provider's `duration_ms` as the primary measurement. See §5 for why it is recorded as corroboration only.
- Token usage. That is PR 2 in this sequence and a separate abstraction.

---

## 3. Background & Context

`AgentSpeedTracker` (`vidbyte/agents/speed/tracker.py:59`) exposes `record_run_start`, `record_run_end`, `record_call`, `record_call_failure`, `rollup()`, and `history()`. `BaseAgent` owns one at `vidbyte/agents/base.py:231` and drives it with a specific lifecycle: reset then `record_run_start` at line 603-604, and `record_run_end` on **all three** exit paths — success (line 640), `Exception` (line 645), and `BaseException` (line 657). That third handler exists so a `CancelledError` still closes the run rather than leaving it open forever.

`CodexRunResult` carries `duration_ms`, `started_at`, and `completed_at` from the provider. None of these is in the tracker's clock domain: `AgentSpeedTracker` defaults to `time.monotonic` (line 65) and stamps `completed_at` itself inside `record_call` (line 141). Mixing a provider wall-clock timestamp into a monotonic ledger would produce a nonsense interval, which is why the design measures locally and treats `duration_ms` as a separate corroborating fact.

Two validation constraints shape the record. `CallSpeedRecord.__post_init__` calls `_require_non_empty_str` on both `provider` and `model` (`vidbyte/lib/dataclasses/speed.py:165-166`), so an unset Codex model cannot be recorded as `""`. And `RecordModelCallInput` requires a non-`None` `response` object it duck-types `provider` and `model` off, exactly as `UsageTracker.record_call` does — but with one important difference: `AgentSpeedTracker.record_call` reads the provider as a plain string with no `ModelProvider` coercion (line 133-135), so the speed record can name `codex` truthfully while the usage record must name `openai` to be priced.

The roadmap tracks this as **O04** ("Measure runtime performance"), whose stated scope is startup latency, first event or text, tool time, total turn time, and interruption latency, "with AgentSpeed-compatible semantics" and an explicit instruction to avoid inventing unavailable internal metrics. Of those five, only total turn time and interruption latency are observable from a completed turn; this design records those two and states the other three as unavailable rather than approximating them.

---

## 4. Requirements

### Functional Requirements

1. `CodexHarnessAgent` owns one `AgentSpeedTracker` instance, created at construction.
2. `arun()` resets the tracker and calls `record_run_start()` before the transport call.
3. `arun()` calls `record_run_end()` on every exit path: success, `Exception`, and `BaseException` including `asyncio.CancelledError`.
4. A completed turn records exactly one successful `CallSpeedRecord`.
5. A failed turn records exactly one failed `CallSpeedRecord` through `record_call_failure`, carrying the raised exception's type name.
6. A cancelled turn records a failed record with `cancelled=True`, and the cancellation still propagates unchanged.
7. `dispatched_at` comes from `AgentSpeedTracker.now()`, taken immediately before the awaited transport call, so the interval is entirely within the tracker's monotonic clock domain.
8. `first_token_at` is never set. No streaming boundary exists, so time-to-first-token must be absent rather than zero.
9. The record's provider is `codex` and its model is the effective model name, falling back to `unknown` when neither the turn nor the thread names one, because `CallSpeedRecord` rejects an empty model.
10. The record carries `input_tokens` and `output_tokens` from the turn's per-turn usage delta when the provider reported usage, so the rollup's throughput denominators are real rather than absent.
11. The provider's own `duration_ms` is published on the message metadata as a separate, clearly named fact, never substituted for the measured interval.
12. `get_speed_stats()` returns the tracker's `AgentSpeedRollup`; `get_speed_history()` returns its bounded `AgentSpeedHistory`, which survives the per-run reset.
13. Speed recording never fails a turn. Every recording call is fail-open, matching the tracker's own documented contract.

### Non-Functional Requirements

- **Performance:** two clock reads and one list append per turn. The instrumentation is immeasurable against a Codex turn, which spawns a process and runs a model loop.
- **Scalability:** the per-run ledger is reset each turn, and history is bounded by `MAX_AGENT_SPEED_HISTORY_RUNS`, so neither grows without limit on a long-lived thread.
- **Security:** timing and token counts only. No prompt text, no reasoning content, no file paths.
- **Observability:** this change is the observability work. `AgentSpeedRecordingIntegrity` distinguishes a complete ledger from one that lost a record.
- **Reliability:** fail-open at every boundary. A metering failure degrades the rollup, never the turn.

---

## 5. High-Level Design

`CodexSpeedTranslator` lands in `vidbyte/agents/codex/speed.py` as a peer of `context.py`, `result.py`, and `fork.py`: one file, one concern, one class. It converts a completed or failed turn into the tracker's input records and files them. It does not own the tracker and does not compute statistics — `AgentSpeedTracker` already owns all aggregation, and duplicating any of it here would create two definitions of the same metric.

The central design decision is **measuring locally rather than trusting `duration_ms`**. The provider reports its own turn duration, which is tempting to record directly. It is the wrong primary source for three reasons. It is in a different clock domain from the tracker's `time.monotonic`, so it cannot be combined with the run boundaries the agent owns. It measures the provider's view of the turn, excluding app-server startup, connection setup, and result normalization — all of which the caller actually waits through, and all of which `CodexTransport.run` performs inside the interval this design measures. And it is absent on some failure paths, where latency matters most. So the record's interval is `tracker.now()` taken before the transport call to `record_call`'s own completion stamp, and `duration_ms` is published separately on the message metadata under its own key, where a reader can compare the two and see the adapter's overhead as the difference.

The second decision is **what to leave empty**. `RunSpeedStats` has fields for `time_to_first_tool_ms`, `parallelism_efficiency`, `max_concurrency`, and more. Every one of them describes a Vidbyte-owned loop. Codex owns its loop, exposes no per-tool intervals on a completed `TurnResult`, and gives no iteration boundaries. Filling those fields with turn-level numbers would put a plausible value under a name that means something else — the exact failure the roadmap warns against. They stay at their empty defaults, and the file header says why, so the next reader does not treat the gap as unfinished work.

```
CodexHarnessAgent.arun()
   |
   |-- self._speed.reset(); self._speed.record_run_start()
   |-- dispatched_at = self._speed.now()          <- tracker clock domain
   v
CodexTransport.run()   ... app-server start + thread + turn + normalize ...
   |                                                   |
   | success                                           | raise
   v                                                   v
CodexSpeedTranslator.record_turn()          CodexSpeedTranslator.record_failure()
   |   RecordModelCallInput(                    |   RecordModelCallFailureInput(
   |     response=CodexSpeedResponse(codex,...) |     provider=codex, model=...,
   |     dispatched_at=..., first_token_at=None |     error_type=..., cancelled=...)
   |     input_tokens=..., output_tokens=...)   |
   v                                            v
AgentSpeedTracker.record_call()          AgentSpeedTracker.record_call_failure()
   |
   |-- self._speed.record_run_end()   <- on success, Exception, and BaseException
   v
get_speed_stats() / get_speed_history()
```

---

## 6. Detailed Design

### 6.1 Codex speed response shim

**File(s):** `vidbyte/lib/dataclasses/codex.py`
**Type:** Modified

#### What it does

Carries the `provider` and `model` attributes `AgentSpeedTracker.record_call` duck-types off its `response` object.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class CodexSpeedResponse:
    """Presents one Codex turn to AgentSpeedTracker in the shape it duck-types."""

    provider: str
    model: str
```

`CodexSpeedTranslationRequest` holds `result: CodexRunResult | None`, `settings: CodexAgentSettings`, `tracker: object`, `dispatched_at: float`, and `error: BaseException | None`.

#### Logic / Algorithm

1. `CodexSpeedResponse.__post_init__` requires both fields as non-empty text, matching what `CallSpeedRecord` will itself demand a moment later, so the rejection happens at the adapter boundary rather than inside the tracker.
2. `CodexSpeedTranslationRequest.__post_init__` requires a non-negative `dispatched_at` and a tracker exposing both `record_call` and `record_call_failure`, and requires exactly one of `result` or `error` to be present.

#### Edge Cases & Error Handling

- **Both `result` and `error` present, or neither.** Rejected at construction: a turn either completed or failed, and a request that claims both would record two contradictory entries for one turn.

### 6.2 CodexSpeedTranslator

**File(s):** `vidbyte/agents/codex/speed.py`
**Type:** New file

#### What it does

Files one speed record per turn — successful or failed — into the caller's tracker.

#### Interface / API

```python
class CodexSpeedTranslator:
    """Records one native turn's latency into Vidbyte's shared speed ledger."""

    @classmethod
    def record_turn(cls, request: CodexSpeedTranslationRequest) -> CallSpeedRecord | None: ...

    @staticmethod
    def _model_name(settings: CodexAgentSettings) -> str: ...

    @staticmethod
    def _token_counts(result: CodexRunResult) -> tuple[int | None, int | None]: ...
```

#### Logic / Algorithm

1. Resolve the model as `turn.model or thread.model or CODEX_UNKNOWN_MODEL`.
2. When `request.error` is set, build `RecordModelCallFailureInput` with the exception's type name and `cancelled=isinstance(error, asyncio.CancelledError)`, then call `tracker.record_call_failure`.
3. Otherwise build `RecordModelCallInput` with `response=CodexSpeedResponse(...)`, `dispatched_at=request.dispatched_at`, `first_token_at=None`, and the token denominators from `_token_counts`, then call `tracker.record_call`.
4. `_token_counts` returns the input and output counts from `result.last_usage` when `usage_available` is true, and `(None, None)` otherwise — absent, never zero.

#### Edge Cases & Error Handling

- **Turn with no usage.** Token denominators are `None`, so throughput statistics are absent rather than computed from a fabricated zero.
- **Empty model at both layers.** Falls back to the `unknown` constant, because `CallSpeedRecord` rejects an empty model and dropping the record entirely would lose the latency measurement over a naming detail.
- **Recording failure.** `AgentSpeedTracker.record_call` is documented fail-open and returns `None` after marking integrity corrupted, so the translator adds no guard of its own.

### 6.3 CodexHarnessAgent speed surface

**File(s):** `vidbyte/agents/codex/agent.py`
**Type:** Modified

#### What it does

Owns the tracker, drives the run boundaries on every exit path, and exposes the two accessors.

#### Interface / API

```python
class CodexHarnessAgent:
    def get_speed_stats(self) -> AgentSpeedRollup: ...
    def get_speed_history(self) -> AgentSpeedHistory: ...
```

#### Logic / Algorithm

1. `__init__` creates `self._speed = AgentSpeedTracker()`.
2. `arun` resets the tracker and calls `record_run_start()` before the transport call, mirroring `vidbyte/agents/base.py:603-604`.
3. The transport call is wrapped so all three outcomes are handled: success records the turn and ends the run; `Exception` records the failure, ends the run, and re-raises; `BaseException` — which is how `asyncio.CancelledError` arrives — records a cancelled failure, ends the run, and re-raises unchanged.
4. `get_speed_stats()` returns `self._speed.rollup()`; `get_speed_history()` returns `self._speed.history()`.

#### Edge Cases & Error Handling

- **Cancellation must stay cancellation.** The `BaseException` handler re-raises with a bare `raise`, never wrapping. `CodexTransport` already takes care to preserve `asyncio.CancelledError`, and this change must not undo that; the S019 cancellation-propagation lint rule enforces it.
- **`record_run_end` twice.** The tracker guards this itself with `_run_archived`, so a defensive check here would be redundant.
- **Reset timing.** Reset happens with `record_run_start`, immediately before the transport call, so a turn rejected during translation leaves the previous turn's rollup readable — the same ordering rule PR 2 applies to the usage tracker.

### 6.4 Provider duration metadata

**File(s):** `vidbyte/agents/codex/result.py`
**Type:** Modified

#### What it does

Publishes the provider's self-reported turn duration under its own metadata key.

#### Logic / Algorithm

1. `CodexResultTranslator.translate` adds `"provider_duration_ms": result.duration_ms` when the provider reported one.
2. The key is omitted when `duration_ms` is `None`, so absent stays distinguishable from zero.

#### Edge Cases & Error Handling

- **Naming.** The key is deliberately `provider_duration_ms`, not `duration_ms`, so no reader can mistake it for the measured end-to-end interval the speed rollup reports.

---

## 7. Data Model Changes

N/A - no persisted records, no database, no migration. Two in-memory dataclasses are added to `vidbyte/lib/dataclasses/codex.py` (`CodexSpeedResponse`, `CodexSpeedTranslationRequest`). Neither is serialized.

---

## 8. API Changes

N/A - no HTTP endpoints in this package. The public Python surface gains two methods on `CodexHarnessAgent` and one metadata key on returned messages, both additive.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/codex-speed-tracking.md` | This design document |
| CREATE | `vidbyte/agents/codex/speed.py` | `CodexSpeedTranslator` |
| MODIFY | `vidbyte/lib/dataclasses/codex.py` | `CodexSpeedResponse`, `CodexSpeedTranslationRequest` |
| MODIFY | `vidbyte/lib/constants/codex.py` | `CODEX_UNKNOWN_MODEL`, `CODEX_PROVIDER_DURATION_KEY` (A007) |
| MODIFY | `vidbyte/agents/codex/agent.py` | Own the tracker, drive run boundaries on all exit paths, add the accessors |
| MODIFY | `vidbyte/agents/codex/result.py` | Publish `metadata["provider_duration_ms"]` |
| MODIFY | `vidbyte/agents/codex/__init__.py` | Export the new dataclasses |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export on the agents facade |
| MODIFY | `vidbyte/__init__.py` | Re-export for public-export integrity (S015) |
| CREATE | `tests/test_codex_speed_tracking.py` | Feature tests for the Testing Plan below |
| CREATE | `scripts/test-codex-speed-tracking.py` | Phase 5 verification script |

Totals: 4 create, 7 modify, 0 delete.

---

## 10. Testing Plan

All tests run offline with an injected fake clock, so intervals are exact rather than timing-dependent.

### Unit Tests

- `CodexSpeedTranslator` -> `records one successful call for a completed turn` — [Edge Case]
- `CodexSpeedTranslator` -> `leaves first_token_at absent, not zero` — [Silent Failure] — the single most dangerous defect here: a zero reads as an instant first token in every rollup that consumes it, turning a missing measurement into a fabricated excellent one.
- `CodexSpeedTranslator` -> `names the provider codex, not openai` — [Silent Failure] — the usage record must say `openai` to be priced and the speed record must say `codex` to be true; copying one convention into the other misattributes every Codex latency to the OpenAI provider group in `model_stats`.
- `CodexSpeedTranslator` -> `falls back to the unknown model when neither layer names one` — [Edge Case] — without it `CallSpeedRecord` raises and the latency is lost.
- `CodexSpeedTranslator` -> `prefers the turn model over the thread model` — [Silent Failure]
- `CodexSpeedTranslator` -> `carries token denominators from the per-turn delta` — [Silent Failure] — using the cumulative snapshot would inflate throughput on every turn after the first.
- `CodexSpeedTranslator` -> `leaves token denominators absent when usage is unavailable` — [Edge Case]
- `CodexSpeedTranslator` -> `records a failed call carrying the exception type name` — [Hidden Failure] — a dropped failure record makes a timeout look like a turn that never happened.
- `CodexSpeedTranslator` -> `marks a CancelledError record as cancelled` — [Hidden Failure]
- `CodexSpeedResponse` -> `rejects an empty model` — [Hidden Assumption]
- `CodexSpeedTranslationRequest` -> `rejects a request carrying both a result and an error` — [Hidden Assumption] — one turn has one outcome.
- `CodexSpeedTranslationRequest` -> `rejects a request carrying neither` — [Hidden Assumption]
- `CodexSpeedTranslationRequest` -> `rejects a tracker missing record_call_failure` — [Hidden Assumption]

### Integration Tests

The flow to prove is: one `arun()` opens and closes exactly one run, on every outcome. Only `CodexTransport` is faked; the real `AgentSpeedTracker` runs with an injected clock, because the defects here — an unclosed run, a double-archived run, a lost cancellation — only appear in the real lifecycle.

- One successful `arun()` yields `get_speed_stats().calls` of length 1 with `succeeded=True`, and `run_stats.total_duration_ms` equal to the fake clock's elapsed interval. [Silent Failure] — proves the interval is measured, not copied from `duration_ms`.
- A failing `arun()` yields one record with `succeeded=False`, and the run is still closed — `run_stats.total_duration_ms` is not `None`. [Hidden Failure] — an unclosed run leaves every subsequent rollup wrong, and this is exactly what a missing `record_run_end` in the exception path produces.
- A cancelled `arun()` re-raises `asyncio.CancelledError` unchanged and records a record with `cancelled=True`. [Hidden Failure] — proves the `BaseException` handler exists; without it the `Exception` handler never runs for a cancellation and the run stays open forever.
- Two sequential `arun()` calls leave `get_speed_stats().calls` of length 1 and `get_speed_history()` reporting 2 completed runs. [Silent Failure] — proves the reset clears the ledger but not the history, the distinction `BaseAgent.get_speed_history` documents.
- The measured `total_duration_ms` differs from `metadata["provider_duration_ms"]` when the fake transport sleeps longer than the reported provider duration. [Silent Failure] — proves the two are genuinely independent facts rather than the same number published twice.

### Manual / QA Test Cases

1. Given a Codex agent with no model configured, when a turn completes, then `get_speed_stats().calls[0].model` is `unknown` and the latency is still recorded. — [Edge Case]
2. Given a Codex agent, when a turn is cancelled mid-flight, then the caller sees `asyncio.CancelledError` and `get_speed_stats()` shows one cancelled record. — [Hidden Failure]
3. Given three completed turns, when `get_speed_history()` is read, then it reports three runs while `get_speed_stats().calls` holds only the most recent. — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `openai-codex` | 0.147.0, optional extra | Source of `duration_ms`, already normalized upstream | None added — no new SDK surface is read |

No dependency additions.

---

## 12. Rollout & Deployment

No feature flag. The change is additive: two new methods, one new metadata key, no altered signatures. Rollback is a revert of this branch.

This is PR 3 of five independent Codex-translation PRs, each branched from `origin/main`. It should be merged after PR 2 (`feat/codex-usage-tracking`) to keep the conflicts in `vidbyte/agents/codex/agent.py` trivial; both add a tracker to `__init__` and a recording call in `arun`, in adjacent lines.

---

## 13. Open Questions

- [ ] Once streaming lands (roadmap T01), should `first_token_at` be populated from the first `agentMessage` delta, or from the first event of any kind? The two answer different questions and the choice should be made with the streaming design, not pre-empted here.
- [ ] Should `record_result_ready()` be called after result translation, giving `time_to_result_ready_ms` a meaning for Codex? Left unwired because the gap between turn completion and translation is sub-millisecond and would report a misleadingly precise near-zero.

---

## 14. Alternatives Considered

### Alternative 1: Record the provider's `duration_ms` as the call interval

- What: Synthesize `dispatched_at`/`completed_at` from `result.duration_ms` instead of measuring locally.
- Why rejected: It is a different clock domain from the tracker's `time.monotonic`, so it cannot be combined with the agent-owned run boundaries. It also excludes app-server startup, connection setup, and result normalization — real latency the caller waits through — and it is absent on the failure paths where latency matters most.

### Alternative 2: Fold speed recording into `CodexMetricsTranslator` from PR 2

- What: One translator handling both usage and speed.
- Why rejected: They disagree on the one thing a shared class would have to settle — the usage record must name the provider `openai` to reach the pricing table, and the speed record must name it `codex` to be truthful. They also have different failure semantics: a failed turn has no usage to record but does have latency worth recording. Merging them would mean a single class with two provider names and two outcome models.

### Alternative 3: Populate `first_token_at` with the turn completion time

- What: Set `first_token_at = completed_at` so the field is not empty.
- Why rejected: It would make time-to-first-token equal to total duration, which is not merely imprecise but actively wrong, and it would silently corrupt `CallSpeedStats`' first-token aggregates. Absent is the honest value until streaming exists.

### Alternative 4: Skip the failure path and record only completed turns

- What: Record on success only, keeping the change smaller.
- Why rejected: Latency matters most when something goes wrong. A turn that hangs for 120 seconds and then fails is the exact event an operator needs in the ledger, and dropping it makes the rollup describe only the healthy subset — a survivorship bias built into the instrumentation.
