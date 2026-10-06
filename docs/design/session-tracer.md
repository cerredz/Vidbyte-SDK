# Design Doc: Session Tracer

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-29
**Last Updated:** 2026-06-29

---

## 1. Overview

This feature adds a reusable SDK-owned `SessionTracer` that groups multiple agent runs under one parent trace while preserving the existing `TracerBase` contract. Today this behavior exists in `vidbyte-harnesses` as harness-local code; moving it into `vidbyte-sdk` lets users compose multi-agent workflows with one shared trace object instead of implementing their own wrapper.

---

## 2. Goals & Non-Goals

### Goals

- Add a public `SessionTracer` implementation under `vidbyte.trace`.
- Let callers wrap any existing `TracerBase` instance in a session-aware tracer.
- Add a LangSmith convenience factory that returns a session-aware tracer backed by `LangSmithTracer`.
- Support manual session lifecycle with `begin_session(...)` and `end_session(...)`.
- Support sync and async context-manager lifecycle through `session(...)`.
- While a session is active, convert agent-level `start_trace("agent.run", ...)` calls into child spans under the session root.
- Preserve normal non-session behavior: outside a session, `start_trace` and `end_trace` delegate to the wrapped tracer as root traces.
- Preserve child `llm.call` and `tool.call` parentage under each `agent.run` span.
- Export `SessionTracer` from `vidbyte.trace` and root `vidbyte`.
- Document the session tracer in README and trace package docs.
- Preserve existing tracing APIs, including `Trace.langsmith(...)`, `Trace.debug(...)`, `trace=`, and `tracer=`.
- Thread an already-resolved tracer into SDK-native `AggregateAgent` child agents so a session tracer supplied to aggregate workflows is not silently dropped.

### Non-Goals

- Do not add default-agent-tracing payload changes such as tool input capture.
- Do not add new trace span types such as `agent.iteration`, `context.window`, or middleware decision spans.
- Do not modify `LangSmithTracer` run payloads, run type classification, flushing, endpoint behavior, or error handling.
- Do not replace `TracerBase` or change its abstract method signatures.
- Do not change pipeline execution semantics.
- Do not add new mandatory dependencies or optional dependency groups.
- Do not implement provider-specific session classes for Langfuse or Phoenix in this PR.
- Do not add test files or verification scripts under this no-tests workflow.

---

## 3. Background & Context

The SDK already has a provider-neutral tracing layer. `vidbyte.lib.tracing.TracerBase` defines `start_trace`, `end_trace`, `start_span`, and `end_span`; `NullTracer` provides no-op behavior; `BaseAgent` accepts `trace=` or `tracer=` and stores a resolved tracer instance; `BaseAgent.generate_reply()` opens one `agent.run` root trace; `AgentRuntime` emits `llm.call` and `tool.call` child spans using the `trace_context` passed from the agent.

Provider adapters live under `vidbyte.providers.tracing`. `LangSmithTracer` already creates root chain runs, child spans, and uses name-based run type classification. The public `Trace` facade in `vidbyte.trace.base` already exposes helpers such as `Trace.off()`, `Trace.debug()`, `Trace.langsmith(...)`, and `Trace.custom(...)`.

The missing reusable SDK abstraction is session grouping. The job-applier harness currently owns a local `SessionTracer` that wraps `LangSmithTracer`: `begin_session()` opens a root run, and while active, each agent's `start_trace("agent.run")` becomes `start_span(..., parent=session_root)`. That local implementation proves the shape, but each user or harness must copy the same wrapper to get multiple agents inside one LangSmith trace.

This change productizes that wrapper inside the SDK and keeps it provider-neutral. LangSmith gets a convenience factory because it is the immediate use case, but the core `SessionTracer` can wrap any `TracerBase`, including `Trace.debug()` for local inspection.

---

## 4. Requirements

### Functional Requirements

1. `SessionTracer` must implement `TracerBase`.
2. `SessionTracer` must wrap one inner `TracerBase`.
3. `Trace.session(inner, ...)` must return a `SessionTracer` around a caller-supplied tracer.
4. `Trace.langsmith_session(...)` must construct `LangSmithTracer` with forwarded LangSmith settings and return it wrapped in `SessionTracer`.
5. `SessionTracer.begin_session(name=None, **attributes)` must open one root trace on the inner tracer and return the root context.
6. `SessionTracer.end_session(output=None, error=None)` must close the active root trace on the inner tracer.
7. `SessionTracer.session(name=None, **attributes)` must return an object usable with both `with` and `async with`.
8. A session context manager must close the root with `error=<exception>` when the managed block exits with an exception.
9. A session context manager must close the root without error when the managed block exits normally.
10. `SessionTracer.in_session` must indicate whether the current execution context has an active session root.
11. `SessionTracer.root_context` must expose the active root context for the current execution context, or `None`.
12. Outside an active session, `SessionTracer.start_trace(...)` must delegate to `inner.start_trace(...)`.
13. Outside an active session, `SessionTracer.end_trace(...)` must delegate to `inner.end_trace(...)`.
14. Inside an active session, `SessionTracer.start_trace(...)` must delegate to `inner.start_span(..., parent=session_root, ...)`.
15. Inside an active session, `SessionTracer.end_trace(...)` must close child contexts with `inner.end_span(...)`.
16. Inside an active session, `SessionTracer.end_trace(session_root, ...)` must close the session root through `end_session(...)`.
17. Inside an active session, `SessionTracer.start_span(..., parent=None, ...)` must attach the span to the session root.
18. Inside an active session, `SessionTracer.start_span(..., parent=some_context, ...)` must preserve the explicit parent.
19. `SessionTracer.end_span(...)` must delegate to `inner.end_span(...)`.
20. `SessionTracer.begin_session(...)` must reject starting a second session in the same execution context with `ConfigurationError`.
21. Session state must be execution-context-local so separate async tasks can use the same `SessionTracer` without clobbering each other's active root.
22. Existing `Trace.langsmith(...)` behavior must remain unchanged.
23. Existing `BaseAgent(trace=...)` and `BaseAgent(tracer=...)` behavior must remain unchanged.
24. Root imports must support `from vidbyte import SessionTracer`.
25. Package imports must support `from vidbyte.trace import SessionTracer`.
26. `AggregateAgent` must accept the same resolved tracer instance through constructor/fork paths and pass it to proposer and aggregator child `BaseAgent`s that it constructs.
27. `BaseAgent._build_aggregate_agent()` must pass its resolved tracer to the internal `AggregateAgent` it builds for multi-model overloads.

### Non-Functional Requirements

- Performance: outside an active session, the wrapper should add only one `ContextVar.get()` and one delegation call per trace operation.
- Reliability: tracing remains best-effort according to the wrapped tracer. The session wrapper must not introduce network calls or provider-specific error handling.
- Concurrency: session root state must not be stored as one mutable `_root_ctx` shared across all async tasks.
- Compatibility: no existing public trace method, `TracerBase` signature, or provider adapter constructor may be removed or changed incompatibly.
- Security: the session wrapper must not inspect, log, print, persist, or redact trace attributes; sensitive-data handling remains owned by existing trace value sanitization and provider adapters.
- Maintainability: session logic must live in `vidbyte.trace`, not in harnesses, providers, agents runtime, or `vidbyte.lib.tracing`.

---

## 5. High-Level Design

The implementation adds `vidbyte/trace/session.py` with two classes: `SessionTracer` and `TraceSession`. `SessionTracer` is the reusable wrapper that implements `TracerBase`. `TraceSession` is a small sync/async context-manager object returned by `SessionTracer.session(...)`. The wrapper stores active session state in a `ContextVar`, which keeps root trace state local to the current sync or async execution context.

The `Trace` facade gets two new helper methods. `Trace.session(inner, ...)` wraps any `TracerBase` instance or class through the existing custom-tracer normalization path. `Trace.langsmith_session(...)` constructs the existing `LangSmithTracer` with the same arguments as `Trace.langsmith(...)`, then wraps it in `SessionTracer`.

The normal data flow becomes:

```text
User creates session tracer
  |
  v
Trace.langsmith_session(...) -> SessionTracer(inner=LangSmithTracer)
  |
  v
with trace.session("workflow.run", run_id="..."):
  |
  v
Agent(trace=trace).arun(...)
  |
  v
BaseAgent.start_trace("agent.run")
  |
  v
SessionTracer.start_trace(...) -> inner.start_span(parent=session_root)
  |
  v
AgentRuntime llm.call/tool.call spans attach under that agent.run span
```

The only agent-layer change is tracer propagation for SDK-native aggregation. `AggregateAgent` is already a `BaseAgent` subclass, but it currently constructs proposer and aggregator child agents without passing the parent tracer. This design adds `tracer`/`trace` support to `AggregateAgent` and threads the resolved tracer to child `BaseAgent`s. This is narrowly included because otherwise a user-supplied session tracer can be silently dropped by the SDK's own multi-agent path.

---

## 6. Detailed Design

### 6.1 Session Tracer Module

**File(s):** `vidbyte/trace/session.py`
**Type:** New file

#### What it does

Defines the provider-neutral session wrapper and context-manager object.

#### Interface / API

```python
class SessionTracer(TracerBase):
    def __init__(self, inner: type[TracerBase] | TracerBase, *, default_name: str = "session.run", default_attributes: Mapping[str, Any] | None = None) -> None: ...
    @property
    def inner(self) -> TracerBase: ...
    @property
    def in_session(self) -> bool: ...
    @property
    def root_context(self) -> SpanContext | None: ...
    def begin_session(self, name: str | None = None, **attributes: Any) -> SpanContext: ...
    def end_session(self, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def session(self, name: str | None = None, **attributes: Any) -> TraceSession: ...
    def start_trace(self, name: str, **attributes: Any) -> SpanContext: ...
    def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext: ...
    def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...

class TraceSession:
    def __enter__(self) -> SessionTracer: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool: ...
    async def __aenter__(self) -> SessionTracer: ...
    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: Any) -> bool: ...
```

#### Logic / Algorithm

1. `SessionTracer.__init__` normalizes the inner tracer by reusing `Trace.custom(...)` equivalent validation through an internal helper to avoid accepting non-tracer objects.
2. The class owns a `ContextVar` that stores the active root context for the current execution context.
3. `begin_session` checks the context variable; if a root already exists, it raises `ConfigurationError`.
4. `begin_session` merges `default_attributes` with call-specific attributes and opens `inner.start_trace(name or default_name, **merged_attributes)`.
5. `end_session` reads the active root; if none exists, it returns without raising.
6. `end_session` calls `inner.end_trace(root, output=output, error=error)` and clears the context variable.
7. `session(...)` returns a `TraceSession` that calls `begin_session` on enter and `end_session` on exit.
8. `start_trace` checks for an active root. If none exists, it delegates to `inner.start_trace`. If a root exists, it delegates to `inner.start_span(name, parent=root, **attributes)`.
9. `end_trace` checks for an active root. If none exists, it delegates to `inner.end_trace`. If the supplied context is the active root, it closes the root through `end_session`. Otherwise it delegates to `inner.end_span`.
10. `start_span` attaches parentless spans to the active root when one exists; explicit parents are preserved.
11. `end_span` delegates directly to `inner.end_span`.

#### Edge Cases & Error Handling

- Starting a nested session in the same execution context raises `ConfigurationError`.
- Ending a session when no session exists is a no-op to keep cleanup paths simple.
- Exceptions from the wrapped tracer propagate or are swallowed according to the wrapped tracer's existing behavior.
- The context-manager exit returns `False` so exceptions from user code are never suppressed.
- If a wrapped tracer is a class, it is instantiated with no arguments, matching existing `Trace.custom(...)` behavior.

---

### 6.2 Trace Facade Session Helpers

**File(s):** `vidbyte/trace/base.py`
**Type:** Modified

#### What it does

Adds public factory methods for generic and LangSmith-backed session tracers.

#### Interface / API

```python
class Trace:
    @staticmethod
    def session(inner: type[TracerBase] | TracerBase, *, default_name: str = "session.run", default_attributes: Mapping[str, Any] | None = None) -> SessionTracer: ...
    @staticmethod
    def langsmith_session(api_key: str | None = None, project: str | None = None, endpoint: str | None = None, strict: bool = False, include_runtime_info: bool = False, *, default_name: str = "session.run", default_attributes: Mapping[str, Any] | None = None) -> SessionTracer: ...
```

#### Logic / Algorithm

1. Import `SessionTracer` lazily or at module import from `vidbyte.trace.session`.
2. `Trace.session(...)` returns `SessionTracer(inner, default_name=..., default_attributes=...)`.
3. `Trace.langsmith_session(...)` builds `LangSmithTracer` with the same provider settings as `Trace.langsmith(...)`.
4. `Trace.langsmith_session(...)` returns `SessionTracer(langsmith_tracer, default_name=..., default_attributes=...)`.

#### Edge Cases & Error Handling

- Invalid inner tracer values raise `ConfigurationError`.
- Missing LangSmith dependency or credentials raise the existing `TracerConfigurationError` from `LangSmithTracer`.
- `Trace.langsmith(...)` remains unchanged and still returns a plain `LangSmithTracer`.

---

### 6.3 Trace Package Exports

**File(s):** `vidbyte/trace/__init__.py`
**Type:** Modified

#### What it does

Exports `SessionTracer` from the public trace package.

#### Interface / API

```python
from vidbyte.trace.session import SessionTracer

__all__ = [..., "SessionTracer", ...]
```

#### Logic / Algorithm

1. Import `SessionTracer`.
2. Add `"SessionTracer"` to `__all__`.

#### Edge Cases & Error Handling

- N/A - import-only change.

---

### 6.4 Root Package Exports

**File(s):** `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Makes the session tracer available from the root package.

#### Interface / API

```python
from vidbyte import SessionTracer
```

#### Logic / Algorithm

1. Import `SessionTracer` from `vidbyte.trace`.
2. Add `"SessionTracer"` to root `__all__`.

#### Edge Cases & Error Handling

- N/A - import-only change.

---

### 6.5 AggregateAgent Tracer Propagation

**File(s):** `vidbyte/agents/aggregation.py`
**Type:** Modified

#### What it does

Allows aggregate workflows to preserve a session tracer when `AggregateAgent` constructs proposer and aggregator child agents.

#### Interface / API

```python
class AggregateAgent(BaseAgent):
    def __init__(self, ..., tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None) -> None: ...
```

#### Logic / Algorithm

1. Add `tracer` and `trace` keyword parameters to `AggregateAgent.__init__`.
2. Pass them to `super().__init__(..., tracer=tracer, trace=trace)`.
3. When building proposer `BaseAgent`s, pass `tracer=self._tracer`.
4. When building the aggregator `BaseAgent`, pass `tracer=self._tracer`.
5. When forking an `AggregateAgent`, pass `tracer=self._tracer`.

#### Edge Cases & Error Handling

- Passing both `tracer` and `trace` to `AggregateAgent` reuses the existing `BaseAgent` conflict behavior and raises `ConfigurationError`.
- Caller-supplied proposer or aggregator objects are not modified; only child agents constructed by the SDK receive the tracer.

---

### 6.6 BaseAgent Aggregate Delegation

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Preserves a resolved session tracer when `BaseAgent` activates the native multi-model overload and delegates to an internal `AggregateAgent`.

#### Interface / API

```python
def _build_aggregate_agent(self) -> BaseAgent: ...
```

#### Logic / Algorithm

1. Add `tracer=self._tracer` to the internal `AggregateAgent(...)` construction.
2. Leave the rest of the aggregation plan unchanged.

#### Edge Cases & Error Handling

- No behavior changes for non-aggregate `BaseAgent` instances.
- No behavior changes when tracing is disabled, because `self._tracer` is already a `NullTracer`.

---

### 6.7 README Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents how users create one session tracer and pass it to multiple agents.

#### Interface / API

```python
from vidbyte import Agent, Trace

trace = Trace.langsmith_session(default_name="research-run", default_attributes={"run_id": run_id})

async with trace.session():
    planner = Agent(..., trace=trace)
    writer = Agent(..., trace=trace)
    await planner.arun("Plan the work")
    await writer.arun("Draft the answer")
```

#### Logic / Algorithm

1. Add a short paragraph to the existing Tracing section.
2. Show a LangSmith session example.
3. State that session tracing groups multiple agent runs under one parent trace.
4. Avoid documenting default trace payload changes that are out of scope.

#### Edge Cases & Error Handling

- Documentation must not imply that tool input capture or new span types are included in this PR.

---

### 6.8 Trace Package README

**File(s):** `vidbyte/trace/README.md`
**Type:** Modified

#### What it does

Adds package-level documentation for `SessionTracer`.

#### Interface / API

```python
session_trace = Trace.session(Trace.debug(events), default_name="workflow")
with session_trace.session(step="local"):
    ...
```

#### Logic / Algorithm

1. Add `SessionTracer` to the role summary.
2. Add a small usage example with `Trace.session(...)`.
3. Add `session.py` to the key modules list.

#### Edge Cases & Error Handling

- N/A - documentation-only change.

---

### 6.9 SDK Skill Documentation

**File(s):** `skills/vidbyte-sdk/SKILL.md`, `skills/sdk/SKILL.md`
**Type:** Modified

#### What it does

Updates SDK development guardrails so future trace preset work knows that session tracing belongs under `vidbyte.trace`.

#### Interface / API

```text
- Keep session tracing wrappers under vidbyte/trace/session.py.
```

#### Logic / Algorithm

1. Add `session.py` to the trace package layout where shown.
2. Add a rule that provider-neutral session wrappers live in `vidbyte/trace/session.py`.

#### Edge Cases & Error Handling

- N/A - documentation-only change.

---

### 6.10 LLMs Reference

**File(s):** `llms.txt`
**Type:** Modified

#### What it does

Keeps the generated long-form SDK reference aligned with the new public session tracer API.

#### Interface / API

```text
Trace.session(...)
Trace.langsmith_session(...)
SessionTracer
```

#### Logic / Algorithm

1. Add short session tracing bullets near existing tracing reference text.
2. Keep wording consistent with README.

#### Edge Cases & Error Handling

- N/A - documentation-only change.

---

## 7. Data Model Changes

### 7.1 Trace Session State

**Change type:** New

```python
@dataclass
class _TraceSessionState:
    root_context: SpanContext
```

**Migration strategy:** N/A - in-process runtime state only. No persisted data, schema, or migration is introduced.

---

## 8. API Changes

### 8.1 Python Import API: `vidbyte.trace`

**Change type:** Modified

**Request:**

```python
from vidbyte.trace import SessionTracer
```

**Response:**

```python
session_trace = SessionTracer(Trace.debug(), default_name="workflow")
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid wrapped tracer values raise `ConfigurationError` |

### 8.2 Python Import API: Root `vidbyte`

**Change type:** Modified

**Request:**

```python
from vidbyte import SessionTracer
```

**Response:**

```python
SessionTracer
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python import/API surface only |

### 8.3 Trace Facade API: Generic Session

**Change type:** New

**Request:**

```python
trace = Trace.session(Trace.debug(), default_name="workflow")
```

**Response:**

```python
SessionTracer(...)
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Invalid wrapped tracer values raise `ConfigurationError` |

### 8.4 Trace Facade API: LangSmith Session

**Change type:** New

**Request:**

```python
trace = Trace.langsmith_session(api_key="...", project="...", default_name="workflow")
```

**Response:**

```python
SessionTracer(inner=LangSmithTracer(...))
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Missing LangSmith package or credentials raise existing `TracerConfigurationError` |

### 8.5 AggregateAgent Constructor API

**Change type:** Modified

**Request:**

```python
agent = AggregateAgent(..., trace=session_trace)
```

**Response:**

```python
agent._tracer is session_trace
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Passing both `trace` and `tracer` raises existing `ConfigurationError` |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/session-tracer.md` | Design doc for SDK-owned session tracer |
| CREATE | `vidbyte/trace/session.py` | Provider-neutral `SessionTracer` and sync/async session context manager |
| MODIFY | `vidbyte/trace/base.py` | Add `Trace.session(...)` and `Trace.langsmith_session(...)` helpers |
| MODIFY | `vidbyte/trace/__init__.py` | Export `SessionTracer` from trace package |
| MODIFY | `vidbyte/__init__.py` | Export `SessionTracer` from root package |
| MODIFY | `vidbyte/agents/aggregation.py` | Preserve tracers through SDK-constructed aggregate child agents |
| MODIFY | `vidbyte/agents/base.py` | Pass resolved tracer into internal aggregate agent delegation |
| MODIFY | `README.md` | Document session tracer usage |
| MODIFY | `vidbyte/trace/README.md` | Document session tracer package role and usage |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Update trace package layout and guardrails |
| MODIFY | `skills/sdk/SKILL.md` | Update trace package layout and guardrails |
| MODIFY | `llms.txt` | Keep SDK reference text aligned with public API |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `langsmith` optional package | Existing optional adapter behavior | Used only when callers choose `Trace.langsmith_session(...)` | Missing package or credentials raise existing `TracerConfigurationError` |

No new mandatory dependency is added to `pyproject.toml`.

---

## 11. Rollout & Deployment

- No feature flag is required.
- This is additive and backward compatible.
- Existing users can keep using plain `Trace.langsmith(...)`, `Trace.debug(...)`, `trace=`, or `tracer=`.
- Users who want one trace for multiple agents can opt into `Trace.session(...)` or `Trace.langsmith_session(...)`.
- Deployment is a normal SDK package release.
- Rollback procedure: remove `vidbyte/trace/session.py`, remove the new `Trace` facade methods, remove exports/docs, and revert the narrow aggregate tracer propagation changes. Existing non-session tracing remains intact.

---

## 12. Open Questions

- [ ] Should future PRs add `Trace.langfuse_session(...)` and `Trace.phoenix_session(...)` convenience factories, or should non-LangSmith users use `Trace.session(Trace.langfuse(...))` for now?
- [ ] Should a later PR add explicit pipeline-level helpers that automatically wrap a whole pipeline run in a trace session?
- [ ] Should a later PR add trace IDs or root-context metadata to returned agent replies for easier UI linking?

---

## 13. Alternatives Considered

### Alternative 1: Keep SessionTracer Only In Harnesses

- What: Leave the existing job-applier `SessionTracer` as harness-local code and let future users copy it.
- Why rejected: The user explicitly wants prebuilt tracing options inside `vidbyte-sdk`, and this is the concrete wrapper users currently have to implement themselves.

### Alternative 2: Add Session Methods Directly To LangSmithTracer

- What: Put `begin_session`, `end_session`, and `session` on `LangSmithTracer`.
- Why rejected: The grouping behavior is provider-neutral. Keeping it as a wrapper lets the same session logic work with `Trace.debug()` and any future tracer without duplicating lifecycle code in every provider adapter.

### Alternative 3: Change BaseAgent To Know About Sessions

- What: Add session-specific parameters or logic directly to `BaseAgent.generate_reply()`.
- Why rejected: `BaseAgent` already speaks only the `TracerBase` contract. A wrapper that converts root traces to child spans preserves that boundary and avoids coupling agents to one trace grouping concept.

### Alternative 4: Implement Default-Agent-Tracing Improvements In The Same PR

- What: Also add tool input capture, iteration spans, context-window spans, and middleware decision spans.
- Why rejected: The user asked to implement only the session tracer. Default trace payload improvements are useful but are a separate feature with different risk and UX choices.
