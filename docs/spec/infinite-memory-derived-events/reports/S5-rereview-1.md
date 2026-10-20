LENS: conformance (post-repair re-review)
VERDICT: SOUND — every repaired finding holds at `2e3696f7` and a test now pins each one, and no new Blocker or Major exists. Four Minor inconsistencies remain in the docs and in one test pin. None changes behaviour, and each is a small text or assertion edit.

Reviewed: `git diff origin/main...2e3696f7` (merge base `181f1992`), and every change since the S3 head `c1c3ecc0`. That window holds one executable line of source, `launch.py:311`. The rest is headers, docstrings, the README, the spec, and the tests changed at `4f51cef1`.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The R-2 fix is one line, correct, and pinned.**
  - `phase = InfinitePairPhase.COMMIT` is the first statement of the inner `except` branch (`launch.py:311`). It adds no literal and no nesting: A007 stays at 255 and S024 at 25, both equal to the baseline.
  - Reverting it in-process makes the pack fail with `2 failed, 416 passed`, both at `test_infinite_memory_derived_pairs.py:736`.
  - A run-level EC-25 probe (a journal write that fails twice) gives `('alpha','failed','OSError','commit',0)` on both the normal path and the error-card path. The next launch reads `in_flight` 1, so the abort decremented the count.
  - The AC-12 test (phase `generator`) and the R-6 verifier-cancel test (phase `verifier`) still pass. A `CancelledError` never enters the inner `except`.
- **The R-1 docs describe what the code really does.**
  - The EC-30 probe gives `['run_started','subagent_launched','run_finished']`, the root reads "Tool execution failed: [Errno 28] No space left on device", and the journal reads `[run_started, pair_started, run_finished]`.
  - The EC-31 root probe gives `[run_started, subagent_launched a, run_stopped]`.
  - The nested EC-31 case, which nobody had observed before, gives `subagent_launched n`, then `subagent_aborted a` (cancelled, KeyboardInterrupt, generator), then `run_stopped`. That stays inside what the row claims.
  - `README.md:173` and the `launch.py:9` header say the same thing.
- **Scope and shape are unchanged since S4.**
  - The source diff is still the 13 files of §12.3.
  - `runtime.py`, `base.py`, `middleware/`, `pipelines/`, `lint/`, `contracts/`, and the root `__init__` all have an empty diff.
  - The tests have not changed since `4f51cef1`, and `4f51cef1` only adds or tightens.
  - Each new kind has exactly one call site (FR-17).
  - Budgets: events.py 658/660, launch.py 456/470, lib records 832/870, 9 modules. Every header ends at line 12.
- **The test-owned fixes catch their mutations.** I re-ran each mutation in-process. M1 is caught only by the R-6 test, M7 only by the R-3 test, M10 by the R-4 test, and M11 only by the R-12 item. The §4 snippet in the AC-1 test is byte-equal to the spec text, and it also runs verbatim against a script I wrote myself.

## FINDINGS

R-C1 [Minor] [weighted word / every-ID] `docs/spec/infinite-memory-derived-events/spec.md:50` (G-1) and `:52` (G-3) — two goal measures still claim more than the code keeps, on paths the spec itself accepts
  Evidence:
  - **G-1** says: "In any finished run, the `memory_committed` count equals the entry ids on all pair cards". The spec's own AC-13 test (`second-commit-fails`) pins two things against that:
    - kinds `[…, "verifier_finished", "memory_committed", "subagent_aborted", "run_finished"]`;
    - journal `["run_started", "pair_started", "run_finished"]`.

    So the run finishes with 1 `memory_committed` and no card. My EC-25 probe shows the same pattern: `memory_committed`, then `subagent_aborted`, and no `pair_finished` for `alpha`. INV-9 is scoped correctly ("for every pair that reaches `_finish`"); G-1 is not.
  - **G-3**'s second sentence says: "Each batch that started pairs is closed by one `batch_finished`, unless its pipeline raised (EC-26)". In EC-30 and EC-31 the batch announced pairs and its pipeline never ran. The EC-30 probe gives `['run_started','subagent_launched','run_finished']`, with no `batch_finished` and no raise from a pipeline. R-1's fix (`36aaf8ce`) widened only G-3's first, pair-level sentence.
  Failure: The user's next step is a dashboard. A consumer that reconciles commits against cards (G-1), or waits for `batch_finished` to close a group (G-3), finds a mismatch on these rare paths: the AC-13 and EC-25 aborts, and the EC-30 and EC-31 batch stops. The spec then gives two answers about what to expect.
  Smallest fix: Two spec-only edits.
  - G-1: "…equals the entry ids on all pair cards, plus the entries a pair committed before it aborted in its commit step (AC-13, EC-25)…".
  - G-3: "…unless its pipeline raised or never ran (EC-26, EC-30, EC-31)".
  Spec IDs: G-1, G-3, INV-9, AC-13, EC-25, EC-26, EC-30, EC-31

R-C2 [Minor] [every-ID / tests] `tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py:296` — the `verifier_started` summary pin accepts a count the spec ruled out at r4, and a mutation that uses that count survives
  Evidence:
  - The test reads `assert started.summary in {f"{PAIR}/ver is checking 2 staged entries and {count} notes" for count in (7, 5)}`.
  - The spec settled the question at r4 (§16 s2-1, the §8.5 comment at `:517`, and §9.2 at `:692`): "`{files}` is `len(files)` … never the number of names shown", which is 7 here.
  - In-process mutation of `events.py:396`, `files=len(files)` → `files=len(shown)`, gives `418 passed`.
  - A control mutation, `len(shown)+1000`, gives `2 failed`, so the patch was live.
  - `stream:222` uses 1 note, so it cannot tell the two counts apart.
  - Three texts are now stale:
    - the test header's KNOWN EDGE CASES (`:9`) still says the spec "does not settle" this;
    - `test-plan.md:263` (Open item 1) still asks the spec owner to settle it;
    - `test-plan.md:264` (Open item 2, settled at r4 as EC-29) and `:279` (Open item 8, "red until the R-2 fix lands", fixed at `2c986483`) are also out of date.
  Failure: If `verifier_started` regresses to the five-name count, its summary under-reports the notes a verifier checks, and the pack stays green.
  Smallest fix: This is a tests-owner change, routed to S2.
  - Assert `started.summary == f"{PAIR}/ver is checking 2 staged entries and 7 notes"`.
  - Drop the stale sentence from the header (`:9`).
  - Mark test-plan Open items 1, 2, and 8 as resolved (r4, r4/EC-29, and `2c986483`).
  Spec IDs: FR-9, §9.2 (s2-1), §8.5

R-C3 [Minor] [deviations / doc consistency] `docs/spec/infinite-memory-derived-events/spec.md:365` (D-10) and `:381` (D-22) — the repair left two decision rows stating facts from before the repair
  Evidence:
  - **D-10** still places COMMIT at one point only: "COMMIT (set after the `if status is not FAILED:` block, just before `if verdict is not UNCHECKED:` …)". The code now also sets it at `launch.py:311`.
  - §16 row s4-2 lists "§8.1 D-10" among the sections it changed, but `git diff --word-diff c1c3ecc0 2e3696f7` shows D-10 changed only in its last sentence, which was R-7's edit.
  - **D-22**'s deciding reason still reads "A child's error arrives as `AgentExecutionError` raised from the original (`BaseAgent._generate_reply`)". That is the claim R-7 (`8ff0cede`) corrected at five other sites. `issubclass` prints `UsageAccountingError True False` and `FailureRaisedError True False` for (VidbyteSdkError, AgentExecutionError).
  Failure: A maintainer who reads D-10 as the decision of record could take the second assignment for a stray line and "simplify" it away. The test at `:736` would catch that, but the decision text still invites it.
  Smallest fix: Two spec-only edits.
  - D-10: append "…and again as the first statement of the inner `except` branch, so a card recorded after an error is also in phase `commit` (EC-10, EC-25; s4-2)".
  - D-22: "A child's error usually arrives as `AgentExecutionError` raised from the original; the three typed errors `BaseAgent` passes through keep their own class (EC-27)…".
  Spec IDs: D-10, D-22, EC-10, EC-25, EC-27, §16 s4-2

R-C4 [Minor] [doc vs spec] `vidbyte/agents/infinite/README.md:120` — the consumer docs say an abort means "without a card", but EC-10 and INV-10 deliver a finish and then an abort for the same key
  Evidence:
  - Three places use the same wording:
    - README `:120`: "`subagent_aborted`: a pair stopped without a card";
    - `events.py:457`: "Announce a pair that stopped without its card";
    - `lib/dataclasses/infinite.py:685`: "a pair that stopped without its card".
  - INV-10 and EC-10 say a sink interrupt during `subagent_finished` gives `subagent_finished` and then `subagent_aborted`. The journal then holds `pair_finished`, as `test_an_interrupt_the_sink_raises_on_an_error_cards_finish_still_aborts_in_the_commit_phase` pins.
  - The package README never mentions EC-10. Only the `events.py:9` header does.
  Failure: A dashboard that trusts the README marks a row as "no card" and drops the card it already received and journaled. This happens only when the developer's own sink raises an interrupt.
  Smallest fix: Docs only. README `:120` becomes "a pair stopped before its card was recorded, or a sink interrupt arrived while its finish was being announced, in which case it follows that pair's `subagent_finished` (derived-events EC-10); …". The two docstrings get "before its card was recorded, or while its finish was being announced".
  Spec IDs: INV-10, EC-10, §12.3 row 12

## VERIFIED CLAIMS

1. **R-2 fix: the two `error_cards_finish` cases pass.** HELD (`2 passed, 19 deselected`). Reverting the line in-process gives `2 failed, 416 passed` at `:736`.
2. **The R-2 fix leaves AC-12's generator phase and R-6's verifier-cancel phase alone.** HELD: both pass in the pack, and a `CancelledError` bypasses `except (VidbyteSdkError, OSError, ValueError)`. It adds no literal and no nesting: `--rule A007` gives 255/255, `--rule S024` gives 25, and both equal `lint/baseline.json`.
3. **EC-25 at run level reads phase `commit`, and `in_flight` drops.** HELD (my probe, both paths).
4. **R-1: EC-30 and EC-31 describe the code's behaviour; EC-31 claims `run_stopped` for a root launch only.** HELD (probes). The nested case also ends in `run_stopped`, after the parent's `subagent_aborted`. The README note and the `launch.py:9` header agree.
5. **R-7: a child's error arrives as a `VidbyteSdkError`, wrapped or one of three typed errors.** HELD (`base.py:965-979`; `issubclass`: Usage `True False`, FailureRaised `True False`, AllModelsFailed `True True`). One leftover site is in D-22 (R-C3).
6. **R-8, R-9, R-10, and R-11 are fixed in text.** HELD:
   - the docstring names all three reasons;
   - the derived citations carry the `derived-events` prefix;
   - the six TESTS lines name the derived files;
   - `spec.md` holds no `AGENT-LINT` except in the §16 row that records the fix.
7. **R-3, R-4, R-6, and R-12: M7, M10, M1, and M11 are each caught.** HELD (in-process mutation):
   - M7 fails `test_in_flight_…`;
   - M1 fails `…verifier_waits…`;
   - M11 fails `[first-commit-fails-from-a-key-error]`;
   - M10 fails the AC-15 test. It also fails the no-sink test, but only because my in-process mutant's code reports itself under a different file name, so that test's check on which module called `descriptions()` fails. That second failure comes from my method, not from the code.
8. **Line budgets 658/456/832, A001 headers end at line 12, and the budget test passes.** HELD.
9. **The tests have not changed since `4f51cef1`, and the lint baseline is untouched.** HELD (both diffs are empty).
10. **Only one executable line of source changed since `c1c3ecc0`.** HELD.
11. **AC-1: the §4 snippet runs as printed.** HELD. The test copy equals the spec's 25 lines, and `exec` of the spec text with my own tree printed `root/p/gen: tool refused (entry_one_line)`, `#1 committed by root/p/ver: …`, and `1 1 0`, with both asserts true.
12. **FR-17: each new kind is called from one site only.** HELD (grep).
13. **INV-8 for the new `verifier_started.files`.** HELD: `files_written` holds the workspace-relative path (`memory.py:104-109`).
14. **The inherited source-stage failure is outside this branch.** HELD: `failure.py` and `harness_threads` have an empty diff, and the test fails the same way locally.
15. **"Each S4 mutation is caught by exactly one test" (test-plan).** HELD for M1, M7, and M11. For M10, see item 7.
16. **The R-13 `[scope-adding]` row stays open and unbuilt.** HELD.
17. **The ID walk.** Since `c1c3ecc0` only `launch.py:311` changed, so S4's walk still holds for every other row. I re-checked the rows that line and the docs edits touch:
    - **No defect found:** INV-3, INV-9, INV-10 (now four exceptions), INV-15, INV-16, INV-19, D-9, D-10's code, EC-10, EC-25, EC-27, EC-30, EC-31, AC-12, AC-13, and FR-11.
    - **Found the defects above:** G-1 and G-3 (R-C1); FR-9's summary pin (R-C2); D-10 and D-22's text (R-C3); the README contract for `subagent_aborted` (R-C4).
    - **The user's weighted words** ("deterministically", "derive these events from the runtime", "dont … change the shape") hold. The repair added one local assignment and nothing that reads a clock or adds a hook. AC-26 passed 3 of 3 runs.

## COMMANDS RUN

- `git log --oneline c1c3ecc0..2e3696f7` → 15 commits, as the briefing lists them.
- `git diff --stat c1c3ecc0 2e3696f7 -- . ':!docs'` → 12 files; the only executable source line is in `launch.py`.
- `git diff --stat origin/main...2e3696f7 -- lint contracts vidbyte/__init__.py vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/middleware vidbyte/pipelines .github pyproject.toml` → empty.
- `git diff --stat 4f51cef1 2e3696f7 -- tests` → empty.
- `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` → `…\worktrees\vidbyte-sdk-infinite-memory-derived-events\vidbyte\__init__.py`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py -q -k "error_cards_finish"` → `2 passed, 19 deselected in 0.98s`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `418 passed in 9.49s`.
- The four `test_infinite_memory_derived_*.py` files, run 3 times → `91 passed` each time.
- `python lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS`.
- `python lint/run.py --rule A007` → `A007 … 255 255 RATCHETED` / `SDK-LINT: PASS`.
- `python lint/run.py --rule S024` → `S024 RATCHETED: 25 known finding(s)` / `SDK-LINT: PASS`.
- `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check` → `contracts/sdk-public-api.json is current at 1332a34e… (vidbyte-sdk 0.4.0, 678 exports).`
- `python -m ruff check <the touched vidbyte files> --config lint/ruff.toml --select I001 --no-cache` → `All checks passed!`
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent/test_infinite_memory_contract.py -q -k budget` → `1 passed, 26 deselected`.
- `PYTHONPATH=$(pwd) python -m pytest tests/features/harness_threads/test_harness_threads_surface.py -k 28_harness_codes` → `1 failed` (inherited); `git diff --stat origin/main...2e3696f7 -- vidbyte/lib/enums/failure.py tests/features/harness_threads` → empty.
- In-process mutation runs. Each heredoc swaps in one method's source and calls `pytest.main` on the pack; no file is written:
  - R-2 revert → `2 failed, 416 passed`;
  - M1 → `1 failed, 417 passed`;
  - M7 → `1 failed, 417 passed`;
  - M10 → `2 failed, 416 passed` (one failure is a method artifact; see VERIFIED CLAIMS 7);
  - M11 → `1 failed, 417 passed`;
  - `verifier_started` `{files}=len(shown)` → `418 passed`;
  - control `len(shown)+1000` → `2 failed, 416 passed`.
- Heredoc probes through `ScriptedTree`, with temporary workspaces under the session scratchpad that are removed on exit:
  - EC-25 normal path and generator-error path;
  - EC-30;
  - EC-31 root and nested;
  - the §4 snippet `exec`'d from `spec.md`.
  Outputs are quoted above.
- `python - <<EOF` comparing the spec's §4 snippet with the AC-1 test copy → `25 25 True`.
- `git status --porcelain` after every run → empty. The only file I wrote is this report.
- The full `run_ci.py --stage source` and `--stage package` were not re-run. The orchestrator ran both at `c2a446b6`, after the R-2 fix landed, and the only later commit (`2e3696f7`) touches only `pipeline.md`. I relied on its results: `1 failed (inherited), 7037 passed, 17 skipped`, and `CI passed.`
