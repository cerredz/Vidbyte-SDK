# Design Doc: Deep CoT Reasoning Event Tools

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-17
**Last Updated:** 2026-08-17

---

## 1. Overview

Adds a family of five model-callable "deep chain-of-thought" tools that decompose
an agent's reasoning into atomic, observable cognitive events: hypotheses held
and resolved, decisions taken with alternatives rejected, assumptions declared
and verified, uncertainty snapshots, and backtracks. Each tool call upserts a
typed context primitive (visible to future model calls) and returns parsed,
structured values in `ToolResult.metadata` so monitors can chart reasoning
health without parsing prose. The primary deliverable value is the parameter
descriptions: they explicitly teach the model what each event means, when to
emit it, and how terse to be.

---

## 2. Goals & Non-Goals

### Goals
- Five new builtin tools: `hypothesis`, `decision`, `assumption_check`,
  `uncertainty`, `backtrack`, following the `ReflexionTool` /
  `TrajectoryCheckpointTool` pattern (`BaseTool` + injected `ContextManager` +
  `ToolPermission.SAFE`).
- Five new frozen-dataclass context primitives rendering into the context
  window like existing reasoning primitives.
- Parsed enums and clamped confidences land in `ToolResult.metadata` for
  observability pipelines (Langfuse/Langsmith/Phoenix charting).
- Exceptionally explicit, coercive tool and parameter descriptions — the
  descriptions are the product.

### Non-Goals
- No changes to the continual trace agent, `UpdateTraceTool`, or trace schemas.
- No new algorithms, middleware, or runtime hooks.
- No auto-registration of these tools onto agents; developers opt in via
  `with_tools(...)` like every other builtin.
- No new dependencies.

---

## 3. Background & Context

The SDK's existing reasoning-monitoring surface is narrative:
`ReflexionTool` (self-critique) and `TrajectoryCheckpointTool` (progress
snapshot). Both write prose plus one scalar score. Research on calibrated
verbalized confidence, tree-of-thoughts search, and progress classification
shows the discriminative monitoring signals live in finer-grained events:
rejected alternatives, load-bearing assumptions, next-step vs on-track
confidence divergence, and velocity classification. The user explicitly
excluded the continual-trace path and asked for a decomposed family of
model-facing tools whose descriptions drive adoption and output quality.

Nearest existing patterns copied for this feature:
- Tool shape: `vidbyte/tools/builtins/reflexion.py` (constructor takes
  `ContextManager`, per-instance counter for stable primitive IDs, `spec()`
  with rich descriptions, `execute()` validates then upserts).
- Primitive shape: `vidbyte/context/primitives/epistemics.py` (frozen slotted
  dataclass, `to_context_text()` rendering deterministic sections bounded by
  `max_chars`, `_truncate_text`/`_extend_section` helpers).
- Score parsing/clamping: `TrajectoryCheckpointTool._parse_score`.

---

## 4. Requirements

### Functional Requirements
1. Each of the five tools is a `BaseTool` subclass whose `spec()` declares a
   lowercase-verb/noun name, a "use this when..." trigger sentence opening the
   description, and per-parameter descriptions that state format, terseness
   limits, and semantics.
2. Required-string validation mirrors `ReflexionTool._validate_required_fields`
   (missing or whitespace-only required string → `ToolResult.error`).
3. Enum params validate against exact allowed values; invalid values return
   `ToolResult.error` with the allowed values named in the message.
4. Confidence params accept a number or numeric string, are coerced to float
   and clamped to [0.0, 1.0] (the `_parse_score` pattern); parse failures on
   optional params degrade to `None`, never an error.
5. Every successful `execute()` upserts exactly one primitive into the
   injected `ContextManager` under a stable `primitive_id`
   (`<kind>:<counter>`), and returns `ToolResult.success` whose `metadata`
   carries the parsed enum/confidence fields.
6. JSON-string params (`rejected` on `decision`) are validated as parseable
   JSON arrays of objects; invalid JSON returns `ToolResult.error`.
7. All five tool classes and all five primitive classes are exported from
   `vidbyte.tools.builtins` and `vidbyte.context.primitives` respectively.
8. Tool names and primitive `kind` strings match
   (`hypothesis`/`hypothesis`, `decision`/`decision`,
   `assumption_check`/`assumption_check`, `uncertainty`/`uncertainty`,
   `backtrack`/`backtrack`).

### Non-Functional Requirements
- Zero new dependencies; stdlib `json` only.
- Each primitive render bounded by `max_chars` (2000 default, matching
  siblings) to prevent unbounded context growth.
- All numeric bounds and enum tuples are named module constants — no inline
  magic values.
- Parsing helpers shared via one static helper class per the class-bound
  helpers field-guide rule.
- Async execution is trivial (no I/O beyond the in-memory manager upsert), so
  no latency concerns.

---

## 5. High-Level Design

Two event modules, two SDK contract modules, and the modified export surfaces.
The tools module (`cot_events.py`) holds the five tool classes plus one shared
static parser class (`CotEventParser`) for enum/confidence/JSON-array coercion.
`vidbyte/lib/enums/cot_events.py` owns categorical values and
`vidbyte/lib/constants/cot_events.py` owns bounds, defaults, and display labels,
so the tool module does not define a second vocabulary. The primitives module
(`cot_events.py` under `context/primitives/`) holds the five frozen dataclasses.

```
Model emits tool call
  -> AgentRuntime.execute_tool_call (existing, unchanged)
  -> <Event>Tool.execute
       -> CotEventParser.* (validate/coerce args)
       -> build frozen primitive
       -> ContextManager.upsert (visible to future turns)
       -> ToolResult.success(text=primitive.to_context_text(),
                             metadata=parsed fields)
  -> Observability providers read result.metadata
```

Key decision: one module per layer rather than five. The existing repo has one
file per builtin tool, but those tools share no logic. These five share three
parsers; a single module with a shared static helper class matches both the
class-bound-helpers rule (PR #328/#329 feedback) and keeps review surface
small. Rejected alternative: five tool files + duplicate parser snippets.

---

## 6. Detailed Design

### 6.1 Shared parser class

**File(s):** `vidbyte/tools/builtins/cot_events.py` (new)
**Type:** New file

`CotEventParser` — static methods:
- `parse_enum(value, allowed: type[CotEventEnum], field_name: str) -> tuple[str | None, str | None]`
  — exact-match against allowed values (case-insensitive, normalized to the
  canonical lowercase value); returns `(parsed, error)`.
- `parse_confidence(value) -> float | None` — coerce number/numeric string,
  clamp to [0,1], `None` on failure.
- `parse_json_objects(value, field_name: str, max_items: int) -> tuple[list[dict] | None, str | None]`
  — parse a JSON string (or pass through a list), require a list of objects,
  cap at `max_items`, returns `(parsed, error)`.
- `require_text(args, names: tuple[str, ...]) -> str | None` — the
  `ReflexionTool._validate_required_fields` pattern.

### 6.2 The five tools

All in `vidbyte/tools/builtins/cot_events.py`. Each class:
`__init__(self, context_manager: ContextManager)`, `spec()`, `execute()`, and
small private helpers (validate → build → upsert), matching `ReflexionTool`'s
shape.

Primitive ID policy: the two ledger tools (`hypothesis`, `assumption_check`)
derive their `primitive_id` from a content hash of the statement
(`statement_primitive_id`), so re-calling with the same statement overwrites
the single ledger entry — exactly what their descriptions promise. The three
append-only event tools (`decision`, `uncertainty`, `backtrack`) use the
counter-based `<name>:<n>` IDs like `ReflexionTool`.

#### `HypothesisTool` (name: `hypothesis`)
Params: `statement*`, `scope*`, `basis*`, `status*` enum
`proposed|supported|weakened|falsified`, `basis_type` enum
`evidence|inference|prior`, `falsifier*`, `confidence`, and `next_check`.
Primitive: `HypothesisContextItem`. Metadata: `status`, `basis_type`, and
parsed `confidence`. The normalized statement remains the ledger identity.

#### `DecisionTool` (name: `decision`)
Params: `decision*`, `chosen_because*`, `criterion*`, `rejected*` JSON array of
1–3 objects with non-empty `option` and `reason` keys, `expected_outcome*`,
`main_risk*`, `reversible` enum `yes|no|costly`, `confidence`, and
`review_trigger`. Primitive: `DecisionContextItem`. Metadata: `reversible`,
`confidence`, and `rejected_count`.

#### `AssumptionCheckTool` (name: `assumption_check`)
Params: `assumption*`, `scope*`, `basis*`, `action*` enum
`declared|verified|falsified`, `impact_if_wrong*` enum `fatal|major|minor`,
`dependency*`, `verification_step` (required when action is `verified` or
`falsified`), `falsifier*`, and `confidence`. Primitive:
`AssumptionCheckContextItem`. Metadata: `action`, `impact_if_wrong`, and parsed
`confidence`. The normalized assumption remains the ledger identity.

#### `UncertaintyTool` (name: `uncertainty`)
Params: `next_step*` number 0–1, `on_track*` number 0–1, `progress*` enum
`progressing|stalled|regressing`, `trigger`, `uncertainty_source*`, `blocker`,
`next_action*`, and `reassessment_condition`. Primitive:
`UncertaintyContextItem`. Metadata: `next_step`, `on_track`, `progress`, and
derived `divergence = on_track - next_step`.

#### `BacktrackTool` (name: `backtrack`)
Params: `abandoning*`, `reason*`, `evidence*`, `attempted_result*`, `salvage`,
`returnable` enum `yes|no`, `replacement_plan*`, and `loop_guard*`. Primitive:
`BacktrackContextItem`. Metadata: `returnable`.

#### Edge Cases & Error Handling
- Missing/blank required strings → `ToolResult.error` naming the field.
- Bad enum → `ToolResult.error` listing allowed values.
- `rejected` JSON unparseable, not a list of objects, or missing non-empty
  `option`/`reason` keys → `ToolResult.error`.
- `ContextManager.upsert` raising `ValueError` (frozen primitive) →
  `ToolResult.error` with the message, matching `ReflexionTool`.
- Optional params absent or empty → defaults, never errors.

### 6.3 The five primitives

**File(s):** `vidbyte/context/primitives/cot_events.py` (new)
**Type:** New file

Frozen, slotted dataclasses with `kind`, `primitive_id`, `title`,
`max_chars = 2000`, `metadata`, `primitive_frozen = False`, and
`to_context_text()` rendering deterministic `Key: value` / `### Section`
lines via `_truncate_text` / `_extend_section` — the `epistemics.py` pattern:
- `HypothesisContextItem` — status/basis/basis_type/statement.
- `DecisionContextItem` — decision/chosen_because/rejected lines/reversible/confidence.
- `AssumptionCheckContextItem` — action/impact/assumption/verification_step.
- `UncertaintyContextItem` — next_step/on_track/progress/trigger.
- `BacktrackContextItem` — abandoning/reason/salvage/returnable.

### 6.4 Export surfaces

**File(s):** `vidbyte/tools/builtins/__init__.py`,
`vidbyte/context/primitives/__init__.py` (both modified)

Import blocks + `__all__` entries for the five tool classes
(`CotEventParser` stays module-public but is exported too for reuse) and five
primitive classes, alphabetically placed as the files do now.

---

## 7. Data Model Changes

N/A - In-memory context primitives only; no persistence, schema, or migration
surface exists or is touched.

---

## 8. API Changes

N/A - No HTTP/RPC endpoints. Public Python API additions only (new exports);
no existing signatures change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/tools/builtins/cot_events.py` | Five deep-CoT tool classes + shared `CotEventParser` |
| CREATE | `vidbyte/context/primitives/cot_events.py` | Five frozen context primitives |
| CREATE | `vidbyte/lib/enums/cot_events.py` | Canonical categorical event values |
| CREATE | `vidbyte/lib/constants/cot_events.py` | Shared bounds, defaults, labels, and limits |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Import + `__all__` for the five tools |
| MODIFY | `vidbyte/context/primitives/__init__.py` | Import + `__all__` for the five primitives |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Re-export event enums |
| MODIFY | `vidbyte/lib/constants/__init__.py` | Re-export event constants |

8 files: 4 created, 4 modified, 0 deleted.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| stdlib `json` | Python 3.11+ | Parse `rejected` JSON | None |

No external services.

---

## 11. Rollout & Deployment

No feature flags; additive exports only. Not a breaking change — no existing
symbol moves or changes. Tools are opt-in via `agent.with_tools(...)`.
Rollback = revert the PR.

---

## 12. Open Questions

- [ ] None blocking. (Descriptions below are the deliverable; user will
  iterate on wording post-review.)

---

## 13. Alternatives Considered

### Alternative 1: One combined "deep checkpoint" tool with many optional params
- What: A single `deep_checkpoint` tool with all fields from the five events.
- Why rejected: User explicitly asked for a decomposed family of atomic
  event tools; one fat tool collapses per-event-type telemetry back into
  narrative dumps and weakens per-event charting.

### Alternative 2: Five separate tool files (strict one-file-per-tool grain)
- What: `hypothesis.py`, `decision.py`, etc., each duplicating parsing.
- Why rejected: The shared parsers would be duplicated five times; the
  class-bound-helpers field-guide rule (PR #328/#329) prefers one static
  helper class for shared concerns. One module keeps the diff reviewable.

### Alternative 3: Reuse existing primitives (e.g. `AssumptionChallengeContextItem`)
- What: Map new tools onto `epistemics.py` challenge primitives.
- Why rejected: Those primitives model disputes raised *against* the agent by
  an algorithm; the new events are model-authored monitoring records with
  different lifecycles (update-in-place via re-statement). Overloading them
  corrupts both semantics.

---

CI gate (recorded per workflow): `python -m pip install -e ".[dev]"` then
`python scripts/run_ci.py`, with the worktree caveat from the field guide:
source stage needs `PYTHONPATH` set to the worktree; package stage must run
without it.

END OF DESIGN DOC
