VERDICT: SOUND WITH FIXES — r2 resolves R-1…R-10 in the spec text and its reshaped §8/§12/§13 hold against the tree at `8baff351`; one Major remains (fork's two experimental fields are sent without the `experimental_api` gate their own precedent has) plus five one-line Minors.

WHAT THE SPEC GETS RIGHT
- **Round 1 is resolved in the text, not only in the log.** INV-21 puts `cancel_pending()` (closed flag, handler dropped, futures cancelled, one lock) first in `_end_running_turns` (R-5). `reject_user_reviewer` runs at every first-request point: preflight step 0, fork step 2 and the three wrappers (R-2). `CODEX_HOST_RETRYABLE_CODES` is chosen code by code (R-4). `CodexCommandApprovalKind`, `approval_id`, `environment_id`, `started_at_ms` and the tri-state `available_decisions` are in place (R-3). INV-47/INV-48, NFR-11, AC-40 and AC-41 bind the #1178 conventions (R-1).
- **The server-request contract is faithful to the 0.163.0 schema.** Required ids match each params schema's `required` list. `kind` defaults to `command`, as the wire does. Every fail-closed default carries its response schema's required field.
- **Retries go through the canonical helper.** `retry_on_overload` runs inside `call`'s existing `wait_for` (about 0.75 s of sleep at most), for four idempotent typed reads only, and spending raw calls keep one attempt (AGENTS.md §5, S012).
- **§12 and §13 are accurate.**
  - Row counts match: 9 non-message constants, 11 message constants, and 3 new files, which equals §8.4.
  - The order pins hold: `FORGET_CODEX_TURNS` goes after `TRACK_CODEX_THREAD_USAGE` and before `START_CODEX_REVIEW` (`test_codex_host_helper_surface.py:244-251,300-305`).
  - All 20 superseded tests and every seam line reference check out.
  - D-14's "no test references the moved privates" holds (grep of `tests/`).

FINDINGS

R-12 [Major] [L7] §8.1 D-19, §6.1 INV-28 step 6, §8.5 seam 2, AC-22 — Fork sends two EXPERIMENTAL-only fields with no `experimental_api` gate, although the `dynamicTools` pattern D-19 says it copies has one.
  Evidence:
  - `beforeTurnId` and `deferGoalContinuation` exist only in `schema-exp/v2/ThreadForkParams.json`. The stable `ThreadForkParams` lacks both, and A-6 confirms the SDK models lack them.
  - The server refuses an experimental field that was not negotiated with JSON-RPC -32600, "`thread/fork.<field> requires experimentalApi capability`" (codex TUI compat cases, `codex-rs/tui/src/app_server_session.rs:2944-2951`).
  - `errors.py:149-152` maps any refused `thread/fork` to `codex.fork_failed`. Its likely cause is "no completed turn at the fork point" (`constants/codex_host.py:146`), and its next step is "Fork from a completed turn." (`constants/codex.py:516`).
  - The precedent gates locally: `host.py:674-675` raises `ConfigurationError(CODEX_HOST_EXPERIMENTAL_API_TEXT)` before sending `dynamicTools` when `experimental_api` is False. `CodexClientSettings.experimental_api` is a public bool (`lib/dataclasses/codex.py:113`).
  - The fake's `_thread_fork` ignores both fields (§13), so no planned test can see this.
  Failure:
  - On a host built with `CodexClientSettings(experimental_api=False)`, `fork_codex_thread(t, before_turn_id="turn-2")` or `defer_goal_continuation=True` passes the record, the thread read and the preflight. It then fails as `codex.fork_failed` with `retryable=False` and "Fork from a completed turn."
  - The developer does exactly that, and gets the same error again.
  - A build that drops the fields instead of refusing would fork the whole history, or start EC-28's untracked goal continuation, the one thing the flag exists to stop.
  Smallest fix:
  - In `fork_codex_thread`, right after the record and before `self._threads.fork`, raise `ConfigurationError` with `details["field"]` naming the field when either field is set and `self._settings.experimental_api` is False. This mirrors `host.py:674`.
  - Text: a new lib constant `CODEX_HOST_FORK_EXPERIMENTAL_MESSAGE`, for example "fork_codex_thread {field} needs CodexClientSettings(experimental_api=True), because Codex accepts it only from clients that opt in to its experimental API." Row 3's message count becomes 12.
  - Add an EC-56 row, and an AC-22 clause: "with `experimental_api=False`, both fields raise `ConfigurationError` before any request".
  - This copies an existing control, so I do not tag it scope-adding. If the author rules otherwise, Q-20 (default: not built) applies, and the zero-scope minimum is an EC-56 row plus a §3 limitation stating the misleading code.

R-13 [Minor] [L5] §6.1 INV-17, INV-21 — The router lock's span is stated at its start but not at its end, so two natural implementations break close.
  Evidence:
  - INV-17 says "still holding the lock, it schedules … and adds the future", then that "One `try` spans parsing, scheduling and waiting" and that "A single `finally` removes the future from the pending set".
  - It never says the lock is released before `future.result()`, or re-taken for the removal.
  - INV-21 cancels "every pending future" under the lock, on the loop thread.
  - The template it cites discards without a lock (`agents/codex/tools.py:186-187`). It is safe only because its `close` iterates a snapshot, `tuple(self._pending)` (`tools.py:194`).
  Failure:
  - **(a) The lock is held across the wait.** A `with lock:` around the whole `try` makes `cancel_pending()` block the event loop thread on the lock. Meanwhile the reader waits on a handler that needs that same loop, so the whole loop freezes for `CODEX_TOOL_CALL_TIMEOUT_SECONDS` (300 s), and AC-38 hangs.
  - **(b) The removal is unlocked.** If the `finally` discards without the lock, `cancel_pending` must not iterate `self._pending` directly. If it does, the cancel wakes the reader, which discards mid-iteration, and "Set changed size during iteration" escapes `_end_running_turns`, intermittently, out of `__aexit__` or `_on_death`. Tests will not reliably catch this.
  Smallest fix: add one sentence to INV-17: "The lock covers the check, the parse, the scheduling and the add, and is released before `future.result()`. The `finally` re-takes it to discard, and `cancel_pending` cancels a snapshot (`tuple(self._pending)`)."

R-14 [Minor] [L9] §6.2 AC-41, §12.3 row 19, INV-30 — AC-41's `start_codex_review("thr-1", target, request={})` fails under the host's own default idiom.
  Evidence:
  - Six host call sites build their records with `x or CodexSpawnRequest()` (`host.py:313,355,489,618,639,647`), and `{}` is falsy.
  - `CodexReviewRequest.request` is typed `CodexSpawnRequest` and is not optional (§8.5, §9.1), so the host must turn `None` into a default before the record.
  - Row 19 says only "guard, record, delegate".
  - The #1178 boundary rows never pass a falsy non-record at host level (`test_codex_host_inputs.py:195-215`). `overrides={}` is tested only at record level (`:83`).
  Failure: S3 copies the sibling idiom. The bad `{}` silently becomes the default review and sends `review/start`, so AC-41's "no request is sent" fails. S3 then has to diverge from the pattern §8.2 told it to follow.
  Smallest fix: in row 19 and INV-30, state "the host substitutes `CodexSpawnRequest()` only when `request is None`; any other value reaches the record unchanged". The other option is to make the record field `CodexSpawnRequest | None` and use `require_instance(..., optional=True)`.

R-15 [Minor] [L7] §9.1 `from_params`, EC-4 — A null or absent question `options` is not mapped, and EC-4 invites treating it as a parse failure.
  Evidence:
  - In stable `ToolRequestUserInputParams`, `ToolRequestUserInputQuestion.options` is typed `["array","null"]` and is not required (only `header`, `id` and `question` are), and `isOther`/`isSecret` default to false.
  - §9.1 gives `options` the default `()`, but its null rules cover only the string fields ("wire `null` → `""`") and `availableDecisions`.
  - EC-4 makes "`questions` is not a list" a parse failure.
  Failure: a parse that generalizes EC-4, or indexes `params["options"]`, fails on every free-form question. Each such request is then declined with `{"answers": {}}`, even on a host whose handler would answer it, and the user sees only one fallback WARNING.
  Smallest fix: in §9.1, state "`options` absent or null → `()`; `isOther`/`isSecret` absent → False", and add an AC-11 clause: a question with `options: null` reaches the handler with `options == ()`.

R-16 [Minor] [L9] §6.1 INV-25, D-26, AC-20 — Refresh-on-miss does not say whether a list fetched by the same check counts as cached.
  Evidence:
  - Today's step 4 is `self._models = self._models or await self.models(...)` (`preflight.py:103`).
  - INV-25 refreshes "when the preflight's cached model list does not include a model".
  - D-26's reason, "a miss is the only case where staleness hurts", does not apply to a list read milliseconds earlier.
  - AC-20 covers only the already-cached case.
  Failure: on a fresh host, a spawn naming a mistyped model walks every `model/list` page twice before refusing. S2 and S3 can then disagree on the read count, for example over AC-31's `warp` case on a fresh host.
  Smallest fix: in INV-25, state "only a list taken from the cache is refreshed; a list this check just fetched is not read again".

R-17 [Minor] [L5] §15 A-10, INV-13 — A-10 is false for goal runs: every goal run's watcher read raises at its normal end, so INV-13 step (a) runs once per goal run.
  Evidence:
  - Each goal end calls `close_goal_stream` (`host.py:886-887`). That calls `state.finish()` and then `wake_notification_reader()`, which queues `_GoalStreamClosed`, an `Exception` (`openai_codex/_goal.py:191-193`).
  - The goal watcher reads "until its stream is closed or fails" (`turns.py:276-277`), so its read raises.
  - Under row 15, that `except` now posts `on_lost`.
  Failure: as specified this is harmless, because step (a) finds the snapshot. But A-10 calls the path rare, and says that "if wrong", the WARNING volume will show it, which it cannot, since step (d) never logs here. An implementer can then reasonably put the grace sleep before the snapshot check. That adds a 0.5 s task to every goal run, and AC-8 has no case for a normal goal end.
  Smallest fix:
  - Restate A-10: "every goal run ends with one watcher read failure (`_GoalStreamClosed`) after its snapshot is set; INV-13 step (a) returns at once."
  - Add an AC-8 clause: a goal run that ends normally sends no interrupt and writes no `codex_host_turn_lost` record.

VERIFIED CLAIMS
- **R-1…R-10 are resolved in the spec text: held.**
  - R-1: INV-47, INV-48, D-31…D-33 and AC-40/41; no new UPPER_CASE binding under `native/`, and the module logger is lowercase.
  - R-2: INV-20, INV-28 step 2 and AC-14.
  - R-3: §8.5, §9.1 and EC-5/6/51/52.
  - R-4: D-6, with `response_invalid` and `thread_resume_failed` raised only where retrying is sound.
  - R-5: INV-17, INV-21, EC-3 and AC-38.
  - R-6: INV-13 (d), D-9 and A-14.
  - R-7: NG-20 and FR-36.
  - R-8: the `fork_point` newest-first tri-state in §8.5.
  - R-9: the §13 seams.
  - R-10: rows 17–19 and §12.4.
- **C021 behaves as INV-47 assumes: held.** It fullmatches `_?[A-Z][A-Z0-9_]*` on top-level `Assign`/`AnnAssign` under `vidbyte/harnesses/native/`, exempting `__all__` and class attributes, with baseline 0 (`lint/baseline.json:30`). Imports by name, such as `CODEX_TOOL_CALL_TIMEOUT_SECONDS` and the grace constant, are `ImportFrom` and are not flagged, so the §13 patch targets work.
- **The cancellation semantics behind AC-38 and EC-3: held.** Python 3.11.0's `concurrent.futures.CancelledError` subclasses `Exception` and is not `asyncio.CancelledError`, so the router's `except Exception` turns a `cancel_pending` cancel into the default answer.
- **A-11: held (run in Python 3.11.0).** `inspect.iscoroutinefunction` is true for `partial(async_fn)`, for an async `__call__` reached through `obj.__call__` (false on the object itself, so the `__call__` check is needed), and for `AsyncMock()`.
- **INV-11's goal path ordering is benign.** The goal cancel spawned by `turn.stop` runs after `close_goal_stream`. `cancel_goal_operation` pauses the goal by thread id, and `_interrupt_goal_operation` falls back to stale ids and recovers the active one from "expected active turn id" (`openai_codex/client.py:572-597`).
- **Plain-turn watchers stop at `turn/completed` without another read (`turns.py:297-306`)**, so the asynchronous review read-back cannot trigger `on_lost` on a completed review.
- **INV-28 step 4's `run(spends=False)` repeats step 0's reviewer check:** local and harmless.
- **§4 and §5 agree with §8.5:** import paths, enum names, the constructor keyword, the `forget_codex_turns` return value, and the flow labels (retry set, fallback paths, two new turn endings).
- **The 0.163.0 wire facts: held.**
  - `ThreadTurnsListParams`, `serviceTierForTurn` and `forceReload` are stable.
  - `CommandExecutionRequestApprovalParams` requires `itemId`, `startedAtMs`, `threadId` and `turnId`, and its `kind` defaults to `command`.
  - `FileChangeRequestApprovalParams` has the same required set, plus a nullable `grantRoot`.
  - The `ToolRequestUserInputResponse` shape matches INV-15.
- **The installed SDK and settings: held.** The installed SDK's `ReasoningEffort` already has `max` and `ultra`, and `EFFORTS` derives from the enum (`threads.py:69`). `CodexClientSettings.experimental_api` defaults to True.
- **File sizes at base: held.** `host.py` 919, `connection.py` 344, `wire.py` 705, `turns.py` 415, `preflight.py` 146, `thread_helpers.py` 258, `lib/dataclasses/codex_host.py` 616, `codex_host_inputs.py` 372, `lib/constants/codex_host.py` 342, `errors/base.py` 652, and `lib/dataclasses/codex.py` 1,205. NFR-6's "about 890" for `host.py` is plausible: about 130 lines move out (review helpers `:803-866`, `_on_turn_event` `:868-889`, and the bodies of fork and review start) and about 100 come in.
- **The #1178 boundary test derives its rows from `inspect.getmembers(CodexHost, iscoroutinefunction)` with more than one parameter** (`test_codex_host_inputs.py:211-212`), so `forget_codex_turns` must get a row, as AC-41 implies.
- **`CODEX_NEXT_STEPS` pin changes are covered by superseded test A4** (`codex_host_support.py:62-67`).
