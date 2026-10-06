# Feature: JevAgent CLAIMS continuation

## High-Level Feature Description

The opt-in CLAIMS done check reviews concrete, checkable factual assertions in JevAgent's final answer. Each parent claim carries five context groups: identity, scope, kind, output, and its assertions with completion criteria. The check pairs each assertion with the parent context and relevant tool-call evidence, asks Jev one yes/no question per assertion, and sends only unsupported assertions back to the main agent. This prevents an unsupported self-report from being mistaken for evidence while leaving the ordinary answer intact if the checker is unavailable.

## Contract

- Claims come from the current final answer, not a predicted list written before the agent starts.
- Each parent claim has `identity` (`title`, `description`, `intent`), `scope` (`scope`, `qualifications`), `kind`, `output`, and one or more atomic assertions.
- Each assertion has a stable id, exact factual statement, and one observable `completion_criteria` string. Parent and assertion ids combine as `parent_id.assertion_id` for state entries and answers.
- Every Jev state entry repeats the five context groups for exactly one assertion and pairs them with tool-call evidence or an explicit no-evidence statement.
- Jev's judgment uses only that assertion's context and evidence; it does not treat the final answer or the handoff's `missing` summary as evidence.
- One unsupported assertion fails the parent claim regardless of the mean score; continuation focus includes only failed assertions and their specific evidence gaps.
- An answer with no concrete, checkable factual assertions adds no CLAIMS questions and passes. If another enabled done check has items, its questions still use the shared Jev request. Missing handoff evidence, missing credentials, or provider errors fail open.
- Every enabled done check still shares one Jev request per finish attempt.

## Actors / Callers

An SDK caller enables CLAIMS with `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.CLAIMS,)))`. JevRuntime invokes the done check when the main agent tries to finish. The handoff model extracts rich parent claims and evidence; Jev judges each assertion; the continuation prompt returns only unsupported assertion references, parent context, tool evidence, and gaps.

## Inputs and Preconditions

The main agent must have a final answer and an available handoff model. The handoff sees the original request, the run-state record, the main agent's responses, tool calls with arguments/state/output, and the final answer. Claim ids must be unique lowercase identifiers accepted by `JEV_DELIVERABLE_ID_PATTERN`.

## Observable Outcomes

`JevAgent.response.handoff.claims` contains structured claim/evidence/missing records. `JevAgent.response.done[JevDoneCheck.CLAIMS]` reports a score over assertions, answers keyed by `parent_id.assertion_id`, incomplete parent claim ids, availability, and pass status. On a failed check, the next main-agent prompt includes only unsupported assertions, their full context, tool evidence, and gaps.

## State Transitions

Each finish attempt recompiles claims from that attempt's final answer. Supported claims do not appear in continuation focus; unsupported claims trigger another loop iteration until corrected or the configured continuation cap is reached. A checker or handoff failure does not block the main agent's answer.

## Invariants

- Do not predict or store final-answer claims in `JevRunStateRecord`.
- One Jev question judges exactly one assertion using the parent claim's identity, scope, kind, output, assertion statement, completion criterion, and evidence.
- Evidence from another parent claim or sibling assertion cannot support the named assertion.
- Each assertion needs its own answer and must meet the threshold independently; any failing assertion marks its parent incomplete.
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

- `tests/test_jev_done.py` covers claim record validation, field descriptions, schema placement, the fixed question contract and token floor, claim extraction/evidence state, one-question-per-assertion batching, assertion scoring and parent aggregation, unsupported-only continuation focus, empty claims, combined checks, and existing done-check behavior. Run with `python -m unittest tests.test_jev_done` or `python scripts/test-jev-multipart-done-criteria.py`.

## Omitted Testing Strategies

- Live provider and end-to-end tests are omitted because they require credentials and produce nondeterministic model judgments; deterministic runner fakes exercise the internal integration boundary.
- Browser, UI, concurrency, load, performance, and persistence strategies are omitted because this is an in-process finish-attempt policy with no browser or concurrent shared-state contract.
- Fuzz and property testing are omitted for now; the bounded id format, duplicate rejection, empty-list behavior, and malformed handoff paths are covered with explicit boundary tests.
