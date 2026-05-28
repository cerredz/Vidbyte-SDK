# Design Doc: Context Window Primitives

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

Context window primitives are window-resident, addressable, named documents that persist across every turn of an agent's agentic loop. Unlike the existing `ContextItem` primitives (which are one-shot input data shapes collapsed into `StrategyContext.artifacts` at construction time), managed primitives live in a fixed, dedicated zone of the context window — after the system prompt and tools, before the agent loop — and can be created, updated, or removed both by developers before runtime and by agents during runtime via tool calls. A tool-primitive binding mechanism lets specific tool executions route their output directly into a named primitive, keeping the agent loop clean.

---

## 2. Goals & Non-Goals

### Goals
- Define a fixed, ordered context window format: system prompt → tools → primitives zone → agent loop
- Add `primitive_id` and `primitive_frozen` fields to all concrete primitive types for addressability and protection
- Upgrade `ContextManager` from an ordered tuple to a dict-backed registry with `upsert`, `get_by_id`, `remove_by_id`, and `render_primitives_zone()`
- Add `render_primitives_zone()` output to the system string in `AgentRuntime` between the fixed header and the agent loop body
- Add `binds_to_primitive: str | None` to `ToolSpec` so bound tool outputs route into a primitive in-place instead of appending raw to the agent loop
- Add a new `PlanContextItem` primitive type for algorithm-owned plan documents
- Ship three builtin agent tools: `context_upsert`, `context_remove`, `context_list`
- Keep all existing `ContextManager.add/extend/to_context()` behavior fully backward compatible

### Non-Goals
- Automatic primitive creation from arbitrary agent-generated schemas (deferred: agent creating novel primitive types not in the SDK)
- Token budget enforcement or eviction policy for the primitives zone
- Persistent cross-run primitive storage or serialization
- Changes to `ContextWindowAlgorithm` — algorithms continue to control only the agent loop zone (zone 4)
- Drift detection between primitives and the codebase (8090-style Knowledge Graph)

---

## 3. Background & Context

The existing `ContextItem`/`ContextManager` system is a one-shot input layer. Developers construct items, add them to a manager, and the manager collapses them into `StrategyContext.artifacts` once at the start of a run. There is no addressability (no `id`), no lifecycle (items cannot be updated in-place), and no guaranteed position in the context string (everything is flattened into artifacts). The `BaseContext.build_context()` rendering order is also incorrect for the desired format — it interleaves tools, memory, and artifacts without a fixed zone structure.

The desired architecture — informed by the SkillOpt paper's fast/slow state split and 8090's document-centric knowledge graph — requires primitives to be:
1. **Window-resident**: rendered from the registry on every turn, not just at construction
2. **Addressable**: each primitive has a stable `primitive_id` so it can be found and updated
3. **Positioned**: primitives always appear after system prompt and tools, before the agent loop
4. **Agent-accessible**: agents can create and update primitives via tool calls
5. **Tool-bound**: specific tools can route their output into a named primitive rather than the agent loop

The `AgentRuntime` already has a clean separation between context-building (`build_context()`) and per-iteration call construction (`_build_iteration_call_options()`), which is the right seam to inject primitive zone rendering.

---

## 4. Requirements

### Functional Requirements

1. Every concrete primitive type (`TextContextItem`, `FileContextItem`, `GitDiffContextItem`, `TaskContextItem`, `DocumentContextItem`, `EnvironmentContextItem`, `MemoryContextItem`, `ProgressContextItem`, `ArtifactContextItem`, `ResponseContextItem`, `ToolCallContextItem`) must accept `primitive_id: str | None = None` and `primitive_frozen: bool = False` optional fields.
2. A new `PlanContextItem` primitive type must be added to `vidbyte/context/primitives.py`.
3. `ContextManager` must expose `upsert(item)`, `get_by_id(id)`, `remove_by_id(id)`, and `render_primitives_zone()`. Items with a `primitive_id` go into an internal `_registry: dict[str, ContextItem]`. Items without `primitive_id` continue to use the existing `_items` list.
4. `upsert(item)` must refuse to overwrite an existing primitive that has `primitive_frozen=True` and must raise `ValueError` in that case.
5. `render_primitives_zone()` must return a formatted string block of all registry items in insertion order, or an empty string when the registry is empty.
6. `BaseContext` must expose two new methods: `build_context_fixed()` (renders system_prompt + tools) and `build_context_body()` (renders all other fields). The existing `build_context()` must continue to return the full string for backward compatibility but must reorder its sections to: system_prompt → tools → memory → history → metadata → budget → artifacts → responses → tool_calls → context_items → files.
7. `AgentRuntime` must store a `context_manager: ContextManager | None` reference and use it in `_build_iteration_call_options()` to inject `manager.render_primitives_zone()` between `build_context_fixed()` and `build_context_body()`.
8. `BaseAgent._runtime()` must pass `self.context_manager` to `AgentRuntime`.
9. `ToolSpec` must accept `binds_to_primitive: str | None = None`. When a tool with this field set executes successfully, `AgentRuntime._process_tool_call()` must call `context_manager.upsert()` with a `TextContextItem` carrying the tool output and the bound primitive id, and must set the model-visible tool result to a brief acknowledgment string instead of the raw output.
10. Three builtin tools — `ContextUpsertTool`, `ContextRemoveTool`, `ContextListTool` — must be implemented in `vidbyte/tools/builtins/context_primitives/`. They must operate on the `AgentRuntime`'s `context_manager`.
11. The three builtin tools must be accessible to agents via injection at agent construction time; they must not be auto-registered by default.
12. All new types must be exported from `vidbyte/context/__init__.py` and `vidbyte/__init__.py`.

### Non-Functional Requirements

- No import cycles introduced; all new imports follow the existing `vidbyte.context → vidbyte.lib → vidbyte.agents → vidbyte.tools` dependency direction
- All existing tests must continue to pass without modification
- New tests use the same `unittest.TestCase` pattern as the existing test suite
- New builtin tools follow the `BaseTool` + `ToolSpec` pattern used by `ContextCompactionTool`, `GlobTool`, etc.
- Backward compatibility: `ContextManager(items=[...])` and `manager.add()`, `manager.extend()`, `manager.to_context()` all continue to work exactly as before

---

## 5. High-Level Design

The implementation has five coordinated layers: primitive identity, registry-backed manager, split context rendering, runtime injection, and agent builtin tools.

**Primitive identity** adds two optional fields (`primitive_id`, `primitive_frozen`) to all existing concrete types. A new `PlanContextItem` is added for plan-and-execute algorithm use. No Protocol changes — `ContextItem` remains structural and backward compatible.

**Registry-backed ContextManager** adds a `_registry: dict[str, ContextItem]` alongside the existing `_items` list. Primitives with an id go into the registry; primitives without continue to use `_items`. The existing public API (`add`, `extend`, `remove`, `clear`, `items`, `by_kind`, `to_context`) is unchanged in behavior. `to_context()` processes `_items` only, as before. The new `upsert/get_by_id/remove_by_id/render_primitives_zone` API manages the registry.

**Split context rendering** splits `BaseContext.build_context()` into `build_context_fixed()` (system_prompt + tools) and `build_context_body()` (everything else), with `build_context()` still returning the full concatenation. The section order in `build_context()` is corrected to put tools before memory and other body fields.

**Runtime injection** threads the `ContextManager` reference through `BaseAgent._runtime()` into `AgentRuntime`. In `_build_iteration_call_options()`, the system string is assembled as: `fixed + primitives_zone + body`. This happens on every iteration, so primitive updates made by tool calls are visible on the very next model turn.

**Agent builtin tools** give the agent structured access to the primitives registry via `context_upsert`, `context_remove`, and `context_list`. They hold a weak reference to the runtime's `ContextManager` and are injected at agent construction when the developer opts in.

```
System message layout (per iteration):
┌──────────────────────────────────────────┐
│ Zone 1: System Prompt                    │  ← build_context_fixed()
│ Zone 2: Tools                            │  ← build_context_fixed()
├──────────────────────────────────────────┤
│ Zone 3: Primitives                       │  ← manager.render_primitives_zone()
│   [task:main]   Task: Build auth         │
│   [plan:current] Step 1: ...             │
│   [file:auth.py] # auth.py content       │
├──────────────────────────────────────────┤
│ Zone 4: Agent Loop                       │  ← build_context_body()
│   Memory, History, Artifacts, Tool calls │
│   (shaped by ContextWindowAlgorithm)     │
└──────────────────────────────────────────┘
```

---

## 6. Detailed Design

### 6.1 Primitive Identity Fields (`vidbyte/context/primitives.py`)

**File(s):** `vidbyte/context/primitives.py`
**Type:** Modified

#### What it does
Adds `primitive_id: str | None = None` and `primitive_frozen: bool = False` to all eleven existing concrete primitive types and introduces `PlanContextItem`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class TaskContextItem:
    goal: str
    status: str = "pending"
    progress: str | None = None
    completed: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    deterministic_checks: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "task"
    title: str = "Task"
    primitive_id: str | None = None        # NEW
    primitive_frozen: bool = False          # NEW

@dataclass(frozen=True, slots=True)
class PlanContextItem:                     # NEW
    steps: tuple[str, ...] = ()
    current_step: int = 0
    status: str = "planning"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "plan"
    title: str = "Plan"
    primitive_id: str | None = None
    primitive_frozen: bool = False

    def to_context_text(self) -> str:
        # Renders plan steps with current_step marker
```

All eleven existing types get the same two new fields appended with defaults. No breaking changes.

#### Logic / Algorithm
1. Add `primitive_id: str | None = None` as the second-to-last field on every frozen dataclass
2. Add `primitive_frozen: bool = False` as the last field on every frozen dataclass
3. Implement `PlanContextItem.to_context_text()` to render numbered steps with a `→` marker on `current_step`
4. Add `PlanContextItem` to `__all__`

#### Edge Cases & Error Handling
- `primitive_id = ""` (empty string): treated as "no id" — an empty string and `None` are both considered "unmanaged". The manager's `upsert()` will raise if `primitive_id` is falsy.
- No validation of `primitive_id` format — any non-empty string is valid

---

### 6.2 Registry-Backed ContextManager (`vidbyte/context/manager.py`)

**File(s):** `vidbyte/context/manager.py`
**Type:** Modified

#### What it does
Adds a `_registry: dict[str, ContextItem]` alongside the existing items list, with `upsert`, `get_by_id`, `remove_by_id`, and `render_primitives_zone()` methods.

#### Interface / API
```python
@dataclass(slots=True)
class ContextManager:
    context_items: Sequence[ContextItem] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    # _registry is NOT in __init__ — it's a post_init-initialized dict

    def upsert(self, item: ContextItem) -> "ContextManager":
        # Adds or replaces a primitive by its primitive_id.
        # Raises ValueError if primitive_id is falsy.
        # Raises ValueError if existing primitive has primitive_frozen=True.

    def get_by_id(self, primitive_id: str) -> ContextItem | None:
        # Returns the primitive with the given id, or None.

    def remove_by_id(self, primitive_id: str) -> "ContextManager":
        # Removes the primitive with the given id; no-op if missing.

    def render_primitives_zone(self) -> str:
        # Returns formatted block of all registry items in insertion order.
        # Returns "" if the registry is empty.

    # Existing API — unchanged:
    def add(self, item: ContextItem) -> "ContextManager": ...
    def extend(self, items: Iterable[ContextItem]) -> "ContextManager": ...
    def remove(self, item: ContextItem) -> "ContextManager": ...
    def clear(self) -> "ContextManager": ...
    def items(self) -> tuple[ContextItem, ...]: ...
    def by_kind(self, kind: str) -> tuple[ContextItem, ...]: ...
    def to_context(self, base_context: BaseContext | None = None, **overrides) -> StrategyContext: ...
```

#### Logic / Algorithm
1. `__post_init__` initializes `_registry: dict[str, ContextItem] = {}` as an instance attribute (not a dataclass field, to keep `__init__` backward compatible)
2. `upsert(item)`:
   a. Check `item.primitive_id` is truthy; raise `ValueError("primitive_id must be a non-empty string")` if not
   b. Check `hasattr(item, 'primitive_id')` — raises `TypeError` if item doesn't have the field
   c. If `primitive_id` already in `_registry` and existing item has `primitive_frozen=True`, raise `ValueError(f"Primitive '{id}' is frozen and cannot be overwritten")`
   d. Store `_registry[item.primitive_id] = item`
   e. Return `self`
3. `get_by_id(id)`: return `_registry.get(id)`
4. `remove_by_id(id)`: pop from `_registry`, return `self`
5. `render_primitives_zone()`:
   a. If `_registry` is empty, return `""`
   b. Build header `"## Context Window Primitives"`
   c. For each item in `_registry.values()`, render as `f"### [{item.primitive_id}] {item.title}\n{item.to_context_text()}"`
   d. Return joined sections
6. `items()` continues to return only `_items` (unmanaged primitives) — registry items do NOT appear in `items()` to avoid double-processing by `to_context()`

#### Edge Cases & Error Handling
- `upsert()` called with item missing `primitive_id` attribute: raises `TypeError` with clear message
- `remove_by_id()` on non-existent id: silent no-op, returns `self`
- `render_primitives_zone()` with empty registry: returns `""` — the runtime detects this and skips injection
- `clear()` does NOT clear the registry — registry items are managed separately. A `clear_registry()` method is added for completeness.

---

### 6.3 BaseContext Split Rendering (`vidbyte/lib/dataclasses/context.py`)

**File(s):** `vidbyte/lib/dataclasses/context.py`
**Type:** Modified

#### What it does
Adds `build_context_fixed()` and `build_context_body()` methods to `BaseContext`. Updates the section order in `build_context()` to correctly position tools before body content.

#### Interface / API
```python
class BaseContext:
    def build_context_fixed(self) -> str:
        # Renders ONLY system_prompt and tools — zones 1 and 2.
        # Used by AgentRuntime to build the fixed header before primitives.

    def build_context_body(self) -> str:
        # Renders everything except system_prompt and tools — zone 4.
        # Includes: memory, history, metadata, budget, artifacts,
        # responses, tool_calls, context_items, files.

    def build_context(self) -> str:
        # Full rendering: build_context_fixed() + build_context_body().
        # Backward compatible — existing callers work unchanged.
```

#### Logic / Algorithm
1. `build_context_fixed()`:
   - Append system_prompt section if present
   - Append tools section if present (using `_format_context_tool`)
   - Return `"\n\n".join(parts)`
2. `build_context_body()`:
   - Append memory, history, metadata, budget, artifacts, responses, tool_calls, context_items, files
   - Return `"\n\n".join(parts)`
3. `build_context()`: return `"\n\n".join(filter(None, [self.build_context_fixed(), self.build_context_body()]))`
   - This preserves the existing return value exactly for contexts with no primitives zone

#### Edge Cases & Error Handling
- If both `build_context_fixed()` and `build_context_body()` return empty strings: `build_context()` returns `""`
- No change to `_build_file_context()` — it remains part of `build_context_body()`

---

### 6.4 AgentRuntime Primitives Injection (`vidbyte/agents/runtime.py`)

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Threads the `ContextManager` reference into `AgentRuntime`, injects the primitives zone on every iteration, and handles tool-primitive binding in `_process_tool_call()`.

#### Interface / API
```python
class AgentRuntime:
    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        tools: Tools,
        permission_policy: PermissionPolicy,
        config: AgentRuntimeConfig | None = None,
        tracer: TracerBase | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        run_id: str | None = None,
        algorithm: ContextWindowAlgorithm | str | None = None,
        context_manager: ContextManager | None = None,   # NEW
    ) -> None: ...

    def _build_iteration_call_options(
        self,
        run_options: dict[str, Any],
        context: BaseAgentContext,
        tool_schemas: Sequence[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]: ...
    # Modified: assembles system string as fixed + primitives_zone + body

    async def _process_tool_call(self, ...) -> ...: ...
    # Modified: after execution, if spec.binds_to_primitive is set,
    # upserts a TextContextItem into context_manager and overrides visible_result
```

#### Logic / Algorithm

**`__init__` change:**
- Add `self.context_manager: ContextManager | None = context_manager`

**`_build_iteration_call_options` change:**
```
1. Build: fixed = context.build_context_fixed()
2. Build: body = context.build_context_body()
3. If self.context_manager is not None:
     primitives_zone = self.context_manager.render_primitives_zone()
   Else:
     primitives_zone = ""
4. system_parts = [p for p in (fixed, primitives_zone, body) if p]
5. system = "\n\n".join(system_parts)
6. call_options.setdefault("system", system)
```

**`_process_tool_call` change (after executing the tool):**
```
After call to execute_tool_call():
1. Get tool spec: spec = self.tools._get(call.tool_name).spec()
2. If spec.binds_to_primitive is not None and context_record.state == SUCCEEDED:
     a. Build TextContextItem(
            primitive_id=spec.binds_to_primitive,
            title=f"Tool: {call.tool_name}",
            content=result.output,
            source=call.tool_name,
        )
     b. If self.context_manager is not None:
            try:
                self.context_manager.upsert(new_item)
            except ValueError:
                pass  # frozen primitive — don't override, let raw result through
     c. Override visible_result output to:
            f"[Output of '{call.tool_name}' stored in primitive '{spec.binds_to_primitive}']"
```

#### Edge Cases & Error Handling
- `context_manager` is `None`: existing behavior, no primitives zone injected
- `render_primitives_zone()` returns `""`: not added to system string (filtered by `if p`)
- `binds_to_primitive` points to a frozen primitive: `upsert()` raises `ValueError`, which is caught; the raw tool result is used instead of the acknowledgment
- Tool execution fails: binding is skipped — only successful results are routed to primitives
- `_get` raises (tool not in catalog): this can't happen in `_process_tool_call` because `_get_tool` already resolved it successfully earlier

---

### 6.5 BaseAgent Runtime Pass-Through (`vidbyte/agents/base.py`)

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
Passes `self.context_manager` to `AgentRuntime` in `_runtime()`.

#### Interface / API
```python
def _runtime(self) -> AgentRuntime:
    return AgentRuntime(
        agent_name=self.name,
        system_prompt=self.system_prompt,
        tools=self.tools,
        permission_policy=self.permission_policy,
        config=self.runtime_config,
        tracer=self._tracer,
        middleware=self.middleware,
        run_id=self.runner_config.run_id,
        algorithm=self.algorithm,
        context_manager=self.context_manager,  # NEW
    )
```

#### Logic / Algorithm
One-line change: add `context_manager=self.context_manager` to the `AgentRuntime(...)` call.

#### Edge Cases & Error Handling
N/A — `context_manager` may be `None`, which `AgentRuntime` handles gracefully.

---

### 6.6 ToolSpec Primitive Binding (`vidbyte/lib/dataclasses/tools.py`)

**File(s):** `vidbyte/lib/dataclasses/tools.py`
**Type:** Modified

#### What it does
Adds `binds_to_primitive: str | None = None` to `ToolSpec`.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = ()
    permission: ToolPermission = ToolPermission.SAFE
    metadata: Mapping[str, Any] = field(default_factory=dict)
    input_schema: Mapping[str, Any] | None = None
    binds_to_primitive: str | None = None   # NEW
```

#### Logic / Algorithm
Single field addition with `None` default. No other changes.

#### Edge Cases & Error Handling
- Existing `ToolSpec` construction without `binds_to_primitive` works unchanged
- `to_prompt_str()` does not render `binds_to_primitive` — it is runtime-only metadata

---

### 6.7 Context Primitive Builtin Tools (`vidbyte/tools/builtins/context_primitives/`)

**File(s):**
- `vidbyte/tools/builtins/context_primitives/__init__.py` (new)
- `vidbyte/tools/builtins/context_primitives/upsert.py` (new)
- `vidbyte/tools/builtins/context_primitives/remove.py` (new)
- `vidbyte/tools/builtins/context_primitives/list_tool.py` (new)

**Type:** New files

#### What it does
Three builtin tools that give agents structured access to the `ContextManager` registry. They hold a reference to the manager set at agent construction or runtime injection.

#### Interface / API
```python
class ContextUpsertTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None:
        # Stores reference to the live manager.

    def spec(self) -> ToolSpec:
        # Returns ToolSpec with parameters: primitive_id (str, required),
        # primitive_type (str, optional, default "text"),
        # content (str, required), title (str, optional).

    async def execute(self, call: ToolCall) -> ToolResult:
        # Creates or updates a primitive in the manager.
        # Supported types: "text", "task", "plan", "document", "memory", "progress".
        # Returns success with the primitive_id and current content summary.

class ContextRemoveTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...

    def spec(self) -> ToolSpec:
        # Parameters: primitive_id (str, required).

    async def execute(self, call: ToolCall) -> ToolResult:
        # Removes the primitive; returns success even if not found (idempotent).

class ContextListTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...

    def spec(self) -> ToolSpec:
        # No parameters.

    async def execute(self, call: ToolCall) -> ToolResult:
        # Returns formatted list of all primitives: id, type, title, char count.
```

#### Logic / Algorithm

**`ContextUpsertTool.execute()`:**
1. Extract `primitive_id`, `primitive_type` (default `"text"`), `content`, `title` from `call.arguments`
2. Build the appropriate primitive instance based on `primitive_type`:
   - `"text"` → `TextContextItem(primitive_id=..., title=..., content=...)`
   - `"task"` → `TaskContextItem(primitive_id=..., goal=content)`
   - `"plan"` → `PlanContextItem(primitive_id=..., steps=tuple(content.splitlines()))`
   - `"document"` → `DocumentContextItem(primitive_id=..., source="agent", content=...)`
   - `"memory"` → `MemoryContextItem(primitive_id=..., content=...)`
   - `"progress"` → `ProgressContextItem(primitive_id=...)`
   - Unknown type → `ToolResult.error()`
3. Call `self._manager.upsert(item)`; if `ValueError` (frozen), return `ToolResult.error()` with message
4. Return `ToolResult.success()` with `f"Primitive '{primitive_id}' upserted successfully."`

**`ContextRemoveTool.execute()`:**
1. Extract `primitive_id` from `call.arguments`
2. Call `self._manager.remove_by_id(primitive_id)` (no-op if missing)
3. Return `ToolResult.success()` with `f"Primitive '{primitive_id}' removed."`

**`ContextListTool.execute()`:**
1. If `self._manager._registry` is empty, return `ToolResult.success("No active context primitives.")`
2. For each `(id, item)` in `self._manager._registry.items()`, render a one-line summary: `f"[{id}] ({item.kind}) {item.title} — {len(item.to_context_text())} chars"`
3. Return `ToolResult.success("\n".join(lines))`

#### Edge Cases & Error Handling
- `primitive_type` not in supported set: `ToolResult.error("Unknown primitive_type: {type}. Supported: text, task, plan, document, memory, progress.")`
- `upsert` on frozen primitive: `ToolResult.error("Primitive '{id}' is frozen and cannot be updated.")`
- `content` argument missing for types that require it: `BaseTool.validate_call()` catches this via `required_parameter_names()`

---

### 6.8 Export Updates (`vidbyte/context/__init__.py`, `vidbyte/__init__.py`, `vidbyte/tools/builtins/__init__.py`)

**Type:** Modified

- `vidbyte/context/__init__.py`: add `PlanContextItem` import and export
- `vidbyte/__init__.py`: add `PlanContextItem`, `ContextUpsertTool`, `ContextRemoveTool`, `ContextListTool`
- `vidbyte/tools/builtins/__init__.py`: add imports from `context_primitives`

---

## 7. Data Model Changes

### 7.1 ContextItem Concrete Types

**Change type:** Modified (backward compatible field additions)

All eleven existing frozen dataclasses gain two trailing optional fields:
```python
primitive_id: str | None = None
primitive_frozen: bool = False
```

Since these fields have defaults and are appended to the end of each dataclass definition, all existing construction code continues to work unchanged (positional args unaffected, keyword args unaffected).

**Migration strategy:** N/A — no persistent storage; fields are in-memory only.

### 7.2 PlanContextItem (New)

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class PlanContextItem:
    steps: tuple[str, ...] = ()
    current_step: int = 0
    status: str = "planning"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "plan"
    title: str = "Plan"
    primitive_id: str | None = None
    primitive_frozen: bool = False
```

### 7.3 ToolSpec

**Change type:** Modified (backward compatible field addition)

```python
binds_to_primitive: str | None = None
```

Appended with `None` default. Existing `ToolSpec` construction unchanged.

### 7.4 ContextManager Internal State

**Change type:** Modified (internal only, not part of dataclass signature)

New internal `_registry: dict[str, ContextItem]` initialized in `__post_init__`. Not a dataclass field — does not appear in `__init__`, `__repr__`, or `__eq__`. Existing public API unchanged.

---

## 8. API Changes

N/A — This feature is internal SDK infrastructure, not an HTTP API layer.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-window-primitives.md` | This design doc |
| MODIFY | `vidbyte/context/primitives.py` | Add `primitive_id`, `primitive_frozen` to all 11 types; add `PlanContextItem` |
| MODIFY | `vidbyte/context/manager.py` | Add `_registry`, `upsert`, `get_by_id`, `remove_by_id`, `render_primitives_zone`, `clear_registry` |
| MODIFY | `vidbyte/context/__init__.py` | Export `PlanContextItem` |
| MODIFY | `vidbyte/lib/dataclasses/context.py` | Add `build_context_fixed()`, `build_context_body()`; reorder `build_context()` sections |
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | Add `binds_to_primitive: str | None = None` to `ToolSpec` |
| MODIFY | `vidbyte/agents/runtime.py` | Add `context_manager` param; modify `_build_iteration_call_options`; modify `_process_tool_call` for binding |
| MODIFY | `vidbyte/agents/base.py` | Pass `context_manager=self.context_manager` in `_runtime()` |
| CREATE | `vidbyte/tools/builtins/context_primitives/__init__.py` | Package init + exports |
| CREATE | `vidbyte/tools/builtins/context_primitives/upsert.py` | `ContextUpsertTool` |
| CREATE | `vidbyte/tools/builtins/context_primitives/remove.py` | `ContextRemoveTool` |
| CREATE | `vidbyte/tools/builtins/context_primitives/list_tool.py` | `ContextListTool` |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export `ContextUpsertTool`, `ContextRemoveTool`, `ContextListTool` |
| MODIFY | `vidbyte/__init__.py` | Export `PlanContextItem`, `ContextUpsertTool`, `ContextRemoveTool`, `ContextListTool` |
| CREATE | `tests/test_context_primitives_registry.py` | Unit tests for registry, upsert, frozen enforcement, rendering |
| CREATE | `tests/test_context_primitives_binding.py` | Unit tests for tool-primitive binding in AgentRuntime |
| CREATE | `tests/test_context_primitives_builtins.py` | Unit tests for the three builtin tools |
| CREATE | `scripts/test_context_window_primitives.py` | Verification script for all test cases |

---

## 10. Testing Plan

### Unit Tests

#### `tests/test_context_primitives_registry.py`

- `test_primitive_id_field_defaults_to_none` — all 12 concrete types have `primitive_id=None` by default — [Hidden Assumption]
- `test_primitive_frozen_field_defaults_to_false` — all 12 types have `primitive_frozen=False` by default — [Hidden Assumption]
- `test_upsert_adds_new_primitive_by_id` — `manager.upsert(TaskContextItem(primitive_id="t1", goal="x"))` puts item in registry — [Edge Case]
- `test_upsert_replaces_existing_primitive_by_id` — second upsert with same id replaces, registry stays size 1 — [Silent Failure]
- `test_upsert_preserves_insertion_order_for_new_ids` — three upserts with different ids maintain order in `render_primitives_zone()` — [Silent Failure]
- `test_upsert_raises_on_frozen_primitive` — upsert with existing frozen=True raises `ValueError` — [Edge Case]
- `test_upsert_allows_overwrite_of_non_frozen_primitive` — upsert on non-frozen existing item succeeds — [Hidden Assumption]
- `test_upsert_raises_on_empty_primitive_id` — `upsert(item)` where `item.primitive_id=""` raises `ValueError` — [Edge Case]
- `test_upsert_raises_on_none_primitive_id` — item without primitive_id set raises `ValueError` — [Edge Case]
- `test_get_by_id_returns_correct_item` — get after upsert returns the exact item — [Silent Failure]
- `test_get_by_id_returns_none_for_missing_id` — get on non-existent id returns `None` — [Edge Case]
- `test_remove_by_id_removes_item` — remove after upsert leaves registry empty — [Edge Case]
- `test_remove_by_id_is_idempotent` — remove on non-existent id does not raise — [Edge Case]
- `test_render_primitives_zone_returns_empty_string_for_empty_registry` — `""` when no items — [Edge Case]
- `test_render_primitives_zone_contains_primitive_id_and_title` — rendered output includes both id and title — [Silent Failure]
- `test_render_primitives_zone_contains_context_text` — rendered output includes `to_context_text()` content — [Silent Failure]
- `test_items_excludes_registry_items` — `manager.items()` does NOT return items added via `upsert()` — [Hidden Failure]
- `test_to_context_excludes_registry_items` — `to_context()` does not add registry items to artifacts or context_items — [Hidden Failure]
- `test_add_without_id_still_works` — `manager.add(TextContextItem(...))` with no id goes into `_items`, not registry — [Hidden Assumption]
- `test_build_context_fixed_contains_system_prompt_and_tools` — `build_context_fixed()` includes both zones — [Silent Failure]
- `test_build_context_body_excludes_system_prompt_and_tools` — body has artifacts but not system_prompt text — [Hidden Failure]
- `test_build_context_equals_fixed_plus_body` — `build_context()` equals `fixed + body` concatenation — [Silent Failure]
- `test_plan_context_item_renders_steps` — `PlanContextItem(steps=("a","b"), current_step=0).to_context_text()` contains "→ a" and "b" — [Silent Failure]

#### `tests/test_context_primitives_binding.py`

- `test_runtime_stores_context_manager` — constructing `AgentRuntime` with `context_manager=...` sets `self.context_manager` — [Hidden Assumption]
- `test_build_iteration_call_options_injects_primitives_zone` — when manager has a registered primitive, the system string contains the rendered zone text — [Silent Failure]
- `test_build_iteration_call_options_skips_empty_zone` — when manager registry is empty, system equals `build_context()` output — [Edge Case]
- `test_build_iteration_call_options_no_manager` — `context_manager=None` → system equals `build_context()` output — [Hidden Assumption]
- `test_tool_spec_accepts_binds_to_primitive` — `ToolSpec(name="x", description="y", binds_to_primitive="file:a")` stores the field — [Hidden Assumption]
- `test_tool_spec_binds_to_primitive_defaults_to_none` — existing ToolSpec construction without the field works — [Hidden Assumption]

#### `tests/test_context_primitives_builtins.py`

- `test_context_upsert_tool_creates_text_primitive` — call with type="text" creates TextContextItem in manager — [Edge Case]
- `test_context_upsert_tool_creates_plan_primitive` — call with type="plan" creates PlanContextItem — [Edge Case]
- `test_context_upsert_tool_overwrites_existing_primitive` — second call with same id replaces — [Silent Failure]
- `test_context_upsert_tool_errors_on_frozen_primitive` — call targeting frozen primitive returns ToolResult.error() — [Edge Case]
- `test_context_upsert_tool_errors_on_unknown_type` — type="unknown" returns ToolResult.error() — [Edge Case]
- `test_context_remove_tool_removes_existing_primitive` — primitive is gone after execute — [Edge Case]
- `test_context_remove_tool_is_idempotent` — calling on non-existent id returns success — [Edge Case]
- `test_context_list_tool_shows_all_primitives` — output contains id and kind for each registered item — [Silent Failure]
- `test_context_list_tool_empty_registry` — returns a no-primitives message, not empty string — [Edge Case]
- `test_context_upsert_tool_validates_required_params` — call without primitive_id returns validation error — [Hidden Assumption]

### Integration Tests

- `test_primitive_survives_across_iterations` — in a mock agentic loop, primitive upserted in iteration N is visible in the system string of iteration N+1 — [Hidden Failure]
- `test_bound_tool_routes_output_to_primitive` — tool with `binds_to_primitive` set: result stored in manager AND visible_result is the acknowledgment string, NOT the raw output — [Silent Failure]
- `test_bound_tool_frozen_falls_through_to_raw` — when bound primitive is frozen, the raw tool output appears in messages instead — [Hidden Failure]
- `test_full_primitives_zone_ordering` — system string section order is: fixed (system_prompt+tools) then primitives zone then body — [Silent Failure]
- `test_existing_context_management_tests_still_pass` — all 9 existing tests in `test_context_management.py` pass unmodified — [Hidden Assumption]

### Manual / QA Test Cases

1. Given an agent with `context_manager=ContextManager().upsert(TaskContextItem(primitive_id="t1", goal="Build auth", primitive_frozen=True))`, when the agent runs, then the system string rendered on each iteration contains `[t1]` in the primitives zone — [Silent Failure]

2. Given an agent with the three builtin tools added, when the agent calls `context_upsert` with `primitive_id="plan:current"`, type="plan"`, `content="Step 1: scaffold\nStep 2: implement"`, then on the next model call the primitives zone contains both steps — [Edge Case]

3. Given a tool defined with `binds_to_primitive="file:main"`, when the agent calls that tool, then the tool result message seen by the model reads "[Output of ... stored in primitive 'file:main']" and the manager registry contains a TextContextItem with that id — [Hidden Failure]

4. Given an agent calling `context_upsert` targeting a `primitive_frozen=True` primitive, then the tool returns an error result and the primitive content is unchanged — [Edge Case]

5. Given a `ContextManager` with 3 registered primitives and 2 unmanaged items added via `add()`, when `to_context()` is called, then `StrategyContext.artifacts` has entries for the 2 unmanaged items only, and the 3 registered items do NOT appear in artifacts — [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python | >=3.11 | `dict` insertion-order guarantee (3.7+), `slots=True` on dataclasses (3.10+) | None — already required |
| Pydantic | >=2,<3 | Not directly used by this feature | None |

No new dependencies added.

---

## 12. Rollout & Deployment

- No feature flags — this is additive (new optional fields with defaults, new optional constructor args)
- Not a breaking change — all existing `ContextManager`, `ContextItem`, `ToolSpec`, and `BaseContext` usages continue to work unchanged
- No deployment order constraints
- Rollback: revert the branch — no state is persisted outside the in-memory runtime

---

## 13. Open Questions

- [ ] **Algorithm-owned primitives**: When `PlanAndExecuteStrategy` creates a `PlanContextItem`, it needs access to the `ContextManager`. Should the strategy receive the manager via `arun(context=..., context_manager=...)`, or should the manager be attached to the `StrategyContext`? Deferred to a follow-up PR.
- [ ] **Agent-created novel primitive types**: R5 partially punts on "agent-created primitives not in the SDK." The `ContextUpsertTool` supports the six known types. How should an agent signal that it needs a new schema? Deferred per user direction.
- [ ] **Builtin tool auto-injection**: Should the three context primitive tools be auto-added to every agent with a `context_manager`, or always opt-in? Current design is opt-in. Worth revisiting once algorithm-owned primitives are designed.
- [ ] **`_registry` visibility in `items()`**: The decision to exclude registry items from `items()` preserves backward compat but means `by_kind()` does not search the registry. A `registry_items()` method could be added later.

---

## 14. Alternatives Considered

### Alternative 1: Add injection_point to primitives
- **What**: Give each primitive an `injection_point: Literal["system_suffix", "turn_prefix"]` field and render them in different message positions
- **Why rejected**: Adds per-primitive rendering complexity and requires the runtime to build multiple message blocks. The single fixed primitives zone (always in the system string) is simpler and still achieves the desired layout. Multiple injection points can be added later if needed.

### Alternative 2: StrategyContext carries the registry
- **What**: Add `primitives_registry: dict[str, ContextItem]` to `StrategyContext` and rebuild it each iteration
- **Why rejected**: `StrategyContext` is a frozen dataclass — it can't carry mutable state. Rebuilding a frozen dataclass each iteration just to update one dict would create garbage and break the registry identity guarantees needed for tool binding.

### Alternative 3: primitives_zone as a string field on BaseAgentContext
- **What**: Render the primitives zone once at context-build time and store it as a string in `BaseAgentContext`
- **Why rejected**: Primitives updated mid-run (via tool calls) would not appear until the next `build_context()` call — which never happens because `BaseAgentContext` is frozen and built only once per `generate_reply()`. The live manager reference is the only design that makes in-turn updates visible to the model.

### Alternative 4: Keep ContextManager as tuple, add separate ContextRegistry class
- **What**: Introduce a new `ContextRegistry` class and leave `ContextManager` unchanged
- **Why rejected**: Splits the manager/registry concepts across two objects that agents must pass around together. The single `ContextManager` holding both `_items` (unmanaged) and `_registry` (managed) keeps the developer API to one object.
