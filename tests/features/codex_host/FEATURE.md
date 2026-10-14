# Feature: CodexHost, small atomic Codex functions with one agent tool per function

## High-Level Feature Description

A developer opens `CodexHost()` with `async with`, and the host runs one `codex app-server` process through openai-codex 0.162. Fifteen small async methods sit on the host: check readiness, read rate limits, list models, spawn, continue and fork threads, list and read threads, wait on, get, steer and interrupt a turn, track a thread's usage, launch several subagents, and start a review. Spawn returns a handle as soon as Codex accepts the turn, and the result comes later. Every failure is a `CodexAgentError` with a semantic code and a next step. `CodexHostTools(host, max_live_turns=N)` exposes the same fifteen functions as agent tools, and six module functions open a host for one call.

If this feature regresses, three things can go wrong. An agent can spend the user's Codex plan without control: a turn nobody owns, a cap that never fires, or a `user` reviewer that silently approves every escalation. A host call can hang, or a stack trace can reach the model. Or private data (the account email, environment values, the app-server's stderr) can leak into an error or a tool result.

## Contract

- Importing `vidbyte`, `vidbyte.harnesses.native.codex`, the builtins and the toolsets never loads openai-codex. Entering a host without the SDK raises `codex.not_installed` with a `pip install "vidbyte-sdk[codex]"` next step (INV-1, AC-2).
- Open resolves `codex` with `shutil.which` and refuses versions below 0.151.0, or ones it cannot parse. A failed open closes what it started (INV-3 to INV-5).
- Spawn, continue, review and launch run their preflight checks before the first spending request. They return a handle at acceptance and register every turn before returning it (INV-12 to INV-14).
- Each turn ends exactly once: COMPLETED, INTERRUPTED or FAILED. A wait never raises because time passed. A timeout or an output cap sends exactly one interrupt (INV-15 to INV-19).
- Only `CodexAgentError`, `ConfigurationError` and `CancelledError` escape. Tools never raise, and they report `"<code>: <message> Next step: <next_step>"` (INV-8, INV-10).
- A `user` reviewer fails closed: at construction, and after `thread/start` or `thread/resume` reports one (D-16, D-32).
- Close cancels running tool calls, finalizes and interrupts running turns, closes goal streams in openai-codex's order, and then closes the process on a daemon thread (INV-7).

## Actors / Callers

- Python callers using `CodexHost` and the six module functions.
- Agents calling the fifteen tools through `ToolExecutor`.
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
- The seven modules from `test_codex_host_lifecycle.py` to `test_codex_host_sdk_contract.py` need the `codex` extra, so CI skips them.
- `codex_host_support.py` holds the spec literals, canaries, `HostTestCase` and `StubCodexHost`. `codex_host_fakes.py` holds the in-memory app-server.

Run it with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host`, from the worktree root, with the venv that has the `codex` extra.

## Omitted Testing Strategies

- **Property-based and fuzz:** `hypothesis` is not a dependency. The algebraic rules (the review-target kinds, snapshot states, the field rules and the error tables) are exhaustive tables over their small domains.
- **Live Codex runs:** these spend the user's plan and CI has no credentials (NG-13). AC-1 is proven at the seam, and a live run is manual QA.
- **Windows npm launcher process trees (EC-3, EC-69) and long silences (EC-5, EC-35, EC-70):** they need a real process or a 300 s wait. The bound itself is proven by patching it small.
- **Load and stress:** the host keeps per-turn state for its lifetime (EC-65), and no limit depends on volume.
- **The controls not built (Q-7, Q-8, Q-9):** there is nothing to test.
