# Trace

Tracing in the Vidbyte SDK makes agent runtime behavior inspectable. The trace
layer includes a small facade for tracer selection, an in-memory debug tracer,
provider-backed tracers, and structured continual trace artifacts.

## Role In The SDK

`vidbyte.trace` exposes `Trace`, `DebugTracer`, provider tracer helpers,
`TraceOption`, `TraceSchema`, `ActionTrace`, `ContinualTraceAgent`, and
`ContinualTraceMiddleware`. Agents use this layer to start and end trace spans,
capture metadata safely, and optionally produce structured handoff-like trace
artifacts.

## Design Philosophy

Observability should be optional, explicit, and safe by default. `Trace.off()`
uses the null tracer, `Trace.debug()` keeps events in memory for local
inspection, provider tracers are configured by the caller, and continual trace
artifacts fail open so trace failures do not abort the main agent run.

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agents need visibility into what
they attempted, which tools they called, what failed, and what state should be
preserved for handoff or follow-up work.

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

Configure continual trace artifacts separately from observability tracing:

```python
from vidbyte import TraceOption
from vidbyte.trace.continual import ActionTrace

agent = agent.fork(trace_option=TraceOption.continual(ActionTrace))
```

Use provider-backed tracing when an external observability backend is configured:

```python
from vidbyte import Trace

agent = agent.fork(
    trace=Trace.langsmith(project="vidbyte-agents", include_runtime_info=True)
)
```

## Feature Coverage

- `Trace.off()`, `Trace.debug()`, `Trace.custom()`, `Trace.continual()`, and provider helpers.
- `DebugTracer` for local in-memory trace event inspection.
- Shared tracer base contracts through `vidbyte.lib.tracing`.
- Provider-backed Langfuse, LangSmith, and Phoenix tracer helpers.
- `TraceOption.continual()` for structured trace artifacts produced by a dedicated trace agent.
- `TraceSchema`, `TraceField`, `TraceMode`, and prebuilt `ActionTrace` schema support.
- Continual trace middleware that records lifecycle events without writing trace memory into the main agent context.

## Key Modules

- `base.py`: public `Trace` facade.
- `debug.py`: in-memory debug tracer.
- `continual/`: continual tracer, middleware, agent, schema helpers, and prebuilt trace models.
- `vidbyte.lib.tracing`: shared tracer base contracts.

## Related Layers

Trace wraps [`agents`](../agents/README.md), can observe [`tools`](../tools/README.md),
and integrates with provider-backed tracing under [`providers`](../providers/README.md).
