# Design Doc: LangSmith Trace Closure Bugfixes

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-06
**Last Updated:** 2026-06-06

---

## 1. Overview

Live trace inspection of the `vidbyte-evals-mbpp` LangSmith project revealed three bugs in the SDK's LangSmith tracing adapter and the linear runtime's span-input builder. Every run in the project shows `end_time=None` and `tokens=0`, meaning the SDK creates trace runs but never successfully closes them. Additionally, `llm.call` spans for the reflexion algorithm variant are silently dropped because the span payload contains a non-JSON-serializable internal object. A third minor issue is that child span `create_run` calls omit `trace_id`, relying on LangSmith server-side inference that can race under load. This doc covers the diagnosis and the minimal targeted fixes.

---

## 2. Goals & Non-Goals

### Goals
- Fix all three bugs identified from live LangSmith trace analysis so that runs properly close with `end_time` set and token counts populated.
- Ensure the reflexion variant's `llm.call` spans land in LangSmith with full inputs instead of being silently dropped.
- Ensure child spans carry an explicit `trace_id` to prevent race-condition orphaning under concurrent eval load.
- Keep changes minimal and non-breaking — no changes to public interfaces.

### Non-Goals
- Rewriting the tracing abstraction or `TracerBase` interface.
- Fixing the `.env` naming mismatch between `LANGCHAIN_*` and `LANGSMITH_*` (tracked separately).
- Adding new tracing features or new span types.
- Changing behavior for `NullTracer`, `DebugTracer`, or any non-LangSmith tracer.
- Modifying `vidbyte-evals`.

---

## 3. Background & Context

The bugs were surfaced by querying the `vidbyte-evals-mbpp` LangSmith project via the `langsmith` Python client. Six consecutive root traces (5-minute cadence cron eval) all showed:
- `end_time = None` on the root `agent.run` chain run.
- `end_time = None` on the child `llm.call` run.
- `total_tokens = 0` on all runs.
- `llm.call` inputs limited to `{iteration: 0, provider: 'gemini'}` instead of the full `_llm_trace_inputs` payload.

**Bug 1** (`end=None`): `langsmith 0.6.7` (installed) buffers `create_run` and `update_run` in a background `TracingQueue`. The eval runs as a cron script that creates one agent, runs an eval suite, and exits. `create_run` fires early in the lifecycle, gets flushed naturally. `update_run` (called from `end_trace`/`end_span`) fires at the very end — after the suite finishes — and is sitting in the buffer when the process exits. Result: every run is permanently open.

**Bug 2** (`llm.call` spans silently dropped): `AgentRuntime._llm_trace_inputs` builds a span input dict that includes `"metadata": self._safe_trace_value(metadata)`. For the reflexion variant, `_arun_once` injects `_inner_context_window_algorithm` (an `InnerContextWindowAlgorithm` object) and `_context_window_state` (a dict with algorithm state) into `runtime_metadata`. `_safe_trace_value` filters out credential-named keys but NOT non-serializable values. When LangSmith's client attempts to JSON-serialize the payload, it fails. `_call_langsmith` catches the exception silently (`strict=False`), the `llm.call` run_id is returned but never lands in LangSmith, and `end_span` also silently no-ops on the phantom ID. The sparse `{iteration, provider}` span visible in LangSmith is from LangChain's `LANGCHAIN_TRACING_V2` auto-tracing, not the SDK.

**Bug 3** (`trace_id` missing): `LangSmithTracer.start_span` passes `parent_run_id` to `create_run` but not `trace_id`. LangSmith infers `trace_id` by walking to the root, which works in low-concurrency cases but introduces a server-side lookup that can fail or race when many runs are created rapidly (as in parallel evals). The fix is to carry the root run ID through `LangSmithSpanContext` and set it on every child `create_run`.

---

## 4. Requirements

### Functional Requirements
1. After `end_trace` and `end_span` call `update_run`, all pending buffered operations must be flushed to LangSmith before returning, so short-lived eval processes do not lose run-closure events.
2. `_llm_trace_inputs` must exclude all private runtime metadata keys (keys starting with `_`) before including `metadata` in the span payload so non-serializable internal objects never reach the LangSmith client.
3. `LangSmithSpanContext` must carry `trace_id` (root run ID). `start_span` must pass `trace_id` to `create_run` so child runs are explicitly associated with the root trace without server-side inference.
4. Existing agent runs with `NullTracer` must not be affected in any measurable way.
5. `strict=False` (default) behavior must remain: LangSmith delivery errors are caught and stored in `_last_error`, never raised.

### Non-Functional Requirements
- **Performance:** `flush()` adds latency only to `end_trace`/`end_span` calls (typically once per agent run). Acceptable for eval workloads. Production high-throughput callers may set an explicit flush strategy.
- **Correctness:** The metadata filter must use a key-prefix check, not value-type introspection, to remain resilient as internal state structures evolve.
- **Backwards compatibility:** No changes to `TracerBase`, `SpanContext`, `LangSmithSpanContext` constructor signature visible to callers. `trace_id` field defaults to `None` so existing code constructing `LangSmithSpanContext` directly still works.

---

## 5. High-Level Design

Three targeted changes across two files:

```
[BaseAgent.generate_reply]
        |
        v
[LangSmithTracer.start_trace]  ←── creates root run, stores run_id AS trace_id in SpanContext
        |
        v
[AgentRuntime._invoke_with_middleware]
        |
        v
[_llm_trace_inputs]  ←── Bug 2 fix: strip "_"-prefixed keys from metadata before serialization
        |
        v
[LangSmithTracer.start_span]  ←── Bug 3 fix: pass trace_id from parent SpanContext to create_run
        |
        v
[LangSmithTracer.end_span]  ←── Bug 1 fix: call self._client.flush() after update_run
        |
        v
[LangSmithTracer.end_trace]  ←── Bug 1 fix: call self._client.flush() after update_run
```

**Bug 1 fix** is a two-line addition: `self._client.flush()` called inside `_call_langsmith`-wrapped helpers in `end_trace` and `end_span`, after the `update_run` call succeeds (or fails silently). Since `flush()` itself may raise, it is wrapped with the same `_call_langsmith` guard.

**Bug 2 fix** is a one-line change in `AgentRuntime._llm_trace_inputs`: the `"metadata"` entry filters out `_`-prefixed keys using a dict comprehension before calling `_safe_trace_value`.

**Bug 3 fix** adds a `trace_id: str | None` field to `LangSmithSpanContext`, sets it in `start_trace` (to the root `run_id`), and threads it through `start_span` both from the parent context and into `create_run`.

---

## 6. Detailed Design

### 6.1 `LangSmithSpanContext` — add `trace_id` field

**File:** `vidbyte/providers/tracing/langsmith.py`
**Type:** Modified

#### What it does
Carries the root run's ID alongside the span's own `run_id` so child spans can explicitly declare their trace membership.

#### Interface / API
```python
@dataclass
class LangSmithSpanContext(SpanContext):
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_run_id: str | None = None
    trace_id: str | None = None  # NEW: root run ID for explicit trace association
```

#### Logic / Algorithm
1. `start_trace` creates a root run and sets `trace_id=run_id` (the root is its own trace root).
2. `start_span` reads `parent.trace_id` (if `parent` is a `LangSmithSpanContext`) and passes it both to the returned `LangSmithSpanContext` and to `create_run` as `trace_id=`.
3. No change for callers constructing `LangSmithSpanContext` directly — `trace_id` defaults to `None`, preserving backwards compatibility.

#### Edge Cases & Error Handling
- If `parent` is a base `SpanContext` (not `LangSmithSpanContext`), `trace_id` stays `None` and `create_run` omits it — same behaviour as today.
- If `trace_id=None`, `create_run` is called without the kwarg (guard with `if context.trace_id is not None`).

---

### 6.2 `LangSmithTracer.start_trace` — set `trace_id` on root context

**File:** `vidbyte/providers/tracing/langsmith.py`
**Type:** Modified

#### What it does
Returns a `LangSmithSpanContext` where `trace_id == run_id`, establishing the root of the trace tree.

#### Logic / Algorithm
1. Generate `run_id`.
2. Call `create_run` (unchanged).
3. Return `LangSmithSpanContext(run_id=run_id, trace_id=run_id)`.

---

### 6.3 `LangSmithTracer.start_span` — pass `trace_id` to child `create_run`

**File:** `vidbyte/providers/tracing/langsmith.py`
**Type:** Modified

#### What it does
Creates a child run in LangSmith with an explicit `trace_id` so the server does not need to infer it from `parent_run_id`.

#### Logic / Algorithm
1. Resolve `parent_run_id` and `trace_id` from `parent` if it is a `LangSmithSpanContext`.
2. Build `create_run` kwargs; add `trace_id=trace_id` only if `trace_id` is not `None`.
3. Return `LangSmithSpanContext(run_id=run_id, parent_run_id=parent_run_id, trace_id=trace_id)`.

#### Edge Cases & Error Handling
- Non-`LangSmithSpanContext` parents: `trace_id` omitted, `parent_run_id` omitted — no regression.

---

### 6.4 `LangSmithTracer.end_trace` and `end_span` — flush after `update_run`

**File:** `vidbyte/providers/tracing/langsmith.py`
**Type:** Modified

#### What it does
Forces the langsmith client to drain its background `TracingQueue` before returning, ensuring short-lived eval processes do not lose run-closure events.

#### Logic / Algorithm
1. Call `update_run` via `_call_langsmith` as today.
2. Immediately call `self._call_langsmith("flush", self._client.flush)` (no args/kwargs). This blocks until all buffered payloads are delivered.
3. If `flush()` raises (network error, auth failure), `_call_langsmith` catches it and stores it in `_last_error`. The caller is unaffected.

#### Edge Cases & Error Handling
- `flush()` after a failed `update_run`: still runs. It flushes any other pending operations (e.g., the root span's `create_run` if called late). This is intentional and correct.
- Long-running agents with many tool calls: `flush()` is only called at end-of-trace or end-of-span, not per model call. Overhead is bounded.
- Callers using `strict=True`: `_call_langsmith` re-raises on flush failure too, consistent with existing behavior.

---

### 6.5 `AgentRuntime._llm_trace_inputs` — filter private metadata keys

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Prevents non-JSON-serializable internal runtime state objects from reaching the LangSmith `create_run` payload.

#### Interface / API
```python
def _llm_trace_inputs(self, handle, message, call_options, provider, iteration_count, model_call_count, metadata) -> dict[str, Any]:
    # Builds sanitized, inspectable model-call inputs for trace providers.
    ...
    public_metadata = {k: v for k, v in dict(metadata).items() if not k.startswith("_")}
    inputs: dict[str, Any] = {
        ...
        "metadata": self._safe_trace_value(public_metadata),
        ...
    }
```

#### Logic / Algorithm
1. Before building the `inputs` dict, create `public_metadata` by filtering `metadata` to only keys that do NOT start with `_`.
2. Pass `public_metadata` (not `metadata`) to `_safe_trace_value` for the `"metadata"` entry.
3. All other keys in `inputs` are unchanged.

#### Edge Cases & Error Handling
- Metadata with zero public keys: `"metadata"` becomes `{}` in the payload — valid, no crash.
- Future private keys added to `runtime_metadata`: automatically excluded by the prefix rule without requiring changes here.
- Public metadata containing non-serializable custom objects: `_safe_trace_value` already handles nested dicts and lists; this fix just ensures the private runtime objects never enter that path.

---

## 7. Data Model Changes

N/A — no schema or data model changes. `LangSmithSpanContext.trace_id` is an in-process runtime field only; it is not persisted.

---

## 8. API Changes

N/A — no HTTP, MCP, or public Python API changes. All modifications are internal to `LangSmithTracer` and `AgentRuntime`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/providers/tracing/langsmith.py` | Add `trace_id` to `LangSmithSpanContext`; set it in `start_trace`; thread it in `start_span`; add `flush()` call in `end_trace` and `end_span` |
| MODIFY | `vidbyte/agents/runtime.py` | Filter `_`-prefixed keys from `metadata` in `_llm_trace_inputs` before serialization |

---

## 10. Testing Plan

Per the task instructions, no test scripts or test files are required for this request.

---

## 11. Dependencies & External Services

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| `langsmith` | 0.6.7 (installed) | LangSmith Python client; `Client.flush()` must be available | `flush()` exists in 0.1+ — low risk for installed version |

---

## 12. Rollout & Deployment

- No feature flags needed.
- Not a breaking change — public interfaces are unchanged.
- `flush()` adds synchronous latency to `end_trace`/`end_span`. For eval workloads this is desirable; for high-frequency production agents using `LangSmithTracer`, callers may wish to set `strict=False` (default) and accept that `flush()` failures are silent.
- Rollback: revert the two files. No migration needed.

---

## 13. Open Questions

- [ ] Does `langsmith.Client.flush()` in 0.6.7 behave as expected (blocks until queue drained)? Should be verified at runtime — `_call_langsmith` wrapping makes it safe either way.
- [ ] Should `flush()` be gated on a new `LangSmithTracer(auto_flush=True)` param for high-throughput callers who prefer async delivery? Left as a follow-up; default behavior after this fix is strictly better for eval use cases.

---

## 14. Alternatives Considered

### Alternative 1: Use `atexit` to flush on process exit
- What: Register `client.flush()` via `atexit.register` in `LangSmithTracer.__init__`.
- Why rejected: `atexit` handlers are not guaranteed to run when the process is killed (e.g., `SIGKILL`, asyncio task cancellation). The explicit `flush()` in `end_trace`/`end_span` is synchronous and deterministic.

### Alternative 2: Switch to `langsmith.run_trees.RunTree` (higher-level API)
- What: Replace `create_run`/`update_run` calls with the `RunTree` context-manager API which handles flushing automatically.
- Why rejected: Would require rewriting `LangSmithTracer` substantially and changing `LangSmithSpanContext`. Out of scope for a targeted bugfix.

### Alternative 3: Filter non-serializable values in `_safe_trace_value` by type
- What: In `_safe_trace_value`, catch `TypeError` on non-JSON-serializable objects and replace with a string placeholder.
- Why rejected: Catches symptoms, not the cause. The private runtime state (`_inner_context_window_algorithm`) should never be in a trace payload at all. The key-prefix filter is the right guardrail and is self-maintaining as new private keys are added.
