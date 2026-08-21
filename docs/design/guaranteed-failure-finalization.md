# Design Doc: Guaranteed Failure Finalization

**Status:** Draft
**Author:** Grok
**Created:** 2026-08-21
**Last Updated:** 2026-08-21

## 1. Overview

Linear agent runs already call the `after_run` middleware hook when they return an `AgentResult` (successful answer, budget stop, contract exhaustion, or middleware abort). They do **not** call it when the loop raises after retries and fallback are spent, or when the task is cancelled. Continual-trace, audit, and any custom cleanup hanging off `after_run` therefore miss the failures that most need finalization.

This change makes `after_run` the universal terminal hook for one `AgentRuntime._arun_once` attempt: success paths keep `_finish_result`; raise paths call a sibling `_finish_error` that invokes `after_run` with `ctx.error` set, under `asyncio.shield`, then re-raises the original exception (including `CancelledError`). Harness authors get a matching fail-open `after_execute` override on the existing `execute()` envelope. No new middleware hook and no prebuilt "on error" middleware: middleware cannot run a hook the runtime never calls.

## 2. Goals & Non-Goals

### Goals

- Guarantee `after_run` runs exactly once for every `_arun_once` exit, including unhandled provider errors, exhausted fallback (`AllModelsFailedError`), and `asyncio.CancelledError`.
- Pass `MiddlewareContext.error` on raise-path `after_run` calls; leave it `None` on result-returning paths.
- Ignore `abort` / `retry` / `deny_tool` decisions on the raise path so cleanup cannot become the run outcome.
- Shield error-path `after_run` so cancellation does not skip it; preserve `CancelledError` as `CancelledError` (never wrap it in `AgentExecutionError`).
- Swallow cleanup `Exception`s on the raise path so they cannot replace the original error.
- Skip `ContinualTraceMiddleware`'s extra model call when `ctx.error` is `CancelledError` or `TimeoutError`; still mark the trace finalized.
- Give `Harness` an optional `after_execute` override, fail-open, called from the existing finalize path for success, failure, timeout, and cancellation.
- Update middleware and harness skill docs so `after_run` is described as terminal for every `_arun_once` outcome, not only returned results.

### Non-Goals

- A tenth `MiddlewareHook.ON_RUN_ERROR` or a prebuilt `OnRunErrorMiddleware` as the guarantee.
- Actor-model, MCTS search, and non-text runner paths (they do not participate in the linear middleware loop).
- Enforcing `AgentLoopSettings.timeout_seconds` as a hard `asyncio.timeout` around `arun`.
- Generate-reply-level finalization for `_assert_schema_satisfied` or `_run_auto_handoff` failures that happen after a successful `_finish_result`.
- Changing retry (`on_model_error` RETRY) or fallback-switch behavior; those remain non-terminal.
- New test files or verification scripts (this is a no-new-tests change). Existing CI must still pass.
- Sharing a new public shield utility across agents and harnesses.

## 3. Background & Context

`AgentMiddleware.after_run` is documented as "before returning the final response payload." `AgentRuntime._finish_result` is the only caller. Every `return await self._finish_result(...)` in `_arun_once` is a controlled stop. The exception path is:

```text
_invoke_with_middleware except Exception
  -> on_model_error (retry / abort / re-raise)
_arun_once except BaseException
  -> _fallback_transition
  -> if None: raise          # skips after_run
```

`CancelledError` is `BaseException`, so it never enters `on_model_error`. `TimeoutError` is in `DEFAULT_FALLBACK_ERRORS`; it is only final when the chain cannot advance. `ModelRetryMiddleware` exhausting retries **aborts** (already hits `_finish_result`). The gap is raise-after-recovery, not abort-after-recovery.

In-repo precedents for "always finalize, then re-raise":

- `vidbyte/agents/multi/lifecycle.py` — `try` / `except BaseException` / `finally` + `shielded_close`
- `vidbyte/agents/multi/cleanup.py` — `asyncio.shield` with a second await after `CancelledError`
- `vidbyte/harnesses/execution.py` — success / FAILED / TIMED_OUT finalize; cancel uses a weaker `_finalize_shielded` that only collects

Python is `>=3.11`. Cancellation is counted: catching `CancelledError` does not uncancel the task. The error-path shield must `uncancel()`, finish the shielded work, then `cancel()` again before re-raising.

`after_run` cardinality is already per `_arun_once`, not per `generate_reply`. Reflexion, prosecutor-defender-judge, independent critic, and the grader each call `_arun_once` per trial or stage. This change keeps that cardinality on the raise path.

Field-guide constraints that apply:

- Runtime work stays in `AgentRuntime`; do not invent a second compaction or usage path (`runtime-boundaries.md`).
- Prefer a method on the existing class over a new module of free functions (`class-bound-helpers.md`).
- Worktree CI must use `PYTHONPATH=<worktree>` for the source stage (`local-ci-verification.md`).

Canonical local CI: `python scripts/run_ci.py` after `python -m pip install -e ".[dev]"`. Required remote checks: `.github/workflows/ci.yml` jobs `Source / Python 3.11`, `Source / Python 3.12`, and `Package`.

## 4. Requirements

### Functional Requirements

1. `AgentRuntime._arun_once` must invoke `after_run` on every exit after `before_run` has been attempted, including exceptions and cancellation.
2. Result-returning exits must keep using `_finish_result` and must keep allowing `after_run` to abort a successful result (existing behavior).
3. Raise-path `after_run` must receive `MiddlewareContext.error` set to the exception that is about to propagate.
4. Raise-path `after_run` must ignore `MiddlewareAction.ABORT_RUN`, `RETRY`, and `DENY_TOOL`.
5. Raise-path `after_run` must run under `asyncio.shield` with Python 3.11 `Task.uncancel()` around the second await so a cancelled task still finishes the hook.
6. `CancelledError` that terminates `_arun_once` must still be `CancelledError` at `BaseAgent.generate_reply` (the existing `except BaseException: raise` path).
7. Cleanup `Exception`s from raise-path `after_run` must not replace the original error.
8. `_finish_result` and `_finish_error` together must not call `after_run` twice for the same `_arun_once` (guard with `run_state["__after_run_done__"]`).
9. `on_model_error` retries and in-loop fallback model switches must not call `after_run`.
10. `ContinualTraceMiddleware.after_run` must skip `_run_update` when `ctx.error` is an instance of `asyncio.CancelledError` or `TimeoutError`, and must still set `finalized = True`.
11. Other `ctx.error` values may still attempt one fail-open trace update (existing `fail_closed = False`).
12. `Harness.after_execute(request, output, status, error)` must exist as an optional override defaulting to a no-op.
13. `execute()` must call `after_execute` from `_finalize` for `SUCCEEDED`, `FAILED`, `TIMED_OUT`, and `CANCELLED`, fail-open.
14. Cancelled harness runs must still attempt `after_execute` and collection under shield, then re-raise `CancelledError`.
15. `MiddlewarePipeline._run` must continue to catch `Exception` only, never `BaseException`.
16. Skill and package docs that describe `after_run` as "before the final result is returned" must state that the hook also runs on terminal exceptions, with `ctx.error` set.

### Non-Functional Requirements

- Reliability: original exception identity is the result of a failed `_arun_once`; cleanup is best-effort.
- Compatibility: no new public hook enum member; existing `after_run` overrides keep working; success-path abort behavior is unchanged.
- Performance: one extra shielded task only on the raise path; success path unchanged besides a boolean flag write.
- Observability: `AuditLogMiddleware` already records `error_type` from `ctx.error` and will start seeing raise-path events without code changes.
- Security: error-path context must not add credential fields; keep using `_middleware_context`.
- Canonical full local CI: `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py` from the worktree, with `PYTHONPATH` set to the worktree for the source stage and unset for the package stage.
- Required remote checks: Source / Python 3.11, Source / Python 3.12, Package.

## 5. High-Level Design

```text
_arun_once
  init locals (run_state, started_at, ...)
  try
    before_run
    loop: retries / fallback / tools / budgets
    return _finish_result(...)          # after_run, error=None; may abort
  except BaseException as exc
    error = exc
    raise
  finally
    if error is not None:
      _finish_error(..., error=error)   # shielded after_run, error=exc; ignore decisions

Harness.execute
  try run()
  except timeout / cancel / Exception
    _finalize(..., status, error)       # after_execute fail-open, then collect
    re-raise (CancelledError preserved)
```

Key decisions:

1. Extend `after_run` rather than add `on_run_error`. Existing consumers (`AuditLogMiddleware`, `ContinualTraceMiddleware`) already implement `after_run`.
2. Put the guarantee in `_arun_once`, not `AgentRuntime.arun` or `generate_reply`, to keep per-attempt cardinality.
3. Shield lives in the runtime finalizer, not in `MiddlewarePipeline`.
4. Harness hook is an override like `score()`, not agent middleware.

## 6. Detailed Design

### 6.1 AgentRuntime terminal envelope

**Files:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Responsibility

Owns the single try/except/finally around the linear loop after locals are initialized, plus raise-path `after_run`.

#### Interface / API

```text
async def _arun_once(...) -> AgentResult
    # existing public-to-runtime contract; now always finalizes after_run

async def _finish_error(self, error: BaseException, *, message, context, provider,
                        iteration_count, model_call_count, tokens_used, started_at,
                        metadata, run_state, model_response=None,
                        tool_call_count: int = 0) -> None

async def _await_shielded(self, awaitable: Awaitable[T]) -> T | None
```

#### Logic / Algorithm

1. After initializing `run_state`, counters, and `started_at` (from the current `before_run` call site onward), wrap the remainder of `_arun_once` in:

   ```python
   error: BaseException | None = None
   try:
       ... existing before_run + while True ...
   except BaseException as exc:
       error = exc
       raise
   finally:
       if error is not None:
           await self._finish_error(
               error,
               message=message,
               context=context,
               provider=provider,
               iteration_count=iteration_count,
               model_call_count=model_call_count,
               tokens_used=tokens_used,
               started_at=started_at,
               metadata=runtime_metadata,
               run_state=run_state,
               model_response=last_response,
               tool_call_count=len(call_contexts),
           )
   ```

2. `_finish_result` sets `run_state["__after_run_done__"] = True` after `after_run` returns (success or abort rewrite).

3. `_finish_error` no-ops if that flag is already true (covers `_finish_result` itself raising `CancelledError` mid-hook).

4. `_finish_error` builds `MiddlewareContext` with `hook=AFTER_RUN` and `error=error`, calls `self.middleware.after_run`, discards the decision, and sets the flag. The call is wrapped in `_await_shielded`. Any `Exception` from the hook is swallowed inside the shielded coroutine.

5. `_await_shielded`:

   ```python
   task = asyncio.create_task(awaitable)
   current = asyncio.current_task()
   try:
       return await asyncio.shield(task)
   except asyncio.CancelledError:
       if current is not None:
           current.uncancel()
       try:
           await asyncio.shield(task)
       finally:
           if current is not None:
               current.cancel()
       raise
   ```

   Other `Exception`s from the inner awaitable are caught by the shielded coroutine itself, not by `_await_shielded`.

6. Do not move `started_at` or reorder the inner-context-window hook that currently runs before `run_state` exists. Failures before `before_run` remain outside the envelope (middleware never started).

#### Edge Cases & Error Handling

- `_finish_result` abort of a successful result: unchanged; flag is set; `finally` sees `error is None`.
- Fallback switch (`continue` after `_fallback_transition`): still inside the try; not terminal.
- `AllModelsFailedError` from `_raise_chain_exhausted`: caught as `error`, `_finish_error` runs, then the error propagates into `generate_reply`'s `except Exception` and becomes `AgentExecutionError`.
- `CancelledError`: `_finish_error` runs under shield; `generate_reply` still re-raises `BaseException` unwrapped.
- Nested `_arun_once` (Reflexion / PDJ): each attempt finalizes independently, matching success-path behavior.
- `_finish_error` must not call `_with_middleware_metadata` to invent an `AgentResult`; the run is raising.

### 6.2 ContinualTraceMiddleware cancel/timeout skip

**Files:** `vidbyte/middleware/continual_trace.py`
**Type:** Modified

#### Responsibility

Avoid a billed model call after a dead deadline, while still marking the per-run artifact finalized.

#### Interface / API

```text
async def after_run(self, ctx: MiddlewareContext) -> MiddlewareDecision
```

#### Logic / Algorithm

1. If `state.finalized` is already true, return `continue_` (existing).
2. If `isinstance(ctx.error, (asyncio.CancelledError, TimeoutError))`, set `finalized = True`, `_publish`, return `continue_` without `_run_update`.
3. Otherwise keep the current "update if this iteration was not already traced, then finalize" path.

#### Edge Cases & Error Handling

- Exhausted-fallback `TimeoutError` is a terminal timeout: skip the extra call.
- Other errors (provider, `AllModelsFailedError`) still attempt one fail-open update.
- `_run_update` already catches `Exception`; this guard is only to avoid starting a call that cannot complete under cancel/timeout.

### 6.3 Harness after_execute

**Files:** `vidbyte/harnesses/execution.py`
**Type:** Modified

#### Responsibility

Author-facing fail-open callback on every `execute()` terminal status, including cancellation.

#### Interface / API

```text
async def after_execute(
    self,
    request: Any,
    output: Any,
    status: HarnessRunStatus,
    error: BaseException | None,
) -> None
```

#### Logic / Algorithm

1. Default body is `return None`.
2. `_finalize` gains `error: BaseException | None = None`, builds `HarnessRun` as today, then `await self._safe_after_execute(...)`, then `_maybe_collect`.
3. `_safe_after_execute` awaits `after_execute` and swallows `Exception` (same policy as `_safe_score` / `_maybe_collect`).
4. `execute()` passes the caught exception into `_finalize` / `_finalize_shielded`. Success passes `error=None`.
5. `_finalize_shielded` shields `_finalize(..., CANCELLED, error=exc)` instead of only `_maybe_collect`, so cancel still runs `after_execute` and collection. Keep the existing "catch CancelledError from shield and return" shape plus 3.11 `uncancel()` so the inner task can finish, matching the runtime helper locally (duplicate the small shield, do not import from `AgentRuntime`).

#### Edge Cases & Error Handling

- `after_execute` raising must not change `HarnessTimeoutError`, `HarnessExecutionError`, or `CancelledError`.
- `score()` remains success-only.
- The cancelled `HarnessRun` is not returned to the caller (cancel still re-raises); it exists so `after_execute` and collection see `CANCELLED`.

### 6.4 Documentation

**Files:** listed in the manifest
**Type:** Modified

#### Responsibility

State that `after_run` is the terminal hook for returned results **and** terminal exceptions (`ctx.error` set), and that harness authors override `after_execute` for envelope-level cleanup.

#### Logic / Algorithm

1. Update the hook table in `skills/vidbyte-sdk/middleware.md`, `skills/sdk/SKILL.md`, and `skills/usage/available_features.md`.
2. Update `AgentMiddleware.after_run` docstring.
3. Note the cancel/timeout skip in `skills/vidbyte-sdk/continual-tracing.md`.
4. Document `after_execute` in `skills/harnesses/SKILL.md` and `vidbyte/harnesses/README.md`.
5. One-sentence clarification in `vidbyte/middleware/README.md` and the middleware paragraph of `llms.txt` if it currently implies success-only.

## 7. Data Model Changes

No persisted schema, collection, or index changes.

`MiddlewareContext.error` already exists (`BaseException | None`). This change is the first time `after_run` populates it.

`run_state["__after_run_done__"]` is an internal boolean flag on the existing per-run dict. It is not part of public result metadata.

## 8. API Changes

**Modified (compatible):**

- `AgentMiddleware.after_run`: same signature; may now be invoked with `ctx.error` set. Overrides that ignored `ctx.error` keep working.
- `Harness`: new optional override `after_execute`. Existing subclasses that do not define it keep the no-op.

**Unchanged:**

- `MiddlewareHook` enum (still nine members).
- `MiddlewareDecision` actions.
- `BaseAgent.generate_reply` exception wrapping (`Exception` → `AgentExecutionError`, `BaseException` re-raised).

**Deprecated:** N/A - no API is removed.

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/guaranteed-failure-finalization.md` | This design doc. |
| MODIFY | `vidbyte/agents/runtime.py` | `_arun_once` envelope, `_finish_error`, `_await_shielded`, `__after_run_done__` in `_finish_result`. |
| MODIFY | `vidbyte/middleware/continual_trace.py` | Skip final LLM update on cancel/timeout. |
| MODIFY | `vidbyte/middleware/base.py` | `after_run` docstring: terminal for success and failure. |
| MODIFY | `vidbyte/harnesses/execution.py` | `after_execute`, `_safe_after_execute`, pass `error` through finalize, shield cancel through `_finalize`. |
| MODIFY | `skills/vidbyte-sdk/middleware.md` | `after_run` hook table and failure-path contract. |
| MODIFY | `skills/sdk/SKILL.md` | Lifecycle hook table. |
| MODIFY | `skills/usage/available_features.md` | `after_run` one-liner. |
| MODIFY | `skills/vidbyte-sdk/continual-tracing.md` | Cancel/timeout skip. |
| MODIFY | `skills/harnesses/SKILL.md` | `after_execute` on the Harness contract. |
| MODIFY | `vidbyte/harnesses/README.md` | Document `after_execute` next to `score()`. |
| MODIFY | `vidbyte/middleware/README.md` | Terminal `after_run` on exceptions. |
| MODIFY | `llms.txt` | Middleware hook sentence if it implies success-only. |

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python asyncio (`shield`, `Task.uncancel`) | stdlib, Python 3.11+ | Shielded cleanup under cancellation | Low — repo already requires `>=3.11` and uses `asyncio.timeout` / `CancelledError` elsewhere |
| N/A - no new third-party packages | N/A | N/A | N/A |

## 11. Rollout & Deployment

- Additive, default-on behavior for linear `after_run` consumers. Existing middleware that does not read `ctx.error` is unchanged on success and newly invoked on failure (usually desirable).
- `ContinualTraceMiddleware` is the one consumer that must not do extra billed work after cancel/timeout; that guard ships in the same PR.
- No feature flag. Alpha SDK (`0.1.0`); document the hook contract in the same change.
- Rollback: revert the PR. No persisted data to migrate.

## 12. Open Questions

- [x] Tenth hook vs guaranteed `after_run` — settled: guarantee `after_run`.
- [x] Prebuilt middleware as the mechanism — settled: no; runtime envelope is the mechanism.
- [x] Harness `after_execute` in this PR — settled: yes, as a `score()`-shaped override, not harness middleware.
- [ ] N/A - no remaining open questions that block implementation.

## 13. Alternatives Considered

### New `on_run_error` middleware hook

- What: Add `MiddlewareHook.ON_RUN_ERROR` and call it only on raise paths; leave `after_run` success-only.
- Why rejected: Every "always finalize" consumer would implement both hooks. `ContinualTraceMiddleware` and `AuditLogMiddleware` would still miss failures until they grew a second method. One terminal hook with `ctx.error` is the complete smaller change.

### Prebuilt `OnRunErrorMiddleware`

- What: A builtin that takes an `on_error` callback and overrides `after_run`.
- Why rejected: Middleware cannot fire if the runtime never calls the hook. Shipping it before the envelope would look correct and be a silent no-op on the paths that matter. After the envelope exists, authors subclass `AgentMiddleware` and override `after_run` — that is the repo grain. A callback wrapper is an abstraction with one implementation.

### Finalize in `BaseAgent.generate_reply`

- What: try/finally at the agent envelope so schema-violation and auto-handoff failures are covered.
- Why rejected: those failures happen after `_finish_result` already ran `after_run` with `error=None`. A second call would double-finalize success-then-fail. That is a different feature. Out of scope.

### Catch `BaseException` in `MiddlewarePipeline`

- What: Convert `CancelledError` inside a hook into fail-open continue or abort.
- Why rejected: would violate "preserve `CancelledError`". Shield belongs outside the pipeline.
