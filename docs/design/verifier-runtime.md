# Design Doc: Verifier Runtime

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-20
**Last Updated:** 2026-08-20

---

## 1. Overview

This adds a verifier runtime to the SDK: a set of eight small, independently
configured pillars — target resolution, verifiers, a collection that runs
them, a gate, a verdict policy, a feedback channel, a repair strategy, a
termination budget, and a ledger — orchestrated by one `AgentVerifierRuntime`
class. It plugs into the existing linear `AgentRuntime` at the same two
finalization boundaries `AgentLoopSettingsOutputContract` already uses, so a
run cannot finish while its own configured mechanical checks (a test suite, a
schema validator, a compiler) are failing. Unset, it is a complete no-op —
every existing agent is unaffected.

---

## 2. Goals & Non-Goals

### Goals
- Ship all eight pillars as real, working classes in
  `vidbyte/agents/runtimes/verifier/`, each with a validated `Params`
  dataclass and full method bodies (no `...` stubs) for every path except the
  one explicitly deferred below.
- Wire `AgentVerifierRuntime` into `AgentLoopSettings`, `BaseAgent`, and the
  linear `AgentRuntime` exactly where `output_contract` is wired today, so the
  integration is additive and default-off.
- Add eight new `ContextItem` primitives in `vidbyte/context/primitives/verifier.py`
  so a verifier's history, regressions, diagnostics, budget, trend, scope,
  tamper baseline, and flake status can be published into an agent's context
  window via the existing `ContextManager.upsert()` registry.
- Leave the package in a runnable end-to-end state: a developer can construct
  `VerifierRuntimeSettings` with a real `Verifier` subclass, attach it to
  `AgentLoopSettings`, and get a working reject-and-continue loop today.

### Non-Goals
- No new test files (per the `design-doc-no-tests` workflow). Existing CI,
  lint, and packaging gates still run and must stay green.
- No concrete production-grade `Verifier` subclasses for every `VerifierKind`
  (`TestSuiteVerifier`, `SchemaVerifier`, etc.) beyond one minimal, generic
  `CallableVerifier` used to prove the collection actually runs something.
  The fifteen-item catalog from the design conversation is future work.
- `RepairMode.PARALLEL_BRANCHING` is declared in the enum and validated in
  `VerifierRepairStrategyParams`, but `VerifierRepairStrategy._parallel_branch`
  raises `NotImplementedError` — session forking is not a confirmed capability
  of this runtime today, and faking it would be worse than naming the gap.
- No YAML/declarative-config resolution for verifiers (the "Declarative Config
  Resolution" field-guide entry governs that path; it is out of scope until a
  registry is actually needed).
- No tuning of the actual decision thresholds (plateau patience, minimize
  logic, flake detection window). These are implemented with a straightforward
  first-pass rule and are the subject of the algorithm-formalization follow-up
  named at the end of this doc.

---

## 3. Background & Context

This follows an extended design conversation (this thread) that arrived at
eight pillars for a "verifier-in-the-loop convergence" runtime: a loop that
regenerates a working artifact against a mechanical check — a compiler, a
test suite, a schema validator — until it passes or a budget runs out,
structurally distinct from an LLM-critiquing-LLM loop because the check has no
blind spots correlated with the generator's.

The SDK already has a structurally adjacent mechanism —
`AgentLoopSettingsOutputContract` (`vidbyte/agents/contract.py`) — but it is
explicitly an **effort floor** system ("has the agent tried hard enough"),
not a **correctness** system ("is the agent's output actually right"). The
`output-contracts` skill guide lists "semantic / schema contracts" as
deferred and "LLM-as-judge quality checks" as out of scope. There is no
existing seam where finalization is gated on a tool's own pass/fail verdict
rather than a cumulative counter.

This PR builds that missing seam as its own runtime-adjacent subsystem rather
than folding it into `OutputContract`, because a verifier's result is not
monotonic (a repair can un-pass a previously passing check) and floors are.

---

## 4. Requirements

### Functional Requirements
1. `VerifierRuntimeSettings(verifier_runtime=...)` is a new optional field on
   `AgentLoopSettings`, validated at construction the same way
   `output_contracts` is.
2. Non-linear runtimes reject a configured, active `verifier_runtime` at
   `BaseAgent` construction, mirroring the existing `output_contract.active()`
   guard in `vidbyte/agents/base.py`.
3. The linear `AgentRuntime` calls `AgentVerifierRuntime.on_finalization_attempt`
   at both existing finalization boundaries (no-tool-calls / `isDone`) before
   allowing a run to finish, when a verifier runtime is configured.
4. A rejected finalization attempt injects feedback (per
   `VerifierRuntimeFeedbackParams`) and continues the loop; an exhausted
   budget stops the run with a new `AgentStopReason.VERIFICATION_FAILED`.
5. Every attempt is recorded in a `VerifierLedger`; `AgentResult.metadata`
   gains a `verifier_evaluations` entry mirroring the existing
   `contract_evaluations` entry.
6. `VerifierTargetResolver` can pull specific or all `ContextItem`s from the
   agent's `ContextManager` into the `VerifierTarget` handed to verifiers,
   and gracefully returns nothing when no context manager is attached.
7. When `VerifierLedgerParams.publish_to_context=True`, the ledger's eight
   context primitives are published via `ContextManager.upsert()` (never
   `add()`/`extend()`) so republishing on every attempt updates the same eight
   slots instead of growing the context window without bound.
8. Every `Params` dataclass validates itself in `__post_init__` and raises
   `ConfigurationError` (the repo's existing exception) on invalid
   configuration, including `VerifierCollectionParams` rejecting any
   `Verifier` whose `kind` is not a `VerifierKind` member.

### Non-Functional Requirements
- **Performance:** verifier execution within a tier runs concurrently
  (`asyncio.gather`) when `execution_mode=PARALLEL_WITHIN_TIER`; tiers
  themselves run sequentially since later tiers may depend on earlier ones.
- **Cost accounting:** budget cost checks reuse the runtime's existing
  `_cost_spent_usd()` (backed by `CostBudgetMiddleware.estimated_spend_usd`)
  per the `runtime-boundaries` field-guide entry — no new cost computation is
  introduced.
- **Observability:** every verifier verdict, aggregated decision, and repair
  outcome is captured in the ledger and surfaced through `report()`.
- **Reliability:** the entire subsystem is a no-op when unconfigured — zero
  behavioral change for any agent not opting in.
- **Style:** class-bound helpers throughout (per the `class-bound-helpers`
  field-guide entry) — no bag of module-level free functions.

---

## 5. High-Level Design

```
AgentLoopSettings(verifier_runtime=VerifierRuntimeSettings(...))
        |
        v  base.py construction: reject if non-linear runtime and active()
        |
AgentRuntime.__init__(verifier_runtime=...)
        |
        v  at each finalization boundary (no-tool-calls, isDone)
        |
AgentVerifierRuntime.on_finalization_attempt(context)
        |
   VerifierTargetResolver.resolve(context) -> VerifierTarget (+ context primitives)
        |
   VerifierCollection.run(target) -> tuple[VerifierVerdict, ...]   (tiered, dependency-ordered)
        |
   VerifierVerdictPolicy.aggregate(verdicts) -> AggregatedVerdict
        |
   VerifierLedger.record(attempt)          -> optionally upserted into ContextManager
        |
   VerifierRuntimeGate.decide(verdict, attempt_number, budget, ledger) -> GateDecision
        |
   ALLOW_FINALIZE ---------------------------------> run finishes normally
   REJECT_AND_CONTINUE -> Feedback.emit() + RepairStrategy.repair() -> loop continues
   REJECT_AND_TERMINATE -> AgentStopReason.VERIFICATION_FAILED
```

Components created: the whole `vidbyte/agents/runtimes/verifier/` package
(12 files) and `vidbyte/context/primitives/verifier.py` (1 file). Components
modified: `vidbyte/lib/dataclasses/agents.py` (new stop reason),
`vidbyte/agents/settings/loop.py` (new field + validation),
`vidbyte/agents/base.py` (construction guard + kwarg threading),
`vidbyte/agents/runtime.py` (constructor param, two boundary calls, metadata
publish helper), `vidbyte/agents/runtimes/__init__.py`,
`vidbyte/agents/__init__.py`, `vidbyte/context/primitives/__init__.py` (all
three: re-export additions only).

The central decision already settled in conversation: eight pillars, each with
its own `Params` dataclass performing its own `__post_init__` validation
(mirroring `ContextManager`'s own `@dataclass` + `__post_init__` pattern, not
the hand-written-`__init__`-plus-`_validate()` pattern `ToolErrorPolicy` uses)
— the user specifically asked for the dataclass itself to own the check.

---

## 6. Detailed Design

### 6.1 `vidbyte/agents/runtimes/verifier/types.py`

**File(s):** new
**Type:** New file

#### What it does
Per review feedback on PR #349 ("all dataclasses in this PR should be in
vidbyte/lib/dataclasses"), this file now only defines `VerifierExecutionMode`,
`GateTrigger`, and `GateDecision` — the three enums that remain eager
defaults exclusively on `VerifierCollectionParams`/`VerifierRuntimeGateParams`
(owned by `collection.py`/`gate.py`, neither modified by the move). Every
other enum this file used to define — `VerifierKind`, `VerifierCostClass`,
`TargetResolutionMode`, `VerdictStrategy`, `FeedbackContentMode`,
`FeedbackDelivery`, `RepairMode`, `BudgetExhaustedAction` — and every shared
dataclass — `VerifierTarget`, `VerifierVerdict`, `AggregatedVerdict`,
`VerificationAttempt`, `ResolutionContext`, `RepairContext`, `RepairOutcome`,
`VerifierRuntimeOutcome` — now lives in `vidbyte/lib/dataclasses/verifier.py`
and is re-exported here for every existing import site in this package
(including `collection.py` and `gate.py`, whose import lines are unchanged).

#### Interface / API
As specified in this conversation's interface-sketch turns, with one addition:
`VerificationAttempt` and `ResolutionContext` both gain `cost_spent_usd: float
= 0.0`, populated by the caller (`runtime.py`) from the existing
`_cost_spent_usd()` helper — not computed inside the verifier package.

#### Logic / Algorithm
Pure data; no behavior beyond dataclass field defaults.

#### Edge Cases & Error Handling
N/A — validation lives on the `Params` dataclasses that consume these types,
not here.

---

### 6.2 `vidbyte/agents/runtimes/verifier/verifier.py`

**File(s):** new
**Type:** New file

#### What it does
`Verifier` (base class: `async check(target) -> VerifierVerdict`,
`applicable(target) -> bool`, `describe() -> str`). `VerifierParams`
(validated dataclass: `name`, `kind: VerifierKind`, `cost_class`, `tier`,
`blocking`, `depends_on`, `timeout_seconds`) now lives in
`vidbyte/lib/dataclasses/verifier.py`, per review feedback on PR #349. Also
ships one concrete,
generic subclass — `CallableVerifier` — that wraps a user-supplied
`Callable[[VerifierTarget], Awaitable[VerifierVerdict] | VerifierVerdict]` so
the collection is runnable end-to-end without requiring a full
`TestSuiteVerifier` implementation in this PR.

#### Interface / API
Per the interface-sketch turns, plus:
```python
class CallableVerifier(Verifier):
    def __init__(self, params: VerifierParams, fn: Callable[[VerifierTarget], Any]) -> None: ...
    async def check(self, target: VerifierTarget) -> VerifierVerdict: ...
```

#### Logic / Algorithm
`CallableVerifier.check` calls `fn(target)`, awaits it if it returned a
coroutine, and normalizes a bare `bool` return into a minimal `VerifierVerdict`
(so the simplest possible caller can pass a plain predicate function).

#### Edge Cases & Error Handling
`fn` raising is not swallowed — it propagates to `VerifierCollection.run`,
which converts it into a failing `VerifierVerdict` with the exception text as
diagnostics rather than crashing the run (a verifier that cannot execute is
a failed check, not a runtime error).

---

### 6.3 `vidbyte/agents/runtimes/verifier/collection.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierCollectionParams` (validates non-empty, unique names, every `kind`
recognized, every `depends_on` resolvable, no dependency cycle) and
`VerifierCollection` (tiers verifiers by `depends_on` into a topological
order, runs each tier per `execution_mode`, short-circuits remaining tiers on
a blocking failure when `stop_on_first_blocking_failure=True`).

#### Logic / Algorithm
1. `_topological_tiers()` — Kahn's algorithm over `depends_on`, grouping
   same-depth nodes into one tier so they can run concurrently.
2. `run(target)` — for each tier in order, `_run_tier`; if any blocking
   verdict in the tier failed and `stop_on_first_blocking_failure`, stop
   evaluating later tiers but still return every verdict gathered so far.
3. `_run_tier` — skips verifiers whose `applicable(target)` is `False`;
   dispatches remaining verifiers concurrently (`PARALLEL_WITHIN_TIER`/
   `COST_ORDERED`) or sequentially (`SEQUENTIAL`); `COST_ORDERED` sorts the
   tier by `VerifierCostClass` (`LEAN` first) before dispatch.

#### Edge Cases & Error Handling
Cycle detection raises `ConfigurationError` at construction (in
`VerifierCollectionParams.__post_init__`), not at run time. A verifier that
raises during `check()` is caught inside `_run_tier` and converted to a
failing verdict — one bad verifier cannot take down the whole collection run.

---

### 6.4 `vidbyte/agents/runtimes/verifier/target.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierTargetResolver`, implementing the five `TargetResolutionMode`
resolvers plus the context-primitive port-in. `ContextPrimitiveSelectorParams`
and `VerifierTargetResolverParams` now live in
`vidbyte/lib/dataclasses/verifier.py`, per review feedback on PR #349.

#### Logic / Algorithm
`resolve(context)` dispatches to the per-mode private resolver, then calls
`_resolve_context_primitives(context)` and attaches the result via
`dataclasses.replace`. Context-primitive resolution reads
`context.context_manager.items()` (unmanaged pool) and
`.registry_items()` (managed pool), filters by `include_kinds`/
`include_managed_ids` unless `include_all`, and returns `()` when
`context.context_manager` is `None` or `params.context_primitives` is `None`
— the "not guaranteed" case from the design conversation.

#### Edge Cases & Error Handling
`STRUCTURED_SUBMISSION` mode reads the most recent tool call named
`submission_tool_name` from `context.messages`; if none exists yet (first
iteration), returns an empty `VerifierTarget` rather than raising — the gate's
`should_fire` is what decides whether verification even applies at this point
in the loop, not the resolver.

---

### 6.5 `vidbyte/agents/runtimes/verifier/gate.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierRuntimeGateParams` + `VerifierRuntimeGate`. `should_fire` checks the
configured `GateTrigger` against the current `ResolutionContext`. `decide`
combines an `AggregatedVerdict` with the budget/ledger state into one of the
three `GateDecision` values.

#### Logic / Algorithm
`decide`: if `verdict.passed`, `ALLOW_FINALIZE`. Else, ask
`budget.exhausted(ledger)`; if exhausted, resolve `on_exhausted` —
`FAIL`/`DOWNGRADE_TO_ADVISORY` both resolve here (`DOWNGRADE_TO_ADVISORY`
returns `ALLOW_FINALIZE` but the caller is expected to surface the advisory
verdicts in the result metadata, which the ledger's `report()` already does),
`ESCALATE_TO_HUMAN` and plain exhaustion both return
`REJECT_AND_TERMINATE`. Otherwise `REJECT_AND_CONTINUE`.

#### Edge Cases & Error Handling
`ON_EXPLICIT_SIGNAL` trigger's `should_fire` checks the latest tool call name
against `explicit_signal_tool_name`; absent that call, returns `False` so
ordinary iterations are never gated.

---

### 6.6 `vidbyte/agents/runtimes/verifier/verdict.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierVerdictPolicy`, implementing all five `VerdictStrategy` aggregations.
`VerifierVerdictPolicyParams` now lives in `vidbyte/lib/dataclasses/verifier.py`,
per review feedback on PR #349.

#### Logic / Algorithm
`ALL_BLOCKING_MUST_PASS`: passed iff every `blocking=True` verdict passed;
non-blocking failures go to `AggregatedVerdict.advisory`.
`ANY_BLOCKING_PASSES`: passed iff at least one blocking verdict passed.
`K_OF_N`: passed iff `count(passed) >= minimum_passing`.
`WEIGHTED_SCORE_THRESHOLD`: passed iff the weighted mean of
`verdict.score or (1.0 if verdict.passed else 0.0)` meets `score_threshold`.
`UNANIMOUS_ENSEMBLE`: passed iff every verdict agrees (all pass or all fail);
disagreement itself is surfaced as a distinct `AggregatedVerdict.passed=False`
with a diagnostic noting the split, per the ensemble-verifier idea from the
design conversation.

#### Edge Cases & Error Handling
An empty `verdicts` sequence (collection had nothing applicable) aggregates to
`passed=True` — nothing configured to check means nothing blocking the run,
consistent with `active()` being the real gate for "is this configured at
all."

---

### 6.7 `vidbyte/agents/runtimes/verifier/feedback.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierRuntimeFeedbackParams` + `VerifierRuntimeFeedback`, implementing
four `FeedbackContentMode` values and truncation. `MINIMIZED_COUNTEREXAMPLE`
and `SCORE_TREND_ONLY` (plus the now-unused `minimize_counterexamples` field)
were removed per review feedback on PR #349.

#### Logic / Algorithm
`emit(verdict)` dispatches on `content_mode`. `RAW_VERDICT` joins every failed
verdict's `diagnostics`. `CUSTOM_MESSAGE` renders `message_template` with
`{failure_count}`/`{verifier_names}` substitutions via `str.format_map` with a
defaulting mapping (missing keys render empty rather than raising).
`STRUCTURED_PAYLOAD` renders only `structured_fields` from each failed
verdict as a compact `field=value` block. `RAW_AND_CUSTOM` concatenates the
custom message and the raw payload. `_truncate` applies
`max_diagnostics_chars` last, on the final rendered string, regardless of
mode.

#### Edge Cases & Error Handling
`STRUCTURED_PAYLOAD` with a `structured_fields` entry the verdict doesn't
carry renders `field=<absent>` rather than raising — a misconfigured field
name should be visible in the feedback text, not crash the run.

---

### 6.8 `vidbyte/agents/runtimes/verifier/repair.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierRepairStrategyParams` + `VerifierRepairStrategy`, implementing three
of the four `RepairMode` values in full; `PARALLEL_BRANCHING` raises
`NotImplementedError` (see Non-Goals).

#### Logic / Algorithm
`IN_PLACE_CONTINUE`: returns a `RepairOutcome` with one injected user message
carrying the feedback text; `restart_session=False`.
`FRESH_RESTART_WITH_SUMMARY`: calls `_summarize_history(ledger)` (renders
each past attempt's number, pass/fail, and top failing verifier names into a
short digest) and returns `restart_session=True` with that summary as the
sole injected message.
`TARGETED_SCOPE`: when `scope_lock=True`, extracts file/symbol references
from the failing verdicts' `diagnostics` via a simple path-looking-token
regex, and sets `RepairOutcome.scope_lock` to that tuple; the message is the
same as `IN_PLACE_CONTINUE`'s.
`PARALLEL_BRANCHING`: raises `NotImplementedError` naming the missing
capability, per the Non-Goals section.

#### Edge Cases & Error Handling
`TARGETED_SCOPE`'s regex extraction finding nothing yields `scope_lock=()` —
an empty lock is not a lock (no restriction) — never crashes or blocks
repair on failure to find a path.

---

### 6.9 `vidbyte/agents/runtimes/verifier/budget.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierRuntimeBudget`, consuming `VerifierRuntimeBudgetParams`. Per review
feedback on PR #349, the params dataclass itself now lives in
`vidbyte/lib/dataclasses/verifier.py` (alongside `BudgetExhaustedAction`,
also moved there), re-exported from `types.py` for every existing import
site — this file only defines the behavior class.

#### Logic / Algorithm
`exhausted(ledger)` is `_attempts_exhausted or _time_exhausted or _plateaued
or _flaky_exhausted or _score_floor_exhausted or
_consecutive_failures_exhausted`. `_attempts_exhausted`: `len(ledger.history())
>= max_attempts`. `_time_exhausted`: `now - ledger.history()[0].started_at >=
max_total_seconds` when set. `_plateaued`: when `plateau_patience` is set,
true when the last `plateau_patience` attempts' aggregate pass rate (fraction
of blocking verdicts passed) is non-increasing — the "first-pass rule"
flagged as a formalization target in Non-Goals. `_flaky_exhausted`: true when
`ledger.flaky_verifiers(min_flips=max_flaky_flips)` is non-empty — a verifier
that keeps flipping won't be fixed by more attempts. `_score_floor_exhausted`:
true when the latest attempt's lowest reported `VerifierVerdict.score` is
below `min_score_floor` — distinct from `_plateaued`, which looks at the
aggregate blocking pass rate, not one verifier's numeric score.
`_consecutive_failures_exhausted`: true when any single verifier's trailing
run of failures (most recent attempts, back to its last pass) reaches
`max_consecutive_failures` — catches one check stuck failing while others
pass, which `_plateaued` can mask. Deliberately no cost-based check: cost
ceilings are a general agent/loop concern (`CostBudgetMiddleware`), not a
verifier-specific one, per review feedback on PR #349.

#### Edge Cases & Error Handling
All six sub-checks short-circuit when their governing field is unset, and the
history-based ones short-circuit on an empty ledger (`False` — nothing to
exhaust on the first attempt).

---

### 6.10 `vidbyte/agents/runtimes/verifier/ledger.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierLedgerParams` + `VerifierLedger` + `VerifierLedgerStatistics`. Per
review feedback on PR #349, the base `VerifierLedger` now handles only the
ledger and its metadata: `record()`, `history()`, `last()`, `report()`.
`VerifierLedgerStatistics(VerifierLedger)` is the subclass that derives every
history-aware statistic — `score_trend`, `regressions_since`,
`flaky_verifiers`, `baseline_snapshot`, `tamper_check` — plus
`to_context_items()`, since building context items needs those statistics.
`AgentVerifierRuntime` constructs a `VerifierLedgerStatistics`, so every
pillar that receives "the ledger" (gate, budget) is actually handed the
statistics subclass.

#### Logic / Algorithm
`record` appends to an internal `list[VerificationAttempt]`.
`score_trend(name)` collects `verdict.score` across attempts for verifiers
matching `name`, skipping `None` scores. `regressions_since(n)` diffs
attempt `n`'s per-verifier pass/fail map against the latest attempt's,
returning names that flipped pass→fail. `flaky_verifiers(min_flips)` counts
sign changes in each verifier's pass/fail sequence across history: `>=
min_flips` flips flags it. `baseline_snapshot(target)` sha256-hashes each
`target.file_paths` entry's content at first call and caches it;
`tamper_check` re-hashes and returns paths whose hash changed. `report()`
mirrors `AgentLoopSettingsOutputContract.report()`'s shape. `to_context_items`
builds all eight `ContextItem`s from current state, only including primitives
whose backing data is non-empty (an empty ledger publishes nothing).

#### Edge Cases & Error Handling
`baseline_snapshot` on a `target` with no `file_paths` (e.g. text-only
targets) returns `{}` — tamper detection is inert for non-file targets, not
an error.

---

### 6.11 `vidbyte/agents/runtimes/verifier/settings.py`

**File(s):** new · **Type:** New file

#### What it does
`VerifierRuntimeSettings` (the thin wrapper with `active()`), exactly as
specified in the interface turns. `VerifierRuntimeSettingsParams` (the
container) now lives in `vidbyte/lib/dataclasses/verifier.py`, per review
feedback on PR #349 — its own field annotations reference `VerifierCollection`/
`VerifierRuntimeGate`/etc. only under `TYPE_CHECKING`, so the move introduces
no cycle back into the pillar files.

---

### 6.12 `vidbyte/agents/runtimes/verifier/runtime.py`

**File(s):** new · **Type:** New file

#### What it does
`AgentVerifierRuntime`, the orchestrator. One instance per `AgentRuntime`
run, constructed lazily on first use inside `AgentRuntime.__init__`.

#### Logic / Algorithm
`on_finalization_attempt(context)` exactly as specified in the interface
turns: gate check → resolve target → run collection → aggregate → record →
gate decide → (on reject) feedback + repair. Adds: when
`ledger_params.publish_to_context` and `context.context_manager is not None`,
upserts `ledger.to_context_items(...)` after recording.

---

### 6.13 `vidbyte/context/primitives/verifier.py`

**File(s):** new · **Type:** New file

#### What it does
The eight `ContextItem` dataclasses from the design conversation:
`VerifierHistoryContextItem`, `VerifierRegressionContextItem`,
`VerifierDiagnosticContextItem`, `VerifierBudgetContextItem`,
`VerifierTrendContextItem`, `VerifierScopeContextItem`,
`VerifierTamperContextItem`, `VerifierFlakeContextItem`. Each carries its
fixed intro sentence as a literal directly inside its own `to_context_text()`
(per review feedback on PR #349 — not as a module-level constant), alongside
`primitive_id` and `primitive_frozen`, matching the shape every other file in
`vidbyte/context/primitives/` already uses.

---

### 6.14 Existing-file wiring

**`vidbyte/lib/dataclasses/agents.py`** — add
`VERIFICATION_FAILED = "verification_failed"` to `AgentStopReason`.

**`vidbyte/agents/settings/loop.py`** — new `verifier_runtime:
"VerifierRuntimeSettings | None" = None` constructor param, stored as
`self.verifier_runtime`, validated by a new `_validate_verifier_runtime`
that delegates to `vidbyte.agents.settings.verifier.validate_verifier_runtime`
(type check only — the settings object validates its own contents in its own
`__post_init__` chain). Per review feedback on PR #349, the type check itself
lives in the new `vidbyte/agents/settings/verifier.py` (see below), not
inline in this file, matching how `ToolErrorPolicy`/`ToolSettings` each own
their nested-settings surface in their own file.

**`vidbyte/agents/settings/verifier.py`** (new) — `validate_verifier_runtime()`,
the one function `AgentLoopSettings._validate_verifier_runtime` calls.

**`vidbyte/lib/dataclasses/verifier.py`** (new) — `BudgetExhaustedAction` +
`VerifierRuntimeBudgetParams`, moved out of
`vidbyte/agents/runtimes/verifier/{types,budget}.py` per review feedback on
PR #349 so the validated dataclass lives with the SDK's other lib-level
dataclasses; `types.py` re-exports `BudgetExhaustedAction` for every existing
import site.

**`vidbyte/agents/base.py`** — one new guard alongside the existing seven at
lines 102-194: reject a non-`LINEAR` runtime with an active `verifier_runtime`,
identical message shape to the existing guards. One new line in `_runtime()`'s
`kwargs` block (mirrors `kwargs["output_contract"] = ...`).

**`vidbyte/agents/runtime.py`** — new constructor param
`verifier_runtime: "VerifierRuntimeSettings | None" = None`, stored as an
`AgentVerifierRuntime` instance (or `None` when inactive). Both finalization
boundaries (~457, ~592) gain a call to it, structured to run *after* the
existing `output_contract` check (output-contract effort floors gate first,
since they are cheaper and already there; the verifier gate is the new,
heavier check). New `_publish_verifier_evaluations` mirroring
`_publish_contract_evaluations`, called at the same sites.

**`vidbyte/agents/runtimes/__init__.py`, `vidbyte/agents/__init__.py`,
`vidbyte/context/primitives/__init__.py`** — re-export additions only, no
logic changes.

---

## 7. Data Model Changes

N/A — no persistent schema. `VerifierLedger` is in-memory, scoped to one
`AgentRuntime` instance's lifetime, matching how `rejections` (the
`OutputContract` counterpart) is already loop-local rather than persisted.
Ledger persistence across a resumed session is an open assumption, not solved
by this PR (see Section 12).

---

## 8. API Changes

N/A — this is an SDK library change, not a service endpoint. The
developer-facing "API" is the new constructor surface on `AgentLoopSettings`
and the twelve new public classes, covered in Section 6.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/runtimes/verifier/__init__.py` | Package exports |
| CREATE | `vidbyte/agents/runtimes/verifier/types.py` | 3 remaining enums (VerifierExecutionMode, GateTrigger, GateDecision) + re-exports |
| CREATE | `vidbyte/agents/runtimes/verifier/verifier.py` | Verifier base + CallableVerifier |
| CREATE | `vidbyte/agents/runtimes/verifier/collection.py` | VerifierCollection (not modified by the PR #349 dataclass-relocation pass) |
| CREATE | `vidbyte/agents/runtimes/verifier/target.py` | VerifierTargetResolver |
| CREATE | `vidbyte/agents/runtimes/verifier/gate.py` | VerifierRuntimeGate (not modified by the PR #349 dataclass-relocation pass) |
| CREATE | `vidbyte/agents/runtimes/verifier/verdict.py` | VerifierVerdictPolicy |
| CREATE | `vidbyte/agents/runtimes/verifier/feedback.py` | VerifierRuntimeFeedback |
| CREATE | `vidbyte/agents/runtimes/verifier/repair.py` | VerifierRepairStrategy |
| CREATE | `vidbyte/agents/runtimes/verifier/budget.py` | VerifierRuntimeBudget |
| CREATE | `vidbyte/agents/runtimes/verifier/ledger.py` | VerifierLedger + VerifierLedgerStatistics |
| CREATE | `vidbyte/agents/runtimes/verifier/settings.py` | VerifierRuntimeSettings |
| CREATE | `vidbyte/agents/runtimes/verifier/runtime.py` | AgentVerifierRuntime orchestrator |
| CREATE | `vidbyte/context/primitives/verifier.py` | 8 ledger-facing ContextItems |
| CREATE | `vidbyte/lib/dataclasses/verifier.py` | Every verifier-runtime enum + dataclass except VerifierCollectionParams (collection.py) and VerifierRuntimeGateParams (gate.py) |
| CREATE | `vidbyte/agents/settings/verifier.py` | validate_verifier_runtime |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | New AgentStopReason member |
| MODIFY | `vidbyte/agents/settings/loop.py` | New verifier_runtime field, delegates validation |
| MODIFY | `vidbyte/agents/base.py` | Non-linear guard + kwarg threading |
| MODIFY | `vidbyte/agents/runtime.py` | Constructor param + 2 boundaries + metadata publish |
| MODIFY | `vidbyte/agents/runtimes/__init__.py` | Re-export new package |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export new public symbols |
| MODIFY | `vidbyte/context/primitives/__init__.py` | Re-export new primitives |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| stdlib `asyncio` | n/a | Concurrent tier execution | None — already a runtime dependency |
| stdlib `hashlib` | n/a | Ledger tamper-check hashing | None |
| stdlib `re` | n/a | Targeted-scope path extraction | Low — best-effort heuristic, never blocking |

No new third-party dependencies.

---

## 11. Rollout & Deployment

No feature flag — the field is `None` by default, which is itself the
off-switch; every existing caller is unaffected without any flag. Not a
breaking change. No deployment ordering concerns (library, not a service).
Rollback is a plain revert; nothing this PR adds is referenced by existing
code paths unless a caller opts in.

---

## 12. Open Questions

- [ ] Should `VerifierLedger` persist across a resumed session (via
      `RunState`/`FileSessionStore`), or is a fresh ledger per process
      lifetime acceptable for v1? Left as in-memory-only in this PR.
- [ ] Plateau detection, minimization, and flake-detection thresholds are
      first-pass rules, not tuned. This is the explicit formalization
      follow-up flagged in Section 2.
- [ ] `PARALLEL_BRANCHING` repair needs a session-fork primitive this PR does
      not build — worth a dedicated design pass once the rest of the runtime
      is in use.

---

## 13. Alternatives Considered

### Alternative 1: Fold verification into `OutputContract`
- What: add a `VerifierPassed` floor type reusing the existing enforcement
  boundaries wholesale.
- Why rejected: floors are monotonic cumulative counters; a verifier's result
  is not (a repair can un-pass a previously passing check). Folding it in
  would blur a distinction `skills/output-contracts/SKILL.md` draws on
  purpose.

### Alternative 2: A new `AgentRuntimeType`
- What: a dedicated non-linear runtime type for verifier-gated execution.
- Why rejected: nothing about *who decides the next step* changes — the model
  still drives generation. Only what's allowed to end the loop changes. A new
  runtime type would pay the full non-linear-runtime rejection-matrix cost in
  `base.py` for no corresponding change in execution semantics.

### Alternative 3: Outer repair facade (regenerate whole attempts, not in-loop)
- What: wrap `arun()` entirely, verify post-hoc, restart with a summary on
  failure.
- Why rejected for this PR (not rejected outright): right for expensive or
  stateful verifiers (a full CI run, a container rebuild), and composes with
  this design rather than replacing it — `FRESH_RESTART_WITH_SUMMARY` repair
  mode is the in-loop analogue. A standalone facade is future work, not
  precluded by anything built here.
