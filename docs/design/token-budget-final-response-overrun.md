# Design Doc: Token Budget Final Response Overrun

**Status:** Draft
**Author:** Codex
**Created:** 2026-06-24
**Last Updated:** 2026-06-24

---

## 1. Overview

This feature extends `TokenBudgetMiddleware` with an opt-in soft-overrun mode that lets an agent spend one additional model call after the configured token budget is reached so it can provide a final answer instead of returning only a middleware abort result. The existing default remains a hard cap: when the budget is reached, the middleware aborts before the next iteration.

---

## 2. Goals & Non-Goals

### Goals

- Add a semantically clear parameter to `TokenBudgetMiddleware` named `allow_final_response_over_budget`.
- Preserve the current hard-cap behavior by default.
- When `allow_final_response_over_budget=True`, inject model-visible context that explains the token budget has been exceeded and instructs the agent to provide its final answer now.
- Limit the soft-overrun behavior to one final model call per run so the middleware does not permit unbounded token spending.
- Surface result metadata that makes hard aborts and soft final-answer nudges inspectable.
- Document the new parameter in SDK middleware docs and the middleware skill reference.

### Non-Goals

- Do not change `AgentRuntimeConfig.max_tokens`; that existing agent-level budget remains a separate hard stop.
- Do not add a new middleware class or rename `TokenBudgetMiddleware`.
- Do not implement model-specific token prediction or local token counting.
- Do not add cost-budget soft-overrun behavior.
- Do not guarantee the model will obey the final-answer instruction; the middleware can instruct and constrain one extra call, but model output is still provider-dependent.

---

## 3. Background & Context

`TokenBudgetMiddleware` currently lives in `vidbyte/middleware/builtins/token_budget.py`. It reads provider-reported cumulative usage from `MiddlewareContext.tokens_used` during `before_iteration` and returns `MiddlewareDecision.abort(...)` when `tokens_used >= max_tokens`. This makes the middleware a strict hard cap, but the user experience can be poor: after spending the entire budget, callers may receive only `Agent runtime stopped by middleware: token_budget_exceeded` instead of a useful answer.

The runtime already supports model-visible transforms through `MiddlewareTransform`. `AgentRuntime._invoke_with_middleware()` calls `middleware.before_model_call(...)` with the current `system` string and provider messages, and `_apply_before_model_call_transform()` applies `transform.system` before invoking the provider. This gives the token budget middleware a narrow integration point for adding final-answer context without changing the runtime loop or provider contracts.

There is a separate agent-level `max_tokens` budget on `AgentRuntimeConfig`, exposed through `Agent(..., max_tokens=...)`. That hard stop is checked before middleware at the top of each iteration. Users who want the new soft-overrun behavior must use `TokenBudgetMiddleware(max_tokens=..., allow_final_response_over_budget=True)` without also setting `Agent(max_tokens=...)` to the same or lower limit, otherwise the agent-level hard cap can stop first.

---

## 4. Requirements

### Functional Requirements

1. `TokenBudgetMiddleware.__init__` must accept `allow_final_response_over_budget: bool = False`.
2. When `allow_final_response_over_budget` is omitted or `False`, behavior must remain unchanged: if `ctx.tokens_used >= max_tokens`, `before_iteration` aborts with `abort_reason`.
3. When `allow_final_response_over_budget=True` and `ctx.tokens_used is None`, the middleware must continue without injecting a final-answer instruction.
4. When `allow_final_response_over_budget=True` and `ctx.tokens_used < max_tokens`, the middleware must continue without injecting a final-answer instruction.
5. When `allow_final_response_over_budget=True` and `ctx.tokens_used >= max_tokens` for the first time in a run, the middleware must allow one additional model call and inject a model-visible instruction telling the agent that it is over budget and must provide a final answer now.
6. The injected instruction must be appended to the existing system string via `MiddlewareTransform(system=...)` during `before_model_call`, not by mutating runtime internals.
7. The soft-overrun path must be tracked per run using `MiddlewareContext.run_state`, avoiding shared mutable state on the middleware instance.
8. After the final-answer instruction has already been injected once for a run, a subsequent over-budget check must abort with `abort_reason` to prevent unlimited over-budget continuation.
9. Soft-overrun continue decisions must include metadata containing `max_tokens`, `tokens_used`, and a marker such as `final_response_requested=True`.
10. When the final-answer notice is injected, the middleware must also publish a public `token_budget` payload through `ctx.run_state["__result_metadata__"]` because the current pipeline does not record normal continue decisions in final middleware events.
11. Existing abort decisions must continue to include `max_tokens` and `tokens_used`.

### Non-Functional Requirements

- Performance: the added logic must be O(1) per hook and must not inspect or copy provider message history.
- Scalability: per-run state must be stored in `ctx.run_state`, not on the middleware instance, so concurrent runs sharing a middleware instance do not leak state.
- Security: the final-answer instruction must be fixed SDK-controlled text, not built from untrusted model/tool content.
- Observability: hard aborts must remain visible in `AgentResult.metadata["middleware"]`; soft-overrun notices must be visible in `AgentResult.metadata["token_budget"]` through the runtime's existing `run_state["__result_metadata__"]` publishing path.
- Reliability / error tolerance: providers that do not report token usage must keep the current no-op behavior because the middleware cannot know whether the budget was reached.

---

## 5. High-Level Design

The existing `TokenBudgetMiddleware` will remain the single budget middleware for cumulative token usage. Its default behavior stays hard-cap-compatible. The new option, `allow_final_response_over_budget`, changes how the middleware reacts after the budget is reached: instead of aborting immediately on the first over-budget point, it records in `ctx.run_state` that a final response was requested and uses a `before_model_call` transform to append a concise instruction to the current system prompt.

The middleware will use a private run-state dataclass, following the pattern used by `LoopDetectionMiddleware`, to track whether the final-answer instruction has already been injected for the current run. This avoids storing per-run flags on the middleware instance and protects concurrent agent runs.

Data flow:

```text
AgentRuntime iteration
  -> before_iteration
       hard mode: abort when tokens_used >= max_tokens
       soft mode: continue when first over-budget response is still pending
  -> build call options with system prompt
  -> before_model_call
       soft mode and first over-budget: append final-answer notice to system
  -> provider call
       model should provide final answer / call isDone
  -> next iteration if model did not finish
       soft mode after notice was already injected: abort
```

The API name will be `allow_final_response_over_budget` rather than `continue` because it describes the user-facing tradeoff directly: the middleware is not generally continuing the run forever, it is allowing a bounded over-budget final-answer attempt.

---

## 6. Detailed Design

### 6.1 TokenBudgetMiddleware

**File(s):** `vidbyte/middleware/builtins/token_budget.py`
**Type:** Modified

#### What it does

Controls cumulative provider-reported token usage for a direct text agent run. It either aborts at the configured budget or, when explicitly enabled, injects one final-answer instruction and permits one extra model call.

#### Interface / API

```python
TOKEN_BUDGET_FINAL_RESPONSE_NOTICE = (
    "Token budget notice: this run has reached or exceeded its configured token budget. "
    "Do not call additional tools or continue exploring. Provide the best final answer now, "
    "using only the information already available in the conversation."
)

@dataclass
class _TokenBudgetRunState:
    final_response_requested: bool = False

class TokenBudgetMiddleware(AgentMiddleware):
    def __init__(self, *, max_tokens: int, abort_reason: str = "token_budget_exceeded", allow_final_response_over_budget: bool = False) -> None: ...
    async def before_run(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_iteration(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
    async def before_model_call(self, ctx: MiddlewareContext) -> MiddlewareDecision: ...
```

#### Logic / Algorithm

1. Import `dataclass` and `MiddlewareTransform`.
2. Add `TOKEN_BUDGET_FINAL_RESPONSE_NOTICE` as a module-level SDK-controlled constant.
3. Add `_TokenBudgetRunState` with `final_response_requested: bool = False`.
4. In `__init__`, validate `max_tokens > 0` exactly as today and store `allow_final_response_over_budget`.
5. In `before_run`, initialize `ctx.run_state[self.__class__] = _TokenBudgetRunState()`.
6. In `before_iteration`, return `continue_()` when `ctx.tokens_used is None` or below budget.
7. In `before_iteration`, if `allow_final_response_over_budget=False` and usage is at or over budget, return the existing abort decision.
8. In `before_iteration`, if `allow_final_response_over_budget=True` and the final-answer notice has not yet been requested, return `continue_()` with metadata indicating the run is over budget and a final response will be requested.
9. In `before_iteration`, if `allow_final_response_over_budget=True` and the final-answer notice has already been requested, abort with `abort_reason` and existing budget metadata.
10. In `before_model_call`, if soft mode is enabled, usage is at or over budget, and `final_response_requested` is false, set it to true.
11. Publish `ctx.run_state["__result_metadata__"]["token_budget"] = {"max_tokens": ..., "tokens_used": ..., "final_response_requested": True}` so the final result exposes that the run used the soft-overrun path.
12. Return `continue_(transform=MiddlewareTransform(system=<system plus notice>), metadata=...)`.
13. If `ctx.system` is present, append the notice after two newlines. If `ctx.system` is missing, use only the notice. The runtime currently supplies a system string, but this keeps the middleware safe for isolated unit calls.
14. In all other cases, return `continue_()`.

#### Edge Cases & Error Handling

- `max_tokens <= 0`: continue raising `ValueError`.
- `ctx.tokens_used is None`: continue with no notice because no reliable budget comparison is possible.
- `ctx.tokens_used == max_tokens`: treat as over budget using the existing inclusive boundary.
- Middleware instance reused across runs: `before_run` resets state in `ctx.run_state`; lazy initialization in hook methods should still work for direct unit tests that call hooks without `before_run`.
- Model ignores notice and calls tools: the middleware permits only the one over-budget model call; a later over-budget iteration aborts.
- Other middleware also transforms `system`: `MiddlewarePipeline` lets later middleware override earlier transform fields. Documentation should recommend placing `TokenBudgetMiddleware` after middleware that rewrites `system` if callers rely on the soft-overrun notice.

### 6.2 Middleware Unit Coverage

**File(s):** `tests/test_new_middleware_builtins.py`
**Type:** Modified

#### What it does

Adds focused tests for the new `allow_final_response_over_budget` behavior alongside the existing `TokenBudgetMiddleware` tests.

#### Interface / API

```python
async def test_soft_overrun_injects_final_response_notice_once(self) -> None: ...
async def test_soft_overrun_aborts_after_notice_was_requested(self) -> None: ...
async def test_soft_overrun_preserves_hard_default(self) -> None: ...
```

#### Logic / Algorithm

1. Construct `TokenBudgetMiddleware(max_tokens=100, allow_final_response_over_budget=True)`.
2. Call `before_run` with a shared `run_state`.
3. Call `before_model_call` with `tokens_used=100` and `system="base system"`.
4. Assert the decision continues, contains a transform, and appends the final-answer notice to the system string.
5. Assert `run_state["__result_metadata__"]["token_budget"]` records `final_response_requested=True`.
6. Call `before_iteration` again with the same over-budget state and assert it aborts.
7. Keep existing hard-cap tests unchanged to prove default compatibility.

#### Edge Cases & Error Handling

- Test both exact-limit and over-limit behavior.
- Test that `tokens_used=None` still continues with no transform.
- Test lazy hook usage without `before_run` if consistent with current middleware test style.

### 6.3 Middleware Docs

**File(s):** `vidbyte/middleware/README.md`, `README.md`, `skills/vidbyte-sdk/middleware.md`
**Type:** Modified

#### What it does

Documents the new option where built-in middleware and token budgets are described.

#### Interface / API

```python
TokenBudgetMiddleware(max_tokens=50000, allow_final_response_over_budget=True)
```

#### Logic / Algorithm

1. Update the built-in middleware catalog entry for `TokenBudgetMiddleware`.
2. Explain that `allow_final_response_over_budget=False` is the hard default.
3. Explain that `True` permits one additional final-answer model call after the budget is reached.
4. Add a short usage snippet in either `vidbyte/middleware/README.md` or `README.md`.

#### Edge Cases & Error Handling

- Docs must warn that `Agent(max_tokens=...)` remains a separate hard cap and can stop before the middleware soft-overrun path.
- Docs must clarify that the behavior depends on provider-reported token usage.

---

## 7. Data Model Changes

### 7.1 _TokenBudgetRunState

**Change type:** New

```python
@dataclass
class _TokenBudgetRunState:
    final_response_requested: bool = False
```

**Migration strategy:** N/A - this is an internal in-memory per-run dataclass stored in `MiddlewareContext.run_state`; no persisted data changes.

---

## 8. API Changes

### 8.1 TokenBudgetMiddleware Constructor

**Change type:** Modified

**Request:**

```json
{
  "max_tokens": "int - positive provider-reported cumulative token ceiling",
  "abort_reason": "str - middleware abort reason when the hard cap fires",
  "allow_final_response_over_budget": "bool - when true, permit one final over-budget model call with an injected final-answer instruction"
}
```

**Response:**

```json
{
  "MiddlewareDecision": "continue or abort depending on usage and over-budget state"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | `max_tokens <= 0` raises `ValueError` during construction |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/token-budget-final-response-overrun.md` | Design source of truth for the feature |
| MODIFY | `vidbyte/middleware/builtins/token_budget.py` | Add soft-overrun option, final-answer notice transform, and per-run state |
| MODIFY | `tests/test_new_middleware_builtins.py` | Cover default hard-cap behavior and the one-time soft-overrun final-answer path |
| MODIFY | `vidbyte/middleware/README.md` | Document the built-in middleware parameter and behavior |
| MODIFY | `README.md` | Mention the soft-overrun option in the public middleware overview |
| MODIFY | `skills/vidbyte-sdk/middleware.md` | Keep the SDK middleware skill reference aligned with the public API |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `dataclasses` | Python >=3.11 | Internal `_TokenBudgetRunState` dataclass | Low; already used in nearby middleware |
| N/A | N/A | No new external services or package dependencies | N/A |

---

## 11. Rollout & Deployment

- No feature flag is required.
- This is not a breaking change because the new parameter defaults to the current hard-cap behavior.
- Deployment is a normal SDK release.
- Rollback procedure: remove the constructor parameter, `before_model_call` logic, run-state dataclass, tests, and docs updates. Existing callers that did not use the new parameter remain compatible either way.

---

## 12. Open Questions

- [ ] Should the final-answer notice instruct the model to return plain text, call `isDone`, or mention both? The proposed wording says "provide the best final answer now" and "do not call additional tools"; it does not reference `isDone` to avoid leaking internal runtime details into docs.
- [ ] Should the notice text be customizable? The proposed design keeps it fixed to avoid expanding the API beyond the requested parameter.
- [ ] Should `TokenBudgetMiddleware` be documented as best placed late in the middleware list when `allow_final_response_over_budget=True`, so later `system` transforms do not override the notice?

---

## 13. Alternatives Considered

### Alternative 1: Boolean parameter named `continue`

- What: Add `continue: bool` or `continue_on_budget_exceeded: bool`.
- Why rejected: `continue` is a Python keyword and the behavior is not indefinite continuation. `continue_on_budget_exceeded` also implies the run can keep going, which is not the desired bounded final-answer behavior.

### Alternative 2: Enum parameter named `over_budget_behavior`

- What: Add `over_budget_behavior: Literal["abort", "final_response"] = "abort"`.
- Why rejected: This is more extensible, but it is a larger API than the current request requires. The boolean `allow_final_response_over_budget` is explicit enough while preserving the default hard-cap behavior.

### Alternative 3: Runtime-level support in `AgentRuntimeConfig.max_tokens`

- What: Add a soft-overrun option to the core agent runtime budget instead of the middleware.
- Why rejected: The request targets the token budgeting prebuilt middleware. Changing runtime-level `max_tokens` would broaden the behavior across all agents and risks surprising users who rely on it as a hard safety rail.

### Alternative 4: Inject a synthetic provider message instead of a system suffix

- What: Append a user or assistant message to `provider_messages` via `MiddlewareTransform(provider_messages=...)`.
- Why rejected: The runtime already supplies `ctx.system` to `before_model_call`, and a system suffix is the clearest place for high-priority runtime instructions. Provider-message transforms are also more likely to interact with compaction middleware that rewrites message history.
