# Jev continuation check context

## What and why

When an enabled done check fails, `JevDoneContinuation` appends one message to the main agent's loop, built from `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md`. Today that message has three problems:

- It opens with two overlapping intro paragraphs, a merge leftover from the self-review and can-simplify PRs.
- It mixes check-specific rules (`FAITHFUL_SCOPE`, `SELF_REVIEW`, simplification, repair-and-revalidate) into an intro the agent reads on every continuation.
- It lists failed Jev questions as terse bullets, with no explanation of what the check looked for or what a "no" answer means.

The owner asked for the continuation to read as a real prompt:

- a general **Goal** and **Instructions** section that explains the original request, the run state, and the handoff;
- for each failed check, paragraphs that explain what follows in the context window and what that check's failed Jev questions mean;
- that check's failed questions placed directly after those paragraphs.

PR #506 (merged) added the same kind of per-check explanation for the fresh continuation. After the owner's review there, it is a `JevDoneGateDescription` per check in `JevDoneRegistry`, with three paragraphs of four to five sentences each: what the gate checks, how to use its failed questions, and its common failure modes. The owner chose one shared source for both continuations. This PR renders the same descriptions, so the two continuations never explain a gate differently.

## How it works

`continue_prompt.md` keeps its five headings (`# Original request`, `# Run state`, `# Handoff`, `# Failed checks`, `# Focus`), which existing tests and the field guide pin. It gains `# Goal` and `# Instructions` sections ahead of them:

- **Goal** (6–8 sentences): close only the gaps the checks found, then finish again.
- **Instructions** (two paragraphs) explain what the original request, the run state, and the handoff are, and what a failed Jev question means. They name the Failed checks section as the most important part.

The duplicated intro and the check-specific rules come out of the prompt. Each of those rules is now in its gate's shared description.

`JevDoneContinuation.message()` renders `{failed}` as one block per failed check:

```
## <Check Title>

<JevDoneRegistry.description(check): what it checks / how to use it / failure modes>

What the check found:
<the existing _explain_<check>() text: gap line + per-item failed Jev questions>
```

The `_explain_*` helpers, `{focus}`, the runtime, and `should_continue()` are unchanged.

## Files

- `vidbyte/prompts/prompts/jev_continuation/continue_prompt.md`: Goal and Instructions sections; the old intro is removed.
- `vidbyte/agents/jev/continuation/done.py`: `message()` renders per-check blocks through `_failed_check()`; header updated.
- `tests/test_jev_done.py`:
  - prompt section order and sentence counts;
  - no check names in the general prompt;
  - the repair/revalidate assertion moves to the `PROBLEMS_RESOLVED` description;
  - the end-to-end continuation test asserts that the description precedes its questions and that only failed checks' descriptions appear.
- `skills/jev-continuation/SKILL.md`: a new check writes its `JevDoneGateDescription`; the Step 13 message layout is updated.

## Out of scope

- Changing what `_explain_*` produces, or the Focus section.
- The fresh continuation's layout, which PR #506 owns.

## Risks

- Each failed check's block grows by 12–15 sentences, and earlier continuation messages stay in history. This is bounded by `max_continuations`.

## Verification

- `PYTHONPATH=$(pwd) python -m pytest tests/test_jev_done.py tests/test_jev_fresh_continuation.py`.
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package`.
- `git add -A`, then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`.
- GitHub Actions automatic triggers are currently disabled repo-wide, so the local gate is the CI of record.
