# Feature: JevAgent CLAIMS continuation

## High-Level Feature Description

The opt-in CLAIMS done check reviews concrete, checkable factual assertions in JevAgent's final answer. It pairs each assertion with relevant tool-call evidence, asks Jev one yes/no question per claim, and sends unsupported assertions back to the main agent. This prevents an unsupported self-report from being mistaken for evidence while leaving the ordinary answer intact if the checker is unavailable.

## Contract

- Claims come from the current final answer, not a predicted list written before the agent starts.
- Each concrete, checkable factual assertion has a unique id, paired tool-call evidence or an explicit no-evidence statement, and one Jev question.
- Jev's judgment uses only that claim and its evidence; it does not treat the final answer or the handoff's `missing` summary as evidence.
- One unsupported claim fails the check regardless of the mean score; continuation focus includes only incomplete claims and their specific evidence gaps.
- An answer with no concrete, checkable factual assertions adds no CLAIMS questions and passes. If another enabled done check has items, its questions still use the shared Jev request. Missing handoff evidence, missing credentials, or provider errors fail open.
- Every enabled done check still shares one Jev request per finish attempt.

## Actors / Callers

An SDK caller enables CLAIMS with `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.CLAIMS,)))`. JevRuntime invokes the done check when the main agent tries to finish. The handoff model extracts claims and evidence; Jev judges each claim; the continuation prompt returns only unsupported claims to the main agent.

## Inputs and Preconditions

The main agent must have a final answer and an available handoff model. The handoff sees the original request, the run-state record, the main agent's responses, tool calls with arguments/state/output, and the final answer. Claim ids must be unique lowercase identifiers accepted by `JEV_DELIVERABLE_ID_PATTERN`.

## Observable Outcomes

`JevAgent.response.handoff.claims` contains claim/evidence/missing records. `JevAgent.response.done[JevDoneCheck.CLAIMS]` reports the score, answers, incomplete claim ids, availability, and pass status. On a failed check, the next main-agent prompt includes only unsupported claim ids, claims, tool evidence, and gaps.

## State Transitions

Each finish attempt recompiles claims from that attempt's final answer. Supported claims do not appear in continuation focus; unsupported claims trigger another loop iteration until corrected or the configured continuation cap is reached. A checker or handoff failure does not block the main agent's answer.

## Invariants

- Do not predict or store final-answer claims in `JevRunStateRecord`.
- A claim's text and evidence are the only state used by its Jev question; no other claim's evidence can support it.
- Each claim needs its own answer and must meet the threshold independently.
- Empty claims are a pass, not an unavailable result.
- CLAIMS adds no field to `JevAgentSettings`, no runtime-specific branch, and no second Jev request.

## External Dependencies

The run's structured generative handoff model and TypeSafe Jev decision runner are external boundaries. Tests replace those runners with deterministic fakes and make no network calls.

## Known Failure Modes

- Handoff omits or merges a concrete claim, assigns duplicate/invalid ids, or pairs it with unrelated calls.
- Evidence summarizes a claim without naming relevant tool arguments, execution state, and output.
- A read-only call is treated as proof of a write, a failed command as a passing check, or a later revert is ignored.
- Missing or malformed handoff output or missing Jev answers are accidentally treated as a failed user task rather than fail-open availability.
- An unsupported claim is hidden by averaging it with supported claims or by including supported claims in continuation focus.
- CLAIMS and MULTI_PART questions are split into separate Jev requests.

## Historical Regressions

This feature pack captures the design exception discovered while extending the pre-run done-check model: the concrete assertions for CLAIMS cannot exist until the final answer does.

## Test Suite Map

- `tests/test_jev_done.py` covers claim record validation, field descriptions, schema placement, the fixed question contract and token floor, claim extraction/evidence state, one-question-per-claim batching, unsupported-only continuation focus, empty claims, combined checks, and existing done-check behavior. Run with `python -m unittest tests.test_jev_done` or `python scripts/test-jev-multipart-done-criteria.py`.

## Omitted Testing Strategies

- Live provider and end-to-end tests are omitted because they require credentials and produce nondeterministic model judgments; deterministic runner fakes exercise the internal integration boundary.
- Browser, UI, concurrency, load, performance, and persistence strategies are omitted because this is an in-process finish-attempt policy with no browser or concurrent shared-state contract.
- Fuzz and property testing are omitted for now; the bounded id format, duplicate rejection, empty-list behavior, and malformed handoff paths are covered with explicit boundary tests.
