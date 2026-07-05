<!--
Context Protocol Header

Description:
    Skill for maintaining and extending Vidbyte SDK tracing.
Purpose:
    Gives a file-by-file maintenance guide so an agent knows exactly which file
    to edit for a given tracing change and what else to update.
Architecture:
    - Responsibility matrix: change X -> edit file Y, also update Z.
    - Export checklist (three re-export layers).
    - Docs checklist (README, llms.txt, skill maintenance rules).
    - Do-not-cross lines that preserve tracing invariants.
Relations:
    Sub-skill of skills/tracing/SKILL.md. References every other tracing skill
    for the "why" behind each file.
-->

# Updating the Tracer

This skill is the file-by-file maintenance guide. For each kind of tracing
change, it says which file to edit and what else to update. The rule: **a change
not described in `docs/design/tracing-skills.md` should not be made without an
approved design**, and every tracing behavior change should update
`vidbyte/trace/README.md` and/or `llms.txt`.

## Responsibility Matrix

| You want to change... | Primary file to edit | Also update |
|-----------------------|----------------------|-------------|
| Add a `Trace.*` facade helper | `vidbyte/trace/base.py` | exports (see below) + `vidbyte/trace/README.md` + `llms.txt` |
| Add a detail preset (`minimal`/`default`/`verbose`/`diagnostic`) | `vidbyte/trace/profiles.py` (`_base_components`) | `vidbyte/trace/__init__.py` if new symbol + `vidbyte/trace/README.md` + `trace-profiles.md` + `trace-types.md` |
| Add a role-oriented preset (`production`/`cost_monitoring`/etc.) | `vidbyte/trace/profiles.py` (new classmethod with hand-tuned `components` map) | same as above; remember to cover all 19 components in the map |
| Add a span kind | `vidbyte/trace/schema.py` (`SpanKind`) | `vidbyte/trace/providers/langsmith.py` (`_run_type`) + `vidbyte/trace/README.md` |
| Add a detail level | `vidbyte/trace/schema.py` (`TraceDetail`) + `vidbyte/trace/profiles.py` (`_DETAIL_ORDER`) | `trace-profiles.md` + `trace-types.md` |
| Add a component span spec (existing area) | `vidbyte/trace/components/<area>.py` | `vidbyte/trace/components/__init__.py` if a new factory class + `vidbyte/trace/controller.py` `_spec_from_name` if a new name prefix + `trace-components.md` + `skills/sdk/SKILL.md` & `skills/vidbyte-sdk/SKILL.md` "Semantic Trace Components" |
| Add a new component area (e.g. `pipelines`, `evals`) | new `vidbyte/trace/components/<area>.py` + `vidbyte/trace/components/__init__.py` (export) + `vidbyte/trace/profiles.py` (`_COMPONENTS` set + every role-oriented preset's `components` map) | `trace-components.md` + `trace-profiles.md` (component list) + `skills/sdk/SKILL.md` & `skills/vidbyte-sdk/SKILL.md` "Semantic Trace Components" + `vidbyte/trace/README.md` |
| Add a parent policy | `vidbyte/trace/schema.py` (`ParentPolicy`) + `vidbyte/trace/controller.py` (`_provider_parent`) | `trace-controller-and-session.md` |
| Add a provider translator | `vidbyte/trace/providers/<name>.py` + `vidbyte/trace/providers/__init__.py` (export) + `vidbyte/trace/base.py` (`_TraceFactory.resolve_translator` name branch) | `trace-providers.md` |
| Add an external provider adapter | `vidbyte/providers/tracing/<name>.py` + `vidbyte/providers/tracing/__init__.py` (export) + `vidbyte/trace/base.py` (`Trace.<name>(...)` helper) | `vidbyte/trace/README.md` + `trace-providers.md` + `trace-types.md` |
| Emit a new runtime span (direct) | `vidbyte/agents/runtime.py` via `self._tracer.start_span(name, ...)` | a matching spec in `vidbyte/trace/components/` + `vidbyte/trace/controller.py` `_spec_from_name` if a new prefix + `trace-components.md` |
| Emit a new semantic-only runtime span | `vidbyte/agents/runtime.py` via `self._start_semantic_span(name, ...)` (only fires for `TraceController`) | same as above; note it is suppressed for raw provider tracers |
| Add a continual trace schema | `vidbyte/trace/continual/prebuilt.py` + `vidbyte/trace/continual/__init__.py` + `vidbyte/trace/__init__.py` | `skills/vidbyte-sdk/continual-tracing.md` |
| Change session grouping | `vidbyte/trace/session.py` (+ `vidbyte/trace/base.py` `Trace.session`/`Trace.langsmith_session` if the API changes) | `trace-controller-and-session.md` + `vidbyte/trace/README.md` |

## Export Checklist

Tracing public symbols flow through **three re-export layers**. When you add a
public symbol, update all three that should carry it:

1. **Module `__init__.py`** — the immediate package:
   - `vidbyte/trace/components/__init__.py` for component factories.
   - `vidbyte/trace/providers/__init__.py` for translators.
   - `vidbyte/providers/tracing/__init__.py` for external adapters.
   - `vidbyte/trace/continual/__init__.py` for continual presets/schemas.
2. **`vidbyte/trace/__init__.py`** — the trace package surface. It re-exports
   `Trace`, `TraceProfile`, `TraceController`, `TraceComponentSettings`,
   `DebugTracer`, `SessionTraceController`, `SpanKind`, `SpanSpec`,
   `TraceDetail`, `ParentPolicy`, `SemanticSpanContext`, `ContinualTracer`,
   `ContinualTraceAgent`, `ContinualTraceMiddleware`, `ActionTrace`, plus the
   `vidbyte.lib.dataclasses.trace` contracts (`TraceField`, `TraceFieldType`,
   `TraceMode`, `TraceOption`, `TraceSchema`). Note: `SessionTracer` is no longer
   exported — the semantic `SessionTraceController` is the only session wrapper.
3. **`vidbyte/__init__.py`** — the top-level package. It re-exports the user-facing
   subset: `Trace`, `TraceProfile`, `TraceDetail`, `SpanKind`, `DebugTracer`,
   `SessionTraceController`, `TraceController`, `TraceComponentSettings`,
   `ContinualTracer`, `ContinualTraceAgent`, `ContinualTraceMiddleware`,
   `ActionTrace`, `TraceOption`, `TraceSchema`,
   `NullTracer`, `TracerBase`, `TracerConfigurationError`.

Add a symbol to the top-level only if it is meant for direct
`from vidbyte import ...` use; keep internal helpers at the module layer.

## Docs Checklist

When public tracing behavior changes, update:

- `vidbyte/trace/README.md` — the canonical module README (profiles, helpers,
  session usage, key modules).
- `llms.txt` — the repo's machine-readable context file (semantic trace profile
  guidance lives here).
- `skills/sdk/SKILL.md` and `skills/vidbyte-sdk/SKILL.md` — the "Semantic Trace
  Components" section lists the component files; update it when the component
  file list changes.
- The relevant `skills/tracing/*.md` skill from the matrix above.

## Do-Not-Cross Lines

These invariants keep the tracing layer clean. Violating them requires an
approved design doc.

1. **Translators must not call external SDKs.** `vidbyte/trace/providers/` only
   translates semantic spans into provider fields. All external client calls live
   in `vidbyte/providers/tracing/`.
2. **The runtime must not import trace feature code.** `vidbyte/agents/runtime.py`
   emits spans **by name** and uses `_is_semantic_tracer` (a duck-type check for
   `inner`/`profile`/`translator` attributes) to decide whether to emit
   `agent.stop` — it never imports `vidbyte.trace` during agent initialization.
   Provider-neutral payload enrichment (e.g. `llm.call`/`tool.call` input fields)
   stays in `vidbyte/agents/runtime.py`.
3. **Continual trace must never enter the main context window.** The
   `trace_option=` path is middleware that writes to `run_state` only; it never
   injects the artifact into provider messages or the system prompt. The only
   sanctioned exception is `TraceReplacementCompactionMiddleware` when explicitly
   attached. See `skills/vidbyte-sdk/continual-tracing.md` for the full
   invariants.
4. **Tracing fails open.** Trace errors must never abort or alter the main agent
   run. Provider adapters swallow errors (or record them in `last_error` /
   `trace_metadata`); `strict` modes are opt-in.
5. **`trace=` and `trace_option=` are independent.** Do not wire one into the
   other. `trace=` is observability spans; `trace_option=` is a continual
   artifact via middleware.

## Common Change Recipes

### Add a `Trace.langsmith_minimal` helper

```python
# vidbyte/trace/base.py
@staticmethod
def langsmith_minimal(api_key=None, project=None, endpoint=None, strict=False, include_runtime_info=False) -> TraceController:
    # Builds a LangSmith tracer wrapped in the minimal semantic profile.
    return Trace.profile(
        Trace.langsmith(api_key=api_key, project=project, endpoint=endpoint, strict=strict, include_runtime_info=include_runtime_info),
        profile=TraceProfile.minimal(),
        provider="langsmith",
    )
```

Then: add to `vidbyte/trace/__init__.py` only if a new symbol is introduced (here
it reuses `Trace`, so no new export). Update `vidbyte/trace/README.md` and
`llms.txt` with the helper and a snippet.

### Add a new component span spec

```python
# vidbyte/trace/components/runtimes.py
class GraphRuntimeTrace:
    """Factory for graph runtime spans."""

    @staticmethod
    def node(**attributes: Any) -> SpanSpec:
        # Describes one graph node execution.
        return SpanSpec("runtime.graph.node", SpanKind.CHAIN, "graph", TraceDetail.VERBOSE, ParentPolicy.CURRENT, attributes)
```

Then: export `GraphRuntimeTrace` from
`vidbyte/trace/components/__init__.py`; add a `graph` entry to `_COMPONENTS` in
`vidbyte/trace/profiles.py`; add a `"runtime.graph."` prefix branch to
`_spec_from_name` in `vidbyte/trace/controller.py`; update
`trace-components.md`, `trace-profiles.md` (component list), and the "Semantic
Trace Components" section of `skills/sdk/SKILL.md` and
`skills/vidbyte-sdk/SKILL.md`.

### Add a new provider adapter

```python
# vidbyte/providers/tracing/<name>.py
class MyProviderTracer(TracerBase):
    def __init__(self, *, api_key=None, **kwargs) -> None:
        # Resolve credentials from kwargs first, then env vars.
        ...
    # implement start_trace/end_trace/start_span/end_span
```

Then: re-export from `vidbyte/providers/tracing/__init__.py`; add a
`Trace.myprovider(...)` `@staticmethod` in `vidbyte/trace/base.py` (import the
adapter lazily inside the method); optionally add a translator in
`vidbyte/trace/providers/` and register its name in
`_TraceFactory.resolve_translator`; update `vidbyte/trace/README.md`,
`llms.txt`, `trace-providers.md`, and `trace-types.md`.

## Verify

There is no dedicated tracing test command, but after any tracing change run:

```bash
python -m compileall vidbyte
python -m unittest tests.test_semantic_tracing tests.test_tracing tests.test_trace_facade tests.test_aggregate_agent
python -m unittest discover -s tests
```

(Clear provider API-key environment variables first if the full suite runs, so
provider-discovery tests stay deterministic.)
