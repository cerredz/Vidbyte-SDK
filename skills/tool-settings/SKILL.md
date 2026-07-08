---
name: tool-settings
description: >-
  Explains ToolSettings and the process for adding new universal tool-use
  constraints enforced in the direct agent runtime. Use when adding fields to
  ToolSettings, wiring tool policy into AgentRuntime, or reviewing tool-settings PRs.
---

<!-- Context Protocol Header
Description:
    Process guide for creating and extending ToolSettings in the Vidbyte SDK.
Purpose:
    Teaches contributors how ToolSettings is wired (settings → runtime config →
    AgentRuntime enforcement) and the checklist for adding a new constraint.
Architecture:
    SDK Skill Guide (contributor process).
Relations:
    Located in skills/tool-settings/SKILL.md.
    Implementation: vidbyte/agents/settings/tool.py, loop.py, runtime.py, base.py.
    Design: docs/design/tool-settings-runtime-enforcement.md.
Similar Files:
    - skills/agentic-loop-settings/SKILL.md
    - skills/mcp-server/add-tool.md
    - skills/vidbyte-sdk/adding-context-window-algorithms.md
    - skills/sdk/update-skill-files.md
-->

# Tool Settings Skill Guide

Use this skill when you need to **create, extend, or review** universal tool-use
settings (`ToolSettings`) in the Vidbyte SDK. It is a **contributor process
guide** distilled from PR #259 (runtime enforcement). It is not middleware and
it is not `PermissionPolicy`.

Related:

- Loop budgets catalog: `skills/agentic-loop-settings/SKILL.md`
- Architecture design: `docs/design/tool-settings-runtime-enforcement.md`
- Skill update matrix: `skills/sdk/update-skill-files.md`

---

## 1. When to Use This Skill

**Use it when:**

- Adding a new field to `ToolSettings`
- Changing denial / abort / truncation semantics
- Wiring new pre-exec or post-exec enforcement in `AgentRuntime`
- Reviewing a PR that touches tool settings

**Do not use it for:**

| Concern | Put it here instead |
|---------|---------------------|
| Loop budgets (`max_iterations`, `max_tokens`, legacy `max_tool_calls`) | Flat `AgentLoopSettings` fields — see `skills/agentic-loop-settings/SKILL.md` |
| Tool *error* retry / backoff / render | `ToolErrorPolicy` + middleware |
| Capability / security gates | `PermissionPolicy` / security middleware |
| Per-hook transforms or run mutation | Middleware |

---

## 2. Mental Model

`ToolSettings` is a nested, developer-facing config object on
`AgentLoopSettings`. It owns **pure decision logic**. The **direct**
`AgentRuntime` owns per-run counting and applies effects inline — the same model
as loop budgets (`max_iterations`, `max_tokens`, `max_tool_calls`). There is no
`ToolSettingsMiddleware`.

```
AgentLoopSettings(tool_settings=ToolSettings(...))
        |
        v
to_runtime_config()
        |
        v
AgentRuntimeConfig(max_tool_calls=..., tool_settings=...)
        |
        v
BaseAgent  --non-linear + tool_settings?--> ConfigurationError
        |
        v
AgentRuntime._process_tool_call
        |
        +--> _enforce_tool_settings          # BEFORE middleware / execute
        |       max_calls mid-iteration stop
        |       budget_stop() hard budgets
        |       denial() -> continue | abort
        |
        +--> middleware + execute_tool_call
        |       asyncio.wait_for if tool_timeout_seconds
        |
        +--> append context (iteration_count tagged)
        +--> failure_budget_stop() after FAILED tools
        +--> _append_tool_result_message
                _truncate_for_tool_settings  # model-visible only
```

### Ownership split

| Concern | Owner |
|---------|--------|
| Policy values + pure decisions (`denial`, `truncate`, `budget_stop`, `failure_budget_stop`, `fingerprint`) | `ToolSettings` |
| Per-run executed counts / iteration tags | `AgentRuntime` via `call_contexts` |
| Inject denial into model context | `AgentRuntime._denied_tool_result` + message append |
| Stop the run | `AgentRuntime._stopped_result` |
| Truncate model-visible tool output | `ToolSettings.truncate` called from runtime post-exec path |
| Per-call timeout | `AgentRuntime._run_tool_execute` reading `tool_timeout_seconds` |

**Concurrency rule:** Never store per-run counters on the shared `ToolSettings`
instance. Multiple concurrent runs of one agent share the same settings object.

---

## 3. Existing Settings Surface

| Field | Type | Default | Runtime effect |
|-------|------|---------|----------------|
| `denied_tools` | `Iterable[str]` → `frozenset[str]` | `()` | Pre-exec: name denied; model sees denied result (`on_deny="continue"`) or run stops (`abort`) |
| `max_calls` | `int \| None` | `None` | Maps into `AgentRuntimeConfig.max_tool_calls`; mid-iteration guard **hard-stops** before over-budget call with `stop_reason=max_tool_calls` |
| `max_calls_per_tool` | `Mapping[str, int] \| None` → `dict[str, int]` | `{}` | Pre-exec: over limit → same deny/abort path as `denied_tools` |
| `max_calls_per_iteration` | `int \| None` | `None` | Pre-exec **hard-stop** when non-denied non-internal calls already recorded for the current iteration ≥ limit (`stop_reason=max_calls_per_iteration`) |
| `max_identical_calls` | `int \| None` | `None` | Pre-exec **hard-stop** when the same tool+args fingerprint already appears ≥ N times across the run (`stop_reason=max_identical_calls`) |
| `max_consecutive_failures` | `int \| None` | `None` | Post-exec **hard-stop** after a trailing streak of `FAILED` (non-denied, non-internal) contexts ≥ N (`stop_reason=max_consecutive_failures`) |
| `max_error_calls` | `int \| None` | `None` | Post-exec **hard-stop** when total `FAILED` (non-denied, non-internal) contexts ≥ N (`stop_reason=max_error_calls`) |
| `tool_timeout_seconds` | `float \| None` | `None` | Per non-internal tool call: `asyncio.wait_for`; timeout → `FAILED` with `metadata.error=timeout`; counts toward failure budgets |
| `sliding_window_max_calls` | `int \| None` | `None` | Pre-exec **hard-stop** when non-denied non-internal calls in the last K iterations ≥ limit (`stop_reason=sliding_window_max_calls`). Requires `sliding_window_iterations`. |
| `sliding_window_iterations` | `int \| None` | `None` | Window size K for `sliding_window_max_calls`. Must be set with it. |
| `result_max_chars` | `int \| None` | `None` | Post-exec: truncate **model-visible** output only; raw `ToolResult` in `ToolCallContext` unchanged; `0` is valid |
| `on_deny` | `"continue" \| "abort"` | `"continue"` | Global policy for **deny-class** decisions only (`denied_tools`, `max_calls_per_tool`). Does **not** soft-continue hard budgets. |

### Decision methods on `ToolSettings`

```python
def denial(self, tool_name: str, executed_counts: Mapping[str, int]) -> tuple[str, dict] | None:
    # Returns (reason, metadata) when blocked, else None. Pure and stateless.

def truncate(self, result: ToolResult) -> ToolResult:
    # Caps model-visible output; callers keep the raw ToolResult.

def fingerprint(self, tool_name: str, arguments: Mapping[str, object] | None) -> str:
    # Stable tool+args fingerprint for identical-call budgets.

def budget_stop(self, *, tool_name: str, arguments: Mapping[str, object] | None, call_contexts: Sequence[ToolCallContext], iteration_count: int) -> tuple[str, dict] | None:
    # Pre-exec hard budgets: per-iteration, sliding window, identical calls.

def failure_budget_stop(self, call_contexts: Sequence[ToolCallContext]) -> tuple[str, dict] | None:
    # Post-exec hard budgets: consecutive failures, then total errors.

@property
def aborts_on_deny(self) -> bool:
    # True when on_deny == "abort".
```

### Observable outcomes

| Surface | Meaning |
|---------|---------|
| `reply.metadata["stop_reason"] == "tool_settings_denied"` | `on_deny="abort"` stopped the run |
| `reply.metadata["stop_reason"] == "max_tool_calls"` | Total `max_calls` budget stopped the run |
| `reply.metadata["stop_reason"] == "max_calls_per_iteration"` | Per-iteration call budget hard-stop |
| `reply.metadata["stop_reason"] == "max_identical_calls"` | Identical tool+args thrash hard-stop |
| `reply.metadata["stop_reason"] == "max_consecutive_failures"` | Consecutive failure hard-stop |
| `reply.metadata["stop_reason"] == "max_error_calls"` | Run-wide failed-call hard-stop |
| `reply.metadata["stop_reason"] == "sliding_window_max_calls"` | Sliding-window call budget hard-stop |
| `ToolCallContext.state == DENIED` | Deny-and-continue; excluded from budget counts |
| `ToolCallContext.iteration_count` | Iteration tag used by per-iteration / sliding-window budgets |

### Usage (developer-facing)

```python
from vidbyte import Agent, ToolSettings
from vidbyte.agents import AgentLoopSettings, ToolSettings

agent = Agent(
    name="repo-worker",
    system_prompt="Use tools carefully.",
    runner=my_runner,
    tools=[search, delete_file],
    agent_loop_settings=AgentLoopSettings(
        tool_settings=ToolSettings(
            denied_tools={"delete_file"},
            max_calls=20,
            max_calls_per_tool={"search": 5},
            max_calls_per_iteration=4,
            max_identical_calls=3,
            max_consecutive_failures=5,
            max_error_calls=20,
            tool_timeout_seconds=30.0,
            sliding_window_max_calls=10,
            sliding_window_iterations=3,
            result_max_chars=8000,
            on_deny="continue",
        ),
    ),
)
```

Public imports:

```python
from vidbyte import ToolSettings
from vidbyte.agents import ToolSettings, AgentLoopSettings
from vidbyte.agents.settings import ToolSettings
```

---

## 4. Where Should My Constraint Live?

| Kind of constraint | Location |
|--------------------|----------|
| Universal deny / per-tool cap / result size bound on tool use | **`ToolSettings`** (this skill) |
| Iteration / token / legacy total tool-call budgets | Flat `AgentLoopSettings` fields |
| Retry / backoff / unrecoverable action on tool *failures* | `ToolErrorPolicy` (+ middleware) |
| Who may call which capability | `PermissionPolicy` / security middleware |
| One-off transforms at hooks | Middleware |

`ToolSettings` is **deny-oriented**, not an allowlist. It documents team policy
and blocks dynamically attached tools by name at call time. It complements
`PermissionPolicy`; it does not replace it.

---

## 5. Process: Add a New ToolSettings Field

Follow every step. Skipping exports or runtime wiring produces settings that
validate but do nothing.

### Step 1 — Define the field on `ToolSettings`

**File:** `vidbyte/agents/settings/tool.py`

1. Add a keyword-only constructor argument with a safe default (`None`, empty
   collection, or an explicit enum/string default).
2. Normalize collections:
   - Strip tool names
   - Reject `str` / `bytes` when an iterable of names is required
   - Prefer immutable storage (`frozenset`, plain validated `dict`)
3. Validate in `_validate()` / helpers. Raise **`ConfigurationError`**, not
   bare `ValueError`.
4. Prefer pure decision methods for policy (`denial`, `truncate`, or a new
   pure method). **Do not** mutate per-run counters on `self`.
5. Update `__repr__` so only active (non-default) fields appear.

### Step 2 — Nest / reconcile on `AgentLoopSettings`

**File:** `vidbyte/agents/settings/loop.py`

Only needed when the field interacts with loop-level budgets or needs type
validation beyond `ToolSettings` itself.

1. Keep `tool_settings: ToolSettings | None = None` nested (do not flatten new
   tool-use fields onto `AgentLoopSettings` unless there is a strong legacy
   reason).
2. `_validate_tool_settings()` must reject non-`ToolSettings` values.
3. If the field maps into an existing `AgentRuntimeConfig` budget (pattern:
   `max_calls` → `max_tool_calls`), map it in `to_runtime_config()` and reject
   mismatches when both are set to different values.
4. Include `tool_settings` in `__repr__` when set.

### Step 3 — Runtime config / stop reasons

**File:** `vidbyte/lib/dataclasses/agents.py`

1. Prefer carrying the **whole** `ToolSettings` object on
   `AgentRuntimeConfig.tool_settings` (already present). Avoid exploding every
   field onto the runtime config unless a budget must coexist with legacy
   fields (like `max_tool_calls`).
2. Add a new `AgentStopReason` member **only** when introducing a new stop
   outcome. Do not overload `MIDDLEWARE_ABORT` for tool-settings stops.
   Precedent: `AgentStopReason.TOOL_SETTINGS_DENIED = "tool_settings_denied"`.

### Step 4 — Enforce in `AgentRuntime`

**File:** `vidbyte/agents/runtime.py`

Choose the chokepoint by effect type:

| Effect type | Where | Helpers |
|-------------|-------|---------|
| Deny / hard-stop budgets before execution | Pre-exec in `_process_tool_call` via `_enforce_tool_settings` | `_tool_settings_budget_stop`, `settings.budget_stop`, `_tool_settings_hard_budget_stop`, `settings.denial`, `_apply_tool_denial` |
| Per-call timeout | During `execute_tool_call` / `_run_tool_execute` | `asyncio.wait_for`, `ToolExecutionError` with `error=timeout` |
| Failure budgets after a failed tool | Post-exec after context append | `settings.failure_budget_stop`, `_enforce_tool_settings_after_failure` |
| Transform model-visible tool output after execution | Post-exec message path | `_append_tool_result_message` → `_model_visible_tool_result` → `_truncate_for_tool_settings` |

Rules:

1. Run pre-exec tool-settings checks **before** middleware `before_tool_call`
   so settings cannot be skipped by middleware order.
2. Skip when `self.config.tool_settings is None` or `tool_is_internal` is true
   (`isDone` and tools marked `metadata["internal"]`).
3. **Deny-and-continue:** build denied context via `_denied_tool_result`, append
   to `call_contexts`, append model message with
   `_append_tool_result_message(..., truncate=False)` so denial text is never
   truncated by `result_max_chars`.
4. **Deny-and-abort:** `_stopped_result(..., stop_reason=AgentStopReason.TOOL_SETTINGS_DENIED)`.
5. **Total call budget mid-iteration:** stop before the over-budget call with
   `AgentStopReason.MAX_TOOL_CALLS` (see `_tool_settings_budget_stop`).
6. **Counts:** use `_executed_counts(call_contexts)` — executed means
   `state is not ToolCallState.DENIED`.
7. **Truncation-like transforms:** apply only to model-visible results; never
   mutate the raw `ToolResult` stored on `ToolCallContext`.

### Step 5 — Construction guards

**File:** `vidbyte/agents/base.py`

If the policy is only supported on the linear/direct runtime, reject
`tool_settings is not None` for non-linear runtimes
(`MCTS_SEARCH`, `ACTOR_MODEL`, `ACTOR_MODEL_P2P`, `ACTOR_MODEL_BROADCAST`) with
`ConfigurationError`. This guard already exists; extend messaging only if
needed.

### Step 6 — Public exports

| Module | Action |
|--------|--------|
| `vidbyte/agents/settings/__init__.py` | Export new public types if introduced |
| `vidbyte/agents/__init__.py` | Re-export |
| `vidbyte/__init__.py` | Root re-export when the symbol is part of the public SDK surface |

Keep import paths working:

```python
from vidbyte import ToolSettings
from vidbyte.agents import ToolSettings
from vidbyte.agents.settings import ToolSettings
```

### Step 7 — Documentation & skills

| File | When |
|------|------|
| `README.md` | Public behavior / example changes |
| `skills/tool-settings/SKILL.md` | This process guide (field table, steps, invariants) |
| `skills/agentic-loop-settings/SKILL.md` | Nested `tool_settings` pointer / stop reasons |
| `skills/sdk/update-skill-files.md` | Keep the "Add or Change Tool Settings" matrix accurate |
| `docs/design/<feature>.md` | Non-trivial architecture changes |
| `llms.txt` / usage skills | Only if the user-facing feature surface meaningfully grows |

---

## 6. Process: Add a New Decision or Effect

### Pre-execution (block or stop)

1. Add pure logic on `ToolSettings` that returns a decision (reason + metadata)
   or `None`.
2. Call it from `_enforce_tool_settings` (or a dedicated helper) with
   run-local inputs (`tool_name`, `_executed_counts(...)`, etc.).
3. Map decision → continue-deny or abort via `on_deny` / `aborts_on_deny`, or a
   new explicit policy field if mixed hard/soft behavior is required.

### Post-execution (transform visible output)

1. Add a pure transform on `ToolSettings` that returns a **new** `ToolResult`
   (or the same instance if unchanged).
2. Invoke it only on the model-visible path after middleware transforms.
3. Preserve raw runtime metadata for observability / debugging.

### New stop reasons

- New terminal stop → new `AgentStopReason` value.
- Continue-in-context denials do **not** need a stop reason; they use
  `ToolCallState.DENIED`.

---

## 7. Invariants (Do Not Break)

1. **Stateless settings** — no per-run mutable state on `ToolSettings`.
2. **Counts from `call_contexts`** — denied calls do not consume per-tool budget.
3. **Internal tools exempt** — never block or truncate `isDone` / internal tools.
4. **Pre-exec before middleware** — tool settings cannot be reordered after
   `before_tool_call`.
5. **Denials not truncated** — use `truncate=False` when appending deny messages.
6. **Raw vs visible** — truncation never mutates the stored raw `ToolResult`.
7. **`max_calls` ↔ `max_tool_calls`** — if both set, values must match; mapping
   prefers `ToolSettings.max_calls` when present.
8. **Linear-only today** — non-linear runtimes reject `tool_settings` at
   construction.
9. **Opt-in** — `tool_settings=None` must preserve pre-ToolSettings behavior.
10. **`ConfigurationError`** for invalid config — fail at construction, not mid-run.

### Edge cases to cover when extending

| Case | Expected |
|------|----------|
| Blank tool names | `ConfigurationError` at construction |
| `str` passed as `denied_tools` | `ConfigurationError` |
| `result_max_chars=0` | Valid; body hidden except truncation marker |
| Multi-tool model turn near `max_calls` | Same-iteration stop before over-budget call |
| Dynamic tool attach by name in `denied_tools` | Denied at call time |
| Concurrent runs sharing settings | Safe only because settings stay stateless |

---

## 8. Verification Checklist

After implementation (import/compile smoke is the minimum for docs-only
workflows; full suites when behavior changes):

- [ ] `from vidbyte import ToolSettings` works
- [ ] `from vidbyte.agents import ToolSettings, AgentLoopSettings` works
- [ ] Invalid construction raises `ConfigurationError` with a clear field name
- [ ] Denied tool with `on_deny="continue"` appears in context; run continues
- [ ] Denied tool with `on_deny="abort"` stops with `tool_settings_denied`
- [ ] Per-tool cap denies after limit; denied calls do not count as executed
- [ ] `max_calls` stops mid-iteration on multi-tool responses when over budget
- [ ] `result_max_chars` truncates visible output; raw context result intact
- [ ] Denial visible even when `result_max_chars=0` (not truncated away)
- [ ] `isDone` never denied / never truncated by tool settings
- [ ] Non-linear runtime + `tool_settings` raises at agent construction
- [ ] README / this skill / update-skill-files matrix updated

---

## 9. What NOT to Do

- **Do not** reintroduce middleware-based tool-settings enforcement (PR #249 is
  superseded).
- **Do not** put per-run counters on the shared `ToolSettings` instance.
- **Do not** block internal tools (`isDone`).
- **Do not** truncate runtime-injected denial messages.
- **Do not** mutate the raw `ToolResult` when applying `result_max_chars`.
- **Do not** overload `MIDDLEWARE_ABORT` for tool-settings stops.
- **Do not** flatten every new tool-use knob onto `AgentLoopSettings` — nest
  under `ToolSettings`.
- **Do not** assume non-linear runtimes enforce `tool_settings` — they reject
  it today.
- **Do not** treat `ToolSettings` as a replacement for `PermissionPolicy`.
- **Do not** add allowlist semantics unless a design review explicitly expands
  the policy surface (current model is denied-only).

---

## 10. Related Files

| Path | Role |
|------|------|
| `vidbyte/agents/settings/tool.py` | `ToolSettings` class + pure decisions |
| `vidbyte/agents/settings/loop.py` | Nesting, validation, `to_runtime_config()` |
| `vidbyte/agents/settings/__init__.py` | Settings package exports |
| `vidbyte/lib/dataclasses/agents.py` | `AgentRuntimeConfig.tool_settings`, `AgentStopReason` |
| `vidbyte/agents/runtime.py` | Enforcement chokepoints |
| `vidbyte/agents/base.py` | Non-linear construction guard |
| `vidbyte/agents/__init__.py` / `vidbyte/__init__.py` | Public re-exports |
| `README.md` | Developer-facing example |
| `docs/design/tool-settings-runtime-enforcement.md` | Original architecture design |
| `docs/design/tool-settings-skill.md` | Design for this skill |
| `docs/design/tool-settings-guardrail-budgets.md` | Guardrail budget fields design |
| `skills/agentic-loop-settings/SKILL.md` | Loop budgets reference |
| `skills/sdk/update-skill-files.md` | Change-type → skill matrix |
