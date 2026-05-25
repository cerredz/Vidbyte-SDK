# Context Management

Use this guide when creating, modifying, or using context management primitives in the Vidbyte SDK.

## What Is Context Management

Context management is the layer that structures what an agent or strategy sees in its context window. It separates the storage and organization of context units (context items, managed by `ContextManager`) from how those units become prompt text (currently through `BaseContext.build_context()`).

Key concepts:

- **ContextItem**: An immutable, structured piece of context (a file, a task, a document, etc.).
- **ContextManager**: An ordered collection of context items with conversion into existing context dataclasses.
- **ContextWindowAlgorithm**: A runtime behavior attached to an agent that controls how context grows during execution (tool-result admission, reasoning traces, plan artifacts).

## When To Use Context Management

| Scenario | Use |
|---|---|
| You want reusable, structured context | `ContextItem` dataclasses + `ContextManager` |
| You want to pass per-call context to an agent | `AgentInput(context_items=[...])` |
| You want default context on an agent | `Agent(context_items=[...])` or `Agent(context_manager=...)` |
| You want to control tool-result visibility | `algorithm=ContextWindow.preset.no_raw_tool_outputs` |
| You want deterministic reasoning traces | `algorithm=ContextWindow.preset.reasoning_trace_medium` |
| You want pre-run planning | `algorithm=ContextWindow.preset.plan_then_implement` |

## Context Items

Standard context item dataclasses live under `vidbyte/context/primitives.py`. All items are immutable (`frozen=True, slots=True`) and implement the `ContextItem` protocol:

- `TextContextItem` — Generic custom text context.
- `FileContextItem` — File path, absolute path, size, content, and language hint.
- `GitDiffContextItem` — Git diff representation.
- `TaskContextItem` — Goal, status, progress, completed steps, next steps, and verification checks.
- `DocumentContextItem` — Named document with content.
- `EnvironmentContextItem` — OS, CWD, and shell metadata.
- `MemoryContextItem` — Preserved memory or summary content.
- `ProgressContextItem` — Completed tasks, touched files, decisions, errors, and next steps.
- `ArtifactContextItem` — Named artifact with content and type.
- `ResponseContextItem` — Model or agent response.
- `ToolCallContextItem` — Structured tool call record.

## ContextManager

`ContextManager` lives in `vidbyte/context/manager.py`. It stores context items in insertion order and converts them into `StrategyContext` fields when `to_context()` is called.

Key methods:
- `add(item)` — Append an item (mutates, returns self).
- `extend(items)` — Append multiple items.
- `remove(item)` — Remove an item by identity.
- `clear()` — Remove all items.
- `items()` — Return current items as a tuple.
- `by_kind(kind)` — Filter items by their `kind` attribute.
- `to_context(base_context=None)` — Convert to `StrategyContext` with optional base fields.

## Context Ownership

- Agent-level default context: `Agent(context_items=[...])` or `Agent(context_manager=...)`.
- Per-call context: `AgentInput(context_items=[...])`.
- Per-call context must not mutate the agent's defaults.
- `AgentRuntime.build_context()` merges agent and per-call context items into a single `BaseAgentContext`.

## Context-Window Algorithms

Context-window algorithms are runtime behaviors attached to an agent with `algorithm=ContextWindow.preset.<name>`. They currently support:

1. **Tool-result admission** — Control how raw tool output appears in model-visible messages.
   - `default` / `raw_tool_outputs` — Raw tool output.
   - `compact_tool_outputs` — Bounded tool output.
   - `hide_tool_outputs` / `no_raw_tool_outputs` — Hidden tool output with a completion notice.

2. **Reasoning traces** — Deterministic operational traces inserted after each non-terminal iteration.
   - `reasoning_trace_small` — Small trace.
   - `reasoning_trace_medium` — Medium trace (default).
   - `reasoning_trace_large` — Large trace with routes, risks, and tradeoffs.
   - `reasoning_trace(size=..., system_prompt=...)` — Custom trace configuration.

3. **Plan-then-implement** — Creates a plan artifact before normal execution.
   - `plan_then_implement` — Default preset.
   - `plan_then_implement_with(planner_prompt=..., artifact_name=..., max_plan_chars=...)` — Custom configuration.

Algorithms can be combined by constructing a custom `ContextWindowAlgorithm`:
```python
from vidbyte.context.algorithms import ContextWindowAlgorithm, ToolResultAdmission
from vidbyte.context.algorithms.types import ReasoningTraceConfig, ReasoningTraceSize

algorithm = ContextWindowAlgorithm(
    name="hidden_with_trace",
    tool_result_admission=ToolResultAdmission.HIDE_RAW,
    reasoning_trace=ReasoningTraceConfig(size=ReasoningTraceSize.MEDIUM),
)
```

## Verification

- `python -m unittest tests.test_context_management tests.test_context_window_algorithms tests.test_agent_runtime`
- `python -m compileall vidbyte`
