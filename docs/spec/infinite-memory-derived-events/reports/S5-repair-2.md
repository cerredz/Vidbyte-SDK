# S5 repair iteration 2: InfiniteMemoryAgent derived run events

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-derived-events`, branch `feat/infinite-memory-derived-events`, started at `76314c4d`. PR https://github.com/cerredz/Vidbyte-SDK/pull/1191. The spec is now r7 (status `reviewed`).

The packet held the post-repair re-review's three text-only Minors (R-C1, R-C3, R-C4); R-C2 was the S2 test author's fix at `76314c4d`. All three are fixed. Two fixes go beyond the re-review's suggested wording, because a probe showed that wording was still inaccurate. Every gate is green apart from the inherited source-stage failure, and the change is proven text-only.

## Gate matrix

The gates ran at `4d65f9a6`. The only later commit, `7f1b1329`, touches `verify-log.md` alone.

| # | Gate | Command | Result |
|---|---|---|---|
| 1 | Import path | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` | PASS |
| 2 | Infinite-memory pack | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS (418/418) |
| 3 | Lint | `python lint/run.py` | PASS, no per-rule count risen |
| 4 | Public-API contract | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS (678 exports) |
| 5 | CI source stage | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except 1 inherited failure |
| 6 | CI package stage | `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS |
| — | Remote checks | `gh pr checks 1191` | none configured |

**Gate 1**
```
C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-derived-events\vidbyte\__init__.py
```

**Gate 2**
```
........................................................................ [ 86%]
..........................................................               [100%]
418 passed in 18.45s
```

**Gate 3** (exit 0). The per-rule counts in the table equal iteration 1's and the baseline. A002 566 is under its baseline of 703. S063 IMPROVED 4 → 3 was already there in iteration 1, and its baseline was not touched.
```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
```
A007   operational-constants                     255    255 RATCHETED
A002   intent-comments                           566    703 IMPROVED
S008   bounded-function-complexity                19     19 RATCHETED
S024   maximum-control-flow-nesting               25     25 RATCHETED
S051   modernized-import-and-syntax-hygiene      259    259 RATCHETED
A009   readme-size-limit                           0      0 CLEAN
```

**Gate 4**
```
contracts/sdk-public-api.json is current at 1332a34e6205ab4c9a86615b0b37462cdd527002 (vidbyte-sdk 0.4.0, 678 exports).
```

**Gate 5.** The stage's lint step printed `SDK-LINT: PASS`, and its log holds exactly one `FAILED` line.
```
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 7037 passed, 17 skipped in 224.00s (0:03:43) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-infinite-memory-derived-events).
```
The failure is `AssertionError: assert 171 == 120` and is inherited. `git diff --stat 181f1992..HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads` is empty (the merge base with `origin/main` is `181f1992`).

**Gate 6**
```
No broken requirements found.
> ...venv\Scripts\python.exe -c from importlib.metadata import entry_points, version; ...
Installed vidbyte-sdk 0.4.0 passed smoke checks.
CI passed.
```

**Remote checks**
```
no checks reported on the 'feat/infinite-memory-derived-events' branch
```
Every workflow has its automatic triggers removed repo-wide. Nothing was dispatched.

## Text-only proof

- `git diff --stat 76314c4d..HEAD -- tests` prints nothing.
- `git diff --stat 76314c4d..HEAD -- vidbyte`:
  ```
   vidbyte/agents/infinite/README.md   | 3 ++-
   vidbyte/agents/infinite/events.py   | 2 +-
   vidbyte/lib/dataclasses/infinite.py | 2 +-
   3 files changed, 4 insertions(+), 3 deletions(-)
  ```
- `git diff -U0 76314c4d..HEAD -- 'vidbyte/*.py'` changes exactly two lines, both one-line docstrings: `subagent_aborted`'s at `events.py:457` and `InfiniteSubagentAbortedDetails`'s at `lib/dataclasses/infinite.py:685`.
- Independent check: a script parses each changed `.py` at `76314c4d` and at HEAD, removes the module, class, and function docstrings, and compares `ast.dump`. It prints:
  ```
  vidbyte/agents/infinite/events.py: code-identical-without-docstrings=True fully-identical=False
  vidbyte/lib/dataclasses/infinite.py: code-identical-without-docstrings=True fully-identical=False
  ```
  The script is in the session scratchpad (`ast_same.py`).
- Budgets are unchanged: `events.py` 670 lines (658/660 after its 12-line header), `lib/dataclasses/infinite.py` 844 (832/870), and `launch.py` untouched. The budget test passes. Both `.py` files keep CRLF, and neither has a `#` comment line over 72 columns.
- The README is 24,021 characters, under A009's 40,000.

## Findings

| ID | Status | Commit |
|---|---|---|
| R-C1 | fixed (wider than suggested; see below) | `d5f61aa6` |
| R-C2 | fixed by the S2 test author; verified unchanged here | `76314c4d` |
| R-C3 | fixed (D-22 worded more exactly than suggested; see below) | `20de6683` |
| R-C4 | fixed; the README notes name the case | `6cb56b1f` |
| R-13 | open · `[scope-adding]` follow-up, not built | — |

The record commit `4d65f9a6` bumps the spec to r7 and adds §16 rows s5-c1, s5-c3, and s5-c4 and the §17 r7 entry. In review.md it adds the "Post-repair re-review Minors" section, rows R-C1 to R-C4.

### R-C1: spec G-1 and G-3

Reproduction: `_commit` announces each `memory_committed` and rule `memory_dropped` as it goes, and `_finish` announces each unchecked `memory_dropped` before its journal write (`launch.py:394-428`). So any abort after those announcements leaves events that no card holds. I ran a probe with the pack's own `ScriptedTree`, in a scratchpad directory, with the classes patched in-process and restored afterwards:

| Path | Kinds | Abort | Journal |
|---|---|---|---|
| EC-25 normal path (`pair_finished` raises `OSError` twice) | `…, verifier_finished, memory_committed, subagent_aborted, run_finished` | `(failed, OSError, commit, 0)` | `[run_started, pair_started, run_finished]` |
| EC-25 error branch (generator stages, then its runner fails) | `run_started, subagent_launched, memory_staged, memory_dropped, subagent_aborted, run_finished` | `(failed, OSError, commit, 0)` | same |
| AC-13 `second-commit-fails` | `…, verifier_finished, memory_committed, subagent_aborted, run_finished` | `(failed, RuntimeError, commit, 1)` | same |

The re-review proposed excepting only "the entries a pair committed before it aborted". The second row shows that G-1's `memory_dropped` equality breaks too. G-1's "How we will know" now reads:

> …except for a pair that aborts in its commit step before its card is recorded (AC-13, EC-25): the entries it committed or dropped before the abort are announced but are on no card.

"Before its card is recorded" leaves out EC-10, which also aborts in the commit step but whose card is journaled and announced. G-3's batch sentence now reads "unless its pipeline raised or never ran (EC-26, EC-30, EC-31)". INV-9 ("for every pair that reaches `_finish`") was already scoped right and is unchanged.

### R-C3: spec D-10 and D-22

- **D-10.** The COMMIT parenthesis gains: "and set again as the first statement of the inner `except` branch, so an error card's `_finish` runs in phase `commit` too: EC-10, EC-25, §16 s4-2". This matches `launch.py:311`.
- **D-22.** The re-review suggested saying the three typed errors "keep their own class". That is not quite right for `error_type`: `FailureRaisedError` is raised `from exc` at `vidbyte/sessions/failure/router.py:368` and `:508`, so D-22's rule `type(error.__cause__ or error)` names its cause. The deciding reason now reads: "A child's error arrives as a `VidbyteSdkError` (`BaseAgent._generate_reply`, EC-27). Usually it is an `AgentExecutionError` raised from the original, whose own name would label provider outages, timeouts, and tool-loop bugs alike (R-2). Otherwise it is one of the three typed errors `BaseAgent` passes through unwrapped, which the same rule names by its cause when it has one and by its own class when it does not."
- **Sweep of the other sites.** I searched the spec for both stale claims.
  - AC-14 and EC-1 describe cases that really are wrapped, and EC-27 already names the pass-through.
  - §12.3 row 6 stays as the historical work order, as iteration 1 decided.
  - r2-17 is a history row.

### R-C4: "an abort means no card"

Reproduction: `_finish` journals `pair_finished` and then calls `subagent_finished`. `_shielded` catches only `Exception`, so a sink `BaseException` escapes to the outer handler, which announces the abort in phase `commit`. I probed both interrupt classes the new text names:

```
KeyboardInterrupt | kinds: [..., 'verifier_finished', 'subagent_finished', 'subagent_aborted', 'run_stopped'] | abort: [('cancelled', 'KeyboardInterrupt', 'commit')] | journal: ['run_started', 'pair_started', 'pair_finished'] | raised: KeyboardInterrupt
CancelledError    | kinds: [..., 'verifier_finished', 'subagent_finished', 'subagent_aborted', 'run_stopped'] | abort: [('cancelled', 'CancelledError', 'commit')] | journal: ['run_started', 'pair_started', 'pair_finished'] | raised: CancelledError
```

Edits, each replacing text in place:

- **README:120.** "a pair stopped before its card was recorded, or the sink raised `KeyboardInterrupt` or `CancelledError` on its `subagent_finished`, which this then follows; …"
- **README Notes for agents.** A new bullet after the EC-4/30/31 bullet: the sink case gives `subagent_aborted` (phase `commit`) right after the finish, the card is already journaled and announced, `in_flight` counts the pair once, and a consumer should close a row on its first closing event.
- **events.py:457 and lib/dataclasses/infinite.py:685.** "…stopped before its card was recorded, or whose finish the sink interrupted…", one line each.

A sweep of `vidbyte/`, `tests/`, `lint/`, and `scripts/` found no other site with the old claim and no test that pins its wording. The other prose about aborts (the enum docstrings, the summary template, `vidbyte/agents/README.md:183`, and the `launch.py` header) is accurate.

The README carries no spec IDs anywhere, and AGENTS.md treats `docs/` as opaque. So the note describes the EC-10 case in words and does not cite "EC-10". The code headers, which already use "derived-events EC-n", keep the citation.

## Commits

- `d5f61aa6` docs(spec): scope G-1 and G-3 to the paths the code keeps [R-C1]
- `20de6683` docs(spec): bring D-10 and D-22 up to the repaired code [R-C3]
- `6cb56b1f` docs(infinite): say an abort can follow a recorded card when the sink interrupts its finish [R-C4]
- `4d65f9a6` docs(spec): record the S5 repair 2 of infinite-memory-derived-events as r7
- `7f1b1329` docs(spec): verify-log iteration 2 for infinite-memory-derived-events. It also corrects the gate-set header's stale `assert 167 == 120` to the observed `171`.
- This report is committed after `7f1b1329`.

## Notes for the PR author

- G-1 and INV-10 now name every path on which a stream event has no matching card or closing event. The PR description can call these rare and accepted: AC-13 and EC-25 for G-1; EC-4, EC-10, EC-30, and EC-31 for INV-10; EC-26, EC-30, and EC-31 for `batch_finished`.
- Dashboard guidance, as the README now states it: close a pair's row on its first closing event, and close a batch's group on its pairs' last events or on the run's terminal event.
- R-13 (`InfiniteWorkspaceUsageDetails.level` accepts any value from 0 to 100) is the one open item. It needs the user's decision and a spec amendment.
