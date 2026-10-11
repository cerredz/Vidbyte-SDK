# Jev question design skill

## What and why

`JevAgent` is going to gain named capabilities that ask Jev fixed internal questions: scope fit, effort budget, decomposition gating, and later ones. Jev (TypeSafe's System One model) is a calibrated classifier, not a reasoning model. It picks among options you define and returns probabilities. It does not plan, count, compare dates, or generate text. A capability only works if its questions are written so that Jev *matches* the state against a definition you supply instead of *inferring* the answer through several steps.

Today nothing in the repository says how to write such a question. `skills/jev-agent/SKILL.md` covers the package boundary and settings, and its one example question ("Is another iteration likely to materially improve the answer?") is a forecast, which is the exact shape this guidance warns against.

This change adds a contributor skill, `skills/asking-jev-questions/SKILL.md`, that teaches question design as a set of pillars with worked examples. It is documentation only.

## How it works

The skill is one Markdown file with YAML frontmatter, in the same format as `skills/jev-agent/SKILL.md`. It contains:

1. **What we are trying to accomplish.** Several paragraphs on the goal: rewrite questions that seem to need reasoning so the reasoning is already done when Jev reads them. Definitions and boundaries go into the question text, facts and combination go into code, and generation goes to a generative model. Jev keeps one recognition step. The section uses an expert-versus-checklist picture and states the limits (information not in the state, generation, reasoning that cannot be written down in advance).
2. **A method.** Write the naive question, list the hidden steps, tag each (definition, fact, lookup, combination, forecast, generation, recognition), and move every step except recognition to its owner. Includes one worked pass.
3. **The two-second test** for checking a finished question.
4. **Twenty-five strategies in six groups:** move the meaning into the question, split the reasoning, do non-judgment work in code, shape the state, time the question, shape the answer. Each strategy says what it means, why it works, and how to apply it, most with a before/after. The strategies are grounded in TypeSafe's published guidance, especially the `jev-1.13` jaggedness page (literal reading, math, dates, indirection, large state, contradictory criteria, structural invariants, generation) and its structure and batching docs.
5. **A checklist** keyed to strategy numbers, and a short note on how the rules apply inside `JevAgent` (definitions from named settings, fallback to the linear loop).
6. **Fifteen general before/after examples** from domains unrelated to the runtime (support urgency, phishing, resumes, reviews, contracts, meeting notes, invoices, bug severity, moderation, diets, record matching, retrieval, churn, schema changes, team routing). Each names the hidden steps, gives the rewritten question as a four-to-five-sentence `instructions` text with its options, and says what code does with the answer.

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

- Every rewritten example question is four or five sentences long, and every example uses a question type and option count that `JevQuestion` accepts (`noul` criteria keys limited to `true`/`false`; `choice` has at least 2 options; `score` has 2–10 levels).
- `python lint/run.py`, `python scripts/run_ci.py --stage source`, and `python scripts/run_ci.py` pass.
- The draft PR's required checks are green.
