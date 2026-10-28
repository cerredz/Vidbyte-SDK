VERDICT: SOUND WITH FIXES — The derivation design is correct and fits the repo, but AC-13, AC-14 and EC-2 assume a child agent's error reaches the pair unwrapped. Some ordering and closure claims are also false, and the phase plan breaks the stream between P1 and P2. All of these are local rewrites.

## WHAT THE SPEC GETS RIGHT

- **D1 really is derived and needs no hook.** `AgentRuntime._denied_tool_result` (vidbyte/agents/runtime.py:1415-1419) keeps `reason` and the middleware's `limit` (delegation_limits.py:55, :67) on a DENIED `ToolCallContext`. The same cumulative list feeds `state.call_contexts` and `result.metadata["tool_calls"]` (`_runtime_metadata`, :2125). `_after_tool_iteration` has one call site (:700), so the high-water mark plus the post-loop catch-up announces each denial exactly once. Generator replies carry `tool_calls` through the metadata merge (base.py:986-1006).
- **D-5 is the smallest robust A3 design.** `VidbyteSdkError.__init__` passes only `message` to `Exception` (errors/base.py:75-79), so `str(exc)` and `exc.message` stay byte-identical when a `details["rule"]` key is added. The runtime reads only `details["error"]` and `details["error_type"]` (runtime.py:1332-1333). No new error family is needed.
- **The budget is honest.**
  - Measured after the header: events 400, launch 398, lib records 604, matching §8.4.
  - The estimates of about 620, 444 and 827 are plausible. Launch is the tightest, at about 3 % headroom.
  - The other budget modules have room: workspace 354, constants 306, memory 284, runtime 131.
  - The package has 9 `.py` files today, so the `<= 9` check holds.
- **Observation-only and determinism are designed in.**
  - Every new method returns before reading its arguments when there is no sink.
  - `_shielded` catches only `Exception`.
  - The catch-and-re-raise in `InfinitePair.run` has no `await`, so it cannot swallow `CancelledError`.
  - Throttles count iterations or are edge-triggered, and the pair turn is `sleep(0)` (constants/infinite.py:43).
  - The AC-2 list and the unchanged AC-3 list at stream test :250 are correct under default caps.

## FINDINGS

R-1 [Blocker] [L10] §6.2 AC-13, §6.3 EC-2 — A generator's own error can never escape its pair, so AC-13 cannot pass and EC-2 describes a stop that never happens
- Evidence:
  - `InfinitePair.run` reaches the generator through `BaseAgent.arun` → `generate_reply` → `_generate_reply` (base.py:1098-1100, :907).
  - The `except Exception` there (base.py:965-979) re-raises every error as `AgentExecutionError(...) from exc`, except three typed errors (`UsageAccountingError`, `FailureRaisedError`, `AllModelsFailedError`).
  - `AgentExecutionError` is a `VidbyteSdkError` (errors/base.py:138). So the pair's `except (VidbyteSdkError, OSError, ValueError)` (launch.py:267) catches a runner or tool-loop `RuntimeError` or `KeyError` and turns it into a card.
  - The existing raising-generator test already shows this: it uses `fail(VidbyteSdkError(...))` and pins `subagent_finished` at test_infinite_memory_events_pairs.py:475-479. §13's note that :479 "adds `subagent_aborted`" is therefore wrong. That list gains `memory_dropped` (unchecked) and `batch_finished`.
  - An `Exception` that does escape `InfinitePair.run` leaves `InfiniteLaunchTool.execute` and is caught by `AgentRuntime._run_tool_call`'s `except Exception` (runtime.py:1341-1348). That returns "Tool execution failed: …", and the root loop continues. No `run_stopped` follows.
- Failure:
  - S2 writes AC-13 as `fail(RuntimeError())` in the generator. The run then delivers `subagent_finished` with an error and no `subagent_aborted`.
  - The implementer cannot turn that green without editing base.py, which INV-20 forbids, so they stop BLOCKED.
  - EC-2's "then `run_stopped`" is wrong for every `Exception`. The real tail is the tool error, the root's next turn, and `run_finished`.
- Smallest fix:
  - Re-ground AC-13 on code inside the pair but outside its child agents. Example seam: monkeypatch `InfiniteWorkspace.commit_entry` to raise `RuntimeError`. `_commit` catches only `ToolExecutionError`, so this gives phase `commit` and `staged` = N.
  - AC-13's Then becomes: `subagent_aborted(failed, RuntimeError, commit)`; the root's `launch_subagent` result starts with "Tool execution failed:"; the run ends with `run_finished`.
  - Rewrite EC-2's "User sees" column to match.
  - Add one sentence: a child agent's own `Exception` always becomes the pair's card, wrapped as `AgentExecutionError`.
  - Correct the §13 prediction for :479.

R-2 [Blocker] [L10] §9.1 `InfiniteSubagentFinishedDetails.error_type`, §6.2 AC-14 — `type(pair.error).__name__` names the wrapper, so almost every failed pair reports "AgentExecutionError"
- Evidence:
  - base.py:976-979 wraps every child `Exception` as `AgentExecutionError ... from exc`, except the three typed errors above. The original class goes into `details["error_type"]` and `__cause__`.
  - The pair already reads `error.__cause__` for its review text (`InfinitePair._error_text`, launch.py:386-391).
  - Only errors raised by the pair's own code arrive unwrapped, for example `workspace.entries` in `_task_message` (launch.py:322) or a journal write. Root errors are also unwrapped, which is why lifecycle test :165-194 pins `RuntimeError` on `run_stopped`.
- Failure:
  - AC-14 ("a generator raises `ToolExecutionError`, and `error_type` is that class name") fails as built.
  - The dashboard gets one value with no information for provider outages, timeouts and tool-loop bugs alike.
- Smallest fix:
  - Use `type(pair.error.__cause__ or pair.error).__name__` as the value rule. This mirrors `_error_text`.
  - Restate AC-14's Given as "the generator's runner raises `ToolExecutionError`".
  - Use the same rule for `subagent_aborted.error_type`, so the two kinds agree.

R-3 [Major] [L5] §1 G-3, §6.1 INV-15, §12.3 row 6 — "Each batch that started pairs is closed by one `batch_finished`" is false whenever the pipeline raises
- Evidence:
  - Row 6 places `batch_finished` after `await ParallelPipeline(...).run("")` inside `if pairs:` (launch.py:157-158).
  - `ParallelPipeline.run` calls `asyncio.gather` without `return_exceptions` (pipelines/parallel.py:43-45). It raises on the first cancelled or failed child, so the `batch_finished` line is skipped:
    - on cancellation (AC-12, EC-3);
    - on every pair abort (the R-1 path), where siblings keep running and the root continues to `run_finished`.
- Failure: G-3's own consumer, a UI that groups rows by batch, keeps that group open forever, and no EC row tells it how to close it.
- Smallest fix:
  - Add an EC row: "a batch whose pipeline raises gets no `batch_finished`; close it on `run_stopped` or `run_finished`".
  - Qualify G-3's metric and INV-15's `batch_finished` sentence with "unless its pipeline raised (EC-n)".
  - Alternative: emit it from a `finally:` around the `await`, with unfinished pairs counted in no verdict bucket.

R-4 [Major] [L5] §15 A-6, §6.3 EC-3, §13 "Cancellation" — `subagent_aborted` comes before `run_stopped` only for pairs that are not waiting on a nested batch
- Evidence:
  - `_GatheringFuture.cancel` cancels each child.
  - Gather's `_done_callback` calls `outer.set_exception` on the first child that finishes cancelled, and that queues the waiting task's wakeup.
  - A depth-1 pair whose generator is itself waiting on a nested `ParallelPipeline` is woken only through its inner gather's callback.
  - Trace with root batch `[b (leaf pair), a (generator waiting on a nested batch)]`:
    1. b's handler runs, then a's grandchildren's handlers run.
    2. The root gather completes from b, and the root task's wakeup is queued.
    3. The inner gather completes, and a's wakeup is queued after the root's.
    4. The root unwinds, and `run_stopped` fires.
    5. Only then does a's handler announce `subagent_aborted`.
  - With the order `[a, b]`, the claim happens to hold. This follows from asyncio ≥ 3.11 semantics and is deterministic, not a race.
- Failure:
  - EC-3's "one `subagent_aborted` per running pair, then `run_stopped`" is false for nested trees.
  - A consumer that finalizes on `run_stopped` misses a late abort. Under `agent.run` that abort fires during `asyncio.run`'s shutdown cancellation.
- Smallest fix:
  - Restate A-6 and EC-3: the order holds for pairs not waiting on a nested batch; such a pair may announce its abort after `run_stopped`, as in EC-12 and EC-17.
  - Add a line to the README notes (row 12) and to events.py KNOWN EDGE CASES (row 5).
  - AC-12 is flat, so it is unaffected.

R-5 [Major] [L8] §12.5 — The claim that no other doc outside `docs/` lists event kinds is false: vidbyte/agents/README.md:183 lists them
- Evidence:
  - vidbyte/agents/README.md:183 lists the stream in prose: "the run starting, resuming, finishing, or stopping, each pair launched, replayed, and finished, each generator's reply, each memory entry saved, staged, or dropped, each note written, and each refused call".
  - §12.3 has no row for this file, and §12.5 says a search found nothing.
- Failure: The agents folder README leaves out verifier steps, aborts, commits, batch close, the heartbeat, usage and the handoff. A stale folder README is exactly the drift the review workflow flags.
- Smallest fix: Add a P3 row to §12.3 that extends that sentence with the new steps, and correct §12.5.

R-6 [Major] [L11] §12.6 — P1 makes every enriched event fail silently, so "every other existing test passes after each phase" is false
- Evidence:
  - Row 4 (P1) appends required fields without defaults to 8 existing details records.
  - `events.py` only starts passing those fields in row 5 (P2).
  - In between, each construction raises `TypeError` inside `_shielded`, which catches `Exception` and drops the event (events.py:322-333).
- Failure:
  - After P1 these kinds all disappear: `run_finished`, `run_stopped`, `batch_rejected`, `tool_refused`, `subagent_launched`, `subagent_finished`, `memory_saved`, `memory_staged`, `file_written`.
  - Tests that S2 does not touch then fail, for example the `file_written` assertions at pairs :514-516.
  - §14 tells the implementer to stop BLOCKED on "a pinned test the spec did not foresee".
- Smallest fix: Either move row 4's "append fields to existing records" bullet into P2 next to row 5, or declare P1 and P2 one checkpoint and run the pack only after P2.

R-7 [Blocker] [L4] §12.3 rows 5, 6, 7, 10 — Comments that this change makes false or incomplete are not scheduled for update, which breaks AGENTS.md principle 2
- Evidence:
  - **launch.py:225-229.** The `@intent one-failed-pair-never-sinks-its-siblings` comment says "cancellation is not caught, so stopping the run stops every pair". D-10's outer `except BaseException` catches cancellation and re-raises it. Row 6 rewrites only header rule 2.
  - **launch.py header :9.** It says an error outside the three types "escapes the pair and the call while its siblings keep running (spec EC-41)". The error is now announced first, and per R-1 the call ends as a tool error. Row 6 rewrites only the EC-37 sentence.
  - **runtime.py:130.** The `_after_tool_iteration` docstring says only "Render the workspace map again…", but the hook now also announces denials, usage and progress.
  - **events.py header.** The :5 ARCHITECTURE NOTE lists the flat helpers but not `_rule` or `_quota`. The :6 FUNCTION INVENTORY groups `batch_rejected` "from the launch tool", but it now also comes from the runtime and from pairs.
  - **journal.py:4.** The ROLE line says InfiniteEvents reads the journal only "for a resumed or finished run's event". The launch path now also reads `started`.
- Failure: AGENTS.md principle 2 says: "update its comments in the same edit so they never describe behavior that is gone". An implementer who follows §12.3 row by row (§14) leaves a false `@intent` comment in a main function, which will draw a convention comment in review.
- Smallest fix: Add these edits to rows 5, 6, 7 and 10. Reword the intent to "cancellation is announced and re-raised, never swallowed, so stopping the run stops every pair".

R-8 [Minor] [L9] §6.1 INV-3, INV-10, INV-16 vs §6.3 EC-10 — The invariants contradict the sink-interrupt edge case
- Evidence:
  - EC-10 delivers `subagent_finished` and then `subagent_aborted` for one pair, but INV-10 says "exactly one".
  - Row 5 decrements `_in_flight` in both methods. So INV-16 ("launched minus finished or aborted") counts that pair twice and under-reports a sibling that is still running. The floor at 0 hides only negative values.
  - INV-3's "re-raises the exact exception object" fails if the sink raises its own `BaseException` inside `subagent_aborted`. Nothing is swallowed, but the new exception replaces the original.
- Smallest fix:
  - Write INV-10 as "exactly one, except EC-4 and EC-10".
  - Skip the decrement in `subagent_aborted` when `pair.result is not None`.
  - Qualify INV-3 with "unless the sink raises a `BaseException` of its own".

R-9 [Minor] [L1] §8.1 D-16, §15 A-11 — `run_finished.files` undercounts resumed runs, and its stated reason contradicts D-12
- Evidence:
  - D-16 rejects counting created files because "it cannot use a disk read inside the shield". But D-12 scans the disk with `workspace.usage()` inside the shield.
  - `journal.root_files` is set by `journal.finish` from the current session's `memory.files_written` (runtime.py:119, journal.py:114-119). An interrupted session writes no `run_finished` record.
  - So after a resume, notes the root wrote in earlier sessions are missing, while D-16 says the pair totals cover the whole run.
- Smallest fix: Either count `workspace.descriptions(run_id)`, A-11's runner-up, which is consistent with D-12. Or keep "notes written", correct the reason, and add the resume gap to EC-16.

R-10 [Minor] [L2] §8.1 D-19 — Reordering `InfiniteEventKind` adds risk and buys nothing
- Evidence:
  - D-19 inserts the 8 new members among the 14 existing ones.
  - The member order of a root-exported enum is observable through `list(InfiniteEventKind)`.
  - A-8 is unverified, and the runner-up, appending, is the smaller change.
- Smallest fix: Append the 8 members after `TOOL_REFUSED`, with `DETAILS_TYPES` in the same order, and drop A-8.

R-11 [Minor] [L7] §10 T-2(c) — The model can still forge the map's closing line when the map is not cut
- Evidence:
  - T-2(c) reasons only about lines that start with `- `. But `map_omitted` reads the map's last line.
  - When nothing is cut, that last line belongs to the last file entry. Either of these can end the map with "… and 9999 more files":
    - a file name with a newline in it, which `bash` can create;
    - a description in `files.jsonl` that contains a newline. `_descriptions` (workspace.py:339-351) accepts any string.
  - The effect is a false `map_omitted` value or a false `cut` flag, in events only.
- Smallest fix: State T-2(c) as an accepted, event-only limitation with an EC row, instead of claiming the line cannot be forged.

R-12 [Minor] [L1] §9.1 `InfiniteWorkspaceUsageDetails` — The usage event does not carry the level that triggered it
- Evidence: `workspace_usage` fires when `(level, cut)` changes (D-12, INV-13). The record holds only counts and caps, and the summary template has no level either.
- Failure: Every consumer has to recompute the level from its own copy of `INFINITE_EVENT_USAGE_PERCENTS`, and can disagree with the trigger, for example about files versus tokens.
- Smallest fix: Add `level: int` (a count, at most 100) to the record and its summary.

R-13 [Minor] [L9] §8.5, §9.3, §11, §13, §17 — Clerical mismatches the implementer will trip on
- Evidence:
  - §17 says "7 enriched details records", but §8.5 and row 4 list 8.
  - §9.3 adds `INFINITE_TOOL_CALL_CONTEXTS_METADATA_KEY = "tool_calls"` next to the existing `INFINITE_TOOL_CALLS_METADATA_KEY = "tool_call_count"` (constants/infinite.py:207). The two names read the opposite way from their values.
  - §13 cites `_worst` at records :165-227, but it is at :144.
  - The directory listing in §11 leaves out `__init__.py` and `settings.py`. The count of 9 is still right.
- Smallest fix: Correct the count, line number and listing. Rename the new key to something like `INFINITE_CALL_RECORDS_METADATA_KEY`.

## VERIFIED CLAIMS

| Claim | Verdict | Evidence |
|---|---|---|
| D-2: a DENIED context carries `limit` and `reason` | TRUE | delegation_limits.py:52-68; runtime.py:1415-1419 |
| D-4: the hook has one call site, and finish, refusal, contract-rejection and abort turns skip it; the catch-up reads the same cumulative list | TRUE | runtime.py:700, :680-698, :2125 |
| A-4: a generator reply carries `tool_calls` | TRUE | base.py:986-1006 |
| A-3: each run gets a fresh runtime, so per-run fields on the runtime are safe | TRUE | base.py:1319, :1388, :1408-1461 |
| D-5 / INV-5: a `details` key leaves `str(exc)` and `exc.message` unchanged | TRUE | errors/base.py:75-79 |
| D-15 / §8.4: lines after header are 400/398/604, the estimates are plausible, and the 9-module limit holds | TRUE | measured with the budget test's `_lines_after_header`; contract test :474-489 |
| NFR-2 / INV-7: a private static `_rule` or `_quota` stays out of the public-method set | TRUE | stream test :418-442 |
| §13: AC-2 under default caps adds no `workspace_usage` or `agent_progress`, and AC-3 :250 is unchanged | TRUE | level 0 never crossed; fewer than 10 root iterations |
| The AC-36 / AC-7 predicted list | TRUE | pairs :542-560 traced against the hook timing |
| The catch-and-re-raise cannot swallow `CancelledError` | TRUE | no `await` in the handler; `_shielded` catches `Exception` only. A sink `BaseException` can replace the error (R-8) |
| AC-13 / EC-2: a generator's `RuntimeError` gives `subagent_aborted`, then `run_stopped` | FALSE | base.py:965-979; runtime.py:1341-1348 (R-1) |
| AC-14: `error_type` is the raised class | FALSE | wrapped as `AgentExecutionError` (R-2) |
| A-6 / EC-3: every abort comes before `run_stopped` | FALSE for nested trees | gather's first-cancelled-child callback (R-4) |
| §12.5: no other doc lists event kinds | FALSE | vidbyte/agents/README.md:183 (R-5) |
| §13: pairs :479 adds `subagent_aborted` | FALSE | that test uses `fail(VidbyteSdkError)`, which becomes a card |
| §13: `_worst` is at records :165 | FALSE | it is at :144 |
| INV-6: the pair turn introduces no clock | TRUE | `INFINITE_PAIR_TURN_SECONDS = 0` (constants/infinite.py:43) |
