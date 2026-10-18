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

With `TraceProfile.diagnostic()`, the SDK records every hook invocation as a
`middleware.hook` trace span with its elapsed duration and safe decision data.
The final agent result's `middleware.events` remains intentionally smaller: it
contains only control-flow decisions and fail-open exceptions, not ordinary
continue decisions.

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
    provider="openai",
    model_name="gpt-4.1",
    tools=[lookup_metric],
    middleware=[TenantPolicy()],
    metadata={"tenant_id": "demo"},
)
```

Built-ins are available from `vidbyte.middleware.builtins` and include rate
limits, token and cost budgets, runtime limits, retry, circuit breaker, audit,
tool policy, tool-result compaction, message-history compaction, canary tripwire,
confused-deputy guard, honeypot tool checks, and delegation limits.

`DelegationLimitsMiddleware(limits, depth=...)` holds one delegating tool to a
depth cap and a per-call batch cap from a `DelegationLimits` record. It denies a
call at or past `max_depth`, or one whose task list is longer than
`max_parallel`, before the tool runs, with a reason that names the cap; every
other tool passes untouched. Give each agent in a tree its own instance at its
own depth. `InfiniteMemoryAgent` uses it for `launch_subagent`, so its prompts
describe how to delegate and never state the caps. Deterministic limits like
these belong in middleware; behavior belongs in the prompt.

`TokenBudgetMiddleware(max_tokens=...)` is a hard cap by default: once
provider-reported cumulative usage reaches the limit, the run stops before the
next iteration. Set `allow_final_response_over_budget=True` to allow one final
over-budget model call with an injected instruction to answer immediately:

```python
from vidbyte.middleware.builtins import TokenBudgetMiddleware

middleware = [
    TokenBudgetMiddleware(max_tokens=50_000, allow_final_response_over_budget=True),
]
```

This soft-overrun mode depends on provider-reported token usage. It is separate
from `Agent(max_tokens=...)`, which remains a runtime hard cap and can stop the
run before middleware gets a chance to request the final response.

`review_finish(ctx)` is the one hook that returns a `FinishReview` instead of a
`MiddlewareDecision`. The linear runtime calls it at every finish attempt, a
plain answer or an `isDone` call, after the output contracts accept it.
`FinishReview.accept()` lets the run end, `FinishReview.continue_with(text)`
sends the model back to work with `text` as a user message, and
`FinishReview.stop(text)` ends the run with the model's answer and
`stop_reason` `contract_unsatisfied`. The first middleware that does not accept
decides, and later ones are not asked. The hook records no events and ignores
`fail_closed`: an exception it raises ends the run. `CodingAgent`'s
`verify_command` is built on it (`builtins/verify_command.py`, not re-exported
from `vidbyte.middleware.builtins`).

## Key Modules

- `base.py`: hook base class for custom middleware.
- `pipeline.py`: ordered hook dispatcher and decision handling.
- `builtins/`: ready-made policy, safety, retry, budget, and compaction middleware.
- `compaction/`: deterministic context and trace-backed compaction helpers.

## Related Layers

Middleware is attached to [`agents`](../agents/README.md), often controls
[`tools`](../tools/README.md), and can shape [`context`](../context/README.md).
