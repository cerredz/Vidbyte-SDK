<!--
Context Protocol Header

Description:
    Skill enumerating every type of tracing in the Vidbyte SDK.
Purpose:
    Lets an agent understand the full tracing taxonomy and choose the right
    tracer type, span kind, and detail level for a task.
Architecture:
    - Separates observability tracing from continual tracing.
    - Lists every TracerBase implementation and wrapper.
    - Documents the SpanKind and TraceDetail enums and their mapping to
      TraceProfile presets.
Relations:
    Sub-skill of skills/tracing/SKILL.md. Pairs with enabling-tracing.md,
    trace-profiles.md, and trace-providers.md. Continual deep detail lives in
    skills/vidbyte-sdk/continual-tracing.md.
-->

# Types of Tracing

The Vidbyte SDK has **two independent tracing systems** with several tracer
types inside the observability system. This skill enumerates all of them and the
two enums that describe span shape.

## Observability vs Continual

| | Observability tracing | Continual tracing |
|---|---|---|
| **Argument** | `trace=` (alias `tracer=`) | `trace_option=` |
| **Output** | A span tree (root + child spans) recorded in a backend or in memory | A structured artifact dict (goal, actions, mistakes, status) published in `reply.metadata["trace"]` |
| **Mechanism** | `TracerBase.start_trace`/`start_span` called by the agent runtime | Runtime middleware (`ContinualTraceMiddleware`) runs a dedicated `ContinualTraceAgent` on an interval |
| **Failure mode** | Tracers fail open; trace errors never abort the run | Fail open (`fail_closed = False`); errors recorded in `trace_metadata` |
| **Where** | `vidbyte/trace/` + `vidbyte/providers/tracing/` + `vidbyte/lib/tracing/` | `vidbyte/trace/continual/` + `vidbyte/agents/continual_trace.py` + `vidbyte/middleware/continual_trace.py` |

They are selected independently and can be used together. For the full continual
contract, read `skills/vidbyte-sdk/continual-tracing.md`.

## Observability Tracer Types

Every observability tracer implements `TracerBase` (defined in
`vidbyte/lib/tracing/base.py`): `start_trace`, `end_trace`, `start_span`,
`end_span`. The types, from simplest to richest:

### 1. Off — `NullTracer`

Zero-overhead no-op tracer. Returned by `Trace.off()` and used as the default
when an agent is constructed without a `trace=` argument. Every method returns a
blank `SpanContext` and does nothing.

### 2. Debug — `DebugTracer`

In-memory tracer (`vidbyte/trace/debug.py`) that appends one dict per lifecycle
event to an `events` list. Returned by `Trace.debug(events)`. Each event records
`type` (`start_trace`/`end_trace`/`start_span`/`end_span`), `name`, `attributes`,
`context`, `parent`, `output`, and `error`. Use it for local inspection and
tests.

```python
from vidbyte import Trace

events = []
trace = Trace.debug(events)
```

### 3. External provider adapters — `LangSmithTracer`, `LangfuseTracer`, `PhoenixTracer`

These live in `vidbyte/providers/tracing/` and **call external SDKs**
(`langsmith.Client`, `langfuse.Langfuse`, OpenTelemetry). Returned by
`Trace.langsmith(...)`, `Trace.langfuse(...)`, `Trace.phoenix(...)`. They are
low-level `TracerBase` implementations that own credential resolution and
network calls. See `trace-providers.md` for env vars and install requirements.

### 4. Semantic controller — `TraceController`

The semantic layer (`vidbyte/trace/controller.py`). It wraps any low-level
tracer (debug, provider adapter, null, or custom) and adds:

- **Profile filtering** — drops spans the active `TraceProfile` does not allow.
- **Provider translation** — converts semantic spans to provider fields (e.g.
  LangSmith `run_type`) via a `ProviderTraceTranslator`.
- **Context-local span stack** — resolves parents async-locally.

Returned by `Trace.profile(inner, profile=..., provider=...)` and by the
`Trace.langsmith_default`/`Trace.langsmith_verbose` helpers (which are
`Trace.profile` with a LangSmith inner tracer and a preset profile).

```python
from vidbyte import Trace, TraceProfile

trace = Trace.profile(inner=Trace.debug([]), profile=TraceProfile.verbose())
```

### 5. Session wrapper — `SessionTraceController`

Groups multiple agent runs under one root trace so a workflow appears as one
tree. `SessionTraceController` (`vidbyte/trace/session.py`) is a
`TraceController` subclass that opens a named session root and converts child
`agent.run` traces into child spans while the session is active. Returned by
`Trace.session(...)` and `Trace.langsmith_session(...)`. See
`trace-controller-and-session.md` for behavior.

```python
from vidbyte import Trace, TraceProfile

trace = Trace.session(Trace.debug([]), name="workflow", profile=TraceProfile.default())
```

## `SpanKind` Enum

Provider-neutral span categories defined in `vidbyte/trace/schema.py`. A
`SpanSpec` carries exactly one `SpanKind`; the provider translator maps it to a
backend-specific field.

| `SpanKind` | Meaning | LangSmith `run_type` |
|------------|---------|----------------------|
| `CHAIN` | Default/orchestration span (agent run, runtime iteration, middleware decision) | `chain` |
| `LLM` | Model call | `llm` |
| `TOOL` | Tool call / permission check | `tool` |
| `RETRIEVER` | Retrieval span | `retriever` |
| `EMBEDDING` | Embedding span | `embedding` |
| `PROMPT` | Context-window / prompt construction span | `prompt` |
| `PARSER` | Tool-call parsing / structured-output validation | `parser` |

The `LangSmithProviderTranslator` sets `run_type` to the `SpanKind` value
directly; the generic pass-through translator adds nothing.

## `TraceDetail` Levels

The detail threshold a span requires, defined in `vidbyte/trace/schema.py`. The
profile's `detail` field and per-component settings use these to decide which
spans survive filtering. Ordering is `MINIMAL < STANDARD < VERBOSE < DIAGNOSTIC`.

| `TraceDetail` | Includes |
|----------------|-----------|
| `MINIMAL` | `agent.run`, `llm.call`, `tool.call` — the high-signal core |
| `STANDARD` | Minimal plus parser spans, tool input/output, `agent.stop`, retriever/embedding categories, session roots |
| `VERBOSE` | Standard plus `runtime.iteration`, context-window summaries, algorithm phases, aggregate phases, middleware decisions |
| `DIAGNOSTIC` | Verbose plus diagnostic component spans (e.g. `middleware.hook`) and fuller metadata subject to redaction/truncation |

### Mapping to `TraceProfile` presets

`TraceProfile` (see `trace-profiles.md`) bundles a `detail` level with
per-component settings. There are two families: **detail presets** (uniform
across all 19 components) and **role-oriented presets** (hand-tuned per
component for a specific use case).

#### Detail presets

| Preset | `detail` | Effect |
|--------|----------|--------|
| `TraceProfile.minimal()` | `MINIMAL` | Only the core three spans |
| `TraceProfile.default()` | `STANDARD` | The recommended single-agent shape |
| `TraceProfile.verbose()` | `VERBOSE` | Adds runtime/context/algorithm/middleware detail |
| `TraceProfile.diagnostic()` | `DIAGNOSTIC` | Everything, for local debugging |

#### Role-oriented presets

| Preset | `detail` | Tuned for |
|--------|----------|-----------|
| `TraceProfile.production()` | `STANDARD` | Live traffic: errors/aborts without internal noise (context/algorithms/runtimes/aggregate off, middleware decisions-only) |
| `TraceProfile.cost_monitoring()` | `STANDARD` | Cost attribution: middleware verbose, tools inputs/outputs, runtimes default |
| `TraceProfile.developer()` | `VERBOSE` | Local development: runtime iteration + context summary, minimal tool noise |
| `TraceProfile.multi_agent()` | `VERBOSE` | Multi-agent workflows: aggregate/pipelines/handoff/sessions verbose, tools minimal |
| `TraceProfile.algorithm_debug()` | `VERBOSE` | In-context learning debugging: algorithms + context verbose |

## Continual Tracing Type

Continual tracing is a different kind of "trace" — not spans, but a typed
artifact updated over the run.

- `ContinualTracer` (`vidbyte/trace/continual/base.py`) — a `DebugTracer`
  subclass with validated `remember` categories (`model_calls`, `tool_calls`,
  `failures`, `outputs`, `decisions`), `max_memory_chars`, and `redact`. Built by
  `Trace.continual(remember, ...)`.
- `ActionTrace` / `ActionTraceModel` (`vidbyte/trace/continual/prebuilt.py`) — a
  Pydantic model with `goal`, `actions_taken`, `mistakes`, `current_status`,
  converted to a `TraceSchema` via `TraceSchema.from_model`.
- `ContinualTraceAgent` / `ContinualTraceMiddleware` — the agent and middleware
  that fill the schema on an interval.

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.continual import ActionTrace

agent = Agent(
    name="worker",
    system_prompt="...",
    runner=runner,
    trace_option=TraceOption.continual(ActionTrace, every_n_iterations=5, max_trace_iterations=3),
)
reply = await agent.arun("task")
artifact = reply.metadata["trace"]
```

See `skills/vidbyte-sdk/continual-tracing.md` for the invariants (the artifact
never enters the main context window, fail-open, bounded cost, linear runtime
only).

## Decision Guide

```text
Do you want to inspect agent runtime behavior (spans)?
|-- yes -> Observability tracing (trace=)
|   |-- no backend, local only        -> Trace.debug(events)
|   |-- LangSmith                     -> Trace.langsmith_default(...)   (recommended)
|   |-- Langfuse                      -> Trace.langfuse(...)
|   |-- Phoenix                       -> Trace.phoenix(...)
|   |-- custom profile/detail         -> Trace.profile(inner, profile=..., provider=...)
|   `-- multiple agents, one tree     -> Trace.session(...) / Trace.langsmith_session(...)
`-- no -> Do you want a live handoff artifact (goal/actions/mistakes/status)?
    |-- yes -> Continual tracing (trace_option=TraceOption.continual(ActionTrace))
    `-- no  -> Trace.off() (default)
```
