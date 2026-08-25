# Design Doc: Usage Recording Integrity Signal

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-24
**Last Updated:** 2026-08-24

---

## 1. Overview

Two functions that meter billable work — `AgentRuntime._record_operation_usage` (priced search/fetch tool calls) and `UsageTracker.record_call` (priced model calls) — currently swallow exceptions raised while computing or storing a usage record, and the caller cannot tell the difference between "there was legitimately nothing to bill" and "we tried to bill this and our own code broke while doing it." This change makes that distinction visible on `UsageRollup` via a new `recording_integrity` field, so the application layer that consumes the rollup can fail the run instead of silently under-billing.

---

## 2. Goals & Non-Goals

### Goals
- Distinguish, on `UsageRollup`, between "every operation this run touched was either priced or explicitly marked unpriced" and "an exception was swallowed while trying to record a real, already-incurred charge."
- Make that distinction available without widening the public return signature of `_record_operation_usage` or `record_call`, since existing callers of both already ignore their return values and only the aggregate rollup is inspected downstream.
- Keep the existing behavior that a metering bug can never crash the agent run itself — the swallow-and-continue behavior at the point of failure is preserved; only what happens *after* the swallow changes.

### Non-Goals
- Do not change how `cost_complete` is computed or what it means (an operation/model with no catalogued rate). This is a second, independent signal, not a replacement.
- Do not attempt to reconstruct a valid, correctly-priced record on the failure path. In both bugs, the exception can originate from the exact accessor that would supply the record's own fields (`tool.units_used`, `usage_cls.from_usage_payload`), so a best-effort partial record would be a guess, not a fact.
- Do not change `_as_provider`'s existing narrow `except (ValueError, TypeError)` — that path is a legitimate "unknown provider string" outcome, not a swallowed bug, and is out of scope.
- Do not refactor `pricing/tracker.py`'s module-level helper functions (`_is_billable_key`, `_reported_or_table_cost`, `_sum_or_none`) into a class-bound helper, even though the field guide's `class-bound-helpers.md` prefers that shape for a module of related free functions. See Alternatives Considered.
- Do not touch the vidbyte (app-layer) side of this — that is a separate design doc and PR in the `vidbyte` repo, which depends on this change.

---

## 3. Background & Context

This was found during an audit of the research harness against the principle "money and permissions should break loudly; logging should never break anything." Two call sites violate the money half:

- `vidbyte/agents/runtime.py:1170-1189`, `_record_operation_usage`: wraps the whole priced-operation recording loop in `except Exception: return`, with a comment stating the swallow is deliberate ("swallows any hook error so a pricing bug can never break execution"). If `tool.mode_used()`, `tool.units_used()`, or `tool.reported_cost_usd()` raises on malformed tool metadata, the real vendor call already happened and its cost is never recorded anywhere.
- `vidbyte/agents/pricing/tracker.py:49-67`, `record_call`, via `_parse_usage` (123-134): if the provider's usage payload fails to parse, `_parse_usage`'s own `except Exception: return None` makes `record_call` return `None` and the model call is never appended to `self._records`. Unlike the SDK's own documented-good pattern for `ModelPricingRegistry.resolve` (an unpriced model still gets a record appended with `cost_usd=None`, correctly flipping `cost_complete` to `False`), this call is invisible to the ledger entirely — if other calls in the same turn priced fine, `cost_complete` can still read `True` on a run that actually had an unrecorded call.

The application layer (`vidbyte` repo, `UsageSession.apply_agent_usage`) already fails closed on `cost_complete is False`. That mechanism is the right template, but `cost_complete` means something different (a known-unpriced operation) from what these two bugs represent (an internal exception during metering itself), so this needs its own signal rather than overloading `cost_complete`.

---

## 4. Requirements

### Functional Requirements
1. `UsageTracker` gains a `mark_recording_corrupted()` method and an internal flag, defaulting to not-corrupted.
2. `UsageRollup` gains a `recording_integrity: UsageRecordingIntegrity` field (new enum: `INTACT`, `CORRUPTED`), defaulting to `INTACT`, populated by `UsageTracker.rollup()` from the internal flag.
3. `AgentRuntime._record_operation_usage`'s `except Exception:` arm calls `self.usage_tracker.mark_recording_corrupted()` before returning, in addition to its existing behavior.
4. `UsageTracker.record_call`'s exception handling moves from inside `_parse_usage` to `record_call` itself: `_parse_usage` no longer catches `from_usage_payload`'s exceptions; `record_call` wraps the call to `_parse_usage` and calls `self.mark_recording_corrupted()` on failure, then returns `None` exactly as it does today for a legitimate skip.
5. `_as_provider` is unchanged — its narrow `except (ValueError, TypeError)` stays as-is.
6. A run where every operation and model call priced normally (no exception ever swallowed) must report `recording_integrity is INTACT`, identical to today's behavior.

### Non-Functional Requirements
- No new dependencies.
- No behavior change to the happy path — every existing test that does not specifically inject a metering failure must pass unmodified.
- The new enum and field must be importable from the same modules their sibling types already are (`vidbyte.agents.pricing.records`), so the `vidbyte` repo's import matches existing patterns (e.g. `from vidbyte.agents.pricing.records import UsageRollup`).
- Public API is purely additive: no existing field, method signature, or return type changes.

---

## 5. High-Level Design

```
[Priced tool call]                    [Model call]
     |                                      |
     v                                      v
_record_operation_usage()          UsageTracker.record_call()
     |  (except Exception:)              |  (except around _parse_usage:)
     v                                      v
 usage_tracker.mark_recording_corrupted()  (same)
     |                                      |
     +------------------+-------------------+
                         v
              UsageTracker._recording_corrupted
                         |
                         v
              UsageTracker.rollup()
                         |
                         v
        UsageRollup.recording_integrity = CORRUPTED
                         |
                         v
        (consumed by vidbyte's UsageSession.apply_agent_usage —
         separate repo, separate design doc)
```

Both bugs currently discard their failure at the point of catching it. The fix keeps the catch exactly where it is (so a metering bug still cannot crash the agent loop) and adds one line to each catch arm that flips a flag on the run's shared `UsageTracker` instance — the same object both functions already have direct access to (`self.usage_tracker` in `runtime.py`, `self` in `tracker.py`). No new plumbing is needed through `execute_tool_call`, `ToolCallContext`, or the model-call loop, because nothing currently threads a per-call outcome through those paths for the happy case either — the aggregate `rollup()` call at turn-end is the existing, single place the application layer already inspects.

---

## 6. Detailed Design

### 6.1 `vidbyte/agents/pricing/records.py`

**File(s):** `vidbyte/agents/pricing/records.py`
**Type:** Modified

#### What it does
Defines the priced-record and rollup dataclasses shared between `UsageTracker` and its consumers.

#### Interface / API
```python
class UsageRecordingIntegrity(str, Enum):
    INTACT = "intact"
    CORRUPTED = "corrupted"
```
`UsageRollup` (existing dataclass) gains one field:
```python
recording_integrity: UsageRecordingIntegrity = UsageRecordingIntegrity.INTACT
```

#### Logic / Algorithm
No behavior in this file — it is a type/dataclass definition. `UsageRecordingIntegrity` follows the existing `str, Enum` pattern used elsewhere in the pricing package (matches `records.py`'s own style once read in full during implementation) so it serializes the same way sibling enums do.

#### Edge Cases & Error Handling
N/A — pure data definition.

### 6.2 `vidbyte/agents/pricing/tracker.py`

**File(s):** `vidbyte/agents/pricing/tracker.py`
**Type:** Modified

#### What it does
Accumulates priced usage records for one agent run and folds them into a `UsageRollup`.

#### Interface / API
```python
class UsageTracker:
    def mark_recording_corrupted(self) -> None: ...
    @property
    def recording_corrupted(self) -> bool: ...
```
`record_call` and `rollup` keep their existing signatures.

#### Logic / Algorithm
1. `__init__` gains `self._recording_corrupted: bool = False`.
2. `mark_recording_corrupted()` sets it to `True`. Idempotent — calling it more than once in a run is harmless.
3. `record_call` wraps the `_parse_usage(provider, payload)` call in its own `try/except Exception`; on exception, call `self.mark_recording_corrupted()` and `return None` (matching today's return value for the legitimate-skip path — see Section 13 for why the return value itself is not widened).
4. `_parse_usage` loses its `try/except Exception: return None` around `usage_cls.from_usage_payload(payload)` — it now either returns a parsed `ProviderUsage`, returns `None` for a legitimate "nothing to parse" case (unknown provider, non-mapping payload, no parser class — unchanged), or lets a genuine parse exception propagate to its one caller, `record_call`.
5. `rollup()` reads `self._recording_corrupted` and sets `UsageRollup.recording_integrity` accordingly.
6. `reset()` clears `self._recording_corrupted` back to `False` alongside the existing ledger clears, so a reused tracker starts each run intact.

#### Edge Cases & Error Handling
- A run with zero operations and zero model calls still reports `INTACT` (nothing was corrupted, nothing was recorded — this is today's existing empty-run behavior via `cost_complete`, unaffected).
- Multiple independent failures across a run (one bad operation, one bad model call) still resolve to a single `CORRUPTED` flag — this is a boolean gate, not a count, matching the granularity the application layer actually needs (fail the run, don't try to bill partial confidence).
- `_as_provider`'s existing `except (ValueError, TypeError): return None` is untouched — an unrecognized provider string is not routed through `mark_recording_corrupted()`.

### 6.3 `vidbyte/agents/runtime.py`

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
`_record_operation_usage` records one priced search/fetch operation per billable attempt after a tool call completes.

#### Interface / API
No signature change — still `def _record_operation_usage(self, tool: object, call: ToolCall, result: ToolResult) -> None`.

#### Logic / Algorithm
The `except Exception:` arm gains one line before its existing `return`:
```python
except Exception:
    self.usage_tracker.mark_recording_corrupted()
    return
```
The early return for `not isinstance(tool, PricedOperationTool)` (a legitimate "this tool isn't billable" case) is unchanged and does not call `mark_recording_corrupted()`.

#### Edge Cases & Error Handling
- A tool that isn't a `PricedOperationTool` at all still returns cleanly with no corruption flag — this path never reached real vendor spend.
- A tool that *is* priced but whose `_billable_attempts` returns `0` (no attempts to bill) also does not corrupt anything — the loop body never executes and no exception can be raised from inside it in that case.
- The corruption flag is set even if only one of several `record_operation` calls inside the `for _ in range(attempts):` loop fails — a partial loop failure is treated the same as a total one, since the alternative (tracking which specific attempt failed) adds complexity the application layer's binary fail-fast decision doesn't need.

---

## 7. Data Model Changes

N/A — `UsageRollup` is an in-memory dataclass crossing the SDK/application boundary once per agent turn; it is not persisted directly to any datastore (confirmed via the `vidbyte` repo's `research-usage-tracking.md` field guide: `HarnessRun.usage` stays a bounded aggregate and never stores raw SDK rollup/record objects). No migration, no backfill, no legacy-shape concern.

---

## 8. API Changes

N/A — this is a Python library with no HTTP surface. Public interface changes are additive only:
- New enum `UsageRecordingIntegrity` exported from `vidbyte.agents.pricing.records`.
- New field `UsageRollup.recording_integrity` with a default, so existing construction call sites (if any exist outside this package) do not break.
- New method `UsageTracker.mark_recording_corrupted()` and property `UsageTracker.recording_corrupted`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/pricing/records.py` | Add `UsageRecordingIntegrity` enum and `UsageRollup.recording_integrity` field |
| MODIFY | `vidbyte/agents/pricing/tracker.py` | Add corruption flag/method; relocate `record_call`'s exception boundary from `_parse_usage` |
| MODIFY | `vidbyte/agents/runtime.py` | Mark corruption in `_record_operation_usage`'s except arm |

---

## 10. Dependencies & External Services

N/A — no new dependencies, no external service calls.

---

## 11. Rollout & Deployment

No feature flag needed — this is purely additive at the SDK level (new field with a safe default, new method) and changes no return type any existing caller depends on. The behavior change (previously-silent failures now set a flag) only becomes consequential once the `vidbyte` repo's separate PR reads `recording_integrity` and acts on it; until that PR merges and re-pins its `vidbyte-sdk` dependency to a commit including this change, this SDK change is inert from the application's perspective. Sequencing: this PR merges to `vidbyte-sdk` main first; the `vidbyte` repo's companion PR then pins to this commit.

---

## 12. Open Questions

- [x] Should the corruption flag distinguish *which* operation/call failed (for richer alerting), or is a single boolean sufficient? Resolved: single boolean — the application layer's response (fail the run, alert) is the same regardless of which specific record was lost, and the existing `HarnessObservability.exception()` call the application layer already makes on this path can carry richer context if needed later.
- [ ] Should `_billable_attempts` failing (as opposed to failing inside the loop) be distinguished from a mid-loop failure? Not resolved — both currently hit the same `except Exception:` arm and are treated identically. Flagging in case future telemetry wants to split them.

---

## 13. Alternatives Considered

### Alternative 1: Widen `record_call` / `_record_operation_usage` to return an explicit outcome enum
- What: Change both functions' return types to something like `UsageRecordingOutcome { RECORDED, NOT_APPLICABLE, RECORDING_FAILED }` instead of using a tracker-level side-effect flag.
- Why rejected: Every existing call site of both functions already discards the return value and only the end-of-turn `rollup()` is inspected by the application layer. Widening the signature is a larger, more invasive change (touches every call site's type expectations) for no behavioral gain over a tracker-level flag that's already reachable from both functions. Kept as a documented alternative in case a future need for per-call-site outcome inspection arises.

### Alternative 2: Reuse `cost_complete` for this signal instead of a new field
- What: On a swallowed exception, still append a record with `cost_usd=None`, which already flips `cost_complete` to `False`.
- Why rejected: Both bugs can be thrown by the exact accessor that would supply the record's own fields (`tool.units_used()`, `usage_cls.from_usage_payload()`), so there often isn't a safe, honest set of fields to construct a placeholder record from. It also conflates two operationally different situations — "we don't have a rate for this yet" (a product/config gap) and "our own code threw while metering a real charge" (a defect that should page someone) — under one flag, losing the ability to alert on them differently.

### Alternative 3: Refactor `pricing/tracker.py`'s module-level helpers into a class-bound helper
- What: The field guide's `class-bound-helpers.md` prefers a single `@staticmethod`-based class over a wall of related free functions (`_parse_usage`, `_as_provider`, `_is_billable_key`, `_reported_or_table_cost`, `_sum_or_none`).
- Why rejected (for this PR): The approved design for this fix is a narrow, surgical change to two specific functions. Folding in the three unrelated helper functions widens the diff well beyond the bug being fixed and risks obscuring the actual fix in an unrelated style refactor. Noted here explicitly, per the field guide's own instruction, so the deferral is a visible decision rather than an oversight — worth a dedicated follow-up PR if the pattern keeps drawing review comments.
