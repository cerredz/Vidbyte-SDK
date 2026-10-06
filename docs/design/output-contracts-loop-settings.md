# Design Doc: Output Contracts (owned by AgentLoopSettings)

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-08
**Last Updated:** 2026-07-08

---

## 1. Overview

Output contracts are deterministic **effort floors** that gate when a linear agent is *allowed* to stop. `AgentLoopSettings` ceilings say when an agent MUST stop; output contracts say when it MAY stop. When the model calls the internal `isDone` tool (or otherwise tries to finalize) before a contract is met, the runtime does not finish — it injects a semantic corrective message into the model's context and continues the agentic loop. This is the enforcement layer.

This design deliberately **homes contracts inside `AgentLoopSettings`** rather than on the `Agent` constructor. A new `output_contracts=` parameter on `AgentLoopSettings` is wrapped at settings-construction time into an `AgentLoopSettingsOutputContract` owner exposed as `AgentLoopSettings.output_contract`. The linear runtime consults that owner at its two finalization boundaries. There is intentionally **no** top-level `Agent(output_contracts=)` parameter — contracts are only configurable through settings, so a floor is always declared next to the ceilings it is validated against.

---

## 2. Goals & Non-Goals

### Goals
- Introduce a declarative `OutputContract` base plus four prebuilt deterministic floors: `MinToolCalls`, `MinTokens`, `MinIterations`, `MinElapsedSeconds`.
- Own contracts on `AgentLoopSettings` via a new `output_contracts=` parameter and a constructed `AgentLoopSettingsOutputContract` at `AgentLoopSettings.output_contract`.
- Validate floor-vs-ceiling conflicts at **settings construction** (fail fast), reading the settings' own ceiling fields directly.
- Enforce contracts in the linear `AgentRuntime` at both finalization boundaries (isDone tool-result envelope; no-tool-calls user-message envelope) by injecting corrective feedback and continuing the loop.
- Bound retries with `max_contract_rejections` (new `AgentLoopSettings` field, default 3); on exhaustion, stop with a new `CONTRACT_UNSATISFIED` stop reason.
- Count only **real** tool calls toward `MinToolCalls` (exclude internal tools such as `isDone`).
- Surface per-contract evaluations in `AgentResult.metadata["contract_evaluations"]`.

### Non-Goals
- **No** top-level `Agent(output_contracts=)` parameter (explicitly rejected — single home is `AgentLoopSettings`).
- No non-deterministic / semantic (LLM-judged) contracts. The base carries a `category` field to leave room, but only deterministic floors ship here.
- No support for output contracts on non-linear runtimes (actor-model family). Attempting it raises `ConfigurationError`.
- No changes to the internal `AgentRuntimeConfig` dataclass — the contract owner is threaded as its own runtime kwarg.
- No tests or verification scripts are added in this PR (per `/design-doc-no-tests`). Behavior is exercised manually.

---

## 3. Background & Context

Agentic loops today only have **ceilings** (`max_iterations`, `max_tokens`, `max_tool_calls`, `timeout_seconds`) that force termination. There is no mechanism to enforce a *minimum* effort before the model is permitted to declare itself done. A model can call `isDone` after a single tool call and finish, even when the task clearly warranted more work.

A prior PR (#243, currently open, unmerged) implemented this as a top-level `Agent(output_contracts=[...])` parameter with a separate `AgentOutputContract` owner that reached *across* an object boundary (`getattr(loop_settings, ceiling_key)`) to validate floors against ceilings living on a different object. Design review concluded the floors belong in the same object as the ceilings they pair with. This design re-homes the feature into `AgentLoopSettings` so that:

- Floor-vs-ceiling validation reads the settings' own fields — no cross-object reach.
- `max_contract_rejections` sits next to its sibling loop parameters.
- A user cannot declare a floor without the ceilings in view.

`origin/main` contains none of the #243 code, so this design is a clean, self-contained introduction of the full mechanism in its re-homed shape.

---

## 4. Requirements

### Functional Requirements
1. `OutputContract` is a declarative base: subclasses set `key` (runtime counter name), `ceiling_key` (paired `AgentLoopSettings` field or `None`), `unit` (human string), and `category` (default `"deterministic"`). The base supplies `satisfied(counters)` and `error(counters)`.
2. `OutputContract.__init__(minimum)` rejects `minimum <= 0` with `ConfigurationError`.
3. Four floors ship: `MinToolCalls` (`tool_call_count`/`max_tool_calls`), `MinTokens` (`tokens_used`/`max_tokens`), `MinIterations` (`iteration_count`/`max_iterations`), `MinElapsedSeconds` (`elapsed_seconds`/`timeout_seconds`).
4. `AgentLoopSettings` accepts `output_contracts: Sequence[OutputContract] = ()` and `max_contract_rejections: int = 3`.
5. `AgentLoopSettings.__init__` constructs and stores `self.output_contract: AgentLoopSettingsOutputContract` (always present; inactive when no contracts).
6. `AgentLoopSettings._validate()` raises `ConfigurationError` if any floor's `minimum >= ceiling` where the ceiling is set on the settings (unreachable-floor guard).
7. `max_contract_rejections` must be a positive int (validated).
8. The linear `AgentRuntime` accepts an `output_contract` and, when `active()`, evaluates it at both finalization boundaries:
   - **isDone boundary:** if unmet and budget remains, inject the corrective feedback as the `isDone` **error tool-result** and continue the loop.
   - **no-tool-calls boundary:** if unmet and budget remains, inject the corrective feedback as a **user message** and continue the loop.
9. On each unmet finalization attempt, a per-run `rejections` counter increments; when `rejections >= max_contract_rejections`, the run stops with `AgentStopReason.CONTRACT_UNSATISFIED`.
10. `tool_call_count` excludes internal tools (`isDone` and any tool flagged internal in its spec metadata), so `MinToolCalls` cannot be satisfied by the finishing call.
11. Each evaluation publishes per-contract records (`name`, `satisfied`, `minimum`) into `AgentResult.metadata["contract_evaluations"]`.
12. Passing active output contracts to a non-linear runtime raises `ConfigurationError` at `Agent.__init__`.
13. There is **no** `Agent(output_contracts=)` parameter.

### Non-Functional Requirements
- **Performance:** contract evaluation is O(contracts) per finalization attempt; negligible. Counter snapshot is O(tool calls) for the internal-tool filter.
- **Correctness/termination:** three independent stop guarantees must hold — (a) construction-time unreachable-floor validation, (b) existing `_budget_stop` ceilings, (c) bounded `max_contract_rejections`. No infinite loop is possible.
- **State isolation:** the contract owner is immutable and stateless across runs; `rejections` lives as a local in `_arun_once` (no leak between runs).
- **Observability:** evaluations surfaced via existing `run_state["__result_metadata__"]` lift path — no new metadata plumbing.
- **Style:** class-first, one-line signatures, mandatory 1–2 line comment under each signature, sparse inline comments — matching the existing SDK house style and the Context Protocol Header convention on new modules.

---

## 5. High-Level Design

Three new modules define the contract vocabulary; three existing modules are modified to own, validate, and enforce them.

**Ownership / data flow:**

```
AgentLoopSettings(output_contracts=[MinToolCalls(5), ...], max_tool_calls=20)
        │  __init__ stores ceilings, then builds + validates:
        ▼
AgentLoopSettings.output_contract : AgentLoopSettingsOutputContract   (validated here, fail-fast)
        │  base._runtime()  (LINEAR only) passes it as output_contract=
        ▼
AgentRuntime.output_contract
        │  _arun_once consulted at 2 boundaries:
        ▼
  ┌─ isDone boundary ─────────► unmet & budget → isDone error tool-result + continue
  │                             unmet & exhausted → stop(CONTRACT_UNSATISFIED)
  └─ no-tool-calls boundary ──► unmet & budget → user message + continue
                                unmet & exhausted → stop(CONTRACT_UNSATISFIED)
        │  counters built by _contract_counters (isDone excluded from tool_call_count)
        ▼
AgentResult.metadata["contract_evaluations"]   (via run_state __result_metadata__ lift)
```

**Key decisions:**
- **Decision vs action split (unchanged from #243):** the contract owner answers `active/unmet/exhausted/feedback/report`; the runtime owns `break`/`continue` and the two injection envelopes. The runtime never inspects individual contracts.
- **Single home:** contracts are only reachable via `AgentLoopSettings`. `base._runtime()` sources the owner from `self.agent_loop_settings.output_contract`.
- **Validation lives in `AgentLoopSettings._validate()`** (not in the owner), reading the settings' own ceiling fields via `getattr(self, ceiling_key)`. The owner is purely runtime-facing.
- **Non-linear guard in `base.py`**, mirroring the existing `tool_error_policy` guard, because settings cannot know the runtime type.
- **`AgentRuntimeConfig` untouched:** the owner is threaded as a separate kwarg, keeping the internal config contract minimal.

---

## 6. Detailed Design

### 6.1 `OutputContract` base + package exports

**File(s):** `vidbyte/agents/contracts/__init__.py`
**Type:** New file

#### What it does
Declares the `OutputContract` base (declarative `key`/`ceiling_key`/`unit`/`category`, plus `satisfied()`/`error()`/`name`) and re-exports the four floors.

#### Interface / API
```python
class OutputContract:
    key: str = ""
    ceiling_key: str | None = None
    unit: str = ""
    category: str = "deterministic"

    def __init__(self, minimum: int | float) -> None: ...
    @property
    def name(self) -> str: ...                              # type(self).__name__
    def satisfied(self, counters: Mapping[str, Any]) -> bool: ...
    def error(self, counters: Mapping[str, Any]) -> str: ...
```

#### Logic / Algorithm
1. `__init__` rejects `minimum <= 0` (`ConfigurationError`), stores `self.minimum`.
2. `satisfied` returns `(counters.get(self.key) or 0) >= self.minimum`.
3. `error` builds `"Only {observed} {unit} so far; at least {minimum} are required before finishing. Keep working."`
4. Import the four floors at the bottom (after the base is defined) and set `__all__`.

#### Edge Cases & Error Handling
- Missing counter key → treated as `0` via `.get(...) or 0` (defensive; unknown counter reads as unmet).
- `minimum` of `0`/negative → rejected at construction.

---

### 6.2 Prebuilt floors

**File(s):** `vidbyte/agents/contracts/floors.py`
**Type:** New file

#### What it does
Four `OutputContract` subclasses, each pure declaration (three data attributes, no logic).

#### Interface / API
```python
class MinToolCalls(OutputContract):     key="tool_call_count";  ceiling_key="max_tool_calls";  unit="tool calls"
class MinTokens(OutputContract):        key="tokens_used";      ceiling_key="max_tokens";       unit="tokens"
class MinIterations(OutputContract):    key="iteration_count";  ceiling_key="max_iterations";   unit="iterations"
class MinElapsedSeconds(OutputContract):key="elapsed_seconds";  ceiling_key="timeout_seconds";  unit="seconds"
```

#### Logic / Algorithm
None — all comparison/feedback logic is inherited from `OutputContract`.

#### Edge Cases & Error Handling
- `MinTokens` depends on the provider reporting tokens; when `tokens_used` is `None`/`0`, the counter reads `0` and the floor stays unmet until budget exhaustion. Documented as a known limitation (Section 12).

---

### 6.3 `AgentLoopSettingsOutputContract` owner

**File(s):** `vidbyte/agents/contract.py`
**Type:** New file

#### What it does
Runtime-facing owner of an agent's contracts. Holds the contract tuple and the rejection budget, and exposes the one-line methods the runtime calls. Construction-time floor-vs-ceiling validation is performed by `AgentLoopSettings` (see 6.4), not here — this class is evaluation-only.

#### Interface / API
```python
class AgentLoopSettingsOutputContract:
    def __init__(self, contracts: Sequence[OutputContract], *, max_rejections: int = 3) -> None: ...
    def active(self) -> bool: ...
    def unmet(self, counters: Mapping[str, Any]) -> list[OutputContract]: ...
    def exhausted(self, rejections: int) -> bool: ...
    def feedback(self, unmet: Sequence[OutputContract], counters: Mapping[str, Any]) -> str: ...
    def report(self, counters: Mapping[str, Any]) -> list[dict[str, Any]]: ...
```

#### Logic / Algorithm
1. `__init__` stores `tuple(contracts)` and `max_rejections`. (No settings reference — validation is external.)
2. `active` → `bool(self._contracts)`.
3. `unmet` → `[c for c in contracts if not c.satisfied(counters)]`.
4. `exhausted(rejections)` → `rejections >= self._max_rejections`.
5. `feedback` → `"You cannot finish yet:\n" + "\n".join(f"- {c.error(counters)}" for c in unmet)`.
6. `report` → `[{"name": c.name, "satisfied": c.satisfied(counters), "minimum": c.minimum} for c in contracts]`.

#### Edge Cases & Error Handling
- Empty contracts → `active()` is `False`; runtime skips all evaluation branches.
- Immutable/stateless: no `rejections` stored here — passed in from the runtime local.

---

### 6.4 `AgentLoopSettings` — own + validate contracts

**File(s):** `vidbyte/agents/settings/loop.py`
**Type:** Modified

#### What it does
Adds `output_contracts=` and `max_contract_rejections=` parameters, constructs `self.output_contract`, and validates floor-vs-ceiling conflicts against its own fields.

#### Interface / API
```python
def __init__(self, *, ..., output_contracts: Sequence[OutputContract] = (), max_contract_rejections: int = 3) -> None: ...
# new attribute: self.output_contract: AgentLoopSettingsOutputContract
```

#### Logic / Algorithm
1. Store all existing ceiling fields first (unchanged order).
2. Store `self.max_contract_rejections`.
3. Construct `self.output_contract = AgentLoopSettingsOutputContract(output_contracts, max_rejections=self.max_contract_rejections)` — the raw contracts are also kept (e.g. `self._output_contracts = tuple(output_contracts)`) for validation.
4. Call `self._validate()` last (after all fields exist).
5. Add `_validate_output_contracts()` to `_validate()`:
   - For each contract with a `ceiling_key`, read `ceiling = getattr(self, contract.ceiling_key, None)`; if `ceiling is not None and contract.minimum >= ceiling`, raise `ConfigurationError` (`floor unreachable, require minimum < ceiling`).
6. Add `max_contract_rejections` to `_POSITIVE_INT_FIELDS` (must be > 0).
7. Add `max_contract_rejections` to `__repr__`'s field list. Do **not** add `output_contract`/`output_contracts` to `__repr__` unless active (keep repr clean); optionally include `output_contracts` when non-empty.
8. `to_runtime_config()` is unchanged (contracts not part of `AgentRuntimeConfig`).

#### Edge Cases & Error Handling
- Ceiling not set (`None`) → conflict check skipped for that floor (floor is unbounded, always reachable).
- Validation ordering: the owner + raw contracts must be assigned before `self._validate()` runs, or `_validate_output_contracts` sees nothing.
- `max_contract_rejections <= 0` → rejected via `_POSITIVE_INT_FIELDS`.

---

### 6.5 `AgentRuntime` — enforce at both boundaries

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Accepts an `output_contract`, evaluates it at the no-tool-calls (FINAL_RESPONSE) and isDone (IS_DONE) boundaries, injects corrective feedback and continues while budget remains, and stops with `CONTRACT_UNSATISFIED` when exhausted. Adds counter-snapshot and evaluation-publish helpers, and a name-based internal-tool check.

#### Interface / API
```python
def __init__(self, ..., output_schema=None, output_contract: "AgentLoopSettingsOutputContract | None" = None) -> None: ...
def _contract_counters(self, *, iteration_count, model_call_count, call_contexts, tokens_used, started_at) -> dict[str, Any]: ...
def _publish_contract_evaluations(self, run_state, counters) -> None: ...
def _tool_name_is_internal(self, tool_name: str) -> bool: ...   # extracted from _tool_is_internal
```

#### Logic / Algorithm
1. `__init__`: `self.output_contract = output_contract or AgentLoopSettingsOutputContract(())`.
2. In `_arun_once`, add a local `rejections = 0` alongside the existing counters.
3. **No-tool-calls boundary** (just before `final = self._final_result(output=last_assistant_output, ... FINAL_RESPONSE)` at main ~422): if `output_contract.active()`, build counters, publish evaluations, compute `unmet`; if `unmet and exhausted(rejections)` → return `_finish_result(_stopped_result(..., CONTRACT_UNSATISFIED, ...), ...)`; elif `unmet` → `rejections += 1`, append `{"role":"user","content": feedback}`, `continue`.
4. **isDone boundary** (just before `final = self._final_result(output=result.output, ... IS_DONE)` at main ~543): same decision; on `unmet` (budget remaining) → `rejections += 1`, append the feedback as an `isDone` **error tool-result** via `_append_tool_result_message(messages, call, ToolResult.error(call.tool_name, feedback), provider, MiddlewareDecision.continue_())`, set a `contract_rejected` flag, `break` the tool loop; after the loop, `if contract_rejected: continue`.
5. `_contract_counters` returns `{iteration_count, model_call_count, tool_call_count, tokens_used, elapsed_seconds}`, where `tool_call_count = sum(1 for c in call_contexts if not self._tool_name_is_internal(c.tool_name))`, `tokens_used = tokens_used or 0`, `elapsed_seconds = self.middleware.clock() - started_at`.
6. `_publish_contract_evaluations` writes `run_state.setdefault("__result_metadata__", {})["contract_evaluations"] = self.output_contract.report(counters)` (lifted into `AgentResult.metadata` by existing `_with_run_state_metadata`).
7. Refactor `_tool_is_internal(call)` to delegate to `_tool_name_is_internal(call.tool_name)` (shared by the counter filter); behavior unchanged.
8. Imports: add `AgentLoopSettingsOutputContract` (from `vidbyte.agents.contract`); `AgentStopReason.CONTRACT_UNSATISFIED` already imported via existing dataclass import.

#### Edge Cases & Error Handling
- `output_contract` is `None` (default) or inactive → all new branches are skipped; loop behavior is byte-for-byte the original.
- isDone-inflation: `_tool_name_is_internal` excludes the finishing call from `tool_call_count`.
- Provider not reporting tokens → `MinTokens` unmet until `exhausted`, then `CONTRACT_UNSATISFIED` (documented limitation).
- The corrective tool-result keeps the transcript provider-valid (every tool call gets a matching result before `continue`).

---

### 6.6 `base.py` — wire from settings, guard non-linear

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Sources the runtime's `output_contract` from `self.agent_loop_settings.output_contract` for LINEAR runtimes, and rejects active contracts on non-linear runtimes. Adds **no** `Agent` parameter.

#### Interface / API
```python
# _runtime(): within the kwargs dict assembly
if self.runtime_type is AgentRuntimeType.LINEAR:
    kwargs["output_contract"] = self.agent_loop_settings.output_contract
```

#### Logic / Algorithm
1. In `__init__`, after `_resolve_loop_settings` (near the existing `tool_error_policy` non-linear guard at ~167): if `self.agent_loop_settings.output_contract.active()` and `self.runtime_type is not AgentRuntimeType.LINEAR`, raise `ConfigurationError` (contracts require the linear runtime).
2. In `_runtime()`, add the LINEAR-only `kwargs["output_contract"]` line before the `return runtime_cls(...)`.

#### Edge Cases & Error Handling
- Non-linear + inactive owner → no error (owner is always present but `active()` is `False`).
- LINEAR + inactive owner → owner passed through harmlessly.

---

### 6.7 `AgentStopReason` — new terminal reason

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does
Adds `CONTRACT_UNSATISFIED = "contract_unsatisfied"` to the enum.

#### Logic / Algorithm
Single enum member addition, placed after `TOOL_LOOP_LIMIT`.

---

### 6.8 Package exports

**File(s):** `vidbyte/agents/__init__.py`
**Type:** Modified

#### What it does
Re-exports `OutputContract`, `MinToolCalls`, `MinTokens`, `MinIterations`, `MinElapsedSeconds` from `vidbyte.agents` so users can `from vidbyte.agents import MinToolCalls`.

#### Logic / Algorithm
Add a `from vidbyte.agents.contracts import (...)` line and append the five names to `__all__`.

---

## 7. Data Model Changes

N/A — no database, ORM, or persisted schema. The only "schema" changes are the in-memory counters `dict` (documented in 6.5) and the `AgentStopReason` enum member (6.7).

---

## 8. API Changes

N/A — no HTTP/network endpoints. The public Python API surface changes are: two new `AgentLoopSettings` constructor kwargs (`output_contracts`, `max_contract_rejections`), the new `AgentLoopSettings.output_contract` attribute, and five newly exported classes. All are additive and backward compatible (no existing signature changes; no removals).

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/contracts/__init__.py` | `OutputContract` base + floor re-exports |
| CREATE | `vidbyte/agents/contracts/floors.py` | Four deterministic floors |
| CREATE | `vidbyte/agents/contract.py` | `AgentLoopSettingsOutputContract` runtime-facing owner |
| CREATE | `docs/design/output-contracts-loop-settings.md` | This design doc |
| MODIFY | `vidbyte/agents/settings/loop.py` | Own `output_contracts` + `max_contract_rejections`; construct owner; validate floor-vs-ceiling; repr |
| MODIFY | `vidbyte/agents/runtime.py` | `output_contract` param; two boundary evaluations; counters + publish + internal-tool split |
| MODIFY | `vidbyte/agents/base.py` | LINEAR-only `output_contract` kwarg from settings; non-linear guard |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `CONTRACT_UNSATISFIED` stop reason |
| MODIFY | `vidbyte/agents/__init__.py` | Export `OutputContract` + four floors |

Summary: **4 created, 5 modified, 0 deleted.**

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| (none) | — | Pure-Python, stdlib only (`collections.abc`, `typing`) | None |

No new third-party packages, no external services.

---

## 11. Rollout & Deployment

- **Feature flags:** none. The feature is inert unless a user passes `output_contracts` to `AgentLoopSettings`; the default owner is inactive.
- **Breaking change:** no. All changes are additive; existing agents behave identically (runtime branches are skipped when the owner is inactive).
- **Migration path:** N/A (no prior public API for this feature; PR #243's `Agent(output_contracts=)` was never merged, so nothing to migrate).
- **Deployment order:** single library; no multi-service ordering.
- **Rollback:** revert the PR; no persisted state or data migration to unwind.

---

## 12. Open Questions

- [ ] `AgentLoopSettingsOutputContract` is a verbose name. Keep it (matches user request) or shorten to e.g. `LoopOutputContracts`? **Assumption: keep the user-specified name.**
- [ ] `MinTokens` when the provider never reports tokens: silently unmet → `CONTRACT_UNSATISFIED` on exhaustion. Acceptable for v1, or should unknown-token runs skip the floor? **Assumption: acceptable for v1; documented limitation.**
- [ ] Should `AgentLoopSettings.__repr__` include `output_contracts` when non-empty? **Assumption: include it when non-empty, keep `output_contract` owner out.**
- [ ] Ceiling-vs-floor precedence: if a *different* ceiling (`max_tokens`) trips before a floor is met, the run stops with the ceiling reason, not `CONTRACT_UNSATISFIED`. **Assumption: ceiling wins (existing `_budget_stop` behavior); this is intended and not reported as a contract failure.**

---

## 13. Alternatives Considered

### Alternative 1: Top-level `Agent(output_contracts=)` parameter (PR #243's shape)
- What: Contracts declared on the `Agent` constructor; a separate `AgentOutputContract` owner reaches into `AgentLoopSettings` to read ceilings for validation.
- Why rejected: Splits floors from the ceilings they are defined against across two objects; validation reaches across a boundary; `max_contract_rejections` becomes an orphan on settings while contracts live on the agent. User explicitly chose the single-home model.

### Alternative 2: Pass the whole `AgentLoopSettings` into `AgentRuntime`
- What: Runtime receives the settings object and reads `settings.output_contract` internally.
- Why rejected: Couples the runtime to the full settings surface. The runtime today receives only the minimal `AgentRuntimeConfig`; keeping it receiving just the contract owner (as a dedicated kwarg) preserves the decision/action split and the minimal internal contract.

### Alternative 3: Keep validation inside the owner (`AgentLoopSettingsOutputContract`)
- What: Owner validates floor-vs-ceiling in its constructor, taking a settings reference.
- Why rejected: Re-introduces the cross-object reach the re-home was meant to remove. Since contracts now live inside `AgentLoopSettings`, the settings' own `_validate()` reads its ceiling fields directly — the owner stays purely runtime-facing.

### Alternative 4: Add contracts to `AgentRuntimeConfig`
- What: Thread contracts through `to_runtime_config()`.
- Why rejected: `AgentRuntimeConfig` is a deliberately minimal internal contract; polluting it with the contract owner mixes config-derivation with a runtime-only collaborator. A dedicated `output_contract` kwarg is cleaner.

---

END OF DESIGN DOC
