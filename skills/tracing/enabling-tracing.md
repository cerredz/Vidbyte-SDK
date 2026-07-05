<!--
Context Protocol Header

Description:
    Skill for enabling observability tracing on Vidbyte SDK agents.
Purpose:
    Shows the trace= argument, the full Trace facade helper catalog, the
    trace= vs tracer= vs trace_option= distinction, the agent.run root trace
    lifecycle, and the spans the runtime emits.
Architecture:
    - Documents BaseAgent trace wiring (vidbyte/agents/base.py).
    - Documents runtime span emission (vidbyte/agents/runtime.py).
    - Documents the Trace facade (vidbyte/trace/base.py).
Relations:
    Sub-skill of skills/tracing/SKILL.md. Pairs with trace-types.md,
    trace-profiles.md, and trace-providers.md. Continual tracing
    (trace_option=) is summarized here and detailed in
    skills/vidbyte-sdk/continual-tracing.md.
-->

# Enabling Tracing on Agents

Tracing is **opt-in and explicit**. You pass a tracer to an agent and the
runtime opens spans around its work. Nothing is traced by default — when no
tracer is supplied the agent uses `NullTracer`, which is zero-overhead.

## The `trace=` Argument

`BaseAgent` (and the public `Agent` subclass) accepts two alias arguments:

```python
agent = Agent(
    name="observed",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    trace=Trace.langsmith_default(project="vidbyte-agents"),
)
```

- `trace=` — the public alias. Pass a `TracerBase` instance or class.
- `tracer=` — the legacy alias. Same semantics.
- You may pass **either, not both**. Passing both raises `ConfigurationError`.

Normalization lives in `BaseAgent._resolve_tracer(tracer, trace)` in
`vidbyte/agents/base.py`: it picks the non-`None` one, instantiates it if you
passed a class, validates it is a `TracerBase`, and falls back to `NullTracer()`
when neither is given.

## `trace=` vs `tracer=` vs `trace_option=`

| Argument | System | What it does |
|----------|--------|--------------|
| `trace=` | Observability | Selects the tracer that records span trees (debug, LangSmith, Langfuse, Phoenix, semantic profile, session). |
| `tracer=` | Observability | Legacy alias for `trace=`. Pass either, not both. |
| `trace_option=` | Continual | Selects a structured-artifact trace (`TraceOption.continual(schema)`) updated by middleware. **Separate subsystem** — see `skills/vidbyte-sdk/continual-tracing.md`. |

A single agent may use `trace=` for observability **and** `trace_option=` for a
continual artifact at the same time; they do not interfere.

## The `Trace` Facade Catalog

`Trace` (in `vidbyte/trace/base.py`) is the namespace of tracer factories. Every
method is a `@staticmethod` that returns a `TracerBase` (or a
`TraceController`/`SessionTraceController` for the semantic wrappers).

| Helper | Returns | Purpose |
|--------|---------|---------|
| `Trace.off()` | `NullTracer` | No-op tracer (the default when nothing is passed). |
| `Trace.debug(events=None)` | `DebugTracer` | In-memory tracer that appends lifecycle events to `events`. |
| `Trace.custom(tracer)` | `TracerBase` | Normalizes a caller-provided tracer class or instance. |
| `Trace.profile(inner, profile=None, provider=None)` | `TraceController` | Wraps a low-level tracer in the semantic profile filter + provider translator. |
| `Trace.session(inner, name=None, profile=None, provider=None)` | `SessionTraceController` | Wraps a low-level tracer in a session-capable semantic controller that groups multiple agent runs under one root. |
| `Trace.continual(remember, *, max_memory_chars=1200, redact=True)` | `ContinualTracer` | Continual trace capture preset (for `trace_option=`, not `trace=`). |
| `Trace.langfuse(public_key=None, secret_key=None, host=None)` | `LangfuseTracer` | Langfuse external adapter. |
| `Trace.langsmith(api_key=None, project=None, endpoint=None, strict=False, include_runtime_info=False)` | `LangSmithTracer` | LangSmith external adapter. |
| `Trace.langsmith_default(...)` | `TraceController` | LangSmith wrapped in `TraceProfile.default()` (recommended single-agent preset). |
| `Trace.langsmith_verbose(...)` | `TraceController` | LangSmith wrapped in `TraceProfile.verbose()`. |
| `Trace.langsmith_session(...)` | `SessionTraceController` | LangSmith wrapped in a session-capable semantic controller (`name` and `profile` optional; defaults to `TraceProfile.default()`). |
| `Trace.phoenix(endpoint=None)` | `PhoenixTracer` | Arize Phoenix (OpenTelemetry) external adapter. |

Provider credentials are read from constructor kwargs first, then environment
variables (see `trace-providers.md`).

## The `agent.run` Root Trace Lifecycle

`BaseAgent.arun()` (in `vidbyte/agents/base.py`) owns the root trace. The
lifecycle is:

1. **Open root**: `self._tracer.start_trace("agent.run", strategy="direct",
   prompt=..., system_prompt=..., tools=..., provider=..., model=...,
   metadata=...)`. Inputs are redacted with `_safe_trace_value` first.
2. **Run** the runtime, passing the root context as `trace_context`.
3. **Record stop**: `_record_agent_stop(trace_ctx, result)` emits an `agent.stop`
   span — but **only when the tracer is semantic** (a `TraceController`). The
   check is `_is_semantic_tracer`, which duck-types the `inner`, `profile`, and
   `translator` attributes.
4. **Close root**: `self._tracer.end_trace(trace_ctx, output=_format_trace_output(result))`.
5. **Error path**: the `except` and the `BaseException` (CancelledError) handlers
   both call `end_trace(trace_ctx, error=exc)` so the root span is **always**
   finalized, even on cancellation.

`_format_trace_output` wraps each agentic-loop iteration in XML tags so the
recorded output reflects the loop structure.

## Spans Emitted by the Runtime

`vidbyte/agents/runtime.py` emits child spans under the root `agent.run` context.
Spans are opened either directly with `self._tracer.start_span(name,
parent=trace_context, ...)` or via the `_start_semantic_span(name, ...)`, which
only fires when the tracer is a `TraceController` (so semantic-only spans are
suppressed for raw provider tracers).

| Span name | Emitted in | Carries |
|-----------|------------|---------|
| `runtime.iteration` | `AgentRuntime._arun_once` | `agent_name`, `model_call_count`, `tool_call_count`, `tokens_used`, `iteration_count` |
| `llm.call` | `_invoke_with_middleware` | `_llm_trace_inputs(...)` (provider, model, messages, tool specs) — redacted |
| `tool.call` | `execute_tool_call` | `tool_name`, `provider`, `metadata` (tool input is redacted via `_safe_trace_value`) |
| `parser.tool_calls` | `_record_parser_span` | `provider`, `tool_call_count` |
| `parser.structured_output` | `AgentRuntime` (semantic-only, when `output_schema` is set) | `output_chars` |
| `context.window.build` | inner-loop context-window hook (semantic-only) | build summary |
| `middleware.decision` | middleware event loop (semantic-only) | `middleware_name`, decision fields |
| `algorithm.<name>` | context-window algorithm hook (semantic-only) | algorithm name, message |
| `agent.stop` | `BaseAgent._record_agent_stop` | final result metadata (semantic tracers only) |

Every span is closed with `end_span(..., output=...)` on success or
`end_span(..., error=exc)` on failure, including in the `BaseException` path so
an `llm.call` span is never left open when a `CancelledError` propagates.

## Secret Redaction at the Agent Layer

Before any payload reaches a tracer, the agent layer strips credential-like
fields and truncates long strings. This is independent of the semantic layer's
own `safe_trace_value`.

- `_safe_trace_value(value)` recursively removes mapping keys that look like
  secrets.
- `_is_secret_trace_key(key)` flags keys whose uppercased name contains
  `API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `CREDENTIAL`, or `AUTH`, or starts
  with `LANGSMITH_`.
- `_trace_text(value, max_chars=12000)` truncates very long strings to
  `"...[truncated]"` so large prompts do not dominate trace payloads.

The semantic controller applies its own `safe_trace_value` (see
`trace-profiles.md`) on top of this, so redaction happens at two layers.

## Code Snippets

### Debug tracer (local inspection)

```python
from vidbyte import Agent, Trace

events = []
agent = Agent(
    name="debugged",
    system_prompt="Work carefully.",
    runner=my_runner,
    trace=Trace.debug(events),
)

reply = await agent.arun("Explain the last tool call.")
for event in events:
    print(event["type"], event.get("name"), event.get("parent"))
```

### Recommended single-agent LangSmith shape

```python
from vidbyte import Agent, Trace

agent = Agent(
    name="observed",
    system_prompt="Work carefully.",
    provider="openai",
    model_name="gpt-4.1",
    trace=Trace.langsmith_default(project="vidbyte-agents"),
)
```

### Semantic profile wrapping a debug tracer

```python
from vidbyte import Trace, TraceProfile

events = []
trace = Trace.profile(
    inner=Trace.debug(events),
    profile=TraceProfile.default(),
)
```

### Session tracing (multiple agents under one root)

```python
from vidbyte import Agent, Trace, TraceProfile

events = []
trace = Trace.session(Trace.debug(events), name="workflow", profile=TraceProfile.verbose())

agent_a = Agent(name="planner", system_prompt="Plan.", runner=r1, trace=trace)
agent_b = Agent(name="worker", system_prompt="Execute.", runner=r2, trace=trace)

with trace.session("workflow"):
    await agent_a.arun("Plan.")
    await agent_b.arun("Execute.")
```

See `trace-controller-and-session.md` for the full session controller behavior.
