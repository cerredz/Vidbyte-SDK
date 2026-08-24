# Design Doc: Tool-Call Loop Detection Fallback Policy

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-19
**Last Updated:** 2026-08-19

---

## 1. Overview

Adds `ToolCallLoopPolicy`, a third fallback-chain trigger alongside `LatencyPolicy` and `CostBudgetPolicy` (introduced in #339, not yet merged). It detects the classic "stuck" pattern where an agent calls the same tool with the same (or near-identical) arguments repeatedly instead of making progress, and advances the fallback chain to the next model when that happens. Unlike its two siblings, it is **chain-wide, not per-hop** — the same rationale the codebase already applies to `fallback_on` (README: "every hop shares the same set") applies here: tolerance for a stuck tool-calling pattern isn't a property of which model in the chain happens to be active.

---

## 2. Goals & Non-Goals

### Goals

- Add `ToolCallLoopPolicy(window_size=..., repeat_threshold=..., ignored_argument_keys=...)` to `vidbyte/agents/fallback/policies.py`, validated eagerly at construction.
- Add `AgentFallback.advance_after_loop_detected(index, call_contexts)` to `vidbyte/agents/fallback/chain.py`, mirroring `advance_after_success`'s shape.
- Wire a new proactive check into `AgentRuntime.arun`'s main loop (`runtime.py`), at the same top-of-iteration checkpoint `CostBudgetPolicy` already uses, via a new `_loop_fallback_transition` method mirroring `_cost_fallback_transition`.
- Extract the tool-call fingerprinting hash (`tool_name` + sorted-JSON args → sha256) that already exists once, inline, in `ToolSettings.fingerprint` (`vidbyte/agents/settings/tool.py`) into a shared free function `fingerprint_tool_call` in `vidbyte/lib/dataclasses/tools.py`, and have both `ToolSettings` and `ToolCallLoopPolicy` call it — removing the existing duplication this change would otherwise triple.
- Export `ToolCallLoopPolicy` from `vidbyte/agents/fallback/__init__.py` and `vidbyte/agents/__init__.py`, and document it in `vidbyte/agents/README.md` alongside the other two policies.

### Non-Goals

- Not per-hop. No `hop_values()`, no participation in `AgentFallbackSettings`'s per-hop array-length validation. This mirrors the existing, deliberate `fallback_on` precedent, not an oversight.
- No new mutable/stateful tracking object (no deque, no dict fed by a `record()` call) attached to the policy instance. `AgentFallback` — and everything it holds, including its `policies` tuple — is constructed once in `BaseAgent.__init__` (`base.py:155-157`) and lives for the agent's lifetime, shared across every `arun()` / `arun_sequentially()` call on that instance. A policy holding its own mutable per-run state would leak history across runs and race under concurrent `arun()` calls on the same agent, breaking the concurrency invariant the design doc for #339 explicitly protects ("the only mutable state (`fallback_index`) stays a loop-local integer"). Detection reads the existing `call_contexts` list instead, which is already a fresh, run-local list (`runtime.py:180`).
- Not wired into `BaseAgent._run_non_text_runner` (image/audio/video/embedding runners) — same reason Latency/Cost aren't: that path has no per-iteration checkpoint loop to hang a proactive check off of.
- No new metadata shape. Reuses `AgentFallback.policy_attempt_record` / `AgentResult.metadata["fallback"]` exactly as Cost policy does, with `error_type` carrying the string `"tool_call_loop_detected"`.
- Does not move the fingerprint/decision logic into `ToolSettings`. Considered and rejected — see Alternatives.

---

## 3. Background & Context

### Why now

Direct follow-up to the design conversation that produced #339 (`feat/agent-fallback-policies`, currently open, based on `main`). That PR built the `policies=[...]` list mechanism and its duck-typed, skip-if-absent validation specifically so future trigger conditions could be added without touching `AgentFallbackSettings`. This is the first policy to actually exercise that extensibility.

### Current state (verified in this repo, this session, on `origin/feat/agent-fallback-policies` @ `dcc4dbf`)

- `AgentFallback.policies: tuple[object, ...]` (`chain.py:68`) is duck-typed. `AgentFallbackSettings._validate_policy_hop_values` does `getattr(policy, "hop_values", None)`; a policy without it is silently skipped, not rejected — already true today, confirmed by reading `settings.py` on this branch.
- The proactive (non-error) checkpoint lives in `AgentRuntime.arun`'s main loop at `runtime.py:270-286`, immediately after the `_budget_stop` return-check and guarded by `iteration_count > 0` (so the first model call, before any state exists, is never checked). `CostBudgetPolicy` hooks in there via `_cost_fallback_transition` (`runtime.py:798-807`).
- `call_contexts: list[ToolCallContext]` (`runtime.py:180`) accumulates every tool call for the entire run, appended in `_process_tool_call` (`runtime.py:1551`, confirmed at that exact line via grep on this branch). Each entry already carries `tool_name`, `arguments`, and `iteration_count` (`vidbyte/lib/dataclasses/tools.py:223-234`). This is sufficient state for detection — nothing new needs to be tracked.
- `ToolSettings` (`vidbyte/agents/settings/tool.py`) already solves an adjacent problem statelessly: `max_identical_calls` / `fingerprint()` / `_identical_call_budget_stop()` (`tool.py:82-89`, `154-170`) count fingerprint-matched calls across all of `call_contexts` to decide whether to *deny* a call. It does not window the count, and its consequence (deny/abort) is different from this policy's consequence (advance the chain) — so it isn't directly reusable as a decision, but its fingerprint hash (`json.dumps(..., sort_keys=True, default=str)` → sha256, `tool.py:84-88`) is the exact computation this policy also needs, currently written inline in one place. Extracting it means this change doesn't create a second, slightly-different copy.
- `ToolSettings.__init__`/`ToolErrorPolicy.__init__` (`settings/tool.py`, `settings/tool_error.py`) both self-validate at construction and raise `ConfigurationError` — the established pattern nested policy objects in this codebase follow, independent of whatever container holds them.
- `AgentFallback.__init__` and `AgentFallbackSettings.__init__` already accept `policies: Sequence[object] = ()` with no fixed set of allowed types — zero signature changes required in either file.

### Baseline

`python -m pip install -e ".[dev]"` then `python scripts/run_ci.py` must pass on this branch before and after the change, matching the `#339` baseline of 1555 passed / 1 skipped / 0 failed (per that PR's own design doc; re-verified fresh at the start of Phase 4 of this change).

---

## 4. Requirements

### Functional Requirements

1. `ToolCallLoopPolicy(window_size: int = 8, repeat_threshold: int = 3, ignored_argument_keys: frozenset[str] = frozenset())` validates `window_size > 0`, `repeat_threshold > 0`, and `repeat_threshold <= window_size` at construction, raising `ConfigurationError` on violation. `ignored_argument_keys` defaults to empty — no invented default key names (no evidence any built-in tool emits volatile fields like timestamps or request IDs).
2. `ToolCallLoopPolicy.is_stuck(call_contexts: Sequence[ToolCallContext]) -> bool` inspects only the last `window_size` entries of `call_contexts`. It fingerprints each entry via the shared `fingerprint_tool_call(tool_name, arguments, ignored_keys=...)` and groups by fingerprint, counting **distinct `iteration_count` values per fingerprint**, not raw occurrence count. Returns `True` when any fingerprint's distinct-iteration count reaches `repeat_threshold`.
   - Counting distinct iterations rather than raw occurrences means legitimate same-iteration parallel fan-out (the model issuing several structurally-identical calls concurrently within one iteration, e.g. a search tool called 3x in parallel with the same query by design) does not by itself trip the detector — it only fires when the *same* call recurs across `repeat_threshold` separate iterations, which is the actual "not making progress" signal.
3. `fingerprint_tool_call(tool_name: str, arguments: Mapping[str, Any], *, ignored_keys: frozenset[str] = frozenset()) -> str` is added to `vidbyte/lib/dataclasses/tools.py`, filtering `ignored_keys` out of `arguments`, then `json.dumps(..., sort_keys=True, default=str)` → sha256, truncated to 16 hex chars, prefixed with `tool_name`. Byte-identical to the logic currently inline in `ToolSettings.fingerprint`.
4. `ToolSettings.fingerprint` (`tool.py:82-89`) is refactored to call `fingerprint_tool_call`, deleting its own inline `hashlib`/`json` logic. Its existing behavior (and every existing caller) is unchanged — this is a pure extraction, not a behavior change. Now-unused `import hashlib` / `import json` are removed from `tool.py`.
5. `AgentFallback.advance_after_loop_detected(index: int, call_contexts: Sequence[ToolCallContext]) -> int | None` returns `None` when `index + 1 >= len(self.models)` (last model in the chain, nowhere to advance — matches `advance_after_success`'s own bounds guard) or when no chain-wide policy reports `is_stuck(call_contexts) is True`; otherwise returns `index + 1`.
6. `AgentFallback._is_loop_stuck(call_contexts) -> bool` folds over `self.policies`, calling `is_stuck(call_contexts)` on any policy that exposes it (duck-typed via `getattr`/`callable`, matching the existing `_first_policy_value` idiom), returning `True` on the first hit.
7. `AgentRuntime.arun`'s main loop checks the loop-detection policy once per iteration, at `runtime.py:270-286` — immediately **after** the existing cost-policy block, so it observes any state the cost check already changed — using a new `_loop_fallback_transition` helper that mirrors `_cost_fallback_transition`'s shape exactly (ask `AgentFallback` for a next index; on a hit, build the record via `policy_attempt_record(index, next_index, "tool_call_loop_detected")`, append it, call `transform`, record the span, return the transition; on `None`, no-op).
8. `ToolCallLoopPolicy` is exported from `vidbyte/agents/fallback/__init__.py` and re-exported from `vidbyte/agents/__init__.py`, matching exactly how `LatencyPolicy`/`CostBudgetPolicy` are exported today.
9. `vidbyte/agents/README.md`'s "Fallback Policies" section documents the new policy with the same structure (rules list) used for the other two; the "Key Modules" bullet for `fallback/` is updated to mention all three policy classes.

### Non-Functional Requirements

- **Performance:** zero added cost on a run with no `policies=` configured, or none exposing `is_stuck` — `_is_loop_stuck` short-circuits over an empty/non-matching tuple exactly like `_first_policy_value` does today. When configured, one check costs `O(window_size)`, a small constant (default 8), once per iteration — no new O(run-length) scans, since only the tail slice of `call_contexts` is inspected.
- **Concurrency:** `ToolCallLoopPolicy` holds only immutable configuration (`window_size`, `repeat_threshold`, `ignored_argument_keys`) set at construction and never mutated — no different from `LatencyPolicy`/`CostBudgetPolicy`. Detection reads `call_contexts`, which is already loop-local to one `arun()` call. The policy object is safe to share across concurrent runs on the same agent for the same reason its siblings already are.
- **Observability:** identical to Cost policy — same `AgentResult.metadata["fallback"]` shape, same `agent.fallback` trace span, distinguished only by `error_type: "tool_call_loop_detected"`.
- **Security:** no credential material touches this policy; it only ever sees tool names and arguments already present in `call_contexts`.
- **Correctness:** `window_size`/`repeat_threshold` are validated exactly once, at `ToolCallLoopPolicy` construction — never re-validated per call, matching `ToolSettings`/`ToolErrorPolicy`'s own self-validating-nested-object precedent.

---

## 5. High-Level Design

The chain-wide/per-hop split already exists conceptually in this codebase (`fallback_on` is chain-wide; Latency/Cost are per-hop), so this change doesn't introduce a new architectural axis — it exercises the one already there. The new policy plugs into the exact extensibility seam #339 built for this purpose: `AgentFallback.policies` is a duck-typed bag, and `AgentFallbackSettings`'s hop-count validation already no-ops for any policy lacking `hop_values()`. No changes to `AgentFallbackSettings` or `AgentFallback.__init__` are required.

```
ToolCallLoopPolicy(window_size=8, repeat_threshold=3)
        |  is_stuck(call_contexts) -- reads the tail of the run's existing call history
        v
AgentFallback.advance_after_loop_detected(index, call_contexts)
        |  folds over self.policies via _is_loop_stuck, same getattr/callable idiom as deadline_for/budget_for
        v
AgentRuntime.arun main loop, runtime.py:270 -- new block right after the existing
CostBudgetPolicy check, calling the new _loop_fallback_transition (mirrors
_cost_fallback_transition) -- on a hit, the same transform()/publish-metadata
sequence every other trigger already uses
```

The only two genuinely new pieces of runtime logic are `ToolCallLoopPolicy.is_stuck` and the fingerprint extraction; everything downstream of "a policy says advance" (`transform`, the runner cache, wire-compatibility handling, metadata/span shape) is reused verbatim from the error and cost paths.

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/dataclasses/tools.py`

**File(s):** `vidbyte/lib/dataclasses/tools.py`
**Type:** Modified

#### What it does
Adds a module-level fingerprint function co-located with `ToolCallContext`, the dataclass it operates on, so it isn't owned by either consumer's business logic.

#### Interface / API
```python
def fingerprint_tool_call(tool_name: str, arguments: Mapping[str, Any], *, ignored_keys: frozenset[str] = frozenset()) -> str: ...
```

#### Logic / Algorithm
1. Filter `arguments` to drop any key in `ignored_keys`.
2. `json.dumps(filtered, sort_keys=True, default=str)`; fall back to `str(filtered)` on `TypeError` (matches `ToolSettings.fingerprint`'s existing `except Exception` fallback, narrowed to `TypeError` since that's the only realistic failure from `json.dumps` with `default=str` already set).
3. sha256 the serialized string, take the first 16 hex chars, prefix with `tool_name`.

#### Edge Cases & Error Handling
- Non-JSON-serializable argument values (e.g. custom objects): handled by `default=str` first; the `try/except` is a second-layer fallback for anything `str()`-incompatible with `json.dumps`'s traversal, matching existing behavior.
- Empty `arguments`: `json.dumps({})` is well-defined (`"{}"`), no special case needed.

---

### 6.2 `vidbyte/agents/settings/tool.py`

**File(s):** `vidbyte/agents/settings/tool.py`
**Type:** Modified

#### What it does
Removes the now-duplicate inline fingerprint logic; delegates to the shared function.

#### Logic / Algorithm
- `fingerprint()` becomes `return fingerprint_tool_call(tool_name, dict(arguments or {}))` — one line, same output for every existing input, since the extraction is byte-for-byte identical logic.
- `import hashlib` and `import json` removed (no longer used anywhere else in the file, confirmed by reading the full file this session).
- Import list gains `fingerprint_tool_call` alongside the existing `from vidbyte.lib.dataclasses.tools import ToolCallContext, ToolCallState, ToolResult`.

#### Edge Cases & Error Handling
- N/A — pure extraction, no behavior change. Existing callers (`_identical_call_budget_stop`) are untouched.

---

### 6.3 `vidbyte/agents/fallback/policies.py`

**File(s):** `vidbyte/agents/fallback/policies.py`
**Type:** Modified (adds a third class to the existing file)

#### What it does
Defines `ToolCallLoopPolicy`, the chain-wide repeated-tool-call detector.

#### Interface / API
```python
class ToolCallLoopPolicy:
    def __init__(self, *, window_size: int = 8, repeat_threshold: int = 3, ignored_argument_keys: frozenset[str] = frozenset()) -> None: ...
    def is_stuck(self, call_contexts: Sequence["ToolCallContext"]) -> bool: ...
```

Deliberately **does not** implement `hop_values()`, `deadline_for()`, or `budget_for()` — it is chain-wide, discovered by `AgentFallback` via a different duck-typed attribute (`is_stuck`), and skipped entirely by `AgentFallbackSettings`'s per-hop validation, which only inspects `hop_values`.

#### Logic / Algorithm
1. `__init__` stores the three fields, then validates: `window_size` and `repeat_threshold` must be positive ints (not bool, matching the existing `isinstance(value, bool)` exclusion pattern from `settings.py`'s own hop-value validation); `repeat_threshold` must not exceed `window_size`, or the trigger could never fire.
2. `is_stuck` slices `call_contexts[-self.window_size:]`, fingerprints each entry via `fingerprint_tool_call`, and builds `dict[str, set[int | None]]` mapping fingerprint → the distinct `iteration_count`s it appeared at. Returns `True` if any set's length reaches `repeat_threshold`.

#### Edge Cases & Error Handling
- `len(call_contexts) < window_size`: Python's slice semantics handle this natively (`[-8:]` on a 3-item list returns all 3) — no explicit bounds check needed.
- Same-iteration parallel duplicate calls: counted as one distinct-iteration entry per iteration, not one per call — see Functional Requirement 2's rationale.
- `repeat_threshold > window_size`: rejected at construction (Functional Requirement 1), not left to silently never-fire at runtime.
- Denied and internal-tool call contexts: deliberately **not** excluded from the window, unlike `ToolSettings`'s own `_is_excluded_context` filter. A call the agent keeps retrying after it was denied is itself evidence of a stuck pattern this policy exists to catch, not noise to filter — `ToolSettings`'s exclusion exists because its job (consumption budgets) is different and must stay immune to denial noise. The internal `isDone` tool cannot trigger this by construction: calling it ends the run immediately (`runtime.py`'s `call.tool_name == IS_DONE_TOOL_NAME` branch), so it can never appear more than once in `call_contexts`.

---

### 6.4 `vidbyte/agents/fallback/chain.py`

**File(s):** `vidbyte/agents/fallback/chain.py`
**Type:** Modified

#### What it does
Adds the chain's decision method for this trigger, placed immediately after `advance_after_success` (`chain.py:117-124`).

#### Interface / API
```python
def advance_after_loop_detected(self, index: int, call_contexts: Sequence["ToolCallContext"]) -> int | None: ...
def _is_loop_stuck(self, call_contexts: Sequence["ToolCallContext"]) -> bool: ...
```

#### Logic / Algorithm
1. `advance_after_loop_detected`: bounds-check first (`index + 1 >= len(self.models)` → `None`, cheaper than fingerprinting when there's nowhere to go anyway), then ask `_is_loop_stuck`; return `index + 1` or `None`.
2. `_is_loop_stuck`: iterate `self.policies`, `getattr(policy, "is_stuck", None)`, call if callable, return `True` on first `True` result — same shape as `_first_policy_value` (`chain.py:134-142`), boolean-OR instead of first-non-None.
3. `ToolCallContext` added to the existing `TYPE_CHECKING` block (`chain.py:41-44`) for the type hints — no runtime import needed, matching how this file already defers `Tools`/`AgentRunnerConfig`.

#### Edge Cases & Error Handling
- `self.policies` empty or containing no `is_stuck`-exposing policy: `_is_loop_stuck` returns `False`, `advance_after_loop_detected` returns `None` — identical no-op path to today, before this change existed.

---

### 6.5 `vidbyte/agents/runtime.py`

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Adds the second proactive checkpoint of the main loop, and the transition helper it calls.

#### Logic / Algorithm
1. New method `_loop_fallback_transition`, inserted immediately after `_cost_fallback_transition` (after `runtime.py:807`), mirroring its exact shape: ask `self.fallback.advance_after_loop_detected(index, call_contexts)`; `None` → `None`; otherwise build the record via `policy_attempt_record(index, next_index, "tool_call_loop_detected")`, append to `attempts`, call `transform`, record the span, return the transition.
2. New block inserted at `runtime.py:287` (immediately after the existing cost-check block closes at line 286, before `decision = await self.middleware.before_iteration(...)` at line 288): guarded by the same `if self.fallback is not None and iteration_count > 0:` condition, calls `_loop_fallback_transition` with the **current** (possibly cost-check-updated) `handle`/`provider`/`fallback_index`, and on a non-`None` result applies the identical `handle, provider = ...` / `tool_schemas, messages = ...` / `fallback_index = ...` / `_publish_fallback_metadata(...)` sequence the cost block uses.
3. `ToolCallContext` is already imported at module level (`runtime.py:62`) — no new import required for this file.

#### Edge Cases & Error Handling
- Cost and loop checks both firing on the same iteration: sequential, not simultaneous — the loop check runs second and sees whatever model the cost check already switched to, so it can advance a second hop in the same iteration if warranted (`fallback_index` is correctly threaded through both blocks).
- `self.fallback is None`: both new pieces are no-ops, identical to how Cost policy already behaves when no chain is configured.
- Loop-detection fires on the last usable transition (`fallback_index` already at the last index): `advance_after_loop_detected`'s own bounds guard returns `None` — the run continues on the current model rather than raising, matching Cost policy's identical last-hop behavior. An agent stuck on its final model keeps looping until `max_iterations`/`max_tool_calls` trips, which is an existing, accepted limitation `CostBudgetPolicy` already has — not a new gap introduced here.

---

### 6.6 `vidbyte/agents/fallback/__init__.py`, `vidbyte/agents/__init__.py`

**File(s):** both
**Type:** Modified

#### What it does
Adds `ToolCallLoopPolicy` to both export surfaces, in the same alphabetical position pattern already used for `LatencyPolicy`/`CostBudgetPolicy`.

---

### 6.7 `vidbyte/agents/README.md`

**File(s):** `vidbyte/agents/README.md`
**Type:** Modified

Adds a bullet list entry to "Fallback Policies" (after the existing `CostBudgetPolicy` bullet, before the `fallback_on`/non-text-runner bullets that apply to all policies) describing the window/threshold semantics and the chain-wide (not per-hop) distinction, and updates the "Key Modules" `fallback/` bullet to list all three policy classes.

---

## 7. Data Model Changes

N/A — no persisted schema. Same as #339: `AgentFallback`/`AgentFallbackSettings`/policy objects are in-process only; `RunState` does not serialize the fallback chain today, and this change does not alter that.

---

## 8. API Changes

N/A — no HTTP/REST surface. This is an in-process SDK constructor addition (`ToolCallLoopPolicy`) and two new methods (`AgentFallback.advance_after_loop_detected`, `_is_loop_stuck`). Public developer-facing surface:

```python
from vidbyte.agents import ToolCallLoopPolicy
from vidbyte.agents.settings import AgentFallbackSettings

agent = Agent(
    ...,
    fallback=AgentFallbackSettings(
        models=["gpt-5-mini"],
        policies=[ToolCallLoopPolicy(window_size=8, repeat_threshold=3)],
    ),
)
```

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | Add shared `fingerprint_tool_call` function |
| MODIFY | `vidbyte/agents/settings/tool.py` | Delegate `ToolSettings.fingerprint` to the shared function; drop now-unused imports |
| MODIFY | `vidbyte/agents/fallback/policies.py` | Add `ToolCallLoopPolicy` |
| MODIFY | `vidbyte/agents/fallback/chain.py` | Add `advance_after_loop_detected` / `_is_loop_stuck` |
| MODIFY | `vidbyte/agents/runtime.py` | Add `_loop_fallback_transition` + main-loop checkpoint |
| MODIFY | `vidbyte/agents/fallback/__init__.py` | Export `ToolCallLoopPolicy` |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export `ToolCallLoopPolicy` |
| MODIFY | `vidbyte/agents/README.md` | Document the new policy |

No files created or deleted.

---

## 10. Dependencies & External Services

None. Pure stdlib (`json`, `hashlib`, already dependencies of the extracted function's new home) plus existing in-repo types.

---

## 11. Rollout & Deployment

- No feature flag — matches Latency/Cost, which shipped the same way. A run with no `policies=` configured is behaviorally unchanged (opt-in by construction).
- Not a breaking change. `ToolSettings.fingerprint`'s public behavior is unchanged (pure internal refactor).
- **This PR targets `feat/agent-fallback-policies` (#339), not `main`** — an explicit, deliberate stacked PR, per this repo's own precedent for building on an in-flight design (and per this session's explicit instruction). Known risk in this repo: two prior stacked PRs (#302, #282) silently lost work when their base branch was squash-merged to `main` without the stacked PR being retargeted first, because squash-merge doesn't update the base branch. Mitigation: once #339 merges, this PR's base must be retargeted to `main` (or recreated via the repo's established `-target-main` cherry-pick pattern) promptly — not left pointing at a branch that's about to become a dead ref.
- CI gate: `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py`, run from this worktree, must be fully green before the PR is opened and before it's considered done.

---

## 12. Open Questions

- [ ] Should `ignored_argument_keys` ship with any default entries once real-world tool usage shows a genuine volatile field (e.g. if a built-in tool starts emitting a request id)? Left empty for this change — no evidence today justifies a guessed default.
- [ ] Should this policy eventually be extended to `BaseAgent._run_non_text_runner` the way a possible future Latency extension is floated in #339's own open questions? Same answer as Latency's: that path has no iteration loop to check per-iteration, so it's out of scope here too.

---

## 13. Alternatives Considered

### Alternative 1: Per-hop `repeat_threshold_by_hop`, matching Latency/Cost's shape
- What: Make `ToolCallLoopPolicy` implement `hop_values()` like its siblings, with a different tolerance per fallback hop.
- Why rejected: No product story supports "the primary model gets more retries before being declared stuck than a fallback." Latency/Cost are per-hop because different models have genuinely different speed/price; tool-call-loop susceptibility isn't a property of which model is currently serving the call. This mirrors why `fallback_on` itself stays chain-wide in #339's own design.

### Alternative 2: Push-based state — `ToolCallLoopPolicy.record(call)` fed from `_process_tool_call`, `should_fallback()` queried from a policy-owned dict
- What: The policy maintains its own in-memory structure of recent calls, updated via an explicit push at the point a tool call is made, rather than reading `call_contexts`.
- Why rejected: `AgentFallback` (and every policy it holds) is constructed once in `BaseAgent.__init__` and reused for the agent's lifetime across every `arun()`/`arun_sequentially()` call. Policy-owned mutable state would leak tool-call history across unrelated runs on the same agent instance and race under concurrent `arun()` calls — breaking the concurrency invariant #339's own design doc protects (only loop-local `fallback_index` is mutable state today). `call_contexts` is already a fresh, run-local list maintained by the runtime for other reasons; reading it costs nothing and duplicates no state. Separately, a `deque(maxlen=N)` cannot be correctly paired with an incrementally-updated counts dict, since eviction gives no callback — any correct implementation ends up re-deriving counts from the deque on each check anyway, which is the same computation as slicing `call_contexts`, plus a redundant second copy of data the runtime already tracks.

### Alternative 3: Add the detection predicate as a new method on `ToolSettings` (e.g. `is_tool_call_looping(...)`), called from the fallback policy
- What: Since `ToolSettings` already has adjacent-looking logic (`max_identical_calls`, `sliding_window_max_calls`), put the new windowed+fingerprint-scoped counting there and have `ToolCallLoopPolicy` delegate to it.
- Why rejected: Neither existing `ToolSettings` mechanism actually computes what's needed — `max_identical_calls` is fingerprint-scoped but unbounded (no window); `sliding_window_max_calls` is windowed but counts total calls, not fingerprint matches. Adding this combination to `ToolSettings` wouldn't reuse existing behavior, it would add new logic to a class whose stated purpose (`tool.py`'s own docstring) is "universal tool-use constraints" it directly enforces (denial, truncation, abort) — nothing else in that file has any relationship to model-fallback routing. The class whose job is "decide whether to advance the chain" should own the computation that decision is based on, matching how `LatencyPolicy`/`CostBudgetPolicy` already work. What *is* shared is the much smaller fingerprint hash (Alternative accepted — see Section 6.1/6.2).

### Alternative 4: Check loop-detection inside `_process_tool_call`, denying/rerouting before the redundant call executes
- What: Since `ToolSettings.budget_stop` already runs pre-execution inside `_process_tool_call`, put the loop check there too, potentially avoiding wasted tool executions.
- Why rejected: That call site's job is "should this specific call be permitted," a `ToolSettings` concern with a deny/abort consequence. Advancing the fallback chain requires rebuilding `handle`/`provider`/`tool_schemas`/`messages` — state owned by the outer loop in `arun`, not by `_process_tool_call` or any function it calls (this is the same reasoning #339's own Alternative 4 used to reject putting the cost check inside `_invoke_with_middleware`'s retry loop instead of the outer loop). Keeping all three proactive/reactive triggers at the same architectural altitude (the outer loop) is more consistent than special-casing one of them.
