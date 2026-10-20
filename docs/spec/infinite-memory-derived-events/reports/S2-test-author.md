# S2 test author report: infinite-memory-derived-events

**Status:** DONE.
- **Commits:** the failing tests and `test-plan.md` are `de91f1bc`. The spec's §6.2 Proof column is `91b1a388`. This report is the third commit.
- **Base:** S2 started at `33cfda07`, which is spec r3 approved, with the base at `181f1992`.
- **Edits:** I changed only the test pack, `test-plan.md`, the Proof column of spec §6.2, and this report. No production code, `lint/`, `scripts/`, `contracts/`, `request.md`, or `pipeline.md` was touched.
- **Session:** the session was interrupted once before any commit. On resume, `git diff` showed the earlier edits intact. Each was re-checked against the authorized list (§5 below) and kept.

## 1. What I read

- **Pipeline inputs:**
  - `spec.md` r3 (all of it, §13 most closely);
  - `request.md`;
  - `context/code-map.md`;
  - `pipeline.md`;
  - `reports/S0-scout.md`, `S1-*.md`.
- **The test pack:** every file in `tests/features/infinite_memory_agent/` that this spec touches, plus the README and FEATURE.md.
- **Production code, read-only:**
  - `vidbyte/agents/infinite/*.py`, `vidbyte/lib/{enums,dataclasses,constants}/infinite.py`, and the prompt catalog leaves the refusal oracles use;
  - the loop's denial path (`AgentRuntime._denied_tool_result`), read to bind names and ground expectations.
- **Probes:** 27 throwaway scripts (`exp*.py`) in the session scratchpad, run against HEAD to confirm runtime facts before pinning them. Examples:
  - the AC-17 iteration and level table;
  - the 102-file map cut;
  - EC-1's stream at HEAD;
  - the wide script's 10 root tool iterations;
  - that a 602-character pair key goes through the journal and `subagent_launched` unchanged.

## 2. Inventory

| File | Status | Items | What it proves |
|---|---|---|---|
| `test_infinite_memory_derived_pairs.py` | new | 17 | AC-3, AC-4, AC-5, AC-9 to AC-14; FR-9 and FR-10 verifier events; INV-3 (identity, and the one replacement case); INV-16 `in_flight`; EC-10; EC-24 abort key |
| `test_infinite_memory_derived_refusals.py` | new | 41 | AC-6 (32 cases, one per raise site, plus a completeness check); AC-7; AC-8; EC-1; EC-8; EC-9 with `InfiniteLaunchTool.denials`; EC-19; `_rule` (15 inputs); `batch_rejected` sources |
| `test_infinite_memory_derived_run.py` | new | 18 | AC-1 snippet; AC-15 to AC-22; AC-26; EC-12; EC-14 (unfinished run); EC-18; NFR-5 scan bound |
| `test_infinite_memory_derived_records.py` | new | 11 | AC-23 to AC-25 (enums, method parameters, record fields and rules); §8.5 seams; §9.2 and §9.3 constants; `journal.started`; `map_omitted` |
| `test_infinite_memory_events_{stream,pairs,lifecycle,records}.py`, `test_infinite_memory_handoff.py`, `test_infinite_memory_contract.py` | updated | 33 red, budget green | The PR #1159 pins this spec changes (§5) |
| `infinite_events_fixtures.py`, `infinite_memory_fixtures.py` | updated | | Fixtures (§4) |
| `README.md`, `FEATURE.md` (pack) | updated | | File Index (S020), Logs, the derived-events failure modes, Test Suite Map, omitted strategies, and the AC-36 line now reversed |

`test-plan.md` maps every AC, INV, EC, FR, and NFR to its tests, with the failure each catches and why it cannot pass vacuously.

## 3. What was pruned

- **A separate INV-1 test** with an `_Untouchable` workspace stand-in. It duplicated AC-20, which counts record constructions and attributes scans with a positive-control run on real objects. Removed.
- **Dead helpers and aliases** left from drafting: `_ = Sequence`, and an `events as journal_events` import alias. Removed; ruff F401 and SIM117 were fixed.
- **Tests not written,** each with its reason in the test-plan:
  - EC-3, EC-4, EC-7, EC-11, EC-15, EC-17, EC-23, EC-25, EC-28;
  - the other-process half of EC-14;
  - INV-20 (a diff property for S4);
  - NFR-7 (a gate run);
  - the out-of-scope kinds C1, C2, E2, and pair-agent progress.

  None of these is an AC. Each is an accepted limitation, needs a seam the spec does not name, or is non-behavioural.
- **Late additions** found while auditing coverage before the commit, kept because each is deterministic and cheap:
  - EC-1 (a failed generator's denials stay silent);
  - EC-14 (`handoff_written` for an unfinished run);
  - INV-3's exception (a sink's `KeyboardInterrupt` on `subagent_aborted` replaces the error);
  - EC-24 (an aborted pair's long key);
  - the NFR-5 bound inside AC-20.

## 4. Fixtures added

- **`infinite_memory_fixtures.py`:**
  - `ToolsStep` and `tool_calls(*calls)`: one model turn that asks for several tool calls, in order.
  - AC-8 needs a denial and an accepted finish in one turn, and EC-8 needs three launches in one iteration. No existing step could script either.
  - Existing steps are unchanged.
- **`infinite_events_fixtures.py`:**
  - `AC2_KINDS` now has 11 kinds.
  - `AC7_LIMITS = {"max_parallel": 2, "max_depth": 1}` is new.
  - `ac7_tree()` is the spec's AC-7 script. It is shared by the refusals test, the updated AC-36 test, and AC-21's `[ac7]` case.
- **In-file builders** (private to their module):
  - `_flaky_commit`: the §13 seam that wraps `InfiniteWorkspace.commit_entry` on the class and fails the n-th call;
  - `_cancel_while_alpha_waits`;
  - `_quota` and `_problem`: parse the quota line and the refusal problem out of the text the model read, using the catalog templates;
  - `_denial` and `_context`: `ToolCallContext` records shaped like `AgentRuntime._denied_tool_result`'s;
  - `_wide_tree`: the one script that reaches 19 of the 22 kinds;
  - `_omitted`, `_normalized`, `_counting`, and `_attributed`.

## 5. Existing tests updated (spec-mandated)

The full file:line, old → new, and spec ID table is in `test-plan.md` § "Existing tests updated (spec-mandated)". In summary:

- **Kinds lists** only gain the new kinds; the old kinds keep their order:
  - lifecycle :88 and :102;
  - pairs :128-137, :178, :328, :479, and :560;
  - stream `AC2_KINDS` and :493.
- **Records tables:**
  - `_FIGURES`: 8 records re-measured and 8 added;
  - `_RECORD_OF_KIND`, `_FIELDS`, and `_COST_RECORDS`;
  - the `_worst` shapes;
  - the :488 call now takes 5 arguments.
- **NFR-2** (stream :419 and :436) now pins 22 methods. The existing equality with the enum is kept.
- **Handoff :248** includes `"rule": InfiniteRefusalRule.MALFORMED_MEMORY` (R-14).
- **Budget caps** are now 470, 870, and 660. That test stays green.
- **Two renames:**
  - `…delivers_seven_events…` → `…delivers_eleven_events…`;
  - `test_middleware_denials_deliver_no_event_and_the_run_still_finishes` → `…deliver_one_batch_rejected_each…`.

No assertion was weakened, and nothing was skipped, marked xfail, or deleted.

## 6. Red run (exact output)

The commands are run from the repository root in Git Bash, at `de91f1bc`.

```
$ PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider --tb=line
120 failed, 294 passed in 7.72s

$ PYTHONPATH=$(pwd) python -m pytest --collect-only -q -p no:cacheprovider
7051 tests collected in 2.12s

$ PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=no -rf
121 failed, 6913 passed, 17 skipped in 211.99s (0:03:31)

$ python lint/run.py
SDK-LINT: PASS
```

**Failures by file (full suite):**

```
     17 test_infinite_memory_derived_pairs.py
     41 test_infinite_memory_derived_refusals.py
     18 test_infinite_memory_derived_run.py
     11 test_infinite_memory_derived_records.py
     22 test_infinite_memory_events_records.py
      5 test_infinite_memory_events_pairs.py
      4 test_infinite_memory_events_stream.py
      1 test_infinite_memory_events_lifecycle.py
      1 test_infinite_memory_handoff.py
      1 tests/features/harness_threads/test_harness_threads_surface.py   (pre-existing, unrelated)
```

**The first failing line of each red item, grouped** (all for a missing spec name or event):

```
 35  derived_refusals  ImportError: cannot import name 'InfiniteRefusalRule'   (the 32 AC-6 cases fail here, after their kinds, agent, problem, and summary checks passed at HEAD)
  5  derived_pairs     ImportError: cannot import name 'InfinitePairPhase'
  1  handoff           ImportError: cannot import name 'InfiniteRefusalRule'
  8  events_records    ValueError: '<new kind>' is not a valid InfiniteEventKind
 11  events_records    TypeError: Infinite*Details.__init__() got an unexpected keyword argument '<new field>'
  2  events_records + derived_pairs  TypeError: InfiniteEvents.subagent_launched() takes 3 positional arguments but 6 were given
 17  derived_*, events_records  AttributeError: a new record, enum, field, or seam (…CommittedDetails, InfiniteRefusalRule, entries_left, error_type, iterations, events_failed, started, map_omitted, denials, _rule, MEMORY_COMMITTED)
  1  derived_records   AssertionError: INFINITE_EVENT_PROGRESS_ITERATIONS = '<missing>', expected 10
 40  all               AssertionError on a kinds list or an event that never arrives (for example "expected one verifier_started event, got 0", "assert [] == ['handoff_written']", "assert [] == [(2, 50), (5, 75), …]")
```

The output was identical over three pack runs once memory addresses and run ids were masked, so the red is deterministic.

The `harness_threads` failure is `assert len(main_members) == 120` (it finds 171). That test reads `FailureCode` at `git merge-base HEAD main`, and this checkout's local `main` has moved. This change touches neither that test nor anything it reads (`git diff --name-only 33cfda07` lists only the pack and `docs/spec/infinite-memory-derived-events/`).

`lint/run.py` reports S020 (README File Index parity) until the new files are tracked; after `git add`, it is back to its baseline of 1. Ruff on the pack shows only the I001 (long in-function imports) pattern the existing files already have. The three updated PR #1159 files have the same ruff findings as at HEAD under the repo's config.

## 7. Spec defects and gaps

1. **`verifier_started` summary `{files}` is ambiguous.** It could mean the notes written or the notes shown. The test accepts both, and the spec owner should settle it.
2. **INV-8 and AC-6 conflict on the disk refusal.** The `OSError` text the model reads names an absolute path built from the SDK's workspace path. AC-6 keeps that text; INV-8 forbids SDK-built absolute paths on events. The test follows AC-6.
3. **§13 misses pins this spec changes:**
   - pairs :128-137 (replay list; §13 cites :106, which does not change);
   - stream :188 and :194 (AC-2 envelopes and summaries);
   - stream :493 (quiet-tools list; §13 cites it only for "no heartbeat");
   - stream :388 (follows `AC2_KINDS`).

   §13 also does not mention that the AC-2 and AC-36 tests must be renamed, because their names state "seven events" and "no event". Separately, these §13 citations need no change: lifecycle :155, :182, :193, :209; pairs :106, :291, :458; handoff :339-372.
4. **AC-8 and EC-8 need several tool calls in one turn,** which the pack's fixtures could not script. `tool_calls` was added. §13's fixture list does not mention this need.
5. **The AC-13 seam is the only path to `subagent_aborted(failed)`.** The implementation must call `workspace.commit_entry` through the instance so the class-level wrapper is seen. Likewise, AC-20 needs `usage()` and `descriptions()` called directly from `events.py`, and `map_omitted` looked up at call time.

## 8. Commands run that changed state

- `git add` and `git commit`, three times, each with the Co-Authored-By trailer.
- No `pip install`, `git stash`, push, or worktree command was used.
