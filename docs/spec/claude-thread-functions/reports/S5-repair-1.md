# S5 repair, iteration 1: claude-thread-functions

Branch `feat/claude-host`. The code head is 821af103, which is pushed and green remotely. A docs commit with this report, `verify-log.md` and the `review.md` statuses follows it. PR https://github.com/cerredz/Vidbyte-SDK/pull/1044.

## Gate matrix (every gate run in this worktree, in this iteration, at 821af103)

| Gate | Result | Final lines |
|---|---|---|
| Claude pack, `pytest tests/features/harness_threads/ -k claude` | PASS | `200 passed, 437 deselected in 23.72s` |
| Source stage, `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `SDK-LINT: PASS` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `6445 passed, 16 skipped in 122.23s (0:02:02)` · `CI passed.` |
| Lint ratchets | PASS, baseline unchanged | Every zero-headroom rule is at its baseline: S008 19, A007 255, A006 34, S015 13, S017 79, S019 5, S051 259, C006 104, C008 45. S009 346/350 and A002 566/703 are IMPROVED by main's merged work; they were not lowered |
| I001 on the 19 touched `vidbyte/*.py` files | PASS | `All checks passed!` (tree-wide: 223, the same as main) |
| Package stage, PYTHONPATH unset | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| Semgrep 1.170.1 | PASS | `Ran 1 rule on 987 files: 0 findings.` |
| Test contract | PASS | `git log --no-merges --oneline 4806c697..HEAD --not origin/main -- tests` is empty; `git show --cc --format= be18994a -- tests` is empty |
| `lint/`, `contracts/`, `pyproject.toml` vs main | PASS | the diff is empty |
| Remote checks on 821af103 (runs 38991106870, 38991108133) | 4/4 green | Package, Static policy, Source / Python 3.11, Source / Python 3.12: all `completed success` |

No timing flake showed up in this run, so no test had to be rerun alone.

## Per finding

**Step 0, the merge (be18994a).** The single conflict was the header of `validation.py`. Of its lines, this PR had changed only `ROLE IN CODEBASE`. I resolved it by taking main's file and inserting `ClaudeWire` into main's reader list, so the diff against origin/main is exactly that one word. After the merge, the Claude pack gave the same 5 failures and no others.

**R-1, fixed in bb624cc9.** `vendor_text=outcome.stderr` is now on `OUTPUT_TOO_LARGE`. Evidence: `test_stdout_past_the_cap_carries_claudes_stderr_as_the_vendor_text` passes.

**R-3, fixed in b65590a4.** `read` now reads the answer before the bound checks, and both bound errors carry `thread_id=newest`. This matches the verifier's `wire_fixed.py` line for line. I checked it against INV-6 myself:
- A fork that printed nothing falls back to its source id through `NativeErrorFactory.failure` (`hostkit/errors.py:104`).
- Evidence: all three `test_answer_printed_before_the_timeout_gives_the_newest_thread_id` cases pass, and C901 stays at 8 (at max 7, ruff reports `8 > 7`).
- I updated the header items to match: the ARCHITECTURE NOTE says the answer is read first; WHAT NOT TO DO item 3 no longer says "never parsed"; and the edge-case sentences in `wire.py` and `threads.py` no longer say that a run which fails before exit carries no id.

**R-2, fixed in 9398d9ee.** `CLAUDE_PROMPT_PATTERN` now sits beside `NATIVE_PROMPT_PATTERN`. The prompt check picks it with a local conditional expression keyed on `NativeHarness.CLAUDE`, never on `NATIVE_STDIN_PROMPT_HARNESSES`. The headers of the constants module and the dataclass module each gained a sentence.
- Evidence: `test_invalid_prompt_is_refused[lone-surrogate]` passes.
- A probe of the record shows Claude refusing the prompt with `{'field': 'prompt'}`. opencode still accepts it (the EC-38 limitation), and emoji are accepted for every harness.

**R-4, fixed in 0fd70984.** I rewrote the one REPO_MAP line in plain words, keeping the merge-base sentences. None of the six forbidden tokens remain, and the only backticks are the ones the base held.
- Evidence: the AC-23 test passes, and the README still holds every token.

**R-8, fixed in 687141f7.** `_missing_member(answer, session)` lost its unused parameter, and a comment now says the None test exists for mypy narrowing. Spec §17 gained deviation item 5. That is the only spec edit.

**R-9, fixed in 5d449187.** The README bullet gained one sentence that names the spec behind each group of IDs, using slugs and no `docs/` paths. `folders.py` now cites "(spec INV-15)", as its siblings do, and names the claude-thread-functions spec for EC-31 and EC-21.

**R-15, fixed in 8d28e7f5**, and **the R-5 comment move, fixed in 821af103:** both are comment text only.

**R-7** is marked `fixed @cabf0f80 (spec r4)`.

## Process incident (no effect on the result)

One I001 command contained a stray `git checkout -q origin/main --`, which detached the worktree at origin/main while the first source-gate run was in the background. I stopped that run and confirmed that no gate processes were left. The branch ref was untouched, so I checked out `feat/claude-host` again and reran the gate from scratch. The rerun log records HEAD 821af103 at its start and at its end. No commit, push or file was affected: the tree was clean, and `git status` showed nothing to commit on both sides.

## Test changes proposed

None.

## Findings I believe are wrong

None.

## Still open

None of the confirmed findings. These follow-ups are left for the user as the briefing directs, with their status unchanged:
- R-5's `@intent` blocks;
- R-6, R-10, R-11, R-12 and R-13;
- R-14 `[scope-adding]`;
- opencode's lone-surrogate gap (EC-38).
