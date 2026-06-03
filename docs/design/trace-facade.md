# Design Doc: Trace Facade

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-03
**Last Updated:** 2026-06-03

---

## 1. Overview

This feature adds a small public `vidbyte.trace` package with a `Trace` helper namespace for ergonomic agent tracing presets. It keeps the existing `TracerBase` runtime contract and provider adapters, but gives SDK users simple entry points such as `Trace.off()`, `Trace.debug()`, `Trace.continual(...)`, `Trace.custom(...)`, `Trace.langfuse(...)`, `Trace.langsmith(...)`, and `Trace.phoenix(...)`. The first implementation also adds a `trace=` alias on `BaseAgent` that resolves into the existing internal `_tracer` path, so the facade is usable from agents without changing the current runtime span emission logic.

---

## 2. Goals & Non-Goals

### Goals

- Add a public `vidbyte/trace/` package.
- Expose a `Trace` class with preset factory methods for off, debug, continual, custom, Langfuse, LangSmith, and Phoenix tracing.
- Reuse the existing `vidbyte.lib.tracing.TracerBase` contract so `AgentRuntime` tracing does not need a new execution path.
- Wire existing provider adapters from `vidbyte.providers.tracing` into the matching `Trace` helper methods.
- Add a lightweight in-memory `DebugTracer` useful for tests and local inspection.
- Add a validated `ContinualTracer` preset with user-required `remember` settings, while deferring memory/context feedback behavior.
- Add `trace=` to `BaseAgent` as an ergonomic alias for `tracer=`, with a validation error when both are provided.
- Preserve backward compatibility for existing `tracer=` callers and existing provider imports.
- Export `Trace`, `DebugTracer`, and `ContinualTracer` from `vidbyte.trace` and root `vidbyte`.
- Add unit tests and a focused verification script for every behavior in this design.

### Non-Goals

- Do not implement trace-to-context memory feedback in this PR.
- Do not add model-generated trace summarization.
- Do not change the existing `AgentRuntime` span names or span emission points.
- Do not remove or rename `TracerBase`, `NullTracer`, or the existing `tracer=` agent parameter.
- Do not add new mandatory dependencies to `pyproject.toml`.
- Do not add new external provider SDKs beyond the existing Langfuse, LangSmith, and Phoenix adapters.
- Do not implement persistent trace storage, JSONL output, remote Vidbyte service uploads, or private Vidbyte service logic.

---

## 3. Background & Context

The SDK already has a provider-neutral tracing contract under `vidbyte/lib/tracing/base.py`: `TracerBase`, `SpanContext`, and `NullTracer`. `BaseAgent` accepts `tracer: type[TracerBase] | TracerBase | None`, stores it as `_tracer`, starts one root `agent.run` trace in `generate_reply()`, and passes the tracer into `AgentRuntime`. `AgentRuntime` emits child spans for model calls and tool calls. Existing provider adapters live under `vidbyte/providers/tracing/` for Langfuse, LangSmith, and Phoenix. Existing tests under `tests/test_tracing.py` cover null tracing, BaseAgent tracer wiring, runtime span emission, and provider configuration failures.

The current API is technically usable but not elegant. Users must know about `TracerBase`, `NullTracer`, or provider-specific adapter classes. The requested shape is a first-class SDK facade: `Trace.off()`, `Trace.debug()`, `Trace.continual(...)`, `Trace.langfuse(...)`, and similar helpers. This feature therefore adds a public namespace above the existing lower-level tracer contract, rather than replacing the runtime contract.

The SDK structure rules prefer public namespaces such as `vidbyte.context`, `vidbyte.tools`, and `vidbyte.middleware`, while shared internal contracts live under `vidbyte/lib/`. The new `vidbyte.trace` package follows that pattern: `vidbyte.trace` is the user-facing factory surface; `vidbyte.lib.tracing` remains the runtime protocol; `vidbyte.providers.tracing` remains the provider adapter layer.

The worktree is currently dirty with many generated `__pycache__` changes and some untracked artifacts. Implementation must therefore happen later in an isolated worktree after approval, preserving unrelated changes.

---

## 4. Requirements

### Functional Requirements

1. `from vidbyte.trace import Trace` must import the public trace facade.
2. `from vidbyte import Trace` must import the same public facade.
3. `Trace.off()` must return a `NullTracer`.
4. `Trace.debug()` must return a `DebugTracer`.
5. `DebugTracer` must implement `TracerBase`.
6. `DebugTracer` must record started and ended traces/spans in an in-memory event list supplied by the caller or owned internally.
7. `Trace.custom(tracer)` must accept a `TracerBase` instance.
8. `Trace.custom(tracer)` must accept a `TracerBase` class and instantiate it without arguments.
9. `Trace.custom(tracer)` must reject `None` and non-tracer objects with `ConfigurationError`.
10. `Trace.continual(remember, *, max_memory_chars=1200, redact=True)` must require the caller to pass a non-empty `remember` sequence.
11. `Trace.continual(...)` must return a `ContinualTracer`.
12. `ContinualTracer` must implement `TracerBase`.
13. `ContinualTracer` must validate `remember` values against a small supported set: `model_calls`, `tool_calls`, `failures`, `outputs`, and `decisions`.
14. `ContinualTracer` must validate `max_memory_chars` as a positive integer.
15. `ContinualTracer` must store immutable settings that later work can use for trace-to-context feedback.
16. `ContinualTracer` must record trace/span lifecycle events in memory like `DebugTracer`.
17. `Trace.langfuse(public_key=None, secret_key=None, host=None)` must construct and return `LangfuseTracer` with matching keyword arguments.
18. `Trace.langsmith(api_key=None, project=None)` must construct and return `LangSmithTracer` with matching keyword arguments.
19. `Trace.phoenix(endpoint=None)` must construct and return `PhoenixTracer` with matching keyword arguments.
20. Provider helper methods must let existing provider adapters raise `TracerConfigurationError` for missing packages or credentials.
21. `BaseAgent.__init__` must accept `trace: type[TracerBase] | TracerBase | None = None` as an alias.
22. `BaseAgent.__init__` must raise `ConfigurationError` if both `trace` and `tracer` are supplied.
23. `BaseAgent` must normalize `trace=` and `tracer=` through one helper so class, instance, and `None` behavior remain consistent.
24. `BaseAgent.fork()` must preserve the resolved tracer instance as it does today.
25. Existing `tracer=` tests must continue to pass unchanged or with only expectation-preserving updates.
26. The root `README.md` must document the simple helper usage without implying that continual memory feedback is already implemented.
27. SDK skill docs must mention `vidbyte.trace` as the public trace facade and keep `vidbyte.lib.tracing` as the internal protocol.

### Non-Functional Requirements

- Performance: `Trace.off()` must keep the existing `NullTracer` no-op behavior. `DebugTracer` and `ContinualTracer` only append small lifecycle records and must not perform network or filesystem I/O.
- Scalability: in-memory debug/continual event lists are intended for local debugging and first-step scaffolding, not unbounded production retention. Documentation must state this.
- Security: `DebugTracer` and `ContinualTracer` must not redact yet except for storing the `redact` setting on `ContinualTracer`; future context feedback work owns real redaction behavior. Provider adapters keep their current behavior.
- Observability: provider helpers must use existing provider adapters and must not swallow provider-construction configuration errors.
- Reliability: invalid facade inputs must fail at construction time with `ConfigurationError`, not later during agent execution.
- Compatibility: existing `tracer=` callers and `vidbyte.lib.tracing` imports must remain valid.

---

## 5. High-Level Design

The design adds one public package, `vidbyte.trace`, centered on a class named `Trace`. `Trace` is a factory namespace, not a runtime singleton. Every helper returns an object implementing `TracerBase`, which means the existing `BaseAgent` and `AgentRuntime` tracing implementation can keep using `_tracer.start_trace(...)`, `_tracer.start_span(...)`, `_tracer.end_span(...)`, and `_tracer.end_trace(...)`.

`Trace.off()` maps to the existing `NullTracer`. `Trace.debug()` returns a new in-memory `DebugTracer`. `Trace.continual(...)` returns a `ContinualTracer`, which is deliberately a validated, parameterized first step: it records lifecycle events and stores the user's `remember`, `max_memory_chars`, and `redact` settings, but it does not yet summarize events into `ContextManager` memory. Provider helpers delegate directly to `LangfuseTracer`, `LangSmithTracer`, and `PhoenixTracer`.

The agent integration stays minimal. `BaseAgent` gains a new optional `trace=` parameter that is mutually exclusive with the existing `tracer=` parameter. Internally both are normalized into `_tracer`, so no runtime span logic changes are required. Users can write `Agent(..., trace=Trace.debug())` while older code can continue using `Agent(..., tracer=RecordingTracer())`.

```text
User code
  |
  v
Trace.debug() / Trace.continual(...) / Trace.langfuse(...)
  |
  v
TracerBase instance
  |
  v
BaseAgent(trace=...) -> _tracer
  |
  v
AgentRuntime existing start_trace/start_span/end_span/end_trace calls
```

---

## 6. Detailed Design

### 6.1 Public Trace Package

**File(s):** `vidbyte/trace/__init__.py`
**Type:** New file

#### What it does

Exports the public trace facade and built-in tracer classes from the new `vidbyte.trace` namespace.

#### Interface / API

```python
from vidbyte.trace.base import ContinualTracer, DebugTracer, Trace

__all__ = ["ContinualTracer", "DebugTracer", "Trace"]
```

#### Logic / Algorithm

1. Import `Trace`, `DebugTracer`, and `ContinualTracer` from `vidbyte.trace.base`.
2. Expose a small `__all__` with only public facade types.

#### Edge Cases & Error Handling

- N/A - import-only module.

---

### 6.2 Trace Facade And Built-In Tracers

**File(s):** `vidbyte/trace/base.py`
**Type:** New file

#### What it does

Defines the public `Trace` helper class plus `DebugTracer` and `ContinualTracer`. The classes implement or return existing `TracerBase` objects.

#### Interface / API

```python
class Trace:
    @staticmethod
    def off() -> TracerBase: ...
    @staticmethod
    def debug(events: list[dict[str, Any]] | None = None) -> DebugTracer: ...
    @staticmethod
    def custom(tracer: type[TracerBase] | TracerBase) -> TracerBase: ...
    @staticmethod
    def continual(remember: Sequence[str], *, max_memory_chars: int = 1200, redact: bool = True) -> ContinualTracer: ...
    @staticmethod
    def langfuse(public_key: str | None = None, secret_key: str | None = None, host: str | None = None) -> TracerBase: ...
    @staticmethod
    def langsmith(api_key: str | None = None, project: str | None = None) -> TracerBase: ...
    @staticmethod
    def phoenix(endpoint: str | None = None) -> TracerBase: ...

class DebugTracer(TracerBase):
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None: ...
    def start_trace(self, name: str, **attributes: Any) -> SpanContext: ...
    def end_trace(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None: ...
    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext: ...
    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None: ...

class ContinualTracer(DebugTracer):
    def __init__(self, remember: Sequence[str], *, max_memory_chars: int = 1200, redact: bool = True, events: list[dict[str, Any]] | None = None) -> None: ...
```

#### Logic / Algorithm

1. `Trace.off()` returns `NullTracer()`.
2. `Trace.debug(events=None)` returns `DebugTracer(events=events)`.
3. `Trace.custom(tracer)` delegates to `_TraceFactory.resolve_custom_tracer(...)`.
4. `Trace.continual(...)` returns `ContinualTracer(...)`.
5. Provider helper methods import existing provider adapters and instantiate them with forwarded keyword arguments.
6. `DebugTracer` owns or receives a list of event dictionaries.
7. `DebugTracer.start_trace(...)` records `{"type": "start_trace", "name": name, "attributes": dict(attributes), "context": context}` and returns a `SpanContext`.
8. `DebugTracer.end_trace(...)` records output/error metadata without raising.
9. `DebugTracer.start_span(...)` records span start with parent metadata and returns a `SpanContext`.
10. `DebugTracer.end_span(...)` records span end output/error metadata without raising.
11. `ContinualTracer.__init__` validates `remember` and `max_memory_chars`, stores `remember` as a tuple, stores `redact`, and delegates event recording behavior to `DebugTracer`.

#### Edge Cases & Error Handling

- `Trace.custom(None)` raises `ConfigurationError`.
- `Trace.custom(object())` raises `ConfigurationError`.
- `Trace.custom(SomeTracerClass)` instantiates with no arguments and lets constructor errors propagate.
- `Trace.continual(())` raises `ConfigurationError`.
- `Trace.continual(["unsupported"])` raises `ConfigurationError`.
- `Trace.continual(["tool_calls"], max_memory_chars=0)` raises `ConfigurationError`.
- Provider helper methods do not catch `TracerConfigurationError`; existing provider adapter behavior remains visible.

---

### 6.3 Trace Factory Helper

**File(s):** `vidbyte/trace/base.py`
**Type:** New file

#### What it does

Keeps validation and normalization logic out of the `Trace` static methods so the public class remains readable.

#### Interface / API

```python
class _TraceFactory:
    @staticmethod
    def resolve_custom_tracer(tracer: type[TracerBase] | TracerBase) -> TracerBase: ...
    @staticmethod
    def validate_remember(remember: Sequence[str]) -> tuple[str, ...]: ...
    @staticmethod
    def validate_max_memory_chars(max_memory_chars: int) -> int: ...
```

#### Logic / Algorithm

1. `resolve_custom_tracer` rejects `None`, instantiates tracer classes, and verifies the final object is a `TracerBase`.
2. `validate_remember` rejects empty sequences and unsupported values.
3. `validate_max_memory_chars` rejects non-positive and non-integer values.

#### Edge Cases & Error Handling

- Strings passed as `remember` are treated as invalid because they are ambiguous sequences of characters; callers must pass a sequence such as `["tool_calls"]`.
- Duplicate `remember` values are de-duplicated while preserving order.

---

### 6.4 BaseAgent Trace Alias

**File(s):** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does

Adds `trace=` as an ergonomic public alias while preserving the existing internal `_tracer` field and existing `tracer=` parameter.

#### Interface / API

```python
class BaseAgent:
    def __init__(..., tracer: type[TracerBase] | TracerBase | None = None, trace: type[TracerBase] | TracerBase | None = None) -> None: ...
    def _resolve_tracer(self, tracer: type[TracerBase] | TracerBase | None, trace: type[TracerBase] | TracerBase | None) -> TracerBase: ...
```

#### Logic / Algorithm

1. Add `trace` after `tracer` in the constructor signature.
2. Replace the inline tracer normalization with `self._resolve_tracer(tracer, trace)`.
3. `_resolve_tracer` raises `ConfigurationError` when both `tracer` and `trace` are not `None`.
4. `_resolve_tracer` selects `trace` when supplied, otherwise `tracer`, otherwise `None`.
5. `_resolve_tracer` preserves existing behavior: `None` becomes `NullTracer()`, classes are instantiated, and instances are used directly.
6. `fork()` continues passing `tracer=self._tracer`, with no new `trace` forwarding needed.

#### Edge Cases & Error Handling

- Passing both `trace=Trace.debug()` and `tracer=RecordingTracer()` raises `ConfigurationError`.
- Passing `trace=RecordingTracer` instantiates the class, matching existing `tracer=` behavior.
- Passing `trace=Trace.off()` stores a `NullTracer`.
- Existing callers using `tracer=` are unaffected.

---

### 6.5 Root Exports

**File(s):** `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Adds the new trace facade types to the root public import surface.

#### Interface / API

```python
from vidbyte.trace import ContinualTracer, DebugTracer, Trace
```

#### Logic / Algorithm

1. Import `Trace`, `DebugTracer`, and `ContinualTracer` from `vidbyte.trace`.
2. Add those names to `__all__`.
3. Keep existing `NullTracer`, `TracerBase`, and `TracerConfigurationError` exports for compatibility.

#### Edge Cases & Error Handling

- N/A - import-only changes.

---

### 6.6 README Documentation

**File(s):** `README.md`
**Type:** Modified

#### What it does

Documents the new public trace facade near the agent/middleware sections.

#### Interface / API

```python
from vidbyte import Agent, Trace

agent = Agent(
    name="researcher",
    system_prompt="Work carefully.",
    runner=my_runner,
    trace=Trace.debug(),
)

agent = Agent(
    name="observed-researcher",
    system_prompt="Work carefully.",
    runner=my_runner,
    trace=Trace.langfuse(public_key="...", secret_key="..."),
)
```

#### Logic / Algorithm

1. Add a short "Tracing" section.
2. Show `Trace.off()`, `Trace.debug()`, `Trace.continual(...)`, and one provider-backed example.
3. State that `Trace.continual(...)` is currently a validated capture preset and that trace-to-context feedback is planned follow-up work.

#### Edge Cases & Error Handling

- Documentation must not claim persistent memory or context feedback exists in this first PR.

---

### 6.7 SDK Skill Documentation

**File(s):** `skills/vidbyte-sdk/SKILL.md`, `skills/sdk/SKILL.md`
**Type:** Modified

#### What it does

Updates package layout and guardrails so future SDK changes know where public trace facade code belongs.

#### Interface / API

```text
vidbyte/
|-- trace/
```

#### Logic / Algorithm

1. Add `vidbyte/trace/` to package layout examples.
2. Add a rule that public trace presets live in `vidbyte/trace/`.
3. Add a rule that provider-neutral tracer protocols remain under `vidbyte/lib/tracing/`.
4. Add a rule that external provider trace adapters remain under `vidbyte/providers/tracing/`.

#### Edge Cases & Error Handling

- N/A - documentation-only changes.

---

### 6.8 Unit Tests

**File(s):** `tests/test_trace_facade.py`, `tests/test_tracing.py`
**Type:** New file and modified file

#### What it does

Adds focused tests for the facade and extends existing tracing tests for `BaseAgent(trace=...)`.

#### Interface / API

```python
class TraceFacadeTests(unittest.TestCase): ...
class BaseAgentTraceAliasTests(unittest.TestCase): ...
```

#### Logic / Algorithm

1. Add `tests/test_trace_facade.py` for `Trace` helpers, built-in tracer validation, and provider helper forwarding.
2. Extend `tests/test_tracing.py` or add facade-specific agent tests to cover `BaseAgent(trace=...)`.
3. Use fake provider tracer classes or `unittest.mock.patch` to avoid requiring optional provider SDKs.
4. Use existing fake runner patterns for agent tests.

#### Edge Cases & Error Handling

- Tests must not call real Langfuse, LangSmith, or Phoenix services.
- Tests must not require optional provider packages to be installed.

---

### 6.9 Verification Script

**File(s):** `scripts/test-trace-facade.py`
**Type:** New file

#### What it does

Runs every test case listed in Section 10 and prints PASS/FAIL lines plus a final summary.

#### Interface / API

```powershell
python scripts/test-trace-facade.py
```

#### Logic / Algorithm

1. Import the implemented trace facade and relevant test doubles.
2. Run each Section 10 case directly.
3. Print one PASS or FAIL line per test.
4. Print `X/Y tests passed`.
5. Exit non-zero if any test fails.

#### Edge Cases & Error Handling

- The script patches provider classes to avoid optional dependency requirements.
- The script must fail if imports are missing or if any validation behavior silently changes.

---

## 7. Data Model Changes

### 7.1 Debug Trace Event Dictionaries

**Change type:** New

```python
{
    "type": "start_trace" | "end_trace" | "start_span" | "end_span",
    "name": str | None,
    "attributes": dict[str, Any],
    "context": SpanContext,
    "parent": SpanContext | None,
    "output": str | None,
    "error": str | None,
}
```

**Migration strategy:** N/A - in-memory debug data only.

### 7.2 ContinualTracer Settings

**Change type:** New

```python
class ContinualTracer(DebugTracer):
    remember: tuple[str, ...]
    max_memory_chars: int
    redact: bool
```

**Migration strategy:** N/A - new optional public tracer class.

---

## 8. API Changes

### 8.1 Python Import API: `vidbyte.trace`

**Change type:** New

**Request:**

```python
from vidbyte.trace import Trace
```

**Response:**

```python
tracer = Trace.debug()
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python import/API surface only; invalid factory arguments raise Python SDK exceptions |

### 8.2 Python Import API: Root `vidbyte`

**Change type:** Modified

**Request:**

```python
from vidbyte import Trace
```

**Response:**

```python
tracer = Trace.off()
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Python import/API surface only |

### 8.3 Agent Constructor API

**Change type:** Modified

**Request:**

```python
agent = Agent(
    name="researcher",
    system_prompt="Work carefully.",
    runner=my_runner,
    trace=Trace.debug(),
)
```

**Response:**

```python
agent._tracer  # DebugTracer instance internally; public runtime behavior unchanged
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | Passing both `trace` and `tracer` raises `ConfigurationError` |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/trace-facade.md` | Design doc for the public trace facade |
| CREATE | `vidbyte/trace/__init__.py` | Public trace package exports |
| CREATE | `vidbyte/trace/base.py` | `Trace`, `DebugTracer`, `ContinualTracer`, and facade validation |
| CREATE | `tests/test_trace_facade.py` | Focused tests for helper methods and built-in tracer behavior |
| CREATE | `scripts/test-trace-facade.py` | Required verification script for all design test cases |
| MODIFY | `vidbyte/agents/base.py` | Add `trace=` alias and shared tracer normalization |
| MODIFY | `vidbyte/__init__.py` | Root exports for `Trace`, `DebugTracer`, and `ContinualTracer` |
| MODIFY | `README.md` | Document public tracing helpers and first-step continual behavior |
| MODIFY | `skills/vidbyte-sdk/SKILL.md` | Add trace package layout and guardrails |
| MODIFY | `skills/sdk/SKILL.md` | Add trace package layout and guardrails |
| MODIFY | `tests/test_tracing.py` | Add or adjust BaseAgent trace alias coverage |

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] `Trace.off` -> `returns NullTracer and accepts start/end trace calls without events`.
- [Edge Case] `Trace.debug` -> `creates an empty internal event list when no list is supplied`.
- [Edge Case] `Trace.debug` -> `uses a caller-supplied empty list and appends lifecycle records`.
- [Silent Failure] `DebugTracer` -> `records the correct event type order for start_trace, start_span, end_span, end_trace`.
- [Silent Failure] `DebugTracer` -> `records span parent context instead of dropping parent linkage`.
- [Hidden Failure] `DebugTracer` -> `end_span and end_trace store error strings without raising`.
- [Hidden Assumption] `Trace.custom` -> `accepts a TracerBase instance instead of assuming only classes`.
- [Hidden Assumption] `Trace.custom` -> `accepts a TracerBase class instead of assuming only instances`.
- [Edge Case] `Trace.custom` -> `raises ConfigurationError for None`.
- [Hidden Failure] `Trace.custom` -> `raises ConfigurationError for non-tracer objects that happen to be callable`.
- [Edge Case] `Trace.continual` -> `raises ConfigurationError for empty remember`.
- [Hidden Assumption] `Trace.continual` -> `raises ConfigurationError when remember is a raw string`.
- [Silent Failure] `Trace.continual` -> `deduplicates duplicate remember values while preserving order`.
- [Edge Case] `Trace.continual` -> `raises ConfigurationError for unsupported remember values`.
- [Edge Case] `Trace.continual` -> `raises ConfigurationError for max_memory_chars equal to zero`.
- [Edge Case] `Trace.continual` -> `raises ConfigurationError for negative max_memory_chars`.
- [Hidden Assumption] `Trace.continual` -> `raises ConfigurationError for non-integer max_memory_chars`.
- [Silent Failure] `Trace.continual` -> `stores remember, max_memory_chars, and redact settings exactly`.
- [Silent Failure] `Trace.continual` -> `records lifecycle events like DebugTracer`.
- [Hidden Failure] `Trace.langfuse` -> `forwards public_key, secret_key, and host to LangfuseTracer`.
- [Hidden Failure] `Trace.langsmith` -> `forwards api_key and project to LangSmithTracer`.
- [Hidden Failure] `Trace.phoenix` -> `forwards endpoint to PhoenixTracer`.
- [Hidden Assumption] Provider helpers -> `propagate TracerConfigurationError instead of swallowing construction failures`.
- [Silent Failure] Root exports -> `from vidbyte import Trace returns the same class as from vidbyte.trace import Trace`.
- [Silent Failure] Package exports -> `vidbyte.trace.__all__ includes Trace, DebugTracer, and ContinualTracer`.
- [Edge Case] `BaseAgent(trace=Trace.off())` -> `stores a NullTracer internally`.
- [Hidden Assumption] `BaseAgent(trace=RecordingTracer)` -> `instantiates tracer classes through the alias path`.
- [Hidden Assumption] `BaseAgent(trace=recording_tracer_instance)` -> `uses tracer instances directly through the alias path`.
- [Edge Case] `BaseAgent(trace=..., tracer=...)` -> `raises ConfigurationError`.
- [Silent Failure] `BaseAgent.fork()` -> `preserves the resolved tracer instance when trace alias was used`.
- [Hidden Failure] Existing tests -> `existing tracer= behavior still passes after refactor`.

### Integration Tests

- [Hidden Failure] Run a fake `BaseAgent` with `trace=Trace.debug(events)` and an `AlwaysDoneRunner`; verify the debug list contains one root trace and runtime span lifecycle records.
- [Silent Failure] Run a fake `BaseAgent` with `trace=Trace.continual(["tool_calls"])`; verify agent execution succeeds and the tracer keeps continual settings plus lifecycle events.
- [Hidden Assumption] Patch provider tracer constructors and call `Trace.langfuse`, `Trace.langsmith`, and `Trace.phoenix`; verify no optional provider SDK is imported during the test.
- [Hidden Failure] Run `python -m unittest tests.test_trace_facade tests.test_tracing` from the SDK root.

### Manual / QA Test Cases

1. [Edge Case] Given `Trace.off()`, when it is passed as `trace=` to an agent, then the agent runs with no observable event list.
2. [Silent Failure] Given `events = []` and `trace=Trace.debug(events)`, when the agent runs, then `events` contains readable ordered trace/span records.
3. [Hidden Assumption] Given `Trace.continual(["tool_calls"], max_memory_chars=500)`, when inspected before execution, then its settings are available for future memory work.
4. [Hidden Failure] Given missing Langfuse optional dependency, when `Trace.langfuse(public_key="pk", secret_key="sk")` is called, then the existing `TracerConfigurationError` message is surfaced.
5. [Silent Failure] Given `from vidbyte import Trace`, when `Trace.debug()` is called, then it returns the same debug tracer class as `from vidbyte.trace import Trace`.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `langfuse` optional package | Existing optional adapter behavior | Used by `Trace.langfuse(...)` through `LangfuseTracer` | Missing package raises `TracerConfigurationError` |
| Existing `langsmith` optional package | Existing optional adapter behavior | Used by `Trace.langsmith(...)` through `LangSmithTracer` | Missing package raises `TracerConfigurationError` |
| Existing OpenTelemetry/Phoenix optional packages | Existing optional adapter behavior | Used by `Trace.phoenix(...)` through `PhoenixTracer` | Missing package raises `TracerConfigurationError` |

No new mandatory dependency is added to `pyproject.toml`.

---

## 12. Rollout & Deployment

- No feature flag is required.
- This is additive and backward compatible.
- Existing users can keep using `tracer=...`.
- New users can use `trace=Trace.<preset>()`.
- Deployment is a normal SDK package release.
- Rollback procedure: remove `vidbyte/trace`, root exports, README/skill docs, tests, verification script, and the `trace=` alias from `BaseAgent`. Existing `tracer=` behavior remains the fallback.

---

## 13. Open Questions

- [ ] Should `Trace.continual(...)` support a default preset later, such as `Trace.continual.default()` or `Trace.continual(remember=["tool_calls", "failures"])`, after this first explicit-parameter version lands?
- [ ] Should provider helper methods also be exposed as lowercase module-level functions like `vidbyte.trace.langfuse(...)`, or should the initial API stay class-based as `Trace.langfuse(...)`?
- [ ] Should `DebugTracer` event dictionaries be promoted into a formal dataclass in a later PR if downstream tooling starts depending on them?

---

## 14. Alternatives Considered

### Alternative 1: Replace `TracerBase` With A New Trace Runtime Contract

- What: Introduce a new event-oriented runtime abstraction and migrate `BaseAgent`/`AgentRuntime` to it.
- Why rejected: The SDK already has working root trace and child span hooks. Replacing the contract would be larger, riskier, and unnecessary for the requested first implementation.

### Alternative 2: Only Add Provider Helper Functions Without `trace=` Agent Alias

- What: Implement `Trace.langfuse(...)` and related helpers but require callers to pass them through the old `tracer=` parameter.
- Why rejected: The user's design direction emphasizes seamless SDK/agent integration. A small `trace=` alias gives the clean public usage without changing runtime behavior.

### Alternative 3: Implement Full Continual Trace Memory Feedback Now

- What: Make `Trace.continual(...)` summarize trace events and inject `MemoryContextItem` or `ProgressContextItem` into future context.
- Why rejected: The current task asks for the beginning implementation and says to stop after helper/provider wiring. Memory feedback needs a separate design because it affects context mutation, redaction, storage, and prompt visibility.

### Alternative 4: Put `Trace` Under `vidbyte/lib/tracing`

- What: Add facade helpers directly to the internal tracing package.
- Why rejected: The repo conventions keep public namespaces at the top level. `vidbyte.trace` is easier to discover and mirrors `vidbyte.context`, `vidbyte.tools`, and `vidbyte.middleware`.
