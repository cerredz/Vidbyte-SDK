# Design Doc: Continual Trace Agent

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

---

## 1. Overview

This feature adds first-class continual trace artifacts to direct text agents. A developer will pass one `trace=` option to `Agent` or `BaseAgent`, built with `TraceOption.continual(...)`, and the normal agent loop will periodically delegate to a built-in `ContinualTraceAgent`. That trace agent reads the main agent's current context window, the developer-supplied or prebuilt trace schema, and the trace artifact so far, then uses a small tool-calling loop to update the artifact. The final `AgentMessage` returns the main result normally and includes the accumulated trace artifact in `reply.metadata["trace"]`.

---

## 2. Goals & Non-Goals

### Goals

- Add a single public `trace` constructor option to `BaseAgent`.
- Add `TraceOption.continual(...)` as the only public configuration entry point for continual tracing.
- Add a thin `ContinualTraceAgent` wrapper under `vidbyte/agents/` that internally composes a normal `BaseAgent`.
- Add prompt assets for the continual trace agent under `vidbyte/prompts/prompts/continual_trace/`.
- Add prebuilt continual trace schemas under `vidbyte/trace/prebuilt/`, importable as `from vidbyte.trace.prebuilt import ActionTrace`.
- Let custom schemas be passed as either `TraceSchema` instances or simple `Mapping[str, str]` field-description dictionaries.
- Update the direct linear text `AgentRuntime` to run the `ContinualTraceAgent` every N main-agent iterations and once before a final `isDone` result.
- Return the trace artifact in final metadata as `metadata["trace"]`.
- Keep continual trace model-call failures fail-open: preserve the previous trace artifact and let the main agent continue.
- Add unit tests, integration tests, a verification script, README docs, and 1-2 SDK skills covering continual tracing.

### Non-Goals

- No support for MCTS or actor runtimes in v1. Agents with non-linear runtimes and continual trace enabled will fail fast.
- No support for non-default context-window algorithms in v1. Continual trace is scoped to the default direct linear text loop.
- No external tracing provider integration. Existing `tracer=` and `vidbyte.lib.tracing` remain observability-only.
- No persistence layer, database schema, remote storage, or cross-run trace memory.
- No new package dependencies.
- No separate `trace_runner` or provider configuration in v1. The continual trace agent uses the same runner object as the main agent.
- No schema-level type system beyond field names and field descriptions in v1. The trace artifact is a JSON-like dictionary keyed by schema fields.
- No automatic handoff document generation in this PR.

---

## 3. Background & Context

The SDK already has a direct text `AgentRuntime` loop in `vidbyte/agents/runtime.py`. It builds a `BaseAgentContext`, sends tool schemas to the model, executes tool calls, appends tool results to provider messages, and stops when the model calls the internal `isDone` tool. The loop already tracks iteration count, tool call contexts, provider token usage, middleware metadata, and final result metadata.

The SDK also already has an observability tracing layer under `vidbyte.lib.tracing` and provider adapters under `vidbyte.providers.tracing`. That system is not the same thing as user-visible continual tracing. To avoid naming collision, this feature will use `trace=` and `vidbyte.trace`, while preserving `tracer=` for external observability spans.

Prompt assets are stored under `vidbyte/prompts/prompts/`, registered by enum values in `vidbyte/lib/enums/prompts.py`, and loaded by `Prompts().get(Prompt.X)`. New prompt assets should use a JSON descriptor plus Markdown prompt body.

Shared SDK dataclasses live under `vidbyte/lib/dataclasses/`, public feature packages re-export stable contracts, and top-level root imports are exposed from `vidbyte/__init__.py`. New code must preserve Context Protocol Header conventions and the design-doc skill's code style constraints for one-line signatures and immediate function comments.

Current checkout note: the local `main` worktree is dirty with many generated `__pycache__` modifications and is behind `origin/main` by seven commits. Phase 3 branch setup will be blocked until main can be cleaned or a fresh worktree can be created from updated main.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.__init__` accepts `trace: TraceOption | None = None`.
2. `BaseAgent.fork()` preserves the parent trace option unless explicitly overridden.
3. `BaseAgent.card().metadata` includes no trace artifact by default; trace artifacts are run results, not static agent card fields.
4. `TraceOption.continual(schema, every_n_iterations=5, max_trace_iterations=3)` returns a validated continual trace option.
5. `TraceOption.continual(...)` accepts either a `TraceSchema` or a `Mapping[str, str]`.
6. `TraceOption.continual(...)` rejects empty schemas.
7. `TraceOption.continual(...)` rejects non-positive `every_n_iterations`.
8. `TraceOption.continual(...)` rejects `max_trace_iterations` outside `1..3`.
9. `TraceSchema` stores a name, description, and ordered field descriptions.
10. `TraceSchema.initial_artifact()` returns a dictionary containing every schema field with `None` values.
11. `vidbyte.trace.prebuilt.ActionTrace` provides a prebuilt schema with at least `goal`, `actions_taken`, and `mistakes`.
12. `vidbyte.trace.prebuilt.DebugTrace` provides a prebuilt schema focused on mistakes, blockers, decisions, and open questions.
13. `ContinualTraceAgent` lives in `vidbyte/agents/continual_trace.py`.
14. `ContinualTraceAgent` is a thin wrapper over `BaseAgent`, not a new runtime.
15. `ContinualTraceAgent` loads its system prompt through `Prompts().get(Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT)`.
16. `ContinualTraceAgent` uses an `UpdateTraceTool` to accept updated trace dictionaries through normal tool calls.
17. `UpdateTraceTool` accepts one required `trace` object argument.
18. `UpdateTraceTool` filters unknown keys from model-provided trace updates.
19. `UpdateTraceTool` preserves previous values for schema fields omitted from an update.
20. `UpdateTraceTool` stores the latest accepted trace artifact for the wrapper to read.
21. `ContinualTraceAgent.update(...)` receives the main context window string, the schema, the trace artifact so far, and optional runtime facts.
22. `ContinualTraceAgent.update(...)` runs its internal agent for `max_trace_iterations` iterations.
23. If the trace agent calls `updateTrace`, the returned trace artifact becomes the main run's current trace.
24. If the trace agent does not call `updateTrace`, the prior trace artifact is preserved.
25. If the trace agent raises or returns invalid tool arguments, the prior trace artifact is preserved and trace metadata records a recoverable error.
26. `AgentRuntime` receives the trace option from `BaseAgent._runtime()`.
27. `AgentRuntime._arun_once()` creates a per-run trace controller when continual trace is enabled.
28. The trace controller updates after every `every_n_iterations` completed main-agent iterations.
29. The trace controller also updates once before returning a final `isDone` result, even if the run completed before the first interval.
30. Final `AgentResult.metadata` includes `"trace": <dict>` whenever continual trace is enabled.
31. Final `AgentResult.metadata` includes `"trace_metadata"` with update count, error count, mode, and schema name whenever continual trace is enabled.
32. `BaseAgent.generate_reply()` copies runtime trace metadata into `AgentMessage.metadata` through the existing result metadata merge.
33. Non-linear runtimes with continual trace enabled raise `ConfigurationError` at `BaseAgent` construction time.
34. Non-default context-window algorithms with continual trace enabled raise `ConfigurationError` at `BaseAgent` construction time.
35. Non-text direct modality runs do not invoke continual tracing in v1.
36. Prompt catalog tests include the new continual trace prompt enum and direct import.
37. New skills document how to use continual tracing and how to modify its implementation safely.

### Non-Functional Requirements

- Backward compatible: agents without `trace=` behave exactly as they do today.
- Fail-open: continual trace failures must never abort the main agent run in v1.
- Bounded cost: trace updates only occur at configured intervals plus one final update, with a maximum of three trace-agent iterations per update.
- No new third-party dependencies.
- Trace artifacts should be JSON-like dictionaries that remain serializable by callers.
- Continual trace helper calls must not recursively enable tracing on the internal `ContinualTraceAgent`.
- The implementation must follow repository Context Protocol Header style and the design-doc skill's one-line function signature/comment requirement.

---

## 5. High-Level Design

The public API adds one constructor option:

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.prebuilt import ActionTrace

agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    runner=runner,
    trace=TraceOption.continual(ActionTrace, every_n_iterations=5, max_trace_iterations=3),
)
reply = await agent.arun("Fix the failing tests")
trace_artifact = reply.metadata["trace"]
```

The main agent remains a normal `BaseAgent`. `TraceOption.continual(...)` is only configuration. When the direct runtime starts, it creates a small trace controller with an initial artifact derived from the schema. At configured intervals, the controller creates a `ContinualTraceAgent` using the same runner object and asks it to update the artifact.

The `ContinualTraceAgent` is just a wrapper around `BaseAgent`. It has one model-visible tool: `updateTrace`. Its prompt receives the rendered main context window, the schema field descriptions, and the current trace artifact. The model can either call `updateTrace` with a complete or partial artifact or do nothing. The tool validates and stores the latest artifact, and the wrapper returns it to the main runtime.

```text
User Agent(trace=TraceOption.continual(...))
  -> BaseAgent.generate_reply()
  -> AgentRuntime._arun_once()
     -> main model/tool iteration 1
     -> main model/tool iteration N
     -> ContinualTraceAgent.update(...)
        -> BaseAgent(name="continual-trace-agent", tools=[UpdateTraceTool])
        -> updateTrace({"trace": {...}})
     -> main loop continues
     -> isDone final result
     -> final ContinualTraceAgent.update(...)
     -> AgentMessage.metadata["trace"]
```

The design intentionally uses the existing tool-calling loop rather than custom JSON parsing as the primary update mechanism. This matches the user's desired mental model and keeps the trace agent reusable as a regular SDK agent.

---

## 6. Detailed Design

### 6.1 Trace Dataclasses

**File(s):** `vidbyte/lib/dataclasses/trace.py`
**Type:** New file

#### What it does

Defines the shared in-memory contracts for trace configuration and schemas.

#### Interface / API

```python
class TraceMode(str, Enum):
    CONTINUAL = "continual"

@dataclass(frozen=True, slots=True)
class TraceSchema:
    name: str
    fields: Mapping[str, str]
    description: str = ""

@dataclass(frozen=True, slots=True)
class TraceOption:
    mode: TraceMode
    schema: TraceSchema
    every_n_iterations: int = 5
    max_trace_iterations: int = 3

    @classmethod
    def continual(cls, schema: TraceSchema | Mapping[str, str], *, every_n_iterations: int = 5, max_trace_iterations: int = 3) -> "TraceOption": ...
```

#### Logic / Algorithm

1. `TraceSchema.__post_init__` validates non-empty name and at least one non-empty field.
2. `TraceSchema.coerce(raw)` returns `raw` when it is already a `TraceSchema`; otherwise it builds a custom schema from a mapping.
3. `TraceSchema.initial_artifact()` returns `{field_name: None for field_name in fields}`.
4. `TraceOption.continual(...)` coerces the schema and validates interval and max iteration values.
5. `TraceOption.enabled` returns `True` for continual mode.

#### Edge Cases & Error Handling

- Empty schema mapping raises `ValueError`.
- Empty field names or descriptions raise `ValueError`.
- `every_n_iterations <= 0` raises `ValueError`.
- `max_trace_iterations` outside `1..3` raises `ValueError`.

---

### 6.2 Public Trace Package

**File(s):** `vidbyte/trace/__init__.py`, `vidbyte/trace/options.py`
**Type:** New file

#### What it does

Provides the public import namespace for continual trace configuration.

#### Interface / API

```python
from vidbyte.trace import TraceOption, TraceSchema
from vidbyte import TraceOption
```

#### Logic / Algorithm

1. `vidbyte.trace.options` re-exports `TraceMode`, `TraceOption`, and `TraceSchema` from `vidbyte.lib.dataclasses.trace`.
2. `vidbyte.trace.__init__` exports those contracts and leaves prebuilt schemas in `vidbyte.trace.prebuilt`.
3. `vidbyte.__init__` imports and root-exports `TraceOption` and `TraceSchema`.

#### Edge Cases & Error Handling

- N/A - import surface only.

---

### 6.3 Prebuilt Trace Schemas

**File(s):** `vidbyte/trace/prebuilt/__init__.py`, `vidbyte/trace/prebuilt/action.py`, `vidbyte/trace/prebuilt/debug.py`
**Type:** New file

#### What it does

Defines SDK-provided schemas that can be passed directly into `TraceOption.continual(...)`.

#### Interface / API

```python
from vidbyte.trace.prebuilt import ActionTrace, DebugTrace

ActionTrace = TraceSchema(...)
DebugTrace = TraceSchema(...)
```

#### Logic / Algorithm

1. `ActionTrace` includes `goal`, `actions_taken`, `mistakes`, and `current_status`.
2. `DebugTrace` includes `goal`, `decisions`, `mistakes`, `blockers`, and `open_questions`.
3. `__init__.py` exports both prebuilt schemas.

#### Edge Cases & Error Handling

- Prebuilt schemas are constructed at import time; invalid definitions raise immediately in tests.

---

### 6.4 Continual Trace Prompt Asset

**File(s):** `vidbyte/prompts/prompts/continual_trace/continual_trace.json`, `vidbyte/prompts/prompts/continual_trace/system_prompt.md`, `vidbyte/lib/enums/prompts.py`
**Type:** New file, Modified

#### What it does

Adds the system prompt used by `ContinualTraceAgent`.

#### Interface / API

```python
Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT = "continual_trace.system_prompt"
Prompts().get(Prompt.CONTINUAL_TRACE_SYSTEM_PROMPT)
```

#### Logic / Algorithm

1. Add a prompt enum member.
2. Add a JSON descriptor with key `continual_trace` and prompt `system_prompt`.
3. Add a Markdown prompt instructing the trace agent to inspect the main context window, compare it with the schema and trace so far, call `updateTrace` when useful, and stop with `isDone`.
4. Existing dynamic prompt exports make `continual_trace_system_prompt` importable from `vidbyte.prompts`.

#### Edge Cases & Error Handling

- Prompt catalog validation fails if the enum and JSON descriptor fall out of sync.
- Tests must verify direct import and `Prompts().get(...)` work.

---

### 6.5 UpdateTraceTool

**File(s):** `vidbyte/trace/tools.py`
**Type:** New file

#### What it does

Defines the tool used by `ContinualTraceAgent` to accept trace updates.

#### Interface / API

```python
class UpdateTraceTool(BaseTool):
    def __init__(self, schema: TraceSchema, initial_trace: Mapping[str, Any] | None = None) -> None: ...
    def spec(self) -> ToolSpec: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
    def current_trace(self) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Store the schema and initialize `_trace` from `schema.initial_artifact()` merged with any supplied previous trace.
2. `spec()` returns an `updateTrace` safe tool with required object parameter `trace`.
3. `execute()` reads `call.arguments["trace"]`.
4. If `trace` is not a mapping, return `ToolResult.error(...)` and keep prior state.
5. Filter the update to known schema fields.
6. Merge filtered values over the previous trace, preserving omitted schema fields.
7. Store the merged trace and return `ToolResult.success(...)`.
8. `current_trace()` returns a plain copy of the stored artifact.

#### Edge Cases & Error Handling

- Non-object trace argument returns an error without changing state.
- Unknown keys are ignored.
- Missing fields preserve prior values.
- Empty object update keeps prior values.

---

### 6.6 ContinualTraceAgent

**File(s):** `vidbyte/agents/continual_trace.py`, `vidbyte/agents/__init__.py`, `vidbyte/agents/client.py`
**Type:** New file, Modified

#### What it does

Adds a built-in thin wrapper class that composes `BaseAgent` to update trace artifacts.

#### Interface / API

```python
class ContinualTraceAgent:
    def __init__(self, *, runner: object, schema: TraceSchema, max_iterations: int = 3, provider: str | None = None) -> None: ...
    async def update(self, *, context_window: str, trace_so_far: Mapping[str, Any], runtime_metadata: Mapping[str, Any] | None = None) -> dict[str, Any]: ...
```

`AgentClient` may expose:

```python
sdk.agents.continual_trace(runner=runner, schema=ActionTrace)
```

#### Logic / Algorithm

1. Construct an `UpdateTraceTool` with the schema and trace artifact so far for each update call.
2. Construct an internal `BaseAgent` named `continual-trace-agent` with the prompt asset, the same runner object, the update tool, and `max_iterations`.
3. Do not pass any `trace` option to the internal agent, preventing recursive tracing.
4. Render a user prompt containing:
   - main context window,
   - schema field descriptions,
   - current trace artifact,
   - runtime metadata such as iteration count, tool call count, and stop reason when available.
5. Run the internal agent with `await agent.arun(prompt)`.
6. Return the tool's stored trace artifact after the run.
7. If the internal agent fails, return the prior trace artifact and let the runtime record an error.

#### Edge Cases & Error Handling

- If the model never calls `updateTrace`, the artifact remains unchanged.
- If the model calls `updateTrace` with partial values, omitted fields preserve prior values.
- If the internal agent hits `max_iterations`, the latest accepted trace is still returned.

---

### 6.7 BaseAgent Integration

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Adds the public `trace` option and passes it into runtimes.

#### Interface / API

```python
class BaseAgent:
    def __init__(..., trace: TraceOption | None = None, tracer: type[TracerBase] | TracerBase | None = None) -> None: ...
    def fork(..., trace: TraceOption | None = None, include_history: bool = False) -> BaseAgent: ...
```

#### Logic / Algorithm

1. Add `trace` to the constructor near runtime policy options.
2. Store `self.trace = trace`.
3. Reject continual trace for non-linear runtimes.
4. Reject continual trace for non-default context-window algorithms in v1.
5. `fork()` preserves `self.trace` unless a replacement is provided.
6. `_runtime()` passes `trace=self.trace` into the resolved runtime class.

#### Edge Cases & Error Handling

- `trace=None` preserves all existing behavior.
- Invalid trace option objects naturally fail type or attribute checks in tests.
- Non-linear runtime plus continual trace raises `ConfigurationError` synchronously.

---

### 6.8 AgentRuntime Integration

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Runs continual trace updates during the direct linear text loop and attaches final trace metadata.

#### Interface / API

```python
class AgentRuntime:
    def __init__(..., trace: TraceOption | None = None, recorder: RecorderBase | None = None) -> None: ...
```

Internal helper:

```python
class ContinualTraceController:
    def __init__(self, *, option: TraceOption | None, runner: object, provider: str) -> None: ...
    async def update_if_due(self, *, force: bool, iteration_count: int, context: BaseAgentContext, messages: Sequence[Mapping[str, Any]], tool_calls: Sequence[ToolCallContext], runtime_metadata: Mapping[str, Any]) -> None: ...
    def metadata(self) -> dict[str, Any]: ...
```

#### Logic / Algorithm

1. Store `self.trace` in `AgentRuntime.__init__`.
2. In `_arun_once`, create a `ContinualTraceController` when `self.trace` is enabled.
3. After each completed main-agent iteration, call `update_if_due(force=False, ...)`.
4. Before returning a final `isDone` result, call `update_if_due(force=True, ...)`.
5. For budget and middleware stops, attach the current trace artifact and metadata even if no final update can be run.
6. The controller renders `context.build_context()` plus provider messages and compact tool-call summaries for the trace agent.
7. The controller catches all exceptions from `ContinualTraceAgent.update(...)`, increments `error_count`, stores the last error type in metadata, and preserves the prior artifact.
8. Final `AgentResult.metadata` includes `"trace"` and `"trace_metadata"` through the existing final result metadata path.

#### Edge Cases & Error Handling

- Empty trace option means no controller is created.
- First-iteration final result still gets a forced trace update.
- Trace update failures do not modify main loop messages or stop the main run.
- Trace agent tool calls are not appended to the main agent's `tool_calls` metadata.

---

### 6.9 Public Root Exports

**File(s):** `vidbyte/__init__.py`, `vidbyte/lib/dataclasses/__init__.py`
**Type:** Modified

#### What it does

Makes continual trace contracts discoverable from stable SDK namespaces.

#### Interface / API

```python
from vidbyte import TraceOption, TraceSchema
from vidbyte.trace import TraceOption, TraceSchema
from vidbyte.trace.prebuilt import ActionTrace
```

#### Logic / Algorithm

1. Export `TraceMode`, `TraceOption`, and `TraceSchema` from `vidbyte.lib.dataclasses`.
2. Root-export `TraceOption` and `TraceSchema` from `vidbyte`.
3. Do not root-export prebuilt schemas; users import them from `vidbyte.trace.prebuilt`.

#### Edge Cases & Error Handling

- Import smoke tests verify all public paths.

---

### 6.10 Documentation and Skills

**File(s):** `README.md`, `skills/vidbyte-sdk/SKILL.md`, `skills/vidbyte-sdk/continual-tracing.md`, `skills/usage/create_agent.md`, `skills/usage/use_continual_trace.md`
**Type:** New file, Modified

#### What it does

Documents how to use and modify continual tracing.

#### Interface / API

N/A - documentation only.

#### Logic / Algorithm

1. Add README usage showing `trace=TraceOption.continual(ActionTrace, ...)`.
2. Add SDK structure rules for `vidbyte/trace/` and `vidbyte/agents/continual_trace.py`.
3. Add `skills/vidbyte-sdk/continual-tracing.md` as the implementation/maintenance guide.
4. Add `skills/usage/use_continual_trace.md` as a user-facing recipe.
5. Update `skills/usage/create_agent.md` constructor docs with the `trace` option.

#### Edge Cases & Error Handling

- Documentation must distinguish `trace=` from existing observability `tracer=`.

---

## 7. Data Model Changes

### 7.1 TraceMode

**Change type:** New

```python
class TraceMode(str, Enum):
    CONTINUAL = "continual"
```

**Migration strategy:** N/A - in-memory SDK enum only.

- Forward migration: add enum and exports.
- Rollback plan: remove enum and callers.

### 7.2 TraceSchema

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class TraceSchema:
    name: str
    fields: Mapping[str, str]
    description: str = ""
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: add dataclass and prebuilt schema constants.
- Rollback plan: remove dataclass, prebuilt schemas, and trace option support.

### 7.3 TraceOption

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class TraceOption:
    mode: TraceMode
    schema: TraceSchema
    every_n_iterations: int = 5
    max_trace_iterations: int = 3
```

**Migration strategy:** N/A - in-memory SDK dataclass only.

- Forward migration: add dataclass and constructor wiring.
- Rollback plan: remove `trace` from `BaseAgent` and runtime.

### 7.4 AgentMessage.metadata

**Change type:** Modified

```python
reply.metadata["trace"] = dict[str, Any]
reply.metadata["trace_metadata"] = {
    "mode": "continual",
    "schema": "action_trace",
    "update_count": int,
    "error_count": int,
}
```

**Migration strategy:** Backward-compatible additive metadata.

- Forward migration: metadata appears only when `trace=` is configured.
- Rollback plan: remove the metadata keys and trace runtime wiring.

---

## 8. API Changes

N/A - this SDK change does not add HTTP endpoints.

### 8.1 Python SDK: Agent continual trace option

**Change type:** New

**Request:**

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.prebuilt import ActionTrace

agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    runner=runner,
    trace=TraceOption.continual(ActionTrace, every_n_iterations=5, max_trace_iterations=3),
)
reply = await agent.arun("Complete the task.")
```

**Response:**

```python
reply.metadata["trace"]
reply.metadata["trace_metadata"]
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Empty trace schema raises `ValueError` during `TraceOption.continual(...)`. |
| N/A | Non-positive interval raises `ValueError` during `TraceOption.continual(...)`. |
| N/A | `max_trace_iterations` outside `1..3` raises `ValueError`. |
| N/A | Continual trace on non-linear runtime raises `ConfigurationError`. |
| N/A | Continual trace update failures are recorded in metadata and do not abort the main run. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/continual-trace-agent.md` | Design doc for this feature |
| CREATE | `vidbyte/lib/dataclasses/trace.py` | TraceMode, TraceSchema, TraceOption contracts |
| CREATE | `vidbyte/trace/__init__.py` | Public trace package exports |
| CREATE | `vidbyte/trace/options.py` | Public option/type compatibility module |
| CREATE | `vidbyte/trace/tools.py` | UpdateTraceTool for trace-agent tool calls |
| CREATE | `vidbyte/trace/prebuilt/__init__.py` | Public prebuilt schema exports |
| CREATE | `vidbyte/trace/prebuilt/action.py` | ActionTrace schema |
| CREATE | `vidbyte/trace/prebuilt/debug.py` | DebugTrace schema |
| CREATE | `vidbyte/agents/continual_trace.py` | Thin ContinualTraceAgent wrapper over BaseAgent |
| CREATE | `vidbyte/prompts/prompts/continual_trace/continual_trace.json` | Prompt family descriptor |
| CREATE | `vidbyte/prompts/prompts/continual_trace/system_prompt.md` | Continual trace system prompt |
| CREATE | `tests/test_continual_trace.py` | Unit and integration tests |
| CREATE | `scripts/test-continual-trace.py` | Full verification script |
| CREATE | `skills/vidbyte-sdk/continual-tracing.md` | Implementation/maintenance skill |
| CREATE | `skills/usage/use_continual_trace.md` | User-facing usage skill |
| MODIFY | `vidbyte/agents/base.py` | Add trace option, validation, fork propagation, runtime wiring |
| MODIFY | `vidbyte/agents/runtime.py` | Add continual trace controller and metadata attachment |
| MODIFY | `vidbyte/agents/__init__.py` | Export ContinualTraceAgent |
| MODIFY | `vidbyte/agents/client.py` | Add optional namespace constructor for continual trace agent |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export trace dataclasses |
| MODIFY | `vidbyte/lib/enums/prompts.py` | Add continual trace prompt enum |
| MODIFY | `vidbyte/__init__.py` | Root-export TraceOption and TraceSchema |
| MODIFY | `README.md` | Document continual trace usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add trace package rules |
| MODIFY | `skills/usage/create_agent.md` | Add trace constructor parameter and usage pointer |

Summary: 15 files created, 10 files modified, 0 files deleted.

---

## 10. Testing Plan

### Unit Tests

- `TraceSchemaTests.test_rejects_empty_fields` - [Edge Case] Empty schema mapping raises `ValueError`.
- `TraceSchemaTests.test_rejects_blank_field_name` - [Hidden Assumption] Field names are not always valid strings.
- `TraceSchemaTests.test_initial_artifact_contains_all_fields` - [Silent Failure] Initial artifact must not omit any schema field.
- `TraceSchemaTests.test_coerce_mapping_preserves_insertion_order` - [Silent Failure] Field order should match developer-provided order.
- `TraceOptionTests.test_continual_accepts_prebuilt_schema` - [Edge Case] Prebuilt `ActionTrace` works without wrapping.
- `TraceOptionTests.test_continual_accepts_mapping_schema` - [Edge Case] A one-field custom mapping schema works.
- `TraceOptionTests.test_rejects_zero_interval` - [Edge Case] `every_n_iterations=0` raises.
- `TraceOptionTests.test_rejects_negative_interval` - [Edge Case] Negative interval raises.
- `TraceOptionTests.test_rejects_zero_trace_iterations` - [Edge Case] `max_trace_iterations=0` raises.
- `TraceOptionTests.test_rejects_trace_iterations_above_three` - [Hidden Assumption] Trace agent should stay within the requested 1-3 iteration budget.
- `PrebuiltTraceTests.test_action_trace_has_required_fields` - [Hidden Failure] Prebuilt schema accidentally drops `goal`, `actions_taken`, or `mistakes`.
- `PrebuiltTraceTests.test_debug_trace_constructs` - [Hidden Failure] Import-time schema validation catches broken prebuilt fields.
- `UpdateTraceToolTests.test_accepts_complete_trace_object` - [Edge Case] Complete update replaces all schema fields.
- `UpdateTraceToolTests.test_partial_update_preserves_existing_values` - [Silent Failure] Missing fields should not silently reset previous values.
- `UpdateTraceToolTests.test_unknown_keys_are_filtered` - [Silent Failure] Unknown model-produced keys should not leak into the artifact.
- `UpdateTraceToolTests.test_non_object_trace_returns_error_without_mutation` - [Hidden Failure] Bad tool arguments should not corrupt trace state.
- `UpdateTraceToolTests.test_empty_update_keeps_initial_artifact` - [Edge Case] Empty trace object keeps all schema fields present.
- `ContinualTraceAgentTests.test_wrapper_uses_prompt_catalog` - [Hidden Assumption] Prompt enum and catalog are correctly wired.
- `ContinualTraceAgentTests.test_update_returns_tool_recorded_trace` - [Edge Case] Trace agent returns updated artifact when `updateTrace` is called.
- `ContinualTraceAgentTests.test_no_update_tool_call_preserves_previous_trace` - [Silent Failure] Ordinary text response should not be mistaken for a trace update.
- `ContinualTraceAgentTests.test_trace_agent_failure_preserves_previous_trace` - [Hidden Failure] Trace-agent runner exception is fail-open.
- `BaseAgentTraceTests.test_agent_stores_trace_option` - [Edge Case] `BaseAgent(trace=...)` stores the option.
- `BaseAgentTraceTests.test_fork_preserves_trace_option` - [Silent Failure] Forked agents must not silently lose trace config.
- `BaseAgentTraceTests.test_fork_can_replace_trace_option` - [Edge Case] Explicit fork override works.
- `BaseAgentTraceTests.test_non_linear_runtime_with_trace_raises` - [Hidden Assumption] Continual tracing is linear-runtime-only in v1.
- `BaseAgentTraceTests.test_non_default_algorithm_with_trace_raises` - [Hidden Assumption] Continual tracing is default-loop-only in v1.
- `PromptCatalogTests.test_continual_trace_prompt_available` - [Hidden Failure] Prompt enum, JSON descriptor, and Markdown asset stay synchronized.
- `PublicImportTests.test_trace_public_imports` - [Hidden Failure] `from vidbyte import TraceOption` and `from vidbyte.trace.prebuilt import ActionTrace` work.

### Integration Tests

- `AgentRuntimeContinualTraceTests.test_final_response_contains_trace_metadata` - [Edge Case] A one-iteration main run still gets a forced final trace update.
- `AgentRuntimeContinualTraceTests.test_updates_every_n_iterations` - [Silent Failure] Off-by-one interval bugs are caught by asserting exact trace update count.
- `AgentRuntimeContinualTraceTests.test_trace_update_failure_does_not_abort_main_agent` - [Hidden Failure] Trace-agent exception preserves main result and increments error metadata.
- `AgentRuntimeContinualTraceTests.test_trace_agent_tool_calls_do_not_pollute_main_tool_calls` - [Silent Failure] Main `tool_call_count` should not include trace-agent internal tools.
- `AgentRuntimeContinualTraceTests.test_trace_artifact_accumulates_across_updates` - [Silent Failure] Later updates merge over prior trace rather than resetting it.
- `AgentRuntimeContinualTraceTests.test_disabled_trace_preserves_existing_runtime_metadata_shape` - [Hidden Assumption] Existing agents without trace remain behaviorally unchanged.

All integration tests use fake runners and fake responses. No live provider, network, MCP server, or external service is required.

### Manual / QA Test Cases

1. Given an agent configured with `trace=TraceOption.continual(ActionTrace, every_n_iterations=2)`, when it runs for four iterations and finishes, then `reply.metadata["trace"]` contains ActionTrace fields and `trace_metadata.update_count >= 2`.
2. Given a custom schema mapping with a single field, when the trace agent updates that field, then the final trace contains exactly that schema field.
3. Given the trace agent emits invalid `updateTrace` arguments, when the main run completes, then the main answer still returns and `trace_metadata.error_count` is greater than zero.
4. Given no `trace` option, when existing unit tests run, then no `trace` or `trace_metadata` key appears in metadata.

### Verification Script

Create `scripts/test-continual-trace.py` to run every Section 10 unit, integration, edge, hidden failure, silent failure, and hidden assumption test. The script must print `PASS` or `FAIL` for each case, print `X/Y tests passed`, and exit non-zero on failure.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib | Python >=3.11 | dataclasses, enum, json, unittest | Existing runtime only |
| pydantic | Existing `>=2,<3` | N/A for v1 implementation | No direct new usage |
| httpx | Existing `>=0.27` | N/A for v1 implementation | No direct new usage |

No new external services or package dependencies are introduced.

---

## 12. Rollout & Deployment

- This is a package-only SDK change.
- No feature flag is needed.
- The change is additive and backward-compatible for users who do not pass `trace=`.
- Rollout sequence after approval:
  1. Resolve dirty-main blocker or create a clean worktree from updated main.
  2. Create `feat/continual-trace-agent` worktree.
  3. Commit this design doc first.
  4. Add trace dataclasses and public package.
  5. Add prebuilt schemas and prompt assets.
  6. Add `UpdateTraceTool` and `ContinualTraceAgent`.
  7. Wire `BaseAgent` and `AgentRuntime`.
  8. Add tests and verification script.
  9. Update README and skills.
  10. Run `python -m compileall vidbyte`, `python -m unittest discover -s tests`, and `python scripts/test-continual-trace.py`.
  11. Push branch and open a draft PR.
- Rollback procedure:
  1. Revert the feature branch merge commit.
  2. Remove `vidbyte/trace/`, `vidbyte/agents/continual_trace.py`, prompt assets, tests, script, and skills.
  3. Remove `trace` from `BaseAgent` and `AgentRuntime`.
  4. Remove prompt enum and root exports.

---

## 13. Open Questions

- [ ] Confirm the public package should be `vidbyte.trace.prebuilt` rather than `vidbyte.tracing.prebuilt`. Recommendation: use `vidbyte.trace.prebuilt` to match the requested import shape and avoid conflict with existing observability tracing.
- [ ] Should `trace_metadata` expose the rendered trace prompt for debugging? Recommendation: no in v1, to avoid large metadata and sensitive context leakage.
- [ ] Should the final forced trace update run on max-iteration/max-token stops? Recommendation: attach the current trace artifact in v1 and only force-update on normal `isDone` final response to keep stop paths simple.

---

## 14. Alternatives Considered

### Alternative 1: Middleware-only continual trace

- What: Implement trace updates as an `AgentMiddleware` built-in.
- Why rejected: The user explicitly wants a `TraceOption.continual(...)` agent parameter and a `ContinualTraceAgent`. Middleware would also make the trace feature look like policy code rather than a first-class agent capability.

### Alternative 2: Custom JSON parser without tool calls

- What: Ask the trace model for raw JSON and parse it directly.
- Why rejected: The user explicitly wants the trace agent to update through tool calls, and the SDK already has a strong tool-calling loop. A tool also gives a clean validation point for schema keys.

### Alternative 3: New runtime type

- What: Add a special trace-aware runtime.
- Why rejected: Continual tracing is an optional feature of the existing direct loop, not a replacement loop paradigm. A new runtime would duplicate the normal linear runtime and make adoption harder.

### Alternative 4: Support non-linear runtimes in v1

- What: Add trace updates to MCTS and actor runtimes.
- Why rejected: The repo already treats non-linear runtimes as incompatible with standard sequential middleware and context algorithms. Extending continual trace there would require a separate design for non-linear event snapshots.

### Alternative 5: Store prebuilt schemas under `vidbyte.tracing.prebuilt`

- What: Use a `vidbyte/tracing/` package.
- Why rejected: The repo already has `vidbyte.lib.tracing` and `vidbyte.providers.tracing` for external observability. `vidbyte.trace` is shorter, matches the user's import example, and keeps user-visible trace artifacts separate from observability tracers.
