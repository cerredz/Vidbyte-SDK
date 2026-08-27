# Design Doc: Verifier Runtime Algorithms

**Status:** Draft
**Author:** Codex
**Created:** 2026-08-27
**Last Updated:** 2026-08-27

---

## 1. Overview

This change adds explicit algorithm modes to the verifier runtime so a caller
can choose how verification is interleaved with an agent run without adding
mode-specific logic to `AgentRuntime`. Four concrete classes will be exposed:
post-run verification, finalization gating, periodic verification, and
verifier-as-tool. A small mode interface owns the algorithm behavior; the
linear runtime exposes only generic run, iteration, finalization, and tool
registration seams. Existing configuration remains default-off and continues
to use finalization gating when no mode is selected.

---

## 2. Goals & Non-Goals

### Goals

- Add one concrete class for each supported verifier execution algorithm.
- Let `VerifierRuntimeSettings` select a mode through one central `mode` field.
- Keep algorithm implementations outside `vidbyte/agents/runtime.py`.
- Add only generic lifecycle delegation to the linear runtime.
- Support full-history, compacted-history, and fresh-context retry behavior as
  settings of post-run verification rather than separate algorithms.
- Support periodic verification with a configurable iteration interval.
- Expose a verifier tool mode with a configurable tool name, call ceiling, and
  optional verification requirement before finalization.
- Preserve the current finalization-gated behavior as the default mode.

### Non-Goals

- No candidate-selection or parallel-branch algorithm in this change.
- No new verifier kinds or concrete verifier implementations.
- No replacement of the existing verifier collection, verdict policy, gate,
  repair, budget, or ledger pillars.
- No new persistent data model or session storage.
- No new test files, per the requested `design-doc-no-tests` workflow; existing
  source, package, lint, and CI checks remain mandatory.

---

## 3. Background & Context

The current verifier runtime in PR #349 is wired directly to the two linear
runtime finalization boundaries. `AgentVerifierRuntime` already owns the
shared verification pillars and the gate now owns target resolution,
collection execution, aggregation, ledger recording, and gate decisions. That
implementation is correct for one algorithm, but its trigger enum and repair
types imply additional behaviors that are not yet represented as selectable
algorithm classes.

The SDK already keeps context-window algorithms outside the main runtime and
dispatches them through lifecycle adapters in `vidbyte/agents/context_algorithms.py`.
The verifier modes will follow that repository pattern. The runtime will know
only a small mode protocol, while each mode owns its own control-flow policy.

---

## 4. Requirements

### Functional Requirements

1. `VerifierRuntimeSettingsParams.mode` accepts a validated verifier mode and
   defaults to finalization gating when omitted.
2. `PostRunVerificationMode` runs a complete agent attempt, verifies its
   result, and retries failed attempts using the configured context mode until
   the shared verifier budget is exhausted.
3. `FinalizationGateMode` verifies only when the agent attempts to finalize and
   preserves the current reject-and-continue behavior.
4. `PeriodicVerificationMode` verifies after every configured number of
   completed non-final iterations and injects the shared repair feedback when
   a checkpoint fails; finalization remains a final verification checkpoint.
5. `VerifierAsToolMode` registers a model-callable verifier tool, reports the
   structured verifier outcome as a normal tool result, enforces an optional
   maximum number of calls, and can require a successful verification before
   finalization.
6. `AgentRuntime` delegates to the selected mode at the complete-run,
   completed-iteration, finalization, and tool-registration seams without
   importing or branching on concrete mode classes.
7. An unconfigured verifier runtime remains a complete no-op, and configured
   verifier runtimes without an explicit mode retain finalization-gate
   semantics.
8. All new public configuration dataclasses validate their own values in
   `__post_init__` and raise `ConfigurationError` on invalid input.

### Non-Functional Requirements

- Mode classes must be independently readable and testable without copying
  the agent loop.
- The mode interface must not add a second verifier implementation or bypass
  the existing ledger and gate.
- Retry context must remain bounded when compacted mode is selected.
- Tool mode must use the existing `BaseTool`/`ToolSpec`/`ToolResult` contract.
- Existing source and package CI gates must pass with the complete verifier
  mode surface installed.

---

## 5. High-Level Design

`VerifierRuntimeSettingsParams` gains an optional `mode` object. The settings
wrapper resolves `None` to `FinalizationGateMode`, so existing callers do not
need to change. `AgentVerifierRuntime` binds the selected mode to the shared
verifier kernel and exposes four lifecycle methods: `run`, `after_iteration`,
`on_finalization_attempt`, and `mode_tools`.

The mode classes live under a new `verifier/algorithms/` package. Post-run and
periodic modes call the existing verifier kernel at their own lifecycle point.
Finalization mode delegates the current finalization check. Tool mode returns
one `BaseTool` that calls the same kernel and renders its outcome through the
normal provider tool-result path.

The linear runtime adds one generic delegation around the complete run, one
generic after-iteration call, and keeps its existing finalization call routed
through `AgentVerifierRuntime`. It does not contain a switch over mode names.

```text
AgentLoopSettings
        |
VerifierRuntimeSettings(mode=ConcreteVerifierRuntimeMode(...))
        |
AgentVerifierRuntime
        |-- mode.run(...)                 -> PostRun outer wrapper
        |-- mode.after_iteration(...)    -> Periodic checkpoints
        |-- mode.on_finalization(...)    -> Finalization or required final check
        |-- mode_tools()                 -> Verifier-as-tool registration
        |
shared target -> collection -> verdict policy -> ledger -> gate -> repair
```

---

## 6. Detailed Design

### 6.1 Mode data contracts

**File(s):** `vidbyte/lib/dataclasses/verifier.py`
**Type:** Modified

#### What it does

Adds the public mode enum, retry context enum, mode-specific parameter
dataclasses, and the typed run request passed to mode wrappers.

#### Interface / API

```python
class VerifierRuntimeModeKind(str, Enum): ...
class VerifierRetryContextMode(str, Enum): ...
class PostRunVerificationModeParams: ...
class PeriodicVerificationModeParams: ...
class VerifierAsToolModeParams: ...
class VerifierRunRequest: ...
```

#### Logic / Algorithm

1. Validate positive attempt and interval values.
2. Validate retry context and tool mode enum values.
3. Add `mode` as an optional final field on `VerifierRuntimeSettingsParams`.
4. Validate a provided mode against the mode base class without introducing a
   runtime import cycle.

#### Edge Cases & Error Handling

- `mode=None` means finalization gating.
- `max_calls=None` means unlimited verifier-tool calls subject to the general
  agent loop budget.
- A non-positive interval, attempt count, or call ceiling raises
  `ConfigurationError` at construction.

### 6.2 `VerifierRuntimeMode`

**File(s):** `vidbyte/agents/runtimes/verifier/algorithms/base.py`
**Type:** New file

#### What it does

Defines the small lifecycle contract implemented by every verifier algorithm.
The base implementation is a no-op wrapper, no-op iteration hook, permissive
finalization hook, and empty tool contribution.

#### Interface / API

```python
class VerifierRuntimeMode:
    async def run(self, runtime, request, run_once): ...
    async def after_iteration(self, runtime, context): ...
    async def on_finalization(self, runtime, context): ...
    def tools(self, runtime): ...
```

#### Logic / Algorithm

1. `run` invokes the supplied complete-attempt callback once.
2. `after_iteration` returns no outcome.
3. `on_finalization` returns an allow outcome.
4. `tools` returns an empty tuple.

#### Edge Cases & Error Handling

The base class is safe for a mode that only needs one lifecycle hook. It does
not execute verifiers itself; concrete modes call the shared runtime kernel.

### 6.3 `PostRunVerificationMode`

**File(s):** `vidbyte/agents/runtimes/verifier/algorithms/post_run.py`
**Type:** New file

#### What it does

Runs complete agent attempts and verifies each completed result. Failed results
are converted into the next attempt's initial message according to the selected
retry context mode.

#### Interface / API

```python
class PostRunVerificationMode(VerifierRuntimeMode):
    def __init__(self, params: PostRunVerificationModeParams): ...
```

#### Logic / Algorithm

1. Invoke the normal runtime attempt callback.
2. Build a resolution context from the result and call the shared verifier
   kernel.
3. Return on an allowed verdict.
4. Return the failed result when the shared budget terminates the attempt.
5. Otherwise create the next run request with full, compacted, or fresh retry
   context and repeat.

#### Edge Cases & Error Handling

- The normal inner finalization hook is permissive for this mode so a result
  can return to the outer post-run verifier.
- Compacted retry context includes only a bounded result summary and feedback.
- Fresh retry context includes the original request and current feedback, not
  the previous transcript.

### 6.4 `FinalizationGateMode`

**File(s):** `vidbyte/agents/runtimes/verifier/algorithms/finalization_gate.py`
**Type:** New file

#### What it does

Preserves PR #349's current algorithm: verification runs when the agent tries
to finalize, and a rejected result is repaired in the same loop.

#### Interface / API

```python
class FinalizationGateMode(VerifierRuntimeMode): ...
```

#### Logic / Algorithm

`on_finalization` delegates to `AgentVerifierRuntime.evaluate_checkpoint`,
which uses the existing gate, ledger, feedback, and repair strategy.

#### Edge Cases & Error Handling

The mode performs no verification after ordinary iterations and contributes no
tool. It is the default when no explicit mode is provided.

### 6.5 `PeriodicVerificationMode`

**File(s):** `vidbyte/agents/runtimes/verifier/algorithms/periodic.py`
**Type:** New file

#### What it does

Verifies completed non-final iterations at a configured cadence and delegates
finalization to the same shared verifier kernel.

#### Interface / API

```python
class PeriodicVerificationMode(VerifierRuntimeMode):
    def __init__(self, params: PeriodicVerificationModeParams): ...
```

#### Logic / Algorithm

1. Ignore iterations before the configured interval.
2. At each interval, call the shared verifier kernel with the current snapshot.
3. Return the outcome so the runtime can inject feedback or stop the run.
4. Always verify the finalization attempt, even after a passing checkpoint.

#### Edge Cases & Error Handling

- A passing checkpoint does not finalize the agent automatically; later work
  may change the target.
- A failed checkpoint uses the configured repair strategy and remains bounded
  by the shared verifier budget.

### 6.6 `VerifierAsToolMode`

**File(s):** `vidbyte/agents/runtimes/verifier/algorithms/as_tool.py`
**Type:** New file

#### What it does

Contributes a normal `BaseTool` that lets the model request verification. The
tool invokes the shared verifier kernel and returns the decision and feedback
as a structured tool result.

#### Interface / API

```python
class VerifierAsToolMode(VerifierRuntimeMode):
    def __init__(self, params: VerifierAsToolModeParams): ...
```

#### Logic / Algorithm

1. Return a bound verifier tool from `tools`.
2. Count calls through the owning `AgentVerifierRuntime`.
3. Reject calls after `max_calls` when configured.
4. On each accepted call, run target resolution, collection, aggregation,
   ledger recording, and gate decision through the shared kernel.
5. If `required_before_finalization=True`, require a successful tool verdict;
   otherwise perform a final verification check before allowing completion.

#### Edge Cases & Error Handling

- Tool validation failures return normal `ToolResult.failure` values.
- The tool does not bypass permissions or middleware because it enters the
  existing tool catalog and executor.
- A required final verification cannot be satisfied by an exhausted or failed
  tool call.

### 6.7 `AgentVerifierRuntime` mode delegation

**File(s):** `vidbyte/agents/runtimes/verifier/runtime.py`,
`vidbyte/agents/runtimes/verifier/settings.py`
**Type:** Modified

#### What it does

Resolves the selected mode, exposes mode lifecycle methods, and keeps the
existing shared verifier kernel in one place.

#### Interface / API

```python
async def run(self, request, run_once): ...
async def after_iteration(self, context): ...
async def on_finalization_attempt(self, context): ...
def mode_tools(self): ...
```

#### Logic / Algorithm

1. Resolve `params.mode` or instantiate `FinalizationGateMode`.
2. Delegate complete-run, iteration, finalization, and tool requests to it.
3. Keep `evaluate_checkpoint` as the common target/collection/verdict/ledger/
   gate operation used by all modes.

#### Edge Cases & Error Handling

An invalid mode is rejected during settings construction. A mode that does not
override a hook receives the base no-op behavior.

### 6.8 Linear runtime integration

**File(s):** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does

Adds generic mode lifecycle calls without importing concrete algorithm classes.

#### Interface / API

The existing `arun`, finalization boundaries, and iteration loop gain calls to
the selected `AgentVerifierRuntime` mode interface only.

#### Logic / Algorithm

1. Wrap the existing context-algorithm-or-`_arun_once` dispatch with
   `AgentVerifierRuntime.run` when configured.
2. Invoke `after_iteration` after a completed non-final tool iteration.
3. Continue to route both existing finalization boundaries through
   `on_finalization_attempt`.
4. Extend the tool catalog with `mode_tools()` during construction.
5. Apply returned repair feedback or stop outcomes through existing message
   and result helpers.

#### Edge Cases & Error Handling

- With no verifier runtime, the current path is unchanged.
- Periodic mode does not run twice for an `isDone` finalization iteration.
- Tool mode uses the normal catalog duplicate-name error if its configured
  tool name conflicts with a user tool.

---

## 7. Data Model Changes

N/A - mode configuration is in-memory and adds no persisted schema. The
existing verifier ledger remains run-local.

---

## 8. API Changes

N/A - this is an SDK constructor/configuration change, not a network endpoint.
The public API adds mode classes and their parameter dataclasses to the
verifier-runtime exports.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/verifier-runtime-algorithms.md` | Record the mode design before implementation |
| CREATE | `vidbyte/agents/runtimes/verifier/algorithms/__init__.py` | Export the four algorithm classes |
| CREATE | `vidbyte/agents/runtimes/verifier/algorithms/base.py` | Shared mode lifecycle contract |
| CREATE | `vidbyte/agents/runtimes/verifier/algorithms/post_run.py` | Post-run verification mode |
| CREATE | `vidbyte/agents/runtimes/verifier/algorithms/finalization_gate.py` | Finalization-gate mode |
| CREATE | `vidbyte/agents/runtimes/verifier/algorithms/periodic.py` | Periodic verification mode |
| CREATE | `vidbyte/agents/runtimes/verifier/algorithms/as_tool.py` | Verifier-as-tool mode and tool |
| MODIFY | `vidbyte/lib/dataclasses/verifier.py` | Mode enums, params, run request, settings field |
| MODIFY | `vidbyte/agents/runtimes/verifier/settings.py` | Resolve and expose the selected mode |
| MODIFY | `vidbyte/agents/runtimes/verifier/runtime.py` | Delegate lifecycle calls and expose shared checkpoint evaluation |
| MODIFY | `vidbyte/agents/runtimes/verifier/__init__.py` | Re-export mode classes and configuration |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export public mode classes |
| MODIFY | `vidbyte/agents/runtime.py` | Add generic mode lifecycle seams |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `dataclasses` | Runtime | Typed mode requests and validated params | None |
| Existing Vidbyte `BaseTool` contract | Repository | Model-callable verifier tool | Low; uses existing executor |

No new third-party dependencies or external services.

---

## 11. Rollout & Deployment

- The feature is default-off when `verifier_runtime` is unset.
- Existing configured verifier runtimes default to `FinalizationGateMode`.
- This is additive SDK behavior and requires no migration.
- Rollback is a revert of the mode commits; no persisted data is changed.
- The branch will update PR #349 rather than opening a replacement PR.

---

## 12. Open Questions

- [ ] Should periodic mode eventually support a passing checkpoint that
      immediately finalizes, or should finalization always require its own
      check? This implementation chooses the latter.
- [ ] Should candidate selection become a fifth mode after session/workspace
      branching is formalized? It is explicitly excluded here.

---

## 13. Alternatives Considered

### Alternative 1: Put all algorithms in `AgentRuntime`

- What: Add a mode switch and implement each loop shape directly in the
  2,000-line runtime.
- Why rejected: It would make the main loop own unrelated policies and make
  every future mode harder to read and verify.

### Alternative 2: One generic mode with many optional callbacks

- What: Keep one configurable class with nullable callbacks for run, iteration,
  finalization, and tool behavior.
- Why rejected: It hides the four public algorithms behind a bag of optional
  fields and makes invalid combinations easy to construct.

### Alternative 3: Keep only finalization gating

- What: Treat post-run, periodic, and tool verification as caller-specific
  wrappers outside the SDK.
- Why rejected: Those are materially different verifier/runtime algorithms and
  are exactly the user-facing choice this change is intended to formalize.

### Alternative 4: Add candidate selection now

- What: Add parallel candidate generation and verification in the same change.
- Why rejected: It requires a separate branch/session lifecycle and is not
  needed to establish the four current algorithm modes.
