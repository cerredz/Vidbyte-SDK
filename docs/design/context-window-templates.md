# Design Doc: Context Window Templates

**Status:** Draft
**Author:** Claude
**Created:** 2026-05-28
**Last Updated:** 2026-05-28

---

## 1. Overview

Context window algorithms produce deterministic structural patterns in the
sequence of events that drive an agent run. This feature introduces a
lightweight tracing layer — `ContextWindowRecorder` — that accumulates
ordered slot events as an algorithm executes, and a template validation layer —
`ContextWindowTemplate` — that asserts a recorded slot sequence matches an
expected structural pattern. Together they give AI-assisted algorithm
implementations a concrete, machine-readable acceptance criterion: the agent
writes the template first, implements the algorithm second, runs the test
harness to collect the actual slot sequence, and iterates on the implementation
until the recorded sequence matches the template exactly. The Reflexion
context-window algorithm is the first implementation validated under this
system.

---

## 2. Goals & Non-Goals

### Goals

- Provide `ContextWindowRecorder` and `NullRecorder` in
  `vidbyte/context/templates/` to accumulate ordered slot events during agent
  runs with zero overhead when not testing.
- Provide `ContextWindowTemplate` and `TemplateViolation` in
  `vidbyte/lib/templates/` to validate a recorder's slot sequence against an
  expected pattern.
- Instrument `AgentRuntime` with an optional recorder that defaults to
  `NullRecorder`.
- Instrument `ReflexionRuntimeAlgorithm` to emit `system_prompt`,
  `reflexion_trial`, and `reflexion_reflection` slots at the exact code points
  where those structural elements are introduced.
- Provide `ReflexionContextWindowTemplate` as the canonical template for the
  Reflexion algorithm, parameterizable by trial count and expected failure
  count.
- Write a comprehensive skill file at
  `skills/vidbyte-sdk/context-window-templates.md` documenting every step
  required to add templates to future algorithms.
- Write unit tests and a verification script covering correct behavior, edge
  cases, and hidden failure modes.

### Non-Goals

- Emitting base runtime slots (`agent_iteration`, `tool_call`, `middleware`)
  from `AgentRuntime._arun_once`. These are Phase 2 work and their slot names
  are reserved but not emitted in this implementation.
- Connecting the recorder to any external observability system (LangSmith,
  Langfuse, OTel). The recorder is a pure in-process data structure.
- Autonomous code-repair loop scripting. That belongs in the skill file as
  workflow guidance, not as shipped SDK infrastructure.
- Modifying `MultiProviderAgenticGraderRuntimeAlgorithm`. Only Reflexion is
  instrumented in this PR.
- Exposing templates on the root `vidbyte` public namespace. Templates are
  internal testing utilities, not user-facing API.

---

## 3. Background & Context

Context-window algorithms are tested structurally today only through
`StrategyResult.metadata` assertions (e.g. `reflexion.trial_count == 2`).
This verifies that the right number of attempts happened but does not verify
that the structural sequence of the context window itself was correct. An
implementation could produce the right metadata while injecting reflection
content at the wrong point, omitting the system prompt, or running reflection
stages out of order.

The template system fills this gap by asserting the exact ordered sequence
of structural slot events, not just aggregate counts. It is deliberately
simple: a list of expected slot name strings compared position-by-position
against the list of emitted slot name strings. Complexity lives in how
templates are constructed (Python list arithmetic), not in the validator.

This system is also the foundation for AI-assisted algorithm development.
When an AI agent is asked to implement a new context-window algorithm, it
derives the expected template from the algorithm description first, then
implements the code, then uses the template as a feedback signal to iterate
until the implementation produces the correct structural sequence.

---

## 4. Requirements

### Functional Requirements

1. `SlotEvent` is an immutable dataclass with fields `slot_type: str`,
   `iteration: int`, and `metadata: dict[str, Any]`.
2. `RecorderBase` is an abstract class with abstract methods `append(slot_type,
   *, iteration, **metadata)` and `slots() -> tuple[str, ...]`.
3. `ContextWindowRecorder` implements `RecorderBase`, stores `SlotEvent`
   instances in insertion order, and exposes `events() -> tuple[SlotEvent, ...]`
   in addition to `slots()`.
4. `NullRecorder` implements `RecorderBase` with no-op `append` and empty-tuple
   `slots()`, adding zero overhead.
5. `TemplateViolation` is an immutable dataclass with fields `position: int`,
   `expected: str`, `actual: str | None` (None when the trace ended early), and
   `message: str`.
6. `ContextWindowTemplate` accepts a `list[str]` of expected slot names and
   exposes `validate(recorder) -> list[TemplateViolation]` and
   `passes(recorder) -> bool`.
7. `validate` reports a violation for every position where expected and actual
   slot names differ, for every expected position where the trace ended early,
   and for every position in the trace beyond the length of the template.
8. `ReflexionContextWindowTemplate` is a `ContextWindowTemplate` subclass that
   accepts `max_trials: int` and `failing_trials: int | None` (defaults to
   `max_trials - 1`) and constructs the correct slot list using the Reflexion
   structural formula.
9. `AgentRuntime.__init__` accepts `recorder: RecorderBase | None = None` and
   stores it as `self.recorder`, defaulting to `NullRecorder()`.
10. `ReflexionRuntimeAlgorithm.arun` emits `"system_prompt"` on the recorder
    once at the start of the run.
11. `ReflexionRuntimeAlgorithm._run_trial` emits `"reflexion_trial"` on the
    recorder at the start of each trial, before calling `_arun_once`.
12. `ReflexionRuntimeAlgorithm._reflect_after_failure` emits
    `"reflexion_reflection"` on the recorder at the start of each reflection
    call, before invoking the runner.
13. The recorder argument is forwarded from `AgentRuntime` to
    `ReflexionRuntimeAlgorithm` via the existing runtime reference
    (`self.runtime.recorder`), requiring no new parameter threading.
14. All new modules include the standard Context Protocol Header docstring.
15. The skill file documents: mental model, slot name conventions, recorder
    usage, template construction, instrumentation pattern, test structure, and
    per-algorithm checklist.

### Non-Functional Requirements

- `NullRecorder.append` must add no list allocations and no attribute lookups
  beyond the method call itself.
- `ContextWindowTemplate.validate` runs in O(n) time where n is
  `max(len(template), len(trace))`.
- The recorder is not thread-safe. Agent runs are async/sequential within a
  single run; no locking is required.
- All new files compile cleanly under `python -m compileall vidbyte`.
- All existing tests continue to pass after `AgentRuntime` gains the optional
  `recorder` parameter.

---

## 5. High-Level Design

```
AgentRuntime
  └─ recorder: RecorderBase (NullRecorder by default)
       │
       │  forwarded via self.runtime.recorder
       ▼
ReflexionRuntimeAlgorithm.arun()
  │  recorder.append("system_prompt")
  │
  ├─ _run_trial(trial_index=0)
  │    recorder.append("reflexion_trial", iteration=0)
  │    → _arun_once() [normal agent loop, no slot emission in Phase 1]
  │
  ├─ _reflect_after_failure(trial_index=0)
  │    recorder.append("reflexion_reflection", iteration=0)
  │    → _invoke_with_middleware()
  │
  ├─ _run_trial(trial_index=1)
  │    recorder.append("reflexion_trial", iteration=1)
  │    → _arun_once()
  │
  └─ [if done] return StrategyResult
       │
       ▼
ContextWindowRecorder.slots()
  → ("system_prompt", "reflexion_trial", "reflexion_reflection", "reflexion_trial")

ReflexionContextWindowTemplate(max_trials=2, failing_trials=1)
  .expected_slots
  → ("system_prompt", "reflexion_trial", "reflexion_reflection", "reflexion_trial")

template.validate(recorder)
  → []  ← empty means all positions match
```

The recorder and template are completely separate from the tracing system
(`TracerBase`, `SpanContext`). Tracing is for observability platforms.
Templates are for structural correctness assertions in tests. They share no
code and have no coupling.

---

## 6. Detailed Design

### 6.1 SlotEvent

**File:** `vidbyte/context/templates/recorder.py`
**Type:** New file

#### What it does
Represents one structural slot event emitted during an agent run.

#### Interface
```python
@dataclass(frozen=True)
class SlotEvent:
    slot_type: str
    iteration: int
    metadata: dict[str, Any]
```

#### Edge Cases & Error Handling
- `metadata` is mutable but the dataclass is frozen — callers must pass a new
  dict each time, not a shared reference.

---

### 6.2 RecorderBase

**File:** `vidbyte/context/templates/recorder.py`
**Type:** New file

#### What it does
Abstract interface all recorder implementations must satisfy.

#### Interface
```python
class RecorderBase(ABC):
    @abstractmethod
    def append(self, slot_type: str, *, iteration: int = 0, **metadata: Any) -> None: ...

    @abstractmethod
    def slots(self) -> tuple[str, ...]: ...
```

---

### 6.3 ContextWindowRecorder

**File:** `vidbyte/context/templates/recorder.py`
**Type:** New file

#### What it does
Accumulates `SlotEvent` instances in insertion order during a run.

#### Interface
```python
class ContextWindowRecorder(RecorderBase):
    def append(self, slot_type: str, *, iteration: int = 0, **metadata: Any) -> None: ...
    def slots(self) -> tuple[str, ...]: ...
    def events(self) -> tuple[SlotEvent, ...]: ...
    def reset(self) -> None: ...
```

#### Logic
1. `append` constructs a `SlotEvent` from the arguments and appends it to
   `self._events`.
2. `slots` returns a tuple of `event.slot_type` for each event in insertion
   order.
3. `events` returns an immutable view of all events.
4. `reset` clears `_events` to allow recorder reuse across test cases.

#### Edge Cases & Error Handling
- `slot_type` is not validated. Unknown slot types are stored silently; the
  template validator is responsible for detecting mismatches.

---

### 6.4 NullRecorder

**File:** `vidbyte/context/templates/recorder.py`
**Type:** New file

#### What it does
Zero-overhead no-op recorder used when no template testing is configured.

#### Interface
```python
class NullRecorder(RecorderBase):
    def append(self, slot_type: str, *, iteration: int = 0, **metadata: Any) -> None: ...
    def slots(self) -> tuple[str, ...]: ...
```

#### Logic
- `append` does nothing.
- `slots` returns `()`.

---

### 6.5 TemplateViolation

**File:** `vidbyte/lib/templates/base.py`
**Type:** New file

#### What it does
Describes one mismatch between expected and actual slot sequences.

#### Interface
```python
@dataclass(frozen=True)
class TemplateViolation:
    position: int
    expected: str
    actual: str | None
    message: str
```

- `actual` is `None` when the trace ended before the expected position.

---

### 6.6 ContextWindowTemplate

**File:** `vidbyte/lib/templates/base.py`
**Type:** New file

#### What it does
Validates a `RecorderBase` slot sequence against an expected ordered list of
slot names.

#### Interface
```python
class ContextWindowTemplate:
    def __init__(self, slots: list[str]) -> None: ...

    @property
    def expected_slots(self) -> tuple[str, ...]: ...

    def validate(self, recorder: RecorderBase) -> list[TemplateViolation]: ...
    def passes(self, recorder: RecorderBase) -> bool: ...
```

#### Logic — `validate`
1. Obtain `actual = recorder.slots()`.
2. Iterate over `range(max(len(expected), len(actual)))`.
3. For each index `i`:
   - If `i >= len(expected)` and `i < len(actual)`: append violation with
     `expected="<end>"`, `actual=actual[i]`.
   - If `i >= len(actual)` and `i < len(expected)`: append violation with
     `expected=expected[i]`, `actual=None`.
   - If both exist and differ: append violation with
     `expected=expected[i]`, `actual=actual[i]`.
4. Return the violations list.

#### Edge Cases & Error Handling
- Empty template against empty recorder → zero violations.
- Empty template against non-empty recorder → one violation per extra slot.
- Non-empty template against empty recorder → one violation per missing slot.

---

### 6.7 ReflexionContextWindowTemplate

**File:** `vidbyte/lib/templates/reflexion.py`
**Type:** New file

#### What it does
Constructs the canonical slot sequence for a Reflexion run given trial count
and expected failure count.

#### Interface
```python
class ReflexionContextWindowTemplate(ContextWindowTemplate):
    def __init__(self, *, max_trials: int = 3, failing_trials: int | None = None) -> None: ...

    @staticmethod
    def _build_slots(*, max_trials: int, failing_trials: int) -> list[str]: ...
```

#### Logic — `_build_slots`

For a Reflexion run where `failing_trials` trials fail and one final trial
succeeds (or runs out):

```
slots = ["system_prompt"]
for _ in range(failing_trials):
    slots += ["reflexion_trial", "reflexion_reflection"]
slots += ["reflexion_trial"]  # final trial
```

Example — `max_trials=3, failing_trials=2`:
```
["system_prompt", "reflexion_trial", "reflexion_reflection",
 "reflexion_trial", "reflexion_reflection", "reflexion_trial"]
```

Example — `max_trials=1, failing_trials=0`:
```
["system_prompt", "reflexion_trial"]
```

#### Edge Cases & Error Handling
- `failing_trials > max_trials - 1` is not validated at construction time.
  The template simply produces a slot list that cannot be satisfied by a
  correct implementation, which is a valid test case (intentionally failing).
- `max_trials=0` raises `ValueError` in `ReflexionAlgorithm.__post_init__`
  before any run begins; no need to guard here.

---

### 6.8 AgentRuntime — recorder parameter

**File:** `vidbyte/agents/runtime.py`
**Type:** Modified

#### What it does
Accepts and stores an optional `RecorderBase` so algorithm implementations can
emit slot events without knowing about test infrastructure.

#### Change
Add `recorder: RecorderBase | None = None` to `AgentRuntime.__init__` after
the existing `context_manager` parameter. Store as:
```python
from vidbyte.context.templates import NullRecorder, RecorderBase
self.recorder: RecorderBase = recorder or NullRecorder()
```

No other changes to `AgentRuntime` are required for Phase 1. The recorder is
accessed by algorithm implementations through `self.runtime.recorder`.

---

### 6.9 ReflexionRuntimeAlgorithm — slot emission

**File:** `vidbyte/agents/algorithms/reflexion.py`
**Type:** Modified

#### What it does
Emits structural slot events at the three key points that define the Reflexion
context window pattern.

#### Changes

In `arun`, immediately after the state variables are initialized and before
the trial loop:
```python
self.runtime.recorder.append("system_prompt")
```

In `_run_trial`, as the first statement of the method body before the
`context_for_trial` call:
```python
self.runtime.recorder.append("reflexion_trial", iteration=trial_index)
```

In `_reflect_after_failure`, as the first statement of the method body before
the `_invoke_with_middleware` call:
```python
self.runtime.recorder.append("reflexion_reflection", iteration=trial_index)
```

These three emit points together produce the complete structural slot sequence
that `ReflexionContextWindowTemplate` validates.

---

### 6.10 Module `__init__` files

**File:** `vidbyte/context/templates/__init__.py`
**Type:** New file

Exports `ContextWindowRecorder`, `NullRecorder`, `RecorderBase`, `SlotEvent`.

**File:** `vidbyte/lib/templates/__init__.py`
**Type:** New file

Exports `ContextWindowTemplate`, `ReflexionContextWindowTemplate`,
`TemplateViolation`.

---

### 6.11 Skill File

**File:** `skills/vidbyte-sdk/context-window-templates.md`
**Type:** New file

The skill file is the authoritative reference for adding template support to
any new context-window algorithm. It must cover:

1. **Mental model**: templates as ordered slot name lists; recorder as a
   deterministic event log; validation as positional string matching.
2. **Slot name conventions**: snake_case, algorithm-prefixed for
   algorithm-specific slots (e.g. `reflexion_trial`, `reflexion_reflection`),
   unprefixed for base runtime slots (e.g. `system_prompt`, `tool_call`,
   `agent_iteration`, `middleware`). Base runtime slots are reserved but not
   yet emitted by `AgentRuntime._arun_once` in Phase 1.
3. **Recorder usage**: create a `ContextWindowRecorder` before the run, pass
   it into `AgentRuntime(recorder=recorder)`, run the agent, then call
   `recorder.slots()` or pass the recorder to a template's `validate` method.
4. **Template construction**: use list arithmetic to build the expected slot
   list; wrap in a `ContextWindowTemplate` subclass with a documented
   `_build_slots` method.
5. **Instrumentation pattern**: emit slots at the exact code point where the
   structural element is introduced, not before or after; use the recorder
   from `self.runtime.recorder` in runtime adapter classes.
6. **Test structure**: one test class per algorithm, one test per scenario
   (e.g. single trial success, two-trial failure/success, max-trial exhaust).
7. **Checklist**: for any new algorithm, the developer must add
   instrumentation, write a template class, write tests, and update this skill
   file.
8. **Full Reflexion walkthrough**: complete worked example showing all files,
   instrumentation points, template construction, and test cases.

---

## 7. Data Model Changes

No schema or database changes. All new types are in-process Python dataclasses.

### 7.1 SlotEvent

**Change type:** New

```python
@dataclass(frozen=True)
class SlotEvent:
    slot_type: str          # e.g. "system_prompt", "reflexion_trial"
    iteration: int          # which trial/iteration index emitted this slot
    metadata: dict[str, Any]  # arbitrary extra context from the emit call
```

### 7.2 TemplateViolation

**Change type:** New

```python
@dataclass(frozen=True)
class TemplateViolation:
    position: int       # 0-based index in the slot sequence
    expected: str       # expected slot name at this position
    actual: str | None  # actual slot name; None if trace ended early
    message: str        # human-readable description
```

---

## 8. API Changes

N/A — no HTTP endpoints are added or modified. This feature is internal SDK
infrastructure.

The only public-facing change is the addition of an optional `recorder`
keyword argument to `AgentRuntime.__init__`. Since it has a default value of
`None`, this is fully backwards-compatible.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `vidbyte/context/templates/__init__.py` | New module exports |
| CREATE | `vidbyte/context/templates/recorder.py` | RecorderBase, ContextWindowRecorder, NullRecorder, SlotEvent |
| CREATE | `vidbyte/lib/templates/__init__.py` | New module exports |
| CREATE | `vidbyte/lib/templates/base.py` | ContextWindowTemplate, TemplateViolation |
| CREATE | `vidbyte/lib/templates/reflexion.py` | ReflexionContextWindowTemplate |
| MODIFY | `vidbyte/agents/runtime.py` | Add optional recorder param, store NullRecorder default |
| MODIFY | `vidbyte/agents/algorithms/reflexion.py` | Emit system_prompt, reflexion_trial, reflexion_reflection slots |
| CREATE | `tests/test_context_window_templates.py` | Unit tests for all new types and Reflexion instrumentation |
| CREATE | `scripts/test-context-window-templates.py` | Executable verification script |
| CREATE | `skills/vidbyte-sdk/context-window-templates.md` | Comprehensive skill guide |

---

## 10. Testing Plan

### Unit Tests — `tests/test_context_window_templates.py`

#### SlotEvent

- `test_slot_event_is_frozen` — creating and trying to mutate raises
  `FrozenInstanceError`. [Hidden Assumption: dataclass frozen=True actually
  prevents mutation]
- `test_slot_event_stores_slot_type_iteration_metadata` — fields are set
  correctly from constructor arguments. [Edge Case: metadata is an empty dict
  by default not a shared singleton]

#### ContextWindowRecorder

- `test_recorder_starts_empty` — `slots()` returns `()` before any appends.
  [Edge Case: empty trace]
- `test_recorder_slots_returns_insertion_order` — appending A, B, C yields
  `("A", "B", "C")` not any other order. [Silent Failure: list or set could
  return wrong order]
- `test_recorder_events_returns_full_slot_events` — `events()` returns
  `SlotEvent` instances, not raw strings. [Silent Failure: returning wrong type
  with no error]
- `test_recorder_append_stores_iteration` — `iteration=5` is stored and
  accessible via `events()[0].iteration`. [Hidden Assumption: iteration kwarg
  is actually threaded through]
- `test_recorder_append_stores_extra_metadata` — extra kwargs appear in
  `events()[0].metadata`. [Hidden Assumption: `**metadata` is captured]
- `test_recorder_reset_clears_all_events` — after `reset()`, `slots()` is
  `()` again. [Edge Case: recorder reuse between test cases]
- `test_recorder_does_not_share_metadata_across_events` — appending with
  `key=1` then `key=2` produces two distinct metadata dicts, not one mutated
  dict. [Hidden Failure: shared mutable reference]

#### NullRecorder

- `test_null_recorder_append_does_not_raise` — calling `append(...)` does not
  raise. [Hidden Assumption: no-op is truly safe]
- `test_null_recorder_slots_always_empty` — `slots()` returns `()` even after
  many `append` calls. [Silent Failure: might accumulate despite being "null"]

#### ContextWindowTemplate

- `test_template_stores_expected_slots` — `expected_slots` matches the list
  passed to the constructor. [Hidden Assumption: constructor correctly converts
  list to tuple]
- `test_validate_returns_empty_for_exact_match` — template `["A", "B"]`
  against recorder with slots `("A", "B")` returns `[]`. [Edge Case: happy
  path must be confirmed explicitly]
- `test_validate_reports_mismatch_at_correct_position` — template `["A", "B"]`
  against `("A", "X")` returns one violation at position 1. [Silent Failure:
  off-by-one in position counting]
- `test_validate_reports_trace_ended_early` — template `["A", "B", "C"]`
  against `("A",)` returns two violations with `actual=None`. [Edge Case:
  truncated trace]
- `test_validate_reports_extra_slots_in_trace` — template `["A"]` against
  `("A", "B", "C")` returns two violations for the extra slots. [Edge Case:
  longer trace than template]
- `test_validate_empty_template_empty_trace` — returns `[]`. [Edge Case:
  both empty]
- `test_validate_empty_template_nonempty_trace` — returns violations for each
  extra slot. [Edge Case: template empty but trace has events]
- `test_validate_nonempty_template_empty_trace` — returns violations for each
  missing slot with `actual=None`. [Edge Case: trace empty but template expects
  slots]
- `test_passes_returns_true_on_exact_match` — `passes()` is `True` when
  `validate()` would be empty. [Silent Failure: passes might return wrong value
  without error]
- `test_passes_returns_false_on_any_violation` — `passes()` is `False` when
  any violation exists. [Silent Failure: passes might return True when
  violations exist]

#### ReflexionContextWindowTemplate

- `test_single_trial_no_failures` — `max_trials=1, failing_trials=0` produces
  `["system_prompt", "reflexion_trial"]`. [Edge Case: minimal possible run]
- `test_two_trials_one_failure` — `max_trials=2, failing_trials=1` produces
  `["system_prompt", "reflexion_trial", "reflexion_reflection",
  "reflexion_trial"]`. [Edge Case: minimal multi-trial]
- `test_three_trials_two_failures_default` — `max_trials=3` (default
  `failing_trials=2`) produces the 7-slot sequence. [Edge Case: default config]
- `test_failing_trials_defaults_to_max_trials_minus_one` — omitting
  `failing_trials` produces the same template as passing `failing_trials=max_trials-1`.
  [Hidden Assumption: default wiring is correct]
- `test_zero_failing_trials_produces_system_prompt_plus_one_trial` — verifies
  no reflection slots are inserted when no failures expected. [Edge Case:
  zero-failure run]

#### AgentRuntime recorder integration

- `test_runtime_defaults_to_null_recorder` — `AgentRuntime(...).recorder` is
  `NullRecorder`. [Hidden Assumption: default is NullRecorder not None]
- `test_runtime_accepts_recorder_instance` — passing a `ContextWindowRecorder`
  stores it as `self.recorder`. [Hidden Assumption: recorder kwarg is wired]
- `test_existing_tests_unaffected` — importing `AgentRuntime` without the
  `recorder` kwarg matches prior behavior. [Silent Failure: adding the param
  might break positional callers]

#### Reflexion instrumentation

- `test_reflexion_emits_system_prompt_once_at_run_start` — after a single-trial
  run, recorder has exactly one `"system_prompt"` slot, and it is the first.
  [Hidden Assumption: system_prompt emitted before any trial]
- `test_reflexion_emits_reflexion_trial_per_trial` — two-trial run produces two
  `"reflexion_trial"` slots. [Silent Failure: might emit zero or one]
- `test_reflexion_emits_reflexion_reflection_per_failing_trial` — two-trial
  run with one failure produces one `"reflexion_reflection"` slot between the
  two trial slots. [Silent Failure: reflection emitted at wrong position]
- `test_reflexion_slot_order_matches_template` — full three-trial run's
  recorder passes `ReflexionContextWindowTemplate(max_trials=3,
  failing_trials=2).passes(recorder)` is `True`. [Integration: recorder
  sequence matches template]
- `test_reflexion_early_success_no_reflection_slot` — if first trial succeeds
  (`isDone`), no `"reflexion_reflection"` slot is emitted. [Edge Case: early
  exit does not pollute trace with extra reflection]
- `test_reflexion_null_recorder_does_not_crash` — running Reflexion with
  default `NullRecorder` completes without error. [Hidden Assumption: NullRecorder
  is safe in production path]
- `test_reflexion_trial_index_stored_in_slot_event` — `events()` shows
  `iteration=0` for the first trial slot, `iteration=1` for the second. [Hidden
  Assumption: trial_index is correctly passed to append]

### Integration Tests

- Full three-trial Reflexion run using `FakeRunner` (sequences of canned
  `FakeResponse` objects), verifying that `ContextWindowRecorder.slots()`
  matches `ReflexionContextWindowTemplate(max_trials=3).expected_slots` exactly.
- Single-trial success (no reflections) verifies no `"reflexion_reflection"`
  slots appear and template with `failing_trials=0` passes.
- Two trials where both exhaust `max_iterations` verifies reflection is emitted
  after the first trial.

### Manual / QA Test Cases

1. Given a new `ContextWindowRecorder` and an `AgentRuntime` configured with
   `algorithm=ContextWindow.preset.reflexion`, when `arun` is called with a
   `FakeRunner` that returns two `max_iterations` stops then one `isDone`, then
   `recorder.slots()` is
   `("system_prompt", "reflexion_trial", "reflexion_reflection",
   "reflexion_trial", "reflexion_reflection", "reflexion_trial")` — [Integration]
2. Given a `ReflexionContextWindowTemplate(max_trials=3)` and the recorder from
   case 1, then `template.passes(recorder)` is `True` — [Silent Failure:
   template might pass when trace has wrong length]
3. Given a `NullRecorder` passed to `AgentRuntime`, when any Reflexion run
   completes, then no exception is raised and all existing test assertions on
   `StrategyResult.metadata` still hold — [Hidden Assumption: NullRecorder does
   not interfere with metadata]
4. Given a `ContextWindowTemplate(["system_prompt", "wrong_slot"])` and a
   correct Reflexion recorder, then `template.validate(recorder)` returns at
   least one `TemplateViolation` with `position=1, expected="wrong_slot"` —
   [Silent Failure: validator might silently pass mismatched templates]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python stdlib `dataclasses` | 3.10+ | SlotEvent, TemplateViolation | None — already used throughout SDK |
| Python stdlib `abc` | 3.10+ | RecorderBase abstract class | None |

No new third-party packages are required.

---

## 12. Rollout & Deployment

- No feature flags. The recorder defaults to `NullRecorder` and adds no
  observable behavior change to existing code paths.
- Not a breaking change. The `recorder` parameter is keyword-only with a
  default.
- No deployment ordering concern — this is a pure library change.
- Rollback: revert the PR. No migrations, no state.

---

## 13. Open Questions

- [ ] Should base runtime slots (`agent_iteration`, `tool_call`, `middleware`)
  be emitted from `AgentRuntime._arun_once` in Phase 1 or deferred to Phase 2?
  Current decision: Phase 2. Phase 1 only instruments Reflexion's
  algorithm-specific slots.
- [ ] Should `ContextWindowRecorder` be thread-safe? Current decision: No.
  Async agent runs are sequential within a single run. If multi-threaded
  use becomes needed, a `threading.Lock` can be added later.
- [ ] Should templates be exportable from the root `vidbyte` namespace?
  Current decision: No. Templates are test utilities, not user-facing API.

---

## 14. Alternatives Considered

### Alternative 1: Validate StrategyResult.metadata instead of slot sequence

- **What:** Assert that `result.metadata["reflexion"]["trial_count"] == 3`
  rather than validating an ordered slot list.
- **Why rejected:** Metadata counts do not verify structural ordering. An
  implementation that runs all reflections before any trials would produce
  correct counts but incorrect structure.

### Alternative 2: External tracing (LangSmith/LangChain) for slot capture

- **What:** Use LangSmith or LangChain's tracing SDK to capture and compare
  execution traces.
- **Why rejected:** Introduces a third-party dependency and requires network
  access. The recorder achieves the same result in process with zero
  dependencies and deterministic behavior in tests.

### Alternative 3: Infer slot types from provider message content

- **What:** After a run, parse the raw provider messages list and classify each
  message by content heuristics.
- **Why rejected:** Inference is fragile. Message content changes with prompt
  overrides, provider format changes, and algorithm updates. Explicit emit-point
  instrumentation is the only reliable approach.

### Alternative 4: Single flat recorder shared across all levels

- **What:** Have `AgentRuntime._arun_once` emit all base slots interleaved with
  algorithm slots in one flat list.
- **Why rejected:** For Phase 1, the Reflexion template only needs
  algorithm-level slots. Interleaving base slots would make the Reflexion
  template depend on the exact number of tool calls and model iterations in
  each trial, making tests fragile and templates hard to construct. Phase 2
  can add base slot emission once the algorithm-level templates are proven.
