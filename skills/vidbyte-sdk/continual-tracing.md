<!--
Context Protocol Header

Description:
    SDK sub-skill for the continual trace agent: how to use it and how to modify it safely.
Purpose:
    Documents the trace_option API, the middleware-driven architecture, the schema
    contracts, and the invariants any change must preserve.
Architecture and Key Functions:
    - Usage: trace_option=TraceOption.continual(schema) on BaseAgent.
    - Internals: ContinualTraceAgent + UpdateTraceTool + ContinualTraceMiddleware.
Relation to the codebase as a whole:
    Sub-skill referenced by skills/vidbyte-sdk/SKILL.md. Pairs with handoff.md and
    middleware.md.
-->

# Continual Tracing

## What it is

A continual trace produces a structured, continually-updated artifact describing a
running agent's goal, work, mistakes, and status — a live handoff document. It is
**opt-in** via one option and is realized as **runtime middleware**, not a change to the
model/tool loop.

```python
from vidbyte import Agent, TraceOption
from vidbyte.trace.continual import ActionTrace

agent = Agent(
    name="worker",
    system_prompt="...",
    runner=runner,
    trace_option=TraceOption.continual(ActionTrace, every_n_iterations=5, max_trace_iterations=3),
)
reply = await agent.arun("task")
artifact = reply.metadata["trace"]          # the accumulated dict
meta = reply.metadata["trace_metadata"]     # {mode, schema, update_count, error_count, last_error?}
agent.last_trace                            # same artifact, mirrors agent.last_handoff
```

`TraceOption.continual(schema)` accepts a Pydantic `BaseModel` subclass (recommended —
typed and described), a `TraceSchema`, or a `{field: description}` mapping. Build agents
ad hoc with `AgentClient().continual_trace(schema)`.

## Architecture (do not bypass)

- `vidbyte/lib/dataclasses/trace.py` — `TraceField`/`TraceFieldType`/`TraceSchema`/`TraceOption`. Config contracts only; no behavior.
- `vidbyte/trace/continual/tools.py` — `UpdateTraceTool`: the only model-visible tool. It validates each provided value against its declared `TraceField.type` and, on mismatch, returns a `ToolResult.error("output shape mismatch: ...")` so the model self-corrects. Merge policy: **append** arrays (de-duplicating exact repeats), **deep-merge** objects, **replace** scalars, **drop** unknown keys, **preserve** omitted fields.
- `vidbyte/trace/continual/agent.py` — `ContinualTraceAgent(BaseAgent)`: a dedicated agent mirroring `HandoffAgent`. One pass per update; built via `from_source_agent` to reuse the source runner/provider; recursion-guarded (never carries a `trace_option`).
- `vidbyte/middleware/continual_trace.py` — `ContinualTraceMiddleware`: the injection seam. Runs an update at `after_iteration` every `every_n_iterations` and one final update at `after_run` (skipped if the last iteration was already traced, or when `ctx.error` is `CancelledError`/`TimeoutError` so a dead deadline does not start another model call). `fail_closed = False`.
- `vidbyte/agents/base.py` — `trace_option=` param, the non-linear-runtime guard, `_runtime_middleware()` injection, `fork` forwarding, and `last_trace`.
- `vidbyte/agents/runtime.py` — `_with_run_state_metadata` lifts `run_state["__result_metadata__"]` into the result. This is **generic and feature-agnostic**; do not import trace code into the runtime.

## Invariants any change must preserve

1. **The trace never enters the main agent context window.** The middleware only writes to `run_state` and returns `MiddlewareDecision.continue_()` without a `MiddlewareTransform`. Never inject the artifact into provider messages or the system prompt.
2. **Fail-open.** A trace failure must never abort or alter the main run. Keep `fail_closed = False` and the try/except in the update path; record errors in `trace_metadata`.
3. **Bounded cost.** Updates only at the interval plus one final pass; each pass is capped at `max_trace_iterations` (1–3). A terminal `CancelledError` or `TimeoutError` skips the final model call and only marks the artifact finalized.
4. **Linear runtime only.** Continual tracing is middleware; non-linear runtimes reject it at construction.
5. **Schema is authoritative.** Only declared fields are written; unknown keys are dropped, not errored.
6. **Append, do not clobber.** Array fields grow across updates. If you change merge semantics, update the tests in `tests/test_continual_trace.py` and `scripts/test-continual-trace.py`.

## Adding a prebuilt schema

Add a Pydantic model with described fields in `vidbyte/trace/continual/prebuilt.py`,
convert it with `TraceSchema.from_model(...)`, and export it from
`vidbyte/trace/continual/__init__.py` and `vidbyte/trace/__init__.py`. Give each field a
4–5 sentence description so the trace agent fills it well.

## Verify

`python scripts/test-continual-trace.py` and `python -m unittest tests.test_continual_trace`.
