# Jev phase progress done check

## Problem

A run can consume its time in planning, investigation, or evidence gathering and then attempt to finish without entering the work the user requested. MULTI_PART checks whether requested outputs were delivered, while CLAIMS checks whether final-answer assertions have run evidence; neither asks whether a run transitioned from preparation into the requested work. The new optional `PHASE_PROGRESS` done check evaluates that transition without treating a requested research, analysis, or planning deliverable as mere preparation.

## Design

`JevRunState` derives only meaningful, request-required outcome stages before the main run. The generative writer names stages from the request rather than selecting from a fixed taxonomy, and it returns no items when the request identifies no meaningful staged work. For each stage, the run state records four named reference fields: stage identity, required transition/result, request scope, and output criterion. At each finish attempt, `JevHandoff` compiles actual run evidence and a separate missing note for every state id. The Jev projection combines the four reference fields with observed evidence as its fifth named field, never including the handoff's missing note.

Jev receives one positive recognition question per required outcome stage in the existing combined request. A yes means the evidence shows the requested stage was reached, or shows a concrete budget/blocking constraint that prevented further progress; a no means the run stopped after preparation while the requested work remained actionable. This makes an observed blocker a stopping condition and avoids repeated continuations after a genuine constraint. No verification stage is invented: verification is represented only when the request requires it. Empty stage lists pass without a Jev call; unavailable run state, handoff, or Jev answer fails open. Incomplete stages are sent to the continuation prompt in the user's terms.

## Files

- Add `PHASE_PROGRESS` and its question key, threshold and state field constants, and request-derived/evidence payloads plus frozen records in the existing JEV enum, constants, and dataclass modules.
- Add the fixed question in `vidbyte/lib/jev/done/phase_progress.py`; register and export it through the done registry and README.
- Add the enabled run-state and handoff schema sections, conversions, batched Jev state projection, scoring, and continuation explanation to the existing done-check classes.
- Export the new response records from the JevAgent public modules and package root; update module headers and the JevAgent done-check guide.

## Risks and boundaries

The run-state writer must distinguish a request's actual outcome (including research or analysis when requested) from preparatory activity used to reach another requested result. The handoff must identify genuine blockers from observed run evidence rather than accepting a bare final-answer claim of being blocked. The check judges progress into required work, not quality, completeness of each deliverable, or generic factual support; those remain separate checks. Runtime, JevAgent wiring, settings, and general system prompts remain unchanged.

## Verification

Inspect the resulting diffs and run non-test lint/static checks. Tests will not be added or run in this branch, per the task's explicit verification constraint; the draft PR's CI provides the automated test signal.
