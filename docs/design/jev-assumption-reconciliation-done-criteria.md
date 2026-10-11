# Assumption reconciliation done check

## Problem and scope

An agent can state an assumption early, use it to guide later work, then receive concrete run evidence that changes the premise without revisiting downstream decisions or artifacts. This can leave a stale result even when no tool call failed and no validation reported an error. The opt-in `ASSUMPTIONS_RECONCILED` done check addresses that narrow case; it does not treat every plan change, uncertain premise, or unverified assumption as a mistake, and does not repeat `PROBLEMS_RESOLVED`'s error-repair-and-revalidation gate.

The research paper [arXiv:2609.17930v1](https://arxiv.org/html/2609.17930v1) reports that agents often fail to detect an initial mistake and that recovery varies with environmental feedback. That result motivates checking whether later observations were incorporated, but it does not evaluate this preset or establish that every changed premise causes downstream harm.

## Design

Keep this as one new `JevDoneCheck` and one question key, `assumptions_reconciled` and `assumptions_reconciled.revisited`. Items are post-run-derived: `JevHandoff` extracts one item for each materially changed assumption only when the original assumption was explicit in an early main-agent response or tool context, later run evidence concretely contradicts or materially changes it, and identifiable downstream work depended on it. Include the item whether downstream work was later revised, left unchanged, or made irrelevant; those outcomes are what Jev judges. Exclude premises that were merely uncertain or unverified and changes in plan without a contradicted premise.

Each item has six named Jev context fields: `original_assumption`, `original_basis`, `later_observation`, `affected_work`, `revision`, and `evidence`. Their structured-field descriptions instruct the handoff to report source-grounded observations and separate its human-readable `missing` summary. The `missing` summary is handed to the main agent but is never included in Jev's state. The question is one positive Noul recognition judgment: whether run evidence shows that dependent work was reconciled after the premise changed. Acknowledgment alone fails; an observable downstream revision or evidence that the work was irrelevant passes. An empty item list passes without a Jev request; an unavailable handoff or decision remains fail-open.

Register the check with the existing `JevDoneRegistry`, add a handoff schema and frozen records, and project one question per item into the existing shared `JevRunState.combine()` request. Score answers through `_judge` using the check's own threshold and veto, and add item-specific continuation feedback. Do not add a second Jev call, change generic prompts, runtime/agent wiring, or settings. Document an enablement example using `JevContinualSettings(checks=(JevDoneCheck.ASSUMPTIONS_RECONCILED,))`.

## Files in scope

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/dataclasses/jev.py`
- `vidbyte/lib/jev/done/assumptions_reconciled.py`, `done.py`, `__init__.py`, and `README.md`
- `vidbyte/agents/jev/done/handoff.py`, `run_state.py`, and `vidbyte/agents/jev/continuation/done.py`
- Public record exports in `vidbyte/agents/jev/__init__.py`, `vidbyte/agents/__init__.py`, and `vidbyte/__init__.py`
- `vidbyte/lib/jev/done/README.md`, the `skills/jev-agent/SKILL.md` guidance, the root `README.md` enablement example, and this design document

## Risks and verification

The handoff is generative, so it may miss an assumption or misidentify its consequences; strict extraction criteria and fail-open behavior keep an unavailable or absent item list from blocking a run. The threshold is a starting point, not a calibrated value. Verify with lint, import/compile checks, static checks, and `git diff --check`; do not add or run tests or CI scripts that run tests. Observe automatically dispatched CI if available, and open one draft PR into `main`.
