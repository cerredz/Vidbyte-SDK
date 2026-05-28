# Design Doc: Middleware Builtins Expansion

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-26
**Last Updated:** 2026-05-26

---

## 1. Overview

This document specifies five new prebuilt middleware implementations for the Vidbyte SDK's agent runtime middleware system: `TokenBudgetMiddleware`, `CostBudgetMiddleware`, `ExponentialBackoffRetryMiddleware`, `LoopDetectionMiddleware`, and `CircuitBreakerMiddleware`. Each targets a distinct operational gap not covered by the existing builtins (`TokenRateLimitMiddleware`, `ModelRetryMiddleware`, `RuntimeLimitMiddleware`, `ToolPolicyMiddleware`, `AuditLogMiddleware`). Together they give SDK users production-grade controls over per-run resource ceilings, retry policy, repetition detection, and sustained-failure protection — all composable via `MiddlewarePipeline` and requiring no changes to `AgentRuntime` internals.

---

## 2. Goals & Non-Goals

### Goals
- Implement `TokenBudgetMiddleware`: abort when cumulative `tokens_used` exceeds a per-run ceiling.
- Implement `CostBudgetMiddleware`: track estimated spend using a blended cost-per-million-token rate and abort when the budget is exceeded.
- Implement `ExponentialBackoffRetryMiddleware`: retry transient model errors with exponential backoff, configurable jitter, and per-error-type filtering.
- Implement `LoopDetectionMiddleware`: abort when the same (tool_name, arguments) pair is called consecutively more than a configured threshold.
- Implement `CircuitBreakerMiddleware`: implement the three-state circuit breaker pattern (CLOSED → OPEN → HALF_OPEN) over model calls.
- Export all five through `vidbyte.middleware.builtins` and `vidbyte.middleware`.
- Write comprehensive tests covering edge cases, hidden failure modes, silent failures, and hidden assumptions.

### Non-Goals
- No changes to `AgentRuntime`, `MiddlewarePipeline`, `MiddlewareContext`, or `MiddlewareDecision` — all five middleware fit within the existing hook model.
- No per-provider cost table or automatic rate fetching — cost rates are user-supplied.
- No distributed state — all middleware state is in-process and per-instance.
- No `ToolArgumentPolicyMiddleware` or `ToolResultCacheMiddleware` in this PR.
- No persistence of circuit breaker state across process restarts.

---

## 3. Background & Context

The middleware system was designed in `docs/design/agent-runtime-middleware.md`. Five builtins exist today. The design conversation identified eight gaps; this PR closes five of them. The hook model already provides everything needed (`before_run`, `before_iteration`, `before_model_call`, `after_model_response`, `on_model_error`, `before_tool_call`) — no new hooks are required.

The primary motivation is production readiness: agents running unattended need hard token/cost ceilings, smarter retry behavior, loop-detection guards, and circuit protection before they can be trusted in production workflows.

---

## 4. Requirements

### Functional Requirements

**TokenBudgetMiddleware**
1. Accept `max_tokens: int` — total token ceiling per run (must be > 0).
2. On `before_iteration`, read `ctx.tokens_used`; if `>= max_tokens`, return `MiddlewareDecision.abort("token_budget_exceeded")` with metadata containing `max_tokens` and `tokens_used`.
3. If `ctx.tokens_used` is `None`, continue without aborting.
4. Accept optional `abort_reason: str` override so callers can customize the abort label.
5. Reset no state between runs (stateless per-run since tokens_used is cumulative in ctx).

**CostBudgetMiddleware**
6. Accept `max_spend_usd: float` (must be > 0) and `cost_per_million_tokens: float` (must be > 0).
7. Accept optional `clock: Callable[[], float]` for testability.
8. On `after_model_response`, compute the token delta since last observed `tokens_used` and accumulate a running cost estimate.
9. On `before_iteration`, if estimated cost `>= max_spend_usd`, abort with reason `"cost_budget_exceeded"` and metadata containing `max_spend_usd`, `estimated_spend_usd`, and `tokens_used`.
10. On `before_run`, reset accumulated state so the middleware is safe to reuse across runs.
11. If `ctx.tokens_used` is `None`, skip accumulation for that call.

**ExponentialBackoffRetryMiddleware**
12. Accept `max_attempts: int` (default 3, must be > 0).
13. Accept `base_seconds: float` (default 1.0, must be > 0) — the initial wait.
14. Accept `cap_seconds: float` (default 60.0, must be >= base_seconds) — maximum wait per attempt.
15. Accept `jitter: bool` (default `True`) — when `True`, add uniform random jitter in `[0, computed_delay)`.
16. Accept `retry_on: tuple[type[BaseException], ...] | None` (default `None` = retry all errors) — when set, only retry if `ctx.error` is an instance of one of the given types.
17. Accept `sleep_fn: Callable[[float], Awaitable[None]] | None` for testability (default `asyncio.sleep`).
18. On `before_run`, reset attempt counter.
19. On `on_model_error`: if error type does not match `retry_on`, abort. If attempts remaining, compute delay as `min(cap, base * 2^(attempt-1))` optionally jittered, return `MiddlewareDecision.retry(sleep_seconds=delay)`. If exhausted, return `MiddlewareDecision.abort("model_retry_exhausted")`.
20. Include `attempt`, `max_attempts`, `delay_seconds`, and `error_type` in metadata on every retry decision.

**LoopDetectionMiddleware**
21. Accept `max_repeated_calls: int` (default 3, must be >= 2) — how many identical consecutive tool calls trigger detection.
22. Accept `window: int` (default 10, must be >= `max_repeated_calls`) — maximum recent calls to track in the sliding deque.
23. Accept `skip_internal_tools: bool` (default `True`) — when `True`, internal tools (e.g., `isDone`) are excluded from loop tracking.
24. On `before_tool_call`, compute a stable key from `ctx.tool_call.tool_name` and a deterministic hash of `ctx.tool_call.arguments`.
25. Append the key to a bounded deque (max length = `window`). Count how many of the last `max_repeated_calls` entries are identical to the current key.
26. If the count equals `max_repeated_calls`, return `MiddlewareDecision.abort("tool_loop_detected")` with metadata containing `tool_name`, `repeated_count`, and `max_repeated_calls`.
27. On `before_run`, reset the deque so the middleware is safe to reuse.
28. If `ctx.tool_call` is `None`, continue without tracking.

**CircuitBreakerMiddleware**
29. Accept `failure_threshold: int` (default 5, must be > 0) — errors within the window that trip the circuit.
30. Accept `window_seconds: float` (default 60.0, must be > 0) — rolling time window for error counting.
31. Accept `recovery_timeout: float` (default 30.0, must be > 0) — how long the circuit stays OPEN before moving to HALF_OPEN.
32. Accept `half_open_max_calls: int` (default 1, must be > 0) — calls allowed in HALF_OPEN before deciding to CLOSE or re-OPEN.
33. Accept `clock: Callable[[], float] | None` for testability.
34. On `before_model_call`:
    - CLOSED → continue.
    - OPEN → if `now - opened_at < recovery_timeout`, abort with reason `"circuit_open"`. Otherwise transition to HALF_OPEN and continue.
    - HALF_OPEN → if `half_open_call_count >= half_open_max_calls`, abort with reason `"circuit_half_open_limit"`. Otherwise increment counter and continue.
35. On `after_model_response`:
    - HALF_OPEN → transition to CLOSED, reset counters.
    - CLOSED → record success (noop for error count).
36. On `on_model_error`:
    - HALF_OPEN → transition back to OPEN (reset `opened_at` to now), return `continue_` (let normal error handling proceed).
    - CLOSED → record error timestamp; if error count in window `>= failure_threshold`, transition to OPEN.
37. Expose a `state` property returning the current `CircuitState` for observability.

### Non-Functional Requirements
- All middleware must be thread-safe for single-async-task use (the agent runtime is single-threaded async, not concurrent per instance).
- Initialization validation (`ValueError` for invalid params) matches the pattern in `ModelRetryMiddleware` and `RuntimeLimitMiddleware`.
- All classes follow the existing code style: Context Protocol Header docstring, `from __future__ import annotations`, named `__all__`.
- Tests use `unittest.IsolatedAsyncioTestCase` matching `test_agent_middleware.py`.
- No third-party dependencies beyond Python stdlib.

---

## 5. High-Level Design

Each new middleware is a standalone file in `vidbyte/middleware/builtins/`, exported through the existing `__init__` chain. No changes to `AgentRuntime` or `MiddlewarePipeline` are needed since all five fit within the existing hook model and `MiddlewareDecision` action set.

```
AgentRuntime
    └── MiddlewarePipeline._run(hook, ctx)
            ├── TokenBudgetMiddleware.before_iteration     → abort if tokens_used >= max_tokens
            ├── CostBudgetMiddleware.after_model_response  → accumulate cost delta
            │   CostBudgetMiddleware.before_iteration      → abort if estimated >= max_spend
            ├── ExponentialBackoffRetryMiddleware.on_model_error → retry with backoff
            ├── LoopDetectionMiddleware.before_tool_call   → abort on repeated (name, args)
            └── CircuitBreakerMiddleware.before_model_call → abort if circuit OPEN
                CircuitBreakerMiddleware.on_model_error    → count errors, maybe OPEN
                CircuitBreakerMiddleware.after_model_response → maybe CLOSE
```

State management: `CostBudgetMiddleware`, `ExponentialBackoffRetryMiddleware`, `LoopDetectionMiddleware`, and `CircuitBreakerMiddleware` all maintain mutable internal state and reset it in `before_run`. `TokenBudgetMiddleware` is stateless (reads directly from ctx each iteration).

The circuit breaker introduces a new `CircuitState` enum (`CLOSED`, `OPEN`, `HALF_OPEN`) as an internal implementation detail, not exported publicly.

---

## 6. Detailed Design

### 6.1 TokenBudgetMiddleware

**File:** `vidbyte/middleware/builtins/token_budget.py`
**Type:** New file

#### What it does
Aborts the run before each iteration when the provider-reported cumulative token count has reached or exceeded the configured ceiling.

#### Interface / API
```python
class TokenBudgetMiddleware(AgentMiddleware):
    def __init__(self, *, max_tokens: int, abort_reason: str = "token_budget_exceeded") -> None: ...
    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm
1. Validate `max_tokens > 0` in `__init__`; raise `ValueError` otherwise.
2. In `before_iteration`: if `ctx.tokens_used is None`, return `continue_()`.
3. If `ctx.tokens_used >= self.max_tokens`, return `abort(self.abort_reason, metadata={"max_tokens": max_tokens, "tokens_used": ctx.tokens_used})`.
4. Return `continue_()`.

#### Edge Cases & Error Handling
- `ctx.tokens_used` is `None` for providers that do not report token counts → silently skipped.
- Exactly equal to limit triggers abort (inclusive boundary), preventing one-over mistakes.

---

### 6.2 CostBudgetMiddleware

**File:** `vidbyte/middleware/builtins/cost_budget.py`
**Type:** New file

#### What it does
Accumulates an estimated cost from token deltas reported in `ctx.tokens_used` after each model response, then aborts if the running total exceeds `max_spend_usd`.

#### Interface / API
```python
class CostBudgetMiddleware(AgentMiddleware):
    def __init__(self, *, max_spend_usd: float, cost_per_million_tokens: float) -> None: ...
    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm
1. Validate both params > 0; raise `ValueError` otherwise.
2. `before_run`: reset `_accumulated_tokens = 0`, `_last_tokens_seen = None`, `_estimated_spend_usd = 0.0`.
3. `after_model_response`: if `ctx.tokens_used is None`, skip. Compute `delta = max(0, ctx.tokens_used - (self._last_tokens_seen or 0))`. Update `_accumulated_tokens += delta`, `_last_tokens_seen = ctx.tokens_used`. Recompute `_estimated_spend_usd = _accumulated_tokens / 1_000_000 * cost_per_million_tokens`.
4. `before_iteration`: if `_estimated_spend_usd >= max_spend_usd`, abort with reason `"cost_budget_exceeded"`, metadata `{"max_spend_usd": ..., "estimated_spend_usd": ..., "tokens_used": ctx.tokens_used}`.

#### Edge Cases & Error Handling
- `ctx.tokens_used` decreasing (provider reset) → `max(0, delta)` prevents negative accumulation.
- `ctx.tokens_used is None` throughout → cost stays zero, no abort ever fires.
- Multiple runs on the same instance → `before_run` resets all state.

---

### 6.3 ExponentialBackoffRetryMiddleware

**File:** `vidbyte/middleware/builtins/exponential_backoff_retry.py`
**Type:** New file

#### What it does
On model error, retries up to `max_attempts` times using exponential backoff with optional jitter. Can be filtered to only retry specific exception types.

#### Interface / API
```python
class ExponentialBackoffRetryMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        max_attempts: int = 3,
        base_seconds: float = 1.0,
        cap_seconds: float = 60.0,
        jitter: bool = True,
        retry_on: tuple[type[BaseException], ...] | None = None,
    ) -> None: ...
    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm
1. Validate: `max_attempts > 0`, `base_seconds > 0`, `cap_seconds >= base_seconds`; raise `ValueError` for each violation.
2. `before_run`: reset `_attempts = 0`.
3. `on_model_error`:
   a. If `retry_on is not None` and `ctx.error` is not an instance of any type in `retry_on`, return `abort("model_error_not_retryable", metadata={"error_type": type(ctx.error).__name__})`.
   b. Increment `_attempts`.
   c. If `_attempts >= max_attempts`, return `abort("model_retry_exhausted", metadata={...})`.
   d. Compute raw delay: `min(cap_seconds, base_seconds * (2 ** (_attempts - 1)))`.
   e. If `jitter=True`, apply `delay *= random.uniform(0.5, 1.0)` (half-jitter pattern, avoids zero-sleep).
   f. Return `retry("model_retry_backoff", sleep_seconds=delay, metadata={"attempt": _attempts, "max_attempts": ..., "delay_seconds": delay, "error_type": ...})`.

#### Edge Cases & Error Handling
- `max_attempts=1` → first error always aborts (no retries).
- `retry_on=()` (empty tuple) → no error matches → all errors abort immediately.
- `ctx.error is None` during `on_model_error` → treated as `object()`, matches nothing in `retry_on` if set.

---

### 6.4 LoopDetectionMiddleware

**File:** `vidbyte/middleware/builtins/loop_detection.py`
**Type:** New file

#### What it does
Tracks the last `window` tool calls by (tool_name, arguments hash) in a bounded deque. Aborts if the same call key appears consecutively `max_repeated_calls` times.

#### Interface / API
```python
class LoopDetectionMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        max_repeated_calls: int = 3,
        window: int = 10,
        skip_internal_tools: bool = True,
    ) -> None: ...
    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm
1. Validate: `max_repeated_calls >= 2`, `window >= max_repeated_calls`; raise `ValueError` otherwise.
2. `before_run`: reset `_call_history: collections.deque[str]` with `maxlen=window`.
3. `before_tool_call`:
   a. If `ctx.tool_call is None`, return `continue_()`.
   b. If `skip_internal_tools and ctx.tool_is_internal`, return `continue_()`.
   c. Compute `key = f"{ctx.tool_call.tool_name}:{_stable_hash(ctx.tool_call.arguments)}"` where `_stable_hash` serializes the mapping to a sorted JSON string and hashes with `hashlib.sha256` (truncated to 16 hex chars for readability in metadata).
   d. Append key to `_call_history`.
   e. Count consecutive tail matches: scan from the end of the deque while the entry equals `key`, stop at first mismatch. If count `>= max_repeated_calls`, abort with `"tool_loop_detected"` and metadata `{"tool_name": ..., "repeated_count": count, "max_repeated_calls": ...}`.
   f. Return `continue_()`.

#### Edge Cases & Error Handling
- Arguments containing non-JSON-serializable values → serialize with `str()` fallback so the hash never raises.
- A window smaller than `max_repeated_calls` is rejected in `__init__`, not silently capped.
- A tool called `max_repeated_calls - 1` times then interrupted by a different tool resets the consecutive count.

---

### 6.5 CircuitBreakerMiddleware

**File:** `vidbyte/middleware/builtins/circuit_breaker.py`
**Type:** New file

#### What it does
Implements the three-state circuit breaker pattern over model calls. In CLOSED state, errors within a rolling time window increment a counter; when the threshold is reached, the circuit opens. In OPEN state, model calls are rejected immediately. After `recovery_timeout` seconds, the circuit moves to HALF_OPEN to probe recovery. A successful probe closes the circuit; a failed probe re-opens it.

#### Interface / API
```python
class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreakerMiddleware(AgentMiddleware):
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] | None = None,
    ) -> None: ...

    @property
    def state(self) -> CircuitState: ...

    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_model_response(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def on_model_error(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm
1. Validate all params > 0; raise `ValueError` for each violation.
2. Init: `_state = CircuitState.CLOSED`, `_error_timestamps: list[float] = []`, `_opened_at: float | None = None`, `_half_open_calls = 0`.
3. `before_model_call`:
   - CLOSED → return `continue_()`.
   - OPEN → `now = clock()`. If `now - _opened_at < recovery_timeout`, return `abort("circuit_open", metadata={"recovery_timeout": ..., "opened_at": ...})`. Else transition to HALF_OPEN (`_half_open_calls = 0`) and return `continue_()`.
   - HALF_OPEN → if `_half_open_calls >= half_open_max_calls`, return `abort("circuit_half_open_limit")`. Else `_half_open_calls += 1`, return `continue_()`.
4. `after_model_response`:
   - HALF_OPEN → transition to CLOSED, clear error timestamps.
   - Other states → noop.
5. `on_model_error`:
   - HALF_OPEN → transition to OPEN (`_opened_at = clock()`), return `continue_()`.
   - CLOSED → prune `_error_timestamps` to only entries within `window_seconds`. Append `clock()`. If `len(_error_timestamps) >= failure_threshold`, transition to OPEN (`_opened_at = clock()`).
   - OPEN → noop, return `continue_()`.

#### Edge Cases & Error Handling
- All errors arrive before recovery timeout: circuit stays OPEN indefinitely until recovery_timeout elapses.
- `half_open_max_calls > 1` allows multi-probe recovery (used for gradual recovery strategies).
- `CircuitState` is exported from `vidbyte/middleware/builtins/circuit_breaker.py` and from `vidbyte/middleware/builtins/__init__.py` for observability use.

---

## 7. Data Model Changes

N/A — No schema, database, or dataclass changes. All five middleware use only existing `MiddlewareContext`, `MiddlewareDecision`, and `MiddlewareAction` types.

---

## 8. API Changes

N/A — These are SDK library additions, not HTTP endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/middleware/builtins/token_budget.py` | TokenBudgetMiddleware implementation |
| CREATE | `vidbyte/middleware/builtins/cost_budget.py` | CostBudgetMiddleware implementation |
| CREATE | `vidbyte/middleware/builtins/exponential_backoff_retry.py` | ExponentialBackoffRetryMiddleware implementation |
| CREATE | `vidbyte/middleware/builtins/loop_detection.py` | LoopDetectionMiddleware implementation |
| CREATE | `vidbyte/middleware/builtins/circuit_breaker.py` | CircuitBreakerMiddleware + CircuitState |
| MODIFY | `vidbyte/middleware/builtins/__init__.py` | Export all five new classes + CircuitState |
| MODIFY | `vidbyte/middleware/__init__.py` | Re-export all five new classes + CircuitState |
| CREATE | `tests/test_new_middleware_builtins.py` | Full test suite for all five middleware |

---

## 10. Testing Plan

### Unit Tests

All tests use `unittest.IsolatedAsyncioTestCase`. Helpers from `test_agent_middleware.py` (`FakeRunner`, `FakeResponse`, `invoke_runner`) are replicated inline.

**TokenBudgetMiddleware**
- `test_token_budget_aborts_when_tokens_at_limit` — tokens_used exactly equals max_tokens → abort. [Edge Case]
- `test_token_budget_aborts_when_tokens_exceed_limit` — tokens_used > max_tokens → abort. [Silent Failure]
- `test_token_budget_continues_below_limit` — tokens_used < max_tokens → continue. [Hidden Assumption]
- `test_token_budget_continues_when_tokens_none` — ctx.tokens_used is None → never aborts. [Edge Case]
- `test_token_budget_custom_abort_reason` — abort_reason param appears in decision. [Silent Failure]
- `test_token_budget_raises_on_zero_max` — max_tokens=0 raises ValueError. [Edge Case]
- `test_token_budget_raises_on_negative_max` — max_tokens=-1 raises ValueError. [Edge Case]

**CostBudgetMiddleware**
- `test_cost_budget_aborts_after_spend_exceeded` — accumulate tokens over multiple responses, abort when spend >= max. [Silent Failure]
- `test_cost_budget_continues_below_spend` — partial spend → continue. [Hidden Assumption]
- `test_cost_budget_resets_state_on_before_run` — call before_run, simulate responses, call before_run again — spend resets. [Hidden Failure]
- `test_cost_budget_skips_none_tokens` — tokens_used is None throughout → spend stays zero, no abort. [Edge Case]
- `test_cost_budget_handles_token_count_decrease` — tokens_used goes backward → delta clamped to 0. [Hidden Failure]
- `test_cost_budget_raises_on_zero_spend` — max_spend_usd=0 raises ValueError. [Edge Case]
- `test_cost_budget_raises_on_zero_rate` — cost_per_million_tokens=0 raises ValueError. [Edge Case]
- `test_cost_budget_metadata_contains_spend` — abort decision metadata has estimated_spend_usd, max_spend_usd. [Silent Failure]

**ExponentialBackoffRetryMiddleware**
- `test_backoff_retries_up_to_max` — 3 errors → 2 retries, 3rd aborts. [Edge Case]
- `test_backoff_delay_is_exponential` — delays grow as base*2^attempt. [Silent Failure]
- `test_backoff_jitter_reduces_delay` — with jitter=True, delay is < computed max. [Hidden Assumption]
- `test_backoff_no_jitter_gives_exact_delay` — jitter=False → delay exactly equals formula. [Silent Failure]
- `test_backoff_delay_capped_at_cap_seconds` — large attempt number → delay capped. [Edge Case]
- `test_backoff_max_attempts_one_aborts_immediately` — first error always aborts when max_attempts=1. [Edge Case]
- `test_backoff_retry_on_filters_error_type` — retry_on=(ValueError,) → RuntimeError is not retried, aborts immediately. [Hidden Assumption]
- `test_backoff_retry_on_none_retries_all` — retry_on=None → all error types retried. [Hidden Assumption]
- `test_backoff_resets_on_before_run` — simulate errors, call before_run, simulate again — attempts reset. [Hidden Failure]
- `test_backoff_raises_on_invalid_cap` — cap_seconds < base_seconds raises ValueError. [Edge Case]
- `test_backoff_metadata_contains_attempt_and_delay` — retry decision metadata has attempt, delay_seconds, error_type. [Silent Failure]

**LoopDetectionMiddleware**
- `test_loop_detection_aborts_on_consecutive_identical_calls` — same (name, args) 3× → abort. [Hidden Failure]
- `test_loop_detection_continues_below_threshold` — same call 2× with max=3 → continue. [Edge Case]
- `test_loop_detection_resets_on_different_tool` — A,A,B,A,A → no abort (streak broken by B). [Silent Failure]
- `test_loop_detection_skips_internal_tools` — skip_internal_tools=True → internal tool calls ignored. [Hidden Assumption]
- `test_loop_detection_tracks_internal_tools_when_not_skipping` — skip_internal_tools=False → internal loops detected. [Hidden Assumption]
- `test_loop_detection_different_args_not_detected` — same tool name, different args → not a loop. [Silent Failure]
- `test_loop_detection_resets_on_before_run` — loop history cleared between runs. [Hidden Failure]
- `test_loop_detection_window_bounds_history` — window=3 → only last 3 calls matter. [Edge Case]
- `test_loop_detection_none_tool_call_skipped` — ctx.tool_call is None → continue without tracking. [Edge Case]
- `test_loop_detection_raises_on_invalid_window` — window < max_repeated_calls raises ValueError. [Edge Case]
- `test_loop_detection_metadata_contains_tool_name` — abort decision metadata has tool_name and repeated_count. [Silent Failure]

**CircuitBreakerMiddleware**
- `test_circuit_starts_closed` — initial state is CLOSED. [Hidden Assumption]
- `test_circuit_opens_after_threshold` — threshold=3 errors → OPEN after 3rd. [Hidden Failure]
- `test_circuit_open_aborts_before_model_call` — OPEN → before_model_call returns abort. [Silent Failure]
- `test_circuit_open_transitions_to_half_open_after_timeout` — after recovery_timeout, state becomes HALF_OPEN. [Hidden Failure]
- `test_circuit_half_open_allows_limited_calls` — half_open_max_calls=1 → first call passes, second aborts. [Edge Case]
- `test_circuit_half_open_closes_on_success` — model success in HALF_OPEN → CLOSED. [Hidden Assumption]
- `test_circuit_half_open_reopens_on_error` — model error in HALF_OPEN → back to OPEN. [Hidden Failure]
- `test_circuit_error_timestamps_pruned_outside_window` — errors older than window_seconds not counted. [Silent Failure]
- `test_circuit_closed_continues_below_threshold` — 2 errors with threshold=3 → stay CLOSED. [Edge Case]
- `test_circuit_raises_on_zero_threshold` — failure_threshold=0 raises ValueError. [Edge Case]
- `test_circuit_abort_reason_is_circuit_open` — abort decision has reason "circuit_open". [Silent Failure]
- `test_circuit_state_property_returns_current` — `.state` reflects transitions correctly. [Hidden Assumption]

### Integration Tests
- Compose `TokenBudgetMiddleware` + `CostBudgetMiddleware` in `MiddlewarePipeline` with a fake runner that reports increasing tokens; verify both can abort independently.
- Compose `ExponentialBackoffRetryMiddleware` with a `FakeRunner` that raises N-1 times then succeeds; verify the run completes and all retry decisions appear in pipeline events.
- Compose `LoopDetectionMiddleware` with a fake runner that always returns the same tool call; verify abort fires at the right iteration.
- Compose `CircuitBreakerMiddleware` with a controlled clock; verify CLOSED → OPEN → HALF_OPEN → CLOSED state machine through a full run.

### Manual / QA Test Cases
1. Given a real agent run against a provider with `TokenBudgetMiddleware(max_tokens=100)`, when the agent exceeds 100 tokens, then the run aborts with `stop_reason=middleware_abort` and `middleware_abort_reason=token_budget_exceeded`. [Hidden Assumption]
2. Given `ExponentialBackoffRetryMiddleware(max_attempts=3, jitter=False)`, when the model fails twice then succeeds, then the agent completes and the middleware events show two retry decisions with delays 1.0s and 2.0s. [Edge Case]
3. Given `LoopDetectionMiddleware(max_repeated_calls=2)` and a tool that always returns a stale context causing the agent to re-call it, then the run aborts after two identical calls. [Hidden Failure]
4. Given `CircuitBreakerMiddleware(failure_threshold=2, recovery_timeout=0.01)`, when two errors fire in rapid succession, then the circuit opens; after 10ms it transitions to HALF_OPEN; a successful call closes it. [Hidden Failure]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `collections.deque` | stdlib | Bounded call history in LoopDetectionMiddleware | None |
| `hashlib.sha256` | stdlib | Stable argument hashing in LoopDetectionMiddleware | None |
| `json` | stdlib | Argument serialization for hashing | Non-serializable values need str() fallback |
| `random.uniform` | stdlib | Jitter in ExponentialBackoffRetryMiddleware | None |
| `asyncio` | stdlib | Type for sleep_fn in ExponentialBackoffRetryMiddleware | None |

---

## 12. Rollout & Deployment

- Pure SDK library additions; no API, database, or infrastructure changes.
- Not a breaking change — all new classes, no existing interfaces modified.
- Existing middleware tests continue to pass unchanged.
- No feature flags needed.
- Rollback: revert the PR; downstream users who have not yet imported the new classes are unaffected.

---

## 13. Open Questions

- [ ] Should `CircuitState` be exported from `vidbyte.middleware` (top-level) for user observability, or only from `vidbyte.middleware.builtins`? **Current decision:** exported from both, consistent with other types.
- [ ] Should `ExponentialBackoffRetryMiddleware` accept a `sleep_fn` injection (like `TokenRateLimitMiddleware` accepts `clock`)? **Current decision:** yes, for testability — note this is distinct from the pipeline's own `sleeper`; the middleware computes the delay and passes it to `MiddlewareDecision.retry(sleep_seconds=...)`, so the pipeline sleeper handles actual sleeping. No `sleep_fn` injection needed.
- [ ] `CostBudgetMiddleware` uses a blended per-token rate since `MiddlewareContext` does not expose input/output token split. Is this acceptable, or should we extend `MiddlewareContext`? **Current decision:** blended rate is acceptable for this PR; extending ctx is a separate concern.

---

## 14. Alternatives Considered

### Alternative 1: Extend `ModelRetryMiddleware` with backoff strategy
Add a `backoff` parameter to the existing `ModelRetryMiddleware` instead of a new class.

**Why rejected:** `ModelRetryMiddleware` uses constant sleep while exponential backoff has a fundamentally different parameter surface (`base_seconds`, `cap_seconds`, `jitter`, `retry_on`). Conflating them in one class would require conditional logic on every path and break the principle each builtin has one clear responsibility.

### Alternative 2: `CostBudgetMiddleware` with per-provider rate tables
Automatically apply known cost-per-token rates indexed by `ctx.provider`.

**Why rejected:** Provider pricing changes frequently. Embedding a rate table creates a maintenance burden and false confidence. User-supplied rates are always accurate.

### Alternative 3: Shared error-window state across `CircuitBreakerMiddleware` instances
A class-level dict keyed by agent name for distributed-style circuit breaking in multi-agent setups.

**Why rejected:** Shared mutable class state is a footgun (test isolation failures, unexpected cross-agent coupling). The in-process per-instance model is correct for the current single-agent-runtime use case.

### Alternative 4: `LoopDetectionMiddleware` using cosine similarity instead of exact hash
Detect semantically similar (but not identical) tool calls.

**Why rejected:** Requires an embedding model or string distance computation, which introduces a dependency and latency that belongs in a strategy layer, not deterministic middleware. Exact hash is correct for this use case.
