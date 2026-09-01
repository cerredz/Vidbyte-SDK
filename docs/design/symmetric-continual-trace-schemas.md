# Design Doc: Symmetric Continual Trace Schemas

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-31
**Last Updated:** 2026-08-31

---

## 1. Overview

Add six new prebuilt continual-trace schemas to `vidbyte/trace/continual/prebuilt.py`, alongside the existing `ActionTrace`. Each schema keeps three evaluation axes — goal success, path quality, and answer correctness — as structurally separate, equally-decomposed field groups that are never averaged into one blended score, mirroring the independent-scoring pattern several agent platforms (Snowflake, Salesforce, Palantir, ServiceNow, AWS) have converged on. The six schemas vary the *shape* used to express that separation (flat current-value fields, checklists, independent sub-metrics, event logs, timelines, and evidence-for/against ledgers) while holding the three-axis split fixed as the one structural invariant across all of them.

---

## 2. Goals & Non-Goals

### Goals
- Add six new `TraceSchema` constants (with backing `pydantic.BaseModel` classes) to `vidbyte/trace/continual/prebuilt.py`, following the `ActionTrace`/`ActionTraceModel` naming and construction pattern exactly.
- Export all six from `vidbyte/trace/continual/__init__.py`, `vidbyte/trace/__init__.py`, and `vidbyte/__init__.py`, matching how `ActionTrace` is already exported at each layer.
- Every field on every schema type-maps correctly through `TraceSchema.from_model` (`vidbyte/lib/dataclasses/trace.py:_annotation_to_type`) to the intended `TraceFieldType`, and every array field that is meant to accumulate history is a genuine top-level `ARRAY` field (not a list nested inside an `OBJECT` field, which the real merge implementation would silently overwrite rather than append to).
- Cover this with both a `unittest` module (matching `tests/test_continual_trace.py`) and a standalone verification script (matching `scripts/test-continual-trace.py`), per this repository's established pairing.

### Non-Goals
- No changes to `UpdateTraceTool`, `ContinualTraceMiddleware`, `ContinualTraceAgent`, or any other continual-trace runtime code — this is additive schema data only.
- No changes to the existing `ActionTrace`/`ActionTraceModel`.
- No new merge semantics, no new `TraceFieldType` values, no changes to `vidbyte/lib/dataclasses/trace.py` or `vidbyte/tools/continual_trace.py`.
- No YAML-config-loader wiring (`ContinualTraceAgentDescriptor`) — these schemas are consumed the same way `ActionTrace` is, via `TraceOption.continual(SomeTrace)` in Python.

---

## 3. Background & Context

The continual-trace subsystem (`skills/vidbyte-sdk/continual-tracing.md`) lets an agent construction option (`trace_option=TraceOption.continual(schema)`) attach a dedicated sub-agent that fills a typed, JSON-like artifact describing a running agent's work, without that artifact ever entering the main agent's context window. Today the only prebuilt schema is `ActionTrace` — four fields (`goal`, `actions_taken`, `mistakes`, `current_status`) with no structural separation between "did the agent succeed," "was the process good," and "are the claims correct."

A separate design conversation (not part of this repo) worked through what a family of schemas enforcing that three-way separation should look like, and iterated based on two corrections:
1. Every axis must get equal structural weight — no schema where one axis is decomposed into a rich array while the other two are left as thin placeholder fields.
2. Any field meant to grow over the life of a run must be declared as a top-level `ARRAY` field. A list nested inside an `OBJECT` field does not accumulate: `UpdateTraceTool._merge_field` (`vidbyte/tools/continual_trace.py:154-164`) does `base = dict(previous); base.update(dict(incoming))` for `OBJECT` fields — a one-level shallow merge — so a nested list inside that object gets replaced wholesale on every pass that touches the object, not appended to. Only fields whose own declared type is `ARRAY` get `_append_unique` treatment.

This design doc formalizes that iteration into six concrete schemas ready to add to the codebase.

---

## 4. Requirements

### Functional Requirements
1. `vidbyte/trace/continual/prebuilt.py` gains six new `pydantic.BaseModel` subclasses and six new `TraceSchema` module-level constants, built via `TraceSchema.from_model(...)`, following the exact pattern of `ActionTraceModel`/`ActionTrace`.
2. Every field on every new model has a non-empty `Field(description=...)` (required by `TraceSchema.from_model`, `vidbyte/lib/dataclasses/trace.py:88-89`).
3. Every field's Python type annotation maps to the intended `TraceFieldType` per `_annotation_to_type`: `str` → `STRING`, `float` → `NUMBER`, `int` → `INTEGER`, `bool` → `BOOLEAN`, `list[...]` → `ARRAY`, `dict[str, Any]` → `OBJECT`. No field uses a nested `BaseModel` type (which `_annotation_to_type` does not recognize and would silently degrade to `STRING`).
4. Each of the six schemas organizes its fields into exactly three axis groups — goal success, path quality, answer correctness — with the same field count and shape in each group within that schema.
5. All six new names are exported from `vidbyte/trace/continual/__init__.py`, `vidbyte/trace/__init__.py`, and `vidbyte/__init__.py` (both the import block and `__all__`), in the same alphabetized position pattern already used for `ActionTrace`.
6. `TraceOption.continual(<any of the six schemas>)` succeeds and produces a working option (exercised by tests).

### Non-Functional Requirements
- No runtime behavior change to existing agents that don't opt into one of the new schemas (purely additive).
- No performance requirement beyond what `TraceSchema.from_model` already costs at import time (schema construction is O(field count), negligible).
- Observability: none needed beyond what the continual-trace subsystem already provides (`trace_metadata` in `reply.metadata`).
- Reliability: because these are pure data/schema definitions with no I/O, the main reliability requirement is correctness of the type mapping and the merge-accumulation properties, both covered by the testing plan.

---

## 5. High-Level Design

`vidbyte/trace/continual/prebuilt.py` currently exports one `(Model, TraceSchema)` pair. This change adds six more pairs to the same file, with no change to how any of them is consumed — a caller still does `TraceOption.continual(SymmetricFlatTrace, every_n_iterations=5)` exactly as they would with `ActionTrace` today. The data flow is unchanged:

```
Agent(trace_option=TraceOption.continual(SymmetricFlatTrace))
        |
        v
ContinualTraceMiddleware (unchanged) -- schedules updates at the configured interval
        |
        v
ContinualTraceAgent (unchanged) -- fills the schema via UpdateTraceTool (unchanged)
        |
        v
reply.metadata["trace"]  -- the accumulated artifact, shaped by whichever schema was chosen
```

The six schemas differ only in field shape, chosen to cover six different ways a developer might want to consume a three-axis trace:

| # | Schema | Shape per axis | When to reach for it |
|---|--------|-----------------|------------------------|
| 1 | `SymmetricFlatTrace` | status + confidence + evidence[] + rationale (4 fields) | Default drop-in; current-value read on each axis |
| 2 | `SymmetricChecklistTrace` | growing array of `{criterion, met, evidence, iteration}` | Rubric-style, many named criteria per axis |
| 3 | `SymmetricSubScoreTrace` | three independent 0-1 float metrics | Numeric dashboards; still never averaged |
| 4 | `SymmetricEventLedgerTrace` | growing array of axis-specific events | Full audit trail per axis |
| 5 | `SymmetricTimelineTrace` | growing array of per-pass snapshots | Trend-over-time per axis |
| 6 | `SymmetricEvidenceTrace` | supporting[] + contradicting[] + verdict (3 fields) | Evidence-weighed verdict per axis |

Every array field in schemas 2, 4, and 5 carries its own `iteration` key inside each entry, making each array an event log rather than a mutable row table — consistent with the `_append_unique` dedupe-only-exact-repeats behavior documented in Section 3.

---

## 6. Detailed Design

### 6.1 `vidbyte/trace/continual/prebuilt.py`

**File(s):** `vidbyte/trace/continual/prebuilt.py`
**Type:** Modified (six new model/schema pairs appended; existing `ActionTrace`/`ActionTraceModel` untouched)

#### What it does
Declares six additional typed continual-trace schemas, each enforcing a three-way axis separation via field naming and grouping, converted to `TraceSchema` instances at module load time.

#### Interface / API

```python
from typing import Any
from pydantic import BaseModel, Field
from vidbyte.lib.dataclasses.trace import TraceSchema


class SymmetricFlatTraceModel(BaseModel):
    """Three axes, each given the identical four-field shape: status, confidence, evidence, rationale."""

    goal_success_status: str = Field(description="...")
    goal_success_confidence: float = Field(description="...")
    goal_success_evidence: list[str] = Field(default_factory=list, description="...")
    goal_success_rationale: str = Field(description="...")

    path_quality_status: str = Field(description="...")
    path_quality_confidence: float = Field(description="...")
    path_quality_evidence: list[str] = Field(default_factory=list, description="...")
    path_quality_rationale: str = Field(description="...")

    answer_correctness_status: str = Field(description="...")
    answer_correctness_confidence: float = Field(description="...")
    answer_correctness_evidence: list[str] = Field(default_factory=list, description="...")
    answer_correctness_rationale: str = Field(description="...")


SymmetricFlatTrace = TraceSchema.from_model(
    SymmetricFlatTraceModel, name="symmetric_flat_trace",
    description="Goal success, path quality, and answer correctness as three parallel current-value reads.",
)

# ... five more (Model, TraceSchema) pairs of the same construction shape:
#   SymmetricChecklistTraceModel / SymmetricChecklistTrace
#   SymmetricSubScoreTraceModel / SymmetricSubScoreTrace
#   SymmetricEventLedgerTraceModel / SymmetricEventLedgerTrace
#   SymmetricTimelineTraceModel / SymmetricTimelineTrace
#   SymmetricEvidenceTraceModel / SymmetricEvidenceTrace
```

The full field lists (with production-quality 4-5 sentence descriptions per field, matching the bar set by `ActionTraceModel` and the continual-tracing skill's explicit "4–5 sentence description" guidance) are:

**`SymmetricChecklistTraceModel`** — `goal_success_checks`, `path_quality_checks`, `answer_correctness_checks`, each `list[dict[str, Any]]` holding `{criterion: str, met: bool, evidence: str, iteration: int}` entries.

**`SymmetricSubScoreTraceModel`** — `goal_intent_alignment`, `goal_constraint_satisfaction`, `goal_completion_pct`, `path_efficiency`, `path_safety`, `path_plan_adherence`, `correctness_grounding`, `correctness_consistency`, `correctness_completeness`, all `float` in `[0, 1]`.

**`SymmetricEventLedgerTraceModel`** — `goal_success_events` (`{iteration, subgoal_id, status, description}`), `path_quality_events` (`{iteration, step_id, action, risk_flag}`), `answer_correctness_events` (`{iteration, claim_id, claim_text, verified}`), all `list[dict[str, Any]]`.

**`SymmetricTimelineTraceModel`** — `goal_success_timeline` (`{iteration, status, confidence, note}`), `path_quality_timeline` (`{iteration, efficiency, risky_action_count, note}`), `answer_correctness_timeline` (`{iteration, verified_claim_count, contradiction_count, note}`), all `list[dict[str, Any]]`.

**`SymmetricEvidenceTraceModel`** — `goal_success_supporting`/`goal_success_contradicting` (`list[str]`) + `goal_success_verdict` (`str`); same triad for `path_quality_*` and `answer_correctness_*`.

#### Logic / Algorithm
1. Define each `BaseModel` subclass with axis-prefixed field names (`goal_*`, `path_*`/`path_quality_*`, `correctness_*`/`answer_correctness_*`) so field grouping is visible from the name alone.
2. Give every field a `Field(description=...)` long enough to guide the trace agent (2-4 sentences: what it captures, its independence from the other axes, its replace-vs-append merge behavior, and — for `status`/`verdict` fields — the closed set of allowed string values).
3. Convert each model with `TraceSchema.from_model(Model, name="snake_case_name", description="one sentence")`, matching the `ActionTrace` call shape exactly.
4. Add all twelve new names (6 models + 6 schemas) to the file's `__all__`.

#### Edge Cases & Error Handling
- A field with no description raises `ValueError` at import time via `TraceSchema.from_model` (`vidbyte/lib/dataclasses/trace.py:88-89`) — covered by writing a description for every field, verified by a test that asserts no exception on import.
- A `dict[str, Any]` field's runtime value must be a `Mapping` and a `list[...]` field's must be a `Sequence`, enforced by `UpdateTraceTool._value_matches_type` at call time — not testable at schema-definition time, but the schema's declared types are asserted directly against `TraceFieldType`.
- No field collides in name across schemas or within a schema (verified by asserting `len(schema.fields) == len(set(schema.fields))`, which is structurally guaranteed by Python class field uniqueness but worth asserting for regression safety).

---

### 6.2 `vidbyte/trace/continual/__init__.py`

**File(s):** `vidbyte/trace/continual/__init__.py`
**Type:** Modified

#### What it does
Re-exports the six new model/schema pairs from `vidbyte.trace.continual.prebuilt`, alongside the existing `ActionTrace`/`ActionTraceModel`.

#### Interface / API
```python
from vidbyte.trace.continual.prebuilt import (
    ActionTrace, ActionTraceModel,
    SymmetricChecklistTrace, SymmetricChecklistTraceModel,
    SymmetricEventLedgerTrace, SymmetricEventLedgerTraceModel,
    SymmetricEvidenceTrace, SymmetricEvidenceTraceModel,
    SymmetricFlatTrace, SymmetricFlatTraceModel,
    SymmetricSubScoreTrace, SymmetricSubScoreTraceModel,
    SymmetricTimelineTrace, SymmetricTimelineTraceModel,
)
```
`__all__` gains the twelve new names, alphabetized alongside the existing four entries.

---

### 6.3 `vidbyte/trace/__init__.py`

**File(s):** `vidbyte/trace/__init__.py`
**Type:** Modified

#### What it does
Re-exports the six new `TraceSchema` constants (not the `*Model` pydantic classes — matching how only `ActionTrace`, not `ActionTraceModel`, is re-exported at this layer, per the existing import at line 25 and `__all__` at line 32).

#### Interface / API
```python
from vidbyte.trace.continual import (
    ActionTrace, ContinualTraceAgent, ContinualTraceMiddleware, ContinualTracer,
    SymmetricChecklistTrace, SymmetricEventLedgerTrace, SymmetricEvidenceTrace,
    SymmetricFlatTrace, SymmetricSubScoreTrace, SymmetricTimelineTrace,
)
```
`__all__` gains the six schema names in alphabetical position.

---

### 6.4 `vidbyte/__init__.py`

**File(s):** `vidbyte/__init__.py`
**Type:** Modified

#### What it does
Re-exports the six new `TraceSchema` constants at the top-level package surface, matching the existing `ActionTrace` re-export at line 316 (import block) and line 517 (`__all__`).

#### Interface / API
```python
from vidbyte.trace import (
    ActionTrace, ContinualTraceAgent, ContinualTraceMiddleware, ContinualTracer,
    DebugTracer, ParentPolicy, SemanticSpanContext, SessionTraceController, SessionTracer,
    SymmetricChecklistTrace, SymmetricEventLedgerTrace, SymmetricEvidenceTrace,
    SymmetricFlatTrace, SymmetricSubScoreTrace, SymmetricTimelineTrace,
    ...
)
```
`__all__` gains the six names next to the existing `"ActionTrace"` entry (line 517).

#### Edge Cases & Error Handling
N/A — pure re-export wiring; no new failure modes beyond what already exists for `ActionTrace`.

---

## 7. Data Model Changes

N/A — no database or persistent schema is touched. `TraceSchema` instances are in-process Python configuration objects, not stored records.

---

## 8. API Changes

N/A — no HTTP/RPC endpoints exist in this SDK layer. The only "API" surface is the Python import surface covered in Section 6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/trace/continual/prebuilt.py` | Add six new `BaseModel`/`TraceSchema` pairs |
| MODIFY | `vidbyte/trace/continual/__init__.py` | Export the six new pairs |
| MODIFY | `vidbyte/trace/__init__.py` | Export the six new `TraceSchema` constants |
| MODIFY | `vidbyte/__init__.py` | Export the six new `TraceSchema` constants at top level |
| CREATE | `tests/test_symmetric_continual_traces.py` | `unittest` coverage per Section 10 |
| CREATE | `scripts/test-symmetric-continual-traces.py` | Standalone verification script per Phase 5 |

---

## 10. Testing Plan

### Unit Tests
- `describe('SymmetricFlatTrace')` -> `it('has exactly 12 fields, 4 per axis, all present in the model')` — [Hidden Assumption] (catches accidental field drop/typo across the three axis groups)
- `describe('SymmetricFlatTrace')` -> `it('types confidence fields as NUMBER and evidence fields as ARRAY')` — [Silent Failure] (catches a field silently degrading to STRING because of a wrong annotation, e.g. a stray nested BaseModel)
- `describe('SymmetricChecklistTrace')` -> `it('types all three *_checks fields as ARRAY')` — [Silent Failure]
- `describe('SymmetricSubScoreTrace')` -> `it('has exactly 9 fields, 3 per axis, all typed NUMBER')` — [Hidden Assumption]
- `describe('SymmetricEventLedgerTrace')` -> `it('has exactly 3 fields, all typed ARRAY')` — [Edge Case] (smallest field count of the six; verifies the minimum shape still holds three axes)
- `describe('SymmetricTimelineTrace')` -> `it('has exactly 3 fields, all typed ARRAY')` — [Edge Case]
- `describe('SymmetricEvidenceTrace')` -> `it('has exactly 9 fields, 3 per axis, with 2 ARRAY + 1 STRING per axis')` — [Hidden Assumption]
- `describe('all six schemas')` -> `it('construct without raising, proving every field has a non-empty description')` — [Hidden Failure] (a missing description raises at `TraceSchema.from_model` call time, which happens at module import — this catches a bad edit that isn't otherwise exercised until something imports `vidbyte.trace`)
- `describe('all six schemas')` -> `it('produce an initial_artifact() with every declared key set to None')` — [Edge Case]
- `describe('TraceOption.continual')` -> `it('accepts each of the six schemas and reports enabled=True')` — [Edge Case]
- `describe('UpdateTraceTool')` -> `it('accumulates SymmetricEventLedgerTrace.goal_success_events across two calls instead of replacing it')` — [Silent Failure] (this is the exact bug class identified in Section 3 — a regression here would mean an ARRAY field was accidentally declared as OBJECT or vice versa)
- `describe('UpdateTraceTool')` -> `it('appends distinct entries to SymmetricChecklistTrace.path_quality_checks across three calls with different criterion values')` — [Silent Failure]
- `describe('UpdateTraceTool')` -> `it('replaces SymmetricFlatTrace.goal_success_status in place rather than accumulating it')` — [Hidden Assumption] (proves scalar fields still replace, i.e. the schema author didn't accidentally type a status field as ARRAY to get accumulation)
- `describe('module import')` -> `it('exposes no duplicate field names across the six new schemas and ActionTrace when imported together')` — [Hidden Failure] (six schemas sharing a module is a plausible place for a copy-paste field-name collision to slip in un-noticed since each schema validates independently)

### Integration Tests
- End-to-end: build an `Agent` with `trace_option=TraceOption.continual(SymmetricEventLedgerTrace, every_n_iterations=1)` against the existing `ScriptedRunner` pattern from `tests/test_continual_trace.py`, run it, and assert `reply.metadata["trace"]["goal_success_events"]` accumulated entries from multiple simulated passes and that `reply.metadata["trace_metadata"]["update_count"] >= 2`. Mocks: `ScriptedRunner` (already established in-repo, no new external dependency). This is the flow most likely to hide a silent failure — a schema that validates fine in isolation but never actually receives updates because of a subtle shape mismatch in what the trace agent tool call sends.
- Confirm none of the six schemas ever cause trace content to leak into `runner.main_payloads` (mirrors `test_trace_never_leaks_into_main_context`), since a new schema with large nested dicts is exactly the kind of change that could tempt a future refactor to inline trace content into the main prompt — this test guards the existing invariant against that specific new schema's use.
- Hidden assumption the integration surface reveals that unit tests can't: `TraceSchema.from_model` runs at **module import time**, not at usage time — so a bad field on any of the six schemas would break importing `vidbyte` entirely, not just fail when that specific schema is used. The integration test's mere ability to `from vidbyte import SymmetricFlatTrace, ...` (alongside every other top-level symbol) is itself a real assertion, not boilerplate.

### Manual / QA Test Cases
1. Given a fresh Python REPL with the SDK installed in editable mode, when running `from vidbyte import SymmetricFlatTrace, SymmetricChecklistTrace, SymmetricSubScoreTrace, SymmetricEventLedgerTrace, SymmetricTimelineTrace, SymmetricEvidenceTrace`, then all six import with no exception — [Hidden Failure]
2. Given `SymmetricSubScoreTrace.describe_fields()`, when printed, then all nine field descriptions render legibly with no `None` or empty description — [Edge Case]
3. Given an `Agent` constructed with `trace_option=TraceOption.continual(SymmetricChecklistTrace, every_n_iterations=1)` run against a real provider (manual smoke test, not part of CI), when the run completes, then `reply.metadata["trace"]["goal_success_checks"]` contains at least one well-formed entry with `criterion`/`met`/`evidence`/`iteration` keys — [Silent Failure] (the schema could be well-typed yet still guide the trace agent to write malformed dict shapes, which nothing in the type system catches since `dict[str, Any]` accepts any mapping)

---

## 11. Dependencies & External Services

N/A — no new dependencies; uses only `pydantic` (already a core dependency, see `pyproject.toml`) and existing SDK internals.

---

## 12. Rollout & Deployment

- No feature flag — this is purely additive; nothing existing changes behavior.
- Not a breaking change; no migration path needed.
- Single-repo change (`vidbyte-sdk`), no deployment ordering concerns with other repos.
- Rollback: revert the PR; nothing else in the codebase will have taken a dependency on the six new names by the time this ships (Non-Goals explicitly excludes wiring them into any other subsystem).

---

## 13. Open Questions

- [ ] Should any of the six schemas eventually get a corresponding YAML-loadable `ContinualTraceAgentDescriptor` entry point? Out of scope here (see Non-Goals) — flagged for a follow-up if a YAML-config consumer wants one of these schemas.
- [ ] Should `describe_fields()` output for the two largest schemas (`SymmetricFlatTrace` at 12 fields, `SymmetricEvidenceTrace`/`SymmetricSubScoreTrace` at 9) be truncated or restructured for prompt-length reasons once used with a real trace agent at scale? No evidence of a problem yet; noted for follow-up if trace-agent prompt size becomes a concern.

---

## 14. Alternatives Considered

### Alternative 1: Nest each axis under one `OBJECT` field instead of flat/prefixed names
- What: `goal_success: dict[str, Any]`, `path_quality: dict[str, Any]`, `answer_correctness: dict[str, Any]`, each holding the axis's sub-fields as dict keys.
- Why rejected: any list nested inside an `OBJECT` field is silently overwritten rather than appended on each update (Section 3) — this breaks every schema here that needs history to accumulate (checklist, event ledger, timeline). Flat, axis-prefixed top-level fields sidestep the bug entirely and were confirmed correct against the actual merge implementation.

### Alternative 2: One combined schema with all six shapes as optional sub-sections
- What: a single very large `TraceSchema` with ~50+ fields covering every shape at once.
- Why rejected: defeats the purpose of offering six distinct shapes for six distinct consumption patterns; also risks tripping the YAML-loader's `_MAX_SCHEMA_KEYS = 50` ceiling (`vidbyte/lib/dataclasses/continual_trace_descriptor.py:27`) if ever loaded that way, even though this design doesn't currently wire YAML loading for these schemas.

### Alternative 3: Upsert-by-id semantics for event/checklist arrays
- What: give ledger entries a stable id and have the trace agent "update" an existing entry by id instead of always appending a new one.
- Why rejected: `UpdateTraceTool._append_unique` has no upsert-by-key behavior and changing it is explicitly out of scope (Non-Goals) — it's shared runtime code used by `ActionTrace` and any other schema, not something to special-case for six new schemas. The event-log convention (append a new entry per change, tagged with `iteration`) works within the existing merge contract instead of requiring a change to it.
