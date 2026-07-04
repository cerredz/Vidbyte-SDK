# Design Doc: Output Contracts — Deterministic Effort Floors

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-04
**Last Updated:** 2026-07-04

---

## 1. Overview

Output contracts are a new mini-abstraction that gates when an agent is *allowed* to stop. Today an agent stops the moment it calls the internal `isDone` tool (or emits a final response with no tool calls). This change introduces `OutputContract` objects that the runtime evaluates at those termination boundaries: if any contract is unmet, the agent's attempt to finish is rejected, corrective feedback is injected into the context window, and the loop continues. This first slice ships the **deterministic effort floors** (`MinTokens`, `MinToolCalls`, `MinIterations`, `MinElapsedSeconds`) plus a dedicated constructor-level bridge class — `ContractSettingsValidator` — that guarantees a floor can never be configured in conflict with an `AgentLoopSettings` ceiling (e.g. `MinToolCalls(50)` under `max_tool_calls=10`), raising a semantic error at agent construction rather than at runtime.

---

## 2. Goals & Non-Goals

### Goals
- Introduce a public `OutputContract` abstraction with a small, termination-scoped interface (`evaluate() -> ContractVerdict`).
- Ship four deterministic effort-floor contracts that read counters the runtime already tracks: `MinTokens`, `MinToolCalls`, `MinIterations`, `MinElapsedSeconds`.
- Add an `output_contracts=` parameter to `Agent` (sibling to `agent_loop_settings=` and `middleware=`).
- Enforce contracts at the two runtime finalization boundaries via an `OutputContractGate`, injecting corrective feedback and continuing the loop when a contract is unmet.
- Add `ContractSettingsValidator`: a constructor-level bridge class whose sole responsibility is to detect and reject conflicts between contracts and loop settings, raising a semantic `ConfigurationError` subclass.
- Guarantee termination: a new `AgentStopReason.CONTRACT_UNSATISFIED` plus a `max_contract_rejections` budget so an unreachable floor can never produce an infinite loop.
- Surface `contract_evaluations` in `AgentResult.metadata` for observability.

### Non-Goals
- **Judge / LLM-based contracts** (`JudgeContract`) — deferred; the async `evaluate` signature is designed to accommodate them later with no protocol change.
- **Predicate / schema / coverage contracts** (`PredicateContract`, `SchemaContract`, `ToolInvoked`) — deferred.
- **Unifying the existing `output_schema=` into an implicit `SchemaContract`** — deferred to the quality-contracts PR.
- **`MinCompactions`** — deferred; it is the one floor that requires new runtime telemetry (a compaction counter published into `run_state`).
- **Non-linear runtimes** (actor / MCTS search) — contracts are a linear-runtime feature in v1, mirroring the existing middleware restriction.
- Changing `isDone`, provider adapters, or the context-window algorithms.

---

## 3. Background & Context

The agent loop lives in `vidbyte/agents/runtime.py` (`AgentRuntime._arun_once`). It already owns the dual of this feature: `AgentLoopSettings` (`vidbyte/agents/settings/loop.py`) define **ceilings** — `max_iterations`, `max_tokens`, `max_tool_calls` — enforced by `_budget_stop` (`runtime.py:1376`). Output contracts are the **floors + gates**: the conditions under which stopping is *permitted*.

The clean framing that bounds this feature:

> **Loop settings say when the agent MUST stop. Output contracts say when the agent MAY stop.**

Two facts from the audit make the deterministic floors the correct first slice:

1. **Zero new telemetry.** Every counter the four floors read is already live in `_arun_once`: `iteration_count`, `model_call_count`, `tokens_used`, `len(call_contexts)`, and elapsed time via `self.middleware.clock() - started_at`.
2. **A natural, provider-correct injection point.** At the `IS_DONE` boundary, `_process_tool_call` deliberately does *not* append a tool-result message for `isDone` (`runtime.py:1339`), yet the assistant message carrying the `isDone` tool-call is already in `messages`. Providers require every tool-call to be answered. So the rejection feedback *becomes* the `isDone` tool result — both the injection mechanism and the thing that keeps the transcript valid.

The user's specific architectural request: the conflict check belongs at the **constructor level**, expressed as a dedicated bridge class that couples `AgentLoopSettings` and `OutputContract` purely to raise semantic errors — not runtime logic. This doc names that class `ContractSettingsValidator`.

---

## 4. Requirements

### Functional Requirements
1. An `Agent` accepts `output_contracts: Sequence[OutputContract] = ()`.
2. When `output_contracts` is empty, agent behavior is byte-for-byte unchanged (no gate is constructed, no boundary logic runs).
3. At the `IS_DONE` boundary, before finalizing, all contracts are evaluated against a `TerminationContext` snapshot.
4. At the no-tool-calls final-response boundary, the same evaluation runs.
5. If all contracts are satisfied, the run finalizes exactly as it does today (`stop_reason` stays `IS_DONE` / `FINAL_RESPONSE`).
6. If any contract is unmet and the rejection budget is not exhausted, the runtime injects the aggregated unmet-contract feedback and continues the loop instead of returning.
7. Injection at the `IS_DONE` boundary is an error-status tool result answering the `isDone` call; at the no-tool-calls boundary it is a synthetic `user` message.
8. If the rejection budget (`max_contract_rejections`) is exhausted, the run stops with `AgentStopReason.CONTRACT_UNSATISFIED`, returning the best candidate output and the unmet-contract list in metadata.
9. Existing ceilings (`_budget_stop`) remain the hard backstop: if a ceiling is reached while chasing a floor, the run stops with the corresponding `MAX_*` reason, unmet contracts recorded in metadata.
10. `MinTokens`, `MinToolCalls`, `MinIterations`, `MinElapsedSeconds` each expose a positive-only constructor and declare the runtime dimension they bound.
11. `ContractSettingsValidator` runs during `Agent.__init__` and raises a `ConfigurationError` subclass when any effort floor's `minimum` is `>=` its paired loop-settings ceiling (strict `<` required).
12. Contracts passed to a non-linear runtime raise `ConfigurationError` at construction, mirroring the middleware restriction.
13. `AgentResult.metadata["contract_evaluations"]` lists each contract's name, satisfied flag, observed vs required values, and rejection count.

### Non-Functional Requirements
- **Performance:** deterministic floors are O(1) counter comparisons; the gate only runs at termination boundaries, never per token. Empty `output_contracts` adds no per-iteration cost.
- **Reliability:** termination is guaranteed by three independent layers (construction-time validator, runtime ceilings, rejection budget). No configuration can produce an unbounded loop.
- **Security:** no new external calls, no new credential surfaces, no changes to tool permission checks.
- **Observability:** every rejection and the final disposition are recorded in `run_state` and lifted into `AgentResult.metadata`.
- **Backward compatibility:** purely additive; all new parameters default to no-ops.

---

## 5. High-Level Design

A new sub-package `vidbyte/agents/contracts/` holds the entire abstraction, parallel to `vidbyte/agents/settings/`. It contains:

- **`base.py`** — the `OutputContract` ABC, the `ContractVerdict` result, and the `TerminationContext` read-only snapshot.
- **`floors.py`** — an `EffortFloor` base (adds a declared `dimension` + `minimum`) and the four concrete deterministic floors.
- **`validation.py`** — `ContractSettingsValidator` (the constructor-level bridge) and `ContractConfigurationError`.
- **`gate.py`** — `OutputContractGate`, the runtime-facing evaluator that decides satisfied / reject-and-continue / exhausted, and builds injection messages.

Data flow, construction time:

```
Agent(output_contracts=[...], agent_loop_settings=...)
        │
        ├─ _resolve_loop_settings()  ── AgentLoopSettings
        │
        └─ ContractSettingsValidator(settings, contracts).validate()
                 └─ raises ContractConfigurationError on min >= ceiling   [FAIL FAST]
```

Data flow, runtime (only when contracts present):

```
_arun_once loop
    │
    ├─ model calls isDone ───────────────► OutputContractGate.evaluate(TerminationContext)
    │                                           │
    │        all satisfied ──► finalize IS_DONE │
    │        unmet & budget left ──► append error tool-result for isDone; continue loop
    │        unmet & budget spent ──► finalize CONTRACT_UNSATISFIED
    │
    └─ model returns final text (no tool calls) ► same gate
             unmet & budget left ──► append synthetic user message; continue loop
```

Key design decisions:
- **Separate abstraction, not middleware.** Middleware cannot express "veto this completion and keep looping" — its non-`CONTINUE` action is `ABORT_RUN`, which *stops*. A termination gate is semantically distinct and matches the user's "mini-abstraction" intent. It reuses existing plumbing (`run_state`, the `messages` list) but is its own concept.
- **Validator is a class, at the constructor, doing nothing but conflict detection.** Per the user's steer. It holds no runtime state and performs no enforcement — it only reads two objects and raises.
- **Floors declare their `dimension`.** This makes the validator data-driven (map dimension → settings field) instead of a pile of `isinstance` branches, and lets future non-floor contracts be transparently skipped by static validation.
- **Strict `<` invariant.** Ceilings stop with `>=` at the top of the next loop, so a floor equal to its ceiling is only satisfiable by a same-iteration race. For a *deterministic* floor that is indistinguishable from broken, so `min >= ceiling` is rejected.

---

## 6. Detailed Design

### 6.1 OutputContract / ContractVerdict / TerminationContext

**File:** `vidbyte/agents/contracts/base.py`
**Type:** New file

#### What it does
Defines the public contract protocol and the immutable payloads passed to and returned from it.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class TerminationContext:
    """Read-only snapshot of runtime counters at a termination boundary."""
    output: str
    iteration_count: int
    model_call_count: int
    tool_call_count: int
    tokens_used: int | None
    elapsed_seconds: float
    rejection_count: int
    run_state: Mapping[Any, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContractVerdict:
    """Outcome of evaluating one contract against a TerminationContext."""
    satisfied: bool
    feedback: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


class OutputContract(ABC):
    """Base class for a condition that must hold before an agent may stop."""

    name: str = ""

    @property
    def contract_name(self) -> str:
        # Returns a stable display name for metadata and feedback messages.
        return self.name or self.__class__.__name__

    @abstractmethod
    async def evaluate(self, ctx: TerminationContext) -> ContractVerdict:
        # Returns a verdict describing whether this contract permits stopping.
        ...
```

#### Logic / Algorithm
Pure data structures plus one abstract method. `evaluate` is async so later judge contracts drop in unchanged.

#### Edge Cases & Error Handling
- Contract implementations that raise from `evaluate` propagate to the gate; the gate treats an exception as fail-closed (unmet) for v1 deterministic floors, which never raise.

---

### 6.2 EffortFloor and the four deterministic floors

**File:** `vidbyte/agents/contracts/floors.py`
**Type:** New file

#### What it does
Provides a shared base for deterministic "minimum X" contracts and the four concrete floors.

#### Interface / API
```python
class EffortFloor(OutputContract):
    """A deterministic contract requiring a runtime counter to reach a minimum."""
    dimension: str
    minimum: float


class MinToolCalls(EffortFloor):
    dimension = "tool_calls"

    def __init__(self, minimum: int) -> None:
        # Stores the required minimum tool-call count, rejecting non-positive values.
        self._require_positive(minimum)
        self.minimum = minimum

    async def evaluate(self, ctx: TerminationContext) -> ContractVerdict:
        # Satisfied once the observed tool-call count reaches the configured minimum.
        return self._verdict(ctx.tool_call_count)
```

`MinTokens` (`dimension="tokens"`, reads `ctx.tokens_used or 0`), `MinIterations` (`dimension="iterations"`, reads `ctx.iteration_count`), and `MinElapsedSeconds` (`dimension="elapsed_seconds"`, reads `ctx.elapsed_seconds`) follow the identical shape. Shared helpers `_require_positive` and `_verdict` (which builds the satisfied/unsatisfied `ContractVerdict` with actionable feedback and `{observed, required}` metadata) live on `EffortFloor`.

#### Logic / Algorithm
1. Constructor validates `minimum > 0` (raises `ConfigurationError`).
2. `evaluate` reads the one relevant counter from `ctx`.
3. Returns satisfied verdict if `observed >= minimum`, else an unsatisfied verdict whose `feedback` tells the model the observed vs required value and to keep working.

#### Edge Cases & Error Handling
- `minimum <= 0` → `ConfigurationError` at construction.
- `tokens_used is None` (no usage reported yet) is treated as `0`.

---

### 6.3 ContractSettingsValidator (the constructor-level bridge)

**File:** `vidbyte/agents/contracts/validation.py`
**Type:** New file

#### What it does
The sole component that couples `AgentLoopSettings` and `OutputContract`. It reads both and raises a semantic error when an effort floor is unreachable because a same-dimension loop-settings ceiling would stop the run first. It performs no enforcement and holds no runtime state.

#### Interface / API
```python
class ContractConfigurationError(ConfigurationError):
    """Raised when an output contract conflicts with the agent's loop settings."""


class ContractSettingsValidator:
    """Bridges AgentLoopSettings and OutputContracts to reject conflicting configurations."""

    _CEILING_FIELD = {
        "tokens": "max_tokens",
        "tool_calls": "max_tool_calls",
        "iterations": "max_iterations",
        "elapsed_seconds": "timeout_seconds",
    }

    def __init__(self, settings: AgentLoopSettings, contracts: Sequence[OutputContract]) -> None:
        # Captures the settings and contracts to be reconciled; runs no checks yet.
        self._settings = settings
        self._contracts = tuple(contracts)

    def validate(self) -> None:
        # Raises ContractConfigurationError if any contract conflicts with the loop settings.
        self._validate_effort_floor_ceilings()

    def _validate_effort_floor_ceilings(self) -> None:
        # Ensures every effort floor is strictly below its paired loop-settings ceiling.
        for contract in self._effort_floors():
            self._check_floor_against_ceiling(contract)

    def _effort_floors(self) -> tuple[EffortFloor, ...]:
        # Returns only the statically checkable EffortFloor contracts, skipping opaque ones.
        return tuple(c for c in self._contracts if isinstance(c, EffortFloor))

    def _check_floor_against_ceiling(self, floor: EffortFloor) -> None:
        # Raises when the floor minimum meets or exceeds its paired ceiling value.
        ceiling = self._ceiling_value(floor.dimension)
        if ceiling is not None and floor.minimum >= ceiling:
            raise ContractConfigurationError(self._conflict_message(floor, ceiling))
```

#### Logic / Algorithm
1. Filter contracts to `EffortFloor` instances (opaque/future contracts are not statically checkable and are skipped).
2. For each floor, map `dimension` → settings field via `_CEILING_FIELD`.
3. If that settings field is set and `floor.minimum >= ceiling`, raise `ContractConfigurationError` with a message naming the floor, its minimum, the settings field, and the ceiling.

#### Edge Cases & Error Handling
- Ceiling unset (`None`) → skip; termination is still guaranteed by the rejection budget at runtime.
- `elapsed_seconds` maps to `timeout_seconds`, which is *not* threaded into the linear runtime loop today; the static check still applies, but there is no `_budget_stop` backstop for elapsed. Documented with a `# NOTE` at the gate and in Section 12.
- Multiple floors on the same dimension are each validated independently.
- Non-`EffortFloor` contracts are ignored (by design).

---

### 6.4 OutputContractGate (runtime enforcement)

**File:** `vidbyte/agents/contracts/gate.py`
**Type:** New file

#### What it does
Evaluates all contracts at a boundary, decides satisfied vs reject-and-continue vs exhausted, and builds the injected feedback message.

#### Interface / API
```python
class OutputContractGate:
    """Evaluates output contracts at termination boundaries and drives reject-and-continue."""

    def __init__(self, contracts: Sequence[OutputContract], *, max_rejections: int) -> None:
        # Stores the contracts and the rejection budget that bounds reject-and-continue.
        self._contracts = tuple(contracts)
        self._max_rejections = max_rejections

    def active(self) -> bool:
        # Returns whether any contract is configured for this run.
        return bool(self._contracts)

    async def evaluate(self, ctx: TerminationContext) -> tuple[ContractReport, ...]:
        # Evaluates every contract against the snapshot and returns per-contract reports.
        ...

    def unmet(self, reports: Sequence[ContractReport]) -> tuple[ContractReport, ...]:
        # Filters reports down to the contracts that were not satisfied.
        ...

    def exhausted(self, rejection_count: int) -> bool:
        # Returns whether the rejection budget has been spent.
        return rejection_count >= self._max_rejections

    def rejection_message(self, unmet: Sequence[ContractReport]) -> str:
        # Builds the aggregated feedback block injected when contracts are unmet.
        ...
```

`ContractReport` is a small frozen record `(name, satisfied, feedback, metadata)` used for both the injected message and the `contract_evaluations` metadata.

#### Logic / Algorithm
1. `evaluate` runs each contract's `evaluate` in order and collects reports; deterministic floors are cheap so all run (complete feedback in one round-trip).
2. `unmet` selects the failing reports.
3. `rejection_message` concatenates each unmet contract's feedback into one directive block.
4. `exhausted` compares the caller-tracked rejection count to `max_rejections`.

#### Edge Cases & Error Handling
- A contract raising inside `evaluate` is caught and recorded as unmet with the exception text as feedback (fail-closed).
- Empty contracts → `active()` is `False`; the runtime never calls the gate.

---

### 6.5 Runtime wiring

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Threads contracts into `AgentRuntime`, tracks a `rejection_count`, and consults the gate at the two finalization boundaries.

#### Interface / API
```python
def __init__(self, *, ..., output_contracts: Sequence[OutputContract] = (), max_contract_rejections: int = 3) -> None:
    # ... existing assignments ...
    self._gate = OutputContractGate(output_contracts, max_rejections=max_contract_rejections)
```

#### Logic / Algorithm
A private helper builds the snapshot:
```python
def _termination_context(self, output: str, *, iteration_count, model_call_count, call_contexts, tokens_used, started_at, run_state, rejection_count) -> TerminationContext:
    # Packages live runtime counters into the read-only snapshot contracts evaluate against.
    ...
```

**Boundary A — `IS_DONE` (`runtime.py:521`, after the existing `after_iteration` CONTINUE check, before `_final_result(..., IS_DONE)`):**
1. If `self._gate.active()`: evaluate, compute `unmet`.
2. If `unmet` and not `exhausted(rejection_count)`: increment `rejection_count`; append an error-status tool result answering `call` (the `isDone` call) carrying `rejection_message`; publish reports to `run_state["__contract_evaluations__"]`; `break` the `for` loop so the enclosing `while` runs another iteration.
3. If `unmet` and `exhausted`: return `_finish_result` with a `_final_result(stop_reason=CONTRACT_UNSATISFIED)` carrying `result.output` and the unmet list.
4. Else (all satisfied): fall through to the existing `IS_DONE` finalize.

**Boundary B — no tool calls (`runtime.py:400`, before the `FINAL_RESPONSE` finalize):**
1. Same evaluate / `unmet` / `exhausted` logic.
2. Reject-and-continue path appends `{"role": "user", "content": rejection_message}` to `messages` and `continue`s the `while`.
3. Exhausted path returns `CONTRACT_UNSATISFIED`.

`rejection_count` is a local in `_arun_once` initialized alongside `iteration_count`.

#### Edge Cases & Error Handling
- The `break` (Boundary A) versus `continue` (Boundary B) distinction matters: the `IS_DONE` handling is nested in `for call in tool_calls:`, so breaking the `for` lets the `while` proceed with the injected tool result already in `messages`; a stray `continue` there would skip remaining calls incorrectly.
- If a ceiling is hit on the next loop, `_budget_stop` returns the `MAX_*` result first — ceilings win.
- Provider-transcript validity is preserved because the injected error tool result answers the outstanding `isDone` tool-call id.

---

### 6.6 Agent constructor wiring

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Adds the `output_contracts=` parameter, runs the validator, enforces the non-linear guard, and threads contracts + `max_contract_rejections` into the runtime.

#### Logic / Algorithm
1. Add `output_contracts: Sequence[OutputContract] = ()` to `__init__`.
2. In the non-linear runtime guard (`base.py:107-117`), add: if `output_contracts` and runtime is non-linear → `ConfigurationError` (contracts are linear-only).
3. After `_resolve_loop_settings` populates `self.agent_loop_settings` (`base.py:171`), run:
   ```python
   self.output_contracts = tuple(output_contracts)
   ContractSettingsValidator(self.agent_loop_settings, self.output_contracts).validate()
   ```
4. In the runtime construction (`base.py:720-733`), pass `output_contracts=self.output_contracts` and `max_contract_rejections=self.agent_loop_settings.max_contract_rejections`.

#### Edge Cases & Error Handling
- Validator raises `ContractConfigurationError` (a `ConfigurationError`) before any runner is exercised.
- Empty `output_contracts` → validator is a no-op, runtime gate inactive.

---

### 6.7 AgentLoopSettings: max_contract_rejections

**File:** `vidbyte/agents/settings/loop.py`
**Type:** Modified

#### What it does
Adds the rejection budget as a first-class loop-governance setting.

#### Logic / Algorithm
- Add `max_contract_rejections: int = 3` to `__init__`, store it, and validate it as a positive int (append to `_POSITIVE_INT_FIELDS` or validate inline). It is *not* forwarded through `to_runtime_config` (which stays a pure budget contract); `base.py` reads it directly to pass to the runtime, mirroring how `output_schema` is threaded outside the config.

#### Edge Cases & Error Handling
- `<= 0` → `ConfigurationError`.
- Included in `__repr__`.

---

### 6.8 AgentStopReason.CONTRACT_UNSATISFIED

**File:** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does
Adds `CONTRACT_UNSATISFIED = "contract_unsatisfied"` to the enum so an exhausted-rejection stop is machine-readable.

---

## 7. Data Model Changes

N/A — no database, ORM, or persisted schema. The only structural additions are in-memory frozen dataclasses (`TerminationContext`, `ContractVerdict`, `ContractReport`) described in Section 6, and one new enum member.

---

## 8. API Changes

No network/HTTP API. The public Python API changes are additive:

### 8.1 `Agent(..., output_contracts=[...])`
**Change type:** New (additive keyword argument)

```python
from vidbyte.agents import Agent
from vidbyte.agents.contracts import MinToolCalls, MinTokens

agent = Agent(
    name="researcher",
    system_prompt="...",
    agent_loop_settings=AgentLoopSettings(max_tokens=1_000_000, max_contract_rejections=5),
    output_contracts=[MinToolCalls(5), MinTokens(50_000)],
)
```

**Error cases:**
| Error | Condition |
|-------|-----------|
| `ContractConfigurationError` | An effort floor's `minimum >= ` its paired loop-settings ceiling |
| `ConfigurationError` | `output_contracts` passed to a non-linear runtime |
| `ConfigurationError` | Any floor constructed with `minimum <= 0`, or `max_contract_rejections <= 0` |

### 8.2 `AgentResult.metadata`
**Change type:** Modified (additive keys)

Adds `contract_evaluations` (tuple of per-contract report dicts) and allows `stop_reason == "contract_unsatisfied"`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/contracts/__init__.py` | Public exports for the contracts sub-package |
| CREATE | `vidbyte/agents/contracts/base.py` | `OutputContract`, `ContractVerdict`, `TerminationContext` |
| CREATE | `vidbyte/agents/contracts/floors.py` | `EffortFloor` + `MinTokens`/`MinToolCalls`/`MinIterations`/`MinElapsedSeconds` |
| CREATE | `vidbyte/agents/contracts/validation.py` | `ContractSettingsValidator`, `ContractConfigurationError` |
| CREATE | `vidbyte/agents/contracts/gate.py` | `OutputContractGate`, `ContractReport` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentStopReason.CONTRACT_UNSATISFIED` |
| MODIFY | `vidbyte/agents/settings/loop.py` | Add `max_contract_rejections` field + validation |
| MODIFY | `vidbyte/agents/runtime.py` | Gate wiring at both finalization boundaries; constructor args; snapshot builder |
| MODIFY | `vidbyte/agents/base.py` | `output_contracts=` param, validator call, non-linear guard, thread to runtime |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export contract primitives |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | — | Feature is pure in-process Python on existing abstractions | None |

No new third-party packages, network calls, or services.

---

## 11. Rollout & Deployment

- **Feature flags:** none needed — the feature is inert unless `output_contracts` is supplied.
- **Breaking change:** no. All additions are keyword-only with no-op defaults; the empty-contracts path is behaviorally identical to today.
- **Deployment order:** single package, single PR.
- **Rollback:** revert the PR; no persisted state or migrations to unwind.

---

## 12. Open Questions

- [ ] Naming: is `ContractSettingsValidator` the preferred name for the bridge class, or do you want `LoopSettingsContractValidator` / `OutputContractReconciler`? (Doc currently uses `ContractSettingsValidator`.)
- [ ] Default `max_contract_rejections = 3` — acceptable, or prefer a different default?
- [ ] `MinElapsedSeconds` has a static ceiling (`timeout_seconds`) but no `_budget_stop` runtime backstop, since `timeout_seconds` is not threaded into the linear loop today. Ship as-is (rely on rejection budget) for v1, or add an elapsed check to `_budget_stop` in this PR? (Doc assumes ship as-is; noted as a follow-up.)
- [ ] Export surface: expose contract primitives from top-level `vidbyte/__init__.py` too, or only from `vidbyte.agents.contracts`? (Doc assumes `vidbyte.agents` + sub-package only.)

---

## 13. Alternatives Considered

### Alternative 1: Implement contracts as middleware
- **What:** Ship floors as an `AgentMiddleware` and add a new `MiddlewareAction` (e.g. `REQUEUE`) so `after_iteration` can veto a completion.
- **Why rejected:** Overloads middleware with the power to resurrect a finished loop (muddy semantics) and forces every contract author to learn the nine-hook lifecycle. The user explicitly wants a distinct mini-abstraction. We still reuse middleware *plumbing* (`run_state`, the `messages` list) without conflating the concepts.

### Alternative 2: Validate conflicts inside the gate at runtime
- **What:** Let the gate detect `min >= ceiling` on the first evaluation.
- **Why rejected:** The user's steer is explicit — conflict detection belongs at construction, as a dedicated bridge class, so misconfiguration fails fast before a runner is ever exercised. Runtime-only validation would surface the error mid-run.

### Alternative 3: Fold `max_contract_rejections` and `output_contracts` into `AgentRuntimeConfig`
- **What:** Extend the internal budget dataclass.
- **Why rejected:** `AgentRuntimeConfig` is a pure numeric-budget contract; contracts are behavioral objects. The established pattern for non-budget runtime inputs is a separate threaded argument (`output_schema`), so we follow it — keeping the config dataclass and `to_runtime_config` untouched.

### Alternative 4: Enforce strict `>` instead of `>=` in the validator
- **What:** Allow `min == ceiling`.
- **Why rejected:** Ceilings stop with `>=` at the top of the next loop, so `min == ceiling` is satisfiable only by a same-iteration race between the counter-incrementing call and `isDone`. For a deterministic floor that is effectively broken, so we require strict `<` (reject `>=`).

---

END OF DESIGN DOC
