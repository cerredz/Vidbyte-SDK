# Feature: Jev Mid-Run Problem Repair Gate

## High-Level Feature Description

The opt-in `PROBLEMS_RESOLVED` continuation gate reviews problems visible in a JevAgent run at each finish attempt. It requires evidence that each encountered error, failed operation, blocker, or failed validation was fully repaired and successfully revalidated, then separately checks that the original user request was completed after repairs. If any item is unsupported, same-context continuation returns the main agent to its existing loop with the current gate assessment focused on unresolved work. The feature matters because moving past an error is not evidence that it was fixed; an agent should not end a run with a known unresolved problem or stop after repair without finishing the requested work.

## Contract

When enabled in `JevContinuationGateSettings.enabled`, the handoff derives one item for each observed problem and one required original-request-completion item. Jev receives one question per item in the existing combined request. A repair is supported only when run evidence shows the fix and a relevant successful follow-up; a repair summary alone is not enough. Failed items trigger a bounded, same-loop continuation that fixes and revalidates unresolved problems, then completes remaining original-request work. Disabled gates do not add a section or Jev call. Unavailable handoff or Jev evaluation follows the existing fail-open policy.

## Actors / Callers

- SDK callers enable the named gate through `JevRuntimeSettings(continuation_gate=JevContinuationGateSettings(enabled=(JevContinuationGate.PROBLEMS_RESOLVED,)))`.
- `JevHandoff` reviews the run window and emits problem evidence.
- `JevRunState` projects handoff items into the one combined Jev request and scores results.
- `JevDoneContinuation` explains failed items and resumes the same main-agent loop.
- `JevAgent.response` exposes the handoff and latest continuation-gate result.

## Inputs and Preconditions

- The check is enabled and a JevAgent run has reached a finish attempt.
- The handoff receives the original request, run state, main-agent responses, tool calls, their outputs, and final answer.
- Handoff item IDs are valid and unique; exactly one item has kind `request_completion`.
- An observed problem is grounded in the current run; hypothetical issues are excluded.

## Observable Outcomes

- Every observed problem has a separate Jev answer and can independently fail the check.
- The original-request-completion item exists even when no problems were observed.
- A failed item appears in the continuation's Failed checks and Focus sections; resolved siblings do not.
- After repair, revalidation, and completion of remaining original-request work, a later finish attempt can pass.
- The gate result is visible through `JevAgent.response.continuation_gates[JevContinuationGate.PROBLEMS_RESOLVED]`.

## State Transitions

1. The main agent works in its ordinary loop and may encounter a problem.
2. At a finish attempt, the handoff derives current problem items and original-request evidence.
3. Jev judges each item in one combined request with every other enabled check.
4. Passing or unavailable results let the current answer stand under existing policy; failed results continue only while the configured budget remains.
5. On continuation, the main agent repairs and validates unresolved issues, returns to remaining original-request work, and tries to finish again.

## Invariants

- Problem items are derived after work, never predicted by the pre-run state writer.
- One question maps to one dynamic item; missing Jev answers make the check unavailable rather than silently pass.
- Handoff `missing` text is for the main agent and is excluded from Jev evidence.
- The required request-completion item is judged separately from problem repairs.
- All enabled continuation-gate questions share one Jev request per finish attempt.
- Same-context continuation keeps the main loop and history while updating the latest handoff and gate assessment in stable context slots; it does not append duplicate run-state or handoff blocks.
- Continuations remain bounded by existing settings; unavailable dependencies retain existing fail-open behavior.

## External Dependencies

- Existing generative provider for handoff compilation.
- Existing TypeSafe `DecisionModelHelper` for calibrated yes/no judgments.
- Existing prompt catalog and main-agent continuation loop.
- No new dependencies, persistent storage, or endpoints.

## Known Failure Modes

- The handoff model can omit a problem from its extraction; tests can pin representative schema and behavior but cannot prove perfect generative recall.
- The existing fail-open policy allows the run to stand when handoff or Jev is unavailable.
- The existing continuation cap allows an unresolved item to remain after the cap, with the latest failed result recorded.
- Incomplete, duplicate, or malformed handoff items must make the handoff unavailable instead of silently dropping a question.
- An attempted repair without a successful relevant revalidation must remain unresolved.

## Historical Regressions

None yet. Add a dated entry and a focused regression test for each fixed defect.

## Test Suite Map

- `tests/test_jev_done.py` protects typed records, item IDs, schema composition, question layout, dynamic item projection, evidence separation, batching, finish/re-handoff behavior, continuation focus, fail-open cases, and the disabled path.
- `scripts/test-jev-problems-resolved.py` runs the relevant done-check tests with PASS/FAIL labels and an `X/Y tests passed` summary.
- `python lint/run.py` protects placement, module headers, question size/layout, and source contracts.

## Omitted Testing Strategies

- Browser interaction and accessibility are omitted because this SDK capability has no user interface.
- Concurrency and load testing are omitted because one JevAgent instance is already documented for one run at a time and the feature adds no concurrent work.
- Live provider tests are omitted because deterministic CI must not require credentials or external calls; scripted runners cover provider boundaries and failure modes.
- Fuzzing and mutation testing are omitted for the first version; malformed IDs, duplicate items, missing answers, and source-level guards receive direct deterministic tests.
- Installed-package smoke testing is covered by the existing SDK package gate, not a second feature-specific installation harness.
