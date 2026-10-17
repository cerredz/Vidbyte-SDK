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

## Iteration 2 — 2026-10-17 02:52 — agent report: reports/S5-repair-2.md
**Defects in:** the 3 Minors from the post-repair re-review (reports/S5-rereview-1.md), R-C1..R-C3, recorded in review.md as rr-1..rr-3. R-C1 is a regression that m-5 introduced in `require_callable`. R-C2 and R-C3 are comment corrections. No gate was red at the start (`5bf5bfc7`): focused tests 192 passed, and the orchestrator's source-stage run at `9cc288ca` had only the 3 inherited `harness_threads` failures.

**Hypotheses and attempts:**
- R-C1, reproduced first. `SCRATCH/s5r2/rc1_repro.py` checks 22 callables and compares each verdict with whether calling the callable makes a coroutine. At `5bf5bfc7` it gives `4 wrong verdicts of 22`, all ACCEPTED although each one makes a coroutine: `AsyncPartial(print)`, `partial(AsyncPartial(print))`, `AsyncPartial(partial(print))`, and `partial(partial(AsyncPartial(print)))`. The briefing's import `from vidbyte.lib.dataclasses.validation import require_callable` does not exist. The real call is `RecordFieldValidator.require_callable(value, field_name, *, optional, synchronous)`.
- R-C1, the re-review's one-clause fix (`… or inspect.iscoroutinefunction(type(value).__call__)`) was rejected. `SCRATCH/s5r2/rc1_candidates.py` runs it over the same 22 inputs and it still gets 2 wrong on 3.11: `partial(AsyncPartial(print))` and `partial(partial(AsyncPartial(print)))`. The reason is that the unwrap loop skips the middle layer. The same script on 3.13 shows 0 wrong for both fixes, because from 3.13 `functools.partial` merges a partial subclass that has no instance `__dict__` into the partial around it. The CPython 3.12 source (`_functoolsmodule.c`, which merges only when `tp_call == partial_call`) shows that 3.12 behaves like 3.11, so the hole is real on the CI matrix.
- R-C1, chosen fix: check every layer, meaning the value and each partial it wraps, for both `iscoroutinefunction(layer)` and `iscoroutinefunction(type(layer).__call__)`. The code is still 3 lines, and the comment grows by 1 line. Result: `0 wrong verdicts of 22` on 3.11, and 0 on 3.13 through the candidates script. The new test's nested case gives the inner partial an attribute (`inner.label`), which stops the 3.13 merge, so the test holds on every Python. A probe confirmed that on 3.11 and 3.13 a partial with a `__dict__` keeps its async layer (`with dict: AP coroutine`).
- R-C1, kill check. `SCRATCH/s5r2/rc1_kill.py` runs the three `require_callable` tests against each version of the condition. Results: head `PASS`. The pre-m-5 condition, the condition at `5bf5bfc7`, the re-review's fix, and a "refuse every partial subclass" mutant are each `KILLED` by the new test. Separately, `validation.py` was put back at `5bf5bfc7` in the worktree, which gave `1 failed, 4 passed` (the new test failed), and was then restored.
- R-C2, re-measured before rewording. `SCRATCH/s5r2/rc2_measure.py` uses the AC-30 builders with 5 fills, 5 summary fills, 3 roles, 3 `at` precisions, and all 4 `json.dumps` settings. Results: details worst case `27015` (subagent_finished); whole-event worst case `31093` (subagent_finished, generator role, U+1F600); the envelope adds `4078` for subagent_finished and at most `4079` for any kind (generator_finished). The comment states all three figures, so 27,015 + 4,079 is not misread as 31,094.
- R-C3, the claim was checked before rewording. `git grep -nE "\[: ?[a-z_]+ - len\("` finds 4 rstrip-plus-suffix cuts in `vidbyte/context`, and `agents/aggregation.py:170` appends its marker after the limit. None of them calls `truncate_chars`. Only comments were changed.
- Tooling: the R-C3 commit was first made as `docs(text): …` and amended to `fix(text): …` before any push, to match the `fix(<scope>)` rule. A run stopped at the account usage limit after the fix commits and resumed with the review.md rows not yet committed. They were committed first on resume.

**Changes:**
- `d913802b` R-C1: `vidbyte/lib/dataclasses/validation.py` (layered check, `@intent` block, header KNOWN EDGE CASES) and one new test function in `tests/test_record_field_validation_event_options.py`, with 2 sink classes and header inventory lines. No existing assertion changed.
- `3bd374c3` R-C2: `vidbyte/lib/constants/infinite.py:147-149`, comment only.
- `2073421b` R-C3: `vidbyte/lib/util/text.py:19-23` and `vidbyte/context/handoff/infinite.py:106`, comments only.
- `6c7e0bd1` review.md rows rr-1..rr-3. This log, the report, and the remote-check record follow in docs-only commits.

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new test (1 function) | `rc1_kill.py`, plus `validation.py` at `5bf5bfc7` in the worktree | PASS at head; red before the fix | head `PASS []`; pre_m5, m5_at_5bf5bfc7, reviewer_fix, refuse_every_partial_subclass each `KILLED`; at `5bf5bfc7`: `FAILED …::test_require_callable_refuses_a_partial_subclass_whose_own_call_is_async` / `1 failed, 4 passed in 0.87s` |
| focused tests @ `6c7e0bd1` | `PYTHONPATH=$(pwd) PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/features/infinite_memory_agent tests/test_record_field_validation_event_options.py tests/test_output_text_truncate_marker.py -q -p no:cacheprovider` | PASS | `193 passed in 6.03s` (192 + 1) |
| lint @ `2073421b` | `PYTHONPATH=$(pwd) python lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS`. No rule REGRESSED. The IMPROVED set is the same as in iteration 1 (A002, C011, S001, S010, S025, S061, S063). `lint/baseline.json` was not touched |
| full gate, source stage @ `2073421b` | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | FAIL, inherited only | `SDK-LINT: PASS`; `context write-path integrity: ok`; `context primitive introductions: ok`; `reasoning trace contracts: ok (182 tools, 55 shapes)`; then `FAILED …test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, `::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, `::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` / `3 failed, 6123 passed, 16 skipped in 104.75s` / `CI failed: Command failed with exit code 1: … -m pytest`. These are the same three names that fail at base `7efceb55` (iteration 1). There is 1 more pass than the orchestrator's `9cc288ca` run (6122), which is the new test |
| full gate, package stage @ `6c7e0bd1` | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| semgrep static policy @ `6c7e0bd1` | `PATH="<SCRATCH>/semgrep-venv/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1) | PASS | `Ran 1 rule on 982 files: 0 findings.` |
| public-API contract @ `6c7e0bd1` | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 52249854c2da0ca5961a743e961d5b8972fa35ce (vidbyte-sdk 0.3.0, 647 exports).` |
| remote checks | `gh workflow run CI` and `gh workflow run "Static policy"` on the pushed head, then `gh api …/commits/<sha>/check-runs` | see reports/S5-repair-2.md | Dispatched after this log is pushed. The run ids and conclusions are recorded in the report, and the final head is dispatched again so that its own check-runs show the result |

**Still open:** no confirmed finding. rr-1..rr-3 are fixed. Minors m-1, m-2, m-3, m-4 and m-9 stay `open (follow-up)` by ruling, and m-10 stays `wontfix (history)`. The only red local gate cells are the 3 `harness_threads` surface tests, which are inherited from `7efceb55`. The sibling forward from iteration 1 still stands: spec §9.1, §9.2 and INV-33 say 31,091, but the measured whole event is 31,093.
