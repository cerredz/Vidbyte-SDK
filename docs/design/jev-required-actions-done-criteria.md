# JevAgent required actions done check

## Problem and scope

`REQUIRED_ACTIONS` keeps a JevAgent run from finishing after a plausible answer when the request explicitly required work procedures or actions that are independently observable in the run. It covers stated actions, not every step that might be useful. It complements `MULTI_PART`, which checks requested outputs, and `CLAIMS`, which checks final-answer factual claims.

## Design

At run start, the existing run-state agent extracts only explicit action obligations from the request. Each item has a stable id, the action and target in the user's terms, an observable completion condition, and predecessor ids only where the user explicitly specified an order. An action is not added merely because it is conventional, helpful, or needed to create an output.

At each finish attempt, the existing handoff agent compiles per-action evidence from the actual ordered tool-call trace, including arguments, execution state, outputs, command/test output, and observable delegation/return evidence. It returns matching trace indices with each item. Attempts, errors, unanswered delegation, final-answer assertions, and summaries alone do not establish successful completion. Jev receives one positive recognition question per action over the run-state condition and handoff evidence; deterministic code applies the threshold and vetoes an otherwise positive answer unless a successful completion call is cited. For explicitly ordered actions, code also verifies that predecessor completion indices are present and earlier; missing or reversed order fails the dependent item. Evidence gaps remain with the handoff and continuation text, never in Jev state.

The check joins the existing single batched Jev request. Missing run state, handoff, or Jev response fails open. A failed item vetoes the check and contributes its failed question, action, and exact gap to the standard same-loop continuation message, subject to the existing continuation cap.

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`, and `vidbyte/lib/dataclasses/jev.py`: public check and question keys, threshold and state fields, structured payloads, and immutable records.
- `vidbyte/lib/jev/done/required_actions.py`, registry, package exports, and README: the fixed one-action question and registration.
- `vidbyte/agents/jev/done/run_state.py`, `handoff.py`, and `vidbyte/agents/jev/continuation/done.py`: request-derived action extraction, per-attempt evidence compilation, scoring/order enforcement, and continuation focus.
- `tests/test_jev_done.py` and `tests/features/jev_required_actions/FEATURE.md`: contracts for explicit-only extraction, evidence requirements, order, batching, continuation, and fail-open behavior.
- Public exports, source headers, `skills/jev-agent/SKILL.md`, and `skills/jev-continuation/SKILL.md`: the user-facing preset and extension guidance.

## Risks and limits

Generative extraction and handoff can omit or mischaracterize an obligation or trace match; the preset therefore asks for direct evidence, keeps the user request beside the item, and fails open on unavailable model stages. Ordered dependencies require successful trace indices for both actions; absent indices fail the dependent action instead of silently passing. This advisory gate cannot prove hidden work absent from the recorded run.

## Verification

Use deterministic scripted runners; exercise extraction and schemas, one-question-per-action recognition, attempts versus successful outcomes, valid and invalid order, multiple enabled checks in one request, same-loop continuation/cap, and unavailable run-state/handoff/Jev paths. Run the focused Jev done checks, lint, source/package CI stages, and manually dispatched CI, Static policy, and Actionlint workflows for the draft PR.
