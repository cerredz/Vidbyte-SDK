# S5 repair, iteration 1 of 8: codex-host-hardening

- **Result:** DONE. Every confirmed finding is fixed. Every gate is green except one inherited test failure, which this branch cannot change; see "Inherited failure" below.
- **Start → end:** `436b07c3` → `31622c00` for the fixes, then one docs commit for this report, verify-log.md and the review.md status cells.
- **PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1181. The diff base is `origin/ai/resolve-pr-1055-comments`.
- **Test contract:** `git diff 6b59d390..HEAD -- tests` is empty. No test was edited, and no test change is proposed.

## Gate matrix

All gates ran in this worktree in this iteration. `V` is `scratchpad/venv-codex163/Scripts/python.exe` (openai-codex 0.163.0, Python 3.11.0).

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (area) | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS; the 1 failure is inherited | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 1046 passed, 3 skipped in 66.20s (0:01:06)` |
| lint | `"$V" lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` |
| ruff (repo config) | `"$V" -m ruff check <23 changed .py> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache` | PASS | `All checks passed!` |
| semgrep | the bundled `semgrep-core.exe` with `.semgrep/typed-mapping-boundary-policy.yml`, once per changed file | PASS | `runs=23 results=0 errors=0`; the positive control gives `results=2` |
| test contract | `git diff 6b59d390..HEAD -- tests` | PASS | 0 lines |
| full local gate, source stage | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` | FAIL: 1, inherited | `SDK-LINT: PASS` · `context write-path integrity: ok` · `context primitive introductions: ok` · `reasoning trace contracts: ok (182 tools, 55 shapes)` · `=========== 1 failed, 6577 passed, 27 skipped in 116.36s (0:01:56) ============` |
| full local gate, package stage | `"$V" scripts/run_ci.py --stage package`, with no PYTHONPATH | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| remote checks | `gh pr checks 1181` | none configured | `no checks reported on the 'feat/codex-host-first-class' branch` |

**Inherited failure.** The test `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` parses `vidbyte/lib/enums/failure.py` at the merge base with `origin/main` and expects 120 members. Main's file has since grown to 167. This command prints nothing:

```
git diff origin/ai/resolve-pr-1055-comments...HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads/
```

So the result does not depend on this branch. S0 recorded the same failure at the base.

## Findings, with evidence

| ID | Commit | What changed | Evidence |
|---|---|---|---|
| R-1 | `df460ec7` | Re-filled the six 73-column comment lines at 72 columns. Each block keeps its words and its `@intent` line. | The PR-added comment scan (`scratchpad/s5r1_wide_comments.py origin/ai/resolve-pr-1055-comments`) finds 0 lines in `vidbyte/`. |
| R-2 | `a54163dc` | Added `CODEX_HOST_ANY_MODEL_TEXT` and `CODEX_HOST_FORK_EXPERIMENTAL_FIELDS` to lib constants. `preflight.py` uses the text. `_reject_experimental_fork_fields` walks the tuple with `getattr`. | The fork-refusal tests in the area run pass, and so do lint rules C021 and A002. |
| R-3 | `4a3dd334` | When a review was read back as ended, `_accept` finishes it inside `try`/`except Exception`, and a failure goes to `events.fail(turn, exc)`, which ends the review FAILED. `_fail` is now the public `fail`. | `CodexReviewCompletionFailureTests` passed 8 runs out of 8. Probe RC1 prints the first review returned, `RUNNING: []`, and the second review accepted. |
| R-7 | `7a7dbd69` | `CODEX_HOST_GOAL_FIELD_MESSAGE` takes `{owner}`. `_reject_goal_fields(owner, request)` passes it through. `CodexGoalRunRequest` names `run_codex_goal request`. | The R-7 rows in the area run pass. |
| R-9 | `e4d21a7f`, `4de7eb60` | Added `LogToken.of(value, limit)` to `vidbyte/lib/util/text.py` (spec row 25). Every id or method that Codex or the caller chose is logged through it, with `CODEX_HOST_LOG_TOKEN_MAX_CHARS = 128`, in five places: `connection.py` (router, `_log_call`), `turns.py` (`observe`, `finish`) and `turn_events.py` (both warnings). Routing still uses the raw values. | The R-9 rows pass. Probe RE1 prints 1 line, a forged `itemId` logs as one token, and a 100,000-character id gives a 268-character record (it was 100,137). |
| R-10 | `4882cb66` | `call` keeps its future. On a cancellation, a future that was still queued is withdrawn and writes nothing (EC-57). A future already running gets `_log_late` as a done-callback. `start`'s cancel hand-over registers the same record callback ahead of `_post_late`, and the timeout hand-over passes `None`, because it already logged. | `CodexCallRecordTests` passed 8 runs out of 8. Probe RC2 prints one record each for `thread/read` and `turn/start`, and the turn is adopted. |
| R-4, R-5, R-6, R-8 | `75bfae7d` (S2) | These were test-only. | Their rows pass in this iteration's area run. |
| m-1 | `8bf92f33` | Gave `run_codex_skill` and `run_codex_openai_docs` docstrings that name NG-13's limits. | The area run passes. |
| m-2 | `31622c00` | The routed default answers now use `CodexApprovalDecision.DECLINE.value`. | The AC-40 dict comparison passes. |

**Budget.** This iteration stays inside §8.4 (r5).
- No new files.
- `LogToken` is the 14th class.
- The 2 new config keys bring the total to 11.
- `CODEX_HOST_ANY_MODEL_TEXT` is the 13th message.
- No dependencies were added.
- 25 non-test, non-docs files are changed: the 24 planned rows, plus `text.py`, which is row 25.

`host.py` is at 927 lines, under the 940 at which I would have asked first. `connection.py` is at 600 lines.

**Disputed findings:** none.

## Open items (none blocks)

- **m-2, second half.** The four fixed-method keys need config keys beyond §8.4.
- **m-3: kept as a follow-up, against the review's "trivial" label.**
  - §9.1 and AC-41 ask for `details["field"]` from the input records in `codex_host_inputs.py` and from two named rows. `CodexServerAnswer` is neither.
  - Its other two raises, through the shared `_reject_wrong_type` and `_reject_bad_tuple` helpers, set no details either, like every other record in `codex_host.py`. Adding details to just two raises would make the record inconsistent with itself.
  - Moving the texts into lib needs S1 to decide whether INV-47 covers lib records.
- **m-4 to m-7.** These stay as routed: m-4 needs a spec change, m-5 needs a refactor that keeps S008/S024 at baseline (`handle` is still 63 lines), and m-6 and m-7 are follow-ups.
- **Wide comments in `tests/`.** 178 comment lines that the PR added under `tests/` are wider than 72 columns. They are S2's files, and the briefing forbids editing tests.
- **Ruff with its own defaults.** This is not a gate, and the repo's ruff config passes. Ruff's own defaults find 15 issues on the changed files before this iteration and 16 after. The new one is BLE001 at `reviews.py:146`: R-3's `except Exception`, which the spec prescribes, the same as its two flagged siblings in `turn_events.py`.
- **Not run: the S4 engineering mutation plugin.** This iteration edited `_end_lost_turn` and `handle`, so the plugin's mutant strings may no longer match.

## Hypotheses for the next agent

- Any later comment edit needs the scan again: `"$V" -I scratchpad/s5r1_wide_comments.py origin/ai/resolve-pr-1055-comments`. The field guide counts the indent in the 72 columns.
- **The R-10 ordering rule.** `concurrent.futures` runs done-callbacks in the order they were registered, and at once in the caller when the future is already done. The record callback must stay ahead of `_post_late`. Moving it inside `_post_late` makes a three-deep chain (AGENTS.md §1).
- **Line endings.** Several working files are CRLF on disk (`core.autocrlf=true`), so a Python search-and-replace on `"\n"` misses. Use the Edit tool.
- **The package stage installs into its own temporary venv.** It must run without PYTHONPATH and after the source stage, not alongside it.
