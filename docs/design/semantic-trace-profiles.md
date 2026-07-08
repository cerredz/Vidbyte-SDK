# Design Doc: Semantic Trace Profiles

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-29
**Last Updated:** 2026-06-29

---

## 1. Overview

This feature adds a Vidbyte-native semantic tracing layer under the existing `vidbyte.trace` package. It lets SDK users compose prebuilt trace configurations for agents, runtimes, context-window algorithms, middleware, tools, parsers, aggregation, and sessions, then translate those semantic Vidbyte spans into provider-specific representations such as LangSmith run types. The change preserves the existing `TracerBase` contract and `trace=` API while adding a higher-level `TraceProfile` and `TraceController` that can coordinate multiple component prebuilts inside one coherent trace tree.

---

## 2. Goals & Non-Goals

### Goals

- Add a Vidbyte semantic tracing abstraction above the existing low-level `TracerBase` protocol.
- Keep the public package name as `vidbyte.trace`, matching current repo conventions, while organizing new code into `vidbyte/trace/components/` and `vidbyte/trace/providers/`.
- Provide built-in trace profiles for `minimal`, `default`, `verbose`, and `diagnostic` behavior.
- Provide component-specific prebuilt configuration for agents, aggregate agents, linear runtime, actor runtime, search runtime, context windows, context-window algorithms, middleware decisions, tools, and structured-output parsing.
- Add a `TraceController` that implements `TracerBase`, wraps an existing provider tracer, resolves span parentage, applies profile filtering, and delegates provider calls.
- Add provider translation interfaces that map Vidbyte semantic span kinds to provider-specific details, beginning with LangSmith `run_type`.
- Add session/multi-agent tracing so multiple agent runs can appear under one shared root trace.
- Make multiple component prebuilts compose safely in one trace, for example an aggregate agent whose child proposer uses a context-window algorithm and tools.
- Improve existing default spans by adding tool arguments, parser spans, stop metadata, and context summary spans when enabled by profile.
- Propagate tracing into `AggregateAgent` child agents and add basic semantic spans for search and actor runtimes.
- Preserve existing `Trace.off`, `Trace.debug`, `Trace.langsmith`, `Trace.langfuse`, `Trace.phoenix`, `Trace.continual`, `tracer=`, and `trace=` behavior.
- Add unit tests and a verification script that cover every behavior in this design without calling real provider services.

### Non-Goals

- Do not rename the public package from `vidbyte.trace` to `vidbyte.tracing`.
- Do not remove or replace `vidbyte.lib.tracing.TracerBase`, `SpanContext`, or `NullTracer`.
- Do not make LangSmith, Langfuse, Phoenix, OpenTelemetry, or other provider SDKs mandatory dependencies.
- Do not add private Vidbyte hosted trace ingestion, persistent storage, database schemas, or service-side APIs.
- Do not implement live network verification against LangSmith, Langfuse, or Phoenix in unit tests.
- Do not make every middleware hook a visible span by default; noisy hooks are opt-in through verbose/diagnostic profiles.
- Do not change the semantic behavior of context-window algorithms, middleware decisions, tool execution, or agent output parsing.
- Do not introduce model-generated trace summaries beyond what existing algorithms already do.

---

## 3. Background & Context

The SDK already has three tracing layers:

- `vidbyte.lib.tracing`: provider-neutral low-level protocol with `TracerBase`, `SpanContext`, and `NullTracer`.
- `vidbyte.providers.tracing`: external provider adapters for Langfuse, LangSmith, and Phoenix.
- `vidbyte.trace`: public facade exposing `Trace.off`, `Trace.debug`, `Trace.langsmith`, `Trace.langfuse`, `Trace.phoenix`, and continual trace artifacts.

The current runtime emits a small fixed tree: `agent.run`, `llm.call`, and `tool.call`. In LangSmith, the useful UI behavior comes from provider run types such as `chain`, `llm`, and `tool`. The SDK currently infers those mostly from span names in `LangSmithTracer`. That works for the first layer of observability, but it does not model Vidbyte-specific concepts like runtime iterations, context-window builds, context-window algorithms, middleware decisions, aggregate proposer/synthesis phases, parser validation, retriever/embedding steps, or multi-agent sessions.

The repo's package rules say public trace presets belong in `vidbyte/trace/`, provider-neutral protocols belong in `vidbyte/lib/tracing/`, and external adapters belong in `vidbyte/providers/tracing/`. This design preserves those boundaries. The new `vidbyte/trace/providers/` package is not a replacement for external adapters; it is a provider translation layer that converts Vidbyte semantic spans into provider-adapter attributes before delegating to `vidbyte.providers.tracing.*`.

Relevant current implementation details:

- `BaseAgent.generate_reply()` opens one `agent.run` trace and passes the trace context into runtime execution.
- `AgentRuntime._invoke_with_middleware()` opens `llm.call` spans.
- `AgentRuntime.execute_tool_call()` opens `tool.call` spans, but currently does not include tool arguments in span inputs.
- `AgentRuntime._llm_trace_inputs()` already captures messages, tools, metadata, and a context-window summary.
- `AggregateAgent` creates proposer and aggregator child agents but does not currently pass its tracer to those child agents.
- `SearchTreeRuntimeComponent` and actor runtimes accept a `tracer` argument but do not currently emit meaningful runtime spans.
- Middleware records events internally, but trace visibility is limited to model/tool spans.

---

## 4. Requirements

### Functional Requirements

1. The feature must preserve all existing public tracing APIs and imports.
2. `TraceProfile.minimal()` must include only the existing core spans: `agent.run`, `llm.call`, and `tool.call`.
3. `TraceProfile.default()` must include minimal spans plus parser, retriever, embedding, agent stop, tool inputs/outputs, and session behavior when applicable.
4. `TraceProfile.verbose()` must include default spans plus runtime iteration, context-window build summaries, context-window algorithm spans, aggregate phases, and middleware decisions that alter control flow.
5. `TraceProfile.diagnostic()` must include verbose spans plus all middleware hook decisions, fuller context payloads, and component-level diagnostic metadata subject to redaction and size limits.
6. `TraceController` must implement `TracerBase` so it can be supplied anywhere a tracer is accepted today.
7. `TraceController` must wrap an inner `TracerBase`, a `TraceProfile`, and a provider translator.
8. `TraceController.start_trace`, `start_span`, `end_span`, and `end_trace` must delegate to the inner tracer when the active profile allows the span.
9. When a profile suppresses a span, the controller must return a no-op semantic span context that can still be ended safely.
10. Provider translators must map Vidbyte span kinds to provider-specific attributes without changing SDK component semantics.
11. The LangSmith translator must map semantic span kinds to LangSmith run types: `chain`, `llm`, `tool`, `retriever`, `embedding`, `prompt`, and `parser`.
12. LangSmith translation must pass `run_type` through span attributes so the existing `LangSmithTracer` can use it.
13. Generic translation must preserve existing behavior for debug, continual, Langfuse, Phoenix, custom, and null tracers.
14. The public facade must add `Trace.profile(inner, profile, provider=None)`.
15. The public facade must add `Trace.langsmith_default(...)`, returning a profiled LangSmith tracer.
16. The public facade must add `Trace.langsmith_session(...)`, returning a profiled session-capable LangSmith tracer.
17. The public facade must add `Trace.langsmith_verbose(...)` as a convenience for `TraceProfile.verbose()`.
18. The public facade must add `Trace.session(inner, name=None, profile=None, provider=None)`.
19. Session tracing must open one shared session root and convert child agent `start_trace("agent.run")` calls into child spans under that root while the session is active.
20. Session tracing must expose sync and async context-manager entry points.
21. Session tracing must close the root with output or error and clear session state in `finally` paths.
22. Component trace presets must be composable by a single profile instead of each component owning an isolated tracer.
23. Parent resolution must prefer explicit parents, then active semantic scope, then profile-defined parent policy, then root.
24. The controller must avoid using process-global mutable parent state that breaks concurrent async runs.
25. `AgentTrace` must define semantic specs for `agent.run`, `agent.stop`, and agent metadata payloads.
26. `AggregateTrace` must define semantic specs for `aggregate.run`, `aggregate.proposer`, `aggregate.synthesis`, and aggregate failures.
27. `LinearRuntimeTrace` must define semantic specs for `runtime.iteration` and direct runtime stop conditions.
28. `ActorRuntimeTrace` must define semantic specs for actor runtime run, spawn, actor message, actor LLM call, and termination.
29. `SearchRuntimeTrace` must define semantic specs for search run, node expansion, node selection, rollback, and completion.
30. `ContextTrace` must define semantic specs for context-window build, context primitive render summary, context compaction, and context updates.
31. `AlgorithmTrace` must define semantic specs for reflexion trial/reflection, multi-provider grader candidate/grading, trajectory checkpoints, problem-space search, and error correction.
32. `MiddlewareTrace` must define semantic specs for middleware decisions, retries, aborts, deny-tool decisions, sleeps, and fail-open/fail-closed errors.
33. `ToolTrace` must add tool input/arguments, call id, tool metadata, permission state, result state, and output/error where enabled by profile.
34. `ParserTrace` must define semantic specs for tool-call parsing and structured-output validation.
35. `BaseAgent` must continue opening `agent.run` through the tracer path but include semantic attributes that the controller can translate.
36. `BaseAgent` must preserve direct custom tracer behavior when the user passes a raw `TracerBase` that is not a `TraceController`.
37. `BaseAgent` must pass the resolved tracer into internal aggregate agents and aggregate child agents when those agents are SDK-built.
38. `AggregateAgent` must preserve user-supplied external fake agent-like objects and only propagate tracing to SDK `BaseAgent` children it constructs or forks.
39. `AgentRuntime` must add optional spans for runtime iteration, context build, parser, and stop events according to profile.
40. `AgentRuntime` must not emit duplicate `llm.call` or `tool.call` spans when semantic profiling is active.
41. Search and actor runtimes must emit basic semantic spans when the tracer is a controller and fall back safely for non-controller tracers.
42. Context-window algorithm runtime adapters must emit algorithm-specific spans when enabled and keep existing metadata outputs unchanged.
43. All trace payloads must use the existing safe trace value behavior or an equivalent profile-level redaction/truncation path.
44. A user must be able to compose `TraceProfile.default().with_components(...)` to enable or disable component groups.
45. Existing `Trace.debug(events)` must still record readable events and must work behind `Trace.profile(...)`.
46. Existing tests for `tests/test_tracing.py` and `tests/test_trace_facade.py` must continue to pass.
47. The verification script must execute every test case in Section 10 and print PASS/FAIL per case.

### Non-Functional Requirements

- Performance: Minimal profile overhead must remain close to the existing tracing path: one controller decision per current span and no provider calls for suppressed spans.
- Scalability: The controller must support nested and concurrent async agent runs without cross-run parent leaks.
- Security: Profile redaction must strip credential-like keys and truncate large prompt, tool, context, and metadata values.
- Reliability: Tracing must remain fail-open by default. Provider delivery errors must not fail agent execution unless the underlying provider adapter is configured for strict verification.
- Compatibility: Raw `TracerBase` implementations must still work when passed through `trace=` or `tracer=`.
- Observability: Semantic span names must remain stable and documented so provider traces are interpretable across LangSmith, Langfuse, Phoenix, debug traces, and future adapters.
- Maintainability: Component modules must describe semantic spans and payload construction; the controller alone owns final tree construction and provider delegation.
- Testability: Tests must use `DebugTracer`, fake tracers, and patched provider constructors. No test may require real LangSmith, Langfuse, Phoenix, model-provider, or network access.

---

## 5. High-Level Design

The design introduces a semantic tracing layer inside `vidbyte.trace`. The key new runtime object is `TraceController`, which implements `TracerBase`. A controller wraps an inner tracer such as `LangSmithTracer`, `DebugTracer`, or a user custom tracer. SDK components continue to call tracer methods, but when the tracer is a controller, those calls are interpreted as Vidbyte semantic spans, filtered by `TraceProfile`, translated through a provider translator, and then delegated to the inner tracer.

Component packages such as `vidbyte.trace.components.runtimes` and `vidbyte.trace.components.algorithms` do not directly call LangSmith or any provider. They define span names, semantic kinds, parent policies, detail levels, and payload builders. This keeps provider concepts out of agent, runtime, context, and middleware logic.

Provider translators under `vidbyte.trace.providers` map semantic spans to provider adapter attributes. For LangSmith, this means converting Vidbyte span kinds into LangSmith `run_type` values. For debug/custom/other providers, generic translation passes names and attributes through with only safe metadata normalization.

Multiple prebuilts compose because only the controller owns the final tree. For example, an aggregate agent with a child proposer using reflexion and tools can produce one coherent tree:

```text
session.run                         chain
+-- agent.run                        chain
    +-- aggregate.run                chain
        +-- aggregate.proposer       chain
        |   +-- agent.run            chain
        |       +-- runtime.iteration chain
        |           +-- context.window.build prompt
        |           +-- algorithm.reflexion.trial chain
        |           +-- llm.call     llm
        |           +-- tool.call    tool
        +-- aggregate.synthesis      chain
            +-- agent.run            chain
                +-- llm.call         llm
```

The public API remains simple:

```python
from vidbyte import Agent, Trace

agent = Agent(
    name="worker",
    system_prompt="Work carefully.",
    runner=my_runner,
    trace=Trace.langsmith_default(project="vidbyte-agents"),
)
```

Custom composition remains available:

```python
from vidbyte import Trace, TraceProfile

profile = TraceProfile.default().with_components(
    algorithms="verbose",
    context="summary",
    middleware="decisions_only",
    tools="inputs_outputs",
)

trace = Trace.profile(
    inner=Trace.langsmith(api_key="...", project="sdk"),
    profile=profile,
    provider="langsmith",
)
```

---

## 6. Detailed Design

### 6.1 Semantic Trace Schema

**File(s):** `vidbyte/trace/schema.py`
**Type:** New file

#### What it does

Defines provider-neutral semantic trace types used by profiles, components, controller, and translators.

#### Interface / API

```python
class TraceDetail(str, Enum): ...
class SpanKind(str, Enum): ...
class ParentPolicy(str, Enum): ...

@dataclass(frozen=True, slots=True)
class SpanSpec: ...

@dataclass(slots=True)
class SemanticSpanContext(SpanContext): ...
```

#### Logic / Algorithm

1. `TraceDetail` contains `minimal`, `standard`, `verbose`, and `diagnostic`.
2. `SpanKind` contains `chain`, `llm`, `tool`, `retriever`, `embedding`, `prompt`, and `parser`.
3. `ParentPolicy` contains `explicit`, `current`, `agent`, `runtime_iteration`, `aggregate`, `session`, and `root`.
4. `SpanSpec` stores `name`, `kind`, `component`, `detail`, `parent_policy`, `attributes`, and optional `metadata`.
5. `SemanticSpanContext` wraps the provider context returned by the inner tracer, plus the semantic spec and a boolean `suppressed`.

#### Edge Cases & Error Handling

- Unknown enum values raise `ValueError` during construction.
- Suppressed contexts are safe to pass to `end_span` and `end_trace`.
- Attributes default to an empty mapping and are copied before use.

### 6.2 Trace Profiles

**File(s):** `vidbyte/trace/profiles.py`
**Type:** New file

#### What it does

Defines `TraceProfile`, component settings, preset constructors, and redaction/truncation settings.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class TraceComponentSettings: ...

@dataclass(frozen=True, slots=True)
class TraceProfile:
    @classmethod
    def minimal(cls) -> TraceProfile: ...
    @classmethod
    def default(cls) -> TraceProfile: ...
    @classmethod
    def verbose(cls) -> TraceProfile: ...
    @classmethod
    def diagnostic(cls) -> TraceProfile: ...
    def with_components(self, **components: str | bool) -> TraceProfile: ...
    def allows(self, spec: SpanSpec) -> bool: ...
```

#### Logic / Algorithm

1. `minimal()` enables agents, LLM calls, and tool calls only.
2. `default()` enables parser/retriever/embedding spans when applicable, tool input/output, session roots, and agent stop metadata.
3. `verbose()` enables runtime iteration, context summaries, aggregate phases, algorithm spans, and middleware decisions that alter behavior.
4. `diagnostic()` enables all component span categories and fuller payloads.
5. `with_components(...)` returns a new immutable profile with named component overrides.
6. `allows(spec)` checks component setting and detail threshold.

#### Edge Cases & Error Handling

- Unknown component keys raise `ConfigurationError`.
- Unknown component values raise `ConfigurationError`.
- `max_chars <= 0` raises `ConfigurationError`.
- Raw strings such as `"true"` are rejected unless explicitly supported values.

### 6.3 Trace Controller

**File(s):** `vidbyte/trace/controller.py`
**Type:** New file

#### What it does

Implements the composable semantic tracer that wraps a provider tracer, filters spans, resolves parent contexts, translates payloads, and delegates to the inner tracer.

#### Interface / API

```python
class TraceController(TracerBase):
    def __init__(self, inner: TracerBase, profile: TraceProfile | None = None, translator: ProviderTraceTranslator | None = None) -> None: ...
    def start_trace(self, name: str, **attributes: Any) -> SemanticSpanContext: ...
    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SemanticSpanContext: ...
    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def open_span(self, spec: SpanSpec, parent: SpanContext | None = None) -> SemanticSpanContext: ...
```

#### Logic / Algorithm

1. Normalize the inner tracer; `None` becomes `NullTracer`.
2. Normalize the profile; `None` becomes `TraceProfile.default()`.
3. Normalize the translator; `None` becomes `GenericProviderTranslator`.
4. Convert legacy `start_trace("agent.run", ...)` and `start_span("llm.call", ...)` calls into `SpanSpec` values.
5. Apply profile filtering with `profile.allows(spec)`.
6. If suppressed, return a `SemanticSpanContext` with no provider context.
7. If allowed, translate name/attributes through the provider translator.
8. Delegate to `inner.start_trace` or `inner.start_span`.
9. Use `contextvars` to track current semantic stack for async-safe parent resolution.
10. On end, delegate only if the context is not suppressed and has a provider context.

#### Edge Cases & Error Handling

- Raw provider contexts from non-controller tracers are passed through safely.
- Ending a suppressed context is a no-op.
- Provider errors follow existing provider adapter behavior.
- Async concurrent tasks do not share active span stacks.

### 6.4 Session Tracing

**File(s):** `vidbyte/trace/session.py`
**Type:** New file

#### What it does

Provides SDK-owned multi-agent/session tracing that groups multiple agent runs under one root trace.

#### Interface / API

```python
class SessionTraceController(TraceController):
    def begin_session(self, name: str, **attributes: Any) -> SpanContext: ...
    def end_session(self, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def session(self, name: str, **attributes: Any) -> ContextManager[SessionTraceController]: ...
    def async_session(self, name: str, **attributes: Any) -> AsyncContextManager[SessionTraceController]: ...
```

#### Logic / Algorithm

1. `begin_session` opens a semantic `session.run` root trace.
2. While a session root is active, `start_trace("agent.run")` opens an `agent.run` child span under the session root.
3. `end_trace` closes child spans while a session is active.
4. `end_session` closes the root trace and clears the active root context.
5. Sync and async context managers call begin/end in `try/finally`.

#### Edge Cases & Error Handling

- Beginning a second session before ending the first raises `ConfigurationError`.
- Ending with no active session is a no-op.
- Exceptions inside session blocks are passed as trace errors and re-raised by the caller's block.

### 6.5 Provider Translation Interfaces

**File(s):** `vidbyte/trace/providers/base.py`, `vidbyte/trace/providers/generic.py`, `vidbyte/trace/providers/langsmith.py`, `vidbyte/trace/providers/__init__.py`
**Type:** New files

#### What it does

Defines how Vidbyte semantic spans map to provider adapter payloads.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class ProviderSpanPayload: ...

class ProviderTraceTranslator:
    def translate_start(self, spec: SpanSpec) -> ProviderSpanPayload: ...

class GenericProviderTranslator(ProviderTraceTranslator): ...
class LangSmithProviderTranslator(ProviderTraceTranslator): ...
```

#### Logic / Algorithm

1. `ProviderSpanPayload` stores provider name, span name, and attributes.
2. `GenericProviderTranslator` passes semantic names and attributes through.
3. `LangSmithProviderTranslator` adds `run_type=spec.kind.value` for non-root spans and standardizes root `chain` spans.
4. Provider translators never call network APIs.

#### Edge Cases & Error Handling

- Unknown span kinds are rejected before translation by `SpanKind`.
- Translator output attributes are copied to prevent mutation after start.
- Generic translation remains compatible with existing `DebugTracer` event assertions.

### 6.6 Component Registry

**File(s):** `vidbyte/trace/registry.py`
**Type:** New file

#### What it does

Provides a small registry for component names, detail defaults, and parent policies used by component trace modules.

#### Interface / API

```python
class TraceComponentRegistry:
    def register(self, component: str, *, default_detail: TraceDetail) -> None: ...
    def default_detail(self, component: str) -> TraceDetail: ...
```

#### Logic / Algorithm

1. Initialize built-in components: agents, aggregate, runtimes, actor_runtime, search_runtime, context, algorithms, middleware, tools, parsers, retrieval, embeddings, session.
2. Reject duplicate component registrations.
3. Provide defaults to `SpanSpec` builders.

#### Edge Cases & Error Handling

- Unknown components in profiles raise `ConfigurationError`.
- Duplicate registrations raise `ConfigurationError`.

### 6.7 Agent Component Tracing

**File(s):** `vidbyte/trace/components/agents.py`
**Type:** New file

#### What it does

Defines semantic spans and payload helpers for `BaseAgent`, `AggregateAgent`, and agent-as-tool delegation.

#### Interface / API

```python
class AgentTrace:
    def run_spec(self, **attributes: Any) -> SpanSpec: ...
    def stop_spec(self, **attributes: Any) -> SpanSpec: ...

class AggregateTrace:
    def run_spec(self, **attributes: Any) -> SpanSpec: ...
    def proposer_spec(self, **attributes: Any) -> SpanSpec: ...
    def synthesis_spec(self, **attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

1. `AgentTrace.run_spec` maps to `agent.run`, `SpanKind.CHAIN`, and minimal detail.
2. `AgentTrace.stop_spec` maps to `agent.stop`, `SpanKind.CHAIN`, and default detail.
3. `AggregateTrace.run_spec` maps to `aggregate.run`, verbose detail.
4. `AggregateTrace.proposer_spec` maps to `aggregate.proposer`, verbose detail.
5. `AggregateTrace.synthesis_spec` maps to `aggregate.synthesis`, verbose detail.

#### Edge Cases & Error Handling

- Missing agent names become `"unknown"` instead of failing tracing.
- Aggregate fake agent-like objects that do not expose SDK tracer fields are not mutated.

### 6.8 Runtime Component Tracing

**File(s):** `vidbyte/trace/components/runtimes.py`
**Type:** New file

#### What it does

Defines semantic spans and payload helpers for linear, actor, and search runtimes.

#### Interface / API

```python
class LinearRuntimeTrace: ...
class ActorRuntimeTrace: ...
class SearchRuntimeTrace: ...
```

#### Logic / Algorithm

1. `LinearRuntimeTrace.iteration_spec` maps to `runtime.iteration`, verbose detail.
2. `LinearRuntimeTrace.stop_spec` maps to `runtime.stop`, default detail.
3. `ActorRuntimeTrace.run_spec` maps to `runtime.actor.run`, verbose detail.
4. `ActorRuntimeTrace.spawn_spec` maps to `runtime.actor.spawn`, diagnostic detail.
5. `ActorRuntimeTrace.message_spec` maps to `runtime.actor.message`, diagnostic detail.
6. `SearchRuntimeTrace.run_spec` maps to `runtime.search.run`, verbose detail.
7. `SearchRuntimeTrace.node_spec` maps to `runtime.search.node`, diagnostic detail.

#### Edge Cases & Error Handling

- Search runtimes with zero candidates still close the search span with completion metadata.
- Actor runtime cleanup still closes runtime spans if tasks are cancelled.

### 6.9 Context Component Tracing

**File(s):** `vidbyte/trace/components/context.py`
**Type:** New file

#### What it does

Defines semantic spans and payload helpers for context-window construction, primitive rendering, and compaction behavior.

#### Interface / API

```python
class ContextTrace:
    def window_build_spec(self, **attributes: Any) -> SpanSpec: ...
    def primitive_render_spec(self, **attributes: Any) -> SpanSpec: ...
    def compaction_spec(self, **attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

1. `context.window.build` uses `SpanKind.PROMPT`.
2. Context build attributes include system length, message count, tool count, primitive count, and profile-controlled payload detail.
3. Primitive render spans are diagnostic-only by default.
4. Compaction spans use `SpanKind.CHAIN` and record before/after counts when available.

#### Edge Cases & Error Handling

- Empty context managers still emit summaries with zero counts when enabled.
- Full context payloads are only included in diagnostic mode and still use redaction/truncation.

### 6.10 Algorithm Component Tracing

**File(s):** `vidbyte/trace/components/algorithms.py`
**Type:** New file

#### What it does

Defines semantic spans for context-window algorithms.

#### Interface / API

```python
class AlgorithmTrace:
    def reflexion_trial_spec(self, **attributes: Any) -> SpanSpec: ...
    def reflexion_reflection_spec(self, **attributes: Any) -> SpanSpec: ...
    def multi_provider_candidate_spec(self, **attributes: Any) -> SpanSpec: ...
    def multi_provider_grader_spec(self, **attributes: Any) -> SpanSpec: ...
    def trajectory_checkpoint_spec(self, **attributes: Any) -> SpanSpec: ...
    def problem_space_search_spec(self, **attributes: Any) -> SpanSpec: ...
    def error_correction_spec(self, **attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

1. Reflexion trials use `algorithm.reflexion.trial`, `SpanKind.CHAIN`.
2. Reflexion reflection model calls remain visible as `llm.call` but get metadata linking them to `algorithm.reflexion.reflect`.
3. Multi-provider grader candidate runs use `algorithm.multi_provider_grader.candidate`.
4. Grading uses `algorithm.multi_provider_grader.grade`.
5. Inner-loop algorithms use chain spans around their lifecycle hooks and prompt/parser spans around model-backed subcalls when possible.

#### Edge Cases & Error Handling

- Algorithm failures close spans with error but preserve existing exception behavior.
- Algorithms without a model-backed step still emit lifecycle spans only when enabled.

### 6.11 Middleware Component Tracing

**File(s):** `vidbyte/trace/components/middleware.py`
**Type:** New file

#### What it does

Defines semantic spans for middleware decisions and provides helpers for converting `MiddlewareDecision` and `MiddlewareEvent` into safe trace metadata.

#### Interface / API

```python
class MiddlewareTrace:
    def decision_spec(self, **attributes: Any) -> SpanSpec: ...
    def error_spec(self, **attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

1. Continue decisions are suppressed unless diagnostic mode is active.
2. Non-continue actions such as retry, abort, deny-tool, and sleep are visible in verbose mode.
3. Middleware errors are visible in verbose mode.
4. Metadata is sanitized before entering spans.

#### Edge Cases & Error Handling

- Middleware fail-open errors are traced as non-fatal decisions.
- Middleware fail-closed errors are traced before returning abort decisions.

### 6.12 Tool Component Tracing

**File(s):** `vidbyte/trace/components/tools.py`
**Type:** New file

#### What it does

Defines semantic spans and payload helpers for SDK tool execution.

#### Interface / API

```python
class ToolTrace:
    def call_spec(self, **attributes: Any) -> SpanSpec: ...
    def permission_spec(self, **attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

1. `tool.call` uses `SpanKind.TOOL` and minimal detail.
2. Default profile includes tool name, arguments, call id, input metadata, result state, and output.
3. Permission spans are verbose-only unless denied.
4. Tool output is truncated by profile settings.

#### Edge Cases & Error Handling

- Empty argument dicts are preserved as `{}`.
- Unknown tools still produce `tool.call` spans closed with error.
- Denied tools that bypass execution still produce tool result metadata.

### 6.13 Parser Component Tracing

**File(s):** `vidbyte/trace/components/parsers.py`
**Type:** New file

#### What it does

Defines semantic spans for provider tool-call parsing and structured-output validation.

#### Interface / API

```python
class ParserTrace:
    def tool_calls_spec(self, **attributes: Any) -> SpanSpec: ...
    def structured_output_spec(self, **attributes: Any) -> SpanSpec: ...
```

#### Logic / Algorithm

1. Tool-call parser spans use `parser.tool_calls`, `SpanKind.PARSER`, default detail.
2. Structured-output validation spans use `parser.structured_output`, `SpanKind.PARSER`, default detail.
3. Successful parser spans record counts and schema names when available.
4. Failed parser spans record sanitized validation errors.

#### Edge Cases & Error Handling

- No tool calls records count zero without emitting a parser span in minimal mode.
- Invalid JSON closes parser span with validation error but preserves current final result behavior.

### 6.14 Trace Facade Changes

**File(s):** `vidbyte/trace/base.py`, `vidbyte/trace/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Adds public profile/session helpers while preserving existing facade behavior.

#### Interface / API

```python
class Trace:
    @staticmethod
    def profile(inner: TracerBase, profile: TraceProfile | None = None, provider: str | ProviderTraceTranslator | None = None) -> TracerBase: ...
    @staticmethod
    def session(inner: TracerBase, name: str | None = None, profile: TraceProfile | None = None, provider: str | ProviderTraceTranslator | None = None) -> TracerBase: ...
    @staticmethod
    def langsmith_default(api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False, include_runtime_info: bool = False, profile: TraceProfile | None = None) -> TracerBase: ...
    @staticmethod
    def langsmith_verbose(...same args...) -> TracerBase: ...
    @staticmethod
    def langsmith_session(...same args..., name: str | None = None) -> TracerBase: ...
```

#### Logic / Algorithm

1. Existing helper methods remain unchanged.
2. `Trace.profile` returns `TraceController`.
3. `Trace.session` returns `SessionTraceController`.
4. `Trace.langsmith_default` builds `LangSmithTracer`, wraps it with `LangSmithProviderTranslator`, and uses `TraceProfile.default()` unless profile is supplied.
5. `Trace.langsmith_verbose` uses `TraceProfile.verbose()`.
6. `Trace.langsmith_session` uses `SessionTraceController`.
7. Root exports include `TraceProfile`, `TraceController`, and `SessionTraceController`.

#### Edge Cases & Error Handling

- `Trace.profile(None)` raises `ConfigurationError`.
- Unknown provider names raise `ConfigurationError`.
- Existing `Trace.langsmith(...)` keeps returning the raw provider tracer.

### 6.15 BaseAgent Integration

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Threads semantic trace metadata through existing agent root spans and propagates profiled tracing into aggregate agents.

#### Interface / API

```python
class BaseAgent:
    def _resolve_tracer(...) -> TracerBase: ...
    def _build_aggregate_agent(self) -> BaseAgent: ...
```

#### Logic / Algorithm

1. Preserve existing `_resolve_tracer`.
2. Add semantic attributes such as `component="agents"`, `span_kind="chain"`, and profile-friendly metadata to existing `agent.run` starts.
3. Add an `agent.stop` span through `TraceController` when enabled.
4. Pass `tracer=self._tracer` into internally built `AggregateAgent`.
5. Ensure aggregate delegation still returns the aggregate reply exactly as today.

#### Edge Cases & Error Handling

- Existing custom tracers ignore unknown semantic attributes safely.
- Aggregate delegation still rejects incompatible non-linear runtime plans as today.

### 6.16 AgentRuntime Integration

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Adds semantic instrumentation for linear runtime iterations, context builds, parser events, tool input/output, middleware decisions, and stop metadata.

#### Interface / API

```python
class AgentRuntime:
    async def _arun_once(...) -> AgentResult: ...
    async def _invoke_with_middleware(...) -> tuple[object | AgentResult, int]: ...
    async def execute_tool_call(...) -> tuple[ToolCallContext, ToolResult]: ...
```

#### Logic / Algorithm

1. Open `runtime.iteration` spans around each loop iteration when profile enables runtime spans.
2. Emit `context.window.build` spans after `_build_iteration_call_options`.
3. Continue emitting exactly one `llm.call` span per model invocation.
4. Emit `parser.tool_calls` spans around `ToolsFormatter.parse_tool_calls` when enabled.
5. Include `tool_input`, `call_id`, `tool_metadata`, and state fields in `tool.call`.
6. Emit middleware decision spans for non-continue actions and diagnostic all-hook mode.
7. Emit `parser.structured_output` spans when `output_schema` or tool output schema validation runs.
8. Emit stop metadata as `agent.stop` or `runtime.stop` when enabled.

#### Edge Cases & Error Handling

- CancelledError still closes open LLM spans.
- Tool exceptions still close `tool.call` with error.
- Parser spans must not change parsing exceptions or result behavior.
- Suppressed profile spans do not affect token usage, loop counts, or final metadata.

### 6.17 AggregateAgent Integration

**File(s):** `vidbyte/agents/aggregation.py`
**Type:** Modified

#### What it does

Adds semantic aggregate spans and propagates tracing into SDK-built proposer/aggregator children.

#### Interface / API

```python
class AggregateAgent(BaseAgent):
    def __init__(..., tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None) -> None: ...
```

#### Logic / Algorithm

1. Accept `tracer` and `trace` parameters and pass them to `BaseAgent`.
2. Open `aggregate.run` around `MultiProviderAggregator.aggregate`.
3. Open `aggregate.proposer` around each proposer execution when enabled.
4. Open `aggregate.synthesis` around the aggregator call.
5. Pass `tracer=self._tracer` to `_build_proposer_agent` and `_build_aggregator`.
6. Preserve external fake agent-like objects without mutation.

#### Edge Cases & Error Handling

- Failing proposer spans close with error and still allow survivor synthesis when current aggregate logic allows it.
- All-proposer failure preserves `AggregateExecutionError`.
- Forked aggregate agents preserve tracer.

### 6.18 Search Runtime Integration

**File(s):** `vidbyte/agents/runtimes/search.py`
**Type:** Modified

#### What it does

Adds basic semantic search-runtime spans without changing conceptual MCTS behavior.

#### Interface / API

```python
class SearchTreeRuntimeComponent:
    async def arun(...) -> StrategyResult: ...
```

#### Logic / Algorithm

1. Store `self._tracer = tracer or NullTracer()`.
2. Open `runtime.search.run` around `arun`.
3. Open `runtime.search.node` spans for expansion and selection when diagnostic profile is active.
4. Close run span with metadata including depth and total nodes.

#### Edge Cases & Error Handling

- If expansion returns no candidates, close run span with zero candidate count.
- Exceptions close the search run span with error and propagate as before.

### 6.19 Actor Runtime Integration

**File(s):** `vidbyte/agents/runtimes/actor/broker.py`
**Type:** Modified

#### What it does

Adds basic actor-runtime semantic spans for actor run, spawn, message, and actor completion.

#### Interface / API

```python
class BaseActorRuntime:
    async def spawn_instance(self, actor: AgentActor) -> AgentActor: ...
    async def invoke_actor_completion(self, actor: AgentActor, prompt: str) -> str: ...
    async def arun(...) -> StrategyResult: ...
```

#### Logic / Algorithm

1. Store `self._tracer = tracer or NullTracer()`.
2. Open `runtime.actor.run` around `arun`.
3. Emit `runtime.actor.spawn` when actors are registered in diagnostic mode.
4. Emit `runtime.actor.message` when messages are routed in diagnostic mode.
5. Emit `llm.call` or `runtime.actor.completion` around actor completion calls with actor id metadata.

#### Edge Cases & Error Handling

- Cancelled actor tasks do not leak open runtime spans.
- Quiescence and max-loop termination close run span with termination metadata.

### 6.20 Provider Adapter Compatibility

**File(s):** `vidbyte/providers/tracing/langsmith.py`, `vidbyte/providers/tracing/langfuse.py`, `vidbyte/providers/tracing/phoenix.py`
**Type:** Modified

#### What it does

Ensures provider adapters tolerate semantic translation attributes without breaking current users.

#### Interface / API

```python
class LangSmithTracer:
    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> LangSmithSpanContext: ...
```

#### Logic / Algorithm

1. Keep LangSmith `run_type` override support.
2. Ensure LangSmith child span `trace_id` is passed to `create_run` when available.
3. For Langfuse and Phoenix, preserve semantic attributes as metadata/attributes and do not require provider-specific run types.
4. Keep provider tracing fail-open on delivery errors.

#### Edge Cases & Error Handling

- Older LangSmith client shapes continue using the existing best-effort diagnostic behavior.
- Unknown semantic attributes do not fail Langfuse or Phoenix spans.

### 6.21 Documentation And Skills

**File(s):** `README.md`, `vidbyte/trace/README.md`, `skills/vidbyte-sdk/SKILL.md`, `skills/sdk/SKILL.md`
**Type:** Modified

#### What it does

Documents semantic trace profiles, package boundaries, and public API examples.

#### Interface / API

```python
trace = Trace.langsmith_default(project="sdk")
trace = Trace.langsmith_session(name="job-run")
profile = TraceProfile.verbose().with_components(middleware="decisions_only")
```

#### Logic / Algorithm

1. README tracing section gets default/session/profile examples.
2. Trace README documents semantic span names and provider translation.
3. Skill files update package layout and rules for new `vidbyte.trace` subpackages.

#### Edge Cases & Error Handling

- Documentation must clearly state that `Trace.langsmith(...)` remains raw provider tracing while `Trace.langsmith_default(...)` adds semantic profiling.

### 6.22 Tests And Verification Script

**File(s):** `tests/test_semantic_tracing.py`, `tests/test_tracing.py`, `tests/test_trace_facade.py`, `tests/test_aggregate_agent.py`, `scripts/test-semantic-trace-profiles.py`
**Type:** New and modified files

#### What it does

Adds coverage for the semantic tracing layer and extends current tracing/aggregate tests for compatibility.

#### Interface / API

```python
class TraceProfileTests(unittest.TestCase): ...
class TraceControllerTests(unittest.TestCase): ...
class SessionTraceTests(unittest.TestCase): ...
class ComponentTraceIntegrationTests(unittest.IsolatedAsyncioTestCase): ...
```

#### Logic / Algorithm

1. Unit tests cover schema, profiles, controller suppression, provider translation, session parentage, and component span specs.
2. Integration tests use fake runners and `DebugTracer` to assert emitted event trees.
3. Aggregate tests assert tracer propagation into SDK-built children.
4. Script test imports implementation directly and runs all Section 10 cases with PASS/FAIL output.

#### Edge Cases & Error Handling

- No tests call real provider services.
- Tests patch provider constructors where needed.
- Script exits non-zero on first or aggregate failures.

---

## 7. Data Model Changes

### 7.1 `SpanSpec`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class SpanSpec:
    name: str
    kind: SpanKind = SpanKind.CHAIN
    component: str = "custom"
    detail: TraceDetail = TraceDetail.STANDARD
    parent_policy: ParentPolicy = ParentPolicy.CURRENT
    attributes: Mapping[str, Any] = field(default_factory=dict)
```

**Migration strategy:** N/A - in-process SDK tracing type only.

### 7.2 `SemanticSpanContext`

**Change type:** New

```python
@dataclass(slots=True)
class SemanticSpanContext(SpanContext):
    provider_context: SpanContext | None = None
    spec: SpanSpec | None = None
    suppressed: bool = False
```

**Migration strategy:** N/A - extends existing in-process context pattern.

### 7.3 `TraceProfile`

**Change type:** New

```python
@dataclass(frozen=True, slots=True)
class TraceProfile:
    detail: TraceDetail
    components: Mapping[str, str | bool]
    redact: bool = True
    max_chars: int = 12000
```

**Migration strategy:** N/A - new optional public configuration object.

### 7.4 Debug Trace Events

**Change type:** Modified

```python
{
    "type": "start_trace" | "end_trace" | "start_span" | "end_span",
    "name": str | None,
    "attributes": dict[str, Any],
    "context": SpanContext,
    "parent": SpanContext | None,
    "output": str | None,
    "error": str | None,
}
```

**Migration strategy:** Keep existing keys stable. Semantic controller may add semantic attributes inside `attributes`, but no existing event keys are removed.

---

## 8. API Changes

### 8.1 Python API: `TraceProfile`

**Change type:** New

**Request:**

```python
from vidbyte import TraceProfile

profile = TraceProfile.verbose().with_components(middleware="decisions_only")
```

**Response:**

```python
profile.allows(span_spec)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Unknown component or value raises `ConfigurationError` |

### 8.2 Python API: `Trace.profile`

**Change type:** New

**Request:**

```python
trace = Trace.profile(inner=Trace.debug([]), profile=TraceProfile.default())
```

**Response:**

```python
agent = Agent(..., trace=trace)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | `inner=None` raises `ConfigurationError` |
| N/A | Unknown provider name raises `ConfigurationError` |

### 8.3 Python API: LangSmith Semantic Helpers

**Change type:** New

**Request:**

```python
trace = Trace.langsmith_default(api_key="...", project="sdk")
trace = Trace.langsmith_verbose(api_key="...", project="sdk")
trace = Trace.langsmith_session(api_key="...", project="sdk", name="job-run")
```

**Response:**

```python
agent = Agent(..., trace=trace)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing LangSmith package or credentials still raises existing `TracerConfigurationError` |

### 8.4 Python API: Session Tracing

**Change type:** New

**Request:**

```python
trace = Trace.session(Trace.debug([]), profile=TraceProfile.verbose())

with trace.session("workflow"):
    await agent_a.arun("...")
    await agent_b.arun("...")
```

**Response:**

```python
# all child agent runs appear under one session root
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Beginning nested sessions on one controller raises `ConfigurationError` |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/semantic-trace-profiles.md` | Design doc for semantic trace profiles |
| CREATE | `vidbyte/trace/schema.py` | Semantic span types, kinds, details, and contexts |
| CREATE | `vidbyte/trace/profiles.py` | TraceProfile presets and component settings |
| CREATE | `vidbyte/trace/controller.py` | TraceController implementing composable semantic tracing |
| CREATE | `vidbyte/trace/session.py` | SessionTraceController for multi-agent root grouping |
| CREATE | `vidbyte/trace/registry.py` | Built-in component registry and validation |
| CREATE | `vidbyte/trace/providers/__init__.py` | Provider translator package exports |
| CREATE | `vidbyte/trace/providers/base.py` | ProviderTraceTranslator protocol and payload type |
| CREATE | `vidbyte/trace/providers/generic.py` | Generic provider translator |
| CREATE | `vidbyte/trace/providers/langsmith.py` | LangSmith semantic-to-run-type translator |
| CREATE | `vidbyte/trace/components/__init__.py` | Component tracing package exports |
| CREATE | `vidbyte/trace/components/agents.py` | Agent and aggregate trace span specs |
| CREATE | `vidbyte/trace/components/runtimes.py` | Linear, actor, and search runtime trace span specs |
| CREATE | `vidbyte/trace/components/context.py` | Context-window and primitive trace span specs |
| CREATE | `vidbyte/trace/components/algorithms.py` | Context-window algorithm trace span specs |
| CREATE | `vidbyte/trace/components/middleware.py` | Middleware decision trace span specs |
| CREATE | `vidbyte/trace/components/tools.py` | Tool call and permission trace span specs |
| CREATE | `vidbyte/trace/components/parsers.py` | Tool-call and structured-output parser span specs |
| CREATE | `tests/test_semantic_tracing.py` | Unit and integration tests for semantic tracing |
| CREATE | `scripts/test-semantic-trace-profiles.py` | Required verification script |
| MODIFY | `vidbyte/trace/base.py` | Add profile/session/LangSmith semantic facade helpers |
| MODIFY | `vidbyte/trace/__init__.py` | Export TraceProfile, TraceController, and session/controller types |
| MODIFY | `vidbyte/trace/debug.py` | Ensure debug tracer preserves semantic attributes and BaseException errors |
| MODIFY | `vidbyte/lib/tracing/base.py` | Keep contract compatible and update comments/types if needed for semantic contexts |
| MODIFY | `vidbyte/providers/tracing/langsmith.py` | Ensure explicit run_type and trace_id support for semantic translation |
| MODIFY | `vidbyte/providers/tracing/langfuse.py` | Preserve semantic attributes safely in provider metadata |
| MODIFY | `vidbyte/providers/tracing/phoenix.py` | Preserve semantic attributes safely in OTel attributes |
| MODIFY | `vidbyte/agents/base.py` | Emit semantic agent metadata and propagate tracer into aggregate agents |
| MODIFY | `vidbyte/agents/runtime.py` | Add linear runtime, context, parser, tool input/output, middleware, and stop tracing |
| MODIFY | `vidbyte/agents/aggregation.py` | Add aggregate spans and propagate tracer to SDK-built children |
| MODIFY | `vidbyte/agents/runtimes/search.py` | Add search runtime semantic spans |
| MODIFY | `vidbyte/agents/runtimes/actor/broker.py` | Add actor runtime semantic spans |
| MODIFY | `vidbyte/__init__.py` | Root exports for semantic trace APIs |
| MODIFY | `README.md` | Document semantic profiles and session tracing |
| MODIFY | `vidbyte/trace/README.md` | Document semantic tracing package and span taxonomy |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update package layout and tracing guardrails |
| MODIFY | `skills/sdk/SKILL.md` | Update package layout and tracing guardrails |
| MODIFY | `tests/test_tracing.py` | Preserve existing behavior and add compatibility assertions |
| MODIFY | `tests/test_trace_facade.py` | Add facade coverage for new helpers |
| MODIFY | `tests/test_aggregate_agent.py` | Add tracer propagation coverage for aggregate agents |

Summary: 20 files to create, 20 files to modify, 0 files to delete.

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] `TraceProfile.minimal` -> allows `agent.run`, `llm.call`, and `tool.call`.
- [Silent Failure] `TraceProfile.minimal` -> suppresses `runtime.iteration`, `context.window.build`, `middleware.decision`, and `aggregate.run`.
- [Edge Case] `TraceProfile.default` -> allows parser, retriever, embedding, tool inputs, and agent stop spans.
- [Silent Failure] `TraceProfile.verbose` -> allows algorithm, aggregate, context summary, and non-continue middleware decision spans.
- [Hidden Assumption] `TraceProfile.diagnostic` -> allows all registered component spans.
- [Edge Case] `TraceProfile.with_components` -> rejects unknown component names.
- [Hidden Assumption] `TraceProfile.with_components` -> rejects unknown component setting values.
- [Edge Case] `TraceProfile` -> rejects zero and negative max_chars.
- [Silent Failure] `SpanSpec` -> stores immutable copied attributes and preserves component/kind/detail.
- [Hidden Failure] `TraceComponentRegistry` -> rejects duplicate component registrations.
- [Hidden Assumption] `TraceComponentRegistry` -> rejects unknown component default lookups.
- [Edge Case] `GenericProviderTranslator` -> preserves span name and attributes.
- [Silent Failure] `LangSmithProviderTranslator` -> maps every `SpanKind` to the expected LangSmith `run_type`.
- [Hidden Failure] `LangSmithProviderTranslator` -> does not mutate caller-owned attributes.
- [Edge Case] `Trace.profile` -> rejects `inner=None`.
- [Hidden Assumption] `Trace.profile` -> accepts a custom translator instance.
- [Silent Failure] `Trace.profile` -> wraps a `DebugTracer` and preserves debug event ordering.
- [Edge Case] `Trace.langsmith_default` -> forwards api_key/project/endpoint/strict/include_runtime_info to `LangSmithTracer`.
- [Silent Failure] `Trace.langsmith_default` -> wraps LangSmith tracer with `LangSmithProviderTranslator`.
- [Edge Case] `Trace.langsmith_verbose` -> uses verbose profile by default.
- [Edge Case] `Trace.session` -> creates a `SessionTraceController`.
- [Hidden Failure] `SessionTraceController` -> rejects nested active sessions.
- [Silent Failure] `SessionTraceController` -> maps child `agent.run` trace starts to child spans during an active session.
- [Hidden Failure] `SessionTraceController` -> closes the session root with error when a context block raises.
- [Edge Case] `TraceController` -> returns suppressed contexts for disallowed spans and ending them is safe.
- [Silent Failure] `TraceController` -> explicit parent beats active parent stack.
- [Hidden Failure] `TraceController` -> contextvars isolate concurrent async parent stacks.
- [Hidden Assumption] `TraceController` -> raw `TracerBase` provider contexts are preserved inside semantic contexts.
- [Silent Failure] `AgentTrace` -> builds `agent.run` as chain/minimal and `agent.stop` as chain/default.
- [Silent Failure] `AggregateTrace` -> builds aggregate run/proposer/synthesis specs with aggregate component.
- [Silent Failure] `LinearRuntimeTrace` -> builds iteration and stop specs with runtime component.
- [Silent Failure] `ActorRuntimeTrace` -> builds run/spawn/message/completion specs with actor component.
- [Silent Failure] `SearchRuntimeTrace` -> builds run/node/rollback specs with search component.
- [Silent Failure] `ContextTrace` -> builds `context.window.build` with prompt kind.
- [Silent Failure] `AlgorithmTrace` -> builds each named algorithm spec with stable names.
- [Silent Failure] `MiddlewareTrace` -> suppresses continue decisions below diagnostic mode.
- [Hidden Failure] `MiddlewareTrace` -> includes retry/abort/deny-tool decisions in verbose mode.
- [Edge Case] `ToolTrace` -> preserves empty argument dicts as `{}`.
- [Hidden Failure] `ToolTrace` -> includes call id, metadata, state, and output/error when configured.
- [Silent Failure] `ParserTrace` -> records zero tool-call count without pretending a parse failure occurred.
- [Hidden Assumption] `ParserTrace` -> structured-output errors are captured as parser errors without changing result behavior.
- [Hidden Failure] `DebugTracer` -> accepts BaseException errors after semantic controller wrapping.

### Integration Tests

- [Hidden Failure] Run `BaseAgent` with `Trace.profile(Trace.debug(events), TraceProfile.minimal())`; assert only current core spans appear.
- [Silent Failure] Run `BaseAgent` with `Trace.profile(Trace.debug(events), TraceProfile.verbose())`; assert `runtime.iteration`, `context.window.build`, `llm.call`, `tool.call`, and `agent.stop` appear in parent order.
- [Hidden Failure] Run a tool-using fake agent and assert `tool.call` attributes include `tool_input`, `tool_name`, and output.
- [Edge Case] Run a no-tool fake agent and assert no `tool.call` is emitted.
- [Hidden Failure] Run with a tool that raises and assert `tool.call` closes with error.
- [Silent Failure] Run with output schema and valid JSON; assert `parser.structured_output` closes successfully.
- [Hidden Failure] Run with output schema and invalid JSON; assert `parser.structured_output` closes with validation error while current result semantics are preserved.
- [Silent Failure] Run with middleware returning continue only; assert no verbose middleware span when profile is `default`.
- [Hidden Failure] Run with middleware returning retry/abort/deny-tool; assert verbose middleware decision spans appear.
- [Hidden Assumption] Run with `Trace.debug` raw, not profiled; assert existing tests and behavior remain unchanged.
- [Hidden Failure] Run `AggregateAgent` with SDK-built proposer/aggregator and semantic tracing; assert aggregate and child agent spans appear.
- [Edge Case] Run `AggregateAgent` with fake external agent-like proposers; assert fake objects are not mutated and aggregate result is unchanged.
- [Hidden Failure] Run aggregate with one failing proposer; assert proposer span closes with error and survivor synthesis still succeeds.
- [Silent Failure] Run `BaseAgent` native multi-model overload and assert tracer is propagated into the internal aggregate agent.
- [Hidden Failure] Run `SessionTraceController` around two agents; assert one `session.run` root with two `agent.run` children.
- [Hidden Failure] Run two async sessions in separate tasks; assert parent stacks do not cross.
- [Hidden Failure] Run `ContextWindow.preset.reflexion` with semantic tracing; assert reflexion trial/reflection metadata appears.
- [Silent Failure] Run an inner-loop algorithm such as trajectory checkpoints with verbose profile; assert algorithm span appears and existing result metadata still appears.
- [Hidden Failure] Run `SearchTreeRuntimeComponent` with semantic tracing; assert search run span closes with total node metadata.
- [Hidden Failure] Run actor runtime with semantic tracing and a tiny fake completion path; assert actor run closes even when tasks are cancelled.
- [Hidden Failure] Run `python -m unittest tests.test_semantic_tracing tests.test_tracing tests.test_trace_facade tests.test_aggregate_agent`.

### Manual / QA Test Cases

1. [Edge Case] Given `trace=Trace.langsmith_default(project="sdk")`, when a simple agent runs, then LangSmith shows `agent.run`, `llm.call`, and `tool.call` with native chain/llm/tool rendering.
2. [Silent Failure] Given `trace=Trace.langsmith_verbose(project="sdk")`, when a tool-using agent runs, then LangSmith shows runtime/context/parser spans without duplicate LLM or tool spans.
3. [Hidden Failure] Given `Trace.langsmith_session(name="workflow")`, when multiple agents run inside the session context, then one LangSmith root contains all child agent runs.
4. [Hidden Assumption] Given a raw custom tracer passed through `trace=`, when an agent runs, then the tracer still receives the existing low-level start/end calls.
5. [Hidden Failure] Given an aggregate agent with one failing proposer, when tracing is verbose, then the failed proposer is visible but the aggregate behavior remains unchanged.
6. [Silent Failure] Given a profile with `middleware="off"`, when middleware aborts, then the run behavior is unchanged and no middleware span appears.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `langsmith` optional package | Existing optional adapter behavior | Used by raw and semantic LangSmith helpers | Client API differences may affect run_type or trace_id behavior |
| Existing `langfuse` optional package | Existing optional adapter behavior | Raw provider adapter; semantic attributes pass through metadata | Provider may ignore unknown semantic metadata |
| Existing Phoenix/OpenTelemetry optional packages | Existing optional adapter behavior | Raw provider adapter; semantic attributes pass through OTel attributes | Attribute value coercion may be lossy |
| Python `contextvars` | Standard library | Async-safe span stack tracking | Misuse could still leak parents if not tested |

No new mandatory dependency is added to `pyproject.toml`.

---

## 12. Rollout & Deployment

- No feature flag is required.
- This is additive and backward compatible.
- Existing `Trace.langsmith(...)` remains a raw provider adapter helper.
- New users can opt into semantic defaults with `Trace.langsmith_default(...)`.
- Multi-agent users can opt into session grouping with `Trace.session(...)` or `Trace.langsmith_session(...)`.
- Deployment is a normal SDK package release.
- Rollback procedure: remove new `vidbyte/trace/schema.py`, `profiles.py`, `controller.py`, `session.py`, `registry.py`, `providers/`, `components/`, facade helpers, runtime instrumentation additions, tests, docs, and script. Existing raw `TracerBase` behavior remains the fallback.

---

## 13. Open Questions

- [ ] Should the package also expose a compatibility alias `vidbyte.tracing` later, or should the SDK keep only `vidbyte.trace`?
- [ ] Should `Trace.langfuse_default` and `Trace.phoenix_default` be added in this PR, or should this PR provide `Trace.profile(Trace.langfuse(...), provider="generic")` and focus first on LangSmith defaults?
- [ ] Should diagnostic context payloads include full prompt text by default, or should full prompt text require an explicit `include_context="full"` setting even in diagnostic mode?
- [ ] Should middleware all-hook tracing live in `MiddlewarePipeline` or remain triggered from runtime call sites around each hook result?
- [ ] Should retriever and embedding spans be fully wired in this PR, or should this PR only define the semantic categories and leave specific code-search/embedding runner instrumentation for follow-up?

---

## 14. Alternatives Considered

### Alternative 1: Rename `vidbyte.trace` To `vidbyte.tracing`

- What: Create a new `vidbyte.tracing` package matching the user's proposed name.
- Why rejected: The repo already exposes `vidbyte.trace` publicly and documents it in README and skills. Renaming would be breaking and would duplicate the current package.

### Alternative 2: Put Component Tracing Under Each Component Package

- What: Put tracing files directly in `vidbyte/agents/tracing.py`, `vidbyte/context/tracing.py`, and `vidbyte/middleware/tracing.py`.
- Why rejected: This scatters prebuilt trace configuration and makes composition harder. A central `vidbyte.trace.components` package keeps the tracing ontology coherent while runtime code only imports small helpers.

### Alternative 3: Replace `TracerBase` With Semantic Events

- What: Remove `start_trace` and `start_span` and migrate everything to event objects.
- Why rejected: Existing provider adapters, tests, and user custom tracers already implement `TracerBase`. A controller that implements `TracerBase` gives semantic tracing without breaking the existing protocol.

### Alternative 4: Make LangSmith The Canonical Trace Model

- What: Model all SDK tracing around LangSmith run types and fields.
- Why rejected: LangSmith is important, but the SDK also supports Langfuse, Phoenix, debug tracing, custom tracers, and future providers. Vidbyte semantic spans should be provider-neutral, with LangSmith as one translator.

### Alternative 5: Let Every Component Open Provider Spans Directly

- What: Each runtime, middleware, and algorithm calls provider-specific APIs.
- Why rejected: This would couple SDK primitives to external provider semantics, make multi-component composition brittle, and make custom tracers much harder to support.

### Alternative 6: Add Only SessionTracer And Stop There

- What: Productize the harness `SessionTracer` as the only new feature.
- Why rejected: Session tracing solves multi-agent grouping but not the broader need for prebuilt component traces, runtime/algorithm visibility, provider translation, or multiple prebuilts in one trace.
