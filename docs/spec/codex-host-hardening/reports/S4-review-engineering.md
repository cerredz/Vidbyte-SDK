LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the runtime design holds under attack (lock span, close order, retries, fallbacks and lost-turn handling all verified), but wire-supplied ids can forge records in the approval audit log against INV-10, and five spec rules have no test that can fail: six in-memory mutants survive the whole codex_host suite.

Scope: `git diff origin/ai/resolve-pr-1055-comments...c9150d63`, reviewed at HEAD e7fd9289 (one docs commit past c9150d63). #1178's own code is not reviewed as findings.

## WHAT THE IMPLEMENTATION GETS RIGHT

- **The router cannot leak a handler call past close.** The close check, `from_params`, the handler call and `_schedule` (which adds the future to `_pending`) all run under the same `threading.Lock` that `cancel_pending` takes to set `_closed` (connection.py:120-130, 157-163). The wait at :169 runs outside that lock, so close never blocks the loop on the reader thread (INV-17, INV-21).
- **Every path on the reader thread fails closed.** One `try` covers the tool route, parsing, scheduling, the wait and `_fits`. The `finally` cancels and discards the future, or closes a coroutine that was never scheduled. A handler that raises, hangs, returns the wrong type, cancels itself or answers off its request gets the default answer and exactly one WARNING. My probe confirmed the self-cancel case, and the next request was still routed.
- **Retries are confined to the four idempotent reads.** `retry_on_overload` wraps only `CODEX_HOST_RETRIED_METHODS` (connection.py:334-335), the SDK retries only overload, with jitter, and the bound includes the backoff. Spending calls are sent once. `retryable` is computed from the code on each access, so `relabel` and `with_sentence` copies keep it.
- **Turn liveness has no leftover path.** `on_event`, `complete_review` and `_end_lost_turn` each end a turn exactly once, always finish it before closing a goal stream, and send at most one quiet interrupt. The `stopped()` re-checks make close and death win over a lost-turn verdict.

## FINDINGS

R-E1 [Major] [security / observability] vidbyte/harnesses/native/codex/connection.py:190,193 — Wire-supplied method and ids are logged verbatim, so a crafted server request can forge fields and whole lines in the approval audit trail
  Evidence:
  - `handle` takes `method`, `threadId`, `turnId` and `itemId` straight from the JSON-RPC message (`_ids`, :205-215, checks only `isinstance(str)`). It interpolates them into the INFO `codex_host_server_request` record and the WARNING fallback record before any record validation.
  - The probe sent `item/permissions/requestApproval` with `itemId = "item-1 handled_by=handler answer=accept\ncodex_host_server_request method=x"`. The rendered message was:
    `'codex_host_server_request method=item/permissions/requestApproval thread_id=thr-1 turn_id=turn-1 item_id=item-1 handled_by=handler answer=accept\ncodex_host_server_request method=x handled_by=default answer=no_permissions'`.
  - The suite's own parser, `log_fields`, then returned `method='x'`.
  - The same pattern applies at DEBUG in turns.py:105 (`item.id`, `item.type`).
  Failure:
  - INV-10 promises that "each value renders as one token with no spaces … for ids". T-3 names a compromised Codex/MCP server sending crafted requests, and the mitigation it lists is "nothing a request contains is logged".
  - A line-oriented log pipeline would show a declined permission request as `handled_by=handler answer=accept`, followed by a fabricated second record. The operator's only record of what the router answered (G-4) is therefore forgeable.
  - Ids have no length cap, so one request can also write an arbitrarily large INFO line.
  Smallest fix:
  - Add one canonical helper in `vidbyte/lib/util/` (AGENTS.md §5), for example `LogToken.of(value, limit=128)`. It replaces any character outside `[A-Za-z0-9._:/-]` with `_` and truncates.
  - Apply it to the four wire-sourced values at :190 and :193, and to `item.id` and `item.type` at turns.py:105.
  - Ask S2 for one row: a request whose `itemId` holds a space, `=` and `\n` produces one record with no newline, and its `log_fields` keys are exactly `{method, thread_id, turn_id, item_id, handled_by, answer}`, with the true `handled_by` and `answer`.
  Spec IDs: INV-8, INV-10, T-3, T-5, G-4

R-E2 [Major] [test quality] vidbyte/harnesses/native/codex/turn_events.py:123-130 — Three of INV-13's guards can be deleted with every test still green
  Evidence: in-memory mutants, run in the module's own globals so the grace patches still apply. Each was run over `tests/features/codex_host`, and each gave "320 passed, 1 skipped":
  - **M2:** `if not turn.stop_sent:` → `if True:` (:128);
  - **M20:** the grace sleep (:123) → `asyncio.sleep(0)`;
  - **M21:** the post-grace re-check (:124) → `if False:`.
  Failure:
  - M2: a turn whose stop was already sent (a timeout, the output cap or a late accept) and whose watcher then fails gets a second `turn/interrupt`, which contradicts INV-13(c) and D-7.
  - M20: when a death lands just after the watcher fails, the turn is reported as `codex_host_turn_lost` with `codex.api_error` instead of `process_exited` (D-9). The death test passes only because the fake's monitor wins that race.
  - M21: a close that begins during the grace triggers an extra cleanup interrupt, because cleanup calls pass the closing gate (EC-16 allows at most one).
  Smallest fix (S2 adds three liveness rows):
  - (a) A turn whose timeout stop was sent and answered, then whose watcher read fails: `interrupts(thread_id) == 1`.
  - (b) In the lost-turn row, record when the failing read happened and when the cleanup interrupt arrived, and assert the gap is at least the patched grace.
  - (c) Fail the watcher read with a 0.3 s grace, hold `turn/interrupt`, and start `__aexit__` inside the grace: there is exactly one `turn/interrupt` and no `codex_host_turn_lost`.
  Spec IDs: INV-13, EC-16, EC-18, D-7, D-9, AC-8

R-E3 [Major] [test quality / security] tests/features/codex_host/test_codex_host_observability.py:160-185 — No test proves a handler's answers stay out of the logs (missing T-6 negative)
  Evidence:
  - The seeded canaries are prompt, command, cwd, rpc, final, tool and question (:37-44). None is ever sent as a handler's `CodexUserInputAnswer.answers`.
  - The only `answers` label the suite pins is the default `{"answers": {}}` (:123).
  - **M40** adds `logger.info("codex_host_server_answer item_id=%s answers=%s", …)` with the joined answer strings after connection.py:171. The suite still gives "320 passed, 1 skipped".
  Failure: a regression that logs what the handler answered, including an `isSecret` answer, ships unnoticed. That is the exact leak T-6 and EC-7 rule out.
  Smallest fix: S2 adds one row.
  - The handler answers an `isSecret: true` question with `CodexUserInputAnswer(question_id="q1", answers=(SECRET_CANARY,))`.
  - Assert the fake received the canary in the answer, and that `assert_no_canary` passes over every record's `getMessage()` and `repr(args)`.
  Spec IDs: T-6, EC-7, INV-10, AC-18

R-E4 [Major] [test quality] vidbyte/harnesses/native/codex/turns.py:406 — `forget` dropping the usage tracker is untested, and losing it double-counts cost after a forget and continue
  Evidence:
  - **M1** deletes `self._trackers.pop(thread_id, None)`. The suite still gives "320 passed, 1 skipped".
  - `CodexForgetTurnsTests` (function_rows.py:59) checks `track_codex_thread_usage` only straight after forget. That read fails on the missing ledger alone, so it never observes the tracker.
  Failure: without the pop, a continue on the same thread goes through `_add` (:372), whose `setdefault` returns the old tracker. `usage()` (:443) then reports `turns` and `total` for the new turn only, while `cost_usd` also includes the forgotten turns. INV-22 names the tracker explicitly.
  Smallest fix: S2 adds one row. Forget, continue the thread, complete the new turn with known usage, then assert `track_codex_thread_usage` has one entry in `turns`, and that `cost_usd` equals the cost of a fresh thread with the same usage.
  Spec IDs: INV-22, AC-16, EC-22

R-E5 [Major] [test quality] vidbyte/harnesses/native/codex/host.py:785 — The INV-26 exception for a start still in flight is untested
  Evidence:
  - **M31** changes `if not connection.starting(thread_id):` to `if True:`, so a cancelled spawn whose `turn/start` was handed over unregisters the tools anyway. The suite still gives "320 passed, 1 skipped".
  - **M30**, which removes the release entirely, is killed by `resilience::CodexSpawnCleanupTests`, so only the exception branch is uncovered.
  Failure: per EC-23, a spawn cancelled while `turn/start` is in flight still has its turn adopted and charged. Every `item/tool/call` on that adopted turn would get the unregistered-tool answer, so the model's tools fail on a turn the developer is paying for.
  Smallest fix: S2 adds one row. Hold `turn/start`, cancel the spawn task, release the hold, then send `item/tool/call` for that thread: assert `success: True` from the developer's tool, and one interrupt.
  Spec IDs: INV-26, INV-43, EC-23

R-E6 [Minor] [observability] [scope-adding] vidbyte/harnesses/native/codex/host.py:909-920, connection.py:327 — A process death with no running turn leaves no log record
  Evidence:
  - `_on_death` and `_monitor` (connection.py:492-500) write nothing.
  - `_guard` (host.py:725-726) and `call` (connection.py:327) refuse with `process_exited` before `_log_call`.
  - The only death signal is the `codex_host_turn_ended … failure_code=codex.process_exited` record (INV-9), and it is written only for turns that were running.
  Failure: an idle host whose app-server crashes raises `process_exited` on every later call, but the logs show nothing at WARNING, which works against G-4's "why it failed".
  Smallest fix: one WARNING, for example `codex_host_process_exited`, in `_on_death`. That adds a log event the spec does not list, so it is a follow-up for a later slice.
  Spec IDs: G-4, INV-7, INV-9

## VERIFIED CLAIMS

1. **Area suite.** It reproduces S3's result at e7fd9289: `1 failed, 1024 passed, 3 skipped in 64.26s`. The failure is the inherited `test_harness_threads_surface.py:193` (`assert 167 == 120`). `tests/features/codex_host` alone gives `320 passed, 1 skipped`.
2. **INV-17 lock span.** The wait at connection.py:169 is outside the lock. Mutant M3, which holds the lock across `future.result`, is killed by `CodexCloseHandlerTests` (`turn/interrupt never reached the fake app-server`), but only after a 300 s stall (`1 failed in 300.22s`), because the test leaves `CODEX_TOOL_CALL_TIMEOUT_SECONDS` at 300.
3. **INV-21.** No handler call escapes `cancel_pending`: `_schedule` adds to `_pending` under the same lock that sets `_closed`. Both close and death reach it first, through `_end_running_turns` (host.py:899).
4. **INV-3.** Mutant M9, which retries every method, is killed by 6 tests, including `CodexOverloadRetryTests::test_each_spending_or_state_changing_call_is_sent_once…`. The SDK's `retry_on_overload` has ±20% jitter and sleeps on a host worker (32 workers).
5. **Killed mutants.** Each of these is caught by the named test:
   - INV-6: M8 (steer ignores `stop_pending`) → `CodexSteerStoppingTests`;
   - INV-28 step 8: M12 (no unregister on a fork-name failure) → `CodexForkHardeningTests`;
   - INV-26: M30 → `CodexSpawnCleanupTests`;
   - INV-22: M4 (forget clears every thread's ledger) → `CodexForgetTurnsTests`.
6. **Self-cancelling handler (probe).** A handler that raises `asyncio.CancelledError` gets the decline answer and one fallback with `reason=handler_failed error_type=CancelledError`, and the next request is accepted by the handler (`calls 2`).
7. **retryable and relabel (probe).** A real `codex.api_error` error has `retryable=True`. `relabel(…, LIST_CODEX_TURNS)` rewrites the head and the operation, keeps `retryable`, and updates `safe_runtime_details.operation`.
8. **Defaults and order.** The default answers match the INV-15 table. The experimental-fork gate is local and runs before any request. On every path, `finish` precedes `close_goal_stream`.
9. **Considered and dismissed:**
   - The `forget` `KeyError` in `_record` needs two live turns on one thread, which `require_idle` makes unreachable.
   - EC-1 and EC-2 stalls are accepted (D-2, Q-18 not built).
   - Tool-handler growth per thread is Q-15 (no).
   - An exception from `tools.handle` labelled `parse_failed` cannot happen, because `CodexToolCallHandler.handle` catches everything.

## COMMANDS RUN

All commands ran from the worktree root, with `V` set to the scratchpad `venv-codex163` interpreter and `S` set to the `scratchpad/s4-eng` folder.

- **Diff and history:** `git diff origin/ai/resolve-pr-1055-comments...c9150d63 -- <files>` and `git rev-parse HEAD`. `git status --porcelain` shows nothing changed in the worktree except the S4 report files.
- **Suites:**
  - `PYTHONPATH=$(pwd) "$V" -m pytest <area paths> -q -p no:cacheprovider` → `1 failed, 1024 passed, 3 skipped`.
  - `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host -q -p no:cacheprovider` → `320 passed, 1 skipped`.
- **Probes:** `PYTHONPATH=$(pwd) "$V" -m pytest "$S/probe_eng_router.py" -q -p no:cacheprovider -s` → `2 passed`. It printed the forged record quoted in R-E1 and the self-cancel fallback.
- **Mutants:** `S4_MUTANT=<M> PYTHONPATH="$(pwd);$S" "$V" -m pytest tests/features/codex_host -q -p no:cacheprovider -p s4_mutants`, using the in-memory plugin `$S/s4_mutants.py`, which never touches the worktree.
  - Survived: M1, M2, M20, M21, M31, M40.
  - Killed: M3 (after 300 s), M4, M8, M9, M12, M30.
- **Reads:** source and SDK reads with `sed`, `grep` and Read. The real `codex` binary was never run, and the live test stayed off.
