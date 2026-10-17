# S1 spec review: codex-host (round 2)

- **Spec reviewed:** `docs/spec/codex-host/spec.md` r2 (commit `b38d573a`, 1,509 lines). Worktree HEAD is `23bf163c` on `feat/codex-host`, base `678136bd`.
- **Scope:** the round-2 Focus, plus the sections that depend on it (§4, §5, §6, §13, §14, §15). The Focus is:
  - §8.1 D-1, D-3, D-6, D-8, D-13, D-16, D-23, D-26, D-27 and D-31, with §8.2, §8.4 and §8.5;
  - §9.1–§9.4, §10 T-3 and T-6, and §12.1–§12.5;
  - INV-7, INV-11, INV-25, INV-28 and INV-29;
  - EC-63 and EC-68–EC-74.
- **Method:** read-only.
  - No gate, test, install or venv was run, and `codex` was run only with `--version`.
  - The §11 blob-hash command was run on `vidbyte/harnesses/README.md` in Git Bash and in Windows PowerShell 5.1.
  - openai-codex 0.162.1 was read from the vidbyte-cli venv.

VERDICT: SOUND WITH FIXES — r2 resolves all 13 round-1 findings in its text, but three of its new mechanisms stop short: the USER rejection misses threads whose effective reviewer is `user`, close leaves dynamic tool calls running, and the late-acceptance path is looser than the normal path. Each needs only a few lines of spec.

WHAT THE SPEC GETS RIGHT
- **The shared-file contract is exact. Do not touch it.**
  - §12.5's two blocks are byte-equal to request.md §C's (its blocks 1 and 2; block 0 is the re-entry card). The native block is 911 LF bytes, SHA `0374a2c8…`.
  - The §11 command prints `4075c323b7b373cabc05d1fb8485828bb440b5e1d630f4e4b7236df904b47e88` for `HEAD:vidbyte/harnesses/README.md` in both shells. That is the same hash the pipe form gives in Git Bash.
  - The rows match the files. REPO_MAP has its heading at line 147, the paragraph at 149 and `##### …/stores/` at 151, as row 27 says. The README is 8,605 characters (8,625 bytes), as row 28 says.
- **The `codex_host` records module (D-26, row 6) is lint-clean as written.**
  - Importing the private helpers from `vidbyte/lib/dataclasses/codex.py:55-90` is allowed: PLC2701 is not among the selectors in `lint/core/ruff.py`, C008 flags definitions, not imports, and A006 sees only lib-to-lib edges.
  - No `vidbyte/lib/dataclasses/__init__.py` insert is needed, because recent modules (`coding`, `jev`, `code_search`, `context_items`, `model_configs`) are not re-exported there either.
  - S020 has nothing to list. There is no README in `vidbyte/lib/dataclasses/`, and `vidbyte/lib/README.md` has no File Index.
  - The list-literal `__all__` and leaving out the `CodexClientSettings` import (which would trip F401) are both right.
- **The death flag and the fixed-text rule (D-27, EC-72, EC-73, row 10) close the leaks they target.**
  - `fail_all` fills response waiters before the global queue (`_message_router.py:345-351`), so EC-72's short window before the flag is real, and the spec states it honestly.
  - `TransportClosedError` from `_read_message` embeds `stderr_tail` (`client.py:907-910`). Row 10 raises the mapped error `from None`, which keeps that text out.
  - The goal start's plain `CodexError` after 30 s (`client.py:636-641`) is correctly mapped to `codex.api_error`.
- **Typed late acceptance and the goal-budget guard are sound.**
  - **Typed starts lose no events on late registration.** `_start_turn` runs inside `pending_turn`, and `prepare_turn(for_handle=False)` installs the default consumer before any pruning (`client.py:677-679`, `_message_router.py:145-175`).
  - **INV-25 and EC-74 guard the requested budget; they are not scope.** If a budget request's effect is unknown and the caller holds no handle, cancelling the goal is the only safe outcome.
  - **D-31's 240 s clamp starts inside the bridge's 300 s clock** (`tools.py:148-150`).

FINDINGS
R-1 [Major] [L7] §6.1 INV-28 / §8.1 D-16 / §15 A-7 / §10 T-6 — USER is refused only when the caller names it, so a thread whose effective reviewer is `user` still has every escalation approved, even though Codex reports that reviewer on every start and resume
  Evidence:
  - **The spec:**
    - INV-28: "`thread/start` sends `approval_policy` and `approvals_reviewer` as given", and "Resume, fork and `turn/start` send approval fields only when the caller set them."
    - §9.1 `CodexSpawnRequest`: "When either field is set, `thread.approval_mode` and `turn.approval_mode` must both be PROVIDER_DEFAULT". So `approval_policy` alone is valid.
    - `CODEX_HOST_USER_REVIEWER_TEXT` ends "…or leave it unset."
    - §9.2 tool row 5: the continue tool's overrides "are `spawn_defaults` with every continue-rejected field cleared". The default `spawn_defaults` is `CodexSpawnRequest()`, which has no approval fields.
    - `list_codex_threads` with the default `source_kinds` lists interactive threads only (EC-66).
    - A-7: "the assumption is that a thread keeps the reviewer it started with … for example for a thread started outside the host with a `user` reviewer and then continued here: those requests reach the host and get the SDK's `accept` fallback". T-6 files this under "A-7 wrong".
  - **openai-codex:**
    - `ThreadStartResponse`, `ThreadResumeResponse` and `ThreadForkResponse` (`generated/v2_all.py:12458`, `:12363`, `:12288`) each carry a required `approvals_reviewer` ("Reviewer currently used for approval requests on this thread") and a required `approval_policy`.
    - When no reviewer is sent, the thread takes Codex's configured default (`v2_all.py:10782`: "[UNSTABLE] Optional default for where approval requests are routed for review").
    - The SDK itself never sends a policy that routes approvals to the client. `ApprovalMode` maps only to (on-request, auto_review) or (never, none) (`_approval_mode.py:28-35`).
  Failure:
  - **Spawn.** A developer wants a human gate, which was round 1's scenario, and follows the rejection text by writing `CodexSpawnRequest(approval_policy=UNTRUSTED)`.
    - `thread/start` sends `approvalPolicy: untrusted` with no reviewer, so the thread takes Codex's configured default.
    - Wherever that default is `user`, every command reaches the host and INV-28 answers `accept`.
    - That is round-1 R-5's exact failure without the word USER.
  - **Continue through the tools, with default settings.** A model lists threads, which are interactive ones by default, then continues one.
    - `thread/resume` sends no reviewer, so the thread keeps `user`.
    - Every escalation in the new turn is approved, where Codex itself would have asked a human.
    - T-2's "stored or default posture" and T-6's "A-7 wrong" both understate this. It is reachable by design, not only when an assumption fails.
  Smallest fix: This is not scope-adding: it applies D-16's own rule, that USER fails closed, to the reviewer Codex reports.
  - **The check.** After `thread/start` and `thread/resume`, and before any `turn/start` or goal start, read the response's `approvalsReviewer` and `approvalPolicy`. If the reviewer is `user` and the policy is not `never`, start nothing and raise D-16's rejection, naming the thread id.
  - **Continue's next step** is `overrides=CodexSpawnRequest(approvals_reviewer=AUTO_REVIEW)`, which `thread/resume` accepts (`ThreadResumeParams.approvals_reviewer`, `v2_all.py:5987`).
  - **Fork and review.** Fork starts no turn, and the next continue checks again. `start_codex_review` sends no resume, so a review is A-7's only remaining residual.
  - **Tests.** Add one EC and one AC. §13's fake already builds these responses from the real models.
  - **Fallback.** If the orchestrator rules the check a new control, then:
    - state in T-2, T-6 and A-7 that the accept fallback is reachable by design through both paths;
    - make the rejection text say to set `approvals_reviewer` whenever `approval_policy` is set.

R-2 [Major] [L5] §6.1 INV-7 / §12.3 row 15 — Close never cancels running dynamic tool calls and can strand goal watchers, so Vidbyte tools keep running after `__aexit__` returns
  Evidence:
  - **The spec:**
    - Neither INV-7's four steps nor row 15's "Close (INV-7)" has a tool step. The four steps are: timers and routing, interrupts, the close thread, the executor.
    - D-18 builds one `CodexToolCallHandler` per tool-using thread through the new `CodexToolBridge.handler()`, and no section ever closes those handlers.
  - **The sibling:**
    - `vidbyte/agents/codex/transport.py:198-213` `_attached_tools`: "cancel unfinished tool calls before the app-server connection closes", then `handler.close()` in its `finally`.
    - `vidbyte/agents/codex/tools.py:174-177`: `CodexToolCallHandler.close()` "Cancels tool coroutines still running when the connection closes".
    - `handle` (`tools.py:132-172`) holds the SDK reader on `future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)`, and answers a cancelled call with a failed result.
  - **openai-codex:**
    - The reader answers server requests inline (`client.py:863-881`).
    - `next_goal_notification` is a bare `Queue.get()` (`_goal.py:113-117`), and `unregister_goal_operation` never wakes it.
    - `fail_all` fails only goal states that are still registered (`_message_router.py:341-350`).
  Failure:
  - **A tool call is running at close.** A thread with `tools` is in a tool call (EC-68) when the host closes.
    - The close interrupts are written, but their responses cannot be read, so close always waits out `CODEX_HOST_CLOSE_INTERRUPT_SECONDS`.
    - `client.close()` ends the process, but the tool coroutine keeps running on the developer's loop for up to 300 s after `__aexit__` returned. A WRITE tool can still be editing files or calling paid services, and its answer goes to a dead pipe.
    - An `item/tool/call` that arrives between step 1 and the process exit is still dispatched to a registered handler.
  - **Goal watchers.** An implementer may read step 1's "stops routing for every turn" as calling `unregister_goal_operation` for a goal run.
    - The goal watcher, blocked in `next_goal_notification`, then misses both the step-2 cancel's notifications and `fail_all`.
    - One daemon thread stays blocked forever per goal run per closed host.
  Smallest fix:
  - **A new first close step.** Add it to INV-7 and row 15: remove every thread's tool handler from `CodexServerRequestRouter`, so later calls get `CODEX_UNREGISTERED_TOOL_TEXT`, and call `close()` on each handler, as `_attached_tools` does. The reader then answers the pending calls at once and can read the interrupt responses.
  - **Goal runs stay registered.** Say that step 1 does not unregister a goal run. Its watcher ends on the cancel's notifications, or on `fail_all` when the process exits.
  - **Test.** Add the tool case to AC-33. §13's seam, in which a test calls the router from a worker thread, can drive it.

R-3 [Major] [L5] §6.1 INV-11 / §12.3 rows 12 and 15 / AC-32 — The late-acceptance path is looser than the normal path: a queued start still goes out, a late review skips D-23's read-back, acceptance during close has no rule, and the bound's namespace is ambiguous
  Evidence:
  - **The spec:**
    - Row 12: "The host awaits that future through `asyncio.shield` under the same bound, and keeps it so that it can attach the INV-11 late-acceptance callback".
    - Row 15: "a done-callback on the submitted future posts to the loop, which registers any turn Codex accepted and sends it one interrupt."
    - D-23: "the review thread is read back with its turns to close the registration race".
    - INV-6: after close, "Every turn is terminal by then (INV-7)". Row 12 shuts the executor down "with `wait=False, cancel_futures=True`".
    - §13 says the bound is "read from the connection module's namespace at call time". Row 12, however, has the host, not the connection, await the shielded future.
  - **openai-codex:**
    - `async_client.py:308-312` awaits its `_TURN_START_EXECUTOR` future with no shield, so a cancelled caller withdraws a start that has not begun. `Future.cancel()` succeeds only before the call runs.
    - A raw `review/start` opens no pending turn, so `_prune_turn_events` drops its early events (`_message_router.py:196-206`).
  - **Python 3.11:** `submit` on a shut-down executor raises `RuntimeError('cannot schedule new futures after shutdown')` (`concurrent/futures/thread.py:167`).
  Failure:
  - **(a) Queued start.**
    - Every `CODEX_HOST_WORKER_THREADS` worker is blocked (EC-68, EC-70), so a spawn's `turn/start` waits in the queue.
    - The caller is cancelled, or gets `codex.api_error` at 300 s.
    - The shield keeps the future, so when a worker frees up, the host sends a paid `turn/start` that nobody wants, then interrupts it.
  - **(b) Late review.** A late review is registered without D-23's read-back. A review that completed before registration stays RUNNING, and its thread answers `codex.session_busy` until close.
  - **(c) Acceptance during close.**
    - A start that returns after INV-7 step 1 registers a RUNNING turn that close never finalizes, which breaks INV-6.
    - After step 4, its interrupt goes to the shut-down executor, and the `RuntimeError` surfaces in a loop callback.
  - **(d) The bound.** An implementer may put the shielded `wait_for` in `host.py` with an imported constant. That ignores AC-32's patch on the connection module, so the S2 test waits the real 300 s.
  Smallest fix: In rows 12 and 15:
  - On cancel or timeout, call `future.cancel()` first, and attach the callback only when it returns False, which means the call is already running.
  - A late `review/start` gets D-23's read-back after it registers.
  - Once close has begun, the callback registers the turn as FAILED with `codex.process_exited` and sends nothing. The closing process ends the turn (A-1).
  - Put the shielded, bounded await in `CodexConnection`, so the bound is read where §13 says it is.

R-4 [Minor] [L5] §6.1 INV-25 / EC-74 — The budget-failure cancel skips the SDK's own goal cleanup, so a rejected pause leaves the thread's goal route registered for the host's lifetime
  Evidence:
  - **The spec:**
    - INV-25: "If the budget request itself fails or outlives its bound, the goal is cancelled the same way before the mapped error propagates (EC-74)".
    - Row 15: "A failed or timed-out goal budget request cancels the goal".
    - Neither names a bound for the cancel or any cleanup after it.
  - **openai-codex:**
    - `cancel_goal_operation` pauses the goal, swallowing any error, then interrupts it (`client.py:572-578`).
    - Both of the SDK's own failure paths then call `state.finish()` and `unregister_goal_operation(state)` (`client.py:643-648`, `async_client.py:273-282`).
    - A goal state finishes on its own only after a terminal goal status plus a completed turn (`_goal.py:79-84`).
    - While a goal state is registered, every turn-scoped notification for its thread goes into it (`_message_router.py:300-309`), and `turn/start` is refused (`client.py:667-671`).
  Failure:
  - **The pause fails.** The budget `thread/goal/set` fails, the pause fails too (for example, Codex rejects it), and the interrupt lands.
    - The goal state never finishes.
    - For the rest of the host's life, every continue on that thread fails with "thread has an active goal operation", and the events of a review on that thread are swallowed.
  - **Timing.** The cancel runs under the normal 300 s call bound, so on a silent server, spawn raises only after about 600 s.
  Smallest fix: State two things:
  - the EC-74 cancel is bounded by `CODEX_HOST_CLOSE_INTERRUPT_SECONDS`, like close's interrupts;
  - the cancel is followed by `state.finish()` and `unregister_goal_operation(state)`, mirroring `client.py:643-648`.

  §13's fake already lists `unregister_goal_operation`.

R-5 [Minor] [L1] §8.1 D-16 / EC-63 — The orchestrator's R-5 decision names the unsupported-combination code, but r2 raises a code-less `ConfigurationError`
  Evidence:
  - **The spec:** D-16 and EC-63 specify a "`ConfigurationError` with `CODEX_HOST_USER_REVIEWER_TEXT`". INV-10: "`ConfigurationError` and `ToolExecutionError` use the code `configuration.invalid_argument`."
  - **The decision:** reject USER "with the unsupported-combination code and a next step naming the later `set_codex_approval_handler`".
  - **The repo:**
    - `vidbyte/lib/enums/failure.py:27` defines `CONFIGURATION_UNSUPPORTED_COMBINATION = "configuration.unsupported_combination"`, which nothing in `vidbyte/` uses yet.
    - `ConfigurationError` has no code field, only `details` (`vidbyte/lib/errors/base.py:59-66`, `:235`).
  Failure: No caller ever sees `configuration.unsupported_combination`. The next-step half of the decision holds. Only developer code can reach this rejection, because D-12 keeps approval fields out of the tool parameters. So this is a gap in fidelity to the decision, not in behaviour.
  Smallest fix: Raise `ConfigurationError(CODEX_HOST_USER_REVIEWER_TEXT, details={"code": FailureCode.CONFIGURATION_UNSUPPORTED_COMBINATION.value})`. Alternatively, record in D-16 that the message alone carries the decision, and have the orchestrator confirm.

VERIFIED CLAIMS:
- **Round-1 R-1 (S054)** — held.
  - §12.4's S054 bullet and row 17's `SPAWN_GOAL_BUDGET_DESCRIPTION` are present.
  - No new §8.5, §9.3 or row-17 name both matches ruff S105's name pattern and is assigned a string.
  - `CODEX_HOST_MIN_TOKEN_LIMIT` matches the pattern but is an int, which S105 ignores.
- **Round-1 R-2 (fixed texts)** — held, byte-exact (see WHAT THE SPEC GETS RIGHT).
- **Round-1 R-3 (single reader)** — held. EC-68, INV-29 and the docstrings in rows 6 and 25 are present, and `client.py:863-881` answers server requests on the reader.
- **Round-1 R-4 (Windows close)** — held in text: the INV-7 order, the A-1 launcher chain and EC-69 are all present. Close still omits tool calls (R-2 here).
- **Round-1 R-5 (USER)** — held for an explicit USER. Two gaps remain: the effective reviewer is never checked (R-1 here), and the error carries no code (R-5 here).
- **Round-1 R-6 (executor)** — held: a host-owned pool, no `to_thread`, a close thread, and `shutdown(wait=False, cancel_futures=True)`. The late path still has gaps (R-3 here).
- **Round-1 R-7 (clamp)** — held. 240 is below 300, and the bridge's clock starts first (`tools.py:148-150`).
- **Round-1 R-8 (hash)** — held (see the §11 entry below).
- **Round-1 R-9 (placement)** — held (see WHAT THE SPEC GETS RIGHT).
- **Round-1 R-10 (SDK facts)** — held. §13 pins the `openai_codex.client.CodexClient` path, the §12.4 method parameters, `max_attempts`, and `_GoalStreamCursor.process`.
- **Round-1 R-11 (review read-back)** — held for the normal path, but not carried to the late path (R-3 here). A-14's schema text is real:
  - `ThreadReadParams.include_turns`: "include turns and their items from rollout history";
  - `Turn.items_view` defaults to `full`.
- **Round-1 R-12 (death flag, goal timeout)** — held. The mapper's first branch checks the death flag, and EC-73 matches `client.py:636-648`.
- **Round-1 R-13 (experimental-API text)** — held. INV-29 and row 7 keep `translate`'s own check, and the host uses `CODEX_HOST_EXPERIMENTAL_API_TEXT`.
- **(a) Executor and close chain** — held as disclosed, with one narrow addition.
  - **`shutdown`.** `shutdown(wait=False, cancel_futures=True)` cancels only queued calls and returns at once (`concurrent/futures/thread.py:216-235`).
  - **Workers outlive close.** They are non-daemon, and `_python_exit` joins them before interpreter exit (`thread.py:23-37`). A blocked worker is released only by a response, or by `fail_all` when the reader dies.
  - **The bounds bound waits, not work.** The 5 s and 10 s values limit how long `__aexit__` waits, so it returns in about 15 s at worst, but they do not stop the blocked calls.
  - **`client.close()` bounds itself to about 3 s** (`client.py:283-302`), with one exception.
    - `proc.stdin.close()` (`:292`) has no timeout. It can block behind a worker stuck in `_write_message` (`:899-901`) on a full pipe to a hung server.
    - Terminate is then never reached, and interpreter exit waits for the app-server, as in EC-69.
    - EC-69 discloses only the npm case. The full-pipe case is narrow enough to leave as is.
  - **Pool size.** 32 is the standard library's default ceiling, which `_TURN_START_EXECUTOR` (`async_client.py:54`) gets by passing no `max_workers`.
- **(b) INV-11 against the router and the single reader** — held for typed starts. The interrupt is sent after the start response, so the turn exists, and an interrupt for a turn that already finished fails harmlessly.
  - **Raw `review/start`** is exposed to `_prune_turn_events` (R-3).
  - **A long tool call** (EC-68) can delay a healthy `turn/start` response past 300 s. Late acceptance then interrupts a turn Codex accepted promptly, which matches the `codex.api_error` the caller already got.
- **(c) INV-25 and EC-74** — a guard, not scope, and cancelling is correct. The SDK's own cancelled-goal cleanup is: cancel, then `state.finish()`, then `unregister_goal_operation` (R-4).
- **(d) Round-1 R-5's error type, code and next step:**
  - **Type and code.** It is a `ConfigurationError` with no code (R-5).
  - **Next step.** The text names `set_codex_approval_handler`.
  - **Changing a thread's reviewer.** `thread/resume` and `turn/start` accept an `approvalsReviewer` override (`v2_all.py:5987`, `:12544`), so a caller can change a resumed thread's reviewer.
- **(e) Round-1 R-9** — held (see WHAT THE SPEC GETS RIGHT).
- **(f) S054** — held (see the round-1 R-1 entry).
- **(g) The §11 hash command** — held.
  - Git Bash and PowerShell 5.1.26100.8737 print the same `4075c323…`.
  - A path that is not yet in the index or HEAD raises `CalledProcessError` (git exit 128), which is a clean failure.
  - `core.autocrlf` is `true`, as §11 says.
- **(h) Consistency** — held.
  - §4's imports resolve to §8.5 and §12.3 names.
  - The 18 CREATE rows equal §8.4's 18 new files.
  - The classes add up: 12 + 17 + 1 = 30.
  - Every §9.3 constant has a user.
  - §5 traces a single spawn, so it does not need the close order or the monitor.
- **(i) The §11 commands** — they match the field guide: the source stage runs with `PYTHONPATH`, the package stage without it. They were not run, per the rules.
- **D-31 against MCP clients** — held.
  - `vidbyte/mcp_server` applies no tool timeout; the word does not appear anywhere in the package. D-31's clamp is therefore the only server-side bound.
  - An MCP client whose own timeout is under 240 s ends the call on its side, and cancelling a wait never affects the turn.
- **The A-1 premise** — `codex --version` printed `codex-cli 0.162.1`, and `codex` resolves to the npm launcher `C:/Users/422mi/AppData/Roaming/npm/codex.cmd`.
- **`agents-md-placement.yml`** — runs on `workflow_dispatch` only ("TEMPORARILY DISABLED"). Its prompt prefers "an existing module when one clearly fits", so a dispatch could move D-26's records into `codex.py`. This is a process risk, not a spec defect.
- **Not verified: which reviewer Codex assigns when none is sent.** Checking needs a live app-server, which the rules forbid. R-1's fix does not depend on the answer.
