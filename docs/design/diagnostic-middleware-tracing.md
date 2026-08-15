# Design Doc: Diagnostic Middleware Tracing

**Status:** Approved for implementation
**Author:** OpenCode
**Created:** 2026-08-15
**Last Updated:** 2026-08-15

---

## 1. Overview

Vidbyte's semantic trace profiles already define `middleware.hook` as a diagnostic-only span, but `MiddlewarePipeline` retains only decisions that alter control flow (plus fail-open exceptions). A diagnostic research trace therefore cannot show that ordinary middleware hooks ran, how long they took, or what they returned.

This change records a compact invocation record for every middleware hook call, then has `AgentRuntime` emit one `middleware.hook` semantic span per record while the enclosing agent trace remains open. Existing `middleware.decision` spans continue to represent only control-flow changes.

This SDK change deliberately does not add a `tracer` argument to `YamlLoader.build_agent`. The public loader accepts declarative settings only; applications that need runtime-only objects construct `BaseAgent` from `AgentSettings.to_agent_kwargs(...)` after resolving registered components, per the configuration boundary documented in `field-guide/vidbyte-sdk/declarative-config-resolution.md`.

---

## 2. Goals And Non-Goals

### Goals

- Record every middleware hook invocation in configured middleware order.
- Capture middleware name, hook name, elapsed duration, returned action, reason, safe decision metadata, and exception type when a hook raises.
- Emit `middleware.hook` spans only for semantic diagnostic tracing.
- Preserve the existing `MiddlewarePipeline.events` and final result metadata contract for control-flow decisions.
- Keep `middleware.decision` spans for actions other than `continue`.
- Preserve fail-closed and fail-open middleware behavior.
- Add focused tests to existing SDK test modules without adding a feature-test directory.

### Non-Goals

- Do not change YAML configuration, registry resolution, or `YamlLoader.build_agent`.
- Do not add application persistence, LangSmith-specific behavior, or Vidbyte product trace schemas.
- Do not expose full middleware contexts, model responses, prompts, tool outputs, or exception messages in diagnostic hook spans.
- Do not alter middleware execution order, decision merging, retry handling, or result metadata shape.
- Do not add a new tracing backend or dependency.

---

## 3. Background And Constraints

- `MiddlewarePipeline._run()` invokes every configured middleware hook, but `events` currently contains only non-continue decisions and fail-open exceptions.
- `AgentRuntime._with_middleware_metadata()` already emits semantic `middleware.decision` spans before the surrounding `agent.run` trace closes.
- `TraceProfile.diagnostic()` permits diagnostic spans. `middleware.hook` must be classified as `TraceDetail.DIAGNOSTIC`; otherwise it would leak into the verbose profile.
- Trace values must use the runtime's existing `_safe_trace_mapping()` / `_safe_trace_value()` path so credential-like keys are removed and large strings are bounded before reaching a tracer.
- Pipeline timing uses the existing injected monotonic clock, which keeps duration deterministic in unit tests and non-negative at runtime.

---

## 4. Detailed Design

### 4.1 Per-Invocation Contract

**File:** `vidbyte/lib/dataclasses/middleware.py`

Add an immutable `MiddlewareHookInvocation` contract with:

```python
middleware_name: str
hook: MiddlewareHook
action: MiddlewareAction
duration_seconds: float
reason: str | None
metadata: Mapping[str, Any]
error_type: str | None
```

The contract is diagnostic-only runtime state. It does not replace `MiddlewareEvent`, which remains the consumer-facing event shape used in final agent metadata and audit middleware.

### 4.2 Pipeline Recording

**File:** `vidbyte/middleware/pipeline.py`

`MiddlewarePipeline` gains a private invocation list and a read-only `hook_invocations` property. `_run()` measures each middleware call with the configured clock, records its normalized decision whether it continues, sleeps, retries, aborts, denies, or raises, then preserves the existing decision-processing flow.

`_exception_decision()` keeps its existing control-flow behavior. Invocation records receive only the exception class name. The existing fail-open event remains intact so current result metadata stays compatible.

### 4.3 Semantic Span Emission

**Files:** `vidbyte/agents/runtime.py`, `vidbyte/trace/controller.py`

`AgentRuntime._record_middleware_spans()` first emits one `middleware.hook` span for each pipeline invocation. Span attributes include the invocation contract fields, with decision metadata passed through `_safe_trace_mapping()`.

The method then emits the existing `middleware.decision` spans for non-continue decisions from `MiddlewarePipeline.events`. This retains useful lower-volume decision tracing for the verbose profile while diagnostic mode supplies the complete hook timeline.

`TraceController._spec_from_name()` treats the exact name `middleware.hook` as diagnostic detail. All other `middleware.*` names retain their verbose classification.

### 4.4 Headers And Documentation

Update Context Protocol Headers in every modified source file to describe the invocation-record and diagnostic-span responsibilities. Update `vidbyte/middleware/README.md` to state that diagnostic semantic tracing records every hook invocation while normal result metadata continues to contain policy-relevant decisions only.

---

## 5. Compatibility And Failure Behavior

| Condition | Expected behavior |
| --- | --- |
| Middleware returns `continue` | One diagnostic `middleware.hook` record; no new final result metadata event; no `middleware.decision` span. |
| Middleware changes control flow | One diagnostic hook record plus the existing decision event and decision span. |
| Fail-open middleware raises | Invocation includes `error_type`; legacy fail-open event remains in final metadata; runtime continues. |
| Fail-closed middleware raises | Invocation includes `error_type`; existing abort behavior is unchanged. |
| `TraceProfile.default()` or `verbose()` | `middleware.hook` spans are suppressed. Existing decision spans retain their current profile behavior. |
| `TraceProfile.diagnostic()` | Every hook invocation becomes one `middleware.hook` span with safe attributes. |
| Raw tracer or no tracer | Existing raw tracing behavior remains unchanged; diagnostic hook emission follows the existing semantic-tracer gate. |

No persisted data, public YAML schema, or package dependency changes are required.

---

## 6. Test Plan

Extend existing tests rather than create a feature-test pack:

- `tests/test_context_compaction_middleware.py`: verify pipeline invocation recording for a normal continue decision, duration measured by the injected clock, and exception type capture.
- `tests/test_semantic_tracing.py`: verify `middleware.hook` is suppressed by verbose and enabled by diagnostic profiles.
- `tests/test_agent_middleware.py`: verify an end-to-end diagnostic runtime trace contains each invoked hook with the expected safe metadata and duration field, without expanding final result metadata with ordinary continue decisions.

Run the full local SDK gates from the worktree:

```powershell
$env:PYTHONPATH = (Get-Location).Path; python scripts/run_ci.py --stage source
Remove-Item Env:PYTHONPATH; python scripts/run_ci.py --stage package
```

---

## 7. File Change Manifest

| Action | File | Reason |
| --- | --- | --- |
| CREATE | `docs/design/diagnostic-middleware-tracing.md` | Design record and first branch commit. |
| MODIFY | `vidbyte/lib/dataclasses/middleware.py` | Add immutable per-hook diagnostic invocation contract. |
| MODIFY | `vidbyte/middleware/pipeline.py` | Measure and retain every hook invocation without changing policy events. |
| MODIFY | `vidbyte/agents/runtime.py` | Emit safe diagnostic hook spans before trace closure. |
| MODIFY | `vidbyte/trace/controller.py` | Classify `middleware.hook` as diagnostic detail. |
| MODIFY | `vidbyte/middleware/README.md` | Document diagnostic tracing and metadata compatibility. |
| MODIFY | `tests/test_context_compaction_middleware.py` | Cover pipeline-level invocation recording. |
| MODIFY | `tests/test_semantic_tracing.py` | Cover profile filtering. |
| MODIFY | `tests/test_agent_middleware.py` | Cover runtime integration and metadata compatibility. |

---

## 8. Rollout And Rollback

This is additive and disabled unless a diagnostic semantic trace profile is active. Vidbyte can adopt it after the SDK PR merges and the dependency pin is updated. Rollback is a normal revert: invocation records are ephemeral and no persistence contract changes.
