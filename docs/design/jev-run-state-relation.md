# Design Doc: Jev Run-State Relationship

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-30
**Last Updated:** 2026-09-30

---

## 1. Overview

This change adds an opt-in Jev preflight preset that recognizes whether a new user request has a substantive relationship to the work or identifiable content in the current `JevRunStateRecord`. A related request keeps that record unchanged, even when it asks for a different action or deliverable about the same identifiable project, entity, or artifact. An unrelated request has no identifiable connection beyond broad topical overlap, so the existing run-state agent creates a new record from the current message. The request still enters JevAgent's ordinary runtime loop as the current message, and the feature does not compact, restore, or rewrite the main conversation history.

---

## 2. Goals & Non-Goals

### Goals

- Add the fixed opt-in `JevPreflightPreset.RUN_STATE_RELATION` with one registered `JevPreflightQuestionKey.RUN_STATE_RELATION` question.
- Ask the relationship question only when the gate receives an existing run-state record; on a first run, initialize state normally without issuing or recording a relation question.
- Combine the current request and a JSON-safe projection of the existing record into the already configured single Jev preflight request. Omit the usage rollup from that projection.
- Keep the record when Jev identifies a substantive relationship, or when the relation answer is unavailable; generate a replacement through `JevRunState.begin` only when no record exists or Jev identifies no substantive relationship.
- Clear a stale prior record before attempting replacement so a typed run-state generation failure cannot leave the unrelated record presented as current.
- Retain current per-run initialization for agents that have not enabled the new preset.
- Build the run-state facade when the preset is enabled even if `JevContinualSettings.checks` is empty, and build a continuation only when at least one done check is enabled.
- Expose the latest relation outcome through the existing `JevAgent.response.results` entry for the preset, without adding metadata or generic response fields.
- Add deterministic tests and an executable focused verification script for the relationship question, gate, runtime, failure cases, response reset, and legacy behavior.

### Non-Goals

- Do not define or change what the main agent retains in its conversation history.
- Do not compact context, restore checkpoints, fork history, or otherwise mutate the main conversation history.
- Do not add a generic hook, user-defined question surface, relation threshold setting, or runtime preset branch.
- Do not change run-state prompts, done-check question content, continuation policy, specialist routing, or TypeSafe provider serialization.
- Do not make Jev plan, count, compare dates, or generate replacement state. The existing generative run-state agent remains responsible for writing a replacement record.
- Do not require a live TypeSafe call for tests.

---

## 3. Background & Context

`JevRuntime.arun` currently starts a fresh response, calls `JevPreflightGate.pass_(message)`, and then invokes `JevRunState.begin(message)` whenever continual done checks are enabled. `begin` clears that state agent's prior record and history before generating a new record. This is correct for today's per-run semantics, but it provides no way to retain state when a later request has an identifiable relationship to the represented work or content.

The gate already combines every enabled fixed-question preset and any specialist question into one Jev request. Fixed question content and preset policy belong in `vidbyte/lib/jev/`; the gate's action belongs in `vidbyte/agents/jev/gate/`; outcomes are written by `JevResponse`. The existing `JevRunState` is built only when continual checks are enabled, while the new preset also needs it to write and retain task state when there are no done checks.

The Jev question house style requires one recognition judgment, a structured brief and mirrored criteria, an explicit way to classify empty input, one string per section, and at least 2,000 meaningful tokens across the question. The new question therefore defines a substantive relationship with concrete references and shared identifiable objects, while distinguishing those from generic topical overlap and wholly separate requests. Its fixed threshold is 0.5, the existing neutral Noul yes threshold; no labeled relation dataset exists in this change, so that value is documented as an initial policy.

---

## 4. Requirements

### Functional Requirements

1. Add the fixed `RUN_STATE_RELATION` preflight preset and the uniquely named question key `run_state_relation` in the existing Jev enums, preset map, constants, question registry, and gate `match`.
2. Define the new question as: “Does `request` have any substantive relationship to the work or identifiable content in `run_state`?” Related cases include follow-ups, corrections, clarifications, explicit references to record content, and requests about the same identifiable project, entity, or artifact, even when the requested action or deliverable changes. Generic topical overlap without an identifiable connection and wholly separate subjects or objects are unrelated. The question does not ask whether the request is easy, how many actions it contains, or what to plan.
3. On each gate pass, reset `run_state_related` to `None`. Set it to the preset's scored pass/fail only when a record was provided and the relation answer is available; leave it `None` for an unavailable answer or when there is no record to compare.
4. When the relation preset is enabled and a record exists, add exactly two named fields to the combined Jev state: the current `request` and a JSON-safe serialization of the record's semantic fields. Exclude usage accounting. Other enabled presets and specialist choice remain in the same request.
5. When there is no record, omit the relation question and relation state field from the Jev call. Do not record an unavailable or passed relation result for this not-applicable first-run case.
6. `JevRunStateRelation.begin(message)` calls `super().begin(message)` if its record is absent or the relation gate explicitly returned false. Otherwise it preserves its record, original request, and rendered form, and writes the record to the new run's `JevResponse` after `JevResponse.start` has reset it.
7. A failed replacement follows the existing typed `VidbyteSdkError` fail-open behavior, which clears the record before the attempt and therefore cannot leave an unrelated old record looking current. Cancellation and non-SDK failures continue to propagate.
8. Build `JevRunStateRelation` when the relation preset is enabled, including when no done checks are enabled. Create `JevDoneContinuation` only when continual done checks are enabled.
9. Pass the current message through the existing inherited main-agent loop unchanged. A related run checks or continues against the preserved original objective when done checks are enabled; it does not replace the original request held by the run-state record.
10. When the relation preset is disabled, retain existing `JevRunState.begin` per-run semantics and existing no-run-state behavior.

### Non-Functional Requirements

- Relation work adds no TypeSafe call when the preset is disabled or when there is no existing record. When requested alongside other preflight questions, it adds one question to their existing request.
- The relation state projection contains only fields needed to identify the existing task; it excludes usage rollups and conversation history.
- Unavailable Jev answers preserve the record as requested, while failed replacement generation leaves no stale record. Do not catch broad exceptions to choose either policy.
- The implementation follows the SDK's typed dependency layers, question-writing rules, one-line signatures, method comments, source lint, and full CI gate.

---

## 5. High-Level Design

`JevPreflightGate` receives the current `JevRunStateRecord` explicitly from `JevRuntime`. When the opt-in relation preset is active and a record exists, the gate adds a JSON-safe projection of that record beside the current request and includes the relation question in the same `JevDecisionRequest` as all other enabled preflight questions. With no record, the gate skips that question entirely; first-run initialization remains the work of `JevRunState.begin`.

`JevAgent` builds a `JevRunStateRelation` subclass when the relation preset is enabled. The subclass retains the gate reference built by the same `JevAgent` and overrides `begin(message)`: a missing record or an explicit unrelated verdict delegates to the existing generator; a related or unavailable verdict keeps the existing typed record and reports it into the newly reset response. `JevRuntime` continues to call `begin` at the same point in its normal flow, and the main loop always receives the current message. The legacy `JevRunState` class is used unchanged when the preset is off.

```text
JevRuntime.arun(message)
  -> response.start(message)
  -> gate.pass_(message, existing run_state.record)
       -> if record + preset: one combined Jev request over {request, run_state}
       -> run_state_related = True | False | None
  -> if gate passes and no specialist: run_state.begin(message)
       -> missing record or False: existing generator writes a new record
       -> True or unavailable: retain record and report it
  -> inherited main-agent loop receives the current message
```

---

## 6. Detailed Design

### 6.1 Run-State Relationship Question and Preset

**File(s):** `vidbyte/lib/jev/preflight/run_state_relation.py`, `vidbyte/lib/jev/preflight/preflight.py`, `vidbyte/lib/jev/preflight/__init__.py`, `vidbyte/lib/jev/presets.py`, `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`
**Type:** New file and modified files

#### What it does

Defines one frozen preflight question and registers it under the opt-in preset. The brief recognizes substantive links to any identifiable work or content in `run_state`, including a different action about the same project or artifact, and distinguishes those from generic topical overlap or wholly separate subjects. It focuses on `request` and the named semantic fields of `run_state`. Each rendered question has at least 2,000 meaningful tokens across the brief, criteria, and gap, and every section uses one standalone string.

#### Interface / API

```python
class JevPreflightPreset(str, Enum):
    RUN_STATE_RELATION = "run_state_relation"

class JevPreflightQuestionKey(str, Enum):
    RUN_STATE_RELATION = "run_state_relation"

JEV_RUN_STATE_RELATION_THRESHOLD = 0.5

@dataclass(frozen=True)
class RunStateRelationQuestion(JevPreflightQuestion):
    ...
```

The question is registered through `JevPreflightRegistry` and its preset definition names the question key and threshold. No new public runtime-setting field is added.

#### Logic / Algorithm

1. Build a single Noul question whose positive side means the new request has a substantive connection to identifiable work or content in the existing record, including a different action about the same concrete project, entity, or artifact.
2. Define an empty message or a message with no task as unrelated; define generic same-topic requests without an identifiable connection, and wholly separate subjects or objects, as unrelated.
3. Describe follow-up, clarification, correction, explicit references, and requests about the same identifiable project or artifact as related even when the requested purpose, action, or deliverable differs.
4. Add the question to `JevPreflightRegistry` and the `RUN_STATE_RELATION` preset definition.
5. Use the named 0.5 threshold, with equality treated as related by the existing inclusive Noul comparison.

#### Edge Cases & Error Handling

- No existing record means the question is not asked and no relation result is written.
- A broad shared topic without an identifiable link must be classified as unrelated; a request about the same concrete project or artifact can be related even when it asks for a new action or deliverable.
- A vague or empty request is not evidence that it relates to the old objective.
- Missing or malformed answers are handled as unavailable by `DecisionModelHelper.score_noul`; the gate records the existing preset's unavailable result and leaves its relation flag `None`.

### 6.2 Gate Input, State Projection, and Outcome

**File(s):** `vidbyte/agents/jev/gate/gate.py`
**Type:** Modified file

#### What it does

Accepts the optional typed existing run-state record in `pass_`, `combine`, and `_ask`; resets `run_state_related` on every pass; includes the relation question and record projection only when applicable; and acts on the relation preset in the existing `match` statement.

#### Interface / API

```python
def combine(self, message: str, run_state: JevRunStateRecord | None = None) -> JevDecisionRequest | None: ...
async def pass_(self, message: str, run_state: JevRunStateRecord | None = None) -> bool: ...
async def _ask(self, message: str, run_state: JevRunStateRecord | None = None) -> Mapping[str, JevAnswer] | None: ...
```

`run_state_related: bool | None` is gate-owned state, not a generic hook or a new response-record field. Serialization explicitly projects `goal`, `objective`, `mission`, `what_not_to_do`, and optional typed request sections; it omits `usage`. Existing `request` is always present in a preflight request.

#### Logic / Algorithm

1. At the start of `pass_`, set `specialist = None` and `run_state_related = None`.
2. Ask `_ask(message, run_state)` once. `combine` skips the relation question if no record exists; when present, append it to the ordinary enabled questions and add the `run_state` projection to the same structured state.
3. Skip `_score` for `RUN_STATE_RELATION` when no record exists, so the response does not report an inapplicable check.
4. For an available relation outcome, set `run_state_related = outcome.passed`; for an unavailable result, leave it `None`. Record outcomes through `JevResponse.preset` as for existing presets.
5. Keep the new `case` inside `pass_`; do not add preset branching to `JevRuntime`.

#### Edge Cases & Error Handling

- No relation preset means the optional record does not alter the existing preflight state or questions.
- Relation-only preflight with no record builds no decision request and remains a normal initialization.
- A missing credential, provider failure, request error, missing answer, or non-Noul answer follows current fail-open handling and produces `run_state_related is None`.
- Serialization handles absent optional record sections as JSON null and converts tuples to JSON arrays. It never attempts to serialize usage dataclasses or conversation history.

### 6.3 Run-State Facade and Agent Construction

**File(s):** `vidbyte/agents/jev/done/relation.py`, `vidbyte/agents/jev/done/__init__.py`, `vidbyte/agents/jev/agent.py`
**Type:** New file and modified files

#### What it does

Adds a narrow `JevRunStateRelation` subclass that adapts the existing `JevRunState.begin` behavior only when the named relation preset is enabled. `JevAgent` builds it even if no done checks are enabled; its continuation remains absent unless done checks are enabled.

#### Interface / API

```python
class JevRunStateRelation(JevRunState):
    def __init__(self, settings: JevAgentSettings, runtime_settings: JevRuntimeSettings, response: JevResponse, preflight: JevPreflightGate) -> None: ...
    async def begin(self, request: str) -> None: ...
```

The subclass lives in `done/relation.py` and is exported by `done/__init__.py`; it is an internal implementation class, not a new `JevAgent` constructor option.

#### Logic / Algorithm

1. Retain the already constructed `JevPreflightGate` reference in the subclass.
2. If `record is None` or `preflight.run_state_related is False`, call `super().begin(request)`. The existing method clears its prior record before generation and catches only typed SDK failures.
3. Otherwise, keep `record`, `request`, and `rendered` unchanged and report `response.run_state(record)` into the current response.
4. In `JevAgent.__init__`, choose this subclass when `RUN_STATE_RELATION` is in validated preflight settings; otherwise construct the existing `JevRunState` only when done checks are enabled.
5. Build `JevDoneContinuation` only when the constructed run-state object has enabled done checks.

#### Edge Cases & Error Handling

- With the relation preset but no done checks, state still initializes and is retained, but no continuation object or done-check request is built.
- With no relation preset, no subclass changes current per-run state-generation semantics.
- On replacement generation failure, report no run state rather than the previous unrelated one.
- Cancellation and non-SDK errors propagate as they do from the existing `begin` method.

### 6.4 Runtime Handoff and Main Loop

**File(s):** `vidbyte/agents/jev/runtime.py`
**Type:** Modified file

#### What it does

Provides the current record to the preflight gate and otherwise preserves the existing runtime order and main-agent loop.

#### Interface / API

```python
await self.preflight.pass_(message, run_state=None if self.run_state is None else self.run_state.record)
```

#### Logic / Algorithm

1. Reset the response as today.
2. Call `pass_` with the current typed record if a run-state facade exists, else `None`.
3. If the gate passes and no specialist is selected, call the run-state facade's `begin(message)` as today; the selected implementation controls retain-or-replace behavior.
4. Continue passing the unchanged current `message`, metadata, options, and trace context through the ordinary loop.

#### Edge Cases & Error Handling

- A closed existing gate still prevents the main loop from running.
- A related/unavailable decision does not skip or rewrite the current user message.
- No relation preset preserves current run-state and runtime behavior.
- The runtime does not import question keys or branch on preflight presets.

### 6.5 Focused Tests and Verification Script

**File(s):** `tests/test_jev_run_state_relation.py`, `scripts/test-jev-run-state-relation.py`
**Type:** New files

#### What it does

The unit/integration tests use the production question, registry, preset, gate, runtime, response, and relation facade with scripted decision and generative runners. The executable script loads the focused suite, prints a `PASS` or `FAIL` label per case, prints `X/Y tests passed`, and exits non-zero on failure.

#### Interface / API

```text
python scripts/test-jev-run-state-relation.py
```

#### Logic / Algorithm

1. Pin question structure, single-string sections, answer-key registration, and the 2,000-token content floor.
2. Verify the relation question uses only current request and serialized record state and that usage is omitted.
3. Exercise applicable and not-applicable gate outcomes, including missing or failed decision replies.
4. Exercise JevRunStateRelation through JevRuntime for related retention, unrelated replacement, replacement failure, fresh responses, done-check behavior, and the disabled legacy path.

#### Edge Cases & Error Handling

- The script inserts the repository root for direct execution from any working directory.
- Tests use no live provider calls and clear any environment credential they need to isolate.
- Cancellation tests confirm cancellation is not swallowed by relation logic.
- The script runs all test cases in the new focused test module and reports each case independently.

---

## 7. Data Model Changes

### 7.1 Preflight Vocabulary and Fixed Question

**Change type:** Modified

```python
JevPreflightPreset.RUN_STATE_RELATION = "run_state_relation"
JevPreflightQuestionKey.RUN_STATE_RELATION = "run_state_relation"
JEV_RUN_STATE_RELATION_THRESHOLD = 0.5
```

The existing `JevPresetResult` and `JevAgentResponse.results` hold the relation decision; no record schema, response field, persisted data, or migration is added.

**Migration strategy:**

- Forward migration: additive enum and preset values; callers enable the preset explicitly.
- Rollback plan: remove the new enum members, preset, question, gate behavior, and subclass selection. Existing configuration has no reference to the opt-in value and requires no data migration.

---

## 8. API Changes

N/A - There is no HTTP endpoint. The user-facing addition is an opt-in value in the existing `JevRuntimeSettings.preflight` tuple. Internal gate methods gain an optional typed `JevRunStateRecord` argument with a default of `None`, preserving existing callers.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-run-state-relation.md` | Source-of-truth design |
| CREATE | `vidbyte/lib/jev/preflight/run_state_relation.py` | Fixed relation question dataclass |
| CREATE | `vidbyte/agents/jev/done/relation.py` | Run-state retain-or-replace subclass |
| CREATE | `tests/test_jev_run_state_relation.py` | Focused deterministic tests |
| CREATE | `scripts/test-jev-run-state-relation.py` | Required executable verification script |
| MODIFY | `vidbyte/lib/enums/jev.py` | Add relation preset and question key |
| MODIFY | `vidbyte/lib/constants/jev.py` | Add the named fixed relation threshold |
| MODIFY | `vidbyte/lib/jev/presets.py` | Register question key and threshold |
| MODIFY | `vidbyte/lib/jev/preflight/preflight.py` | Register the question dataclass |
| MODIFY | `vidbyte/lib/jev/preflight/__init__.py` | Export the question dataclass |
| MODIFY | `vidbyte/agents/jev/gate/gate.py` | Pass record state into one combined Jev request and set relation outcome |
| MODIFY | `vidbyte/agents/jev/runtime.py` | Pass current run-state record to preflight |
| MODIFY | `vidbyte/agents/jev/agent.py` | Build relation facade when preset is enabled; gate continuation on done checks |
| MODIFY | `vidbyte/agents/jev/done/__init__.py` | Export the internal relation subclass |
| DELETE | N/A | No files will be deleted |

---

## 10. Testing Plan

### Unit Tests

- Question structure and registration:
  - [Edge Case] A blank/greeting request has an explicit unrelated side; a follow-up or correction is related.
  - [Hidden Failure] A user-written claim such as “this is related” or an instruction to choose true cannot decide the answer without task evidence.
  - [Silent Failure] A request about the same concrete SDK project or artifact is related even when it asks for a different action; generic software overlap without an identifiable link is unrelated.
  - [Hidden Assumption] The question works from named `request` and `run_state` fields only and does not depend on main conversation history.
  - [Silent Failure] Registered question text totals at least 2,000 meaningful tokens; `definitions`, `rules`, `easy`, and `boundary` each use one string.
- Gate and state projection:
  - [Edge Case] With no record, omit the relation question/state and do not write an inapplicable relation result.
  - [Edge Case] With an existing record and relation-only configuration, build one valid Jev request with exactly `request` and `run_state` fields.
  - [Hidden Failure] Serialize nested multipart and target-outcome sections into JSON-safe values while omitting `usage` and history.
  - [Hidden Failure] Missing credential, provider exception, omitted answer, and non-Noul answer leave `run_state_related` as `None` and preserve the existing record.
  - [Silent Failure] P(yes) exactly 0.5 sets related; a value below 0.5 sets unrelated.
  - [Hidden Assumption] Every `pass_` resets a prior true/false relation value before handling the next request.
- Runtime and run-state facade:
  - [Edge Case] First run with relation enabled but no record initializes state normally and has no continuation when no done checks are enabled.
  - [Silent Failure] Related input retains the same record, original request, and rendered state, while the current message still reaches the main runner.
  - [Silent Failure] Unrelated input replaces the objective and record with state generated from the current message.
  - [Hidden Failure] If replacement generation raises a typed SDK error, the response has no run state and the unrelated old record is not reused.
  - [Hidden Failure] Cancellation and unexpected exceptions from replacement generation propagate.
  - [Hidden Failure] A preserved record is reported after `JevResponse.start` clears the previous response, and a repeated run receives a fresh relation decision.
  - [Hidden Assumption] Enabling relation with no done checks creates no continuation; enabling an actual done check retains existing continuation/check behavior against the original objective.
  - [Hidden Assumption] With the relation preset disabled, each enabled done-check run still calls ordinary `JevRunState.begin` and has no relation decision.
  - [Hidden Assumption] The relation path does not clear or rewrite main-agent history; existing history plus the current message follows standard runtime behavior.

### Integration Tests

- The focused script runs every test in `tests/test_jev_run_state_relation.py` with production settings validation, registry, gate, JevRuntime, and response wiring, while scripted runners replace only external model boundaries.
- Run `python scripts/test-jev-run-state-relation.py`, then `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py` from the worktree.
- Verify `vidbyte.__file__` resolves to the worktree before Python verification; use the worktree absolute path on `PYTHONPATH` or an isolated venv to avoid changing the shared editable install.
- Live TypeSafe calls are excluded; all provider responses are scripted.

### Manual / QA Test Cases

1. Given an opted-in JevAgent with no run-state record, run a first request and confirm the relation question is absent while a normal run-state record is created.
2. Given an existing objective and a related follow-up, confirm Jev sees the current message and record, the record is retained, and the main agent receives only the current message through its ordinary loop.
3. Given an existing record about a concrete project and a different action concerning that same project, confirm Jev returns related and the record remains unchanged; given only generic topic overlap without a concrete link, confirm Jev returns unrelated and a replacement record is built from the new request.
4. Given an existing record and an unavailable relation decision, confirm the record remains visible on the latest response and no replacement state generation occurs.
5. Given the preset disabled, confirm current per-run run-state initialization remains unchanged.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| TypeSafe Jev | Existing configured System One endpoint | Classify relationship when a record exists and the preset is enabled | Calibration may vary; unavailable answers intentionally preserve the record |
| Existing generative provider | Existing JevAgent provider/model | Write the initial or explicitly requested replacement run state | A typed provider failure leaves replacement state unavailable rather than reusing stale state |
| No new package dependency | N/A | Uses existing typed Jev and agent infrastructure | N/A |

---

## 12. Rollout & Deployment

- The capability is opt-in through `JevPreflightPreset.RUN_STATE_RELATION`; default JevAgent behavior remains unchanged.
- A relation question is asked only when both the preset and an existing record are present.
- The initial fixed threshold is 0.5, inclusive. A labeled evaluation set can justify a later change without adding a user-facing threshold setting.
- Rollback is a code revert. There are no persisted schema changes, external resources, or conversations rewritten by the feature.

---

## 13. Open Questions

No unresolved implementation decisions. The 0.5 relation threshold is intentionally an initial uncalibrated policy; building and evaluating a labeled relationship set can be a follow-up if production evidence warrants it.

---

## 14. Alternatives Considered

### Alternative 1: Always initialize a new run state for every run

- What: Keep the current behavior regardless of the existing record.
- Why rejected: It discards the original objective on related requests, which is the behavior this opt-in capability addresses.

### Alternative 2: Ask the relation question when no record exists

- What: Send the relation question with an empty or absent prior state and treat it as a passing first run.
- Why rejected: There is nothing to relate to. Skipping the question avoids an unnecessary decision call and avoids reporting a fabricated relation result.

### Alternative 3: Carry or rewrite the main conversation history to retain the objective

- What: Compact, restore, or manually edit conversation history when Jev considers a request related.
- Why rejected: The typed run-state record is the existing objective contract; changing history would add a second state mechanism and violate the requested runtime boundary.

### Alternative 4: Add relation inference to `JevRuntime`

- What: Branch in `JevRuntime.arun` on `JevPreflightPreset.RUN_STATE_RELATION` and score answers there.
- Why rejected: The repository's JEV convention keeps fixed-preset matching and actions in `JevPreflightGate`; the runtime passes typed state and delegates.
