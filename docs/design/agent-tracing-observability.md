# Design Doc: Agent Tracing & Observability

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-23
**Last Updated:** 2026-05-23

---

## 1. Overview

This feature adds a platform-agnostic tracing layer to the Vidbyte SDK so that developers can attach any major observability provider (Langfuse, LangSmith, Arize Phoenix, and others) to a `BaseAgent` with a single `tracer=` constructor parameter. Trace data — root agent runs, per-iteration LLM calls, and individual tool executions — flows automatically into the chosen platform without the developer instrumenting their own application code. When no tracer is configured, a zero-overhead `NullTracer` is used and no performance penalty is incurred.

---

## 2. Goals & Non-Goals

### Goals
- Add a `tracer` parameter to `BaseAgent.__init__()` that accepts either a tracer class or a pre-configured tracer instance.
- Define a `TracerBase` abstract class in `vidbyte/lib/tracing/` that represents the canonical tracing contract all platform adapters must implement.
- Ship three platform adapters in `vidbyte/providers/tracing/`: `LangfuseTracer`, `LangSmithTracer`, `PhoenixTracer` (Arize).
- Each adapter reads credentials from constructor keyword arguments, falling back to `.env` / environment variables when not supplied.
- Produce hierarchical spans: one root span per `generate_reply()` call, with child LLM-call spans and tool-call spans emitted by `AgentRuntime`.
- Propagate the tracer to child agents created via `fork()`.
- Provide a `NullTracer` default so no change in behavior when `tracer` is omitted.

### Non-Goals
- Tracing inside strategy-level execution (ReAct, Reflexion, TreeOfThoughts, multi-agent strategies) — strategies call runners directly and are out of scope for V1; follow-up work.
- Pipeline-level tracing.
- Weave (W&B), AgentOps, or Laminar adapters in V1 (architecture supports them; ship as follow-ups).
- Auto-loading `.env` files — the SDK reads standard OS environment variables; `.env` loading is the caller's responsibility (e.g. via `python-dotenv`).
- Modifying strategies, pipelines, or harnesses.

---

## 3. Background & Context

Vidbyte providers (`AnthropicProvider`, `OpenAIProvider`, etc.) are raw HTTP wrappers that call `transport.request()` directly rather than using official vendor Python clients. This means every existing auto-instrumentation package (e.g. `opentelemetry-instrumentation-anthropic`, `langsmith.wrappers`) will silently no-op because they patch client library internals, not raw HTTP. Tracing hooks must therefore be added explicitly at the agent and runtime layers.

The codebase already has a clean provider/lib split: `vidbyte/providers/` holds LLM adapters; `vidbyte/lib/` holds shared infrastructure. Tracing follows the same pattern: `vidbyte/lib/tracing/` owns the protocol and null implementation; `vidbyte/providers/tracing/` owns the platform-specific adapters.

---

## 4. Requirements

### Functional Requirements

1. `BaseAgent.__init__()` accepts `tracer: type[TracerBase] | TracerBase | None = None`.
2. If `tracer` is a class, the SDK instantiates it with no arguments (reads credentials from env). If it is an instance, the SDK uses it as-is. If `None`, a `NullTracer` is used.
3. `generate_reply()` opens a root trace span before execution and closes it (with output or error) after execution, regardless of whether a strategy is used.
4. `AgentRuntime.arun()` opens a child LLM-call span before each `invoke_runner` call and closes it with the model output afterward.
5. `AgentRuntime.execute_tool_call()` opens a child tool-call span before execution and closes it with the result or error after.
6. `fork()` copies the tracer reference to the child agent.
7. `LangfuseTracer` accepts `public_key`, `secret_key`, and `host` keyword arguments, falling back to `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` environment variables.
8. `LangSmithTracer` accepts `api_key` and `project` keyword arguments, falling back to `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` environment variables.
9. `PhoenixTracer` (Arize) accepts `endpoint` keyword argument, falling back to `PHOENIX_COLLECTOR_ENDPOINT` environment variable.
10. All three adapters raise `TracerConfigurationError` on construction if required credentials cannot be resolved.
11. All span close calls are guarded: if the platform SDK raises, the exception is swallowed and does not propagate to the caller.

### Non-Functional Requirements

- `NullTracer` operations must be branch-free (no `if tracer is not None` guards scattered through `generate_reply` / `AgentRuntime`); the null object pattern eliminates branching.
- Platform adapter dependencies (`langfuse`, `langsmith`, `arize-phoenix`) are lazy-imported at first use inside each adapter's `__init__`, not at module load time. Import errors surface as `TracerConfigurationError` with a human-readable install hint.
- No new mandatory dependencies added to `pyproject.toml`; all tracing SDKs are optional extras.

---

## 5. High-Level Design

The tracing system is divided into two layers following the existing `lib/` vs `providers/` pattern.

**`vidbyte/lib/tracing/`** defines the contract: `TracerBase` (abstract base class), `SpanContext` (opaque span handle passed between methods), and `NullTracer` (production default). The agent and runtime layers import only from `lib/tracing`; they never reference platform-specific types.

**`vidbyte/providers/tracing/`** contains concrete adapters (`LangfuseTracer`, `LangSmithTracer`, `PhoenixTracer`). Each lazily imports its third-party SDK at construction time and maps the `TracerBase` interface onto the platform's native trace/span model.

`BaseAgent` stores `self._tracer: TracerBase`. On `generate_reply()`, it opens a root span, delegates execution as before, then closes the span. It passes the tracer into `AgentRuntime` (via the `_runtime()` factory) so that the runtime can attach LLM-call and tool-call spans as children of the root.

```
BaseAgent.generate_reply()
  │
  ├─ tracer.start_trace("agent.run")  ← root span
  │
  ├─ AgentRuntime.arun()
  │     │
  │     ├─ [loop] tracer.start_span("llm.call", parent=root)
  │     │          invoke_runner()
  │     │          tracer.end_span(...)
  │     │
  │     └─ [loop] tracer.start_span("tool.call", parent=root)
  │                execute_tool_call()
  │                tracer.end_span(...)
  │
  └─ tracer.end_trace(root, output=...)
```

---

## 6. Detailed Design

### 6.1 `vidbyte/lib/tracing/base.py`

**File:** `vidbyte/lib/tracing/base.py`
**Type:** New file

#### What it does
Defines the canonical tracing contract and the null implementation.

#### Interface / API

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpanContext:
    """Opaque handle to an open span. Subclassed by each adapter to carry
    platform-specific state (Langfuse trace object, LangSmith run ID, OTel span)."""
    metadata: dict[str, Any] = field(default_factory=dict)


class TracerBase(ABC):
    """Abstract tracing contract all platform adapters must implement."""

    @abstractmethod
    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        """Open a root trace (one per agent.generate_reply call)."""

    @abstractmethod
    def end_trace(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
    ) -> None:
        """Close the root trace, recording final output or error."""

    @abstractmethod
    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        **attributes: Any,
    ) -> SpanContext:
        """Open a child span under the given parent (or root if None)."""

    @abstractmethod
    def end_span(
        self,
        context: SpanContext,
        *,
        output: str | None = None,
        error: Exception | None = None,
    ) -> None:
        """Close a child span."""


class NullTracer(TracerBase):
    """Zero-overhead no-op tracer. Used when no platform is configured."""

    def start_trace(self, name: str, **attributes: Any) -> SpanContext:
        return SpanContext()

    def end_trace(self, context: SpanContext, **_: Any) -> None:
        pass

    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> SpanContext:
        return SpanContext()

    def end_span(self, context: SpanContext, **_: Any) -> None:
        pass
```

#### Edge Cases & Error Handling
- `NullTracer` methods are pure no-ops; no exceptions possible.
- Platform adapters must not let `end_trace` / `end_span` propagate exceptions (they guard with try/except internally).

---

### 6.2 `vidbyte/lib/tracing/__init__.py`

**File:** `vidbyte/lib/tracing/__init__.py`
**Type:** New file

Exports `TracerBase`, `SpanContext`, `NullTracer`, and `TracerConfigurationError`.

---

### 6.3 `vidbyte/lib/errors/base.py`

**File:** `vidbyte/lib/errors/base.py`
**Type:** Modified

Adds one new exception to the existing hierarchy:

```python
class TracerConfigurationError(VidbyteSdkError):
    """Raised when a tracing provider cannot be configured (missing credentials or SDK)."""
```

---

### 6.4 `vidbyte/providers/tracing/langfuse.py`

**File:** `vidbyte/providers/tracing/langfuse.py`
**Type:** New file

#### What it does
Bridges `TracerBase` onto Langfuse's native `trace` / `generation` / `span` model.

#### Interface / API

```python
class LangfuseSpanContext(SpanContext):
    """Carries the Langfuse trace or generation handle."""
    handle: Any  # langfuse.client.StatefulTraceClient | langfuse.client.StatefulGenerationClient

class LangfuseTracer(TracerBase):
    def __init__(
        self,
        *,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
    ) -> None: ...

    def start_trace(self, name: str, **attributes: Any) -> LangfuseSpanContext: ...
    def end_trace(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None: ...
    def start_span(self, name: str, parent: SpanContext | None = None, **attributes: Any) -> LangfuseSpanContext: ...
    def end_span(self, context: SpanContext, *, output: str | None = None, error: Exception | None = None) -> None: ...
```

#### Logic / Algorithm

1. `__init__`: lazy-import `langfuse`. Raise `TracerConfigurationError` with install hint if import fails. Resolve `public_key`, `secret_key`, `host` from kwargs → env vars `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`. Raise `TracerConfigurationError` if `public_key` or `secret_key` are still `None`.
2. `start_trace`: call `self._client.trace(name=name, metadata=attributes)`. Return `LangfuseSpanContext(handle=trace_obj)`.
3. `end_trace`: call `context.handle.update(output=output)` on success; `context.handle.update(status_message=str(error), level="ERROR")` on error. Guard with try/except.
4. `start_span`: if `parent` is a `LangfuseSpanContext`, call `parent.handle.generation(name=name, metadata=attributes)` (for LLM calls) or `parent.handle.span(name=name, metadata=attributes)` (for tool calls). Detect span type from `name` prefix (`"llm."` → generation, else span).
5. `end_span`: call `context.handle.end(output=output)` or set error level. Guard with try/except.

#### Edge Cases
- If `langfuse` is not installed: `TracerConfigurationError("Install langfuse: pip install langfuse")`.
- If Langfuse API is unreachable at trace time: silently swallowed per requirement 11. The Langfuse SDK itself queues events and retries asynchronously.

---

### 6.5 `vidbyte/providers/tracing/langsmith.py`

**File:** `vidbyte/providers/tracing/langsmith.py`
**Type:** New file

#### Interface / API

```python
class LangSmithSpanContext(SpanContext):
    run_id: str
    parent_run_id: str | None

class LangSmithTracer(TracerBase):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        project: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm

1. Lazy-import `langsmith`. Resolve `api_key` → `LANGSMITH_API_KEY`; `project` → `LANGSMITH_PROJECT` (default `"default"`).
2. `start_trace`: use `langsmith.Client` to `create_run(run_type="chain", name=name, inputs=attributes)`. Store run ID in `LangSmithSpanContext`.
3. `end_trace`: call `client.update_run(run_id, outputs={"output": output})` or set error.
4. `start_span` / `end_span`: `create_run(run_type="llm"|"tool", parent_run_id=parent.run_id, ...)` and update on close.

---

### 6.6 `vidbyte/providers/tracing/phoenix.py`

**File:** `vidbyte/providers/tracing/phoenix.py`
**Type:** New file

#### Interface / API

```python
class PhoenixSpanContext(SpanContext):
    span: Any  # opentelemetry.trace.Span

class PhoenixTracer(TracerBase):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
    ) -> None: ...
```

#### Logic / Algorithm

1. Lazy-import `openinference.instrumentation`, `opentelemetry.trace`, `opentelemetry.sdk.trace`, and `opentelemetry.exporter.otlp.proto.http`. Resolve `endpoint` → `PHOENIX_COLLECTOR_ENDPOINT` (default `"http://localhost:6006/v1/traces"`).
2. Configure an OTLP HTTP exporter and a `TracerProvider` with `SimpleSpanProcessor` on first construction.
3. Use OTel `tracer.start_as_current_span(name)` to create spans; set OpenInference semantic attributes (`input.value`, `output.value`, `llm.model_name`, etc.).
4. Store the span object in `PhoenixSpanContext`.

---

### 6.7 `vidbyte/providers/tracing/__init__.py`

**File:** `vidbyte/providers/tracing/__init__.py`
**Type:** New file

Exports `LangfuseTracer`, `LangSmithTracer`, `PhoenixTracer`.

---

### 6.8 `vidbyte/agents/base.py`

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### Changes

1. Add import: `from vidbyte.lib.tracing import NullTracer, SpanContext, TracerBase`
2. Add `tracer: type[TracerBase] | TracerBase | None = None` to `__init__()` signature.
3. In `__init__()` body, resolve the tracer:

```python
if tracer is None:
    self._tracer: TracerBase = NullTracer()
elif isinstance(tracer, type):
    self._tracer = tracer()
else:
    self._tracer = tracer
```

4. Wrap `generate_reply()` with tracing:

```python
async def generate_reply(self, message, *, modality=None, context=None, history=(), recipient="orchestrator", **options):
    await self._ensure_mcp_connected()
    trace_ctx = self._tracer.start_trace(
        "agent.run",
        agent_name=self.name,
        strategy=type(self.strategy).__name__ if self.strategy else "direct",
    )
    try:
        # ... existing logic unchanged ...
        result = await self._run_without_strategy(prompt, agent_context, runner=runner, modality=selected_modality, trace_context=trace_ctx, **options)
        # or for strategy path:
        result = await self.strategy.arun(prompt, runner=runner, context=agent_context, tools=self._agent_tool_items, **options)
        self._tracer.end_trace(trace_ctx, output=result.output)
    except Exception as exc:
        self._tracer.end_trace(trace_ctx, error=exc)
        raise AgentExecutionError(...) from exc
    ...
```

5. Pass `trace_context` to `_run_without_strategy()` and through to `_runtime().arun()`.
6. In `_runtime()` factory, pass `tracer=self._tracer`:

```python
def _runtime(self) -> AgentRuntime:
    return AgentRuntime(
        agent_name=self.name,
        system_prompt=self.system_prompt,
        tools=self.tools,
        permission_policy=self.permission_policy,
        config=self.runtime_config,
        tracer=self._tracer,
    )
```

7. In `fork()`, pass `tracer=self._tracer` to the child `BaseAgent` constructor.

---

### 6.9 `vidbyte/agents/runtime.py`

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Changes

1. Add `tracer: TracerBase | None = None` to `AgentRuntime.__init__()`. Store as `self._tracer = tracer or NullTracer()`.
2. Add `trace_context: SpanContext | None = None` parameter to `arun()`.
3. Inside the `while True` loop in `arun()`, wrap each `invoke_runner` call with an LLM span:

```python
llm_span = self._tracer.start_span(
    "llm.call",
    parent=trace_context,
    provider=provider,
    iteration=iteration_count,
)
raw_result = await invoke_runner(runner, message, **call_options)
self._tracer.end_span(llm_span, output=runner_output_text(raw_result))
```

4. In `execute_tool_call()`, wrap the execution with a tool span. Since `execute_tool_call` does not currently receive `trace_context`, add it as a parameter:

```python
async def execute_tool_call(
    self,
    call: ToolCall,
    *,
    provider: str,
    trace_context: SpanContext | None = None,
) -> tuple[ToolCallContext, ToolResult]:
    tool_span = self._tracer.start_span(
        "tool.call",
        parent=trace_context,
        tool_name=call.tool_name,
    )
    try:
        # ... existing logic ...
    finally:
        self._tracer.end_span(tool_span, output=result.output if result else None)
```

5. Update the internal `_process_tool_call()` helper to thread `trace_context` through to `execute_tool_call`.

---

### 6.10 `vidbyte/__init__.py`

**File:** `vidbyte/__init__.py`
**Type:** Modified

Add to public exports: `NullTracer`, `TracerBase`, `TracerConfigurationError` (from `vidbyte.lib.tracing` and `vidbyte.lib.errors`). Platform-specific tracers (`LangfuseTracer`, etc.) are NOT re-exported from root — developers import them directly from `vidbyte.providers.tracing`.

---

## 7. Data Model Changes

N/A — no persistence layer, no schema changes. `SpanContext` is an in-process, per-request object.

---

## 8. API Changes

N/A — this is a Python SDK with no HTTP endpoints. The public API change is the new `tracer` constructor parameter on `BaseAgent`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/tracing/__init__.py` | Export tracing contract |
| CREATE | `vidbyte/lib/tracing/base.py` | `TracerBase`, `SpanContext`, `NullTracer` |
| CREATE | `vidbyte/providers/tracing/__init__.py` | Export platform adapters |
| CREATE | `vidbyte/providers/tracing/langfuse.py` | `LangfuseTracer` adapter |
| CREATE | `vidbyte/providers/tracing/langsmith.py` | `LangSmithTracer` adapter |
| CREATE | `vidbyte/providers/tracing/phoenix.py` | `PhoenixTracer` adapter |
| MODIFY | `vidbyte/lib/errors/base.py` | Add `TracerConfigurationError` |
| MODIFY | `vidbyte/lib/errors/__init__.py` | Export new error |
| MODIFY | `vidbyte/agents/base.py` | `tracer` param, generate_reply hooks, fork propagation |
| MODIFY | `vidbyte/agents/runtime.py` | LLM + tool call spans, `tracer` in `__init__` |
| MODIFY | `vidbyte/__init__.py` | Export `TracerBase`, `NullTracer`, `TracerConfigurationError` |
| CREATE | `tests/test_tracing.py` | Unit tests for tracing integration |

**Total: 6 new files, 6 modified files.**

---

## 10. Testing Plan

### Unit Tests (`tests/test_tracing.py`)

All tests use a `RecordingTracer(TracerBase)` fake that collects calls into lists for assertion — no real platform SDKs required.

**`NullTracer`**
- `it should return a SpanContext from start_trace`
- `it should return a SpanContext from start_span`
- `it should accept end_trace with no output or error`
- `it should accept end_span with no output or error`

**`BaseAgent` tracer wiring**
- `it should default to NullTracer when tracer=None`
- `it should instantiate a tracer class when tracer=MyTracerClass is passed`
- `it should use a tracer instance directly when tracer=MyTracerInstance is passed`
- `it should call start_trace before generate_reply and end_trace after`
- `it should call end_trace with error when generate_reply raises`
- `it should propagate tracer to forked child agent`

**`AgentRuntime` span hooks**
- `it should emit one llm.call span per invoke_runner invocation`
- `it should emit one tool.call span per tool execution`
- `it should attach llm.call spans as children of the root trace context`
- `it should attach tool.call spans as children of the root trace context`
- `it should call end_span even when tool execution raises`

**`TracerConfigurationError`**
- `it should be raised when LangfuseTracer is constructed without credentials and env vars are absent`
- `it should be raised when langfuse package is not installed` (mock `ImportError`)
- `it should be raised when LangSmithTracer is constructed without api_key and env var is absent`
- `it should be raised when PhoenixTracer import fails` (mock `ImportError`)

### Integration Tests

No external platform accounts required. Validate the full agent→runtime→tracer chain using `RecordingTracer`:
- Run a `BaseAgent` with a `FakeRunner` (from existing test helpers) and `RecordingTracer`. Assert span names, parent linkage, and attribute payloads.
- Verify `fork()` child emits spans under the same tracer instance.

### Manual / QA Test Cases

1. Given a Langfuse account, when `BaseAgent(tracer=LangfuseTracer)` is run with env vars set, then a trace appears in the Langfuse UI with correct agent name, model, and tool call children.
2. Given no env vars set, when `BaseAgent(tracer=LangfuseTracer)` is constructed, then `TracerConfigurationError` is raised before any agent execution.
3. Given `tracer=LangfuseTracer(public_key="pk", secret_key="sk")`, when an agent runs, then Langfuse receives traces using the provided credentials.
4. Given `tracer=None`, when an agent runs, then performance is identical to the baseline (no tracing overhead).

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `langfuse` | `>=2.0` | Langfuse adapter | Optional; lazy-imported; not in `pyproject.toml` |
| `langsmith` | `>=0.1` | LangSmith adapter | Optional; lazy-imported; not in `pyproject.toml` |
| `opentelemetry-sdk` | `>=1.20` | Phoenix/OTel adapter | Optional; lazy-imported; not in `pyproject.toml` |
| `opentelemetry-exporter-otlp-proto-http` | `>=1.20` | OTLP export for Phoenix | Optional; lazy-imported |
| `openinference-semantic-conventions` | `>=0.1` | OTel attribute names for Phoenix | Optional; lazy-imported |

None of these are added as mandatory dependencies. The root `pyproject.toml` is not modified.

---

## 12. Rollout & Deployment

- No breaking changes. `tracer` defaults to `None` → `NullTracer`. All existing agent code is unaffected.
- No feature flags needed.
- No deployment steps — this is a library release.
- Rollback: remove `tracer` parameter handling; restore original `generate_reply` and `AgentRuntime.arun` signatures.

---

## 13. Open Questions

- [ ] Should `fork()` carry a reference to the same tracer instance (shared state, e.g. Langfuse batches) or create a fresh instantiation? Current design shares the instance — this is correct for Langfuse (single async flush queue) but should be validated for LangSmith.
- [ ] Should strategy-level LLM calls (ReAct, Reflexion, etc.) be captured in V2? If yes, strategies need to accept an optional `trace_context` kwarg.
- [ ] Should `vidbyte/providers/tracing/` adapters for Weave and AgentOps be added to V1 or deferred?
- [ ] Should `pyproject.toml` gain optional dependency groups (e.g. `[project.optional-dependencies] langfuse = ["langfuse>=2.0"]`) to give users pip-installable extras?

---

## 14. Alternatives Considered

### Alternative 1: Tracing mixin on `BaseAgent` (like `McpAttachableMixin`)
- **What:** Create a `TraceableMixin` with `attach_tracer()` builder method, matching the MCP pattern.
- **Why rejected:** MCP uses a list of servers (many-to-one); tracing uses exactly one tracer at a time. A constructor parameter is simpler and doesn't add a builder API for a single optional value.

### Alternative 2: OpenTelemetry as the sole abstraction
- **What:** Use OTel's `Tracer` protocol directly instead of `TracerBase`, making Phoenix the de facto default and exporting to other platforms via OTel exporters.
- **Why rejected:** Langfuse and LangSmith both have richer agent-specific concepts (generation vs. span, prompt/completion, token counts) that don't map cleanly onto vanilla OTel spans. A native `TracerBase` lets each adapter use platform idioms. OTel-based platforms (Phoenix) just implement `TracerBase` on top of OTel.

### Alternative 3: Decorator / context manager API rather than constructor param
- **What:** Expose `@vidbyte.trace(tracer=...)` decorator that wraps any agent run call.
- **Why rejected:** Requires more developer boilerplate. Constructor injection is more ergonomic (configure once, run many times) and consistent with how `permission_policy` and `runner` are already threaded through `BaseAgent`.

### Alternative 4: Place adapters in `vidbyte/lib/tracing/` instead of `vidbyte/providers/tracing/`
- **What:** Keep everything tracing-related under `lib/`.
- **Why rejected:** The user's explicit architecture decision. `lib/` holds shared internal infrastructure (protocol + null impl); `providers/` holds external-service adapters. This is consistent with how `providers/anthropic.py`, `providers/openai.py`, etc. are structured.
