# Design Doc: Jev Mid-Run Problem Repair Gate

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-29
**Last Updated:** 2026-09-29

---

## 1. Overview

Add an opt-in `PROBLEMS_RESOLVED` done check to JevAgent. At each finish attempt, the handoff extracts problem episodes from the agent's run, records attempted repairs and verification evidence, and adds one required item for completion of the original request after repairs. Jev judges each problem and the completion item separately in the existing combined request. Failed items send the main agent back through the same loop with a focused repair list; after fixing them, it returns to the original request and completes any remaining work before finishing again.

---

## 2. Goals & Non-Goals

### Goals

- Add a named `JevDoneCheck.PROBLEMS_RESOLVED` capability selectable through `JevContinualSettings.checks`.
- Derive problem items from the current finish attempt's observed responses and tool calls; do not predict problems in the pre-run state.
- Require the handoff to report problems observed in the run, their repairs, relevant revalidation, and completion of the original request after repair.
- Have Jev evaluate the compiled evidence and have `JevDoneContinuation` resume the same loop with the original request and specific missing work when the check fails.
- Preserve existing done-check behavior, one-request batching, response reporting, continuation limits, and fail-open handling for unavailable run-state, handoff, or Jev calls.
- Add deterministic tests and a focused executable verification script for success, repair, repeat, and failure cases.

### Non-Goals

- Automatically detect or remediate errors during tool execution; the main agent remains responsible for repairs.
- Retry failed tools, commands, tests, or model calls through a new runtime hook.
- Continue indefinitely, start a fresh main-agent loop, or alter existing continuation limits.
- Enable the new check by default or change the existing empty default for `JevContinualSettings.checks`.
- Judge hypothetical issues that did not occur in the observed run.

---

## 3. Background & Context

JevAgent already supports named done checks. `JevRunState` writes request-derived state before the main loop; `JevHandoff` compiles evidence and can derive items from the completed run, as the current CLAIMS check does; one combined Jev request judges all enabled checks; and `JevDoneContinuation` appends a focused user message to the same loop when a check fails. The `jev-continuation` skill requires one question per item, dynamic items to come from the handoff when they cannot be known before work, and no branch in `JevRuntime`.

The current multi-part check covers whether requested deliverables were completed; CLAIMS checks whether final-answer claims are supported. Neither separately requires problems encountered during the run to be repaired and revalidated before the agent finishes the original request. This check follows CLAIMS's post-run-derived pattern: the handoff creates one item per observed problem and one required original-request-completion item, without predicting problems in the pre-run state.

Constraints: JEV records and enums belong in `vidbyte/lib`; question content belongs in `vidbyte/lib/jev/done/`; orchestration belongs in the existing Jev done-check and continuation modules; feature results are recorded through `JevResponse`; questions must follow the asking-jev-questions skill; and all checks share one Jev request per finish attempt.

---

## 4. Requirements

### Functional Requirements

1. Register `JevDoneCheck.PROBLEMS_RESOLVED` with a fixed question key and threshold; callers enable it through `JevContinualSettings(checks=(JevDoneCheck.PROBLEMS_RESOLVED,))`.
2. At each finish attempt, derive problem items from the current main-agent responses and tool calls; do not predict problems in the pre-run state.
3. Include one required item judging whether the original request was completed after any problem repairs, even when no problems were encountered.
4. Compile evidence from the main agent's current responses, tool calls, and final answer. A repair counts as full only when the evidence shows an appropriate successful follow-up; a repair claim without its result is insufficient.
5. A problem is unresolved when the run shows an encountered error, failure, blocker, or failed validation without evidence of a complete repair and relevant successful revalidation. Do not invent hypothetical problems.
6. Include the new check's per-item state and questions in the existing single Jev request with all other enabled checks. Report its result through `JevAgent.response.done`.
7. On failure with a usable handoff and remaining continuation budget, send the main agent the original request, run state, handoff, failed question, and a Focus entry naming unresolved repairs and the original work to complete afterward. Continue in the same loop.
8. Re-evaluate the full run at every finish attempt, including after a continuation. The latest result is reported; at the configured cap, the answer stands as it does for existing checks.
9. Preserve fail-open behavior when handoff compilation or Jev evaluation is unavailable, and preserve the disabled path when the check is not enabled.
10. Do not change `JevRuntime`, `JevAgent` constructor behavior, the public settings shape, or the existing continuation cap. Update only the shared continuation prompt instructions to explicitly return to the original request after repairs.

### Non-Functional Requirements

- No new dependency, network endpoint, persistent storage, or database migration.
- Reuse the current per-run state and context window; do not retain data across runs.
- Keep problem details in existing response and handoff records; do not log or expose credentials.
- Make no live provider calls in deterministic tests.
- Do not raise lint baselines or weaken validation.

---

## 5. High-Level Design

Represent this behavior as a new dynamic done check rather than a new runtime continuation class. Problems cannot be enumerated before the run, so `JevRunState` adds no predicted section. `JevHandoff` adds a `problems_resolved` section containing one typed item per observed problem episode and one required original-request-completion item. Each item has five named context sections so Jev can make one recognition judgment about that item. Handoff IDs are validated for uniqueness, and one question is built per item.

At every finish attempt, the handoff is regenerated from the full run window. The check's fixed question asks whether the evidence shows the item is satisfied: each problem item requires a full repair and successful relevant revalidation; the required request item requires the original request to be completed after any repairs. A failed result uses the existing `JevDoneContinuation` path: it explains the failure and focuses the main agent on unresolved repairs, then returning to the original task. The subsequent finish attempt recompiles evidence and asks all enabled done checks together in one request.

```text
main agent finish attempt
        |
        v
JevHandoff: observed problems + attempted repairs + verification + original-task result
        |
        v
JevRunState: request-derived state + other enabled check state
        |
        v
one combined Jev request
        | pass                         | fail and budget remains
        v                              v
return current answer       append focused repair message to same loop
                                       |
                                       v
                         repair -> revalidate -> complete original request
                                       |
                                       v
                               check again at finish
```

---

## 6. Detailed Design

### 6.1 Check key, threshold, and question registry

**File(s):** `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/jev/done/problems_resolved.py`, `vidbyte/lib/jev/done/done.py`, `vidbyte/lib/jev/done/__init__.py`, `vidbyte/lib/jev/done/README.md`
**Type:** Modified and new file

#### What it does

Defines and registers the opt-in check, an item-kind enum, its question key and threshold, and its fixed `JevDoneQuestion` implementation. Items come from the post-run handoff, following the repository's `CLAIMS` pattern.

#### Interface / API

```python
JevDoneCheck.PROBLEMS_RESOLVED = "problems_resolved"
JevDoneQuestionKey.PROBLEMS_RESOLVED_FIXED = "problems_resolved.fixed"
JevContinualSettings(checks=(JevDoneCheck.PROBLEMS_RESOLVED,))
```

The question uses the existing `JevBrief`, `JevCriterion`, and `JevDoneQuestion` contracts. Each item state has five named context sections: problem identity, scope, kind, repair, and the one assertion being judged. Its instructions define an encountered problem as an observed error, failure, blocker, or failed validation; distinguish an attempted repair from a verified repair; and require successful relevant revalidation. A separate required item checks original-request completion after repairs. The question and gap follow the full question-writing skill, including mirrored criteria and the 2,000-token minimum.

#### Logic / Algorithm

1. Register the check, item-kind enum, and question key in existing JEV enums.
2. Add named field constants, a threshold, and register the question and threshold in `JevDoneRegistry`.
3. Export the question and document the module in the done-check README.
4. Keep question content in the shared JEV layer; do not add a prompt asset.

#### Edge Cases & Error Handling

- No observed problems still produces the required original-request-completion item.
- A repair attempt with no successful follow-up is unresolved.
- An omitted or ambiguous verification result does not count as a verified fix.
- Jev unavailability remains fail-open through the existing done-check runner.

### 6.2 Dynamic handoff items and combined state

**File(s):** `vidbyte/lib/enums/jev.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/agents/jev/done/run_state.py`, `vidbyte/agents/jev/done/handoff.py`, `vidbyte/lib/jev/done/multi_part.py`
**Type:** Modified

#### What it does

Adds a handoff-only section for post-run-derived problem items. Each item carries five named state sections and evidence; one reserved item always represents original-request completion. `JevRunState._section` projects each item into the shared Jev request. `DONE_STATE` is updated so every done-question brief accurately describes the optional `problems_resolved` field alongside `deliverables` and `claims`.

#### Interface / API

Add a `JevProblemCheckItemType` enum with `PROBLEM` and `REQUEST_COMPLETION`, typed item and handoff records, and an optional `problems_resolved` field on `JevHandoffRecord`. Each item has a stable validated ID, kind, five context sections, evidence, and a handoff-only `missing` summary. Exactly one request-completion item is required; problem IDs must be unique and cannot collide with the reserved completion ID. There is no new field on `JevRunStateRecord`.

#### Logic / Algorithm

1. Add strict payloads and frozen records in `vidbyte/lib/dataclasses/jev.py`; keep parsing and conversion out of records.
2. Add the check to `JevHandoff._SECTIONS`; do not add a run-state schema section because problem episodes only exist after work.
3. Convert validated payloads in `JevHandoff._record`, validate unique IDs and exactly one request-completion item, and make invalid data unavailable.
4. Add one `JevRunState._section` case that projects each item's five context sections and evidence into the combined request, excluding `missing`.
5. Add one `_judge` case that scores all expected item IDs with `DecisionModelHelper.score_noul` using the registered threshold as both threshold and veto. Missing answers or unavailable inputs fail open.
6. Add one `_explain` case that names each unresolved problem and directs the main agent to repair, revalidate, and then complete remaining original-request work.
7. Update `DONE_STATE` to describe the dynamic optional state key truthfully for every combination of enabled checks.

#### Edge Cases & Error Handling

- Empty problem list is valid, but the handoff must still include the original-request-completion item.
- Duplicate IDs, a missing completion item, or repeated completion items invalidate the handoff.
- An incomplete original request is a separately failed item even if every observed problem is resolved.
- A missing question answer or provider error makes the check unavailable and fail-open.
- After the continuation cap, record the latest result and return the current answer.

### 6.3 Continuation wiring

**File(s):** `vidbyte/agents/jev/continuation/done.py`
**Type:** Modified

#### What it does

Adds the new check's failed-question explanation and focus text to the existing continuation message, and clarifies that after repairs the main agent returns to the original request and completes remaining work.

#### Interface / API

No new runtime hook. `JevDoneContinuation._explain(result)` adds one `JevDoneCheck.PROBLEMS_RESOLVED` match case and returns the existing `(failed, focus)` pair. The continuation prompt gains one instruction to return to the original request after repairs and finish all remaining requested work.

#### Logic / Algorithm

1. Name the question and Jev's negative answer for each failed dynamic item.
2. Include the handoff's unresolved problem and missing verification details.
3. Focus the main agent on fully repairing and validating each problem, then completing the original request.
4. Keep `JevRuntime` unchanged. The prompt update clarifies existing same-loop behavior without changing its placeholders.

#### Edge Cases & Error Handling

- An unavailable check never appears as a failed continuation.
- If there are no unresolved problems but original work is incomplete, Focus states that original completion remains required.
- The current same-loop history, tools, and budgets are preserved.

### 6.4 Tests, focused script, and guidance

**File(s):** `tests/test_jev_done.py`, `scripts/test-jev-problems-resolved.py`, `skills/jev-agent/SKILL.md`, `skills/jev-continuation/SKILL.md`, `vidbyte/agents/jev/README.md`
**Type:** Modified and new file

#### What it does

Adds deterministic coverage, an executable script for the focused verification cases, and instructions for the named capability in the JevAgent and continuation guides.

#### Interface / API

No production API beyond `JevDoneCheck.PROBLEMS_RESOLVED` and enabling it through existing `JevContinualSettings.checks`.

#### Logic / Algorithm

Tests use scripted generative and decision runners. The focused script directly loads the done-check test cases, prints a PASS/FAIL result per case, summarizes `X/Y tests passed`, and exits nonzero on any failure. The continuation prompt test pins the repair-then-original-request instruction.

#### Edge Cases & Error Handling

- Exercise a disabled check, empty issue set, malformed/mismatched handoff, missing Jev answer, and continuation cap.
- Assert a failed check resumes the same loop and that a later handoff sees the repair and original request completion.
- Ensure other enabled checks remain batched in one Jev request.

---

## 7. Data Model Changes

### 7.1 Jev problem-resolution handoff records

**Change type:** Modified

Add a typed handoff payload/record section containing observed problems, attempted repairs, verification evidence, a handoff-only missing summary, and a required original-request-completion item. Add the optional field to `JevHandoffRecord`; do not add a predicted problem field to `JevRunStateRecord`, persistent storage, migrations, or provider wire payload dictionaries to lib records.

**Migration strategy:** N/A - records are in-memory per-run data and no persisted schema is changed.

---

## 8. API Changes

N/A - no endpoint or constructor changes. The capability is selected using the existing `JevContinualSettings.checks` setting and is opt-in.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/enums/jev.py` | Add the done-check member, item-kind enum, and question key. |
| MODIFY | `vidbyte/lib/constants/jev.py` | Define the named threshold and shared item/state field names. |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Add strict handoff payloads, typed problem records, and the optional handoff field. |
| CREATE | `vidbyte/lib/jev/done/problems_resolved.py` | Define the fixed question for dynamic problem and request-completion items. |
| MODIFY | `vidbyte/lib/jev/done/done.py` | Register the question and threshold. |
| MODIFY | `vidbyte/lib/jev/done/__init__.py` | Export the question class. |
| MODIFY | `vidbyte/lib/jev/done/README.md` | Document the new question module. |
| MODIFY | `vidbyte/lib/jev/done/multi_part.py` | Keep the shared batched-state description true when the new dynamic state key is present. |
| MODIFY | `vidbyte/agents/jev/done/run_state.py` | Project dynamic item context, ask, and score the new check. |
| MODIFY | `vidbyte/agents/jev/done/handoff.py` | Compose, validate, and record dynamic problem evidence. |
| MODIFY | `vidbyte/agents/jev/continuation/done.py` | Add per-item failed-check and Focus text. |
| MODIFY | `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md` | Explicitly return to the original request after repairs and complete remaining work. |
| MODIFY | `vidbyte/agents/jev/README.md` | Document the new opt-in capability and dynamic item source. |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Export new records returned through `JevAgent.response`. |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export public Jev response record types. |
| MODIFY | `vidbyte/__init__.py` | Re-export public Jev response record types. |
| MODIFY | `tests/test_jev_done.py` | Cover schemas, question, evidence, decisions, and continuations. |
| CREATE | `scripts/test-jev-problems-resolved.py` | Run every new Section 10 case and report PASS/FAIL. |
| MODIFY | `skills/jev-agent/SKILL.md` | Document the new named done-check capability. |
| MODIFY | `skills/jev-continuation/SKILL.md` | Document dynamic problem items and the repair-then-original-task behavior. |
| CREATE | `docs/design/jev-mid-run-problem-repair-gate.md` | Record the design and verification plan. |

No files are deleted. The manifest therefore contains 3 creates and 18 modifications.

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] Construct `JevContinualSettings` with the new check, with no checks, with a bare string, and with a repeated check; confirm the existing validator accepts only the valid configurations.
- [Hidden Assumption] Confirm the new check is opt-in and the default configuration builds no run-state or handoff agent and makes no Jev request.
- [Edge Case] Build the handoff schema with only the new check, with each existing check, and with all checks; assert only enabled sections are present and the run-state schema does not predict dynamic problem items.
- [Hidden Failure] Return a syntactically valid handoff with duplicate IDs, no request-completion item, or multiple request-completion items; assert it is rejected and cannot silently skip the check.
- [Silent Failure] Assert problem evidence is included in the Jev state while the handoff writer's `missing` judgment is only sent to the main agent and is not presented as evidence to Jev.
- [Hidden Assumption] Supply no observed problems and confirm the required request-completion item passes only when the original request is shown complete; an incomplete original request must fail.
- [Edge Case] Supply one observed problem and a fully evidenced repair plus successful relevant revalidation and post-repair task completion; assert the check passes at the threshold boundary.
- [Silent Failure] Supply an attempted repair with a failed or absent revalidation; assert it remains unresolved even if the handoff says the task was completed.
- [Hidden Failure] Omit one expected Jev answer from a combined response; assert the result is unavailable and fail-open rather than treating the missing problem as passed.
- [Hidden Assumption] Include several different observed problems and ensure the check asks one question per problem plus exactly one separate original-request-completion question.
- [Edge Case] Enable multi-part, claims, and problem-resolution checks; assert one Jev request contains all enabled state sections and all questions, with no second decision request.
- [Silent Failure] Return a Jev negative answer for the problem check while other checks pass; assert only the problem check fails and only its unresolved work appears in its continuation explanation.
- [Hidden Failure] Simulate run-state, handoff, and Jev provider failures independently; assert each failure remains fail-open and does not suppress the original agent answer.
- [Edge Case] With `max_continuations=0`, assert the check still runs and is recorded but the agent is not continued; at the configured cap, assert the latest verdict remains on the response.
- [Hidden Assumption] After a failed check, simulate the main agent repairing and revalidating the problem and completing the original request; assert the next finish attempt rebuilds the handoff from the longer run and the check passes in the same loop.
- [Silent Failure] Assert continuation message includes original request, run state, handoff, failed check, and focused repair/revalidation followed by original task completion; assert passing checks and resolved problems are omitted from Focus.

### Integration Tests

- Run JevAgent with `ScriptedGenerativeRunner` and `ScriptedDecisionRunner` through: initial request; encountered failure; continuation with repair and relevant revalidation; original request completion; re-handoff; passing check. Assert the main loop's history is retained and no live provider is called.
- Run the combined flow with `MULTI_PART` and `PROBLEMS_RESOLVED` enabled; assert one combined Jev request per finish attempt and outcomes recorded through `JevAgent.response.done`.
- Run the continuation cap and unavailable-provider paths through JevAgent, asserting the current final answer stands and latest results remain inspectable.

### Manual / QA Test Cases

1. Given the new check enabled, when the agent encounters a failed command and continues without a successful repair/revalidation, then the handoff reports the unresolved issue and the same agent loop receives a focused repair request plus the original request.
2. Given a continuation, when the agent fully fixes the issue, validates the fix successfully, and then completes the original request, then the next handoff records that sequence and the check passes.
3. Given a run with no encountered problems, when the agent completes the original request, then the required completion item passes without inventing problems.
4. Given the check disabled, when JevAgent runs, then no new run-state section, handoff section, Jev question, or continuation behavior is added.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing TypeSafe `DecisionModelHelper` / `DecisionModelRunner` | Existing configured endpoint | Judge the per-item question from compiled run evidence. | Unavailable calls fail open under existing done-check policy. |
| Existing JevAgent generative provider | Existing configured provider | Write run state and compile the handoff evidence. | Incomplete/malformed handoff is unavailable and fails open. |
| No new package dependencies | N/A | N/A | No dependency change. |

---

## 12. Rollout & Deployment

- Opt-in only: callers add `JevDoneCheck.PROBLEMS_RESOLVED` to `JevContinualSettings.checks`.
- No migration or feature flag service is required.
- Rollback by removing the enum registration, question, schema cases, tests, and guidance in a follow-up revert; callers must remove the new check before rollback.
- Existing JevAgent users who do not enable the check retain the current behavior.

---

## 13. Open Questions

N/A - no unresolved design decisions. The check is opt-in, matching the existing empty `JevContinualSettings.checks` default and the continuation skill's named-capability pattern.

---

## 14. Alternatives Considered

### Alternative 1: Add a separate `JevContinuation` subclass

- What: Add an independently wired continuation that inspects run failures and triggers outside the done-check system.
- Why rejected: The new behavior is a judgment about whether finished work is complete and repair evidence is sufficient. The existing `JevDoneContinuation` already re-evaluates checks after handoff, enforces a continuation cap, records results, and resumes the same loop.

### Alternative 2: Re-run the main agent from the original request

- What: Start a fresh agent loop after finding an unresolved problem.
- Why rejected: It discards the original run history and repair context. The established continuation appends to the same loop and explicitly includes the original request.

### Alternative 3: Track only requested deliverables

- What: Treat a completed deliverable as proof that problems encountered along the way were fixed.
- Why rejected: Completing a requested output does not establish that a failed command, test, or operation was repaired and revalidated; the two obligations require separate evidence.
