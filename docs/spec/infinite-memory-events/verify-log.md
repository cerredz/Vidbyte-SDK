# Verification log: InfiniteMemoryAgent native run events and handoff

Gate set (from context/code-map.md §1; run from the worktree root):

| Gate | Command | Where |
|---|---|---|
| focused tests | `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider` | local |
| lint (SDK-LINT) | `PYTHONPATH=$(pwd) python lint/run.py` (new files `git add`ed first) | local; also inside the source stage |
| full gate, source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` (lint, compileall, three check scripts, pytest) | local; remote `CI` Source / Python 3.11 and 3.12 |
| full gate, package stage | `python scripts/run_ci.py --stage package` with no PYTHONPATH | local; remote `CI` package job |
| semgrep static policy | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1, needs `mcp<2`) | local from a scratch venv with its `Scripts` first on PATH; remote `Static policy` |
| public-API contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | local; also lint C016 |
| remote checks | `gh workflow run CI` and `gh workflow run "Static policy"` on the branch, then `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs` | remote only (no checks run on PRs automatically) |

Known inherited failures (base `7efceb55`, PR #1084): 3 `tests/features/harness_threads/test_harness_threads_surface.py` tests that diff `merge-base origin/main HEAD` and fail on any branch touching `vidbyte/tools`, `vidbyte/lib/configs`, or root exports (field guide `local-ci-verification.md`); `test_mcp_stdio_transport` flakes under full-suite load.

## Iteration 1 — 2026-10-16 17:25 — agent report: reports/S5-repair-1.md
**Defects in:** Majors R-1..R-7 (R-7 ruled option A by the orchestrator, 2026-10-16 15:50); Minors tagged trivial m-5, m-6, m-7, m-8; m-10 to mark `wontfix (history)`. No gate was red at the start (`0139fcce`): focused tests 186 passed, lint PASS, source stage with only the 3 inherited `harness_threads` failures. Remote checks had never been dispatched on the branch.

**Hypotheses and attempts:**
- R-2: the root cause is Python 3.11 `Path.resolve` raising `RuntimeError("Symlink loop …")`, which `relative`'s except tuple missed. Adding `RuntimeError` fixed it. Also covered: `expanduser` raises `RuntimeError` for an unknown `~user`. The first test asserted the exact path, but a stdlib probe showed that 3.13's `resolve` no longer raises and returns the loop's other link. The test now asserts one consistent workspace-relative name, exact on 3.11 and 3.12 (the CI matrix). It still fails on code without the fix.
- R-3 to R-6: test-only. Each mutant was first shown SURVIVED with `SCRATCH/v_mut.py`, then shown KILLED by the new test copied into `SCRATCH/mut` with `SCRATCH/s5_kill.py`. The copy-in is removed afterwards. That script runs the node at baseline and under the mutant, then the whole pack under the mutant, and restores the files.
- R-4: the review's fix (deleting the `_deliver` guard) stays refuted (mypy S009). A log-only assertion would miss `run_stopped`: with placeholder arguments it builds a whole event without raising. A spy on `InfiniteEvent.__post_init__` covers it (extra mutant `no_sink_run_stopped` KILLED). `events.py` is unchanged at 400/400.
- R-7: three homes were considered for the helper. A new `TextCut` class goes beyond §8.4's class count. `SubstringCounter` is the wrong concern. The existing `TokenEstimate`, which already has `cut` and `cap`, was chosen, as `truncate_chars`. A 1,404-case differential against both old cuts found 0 mismatches. Fresh imports of every entry module in each order succeed, so there is no cycle. A seeded off-by-one fails 25 tests, so the helper is covered. The surrogate scrub was not consolidated (optional, needs a second helper).
- Tooling traps:
  - Git Bash quoted heredocs collapse `\\` to `\`. One Python edit script therefore wrote a real lone surrogate and left a test file at 0 bytes, which was restored with `git checkout --`. Use the Edit tool for any text with backslashes.
  - The scratch venv's `semgrep.exe` runs the global `pysemgrep` (mcp 2.x crash) unless `/c/…/semgrep-venv/Scripts` is first on `PATH`. A `C:` path breaks bash `PATH`.

**Changes:**
- `ca5157a4` R-2 fix and test; `99c5908d` R-3 test; `d8186147` R-4 test; `755e55cd` R-5 test; `ae71adb1` R-6 test.
- `e7625553` R-1; `a16ba2f8` R-7.
- `3f68608d` m-7; `cd07e8f0` m-6; `e7e6dd59` m-5; `146effaa` m-8.
- `1dbfdd84` R-2 test kept true on 3.13.
- `52e7571a` review.md statuses and spec §17 deviations 8 and 9.
- This log and the report follow in a docs-only commit.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (6 new functions) | each new test at the worktree, and under its mutant in `SCRATCH/mut` through `SCRATCH/s5_kill.py` | PASS; every named mutant KILLED | R-3 `handoff_no_surrogate_fix`, R-4 `no_sink_still_builds` and `no_sink_run_stopped`, R-5 `cost_any_not_all` and `cost_empty_rollups_known`, R-6 `resumed_root_only_finished`, `resumed_root_only_interrupted` and `run_finished_root_pairs`: each `KILLED :: 1 failed, 186 passed`. R-2 and m-5: red before the fix, green after |
| focused tests | `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider` | PASS | `192 passed in 6.48s` (baseline 186 + 6) |
| lint | `PYTHONPATH=$(pwd) python lint/run.py` (also the first step of the source stage) | PASS | `S064 RATCHETED: 4 known finding(s).` … `SDK-LINT: PASS`. No rule REGRESSED. The IMPROVED rules (A002, C011, S001, S010, S025, S061, S063) are the branch's existing state against main's baseline; `lint/baseline.json` was not touched |
| full gate, source stage @ `1dbfdd84` | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | FAIL, inherited only | `FAILED …test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, `::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `3 failed, 6122 passed, 16 skipped in 106.09s` / `CI failed: Command failed with exit code 1: … -m pytest`. The same three fail at base `7efceb55`: a `git clone --shared` in scratch, checked out at `7efceb55` with this repo's `origin/main` fetched, gives `3 failed, 6 passed in 3.89s` with the same three names. lint, compileall, and the three `check_*` scripts passed |
| full gate, package stage @ `1dbfdd84` | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| semgrep static policy @ `146effaa` (vidbyte/ is identical to the final head) | `PATH="<SCRATCH>/semgrep-venv/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1, mcp 1.23.3, scratch venv) | PASS | `Scanning 1223 files tracked by git with 1 Code rule:` / `Ran 1 rule on 982 files: 0 findings.` |
| public-API contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 52249854… (vidbyte-sdk 0.3.0, 647 exports).` |
| remote checks @ `52e7571a` | `gh workflow run CI` and `gh workflow run "Static policy"` (runs 38968773566, 38968776250), then `gh api …/commits/52e7571a…/check-runs` | 4/4 green | `Package success 52e7571a` / `Static policy success 52e7571a` / `Source / Python 3.12 success 52e7571a` / `Source / Python 3.11 success 52e7571a` |

**Still open:** no confirmed finding. Minors m-1, m-2, m-3, m-4, m-9 are `open (follow-up)` by ruling; m-10 is `wontfix (history)`. The only red gate cells are the 3 `harness_threads` surface tests, inherited from `7efceb55`. Forward m-8's corrected figure (31,093 bytes per whole event; 31,086 with microsecond 0) to the CLI and Vidbyte siblings: spec §9.1 Volume, §9.2 and INV-33 still say 31,091, and this iteration may not edit them.
