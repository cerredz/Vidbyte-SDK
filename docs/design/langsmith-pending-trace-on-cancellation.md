# Design Doc: LangSmith Pending Trace on Cancellation (#142)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-15
**Last Updated:** 2026-06-15

---

## 1. Overview

Root `agent.run` traces and child `llm.call` spans opened in LangSmith can remain permanently `pending` when an agent run is interrupted by a `BaseException` subclass (most commonly `asyncio.CancelledError`, but also `KeyboardInterrupt` or `SystemExit`). Both `generate_reply` in `base.py` and `_invoke_with_middleware` in `runtime.py` use `except Exception` guards, which do not catch `BaseException`. The fix widens the catch scope at each of the two trace-close sites to include `BaseException` without changing any happy-path behavior.

---

## 2. Goals & Non-Goals

### Goals
- Ensure every `start_trace` call has a matching `end_trace` call, even when the run is cancelled via `asyncio.CancelledError` or another `BaseException`.
- Ensure every `start_span("llm.call")` call has a matching `end_span` call under the same conditions.
- Update `TracerBase`, `LangSmithTracer`, and `RecordingTracer` type hints so `error` accepts `BaseException | None` instead of `Exception | None`.
- Preserve the existing happy-path trace behavior and the existing `except Exception → AgentExecutionError` re-raise chain.

### Non-Goals
- Changing the retry / abort logic in `on_model_error` middleware.
- Adding new trace fields or metadata beyond what already exists.
- Fixing the same gap in non-LangSmith tracers (Langfuse, continual); those adapters already accept arbitrary exceptions via `str(error)`.

---

## 3. Background & Context

In Python 3.8+, `asyncio.CancelledError` was promoted from `Exception` to `BaseException`. An eval harness cancelling an `asyncio.Task` (via `task.cancel()` or a timeout context) raises `CancelledError` inside the awaited coroutine. Because neither `generate_reply` nor `_invoke_with_middleware` catch `BaseException`, the cancellation propagates out before `end_trace` / `end_span` is reached, leaving the LangSmith runs in a permanent `pending` state.

The trace evidence confirms this: trace `973e...` shows 2 pending runs (the root `agent.run` and the final `llm.call` span) — precisely the two spans whose close paths are guarded by `except Exception`.

A previous fix in PR #133 (`langsmith-trace-closure-bugfixes`) already addressed `flush` ordering and `trace_id` threading; this issue is a distinct gap in the cancellation path.

---

## 4. Requirements

### Functional Requirements
1. A root `agent.run` trace opened by `generate_reply` must be closed (via `end_trace`) regardless of whether `_run_direct` returns normally, raises an `Exception`, or raises a `BaseException` (e.g. `CancelledError`).
2. An `llm.call` span opened by `_invoke_with_middleware` must be closed (via `end_span`) regardless of whether `handle.invoke` returns normally, raises an `Exception`, or raises a `BaseException`.
3. When a `BaseException` (non-`Exception`) causes trace closure, the trace must be marked with an error string so it reaches a terminal state (not success).
4. The `BaseException` must be re-raised unchanged after the trace is closed.
5. The `except Exception → AgentExecutionError` re-raise chain must be unaffected.

### Non-Functional Requirements
- Zero change to trace output or LangSmith API calls in the happy path.
- No new dependencies.
- The type annotation `error: Exception | None` in `TracerBase.end_trace`, `TracerBase.end_span`, `LangSmithTracer.end_trace`, and `LangSmithTracer.end_span` must be widened to `BaseException | None` for accuracy.

---

## 5. High-Level Design

Two independent call sites need a `BaseException` catch clause added after their existing `Exception` clause:

```
generate_reply (base.py)
  try:
    start_trace(...)          ← opens root trace
    _run_direct(...)          ← may raise CancelledError
    end_trace(..., output)    ← only reached on success
  except Exception:
    end_trace(..., error)     ← reached on Exception
    raise AgentExecutionError
  except BaseException:       ← NEW: catches CancelledError etc.
    end_trace(..., error)
    raise

_invoke_with_middleware (runtime.py)
  llm_span = start_span(...)
  try:
    handle.invoke(...)
    end_span(..., output)
    return
  except Exception:
    end_span(..., error)
    on_model_error / retry / raise
  except BaseException:       ← NEW: catches CancelledError etc.
    end_span(..., error)
    raise
```

The type annotation change in `TracerBase` is a supporting correctness fix: `str(exc)` already works for any `BaseException`, so the LangSmith adapter behavior does not change — only the static types are corrected.

---

## 6. Detailed Design

### 6.1 `generate_reply` — `vidbyte/agents/base.py`

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What it does
`generate_reply` is the public entry point. It opens a root `agent.run` trace before calling `_run_direct` and closes it on success or `Exception`. The new `except BaseException` clause closes the trace when a non-`Exception` (e.g. `CancelledError`) propagates out, then re-raises unconditionally.

#### Interface / API
No signature change.

#### Logic / Algorithm
Current structure (simplified):
```python
try:
    trace_ctx = self._tracer.start_trace(...)
    result = await self._run_direct(...)
    self._tracer.end_trace(trace_ctx, output=result.output)
except Exception as exc:
    self._tracer.end_trace(trace_ctx, error=exc)
    raise AgentExecutionError(...) from exc
```

New structure:
```python
try:
    trace_ctx = self._tracer.start_trace(...)
    result = await self._run_direct(...)
    self._tracer.end_trace(trace_ctx, output=result.output)
except Exception as exc:
    if trace_ctx is not None:
        self._tracer.end_trace(trace_ctx, error=exc)
    self._active_prompt = ""
    raise AgentExecutionError(...) from exc
except BaseException as exc:
    if trace_ctx is not None:
        self._tracer.end_trace(trace_ctx, error=exc)
    self._active_prompt = ""
    raise
```

#### Edge Cases & Error Handling
- If `start_trace` itself raises (unlikely but possible in strict mode), `trace_ctx` stays `None` and the guard `if trace_ctx is not None` skips double-close.
- `_active_prompt` is reset in both exception paths, matching current behavior.

---

### 6.2 `_invoke_with_middleware` — `vidbyte/agents/runtime.py`

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
`_invoke_with_middleware` opens a child `llm.call` span, calls `handle.invoke`, then closes the span. The new `except BaseException` clause closes the span when cancellation propagates through the `handle.invoke` await, then re-raises.

#### Interface / API
No signature change.

#### Logic / Algorithm
Current structure (simplified):
```python
llm_span = self._tracer.start_span("llm.call", ...)
try:
    raw_result = await handle.invoke(message, **current_call_options)
    output_text = handle.extract_text(raw_result)
    self._tracer.end_span(llm_span, output=output_text)
    return raw_result, model_call_count
except Exception as exc:
    self._tracer.end_span(llm_span, error=exc)
    decision = await self.middleware.on_model_error(...)
    if decision.action is MiddlewareAction.RETRY:
        continue
    if decision.action is MiddlewareAction.ABORT_RUN:
        return (self._middleware_abort_result(...), model_call_count)
    raise
```

New structure — add a `except BaseException` after the `except Exception` block, inside the `while True` retry loop:
```python
llm_span = self._tracer.start_span("llm.call", ...)
try:
    raw_result = await handle.invoke(message, **current_call_options)
    output_text = handle.extract_text(raw_result)
    self._tracer.end_span(llm_span, output=output_text)
    return raw_result, model_call_count
except Exception as exc:
    self._tracer.end_span(llm_span, error=exc)
    # ... existing on_model_error / retry / abort / raise logic unchanged ...
except BaseException as exc:
    self._tracer.end_span(llm_span, error=exc)
    raise
```

#### Edge Cases & Error Handling
- The `except BaseException` is inside the `while True` retry loop — a cancellation breaks out of the loop entirely via `raise`, which is correct.
- The `except Exception` path's retry/abort logic is untouched.

---

### 6.3 `TracerBase` type hint update — `vidbyte/lib/tracing/base.py`

**File:** `vidbyte/lib/tracing/base.py`
**Type:** Modified

#### What it does
Widens the `error` parameter type from `Exception | None` to `BaseException | None` in `end_trace` and `end_span` abstract method signatures, and in `NullTracer`'s concrete implementations.

#### Interface / API
```python
@abstractmethod
def end_trace(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...

@abstractmethod
def end_span(self, context: SpanContext, *, output: str | None = None, error: BaseException | None = None) -> None: ...
```

---

### 6.4 `LangSmithTracer` type hint update — `vidbyte/providers/tracing/langsmith.py`

**File:** `vidbyte/providers/tracing/langsmith.py`
**Type:** Modified

#### What it does
Widens `error` parameter type from `Exception | None` to `BaseException | None` in `end_trace` and `end_span`. No behavior change — `str(error)` already works for any `BaseException`.

---

### 6.5 `RecordingTracer` type hint update — `tests/test_tracing.py`

**File:** `tests/test_tracing.py`
**Type:** Modified

#### What it does
Updates `end_trace` and `end_span` signatures in `RecordingTracer` to match the widened `TracerBase` contract.

---

## 7. Data Model Changes

N/A — no schema or data model changes.

---

## 8. API Changes

N/A — no HTTP endpoints affected.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/agents/base.py` | Add `except BaseException` in `generate_reply` to close root trace on cancellation |
| MODIFY | `vidbyte/agents/runtime.py` | Add `except BaseException` in `_invoke_with_middleware` to close `llm.call` span on cancellation |
| MODIFY | `vidbyte/lib/tracing/base.py` | Widen `error` type to `BaseException | None` in abstract signatures |
| MODIFY | `vidbyte/providers/tracing/langsmith.py` | Widen `error` type to `BaseException | None` in concrete implementations |
| MODIFY | `tests/test_tracing.py` | Update `RecordingTracer` signatures to match widened contract; add cancellation test cases |

---

## 10. Testing Plan

### Unit Tests

**`test_tracing.py` — new cases for `RecordingTracer` / `BaseAgent`:**

- `describe('generate_reply cancellation')` → `it('closes root trace when CancelledError is raised during _run_direct')` — [Hidden Failure]: run is cancelled mid-way, previously left trace pending
- `describe('generate_reply cancellation')` → `it('re-raises CancelledError unchanged after closing trace')` — [Hidden Assumption]: callers expect CancelledError to propagate
- `describe('generate_reply cancellation')` → `it('sets end_trace error to the CancelledError instance')` — [Silent Failure]: trace might be closed with no error vs. the actual exception
- `describe('generate_reply cancellation')` → `it('resets _active_prompt even when CancelledError is raised')` — [Edge Case]: agent state must be clean after cancellation
- `describe('_invoke_with_middleware cancellation')` → `it('closes llm.call span when CancelledError is raised by handle.invoke')` — [Hidden Failure]: matches the second pending span observed in the trace
- `describe('_invoke_with_middleware cancellation')` → `it('re-raises CancelledError after closing llm.call span')` — [Hidden Assumption]: cancellation must propagate out of the retry loop
- `describe('generate_reply cancellation')` → `it('does not double-close trace when start_trace succeeds but _run_direct raises CancelledError')` — [Edge Case]: guard `if trace_ctx is not None` correctness
- `describe('generate_reply error path')` → `it('still wraps Exception in AgentExecutionError when non-BaseException is raised')` — [Silent Failure]: existing behavior must not regress
- `describe('TracerBase contract')` → `it('end_trace accepts a BaseException as error without TypeError')` — [Hidden Assumption]: type widening is backward-compatible

### Integration Tests
- A full `generate_reply` run using an `AlwaysDoneRunner`-style fake that raises `asyncio.CancelledError` on the first `handle.invoke` call should produce exactly one closed trace entry in `RecordingTracer.traces_ended` with a non-None `error`.
- The same run should produce exactly one closed span entry in `RecordingTracer.spans_ended` with a non-None `error`.
- Existing passing tests in `test_tracing.py` must continue to pass without modification (happy path).

### Manual / QA Test Cases
1. Given a `BaseAgent` with a `LangSmithTracer`, when the agent task is cancelled via `asyncio.Task.cancel()` mid-run, then the LangSmith root run must not remain in `pending` state — [Hidden Failure]
2. Given a completed agent run, when inspecting LangSmith, then the root run must have `end_time` set and `outputs` populated — [Edge Case, regression check]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `langsmith` | Optional, installed by user | LangSmith client | None — no API change |
| `asyncio` | stdlib | `CancelledError` source | None |

---

## 12. Rollout & Deployment

- No feature flags. The fix is unconditionally applied.
- Not a breaking change: widening `error: Exception | None` to `error: BaseException | None` is backward-compatible — existing callers passing `Exception` instances continue to work.
- No deployment ordering required.
- Rollback: revert the two `except BaseException` additions if any regression is observed; the type hint changes are cosmetic.

---

## 13. Open Questions

- [ ] Should other tracers (Langfuse, OpenTelemetry if added later) also have their type hints widened in this PR, or deferred?
- [ ] Is `asyncio.CancelledError` the only `BaseException` subclass seen in practice, or have `KeyboardInterrupt` / `SystemExit` also been observed in eval harness runs?

---

## 14. Alternatives Considered

### Alternative 1: `try/finally` with a sentinel flag
Use a `finally` block and track whether the trace was already closed via a boolean flag.
- What: `_trace_closed = False` set to `True` in both success and error branches; `finally` checks the flag before calling `end_trace`.
- Why rejected: More state to track and more lines changed than adding a focused `except BaseException` clause. The dual-except pattern is idiomatic Python and directly mirrors the existing structure.

### Alternative 2: Catch `BaseException` in the single `except` clause
Change `except Exception` to `except BaseException` in the existing blocks.
- What: Replace `except Exception as exc:` with `except BaseException as exc:` and add `if isinstance(exc, Exception): raise AgentExecutionError(...) from exc; raise` logic.
- Why rejected: The existing `except Exception` block has specific handling (wrapping into `AgentExecutionError`) that should not apply to `CancelledError`. Separating the two clauses is cleaner and more explicit.
