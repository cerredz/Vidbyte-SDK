# Feature: Claude Code harness agent (`vidbyte.agents.claude_code`)

## High-Level Feature Description

`ClaudeCodeHarnessAgent` is one Claude Code conversation on the user's machine. Its first `arun(ClaudeCodeRunInput)` starts a session in Claude Code's print mode with a fresh `--session-id`, every later `arun` on the same object resumes it with `--resume`, and each run returns a `ClaudeCodeRunResult` with the structured output, the final text, the session id, this run's token usage and cost, and the model. The user's own `claude` runs every model turn under the user's own login or key, which is how vidbyte-cli's `agents suggest` bills Anthropic usage to the user (bring your own key) and charges Vidbyte's own price separately.

## Contract

The cross-repo suggest-BYOK contract (section 2) pins the names `ClaudeCodeHarnessAgent`, `ClaudeCodeHarnessAgentSettings`, `ClaudeCodeRunInput`, `ClaudeCodeRunResult`, `ClaudeCodeUsage`, `ClaudeCodeImage`, `ClaudeCodeAgentError` and `ClaudeCodeFailureKind`'s seven members, and the settings, input and result fields in their order; optional fields may follow. Every run: refuses unsupported attachments and a missing `claude` before anything starts; runs `claude --print` with stream-json in and out, `--safe-mode --setting-sources= --strict-mcp-config --disable-slash-commands`, the instructions through a private `--system-prompt-file`, `--tools=` with no allowed tools; writes one stdin message (images, then the prompt); strips a parent Claude Code session's variables from the child environment; reads the `init` and `result` events; and raises one `ClaudeCodeAgentError` whose message says what happened, quotes Claude Code (scrubbed), and gives the likely cause and next step.

## Actors / Callers

vidbyte-cli's suggestion agent (generator, critic and extra-compute turns) through the root `vidbyte` package, and any SDK caller. Underneath: `CliArgv` and `CliRunner` (`vidbyte/lib/process/`).

## Inputs and Preconditions

Offline tests: the stand-in `fake_claude.py` is the only `claude` (an `.exe` from pip's launcher on Windows, a script on POSIX), on a `PATH` holding only the sandbox's bin folder; temp folders are redirected into the sandbox; provider credentials are cleared and a parent Claude Code session's variables are set. The live test needs a signed-in Claude Code and `VIDBYTE_LIVE_CLAUDE_CODE=1`.

## Observable Outcomes

What the stand-in received (argv, parsed options, cwd and its files, the stdin message, the instructions file's text and folder, the watched environment variables, its pid), the result records, the errors (kind, attributes, message parts and order), the folders left on disk, and which processes are still alive.

## State Transitions

`agent.session_id` is `None` until the first run succeeds, then fixed; a failed run never changes it. The stand-in's session store, keyed by working folder, makes a resume from another folder fail as Claude Code's does. The agent's temporary workspace exists from its first run until `close()`; each run's instructions folder exists only during that run.

## Invariants

- The prompt and the instructions never appear on argv; every argv element is a known switch or a joined `--flag=value`.
- The isolation flags are always sent; `--bare` never is.
- `--tools=` (empty) when no tools are allowed; named tools are sent as both `--tools` and `--allowed-tools`.
- `cost_usd` is this run's cost; `session_cost_usd` is the cumulative total.
- No credential value appears in an error message or its details.
- A timed-out or cancelled run leaves no process and no instructions file behind.

## External Dependencies

None offline. The live test uses the real Claude Code and this machine's login (about $0.001 with the haiku alias).

## Known Failure Modes

A login failure read as success because `subtype` says "success"; a schema violation missed because Claude Code exits 0 without `structured_output`; a cumulative session cost reported per run; a resume from a new temporary folder ("No conversation found"); a parent session's messaging socket or effort leaking into the thread; a 52 KB system prompt overflowing the Windows command line; an npm `claude.cmd` re-parsing argv through `cmd.exe`; a Claude Code that ignores `--tools=` or loads an MCP server; a key echoed back in Claude Code's error text.

## Historical Regressions

None yet (created 2026-10-30).

## Test Suite Map

`test_claude_code_agent.py` (success paths), `test_claude_code_failures.py` (every failure kind, timeout, cancellation, scrubbing), `test_claude_code_records.py` (validation), `test_claude_code_surface.py` (public surface and contract file), `test_claude_code_live.py` (opt-in live).

## Omitted Testing Strategies

No test drives a real Claude Code in the gate or remote CI: it would need a signed-in account and spend money, so the live test is opt-in and the stand-in replays the live shapes recorded in `docs/design/claude-code-harness-agent.md` section 4. Model behaviour (answer quality, schema adherence) is out of scope.
