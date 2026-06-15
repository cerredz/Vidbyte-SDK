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

## Key Modules

- `base.py`: hook base class for custom middleware.
- `pipeline.py`: ordered hook dispatcher and decision handling.
- `builtins/`: ready-made policy, safety, retry, budget, and compaction middleware.
- `compaction/`: deterministic context and trace-backed compaction helpers.

## Related Layers

Middleware is attached to [`agents`](../agents/README.md), often controls
[`tools`](../tools/README.md), and can shape [`context`](../context/README.md).
