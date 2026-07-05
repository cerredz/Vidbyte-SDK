<!--
Context Protocol Header

Description:
    Skill for the TraceController internals and session tracing in the Vidbyte SDK.
Purpose:
    Explains how the semantic controller filters, translates, and parents spans,
    and how session tracing groups multiple agent runs under one root.
Architecture:
    - Covers vidbyte/trace/controller.py (TraceController, _SPAN_STACK,
      _spec_from_name, _provider_parent, suppression, as_trace, nested agent.run).
    - Covers vidbyte/trace/session.py (SessionTracer legacy path,
      SessionTraceController semantic path, TraceSession / _SessionContext /
      _AsyncSessionContext).
    - References vidbyte/trace/schema.py (ParentPolicy, SemanticSpanContext).
Relations:
    Sub-skill of skills/tracing/SKILL.md. Pairs with trace-profiles.md (allows()),
    trace-providers.md (translator), and trace-components.md (span specs).
-->

# Trace Controller and Session Tracing

`TraceController` is the heart of the semantic layer. It sits between the agent
runtime (which emits spans by name) and a low-level `TracerBase` (debug, a
provider adapter, null, or custom). It **filters** spans via the profile,
**translates** them via a provider translator, and **parents** them via an
async-local stack. Session tracing extends this to group multiple agent runs
under one root.

## `TraceController` Role

```python
class TraceController(TracerBase):
    def __init__(self, inner, profile=None, translator=None) -> None:
        self.inner = inner or NullTracer()
        self.profile = profile or TraceProfile.default()
        self.translator = translator or GenericProviderTranslator()
```

It implements the full `TracerBase` contract (`start_trace`/`end_trace`/
`start_span`/`end_span`) but delegates the actual span lifecycle to `inner`. Its
own job is filtering, translation, and parent resolution.

## The Context-Local Span Stack

Parent resolution is **async-local**, not call-stack based:

```python
_SPAN_STACK: ContextVar[tuple[SemanticSpanContext, ...]] = ContextVar(
    "vidbyte_trace_span_stack", default=()
)
```

- `_push_context(ctx)` appends to the tuple stored in the `ContextVar`.
- `_pop_context(ctx)` removes that exact context object (identity comparison) if
  present.
- Each async task sees its own stack, so concurrent agent runs do not steal each
  other's parents.

`SemanticSpanContext` (a `SpanContext` subclass) carries three things:
`provider_context` (the handle returned by `inner`), `spec` (the `SpanSpec`),
and `suppressed` (whether the profile rejected this span).

## Parent Resolution — `ParentPolicy`

`ParentPolicy` (`vidbyte/trace/schema.py`) declares how a span's parent is
resolved:

| Policy | Meaning |
|--------|---------|
| `EXPLICIT` | Use the `parent=` argument passed to `start_span`. |
| `CURRENT` | Use the nearest open non-suppressed span on the stack (default). |
| `AGENT` | Attach to the active agent root. |
| `RUNTIME_ITERATION` | Attach to the active runtime iteration span. |
| `AGGREGATE` | Attach to the active aggregate span. |
| `SESSION` | Attach to the active session root. |
| `ROOT` | No parent — this span is a root. |

`_provider_parent(explicit, policy)` resolves it:

1. If an explicit parent is given, unwrap it (return its `provider_context` if it
   is a `SemanticSpanContext`, else the raw context).
2. If `policy is ROOT`, return `None`.
3. Otherwise scan the stack from newest to oldest and return the first
   non-suppressed context that has a `provider_context`.

## Name-Prefix Routing — `_spec_from_name`

The runtime emits spans by name (e.g. `"llm.call"`). The controller maps each
name to a component, kind, and detail by prefix:

| Name prefix | Kind | Component | Detail |
|-------------|------|-----------|--------|
| `llm.` | LLM | `agents` | MINIMAL |
| `tool.` | TOOL | `tools` | MINIMAL |
| `parser.` | PARSER | `parsers` | STANDARD |
| `context.` | PROMPT | `context` | VERBOSE |
| `algorithm.` | CHAIN | `algorithms` | VERBOSE |
| `runtime.` | CHAIN | `runtimes` | VERBOSE |
| `middleware.` | CHAIN | `middleware` | VERBOSE |
| `aggregate.` | CHAIN | `aggregate` | VERBOSE |
| `session.` | CHAIN | `sessions` | STANDARD |
| `agent.` | CHAIN | `agents` | STANDARD for `agent.stop`, else MINIMAL |
| (other) | CHAIN | `core` | MINIMAL |

The `parent_policy` is set to `ROOT` when the span is a root trace, else
`CURRENT`. This routing must stay in sync with the component factories in
`vidbyte/trace/components/` (see `trace-components.md`).

## Suppression and the `as_trace` Flag

`open_span(spec, parent=None, *, as_trace=False)` is the single entry point:

1. **Sanitize**: `_sanitize_spec` applies `safe_trace_value` with the profile's
   `max_chars` and `redact` settings (see `trace-profiles.md`).
2. **Filter**: if `profile.allows(normalized)` is `False`, push a **suppressed**
   `SemanticSpanContext` (`suppressed=True`, no `provider_context`) and return
   it. No call to `inner` is made.
3. **Translate**: `translator.translate_start(normalized)` builds the
   provider-facing `ProviderSpanPayload` (name + attributes).
4. **Parent**: resolve the provider parent via `_provider_parent`.
5. **Delegate**: if `as_trace` is `True`, call `inner.start_trace(payload.name,
   **payload.attributes)`; otherwise `inner.start_span(payload.name,
   parent=provider_parent, **payload.attributes)`.
6. **Push** the resulting `SemanticSpanContext` (with `provider_context`,
   `spec`, `suppressed=False`, `metadata["as_trace"]=as_trace`).

`end_trace`/`end_span` check `suppressed`: a suppressed context just pops off the
stack without calling `inner`. The `as_trace` flag controls whether the end call
goes to `inner.end_trace` or `inner.end_span`.

## `start_trace` vs `start_span`

`start_trace(name, **attributes)`:
- If `name == "agent.run"` and there is already an active provider parent on the
  stack, open it as a **child span** (`as_trace=False`) — this is the nested
  agent case (see below).
- Otherwise open a **root trace** (`as_trace=True`, `parent=None`).

`start_span(name, parent=None, **attributes)` always opens a child span
(`as_trace=False`) under the explicit or current parent.

## Nested `agent.run`

When one agent is run inside another agent's trace (e.g. an aggregate agent, a
handoff, or a sub-agent), a second `agent.run` would normally create a second
root. The controller avoids this: if `start_trace("agent.run", ...)` is called
while `_has_active_provider_parent()` is true, it opens as a child span instead
of a new root. `_has_active_provider_parent()` returns `True` when any
non-suppressed context on the stack has a `provider_context`.

This keeps nested agent work under the existing trace tree.

## Session Tracing

Session tracing groups multiple independent `agent.run` calls under one shared
root so a multi-step workflow appears as one trace. It is implemented by
`SessionTraceController` (`vidbyte/trace/session.py`), a `TraceController`
subclass. There is no longer a separate legacy session wrapper — the semantic
session controller is the only path.

### `SessionTraceController`

The session root is itself a semantic span (component `sessions`, detail
`STANDARD`, policy `ROOT`):

```python
controller = SessionTraceController(inner, profile=profile, translator=translator, name="workflow")
```

Session state is stored on a **plain instance attribute**
(`self._session_root: SpanContext | None = None`), not a `ContextVar`. This
means each controller instance tracks one session — a single controller cannot
run concurrent interleaved sessions. Use one controller per concurrent session.

- `begin_session(name=None, **attributes)` builds a session `SpanSpec` and opens
  it via `open_span(spec, as_trace=True)`. Raises `ConfigurationError` if a
  session is already active on this controller.
- While the session root is open, `start_trace("agent.run", ...)` is redirected
  to `start_span("agent.run", parent=root, ...)` — child agents become child
  spans under the session root. `end_trace` for a child becomes `end_span`.
- `end_session(output=None, error=None)` closes the root via `end_trace` and
  clears `self._session_root = None` (try/finally so it clears even on error).
- `session(name=None, **attributes)` returns a **sync** context manager
  (`_SessionContext`); `async_session(...)` returns an **async** context manager
  (`_AsyncSessionContext`).

### `Trace.session(...)` and `Trace.langsmith_session(...)`

`Trace.session(inner, name=None, profile=None, provider=None)` always returns a
`SessionTraceController` — it resolves the inner tracer, profile, translator,
and optional `name` and constructs the controller directly. There is no
`default_name`/`default_attributes` legacy path.

`Trace.langsmith_session(api_key=..., project=..., name=..., profile=...)` builds
a `LangSmithTracer` and passes it to `Trace.session(inner, name=name,
profile=profile or TraceProfile.default(), provider="langsmith")`.

## Code Snippets

### Semantic session (debug inner)

```python
from vidbyte import Agent, Trace, TraceProfile

events = []
trace = Trace.session(Trace.debug(events), name="workflow", profile=TraceProfile.verbose())

agent_a = Agent(name="planner", system_prompt="Plan.", runner=r1, trace=trace)
agent_b = Agent(name="worker", system_prompt="Execute.", runner=r2, trace=trace)

with trace.session("workflow"):
    await agent_a.arun("Plan.")
    await agent_b.arun("Execute.")
```

### LangSmith session

```python
from vidbyte import Trace

trace = Trace.langsmith_session(api_key="...", project="sdk", name="workflow")
```

### Async session

```python
trace = Trace.session(Trace.debug([]), name="workflow", profile=TraceProfile.default())

async with trace.async_session("workflow"):
    await agent_a.arun("Plan.")
    await agent_b.arun("Execute.")
```
