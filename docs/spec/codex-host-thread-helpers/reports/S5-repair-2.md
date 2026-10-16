# S5 repair report, iteration 2 of 8

Stage: S5 repair · Branch `feat/codex-host` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1055 (draft) · Start HEAD `13a61e67` (origin at `03e1d7fd`) · Venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python`

## Outcome

The one finding handed to this iteration, R-16 (re-review R-C101), is fixed in one commit. Before the fix, the header named no `tests/features/codex_host` file (RED). After it, the header names two (GREEN). A mutation probe confirms that the two named files are exactly the ones that catch a change to this file's export list. The complete local gate set has the same results as iteration 1: the same counts, the same single inherited failure, and the same lint table. The branch was pushed fast-forward, `03e1d7fd..ddc432fe`, and both workflows were dispatched on it.

| Commit | Finding | Subject |
|---|---|---|
| `ddc432fe` | R-16 | `fix(codex): name the S2 test files in the enums package TESTS block [R-16]` |
| next | — | `docs(spec): verify-log iteration 2 for codex-host-thread-helpers` (the R-16 row in review.md, the verify-log entry, this report) |

## Gate matrix

The local gates ran at `ddc432fe`, from the worktree root, in CI order, on a clean tree. The pending review.md row was saved to scratch for the run and put back afterwards, and `git status --porcelain` was empty before and after. The final docs commit changes only `docs/spec/`.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (the R-16 pins and S2 r2) | gate 1 with `-rA` | PASS | `PASSED …::CodexHelperEnumTests::test_skill_scope_has_the_four_wire_values_and_is_exported` · `PASSED …::CodexHostExportTests::test_existing_export_lists_gain_only_the_new_names_in_place` · `PASSED …::test_a_failed_or_cancelled_goal_run_releases_its_slot` · `PASSED …::test_a_delete_in_flight_holds_the_thread_until_it_ends` · `PASSED …::test_a_failed_or_cancelled_delete_releases_the_thread` · `PASSED …::test_a_skill_recorded_under_another_name_stops_the_run_once` · `PASSED …::test_input_recorded_on_another_turn_does_not_confirm_the_run` |
| narrow | the two pinning files, `tests/test_jev_agent.py`, `tests/test_jev_run_brief.py` and `tests/features/jev_skills_preload/test_skill_sources_contract.py`; then `$VPY lint/run.py --rule A001` | PASS | `78 passed in 1.81s` · `A001 IMPROVED 642 -> 640. Lower it with: …` · `SDK-LINT: PASS` |
| 1 area tests | `PYTHONPATH=$(pwd) $VPY -m pytest -q tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py` | PASS (inherited only) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 678 passed, 2 skipped in 52.00s` (identical to iteration 1) |
| 2 lint | `$VPY lint/run.py` | PASS | 133 rule rows. The IMPROVED rows are the same eight as in iteration 1. `A007 255 255 RATCHETED` · `C008 45 45` · `S008 19 19` · `S024 25 25` · `S064 4 4` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| 3 public API | `PYTHONPATH=$(pwd) $VPY scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 998dc0da01d5f4519e76a3d92f08c4cd9d59d0df (vidbyte-sdk 0.3.0, 639 exports).` |
| 4 source stage | `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source` | PASS (inherited only) | `SDK-LINT: PASS` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `============ 1 failed, 5957 passed, 25 skipped in 96.80s (0:01:36) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| 5 package stage | `env -u PYTHONPATH $VPY scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` · `exit=0` |
| 6 static policy | `git add -A` (stages nothing); `pysemgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`; `pysemgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1, `codex-host-semgrep` venv, the CI pin) | PASS | `1/1: ✓ All tests passed` · `Scanning 1177 files tracked by git with 1 Code rule` · `Scan was limited to files tracked by git` · `Ran 1 rule on 980 files: 0 findings.` |
| inherited proof | the inherited test in a `git clone --shared` scratch copy at merge-base `72a4ade1`, with `refs/remotes/origin/main` pinned there | FAIL, as on main | `HEAD=72a4ade1 merge-base=72a4ade1` · `test_harness_threads_surface.py:193: AssertionError: assert 148 == 120` · `1 failed in 1.15s` |
| 7 remote checks | `gh workflow run ci.yml` and `static-policy.yml --ref feat/codex-host`; runs 38930980948 (CI) and 38930984111 (Static policy) on `ddc432fe` | PASS 4/4 | `gh api repos/cerredz/Vidbyte-SDK/commits/ddc432fe…/check-runs`: `Package completed success` · `Static policy completed success` · `Source / Python 3.12 completed success` · `Source / Python 3.11 completed success`. The docs commit after this one is dispatched again; its result is in the S5 STATUS block. |

The inherited failure is not this PR's. It fails in the same way at the branch's base commit (`git merge-base origin/main HEAD` = `72a4ade1`). Remote CI passes it because a shallow checkout has no `origin/main` (`test_harness_threads_surface.py:185-187`).

## Per finding

**R-16 (Minor, trivial, code; re-review R-C101).**
- *Reproduced.* `git diff c181be65...HEAD -- vidbyte/lib/enums/__init__.py` shows `+    CodexSkillScope,` and `+    "CodexSkillScope",`, so §12.3 row 3 modifies the file. `sed -n 1,36p … | grep -c tests/features/codex_host` gives `0`.
- *No byte pin.* `git grep -n "enums/__init__" -- tests` finds only the header text of `tests/features/jev_skills_preload/test_skill_sources_contract.py:4`. That test reads `enums.__all__`, not the file's bytes. So the fix needs no test change, and nothing is BLOCKED.
- *The file pair, verified independently.* `scratchpad/s5i2_enums_mutants.py` runs on a `git archive HEAD vidbyte tests pyproject.toml` copy, and each run prints `loaded_from=…\scratchpad\s5i2\mut\vidbyte\lib\enums\__init__.py`. The copy's baseline is `1 failed, 677 passed, 3 skipped`. That failure is `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores`, which fails only because the archive has no `REPO_MAP.md`.
  - Unexport (`"CodexSkillScope"` removed from `__all__`): `2 failed`, all in `test_codex_host_packaging.py`.
  - Reorder (moved to the end of `__all__`): `2 failed`, all in `test_codex_host_packaging.py`.
  - Drop (the import removed too): `3 failed`, in `test_codex_host_helper_surface.py` and `test_codex_host_packaging.py`.
  - So these two files catch every change to the export list, and no other file in the area suite does. "(the Codex* export order)" describes what the packaging file pins. The helper_surface file pins that the name is exported at all.
- *Fix.* Three lines appended to the indented TESTS block, after "Configuration and runtime tests cover the exported enum namespace.":
  ```
      tests/features/codex_host/test_codex_host_helper_surface.py and
      tests/features/codex_host/test_codex_host_packaging.py (the Codex*
      export order).
  ```
  - This is the re-reviewer's text, filled by `textwrap` at 72 columns (field guide comment-format.md) with the block's 4-space indent. The widths are 67, 70 and 18.
  - The block's existing lines are 60 and 70 wide, so 72 fits them too. The older lines elsewhere in the header go up to 96 and were left alone.
  - The phrasing "X and Y." matches the block's first line and R-7's `4fbc88b6` wording ("…helper_surface.py and …records.py.").
- *Line ending.* The index stores the file with LF; the working copy is CRLF (autocrlf). The edit script refuses mixed endings and writes CRLF. `crlf 320 lf 320 bare_lf 0`. `git diff` shows `3 insertions(+)` and no churn.
- *Verified.* GREEN check `2`. The narrow run gives `78 passed`, and A001 reads `642 -> 640`, the same as at `7e092c46`; A001 checks only that a field exists. The complete gate set is above.

## Test changes proposed
None. No file under `tests/` was changed.

## Findings I believe are wrong
None. The probe confirmed R-C101's file pair, so I applied its exact text.

## Checked and left alone
- The header's other lines wider than 72 (`:4`, `:8`, `:9`, `:13`, `:14`, `:21`, `:25`, `:28`; widths 73 to 96) predate this run, are docstring prose rather than `#` comments, and are outside the finding. Changing them is out of scope (briefing §6).
- The review.md verdict paragraph ("four Majors are open") is the historical S4 verdict and was left as it is. The status columns carry the current state.

## Still open
None. R-1 to R-9 and R-16 are fixed. R-10 to R-15 are follow-ups for the S6 PR body.

## If another iteration is needed
No gate is red. If a remote run on the final docs HEAD fails, first rerun it with `gh run rerun <id> --failed`, because of the known Python 3.11 MCP stdio flake (field guide `local-ci-verification.md`). Then reproduce with `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source`. The scratch tools are:
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s5i2_enums_mutants.py`, the probe;
- `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s5i2_apply_r16.py`, the edit.
