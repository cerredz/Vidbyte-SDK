<!--
Context Protocol Header

Description:
    Documents the design pattern for converting a context-window algorithm into a
    model-callable prebuilt tool in the Vidbyte SDK.
Purpose:
    Gives contributors a concrete recipe for when and how to offer a "tool form"
    of an existing context-window algorithm, covering the conceptual distinction,
    a 5-step conversion checklist, and two worked examples.
Architecture:
    - Section 1: The core distinction (algorithm vs tool).
    - Section 2: When to use each form.
    - Section 3: The 5-step conversion checklist.
    - Section 4: Worked example — TrajectoryCheckpointAlgorithm to TrajectoryCheckpointTool.
    - Section 5: Worked example — ReflexionAlgorithm to ReflexionTool.
    - Section 6: File placement rules.
    - Section 7: Things to remember.
Relations:
    See also: skills/vidbyte-sdk/adding-context-window-algorithms.md (for the algorithm side).
    Related design doc: docs/design/context-algorithms-as-tools.md.
-->

# Context Window Algorithm to Prebuilt Tool

Use this guide when you want to expose the behavior of an existing context-window
algorithm as a model-callable tool. This pattern produces two related objects that
share a `ContextItem` primitive but differ in who triggers them and who authors the
content.

Related skill files:

- Adding context window algorithms: `skills/vidbyte-sdk/adding-context-window-algorithms.md`
- Vidbyte SDK structure: `skills/vidbyte-sdk/SKILL.md`

Related design docs:

- `docs/design/context-algorithms-as-tools.md`
- `docs/design/trajectory-checkpoint-inner-loop-context-window.md`

---

## 1. The Core Distinction

Every context-window algorithm has a **tool equivalent**. The two forms share the same
`ContextItem` primitive and write it through the same `ContextManager.upsert()` call.
What differs is the trigger and the author of the content.

```
Context Window Algorithm (runtime-triggered)
  Trigger:    AgentRuntime calls after_tool_calls() on a deterministic cadence
  Author:     Secondary LLM (summarizer) or the runtime itself
  Cadence:    Every N iterations, on failure, at milestones — not the model's choice
  Shape:      InnerContextWindowAlgorithm.after_tool_calls(ctx: ContextWindowRunContext)

Prebuilt Tool (model-triggered)
  Trigger:    Primary model calls the tool by name when it judges the moment right
  Author:     Primary model (it writes all content fields directly in the arguments)
  Cadence:    Whenever the model decides — a self-chosen strategic moment
  Shape:      BaseTool.execute(call: ToolCall) -> ToolResult
```

The algorithm fires *regardless of what the model thinks*. The tool fires *because the
model decided it should*. This is not just a timing difference — it changes who is
responsible for the content.

In `TrajectoryCheckpointAlgorithm`, a secondary summarizer LLM reads the message
history and fills in `reasoning_summary / trajectory / output / score / feedback`.
The primary model never sees its own checkpoint being written; it simply finds a
compressed state block in the next context window.

In `TrajectoryCheckpointTool`, the primary model writes those same fields directly
as tool arguments. It IS the summarizer. It decides when its state is worth
persisting, and it decides what to say.

---

## 2. When to Use Each Form

Use the **algorithm form** when:

- You want guaranteed, systematic context injection regardless of model behavior
- The content requires a secondary LLM to summarize (the primary model's context is too
  large for it to self-summarize reliably at a fixed interval)
- The cadence is a non-negotiable policy (e.g. "every 3 iterations, always")
- You are implementing a runtime safety feature or observability mechanism

Use the **tool form** when:

- You want the model to decide when and whether to record its state
- The model already has the information it needs to write the content (it just ran through
  the iterations; it knows what it did)
- You want to enable metacognitive behavior — the model pausing to reflect at a
  decision boundary, not on a fixed clock
- You are building a cooperative agent workflow where the model participates in its own
  context management

Both forms can coexist. A developer might attach `TrajectoryCheckpointAlgorithm` to ensure
systematic checkpoints AND also give the model `TrajectoryCheckpointTool` so it can
write additional checkpoints at self-chosen moments.

---

## 3. The 5-Step Conversion Checklist

When converting an algorithm to a tool, work through each concern:

### Step 1: Identify the shared ContextItem primitive

The algorithm and its tool equivalent share the same `ContextItem` dataclass. Identify
which primitive the algorithm writes. If it does not yet exist in the
`vidbyte/context/primitives/` package, add it to the appropriate module (e.g.
`checkpoints.py`, `tasks.py`, `records.py`) and export it from
`vidbyte/context/primitives/__init__.py` — not as an algorithm-private class.

```python
# vidbyte/context/primitives/checkpoints.py — shared by both the algorithm and its tool
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointContextItem:
    primitive_id: str
    reasoning_summary: str
    trajectory: str
    output: str
    score: float | None
    feedback: str
    ...
    def to_context_text(self) -> str: ...
```

### Step 2: Determine content authorship

Ask: "Who should fill in the content fields?"

- If the algorithm uses a secondary LLM: decide whether the tool should also invoke a
  secondary model (hybrid) or let the primary model write the content directly (pure).
  For `TrajectoryCheckpointTool` and `ReflexionTool`, we chose **pure** — the primary
  model writes all fields as tool arguments. This is simpler and works because the
  model calling the tool has the full context in its window already.

- If the algorithm is deterministic (no LLM): map each auto-computed field to a model-
  provided argument.

### Step 3: Map config fields to constructor, content fields to parameters

The algorithm's frozen config (e.g. `interval`, `max_checkpoints`) becomes the tool's
constructor arguments — fixed policy injected at build time by the developer.

The algorithm's auto-computed or LLM-generated content (e.g. `reasoning_summary`,
`trajectory`) becomes the tool's `ToolParameter` list — the model provides these at
call time.

```python
# Algorithm: config is frozen, content is generated automatically
TrajectoryCheckpointAlgorithm(interval=3, max_checkpoints=8)
  → generates reasoning_summary, trajectory, output, score, feedback
    from message history via secondary LLM

# Tool: config in constructor, content from model
TrajectoryCheckpointTool(context_manager)
  model calls: trajectory_checkpoint(reasoning_summary="...", trajectory="...", output="...")
```

### Step 4: Keep the same ContextManager injection pattern

Every tool that writes to the context window receives a `ContextManager` at construction
time, the same way `ContextUpsertTool` does. Never pass `ContextManager` into `execute()`.
The manager is runtime-scoped; it is instantiated by `AgentRuntime` and shared with tools
at agent setup time.

```python
class TrajectoryCheckpointTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None:
        self._manager = context_manager  # live manager, shared with AgentRuntime
        self._counter = 0                # per-instance counter for stable primitive IDs

    async def execute(self, call: ToolCall) -> ToolResult:
        ...
        self._manager.upsert(item)       # same upsert call the algorithm uses
        return ToolResult.success(call.tool_name, item.to_context_text())
```

### Step 5: Return the rendered primitive in ToolResult.output

Always return `item.to_context_text()` as the `ToolResult.output`. This lets the model
immediately read back what was stored and verify it is correct. Returning "OK" or a
bare ID is not enough — the model should be able to confirm its checkpoint or critique
was recorded as intended.

---

## 4. Worked Example: TrajectoryCheckpointAlgorithm to TrajectoryCheckpointTool

### The algorithm (feat/agentic-trajectory-checkpoints)

`TrajectoryCheckpointAlgorithm` is an `InnerContextWindowAlgorithm`. The runtime calls
`after_tool_calls(ctx)` once per completed iteration. When the cadence condition is met
(every `interval` iterations, up to `max_checkpoints`), it:

1. Calls a secondary summarizer LLM with the full message history
2. Parses the JSON response to extract `reasoning_summary`, `trajectory`, `output`, `score`, `feedback`
3. Constructs a `TrajectoryCheckpointContextItem` and calls `ctx.context_manager.upsert(item)`

The model never decides when this happens. It just finds the checkpoint in its next context window.

### The tool (vidbyte/tools/builtins/trajectory_checkpoint.py)

`TrajectoryCheckpointTool` is a `BaseTool`. The model calls `trajectory_checkpoint(...)` when it
decides to record its state. The tool:

1. Validates that `reasoning_summary`, `trajectory`, `output` are non-empty
2. Parses the optional `score` string to a float clamped to [0.0, 1.0]
3. Auto-generates `primitive_id = f"trajectory_checkpoint:{self._counter}"`
4. Constructs `TrajectoryCheckpointContextItem(iteration=0, checkpoint_index=counter, ...)`
5. Calls `self._manager.upsert(item)`
6. Returns `item.to_context_text()` so the model can confirm

### What the model sees and writes

```
# Model calls:
trajectory_checkpoint(
    reasoning_summary="I have identified the root cause. The issue is in auth.py line 42.",
    trajectory="read_file(auth.py) → grep(validate_token) → found null check missing",
    output="Proposed fix: add 'if token is None: return None' at line 42",
    score="0.85",
    feedback="Verify edge case where token is empty string, not just None"
)

# Tool writes to ContextManager:
### [trajectory_checkpoint:1] Runtime Checkpoint
Iteration: 0
Checkpoint: 1

### Reasoning Summary
I have identified the root cause. The issue is in auth.py line 42.

### Trajectory
read_file(auth.py) -> grep(validate_token) -> found null check missing

### Output
Proposed fix: add 'if token is None: return None' at line 42

### Score
0.85

### Feedback
Verify edge case where token is empty string, not just None
```

### Key differences from the algorithm

| Concern | Algorithm | Tool |
|---------|-----------|------|
| Trigger | runtime, every N iterations | model, strategic choice |
| Content author | secondary summarizer LLM | primary model (direct arguments) |
| `iteration` field | actual runtime iteration count | always 0 (tool has no runtime context) |
| Eviction | enforces `max_checkpoints` | no eviction — model manages explicitly |
| Placement | configurable (top/end of context zone) | registry zone via `upsert()` |

---

## 5. Worked Example: ReflexionAlgorithm to ReflexionTool

### The algorithm (vidbyte/context/algorithms/reflexion.py)

`ReflexionAlgorithm` is a return-level algorithm attached to `ContextWindowAlgorithm`. The runtime
wraps the entire agent run in a retry loop. On failure (stop reason is not `IS_DONE`), it:

1. Calls a separate reflection model with `render_reflection_prompt()`
2. Captures the reflection text via `capture_reflection()`
3. Injects the accumulated reflections into the next trial's system prompt via `context_for_trial()`

The model does not trigger this. The runtime detects failure and runs the reflection loop.

### The tool (vidbyte/tools/builtins/reflexion.py)

`ReflexionTool` is a `BaseTool`. The model calls `reflexion(...)` when it self-detects a reasoning
error, a repeated mistake, or a dead-end approach. The tool:

1. Validates that `critique` and `correction_plan` are non-empty
2. Handles optional `failed_attempt` (set to `None` if empty or absent)
3. Auto-generates `primitive_id = f"reflexion:{self._counter}"`
4. Constructs `ReflexionContextItem` and calls `self._manager.upsert(item)`
5. Returns `item.to_context_text()`

### What the model sees and writes

```
# Model calls:
reflexion(
    critique="I kept searching for a config file that doesn't exist. Wrong assumption.",
    correction_plan="Check the README first. The config is passed as an env var, not a file.",
    failed_attempt="Searched /etc/app/, ~/.config/app/, and /usr/local/app/ — none exist"
)

# Tool writes to ContextManager:
### [reflexion:1] Reflexion Note
### Critique
I kept searching for a config file that doesn't exist. Wrong assumption.

### Correction Plan
Check the README first. The config is passed as an env var, not a file.

### Failed Attempt
Searched /etc/app/, ~/.config/app/, and /usr/local/app/ — none exist
```

### Key differences from the algorithm

| Concern | Algorithm | Tool |
|---------|-----------|------|
| Trigger | runtime, on failure detection | model, on self-detected error |
| Content author | secondary reflection LLM | primary model (direct arguments) |
| Injection point | next trial's system prompt (via `context_for_trial()`) | registry zone via `upsert()` |
| Retry loop | yes — algorithm controls retry orchestration | no — tool only records the critique |
| Scope | wraps the entire agent run | scoped to one context window note |

---

## 6. File Placement Rules

Follow these rules when adding a new algorithm-to-tool conversion:

```
vidbyte/context/primitives/
    Add the shared ContextItem dataclass to the appropriate module in this package
    (e.g. checkpoints.py) and export it from __init__.py. Both the algorithm and the
    tool import it from vidbyte.context.primitives. Do not define primitives inside
    the algorithm or tool file.

vidbyte/tools/builtins/<tool_name>.py
    One file per tool. Follow the naming of existing builtins (reflexion.py,
    trajectory_checkpoint.py). The class name is the PascalCase of the file name.

vidbyte/tools/builtins/__init__.py
    Add the new tool class to both the import list and __all__.

tests/test_context_algorithm_tools.py
    Add tests to this shared test file (or a new one if the file grows large).
    Every tool needs: required-field validation, optional-field handling, primitive
    written to manager, distinct IDs on repeated calls, frozen-primitive rejection,
    spec().name, and render_primitives_zone round-trip.

skills/vidbyte-sdk/context-algorithm-to-tool.md (this file)
    Add a new worked example section (Section 6+) for each new conversion.
```

---

## 7. Things to Remember

- **The ContextItem is the shared currency.** The same dataclass serves both the algorithm
  and the tool. Never fork it; extend it if new fields are needed.

- **`iteration=0` for tool-written checkpoints.** The tool has no access to the runtime
  iteration count. Set `iteration=0` and let `checkpoint_index` track order via the counter.

- **Auto-generate primitive IDs.** Do not ask the model to provide primitive IDs. A
  per-instance counter (`self._counter`) produces stable, unique IDs without user input.

- **Never call LLMs inside `execute()` for the pure form.** Keep tool `execute()` methods
  free of I/O unless you are explicitly building a hybrid tool (model triggers, secondary
  LLM summarizes). Document the hybrid choice in the design doc.

- **Return `to_context_text()` in ToolResult.output.** This is the confirmation the model
  reads to verify what was stored. A bare "OK" leaves the model guessing.

- **`_truncate_text` is in `vidbyte/context/primitives/base.py`.** Use `_truncate_text(text, max_chars)` in
  `to_context_text()` to enforce character bounds. It passes through when `max_chars <= 0`.

- **ToolPermission.SAFE for all context-writing tools.** Context tools do not touch the
  filesystem, network, or external state. They are always `SAFE`.

- **Both forms can coexist.** Attaching `TrajectoryCheckpointAlgorithm` to an agent AND
  giving it `TrajectoryCheckpointTool` is a valid configuration. The algorithm provides
  the systematic floor; the tool lets the model add strategic notes.
