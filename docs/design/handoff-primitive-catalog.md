# Design Doc: Process-Shape Handoff Primitive Catalog

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

> **Stacked PR.** This change builds on `feat/handoff-agent` (PR #105), which introduces the base `Handoff` primitive, `HandoffAgent`, and the handoff prompt asset. The new code here subclasses `Handoff`, which does not exist on `main` yet. To run tests and avoid duplicating PR #105's code, this PR branches from and targets `feat/handoff-agent`. Once #105 merges to `main`, retarget this PR's base to `main`. No code from PR #105 is repeated here.

---

## 1. Overview

This change adds ten new prebuilt `Handoff` context primitives to the Vidbyte SDK, each modeling a distinct *shape of an agent's problem-solving process* rather than a domain. Where the existing prebuilts (`EngineeringHandoff`, `ResearchHandoff`, `MinimalHandoff`) cover a decision-log, a findings-with-provenance, and a flat summary respectively, these ten capture reasoning/execution topologies whose load-bearing structural element differs in each case: a search frontier, a subproblem tree, an iteration journal, a constraint ledger, a decision stack, a Pareto frontier, a goal hierarchy, a coverage map, a budget curve, and a state delta. Each is a thin `Handoff` subclass that only presets a title and an ordered section map, so they require no new behavior, prompt, or runtime changes.

---

## 2. Goals & Non-Goals

### Goals

- Add ten new `Handoff` subclasses, each a distinct process-shape: `TreeSearchHandoff`, `DecompositionHandoff`, `RefinementLoopHandoff`, `ConstraintSatisfactionHandoff`, `BacktrackingHandoff`, `TradeoffHandoff`, `GoalStackHandoff`, `CoverageHandoff`, `BudgetBoundedHandoff`, `MigrationHandoff`.
- Place them where they naturally belong — alongside the existing prebuilts in `vidbyte/context/handoffs.py` — as if PR #105 were already merged.
- Export each from `vidbyte/context/handoffs.py` `__all__`, `vidbyte/context/__init__.py`, and the root `vidbyte/__init__.py`.
- Keep each subclass tiny: `DEFAULT_TITLE` + `default_sections()` returning a curated, decision-oriented `{title: description}` map.
- Cover them with a dedicated test module and a verification script.
- Update the handoff skill doc to reference the expanded catalog.

### Non-Goals

- No changes to the base `Handoff` class, `HandoffAgent`, `BaseAgent` integration, or the handoff prompt asset (all owned by PR #105).
- No new prompt assets or `Prompt` enum members — these specs reuse the existing handoff system prompt.
- No new behavior, parsing, or runtime logic. These are pure section-map presets.
- No deterministic no-LLM rendering or schema enforcement (out of scope, as in #105).
- No re-implementation of any PR #105 code.

---

## 3. Background & Context

PR #105 established that a handoff is one `Handoff` object playing three roles (context primitive, spec, and produced document), and that prebuilt variants are subclasses overriding `DEFAULT_TITLE` and `default_sections()`. It shipped three prebuilts and documented, in `skills/vidbyte-sdk/handoff.md`, the exact recipe for adding more: "Subclass `Handoff`, set `DEFAULT_TITLE`, and override `default_sections()` … Export it from the three sites … Add a unit test asserting the variant exposes a non-empty, distinct section map and that `fill()` preserves its type."

This change follows that recipe to expand the catalog with process-shape primitives. The motivation is coverage: agents solve problems in recognizably different control-flow shapes (search, decomposition, refinement, constraint solving, backtracking, trade-off analysis, hierarchical goals, exhaustive coverage, budget-bounded work, and state migration), and a handoff is most useful when its structure mirrors the shape of the work that produced it.

Constraint: the base `Handoff` only exists on `feat/handoff-agent`. Branching from `main` would make the new subclasses un-importable and untestable. Therefore this is a stacked PR (see banner).

---

## 4. Requirements

### Functional Requirements

1. Ten new classes exist in `vidbyte/context/handoffs.py`, each subclassing `Handoff`.
2. Each new class overrides `DEFAULT_TITLE` with a human-readable title and `default_sections()` returning a non-empty ordered `dict[str, str]` of section title → guidance description.
3. The ten section maps are pairwise distinct, and distinct from the three existing prebuilts' maps.
4. `default_sections()` returns a freshly constructed dict on each call (no shared mutable state across instances).
5. Each new class is exported from `vidbyte/context/handoffs.py` `__all__`, `vidbyte/context/__init__.py` (import + `__all__`), and `vidbyte/__init__.py` (import + `__all__`).
6. Each new class satisfies the `ContextItem` protocol (inherited from `Handoff`) and renders via `to_context_text()`.
7. Each new class's `fill(sections)` returns an instance of the same subclass with `metadata["filled"] = True` (inherited behavior, verified per subclass).
8. Each new class works as a `HandoffAgent` spec: `HandoffAgent(Variant()).generate_handoff(...)` returns a filled instance of that variant.
9. The handoff skill doc lists the expanded catalog.

### Non-Functional Requirements

- **Zero new runtime dependencies**; standard library only.
- **No import cycles**: the new code lives in the same module as `Handoff`, so no new import edges are introduced.
- **Backward compatible**: purely additive; no existing symbol changes meaning.
- **Context Protocol Header** preserved on the modified module (already present from #105); the new test/script files get their own headers.
- **Testing**: Python `unittest`, no network — fake runners only (matching `tests/` conventions).

---

## 5. High-Level Design

Each new primitive is a ~10-line subclass of `Handoff`. The base class already implements everything operational: `__init__` resolves `sections` to `self.default_sections()` when none is passed, `to_context_text()` renders the sections, `render_section_brief()` produces the model-facing brief, and `fill()` constructs `type(self)(...)` so the concrete subclass is preserved. A new subclass therefore only declares its identity (`DEFAULT_TITLE`) and its structure (`default_sections()`).

```
            Handoff  (base — owned by PR #105)
               ^
   ┌───────────┼───────────────────────────────────────────────┐
   │ existing  │                       new (this PR)             │
EngineeringHandoff   TreeSearchHandoff      GoalStackHandoff
ResearchHandoff      DecompositionHandoff   CoverageHandoff
MinimalHandoff       RefinementLoopHandoff  BudgetBoundedHandoff
                     ConstraintSatisfactionHandoff   MigrationHandoff
                     BacktrackingHandoff
                     TradeoffHandoff
```

Data flow is unchanged from #105: a `Handoff` (template) → `HandoffAgent` builds a system prompt from the asset + the spec's section brief → the model emits `## Title` blocks → `HandoffAgent` parses them and calls `spec.fill()` → a filled `Handoff` of the same subclass, droppable into another agent's `context_items`. The only thing these ten classes change is the *structure* the agent is asked to produce.

Key decisions: (1) put the classes in the existing `handoffs.py` rather than a new module, because that is their natural home and matches the "where they would be if the old PR merged" instruction; (2) keep each a pure preset with no overridden methods, so they inherit all tested behavior; (3) isolate the new tests in a new `tests/test_handoff_primitives.py` so the addition is self-contained and does not entangle #105's `tests/test_handoff_agent.py`.

---

## 6. Detailed Design

### 6.1 New `Handoff` subclasses

**File(s):** `vidbyte/context/handoffs.py`
**Type:** Modified (append ten classes + extend `__all__`)

#### What it does

Adds ten process-shape prebuilt handoffs. Each declares `DEFAULT_TITLE` and overrides `default_sections()`.

#### Interface / API

```python
class TreeSearchHandoff(Handoff):
    DEFAULT_TITLE = "Tree Search Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Search Goal, Frontier, Explored Branches, Pruned / Dead Branches, Best So Far, Next Expansion

class DecompositionHandoff(Handoff):
    DEFAULT_TITLE = "Decomposition Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Top-Level Problem, Decomposition, Solved Subproblems, Open Subproblems, Composition Status, Next Steps

class RefinementLoopHandoff(Handoff):
    DEFAULT_TITLE = "Refinement Loop Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Objective, Current Draft State, Iteration Log, Open Critiques, Convergence Status, Next Revision

class ConstraintSatisfactionHandoff(Handoff):
    DEFAULT_TITLE = "Constraint Satisfaction Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Objective, Constraints, Current Candidate, Conflicts & Tensions, Trade-offs Made, Next Steps

class BacktrackingHandoff(Handoff):
    DEFAULT_TITLE = "Backtracking Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Objective, Decision Stack, Tentative Choices, Backtrack Points, Abandoned Paths, Next Steps

class TradeoffHandoff(Handoff):
    DEFAULT_TITLE = "Trade-off Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Decision to Make, Objectives & Priorities, Options Evaluated, Frontier, Leaning / Chosen, Open Questions

class GoalStackHandoff(Handoff):
    DEFAULT_TITLE = "Goal Stack Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Root Goal, Goal Hierarchy, Active Path, Satisfied Goals, Suspended Goals, Next Steps

class CoverageHandoff(Handoff):
    DEFAULT_TITLE = "Coverage Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Objective & Scope, Coverage Map, Completed, Gaps & Skipped, Systematic Next

class BudgetBoundedHandoff(Handoff):
    DEFAULT_TITLE = "Budget-Bounded Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Objective, Budget Status, Value Delivered, Remaining Work, Cut Line, Next Steps

class MigrationHandoff(Handoff):
    DEFAULT_TITLE = "Migration Handoff"
    def default_sections(self) -> dict[str, str]: ...   # Target State, Current State, Completed Migrations, Remaining Delta, Reversibility, Next Steps
```

Full section descriptions are specified in Appendix A and implemented verbatim.

#### Logic / Algorithm

1. Each `default_sections()` returns a new dict literal of decision-oriented descriptions.
2. No other methods are overridden; `__init__`, `to_context_text`, `render_section_brief`, `fill`, and `is_filled` are inherited unchanged.
3. `__all__` is extended with the ten new names.

#### Edge Cases & Error Handling

- Passing custom `sections=` still overrides the preset (inherited behavior); the subclass default applies only when `sections` is omitted.
- Returning a fresh dict each call prevents cross-instance mutation (a class-level dict constant would be a hidden shared-state bug).
- All values are plain strings, so the inherited `_coerce` never has to convert.

### 6.2 Context package export

**File(s):** `vidbyte/context/__init__.py`
**Type:** Modified

Add the ten names to the `from vidbyte.context.handoffs import (...)` block and to `__all__`.

### 6.3 Root package export

**File(s):** `vidbyte/__init__.py`
**Type:** Modified

Add the ten names to the `from vidbyte.context import (...)` block and to `__all__`.

### 6.4 Skill doc update

**File(s):** `skills/vidbyte-sdk/handoff.md`
**Type:** Modified

Add a short "Process-shape catalog" subsection listing the ten new variants and their one-line shapes, so the doc reflects the full prebuilt set.

### 6.5 Tests

**File(s):** `tests/test_handoff_primitives.py`
**Type:** New file

Parametrized `unittest` coverage over all ten variants plus a `HandoffAgent` integration smoke test using a fake runner (mirrors `tests/test_handoff_agent.py`).

### 6.6 Verification script

**File(s):** `scripts/test_handoff_primitives.py`
**Type:** New file

Runs every case in `tests/test_handoff_primitives.py` individually with PASS/FAIL labels and an `X/Y` summary; exits non-zero on any failure (mirrors `scripts/test_handoff_agent.py`).

---

## 7. Data Model Changes

N/A — no database/schema changes. The only additions are ten in-memory `Handoff` subclasses (Section 6.1). No `Prompt` enum or asset changes.

---

## 8. API Changes

N/A for HTTP endpoints. Public **Python API** additions: ten new exported symbols — `TreeSearchHandoff`, `DecompositionHandoff`, `RefinementLoopHandoff`, `ConstraintSatisfactionHandoff`, `BacktrackingHandoff`, `TradeoffHandoff`, `GoalStackHandoff`, `CoverageHandoff`, `BudgetBoundedHandoff`, `MigrationHandoff` — importable from `vidbyte` and `vidbyte.context`. All additive and backward compatible.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/handoff-primitive-catalog.md` | This design doc (first commit) |
| MODIFY | `vidbyte/context/handoffs.py` | Add ten process-shape `Handoff` subclasses + extend `__all__` |
| MODIFY | `vidbyte/context/__init__.py` | Export the ten new variants |
| MODIFY | `vidbyte/__init__.py` | Root exports for the ten new variants |
| MODIFY | `skills/vidbyte-sdk/handoff.md` | Document the expanded process-shape catalog |
| CREATE | `tests/test_handoff_primitives.py` | Unit + integration tests for the ten variants |
| CREATE | `scripts/test_handoff_primitives.py` | Phase 5 verification script |

---

## 10. Testing Plan

All tests use Python `unittest` (`IsolatedAsyncioTestCase` where async) with fake runners, no network. `ALL_NEW` denotes the list of the ten new classes; `ALL_PREBUILTS` denotes those ten plus the three from #105.

### Unit Tests

- `it('every new variant exposes a non-empty default_sections map')` — [Edge Case] (iterates the 10-item list)
- `it('every prebuilt section map is pairwise distinct across all 13')` — [Silent Failure] (catches copy-paste duplication between variants)
- `it('every new variant fill() returns an instance of the same subclass')` — [Silent Failure] (a base-class rebuild would silently downcast)
- `it('every new variant fill() sets metadata["filled"]=True')` — [Hidden Assumption]
- `it('every new variant satisfies the ContextItem protocol')` — [Hidden Assumption]
- `it('default_sections returns a fresh dict so mutating one instance does not affect another')` — [Hidden Failure] (guards against a class-level shared dict)
- `it('to_context_text renders the title and every section header for a representative variant')` — [Edge Case]
- `it('render_section_brief lists every section title for a representative variant')` — [Silent Failure] (a dropped section would shrink the brief silently)
- `it('every new variant has a DEFAULT_TITLE distinct from the base Handoff default "Handoff"')` — [Hidden Assumption]
- `it('each new variant is the same object when imported from vidbyte and from vidbyte.context')` — [Hidden Assumption]
- `it('constructing a variant with explicit sections overrides the preset')` — [Edge Case]

### Integration Tests

- `it('HandoffAgent(TreeSearchHandoff(), fake_runner).generate_handoff(...) returns a filled TreeSearchHandoff with parsed sections')` — [Hidden Assumption] (the variant flows through the unchanged agent path end-to-end). Fake runner emits `## <Title>` blocks for the variant's sections; assert the parsed content lands in the right sections and the returned type is the variant.
- Silent-failure path in integration: the parsed section content must map to the correct titles for a variant whose titles contain punctuation (e.g. "Pruned / Dead Branches", "Trade-offs Made") — [Silent Failure]. Use `TreeSearchHandoff`/`ConstraintSatisfactionHandoff` to exercise slashes and hyphens in headers.
- Mock vs real: fake runner only; no provider calls.

### Manual / QA Test Cases

1. Given `from vidbyte import TreeSearchHandoff`, when `TreeSearchHandoff().to_context_text()` is rendered, then it contains `## Frontier` and `## Pruned / Dead Branches` — [Edge Case: punctuated section titles].
2. Given a `BudgetBoundedHandoff()` produced by an agent, when fed into a fresh `Agent(context_items=[doc])`, then the doc's content appears in that agent's context — [Hidden Assumption: produced doc is reusable as context].
3. Given `ConstraintSatisfactionHandoff(sections={"Only": "x"})`, when constructed, then `sections` is exactly `{"Only": "x"}` (preset not applied) — [Edge Case: explicit override].

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | 3.11+ | Types, unittest | None |
| `vidbyte.context.handoffs.Handoff` (from PR #105) | branch `feat/handoff-agent` | Base class subclassed here | Medium — this PR is unmergeable to `main` until #105 lands; mitigated by stacking |

No new third-party packages.

---

## 12. Rollout & Deployment

- No feature flags. Purely additive, backward-compatible Python API.
- **Stacked PR**: base branch is `feat/handoff-agent`. Merge order: PR #105 → `main`, then retarget this PR's base to `main` and merge. If #105 changes the `Handoff` base API before merging, rebase this branch on the updated `feat/handoff-agent`.
- Not a breaking change. Rollback: revert this PR; no migrations or persisted state.

---

## 13. Open Questions

- [ ] Confirm the stacked-PR approach (base = `feat/handoff-agent`) is acceptable, vs. waiting for #105 to merge and then branching from `main`. Current decision: stack, because it lets tests run now and produces a clean non-duplicating diff — matching the request.
- [ ] Scope is the ten process-shape variants from the latest discussion (not the earlier domain set: Browser/Backend/Math/Physics/Security/etc.). Confirm domain variants are a separate future PR.
- [ ] Should the three existing prebuilts and these ten be grouped/segmented in `__all__` or kept flat-alphabetical? Current decision: keep flat, consistent with existing style.

---

## 14. Alternatives Considered

### Alternative 1: Branch from `main` and add the files anyway
- What: create the new subclasses on a branch off `main`.
- Why rejected: `Handoff` doesn't exist on `main` yet, so the module would fail to import and no test could pass — violating the Phase 5 gate. Stacking on `feat/handoff-agent` is the only way to satisfy "where they would be if the old PR merged" while keeping the suite green.

### Alternative 2: A separate module (e.g. `vidbyte/context/handoff_catalog.py`)
- What: put the ten classes in a new file.
- Why rejected: the requester asked for the code "where they would be if the old PR merged into main" — that is `handoffs.py`, alongside the existing prebuilts. A separate module would fragment the catalog.

### Alternative 3: Extend `tests/test_handoff_agent.py` instead of a new test file
- What: add the new tests to #105's test module.
- Why rejected: keeping `tests/test_handoff_primitives.py` separate makes this PR self-contained, avoids merge churn on #105's file, and cleanly maps to its own verification script.

### Alternative 4: Add domain variants (Browser, Math, Physics, Security, …) in the same PR
- What: implement the earlier domain-shaped set too.
- Why rejected: the latest request scoped this to the ten process-shape variants; bundling more would enlarge the diff and mix two distinct catalogs. Domain variants can be a follow-up.

---

## Appendix A — Full section maps

Each entry is `Section Title → guidance description` and is implemented verbatim in `default_sections()`.

**TreeSearchHandoff** — *search frontier*
- Search Goal → The goal the search is trying to reach and what a solution looks like.
- Frontier → Open branches still worth expanding, ranked by promise.
- Explored Branches → Paths already taken and their evaluated scores or outcomes.
- Pruned / Dead Branches → Branches abandoned and why, so they are not re-explored.
- Best So Far → The strongest complete or partial solution found to date.
- Next Expansion → Which frontier node to expand next, and the reason.

**DecompositionHandoff** — *subproblem tree*
- Top-Level Problem → The overall problem being decomposed.
- Decomposition → How the problem was split into subproblems (the tree).
- Solved Subproblems → Which subproblems are done and their results.
- Open Subproblems → Which subproblems remain and how they depend on each other.
- Composition Status → How solved parts combine and what blocks final assembly.
- Next Steps → The next subproblem to tackle or composition step to perform.

**RefinementLoopHandoff** — *iteration journal*
- Objective → What the work product needs to achieve.
- Current Draft State → Where the artifact stands right now.
- Iteration Log → Each refinement pass: what was critiqued and what changed.
- Open Critiques → Known problems identified but not yet addressed.
- Convergence Status → Whether quality is improving, plateauing, or oscillating.
- Next Revision → The next change to make to the draft.

**ConstraintSatisfactionHandoff** — *constraint ledger*
- Objective → The goal the solution must achieve.
- Constraints → The full set of requirements, each marked satisfied, violated, or unknown.
- Current Candidate → The working solution under evaluation.
- Conflicts & Tensions → Constraints that pull against one another.
- Trade-offs Made → Which constraints were relaxed or prioritized, and why.
- Next Steps → What to adjust to satisfy the remaining constraints.

**BacktrackingHandoff** — *decision stack*
- Objective → The goal being pursued through a sequence of choices.
- Decision Stack → Ordered choices committed to reach the current state.
- Tentative Choices → Decisions made but not yet confirmed.
- Backtrack Points → Where to safely revert if the current path fails.
- Abandoned Paths → Choices already undone and the reason.
- Next Steps → The next choice to commit or path to explore.

**TradeoffHandoff** — *Pareto frontier*
- Decision to Make → The decision that requires balancing competing objectives.
- Objectives & Priorities → The competing goals and their relative weights.
- Options Evaluated → Candidate options and how each scores against the objectives.
- Frontier → The non-dominated options still worth considering.
- Leaning / Chosen → The current preferred option and its justification.
- Open Questions → What remains unresolved before committing.

**GoalStackHandoff** — *goal hierarchy*
- Root Goal → The top-level goal everything serves.
- Goal Hierarchy → The tree of goals and their subgoals.
- Active Path → The current chain from the root to the goal being worked now.
- Satisfied Goals → Completed subgoals and their outputs.
- Suspended Goals → Goals paused while awaiting a prerequisite.
- Next Steps → The next subgoal to pursue.

**CoverageHandoff** — *coverage map*
- Objective & Scope → The space that must be fully covered.
- Coverage Map → Regions or items marked done, pending, or skipped.
- Completed → What has been visited and the result for each.
- Gaps & Skipped → What remains and why anything was skipped.
- Systematic Next → The next region to cover and the ordering rule.

**BudgetBoundedHandoff** — *budget curve*
- Objective → The goal being pursued under a fixed budget.
- Budget Status → Resources consumed versus remaining (tokens, time, calls, or cost).
- Value Delivered → What has been accomplished so far, ranked by importance.
- Remaining Work → What is left, ordered by value per unit cost.
- Cut Line → What to drop first if the budget runs out.
- Next Steps → The highest-value work to do next.

**MigrationHandoff** — *state delta*
- Target State → The end-state the system is being migrated toward.
- Current State → Where the system is now, mid-transition.
- Completed Migrations → Steps already applied.
- Remaining Delta → The gap between the current and target states.
- Reversibility → What is safely revertible versus the point of no return.
- Next Steps → The next migration step to apply.
