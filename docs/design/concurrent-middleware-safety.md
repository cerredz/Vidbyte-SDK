# Design Doc: Concurrent Middleware Safety — Per-Run State Isolation

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-29
**Last Updated:** 2026-05-29

---

## 1. Overview

Five builtin middleware classes store per-run mutable state in instance variables and reset that state via `before_run`. When a single middleware instance is shared across two concurrent agent runs — which happens inside `ParallelPipeline`, in server deployments, and any time `agent.run()` is called from multiple coroutines — asyncio context switches at `await` boundaries allow Run B's `before_run` to clear Run A's accumulated state mid-flight. This silently disables safety guarantees (confused-deputy detection, loop detection, retry counting) without any exception or log entry. The fix moves all per-run state out of middleware instances and into a per-run `run_state` dict that is scoped to a single `_arun_once` call and threaded through `MiddlewareContext`.

---

## 2. Goals & Non-Goals

### Goals
- Eliminate shared-instance data races for `ModelRetryMiddleware`, `ConfusedDeputyGuardMiddleware`, `LoopDetectionMiddleware`, and `TokenRateLimitMiddleware` by scoping their mutable state to individual runs via `MiddlewareContext.run_state`.
- Make `CircuitBreakerMiddleware` safe for concurrent access by protecting its intentionally cross-run state with `asyncio.Lock`.
- Preserve all existing middleware semantics (detection thresholds, retry counts, rate-limit windows) unchanged for single-run usage.
- Add concurrency tests that would have caught the original bug.
- Update existing tests that asserted on private instance variables to assert on behavior instead.

### Non-Goals
- Refactoring `CanaryTripwireMiddleware`, `HoneypotToolMiddleware`, `AuditLogMiddleware`, or any other builtin not listed above (though they may have the same pattern).
- Adding distributed/multi-process state sharing for circuit breakers.
- Changing the public API of `AgentMiddleware`, `MiddlewarePipeline`, or `BaseAgent`.
- Introducing any form of transaction or atomicity across multiple middleware in a pipeline.

---

## 3. Background & Context

### The corruption path — traced from `await agent.run()`

```
BaseAgent.run() / BaseAgent.arun()
  └─ BaseAgent.generate_reply()
       └─ BaseAgent._run_direct()
            └─ BaseAgent._runtime()           # creates a NEW AgentRuntime each call,
                 AgentRuntime.__init__()       #   but `self.middleware` is the same tuple
                   MiddlewarePipeline(middleware)  # wraps the SAME AgentMiddleware instances
            └─ AgentRuntime.arun()
                 └─ AgentRuntime._arun_once()
                      await middleware.before_run(ctx)   # calls mw.before_run(ctx)
                                                          # which writes mw._attempts = 0
```

`BaseAgent._runtime()` (line 441–453 of `agents/base.py`) calls `AgentRuntime(middleware=self.middleware, ...)`. `self.middleware` is `tuple(middleware)` set in `__init__`. Each `arun` call constructs a fresh `AgentRuntime` with the same middleware tuple. The `MiddlewarePipeline` wraps those same instances. So every concurrent call to `agent.arun()` ends up with a different `AgentRuntime` and `MiddlewarePipeline` wrapper, but the **same** `AgentMiddleware` objects. When two coroutines run concurrently (e.g. from `asyncio.gather`), both call `await middleware.before_run(ctx)` and both write to `mw._attempts`, `mw._tool_outputs`, etc.

### Why asyncio makes this certain, not just possible

asyncio's cooperative multitasking switches tasks at every `await`. `before_run`, `before_tool_call`, and every other hook is called with `await getattr(middleware, hook.value)(ctx)` inside `MiddlewarePipeline._run()`. Between the `await self.middleware.before_run(...)` line in Run A and the next line in Run A, Run B's `before_run` can execute, clearing shared state.

### CircuitBreakerMiddleware — intentional cross-run state

`CircuitBreakerMiddleware` is the exception: its `_state`, `_error_timestamps`, and `_opened_at` are designed to persist across runs. That is the whole point of a circuit breaker — it accumulates errors from many calls and trips the circuit for future calls. Moving this state to `run_state` would break the feature. Instead, concurrent access to this state must be serialized with `asyncio.Lock`.

---

## 4. Requirements

### Functional Requirements

1. After the fix, two concurrent runs sharing a `ModelRetryMiddleware` instance must each track their own independent `_attempts` counter. Run B's `before_run` must not reset Run A's counter.
2. After the fix, two concurrent runs sharing a `ConfusedDeputyGuardMiddleware` instance must each accumulate their own `_tool_outputs`. Run B's `before_run` must not clear Run A's accumulated outputs.
3. After the fix, two concurrent runs sharing a `LoopDetectionMiddleware` instance must each maintain their own `_call_history` deque. Run B must not corrupt Run A's loop detection window.
4. After the fix, two concurrent runs sharing a `TokenRateLimitMiddleware` instance must each track their own `_window_tokens`/`_window_started`. Run B's window reset must not affect Run A's token accounting.
5. After the fix, `CircuitBreakerMiddleware` must correctly serialize concurrent access to `_state`, `_error_timestamps`, `_opened_at`, and `_half_open_calls` using `asyncio.Lock` so no concurrent corruption of the cross-run state occurs.
6. All existing single-run middleware tests must continue to pass with no behavioral change.
7. `MiddlewareContext` must expose a `run_state` field (mutable dict keyed by middleware type) that middleware can read and write during a run.
8. `AgentRuntime._arun_once` must create one fresh `run_state` dict per run invocation and thread it through every `_middleware_context` call within that run.
9. `before_run` in each affected middleware must initialize its per-run state dataclass in `ctx.run_state[self.__class__]`.
10. All other hooks in each affected middleware must read state from `ctx.run_state[self.__class__]` with a safe fallback if state is absent (lazy initialization or no-op).

### Non-Functional Requirements

- **Performance:** The `run_state` dict lookup (`ctx.run_state.get(T)`) is O(1) and negligible compared to the `await` overhead of each hook call. No performance impact.
- **Concurrency:** The asyncio.Lock added to `CircuitBreakerMiddleware` is non-blocking for CLOSED state (fast path acquires and releases lock immediately). Contended cases only occur when the circuit is tripping or recovering, which is intentionally a slow path.
- **Backward compatibility:** The `run_state` field has a default of `{}`, so existing callsites that construct `MiddlewareContext` without `run_state` continue to work.
- **Observability:** No change to middleware events, decisions, or metadata. The fix is invisible to callers.
- **Security:** The confused-deputy and canary tripwire guarantees are restored, not weakened. No new information is exposed.

---

## 5. High-Level Design

The root cause is that middleware instances act as both **configuration holders** and **per-run state stores**. The fix separates these two concerns: instances hold only configuration (thresholds, windows, max counts), while per-run mutable data lives in a per-run dict that is created fresh by `AgentRuntime._arun_once` and flows through `MiddlewareContext`.

```
_arun_once():
  run_state = {}                     ← ONE dict per run, created here
  ...
  ctx = MiddlewareContext(..., run_state=run_state)
    → middleware.before_run(ctx)     ← middleware writes ctx.run_state[self.__class__] = RunState(...)
    → middleware.before_tool_call(ctx) ← middleware reads ctx.run_state[self.__class__]
```

`MiddlewareContext` gains a `run_state: dict[type, Any]` field with `default_factory=dict`. Because `MiddlewareContext` is `frozen=True`, no field can be *reassigned*, but the dict itself is mutable: `ctx.run_state[K] = V` is legal even on a frozen dataclass.

For `CircuitBreakerMiddleware`, all state remains on the instance (cross-run by design). An `asyncio.Lock` is added to the `__init__` and acquired around every read-modify-write operation on `_state`, `_error_timestamps`, `_opened_at`, and `_half_open_calls`.

---

## 6. Detailed Design

### 6.1 `MiddlewareContext` — add `run_state` field

**File:** `vidbyte/lib/dataclasses/middleware.py`
**Type:** Modified

#### What it does
Carries a shared mutable dict from the runtime into every middleware hook within a single run. The dict is keyed by middleware type (the class itself) and stores per-run state dataclass instances.

#### Interface / API
```python
@dataclass(frozen=True, slots=True)
class MiddlewareContext:
    ...
    run_state: dict[type, Any] = field(default_factory=dict)
```

Because `frozen=True` only prevents field *reassignment*, middleware can mutate the dict in place:
```python
ctx.run_state[self.__class__] = MyRunState(...)  # legal — mutating the dict, not reassigning the field
```

#### Edge Cases & Error Handling
- Existing `MiddlewareContext(hook=..., agent_name=...)` call-sites omit `run_state` and receive an empty dict by default — no changes required at call-sites that don't need per-run state.
- Middleware that reads `ctx.run_state.get(self.__class__)` and receives `None` must handle the absent-state case gracefully (skip or no-op).

---

### 6.2 `AgentRuntime._arun_once` and `_middleware_context` — thread `run_state`

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Creates one `run_state` dict at the top of `_arun_once` and passes it to every `_middleware_context` invocation within that call, guaranteeing all hooks for the same run share the same dict while concurrent runs each get their own.

#### Interface / API
```python
async def _arun_once(self, message, *, ...) -> AgentResult:
    # ...existing setup...
    run_state: dict[type, Any] = {}   # ← new: one dict per run
    # Every _middleware_context call gains: run_state=run_state

def _middleware_context(self, hook, *, ..., run_state: dict[type, Any] | None = None) -> MiddlewareContext:
    return MiddlewareContext(
        ...,
        run_state=run_state or {},
    )
```

#### Logic / Algorithm
1. At the top of `_arun_once`, before calling `middleware.before_run`, add `run_state: dict[type, Any] = {}`.
2. Modify every call to `self._middleware_context(...)` in `_arun_once` to pass `run_state=run_state`.
3. The same `run_state` dict is also forwarded to `_invoke_with_middleware`, `_process_tool_call`, and `_finish_result` by adding it to their signatures as a keyword argument.
4. `_middleware_context` gains a `run_state: dict[type, Any] | None = None` keyword parameter and passes `run_state=run_state or {}` to `MiddlewareContext`.

#### Edge Cases & Error Handling
- `_finish_result` is called from many places; all call-sites are in `_arun_once` and will receive the same `run_state` after this change.
- `AgentRuntimeContextAlgorithms.arun` is called before `_arun_once` in some paths — that path does not currently use `run_state` and needs no change for now (it would need `run_state` if/when its middleware hooks are added).

---

### 6.3 `ModelRetryMiddleware` — per-run `_attempts`

**File:** `vidbyte/middleware/builtins/retry.py`
**Type:** Modified

#### What it does
Tracks the number of model-call errors within a single run to enforce `max_attempts`. After the fix the instance holds only configuration (`max_attempts`, `sleep_seconds`).

#### Interface / API
```python
@dataclass
class _ModelRetryRunState:
    attempts: int = 0

class ModelRetryMiddleware(AgentMiddleware):
    def __init__(self, *, max_attempts: int = 2, sleep_seconds: float = 0) -> None:
        # configuration only — no mutable per-run state

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        ctx.run_state[self.__class__] = _ModelRetryRunState()
        return MiddlewareDecision.continue_()

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        state: _ModelRetryRunState = ctx.run_state.get(self.__class__) or _ModelRetryRunState()
        state.attempts += 1
        ctx.run_state[self.__class__] = state
        ...
```

#### Logic / Algorithm
1. Remove `self._attempts = 0` from `__init__`.
2. Add `_ModelRetryRunState` dataclass with `attempts: int = 0`.
3. `before_run`: write `ctx.run_state[self.__class__] = _ModelRetryRunState()`.
4. `on_model_error`: read state with `.get(self.__class__) or _ModelRetryRunState()`, increment, write back (needed because the dataclass may not be frozen — but writing back ensures the new value is persisted even if we started from the fallback).

#### Edge Cases & Error Handling
- If `on_model_error` is somehow called before `before_run` (not a normal runtime flow), the fallback `_ModelRetryRunState()` starts at `attempts=0` — safe.

---

### 6.4 `ConfusedDeputyGuardMiddleware` — per-run `_user_message` and `_tool_outputs`

**File:** `vidbyte/middleware/builtins/confused_deputy.py`
**Type:** Modified

#### What it does
Detects confused-deputy attacks by checking if tool call arguments are verbatim copies of prior tool results. Requires per-run accumulation of tool outputs and the original user message.

#### Interface / API
```python
@dataclass
class _ConfusedDeputyRunState:
    user_message: str = ""
    tool_outputs: list[str] = field(default_factory=list)

class ConfusedDeputyGuardMiddleware(AgentMiddleware):
    def __init__(self, *, max_external_content_ratio: float = 0.6,
                 min_argument_length: int = 20, abort_reason: str = "confused_deputy_detected") -> None:
        # configuration only

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        ctx.run_state[self.__class__] = _ConfusedDeputyRunState(user_message=ctx.message)
        return MiddlewareDecision.continue_()
```

#### Logic / Algorithm
1. Remove `self._user_message`, `self._tool_outputs` from `__init__`.
2. Add `_ConfusedDeputyRunState` dataclass.
3. `before_run`: initialize fresh state with `user_message=ctx.message`.
4. `after_tool_call`: read state, append to `state.tool_outputs` if `ctx.tool_result` has output.
5. `before_tool_call`: read state, pass `state.tool_outputs` into `_check_arguments`.
6. All private logic methods (`_check_arguments`, `_max_overlap_ratio`, `_longest_common_substring_length`) remain on the class as instance/static methods — they are pure functions that receive data rather than reading from instance state.

#### Edge Cases & Error Handling
- If `before_run` was never called (unit-test scenario calling hooks in isolation), fallback to an empty `_ConfusedDeputyRunState()`.
- `_check_arguments` already early-returns if `tool_outputs` is empty.

---

### 6.5 `LoopDetectionMiddleware` — per-run `_call_history`

**File:** `vidbyte/middleware/builtins/loop_detection.py`
**Type:** Modified

#### What it does
Detects when the same tool call is repeated consecutively beyond a threshold. The `_call_history` deque is scoped per-run because loop detection must reset between independent requests.

#### Interface / API
```python
@dataclass
class _LoopDetectionRunState:
    call_history: deque[str] = field(default_factory=lambda: collections.deque())

class LoopDetectionMiddleware(AgentMiddleware):
    def __init__(self, *, max_repeated_calls: int = 3, window: int = 10,
                 skip_internal_tools: bool = True) -> None:
        # configuration only — no mutable deque here

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        ctx.run_state[self.__class__] = _LoopDetectionRunState(
            call_history=collections.deque(maxlen=self.window)
        )
        return MiddlewareDecision.continue_()
```

#### Logic / Algorithm
1. Remove `self._call_history` from `__init__`.
2. Add `_LoopDetectionRunState` with `call_history: deque[str]`.
3. `before_run`: initialize `_LoopDetectionRunState(call_history=deque(maxlen=self.window))`.
4. `before_tool_call`: read state from `ctx.run_state`, operate on `state.call_history`, then call `_count_consecutive_tail` (which is already a pure method taking `key`).
5. `_make_key` and `_count_consecutive_tail` are already pure — no changes needed.

#### Edge Cases & Error Handling
- If `before_run` was skipped, fallback to `_LoopDetectionRunState(call_history=deque(maxlen=self.window))` on first `before_tool_call`.

---

### 6.6 `TokenRateLimitMiddleware` — per-run `_window_started`, `_window_tokens`, `_last_tokens_seen`

**File:** `vidbyte/middleware/builtins/rate_limit.py`
**Type:** Modified

#### What it does
Throttles iteration speed when token usage within a rolling window exceeds `max_tokens`. Semantics are per-run (each agent run gets its own token window).

#### Interface / API
```python
@dataclass
class _TokenRateLimitRunState:
    window_started: float = 0.0
    window_tokens: int = 0
    last_tokens_seen: int | None = None

class TokenRateLimitMiddleware(AgentMiddleware):
    def __init__(self, *, max_tokens: int, per_seconds: float,
                 clock: Callable[[], float] | None = None) -> None:
        # configuration only

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        ctx.run_state[self.__class__] = _TokenRateLimitRunState(window_started=self.clock())
        return MiddlewareDecision.continue_()
```

#### Logic / Algorithm
1. Remove `self._window_started`, `self._window_tokens`, `self._last_tokens_seen` from `__init__`.
2. Add `_TokenRateLimitRunState` dataclass.
3. `before_run`: initialize fresh state with `window_started=self.clock()`.
4. `before_iteration`: read state with lazy initialization fallback, mutate in place, write back.

#### Edge Cases & Error Handling
- Existing tests call `before_iteration` without `before_run` — lazy init creates fresh state with `window_started=self.clock()` so the first window starts from that moment.

---

### 6.7 `CircuitBreakerMiddleware` — asyncio.Lock for cross-run state

**File:** `vidbyte/middleware/builtins/circuit_breaker.py`
**Type:** Modified

#### What it does
Three-state circuit breaker whose state (`_state`, `_error_timestamps`, `_opened_at`, `_half_open_calls`) intentionally persists across agent runs. Requires explicit serialization for concurrent access.

#### Interface / API
```python
class CircuitBreakerMiddleware(AgentMiddleware):
    def __init__(self, ...) -> None:
        ...
        self._lock = asyncio.Lock()       # ← new: protects all state mutations

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return MiddlewareDecision.continue_()
            ...

    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        async with self._lock:
            ...

    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision:
        async with self._lock:
            ...
```

#### Logic / Algorithm
1. Add `self._lock = asyncio.Lock()` to `__init__` after parameter validation.
2. Wrap the body of `before_model_call`, `after_model_response`, and `on_model_error` with `async with self._lock:`.
3. All private state-mutation helpers (`_handle_open_state`, `_handle_half_open_state`, `_record_error_and_maybe_open`, `_prune_error_window`, `_transition_to_open`, `_transition_to_closed`) are called from within the lock context and require no changes.
4. The `state` property is a read-only observer and does not need locking (acceptable stale read for observability).

#### Edge Cases & Error Handling
- `asyncio.Lock` is not re-entrant. Callers that hold the lock and then trigger another hook that also acquires it would deadlock — this cannot happen because the runtime calls each hook sequentially, not recursively.
- Lock acquisition is a coroutine step and introduces one additional asyncio context-switch opportunity, which is fine since we want exclusivity.

---

### 6.8 Updated tests — `test_security_middleware.py`

**File:** `tests/test_security_middleware.py`
**Type:** Modified

#### What it does
The existing tests for `ConfusedDeputyGuardMiddleware` assert on `mw._user_message` and `mw._tool_outputs`. After the fix these attributes no longer exist on the instance. Tests must be updated to:
1. Pass a shared `run_state` dict through `MiddlewareContext`.
2. Assert on `run_state[ConfusedDeputyGuardMiddleware]` attributes, OR
3. Assert on observable behavior only (e.g., does `before_tool_call` return abort or continue).

Specifically these tests need updating:
- `test_before_run_captures_user_message` — assert on `run_state` contents
- `test_after_tool_call_accumulates_results` — assert on `run_state` contents
- `test_before_run_resets_state` — becomes a concurrent safety test

---

### 6.9 New test file — `tests/test_concurrent_middleware.py`

**File:** `tests/test_concurrent_middleware.py`
**Type:** New file

#### What it does
Directly tests that two concurrent coroutines sharing a single middleware instance produce independent behavior — the core guarantee this fix provides.

One shared `run_state` per run is simulated by constructing `MiddlewareContext` objects with separate dicts, then running two async coroutines that interleave at known points.

---

## 7. Data Model Changes

### 7.1 `MiddlewareContext` — add `run_state` field

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class MiddlewareContext:
    # existing fields unchanged ...
    run_state: dict[type, Any] = field(default_factory=dict)  # NEW
```

The field is added at the end so all existing positional construction patterns that name fields explicitly are unaffected (Python dataclasses with `slots=True` support keyword construction).

**Migration strategy:** All existing `MiddlewareContext(hook=..., agent_name=...)` call-sites omit `run_state` and automatically receive `{}`. No migration needed.

---

## 8. API Changes

N/A — No public HTTP API changes. The changes are internal to the SDK's middleware protocol.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/dataclasses/middleware.py` | Add `run_state` field to `MiddlewareContext` |
| MODIFY | `vidbyte/agents/runtime.py` | Create per-run `run_state` dict; thread through `_middleware_context` and callee methods |
| MODIFY | `vidbyte/middleware/builtins/retry.py` | Move `_attempts` to `_ModelRetryRunState` in `ctx.run_state` |
| MODIFY | `vidbyte/middleware/builtins/confused_deputy.py` | Move `_user_message`, `_tool_outputs` to `_ConfusedDeputyRunState` in `ctx.run_state` |
| MODIFY | `vidbyte/middleware/builtins/loop_detection.py` | Move `_call_history` to `_LoopDetectionRunState` in `ctx.run_state` |
| MODIFY | `vidbyte/middleware/builtins/rate_limit.py` | Move `_window_started`, `_window_tokens`, `_last_tokens_seen` to `_TokenRateLimitRunState` in `ctx.run_state` |
| MODIFY | `vidbyte/middleware/builtins/circuit_breaker.py` | Add `asyncio.Lock` to serialize cross-run state mutations |
| MODIFY | `tests/test_security_middleware.py` | Update assertions on `mw._user_message`/`mw._tool_outputs` to use `run_state` |
| MODIFY | `tests/test_middleware_builtins.py` | Update `TokenRateLimitMiddleware` tests to pass `run_state` |
| CREATE | `tests/test_concurrent_middleware.py` | New concurrency safety tests |
| CREATE | `scripts/test_concurrent_middleware_safety.py` | Verification script |

---

## 10. Testing Plan

### Unit Tests

**`ModelRetryMiddleware`**
- `test_retry_state_initialized_fresh_each_run` — `before_run` on a fresh `run_state` gives `attempts=0` [Edge Case]
- `test_retry_attempts_increment_per_run_state` — `on_model_error` increments `run_state` counter, not instance variable [Hidden Failure]
- `test_retry_exhausted_aborts_after_max_attempts` — behavioral parity with existing test [Silent Failure]
- `test_two_concurrent_runs_have_independent_attempt_counters` — two `run_state` dicts, each tracks its own count [Hidden Failure]
- `test_on_model_error_without_before_run_does_not_crash` — lazy fallback initializes gracefully [Hidden Assumption]

**`ConfusedDeputyGuardMiddleware`**
- `test_before_run_writes_fresh_state_to_run_state` — `run_state[ConfusedDeputyGuardMiddleware].user_message` equals `ctx.message` [Hidden Assumption]
- `test_after_tool_call_appends_to_run_state_tool_outputs` — appends to `state.tool_outputs` [Edge Case]
- `test_run_b_cannot_clear_run_a_tool_outputs` — Run B's `before_run` with its own `run_state` does not affect Run A's `run_state` [Hidden Failure]
- `test_confused_deputy_abort_fires_correctly_per_run` — abort fires for run with injected args, not for clean run [Silent Failure]
- `test_no_tool_outputs_in_run_state_skips_check` — `before_tool_call` continues when state is absent [Hidden Assumption]

**`LoopDetectionMiddleware`**
- `test_loop_detection_fresh_history_each_run` — `run_state` deque starts empty [Edge Case]
- `test_loop_detected_within_same_run` — loop abort fires correctly within a single run [Silent Failure]
- `test_loop_history_not_shared_across_concurrent_runs` — Run A's call history is invisible to Run B [Hidden Failure]
- `test_before_tool_call_without_before_run_falls_back_safely` — lazy init returns safe deque [Hidden Assumption]

**`TokenRateLimitMiddleware`**
- `test_token_window_initialized_in_before_run` — `run_state` contains fresh state [Edge Case]
- `test_sleep_fires_on_window_exceeded` — behavioral parity with existing test [Silent Failure]
- `test_two_runs_have_independent_token_windows` — Run B's tokens don't deplete Run A's window [Hidden Failure]
- `test_before_iteration_without_before_run_initializes_lazily` — backward compat for isolated calls [Hidden Assumption]

**`CircuitBreakerMiddleware`**
- `test_circuit_state_persists_across_runs_intentionally` — state transitions accumulate across multiple `run_state` dicts (cross-run intent preserved) [Hidden Assumption]
- `test_concurrent_error_recording_does_not_corrupt_state` — two concurrent `on_model_error` calls produce exactly 2 error timestamps [Hidden Failure]
- `test_lock_prevents_race_on_open_transition` — circuit trips exactly once when threshold is met under concurrency [Silent Failure]
- `test_half_open_calls_bounded_under_concurrency` — `_half_open_calls` does not exceed `half_open_max_calls` [Hidden Failure]

### Integration Tests

- **Two concurrent `ModelRetryMiddleware` runs**: Create one `ModelRetryMiddleware(max_attempts=2)`. Launch two `asyncio.gather` tasks each calling a fake runner that raises an error. Verify each task gets its own retry count and both receive `abort` after max attempts without interleaving. [Hidden Failure]
- **Confused deputy under parallelism**: Create one `ConfusedDeputyGuardMiddleware`. Run two concurrent tasks — Task A accumulates injected tool output and calls a tool with matching argument. Task B accumulates clean output and calls a tool with a clean argument. Verify Task A aborts and Task B continues. [Hidden Failure]
- **CircuitBreaker under parallel load**: Run 10 concurrent tasks against a shared `CircuitBreakerMiddleware(failure_threshold=3)`. Verify the circuit trips after exactly `failure_threshold` errors are recorded in the lock-protected window. [Silent Failure]

### Manual / QA Test Cases

1. Given a `BaseAgent` with `LoopDetectionMiddleware(max_repeated_calls=2)` calling `asyncio.gather(agent.arun("task1"), agent.arun("task2"))`, when both calls loop twice, then each call aborts independently with `tool_loop_detected` and neither task's abort affects the other. [Hidden Failure]
2. Given a `ConfusedDeputyGuardMiddleware` shared across two `ParallelPipeline` branches, when Branch A receives injected tool output and Branch B receives clean output, then Branch A is aborted and Branch B completes normally. [Hidden Failure]
3. Given a `CircuitBreakerMiddleware(failure_threshold=2)` shared across concurrent calls, when the first two concurrent calls both fail, then the circuit is OPEN and subsequent calls are aborted. No double-counting of errors. [Silent Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `asyncio.Lock` | Python stdlib 3.11 | Serialize concurrent state mutations in `CircuitBreakerMiddleware` | None — stdlib, no new dep |
| `dataclasses.dataclass` | Python stdlib 3.11 | Define per-run state containers | None — already used in codebase |

---

## 12. Rollout & Deployment

- No feature flags needed. This is a bug fix for a latent concurrency issue.
- **Not a breaking change** for callers who construct `MiddlewareContext` by keyword (the new `run_state` field has a default). It IS a breaking change for any code that directly accesses `mw._attempts`, `mw._user_message`, `mw._tool_outputs`, `mw._call_history`, `mw._window_started`, `mw._window_tokens`, `mw._last_tokens_seen` on a middleware instance. All such code in the repo is internal test code which will be updated in this PR.
- The existing `CanaryTripwireMiddleware` has the same pattern but is not in scope. Its state (`_canaries`) will continue to be corrupted under concurrency until a follow-up PR fixes it.
- No deployment order constraints — this is a pure Python library change.
- **Rollback:** revert the PR. No data migration needed.

---

## 13. Open Questions

- [ ] Should `TokenRateLimitMiddleware` be per-run (each run gets its own rate-limit window) or cross-run (shared budget across all concurrent runs)? Current interpretation: per-run, matching the docstring "direct text agent runs". If cross-run is desired, it needs the same `asyncio.Lock` treatment as `CircuitBreakerMiddleware` instead.
- [ ] `CanaryTripwireMiddleware` has the same `_canaries` instance-variable corruption pattern. Should it be fixed in this PR or a follow-up?
- [ ] `_arun_once` is the only call-site for middleware hooks today. But `AgentRuntimeContextAlgorithms.arun` may call middleware hooks in the future. Should `run_state` be threaded through that path proactively?

---

## 14. Alternatives Considered

### Alternative 1: run_id-keyed state store in `MiddlewarePipeline`
- **What:** `MiddlewarePipeline` maintains `_state_store: dict[str, dict[AgentMiddleware, Any]]` keyed by `(run_id, middleware)`. Middleware receives the store via a separate mechanism.
- **Why rejected:** Requires `run_id` to be unique per run (currently optional/None), adds a growing dict to `MiddlewarePipeline` that requires explicit eviction, and requires either passing the state store to middleware out-of-band (breaking the `MiddlewareContext` contract) or adding a method to `MiddlewarePipeline` that middleware instances must call directly (tight coupling).

### Alternative 2: Subclass `AgentMiddleware` with a `PerRunStateMixin`
- **What:** Add a `PerRunStateMixin.get_run_state(run_id)` method that lazily creates per-run state keyed by `run_id`.
- **Why rejected:** Requires `run_id` to be unique per run, still stores state on the middleware instance (just in a nested dict), doesn't solve the core problem — only defers it behind a dict lookup. Memory management (when to evict finished runs) is unclear.

### Alternative 3: Instantiate fresh middleware per `arun` call inside `BaseAgent`
- **What:** Change `BaseAgent._runtime()` to deep-copy the middleware tuple each call, so each run gets fresh instances.
- **Why rejected:** Deep-copying middleware instances breaks `CircuitBreakerMiddleware` (cross-run state intentionally lost), and breaks any user-defined middleware that stores intentional cross-run state. It also violates the principle of least surprise — users who pass a shared `CircuitBreakerMiddleware` expect it to be shared.

### Alternative 4: Add `asyncio.Lock` to all five middleware
- **What:** Protect every instance-variable access in all five middleware with locks.
- **Why rejected:** For per-run state (retry attempts, tool outputs, loop history, rate-limit window), locking shared state is incorrect — the state should be independent, not serialized. Using a lock would still allow Run B to reset Run A's counter (just without a race condition in the assignment itself). The only correct fix for per-run state is to scope it per-run.
