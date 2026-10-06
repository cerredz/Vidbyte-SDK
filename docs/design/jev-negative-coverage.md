# Negative inspection coverage

## Problem

A final answer can imply that a requested research, audit, review, test, or source-inspection target has no findings even though the run contains no evidence that the target was inspected. The existing CLAIMS check evaluates factual answer assertions broadly; this check focuses on the narrower, high-risk combination of a requested inspection, a zero-findings or all-clear conclusion, and missing inspection evidence. It does not require a finding to exist.

## Design

Add an opt-in `JevDoneCheck.NEGATIVE_COVERAGE`. `JevRunState` derives inspection targets from the request before work. `JevHandoff` records, for each target, whether the final answer gives an explicit or implicit no-findings/clear conclusion, what run evidence shows the target was inspected, and whether the answer explicitly says the inspection remains incomplete. Jev receives each target with the request and those observations, then recognizes whether the risky combination is present. An explicit incomplete report also fails when inspection evidence is absent, so the continuation directs the agent to finish the requested inspection. Evidence of inspection passes whether it found zero or many issues. No negative conclusion and no incomplete-status claim passes. Missing or failed handoff/Jev calls continue to fail open.

The new check remains in the existing batched done-check flow. Its continuation explanation includes the requested target and the handoff gap; it asks for inspection evidence, not for a non-empty finding list. CLAIMS remains responsible for general factual support.

## Files

- `vidbyte/lib/enums/jev.py`, `vidbyte/lib/constants/jev.py`, `vidbyte/lib/dataclasses/jev.py`: check key, threshold/state fields, typed request and handoff records.
- `vidbyte/lib/jev/done/negative_coverage.py`, `done.py`, `README.md`, `__init__.py`: fixed question and registry/export.
- `vidbyte/agents/jev/done/run_state.py`, `handoff.py`, `continuation/done.py`: request-derived targets, per-finish observations, judging, and actionable focus.
- Public exports, `README.md`, and `skills/jev-agent/SKILL.md`: enablement and behavioral contract.

## Risks

The generative run-state and handoff writers can omit a target or misread a vague zero-findings conclusion. The design keeps items anchored to explicit inspection requests, requires exact target coverage in the handoff, and scopes the question to observed text and evidence. The advisory check fails open when structured evidence is unavailable and is bounded by the existing continuation limit.

## Verification

Review the question against `skills/asking-jev-questions/SKILL.md`, inspect the final diff, and run `git diff --check`. Per instruction, do not add or run tests or local CI; inspect automatic PR CI after opening the draft PR.