# JEV can-simplify done check

## Goal

Add an opt-in `CAN_SIMPLIFY` continuation check that catches a concrete, behavior-preserving way to reduce implementation complexity before the main agent finishes. The check uses the existing `JevDoneContinuation` and is advisory when its inputs are unavailable.

## Design

The run-state writer defines the implementation scope and requirements that a simplification must preserve from the user's request, before work starts. At each finish attempt, the handoff writer reports implementation evidence and any concrete simpler alternative, including why it preserves those requirements; its `missing` field gives the main agent a concise action. Jev receives the scope, preservation constraints, and evidence, and answers whether the implementation can stand as-is without a meaningful simplification. A confident no fails the check and sends the main agent back in the same loop. The failed-check text and Focus section carry the specific alternative and preservation constraints. A missing run state, handoff, or Jev answer fails open.

The check is one implementation-wide item, so it asks one question per finish attempt and joins the existing batched Jev request. It does not add a new continuation class, runtime branch, setting, or system prompt.

## Files

- Add the check enum/key, threshold and state constants, payloads and frozen records, question, registry entry, and run-state/handoff/continuation match cases.
- Export the response records, update the continuation prompt, done-check guides, README, and this design document.
- Extend `tests/test_jev_done.py` for schema, question, continuation, fail-open, and batching behavior.

## Risks

The handoff model can overlook a simpler alternative or propose one that changes behavior. The question therefore requires evidence for a concrete alternative and preservation of the request's stated requirements; the continuation prompt asks the main agent to preserve required behavior and scope. The check remains advisory and bounded by the existing continuation limit.

## Verification

Run `python scripts/test-jev-multipart-done-criteria.py`, `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py --stage package`.
