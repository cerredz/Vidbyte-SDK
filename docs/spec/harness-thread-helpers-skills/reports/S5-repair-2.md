# S5 repair, iteration 2 of 8: harness-thread-helpers-skills

Branch `feat/harness-thread-helpers-skills` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1147 · start HEAD `68c2cf49` · code SHA `ade57291` · records commit after it (docs only)

## Outcome

This was a one-defect iteration. The final conformance re-review (`reports/S5-rereview.md`) returned SOUND with two Minors:
- **R-C1 → R-24**, the source Minor. It is fixed in one docstring line in `vidbyte/harnesses/native/muse/commands.py` (`ade57291`).
- **R-C2 → R-25**, a spec-text Minor. The spec author had already fixed it at `3c114e7b`. I only recorded it in review.md.

Every gate is green locally and remotely on `ade57291`. No confirmed finding is open. The PR author can finalize #1147.

## Gate matrix (code SHA `ade57291`, run in this worktree in this iteration)

`PY` = `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python`. `DEEPSEEK_API_KEY` was set, as in the user's shell. Every exit code below is the gate's own, written as `cmd; echo exit=$?` and never read through `tail`.

| # | Gate | Command | Result | Final lines |
|---|---|---|---|---|
| 1 | lint | `$PY lint/run.py` | PASS, exit 0 | `S063 IMPROVED 4 -> 3. Lower it with: …` · `S064 RATCHETED: 4 known finding(s). …` · `SDK-LINT: PASS`. A001 642/642 (none in `muse/commands.py`), A002 605/703, S009 350/350, C002 9/9, S052 0, A009 0 |
| 2 | new tests | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads` | PASS, exit 0 | `1025 passed, 3 skipped in 90.58s (0:01:30)` |
| 2a | narrowest | `$PY -m pytest -p no:cacheprovider -q tests/features/harness_threads/test_harness_threads_muse_commands.py` | PASS, exit 0 | `32 passed in 6.33s` |
| 3 | full local gate | `$PY scripts/run_ci.py` | PASS, exit 0 | `6632 passed, 17 skipped in 138.65s (0:02:18)` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 4 | semgrep fixtures | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` (1.170.1) | PASS, exit 0 | `1/1: ✓ All tests passed` · `No tests for fixes found.` |
| 5 | semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS, exit 0 | `✅ Scan completed successfully.` · `Ran 1 rule on 975 files: 0 findings.` |
| 6 | remote CI | `gh workflow run ci.yml --ref feat/harness-thread-helpers-skills` → run 38942154825 | success | 3.12: `SDK-LINT: PASS` · `6580 passed, 69 skipped, 19 warnings in 146.09s` · `CI passed.` 3.11: `6580 passed, 69 skipped in 134.16s` · `CI passed.` Package: `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 7 | remote static policy | `gh workflow run static-policy.yml --ref …` → run 38942158122 | success | `1/1: ✓ All tests passed` · `Ran 1 rule on 975 files: 0 findings.` |
| — | check-runs | `gh api repos/cerredz/Vidbyte-SDK/commits/ade57291…/check-runs` | 4/4 green | `Package completed success ade57291` · `Static policy completed success ade57291` · `Source / Python 3.11 completed success ade57291` · `Source / Python 3.12 completed success ade57291` |

- The only annotation is a runner notice, not billing: "The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19, 2026."
- Remote runs skip 69 tests and local runs skip 17. As the briefing says, this is a platform difference.
- No failure needed a base-commit proof, because nothing failed.

Invariants:
- `git diff cd2b329b..HEAD -- tests/features/harness_threads | wc -l` → `0`.
- `git diff 239c408a HEAD -- lint/baseline.json` and `git diff origin/main HEAD -- lint/baseline.json` → empty.
- `git diff --name-only 68c2cf49..ade57291` → `vidbyte/harnesses/native/muse/commands.py` only (`1 insertion(+), 1 deletion(-)`).
- The comment-width loop over all 31 changed `vidbyte/*.py` files, HEAD against `origin/main`, gives `files=31 new_wide_comment_lines=0`.
- `origin/main` is still `f7f32b19` after a fetch. I did not merge and did not rebase.

## Per finding

### R-24 (S5-rereview R-C1), Minor, trivial: fixed @`ade57291`

- **Reproduced.** `grep -n 'transcript\|export' vidbyte/harnesses/native/muse/commands.py` hit `:4` (re-exported), `:5` ("no `muse export` runs for evidence (spec D-33)") and `:8` ("Do not give the evidence read or the export a key"). The header contradicted itself.
- **Root cause.** The r5 D-33 repair (`f8c00aa7`) deleted the export path. ROLE IN CODEBASE and ARCHITECTURE NOTE were updated, but WHAT NOT TO DO item 1 was missed.
- **Options weighed:**
  - (a) Delete item 1. This drops a true and still-needed warning: the evidence read must stay keyless (INV-23).
  - (b) Reword it to say that no export runs. This duplicates `:5`.
  - (c) The re-review's wording. I chose (c).
- **Change.** `1. Do not give the evidence read a key; only the exec child carries META_API_KEY.` I changed one docstring line and nothing else in the file. `RecordFieldValidator.require_text` at `:99` (the D-25 check) is untouched.
- **Proof the new text is true:**
  - `MuseCommandRun.execute` → `MuseHelperRun.tool_calls` (`muse/helpers.py:263`) → `_serve` → `MuseChildren.serve(..., removed=native_threads.NATIVE_HELPER_REMOVED_VARIABLES)` (`muse/helpers.py:297`). That tuple holds `META_API_KEY` (`lib/constants/native_threads.py:458-463`). The only keyed child is #1036's `muse exec` via `MuseThreadRun.execute`.
  - The other symbols the header names all exist: `MuseThreadHelpers`, `init_muse_workspace`, `tool_calls`, `MUSE_READ_SKILL_ID_MEMBER` (`:406`), both prompt templates (`:454-455`) and the `noneReason` field read (`muse/wire.py:314`).
- **Width.** The line is a module docstring line, not a `#` comment. Field guide `comment-format.md` and R-1 govern `#` comments only, and every sibling native header keeps one long line per key (for example `grok/commands.py`). So the shape stays as it was.
- **Re-checks:**
  - after the fix, the grep hits only `:4` and `:5`;
  - `lint/run.py --rule A001` → `A001 RATCHETED: 642 known finding(s).` · `SDK-LINT: PASS`, and `--all | grep -c muse/commands` → `0`;
  - Muse command tests: `32 passed`.

### R-25 (S5-rereview R-C2), spec text: fixed @`3c114e7b` by the spec author

I recorded it only, so review.md carries every finding. I did not edit spec.md.

### "Gets right" list

Nothing on it moved. The diff is one docstring line, and the full gate and the area suite match iteration 1's counts (`6632 passed, 17 skipped`; `1025 passed, 3 skipped`).

## Test changes proposed

None.

## Findings I believe are wrong

None.

## Still open

No confirmed finding and no gate. These follow-ups are unchanged by decision: R-8, R-9, R-12, R-13, R-14, R-18..R-20, R-22, and R-21's 44 markers.

## Next move this opens

The PR is ready for S6, the PR author. The PR body should:
- cite the 13 S5 fix commits (iteration 1's 12 plus `ade57291`);
- name the follow-ups listed above as deliberate scope, so a reviewer does not re-raise them;
- record that CI is dispatch-only, and quote the check-runs of the final head.
