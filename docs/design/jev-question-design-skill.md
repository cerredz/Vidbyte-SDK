# Jev question design skill

## What and why

`JevAgent` is going to gain named capabilities that ask Jev fixed internal questions: scope fit, effort budget, decomposition gating, and later ones. Jev (TypeSafe's System One model) is a calibrated classifier, not a reasoning model. It picks among options you define and returns probabilities. It does not plan, count, compare dates, or generate text. A capability only works if its questions are written so that Jev *matches* the state against a definition you supply instead of *inferring* the answer through several steps.

Today nothing in the repository says how to write such a question. `skills/jev-agent/SKILL.md` covers the package boundary and settings, and its one example question ("Is another iteration likely to materially improve the answer?") is a forecast, which is the exact shape this guidance warns against.

This change adds a contributor skill, `skills/asking-jev-questions/SKILL.md`, that teaches question design as a set of pillars with worked examples. It is documentation only.

## How it works

The skill is one Markdown file with YAML frontmatter, in the same format as `skills/jev-agent/SKILL.md`. It contains:

1. **The core idea.** Phrasing does not delete reasoning. It moves it to the question author (definitions), to code (arithmetic, combination, actions), or to the main model (planning, generation). Jev keeps only the matching step.
2. **Fifteen pillars.** Each pillar has a rule, a reason tied to how Jev behaves, and a short bad/good contrast. The pillars are grounded in TypeSafe's published guidance, especially the `jev-1.13` jaggedness page (literal reading, math, dates, indirection, large state, contradictory criteria, structural invariants, generation).
3. **A two-second test** for checking any question before it ships.
4. **Few-shot examples** as full request bodies in the wire shape `TypeSafeProvider` sends (`state`, `questions` with `type`, `instructions`, `criteria`), each followed by the code-side action for every answer. The examples cover the three capabilities discussed for `JevAgent`: scope fit, effort budget (as feature questions combined in code), decomposition gating, plus a mid-run progress check that replaces the forecast example.
5. **A pre-ship checklist.**

`skills/jev-agent/SKILL.md` changes in two places: step 3 of the change workflow points to the new skill, and the capability design example swaps the forecast question for an observation.

## Files

| Action | Path | Change |
| --- | --- | --- |
| Create | `skills/asking-jev-questions/SKILL.md` | The new skill. |
| Edit | `skills/jev-agent/SKILL.md` | Link to the new skill; replace the forecast example question. |
| Create | `docs/design/jev-question-design-skill.md` | This document. |

No Python, tests, or package data change. `pyproject.toml` already includes `skills/*/*.md` in the source distribution, so the new file is picked up without a packaging change.

## Risks and open questions

- **The guidance is not yet measured on Vidbyte traffic.** The pillars come from TypeSafe's own documentation and from how the task types are structured, not from an eval of `JevAgent` capabilities. The skill says so and tells the implementer to build a labeled set before choosing thresholds.
- **Model drift.** The jaggedness list is versioned (`jev-1.13`, reviewed 2026-09-17). The skill names the version it was written against so a reader knows when to recheck it.
- **Thresholds in the examples are illustrative.** The skill labels them as starting points, not tuned values.

## Verification

- Every example request uses only fields that `JevQuestion` and `TypeSafeWireQuestion` accept (`noul` criteria keys limited to `true`/`false`; `choice` has at least 2 options; `score` has 2–10 levels). Check this by building each example as a `JevDecisionRequest` in a throwaway script.
- `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py` pass.
- The draft PR's required checks are green.
