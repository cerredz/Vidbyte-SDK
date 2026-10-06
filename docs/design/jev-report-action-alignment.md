# JEV report/action alignment done check

## Purpose

Add one opt-in continuation check for material differences between an agent's visible plan, the work recorded during the run, and its final account. It is enabled with `JevDoneCheck.REPORT_ACTION_ALIGNMENT` through the existing `JevContinualSettings.checks` field. The check catches false reports of completed actions and claims of overall completion when request-relevant work remains; it does not treat every changed or abandoned plan step as required work.

## Approach

The final account and plan do not exist as stable inputs before execution, so `JevHandoff` will generate one item per material explicit plan or commitment in an earlier main-agent response that the final account refers to or implies was carried out. Each item will carry five named fields: the visible plan or commitment, recorded tool actions/results or delivered artifacts, the final account's description, relevance to the original request, and evidence. The run-state writer will not predict these items. The handoff includes aligned and potentially misaligned items; Jev determines whether the report matches the execution and request relevance. When no eligible visible plan/account relationship exists, the check passes without a Jev request.

One fixed positive Noul question per candidate will ask whether the final account accurately reflects recorded execution while accounting for justified plan changes and whether the described completion fits the request's actual requirements. A low P(yes) marks that candidate incomplete and sends the focused discrepancy back through the existing same-loop continuation. Every enabled done check remains in the existing single batched Jev request. Missing handoff or Jev results fail open. Records are frozen and validate ids/text; generated schema fields have at least five sentences of guidance. CLAIMS remains distinct: it checks individual factual final-answer assertions, while this check evaluates the relationship among prior commitments, observed execution, and retrospective reporting.

## Files

- Extend `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`, and `vidbyte/lib/dataclasses/jev.py` with the named check, key, threshold/state fields, and typed handoff records/payloads.
- Add `vidbyte/lib/jev/done/report_action_alignment.py`; register and export its question through the existing done registry and package surfaces.
- Extend `vidbyte/agents/jev/done/handoff.py`, `run_state.py`, and `vidbyte/agents/jev/continuation/done.py` to produce, batch, score, and focus the dynamic candidates.
- Update the done-check and JevAgent READMEs with the preset and an API example.

## Risks and verification

The handoff's candidate selection must not equate an unfulfilled plan with unfinished user work; its request-relevance field and the question's boundaries make that distinction explicit. The check remains opt-in and fail-open. Verify with lint and `git diff --check`; do not add or run tests or test-running CI scripts for this change.

## Research basis

The motivating observation comes from [Kraishan and Jitkajornwanich, “Plans They Abandon, Reports They Author: The Narrative Layer of Autonomous Agents” (2026)](https://arxiv.org/html/2609.12205v1). In 5,851 developer sessions, their analysis found that reports tracked execution when agents followed their plans and drifted toward plans as execution diverged. The paper does not establish that every unexecuted plan step was required work; this check therefore evaluates request relevance and permits accurately reported, unnecessary, or superseded plan changes.
