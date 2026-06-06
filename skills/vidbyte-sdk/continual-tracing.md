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
artifact = reply.metadata["trace"]          # the accumulated dict (primary trace)
meta = reply.metadata["trace_metadata"]     # {mode, schema, update_count, error_count, last_error?}
agent.last_trace                            # same artifact, mirrors agent.last_handoff
```

`TraceOption.continual(schema)` accepts a Pydantic `BaseModel` subclass (recommended —
typed and described), a `TraceSchema`, or a `{field: description}` mapping. Build agents
ad hoc with `AgentClient().continual_trace(schema)`.

Eight prebuilt schemas ship under `vidbyte.trace.continual`, each a lens over a run:
`ActionTrace`, `PlanTrace`, `ReasoningTrace`, `HistoryTrace`, `ToolTrace`,
`DecisionTrace`, `ArtifactTrace`, `KnowledgeTrace`.

### Multiple traces

`trace_option=` also accepts a sequence of `TraceOption`s. One
`ContinualTraceMiddleware` is attached per option; each keeps its own schedule and
artifact, and each runs as its own bounded trace-agent pass (cost stacks linearly).

```python
trace_option=[TraceOption.continual(PlanTrace), TraceOption.continual(ReasoningTrace)]
# reply.metadata["traces"]          == {"plan_trace": {...}, "reasoning_trace": {...}}
# reply.metadata["traces_metadata"] == {"plan_trace": {...}, "reasoning_trace": {...}}
# agent.last_traces                 == that map
```

The first option is the **primary**: its artifact/summary are mirrored to the legacy
`metadata["trace"]` / `metadata["trace_metadata"]` keys and `agent.last_trace`, so
single-trace consumers are unaffected. Schema names must be unique within one agent
(they key the output map); duplicates raise `ConfigurationError` at construction.

## Architecture (do not bypass)

- `vidbyte/lib/dataclasses/trace.py` — `TraceField`/`TraceFieldType`/`TraceSchema`/`TraceOption`. Config contracts only; no behavior.
- `vidbyte/trace/continual/tools.py` — `UpdateTraceTool`: the only model-visible tool. It validates each provided value against its declared `TraceField.type` and, on mismatch, returns a `ToolResult.error("output shape mismatch: ...")` so the model self-corrects. Merge policy: **append** arrays (de-duplicating exact repeats), **deep-merge** objects, **replace** scalars, **drop** unknown keys, **preserve** omitted fields.
- `vidbyte/trace/continual/agent.py` — `ContinualTraceAgent(BaseAgent)`: a dedicated agent mirroring `HandoffAgent`. One pass per update; built via `from_source_agent` to reuse the source runner/provider; recursion-guarded (never carries a `trace_option`).
- `vidbyte/trace/continual/middleware.py` — `ContinualTraceMiddleware`: the injection seam. Runs an update at `after_iteration` every `every_n_iterations` and one final update at `after_run` (skipped if the last iteration was already traced). `fail_closed = False`. Multi-instance-safe: keys its `run_state` by `(class, schema_name)` and publishes into `traces`/`traces_metadata` maps, mirroring the flat `trace`/`trace_metadata` keys only when `primary=True`.
- `vidbyte/trace/continual/prebuilt/` — one module per prebuilt schema, re-exported from the package `__init__`.
- `vidbyte/agents/base.py` — `trace_option=` accepts a `TraceOption` or a sequence; `_normalize_trace_options` validates and rejects duplicate schema names; `_runtime_middleware()` injects one middleware per enabled option (first is primary); `fork` forwards the full set; `last_trace` (primary) and `last_traces` (full map).
- `vidbyte/agents/runtime.py` — `_with_run_state_metadata` lifts `run_state["__result_metadata__"]` into the result. This is **generic and feature-agnostic**; do not import trace code into the runtime.

## Invariants any change must preserve

1. **The trace never enters the main agent context window.** The middleware only writes to `run_state` and returns `MiddlewareDecision.continue_()` without a `MiddlewareTransform`. Never inject the artifact into provider messages or the system prompt.
2. **Fail-open.** A trace failure must never abort or alter the main run. Keep `fail_closed = False` and the try/except in the update path; record errors in `trace_metadata`.
3. **Bounded cost.** Updates only at the interval plus one final pass; each pass is capped at `max_trace_iterations` (1–3).
4. **Linear runtime only.** Continual tracing is middleware; non-linear runtimes reject it at construction.
5. **Schema is authoritative.** Only declared fields are written; unknown keys are dropped, not errored.
6. **Append, do not clobber.** Array fields grow across updates. If you change merge semantics, update the tests in `tests/test_continual_trace.py` and `scripts/test-continual-trace.py`.

## Adding a prebuilt schema

Add a new module under `vidbyte/trace/continual/prebuilt/` (one schema per module)
holding a Pydantic model with described fields, convert it with
`TraceSchema.from_model(..., name="snake_case")`, then re-export the schema and its
`*Model` from `prebuilt/__init__.py`, `vidbyte/trace/continual/__init__.py`,
`vidbyte/trace/__init__.py`, and root `vidbyte/__init__.py`. Give each field a
`title=` string (human-readable name), a `min_length=` constraint (`min_length=1` for
required `str` fields, `min_length=0` for optional `str` and `list` fields; omit for
`int` and `dict`), and a **4–5 sentence description** that coherently explains both the
field's meaning and its intent: what it contains, how to populate it (what goes in each
entry), when to append versus overwrite, what value it provides for a handoff reader, and
any precision or edge-case guidance. Choose each field's type to get the right merge
behavior: `list[...]` appends, `dict` deep-merges, scalars (`str`/`int`/`bool`) replace.
Keep schema names unique. Update `tests/test_continual_trace.py` and
`scripts/test-continual-trace.py`.

## Verify

`python scripts/test-continual-trace.py` and `python -m unittest tests.test_continual_trace`.
