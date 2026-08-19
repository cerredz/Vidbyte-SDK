# Design Doc: Fallback Policy Mode (ANY / ALL)

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-19
**Last Updated:** 2026-08-19

---

## 1. Overview

PR #339 (`feat/agent-fallback-policies`) lets a developer attach multiple per-hop fallback policies (`LatencyPolicy`, `CostBudgetPolicy`) to an agent's fallback chain. Today those policies trigger independently: any single policy that fires advances the chain. This change adds a top-level combinator — `policies_mode` on `AgentFallbackSettings`, defaulting to `ANY` (today's behavior) — so a developer can instead require **every** configured checkpoint policy to be satisfied before the chain advances ("fall back only when the call is slow *and* over budget", not "slow *or* over budget"). The feature is one parameter, one enum, and a rework of the existing top-of-iteration checkpoint from "first policy with a crossed ceiling wins" into "every voting policy casts a verdict, and the mode composes the verdicts." It adds no new policies.

The mode deliberately governs only the **checkpoint voters** — policies that expose a per-hop `triggered()` verdict evaluated once per loop iteration against the run's usage rollup. The exception-based trigger (`fallback_on`) and `LatencyPolicy` are **hard triggers**: a provider-level error or a timeout always justifies a switch, regardless of the mode. A timeout or an outage either routes to the next model or the run fails; neither can be made to "wait" for a second condition, so gating them on the mode would convert survivable failures into run failures. This boundary is the feature's central design decision and is documented as a non-goal rather than left implicit.

---

## 2. Goals & Non-Goals

### Goals

- Add `FallbackPolicyMode(str, Enum)` with members `ANY = "any"` and `ALL = "all"` to `vidbyte/lib/enums/` (one file per domain, matching `agent_runtime.py`/`model_provider.py`).
- Add `policies_mode: FallbackPolicyMode | str = FallbackPolicyMode.ANY` to `AgentFallbackSettings`, validated at construction (an unknown value raises `ConfigurationError`).
- Rework the checkpoint: each policy that can vote at the checkpoint exposes `triggered(index, signals) -> bool`; `AgentFallback.advance_after_checkpoint(index, *, signals)` composes the verdicts by mode and returns `(next_index, reason)`.
- Preserve today's behavior byte-for-byte when `policies_mode` is unset (`ANY`): any-mode with one voting policy is exactly what `advance_after_success` does today, and the `error_type` reason strings (`"cost_budget_exceeded"`) stay unchanged.
- Under `ALL`, a switch records `error_type: "all_policies_satisfied"` in the existing metadata shape — no new metadata keys, no new span kind.
- Replace the single-policy checkpoint plumbing (`advance_after_success`, `_cost_fallback_transition`) with the vote-based one, removing the now-dead chain-level `budget_for` fold.
- Document the feature in `vidbyte/agents/README.md` and export `FallbackPolicyMode` from `vidbyte.agents.fallback` and `vidbyte.agents`.

### Non-Goals

- **Governing the error trigger (`fallback_on`) or `LatencyPolicy` with the mode.** Both remain hard triggers. Under `ALL`, a provider error or a latency timeout still advances the chain immediately. Gating them would mean "don't fall back on a 429 unless the cost ceiling is also crossed" — converting a routed-around outage into a run failure. Confirmed with the user before implementation.
- **Adding a `triggered()` capability to `LatencyPolicy`.** Latency fires reactively as a `TimeoutError` inside the call (`asyncio.wait_for`), not as a checkpoint vote; there is no boolean to compose. Its exclusion is structural, and the README states it in plain words so `mode=ALL` + `LatencyPolicy` cannot be misread as "slow AND expensive".
- **A per-hop mode array** (`policies_mode_by_hop`). The user explicitly asked for one top-level parameter. If a hop-varying mode is ever needed it slots in as an array-shaped variant later; not built now.
- **New policies.** No `TokenBudgetPolicy` or any other policy is added by this change. The `triggered()` seam is designed so a future policy (e.g. the planned token-budget policy) participates by implementing one method.
- **Changing the `error_type` field shape.** PR #339's open question about promoting the string to a structured `trigger_kind` field stays open; this change adds one more string value (`"all_policies_satisfied"`) to the existing field, consistent with how #339 and the token-budget design doc already add string values.
- **New test files**, per the `/design-doc-no-tests` workflow. The existing suite must stay green.
- **Session serialization.** `RunState`/`export_state`/`restore` don't serialize the fallback chain at all; `policies_mode` rides on the settings object and inherits that same pre-existing gap, not a new one.

---

## 3. Background & Context

### Why now

PR #339 is unmerged at the time of writing (`dcc4dbf`, 5 commits). The fallback subsystem now lives in `vidbyte/agents/fallback/` (`chain.py`, `settings.py`, `policies.py`, `__init__.py`), and two per-hop policies exist. The user is about to add more policies (a token-budget policy is already designed in `docs/design/token-budget-fallback-policy.md`, stacked on the same branch). With two policies the implicit OR is already expressible; the moment a developer wants "only downgrade when *both* conditions hold", no configuration exists for it, and adding a third policy without a combinator would force per-policy boolean AND/OR wiring into the runtime. Building the combinator now — before the third policy lands — lets every future policy participate through one `triggered()` method instead of the runtime growing one near-identical transition method per policy.

### Current state (verified in this repo, against the actual unmerged branch)

- `vidbyte/agents/fallback/policies.py` defines `LatencyPolicy` and `CostBudgetPolicy`. Both expose `hop_values()` (for `AgentFallbackSettings` length/value validation) and one policy-specific getter (`deadline_for` / `budget_for`) returning the value for a chain index or `None` past the array.
- `vidbyte/agents/fallback/chain.py`'s `AgentFallback` folds policies via `_first_policy_value(index, attr)`: first policy exposing a callable `attr` whose result is non-`None` wins. `deadline_for` (used by the runtime's latency wrap) and `budget_for` (used only by `advance_after_success`) ride this fold.
- `AgentFallback.advance_after_success(index, *, cost_usd)` is the single-policy checkpoint: `None` when `cost_usd is None` or `index + 1 >= len(self.models)`, otherwise `index + 1` when `cost_usd >= self.budget_for(index)`.
- `AgentRuntime.arun` runs the checkpoint at `runtime.py:270-287` (branch): `if self.fallback is not None and iteration_count > 0:` calls `_cost_fallback_transition(...)` and, on a non-`None` result, reassigns `handle`, `provider`, `tool_schemas`, `messages`, `fallback_index` and calls `_publish_fallback_metadata`.
- `_cost_fallback_transition` (`runtime.py:798-809`) sources its signal from `self.usage_tracker.rollup().cost_usd` — the same `UsageTracker` the field guide (`field-guide/vidbyte-sdk/runtime-boundaries.md`, "Keep model usage accounting agent-owned") requires runtimes to reuse rather than duplicate. `UsageRollup` (`agents/pricing/records.py`) carries `cost_usd: float | None`, `total_tokens: int | None`, and `output_tokens: int | None`, all computed by the same `rollup()`.
- `AgentFallbackSettings` (`fallback/settings.py`) already validates per-hop policies generically via duck-typed `hop_values()`; it imports `ModelProvider` from `vidbyte.lib.enums`, so the enum package is an established dependency.
- `vidbyte/lib/enums/` is a package, one file per domain (`agent_runtime.py`, `model_provider.py`, ...), each with a Context Protocol Header, re-exported from `vidbyte/lib/enums/__init__.py`.
- `fork()` re-passes `agent._fallback_spec` — the original settings object — to child constructors, so `policies_mode` inherits across forks for free; no change to `fork.py`.
- No test file references `AgentFallback`, `AgentFallbackSettings`, `LatencyPolicy`, or `CostBudgetPolicy` by name (verified in PR #339's own audit), so removing `advance_after_success`/`budget_for` carries no hidden suite pins.

### Baseline

`python -m pytest tests/ -q` on the branch tip (`dcc4dbf`): **1555 passed, 1 skipped, 0 failed** (PR #339's own recorded baseline). This change must keep that result exactly, plus green `scripts/run_ci.py`.

---

## 4. Requirements

### Functional Requirements

1. `FallbackPolicyMode(str, Enum)` with `ANY = "any"`, `ALL = "all"`, importable from `vidbyte.lib.enums`, `vidbyte.agents.fallback`, and `vidbyte.agents`.
2. `AgentFallbackSettings.__init__` accepts `policies_mode: FallbackPolicyMode | str = FallbackPolicyMode.ANY`. A value that is neither member raises `ConfigurationError` at construction naming the offending value.
3. `AgentFallbackSettings.to_fallback()` passes the mode through to `AgentFallback`.
4. `CostBudgetPolicy` gains `triggered(index, signals) -> bool` — `True` exactly when `signals.cost_usd` is known and at/above the hop's ceiling — and a class constant `reason = "cost_budget_exceeded"`. `LatencyPolicy` gains neither.
5. `FallbackSignals` is a frozen dataclass (`cost_usd: float | None`, `total_tokens: int | None`) defined in `vidbyte/agents/fallback/policies.py` — the input contract of a checkpoint vote.
6. `AgentFallback.advance_after_checkpoint(index, *, signals) -> tuple[int, str] | None` replaces `advance_after_success`:
   - `None` when `index + 1 >= len(self.models)` (nothing left to advance to) or when no configured policy exposes `triggered` (no checkpoint voters — this guard is mandatory: `all([])` is `True` in Python and would otherwise cascade every run under `ALL`).
   - Under `ANY`: `(index + 1, policy.reason)` for the first policy whose `triggered` is `True`, else `None`.
   - Under `ALL`: `(index + 1, "all_policies_satisfied")` when every voting policy's `triggered` is `True`, else `None`.
7. `AgentFallback.policies_mode` is stored at construction and defaults to `FallbackPolicyMode.ANY`. `AgentFallback.budget_for` is removed (its only consumer, `advance_after_success`, is replaced); `_first_policy_value` and `deadline_for` remain (latency plumbing).
8. `AgentRuntime._cost_fallback_transition` is replaced by `_checkpoint_fallback_transition` with the same signature and reassignment flow, building `FallbackSignals` from a single `self.usage_tracker.rollup()` read and using the reason returned by `advance_after_checkpoint` in `policy_attempt_record`.
9. The checkpoint in `arun` remains a single `if self.fallback is not None and iteration_count > 0:` block; the guard placement, `_publish_fallback_metadata`, span recording, and `transform` flow are unchanged.
10. A run with no `policies_mode` set, or with `policies_mode=FallbackPolicyMode.ANY` and one voting policy, behaves identically to the branch tip: same triggers, same `error_type` strings, same metadata.
11. Under `ALL`, an unmeasurable signal (e.g. `cost_usd is None` because no provider reported usage) votes `False` — the run fails closed and does not advance on a condition it could not verify.
12. `AgentFallbackSettings.__repr__` shows `policies_mode=FallbackPolicyMode.ALL` when the mode is not the default, mirroring the existing `enabled=False` repr pattern.

### Non-Functional Requirements

- **Performance:** one extra attribute-fold per iteration when policies exist (identical cost to today's `advance_after_success`); zero overhead when `self.fallback is None`. The `rollup()` read is unchanged — it already happens for the cost check today.
- **Concurrency:** `policies_mode` is an immutable field on the already-immutable `AgentFallback`; the chain stays safe under `arun_sequentially`/`asyncio.gather` exactly as today.
- **Observability:** every mode-composed switch is recorded through the existing `AgentResult.metadata["fallback"]` shape and `agent.fallback` span, distinguished only by the `error_type` string.
- **Security:** no credential material in the new surface; `FallbackSignals` carries only usage numbers.
- **Correctness:** the mode is validated once at settings construction; the checkpoint never re-validates.

---

## 5. High-Level Design

The change replaces the "first policy with a crossed ceiling wins" checkpoint with "every policy that can vote casts a verdict; the mode composes the verdicts." Voting policies (today: `CostBudgetPolicy`; tomorrow: token-budget and any other budget-style policy) implement one method — `triggered(index, signals) -> bool` — plus a `reason` constant. Non-voting policies (`LatencyPolicy`) and the error trigger are untouched and remain hard triggers.

```
AgentFallbackSettings(models=[...], policies=[CostBudgetPolicy(...)], policies_mode=ALL)
        |  to_fallback(primary=...)
        v
AgentFallback(models=..., policies=..., policies_mode=ALL)
        |
        +-- advance_after_checkpoint(index, signals)   <-- NEW, replaces advance_after_success
        |      votes = [p.triggered(index, signals) for p in policies if p exposes triggered]
        |      ANY: first True  -> (index+1, p.reason)
        |      ALL: all True    -> (index+1, "all_policies_satisfied")
        |      no voters        -> None        (guards against all([]) == True)
        |
        +-- deadline_for(index) --> latency wrap   [unchanged, hard trigger via TimeoutError]
        +-- advance(error, index)                   [unchanged, hard trigger via fallback_on]

AgentRuntime.arun, top-of-iteration checkpoint (iteration_count > 0):
        _checkpoint_fallback_transition          <-- NEW, replaces _cost_fallback_transition
              signals = FallbackSignals(**rollup slice)
              next_index, reason = advance_after_checkpoint(index, signals)
              -> policy_attempt_record(index, next_index, reason)
              -> transform -> swap locals -> publish metadata      [unchanged flow]
```

The mode is a property of the chain, not of any policy, because AND/OR composes *across* policies — there is no per-policy reading of "all". The single evaluation point is a structural requirement of AND, not a refactor for its own sake.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/enums/fallback.py` (new) and `vidbyte/lib/enums/__init__.py`

**File(s):** both
**Type:** New + modified

#### What it does

Defines the mode enum in the repo's canonical enum home and re-exports it.

#### Interface / API

```python
"""Context Protocol Header (Description/Purpose/Architecture/Relations/Similar Files)"""

from __future__ import annotations
from enum import Enum


class FallbackPolicyMode(str, Enum):
    """String-backed enum composing multiple per-hop fallback policies into one trigger."""

    ANY = "any"
    ALL = "all"
```

`vidbyte/lib/enums/__init__.py` gains `from vidbyte.lib.enums.fallback import FallbackPolicyMode` and the name in `__all__` (alphabetical position: after `DocumentType`, before `ContextMinimalFanoutSkill` — match the existing ordering at implementation time).

#### Edge Cases & Error Handling

N/A — enum members are validated at consumption (`AgentFallbackSettings` wraps `ValueError` into `ConfigurationError`).

---

### 6.2 `vidbyte/agents/fallback/policies.py`

**File(s):** `vidbyte/agents/fallback/policies.py`
**Type:** Modified

#### What it does

Adds the vote contract (`FallbackSignals` + `triggered`/`reason`) to the policy surface. `LatencyPolicy` is deliberately untouched — it has no `triggered`.

#### Interface / API

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FallbackSignals:
    """Usage snapshot a checkpoint policy votes against; a None signal is unmeasurable, never a trigger."""

    cost_usd: float | None = None
    total_tokens: int | None = None


class CostBudgetPolicy:
    # ... existing __init__/hop_values/budget_for unchanged ...
    reason = "cost_budget_exceeded"

    def triggered(self, index: int, signals: FallbackSignals) -> bool:
        # Votes True when run cost is known and at/above this hop's ceiling; unmeasurable votes False.
        return signals.cost_usd is not None and signals.cost_usd >= self.budget_for(index)
```

#### Logic / Algorithm

`triggered` reads the policy's own array (`self.budget_for(index)` — the policy method, not the chain fold), so no `_first_policy_value` involvement. `reason` is a class constant so the vote composition can name the trigger without an if/else on policy kind.

#### Edge Cases & Error Handling

- `signals.cost_usd is None` (no provider in the run ever reported usage): votes `False`. Under `ANY` that matches today's no-op; under `ALL` the run fails closed and stays on the current model.
- Hop index past the configured array: `self.budget_for(index)` returns `None`, the comparison `cost_usd >= None` would raise — so the `signals.cost_usd is not None` guard is what makes this total. `triggered` never raises.

---

### 6.3 `vidbyte/agents/fallback/chain.py`

**File(s):** `vidbyte/agents/fallback/chain.py`
**Type:** Modified

#### What it does

Stores the mode and replaces the single-policy checkpoint with the mode-composing vote.

#### Interface / API

```python
class AgentFallback:
    def __init__(self, models, *, fallback_on=DEFAULT_FALLBACK_ERRORS, policies=(), policies_mode: FallbackPolicyMode = FallbackPolicyMode.ANY) -> None: ...

    def advance_after_checkpoint(self, index: int, *, signals: FallbackSignals) -> tuple[int, str] | None: ...
    # advance_after_success: DELETED (replaced)
    # budget_for: DELETED (dead — only advance_after_success consumed it)
    # deadline_for, _first_policy_value: UNCHANGED
```

#### Logic / Algorithm

1. `__init__` stores `self.policies_mode = policies_mode` alongside `models`/`fallback_on`/`policies`. No validation here — the mode is validated at `AgentFallbackSettings` construction, the only production path that builds a chain with a mode (mirroring why policies are not re-validated here).
2. `advance_after_checkpoint`:

```python
def advance_after_checkpoint(self, index: int, *, signals: FallbackSignals) -> tuple[int, str] | None:
    # Returns (next_index, reason) when the checkpoint vote elects to advance, or None to stay.
    if index + 1 >= len(self.models):
        return None
    votes = [(policy, policy.triggered(index, signals)) for policy in self.policies if hasattr(policy, "triggered")]
    if not votes:
        return None
    if self.policies_mode is FallbackPolicyMode.ALL:
        if not all(triggered for _, triggered in votes):
            return None
        return index + 1, "all_policies_satisfied"
    for policy, triggered in votes:
        if triggered:
            return index + 1, policy.reason
    return None
```

3. The duck-typed `hasattr(policy, "triggered")` filter is the same optional-capability idiom `_first_policy_value` already uses for `deadline_for`/`budget_for` — no `typing.Protocol`, matching the codebase's established line.

#### Edge Cases & Error Handling

- **Empty vote list** (e.g. `policies=[LatencyPolicy(...)]` with any mode): the `if not votes: return None` guard prevents `all([]) == True` from advancing every run under `ALL`. This is the feature's most dangerous silent-failure trap and the guard is load-bearing.
- **Same-kind stacking** (two `CostBudgetPolicy` instances): both vote; under `ALL` the higher ceiling governs, under `ANY` the first-declared firing policy wins — coherent, not validated as an error, matching PR #339's stance on stacking.
- **Last chain index**: the first guard returns `None` — a crossed ceiling on the terminal model is not actionable, the run continues on that model (identical to `advance_after_success`'s guard).
- **`None` signal**: fails closed via the policy's own `triggered` (Section 6.2).

---

### 6.4 `vidbyte/agents/fallback/settings.py`

**File(s):** `vidbyte/agents/fallback/settings.py`
**Type:** Modified

#### What it does

Accepts, validates, and forwards `policies_mode`.

#### Interface / API

```python
class AgentFallbackSettings:
    def __init__(self, *, models: Sequence[str | FallbackModel], fallback_on: tuple[type[BaseException], ...] | None = None, policies: Sequence[object] = (), policies_mode: FallbackPolicyMode | str = FallbackPolicyMode.ANY, enabled: bool = True) -> None: ...
```

#### Logic / Algorithm

1. `__init__` coerces the mode before storing: `self.policies_mode = self._resolve_policies_mode(policies_mode)`.
2. `_resolve_policies_mode` (static): `FallbackPolicyMode(policies_mode)` inside `try/except ValueError`, raising `ConfigurationError` on failure with the offending value named — the same coercion idiom `_split_provider_prefix` already uses for `ModelProvider`.
3. `to_fallback()` passes `policies_mode=self.policies_mode` to `AgentFallback(...)`.
4. `__repr__` appends `, policies_mode=FallbackPolicyMode.ALL` only when the mode is not `ANY`, mirroring the existing `enabled=False` conditional.

#### Edge Cases & Error Handling

- `policies_mode="bogus"` → `ConfigurationError` at construction, before any agent exists.
- `policies_mode=None` → `ValueError` from the enum coercion, wrapped into `ConfigurationError` (the type annotation excludes it, but the coercion still guards it — no silent `None` reaching the chain).
- Default `FallbackPolicyMode.ANY`: zero behavior change, verified by the mode-composition falling through to first-triggered semantics.

---

### 6.5 `vidbyte/agents/runtime.py`

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does (changes only)

Replaces the cost-only checkpoint transition with the mode-composing one. The `arun` call site block keeps its shape.

#### Interface / API

```python
def _checkpoint_fallback_transition(self, *, index: int, handle: RunnerHandle, provider: str, messages: list[dict[str, Any]], attempts: list[dict[str, str]], parent_span: SpanContext | None) -> "FallbackTransform | None": ...
```

#### Logic / Algorithm

1. The `arun` checkpoint block (branch lines 270-287) changes the method name only — `cost_transition = self._cost_fallback_transition(...)` becomes `checkpoint_transition = self._checkpoint_fallback_transition(...)`; the reassignment/`_publish_fallback_metadata` body is unchanged.
2. `_checkpoint_fallback_transition`:

```python
def _checkpoint_fallback_transition(self, *, index, handle, provider, messages, attempts, parent_span):
    # Returns rebuilt state when the checkpoint vote elects to downgrade, or None to keep the current model.
    rollup = self.usage_tracker.rollup()
    decision = self.fallback.advance_after_checkpoint(
        index, signals=FallbackSignals(cost_usd=rollup.cost_usd, total_tokens=rollup.total_tokens),
    )
    if decision is None:
        return None
    next_index, reason = decision
    record = self.fallback.policy_attempt_record(index, next_index, reason)
    attempts.append(record)
    transition = self.fallback.transform(handle, provider, self.tools, messages, next_index)
    self._record_fallback_span(record, transition.context_reset, parent_span)
    return transition
```

3. `FallbackSignals` is imported at runtime (not `TYPE_CHECKING`) — it is constructed here; `total_tokens` is read even though no current policy votes on it, so a future token-budget policy needs zero runtime changes.

#### Edge Cases & Error Handling

- `self.fallback is None`: the outer `if` guard skips entirely — zero overhead.
- `usage_tracker.rollup()` returning all-`None` signals: every policy votes `False` (Section 6.2), `ANY` and `ALL` both no-op — the run continues on the current model rather than raising.
- Reason string flows through the existing `policy_attempt_record` — no change to `_build_attempt_record`, `result_metadata`, or the metadata shape.

---

### 6.6 Exports and documentation

**Files:** `vidbyte/agents/fallback/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/agents/README.md`
**Type:** Modified

- `vidbyte/agents/fallback/__init__.py`: add `FallbackPolicyMode` and `FallbackSignals` to the import lines and `__all__`.
- `vidbyte/agents/__init__.py`: add `FallbackPolicyMode` to the fallback import line and `__all__` (alphabetically, between `FallbackModel` and `FallbackTransform`). `FallbackSignals` stays one level deeper — it is an internal vote contract, not a developer-facing name.
- `vidbyte/agents/README.md` "Fallback Policies" section:
  - New bullet: `policies_mode=FallbackPolicyMode.ALL` requires *every* configured policy to be satisfied before the chain advances proactively; the default `ANY` advances when any policy fires. `error_type` reports `"all_policies_satisfied"` under ALL.
  - New bullet (the trap): the mode applies only to checkpoint policies. `LatencyPolicy` and provider errors always trigger a fallback regardless of the mode — ALL does not mean "slow AND expensive" unless both are checkpoint policies.
  - Extend the example with `policies_mode=FallbackPolicyMode.ALL` and its import.
  - Update the "Key Modules" entry for `policies.py` to mention the vote contract.

---

## 7. Data Model Changes

N/A — no database, no persisted schema. `FallbackSignals` is an in-process frozen dataclass; `RunState` does not serialize the fallback chain today (pre-existing, unrelated non-goal) and `policies_mode` inherits that.

---

## 8. API Changes

N/A for HTTP endpoints — this is a library. The Python surface changes are additive except where noted:

| Surface | Change | Breaking |
|---|---|---|
| `AgentFallbackSettings(policies_mode=...)` | New optional keyword-only param, defaults `FallbackPolicyMode.ANY` | No |
| `FallbackPolicyMode` | New enum export (`vidbyte.lib.enums`, `vidbyte.agents.fallback`, `vidbyte.agents`) | No |
| `FallbackSignals` | New dataclass export (`vidbyte.agents.fallback` only) | No |
| `CostBudgetPolicy.triggered` / `CostBudgetPolicy.reason` | New vote-contract members | No |
| `AgentFallback.advance_after_checkpoint` | New method | No |
| `AgentFallback.advance_after_success`, `AgentFallback.budget_for` | **Deleted** — added in unreleased PR #339, no external callers (verified: only `_cost_fallback_transition` consumed them, replaced here) | No (pre-release) |
| `AgentRuntime._cost_fallback_transition` | Renamed to `_checkpoint_fallback_transition` | No (private) |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/fallback-policy-mode.md` | This design doc; first commit on the branch |
| CREATE | `vidbyte/lib/enums/fallback.py` | `FallbackPolicyMode` |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Re-export `FallbackPolicyMode` |
| MODIFY | `vidbyte/agents/fallback/policies.py` | `FallbackSignals`, `CostBudgetPolicy.triggered`/`reason` |
| MODIFY | `vidbyte/agents/fallback/chain.py` | `policies_mode`, `advance_after_checkpoint`; delete `advance_after_success`/`budget_for` |
| MODIFY | `vidbyte/agents/fallback/settings.py` | `policies_mode` param, coercion/validation, pass-through, repr |
| MODIFY | `vidbyte/agents/runtime.py` | `_checkpoint_fallback_transition` replaces `_cost_fallback_transition` |
| MODIFY | `vidbyte/agents/fallback/__init__.py` | Export `FallbackPolicyMode`, `FallbackSignals` |
| MODIFY | `vidbyte/agents/__init__.py` | Export `FallbackPolicyMode` |
| MODIFY | `vidbyte/agents/README.md` | Document `policies_mode` and the hard-trigger boundary |

**Totals:** 2 created (1 doc, 1 source), 8 modified, 0 deleted.

No files under `tests/` are created or modified, per the `/design-doc-no-tests` workflow.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| — | — | No new runtime dependencies | None |

Built entirely from existing internals: `AgentFallback` folds, the `UsageTracker`/`UsageRollup` pair (`agents/pricing/records.py`), and the `vidbyte.lib.enums` package. `pyproject.toml` is unchanged.

---

## 11. Rollout & Deployment

- **Base branch is `feat/agent-fallback-policies` (PR #339), not `main`.** This PR is a stack: it cannot merge before #339 does, and its diff shows only the mode-specific changes while #339 remains unmerged. If #339 merges first, this branch should be rebased onto `main` before finalizing.
- No feature flag: `policies_mode` defaults to `ANY`, which reproduces the branch tip's behavior exactly — an agent that doesn't set it sees zero behavior change.
- Not a breaking change for any documented public API: the only deletions (`advance_after_success`, `budget_for`, `_cost_fallback_transition`) are internal/pre-release names added by the unmerged base PR.
- Single-repo change (`vidbyte-sdk`). No coordinated deployment.
- Rollback: revert this PR (or, while stacked, simply close it) — nothing persisted, nothing migrated.

---

## 12. Open Questions

- [ ] **Should `"all_policies_satisfied"` enumerate the satisfied policies** (e.g. `"cost_budget_exceeded,token_budget_exceeded"`) instead of one generic string? Decided: single generic string, because the `error_type` field is a string and embedding a list into it is a shape change nothing has asked for. Inherited from PR #339: the structured `trigger_kind` question stays open and would be the natural home for a richer answer.
- [ ] **Should the mode be per-hop** (`policies_mode_by_hop`) once the chain semantics demand it? Not built — the user asked for one parameter. A future array-shaped variant would slot in beside `policies_mode` without breaking it.
- [ ] **Should `ALL` + `LatencyPolicy` (a non-voting policy) be rejected at construction instead of documented?** Decided: document, not reject — the combination "latency hard trigger + ALL over the budget policies" is coherent and useful, and rejecting it would forbid a legitimate configuration to protect against a misreading the README prevents.

---

## 13. Alternatives Considered

### Alternative 1: The mode governs every trigger, including errors and latency

- **What:** Under `ALL`, a provider error or latency timeout only advances the chain when the checkpoint policies are also satisfied; otherwise the error re-raises and the run fails.
- **Why rejected:** it converts a survivable outage (429/529/timeout) into a run failure whenever the second condition isn't met — the availability story of the whole fallback feature would depend on a dollar ceiling being crossed. Nothing in the user's request ("the fallback requires ALL of the policies to be true") asked to make errors *harder* to fall back from; confirmed with the user before implementation.

### Alternative 2: Keep the two sequential single-policy checks and compose at the runtime

- **What:** Leave `advance_after_success`/`_cost_fallback_transition` in place, add `advance_after_token_budget`-style methods per policy, and let the runtime's two sequential blocks decide whether both fired.
- **Why rejected:** AND is unobservable with first-wins folds — `advance_after_success` returns a decision for *one* policy kind and cannot express "cost didn't fire but token did, so under ALL nobody fires". The composition would leak policy arithmetic into the runtime, and every future policy would add a third sequential block. The single vote point is the smallest place the requirement can be expressed.

### Alternative 3: A `typing.Protocol` requiring `triggered` on every policy

- **What:** A formal `FallbackPolicy(Protocol)` with `triggered`, implemented by both policies (LatencyPolicy returning a permanent `False`).
- **Why rejected:** forces a no-op vote method onto a policy that structurally cannot vote, and doesn't match how this codebase draws the optional-capability line — `_first_policy_value` and `_bind_session_tool` (`agents/base.py`) both use plain `getattr`/`callable()` duck typing. The `hasattr(policy, "triggered")` filter follows the established idiom.

### Alternative 4: `policies_mode` as a plain string (`"any"`/`"all"`) without an enum

- **What:** Accept bare strings and validate membership.
- **Why rejected:** every other mode-like value in the repo is a `str, Enum` in `vidbyte/lib/enums/` (`AgentRuntimeType`, `ModelProvider`, `OrchestratorAction`, ...); a bare-string parameter would be the only untyped mode knob in the codebase and would invite typos the validator catches later than it should. The enum is the repo's grain.

### Alternative 5: Put `FallbackSignals` in a new `signals.py` module

- **What:** A third module in the fallback package for the vote input contract.
- **Why rejected:** the contract belongs with the policy interface it feeds (`policies.py` already hosts `hop_values()`/`deadline_for`/`budget_for`); a one-dataclass module is a file nobody would look in first. `chain.py` importing from `policies.py` is acyclic (`policies.py` imports nothing from the package).

---

## 14. CI Gate

Per the repo field guide (`field-guide/vidbyte-sdk/local-ci-verification.md`) and PR #339's own verification, from inside the implementation worktree:

```bash
PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source
python scripts/run_ci.py --stage package
python scripts/run_ci.py
```

The `PYTHONPATH` prefix applies to the source stage only — without it the editable install resolves `vidbyte` to the canonical checkout and silently tests old code; leaking it into the package stage breaks that stage's fresh-venv install check. Both stages, then the full run, must pass before this PR is opened.