LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the lifecycle core (shielded starts, queued withdrawal, death handling, per-turn usage and the once-only cap interrupt) holds under probing, but four cancellation windows leave paid turns unowned, unstopped or leaking the app-server, the output schema is checked only after `thread/start` already sent, and the late-acceptance tests check status only, so these gaps went unnoticed; every fix is local and needs no new class or record.

Diff reviewed: `git diff origin/main...099fac83` (local HEAD 3ebefd11 differs only in `docs/spec/codex-host/pipeline.md`; `vidbyte/` and `tests/` are byte-identical to 099fac83). Line numbers come from `git show 099fac83:<path> | cat -n`.

WHAT THE IMPLEMENTATION GETS RIGHT
- Spending starts go through `connection.start` (connection.py:202-236), which awaits a shield and then hands the start over. If the caller leaves, `future.cancel()` withdraws a start that is still queued, and a start already running reports back through a done-callback, which fires at once on a future that has already finished. That closes the cancel-after-completion race. The EC-78 test is not vacuous: a mutant that skips the queued withdrawal fails it 3/3 runs.
- Death handling holds in every window I probed. Death during `turn/start` gives `codex.process_exited` "The Codex app-server exited during turn/start. Thread: thr-1.", with closes=1 and running=0. Death during a goal gives FAILED/process_exited and runs finish → wake_notification_reader → unregister_goal_operation → close, and the watchers go 1→0. Death during the close interrupts still lets close finish, with the executor shut down. Idle death is reaped and the monitor thread ends. A second death is impossible, because the `_closing` guard at host.py:726 absorbs the second post.
- Per-turn usage is right under A-3. `usage_delta` (turns.py:107-117) computes latest.total − (first.total − first.last). `over_cap` (turns.py:119-125) uses a strict `>` and checks `stop_sent`. The riskiest test (`test_the_output_cap_counts_only_the_turns_own_tokens_and_interrupts_once`) is strong: it catches `>=`, cumulative-total and first-total mutants as well as double interrupts.
- The tool-scope reserve has no real suspension point, so two concurrent tool calls cannot overshoot `max_live_turns`. Late acceptance of a plain spawn, a goal and a continue is owned and interrupted once, with `problem=None` (D-35). A late goal gives "GOAL cancels: 1, budget sets: 0, status: interrupted, problem: None", closes its stream in order and its watcher exits.

FINDINGS (ranked)

R-E1 [Blocker] [concurrency] vidbyte/harnesses/native/codex/host.py:629 — A review whose caller is cancelled during the D-23 read-back is registered but never watched or interrupted, so it stays RUNNING forever and its thread stays busy
  Evidence: `_accept_review` registers the turn (line 627 `register_turn_notifications`, line 628 `track`) and then awaits `_read_back` (line 629). `watch` (line 643) and the late `_stop` (line 645) come after that await, with no try/finally. In the probe the fake held `thread/read` with includeTurns, the caller was cancelled, and the fake then completed the turn. Output: "caller got CancelledError / registered snapshot: inProgress / turn/interrupt sent: 0 / after Codex completed it, wait(1s) -> inProgress / continue on that thread -> codex.session_busy / usage turns listed: 0".
  Failure: The review keeps spending and is never interrupted. Its notifications are routed but nobody reads them. Its snapshot never reaches a terminal state, so `require_idle` refuses every later continue or review on that thread until the host closes, and its usage never reaches the ledger. The AC-32 review test cancels only during `review/start`, so this window is untested.
  Smallest fix: Make the read-back cancellation-safe: `try: stored = ... await self._read_back(...) except BaseException: turn.watch(client, self._on_turn_event, self._stop); self._stop(turn, None); raise`. Alternatively, run the read-back and watch from `self._spawn_task` for the non-late path as well, and return the handle once the task has registered the turn. Add a test that holds `thread/read` and cancels the caller.
  Spec IDs: INV-11, INV-14, INV-15, INV-16, INV-24, D-23, AC-32

R-E2 [Blocker] [correctness] vidbyte/lib/dataclasses/codex_host.py:205 — `output_schema` is only checked as "a type or a mapping", so a bad schema fails after `thread/start` already created a thread, and one shape escapes as a raw pydantic error
  Evidence: The record accepts any `type` and any `Mapping` (line 205-206). The real conversion happens in `CodexParamsTranslator.turn_start` (wire.py:222, 231), which is called from `_start_turn` (host.py:531) after `_open_thread` (host.py:240). Probe through the fake host: `output_schema=<dataclass type>` gives "vidbyte.lib.errors.base.ConfigurationError | output_schema must be a Pydantic BaseModel subclass or a dict, got 'type'. / thread/start sent: 1 turn/start sent: 0". `output_schema={"type": "object", "x": object()}` gives "pydantic_core._pydantic_core.PydanticSerializationError | Unable to serialize unknown type: <class 'object'> / thread/start sent: 1 turn/start sent: 0".
  Failure: This breaks INV-26 ("An invalid record never reaches Codex") because a stored thread is created and orphaned. It breaks INV-8 ("No SDK exception … or pydantic ValidationError escapes") because a pydantic_core exception reaches the caller, and through the tools it bypasses INV-10's mapping. The ConfigurationError does not name the thread that was created (EC-62). Launch fails the same way on its first item, and continue fails after `thread/resume`.
  Smallest fix: Without a new class, build the output schema before preflight, next to `input_items`/`_tool_bridge` (host.py:234-235, 256, 411-412). The comment at host.py:232-233 already promises this for the prompt and tools. Also wrap `PydanticSerializationError` in `turn_start` as `ConfigurationError("output_schema …")`. Or, at the record level, require `issubclass(BaseModel)` for types and `json.dumps`-ability for mappings in the existing `_reject_*` check.
  Spec IDs: INV-8, INV-10, INV-12, INV-26, EC-62, G-2

R-E3 [Major] [concurrency] vidbyte/harnesses/native/codex/host.py:421 — Cancelling a launch after k items started leaves those k turns running and outside the tool scope, so the live-turn cap is exceeded
  Evidence: Only `except CodexAgentError` (line 421) interrupts `started`. A `CancelledError` raised at line 417/418 skips it. The launch tool then releases its slots in `finally` (delegation.py:72-73) and never calls `own` (line 74). Probe with `CodexHostTools(host, max_live_turns=2)`, holding the second item's `thread/start` and cancelling: "turn/start sent: 1 turn/interrupt sent: 0 / scope live: 0 reserved: 0 / spawn 0 success / spawn 1 success / turns inProgress on the fake: 3 with max_live_turns=2". A second probe cancelled during the second item's `turn/start`: the in-flight item was adopted and interrupted once (correct), but turn-1 stayed inProgress with 0 interrupts.
  Failure: Paid turns keep running with no owner-facing handle and no interrupt, and the tool scope undercounts, so the INV-32 cap is breached.
  Smallest fix: Change line 421 to `except BaseException as exc:`. Interrupt each started turn with `self._stop(turn, None)`. Re-raise `CancelledError` unchanged and keep today's message rewrite only for `CodexAgentError`.
  Spec IDs: INV-37, INV-11, INV-32, T-1

R-E4 [Major] [concurrency] vidbyte/harnesses/native/codex/host.py:193 — If `__aexit__` is cancelled while it awaits the close interrupts, the client is never closed and a retry is a no-op, so the app-server process and the host executor leak
  Evidence: `_closing = True` is set at line 180. Steps 4–6 (`close_goal_stream`, `connection.close()`, lines 198-200) come after `await asyncio.wait(stops)` (line 193) with no try/finally. A second `__aexit__` returns at line 178. Probe holding `turn/interrupt` and cancelling `__aexit__`: "client.close() calls: 0 / after a second __aexit__, client.close() calls: 0 / executor shut down: False".
  Failure: A Ctrl-C or `asyncio.run` shutdown during the close-interrupt phase, which can last up to `CODEX_HOST_CLOSE_INTERRUPT_SECONDS`, leaves the codex process, its reader and monitor threads, and 32 workers alive with no way to close them. That violates INV-7's "close always finishes" order.
  Smallest fix: Wrap lines 188-199 in `try:` and put `for turn in ended: turn.close_goal_stream(...)` and `await connection.close()` in `finally:`. Use `asyncio.shield(connection.close())` if the second await must survive the same cancellation.
  Spec IDs: INV-7, NFR-9, EC-69

R-E5 [Major] [concurrency] vidbyte/harnesses/native/codex/host.py:274 — Continue and review release the thread's reservation when their caller leaves, even though the handed-over start is still in flight, so a second continue starts a second turn on the same thread
  Evidence: `finally: self._registry.release(thread_id)` (continue at line 274-275, review at line 452-453) runs as soon as `connection.start` re-raises (connection.py:223-229). The turn is registered only later, by `on_late`. Probe holding the first continue's `turn/start`, cancelling it, then continuing again: "second continue sent thread/resume: 2 / second continue returned a handle: turn-3 / turn/start count: 2". The late first turn was still interrupted once with problem None.
  Failure: INV-24's purpose is "one running turn per thread … raises codex.session_busy before any request". Here the host sends a second `thread/resume` + `turn/start` while its own first start is still pending. The same applies after `codex.api_error` for the 300 s bound (EC-36), which is exactly when a caller retries.
  Smallest fix: Keep the reservation while a start is handed over. Release it in the late path (`_adopt_late_turn`/`_adopt_late_review` after `track`, or in a no-accept `_post_late` outcome) rather than in `finally` on CancelledError or TimeoutError. A done-callback on the handed-over future that posts `release` also works.
  Spec IDs: INV-24, INV-11, EC-36, EC-67

R-E6 [Major] [test-quality] tests/features/codex_host/test_codex_host_failures.py:77-86 — The late-acceptance tests check only the status, so two INV-11/D-35 mutants survive the whole pack
  Evidence: The pack baseline is 101 run, 0 failed. Mutant M1 makes `_adopt_late_goal` skip its `_stop` and cancel, so a late goal is never cancelled: 0 failures. Mutant M2 labels a late turn `CODEX_TURN_TIMED_OUT` instead of `None`: 0 failures. `_assert_owned_and_interrupted_once` asserts `snapshot.status.value == "interrupted"` (line 86) and never `problem is None`. No test drives a goal start whose caller leaves.
  Failure: D-35 ("ends INTERRUPTED with no problem") and INV-11's goal branch ("cancel_goal_operation for a goal") could regress silently. Both hold today: I probed them directly.
  Smallest fix: Add `self.assertIsNone(snapshot.problem)` to the helper, and add one test that holds `thread/goal/set` (or the goal start) and cancels the spawn caller, then asserts one goal cancel and a `None` problem.
  Spec IDs: INV-11, D-35, EC-36, EC-67, AC-32

R-E7 [Major] [correctness] vidbyte/harnesses/native/codex/wire.py:569 — A mapping `output_schema` is only JSON-parsed and never validated, so `codex.schema_violation` can never fire for it, including every spawn-tool schema
  Evidence: `OutputSchemaFormatter.validate` (vidbyte/providers/output_schema.py:86-105) validates only `BaseModel` subclasses and returns `(parsed, None)` for a Mapping. Inline check: `validate('{"y": 1}', {"type":"object","required":["x"],...})` returns `({'y': 1}, None)`. The spawn tool always passes its `output_schema` as a Mapping. The AC-13 test (test_codex_host_turns.py:359-379) uses only the pydantic `ReadmeSummary`.
  Failure: INV-21's "one that does not validate stays COMPLETED with codex.schema_violation" is false for mappings. Non-conforming JSON is returned as `result.structured`, and only Codex's own `outputSchema` enforcement stands between the caller and bad data.
  Smallest fix: In scope: amend the INV-21 text and the `CodexSpawnRequest.output_schema` docstring to say that a mapping is enforced by Codex's `outputSchema` and only parsed locally, and add a test that pins this behaviour. A real JSON-Schema validator needs a dependency (NG-7) or a new helper, so it is [scope-adding] and belongs in a follow-up.
  Spec IDs: INV-21, EC-32, AC-13

R-E8 [Major] [test-quality] vidbyte/tools/builtins/codex/delegation.py:70-73 — No test proves that the launch tool frees its cap slots when the launch fails
  Evidence: Mutant M3 makes `LaunchCodexSubagentsTool._perform` release only on success: 0 failures in the pack. The slot test `test_cancellation_propagates_and_frees_the_reserved_slot` (test_codex_host_tools.py:187-198) covers the spawn tool only.
  Failure: A regression there would leak `len(prompts)` reserved slots on each failed launch, and the scope would eventually refuse every spawn with `codex.session_busy`.
  Smallest fix: Make the existing slot test table-driven over spawn and launch, with a failing launch (`thread/start` error) followed by a launch that must fit the cap.
  Spec IDs: INV-32, INV-10, T-1

R-E9 [Minor] [concurrency] vidbyte/harnesses/native/codex/host.py:558-563 — A second cancellation during goal-start cleanup skips `finish()` and `unregister_goal_operation`
  Evidence: The cleanup awaits `cancel_goal_operation` under `suppress(CodexAgentError)` only (line 559-560). A `CancelledError` delivered during that await, for example a second cancel from a TaskGroup or from `asyncio.run` shutdown, skips lines 561-562. This finding comes from reading the code; I did not probe it.
  Failure: The goal state stays registered with openai-codex, so the SDK refuses later turns on that thread and the goal stream is never released (INV-25 "the thread's goal route is released").
  Smallest fix: Put `state.finish()` and `connection.client.unregister_goal_operation(state)` in a `finally:` around the cancel await.
  Spec IDs: INV-25, EC-74

R-E10 [Minor] [correctness] vidbyte/harnesses/native/codex/connection.py:316 — At close, `shutdown(cancel_futures=True)` makes a still-queued call's caller receive `CancelledError` instead of `codex.process_exited`
  Evidence: A queued `executor.submit` future is cancelled by the shutdown. `wrap_future` → shield → `wait_for` (line 222) then raises `CancelledError` into a caller that was never cancelled, and `except asyncio.CancelledError` (line 223) re-raises it. This needs every host worker to be blocked at close (EC-70). I found it by reading the code and did not probe it.
  Failure: A caller that was not cancelled sees cancellation. In a TaskGroup or under `asyncio.run` that looks like the task itself was cancelled, which masks the real cause (G-2).
  Smallest fix: In `start`/`call`, when `CancelledError` arrives and `future.cancelled()` is true while `self._closing or self._dead.is_set()` and `asyncio.current_task().cancelling() == 0`, raise `CodexErrorMapper.process_exited(operation, thread_id)` instead.
  Spec IDs: INV-8, INV-7, EC-70

R-E11 [Minor] [correctness] vidbyte/harnesses/native/codex/host.py:383-386 — `interrupt_codex_turn` ignores `stop_sent`, so a turn already stopped by its timeout, its cap or late acceptance gets a second `turn/interrupt`
  Evidence: Line 383 returns early only when there is a snapshot. A turn whose first interrupt is in flight still has `snapshot is None`, so a rebuilt handle (INV-23) or the interrupt tool sends another one.
  Failure: D-35 says the late-acceptance interrupt "stays the turn's only interrupt". A second interrupt that races the turn's end can surface Codex's "no active turn" error to a caller who asked for a no-op.
  Smallest fix: `if turn.snapshot is not None or turn.stop_sent: return`.
  Spec IDs: D-35, D-7, AC-16

R-E12 [Minor] [test-quality] vidbyte/harnesses/native/codex/host.py:497 — The boundary mutants for the launch `limit` and the interrupt's `stop_sent` survive
  Evidence: Mutant M4 changes `len(prompts) > limit` to `>=`: 0 failures. The threads test (test_codex_host_threads.py:135-137) uses only limit 0, True, and 3 prompts over 2. Mutant M5 removes `turn.stop_sent = True` at line 385: 0 failures.
  Failure: Off-by-one refusals at `len == limit`, or a cap interrupt plus a `budget_exhausted` label after a user interrupt, would ship unnoticed.
  Smallest fix: Add a `len(prompts) == limit` success row. Add one turn test where the user interrupts and then usage crosses the cap, and assert one interrupt and `problem=None`.
  Spec IDs: INV-37, AC-16, D-7

R-E13 [Minor] [performance] vidbyte/harnesses/native/codex/turns.py:95 — Finished turns keep their `items` list after the snapshot has copied the items into `result.items`
  Evidence: `observe` appends every completed item (line 95). `finish` (lines 127-135) keeps `self.items`, and the registry holds each `CodexLiveTurn` until close.
  Failure: Item memory is doubled for the host's lifetime. EC-65 accepts one registry entry per turn, not a second copy of every item.
  Smallest fix: Set `self.items = []` (and drop `completed`) in `finish` once the snapshot is set.
  Spec IDs: EC-65, NFR-9

VERIFIED CLAIMS
- S3 says "101 passed" for the pack. HELD: 101 passed in 7.26s.
- The tests are unchanged between 099fac83 and HEAD 3ebefd11. HELD: `git diff --stat 099fac83 3ebefd11 -- vidbyte tests` is empty.
- Late acceptance owns spawn, goal and continue turns and interrupts each once, with problem None (D-35). HELD by probe. It did NOT HOLD for the review read-back window (R-E1) or for a launch's already-started items (R-E3).
- "Cancellation frees the reserved slot in callers' finally". HELD for the slots, but the cap is still breached through R-E3.
- INV-24, two concurrent continues. HELD in the test, but did NOT HOLD on the cancel and timeout path (R-E5).
- INV-21 structured-output violation. HELD for pydantic models and did NOT HOLD for mappings (R-E7).
- INV-8 and INV-26 on spawn. Did NOT HOLD for a bad `output_schema` (R-E2).
- Death handling, including S3 deviation 2 (fixed text, once-only post). HELD in every probed window.
- The EC-78 test is not vacuous. HELD: the mutant failed 3/3 runs.
- The goal update-after-completion test (test_codex_host_review_goals.py:181-190) is deterministic for a correct implementation. HELD: its later `goal_status == "complete"` assertion catches a run that ends at its first completion.
- The output-cap test catches `>=`, cumulative-total and double-interrupt bugs. HELD.
- The router mirrors the SDK `_default_approval_handler` (accept for command and fileChange approvals, `{}` otherwise). HELD (connection.py:99-116). Approvals are not reachable through a shorter path.

COMMANDS RUN
- `PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` → `101 passed in 7.26s`
- `git diff --stat 099fac83 3ebefd11 -- vidbyte tests` → (empty); `git diff --stat origin/main...099fac83 -- vidbyte` → `27 files changed, 4627 insertions(+), 4 deletions(-)`
- `git show 099fac83:<path> | cat -n` for host.py, connection.py, turns.py, wire.py, codex_host.py, delegation.py and providers/output_schema.py (line anchors above)
- Inline probes (`$PY -P -` heredocs that subclass `tests.features.codex_host.codex_host_support.HostTestCase` over the in-memory fake, with nothing written to disk):
  - review with `thread/read` held, then cancel → `turn/interrupt sent: 0 … wait(1s) -> inProgress … continue -> codex.session_busy` (R-E1)
  - spawn with a bad `output_schema` → `ConfigurationError … thread/start sent: 1` and `PydanticSerializationError … thread/start sent: 1` (R-E2)
  - `CodexHostTools(max_live_turns=2)`: launch, second `thread/start` held, cancel → `turns inProgress on the fake: 3 with max_live_turns=2` (R-E3)
  - `turn/interrupt` held, `__aexit__` cancelled → `client.close() calls: 0 … executor shut down: False` (R-E4)
  - continue with `turn/start` held, cancel, continue again → `second continue returned a handle: turn-3 / turn/start count: 2` (R-E5)
  - late goal → `GOAL cancels: 1 budget sets: 0 status: interrupted problem: None goal_status: paused`; late continue → interrupted once, problem None
  - death during `turn/start`, goal, close, and idle → as listed under GETS RIGHT
  - `CodexParamsTranslator.turn_start` with a mapping that holds `object()` → `RAISES pydantic_core._pydantic_core.PydanticSerializationError`
  - `OutputSchemaFormatter().validate('{"y": 1}', <schema requiring x>)` → `({'y': 1}, None)`
- Mutation sweep (in-memory monkeypatch, one subprocess per mutant, unittest loader over `tests.features.codex_host.test_codex_host_*`): baseline `ran 101, failed 0`; M1 late goal not stopped → 0 failed; M2 late label timed_out → 0; M3 launch slots released on success only → 0; M4 limit `>=` → 0; M5 no `stop_sent` on interrupt → 0; M6 review without read-back → 2; M7 cap `>=` → 6; M8 continue reservation not released on failure → 7; EC-78 no-withdrawal mutant → failed 3/3 runs
