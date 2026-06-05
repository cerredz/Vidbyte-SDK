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
    - context_primitives tools: model-callable upsert/list/remove.
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
| `items()` / `by_kind(kind)` | Inspect the current items. |
| `render_primitives_zone()` | Render the primitives zone to text. |
| `clear()` / `clear_registry()` | Reset. |

Inner-loop context-window algorithms write through the run context's
`place_after_system_prompt` / `place_after_tools` rather than mutating provider messages —
see `skills/vidbyte-sdk/adding-context-window-algorithms.md`.

## Model-Callable Context Tools

The `context_primitives` tool family lets the model manage its own context window. Each tool is
constructed with the live `ContextManager` and is `ToolPermission.SAFE`:

```python
from vidbyte.tools.builtins.context_primitives import ContextUpsertTool, ContextListTool, ContextRemoveTool

# context_manager comes from the agent runtime; never pass it into execute()
tools = [
    ContextUpsertTool(context_manager),
    ContextListTool(context_manager),
    ContextRemoveTool(context_manager),
]
```

| Tool | Action |
|------|--------|
| `ContextUpsertTool` | Model inserts/updates a structured context item. |
| `ContextListTool` | Model lists current context items. |
| `ContextRemoveTool` | Model removes a context item by id. |

These tools share the same `ContextManager.upsert()` path that context-window algorithms use.
The difference is who triggers the write (model vs. runtime) — see
`skills/vidbyte-sdk/context-algorithm-to-tool.md`.

## Adding a New Primitive

1. Add the dataclass to the appropriate module under `vidbyte/context/primitives/`
   (or a new module), `@dataclass(frozen=True, slots=True)` with a `primitive_id` and a
   `to_context_text()` that bounds output with `_truncate_text`.
2. Export it from `vidbyte/context/primitives/__init__.py` (and `vidbyte/context/__init__.py` /
   `vidbyte/__init__.py` if public).
3. If the primitive backs a context-window algorithm and a tool, follow
   `skills/vidbyte-sdk/context-algorithm-to-tool.md` so both forms share the one dataclass.
4. Add tests (`tests/test_context_management.py`, `tests/test_context_primitives_*`).

## Verification

```powershell
python -m compileall vidbyte
python -m unittest tests.test_context_management tests.test_context_primitives_builtins tests.test_context_primitives_registry
```
