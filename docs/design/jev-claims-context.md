# Design Doc: Expand Jev CLAIMS Context

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-28
**Last Updated:** 2026-09-29

---

## 1. Overview

CLAIMS currently gives Jev a claim string and a prose evidence string, which leaves the checker to infer the assertion's purpose, boundaries, kind, expected output, and criteria from prose. This change gives every post-run claim a typed context with five named sections, extracts atomic assertions within it, and attaches completion criteria to each assertion. The handoff continues to derive claims from each attempted final answer; Jev continues to recognize whether recorded evidence meets the provided criteria, while code combines assertion answers into the existing per-claim completion result. The continuation skill will make this five-section example and the repository's five-sentence structured-field requirement part of the procedure for designing done checks.

---

## 2. Goals & Non-Goals

### Goals

- Replace CLAIMS' bare `claim: str` with a typed claim context containing identity (`title`, `description`, `intent`), scope (`scope`, `qualifications`), `kind`, `output`, and `assertions`.
- Put `completion_criteria` on each atomic assertion so Jev can compare a single asserted fact against a stated observation condition.
- Project five named context sections into Jev's shared state and ask one question for each assertion, in the existing combined request.
- Combine assertion outcomes in code so any unsupported assertion keeps its parent claim incomplete and its failure can be named in continuation feedback.
- Update `skills/jev-continuation/SKILL.md` with the five-section pattern, field-writing guidance, and at-least-five-sentence descriptions for structured-output fields.

### Non-Goals

- Do not move claims into request-derived run state; the final-answer assertions only exist after work.
- Do not change `JevAgent` settings, runtime wiring, system prompts, continuation limits, the MULTI_PART check, or the public threshold.
- Do not use the handoff's `missing` assessment as evidence for Jev.
- Do not claim that more fields alone establish improved model accuracy; that requires a labeled evaluation set.
- Do not add live provider calls or dependencies.

---

## 3. Background & Context

- **Why now?** The owner wants the central claim object to carry the context that makes each CLAIMS continuation question understandable and checkable, and wants that shape documented for future gates.
- **Problem:** `JevClaimEvidencePayload` currently has `id`, `claim`, `evidence`, and `missing`. `JevRunState._section(CLAIMS)` sends only claim text and evidence to Jev. Separate facts are extracted per current entry, but the structured API does not distinguish the claim's intent, scope, kind, output, assertion, or completion criteria.
- **Current flow:** `JevHandoff.compile()` extracts answer-derived claim records and run evidence. `JevRunState.combine()` projects enabled checks into one state and batches their questions. `_claims()` scores the answers with a per-item veto. `JevDoneContinuation._explain()` focuses the main agent on incomplete claims.
- **Constraints:** Records and payloads belong in `vidbyte/lib/dataclasses/jev.py`, enums in `vidbyte/lib/enums/jev.py`, question definitions in `vidbyte/lib/jev/done/claims.py`, and behavior in the existing Jev agents. Generative field descriptions are the handoff writer's instructions. Jev must retain recognition-only questions, one question per independently checkable assertion, probability-based scoring, and fail-open behavior.

---

## 4. Requirements

### Functional Requirements

1. Each handoff claim has five top-level context sections: `identity`, `scope`, `kind`, `output`, and `assertions`.
2. `identity` contains `title`, `description`, and `intent`; intent is included only when the request or final answer gives a clear purpose, otherwise it is explicitly `None`.
3. `scope` contains what the claim covers and `qualifications` that the final answer expressly attaches to it. Missing qualifications produce an empty list.
4. `kind` uses a closed `JevClaimKind` enum defined in `vidbyte/lib/enums/jev.py` and covers the categories of factual claims the current CLAIMS contract accepts.
5. `output` names the result the final answer claims, or is `None` when the assertion is observational and claims no produced artifact.
6. Every claim contains at least one atomic assertion. Each assertion has a unique stable id within its parent claim, a statement, and a `completion_criteria` string describing the observation that would establish that statement.
7. Handoff payloads, frozen records, and all model-facing payload fields validate their values and use five-sentence descriptions. The five-sentence minimum applies to schema instructions, not to the amount of prose a claim value must contain.
8. At each finish attempt, Jev's state presents exactly the five named context sections for each assertion, plus the run evidence. It asks one positive yes/no question for each assertion and keeps all enabled done-check questions in one Jev request.
9. Code combines assertion outcomes under their parent claim. A claim is incomplete if any assertion misses the existing CLAIMS threshold; missing answers or provider failures mark the check unavailable and fail open.
10. On continuation, only incomplete parent claims appear in focus, with their unsupported assertions, associated completion criteria, and the handoff evidence gap. Supported assertions and claims remain out of focus.
11. An empty claim list adds no questions and passes. A claim without assertions, duplicate assertion ids, invalid identifiers, or an unusable handoff makes the handoff unavailable rather than silently passing an unchecked claim.
12. The continuation skill explains how to choose four to six decision-relevant context sections for each per-item gate question, how the question refers to those sections while asking one recognition judgment, and how each structured-output field description has at least five complete, useful sentences.

### Non-Functional Requirements

- Preserve the alpha SDK's typed records, strict Pydantic payloads, lower-layer ownership, and single-request batching.
- Keep execution bounded by the existing handoff, Jev, and continuation limits. Additional claim context increases generated output and decision-state size, so oversized or malformed output must follow existing fail-open behavior.
- Do not add logs, persistence, network calls, or third-party dependencies.
- Keep the user-visible run behavior advisory: unavailable checking leaves the main agent's answer standing.

---

## 5. High-Level Design

The handoff's claim becomes a typed object with five Jev-facing context sections. The identity section groups title, description, and stated intent. The scope section groups the included scope and explicit qualifications. `kind` uses a registered enum. `output` names the stated result when one exists. `assertions` is a list of independently checkable statements, each with its own completion criteria and stable id. The existing evidence and missing fields remain siblings of this object on the evidence record.

At each finish attempt, the handoff extracts the richer record from the current final answer and maps it to immutable records. The shared-state projection expands each parent claim into assertion entries, repeats the five context sections needed to interpret the assertion, and includes only the tool evidence. Jev receives one question per assertion in the existing combined request. Code scores each answer against the unchanged threshold, maps a failed assertion to its parent claim, and preserves the existing meaning that any unsupported claim requires continuation. The continuation renders only incomplete claims and names their failing assertions and criteria.

The general handoff prompt and runtime wiring remain unchanged; the output schema carries the check-specific extraction instructions. The continuation skill becomes the reusable design guide for this context shape and for writing complete model-facing field descriptions. Existing done checks keep their current payloads; the four-to-six context rule guides new or deliberately redesigned gate questions and does not trigger unrelated changes to MULTI_PART in this PR.

```text
final answer + run evidence
        -> JevHandoff: claim identity / scope / kind / output / assertions
        -> JevRunState: one state entry and Jev question per assertion
        -> one batched Jev request
        -> code groups failing assertions by parent claim
        -> JevDoneContinuation focuses only those claims
```

---

## 6. Detailed Design

### 6.1 Typed claim context and evidence records

**File(s):** `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/enums/jev.py`, `vidbyte/agents/jev/__init__.py`, `vidbyte/__init__.py`
**Type:** Modified

#### What it does

Defines strict nested payloads for the five context sections, an assertion record with completion criteria, a closed claim-kind enum, and corresponding immutable records. `JevClaimEvidencePayload.claim` and `JevClaimEvidence.claim` change from a string to the typed context, with `evidence` and `missing` remaining alongside it. A parent claim still has a stable id; assertion ids are unique within it and form the keys used to name Jev answers. Public record exports let callers inspect the richer `JevAgent.response.handoff.claims` result.

#### Interface / API

```python
JevClaimContext(identity, scope, kind, output, assertions)
JevClaimIdentity(title, description, intent)
JevClaimScope(scope, qualifications)
JevClaimAssertion(id, statement, completion_criteria)
JevClaimEvidence(id, claim, evidence, missing)
```

Payload equivalents use `BaseModel`, `extra="forbid"`, and five-sentence field descriptions. Required contextual text is nonblank; `intent` and `output` are nullable for facts that do not state a purpose or produced output. Each parent has a nonempty assertion list, and every assertion has one nonblank completion-criteria string; the parent claims list may be empty.

#### Logic / Algorithm

1. Define `JevClaimKind` in `lib/enums/jev.py` for the closed claim categories supported by the current contract.
2. Define Pydantic component payloads and frozen component records in `lib/dataclasses/jev.py`.
3. Validate every string, enum, collection, parent id, and within-parent assertion-id uniqueness at the owning payload/record boundary.
4. Preserve empty parent claims as a valid no-work-to-check result.
5. Export records reachable from `JevAgent.response`; export the enum from `lib/enums/__init__.py` if used as a public record field.

#### Edge Cases & Error Handling

- `intent=None`, `output=None`, and `qualifications=()` represent absent information; empty strings are invalid.
- A claim with no assertions is invalid so extraction cannot silently bypass its checks.
- Duplicate assertion ids within one claim are invalid; identical assertion ids under different parent ids remain distinct.
- Invalid or malformed generated structures make handoff compilation unavailable and retain fail-open behavior.

### 6.2 Handoff extraction

**File(s):** `vidbyte/lib/dataclasses/jev.py`, `vidbyte/agents/jev/done/handoff.py`
**Type:** Modified

#### What it does

Expands the handoff schema so the generative writer extracts the structured claim from the final answer. The field descriptions tell it to preserve the final answer's actual title, meaning, stated purpose, scope, qualifications, result, and separate factual assertions. It must not invent purpose or qualifications, turn advice into an assertion, or strengthen an assertion when writing its criteria. `JevHandoff._record()` converts the validated nested payload to immutable records while retaining the evidence and missing notes. The handoff is regenerated for every finish attempt, so revisions to the final answer produce a matching revised record.

#### Interface / API

```python
JevClaimEvidencePayload(id, claim, evidence, missing)
JevClaimContextPayload(identity, scope, kind, output, assertions)
```

Each field's schema description has at least five sentences covering its meaning, source, boundary, absent-value handling, and relationship to adjacent fields. The nested description explains that the five context sections each serve the later question; detailed qualifications and completion criteria remain attached to their owning sections.

#### Logic / Algorithm

1. Extract one parent context for each concrete factual claim in the final answer.
2. Split independent facts into separate assertion payloads and assign each a stable id unique within its parent.
3. Generate completion criteria for each assertion from the observable condition implied by that assertion and preserve any explicit qualification.
4. Compile the payload to typed context, assertion, evidence, and missing records.
5. Return unavailable on structured-output errors or validation failures, preserving fail-open behavior.

#### Edge Cases & Error Handling

- No checkable claims yields an empty valid list.
- A claim with multiple independent facts yields multiple assertions; one indivisible fact yields one assertion.
- Intent is taken only from a clear purpose in the request or final answer; absent intent and output are represented as `None`, and unqualified assertions have no qualifications.
- Empty assertions, duplicated assertion ids, and malformed field types are not treated as an empty successful check.

### 6.3 Jev state projection and scoring

**File(s):** `vidbyte/agents/jev/done/run_state.py`, `vidbyte/lib/jev/done/claims.py`
**Type:** Modified

#### What it does

Projects each assertion into a shared-state entry with five named context sections: `identity`, `scope`, `kind`, `output`, and the singular `assertion` being judged. The assertion section includes its text and completion criteria; the evidence sibling contains the run evidence; the handoff's `missing` assessment stays out. The fixed question asks whether that evidence meets the criteria for that assertion given the five context sections. Question names distinguish parent and assertion ids, and every generated question remains in the existing combined decision request. `_claims()` scores all assertion answers at the existing threshold and veto, then lists the parent claim as incomplete if any of its assertions falls below the threshold.

#### Interface / API

The shared-state `claims` mapping contains one key per claim assertion. Each entry has the five context sections `identity`, `scope`, `kind`, `output`, `assertion` and the evidence used to judge it. `JevDoneResult.incomplete` continues to identify parent claim ids. The answer mapping identifies individual assertion questions so the caller can inspect which fact failed.

#### Logic / Algorithm

1. Flatten parent claims into stable `(claim_id, assertion_id)` question references without changing the parent record.
2. Build one state entry and one `JevDoneQuestion` per assertion using all five context sections.
3. Include those questions with all other enabled checks in one `JevDecisionRequest`.
4. Apply the existing threshold/veto to each assertion; mark a parent incomplete when at least one associated answer is below threshold.
5. Return an unavailable result for a missing expected answer, a missing handoff, or a Jev failure; return a passing result without a call for no parent claims.

#### Edge Cases & Error Handling

- Multiple assertions map back to exactly one parent claim; identifiers cannot collide across parents.
- One failed assertion cannot be averaged away by supported assertions or by MULTI_PART answers.
- Empty claims add no questions while other enabled checks still run in the shared request.
- Missing assertion answers make the check unavailable instead of silently dropping that assertion.

### 6.4 Continuation feedback

**File(s):** `vidbyte/agents/jev/continuation/done.py`
**Type:** Modified

#### What it does

Resolves incomplete parent claim ids back to their assertions and emits failure detail only for assertions whose Jev answer fell below threshold. The focus includes the claim title, description, scope, claimed output, the unsupported assertion, its completion criteria, the relevant evidence, and the handoff's actionable gap. Supported sibling assertions stay out of failure focus. The output remains plain text in the existing continuation prompt asset. A failed or unavailable check still follows current continuation and fail-open policy.

#### Interface / API

`JevDoneContinuation._explain(result)` continues to return the failed-question text and focus text expected by the existing prompt. It consumes the expanded `JevClaimEvidence` record and assertion-keyed answers; it does not add runtime settings or prompt formatting fields.

#### Logic / Algorithm

1. Resolve each incomplete claim to its assertion records.
2. Select the assertions whose answer probability fell below the registered threshold.
3. Emit each failed assertion with the parent context and its completion criteria.
4. Keep supported claims and assertions out of the focus section.

#### Edge Cases & Error Handling

- One incomplete assertion emits its parent once and the failing assertion detail once.
- Several failing assertions under one claim share the parent description without duplicate claim headings.
- Missing references after validated scoring are treated as a typed invariant failure in tests rather than silently formatting another item.

### 6.5 Continuation skill guidance

**File(s):** `skills/jev-continuation/SKILL.md`
**Type:** Modified

#### What it does

Teaches that a per-item gate state should supply four to six named, decision-relevant context sections, and that the question should refer to those sections while asking one recognition judgment. It documents CLAIMS' five sections and the nested fields they group. It gives a detailed five-sentence minimum for each structured-output field description, consistent with `AGENTS.md`'s existing four-to-six sentence requirement. The five sentences explain purpose, source, scope, absent-value behavior, and interaction with other fields rather than asking generated values to be verbose. It also documents one-question-per-assertion scoring and parent-claim aggregation.

#### Interface / API

Documentation only; the skill's checklist and dynamic-claims section gain the new field design and procedure.

#### Logic / Algorithm

1. Explain how to select four to six context sections based on what the single judgment needs.
2. Include the CLAIMS mapping: identity (`title`, `description`, `intent`), scope (`scope`, `qualifications`), `kind`, `output`, and `assertions` with per-assertion `completion_criteria`.
3. Require each Jev question to name the current assertion and use the context sections as reference material.
4. Require a five-sentence minimum for every structured-output field description, with no empty repetitions or extra work imposed on the agent.
5. Update the checklist and claim flow so its instructions match runtime behavior.

#### Edge Cases & Error Handling

- Clarify that the five-sentence minimum is for schema descriptions and does not prescribe output value length.
- State that intent is derived only from clear request or final-answer context, and absent intent, output, and qualifications are represented explicitly rather than fabricated.
- Keep existing check payloads stable; the guidance applies when a check is added or its context is redesigned.

---

## 7. Data Model Changes

### 7.1 `JevClaimContext` and related records

**Change type:** Modified

```python
JevClaimContext(
    identity=JevClaimIdentity(title, description, intent),
    scope=JevClaimScope(scope, qualifications),
    kind=JevClaimKind,
    output=str | None,
    assertions=tuple[JevClaimAssertion(id, statement, completion_criteria), ...],
)
JevClaimEvidence(id, claim=JevClaimContext, evidence, missing)
```

**Migration strategy:**

- Forward migration: None. This is an in-memory alpha SDK response and model-output shape; no persisted store or wire endpoint consumes it.
- Rollback plan: Revert this PR commit set; there is no data migration to reverse. Existing consumers that construct or inspect the in-PR `JevClaimEvidence` record must adopt the structured claim type with this change.

---

## 8. API Changes

### 8.1 CLAIMS handoff / Jev shared-state item

**Change type:** Modified

**Request:**

```json
{
  "claims": {
    "readme_docs": {
      "id": "readme_docs",
      "claim": {
        "identity": {
          "title": "Documented --dry-run",
          "description": "README.md explains that the deploy command previews a deployment when --dry-run is supplied.",
          "intent": "Help readers understand how to preview a deployment."
        },
        "scope": {
          "scope": "The deploy command documentation in README.md.",
          "qualifications": []
        },
        "kind": "file_content",
        "output": "Documentation for the --dry-run option.",
        "assertions": [
          {
            "id": "preview_behavior_described",
            "statement": "README.md says --dry-run previews a deployment.",
            "completion_criteria": "The recorded README.md content contains that explanation."
          }
        ]
      },
      "evidence": "The run's relevant tool evidence.",
      "missing": "Nothing is missing."
    }
  }
}
```

**Response:**

```json
{
  "claims.supported.readme_docs.preview_behavior_described": {
    "true": 0.94,
    "false": 0.06
  }
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| N/A | The SDK has no HTTP endpoint for this in-process state. Malformed generated output makes the handoff unavailable and the done check fails open. |

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/jev-claims-context.md` | Decision record for the expanded claim context. |
| MODIFY | `vidbyte/lib/constants/jev.py` | Define stable field names and the composite parent/assertion question-id separator. |
| MODIFY | `vidbyte/lib/dataclasses/jev.py` | Add nested claim payloads and records; change the evidence record to hold a structured claim. |
| MODIFY | `vidbyte/lib/enums/jev.py` | Define the closed claim-kind vocabulary. |
| MODIFY | `vidbyte/lib/enums/__init__.py` | Export the claim-kind enum. |
| MODIFY | `vidbyte/agents/jev/done/handoff.py` | Convert expanded handoff payloads into typed records. |
| MODIFY | `vidbyte/agents/jev/done/run_state.py` | Project five context sections per assertion and aggregate assertion outcomes by parent claim. |
| MODIFY | `vidbyte/lib/jev/done/claims.py` | Ask a recognition-only question about one assertion and its completion criteria. |
| MODIFY | `vidbyte/lib/jev/done/multi_part.py` | Keep the shared state description accurate for assertion-keyed CLAIMS entries. |
| MODIFY | `vidbyte/agents/jev/continuation/done.py` | Return only failed assertions under incomplete parent claims. |
| MODIFY | `vidbyte/agents/jev/__init__.py` | Re-export public claim context and assertion records. |
| MODIFY | `vidbyte/agents/__init__.py` | Re-export public claim records through the agents package. |
| MODIFY | `vidbyte/__init__.py` | Preserve top-level access to public claim records and enum. |
| MODIFY | `skills/jev-continuation/SKILL.md` | Document the context sections, one-question-per-assertion rule, and field-description depth. |
| MODIFY | `tests/test_jev_done.py` | Cover expanded records, projection, assertion-level scoring, and continuation feedback. |
| MODIFY | `tests/features/jev_claims/FEATURE.md` | Update the feature contract and observable response shape. |
| MODIFY | `scripts/test-jev-multipart-done-criteria.py` | Update the script header's related design reference for the expanded CLAIMS contract. |
| DELETE | N/A | No files are removed. |

---

## 10. Testing Plan

Tests use deterministic fake handoff/model responses; they make no live TypeSafe calls. Every case below is tagged with its primary failure category.

### Unit Tests

- [Edge Case] Validate a complete nested claim record with an absent intent, no output, no qualifications, and one assertion.
- [Edge Case] Accept an empty parent claim list and confirm it produces no claims question.
- [Edge Case] Convert a parent with several distinct assertions into distinct stable question ids.
- [Hidden Failure] Reject a claim with zero assertions, a duplicate assertion id, or an invalid parent id; verify handoff compilation becomes unavailable.
- [Hidden Failure] Return an unavailable done result when any expected assertion answer is missing from a successful-looking Jev response.
- [Silent Failure] Assert all five context sections and the selected assertion's criteria appear in that Jev state entry, and `missing` does not.
- [Silent Failure] Make one of several assertions unsupported and verify the parent claim fails even when the other assertion probabilities exceed threshold.
- [Silent Failure] Verify question-answer ids map to the right parent and assertion when two claims contain identically named assertion ids.
- [Hidden Assumption] Verify `None` intent/output and empty qualifications survive Pydantic conversion, frozen-record conversion, and public response serialization without fabricated defaults.
- [Hidden Assumption] Verify assertion ordering and parent ordering stay aligned across payload conversion, question construction, result mapping, and continuation focus.
- [Edge Case] Verify a very long valid parent/assertion id pair creates a stable question name or is rejected at a documented validation boundary; it must never collide through truncation.

### Integration Tests

- [Silent Failure] Run one CLAIMS finish attempt with multiple claims and assertions plus MULTI_PART; assert every question shares one Jev request and each response maps to the correct done check.
- [Hidden Failure] Simulate a handoff schema failure and a Jev provider error; assert both leave the main answer standing under fail-open policy.
- [Silent Failure] Trigger continuation for one failed assertion and assert feedback names the parent context and exact criteria while omitting supported sibling assertions and claims.
- [Hidden Assumption] Use two finish attempts with different final answers and assert the second handoff, assertion ids, and questions contain no stale claim from the first attempt.
- [Hidden Assumption] Verify the skill's schema-description guidance is enforced by sentence-count tests for every new payload field.

### Manual / QA Test Cases

1. [Edge Case] Provide a final answer with no factual claim; confirm CLAIMS asks no question and passes.
2. [Silent Failure] Provide one final-answer sentence with two independently checkable facts and evidence for one; confirm the handoff splits the facts and continuation identifies only the unsupported one.
3. [Hidden Assumption] Provide an assertion with a stated limitation and an unstated intent; confirm the qualification is preserved and the intent stays null.
4. [Hidden Failure] Force malformed handoff output; confirm no done failure blocks the original response.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing generative runner | Configured by `JevAgentSettings` | Extract the structured post-run claim context and evidence. | Larger output schema may exceed configured handoff output limits; the check then fails open. |
| Existing TypeSafe Jev runner | Configured by `JevRuntimeSettings.decision` | Recognize whether each assertion's evidence satisfies its criteria. | Model judgments remain probabilistic and require labeled evaluation to calibrate. |
| Pydantic | Existing project dependency | Validate structured handoff payloads. | No new dependency or external endpoint. |

---

## 12. Rollout & Deployment

- No feature flag changes; `JevDoneCheck.CLAIMS` remains opt-in.
- The in-PR structured handoff/response shape changes from string claims to typed context objects. The SDK is alpha and has no persisted claim records to migrate; update downstream construction/access to match before release.
- No multi-service deployment ordering applies.
- Rollback by reverting this feature commit set. No database or durable session migration is needed.
- Update the existing PR #477 branch; do not create a second pull request for this continuation of its CLAIMS feature.

---

## 13. Open Questions

N/A - The design resolves these decisions: `JevClaimKind` uses `source_content`, `artifact_change`, `command_result`, `test_result`, `run_activity`, and `other_fact`; unstated intent and absent output are nullable; question names append the assertion id to its parent id with a period, which is excluded from both validated ids and therefore unambiguous. The SDK's `JevQuestion` contract validates names as nonblank strings and does not impose a character limit.

---

## 14. Alternatives Considered

### Alternative 1: Keep one prose string and append details to it

- What: Add title, scope, output, assertions, and criteria to the existing `claim` string.
- Why rejected: The handoff, Jev state, tests, and continuation would still need to infer boundaries between concepts; a structured record gives each concept a named typed field.

### Alternative 2: Ask Jev one question for an entire claim with multiple assertions

- What: Include all assertion text and criteria but retain one question per parent claim.
- Why rejected: A no answer could mean any one of several independent facts is unsupported. Asking once per assertion keeps the recognition judgments separate; code still reports a single parent claim as incomplete when any assertion fails.

### Alternative 3: Put predicted claims in pre-run state

- What: Expand `JevRunStateRecord` and ask the handoff to match final assertions against predicted fields.
- Why rejected: The main agent's actual final assertions do not exist before work begins. A prediction can omit claims the agent later makes or add obligations it never claimed.

### Alternative 4: Require every future done check to copy CLAIMS' literal fields

- What: Add the same claim-specific fields to all done-check schemas, including MULTI_PART.
- Why rejected: Purpose, kind, output, assertions, and claim qualifications do not map to every gate. The skill instead requires each gate to select four to six named fields that supply the information its own single judgment needs; existing checks are not restructured as unrelated work.
