# Trace

Tracing in the Vidbyte SDK makes agent runtime behavior inspectable. The trace
layer includes a small facade for tracer selection, an in-memory debug tracer,
provider-backed tracers, and structured continual trace artifacts.

## Role In The SDK

`vidbyte.trace` exposes `Trace`, `DebugTracer`, `SessionTracer`, provider tracer
helpers, `TraceOption`, `TraceSchema`, `ActionTrace`, `ContinualTraceAgent`, and
`ContinualTraceMiddleware`. Agents use this layer to start and end trace spans,
group related agent runs into one session trace, capture metadata safely, and
optionally produce structured handoff-like trace artifacts.

## Design Philosophy

Observability should be optional, explicit, and safe by default. `Trace.off()`
uses the null tracer, `Trace.debug()` keeps events in memory for local
inspection, provider tracers are configured by the caller, and continual trace
artifacts fail open so trace failures do not abort the main agent run.

Semantic trace profiles sit above raw provider adapters. They let the SDK define
Vidbyte concepts once, then translate them into provider-specific fields such as
LangSmith `run_type`.

## Usage

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

Use `Trace.langsmith_default(...)` for the recommended single-agent LangSmith
trace shape:

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

Use semantic profiles when you want prebuilt SDK spans instead of hand-written
provider callbacks:

```python
events = []
trace = Trace.profile(
    inner=Trace.debug(events),
    profile=TraceProfile.default(),
)
```

LangSmith helpers wrap the optional LangSmith adapter and translate Vidbyte span
kinds to LangSmith run types:

```python
trace = Trace.langsmith_default(api_key="...", project="sdk")
trace = Trace.langsmith_verbose(api_key="...", project="sdk")
trace = Trace.langsmith_session(api_key="...", project="sdk", name="workflow")
```

Profiles:

- `TraceProfile.minimal()`: `agent.run`, `llm.call`, and `tool.call`.
- `TraceProfile.default()`: minimal plus parser, tool input/output, agent stop, retriever/embedding categories, and session roots.
- `TraceProfile.verbose()`: default plus runtime iteration, context-window summaries, algorithms, aggregate phases, and middleware decisions.
- `TraceProfile.diagnostic()`: verbose plus diagnostic component spans and fuller metadata subject to redaction/truncation.

Provider-neutral span kinds are `chain`, `llm`, `tool`, `retriever`,
`embedding`, `prompt`, and `parser`.

Session tracing groups multiple agent runs under one root:

```python
trace = Trace.session(Trace.debug(events), name="workflow", profile=TraceProfile.verbose())

with trace.session("workflow"):
    await agent_a.arun("Plan.")
    await agent_b.arun("Execute.")
```

Configure continual trace artifacts separately from observability tracing:

```python
from vidbyte import AgentForkSettings, TraceOption
from vidbyte.trace.continual import ActionTrace

agent = agent.fork(AgentForkSettings(trace_option=TraceOption.continual(ActionTrace)))
```

Omitting `trace_option` on `fork()` preserves the parent agent's continual trace
option; passing a new option overrides it for the forked agent only.

## Key Modules

- `base.py`: public `Trace` facade.
- `debug.py`: in-memory debug tracer.
- `schema.py`: semantic span names, kinds, detail levels, parent policies, and contexts.
- `profiles.py`: profile presets and redaction/truncation behavior.
- `controller.py`: `TraceController`, the composable semantic tracer.
- `session.py`: legacy `SessionTracer` plus `SessionTraceController` for multi-agent root grouping.
- `components/`: prebuilt span-spec factories for agents, runtimes, context, algorithms, middleware, tools, and parsers.
- `providers/`: semantic-to-provider translators such as LangSmith run-type mapping.
- `continual/`: continual tracer, middleware, agent, schema helpers, and prebuilt trace models.
- `vidbyte.lib.tracing`: shared tracer base contracts.

## Related Layers

Trace wraps [`agents`](../agents/README.md), can observe [`tools`](../tools/README.md),
and integrates with provider-backed tracing under [`providers`](../providers/README.md).
