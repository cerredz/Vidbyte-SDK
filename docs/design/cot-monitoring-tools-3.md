# Design Doc: CoT Monitoring Tools — Batch 3 (Deep Families)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-17
**Last Updated:** 2026-08-17

---

## 1. Overview

Adds 24 model-callable monitoring tools organized into five deep families:
context-window awareness (4), information-foraging (4), self-verification (4),
inter-agent/handoff epistemics (4 + 2 extras: `subagent_failures`,
`blocked_on`), and meta-monitoring (4 + 2 extras: `calibration_self_report`,
`description_drift`). Each tool is param-rich (4–7 params) by explicit user
direction — more semantic axes per call, not fewer — with descriptions that
drive when/how the model calls them. Parsed enums/numbers land in
`ToolResult.metadata` for trace-side charting. Stacked on
`feat/deep-cot-tools-2` (PR #338); reuses `CotEventParser` and
`_CotEventToolBase` from `vidbyte/tools/builtins/cot_events.py`.

---

## 2. Goals & Non-Goals

### Goals
- 24 new tools across five new per-family modules under
  `vidbyte/tools/builtins/`, one module per family, all subclassing
  `_CotEventToolBase`.
- 24 new frozen primitives across five mirrored modules under
  `vidbyte/context/primitives/`.
- Param-rich specs (bias to more params), descriptions in the batch-1/2 voice:
  trigger sentence, per-param format/terseness rules, honest-use guidance.
- Conditional requirements enforced in code (e.g. `if_no_recover_how` required
  when `still_visible` != yes; `if_disagree` required when `agree` != yes;
  `drift_detail`/`corrective_action` semantics when `matches_memory` != yes).
- ID policy: snapshot ids for current-state tools (`context_load`,
  `ritual_check`, `calibration_self_report`); statement-hash ledger id for
  `blocked_on`; counter ids for the 20 append-only events.

### Non-Goals
- No runtime wiring (no middleware, no auto-resolution of predictions, no
  compaction triggers) — these are records; acting on them belongs to monitors.
- No changes to batch-1/2 tools beyond exporting the shared base.
- No new dependencies.

---

## 3. Background & Context

Batches 1 (#337) and 2 (#338) shipped 11 atomic reasoning-event tools. The
follow-up taxonomy proposed five deeper families; the user selected the first
four of each family plus four named extras. Family rationale (from the
research grounding conversation): context-window awareness monitors the #1
silent failure of long runs (facts falling out of window); information-foraging
makes search a measurable loop (over/under-searching are chronic per METR
long-horizon findings); self-verification is the highest-trust telemetry
because verification acts are checkable in a way narration is not (CoT
faithfulness results); delegation epistemics covers trust transferred without
verification across agent boundaries; meta-monitoring keeps the other families
honest over long runs.

---

## 4. Requirements

### Functional Requirements
1. Every tool subclasses `_CotEventToolBase` (constructor takes
   `ContextManager`) and validates via `CotEventParser`; error behavior
   identical to batches 1–2 (blank required → error naming field; bad enum →
   error listing values; JSON arrays validated as arrays of strings/objects).
2. `queries` (search_plan) is a JSON array of 1–3 objects each with a
   non-empty `query` string and validated `expected_yield` enum.
3. Conditional requirements listed in Goals are enforced with explicit error
   messages.
4. All enum values and bounds are named module constants.
5. Each successful execute upserts exactly one primitive and returns parsed
   fields in `metadata`.
6. All 24 tools exported from `vidbyte.tools.builtins`; all 24 primitives
   from `vidbyte.context.primitives`.
7. Tool names: `context_load`, `attention_check`, `recall_test`,
   `forget_decision`, `search_why`, `search_plan`, `search_yield`, `enough`,
   `verify`, `self_test`, `independently_derived`, `read_back`,
   `delegation_brief`, `delegation_receipt`, `handoff_why`,
   `handoff_completeness`, `subagent_failures`, `blocked_on`,
   `record_dispute`, `ritual_check`, `telemetry_gap`, `signal_highlight`,
   `calibration_self_report`, `description_drift`.

### Non-Functional Requirements
- Zero new dependencies; renders bounded by `max_chars = 2000`.
- Per-family modules keep each file reviewable (< ~600 lines).

---

## 5. High-Level Design

Same execution shape as batches 1–2. New structure only in file layout: one
tools module + one primitives module per family:

```
vidbyte/tools/builtins/        cot_context.py  cot_foraging.py  cot_verification.py
                              cot_delegation.py  cot_meta.py
vidbyte/context/primitives/   cot_context.py  cot_foraging.py  cot_verification.py
                              cot_delegation.py  cot_meta.py
```

New modules import `CotEventParser` and `_CotEventToolBase` from
`vidbyte.tools.builtins.cot_events` — single source of truth for parsing and
the record/upsert plumbing. (`_CotEventToolBase` is module-underscore but
package-internal reuse; called out here per the no-unspoken-patterns rule.)

---

## 6. Detailed Design

### 6.1 Family A — context-window awareness (`cot_context.py`)

**`context_load`** (snapshot `context_load:current`): `occupying*` JSON 1–3
strings; `crowded*` enum `comfortable|tight|overflowing`; `what_to_forget*`;
`oldest_unreferenced` opt; `imbalance` enum
`none|tool_heavy|primitive_heavy|conversation_heavy`; `compaction_recommended`
enum `yes|no`. Metadata: crowded, imbalance, compaction_recommended.

**`attention_check`** (append): `next_step*`; `depends_on*`; `still_visible*`
enum `yes|no|partially`; `if_no_recover_how` (required when still_visible !=
yes); `could_state_from_memory` opt number 0–1. Metadata: still_visible.

**`recall_test`** (append): `claimed_fact*`; `confidence*` 0–1 (memory
certainty — the calibration signal); `source_step` opt; `verified_now` enum
`yes|no`; `matches` enum `correct|wrong|could_not_verify` (required when
verified_now = yes). Metadata: confidence, verified_now, matches.

**`forget_decision`** (append): `what*`; `why*`; `recoverable*` enum
`yes|costly|no`; `reload_cost` enum `cheap|moderate|expensive|impossible`;
`what_still_depends_on_it*`. Metadata: recoverable, reload_cost.

### 6.2 Family B — information-foraging (`cot_foraging.py`)

**`search_why`** (append): `missing_fact*`; `why_needed*`; `stop_condition*`;
`expected_source` enum `docs|code|web|data|teammate|memory`; `fallback_if_not_found*`.
Metadata: expected_source.

**`search_plan`** (append): `queries*` JSON 1–3 objects `{query, target?,
expected_yield}` with `expected_yield` enum `exact_hit|partial|exploratory`;
`order_rationale*`; `max_queries` opt int; `abort_if` opt. Metadata:
query_count.

**`search_yield`** (append): `found*` enum
`exactly|partially|nothing|contradicts_expectation`; `queries_spent*` int;
`best_result` opt; `missing_still` opt; `pivot` enum
`continue|refine|change_tool|abandon_line`; `surprise` enum
`expected|mild|major`. Metadata: found, queries_spent, pivot.

**`enough`** (append): `acting_on*`; `evidence_count*` int; `would_change_mind*`
enum `yes|no`; `strongest_evidence*`; `weakest_link*`; `what_would_reverse` opt.
Metadata: evidence_count, would_change_mind.

### 6.3 Family C — self-verification (`cot_verification.py`)

**`verify`** (append): `claim*`; `method*` enum
`re-derive|re-run|cross-check|read-back`; `verdict*` enum
`passes|fails|cannot_verify`; `evidence*`; `severity_if_wrong` enum
`fatal|major|minor`; `fixed` enum `yes|no|not_needed` (required when verdict =
fails). Metadata: method, verdict, fixed.

**`self_test`** (append): `test*`; `ran*` enum `yes|no|not_possible`;
`result` enum `passed|failed|n_a` (required when ran = yes); `if_skipped_why`
(required when ran != yes); `coverage` enum `targeted|spot|exhaustive`.
Metadata: ran, result.

**`independently_derived`** (append): `conclusion*`; `path_a*`; `path_b*`;
`agree*` enum `yes|no|unclear`; `if_disagree` (required when agree != yes).
Metadata: agree.

**`read_back`** (append): `record*`; `matches_memory*` enum
`yes|drifted|contradicts`; `drift_detail` (required when != yes);
`corrective_action` opt. Metadata: matches_memory.

### 6.4 Family D — delegation epistemics (`cot_delegation.py`)

**`delegation_brief`** (append): `task*`; `success_criteria*`;
`assumptions_passed` JSON strings opt; `withheld` opt; `context_attached` enum
`minimal|moderate|full`; `fallback_on_failure` opt. Metadata:
context_attached, assumptions_passed_count.

**`delegation_receipt`** (append): `result_summary*`; `trust*` enum
`verified|spot_checked|assumed`; `criteria_met*` enum
`met|partially_met|missed|gamed`; `discrepancies` opt; `recheck_cost` enum
`cheap|expensive|impossible`. Metadata: trust, criteria_met.

**`handoff_why`** (append): `work*`; `reason*` enum
`specialization|capacity|context_limit|parallelism`; `rationale*`;
`receiver_ready` enum `yes|no|unclear`; `take_back_trigger` opt. Metadata:
reason.

**`handoff_completeness`** (append): `brief*`; `missing*` enum
`nothing|context|constraints|format|success_criteria`; `fix_applied` enum
`yes|no`; `risk_if_unfixed` enum `fatal|major|minor`. Metadata: missing.

**`subagent_failures`** (append): `failure*`; `owner*` enum
`brief|capability|context|luck`; `analysis*`; `recoverable` enum
`yes|costly|no`; `retry_differently` opt. Metadata: owner.

**`blocked_on`** (ledger, statement-hash id): `blocked_on*`;
`blocking_since_step` opt int; `steps_wasted` opt int; `response*` enum
`wait|nudge|take_back|escalate`; `unblock_condition*`. Metadata: response.

### 6.5 Family E — meta-monitoring (`cot_meta.py`)

**`record_dispute`** (append): `record_a*`; `record_b*`; `contradiction*`;
`which_is_wrong*` enum `a|b|both|neither`; `resolution` opt. Metadata:
which_is_wrong.

**`ritual_check`** (snapshot `ritual_check:current`): `reflexive*` JSON 1–5
strings; `still_earning*` JSON 1–5 strings; `blind_spots` opt; `overall` enum
`healthy|heavy|smothering`. Metadata: reflexive_count, earning_count, overall.

**`telemetry_gap`** (append): `event*`; `wanted_to_record*`; `closest_tool`
opt; `severity` enum `minor|notable|critical`. Metadata: severity.

**`signal_highlight`** (append): `record*`; `changed_direction*` enum
`yes|slightly|no`; `would_have_happened*`; `surprise` enum
`expected|surprising|alarming`. Metadata: changed_direction.

**`calibration_self_report`** (snapshot `calibration:current`):
`predictions_made*` int; `estimated_hits*` int; `estimated_rate*` 0–1;
`confidence_in_estimate*` 0–1; `bias_self_assessment` enum
`overconfident|calibrated|underconfident|unknown`. Metadata: estimated_rate,
bias.

**`description_drift`** (append): `tool*`; `actual_usage*`;
`description_wrong_about*`; `suggested_fix` opt. Metadata: tool.

### 6.6 Edge Cases & Error Handling
Same as batches 1–2 plus: conditional-required fields produce errors naming
the field and its triggering condition; `queries`/`assumptions_passed`/
`reflexive`/`still_earning` JSON arrays validated per element type; ints
coerced (number or numeric string, >= 0), errors on non-numeric.

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
| CREATE | `vidbyte/tools/builtins/cot_context.py` | Family A tools (4) |
| CREATE | `vidbyte/tools/builtins/cot_foraging.py` | Family B tools (4) |
| CREATE | `vidbyte/tools/builtins/cot_verification.py` | Family C tools (4) |
| CREATE | `vidbyte/tools/builtins/cot_delegation.py` | Family D tools (6) |
| CREATE | `vidbyte/tools/builtins/cot_meta.py` | Family E tools (6) |
| CREATE | `vidbyte/context/primitives/cot_context.py` | Family A primitives |
| CREATE | `vidbyte/context/primitives/cot_foraging.py` | Family B primitives |
| CREATE | `vidbyte/context/primitives/cot_verification.py` | Family C primitives |
| CREATE | `vidbyte/context/primitives/cot_delegation.py` | Family D primitives |
| CREATE | `vidbyte/context/primitives/cot_meta.py` | Family E primitives |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Import + `__all__` for 24 tools |
| MODIFY | `vidbyte/tools/builtins/cot_events.py` | Add shared `CotEventParser.parse_int` |
| MODIFY | `vidbyte/context/primitives/__init__.py` | Import + `__all__` for 24 primitives |

13 files: 10 created, 3 modified, 0 deleted. Stacked on `feat/deep-cot-tools-2`.

---

## 10. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| stdlib `json`, `hashlib` | Python 3.11+ | Parsing, ledger ids | None |

---

## 11. Rollout & Deployment

Additive; opt-in. Merge order: #337 → #338 → this PR.

---

## 12. Open Questions

- [ ] None blocking. Runtime reactions (e.g. compaction on
  `compaction_recommended=yes`) are deliberate non-goals for a future PR.

---

## 13. Alternatives Considered

### Alternative 1: All 24 tools in one `cot_events.py`
- What: Extend the existing module.
- Why rejected: ~3,000 added lines in one file is unreviewable; per-family
  modules match the repo's folder-per-concern grain.

### Alternative 2: Duplicate parsers per family module
- What: Local copies of enum/confidence parsing.
- Why rejected: Class-bound-helpers rule — one shared parser class, imported
  from `cot_events`.

### Alternative 3: Fewer params per tool
- What: Lean 2–3 param specs like batch 1.
- Why rejected: User explicitly directed bias-toward-more-params; richer axes
  are the observability payload of this batch.

---

CI gate: `PYTHONPATH=<worktree> python scripts/run_ci.py --stage source`, then
`python scripts/run_ci.py --stage package` without PYTHONPATH.

END OF DESIGN DOC
