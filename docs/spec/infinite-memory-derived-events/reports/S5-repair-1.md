# S5 repair iteration 1: InfiniteMemoryAgent derived run events

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-derived-events`, branch `feat/infinite-memory-derived-events`, started at `11f8e6ea`. PR https://github.com/cerredz/Vidbyte-SDK/pull/1191. The spec is now r6 (status `reviewed`).

The session was interrupted once, after the R-2 edit and before its commit. On resume, `git diff` showed only the R-2 hunk (4 insertions, 3 deletions in `launch.py`), with no header change mixed in. It was re-verified (the pack and the lint) and committed alone.

## Gate matrix

The gates ran at `8d80da21`. Every later commit is docs-only under `docs/spec/`.

| # | Gate | Command | Result | Final lines |
|---|---|---|---|---|
| 1 | Import path | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` | PASS | `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-derived-events\vidbyte\__init__.py` |
| 2 | Infinite-memory pack (new tests included) | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q` | PASS (418/418) | see below |
| 3 | Lint | `python lint/run.py` | PASS | see below |
| 4 | Public-API contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | see below |
| 5 | CI source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except 1 inherited failure | see below |
| 6 | CI package stage | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | see below |
| — | Remote checks | `gh pr checks 1191` | none configured | Automatic triggers are disabled repo-wide (`workflow_dispatch` only); nothing was dispatched. |

**Gate 2**
```
........................................................................ [ 86%]
..........................................................               [100%]
418 passed in 9.14s
```

**Gate 3**
```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
- The per-rule counts this change could move equal S3's recorded pre-repair figures (`reports/S3-implementer.md`): A001 642, A002 566, A007 255 (exactly the baseline), A009 0, S008 19, S019 5, S020 1, S024 25, S051 259.
- The full 91-row per-rule table after R-2 alone is identical to the table at the end, so the docs commits moved nothing.
- A002 and S063 report IMPROVED from causes outside this change. Their baselines are left alone.
- No baseline was edited, and no suppression was added.

**Gate 4**
```
contracts/sdk-public-api.json is current at 1332a34e6205ab4c9a86615b0b37462cdd527002 (vidbyte-sdk 0.4.0, 678 exports).
```

**Gate 5**
```
E       AssertionError: assert 171 == 120
tests\features\harness_threads\test_harness_threads_surface.py:196: AssertionError
=========================== short test summary info ===========================
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 7037 passed, 17 skipped in 231.39s (0:03:51) ============
CI failed: Command failed with exit code 1: C:\Users\422mi\AppData\Local\Programs\Python\Python311\python.exe -m pytest (cwd=C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-derived-events).
```
The lint step inside this stage also ends `SDK-LINT: PASS`.

**Gate 6**
```
> ...\venv\Scripts\python.exe -m pip check
No broken requirements found.
> ...\venv\Scripts\python.exe -c from importlib.metadata import entry_points, version; import vidbyte; ...
Installed vidbyte-sdk 0.4.0 passed smoke checks.
CI passed.
```
This ran with `PYTHONPATH` unset (`env | grep -c ^PYTHONPATH=` printed 0) and exited 0. Afterwards `git status --porcelain` showed no build artifacts in the worktree.

**Guards**
- `git diff 4f51cef1..HEAD -- tests` is empty. No test was changed.
- `git diff --name-only 181f1992..HEAD -- vidbyte` still lists exactly the 13 files of §12.3.
- Budgets after the header: launch.py 456/470, events.py 658/660, lib dataclasses 832/870. Every touched header still ends at line 12.
- The package README is 23,376 characters (A009 limit 40,000).
- Every comment line added is at most 72 columns.

## Per finding

### R-2 (Major, code): fixed @`2c986483`, EC-25 wording @`f2de0b32`
- **Reproduced.** `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py -q -k error_cards_finish` gave `2 failed, 19 deselected`, with `At index 2 diff: <InfinitePairPhase.VERIFIER: 'verifier'> != <InfinitePairPhase.COMMIT: 'commit'>` (and `generator` for the other item).
- **Root cause.** The inner `except (VidbyteSdkError, OSError, ValueError)` branch of `InfinitePair.run` records the card through `_finish`, but `phase` still holds the step that failed. So the outer `except BaseException` names that step when `_finish` raises: a sink interrupt on `subagent_finished` (EC-10), or a second journal failure (EC-25).
- **Fix.** `phase = InfinitePairPhase.COMMIT` is now the branch's first statement. The comment above it reads "The pair is now in its commit step. After an error the …". It keeps three lines, each at most 72 columns.
- **What it leaves alone.** A `CancelledError` never enters that branch, so AC-12 (phase `generator`) and R-6's verifier cancel (phase `verifier`) are unchanged. Both pass in the pack.
- **After the fix.** The reproducer gives `2 passed`, and the pack gives `418 passed`.
- **Spec.** EC-25's "User sees" now reads "in phase `commit`", and §16 has row s4-2.

### R-1 (Major, docs): fixed @`36aaf8ce`
- **Spec.**
  - G-3 now reads "except in EC-4, EC-10, EC-30, and EC-31".
  - INV-10 now has four exceptions.
  - New EC-30 covers a `pair_started` write that fails part-way through a batch. The error escapes `execute`, and the loop reports "Tool execution failed: …". The pairs already announced never run, the journal lists them as interrupted, and `in_flight` stays raised, as in EC-4.
  - New EC-31 covers a sink `BaseException` on `subagent_launched`. `_shielded` catches only `Exception`, so no pair of the batch starts, and the batch's later tasks are neither recorded nor announced.
  - §16 has row s4-1.
- **Package README.** The note beside EC-4 (README:173) names both cases.
- **launch.py:9.** KNOWN EDGE CASES gains one clause and stays a single line.
- **Facts checked before writing the rows.**
  - `InfiniteRunJournal.pair_started` appends to disk before `_started`, so a failed write leaves that pair unrecorded.
  - `interrupted` lists started keys that have no card.
  - `_shielded` catches only `Exception`.
- **Claim scoped to evidence.** EC-31 says the run ends with `run_stopped` only for a root launch, which the S4 verifier observed (V3). A nested launch's interrupt unwinds inside an asyncio task, and nobody has observed that case.
- **Not attempted.** "Journal all, then announce" was refuted in S4: it changes AC-10's pinned `agents_started` from 4 to 6.

### R-7 (Minor, docs): fixed @`8ff0cede`
- **Checked first.** `BaseAgent._generate_reply` (`base.py:965-979`) passes `UsageAccountingError`, `FailureRaisedError`, and `AllModelsFailedError` through unwrapped. `issubclass` shows all three are `VidbyteSdkError`s, and only `AllModelsFailedError` is an `AgentExecutionError`.
- **Reworded.** The claim now reads "always arrives as a `VidbyteSdkError` (`AgentExecutionError`, or one of the three typed errors `BaseAgent` passes through unwrapped)" in five places:
  - launch.py:9;
  - README:178;
  - INV-19;
  - D-10's last sentence;
  - the §13 seam fact at spec line ~972, which carried the same false claim but was not in the review's list.
- **Left alone.** §12.3 row 6 is left as the historical work order.

### R-8 (Minor, docs): fixed @`86741ac0`
The `InfiniteMemoryDroppedDetails` docstring now names all three reasons: "never committed (its verifier dropped it, the pair had no verdict, or a rule refused it at commit)". No test source pins the docstring; the only grep matches were in compiled `.pyc` caches.

### R-9 (Minor, docs): fixed @`41f420c5`
- events.py:9: each new citation now reads "(derived-events EC-n)" (EC-4, EC-10, EC-17, EC-26, EC-28). The old-spec citations are unchanged.
- launch.py:9: "(EC-37)" now reads "(derived-events FR-15)".
- Both edits are line-neutral, and events.py stays at 658/660.

### R-10 (Minor, docs): fixed @`369e901e`
Each module's TESTS line now names the derived test files that prove its change:
- memory.py: `_derived_refusals`.
- workspace.py: `_derived_refusals` and `_derived_records`. `_derived_records` holds `test_map_omitted_reads_a_cut_maps_closing_line_and_never_raises`.
- journal.py: `_derived_pairs` and `_derived_records`. `_derived_records` holds `test_the_journal_lists_every_pair_start_in_order_with_repeats`.
- agent.py: `_derived_run`.
- lib/enums/infinite.py and lib/dataclasses/infinite.py: `_derived_records`.

Each edit was made by a byte-level script that keeps CRLF and changes exactly line 11. A001 stays at 642.

### R-11 (Minor, docs): fixed @`e7dd0ef8`
- `lint/core/report.py:58` prints `SDK-LINT: PASS`.
- The spec's `AGENT-LINT: PASS` is replaced at NFR-7, §11, and §12.4.
- §16 has row s4-11.

### R-3, R-4, R-5, R-6, R-12 (test-owned): fixed @`4f51cef1` by the S2 test author
I confirmed each one in the test source before marking it:
- R-3: the sink raises on `a`'s `subagent_finished` (derived_pairs :638).
- R-4: the AC-15 test seeds an earlier run's note and record (derived_run :270, :302).
- R-5: the new parametrized EC-10 error-branch test. It was red before R-2 and is green after.
- R-6: `test_a_run_cancelled_while_the_verifier_waits_announces_its_abort_in_the_verifier_step`.
- R-12: the `first-commit-fails-from-a-key-error` item.

### R-13 (Minor, `[scope-adding]`): open
This finding is not for repair. It needs a spec amendment and the user's decision (briefing §6).

### Spec bookkeeping @`8d80da21`
- §16 rows s4-8, s4-9, and s4-10 were added.
- §17 gained the r6 entry.
- The frontmatter moved to revision 6, updated 2026-10-20. Status stays `reviewed`.

## Test changes proposed
None. No test contradicts the spec.

## Findings I believe are wrong
None.

## Inherited failure (gate 5)
The source stage has one failure: `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, which fails with `assert 171 == 120`. It is inherited, and I proved this rather than assumed it.

- **Where the number comes from.** The assertion's left side comes only from `git show $(git merge-base origin/main HEAD):vidbyte/lib/enums/failure.py`. The test parses that file with `ast` and counts the string members of `FailureCode`.
- **Independent recount.** Running the same AST count at the merge base `181f1992` gives `FailureCode str members at merge-base 181f1992 = 171`.
- **The branch cannot reach it.** `git diff --stat 181f1992..HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads` is empty.
- **Same result at the base.** Run at the base commit, the same test reads the same file and fails with the same `171 == 120`.
- **Why 171 and not 167.** The field guide (`local-ci-verification.md`) records `167 == 120` at the older main `6f5a7310`. Main has added FailureCode members since then, which explains the 167 in the briefing.
- **Collected count.** 1 + 7037 + 17 = 7055 tests, which matches the briefing's expected count of about 7055 with the new tests.

## What remains open, and what to try next
- R-13 stays open as the user's follow-up.
- No confirmed finding is open, and every gate is green apart from the inherited failure above.
- If the conformance re-review challenges a wording:
  - EC-30 and EC-31 claim only what the code and the S4 verifier evidence show.
  - Neither row claims `run_stopped` for a nested launch, because no one has observed how a `KeyboardInterrupt` unwinds inside a pair's asyncio task.
  - If the re-reviewer wants that pinned, the next step is a sandbox probe (outside the worktree) of a sink `KeyboardInterrupt` on a depth-2 `subagent_launched`, not a code change.
