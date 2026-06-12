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

## Key Modules

- `base.py`: public `Trace` facade.
- `debug.py`: in-memory debug tracer.
- `continual/`: continual tracer, middleware, agent, schema helpers, and prebuilt trace models.
- `vidbyte.lib.tracing`: shared tracer base contracts.

## Related Layers

Trace wraps [`agents`](../agents/README.md), can observe [`tools`](../tools/README.md),
and integrates with provider-backed tracing under [`providers`](../providers/README.md).
