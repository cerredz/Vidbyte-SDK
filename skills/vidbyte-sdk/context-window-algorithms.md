# Context Window Algorithms

Use this guide when adding, modifying, or using context-window algorithms in the Vidbyte SDK.

## What Are Context Window Algorithms

Context-window algorithms control what the model sees at runtime. They run inside the direct agent execution loop (`AgentRuntime.arun()`) and modify the provider message list — the ordered sequence of assistant, tool, and lifecycle messages sent to the model on each call.

Unlike context items (which define what context is stored) or strategies (which define prompt-engineering recipes), context-window algorithms define how context grows and transforms during iterative agent execution.

## Current Algorithm Hooks

### Tool-Result Admission

Controlled by `ContextWindowAlgorithm.tool_result_admission` and the method `model_visible_tool_result(call, result)`. Runs after a tool executes and before its result is appended to provider messages.

Modes:
- `RAW` — Pass tool output through unchanged.
- `COMPACT` — Bound tool output to `max_tool_result_chars`.
- `HIDE_RAW` — Replace tool output with a status-only notice.

### Pre-Run Planning

Controlled by `ContextWindowAlgorithm.plan_then_implement`. Runs once after `before_run` middleware and before the main execution loop. Creates a `ContextArtifact` from a planner call and attaches it to the agent context.

### After-Iteration Reasoning Trace

Controlled by `ContextWindowAlgorithm.reasoning_trace`. Runs after each non-terminal iteration (no tool calls or after tool calls are processed). Inserts a deterministic operational trace message into the provider message list for the next model call.

## Adding A New Algorithm

### Step 1: Config Type

If the algorithm needs new configuration, add config dataclasses to `vidbyte/context/algorithms/types.py`. Keep them frozen and side-effect free.

### Step 2: Algorithm Implementation

Create a new file under `vidbyte/context/algorithms/` following the snake_case naming convention. Every file must start with the Context Protocol Header block comment (Description, Purpose, Architecture, Relations).

### Step 3: Runtime Integration

Add the algorithm logic to `vidbyte/agents/runtime.py`. New lifecycle hooks should be added as internal methods on `AgentRuntime` and called from the appropriate point in the `arun()` loop.

### Step 4: Preset Registration

Add preset properties or factories to `ContextWindowPresets` in `vidbyte/context/presets.py`. Fixed properties support string resolution (e.g., `algorithm="my_preset"`); factories support parameterized usage (e.g., `ContextWindow.preset.my_preset(size=...)`).

### Step 5: Exports

Update the following export chains:

```
vidbyte/context/algorithms/__init__.py    — Import + add to __all__
vidbyte/context/__init__.py              — Re-export stable config types
vidbyte/__init__.py                       — Root convenience exports
```

### Step 6: Tests

Add tests to:
- `tests/test_context_window_algorithms.py` — Config and renderer tests.
- `tests/test_agent_runtime.py` — Runtime integration tests.
- `tests/test_context_management.py` — Preset resolution tests.

### Step 7: Documentation

Update:
- `skills/vidbyte-sdk/context-window-algorithms.md` — This file.
- `skills/vidbyte-sdk/context-management.md` — Context management overview.
- `skills/vidbyte-sdk/SKILL.md` — SDK structure reference.
- `skills/vidbyte-sdk-doc/SKILL.md` — Repository reference.
- `README.md` — Public usage examples.

## Leakage Rules

- Reasoning traces must not reinject raw tool output that was hidden by tool-result admission algorithms.
- Reasoning traces must not claim or attempt to expose hidden model chain-of-thought.
- Runtime metadata (full tool output, call states) must remain available for auditing even when hidden from model-visible messages.
- Plan artifacts must not contain sensitive information beyond what is explicitly returned by the planner model call.

## Verification

- `python -m unittest tests.test_context_window_algorithms tests.test_context_management tests.test_agent_runtime`
- `python -m compileall vidbyte`
