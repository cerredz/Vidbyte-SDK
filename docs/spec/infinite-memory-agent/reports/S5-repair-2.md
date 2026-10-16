# S5 repair iteration 2/8: InfiniteMemory agent

- **Branch and PR:** `feat/infinite-memory-agent`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1084 (draft).
- **Commits:** from 3d7f0e57 to 5c5b7d33 (pushed), plus the docs commit that carries this report.
- **No test or lint file changed:** `git diff 11b19a7d..HEAD -- tests/` and `git diff 3d7f0e57..HEAD -- lint/` are both empty.
- **Source diff:** 3 files, +32/−5 lines. They are `vidbyte/agents/infinite/workspace.py`, `vidbyte/agents/infinite/README.md`, and spec §17.

## Gate matrix

| Gate | Command | Result | Final lines |
|---|---|---|---|
| New tests | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS (was 4 failed, 107 passed) | `.......................................  [100%]` / `111 passed in 2.89s` |
| Lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| Import order (S051) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (no new finding) | `Found 223 errors.` / `[*] 223 fixable with the --fix option.` (origin/main also has 223. The only hit in an infinite file is main's own block at `runtimes.py:33`.) |
| Semgrep (CI only) | iteration 1's stub launcher, `scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte --metrics=off` | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 946 files: 0 findings.` / exit 0 |
| Full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `5284 passed, 14 skipped in 50.95s` / `CI passed.` / exit 0 |
| Full local gate, package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / exit 0 |
| Remote checks | `gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/1084` | none (workflows are disabled repo-wide) | `no checks reported on the 'feat/infinite-memory-agent' branch` (PR head 5c5b7d33) |

**Lint counts.** I captured the lint output at 3d7f0e57 before any change, and compared each later run's 133 rule lines with it using `diff`. The lines were identical after R-26, after R-27, and in the final run. The final counts include C012 23, S061 5, S062 889, S008 19, and S051 259. The import target was confirmed as the worktree's `vidbyte/__init__.py`. The known-flaky MCP stdio test did not fail this run.

## Per finding

### R-26 (Major) — fixed in 582b5793

**Root cause.** `LocalFileSystemBackend.copy` uses `shutil.copy2`, which copies a read-only seed's mode bits onto `seed/<name>`. The next construction over the same `memory/` then cannot overwrite that copy.

**Fix.** Setup binds `copy`, copies the seed through the backend, and then runs `copy.chmod(copy.stat().st_mode | stat.S_IWRITE)`. It also:
- adds `import stat`;
- adds one sentence to the setup `@intent` comment;
- deletes the KNOWN EDGE CASES sentence.

Tools still cannot write under `seed/`, because `_note_path` enforces that, not the mode bits.

**Evidence.**
- `test_a_read_only_seed_is_copied_again_each_time_an_agent_attaches` passes.
- `-k seed` gives `4 passed`.
- `c1_ro_seed.py` prints `built | copy writable: True | copy == source: True` for the 1st, 2nd and 3rd constructions. The 3rd construction comes after the seed was edited.
- S061 stays at 5.

### R-27 (Major) — fixed in c90b43be

**Root cause.** A write that changes two files encoded each text only inside `_replace`. Text UTF-8 cannot hold therefore failed on the second file, after the first was already on disk.

**Fix.**
- **`_entry_rules`.** Its new first block, `@intent unwritable-entries-are-refused-first`, encodes `(draft.text, *draft.refs)`. Staging (`check_entry`) and root commits (`commit_entry`) both refuse before anything is staged or written. `commit_entry` needs no loop of its own, because its other texts are raw lines read with `errors="replace"` or fields bound by a pattern.
- **`write_note`.** After `_room`, `@intent a-refused-note-writes-nothing` encodes every value of `changed` before the write loop.
- **Unchanged.** `_commit` still catches only `ToolExecutionError` (INV-29). The memory tools' catch tuples are also untouched; they already turn the `UnicodeEncodeError`, a subclass of `ValueError`, into "Nothing was saved …" with the quota line.
- **Header.** The inventory line for `_entry_rules` and one KNOWN EDGE CASES sentence are updated. That sentence records the staging check and why `_commit` never sees the error.

**Evidence.**
- All three R-27 tests pass. The pair test takes the "refused when staged" branch.
- `c2_partial.py`:
  - steps 2–4 give `changed files: []` and `superseded ids: [] | live ids: [1]`;
  - step 5 leaves `['notes/b.md']` with `created counter: 1`;
  - step 6 is refused.
- Step 6 then prints `IndexError`. That is the probe indexing an entry that was never staged, not a defect.
- `rr/r1_guard.py` gives `Verdict: passed` for both pairs and `entries.jsonl texts: ['a first fact', 'a third fact', 'b fact']`.
- No comment line passes 72 columns (`awk 'length($0) > 72' workspace.py | grep -E '^\s*#'` prints nothing).

### R-28 (Minor, trivial) — fixed in 5c5b7d33

**Spec §17.** The S3 bullet on `runtimes.py` now says the file changes only by the import and the registry row, with a note that S5 corrected it per R-5 and R-28. Evidence:
- `git diff origin/main...HEAD -- vidbyte/lib/registries/runtimes.py` shows only those two lines.
- `PYTHONIOENCODING=utf-8 python lint/run.py --rule S062 --all` lists main's own `runtimes.py:53` finding and none in the infinite test files.

A new "Implementation deviations (S5)" list names five rules:
- a note path is one line and holds no colon (R-1, R-8);
- the model must be in `ProviderModelRegistry`'s catalog, relaxed with `STRICT_MODEL_VALIDATION` (R-7);
- `INFINITE_MIN_CAP = 1` (R-15);
- journal lines are ASCII JSON (R-1);
- memory text must be UTF-8-encodable (R-27).

"Seed copies keep mode bits" is not listed, because R-26 removed it.

**README.** The folder README's limits list gains one bullet. It says `model_name` must be in the catalog under `provider` and names `ProviderModelRegistry.STRICT_MODEL_VALIDATION = False`.

**Scope deviation from the review row.** The review's fix text also suggested adding "one line, no colon" to INV-20. I did not do that, because the briefing granted only the §17 list and the fix to the stale bullet ("Change nothing else in the spec"). The §17 list records the rule instead.

### R-29 and the follow-up Minors

Left `open` by instruction: R-29, R-14, R-19, R-20, R-22, R-24 and R-25.

## "Gets right" re-checked

- **AC-1.** It is in the pack, which passes.
- **The R-1 guard and ASCII journal.** Untouched. `r1_guard.py` still shows `pair_finished per key: {'root/a': 1, 'root/b': 1}`.
- **Locks and ids.** The one class-level lock, and ids from `max(live ∪ superseded) + 1`, are untouched.
- **Guard tuple.** `(VidbyteSdkError, OSError, ValueError)` is unchanged; no catch was added or widened.
- **Scope.** Unchanged: the only source change is in `workspace.py`, plus one README bullet and the spec edit I was granted.

## Test changes proposed

None.

## Findings I believe are wrong

None.

## What remains open, and what I would try next

**R-29** (`follow-up`). On Windows, a second process can hold `entries.jsonl` or `files.jsonl` open when the second `os.replace` runs. The two candidates are:
- inside `commit_entry` and `write_note`, on an `OSError` from the second `_replace`, write the first file back from the text already read under the lock;
- record the case beside the crash case in INV-19 and the README.

Either is a small change in `workspace.py`. Reproduce it with `PYTHONPATH=$(pwd) python $V/c2_lock.py $V/work_c2`, where `$V` is the verifier's scratch folder named in review.md. The R-27 encode checks do not cover this case, because the failure is the OS refusing the swap, not encoding.
