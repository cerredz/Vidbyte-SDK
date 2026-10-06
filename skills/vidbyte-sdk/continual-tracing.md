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

- `vidbyte/lib/dataclasses/trace.py` — `TraceField`/`TraceFieldType`/`TraceSchema`/`TraceOption`. Config contracts only; no behavior. An OBJECT field can declare `fields: Mapping[str, TraceField]` and an ARRAY field can declare `items: TraceField` — real typed nested subfields instead of only a prose-described shape. `TraceSchema.from_model` builds this automatically from a nested `BaseModel`/`list[BaseModel]` annotation; nesting is capped at `MAX_TRACE_FIELD_NESTING_DEPTH` (`vidbyte/lib/constants/trace.py`).
- `vidbyte/tools/continual_trace.py` — `UpdateTraceTool` (re-exported by the legacy path `vidbyte/trace/continual/tools.py`): the only model-visible tool. It validates each provided value against its declared `TraceField.type`, recursing into declared `fields`/`items` when present, and on mismatch returns a `ToolResult.error("output shape mismatch: ...")` so the model self-corrects. Merge policy: **append** arrays (de-duplicating exact repeats), **shallow-merge** objects one key at a time (never recursively), **replace** scalars, **drop** unknown keys, **preserve** omitted fields. This is unchanged by nested `fields`/`items` — see the invariant below.
- `vidbyte/trace/continual/agent.py` — `ContinualTraceAgent(BaseAgent)`: a dedicated agent mirroring `HandoffAgent`. One pass per update; built via `from_source_agent` to reuse the source runner/provider; recursion-guarded (never carries a `trace_option`).
- `vidbyte/trace/continual/middleware.py` — `ContinualTraceMiddleware`: the injection seam. Runs an update at `after_iteration` every `every_n_iterations` and one final update at `after_run` (skipped if the last iteration was already traced). `fail_closed = False`.
- `vidbyte/agents/base.py` — `trace_option=` param, the non-linear-runtime guard, `_runtime_middleware()` injection, `fork` forwarding, and `last_trace`.
- `vidbyte/agents/runtime.py` — `_with_run_state_metadata` lifts `run_state["__result_metadata__"]` into the result. This is **generic and feature-agnostic**; do not import trace code into the runtime.

## Invariants any change must preserve

1. **The trace never enters the main agent context window.** The middleware only writes to `run_state` and returns `MiddlewareDecision.continue_()` without a `MiddlewareTransform`. Never inject the artifact into provider messages or the system prompt.
2. **Fail-open.** A trace failure must never abort or alter the main run. Keep `fail_closed = False` and the try/except in the update path; record errors in `trace_metadata`.
3. **Bounded cost.** Updates only at the interval plus one final pass; each pass is capped at `max_trace_iterations` (1–3).
4. **Linear runtime only.** Continual tracing is middleware; non-linear runtimes reject it at construction.
5. **Schema is authoritative.** Only declared fields are written; unknown keys are dropped, not errored.
6. **Append, do not clobber — but only a top-level ARRAY field actually does.** A field's own top-level `ARRAY` type is what grows across updates via `_append_unique`. An `OBJECT` field's merge is a one-level shallow key-union: a sub-key the update omits keeps its prior value, but a sub-key the update *does* include — even an `ARRAY`-shaped one — is replaced with its new value whole, never merged element-wise with the old one. So a nested `ARRAY`-shaped subfield only loses its history when an update explicitly resends that specific subfield; declaring nested `fields`/`items` (see below) only changes what shape is validated and shown to the model, it does not add append behavior one level down. Anything meant to accumulate incrementally across separate trace-agent passes must be its own top-level `ARRAY` field. If you change merge semantics, update the tests in `tests/test_continual_trace.py` and `scripts/test-continual-trace.py`.

## Nested subfield/item shape

An `OBJECT` field can declare `fields: Mapping[str, TraceField]` and an `ARRAY` field can
declare `items: TraceField`, so the model sees real JSON Schema `properties`/`items`
instead of only a prose "Shape: {...}" description, and `UpdateTraceTool` validates
incoming updates against that nested shape recursively. `TraceSchema.from_model` builds
this automatically: annotate a field with a nested `BaseModel` (for `OBJECT`) or
`list[SubModel]` (for `ARRAY`) instead of `dict[str, Any]`/`list[dict[str, Any]]`, and
give every field on that submodel its own `Field(description=...)`, the same requirement
already enforced at the top level. See `HierarchicalTaskTreeTrace`/`CalibrationTrace`/etc.
in `vidbyte/trace/continual/prebuilt.py` for worked examples. This is purely additive —
`dict[str, Any]`/`list[dict[str, Any]]` fields keep working exactly as before, opaque and
untyped past their own top-level shape.

## Adding a prebuilt schema

Add a Pydantic model with described fields in `vidbyte/trace/continual/prebuilt.py`,
convert it with `TraceSchema.from_model(...)`, and export it from
`vidbyte/trace/continual/__init__.py`, `vidbyte/trace/__init__.py`, and `vidbyte/__init__.py`.
Give each field a 4–5 sentence description so the trace agent fills it well, and prefer a
nested submodel over `dict[str, Any]` whenever a field has real internal structure worth
declaring rather than only describing in prose.

## Verify

`python scripts/test-continual-trace.py` and `python -m unittest tests.test_continual_trace`.
