# Design Doc: AgentLoopSettings

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-14
**Last Updated:** 2026-06-14

---

## 1. Overview

`AgentLoopSettings` is a new first-class configuration object that consolidates all deterministic parameters governing the agentic execution loop into a single, validated, developer-facing class. Previously these parameters were scattered as flat keyword arguments on `BaseAgent` and stored internally in `AgentRuntimeConfig`. This change groups them under a named abstraction that owns its own validation, documents the full parameter surface in a companion skill file, and wires the object through `BaseAgent` so that `self.agent_loop_settings` is the single source of truth for loop constraints at runtime.

---

## 2. Goals & Non-Goals

### Goals
- Introduce `AgentLoopSettings` as a structured class in `vidbyte/agents/settings/` that holds all agentic loop control parameters.
- Move validation for existing loop budget params (`max_iterations`, `max_tokens`, `compaction_trigger_tokens`, `compaction_target_tokens`) from `AgentRuntimeConfig.__post_init__` into `AgentLoopSettings.__init__`.
- Add new validated parameters: `max_tool_calls`, `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, `allowed_tools`.
- Wire `self.agent_loop_settings` onto `BaseAgent` so every agent exposes a populated settings object.
- Enforce `max_tool_calls` at runtime via `AgentRuntime._budget_stop()` (the one new param that maps directly to existing runtime accounting).
- Inject the calculable loop budgets (`max_iterations`, `max_tokens`, `max_tool_calls`) into the system context on every iteration as `current usage / configured limit`, placed directly beneath the system-prompt header.
- Write the canonical `skills/agentic-loop-settings/SKILL.md` skill file as the ground-truth reference for all agentic loop settings — past, present, and future.
- Export `AgentLoopSettings` from `vidbyte/agents/__init__.py`.
- Maintain full backward compatibility with the existing flat kwargs on `BaseAgent`.

### Non-Goals
- Runtime enforcement of `max_parallel_tool_calls`, `max_retries`, `timeout_seconds`, `context_window_budget`, or `allowed_tools` (these are stored and validated on `AgentLoopSettings` but the runtime loop enforcement is deferred to follow-up PRs).
- Context-window injection of the non-calculable settings (`max_retries`, `timeout_seconds`, `allowed_tools`, etc.) — only the calculable budgets are surfaced to the agent.
- A `memory_strategy` parameter — this concept does not belong on `AgentLoopSettings` and is intentionally excluded.
- Removal or replacement of `AgentRuntimeConfig` — it stays as the internal runtime-facing dataclass; `AgentLoopSettings` converts to it via `to_runtime_config()`.
- Changes to MCTS or Actor runtimes — they do not read `AgentRuntimeConfig` via the same path.
- Identity or multi-agent parameters (`agent_role`, `parent_agent_id`, `max_subagents`, `output_schema`).

---

## 3. Background & Context

`BaseAgent.__init__` currently accepts `max_iterations`, `max_tokens`, `compaction_trigger_tokens`, and `compaction_target_tokens` as flat keyword arguments. These get assembled into an `AgentRuntimeConfig` frozen dataclass that `AgentRuntime` reads during execution. This is sufficient for four parameters but creates a flat, undifferentiated surface that will become unmaintainable as new loop-control parameters are added.

The semantic concept of "things that control the agent's execution loop" is a natural cohesion unit. By creating `AgentLoopSettings`, the SDK gains:
1. A documented, introspectable place to read loop constraints from any code that holds a `BaseAgent`.
2. A single class that owns validation and can raise `ConfigurationError` with clear messages.
3. A skill file that serves as the living reference for what each setting means and when to use it.

The `ActorRuntime` class in `vidbyte/agents/runtimes/configs.py` is the nearest precedent: a plain class (not a dataclass) that holds runtime-specific parameters with `__init__`-level validation. `AgentLoopSettings` follows that same pattern.

---

## 4. Requirements

### Functional Requirements
1. `AgentLoopSettings` can be constructed with any combination of its parameters; all parameters are optional and default to `None`.
2. `AgentLoopSettings.__init__` raises `ConfigurationError` for any param that is provided with a non-positive numeric value.
3. `AgentLoopSettings.__init__` raises `ConfigurationError` if `compaction_target_tokens >= compaction_trigger_tokens` when both are provided.
4. `AgentLoopSettings.to_runtime_config()` returns an `AgentRuntimeConfig` populated from the settings.
5. `BaseAgent.__init__` accepts `agent_loop_settings: AgentLoopSettings | None = None` in addition to existing flat params.
6. If both `agent_loop_settings` and any individual flat param (`max_iterations`, `max_tokens`, etc.) are provided simultaneously, `BaseAgent.__init__` raises `ConfigurationError`.
7. If only flat params are provided (no `agent_loop_settings`), `BaseAgent.__init__` internally constructs an `AgentLoopSettings` from them so `self.agent_loop_settings` is always set.
8. `BaseAgent.agent_loop_settings` is a public attribute, always set after construction.
9. `AgentRuntime._budget_stop()` enforces `max_tool_calls` in addition to existing `max_iterations` / `max_tokens`.
10. `AgentRuntimeConfig` gains a `max_tool_calls: int | None = None` field.
11. `AgentLoopSettings` is exported from `vidbyte/agents/__init__.py`.
12. The skill file `skills/agentic-loop-settings/SKILL.md` documents all parameters with descriptions, intent, implementation status, and code examples.
13. `AgentRuntime` injects the calculable budgets (`max_iterations`, `max_tokens`, `max_tool_calls`) into the system context on every iteration as `current usage / configured limit`, placed directly beneath the system-prompt header. Non-calculable settings are excluded. When no calculable budget is configured, no block is injected.

### Non-Functional Requirements
- No performance regression: `AgentLoopSettings.__init__` runs at agent construction time, not in the hot loop.
- Backward compatibility: existing code that passes flat params to `BaseAgent` must continue to work unchanged.
- Validation messages must name the offending parameter explicitly.

---

## 5. High-Level Design

`AgentLoopSettings` is a plain Python class (following the `ActorRuntime` precedent) that lives in a new `vidbyte/agents/settings/` sub-package. It accepts all loop budget parameters in its `__init__`, calls a private `_validate()` method immediately, and exposes parameters as instance attributes. It provides a `to_runtime_config()` method that converts the subset of fields understood by `AgentRuntimeConfig` into one.

`BaseAgent.__init__` gains a new `agent_loop_settings` keyword argument. A private static method `_resolve_loop_settings()` handles the three possible call shapes: (a) `agent_loop_settings` provided — use it directly; (b) flat params provided — build `AgentLoopSettings` from them; (c) nothing provided — construct a default empty `AgentLoopSettings`. Shape (a) + flat params together is an error.

`AgentRuntimeConfig` gains one new field (`max_tool_calls`) so that `AgentRuntime._budget_stop()` can enforce it without reading `AgentLoopSettings` directly.

```
BaseAgent.__init__
  └─ _resolve_loop_settings(agent_loop_settings, flat_params)
        └─ AgentLoopSettings(...)          ← validates all params
              └─ .to_runtime_config()       ← feeds AgentRuntimeConfig
                    └─ AgentRuntime._budget_stop() enforces max_iterations, max_tokens, max_tool_calls
```

The skill file is a standalone Markdown document at `skills/agentic-loop-settings/SKILL.md` and does not affect runtime behavior.

---

## 6. Detailed Design

### 6.1 `AgentLoopSettings`

**File:** `vidbyte/agents/settings/loop.py`
**Type:** New file

#### What it does
Holds all deterministic parameters that govern the agentic execution loop. Validates constraints at construction time and converts to the internal `AgentRuntimeConfig` contract.

#### Interface / API
```python
class AgentLoopSettings:
    def __init__(
        self,
        *,
        max_iterations: int | None = None,
        max_tokens: int | None = None,
        max_tool_calls: int | None = None,
        max_parallel_tool_calls: int | None = None,
        max_retries: int | None = None,
        timeout_seconds: float | None = None,
        context_window_budget: int | None = None,
        compaction_trigger_tokens: int | None = None,
        compaction_target_tokens: int | None = None,
        allowed_tools: tuple[str, ...] | None = None,
    ) -> None: ...

    def to_runtime_config(self) -> AgentRuntimeConfig: ...
```

#### Logic / Algorithm
1. Store all params as instance attributes.
2. Call `_validate()` immediately.
3. `_validate()` checks:
   - For each of `max_iterations`, `max_tokens`, `max_tool_calls`, `max_parallel_tool_calls`, `max_retries`, `context_window_budget`, `compaction_trigger_tokens`, `compaction_target_tokens`: if not `None` and `<= 0`, raise `ConfigurationError`.
   - For `timeout_seconds`: if not `None` and `<= 0.0`, raise `ConfigurationError`.
   - If both `compaction_trigger_tokens` and `compaction_target_tokens` are set and `compaction_target_tokens >= compaction_trigger_tokens`, raise `ConfigurationError`.
4. `to_runtime_config()` returns `AgentRuntimeConfig(max_iterations=..., max_tokens=..., max_tool_calls=..., compaction_trigger_tokens=..., compaction_target_tokens=...)`.

#### Edge Cases & Error Handling
- All-`None` construction is valid (a default settings object).
- `allowed_tools` as an empty tuple is valid (means no tools are allowed).
- Error messages include the param name and the invalid value.

---

### 6.2 `vidbyte/agents/settings/__init__.py`

**File:** `vidbyte/agents/settings/__init__.py`
**Type:** New file

Exports `AgentLoopSettings`.

---

### 6.3 `AgentRuntimeConfig` extension

**File:** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it changes
Adds `max_tool_calls: int | None = None` to the frozen dataclass and adds `max_tool_calls` to the `__post_init__` positive-integer validation loop.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None      # NEW
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
```

---

### 6.4 `BaseAgent` changes

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it changes
- Adds `agent_loop_settings: AgentLoopSettings | None = None` to `__init__` signature.
- Adds `_resolve_loop_settings()` static method.
- Removes the existing inline `AgentRuntimeConfig(...)` construction block and delegates to `agent_loop_settings.to_runtime_config()`.
- Sets `self.agent_loop_settings` as a public attribute.
- Updates `fork()` to pass `agent_loop_settings=self.agent_loop_settings` and remove the individual flat params from the fork call.

#### Logic / Algorithm
`_resolve_loop_settings(agent_loop_settings, flat_kwargs)`:
1. If `agent_loop_settings` is set and any flat kwarg is also set: raise `ConfigurationError`.
2. If `agent_loop_settings` is set: return it as-is.
3. Otherwise: construct `AgentLoopSettings(**flat_kwargs)` and return it.

In `__init__`:
```python
self.agent_loop_settings = self._resolve_loop_settings(
    agent_loop_settings,
    max_iterations=effective_max_iterations,
    max_tokens=max_tokens,
    compaction_trigger_tokens=compaction_trigger_tokens,
    compaction_target_tokens=compaction_target_tokens,
)
self.runtime_config = self.agent_loop_settings.to_runtime_config()
```

#### Edge Cases & Error Handling
- `max_tool_rounds` alias (deprecated alias for `max_iterations`) is handled identically to today: resolved into `effective_max_iterations` before `_resolve_loop_settings` is called.
- Providing both `max_iterations` and `max_tool_rounds` is still an error (existing behavior, handled before the settings resolution).

---

### 6.5 `AgentRuntime._budget_stop()` extension

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it changes
Adds a `max_tool_calls` check to `_budget_stop()`. The `tool_call_count` is the existing `len(contexts)` already tracked in the loop.

```python
def _budget_stop(self, *, iteration_count, tokens_used, contexts):
    # existing max_iterations check
    # existing max_tokens check
    if self.config.max_tool_calls is not None and len(contexts) >= self.config.max_tool_calls:
        return self._stopped_result(
            "Agent runtime stopped after reaching max_tool_calls.",
            stop_reason=AgentStopReason.MAX_TOOL_CALLS,
            ...
        )
    return None
```

`AgentStopReason` gains a `MAX_TOOL_CALLS = "max_tool_calls"` enum value.

---

### 6.6 `vidbyte/agents/__init__.py` export

**File:** `vidbyte/agents/__init__.py`
**Type:** Modified

Adds:
```python
from vidbyte.agents.settings import AgentLoopSettings
```
and adds `"AgentLoopSettings"` to `__all__`.

---

### 6.7 Skill file

**File:** `skills/agentic-loop-settings/SKILL.md`
**Type:** New file

A Markdown document with Context Protocol Header comment block. Covers:
- What agentic loop settings are and why they exist as a named concept.
- Intent: these are deterministic parameters that control the execution envelope of the loop and are injected into the agent's awareness.
- Full parameter table (name, type, description, implementation status, default).
- The static config vs runtime-injected state distinction.
- Code examples for both the `agent_loop_settings=` object path and the flat params path.
- A section on which params are currently enforced by the runtime vs which are stored-and-reserved.
- Future roadmap section for deferred params.

---

## 7. Data Model Changes

### 7.1 `AgentRuntimeConfig`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    max_iterations: int | None = None
    max_tokens: int | None = None
    max_tool_calls: int | None = None        # NEW FIELD
    compaction_trigger_tokens: int | None = None
    compaction_target_tokens: int | None = None
```

**Migration strategy:** N/A — no persistence. Internal dataclass only. All callers that construct `AgentRuntimeConfig` directly (currently just `BaseAgent`) will be updated.

### 7.2 `AgentStopReason`

**Change type:** Modified

```python
class AgentStopReason(str, Enum):
    ...
    MAX_TOOL_CALLS = "max_tool_calls"    # NEW VALUE
```

---

## 8. API Changes

N/A — no HTTP endpoints are affected. The public Python SDK surface gains:
- `vidbyte.agents.AgentLoopSettings` (new class)
- `BaseAgent(agent_loop_settings=...)` (new keyword argument)
- `BaseAgent.agent_loop_settings` (new public attribute)

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/agents/settings/__init__.py` | New settings sub-package init |
| CREATE | `vidbyte/agents/settings/loop.py` | `AgentLoopSettings` class |
| CREATE | `skills/agentic-loop-settings/SKILL.md` | Canonical skill reference for agentic loop settings |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `max_tool_calls` to `AgentRuntimeConfig`; add `MAX_TOOL_CALLS` to `AgentStopReason` |
| MODIFY | `vidbyte/agents/base.py` | Add `agent_loop_settings` param; wire `_resolve_loop_settings`; set `self.agent_loop_settings` |
| MODIFY | `vidbyte/agents/runtime.py` | Enforce `max_tool_calls` in `_budget_stop()` |
| MODIFY | `vidbyte/agents/__init__.py` | Export `AgentLoopSettings` |
| CREATE | `scripts/test-agent-loop-settings.py` | Verification script covering all test cases |

---

## 10. Testing Plan

### Unit Tests

#### `AgentLoopSettings` validation
- `it('should construct successfully with all None defaults')` — [Edge Case]
- `it('should construct successfully with only max_iterations set')` — [Edge Case]
- `it('should raise ConfigurationError when max_iterations is 0')` — [Edge Case]
- `it('should raise ConfigurationError when max_iterations is negative')` — [Edge Case]
- `it('should raise ConfigurationError when max_tokens is 0')` — [Edge Case]
- `it('should raise ConfigurationError when max_tool_calls is 0')` — [Edge Case]
- `it('should raise ConfigurationError when timeout_seconds is 0.0')` — [Edge Case]
- `it('should raise ConfigurationError when timeout_seconds is negative')` — [Edge Case]
- `it('should raise ConfigurationError when compaction_target_tokens >= compaction_trigger_tokens')` — [Hidden Failure]
- `it('should accept allowed_tools as empty tuple')` — [Edge Case]
- `it('should raise ConfigurationError when context_window_budget is 0')` — [Edge Case]

#### `AgentLoopSettings.to_runtime_config()`
- `it('should produce AgentRuntimeConfig with None fields when all settings are None')` — [Silent Failure]
- `it('should correctly map max_iterations to AgentRuntimeConfig')` — [Silent Failure]
- `it('should correctly map max_tool_calls to AgentRuntimeConfig')` — [Silent Failure]
- `it('should correctly map compaction fields to AgentRuntimeConfig')` — [Silent Failure]

#### `BaseAgent` integration
- `it('should set self.agent_loop_settings when agent_loop_settings is provided')` — [Hidden Assumption]
- `it('should construct AgentLoopSettings from flat params when agent_loop_settings is not provided')` — [Silent Failure]
- `it('should default self.agent_loop_settings to an all-None instance when no params are provided')` — [Edge Case]
- `it('should raise ConfigurationError when agent_loop_settings AND max_iterations are both provided')` — [Hidden Assumption]
- `it('should raise ConfigurationError when agent_loop_settings AND max_tokens are both provided')` — [Hidden Assumption]
- `it('should still accept max_tool_rounds as an alias for max_iterations via flat params path')` — [Edge Case]

#### `AgentRuntime._budget_stop()` enforcement
- `it('should stop with MAX_TOOL_CALLS stop reason when tool call count reaches max_tool_calls')` — [Edge Case]
- `it('should not stop early when tool call count is below max_tool_calls')` — [Silent Failure]
- `it('should stop on MAX_TOOL_CALLS even if max_iterations has not been reached')` — [Hidden Failure]
- `it('should not enforce max_tool_calls when the field is None')` — [Hidden Assumption]

#### `AgentRuntime` loop-settings context injection
- `it('should render calculable budgets as current/limit lines')` — [Silent Failure]
- `it('should exclude budgets that are not configured')` — [Edge Case]
- `it('should render an empty block when no budgets are configured')` — [Edge Case]
- `it('should place the loop settings block beneath the system prompt header')` — [Hidden Assumption]

### Integration Tests
- `BaseAgent` constructed with `agent_loop_settings=AgentLoopSettings(max_tool_calls=2)` — run a fake runner that issues 3 tool calls and verify the loop stops with `stop_reason=max_tool_calls`. This catches the wiring between `AgentLoopSettings.to_runtime_config()` → `AgentRuntimeConfig` → `AgentRuntime._budget_stop()`. [Hidden Failure]
- `BaseAgent` constructed with flat params (`max_iterations=5`) — verify `self.agent_loop_settings.max_iterations == 5` and the runtime still stops correctly. [Silent Failure]
- `BaseAgent` forked from a parent — verify the fork's `agent_loop_settings` matches the parent's. [Hidden Assumption]

### Manual / QA Test Cases
1. Given a `BaseAgent` with `agent_loop_settings=AgentLoopSettings(max_tool_calls=1)`, when the agent calls a tool and the tool result returns, then the loop stops and `stop_reason` in metadata is `"max_tool_calls"`. — [Edge Case]
2. Given a `BaseAgent` constructed with `max_iterations=3` (flat param path), when `agent.agent_loop_settings` is inspected, then `agent_loop_settings.max_iterations == 3`. — [Silent Failure]
3. Given a `BaseAgent` with `agent_loop_settings=AgentLoopSettings(max_iterations=3)`, when it runs, then the system context contains a line `max_iterations: <current>/3` beneath the system prompt. — [Hidden Assumption]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte.lib.errors.ConfigurationError` | internal | Validation error type | None — already used everywhere |
| `vidbyte.lib.dataclasses.agents.AgentRuntimeConfig` | internal | Conversion target | Low — minor field addition |

---

## 12. Rollout & Deployment

- No feature flags. The `agent_loop_settings` param is additive; existing flat-param callers continue to work unchanged.
- Not a breaking change.
- No deployment order concerns — pure library code.
- Rollback: revert the PR. No migration artifacts.

---

## 13. Open Questions

- [ ] Should `AgentLoopSettings` be frozen/immutable (like `AgentRuntimeConfig`) or mutable? Current proposal: mutable class (like `ActorRuntime`), which allows subclassing but risks accidental mutation. Alternative: frozen dataclass.
- [ ] Should the skill file reference deferred params with a `[RESERVED]` tag or a `[FUTURE]` section to set expectations for contributors?
- [ ] `allowed_tools` param: should it be `tuple[str, ...]` or `frozenset[str]`? Set semantics make more sense for lookup but tuple is consistent with the rest of the SDK.

---

## 14. Alternatives Considered

### Alternative 1: Extend `AgentRuntimeConfig` directly
- What: Add all new fields directly to the `AgentRuntimeConfig` frozen dataclass and keep it as the single config object.
- Why rejected: `AgentRuntimeConfig` is an internal dataclass not exposed to users. Adding developer-facing params with validation logic directly to it would blur the internal/external boundary and make it harder to document and skill-file.

### Alternative 2: Replace `AgentRuntimeConfig` with `AgentLoopSettings`
- What: Delete `AgentRuntimeConfig` and pass `AgentLoopSettings` directly to `AgentRuntime`.
- Why rejected: `AgentRuntimeConfig` is referenced in `AgentRuntime.__init__`, the MCTS search runtime, and tests. A clean replacement is a follow-up refactor after `AgentLoopSettings` is established.

### Alternative 3: Dataclass instead of plain class
- What: Make `AgentLoopSettings` a `@dataclass(frozen=True, slots=True)` like `AgentRuntimeConfig`.
- Why rejected: Frozen dataclasses don't support custom `__init__` validation patterns as cleanly. The `ActorRuntime` precedent (a plain class with `__init__`-level validation) is the closer semantic match and is already established in this codebase.
