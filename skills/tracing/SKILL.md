<!--
Context Protocol Header

Description:
    Master index and file map for Vidbyte SDK tracing skills.
Purpose:
    Routes agents and contributors to the right tracing skill by task and gives
    a complete map of every tracing file in the repository.
Architecture:
    - Explains the two tracing systems (observability vs continual).
    - Maps the three tracing folders to their roles.
    - Routes the reader to seven sibling skills by topic.
    - Lists the full tracing file inventory with one-line responsibilities.
Relations:
    Entry point for skills/tracing/. Sibling skills live in the same folder.
    Continual deep detail lives in skills/vidbyte-sdk/continual-tracing.md.
-->

# Tracing Skills

This folder is the complete, self-contained reference for tracing inside the
Vidbyte SDK. Read the skill that matches your task; each one is standalone and
includes code snippets drawn from the real implementation.

## Two Tracing Systems

The SDK has **two independent tracing systems**. They are selected by different
agent constructor arguments and must not be confused:

| System | Argument | What it produces | Where it lives |
|--------|----------|------------------|----------------|
| **Observability tracing** | `trace=` (alias `tracer=`) | Span trees that make agent runtime behavior inspectable in a backend (LangSmith, Langfuse, Phoenix) or in memory | `vidbyte/trace/` + `vidbyte/providers/tracing/` + `vidbyte/lib/tracing/` |
| **Continual tracing** | `trace_option=` | A structured, continually-updated artifact (goal, actions, mistakes, status) published as a live handoff document via middleware | `vidbyte/trace/continual/` (+ `vidbyte/agents/continual_trace.py`, `vidbyte/middleware/continual_trace.py`) |

Continual tracing is **not** observability. It is runtime middleware that fills a
typed schema. For full continual-tracing detail, read
[`skills/vidbyte-sdk/continual-tracing.md`](../vidbyte-sdk/continual-tracing.md);
the skills in this folder only summarize it and link there.

## Three Folders

| Folder | Role | Calls external SDKs? |
|--------|------|-----------------------|
| `vidbyte/trace/` | Public `Trace` facade, semantic profiles, controller, session, component span specs, provider translators, continual presets | No (translators only map fields) |
| `vidbyte/providers/tracing/` | Legacy external provider adapters (`LangSmithTracer`, `LangfuseTracer`, `PhoenixTracer`) | Yes (langsmith, langfuse, opentelemetry clients) |
| `vidbyte/lib/tracing/` | Provider-neutral tracer contracts: `TracerBase` (ABC), `SpanContext`, `NullTracer` | No |

The split is deliberate: `vidbyte/trace/providers/` **translates** semantic spans
into provider fields (e.g. LangSmith `run_type`) without network calls; the
adapters under `vidbyte/providers/tracing/` own the actual external SDK calls.

## Which Skill To Read

| If you want to... | Read |
|-------------------|------|
| Turn tracing on for an agent and see the span lifecycle | [`enabling-tracing.md`](enabling-tracing.md) |
| Understand every kind of tracing and the span/detail enums | [`trace-types.md`](trace-types.md) |
| Pick or tune a `TraceProfile` (minimal/default/verbose/diagnostic) | [`trace-profiles.md`](trace-profiles.md) |
| Wire up LangSmith, Langfuse, or Phoenix, or add a provider | [`trace-providers.md`](trace-providers.md) |
| See the catalog of every semantic span spec and the maintenance rule | [`trace-components.md`](trace-components.md) |
| Understand `TraceController` filtering/parent logic or group multi-agent runs | [`trace-controller-and-session.md`](trace-controller-and-session.md) |
| Change the tracer and know exactly which files to edit and update | [`updating-the-tracer.md`](updating-the-tracer.md) |

## Tracing File Map

Every tracing file and its responsibility:

```text
vidbyte/lib/tracing/
  base.py                 SpanContext, TracerBase (ABC), NullTracer (off)
  __init__.py             re-exports NullTracer, SpanContext, TracerBase

vidbyte/trace/
  __init__.py             public exports (Trace, TraceProfile, SpanKind, ...)
  base.py                 Trace facade: off/debug/custom/profile/session/
                          continual/langfuse/langsmith/langsmith_default/
                          langsmith_verbose/langsmith_session/phoenix
  debug.py                DebugTracer (in-memory event recorder)
  schema.py               SpanKind, TraceDetail, ParentPolicy, SpanSpec,
                          SemanticSpanContext
  profiles.py             TraceProfile presets (4 detail + 5 role-oriented) +
                          TraceComponentSettings + safe_trace_value / _is_secret_key
  controller.py           TraceController (profile filter + translator +
                          context-local span stack)
  session.py              SessionTraceController (multi-agent root grouping)
  registry.py             TraceComponentRegistry (test/doc span registry)
  components/             Vidbyte-owned span-spec factories — 13 files:
    agents.py             agent + aggregate spans (run, stop, loop settings,
                          output contract, handoff, modality, algorithm, mcp, runner)
    runtimes.py           linear/actor/search runtime spans
    context.py            context-window, compaction, manager, primitive, template
    algorithms.py         context-window algorithm phases
    middleware.py         middleware decisions, per-hook, actions, transforms, builtins
    tools.py              tool lifecycle (call, permission, resolve, validate, deny,
                          error, compact, parallel_batch, mcp)
    parsers.py            tool-call parsing, structured output, is_done, response format
    pipelines.py          pipeline topology runs + stage invoke
    handoff.py            handoff generate/validate/record/sync
    sources.py            artifact source fetch/load + cache hit/miss
    sessions.py           session start/end + case
    evals.py              eval harness run/grade/behavior
    mcp.py                MCP attach/search/transport
  providers/              semantic-to-provider translators (see trace-providers.md)
  continual/              ContinualTracer + ActionTrace + re-exports
                          (see skills/vidbyte-sdk/continual-tracing.md)

vidbyte/providers/tracing/             external-SDK adapters (see trace-providers.md)
  langsmith.py            LangSmithTracer
  langfuse.py             LangfuseTracer
  phoenix.py              PhoenixTracer

vidbyte/agents/
  base.py                 trace=/tracer= wiring, agent.run root trace, agent.stop
  runtime.py              runtime.iteration / llm.call / tool.call /
                          parser.tool_calls / parser.structured_output span
                          emission + payload redaction

vidbyte/lib/dataclasses/trace.py       TraceOption/TraceSchema (continual config)
vidbyte/lib/errors.py                  ConfigurationError, TracerConfigurationError
```

## Quick Start

Debug tracer (in-memory, no backend):

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
print(events)
```

Recommended single-agent LangSmith shape (semantic default profile):

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

The default LangSmith tree keeps the high-signal core spans:

```text
agent.run
|-- llm.call
`-- tool.call
```

Semantic profile wrapping any low-level tracer:

```python
from vidbyte import Trace, TraceProfile

events = []
trace = Trace.profile(
    inner=Trace.debug(events),
    profile=TraceProfile.default(),
)
```

## Maintenance Rule

When you change tracing behavior, update `vidbyte/trace/README.md` and/or
`llms.txt`, and follow the file-by-file guide in
[`updating-the-tracer.md`](updating-the-tracer.md). When you add or change an
agent runtime, context-window algorithm, middleware, tool, parser, or
aggregate-agent behavior, check whether `vidbyte/trace/components/` needs a new
or updated span spec in the same change — see
[`trace-components.md`](trace-components.md).
