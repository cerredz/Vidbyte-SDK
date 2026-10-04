# Feature: JevAgent dynamic input exhaustion

## High-Level Feature Description

The opt-in `INPUT_EXHAUSTION` continuation gate detects when an agent stops before traversing a dynamically discovered collection it was explicitly asked to inspect completely. The collection may be paginated, cursor-based, or discovered while following a source. The feature matters because a plausible answer from the first page or a partial batch can conceal requested work that remains. Finite named files or bounded user-supplied inputs belong to the separate input-set coverage gate.

## Contract

- Run state records one stable obligation for each explicit exhaustive traversal in the request, with the collection, scope, unit being traversed, and the stated stopping condition.
- Handoff evidence is recompiled from the current run trace on every finish attempt and includes distinct trace-backed visited units, source-reported totals, continuation positions, terminal evidence, failed retrievals, last position, and an actionable gap.
- Code compares distinct visited unit IDs with an explicit request-stated total first, or a comparable source-reported total when the request has no total; the source total may supplement or conflict with the requested bound. A known total is complete only when the distinct count matches and there is no outstanding cursor or failed retrieval.
- Counts are compared only when identifier units match the requested unit. If the request explicitly states N units and the handoff uses a mismatched or unknown unit type, an end-of-results signal cannot substitute for verifying N; the obligation remains incomplete.
- Jev receives one question per obligation in the same combined decision request as other enabled continuation gates. Jev recognizes whether the provided evidence establishes the stated exhaustion condition; it does not count units or invent an unseen universe.
- When no total is available, the evidence must contain an affirmative source end-of-results signal. A first page, sample, search snippet, failed fetch, or lack of a next-page call is not terminal evidence.
- An outstanding continuation or failed retrieval is concrete incompleteness. A readable handoff without a usable expected or source total and without affirmative terminal evidence is an incomplete obligation and triggers continuation; unknown universe size does not make a valid missing-completion-evidence handoff unavailable. Missing or malformed run state or handoff, failed Jev calls, and missing answers remain unavailable and fail open.
- A rejected obligation sends the main agent back through the same loop with the collection, last known page/cursor, missing evidence, and an actionable next step. The continuation cap remains effective.
- Handoff `missing` is for the main agent's continuation only and never enters Jev state. Every finish attempt uses one batched Jev request.

## Actors / Callers

SDK users enable `JevContinuationGate.INPUT_EXHAUSTION` in `JevContinuationGateSettings.enabled`, configured through `JevRuntimeSettings.continuation_gate`. `JevRunState` writes obligations before the main loop; `JevHandoff` compiles trace evidence at each finish attempt; Jev recognizes each collection's evidence; `JevDoneContinuation` focuses the same-loop continuation.

## Inputs and Preconditions

The request explicitly requires exhaustive traversal of a collection whose members or extent may be discovered during work. Handoff receives the request, the immutable run state, main-agent responses, tool calls and outputs, and current final answer. Collection and evidence identifiers are stable lowercase IDs.

## Observable Outcomes

`JevAgent.response.run_state` exposes typed traversal obligations; `.handoff` exposes typed evidence, extracted counts and positions, terminal/failure signals, and continuation gaps; `.continuation_gates[JevContinuationGate.INPUT_EXHAUSTION]` exposes availability, score, answers, pass status, and incomplete obligation IDs. In same-context mode, failure resumes the current main-agent loop with the latest gate assessment and evidence snapshots; only incomplete obligations appear in the failed-gate focus.

## Failure Inventory

- Run-state model omits or invents an obligation, or gives duplicate IDs.
- Handoff drops an obligation, merges IDs, invents visited IDs, or omits a current cursor, failed fetch, total, or terminal marker.
- Duplicate visited IDs are counted more than once, or a source total is compared with units of a different kind.
- A first page, a representative sample, search snippet, failed fetch, or silence about the next page is mistaken for completion.
- A source-reported total is reached while a continuation remains or a retrieval failed.
- An unknown total without affirmative end-of-results evidence is incorrectly passed instead of failed as an unmet exhaustive request.
- Missing run state, handoff, Jev reply, or one expected answer blocks the main answer instead of failing open.
- Input exhaustion is split into a separate Jev request, includes handoff `missing` in Jev state, or sends already-complete collections in failed-gate focus.
- Continuation feedback omits the last known page/cursor or an actionable next step.

## Test Suite Map

- `tests/test_jev_done.py` covers schemas, typed-record validation, question contract and token minimum, extraction boundaries, count/duplicate logic, terminal and incomplete signals, unknown-total failure and provider fail-open behavior, combined requests, same-loop continuation focus, cap, and provider failures.
- `scripts/test-jev-multipart-done-criteria.py` runs the exhaustive focused done-check test module, including input exhaustion coverage.

## Omitted Testing Strategies

- Live provider tests are omitted because they need credentials and make nondeterministic judgments; scripted model and decision runners protect the integration boundary.
- Browser, concurrency, persistence, and UI tests are omitted because the feature is an in-process advisory finish-attempt check with no browser or shared-storage contract.
- Fuzz/property tests are deferred; explicit tests cover identifier validation, duplicate rejection, distinct-unit counting, missing answers, and malformed typed handoff paths.

## Historical Regressions

No prior regression. Add future fixes here with the test that preserves the behavior.
