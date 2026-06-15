# Design Doc: Loop Detection — Repeated Output Detection (#143)

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-15
**Last Updated:** 2026-06-15

---

## 1. Overview

`LoopDetectionMiddleware` currently aborts only when the same tool is called with the same arguments consecutively. The SWE-bench trace showed a more common stuck pattern: the agent alternates among multiple tools (`read_file`, `glob`, `run_tests`, `grep`) and each tool repeatedly returns the same output, yet no consecutive-call threshold is ever crossed. This design adds `max_repeated_outputs` to `LoopDetectionMiddleware` — an optional total-count check in `after_tool_call` that fires when any single (tool, output) pair has been observed more than the threshold number of times during the run.

---

## 2. Goals & Non-Goals

### Goals
- Add `max_repeated_outputs: int | None` to `LoopDetectionMiddleware` to detect repeated identical outputs for the same tool, regardless of call ordering.
- Track counts in `after_tool_call` via a new `output_counts` field on `_LoopDetectionRunState`.
- Abort with reason `tool_output_loop_detected` and meaningful metadata when the threshold is crossed.
- Keep the existing consecutive-input detection (`max_repeated_calls` / `_count_consecutive_tail`) unchanged.
- Keep `max_repeated_outputs=None` (disabled) as the default so existing callers are unaffected.

### Non-Goals
- Detecting periodic sequences (A-B-C-A-B-C) via cycle detection algorithms.
- Tracking unique distinct outputs per tool (this design tracks per (tool, output) pair, not per tool overall).
- Changing the `window` parameter — it continues to apply only to the existing call-input deque.
- Modifying the stop-reason enum; `tool_output_loop_detected` is carried as a metadata string, not an `AgentStopReason`.

---

## 3. Background & Context

The clean SWE-bench trace (`973e...`) had 86 tool calls. Post-analysis showed:
- `read_file` same output: 19 times
- `glob` same output: 17 times
- `run_tests` same output: 15 times
- `grep` no-match output: 12 times

The retry trace (`fdfe...`) had 359 tool calls. The same pattern continued until the provider hit a credit-limit error, the only condition that stopped the run.

The existing consecutive-call detection never fired because the agent was interleaving different tool names. A total-count check on (tool, output) pairs would have caught this far earlier: with `max_repeated_outputs=8`, the `read_file` repetition would have triggered after 8 identical outputs — about one-tenth the total calls.

---

## 4. Requirements

### Functional Requirements
1. `LoopDetectionMiddleware` must accept an optional `max_repeated_outputs: int | None` parameter (default `None`).
2. When `max_repeated_outputs` is not `None`, the middleware must implement `after_tool_call`.
3. In `after_tool_call`, if `ctx.tool_result` is not `None` and `ctx.tool_is_internal` is `False` (when `skip_internal_tools=True`), the middleware must hash `(tool_name, output)` and increment a per-run counter.
4. When any counter reaches `max_repeated_outputs`, the middleware must return `MiddlewareDecision.abort("tool_output_loop_detected", metadata={...})`.
5. The `max_repeated_outputs` threshold must be validated: it must be `>= 2` (same rule as `max_repeated_calls`).
6. Existing behavior when `max_repeated_outputs=None` must be completely unchanged (no new state allocated, `after_tool_call` returns `continue_()` immediately).

### Non-Functional Requirements
- Output count tracking must be bounded: use a `dict[str, int]` keyed by `tool_name:output_hash_prefix`. Keys grow at most once per unique (tool, output) pair observed in the run.
- No new external dependencies.
- The additional per-run state must be stored in the existing `_LoopDetectionRunState` dataclass, not a second entry in `run_state`.

---

## 5. High-Level Design

```
AgentRuntime
  → before_run     → LoopDetectionMiddleware.before_run   (init state)
  → before_tool_call → LoopDetectionMiddleware.before_tool_call  (existing consecutive check)
  → [tool executes]
  → after_tool_call  → LoopDetectionMiddleware.after_tool_call   (NEW: output count check)
```

The middleware accumulates a `dict[str, int]` keyed by `"{tool_name}:{sha256(output)[:16]}"`. On every `after_tool_call`, the counter for the current (tool, output) pair is incremented. If the counter reaches `max_repeated_outputs`, the run is aborted.

The `_LoopDetectionRunState` dataclass gains one new field:

```
output_counts: dict[str, int]   # keyed by "tool_name:output_hash"
```

---

## 6. Detailed Design

### 6.1 `_LoopDetectionRunState` — `vidbyte/middleware/builtins/loop_detection.py`

**File:** `vidbyte/middleware/builtins/loop_detection.py`
**Type:** Modified

#### What it does
Carries per-run state for `LoopDetectionMiddleware`. Adding `output_counts` avoids a second `run_state` dict entry and keeps all loop-detection state colocated.

#### Interface / API
```python
@dataclass
class _LoopDetectionRunState:
    call_history: collections.deque[str]
    output_counts: dict[str, int]   # NEW
```

---

### 6.2 `LoopDetectionMiddleware` — `vidbyte/middleware/builtins/loop_detection.py`

**File:** `vidbyte/middleware/builtins/loop_detection.py`
**Type:** Modified

#### What it does
Extended with `max_repeated_outputs` parameter and `after_tool_call` hook.

#### Interface / API
```python
class LoopDetectionMiddleware(AgentMiddleware):
    def __init__(self, *, max_repeated_calls: int = 3, window: int = 10,
                 skip_internal_tools: bool = True,
                 max_repeated_outputs: int | None = None) -> None: ...

    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def after_tool_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...  # NEW

    def _make_key(self, tool_name: str, arguments: Any) -> str: ...
    def _make_output_key(self, tool_name: str, output: str) -> str: ...  # NEW
    @staticmethod
    def _count_consecutive_tail(key: str, history: collections.deque[str]) -> int: ...
```

#### Logic / Algorithm

**`__init__`:**
1. Validate `max_repeated_outputs >= 2` if provided.
2. Store `self.max_repeated_outputs = max_repeated_outputs`.

**`before_run`:**
1. Initialize `_LoopDetectionRunState` with both `call_history` deque and `output_counts={}`.

**`after_tool_call`:**
1. If `max_repeated_outputs` is `None`, return `continue_()` immediately.
2. If `ctx.tool_result is None`, return `continue_()`.
3. If `skip_internal_tools` and `ctx.tool_is_internal`, return `continue_()`.
4. Retrieve or initialize the run state.
5. Build `output_key = self._make_output_key(ctx.tool_result.tool_name, ctx.tool_result.output)`.
6. Increment `state.output_counts[output_key]`.
7. If `state.output_counts[output_key] >= self.max_repeated_outputs`, return `MiddlewareDecision.abort("tool_output_loop_detected", metadata={...})`.
8. Return `continue_()`.

**`_make_output_key`:**
1. Encode `(tool_name + ":" + output)` as UTF-8 bytes.
2. Return `f"{tool_name}:{sha256(output.encode()).hexdigest()[:16]}"`.

#### Edge Cases & Error Handling
- If `ctx.tool_result` is `None` (tool was denied by permission policy before executing), skip — no output to track.
- If `before_run` was never called (state missing from `run_state`), initialize a default state inline (same pattern as existing `before_tool_call`).
- Empty string output (`""`) is a valid output and must be tracked.
- Very long outputs are hashed; the dict key is bounded regardless of output size.

---

## 7. Data Model Changes

N/A — no schema or persistent data changes.

---

## 8. API Changes

N/A — no HTTP endpoints.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/middleware/builtins/loop_detection.py` | Add `max_repeated_outputs`, `output_counts` field, `after_tool_call` hook |
| MODIFY | `tests/test_new_middleware_builtins.py` | Add tests for the new output-repetition detection |

---

## 10. Testing Plan

### Unit Tests

**`tests/test_new_middleware_builtins.py` — additions to `TestLoopDetectionMiddleware`:**

- `it('aborts when same tool produces identical output max_repeated_outputs times')` — [Hidden Failure]: the primary fix; alternating tools with the same output
- `it('does not abort when max_repeated_outputs is None (default)')` — [Edge Case]: opt-in behavior must not activate by default
- `it('does not abort when identical output count is below threshold')` — [Edge Case]: count < threshold must continue
- `it('counts different tools independently')` — [Silent Failure]: tool A hitting threshold must not abort tool B
- `it('counts same output across non-consecutive calls correctly')` — [Hidden Failure]: the key use-case; A-B-A-B where A always returns same output
- `it('does not count outputs from internal tools when skip_internal_tools=True')` — [Hidden Assumption]: consistent with existing input-loop skip behavior
- `it('does track outputs from internal tools when skip_internal_tools=False')` — [Hidden Assumption]: explicitly opted-in tracking
- `it('does not track when tool_result is None (denied tool call)')` — [Edge Case]: skip denied calls
- `it('counts empty string output')` — [Edge Case]: empty output is valid and must be tracked
- `it('includes correct metadata in abort decision')` — [Silent Failure]: metadata must include tool_name, output_hash, and count
- `it('raises ValueError when max_repeated_outputs is 1')` — [Edge Case]: validation must enforce >= 2
- `it('output_counts resets on new before_run call (separate run_state dicts)')` — [Hidden Failure]: runs must not share output state
- `it('consecutive input and output detection coexist independently')` — [Hidden Assumption]: both thresholds can fire independently; input threshold fires first on consecutive runs

### Integration Tests
- Simulate an eval-style loop where `read_file` returns the same output 8 times interspersed with `glob` and `grep` calls; verify abort fires on the 8th `read_file` output, before the model exhausts its budget.

### Manual / QA Test Cases
1. Given a `LoopDetectionMiddleware(max_repeated_outputs=5)`, when `glob` returns `[]` five times in non-consecutive calls, then the run must abort with `tool_output_loop_detected` — [Hidden Failure]
2. Given default `LoopDetectionMiddleware()` (no `max_repeated_outputs`), when `read_file` returns the same content 50 times, then no output-based abort fires — [Edge Case, regression check]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `hashlib` | stdlib | SHA-256 output fingerprint | None |
| `json` | stdlib | Already used by existing `_make_key` | None |

---

## 12. Rollout & Deployment

- `max_repeated_outputs=None` by default — fully opt-in. Existing callers that already use `LoopDetectionMiddleware()` are completely unaffected.
- No breaking changes.
- No feature flags required.
- Rollback: remove the new parameter; the `__init__` default handles it gracefully.

---

## 13. Open Questions

- [ ] Should `max_repeated_outputs` also check across the call-input deque (i.e., should tool outputs share the same `window` cap as call-history)? Current design uses an unbounded `dict` per run, which is acceptable for eval runs of a few hundred calls but might need a `maxlen` for very long-running agents.
- [ ] Should the feature expose the current output-loop count in agent metadata or stop-reason metadata so operators can tune the threshold based on observed traces?

---

## 14. Alternatives Considered

### Alternative 1: Separate `OutputLoopDetectionMiddleware` class
- What: Add a distinct class instead of extending `LoopDetectionMiddleware`.
- Why rejected: Conceptually the same concern (loop detection); keeping it in one class avoids users having to wire two middleware instances and keeps the `run_state` key unified.

### Alternative 2: Cycle detection (Brent's / Floyd's algorithm)
- What: Detect periodic patterns like A-B-C-A-B-C in the tool call sequence.
- Why rejected: Significantly more complex to implement and test, and the observed failure mode is not periodic in a clean cycle — it's a broader "the agent is making the same kinds of calls and getting the same answers" pattern. Repeated-output detection handles this with far less complexity.

### Alternative 3: Track repeated outputs in `after_iteration` using the full message history
- What: Scan the accumulated message history at the end of each iteration for repeated tool outputs.
- Why rejected: Requires scanning the full context window on every iteration, which is O(n×m) per run. The per-call counter dict is O(1) per call.
