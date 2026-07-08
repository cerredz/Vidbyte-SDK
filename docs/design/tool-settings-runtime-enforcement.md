# Design Doc: Tool Settings Runtime Enforcement

**Status:** Draft
**Author:** Claude
**Created:** 2026-07-08
**Last Updated:** 2026-07-08

---

## 1. Overview

Add a small, universal `ToolSettings` configuration object to `vidbyte-sdk` and enforce it **directly inside the direct agent runtime**, the same way `AgentLoopSettings` budgets (`max_iterations`, `max_tokens`, `max_tool_calls`) are enforced today — via `AgentRuntimeConfig` and inline runtime checks. `ToolSettings` lets developers deny named tools, cap total tool use, cap per-tool use, and truncate model-visible tool results without composing middleware. The enforcement decision logic lives on `ToolSettings` itself (pure, stateless methods); the runtime owns per-run counting and translates each decision into its existing effects (inject a denied tool result into context, stop the run, or truncate the visible result). This supersedes the middleware-based approach drafted in PR #249.

---

## 2. Goals & Non-Goals

### Goals

- Add `ToolSettings` under `vidbyte.agents.settings`, exported from `vidbyte.agents.settings`, `vidbyte.agents`, and `vidbyte`.
- Support exactly these settings: `denied_tools`, `max_calls`, `max_calls_per_tool`, `result_max_chars`, plus an `on_deny` policy knob (`"continue"` | `"abort"`).
- Carry `ToolSettings` into the runtime through `AgentRuntimeConfig`, the same pipe used by the existing loop budgets.
- Enforce all tool settings **inside `AgentRuntime`** (the linear/direct runtime), with no dedicated middleware class.
- Keep decision logic on `ToolSettings` as pure, stateless methods; keep per-run counters in the runtime, derived from the existing `call_contexts` record.
- `denied_tools` and over-limit `max_calls_per_tool` calls inject a denied tool result into the model context and continue the loop when `on_deny="continue"` (default), or stop the run when `on_deny="abort"`.
- `max_calls` stops the run before executing an over-budget tool call, including a same-iteration guard for multi-tool model responses.
- `result_max_chars` truncates only the model-visible tool result, preserving the raw `ToolResult` in `ToolCallContext`.
- Add an `AgentStopReason.TOOL_SETTINGS_DENIED` so an `on_deny="abort"` stop is observable and not mislabeled as a middleware abort.
- Reject `tool_settings` on non-linear runtimes with a clear `ConfigurationError`, matching the existing non-linear restrictions.
- Preserve backward compatibility with `AgentLoopSettings.max_tool_calls`.

### Non-Goals

- No middleware class for tool settings. (`ToolSettingsMiddleware` from PR #249 is not part of this design.)
- No allowlist. The policy surface is denied-only.
- No timeout, parallelism, caching, sandbox, schema, or argument-coercion settings.
- No public behavior change when `tool_settings` is omitted.
- No enforcement inside non-linear runtimes (actor/MCTS); those reject `tool_settings` at construction instead.
- No new external dependencies.
- No test-file additions in this design-doc-no-tests workflow. Verification uses import/compile smoke checks after implementation.

---

## 3. Background & Context

`AgentLoopSettings` (`vidbyte/agents/settings/loop.py`) centralizes loop controls and converts to the internal `AgentRuntimeConfig` via `to_runtime_config()`. `BaseAgent` resolves the settings (`base.py:172`: `self.runtime_config = self.agent_loop_settings.to_runtime_config()`) and passes the config into the runtime (`base.py:725`: `config=self.runtime_config`). The direct runtime then reads budgets from `self.config` and enforces them inline — e.g. `_budget_stop()` (`runtime.py:1376`) checks `self.config.max_tool_calls` and returns a graceful `_stopped_result`. No middleware is involved for these budgets.

PR #249 introduced `ToolSettings` but enforced it through an auto-registered `ToolSettingsMiddleware`. That created a second enforcement model living beside the runtime-native budgets. The user's decision is to unify on the runtime-native model: config object → `to_runtime_config()` → `self.config.tool_settings` → inline runtime enforcement, with the decision logic owned by `ToolSettings`.

The runtime already exposes every seam needed:

- `_process_tool_call()` (`runtime.py:1263`) is the single per-call chokepoint. Returning an `AgentResult` from it stops the loop (`runtime.py:469`).
- `_middleware_denied_tool()` (`runtime.py:1029`) already builds a `ToolResult.error(...)` and a `DENIED` `ToolCallContext`; the caller appends the visible result to `messages` (`runtime.py:1343`). This is exactly the "inject denial into context" behavior. It will be generalized/renamed to a policy-neutral `_denied_tool_result()`.
- `_budget_stop()` and `_stopped_result()` provide the graceful-stop precedent.
- `call_contexts` is the run-scoped list of `ToolCallContext`; denied calls are recorded with `state=DENIED`. Per-tool executed counts are derived from it, so no new per-run state structure is required.

The most important semantic point (unchanged from PR #249): `denied_tools` is useful even when tools are passed explicitly — it documents team policy and blocks dynamically attached tools by name at call time.

---

## 4. Requirements

### Functional Requirements

1. `ToolSettings` must accept `denied_tools: Iterable[str] = ()`.
2. `ToolSettings` must accept `max_calls: int | None = None`.
3. `ToolSettings` must accept `max_calls_per_tool: Mapping[str, int] | None = None`.
4. `ToolSettings` must accept `result_max_chars: int | None = None`.
5. `ToolSettings` must accept `on_deny: str = "continue"` restricted to `"continue"` or `"abort"`.
6. `ToolSettings` must normalize tool-name collections into immutable internal values (stripped names, `frozenset`/`dict`).
7. `ToolSettings` must raise `ConfigurationError` for blank denied tool names, blank per-tool keys, a non-iterable/`str` `denied_tools`, `max_calls < 1`, any `max_calls_per_tool` value `< 1`, `result_max_chars < 0`, or an `on_deny` outside the allowed set.
8. `ToolSettings` must expose pure, stateless decision methods used by the runtime: a denial check and a result-truncation transform.
9. `AgentLoopSettings` must accept `tool_settings: ToolSettings | None = None`, validate its type, and reject a `max_tool_calls` vs `ToolSettings.max_calls` mismatch (equal values are accepted and mapped once).
10. `AgentLoopSettings.to_runtime_config()` must map `ToolSettings.max_calls` into `AgentRuntimeConfig.max_tool_calls` and pass the `ToolSettings` object through as `AgentRuntimeConfig.tool_settings`.
11. `AgentLoopSettings.__repr__()` must include `tool_settings` when provided.
12. `AgentRuntimeConfig` must carry `tool_settings: ToolSettings | None = None` without introducing an import cycle.
13. Denied tools must not execute; a denied call must produce the existing denied tool-result path so the model sees it was blocked, then the loop continues (when `on_deny="continue"`).
14. `denied_tools` must apply to user tools and dynamically attached tools by name; it must never block the internal `isDone` tool.
15. `max_calls` must stop the run before executing a tool call that would exceed the total budget, including a same-iteration guard before executing the 2nd+ tool call of a multi-tool model response.
16. `max_calls_per_tool` must deny the over-budget call (letting the model choose a different tool next turn) when `on_deny="continue"`, or stop the run when `on_deny="abort"`.
17. Per-run, per-tool execution counts must be derived from `call_contexts` (executed = state not `DENIED`), not stored on the shared `ToolSettings` instance.
18. `result_max_chars` must truncate only the model-visible result appended to provider messages and must not mutate the raw `ToolResult` stored in `ToolCallContext`; `result_max_chars=0` is valid.
19. `on_deny="abort"` must stop the run via `_stopped_result` with `AgentStopReason.TOOL_SETTINGS_DENIED`.
20. Non-linear runtimes (`MCTS_SEARCH`, `ACTOR_MODEL`, `ACTOR_MODEL_P2P`, `ACTOR_MODEL_BROADCAST`) must raise `ConfigurationError` when `tool_settings` is provided.
21. Public imports must allow `from vidbyte.agents.settings import ToolSettings`, `from vidbyte.agents import ToolSettings`, and `from vidbyte import ToolSettings`.

### Non-Functional Requirements

- **Compatibility:** Agents without `tool_settings` behave identically; existing `max_tool_calls` continues to work.
- **Concurrency safety:** No per-run mutable state on the shared `ToolSettings` instance; counts derive from run-local `call_contexts`, so concurrent runs of one agent cannot cross-contaminate.
- **Security:** Denied tools are blocked before execution, including dynamically attached tools resolved by name.
- **Context control:** Result truncation reduces model-visible bloat while preserving raw runtime metadata.
- **Performance:** Denial and truncation checks are O(k) in the number of prior tool calls for per-tool counting (derived from `call_contexts`), which is already bounded by the run's tool budget; no additional allocations beyond the existing string slicing.
- **Observability:** Denied calls carry existing denial metadata; abort stops carry `AgentStopReason.TOOL_SETTINGS_DENIED` and a reason string.

---

## 5. High-Level Design

`ToolSettings` becomes a plain, eagerly-validated, **stateless** settings class under `vidbyte/agents/settings/tool.py`, a sibling of `AgentLoopSettings`. It owns the policy *decision* logic as pure methods; it holds no per-run counters. `AgentLoopSettings` gains a `tool_settings` field and threads it through `to_runtime_config()` into a new `AgentRuntimeConfig.tool_settings` field, alongside mapping `max_calls` into the existing `max_tool_calls` budget.

`AgentRuntime` reads `self.config.tool_settings` and enforces it inline at its existing chokepoints — no middleware. In `_process_tool_call()` the runtime, for non-internal tools:

1. Applies a same-iteration total-budget guard (`max_calls`).
2. Asks `ToolSettings` whether the call is denied (`denied_tools` / `max_calls_per_tool`, counts derived from `call_contexts`). A denial either injects a denied result and continues, or stops the run, based on `on_deny`.
3. Executes the tool normally when allowed.
4. After execution, asks `ToolSettings` to produce the truncated model-visible result (`result_max_chars`) while leaving the raw `ToolResult` untouched.

`BaseAgent` gains one guard: reject `tool_settings` on non-linear runtimes. No middleware wiring is added. The `ToolSettingsMiddleware` from PR #249 is not created.

```
AgentLoopSettings(tool_settings=ToolSettings(...))
      |
      v
to_runtime_config()  ->  AgentRuntimeConfig(max_tool_calls=..., tool_settings=...)
      |
      v
BaseAgent  ->  AgentRuntime(config=...)      # config carries tool_settings
      |
      v
AgentRuntime._process_tool_call(call, call_contexts, ...)
   ts = self.config.tool_settings
   if ts and not tool_is_internal:
     - same-iteration total-budget guard (max_calls) -> _stopped_result(MAX_TOOL_CALLS)
     - denial = ts.denial(name, executed_counts_from(call_contexts))
         if denial and on_deny == "abort" -> _stopped_result(TOOL_SETTINGS_DENIED)
         if denial                        -> _denied_tool_result(...) ; append ; continue
   ... execute_tool_call(...) ...
   visible = ts.truncate(result) if ts else result   # raw ToolResult unchanged
   messages.append(format_tool_result(call, visible, provider))
```

---

## 6. Detailed Design

### 6.1 ToolSettings

**File(s):** `vidbyte/agents/settings/tool.py`
**Type:** New file

#### What it does

Defines the developer-facing universal tool settings object, owns eager validation, and exposes pure decision methods the runtime calls. Holds no per-run state.

#### Interface / API

```python
class ToolSettings:
    def __init__(self, *, denied_tools: Iterable[str] = (), max_calls: int | None = None, max_calls_per_tool: Mapping[str, int] | None = None, result_max_chars: int | None = None, on_deny: str = "continue") -> None: ...
    def denial(self, tool_name: str, executed_counts: Mapping[str, int]) -> tuple[str, dict] | None: ...
    def truncate(self, result: ToolResult) -> ToolResult: ...
    @property
    def aborts_on_deny(self) -> bool: ...
```

#### Logic / Algorithm

1. `__init__` normalizes `denied_tools` to a `frozenset[str]` of stripped names, `max_calls_per_tool` to a validated `dict[str, int]`, stores `max_calls`, `result_max_chars`, `on_deny`, then calls `_validate()`.
2. `_validate()` enforces integer bounds (`max_calls >= 1`, `result_max_chars >= 0`) and the `on_deny` membership, raising `ConfigurationError`.
3. `denial(tool_name, executed_counts)` returns `("tool_settings_denied", {"tool_name": ...})` if the name is in `denied_tools`; else `("tool_settings_max_calls_per_tool", {...})` if a per-tool limit exists and `executed_counts.get(name, 0) >= limit`; else `None`.
4. `truncate(result)` returns `result` unchanged when `result_max_chars is None` or `len(result.output) <= result_max_chars`; otherwise returns a new `ToolResult` with output sliced to `result_max_chars` plus a truncation indicator and truncation metadata (`tool_settings_truncated`, `original_chars`, `visible_chars`, `truncated_chars`).
5. `aborts_on_deny` returns `self.on_deny == "abort"`.
6. `__repr__()` shows only active fields.

#### Edge Cases & Error Handling

- Blank denied names / per-tool keys, `str`/`bytes` for `denied_tools`, non-int numerics, out-of-bound numerics, and invalid `on_deny` all raise `ConfigurationError` at construction.
- `result_max_chars=0` is valid (hides the body except the truncation indicator).
- Duplicate denied names collapse via `frozenset`; `max_calls_per_tool=None` and `{}` are equivalent.
- `denial()` and `truncate()` never mutate the instance; they are safe to call concurrently.

---

### 6.2 AgentLoopSettings Integration

**File(s):** `vidbyte/agents/settings/loop.py`
**Type:** Modified

#### What it does

Adds `tool_settings` as a nested settings object, reconciles `ToolSettings.max_calls` with the existing `max_tool_calls`, and threads both into `AgentRuntimeConfig`.

#### Interface / API

```python
class AgentLoopSettings:
    def __init__(self, *, ..., max_tool_calls: int | None = None, ..., tool_settings: "ToolSettings | None" = None) -> None: ...
```

#### Logic / Algorithm

1. Import `ToolSettings` from `vidbyte.agents.settings.tool`.
2. Store `tool_settings`; call `_validate_tool_settings()` from `_validate()`.
3. `_validate_tool_settings()` raises `ConfigurationError` when `tool_settings` is not a `ToolSettings`, or when both `max_tool_calls` and `tool_settings.max_calls` are set and differ.
4. `to_runtime_config()` computes `max_tool_calls = tool_settings.max_calls if (tool_settings and tool_settings.max_calls is not None) else self.max_tool_calls`, and passes both `max_tool_calls=...` and `tool_settings=self.tool_settings` to `AgentRuntimeConfig`.
5. `__repr__()` includes `tool_settings` when set.

#### Edge Cases & Error Handling

- Existing `AgentLoopSettings(max_tool_calls=20)` remains valid and unchanged.
- `AgentLoopSettings(tool_settings=ToolSettings(max_calls=20))` maps to the same runtime budget and additionally passes the object through.
- Both set to different values → `ConfigurationError`; equal values accepted.

---

### 6.3 AgentRuntimeConfig Field

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Carries the `ToolSettings` object into the runtime alongside the loop budgets.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
    tool_settings: "ToolSettings | None" = None
```

#### Logic / Algorithm

1. Add the `tool_settings` field with default `None`.
2. Use a `TYPE_CHECKING`-guarded import of `ToolSettings` (module already uses `from __future__ import annotations`, so the annotation stays a string and no import cycle is created).
3. `__post_init__` numeric validation is unchanged (the field needs no numeric check; `ToolSettings` self-validates).

#### Edge Cases & Error Handling

- Default `None` preserves all existing construction sites.
- No runtime type check here; `AgentLoopSettings` already validates the object.

---

### 6.4 AgentRuntime Enforcement

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Enforces `ToolSettings` inline at the per-call chokepoint and generalizes the denied-result helper to be policy-neutral.

#### Interface / API

```python
class AgentRuntime:
    async def _process_tool_call(self, call, provider, messages, call_contexts, *, ...) -> tuple[ToolCallContext, ToolResult] | AgentResult: ...
    def _denied_tool_result(self, call: ToolCall, provider: str, reason: str, metadata: Mapping[str, Any]) -> tuple[ToolCallContext, ToolResult]: ...
    @staticmethod
    def _executed_counts(call_contexts: Sequence[ToolCallContext]) -> dict[str, int]: ...
```

#### Logic / Algorithm

1. Rename/refactor `_middleware_denied_tool(call, provider, decision)` into policy-neutral `_denied_tool_result(call, provider, reason, metadata)` that builds the same `ToolResult.error("Tool denied: <reason>")` + `DENIED` `ToolCallContext`. Keep the existing `MiddlewareAction.DENY_TOOL` caller working by passing `decision.reason` / `decision.metadata` through the new signature.
2. Add `_executed_counts(call_contexts)`: returns `{name: count}` over `call_contexts` where `state is not ToolCallState.DENIED`.
3. In `_process_tool_call`, after computing `tool_is_internal` and before the existing `before_tool_call` middleware hook, insert a tool-settings block guarded by `ts = self.config.tool_settings; if ts is not None and not tool_is_internal:`
   - **Total budget same-iteration guard:** `if ts.max_calls is not None and len(call_contexts) >= ts.max_calls: return self._stopped_result("Agent runtime stopped after reaching max_tool_calls.", stop_reason=AgentStopReason.MAX_TOOL_CALLS, iteration_count=..., tokens_used=..., contexts=call_contexts)`.
   - **Denial:** `denial = ts.denial(call.tool_name, self._executed_counts(call_contexts))`. If `denial is not None`:
     - if `ts.aborts_on_deny`: `return self._stopped_result(f"Agent runtime stopped by tool settings: {reason}", stop_reason=AgentStopReason.TOOL_SETTINGS_DENIED, ...)`.
     - else: build `context_record, result = self._denied_tool_result(call, provider, reason, metadata)`, append to `call_contexts`, append the visible (denied) result to `messages` via `ToolsFormatter.format_tool_result`, and `return context_record, result` so the loop continues to the next call/iteration.
4. The existing middleware hooks and `execute_tool_call` path are unchanged for allowed calls.
5. **Truncation:** at the point where `visible_result` is finalized (`runtime.py:1340-1342`), after any middleware transform, add: `if ts is not None and not tool_is_internal: visible_result = ts.truncate(visible_result)`. The raw `result`/`context_record` are untouched, preserving raw metadata.

#### Edge Cases & Error Handling

- Internal tools (including `isDone`) bypass all tool-settings enforcement.
- A denied call appends a `DENIED` context, so it is excluded from `_executed_counts` and never consumes a per-tool budget.
- The same-iteration guard only triggers when `tool_settings.max_calls` is set, preserving legacy `max_tool_calls` semantics (which stop at iteration boundaries via `_budget_stop`). `_budget_stop` continues to enforce the boundary case for both.
- Truncation composes with existing context-window admission middleware: the middleware transform is applied first, then tool-settings truncation caps the visible result; raw state is preserved regardless.

---

### 6.5 BaseAgent Guard

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Rejects `tool_settings` on non-linear runtimes, consistent with the existing middleware/tracing/algorithm restrictions. Adds no middleware wiring.

#### Interface / API

```python
class BaseAgent:
    def __init__(self, ...): ...  # existing non-linear guard block extended
```

#### Logic / Algorithm

1. In the existing non-linear runtime guard block (`base.py:107`), after resolving `self.agent_loop_settings`, add: if the runtime is non-linear and `self.agent_loop_settings.tool_settings is not None`, raise `ConfigurationError(f"Agent {name} uses non-linear runtime {self.runtime_type.value}, which does not support tool_settings.")`.
2. Because `self.agent_loop_settings` is resolved later (`base.py:165`), the check is placed immediately after resolution rather than in the early guard block, or the early block reads the passed `agent_loop_settings`/flat params. Implementation resolves settings first, then runs the non-linear `tool_settings` check.

#### Edge Cases & Error Handling

- Linear runtime: no change.
- Non-linear runtime without `tool_settings`: no change.

---

### 6.6 AgentStopReason

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Adds a machine-readable stop reason for `on_deny="abort"`.

#### Interface / API

```python
class AgentStopReason(str, Enum):
    ...
    TOOL_SETTINGS_DENIED = "tool_settings_denied"
```

#### Logic / Algorithm

1. Add the enum member so an abort-on-deny stop is not mislabeled `MIDDLEWARE_ABORT`.

#### Edge Cases & Error Handling

- Existing consumers switch on known members; a new member is additive.

---

### 6.7 Public Exports

**File(s):** `vidbyte/agents/settings/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes `ToolSettings` discoverable through the existing public import surfaces.

#### Logic / Algorithm

1. Export `ToolSettings` from `vidbyte.agents.settings`.
2. Re-export from `vidbyte.agents`.
3. Re-export from root `vidbyte`, importing from `vidbyte.agents.settings` (not from any middleware module).

#### Edge Cases & Error Handling

- Root exports avoid import cycles by importing only from `agents.settings`.

---

### 6.8 Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents the universal tool settings surface and its runtime-level enforcement.

#### Logic / Algorithm

1. Show `AgentLoopSettings(tool_settings=ToolSettings(denied_tools={...}, max_calls=..., max_calls_per_tool={...}, result_max_chars=..., on_deny=...))`.
2. Explain `denied_tools` documents team policy and blocks dynamically attached tools by name; internal runtime tools are never blocked.
3. Explain raw tool results remain in runtime metadata while model-visible results may be truncated.
4. Note that enforcement is runtime-level (not middleware) and that `on_deny` chooses continue-in-context vs. stop-the-run.

#### Edge Cases & Error Handling

- Must not imply `ToolSettings` replaces `PermissionPolicy`.

---

## 7. Data Model Changes

### 7.1 `ToolSettings`

**Change type:** New

```python
class ToolSettings:
    denied_tools: frozenset[str]
    max_calls: int | None
    max_calls_per_tool: dict[str, int]
    result_max_chars: int | None
    on_deny: str  # "continue" | "abort"
```

**Migration strategy:** N/A — in-memory Python SDK settings object.

- Forward: add class, wire through `AgentLoopSettings` and `AgentRuntimeConfig`.
- Rollback: remove class and the `tool_settings` fields/enforcement.

### 7.2 `AgentRuntimeConfig.tool_settings`

**Change type:** Modified (new optional field, default `None`).

### 7.3 `AgentStopReason.TOOL_SETTINGS_DENIED`

**Change type:** Modified (new enum member).

---

## 8. API Changes

N/A — no HTTP endpoints. Python SDK surface only:

```python
from vidbyte import Agent, AgentLoopSettings, ToolSettings

agent = Agent(
    name="repo-worker",
    system_prompt="Use tools carefully.",
    runner=my_runner,
    tools=[...],
    agent_loop_settings=AgentLoopSettings(
        tool_settings=ToolSettings(
            denied_tools={"delete_file"},
            max_calls=20,
            max_calls_per_tool={"search": 5},
            result_max_chars=8000,
            on_deny="continue",
        ),
    ),
)
```

| Result surface | Meaning |
|----------------|---------|
| `reply.metadata["stop_reason"] == "tool_settings_denied"` | An `on_deny="abort"` denial stopped the run. |
| `reply.metadata["stop_reason"] == "max_tool_calls"` | `max_calls` total budget stopped the run. |
| `ToolCallContext.state == DENIED` | A `denied_tools` / per-tool-over-limit call that was blocked (continue mode). |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/tool-settings-runtime-enforcement.md` | This design doc |
| CREATE | `vidbyte/agents/settings/tool.py` | New `ToolSettings` class with pure decision methods |
| MODIFY | `vidbyte/agents/settings/loop.py` | Add `tool_settings`; reconcile `max_calls`; pass through to runtime config |
| MODIFY | `vidbyte/agents/settings/__init__.py` | Export `ToolSettings` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentRuntimeConfig.tool_settings`; add `AgentStopReason.TOOL_SETTINGS_DENIED` |
| MODIFY | `vidbyte/agents/runtime.py` | Inline enforcement in `_process_tool_call`; generalize denied-result helper; add `_executed_counts` |
| MODIFY | `vidbyte/agents/base.py` | Reject `tool_settings` on non-linear runtimes |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export `ToolSettings` |
| MODIFY | `vidbyte/__init__.py` | Root export for `ToolSettings` |
| MODIFY | `README.md` | Document runtime-level tool settings |

No middleware files are created or modified.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | dataclasses, collections ABCs, string slicing, enum | Existing runtime only |
| `vidbyte.lib.errors.ConfigurationError` | internal | Settings validation errors | Low — already used by settings |
| `vidbyte.lib.dataclasses.tools` | internal | `ToolResult`, `ToolCallState` | Low — existing types |

No new package dependencies or external services.

---

## 11. Rollout & Deployment

- Package-only SDK change; no feature flag; opt-in via `AgentLoopSettings(tool_settings=...)`.
- Existing `max_tool_calls` remains supported.
- Supersedes PR #249 (middleware approach). PR #249 should be closed after this merges; no code from it is reused.
- Rollout after approval:
  1. Create a worktree from `origin/main`.
  2. Commit this design doc first.
  3. Add `ToolSettings`.
  4. Add `AgentRuntimeConfig.tool_settings` and `AgentStopReason.TOOL_SETTINGS_DENIED`.
  5. Wire `AgentLoopSettings.to_runtime_config()`.
  6. Add runtime enforcement in `AgentRuntime`.
  7. Add the `BaseAgent` non-linear guard.
  8. Add exports; update README.
  9. Run import/compile verification.
  10. Push branch and open a draft PR.
- Rollback: revert the branch merge; remove new files and the added fields/enforcement.

---

## 12. Open Questions

- [ ] Base branch: build fresh off `origin/main` (recommended, fully supersedes PR #249) vs. stack on `feat/tool-settings-enforcement`. This doc assumes fresh off `origin/main`.
- [ ] Should `on_deny` be a single global knob (this design) or per-constraint (e.g. a `{name: "continue"|"abort"}` mapping on `denied_tools`)? Recommendation: ship the single global knob; evolve only if a concrete case needs mixed behavior.
- [ ] Should the same-iteration total-budget guard also apply to legacy `max_tool_calls` (without `tool_settings`)? This design keeps legacy semantics unchanged and only guards mid-iteration when `tool_settings.max_calls` is set.

---

## 13. Alternatives Considered

### Alternative 1: Keep the PR #249 middleware approach

- What: Enforce via an auto-registered `ToolSettingsMiddleware`.
- Why rejected: Creates a second enforcement model beside the runtime-native budgets. The user's decision is to unify on runtime-level enforcement so `tool_settings` behaves exactly like `max_iterations`/`max_tokens`/`max_tool_calls`.

### Alternative 2: Store per-run counters on the ToolSettings instance

- What: Track `calls_by_tool` on `ToolSettings`.
- Why rejected: `ToolSettings` is a shared config object reused across concurrent runs of one agent; mutable per-run state on it is a concurrency bug. Counts are derived from the run-local `call_contexts` instead.

### Alternative 3: Add a new mutable run-state structure in the runtime

- What: Maintain a dedicated `dict[str,int]` threaded through `_process_tool_call`.
- Why rejected: `call_contexts` already records every call with its `state`; deriving counts avoids new plumbing and cannot drift from the recorded truth.

### Alternative 4: Flat fields on AgentLoopSettings

- What: Put `denied_tools`/`max_calls`/... directly on `AgentLoopSettings`.
- Why rejected: These are tool-use concerns; a nested `ToolSettings` keeps the loop-settings constructor focused and leaves room for future universal tool settings.
```