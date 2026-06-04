# Design Doc: Context Window Algorithms as Prebuilt Tools

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

---

## 1. Overview

This PR introduces two new prebuilt tools — `TrajectoryCheckpointTool` and `ReflexionTool` — that expose the behavior of existing context-window algorithms as model-callable tools. Context-window algorithms fire deterministically at runtime-defined intervals; these tools give the primary model the ability to trigger the same context-writing behavior whenever it judges the moment appropriate. The PR also ships a skill file at `skills/vidbyte-sdk/context-algorithm-to-tool.md` that documents the conversion pattern as a reusable engineering recipe for future contributors.

---

## 2. Goals & Non-Goals

### Goals
- Add `TrajectoryCheckpointTool`: model-callable tool that writes a `TrajectoryCheckpointContextItem` into the active `ContextManager`
- Add `ReflexionTool`: model-callable tool that writes a `ReflexionContextItem` into the active `ContextManager`
- Add `TrajectoryCheckpointContextItem` and `ReflexionContextItem` to `vidbyte/context/primitives.py`
- Export both tools from `vidbyte/tools/builtins/__init__.py`
- Ship `skills/vidbyte-sdk/context-algorithm-to-tool.md` documenting the algorithm-to-tool conversion pattern
- Follow the `ContextUpsertTool` injection pattern exactly for `ContextManager` access

### Non-Goals
- Do not replace or modify existing context-window algorithms (`ReflexionAlgorithm`, `TrajectoryCheckpointAlgorithm`)
- Do not implement `CompactContextTool` or `GradeOutputTool` (deferred to future PRs)
- Do not change `ContextManager`'s public API
- Do not add secondary LLM calls inside tool `execute()` — both tools are pure model-authored (the calling model writes all content directly)
- Do not touch the feat/agentic-trajectory-checkpoints branch

---

## 3. Background & Context

The vidbyte SDK has two existing context-window algorithm families:

1. **`ReflexionAlgorithm`** (main branch): A return-level algorithm that wraps an agent run in a retry loop. On failure it invokes a secondary model to critique the failed attempt, then injects the reflection into the next trial's system prompt via `context_for_trial()`.

2. **`TrajectoryCheckpointAlgorithm`** (feat/agentic-trajectory-checkpoints branch, PR #106): An inner-loop algorithm that fires every N iterations. It invokes a secondary summarizer model to produce a `TrajectoryCheckpointContextItem` and places it into the `ContextManager`.

Both algorithms are **runtime-triggered**: the SDK decides when they fire, independently of the model. This is the right design for systematic, enforced compression. However it leaves a gap: the model cannot self-trigger a checkpoint or reflection when it encounters a decision boundary mid-task, without waiting for the deterministic cadence.

The tools in this PR close that gap. They share the same `ContextItem` primitives as the algorithms but put the trigger and content authorship in the model's hands.

---

## 4. Requirements

### Functional Requirements

1. `TrajectoryCheckpointTool.execute()` must construct a `TrajectoryCheckpointContextItem` from model-provided arguments and upsert it into the injected `ContextManager`
2. `TrajectoryCheckpointTool` must accept: `reasoning_summary` (required), `trajectory` (required), `output` (required), `score` (optional float string), `feedback` (optional), `title` (optional)
3. `ReflexionTool.execute()` must construct a `ReflexionContextItem` from model-provided arguments and upsert it into the injected `ContextManager`
4. `ReflexionTool` must accept: `critique` (required), `correction_plan` (required), `failed_attempt` (optional), `title` (optional)
5. Both tools must auto-generate a stable `primitive_id` using an incrementing counter per tool instance
6. Both tools must return the full rendered `to_context_text()` output in `ToolResult.output` so the model can verify what was stored
7. `TrajectoryCheckpointContextItem` must render `reasoning_summary / trajectory / output / score / feedback` sections with char bounding via `max_chars`
8. `ReflexionContextItem` must render `critique / correction_plan / failed_attempt` sections with char bounding via `max_chars`
9. Both tools must validate that required string arguments are non-empty
10. Both new `ContextItem` types must appear in `primitives.py.__all__`
11. Both tools must appear in `vidbyte/tools/builtins/__init__.py.__all__`

### Non-Functional Requirements
- No external I/O inside `execute()` — both tools are synchronous over the injected manager
- `score` parsing must coerce string → float safely and fall back to `None` on invalid input without raising
- Both tools must be `ToolPermission.SAFE`

---

## 5. High-Level Design

Both tools follow the identical injection pattern established by `ContextUpsertTool`: the `ContextManager` is passed at construction time and stored on the instance. This is the only way a tool can write into the context window managed by `AgentRuntime`, since `execute()` receives only a `ToolCall` — it has no access to runtime internals.

The new `ContextItem` primitives (`TrajectoryCheckpointContextItem`, `ReflexionContextItem`) are added to `vidbyte/context/primitives.py`. They are the same shared currency used by the algorithms: the algorithm version writes them from a secondary LLM; the tool version writes them from the primary model's arguments.

The key architectural distinction from algorithms:

```
Algorithm flow:
  runtime.after_tool_calls()
    → AlgorithmClass.after_tool_calls(ctx)
      → (optional secondary LLM call)
      → ctx.context_manager.upsert(ContextItem)

Tool flow:
  model.tool_call("trajectory_checkpoint", {...})
    → TrajectoryCheckpointTool.execute(call)
      → ContextManager.upsert(TrajectoryCheckpointContextItem)
```

The destination (`ContextManager.upsert`) is identical. The trigger and the author differ.

---

## 6. Detailed Design

### 6.1 TrajectoryCheckpointContextItem (new primitive)

**File:** `vidbyte/context/primitives.py`
**Type:** Modified (adds new dataclass and helper)

#### What it does
Typed, bounded context unit representing a runtime trajectory checkpoint. Identical in structure to the primitive defined in the feat branch, adapted for the single-file `primitives.py` layout on main.

#### Interface
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

#### Logic
`to_context_text()` renders sections in deterministic order: `Iteration`, `Checkpoint`, `Reasoning Summary`, `Trajectory`, `Output`, `Score`, `Feedback`. The full text is then truncated to `max_chars` via `_truncate_text()`.

A private `_truncate_text(text, max_chars)` helper is added to `primitives.py` since it does not yet exist on main.

#### Edge Cases
- `score` can be `None`; render as `"N/A"`
- `max_chars` of 0 or negative: the helper should pass through untruncated (guard against over-zealous truncation)

---

### 6.2 ReflexionContextItem (new primitive)

**File:** `vidbyte/context/primitives.py`
**Type:** Modified (adds new dataclass)

#### What it does
Typed context unit representing a model self-critique. Analogous in structure to `TrajectoryCheckpointContextItem` but scoped to reflexion semantics.

#### Interface
```python
@dataclass(frozen=True, slots=True)
class ReflexionContextItem:
    primitive_id: str
    critique: str
    correction_plan: str
    failed_attempt: str | None = None
    title: str = "Reflexion Note"
    max_chars: int = 1200
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "reflexion"
    primitive_frozen: bool = False

    def to_context_text(self) -> str: ...
```

#### Logic
`to_context_text()` renders `Critique`, `Correction Plan`, and optionally `Failed Attempt` sections. Truncated via `_truncate_text()`.

---

### 6.3 TrajectoryCheckpointTool

**File:** `vidbyte/tools/builtins/trajectory_checkpoint.py`
**Type:** New file

#### What it does
Model-callable builtin that writes a `TrajectoryCheckpointContextItem` into the live `ContextManager`. The model provides all content fields directly; no secondary LLM is invoked.

#### Interface
```python
class TrajectoryCheckpointTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _next_primitive_id(self) -> str: ...
    def _parse_score(self, raw: str | None) -> float | None: ...
    def _build_item(self, args: dict, primitive_id: str) -> TrajectoryCheckpointContextItem: ...
```

#### Parameters (model-facing)
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `reasoning_summary` | string | yes | Summary of reasoning and decisions made so far |
| `trajectory` | string | yes | Recent sequence of tool calls and outcomes |
| `output` | string | yes | Current best answer, result, or in-progress state |
| `score` | string | no | Self-assessed quality 0.0–1.0 (e.g. "0.75") |
| `feedback` | string | no | What to focus on or change in the next steps |
| `title` | string | no | Display label; defaults to "Runtime Checkpoint" |

#### Logic
1. Extract and validate `reasoning_summary`, `trajectory`, `output` as non-empty strings
2. Parse `score` via `_parse_score()`: coerce to float, clamp to [0.0, 1.0], return `None` on failure
3. Generate `primitive_id` via `_next_primitive_id()` using an incrementing `_counter`
4. Build `TrajectoryCheckpointContextItem` via `_build_item()`
5. Call `self._manager.upsert(item)` — raises `ValueError` on frozen primitive
6. Return `ToolResult.success` with `item.to_context_text()` as output

#### Error Handling
- Missing required args → `ToolResult.error` with field name listed
- `manager.upsert()` raises `ValueError` (frozen primitive) → `ToolResult.error`
- Invalid score string → silently set `score=None`

---

### 6.4 ReflexionTool

**File:** `vidbyte/tools/builtins/reflexion.py`
**Type:** New file

#### What it does
Model-callable builtin that writes a `ReflexionContextItem` into the live `ContextManager`. The model provides the critique and correction plan directly.

#### Interface
```python
class ReflexionTool(BaseTool):
    def __init__(self, context_manager: ContextManager) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def _next_primitive_id(self) -> str: ...
    def _build_item(self, args: dict, primitive_id: str) -> ReflexionContextItem: ...
```

#### Parameters (model-facing)
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `critique` | string | yes | What went wrong or what should be improved |
| `correction_plan` | string | yes | Concrete steps to correct the approach |
| `failed_attempt` | string | no | Brief description of the approach that failed |
| `title` | string | no | Display label; defaults to "Reflexion Note" |

#### Logic
1. Extract and validate `critique`, `correction_plan` as non-empty strings
2. Generate `primitive_id` via `_next_primitive_id()`
3. Build `ReflexionContextItem`
4. Call `self._manager.upsert(item)`
5. Return `ToolResult.success` with `item.to_context_text()` as output

---

### 6.5 Export updates

**File:** `vidbyte/tools/builtins/__init__.py`
**Type:** Modified

Add `TrajectoryCheckpointTool` and `ReflexionTool` to imports and `__all__`.

---

### 6.6 Skill file

**File:** `skills/vidbyte-sdk/context-algorithm-to-tool.md`
**Type:** New file

Documents the complete algorithm-to-tool conversion pattern. Covers:
- The core distinction (runtime-triggered vs model-triggered; secondary LLM vs primary model)
- The 5-step conversion checklist
- A worked example tracing `TrajectoryCheckpointAlgorithm` → `TrajectoryCheckpointTool`
- A second worked example tracing `ReflexionAlgorithm` → `ReflexionTool`
- When to use each pattern

---

## 7. Data Model Changes

### 7.1 TrajectoryCheckpointContextItem

**Change type:** New (added to existing `vidbyte/context/primitives.py`)

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
```

**Migration strategy:** N/A — new type, no existing data.

---

### 7.2 ReflexionContextItem

**Change type:** New (added to existing `vidbyte/context/primitives.py`)

```python
@dataclass(frozen=True, slots=True)
class ReflexionContextItem:
    primitive_id: str
    critique: str
    correction_plan: str
    failed_attempt: str | None = None
    title: str = "Reflexion Note"
    max_chars: int = 1200
    metadata: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "reflexion"
    primitive_frozen: bool = False
```

**Migration strategy:** N/A — new type, no existing data.

---

## 8. API Changes

N/A — no HTTP endpoints. Tool specs are the public API.

### TrajectoryCheckpointTool spec
- **name:** `trajectory_checkpoint`
- **permission:** `SAFE`

### ReflexionTool spec
- **name:** `reflexion`
- **permission:** `SAFE`

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/context/primitives.py` | Add `TrajectoryCheckpointContextItem`, `ReflexionContextItem`, `_truncate_text` helper |
| CREATE | `vidbyte/tools/builtins/trajectory_checkpoint.py` | New `TrajectoryCheckpointTool` |
| CREATE | `vidbyte/tools/builtins/reflexion.py` | New `ReflexionTool` |
| MODIFY | `vidbyte/tools/builtins/__init__.py` | Export both new tools |
| CREATE | `skills/vidbyte-sdk/context-algorithm-to-tool.md` | Algorithm-to-tool conversion skill |
| CREATE | `tests/test_context_algorithm_tools.py` | Unit tests for both tools and their primitives |
| CREATE | `scripts/test-context-algorithm-tools.py` | Standalone verification script |

---

## 10. Testing Plan

### Unit Tests (`tests/test_context_algorithm_tools.py`)

**TrajectoryCheckpointContextItem rendering:**
- `to_context_text()` includes all 6 sections — [Edge Case: all fields populated]
- `to_context_text()` renders score as "N/A" when `score=None` — [Edge Case: optional field absent]
- `to_context_text()` truncates to `max_chars` — [Silent Failure: text exceeds limit but no error raised]
- `to_context_text()` passes through when content is under `max_chars` — [Silent Failure: truncation fires too early]

**ReflexionContextItem rendering:**
- `to_context_text()` includes critique and correction_plan — [Edge Case: minimum required fields]
- `to_context_text()` omits Failed Attempt section when `failed_attempt=None` — [Edge Case: optional field absent]
- `to_context_text()` truncates to `max_chars` — [Silent Failure: over-length content]

**TrajectoryCheckpointTool execution:**
- Execute with all fields → item written to manager, `to_context_text()` returned — [Hidden Assumption: upsert succeeds]
- Execute with missing `reasoning_summary` → `ToolResult.error` — [Hidden Assumption: required field present]
- Execute with missing `trajectory` → `ToolResult.error` — [Hidden Assumption: required field present]
- Execute with missing `output` → `ToolResult.error` — [Hidden Assumption: required field present]
- Execute with invalid `score` string "abc" → item written with `score=None` — [Hidden Failure: bad float input silently drops]
- Execute with `score="0.85"` → item stored with `score=0.85` — [Silent Failure: float coercion wrong]
- Execute twice → generates distinct primitive IDs — [Hidden Failure: counter not incrementing]
- Execute on frozen primitive → `ToolResult.error` — [Hidden Assumption: manager allows overwrite]
- `spec()` returns `ToolSpec` with name `"trajectory_checkpoint"` — [Edge Case: spec is correct]
- `validate_call()` returns error string when required args missing — [Edge Case: BaseTool validation path]

**ReflexionTool execution:**
- Execute with `critique` + `correction_plan` → item written, text returned — [Hidden Assumption: minimum fields work]
- Execute with missing `critique` → `ToolResult.error` — [Hidden Assumption: required field present]
- Execute with missing `correction_plan` → `ToolResult.error` — [Hidden Assumption: required field present]
- Execute with optional `failed_attempt` present → included in rendered text — [Silent Failure: optional field dropped]
- Execute twice → distinct primitive IDs — [Hidden Failure: counter shared across instances]
- Execute on frozen primitive → `ToolResult.error` — [Hidden Assumption: manager allows overwrite]
- `spec()` returns `ToolSpec` with name `"reflexion"` — [Edge Case: spec correct]

### Integration Tests
- Both tools can be passed to `ContextManager` and their primitives rendered via `render_primitives_zone()` — verifies the round-trip from `execute()` to rendered context block
- Two `TrajectoryCheckpointTool` instances each maintain independent counters — [Hidden Assumption: counter is instance-local]

### Manual / QA Test Cases
1. Given a `ContextManager`, when `TrajectoryCheckpointTool.execute()` is called with all fields, then `manager.get_by_id("trajectory_checkpoint:1")` returns a `TrajectoryCheckpointContextItem` — [Hidden Assumption]
2. Given `score="2.5"` (out of range), when execute is called, then item is stored with `score=None` or `score` clamped to 1.0 — [Edge Case: score out of [0,1]]
3. Given `max_chars=50` on a `TrajectoryCheckpointContextItem` with long content, when `to_context_text()` is called, then output is ≤ 50 chars — [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `vidbyte.context.manager.ContextManager` | internal | Primitive storage | None — existing, stable |
| `vidbyte.tools.base.BaseTool` | internal | Tool contract | None — existing, stable |
| `vidbyte.tools.types` | internal | ToolCall/ToolResult/ToolSpec | None — existing, stable |

---

## 12. Rollout & Deployment

- No feature flags required
- Not a breaking change — additive only (new exports, new primitives)
- No migration required
- Both tools must be instantiated with a `ContextManager` before use; they are not auto-registered

---

## 13. Open Questions

- [x] Should `score` be clamped to [0.0, 1.0] or stored as-is? **Decision: clamp + None on parse failure**
- [x] Should primitive IDs be user-controllable? **Decision: auto-generated only — keeps tool interface minimal**
- [ ] Should `TrajectoryCheckpointContextItem.iteration` and `checkpoint_index` be auto-derived from the counter, or should iteration always be 0 when called from the tool (not the algorithm)? **Leaning toward: tool sets iteration=0, index from counter — avoids exposing runtime internals to model**

---

## 14. Alternatives Considered

### Alternative 1: Hybrid tool (model triggers, secondary LLM summarizes)
- What: `TrajectoryCheckpointTool.execute()` invokes a summarizer runner, mirroring the algorithm's agentic mode
- Why rejected: Adds nested LLM calls inside tool execute, making the tool async-complex and runner-dependent; the model calling this tool has the full context and can write the summary itself

### Alternative 2: Reuse `ContextUpsertTool` with a `trajectory_checkpoint` type
- What: Extend `ContextUpsertTool` to accept a new primitive type instead of adding a dedicated tool
- Why rejected: `TrajectoryCheckpointContextItem` has typed fields (score as float, structured sections) that can't be cleanly represented as a single `content: str` argument; a dedicated tool preserves the type structure

### Alternative 3: Add `primitive_id` as a model-provided parameter
- What: Let the model choose its own primitive IDs
- Why rejected: Model-provided IDs risk collision and non-determinism; the auto-counter is simpler and safe
