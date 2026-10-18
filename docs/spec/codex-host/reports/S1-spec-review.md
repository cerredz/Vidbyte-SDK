# S1 spec review: codex-host (round 1)

- **Spec reviewed:** `docs/spec/codex-host/spec.md` r1, from commit `a1ee792a`.
- **Branch state:** worktree HEAD `90ccdf12` on `feat/codex-host`, base `678136bd`.
- **Request revision:** request.md §C as revised in `90ccdf12`.
- **Method:** read-only. No gate, test, install or `codex` run beyond `--version`.
- **Probes:** ruff 0.16.0 from the vidbyte-cli venv, with `--no-cache --isolated --target-version py311`, on stdin and over `vidbyte/`.

VERDICT: SOUND WITH FIXES — Approach B and the wire facts hold against openai-codex 0.162.1. Two things must change before S2:
- §12 omits the zero-headroom S054 rule.
- §12 still carries its own REPO_MAP text.

Five lifecycle claims also need scoped corrections: the shared reader thread, the Windows close, close on the default executor, USER approvals, and the wait clamp.

WHAT THE SPEC GETS RIGHT
- **An S012-clean transport with no private attribute.** Keep D-2 and the §12.4 call list as written.
  - Each typed `CodexClient` method takes the full params object, so `lastTurnId`, `excludeTurns`, `approvalsReviewer`, `developerInstructions` and `dynamicTools` need no raw call:
    - `thread_start(params: V2ThreadStartParams | JsonObject | None)` at `client.py:478`;
    - `thread_resume(thread_id, params)` at :485;
    - `thread_fork(thread_id, params)` at :505.
  - The five raw calls go through `request_with_retry_on_overload` (:731). It retries only overload errors (`retry.py:12`, `errors.py:112:is_retryable_error`) and accepts `max_attempts=1` for the two calls that spend.
- **Gap-free handles for spawn and continue.**
  - The typed `turn_start` starts its turn inside `pending_turn(thread_id)` (`_message_router.py:145`).
  - `prepare_turn` (:159) registers a consumer before `_prune_turn_events` (:196) can drop anything.
  - Dedicated daemon watchers (D-6) and a monitor that drains the unbounded global queue (D-27) keep long waits out of the executor.
- **The lazy-import boundary (D-21).**
  - The SDK is imported only in `connection`, `wire` and `turns`, which load from `__aenter__`, and the tools import the host only under `TYPE_CHECKING`.
  - This fits the package-stage smoke test, which runs without the extra.
  - It also fits `ComponentRegistry._discover`, whose `vars(builtins)` scan (`vidbyte/lib/registries/components.py:101-124`) imports every builtin tool module.
- **Accurate wire and repo facts:**
  - `last_turn_id` is inclusive and cannot be in progress, `exclude_turns` only shapes the response, and `ThreadForkParams` has no personality field.
  - `ordinary_usage_allowed=None` must not be read as recovery.
  - `timeout_seconds` keeps S045 (ASYNC109) clean.
  - The 15 codes go right after `CODEX_RUN_OPTION_UNSUPPORTED` (`failure.py:46`), under the existing classification and dot-rule tests.
  - The field-rules table matches `ThreadResumeParams` and `ThreadForkParams`.

FINDINGS

R-1 [Blocker] [L8] §12.4 — §12.4 omits S054, which has no headroom, so the description constant §12.3 requires for `goal_token_budget` fails the lint gate
  Evidence:
  - **What the spec requires:**
    - Row 17: "One description constant per tool and per parameter."
    - §9.2 tool row 4: "`goal_token_budget` (integer ≥ 1; only with `goal_objective`)".
    - §12.4 lists A001, A002, A003, A006, A007, A009, C006–C008, C015, S006–S009, S012, S015–S017, S019, S024, S025, S039, S045, S051, S060, S062, S063 and Semgrep. S054 is not among them.
  - **The lint wiring:**
    - `lint/baseline.json:81` is `"S054": 3`.
    - `lint/rules/s054_bandit_security_subset.py:27` sets the codes to `{"S105","S106","S107","S108","S301","S302","S501"}`, and `lint/core/ruff.py:34` selects them over `vidbyte`.
  - **Current findings:** ruff with those seven codes over `vidbyte/` prints "Found 3 errors.":
    - `middleware/builtins/token_budget.py:28 TOKEN_BUDGET_FINAL_RESPONSE_NOTICE`;
    - `middleware/compaction/base.py:28 TRIM_TO_TOKEN_BUDGET`;
    - `workflows/contracts.py:73 PASS`.
  - **Stdin probe:**
    - It flags `GOAL_TOKEN_BUDGET_DESCRIPTION = "…"`: "S105 Possible hardcoded password assigned to: "GOAL_TOKEN_BUDGET_DESCRIPTION"".
    - It also flagged `CODEX_TOKEN_USAGE_UPDATED_NOTIFICATION = "…"`, `token_budget == "null"` and `params["token_budget"] = "5"`.
    - It passes `SPAWN_GOAL_BUDGET_DESCRIPTION`, `MAX_OUTPUT_TOKENS_DESCRIPTION`, `CODEX_USAGE_UPDATED_NOTIFICATION`, `params["tokenBudget"] = …` and `{"goal_token_budget": …}` keys.
  Failure:
  - S3 writes the natural `GOAL_TOKEN_BUDGET_DESCRIPTION` in `descriptions.py`. S054 goes from 3 to 4 and reports REGRESSED. `python lint/run.py` and the source stage fail.
  - Two of the three existing allowances are this exact token-budget naming pattern, so it has already happened twice in this repo.
  - The same applies to any `token_*` name or `*_token` comparison against a string in `wire.py` or `turns.py`.
  Smallest fix:
  - Add an S054 item to §12.4 under "Lint rules on harness code": "S054 (ruff S105–S108, S301, S302, S501; baseline 3, current 3, no headroom)."
  - State the rule it enforces. The rule applies to a variable, attribute, constant or subscript key when one of its `_`-separated segments, matched case-insensitively, is `token`, `secret`, `password`/`passwd`, `pwd` or `pass`. Such a name is never:
    - assigned or compared to a string literal;
    - given a non-empty string default;
    - passed as a string keyword.
  - Note that `tokens` and `tokenBudget` are safe segments.
  - Prescribe the name `SPAWN_GOAL_BUDGET_DESCRIPTION` in row 17.
  - Keep §9.3's `CODEX_USAGE_UPDATED_NOTIFICATION`. A `CODEX_TOKEN_USAGE_…` rename trips the rule.

R-2 [Blocker] [L1] §12.5 — §12.5 and row 27 prescribe a REPO_MAP paragraph that differs from request.md §C's byte-fixed block and breaks the map rule
  Evidence:
  - **The spec's text:** §12.5 says "Insert this text verbatim before `##### \`vidbyte/harnesses/stores/\``". Its paragraph begins "Hosts for native coding-harness executables, the vendors' own coding agents, …". It also contains "reported as a `<host>.<problem>` code" and "lives under `vidbyte/tools/builtins/`, bundled by a toolset in `vidbyte/tools/toolsets/`".
  - **request.md:176:** "both PRs insert the same text at the same spot, byte for byte … two different texts at the same spot would conflict … These texts replace whatever wording a spec proposed for these two files."
  - **request.md:178:** "no backtick-quoted file name, child-folder path or command in the description body".
  - **request.md:184** carries the fixed paragraph, which begins "Hosts for the coding agents that vendors ship as their own executables, …".
  - **§9.4:** "The repo-map section and README bullet (rows 27, 28) are byte-identical in both PRs, so git merges them cleanly". That is false while §12.5 differs.
  Failure:
  - S3 builds row 27 "verbatim" from §12.5.
  - The orchestrator's byte comparison against request.md fails. Otherwise, the second merge conflicts at the insertion point just above REPO_MAP.md:151.
  - The backticked child-folder paths and the `<host>.<problem>` token also draw the map-rule comment that the request was revised to prevent.
  Smallest fix:
  - Replace §12.5's REPO_MAP quote with request.md:182-184 verbatim: the heading, a blank line, and the one paragraph.
  - Make row 27 and §9.4 cite request.md §C as the source of the text.
  - The README bullet in §12.5 already matches request.md:188 byte for byte, so leave it.

R-3 [Major] [L5] INV-29 / EC-29 — A dynamic tool call blocks the host's only reader thread, which stalls every other turn and request on the host for up to 300 s
  Evidence:
  - **The spec:**
    - INV-29: "The SDK reader thread is blocked for at most `CODEX_TOOL_CALL_TIMEOUT_SECONDS` per call."
    - EC-29: "output can pass `max_output_tokens` by up to one model call".
    - EC-36: "accepted: Codex answers `turn/start` far inside the bound".
    - EC-48 covers only the self-call case.
  - **The SDK:** `openai_codex/client.py:863-871:_reader_loop` runs `response = self._handle_server_request(msg)`, then `self._write_message(...)`, and only then reads the next message.
  - **The handler:** `vidbyte/agents/codex/tools.py:148-150` waits `future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)` on that thread.
  - **Why it is shared:** one host owns one app-server (FR-1), so one reader serves every thread.
  Failure: one host runs turn A, whose dynamic tool takes 120 s, and turn B with `max_output_tokens=2000`. While A's tool runs:
  - No notification for B is routed. B's crossing of its cap is seen up to 120 s late, which is far more than "one model call".
  - B's `turn/completed` is held, so `wait_codex_turn(B, 30)` returns RUNNING for a turn that has finished.
  - Every response waits too, including interrupts, reads and the monitor's view of death.
  - If the tool runs near 300 s, a concurrent spawn's `turn/start` hits the bound. It raises `codex.api_error` while Codex later accepts the turn, which then runs unowned and uncapped (EC-36).
  Smallest fix: the SDK answers server requests synchronously, so this is documentation and edge-case work, not new machinery.
  - Add an EC: "A dynamic tool call holds the host's single reader. Other turns' events and all responses wait for it, for up to 300 s." Mark it accepted.
  - Correct EC-29 to "one model call, plus the duration of any dynamic tool call running on the same host".
  - Add this warning to the docstring obligations of `CodexSpawnRequest.tools` (row 6) and `CodexHostTools` (row 25): keep tools short, or give tool-using threads their own `CodexHost`.

R-4 [Major] [L5] §15 A-1 / INV-7 / Rollback — On the user's Windows npm install, `close()` terminates only cmd.exe, so "closing the host kills the app-server" is unverified and likely false
  Evidence:
  - **The spec:**
    - A-1: "`CodexClient.close()`'s terminate stops the app-server behind it."
    - Rollback: "closing the host kills the app-server, which stops every turn it ran."
  - **`client.py:291-297`:** `close()` runs `proc.stdin.close(); proc.terminate(); proc.wait(timeout=2)`, with `kill()` only on an exception. `client.py:268` is a plain `subprocess.Popen`, with no creationflags and no job object.
  - **The launcher chain:**
    - `C:/Users/422mi/AppData/Roaming/npm/codex.cmd` runs node `…\@openai\codex\bin\codex.js`.
    - That script `spawn`s the native `codex.exe` with `stdio: "inherit"`, and forwards only SIGINT, SIGTERM and SIGHUP.
    - On Windows, `Popen.terminate()` is `TerminateProcess` on the launched cmd.exe only.
  Failure: the host is closed with a turn running.
  - cmd.exe dies, `wait(2)` succeeds and `kill()` never runs.
  - node and codex.exe keep the stdout pipe open, so the SDK reader never sees EOF and `fail_all` never fires.
  - Whether the turn stops now depends on the app-server exiting on stdin EOF. That is unverified, and a server that drains in-flight work on EOF keeps spending with no owner.
  - The monitor and the turn and goal watchers stay blocked until the process exits.
  Smallest fix:
  - In `__aexit__`, before `client.close()`, send one bounded interrupt per running turn, using `cancel_goal_operation` for goal runs, and ignore its errors.
  - Rewrite A-1 to the verified launcher chain.
  - Make INV-7 and the rollback text promise "interrupts running turns, then closes".
  - Add an EC for children that outlive the terminate.

R-5 [Major] [L7] INV-28 / D-16 / EC-63 — With `approvals_reviewer=USER`, every escalation is silently approved, the opposite of what the setting asks for
  Evidence:
  - **The spec:**
    - INV-28: "Command and file-change approval requests that reach the host are answered `accept`, as the SDK's default handler does."
    - §8.5 lists `CodexApprovalsReviewer.USER = "user"`.
    - A-7: "Only `user` sends them to the host."
    - EC-63: "no human approval prompt appears | accepted: mirrors the SDK".
  - **The SDK:**
    - `openai_codex/_approval_mode.py:16-35`: the public `ApprovalMode` maps only `deny_all` to (never, None) and `auto_review` to (on-request, auto_review). The SDK's own API therefore never routes approvals to its `_default_approval_handler` (`client.py:833-838`).
    - `generated/v2_all.py` has no approval-decision enum.
  - **The request:** request.md's R3 vocabulary row is `permission_denied` | "approval declined".
  Failure:
  - A developer sets `approvals_reviewer=USER`, typically with `approval_policy=UNTRUSTED`, to get a human gate.
  - Every command and file-change request is accepted with no prompt, including escalations outside the sandbox.
  - That is more permissive than either Codex-side reviewer, and only explicit developer code can reach this path, so it looks like a safe setting.
  Smallest fix (fail closed):
  - `CodexSpawnRequest.__post_init__` rejects `approvals_reviewer=USER` with a `ConfigurationError` naming the unstarred `set_codex_approval_handler`. Dropping the USER member is an equivalent fix.
  - The `accept` answer stays only as the SDK-mirroring fallback for the case where A-7 is wrong.
  - Q-3 stays open for the callback, and T-6 and EC-63 are updated.

R-6 [Major] [L5] D-1 / D-3 / §12.3 row 12 — Calls, including `close()`, run on the loop's default executor, so a silent app-server can starve the developer's process and stop close from ever running
  Evidence:
  - **The spec:**
    - D-1: "Every call runs as `asyncio.wait_for(asyncio.to_thread(...), CODEX_HOST_REQUEST_TIMEOUT_SECONDS)`."
    - Row 12: "starts, initializes and closes the client in worker threads".
    - NFR-9 keeps only the watchers "outside the default executor".
    - EC-35: "host calls end at 300 s with `codex.api_error`".
  - **The SDK precedent:** `openai_codex/async_client.py:53-54` reads `# Bound workers while allowing cancellation cleanup to outlive an asyncio waiter.` followed by `_TURN_START_EXECUTOR = ThreadPoolExecutor(...)`. Its goal start and its cancelled-start cleanup also run on dedicated daemon threads (:258-261, :283-286).
  - **The standard library:** `to_thread` uses the default executor, which has min(32, cpu+4) workers. `wait_for` cannot stop a worker blocked in a router waiter.
  Failure: the app-server is alive but silent (EC-35).
  - Each timed-out call leaves its worker blocked until a response arrives or `fail_all` runs.
  - A launch, or a few agents or MCP calls, fills the pool. After that, every `to_thread` and `loop.getaddrinfo` in the developer's process queues.
  - `__aexit__`'s close queues as well. It times out at 300 s and is cancelled before it starts, so the app-server is never terminated.
  Smallest fix:
  - Run `close()` and the death cleanup on a dedicated daemon thread.
  - Run host calls on a host-owned executor, following the `_TURN_START_EXECUTOR` precedent, never on the loop default.
  - Add an EC for this case.
  - When the 300 s bound elapses on `turn/start` or `review/start`, apply INV-11's late-acceptance handling: register the turn and send one interrupt. EC-36 then stops being "accepted".

R-7 [Major] [L5] D-31 / §9.3 — The wait tool's default and clamp equal the Codex tool-call cancel bound, so a Codex caller always gets a timeout instead of a RUNNING snapshot
  Evidence:
  - **The spec:**
    - D-31: "The wait tool's `timeout_seconds` defaults to `CODEX_HOST_TOOL_MAX_WAIT_SECONDS` (300 s) and is clamped to it. | `CodexHarnessAgent` cancels its own tool calls at 300 s".
    - §9.3 sets it "`= CODEX_TOOL_CALL_TIMEOUT_SECONDS` (300.0)".
  - **The repo:**
    - `vidbyte/agents/codex/tools.py:150-157` calls `future.result(timeout=CODEX_TOOL_CALL_TIMEOUT_SECONDS)` and returns "Tool call timed out after 300 seconds.".
    - The host's router reuses that handler (D-18, row 12).
    - `vidbyte/tools/executor.py` has no timeout at all, so only Codex-bridged callers are affected.
  Failure:
  - A Codex model calls `wait_codex_turn` with no `timeout_seconds` on a turn longer than 300 s. The model may be running in a `CodexHarnessAgent`, or in a host thread given a second host's `CodexHostTools` as EC-48 advises.
  - The bridge's 300 s clock starts before the tool's own 300 s wait, so the bridge always fires first.
  - Every such call returns "Tool call timed out after 300 seconds." and never the RUNNING snapshot that D-31 was written to protect.
  Smallest fix:
  - Make `CODEX_HOST_TOOL_MAX_WAIT_SECONDS` its own constant, strictly below `CODEX_TOOL_CALL_TIMEOUT_SECONDS` (for example 240 s).
  - State the margin in D-31 and add an EC.

R-8 [Major] [L11] §11 / §12.4 / §14 / AC-36 — The native-bytes check hashes the working copy, which is CRLF on this machine, so correct bytes print the wrong SHA and trigger a false BLOCKED
  Evidence:
  - **The spec:**
    - §11 "Native bytes": `python -I -c "import hashlib;print(hashlib.sha256(open('vidbyte/harnesses/native/__init__.py','rb').read()).hexdigest())"` must print `0374a2c8…`.
    - §12.4: "If a gate rejects those bytes, stop and report BLOCKED."
    - §14: "Verify the native `__init__` SHA-256 after any change near it."
  - **The repo:**
    - `git config core.autocrlf` is `true`.
    - There is no root `.gitattributes`; only `contracts/` and `lint/contracts/` have one.
    - Working copies are CRLF, request.md included.
  - **Measured:** request.md:155-164 hash to `0374a2c8…942f497a` with LF endings (911 bytes) and to `fbf12a15…af2e42` with CRLF endings.
  Failure:
  - In any fresh checkout or worktree on this machine, the working copy is CRLF and the command prints `fbf12a15…` for correct committed bytes. That covers the orchestrator's check, the reviewers, and a catch-up merge that touches the file.
  - The result is a false BLOCKED, or an implementer "repairing" correct bytes.
  - S2 may hash the file from disk to prove AC-36. That test would pass on Linux CI and fail the local gate.
  Smallest fix:
  - Hash the blob in §11, §14 and AC-36: `git cat-file -p :vidbyte/harnesses/native/__init__.py | python -I -c "import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())"`. Use the staged blob, or `HEAD:` after commit.
  - Add a §13 fact: a test that checks these bytes normalizes `\r\n` to `\n` before hashing.

R-9 [Major] [L4] NG-12 / Q-1 / NFR-10 — Adding about 400 lines to the 1,205-line dataclass module contradicts AGENTS.md:31 and the spec's own §12.4 checkbox
  Evidence:
  - **The spec:**
    - NG-12: "Splitting the 1,205-line Codex dataclass module. *Why not:* request.md §C places the new records there".
    - Q-1: "now 1,205 lines and growing past 1,600".
    - NFR-10 checks "each new file" only.
    - §12.4: "Every file stays under 1,000 lines, and is split along subsystem lines before it grows past that."
  - **The repo:**
    - AGENTS.md:31: "when a file heads toward four digits, split it into smaller modules along subsystem lines before adding more".
    - `git show HEAD:vidbyte/lib/dataclasses/codex.py | wc -l` gives 1205.
    - No lint rule caps file length, so only review will catch this.
    - request.md:275's "existing module" line is R2's restatement of the placement rule. It is not one of the user's settled decisions.
  Failure:
  - S3 grows a file that AGENTS.md already says to split and ticks a §12.4 box that is false.
  - The placement rule says "`<domain>` names the feature or subsystem", so a host-records module complies with it.
  Smallest fix:
  - Put the 15 host records in a new `vidbyte/lib/dataclasses/codex_host.py`, with its own `Codex*` `__all__`, importing the existing settings records.
  - Leave `codex.py` untouched, with no split of existing code.
  - Update §4's import, row 6, §9.1, D-26, NG-12, Q-1 and §8.4 (18 files).
  - The enum module (120 lines) and the constants module (267 lines) stay where they are.

R-10 [Minor] [L10] D-1 / §13 — "Public `CodexClient`" is overstated, and the "SDK contract tests" D-1 relies on are never assigned
  Evidence:
  - **The spec:** D-1: "`CodexClient` and every method used have public names … No private attribute is touched. | … | A pin bump renames `CodexClient` methods; the SDK contract tests catch this". §13 lists prior art only.
  - **The SDK:**
    - `openai_codex/__init__.py:40` imports only `CodexConfig` from `.client`, so `CodexClient` is not in `__all__`.
    - `start_goal_operation` returns the private `_GoalOperationState` (`_goal.py:37`).
    - `CodexGoalFinishRule` mirrors the private `_GoalStreamCursor.process` (`_goal.py:249`).
  - **The request:** request.md:235 says private reach is "acceptable only under the existing `<0.163` pin, with a contract test".
  Failure: a 0.162.x patch could move `CodexClient`, rename a method or change the goal cursor. The fake-client suite would still pass, and the break would show only in live use.
  Smallest fix:
  - Reword D-1: `CodexClient` is a non-exported class in `openai_codex.client`, and the goal state type is private.
  - Add a §13 bullet for a `skipUnless(find_spec("openai_codex"))` test that:
    - imports `openai_codex.client.CodexClient`;
    - checks `inspect.signature` for every §12.4 method, including `request_with_retry_on_overload(…, max_attempts=)`;
    - asserts that `_GoalStreamCursor.process` still exists.

R-11 [Minor] [L5] D-23 / EC-44 — The review registration race is only half closed, so a successful review can end FAILED with `response_invalid`
  Evidence:
  - **The spec:**
    - D-23: "its turn is registered right after the response, and the review thread is read back with its turns to close the registration race".
    - EC-44 covers only "the review turn completes before the host registers".
  - **The SDK:** `_message_router.py:196:_prune_turn_events` drops a turn's events when the turn has no subscriber and its thread has no pending turn request. Raw `review/start` opens no `pending_turn`, unlike the typed `turn_start`.
  Failure:
  - The review's final `item/completed` arrives before registration and is pruned.
  - Its `turn/completed` arrives after the read-back.
  - The watcher finalizes with no final answer, giving FAILED `codex.response_invalid` (INV-20) for a review that succeeded.
  Smallest fix:
  - When a registered review turn completes, build its result from a `thread/read` of that turn, or merge the read-back items, before applying INV-20.
  - Add this case to EC-44.

R-12 [Minor] [L5] §9.2 exception table — "Any other `CodexError` → `protocol_mismatch`" misclassifies the goal-start timeout and puts raw stdout into messages after reader death
  Evidence:
  - **The spec:**
    - §9.2: "any other `CodexError` (for example the runtime-version gate, or the goal-start timeout) | `protocol_mismatch` | the exception's message".
    - The next step for that code: "Match the Codex CLI and openai-codex versions (codex update)…".
  - **The SDK:**
    - `client.py:636-641` raises `CodexError("timed out waiting for goal turn to start after 30 seconds")`.
    - `client.py:916` raises `CodexError(f"Invalid JSON-RPC line: {line!r}")`, and `_reader_loop` (:880-881) hands it to `fail_all`, so every waiter receives it.
  Failure:
  - A slow runtime that misses the 30 s goal start is told to update its versions. That is a TERMINAL code for a transient fault.
  - A corrupted stdout line kills the reader. Every in-flight call then raises `protocol_mismatch` with the raw line in its message, which is an INV-9 risk. Meanwhile D-27 finalizes the turns as `process_exited`.
  Smallest fix:
  - Map the goal-start timeout to `codex.api_error`.
  - Once the connection has seen the reader die, map every exception it delivered to `codex.process_exited` with fixed text, never the exception's message.

R-13 [Minor] [L9] §12.3 rows 3, 7, 24, 26 / §12.4 / §12.5 / INV-29 — Stale rationale and two inaccurate reuse statements
  Evidence:
  - **(a) The export-list rationale is stale.** Rows 3, 24 and 26, §12.4 ("It replaces request.md §C's "append-only" wording, which is wrong for these files") and §12.5 all argue against wording that request.md:173-174 no longer has. The request now reads "insert only your own entries … Put each new entry where the file's own ordering puts it".
  - **(b) Row 7 miscounts the messages.** It says "the existing name loop with the same three messages", but the loop at `vidbyte/agents/codex/tools.py:65-72` raises two. The third, at :60-63, reads `settings.codex.client.experimental_api`, which `validate_names(catalog)` cannot see.
  - **(c) The reused message names the wrong path.** INV-29 and EC-49 reuse "Codex harness agent tools require codex.client.experimental_api=True." for the host, whose setting is `CodexHost(settings=CodexClientSettings(experimental_api=True))`.
  Failure: none of these breaks the build. An implementer could still move the experimental-API check into `validate_names`, which has no settings, or show developers a wrong field path.
  Smallest fix:
  - Cite the revised request.md §C as the source of the sorted rule.
  - Change row 7 to "two messages; `translate` keeps the experimental-API check".
  - Give the host its own message constant naming `CodexClientSettings.experimental_api`.

VERIFIED CLAIMS:
- **D-1, a "public `CodexClient`"** — partly held.
  - The methods and the `openai_codex.client.CodexClient` name have no underscore.
  - The class is not in `openai_codex.__all__` (`__init__.py:40`), and goal ops use the private `_GoalOperationState` (R-10).
- **D-2, typed methods taking full params** — held. `thread_start`, `thread_resume` and `thread_fork` accept `V2*Params | JsonObject` (`client.py:478-511`), and `thread_read` always sends `includeTurns`.
- **D-2, retry semantics** — held.
  - `request_with_retry_on_overload(method, params, *, response_model, max_attempts=3, …)` (`client.py:731-746`) retries only when `is_retryable_error` (`errors.py:112`) is true.
  - `max_attempts=1` is valid; `retry.py:22` rejects values below 1.
- **§12.4 S012 analysis** — held. `REQUEST_METHODS` is request/request_bytes/stream_request/upload_multipart/urlopen, with timeout keywords `timeout`/`timeout_seconds`. `request_with_retry_on_overload` is not matched, and the §12.4 call list has no `request(` call.
- **S045** — held. ruff ASYNC109 at py311 flags only a parameter named exactly `timeout`, so `timeout_seconds` passes. `lint/ruff.toml` sets `target-version = "py311"`.
- **S054** — not addressed by the spec. Its baseline is 3 and the current count is 3 (R-1).
- **Gap-free typed `turn_start`** — held (`_message_router.py:145/159/196`).
- **Raw `review/start` unprotected (D-23 premise)** — held.
- **`CodexClient` safe for concurrent worker threads** — held. Writes are under `self._lock`, each request has its own router waiter, and `AsyncCodexClient` itself wraps every method in `to_thread`.
- **The reader answers server requests synchronously** (`client.py:863-881`) — held. This is the root of R-3.
- **INV-28/AC-30, the default approval answers** — held. The answers are `{"decision": "accept"}` for the two approval methods and `{}` otherwise (`client.py:833-838`).
- **`CODEX_APPROVAL_MODE_WIRE` matching `ApprovalMode`** — held (`_approval_mode.py:16-35`).
- **A-1, the Windows launcher** — launch plausible; "terminate stops the app-server" false as stated (R-4).
  - `codex.cmd` runs node `codex.js`, which runs `codex.exe` with stdio inherit.
  - `close()` terminates only the launched process.
- **D-29 and the fork field rules** — held. `last_turn_id` is "fork through, inclusive … cannot be in progress", `exclude_turns` only shapes the response, and `ThreadForkParams` has no personality.
- **The continue column of the field rules** — held. It matches the fields of `ThreadResumeParams`.
- **D-8** — held. `ThreadGoalSetParams.token_budget` exists, and `thread_goal_set` has no budget parameter.
- **The goal machinery** — held.
  - `start_goal_operation` has a 30 s start window (`client.py:70, 636`), cleans up on failure, and requires an idle persisted thread.
  - `_terminal_goal_status` covers paused, blocked, usage_limited, budget_limited and complete, matching the §9.2 goal table.
- **D-28 rate-limit semantics** — held. `GetAccountRateLimitsResponse.ordinary_usage_allowed` reads "Null means unavailable; clients must not infer recovery".
- **D-5** — held. `MINIMUM_RUNTIME_VERSION = "0.151.0"`.
- **Row 1 and AC-29** — held.
  - `failure.py:46` is `CODEX_RUN_OPTION_UNSUPPORTED`, the last `CODEX_*` member.
  - Only `tests/test_codex_failure_recovery.py:194,200` and `tests/test_session_failures.py:139` enumerate `FailureCode`.
- **Row 6** — held. `lib/dataclasses/codex.py` has 1,205 lines, with `CodexSdkTypes` at 1185 and the `__all__` comprehension at 1205. `PermissionPolicy` is a lib type (`lib/dataclasses/security.py:30`), so there is no A006 issue.
- **Rows 2, 3, 24 and 26 sort positions** — held.
  - The enum `__all__` is alphabetical after `CodexFailureClass`.
  - The enums `__init__` Codex import block is at 41-51 and its `__all__` entries at 153-161.
  - The builtins `__init__` imports `code_search` at line 30 and `context` at 31.
  - `CodexHostTools` sorts before `CodingAgentTools`.
- **Rows 27 and 28 anchors** — held.
  - REPO_MAP has `#### vidbyte/harnesses/` at 147 and the stores heading at 151.
  - The README "Key modules" list ends with the `serialization.py` bullet at 177.
  - The §12.5 README bullet is byte-identical to request.md:188; the REPO_MAP paragraph is not (R-2).
- **§11, the README is "8,805 characters"** — held for the CRLF working copy only; the LF blob is 8,625. Either way it is far under A009's 40,000, so this is harmless.
- **The native `__init__` SHA** — held for LF bytes only (R-8).
- **EC-50 and the registry** — held. `ComponentRegistry._discover` collects every public `BaseTool` in `vidbyte.tools.builtins`, and no test enumerates the registry, so 15 tools with required arguments break no existing test.
- **The `codex` binary version** — `codex --version` prints `codex-cli 0.162.1`. request.md:192's "0.161.0" is stale, but the spec depends on neither number.
- **The §11 gate commands, `McpStudioServer.run()` being async (AC-27), and the reuse anchors** — held. The anchors are `CodexMetricsTranslator._model_name` and `UsageTracker`.
- **"No README" for new folders** — defensible. C015 forbids shipping READMEs, and 32 of the 106 code folders under `vidbyte/` carry one.
