# Design Doc: Tool Settings Guardrail Budgets

**Status:** Draft  
**Author:** Claude  
**Created:** 2026-07-08  
**Last Updated:** 2026-07-08  

---

## 1. Overview

This feature extends the existing `ToolSettings` object and direct `AgentRuntime` enforcement path with six additional universal tool-use guardrails: per-iteration call caps, identical-call thrash limits, consecutive and total failure budgets, per-tool-call timeouts, and a sliding-window call budget over the last K iterations. Budget-class limits hard-stop the run with dedicated `AgentStopReason` values (matching `max_calls` / `max_tool_calls` behavior). Timeouts convert hung tool executions into error results that feed failure budgets. Decision logic stays pure and stateless on `ToolSettings`; per-run counting and stop effects remain owned by `AgentRuntime`.

---

## 2. Goals & Non-Goals

### Goals

- Add six validated, opt-in fields on `ToolSettings` and enforce them in the linear/direct runtime.
- **Hard-stop all budget-class limits** (never soft-deny / continue-in-context for budgets).
- Keep `on_deny` behavior unchanged for existing deny-class settings (`denied_tools`, `max_calls_per_tool`).
- Preserve skill invariants: stateless settings, counts from run-local state / `call_contexts`, internal tools exempt, pre-exec before middleware.
- Tag tool-call contexts with iteration index so sliding-window and per-iteration budgets can be computed without storing counters on the shared settings object.
- Document the new surface in README and `skills/tool-settings/SKILL.md`.
- Ship as one cohesive PR (no tests required by this workflow).

### Non-Goals

- Middleware-based enforcement or reintroduction of `ToolSettingsMiddleware`.
- Enforcing `tool_settings` on non-linear runtimes (still construction-time reject).
- Soft-deny / skip-remainder behavior for the new budgets.
- Strategy injection or “force strategy change” beyond hard-stopping the run.
- Changing `ToolErrorPolicy` or `LoopDetectionMiddleware` APIs.
- Whole-run wall-clock timeout (`AgentLoopSettings.timeout_seconds` remains reserved / separate).
- Allowlist semantics or flattening fields onto `AgentLoopSettings`.
- Writing automated tests or verification scripts (explicitly out of scope for this skill).
- Guaranteeing hard cancellation of non-cooperative sync tool work after timeout.

---

## 3. Background & Context

### Why now

PR #259 introduced runtime-enforced `ToolSettings` (`denied_tools`, `max_calls`, `max_calls_per_tool`, `result_max_chars`, `on_deny`). PR #260 documented the contributor process in `skills/tool-settings/SKILL.md`. Production agent loops still thrash (identical calls), fan out too many tools per model turn, hang on tools, and burn runs on failure spirals. These six knobs close those gaps inside the same config surface.

### Current state

| Piece | Location |
|-------|----------|
| Settings + pure decisions | `vidbyte/agents/settings/tool.py` |
| Nesting / `to_runtime_config` | `vidbyte/agents/settings/loop.py` |
| Enforcement | `vidbyte/agents/runtime.py` (`_enforce_tool_settings`, `_process_tool_call`, `_execute_tool`) |
| Config / stop reasons | `vidbyte/lib/dataclasses/agents.py` |
| Process skill | `skills/tool-settings/SKILL.md` |

Existing budget pattern: `max_calls` → mid-iteration hard stop with `AgentStopReason.MAX_TOOL_CALLS`.  
Existing deny pattern: `denial()` → continue (inject DENIED) or abort via `on_deny`.

Related but separate systems:

- `LoopDetectionMiddleware` — consecutive identical tool+args abort (middleware opt-in).
- `ToolErrorPolicy.max_total_tool_errors` — middleware-owned total error abort with retries.

### Constraints

- Python 3.11+, async agent runtime.
- Style: single-line signatures, 1–2 line method comments, class-first helpers, `ConfigurationError` at construction.
- Skill process for adding fields must be followed.

### Locked decisions (from pre-implementation talk)

1. **Hard stop for budgets** (user-confirmed).
2. New budgets do **not** use `on_deny` soft continue.
3. Failures = `ToolCallState.FAILED` (timeouts count as failed); denials do not count as failures or consume executed budgets.
4. `max_identical_calls` = **total lifetime** fingerprint count (not consecutive).
5. Sliding window requires companion `sliding_window_iterations` (window size K).

---

## 4. Requirements

### Functional Requirements

1. `ToolSettings` accepts optional `max_calls_per_iteration: int | None = None` (≥ 1 when set). Before executing a non-internal tool, if the number of non-denied tool contexts already recorded for the **current iteration** is ≥ the limit, hard-stop with `stop_reason=max_calls_per_iteration`.
2. `ToolSettings` accepts optional `max_identical_calls: int | None = None` (≥ 1 when set). Fingerprint = stable hash of `tool_name` + JSON-serialized args (sorted keys). Before executing a non-internal tool, if prior **executed** (non-`DENIED`) contexts with the same fingerprint count ≥ N, hard-stop with `stop_reason=max_identical_calls`. The call about to run would be the (N+1)th; stop before executing it.
3. `ToolSettings` accepts optional `max_consecutive_failures: int | None = None` (≥ 1 when set). After a non-internal tool finishes in `FAILED` state, if the trailing streak of non-denied contexts that are `FAILED` (ignoring internal tools when counting streak) is ≥ N, hard-stop with `stop_reason=max_consecutive_failures`.
4. `ToolSettings` accepts optional `max_error_calls: int | None = None` (≥ 1 when set). After a non-internal tool finishes in `FAILED` state, if total non-denied `FAILED` contexts (non-internal) ≥ N, hard-stop with `stop_reason=max_error_calls`. Independent of success count and of `max_calls`.
5. `ToolSettings` accepts optional `tool_timeout_seconds: float | None = None` (> 0 when set). Each non-internal tool execution is wrapped in `asyncio.wait_for(..., timeout=...)`. On timeout, produce a `ToolResult.error` with metadata indicating timeout and record `ToolCallState.FAILED`. That failure counts toward `max_error_calls` and `max_consecutive_failures`. Internal tools are not timed out by this setting.
6. `ToolSettings` accepts optional `sliding_window_max_calls: int | None = None` and `sliding_window_iterations: int | None = None`. Both must be set together (or both null); each ≥ 1 when set. Before executing a non-internal tool, count non-denied tool contexts whose recorded `iteration_count` is in `[current_iteration - K + 1, current_iteration]` (inclusive). If that count ≥ `sliding_window_max_calls`, hard-stop with `stop_reason=sliding_window_max_calls`.
7. Every new integer/float field raises `ConfigurationError` with a clear field name when invalid (type, zero, negative, unpaired sliding-window fields).
8. Internal tools (`isDone` and tools with `metadata["internal"]`) are never blocked, timed out, or counted by the new budgets.
9. When `tool_settings is None`, runtime behavior is unchanged.
10. Existing fields (`denied_tools`, `max_calls`, `max_calls_per_tool`, `result_max_chars`, `on_deny`) keep current semantics.
11. New stop reasons are added to `AgentStopReason` for each hard-stop budget (not overloaded onto `TOOL_SETTINGS_DENIED` or `MIDDLEWARE_ABORT`).
12. `ToolCallContext` records the iteration index when the call is appended so window/per-iteration counts are reconstructable from `call_contexts` alone where possible; runtime may also pass live counters into pure decision helpers.
13. Public imports of `ToolSettings` remain valid; no new public types required unless a small helper is needed (prefer methods on `ToolSettings`).
14. README and `skills/tool-settings/SKILL.md` field tables document the new settings and hard-stop semantics.

### Non-Functional Requirements

- **Performance:** Fingerprint and window scans are O(n) over call_contexts per tool call; n is bounded by existing `max_calls` / loop budgets. Acceptable for agent loops.
- **Concurrency:** No per-run mutable state on the shared `ToolSettings` instance. Concurrent runs of one agent remain safe.
- **Security:** No new trust boundaries; timeouts only limit hung work best-effort.
- **Observability:** Stop messages and result metadata include limit values and current counts; timeouts mark `metadata["error"] = "timeout"` (or equivalent).
- **Reliability:** Timeout yields a model-visible error result and continues the loop unless a failure budget then hard-stops.
- **Backward compatibility:** Opt-in only; no breaking change for agents without the new fields.

---

## 5. High-Level Design

Extend `ToolSettings` with the six (plus window companion) fields. Keep pure decision helpers on the class:

- Budget predicates that return `(stop_reason_key, metadata) | None` given run-local snapshots (counts, fingerprints, failure streak, iteration-tagged contexts).
- No mutation of settings state.

Expand `_enforce_tool_settings` (pre-exec) to evaluate **hard-stop budgets** before existing `denial()`:

1. `max_calls` (existing)
2. `max_calls_per_iteration`
3. `sliding_window_max_calls`
4. `max_identical_calls`
5. then existing `denial()` for deny-class rules

Post-exec path in `_process_tool_call` (after tool result is final, context appended) checks:

1. `max_consecutive_failures`
2. `max_error_calls`

Timeout is applied inside `execute_tool_call` / `_execute_tool` via `asyncio.wait_for`.

```
AgentLoopSettings(tool_settings=ToolSettings(...new fields...))
        |
        v
to_runtime_config()  ->  AgentRuntimeConfig(tool_settings=...)
        |
        v
AgentRuntime._process_tool_call
        |
        +--> _enforce_tool_settings          # pre-exec hard budgets + denial
        |       max_calls
        |       max_calls_per_iteration
        |       sliding_window_max_calls
        |       max_identical_calls
        |       denial()  # denied_tools / max_calls_per_tool + on_deny
        |
        +--> middleware + execute_tool_call
        |       asyncio.wait_for if tool_timeout_seconds
        |
        +--> append context (with iteration_count)
        +--> _enforce_tool_settings_after_failure  # consecutive / total errors
        +--> append model-visible message / truncate
```

**Key decisions:**

| Decision | Choice | Why |
|----------|--------|-----|
| Budget effect | Hard stop only | User-locked; matches `max_calls` |
| Identical semantics | Total fingerprint count | Differentiates from consecutive middleware |
| Failure definition | `FAILED` only | Denials are policy, not thrash |
| Sliding window K | Required companion field | Incomplete otherwise |
| Timeout ownership | ToolSettings + runtime wrap | Universal per-call, no middleware |
| Iteration tagging | Store on `ToolCallContext.metadata` or dedicated field | Prefer dedicated `iteration_count: int | None = None` on context for clarity |

---

## 6. Detailed Design

### 6.1 ToolSettings (fields + pure decisions)

**File(s):** `vidbyte/agents/settings/tool.py`  
**Type:** Modified

#### What it does

Owns validated configuration and pure predicates for the new budgets/timeout.

#### Interface / API

```python
class ToolSettings:
    def __init__(
        self,
        *,
        denied_tools: Iterable[str] = (),
        max_calls: int | None = None,
        max_calls_per_tool: Mapping[str, int] | None = None,
        result_max_chars: int | None = None,
        on_deny: str = "continue",
        max_calls_per_iteration: int | None = None,
        max_identical_calls: int | None = None,
        max_consecutive_failures: int | None = None,
        max_error_calls: int | None = None,
        tool_timeout_seconds: float | None = None,
        sliding_window_max_calls: int | None = None,
        sliding_window_iterations: int | None = None,
    ) -> None: ...

    def denial(self, tool_name: str, executed_counts: Mapping[str, int]) -> tuple[str, dict] | None: ...
    def truncate(self, result: ToolResult) -> ToolResult: ...

    def fingerprint(self, tool_name: str, arguments: Mapping[str, object] | None) -> str:
        # Stable tool+args fingerprint for identical-call budgets.

    def budget_stop(self, *, tool_name: str, arguments: Mapping[str, object] | None, call_contexts: Sequence[ToolCallContext], iteration_count: int) -> tuple[str, dict] | None:
        # Returns (reason, metadata) when a pre-exec hard budget is exceeded; else None.
        # Checks: max_calls_per_iteration, sliding_window, max_identical_calls.
        # Does NOT re-check max_calls (runtime already maps that to MAX_TOOL_CALLS).

    def failure_budget_stop(self, call_contexts: Sequence[ToolCallContext]) -> tuple[str, dict] | None:
        # Returns (reason, metadata) when consecutive or total failure budgets are exceeded after a failure.
```

Note: Constructor signature may stay multi-kw in spirit of existing code; **new methods** follow single-line signature style required by this workflow.

#### Logic / Algorithm

**Validation (`_validate` / helpers):**

- Integers ≥ 1 when present: `max_calls_per_iteration`, `max_identical_calls`, `max_consecutive_failures`, `max_error_calls`, `sliding_window_max_calls`, `sliding_window_iterations`.
- `tool_timeout_seconds` must be `int` or `float` (not bool), and `> 0` when present.
- Sliding window: if one of `(sliding_window_max_calls, sliding_window_iterations)` is set, the other must be set; else `ConfigurationError`.

**`fingerprint`:**

1. `json.dumps(arguments or {}, sort_keys=True, default=str)` (fallback `str(arguments)` on error).
2. SHA-256 hex digest truncated to 16 chars (match loop_detection style).
3. Return `f"{tool_name}:{digest}"`.

**`budget_stop` (order):**

1. **Per-iteration:** count non-denied, non-internal contexts with `iteration_count == current`. If `>= max_calls_per_iteration` → `("max_calls_per_iteration", meta)`.
2. **Sliding window:** let `lo = max(1, current - K + 1)`. Count non-denied, non-internal contexts with `iteration_count` in `[lo, current]`. If `>= sliding_window_max_calls` → `("sliding_window_max_calls", meta)`.
3. **Identical:** count non-denied, non-internal contexts whose fingerprint equals candidate fingerprint. If `>= max_identical_calls` → `("max_identical_calls", meta)`.

Internal classification for pure methods: contexts with `metadata.get("internal") is True` or tool name `isDone` are skipped. Runtime should stamp `metadata["internal"]=True` on internal contexts when recording, **or** pass a helper that only includes non-internal contexts. Prefer runtime filtering before calling pure methods so ToolSettings does not need the tools catalog.

**Simpler approach (preferred):** Runtime only invokes budget checks for non-internal tools, and pure methods only count contexts that are not `DENIED`. For iteration tagging, runtime stamps every context with `iteration_count`. Internal tool contexts that slip into counts: still skipped by runtime never calling budget_stop for them; counts of internal tools in history could inflate windows if we don't filter them. Therefore pure methods must skip contexts whose `metadata.get("internal")` is true, and runtime must set that flag when building contexts for internal tools.

**`failure_budget_stop`:**

1. Walk contexts reverse, skip DENIED and internal; count trailing `FAILED` streak. If ≥ `max_consecutive_failures` → stop.
2. Count total non-denied non-internal `FAILED`. If ≥ `max_error_calls` → stop.
3. If both trip, prefer **consecutive** reason first if streak tripped, else total (document order: consecutive then total).

#### Edge Cases & Error Handling

- Blank / wrong types → `ConfigurationError` at construction.
- `max_identical_calls=1` means the second identical call stops (first succeeds).
- Empty args fingerprint still stable.
- Unpaired sliding window fields → construction error.
- Pure methods return `None` when the corresponding setting is unset.

---

### 6.2 ToolCallContext iteration tagging

**File(s):** `vidbyte/lib/dataclasses/tools.py`  
**Type:** Modified

#### What it does

Adds optional `iteration_count: int | None = None` so window/per-iteration budgets can scan history.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ToolCallContext:
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    state: ToolCallState = ToolCallState.REQUESTED
    call_id: str | None = None
    result: ToolResult | None = None
    provider: str | None = None
    model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    iteration_count: int | None = None  # NEW
```

#### Logic / Algorithm

1. Add field with default `None` for backward compatibility.
2. All sites that construct `ToolCallContext` in `AgentRuntime` pass `iteration_count=iteration_count` when available.
3. For denied contexts in tool settings path, same.

#### Edge Cases

- Contexts without iteration_count are ignored by sliding/per-iteration counters (defensive).

---

### 6.3 AgentStopReason

**File(s):** `vidbyte/lib/dataclasses/agents.py`  
**Type:** Modified

#### What it does

Adds dedicated stop reasons for each hard budget.

#### Interface / API

```python
class AgentStopReason(str, Enum):
    ...
    MAX_CALLS_PER_ITERATION = "max_calls_per_iteration"
    MAX_IDENTICAL_CALLS = "max_identical_calls"
    MAX_CONSECUTIVE_FAILURES = "max_consecutive_failures"
    MAX_ERROR_CALLS = "max_error_calls"
    SLIDING_WINDOW_MAX_CALLS = "sliding_window_max_calls"
```

(No new reason for timeout alone — timeout is a tool error, not a run stop, unless a failure budget then stops.)

#### Mapping from pure reason string → enum

| reason string | AgentStopReason |
|---------------|-----------------|
| `max_calls_per_iteration` | `MAX_CALLS_PER_ITERATION` |
| `max_identical_calls` | `MAX_IDENTICAL_CALLS` |
| `max_consecutive_failures` | `MAX_CONSECUTIVE_FAILURES` |
| `max_error_calls` | `MAX_ERROR_CALLS` |
| `sliding_window_max_calls` | `SLIDING_WINDOW_MAX_CALLS` |

---

### 6.4 AgentRuntime enforcement

**File(s):** `vidbyte/agents/runtime.py`  
**Type:** Modified

#### What it does

Wires pre-exec budgets, timeout, iteration tagging, and post-failure budgets.

#### Interface / API (helpers)

```python
def _enforce_tool_settings(...) -> tuple[ToolCallContext, ToolResult] | AgentResult | None:
    # Pre-exec: max_calls, ToolSettings.budget_stop, denial/on_deny.

def _tool_settings_hard_budget_stop(settings, reason, meta, *, iteration_count, tokens_used, contexts) -> AgentResult:
    # Maps reason string to AgentStopReason and returns _stopped_result.

def _enforce_tool_settings_after_failure(settings, call_contexts, *, iteration_count, tokens_used) -> AgentResult | None:
    # Post-exec failure budgets.

async def _execute_tool(self, tool, call) -> ToolResult:
    # Wraps execute with wait_for when tool_timeout_seconds set and tool not internal.
```

#### Logic / Algorithm

**Pre-exec (`_enforce_tool_settings`):**

1. If no settings or internal → `None`.
2. Existing `_tool_settings_budget_stop` for `max_calls`.
3. Call `settings.budget_stop(tool_name=..., arguments=call.arguments, call_contexts=call_contexts, iteration_count=iteration_count)`.
4. If not None → hard stop via mapped `AgentStopReason`.
5. Existing `denial()` + `_apply_tool_denial`.

**Context construction:** every `ToolCallContext(...)` built in runtime for this run path includes `iteration_count=iteration_count`. When building internal tool contexts, set `metadata` to include `internal: True` if not already present.

**Timeout (`_execute_tool` or `execute_tool_call`):**

1. If settings has `tool_timeout_seconds` and call is not internal:
   ```python
   try:
       return await asyncio.wait_for(tool.execute(call), timeout=settings.tool_timeout_seconds)
   except asyncio.TimeoutError as exc:
       raise ToolExecutionError(
           f"Tool '{call.tool_name}' timed out after {settings.tool_timeout_seconds}s",
           details={"tool_name": call.tool_name, "error_type": "timeout", "error": "timeout"},
       ) from exc
   ```
2. Existing exception handlers convert this to `FAILED` + error result. Ensure metadata includes `"error": "timeout"`.

**Post-exec:** After `call_contexts.append(context_record)` and before/after abort middleware checks, if result state is `FAILED` (or context.state is FAILED) and not internal:

```python
stop = self._enforce_tool_settings_after_failure(settings, call_contexts, ...)
if stop is not None:
    return stop  # AgentResult
```

Still append the failure tool message to the model if the run stops? **Yes for consistency with mid-iteration max_tool_calls after prior tools** — the failed call already completed; stop before further tools. Order:

1. append context  
2. if failure budgets → return stopped result (but tool result message for this failure should already be appended so the partial transcript is coherent)  
3. else continue  

Implementation order inside `_process_tool_call` after the retry loop:

1. `call_contexts.append(context_record)`
2. middleware abort check
3. append tool result message (non-isDone)
4. if not internal and settings and state FAILED: failure budget stop → return AgentResult
5. return context_record, result

#### Edge Cases

- Multi-tool model turn: pre-exec stops remaining tools; earlier tools stay in context.
- Timeout during middleware retry: each attempt is subject to the same timeout; retries still possible via middleware until final failure is recorded once.
- `isDone` never timed out / never counted.
- Concurrent runs: safe (no settings mutation).

---

### 6.5 Documentation & skills

**File(s):**  
- `README.md`  
- `skills/tool-settings/SKILL.md`  
- `skills/agentic-loop-settings/SKILL.md` (stop reasons pointer only if present)  

**Type:** Modified

#### What it does

Documents new fields, hard-stop semantics, timeout failure coupling, and sliding-window companion field.

#### Content updates

- Field table rows for each new setting.
- Note: budgets hard-stop; `on_deny` does not apply to them.
- Example snippet extended with one or two new fields.
- Skill process section unchanged in structure; field table updated.

---

### 6.6 AgentLoopSettings / exports / base

**File(s):**  
- `vidbyte/agents/settings/loop.py` — only if repr or validation needs updates (no flatten).  
- `vidbyte/agents/base.py` — no change expected (already rejects tool_settings on non-linear).  
- Exports — no new types.

**Type:** Modified only if needed for `__repr__` of nested tool_settings (automatic via ToolSettings.__repr__).

---

## 7. Data Model Changes

### 7.1 ToolSettings fields

**Change type:** Modified (class attributes)

```python
max_calls_per_iteration: int | None
max_identical_calls: int | None
max_consecutive_failures: int | None
max_error_calls: int | None
tool_timeout_seconds: float | None
sliding_window_max_calls: int | None
sliding_window_iterations: int | None
```

**Migration strategy:** Opt-in defaults `None`. No migration. Rollback: unset fields / revert PR.

### 7.2 ToolCallContext.iteration_count

**Change type:** Modified

```python
iteration_count: int | None = None
```

**Migration strategy:** Default `None` preserves frozen dataclass compatibility for external constructors. Rollback: remove field.

### 7.3 AgentStopReason members

**Change type:** Modified (enum extension)

```python
MAX_CALLS_PER_ITERATION = "max_calls_per_iteration"
MAX_IDENTICAL_CALLS = "max_identical_calls"
MAX_CONSECUTIVE_FAILURES = "max_consecutive_failures"
MAX_ERROR_CALLS = "max_error_calls"
SLIDING_WINDOW_MAX_CALLS = "sliding_window_max_calls"
```

**Migration strategy:** Additive enum values only. Rollback: remove members (callers must not depend yet).

---

## 8. API Changes

N/A — no HTTP endpoints. Public Python constructor API for `ToolSettings` gains optional keyword-only parameters listed in §6.1. `AgentResult.metadata["stop_reason"]` may contain the new string values.

### Developer-facing usage

```python
from vidbyte.agents import AgentLoopSettings, ToolSettings

settings = AgentLoopSettings(
    tool_settings=ToolSettings(
        max_calls=50,
        max_calls_per_iteration=4,
        max_identical_calls=3,
        max_consecutive_failures=5,
        max_error_calls=20,
        tool_timeout_seconds=30.0,
        sliding_window_max_calls=10,
        sliding_window_iterations=3,
        on_deny="continue",  # still only for denied_tools / max_calls_per_tool
    ),
)
```

**Error cases (construction):**

| Condition | Error |
|-----------|--------|
| Invalid int / float | `ConfigurationError` |
| Unpaired sliding window fields | `ConfigurationError` |
| `tool_timeout_seconds <= 0` | `ConfigurationError` |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/tool-settings-guardrail-budgets.md` | This design doc |
| MODIFY | `vidbyte/agents/settings/tool.py` | New fields, validation, pure budget/fingerprint helpers, repr |
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | `ToolCallContext.iteration_count` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | New `AgentStopReason` members |
| MODIFY | `vidbyte/agents/runtime.py` | Pre-exec budgets, timeout wrap, iteration tag, post-failure stops |
| MODIFY | `README.md` | Document new ToolSettings fields and hard-stop behavior |
| MODIFY | `skills/tool-settings/SKILL.md` | Field table + stop reasons + process notes |
| MODIFY | `skills/agentic-loop-settings/SKILL.md` | Stop-reason list if it documents tool_settings stops |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio` (stdlib) | Python 3.11+ | `wait_for` for tool timeouts | Low — cooperative cancel only |
| Existing `hashlib` / `json` | stdlib | Fingerprints | Low |

No new third-party packages.

---

## 11. Rollout & Deployment

- **Feature flags:** None. Opt-in via constructor fields.
- **Breaking change:** No. Additive API only. `ToolCallContext` gains optional field with default.
- **Deployment order:** Single library PR to `main`.
- **Rollback:** Revert PR; agents without new fields never exercise the path.
- **Overlap note:** If both `ToolSettings.max_error_calls` and `ToolErrorPolicy.max_total_tool_errors` are set, either may stop the run first depending on middleware ordering vs post-exec checks; document coexistence without coupling.

---

## 12. Open Questions

Resolved for this design (locked):

- [x] Hard stop for budgets — **yes**.
- [x] Identical = total fingerprint count — **yes**.
- [x] Sliding window companion field — **`sliding_window_iterations`**.
- [x] Failures = `FAILED` only — **yes**.
- [x] Timeout counts toward failure budgets — **yes**.

Remaining (non-blocking; defaults chosen):

- [x] Internal tool exclusion in pure counters — **skip `metadata["internal"]` and `isDone`**.
- [x] Both consecutive + total fire — **prefer consecutive reason if streak ≥ limit, else total**.

---

## 13. Alternatives Considered

### Alternative 1: Soft-deny remainder of iteration for `max_calls_per_iteration`

- **What:** Inject DENIED results for leftover tools via `on_deny`.
- **Why rejected:** User locked hard-stop for budgets; matches `max_calls` simplicity.

### Alternative 2: Put error budgets only on `ToolErrorPolicy`

- **What:** Extend middleware-only error policy instead of ToolSettings.
- **Why rejected:** User asked for ToolSettings knobs; runtime-native budgets work without middleware composition.

### Alternative 3: Consecutive-only `max_identical_calls` (like LoopDetectionMiddleware)

- **What:** Only trailing streak of identical fingerprints.
- **Why rejected:** Would duplicate middleware; total count is the clearer ToolSettings differentiator. Middleware remains available for consecutive loops.

### Alternative 4: Store counters on ToolSettings instance

- **What:** Mutable per-run counters on settings.
- **Why rejected:** Skill invariant / concurrent run corruption.

### Alternative 5: Tag iteration only in a runtime-side list, not on ToolCallContext

- **What:** Keep `list[int]` of counts per iteration in runtime local vars.
- **Why rejected:** Context tagging is inspectable in result metadata and keeps pure methods testable with contexts alone. Slightly better observability.

### Alternative 6: Hard-kill tool threads on timeout

- **What:** Run tools in threads and kill on deadline.
- **Why rejected:** Unsafe in Python; not used elsewhere in SDK. Best-effort `wait_for` + ERROR result is enough for v1.

---

## Implementation Notes (for Phase 4)

Commit order:

1. Design doc only.
2. Data model: `AgentStopReason` + `ToolCallContext.iteration_count`.
3. `ToolSettings` fields + pure methods + validation + repr.
4. Runtime enforcement (pre-exec, timeout, post-failure, iteration tagging).
5. Docs/skills.

Code style (mandatory for this workflow):

- Prefer helper methods on `ToolSettings` / `AgentRuntime` over large inlined blocks.
- Single-line method signatures where practical (match surrounding file density for long existing methods).
- 1–2 line comment under every new function/method.
- `ConfigurationError` for config; no bare `ValueError` for ToolSettings fields.
