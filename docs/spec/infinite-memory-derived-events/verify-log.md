# Verification log: InfiniteMemoryAgent derived run events

Gate set (from `context/code-map.md` §1.4, AGENTS.md, and field guide `local-ci-verification.md`), all run locally from the worktree root, in this order:
1. Import path: `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` must print the worktree path.
2. New tests and pack: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`.
3. Lint: `python lint/run.py` must end `SDK-LINT: PASS`, with no per-rule count risen.
4. Public API: `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` (678 exports; root exports unchanged).
5. CI source stage: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`. Only the known inherited failure `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` may fail. It reads `assert 171 == 120`, counted from `vidbyte/lib/enums/failure.py` at the merge base `181f1992`, which this branch never touches; the field guide's `167` is an older main.
6. CI package stage: `python scripts/run_ci.py --stage package`, with no `PYTHONPATH`.
- Remote checks: none configured. Every workflow in `.github/workflows/` has its automatic triggers removed ("TEMPORARILY DISABLED"; `workflow_dispatch` only). Do not dispatch them. The local gate set is the authority.

## Iteration 1 — 2026-10-20 — agent report: reports/S5-repair-1.md
**Defects in:**
- R-2 (Major, code). It explained the failing pack gate: `2 failed, 416 passed`, both items of `test_an_interrupt_the_sink_raises_on_an_error_cards_finish_still_aborts_in_the_commit_phase`.
- R-1 (Major, docs).
- Minors R-7, R-8, R-9, R-10, R-11 (trivial docs).
- The EC-25 wording.
- R-3, R-4, R-5, R-6, and R-12 were test-owned. The S2 test author had already landed them at `4f51cef1`; this iteration verified them and marked them fixed. R-13 is `[scope-adding]` and stays open as a follow-up for the user.

**Hypotheses and attempts:**
- **R-2.** H1: the inner `except (VidbyteSdkError, OSError, ValueError)` branch of `InfinitePair.run` calls `_finish` without moving `phase` to COMMIT, so an abort raised inside that `_finish` reports the step that failed. Confirmed.
  - Reproducer: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py -q -k error_cards_finish` gave `2 failed` (`VERIFIER != COMMIT`, and the generator analogue).
  - Fix: `phase = InfinitePairPhase.COMMIT` as the branch's first statement. The three-line comment above it was rewritten at the same line count, each line ≤ 72 columns.
  - Result: `2 passed`, then the pack gave `418 passed`.
  - Alternatives rejected without trying:
    - Setting the phase inside `_finish` cannot work, because `phase` is a local of `run`.
    - Hoisting `phase = COMMIT` above the inner `try` would mislabel generator and verifier aborts.
    - A second `except BaseException` clause misses EC-25 (D-10's runner-up), and S024 is already at its limit of 3.
- **R-1.** Docs only, as the review settled. "Journal all, then announce" is REFUTED: it changes AC-10's `agents_started` from 4 to 6. It was not retried, and no code change was attempted. A catch-announce-re-raise around the start loop is the runner-up. It flips only if the dashboard must close every row with its own event (D-23).
  - EC-31's "User sees" claims `run_stopped` only for a root launch, which the S4 verifier observed (V3). For a nested launch, a `KeyboardInterrupt` inside an asyncio task unwinds differently, and no one has observed it.
- **R-7.** The same false claim also sat in spec §13's seam fact (line ~972), beyond the four sites the review named. It was fixed there too. §12.3 row 6 was left as the historical work order.
- **R-9.** The repo's grain (agent.py:9, runtime.py:9) prefixes a citation once, and the bare citations after it belong to the same spec. events.py:9 still reused `(EC-10)` across two specs, so every new citation now carries `derived-events`, as the review asked.
- **R-10.** `_derived_records` was added to workspace.py and journal.py as well, because it unit-tests their new `map_omitted` and `started`. This goes one file past the review's minimum on each.
- **Line endings.** Git stores LF and checks out CRLF (`core.autocrlf=true`; `git ls-files --eol` shows `i/lf w/crlf`), so exact-match edits are safe. spec.md and review.md are LF in the working tree.

**Changes:**
- `2c986483` fix(infinite): put an error card's finish in the commit phase [R-2]
- `36aaf8ce` docs(infinite): list the two batch stops that leave a launched pair unclosed [R-1]
- `8ff0cede` docs(infinite): say a child's error arrives as a VidbyteSdkError, not always wrapped [R-7]
- `86741ac0` docs(infinite): give memory_dropped's docstring all three drop reasons [R-8]
- `41f420c5` docs(infinite): prefix the derived-events citations in two module headers [R-9]
- `369e901e` docs(infinite): name the derived-events test files in six TESTS headers [R-10]
- `e7dd0ef8` docs(spec): name the lint's real last line, SDK-LINT: PASS [R-11]
- `f2de0b32` docs(spec): name phase commit in EC-25 [R-2]
- `8d80da21` docs(spec): record the S5 repair of infinite-memory-derived-events as r6

**Gate matrix out** (run at `8d80da21`; the source tree is unchanged by the later docs-only commits):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| import path | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` | PASS | `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-derived-events\vidbyte\__init__.py` |
| new tests (pack) | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q` | PASS | `418 passed in 9.14s` |
| lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`. Counts equal S3's: A007 255, A002 566, S051 259, S008 19, S024 25, S019 5. |
| public API | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 1332a34e… (vidbyte-sdk 0.4.0, 678 exports).` |
| CI source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except 1 inherited failure | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`AssertionError: assert 171 == 120`) / `1 failed, 7037 passed, 17 skipped in 231.39s (0:03:51)`; its lint step ends `SDK-LINT: PASS`. The failure is inherited: `171` is counted from `failure.py` at the merge base `181f1992`, which this branch never touches (the field guide's `167` is an older main). |
| CI package | `python scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| remote checks | `gh pr checks 1191` | none configured | Automatic triggers are disabled repo-wide; nothing was dispatched. |

**Still open:** R-13 (`[scope-adding]` follow-up; needs the user's decision and a spec amendment; not built). No confirmed finding is open. Every gate is green apart from the inherited source-stage failure.

## Iteration 2 — 2026-10-20 — agent report: reports/S5-repair-2.md
**Defects in:**
- The post-repair re-review (reports/S5-rereview-1.md) found the branch SOUND, with four Minors and no failing gate.
- R-C1 (spec G-1, G-3), R-C3 (spec D-10, D-22), and R-C4 (README, two docstrings) are text-only.
- R-C2 was test-owned. The S2 test author fixed it at `76314c4d`, and it was verified here, not touched. R-13 stays `[scope-adding]` and unbuilt.

**Hypotheses and attempts:**
- No gate was red going in, so there was no repeated failure to route around. Each fix was checked against running code, not only against the re-review's text.
- **R-C1.** H1: G-1's equality breaks only for `memory_committed`, which is what the re-review's suggested wording covered. Refuted in part.
  - Probe (scratchpad, the pack's own `ScriptedTree`):
    - EC-25 normal path: `memory_committed`, then `subagent_aborted (failed, OSError, commit, 0)`.
    - EC-25 error branch: `memory_staged`, `memory_dropped`, `subagent_aborted`.
    - AC-13 `second-commit-fails`: one `memory_committed`, then the abort.
    - The journal is `[run_started, pair_started, run_finished]` in all three, and no `subagent_finished` arrives.
  - So G-1's dropped count breaks too, and the exception now covers both counts. It is scoped to aborts "before its card is recorded", because EC-10 also aborts in the commit step but keeps its card.
- **R-C3.** D-22's new wording does not claim that a passed-through typed error "keeps its own class". `FailureRaisedError` is raised `from exc` at `sessions/failure/router.py:368` and `:508`, so the cause rule names that error's cause. The new text says the same rule applies to these errors.
  - Swept the spec for other stale sites. AC-14 and EC-1 describe cases that really are wrapped. §12.3 row 6 stays as the historical work order, as iteration 1 decided.
- **R-C4.** The new text claims that `CancelledError` from the sink behaves like EC-10's tested `KeyboardInterrupt`.
  - Probe: both give `subagent_finished`, then `subagent_aborted (cancelled, <class>, commit)`, then `run_stopped`. The journal holds `pair_finished`, and the same class is re-raised.
  - The package README cites no spec IDs anywhere, and AGENTS.md treats `docs/` as opaque. So the README note describes the EC-10 case in words, without the ID.
  - The two docstring edits are line-neutral: events.py is still 658/660 lines after its header, and the lib records are 832/870.
- **Text-only proof.**
  - `git diff 76314c4d..HEAD -- tests` is empty.
  - In `vidbyte/`, only two docstring lines and the README changed.
  - An AST comparison with docstrings stripped (`ast_same.py` in the scratchpad) reports `code-identical-without-docstrings=True` for both `.py` files.

**Changes:**
- `d5f61aa6` docs(spec): scope G-1 and G-3 to the paths the code keeps [R-C1]
- `20de6683` docs(spec): bring D-10 and D-22 up to the repaired code [R-C3]
- `6cb56b1f` docs(infinite): say an abort can follow a recorded card when the sink interrupts its finish [R-C4]
- `4d65f9a6` docs(spec): record the S5 repair 2 of infinite-memory-derived-events as r7 (spec r7: §16 s5-c1, s5-c3, s5-c4 and §17; review.md "Post-repair re-review Minors")

**Gate matrix out** (run at `4d65f9a6`):

| Gate | Command | Result | Final lines |
|---|---|---|---|
| import path | `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` | PASS | `C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-infinite-memory-derived-events\vidbyte\__init__.py` |
| new tests (pack) | `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` | PASS | `418 passed in 18.45s` |
| lint | `python lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS`. A007 255, A002 566, S008 19, S024 25, S051 259, S019 5, A009 0, all at baseline. S063 reports IMPROVED 4 → 3 (baseline not touched). |
| public API | `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at 1332a34e… (vidbyte-sdk 0.4.0, 678 exports).` |
| CI source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS except 1 inherited failure | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 171 == 120`) / `1 failed, 7037 passed, 17 skipped in 224.00s (0:03:43)`. Its lint step ends `SDK-LINT: PASS`. `git diff 181f1992..HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads` is empty. |
| CI package | `env -u PYTHONPATH python scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.4.0 passed smoke checks.` / `CI passed.` |
| remote checks | `gh pr checks 1191` | none configured | `no checks reported on the 'feat/infinite-memory-derived-events' branch`. Automatic triggers are disabled repo-wide, and nothing was dispatched. |

**Still open:** R-13 is a `[scope-adding]` follow-up that needs the user's decision and is not built. No confirmed finding is open, and every gate is green apart from the inherited source-stage failure.
