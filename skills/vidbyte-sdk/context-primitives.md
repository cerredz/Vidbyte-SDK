<!--
Context Protocol Header

Description:
    Reference for the context primitives package, ContextManager, and the
    model-callable context tools.
Purpose:
    Explains how structured context items are defined, stored, placed in the
    context window, and read/written by tools and context-window algorithms.
Architecture:
    - vidbyte/context/primitives/: ContextItem dataclasses (one module per group).
    - ContextManager: runtime-scoped collection + placement + rendering.
    - context_primitives tools: model-callable create/list/remove/view/stats/edit/move.
Relations:
    See skills/vidbyte-sdk/context-algorithm-to-tool.md (algorithm/tool forms),
    skills/vidbyte-sdk/adding-context-window-algorithms.md, and
    skills/usage/available_tools.md.
-->

# Context Primitives & ContextManager

Use this guide when working with structured context items, the `ContextManager`,
or the model-callable context tools.

## The Primitives Package

Context item primitives live in the `vidbyte/context/primitives/` **package** (not a
single `primitives.py` module). Each module groups related items:

```text
vidbyte/context/primitives/
|-- __init__.py     re-exports every public primitive + helpers (e.g. _truncate_text)
|-- base.py         ContextItem protocol + shared helpers (_truncate_text)
|-- records.py      text/file/response/tool-call/artifact-style items
|-- documents.py    document/environment/memory items
|-- tasks.py        TaskContextItem, PlanContextItem
`-- checkpoints.py  TrajectoryCheckpointContextItem (and similar)
```

Public items are importable from `vidbyte.context.primitives` (and most from
`vidbyte.context` / `vidbyte`):

```python
from vidbyte.context.primitives import (
    TextContextItem, FileContextItem, GitDiffContextItem, TaskContextItem, PlanContextItem,
    DocumentContextItem, EnvironmentContextItem, MemoryContextItem, ProgressContextItem,
    ArtifactContextItem, ResponseContextItem, ToolCallContextItem, TrajectoryCheckpointContextItem,
)
```

Every primitive implements the `ContextItem` protocol — it carries a stable
`primitive_id` and renders to text via `to_context_text()`. Use `_truncate_text(text, max_chars)`
from `vidbyte/context/primitives/base.py` to bound rendered output (it passes through when
`max_chars <= 0`).

## ContextManager

`ContextManager` (`vidbyte/context/manager.py`) is the runtime-scoped collection that owns
context items, their placement in the context window, and rendering. It is instantiated by
`AgentRuntime` and shared with tools and context-window algorithms. Key methods:

| Method | Purpose |
|--------|---------|
| `upsert(item, *, placement=END_OF_CONTEXT)` | Insert or replace an item; returns self. |
| `place_after_system_prompt(item) -> str` | Render the item at the top of the context zone; mints a `primitive_id`. |
| `place_after_tools(item) -> str` | Render the item at the end of the context zone; mints a `primitive_id`. |
| `get_by_id(primitive_id)` / `remove_by_id(primitive_id)` | Look up / remove by id. |
| `registry_items()` | Ordered, read-only view of managed registry entries. |
| `set_placement(primitive_id, placement)` | Move an existing managed primitive to a new render placement. |
| `set_frozen(primitive_id, frozen)` | Mark an existing managed primitive developer-owned or agent-editable. |
| `upsert_preserving_placement(item)` | Re-upsert using the id's prior placement (default `END_OF_CONTEXT`). |
| `recite(primitive_id, *, slot_id=None) -> str` | Copy a primitive to `END_OF_CONVERSATION` under `slot_id` or `recite:{id}`. |
| `items()` / `by_kind(kind)` | Inspect the current items. |
| `render_primitives_zone()` | Render the primitives zone to text. |
| `clear()` / `clear_registry()` | Reset. |

Inner-loop context-window algorithms write through the run context's
`place_after_system_prompt` / `place_after_tools` rather than mutating provider messages —
see `skills/vidbyte-sdk/adding-context-window-algorithms.md`.

## Model-Callable Context Tools

The `context_primitives` tool family lets the model manage its own context window. Each tool is constructed with the same live `ContextManager` that is passed to `BaseAgent(context_manager=...)` and is `ToolPermission.SAFE`:

```python
from vidbyte import Agent, ContextManager
from vidbyte.tools.builtins.context_primitives import ContextWindowFactory

ctx = ContextManager()
agent = Agent(
    name="context-editor",
    runner=my_runner,
    context_manager=ctx,
    tools=ContextWindowFactory(ctx).build(),
)
```

| Tool | Action |
|------|--------|
| `ContextWindowFactory(context_manager).build(include=None, management=True)` | Class factory mounting per-primitive create tools plus management tools. |
| `context_window_tools(...)` | Thin convenience wrapper around `ContextWindowFactory(...).build(...)`. |
| `CreateContextPrimitiveTool` | Registry-backed generic class used to instantiate `context_create_<key>` tools. |
| `context_create_text`, `context_create_document`, `context_create_memory`, `context_create_plan`, `context_create_task`, `context_create_progress`, `context_create_artifact`, `context_create_environment`, `context_create_git_diff` | Typed create/upsert tools for supported primitive keys. Tool strings live on each primitive's `TOOL_CREATE_META`. Reusing `primitive_id` overwrites unless the existing primitive is frozen. |
| `ContextListTool` | Model lists current context items. |
| `ContextRemoveTool` | Model removes a non-frozen context item by id. |
| `ContextStatsTool` | Model lists id, kind, title, placement, frozen flag, and rendered character count. |
| `ContextEditTool` | Model performs an exact, unique string replacement across editable string/tuple fields (`content`, `goal`, `steps`, etc.). |
| `ContextReciteTool` | Model re-emits a named primitive at `END_OF_CONVERSATION` (copy id `recite:{id}` or optional `slot_id`) for recent attention. |
| `ContextMoveTool` | Model changes the placement for one non-frozen primitive. |
| `ContextUpsertTool` | Legacy flattened insert/update tool retained for compatibility. |

These tools share the same `ContextManager.upsert()` path that context-window algorithms use. The difference is who triggers the write: model vs. runtime. Supported create keys intentionally exclude filesystem-backed `file`, event-record primitives (`response`, `tool_call`), and algorithm-owned primitives (`reflexion`, `trajectory_checkpoint`, `error_correction`, `problem_space_search`). Keep one shared manager instance everywhere; tools mutate that manager, and the linear runtime re-renders its registry on the next iteration.

## Adding a New Primitive

1. Add the dataclass to the appropriate module under `vidbyte/context/primitives/`
   (or a new module), `@dataclass(frozen=True, slots=True)` with a `primitive_id` and a
   `to_context_text()` that bounds output with `_truncate_text`.
2. If the primitive should be model-creatable, add a `TOOL_CREATE_META` ClassVar dictionary
   on the dataclass with `key`, `tool_name`, `default_title`, a detailed
   `{tool_name} is ... {tool_name} does ...` description, and a `fields` map of detailed
   parameter strings/schemas. Then register a builder row in
   `vidbyte/tools/builtins/context_primitives/registry.py`.
3. Export it from `vidbyte/context/primitives/__init__.py` (and `vidbyte/context/__init__.py` /
   `vidbyte/__init__.py` if public).
4. If the primitive backs a context-window algorithm and a tool, follow
   `skills/vidbyte-sdk/context-algorithm-to-tool.md` so both forms share the one dataclass.
4. Add tests (`tests/test_context_management.py`, `tests/test_context_primitives_*`).

## Verification

```powershell
python -m compileall vidbyte
python -m unittest tests.test_context_management tests.test_context_primitives_builtins tests.test_context_primitives_registry
```
