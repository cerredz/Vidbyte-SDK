# Feature: Coding agent

## High-Level Feature Description

An SDK caller builds `CodingAgent` with one constructor call and gets a `BaseAgent` whose model can run shell commands, read, write and edit files, search files, and fetch web pages, all under one root folder. The model can act without the caller writing a policy, because the default policy allows every permission. Every bash call returns in bounded time with bounded output. A supplied fetch key picks one priced provider, and the model reads the pages it fetched. By default the root folder's `AGENTS.md` is read once, at construction, and shown to the model right after the system prompt, so the model follows the rules the repository already wrote down. The root folder's `MAP.md`, a short human-written map of where things live, is shown the same way right after it, so the model can skip exploring the layout. With a `verify_command`, the run may not finish until that command exits with code 0.

## Contract

`CodingAgent(*, name, system_prompt, root_dir, firecrawl_api_key=None, browserbase_api_key=None, parallel_api_key=None, tavily_api_key=None, verify_command=None, max_verify_attempts=3, tools=(), permission_policy=None, readonly_paths=(), max_rewrite_lines=300, load_agents=True, load_map=True, setup_commands=(), progress_notes=True, context_manager=None, **BaseAgent options)` registers, in this order: `bash`, `read_lines`, `write_text`, `replace_text`, `glob`, `grep`, and one web-fetch tool, followed by the caller's tools. `root_dir` is resolved once, at construction, to an absolute path. With no policy, the agent uses `PermissionPolicy.allow_all()`, and a caller's policy object is used as given. At most one fetch key may be supplied, and it must be a non-blank string. The key picks Firecrawl, Browserbase, Parallel or Tavily; with no key the tool is the unpriced direct fetch. `readonly_paths` is a list or tuple of non-blank `fnmatch` globs relative to `root_dir`; when it is non-empty, one `ReadonlyPathsMiddleware` is appended after the caller's middleware, and it denies `write_text` and `replace_text` on any file whose resolved, root-relative POSIX path matches (ignoring case on Windows), naming the file and the pattern. `max_rewrite_lines` (an int of at least 1, or `None` for no limit) makes `write_text` refuse, with an error result that points to `replace_text`, to replace an existing file with more lines than the limit; the file is left untouched and the `write_text` description names the limit. Behaviour other than construction is `BaseAgent`'s own.

With `load_agents=True` (a real `bool`), the agent lists `root_dir` once and reads `AGENTS.md`, or, when that exact name is absent, the first case variant in sorted order; parent folders are never searched. At most `CODING_AGENTS_MD_MAX_BYTES` (32,768) bytes are read and decoded as UTF-8 with replacement characters, without a byte-order mark; a longer file is cut at a whole character and ends with a line giving the shown and total bytes and the `read_lines` start line for the rest. The text renders as primitive `coding:agents_md`, titled `Repository instructions (<file name>)`, after the system prompt and before the user message. A missing or blank file adds nothing; a present file that is not a readable regular file raises `ConfigurationError` naming its path. `CodingContextWindow.build(sections, context_manager)` places the sections in `CodingContextSection` order ahead of the caller's manager content, in a new manager; with no sections it returns the caller's manager, or `None`.

With `load_map=True` (a real `bool`), `MAP.md` (else a case variant such as `map.md`) is read the same way, through the same `RootFileLoader` steps, capped at `CODING_MAP_MD_MAX_BYTES` (32,768), and renders as primitive `coding:repo_map`, titled `Repository map (<file name>)`, after the `AGENTS.md` section. Other names, such as `REPO_MAP.md`, are not read.

`setup_commands` is a list or tuple of non-blank strings; a bare string, a non-sequence, or a bad item raises `ConfigurationError` naming `setup_commands` before anything runs. The commands run once, at construction, in order, each as `bash -c <command>` in `root_dir` with stdin closed and stderr merged into stdout, through `BashTool.find_bash()` and `BASH_TIMEOUT_SECONDS`. The first non-zero exit, timeout, or failure to start stops the run, and later commands are listed as not run. Nothing raises for a command's outcome. The note renders as primitive `coding:setup_results`, titled `Setup command results`, after the `AGENTS.md` and `MAP.md` sections and before the progress notes: one `passed` line per passing command, and for the failed one at most `CODING_SETUP_OUTPUT_TAIL_LINES` (30) lines from at most its last `CODING_SETUP_OUTPUT_TAIL_BYTES` (8,192) bytes of output. Without bash, nothing runs and the note says so with `BashTool.not_found_message()`. An empty list runs nothing and adds nothing.

With `progress_notes=True` (the default, a real `bool`), construction creates `<root>/.vidbyte/coding-agent/progress.md` from `CODING_PROGRESS_NOTES_TEMPLATE` and `<root>/.vidbyte/coding-agent/.gitignore` holding `*`, each only when missing, and never overwrites either; `.vidbyte/` itself gets no `.gitignore`. The notes, at most `CODING_PROGRESS_NOTES_MAX_BYTES` (32,768) bytes, render as primitive `coding:progress_notes`, the last section, titled `Progress notes (.vidbyte/coding-agent/progress.md)`, after `CODING_PROGRESS_NOTES_INSTRUCTION`; a longer file is cut and followed by `CODING_PROGRESS_NOTES_TRUNCATION_NOTE`. Any `OSError` while creating or reading them gives no section and no error. `progress_notes=False` creates and reads nothing.

With `verify_command` set (a non-blank string; `max_verify_attempts` is an int of at least 1, never a bool), the agent appends one `VerifyCommandMiddleware` after the caller's middleware. At every finish attempt that the output contracts accept, a plain answer or an `isDone` call, it runs `bash -c <command>` once in `root_dir` through `BashTool`. Exit code 0 lets the run end as usual. Anything else sends the model `Not done yet: the verification command `<command>` failed (<reason>). Its output is below. Fix the problem, then finish again.` and the bash output, as a user message. The `max_verify_attempts`-th failure ends the run without raising: the output is the model's last answer and `stop_reason` is `contract_unsatisfied`. `metadata["verify_command"]` is `{"passed", "attempts", "last_exit_code"}`. With no bash, construction raises `ConfigurationError` naming `verify_command`.

`BashTool(root_dir)` runs `bash -c <command>` in `root_dir` with stdin closed and stderr merged into stdout. A success result holds the decoded output, at most `BASH_MAX_OUTPUT_BYTES` bytes followed by an omitted-byte count, and ends with `exit code: <n>`. It returns `bash_not_found`, `spawn_failed` or `timeout` errors. One time limit, `BASH_TIMEOUT_SECONDS`, covers both reading and waiting. On a timeout or a cancellation, the command's process group is killed (POSIX) or Git's launcher is killed (Windows), then the tool waits at most `BASH_KILL_GRACE_SECONDS` and closes the pipe.

## Actors / Callers

SDK callers that construct `vidbyte.CodingAgent`, and the model inside `AgentRuntime`'s tool loop, which calls the seven tools. `BaseAgent.export_state` / `restore` and `agent.card()` consumers read the built agent.

## Inputs and Preconditions

`root_dir` is an existing directory, given as a str or Path, relative or absolute. It may hold an `AGENTS.md`. Optional fetch keys, caller tools, and a caller `context_manager` may be supplied. For bash, POSIX hosts need `bash` on `PATH`, and Windows hosts need Git for Windows, with `<G>/bin/bash.exe` within three parent folders of the resolved `git`. The tests need no network and no real keys: provider HTTP is faked at `HttpTransport._send_once`.

## Observable Outcomes

- `agent.tools.names()`, `agent.root_dir` and `agent.permission_policy`.
- The system string and the user prompt the model receives, and `agent.context_manager`.
- `reply.metadata["tool_call_states"]`.
- The tool messages the model receives.
- Files under `root_dir`.
- `agent.get_usage().operations`.
- `export_state()` and `card()` text.
- The `ToolResult` status, output and metadata of a bash call, plus whether its processes are still running after the call (from `/proc` on Linux).
- The elapsed time of a call, measured against an upper bound.
- Transports left open, unraisable loop errors, and `ResourceWarning`s after `asyncio.run` returns.

## State Transitions

Construction either raises (bad root, bad or duplicate key, duplicate tool name, a `load_agents`, `load_map`, or `progress_notes` that is not a bool, bad `setup_commands`, an unreadable `AGENTS.md` or `MAP.md`, or a `BaseAgent` identity error) or yields a ready agent. Building an agent makes no network call and starts no process except the setup commands; it reads at most 32,768 bytes each of `AGENTS.md`, `MAP.md`, and `.vidbyte/coding-agent/progress.md`, and creates only the two notes files, when they are missing. A bash call goes through these stages:

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
- `CodingAgent` adds only a constructor. Its exported state equals that of a `BaseAgent` built with the same tools, policy, and context manager.
- `AGENTS.md` is read once, at construction, from the resolved root only, and never more than 32,768 bytes of it.
- With nothing to load, the request equals a plain `BaseAgent`'s byte for byte.
- The caller's `context_manager` is never changed; its content renders after the coding sections.
- Sections render in `CodingContextSection` order whatever order the loaders are listed in.
- A setup command after a failed one never starts, and a setup command's outcome never raises.
- Without `verify_command`, the caller's middleware reaches `BaseAgent` untouched and a run makes no extra model call.
- Only a finish attempt runs the verification command; the model's own `bash` calls never do, and the command is never a tool call in `tool_call_states`.
- The attempt count belongs to one run, so a second run on the same agent starts again at one.

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
- **Edit report errors.** The diff from `write_text` or `replace_text` is built but never reaches the model's tool message, so the model cannot see what its edit changed.
- **Rewrite limit errors.** The default 300 never reaches `write_text`, so a model rewrites a big file from memory and drops code. `None` still limits, or a bad value (`0`, `True`, `2.5`, `"300"`) is accepted and sets a different limit.
- **Tool list errors.** A caller tool silently shadows a built-in tool (AC-8). Caller tools are reordered or dropped (AC-9).
- **Read-only path errors.**
  - `readonly_paths="tests/**"` is split into one-character patterns that protect nothing.
  - The raw `path` argument is matched, so `./tests/x.py`, `src/../tests/x.py`, an absolute path, or on Windows `tests\x.py` and `TESTS/x.py` edit a protected file.
  - Only existing files are checked, so a new test file is written.
  - A path the tool would reject (outside root) gets a denial instead of the tool's own error.
  - The check runs before the caller's middleware, or is added when there are no patterns.
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
- **AGENTS.md errors.**
  - The section is built but never rendered, because `BaseAgent` rebuilds its manager from plain items only.
  - The text lands after the user message, or inside the system prompt string, so `export_state()` changes.
  - With no file, the request still changes (an empty primitives zone or a new manager).
  - `load_agents=False` still reads the folder.
  - A lowercase `agents.md` is missed on Linux, or the choice between variants is not deterministic.
  - A parent folder's `AGENTS.md` is read.
  - A huge file is read whole, or the cut splits a character into garbage, or the `read_lines` start line is off by one.
  - A blank file renders an empty section; invalid UTF-8 raises.
  - A folder named `AGENTS.md` is silently skipped.
  - `load_agents="yes"` or `1` is accepted by truthiness.
  - The caller's manager is changed, or its content is dropped or rendered first.
  - `fork()` loses the section, or a later `chdir` or edit changes it.
- **MAP.md errors.** The map renders before `AGENTS.md` or not at all; `load_map=False` still reads the folder; a lowercase `map.md` is missed; the cut splits a character or names the wrong file; a folder named `MAP.md` is skipped; `load_map="yes"` is accepted. The shared `RootFileLoader` steps are pinned by the `AGENTS.md` tests.
- **Setup command errors.**
  - `setup_commands="uv sync"` runs one command per character.
  - A command after a failure still runs, or the failure is hidden or raises.
  - A command that never ends hangs construction.
  - Commands run in the process working directory instead of `root_dir`.
  - A missing bash raises, or something still starts.
  - A huge failing output fills the context.
- **Progress notes errors.** The last run's notes or a changed `.vidbyte/coding-agent/.gitignore` are overwritten. Git lists the notes folder, or the user's root `.gitignore` is edited. Another tool's files under `.vidbyte/`, such as vidbyte-cli's `.vidbyte/task-board/`, are hidden from git. The notes render before another section, or never reach the model. A notes edit made in one run is not shown to the next agent. A read-only root fails construction. `progress_notes=False` still creates the folder. A truthy stand-in flips the switch. A file over the cap crashes or shows a split character.
- **Verification errors.**
  - The run reports success although the command failed, or ends with an exception instead of the model's last answer (never-fixed cases).
  - The feedback loses the end of the command's output, which is the part a test run puts its summary in (the output-cap case).
  - The command runs on the model's own `bash` calls, before the output contracts, or outside `root_dir`.
- **Bash lookup errors.** On Windows the `PATH` `bash` (WSL's launcher) is chosen instead of Git's `bin/bash.exe`, or the lookup walks past three parent folders (AC-22). A missing bash breaks construction or the other tools (AC-17).

## Historical Regressions

None yet. This is a new feature, specified in `docs/spec/coding-agent/spec.md` r3. The S1 review found the Windows launcher orphan (EC-14), the pipe-holding descendants (EC-28 to EC-30) and the transport leak (INV-26) before any code existed.

## Test Suite Map

- `test_coding_agent_acceptance.py` checks the caller-visible promise end to end through `BaseAgent`'s loop: the spec snippet, the default policy, the edit diffs the model sees, a read-only policy, a keyed fetch shown and billed, and a missing bash.
- `test_coding_agent_contract.py` checks the following:
  - The public names.
  - The constructor-only subclass and its signature.
  - Export parity with `BaseAgent`, and `restore`.
  - Caller tools: their order and duplicates.
  - Identity errors.
  - Root validation, and the root fixed across `chdir`.
- `test_coding_agent_web_fetch.py` checks the following for each provider: provider selection, the key reaching its provider, the view against the bare tool, failed-fetch pass-through, keys absent from exports, two keys, and blank keys.
- `test_coding_agent_agents_md.py` checks `AGENTS.md` loading and the shared coding context window: the position in the request, the byte-identical request without a file, the switch, case variants, the root-only lookup, the cap and the cut character, blank and undecodable files, a broken file, strict bool validation, the caller's manager, fork, read-once, and `CodingContextWindow` and `CodingContextSectionText` on their own.
- `test_coding_agent_map_md.py` checks `MAP.md` loading: the position before the user message and after `AGENTS.md`, a missing or blank file, `map.md`, the cap and the cut character, a broken file, the switch, and strict bool validation.
- `test_coding_agent_setup_commands.py` checks setup commands: two passing lines placed after `AGENTS.md` and before the user message, stop at the first failure (a marker file proves the next command never ran), the time limit, `root_dir` as the working directory, no bash, the empty default, input validation, and the capped tail of a huge output.
- `test_coding_agent_progress_notes.py` checks progress notes: a fresh root, existing notes and `.gitignore` kept, git status clean, a sibling tool's `.vidbyte/` files still visible to git, the cross-run edit with `replace_text`, a root that cannot be written, the switch, strict bool validation, and the cap.
- `test_coding_agent_max_rewrite_lines.py` checks that the default 300 refuses a 301-line rewrite through the loop and the run goes on, that the model is told the limit, that `None` turns it off, and that bad values fail at construction. The line-counting rules are tested in `tests/test_filesystem_tools.py` (`WriteTextOverwriteLimitTests`).
- `test_coding_agent_verify_command.py` checks `verify_command` on both finish paths: a pass on the first finish, a failure fixed after feedback, a run never fixed, a run ended first by another limit, no command, invalid arguments, a missing bash, the output cap, the time limit, the root after `chdir`, the model's own bash calls, contracts first, a fresh count per run, and a plain `BaseAgent`. It also checks `FinishReview`, `MiddlewarePipeline.review_finish`, and what a refused finish leaves behind: the after-iteration hooks still run, a refused empty answer is not sent back, and the end-of-run hooks see a stopped answer.
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
- `test_coding_agent_readonly_paths.py` checks `readonly_paths` through the loop: both edit tools denied with the file unchanged and the path and pattern named, every path spelling and a new file, case on Windows, unprotected writes and protected reads, the outside-root error unchanged, no middleware by default, construction errors, and the caller's middleware first.

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
- **A case-sensitive filesystem on Windows.** The exact-name-wins `AGENTS.md` case skips on a case-insensitive filesystem; it runs on Linux CI, and locally in a folder marked with `fsutil file setCaseSensitiveInfo <dir> enable`.
- **An `AGENTS.md` edited during construction.** The read is a single bounded read; a concurrent writer is not modelled.
- **AC-27 on Python 3.13.** This must be run manually with `py -3.13` on a Windows host. CI runs 3.11 and 3.12 on Linux.
