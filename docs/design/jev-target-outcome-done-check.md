# JevAgent target outcome done check

## Problem

An agent can show a nearby milestone, such as a successful build or smoke test, without showing that the user's requested result occurred on the intended target and at the requested scope. `MULTI_PART` checks whether requested outputs appear, while `CLAIMS` checks whether final-answer claims have supporting evidence. This check evaluates whether the evidence reaches the requested outcome on the actual target beyond a proxy milestone.

## Design

Add the opt-in `JevDoneCheck.TARGET_OUTCOME` request-derived check. The run-state writer lists only distinct target outcomes that the request makes applicable and can state without guessing. Each item contains four named fields: `outcome`, `target`, `scope`, and `completion_criterion`. The handoff records any `observed_proxy`, `direct_evidence`, and a separate `missing` note; a proxy is run evidence and cannot be known from the request alone. The batched Jev state projects those four item fields plus `observed_proxy` and `direct_evidence` (six named context fields); it does not include `missing`.

Jev makes one positive recognition judgment per item: whether the direct evidence demonstrates the requested outcome on the actual target, at the stated scope and criterion, beyond the observed proxy. Evidence may refer to tool results, artifacts, or the final answer only when that answer itself is the target outcome. A build, installation, plan, or smoke test is context for the proxy and does not establish the target result by itself. This is a recognition check; it does not ask Jev to infer, calculate, or generate outcomes.

The run-state schema may return an empty list when a request has no separate real target outcome, or when defining one would require inventing a target or criterion. The check then passes with no Jev question. An item whose required target, scope, or completion criterion is genuinely inapplicable must not be synthesized; the run-state writer omits it, and the empty-list path remains a clean no-op. The handoff must return one evidence entry for each run-state id; if it cannot compile a valid section, the check becomes unavailable and fails open. Stable ids reuse the existing lowercase `JEV_DELIVERABLE_ID_PATTERN` and unique-id validation. The initial `JEV_TARGET_OUTCOME_THRESHOLD` is 0.8, used as both mean threshold and veto; it is a starting point, not tuned on labeled examples.

On a failed judgment, continue the same main-agent loop with only the incomplete outcomes in Focus, including the target, scope, completion criterion, observed proxy, and handoff `missing` note. On unavailable evidence or Jev, allow the finish attempt to stand. This check does not replace `MULTI_PART` output presence/completeness or `CLAIMS` assertion support: its decision turns on whether evidence is for the right target and level.

## Files

- Extend the done-check enum, question key, threshold, shared field constants, typed run-state and handoff payloads/records, registry, exports, and done-question README.
- Add the target-outcome Jev question module.
- Extend `JevRunState` state assembly, scoring, and `JevDoneContinuation` failure explanation.
- Update Jev public exports and user-facing JevAgent docs with an enabling example.

## Risks and verification

The main risk is confusing a proxy with direct evidence or treating an answer artifact as a separate target. The question explicitly defines both and assigns answer-only tasks to the no-item path. Check formatting and structural policy with lint; tests must not be added or run unless requested, per the task instruction. Hosted PR CI is observed if available, not manually dispatched.
