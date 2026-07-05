# Design Doc: Trace Component Expansion

**Status:** Draft
**Author:** Codex
**Created:** 2026-07-04
**Last Updated:** 2026-07-04
**Base Branch:** `feat/semantic-trace-profiles` (PR #198)

---

## 1. Overview

This feature expands the semantic trace component layer from a coarse structural map (one span per component phase) into a detailed semantic event catalog (one span per meaningful state transition inside each abstraction). It adds 6 new component factory files for SDK abstractions that currently have no trace coverage, and deepens the 6 existing component factories with per-hook, per-action, and per-lifecycle spans that surface the extensive configuration surface of each abstraction.

---

## 2. Goals & Non-Goals

### Goals

- Add new component factory files for: pipelines, handoff, sources, sessions, evals, and MCP.
- Expand `AgentTrace` with enforcement spans: loop_settings, output_contract, handoff, modality, aggregate plan, algorithm, MCP attach, runner creation.
- Expand `MiddlewareTrace` with per-hook ran spans, per-action spans (sleep, abort, deny_tool, retry), exception spans, transform spans, and builtin-specific spans.
- Expand `ToolTrace` with resolve, validate, deny, error, compact, parallel_batch, and MCP tool spans.
- Expand `ContextTrace` with manager upsert/extend, primitive add/remove, compaction trigger/strategy, template record, and handoff sync spans.
- Expand `LinearRuntimeTrace` with model_call, tool_batch, and stop_condition spans. Expand `ActorRuntimeTrace` with quiescence and compile_prompt. Expand `SearchRuntimeTrace` with expand, evaluate, and select.
- Expand `ParserTrace` with is_done and response_format_built spans.
- Add new component names to `_COMPONENTS` in `profiles.py`.
- Export all new factories from `vidbyte/trace/components/__init__.py`.
- Preserve all existing span specs, profile behavior, and public APIs.

### Non-Goals

- Do not modify the `SpanSpec` dataclass shape or add new `SpanKind` values.
- Do not modify `TraceProfile.allows()` filtering logic.
- Do not modify `TraceController` or provider translators.
- Do not modify agent runtime, middleware pipeline, or tool executor implementation code.
- Do not add new `TraceDetail` levels.
- Do not change the existing `minimal()`, `default()`, `verbose()`, or `diagnostic()` presets.
- Do not add tests or verification scripts (design-doc-no-tests workflow).

---

## 3. Background & Context

PR #198 (`feat/semantic-trace-profiles`) introduced the semantic trace layer with 8 component factory files and ~25 total span specs. The SDK has far more configurable surface area than what is currently traced:

- **Middleware**: 9 hooks x 5 actions x 16 builtins, but only `middleware.decision` and `middleware.hook` spans exist.
- **Agent**: `AgentLoopSettings` (10 fields), `output_schema` enforcement, handoff lifecycle, modality routing, aggregate plan resolution, MCP attach, algorithm resolution — none traced.
- **Tools**: Full execution lifecycle (resolve, validate, deny, error, compact, parallel, MCP) — only `call` and `permission` traced.
- **Context**: `ContextManager` upsert/extend, primitive lifecycle, compaction trigger/strategy, template recording — only `window_build`, `primitive_render`, `compaction`, `update` traced.
- **Runtimes**: Inner-loop model calls, tool batches, specific `AgentStopReason` values, actor quiescence/prompt compilation, search expand/evaluate/select — only coarse iteration/stop/spawn/message spans exist.
- **Parsers**: `is_done` tool parsing, response format construction — only `tool_calls` and `structured_output` traced.
- **Pipelines**: First-class orchestration primitive with no trace coverage at all.
- **Handoff**: Core agent lifecycle event with no trace coverage.
- **Sources**: Artifact sources, llms.txt, document loaders with no trace coverage.
- **Sessions**: `SessionTracer` exists but has no component factory.
- **Evals**: Eval harnesses and graders with no trace coverage.
- **MCP**: MCP attach/search/transport distinct from tool calls with no trace coverage.

The existing `SpanSpec` infrastructure (name, kind, component, detail, parent_policy, attributes) is sufficient to express all of these. The `ParentPolicy` enum has unused values (`AGENT`, `RUNTIME_ITERATION`, `AGGREGATE`, `SESSION`, `ROOT`) that should be leveraged for the new spans.

---

## 4. Requirements

### Functional Requirements

1. `AgentTrace` must define span specs for: `loop_settings.resolved`, `loop_settings.enforced`, `output_contract.enforced`, `output_contract.violation`, `handoff.requested`, `handoff.generated`, `handoff.failed`, `modality.resolved`, `aggregate.plan_resolved`, `algorithm.resolved`, `mcp.attached`, `runner.created`.
2. `AggregateTrace` must remain unchanged (already has run, proposer, synthesis, failure).
3. `MiddlewareTrace` must define span specs for: per-hook ran spans (`before_run.ran`, `before_iteration.ran`, `before_model_call.ran`, `after_model_response.ran`, `on_model_error.ran`, `before_tool_call.ran`, `after_tool_call.ran`, `after_iteration.ran`, `after_run.ran`), per-action spans (`action.sleep`, `action.abort_run`, `action.deny_tool`, `action.retry`), `exception`, `transform.applied`, and `builtin.<name>` (parameterized).
4. `ToolTrace` must define span specs for: `resolve`, `validate`, `deny`, `error`, `compact`, `parallel_batch`, `mcp.invoke`, `mcp.attach`.
5. `ContextTrace` must define span specs for: `manager.upsert`, `manager.extend`, `primitive.add`, `primitive.remove`, `compaction.trigger`, `compaction.strategy`, `template.record`, `handoff.sync`.
6. `LinearRuntimeTrace` must define span specs for: `model_call`, `tool_batch`, `stop_condition`.
7. `ActorRuntimeTrace` must define span specs for: `quiescence`, `compile_prompt`.
8. `SearchRuntimeTrace` must define span specs for: `expand`, `evaluate`, `select`.
9. `ParserTrace` must define span specs for: `is_done`, `response_format_built`.
10. A new `PipelineTrace` factory must define span specs for: `sequential.run`, `parallel.run`, `conditional.run`, `map_reduce.run`, `stage.invoke`.
11. A new `HandoffTrace` factory must define span specs for: `generate`, `validate`, `record`, `sync`.
12. A new `SourceTrace` factory must define span specs for: `fetch`, `load`, `cache.hit`, `cache.miss`.
13. A new `SessionTrace` factory must define span specs for: `start`, `end`, `case`.
14. A new `EvalTrace` factory must define span specs for: `run`, `grade`, `behavior`.
15. A new `McpTrace` factory must define span specs for: `attach`, `search`, `transport`.
16. `_COMPONENTS` in `profiles.py` must include the new component names: `pipelines`, `handoff`, `sources`, `evals`, `mcp`.
17. `vidbyte/trace/components/__init__.py` must export all new factory classes.
18. All new span specs must use the existing `SpanSpec` dataclass, `SpanKind` enum, `TraceDetail` enum, and `ParentPolicy` enum.
19. All new span specs must specify appropriate `detail` levels so that profile filtering works correctly.
20. All new span specs must specify appropriate `parent_policy` values, using `ParentPolicy.AGENT`, `RUNTIME_ITERATION`, `AGGREGATE`, `SESSION`, or `ROOT` where semantically appropriate instead of defaulting to `CURRENT`.
21. All new factory methods must follow the existing pattern: `@staticmethod def method_name(**attributes: Any) -> SpanSpec:`.
22. All new factory methods must include a 1-line comment describing what the span describes.
23. Each new component file must define `__all__` listing its public classes.

### Non-Functional Requirements

- Maintainability: Each new span spec must be self-documenting via its name and comment.
- Compatibility: No existing span spec names, detail levels, or component assignments may change.
- Performance: Span specs are lightweight immutable dataclasses; no runtime cost unless emitted.

---

## 5. High-Level Design

The change is purely additive within `vidbyte/trace/components/`. No existing span specs are modified. Six new files are created, six existing files are extended with new factory methods, and two infrastructure files (`__init__.py` and `profiles.py`) are updated to register and export the new factories and components.

The design follows the existing factory pattern: each component abstraction gets a class with `@staticmethod` methods returning `SpanSpec` instances. The `SpanSpec` captures the span name, kind, component, detail threshold, parent policy, and caller-supplied attributes.

The key design decision is **detail level assignment**: each new span gets a detail level that reflects its noise-to-signal ratio. Spans that capture errors or enforcement violations get `STANDARD` (visible in default profiles). Spans that capture internal lifecycle steps get `VERBOSE`. Spans that capture per-iteration diagnostics get `DIAGNOSTIC`. This ensures that the existing 4 presets (`minimal`, `default`, `verbose`, `diagnostic`) naturally filter the new spans without requiring profile logic changes.

The second key design decision is **parent policy assignment**: the existing components uniformly use `ParentPolicy.CURRENT`. The new spans use semantically appropriate policies: enforcement spans use `ParentPolicy.AGENT`, runtime inner-loop spans use `ParentPolicy.RUNTIME_ITERATION`, aggregate-related spans use `ParentPolicy.AGGREGATE`, session spans use `ParentPolicy.SESSION`, and pipeline/source/eval spans use `ParentPolicy.ROOT` when they represent top-level orchestration.

---

## 6. Detailed Design

### 6.1 AgentTrace Expansion

**File(s):** `vidbyte/trace/components/agents.py`
**Type:** Modified

#### What it does

Adds 12 new span specs covering agent-level enforcement, lifecycle, and configuration resolution events.

#### Interface / API

```python
class AgentTrace:
    @staticmethod
    def run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def stop(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def loop_settings_resolved(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def loop_settings_enforced(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def output_contract_enforced(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def output_contract_violation(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def handoff_requested(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def handoff_generated(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def handoff_failed(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def modality_resolved(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def aggregate_plan_resolved(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def algorithm_resolved(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def mcp_attached(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def runner_created(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `loop_settings_resolved` | `agent.loop_settings.resolved` | CHAIN | STANDARD | AGENT |
| `loop_settings_enforced` | `agent.loop_settings.enforced` | CHAIN | STANDARD | AGENT |
| `output_contract_enforced` | `agent.output_contract.enforced` | CHAIN | VERBOSE | AGENT |
| `output_contract_violation` | `agent.output_contract.violation` | CHAIN | STANDARD | AGENT |
| `handoff_requested` | `agent.handoff.requested` | CHAIN | VERBOSE | AGENT |
| `handoff_generated` | `agent.handoff.generated` | CHAIN | VERBOSE | AGENT |
| `handoff_failed` | `agent.handoff.failed` | CHAIN | STANDARD | AGENT |
| `modality_resolved` | `agent.modality.resolved` | CHAIN | VERBOSE | AGENT |
| `aggregate_plan_resolved` | `agent.aggregate.plan_resolved` | CHAIN | VERBOSE | AGENT |
| `algorithm_resolved` | `agent.algorithm.resolved` | CHAIN | VERBOSE | AGENT |
| `mcp_attached` | `agent.mcp.attached` | CHAIN | VERBOSE | AGENT |
| `runner_created` | `agent.runner.created` | CHAIN | DIAGNOSTIC | AGENT |

#### Edge Cases & Error Handling

- All methods accept arbitrary attributes and pass them through to `SpanSpec`.
- Missing attribute values are the caller's responsibility; factory methods do not validate.

### 6.2 MiddlewareTrace Expansion

**File(s):** `vidbyte/trace/components/middleware.py`
**Type:** Modified

#### What it does

Adds per-hook ran spans for all 9 middleware hooks, per-action spans for all 5 middleware actions, exception spans, transform spans, and a parameterized builtin span factory.

#### Interface / API

```python
class MiddlewareTrace:
    @staticmethod
    def decision(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def hook(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def before_run_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def before_iteration_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def before_model_call_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def after_model_response_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def on_model_error_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def before_tool_call_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def after_tool_call_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def after_iteration_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def after_run_ran(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def action_sleep(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def action_abort_run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def action_deny_tool(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def action_retry(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def exception(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def transform_applied(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def builtin(name: str, **attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `before_run_ran` | `middleware.before_run.ran` | CHAIN | DIAGNOSTIC | CURRENT |
| `before_iteration_ran` | `middleware.before_iteration.ran` | CHAIN | DIAGNOSTIC | RUNTIME_ITERATION |
| `before_model_call_ran` | `middleware.before_model_call.ran` | CHAIN | DIAGNOSTIC | RUNTIME_ITERATION |
| `after_model_response_ran` | `middleware.after_model_response.ran` | CHAIN | DIAGNOSTIC | RUNTIME_ITERATION |
| `on_model_error_ran` | `middleware.on_model_error.ran` | CHAIN | DIAGNOSTIC | RUNTIME_ITERATION |
| `before_tool_call_ran` | `middleware.before_tool_call.ran` | CHAIN | DIAGNOSTIC | RUNTIME_ITERATION |
| `after_tool_call_ran` | `middleware.after_tool_call.ran` | CHAIN | DIAGNOSTIC | RUNTIME_ITERATION |
| `after_iteration_ran` | `middleware.after_iteration.ran` | CHAIN | DIAGNOSTIC | RUNTIME_ITERATION |
| `after_run_ran` | `middleware.after_run.ran` | CHAIN | DIAGNOSTIC | AGENT |
| `action_sleep` | `middleware.action.sleep` | CHAIN | VERBOSE | CURRENT |
| `action_abort_run` | `middleware.action.abort_run` | CHAIN | STANDARD | CURRENT |
| `action_deny_tool` | `middleware.action.deny_tool` | CHAIN | STANDARD | CURRENT |
| `action_retry` | `middleware.action.retry` | CHAIN | VERBOSE | CURRENT |
| `exception` | `middleware.exception` | CHAIN | STANDARD | CURRENT |
| `transform_applied` | `middleware.transform.applied` | CHAIN | VERBOSE | CURRENT |
| `builtin(name)` | `middleware.builtin.{name}` | CHAIN | DIAGNOSTIC | CURRENT |

The `builtin` method sanitizes the name by replacing underscores with hyphens, matching the pattern in `AlgorithmTrace.named`.

#### Edge Cases & Error Handling

- `builtin(name)` with empty string produces `middleware.builtin.` which is valid but unhelpful; callers should provide a meaningful name.
- Per-hook ran spans are DIAGNOSTIC by default so they do not flood verbose traces.

### 6.3 ToolTrace Expansion

**File(s):** `vidbyte/trace/components/tools.py`
**Type:** Modified

#### What it does

Adds 8 new span specs covering the full tool execution lifecycle.

#### Interface / API

```python
class ToolTrace:
    @staticmethod
    def call(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def permission(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def resolve(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def validate(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def deny(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def error(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def compact(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def parallel_batch(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def mcp_invoke(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def mcp_attach(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `resolve` | `tool.resolve` | TOOL | VERBOSE | CURRENT |
| `validate` | `tool.validate` | TOOL | VERBOSE | CURRENT |
| `deny` | `tool.deny` | TOOL | STANDARD | CURRENT |
| `error` | `tool.error` | TOOL | STANDARD | CURRENT |
| `compact` | `tool.compact` | TOOL | VERBOSE | CURRENT |
| `parallel_batch` | `tool.parallel_batch` | TOOL | VERBOSE | RUNTIME_ITERATION |
| `mcp_invoke` | `tool.mcp.invoke` | TOOL | VERBOSE | CURRENT |
| `mcp_attach` | `tool.mcp.attach` | TOOL | VERBOSE | AGENT |

### 6.4 ContextTrace Expansion

**File(s):** `vidbyte/trace/components/context.py`
**Type:** Modified

#### What it does

Adds 8 new span specs covering context manager operations, primitive lifecycle, compaction detail, template recording, and handoff synchronization.

#### Interface / API

```python
class ContextTrace:
    @staticmethod
    def window_build(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def primitive_render(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def compaction(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def update(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def manager_upsert(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def manager_extend(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def primitive_add(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def primitive_remove(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def compaction_trigger(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def compaction_strategy(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def template_record(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def handoff_sync(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `manager_upsert` | `context.manager.upsert` | CHAIN | VERBOSE | AGENT |
| `manager_extend` | `context.manager.extend` | CHAIN | VERBOSE | AGENT |
| `primitive_add` | `context.primitive.add` | CHAIN | DIAGNOSTIC | AGENT |
| `primitive_remove` | `context.primitive.remove` | CHAIN | DIAGNOSTIC | AGENT |
| `compaction_trigger` | `context.compaction.trigger` | CHAIN | VERBOSE | RUNTIME_ITERATION |
| `compaction_strategy` | `context.compaction.strategy` | CHAIN | VERBOSE | RUNTIME_ITERATION |
| `template_record` | `context.template.record` | CHAIN | DIAGNOSTIC | AGENT |
| `handoff_sync` | `context.handoff.sync` | CHAIN | VERBOSE | AGENT |

### 6.5 RuntimeTrace Expansion

**File(s):** `vidbyte/trace/components/runtimes.py`
**Type:** Modified

#### What it does

Adds inner-loop detail spans for linear runtime, actor runtime, and search runtime.

#### Interface / API

```python
class LinearRuntimeTrace:
    @staticmethod
    def iteration(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def stop(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def model_call(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def tool_batch(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def stop_condition(**attributes: Any) -> SpanSpec: ...

class ActorRuntimeTrace:
    @staticmethod
    def run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def spawn(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def message(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def completion(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def quiescence(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def compile_prompt(**attributes: Any) -> SpanSpec: ...

class SearchRuntimeTrace:
    @staticmethod
    def run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def node(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def rollback(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def expand(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def evaluate(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def select(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `LinearRuntimeTrace.model_call` | `runtime.linear.model_call` | LLM | STANDARD | RUNTIME_ITERATION |
| `LinearRuntimeTrace.tool_batch` | `runtime.linear.tool_batch` | TOOL | VERBOSE | RUNTIME_ITERATION |
| `LinearRuntimeTrace.stop_condition` | `runtime.linear.stop_condition` | CHAIN | STANDARD | AGENT |
| `ActorRuntimeTrace.quiescence` | `runtime.actor.quiescence` | CHAIN | VERBOSE | CURRENT |
| `ActorRuntimeTrace.compile_prompt` | `runtime.actor.compile_prompt` | CHAIN | DIAGNOSTIC | CURRENT |
| `SearchRuntimeTrace.expand` | `runtime.search.expand` | CHAIN | VERBOSE | CURRENT |
| `SearchRuntimeTrace.evaluate` | `runtime.search.evaluate` | CHAIN | VERBOSE | CURRENT |
| `SearchRuntimeTrace.select` | `runtime.search.select` | CHAIN | VERBOSE | CURRENT |

### 6.6 ParserTrace Expansion

**File(s):** `vidbyte/trace/components/parsers.py`
**Type:** Modified

#### What it does

Adds `is_done` and `response_format_built` span specs.

#### Interface / API

```python
class ParserTrace:
    @staticmethod
    def tool_calls(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def structured_output(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def is_done(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def response_format_built(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `is_done` | `parser.is_done` | PARSER | VERBOSE | RUNTIME_ITERATION |
| `response_format_built` | `parser.response_format_built` | PARSER | DIAGNOSTIC | AGENT |

### 6.7 PipelineTrace (New)

**File(s):** `vidbyte/trace/components/pipelines.py`
**Type:** New file

#### What it does

Defines semantic span specs for pipeline orchestration topologies.

#### Interface / API

```python
class PipelineTrace:
    @staticmethod
    def sequential_run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def parallel_run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def conditional_run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def map_reduce_run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def stage_invoke(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `sequential_run` | `pipeline.sequential.run` | CHAIN | STANDARD | ROOT |
| `parallel_run` | `pipeline.parallel.run` | CHAIN | STANDARD | ROOT |
| `conditional_run` | `pipeline.conditional.run` | CHAIN | STANDARD | ROOT |
| `map_reduce_run` | `pipeline.map_reduce.run` | CHAIN | STANDARD | ROOT |
| `stage_invoke` | `pipeline.stage.invoke` | CHAIN | VERBOSE | CURRENT |

#### Edge Cases & Error Handling

- Pipeline spans use `ParentPolicy.ROOT` because pipelines are top-level orchestration primitives that should not nest under agent runs.

### 6.8 HandoffTrace (New)

**File(s):** `vidbyte/trace/components/handoff.py`
**Type:** New file

#### What it does

Defines semantic span specs for the agent handoff lifecycle.

#### Interface / API

```python
class HandoffTrace:
    @staticmethod
    def generate(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def validate(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def record(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def sync(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `generate` | `handoff.generate` | CHAIN | VERBOSE | AGENT |
| `validate` | `handoff.validate` | CHAIN | VERBOSE | AGENT |
| `record` | `handoff.record` | CHAIN | STANDARD | AGENT |
| `sync` | `handoff.sync` | CHAIN | VERBOSE | AGENT |

### 6.9 SourceTrace (New)

**File(s):** `vidbyte/trace/components/sources.py`
**Type:** New file

#### What it does

Defines semantic span specs for artifact source fetching, loading, and caching.

#### Interface / API

```python
class SourceTrace:
    @staticmethod
    def fetch(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def load(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def cache_hit(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def cache_miss(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `fetch` | `source.fetch` | RETRIEVER | STANDARD | CURRENT |
| `load` | `source.load` | RETRIEVER | STANDARD | CURRENT |
| `cache_hit` | `source.cache.hit` | CHAIN | VERBOSE | CURRENT |
| `cache_miss` | `source.cache.miss` | CHAIN | VERBOSE | CURRENT |

### 6.10 SessionTrace (New)

**File(s):** `vidbyte/trace/components/sessions.py`
**Type:** New file

#### What it does

Defines semantic span specs for session-level tracing.

#### Interface / API

```python
class SessionTrace:
    @staticmethod
    def start(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def end(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def case(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `start` | `session.start` | CHAIN | STANDARD | ROOT |
| `end` | `session.end` | CHAIN | STANDARD | ROOT |
| `case` | `session.case` | CHAIN | VERBOSE | SESSION |

### 6.11 EvalTrace (New)

**File(s):** `vidbyte/trace/components/evals.py`
**Type:** New file

#### What it does

Defines semantic span specs for evaluation harnesses and graders.

#### Interface / API

```python
class EvalTrace:
    @staticmethod
    def run(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def grade(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def behavior(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `run` | `eval.run` | CHAIN | STANDARD | ROOT |
| `grade` | `eval.grade` | CHAIN | STANDARD | CURRENT |
| `behavior` | `eval.behavior` | CHAIN | VERBOSE | CURRENT |

### 6.12 McpTrace (New)

**File(s):** `vidbyte/trace/components/mcp.py`
**Type:** New file

#### What it does

Defines semantic span specs for MCP server lifecycle, search, and transport.

#### Interface / API

```python
class McpTrace:
    @staticmethod
    def attach(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def search(**attributes: Any) -> SpanSpec: ...
    @staticmethod
    def transport(**attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

| Method | Span name | Kind | Detail | Parent policy |
|---|---|---|---|---|
| `attach` | `mcp.attach` | CHAIN | STANDARD | AGENT |
| `search` | `mcp.search` | CHAIN | VERBOSE | CURRENT |
| `transport` | `mcp.transport` | CHAIN | VERBOSE | CURRENT |

### 6.13 Component Exports Update

**File(s):** `vidbyte/trace/components/__init__.py`
**Type:** Modified

#### What it does

Exports all 6 new factory classes and updates `__all__`.

#### Interface / API

```python
from vidbyte.trace.components.agents import AgentTrace, AggregateTrace
from vidbyte.trace.components.algorithms import AlgorithmTrace
from vidbyte.trace.components.context import ContextTrace
from vidbyte.trace.components.evals import EvalTrace
from vidbyte.trace.components.handoff import HandoffTrace
from vidbyte.trace.components.mcp import McpTrace
from vidbyte.trace.components.middleware import MiddlewareTrace
from vidbyte.trace.components.parsers import ParserTrace
from vidbyte.trace.components.pipelines import PipelineTrace
from vidbyte.trace.components.runtimes import ActorRuntimeTrace, LinearRuntimeTrace, SearchRuntimeTrace
from vidbyte.trace.components.sessions import SessionTrace
from vidbyte.trace.components.sources import SourceTrace
from vidbyte.trace.components.tools import ToolTrace

__all__ = [
    "ActorRuntimeTrace",
    "AgentTrace",
    "AggregateTrace",
    "AlgorithmTrace",
    "ContextTrace",
    "EvalTrace",
    "HandoffTrace",
    "LinearRuntimeTrace",
    "McpTrace",
    "MiddlewareTrace",
    "ParserTrace",
    "PipelineTrace",
    "SearchRuntimeTrace",
    "SessionTrace",
    "SourceTrace",
    "ToolTrace",
]
```

### 6.14 Profile Component Registry Update

**File(s):** `vidbyte/trace/profiles.py`
**Type:** Modified

#### What it does

Adds the 5 new component names to the `_COMPONENTS` set so that `TraceProfile.with_components()` accepts them without raising `ConfigurationError`.

#### Logic / Algorithm

Add `"pipelines"`, `"handoff"`, `"sources"`, `"evals"`, `"mcp"` to the `_COMPONENTS` set. The existing `"sessions"` entry already covers the session component.

---

## 7. Data Model Changes

N/A - No data model changes. All new span specs use the existing `SpanSpec` dataclass, `SpanKind` enum, `TraceDetail` enum, and `ParentPolicy` enum.

---

## 8. API Changes

### 8.1 Python API: New Component Factories

**Change type:** New

```python
from vidbyte.trace.components import PipelineTrace, HandoffTrace, SourceTrace, SessionTrace, EvalTrace, McpTrace
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | All factory methods accept arbitrary attributes and return SpanSpec |

### 8.2 Python API: Expanded Existing Factories

**Change type:** Modified (additive)

```python
from vidbyte.trace.components import AgentTrace, MiddlewareTrace, ToolTrace, ContextTrace, LinearRuntimeTrace, ParserTrace

AgentTrace.loop_settings_enforced(which="max_iterations", limit=10)
MiddlewareTrace.before_tool_call_ran(middleware_name="CircuitBreakerMiddleware")
ToolTrace.deny(tool_name="execute_code", permission="elevated")
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | All new methods follow the existing pattern |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/trace-component-expansion.md` | Design doc for trace component expansion |
| CREATE | `vidbyte/trace/components/pipelines.py` | Pipeline orchestration trace span specs |
| CREATE | `vidbyte/trace/components/handoff.py` | Handoff lifecycle trace span specs |
| CREATE | `vidbyte/trace/components/sources.py` | Artifact source trace span specs |
| CREATE | `vidbyte/trace/components/sessions.py` | Session-level trace span specs |
| CREATE | `vidbyte/trace/components/evals.py` | Evaluation harness trace span specs |
| CREATE | `vidbyte/trace/components/mcp.py` | MCP lifecycle trace span specs |
| MODIFY | `vidbyte/trace/components/agents.py` | Add 12 new AgentTrace enforcement/lifecycle spans |
| MODIFY | `vidbyte/trace/components/middleware.py` | Add per-hook, per-action, exception, transform, builtin spans |
| MODIFY | `vidbyte/trace/components/tools.py` | Add 8 new tool lifecycle spans |
| MODIFY | `vidbyte/trace/components/context.py` | Add 8 new context manager/primitive/compaction spans |
| MODIFY | `vidbyte/trace/components/runtimes.py` | Add 8 new inner-loop runtime spans |
| MODIFY | `vidbyte/trace/components/parsers.py` | Add is_done and response_format_built spans |
| MODIFY | `vidbyte/trace/components/__init__.py` | Export 6 new factory classes |
| MODIFY | `vidbyte/trace/profiles.py` | Add 5 new component names to _COMPONENTS |

Summary: 7 files to create, 8 files to modify, 0 files to delete.

---

## 10. Testing Plan

N/A - Design-doc-no-tests workflow. Verification will be done via lint and typecheck.

---

## 11. Dependencies

- **Depends on:** PR #198 (`feat/semantic-trace-profiles`) — provides `SpanSpec`, `SpanKind`, `TraceDetail`, `ParentPolicy`, and the existing component factory pattern.
- **No new external dependencies.**

---

## 12. Rollout

1. Merge PR #198 (`feat/semantic-trace-profiles`) to main.
2. Merge this PR to main.
3. The new span specs are immediately available for use by the runtime integration layer (future PR) and by profile presets (companion PR).

---

## 13. Open Questions

1. **Should `AgentStopReason` values be embedded in `stop_condition` span attributes, or should each reason get its own span name?** Current design: one span name with attributes. Alternative: `runtime.linear.stop_condition.max_iterations`, `runtime.linear.stop_condition.max_tokens`, etc. The attribute approach is simpler and avoids span name explosion.

2. **Should `middleware.builtin.{name}` use the class name or a registered middleware name?** Current design: caller provides the name via the `name` parameter. The `AgentMiddleware.middleware_name` property returns `self.name or self.__class__.__name__`, so either is valid.

3. **Should pipeline spans use `SpanKind.CHAIN` or a new kind?** Current design: `CHAIN`. The existing `SpanKind` enum does not have a `WORKFLOW` kind, and adding one is a non-goal.

---

## 14. Alternatives Considered

### Alternative 1: Sub-component filtering in TraceProfile

Add a `sub_component` field to `SpanSpec` and modify `TraceProfile.allows()` to filter on it. This would allow presets to say "show middleware decisions but not hooks" with more precision.

**Rejected because:** It changes the `SpanSpec` dataclass shape and `allows()` logic, which are non-goals. The existing `detail` level mechanism is sufficient: per-hook spans are `DIAGNOSTIC`, decisions are `STANDARD`/`VERBOSE`, so presets already filter them correctly.

### Alternative 2: New SpanKind values

Add `SpanKind.WORKFLOW` for pipelines, `SpanKind.GENERATOR` for handoff/eval, etc.

**Rejected because:** Adding new `SpanKind` values is a non-goal. The existing 7 kinds (CHAIN, LLM, TOOL, RETRIEVER, EMBEDDING, PROMPT, PARSER) are sufficient. Provider translators would need updating for new kinds, which is out of scope.

### Alternative 3: Parameterized span names instead of distinct methods

Instead of `MiddlewareTrace.before_tool_call_ran()`, use `MiddlewareTrace.hook_ran("before_tool_call")`.

**Rejected because:** The existing pattern (e.g., `AlgorithmTrace.reflexion_trial()`, `AlgorithmTrace.reflexion_reflection()`) uses distinct named methods. The per-hook methods follow this convention and provide better IDE autocomplete and type safety.
