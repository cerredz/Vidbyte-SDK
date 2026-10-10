---
spec: coding-agent
title: CodingAgent — a minimal BaseAgent with seven file-system and web tools
status: draft            # draft | approved | tests-written | implemented | reviewed | verified | pr-open | abandoned
revision: 1
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent
branch: feat/coding-agent
base_commit: 8f23fd676d60f413e0353281dd73e60dc719407a
created: 2026-10-10
updated: 2026-10-10
pr:                      # filled at S3 (draft) and finalized at S6
---

# Spec: CodingAgent — a minimal BaseAgent with seven file-system and web tools

> **TL;DR** — Add `CodingAgent`, a thin `BaseAgent` subclass that takes every `BaseAgent` keyword unchanged plus a required `root_dir` and four optional fetch keys, and pre-loads seven tools: a new minimal subprocess `BashTool` and the existing `read_lines`, `write_text`, `replace_text`, `glob`, `grep`, and one fetch tool chosen by which key was passed. The decision that matters most: the agent's own tools must actually work for the model by default, so `CodingAgent` defaults to an allow-all permission policy (a caller's policy still wins) and shows the model the text of pages a keyed provider fetched, without changing the existing fetch tools for anyone else.

## §0 User prompts

The verbatim record of every prompt lives in `docs/spec/coding-agent/request.md` §A (Prompt 1 is the original feature request; Prompt 2, below, invoked the pipeline).

### 0.1 Invoking request (verbatim)
the 7 tools sound good, and you can fetch the keys from the parameter. for bash I dont want to use the sandbox, just implement a miniamlistic subprocess bash, no default system prompt, tool names I dont care.

### 0.2 User replies during the run
_None yet. The orchestrator appends any reply the user sends during the run here verbatim, labeled with the revision it produced._

---

## Part A — Framing

## §1 Goal

Today a developer who wants a coding agent from this SDK has to assemble it by hand, and the obvious assembly does not work. There is no shell tool anywhere in `vidbyte/` (the only process spawn is the MCP stdio transport). The file tools use two different root representations (`root_dir` for glob/grep/patch, `FileSystemToolConfig.root` for read/write/replace). `BaseAgent`'s default policy allows only SAFE and READ, so a write or a shell call is returned to the model as DENIED and the loop carries on (`tests/test_agent_tool_loop.py::test_agent_denies_write_tool_by_default` pins this). The keyed fetch tools hand the model a one-line summary such as `1. https://… (5234 chars)` and keep the page text in metadata the model never sees. On the user's own Windows 11 machine, `shutil.which("bash")` resolves `C:\WINDOWS\system32\bash.EXE`, the WSL launcher, which exits 1 with "WSL2 is unable to start" (verified 2026-10-10), even though Git Bash is installed at `C:\Program Files\Git\bin\bash.exe`.

| ID | Goal (outcome) | How we will know | Source |
|---|---|---|---|
| G-1 | A developer gets a working coding agent from one constructor call: everything `BaseAgent` accepts and does, plus Bash, Read, Write, Edit, Glob, Grep, and WebFetch. | The §4 snippet runs as written; AC-1, AC-9, AC-10. | request.md §A Prompt 1 ("same settings and functionality … just add the following tools"), Prompt 2 ("the 7 tools sound good") |
| G-2 | Each of the seven tools does its job for the model without extra setup: writes, edits, and shell commands are not denied by default, and a keyed WebFetch lets the model read the page it fetched. | AC-2, AC-6, AC-7. | Prompt 1 ("has all of the tools to interact with the file system", "WebFetch (can change provide based on key)"); request.md §C constraint on default permissions |
| G-3 | Bash is a minimal, unsandboxed subprocess that cannot hang a run forever or exhaust memory, and that runs on the user's Windows machine (Git Bash) as well as on Linux and macOS. | AC-12 to AC-18, AC-22. | Prompt 2 ("dont want to use the sandbox, just implement a miniamlistic subprocess bash"); request.md §C open question on Windows bash |

## §2 Objective

When this PR merges, `vidbyte` exports `CodingAgent` (from `vidbyte.agents` and the root `vidbyte` package) and `vidbyte.tools.builtins` exports a new `BashTool`. `CodingAgent(name=…, system_prompt=…, root_dir=…, [one of four fetch keys], **any BaseAgent keyword)` builds a `BaseAgent` whose catalog starts with exactly seven tools over one resolved root folder (`bash`, `read_lines`, `write_text`, `replace_text`, `glob`, `grep`, and one of `firecrawl_fetch` / `browserbase_fetch` / `parallel_extract` / `tavily_extract` / `direct_http_fetch`), followed by any tools the caller passed. Its default permission policy allows all four permission levels. A keyed fetch result shows the model every fetched page's text. `BashTool` runs one command per call as `bash -c <command>` through `asyncio.create_subprocess_exec` in the root folder, bounded by a 600-second wall clock and a 1,000,000-byte capture cap, with the command's process group killed on timeout or cancellation. The public API contract and two READMEs are updated. This is the whole feature in one PR; nothing is deferred to a later slice.

## §3 Non-goals

- **NG-1** — Running Bash through `SandboxTransport` or any sandbox. — *Why not:* the user rejected it ("for bash I dont want to use the sandbox").
- **NG-2** — A default or built-in coding system prompt. — *Why not:* the user rejected it ("no default system prompt"); `system_prompt` passes to `BaseAgent` unchanged, and `BaseAgent` rejects an empty one.
- **NG-3** — Renaming or wrapping tools under stable names such as `web_fetch`, `edit`, or `read`. — *Why not:* "tool names I dont care"; the existing model-facing names are kept.
- **NG-4** — Any tool beyond the seven (web search, todo list, multi-edit, list-directory, notebook edit, patch). — *Why not:* the user accepted exactly seven.
- **NG-5** — Reading fetch API keys from environment variables. — *Why not:* the user chose constructor parameters ("you can fetch the keys from the parameter").
- **NG-6** — Linkup as a keyed WebFetch provider. — *Why not:* `LinkupFetchTool.execute` always returns a priced stub and never fetches (`fetch.py:193-196`), and `operations/clients/` has no Linkup client, so a Linkup key could not change what is fetched.
- **NG-7** — Changing what the existing fetch tools show the model for other users (`_render_fetched_pages`, `fetch.py:39-42`). — *Why not:* `vidbyte/tools/README.md` ("Priced Operation Tools") documents `output` as a compact summary and `metadata["operation_payload"]` as the application channel; every current user of those tools would start paying for full page text in context.
- **NG-8** — A persistent shell session (working directory or variables that survive between calls), background-job management, or streaming output. — *Why not:* not requested; a fresh process per call is the minimal subprocess bash.
- **NG-9** — Command allow-lists or deny-lists for Bash. — *Why not:* not requested; the agent's `PermissionPolicy` is the existing control.
- **NG-10** — A `VidbyteSDK().agents.coding(...)` entry on `AgentClient`, a declarative YAML agent type, or MCP-server exposure. — *Why not:* not requested.
- **NG-11** — Making `fork()`, `restore()`, or a cold session resume return a `CodingAgent` instance. — *Why not:* `AgentForker.fork` and `Session._restore_agent` build plain `BaseAgent`s by design; a `BaseAgent` with the same tools and policy behaves identically (CodingAgent adds no runtime behavior). See EC-20, EC-21, Q-5.
- **NG-12** — Windows CI coverage, and Windows bash sources other than Git for Windows (MSYS2, Cygwin, WSL). — *Why not:* CI runs only on ubuntu-latest; the Windows path is best-effort for the user's documented setup.
- **NG-13** — Bounding the size of `direct_http_fetch` bodies, `read_lines` file reads, or keyed page text in the model's context. — *Why not:* those are existing tools' behaviors; the repo's control for model-visible size is `ToolSettings.result_max_chars`, which the caller already has (Q-4).
- **NG-14** — A configurable Bash timeout or output cap (constructor knob or model-facing `timeout` parameter). — *Why not:* not requested; fixed constants plus the existing `ToolSettings.tool_timeout_seconds` cover it (Q-2).

## §4 Developer usage

```python
from vidbyte import CodingAgent

agent = CodingAgent(
    name="coder",
    system_prompt="You are a careful software engineer. Make the smallest change that fixes the task.",
    root_dir="my-project",            # an existing folder; every file tool and every bash command starts here
    firecrawl_api_key="fc-your-key",  # optional; which key you pass picks the WebFetch provider
    provider="openai",
    model_name="gpt-4.1",
)

print(agent.root_dir)
# the absolute path of ./my-project
print(agent.tools.names())
# ('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')

reply = agent.run("Run the tests with python -m pytest -q and fix the first failure.")
print(reply.content)
```

The developer passes the same keywords they would pass to `BaseAgent` and gets an agent whose model can run shell commands, read, write, and edit files under one folder, search it by name and content, and read web pages, without assembling seven tools, two root objects, and a permission policy by hand. With no fetch key the last tool is `direct_http_fetch`; to make the agent read-only, pass `permission_policy=PermissionPolicy()` (from `vidbyte.tools.security`).

## §5 Flow diagram

```mermaid
flowchart TD
  A["Developer: CodingAgent(...)"] -->|"root_dir, fetch keys, tools, permission_policy, **kwargs"| B["CodingAgent.__init__"]
  B -->|"root_dir"| R["CodingAgent._resolve_root"]
  B -->|"four optional keys"| F["CodingAgent._web_fetch_tool"]
  R -->|"absolute Path"| T["BashTool, ReadLinesTool, WriteTextTool, ReplaceTextTool, GlobTool, GrepTool"]
  F -->|"keyed tool inside _FetchedPagesView, or DirectHttpFetchTool"| W0["WebFetch tool"]
  T -->|"seven tools, then caller tools"| C["BaseAgent.__init__"]
  W0 --> C
  B -->|"caller policy, or PermissionPolicy.allow_all()"| C
  C --> D["agent.run / agent.arun"]
  D --> E["AgentRuntime: model call with tool schemas"]
  E -->|"ToolCall"| P{"AgentRuntime._check_permission"}
  P -->|"denied"| X["DENIED ToolResult; loop continues"]
  P -->|"allowed"| K["tool.execute"]
  K -->|"bash"| S["BashTool.execute: bash -c command in root_dir"]
  K -->|"keyed fetch"| W["_FetchedPagesView.execute: page text into output"]
  K -->|"file tools"| FS["root-scoped read / write / edit / glob / grep"]
  S --> M["model-visible tool message"]
  W --> M
  FS --> M
  X --> M
  M --> E
```

```mermaid
sequenceDiagram
  participant RT as AgentRuntime
  participant BT as BashTool
  participant OS as bash process (own session on POSIX)
  RT->>BT: execute(ToolCall with command)
  BT->>OS: create_subprocess_exec(bash, "-c", command, cwd=root_dir, stdin=DEVNULL)
  loop until end of output or BASH_TIMEOUT_SECONDS
    OS-->>BT: stdout+stderr bytes (first BASH_MAX_OUTPUT_BYTES kept, the rest counted)
  end
  alt command finishes in time
    BT-->>RT: ToolResult.success(output, final line "exit code: N")
  else time limit reached
    BT->>OS: kill the process group
    BT-->>RT: ToolResult.error(metadata error="timeout")
  else cancelled (agent tool timeout or task cancel)
    BT->>OS: kill the process group
    BT-->>RT: CancelledError re-raised
  end
```

Construction is where everything is validated: `CodingAgent.__init__` rejects a `root_dir` that is not an existing directory and any fetch key that is blank or supplied alongside another key, before `BaseAgent.__init__` runs and rejects an empty name or system prompt. At run time the existing `AgentRuntime._check_permission` (`runtime.py:1270`) decides each call before any tool code runs; a denial becomes a DENIED result and nothing raises. Bash state changes only inside the child process; the tool catches the time limit itself, and lets cancellation propagate after killing the child. A keyed fetch's billing metadata passes through the view untouched, so the runtime prices it exactly as it prices the bare tool.

---

## Part B — Behavior (this is the spec; everything else is framing)

## §6 Behavior

### 6.1 Invariants

- **INV-1** — A `CodingAgent` is a `BaseAgent` (`isinstance`), and the class defines only `__init__` plus private construction helpers; it never overrides `generate_reply`, `run`, `arun`, `fork`, `export_state`, `restore`, `from_run_id`, or any other `BaseAgent` method.
- **INV-2** — Every keyword `BaseAgent.__init__` accepts is accepted by `CodingAgent.__init__` with the same meaning, except that `tools` is appended after the seven coding tools and `permission_policy` defaults to allow-all.
- **INV-3** — The catalog always starts with exactly seven coding tools in this order: `bash`, `read_lines`, `write_text`, `replace_text`, `glob`, `grep`, then the one WebFetch tool; caller tools follow in the caller's order. The tool count is always 7 + the number of caller tools.
- **INV-4** — The five root-scoped tools (`read_lines`, `write_text`, `replace_text`, `glob`, `grep`) and Bash's working directory use one absolute root, resolved once at construction; `agent.root_dir` is that path, and a later change of the process working directory never moves it.
- **INV-5** — Exactly one WebFetch tool is registered. Its provider is the provider of the one key passed (`firecrawl_api_key` → `firecrawl_fetch`, `browserbase_api_key` → `browserbase_fetch`, `parallel_api_key` → `parallel_extract`, `tavily_api_key` → `tavily_extract`); with no key it is `direct_http_fetch`.
- **INV-6** — `CodingAgent` never reads an environment variable to choose or configure the fetch provider or its key.
- **INV-7** — When the caller passes `permission_policy`, that exact object becomes `agent.permission_policy`; when the caller passes none, the policy allows SAFE, READ, WRITE, and EXECUTE.
- **INV-8** — `CodingAgent` never supplies or modifies a system prompt; `system_prompt` reaches `BaseAgent` unchanged.
- **INV-9** — `BashTool` never spawns through a shell API (`shell=True`, `asyncio.create_subprocess_shell`, `os.system`) and never touches `SandboxTransport`; it execs the resolved bash executable with the argument list `[bash, "-c", command]`.
- **INV-10** — `BashTool` holds at most `BASH_MAX_OUTPUT_BYTES` of a command's output in memory, whatever the command prints; beyond that it keeps reading and counting so the command is never blocked on a full pipe.
- **INV-11** — No command runs longer than `BASH_TIMEOUT_SECONDS`. At the limit the tool kills the command (on POSIX, its whole process group) and returns an error result whose metadata `error` is `"timeout"`.
- **INV-12** — When a `BashTool` call is cancelled (the agent-level `ToolSettings.tool_timeout_seconds`, or the run's task being cancelled), the command (on POSIX, its process group) is killed before the cancellation leaves the tool, and `CancelledError` always propagates.
- **INV-13** — A command that runs to completion is a successful tool call whatever its exit code; its output ends with a line `exit code: <N>` and its metadata carries `exit_code` and `truncated`. Only "could not start" and "did not finish" are error results.
- **INV-14** — `BashTool` has `ToolPermission.EXECUTE`, so the existing tool-error retry policy never retries it automatically (`tool_error_policy.py:28`, `:142-147` treat only SAFE and READ as idempotent).
- **INV-15** — On `win32`, `BashTool` never runs the `bash` found on `PATH` (the System32 / WindowsApps WSL launcher); it uses Git for Windows' `bin/bash.exe` located from `git` on `PATH`, or reports `bash_not_found`.
- **INV-16** — A successful keyed fetch shows the model, after the provider's summary line, every returned page's final URL followed by its full content, in payload order. Error results pass through unchanged, and the result's metadata (including the operation-usage annotation) is passed through unchanged, so usage is recorded under the same operation and provider as the bare tool.
- **INV-17** — No fetch API key value ever appears in an exception message or details, a `ToolResult` output or metadata, `export_state()`, or `card()`.
- **INV-18** — Building a `CodingAgent` performs no network request and spawns no process.

**Must not regress:**
- **INV-19** — `BaseAgent`'s own default policy stays SAFE+READ (`vidbyte/agents/base.py:185`, `vidbyte/lib/dataclasses/security.py:33`); a plain `BaseAgent` still denies writes by default (`tests/test_agent_tool_loop.py::test_agent_denies_write_tool_by_default`).
- **INV-20** — The existing fetch tools' model-visible output is unchanged for every caller that is not a `CodingAgent` (`vidbyte/tools/builtins/operations/fetch.py` is not edited).
- **INV-21** — `FileSystemToolConfig.allow_write` still defaults to `False` (`vidbyte/lib/dataclasses/filesystem.py:31`); only `CodingAgent` opts in.
- **INV-22** — A `CodingAgent` can serve as a `JevAgent` specialist, because it replies through `BaseAgent.generate_reply` (`vidbyte/agents/jev/agent.py:86-98`).
- **INV-23** — `agent.fork()` on a `CodingAgent` returns a `BaseAgent` with the same tool names and the same permission policy (`vidbyte/agents/fork.py:43`, `:136-142`).
- **INV-24** — A `CodingAgent` built with a non-linear `runtime` (MCTS or actor) is accepted exactly as a `BaseAgent` with the same arguments, because `CodingAgent` adds no middleware.

### 6.2 Acceptance criteria

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-1 | a clean checkout of this branch and an existing folder `my-project` | the §4 snippet runs (with an offline runner bound for the `run` line) | `agent.root_dir` is the absolute path of `my-project`, `agent.tools.names()` is exactly `('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')`, and `run` completes through `BaseAgent`'s loop | P0 | |
| AC-2 | a `CodingAgent` built without `permission_policy` | the model calls `bash`, `write_text`, and `replace_text` | each call executes (state `succeeded`, never `denied`), the file is written and edited under `root_dir`, and the command's output reaches the model | P0 | |
| AC-3 | a `CodingAgent` built with `permission_policy=PermissionPolicy()` | the model calls `bash` and `write_text` | both are `denied`, no process is spawned, no file changes, and the run continues | P0 | |
| AC-4 | two fetch keys passed (any pair) | `CodingAgent(...)` is constructed | `ConfigurationError` is raised naming the parameters; neither key value appears in the message or `details` | P0 | |
| AC-5 | one fetch key that is empty or whitespace, or not a string | construction | `ConfigurationError`; the value does not appear in the message or `details` | P0 | |
| AC-6 | exactly one of the four keys, or none | construction | the last tool name is respectively `firecrawl_fetch`, `browserbase_fetch`, `parallel_extract`, `tavily_extract`, or `direct_http_fetch`, and no network call happened | P0 | |
| AC-7 | a `CodingAgent` with a Firecrawl key whose HTTP layer returns two scraped pages | the model calls `firecrawl_fetch` | the model-visible tool result contains both pages' final URLs and full markdown, and the agent's usage records the fetch under operation `fetch` and provider `firecrawl` exactly as for a bare `FirecrawlFetchTool` | P0 | |
| AC-8 | a caller tool whose name equals one of the seven (for example a custom `glob`) | construction | `ToolRegistrationError` ("Tool already exists: glob") at construction | P0 | |
| AC-9 | caller `tools=[custom]` (a sequence or a `Tools` catalog) | construction | `agent.tools.names()` is the seven names followed by `custom`'s name | P0 | |
| AC-10 | `system_prompt=""`, or `name`/`system_prompt` omitted | construction | the same error `BaseAgent` raises (`AgentExecutionError` "Agent system_prompt is required." / `TypeError` for a missing keyword); no prompt is supplied by `CodingAgent` | P0 | |
| AC-11 | `root_dir` that does not exist, or is a file | construction | `ConfigurationError` naming the bad `root_dir` | P0 | |
| AC-12 | a command that writes to both stdout and stderr and exits with code 3 | `BashTool` runs it | a success result whose output holds both streams and ends with `exit code: 3`, metadata `exit_code == 3` and `truncated is False` | P0 | |
| AC-13 | a command that prints more than `BASH_MAX_OUTPUT_BYTES` bytes | `BashTool` runs it | the result keeps exactly the first `BASH_MAX_OUTPUT_BYTES` bytes of output (decoded), states how many bytes were not shown, has `truncated is True`, and still reports the real exit code | P0 | |
| AC-14 | a command that does not finish within `BASH_TIMEOUT_SECONDS`, which itself started a child process (POSIX) | `BashTool` runs it | an error result with metadata `error == "timeout"` arrives within the limit plus a small margin, any output captured so far is in it, and neither the command nor its child is still running | P0 | |
| AC-15 | a long-running command (POSIX) | the awaiting task is cancelled, or `ToolSettings.tool_timeout_seconds` fires first | `CancelledError` propagates out of `execute` (the runtime reports its own timeout), and the command's process group is gone | P0 | |
| AC-16 | a `BashTool` built with a root folder (POSIX) | the command prints its working directory | the printed path is the root folder | P0 | |
| AC-17 | no usable bash executable (POSIX: none on `PATH`; Windows: no `git` on `PATH` or no `bin/bash.exe` beside it) | any `bash` call | an error result with metadata `error == "bash_not_found"` whose text says how to fix it; the run continues and the other six tools still work | P0 | |
| AC-18 | a `bash` call whose `command` is missing, empty, whitespace-only, or not a string | the runtime validates it | a validation error result and no process is spawned | P0 | |
| AC-19 | the new source files | `python lint/run.py` runs | every rule is at or below its baseline count on `main` (S055, S052, S019, S006, S039, S045, S016, S017, S025, S062, A001, A002, A006, A007, S015, C016 named explicitly) and `SDK-LINT: PASS` | P0 | |
| AC-20 | the merged branch | `from vidbyte import CodingAgent`, `from vidbyte.agents import CodingAgent`, `from vidbyte.tools.builtins import BashTool` | all three import; the first two are the same object; `python scripts/generate-sdk-public-api.py --check` passes | P0 | |
| AC-21 | a `CodingAgent` and its `export_state()` | `BaseAgent.restore(state, tools=agent.tools.all())` | the restored agent has the same tool names, an allow-all policy, and no `__resume_tool_mismatch__` marker | P1 | |
| AC-22 | `sys.platform == "win32"`, `git` at `<G>/cmd/git.exe`, `<G>/bin/bash.exe` present, and a WSL `bash` earlier on `PATH` | `BashTool` is constructed | it runs `<G>/bin/bash.exe`, never the `PATH` `bash` | P1 | |
| AC-23 | a `CodingAgent` built with a fetch key | `repr(agent.export_state())`, `agent.card()`, and every `ToolResult` from a failed fetch are inspected | the key string appears in none of them | P0 | |

### 6.3 Edge cases and failure modes

| ID | Trigger (input + state) | System behavior | User sees | Guarded by (INV-/D-) |
|---|---|---|---|---|
| EC-1 | Two fetch keys passed, e.g. Firecrawl and Tavily. Without a guard one would be silently ignored and the developer would pay the wrong vendor. | Construction raises `ConfigurationError` listing the supplied parameter names. | A clear error at construction; no key value in it. | INV-5, INV-17, D-3 |
| EC-2 | A key read from an unset or empty variable, e.g. `firecrawl_api_key=""`. Without a guard every fetch would 401 and return "firecrawl fetch failed." | Construction raises `ConfigurationError`. `None` means "no key" and selects `direct_http_fetch`. | A clear error naming the parameter. | D-3 |
| EC-3 | A non-blank but invalid or expired key. | Each fetch call returns the existing tool's failed result (`metadata["error"] == "fetch_failed"`), billed for the attempts it spent, exactly as for a bare tool; the run continues. | The model sees the fetch failure; the developer sees failed calls in `tool_call_states`. | INV-16 (pass-through) — accepted: existing tool behavior |
| EC-4 | A caller tool named like one of the seven (`glob`, `bash`, …). | Construction raises `ToolRegistrationError` from the catalog (`catalog.py:38`, `base.py:1283-1290`). | Error at construction, not a silent replacement. | D-7 |
| EC-5 | The caller passes a stricter policy, e.g. `PermissionPolicy()`. | Write, edit, and bash calls become DENIED results; the loop continues; the model may fall back to read-only work. | `tool_call_states` shows `denied`. | INV-7 — the caller's choice |
| EC-6 | `root_dir` missing, a file, or not path-like. Without a guard every file call and every bash spawn would fail per call with differing errors (`ValueError` from code search, `ToolExecutionError` from filesystem tools, `FileNotFoundError` from spawn). | Construction raises `ConfigurationError` naming the value. | One clear error at construction. | D-8 |
| EC-7 | `root_dir` is relative and the process later calls `os.chdir`. | The root was resolved to an absolute path at construction and does not move. | Tools keep working in the original folder. | INV-4 |
| EC-8 | A command never exits (`npm run dev`, `sleep 9999`, an editor waiting on a terminal). Without a bound the run would hang forever under default settings, since `ToolSettings.tool_timeout_seconds` and `AgentLoopSettings.timeout_seconds` both default to `None`. | Killed at `BASH_TIMEOUT_SECONDS` (or earlier by the agent-level tool timeout); error result `timeout` with captured output. | The model sees the timeout and the output so far. | INV-11, INV-12, D-11 |
| EC-9 | A command starts a background process that keeps the output pipe open (`server &`). | The call waits until the time limit, then the process group, including the background process, is killed (POSIX). | A timeout result. The tool description tells the model to redirect a background process's output to a file. | INV-11 — accepted limitation, documented in the tool description |
| EC-10 | A command prints without end or prints gigabytes (`yes`, `cat` of a huge log). Without the cap memory would grow until the process is killed by the OS. | The first `BASH_MAX_OUTPUT_BYTES` are kept, the rest are read and counted, until exit or the time limit. | A truncated output with the omitted byte count. | INV-10 |
| EC-11 | A command reads standard input (`cat` with no file, `read`, an interactive prompt). Without closing stdin the command would wait on the parent's stdin. | stdin is the null device, so the read sees end-of-file at once. | Normal completion, usually a non-zero exit code. | D-10 |
| EC-12 | A command leaves the root (`cd ..`, absolute paths, `rm` outside the root). | Allowed: Bash is not root-scoped; only the five file tools are. | Whatever the command did. Documented in the tool description and README. | T-1 — accepted by user decision (no sandbox) |
| EC-13 | Windows, where `bash` on `PATH` is the WSL launcher (true on the user's machine). Without INV-15 every call would exit 1 with "WSL2 is unable to start". | Git for Windows' `bin/bash.exe` is used when `git` is on `PATH`; otherwise `bash_not_found`. | Working Bash with Git for Windows installed, or a clear error. | INV-15, D-13 |
| EC-14 | Windows: a timed-out or cancelled command started its own children. | Only `bash.exe` is killed; its children may keep running. | Possibly a lingering process. | Accepted limitation (NG-12); POSIX is the CI-verified path |
| EC-15 | A `command` containing a NUL byte, or longer than the OS argument limit. Without a guard `ValueError`/`OSError` would escape as an unclassified tool failure. | Error result `spawn_failed`, naming only the exception class. | A clear "could not start" error. | D-10, INV-13 |
| EC-16 | Output that is not valid UTF-8 (binary data, a legacy code page). | Decoded with replacement characters; never raises. | Readable text with replacement marks. | D-10 |
| EC-17 | A tool result is too large for the model's context: up to 1 MB of bash output, an unbounded `direct_http_fetch` body (`vidbyte/tools/builtins/operations/fetch.py:215-229`, `vidbyte/sources/fetches/http.py:38-55`), a large `read_lines` file, or multi-megabyte keyed page text. | Passed to the model in full unless the caller set `ToolSettings.result_max_chars`, which truncates the model-visible copy (`runtime.py:1713-1718`, `settings/tool.py:65-78`). | The provider may reject the next request and the run ends with that error. | Accepted limitation (NG-13); control exists; Q-4 |
| EC-18 | The caller sets `ToolSettings.tool_timeout_seconds` above `BASH_TIMEOUT_SECONDS`, e.g. 1200 for a slow test suite. | Bash's own 600-second limit fires first. A smaller agent-level value fires first and cancels the call. | A `timeout` result at 600 seconds. | D-11 — accepted; Q-2 |
| EC-19 | Parallel tool calls (`max_parallel_tool_calls > 1`) run two bash commands, or bash and `write_text`, on the same files at once. | Independent processes; no locking. | Whatever order the OS gives; the model owns sequencing. | Accepted — same as any tool today |
| EC-20 | `CodingAgent.restore(state)` is called directly. | `TypeError` for the missing `root_dir`, raised by Python before any state is touched. | Use `BaseAgent.restore(state, tools=CodingAgent(...).tools.all())`, or a session cold-resume (which already calls `BaseAgent.restore`, `sessions/session.py:435`). | D-8 — accepted limitation, documented in README; Q-5 |
| EC-21 | `agent.fork()`. | A plain `BaseAgent` with the same tools (the view is re-wrapped around the same inner tool) and the same policy. | `isinstance(child, CodingAgent)` is `False`; behavior is identical. | INV-23 — accepted (NG-11) |
| EC-22 | Caller-supplied tools with EXECUTE or WRITE permission (for example MCP-bridged tools, whose default is EXECUTE, `tools/mcp/bridge.py:35`) on a `CodingAgent` with the default policy. | They are allowed too: one policy covers the whole agent. | They run where a plain `BaseAgent` would deny them. | INV-7 — documented in README; the caller can pass a policy |
| EC-23 | Prompt-injected text in a fetched page or a repository file tells the model to run a destructive or exfiltrating command. | The command runs under the default allow-all policy. | Whatever the command did. | T-2 — accepted by user decision (no sandbox); caller policy is the control |
| EC-24 | The command kills itself or is killed by a signal before exiting. | Completion with the OS return code (negative on POSIX for a signal). | `exit code: -9` or similar. | INV-13 |
| EC-25 | The process exits at the exact moment the time limit fires, so the kill finds no process. | `ProcessLookupError` is ignored, as `transport.py` does on close. | A `timeout` result. | D-14 |
| EC-26 | Windows with an event loop that cannot spawn subprocesses (a selector loop forced by a framework). | `NotImplementedError` escapes `execute`; the runtime turns it into an `execution_error` result (`runtime.py:1287-1297`, `:1149-1157`). | An error result naming the exception type. | Accepted — default Windows loop is the proactor loop, which supports subprocesses |
| EC-27 | The agent runs with no network. | `direct_http_fetch` or the keyed tool returns its existing failure result; nothing else is affected. | A fetch failure for the model. | Existing tool behavior |

**Rollback of the user action:** `CodingAgent` itself stores nothing; dropping the object undoes it. Effects of the model's tool calls (files written or edited under `root_dir`, anything a bash command did anywhere on the machine, provider charges for keyed fetches) are not undone by the SDK. The developer's undo is their version control for files and their vendor dashboard for charges; the README says so.

## §7 Requirements

**Functional**
| ID | Requirement | Priority | Source (request.md / G-) |
|---|---|---|---|
| FR-1 | Add class `CodingAgent(BaseAgent)` in a new module under `vidbyte/agents/`, exported from `vidbyte.agents` and `vidbyte`. | P0 | Prompt 1 ("create a new CodingAgent class … inside of the vidbyte/agents folder"); G-1 |
| FR-2 | `CodingAgent.__init__` accepts every `BaseAgent.__init__` keyword unchanged through `**kwargs`, including the required `name` and `system_prompt`; it supplies no system prompt. | P0 | Prompt 1 ("same settings and functionality"), Prompt 2 ("no default system prompt"); G-1 |
| FR-3 | `CodingAgent` requires keyword `root_dir: str \| Path`, rejects anything that is not an existing directory with `ConfigurationError`, resolves it once to an absolute path, and exposes it as `agent.root_dir`. | P0 | request.md §C open question "Name of the working-folder parameter"; G-1 |
| FR-4 | `CodingAgent` registers exactly the seven tools of INV-3: `BashTool(root)`, `ReadLinesTool(fs)`, `WriteTextTool(fs)`, `ReplaceTextTool(fs)`, `GlobTool(root)`, `GrepTool(root)`, and the WebFetch tool, where `fs = FileSystemToolConfig(root=root, allow_write=True)`. | P0 | Prompt 2 ("the 7 tools sound good"); request.md §C tool map; G-1, G-2 |
| FR-5 | WebFetch provider selection by key parameter: `firecrawl_api_key` → `FirecrawlFetchTool(client=FirecrawlClient(key))`; `browserbase_api_key` → `BrowserbaseFetchTool(client=BrowserbaseClient(key))`; `parallel_api_key` → `ParallelExtractTool(client=ParallelClient(key))`; `tavily_api_key` → `TavilyExtractTool(client=TavilyClient(key))`; none → `DirectHttpFetchTool()`. More than one key, or a supplied key that is not a non-blank string, raises `ConfigurationError` without the key value. | P0 | Prompt 1 ("WebFetch (can change provide based on key)"), Prompt 2 ("fetch the keys from the parameter"); G-1 |
| FR-6 | A keyed WebFetch tool is wrapped in a private delegating view so that a successful result's model-visible output carries every page's final URL and content (INV-16); spec, validation, permission, metadata, and pricing are those of the wrapped tool. | P0 | Forced by Prompt 1 "WebFetch": a fetch whose page the model cannot read does not fetch for the model (`fetch.py:39-42`, `lib/tools/formatter.py:322-333`); G-2 |
| FR-7 | Caller `tools` (a sequence or a `Tools` catalog) are appended after the seven; a duplicate name raises `ToolRegistrationError` at construction. | P0 | request.md §C open question "How the caller's own tools= combine with the seven"; G-1 |
| FR-8 | `permission_policy` defaults to `PermissionPolicy.allow_all()`; a caller-supplied policy is used unchanged. | P0 | request.md §C constraint ("must actually be permitted to run by default … still accepting a caller's stricter policy"); G-2 |
| FR-9 | Add `BashTool(BaseTool)` with model-facing name `bash`, permission EXECUTE, one required string parameter `command`; each call runs `asyncio.create_subprocess_exec(<bash>, "-c", command, cwd=root, stdin=DEVNULL, stdout=PIPE, stderr=STDOUT, start_new_session=True)` with the inherited environment and returns combined output and the exit code per INV-13. | P0 | Prompt 2 ("just implement a miniamlistic subprocess bash"); G-3 |
| FR-10 | `BashTool` enforces `BASH_TIMEOUT_SECONDS` and `BASH_MAX_OUTPUT_BYTES`, kills the command (POSIX: its process group) on timeout or cancellation, and re-raises cancellation. | P0 | request.md §C open question "timeout and output limits"; G-3 |
| FR-11 | `BashTool` resolves its executable once at construction: on POSIX `shutil.which("bash")`; on `win32`, `<dir of git>/../bin/bash.exe` where `git = shutil.which("git")`, if that file exists; otherwise none, and every call returns the `bash_not_found` error result. | P0 | request.md §C open question "which executable on Windows vs POSIX"; constraint "The user's machine is Windows 11 … Git Bash is installed there"; G-3 |
| FR-12 | `BashTool` is exported from `vidbyte.tools.builtins`. | P1 | Repo grain: every builtin tool is exported there (`vidbyte/tools/builtins/__init__.py`); request.md §C exports checklist |
| FR-13 | Document `CodingAgent` in `vidbyte/agents/README.md` (a short section plus a Key Modules bullet) and list bash in the `builtins/` line of `vidbyte/tools/README.md`. | P1 | request.md §C ("Bash is not root-scoped … Document it", "`vidbyte/agents/README.md` entries"); agentic-engineering folder-README obligation |
| FR-14 | Regenerate `contracts/sdk-public-api.json` after the root export is committed. | P0 | Lint C016 (baseline 0) |

**Non-functional**
| ID | Requirement | Priority | Target |
|---|---|---|---|
| NFR-1 | Minimal change ("just create a new CodingAgent class", "very minimalistic", "minimalistic subprocess bash"). | P0 | ≤ 3 new source files, 0 new dependencies, 0 new enums or dataclasses, 0 edits to existing tool classes, `BaseAgent`, `PermissionPolicy`, or `FileSystemToolConfig`; `CodingAgent` module ≤ 200 lines, `BashTool` module ≤ 250 lines |
| NFR-2 | Every gate green. | P0 | `python lint/run.py` ends `SDK-LINT: PASS` with no rule above its `main` count; `python scripts/run_ci.py` exits 0 (source stage with `PYTHONPATH` set to the worktree, package stage without); semgrep static policy clean |
| NFR-3 | Bash memory is bounded. | P0 | In-memory capture ≤ `BASH_MAX_OUTPUT_BYTES` (1,000,000) per call regardless of output volume |
| NFR-4 | Bash wall clock is bounded. | P0 | ≤ `BASH_TIMEOUT_SECONDS` (600) per call plus kill-and-reap time |
| NFR-5 | Secrets never leak through SDK surfaces. | P0 | No key value in any exception, result, `RunState`, or card (INV-17) |
| NFR-6 | Construction is side-effect free. | P1 | No network request and no process spawn while building a `CodingAgent` (INV-18) |
| NFR-7 | The work is fully enumerated ("create a checklist of all the things we have to think about/do"). | P0 | Every file, symbol, export, doc, and lint obligation the implementer needs is in §12; a reviewer can tick §12.4 line by line |
| NFR-8 | Platform coverage. | P1 | POSIX behavior verified in CI (ubuntu-latest, Python 3.11 and 3.12); Windows behavior with Git for Windows is best-effort and not CI-verified |

---

## Part C — Design

## §8 Architecture and decisions

### 8.1 Decisions
| ID | Decision | Deciding reason | Runner-up | Flips if |
|---|---|---|---|---|
| D-1 | `CodingAgent` is a thin subclass: explicit keyword-only `root_dir`, four keys, `tools`, `permission_policy`; everything else passes through `**kwargs` to `BaseAgent.__init__`. | "Same settings and functionality" without copying `BaseAgent`'s 31 parameters, which would drift; `HandoffAgent` and `ContinualTraceAgent` use the same pass-through. | Redeclare every `BaseAgent` parameter explicitly for IDE help. | The user wants a fully typed signature; or `BaseAgent` gains a parameter that must be intercepted. |
| D-2 | Tool choices: Read = `ReadLinesTool` (reads the whole file when no range is given, and ranges otherwise); Write = `WriteTextTool`; Edit = `ReplaceTextTool`; Glob = `GlobTool`; Grep = `GrepTool`. | Read/Write/Edit share one `FileSystemToolConfig` and one `allow_write` switch; `replace_text` requires exactly one match, like Claude Code's Edit; `read_lines` covers `read_text` plus ranges. | Edit = `PatchTool` (its own `root_dir`, no `allow_write`, returns a diff). | The user answers Q-1 with `PatchTool`. |
| D-3 | Fetch keys are four optional keyword parameters, `firecrawl_api_key`, `browserbase_api_key`, `parallel_api_key`, `tavily_api_key`; the one that is set picks the provider; more than one, or a blank one, is a `ConfigurationError`. | Literally "change provider based on key"; no closed-set value parameter exists, so no enum is needed; two keys fail loudly instead of resolving by a hidden precedence. | `fetch_provider: <new enum>` plus `fetch_api_key: str` (mirrors `BaseAgent`'s `provider` + `api_key`). | The user wants one provider parameter, or more fetch providers are planned. |
| D-4 | Keyed providers are Firecrawl, Browserbase, Parallel, and Tavily. | Each has a client that needs only `api_key` (`FirecrawlClient`, `BrowserbaseClient`, `ParallelClient`, `TavilyClient` in `vidbyte.tools.builtins.operations.clients`); Linkup has no client and its tool is always a stub (NG-6). | Include Linkup. | A Linkup client is added. |
| D-5 | The model sees keyed page text through `_FetchedPagesView`, a private `_ToolWrapper` subclass in the `CodingAgent` module that delegates `spec`/`validate_call`/`execute` and replaces only a successful result's `output`. | Smallest change that makes WebFetch usable without touching the fetch tools module; `_ToolWrapper` is the repo's delegating-view contract, and the runtime unwraps it before pricing (`AgentRuntime._record_operation_usage` → `ActivityToolFormatter.unwrap` → `vidbyte.tools.base._unwrap_tool`), and pricing reads only the result's metadata (`PricedOperationTool.units_used`, `mode_used`, `attempts_used`). | Edit `_render_fetched_pages` to include page text for every caller. | The user wants every keyed fetch tool to show page text by default (then the view is deleted and the fetch tools module changes). |
| D-6 | Default policy `PermissionPolicy.allow_all()`; a caller policy is used as-is. | Without it Bash, Write, and Edit are always DENIED under `BaseAgent`'s default (`PermissionPolicy.allowed` defaults to SAFE and READ); request.md §C records this as forced. | Allow exactly the four permissions the seven tools declare (identical set today). | `ToolPermission` gains a level that the coding tools must not imply. |
| D-7 | Caller tools are appended after the seven; a name collision fails at construction. | Uses the catalog's existing `ToolRegistrationError`; deterministic order; no silent override. | Let caller tools replace same-named coding tools (`Tools.add(replace=True)`). | The user asks to swap one of the seven for their own tool. |
| D-8 | `root_dir` is required, validated as an existing directory, and resolved once. Direct `CodingAgent.restore(state)` therefore raises `TypeError`; this is accepted and documented. | An agent that writes files and runs commands should not silently default to the process working directory; cold session resume already uses `BaseAgent.restore` (`Session._restore_agent`). | Default `root_dir` to the current directory so `restore` works. | The user asks for `CodingAgent.restore` (Q-5). |
| D-9 | `BashTool` lives in module `vidbyte.tools.builtins.bash` and is exported from `vidbyte.tools.builtins`. | `REPO_MAP.md` places shipped tools, including code execution, in the builtins package; it is reusable on any `BaseAgent`. | Keep it private inside the `CodingAgent` module. | The user does not want a public `BashTool`. |
| D-10 | Spawn with `asyncio.create_subprocess_exec(bash, "-c", command, cwd=root, stdin=DEVNULL, stdout=PIPE, stderr=STDOUT, start_new_session=True)`, inheriting the parent environment; decode UTF-8 with replacement. | Exactly "a minimalistic subprocess bash"; argv exec satisfies lint rule S055; merged streams keep their order under one cap; closed stdin cannot hang; inheriting the environment is what a subprocess does by default and keeps `PATH`, virtualenvs, and proxies working. | Restricted environment via `vidbyte.tools.mcp.transport.build_child_env`. | The user wants commands unable to read the developer's environment secrets (Q-3). |
| D-11 | Fixed bounds `BASH_TIMEOUT_SECONDS = 600.0` and `BASH_MAX_OUTPUT_BYTES = 1_000_000` (plus `BASH_READ_CHUNK_BYTES = 65_536` for draining) in module `vidbyte.lib.constants.bash`, not configurable. | Every outbound boundary in the repo carries its own timeout (S012's intent; the MCP stdio transport's `_DEFAULT_REQUEST_TIMEOUT`), and `ToolSettings.tool_timeout_seconds` defaults to `None`; caps stay generous per `strict-config-dataclasses.md` ("generous … never tight guesses"), and model-visible size is the caller's existing `ToolSettings.result_max_chars`. `1_000_000` matches `BaseCodeSearchTool`'s `max_file_bytes`. | No tool-level timeout; rely on `ToolSettings.tool_timeout_seconds` only (`runtime-boundaries.md` warns against parallel ceilings). | The user wants a single configurable timeout (Q-2). |
| D-12 | A finished command is a success result whatever its exit code; only "could not start" and "did not finish" are errors. | A failing `pytest` is information, not a tool failure; marking it an error would trip `ToolSettings.max_consecutive_failures` and pollute `tool_call_states`. | Non-zero exit = `ToolResult.error`. | The user wants failed commands counted as failed calls. |
| D-13 | Executable: POSIX `shutil.which("bash")`; Windows `Path(shutil.which("git")).parent.parent / "bin" / "bash.exe"` if it is a file; resolved in `BashTool.__init__`. | On the user's machine `PATH` `bash` is the failing WSL launcher, and `git` resolves to `C:\Program Files\Git\cmd\git.EXE` beside `Git\bin\bash.exe` (both verified 2026-10-10). | Use `shutil.which("bash")` everywhere. | Windows users without Git for Windows must be supported (NG-12). |
| D-14 | Stop: on POSIX `os.killpg(process.pid, signal.SIGKILL)`; on Windows `process.kill()`; ignore `ProcessLookupError`; then `await process.wait()`. Applied on timeout and, in a `finally`, whenever the call leaves while the process is still running. | `start_new_session=True` makes the shell a group leader, so one call kills its children too and the pipe closes; same `ProcessLookupError` handling as `McpStdioTransport.close`. | `process.kill()` only. | Never (correctness); Windows grandchildren remain a documented limitation. |
| D-15 | Bash error results set `metadata["error"]` to the strings `"bash_not_found"`, `"spawn_failed"`, `"timeout"`, following the builtins' existing convention. | Every builtin uses string codes in `metadata["error"]` (`GlobTool` "unsafe_path", `PatchTool` "empty_search", the fetch tools "fetch_failed"), and the runtime's own timeout code is `"timeout"`. | A new `str, Enum` in the `vidbyte.lib.enums` package. | A reviewer asks for an enum (then add a `bash` enums module there and export it). |
| D-16 | `CodingAgent` and `_FetchedPagesView` share one module, `vidbyte.agents.coding`; the view is private. | The view exists only so `CodingAgent`'s model can read pages; keeping it private adds no public API and leaves the fetch tools module byte-identical. | Put a public view in the fetch tools module. | Another feature needs the same view. |

### 8.2 Patterns inherited
- **Thin configured subclass with keyword pass-through** — keeps "same settings" without a second copy of the constructor — `vidbyte/agents/handoff.py:HandoffAgent.__init__`, `vidbyte/agents/continual_trace.py:ContinualTraceAgent.__init__`.
- **Fail-fast construction validation with `ConfigurationError(details=…)`** — invalid configuration fails where it enters — `vidbyte/agents/jev/agent.py:JevAgent.__init__` and `_require_metered_specialists`.
- **Delegating tool view** — changes one presentation aspect while spec, validation, permission, and pricing stay the wrapped tool's — `vidbyte/tools/base.py:_ToolWrapper`, `_CustomizedTool`; `vidbyte/tools/activity.py:_ActivityBoundTool`; fork re-wrapping in `vidbyte/agents/fork.py:AgentForker._clone_tool`.
- **Fixed executable plus argument list, never a shell string** — `vidbyte/tools/mcp/transport.py:McpStdioTransport.start` (`create_subprocess_exec`, line 168), required by S055.
- **Bounded capture of untrusted process output** — `vidbyte/tools/mcp/transport.py:_DEFAULT_STDERR_MAX_BYTES`; field guide `cli-backed-source-integrations.md` ("clip untrusted output by UTF-8 byte size").
- **Kill with `ProcessLookupError` tolerance** — `vidbyte/tools/mcp/transport.py:McpStdioTransport.close`.
- **Allow-list permission policy** — `vidbyte/lib/dataclasses/security.py:PermissionPolicy.allow_all`.
- **Credential injected through a client, never discovered** — `vidbyte/tools/builtins/operations/clients/_base.py:WebOperationClient` ("never discovers a credential on its own", `vidbyte/tools/README.md`).

### 8.3 Smaller design rejected

The smallest design is a `CodingAgent` whose `__init__` only builds the seven existing-or-new tool objects and passes them to `BaseAgent` with no other change: no policy default, no view, `bash` found on `PATH`. It is about 25 lines. It fails three requirements. It fails **FR-8 / AC-2**: under `BaseAgent`'s default policy every `bash`, `write_text`, and `replace_text` call comes back DENIED (`AgentRuntime._check_permission` against `PermissionPolicy`'s SAFE+READ default), so three of the seven tools never run. It fails **FR-6 / AC-7**: with a key, the model receives only `firecrawl scrape: 1 pages.\n1. <final_url> (<n> chars)` (`_render_fetched_pages` in the fetch tools module), never the page. It fails **FR-11 / AC-22** on the user's own machine, where `PATH` `bash` is the WSL launcher that exits 1. An even smaller design, a factory function returning a `BaseAgent`, fails **FR-1** (Prompt 1 asks for "a new CodingAgent class").

### 8.4 Complexity budget
| Item | Count | Justification for each |
|---|---|---|
| New files | 3 | `vidbyte/agents/coding.py` (the requested class, FR-1); `vidbyte/tools/builtins/bash.py` (no shell tool exists, FR-9); `vidbyte/lib/constants/bash.py` (named bounds required by A007 and kept under `vidbyte/lib` per `model-facing-tool-contracts.md`, D-11). Test files are written by the S2 test author and are not part of this budget. |
| New classes/modules | 3 modules; 3 classes | Modules as in "New files". Classes: `CodingAgent` (FR-1) and private `_FetchedPagesView` (FR-6, D-5, D-16) in the agent module; `BashTool` (FR-9) in the bash tool module; the constants module has no class. |
| New dependencies | 0 | `asyncio`, `os`, `shutil`, `signal`, `sys` are stdlib. |
| New config keys | 0 env vars or settings; 5 constructor parameters; 3 constants | Parameters: `root_dir` (FR-3) and four keys (FR-5). Constants: two bounds (FR-10) and one read chunk size (A007 forbids a bare literal in `read(...)`). |
| New collections/tables | 0 | Nothing is persisted. |
| New public endpoints/commands | 2 public names | `CodingAgent` (root and `vidbyte.agents`), `BashTool` (`vidbyte.tools.builtins`); model-facing tool `bash`. |

_The implementer may not exceed this budget without stopping and reporting BLOCKED._

### 8.5 Key interfaces

```python
# module vidbyte.lib.constants.bash
BASH_TIMEOUT_SECONDS: float = 600.0     # wall clock per command
BASH_MAX_OUTPUT_BYTES: int = 1_000_000  # bytes of combined output kept in memory per command
BASH_READ_CHUNK_BYTES: int = 65_536     # bytes read per drain step after the cap is reached


# module vidbyte.tools.builtins.bash   (imports the three constants by name into its module namespace)
class BashTool(BaseTool):
    root_dir: Path  # absolute, resolved at construction

    def __init__(self, root_dir: str | Path) -> None: ...
        # resolves root_dir and the bash executable once (FR-11); spawns nothing
    def spec(self) -> ToolSpec: ...
        # ToolSpec(name="bash", permission=ToolPermission.EXECUTE,
        #          parameters=(ToolParameter(name="command", type="string", required=True, ...),))
    def validate_call(self, call: ToolCall) -> str | None: ...
        # base required-parameter check, then: "command" must be a non-blank str
    async def execute(self, call: ToolCall) -> ToolResult: ...

# BashTool result contract
#   success  status=SUCCESS, output = <decoded output>
#                                    [+ "\n[output truncated: <N> bytes not shown]" when truncated]
#                                    + "\nexit code: <code>"   (always the final line)
#            metadata = {"exit_code": int, "truncated": bool}
#   errors   status=ERROR, metadata["error"] in {"bash_not_found", "spawn_failed", "timeout"}
#            bash_not_found: output says how to install bash (POSIX) or Git for Windows (win32)
#            spawn_failed:   output names the exception class only, never its message
#            timeout:        output = output captured so far + a final line naming BASH_TIMEOUT_SECONDS


# module vidbyte.agents.coding
class CodingAgent(BaseAgent):
    root_dir: Path  # absolute, resolved at construction

    def __init__(
        self,
        *,
        root_dir: str | Path,
        firecrawl_api_key: str | None = None,
        browserbase_api_key: str | None = None,
        parallel_api_key: str | None = None,
        tavily_api_key: str | None = None,
        tools: Sequence[object] | Tools = (),
        permission_policy: PermissionPolicy | None = None,
        **kwargs: Any,  # every other BaseAgent.__init__ keyword, unchanged (name, system_prompt, provider, ...)
    ) -> None: ...

class _FetchedPagesView(_ToolWrapper):   # private; not exported
    def __init__(self, tool: BaseTool) -> None: ...
    @property
    def wrapped_tool(self) -> BaseTool: ...
    def _rewrap(self, tool: BaseTool) -> BaseTool: ...
    def spec(self) -> ToolSpec: ...                      # wrapped tool's spec, unchanged
    def validate_call(self, call: ToolCall) -> str | None: ...
    async def execute(self, call: ToolCall) -> ToolResult: ...
        # success with a FetchPayload under metadata[PricedOperationTool._PAYLOAD_KEY]:
        #   dataclasses.replace(result, output=summary + "\n\n" + one block per page "<i>. <final_url>\n<content>")
        # anything else: the wrapped result, unchanged

# Model-facing tool names, in catalog order (contract):
#   "bash", "read_lines", "write_text", "replace_text", "glob", "grep",
#   then exactly one of "firecrawl_fetch" | "browserbase_fetch" | "parallel_extract" | "tavily_extract" | "direct_http_fetch"
```

## §9 Data, API, configuration, migration

### 9.1 Data model
N/A — nothing is persisted. `export_state()` already records `tool_names` and the permission values; keys and `root_dir` are not part of `RunState`, and this PR adds no field to it.

### 9.2 API and interface surface

- **`CodingAgent(...)`** (public library class). Keyword-only. Validation at the boundary, in this order: `root_dir` must be path-like and an existing directory → else `ConfigurationError("CodingAgent root_dir must be an existing directory.", details={"root_dir": <the given value as text>})`; each supplied key must be a non-blank `str` → else `ConfigurationError` naming the parameter (never the value); at most one key may be supplied → else `ConfigurationError` listing the supplied parameter names. Then `BaseAgent.__init__` applies its own validation unchanged (name, system prompt, runtime rules). A duplicate tool name raises `ToolRegistrationError` from the catalog.
- **`BashTool(root_dir)`** (public builtin) and its model-facing tool `bash` (`command: string`, required, EXECUTE). Error responses are `ToolResult.error` values as in §8.5; nothing raises out of `execute` except `CancelledError`, `NotImplementedError` from an event loop that cannot spawn (EC-26), and any other unexpected exception, which the runtime wraps (`runtime.py:1287-1297`).
- **Model-visible fetch output** for a `CodingAgent` with a key: as §8.5.
- No REST route, CLI flag, or auth surface; this is an in-process library.

### 9.3 Configuration and flags
| Variable / key | Required | Default | Purpose | Lives in |
|---|---|---|---|---|
| `BASH_TIMEOUT_SECONDS` | — (constant) | `600.0` | Per-command wall clock | `vidbyte/lib/constants/bash.py` |
| `BASH_MAX_OUTPUT_BYTES` | — (constant) | `1_000_000` | In-memory capture cap per command | `vidbyte/lib/constants/bash.py` |
| `BASH_READ_CHUNK_BYTES` | — (constant) | `65_536` | Read size while draining past the cap | `vidbyte/lib/constants/bash.py` |
| `root_dir` | yes | — | The folder every file tool and every bash command starts in | `CodingAgent.__init__` parameter |
| `firecrawl_api_key` / `browserbase_api_key` / `parallel_api_key` / `tavily_api_key` | no (at most one) | `None` | Picks and authenticates the WebFetch provider | `CodingAgent.__init__` parameters |

No environment variables are read (INV-6). The existing `ToolSettings.tool_timeout_seconds` and `ToolSettings.result_max_chars` (via `agent_loop_settings=AgentLoopSettings(tool_settings=ToolSettings(...))`) remain the caller's agent-wide controls.

### 9.4 Migrations and compatibility
Additive only. `contracts/sdk-public-api.json` gains `"CodingAgent"`; `vidbyte.tools.builtins.__all__` gains `"BashTool"`. No existing signature, default, or output changes; no deprecation path is needed.

## §10 Security and tenancy
| ID | Attacker | Shortest path to harm | Control | Where the control sits |
|---|---|---|---|---|
| T-1 | Careless user | Points `root_dir` at `/` or their home folder, or lets the model `rm -rf` through Bash, which is not root-scoped. | File tools reject paths outside `root_dir` (`FileSystemPermissions.resolve_scoped_path`, `BaseCodeSearchTool.resolve_under_root`); the agent's `PermissionPolicy` is checked before every call (`AgentRuntime._check_permission`). Bash is unscoped by the user's decision; README and the tool description say so. | In SDK code, before tool execution (`vidbyte/agents/runtime.py`, `vidbyte/lib/tools/filesystem/permissions.py`) |
| T-2 | Hostile content (prompt injection in a fetched page or a repository file) | The model is told to run `curl … \| sh` or to delete files, and the default allow-all policy lets it. | `PermissionPolicy` passed by the caller (deny EXECUTE/WRITE); `BashTool` is EXECUTE so it is never auto-retried (INV-14). No sandbox, by the user's explicit decision (NG-1); accepted risk, stated in README. | `AgentRuntime._check_permission`; `ToolErrorPolicyMiddleware._tool_permission_allows_retry` |
| T-3 | Compromised teammate / leaked credential | A fetch key leaks through an error message, tool metadata, a checkpoint, or a trace; or a bash command reads secrets from the inherited environment and sends them out. | Keys are validated without echoing them, held only inside the provider client (`FirecrawlClient._headers` keeps the key in the request header only), and never stored on the agent, in `RunState`, or in results (INV-17). Environment exposure to Bash is accepted (D-10); Q-3 offers an allow-listed environment, default no. | `CodingAgent.__init__` validation; `WebOperationClient` (`clients/_base.py`); `RunState` export (`BaseAgent.export_state`) |
| T-4 | Another tenant | N/A — the SDK runs inside the developer's own process with the developer's own credentials; there is no multi-tenant boundary in this change. | — | — |

Secrets follow the repo's existing convention: credentials are passed explicitly to clients, never discovered (`vidbyte/tools/README.md`, "Priced Operation Tools"); S017 forbids exception text in tool results under `vidbyte/tools/`.

## §11 Codebase grounding

- **Rules read:** `AGENTS.md` in full — Repository Map (read `REPO_MAP.md` before creating files; `docs/` opaque; full gate `python scripts/run_ci.py`), Style 1 (one-level call chains, no nested functions), Style 2 (narrate main functions), Style 3 (layers; `vidbyte/lib/` at the bottom; no cycles; files well under 1,000 lines), Style 4 (validated frozen dataclasses for core I/O; enums for closed sets), Placement Rules (dataclasses in `vidbyte/lib/dataclasses/<domain>.py`, enums in `vidbyte/lib/enums/<domain>.py` and exported), Existing code (do not copy old placement as precedent). `REPO_MAP.md` entries for `vidbyte/agents/`, `vidbyte/tools/`, `vidbyte/tools/builtins/`, `vidbyte/tools/filesystem/`, `vidbyte/tools/security/`, `vidbyte/lib/constants/`, `vidbyte/lib/enums/`, `vidbyte/lib/dataclasses/`. Folder READMEs: `vidbyte/agents/README.md` (Key Modules, no File Index), `vidbyte/tools/README.md` (Key Modules, Priced Operation Tools). Lint rule sources opened: A001, A002, A005, A007, S017 (scope), S016 (scope), S025, S055, S062.
- **Field-guide entries applied:**
  - `local-ci-verification.md` — source stage with `PYTHONPATH=$(pwd)`, package stage without; `git add` new files before lint and semgrep; check S051 over the whole tree.
  - `blocking-lint-invariants.md` — never name a helper `request` (S012); A006 counts function-local imports.
  - `model-facing-tool-contracts.md` — 4–5 sentence descriptions for the tool and each parameter, no examples; shared constants under `vidbyte/lib`.
  - `cli-backed-source-integrations.md` — bound process output by UTF-8 bytes, own timeout and cancellation. Its "do not expose command strings to model-facing inputs" is overridden by the user's explicit request for a Bash tool (D-10, T-2).
  - `strict-config-dataclasses.md` — size caps generous, never tight guesses (D-11).
  - `runtime-boundaries.md` — do not add a parallel configurable ceiling; D-11 adds a fixed transport bound, not a setting, and keeps `ToolSettings.tool_timeout_seconds` as the configurable control.
  - `class-bound-helpers.md` — helpers are methods on `BashTool`/`CodingAgent`, not module-level free functions.
  - `agents-md-map.md` — no `REPO_MAP.md` change for a single new module.
  - `review-scope.md` — every file in the diff traces to the minimal surface.
- **Stack (from manifests):** Python `>=3.11` (`pyproject.toml`), package `vidbyte-sdk` 0.2.0; asyncio subprocesses; `httpx` under `vidbyte/lib/http/transport.py`; no database; tests on pytest 8.3.5 with pytest-asyncio 1.3.0; lint via `lint/run.py` with ruff 0.16.4 and mypy 2.3.1 adapters.
- **Commands (exact, from `context/code-map.md` §1 / §3 and AGENTS.md):**
  - Install: `python -m pip install -e ".[dev]"`
  - Lint: `python lint/run.py` · one rule: `python lint/run.py --rule <ID>` · import order over the whole tree: `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`
  - Typecheck: runs inside lint as S009 — `python lint/run.py --rule S009`
  - Test (focused): `PYTHONPATH=$(pwd) python -m pytest -q tests/<file>.py`
  - Test (full): `PYTHONPATH=$(pwd) python -m pytest`
  - Full local gate: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with `PYTHONPATH` unset (AGENTS.md's single command is `python scripts/run_ci.py`; the split is required from a worktree by `local-ci-verification.md`)
  - Public API contract: `python scripts/generate-sdk-public-api.py` (after committing `vidbyte/__init__.py`) · verify: `python scripts/generate-sdk-public-api.py --check`
  - Remote-only checks: all CI is `workflow_dispatch` only — `gh workflow run ci.yml --ref feat/coding-agent` (ubuntu-latest, Python 3.11/3.12 source, 3.11 package) and `gh workflow run static-policy.yml --ref feat/coding-agent` (semgrep). Semgrep is not in `run_ci.py`; locally, in its own venv or pipx with `semgrep==1.170.1`: `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` and `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`. `agents-md-placement.yml` is also dispatch-only.
- **Baseline on clean `origin/main` (this worktree at `194921b1`, which adds only `docs/`):** `python lint/run.py` → `SDK-LINT: PASS` (run by S1, 59 s). Counts relevant here: A001 643/643, A002 682 (baseline 703, IMPROVED), A006 34/34, A007 255/255, C016 0, S008 19/19, S015 13/13, S016 50/50, S017 78 (baseline 79, IMPROVED), S019 5/5, S025 261 (baseline 263, IMPROVED), S039 5/5, S045 2/2, S051 258 (baseline 259, IMPROVED), S052 0, S055 0. The IMPROVED headroom predates this PR and must not be consumed. Pytest and the package stage were not run by S0 or S1; known flake: `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` on CI Python 3.11.
- **Directory layout relevant to this change:**
  ```
  vidbyte/
    agents/            base.py, handoff.py, continual_trace.py, jev/agent.py, fork.py, __init__.py, README.md   (+ coding.py)
    tools/
      base.py          BaseTool, _ToolWrapper, _unwrap_tool
      builtins/        __init__.py, code_execution.py, code_search/{glob,grep}.py, operations/{base,fetch}.py, operations/clients/   (+ bash.py)
      filesystem/      read_lines.py, write_text.py, replace_text.py, _base_tool.py
      mcp/transport.py the only subprocess precedent
      README.md
    lib/
      constants/       speed.py, trace.py, ...   (+ bash.py)
      dataclasses/     filesystem.py (FileSystemToolConfig), security.py (PermissionPolicy), operations.py (FetchPayload), tools.py
    __init__.py
  contracts/sdk-public-api.json
  ```
- **Nearest sibling feature (the template to copy):**
  - `vidbyte/agents/handoff.py` (`HandoffAgent`) and `vidbyte/agents/continual_trace.py` (`ContinualTraceAgent`) — copy the single-module `BaseAgent` subclass with `**kwargs` pass-through and fixed tools; do **not** copy their "Context Protocol Header" docstrings.
  - `vidbyte/agents/jev/agent.py` — copy its A001 header format (FILE / PURPOSE / ROLE IN CODEBASE / ARCHITECTURE NOTE / COMMON MODIFICATION PATTERNS / KNOWN EDGE CASES / RELATED DOCS / TESTS) and its `ConfigurationError(..., details=...)` style; do **not** copy its closed settings surface.
  - `vidbyte/tools/builtins/code_execution.py` (`CodeExecutionTool`) — copy the builtin tool shape: A001 header, multi-sentence single-literal descriptions, narrated `execute`.
  - `vidbyte/tools/mcp/transport.py` — copy `create_subprocess_exec` argv style, bounded buffer, and kill/`ProcessLookupError` handling; do **not** copy its `asyncio.Lock` (S039) or its allow-listed environment (D-10).
  - `vidbyte/tools/base.py:_CustomizedTool` — copy the `_ToolWrapper` delegation shape for `_FetchedPagesView`.
- **Reusable pieces:**
  - `vidbyte/agents/base.py:BaseAgent.__init__` — owns everything except the tool list and the default policy.
  - `vidbyte/tools/builtins/code_search/glob.py:GlobTool`, `grep.py:GrepTool` — `GlobTool(root_dir)`, `GrepTool(root_dir)`, READ.
  - `vidbyte/tools/filesystem/read_lines.py:ReadLinesTool`, `write_text.py:WriteTextTool`, `replace_text.py:ReplaceTextTool` — built from one `FileSystemToolConfig(root=…, allow_write=True)`.
  - `vidbyte/tools/builtins/operations/fetch.py:FirecrawlFetchTool`, `BrowserbaseFetchTool`, `ParallelExtractTool`, `TavilyExtractTool`, `DirectHttpFetchTool` and `operations/clients/{firecrawl,browserbase,parallel,tavily}.py` clients — constructed with `client=<Client>(api_key)`.
  - `vidbyte/tools/builtins/operations/base.py:PricedOperationTool._PAYLOAD_KEY` — the documented `operation_payload` key the view reads.
  - `vidbyte/lib/dataclasses/operations.py:FetchPayload`, `FetchedPage` — `pages`, `final_url`, `content`.
  - `vidbyte/lib/dataclasses/security.py:PermissionPolicy.allow_all` (import via `vidbyte.tools.security`).
  - `vidbyte/tools/catalog.py:Tools` — `all()`, `names()`; raises `ToolRegistrationError` on duplicates.
  - `vidbyte/tools/base.py:_ToolWrapper` (already imported across packages by `vidbyte/agents/fork.py`).
  - `vidbyte/lib/errors:ConfigurationError`, `ToolExecutionError`.
- **Code-style exemplar** (`vidbyte/tools/builtins/code_execution.py`, lines 135–147):
  ```python
      async def execute(self, call: ToolCall) -> ToolResult:
          code = call.arguments.get("code", "")

          # Refuse obvious shell, file, and dynamic-evaluation requests up front with a clear error.
          blocked = self._blocked_fragment(code)
          if blocked is not None:
              return ToolResult.error(
                  self.name,
                  f"Security exception: use of '{blocked}' is forbidden in this simulated sandbox.",
              )

          # Simulate stdout by rendering each print line; other statements produce no output.
          lines = [line.strip() for line in code.split("\n") if line.strip()]
  ```
- **Domain glossary:**
  - *root* / `root_dir` — the folder the five file tools are confined to and where each bash command starts.
  - *keyed provider* — a fetch vendor reached through a `WebOperationClient` built from an API key.
  - *priced operation tool* — a `PricedOperationTool` subclass whose results carry `metadata["operation_usage"]`, which the runtime turns into billed usage.
  - *model-visible result* — the `ToolResult.output` the runtime formats into the next model request (`lib/tools/formatter.py:309-333`); metadata never reaches the model.
  - *DENIED* — `ToolCallState.DENIED`, the state of a call the permission policy rejected; the loop continues.
  - *view* — a `_ToolWrapper` subclass that delegates to one wrapped tool; the runtime unwraps views for pricing and binding.
- **Prior specs / design docs / ADRs that constrain this:** none named by the orchestrator (`docs/` is opaque per AGENTS.md).
- **Conflicts between house style and AGENTS.md / repo grain:** (1) House style wants enums for meaningful strings; every builtin uses string codes in `metadata["error"]`, and AGENTS.md's enum rule names fields, parameters, and registry keys — repo grain wins (D-15). (2) AGENTS.md Style 4 asks for dataclass inputs to core logic; `CodingAgent` follows the `HandoffAgent` keyword pass-through because the user asked for `BaseAgent`'s exact settings, and the tool I/O is already `ToolCall`/`ToolResult` dataclasses. No other conflict.

## §12 Work breakdown — everything this PR has to do

### 12.1 Feature list
| ID | Feature (capability this PR adds) | Serves | Visible to |
|---|---|---|---|
| W-1 | Named Bash bounds as shared constants. | FR-10, NFR-3, NFR-4 | developer |
| W-2 | `BashTool`: minimal subprocess bash with bounded output and time, process-group kill, cancellation safety, and per-platform executable resolution. | FR-9, FR-10, FR-11, AC-12–AC-18, AC-22 | developer, model |
| W-3 | `BashTool` exported from `vidbyte.tools.builtins`. | FR-12, AC-20 | developer |
| W-4 | `CodingAgent`: root validation, seven tools, key-selected WebFetch, caller-tool merge, default allow-all policy, `**kwargs` pass-through. | FR-1–FR-5, FR-7, FR-8, AC-1–AC-6, AC-8–AC-11, AC-21, AC-23 | developer |
| W-5 | `_FetchedPagesView`: keyed fetch results show page text to the model. | FR-6, AC-7 | model |
| W-6 | `CodingAgent` exported from `vidbyte.agents` and `vidbyte`, public API contract regenerated. | FR-1, FR-14, AC-20 | developer |
| W-7 | README documentation of `CodingAgent` and `bash`. | FR-13 | developer |

### 12.2 Folder and module map
| Folder | Kind of code (per repo rules) | New? | README / header obligation | May import from |
|---|---|---|---|---|
| `vidbyte/lib/constants/` | Shared named constants, bottom layer (REPO_MAP) | no | A001 header on the new module; no README in folder; no `__init__` re-export required (precedent `trace.py`, `jev.py` are not re-exported) | nothing in `vidbyte` |
| `vidbyte/tools/builtins/` | Shipped tool library (REPO_MAP: "code execution, code search…") | no | A001 header on `bash.py`; folder has no README — `vidbyte/tools/README.md` Key Modules `builtins/` line updated | `vidbyte.lib.*`, `vidbyte.tools.base`, `vidbyte.tools.types` (never `vidbyte.agents`) |
| `vidbyte/agents/` | Executable agent actors (REPO_MAP) | no | A001 header on `coding.py`; `vidbyte/agents/README.md` Key Modules bullet + section | `vidbyte.agents.base`, `vidbyte.tools.*` concrete submodules, `vidbyte.lib.*` |
| repo root `contracts/` | Generated public API contract | no | generated only by `scripts/generate-sdk-public-api.py` | — |

### 12.3 File-by-file actions
| # | Action | Path | Kind of code | What exactly changes (symbols, signatures, exports, registrations) | Governing standard (AGENTS.md § / placement rule / field-guide file / lint rule ID) | Serves | Phase |
|---|---|---|---|---|---|---|---|
| 1 | CREATE | `vidbyte/lib/constants/bash.py` | constants | A001 header (FILE, PURPOSE, ROLE IN CODEBASE naming `vidbyte/tools/builtins/bash.py` as the consumer, ARCHITECTURE NOTE "constants only", COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS `docs/spec/coding-agent/spec.md`, TESTS). `from __future__ import annotations`. `BASH_TIMEOUT_SECONDS = 600.0`, `BASH_MAX_OUTPUT_BYTES = 1_000_000`, `BASH_READ_CHUNK_BYTES = 65_536`. `__all__` listing the three. Imports nothing from `vidbyte`. | A001; A007 (uppercase named constants); REPO_MAP `vidbyte/lib/constants/`; `model-facing-tool-contracts.md` (constants under `vidbyte/lib`); AGENTS.md Style 3 (lib imports nothing above it); precedent `vidbyte/lib/constants/trace.py` | W-1, FR-10, D-11 | P1 |
| 2 | CREATE | `vidbyte/tools/builtins/bash.py` | tool | A001 header (FILE, PURPOSE, ROLE IN CODEBASE: exported by `vidbyte/tools/builtins/__init__.py`, used by `vidbyte/agents/coding.py`, executed by `vidbyte/agents/runtime.py`; ARCHITECTURE NOTE: argv exec, own session, bounded capture, kill on timeout/cancel; FUNCTION INVENTORY; COMMON MODIFICATION PATTERNS; WHAT NOT TO DO IN THIS FILE (no shell=True, no SandboxTransport, no env filtering, no persistent session); KNOWN EDGE CASES (Windows WSL launcher, Windows grandchildren, background processes holding the pipe); RELATED DOCS `docs/spec/coding-agent/spec.md`; TESTS). Imports the three constants **by name** (`from vidbyte.lib.constants.bash import BASH_...`). `class BashTool(BaseTool)` with: `__init__(self, root_dir: str \| Path) -> None` storing `self.root_dir = Path(root_dir).resolve()` and `self._executable: str \| None` from `_find_bash()`; `@staticmethod _find_bash() -> str \| None` (D-13); `spec()` → `ToolSpec(name="bash", description=<one literal, ≥ 4 sentences>, parameters=(ToolParameter(name="command", type="string", description=<one literal, ≥ 4 sentences>, required=True),), permission=ToolPermission.EXECUTE)`; `validate_call(call)` → base check, then non-blank `str` `command`; `async execute(call)` (main, narrated) → no executable → `bash_not_found` result; `_spawn(command)` (catches `OSError` and `ValueError` → `spawn_failed` result naming `type(exc).__name__`); read under `asyncio.wait_for(..., BASH_TIMEOUT_SECONDS)` into a `bytearray` via `_read_bounded(stream, buffer) -> int` (returns bytes not kept); on `TimeoutError` → `_stop(process)` and `timeout` result with captured text; on completion → `await process.wait()` and `_render(buffer, omitted, exit_code)` success result; a `try/finally` calls `_stop(process)` whenever the process is still running (covers cancellation; no `except` that swallows `CancelledError`). `_stop(process)`: POSIX `os.killpg(process.pid, signal.SIGKILL)`, Windows `process.kill()`, ignore `ProcessLookupError`, then `await process.wait()`. `__all__ = ["BashTool"]`. Description content: runs one command in a fresh bash process started in the root folder; changes of directory and variables do not carry over; it is not confined to the root folder; stdout and stderr are returned together, cut after `BASH_MAX_OUTPUT_BYTES` bytes; the exit code is the last line; commands are stopped after `BASH_TIMEOUT_SECONDS` seconds; stdin is closed; a background process must redirect its output to a file or the call waits for the time limit. | AGENTS.md Styles 1–2 (flat helpers, narrated `execute`); REPO_MAP `vidbyte/tools/builtins/`; S055 (argv exec only); S052 (asyncio subprocess API only in async code); S019 (cancellation re-raised; cleanup in `finally`); S006 (no `create_task`); S039 (no `asyncio.Lock`); S045 (no async function with a timeout-named parameter); A002 (`# @intent` on `_spawn` — token "subprocess" — and on any other method whose identifiers or annotations hit a policy token); S009 (`sys.platform` branches for `os.killpg`/`signal.SIGKILL`); A007 (no bare numbers near timeout/byte/read); S016 (no builtin exceptions raised); S017 (no exception text in results); S025 + S062 (≥ 4-sentence single-literal descriptions); `model-facing-tool-contracts.md` (no examples in descriptions); `cli-backed-source-integrations.md` (byte-bounded output); `class-bound-helpers.md` (helpers are methods); D-10, D-12–D-15 | W-2, FR-9, FR-10, FR-11, INV-9–INV-15 | P1 |
| 3 | MODIFY | `vidbyte/tools/builtins/__init__.py` | package exports | Add `from vidbyte.tools.builtins.bash import BashTool` in sorted position (before `code_execution`); add `"BashTool"` to the literal `__all__` in its sorted position; add one Architecture bullet "Minimal subprocess bash tool from builtins.bash." to the existing header. Do not convert the header format. | S015 (`__all__` entries unique and bound); S051 (import order, checked over the whole tree); AGENTS.md "Do not rewrite untouched code" | W-3, FR-12 | P1 |
| 4 | CREATE | `vidbyte/agents/coding.py` | agent | A001 header copied in format from `vidbyte/agents/jev/agent.py` (FILE, PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, FUNCTION INVENTORY, COMMON MODIFICATION PATTERNS, WHAT NOT TO DO IN THIS FILE: no `generate_reply` override, no env key lookup, no default prompt, no edits to the wrapped tools; KNOWN EDGE CASES: restore `TypeError`, fork returns `BaseAgent`, allow-all covers caller tools; RELATED DOCS `docs/spec/coding-agent/spec.md`; TESTS). Imports concrete submodules only: `vidbyte.agents.base.BaseAgent`; `vidbyte.tools.builtins.bash.BashTool`; `vidbyte.tools.builtins.code_search.glob.GlobTool`, `.grep.GrepTool`; `vidbyte.tools.filesystem.read_lines.ReadLinesTool`, `.write_text.WriteTextTool`, `.replace_text.ReplaceTextTool`; `vidbyte.tools.builtins.operations.fetch` (five fetch tools); `vidbyte.tools.builtins.operations.clients.{firecrawl,browserbase,parallel,tavily}` clients; `vidbyte.tools.builtins.operations.base.PricedOperationTool`; `vidbyte.tools.base.BaseTool, _ToolWrapper`; `vidbyte.tools.catalog.Tools`; `vidbyte.tools.security.PermissionPolicy`; `vidbyte.tools.types` (`ToolCall`, `ToolResult`, `ToolSpec`, `ToolStatus`); `vidbyte.lib.dataclasses.filesystem.FileSystemToolConfig`; `vidbyte.lib.dataclasses.operations.FetchPayload`; `vidbyte.lib.errors.ConfigurationError`. `class CodingAgent(BaseAgent)` with `__init__` exactly as §8.5 (main, narrated, `# @intent` block because it handles `permission_policy`): `root = self._resolve_root(root_dir)`; `fetch_tool = self._web_fetch_tool(...)`; `fs = FileSystemToolConfig(root=root, allow_write=True)`; `coding_tools = (BashTool(root), ReadLinesTool(fs), WriteTextTool(fs), ReplaceTextTool(fs), GlobTool(root), GrepTool(root), fetch_tool)`; `caller_tools = tools.all() if isinstance(tools, Tools) else tuple(tools)`; `self.root_dir = root`; `super().__init__(tools=(*coding_tools, *caller_tools), permission_policy=permission_policy if permission_policy is not None else PermissionPolicy.allow_all(), **kwargs)`. `@staticmethod _resolve_root(root_dir) -> Path` (FR-3, EC-6). `@staticmethod _web_fetch_tool(*, firecrawl_api_key, browserbase_api_key, parallel_api_key, tavily_api_key) -> BaseTool` with `# @intent` (token "fetch"): validate each supplied key, reject more than one, return `_FetchedPagesView(<Tool>(client=<Client>(key)))` or `DirectHttpFetchTool()`, using an explicit ordered tuple of (key, tool class, client class) — no string-keyed registry, no lambdas. `class _FetchedPagesView(_ToolWrapper)` as §8.5, reading the payload with `PricedOperationTool._PAYLOAD_KEY` (no duplicated `"operation_payload"` literal) and returning `dataclasses.replace(result, output=...)`. `__all__ = ["CodingAgent"]`. | AGENTS.md Styles 1–3 (one level of helpers, narrated `__init__`, small single-purpose classes); REPO_MAP `vidbyte/agents/`; A001 (copy `jev/agent.py`, not "Context Protocol Header"); A002 (`# @intent` near `__init__` and `_web_fetch_tool`); A006 (agents → tools/lib only; no import of the `vidbyte.tools.builtins` package root, mirroring `vidbyte/__init__.py` and `runtime.py:149`); S007 (annotations incl. `**kwargs: Any`); S051; `jev/agent.py` `ConfigurationError(details=)` style; INV-1 (no `BaseAgent` method overrides; `jev/agent.py:86-98`); NG-2, NG-5 | W-4, W-5, FR-1–FR-8, INV-1–INV-8, INV-16–INV-18 | P2 |
| 5 | MODIFY | `vidbyte/agents/__init__.py` | package exports | Add `from vidbyte.agents.coding import CodingAgent` in sorted position (after the `vidbyte.agents.codex` import block, before `context_algorithms`); add `"CodingAgent"` to the literal `__all__` (between `"CodexUsageResponse"` and `"ContinualTraceAgent"`); add one Architecture bullet "- CodingAgent: BaseAgent preloaded with seven coding tools over one root folder." Do not convert the header format. | S015; S051; AGENTS.md "Do not rewrite untouched code" | W-6, FR-1 | P2 |
| 6 | MODIFY | `vidbyte/__init__.py` | root exports | Add `CodingAgent,` to the `from vidbyte.agents import (...)` block in sorted position (after `CodexUsageResponse,`, before `FinalizationContext,`); add `"CodingAgent"` to `__all__` next to `"JevAgent"`; add `CodingAgent` to the header's "Agent exports" line. Commit this file before row 7. | S015 (every public name imported into `vidbyte/__init__.py` is in `__all__`); S051; C016 prerequisite (generator refuses while this file is uncommitted) | W-6, FR-1, AC-20 | P3 |
| 7 | MODIFY | `contracts/sdk-public-api.json` | generated contract | Regenerate with `python scripts/generate-sdk-public-api.py` after row 6 is committed; commit the result. Never hand-edit. | C016 (baseline 0); `scripts/generate-sdk-public-api.py` header "Commit the vidbyte/__init__.py … change first" | W-6, FR-14 | P3 |
| 8 | MODIFY | `vidbyte/agents/README.md` | doc | Add Key Modules bullet "- `coding.py`: `CodingAgent`, a `BaseAgent` preloaded with bash, read, write, edit, glob, grep, and one web-fetch tool over one root folder." Add a short "## Coding Agent" section (≤ 30 lines) after "## Usage": one construction example (no real keys), how the key picks the fetch provider, and these caveats: default policy allows all tools including caller tools (pass `PermissionPolicy()` for read-only); Bash is not confined to `root_dir` and runs unsandboxed with the inherited environment; per-command limits of 600 s and 1,000,000 bytes, and `ToolSettings.tool_timeout_seconds` / `result_max_chars` as the agent-wide controls; fork and restore return a `BaseAgent` (`BaseAgent.restore(state, tools=CodingAgent(...).tools.all())`); Windows needs Git for Windows. | agentic-engineering folder README obligation (house-style table); request.md §C ("Document it"); `vidbyte/agents/README.md` existing section style | W-7, FR-13 | P3 |
| 9 | MODIFY | `vidbyte/tools/README.md` | doc | In "## Key Modules", extend the `builtins/` bullet to include "a minimal subprocess bash tool". No other change. | agentic-engineering folder README obligation; existing Key Modules list | W-7, FR-13 | P3 |

### 12.4 Standards checklist for this change

- [ ] Each new `.py` file (`coding.py`, `bash.py`, `lib/constants/bash.py`) opens with a module docstring holding non-empty `FILE:`, `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `COMMON MODIFICATION PATTERNS:`, `KNOWN EDGE CASES:`, `RELATED DOCS:`, and `TESTS:` lines, in the format of `vidbyte/agents/jev/agent.py`, never the "Context Protocol Header" format — *source:* `lint/rules/a001_agent_readable_file_headers.py` `REQUIRED_FIELDS`; agentic-engineering `file_headers.md`.
- [ ] `git add` every new file before running `python lint/run.py` or semgrep; both read only tracked files — *source:* `context/code-map.md` §1; `local-ci-verification.md`.
- [ ] A `# @intent <name>` comment, followed by the invariant and why, sits within 4 lines before to 20 lines after the `def` line of every function whose own name, body identifiers, or annotations (split on `_` and `.`) contain a policy token. In this design that is at least `CodingAgent.__init__` ("permission" from `permission_policy`), `CodingAgent._web_fetch_tool` ("fetch" in its name), `BashTool._spawn` ("subprocess" from `create_subprocess_exec`), and any `BashTool` method annotated with `asyncio.subprocess.Process`; run `python lint/run.py --rule A002` to catch the rest — *source:* `lint/rules/a002_intent_comments.py` (`IntentAnalyzer._categories`, `POLICY_TOKENS`, `INTENT_WINDOW_LINES = 20`).
- [ ] Platform branches test `sys.platform == "win32"` (not `os.name`), so mypy narrows `os.killpg` and `signal.SIGKILL`, which typeshed declares only under `if sys.platform != "win32"`, on both Windows and Linux hosts — *source:* S009 (`lint/rules/s009_staged_mypy_contracts.py`, whole-package mypy ratchet); mypy typeshed `stdlib/os/__init__.pyi:1516-1520`, `stdlib/signal.pyi`.
- [ ] No bare numeric literal in any expression or default near timeout/byte/limit/token/char/read context; use `BASH_TIMEOUT_SECONDS`, `BASH_MAX_OUTPUT_BYTES`, `BASH_READ_CHUNK_BYTES` — *source:* `lint/rules/a007_operational_constants.py` (`OPERATIONAL_TOKENS`, `OPERATIONAL_CALLS` includes `read`).
- [ ] The `bash` tool description and the `command` parameter description are each one string literal (or one f-string) of at least 4 sentences, contain no examples, and state the behaviors listed in §12.3 row 2 — *source:* S025 (`MINIMUM_SENTENCES = 4`), S062 (no adjacent string literals), `model-facing-tool-contracts.md`.
- [ ] No `shell=True`, no `asyncio.create_subprocess_shell`, no `os.system`; the only spawn is `asyncio.create_subprocess_exec(executable, "-c", command, ...)` — *source:* S055.
- [ ] Inside `async def`, only the asyncio subprocess API is used (no `subprocess.run`/`Popen`/`os.wait*`) — *source:* S052 (ASYNC220/221/222).
- [ ] No `except BaseException`, `except asyncio.CancelledError`, or bare `except` that does not re-raise; process cleanup lives in `finally` — *source:* S019.
- [ ] No `asyncio.create_task`, no `asyncio.Lock`, no `typing.TypedDict`, no `typing.assert_never` — *source:* S006, S039.
- [ ] No `async def` takes a parameter named like a timeout — the limit is passed to `asyncio.wait_for` from the constant — *source:* S045.
- [ ] No builtin `Exception`/`RuntimeError`/`TypeError`/`ValueError` is raised in `vidbyte/tools/builtins/bash.py`; failures are `ToolResult.error` values — *source:* S016 (`BOUNDARY_PREFIXES`).
- [ ] No `str(exc)` or `f"{exc}"` in any result, error, or return in `vidbyte/tools/builtins/bash.py`; name `type(exc).__name__` only — *source:* S017 (`SCOPED_PREFIXES` includes `vidbyte/tools/`).
- [ ] No `print()` — *source:* A008.
- [ ] Output is decoded with an explicit encoding (`"utf-8"`, `errors="replace"`) — *source:* S041 intent; EC-16.
- [ ] Imports sorted; verify with `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` filtered to the touched paths — *source:* S051; `local-ci-verification.md`.
- [ ] `vidbyte/lib/constants/bash.py` imports nothing from `vidbyte`; `vidbyte/tools/builtins/bash.py` imports only from `vidbyte.lib.*`, `vidbyte.tools.base`, `vidbyte.tools.types`; `vidbyte/agents/coding.py` imports concrete submodules, never the `vidbyte.tools.builtins` package root; A006 stays at 34 — *source:* AGENTS.md Style 3; A006; `blocking-lint-invariants.md`.
- [ ] Call chains one level deep: `CodingAgent.__init__`, `BashTool.execute`, and `_FetchedPagesView.execute` call a flat list of their own helpers; helpers call no other helper of the same class; no nested functions or lambdas — *source:* AGENTS.md Style 1.
- [ ] `CodingAgent.__init__`, `BashTool.execute`, and `_FetchedPagesView.execute` carry short plain-English comments through the body — *source:* AGENTS.md Style 2.
- [ ] Each new file stays well under 1,000 lines (targets in NFR-1); each function ≤ ~40 lines; S008 stays at 19 — *source:* AGENTS.md Style 3; S008; house style.
- [ ] No new dataclass and no new enum. If one becomes necessary, stop and report BLOCKED (budget); it would go to `vidbyte/lib/dataclasses/<domain>.py` / `vidbyte/lib/enums/<domain>.py` with an `__init__` export — *source:* AGENTS.md Placement Rules; §8.4.
- [ ] Helpers are `@staticmethod`s or methods on `BashTool` / `CodingAgent`, not module-level free functions — *source:* `class-bound-helpers.md`.
- [ ] Every new module defines `__all__`; `vidbyte/agents/__init__.py`, `vidbyte/tools/builtins/__init__.py`, and `vidbyte/__init__.py` import and list the new names exactly once — *source:* S015.
- [ ] Commit `vidbyte/__init__.py`, then run `python scripts/generate-sdk-public-api.py`, then commit `contracts/sdk-public-api.json`; `--check` passes — *source:* C016; generator header.
- [ ] `CodingAgent` overrides no `BaseAgent` method (only `__init__`) — *source:* INV-1; `vidbyte/agents/jev/agent.py:86-98`.
- [ ] `vidbyte/tools/builtins/operations/fetch.py`, `vidbyte/tools/filesystem/*`, `vidbyte/tools/builtins/code_search/*`, `vidbyte/agents/base.py`, `vidbyte/lib/dataclasses/security.py`, and `vidbyte/lib/dataclasses/filesystem.py` are byte-identical to `main` — *source:* INV-19–INV-21; NFR-1.
- [ ] No fetch key value is placed in any message, `details`, metadata, attribute, or log — *source:* INV-17; T-3.
- [ ] `ConfigurationError` is raised with a `details=` mapping, in the style of `vidbyte/agents/jev/agent.py` — *source:* repo precedent.
- [ ] No rule count rises above its `main` count, and the IMPROVED headroom on `main` (A002, S017, S025, S051) is not consumed; never run `--update-baseline`, never edit `lint/baseline.json`, never add `noqa` — *source:* `vidbyte-gates.md` lint rules; §11 baseline.
- [ ] Full gate: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` passes, then `python scripts/run_ci.py --stage package` passes with `PYTHONPATH` unset; semgrep scan in its own environment is clean — *source:* AGENTS.md; `local-ci-verification.md`.
- [ ] `REPO_MAP.md` is not edited (no new folder) — *source:* AGENTS.md Repository Map; `agents-md-map.md`.
- [ ] Nothing outside the conversation is built: no env-var key lookup, default prompt, tool renaming, Bash allow/deny lists, sandbox, persistent shell, extra tools, or config knobs — *source:* request.md §C; hard rule (scope is the conversation).

### 12.5 Non-code actions

- `vidbyte/agents/README.md` — Key Modules bullet and "## Coding Agent" section (row 8) — *source:* agentic-engineering folder README obligation; request.md §C.
- `vidbyte/tools/README.md` — `builtins/` line mentions bash (row 9) — *source:* agentic-engineering folder README obligation.
- `contracts/sdk-public-api.json` — regenerated (row 7) — *source:* C016.
- Exports: `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/tools/builtins/__init__.py` (rows 3, 5, 6) — *source:* S015; repo grain.
- `REPO_MAP.md` — no change: the map is folder-level and no folder is added — *source:* AGENTS.md; `agents-md-map.md`.
- `llms.txt`, `artifacts/file_index.md` — no change: neither is maintained per feature (`JevAgent` is absent from `llms.txt`), and AGENTS.md has no update rule for them.
- `vidbyte/lib/constants/__init__.py` — no re-export: `trace.py` and `jev.py` are imported from their own modules.
- `.env.example` — none: keys come only from parameters.
- Design doc under `docs/design/` — none: AGENTS.md has no per-feature design-doc rule; this spec is the design record.
- Lint baseline ratchet — none.
- Remote CI: dispatch `ci.yml` and `static-policy.yml` on `feat/coding-agent` once pushed (S5/S6) — *source:* code-map §1; workspace memory (CI is manual).

### 12.6 Phases and dependency order

**P1 — Bash tool** (ships: `from vidbyte.tools.builtins import BashTool` works on any `BaseAgent`): rows 1, 2, 3
**P2 — CodingAgent** (ships: `from vidbyte.agents import CodingAgent` with all seven tools and the fetch view): rows 4, 5
**P3 — Root export, contract, docs** (ships: `from vidbyte import CodingAgent`, C016 green, READMEs): rows 6, 7, 8, 9

**Dependency order:** 1 → 2 → 3; 2 → 4 → 5 → 6 → (commit) → 7. **Independent:** 8 and 9 (after 4 and 2 exist, so the text matches the code). Each phase leaves the package importable and the existing tests passing.

## §13 Test seams (facts for the test author — no tests here)

- **Framework:** pytest 8.3.5 and pytest-asyncio 1.3.0; `pyproject.toml` sets `testpaths=["tests"]`, `addopts=["--strict-config","--strict-markers"]`, `asyncio_default_fixture_loop_scope="function"`. Three styles coexist: `unittest.IsolatedAsyncioTestCase` (`tests/test_code_search_tools.py`), `unittest.TestCase` with `asyncio.run` (`tests/test_filesystem_tools.py`), and module-level `@pytest.mark.asyncio` functions with `monkeypatch` (`tests/test_web_operation_client_retry.py`).
- **Layout and naming:** flat `tests/test_<area>.py`; feature packs under `tests/features/<feature>/` (prior art `tests/features/sdk_operation_costs/`). A001 scans `tests/`, so every new test module needs the FILE/PURPOSE/… header (compliant precedents: `tests/test_restore_permission_policy.py`, `tests/test_web_operation_client_retry.py`), and must be `git add`-ed before lint.
- **Prior art to copy:**
  - `tests/test_agent_tool_loop.py` — `ToolCallingRunner` + `FakeResponse` script real OpenAI-shaped `function_call` items through `BaseAgent`'s loop; `reply.metadata["tool_call_states"]` reports `"denied"`/`"succeeded"`/`"failed"` per call; `test_agent_denies_write_tool_by_default` is the default-deny precedent.
  - `tests/test_jev_agent.py` — root-versus-package export identity and `inspect.signature` pinning.
  - `tests/test_mcp_stdio_transport.py` — real subprocesses, with a `sys.platform == "win32"` branch (line 419).
  - `tests/test_web_operation_client_retry.py` — `monkeypatch.setattr(HttpTransport, "_send_once", fake)` and patched `asyncio.sleep`; because the patch is on the class, it also covers clients `CodingAgent` builds internally from a key.
  - `tests/test_restore_permission_policy.py`, `tests/test_agent_fork_isolation.py` — `export_state`/`restore` and fork patterns.
- **Fixtures / factories:** `tests/agent_test_support.py` — `build_test_agent(*args, runner=..., agent_type=CodingAgent, **options)` constructs any `BaseAgent` subclass with offline defaults (`provider="openai"`, `model_name="gpt-4.1-mini"`) and binds the runner into `_runner_cache`; `bind_test_runner(agent, runner)` for an existing agent. `CodingAgent` accepts these options through `**kwargs`.
- **Real seams (do not mock):** real temporary directories for `root_dir`; real `bash` subprocesses on Linux (CI ubuntu-latest has bash); `BaseAgent`/`AgentRuntime` permission checks and `ToolsFormatter`. `tests/agent_test_support.py` forbids monkeypatching `BaseAgent.__init__` and making provider calls. Contract seams this spec fixes: `vidbyte/tools/builtins/bash.py` imports `BASH_TIMEOUT_SECONDS`, `BASH_MAX_OUTPUT_BYTES`, `BASH_READ_CHUNK_BYTES` by name into its module namespace, so patching `vidbyte.tools.builtins.bash.<NAME>` changes the bound a call uses; the executable is resolved in `BashTool.__init__` from `shutil.which` and `sys.platform` as read at construction time. A `CodingAgent`'s WebFetch tool is `agent.tools.all()[6]`; for a keyed provider it is a view whose public `wrapped_tool` property returns the priced tool.
- **Platform facts:** the developer machine is Windows 11 with Git for Windows (`C:\Program Files\Git\bin\bash.exe`) and a failing WSL launcher first on `PATH`; CI is Linux only. Process-group behavior (`os.killpg`, `start_new_session`) exists only on POSIX. Known CI flake: `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` on Python 3.11.
- **Per-area config:** none beyond `pyproject.toml`.
- **Run one file:** `PYTHONPATH=$(pwd) python -m pytest -q tests/<file>.py` · **Run all:** `PYTHONPATH=$(pwd) python -m pytest`

## §14 Agent boundaries
- **Always:** work only inside the worktree; build exactly §12.3 in §12.6 order; `git add` new files before lint; run the touched lint rules (`--rule A001`, `A002`, `A006`, `A007`, `S015`, `S016`, `S017`, `S019`, `S025`, `S039`, `S045`, `S052`, `S055`, `S062`, `C016`) and then `python lint/run.py` after each phase; run the new tests after each work item; run the full gate (§11) before pushing; commit `vidbyte/__init__.py` before regenerating the contract; cite `W-`/`FR-`/`D-` IDs in commit messages.
- **Ask first (stop and report BLOCKED):** touching any file not in §12.3; exceeding §8.4 (a fourth new file, a new enum or dataclass, a new dependency); editing `fetch.py`, any filesystem or code-search tool, `BaseAgent`, `PermissionPolicy`, or `FileSystemToolConfig`; changing a `BASH_*` value; adding any public name beyond `CodingAgent` and `BashTool`; modifying any test file, including the ones S2 wrote.
- **Never:** commit real API keys or secrets (examples use placeholders like `fc-your-key`); delete, skip, xfail, or weaken a test; raise a lint baseline, run `--update-baseline`, or add a suppression or `noqa`; use `shell=True`, `create_subprocess_shell`, `os.system`, or `SandboxTransport`; read environment variables for keys; add a default system prompt, tool renaming, Bash allow/deny lists, a persistent shell, or extra tools; read anything under `docs/` except `docs/spec/coding-agent/`; push to `main`.

## §15 Assumptions and open questions
**Assumptions** (stand unless the user corrects them):
- **A-1** — "WebFetch" means the model can read the fetched page, as with Claude Code's WebFetch, so the keyed summary-only output must be extended for `CodingAgent` (D-5). — *If wrong:* delete `_FetchedPagesView` and pass the bare keyed tool; FR-6, AC-7, INV-16 go away.
- **A-2** — Windows users have Git for Windows installed in its standard layout (`<G>\cmd\git.exe` beside `<G>\bin\bash.exe`), as on the user's machine. — *If wrong:* Bash returns `bash_not_found` there; D-13 needs another lookup.
- **A-3** — Commands may inherit the developer's full environment, secrets included. — *If wrong:* answer Q-3 yes; Bash uses `build_child_env`.
- **A-4** — 600 seconds and 1,000,000 bytes are acceptable fixed bounds. — *If wrong:* change the constants (one file) or answer Q-2.
- **A-5** — `read_lines` is an acceptable Read (whole file without a range). — *If wrong:* swap in `ReadTextTool`; tool name changes to `read_text`.
- **A-6** — `root_dir` is the right name and should be required. — *If wrong:* rename across §4/§8.5/§12 or add a default (reopens D-8).
- **A-7** — A finished command with a non-zero exit code is a successful tool call (D-12). — *If wrong:* return `ToolResult.error` for non-zero exits.
- **A-8** — Four key parameters (D-3) are preferred over a provider enum plus one key. — *If wrong:* replace them with `fetch_provider` + `fetch_api_key` and add one enum in `vidbyte/lib/enums/`.

**Open questions** (max 5 blocking):
| ID | Question | Blocking? | Default if unanswered |
|---|---|---|---|
| Q-1 | Edit tool: `ReplaceTextTool` (exact-once replace, shares the file config) or `PatchTool` (search-block patch returning a diff)? | non-blocking | `ReplaceTextTool` |
| Q-2 | Add a configurable Bash timeout or output cap (constructor parameter or model-facing `timeout`)? | non-blocking | No — fixed constants; agent-wide `ToolSettings.tool_timeout_seconds` remains |
| Q-3 | Run Bash with an allow-listed environment (`build_child_env`) so commands cannot read the developer's secrets? | non-blocking | No — inherit the environment |
| Q-4 | Give `CodingAgent` a default model-visible output cap (`ToolSettings.result_max_chars`) to protect the context window? | non-blocking | No — caller configures `agent_loop_settings` |
| Q-5 | Add `CodingAgent.restore(state, root_dir=..., <key>=...)` so a restore returns a `CodingAgent`? | non-blocking | No — use `BaseAgent.restore(state, tools=...)` |

## §16 Review log
| Round | ID | Severity | Section | Finding (one line) | Disposition | Change made / reason |
|---|---|---|---|---|---|---|
| — | — | — | — | No review yet. | — | — |

## §17 Revision history
| Revision | Date | Stage | Summary |
|---|---|---|---|
| r1 | 2026-10-10 | S1 spec | Initial spec |
