# Middleware

Middleware in the Vidbyte SDK is deterministic runtime policy around the agent
loop. It lets developers authorize runs, deny tools, compact context, retry
models, enforce budgets, and record audit events without making those controls
model-visible tools.

## Role In The SDK

`vidbyte.middleware` exposes `AgentMiddleware`, `MiddlewarePipeline`, structured
decisions, context payloads, events, transforms, and built-in middleware. Agents
pass middleware into compatible runtimes, which call lifecycle hooks before and
after model calls, tool calls, iterations, and whole runs.

## Design Philosophy

Policies should be explicit, ordered, and inspectable. Middleware returns
structured `MiddlewareDecision` objects instead of mutating hidden global state.
By default middleware fails closed, while individual middleware can opt into
fail-open behavior when policy failure should not abort the run.

## Vidbyte Website

This abstraction is used by the SDK architecture that powers agents on the
[Vidbyte website](https://vidbyte.pro). Website agents need deterministic runtime
controls for budgets, permissions, retries, auditability, and context bloat; the
middleware layer keeps those controls outside model-visible tool definitions.

## Usage

```python
from vidbyte import Agent, AgentMiddleware, MiddlewareDecision

class TenantPolicy(AgentMiddleware):
    async def before_run(self, ctx):
        if ctx.metadata.get("tenant_id") is None:
            return MiddlewareDecision.abort("missing_tenant")
        return MiddlewareDecision.continue_(metadata={"tenant_checked": True})

agent = Agent(
    name="guarded",
    system_prompt="Use tools only when they help.",
    runner=my_runner,
    tools=[lookup_metric],
    middleware=[TenantPolicy()],
    metadata={"tenant_id": "demo"},
)
```

Built-ins are available from `vidbyte.middleware.builtins` and include rate
limits, token and cost budgets, runtime limits, retry, circuit breaker, audit,
tool policy, tool-result compaction, message-history compaction, canary tripwire,
confused-deputy guard, and honeypot tool checks.

Apply built-in tool policy and compaction together:

```python
from vidbyte.middleware.builtins import MessageHistoryCompactionMiddleware, ToolPolicyMiddleware

agent = agent.fork(
    middleware=[
        ToolPolicyMiddleware(allow_tools={"lookup_metric"}),
        MessageHistoryCompactionMiddleware.trim_to_token_budget(max_tokens=8000),
    ]
)
```

## Feature Coverage

- Lifecycle hooks before and after runs, iterations, model calls, model errors, tool calls, and completed runs.
- Structured decisions for continue, abort, sleep, deny tool, and transform behavior.
- Ordered middleware pipelines with metadata merging and transform merging.
- Failure policy through `fail_closed` and fail-open event recording.
- Built-ins for audit logs, rate limits, token/cost budgets, runtime limits, retries, circuit breakers, loop detection, tool policy, safety tripwires, and compaction.
- Context and provider-message transforms for deterministic compaction.
- Metadata output for final agent results.

## Key Modules

- `base.py`: hook base class for custom middleware.
- `pipeline.py`: ordered hook dispatcher and decision handling.
- `builtins/`: ready-made policy, safety, retry, budget, and compaction middleware.
- `compaction/`: deterministic context and trace-backed compaction helpers.

## Related Layers

Middleware is attached to [`agents`](../agents/README.md), often controls
[`tools`](../tools/README.md), and can shape [`context`](../context/README.md).
