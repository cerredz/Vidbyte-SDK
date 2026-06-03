<!--
Context Protocol Header

Description:
    User-facing recipe for enabling continual trace artifacts on Vidbyte agents.
Purpose:
    Shows how to attach prebuilt or custom trace schemas and read final trace
    metadata from an AgentMessage reply.
Architecture:
    Usage skill with short examples and constraints.
Relations:
    Complements skills/usage/create_agent.md and SDK continual tracing guidance.
-->

# Use Continual Trace

Use continual trace when an agent should return a structured handoff-style artifact describing its goal, actions, mistakes, and status.

## Prebuilt Schema

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.prebuilt import ActionTrace

agent = Agent(
    name="worker",
    system_prompt="Work carefully and record useful progress.",
    runner=my_runner,
    trace=TraceOption.continual(ActionTrace, every_n_iterations=5, max_trace_iterations=3),
)

reply = await agent.arun("Implement the requested change")
trace = reply.metadata["trace"]
trace_metadata = reply.metadata["trace_metadata"]
```

`ActionTrace` includes `goal`, `actions_taken`, `mistakes`, and `current_status`.

## Custom Schema

```python
from vidbyte import TraceOption

trace = TraceOption.continual({
    "goal": "The task the agent is pursuing.",
    "actions_taken": "Important actions or tool calls completed so far.",
    "mistakes": "Mistakes, failed attempts, or recoveries worth preserving.",
})
```

Pass the resulting `trace` option to `Agent(..., trace=trace)`.

## Constraints

- Continual trace works on the default direct linear text runtime.
- Non-linear runtimes and non-default context-window algorithms reject `trace=` in v1.
- `trace=` is user-visible run metadata. `tracer=` is observability instrumentation.
- The final artifact is returned in `reply.metadata["trace"]`; bookkeeping is returned in `reply.metadata["trace_metadata"]`.
