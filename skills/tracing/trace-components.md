<!--
Context Protocol Header

Description:
    Skill cataloguing the semantic span-spec factories in vidbyte/trace/components.
Purpose:
    Lists every Vidbyte-owned span spec by component file, documents SpanSpec
    fields, the TraceComponentRegistry, and the maintenance rule for keeping
    components in sync with runtime/algorithm/middleware/tool/parser changes.
Architecture:
    - Covers vidbyte/trace/components/{agents,runtimes,context,algorithms,
      middleware,tools,parsers}.py and __init__.py.
    - References vidbyte/trace/schema.py (SpanSpec) and registry.py.
Relations:
    Sub-skill of skills/tracing/SKILL.md. Pairs with trace-profiles.md
    (component names + allows() filtering) and trace-controller-and-session.md
    (_spec_from_name name-prefix routing).
-->

# Trace Components

`vidbyte/trace/components/` holds the Vidbyte-owned **span-spec factories**.
Each factory builds a `SpanSpec` — the provider-neutral description of one
semantic span. These are the canonical declarations of what the SDK traces; the
runtime emits spans by name and the `TraceController` routes those names to specs
(see `trace-controller-and-session.md`).

## What a Span Spec Is

`SpanSpec` (`vidbyte/trace/schema.py`) is an immutable dataclass:

```python
@dataclass(frozen=True, slots=True)
class SpanSpec:
    name: str
    kind: SpanKind = SpanKind.CHAIN
    component: str = "core"
    detail: TraceDetail = TraceDetail.MINIMAL
    parent_policy: ParentPolicy = ParentPolicy.CURRENT
    attributes: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def with_attributes(self, **attributes: Any) -> SpanSpec:
        # Returns a copy with merged semantic attributes.
        ...
```

- `name` — the span name (e.g. `agent.run`, `llm.call`).
- `kind` — the `SpanKind` (chain/llm/tool/retriever/embedding/prompt/parser).
- `component` — the component group used by `TraceProfile.allows()` (see
  `trace-profiles.md`).
- `detail` — the minimum `TraceDetail` the span requires.
- `parent_policy` — how the controller resolves the parent (see
  `trace-controller-and-session.md`).
- `attributes` / `metadata` — payload carried with the span.

## Component Factory Catalog

### `agents.py` — `AgentTrace`, `AggregateTrace`

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `AgentTrace.run()` | `agent.run` | chain | `agents` | MINIMAL |
| `AgentTrace.stop()` | `agent.stop` | chain | `agents` | STANDARD |
| `AgentTrace.loop_settings_resolved()` | `agent.loop_settings.resolved` | chain | `agents` | STANDARD |
| `AgentTrace.loop_settings_enforced()` | `agent.loop_settings.enforced` | chain | `agents` | STANDARD |
| `AgentTrace.output_contract_enforced()` | `agent.output_contract.enforced` | chain | `agents` | VERBOSE |
| `AgentTrace.output_contract_violation()` | `agent.output_contract.violation` | chain | `agents` | STANDARD |
| `AgentTrace.handoff_requested()` | `agent.handoff.requested` | chain | `agents` | VERBOSE |
| `AgentTrace.handoff_generated()` | `agent.handoff.generated` | chain | `agents` | VERBOSE |
| `AgentTrace.handoff_failed()` | `agent.handoff.failed` | chain | `agents` | STANDARD |
| `AgentTrace.modality_resolved()` | `agent.modality.resolved` | chain | `agents` | VERBOSE |
| `AgentTrace.aggregate_plan_resolved()` | `agent.aggregate.plan_resolved` | chain | `agents` | VERBOSE |
| `AgentTrace.algorithm_resolved()` | `agent.algorithm.resolved` | chain | `agents` | VERBOSE |
| `AgentTrace.mcp_attached()` | `agent.mcp.attached` | chain | `agents` | VERBOSE |
| `AgentTrace.runner_created()` | `agent.runner.created` | chain | `agents` | DIAGNOSTIC |
| `AggregateTrace.run()` | `aggregate.run` | chain | `aggregate` | VERBOSE |
| `AggregateTrace.proposer()` | `aggregate.proposer` | chain | `aggregate` | VERBOSE |
| `AggregateTrace.synthesis()` | `aggregate.synthesis` | chain | `aggregate` | VERBOSE |
| `AggregateTrace.failure()` | `aggregate.failure` | chain | `aggregate` | VERBOSE |

The agent-level spans beyond `run`/`stop` use `ParentPolicy.AGENT` and capture
lifecycle events resolved by `BaseAgent` (loop settings, output schema
enforcement, auto-handoff, modality detection, algorithm selection, MCP
attachment, runner construction).

### `runtimes.py` — `LinearRuntimeTrace`, `ActorRuntimeTrace`, `SearchRuntimeTrace`

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `LinearRuntimeTrace.iteration()` | `runtime.iteration` | chain | `runtimes` | VERBOSE |
| `LinearRuntimeTrace.stop()` | `runtime.stop` | chain | `runtimes` | VERBOSE |
| `LinearRuntimeTrace.model_call()` | `runtime.linear.model_call` | llm | `runtimes` | STANDARD |
| `LinearRuntimeTrace.tool_batch()` | `runtime.linear.tool_batch` | tool | `runtimes` | VERBOSE |
| `LinearRuntimeTrace.stop_condition()` | `runtime.linear.stop_condition` | chain | `runtimes` | STANDARD |
| `ActorRuntimeTrace.run()` | `runtime.actor.run` | chain | `actor` | VERBOSE |
| `ActorRuntimeTrace.spawn()` | `runtime.actor.spawn` | chain | `actor` | VERBOSE |
| `ActorRuntimeTrace.message()` | `runtime.actor.message` | chain | `actor` | VERBOSE |
| `ActorRuntimeTrace.completion()` | `runtime.actor.completion` | chain | `actor` | VERBOSE |
| `ActorRuntimeTrace.quiescence()` | `runtime.actor.quiescence` | chain | `actor` | VERBOSE |
| `ActorRuntimeTrace.compile_prompt()` | `runtime.actor.compile_prompt` | chain | `actor` | DIAGNOSTIC |
| `SearchRuntimeTrace.run()` | `runtime.search.run` | chain | `search` | VERBOSE |
| `SearchRuntimeTrace.node()` | `runtime.search.node` | chain | `search` | VERBOSE |
| `SearchRuntimeTrace.rollback()` | `runtime.search.rollback` | chain | `search` | VERBOSE |
| `SearchRuntimeTrace.expand()` | `runtime.search.expand` | chain | `search` | VERBOSE |
| `SearchRuntimeTrace.evaluate()` | `runtime.search.evaluate` | chain | `search` | VERBOSE |
| `SearchRuntimeTrace.select()` | `runtime.search.select` | chain | `search` | VERBOSE |

### `context.py` — `ContextTrace`

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `ContextTrace.window_build()` | `context.window.build` | prompt | `context` | VERBOSE |
| `ContextTrace.primitive_render()` | `context.primitive.render` | prompt | `context` | VERBOSE |
| `ContextTrace.compaction()` | `context.compaction` | chain | `context` | VERBOSE |
| `ContextTrace.update()` | `context.update` | chain | `context` | VERBOSE |
| `ContextTrace.manager_upsert()` | `context.manager.upsert` | chain | `context` | VERBOSE |
| `ContextTrace.manager_extend()` | `context.manager.extend` | chain | `context` | VERBOSE |
| `ContextTrace.primitive_add()` | `context.primitive.add` | chain | `context` | DIAGNOSTIC |
| `ContextTrace.primitive_remove()` | `context.primitive.remove` | chain | `context` | DIAGNOSTIC |
| `ContextTrace.compaction_trigger()` | `context.compaction.trigger` | chain | `context` | VERBOSE |
| `ContextTrace.compaction_strategy()` | `context.compaction.strategy` | chain | `context` | VERBOSE |
| `ContextTrace.template_record()` | `context.template.record` | chain | `context` | DIAGNOSTIC |
| `ContextTrace.handoff_sync()` | `context.handoff.sync` | chain | `context` | VERBOSE |

### `algorithms.py` — `AlgorithmTrace`

`AlgorithmTrace.named(name)` builds `algorithm.<safe-name>` (underscores →
hyphens) as a chain, component `algorithms`, detail VERBOSE. Prebuilt aliases:

| Factory method | Span name |
|----------------|-----------|
| `AlgorithmTrace.reflexion_trial()` | `algorithm.reflexion.trial` |
| `AlgorithmTrace.reflexion_reflection()` | `algorithm.reflexion.reflection` |
| `AlgorithmTrace.multi_provider_grader()` | `algorithm.multi-provider-agentic-grader` |
| `AlgorithmTrace.trajectory_checkpoint()` | `algorithm.trajectory-checkpoints` |
| `AlgorithmTrace.problem_space_search()` | `algorithm.problem-space-search` |
| `AlgorithmTrace.error_correction()` | `algorithm.error-correction` |

All are kind `chain`, component `algorithms`, detail `VERBOSE`.

### `middleware.py` — `MiddlewareTrace`

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `MiddlewareTrace.decision()` | `middleware.decision` | chain | `middleware` | VERBOSE |
| `MiddlewareTrace.hook()` | `middleware.hook` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.before_run_ran()` | `middleware.before_run.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.before_iteration_ran()` | `middleware.before_iteration.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.before_model_call_ran()` | `middleware.before_model_call.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.after_model_response_ran()` | `middleware.after_model_response.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.on_model_error_ran()` | `middleware.on_model_error.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.before_tool_call_ran()` | `middleware.before_tool_call.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.after_tool_call_ran()` | `middleware.after_tool_call.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.after_iteration_ran()` | `middleware.after_iteration.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.after_run_ran()` | `middleware.after_run.ran` | chain | `middleware` | DIAGNOSTIC |
| `MiddlewareTrace.action_sleep()` | `middleware.action.sleep` | chain | `middleware` | VERBOSE |
| `MiddlewareTrace.action_abort_run()` | `middleware.action.abort_run` | chain | `middleware` | STANDARD |
| `MiddlewareTrace.action_deny_tool()` | `middleware.action.deny_tool` | chain | `middleware` | STANDARD |
| `MiddlewareTrace.action_retry()` | `middleware.action.retry` | chain | `middleware` | VERBOSE |
| `MiddlewareTrace.exception()` | `middleware.exception` | chain | `middleware` | STANDARD |
| `MiddlewareTrace.transform_applied()` | `middleware.transform.applied` | chain | `middleware` | VERBOSE |
| `MiddlewareTrace.builtin(name)` | `middleware.builtin.<name>` | chain | `middleware` | DIAGNOSTIC |

`middleware.decision` is the span surfaced by the `decisions_only` component
setting (see `trace-profiles.md`). The per-hook `*.ran` spans and
`middleware.builtin.<name>` are DIAGNOSTIC, so they only appear under
`TraceProfile.diagnostic()` or when the `middleware` component is set to
`"diagnostic"`. `MiddlewareTrace.builtin(name)` sanitizes the name
(underscores → hyphens).

### `tools.py` — `ToolTrace`

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `ToolTrace.call()` | `tool.call` | tool | `tools` | MINIMAL |
| `ToolTrace.permission()` | `tool.permission` | tool | `tools` | STANDARD |
| `ToolTrace.resolve()` | `tool.resolve` | tool | `tools` | VERBOSE |
| `ToolTrace.validate()` | `tool.validate` | tool | `tools` | VERBOSE |
| `ToolTrace.deny()` | `tool.deny` | tool | `tools` | STANDARD |
| `ToolTrace.error()` | `tool.error` | tool | `tools` | STANDARD |
| `ToolTrace.compact()` | `tool.compact` | tool | `tools` | VERBOSE |
| `ToolTrace.parallel_batch()` | `tool.parallel_batch` | tool | `tools` | VERBOSE |
| `ToolTrace.mcp_invoke()` | `tool.mcp.invoke` | tool | `tools` | VERBOSE |
| `ToolTrace.mcp_attach()` | `tool.mcp.attach` | tool | `tools` | VERBOSE |

### `parsers.py` — `ParserTrace`

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `ParserTrace.tool_calls()` | `parser.tool_calls` | parser | `parsers` | STANDARD |
| `ParserTrace.structured_output()` | `parser.structured_output` | parser | `parsers` | STANDARD |
| `ParserTrace.is_done()` | `parser.is_done` | parser | `parsers` | VERBOSE |
| `ParserTrace.response_format_built()` | `parser.response_format_built` | parser | `parsers` | DIAGNOSTIC |

### `pipelines.py` — `PipelineTrace` (NEW)

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `PipelineTrace.sequential_run()` | `pipeline.sequential.run` | chain | `pipelines` | STANDARD |
| `PipelineTrace.parallel_run()` | `pipeline.parallel.run` | chain | `pipelines` | STANDARD |
| `PipelineTrace.conditional_run()` | `pipeline.conditional.run` | chain | `pipelines` | STANDARD |
| `PipelineTrace.map_reduce_run()` | `pipeline.map_reduce.run` | chain | `pipelines` | STANDARD |
| `PipelineTrace.stage_invoke()` | `pipeline.stage.invoke` | chain | `pipelines` | VERBOSE |

The four topology runs use `ParentPolicy.ROOT` (a pipeline is its own root);
`stage_invoke` uses `ParentPolicy.CURRENT`.

### `handoff.py` — `HandoffTrace` (NEW)

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `HandoffTrace.generate()` | `handoff.generate` | chain | `handoff` | VERBOSE |
| `HandoffTrace.validate()` | `handoff.validate` | chain | `handoff` | VERBOSE |
| `HandoffTrace.record()` | `handoff.record` | chain | `handoff` | STANDARD |
| `HandoffTrace.sync()` | `handoff.sync` | chain | `handoff` | VERBOSE |

All use `ParentPolicy.AGENT` — handoff spans attach to the active agent root.

### `sources.py` — `SourceTrace` (NEW)

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `SourceTrace.fetch()` | `source.fetch` | retriever | `sources` | STANDARD |
| `SourceTrace.load()` | `source.load` | retriever | `sources` | STANDARD |
| `SourceTrace.cache_hit()` | `source.cache.hit` | chain | `sources` | VERBOSE |
| `SourceTrace.cache_miss()` | `source.cache.miss` | chain | `sources` | VERBOSE |

`fetch`/`load` are the first component spans to use `SpanKind.RETRIEVER`.

### `sessions.py` — `SessionTrace` (NEW)

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `SessionTrace.start()` | `session.start` | chain | `sessions` | STANDARD |
| `SessionTrace.end()` | `session.end` | chain | `sessions` | STANDARD |
| `SessionTrace.case()` | `session.case` | chain | `sessions` | VERBOSE |

`start`/`end` use `ParentPolicy.ROOT`; `case` uses `ParentPolicy.SESSION`.

### `evals.py` — `EvalTrace` (NEW)

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `EvalTrace.run()` | `eval.run` | chain | `evals` | STANDARD |
| `EvalTrace.grade()` | `eval.grade` | chain | `evals` | STANDARD |
| `EvalTrace.behavior()` | `eval.behavior` | chain | `evals` | VERBOSE |

`eval.run` uses `ParentPolicy.ROOT` (an eval harness is its own root).

### `mcp.py` — `McpTrace` (NEW)

| Factory method | Span name | Kind | Component | Detail |
|----------------|-----------|------|-----------|--------|
| `McpTrace.attach()` | `mcp.attach` | chain | `mcp` | STANDARD |
| `McpTrace.search()` | `mcp.search` | chain | `mcp` | VERBOSE |
| `McpTrace.transport()` | `mcp.transport` | chain | `mcp` | VERBOSE |

`mcp.attach` uses `ParentPolicy.AGENT`; `search`/`transport` use
`ParentPolicy.CURRENT`.

All 16 factories are re-exported from `vidbyte/trace/components/__init__.py`:
`AgentTrace`, `AggregateTrace`, `AlgorithmTrace`, `ContextTrace`, `EvalTrace`,
`HandoffTrace`, `LinearRuntimeTrace`, `ActorRuntimeTrace`, `SearchRuntimeTrace`,
`McpTrace`, `MiddlewareTrace`, `ParserTrace`, `PipelineTrace`, `SessionTrace`,
`SourceTrace`, `ToolTrace`.

## How Spans Actually Get Emitted

The factories are the **canonical declarations** (used by tests, docs, and the
registry). The runtime itself emits spans **by name** through two paths:

- **Direct** (`self._tracer.start_span(name, parent=trace_context, ...)`) —
  always emitted regardless of tracer type: `runtime.iteration`, `llm.call`,
  `tool.call`, and `parser.tool_calls` (via `_record_parser_span`).
- **Semantic-only** (`self._start_semantic_span(name, ...)`) — emitted only when
  `_is_semantic_tracer(self._tracer)` is true (i.e. the tracer is a
  `TraceController`); suppressed for raw provider tracers:
  `parser.structured_output`, `context.window.build`, `middleware.decision`,
  `algorithm.<name>`.
- `BaseAgent._record_agent_stop()` emits `agent.stop` for semantic tracers.
- `BaseAgent.arun()` opens the root `start_trace("agent.run", ...)`.

The `TraceController._spec_from_name` then routes each name by prefix
(`agent.`, `llm.`, `tool.`, `parser.`, `context.`, `algorithm.`, `runtime.`,
`middleware.`, `aggregate.`, `session.`) to a component, kind, and detail —
matching the declarations above. When you add a new span, add the factory here
**and** ensure the controller's name-prefix routing covers it (see
`updating-the-tracer.md`).

## `TraceComponentRegistry`

`vidbyte/trace/registry.py` defines a small registry for tests and docs:

```python
@dataclass(slots=True)
class TraceComponentRegistry:
    _specs: dict[str, SpanSpec] = field(default_factory=dict)

    def register(self, spec: SpanSpec) -> None:
        # Rejects duplicate names with ConfigurationError.
        ...
    def get(self, name: str) -> SpanSpec:
        # Returns the spec or raises ConfigurationError for unknown names.
        ...
    def all(self) -> tuple[SpanSpec, ...]:
        # Returns all registered specs in insertion order.
        ...
```

Use it to look up or enumerate the canonical span specs when you need to assert
on the full set in tests or documentation generation.

## Maintenance Rule

> When adding or changing an agent runtime, context-window algorithm, middleware
> class, tool surface, parser, or aggregate-agent behavior, check whether
> `vidbyte/trace/components/` needs a new or updated span spec **in the same
> change**.

Concretely:

- **New runtime** (e.g. a new non-linear runtime) → add a factory class in
  `runtimes.py` with span specs for its phases; ensure `_spec_from_name` in
  `controller.py` routes the new name prefix.
- **New context-window algorithm** → add an `AlgorithmTrace.<alias>()` method (or
  use `AlgorithmTrace.named("<name>")`) so the algorithm phase is traceable.
- **New middleware** → if it makes a runtime control-flow decision, it should be
  visible as a `middleware.decision` span; add a `middleware.hook` spec only for
  diagnostic instrumentation.
- **New tool surface** → no new spec needed unless you introduce a new tool
  lifecycle phase beyond `tool.call`/`tool.permission`.
- **New parser / structured-output path** → add a `ParserTrace` method if it is
  not covered by `parser.tool_calls`/`parser.structured_output`.
- **New aggregate-agent phase** → add an `AggregateTrace` method.

Also update `vidbyte/trace/README.md` or `llms.txt` when public tracing behavior
changes, and update `skills/sdk/SKILL.md` and `skills/vidbyte-sdk/SKILL.md`
"Semantic Trace Components" section when the component file list changes.
