# JEV continuation skill

## What and why

PR #471 finished the first JevAgent continuation feature: the multi-part done check. A user enables it with `JevRuntimeSettings(continual=JevContinualSettings(checks=(JevDoneCheck.MULTI_PART,)))`. At every finish attempt, `JevDoneContinuation` has `JevRunState` run the check. The check uses the run state, the `JevHandoff` evidence, and one batched Jev request. When the check fails, the continuation sends the main agent back to work in the same loop.

The next done checks will reuse the same seams. The only guide to adding one is five lines in `skills/jev-agent/SKILL.md` ("Adding a done check"). That section names the edits but not the reasons behind them or the invariants the tests and reviews enforce. Examples of those invariants: questions go out in one batch per finish attempt, generative agents write and Jev only recognizes, `missing` text never goes to Jev, everything fails open, and the system prompts stay general.

This change adds a dedicated skill that walks an agent through adding a continuation done check end to end, as a detailed checklist. It also adds pointer comments in the code where that work starts, so an agent editing those spots loads the skill first.

## How it works

- New skill `skills/jev-continuation/SKILL.md` (frontmatter `name: jev-continuation`), a contributor-facing skill in the repository-level `skills/` folder. Its contents:
  - the overall flow of the feature, from settings to continuation message;
  - the important files, and when to create a new file versus extend an existing one;
  - a numbered checklist, each step explained in detail:
    - the enum and question key;
    - the run-state and handoff section payload subclasses, and what logic belongs where;
    - the records and constants;
    - writing the Jev question, and its structure;
    - registry and threshold;
    - the `_SECTIONS`, `_record`, `_section` (the batched state and questions), and `_judge` entries;
    - the `_explain` case;
    - what the main agent receives after `should_continue` returns True;
    - exports, tests, and verification;
  - "important things to remember", and when a new `JevContinuation` subclass is warranted instead.
- Pointer comments in the code that tell an agent to load the skill before extending the feature:
  - above `JevDoneCheck` in `vidbyte/lib/enums/jev.py`, the first edit of every new check;
  - above `JevContinuation` in `vidbyte/agents/jev/continuation/base.py`, the seam for any new continuation.
- One line in `skills/jev-agent/SKILL.md` "Adding a done check" and one row in the AGENTS.md "JEV File Locations" table, both pointing to the new skill.

## Files

- `skills/jev-continuation/SKILL.md` (new)
- `vidbyte/lib/enums/jev.py` (comment only)
- `vidbyte/agents/jev/continuation/base.py` (comment only)
- `skills/jev-agent/SKILL.md` (one pointer line)
- `AGENTS.md` (one table row)
- `docs/design/jev-continuation-skill.md` (this document)

## Risks and open questions

- The skill describes code as of `280a9121`. When the done-check seams change, update the skill in the same PR, as `skills/jev-agent/SKILL.md` already asks for itself.
- The skill states one rule that is not yet exercised. `DONE_STATE`, the shared description of the batched state, must stay true for every combination of enabled checks, so a second check that adds a state field must update it. This is guidance for the next check, not a code change here.
- No behavior changes. Comments are the only code edits.

## Verification

- `python lint/run.py` and `python scripts/run_ci.py --stage source` pass: the comment edits change no rule counts, and the skill is not packaged.
- `python scripts/run_ci.py --stage package` passes.
- Every file path, class, method, constant, and test named in the skill exists on the branch. A script greps each one.
