# Verification log: CodexHost thread helpers and built-in skill functions

Gate set (from context/code-map.md §1 and the S5 briefing), run from the worktree root in this order with `VPY=C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python`:

| # | Gate | Command | Where |
|---|---|---|---|
| 1 | area tests | `PYTHONPATH=$(pwd) $VPY -m pytest -q tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py` | local |
| 2 | lint | `$VPY lint/run.py` (final line `SDK-LINT: PASS`) | local; also inside gate 4 |
| 3 | public API contract | `PYTHONPATH=$(pwd) $VPY scripts/generate-sdk-public-api.py --check` | local |
| 4 | source stage | `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source` (bytecode check, lint, compileall, three scripts, full pytest) | local; remote `Source / Python 3.11`, `Source / Python 3.12` |
| 5 | package stage | `$VPY scripts/run_ci.py --stage package`, no `PYTHONPATH` (final line `CI passed.`) | local; remote `Package` |
| 6 | static policy | `git add -A`, then `pysemgrep --test` on the fixtures and `pysemgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` from the `codex-host-semgrep` venv | local; remote `Static policy` |
| 7 | remote checks | `gh workflow run ci.yml` and `static-policy.yml --ref feat/codex-host`, then the commit's check-runs | remote only (dispatch-only CI) |

Expected red: exactly one inherited test, `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 148 == 120` at `:193`). It fails on plain origin/main `72a4ade1`, so gate 1 and gate 4 exit 1 on it alone. Remote CI passes it because its shallow checkout has no `origin/main`: `optional_merge_base()` returns None, and the test returns before it compares against main (`test_harness_threads_surface.py:185-187`).

## Iteration 1 — 2026-10-16 15:30 UTC — agent report: reports/S5-repair-1.md
**Defects in:** R-2 and R-3 (Major, code); R-6, R-7 and R-9 (Minor, trivial, code); R-5 (Minor, spec wording). No gate was red at the start: at `7e092c46` the area suite gave `1 failed, 678 passed, 2 skipped`, the inherited test only. R-1, R-4 and R-8 were S2's (round 2) and only had to be shown passing.

**Hypotheses and attempts** (in order; failed or rejected ones included):
1. **Reproduce first.** A read-only probe (`scratchpad/s5_probe.py`, kept out of the repo) checks the fact each finding names: the constant and its `__all__` slot (R-2), the five schema bounds by value (R-3), the docstring against the 27 functions (R-6), the four TESTS lines (R-7), the host header, the `__init__` narration and the line count (R-9), and the INV-19 text (R-5). All six were RED at `7e092c46` and GREEN after their commits.
2. **R-2 as the review proposed** worked first time: the constant goes after `CODEX_COMPACTION_ITEM_TYPE` in the module and in `__all__`. Only `test_codex_host_helper_surface.py:288` pins the tail of `__all__`, and `test_codex_host_records.py:477` checks membership only, so a mid-list insert is safe and an end-append is not (verifier probe F02b). The commit also adds S3 deviation 8 to spec §17.
3. **R-3 as proposed.** The bounds mirror what the runtime already enforces: listing limit 1 to 1000 (`native/codex/thread_helpers.py:208`), turns limit at least 1 (`:140`), token budget at least 1 (`lib/dataclasses/codex_host.py:119`). `since` stays unbounded, as decided. `lint/run.py --rule A007` stays `RATCHETED: 255`.
4. **R-6 has a knock-on.** Spec §17 deviation 5 said the docstring was "unchanged", which R-6 makes false. That line was rewritten in the same commit. The pinned `toolsets/__init__.py:11` has an empty diff against `c181be65`.
5. **R-7, first try failed.** The edit script asserted LF endings and stopped on `vidbyte/lib/enums/codex.py`, which is CRLF in this working copy (autocrlf). Rerun keeping each file's own line ending: one line changed per file.
6. **R-7, the review's file list for `result.py` was not taken as given.** A mutation probe (`scratchpad/s5_items_mutant.py`) makes `CodexResultSerializer.items` raise in memory. It is killed by `test_codex_host_goal_skills.py` (10 failing), `test_codex_host_thread_helpers.py` (4) and `test_codex_host_helper_lifecycle.py` (3). It is killed by neither `test_codex_host_helper_surface.py` nor `test_codex_host_records.py`. So `result.py` names those three files, and the three lib files name helper_surface and records, which import them and assert their values.
7. **The A001 "IMPROVED 642 -> 640" line looked like an R-7 effect. It is not.** A001 checks only that a field exists and is not empty (`lint/rules/a001_agent_readable_file_headers.py:51-54`). A scratch clone at `7e092c46` shows the same `642 -> 640`. The whole lint table (133 rule rows) is identical at `7e092c46` and at `3d1ff4e2`.
8. **R-9 in place:** the header line stays one line, and the narration grows by one line. `host.py` goes from 891 to 892 lines. No added `#` line in `c181be65..HEAD` is wider than 72 columns.
9. **R-5:** AC-21 ("Exactly one `thread/delete`") was left as it is: it holds under its Given (idle thread, no overload), and a test pins it.
10. **Observed, not mine:** `test_codex_host_review_gaps.py::CodexHostInFlightStartTests::test_a_failed_in_flight_start_frees_its_thread_when_it_returns` passes but logs "Future exception was never retrieved" (`InternalRpcError -32603`). It logs the same at `7e092c46`.

**Changes:** `54f599de` [R-2] · `dd3fe2c2` [R-3] · `c3a3ef98` [R-6] · `4fbc88b6` [R-7] · `549c7475` [R-9] · `3d1ff4e2` [R-5] · then the docs commit `docs(spec): verify-log iteration 1 for codex-host-thread-helpers` (review.md statuses, this entry, the report).

**Gate matrix out** (local gates at `3d1ff4e2`; the docs commit after it changes only `docs/spec/`):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (S2 r2: R-1, R-4, R-8) | gate 1 with `-rA` | PASS (5/5) | `PASSED …::test_a_failed_or_cancelled_goal_run_releases_its_slot`; `PASSED …::test_a_delete_in_flight_holds_the_thread_until_it_ends`; `PASSED …::test_a_failed_or_cancelled_delete_releases_the_thread`; `PASSED …::test_a_skill_recorded_under_another_name_stops_the_run_once`; `PASSED …::test_input_recorded_on_another_turn_does_not_confirm_the_run` |
| 1 area tests | see header | PASS (inherited only) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 678 passed, 2 skipped in 51.62s` |
| 2 lint | `$VPY lint/run.py` | PASS | `A007 255/255, C008 45/45, S008 19/19, S024 25/25, S064 4/4 RATCHETED` · `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS` |
| 3 public API | `generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 998dc0da01d5f4519e76a3d92f08c4cd9d59d0df (vidbyte-sdk 0.3.0, 639 exports).` |
| 4 source stage | `run_ci.py --stage source` | PASS (inherited only) | `SDK-LINT: PASS` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 5957 passed, 25 skipped in 95.86s (0:01:35)` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| 5 package stage | `run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 6 static policy | `pysemgrep --test …` then `pysemgrep scan --error …` | PASS | `1/1: ✓ All tests passed` · `Scan was limited to files tracked by git` · `Ran 1 rule on 980 files: 0 findings.` |
| extra: mypy | `mypy --follow-imports=silent` on S3's four host modules (host, native skill_functions, thread_helpers, wire) plus the four other modules this iteration changed (tool thread_helpers and skill_functions, toolsets/codex, constants/codex) | PASS | `Success: no issues found in 8 source files` |
| inherited proof | that test at `72a4ade1` (scratch clone, `origin/main` pinned there) | FAIL, as on main | `E       AssertionError: assert 148 == 120` · `1 failed in 0.85s` |
| 7 remote checks | dispatched `ci.yml` 38924353312 and `static-policy.yml` 38924356214 on `3d1ff4e2` | PASS 4/4 | `gh api repos/cerredz/Vidbyte-SDK/commits/3d1ff4e2…/check-runs`: `Package completed success` · `Source / Python 3.12 completed success` · `Static policy completed success` · `Source / Python 3.11 completed success`. The docs commit after this one is dispatched again; its result is in the S5 STATUS block. |

**Still open:** none of R-1 to R-9. R-10 to R-15 are follow-ups for the PR body (not this stage's).

## Iteration 2 — 2026-10-16 16:19 UTC — agent report: reports/S5-repair-2.md
**Defects in:** R-16 (Minor, trivial, code), which the re-review raised as R-C101 (reports/S5-rereview-1.md). The TESTS block of `vidbyte/lib/enums/__init__.py:33-35` named no S2 test file, although §12.3 row 3 modifies the file to export `CodexSkillScope` (§12.5, NFR-8). No gate was red at the start: the orchestrator's re-run at `03e1d7fd` matched the iteration 1 matrix.

**Hypotheses and attempts** (in order):
1. **Reproduce first.** `git diff c181be65...HEAD -- vidbyte/lib/enums/__init__.py` shows that this run adds the two `CodexSkillScope` lines. The header's first 36 lines hold 0 mentions of `tests/features/codex_host` (RED). After the fix they hold 2 (GREEN).
2. **Check for a byte pin before editing.** `git grep -n "enums/__init__" -- tests` finds only the header text of `tests/features/jev_skills_preload/test_skill_sources_contract.py:4`. That file reads `enums.__all__` and no file bytes, and no test hashes the file. So the fix needs no test change.
3. **The re-reviewer's file pair was checked, not taken as given.** A mutation probe (`scratchpad/s5i2_enums_mutants.py`) runs on a `git archive HEAD` copy and confirms that it loaded from that copy. The copy's baseline has one failure of its own: the archive has no `REPO_MAP.md`, so `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores` fails. Each mutant's count includes that failure:
   - Remove `"CodexSkillScope"` from `__all__`: 2 failed, the packaging file only.
   - Move it to the end of `__all__`: 2 failed, the packaging file only.
   - Also remove its import: 3 failed, packaging plus `test_codex_host_helper_surface.py`.
   No other file in the area suite catches any of the three. So the TESTS block names exactly those two files.
4. **Line ending and width.** The index stores the file with LF, and the working copy has CRLF (autocrlf). The edit script refuses mixed line endings and keeps CRLF: 320 of 320 lines are CRLF. `git diff` shows 3 pure insertions. The new sentence is filled by `textwrap` at 72 columns, with the block's 4-space indent: line widths 67, 70 and 18. The older lines are wider (up to 96, wrapped at 79) and are outside the TESTS block, so they were left alone. The phrasing "X and Y." matches the block's first line and R-7's `4fbc88b6` wording.
5. **Gates on a clean tree.** The R-16 review.md row was written before the fix and saved to scratch during the gate run, so gates 1 to 6 ran on a tree exactly at `ddc432fe` (`git status --porcelain` was empty). The row was put back afterwards.

**Changes:** `ddc432fe` [R-16] · then the docs commit `docs(spec): verify-log iteration 2 for codex-host-thread-helpers` (the R-16 row in review.md, this entry, the report).

**Gate matrix out** (local gates at `ddc432fe`; the docs commit after it changes only `docs/spec/`):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (the R-16 pins and S2 r2) | gate 1 with `-rA` | PASS | `PASSED …test_codex_host_helper_surface.py::CodexHelperEnumTests::test_skill_scope_has_the_four_wire_values_and_is_exported` · `PASSED …test_codex_host_packaging.py::CodexHostExportTests::test_existing_export_lists_gain_only_the_new_names_in_place` · the five S2 round-2 tests `PASSED` |
| narrow | the two pinning files plus `tests/test_jev_agent.py`, `tests/test_jev_run_brief.py`, `test_skill_sources_contract.py`; `lint/run.py --rule A001` | PASS | `78 passed in 1.81s` · `A001 IMPROVED 642 -> 640` (as at `7e092c46`) · `SDK-LINT: PASS` |
| 1 area tests | see header | PASS (inherited only) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 678 passed, 2 skipped in 52.00s` |
| 2 lint | `$VPY lint/run.py` | PASS | 133 rule rows. The IMPROVED rows are the same eight as in iteration 1 (A001, A002, C012, S001, S010, S025, S061, S063). `A007 255/255, C008 45/45, S008 19/19, S024 25/25, S064 4/4 RATCHETED` · `S064 RATCHETED: 4 known finding(s).` · `SDK-LINT: PASS` |
| 3 public API | `PYTHONPATH=$(pwd) $VPY scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 998dc0da01d5f4519e76a3d92f08c4cd9d59d0df (vidbyte-sdk 0.3.0, 639 exports).` |
| 4 source stage | `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source` | PASS (inherited only) | `SDK-LINT: PASS` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 5957 passed, 25 skipped in 96.80s (0:01:36)` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| 5 package stage | `env -u PYTHONPATH $VPY scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 6 static policy | `git add -A` (nothing to stage); `pysemgrep --test …`; `pysemgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1) | PASS | `1/1: ✓ All tests passed` · `Scan was limited to files tracked by git` · `Ran 1 rule on 980 files: 0 findings.` |
| inherited proof | that test in a `--shared` scratch clone at merge-base `72a4ade1`, with `origin/main` pinned there (origin/main itself has moved on to `cb554ed3`) | FAIL, as on main | `test_harness_threads_surface.py:193: AssertionError: assert 148 == 120` · `1 failed in 1.15s` |
| 7 remote checks | `gh workflow run ci.yml` and `static-policy.yml --ref feat/codex-host`; runs 38930980948 (CI) and 38930984111 (Static policy) on `ddc432fe` | PASS 4/4 | `gh api repos/cerredz/Vidbyte-SDK/commits/ddc432fe…/check-runs`: `Package completed success` · `Static policy completed success` · `Source / Python 3.12 completed success` · `Source / Python 3.11 completed success`. The docs commit after this one is dispatched again; its result is in the S5 STATUS block. |

**Still open:** none. R-1 to R-9 and R-16 are fixed. R-10 to R-15 are follow-ups for the PR body.
