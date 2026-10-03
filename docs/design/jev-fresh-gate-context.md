# Design Doc: JEV Fresh Continuation Gate Context

**Status:** Implemented
**Author:** Codex
**Created:** 2026-10-03
**Last Updated:** 2026-10-03

---

## 1. Overview

When JevAgent uses its fresh-context continuation, the new agent will receive an assessment section describing every enabled continuation gate and its current failed questions. Each gate owns a stable two-to-three paragraph explanation of what it checks, how the agent should use it, and common failure patterns. The question list comes from the gate's latest Jev answers, includes the exact rendered question text, and excludes probabilities. Rebuilding the section on each retry ensures the next fresh agent sees the current failures.

---

## 2. Goals & Non-Goals

### Goals

- Give each registered `JevDoneCheck` a reusable human-authored explanation.
- Preserve, per result, the exact rendered Jev question texts whose answers failed that gate's threshold.
- Add a `<completion_gate_assessment>` section to every fresh-continuation input, including all configured gates in configured order.
- Refresh question failures from the latest gate evaluation on every continuation attempt.
- Keep probabilities, scores, and internal result identifiers out of fresh-agent context.
- Keep Jev evaluation fail-open and preserve current continuation caps and handoff behavior.

### Non-Goals

- Change any Jev question, threshold, question wording, gate semantics, or continuation policy.
- Change the same-context continuation's message format.
- Add dynamic model-generated explanations or remediation advice.
- Include handoff-derived focus instructions or probability values in the assessment section.
- Change the public JevAgent settings or response contract.

---

## 3. Background & Context

`JevRunState.check()` asks all enabled done checks in one shared decision request, then `_judge()` creates one `JevDoneResult` per check. Each result contains the answers used by that check. `JevDoneContinuation` retains the failed results on `self.failed`. The same-context continuation formats its own question and focus feedback through per-check handlers. `JevFreshContinuation.message()` instead formats a separate prompt from the request, run state, and handoff, so its new agent currently does not see the gate descriptions or the specific Jev questions that failed.

The desired context is gate-oriented: one explanation for each enabled check, followed by the actual question text that the check's scoring logic found blocking. Question text is recoverable from the registered `JevDoneQuestion` by matching each blocking `JevAnswer.question_name`; gate scoring remains the authority for whether that answer caused failure. `JevAnswer` probability data stays internal. A failed gate can also result from deterministic evidence conditions without a blocking Jev answer; that gate still receives its description and an explicit note that no Jev question failed, while the existing handoff remains available for evidence.

---

## 4. Requirements

### Functional Requirements

1. Every registered `JevDoneCheck` has a non-empty, human-authored two-to-three paragraph description covering purpose, how the agent should use the check, and common failure modes.
2. Gate descriptions are registered with `JevDoneRegistry`, in configuration order when rendered.
3. `JevDoneResult` retains the exact rendered question text that caused the result to fail under that gate's own scoring rule. Question text includes the concrete checked item name; composite checks retain each question involved in the blocking result.
4. A passed answer is not listed as a failed question, even when a separate deterministic rule causes its gate result to fail.
5. Fresh-continuation context renders one `<completion_gate_assessment>` section containing every enabled gate, its description, and only its latest failed questions. Results without failed Jev questions are identified as such.
6. The section is regenerated after every call to `JevRunState.check()`; questions repaired in the previous attempt do not persist as failures.
7. The assessment contains neither probabilities nor scores and does not reveal internal question keys.
8. Missing records, a Jev outage, or an unavailable result preserve current fail-open behavior and do not prevent continuation handling.
9. Existing fresh prompt context (original request, run state, handoff), response evidence, and continuation limit remain intact.

### Non-Functional Requirements

- Keep rendering local and deterministic with no additional model or network calls.
- Keep the serialized additions bounded by the enabled gate count and failed question count for one attempt.
- Keep `vidbyte/lib/` independent of the agents layer.
- Preserve the public result contract except for an additive defaulted record field.

---

## 5. High-Level Design

Add a JEV record for a failed question containing the answer's question name internally and the exact question sentence for rendering. Add `failed_questions` to `JevDoneResult`. `JevRunState` already has the check-specific result and all answers, so it will apply the check's scoring rule, resolve blocking answer names through the registered question set, and attach the rendered question text to the result before returning it. This captures the scorer's actual failed judgments, including composite checks whose question names have a suffix distinct from the incomplete item id.

Add a complete description registry beside `JevDoneRegistry` with one entry per done check. `JevFreshContinuation.message()` will iterate its configured checks and latest results, render each description and its failed question sentences, and pass the completed block into a new placeholder in `fresh_prompt.md`. The block will use `<completion_gate_assessment>` as its boundary signal. It will render all enabled gates, not only failed ones, so each gate's role remains understandable and a resolved gate is visibly clear on later attempts.

```text
JevRunState.check()
  -> one JevDoneResult per configured gate, including failed question text
  -> JevFreshContinuation.message()
  -> <completion_gate_assessment> in the clean fresh-agent context
```

---

## 6. Detailed Design

### 6.1 Failed question record and result

**File(s):** `vidbyte/lib/dataclasses/jev.py`
**Type:** Modified

#### What it does

Defines a frozen record for one actual failed Jev question and adds an immutable tuple of these records to `JevDoneResult`. The record retains the internal answer name for matching/debugging and the exact rendered question sentence for the continuation to show. It intentionally carries no answer value, probability, threshold, or focus narrative.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class JevFailedDoneQuestion:
    name: str
    question: str

@dataclass(frozen=True, slots=True)
class JevDoneResult:
    failed_questions: tuple[JevFailedDoneQuestion, ...] = ()
```

#### Logic / Algorithm

1. Preserve existing result construction by giving the new field an empty tuple default.
2. Validate each recorded failure at construction and freeze the tuple.
3. Export the new record only if it is part of the established public result surface; otherwise keep the type internal to the result module's existing exports.

#### Edge Cases & Error Handling

- Empty failed-question tuple is valid for passes and deterministic-only failures.
- The question text must be non-blank and the name must be a non-blank string.
- No exception or unavailable result is converted into a fabricated question.

### 6.2 Done-question matching and gate descriptions

**File(s):** `vidbyte/lib/jev/done/done.py`
**Type:** Modified

#### What it does

Extends the existing registry with one explanatory description for every enabled gate and a lookup for resolving a rendered answer name to the corresponding fixed question. Existing question, threshold, and check validation remain the single source of truth.

#### Interface / API

```python
@classmethod
def description(cls, check: JevDoneCheck) -> str: ...

@classmethod
def question_for_answer_name(cls, name: str) -> tuple[JevDoneQuestion, str]: ...
```

#### Logic / Algorithm

1. Add a mapping keyed by every `JevDoneCheck`; each value has a heading and a two-to-three paragraph description.
2. Validate that question checks, thresholds, and descriptions cover the same gate set.
3. Resolve question names by testing registered question keys against the name prefix and returning the question plus the exact item suffix.
4. Raise the repository's existing configuration error for an unknown/ambiguous name rather than silently dropping an answer.
5. Descriptions cover each gate's check target, how to apply its result, and common incompletion patterns without changing Jev's rubric.

#### Edge Cases & Error Handling

- Every current gate and future registered gate must have a description.
- Names for paired questions sharing an item must resolve to their own exact question.
- Inventory question names resolve through the inventory registry as well as ordinary question groups.
- Empty or ambiguous answer names fail clearly during scoring, before fresh prompt construction.

### 6.3 Capture blocking questions in each result

**File(s):** `vidbyte/agents/jev/done/run_state.py`
**Type:** Modified

#### What it does

Adds the exact Jev questions whose answers fail the threshold to each `JevDoneResult`, using the same registered threshold used by gate scoring.

#### Interface / API

The private helpers `_failed_questions(result)` and `_blocking_answer_names(result, threshold)` attach a tuple of failed-question records at the shared `_judge()` boundary.

#### Logic / Algorithm

1. Each `_judge_*` path already returns a check-scoped result with its answers and blocking items.
2. At the common `_judge()` boundary, normalize that result through one helper before returning it.
3. For ordinary checks, use `DecisionModelHelper.noul_passes` and the check threshold to retain answers below threshold.
4. For composite checks whose blocker is a combination of affirmative answers, retain the answers for the blocking item that establish that combination.
5. Resolve each selected answer name to its registered question and complete item suffix, then format the same question sentence that Jev received.
6. Preserve result availability and deterministic `incomplete` behavior when no Jev answer is itself blocking.

#### Edge Cases & Error Handling

- Missing answers are unavailable, not failed questions.
- Non-Noul answers are unavailable, not failed questions.
- Inclusive threshold behavior matches existing `DecisionModelHelper` semantics for ordinary checks.
- Composite checks preserve their gate-specific logic: required next actions retain affirmative necessity and unfinished questions; self-review retains the paired questions for each standing objection.
- Compound questions retain separate sentences and names.
- A deterministic incomplete item with a passing Jev answer does not incorrectly appear as a failed Jev question.

### 6.4 Render the assessment for fresh continuation

**File(s):** `vidbyte/agents/jev/continuation/fresh.py`, `vidbyte/prompts/prompts/jev_fresh_continuation/fresh_prompt.md`
**Type:** Modified

#### What it does

Renders the fresh agent's gate assessment from the latest failed results and injects it into the existing clean-context prompt.

#### Interface / API

```python
def _render_gate_assessment(self) -> str: ...
```

#### Logic / Algorithm

1. Iterate configured checks in their original order.
2. For each check, render its stable heading and description.
3. Render exact question sentences from that check's current result; omit probabilities and internal answer names.
4. State explicitly when a gate is currently passing, has no failed Jev questions, or is unavailable.
5. Wrap the rendered entries in `<completion_gate_assessment>...</completion_gate_assessment>`.
6. Format the fresh prompt with the new assessment placeholder on every continuation attempt.

#### Edge Cases & Error Handling

- Missing result does not prevent fresh continuation; render a safe unavailable status.
- Checks with no failed questions remain visible with their current state.
- A later retry uses only its newly evaluated results; no previous assessment is cached.
- Existing missing request/state/handoff checks still prevent launching with partial source context.

### 6.5 Prompt instructions and verification coverage

**File(s):** `vidbyte/prompts/prompts/jev_fresh_continuation/fresh_prompt.md`, `tests/test_jev_fresh_continuation.py`, `scripts/test-jev-fresh-gate-context.py`
**Type:** Modified, Modified, New

#### What it does

Tells the fresh agent how to use the gate assessment and verifies it with focused offline tests plus an executable verification script.

#### Interface / API

The prompt names the assessment section as internal execution context, directs the agent to address its failed questions using the original request, run state, and handoff, and says to preserve completed work and not mention internal notes to the user.

#### Logic / Algorithm

1. Extend the fresh continuation test stubs to return real typed done results and descriptions.
2. Assert exact question sentences are present, internal names and probabilities are absent, and every enabled gate appears in order.
3. Exercise a second attempt where a previously failed question passes and disappears while another remains.
4. Cover deterministic-only failure, unavailable check, empty answer set, paired questions, and unknown question names.
5. Add an executable script that runs all cases listed below and reports per-case PASS/FAIL plus a total.

#### Edge Cases & Error Handling

- Fake answers cover threshold boundaries and missing-answer behavior without a provider call.
- Script propagates a non-zero exit if any case fails.
- Prompt formatting with an empty gate assessment remains valid.

---

## 7. Data Model Changes

### 7.1 `JevFailedDoneQuestion` and `JevDoneResult`

**Change type:** Modified

```python
@dataclass(frozen=True, slots=True)
class JevFailedDoneQuestion:
    name: str
    question: str

@dataclass(frozen=True, slots=True)
class JevDoneResult:
    failed_questions: tuple[JevFailedDoneQuestion, ...] = ()
```

No persistence or migration applies. Existing construction remains source-compatible through the default.

---

## 8. API Changes

N/A - This is an internal SDK continuation-context change. It adds a defaulted field to an existing result record but does not add a user configuration option or network endpoint.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Add failed question record and result field. |
| MODIFY | `vidbyte/lib/jev/done/done.py` | Register gate descriptions and exact question lookup. |
| MODIFY | `vidbyte/agents/jev/done/run_state.py` | Capture the question text that blocks each result. |
| MODIFY | `vidbyte/agents/jev/continuation/fresh.py` | Render the latest assessment per attempt. |
| MODIFY | `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py` | Re-export the new result record with the existing public JEV result types. |
| MODIFY | `lint/baseline.json` | Ratchet the verified improvements in A002, S009, and S051, as required by the repository lint policy. |
| MODIFY | `vidbyte/prompts/prompts/jev_fresh_continuation/fresh_prompt.md` | Explain and place the assessment section. |
| MODIFY | `tests/test_jev_fresh_continuation.py` | Add focused behavioral tests. |
| CREATE | `scripts/test-jev-fresh-gate-context.py` | Run every design-plan case with named PASS/FAIL output. |

---

## 10. Testing Plan

All cases run offline with deterministic typed records and no TypeSafe request. Each category label is retained in the focused verification script.

### Unit Tests

- [Edge Case] Every registered gate has one two-paragraph description; registry validation rejects a missing description.
- [Edge Case] Compound follow-up and self-review gates preserve both exact questions that jointly block the result.
- [Hidden Failure] Unknown question names raise a configuration error instead of silently dropping a failed answer.
- [Silent Failure] Item ids containing dots and colons are preserved in the exact rendered question sentence.
- [Silent Failure] Only below-threshold ordinary answers are retained; a passing answer and an answer exactly at threshold are omitted.
- [Hidden Assumption] Remapped scorer answer keys still resolve through `JevAnswer.question_name` to the registered question.

### Integration Tests

- [Edge Case] Fresh input retains the request, run state, handoff, gate descriptions, and exact current failed questions.
- [Hidden Failure] Unavailable gates are marked not evaluated, deterministic failures do not fabricate Jev questions, and fresh-agent errors preserve the current fail-open behavior.
- [Silent Failure] Across two finish attempts, a repaired question disappears while an outstanding question remains; passed enabled gates remain listed.
- [Hidden Assumption] Multiple configured gates render once each, in configured order, with no internal keys or probabilities exposed.

### Manual / QA Test Cases

N/A - The changed surface is a deterministic prompt assembled from typed check results; the offline integration tests assert the complete rendered input without requiring a real provider or human judgment.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing `JevDoneRegistry` | Internal SDK | Gate description and question lookup | Incomplete registry coverage could omit context; validation and tests pin coverage. |
| Existing `DecisionModelHelper` | Internal SDK | Reuse threshold semantics when identifying failed answers | None beyond existing scorer contract. |
| TypeSafe Jev service | Existing configured provider | Produces gate answers as before | No additional requests are introduced. |

---

## 12. Rollout & Deployment

- No feature flag or data migration is required; behavior applies to the existing opt-in fresh gate.
- The same-context gate path is unaffected.
- Rollback is a normal code revert; no persisted data needs repair.

---

## 13. Open Questions

- N/A - The section name, question-level content, refresh semantics, and handling of deterministic-only failures are settled by the request and current result model.

---

## 14. Alternatives Considered

### Alternative 1: Add a `fresh_agent` explanation to every question

- What: Store a generic fresh-agent paragraph on each question and append it beside failed questions.
- Why rejected: The user wants shared guidance per gate, and question-level copies would repeat the same instructions for every item and drift from one another.

### Alternative 2: Reuse the current `_explain()` focus output

- What: Carry the existing human-readable failure and focus summaries to the fresh prompt.
- Why rejected: The requested context should show the gate's general purpose and the actual Jev questions that failed. Existing focus is separately authored per check and may include handoff prose or probabilities.

### Alternative 3: Ask a model to explain failed checks at runtime

- What: Generate a new summary of each failed gate before launching the fresh agent.
- Why rejected: It adds latency and another failure path; authored gate descriptions and recorded Jev questions already provide the intended content deterministically.
