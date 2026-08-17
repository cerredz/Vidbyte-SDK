# Design Doc: CoT Monitoring Tools — Batch 2

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-17
**Last Updated:** 2026-08-17

---

## 1. Overview

Adds six more model-callable chain-of-thought monitoring tools to the deep
CoT event family introduced in `docs/design/deep-cot-tools.md`: `prediction`
(forward-looking falsifiable forecasts with a resolution trigger), `goal_check`
(goal-drift attestation), `counterfactual` (branch hindsight), `assumptions`
(periodic snapshot of everything currently being taken as true), `failures`
(premortem scan of what could go wrong at the current stage), and `why`
(retrospective on the rationale behind actions taken so far). As with batch 1,
the core value is the parameter descriptions; parsed enums/confidences land in
`ToolResult.metadata` for observability charting. This PR is **stacked on
`feat/deep-cot-tools` (PR #337)** because it reuses `CotEventParser`,
`_CotEventToolBase`, and the batch-1 primitives module.

---

## 2. Goals & Non-Goals

### Goals
- Six new tools in `vidbyte/tools/builtins/cot_events.py`, reusing
  `CotEventParser` and `_CotEventToolBase` from batch 1.
- Six new frozen-dataclass primitives in
  `vidbyte/context/primitives/cot_events.py`, following the batch-1 rendering
  pattern.
- Explicit, coercive tool and parameter descriptions (the deliverable).
- Snapshot semantics for `assumptions` and `failures` (fixed primitive_id,
  latest replaces prior); append-only for `prediction`, `goal_check`,
  `counterfactual`, `why`.

### Non-Goals
- No automatic prediction resolution (hit/miss scoring) — monitors resolve
  against outcomes; this PR only emits the records.
- No changes to trace schemas, algorithms, middleware, or runtime.
- No new files beyond extending the two batch-1 modules and their exports.

---

## 3. Background & Context

Batch 1 shipped five atomic reasoning-event tools (hypothesis, decision,
assumption_check, uncertainty, backtrack). The follow-up brainstorm produced
ten candidates; grounding in current research (CoT faithfulness: Anthropic
Apr 2025 / arXiv:2507.11473; verbalized calibration: arXiv:2305.14975;
process-vs-outcome evaluation: AgentBoard arXiv:2401.13178; long-horizon
drift: METR arXiv:2503.14499) plus the user's own ideas selected six.
`counterfactual` is included by explicit user choice despite the faithfulness
literature's caution about post-hoc narration — the record is offered as
model-authored hindsight, not ground truth, and the description says so.

---

## 4. Requirements

### Functional Requirements
1. Each tool is a `BaseTool` subclass (via `_CotEventToolBase`) with a
   "use this when..." trigger opening its description and per-parameter
   descriptions stating format, terseness, and semantics.
2. Required-string and enum validation via `CotEventParser`, identical error
   behavior to batch 1 (missing/blank → error naming field; bad enum → error
   listing allowed values; optional confidence coerced/clamped, `None` on
   failure).
3. `prediction.confidence` is **required** and must parse to [0,1].
4. `assumptions.assumptions` is a JSON array of 1–10 non-empty strings.
5. `failures.failures` is a JSON array of 1–5 objects, each with a non-empty
   `failure` key and an optional `likelihood` validated against
   `high|medium|low` (default `medium`); invalid likelihood → error listing
   allowed values.
6. Every successful execute upserts exactly one primitive and returns
   `ToolResult.success` with parsed fields in `metadata`.
7. Snapshot tools use fixed primitive ids (`assumptions:current`,
   `failures:current`); append-only tools use counter ids (`<name>:<n>`).
8. All six tool classes and six primitive classes exported from
   `vidbyte.tools.builtins` and `vidbyte.context.primitives`.

### Non-Functional Requirements
- Zero new dependencies.
- Primitive renders bounded by `max_chars = 2000`.
- Enum tuples and bounds as named module constants.
- No inline magic values.

---

## 5. High-Level Design

Same architecture as batch 1 — this is an extension, not a new mechanism:

```
Model emits tool call -> runtime -> <Event>Tool.execute
  -> CotEventParser.* (validate/coerce)
  -> frozen primitive -> ContextManager.upsert
  -> ToolResult.success(text=render, metadata=parsed fields)
```

ID policy split: `prediction`, `goal_check`, `counterfactual`, `why` are
append-only event records (counter ids, time-series chartable);
`assumptions` and `failures` describe the *current* state (fixed
`<name>:current` ids, so the newest call replaces the previous snapshot —
matching their "current" semantics in the descriptions).

---

## 6. Detailed Design

### 6.1 `PredictionTool` (name: `prediction`)
Params: `predicts*` string (one falsifiable sentence about what will happen),
`by_when*` string (the observable trigger that resolves it — next call, next
N steps, end of run), `confidence*` number 0–1 (forecast, not feeling).
Primitive `PredictionContextItem` (predicts/by_when/confidence). Metadata:
`confidence`. Append-only.

### 6.2 `GoalCheckTool` (name: `goal_check`)
Params: `original_goal*` string (verbatim restatement — restating verbatim is
the drift test), `current_activity*` string (what you are doing right now),
`still_serves*` enum `directly|indirectly|no`, `pivot_to` optional string
(required semantically when `still_serves=no`). Primitive
`GoalCheckContextItem`. Metadata: `still_serves`. Append-only (drift time
series).

### 6.3 `CounterfactualTool` (name: `counterfactual`)
Params: `outcome*` string (what actually happened), `alternative*` string
(the branch not taken), `would_have*` string (predicted outcome of the
alternative), `confidence` optional number, `lesson` optional string.
Primitive `CounterfactualContextItem`. Metadata: `confidence`. Append-only.
Description explicitly frames the record as the model's own hindsight, which
may be post-hoc rationalization.

### 6.4 `AssumptionsTool` (name: `assumptions`)
Params: `assumptions*` JSON array of 1–10 non-empty strings (everything
currently being taken as true, each one checkable fact), `scope` optional
string (what part of the run these concern). Primitive
`AssumptionsSnapshotContextItem` (renders the list). Metadata: `count`.
Snapshot id `assumptions:current`. Distinct from `assumption_check` (single
ledger entry with declared/verified/falsified lifecycle): this is the
periodic dump of the whole current set.

### 6.5 `FailuresTool` (name: `failures`)
Params: `failures*` JSON array of 1–5 objects with keys `failure` (what
could go wrong at the current stage), `likelihood` enum `high|medium|low`
(default `medium`), `mitigation` optional (one clause), `stage` optional
string (what stage of the run this scan describes). Primitive
`FailureScanContextItem`. Metadata: `failure_count`, `likelihoods` tuple.
Snapshot id `failures:current`.

### 6.6 `WhyTool` (name: `why`)
Params: `why*` string (prose: why the actions taken so far were taken —
reasons, not a recap), `reconsider*` enum `none|some|core` (whether examining
the rationale changed anything: none = rationale holds; some = one step
should change; core = the foundational rationale is wrong), `change` optional
string (what to change, required semantically when reconsider != none).
Primitive `WhyContextItem`. Metadata: `reconsider`. Append-only.

### 6.7 Edge Cases & Error Handling
Identical to batch 1: blank required strings, bad enums, bad JSON arrays →
`ToolResult.error`; optional params absent → defaults; `upsert` ValueError
(frozen) → error. New: `failures` entries missing `failure` key or with
invalid `likelihood` → error naming the entry index and allowed values.

---

## 7. Data Model Changes

N/A - In-memory context primitives only.

---

## 8. API Changes

N/A - Additive Python exports only.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/tools/builtins/cot_events.py` | Six new tool classes |
| MODIFY | `vidbyte/context/primitives/cot_events.py` | Six new primitives |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export the six tools |
| MODIFY | `vidbyte/context/primitives/__init__.py` | Export the six primitives |

0 created, 4 modified, 0 deleted. **Stacked on `feat/deep-cot-tools` (PR #337).**

---

## 10. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| stdlib `json`, `hashlib` | Python 3.11+ | Parsing, batch-1 helpers | None |

---

## 11. Rollout & Deployment

Additive; opt-in via `with_tools(...)`. Rollback = revert. Merge order: PR
#337 first, then this PR (rebased automatically by GitHub's stacked diff).

---

## 12. Open Questions

- [ ] None blocking. Prediction auto-resolution (hit/miss scoring in a
  monitor) is a deliberate follow-up, not part of this PR.

---

## 13. Alternatives Considered

### Alternative 1: New module for batch 2
- What: `cot_events_2.py` for the six tools.
- Why rejected: Same shared parser/base; one module per concern matches the
  class-bound-helpers rule and keeps the family in one reviewable place.

### Alternative 2: Drop `counterfactual` per faithfulness research
- What: Exclude because post-hoc narration is the least faithful channel.
- Why rejected: User explicitly selected it; description discloses the
  hindsight caveat instead, and the record remains useful as self-report
  telemetry when paired with objective outcome data in the monitor.

### Alternative 3: `assumptions`/`failures` as append-only events
- What: Counter ids, full history retained.
- Why rejected: Their semantics are "the current set" — a history of
  snapshots clutters the context window; the snapshot-replace id keeps
  exactly one current copy model-visible, matching the descriptions.

---

CI gate: `PYTHONPATH=<worktree> python scripts/run_ci.py --stage source`,
then `python scripts/run_ci.py --stage package` without PYTHONPATH
(field-guide: local CI verification).

END OF DESIGN DOC
