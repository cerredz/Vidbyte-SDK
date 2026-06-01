# Design Doc: Trajectory Checkpoint Context Window

**Status:** Approved
**Author:** Codex
**Created:** 2026-06-01
**Last Updated:** 2026-06-01

---

## 1. Overview

This feature adds a deterministic context-window algorithm that periodically injects bounded runtime checkpoint blocks into the agent-visible message window during the direct linear agent loop. Developers opt in with `algorithm=ContextWindow.preset.trajectory_checkpoints`; every configured interval of completed model-call iterations, the runtime adds a structured checkpoint containing a reasoning summary, trajectory, current output, heuristic score, and feedback while preserving existing tool execution, middleware, permissions, tracing, and template-validation behavior.

---

## 2. Goals & Non-Goals

### Goals

- Add public `TrajectoryCheckpointAlgorithm` and `ContextWindow.preset.trajectory_checkpoints`.
- Inject model-visible checkpoints after every configured `interval` completed direct-runtime iteration.
- Render checkpoint blocks deterministically from observable runtime state, not hidden chain-of-thought.
- Preserve normal `AgentRuntime._arun_once` behavior through a generic iteration-observer hook.
- Record deterministic slots: `system_prompt`, `trajectory_checkpoint_iteration`, and `trajectory_checkpoint_injection`.
- Add `TrajectoryCheckpointContextWindowTemplate` for cadence and ordering validation.
- Attach bounded checkpoint metadata to final `AgentResult.metadata`.
- Add tests and a verification script covering edge cases, hidden failures, silent failures, and hidden assumptions.
- Document the preset in README and update context-window template guidance.

### Non-Goals

- No model-weight updates, harness file mutation, fine-tuning, RL, or autonomous skill editing.
- No LLM judge or external scoring model in v1; score is a labeled deterministic heuristic.
- No model-visible tool that the agent chooses to call for checkpoints.
- No database, persistence layer, replay store, vector memory, or cross-run storage.
- No broad redesign of middleware, provider formatting, or tool-call parsing.
- No live provider tests or network calls.

---

## 3. Background & Context

- The SDK is a Python `>=3.11` package using `setuptools`, `unittest`, and `pydantic>=2,<3`.
- Context-window algorithms are selected through `algorithm=ContextWindow.preset.<name>` and normalized by `ContextWindow.resolve_algorithm(...)`.
- Public algorithm configuration lives under `vidbyte/context/algorithms/`; runtime adapters live under `vidbyte/agents/algorithms/`; dispatcher mapping lives in `vidbyte/agents/context_algorithms.py`.
- `AgentRuntime.arun(...)` delegates to `AgentRuntimeContextAlgorithms`; if no runtime algorithm applies, it falls back to `_arun_once(...)`.
- Existing templates use `ContextWindowRecorder`, `ContextWindowTemplate`, and algorithm-specific subclasses for deterministic structural validation.
- Existing base-runtime template slots like `agent_iteration` are reserved but not globally emitted. This feature uses algorithm-specific iteration slots so existing templates are not disrupted.
- Implementation must happen in an isolated worktree after approval, with the design doc committed first.

---

## 4. Requirements

### Functional Requirements

1. `TrajectoryCheckpointAlgorithm` must be a frozen public config dataclass under `vidbyte/context/algorithms/trajectory_checkpoints.py`.
2. The config must validate `interval`, `max_checkpoints`, `max_checkpoint_chars`, `max_field_chars`, title strings, and metadata keys at construction time.
3. `ContextWindowAlgorithm` must allow exactly one runtime algorithm among Reflexion, Multi-Provider Agentic Grader, and Trajectory Checkpoints.
4. `ContextWindow.preset.trajectory_checkpoints` and string resolution must work.
5. `AgentRuntimeContextAlgorithms` must dispatch to `TrajectoryCheckpointRuntimeAlgorithm`.
6. The runtime algorithm must call `AgentRuntime._arun_once(...)` and preserve normal direct-loop behavior.
7. `_arun_once(...)` must support an optional algorithm-neutral iteration observer that receives observable iteration snapshots and may append a message before the next model call.
8. The observer must not run after final `isDone`.
9. Every completed observed iteration must emit `trajectory_checkpoint_iteration`.
10. Every injected checkpoint must emit `trajectory_checkpoint_injection`.
11. The algorithm must emit `system_prompt` once at run start.
12. Checkpoint cadence is based on completed runtime iteration count: for `interval=3`, inject after iterations 3, 6, 9, and so on.
13. `max_checkpoints` must cap injected checkpoints.
14. Checkpoint text must include `Reasoning Summary`, `Trajectory`, `Output`, `Score`, and `Feedback` in that order.
15. Reasoning text must be an observable-state summary and must not claim hidden chain-of-thought.
16. Score must be deterministic, in `0.00` to `1.00`, or `N/A` when scoring is disabled.
17. Checkpoint text and fields must be bounded.
18. Raw tool output must be summarized by default; full raw output remains available through existing runtime metadata.
19. Final metadata must include `trajectory_checkpoints` with interval, count, and compact checkpoint records.
20. Existing algorithm, runtime, middleware, and tool-result-admission tests must continue to pass.

### Non-Functional Requirements

- Performance: checkpoint rendering is O(new observable runtime state) and adds no model calls.
- Security: checkpoints do not bypass permissions, middleware policy, or tool-result admission.
- Reliability: default behavior is unchanged when the preset is not selected.
- Observability: metadata records cadence, injection iteration, score, and counts.
- Maintainability: the runtime hook is generic and algorithm-neutral.
- Testability: all tests use fake runners and fake tools.

---

## 5. High-Level Design

The feature adds one runtime context-window algorithm. The public layer defines the config, checkpoint dataclass, pure rendering helpers, deterministic score computation, and bounds. The runtime layer wraps a normal direct agent run by passing an observer into `_arun_once(...)`. The observer receives snapshots, records iteration slots, decides whether the interval boundary has been reached, renders a checkpoint, records the injection slot, and returns checkpoint text for `_arun_once(...)` to append to provider messages.

```text
Agent(..., algorithm=ContextWindow.preset.trajectory_checkpoints)
    -> AgentRuntime.arun(...)
    -> AgentRuntimeContextAlgorithms.return_algorithm()
    -> TrajectoryCheckpointRuntimeAlgorithm.arun()
    -> AgentRuntime._arun_once(..., iteration_observer=observer)
    -> AgentResult + trajectory_checkpoints metadata
```

The main design decision is to add a small observer hook instead of duplicating `_arun_once(...)`. Duplicating the loop would risk regressions in middleware, permissions, internal `isDone`, provider parsing, token accounting, tracing, primitive binding, and tool-result admission.

---

## 6. Detailed Design

### 6.1 Public Algorithm Config

**File(s):** `vidbyte/context/algorithms/trajectory_checkpoints.py`
**Type:** New file

#### What it does

Defines the public immutable configuration and pure checkpoint rendering logic.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpoint:
    iteration: int
    checkpoint_index: int
    reasoning_summary: str
    trajectory: str
    output: str
    score: float | None
    feedback: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    def to_context_text(self, *, max_chars: int, title: str) -> str: ...

@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm:
    interval: int = 3
    max_checkpoints: int = 8
    max_checkpoint_chars: int = 2000
    max_field_chars: int = 600
    include_tool_outputs: bool = False
    score_enabled: bool = True
    checkpoint_title: str = "Runtime Checkpoint"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    def should_checkpoint(self, iteration_count: int, checkpoint_count: int) -> bool: ...
    def build_checkpoint(self, snapshot: AgentIterationSnapshot, *, checkpoint_index: int) -> TrajectoryCheckpoint: ...
```

#### Logic / Algorithm

1. Validate numeric fields and metadata keys.
2. `should_checkpoint(...)` returns true when `iteration_count % interval == 0` and checkpoint count is below the cap.
3. `build_checkpoint(...)` derives bounded reasoning summary, trajectory, output, score, and feedback from observable snapshot fields.
4. `to_context_text(...)` renders required headings in stable order and truncates the final block.

#### Edge Cases & Error Handling

- Invalid numeric config raises `ConfigurationError`.
- Blank title raises `ConfigurationError`.
- Empty observations render explicit fallback text.
- `score_enabled=False` renders `Score` as `N/A`.

### 6.2 Agent Iteration Snapshot Contract

**File(s):** `vidbyte/lib/dataclasses/agents.py`
**Type:** Modified

#### What it does

Adds a small immutable snapshot type representing observable state after one completed non-final runtime iteration.

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

`_arun_once(...)` builds a snapshot after completed non-final iterations. `tool_calls` contains accumulated tool-call contexts, `assistant_output` contains latest no-tool-call text, and metadata excludes raw provider objects.

#### Edge Cases & Error Handling

- Missing provider token usage leaves `tokens_used=None`.
- Iterations with no new tool output still produce a snapshot.

### 6.3 AgentRuntime Observer Hook

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Adds an optional iteration observer parameter to `_arun_once(...)`.

#### Interface / API

```python
IterationObserver = Callable[[AgentIterationSnapshot], str | None]
async def _arun_once(..., iteration_observer: IterationObserver | None = None) -> AgentResult: ...
```

#### Logic / Algorithm

1. Preserve existing behavior when no observer is provided.
2. After no-tool-call iterations and after non-final tool-call iterations, build a snapshot and call the observer.
3. If the observer returns non-empty text, append it via `_assistant_message(...)`.
4. Do not observe after `isDone`.

#### Edge Cases & Error Handling

- Empty observer output is ignored.
- Observer runs after middleware for the iteration and performs no actions.

### 6.4 Runtime Algorithm Adapter

**File(s):** `vidbyte/agents/algorithms/trajectory_checkpoints.py`
**Type:** New file

#### What it does

Runs the normal direct loop with a trajectory checkpoint observer and attaches final metadata.

#### Interface / API

```python
class TrajectoryCheckpointRuntimeAlgorithm:
    name = "trajectory_checkpoints"
    def __init__(self, runtime: AgentRuntime, algorithm: TrajectoryCheckpointAlgorithm) -> None: ...
    async def arun(self, message: str, *, runner: object, context: BaseAgentContext, provider: str, invoke_runner: Callable[..., Any], runner_output_text: Callable[[object], str], runner_output_metadata: Callable[[object], Mapping[str, Any]], metadata: Mapping[str, Any] | None = None, options: Mapping[str, Any] | None = None, trace_context: SpanContext | None = None) -> AgentResult: ...
```

#### Logic / Algorithm

1. Emit `system_prompt`.
2. Create `TrajectoryCheckpointObserver`.
3. Call `_arun_once(..., iteration_observer=observer.observe)`.
4. Merge observer metadata into result metadata without dropping normal metadata.

#### Edge Cases & Error Handling

- Early finish before interval reports zero checkpoints.
- Budget or middleware stops preserve checkpoints already injected.

### 6.5 Runtime Observer

**File(s):** `vidbyte/agents/algorithms/trajectory_checkpoints.py`
**Type:** New class in new file

#### What it does

Tracks seen iterations, records template slots, renders checkpoints, and stores compact metadata.

#### Interface / API

```python
class TrajectoryCheckpointObserver:
    def __init__(self, *, algorithm: TrajectoryCheckpointAlgorithm, recorder: RecorderBase) -> None: ...
    def observe(self, snapshot: AgentIterationSnapshot) -> str | None: ...
    def metadata(self) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Record `trajectory_checkpoint_iteration`.
2. Ignore duplicate iteration counts.
3. If cadence matches, build a checkpoint, record `trajectory_checkpoint_injection`, store metadata, and return text.
4. Otherwise return `None`.

#### Edge Cases & Error Handling

- Duplicate snapshots cannot inject duplicate checkpoints.
- Raw tool outputs are omitted unless explicitly enabled.

### 6.6 Preset Registration

**File(s):** `vidbyte/context/algorithms/tool_results.py`, `vidbyte/context/algorithms/__init__.py`, `vidbyte/context/presets.py`, `vidbyte/context/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Adds the new public algorithm to context-window configuration and exports.

#### Interface / API

```python
ContextWindow.preset.trajectory_checkpoints
ContextWindow.resolve_algorithm("trajectory_checkpoints")
from vidbyte import TrajectoryCheckpointAlgorithm
```

#### Logic / Algorithm

Add a `trajectory_checkpoints` field to `ContextWindowAlgorithm`, include it in active-algorithm validation, register the preset, and export the config.

#### Edge Cases & Error Handling

Multiple runtime algorithms raise; unknown preset strings still raise.

### 6.7 Runtime Dispatcher

**File(s):** `vidbyte/agents/context_algorithms.py`, `vidbyte/agents/algorithms/__init__.py`
**Type:** Modified

#### What it does

Maps the public config to the runtime adapter.

#### Interface / API

```python
AgentRuntimeContextAlgorithms.detect_algorithm() -> "trajectory_checkpoints"
```

#### Logic / Algorithm

Import `TrajectoryCheckpointRuntimeAlgorithm`, detect `self.runtime.algorithm.trajectory_checkpoints`, and return the adapter.

#### Edge Cases & Error Handling

Tool-result-only presets continue to return `None`.

### 6.8 Template Support

**File(s):** `vidbyte/lib/templates/trajectory_checkpoints.py`, `vidbyte/lib/templates/__init__.py`
**Type:** New file, Modified

#### What it does

Adds a reusable template for checkpoint cadence validation.

#### Interface / API

```python
class TrajectoryCheckpointContextWindowTemplate(ContextWindowTemplate):
    def __init__(self, *, iterations: int, interval: int = 3, max_checkpoints: int | None = None) -> None: ...
```

#### Logic / Algorithm

Start with `system_prompt`, append `trajectory_checkpoint_iteration` for each iteration, and append `trajectory_checkpoint_injection` at interval boundaries until the max cap is reached.

#### Edge Cases & Error Handling

`iterations=0` produces only `system_prompt`; `interval <= 0` raises `ValueError`.

### 6.9 Documentation And Skill Updates

**File(s):** `README.md`, `skills/vidbyte-sdk/context-window-templates.md`, `skills/vidbyte-sdk/adding-context-window-algorithms.md`
**Type:** Modified

#### What it does

Documents usage, slot names, and the observer-hook pattern.

#### Interface / API

```python
agent = Agent(..., algorithm=ContextWindow.preset.trajectory_checkpoints)
```

#### Logic / Algorithm

Add concise README and skill sections.

#### Edge Cases & Error Handling

Docs must not imply hidden chain-of-thought or authoritative correctness scoring.

---

## 7. Data Model Changes

### 7.1 `TrajectoryCheckpoint`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpoint: ...
```

**Migration strategy:** N/A - in-memory SDK dataclass.

### 7.2 `TrajectoryCheckpointAlgorithm`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class TrajectoryCheckpointAlgorithm: ...
```

**Migration strategy:** N/A - in-memory SDK config.

### 7.3 `AgentIterationSnapshot`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class AgentIterationSnapshot: ...
```

**Migration strategy:** N/A - internal runtime snapshot.

### 7.4 `TrajectoryCheckpointContextWindowTemplate`

**Change type:** New

```python
class TrajectoryCheckpointContextWindowTemplate(ContextWindowTemplate): ...
```

**Migration strategy:** N/A - testing utility.

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
    content="...",
    metadata={"trajectory_checkpoints": {"interval": 3, "checkpoint_count": 2}},
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid config raises `ConfigurationError`. |
| N/A | Unknown preset string raises `ValueError`. |
| N/A | Budget stop returns normal metadata with any checkpoints already injected. |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/trajectory-checkpoint-context-window.md` | Design doc for this feature |
| CREATE | `vidbyte/context/algorithms/trajectory_checkpoints.py` | Public config, checkpoint dataclass, deterministic rendering |
| CREATE | `vidbyte/agents/algorithms/trajectory_checkpoints.py` | Runtime adapter and observer |
| CREATE | `vidbyte/lib/templates/trajectory_checkpoints.py` | Template for checkpoint cadence validation |
| CREATE | `tests/test_trajectory_checkpoint_algorithm.py` | Public API, runtime, renderer, and metadata tests |
| CREATE | `scripts/test-trajectory-checkpoints.py` | Executable verification script for all design test cases |
| MODIFY | `vidbyte/lib/dataclasses/agents.py` | Add `AgentIterationSnapshot` |
| MODIFY | `vidbyte/agents/runtime.py` | Add optional iteration observer hook and snapshot creation |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Dispatch trajectory checkpoint algorithm |
| MODIFY | `vidbyte/agents/algorithms/__init__.py` | Export runtime adapter |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add algorithm field and active-algorithm validation |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export public algorithm config |
| MODIFY | `vidbyte/context/presets.py` | Add preset |
| MODIFY | `vidbyte/context/__init__.py` | Export public algorithm config |
| MODIFY | `vidbyte/lib/templates/__init__.py` | Export template class |
| MODIFY | `vidbyte/__init__.py` | Export public algorithm config |
| MODIFY | `tests/test_context_window_templates.py` | Add template construction tests |
| MODIFY | `tests/test_agent_runtime.py` | Add observer hook regression tests |
| MODIFY | `README.md` | Document new preset |
| MODIFY | `skills/vidbyte-sdk/context-window-templates.md` | Document slot sequence and tests |
| MODIFY | `skills/vidbyte-sdk/adding-context-window-algorithms.md` | Note observer-hook pattern for within-loop algorithms |

Summary: 6 files created, 15 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_preset_exposes_trajectory_checkpoint_algorithm`. [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_resolve_algorithm_accepts_trajectory_checkpoints_string`. [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_rejects_zero_interval`. [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_rejects_empty_checkpoint_title`. [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_config_rejects_non_string_metadata_key`. [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_context_window_algorithm_rejects_multiple_runtime_algorithms`. [Hidden Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_checkpoint_renderer_outputs_required_sections_in_order`. [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_checkpoint_renderer_bounds_long_fields`. [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_score_disabled_renders_na`. [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_score_heuristic_penalizes_failed_tool_calls`. [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_dispatcher_detects_and_returns_runtime_algorithm`. [Hidden Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_injects_checkpoint_after_interval`. [Integration]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_does_not_inject_before_interval`. [Silent Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_metadata_reports_zero_checkpoints_for_early_finish`. [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_respects_max_checkpoints`. [Edge Case]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_checkpoint_metadata_preserves_normal_metadata`. [Hidden Failure]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_checkpoint_omits_raw_tool_output_by_default`. [Hidden Assumption]
- `tests/test_trajectory_checkpoint_algorithm.py` -> `test_runtime_checkpoint_can_include_bounded_tool_output_when_enabled`. [Edge Case]
- `tests/test_context_window_templates.py` -> `test_trajectory_template_zero_iterations`. [Edge Case]
- `tests/test_context_window_templates.py` -> `test_trajectory_template_interval_two`. [Silent Failure]
- `tests/test_context_window_templates.py` -> `test_trajectory_template_respects_max_checkpoints`. [Edge Case]
- `tests/test_agent_runtime.py` -> `test_iteration_observer_default_none_preserves_existing_behavior`. [Hidden Assumption]
- `tests/test_agent_runtime.py` -> `test_iteration_observer_appends_returned_message`. [Hidden Failure]
- `tests/test_agent_runtime.py` -> `test_iteration_observer_not_called_after_is_done`. [Silent Failure]

### Integration Tests

- Full direct-runtime fake-runner flow with assistant output, tool call, checkpoint injection, and `isDone`.
- `interval=1` with `max_checkpoints=2` verifies cap behavior.
- Template integration verifies recorder slots pass `TrajectoryCheckpointContextWindowTemplate`.

### Manual / QA Test Cases

1. Given `ContextWindow.preset.trajectory_checkpoints`, when two non-final iterations complete, then the next runner call includes a `Runtime Checkpoint`. [Integration]
2. Given `interval=3`, when only two iterations complete before `isDone`, then metadata reports zero checkpoints. [Edge Case]
3. Given `interval=1, max_checkpoints=1`, when three non-final iterations complete, then exactly one checkpoint is injected. [Silent Failure]
4. Given a recorder and matching template, then `template.validate(recorder) == []`. [Hidden Failure]
5. Given a long tool output and default `include_tool_outputs=False`, checkpoint text omits raw output. [Hidden Assumption]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `dataclasses` | Python >=3.11 | Frozen dataclasses | Existing dependency only |
| Python stdlib `typing` / `collections.abc` | Python >=3.11 | Callable and mapping contracts | Existing dependency only |
| pydantic | `>=2,<3` | Existing tool validation path | No new use |

No new third-party dependencies or external services are introduced.

---

## 12. Rollout & Deployment

- No feature flag is required; default behavior is unchanged unless the preset is selected.
- This is not a breaking change; `_arun_once(...)` observer parameter is optional and keyword-only.
- Rollout: commit this design doc first, implement config and runtime hook, add adapter and template, add tests and script, update docs, then run compile, focused tests, full unittest discovery, and the verification script.
- Rollback: revert the feature branch merge commit; remove preset, hook, adapter, tests, script, and docs.

---

## 13. Open Questions

- [ ] Should `include_tool_outputs=True` be allowed, or should checkpoint text always avoid tool output?
- [ ] Should heuristic `Score` be enabled by default, or default to `N/A`?
- [ ] Should trajectory checkpoints compose with tool-result admission presets?
- [ ] Should checkpoint messages be appended as `assistant` messages, or wait for a future dynamic system/developer message mechanism?
- [ ] Should `BaseAgent` expose recorder support, or should recorder usage remain runtime-test-only?

---

## 14. Alternatives Considered

### Alternative 1: Model-Visible Checkpoint Tool

- What: Add a built-in tool the model can call to create runtime checkpoints.
- Why rejected: A model-chosen tool cannot guarantee every-`n` cadence or structural correctness.

### Alternative 2: Copy `_arun_once(...)` Into The Algorithm

- What: Implement the whole linear loop inside the algorithm.
- Why rejected: It would duplicate tool execution, permissions, middleware, provider parsing, token accounting, tracing, primitive binding, and `isDone` behavior.

### Alternative 3: Emit Global `agent_iteration` Slots

- What: Add base runtime slot emission for every run.
- Why rejected: Existing templates intentionally omit base runtime slots; global emission risks unrelated regressions.

### Alternative 4: LLM Judge For Score And Feedback

- What: Call another model every checkpoint.
- Why rejected: Adds latency, cost, provider dependencies, and new failure modes.

### Alternative 5: Store Checkpoints In `ContextManager` Primitives

- What: Upsert checkpoints into the primitives zone.
- Why rejected: Algorithms should not mutate caller-owned context managers, and not all agents have a manager.
