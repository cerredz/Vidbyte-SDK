# Middleware

## Folder Intent

This folder owns deterministic runtime policy around agent loops: lifecycle hooks, middleware decisions, built-in safety controls, and compaction integration.

## Non-Goals

Do not put model provider calls, tool implementation details, or agent construction policy here. Middleware should observe, transform, delay, abort, or annotate runtime flow.

## Usage

```python
from vidbyte.middleware import AgentMiddleware
from vidbyte.lib.dataclasses.middleware import MiddlewareDecision

class StopOnEmptyPrompt(AgentMiddleware):
    async def before_run(self, ctx):
        if not str(ctx.message).strip():
            return MiddlewareDecision.abort("empty_prompt")
        return MiddlewareDecision.continue_()
```

## File Index

- `__init__.py`: Exports public agent runtime middleware contracts and built-ins. Gives SDK users a concise import path for creating and attaching runtime middleware to direct text agents. Key symbols: AgentMiddleware, AuditLogMiddleware, CanaryTripwireMiddleware, CircuitBreakerMiddleware, CircuitState, ConfusedDeputyGuardMiddleware.
- `base.py`: Defines the public base class for agent runtime middleware. Lets SDK users create middleware by subclassing one class and overriding only the runtime lifecycle hooks they need. Key symbols: AgentMiddleware.
- `continual_trace.py`: Implements continual trace scheduling as agent runtime middleware. Injects continual trace updates at fixed lifecycle points (every N iterations and once at run end), accumulating the artifact in run_state and publishing it for the runtime to surface, while never writing the trace into the context window. Key symbols: ContinualTraceMiddleware, RESULT_METADATA_KEY.
- `pipeline.py`: Implements ordered middleware hook dispatch for agent runtime middleware. Centralizes middleware decision handling, sleeps, exception policy, and metadata events so AgentRuntime remains focused on the model/tool loop. Key symbols: MiddlewarePipeline.

## Subfolder Routing

- `builtins/`: Ready-made runtime policies such as budgets, retry, circuit breaking, and safety filters.
- `compaction/`: Context compaction engine, strategies, and trace rendering.

## Logs

- 2026-07-07: Fail-open and fail-closed behavior in the pipeline is a runtime safety boundary.
- 2026-07-07: This README is part of the agentic-engineering documentation pass described in `docs/design/agentic-engineering-principles-agents-middleware-tools.md`.

## Related Layers

- `vidbyte/agents`: executable agent construction and runtime selection.
- `vidbyte/middleware`: deterministic runtime policy around agent loops.
- `vidbyte/tools`: model-callable tool contracts and execution helpers.
- `vidbyte/lib`: shared dataclasses, registries, enums, errors, and low-level utilities.
