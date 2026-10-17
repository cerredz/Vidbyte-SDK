# S5 · Repair iteration 1/8 — report

Status: DONE.
- Started from HEAD `a7f53b09`.
- The code commits end at `8da92fb9`, which is pushed and remotely checked.
- After them comes the `docs(spec)` commit. It carries this report, verify-log.md and the review.md statuses.

verify-log.md, iteration 1, has every hypothesis I tried and every command I ran.

## Outcome

- **Findings fixed.**
  - Every confirmed finding handed in is fixed: R-1 to R-7.
  - Every test-pack finding is fixed: R-8 to R-11 and R-24, whose tests in fd6dab0b are now green.
  - The trivial Minors R-12 to R-16 and R-19 are fixed.
- **Not touched.** Follow-ups R-17, R-18, R-20, R-21 and R-22, the waived R-23, and the refuted rows.
- **Merge.** Main 6f5a7310 is merged in, so the PR no longer conflicts.
- **Tests.**
  - The 10 tests that were red at a7f53b09 are now green.
  - The related suites give `346 passed`.
  - The whole `tests/` tree gives `3 failed, 6580 passed, 16 skipped`. The 3 failures are the inherited `harness_threads` surface tests (see below).

| Row | Commit | Fix | Independent check |
|---|---|---|---|
| merge-main | 16e39b73 | Merged origin/main 6f5a7310 (#1055). The one conflict, the toolsets `__init__` header inventory, keeps both lines. | The contract is current at 645 exports. The related suites are unchanged at 10 failed, 336 passed. |
| R-1 | 848469a2 | The recall `question` description loses its examples: "and any limit on the answer." | The leaf states no number (INV-0.3). |
| R-2 | 0e41b3a2 | Following FR-8.6 and INV-8.2: blank-check the raw query, then turn NUL into a space and drop lone surrogates. Entry lines and note names that UTF-8 cannot encode are left out (EC-8.8). | Verifier fuzz: every query succeeds; `'a\x00b'` gives 1 of 1, `'\ud800x'` gives 0 of 0. Poison probe: later searches succeed. Recall probe: the retriever starts. |
| R-7 | 7eb2942c | A private `os.scandir` walk (`_listing`) stats every file, and sniffs or reads only those whose `(mtime_ns, size)` changed. `base.py` is untouched. | Re-run at 8da92fb9 with 1,900 files and 8,000 entries: warm `4 ms` (was 494–532 ms), cold `952 ms` (was 1,362 ms), 20 parallel warm searches `81 ms` wall (was 9,916 ms). The walk-equivalence probe matches `iter_files`. |
| R-3 | 5634b579 | A scoped window never masks an output that comes after the newest `assistant` or `model` turn. Unscoped windows are unchanged. | Verifier probes: Gemini sequential reads mask 2. Parallel batches of 3 to 8 mask 0 on every wire. |
| R-6 | 5698fdab | Only the repeat digest uses `surrogatepass`, so the sent body is unchanged. | `LoneSurrogateTests` green. |
| R-4 | 7d6d7449 | The gate is now inline in `_create_payload`, and `_marked_message` is folded into `_attach_cache_breakpoints`. | The AST depth scan finds no new 3-level chain. The in-place mutation fails 14 of 15 cache tests. 620 Anthropic-referencing tests pass. |
| R-19 | d7bb1f4a | The pre-search and the task build sit inside the retriever's guarded `try`. | A raise there returns the recall-shaped error. Nothing awaits between the quota check and its increment. |
| R-14 | 468303dc | `await asyncio.to_thread(self.workspace.map_snapshot)`. | Related suites green. |
| R-13 | 1fbe3ede, then 8da92fb9 | `vidbyte.lib.util.fulltext` is imported by its literal name and the export is returned with `getattr(module, name)`. | C003 is clean and S015 is ratcheted. A `Bogus` map entry raises `AttributeError`. 13 fulltext tests pass. |
| R-12 | 3ec30b9e | The README now says "(see Anthropic Prompt-Cache Marks above)". | A009 stays under its ceiling. |
| R-15 | a805c951 | Two headers now name `recall.py` and the search and recall tests. | A001 ratcheted. |
| R-16 | 7ab9a924 | `InfiniteSearchMemoryTool` added at `llms.txt:519` and `:815` and at `artifacts/file_index.md:422`. No generator owns these lines. | BOM and CRLF are kept. |
| R-5 | 1a6365e6 | Greedy 72-column rewrap of 33 new comment lines in 16 files. Each rewrap is limited to the paragraph that holds the line. | The awk check prints only the 6 refuted on-main `windows.py` lines. A002 passes. |

## Gates (final lines; all run in this worktree in this iteration)

**New tests.** Command: the related suites listed in the verify-log gate set. Result at 8da92fb9:
```
........................................................................ [ 83%]
..........................................................               [100%]
346 passed in 9.34s
```

**Lint.** Command: `PYTHONIOENCODING=utf-8 python lint/run.py`. Result at 8da92fb9:
```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
- On origin/main 6f5a7310, run in a scratch git copy, the count is equal for all 133 lines of rule counts (`diff` is empty).
- The IMPROVED verdicts come from main's stale baseline. The baseline is untouched.

**Source stage.** Command: `PYTHONPATH="$(cygpath -w "$(pwd)")" python scripts/run_ci.py --stage source`. Result at 8da92fb9:
```
reasoning trace contracts: ok (182 tools, 55 shapes)
...
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded
=========== 3 failed, 6580 passed, 16 skipped in 116.66s (0:01:56) ============
```
- Before the run that produced these lines, the first source run (at 1a6365e6) stopped in lint with `C003 REGRESSED: 1 finding(s), allowance 0`.
- That regression came from the R-13 attempt and is fixed in 8da92fb9.

**Package stage.** Command: `env -u PYTHONPATH python scripts/run_ci.py --stage package`. Result:
```
No broken requirements found.
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

**Contract.** Command: `python scripts/generate-sdk-public-api.py --check`. Result:
```
contracts/sdk-public-api.json is current at 5ccc4926362e7f46620a1e1594d28f6b2686c959 (vidbyte-sdk 0.3.0, 645 exports).
```

**Semgrep 1.170.1, pinned venv.** Commands: `semgrep --test …` and `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`. Result: exit 0.
```
1/1: ✓ All tests passed
 • Findings: 0 (0 blocking)
Ran 1 rule on 1008 files: 0 findings.
```

**Remote checks.** Both were dispatched with `--ref feat/infinite-memory-context-economy`, and both runs have `headSha` 8da92fb9:
- static-policy.yml, run 39017632180: `Static policy: completed/success 8da92fb9`.
- ci.yml, run 39017630351: success. The jobs API shows 3/3 completed/success at 8da92fb9. From the run log:
```
Source / Python 3.12 | ========== 6399 passed, 200 skipped, 19 warnings in 129.38s (0:02:09) ==========
Source / Python 3.12 | CI passed.
Source / Python 3.11 | ================= 6399 passed, 200 skipped in 88.15s (0:01:28) =================
Source / Python 3.11 | CI passed.
Package | Installed vidbyte-sdk 0.3.0 passed smoke checks.
Package | CI passed.
```

## Inherited source-stage failures

Each test compares the checkout with `git merge-base origin/main HEAD`. After the merge, that merge base is main 6f5a7310 itself.
- `test_failure_codes…` fails with `assert 167 == 120`.
  - Main's own `FailureCode` has 167 members, counted from `git show 6f5a7310:vidbyte/lib/enums/failure.py` with an AST.
  - The branch does not touch that file: `git diff --stat 6f5a7310 HEAD -- vidbyte/lib/enums/failure.py` is empty.
  - So the test fails on main itself in any checkout that has `origin/main`.
- `test_branch_leaves_the_tools…` fails on any branch that changes `vidbyte/tools`. This PR changes it by design (§12.3 rows).
- `test_import_vidbyte…` fails because the root `__all__` gains `InfiniteRecallMode`, the §8.4 public export.
- All three skip or return early without `origin/main`:
  - On a git-less copy of main 6f5a7310, the file gives `8 passed, 1 skipped`.
  - CI's checkout (`actions/checkout` without `fetch-depth`) is the same case, so the remote Source jobs pass.
- This is the same set the briefing measured at a7f53b09. I did not edit any of these tests.

## Interpretation, not a dispute: R-19

The briefing asks that a failing pre-search not spend quota without starting a retriever. The attempt still counts, for three reasons:
- Refunding it would put an `await` between the quota check and its increment, which the "gets right" list forbids.
- INV-10.6 frees only calls refused for validation or quota.
- EC-10.3 counts an attempt that fails after it starts.

The failure is now recall-shaped. R-2 removes every known trigger: the pre-search raises for none of the verifier's inputs.

## "Gets right" list re-checked

- Marks go only on copies; the mutation still fails.
- Nothing awaits between the quota check and its increment.
- The lock is held across refresh and search inside `to_thread`.
- `entries.jsonl` is listed up to `largest_file_bytes`, the same cap `is_text_file` applied before.
- Masking stays first in the root middleware.
- Unscoped windows keep main's output.
- `base.py` is untouched.
- Nothing new was added: no class, no dependency, no module.
- The lint counts equal main on every rule.
- The baseline, tests and CI files are unchanged. `git log --first-parent 3bda907e..HEAD -- tests` lists only the merge commit.

## Open items

- No confirmed finding is open.
- Every gate is green, apart from the 3 inherited `harness_threads` surface tests described above. They fail locally only, and they skip on CI.
- These items stay as the briefing set them:
  - R-17, R-18, R-20, R-21 and R-22 are follow-ups.
  - R-23 is waived.
- The `docs(spec)` commit that carries this report was dispatched to remote CI again after push. Its result is in the STATUS block returned to the orchestrator.
