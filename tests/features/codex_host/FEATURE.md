# Feature: CodexHost, small atomic Codex functions with one agent tool per function

## High-Level Feature Description

A developer opens `CodexHost()` with `async with`, and the host runs one `codex app-server` process through openai-codex 0.163. Twenty-eight small async methods sit on the host. The first fifteen come from `docs/spec/codex-host/spec.md`: check readiness, read rate limits, list models, spawn, continue and fork threads, list and read threads, wait on, get, steer and interrupt a turn, track a thread's usage, launch several subagents, and start a review. The twelve thread helpers come from `docs/spec/codex-host-thread-helpers/spec.md`: list recent threads, threads changed since a time and threads that match a search; walk a thread's lineage; list its stored turns; compact a thread, delete it and read its goal; and run a goal, list skills, run a skill and run the bundled `openai-docs` skill. The hardening slice (`docs/spec/codex-host-hardening/spec.md`) adds the local `forget_codex_turns`; an optional async `approval_handler` keyword on `CodexHost`, which answers command, file-change and user-input requests while every other server request gets a fixed fail-closed answer; overload retries of four idempotent reads; redacted logs; and the turn settings `turn_service_tier`, `network_access`, `writable_roots` and the `max` and `ultra` efforts. Spawn returns a handle as soon as Codex accepts the turn, and the result comes later. Every failure is a `CodexAgentError` with a semantic code, a next step and a derived `retryable`. `CodexHostTools(host, max_live_turns=N)` exposes twenty-six of the functions as agent tools: every one except `delete_codex_thread`, which no model may reach, and `forget_codex_turns`, which is local and toolless. Six module functions open a host for one call.

If this feature regresses, three things can go wrong. An agent can spend the user's Codex plan without control: a turn nobody owns, a cap that never fires, a paid call sent twice, or an approval request accepted that nobody approved. A host call or a wait can hang, or a stack trace can reach the model. Or private data (the account email, environment values, the app-server's stderr, a prompt or a command) can leak into an error, a tool result or a log record.

## Contract

- Importing `vidbyte`, `vidbyte.harnesses.native.codex`, the builtins and the toolsets never loads openai-codex. Entering a host without the SDK raises `codex.not_installed` with a `pip install "vidbyte-sdk[codex]"` next step (INV-1, AC-2).
- Open resolves `codex` with `shutil.which` and refuses versions below 0.151.0, or ones it cannot parse. A failed open closes what it started (INV-3 to INV-5).
- Spawn, continue, review and launch run their preflight checks before the first spending request. They return a handle at acceptance and register every turn before returning it (INV-12 to INV-14).
- Each turn ends exactly once: COMPLETED, INTERRUPTED or FAILED. A wait never raises because time passed. A timeout or an output cap sends exactly one interrupt (INV-15 to INV-19).
- Only `CodexAgentError`, `ConfigurationError` and `CancelledError` escape. Tools never raise, and they report `"<code>: <message> Next step: <next_step>"` (INV-8, INV-10).
- A `user` reviewer fails closed on a host without an `approval_handler`: every spawning or continuing call refuses it before any request, and so does a `thread/start` or `thread/resume` that reports one (hardening INV-20 and D-5 moved the refusal out of record construction). With a handler it is allowed, and its approvals reach the handler.
- Close cancels running tool calls, finalizes and interrupts running turns, closes goal streams in openai-codex's order, and then closes the process on a daemon thread (INV-7).
- The thread helpers (thread-helpers spec) send no preflight request. The listing helpers send `sortKey`, `sortDirection: "desc"`, the five `sourceKinds` other than `subAgent`, and the count still missing as `limit`. The walk follows cursors until it has `limit` threads, a cursor repeats, the list ends or 1000 pages pass, and it never returns a thread twice (INV-10 to INV-14).
- A lineage walk reads each ancestor without turns. It stops at a missing or refused ancestor, at a cycle, or after 100 summaries, and a timeout propagates (INV-16).
- Compact and delete refuse a thread that runs a turn on this host before any request, and a thread Codex reports `active` after one read. Compact checks the goal of a `notLoaded` thread before it resumes it, and refuses an unfinished goal. No READ helper sends `thread/resume` (INV-8, INV-18, INV-33).
- A goal run or a skill run returns a handle only when Codex shows that the goal or the skill entry took. Otherwise the run is stopped exactly once, and `codex.command_not_run` is raised (INV-21, INV-22, INV-34, INV-35). No tool deletes a thread (INV-2).

The hardening slice adds these (`docs/spec/codex-host-hardening/spec.md`; the IDs below are that spec's):

- Every server request gets exactly one answer, and the router never raises. Without a handler, approvals are declined, user input gets no answers, permissions grant nothing, and unknown requests get `{}`. With a handler, only command, file-change and user-input requests reach it, on the host's own loop; a parse failure, an error, a timeout, a non-answer or an answer that does not fit the request falls back to the default answer with one WARNING (INV-15 to INV-19, INV-21).
- An error names the thread it left behind, and a failed spawn, launch or fork name-set unregisters that thread's dynamic tools (INV-1, INV-26, INV-28).
- `retryable` is derived from the code and never stored in `details`. Only `account/read`, `thread/read`, `thread/list` and `thread/name/set` are retried on overload; every spending or state-changing call is sent once (INV-2, INV-3, INV-43).
- `thread/read` means not found only when Codex refuses it (-32600 or -32602); an internal error or a lasting overload is `codex.api_error`, and a lineage walk raises it instead of ending early (INV-4, INV-5).
- A failing event, a lost watcher or a failing review completion ends the turn `FAILED` with one stop, so `wait_codex_turn` with no timeout always returns; a process death is still `codex.process_exited` and is not a lost turn (INV-11 to INV-14, INV-45).
- Every call, server request, turn item and turn end is logged once, %-style, with ids and labels only; no prompt, command, canary or exception text reaches a record (INV-7 to INV-10).
- Tools never raise: an unexpected exception under a tool is a `codex.api_error` result naming the tool and the exception type, plus one WARNING with its origin (INV-23).
- An error escaping `run_codex_goal`, `run_codex_skill` or `run_codex_openai_docs` carries the wrapper's operation in its field and message head, with every other field kept (INV-31).
- Fork runs its checks in a fixed order; `before_turn_id` excludes `from_turn_id`, and it and `defer_goal_continuation` need the experimental API. Only `read_codex_thread` asks Codex for a thread's full history; fork points and review read-backs use `thread/turns/list` pages (INV-28, INV-38).
- A goal run refuses every turn-only field when the request is built; a service tier is checked against the tiers `model/list` reports unless a custom provider is set; network access and writable roots go into the turn's sandbox policy and are refused on fork and review (INV-34 to INV-37).
- Continue refuses a `notLoaded` thread whose stored goal is unfinished, readiness reports used-up usage, a model or tier the cached list lacks costs one fresh walk, and `forget_codex_turns` releases an idle thread's ended turns without a request (INV-22, INV-24, INV-25, INV-27).

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

- openai-codex 0.163.0, the optional `codex` extra, pinned `>=0.163.0,<0.164.0` by the hardening slice (INV-39). The test modules that need it skip without it, as CI installs only `.[dev]`. `test_codex_host_sdk_contract.py` pins the 0.163.0 surface the host reaches, so it is the first file to rerun after a pin bump.
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
- Delete holds no registry reservation, or keeps it after a failure or a cancel → a continue or a review starts a paid turn on a thread being deleted, or the thread stays busy forever.
- A goal run reads nothing back, or compares only the objective → a goal without its budget keeps spending. A mismatch with no cancel → the goal keeps running.
- A skill match that ignores case, takes a disabled duplicate, or lists every installed skill in the error → the wrong skill, a refused skill, or an unbounded message.
- A skill run with no read-back → Codex drops the skill entry, and the caller gets a handle for a plain prompt. A read-back with no deadline or attempt cap → it waits forever. A read-back that accepts a skill entry of another name or case, or the input of another turn → a run Codex never confirmed returns a handle.
- A skill run on an ephemeral thread → the read-back can never confirm it, so it always spends and then fails.
- The turns tool sends no default `limit` → a whole transcript lands in one tool result.
- A run tool takes no cap slot, or keeps it after a failure or a cancel (the goal tool included) → the cap never fires, or it fills up forever.
- A delete tool exists → a prompt-injected model deletes the user's history.
- A skill path, a skill description or a goal objective is copied into an error → private paths and text reach the model.

The hardening slice adds these (codex-host-hardening spec):

- A command or file-change approval on a host without a handler is answered `accept` → every escalation runs unasked.
- A handler that raises, hangs, returns a dict, picks a decision Codex did not offer, or answers an unknown question → the SDK reader thread dies, the request is never answered, or Codex gets an answer it cannot use.
- Permission, MCP-elicitation or legacy approval requests are routed to the handler → code grants permissions the spec keeps fixed.
- A handler is built from a sync function or a lambda → the reader thread blocks on it, or the host starts a process before refusing it.
- A handler call pending at close is left running, or a request arriving after close began reaches the handler → an answer from a closing host.
- A `user` reviewer is accepted on a host without a handler, or refused at record construction → silent approvals, or no way to build the request a handler host needs.
- A spawn whose first `turn/start` or `thread/name/set` fails raises without the thread id and keeps the tool registration → an orphan thread the caller cannot find, still answering tool calls.
- An overloaded `thread/start`, `turn/start` or `turn/steer` is retried → a paid call sent twice. An overloaded `account/read` is not retried → a spurious failure.
- `thread/read` answering -32603, or overloaded three times, is reported as not found → a live thread treated as gone, and a lineage walk that ends early looks complete.
- Processing a turn or goal event raises inside the loop callback, or the watcher's read fails → the turn never ends, and `wait_codex_turn` with no timeout hangs.
- A process death is handled as a lost watcher → a misleading WARNING, a cleanup interrupt written after close.
- A review's completion read-back raises a non-Codex error → the review never ends.
- A steer sent while the turn's interrupt is in flight → Codex refuses it as a protocol error instead of a clear not-found.
- An unexpected exception under a tool escapes → a stack trace reaches the model.
- A log record carries the prompt, the command, the account email or an exception message → private data in the operator's logs.
- A wrapper re-raises the inner call's error unchanged → the caller of `run_codex_goal` reads `get_codex_goal` as the failing operation.
- Continue loads a `notLoaded` thread whose goal is active → Codex resumes the goal as untracked paid turns.
- A goal request keeps a turn setting, an output schema, a tier or a sandbox field → the setting is silently ignored for every goal turn.
- An unlisted service tier is sent → Codex refuses only after `thread/start` created a thread.
- `network_access` with full access, or a relative writable root → a setting Codex ignores or refuses late.
- A fork takes both fork points, or sends experimental fields without the capability → Codex refuses after the checks that should have caught it, or forks from the wrong turn.
- A review or fork reads the thread with `includeTurns: true` → a whole transcript read for one item, on the path Codex 0.163 deprecates.
- Readiness ignores used-up usage → a host reports ready and its first spawn is refused. A cached model list is never refreshed → a newly enabled model is refused for the life of the host.
- `forget_codex_turns` drops a running turn, sends a request, or unregisters the thread's tools → a turn nobody owns, or a continued thread whose tools stop answering.

The first-class-features slice adds these (codex-host-first-class spec):

- A collaboration mode sent without the experimental API, or kept on a goal, review, launch or fork → Codex refuses after a thread exists, or drops the mode silently.
- A plan or mode turn priced as the spawn model instead of the model Codex resolved → a wrong cost. A settings change re-prices a running turn → its usage is split across two prices.
- `update_codex_thread_settings` sends unset fields → Codex resets settings the caller never named.
- The slice-2 load guard reuses compact's complete-only set → a paused goal blocks settings, memory, revert and inject, and the next step loops. It lets an active goal load → untracked paid goal turns.
- A stream keeps every event, or waits on a slow subscriber → unbounded memory, or a turn delayed by its reader. An abandoned or never-iterated subscription keeps the window → memory held until close.
- A stream event or log carries raw reasoning text → private reasoning reaches the caller.
- A side chat names, unsubscribes or injects into the parent, or skips the boundary item → the parent's history changes, or the fork answers as the main thread.
- A side chat on a fork whose approvals Codex routes to a person, on a host without a handler → approvals accepted unasked. A failed side chat keeps the fork's tools or its turn → an orphan turn spending the plan.
- The side-chat tool runs with a writable sandbox or asks the user → a prompt-injected model escalates through a read-only feature.
- The worktree folder is the raw branch name, git runs without a bound or with terminal prompts on, or git's stderr is copied whole into the error or a log → a path outside the root, a hang, or private paths in the logs.
- `resume_codex_goal` resumes a spent budget, or starts the run untracked → turns refused at once, or goal turns nobody caps. `pause_codex_goal` leaves a tracked goal run open → its wait never ends.
- Content search omits `sourceKinds` → the host's own app-server threads are never found.
- A tool exists for clear goal, revert, inject, reset memories or the terminal clean → a prompt-injected model destroys history or stops processes.
- An unmodeled answer is read without a check → an `AttributeError` deep in the host instead of `codex.protocol_mismatch`.
- `wait_codex_turns` interrupts or forgets its turns at the timeout → turns stop or lose their owner silently.

## Historical Regressions

- PR #1178 (codex-host-hardening AC-2 and AC-3): a spawn or launch whose `turn/start` failed raised without the new thread's id, and its tool registration stayed behind. Protected by `test_codex_host_resilience.py::CodexSpawnCleanupTests`, red until the hardening slice lands.

## Test Suite Map

- `test_codex_host_records.py` checks each record's validation rules as an invalid-record table, with exhaustive tables for the review target kinds and snapshot states. It also covers a USER reviewer request that now builds (hardening D-5), the new failure codes with their rows and next steps, the section 9.3 constants, `next_step` on `CodexAgentError`, and the enum wire values. It is CI-visible, except one test that cross-checks the wire values against the SDK.
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
- `test_codex_host_review_gaps.py` also covers the thread-helpers review finding R-18 (`docs/spec/codex-host-thread-helpers/review.md`): a launch that fails midway raises the mapped error with every field kept, `error_type` and `thread_id` included, plus the count of turns started (INV-37, AC-18, EC-52, D-22). It needs the `codex` extra, so CI skips it.
- `test_codex_host_helper_surface.py` checks the thread-helpers surface: the five new records and their validation, `CodexSkillScope`, the four new failure codes and twelve new operations in place, the section 9.3 constants and the message texts, and the twelve host method signatures in order. It is CI-visible.
- `test_codex_host_helper_tools.py` checks the eleven new tools over a stub host: the 42-tool order, with the eleven at rows 16 to 26 and no delete tool, schemas and permissions, argument checks before the host, the default limits, the run tools' cap slot and ownership, error results with the new next steps, and the JSON or text outputs (AC-33, AC-41). It is CI-visible.
- `test_codex_host_thread_helpers.py` covers the listing walks (params, cursors, the page bound, since and search), the summary mapping, lineage, the turn listing, compact with its goal check, delete, the busy and unknown refusals, and the compact reservation (AC-2 to AC-23, AC-38).
- `test_codex_host_goal_skills.py` covers `get_codex_goal`, the goal run and its read-back, the skill listing, the skill run and the docs run with the bounded read-back, and the stop sent on every miss, failure and cancel, with a failed check's error re-raised with every field it carried (AC-24 to AC-32, AC-39, AC-40, AC-42, AC-43; review R-17).
- `test_codex_host_helper_lifecycle.py` covers the thread-helpers section 4 snippet, the call guards, no preflight and no resume on the READ helpers, `-32601` per method, and the privacy canaries (AC-1, AC-34, AC-37).
- The seven modules from `test_codex_host_lifecycle.py` to `test_codex_host_sdk_contract.py` need the `codex` extra, so CI skips them. So do `test_codex_host_thread_helpers.py`, `test_codex_host_goal_skills.py` and `test_codex_host_helper_lifecycle.py`.

The hardening slice (`docs/spec/codex-host-hardening/spec.md`, test plan `docs/spec/codex-host-hardening/test-plan.md`) adds these:

- `test_codex_host_hardening_records.py` checks the three new enums and the `MAX`, `ULTRA` and `FORGET_CODEX_TURNS` members, the six wire-mirroring records, `CodexServerRequest.from_params` on full, sparse and broken params, the three new `CodexSpawnRequest` fields with the goal rule, and the tier fields of `CodexModelInfo` (AC-11, AC-29 to AC-32). It is CI-visible.
- `test_codex_host_hardening_contract.py` checks `CodexHostSetup` and the constructor keyword, the fields appended to the input records, `retryable`, `with_operation` and `relabel`, `ExceptionOrigin`, every new constant verbatim in its sorted `__all__`, the C021 rule by an AST scan, the two new modules, the 0.163 pin and the documented limitations (AC-5, AC-13, AC-34, AC-39 to AC-41). It is CI-visible, except the class that maps JSON-RPC errors through the SDK's classes.
- `test_codex_host_approvals.py` covers the section 4 snippet, the default answers with and without a handler, what the handler sees and how its answer is encoded, every fallback, the USER reviewer per operation, and close with a pending handler (AC-1, AC-10 to AC-15, AC-38).
- `test_codex_host_resilience.py` covers the thread id and tool cleanup of a failed spawn and launch, the overload retries, the `thread/read` classification and lineage, steer while stopping, and the wrapper operation (AC-2 to AC-4, AC-6, AC-24, AC-26).
- `test_codex_host_liveness.py` covers a failing turn or goal event, a lost watcher, a process death that is not a loss, a goal run that ends normally, and a failing review completion (AC-7 to AC-9).
- `test_codex_host_observability.py` covers every log event with its fields and the privacy canaries in the logs (AC-18).
- `test_codex_host_function_rows.py` covers `forget_codex_turns`, readiness usage, the model-list refresh, continue's goal check, `limit` and `force_reload`, the skill folder, and the new bad arguments (AC-16, AC-19 to AC-21, AC-23, AC-27, AC-28, AC-41).
- `test_codex_host_fork_review.py` covers the fork points, the deferred goal, the experimental gate, the fork's failed name-set, the capped review and the one-page read-backs (AC-22, AC-25, AC-33).
- `test_codex_host_turn_settings.py` covers the goal-run field refusals, the new efforts on the wire, service tiers and the sandbox policy (AC-29 to AC-32).
- `test_codex_host_tool_hardening.py` covers the tool local-failure result, the 42-tool surface with no forbidden parameter, the new efforts in the schemas, a goal spawn with an effort, and a USER reviewer in `spawn_defaults` (AC-17, AC-30, AC-36). Its stub-host classes are CI-visible.
- `test_codex_host_live_smoke.py` is the one live module: opt-in with `VIDBYTE_CODEX_LIVE_TESTS=1`, it opens a real host and calls only non-spending reads, while a spy on the SDK's writer proves nothing else was sent (AC-35). Its gate class is CI-visible; the live class is skipped unless enabled.
- `test_codex_host_sdk_contract.py` gains `CodexHardeningSdkContractTests`, which pins openai-codex 0.163, `retry_on_overload` and the wire fields the slice sends.
- Every hardening module except the records, the contract (minus one class), the tool class and the live gate needs the `codex` extra, so CI skips it.
- `codex_host_support.py` holds the spec literals, canaries, `HostTestCase` and `StubCodexHost`. `codex_host_fakes.py` holds the in-memory app-server, and `codex_host_helper_fakes.py` holds its thread-helper, goal and skill handlers, a mixin `FakeAppServer` inherits.

The first-class-features slice (`docs/spec/codex-host-first-class/spec.md`, test plan `docs/spec/codex-host-first-class/test-plan.md`) adds these, all red until the slice lands:

- `test_codex_host_feature_records.py` checks the new records, the collaboration-mode rules, `GitWorktreeSpec` with a seeded property test of its ref rule, and the seventeen input records (section 9.1). It is CI-visible.
- `test_codex_host_feature_constants.py` pins the section 9.2 texts, the section 9.3 values, the ten new enums and the twenty-five new operations. It is CI-visible.
- `test_codex_host_feature_structure.py` checks the four SDK-free mixins over `CodexHostCore`, the section 8.5 signatures, the import probe, the `TYPE_CHECKING`-only imports, the INV-47 line ceilings and the two frozen files. It is CI-visible, except the collaborator-interface class.
- `test_codex_host_feature_docs.py` checks the limits each new docstring must state (FR-33, T-1). It is CI-visible.
- `test_codex_host_feature_tools.py` checks the sixteen new tools: no tool for the INV-42 functions, no posture parameter, the paid-work sentence, the arguments passed, the side-chat posture, cap slots, ownership and error results (AC-35 to AC-37). Its stub-host classes are CI-visible.
- `test_codex_host_feature_contract.py` covers the call guards, the experimental gate, the error packets with one failed call record each, malformed answers and a dead app-server for all twenty-five methods (AC-8, AC-34, AC-41).
- `test_codex_host_settings_modes.py` covers thread settings, the preset list, modes on the wire and their pricing, the plan run and its fallback answer, and turn settings (AC-2 to AC-11, AC-20).
- `test_codex_host_stream_wait.py` covers the stream's order, bounds, gaps, release rules and handle checks, a slow approval handler, and `wait_codex_turns` (AC-12 to AC-18, AC-43, AC-44).
- `test_codex_host_mcp_memory.py` covers the MCP listing and the three memory functions (AC-19, AC-21).
- `test_codex_host_side_chat.py` covers the side-chat flow, its refusals and its cleanup (AC-22, AC-23, AC-42).
- `test_codex_host_worktree.py` covers `create_codex_worktree` and `GitWorktrees` with the real git on temporary repositories (AC-24). Its `GitWorktrees` class is CI-visible wherever git is installed.
- `test_codex_host_goal_control.py` covers pause, resume, edit and clear of a goal (AC-25 to AC-29).
- `test_codex_host_thread_admin.py` covers archive, unarchive, rename, revert, inject, the terminals, content search, the child listing and the load guard (AC-30 to AC-33).
- `test_codex_host_first_class_snippet.py` runs the section 4 snippet (AC-1).
- `codex_host_feature_support.py` holds the slice's literals and `FeatureStubMethods`, and `codex_host_feature_fakes.py` holds the fake's slice-2 handlers, a mixin `FakeAppServer` inherits. `FeatureHostCase` in `codex_host_support.py` keeps a request window per test.
- The section 13 pins in nine older modules now expect the slice: 42 tools, the new exports, enums and operations, the fork row's `collaboration_mode` tail, and the seventh `GOAL_REJECTED_FIELDS` entry.

Run it with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host`, from the worktree root, with the venv that has the `codex` extra.

## Omitted Testing Strategies

- **Property-based and fuzz:** `hypothesis` is not a dependency. The algebraic rules (the review-target kinds, snapshot states, the field rules and the error tables) are exhaustive tables over their small domains.
- **Paid live Codex runs:** these spend the user's plan and CI has no credentials (NG-13). AC-1 is proven at the seam, and a live turn is manual QA. The hardening slice adds one opt-in live module, `test_codex_host_live_smoke.py` (X9, D-28), which calls only non-spending reads and is skipped unless `VIDBYTE_CODEX_LIVE_TESTS=1`.
- **Windows npm launcher process trees (EC-3, EC-69) and long silences (EC-5, EC-35, EC-70):** they need a real process or a 300 s wait. The bound itself is proven by patching it small.
- **Load and stress:** the host keeps per-turn state for its lifetime (EC-65), and no limit depends on volume.
- **The controls not built (Q-7, Q-8, Q-9):** there is nothing to test.
- **A transcript of an ephemeral thread (thread-helpers EC-49):** the fake could only repeat assumption A-21, so a test would prove the fake, not Codex.
- **The accepted thread-helpers limits (EC-19, EC-20, EC-21, EC-33, EC-41, EC-43, EC-44):** they describe what Codex does after an accepted request, so the fake would only replay the assumption.
- **A live goal run, skill run or `openai-docs` run:** each spends the user's plan (NG-15). AC-1 is proven at the seam.
- **The sentence counts of the new tool descriptions (NFR-7):** a count of sentences says nothing about meaning, so review checks them.
- **A handler that calls its own host, or a slow handler stalling other turns (hardening EC-1, EC-2, EC-50):** they need a 300 s stall or a second turn racing the SDK's single reader thread, and the spec accepts both; AC-39 checks that the `CodexHost` docstring names them.
- **The SDK's retry backoff running past the request bound (hardening EC-14):** it needs the SDK's real backoff sleeps; the bound itself is the existing one, already proven by patching it small.
- **What Codex does after an accepted request (hardening EC-10, EC-27, EC-28, EC-36, EC-47):** a schema-invalid `{}` answer, an unknown `before_turn_id`, a goal continuing on a fork, an unversioned CLI and a retried delete are Codex's or the SDK's behaviour, so the fake would only replay the spec's assumption.
- **`forget_codex_turns` racing a handed-over start (hardening EC-19):** the window is a few instructions wide; the busy row proves the same `require_idle` refusal deterministically.
- **The focused C021 agent lint (hardening AC-40):** it is a command the implementer and reviewer run (`AGENT-LINT: PASS`); the pack scans `vidbyte/harnesses/native` with `ast` for the same rule.
- **Stdlib logging when a handler raises (hardening EC-44):** that is the standard library's behaviour, not the host's.
- **The first-class controls not built (the queue, P2 items, one-shot mirrors, a stream tool, turn-less notification watching, Q-10, Q-11):** there is nothing to test, and no test asks for them.
- **First-class T-4 and T-7:** T-4 is N/A (one account's private app-server) and T-7 is out of scope (Codex owns sign-in), so neither has a control to test.
- **How long a slow approval handler pauses a stream (first-class EC-55):** the test checks that every event arrives after the handler answers; a timed pause would need a wall clock.
