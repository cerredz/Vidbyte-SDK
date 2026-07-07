# Design Doc: Tool Settings Enforcement

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-07
**Last Updated:** 2026-07-07

---

## 1. Overview

Add a small, universal `ToolSettings` configuration object to `vidbyte-sdk` and wire it into the direct agent runtime so developers can deny named tools, cap total tool use, cap individual tool use, and truncate model-visible tool results without manually composing middleware. This gives teams a durable tool-use policy surface for reminders, guardrails, dynamic tool attachment boundaries, and context bloat control while preserving existing middleware and loop-setting behavior.

---

## 2. Goals & Non-Goals

### Goals

- Add `ToolSettings` under `vidbyte.agents.settings`.
- Support exactly these settings in the initial API: `denied_tools`, `max_calls`, `max_calls_per_tool`, and `result_max_chars`.
- Enforce `denied_tools` before tool permission checks, validation, or execution.
- Enforce `max_calls` as a total per-run tool-call budget, including a same-iteration guard before executing extra tool calls from a multi-tool model response.
- Enforce `max_calls_per_tool` as a per-run, per-tool execution budget.
- Enforce `result_max_chars` by truncating the model-visible tool result while preserving the raw `ToolResult` in `ToolCallContext`.
- Hang `tool_settings` off `AgentLoopSettings`, matching the existing settings-driven runtime pattern.
- Auto-register settings-driven middleware from `BaseAgent` so users only need to set `agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(...))`.
- Preserve existing explicit middleware APIs for advanced users.
- Preserve backward compatibility with existing `AgentLoopSettings.max_tool_calls`.

### Non-Goals

- No allowlist setting. The requested policy surface is denied-only.
- No timeout, parallelism, caching, sandbox, schema, provider-rendering, or argument-coercion settings.
- No public behavior change when `tool_settings` is omitted.
- No changes to non-linear runtimes beyond rejecting settings that require middleware, consistent with existing middleware constraints.
- No new external dependencies.
- No test-file additions in this design-doc-no-tests workflow. Verification will use import/compile smoke checks after implementation.

---

## 3. Background & Context

`AgentLoopSettings` already centralizes loop controls in `vidbyte/agents/settings/loop.py`, and `BaseAgent` resolves it before building `AgentRuntimeConfig`. The direct runtime already enforces `max_tool_calls` via `AgentRuntimeConfig.max_tool_calls`, but that is currently a loop-level setting, not a cohesive tool policy object. It also only stops at loop boundaries, so a model response with multiple tool calls can still rely on runtime flow rather than an explicit same-iteration tool-settings guard.

The SDK already has the right enforcement seams:

- `ToolPolicyMiddleware` denies named tools in `before_tool_call`.
- `ToolResultCompactionMiddleware.truncate(...)` compacts model-visible tool outputs in `after_tool_call`.
- `RuntimeLimitMiddleware` and `AgentRuntime._budget_stop()` provide budget-stop precedents.
- `MiddlewareContext.run_state` is the established concurrency-safe place for per-run counters.
- `AgentRuntime._process_tool_call()` appends the raw `ToolCallContext` while using middleware transforms for the model-visible result.

The user specifically wants simple universal settings, not a broad tool framework. The most important semantic point is that `denied_tools` is still useful even when developers pass tools explicitly: it communicates team intent, acts as a hard reminder, and blocks tools acquired dynamically through agent-facing attachment tools when their names are denied.

---

## 4. Requirements

### Functional Requirements

1. `ToolSettings` must accept `denied_tools: Iterable[str] = ()`.
2. `ToolSettings` must accept `max_calls: int | None = None`.
3. `ToolSettings` must accept `max_calls_per_tool: Mapping[str, int] | None = None`.
4. `ToolSettings` must accept `result_max_chars: int | None = None`.
5. `ToolSettings` must normalize tool-name collections into immutable internal values.
6. `ToolSettings` must raise `ConfigurationError` for blank denied tool names.
7. `ToolSettings` must raise `ConfigurationError` when `max_calls` is provided and is not greater than zero.
8. `ToolSettings` must raise `ConfigurationError` when any `max_calls_per_tool` value is not greater than zero.
9. `ToolSettings` must raise `ConfigurationError` for blank `max_calls_per_tool` keys.
10. `ToolSettings` must raise `ConfigurationError` when `result_max_chars` is provided and is negative.
11. `result_max_chars=0` must be valid and must hide the raw body except for a truncation indicator.
12. `AgentLoopSettings` must accept `tool_settings: ToolSettings | None = None`.
13. `AgentLoopSettings.__repr__()` must include `tool_settings` when provided.
14. `AgentLoopSettings.to_runtime_config()` must map `ToolSettings.max_calls` into `AgentRuntimeConfig.max_tool_calls`.
15. If both existing `AgentLoopSettings.max_tool_calls` and `ToolSettings.max_calls` are provided with different values, settings validation must raise `ConfigurationError`.
16. If both existing `AgentLoopSettings.max_tool_calls` and `ToolSettings.max_calls` are provided with the same value, settings validation may accept it and map that value once.
17. `BaseAgent._runtime_middleware()` must auto-register a settings-driven middleware when `agent_loop_settings.tool_settings` is not `None`.
18. Non-linear runtimes that currently reject middleware must also reject `tool_settings` when it would require settings middleware.
19. Denied tools must not execute.
20. Denied tool calls must produce the existing middleware-denied tool-result path so the model can see that the tool was blocked.
21. `denied_tools` must apply to user tools and dynamically attached tools by name.
22. The internal runtime `isDone` tool must not be blocked by `denied_tools`, to avoid trapping the agent loop.
23. `max_calls` must stop the run before executing a tool call that would exceed the total tool-call budget.
24. `max_calls_per_tool` must deny the over-budget tool call before execution while allowing the model to choose a different tool on a later turn.
25. Per-run counters for `max_calls_per_tool` must live in `MiddlewareContext.run_state`, not on the middleware instance.
26. `result_max_chars` must truncate only the model-visible result appended to provider messages.
27. `result_max_chars` must not mutate the raw `ToolResult` stored in `ToolCallContext`.
28. Settings-driven middleware must compose with user-provided middleware and existing context-window admission middleware.
29. Public exports must allow `from vidbyte.agents.settings import ToolSettings`, `from vidbyte.agents import ToolSettings`, and `from vidbyte import ToolSettings`.

### Non-Functional Requirements

- **Compatibility:** Existing agents without `tool_settings` must behave unchanged.
- **Security:** Denied tools must be blocked before permission checks, validation, or tool execution; this is especially important for dynamic attach tools.
- **Reliability:** Per-run counters must be concurrency-safe and must not leak across simultaneous runs that share an agent or middleware instance.
- **Context control:** Result truncation must reduce model-visible context bloat without losing raw runtime metadata.
- **Performance:** Enforcement must be O(1) per tool call, excluding the existing string slicing needed for result truncation.
- **Observability:** Middleware decisions should use explicit reasons and metadata such as `tool_name`, `max_calls`, `max_calls_per_tool`, and `result_max_chars`.

---

## 5. High-Level Design

Create `ToolSettings` as a sibling to the existing loop settings class under `vidbyte/agents/settings/tool.py`. `AgentLoopSettings` receives an optional `tool_settings` field and validates that it is either absent or a `ToolSettings` instance. `ToolSettings.max_calls` becomes the new cohesive public name for the total tool-call budget, while existing `AgentLoopSettings.max_tool_calls` remains supported for compatibility.

Add a new built-in `ToolSettingsMiddleware` to enforce the tool-specific policy at runtime. It uses `before_tool_call` for `denied_tools`, `max_calls`, and `max_calls_per_tool`, and `after_tool_call` for `result_max_chars`. The middleware stores per-run call counters in `ctx.run_state[ToolSettingsMiddleware]`, following the concurrency-safe middleware pattern already used elsewhere in the repo.

`BaseAgent._runtime_middleware()` auto-inserts `ToolSettingsMiddleware` when `agent_loop_settings.tool_settings` exists. It should run before user middleware because settings are baseline agent construction policy, not optional model behavior. When `ToolErrorPolicyMiddleware` is also configured, it runs ahead of `ToolSettingsMiddleware` so silent retry attempts do not consume per-tool execution budgets before the final result is known. The runtime still appends context-window admission middleware afterward, so explicit algorithm-based compaction remains later in the pipeline and can override earlier result transforms if configured.

```text
AgentLoopSettings(tool_settings=ToolSettings(...))
      |
      v
BaseAgent._runtime_middleware()
      |
      v
ToolSettingsMiddleware
  before_tool_call:
    - deny named tools
    - abort if total max_calls would be exceeded
    - deny if per-tool max would be exceeded
  after_tool_call:
    - truncate model-visible result to result_max_chars
      without changing raw ToolCallContext.result
      |
      v
AgentRuntime._process_tool_call()
  - records raw context
  - appends transformed visible result to provider messages
```

---

## 6. Detailed Design

### 6.1 ToolSettings

**File(s):** `vidbyte/agents/settings/tool.py`
**Type:** New file

#### What it does

Defines the developer-facing universal tool settings object and owns eager validation for denied names, call budgets, per-tool budgets, and model-visible result bounds.

#### Interface / API

```python
class ToolSettings:
    def __init__(self, *, denied_tools: Iterable[str] = (), max_calls: int | None = None, max_calls_per_tool: Mapping[str, int] | None = None, result_max_chars: int | None = None) -> None: ...
```

#### Logic / Algorithm

1. Normalize `denied_tools` into a `frozenset[str]` of stripped tool names.
2. Normalize `max_calls_per_tool` into a `dict[str, int]` with stripped tool names.
3. Store `max_calls` and `result_max_chars`.
4. Validate blank names and numeric bounds.
5. Implement `__repr__()` showing only non-empty or non-`None` fields.

#### Edge Cases & Error Handling

- Blank denied tool names raise `ConfigurationError`.
- Blank per-tool budget keys raise `ConfigurationError`.
- Duplicate denied names collapse naturally through `frozenset`.
- `max_calls_per_tool=None` and `{}` are equivalent.
- `result_max_chars=0` is valid.

---

### 6.2 AgentLoopSettings Integration

**File(s):** `vidbyte/agents/settings/loop.py`, `vidbyte/agents/settings/__init__.py`
**Type:** Modified

#### What it does

Adds `tool_settings` as a nested settings object and reconciles `ToolSettings.max_calls` with the existing `max_tool_calls` field.

#### Interface / API

```python
class AgentLoopSettings:
    def __init__(self, *, ..., max_tool_calls: int | None = None, ..., tool_settings: ToolSettings | None = None) -> None: ...
```

#### Logic / Algorithm

1. Import `ToolSettings`.
2. Add `tool_settings` to the constructor and store it.
3. Add `_validate_tool_settings()`:
   - if present and not a `ToolSettings`, raise `ConfigurationError`;
   - if `self.max_tool_calls` and `self.tool_settings.max_calls` are both present and differ, raise `ConfigurationError`.
4. Update `to_runtime_config()`:
   - compute `max_tool_calls = self.tool_settings.max_calls if available else self.max_tool_calls`;
   - pass that value into `AgentRuntimeConfig`.
5. Export `ToolSettings` from `vidbyte.agents.settings`.

#### Edge Cases & Error Handling

- Existing `AgentLoopSettings(max_tool_calls=20)` remains valid.
- New `AgentLoopSettings(tool_settings=ToolSettings(max_calls=20))` maps to the same runtime budget.
- Providing both with different values raises a clear error instead of silently picking one.

---

### 6.3 ToolSettingsMiddleware

**File(s):** `vidbyte/middleware/builtins/tool_settings.py`, `vidbyte/middleware/builtins/__init__.py`, `vidbyte/middleware/__init__.py`
**Type:** New file, Modified

#### What it does

Enforces `ToolSettings` at middleware hook boundaries.

#### Interface / API

```python
class ToolSettingsMiddleware(AgentMiddleware):
    def __init__(self, settings: ToolSettings) -> None: ...
    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm

1. `before_run` initializes `_ToolSettingsRunState(calls_by_tool={})` in `ctx.run_state`.
2. `before_tool_call` returns continue when `ctx.tool_call` is missing.
3. `before_tool_call` returns continue for the internal `isDone` tool even if its name appears in `denied_tools`.
4. If the tool name is in `settings.denied_tools`, return `MiddlewareDecision.deny_tool("tool_settings_denied", metadata={"tool_name": name})`.
5. If `settings.max_calls` is set and `ctx.tool_call_count >= settings.max_calls`, return `MiddlewareDecision.abort("tool_settings_max_calls", metadata={"max_calls": settings.max_calls})`.
6. If `settings.max_calls_per_tool` has a limit for the tool and the per-run count is already at that limit, return `MiddlewareDecision.deny_tool("tool_settings_max_calls_per_tool", metadata={...})`.
7. If the tool is allowed to proceed, return continue without incrementing yet.
8. `after_tool_call` increments the per-tool counter only after a non-middleware-denied final result reaches the hook. This avoids counting settings/user denials and avoids counting silent retry attempts that `ToolErrorPolicyMiddleware` will retry before the model sees them.
9. `after_tool_call` returns continue when `result_max_chars` is `None`, when the tool is internal, or when no tool result exists.
10. `after_tool_call` slices `ctx.tool_result.output` when its length exceeds `result_max_chars`, appends a clear truncation indicator, and returns `MiddlewareTransform(model_visible_tool_result=...)`.
11. The transformed result keeps the original status and metadata, adding metadata such as `tool_settings_truncated=True`, `original_chars`, and `visible_chars`.

#### Edge Cases & Error Handling

- Middleware hook-level tests may call `before_tool_call` without `before_run`; `_state_for(ctx)` must initialize missing state defensively.
- A denied call from this middleware or another middleware does not increment per-tool execution counters.
- A per-tool over-limit denial does not execute the tool.
- Silent retry attempts do not increment per-tool execution counters; only the final non-retried result does.
- Total `max_calls` aborts the run instead of denying a single tool, because the total run budget has been exhausted.
- Later middleware transforms may override the model-visible result; this is acceptable and follows existing middleware ordering rules.

---

### 6.4 BaseAgent Wiring

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Auto-registers settings-driven middleware and blocks unsupported runtime combinations.

#### Interface / API

```python
class BaseAgent:
    def _runtime_middleware(self) -> tuple[AgentMiddleware, ...]: ...
```

#### Logic / Algorithm

1. After resolving `self.agent_loop_settings`, reject non-linear runtimes when `tool_settings` is present, matching the existing middleware restriction.
2. In `_runtime_middleware()`, create `ToolSettingsMiddleware(self.agent_loop_settings.tool_settings)` when settings are present.
3. Return middleware in this order: tool-error policy middleware if present, tool-settings middleware if present, user middleware, continual-trace middleware when enabled.
4. Preserve `fork()` behavior by passing the existing `agent_loop_settings` object to the child.

#### Edge Cases & Error Handling

- Existing agents with no `tool_settings` see no middleware insertion.
- If a user also passes explicit `ToolPolicyMiddleware` or `ToolResultCompactionMiddleware`, both compose through normal middleware order.
- Tool-error policy middleware is ordered first only to let retry decisions short-circuit intermediate attempts; tool settings still run before user middleware for normal allowed/denied tool calls.

---

### 6.5 Public Exports

**File(s):** `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes `ToolSettings` and `ToolSettingsMiddleware` discoverable through existing public import surfaces.

#### Interface / API

```python
from vidbyte import AgentLoopSettings, ToolSettings
from vidbyte.middleware.builtins import ToolSettingsMiddleware
```

#### Logic / Algorithm

1. Export `ToolSettings` from `vidbyte.agents.settings`.
2. Export `ToolSettings` from `vidbyte.agents`.
3. Export `ToolSettings` from root `vidbyte`.
4. Export `ToolSettingsMiddleware` from `vidbyte.middleware.builtins` and `vidbyte.middleware`.

#### Edge Cases & Error Handling

- Avoid import cycles by keeping `ToolSettings` independent from middleware code.
- Root exports must import from agents/settings, not from middleware internals.

---

### 6.6 Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents the small universal settings surface near the existing tools/middleware docs.

#### Interface / API

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
        ),
    ),
)
```

#### Logic / Algorithm

1. Explain that `ToolSettings` is for simple universal tool guardrails.
2. Explain that `denied_tools` is useful even when tools are passed explicitly because it documents team policy and blocks dynamically attached tools by name.
3. Explain that raw tool results remain available in runtime metadata while model-visible results may be truncated.

#### Edge Cases & Error Handling

- Documentation must not imply that `ToolSettings` replaces `PermissionPolicy` or explicit middleware.
- Documentation must note that internal runtime tools are not blocked by denied tool settings.

---

## 7. Data Model Changes

### 7.1 `ToolSettings`

**Change type:** New

```python
class ToolSettings:
    denied_tools: frozenset[str]
    max_calls: int | None
    max_calls_per_tool: Mapping[str, int]
    result_max_chars: int | None
```

**Migration strategy:** N/A - in-memory Python SDK settings object only.

- Forward migration: add the new class and wire it through `AgentLoopSettings`.
- Rollback plan: remove the class, remove `AgentLoopSettings.tool_settings`, and remove settings-driven middleware registration.

### 7.2 `_ToolSettingsRunState`

**Change type:** New internal runtime state

```python
@dataclass
class _ToolSettingsRunState:
    calls_by_tool: dict[str, int]
```

**Migration strategy:** N/A - per-run in-memory middleware state only.

- Forward migration: create state in `before_run` and defensive hook paths.
- Rollback plan: remove the middleware.

---

## 8. API Changes

N/A - no HTTP endpoints are affected.

### 8.1 Python SDK: ToolSettings

**Change type:** New

**Request:**

```python
AgentLoopSettings(
    tool_settings=ToolSettings(
        denied_tools={"delete_file"},
        max_calls=20,
        max_calls_per_tool={"search": 5, "shell": 3},
        result_max_chars=8000,
    )
)
```

**Response:**

```python
reply.metadata["stop_reason"] == "middleware_abort"  # when max_calls aborts through middleware
reply.metadata["tool_call_states"]                  # includes "denied" for denied or per-tool-over-limit calls
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid settings values raise `ConfigurationError` during agent/settings construction. |
| N/A | A denied tool returns a middleware-denied tool result and does not execute. |
| N/A | A total tool-call budget overrun aborts the run before executing another tool. |
| N/A | A per-tool budget overrun denies that tool call and lets the model continue. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/tool-settings-enforcement.md` | Design doc for simple universal tool settings |
| CREATE | `vidbyte/agents/settings/tool.py` | New `ToolSettings` class |
| CREATE | `vidbyte/middleware/builtins/tool_settings.py` | Settings-driven middleware enforcement |
| MODIFY | `vidbyte/agents/settings/loop.py` | Add `tool_settings` and reconcile `max_calls` with `max_tool_calls` |
| MODIFY | `vidbyte/agents/settings/__init__.py` | Export `ToolSettings` |
| MODIFY | `vidbyte/agents/base.py` | Auto-register settings middleware and reject unsupported runtimes |
| MODIFY | `vidbyte/agents/__init__.py` | Export `ToolSettings` |
| MODIFY | `vidbyte/middleware/builtins/__init__.py` | Export `ToolSettingsMiddleware` |
| MODIFY | `vidbyte/middleware/__init__.py` | Re-export `ToolSettingsMiddleware` |
| MODIFY | `vidbyte/__init__.py` | Root export for `ToolSettings` and `ToolSettingsMiddleware` |
| MODIFY | `README.md` | Document simple universal tool settings |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | dataclasses, collections ABCs, string slicing | Existing runtime only |
| `vidbyte.lib.errors.ConfigurationError` | internal | Settings validation errors | Low - already used by settings |
| `vidbyte.middleware` | internal | Runtime enforcement hooks | Low - established policy seam |

No new package dependencies or external services are introduced.

---

## 11. Rollout & Deployment

- This is a package-only SDK change.
- No feature flag is required.
- The feature is opt-in through `AgentLoopSettings(tool_settings=...)`.
- Existing `max_tool_calls` remains supported.
- Rollout sequence after approval:
  1. Create an isolated worktree from updated `main`.
  2. Commit this design doc first.
  3. Add `ToolSettings`.
  4. Add `ToolSettingsMiddleware`.
  5. Wire settings through `AgentLoopSettings` and `BaseAgent`.
  6. Add exports.
  7. Update README.
  8. Run compile/import verification.
  9. Push the branch and open a draft PR.
- Rollback procedure:
  1. Revert the feature branch merge commit.
  2. Remove the new settings and middleware files.
  3. Restore modified exports, README, `AgentLoopSettings`, and `BaseAgent`.

---

## 12. Open Questions

- [ ] Should `max_calls_per_tool` over-limit behavior deny the single tool call, as proposed, or abort the whole run like `max_calls`?
- [ ] Should `ToolSettings.max_calls` eventually replace the older top-level `AgentLoopSettings.max_tool_calls` in documentation, leaving the old field as a compatibility alias?
- [ ] Should settings-driven middleware run before all user middleware, as proposed, or after user middleware so custom audit middleware can observe every attempted call before a denial?

---

## 13. Alternatives Considered

### Alternative 1: Add flat fields directly to AgentLoopSettings

- What: Add `denied_tools`, `max_calls`, `max_calls_per_tool`, and `result_max_chars` directly to `AgentLoopSettings`.
- Why rejected: These settings are conceptually about tool use, not the whole loop. A nested `ToolSettings` object keeps the public API cleaner and leaves room for future universal tool settings without bloating the loop settings constructor.

### Alternative 2: Require users to compose existing middleware manually

- What: Tell users to use `ToolPolicyMiddleware`, `RuntimeLimitMiddleware`, and `ToolResultCompactionMiddleware` directly.
- Why rejected: The request is for first-class settings. Manual middleware composition is still useful for advanced cases, but it does not provide the team-level declarative reminder and dynamic-tool guardrail the user asked for.

### Alternative 3: Implement everything directly inside AgentRuntime

- What: Pass `ToolSettings` into `AgentRuntime` and add enforcement directly in `_process_tool_call()`.
- Why rejected: The repo already treats tool policy and result shaping as middleware concerns. Runtime should provide the mechanism; settings-driven middleware should own policy.

### Alternative 4: Reuse only ToolPolicyMiddleware and ToolResultCompactionMiddleware

- What: Auto-register existing middleware classes and add no new settings-specific middleware.
- Why rejected: `max_calls_per_tool` needs new per-run state and `max_calls` needs a same-iteration pre-execution guard. A dedicated middleware is clearer than spreading settings behavior across several generated middleware instances.
