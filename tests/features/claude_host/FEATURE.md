# Feature: ClaudeHost — Claude Code as small atomic functions and agent tools

## High-Level Feature Description

A developer enters `async with ClaudeHost()` and calls 15 coroutine functions that check the installed Claude Code CLI, list its models and rate-limit windows, start, continue, fork, steer, interrupt and wait on Claude Code sessions, read session history offline, and track what a session cost. Each function wraps claude-agent-sdk 0.2.165, which comes from the optional `claude` extra, and fails with one `ClaudeOperationError` that carries a semantic failure code and a next step. `ClaudeTools(host, request)` exposes the same 15 functions as agent tools, READ or WRITE, so an orchestrator agent can run Claude Code sessions under `await agent.arun()`. Every turn runs in its own `claude` process, which the host starts and always closes. The contract comes from `docs/spec/claude-host/spec.md` (r3).

## Contract

- Importing `vidbyte`, `vidbyte.tools.builtins`, `vidbyte.tools.toolsets`, `vidbyte.tools.toolsets.claude`, `vidbyte.harnesses.native` or `vidbyte.harnesses.native.claude` never imports `claude_agent_sdk`. `ClaudeSdkLoader.load` is the only import of it. With the extra missing, every ★ function raises `claude.sdk_unavailable`, except `check_claude_ready`, which reports it in `failure`.
- Every ★ function returns its documented record or raises `ClaudeOperationError` with a `FailureCode` value, a reason and a next step. No vendor or builtin exception escapes. The 15 tools never raise: they return `"<code>: <reason> Next step: <next_step>"` with the metadata `{"error": code, "error_type": "ClaudeOperationError"}`.
- Spawn, continue and launch return QUEUED or RUNNING handles before any turn they start can end. Every turn ends exactly once, as COMPLETED, FAILED or INTERRUPTED, and only after its client's one `disconnect()` has finished. Nothing ever cancels that disconnect.
- A failed turn carries exactly one code, chosen by the fixed precedence of spec §9.2 "Turn classification". SDK exceptions map by §9.2 "Exception mapping". A `ProcessError` or `CLIConnectionError` raised by `connect()` gets `CLAUDE_START_FAILURE_NEXT_STEP`.
- Steer means interrupt, then resend, with one pending message at a time. Every interrupt that returns is bounded by `CLAUDE_INTERRUPT_GRACE_SECONDS`. The request's `timeout_seconds` is a watchdog that ends the turn with `claude.budget_exhausted`, never INTERRUPTED.
- Within one host, at most one live handle exists per session id, and at most `max_live_sessions` live handles exist in total. A launch registers all N handles or none.
- `ClaudeSpawnRequest` (58 fields) validates itself and maps field by field onto `ClaudeAgentOptions`, an `extra_args` flag or one env variable, per §9.2 "Field mapping". Unset fields are left at the SDK default.
- The host serves only the event loop that entered it. Before entry, after `aclose`, or from another loop, every ★ call and `get_handle` raises `action.precondition_failed`.

## Actors / Callers

- SDK users calling `ClaudeHost` directly, as in the §4 snippet.
- Agents running `ClaudeTools` under `arun`, with a `PermissionPolicy` that decides whether WRITE tools run.
- `McpStudioServer` listing the tools.
- Claude Code itself, which calls back into custom `BaseTool`s through the in-process `vidbyte` MCP server.

## Inputs and Preconditions

- `ClaudeHost(cli_path=..., max_live_sessions=...)`.
- `ClaudeSpawnRequest` and its sub-records.
- Model-written tool arguments (JSON).
- The CLI's initialize response (version, account, models, `hooks_applied`) and its message stream (assistant, result, rate-limit and task messages).
- The SDK's offline history functions.

Tests patch `ClaudeSdkLoader.load` to return a real `ClaudeSdkTypes` built from fakes, give the host an explicit `cli_path` (or patch `shutil.which` where the probe module looks it up), and never start `claude`.

## Observable Outcomes

- The records the functions return: `ClaudeSessionHandle`, `ClaudeTurnResult`, `ClaudeReadiness`, `ClaudeModelInfo`, `ClaudeRateLimitWindow`, `ClaudeSessionSummary`, `ClaudeSessionMessage` and `ClaudeUsageSnapshot`.
- The attributes of a raised `ClaudeOperationError`.
- Tool results.
- Everything the fake SDK recorded:
  - each client's constructor options;
  - its `connect`, `get_server_info`, `query`, `interrupt` and `disconnect` calls, in order;
  - whether a disconnect finished or was cancelled;
  - the peak number of connected clients;
  - the history calls and the thread each one ran on.

## State Transitions

A turn moves from QUEUED to RUNNING once connect and the process preconditions pass and the prompt is sent. From RUNNING it ends as COMPLETED, FAILED or INTERRUPTED (spec §9.1). A steer keeps the turn RUNNING across the interrupted result and sends one new prompt. A grace expiry or a time-budget stop starts the close. A turn becomes terminal only after the close completes, and a terminal status never changes. Finished handles stay readable until `aclose`. A host moves from new to entered to closed, and is never reopened.

## Invariants

- No client stays connected after its turn is terminal. Every client the host constructs is disconnected exactly once.
- A precondition failure sends no prompt: no `query` is recorded.
- History reads and fork run off the event loop thread and construct no client.
- `track_claude_session_usage` reports the latest result's figures, never a sum.
- No reason, next step, tool output or `repr` contains raw exception text, an `env` value or a `headers` value.
- The marker module `vidbyte/harnesses/native/__init__.py` hashes to `0374a2c8…942f497a` once every CRLF is replaced by LF.

## External Dependencies

- claude-agent-sdk 0.2.165, faked through the one seam. The fakes copy the real class names, fields and defaults, and the options fake has exactly the real `ClaudeAgentOptions` fields.
- `shutil.which` and the home folder, for the CLI lookup.
- `asyncio.to_thread`.
- These run unmocked: the agent runtime, `ToolExecutor`, `Tools`, `PermissionPolicy`, `ToolsFormatter` and `McpStudioServer`.

## Known Failure Modes

Each line is input + state → wrong output.

**Import and lookup**
- `claude_agent_sdk` not installed, then `import vidbyte` → `ImportError` for every user (INV-1).
- A tools module imports `ClaudeHost` at run time → the vendor import chain loads during `import vidbyte.agents`.
- Windows PATH finds npm's `claude.cmd` first → the shim is handed to the SDK → `CLIConnectionError` at connect, which no respawn fixes (EC-57).
- No `cli_path` and nothing found → the SDK silently runs its bundled CLI, with no login (EC-2).
- `version_ok("2.1.1000")` compared as text → a newer CLI is refused. `"2.1.29"` compared as text → an older CLI is accepted.

**Turn lifecycle**
- A turn completes, but done fires before `disconnect()` finishes → a wedged `claude` keeps running while the cap admits a new spawn (EC-60).
- The pump cancels the close task when the stream ends → the terminate and kill escalation never runs.
- An interrupt is acknowledged but no result follows → the turn stays RUNNING, with a busy session id and a taken slot, until `aclose` (EC-53).
- A grace timer is armed after the prompt's result was already read → the steered prompt is disconnected mid-turn (AC-37 d).
- A caller times out a steer → the session never arms the grace → the turn hangs (EC-59, AC-40).
- A second steer while one is pending → two messages coalesce into one CLI turn → the pump waits forever.
- An injected task-notification result arrives first → the handle finishes with another turn's text (EC-56).

**Failure codes**
- `ResultError` is dispatched before its `ProcessError` base is checked → `error_max_turns` is reported as `process_exited`.
- The watchdog sets the caller-interrupt flag → a budget stop is reported as INTERRUPTED.
- A rejected window mid-turn plus an error result → `api_error` instead of `usage_limited`.
- An interrupted result has `is_error=True`, and the caller interrupted → `api_error` instead of INTERRUPTED.

**Admission**
- `max_live_sessions=1` and a launch whose slot is released before close → two clients connected at once.
- A launch refused for the cap still registers some handles → later spawns are refused.
- A continue on a live session id → two processes append to one transcript (EC-11).

**Field mapping**
- `builtin_tools=()` passed as a tuple → the SDK treats it as the preset and enables every built-in tool.
- `skills` passed as a tuple → the SDK raises `TypeError` at connect.
- `effort` left at `""` → `--effort ""` on the command line.
- `user` or `settings` left at `""` → the process start fails, or `--settings ""` is sent.
- The default system prompt sent as `None` → the CLI runs with an empty system prompt (INV-17).

**Tools and secrets**
- A tool lets `ClaudeOperationError` escape → the agent loop sees a crash instead of a recoverable error.
- `"limit": "2"` is accepted → a string reaches the semaphore.
- `str(exc)` of `ProcessError` is copied into a reason → its stderr, which can hold secrets, reaches the model.
- A record's `repr` → `env` and MCP `headers` are printed in logs.

## Historical Regressions

None yet. Add one line per fixed bug with the test that protects it.

## Test Suite Map

- `test_claude_host_acceptance.py`:
  - the §4 snippet as written (AC-1), in both its ready and not-ready outputs;
  - the snippet-2 orchestrator agent driving the tools under `arun`;
  - sync `agent.run()` refused through a tool error (EC-25).
- `test_claude_host_contract.py`:
  - the import boundary in a clean interpreter (INV-1);
  - the marker bytes (AC-19);
  - the failure-code block and next steps (AC-23);
  - the constants;
  - the enum wire values and exports (AC-27);
  - the record shapes;
  - the public `ClaudeHost` surface (AC-35);
  - the pyproject extra (AC-33);
  - the REPO_MAP and README insertions (AC-32).
- `test_claude_host_request.py`:
  - the field mapping, row by row (AC-17), and the default preset (INV-17);
  - image prompts;
  - record validation (AC-18);
  - the custom-tool MCP server and its handler (AC-20).
- `test_claude_host_turns.py`:
  - the spawn snapshot and the client's `cli_path` (AC-3);
  - wait timeouts (AC-4, EC-24);
  - the result fields;
  - the budget subtypes (AC-5);
  - every detection condition and exception mapping (AC-6, AC-39);
  - the classification precedence (INV-19);
  - usage (AC-15);
  - `hooks_applied` (AC-28);
  - injected results (AC-36);
  - disconnect errors.
- `test_claude_host_stops.py`:
  - steer (AC-9, EC-20, EC-21);
  - interrupt (AC-10, EC-22, D-26);
  - `aclose` and the loop guard (AC-21);
  - the never-cancelled close (AC-25);
  - the budget watchdog (AC-31);
  - the interrupt grace (AC-37, AC-40);
  - pending-steer discards (INV-18).
- `test_claude_host_admission.py`:
  - continue (AC-7);
  - launch (AC-11, INV-6, EC-33);
  - rate limits (AC-16, EC-52);
  - the live cap (AC-30);
  - busy session ids (INV-4);
  - empty and mistyped arguments (EC-49, EC-50);
  - CLI path choice (INV-10);
  - session-id natural keys (§9.1, EC-34).
- `test_claude_host_history.py`:
  - fork (AC-8);
  - list, info and messages, with the text rendering (AC-14);
  - no process for history (INV-16).
- `test_claude_host_readiness.py`:
  - the missing extra (AC-2);
  - version and auth mode (AC-22);
  - models (AC-34);
  - CLI lookup (AC-38);
  - start failures in readiness (AC-39);
  - the sign-in and version tables (A-7, D-6).
- `test_claude_host_tools.py`:
  - the per-tool contract (AC-12);
  - the toolset order and permissions (AC-13);
  - wrong JSON types and null arguments (AC-26);
  - the MCP listing (AC-29);
  - success rendering.
- `test_claude_host_security.py`:
  - secret and error-text markers through every surface (AC-24, INV-12);
  - validation that never echoes values (T-3);
  - extra model arguments never reaching the options (T-2, D-13);
  - foreign handle ids (T-4, EC-48).
- `claude_host_fixtures.py`: the fake SDK, the message factories, the history fakes, `TicketTool` and the `ClaudeHostCase` base class.

Run `PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host` from the worktree root.

## Omitted Testing Strategies

- **Property-based and fuzz testing:** `hypothesis` is not a dependency. The ordered rules use exhaustive tables over their small domains instead: the classification precedence, version comparison, the sign-in rule and the CLI lookup.
- **Stress and performance:** no NFR sets a latency or throughput threshold to assert, and memory per `claude` process is unmeasured (Q-8).
- **Live end-to-end:** a real `claude` would spend the user's plan window (NG-10, NFR-6).
- **Real-SDK contract tests:** the optional extra must not be installed in this stage, so these tests could not be proven red. See `docs/spec/claude-host/test-plan.md`.
- **No UI, accessibility or migration tests:** the feature has no UI and no persisted state.
- **The optional Q-1 to Q-11 behaviours, which are not built:**
  - clipping;
  - a permission gate on MCP;
  - cwd-scoped history;
  - root exports;
  - a temporary-file MCP config.
- **Accepted limitations, which have no behaviour to assert:** EC-28, EC-43, EC-45, EC-46, EC-47, EC-51, EC-54, EC-55 and EC-58.
- **Lint-owned rules:** description sentence counts (S025), file sizes, call depth and numeric constants. `python lint/run.py` enforces them.

Existing module tests that also guard this boundary:
- `tests/test_session_failures.py` checks that every `FailureCode` has a category prefix (INV-23);
- `tests/test_codex_tools.py` covers the Codex host that this feature mirrors;
- `tests/test_mcp_studio_server.py` covers the MCP listing.
