# S5 repair report, iteration 1 of 8

Stage: S5 repair · Branch `feat/codex-host` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1055 (draft) · Start HEAD `7e092c46` (the briefing named `ecba0d48`; before the resume, the orchestrator added one commit that touches only `pipeline.md`) · Venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python`

## Outcome

All six findings handed to this iteration are fixed, one commit each. A probe showed each one RED before its fix and GREEN after it. The complete local gate set is green, apart from the one named inherited test. The lint rule table is identical to the starting HEAD in all 133 rows, and every no-slack ratchet is still at its baseline. The five S2 round-2 tests for R-1, R-4 and R-8 pass. The branch was pushed fast-forward, `c81ba632..3d1ff4e2`, and both workflows were dispatched on it.

| Commit | Finding | Subject |
|---|---|---|
| `54f599de` | R-2 | `fix(codex): move the userMessage item type into the lib constants [R-2]` |
| `dd3fe2c2` | R-3 | `fix(codex): bound the numeric schemas of the new Codex tools [R-3]` |
| `c3a3ef98` | R-6 | `fix(codex): say CodexHostTools has no tool for delete_codex_thread [R-6]` |
| `4fbc88b6` | R-7 | `fix(codex): name the S2 test files in four TESTS header lines [R-7]` |
| `549c7475` | R-9 | `fix(codex): give the CodexHost header and __init__ the two collaborators [R-9]` |
| `3d1ff4e2` | R-5 | `docs(spec): reword INV-19 for overload resends [R-5]` |
| next | — | `docs(spec): verify-log iteration 1 for codex-host-thread-helpers` (review.md statuses, verify-log, this report) |

## Gate matrix

The local gates ran at `3d1ff4e2`, from the worktree root, in CI order. The final docs commit changes only `docs/spec/`.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (S2 r2) | gate 1 with `-rA` | PASS 5/5 | `PASSED tests/features/codex_host/test_codex_host_helper_tools.py::CodexHelperToolScopeTests::test_a_failed_or_cancelled_goal_run_releases_its_slot` · `PASSED …test_codex_host_thread_helpers.py::CodexThreadReservationTests::test_a_delete_in_flight_holds_the_thread_until_it_ends` · `PASSED …::test_a_failed_or_cancelled_delete_releases_the_thread` · `PASSED …test_codex_host_goal_skills.py::CodexSkillReadBackTests::test_a_skill_recorded_under_another_name_stops_the_run_once` · `PASSED …::test_input_recorded_on_another_turn_does_not_confirm_the_run` |
| 1 area tests | `PYTHONPATH=$(pwd) $VPY -m pytest -q tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py` | PASS (inherited only) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 678 passed, 2 skipped in 51.62s` (identical to `7e092c46`) |
| 2 lint | `$VPY lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| 3 public API | `PYTHONPATH=$(pwd) $VPY scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 998dc0da01d5f4519e76a3d92f08c4cd9d59d0df (vidbyte-sdk 0.3.0, 639 exports).` |
| 4 source stage | `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source` | PASS (inherited only) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `============ 1 failed, 5957 passed, 25 skipped in 95.86s (0:01:35) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| 5 package stage | `env -u PYTHONPATH $VPY scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 6 static policy | `git add -A`; `pysemgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`; `pysemgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1, `codex-host-semgrep` venv) | PASS | `1/1: ✓ All tests passed` · `Scanning 1177 files tracked by git with 1 Code rule` · `Ran 1 rule on 980 files: 0 findings.` |
| extra: mypy | `$VPY -m mypy --follow-imports=silent` on host.py, native skill_functions.py, thread_helpers.py and wire.py, tool thread_helpers.py and skill_functions.py, toolsets/codex.py and constants/codex.py | PASS | `Success: no issues found in 8 source files` |
| inherited proof | the inherited test in a scratch clone at merge-base `72a4ade1`, with `origin/main` pinned there | FAIL, as on main | `E       AssertionError: assert 148 == 120` · `1 failed in 0.85s` |
| 7 remote checks | `gh workflow run ci.yml` and `static-policy.yml --ref feat/codex-host`; runs 38924353312 and 38924356214 on `3d1ff4e2` | PASS 4/4 | `gh api repos/cerredz/Vidbyte-SDK/commits/3d1ff4e2…/check-runs`: `Package completed success` · `Source / Python 3.12 completed success` · `Static policy completed success` · `Source / Python 3.11 completed success`. The docs commit after this one is dispatched again; its result is in the S5 STATUS block. |

Source-stage count: S3 measured 5952 passed. The 5 extra here are S2's round-2 tests.

## Per finding

**R-2 (Major).** Reproduced: `git grep -n '"userMessage"' -- vidbyte` gave `vidbyte/harnesses/native/codex/skill_functions.py:66:USER_MESSAGE_ITEM_TYPE = "userMessage"`. The probe read `const=False placed_after_compaction=False feature_literal_gone=False`.
- Fix: add `CODEX_USER_MESSAGE_ITEM_TYPE = "userMessage"`, with a one-line comment, right after `CODEX_COMPACTION_ITEM_TYPE` in `vidbyte/lib/constants/codex.py`. Its `__all__` entry goes right after `"CODEX_COMPACTION_ITEM_TYPE"`. Import it by name in the native `skill_functions.py`, delete the two local lines, and use it at the read-back.
- Spec §17 gains deviation 8. It says why the constant is not at the end of `__all__`: `test_codex_host_helper_surface.py:288` pins the tail to exactly the §9.3 names, and `test_codex_host_records.py:477` checks only membership.
- Verified: probe GREEN; 96 passed over helper_surface, goal_skills, helper_lifecycle, records and output_contracts; no ruff `I001,F401,F821` finding on either path. The `CODEX_HOST_INPUT_CHECK_*` names are still imported by name, so the tests' patches still apply.

**R-3 (Major).** Reproduced: the probe read `{}` for all five properties.
- Fix: the three listing `limit`s get `"minimum": CODEX_HOST_MIN_LIST_LIMIT, "maximum": CODEX_HOST_THREAD_LIST_MAX_LIMIT`. The turns `limit` gets `"minimum": CODEX_HOST_MIN_LIST_LIMIT`. `run_codex_goal.token_budget` gets `"minimum": CODEX_HOST_MIN_TOKEN_LIMIT`. Every bound is a constant, written in the key order of `threads.py:92`.
- These are exactly the bounds the runtime already enforces: `native/codex/thread_helpers.py:208` (1 to 1000), `:140` (at least 1) and `lib/dataclasses/codex_host.py:119` (at least 1). The descriptions already say "at least one" and "Very large values are refused".
- `since` stays unbounded.
- Verified: probe GREEN; `A007 RATCHETED: 255`; 35 of 35 collected tests passed over helper_tools, tools and packaging; ruff clean on both paths.

**R-6 (Minor).** Reproduced: the probe found 27 functions and the docstring "Catalog of one agent tool per CodexHost function over one host."
- Fix: "…per CodexHost function except delete_codex_thread, over one host."
- Knock-on: spec §17 deviation 5 said this docstring was "unchanged", which would now be false. It was rewritten in the same commit.
- Verified: `git diff c181be65 -- vidbyte/tools/toolsets/__init__.py` is empty (0 lines), so the pinned bullet is untouched; 35 passed.

**R-7 (Minor).** Reproduced: the probe listed the missing names for all four files.
- The three lib files name `test_codex_host_helper_surface.py` and `test_codex_host_records.py`, which import them and assert their new values. S2 modified records in `aeeee55b`.
- **Refinement, with evidence:** `result.py` does not name helper_surface or records. A mutation probe made `CodexResultSerializer.items` raise. It was killed by goal_skills (10), thread_helpers (4) and helper_lifecycle (3), and by neither of the other two files. So `result.py` names the three files that reach it. The review's wording could be read as adding helper_surface and records there too. That would have been a false TESTS line.
- Format: the files are appended after `; `, the separator these headers already use on their RELATED DOCS lines.
- Verified: probe GREEN; `SDK-LINT: PASS` for A001; `45/45 tests passed` for `scripts/test-session-failure-vocabulary.py`; 21 passed over helper_surface and records.

**R-9 (Minor).** Reproduced: the probe read `pattern_names_collaborators=False`, and the narration left out `_threads` and `_skills`.
- Fix, in place: the COMMON MODIFICATION PATTERNS line gains "A new thread helper goes in CodexThreadHelpers and a new run wrapper in CodexSkillFunctions; its host method is the guard, then one delegation." It stays one line. The `__init__` narration now lists "_threads (thread helpers) and _skills (goal and skill runs)".
- `host.py` goes from 891 to 892 lines (cap +3).
- Verified: probe GREEN. No `#` line added in `c181be65..HEAD` is over 72 columns; I scanned the added diff lines, not whole files. 30 passed over lifecycle, helper_surface and packaging.

**R-5 (Minor, spec).** Reproduced: INV-19 read "`thread/delete` is sent exactly once per call, through the raw path."
- Now: "One `thread/delete` is sent per call, through the raw path, which the SDK may resend after an overload refusal (EC-24, A-14)."
- Checked against the code: `native/codex/thread_helpers.py:185-190` sends one raw delete. `connection.py:209-210` keeps `request_with_retry_on_overload` for every method outside `SPENDING_RAW_METHODS`.
- AC-21 ("Exactly one `thread/delete`") is unchanged: it holds under its Given, and a test pins it.

**R-1, R-4 and R-8** were S2's work, and all five of their tests pass (gate matrix, row 1). review.md records them as `fixed @<S2 sha> (S2 r2; passes in S5 iteration 1)`, so the ledger does not show them as open. R-10 to R-15 stay `open`: they are follow-ups for the PR body.

## Test changes proposed
None. No file under `tests/` was changed.

## Findings I believe are wrong
None. The one refinement, R-7's file list for `result.py`, is explained above with the mutation evidence.

## Checked and left alone (so the re-review need not re-derive them)
- **A001 `IMPROVED 642 -> 640`, and seven other IMPROVED rows** (A002, C012, S001, S010, S025, S061, S063): all are already present at `7e092c46`, measured in a scratch clone with the same 133-row table. A001 checks only that a field exists, so R-7 cannot move it. The baseline was not touched (briefing §6). The owner may lower these with `--update-baseline`.
- **`ONE_TURN = 1`** in `tools/builtins/codex/skill_functions.py:38` copies the existing `threads.py:68` and `delegation.py:38`, and spec §12.3 row 15 names it. It follows the repo's grain, so it is not an R-2-class defect.
- **"Future exception was never retrieved"** is logged by the passing `test_codex_host_review_gaps.py::CodexHostInFlightStartTests::test_a_failed_in_flight_start_frees_its_thread_when_it_returns`. The same log appears at `7e092c46`, and the test predates this PR's helpers. It is a candidate follow-up for the codex-host turn-start path, not a gate.

## Still open
None of R-1 to R-9. The follow-ups R-10 to R-15 belong to the S6 PR body.

## If another iteration is needed
No gate is red, so there is nothing to retry. If the remote run on the final docs HEAD fails, rerun first: `gh run rerun <id> --failed`, for the known Python 3.11 MCP stdio flake (field guide `local-ci-verification.md`). Otherwise reproduce with `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source`. The scratch tools are `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s5_probe.py` (all six facts) and `…/scratchpad/s5_items_mutant.py`.
