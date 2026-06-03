# Design Doc: Trajectory Checkpoint Inner Loop Context Window

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

---

> **Revision (PR #100 review):** The inner-loop API described below was
> simplified during review. The six-event `ContextWindowLifecycleEvent`
> lifecycle and the matching `InnerContextWindowAlgorithm` methods
> (`on_run_start`, `before_model_call`, `after_model_response`, `after_tool_call`,
> `after_iteration`, `on_run_end`) were collapsed into a **single** hook,
> `after_tool_calls`, dispatched from one point in the runtime loop (after a
> completed non-final iteration's tool calls; plus one run-start invocation with
> `ctx.iteration is None`). The two runtime dispatch helpers were merged into one.
> `ContextWindowRunContext` was reduced to `context_manager`, `recorder`, `state`,
> and `iteration`; all primitive placement logic now lives on `ContextManager`,
> which exposes semantic methods `place_after_system_prompt` and
> `place_after_tools` (these mint a stable `primitive_id` when missing). The
> `primitives.py` module was split into a `vidbyte/context/primitives/` package.
> Sections below that describe per-event lifecycle methods or the wide run-context
> object reflect the original design, not the shipped API.

## 1. Overview

This feature replaces PR #94's ad hoc `iteration_observer` message injection with a standard inner-loop context-window lifecycle API built on the existing `ContextManager`. Context-window algorithms that need to update model-visible context during the direct agent loop will receive a small `ContextWindowRunContext` object and will write typed `ContextItem` primitives into the active manager. The trajectory checkpoint preset will use this path by writing a custom `TrajectoryCheckpointContextItem` every configured number of completed non-final iterations, so the next model call sees the checkpoint through the normal context-window primitive rendering path.

---

## 2. Goals & Non-Goals

### Goals

- Add a standard, simple interface for context-window algorithms that update context during the inner direct agent loop.
- Use the existing `ContextManager` as the storage and rendering target for inner-loop context updates.
- Add a small abstract base class for inner-loop context-window algorithms with lifecycle hooks beyond only `after_iteration`.
- Add a `ContextWindowRunContext` object that exposes the current event facts, `ContextManager`, recorder, metadata store, and helper methods.
- Add context placement support for manager-backed context primitives while preserving existing default render behavior.
- Add a public `TrajectoryCheckpointAlgorithm` preset that writes a typed `TrajectoryCheckpointContextItem`.
- Preserve deterministic checkpoint cadence, bounded rendering, score metadata, and omission of raw tool output by default.
- Remove the need for `iteration_observer: Callable[[AgentIterationSnapshot], str | None]`.
- Update `skills/vidbyte-sdk/adding-context-window-algorithms.md` with guidance for inner-loop context updates.
- Add focused tests and an executable verification script covering public API, lifecycle behavior, manager rendering, trajectory checkpoints, and skill-doc guidance.

### Non-Goals

- No model-visible `write_context` tool for trajectory checkpoints in this PR.
- No model-controlled checkpoint cadence.
- No broad middleware contract changes.
- No replacement of existing `ContextUpsertTool`, primitive binding, or tool-result admission behavior.
- No database, persistence layer, vector memory, replay store, or cross-run storage.
- No live provider calls or network-based tests.
- No broad rewrite of `_arun_once(...)`, provider formatting, middleware, tracing, or tool execution.
- No support for composing multiple runtime algorithms at the same time.

---

## 3. Background & Context

- PR #94 adds trajectory checkpoints by passing an `iteration_observer` callback into `AgentRuntime._arun_once(...)` and appending returned text directly to provider `messages`.
- That approach works behaviorally but creates a second path for inner-loop context mutation that is not tied to the SDK's existing context-window primitives.
- The SDK already has `ContextManager.upsert()`, `ContextManager.render_primitives_zone()`, `ContextUpsertTool`, and tool primitive bindings.
- `AgentRuntime._build_system_string(...)` already renders the active manager's primitive zone between fixed system context and context body on each model call.
- Existing runtime algorithms such as Reflexion and Multi-Provider Agentic Grader wrap complete `_arun_once(...)` trials. Trajectory checkpoints are different because they need to update context between iterations inside one direct run.
- Middleware already has lifecycle hooks, but its decision contract is for runtime control actions such as continue, sleep, abort, deny tool, and retry. It does not own context-window writes.
- The desired standard is: inner-loop context-window algorithms receive a small run context and update context only through manager-backed context primitives.

---

## 4. Requirements

### Functional Requirements

1. `AgentIterationSnapshot` must represent observable completed iteration state without raw provider objects.
2. `ContextWindowLifecycleEvent` must enumerate the inner-loop lifecycle points exposed to context-window algorithms.
3. `ContextWindowPlacement` must represent where a managed context primitive should be rendered.
4. `InnerContextWindowAlgorithm` must provide no-op lifecycle methods for run start, before model call, after model response, after tool call, after iteration, and run end.
5. `ContextWindowRunContext` must expose the lifecycle event, current iteration snapshot, active `ContextManager`, recorder, metadata store, tool call/result facts, provider, message, and helper methods.
6. `ContextWindowRunContext.upsert(...)` must upsert a `ContextItem` into the active `ContextManager`.
7. `ContextWindowRunContext.append(...)` must append a `ContextItem` by generating a stable per-run primitive id when the item does not already have one.
8. `ContextWindowRunContext.remove(...)` must remove a managed primitive by id.
9. `ContextWindowRunContext.record(...)` must append recorder slots through the existing recorder abstraction.
10. `ContextWindowRunContext.set_metadata(...)` must allow algorithms to publish bounded final metadata.
11. `ContextWindowRunContext.every(iterations=n)` must return true only when the current completed iteration is a positive multiple of `n`.
12. `ContextManager.upsert(...)` must accept an optional placement while preserving the current default behavior.
13. Existing `ContextManager.upsert(item)` callers must continue to work unchanged.
14. Existing `ContextManager.render_primitives_zone()` output must remain backward compatible for default placements.
15. Runtime must create a private per-run `ContextManager` when an inner-loop context-window algorithm is active and the caller did not provide one.
16. Runtime must call inner-loop lifecycle methods at generic points without importing trajectory-specific code.
17. Runtime must not append trajectory checkpoint text directly to provider `messages`.
18. Runtime must not call inner-loop checkpoint hooks after final `isDone` in a way that writes a new checkpoint for a completed final run.
19. `TrajectoryCheckpointContextItem` must render checkpoint sections in stable order: `Reasoning Summary`, `Trajectory`, `Output`, `Score`, `Feedback`.
20. `TrajectoryCheckpointAlgorithm` must validate interval, max checkpoints, character limits, title strings, placement, and metadata keys at construction time.
21. `ContextWindow.preset.trajectory_checkpoints` must resolve to a configured `ContextWindowAlgorithm`.
22. `ContextWindow.resolve_algorithm("trajectory_checkpoints")` must return the preset.
23. `AgentRuntimeContextAlgorithms` must detect trajectory checkpoints as an inner-loop algorithm but must not wrap `_arun_once(...)` in an adapter that duplicates the loop.
24. Checkpoint cadence must be based on completed non-final iteration count.
25. `max_checkpoints` must cap the number of checkpoint primitives written.
26. Checkpoints must summarize observable runtime state only and must not claim hidden chain-of-thought.
27. Raw tool output must be omitted by default from checkpoint context text.
28. Raw tool output may be included only when explicitly configured and must be bounded.
29. Final `AgentResult.metadata` must include `trajectory_checkpoints` metadata with interval, checkpoint count, checkpoint records, and placements.
30. The SDK skill `skills/vidbyte-sdk/adding-context-window-algorithms.md` must document the standard path for inner-loop context-window updates.

### Non-Functional Requirements

- Performance: lifecycle dispatch must be O(1) per hook plus O(new observable state) for algorithms that run at that point.
- Security: context-window writes must not bypass tools, permissions, middleware, tracing, or tool-result admission.
- Reliability: default behavior must be unchanged when no inner-loop algorithm is configured.
- Observability: recorder slots and final metadata must describe lifecycle and checkpoint writes.
- Maintainability: runtime integration must be generic and algorithm-neutral.
- Testability: all runtime tests must use fake runners and fake tools.
- Backward compatibility: existing context primitive registry tests and tool binding tests must continue to pass.

---

## 5. High-Level Design

The feature adds a small inner-loop context-window lifecycle layer. `AgentRuntime` remains the owner of the direct model/tool loop. At existing lifecycle points, it builds a `ContextWindowRunContext` and delegates to the configured inner-loop context-window algorithm, if any. The algorithm can inspect bounded observable state and update the context window by upserting/removing typed `ContextItem`s through the active `ContextManager`.

Trajectory checkpoints become one implementation of this standard. The public `TrajectoryCheckpointAlgorithm` owns validation, cadence, deterministic scoring, and checkpoint construction. When `after_iteration(...)` fires on a non-final completed iteration, it checks `ctx.every(iterations=self.interval)`, builds a `TrajectoryCheckpointContextItem`, and writes it with `ctx.upsert(...)`. The next model call rebuilds the system prompt and naturally includes the checkpoint through `ContextManager.render_primitives_zone()`.

This design avoids three rejected approaches: it does not expose checkpoint creation as a model-selected tool, it does not add an arbitrary observer callback returning message text, and it does not overload middleware with prompt/context mutation effects. Instead, it creates one standard path for context-window algorithms that need to update context during the inner loop.

```text
AgentRuntime._arun_once(...)
    -> before_model_call lifecycle
    -> model call
    -> after_model_response lifecycle
    -> tool calls
        -> after_tool_call lifecycle
    -> after_iteration lifecycle
        -> TrajectoryCheckpointAlgorithm writes TrajectoryCheckpointContextItem
    -> next loop rebuilds system string
        -> ContextManager.render_primitives_zone()
```

---

## 6. Detailed Design

### 6.1 Agent Iteration Snapshot

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Adds an immutable snapshot of observable direct-runtime state after a completed model iteration.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class AgentIterationSnapshot:
    iteration_count: int
    message: str
    provider: str
    assistant_output: str | None = None
    tool_calls: tuple[ToolCallContext, ...] = ()
    tokens_used: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Runtime builds the snapshot from current loop counters, latest assistant text, accumulated tool call contexts, token count, and bounded metadata.
2. Snapshot excludes raw provider response objects.
3. Snapshot is passed to lifecycle context when an iteration has completed and the run will continue.

#### Edge Cases & Error Handling

- Missing provider token usage leaves `tokens_used=None`.
- Iterations with only tool calls use `assistant_output=None`.
- Empty assistant output is allowed.

---

### 6.2 Context Window Runtime Contracts

**File(s):** `vidbyte/context/runtime.py`
**Type:** New file

#### What it does

Defines the small abstraction used by inner-loop context-window algorithms.

#### Interface / API

```python
class ContextWindowLifecycleEvent(str, Enum):
    RUN_START = "run_start"
    BEFORE_MODEL_CALL = "before_model_call"
    AFTER_MODEL_RESPONSE = "after_model_response"
    AFTER_TOOL_CALL = "after_tool_call"
    AFTER_ITERATION = "after_iteration"
    RUN_END = "run_end"

class ContextWindowPlacement(str, Enum):
    TOP_OF_CONTEXT = "top_of_context"
    END_OF_CONTEXT = "end_of_context"
    TOP_OF_CONVERSATION = "top_of_conversation"
    END_OF_CONVERSATION = "end_of_conversation"

class InnerContextWindowAlgorithm:
    def on_run_start(self, ctx: ContextWindowRunContext) -> None: ...
    def before_model_call(self, ctx: ContextWindowRunContext) -> None: ...
    def after_model_response(self, ctx: ContextWindowRunContext) -> None: ...
    def after_tool_call(self, ctx: ContextWindowRunContext) -> None: ...
    def after_iteration(self, ctx: ContextWindowRunContext) -> None: ...
    def on_run_end(self, ctx: ContextWindowRunContext) -> None: ...

@dataclass(slots=True)
class ContextWindowRunContext:
    event: ContextWindowLifecycleEvent
    context_manager: ContextManager
    recorder: RecorderBase
    metadata: dict[str, Any]
    message: str
    provider: str
    iteration: AgentIterationSnapshot | None = None
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    model_response: object | None = None
    is_final: bool = False
    def upsert(self, item: ContextItem, *, placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT) -> None: ...
    def append(self, item: ContextItem, *, placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT) -> str: ...
    def remove(self, primitive_id: str) -> None: ...
    def record(self, slot: str, **metadata: Any) -> None: ...
    def set_metadata(self, key: str, value: Any) -> None: ...
    def every(self, *, iterations: int) -> bool: ...
```

#### Logic / Algorithm

1. The no-op abstract class makes lifecycle methods discoverable and overridable.
2. `upsert(...)` delegates to `ContextManager.upsert(item, placement=placement)`.
3. `append(...)` ensures the item has a primitive id, then delegates to upsert.
4. `remove(...)` delegates to `ContextManager.remove_by_id(...)`.
5. `record(...)` delegates to the runtime recorder.
6. `set_metadata(...)` writes into the mutable per-run algorithm metadata dict.
7. `every(...)` validates `iterations > 0` and checks the current iteration count.

#### Edge Cases & Error Handling

- `every(iterations=0)` raises `ValueError`.
- `append(...)` raises `ValueError` when it cannot create an id for a non-dataclass or unsupported item.
- `upsert(...)` preserves `ContextManager` frozen primitive errors.
- `record(...)` accepts empty metadata and still records the slot.

---

### 6.3 Context Manager Placement Support

**File(s):** `vidbyte/context/manager.py`
**Type:** Modified

#### What it does

Extends existing managed primitive storage with placement metadata while preserving current behavior.

#### Interface / API

```python
class ContextManager:
    def upsert(self, item: ContextItem, *, placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT) -> ContextManager: ...
    def placement_for(self, primitive_id: str) -> ContextWindowPlacement | None: ...
    def render_primitives_zone(self) -> str: ...
    def render_conversation_messages(self, placement: ContextWindowPlacement) -> tuple[dict[str, str], ...]: ...
```

#### Logic / Algorithm

1. Store placements in a private `_placements: dict[str, ContextWindowPlacement]`.
2. Default placement is `END_OF_CONTEXT`, so existing callers render the same way.
3. `TOP_OF_CONTEXT` items render before `END_OF_CONTEXT` items inside `render_primitives_zone()`.
4. `TOP_OF_CONVERSATION` and `END_OF_CONVERSATION` items render as assistant messages for provider `messages`.
5. Removing a primitive also removes placement metadata.
6. Clearing the registry clears placement metadata.

#### Edge Cases & Error Handling

- Invalid placement strings are normalized through `ContextWindowPlacement(...)` and raise `ValueError`.
- Replacing an item with the same id updates its placement.
- Frozen primitive replacement still raises before placement is changed.
- Empty registry still renders an empty string.

---

### 6.4 Context Window Lifecycle Dispatcher

**File(s):** `vidbyte/agents/context_algorithms.py`
**Type:** Modified

#### What it does

Detects both outer runtime algorithms and inner-loop context-window algorithms without putting algorithm-specific branches in `AgentRuntime`.

#### Interface / API

```python
class AgentRuntimeContextAlgorithms:
    def detect_algorithm(self) -> str | None: ...
    def return_algorithm(self) -> ReflexionRuntimeAlgorithm | MultiProviderAgenticGraderRuntimeAlgorithm | None: ...
    def inner_loop_algorithm(self) -> InnerContextWindowAlgorithm | None: ...
    def has_inner_loop_algorithm(self) -> bool: ...
```

#### Logic / Algorithm

1. Existing outer runtime algorithm behavior remains unchanged for Reflexion and Multi-Provider Agentic Grader.
2. `inner_loop_algorithm()` returns `self.runtime.algorithm.trajectory_checkpoints` when configured.
3. Outer runtime algorithms still use `arun(...)`; inner-loop algorithms are used by `_arun_once(...)`.
4. Multiple runtime algorithms remain invalid at config construction.

#### Edge Cases & Error Handling

- No configured inner algorithm returns `None`.
- Tool-result-only presets return `None`.
- Dispatcher tests fail if the preset exists but the runtime cannot discover it.

---

### 6.5 AgentRuntime Inner Loop Integration

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Adds generic context-window lifecycle dispatch to the direct runtime loop.

#### Interface / API

```python
class AgentRuntime:
    def _active_context_manager(self) -> ContextManager | None: ...
    def _context_window_run_context(...) -> ContextWindowRunContext | None: ...
    def _run_inner_context_window_hook(...) -> None: ...
    def _iteration_snapshot(...) -> AgentIterationSnapshot: ...
```

#### Logic / Algorithm

1. Runtime determines whether an inner-loop algorithm exists through `AgentRuntimeContextAlgorithms(self).inner_loop_algorithm()`.
2. If an inner-loop algorithm exists and `self.context_manager is None`, runtime creates a private per-run `ContextManager`.
3. Runtime calls `on_run_start(...)` once before loop execution.
4. Runtime calls `before_model_call(...)` before building final call options for each model call.
5. Runtime calls `after_model_response(...)` after token accounting and middleware acceptance.
6. Runtime calls `after_tool_call(...)` after each non-internal tool call has been executed or denied.
7. Runtime calls `after_iteration(...)` after completed non-final iterations only.
8. Runtime calls `on_run_end(...)` before returning the final `AgentResult`.
9. Runtime merges algorithm metadata from `ContextWindowRunContext.metadata` into final result metadata.
10. Runtime uses `ContextManager.render_conversation_messages(...)` when building call options for conversation placements.

#### Edge Cases & Error Handling

- No inner-loop algorithm means no private manager is created and no hook is called.
- If a lifecycle hook raises, the exception is allowed to fail the run because this is SDK algorithm code, not user middleware.
- `after_iteration(...)` is skipped for final `isDone`.
- Middleware abort results still pass through run-end lifecycle for metadata completion.
- Existing caller-provided `ContextManager` is reused rather than replaced.

---

### 6.6 Public Trajectory Checkpoint Config

**File(s):** `vidbyte/context/algorithms/trajectory_checkpoints.py`
**Type:** New file

#### What it does

Defines public immutable configuration, deterministic checkpoint building, and lifecycle behavior.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm(InnerContextWindowAlgorithm):
    interval: int = 3
    max_checkpoints: int = 8
    max_checkpoint_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
    score_enabled: bool = True
    checkpoint_title: str = "Runtime Checkpoint"
    placement: ContextWindowPlacement = ContextWindowPlacement.END_OF_CONTEXT
    metadata: Mapping[str, Any] = field(default_factory=dict)
    def after_iteration(self, ctx: ContextWindowRunContext) -> None: ...
    def on_run_end(self, ctx: ContextWindowRunContext) -> None: ...
    def should_checkpoint(self, iteration_count: int, checkpoint_count: int) -> bool: ...
    def build_item(self, snapshot: AgentIterationSnapshot, *, checkpoint_index: int) -> TrajectoryCheckpointContextItem: ...
```

#### Logic / Algorithm

1. Validate all public fields at construction time.
2. On `after_iteration(...)`, record `trajectory_checkpoint_iteration`.
3. Ignore duplicate iteration counts.
4. Check `should_checkpoint(...)`.
5. Build a `TrajectoryCheckpointContextItem` from observable snapshot state.
6. Upsert the item into the context manager with the configured placement.
7. Record `trajectory_checkpoint_injection`.
8. Store compact checkpoint metadata in instance-managed per-run state or `ctx.metadata`.
9. On run end, attach final `trajectory_checkpoints` metadata.

#### Edge Cases & Error Handling

- Invalid numeric config raises `ConfigurationError`.
- Blank title raises `ConfigurationError`.
- Non-string metadata keys raise `ConfigurationError`.
- Empty observations render explicit fallback text.
- `score_enabled=False` renders score as `N/A`.
- Raw tool outputs are omitted unless explicitly enabled.

---

### 6.7 Trajectory Checkpoint Context Item

**File(s):** `vidbyte/context/primitives.py`
**Type:** Modified

#### What it does

Adds a typed context primitive for trajectory checkpoints.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointContextItem:
    primitive_id: str
    iteration: int
    checkpoint_index: int
    reasoning_summary: str
    trajectory: str
    output: str
    score: float | None
    feedback: str
    title: str = "Runtime Checkpoint"
    max_chars: int = 2000
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "trajectory_checkpoint"
    primitive_frozen: bool = False
    def to_context_text(self) -> str: ...
```

#### Logic / Algorithm

1. Render required sections in stable order.
2. Format numeric scores with two decimals.
3. Render `N/A` for disabled score.
4. Bound final rendered text to `max_chars`.
5. Include metadata only as structured metadata, not in visible context text.

#### Edge Cases & Error Handling

- Very small `max_chars` truncates without exceeding the bound.
- Empty strings still render section headers.
- Score `None` renders `N/A`.

---

### 6.8 Presets And Public Exports

**File(s):** `vidbyte/context/algorithms/tool_results.py`, `vidbyte/context/algorithms/__init__.py`, `vidbyte/context/presets.py`, `vidbyte/context/__init__.py`, `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Wires the new public algorithm and primitive into the SDK surface.

#### Interface / API

```python
ContextWindow.preset.trajectory_checkpoints
ContextWindow.resolve_algorithm("trajectory_checkpoints")
from vidbyte import TrajectoryCheckpointAlgorithm, TrajectoryCheckpointContextItem
```

#### Logic / Algorithm

1. Add `trajectory_checkpoints: TrajectoryCheckpointAlgorithm | None` to `ContextWindowAlgorithm`.
2. Include trajectory checkpoints in runtime algorithm exclusivity validation.
3. Register preset in `ContextWindowPresets`.
4. Export the algorithm and context item from public modules.

#### Edge Cases & Error Handling

- Unknown preset strings still raise `ValueError`.
- Multiple runtime algorithms still raise.
- Existing default and tool-result-only presets remain unchanged.

---

### 6.9 Template Support

**File(s):** `vidbyte/lib/templates/trajectory_checkpoints.py`, `vidbyte/lib/templates/__init__.py`
**Type:** New file, Modified

#### What it does

Adds a template for validating trajectory checkpoint slot cadence.

#### Interface / API

```python
class TrajectoryCheckpointContextWindowTemplate(ContextWindowTemplate):
    def __init__(self, *, iterations: int, interval: int = 3, max_checkpoints: int | None = None) -> None: ...
```

#### Logic / Algorithm

1. Start with `system_prompt`.
2. Add `trajectory_checkpoint_iteration` for each completed non-final observed iteration.
3. Add `trajectory_checkpoint_injection` at interval boundaries until the cap is reached.

#### Edge Cases & Error Handling

- `iterations=0` produces only `system_prompt`.
- Negative iterations raise `ValueError`.
- `interval <= 0` raises `ValueError`.

---

### 6.10 Documentation And Skill Updates

**File(s):** `README.md`, `skills/vidbyte-sdk/adding-context-window-algorithms.md`, `skills/vidbyte-sdk/context-window-templates.md`
**Type:** Modified

#### What it does

Documents the new preset and the standard inner-loop context-window update path.

#### Interface / API

```python
agent = Agent(..., algorithm=ContextWindow.preset.trajectory_checkpoints)
```

#### Logic / Algorithm

1. README shows concise user-facing usage.
2. Context-window algorithm skill adds a section on inner-loop algorithms.
3. Skill guidance states algorithms must update context through `ContextWindowRunContext` and `ContextManager`, not direct `messages` mutation.
4. Template docs list trajectory checkpoint slots.

#### Edge Cases & Error Handling

- Docs must not imply hidden chain-of-thought access.
- Docs must not suggest model-called tools are required for deterministic runtime checkpoints.

---

## 7. Data Model Changes

### 7.1 `AgentIterationSnapshot`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class AgentIterationSnapshot:
    iteration_count: int
    message: str
    provider: str
    assistant_output: str | None = None
    tool_calls: tuple[ToolCallContext, ...] = ()
    tokens_used: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - in-memory SDK dataclass.

### 7.2 `ContextWindowLifecycleEvent`

**Change type:** New

```python
class ContextWindowLifecycleEvent(str, Enum): ...
```

**Migration strategy:** N/A - in-memory SDK enum.

### 7.3 `ContextWindowPlacement`

**Change type:** New

```python
class ContextWindowPlacement(str, Enum): ...
```

**Migration strategy:** N/A - in-memory SDK enum.

### 7.4 `ContextWindowRunContext`

**Change type:** New

```python
@dataclass(slots=True)
class ContextWindowRunContext: ...
```

**Migration strategy:** N/A - in-memory runtime object.

### 7.5 `TrajectoryCheckpointContextItem`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointContextItem: ...
```

**Migration strategy:** N/A - managed context primitive.

### 7.6 `ContextManager` Placement Registry

**Change type:** Modified

```python
_placements: dict[str, ContextWindowPlacement]
```

**Migration strategy:** No migration. Existing calls default to `END_OF_CONTEXT`.

---

## 8. API Changes

N/A - no HTTP endpoints are added or modified.

### 8.1 Python SDK Context-Window Preset

**Change type:** New

**Request:**

```python
from vidbyte import Agent, ContextWindow

agent = Agent(
    name="worker",
    system_prompt="Complete the task carefully.",
    runner=runner,
    tools=[lookup],
    algorithm=ContextWindow.preset.trajectory_checkpoints,
)
```

**Response:**

```python
AgentMessage(
    content="done",
    metadata={"trajectory_checkpoints": {"interval": 3, "checkpoint_count": 2}},
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid config raises `ConfigurationError`. |
| N/A | Unknown preset string raises `ValueError`. |
| N/A | Frozen context primitive blocks replacement and surfaces as a runtime error from SDK algorithm code. |

### 8.2 Python SDK Inner-Loop Context API

**Change type:** New

**Request:**

```python
class CustomAlgorithm(InnerContextWindowAlgorithm):
    def after_tool_call(self, ctx: ContextWindowRunContext) -> None:
        ctx.upsert(TextContextItem(primitive_id="tool:last", title="Last Tool", content="..."))
```

**Response:**

```python
# The item is rendered into the active context window on the next model call.
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | `ctx.every(iterations=0)` raises `ValueError`. |
| N/A | `ctx.upsert(...)` without a primitive id raises `ValueError`. |
| N/A | Invalid placement raises `ValueError`. |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/trajectory-checkpoint-inner-loop-context-window.md` | Design doc for revised PR #94 architecture |
| CREATE | `vidbyte/context/runtime.py` | Inner-loop context-window lifecycle contracts and run context |
| CREATE | `vidbyte/context/algorithms/trajectory_checkpoints.py` | Public trajectory checkpoint algorithm config and lifecycle behavior |
| CREATE | `vidbyte/lib/templates/trajectory_checkpoints.py` | Template for checkpoint recorder slots |
| CREATE | `tests/test_inner_context_window_algorithms.py` | Lifecycle/run-context/placement tests |
| CREATE | `tests/test_trajectory_checkpoint_algorithm.py` | Public API and runtime trajectory checkpoint tests |
| CREATE | `scripts/test-trajectory-checkpoints.py` | Executable verification script for all Section 10 cases |
| MODIFY | `README.md` | Document trajectory checkpoint preset |
| MODIFY | `skills/vidbyte-sdk/adding-context-window-algorithms.md` | Document standard inner-loop context updates |
| MODIFY | `skills/vidbyte-sdk/context-window-templates.md` | Document trajectory checkpoint slots |
| MODIFY | `vidbyte/__init__.py` | Export public algorithm, run context types, placement enum, and context item |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export trajectory runtime symbols if needed by dispatcher/tests |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Detect inner-loop context-window algorithms |
| MODIFY | `vidbyte/agents/runtime.py` | Dispatch generic inner-loop lifecycle hooks and render placed context |
| MODIFY | `vidbyte/context/__init__.py` | Export public algorithm and runtime context contracts |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export trajectory checkpoint algorithm |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add trajectory checkpoint field and exclusivity validation |
| MODIFY | `vidbyte/context/manager.py` | Add placement-aware upsert/rendering |
| MODIFY | `vidbyte/context/presets.py` | Add trajectory checkpoints preset |
| MODIFY | `vidbyte/context/primitives.py` | Add `TrajectoryCheckpointContextItem` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentIterationSnapshot` |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export new context item and snapshot |
| MODIFY | `vidbyte/lib/templates/__init__.py` | Export trajectory checkpoint template |
| MODIFY | `tests/test_agent_runtime.py` | Add generic lifecycle integration regression tests |
| MODIFY | `tests/test_context_primitives_registry.py` | Add placement rendering tests |
| MODIFY | `tests/test_context_primitives_binding.py` | Preserve existing primitive binding behavior with placement defaults |
| MODIFY | `tests/test_context_window_templates.py` | Add trajectory checkpoint template tests |

Summary: 7 files created, 20 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_inner_context_window_algorithms.py` -> `test_run_context_upsert_writes_to_context_manager` [Hidden Failure]
- `tests/test_inner_context_window_algorithms.py` -> `test_run_context_append_generates_stable_primitive_id` [Silent Failure]
- `tests/test_inner_context_window_algorithms.py` -> `test_run_context_remove_deletes_primitive` [Edge Case]
- `tests/test_inner_context_window_algorithms.py` -> `test_run_context_record_delegates_to_recorder` [Hidden Failure]
- `tests/test_inner_context_window_algorithms.py` -> `test_run_context_set_metadata_preserves_existing_keys` [Silent Failure]
- `tests/test_inner_context_window_algorithms.py` -> `test_run_context_every_rejects_zero_iterations` [Edge Case]
- `tests/test_inner_context_window_algorithms.py` -> `test_run_context_every_false_without_iteration_snapshot` [Hidden Assumption]
- `tests/test_inner_context_window_algorithms.py` -> `test_inner_algorithm_default_hooks_are_noops` [Hidden Assumption]
- `tests/test_context_primitives_registry.py` -> `test_upsert_default_placement_matches_existing_rendering` [Hidden Assumption]
- `tests/test_context_primitives_registry.py` -> `test_top_of_context_renders_before_end_of_context` [Silent Failure]
- `tests/test_context_primitives_registry.py` -> `test_replacing_primitive_updates_placement` [Silent Failure]
- `tests/test_context_primitives_registry.py` -> `test_remove_by_id_removes_placement_metadata` [Hidden Failure]
- `tests/test_context_primitives_registry.py` -> `test_conversation_placement_does_not_render_in_primitives_zone` [Hidden Failure]
- `tests/test_context_primitives_registry.py` -> `test_conversation_messages_render_in_placement_order` [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_preset_exposes_trajectory_checkpoint_algorithm` [Hidden Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_resolve_algorithm_accepts_trajectory_checkpoints_string` [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_rejects_zero_interval` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_rejects_empty_checkpoint_title` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_rejects_non_string_metadata_key` [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_context_window_algorithm_rejects_multiple_runtime_algorithms` [Hidden Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_checkpoint_item_outputs_required_sections_in_order` [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_checkpoint_item_bounds_rendered_text` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_score_disabled_renders_na` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_score_heuristic_penalizes_failed_tool_calls` [Silent Failure]
- `tests/test_context_window_templates.py` -> `test_trajectory_template_zero_iterations` [Edge Case]
- `tests/test_context_window_templates.py` -> `test_trajectory_template_interval_two` [Silent Failure]
- `tests/test_context_window_templates.py` -> `test_trajectory_template_respects_max_checkpoints` [Edge Case]

### Integration Tests

- `tests/test_agent_runtime.py` -> `test_inner_context_window_lifecycle_runs_without_algorithm_specific_runtime_logic` [Hidden Failure]
- `tests/test_agent_runtime.py` -> `test_inner_context_window_private_manager_created_when_missing` [Hidden Assumption]
- `tests/test_agent_runtime.py` -> `test_inner_context_window_uses_caller_context_manager_when_present` [Hidden Assumption]
- `tests/test_agent_runtime.py` -> `test_context_window_end_placement_visible_on_next_model_call` [Silent Failure]
- `tests/test_agent_runtime.py` -> `test_context_window_conversation_top_placement_visible_before_existing_messages` [Silent Failure]
- `tests/test_agent_runtime.py` -> `test_after_tool_call_lifecycle_receives_tool_result` [Hidden Failure]
- `tests/test_agent_runtime.py` -> `test_after_iteration_lifecycle_not_called_to_write_after_is_done` [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_writes_checkpoint_primitive_after_interval` [Integration]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_does_not_write_checkpoint_before_interval` [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_metadata_reports_zero_checkpoints_for_early_finish` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_respects_max_checkpoints` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_checkpoint_metadata_preserves_normal_metadata` [Hidden Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_checkpoint_omits_raw_tool_output_by_default` [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_checkpoint_can_include_bounded_tool_output_when_enabled` [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_slots_match_template` [Hidden Failure]

### Manual / QA Test Cases

1. Given `ContextWindow.preset.trajectory_checkpoints`, when two non-final iterations complete with `interval=2`, then the next runner call includes a `TrajectoryCheckpointContextItem` rendered by the context manager. [Integration]
2. Given no caller-provided `ContextManager`, when trajectory checkpoints are active, then runtime still writes and renders checkpoints through a private manager. [Hidden Assumption]
3. Given `interval=3`, when the agent finishes through `isDone` after two iterations, then no checkpoint is written after final completion. [Silent Failure]
4. Given `placement=TOP_OF_CONTEXT`, when another default primitive exists, then the checkpoint appears before the default primitive in the context primitives zone. [Silent Failure]
5. Given a long raw tool output and `include_tool_outputs=False`, checkpoint text excludes raw output while runtime metadata still retains tool-call audit data. [Hidden Assumption]
6. Given the verification script, when run from the repo root, then it prints `PASS` for every Section 10 test and exits `0`. [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `dataclasses` | Python >=3.11 | Immutable config/context/item dataclasses | Existing dependency only |
| Python stdlib `enum` | Python >=3.11 | Lifecycle event and placement enums | Existing dependency only |
| Python stdlib `typing` / `collections.abc` | Python >=3.11 | Protocols, mappings, callables, sequences | Existing dependency only |
| pydantic | `>=2,<3` | Existing SDK dependency; no new use | No new risk |

No new third-party dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- No feature flag is required; default behavior is unchanged unless the trajectory checkpoint preset is selected.
- This is a backward-compatible SDK feature if placement defaults preserve current `ContextManager.upsert(item)` behavior.
- Existing PR #94 should be updated or replaced from a fresh worktree branch after this design is approved.
- Rollout order: commit design doc, implement generic inner-loop context-window API, update context manager placement support, add trajectory checkpoint primitive and algorithm, wire preset/exports/dispatcher/runtime, add tests, update docs/skill, add verification script.
- Rollback: revert the feature branch merge commit. This removes the preset, inner-loop lifecycle contracts, placement support, trajectory primitive, tests, script, and docs.

---

## 13. Open Questions

- [ ] Should `TOP_OF_CONVERSATION` and `END_OF_CONVERSATION` be included in this PR, or should this PR only support context-zone placements and reserve conversation placement for a follow-up?
- [ ] Should `ContextWindowRunContext.append(...)` generate ids with a caller-provided namespace, or should algorithms always provide primitive ids explicitly?
- [ ] Should lifecycle hook exceptions fail the run directly, or should runtime convert them into an `AgentResult` with `stop_reason="context_window_error"`?
- [ ] Should trajectory checkpoints keep only the latest checkpoint primitive by default, or retain up to `max_checkpoints` visible primitives?
- [ ] Should `TrajectoryCheckpointAlgorithm` be both the public config and the inner-loop lifecycle implementation, or should it own a separate runtime state object per run to avoid storing mutable state on a frozen config?

---

## 14. Alternatives Considered

### Alternative 1: Keep PR #94 `iteration_observer`

- What: Pass `iteration_observer: Callable[[AgentIterationSnapshot], str | None]` into `_arun_once(...)` and append returned text to provider messages.
- Why rejected: It creates a separate callback/message mutation path instead of a standard context-window update interface, and it bypasses the existing `ContextManager` primitive model.

### Alternative 2: Use Middleware For Context Mutation

- What: Extend middleware decisions so `after_iteration` can append model-visible context.
- Why rejected: Middleware currently owns runtime control policy, not context-window rendering. Adding prompt mutation effects to middleware would blur responsibilities and make context algorithms depend on cross-cutting policy machinery.

### Alternative 3: Expose A Model-Called `write_context` Tool

- What: Let the model call a tool to write trajectory checkpoints into context.
- Why rejected: Checkpoint cadence and content must be deterministic and based on runtime-observed state. A model-called tool can skip, over-call, or write malformed/self-reported checkpoints.

### Alternative 4: Algorithm Calls A Tool Internally

- What: Have the context-window algorithm invoke an internal write-context tool after each interval.
- Why rejected: If the algorithm is already running at a lifecycle point, invoking a tool is unnecessary indirection. The algorithm can write a typed context item directly into `ContextManager`.

### Alternative 5: Duplicate `_arun_once(...)` Inside Trajectory Algorithm

- What: Copy the direct agent loop into the trajectory checkpoint runtime adapter.
- Why rejected: This would duplicate provider formatting, middleware, permissions, tracing, `isDone`, token accounting, and tool result admission, making regressions likely.
