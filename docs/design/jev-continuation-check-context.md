# Jev continuation check context

## What and why

When an enabled done check fails, `JevDoneContinuation` appends one message to the main agent's loop, built from `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md`. Today that message opens with two overlapping intro paragraphs (a merge leftover from the self-review and can-simplify PRs). It mixes check-specific rules (`FAITHFUL_SCOPE`, `SELF_REVIEW`, simplification, repair-and-revalidate) into an intro the agent reads on every continuation. And it lists failed Jev questions as terse bullets with no explanation of what the check looked for or what a "no" answer means.

The owner asked for the continuation to read as a real prompt:

- a general **Goal** and **Instructions** section that explains the original request, the run state, and the handoff;
- for each failed check, a 1–2 paragraph description (6–8 sentences) of what follows in the context window and what that check's failed Jev questions mean;
- that check's failed questions placed directly after its description.

## How it works

`continue_prompt.md` keeps its five headings (`# Original request`, `# Run state`, `# Handoff`, `# Failed checks`, `# Focus`), which existing tests and the field guide pin. It gains `# Goal` and `# Instructions` sections ahead of them. The two duplicated intro paragraphs become those sections, and the check-specific rules move out into their checks' descriptions. The Instructions section names `# Failed checks` and tells the agent that each check's description says what counts as fixed and takes priority over its general approach.

Each `JevDoneCheck` gets a description asset, `jev_continuation/<check>.md`, registered in `jev_continuation.json` with a `Prompt.JEV_CONTINUATION_<CHECK>` key. A constant `JEV_CONTINUATION_CHECK_PROMPTS: Mapping[JevDoneCheck, Prompt]` in `vidbyte/lib/constants/jev.py` maps each check to its key. Each description has 6–8 sentences across 1–2 paragraphs. It explains:

- what the run state recorded for this check before work began;
- what the handoff quoted from the run;
- what Jev was asked about each item;
- what a "no" answer means for this check;
- what counts as fixed;
- for checks that already have rules in today's intro, those same rules, moved here unchanged in meaning.

`JevDoneContinuation.message()` renders `{failed}` as one block per failed check:

```
## <check title>

<description asset>

<the existing _explain_<check>() failed text: gap line + per-item question lines>
```

The `_explain_*` helpers, `{focus}`, the runtime, and `should_continue()` are unchanged.

## Files

- `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md`: add Goal and Instructions sections and remove the duplicated intro.
- `vidbyte/prompts/prompts/jev_continuation/<check>.md` (24 new files) and `jev_continuation.json`.
- `vidbyte/lib/enums/prompts.py`: 24 `JEV_CONTINUATION_<CHECK>` keys.
- `vidbyte/lib/constants/jev.py`: the `JEV_CONTINUATION_CHECK_PROMPTS` mapping.
- `vidbyte/agents/jev/continuation/done.py`: `message()` renders per-check blocks; update the header.
- `tests/test_jev_done.py`:
  - every `JevDoneCheck` has a description;
  - each description has 6–8 sentences;
  - only failed checks' descriptions appear, each ahead of its own questions;
  - the repair/revalidate assertion moves to the `PROBLEMS_RESOLVED` description.
- `skills/jev-continuation/SKILL.md`: Step 13 and the file table say a new check also adds its description asset.

## Out of scope

- `JevFreshContinuation` and `fresh_prompt.md`. The fresh path still does not receive failed checks; that belongs in a separate PR.
- Changing what `_explain_*` produces, or the Focus section.

## Risks and open questions

- The message grows by about 150–250 tokens per failed check, and earlier continuation messages stay in history. This is bounded by `max_continuations`.
- PR #502 edits `done.py` and `continue_prompt.md` from an older base, so whichever PR lands second must rebase.

## Verification

- `PYTHONPATH=$(pwd) python -m pytest tests/test_jev_done.py tests/test_jev_fresh_continuation.py`.
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package`.
- `git add -A`, then semgrep per the field guide.
- Open a draft PR and wait for CI to pass.
