# Design Doc: Context Window Lifecycle Algorithms

**Status:** Draft
**Author:** Codex
**Created:** 2026-05-25
**Last Updated:** 2026-05-25

---

## 1. Overview

This feature expands the PR #44 context management foundation from tool-result admission into first-party context-window lifecycle algorithms. It adds SDK skills that document how context management and context-window algorithms work, then adds two new presets: a deterministic reasoning-trace preset that inserts model-visible operational trace tokens after each direct agent runtime iteration, and a plan-then-implement preset that creates a plan artifact before normal execution and attaches it to the context window.

---

## 2. Goals & Non-Goals

### Goals

- Add context management skill docs under `skills/vidbyte-sdk/` covering context primitives, context managers, context-window algorithms, preset usage, and the process for adding new algorithms.
- Preserve the public `algorithm=ContextWindow.preset.<name>` agent option introduced by PR #44.
- Add reasoning-trace presets with small, medium, and large trace sizes.
- Let developers customize the reasoning-trace size and trace system prompt without writing runtime code.
- Insert a deterministic, model-visible reasoning trace after each non-terminal direct agent runtime iteration.
- Ensure reasoning traces do not expose hidden raw tool output when paired with raw-output hiding algorithms.
- Add a plan-then-implement preset that creates a plan artifact from the original request before normal direct runtime execution.
- Attach the plan artifact to the agent context window so subsequent model calls see the plan through existing `BaseContext.build_context()`.
- Keep full raw runtime data in metadata/tool-call context while controlling only what becomes model-visible.
- Add focused unit tests for preset resolution, trace rendering, plan artifact insertion, runtime message ordering, and raw-output leakage prevention.

### Non-Goals

- No model-weight, fine-tuning, or training behavior.
- No provider-specific prompt format overhaul.
- No general context renderer/compiler abstraction beyond the minimal lifecycle hooks needed for these algorithms.
- No persistent memory store, database, vector retrieval, or cross-session plan storage.
- No automatic chain-of-thought extraction. The reasoning trace is a deterministic operational scaffold based on visible runtime state, not a claim to expose hidden model thoughts.
- No lifecycle control inside arbitrary strategy implementations. These hooks apply to the direct text agent runtime; strategies can receive the initial context but their internal model calls remain strategy-owned.
- No changes to image or video one-shot runner behavior.

---

## 3. Background & Context

PR #44 split the context system into public primitives, presets, and algorithm implementations. Context item primitives now live under `vidbyte/context/primitives.py`, the preset registry lives in `vidbyte/context/presets.py`, and algorithm behavior lives under `vidbyte/context/algorithms/`. `ContextWindow.preset.<name>` remains the developer-facing API.

The current `ContextWindowAlgorithm` only controls tool-result admission through `model_visible_tool_result(...)`. `AgentRuntime._process_tool_call(...)` uses that hook after a tool executes, then appends the formatted visible tool result to the provider message list. This works for `no_raw_tool_outputs`, but it does not provide lifecycle hooks for inserting context after model calls or creating context before the first implementation call.

Direct agent execution is centralized in `vidbyte/agents/runtime.py`. `AgentRuntime.arun(...)` builds per-iteration call options from the immutable `BaseAgentContext`, invokes the runner, parses tool calls, executes tools, appends provider messages, and loops until `isDone`, `max_iterations`, or `max_tokens`. This is the correct layer for lifecycle algorithms because it owns ordered provider messages and the repeated model-call loop.

The existing context dataclasses already support artifacts through `ContextArtifact` and render them in `BaseContext.build_context()`. The plan-then-implement algorithm should use that existing artifact path rather than inventing a new plan store. The existing skills under `skills/vidbyte-sdk/` define package rules, so new context-management skill docs should be added there and linked from the main SDK skill.

This design assumes implementation branches from PR #44 (`ai/resolve-pr-42-comments`) or from `main` after PR #44 merges. `main` alone does not yet contain the context-window split that this feature extends.

---

## 4. Requirements

### Functional Requirements

1. The SDK must document context management concepts in `skills/vidbyte-sdk/context-management.md`.
2. The SDK must document context-window algorithm authoring rules in `skills/vidbyte-sdk/context-window-algorithms.md`.
3. The main `skills/vidbyte-sdk/SKILL.md` must link to the new context-management skill docs.
4. `ContextWindowAlgorithm` must support existing tool-result admission behavior without breaking existing presets.
5. `ContextWindowAlgorithm` must support optional lifecycle behavior for initial planning and after-iteration reasoning traces.
6. The preset registry must expose default reasoning trace presets: small, medium, and large.
7. The preset registry must expose a configurable factory for reasoning trace algorithms with custom size and optional trace system prompt.
8. The preset registry must expose `ContextWindow.preset.plan_then_implement`.
9. The preset registry must expose a configurable factory for plan-then-implement algorithms with custom planner prompt, artifact name, and maximum plan length.
10. `ContextWindow.resolve_algorithm(...)` must continue to accept `None`, preset objects, and preset-name strings.
11. The reasoning-trace algorithm must append a model-visible trace message after each non-terminal direct runtime iteration.
12. The reasoning trace must be deterministic: given the same request, iteration number, visible assistant text, tool names, tool statuses, and config, it must render the same trace text.
13. Reasoning trace size must affect the amount of inserted trace content.
14. The reasoning-trace config must allow a trace system prompt that is included with the inserted trace message.
15. Reasoning traces must not include raw tool result output unless that output is already present in model-visible provider messages.
16. The plan-then-implement algorithm must create a `ContextArtifact` before normal implementation begins.
17. The plan artifact must be attached to the `BaseAgentContext.artifacts` sequence before the first normal implementation model call.
18. The plan artifact must render through existing `BaseContext.build_context()` without adding a separate renderer.
19. The plan-then-implement algorithm must use the same runner abstraction as the direct runtime for the planning call.
20. If the planner response is empty or unusable, the runtime must attach a deterministic fallback plan artifact rather than failing silently.
21. Runtime metadata must record whether a plan artifact was created and whether fallback planning was used.
22. Runtime metadata must record how many reasoning trace messages were inserted.
23. Existing direct runtime behavior must be unchanged when `algorithm` is `None` or `ContextWindow.preset.default`.
24. Existing tests for raw, compacted, and hidden tool output must continue to pass.

### Non-Functional Requirements

- Performance: reasoning trace insertion must be local deterministic string rendering. Plan-then-implement may add one extra model call before normal execution.
- Scalability: trace content must be bounded by size presets; plan content must be bounded by `max_plan_chars`.
- Security: lifecycle traces must never reintroduce raw tool output hidden by `no_raw_tool_outputs` or future redaction algorithms.
- Reliability: a planner failure should either surface clearly through `AgentExecutionError` or attach a deterministic fallback plan, depending on config. The default preset uses fallback to preserve normal execution.
- Observability: runtime metadata must expose inserted trace count, plan artifact name, and fallback status.
- Compatibility: existing public imports and preset names remain valid.

---

## 5. High-Level Design

The implementation keeps `ContextWindowAlgorithm` as the single algorithm object attached to an agent, but expands it from a tool-result-only config into a runtime lifecycle config. It will still hold `tool_result_admission`, `max_tool_result_chars`, and metadata, and it will gain optional `reasoning_trace` and `plan_then_implement` config fields. This keeps preset usage simple while making algorithms composable by constructing a custom `ContextWindowAlgorithm`.

The runtime will gain two internal hook points. The first hook runs once after `before_run` middleware and before the normal direct runtime loop. If the selected algorithm has plan-then-implement config, the runtime asks the runner for a plan, bounds the plan text, attaches it as a `ContextArtifact`, and continues with the updated context. The second hook runs after each non-terminal iteration, after visible assistant/tool messages for that iteration have been appended. If the selected algorithm has reasoning-trace config, the runtime renders a deterministic trace message and appends it to the provider message list for the next model call.

Data flow:

```text
Agent(..., algorithm=ContextWindow.preset.plan_then_implement)
        |
        v
BaseAgent stores normalized ContextWindowAlgorithm
        |
        v
AgentRuntime.arun(...)
        |
        +--> optional pre-run plan call -> ContextArtifact("Plan") -> updated BaseAgentContext
        |
        v
normal direct agent loop
        |
        +--> after each non-terminal iteration -> deterministic reasoning trace message
        |
        v
next runner call sees context.build_context() + ordered provider messages
```

The design deliberately avoids exposing hidden chain-of-thought. The reasoning trace is a model-visible operational note: what happened in the last visible step, what constraints still matter, what reasonable next routes are available, and when the agent should finish. This is aligned with context-window management because it changes the context the model sees, but it does not attempt to read or reveal private model reasoning.

---

## 6. Detailed Design

### 6.1 Context Algorithm Config Types

**File(s):** `vidbyte/context/algorithms/types.py`
**Type:** New file

#### What it does

Defines typed configs and event payloads used by lifecycle algorithms.

#### Interface / API

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vidbyte.tools.types import ToolCallContext


class ReasoningTraceSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass(frozen=True, slots=True)
class ReasoningTraceConfig:
    size: ReasoningTraceSize = ReasoningTraceSize.MEDIUM
    system_prompt: str | None = None
    role: str = "user"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlanThenImplementConfig:
    artifact_name: str = "Plan"
    planner_prompt: str | None = None
    max_plan_chars: int = 4000
    fallback_on_empty: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextWindowMessage:
    role: str
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContextWindowIterationEvent:
    request: str
    iteration_count: int
    assistant_output: str | None = None
    tool_contexts: Sequence[ToolCallContext] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

#### Logic / Algorithm

1. Coerce string sizes into `ReasoningTraceSize` at preset/factory construction time.
2. Keep config objects frozen and side-effect free.
3. Use `ContextWindowIterationEvent` as the safe input to trace rendering.

#### Edge Cases & Error Handling

- Unknown size strings raise `ValueError` from the preset factory.
- Empty custom prompts are treated as `None`.
- `max_plan_chars <= 0` means no truncation, matching the existing `_compact_output` convention.

---

### 6.2 ContextWindowAlgorithm Lifecycle Fields

**File(s):** `vidbyte/context/algorithms/tool_results.py`
**Type:** Modified

#### What it does

Extends the existing algorithm dataclass with optional lifecycle config while preserving tool-result behavior.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    reasoning_trace: ReasoningTraceConfig | None = None
    plan_then_implement: PlanThenImplementConfig | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def model_visible_tool_result(self, call: ToolCall, result: ToolResult) -> ToolResult: ...
```

#### Logic / Algorithm

1. Keep `model_visible_tool_result(...)` unchanged for raw, compact, and hidden tool outputs.
2. Add fields only; lifecycle execution remains in `AgentRuntime` so the algorithm object remains declarative.
3. Preserve imports from `vidbyte.context.algorithms` and `vidbyte.context.window`.

#### Edge Cases & Error Handling

- Existing code that constructs `ContextWindowAlgorithm(name="x")` continues to work.
- Existing preset objects remain valid.

---

### 6.3 Reasoning Trace Algorithm

**File(s):** `vidbyte/context/algorithms/reasoning_trace.py`
**Type:** New file

#### What it does

Renders deterministic, model-visible reasoning trace messages from visible runtime state.

#### Interface / API

```python
DEFAULT_REASONING_TRACE_PROMPT = (
    "Maintain a concise operational trace for the next model call. "
    "Do not expose hidden chain-of-thought. Track visible state, constraints, next actions, and finish criteria."
)

def render_reasoning_trace(
    config: ReasoningTraceConfig,
    event: ContextWindowIterationEvent,
) -> ContextWindowMessage:
    ...
```

#### Logic / Algorithm

1. Start with a stable heading: `Context window reasoning trace`.
2. Include the configured trace system prompt.
3. Include the current iteration number and original request excerpt.
4. Include the last visible assistant output excerpt when present.
5. Include tool names and statuses from the current iteration, but not raw tool output.
6. Render size-specific content:
   - small: current state, next action, finish check.
   - medium: small plus constraints and alternate routes.
   - large: medium plus risk checks, validation checks, and route tradeoffs.
7. Return a `ContextWindowMessage(role=config.role, content=rendered, metadata=...)`.

#### Edge Cases & Error Handling

- If no assistant output or tool contexts exist, render a generic "continue from the request" state.
- If a tool failed or was denied, mention only name and state.
- Do not inspect `ToolCallContext.result.output`; this prevents hidden raw output from leaking.

---

### 6.4 Plan Then Implement Algorithm

**File(s):** `vidbyte/context/algorithms/plan_then_implement.py`
**Type:** New file

#### What it does

Builds planner prompts, bounds plan text, and creates plan artifacts for the runtime to attach before normal execution.

#### Interface / API

```python
DEFAULT_PLAN_PROMPT = (
    "Create a concise implementation plan for the user's request. "
    "Return only the plan. Include objective, steps, risks, and verification."
)

def build_plan_prompt(
    request: str,
    context_text: str,
    config: PlanThenImplementConfig,
) -> str:
    ...

def plan_artifact_from_text(
    plan_text: str,
    request: str,
    config: PlanThenImplementConfig,
    *,
    fallback_used: bool = False,
) -> ContextArtifact:
    ...

def fallback_plan(request: str) -> str:
    ...
```

#### Logic / Algorithm

1. Render a planner prompt from the request, current context text, and custom/default planner prompt.
2. The runtime sends this prompt to the same runner with no tools.
3. Extract text with the existing `runner_output_text` callback.
4. If the planner text is empty and `fallback_on_empty` is true, use `fallback_plan(...)`.
5. Bound plan text to `max_plan_chars`.
6. Return `ContextArtifact(name=config.artifact_name, content=plan_text, artifact_type="plan", metadata=...)`.

#### Edge Cases & Error Handling

- Empty runner output uses fallback by default.
- Planner exceptions should propagate through the existing model-error middleware path where practical; otherwise they surface as `AgentExecutionError`.
- The planner call does not receive tool schemas, so it cannot act before planning.

---

### 6.5 Preset Registry

**File(s):** `vidbyte/context/presets.py`
**Type:** Modified

#### What it does

Adds first-party presets and factories for the two new lifecycle algorithms.

#### Interface / API

```python
class ContextWindowPresets:
    @property
    def reasoning_trace_small(self) -> ContextWindowAlgorithm: ...

    @property
    def reasoning_trace_medium(self) -> ContextWindowAlgorithm: ...

    @property
    def reasoning_trace_large(self) -> ContextWindowAlgorithm: ...

    def reasoning_trace(
        self,
        *,
        size: ReasoningTraceSize | str = ReasoningTraceSize.MEDIUM,
        system_prompt: str | None = None,
    ) -> ContextWindowAlgorithm: ...

    @property
    def plan_then_implement(self) -> ContextWindowAlgorithm: ...

    def plan_then_implement_with(
        self,
        *,
        planner_prompt: str | None = None,
        artifact_name: str = "Plan",
        max_plan_chars: int = 4000,
    ) -> ContextWindowAlgorithm: ...
```

#### Logic / Algorithm

1. Fixed properties support string resolution, for example `algorithm="reasoning_trace_medium"`.
2. Factories support parameterized usage, for example `ContextWindow.preset.reasoning_trace(size="large")`.
3. Preset names are stable and human-readable.

#### Edge Cases & Error Handling

- String resolution only works for fixed preset properties, not factories requiring arguments.
- Invalid sizes raise `ValueError`.

---

### 6.6 Runtime Lifecycle Hook Integration

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Executes pre-run planning and after-iteration trace insertion inside the direct text runtime loop.

#### Interface / API

No public method signature changes are required.

Internal helpers:

```python
async def _prepare_algorithm_context(...) -> tuple[BaseAgentContext, int | None]: ...

def _append_reasoning_trace_if_needed(
    self,
    messages: list[dict[str, Any]],
    *,
    request: str,
    iteration_count: int,
    assistant_output: str | None,
    current_iteration_contexts: Sequence[ToolCallContext],
) -> int:
    ...
```

#### Logic / Algorithm

1. In `arun(...)`, after `before_run` middleware succeeds, call `_prepare_algorithm_context(...)`.
2. If no plan config exists, return the original context.
3. If plan config exists, invoke the runner once with a planner prompt and no tools.
4. Convert planner text into a plan artifact and replace the local context with `dataclasses.replace(context, artifacts=...)`.
5. During each loop, track tool contexts added during the current iteration.
6. In the no-tool-call path, append the assistant message, then append a reasoning trace if configured.
7. In the tool-call path, append visible tool messages as today, then append a reasoning trace if configured and no terminal `isDone` occurred.
8. Increment trace counters in runtime metadata.

#### Edge Cases & Error Handling

- Do not append a trace after terminal `isDone` because there is no next model call.
- Do not append a trace after middleware abort.
- If max iterations stops the loop, preserve the trace count accumulated so far.
- Preserve provider message ordering: visible tool result messages for the iteration come before the trace message.

---

### 6.7 Public Exports

**File(s):** `vidbyte/context/algorithms/__init__.py`, `vidbyte/context/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Exports the new config types for developers who need custom algorithms.

#### Interface / API

```python
from vidbyte import (
    ContextWindow,
    ContextWindowAlgorithm,
    ReasoningTraceConfig,
    ReasoningTraceSize,
    PlanThenImplementConfig,
)
```

#### Logic / Algorithm

1. Re-export only stable config types and enums.
2. Keep implementation helper functions under `vidbyte.context.algorithms`.

#### Edge Cases & Error Handling

- Existing imports from `vidbyte` and `vidbyte.context` remain valid.

---

### 6.8 SDK Skill Docs

**File(s):** `skills/vidbyte-sdk/context-management.md`, `skills/vidbyte-sdk/context-window-algorithms.md`, `skills/vidbyte-sdk/SKILL.md`, `skills/vidbyte-sdk-doc/SKILL.md`
**Type:** New files and modified files

#### What it does

Adds local instructions for future agents working on context management.

#### Interface / API

N/A - Markdown skill documentation, not runtime API.

#### Logic / Algorithm

1. `context-management.md` explains primitives, managers, artifacts, context ownership, and when to use `AgentInput` vs agent defaults.
2. `context-window-algorithms.md` explains algorithm presets, lifecycle hooks, adding new algorithms, required files, required tests, leakage rules, and docs updates.
3. `SKILL.md` links these docs in the context rules section.
4. `vidbyte-sdk-doc/SKILL.md` updates the repository reference with the new algorithms and docs.

#### Edge Cases & Error Handling

- Skill docs must not describe unimplemented algorithms until the implementation PR lands.
- The docs should explicitly say reasoning traces are model-visible operational scaffolds, not hidden chain-of-thought.

---

### 6.9 README Examples

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents basic usage for the new presets.

#### Interface / API

```python
from vidbyte import Agent, ContextWindow

agent = Agent(
    name="builder",
    system_prompt="Work carefully.",
    runner=my_runner,
    tools=[lookup_tool],
    algorithm=ContextWindow.preset.reasoning_trace_medium,
)

planning_agent = Agent(
    name="planner",
    system_prompt="Plan then implement.",
    runner=my_runner,
    tools=[edit_tool],
    algorithm=ContextWindow.preset.plan_then_implement,
)
```

#### Logic / Algorithm

N/A - Documentation only.

#### Edge Cases & Error Handling

- Examples should avoid advanced internal runners and use existing `Agent` style.

---

## 7. Data Model Changes

### 7.1 `ContextWindowAlgorithm`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class ContextWindowAlgorithm:
    name: str
    tool_result_admission: ToolResultAdmission = ToolResultAdmission.RAW
    max_tool_result_chars: int = 600
    reasoning_trace: ReasoningTraceConfig | None = None
    plan_then_implement: PlanThenImplementConfig | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - additive dataclass fields with defaults.

- Forward migration: existing callers need no changes.
- Rollback plan: remove new fields and preset references if the feature is reverted.

### 7.2 `ReasoningTraceConfig`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class ReasoningTraceConfig:
    size: ReasoningTraceSize = ReasoningTraceSize.MEDIUM
    system_prompt: str | None = None
    role: str = "user"
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - new runtime config type.

### 7.3 `PlanThenImplementConfig`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class PlanThenImplementConfig:
    artifact_name: str = "Plan"
    planner_prompt: str | None = None
    max_plan_chars: int = 4000
    fallback_on_empty: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - new runtime config type.

---

## 8. API Changes

### 8.1 Python SDK Preset API

**Change type:** Modified

**Request:**

```python
agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    runner=my_runner,
    algorithm=ContextWindow.preset.reasoning_trace_medium,
)
```

**Response:**

```python
AgentMessage(
    content="...",
    metadata={
        "context_window_reasoning_trace_count": 2,
        ...
    },
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | `ValueError` for unknown preset name or invalid reasoning trace size |
| N/A | `AgentExecutionError` if the planner model call fails and fallback is disabled |

### 8.2 Python SDK Plan Preset API

**Change type:** New

**Request:**

```python
agent = Agent(
    name="worker",
    system_prompt="Plan before acting.",
    runner=my_runner,
    tools=[edit_tool],
    algorithm=ContextWindow.preset.plan_then_implement,
)
```

**Response:**

```python
AgentMessage(
    content="...",
    metadata={
        "context_window_plan_artifact": "Plan",
        "context_window_plan_fallback_used": False,
        ...
    },
)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Empty planner output uses fallback by default |
| N/A | Planner exception follows existing runner/middleware error behavior |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/context-window-lifecycle-algorithms.md` | Approved design for lifecycle context-window algorithms |
| CREATE | `skills/vidbyte-sdk/context-management.md` | Skill doc for context primitives, managers, and usage |
| CREATE | `skills/vidbyte-sdk/context-window-algorithms.md` | Skill doc for adding and using context-window algorithms |
| CREATE | `vidbyte/context/algorithms/types.py` | Shared config/event/message types for lifecycle algorithms |
| CREATE | `vidbyte/context/algorithms/reasoning_trace.py` | Deterministic reasoning trace rendering algorithm |
| CREATE | `vidbyte/context/algorithms/plan_then_implement.py` | Plan prompt, fallback, and plan artifact helpers |
| CREATE | `tests/test_context_window_algorithms.py` | Focused tests for lifecycle algorithm configs and renderers |
| MODIFY | `vidbyte/context/algorithms/tool_results.py` | Add lifecycle config fields to `ContextWindowAlgorithm` |
| MODIFY | `vidbyte/context/algorithms/__init__.py` | Export new config types and algorithm helpers |
| MODIFY | `vidbyte/context/presets.py` | Add reasoning trace and plan-then-implement presets/factories |
| MODIFY | `vidbyte/context/__init__.py` | Re-export stable config types |
| MODIFY | `vidbyte/__init__.py` | Add root convenience exports for stable config types |
| MODIFY | `vidbyte/agents/runtime.py` | Add pre-run plan and after-iteration trace lifecycle hooks |
| MODIFY | `tests/test_agent_runtime.py` | Cover runtime insertion of traces and plan artifacts |
| MODIFY | `tests/test_context_management.py` | Cover preset names and string resolution |
| MODIFY | `README.md` | Document new preset usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Link new context management skill docs and rules |
| MODIFY | `skills/vidbyte-sdk-doc/SKILL.md` | Update repository reference for lifecycle algorithms |

No files will be deleted.

---

## 10. Testing Plan

### Unit Tests

- `tests/test_context_window_algorithms.py` -> `test_reasoning_trace_small_renders_bounded_operational_note`
- `tests/test_context_window_algorithms.py` -> `test_reasoning_trace_large_includes_routes_risks_and_finish_criteria`
- `tests/test_context_window_algorithms.py` -> `test_reasoning_trace_does_not_include_tool_result_output`
- `tests/test_context_window_algorithms.py` -> `test_plan_artifact_bounds_long_plan_text`
- `tests/test_context_window_algorithms.py` -> `test_plan_fallback_is_deterministic`
- `tests/test_context_management.py` -> `test_lifecycle_context_window_presets_are_named_algorithms`
- `tests/test_agent_runtime.py` -> `test_runtime_appends_reasoning_trace_after_non_terminal_assistant_iteration`
- `tests/test_agent_runtime.py` -> `test_runtime_appends_reasoning_trace_after_tool_iteration_without_leaking_hidden_output`
- `tests/test_agent_runtime.py` -> `test_runtime_plan_then_implement_attaches_plan_artifact_before_first_normal_call`
- `tests/test_agent_runtime.py` -> `test_default_algorithm_does_not_insert_lifecycle_messages`

### Integration Tests

- Run direct text agent runtime with a fake runner that first returns ordinary text and then `isDone`; verify the second runner call sees a reasoning trace message.
- Run direct text agent runtime with a fake runner that first returns a tool call and then `isDone`; verify visible tool result comes before reasoning trace.
- Run plan-then-implement with a fake runner; verify the first call is the planner call and the second normal call receives a context containing `Artifacts:\nPlan (plan):`.

### Manual / QA Test Cases

1. Given an agent configured with `ContextWindow.preset.reasoning_trace_small`, when it runs for two iterations, then the second model call includes a short context trace.
2. Given an agent configured with `ContextWindow.preset.reasoning_trace(size="large", system_prompt="Track options.")`, when it runs, then the trace includes the custom trace prompt and larger route/check sections.
3. Given an agent configured with `ContextWindow.preset.plan_then_implement`, when it receives a request, then it first creates a plan artifact and then performs the normal implementation loop.
4. Given an agent configured with hidden tool outputs and a reasoning trace through a custom `ContextWindowAlgorithm`, when a tool returns secret output, then the trace and provider messages do not contain the secret.

Verification commands:

```powershell
python -m unittest tests.test_context_window_algorithms tests.test_context_management tests.test_agent_runtime
python -m unittest discover -s tests
python -m compileall vidbyte
```

Attempt if available:

```powershell
python -m ruff check .
python -m flake8 .
python -m mypy .
```

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | Python >=3.11 | Dataclasses, enums, typing, `dataclasses.replace` | Low |
| Existing runner abstraction | Internal SDK contract | Plan preflight call and normal direct runtime calls | Medium: planner call consumes one extra model call |
| Existing `unittest` suite | Standard library | Regression coverage | Low |

No new package dependencies or external services are required.

---

## 12. Rollout & Deployment

- Feature flags: none.
- Breaking change: no. Existing algorithms and agent construction remain source compatible.
- Migration path: developers opt in with `algorithm=ContextWindow.preset.reasoning_trace_medium` or `algorithm=ContextWindow.preset.plan_then_implement`.
- Deployment order: PR #44 must merge first, or this feature branch must be based on PR #44.
- Rollback procedure: revert the implementation commits; existing default context algorithm behavior should remain unchanged.

---

## 13. Open Questions

- [ ] Should the implementation branch be based directly on PR #44 (`ai/resolve-pr-42-comments`) or wait until PR #44 is merged into `main`?
- [ ] Should `plan_then_implement` count the planner call in a new metadata field only, or should it also affect existing model-call budget accounting?
- [ ] Should the default plan preset use fallback-on-empty only, or should it also fallback on planner exceptions?
- [ ] Do we want a first-class composition helper such as `ContextWindow.preset.compose(...)`, or is direct `ContextWindowAlgorithm(...)` construction enough for combining `no_raw_tool_outputs` with reasoning traces in this PR?

---

## 14. Alternatives Considered

### Alternative 1: Implement Reasoning Trace As A Tool

- What: Add a built-in tool that the model can call to write reasoning traces.
- Why rejected: The user specifically asked for deterministic insertion after every model call. A model-called tool would be optional and non-deterministic.

### Alternative 2: Append Hidden Chain-of-Thought

- What: Ask the model to reveal and persist its private reasoning.
- Why rejected: The SDK should not claim access to hidden model thought. A deterministic operational scaffold is safer, auditable, and aligned with model-visible context engineering.

### Alternative 3: Build A Full Context Renderer

- What: Add a renderer/compiler layer for all context items and algorithms.
- Why rejected: This would exceed the requested scope. The existing `BaseContext.build_context()` path is sufficient for plan artifacts, and provider messages are sufficient for per-iteration traces.

### Alternative 4: Make Plan-Then-Implement Fully Deterministic

- What: Generate a static generic plan from the request without a planner model call.
- Why rejected: The requested algorithm is useful because it creates a request-specific plan artifact. A deterministic fallback remains available for empty planner output, but the default preset should use the runner to create the plan.
