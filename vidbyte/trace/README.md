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

The default LangSmith tree is:

```text
agent.run
|-- llm.call
`-- tool.call
```

Those names use LangSmith-native run types: `agent.run` is a chain run,
`llm.call` is an LLM run, and `tool.call` is a tool run. Specialized LangSmith
run types such as retriever, embedding, prompt, and parser are reserved for
future verbose or subsystem-specific tracing work.

Group several agent runs under one parent trace with `SessionTracer`:

```python
events = []
trace = Trace.session(Trace.debug(events), default_name="local-workflow")

with trace.session(case="smoke"):
    planner = Agent(name="planner", system_prompt="Plan.", runner=planner_runner, trace=trace)
    writer = Agent(name="writer", system_prompt="Write.", runner=writer_runner, trace=trace)
    planner.run("Plan the answer")
    writer.run("Write the answer")
```

Configure continual trace artifacts separately from observability tracing:

```python
from vidbyte import TraceOption
from vidbyte.trace.continual import ActionTrace

agent = agent.fork(trace_option=TraceOption.continual(ActionTrace))
```

## Key Modules

- `base.py`: public `Trace` facade.
- `debug.py`: in-memory debug tracer.
- `session.py`: session tracer wrapper for grouping multiple agent runs.
- `continual/`: continual tracer, middleware, agent, schema helpers, and prebuilt trace models.
- `vidbyte.lib.tracing`: shared tracer base contracts.

## Related Layers

Trace wraps [`agents`](../agents/README.md), can observe [`tools`](../tools/README.md),
and integrates with provider-backed tracing under [`providers`](../providers/README.md).
