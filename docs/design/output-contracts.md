# Design Doc: Output Contracts — Deterministic Effort Floors

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-06
**Last Updated:** 2026-07-06

---

## 1. Overview

Output contracts gate *when an agent is allowed to stop*. Today an agent stops the moment it calls the internal `isDone` tool, or emits a final response with no tool calls. This change lets a developer attach `OutputContract` objects to an `Agent`; the linear runtime evaluates them at those two termination boundaries. If any contract is unmet, the attempt to finish is vetoed, corrective feedback is injected into the context window, and the loop continues. This first slice ships the four **deterministic effort floors** — `MinToolCalls`, `MinTokens`, `MinIterations`, `MinElapsedSeconds` — behind one small owner class, `AgentOutputContract`, that validates configuration at agent-construction time and exposes one-line methods the runtime calls at each boundary.

The framing that bounds this feature:

> **`AgentLoopSettings` say when the agent MUST stop (ceilings). Output contracts say when the agent MAY stop (floors).**

This design deliberately favors the simplest shape that satisfies the intent: **two classes total** (`AgentOutputContract` + the `OutputContract` ABC), counters passed as a plain `dict`, and primitive return values (`list` / `bool` / `str`) instead of a family of result dataclasses.

---

## 2. Goals & Non-Goals

### Goals
- Introduce an `OutputContract` ABC that is almost pure declaration: `key`, `ceiling_key`, `unit`, `category`, plus a base-provided `satisfied()` / `error()`.
- Ship four deterministic effort floors that read counters the runtime already tracks.
- Add one owner class `AgentOutputContract` that (a) validates floor-vs-ceiling conflicts in its constructor and (b) exposes one-line methods the runtime calls at each boundary.
- Add an `output_contracts=` parameter to `Agent`, construct `AgentOutputContract` at agent-build time (fail-fast validation), and thread it into the linear runtime.
- Enforce contracts at the two finalization boundaries: inject corrective feedback and continue the loop when unmet.
- Guarantee termination via a `max_contract_rejections` budget and a new `AgentStopReason.CONTRACT_UNSATISFIED`.
- Surface `contract_evaluations` in `AgentResult.metadata`.

### Non-Goals
- **Judge / LLM-based contracts**, **predicate / schema / coverage contracts** — deferred. The declarative base is designed so they slot in later.
- **`MinCompactions`** — deferred; it is the one floor needing new runtime telemetry.
- **Non-linear runtimes** (actor / MCTS) — contracts are linear-only in v1, mirroring the existing middleware restriction.
- **Fail-closed exception handling inside `satisfied()`** — deferred; deterministic floors are a dict lookup + compare and cannot raise. Added when judge/predicate contracts land (see §12).
- Changing `isDone`, provider adapters, `to_runtime_config`, or the context-window algorithms.

---

## 3. Background & Context

The agent loop lives in `vidbyte/agents/runtime.py` (`AgentRuntime._arun_once`). It already owns the dual of this feature: `AgentLoopSettings` (`vidbyte/agents/settings/loop.py`) define **ceilings** — `max_iterations`, `max_tokens`, `max_tool_calls` — enforced by `_budget_stop` (`runtime.py:1479`). Output contracts are the **floors**: the conditions under which stopping is *permitted*.

Two facts from the audit make deterministic floors the correct first slice:

1. **Zero new telemetry.** Every counter the four floors need is already live in `_arun_once`: `iteration_count`, `model_call_count`, `tokens_used`, `len(call_contexts)`, and elapsed time via `self.middleware.clock() - started_at` (`runtime.py:174–177`).
2. **A natural, provider-correct injection point.** At the `IS_DONE` boundary, `_process_tool_call` deliberately does *not* append a tool-result message for `isDone` (`runtime.py:1399`), yet the assistant message carrying the `isDone` call is already in `messages`. Providers require every tool-call to be answered, so the rejection feedback *becomes* the `isDone` tool result — one move that both injects the correction and keeps the transcript valid. This reuses the existing `_append_tool_result_message` helper (`runtime.py:1403`) with a `ToolResult.error(...)`.

This design supersedes the earlier PR #207 shape, which introduced five frozen dataclasses (`TerminationContext`, `ContractVerdict`, `ContractReport`, `ContractDecision`) plus a separate gate and validator. That type surface was judged to carry unneeded mental complexity. The revision collapses it to two classes, a counters `dict`, and primitive returns, while keeping the same runtime behavior and the same three-layer termination guarantee.

---

## 4. Requirements

### Functional Requirements
1. An `Agent` accepts `output_contracts: Sequence[OutputContract] = ()`.
2. When `output_contracts` is empty, agent behavior is byte-for-byte unchanged: `AgentOutputContract.active()` is `False` and the runtime never evaluates it.
3. At the `IS_DONE` boundary, before finalizing, all contracts are evaluated against a counters snapshot.
4. At the no-tool-calls final-response boundary, the same evaluation runs.
5. If all contracts are satisfied, the run finalizes exactly as today (`stop_reason` stays `IS_DONE` / `FINAL_RESPONSE`).
6. If any contract is unmet and the rejection budget is not exhausted, the runtime injects the aggregated feedback and continues the loop instead of returning.
7. Injection at the `IS_DONE` boundary is an error-status tool result answering the `isDone` call; at the no-tool-calls boundary it is a synthetic `user` message.
8. If the rejection budget (`max_contract_rejections`) is exhausted, the run stops with `AgentStopReason.CONTRACT_UNSATISFIED`, returning the best candidate output.
9. Existing ceilings (`_budget_stop`) remain the hard backstop: a ceiling reached while chasing a floor stops the run with the corresponding `MAX_*` reason.
10. `AgentOutputContract` validates every effort floor against its paired loop-settings ceiling **at construction time** (`Agent.__init__`), raising a `ConfigurationError` when a floor's `minimum >= ` its ceiling (strict `<` required).
11. Contracts passed to a non-linear runtime raise `ConfigurationError` at construction, mirroring the middleware restriction.
12. `AgentResult.metadata["contract_evaluations"]` lists each contract's name, satisfied flag, and minimum.

### Non-Functional Requirements
- **Performance:** floors are O(1) `dict` lookups + compares; evaluation runs only at termination boundaries. Empty `output_contracts` adds no per-iteration cost.
- **Reliability:** termination is guaranteed by three independent layers — construction-time validator, runtime ceilings (`_budget_stop`), and the rejection budget.
- **Security:** no new external calls, credentials, or tool-permission changes.
- **Observability:** the final disposition is recorded in `run_state["__result_metadata__"]` and lifted into `AgentResult.metadata` by the existing `_with_run_state_metadata`.
- **Backward compatibility:** purely additive; all new parameters default to no-ops.

---

## 5. High-Level Design

Two locations, honoring the "class in its own file, prebuilt contracts in a folder" intent:

- **`vidbyte/agents/contract.py`** — the owner class `AgentOutputContract` (singular file, peer to `runtime.py`'s `AgentRuntime`).
- **`vidbyte/agents/contracts/`** — the prebuilt library: `__init__.py` holds the `OutputContract` ABC and re-exports; `floors.py` holds the four deterministic floors.

Construction-time data flow:

```
Agent(output_contracts=[...], agent_loop_settings=...)
        │
        ├─ _resolve_loop_settings()  ── AgentLoopSettings   (always returns an object)
        │
        └─ AgentOutputContract(contracts, loop_settings, max_rejections)
                 └─ __init__ validates: floor.minimum >= settings[ceiling_key]  → ConfigurationError [FAIL FAST]
```

Runtime data flow (linear runtime only, and only when `active()`):

```
_arun_once loop
    │
    ├─ model calls isDone ──────────► counters = {...}
    │                                  unmet = contract.unmet(counters)
    │        no unmet ──► finalize IS_DONE (unchanged)
    │        unmet & budget left ──► append ToolResult.error answering isDone; break the for-loop → while re-iterates
    │        unmet & budget spent ──► finalize CONTRACT_UNSATISFIED
    │
    └─ model returns final text (no tool calls) ► same unmet check
             unmet & budget left ──► append {"role":"user", "content": feedback}; continue the while
             unmet & budget spent ──► finalize CONTRACT_UNSATISFIED
```

Key decisions:
- **The runtime delegates the *decision*, not the *action*.** `AgentOutputContract` answers "which contracts are unmet?", "is the budget spent?", and "what feedback text?". The runtime keeps the control flow (`break` vs `continue` vs `return`) and builds the two different injection envelopes, because those depend on loop-local state (`call`, `messages`) and provider-transcript rules.
- **`AgentOutputContract` is config-only and immutable.** It is built once in `Agent.__init__` for fail-fast validation and holds no per-run state. `rejections` is a local in `_arun_once`, passed into `exhausted(rejections)`. This avoids state leaking across sequential or concurrent runs of the same agent.
- **Counters travel as a plain `dict`** whose keys equal each contract's `key`. `key` reads the snapshot; `ceiling_key` reads `AgentLoopSettings`. Those two strings are the entire coupling surface.
- **Strict `<` invariant.** Ceilings stop with `>=` at the top of the next loop, so a floor equal to its ceiling is only satisfiable by a same-iteration race — for a deterministic floor that is indistinguishable from broken, so `min >= ceiling` is rejected.

---

## 6. Detailed Design

### 6.1 OutputContract ABC + concrete floors

**File:** `vidbyte/agents/contracts/__init__.py` (ABC), `vidbyte/agents/contracts/floors.py` (floors)
**Type:** New files

#### What it does
Defines the declarative contract base and the four deterministic floors. The base owns the read, the compare, and the error text; a concrete floor is three lines of data.

#### Interface / API
```python
# contracts/__init__.py
class OutputContract(ABC):
    """Base class for a condition that must hold before an agent may stop."""

    key: str                        # counters[key] — the runtime counter this floor reads
    ceiling_key: str | None = None  # paired AgentLoopSettings field, or None
    unit: str = ""                  # human unit for the error message ("tool calls", "tokens")
    category: str = "deterministic"

    def __init__(self, minimum: int | float) -> None:
        # Stores the required minimum, rejecting non-positive values at construction.
        if minimum <= 0:
            raise ConfigurationError(f"{self.name}: minimum must be greater than zero, got {minimum}.")
        self.minimum = minimum

    @property
    def name(self) -> str:
        # Stable display name used in feedback and result metadata.
        return type(self).__name__

    def satisfied(self, counters: Mapping[str, Any]) -> bool:
        # Returns whether the observed counter has reached this floor's minimum.
        return (counters.get(self.key) or 0) >= self.minimum

    def error(self, counters: Mapping[str, Any]) -> str:
        # Builds the corrective feedback shown to the model when this floor is unmet.
        observed = counters.get(self.key) or 0
        return f"Only {observed} {self.unit} so far; at least {self.minimum} are required before finishing. Keep working."
```

```python
# contracts/floors.py
class MinToolCalls(OutputContract):
    key = "tool_call_count"; ceiling_key = "max_tool_calls"; unit = "tool calls"

class MinTokens(OutputContract):
    key = "tokens_used"; ceiling_key = "max_tokens"; unit = "tokens"

class MinIterations(OutputContract):
    key = "iteration_count"; ceiling_key = "max_iterations"; unit = "iterations"

class MinElapsedSeconds(OutputContract):
    key = "elapsed_seconds"; ceiling_key = "timeout_seconds"; unit = "seconds"
```

#### Logic / Algorithm
1. Constructor validates `minimum > 0`.
2. `satisfied` reads one key from the counters dict (`None` → `0`) and compares to `minimum`.
3. `error` formats the observed-vs-required feedback.

#### Edge Cases & Error Handling
- `minimum <= 0` → `ConfigurationError` at construction.
- `tokens_used` may be `None` early in a run; `counters.get(key) or 0` treats it as `0`.
- `MinElapsedSeconds` declares `ceiling_key="timeout_seconds"` for the static conflict check, but `timeout_seconds` is not threaded into the linear loop's `_budget_stop` today, so only the rejection budget bounds it at runtime (documented in §12).

---

### 6.2 AgentOutputContract (owner class)

**File:** `vidbyte/agents/contract.py`
**Type:** New file

#### What it does
The single component that couples `AgentLoopSettings` and the contracts. It validates floor-vs-ceiling conflicts in its constructor and exposes the one-line methods the runtime calls at each boundary. Immutable; holds no per-run state.

#### Interface / API
```python
class AgentOutputContract:
    """Owns an agent's output contracts: validates config at construction, evaluates at termination boundaries."""

    _CEILING_LABEL = "AgentLoopSettings"

    def __init__(self, contracts: Sequence[OutputContract], loop_settings: AgentLoopSettings, *, max_rejections: int = 3) -> None:
        # Captures contracts + settings and validates every floor-vs-ceiling conflict immediately.
        self._contracts = tuple(contracts)
        self._loop_settings = loop_settings
        self._max_rejections = max_rejections
        self._validate()

    def _validate(self) -> None:
        # Raises ConfigurationError when any floor's minimum meets or exceeds its paired ceiling.
        for contract in self._contracts:
            self._validate_ceiling(contract)

    def _validate_ceiling(self, contract: OutputContract) -> None:
        # Enforces the strict floor < ceiling invariant for one contract that declares a ceiling_key.
        if not contract.ceiling_key:
            return
        ceiling = getattr(self._loop_settings, contract.ceiling_key, None)
        if ceiling is not None and contract.minimum >= ceiling:
            raise ConfigurationError(
                f"{contract.name}(minimum={contract.minimum}) conflicts with "
                f"{self._CEILING_LABEL}.{contract.ceiling_key}={ceiling}: the floor is unreachable (require minimum < ceiling)."
            )

    def active(self) -> bool:
        # Returns whether any contract is configured for this agent.
        return bool(self._contracts)

    def unmet(self, counters: Mapping[str, Any]) -> list[OutputContract]:
        # Returns the contracts not yet satisfied by the current counters snapshot.
        return [c for c in self._contracts if not c.satisfied(counters)]

    def exhausted(self, rejections: int) -> bool:
        # Returns whether the reject-and-continue budget has been spent.
        return rejections >= self._max_rejections

    def feedback(self, unmet: Sequence[OutputContract], counters: Mapping[str, Any]) -> str:
        # Builds the aggregated corrective message injected when contracts are unmet.
        lines = "\n".join(f"- {c.error(counters)}" for c in unmet)
        return f"You cannot finish yet:\n{lines}"

    def report(self, counters: Mapping[str, Any]) -> list[dict[str, Any]]:
        # Builds the per-contract records surfaced in AgentResult.metadata["contract_evaluations"].
        return [{"name": c.name, "satisfied": c.satisfied(counters), "minimum": c.minimum} for c in self._contracts]
```

#### Logic / Algorithm
1. `__init__` stores config and calls `_validate()` — fail fast.
2. `_validate` maps each contract's `ceiling_key` onto the settings object and rejects `minimum >= ceiling`.
3. Runtime methods are pure: `unmet`, `exhausted`, `feedback`, `report` each read inputs and return primitives.

#### Edge Cases & Error Handling
- Ceiling unset (`None`) → skipped; termination is still guaranteed by the rejection budget.
- Contract with `ceiling_key = None` → no static check (by design; future opaque contracts skip transparently).
- Empty contracts → `active()` is `False`; the runtime never calls any other method.

---

### 6.3 Runtime wiring

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Accepts the `AgentOutputContract`, tracks a `rejections` local, builds a counters snapshot, and consults the owner at the two finalization boundaries.

#### Interface / API
```python
def __init__(self, *, ..., output_contract: "AgentOutputContract | None" = None) -> None:
    # ... existing assignments ...
    from vidbyte.agents.contract import AgentOutputContract
    self.output_contract = output_contract or AgentOutputContract((), AgentLoopSettings())
```

A small helper builds the snapshot:
```python
def _contract_counters(self, *, iteration_count, model_call_count, call_contexts, tokens_used, started_at) -> dict[str, Any]:
    # Packages the live runtime counters into the dict contracts read by key.
    return {
        "iteration_count": iteration_count,
        "model_call_count": model_call_count,
        "tool_call_count": len(call_contexts),
        "tokens_used": tokens_used or 0,
        "elapsed_seconds": self.middleware.clock() - started_at,
    }
```

#### Logic / Algorithm
`rejections = 0` is initialized alongside `iteration_count` (`runtime.py:174`).

**Boundary A — `IS_DONE`** (`runtime.py:543`, after the existing `after_iteration` CONTINUE check, before building the `IS_DONE` `final`):
```python
if self.output_contract.active():
    counters = self._contract_counters(...)
    unmet = self.output_contract.unmet(counters)
    if unmet:
        run_state.setdefault("__result_metadata__", {})["contract_evaluations"] = self.output_contract.report(counters)
        if self.output_contract.exhausted(rejections):
            return await self._finish_result(self._stopped_result(result.output, stop_reason=AgentStopReason.CONTRACT_UNSATISFIED, ...), ...)
        rejections += 1
        self._append_tool_result_message(messages, call, ToolResult.error(call.tool_name, self.output_contract.feedback(unmet, counters)), provider, MiddlewareDecision.continue_())
        break   # exit the for-loop; the enclosing while runs another iteration
# else: fall through to the existing IS_DONE finalize
```

**Boundary B — no tool calls** (`runtime.py:422`, before building the `FINAL_RESPONSE` `final`):
```python
if self.output_contract.active():
    counters = self._contract_counters(...)
    unmet = self.output_contract.unmet(counters)
    if unmet:
        run_state.setdefault("__result_metadata__", {})["contract_evaluations"] = self.output_contract.report(counters)
        if self.output_contract.exhausted(rejections):
            return await self._finish_result(self._stopped_result(last_assistant_output, stop_reason=AgentStopReason.CONTRACT_UNSATISFIED, ...), ...)
        rejections += 1
        messages.append({"role": "user", "content": self.output_contract.feedback(unmet, counters)})
        continue   # re-enter the while
# else: fall through to FINAL_RESPONSE finalize
```

On the satisfied path, `run_state["__result_metadata__"]["contract_evaluations"]` is also written (once) so successful runs surface the evaluations too. `_with_run_state_metadata` (`runtime.py:736`) already lifts `__result_metadata__` into `AgentResult.metadata` — no change to `_finish_result` needed.

#### Edge Cases & Error Handling
- `break` (Boundary A) vs `continue` (Boundary B): Boundary A is nested in `for call in tool_calls:`; breaking lets the `while` proceed with the injected tool result already in `messages`. A stray `continue` there would skip remaining tool calls.
- Injected `isDone` error result answers the outstanding tool-call id, preserving provider-transcript validity.
- If a ceiling is hit on the next loop, `_budget_stop` returns the `MAX_*` result first — ceilings win.
- The default `AgentOutputContract((), AgentLoopSettings())` guarantees `active()` is `False` when no contract was threaded, so non-contract runs are untouched.

---

### 6.4 Agent constructor wiring

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Adds the `output_contracts=` parameter, enforces the non-linear guard, constructs and validates the `AgentOutputContract`, and threads it into the linear runtime.

#### Logic / Algorithm
1. Add `output_contracts: Sequence[OutputContract] = ()` to `__init__`.
2. In the non-linear runtime guard block (`base.py:112–135`), add: if `output_contracts` and the runtime is non-linear → `ConfigurationError` (contracts are linear-only).
3. After `_resolve_loop_settings` populates `self.agent_loop_settings` (`base.py:170`), construct:
   ```python
   from vidbyte.agents.contract import AgentOutputContract
   self.output_contract = AgentOutputContract(output_contracts, self.agent_loop_settings, max_rejections=self.agent_loop_settings.max_contract_rejections)
   ```
   (constructor validates → fail fast, before any runner runs.)
4. In `_runtime()` (`base.py:941–981`), pass `output_contract=self.output_contract` **only** for the linear runtime (add to the conditional `kwargs`), since non-linear runtime classes do not accept it and the guard already forbids contracts there.

#### Edge Cases & Error Handling
- `AgentOutputContract.__init__` raises `ConfigurationError` before the agent is usable.
- Empty `output_contracts` → owner built but inert (`active()` is `False`).

---

### 6.5 AgentLoopSettings: max_contract_rejections

**File:** `vidbyte/agents/settings/loop.py`
**Type:** Modified

#### What it does
Adds the rejection budget as a first-class loop-governance setting.

#### Logic / Algorithm
- Add `max_contract_rejections: int = 3` to `__init__`, store it, and add its name to `_POSITIVE_INT_FIELDS` so the existing `_validate_positive_int_fields` rejects `<= 0`.
- Add it to the `__repr__` field list.
- It is **not** forwarded through `to_runtime_config` (which stays a pure numeric-budget contract); `base.py` reads it directly to pass into `AgentOutputContract`, mirroring how `output_schema` is threaded outside the config.

#### Edge Cases & Error Handling
- `<= 0` → `ConfigurationError` (via `_validate_positive_int_fields`).

---

### 6.6 AgentStopReason.CONTRACT_UNSATISFIED

**File:** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does
Adds `CONTRACT_UNSATISFIED = "contract_unsatisfied"` to the `AgentStopReason` enum (`agents.py:39`) so an exhausted-rejection stop is machine-readable.

---

### 6.7 Package exports

**File:** `vidbyte/agents/__init__.py`, `vidbyte/agents/contracts/__init__.py`
**Type:** Modified / New

Re-export `OutputContract`, `MinToolCalls`, `MinTokens`, `MinIterations`, `MinElapsedSeconds`, and `AgentOutputContract` from `vidbyte.agents` (and the contract primitives from `vidbyte.agents.contracts`), and add them to `__all__`.

---

## 7. Data Model Changes

N/A — no database, ORM, or persisted schema. The only structural additions are two new classes, four tiny subclasses, and one new enum member. Counters travel as an in-memory `dict`.

---

## 8. API Changes

No network/HTTP API. The public Python API changes are additive.

### 8.1 `Agent(..., output_contracts=[...])`
**Change type:** New (additive keyword argument)

```python
from vidbyte.agents import Agent, AgentLoopSettings
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
| `ConfigurationError` | An effort floor's `minimum >= ` its paired loop-settings ceiling |
| `ConfigurationError` | `output_contracts` passed to a non-linear runtime |
| `ConfigurationError` | Any floor constructed with `minimum <= 0`, or `max_contract_rejections <= 0` |

### 8.2 `AgentResult.metadata`
**Change type:** Modified (additive keys)

Adds `contract_evaluations` (list of `{name, satisfied, minimum}` dicts) and allows `stop_reason == "contract_unsatisfied"`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/contract.py` | `AgentOutputContract` owner class |
| CREATE | `vidbyte/agents/contracts/__init__.py` | `OutputContract` ABC + public exports |
| CREATE | `vidbyte/agents/contracts/floors.py` | `MinToolCalls` / `MinTokens` / `MinIterations` / `MinElapsedSeconds` |
| MODIFY | `vidbyte/agents/runtime.py` | Contract wiring at both finalization boundaries; `output_contract` ctor arg; counters snapshot helper |
| MODIFY | `vidbyte/agents/base.py` | `output_contracts=` param, owner construction + validation, non-linear guard, thread to linear runtime |
| MODIFY | `vidbyte/agents/settings/loop.py` | Add `max_contract_rejections` field + validation |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentStopReason.CONTRACT_UNSATISFIED` |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export contract primitives + `AgentOutputContract` |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| None | — | Pure in-process Python on existing abstractions | None |

No new third-party packages, network calls, or services.

---

## 11. Rollout & Deployment

- **Feature flags:** none — inert unless `output_contracts` is supplied.
- **Breaking change:** no. All additions are keyword-only with no-op defaults; the empty-contracts path is behaviorally identical to today.
- **Deployment order:** single package, single PR.
- **Rollback:** revert the PR; no persisted state or migrations.
- **PR #207:** closed in favor of this design before this PR opens.

---

## 12. Open Questions

- [ ] **Module layout:** `contract.py` (owner, singular) + `contracts/` (library, plural) honors the "own file like `AgentRuntime`" intent but the singular/plural adjacency can read as a typo. Alternative: a single `contracts/` package with `manager.py` + `base.py` + `floors.py`. Doc currently uses the singular/plural split as approved. Confirm.
- [ ] **`MinElapsedSeconds` backstop:** it has a static ceiling (`timeout_seconds`) but no `_budget_stop` runtime backstop, since `timeout_seconds` is not threaded into the linear loop today. Ship as-is (rejection budget bounds it) for v1, or thread `timeout_seconds` into `_budget_stop` in this PR? Doc assumes ship as-is.
- [ ] **Default `max_contract_rejections = 3`** — acceptable default?
- [ ] **Fail-closed `satisfied()`** — deterministic floors cannot raise, so no try/except is added now. Confirm deferring it to the judge/predicate PR is acceptable.

---

## 13. Alternatives Considered

### Alternative 1: The PR #207 shape (five dataclasses + separate gate + validator)
- **What:** `TerminationContext`, `ContractVerdict`, `ContractReport`, `ContractDecision`, an `OutputContractGate`, and a `ContractSettingsValidator`.
- **Why rejected:** Judged to carry unneeded mental complexity for a feature whose core is "compare a counter to a minimum." This design collapses the five dataclasses to a counters `dict` + primitive returns and merges the gate and validator into one owner class, with identical runtime behavior.

### Alternative 2: Implement contracts as middleware
- **What:** Ship floors as an `AgentMiddleware` with a new veto action.
- **Why rejected:** Middleware's non-`CONTINUE` action is `ABORT_RUN`, which *stops*; it cannot express "veto this completion and keep looping." A termination check is semantically distinct. We still reuse middleware *plumbing* (`run_state`, the `messages` list).

### Alternative 3: Push message injection into `AgentOutputContract`
- **What:** Let the owner mutate `messages` itself so the runtime is a single call.
- **Why rejected:** The two boundaries need different envelopes (an `isDone` error tool result vs a `user` message) and different control flow (`break` vs `continue`), both dependent on loop-local state (`call`, `messages`). Pushing that into the owner would require handing it runtime internals — recreating the coupling in a less visible place. The owner returns the decision; the runtime performs the act.

### Alternative 4: Store `rejections` on `AgentOutputContract`
- **What:** Make the owner stateful and increment its own counter.
- **Why rejected:** The owner is built once in `Agent.__init__`; per-run state on it would leak across sequential runs and corrupt concurrent async runs of the same agent. `rejections` stays a local in `_arun_once`.

### Alternative 5: Enforce strict `>` instead of `>=` in the validator
- **What:** Allow `min == ceiling`.
- **Why rejected:** Ceilings stop with `>=` at the top of the next loop, so `min == ceiling` is satisfiable only by a same-iteration race. For a deterministic floor that is effectively broken, so we require strict `<`.

---

END OF DESIGN DOC
