# Design Doc: Context Primitives Agent Sync

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

This feature promotes the existing context item foundation into first-version durable context primitives for agents. Developers will be able to seed an agent with typed primitives such as identity, task, plan, file, and progress objects; tools will be able to return primitive updates alongside normal tool output; and the direct agent runtime will keep those primitives synchronized, render model-visible primitives directly beneath the system prompt, and let context-window algorithms control primitive visibility and ordering without each tool or strategy inventing its own context shape.

---

## 2. Goals & Non-Goals

### Goals

- Add a public `context_primitives` agent construction option while preserving existing `context_items` and `context_manager` compatibility.
- Add first-class primitive metadata for stable IDs, placement, priority, and visibility.
- Add built-in `IdentityContextItem` and `PlanContextItem` primitives.
- Let `AgentInput` and `AgentSpec` accept `context_primitives` for per-call and construction-friendly primitive seeding.
- Add a typed primitive update contract that tools can return through `ToolResult`.
- Apply tool-returned primitive updates inside `AgentRuntime` so later model calls see the updated primitive store.
- Render model-visible sticky primitives near the top of the context window, directly after the system prompt and before history/tool-loop messages.
- Let `ContextWindowAlgorithm` perform default primitive admission: filter hidden primitives, sort by placement and priority, and preserve raw primitive data in runtime metadata.
- Keep the implementation additive and source-compatible for current `ContextItem`, `ContextManager`, `ToolResult`, `Agent`, `AgentInput`, and `AgentSpec` users.
- Add tests that prove agent-seeded primitives, per-call primitives, tool-returned updates, hidden primitive filtering, and top-of-window rendering work.
- Update README and SDK skill documentation with the approved primitive/store/update model.

### Non-Goals

- No persistent database or cross-session primitive storage.
- No vector retrieval, semantic ranking, tokenizer-based pruning, or automatic summarization.
- No autonomous task decomposition algorithm that creates tasks from arbitrary requests; this PR only creates the plumbing for future algorithms to do so.
- No full context renderer/compiler abstraction beyond the existing `BaseContext.build_context()` path.
- No breaking removal of `context_items`, `ContextItem`, or `ContextManager`.
- No automatic filesystem crawling, git inspection, or file content loading beyond explicit caller/tool behavior.
- No changes to pipeline semantics; pipelines remain string-oriented and do not own context primitives.
- No strategy-internal lifecycle hooks. This first version applies primitive sync to the direct text agent runtime.

---

## 3. Background & Context

The SDK already has a context-management foundation from PR #44. Public primitives live in `vidbyte/context/primitives.py`, `ContextManager` collects them in `vidbyte/context/manager.py`, and agents already accept `context_items` / `context_manager` in `BaseAgent`, `AgentInput`, and `AgentSpec`. `AgentRuntime.build_context(...)` merges agent-level and per-call context into `BaseAgentContext`.

The current foundation is useful, but it still behaves mostly like a compatibility bridge. `ContextManager.to_context(...)` maps primitives into legacy `StrategyContext` fields such as artifacts, memory, responses, and tool calls, and `BaseContext.build_context()` renders `context_items` late in the context after metadata, artifacts, responses, and tool calls. That is not yet the desired "durable working-memory objects near the top of the context window" model.

Tool results currently contain `tool_name`, `status`, `output`, and `metadata` only. `AgentRuntime._process_tool_call(...)` executes a tool, stores full tool-call context in metadata, asks the selected `ContextWindowAlgorithm` how much tool output should become model-visible, and appends the model-visible tool result into provider messages. This is the right layer to synchronize tool-returned primitives because it owns ordered provider messages, runtime metadata, tool-call contexts, and the repeated model loop.

The context-window algorithm surface currently controls tool-result admission and, in local feature work, also goal/harness prompt overlays. The intended next step is to let algorithms reason over typed primitive objects instead of only strings. This PR adds the minimal primitive admission path without trying to implement every future algorithm hook.

Repository audit summary:

- Language/runtime: Python >=3.11.
- Packaging: setuptools via `pyproject.toml`.
- Dependencies: `pydantic>=2,<3`; this feature does not need new dependencies.
- Tests: standard-library `unittest`, run with `python -m unittest discover -s tests`.
- Core agent runtime: `vidbyte/agents/base.py` and `vidbyte/agents/runtime.py`.
- Shared dataclasses: `vidbyte/lib/dataclasses/`.
- Context package: `vidbyte/context/`.
- Tool contracts: `vidbyte/lib/dataclasses/tools.py`, re-exported through `vidbyte/tools/types.py`.
- Public exports: root `vidbyte/__init__.py`, package `vidbyte/context/__init__.py`, and `vidbyte/lib/dataclasses/__init__.py`.

---

## 4. Requirements

### Functional Requirements

1. The SDK must expose `ContextPrimitive` as a public alias/protocol-compatible name for the existing `ContextItem` concept.
2. The SDK must expose `ContextPrimitivePlacement` with at least `STICKY`, `NORMAL`, and `EPHEMERAL`.
3. The SDK must expose `ContextPrimitiveVisibility` with at least `MODEL`, `METADATA_ONLY`, and `HIDDEN`.
4. Existing context item dataclasses must remain constructible with their current positional arguments.
5. Existing context item dataclasses must gain optional primitive metadata fields: `id`, `placement`, `priority`, and `visibility`, added after existing fields to preserve positional compatibility.
6. The SDK must add `IdentityContextItem` for role/behavior/personality/constraints that are model-visible but lower authority than the system prompt.
7. The SDK must add `PlanContextItem` for ordered task steps, current step, risks, and verification criteria.
8. `ContextManager` must support stable-ID upsert semantics for primitives with IDs.
9. `ContextManager` must support applying a sequence of primitive updates.
10. The SDK must expose a typed `ContextPrimitiveUpdate` contract with `UPSERT` and `REMOVE` actions.
11. `ToolResult` must accept `context_updates` so tools can return primitive mutations alongside normal output.
12. `ToolResult.success(...)`, `ToolResult.error(...)`, and `ToolResult.failure(...)` must accept optional `context_updates`.
13. `BaseAgent.__init__` must accept `context_primitives` as an alias for seeded context primitives.
14. `AgentInput` must accept `context_primitives` for per-call primitive seeding.
15. `AgentSpec` must accept `context_primitives` for construction-friendly primitive seeding.
16. If both `context_items` and `context_primitives` are supplied, the runtime must merge both in deterministic order: existing `context_items`, then `context_primitives`, then per-call items/primitives.
17. `AgentRuntime` must maintain a per-run primitive store derived from the built `BaseAgentContext.context_items`.
18. After each non-internal tool result, `AgentRuntime` must apply `ToolResult.context_updates` to the per-run primitive store.
19. The updated primitive store must be reflected in the `BaseAgentContext` used for subsequent model calls.
20. Runtime result metadata must expose the final primitive list and the primitive updates applied during the run.
21. `ContextWindowAlgorithm` must expose a default primitive admission method that filters out hidden primitives and sorts model-visible primitives by placement and priority.
22. `BaseContext.build_context()` must render admitted model-visible primitives immediately after the system prompt.
23. Hidden primitives must not appear in `BaseContext.build_context()` output.
24. Metadata-only primitives must be retained in context/runtime metadata but must not appear in model-visible context text.
25. Tool-result admission behavior (`RAW`, `COMPACT`, `HIDE_RAW`) must continue to work unchanged.
26. Public imports from `vidbyte`, `vidbyte.context`, and `vidbyte.lib.dataclasses` must include new primitive/update types.
27. README must show agent-seeded primitives and tool-returned primitive updates.
28. SDK skill docs must document when to use primitives, primitive updates, context managers, tools, and algorithms.

### Non-Functional Requirements

- Performance: primitive store operations must be linear in the number of explicitly supplied primitives and updates; no background IO or crawling is allowed.
- Scalability: first-version rendering must support bounded excerpts/metadata through primitive fields but will not implement tokenizer-aware pruning.
- Security: hidden and metadata-only primitives must not render into model-visible context; raw tool output hidden by `HIDE_RAW` must not leak through primitive rendering.
- Reliability: invalid primitive update operations should fail predictably with normal Python exceptions during local construction or be ignored with metadata when generated from a tool result, depending on the update shape.
- Observability: runtime metadata should include primitive update counts and final primitive IDs so developers can debug sync behavior.
- Compatibility: existing code using `context_items`, `ContextManager`, `ToolResult.success`, and `AgentInput` must continue to work.

---

## 5. High-Level Design

This feature keeps one concept: context primitives are the durable working-memory objects, and the existing `ContextItem` surface becomes the compatibility foundation for them. `context_primitives` is introduced as a clearer public alias at the agent/input/spec API layer, but internally the runtime still stores primitives in `BaseContext.context_items`. This avoids creating a second context system.

Tools synchronize primitives by returning `ContextPrimitiveUpdate` objects in `ToolResult.context_updates`. The direct runtime applies those updates after the tool executes and before the next model call. The raw updates are retained in runtime metadata, while model-visible rendering is controlled by the selected `ContextWindowAlgorithm`.

Rendering remains inside `BaseContext.build_context()` for this first version. The change is ordering and admission: system prompt first, then admitted context primitives, then memory/history/tools/metadata/artifacts/responses/tool calls/files. This gives stable primitives the desired top-of-window placement without introducing a full renderer/compiler layer.

```text
Agent(context_primitives=[Task, Plan, File])
        |
        v
BaseAgent merges defaults + AgentInput primitives
        |
        v
AgentRuntime builds per-run primitive store
        |
        +--> BaseContext.build_context()
        |       System prompt
        |       Context primitives admitted by algorithm
        |       Remaining context
        |
        v
Model call -> tool call -> ToolResult(context_updates=[upsert/remove])
        |
        v
Runtime applies updates to primitive store
        |
        v
Next model call sees updated primitive block
```

The key design decision is to make primitives data objects and keep policy in algorithms/runtime. A `FileContextItem` stores facts about a file; a context-window algorithm decides whether the model sees full content, an excerpt, metadata only, or nothing. A tool can propose primitive updates; the runtime applies them through a single audited path.

---

## 6. Detailed Design

### 6.1 Context Primitive Metadata And Built-Ins

**File(s):** `vidbyte/context/primitives.py`
**Type:** Modified

#### What it does

Extends the existing context item dataclasses into first-version durable primitives. Adds placement/visibility enums, helper functions for stable IDs and rendering admission, plus new `IdentityContextItem` and `PlanContextItem` dataclasses.

#### Interface / API

```python
class ContextPrimitivePlacement(str, Enum):
    STICKY = "sticky"
    NORMAL = "normal"
    EPHEMERAL = "ephemeral"


class ContextPrimitiveVisibility(str, Enum):
    MODEL = "model"
    METADATA_ONLY = "metadata_only"
    HIDDEN = "hidden"


ContextPrimitive = ContextItem


@dataclass(frozen=True, slots=True)
class IdentityContextItem:
    role: str
    behavior: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    personality: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "identity"
    title: str = "Identity"
    id: str | None = "identity:agent"
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 0
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class PlanContextItem:
    objective: str
    steps: tuple[str, ...] = ()
    current_step: str | None = None
    risks: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "plan"
    title: str = "Plan"
    id: str | None = "plan:current"
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 20
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL

    def to_context_text(self) -> str: ...


def context_primitive_id(item: ContextItem) -> str: ...
def context_primitive_placement(item: ContextItem) -> ContextPrimitivePlacement: ...
def context_primitive_visibility(item: ContextItem) -> ContextPrimitiveVisibility: ...
def context_primitive_priority(item: ContextItem) -> int: ...
```

Existing item dataclasses (`TextContextItem`, `FileContextItem`, `GitDiffContextItem`, `TaskContextItem`, `DocumentContextItem`, `EnvironmentContextItem`, `MemoryContextItem`, `ProgressContextItem`, `ArtifactContextItem`, `ResponseContextItem`, `ToolCallContextItem`) will receive appended fields:

```python
id: str | None = None
placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
priority: int = 100
visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL
```

`TaskContextItem` should default to `placement=STICKY`, `priority=10`; `FileContextItem` should default to `placement=NORMAL`, `priority=100`.

#### Logic / Algorithm

1. Add enums and helper functions near the top of `primitives.py`.
2. Keep `ContextItem` structurally compatible by not requiring the new primitive metadata in the protocol.
3. Add optional fields at the end of existing dataclasses to avoid breaking positional construction.
4. `context_primitive_id(item)` returns `item.id` when present and non-empty; otherwise derives a deterministic fallback from kind/title and stable identifying fields where available.
5. `context_primitive_visibility(item)` coerces string/enum values and defaults to `MODEL`.
6. `context_primitive_placement(item)` coerces string/enum values and defaults to `NORMAL`.
7. `IdentityContextItem.to_context_text()` must clearly render as lower-authority role/behavior context, not a replacement for the system prompt.
8. `PlanContextItem.to_context_text()` renders objective, current step, ordered steps, risks, and verification.

#### Edge Cases & Error Handling

- Unknown placement/visibility strings raise `ValueError` when helper functions are called.
- Items without explicit IDs remain valid and receive derived IDs for store operations.
- Existing custom `ContextItem` implementations without new metadata remain valid.

---

### 6.2 Primitive Update Contract

**File(s):** `vidbyte/context/updates.py`
**Type:** New file

#### What it does

Defines a typed update object that tools and future algorithms can return to synchronize the primitive store.

#### Interface / API

```python
class ContextPrimitiveUpdateAction(str, Enum):
    UPSERT = "upsert"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class ContextPrimitiveUpdate:
    action: ContextPrimitiveUpdateAction | str
    item: ContextItem | None = None
    item_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def upsert(cls, item: ContextItem, *, metadata: Mapping[str, Any] | None = None) -> "ContextPrimitiveUpdate": ...

    @classmethod
    def remove(cls, item_id: str, *, metadata: Mapping[str, Any] | None = None) -> "ContextPrimitiveUpdate": ...
```

#### Logic / Algorithm

1. `upsert(...)` requires an item and derives the item ID through `context_primitive_id(item)`.
2. `remove(...)` requires a non-empty item ID.
3. The dataclass remains frozen and side-effect free.

#### Edge Cases & Error Handling

- `UPSERT` with no item raises `ValueError` when applied.
- `REMOVE` with no item ID raises `ValueError` when constructed via `remove(...)`.
- Unknown actions raise `ValueError` when applied by `ContextManager`.

---

### 6.3 Context Manager Primitive Store Behavior

**File(s):** `vidbyte/context/manager.py`
**Type:** Modified

#### What it does

Adds stable-ID upsert/remove/update behavior to the existing `ContextManager` without replacing the public class.

#### Interface / API

```python
class ContextManager:
    ...
    def upsert(self, item: ContextItem) -> "ContextManager": ...
    def remove_by_id(self, item_id: str) -> "ContextManager": ...
    def apply_update(self, update: ContextPrimitiveUpdate) -> "ContextManager": ...
    def apply_updates(self, updates: Iterable[ContextPrimitiveUpdate]) -> "ContextManager": ...
    def visible_items(self, algorithm: ContextWindowAlgorithm | None = None) -> tuple[ContextItem, ...]: ...
```

#### Logic / Algorithm

1. `add(...)` keeps append semantics for backward compatibility.
2. `upsert(item)` derives an ID. If an existing item has the same ID, replace it in place; otherwise append.
3. `remove_by_id(item_id)` removes all items with that derived ID.
4. `apply_update(update)` dispatches `UPSERT` and `REMOVE`.
5. `apply_updates(updates)` applies updates in order.
6. `visible_items(...)` delegates to `algorithm.model_visible_context_primitives(...)` when provided; otherwise filters out hidden/metadata-only items and sorts by placement/priority.
7. `to_context(...)` continues to preserve `context_items`.

#### Edge Cases & Error Handling

- Removing an unknown ID is a no-op to make tool update replay idempotent.
- Upserting two items with the same ID in one update sequence leaves the last item.
- Existing `remove(item)` list semantics are preserved and still raise `ValueError` for missing object identity/equality.

---

### 6.4 Base Context Rendering

**File(s):** `vidbyte/lib/dataclasses/context.py`
**Type:** Modified

#### What it does

Moves context primitive rendering to the top of the context window and supports pre-admitted model-visible primitive lists.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class BaseContext:
    ...
    context_items: Sequence[ContextItem] = ()

    def build_context(self) -> str: ...
```

#### Logic / Algorithm

1. Keep the existing public field name `context_items`.
2. In `build_context()`, append `System prompt` first when present.
3. Immediately after the system prompt, append `Context primitives:` for model-visible primitives.
4. Use `context_primitive_visibility(...)` to exclude `HIDDEN` and `METADATA_ONLY`.
5. Sort primitives by placement and priority before rendering.
6. Continue rendering existing sections after primitives.
7. Avoid duplicate primitive rendering later in the method.

#### Edge Cases & Error Handling

- Custom context items that raise from `to_context_text()` continue to surface their exception.
- Hidden primitives remain available in `context_items` for metadata/runtime but not text.
- Contexts without primitives render as before except for section ordering where relevant.

---

### 6.5 Context Window Algorithm Primitive Admission

**File(s):** `vidbyte/context/algorithms/tool_results.py`
**Type:** Modified

#### What it does

Adds default primitive admission methods to `ContextWindowAlgorithm`.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    ...
    def model_visible_context_primitives(self, items: Sequence[ContextItem]) -> tuple[ContextItem, ...]: ...
```

#### Logic / Algorithm

1. Filter out primitives with `visibility` equal to `HIDDEN` or `METADATA_ONLY`.
2. Sort by placement group: sticky first, normal second, ephemeral last.
3. Sort within each placement by numeric priority, then derived primitive ID for deterministic ordering.
4. Return the admitted primitive tuple.
5. Existing `model_visible_tool_result(...)` behavior is unchanged.

#### Edge Cases & Error Handling

- Invalid placement/visibility values raise `ValueError`, which surfaces during context construction/rendering.
- Future algorithm-specific configs can override this method or add fields without changing the runtime path.

---

### 6.6 Tool Result Primitive Updates

**File(s):** `vidbyte/lib/dataclasses/tools.py`, `vidbyte/tools/types.py`
**Type:** Modified

#### What it does

Adds primitive updates to the tool result contract and re-exports the updated type through the existing compatibility module.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_name: str
    status: ToolStatus
    output: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context_updates: tuple[ContextPrimitiveUpdate, ...] = ()

    @classmethod
    def success(
        cls,
        tool_name: str,
        output: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        context_updates: Sequence[ContextPrimitiveUpdate] = (),
    ) -> "ToolResult": ...
```

#### Logic / Algorithm

1. Add `context_updates` as the final dataclass field for constructor compatibility.
2. Add optional `context_updates` keyword-only parameters to `success`, `error`, and `failure`.
3. Store updates as a tuple.
4. `tools/types.py` remains a re-export shim; no behavioral logic is added there.

#### Edge Cases & Error Handling

- Existing `ToolResult(...)` positional construction remains valid.
- Existing helper calls without `context_updates` remain valid.
- Tool execution errors created by `ToolExecutor` have no updates unless explicitly provided by the tool.

---

### 6.7 Agent API Aliases

**File(s):** `vidbyte/agents/base.py`, `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Adds `context_primitives` as the developer-facing seed API while keeping `context_items` as the compatibility name.

#### Interface / API

```python
class BaseAgent:
    def __init__(
        self,
        *,
        ...
        context_items: Sequence[ContextItem] = (),
        context_primitives: Sequence[ContextItem] = (),
        context_manager: ContextManager | None = None,
        ...
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class AgentInput:
    prompt: str
    ...
    context_items: tuple[ContextItem, ...] = ()
    context_primitives: tuple[ContextItem, ...] = ()
    context_manager: ContextManager | None = None
```

`AgentSpec` gets the same `context_primitives` field.

#### Logic / Algorithm

1. Store `self.context_items` as `(*context_items, *context_primitives)`.
2. Preserve fork behavior by carrying merged primitive defaults forward.
3. `_normalize_input_context(...)` returns both `context_items` and `context_primitives` merged in deterministic order.
4. `AgentInput` and `AgentSpec` fields are appended to preserve positional compatibility as much as possible.

#### Edge Cases & Error Handling

- Passing the same primitive in both `context_items` and `context_primitives` may create duplicates unless it has the same stable ID and is later upserted by the manager.
- Existing callers using only `context_items` observe no API break.

---

### 6.8 Runtime Primitive Sync

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Maintains a per-run primitive store and applies tool-returned primitive updates before subsequent model calls.

#### Interface / API

No public method signature change is required beyond existing context construction parameters.

Internal helpers:

```python
def _primitive_manager_from_context(self, context: BaseAgentContext) -> ContextManager: ...

def _replace_context_primitives(
    self,
    context: BaseAgentContext,
    manager: ContextManager,
) -> BaseAgentContext: ...

def _apply_tool_context_updates(
    self,
    context: BaseAgentContext,
    manager: ContextManager,
    result: ToolResult,
    runtime_metadata: dict[str, Any],
) -> BaseAgentContext: ...
```

#### Logic / Algorithm

1. At the start of `arun(...)`, create `primitive_manager = ContextManager(context.context_items)`.
2. Before each model call, replace the local immutable `context` with one containing admitted/sorted context primitives.
3. After a non-internal tool executes, inspect `result.context_updates`.
4. Apply each update to `primitive_manager`.
5. Replace local `context` with updated `context_items`.
6. Record update count, updated IDs, and final primitive IDs in runtime metadata.
7. Keep full tool-call context storage unchanged.
8. Do not append primitive update details to provider messages directly; rendering happens through context rebuilding.

#### Edge Cases & Error Handling

- Internal `isDone` tool results do not apply primitive updates.
- A malformed update from a tool is recorded in metadata and does not crash the entire run unless it indicates a programmer error during construction.
- If a tool result hides raw output from model messages, primitive rendering still respects primitive visibility.

---

### 6.9 Export Chain

**File(s):** `vidbyte/context/__init__.py`, `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Exports new primitive metadata enums, built-in primitives, and update contracts from the standard public import surfaces.

#### Interface / API

```python
from vidbyte import (
    ContextPrimitive,
    ContextPrimitivePlacement,
    ContextPrimitiveUpdate,
    ContextPrimitiveUpdateAction,
    ContextPrimitiveVisibility,
    IdentityContextItem,
    PlanContextItem,
)
```

#### Logic / Algorithm

1. Import new names from `vidbyte.context.primitives` and `vidbyte.context.updates`.
2. Add names to `__all__` in each export module.
3. Preserve existing root exports.

#### Edge Cases & Error Handling

- N/A - import/export only.

---

### 6.10 Documentation

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`, `skills/vidbyte-sdk/context-primitives.md`
**Type:** Modified and New file

#### What it does

Documents the approved first-version primitive model for developers and future SDK agents.

#### Interface / API

README example:

```python
from vidbyte import Agent, ContextPrimitiveUpdate, IdentityContextItem, TaskContextItem, ToolResult

agent = Agent(
    name="builder",
    system_prompt="Follow the user request.",
    runner=my_runner,
    context_primitives=[
        IdentityContextItem(role="SDK implementation agent"),
        TaskContextItem(id="task:ship-primitives", goal="Ship context primitives", placement="sticky"),
    ],
)

return ToolResult.success(
    "inspect_diff",
    "Diff inspected.",
    context_updates=[
        ContextPrimitiveUpdate.upsert(TaskContextItem(id="task:ship-primitives", goal="Ship context primitives", status="in_progress")),
    ],
)
```

#### Logic / Algorithm

1. README adds a concise section under Context Management.
2. `skills/vidbyte-sdk/context-primitives.md` explains primitives, IDs, visibility, tool updates, and algorithm admission rules.
3. `skills/vidbyte-sdk/SKILL.md` links the new guide.

#### Edge Cases & Error Handling

- Documentation must warn that `IdentityContextItem` is lower-authority than the system prompt.
- Documentation must warn that tools should return updates rather than mutating agent context directly.

---

## 7. Data Model Changes

### 7.1 Context Primitive Metadata Fields

**Change type:** Modified

```python
id: str | None = None
placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.NORMAL
priority: int = 100
visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL
```

**Migration strategy:** N/A - fields are additive and defaulted.

- Forward migration: existing constructors continue to work.
- Rollback plan: remove appended fields, helper functions, tests, and docs.

### 7.2 IdentityContextItem

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class IdentityContextItem:
    role: str
    behavior: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    personality: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "identity"
    title: str = "Identity"
    id: str | None = "identity:agent"
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 0
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL
```

**Migration strategy:** N/A - new optional primitive.

### 7.3 PlanContextItem

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class PlanContextItem:
    objective: str
    steps: tuple[str, ...] = ()
    current_step: str | None = None
    risks: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "plan"
    title: str = "Plan"
    id: str | None = "plan:current"
    placement: ContextPrimitivePlacement | str = ContextPrimitivePlacement.STICKY
    priority: int = 20
    visibility: ContextPrimitiveVisibility | str = ContextPrimitiveVisibility.MODEL
```

**Migration strategy:** N/A - new optional primitive.

### 7.4 ContextPrimitiveUpdate

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class ContextPrimitiveUpdate:
    action: ContextPrimitiveUpdateAction | str
    item: ContextItem | None = None
    item_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - new optional update object.

### 7.5 ToolResult.context_updates

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class ToolResult:
    ...
    context_updates: tuple[ContextPrimitiveUpdate, ...] = ()
```

**Migration strategy:** Additive final field with default.

- Forward migration: existing tool results continue to work.
- Rollback plan: remove field and helper keyword arguments; tools no longer return primitive updates.

---

## 8. API Changes

### 8.1 Python SDK Agent Construction

**Change type:** Modified

**Request:**

```python
agent = Agent(
    name="builder",
    system_prompt="Work carefully.",
    runner=my_runner,
    context_primitives=[
        IdentityContextItem(role="SDK engineer"),
        TaskContextItem(id="task:current", goal="Ship primitive sync", placement="sticky"),
    ],
)
```

**Response:**

```python
reply = await agent.arun("Continue")
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid primitive placement/visibility raises `ValueError` during rendering/admission |

### 8.2 Python SDK AgentInput Per-Call Primitives

**Change type:** Modified

**Request:**

```python
reply = await agent.arun(
    AgentInput(
        "Review this file",
        context_primitives=(FileContextItem.from_path("README.md"),),
    )
)
```

**Response:**

```python
reply.content
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | File construction errors surface before the agent call |

### 8.3 Python SDK ToolResult Primitive Updates

**Change type:** Modified

**Request:**

```python
return ToolResult.success(
    "read_file",
    "Read README.md",
    context_updates=[
        ContextPrimitiveUpdate.upsert(
            FileContextItem(id="file:README.md", path="README.md", absolute_path=..., size_bytes=123)
        )
    ],
)
```

**Response:**

```python
ToolResult(..., context_updates=(ContextPrimitiveUpdate(...),))
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | `ContextPrimitiveUpdate.remove("")` raises `ValueError` |
| N/A | Malformed updates returned by tools are recorded in runtime metadata when possible |

### 8.4 ContextWindowAlgorithm Primitive Admission

**Change type:** Modified

**Request:**

```python
visible = ContextWindow.preset.default.model_visible_context_primitives(items)
```

**Response:**

```python
(IdentityContextItem(...), TaskContextItem(...), ...)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid enum strings raise `ValueError` |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-primitives-agent-sync.md` | Approved design for first-version primitive sync |
| CREATE | `vidbyte/context/updates.py` | New primitive update contract for tools and algorithms |
| CREATE | `tests/test_context_primitives.py` | Focused tests for primitive metadata, updates, admission, and rendering |
| CREATE | `skills/vidbyte-sdk/context-primitives.md` | SDK skill documentation for primitives and update rules |
| MODIFY | `vidbyte/context/primitives.py` | Add primitive metadata, enums, helpers, identity, and plan primitives |
| MODIFY | `vidbyte/context/manager.py` | Add upsert/remove/update behavior and visible item admission |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add default primitive admission to `ContextWindowAlgorithm` |
| MODIFY | `vidbyte/lib/dataclasses/context.py` | Render model-visible primitives beneath the system prompt |
| MODIFY | `vidbyte/lib/dataclasses/tools.py` | Add `ToolResult.context_updates` |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `context_primitives` to `AgentInput` and `AgentSpec` |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Re-export new primitive and update types |
| MODIFY | `vidbyte/tools/types.py` | Re-export updated tool dataclasses and any new update type if needed |
| MODIFY | `vidbyte/agents/base.py` | Add `context_primitives` constructor/fork/per-call merge support |
| MODIFY | `vidbyte/agents/runtime.py` | Apply tool-returned primitive updates and update runtime metadata |
| MODIFY | `vidbyte/context/__init__.py` | Public context exports for primitive/update types |
| MODIFY | `vidbyte/__init__.py` | Root convenience exports for primitive/update types |
| MODIFY | `tests/test_context_management.py` | Update existing manager/rendering expectations for primitive metadata |
| MODIFY | `tests/test_agent_base.py` | Cover agent and per-call `context_primitives` merging |
| MODIFY | `tests/test_agent_runtime.py` | Cover runtime primitive sync from tool results |
| MODIFY | `README.md` | Document public primitive seeding and tool update usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Link primitive guidance and update repository rules |

No files will be deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_context_primitives.py` -> `test_identity_context_item_defaults_to_sticky_model_visible`
- `tests/test_context_primitives.py` -> `test_plan_context_item_renders_steps_risks_and_verification`
- `tests/test_context_primitives.py` -> `test_context_primitive_id_uses_explicit_id`
- `tests/test_context_primitives.py` -> `test_context_primitive_id_derives_file_id_from_path`
- `tests/test_context_primitives.py` -> `test_hidden_and_metadata_only_primitives_are_not_model_visible`
- `tests/test_context_primitives.py` -> `test_context_window_algorithm_sorts_sticky_primitives_first_by_priority`
- `tests/test_context_primitives.py` -> `test_context_primitive_update_upsert_and_remove_helpers`
- `tests/test_context_primitives.py` -> `test_context_manager_upsert_replaces_existing_item_with_same_id`
- `tests/test_context_primitives.py` -> `test_context_manager_apply_updates_upserts_and_removes`
- `tests/test_context_primitives.py` -> `test_base_context_renders_primitives_after_system_prompt`
- `tests/test_context_management.py` -> update/extend public import coverage for new primitive/update types
- `tests/test_agent_base.py` -> `test_agent_accepts_context_primitives_alias`
- `tests/test_agent_base.py` -> `test_agent_input_context_primitives_merge_after_agent_defaults`
- `tests/test_agent_runtime.py` -> `test_runtime_applies_tool_result_context_updates_before_next_model_call`
- `tests/test_agent_runtime.py` -> `test_runtime_does_not_render_hidden_tool_returned_primitive`
- `tests/test_agent_runtime.py` -> `test_runtime_metadata_records_context_primitive_updates`

### Integration Tests

- Run a fake direct text agent where the first model call invokes a tool returning `ContextPrimitiveUpdate.upsert(TaskContextItem(...))`; assert the second runner call receives a context containing the updated task primitive beneath the system prompt.
- Run a fake direct text agent where a tool returns a hidden `FileContextItem`; assert the final metadata contains the primitive but the second model call does not contain its content.
- Run an agent with both default `context_primitives` and per-call `AgentInput.context_primitives`; assert deterministic ordering and no mutation of agent defaults.

### Manual / QA Test Cases

1. Create an `Agent` with `IdentityContextItem`, `TaskContextItem`, and `PlanContextItem`; run with a fake runner and confirm the system prompt context has a `Context primitives:` block immediately after `System prompt:`.
2. Create a custom tool that returns `ContextPrimitiveUpdate.upsert(FileContextItem(...))`; run two iterations and confirm the second model call includes the file primitive.
3. Create a custom tool that returns `ContextPrimitiveUpdate.remove("task:current")`; confirm the next model call no longer includes the task.
4. Create a hidden primitive and confirm it appears in runtime metadata but not model-visible context text.

Verification commands:

```powershell
python -m unittest tests.test_context_primitives tests.test_context_management tests.test_agent_base tests.test_agent_runtime
python -m unittest discover -s tests
python -m compileall vidbyte
```

Attempt if available:

```powershell
python -m ruff check .
python -m mypy .
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python >=3.11 | Dataclasses, enums, typing | Low |
| Existing `pydantic` dependency | Existing `>=2,<3` | N/A - not used by this feature | None |

No new package dependencies or external services are required.

---

## 12. Rollout & Deployment

- Feature flags: none.
- Breaking change: intended to be non-breaking. New fields and parameters are optional and defaulted.
- Migration path: developers can continue using `context_items`; new code should prefer `context_primitives`.
- Deployment order: single SDK package release after tests pass.
- Rollback procedure: revert implementation commits; remove `vidbyte/context/updates.py`, new docs/tests, new primitive fields/types, `ToolResult.context_updates`, and agent/runtime sync logic.
- Compatibility note: if top-of-window primitive rendering changes existing text snapshots, tests must be updated intentionally and release notes should mention the new context ordering.

---

## 13. Open Questions

- [ ] Should `ContextManager.to_context(...)` continue bridging primitive objects into legacy artifacts/responses/tool_calls, or should model-visible primitive rendering become the only default path to avoid duplicate context?
- [ ] Should malformed `ToolResult.context_updates` fail the run, or should the runtime record an ignored update and continue?
- [ ] Should `context_primitives` eventually replace `context_items` in docs, leaving `context_items` as compatibility-only?
- [ ] Should future context-window algorithms be able to generate primitive updates through a formal lifecycle hook, or is direct runtime/tool update sync enough for this first PR?
- [ ] Should `IdentityContextItem` be named `RoleContextItem` or `BehaviorProfileContextItem` to make its lower authority clearer?

---

## 14. Alternatives Considered

### Alternative 1: Create A Separate `ContextPrimitives` System

- What: Add a new collection class unrelated to `ContextItem` and `ContextManager`.
- Why rejected: The repo already has `ContextItem`, `ContextManager`, and agent wiring. A separate system would create parallel APIs and force callers to choose between "items" and "primitives" for the same concept.

### Alternative 2: Let Tools Mutate Agent Context Directly

- What: Give tools a handle to the agent context store and let them mutate it during execution.
- Why rejected: Direct mutation is harder to audit, test, and secure. Returning typed updates through `ToolResult` keeps tool execution side-effect-light and lets `AgentRuntime` enforce visibility and ordering.

### Alternative 3: Implement A Full Renderer/Compiler First

- What: Add a new renderer abstraction with token budgets, ranking, compaction, diagnostics, and provider-specific formatting.
- Why rejected: That is likely the right long-term architecture, but it is too large for the first primitive-sync PR. The existing `BaseContext.build_context()` path is sufficient to prove durable primitive storage and sync.

### Alternative 4: Store Primitive Updates In Tool Metadata

- What: Put primitive update payloads under `ToolResult.metadata["context_updates"]`.
- Why rejected: Metadata-only updates are untyped and easy for tools/runtimes to ignore accidentally. A first-class `context_updates` field makes the contract discoverable and testable.

### Alternative 5: Make Context-Window Algorithms Own The Primitive Store

- What: Store primitives inside `ContextWindowAlgorithm` instances.
- Why rejected: Algorithms are immutable preset/config objects. The mutable per-run primitive state belongs in `AgentRuntime` / `ContextManager`, while algorithms should control admission and lifecycle policy.
