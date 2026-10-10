# Feature: Coding agent

## High-Level Feature Description

An SDK caller builds `CodingAgent` with one constructor call and gets a `BaseAgent` whose model can run shell commands, read, write and edit files, search files, and fetch web pages, all under one root folder. The model can act without the caller writing a policy, because the default policy allows every permission. Every bash call returns in bounded time with bounded output. A supplied fetch key picks one priced provider, and the model reads the pages it fetched.

## Contract

`CodingAgent(*, name, system_prompt, root_dir, firecrawl_api_key=None, browserbase_api_key=None, parallel_api_key=None, tavily_api_key=None, tools=(), permission_policy=None, **BaseAgent options)` registers, in this order: `bash`, `read_lines`, `write_text`, `replace_text`, `glob`, `grep`, and one web-fetch tool, followed by the caller's tools. `root_dir` is resolved once, at construction, to an absolute path. With no policy, the agent uses `PermissionPolicy.allow_all()`, and a caller's policy object is used as given. At most one fetch key may be supplied, and it must be a non-blank string. The key picks Firecrawl, Browserbase, Parallel or Tavily; with no key the tool is the unpriced direct fetch. Behaviour other than construction is `BaseAgent`'s own.

`BashTool(root_dir)` runs `bash -c <command>` in `root_dir` with stdin closed and stderr merged into stdout. A success result holds the decoded output, at most `BASH_MAX_OUTPUT_BYTES` bytes followed by an omitted-byte count, and ends with `exit code: <n>`. It returns `bash_not_found`, `spawn_failed` or `timeout` errors. One time limit, `BASH_TIMEOUT_SECONDS`, covers both reading and waiting. On a timeout or a cancellation, the command's process group is killed (POSIX) or Git's launcher is killed (Windows), then the tool waits at most `BASH_KILL_GRACE_SECONDS` and closes the pipe.

## Actors / Callers

SDK callers that construct `vidbyte.CodingAgent`, and the model inside `AgentRuntime`'s tool loop, which calls the seven tools. `BaseAgent.export_state` / `restore` and `agent.card()` consumers read the built agent.

## Inputs and Preconditions

`root_dir` is an existing directory, given as a str or Path, relative or absolute. Optional fetch keys and caller tools may be supplied. For bash, POSIX hosts need `bash` on `PATH`, and Windows hosts need Git for Windows, with `<G>/bin/bash.exe` within three parent folders of the resolved `git`. The tests need no network and no real keys: provider HTTP is faked at `HttpTransport._send_once`.

## Observable Outcomes

- `agent.tools.names()`, `agent.root_dir` and `agent.permission_policy`.
- `reply.metadata["tool_call_states"]`.
- The tool messages the model receives.
- Files under `root_dir`.
- `agent.get_usage().operations`.
- `export_state()` and `card()` text.
- The `ToolResult` status, output and metadata of a bash call, plus whether its processes are still running after the call (from `/proc` on Linux).
- The elapsed time of a call, measured against an upper bound.
- Transports left open, unraisable loop errors, and `ResourceWarning`s after `asyncio.run` returns.

## State Transitions

Construction either raises (bad root, bad or duplicate key, duplicate tool name, or a `BaseAgent` identity error) or yields a ready agent. Building an agent makes no network call and starts no process. A bash call goes through these stages:

1. Validated.
2. Spawned.
3. Read to the end of output, with the output capped and the rest counted.
4. Waited on, within the one limit.
5. Returns `success`. If the limit is reached instead, the call kills the command, waits at most the grace period, closes the pipe, and returns `timeout`. If it is cancelled, it kills, waits, closes, and re-raises `CancelledError`.

## Invariants

- The order of the seven tools is fixed, and caller tools come after them.
- The root folder is fixed at construction and does not follow later `chdir` calls.
- A caller's policy always wins.
- A fetch key reaches only its own provider, never comes from the environment, and never appears in exported state, the card, or failed results.
- The keyed fetch view changes only the model-visible text. Its schema, metadata and billing are the bare priced tool's.
- Every bash call returns within `BASH_TIMEOUT_SECONDS` + `BASH_KILL_GRACE_SECONDS`.
- Captured output never exceeds the cap.
- Cancellation always propagates, and on POSIX the process group is killed even after the shell has exited.
- A normal completion kills nothing.
- After a timeout, the pipe is closed before the call returns.
- `CodingAgent` adds only a constructor. Its exported state equals that of a `BaseAgent` built with the same tools and policy.

## External Dependencies

- A real `bash`: Linux bash on CI, Git for Windows bash locally.
- `/proc` for liveness checks on Linux.
- `setsid` for the AC-25 and AC-28 POSIX cases.
- The four provider clients' request builders and response parsers. These are real, and only the single HTTP send is faked.

## Known Failure Modes

These are the failure inventory the tests were chosen from, given as input → wrong output.

- **Root errors.** A relative `root_dir` is resolved at call time instead of construction, so after a `chdir` the files land in the wrong folder (INV-4, EC-7). A missing or file `root_dir` is accepted, and the first tool call fails later (AC-11).
- **Policy errors.** No default policy means every WRITE or EXECUTE call is denied, so the agent is useless (AC-2). The caller's `PermissionPolicy()` is replaced or merged with allow-all, which is a security regression (AC-3).
- **Key errors.**
  - Two keys are accepted with hidden precedence, so the wrong vendor is billed (AC-4).
  - A blank key from an unset environment variable becomes a 401 on every fetch (AC-5).
  - The key value is echoed in an error (AC-4, AC-5).
  - The key leaks into `export_state()`, `card()` or a failed result (AC-23).
  - The client falls back to the provider's environment variable (INV-6).
  - Construction makes a network call (INV-18).
- **Fetch view errors.** The model sees only the "Fetched N page(s)" summary and never the page text (AC-7). The view changes the schema or metadata, so the bill differs from the bare tool's (AC-7, INV-16, INV-20).
- **Tool list errors.** A caller tool silently shadows a built-in tool (AC-8). Caller tools are reordered or dropped (AC-9).
- **Subclass errors.** `CodingAgent` overrides `BaseAgent` behaviour, or adds state that changes `export_state` (INV-1, INV-2). `restore` reports a tool mismatch or loses allow-all (AC-21).
- **Bash spawn errors.**
  - `shell=True` or string interpolation mangles quotes or `$` (INV-9).
  - stdin is inherited, so `read` hangs until the time limit (EC-11).
  - The stdout and stderr order is lost, or stderr is dropped (AC-12).
  - A non-zero exit becomes an error result (AC-12).
  - Invalid UTF-8 raises an error (EC-16).
  - A NUL byte or an oversized argument raises an error, or leaks its message (EC-15).
  - A path with a space or a non-ASCII character breaks `cwd` (AC-16).
  - A missing or blank command spawns a process (AC-18).
- **Bash output errors.** The whole output is buffered, so memory grows with the output (AC-13, EC-10). The cap or the omitted count is wrong (AC-13). An endless printer's timeout result is not truncated, or claims a count (AC-29).
- **Bash time errors.**
  - The limit covers only the wait, so EOF reached early unbounds the call (AC-24).
  - A background child holds the pipe and the call never returns, or the child survives (AC-14, EC-9).
  - A `setsid` descendant stretches the call past the limit plus the grace period (AC-25).
  - On Windows with Python 3.12+, `Process.wait()` blocks until the orphan exits (AC-27).
  - A normal completion kills the detached server (AC-26).
- **Bash cleanup errors.**
  - Cancellation is swallowed, or the group is not killed because the shell already exited (AC-15, EC-29).
  - An unbounded wait follows the kill (INV-12).
  - The transport is left open, so `Event loop is closed` or `closed pipe` noise appears after `asyncio.run` (AC-28).
- **Bash lookup errors.** On Windows the `PATH` `bash` (WSL's launcher) is chosen instead of Git's `bin/bash.exe`, or the lookup walks past three parent folders (AC-22). A missing bash breaks construction or the other tools (AC-17).

## Historical Regressions

None yet. This is a new feature, specified in `docs/spec/coding-agent/spec.md` r3. The S1 review found the Windows launcher orphan (EC-14), the pipe-holding descendants (EC-28 to EC-30) and the transport leak (INV-26) before any code existed.

## Test Suite Map

- `test_coding_agent_acceptance.py` checks the caller-visible promise end to end through `BaseAgent`'s loop: the spec snippet, the default policy, a read-only policy, a keyed fetch shown and billed, and a missing bash.
- `test_coding_agent_contract.py` checks the following:
  - The public names.
  - The constructor-only subclass and its signature.
  - Export parity with `BaseAgent`, and `restore`.
  - Caller tools: their order and duplicates.
  - Identity errors.
  - Root validation, and the root fixed across `chdir`.
- `test_coding_agent_web_fetch.py` checks the following for each provider: provider selection, the key reaching its provider, the view against the bare tool, failed-fetch pass-through, keys absent from exports, two keys, and blank keys.
- `test_bash_tool_contract.py` covers the following:
  - The spec and constants.
  - Validation.
  - Streams and the exit code.
  - `cwd` with spaces and Unicode.
  - The verbatim argv.
  - stdin at EOF.
  - `spawn_failed`.
  - Invalid UTF-8.
  - The output cap with bounded memory.
  - `bash_not_found`.
  - The Windows lookup, simulated on a POSIX host.
- `test_bash_tool_process_bounds.py` covers the following:
  - The time limit.
  - The group kill.
  - Early EOF.
  - A `setsid` descendant.
  - Detached background processes.
  - An endless printer.
  - Closing the transport after `asyncio.run`.
  - Cancellation, both directly and through the runtime's tool timeout.

Run everything with `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent`.

## Omitted Testing Strategies

- **Property-based and fuzz tests.** No contract here is algebraic. Command text goes to bash verbatim, and one adversarial argv case covers quoting.
- **Live provider calls and real keys.** These are forbidden. The real clients are exercised against a faked HTTP send.
- **Fork isolation (INV-23).** `vidbyte/agents/fork.py` is unchanged and already covered.
- **Non-linear runtimes (INV-24).** These pass through `BaseAgent` unchanged.
- **Parallel tool calls (EC-19).** Each call owns its own process, so there is no shared state to race.
- **The `ProcessLookupError` race at the kill (EC-25).** It cannot be made deterministic.
- **Signal exit codes (EC-24).** These are covered by the generic exit-code path.
- **Windows command-stop checks.** On Windows the command may legitimately keep running (EC-14), so Windows checks only time bounds and pipe cleanup.
- **AC-27 on Python 3.13.** This must be run manually with `py -3.13` on a Windows host. CI runs 3.11 and 3.12 on Linux.
