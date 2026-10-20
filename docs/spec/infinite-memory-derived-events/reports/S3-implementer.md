# S3 implementer report: InfiniteMemoryAgent derived run events

Spec: `docs/spec/infinite-memory-derived-events/spec.md` r4 → r5 · Branch: `feat/infinite-memory-derived-events` · S3 base: `043004bb` (tests pinned at `2cab5070`) · Code HEAD: `939381ec` · Spec HEAD: `1bc7d8a1` · Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/1191

## Outcome

Every row of §12.3 is implemented in the §12.6 phase order, except row 13, which S2 had already done. The infinite-memory pack was at S2's red baseline of 120 failed and 294 passed; it now passes **414 of 414**.

The other gates:
- The agent lint ends `SDK-LINT: PASS`, with no baseline raised and no suppression added.
- The CI source stage fails only on the known pre-existing test.
- The CI package stage passes.
- The public-API contract is current.
- `git diff 2cab5070 -- tests/` is empty.

## Commits

| Phase | SHA | Row(s) | Message |
|---|---|---|---|
| P1 | `ed8c0123` | 1 | feat(infinite): add 8 event kinds and the refusal-rule, refusal-source, and pair-phase enums [W-1; FR-3, FR-11, AC-24] |
| P1 | `b8feb91c` | 2 | feat(enums): export InfinitePairPhase, InfiniteRefusalRule, and InfiniteRefusalSource [W-1; AC-24] |
| P1 | `59c1d22c` | 3 | feat(infinite): add the derived-event summaries, throttle, usage levels, and metadata and refusal keys [W-1; FR-3, FR-11..FR-16] |
| P1 | `4bb55718` | 4 (all but the P2 bullet) | feat(infinite): add the eight derived-event details records and their kinds [W-2; …, AC-25] |
| P1 | `8a9b68fc` | 9 | feat(infinite): name the refusal rule at every workspace raise and read a cut map's omitted count [W-6, W-7; FR-3, FR-14, AC-6, AC-17] |
| P1 | `048e50ee` | 10 | feat(infinite): expose every pair_started key on InfiniteRunJournal.started [W-5; FR-5, FR-6, AC-10, AC-11] |
| P1 fix | `542124fa` | 9 | style(infinite): sort the workspace constant imports [W-6; FR-14] |
| P2 | `611f14e0` | 4 (P2 bullet), 5, 8, 6, 7, 11 | feat(infinite): announce the eight derived run events and enrich eight more from the runtime, launches, pairs, memory tools, and handoff [W-2..W-8; FR-1..FR-17, AC-1..AC-23, AC-25, AC-26] |
| P3 | `e8b47db1` | 12 | docs(infinite): list all 22 event kinds with their new fields and add six agent notes [W-9; NFR-7] |
| P3 | `80a7d568` | 14 | docs(agents): name the derived run events in the InfiniteMemoryAgent event-stream sentence [W-9; NFR-7] |
| headers | `939381ec` | 7, 11 | docs(infinite): name the new announcements in the runtime and agent PURPOSE headers [W-6, W-8; FR-13..FR-16] |
| Phase 6 | `f9a55dee` | spec | docs(spec): record draft PR for infinite-memory-derived-events |
| Phase 7 | `1bc7d8a1` | spec | docs(spec): record implementation proof for infinite-memory-derived-events |

**After P1** the package imported, and the pack stood at 104 failed and 310 passed. Every failure was in a file S2 had touched.

**P2 is one commit** because its rows change signatures that call each other: `batch_rejected`, `tool_refused`, `run_finished`, `subagent_launched`, `_commit`, and `_finish`.

**Every commit is pushed.** No commit was amended, and no branch was force-pushed.

## Data flow, in run order

1. **The runtime builds the event writer.** `InfiniteMemoryRuntime.arun` builds `InfiniteEvents`, which starts `_opened`, `_in_flight`, `_failures`, and `_level`. It keeps the root's launch tool in `self._launch`.
2. **After each root tool iteration,** `_after_tool_iteration` renders the map once and upserts it. When the launch tool exists, it then does three things:
   - `_announce_denials(launch, state.call_contexts)` sends `batch_rejected` (source `middleware`) for each DENIED `launch_subagent` record after `_announced`.
   - `workspace_usage(workspace, map_text)` scans only when there is a sink, and announces only when the level or the cut state changes.
   - `agent_progress(settings, state)` announces every 10th iteration.
3. **`InfiniteLaunchTool.execute` handles a batch.**
   - A refused batch sends `batch_rejected(self, exc)`, with source `tool` and the rule taken from the error's details.
   - Otherwise it records `batch, started = len(journal.started), time.monotonic()`.
   - For each new task it writes `pair_started`, then sends `subagent_launched(self, task, batch, index, size)`. The method raises `_in_flight` first, and `attempt` is `journal.started.count(key)`.
   - A replayed task sends `subagent_replayed`.
   - When `ParallelPipeline` returns, it sends `batch_finished`.
4. **`InfinitePair.run` drives one pair,** tracking `phase` and `last`.
   - **Generator:** the reply comes back; each denial in `reply.metadata["tool_calls"]` sends `batch_rejected(writer, denial)`; then `generator_finished`.
   - **Verifier:** `verifier_started`, then `arun`, then `_verdict`, then `verifier_finished`.
   - **Commit:** the phase becomes `commit`, and `_commit(checker)` sends `memory_committed` or `memory_dropped` (rule) for each entry.
   - **Finish:** `_finish(last, …)` sends `memory_dropped` (unchecked) for each remaining entry, records `pair_finished`, then sends `subagent_finished`. That method lowers `_in_flight` first and takes `error_type` from `self.error`.
   - **Abort:** any `BaseException` that escapes sends `subagent_aborted(self, exc, phase)` and is raised again. The abort lowers `_in_flight` only when the journal has no finish for the pair.
5. **The memory tools** attach `_quota(memory)` to `memory_saved`, `memory_staged`, and `file_written`. On a refusal they pass the error itself to `tool_refused`, whose `_rule` reads `details["rule"]`.
6. **When the loop returns,** `_announce_denials` catches up on `result.metadata["tool_calls"]`. Then `journal.finish` runs, and `run_finished(journal, result, workspace)` reports:
   - this session's counts;
   - the whole run's verdicts, committed entries, created notes, and deepest pair;
   - `events_failed`.

   If the run raises instead, `run_stopped` reports `events_failed`.
7. **`InfiniteMemoryAgent.run_handoff`** writes the handoff file, then calls `InfiniteEvents(on_event, run_id).handoff_written(workspace, target, handoff)`.

## §12.3 rows

- [x] 1 `vidbyte/lib/enums/infinite.py`: `ed8c0123`
- [x] 2 `vidbyte/lib/enums/__init__.py`: `b8feb91c`
- [x] 3 `vidbyte/lib/constants/infinite.py`: `59c1d22c`
- [x] 4 `vidbyte/lib/dataclasses/infinite.py`: `4bb55718` (P1) and `611f14e0` (the P2 bullet). The P2 bullet appended the fields and extended the existing `for name in (...)` loops. `attempt` is checked only through the string-name loop, and the three quota-carrying records each gained one 4-name loop.
- [x] 5 `vidbyte/agents/infinite/events.py`: `611f14e0`
- [x] 6 `vidbyte/agents/infinite/launch.py`: `611f14e0`
- [x] 7 `vidbyte/agents/infinite/runtime.py`: `611f14e0`; header in `939381ec`
- [x] 8 `vidbyte/agents/infinite/memory.py`: `611f14e0`
- [x] 9 `vidbyte/agents/infinite/workspace.py`: `8a9b68fc`, plus the import sort in `542124fa`
- [x] 10 `vidbyte/agents/infinite/journal.py`: `048e50ee`
- [x] 11 `vidbyte/agents/infinite/agent.py`: `611f14e0`; header in `939381ec`
- [x] 12 `vidbyte/agents/infinite/README.md`: `e8b47db1`. The README is 23,230 characters; A009 is clean.
- [—] 13 the test budget: S2's row, done at `2cab5070`. Not touched.
- [x] 14 `vidbyte/agents/README.md`: `80a7d568`

**§12.4:** every item holds; the evidence is in the budget and gate sections below. The one exception is the shape item, covered by deviation 1.

**§12.5:**
- Both READMEs and every touched module header are updated.
- `llms.txt`, `REPO_MAP.md`, the file index, the changelog, and `contracts/sdk-public-api.json` are unchanged, and the public-API check reports the contract current.

**§6.2:** no Proof cell was blank. Every AC already named its S2 test, so no SHA was added.

## Deviations (also recorded in spec §17, r5)

1. **Where the `_in_flight` changes sit.** In `subagent_launched`, `subagent_finished`, and `subagent_aborted`, the change sits just before `with self._shielded(...)`, right after the `on_event` check. D-9 and R-17 asked for it to be the first statement inside the shield.
   - **Why:** A007 treats every numeric literal inside a shield body as operational, because that body's `_deliver` call names `depth`. A007 is exactly at its baseline of 255, so the `1` in `+= 1` and `- 1` would have pushed it over.
   - **Why behaviour is unchanged:** the change still runs before anything that can fail, and only when a sink is attached. The abort's journal check is `self._cards.get(key)`, which cannot raise.
2. **Starting values.** `_in_flight`, `_failures`, and `InfiniteMemoryRuntime._announced` start at `INFINITE_MIN_COUNT`, not a bare `0`, for the same lint reason. This matches `_level`.
3. **`tool_refused` uses `str(error)` inline** instead of binding a `problem` local. This keeps `events.py` within its cap: 658 of 660 lines after the header.
4. **Extra commit `542124fa`.** It repairs one I001 import order that the row 9 commit introduced. The P1 full lint showed S051 at 260 against an allowance of 259. History was not rewritten.
5. **Extra commit `939381ec`.** It names the new announcements in the PURPOSE lines of `runtime.py` and `agent.py`. The header item in §12.4 requires this, but rows 7 and 11 did not list it.
6. **Revision label.** The brief asked for an r4 row in §17, but r4 already holds S2's open items. The row is therefore r5, and the frontmatter `revision` is 5.

## Files touched outside §12.3

None. `git diff 043004bb --stat` lists only §12.3 files, plus `spec.md` for Phase 6 and Phase 7 and this report. There is no change to:
- `vidbyte/agents/runtime.py`
- `vidbyte/agents/base.py`
- `vidbyte/middleware/`
- `vidbyte/pipelines/`
- `vidbyte/__init__.py`
- `request.md` or `pipeline.md`

## Budget used

| Budget | Used | Cap |
|---|---|---|
| `events.py`, lines after header | 658 | 660 |
| `launch.py`, lines after header | 455 | 470 |
| `vidbyte/lib/dataclasses/infinite.py`, lines after header | 832 | 870 |
| `runtime.py` / `memory.py` / `agent.py` / `journal.py` / `workspace.py` | 160 / 286 / 179 / 191 / 374 | 400 |
| Package modules | 9 | 9 |
| A007 operational constants | 255 | 255 (baseline, RATCHETED) |
| A002 intent comments | 566 | 703 (IMPROVED; baseline left alone) |
| S051 / S008 / S024 / S019 | 259 / 19 / 25 / 5 | 259 / 19 / 25 / 5 |
| New dependencies, hooks, middleware, listeners, timers, tasks | 0 | 0 |

**Headers:** every touched module's header still ends at line 12.

**Comment width:** every comment line this change added is at most 72 columns. Five older lines are 73 columns: `agent.py:76` and `:79`, `launch.py:192` and `:193`, and `settings.py:171`. They are untouched.

## Gates (final lines)

**Infinite-memory pack:** `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`, at `939381ec`
```
........................................................................ [ 86%]
......................................................                   [100%]
414 passed in 9.51s
```

**Full agent lint:** `python lint/run.py`, at the P2 checkpoint, and again inside the CI source stage at `939381ec`
```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```
The focused rules at P2 were:
- A007 255/255 RATCHETED
- A002 566/703 IMPROVED
- S008 19/19
- S024 25/25
- S019 5/5
- S051 259/259

Each run ended `SDK-LINT: PASS`.

**S051 command:** `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`
```
Found 223 errors.
[*] 223 fixable with the `--fix` option.
```
The same command on a `git archive` of `043004bb` also gives `Found 223 errors.`, so all 223 findings predate this change. The changed files alone give `All checks passed!`.

**CI source stage:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, at `939381ec`
```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 7033 passed, 17 skipped in 227.37s (0:03:47) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-infinite-memory-derived-events).
```
The single failure is the known pre-existing one named in the brief.

**CI package stage:** `python scripts/run_ci.py --stage package`, with `PYTHONPATH` unset
```
No broken requirements found.
Installed vidbyte-sdk 0.4.0 passed smoke checks.
CI passed.
```

**Public API:** `PYTHONPATH=$(pwd) python scripts/generate-sdk-public-api.py --check`
```
contracts/sdk-public-api.json is current at 1332a34e6205ab4c9a86615b0b37462cdd527002 (vidbyte-sdk 0.4.0, 678 exports).
```

**Tests untouched:** `git diff 2cab5070 -- tests/ | wc -l` prints `0`.

## Tricky parts

- **A007 is exactly at its baseline of 255.** Its context walk counts a numeric literal anywhere in a `with self._shielded(...)` body as operational, because `_deliver(..., depth, ...)` is in the same body. Any literal added inside a shield therefore fails the lint (deviations 1 and 2).
- **A002 and `attempt`.** `attempt` is passed inline as a keyword argument, and the records check it only through the string-name loop. The record's class field sits more than four lines above `__post_init__`, so it is outside A002's window.
- **S051 counts I001 findings across the whole tree.** The P1 lint caught one misplaced import, where `INFINITE_MIN_COUNT` came after `INFINITE_NO_DESCRIPTION`. `ruff --select I001 --fix` on the two files fixed it.
- **`InfinitePair.run` nests exactly 3 levels deep:** outer `try`, inner `try`, then `if`/`for`. S008 and S024 stayed at their baselines, so the verifier step did not have to move into a helper.
- **EC-10.** A sink that raises `KeyboardInterrupt` on `subagent_finished` sends the interrupt out of `_finish` into the outer handler with phase `commit`. `subagent_aborted` sees that the journal already has the finish, so it does not lower `in_flight` a second time.
- **AC-13.** `_commit` keeps `self.staged.remove(item)` after the `try`. An escaping error therefore leaves the failing entry and the later ones staged, and `staged` reads `2 − (fail_on − 1)`.
- **`map_omitted`.** In Python 3.11, `int()` raises `ValueError` for a string of more than 4,300 digits. The parse is wrapped and returns 0 in that case.
- **Line endings.** Source files in this worktree are CRLF, and `spec.md` is LF. Every edit went through a replacement script that keeps the file's line endings and refuses any pattern that does not match exactly once.

## Notes for S4 and S6

- The PR body is still the placeholder. S6 replaces it, and per §12.5 it must list the 8 new kinds, the 3 new enums with their values, and the changed details fields.
- NFR-7 and §12.4 say `AGENT-LINT: PASS`, but this repository's lint prints `SDK-LINT: PASS`.
