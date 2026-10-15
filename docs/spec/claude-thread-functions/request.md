---
slug: claude-thread-functions
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-15 18:13
flags: none (update existing PR #1044 in place on branch feat/claude-host; stacked on PR #1036, branch feat/native-grok-opencode-meta-hosts)
---

# Request: reshape PR #1044 (ClaudeHost) into Claude Code thread functions (`run_claude_thread`, `continue_claude_thread`, `fork_claude_thread`) shaped like PR #1036

This run updates an existing pull request in place: https://github.com/cerredz/Vidbyte-SDK/pull/1044, branch `feat/claude-host`, currently based on `main`. The PR was built by an earlier pipeline run (slug `claude-host`, files under `docs/spec/claude-host/`). The repository owner (GitHub login `cerredz`, the user) looked at it next to PR #1036 (https://github.com/cerredz/Vidbyte-SDK/pull/1036, branch `feat/native-grok-opencode-meta-hosts`) and asked for #1044 to take #1036's shape.

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening message):

````text
Take a look at pr #1036 for the vidbyte-sdk/, then take a look at pr #1044, i wanted 1044 to moreso look  like 1036 in the sense of implementing the functions that we can actually use in the code, take a lok at the prs, do you understand what i mean by this?
````

**Prompt 2** (the `/spec-pipeline` invocation; its whole argument string, sent in reply to the assistant's proposal quoted in §C):

````text
great, implement this change and update the pr
````

## B. Handoff block and decision ledger (verbatim, if present)

None in this conversation. The earlier run's request (`docs/spec/claude-host/request.md`, on this branch) holds the original "CodexHost and ClaudeHost" design prompts and a decision ledger ("one host class per harness, spawn returns a handle", "one tool per function"). That ledger is **superseded** for this PR wherever it conflicts with §A and §C here. PR #1036's own rework request (`docs/spec/harness-thread-functions/request.md` on branch `feat/native-grok-opencode-meta-hosts`) recorded the same supersession for Grok, opencode and Muse; its §A Prompt 3 is the owner's statement of the shape they want, quoted in §C below.

## C. Structured conversation notes

### The assistant's proposal that the user accepted with "great" (verbatim)

The assistant read both PRs and replied as follows. Prompt 2 ("great, implement this change and update the pr") accepts this proposal. Point 3 at the end was a question the user did not answer; see "Open questions".

````markdown
Yes, I see what you mean. #1036 became a set of plain functions that you `await` and get an answer back from. #1044 is still a framework you have to manage: a host object, handles, live sessions and agent tools. You want #1044 cut down to the same kind of functions for Claude Code.

## Where the two PRs stand

| | #1036 (after its rework) | #1044 (as it is) |
|---|---|---|
| What you call | `await run_grok_thread(prompt, api_key=..., workspace=..., skills=..., config=...)` | `async with ClaudeHost() as host:` → `spawn_claude_session(request)` → handle → `wait_claude_turn(handle)` |
| Public surface | 3 functions per harness (`run_` / `continue_` / `fork_<harness>_thread`) | 15 methods: readiness, models, rate limits, spawn, continue, fork, launch, wait, result, steer, interrupt, usage, 3 history reads |
| API key | The caller passes it; it only goes into the child process's environment | None. It uses whatever `claude` login is on the machine |
| What comes back | `NativeThreadResult(thread_id, text)` or one `NativeThreadError` | Handles, turn snapshots, usage snapshots, `ClaudeOperationError` |
| Agent tools | All 43 deleted | 15 `BaseTool`s plus a `ClaudeTools` toolset |
| Size (SDK code) | Grok is 305 lines, on shared helper code (`CliRunner`, `CliArgv`, `NativeErrorFactory`, `NativeLauncher`) | about 4,070 lines, plus a new `claude-agent-sdk` extra |

#1044 was built from the same early "CodexHost and ClaudeHost" design that #1036's rework set aside. That design's "one host class per harness, spawn returns a handle" and "one tool per function" choices are exactly what #1044 still has.

## What #1044 would become

```python
from vidbyte.harnesses.native import run_claude_thread, continue_claude_thread, fork_claude_thread

first  = await run_claude_thread("Add a --verbose flag.", api_key=key, workspace=repo, skills=[...])
again  = await continue_claude_thread(first.thread_id, "Now add a test.", api_key=key, workspace=repo)
branch = await fork_claude_thread(first.thread_id, "Try it another way.", api_key=key, workspace=repo)
```

- **Each call runs `claude` once, headless:** `claude -p --output-format json`. A continue adds `--resume <id>`, and a fork adds `--resume <id> --fork-session`. The JSON output already includes `session_id` and `result`, which map straight onto `NativeThreadResult`.
- **The key goes only in the child's `ANTHROPIC_API_KEY`.** As far as I know, Claude Code's docs say `-p` mode always uses that key when it is set, even if a `claude login` exists, so the caller's key pays. That needs checking against the real CLI.
- **Skills and sessions would live in a private `CLAUDE_CONFIG_DIR`** under `~/.vidbyte/`, one per workspace. This copies how Grok gets a private `GROK_HOME`. Claude Code keeps its session files in that folder, so a continue or fork finds the thread. I still need to check this against the real CLI.
- **It plugs into #1036's shared code:** the `claude.*` failure codes, one `NativeThreadError`, a `ClaudeFlag` enum, constants in `lib/constants/native_threads.py`, and a small `ClaudeThreadConfig` like `GrokThreadConfig`.
- **Deleted:** `ClaudeHost`, `ClaudeLiveSession`, handles, spawn, wait, steer, interrupt, usage, rate limits, `launch_claude_subagents`, the history reads, the readiness probe, all 15 tools and the toolset. If we use the CLI, the `claude-agent-sdk` extra goes too. I'd expect roughly 300 lines instead of about 4,070.

One more fact: #1044's `fork_claude_session` only copies the session and returns an id. In #1036, a fork also runs a prompt on the copy. The Claude version would match #1036.

## Before I reshape it

1. **Stack it on #1036.** Both PRs create `vidbyte/harnesses/native/__init__.py` with different contents, so #1044 has to build on #1036's branch. #1036's Graphite merge failed today with conflicts, so that needs sorting out first.
2. **Run `claude` directly, not through `claude-agent-sdk` (my recommendation).** It means one runner and one error path for all four harnesses, and no new dependency. The cost: the in-process MCP bridge that gives Claude vidbyte's `BaseTool`s goes away. You didn't ask for that bridge.
3. **Your unresolved comment on #1036** (`grok/threads.py:56`): "all inputs for these should input params into dataclass… same for all functions." Right now #1036 takes loose arguments and builds a `NativeThreadRequest` inside the function. Do you want the public signature itself to take a validated record, like `run_claude_thread(ClaudeThreadRequest(...))`? Whatever you choose should apply to all four harnesses.

#1055 (`CodexHost`, draft, +18,523 lines) has the same host-plus-tools shape as #1044, so it would need the same rework.

Should I go ahead and reshape #1044 this way, stacked on #1036? And how do you want to handle point 3?
````

### The owner's statement of the shape, from PR #1036's rework (verbatim, `docs/spec/harness-thread-functions/request.md` §A Prompts 3 and 4 on branch `feat/native-grok-opencode-meta-hosts`)

````text
there seems to be some disconnect with the pr and what I wanted the pr to do. i wanted the pr to simply do the following: the user providers their api key, and then we simply  create functions that run the already existing cli/sdk code of open  source harensses (ex: run_grok_thread(api key, skills, prompt, config), run_opencode_thread(params), fork_grok_thread(grok_thread_id), then even complex functions like run_grok_thread_verify_with_opencode(params) etc (dont worry about the complex functions for now). And then each function has the parameters needed for the function and then the api key that the user is providing. Does the pr do this right now?
````

````text
I dont literally want the things that I said, but I want you to figure out the general shape of what I said and how to implement optimally (only thing I definately want is the actual function naming the way i said). Can you figure this out,  update the pr, and also resolve the comments that I left
````

### The owner's open review comment on PR #1036 (verbatim; thread unresolved at invocation time)

Comment 4288576487 and its reply 4288578540, both by `cerredz`, 2026-10-15 21:42 UTC, on `vidbyte/harnesses/native/grok/threads.py` line 56 at #1036 commit f77330d9 (the reworked `GrokThreads.run_grok_thread` signature, which takes `prompt` plus keyword arguments `api_key`, `workspace`, `model`, `skills`, `config` and builds a validated `NativeThreadRequest` inside `GrokThreads._call`):

````text
all inputs for these should input params into dataclass, and dataclass should have strict input validation 
````

````text
same for all functions for this repo 
````

### Key decisions
- KD-1 — PR #1044's public surface becomes three plain async functions, `run_claude_thread`, `continue_claude_thread` and `fork_claude_thread`, exported from `vidbyte.harnesses.native` beside #1036's nine, never from root `vidbyte`. Reason: Prompt 1 ("implementing the functions that we can actually use in the code", "look like 1036"), accepted proposal.
- KD-2 — Names follow #1036's `<verb>_<harness>_thread` pattern exactly. The owner said on #1036 that the function naming is the one thing they definitely want.
- KD-3 — Each call runs the user's installed `claude` command-line tool once, headless (`claude -p --output-format json`; continue adds `--resume <id>`; fork adds `--resume <id> --fork-session`), through #1036's `CliRunner`, and returns a `NativeThreadResult` (harness, thread id, final text). Not through `claude-agent-sdk`. Reason: accepted proposal point 2 (one runner and one error path for all four harnesses, no new dependency).
- KD-4 — The caller passes `api_key`; it reaches Claude Code only through the child process's environment (`ANTHROPIC_API_KEY`, to be verified), never on the command line, in a file, in `os.environ`, or in an error message. A stored `claude` login on the machine must not be what pays. Reason: #1036's contract ("the user providers their api key"), accepted proposal.
- KD-5 — Fork means "copy the thread, run the prompt on the copy, return the new id", like #1036, not #1044's copy-only `fork_claude_session`. Reason: accepted proposal.
- KD-6 — Reuse #1036's shared code instead of a Claude-only stack: `NativeThreadResult`, `NativeThreadError`, `NativeErrorFactory`, `NativeLauncher`, `NativeSkillFolders`, `CliArgv`, `CliRunner`, the enums in `vidbyte/lib/enums/native_threads.py`, the constants in `vidbyte/lib/constants/native_threads.py`, `FailureCode` members named `claude.<problem>`, a `ClaudeFlag` enum and a small `ClaudeThreadConfig` record shaped like `GrokThreadConfig`. Reason: accepted proposal; #1036's resolved review comments ("wrong file location", "define enums for flags/hardcoded strings", "error messages need to be in much more detail") apply to this harness too.
- KD-7 — Delete what the shape does not use: `ClaudeHost`, `ClaudeLiveSession`, handles, spawn, wait, result, steer, interrupt, usage, rate limits, `launch_claude_subagents`, the three history reads, the readiness and model probes, the in-process MCP tool server, all 15 `BaseTool`s and the `ClaudeTools` toolset, the `claude = ["claude-agent-sdk…"]` optional extra in `pyproject.toml`, the old feature test pack `tests/features/claude_host/`, and the superseded design record `docs/spec/claude-host/`. Reason: accepted proposal ("Deleted: …"); #1036 deleted its own superseded host classes, tools and spec folder the same way.
- KD-8 — Stack on #1036: merge `origin/feat/native-grok-opencode-meta-hosts` into `feat/claude-host` (merge, never rebase: the branch is pushed and force-push is forbidden), and retarget PR #1044's base branch to `feat/native-grok-opencode-meta-hosts` so its diff shows only the Claude change. Reason: accepted proposal point 1 (both PRs create `vidbyte/harnesses/native/__init__.py` with different contents).
- KD-9 — Update PR #1044 in place on branch `feat/claude-host`. Reason: Prompt 2 "update the pr".

### Rejected alternatives
- Keep `ClaudeHost` (async context manager, handles, live sessions) — rejected by Prompt 1 and the accepted proposal; it is the shape #1036's owner rejected for Grok, opencode and Muse.
- Keep one agent tool per function (`ClaudeTools`) — rejected; #1036 deleted all 43 of its tools, and the owner asked for functions usable in code.
- Drive Claude Code through `claude-agent-sdk` — rejected by accepted proposal point 2. Its only unique benefit here was the in-process MCP bridge for vidbyte `BaseTool`s, which nobody asked for.
- A Claude-only error type (`ClaudeOperationError`) and a Claude-only constants/enums/dataclass set parallel to #1036's — rejected; one `NativeThreadError` and #1036's shared modules.

### Constraints and assumptions
- The user's installed `claude` executable is what runs. On Windows, #1036's `NativeLauncher` refuses `.cmd`/`.bat` launchers; #1044's probe likewise accepted only a native `claude.exe`. (Which Claude Code version is installed on this machine and where is a vendor fact to verify.)
- Vendor behavior the proposal stated "as far as I know" and flagged "needs checking against the real CLI": that `-p` mode uses `ANTHROPIC_API_KEY` over a stored login; that `CLAUDE_CONFIG_DIR` relocates both skills and session files; the exact JSON fields of `--output-format json`; that `--resume <id> --fork-session` returns a new session id. These must be verified with free probes (help text, version, a run with an invalid key, an unknown session id) before the spec relies on them. No probe may spend a real key or the user's subscription.
- Every input is validated before any process starts or any file is written, as in #1036.
- #1036 is still open (owner merge via Graphite failed on conflicts with main on 2026-10-15 21:46 UTC; its branch has since merged main again, head 5c08c35e). This PR builds on whatever #1036's branch head is when the S0 merge runs.
- A separate pipeline run (`native-thread-compose`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`) is building composition functions stacked on #1036 at the same time. It will touch the same shared modules (`vidbyte/harnesses/native/__init__.py`, the native-thread enums, constants and failure codes). This run does not coordinate with it; conflicts between the two stacked PRs are resolved when either merges.

### Clarifications and answers
- Q (assistant, proposal point 1): stack on #1036? — A: "great, implement this change and update the pr" (accepted).
- Q (assistant, proposal point 2): run `claude` directly rather than `claude-agent-sdk`? — A: accepted, as above.
- Q (assistant, proposal point 3): should the public signature itself take a validated record, e.g. `run_claude_thread(ClaudeThreadRequest(...))`? — A: not answered. See "Open questions".

### Terminology
- Thread — one Claude Code conversation (Claude Code calls it a session); its id is Claude Code's `session_id`. The SDK's public word is "thread", as in #1036.
- Harness — a vendor's own agent CLI (Grok Build, opencode, Muse Code, and now Claude Code).
- Run / continue / fork — start a new thread with a prompt; run one more prompt on an existing thread; copy an existing thread into a new one and run a prompt on the copy.
- "#1036's shape" — the public surface and contracts described in #1036's PR body and `docs/spec/harness-thread-functions/spec.md` (r4) on branch `feat/native-grok-opencode-meta-hosts`.

### Implementation hints
- #1036's Grok harness is the model to copy: `vidbyte/harnesses/native/grok/__init__.py` (binds module names to `GrokThreads` static methods), `grok/threads.py` (`GrokThreads` with the three functions and one guarded `_call`; `GrokThreadRun.execute` as the narrated main function), `grok/wire.py` (`GrokWire.read` turns the one JSON answer into the result or a failure code). Grok's private `GROK_HOME` under `~/.vidbyte/grok-homes/<hash of workspace>` is the precedent for a private Claude config folder.
- #1036's shared modules: `vidbyte/harnesses/native/hostkit/` (errors, launcher, skills), `vidbyte/lib/process/` (`CliArgv`, `CliRunner`, `ProcessStopper`), `vidbyte/lib/dataclasses/native_threads.py`, `vidbyte/lib/dataclasses/process.py`, `vidbyte/lib/dataclasses/validation.py`, `vidbyte/lib/enums/native_threads.py`, `vidbyte/lib/enums/process.py`, `vidbyte/lib/constants/native_threads.py`, `vidbyte/lib/errors/base.py` (`NativeThreadError`), `vidbyte/lib/enums/failure.py`.
- #1036's test pack `tests/features/harness_threads/` (a scripted stand-in `fake_harness.py` runs as a real child process; `conftest.py::check_error` defines the error-message order; a static-policy test checks with `ast` that no module under `vidbyte/harnesses/native/` holds constants or hardcoded strings; a surface test pins exported names). Claude's tests follow the same pattern.
- #1044's existing code holds Claude-specific facts worth reading before deleting: `vidbyte/harnesses/native/claude/probe.py` (CLI lookup locations, the native-`claude.exe`-only rule on Windows, version floor `CLAUDE_MIN_CLI_VERSION = "2.1.296"`), `options.py` (how request fields map to CLI flags and env), `vidbyte/lib/constants/claude.py`, `vidbyte/lib/enums/claude.py`.
- `vidbyte/harnesses/native/__init__.py` exists on both branches with different contents; #1036's version (re-exports of the nine functions) is the one to build on.
- PR #1055 (`CodexHost`, draft) shares #1044's old `vidbyte/harnesses/native/__init__.py` "marker" contract. It is not part of this run.

### Open questions
- OQ-1 — Proposal point 3, unanswered: should `run_claude_thread` / `continue_claude_thread` / `fork_claude_thread` take one validated dataclass as their public input (as the owner's open #1036 comment "all inputs for these should input params into dataclass … same for all functions for this repo" may mean), or match #1036's current signature (`prompt` plus keyword arguments, validated into `NativeThreadRequest` before anything starts)? The proposal said "Whatever you choose should apply to all four harnesses." **Orchestrator default:** match #1036's current signature exactly, so all twelve functions in `vidbyte.harnesses.native` share one shape; changing the signature is one cross-harness decision for #1036's open thread and is applied to all four harnesses together. The spec carries this as a `Q-n` with that default so the owner can interrupt.
- OQ-2 — Exactly how the caller's key, the skills and the session store reach Claude Code (env var, private `CLAUDE_CONFIG_DIR`, `--bare`, `--plugin-dir`, `--setting-sources`, `--settings`), and how to keep a workspace's own `.claude/settings.json` (env, `apiKeyHelper`, hooks) from overriding the key or running code with it — resolved from verified vendor facts by the spec author.
- OQ-3 — Which Claude Code settings belong on `ClaudeThreadConfig` (the proposal named only "a small `ClaudeThreadConfig` like `GrokThreadConfig`": e.g. permission mode, timeout, `claude_command`). The spec author picks the smallest set that mirrors `GrokThreadConfig`, and lists anything else as an optional `Q-n` (default: not built).

## D. Weighted words

- "the functions that we can actually use in the code" — Prompt 1
- "only thing I definately want is the actual function naming the way i said" — #1036 owner prompt (quoted in §C)
- "all inputs for these should input params into dataclass, and dataclass should have strict input validation" — #1036 owner comment (quoted in §C)
- "same for all functions for this repo" — #1036 owner comment (quoted in §C)
- "The key goes only in the child's `ANTHROPIC_API_KEY`" — accepted proposal
- "Each call runs `claude` once, headless" — accepted proposal
- "Whatever you choose should apply to all four harnesses." — accepted proposal
