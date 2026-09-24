# Design Doc: Jev Done Criteria

**Status:** Approved; implementation clarification  
**Author:** OpenCode  
**Created:** 2026-09-23  
**Last Updated:** 2026-09-24

---

## 1. Overview

Add a Jev-owned done-criteria subsystem so a `JevAgent` can reject premature completion attempts deterministically. The first criterion is a minimum run duration configured in seconds, minutes, hours, or days. If the model attempts completion before the threshold, Jev appends a continuation prompt and keeps the same runtime loop running; elapsed time only makes completion eligible and never establishes task completion. Results from configured runs include the computed `minimum_duration_met` Boolean.

---

## 2. Goals & Non-Goals

### Goals

- Add `vidbyte/agents/jev/done_criteria/` with a composite criteria evaluator, criterion contract, and concrete criterion subclasses.
- Implement `JevPreset.MinimumTime(...)` supporting one positive `seconds`, `minutes`, `hours`, or `days` argument.
- Accept criteria through `JevAgentSettings.done_criteria`; preserve the existing `JevAgent(settings)` construction surface.
- Use the per-run monotonic clock for the duration check.
- Reject early normal final responses and internal `isDone` completion attempts, append a continuation prompt, and continue the same loop.
- Record `minimum_duration_met` in result metadata whenever a minimum-time criterion is configured, including non-success budget results.
- Add focused tests and an executable feature verification script.

### Non-Goals

- Do not finish automatically when the duration elapses.
- Do not sleep or poll until the threshold.
- Do not change completion behavior when criteria are not configured.
- Do not add declarative configuration support or criteria beyond minimum time.
- Do not change generic `AgentLoopSettings` output-contract behavior or replace its existing `MinElapsedSeconds` contract.

---

## 3. Background & Context

`JevAgent` currently accepts one `JevAgentSettings` object and passes it to a registered `JevRuntime` subclass through `_runtime_extension_kwargs()`. `JevRuntime` currently delegates to the shared `AgentRuntime` loop. The shared runtime finalizes in two ordinary model-originated cases: a text response without tool calls and the internal `isDone` tool. Both must be gated; handling only `isDone` would leave a silent bypass for ordinary final responses.

The direct runtime has no protected finish-attempt seam today. Add a narrow default-accept hook at both ordinary completion boundaries, with continuation mechanics remaining in the shared loop and the actual criterion policy implemented by Jev's criterion classes. Do not copy the runtime loop into `JevRuntime`.

The SDK already has generic `MinElapsedSeconds`/`MinTimeTaken` output contracts, configured through `AgentLoopSettings`. Those are related but do not provide the requested Jev-specific subclass package and direct `minimum_duration_met` field. This feature remains opt-in and separate. `AgentRuntime` captures `started_at` from `MiddlewarePipeline.clock`, which defaults to `time.monotonic` and is injectable for deterministic tests. Relevant project guidance: `field-guide/vidbyte-sdk/runtime-boundaries.md` and `strict-config-dataclasses.md`.

---

## 4. Requirements

### Functional Requirements

1. `JevAgentSettings` accepts zero or more done criteria, defaulting to empty.
2. `JevPreset.MinimumTime` accepts exactly one positive finite numeric value among `seconds`, `minutes`, `hours`, and `days`; booleans and invalid values are rejected with `ConfigurationError` at construction.
3. Criteria are immutable/snapshotted and validated before runtime/provider construction.
4. Elapsed duration uses one per-attempt monotonic clock domain and clamps negative injected-clock deltas to zero.
5. All configured criteria must pass before either a normal text final response or `isDone` can finalize the run.
6. If any criterion is unmet, append the candidate assistant response where needed, add a continuation message, and continue the same runtime loop with existing counters, history, middleware, and tool state.
7. Re-evaluate time on every completion attempt. Crossing the threshold permits a future model-originated finish but never completes the task by itself.
8. A returned result for a configured minimum-time criterion includes `metadata["minimum_duration_met"]`, computed at finalization. Omit the key if the criterion is absent.
9. Existing generic output contracts and non-Jev runtime behavior remain unchanged.

### Non-Functional Requirements

- Gate evaluation is synchronous, deterministic, and adds no network call or new dependency.
- Concurrent runs do not share start times or mutable criterion state.
- Existing middleware ordering, runtime budgets, tool accounting, usage/speed tracking, context behavior, and tracing are preserved.
- Configuration and builder-style errors remain explicit; no fail-open completion.

---

## 5. High-Level Design

Add a `done_criteria` package under Jev with `JevDoneCriterion` as the criterion contract, `JevDoneCriteria` as the composite evaluator, and `MinimumTime` as the first concrete subclass. `JevPreset.MinimumTime(...)` is the public factory. Settings snapshot and validate the tuple and the existing Jev runtime receives the policy through its settings.

Add a protected async `_continue_finish_attempt(...)` hook to `AgentRuntime`, defaulting to `False`. At both normal finalization boundaries, the shared loop gives the subclass the candidate result, run-local state, and mutable messages. If the hook returns `True`, the shared loop continues; otherwise it finalizes as today. On a rejected text response, the base loop appends that assistant response before continuing, then the Jev hook appends user feedback. On a rejected `isDone`, preserve the tool-call history and add continuation feedback. Jev's hook evaluates criteria and only implements policy; `JevRuntime` adds the final computed metadata on every returned result.

```text
JevAgentSettings(done_criteria=(JevPreset.MinimumTime(hours=5),))
  -> JevRuntime -> AgentRuntime normal finish attempt (text OR isDone)
  -> JevDoneCriteria evaluates monotonic elapsed duration
       unmet: append feedback, continue same loop
       met: accept only the model's completion attempt
  -> result finalization includes minimum_duration_met
```

---

## 6. Detailed Design

### 6.1 Jev criterion package

**File(s):** `vidbyte/agents/jev/done_criteria/__init__.py`, `vidbyte/agents/jev/done_criteria/base.py`, `vidbyte/agents/jev/done_criteria/criteria.py`, `vidbyte/agents/jev/done_criteria/presets.py`  
**Type:** New files

#### What it does

Defines the shared Jev criterion contract and composite, with each criterion subclass implementing evaluation, continuation feedback, and result metadata. `MinimumTime` stores one normalized positive finite duration in seconds. `JevPreset.MinimumTime(...)` is its named ergonomic factory.

#### Interface / API

```python
class JevDoneCriterion(ABC):
    def is_met(self, *, elapsed_seconds: float) -> bool: ...
    def continuation_prompt(self, *, elapsed_seconds: float) -> str: ...
    def result_metadata(self, *, elapsed_seconds: float) -> Mapping[str, object]: ...

class JevDoneCriteria:
    def continuation_prompt(self, *, elapsed_seconds: float) -> str | None: ...
    def result_metadata(self, *, elapsed_seconds: float) -> Mapping[str, object]: ...

class MinimumTime(JevDoneCriterion):
    def __init__(self, *, seconds: float | None = None, minutes: float | None = None, hours: float | None = None, days: float | None = None) -> None: ...

class JevPreset:
    @staticmethod
    def MinimumTime(*, seconds: float | None = None, minutes: float | None = None, hours: float | None = None, days: float | None = None) -> MinimumTime: ...
```

The composite uses AND semantics and combines feedback from unmet criteria. Empty criteria accept completion and emit no metadata.

#### Logic / Algorithm

1. Validate exactly one duration unit is supplied and its value is a positive finite number but not a Boolean.
2. Convert that value to canonical seconds during criterion construction.
3. Calculate elapsed time using `max(0.0, middleware.clock() - state.started_at)` at each finish attempt and result finalization.
4. Reject if any criterion is unmet; otherwise return no continuation prompt.
5. Return direct criterion result metadata, including `minimum_duration_met` for the duration criterion.

#### Edge Cases & Error Handling

- Empty configured criteria are valid and preserve existing behavior.
- Missing/multiple unit arguments, invalid values, and arbitrary non-criterion objects raise `ConfigurationError` during construction.
- A rejected finish never produces a success result; runtime budgets remain active and can terminate a run that repeatedly attempts early completion.

### 6.2 Settings and Jev runtime

**File(s):** `vidbyte/agents/jev/settings.py`, `vidbyte/agents/jev/runtime.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified files

#### What it does

Adds and validates `done_criteria` on Jev settings, uses the existing runtime extension seam to provide the criteria to Jev, implements its completion hook, attaches metadata at finalization, and exports the public types.

#### Interface / API

```python
JevAgentSettings(..., done_criteria: Sequence[JevDoneCriterion] = ())
JevAgentSettings(..., done_criteria=(JevPreset.MinimumTime(hours=5),))
```

`JevAgent(settings)` remains the constructor; no separate keyword-only constructor API is added.

#### Logic / Algorithm

1. Convert supported criteria to a tuple and validate each criterion instance.
2. Pass the immutable criteria to the run's `JevRuntime` through existing settings.
3. Implement `_continue_finish_attempt(...)` in `JevRuntime` by delegating evaluation to `JevDoneCriteria` and appending feedback when unmet.
4. Add result metadata without dropping any existing result fields or metadata.
5. Export `JevDoneCriterion`, `JevDoneCriteria`, `MinimumTime`, and `JevPreset` from the Jev, agents, and root packages.

#### Edge Cases & Error Handling

- Existing settings callers remain source-compatible.
- Strings/bytes are rejected as the criteria iterable; criteria are copied so later caller mutation cannot change settings.
- Runtime start time is state-local, not stored on the shared agent or criterion.

### 6.3 Shared runtime finish-attempt hook

**File(s):** `vidbyte/agents/runtime.py`  
**Type:** Modified file

#### What it does

Adds a protected async hook called at both normal model-originated completion paths: no-tool final response and internal `isDone`. Base implementation accepts completion by returning `False`; Jev can append feedback and return `True` to request continuation.

#### Interface / API

```python
async def _continue_finish_attempt(self, result: AgentResult, state: BaseAgentRuntimeLoopState, messages: list[dict[str, Any]]) -> bool: ...
```

#### Logic / Algorithm

1. Call the hook at the final response branch after existing output-contract checks and before final result return.
2. Call the hook at the `isDone` branch after existing output-contract checks and before accepting the `ToolResult` as final.
3. For a rejected plain-text final response, add the candidate assistant output to conversation messages before looping, so the continuation prompt has the candidate as context.
4. For rejected `isDone`, retain the existing assistant tool-call message and add continuation feedback in model-visible form.
5. If the hook returns `True`, continue through the existing loop and its budgets; otherwise follow current finalization.
6. Default hook returns `False` so non-Jev runtimes retain current behavior.

#### Edge Cases & Error Handling

- Generic contract rejection remains independent and uses its existing rejection budget.
- Middleware after-iteration hooks still run in their existing order for both completion paths.
- The hook is called only for ordinary model-originated finish attempts, not budget or middleware abort results.

### 6.4 Tests and verification script

**File(s):** `tests/test_jev_done_criteria.py`, `scripts/test-jev-done-criteria.py`  
**Type:** New files

#### What it does

Tests validation and both completion paths with scripted model output and a controllable monotonic clock. The verification script runs the focused tests and prints per-case results plus a final count.

#### Interface / API

Run `python scripts/test-jev-done-criteria.py` from the SDK root.

#### Logic / Algorithm

1. Build test agents without live provider calls.
2. Drive fake monotonic time below, at, and above the threshold.
3. Verify provider-visible history, continuation behavior, outputs, result metadata, and default behavior.
4. Execute all listed tests through the script and propagate any non-zero result.

#### Edge Cases & Error Handling

- No test sleeps for a real duration.
- Tests cover invalid inputs, a threshold boundary, repeated attempts bounded by runtime budgets, and concurrent run isolation.

---

## 7. Data Model Changes

### 7.1 JevAgentSettings and result metadata

**Change type:** Modified in-memory configuration and result metadata; no persistence schema.

```python
done_criteria: tuple[JevDoneCriterion, ...] = ()
AgentResult.metadata["minimum_duration_met"]: bool  # only when configured
```

**Migration strategy:** N/A - additive in-memory SDK API and metadata only; no stored documents or migrations.

---

## 8. API Changes

### 8.1 Jev SDK construction

**Change type:** Additive public SDK API.

```python
JevAgentSettings(name="researcher", system_prompt="Research.", provider="openai", model_name="gpt-4.1-mini", done_criteria=(JevPreset.MinimumTime(hours=5),))
```

Invalid configurations raise `ConfigurationError` during settings construction. There are no HTTP endpoints.

### 8.2 Result metadata

Configured runs return `minimum_duration_met: bool`; absent criterion omits the field.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-done-criteria.md` | Approved source of truth. |
| CREATE | `vidbyte/agents/jev/done_criteria/README.md` | Explain subsystem intent, boundaries, and file routing. |
| CREATE | `vidbyte/agents/jev/done_criteria/__init__.py` | Public exports for criteria package. |
| CREATE | `vidbyte/agents/jev/done_criteria/base.py` | Criterion and composite contracts. |
| CREATE | `vidbyte/agents/jev/done_criteria/criteria.py` | Minimum-time criterion. |
| CREATE | `vidbyte/agents/jev/done_criteria/presets.py` | `JevPreset.MinimumTime(...)` factory. |
| MODIFY | `vidbyte/agents/jev/settings.py` | Validated criteria setting. |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Jev completion policy and metadata. |
| MODIFY | `vidbyte/agents/runtime.py` | Default completion hook at both terminal boundaries. |
| MODIFY | `lint/baseline.json` | Ratchet the S051 allowance after formatting improves its count by one. |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Jev public exports. |
| MODIFY | `vidbyte/agents/__init__.py` | Agent namespace exports. |
| MODIFY | `vidbyte/__init__.py` | Root namespace exports. |
| CREATE | `tests/features/jev_minimum_duration/FEATURE.md` | Feature contract and failure inventory for future test authors. |
| CREATE | `tests/test_jev_done_criteria.py` | Unit and integration coverage. |
| CREATE | `scripts/test-jev-done-criteria.py` | Executable verification runner. |

No files are planned for deletion.

---

## 10. Testing Plan

### Unit Tests

- Each unit supplied in seconds/minutes/hours/days normalizes correctly — [Edge Case].
- Zero, negative, Boolean, non-finite, and non-numeric durations are rejected — [Edge Case].
- Missing or multiple unit arguments are rejected — [Hidden Assumption].
- Empty criteria are accepted and retain ordinary Jev behavior — [Edge Case].
- String/bytes iterables and arbitrary criteria objects are rejected — [Hidden Assumption].
- Composite criteria require all configured criteria to pass — [Silent Failure].

### Integration Tests

- Early ordinary final response is retained in history, followed by continuation feedback, and the same loop continues — [Silent Failure].
- Early `isDone` is rejected and another model invocation occurs — [Silent Failure].
- A threshold-minus-epsilon rejects while exactly-at and threshold-plus-epsilon permit a later model completion attempt — [Edge Case].
- Passing the threshold without a model finish signal does not complete the run — [Hidden Assumption].
- Budget termination before threshold returns `minimum_duration_met=False`; termination after threshold returns `True` — [Silent Failure].
- Concurrent attempts use isolated start times — [Hidden Failure].
- Gate behavior composes with generic contracts and middleware lifecycle — [Hidden Failure].
- No criteria means no prompt, no metadata key, and unchanged behavior — [Hidden Assumption].
- Public Jev, agents, and root imports expose the same API — [Hidden Failure].

### Manual / QA Test Cases

1. Configure five hours, script an early ordinary final response and verify the captured next model call includes the candidate answer and continuation message — [Silent Failure].
2. Script an early internal `isDone` call and verify feedback appears and the runtime continues without sleeping — [Hidden Failure].
3. Run without criteria and compare completion/result metadata to the current scaffold — [Hidden Assumption].

The executable script `python scripts/test-jev-done-criteria.py` will run every listed automated case, print PASS/FAIL per case, summarize `X/Y tests passed`, and exit non-zero for any failure.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `MiddlewarePipeline.clock` / Python `time.monotonic` | Python 3.11+ | Same monotonic domain for run start and elapsed-time evaluation. | A custom injected clock must be stable and monotonic; clamped negative elapsed avoids false satisfaction. |
| Existing pytest and scripted runner utilities | Pinned project dev dependencies | Offline deterministic test execution. | Tests must use the fake clock and avoid live model credentials. |

No new package dependency or external service is introduced.

---

## 12. Rollout & Deployment

- Opt-in only; no flag is needed.
- API is additive and existing callers remain valid.
- Release through the normal SDK package workflow; no migration/deployment ordering.
- Revert the feature commit to roll back. Callers can remove the criterion before downgrading.
- Run focused tests, source CI, full CI, and the repository lint gate.

---

## 13. Open Questions

- [x] Public API spelling is `JevPreset.MinimumTime(...)` with unit keywords and passed through `JevAgentSettings.done_criteria`.
- [x] Multiple criteria use AND semantics.
- [x] Omit `minimum_duration_met` when no minimum-time criterion is configured.

---

## 14. Alternatives Considered

### Alternative 1: Reuse generic `AgentLoopSettings.output_contracts` only

- **What:** Configure the existing `MinElapsedSeconds`/`MinTimeTaken` floor.
- **Why rejected:** It does not supply the requested Jev-local criterion subclass package or direct result field; changing it would affect unrelated agents. It remains an independent generic feature.

### Alternative 2: Copy `_arun_once` into `JevRuntime`

- **What:** Duplicate the runtime loop to catch completion locally.
- **Why rejected:** It duplicates middleware, fallback, tool, context, accounting, and trace semantics. A protected default-accept hook is smaller and less likely to drift.

### Alternative 3: Middleware-only gate

- **What:** Reject `isDone` through tool middleware.
- **Why rejected:** It does not cover ordinary final text responses and does not provide a clean continue/finalize lifecycle at both runtime completion boundaries.

### Alternative 4: Sleep until threshold

- **What:** Block on the first early completion attempt until time elapses.
- **Why rejected:** The required behavior is to prompt the model to continue. Passing time does not imply task completion, and sleeping prevents productive work during the minimum interval.
