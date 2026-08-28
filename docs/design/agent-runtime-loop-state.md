# Design Doc: Agent Runtime Loop State

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-25
**Last Updated:** 2026-08-25

---

## 1. Overview

`AgentRuntime._arun_once` and its three private helpers (`_invoke_with_middleware`, `_process_tool_call`, `_finish_result`) each rebuild a `MiddlewareContext` snapshot by passing the same 8-11 keyword arguments (`message`, `context`, `provider`, `iteration_count`, `model_call_count`, `tool_call_count`, `tokens_used`, `started_at`, `metadata`, `run_state`, `model_response`) into `self._middleware_context(...)` at every one of its 11 call sites. This change introduces one mutable, per-attempt parameter object, `BaseAgentRuntimeLoopState`, that carries this bag plus the inner context-window algorithm, its mutable state, and iteration outputs. `_middleware_context`, `_finish_result`, and `_process_tool_call` accept `state: BaseAgentRuntimeLoopState` instead of the individual fields, collapsing every call site from 8-16 lines down to 1-4. `_invoke_with_middleware` keeps its existing public keyword signature (it has external callers outside `runtime.py`) but builds a local `BaseAgentRuntimeLoopState` internally to get the same reduction on its own two call sites. Runtime state handoff keys are declared by `AgentRuntimeStateKey` rather than repeated string literals.

---

## 2. Goals & Non-Goals

### Goals

- Eliminate the repeated 8-11 argument bag at every `self._middleware_context(...)` call site inside `AgentRuntime`.
- Eliminate the repeated 9-argument bag at every `self._finish_result(...)` call site inside `_arun_once`.
- Derive `tool_call_count` (`len(call_contexts)`) as a `@property` on the new state object instead of recomputing `len(call_contexts)` inline at 8 of the 11 `_middleware_context` call sites.
- Keep `_invoke_with_middleware`'s existing public keyword-argument signature unchanged, since `vidbyte/agents/algorithms/reflexion.py` and `vidbyte/agents/algorithms/multi_provider_agentic_grader.py` call it directly with that signature.
- Preserve every existing runtime behavior exactly: this is a structural refactor, not a logic change. No call site's effective arguments change.

### Non-Goals

- Changing `_invoke_with_middleware`'s or `_process_tool_call`'s call sites in `reflexion.py` / `multi_provider_agentic_grader.py`. `_process_tool_call` has no external callers so its signature does change, but no caller outside `runtime.py` is touched.
- Touching `_budget_stop`, `_contract_counters`, `_final_result`, `_stopped_result`, `_middleware_abort_result`, `_llm_trace_inputs`, `_build_iteration_call_options`, `_enforce_tool_settings`, `_enforce_tool_settings_after_failure`, or `execute_tool_call`. These take a different, smaller subset of fields for a different purpose (budget/contract/tool-policy checks, not middleware-context construction) and are out of scope.
- Implementing PR #351 ("Guaranteed Failure Finalization") in this PR. That work (the `_finish_error` / `_await_shielded` envelope) is rebased onto this refactor's branch and updated separately, after this PR is reviewable, so the two changes stay independently reviewable.
- Any new test files (this is a "no tests" design-doc workflow; existing tests are the regression net for a pure refactor).
- Moving `BaseAgentRuntimeLoopState` into `vidbyte/lib/dataclasses/`. That package is for shared, externally-constructed, validated value types (see `strict-config-dataclasses.md`); this state is mutable scratch state owned by exactly one `_arun_once`/`_invoke_with_middleware` call, matching the existing `_RunState` precedent in `vidbyte/workflows/machine.py` while remaining defined next to the runtime that owns it.

---

## 3. Background & Context

A user question surfaced that every `self.middleware.after_iteration(self._middleware_context(MiddlewareHook.AFTER_ITERATION, message=..., context=..., provider=..., iteration_count=..., model_call_count=..., tool_call_count=len(call_contexts), tokens_used=..., started_at=..., metadata=..., run_state=..., model_response=...))` block in `vidbyte/agents/runtime.py` is extremely long, and asked whether a `@property` on the runtime class could shrink it.

It cannot: `message`, `iteration_count`, `model_call_count`, `tokens_used`, `provider`, `run_state`, and `call_contexts` are local variables inside one `_arun_once` call, not instance state on `self`. They mutate every pass through `_arun_once`'s `while True:` loop, and per PR #351's design doc, `_arun_once` is called multiple times per `AgentRuntime` instance for nested trials (Reflexion, prosecutor-defender-judge), each finalizing independently. Hoisting them onto `self.iteration_count` etc. would let two nested/concurrent `_arun_once` calls on the same runtime stomp on each other's counters.

The actual fix is a parameter-object refactor: bundle the mutable per-call locals into one object created once per `_arun_once` (or `_invoke_with_middleware`) call, and thread that object through instead of the individual fields. `tool_call_count`, which is recomputed as `len(call_contexts)` at 8 of the 11 `_middleware_context` call sites, becomes a `@property` on that object once it also holds `call_contexts`.

This also directly benefits PR #351 ("Guaranteed Failure Finalization", open, branch `feat/guaranteed-failure-finalization`), which adds a `_finish_error` sibling to `_finish_result` carrying the exact same argument bag plus `error`. Landing the parameter object first means `_finish_error` is written against `BaseAgentRuntimeLoopState` from the start instead of duplicating the giant signature a second time.

Constraints from the field guide (`field-guide/vidbyte-sdk/`):

- `class-bound-helpers.md`: prefer one named class over free functions for a shared concern — satisfied by `BaseAgentRuntimeLoopState` being one class rather than a loose dict.
- `strict-config-dataclasses.md`: shared, validated value types live in `vidbyte/lib/dataclasses/` as `frozen=True, slots=True`. `BaseAgentRuntimeLoopState` is neither shared nor a validated config value — it is mutable, per-call scratch state — so it follows the `vidbyte/workflows/machine.py::_RunState` precedent instead: a `@dataclass(slots=True)` (not frozen) defined next to the class that owns it.
- `local-ci-verification.md`: the source CI stage must run with `PYTHONPATH=<worktree>` or it silently tests the canonical checkout's old code.

Canonical local CI: `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py` (source stage needs `PYTHONPATH=$(pwd)` from a worktree; package stage needs it unset). Required remote checks: `.github/workflows/ci.yml` jobs `Source / Python 3.11`, `Source / Python 3.12`, and `Package`.

---

## 4. Requirements

### Functional Requirements

1. Add a `@dataclass(slots=True)` named `BaseAgentRuntimeLoopState` in `vidbyte/agents/runtime.py`, holding: `message: str`, `context: BaseAgentContext`, `provider: str`, `metadata: dict[str, Any]`, `started_at: float`, `inner_context_window_algorithm: InnerContextWindowAlgorithm | None`, `context_window_state: dict[str, Any]`, `run_state: dict[Any, Any]` (default `{}`; heterogeneous middleware class and string keys), `call_contexts: list[ToolCallContext]` (default `[]`), `iteration_outputs: list[str]` (default `[]`), `iteration_count: int` (default `0`), `model_call_count: int` (default `0`), `tokens_used: int | None` (default `None`), `model_response: object | None` (default `None`).
2. `BaseAgentRuntimeLoopState` exposes `tool_call_count` as a read-only `@property` returning `len(self.call_contexts)`.
3. `_middleware_context` accepts `(self, hook: MiddlewareHook, state: BaseAgentRuntimeLoopState, *, tool_call=None, tool_result=None, model_response=None, model_usage=None, error=None, tool_is_internal=False, provider_messages=(), system=None, tool_call_count=None, metadata=None)`. `model_response` falls back to `state.model_response` when not given; `tool_call_count` falls back to `state.tool_call_count`; `metadata` falls back to `state.metadata`. Every other field (`message`, `provider`, `iteration_count`, `model_call_count`, `tokens_used`, `agent_context`, `run_state`, `elapsed_seconds`) is always read from `state`.
4. `_finish_result` accepts `(self, result: AgentResult, state: BaseAgentRuntimeLoopState) -> AgentResult` and internally computes the same `tool_call_count=int(dict(result.metadata).get("tool_call_count", 0))` override it does today, passed into `_middleware_context`.
5. `_process_tool_call` accepts `(self, call: ToolCall, messages: list[dict[str, Any]], state: BaseAgentRuntimeLoopState, *, trace_context: SpanContext | None = None)`. It reads `provider`/`call_contexts`/`iteration_count`/`tokens_used`/`metadata`/`run_state`/`model_response` from `state`, mutates `state.call_contexts` in place exactly where it does today (`state.call_contexts.append(context_record)`), and keeps its `AFTER_TOOL_CALL` call's existing `tool_call_count=len(call_contexts) + 1` and `metadata=self._tool_call_middleware_metadata(...)` overrides (both become `tool_call_count=state.tool_call_count + 1` / `metadata=self._tool_call_middleware_metadata(state.metadata, call)`).
6. `_invoke_with_middleware` keeps its exact current public signature (`handle`, `message`, `call_options`, `context`, `iteration_count`, `model_call_count`, `call_contexts`, `tokens_used`, `started_at`, `metadata`, `run_state=None`, `trace_context=None`, `compaction_count=0`) unchanged. Internally it builds one local `BaseAgentRuntimeLoopState` from those arguments (`provider=handle.provider`, `call_contexts=list(call_contexts)`, `metadata=dict(metadata)`, `run_state=run_state if run_state is not None else {}`) and uses it for both of its `_middleware_context` calls (`BEFORE_MODEL_CALL`, `ON_MODEL_ERROR`).
7. `_arun_once` constructs one `state = BaseAgentRuntimeLoopState(...)` immediately after computing `handle.provider` and `self.middleware.clock()`, including the inner context-window algorithm, its mutable context-window state, and iteration-output storage. Every read/write of the loop state inside `_arun_once` becomes a read/write of the matching `state.` field (`state.provider = transition.provider` on fallback, `state.model_response = raw_result` immediately after a non-`AgentResult` raw result is obtained, `state.iteration_outputs.append(...)`, `state.iteration_count += 1`, etc.). `message` and `context` remain plain locals (they never mutate) and are not re-read through `state` outside of `_middleware_context`/`_finish_result` calls.
8. `state.model_response` is updated to the freshly obtained `raw_result` at exactly the point `_arun_once` does it today (immediately after confirming `raw_result` is not itself an `AgentResult`, before `iteration_count` is incremented) and nowhere else. Every `_middleware_context`/`_finish_result` call site in `_arun_once` that today passes `model_response=raw_result` or `model_response=last_response` omits the argument and relies on this default, since `state.model_response` already holds the correct value at every one of those call sites (verified call site by call site in Section 6.4).
9. Every `_finish_result` call site in `_arun_once` becomes `return await self._finish_result(<result>, state)`.
10. Every `_middleware_context` call site in `_arun_once` passes only the hook and `state`, plus any genuinely-varying override (`model_usage` at `AFTER_MODEL_RESPONSE` only).
11. No change to `MiddlewareContext`, `MiddlewareHook`, `MiddlewareDecision`, or any public agent/middleware API. No change to `AgentRuntime.__init__`, `arun`, `build_context`, or any method not listed above.

### Non-Functional Requirements

- Behavior-preserving: for every existing call site, the `MiddlewareContext` produced after the refactor must be field-for-field identical to the one produced before it, for the same point in execution.
- No new runtime allocations beyond the one `BaseAgentRuntimeLoopState` per `_arun_once` call and one per `_invoke_with_middleware` call (replacing, not adding to, the existing per-call-site dict/list work `_middleware_context` already did).
- Readability: `BaseAgentRuntimeLoopState`'s docstring and the one comment at the `state.model_response = raw_result` assignment must make the "set once per iteration, read as current response until next iteration" invariant explicit, since it is now implicit at every downstream call site instead of spelled out via an explicit keyword each time.
- No new package-level public API surface: `BaseAgentRuntimeLoopState` is not exported from `vidbyte/agents/__init__.py` or any `__all__`.

---

## 5. High-Level Design

```
_arun_once
  state = BaseAgentRuntimeLoopState(message, context, provider=handle.provider, metadata, started_at)
  before_run: self._middleware_context(BEFORE_RUN, state)
  while True:
    before_iteration: self._middleware_context(BEFORE_ITERATION, state)
    raw_result, state.model_call_count, compaction_count = _invoke_with_middleware(handle, message, ..., context=context, iteration_count=state.iteration_count, ...)  # signature unchanged
      [_invoke_with_middleware builds its OWN local BaseAgentRuntimeLoopState from its args]
    state.model_response = raw_result        # single point of truth from here on
    state.iteration_count += 1
    state.tokens_used = ...
    after_model_response: self._middleware_context(AFTER_MODEL_RESPONSE, state, model_usage=...)
    for call in tool_calls:
      processed = self._process_tool_call(call, messages, state, trace_context=...)
        [state.call_contexts.append(...) mutates the same state the loop already holds]
    after_iteration: self._middleware_context(AFTER_ITERATION, state)
    return await self._finish_result(final_or_stopped_result, state)
```

Key decisions:

1. One mutable object, constructed once per attempt, replaces ~9 separate locals that today move through `_arun_once` in lockstep. This mirrors the existing `_RunState` pattern in `vidbyte/workflows/machine.py`.
2. `_invoke_with_middleware` gets an internal-only `BaseAgentRuntimeLoopState`, not a signature change, because two files outside `runtime.py` call it directly with the current keyword signature.
3. `_process_tool_call` does get a signature change (`state` replaces 9 of its 11 parameters) because it has zero external callers — verified via repo-wide grep.
4. `model_response` defaulting to `state.model_response` (rather than always requiring an explicit override) is safe because `_arun_once` already updates it at exactly one point per iteration, before any hook that should see the new value fires, and never anywhere else in the method — this is verified per-call-site in Section 6.4, not assumed.

---

## 6. Detailed Design

### 6.1 `BaseAgentRuntimeLoopState`

**Files:** `vidbyte/agents/runtime.py`
**Type:** New module-scoped class, defined directly above `class AgentRuntime` and not exported by the agent package

#### Responsibility

Owns the mutable per-attempt state (`_arun_once`) or per-call state (`_invoke_with_middleware`) that `_middleware_context` reads to build a `MiddlewareContext` snapshot.

#### Interface / API

```python
@dataclass(slots=True)
class BaseAgentRuntimeLoopState:
    """Mutable state threaded through one direct agent runtime attempt."""

    message: str
    context: BaseAgentContext
    provider: str
    metadata: dict[str, Any]
    started_at: float
    inner_context_window_algorithm: InnerContextWindowAlgorithm | None = None
    context_window_state: dict[str, Any] = field(default_factory=dict)
    run_state: dict[Any, Any] = field(default_factory=dict)
    call_contexts: list[ToolCallContext] = field(default_factory=list)
    iteration_outputs: list[str] = field(default_factory=list)
    iteration_count: int = 0
    model_call_count: int = 0
    tokens_used: int | None = None
    model_response: object | None = None

    @property
    def tool_call_count(self) -> int:
        """Tool calls recorded so far in this attempt."""
        return len(self.call_contexts)
```

#### Logic / Algorithm

No behavior beyond field storage and the one derived property. Not frozen: every field except `message`/`context` is reassigned or mutated during the loop it belongs to.

#### Edge Cases & Error Handling

- None — this is a plain value container. Validation is not applicable (`strict-config-dataclasses.md` governs externally-constructed, validated config types; this is internal scratch state built only by `AgentRuntime` itself from already-valid values).

---

### 6.2 `_middleware_context`

**Files:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Responsibility

Builds a `MiddlewareContext` snapshot from one `BaseAgentRuntimeLoopState` plus whatever varies at a specific call site.

#### Interface / API

```python
def _middleware_context(self, hook: MiddlewareHook, state: BaseAgentRuntimeLoopState, *, tool_call: ToolCall | None = None, tool_result: ToolResult | None = None, model_response: object | None = None, model_usage: object | None = None, error: BaseException | None = None, tool_is_internal: bool = False, provider_messages: Sequence[Mapping[str, Any]] = (), system: str | None = None, tool_call_count: int | None = None, metadata: Mapping[str, Any] | None = None) -> MiddlewareContext:
```

#### Logic / Algorithm

1. Resolve `resolved_tool_call_count = tool_call_count if tool_call_count is not None else state.tool_call_count`.
2. Resolve `resolved_model_response = model_response if model_response is not None else state.model_response`.
3. Resolve `resolved_metadata = metadata if metadata is not None else state.metadata`.
4. Construct and return `MiddlewareContext` reading `provider`, `message`, `iteration_count`, `model_call_count`, `tokens_used`, `agent_context`, `run_state` directly from `state`; `elapsed_seconds=max(0, self.middleware.clock() - state.started_at)`; everything else from the resolved values or the passed-through override parameters (`tool_call`, `tool_result`, `model_usage`, `error`, `tool_is_internal`, `provider_messages`, `system`) exactly as today.

#### Edge Cases & Error Handling

- No behavior change from today's version for any existing caller; this is a pure signature/plumbing change. The three resolvable fields (`tool_call_count`, `model_response`, `metadata`) preserve today's exact value at every one of the 11 call sites (verified in 6.4/6.5/6.6 below).

---

### 6.3 `_finish_result`

**Files:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Interface / API

```python
async def _finish_result(self, result: AgentResult, state: BaseAgentRuntimeLoopState) -> AgentResult:
```

#### Logic / Algorithm

Identical body to today, except the `after_run` call becomes `self._middleware_context(MiddlewareHook.AFTER_RUN, state, tool_call_count=int(dict(result.metadata).get("tool_call_count", 0)))`, and the subsequent `_middleware_abort_result`/`_with_context_window_metadata`/`_with_run_state_metadata` calls read `state.iteration_count`, `state.tokens_used`, `state.metadata`, `state.run_state` instead of the old individual parameters.

#### Edge Cases & Error Handling

- Unchanged from today: `ABORT_RUN` still rebuilds `result` before the metadata merges; the metadata merges still run unconditionally.

---

### 6.4 `_arun_once`

**Files:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### Responsibility

Same as today (drive one direct model/tool attempt); this section only changes how call sites reach their arguments.

#### Logic / Algorithm

1. Keep `run_options = dict(options or {})`.
2. Build `state = BaseAgentRuntimeLoopState(message=message, context=context, provider=handle.provider, metadata=dict(metadata or {}), started_at=self.middleware.clock(), inner_context_window_algorithm=AgentRuntimeContextAlgorithms(self).inner_loop_algorithm())` where today's code builds `provider`, `runtime_metadata`, and the inner algorithm state separately.
3. Inner-context-window setup uses `state.inner_context_window_algorithm` and the dedicated `state.context_window_state` dict; it does not add private algorithm objects to middleware metadata.
4. `tool_schemas = self._resolve_tool_schemas(state.provider)`.
5. Keep `messages`, `rejections`, `compaction_count`, `last_assistant_output`, `active_trace_context`, `fallback_index`, `fallback_attempts`, `fallback_errors` as plain locals; `iteration_outputs` is owned by `state` because it is part of the attempt's durable result metadata.
6. `BEFORE_RUN`: `self._middleware_context(MiddlewareHook.BEFORE_RUN, state)`. On abort: `self._finish_result(self._middleware_abort_result(decision, iteration_count=state.iteration_count, tokens_used=state.tokens_used, contexts=state.call_contexts), state)`.
7. Loop top: `_run_inner_context_window_hook` call and `_budget_stop` call read `state.iteration_count`/`state.tokens_used`/`state.call_contexts`/`state.metadata`/`state.provider` instead of the old locals; on a budget stop, `return await self._finish_result(stop_result, state)` (drops the old explicit `model_response=last_response` — see point 9 below).
8. `BEFORE_ITERATION`: `self._middleware_context(MiddlewareHook.BEFORE_ITERATION, state)` (drops the old explicit `model_response=last_response`).
9. `_invoke_with_middleware` call: unchanged keyword names, but every value now reads from `state` (`context=context, iteration_count=state.iteration_count, model_call_count=state.model_call_count, call_contexts=state.call_contexts, tokens_used=state.tokens_used, started_at=state.started_at, metadata=state.metadata, run_state=state.run_state`), and the return unpacks into `raw_result, state.model_call_count, compaction_count = await self._invoke_with_middleware(...)`.
10. On `BaseException` from that call: fallback transition reads `provider=state.provider`; on a non-`None` transition, `handle, state.provider = transition.handle, transition.provider`; `self._publish_fallback_metadata(state.run_state, ...)`.
11. If `raw_result` is an `AgentResult`: `return await self._finish_result(raw_result, state)`. This is the one early-return branch that must NOT update `state.model_response` first — it needs the *previous* iteration's response (today's explicit `model_response=last_response`), which is exactly what the default already resolves to, since `state.model_response` has not been touched yet this iteration.
12. Otherwise: `state.model_response = raw_result` (single point of truth from here on — comment this line to make the invariant explicit), then `state.iteration_count += 1`, `last_assistant_output = handle.extract_text(raw_result)`, `state.iteration_outputs.append(last_assistant_output or "")`, `state.run_state[AgentRuntimeStateKey.ITERATION_OUTPUTS.value] = tuple(state.iteration_outputs)`, and `state.tokens_used = self._add_token_usage(state.tokens_used, ...)`.
13. `AFTER_MODEL_RESPONSE`: `self._middleware_context(MiddlewareHook.AFTER_MODEL_RESPONSE, state, model_usage=usage_record.usage if usage_record is not None else None)` — drops the old explicit `model_response=raw_result` (now redundant with the default set in step 12).
14. No-tool-calls branch: `token_stop`/contract-unsatisfied/`final` results all call `return await self._finish_result(<result>, state)`, dropping their old explicit `model_response=raw_result`. The `AFTER_ITERATION` call inside this branch drops its old explicit `model_response=raw_result` too.
15. Tool-call loop: `processed = await self._process_tool_call(call, messages, state, trace_context=active_trace_context)` (drops `provider`, `call_contexts`, and the 8 other now-redundant keyword arguments). The `IS_DONE_TOOL_NAME` branch's `AFTER_ITERATION` call and its `_finish_result` calls drop their old explicit `model_response=raw_result` for the same reason as step 14 — `_process_tool_call` does not touch `state.model_response`, so it is still `raw_result` from step 12.
16. Post-loop `AFTER_ITERATION` call and its `_finish_result` call: same pattern.

#### Edge Cases & Error Handling

- The one place `model_response` must NOT default to `state.model_response` is never reached, because there is no call site in `_arun_once` where the *desired* value differs from whatever `state.model_response` currently holds — every site was audited above. If a future edit needs a genuinely different value at some new call site, `_middleware_context`'s `model_response=` override parameter still exists for that.
- Fallback transitions that change `state.provider` mid-loop are read by every subsequent `_middleware_context` call automatically, exactly as today's reassigned `provider` local was.

---

### 6.5 `_invoke_with_middleware`

**Files:** `vidbyte/agents/runtime.py`
**Type:** Modified (body only; public signature unchanged)

#### Interface / API

```python
async def _invoke_with_middleware(self, handle: RunnerHandle, message: str, call_options: Mapping[str, Any], *, context: BaseAgentContext, iteration_count: int, model_call_count: int, call_contexts: Sequence[ToolCallContext], tokens_used: int | None, started_at: float, metadata: Mapping[str, Any], run_state: dict[type, Any] | None = None, trace_context: SpanContext | None = None, compaction_count: int = 0) -> tuple[object | AgentResult, int, int]:
```

(Byte-identical to today's signature — required so `reflexion.py`'s `_reflect_after_failure` and `multi_provider_agentic_grader.py`'s grader call keep working unmodified.)

#### Logic / Algorithm

1. First line of the body: `state = BaseAgentRuntimeLoopState(message=message, context=context, provider=handle.provider, metadata=dict(metadata), started_at=started_at, run_state=run_state if run_state is not None else {}, call_contexts=list(call_contexts), iteration_count=iteration_count, model_call_count=model_call_count, tokens_used=tokens_used)`.
2. Replace the retry `while True:` loop's two `_middleware_context` calls (`BEFORE_MODEL_CALL`, `ON_MODEL_ERROR`) with calls that pass `state` instead of the 8-9 individual keywords each currently repeats; `ON_MODEL_ERROR` still passes `error=exc` explicitly (state has no error field).
3. Replace `model_call_count += 1` with `state.model_call_count += 1`; replace every other read of `iteration_count`/`tokens_used`/`call_contexts` in this method (`_llm_trace_inputs`, `_middleware_abort_result` calls, `self.middleware.sleep` gate) with the matching `state.` field.
4. Both `return` statements that currently return the plain `model_call_count` local now return `state.model_call_count`.

#### Edge Cases & Error Handling

- `run_state` passed in by `_arun_once` is `state.run_state` from the caller's own `BaseAgentRuntimeLoopState` — the same dict object, not a copy — so mutations middleware makes to it inside `_invoke_with_middleware`'s local state remain visible to the caller's state after the call returns, exactly as today's pass-by-reference `run_state` dict did.
- `call_contexts` and `metadata` ARE copied (`list(...)`, `dict(...)`) into the local state, matching today's behavior: this method never mutates either one, it only reads them, so a copy vs. a reference makes no observable difference, and the copy satisfies the concrete `list`/`dict` field types when a caller (e.g. `reflexion.py`, passing `call_contexts=()`) hands in a different `Sequence`/`Mapping` implementation.

---

### 6.6 `_process_tool_call`

**Files:** `vidbyte/agents/runtime.py`
**Type:** Modified (signature and body)

#### Interface / API

```python
async def _process_tool_call(self, call: ToolCall, messages: list[dict[str, Any]], state: BaseAgentRuntimeLoopState, *, trace_context: SpanContext | None = None) -> tuple[ToolCallContext, ToolResult] | AgentResult:
```

#### Logic / Algorithm

1. `call = self.tools.prepare_call(call)`, `tool_is_internal = self._tool_is_internal(call)` — unchanged.
2. `settings_outcome = self._enforce_tool_settings(call, state.provider, messages, state.call_contexts, tool_is_internal, iteration_count=state.iteration_count, tokens_used=state.tokens_used)` — unchanged except reading from `state`.
3. `BEFORE_TOOL_CALL`: `self._middleware_context(MiddlewareHook.BEFORE_TOOL_CALL, state, tool_call=call, tool_is_internal=tool_is_internal)` (drops the old explicit `model_response=model_response` — the parameter no longer exists; `state.model_response` already holds the value the caller used to pass in).
4. Retry loop: `context_record, result = self._middleware_denied_tool(call, state.provider, decision, iteration_count=state.iteration_count)` or `await self.execute_tool_call(call, provider=state.provider, trace_context=trace_context, iteration_count=state.iteration_count, tool_is_internal=tool_is_internal)` — unchanged except reading from `state`.
5. `AFTER_TOOL_CALL`: `self._middleware_context(MiddlewareHook.AFTER_TOOL_CALL, state, tool_call=call, tool_result=result, tool_is_internal=tool_is_internal, tool_call_count=state.tool_call_count + 1, metadata=self._tool_call_middleware_metadata(state.metadata, call))` — keeps both existing overrides (count-before-append needs `+1`; metadata is a transform, not the raw bag).
6. `state.call_contexts.append(context_record)` in place of `call_contexts.append(context_record)`.
7. `self._append_tool_result_message(messages, call, result, state.provider, after_decision)`.
8. `failure_stop = self._enforce_tool_settings_after_failure(context_record, tool_is_internal, state.call_contexts, iteration_count=state.iteration_count, tokens_used=state.tokens_used)` — unchanged except reading from `state`.

#### Edge Cases & Error Handling

- `_process_tool_call` mutates `state.call_contexts` in place (`.append(...)`); since `_arun_once` passes its own `state` object by reference, the caller's `state.call_contexts` (and therefore `state.tool_call_count`) reflects the appended tool call immediately after `_process_tool_call` returns — matching today's shared-list-reference behavior exactly.
- The `AFTER_TOOL_CALL` count-before-append `+1` and the transformed `metadata` are the only two fields this method must override; every other field correctly defaults from `state`.

---

## 7. Data Model Changes

N/A - `BaseAgentRuntimeLoopState` is not a persisted schema, collection, index, or package-level public API type. It is an in-process value object scoped to one `_arun_once`/`_invoke_with_middleware` call.

---

## 8. API Changes

**Modified (compatible, internal-only):**

- `AgentRuntime._middleware_context`: signature changes from ~19 keyword parameters to `(hook, state, **overrides)`. Private method (`_`-prefixed), zero callers outside `runtime.py`.
- `AgentRuntime._finish_result`: signature changes from `(result, **9 keywords)` to `(result, state)`. Private method, zero callers outside `runtime.py`.
- `AgentRuntime._process_tool_call`: signature changes from `(call, provider, messages, call_contexts, **9 keywords)` to `(call, messages, state, *, trace_context=None)`. Private method, zero callers outside `runtime.py` (verified via repo-wide grep for `_process_tool_call`).

**Unchanged:**

- `AgentRuntime._invoke_with_middleware`: public keyword signature is byte-identical to today's. `reflexion.py` and `multi_provider_agentic_grader.py` keep calling it exactly as they do today.
- `AgentRuntime.arun`, `AgentRuntime.build_context`, `AgentRuntime.__init__`, `MiddlewareContext`, `MiddlewareHook`, `MiddlewareDecision`, `MiddlewareAction` — no changes.

**Deprecated:** N/A - no API is removed; nothing here was public.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/agent-runtime-loop-state.md` | This design doc. |
| MODIFY | `vidbyte/agents/runtime.py` | Add `BaseAgentRuntimeLoopState`; rewrite `_middleware_context`, `_finish_result`, `_process_tool_call`, `_arun_once`; rewrite `_invoke_with_middleware`'s body (signature unchanged); add runtime state-key usage. |
| MODIFY | `vidbyte/lib/enums/agent_runtime.py` | Declare the runtime run-state key enum alongside the runtime-type enum. |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export the runtime run-state key enum from the SDK enum namespace. |

---

## 10. Dependencies & External Services

N/A - no new third-party packages. `dataclasses` is Python stdlib, already used elsewhere in this repo (`vidbyte/workflows/machine.py`, `vidbyte/lib/dataclasses/*`).

---

## 11. Rollout & Deployment

- Pure internal refactor behind no flag; behavior must be bit-for-bit identical to today for every existing test.
- Not a breaking change: no public API changes. The two external callers of `_invoke_with_middleware` (`reflexion.py`, `multi_provider_agentic_grader.py`) require no edits.
- Alpha SDK (`0.1.0`); no migration path needed.
- Rollback: revert the PR. No persisted data, no schema, nothing to migrate.
- Follow-up (out of scope for this PR): PR #351 ("Guaranteed Failure Finalization", branch `feat/guaranteed-failure-finalization`) is rebased onto this PR's branch after this PR is opened, and its `_finish_error`/`_await_shielded` code is rewritten to accept `BaseAgentRuntimeLoopState` instead of the same 9-11 keyword bag it currently duplicates. That PR keeps `base: main` throughout (per this workspace's stacked-PR-orphan lesson — a PR's base must never be retargeted to another feature branch), and its description notes the dependency on this PR so the diff is understood to shrink once this PR merges to main.

---

## 12. Open Questions

- [x] Where does `BaseAgentRuntimeLoopState` live — `vidbyte/lib/dataclasses/` or `runtime.py`? Settled: in `runtime.py`, matching the `_RunState` precedent in `vidbyte/workflows/machine.py` while giving the state type an explicit name.
- [x] Does `_invoke_with_middleware`'s public signature change? Settled: no — it has external callers with the current signature.
- [x] Does `_process_tool_call`'s signature change? Settled: yes — zero external callers.
- [ ] N/A - no remaining open questions that block implementation.

---

## 13. Alternatives Considered

### Keep individual keyword arguments, just shorten names

- What: Rename `iteration_count` → `it`, `model_call_count` → `mc`, etc., to shrink each call site without introducing a new type.
- Why rejected: Saves characters, not lines or repetition. The actual complaint is that the same 8-11 values are threaded through by hand at 11+ call sites; shorter names don't remove that duplication and make the code harder to read for no structural benefit.

### `@property` on `AgentRuntime` itself

- What: Store `iteration_count`, `tokens_used`, etc. as `self.` attributes and expose them via properties, as the original question proposed.
- Why rejected: These values are per-call-site mutable local state, not instance state. `AgentRuntime` instances are reused, and `_arun_once` runs multiple, independent, potentially-nested attempts per instance (Reflexion, PDJ). Storing loop-attempt state on `self` would let concurrent/nested attempts corrupt each other's counters — a correctness regression, not a simplification.

### Pass a plain `dict` bag instead of a dataclass

- What: Collapse the arguments into `state: dict[str, Any]` instead of a typed class.
- Why rejected: Loses static typing and IDE support on every field, and loses the natural place to put the `tool_call_count` derived property. The repo's own `class-bound-helpers.md` and the `_RunState` precedent in `vidbyte/workflows/machine.py` both favor a named class over an untyped bag for exactly this kind of shared, structured, mutable state.

### Change `_invoke_with_middleware`'s public signature too

- What: Have `reflexion.py` and `multi_provider_agentic_grader.py` construct a `BaseAgentRuntimeLoopState` themselves and pass it in, for full consistency with `_process_tool_call`.
- Why rejected: `BaseAgentRuntimeLoopState` remains owned by `runtime.py`; exporting it for two external call sites — each of which builds a one-off synthetic attempt, not a real `_arun_once` loop — adds cross-module coupling and ceremony to two files this change doesn't need to touch, for a benefit (two fewer long call sites, both already using named keyword arguments today) that doesn't justify the widened blast radius.
