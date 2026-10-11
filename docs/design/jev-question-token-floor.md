# Jev question token floor: 2,000 to 500

## What and why

Every Jev question must carry a minimum amount of meaningful text across its rendered instructions, answer-side descriptions, and gap. The floor was 2,000 tokens. That floor suits done checks, whose briefs define long evidence vocabularies, but it is too high for the short, narrow sign questions planned for mid-run dynamic compute, where each question tests one observable sign and is asked many times per run. Padding those questions to 2,000 tokens adds cost and latency on every checkpoint without adding definitions, rules, or boundaries Jev can use.

The floor becomes 500 tokens. It stays a completeness check: every sentence must still define a term, state a rule, mark a boundary, give a recognition example, or make the gap readable on its own. Existing questions are unaffected; all of them are well above 500.

## Changes

- `skills/asking-jev-questions/SKILL.md`: the "Minimum content length" rule, its tokenizer margin, the checklist item, and the worked-example introduction say 500.
- `skills/jev-continuation/SKILL.md`: the done-question rule and the question-test checklist say 500, and name the renamed test.
- `vidbyte/lib/jev/done/README.md`: the question-format rule says 500.
- `tests/test_jev_done.py`: the four token-floor assertions use 500 and their tests are renamed `..._at_least_five_hundred_tokens`.

`tests/test_jev_done.py` also asserts that the can-simplify brief renders to more than 2,000 characters. That is a character-length check on one brief, not the token floor, and it is unchanged.

## Risks

A lower floor permits thinner questions. The house-style rules that decide question quality (definitions in dependency order, mirrored criteria, minimal pairs, the T14 guard) are unchanged, and reviewers still check them.

## Verification

`python scripts/run_ci.py --stage source` with the worktree on `PYTHONPATH`.
