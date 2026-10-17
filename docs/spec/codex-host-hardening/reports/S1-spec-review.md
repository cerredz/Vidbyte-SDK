VERDICT: SOUND WITH FIXES — The design is sound, and its schema facts, retry placement and test pins check out. It must still adopt the #1055 review conventions (constants in lib, the error-packet wording, input records) and close four behavioural gaps before S2 writes tests from it.

WHAT THE SPEC GETS RIGHT
- **The superseded-test list in §13 is accurate and complete.** All 17 tests exist with the named assertions. My greps found no other test pinning:
  - the accept answers or the construction-time USER refusal;
  - fork/review `includeTurns` (the read at `test_codex_host_threads.py:293` is `read_codex_thread(include_turns=True)`, which INV-38 keeps);
  - the wrapper operations, the two removed constants, or the effort members;
  - a tool letting a non-mapped exception escape.
- **The retry placement is right.**
  - `retry_on_overload` sits inside the existing `asyncio.wait_for` bound of `CodexConnection.call`, for an allow-list of idempotent typed reads only. That is S012-clean.
  - The SDK retries only `is_retryable_error` (a `ServerBusyError` or overloaded data, `openai_codex/errors.py:112-121`). So the existing -32603 failure tests, such as `test_codex_host_lifecycle.py:331`, neither slow down nor change.
- **The fail-closed defaults match the 0.163.0 schemas exactly.** Each default carries every field its response schema requires:
  - `decision` on CommandExecution, FileChange, ExecCommand and ApplyPatch;
  - `answers` on ToolRequestUserInput;
  - `permissions` on PermissionsRequestApproval;
  - `action` on McpServerElicitation;
  - the integer `currentTimeAt` on CurrentTimeRead.

  The handler bridge reuses the proven one-try shape of `CodexToolCallHandler.handle` (`vidbyte/agents/codex/tools.py:142-185`).
- **The ordering and placement choices keep every pin green by construction.**
  - `FORGET_CODEX_TURNS` sits before `START_CODEX_REVIEW`, and `forget_codex_turns` is defined before `start_codex_review`.
  - The `__all__` insertion goes before the thread-helpers tail.
  - The two removed names sit at `vidbyte/lib/constants/codex.py:609-610`, before the tail that starts at `:626`.

FINDINGS

R-1 [Blocker] [L4] §9.2, §12.3 rows 12/14/15/16/19, INV-1, INV-29 — The spec places new constants, tables and messages in native-host modules and invents its own error-message suffix. The #1055 review already rejected both, and open PR #1178 blocks them with a lint at baseline 0.
  Evidence:
  - **What the spec prescribes.**
    - §9.2 "Message constants (module-level …)" places 12 new messages in `host`, `wire`, `preflight`, `thread_helpers` and `tools _base`.
    - Row 12 adds a module table, `GOAL_REJECTED_FIELDS`, plus a new `REJECTED_FIELDS` row.
    - Row 15 puts `REVIEW_REQUEST` at module level in the new `reviews.py`.
    - INV-29 validates the list arguments inline in `CodexThreadHelpers.reject_list_arguments`.
    - INV-1 and AC-2 pin the suffix `" Thread: <id>."`.
  - **What the field guide says** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`). Each of these entries cites #1055 review comments 4301484278, 4301488494, 4301489517, 4301496612 and 4301744297:
    - `blocking-lint-invariants.md` "C021: a native harness host keeps no module-level constants; they live in `vidbyte/lib/constants/<domain>.py`". Its When clause is "Adding a table, bound, field rule or message text to any module under `vidbyte/harnesses/native/`, including `codex/`".
    - `diagnostic-context.md` "A harness host's errors use the lib error-packet shape", with the format `<operation> failed with <code>. <summary> [The thread id was <id>.] Likely cause: … Next step: …`.
    - `strict-config-dataclasses.md` "A host's public methods keep their keyword signatures and build one validated record right after the call guard", with the records in `vidbyte/lib/dataclasses/<domain>_inputs.py`.
  - **What the spec cites.** §11 "Field-guide entries applied" cites `blocking-lint-invariants.md` for S012, A003 and A007, but not its C021 entry. It cites neither of the other two entries.
  - **What PR #1178 does** (`gh pr view 1178`: OPEN, "fix: resolve review comments from PR #1055").
    - It adds `lint/rules/c021_native_host_constants_in_lib.py`. The rule is blocking, seeded at 0, and flags every top-level UPPER_CASE binding under `vidbyte/harnesses/native/`.
    - It adds `vidbyte/lib/constants/codex_host.py`, and `vidbyte/lib/dataclasses/codex_host_inputs.py` with 16 records. It moves `REJECTED_FIELDS` into those records.
    - It rewrites every mapped message into the packet shape and takes `host.py` to 919 lines.
    - It edits 11 of the 21 files in §12.3: errors, connection, wire, preflight, turns, thread_helpers, host, skill_functions, `lib/dataclasses/codex_host.py`, `lib/errors/base.py` and `tools/builtins/codex/_base.py`. It also edits `codex_host_support.py`, `test_codex_host_goal_skills.py` and `test_codex_host_helper_surface.py`, which S2 must edit too.
  Failure:
  - **If S3 builds §12 exactly**, the PR draws the same three comments #1055 drew:
    - "wrong file location, put inside of lib";
    - "messages need more detail, formatted like the lib error folder";
    - "dataclasses with strict input validation".
  - **If #1178 reaches main first**, the slice-1 rebase fails C021 on every new constant and conflicts in 11 files. INV-31's "keep the message" then leaves the text `"<inner op> failed with …"` on an error whose `operation` is the wrapper's. `host.py` lands near 946 lines, not the ~920 of NFR-6.
  Smallest fix (the base decision stays):
  1. In §9.2 and §12.3, put every new message, table and bound in `vidbyte/lib/constants/codex.py` under a `CODEX_HOST_` name. Insert each before the thread-helpers `__all__` tail, as §9.3 already requires.
     - `REVIEW_REQUEST` becomes an attribute set in `CodexReviews.__init__`, not a module constant.
     - Existing module constants stay where they are; moving them is #1178's job.
  2. In INV-1 and AC-2, use the field-guide sentence `The thread id was <id>.` in place of `" Thread: <id>."`. Under the packet shape, INV-31 must also rewrite the leading operation of the message.
  3. Validate the new or changed inputs through records rather than `reject_list_arguments`. The inputs are `limit`, `before_turn_id`, `defer_goal_continuation`, `force_reload`, the review `request`, and the `thread_id` of `forget_codex_turns`.
     - If #1178 has merged, extend its `codex_host_inputs.py`.
     - Otherwise, create that module with only this slice's records, so the two merge into one file. §8.4 grows by 1 file and about 5 classes.
  4. Add to §15:
     - A-13: "PR #1178 is open and overlaps §12.3; whichever merges first, the other rebases."
     - Q-17: "If #1178 is on main before S3 starts, rebase slice 1 onto it and target its constants and input modules?" (default: yes).

R-2 [Major] [L9] §6.1 INV-20, §6.2 AC-14 — "Refused before any request" is false for fork and the two skill runs, so S2's AC-14 test and S3's INV-28 implementation cannot both pass.
  Evidence:
  - **What the spec promises.**
    - INV-20: "`CodexPreflight.run` refuses … as its first step and before any request. This covers spawn, continue, launch, fork, `run_codex_goal`, `run_codex_skill` and `run_codex_openai_docs`."
    - AC-14: "Without a handler, each call [spawn, continue, launch, fork, run_codex_goal] raises … before any request."
  - **What actually runs first.**
    - INV-28 orders fork as "2. The thread must exist: one metadata `thread/read`" before "3. `CodexPreflight.run`".
    - `skill_functions.py:145-147` sends `list_codex_skills` (`skills/list`) before `spawn_codex_thread`, which is where the preflight runs. INV-33 keeps that order.
  - **Why fork must keep that order.** D-21 depends on the thread-first order, because `test_codex_host_lifecycle.py:331-339` also fails `model/list`.
  Failure:
  - `fork_codex_thread(…, overrides=CodexSpawnRequest(approvals_reviewer=USER))` on a host without a handler sends `thread/read` and then refuses.
  - `run_codex_skill` sends `skills/list` and then refuses.
  - S2 writes AC-14's fork case as "no request sent", and S3 implements INV-28 exactly. That test then fails, §14 forbids S3 to edit it, and the stage loops BLOCKED.
  Smallest fix: amend INV-20 and AC-14 to read "before the operation's first Codex request, except fork, after its metadata `thread/read` (INV-28 step 2), and `run_codex_skill`/`run_codex_openai_docs`, after the skill listing".
  - Alternative: run the local reviewer check in INV-28 step 1, and at the start of the skill runs. It needs no request, so "before any request" stays literally true.

R-3 [Major] [L7] §9.1, §8.1 D-4, §4 — `CodexServerRequest` drops the scalar `kind` (`command` or `writeStdin`) and `approvalId`. A handler therefore cannot tell approving a new command from approving input typed into a terminal that is already running.
  Evidence:
  - **The 0.163.0 schema.** `CommandExecutionRequestApprovalParams.json` carries these fields:
    - `kind`: `CommandExecutionApprovalKind`, enum `["command", "writeStdin"]`, default `command`. Its description is "Distinguishes a command approval from input sent to an existing terminal."
    - `approvalId`: "multiple callbacks can belong to one parent `itemId` … Stdin approvals also use a distinct callback id; inspect `kind`".
    - `environmentId`.
    - `startedAtMs`, which is required.
  - **What the spec mirrors.** §9.1's `from_params` mapping lists none of these fields. Yet D-4 says "Records mirror the scalar wire fields". The field-guide entry it cites (`class-bound-helpers.md:45-49`) says the record "mirrors the provider's wire schema field for field".
  Failure:
  - **The handler cannot see what it approves.** The §4 handler itself (`request.kind is COMMAND_EXECUTION and request.command == "git status"`) cannot distinguish a `writeStdin` approval from a command approval. A rule written for commands therefore also approves stdin writes into an existing terminal session. That is a shorter path to harm than T-1 and T-3 trace.
  - **Separate callbacks cannot be told apart.** Two approvals under one `itemId` reach the handler as indistinguishable records.
  - **An all-object decision list collapses to "anything fits".** A present `availableDecisions` made only of object decisions becomes `()`, which INV-18 treats as anything fitting. An ACCEPT that Codex did not offer then passes.
  Smallest fix:
  - Add `CodexCommandApprovalKind` (`COMMAND="command"`, `WRITE_STDIN="writeStdin"`) to `vidbyte/lib/enums/codex.py`. Add the fields `approval_kind` (default COMMAND, matching the wire default), `approval_id: str = ""` and `environment_id: str = ""` to `CodexServerRequest`, and to the AC-11 field list. §8.4 grows by 1 class.
  - Let INV-18 tell "list absent" apart from "list present but nothing known", for example with `available_decisions: tuple | None`. In the second case, only DECLINE or CANCEL fits.

R-4 [Major] [L5] §6.1 INV-2, AC-5 — Deriving `retryable` from the TRANSIENT class marks deterministic refusals, and a dead host, as retryable.
  Evidence:
  - The TRANSIENT codes in `CODEX_FAILURE_CLASSIFICATION` are `thread_resume_failed`, `fork_failed`, `response_invalid`, `usage_limited`, `session_busy`, `api_error`, `process_exited` and `turn_timed_out`.
  - INV-28 step 4 raises `codex.fork_failed` deterministically: for an unknown or non-completed `from_turn_id`, and when there is no completed turn.
  - EC-27 raises `fork_failed` for a `before_turn_id` that names no turn.
  - After a death, every call on the same host raises `process_exited` (`test_codex_host_turns.py:322-329`).
  Failure:
  - A caller following §4 ("decide whether to retry") retries `fork_codex_thread(t, from_turn_id="turn-unknown")`, which reports `retryable=True` and fails the same way every time.
  - The same caller retries a call on a dead host forever. AC-5 then pins the wrong values.
  Smallest fix: have INV-2 decide this code by code.
  - Either add `CODEX_HOST_RETRYABLE_CODES` to the lib constants, excluding `fork_failed` (§8.4 grows by 1 config key).
  - Or keep the derivation and have INV-2 and the property docstring name the exceptions. `fork_failed` is not retryable. `process_exited` is retryable only on a new host.

R-5 [Major] [L5] §6.1 INV-21, EC-3, AC-38 — Close leaves the router routing approvals to the handler. EC-3's "RuntimeError" premise is false, so handler coroutines can outlive the host.
  Evidence:
  - **When close cancels.** Row 16 cancels pending handler calls in `_end_running_turns` (`host.py:213`). The router is still live while close then awaits one cleanup interrupt per running turn, each bounded by the close bound (`host.py:215-223`), and only afterwards closes the client.
  - **Why EC-3 is wrong.** `run_coroutine_threadsafe` raises only when the loop is *closed*, through `call_soon_threadsafe`, and the loop is running during `__aexit__`. EC-3 "A server request arrives after close began → `run_coroutine_threadsafe` raises `RuntimeError`" therefore does not hold.
  - **Why the reader survives.** `CodexClient.close` joins the reader for 0.5 s only (`openai_codex/client.py:301-302`).
  Failure: an approval request arrives for a still-running turn after `cancel_pending()` and before the cleanup interrupt lands.
  - The approval is scheduled on the developer's handler.
  - `__aexit__` returns while the reader is still blocked in `future.result(300)`.
  - The handler coroutine keeps running on the caller's loop after the host has closed, which violates INV-21's "no handler coroutine outlives the host".
  - AC-38 does not cover this case.
  Smallest fix: `cancel_pending()` also drops the router's handler, mirroring `remove_all`. Every later routed request then takes the no-handler default answer without scheduling. Rewrite EC-3 to cite this mechanism instead of `RuntimeError`.

R-6 [Minor] [L5] §6.1 INV-13 (b)/(c), EC-16 — On a process death, the lost-turn path can run before the death flag is set. It then logs a false `codex_host_turn_lost` WARNING and attempts a stray interrupt.
  Evidence:
  - A reader failure wakes both of these through the SDK's `fail_all`:
    - each watcher's blocked read (`turns.py:301-309`);
    - the monitor's `next_notification` (`connection.py:310-318`), which sets `_dead` before posting `on_death`.
  - These are independent threads. Nothing orders the watcher's `on_lost` post after `_dead.set()`.
  - EC-16 assumes that step (a) "sees … a stopped connection".
  Failure:
  - The watcher wins the race, so (a) passes and (b) logs a WARNING for an ordinary death. (c) then calls `interrupt(cleanup=True)`, which normally refuses at `call()`'s `_dead` check.
  - In a narrow window, though, the write lands after the reap. That records `write_after_close`, which the INV-45 death tests assert is empty (`test_codex_host_turns.py:329,343`).
  Smallest fix: move the WARNING into step (d), so it is logged only when the turn is actually finished `FAILED`. State in EC-16 that a racing death may cost one quiet, refused interrupt attempt.

R-7 [Minor] [L1] §3, §7, FR-36 — The second half of request row 4 has neither an FR nor an accepted limitation: "L10: 3–4 uncached preflight round trips run before every spawn".
  Evidence:
  - NFR-2 maps L10 only to FR-24, the review caps.
  - FR-36's list of accepted rows (9, 10, 12, 13, 14, 16–18, 21, 22) omits row 4.
  - No NG mentions preflight round trips. Row 1 (INV-24) and INV-25 add reads rather than removing any.
  Failure: a requested row is silently dropped, and the coverage check of L1 fails.
  Smallest fix: add NG-20, "Per-spawn preflight round trips (row 4, L10)". The reason: account and usage reads must be fresh, because sign-in and allowance change; the model list is already cached and refreshed only on a miss (D-26). Add row 4 to FR-36.

R-8 [Minor] [L9] §8.5 `CodexResponseTranslator.fork_point(turns: Sequence[Turn], …)` — The order of `turns` is unstated, and today's body assumes oldest first.
  Evidence:
  - `wire.py:598-601` returns `next(reversed(completed), "")` for an empty `from_turn_id`. That is the newest completed turn only when `thread.turns` runs oldest first.
  - INV-28 step 4 and D-18 make the scan newest first.
  Failure: an implementer who keeps the body and passes the newest-first pages forks from the *oldest* completed turn among them. B1's "last completed" assertion (`test_codex_host_threads.py:206-208`) catches this only because its seed has two completed turns.
  Smallest fix: §8.5 states "`turns` newest first; an empty `from_turn_id` means the first completed turn in the sequence", and row 11 says the body changes accordingly.

R-9 [Minor] [L10] §13 — The fault-injection seams for AC-7, AC-8 and AC-9, and the handler-timeout patch, are not named, so a blind test author has to guess or mock forbidden parts.
  Evidence:
  - §13 names no way to make event processing raise (AC-7), make a watcher read raise while the process lives (AC-8), or make the review read-back raise a non-Codex exception (AC-9).
  - The watcher binds `partial(client.next_turn_notification, turn_id)` or `next_goal_notification` at `watch` time (`turns.py:157-160`). A patch must therefore be in place before the spawn.
  - The pack's precedent is `mock.patch.object(self.server.client, "account_read", side_effect=…)` (`test_codex_host_failures.py:244`).
  - §13 says `patch_connection("CODEX_TOOL_CALL_TIMEOUT_SECONDS", …)` works. But `patch_connection` is `mock.patch` without `create=True` (`codex_host_support.py:343-347`), and `connection.py` does not import that name today.
  Failure: S2 writes AC-7, AC-8 and AC-9 against seams S3 does not provide, or mocks parts §13 forbids. A handler-timeout test raises `AttributeError` unless row 10 imports the constant by name and reads it at call time.
  Smallest fix:
  - Add to §13: patch `server.client.next_turn_notification` or `next_goal_notification` before the spawn for AC-8. Make the patched read raise for AC-7, through a notification the fake can emit or by patching `CodexResponseTranslator.turn_snapshot`. Patch `CodexResponseTranslator.stored_turn` for AC-9.
  - Add to row 10: "import `CODEX_TOOL_CALL_TIMEOUT_SECONDS` by name and read it inside `handle`".

R-10 [Minor] [L8] §12.3 rows 15/16, §12.4 import-safety item — The rows never say that `reviews.py` must be loaded inside `_open`.
  Evidence:
  - `CodexReviews` needs `turns.py`, which imports `openai_codex` at module level (`turns.py:22,33`).
  - `host.py` imports `preflight`, `skill_functions` and `thread_helpers` at module level, but loads `connection`, `turns` and `wire` inside `_open` (`host.py:162-170`).
  - The §12.4 import-safety item names only `connection.py`.
  Failure: a natural `from …reviews import CodexReviews` at the top of `host.py` makes `import vidbyte.harnesses.native.codex` load the SDK. That breaks INV-41 and `test_codex_host_packaging.py:169-182`, and the package fails to import without the extra.
  Smallest fix: row 15/16 and §12.4 say "`CodexReviews` is imported inside `_open`, beside `CodexConnection`, `CodexTurnRegistry` and the translators".

R-11 [Minor] [scope-adding] [L5] EC-1, D-2 — A handler that awaits any talking method of its own host freezes every turn on that host for 300 s, every time.
  Evidence:
  - EC-1 accepts this case and documents it only in a docstring.
  - Both bounds are 300 s (`CODEX_HOST_REQUEST_TIMEOUT_SECONDS == CODEX_TOOL_CALL_TIMEOUT_SECONDS`, `test_codex_host_records.py:484`), so the two sides time out together.
  - Reading the thread before approving is a natural thing for a handler to do.
  Failure: `approval_handler` calls `host.read_codex_thread(request.thread_id)`. All notifications on the host stop for 300 s. The handler then gets `codex.api_error`, and the request gets its default answer.
  Optional fix: Q-18, "Mark handler calls with a contextvar set when the router schedules the handler, and have `_guard(talks=True)` raise `ConfigurationError` at once inside a handler?" (default: not built).

VERIFIED CLAIMS:
- **File sizes at base: held.**
  - `host.py` 893, `connection.py` 374, `wire.py` 710, `preflight.py` 186 and `turns.py` 419 lines.
  - `lib/dataclasses/codex.py` 1,205 and `lib/dataclasses/codex_host.py` 616 lines.
- **The router auto-accepts approvals and answers everything else `{}`** (`connection.py:127-130`): held.
- **The openai-codex reader handles server requests synchronously: held.**
  - It calls the approval handler on its reader thread, and any exception reaches `fail_all`.
  - `close()` joins the reader for 0.5 s only (`client.py:283-302`).
  - `CodexToolCallHandler.close()` only cancels pending futures; it has no closed flag.
- **`retry_on_overload` matches the spec's description: held.** It makes 3 attempts and sleeps between them. It retries only `ServerBusyError` or overloaded data. The four retried methods exist as constants (`codex.py:527-532`) and are sent through typed `connection.call` sites (`host.py:241,348,368,670`, `preflight.py:105,172`, `thread_helpers.py:221`).
- **0.163.0 schemas: held, with the record gap noted in R-3.**
  - Every default answer carries its schema's required fields.
  - The user-input answer shape `{answers: {id: {answers: [str]}}}` is correct.
  - FileChange approvals carry no `availableDecisions`.
  - SandboxPolicy `readOnly` and `workspaceWrite` take `networkAccess`; only `workspaceWrite` takes `writableRoots` (INV-37).
  - `ThreadTurnsListParams` has `cursor`, `itemsView`, `limit` and `sortDirection`.
  - CommandExecution approvals also carry `kind`, `approvalId`, `environmentId` and `startedAtMs` (R-3).
- **The 17 superseded tests in §13: held.** All exist with the named assertions. A2 is `test_codex_host_records.py:357-370`, B1 is `test_codex_host_threads.py:189-228`, and G1–G4 are at `test_codex_host_goal_skills.py:209,570,636,645`.
- **No missed pins: held.** Greps for accept answers, `validate_spawn_request`, `includeTurns`, the removed constants, effort members, `.fail(` on the retried methods, and a `StubCodexHost` parity check found nothing further.
- **The "green by construction" pins: held.** The operation-order test (`test_codex_host_helper_surface.py:245-251`), the method-order test (`:299-304`) and the `__all__`-tail test (`:272-288`) all stay green with the §8.5 and §9.3 placements.
- **Reused symbols exist: held.** `CODEX_MILLISECONDS_PER_SECOND` (`codex.py:329`), `CODEX_HOST_THREAD_LIST_MAX_PAGES = 1000`, `CODEX_TOOL_CALL_TIMEOUT_SECONDS = 300.0` and `CodexLiveTurn.stop` (sync, spawns the interrupt; `turns.py:166-177`) all exist.
- **`patch_connection` covers the handler bound: not held.** `connection.py` does not import `CODEX_TOOL_CALL_TIMEOUT_SECONDS` (R-9).
- **The import path D-6 gives: not held.** `vidbyte/lib/enums/native_threads.py` imports no errors module; it only names one in its docstring. D-6's conclusion still holds: keep the import function-level, because importing `vidbyte.lib.constants.codex` already loads `vidbyte.lib.errors.base` through other package inits.
- **G-3, "every server request gets an answer its schema accepts": not held as written.** EC-10's `{}` fails `ChatgptAuthTokensRefreshResponse` (requires `accessToken` and `chatgptAccountId`) and `AttestationGenerateResponse` (requires `token`). EC-10 itself states the limitation correctly, so qualify G-3 and FR-13.
- **D-21's reason (fork reads the thread before the preflight): held.** The one-shot lifecycle test also fails `model/list` (`test_codex_host_lifecycle.py:331-339`).
- **Pre-existing `harness_threads` failure at `:193` (120 vs 167 `FailureCode` members): held.** PR #1178's body reports the same failure on main. No new `FailureCode` appears in §12.3.
- **INV-36's tier check and NG-9: consistent with the schema.** `ReviewStartParams` takes no model, effort or tier (code-map §4.5, and the spec's own NG-9).
- **The §8.4 new-file count of 2 equals rows 7 and 15: held.** R-1 and R-3 change the budget by +1 file and about +6 classes if they are adopted.
- **Field-guide coverage in §11: not held.** The entries it cites exist. It omits the three #1055-review entries that apply to this change (R-1).
