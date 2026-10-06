# Design Doc: Context-Window Reasoning Algorithms (Problem-Space Search & Error Correction)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-07
**Last Updated:** 2026-06-07

---

## 1. Overview

This feature adds two new inner-loop context-window algorithms to the Vidbyte SDK. Both follow the existing `InnerContextWindowAlgorithm` lifecycle pioneered by `TrajectoryCheckpointAlgorithm`: every `n` completed iterations of a direct agent run, the algorithm pauses, makes a single model call to reason about the run so far, and writes a bounded, structured context primitive into the active `ContextManager` so the next model call sees it.

- **Problem-Space Search** (`ContextWindow.preset.problem_space_search`): every `n` iterations, an "explorer" model pass inspects the system prompt and conversation history and surfaces things the agent has **not yet considered** — blind spots, unexplored approaches, and next directions — and injects them as a bounded note.
- **Error Correction** (`ContextWindow.preset.error_correction`): every `n` iterations, an "error-correction agent" model pass audits the context window against the **original system prompt**, identifies claims/assumptions that are incorrect or contradict the system prompt, and (a) injects one authoritative **Correction Notice** instructing the model to disregard them and (b) prunes the algorithm's own previously-injected primitives that are now stale.

Both are SDK-selected runtime behaviors attached through `algorithm=ContextWindow.preset.<name>`, requiring no manual wiring by the developer.

---

## 2. Goals & Non-Goals

### Goals

- Provide two obvious presets: `ContextWindow.preset.problem_space_search` and `ContextWindow.preset.error_correction`.
- Support string resolution: `ContextWindow.resolve_algorithm("problem_space_search")` and `("error_correction")`.
- Expose typed public config dataclasses (`ProblemSpaceSearchAlgorithm`, `ErrorCorrectionAlgorithm`) with full `__post_init__` validation.
- Give each algorithm its own typed, bounded context primitive ("a context window for this algorithm" per the request).
- Keep prompt bodies in the Markdown-backed prompt catalog, not inline Python strings.
- Attach behavior automatically through the existing inner-loop dispatch in `AgentRuntimeContextAlgorithms` / `AgentRuntime._arun_once`.
- Preserve every runtime contract in §12 of the skill: tools, permissions, middleware, tracing, provider formatting, and `AgentResult` metadata.
- Per-algorithm default cadence: `problem_space_search` every **5** iterations, `error_correction` every **4** iterations.
- Publish a structured metadata trace and a deterministic slot template for each algorithm.
- Tests-first: public API, prompt catalog, dispatcher, runtime behavior, edge cases, and hidden assumptions.

### Non-Goals

- **No mutation of provider `messages` or prior `AgentMessage` history.** Per the inner-loop contract (skill §10.3, §13), these algorithms only place/remove managed primitives on the `ContextManager`. "Error correction" therefore *overrides* incorrect content with an authoritative notice and prunes its own primitives; it does **not** physically delete conversation turns. This is a deliberate, documented constraint, not an oversight.
- No new trial-wrapping runtime adapter under `vidbyte/agents/algorithms/` (these are inner-loop, not Reflexion-style retry algorithms).
- No changes to pipelines, no provider-specific network logic, no new low-level builder API.
- No tool-based `write_context` mechanism — placement is SDK-driven, not model-tool-driven.
- Unknown preset names continue to fail loudly (no silent fallback to `default`).

---

## 3. Background & Context

The SDK already supports inner-loop context-window algorithms. `TrajectoryCheckpointAlgorithm` is the canonical example: it subclasses `InnerContextWindowAlgorithm`, implements the single `after_tool_calls` hook, calls the model runner via `ctx.invoke_runner`, and writes a `TrajectoryCheckpointContextItem` through `ctx.place_after_tools(...)`. The runtime invokes the hook once at run start (`ctx.iteration is None`) and once after each completed non-final iteration's tool calls (`vidbyte/agents/runtime.py:217-235`, `:702-737`).

The user wants two new behaviors that fit this exact shape:

1. A periodic "search the problem space" reflection that surfaces unconsidered angles.
2. A periodic "error-correction agent" that cleans the context window of content that is wrong relative to the original system prompt.

Both are most naturally expressed as inner-loop algorithms because they operate *within* a single direct run, every `n` iterations, modifying what the next model call sees — exactly what the inner-loop lifecycle is for. The trajectory-checkpoint implementation, primitive, template, prompt-catalog entry, and test file give us a complete, proven blueprint to mirror.

Key architectural constraint discovered during the audit: inner-loop algorithms have a **slim write surface** (`ContextWindowRunContext`) that exposes only `place_after_system_prompt`, `place_after_tools`, `remove`, `record`, and `set_metadata` over the `ContextManager`. There is no API to edit `messages`, and the skill explicitly forbids it. This shapes the error-correction design (override + self-prune, not delete).

---

## 4. Requirements

### Functional Requirements

**Shared (both algorithms)**

1. Each algorithm is selectable via `algorithm=ContextWindow.preset.<name>` on an `Agent`.
2. Each runs only on direct (no trial-wrapping) agent runs through the inner-loop lifecycle.
3. The run-start invocation (`ctx.iteration is None`) initializes per-run state and records the `"system_prompt"` slot, mirroring trajectory checkpoints.
4. Each completed non-final iteration records a per-iteration slot; deduplication prevents double-processing the same `iteration_count`.
5. On cadence (`iteration_count % interval == 0`, `iteration_count > 0`), the algorithm makes exactly one model call via `ctx.invoke_runner(ctx.runner, prompt, **options)`.
6. The model call uses the catalog prompt unless a per-config override string is supplied.
7. Each algorithm publishes a compact, structured metadata object to the final `AgentResult.metadata` via `ctx.set_metadata`.
8. Invalid numeric/string config raises `ConfigurationError` at construction time.
9. Each algorithm is mutually exclusive with other runtime context algorithms (enforced by `ContextWindowAlgorithm.__post_init__`).

**Problem-Space Search**

10. Default `interval = 5`.
11. On each pass, the explorer call returns JSON describing `unconsidered`, `blind_spots`, and `next_directions`.
12. The result is injected as a bounded `ProblemSpaceSearchContextItem` via the configured placement (default end-of-context).
13. Notes accumulate as numbered primitives (`problem_space_search:1`, `:2`, ...) capped by `max_notes` (default 6). Once the cap is reached, no further notes are injected (but iteration slots still record).
14. Malformed/empty model output does not crash the run (graceful degradation with recorded failure slot, error re-raised per trajectory-checkpoint convention — see §6.5 Open Question).

**Error Correction**

15. Default `interval = 4`.
16. On each pass, the error-correction agent call returns JSON describing `corrections` (list of `{claim, why_wrong}`), `stale_primitive_ids` (managed ids to remove), and `summary`.
17. The algorithm injects/replaces exactly **one** `ErrorCorrectionContextItem` with a stable id (`error_correction:notice`) via `upsert`, so the notice reflects the current audit rather than accumulating.
18. The algorithm removes only managed primitives whose ids are in `stale_primitive_ids` **and** match a safe prefix allow-list (default: `error_correction:` and `problem_space_search:`), preventing the model from deleting arbitrary registry entries.
19. Passes are capped by `max_passes` (default 8).
20. Removals and corrections are reported in metadata; removals are **not** template slots (they are model-dependent and therefore non-deterministic).

### Non-Functional Requirements

- **Performance:** one extra model call per cadence hit; bounded by `max_notes` / `max_passes`. All injected text bounded by char limits (`_truncate`).
- **Determinism of structure:** slot sequences are deterministic given `iterations`, `interval`, and the cap, enabling `ContextWindowTemplate` validation. Model *content* is non-deterministic; only structural slots are templated.
- **Observability:** structured metadata trace per algorithm; recorder slots for template tests; failure slot recorded on model/parse error.
- **Reliability:** per-run state keyed under a private state key; iteration dedup via a `set`; no shared mutable `options` leakage (copy per call as trajectory checkpoints does with `**dict(ctx.options or {})`).
- **Security:** error-correction removal is prefix-gated so a hostile/confused model cannot prune unrelated context primitives.

---

## 5. High-Level Design

Both algorithms are implemented purely as **inner-loop context-window algorithms**. No changes to `AgentRuntime.arun` control flow are needed beyond what already exists — the runtime already invokes `after_tool_calls` for any configured `InnerContextWindowAlgorithm`. The work is: (1) two public config dataclasses, (2) two context primitives, (3) two prompt-catalog families, (4) two preset properties + two fields on `ContextWindowAlgorithm`, (5) dispatcher detection wiring, (6) two slot templates, (7) tests, (8) docs.

Data flow for one cadence hit (identical skeleton for both):

```
AgentRuntime._arun_once loop
  └─(iteration_count % interval == 0)→ _run_inner_context_window_hook(...)
        └─ algorithm.after_tool_calls(ContextWindowRunContext)
              ├─ should_run(iteration_count, count) ?
              ├─ build prompt = catalog_prompt + system_prompt + history(+ managed primitives for error_correction)
              ├─ response = await ctx.invoke_runner(ctx.runner, prompt, **options)
              ├─ parsed = parse_json(ctx.runner_output_text(response))
              ├─ PROBLEM SEARCH:  ctx.place_after_tools(ProblemSpaceSearchContextItem(...))
              │  ERROR CORRECT:   ctx.remove(stale ids)  +  ctx.context_manager.upsert(ErrorCorrectionContextItem(stable id))
              ├─ ctx.record(<injection/pass slot>, ...)
              └─ ctx.set_metadata(<algorithm key>, {...trace...})
   └─ next model call renders ContextManager → primitive becomes model-visible
```

Key design decisions:

- **Mirror `TrajectoryCheckpointAlgorithm` exactly** for state handling, JSON parsing, history formatting, truncation, validation helpers, and metadata publication. This maximizes review familiarity and reuses proven edge-case handling.
- **Problem-space search accumulates** numbered notes (history of frontiers is useful); **error correction replaces** a single notice (only the current correction set matters) and additionally prunes. This difference is intentional and documented.
- **Removal is prefix-gated** to satisfy the §13 contract that algorithms must not mutate arbitrary context they do not own.
- **Per-algorithm intervals** (5 and 4) are config defaults, overridable via the dataclass.

```
[Agent(algorithm=preset)] -> [AgentRuntime._arun_once] -> [InnerContextWindowAlgorithm.after_tool_calls]
                                                                  |
                                          [ctx.invoke_runner] -> [model] (explorer / auditor)
                                                                  |
                                          [ContextManager.place/upsert/remove] -> [next model call sees primitive]
```

---

## 6. Detailed Design

### 6.1 ProblemSpaceSearchAlgorithm (public config + inner-loop logic)

**File(s):** `vidbyte/context/algorithms/problem_space_search.py`
**Type:** New file

#### What it does
Frozen public config dataclass that also implements the inner-loop `after_tool_calls` hook. Every `interval` iterations it runs an explorer model pass and injects a bounded `ProblemSpaceSearchContextItem`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ProblemSpaceSearchAlgorithm(InnerContextWindowAlgorithm):
    interval: int = 5
    max_notes: int = 6
    max_note_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
    note_title: str = "Problem-Space Search"
    explorer_prompt: str | None = None            # overrides catalog prompt
    placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None: ...
    def should_explore(self, iteration_count: int, note_count: int) -> bool: ...
    async def build_item(self, ctx, snapshot, note_index: int) -> ProblemSpaceSearchContextItem: ...
```

#### Logic / Algorithm
1. `_state(ctx)` → `{"seen_iterations": set(), "notes": []}` under private state key.
2. If `ctx.iteration is None`: `ctx.record("system_prompt")`, publish empty metadata, return.
3. Dedup on `snapshot.iteration_count`; record `"problem_space_search_iteration"`.
4. `should_explore` → `note_count < max_notes and iteration_count > 0 and iteration_count % interval == 0`.
5. If yes: `build_item` (model call), `place` via configured placement, append compact record, `record("problem_space_search_injection", ...)`.
6. `_publish_metadata` every call.

`build_item`: load `Prompt.PROBLEM_SPACE_SEARCH_EXPLORER` (or `explorer_prompt` override), build `system_prompt + history` user message, `invoke_runner`, parse JSON `{unconsidered, blind_spots, next_directions}`, construct bounded item with id `problem_space_search:{note_index}`.

#### Edge Cases & Error Handling
- Missing runner/invoke callable → `ValueError` (mirrors trajectory checkpoints).
- JSON parse failure → record `"problem_space_search_failure"` slot, re-raise (consistent with existing convention; see §6.5 Open Question on whether to swallow instead).
- `max_notes` reached → iteration slot still recorded, no injection slot.
- Empty parsed fields render as empty sections, bounded by `_truncate`.

---

### 6.2 ErrorCorrectionAlgorithm (public config + inner-loop logic)

**File(s):** `vidbyte/context/algorithms/error_correction.py`
**Type:** New file

#### What it does
Frozen public config dataclass implementing the inner-loop hook. Every `interval` iterations an "error-correction agent" model pass audits the context against the original system prompt, then prunes flagged managed primitives and upserts a single authoritative correction notice.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ErrorCorrectionAlgorithm(InnerContextWindowAlgorithm):
    interval: int = 4
    max_passes: int = 8
    max_notice_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = True
    removable_prefixes: tuple[str, ...] = ("error_correction:", "problem_space_search:")
    notice_title: str = "Correction Notice"
    auditor_prompt: str | None = None
    placement: ContextWindowPlacement = ContextWindowPlacement.TOP_OF_CONTEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None: ...
    async def after_tool_calls(self, ctx: ContextWindowRunContext) -> None: ...
    def should_audit(self, iteration_count: int, pass_count: int) -> bool: ...
    async def run_audit(self, ctx, snapshot) -> dict[str, Any]: ...
    def apply_removals(self, ctx, stale_ids: Sequence[str]) -> list[str]: ...
    def build_notice(self, corrections, summary, pass_index) -> ErrorCorrectionContextItem: ...
```

#### Logic / Algorithm
1. `_state(ctx)` → `{"seen_iterations": set(), "passes": [], "removed": []}`.
2. Run-start (`ctx.iteration is None`): record `"system_prompt"`, publish empty metadata, return.
3. Dedup; record `"error_correction_iteration"`.
4. `should_audit` → `pass_count < max_passes and iteration_count > 0 and iteration_count % interval == 0`.
5. If yes:
   a. `run_audit` → model call → JSON `{corrections: [{claim, why_wrong}], stale_primitive_ids: [...], summary}`.
   b. `apply_removals`: for each id in `stale_primitive_ids`, remove via `ctx.remove(id)` **only if** it `startswith` an allowed prefix; collect actually-removed ids.
   c. `build_notice`: one `ErrorCorrectionContextItem` (stable id `error_correction:notice`); placed via `ctx.context_manager.upsert(item, placement=...)` so it replaces the prior notice.
   d. Record `"error_correction_pass"`; append compact pass record (corrections count, removed ids).
6. `_publish_metadata` every call.

The auditor prompt includes the original system prompt verbatim as the authority, the conversation history, and the list of currently-managed primitive ids+titles (so the model can name stale ids).

#### Edge Cases & Error Handling
- `stale_primitive_ids` containing ids outside the allow-list → silently skipped, counted in metadata as `skipped_removals`.
- Removing a non-existent id → `remove_by_id` already no-ops silently.
- Empty `corrections` → still upserts a notice stating "no corrections"? **No** — if corrections is empty and nothing removed, skip the notice upsert to avoid noise; record the pass with `corrections=0`. (Documented behavior.)
- `max_passes` reached → iteration slot recorded, no pass slot.
- Parse failure → record `"error_correction_failure"`, re-raise (see §6.5 Open Question).

---

### 6.3 Context Primitives

**File(s):** `vidbyte/context/primitives/reasoning.py`
**Type:** New file

```python
@dataclass(frozen=True, slots=True)
class ProblemSpaceSearchContextItem:
    primitive_id: str
    iteration: int
    note_index: int
    unconsidered: str
    blind_spots: str
    next_directions: str
    title: str = "Problem-Space Search"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "problem_space_search"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...   # ordered sections, bounded by _truncate_text

@dataclass(frozen=True, slots=True)
class ErrorCorrectionContextItem:
    primitive_id: str
    iteration: int
    pass_index: int
    corrections: tuple[str, ...]
    summary: str
    title: str = "Correction Notice"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "error_correction"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...   # authoritative "disregard the following" framing
```

Both reuse `_truncate_text` from `vidbyte/context/primitives/base.py`, mirroring `checkpoints.py`. Re-exported from `primitives/__init__.py`, `context/__init__.py`, and root `vidbyte/__init__.py`.

---

### 6.4 Preset Registration & Config Field

**File(s):** `vidbyte/context/algorithms/tool_results.py` (MODIFY), `vidbyte/context/presets.py` (MODIFY)

Add two optional fields to `ContextWindowAlgorithm`:
```python
problem_space_search: ProblemSpaceSearchAlgorithm | None = None
error_correction: ErrorCorrectionAlgorithm | None = None
```
Extend the `__post_init__` mutual-exclusion list to include both. Add two preset properties:
```python
@property
def problem_space_search(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(name="problem_space_search", problem_space_search=ProblemSpaceSearchAlgorithm())

@property
def error_correction(self) -> ContextWindowAlgorithm:
    return ContextWindowAlgorithm(name="error_correction", error_correction=ErrorCorrectionAlgorithm())
```
String resolution already works generically via `getattr(preset_registry, algorithm)` in `resolve_context_window_algorithm`, so no change needed there — unknown names still raise `ValueError`.

---

### 6.5 Dispatcher Wiring

**File(s):** `vidbyte/agents/context_algorithms.py` (MODIFY)

Extend `detect_algorithm()` and `inner_loop_algorithm()`:
```python
def detect_algorithm(self):
    ...
    if self.runtime.algorithm.problem_space_search is not None: return "problem_space_search"
    if self.runtime.algorithm.error_correction is not None: return "error_correction"
    return None

def inner_loop_algorithm(self):
    if self.runtime.algorithm.trajectory_checkpoints is not None: return self.runtime.algorithm.trajectory_checkpoints
    if self.runtime.algorithm.problem_space_search is not None: return self.runtime.algorithm.problem_space_search
    if self.runtime.algorithm.error_correction is not None: return self.runtime.algorithm.error_correction
    return None
```
`return_algorithm()` (trial adapters) is unchanged — these are inner-loop, not trial-wrapping. `AgentRuntime.arun` / `_arun_once` need **no** changes.

#### Open Question (§6.5)
The existing `build_item` in trajectory checkpoints **re-raises** on parse failure, which aborts the whole agent run. For these reflective, best-effort algorithms, a failed audit/exploration arguably should be skipped (record failure slot, continue) rather than killing the run. **Proposed:** swallow parse/model errors for these two algorithms (record `*_failure`, continue), since they are auxiliary reflection, not core output. Flagged in §13 Open Questions for confirmation.

---

### 6.6 Prompt Catalog

**File(s):**
- `vidbyte/prompts/prompts/problem_space_search.json` (NEW)
- `vidbyte/prompts/prompts/problem_space_search_explorer.md` (NEW)
- `vidbyte/prompts/prompts/error_correction.json` (NEW)
- `vidbyte/prompts/prompts/error_correction_auditor.md` (NEW)
- `vidbyte/lib/enums/prompts.py` (MODIFY)

JSON descriptors follow the trajectory-checkpoints shape (auto-discovered by `Prompts._json_assets`). New enum members:
```python
PROBLEM_SPACE_SEARCH_EXPLORER = "problem_space_search.explorer"
ERROR_CORRECTION_AUDITOR = "error_correction.auditor"
```
Explorer prompt: instructs the model to return strict JSON with `unconsidered`, `blind_spots`, `next_directions`. Auditor prompt: instructs the model to treat the provided system prompt as ground truth and return strict JSON with `corrections`, `stale_primitive_ids`, `summary`.

---

### 6.7 Slot Templates

**File(s):** `vidbyte/lib/templates/problem_space_search.py` (NEW), `vidbyte/lib/templates/error_correction.py` (NEW), `vidbyte/lib/templates/__init__.py` (MODIFY)

Mirror `TrajectoryCheckpointContextWindowTemplate`:
- `ProblemSpaceSearchContextWindowTemplate(iterations, interval=5, max_notes=None)` → `["system_prompt", "problem_space_search_iteration", ("problem_space_search_injection")...]`.
- `ErrorCorrectionContextWindowTemplate(iterations, interval=4, max_passes=None)` → `["system_prompt", "error_correction_iteration", ("error_correction_pass")...]`.

Removals are excluded from templates (non-deterministic).

---

## 7. Data Model Changes

N/A — no database/persistent schema. The only "data model" changes are in-memory frozen dataclasses (config objects and context primitives) described in §6.1–6.3, and two new fields on the existing `ContextWindowAlgorithm` dataclass (§6.4). No migration required; new fields default to `None`, preserving all existing behavior.

---

## 8. API Changes

N/A — no network/HTTP API. The developer-facing surface changes are additive Python API:

- New: `ContextWindow.preset.problem_space_search`, `ContextWindow.preset.error_correction`.
- New exported symbols: `ProblemSpaceSearchAlgorithm`, `ErrorCorrectionAlgorithm`, `ProblemSpaceSearchContextItem`, `ErrorCorrectionContextItem` (from `vidbyte` root and `vidbyte.context`).
- New prompt enum members and template classes.

All additive; no existing signatures change.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/context/algorithms/problem_space_search.py` | `ProblemSpaceSearchAlgorithm` config + inner-loop logic |
| CREATE | `vidbyte/context/algorithms/error_correction.py` | `ErrorCorrectionAlgorithm` config + inner-loop logic |
| CREATE | `vidbyte/context/primitives/reasoning.py` | `ProblemSpaceSearchContextItem`, `ErrorCorrectionContextItem` |
| CREATE | `vidbyte/prompts/prompts/problem_space_search.json` | Explorer prompt family descriptor |
| CREATE | `vidbyte/prompts/prompts/problem_space_search_explorer.md` | Explorer prompt body |
| CREATE | `vidbyte/prompts/prompts/error_correction.json` | Auditor prompt family descriptor |
| CREATE | `vidbyte/prompts/prompts/error_correction_auditor.md` | Auditor prompt body |
| CREATE | `vidbyte/lib/templates/problem_space_search.py` | Slot template for problem-space search |
| CREATE | `vidbyte/lib/templates/error_correction.py` | Slot template for error correction |
| CREATE | `tests/test_problem_space_search_algorithm.py` | Unit/integration tests |
| CREATE | `tests/test_error_correction_algorithm.py` | Unit/integration tests |
| CREATE | `scripts/test-context-window-reasoning-algorithms.py` | Phase-5 verification script |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export the two new config classes |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Two new fields + mutual-exclusion update |
| MODIFY | `vidbyte/context/presets.py` | Two new preset properties + imports |
| MODIFY | `vidbyte/context/primitives/__init__.py` | Export the two new primitives |
| MODIFY | `vidbyte/context/__init__.py` | Re-export new configs + primitives |
| MODIFY | `vidbyte/__init__.py` | Root re-export of new configs + primitives |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Detect + return new inner-loop algorithms |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Two new prompt enum members |
| MODIFY | `vidbyte/lib/templates/__init__.py` | Export two new templates |
| MODIFY | `skills/vidbyte-sdk/adding-context-window-algorithms.md` | Note the two new inner-loop presets (if workflow changes) |
| MODIFY | `README.md` | Document the two new presets (user-facing) |

**Totals:** 12 created, 10 modified, 0 deleted.

---

## 10. Testing Plan

Tests use `FakeRunner`/`FakeResponse`/`RunnerHandle` exactly as `tests/test_trajectory_checkpoint_algorithm.py`. No live providers.

### Unit Tests

**Public API & presets**
- `it('exposes ContextWindow.preset.problem_space_search with name and config')` — [Edge Case]
- `it('exposes ContextWindow.preset.error_correction with name and config')` — [Edge Case]
- `it('resolve_algorithm("problem_space_search").name == "problem_space_search"')` — [Hidden Assumption]
- `it('resolve_algorithm("error_correction") resolves the config')` — [Hidden Assumption]
- `it('raises ValueError for unknown preset name (no silent default)')` — [Silent Failure]
- `it('ContextWindowAlgorithm rejects two runtime algorithms configured at once')` — [Hidden Failure]

**Config validation (`ProblemSpaceSearchAlgorithm` / `ErrorCorrectionAlgorithm`)**
- `it('raises ConfigurationError when interval <= 0')` — [Edge Case]
- `it('raises ConfigurationError when max_notes/max_passes <= 0')` — [Edge Case]
- `it('raises ConfigurationError when char limit exceeds upper bound')` — [Edge Case]
- `it('raises ConfigurationError on blank title')` — [Edge Case]
- `it('raises ConfigurationError on empty explorer_prompt/auditor_prompt override')` — [Silent Failure] (empty string silently falling back to catalog)
- `it('raises ConfigurationError on non-string metadata keys')` — [Hidden Assumption]
- `it('coerces placement string to ContextWindowPlacement enum')` — [Hidden Assumption]

**JSON parsing**
- `it('parses fenced ```json blocks and bare objects')` — [Edge Case]
- `it('does not silently ignore malformed JSON')` — [Silent Failure]
- `it('handles empty fields without crashing (renders empty sections)')` — [Edge Case]

**Dispatcher (`AgentRuntimeContextAlgorithms`)**
- `it('detect_algorithm returns "problem_space_search" when configured')` — [Hidden Failure]
- `it('detect_algorithm returns "error_correction" when configured')` — [Hidden Failure]
- `it('inner_loop_algorithm returns the configured inner algorithm instance')` — [Silent Failure] (preset exists but never attaches)
- `it('inner_loop_algorithm returns None when no inner algorithm configured')` — [Edge Case]

**Templates**
- `it('problem-space template builds [system_prompt, iteration, (injection per interval up to max_notes)]')` — [Silent Failure] (cadence off-by-one)
- `it('error-correction template builds [system_prompt, iteration, (pass per interval up to max_passes)]')` — [Silent Failure]
- `it('template raises when interval <= 0 or iterations < 0')` — [Edge Case]

### Integration Tests (through `AgentRuntime`)

**Problem-Space Search**
- `it('runs explorer and injects ProblemSpaceSearchContextItem at iteration == interval')` — [Silent Failure]
- `it('does NOT inject before interval reached')` — [Silent Failure] (premature injection)
- `it('caps injected notes at max_notes while still recording iteration slots')` — [Edge Case]
- `it('next model call sees the note via ContextManager, not via injected messages')` — [Hidden Assumption] (must not mutate `messages`)
- `it('recorded slot sequence matches ProblemSpaceSearchContextWindowTemplate')` — [Silent Failure]
- `it('publishes problem_space_search metadata onto final AgentResult')` — [Silent Failure]
- `it('preserves normal runtime metadata fields after attaching algorithm metadata')` — [Silent Failure]

**Error Correction**
- `it('runs auditor and upserts a single error_correction:notice on cadence')` — [Silent Failure]
- `it('replaces (not duplicates) the notice on a second pass')` — [Hidden Failure] (notice accumulation)
- `it('removes only managed ids matching removable_prefixes')` — [Hidden Assumption] (security: cannot prune arbitrary primitives)
- `it('skips removal of ids outside the allow-list and counts them in metadata')` — [Hidden Failure]
- `it('removing a non-existent id is a no-op and does not crash')` — [Edge Case]
- `it('skips notice upsert when corrections empty and nothing removed')` — [Edge Case]
- `it('does NOT mutate provider messages or prior history')` — [Hidden Assumption]
- `it('caps passes at max_passes')` — [Edge Case]
- `it('recorded slot sequence matches ErrorCorrectionContextWindowTemplate')` — [Silent Failure]

**Shared hidden-failure paths**
- `it('does not double-process the same iteration_count (dedup)')` — [Hidden Failure]
- `it('run-start invocation records system_prompt and publishes empty metadata')` — [Hidden Assumption]
- `it('does not leak options/messages between model calls across passes')` — [Hidden Failure]
- `it('parse failure records *_failure slot')` — [Hidden Failure] (and, per §6.5 resolution, either continues or aborts — test the chosen behavior)
- `it('mutual exclusivity: cannot combine with trajectory_checkpoints/reflexion')` — [Hidden Failure]

### Manual / QA Test Cases
1. Given an `Agent` with `algorithm=ContextWindow.preset.problem_space_search` and a real provider run of ≥5 iterations, when it runs, then the conversation shows a "Problem-Space Search" block after iteration 5 listing unconsidered angles — [Edge Case: exactly at interval boundary].
2. Given `algorithm=ContextWindow.preset.error_correction` and a run where an early model turn states something contradicting the system prompt, when iteration 4 completes, then a "Correction Notice" appears flagging the contradiction and the next turn corrects course — [Hidden Assumption: system prompt is ground truth].
3. Given a malformed model response during an audit pass, when the pass runs, then the run does not crash (per §6.5) and a failure is recorded — [Hidden Failure].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `RunnerHandle` / provider runner | in-repo | Model calls for explorer/auditor passes | Provider may not report token usage; handled by snapshot allowing `None` |
| `Prompts` catalog | in-repo | Prompt bodies (auto-discovered JSON) | Missing package data → covered by prompt tests |
| `ContextManager` | in-repo | Primitive placement/removal | Removal gated by prefix allow-list |

No new third-party dependencies.

---

## 12. Rollout & Deployment

- **Feature flags:** none. Behavior is opt-in via `algorithm=ContextWindow.preset.<name>`; default behavior is unchanged (new config fields default to `None`).
- **Breaking change:** none. Purely additive.
- **Deployment order:** single SDK package; no multi-service ordering.
- **Rollback:** revert the PR; no persisted state or migrations.

---

## 13. Open Questions

- [ ] **§6.5 error handling:** For these auxiliary reflection passes, should a model/JSON-parse failure **abort the run** (mirroring trajectory checkpoints' re-raise) or be **swallowed** (record `*_failure`, continue)? Proposed: swallow & continue. Confirm.
- [ ] **Problem-space accumulation vs. replace:** Proposed numbered accumulation capped at `max_notes`. Acceptable, or prefer a single rolling "frontier" note that the explorer rewrites each pass?
- [ ] **Default `removable_prefixes`** for error correction: proposed `("error_correction:", "problem_space_search:")`. Should it also be allowed to prune `trajectory_checkpoint:` primitives if both are ever combined? (Currently impossible due to mutual exclusivity — so likely no.)
- [ ] **Empty-corrections behavior:** Proposed to skip the notice when there are zero corrections and zero removals. Confirm (alternative: always post a "no corrections this pass" notice).
- [ ] **README placement:** add a short "Reasoning algorithms" subsection, or fold into the existing context-window presets section?

---

## 14. Alternatives Considered

### Alternative 1: Trial-wrapping runtime adapters (Reflexion-style)
- **What:** Implement both as `*RuntimeAlgorithm` adapters under `vidbyte/agents/algorithms/`, wrapping whole agent trials and transforming context between attempts.
- **Why rejected:** The user's framing is explicitly "every n iterations *within* the loop," not "retry the whole task." Inner-loop is the matching lifecycle, is simpler, and avoids touching `AgentRuntime.arun` control flow. Trial-wrapping would also re-run the entire task, which is wrong for periodic mid-run reflection.

### Alternative 2: Physically deleting wrong content from `messages` (error correction)
- **What:** Have the error-correction agent rewrite/remove provider message turns.
- **Why rejected:** Violates the documented inner-loop contract (skill §10.3, §13: "Do not mutate provider `messages` directly"; "should not mutate prior `AgentMessage` history"). Would require a runtime-level design exception, break middleware/tracing/provider-formatting guarantees, and risk corrupting tool-call/result pairing. The override-notice + self-prune approach achieves the user's "clean the context window" intent within the architecture. (User selected the "error-correction agent every n iterations" framing, which this satisfies.)

### Alternative 3: A model-callable `write_context` / `correct_context` tool
- **What:** Expose tools the model can call to edit context.
- **Why rejected:** Skill §10.3 explicitly forbids making deterministic runtime algorithms depend on a model-called tool; tools are model-selected, inner-loop context algorithms are SDK-selected. Cadence control would also be lost.

### Alternative 4: One combined "self-reflection" preset doing both
- **What:** A single algorithm that both explores and corrects.
- **Why rejected:** The two behaviors have different cadences, different outputs, different placement semantics (accumulate vs. replace), and different prompts. Separate presets are clearer, independently testable, and match the user's request for two algorithms.

---

END OF DESIGN DOC
