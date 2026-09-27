# Jev research tips and clarity preflight tuning

## What and why

The asking-jev-questions skill was written from TypeSafe's own documentation. Since Jev launched (15 September 2026), ten arXiv papers and a set of public audit repositories have measured which question framings actually change Jev's accuracy. This change does two things with that evidence.

1. **Skill update.** Add the 25 research-backed tips to `skills/asking-jev-questions/SKILL.md`, each with its evidence and how to apply it, plus a "Research on Jev" section that links each paper and says what strategy it tested and what it found. Update the checklist, the "Writing a full question" rules, and the sources.
2. **Clarity preflight tuning.** Apply the tips that the current 14 clarity questions and their scoring are missing.

## What the clarity preset is missing, and the fix

| Tip | Gap on `main` | Fix |
|---|---|---|
| 7. Language | Nothing says a request may be informal or in another language | New shared rule `JUDGE_MEANING` in every brief |
| 14. Authority claims | `IGNORE_CLAIMS` covers "this is clear" but not "already approved" or instructions to the checker | Extend `IGNORE_CLAIMS` |
| 15. One message | `REQUEST_STATE` does not say the state is exactly one message | Extend `REQUEST_STATE` |
| 8. A way out | No question says where an empty message or a greeting goes | One explicit no-task rule per question, placed on the side the question's existing rules already imply |
| 13 / exclusions. Pasted material | A pasted document full of commands can read as the user's action | Exclusion rule in the action question |
| 5. Stale knowledge | Time question lets Jev decide from memory that a result never changes; information question lets Jev treat the user's own material as general knowledge | One rule in each |
| 23. Averaging hides a clear failure | Mean P(yes) of 14 questions passes a request with one or two clear no answers, such as "Fix the bug in the file." (target and material missing) | Add a per-question veto: any answer with P(yes) below `JEV_CLARITY_VETO_THRESHOLD` (0.2) fails the preset by itself |
| 24. Gate, then hide | A greeting fails most checks, and the clarifier is handed every one of their gaps | The preset names a gate question (`clarity.action`); when it fails, the clarifier gets only its gap |

## How it works

- `JevPresetDefinition` gains two optional fields: `veto` (a probability) and `gate` (a question key that must be one of the preset's keys).
- `DecisionModelRunner.score_noul(answers, names, threshold, veto=None)` still averages P(yes). With a veto, it also fails when any single answer is below the veto. Owner feedback put this rule on the runner.
- `JevPreflightGate._score` passes the definition's veto.
- `JevClarificationAgent.gaps` returns only the gate question's key when that question failed.
- Question text changes stay inside the existing `JevBrief` and `JevCriterion` layout. Examples, definitions, and criteria are untouched except where a rule above needs a mirror.

## Files

- `skills/asking-jev-questions/SKILL.md`
- `vidbyte/lib/jev/preflight/clarity.py`
- `vidbyte/lib/constants/jev.py`, `vidbyte/lib/dataclasses/jev.py`, `vidbyte/lib/jev/presets.py`
- `vidbyte/lib/runners/decision.py`, `vidbyte/agents/jev/gate/gate.py`, `vidbyte/agents/jev/gate/clarification.py`
- `tests/test_jev_preflight.py`

## Out of scope

These tips need labeled data or a primitive change, so they are listed in the skill but not built: per-question thresholds and recalibration fitted on labels (tips 21, 22), a learned combination (tip 23, second half), Score instead of noul (tip 16), and a paraphrase probe set (tip 25). The veto threshold (0.2) is a starting point, not a tuned value, like the existing 0.75.

## Risks

- The veto makes the preset stricter, so more requests stop for clarification. Fail-open behavior is unchanged.
- Adding rules lengthens every brief. Input tokens are cheap for Jev, and the skill already favors full briefs.

## Verification

- New tests: the veto in `score_noul`, the definition's veto and gate validation, a gate run where one clear no fails an otherwise high-scoring request, and gate-only gaps when the action check fails. Also layout tests confirming every brief carries `JUDGE_MEANING` and a no-task rule.
- `python scripts/test-jev-preflight.py`, then the full local gate `python scripts/run_ci.py`, then PR CI.
