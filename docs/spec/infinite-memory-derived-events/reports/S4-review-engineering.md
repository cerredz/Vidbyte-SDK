LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — on every path the spec lists, the code behaves correctly, but one reachable journal-write failure breaks INV-10 and leaves `in_flight` too high for the rest of the session, and the test pack lets 4 of 20 plausible regressions through, 3 of them in P0 fields.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- `in_flight` accounting on the listed paths. A launch counts once even when the sink raises (events.py:333). A finish counts once even when the sink raises on it (events.py:421; probe P2 reads b=1 with events_failed 2). An abort after a journaled finish does not count again (EC-10, events.py:463). An abort without a journaled finish does count (EC-25; probe P4 reads b=1). The count is floored at 0. Mutations M4, M15, M36 and M40 are each killed. Do not move these lines inside the shield or after `_deliver`.
- The root-denial dedupe uses one high-water mark over an append-only list (runtime.py:157-164). `state.call_contexts` only ever grows (vidbyte/agents/runtime.py:1814, :1911), and `metadata["tool_calls"]` is `tuple(contexts)` (:2125), so the hook and the post-loop catch-up cannot announce one call twice. M2 and M3 are both killed. Keep the single index. Do not switch to a set of call ids.
- The events only observe. `vidbyte/agents/{runtime,base}.py`, `vidbyte/middleware`, and `vidbyte/pipelines` have an empty diff. Each public method returns before building anything when `on_event is None` (AC-20). A sink that raises on every kind leaves the reply, journal, disk, and model calls byte-identical (AC-22). `_level` is stored before delivery (events.py:266-271; M6 is killed).
- Input the model controls is parsed defensively. `map_omitted` returns 0 for a 5000-digit count, for superscript digits, for a missing count, and for an empty map, and it returns 12 for a well-formed header. All 28 workspace raise sites keep their messages byte-identical and only add the `details` rule.

FINDINGS (ranked, most severe first, max 15)
R-E1 [Major] [error handling] vidbyte/agents/infinite/launch.py:160-163 — A journal start write that fails mid-batch leaves the batch's earlier pairs launched but never closed, and `in_flight` stays raised for the rest of the session
  Evidence: `for task, key in zip(cards, keys, strict=True): if key in pairs: self.journal.pair_started(key); self.events.subagent_launched(self, task, batch, tuple(pairs).index(key), len(pairs))`. Probe P6 patches `InfiniteRunJournal.pair_started` to raise `OSError("disk full")` for pair b of a two-pair batch [a, b], and a later batch launches c. Output: `P6 kinds: ['run_started', 'subagent_launched', 'subagent_launched', 'generator_finished', 'verifier_started', 'verifier_finished', 'subagent_finished', 'batch_finished', 'run_finished']`, `P6 launched in_flight: [('a', 1), ('c', 2)]`, `P6 closed: [('subagent_finished', 'c')]`.
  Failure: A disk-full or file-lock `OSError` on b's `pair_started` append escapes `execute` before `ParallelPipeline` starts. EC-25 already treats journal append failures as realistic. The root loop turns the error into a tool error and the run goes on. Pair a was announced as launched but never runs, and it never gets `subagent_finished` or `subagent_aborted`. INV-10 lists only two exceptions, EC-4 and EC-10, and this case is neither. Every later `subagent_launched` and `subagent_finished` overstates "running now" by 1: c reports 2 while it is the only pair running. On main the orphan `subagent_launched` already happened, but `in_flight` and INV-10 are new in this PR.
  Smallest fix: Split the loop in two. The first pass writes `journal.pair_started(key)` for every new pair. The second pass announces `subagent_launched` and `subagent_replayed` in task order, which keeps the `launches-are-announced-in-task-order` order. The comment "a new pair right after its started record" needs rewording to match. If the authors want no code change, add this case to INV-10 as a third listed exception and give it an EC row.
  Spec IDs: INV-10, D-9 ("the only source of 'running now'"), FR-5

R-E2 [Major] [test quality] tests/features/infinite_memory_agent/test_infinite_memory_derived_run.py:264 (vs vidbyte/agents/infinite/events.py:221) — The AC-15 test cannot tell this run's notes from another run's, so the test plan claims a catch it does not make
  Evidence: test-plan.md:56 says the AC-15 test catches "`files` counting another run's notes". The test runs once on a fresh `tmp_path` and filters `record["run"] == run_id` (:295) over a `files.jsonl` that holds only this run's records. Mutation M10 replaces `len(workspace.descriptions(journal.run_id))` with `len(workspace.descriptions())` and leaves the pack at `414 passed in 12.04s`. Probe P3 runs twice on one workspace, one note each. Unmutated it gives `[1, 1]`; under M10 it gives `[1, 2]`.
  Failure: If anyone drops the run filter, `run_finished.files` on any reused workspace counts every earlier run's notes, and nothing in the pack fails. R-9 settled this choice explicitly.
  Smallest fix: In the AC-15 test, or in a new two-run variant, seed `files.jsonl` with one record under another run id before the run, or run a first run on the same workspace. Keep the assertion `files == 2`.
  Spec IDs: AC-15, D-16, EC-16, FR-6

R-E3 [Major] [test quality] vidbyte/agents/infinite/launch.py:288 — No test ever observes `subagent_aborted` with phase `verifier` from a real run, so losing the VERIFIER phase assignment passes the whole pack
  Evidence: `phase, last = InfinitePairPhase.VERIFIER, checker`. Mutation M1 rewrites it to `last = checker` and leaves the pack at `414 passed in 11.25s`. Probe P1 cancels while the verifier waits. Unmutated: `P1 abort: [('verifier', 1, 'cancelled')]`. Under M1: `P1 abort: [('generator', 1, 'cancelled')]`, delivered after `verifier_started`. The only `VERIFIER` phases in the pack are passed by hand to `subagent_aborted` in the component test (test_infinite_memory_derived_pairs.py:592-644). AC-12 (:427) covers phase `generator` only, and EC-10 and AC-13 cover `commit` only.
  Failure: If a refactor of `run` drops or moves the VERIFIER assignment, every abort during verification is reported as `generator`. A dashboard then puts the failure on the wrong agent, and no test fails.
  Smallest fix: Add one run-level case: probe P1's script, with a `Signal` held in the verifier's model call, then cancel. Assert one `subagent_aborted` with `phase == VERIFIER`, `staged == 1`, reason `cancelled`, and that it comes after `verifier_started`. This can be a second parameter of the AC-12 test.
  Spec IDs: D-10, FR-11, INV-15

R-E4 [Major] [test quality] vidbyte/agents/infinite/events.py:419-421 — R-17 says a sink that raises cannot skip the `in_flight` decrement on `subagent_finished`, and no test checks it
  Evidence: The `# The pair leaves the count before anything that can fail, so a sink that raises on this event cannot keep it counted.` comment is followed by `self._in_flight = max(self._in_flight - 1, INFINITE_MIN_COUNT)` and then `with self._shielded(InfiniteEventKind.SUBAGENT_FINISHED):`. Mutation M7 moves the decrement after `_deliver` and keeps the reported value the same. The pack stays at `414 passed in 13.41s`. Its twin M40, the same move for the increment in `subagent_launched`, is killed by test_in_flight_counts_each_pair_once_and_never_goes_below_zero. Probe P2 has a sink that raises `ValueError` on `subagent_finished` and launches a, then b. Unmutated: `[('a', 1), ('b', 1)]`. Under M7: `[('a', 1), ('b', 2)]`.
  Failure: Implementer deviation 1 already moved these lines once to satisfy the A007 baseline, so a later move is plausible. If the decrement moves after delivery, each finish under a flaky sink leaks one count for the session, and the test docstring that cites R-17 still passes.
  Smallest fix: In the in_flight component test, make the sink at :608 also raise on a's `subagent_finished`, which is called at :625. The existing assertion that d's launch reads 2 still holds today and reads 3 under M7. Alternatively, add P2 as a run-level assertion.
  Spec IDs: D-9, INV-16, AC-22

R-E5 [Minor] [test quality] vidbyte/agents/infinite/events.py:471 — D-22's cause rule on `subagent_aborted.error_type` is untested
  Evidence: `error_type = type(error.__cause__ or error).__name__`. Mutation M11 changes it to `type(error).__name__` and leaves the pack at `414 passed in 13.28s`. Every abort in the pack raises an error without a `__cause__` (`RuntimeError`, `OSError`, `KeyboardInterrupt`, `CancelledError`).
  Failure: Code the pair runs itself raises `raise RuntimeError(...) from KeyError(...)` in its commit step. The abort should name `KeyError`, as the review text does under `_error_text`. Under M11 it names `RuntimeError`, and nothing fails.
  Smallest fix: Add a chained-error case to the AC-13 parametrization: a `_flaky_commit` that raises `RuntimeError` from `KeyError`, asserting `error_type == "KeyError"`.
  Spec IDs: D-22, FR-11

R-E6 [Minor] [failure modes] vidbyte/agents/infinite/launch.py:163 (spec INV-10) — A `BaseException` the sink raises on `subagent_launched` is a third INV-10 exception that the spec does not list
  Evidence: Probe P5 has a sink that raises `KeyboardInterrupt` on the second `subagent_launched` of an [a, b] batch. Output: `P5 kinds: ['run_started', 'subagent_launched', 'subagent_launched', 'run_stopped']`. Neither pair gets `subagent_finished` or `subagent_aborted`.
  Failure: Neither pair is ever closed. The interrupt escapes `execute` before any pair task exists, and the run ends with `run_stopped`. EC-26 already tells consumers to close open rows on `run_stopped`, so no reader is misled for long. The gap is in the invariant text, not in the behaviour.
  Smallest fix: Doc-only. Add the case to INV-10's exception list, or extend INV-3's sink-interrupt sentence: "a sink interrupt on `subagent_launched` stops the batch before its pairs start; they get neither event, and `run_stopped` follows".
  Spec IDs: INV-10, INV-3

VERIFIED CLAIMS:
- The pack passes at c1c3ecc0, which is the same code as HEAD 6185889b (only pipeline.md differs): 414 passed. HELD.
- Nothing is changed in `vidbyte/agents/runtime.py`, `vidbyte/agents/base.py`, `vidbyte/middleware`, or `vidbyte/pipelines`: the diff stat is empty. HELD.
- The 28 workspace raise sites keep their messages byte-identical and only add the details rule: 30 of 30 changed lines matched, and the 2 mismatches are header docstrings. HELD.
- The root denial high-water mark cannot announce a call twice, and the catch-up covers the last turn. `call_contexts` is append-only, `tool_calls` is `tuple(contexts)`, and M2 and M3 are killed. HELD.
- EC-25: an abort with no journaled finish decrements `in_flight` (P4: b reads 1; M15 and M36 killed). HELD.
- EC-10: an abort after a journaled finish does not decrement again (M4 killed by the in_flight test; the :647 test passes). HELD.
- The decrement survives a sink that raises on `subagent_finished` (P2 reads b=1 and events_failed 2). HELD in code, UNTESTED (R-E4).
- Cancelling during the verifier aborts with phase `verifier` and staged 1 (P1). HELD in code, UNTESTED (R-E3).
- `run_finished.files` counts this run's notes only (P3 gives [1, 1]). HELD in code. The test-plan claim that AC-15 catches the cross-run bug FAILED (R-E2).
- INV-10 has exactly two exceptions (EC-4, EC-10). FAILED: P6 is reachable through an `Exception` (R-E1), and P5 through a sink interrupt (R-E6).
- The batch offset is read before the batch's own starts (M23 killed by 3 tests), and `batch_finished` verdicts count every pair (M39 killed). HELD.
- The outer handler catches `BaseException` and not `Exception` (M26 killed by 3 tests), and generator denials come before `generator_finished` (M37 killed). HELD.
- `workspace_usage` fires on (level, cut) with `>=` thresholds (M13 and M28 killed), and the handoff section cut test checks both caps (M38 killed). HELD.
- `map_omitted` on hostile headers returns 0 for 5000 digits, `²³`, an empty map, and a missing count, and 12 for "… and 12 more files". HELD.
- Mutation score: 20 mutations, 16 killed, 4 survived (M1, M7, M10, M11).

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider` → `414 passed in 10.68s`
- `git diff --stat origin/main...c1c3ecc0 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/middleware vidbyte/pipelines | wc -l` → `0`
- `git diff --stat c1c3ecc0 HEAD` → `docs/spec/infinite-memory-derived-events/pipeline.md | 8 +++++---` (1 file)
- Raise-message diff check (workspace.py old vs new raise lines) → `30 30 … mismatches 2` (both header docstrings)
- Sandbox baseline (copy outside the worktree) → `414 passed in 11.93s`
- `python <scratchpad>/s4-engineering/mutate.py "<scratchpad>/s4-engineering/mut"` → M1 `414 passed`; M2 `1 failed`; M3 `4 failed`; M4 `1 failed`; M5 `1 failed`; M6 `1 failed`; M7 `414 passed`; M8 `1 failed`; M10 `414 passed`; M11 `414 passed`; M13 `1 failed`; M15 `1 failed`; M23 `3 failed`; M26 `3 failed`; M28 `1 failed`; M36 `1 failed`; M37 `4 failed`; M38 `1 failed`; M39 `2 failed`; M40 `1 failed`
- `PYTHONPATH=<worktree> python <scratchpad>/s4-engineering/probes.py` → `P1 abort: [('verifier', 1, 'cancelled')]`; `P2 launched in_flight: [('a', 1), ('b', 1)] events_failed: 2`; `P3 run_finished.files per run: [1, 1]`; `P4 launched in_flight: [('a', 1), ('b', 1)]`, `P4 abort: [('a', 'commit', 'OSError')]`; `P5 kinds: ['run_started', 'subagent_launched', 'subagent_launched', 'run_stopped']`
- `python <scratchpad>/s4-engineering/mutprobe.py M7 p2` → `P2 launched in_flight: [('a', 1), ('b', 2)] events_failed: 2`; `M10 p3` → `[1, 2]`; `M1 p1` → `P1 abort: [('generator', 1, 'cancelled')]`; `M11 p4` → `[('a', 'commit', 'OSError')]` (no cause, so this probe does not separate M11)
- `PYTHONPATH=<worktree> python <scratchpad>/s4-engineering/probe6.py` → `P6 launched in_flight: [('a', 1), ('c', 2)]`, `P6 closed: [('subagent_finished', 'c')]`
- `map_omitted` probe → `0 12 0 0 0`
- `git status --short` (worktree) → only `?? docs/spec/infinite-memory-derived-events/reports/S4-review-conformance.md` (another reviewer's report) before this file was written
- `<scratchpad>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/452d7a62-18aa-47aa-9d05-a78769228dbf/scratchpad`
