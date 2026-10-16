# Feature: CodexHost, small atomic Codex functions with one agent tool per function

## High-Level Feature Description

A developer opens `CodexHost()` with `async with`, and the host runs one `codex app-server` process through openai-codex 0.162. Twenty-seven small async methods sit on the host. The first fifteen come from `docs/spec/codex-host/spec.md`: check readiness, read rate limits, list models, spawn, continue and fork threads, list and read threads, wait on, get, steer and interrupt a turn, track a thread's usage, launch several subagents, and start a review. The twelve thread helpers come from `docs/spec/codex-host-thread-helpers/spec.md`: list recent threads, threads changed since a time and threads that match a search; walk a thread's lineage; list its stored turns; compact a thread, delete it and read its goal; and run a goal, list skills, run a skill and run the bundled `openai-docs` skill. Spawn returns a handle as soon as Codex accepts the turn, and the result comes later. Every failure is a `CodexAgentError` with a semantic code and a next step. `CodexHostTools(host, max_live_turns=N)` exposes twenty-six of the functions as agent tools: every one except `delete_codex_thread`, which no model may reach. Six module functions open a host for one call.

If this feature regresses, three things can go wrong. An agent can spend the user's Codex plan without control: a turn nobody owns, a cap that never fires, or a `user` reviewer that silently approves every escalation. A host call can hang, or a stack trace can reach the model. Or private data (the account email, environment values, the app-server's stderr) can leak into an error or a tool result.

## Contract

- Importing `vidbyte`, `vidbyte.harnesses.native.codex`, the builtins and the toolsets never loads openai-codex. Entering a host without the SDK raises `codex.not_installed` with a `pip install "vidbyte-sdk[codex]"` next step (INV-1, AC-2).
- Open resolves `codex` with `shutil.which` and refuses versions below 0.151.0, or ones it cannot parse. A failed open closes what it started (INV-3 to INV-5).
- Spawn, continue, review and launch run their preflight checks before the first spending request. They return a handle at acceptance and register every turn before returning it (INV-12 to INV-14).
- Each turn ends exactly once: COMPLETED, INTERRUPTED or FAILED. A wait never raises because time passed. A timeout or an output cap sends exactly one interrupt (INV-15 to INV-19).
- Only `CodexAgentError`, `ConfigurationError` and `CancelledError` escape. Tools never raise, and they report `"<code>: <message> Next step: <next_step>"` (INV-8, INV-10).
- A `user` reviewer fails closed: at construction, and after `thread/start` or `thread/resume` reports one (D-16, D-32).
- Close cancels running tool calls, finalizes and interrupts running turns, closes goal streams in openai-codex's order, and then closes the process on a daemon thread (INV-7).
- The thread helpers (thread-helpers spec) send no preflight request. The listing helpers send `sortKey`, `sortDirection: "desc"`, the five `sourceKinds` other than `subAgent`, and the count still missing as `limit`. The walk follows cursors until it has `limit` threads, a cursor repeats, the list ends or 1000 pages pass, and it never returns a thread twice (INV-10 to INV-14).
- A lineage walk reads each ancestor without turns. It stops at a missing or refused ancestor, at a cycle, or after 100 summaries, and a timeout propagates (INV-16).
- Compact and delete refuse a thread that runs a turn on this host before any request, and a thread Codex reports `active` after one read. Compact checks the goal of a `notLoaded` thread before it resumes it, and refuses an unfinished goal. No READ helper sends `thread/resume` (INV-8, INV-18, INV-33).
- A goal run or a skill run returns a handle only when Codex shows that the goal or the skill entry took. Otherwise the run is stopped exactly once, and `codex.command_not_run` is raised (INV-21, INV-22, INV-34, INV-35). No tool deletes a thread (INV-2).

## Actors / Callers

- Python callers using `CodexHost` and the six module functions.
- Agents calling the twenty-six tools through `ToolExecutor`.
- MCP clients reaching the tools through `McpStudioServer`.
- Codex threads calling dynamic tools through the server-request router.

## Inputs and Preconditions

- `CodexClientSettings` on the host, `CodexSpawnRequest` and the other new records, and the model's JSON tool arguments.
- The app-server is replaced at the spec section 13 seam, `vidbyte.harnesses.native.codex.connection.CodexClient`, by `codex_host_fakes.client_class(server)`. That class subclasses the real `openai_codex.client.CodexClient` and swaps only the subprocess for an in-memory pipe. The SDK's reader thread, message router, retry helper and goal routing all run for real.
- `shutil.which` is patched to return a fake absolute path, so nothing is ever executed. No test starts `codex` or touches the network (NG-13).

## Observable Outcomes

- The JSON-RPC requests the fake receives: method, params, order, and the thread that wrote each one.
- The fake's log of client lifecycle and goal cleanup calls: start, close, any write attempted after close, `cancel_goal_operation`, `finish`, `wake_notification_reader`, `unregister_goal_operation`, and the goal watcher's reads.
- The answers the client writes to server requests.
- The records the host returns, and the code, operation, message and next step of each error raised.
- Tool `ToolResult` status, output and metadata.

## State Transitions

- **Host:** NEW, then OPEN, then CLOSING, then CLOSED. Process death moves OPEN to DEAD. A failed open goes from NEW straight to CLOSED. A closed host never reopens.
- **Turn:** RUNNING from acceptance, then exactly one of:
  - COMPLETED, when Codex completes it with a final answer;
  - INTERRUPTED, with the stop reason only when Vidbyte sent the interrupt;
  - FAILED, with a mapped problem, `codex.response_invalid`, or `codex.process_exited` on close or death.

  Goal runs follow the section 9.2 goal table.

## Invariants

- No request that spends (`thread/start`, `thread/resume`, `turn/start`, `review/start`, goal requests) follows a failed preflight check, a record that is invalid, or a refused reviewer.
- A turn Codex accepts is never left unowned. A start accepted after its caller left gets exactly one interrupt, and a start still queued is never sent.
- No account email, environment value, stderr text or raw stdout line appears in any error, record or tool output.

## External Dependencies

- openai-codex 0.162.1, the optional `codex` extra. The test modules that need it skip without it, as CI installs only `.[dev]`.
- The real `CodexContentTranslator`, `CodexResultSerializer`, `CodexMetricsTranslator`, `UsageTracker`, `ToolExecutor`, `PermissionPolicy`, `Tools` and `McpStudioServer`.

## Known Failure Modes

Each line reads input + state → wrong output.

- A spawn with no approval fields, sent without the `on-request` plus `auto_review` default → Codex's default `user` reviewer → every escalation is auto-accepted.
- A continue on a thread whose reviewer is `user` → the turn starts → approvals are silently accepted (EC-76).
- The output cap is compared with the thread's cumulative output, not the turn's own → the second turn on a busy thread is interrupted at once.
- A timeout interrupt fails, but the turn is still labelled `turn_timed_out` → a wrong stop reason.
- `review/start` is retried on overload → two paid reviews.
- A review whose events arrive before registration → no read-back → the wait hangs, or the turn ends `response_invalid`.
- The goal budget echo is not checked, or the cleanup order is wrong → a goal keeps running without its budget, and later turns on that thread are refused.
- A spawn is cancelled while `turn/start` is in flight → the accepted turn runs unowned and spends the plan.
- A host call runs on the loop's default executor → a silent app-server starves the developer's own executor.
- A death message carries the SDK exception's text → stderr or a raw stdout line reaches the model.
- The router raises on a bad server request → the SDK reader thread dies, and with it the host.
- A fork of a thread with dynamic tools gets no tool handler → Codex's tool calls on the fork fail with the unregistered-tool text.
- The wait tool waits 300 s or more → the calling bridge cuts it off first.
- The refusal of an unusable `output_schema` carries the library's exception text or chains it → pydantic's text reaches the caller and, through the tool result, the model.
- An `output_schema` mapping with a cycle under `properties` or `items` → a RecursionError escapes the host and the spawn tool instead of a refusal.
- A stop that failed blocks every later `interrupt_codex_turn` → the turn the caller asked to stop keeps running and spending.

The thread helpers add these (thread-helpers spec):

- A listing without `sourceKinds` → subagent threads appear among the recent threads.
- The walk sends the caller's `limit` on every page, not the count still missing → more threads than asked for, or wasted pages.
- The walk trusts every `nextCursor` → a repeated cursor, or endless new ones, loop forever.
- `limit=0` is dropped as falsy, `True` passes as 1, or `since=1.5` is compared with integer times → Codex's own page size, or a silent wrong window.
- A blank search query is dropped as falsy → every thread "matches".
- The since filter is exclusive, or the walk goes on past the first older thread → the boundary thread is lost, or pages are wasted.
- An empty `name` becomes `""`, `parentThreadId` wins over `forkedFromId`, or a null `model` stays None → wrong summary fields.
- Lineage raises on a deleted ancestor, loops on a cycle, has no depth bound, or swallows a timeout as the end of the chain → an error, a hang, or a short chain that looks complete.
- The turn listing passes reasoning `content` through → private reasoning reaches the caller and the model.
- The turn listing or the goal read resumes a `notLoaded` thread → Codex can continue an unfinished goal as untracked turns.
- Compact resumes a `notLoaded` thread with an unfinished goal → untracked, uncapped goal turns.
- Compact holds no registry reservation, or keeps it after a failure or a cancel → a continue slips in during the compaction, or the thread stays busy forever.
- A goal run reads nothing back, or compares only the objective → a goal without its budget keeps spending. A mismatch with no cancel → the goal keeps running.
- A skill match that ignores case, takes a disabled duplicate, or lists every installed skill in the error → the wrong skill, a refused skill, or an unbounded message.
- A skill run with no read-back → Codex drops the skill entry, and the caller gets a handle for a plain prompt. A read-back with no deadline or attempt cap → it waits forever.
- A skill run on an ephemeral thread → the read-back can never confirm it, so it always spends and then fails.
- The turns tool sends no default `limit` → a whole transcript lands in one tool result.
- A run tool takes no cap slot, or keeps it after a failure → the cap never fires, or it fills up forever.
- A delete tool exists → a prompt-injected model deletes the user's history.
- A skill path, a skill description or a goal objective is copied into an error → private paths and text reach the model.

## Historical Regressions

None yet. Add one line per fixed bug, with the test that protects it.

## Test Suite Map

- `test_codex_host_records.py` checks each record's validation rules as an invalid-record table, with exhaustive tables for the review target kinds and snapshot states. It also covers the USER reviewer refusal, the new failure codes with their rows and next steps, the section 9.3 constants, `next_step` on `CodexAgentError`, and the enum wire values. It is CI-visible, except one test that cross-checks the wire values against the SDK.
- `test_codex_host_packaging.py` checks import safety in a fresh interpreter (AC-2, INV-1), the native marker's bytes (AC-36), the export lists, and the REPO_MAP and README texts. It is CI-visible, except one test that needs the SDK installed to prove the imports leave it unloaded.
- `test_codex_host_bridge.py` checks `CodexToolTranslator.validate_names` and `CodexToolBridge.handler`. It is CI-visible.
- `test_codex_host_tools.py` checks the toolset's shape and permissions, error results, the live-turn cap and ownership, `spawn_defaults` with JSON `null`, argument checks, output shapes, the wait clamp, and MCP. It runs over a stub host and is CI-visible.
- `test_codex_host_lifecycle.py` covers the section 4 snippet, binary resolution, the version gate, the call guards, close order (turns, tool calls, goal runs), D-1 thread use, and the module functions.
- `test_codex_host_turns.py` covers spawn params, preflight, waits, results, the timeout and the output cap, process death, the turn-error table, structured output, steer, interrupt, and usage tracking.
- `test_codex_host_threads.py` covers continue, the field rules, fork, list and read, readiness with rate limits and models, the effective-reviewer check, dynamic tools (a fork's inherited tools included), and the `agents` config.
- `test_codex_host_review_goals.py` covers review (single attempt, both registration races, detached delivery) and goal runs (budget, echo mismatch, cleanup order, goal states).
- `test_codex_host_failures.py` covers late acceptance, the queued start that is withdrawn, a start accepted after close, and privacy canaries.
- `test_codex_host_router.py` covers the server-request router on the real reader thread.
- `test_codex_host_sdk_contract.py` pins the openai-codex surface that the host reaches outside the public API.
- `test_codex_host_review_gaps.py` covers the windows the S4 review found open (review.md R-1, R-2, R-6, R-7, R-10, R-12, R-13 and R-14): a review cancelled during its read-back, a cancelled launch or close, an unusable `output_schema`, a start still in flight when its caller left, the problem a late-accepted turn or goal run ends with, and a mapping `output_schema` that is only parsed as JSON. Its host classes need the `codex` extra; its launch tool class runs over a stub host and is CI-visible.
- `test_codex_host_review_gaps.py` also covers the S5 re-review findings (review.md R-26 and R-27): an unusable `output_schema` refused with no library text and no cause, a schema whose walk never ends refused before any request, and a user interrupt after a stop that failed or while one is in flight. These classes need the `codex` extra, so CI skips them.
- `test_codex_host_helper_surface.py` checks the thread-helpers surface: the five new records and their validation, `CodexSkillScope`, the four new failure codes and twelve new operations in place, the section 9.3 constants and the message texts, and the twelve host method signatures in order. It is CI-visible.
- `test_codex_host_helper_tools.py` checks the eleven new tools over a stub host: the 26-tool order with no delete tool, schemas and permissions, argument checks before the host, the default limits, the run tools' cap slot and ownership, error results with the new next steps, and the JSON or text outputs (AC-33, AC-41). It is CI-visible.
- `test_codex_host_thread_helpers.py` covers the listing walks (params, cursors, the page bound, since and search), the summary mapping, lineage, the turn listing, compact with its goal check, delete, the busy and unknown refusals, and the compact reservation (AC-2 to AC-23, AC-38).
- `test_codex_host_goal_skills.py` covers `get_codex_goal`, the goal run and its read-back, the skill listing, the skill run and the docs run with the bounded read-back, and the stop sent on every miss, failure and cancel (AC-24 to AC-32, AC-39, AC-40, AC-42, AC-43).
- `test_codex_host_helper_lifecycle.py` covers the thread-helpers section 4 snippet, the call guards, no preflight and no resume on the READ helpers, `-32601` per method, and the privacy canaries (AC-1, AC-34, AC-37).
- The seven modules from `test_codex_host_lifecycle.py` to `test_codex_host_sdk_contract.py` need the `codex` extra, so CI skips them. So do `test_codex_host_thread_helpers.py`, `test_codex_host_goal_skills.py` and `test_codex_host_helper_lifecycle.py`.
- `codex_host_support.py` holds the spec literals, canaries, `HostTestCase` and `StubCodexHost`. `codex_host_fakes.py` holds the in-memory app-server.

Run it with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host`, from the worktree root, with the venv that has the `codex` extra.

## Omitted Testing Strategies

- **Property-based and fuzz:** `hypothesis` is not a dependency. The algebraic rules (the review-target kinds, snapshot states, the field rules and the error tables) are exhaustive tables over their small domains.
- **Live Codex runs:** these spend the user's plan and CI has no credentials (NG-13). AC-1 is proven at the seam, and a live run is manual QA.
- **Windows npm launcher process trees (EC-3, EC-69) and long silences (EC-5, EC-35, EC-70):** they need a real process or a 300 s wait. The bound itself is proven by patching it small.
- **Load and stress:** the host keeps per-turn state for its lifetime (EC-65), and no limit depends on volume.
- **The controls not built (Q-7, Q-8, Q-9):** there is nothing to test.
- **A transcript of an ephemeral thread (thread-helpers EC-49):** the fake could only repeat assumption A-21, so a test would prove the fake, not Codex.
- **The accepted thread-helpers limits (EC-19, EC-20, EC-21, EC-33, EC-41, EC-43, EC-44):** they describe what Codex does after an accepted request, so the fake would only replay the assumption.
- **A live goal run, skill run or `openai-docs` run:** each spends the user's plan (NG-15). AC-1 is proven at the seam.
- **The sentence counts of the new tool descriptions (NFR-7):** a count of sentences says nothing about meaning, so review checks them.
