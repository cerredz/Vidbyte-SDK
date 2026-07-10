# Agents

## Folder Description / Intent

`vidbyte.agents` is the SDK's executable-agent boundary. It turns explicit
agent configuration—system instruction, provider/model identity, tools, context,
permissions, middleware, tracing, and loop settings—into a runnable actor that
returns an `AgentMessage`. The folder exists so callers can compose those
capabilities without treating any one provider, tool implementation, or runtime
strategy as the public agent API.

The folder separates public composition from execution mechanics. `base.py`
owns agent lifecycle and public entry points; `runtime.py` owns the canonical
linear model/tool loop; `runtimes/` holds alternate runtime implementations;
and focused modules own handoff, aggregation, context algorithms, settings, and
MCP attachment integration. This separation keeps compatibility decisions near
construction and leaves model/tool behavior inspectable at the runtime boundary.

This folder is not the home for provider adapters, tool implementations, context
primitive definitions, generic middleware, session storage, or pipeline
topologies. Read the relevant owning folder before adding any of those concerns
to an agent-facing API.

## Usage

```python
from vidbyte import Agent, tool

@tool
def lookup_metric(user_id: int) -> dict[str, int]:
    return {"user_id": user_id, "score": 94}

agent = Agent(
    name="analyst",
    system_prompt="Answer directly and cite uncertainty.",
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
)

reply = await agent.arun("Summarize user 42.")
print(reply.content)
```

Use `AgentInput` when one call needs context or metadata without changing the
agent defaults. Use `agent.persist(store=...)` to bind a durable session; the
session records checkpoints around the same public `arun()` and `run()` paths.

## Non-Goals

- Do not define context primitives, context budgets, or context placement here; `vidbyte/context` owns those contracts.
- Do not add generic policy hooks or policy implementations here; `vidbyte/middleware` owns ordered runtime policy.
- Do not implement local, built-in, MCP, or permission-policy tools here; `vidbyte/tools` owns those capabilities.
- Do not add provider-specific request/response adapters here; `vidbyte/providers` and `vidbyte/lib/runners` own provider integration.
- Do not add shared dataclasses, enums, base errors, or registries here; `vidbyte/lib` owns cross-layer contracts.
- Do not add durable session storage formats or stores here; `vidbyte/sessions` owns persistence and checkpoint transport.
- Do not add pipeline fan-out, reduction, or conditional topology here; `vidbyte/pipelines` owns agent composition above one actor.
- Do not add paradigm-specific orchestration here; `vidbyte/paradigms` owns opinionated runnable harnesses.
- Do not add trace backends or provider tracing adapters here; `vidbyte/trace` owns observability implementations.

## File Index

- `__init__.py` — public agent-layer exports, including `Agent` as the `BaseAgent` compatibility alias. Open it when changing import compatibility, not to implement runtime behavior.
- `base.py` — public `BaseAgent` lifecycle: configuration validation, runner inference, dispatch, trace/session/handoff integration, and sync wrappers. Start here for public agent behavior.
- `runtime.py` — canonical direct text model/tool loop. Open it for middleware order, tool execution, budgets, context-window hooks, output contracts, or direct-run traces.
- `errors.py` — typed, redacted diagnostic errors raised at base-agent and direct-runtime boundaries. Open it before adding a target-scope failure mode.
- `client.py` — namespace factory used by `VidbyteSDK().agents`. Open it for SDK client ergonomics rather than agent execution.
- `aggregation.py` — multi-provider aggregation agent and synthesis flow. Open it for aggregation-specific behavior; do not fold it into `BaseAgent`.
- `context_algorithms.py` — adapter between `AgentRuntime` and context-window algorithms. Open it when changing pre-loop or inner-loop algorithm selection.
- `continual_trace.py` — agent-facing continual-trace integration. Open it for trace artifact behavior, not generic tracing backends.
- `handoff.py` — structured handoff generation from completed runs. Open it when changing handoff schema or post-run summaries.
- `mixins.py` — MCP server attachment lifecycle mixed into agents and harnesses. Open it for subprocess attachment or cleanup behavior.
- `types.py` — compatibility exports for agent-facing dataclasses and modality types. Open it when changing public type import paths.
- `settings/` — strongly typed loop, tool, and output configuration. Open it before adding new runtime settings.
- `runtimes/` — linear compatibility export plus search and actor-model runtime implementations. Open it only when the runtime topology itself changes.
- `algorithms/` — agent-local algorithm helpers. Open it for algorithm implementation rather than public agent configuration.

## Logs

- `base.py` owns public composition and `runtime.py` owns the direct loop - keeping that split prevents provider or tool mechanics from leaking into public construction.
- Non-linear runtime incompatibilities fail during construction - this prevents a linear-only policy from becoming a silent no-op at execution time.
- Agent diagnostic errors redact dynamic state by default - error packets may aid internal debugging but must not become model-visible prompt or tool payloads.
- `runtimes/linear.py` remains a compatibility re-export - direct-loop changes belong in `runtime.py`, not in the shim.

## Related Layers

Agents compose [`context`](../context/README.md), [`tools`](../tools/README.md),
[`middleware`](../middleware/README.md), [`providers`](../providers/README.md),
the session contracts under `vidbyte/sessions`, [`pipelines`](../pipelines/README.md),
and [`trace`](../trace/README.md).
