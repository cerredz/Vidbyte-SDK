# Design Doc: RunnerHandle Refactor

**Status:** Draft
**Author:** Claude
**Created:** 2026-06-02
**Last Updated:** 2026-06-02

---

## 1. Overview

This refactor consolidates four related runner parameters (`runner`, `provider`, `invoke_runner`, `runner_output_text`, `runner_output_metadata`) that are currently threaded through every `arun` signature in the agent runtime layer into a single `RunnerHandle` object. The change is purely internal — no public developer-facing API changes. Developers still call `BaseAgent.arun(message)` exactly as before.

---

## 2. Goals & Non-Goals

### Goals
- Replace four loosely-coupled parameters with one cohesive `RunnerHandle` object across all runtime `arun` and helper method signatures
- Make the `wrap_text` interception pattern in `MultiProviderAgenticGraderRuntimeAlgorithm` explicit and named rather than an anonymous closure side-effect
- Make the per-provider runner swap pattern in the multi-provider grader explicit via `handle.with_runner(runner, provider)`
- Eliminate duplicated parameter threading in `_arun_once`, `_invoke_with_middleware`, `_run_trial`, `_reflect_after_failure`, `_run_provider_trial`, `_run_grader`, and `BaseActorRuntime`

### Non-Goals
- No changes to the public `BaseAgent` constructor or `arun`/`generate_reply` signatures
- No changes to `AgentResult`, `BaseAgentContext`, or any dataclass shapes
- No changes to `provider: str` in internal tool-focused helpers (`_process_tool_call`, `execute_tool_call`) — these don't receive runner callbacks and keeping `provider` as a plain string there avoids unnecessary coupling
- No behavioral changes of any kind — this is a structural refactor only
- No new features

---

## 3. Background & Context

The current `arun` protocol passes runner concerns as four separate arguments:

```python
async def arun(
    self,
    message: str,
    *,
    runner: object,                                       # which model object to call
    provider: str,                                        # label for tracing/tool schemas
    invoke_runner: Callable[..., Any],                    # how to call any runner object
    runner_output_text: Callable[[object], str],          # how to read text from response
    runner_output_metadata: Callable[[object], Mapping],  # how to read metadata from response
    ...
) -> AgentResult:
```

These four always travel together and are always sourced from the same three static methods on `BaseAgent`. The only exception is the multi-provider grader, which:
1. Creates a new `runner` per provider trial while reusing `invoke_runner`
2. Wraps `runner_output_text` with an anonymous closure to intercept outputs for grading

Both of these patterns become cleaner with a `RunnerHandle` that has named methods (`with_runner`, `wrap_text`).

The four-parameter form accumulated incrementally as the runtime gained features; it was never designed as a unified interface. The original intent — allowing runtimes to be stateless and sharable — doesn't hold in practice because runtimes already hold agent-specific state (`self.middleware`, `self.algorithm`, etc.).

---

## 4. Requirements

### Functional Requirements
1. `RunnerHandle` must encapsulate `runner`, `provider`, and the three callback functions
2. `RunnerHandle.invoke(message, **options)` must call the underlying runner via duck-typed dispatch
3. `RunnerHandle.extract_text(result)` must return the text content from any runner response shape
4. `RunnerHandle.extract_metadata(result)` must return the metadata mapping from any runner response shape
5. `RunnerHandle.with_runner(runner, provider)` must return a new handle reusing the invocation and extraction logic with a different runner and provider label
6. `RunnerHandle.wrap_text(interceptor)` must return a new handle where `extract_text` calls `interceptor(text)` as a side-effect before returning
7. All `arun` method signatures across all six affected runtime components must be updated to accept `handle: RunnerHandle` instead of the four separate parameters
8. `BaseAgent._run_direct` must construct the `RunnerHandle` from `runner`, `provider`, and the three static methods before dispatching
9. `BaseActorRuntime` must store `self._handle: RunnerHandle | None` instead of four separate instance variables

### Non-Functional Requirements
- Zero behavioral change — all existing tests must pass without modification to test logic
- No allocation overhead worth measuring — one extra object per agent run is negligible

---

## 5. High-Level Design

`RunnerHandle` is a plain Python class created once per agent run inside `BaseAgent._run_direct` and passed as a single `handle` argument to all runtimes. Runtimes call `handle.invoke(...)`, `handle.extract_text(...)`, and `handle.extract_metadata(...)` instead of the separate callbacks. Algorithms that need to swap the runner (multi-provider grader) or intercept text output (grader trial capture) use `handle.with_runner(...)` and `handle.wrap_text(...)`.

```
BaseAgent._run_direct()
  │ builds RunnerHandle(runner, provider, _invoke_fn, _extract_text_fn, _extract_metadata_fn)
  ↓
AgentRuntime.arun(message, handle=handle, context=..., ...)
  │ or AgentRuntimeContextAlgorithms → ReflexionRuntimeAlgorithm
  │ or AgentRuntimeContextAlgorithms → MultiProviderAgenticGraderRuntimeAlgorithm
  ↓
AgentRuntime._arun_once(message, handle=handle, ...)
  provider = handle.provider
  │
  ├── handle.invoke(message, **call_options)     # was: invoke_runner(runner, message, ...)
  ├── handle.extract_text(raw_result)            # was: runner_output_text(raw_result)
  └── handle.extract_metadata(raw_result)        # was: runner_output_metadata(raw_result)
```

For the multi-provider grader:
```
trial_handle = handle.with_runner(p_runner, provider_name).wrap_text(captured_output.append)
# replaces: creating p_runner + wrapped_output_text closure
```

---

## 6. Detailed Design

### 6.1 RunnerHandle

**File:** `vidbyte/lib/dataclasses/runner.py`
**Type:** New file

#### What it does
Bundles the runner object, provider label, and the three invocation/extraction callables into one object. Provides named methods for the three operations plus two factory methods for creating modified variants.

#### Interface / API
```python
class RunnerHandle:
    def __init__(self, *, runner: object, provider: str, invoke: Callable[..., Any], extract_text: Callable[[object], str], extract_metadata: Callable[[object], Mapping[str, Any]]) -> None: ...
    async def invoke(self, message: str, **options: Any) -> object: ...
    def extract_text(self, result: object) -> str: ...
    def extract_metadata(self, result: object) -> Mapping[str, Any]: ...
    def with_runner(self, runner: object, provider: str) -> RunnerHandle: ...
    def wrap_text(self, interceptor: Callable[[str], None]) -> RunnerHandle: ...
```

#### Logic / Algorithm

`invoke(message, **options)`:
1. Calls `self._invoke(self.runner, message, **options)`
2. Returns the raw result object

`extract_text(result)`:
1. Calls `self._extract_text(result)`
2. Returns the string

`extract_metadata(result)`:
1. Calls `self._extract_metadata(result)`
2. Returns the mapping

`with_runner(runner, provider)`:
1. Returns `RunnerHandle(runner=runner, provider=provider, invoke=self._invoke, extract_text=self._extract_text, extract_metadata=self._extract_metadata)`

`wrap_text(interceptor)`:
1. Captures `self._extract_text` as `original`
2. Creates `wrapped(r) = interceptor(original(r)) or original(r)` — calls interceptor as side effect, returns text unchanged
3. Returns `RunnerHandle(runner=self.runner, provider=self.provider, invoke=self._invoke, extract_text=wrapped, extract_metadata=self._extract_metadata)`

#### Edge Cases & Error Handling
- `wrap_text` interceptors must not raise; if they do the exception propagates to the caller (no swallowing)
- `with_runner` does not validate the new runner — same as current behavior where any duck-typed object is accepted

---

### 6.2 BaseAgent

**File:** `vidbyte/agents/base.py`
**Type:** Modified

#### What changes
`_run_direct` and `_run_with_tools` build a `RunnerHandle` before dispatching to the runtime. The four-parameter call site is replaced by `handle=handle`.

```python
# Before
result = await self._runtime().arun(
    message,
    runner=runner,
    context=context,
    provider=provider,
    invoke_runner=self._invoke_runner,
    runner_output_text=self._runner_output_text,
    runner_output_metadata=self._runner_output_metadata,
    metadata=runtime_metadata,
    options=options,
    trace_context=trace_context,
)

# After
handle = RunnerHandle(
    runner=runner,
    provider=provider,
    invoke=self._invoke_runner,
    extract_text=self._runner_output_text,
    extract_metadata=self._runner_output_metadata,
)
result = await self._runtime().arun(
    message,
    handle=handle,
    context=context,
    metadata=runtime_metadata,
    options=options,
    trace_context=trace_context,
)
```

The static methods `_invoke_runner`, `_runner_output_text`, `_runner_output_metadata` are unchanged — they remain on `BaseAgent` and are passed into the `RunnerHandle` constructor.

---

### 6.3 AgentRuntime

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What changes
`arun`, `_arun_once`, and `_invoke_with_middleware` replace the four separate parameters with `handle: RunnerHandle`. Provider is extracted at the top of each method for use in tool schemas, middleware contexts, and `ToolsFormatter`.

```python
# _arun_once — top of method body
provider = handle.provider
tool_schemas = self._resolve_tool_schemas(provider)
...
# usage sites
raw_result = await handle.invoke(message, **dict(call_options))
runner_metadata = dict(handle.extract_metadata(raw_result))
messages.append(self._assistant_message(handle.extract_text(raw_result)))
```

`_process_tool_call`, `execute_tool_call`, and all other internal methods that only use `provider: str` are unchanged — they receive `provider` extracted from the handle, not the handle itself.

---

### 6.4 AgentRuntimeContextAlgorithms

**File:** `vidbyte/agents/context_algorithms.py`
**Type:** Modified

Replace four params with `handle: RunnerHandle` in `arun`. Pass `handle` through to the algorithm.

---

### 6.5 ReflexionRuntimeAlgorithm

**File:** `vidbyte/agents/algorithms/reflexion.py`
**Type:** Modified

`arun`, `_run_trial`, and `_reflect_after_failure` replace the four params with `handle: RunnerHandle`. `_run_trial` passes `handle` to `_arun_once`. `_reflect_after_failure` passes `handle` to `_invoke_with_middleware`.

---

### 6.6 MultiProviderAgenticGraderRuntimeAlgorithm

**File:** `vidbyte/agents/algorithms/multi_provider_agentic_grader.py`
**Type:** Modified

The anonymous `wrapped_output_text` closure is replaced by `handle.with_runner(...).wrap_text(...)`:

```python
# Before
p_runner = ModalityDetector.create_runner(...)
captured_output: list[str] = []
def wrapped_output_text(r: object) -> str:
    txt = runner_output_text(r)
    captured_output.append(txt)
    return txt
res = await self.runtime._arun_once(
    message, runner=p_runner, invoke_runner=invoke_runner,
    runner_output_text=wrapped_output_text, ...
)

# After
p_runner = ModalityDetector.create_runner(...)
captured_output: list[str] = []
trial_handle = handle.with_runner(p_runner, provider_name).wrap_text(captured_output.append)
res = await self.runtime._arun_once(message, handle=trial_handle, ...)
```

`_run_grader` similarly builds its own handle via `handle.with_runner(grader_runner, grader_provider)`.

All helper method signatures (`_run_provider_trials`, `_run_provider_trial`, `_run_grader`, `_select_winner`) drop the three separate callable params and receive `handle: RunnerHandle`.

---

### 6.7 SearchTreeRuntimeComponent

**File:** `vidbyte/agents/runtimes/search.py`
**Type:** Modified

`arun` signature updated; the four params become `handle: RunnerHandle`. The handle is not used in the current stub implementation but the signature must match the protocol.

---

### 6.8 BaseActorRuntime

**File:** `vidbyte/agents/runtimes/actor/broker.py`
**Type:** Modified

The four instance variables stored at `arun` time:
```python
self._runner = runner
self._invoke_runner = invoke_runner
self._runner_output_text = runner_output_text
self._runner_output_metadata = runner_output_metadata
self._provider = provider
```
become one:
```python
self._handle = handle
```

All sites that access `self._runner`, `self._invoke_runner`, `self._runner_output_text`, `self._provider` are updated to `self._handle.runner`, `self._handle.invoke(...)`, `self._handle.extract_text(...)`, `self._handle.provider`.

---

### 6.9 vidbyte/lib/dataclasses/__init__.py

**File:** `vidbyte/lib/dataclasses/__init__.py`
**Type:** Modified

Add `RunnerHandle` to exports.

---

## 7. Data Model Changes

N/A — no schema, persistence, or database changes. `RunnerHandle` is a transient per-run object.

---

## 8. API Changes

N/A — no HTTP endpoints or external API surfaces are affected.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/lib/dataclasses/runner.py` | New `RunnerHandle` class |
| MODIFY | `vidbyte/lib/dataclasses/__init__.py` | Export `RunnerHandle` |
| MODIFY | `vidbyte/agents/base.py` | Build `RunnerHandle` in `_run_direct` and `_run_with_tools` |
| MODIFY | `vidbyte/agents/runtime.py` | Replace 4 params with `handle` in `arun`, `_arun_once`, `_invoke_with_middleware` |
| MODIFY | `vidbyte/agents/context_algorithms.py` | Replace 4 params with `handle` in `arun` |
| MODIFY | `vidbyte/agents/algorithms/reflexion.py` | Replace 4 params with `handle` in `arun`, `_run_trial`, `_reflect_after_failure` |
| MODIFY | `vidbyte/agents/algorithms/multi_provider_agentic_grader.py` | Replace 4 params with `handle` in all methods; replace closure with `wrap_text` |
| MODIFY | `vidbyte/agents/runtimes/search.py` | Replace 4 params with `handle` in `arun` |
| MODIFY | `vidbyte/agents/runtimes/actor/broker.py` | Replace 5 instance vars with `self._handle`; update all access sites |
| MODIFY | `tests/test_agent_runtime.py` | Update `arun` call sites that pass the 4 params directly |
| MODIFY | `tests/test_reflexion_algorithm.py` | Same |
| MODIFY | `tests/test_multi_provider_agentic_grader.py` | Same |

---

## 10. Testing Plan

### Unit Tests

**`RunnerHandle` core behavior:**
- `it should invoke the runner via the invoke callable` — [Edge Case: confirms delegation works]
- `it should extract text via the extract_text callable` — [Hidden Assumption: callable is always called, never bypassed]
- `it should extract metadata via the extract_metadata callable` — [Hidden Assumption: same]
- `it should return a new handle from with_runner with the new runner and provider` — [Silent Failure: ensure original handle is not mutated]
- `it should return a new handle from wrap_text with the original handle unchanged` — [Silent Failure: immutability]
- `it should call the wrap_text interceptor and still return the original text unchanged` — [Silent Failure: interceptor side-effect must not alter return value]
- `it should chain wrap_text twice, calling both interceptors` — [Edge Case: multiple wraps]
- `it should propagate exceptions from the interceptor without swallowing` — [Hidden Failure: silent swallowing]
- `it should propagate exceptions from extract_text` — [Hidden Failure]
- `it should work with a runner that has no arun or run but is callable` — [Hidden Assumption: duck-typed runner dispatch]

**`AgentRuntime` integration:**
- `it should run the tool loop end-to-end when called with a RunnerHandle` — [Hidden Assumption: handle plumbed correctly]
- `it should pass handle.provider to tool schema resolution` — [Silent Failure: schemas resolved for wrong provider]
- `it should pass handle.provider to ToolsFormatter.parse_tool_calls` — [Silent Failure: wrong parse format]
- `it should use handle.extract_metadata to accumulate token usage` — [Silent Failure: tokens not counted]

**`MultiProviderAgenticGraderRuntimeAlgorithm`:**
- `it should capture trial output via wrap_text interceptor` — [Hidden Failure: output capture regression]
- `it should use with_runner to swap runners per provider trial` — [Hidden Assumption: each trial uses its own runner]
- `it should use with_runner for the grader call` — [Silent Failure: grader calls wrong provider]

**`ReflexionRuntimeAlgorithm`:**
- `it should pass the handle through to _reflect_after_failure unchanged` — [Hidden Assumption: reflection uses same runner as trial]

### Integration Tests

- Full `BaseAgent.arun` call through linear runtime with a fake runner — verifies the handle is built and passed correctly end-to-end
- Full `BaseAgent.arun` call through Reflexion algorithm — verifies handle threading across trial boundaries
- `MultiProviderAgenticGraderRuntimeAlgorithm` full run with two fake providers — verifies `with_runner` + `wrap_text` produce correct candidates

The key hidden assumption the integration tests surface that unit tests cannot: the `RunnerHandle` built in `_run_direct` has the right `runner` reference by the time a middleware retry occurs (because `_invoke_with_middleware` loops and re-calls `handle.invoke(...)` — the handle must not be stale across retry iterations).

### Manual / QA Test Cases

1. Given a `BaseAgent` with a real `TextModelRunner`, when `arun("hello")` is called, then the response is returned and `result.metadata["stop_reason"]` is populated — [Hidden Assumption: metadata extraction path works end-to-end]
2. Given a `BaseAgent` configured with Reflexion algorithm, when `arun` is called, then `result.metadata["reflexion"]["trial_count"]` is present — [Silent Failure: reflexion metadata dropped in handle threading]
3. Given a `BaseAgent` configured with `MultiProviderAgenticGrader`, when `arun` is called with two providers configured, then `result.strategy_name == "multi_provider_agentic_grader"` — [Hidden Failure: handle swap regression]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `collections.abc` | 3.11+ | `Callable`, `Mapping` type hints | None |

No new external dependencies.

---

## 12. Rollout & Deployment

- No feature flags — this is a pure internal refactor with no user-visible surface
- Not a breaking change for any public API — `BaseAgent.arun` signature unchanged
- Single deployment: this is a library, not a service
- Rollback: revert the branch; no migration needed

---

## 13. Open Questions

- [ ] Should `RunnerHandle` live in `vidbyte/lib/dataclasses/runner.py` or closer to the agent layer at `vidbyte/agents/runner_handle.py`? The `lib/dataclasses/` location follows existing convention but `RunnerHandle` is more behavioral than the pure data classes there.
- [ ] Should `with_runner` and `wrap_text` be named methods or classmethods / factory functions? Named instance methods are proposed here as they read naturally at the call site.

---

## 14. Alternatives Considered

### Alternative 1: Protocol instead of concrete class
- What: Define `RunnerHandleProtocol` and let runtimes accept any object matching the protocol
- Why rejected: `RunnerHandle` is always constructed from `BaseAgent`'s three static methods — there is no meaningful variation in implementation. A Protocol adds complexity with no benefit here. Protocols are appropriate for the external `ToolLike` interface; this is internal.

### Alternative 2: Attach methods directly to the runner object
- What: Require runners to implement `extract_text()` and `extract_metadata()` as methods
- Why rejected: This would require every external or third-party runner object to conform to a new interface. The current duck-typed extraction logic in `BaseAgent._runner_output_text` is specifically designed to handle runners that don't know about this SDK.

### Alternative 3: Move all four callables into `AgentRuntime.__init__`
- What: Pass them at construction time rather than per-call
- Why rejected: The runner is selected per-call based on modality. A modality-specific runner is resolved in `generate_reply()`, not at construction time. Putting it in the constructor would require constructing a new runtime per run or mutating shared state.

### Alternative 4: Keep `provider` as a separate parameter alongside `handle`
- What: Pass `handle: RunnerHandle` + `provider: str` separately
- Why rejected: Provider is inherently part of the runner bundle — it labels which provider the runner belongs to. Keeping them separate preserves the same smell in a different form.
