---
slug: claude-host
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-12 21:41
flags: none
---

# Request: ClaudeHost: small atomic Claude Code functions with one agent tool per function

## A. Every user prompt in this conversation, verbatim and in order

_Local commands the user typed between prompts (`/model`, `/rename`, `/effort`) were not requests and are omitted._

**Prompt 1** (first message of the conversation, 2026-10-12 19:43 UTC):
`````text
few questions for the CodexHarnessAgent, future ClaudeHarnessAgent, and vidbyte-cli/ repo. the whole point of these harnesses was to translate the vidbyte-sdk/ custom abstractions into a language that codex and claude can use. I was using these agents  (future claude one) with the intention of building agents out of them inside of the vidbyte-cli/. I reecently came to the conclusion though that for some of the agents that we are building I feel like I dont really need them, and instead am thinking of coming up with a "vocabulary" for "launching a codex agent", forking a codex agent, launching a codex agent with x tools, launch a claude sesstion, etc. And coming up with very simple agents to be built inside of the vidbyte-cli/ like this. Few reasons, 1) we dont actually need alot of vidbyte-sdk/ abstractions yet, just want to pump out simple agents and 2) value right now in agents is in the custom tools, custom output connectors, etc and 3) feel like there is alot of edge in something like "launch a codex thread and then launch a claude thread as adversarial review, etc" 4) WE can create these simple terminal commands for all coding harnesses. All of a sudden, "launching a codex thread with 3 codex subagents, 4 claude subagents, and then using a grok thread to merge the results is very easy,  it is only a few functions that we create, and 5) we could even package all of these into tools that other agents can use. we can even create like an "agent terminal toolset mcp" that packages all of these types of tools/functions


i feel like a big point for the vidbytte-cli/ is to have agents intergrated into their coding harnesses that they already use, not really rely on vidbyte-sdk/, which is the reason for this sudden change. Anyways, what do you think of this idea, list the pros and cons, and if you think that it is a good idea then can you list out how  we would actually implement some of the basic functions/capability (launching a codex thread, claude threads, custom controls), and then finally list out some   more functions that we can create
`````

**Prompt 2** (after the assistant's first design reply, 2026-10-12 20:54 UTC):
`````text
great, lets refine the implementation a little bit, i think that i want to add this abstraction inside of the vidbyte/harnesses folder of the repo and connect each individual function to the vidbyte/tools folder as well to give agents the functionalties in tools and not have to rely on them actually trying to do these things during their agent run. 


then, i want to create a function like "spawn_codex_thread(params  (model, reasoning, prompt, output-tokens, etc))"  the function should have all the params needed to launch a codex thread according to their sdk and also return semantic error  messages if something goes wrong, each funciton shoulllld make sure to handle errors. Then some more examples functions we can create a track_codex_thread_usage(), fork_codex_thread(), launch_codex_subagents(number, prompts, etc). I want to create all types of small, atomic, rueusable, and helper functions for interacting with codex in this class, and then apply this same principle/philosophy of functions to other open source harnesses  (claude code, grok build, opencode, etc).

Can you help think of a checklist of other functions that we can implement with codex usiing what is possible with their open source sdk (ex: claude code has a "cloud provider" subcommand, we could create like a claude_thread_cloud() function, and then error handling would be something like make sure user is signed in).

can you help come up with some more codex functions that we can create, all that you can think of? before implementation
`````

**Prompt 3** (after design reply R2 (see §E), 2026-10-12 21:17 UTC):
`````text
yes the folder change the things that you pushed back on makes sense, one thing I do want you to do before we start implementing is can you recommend the same "full implementation subspace of functions" for a similiar ClaudeHost class that implements everything that we can do with claude code. Then,  return to me all of the functions for the ClaudeHost and CodexHost, expecting a big list in this request.
`````

**Prompt 4** (the `/spec-pipeline` invocation arguments, after design reply R3 (see §E), 2026-10-12 21:41 UTC):
`````text
great, using the spec-pipeline skill file do you think that you can implement the Codexhost and ClaudeHost functionality in the vidbyte-sdk/ in parallel in 2 seperate prs. Coordinate 2 sets of subagents that use the skill file to develope the 2 features in parallel
`````

## B. Handoff block and decision ledger (verbatim, if present)

No `## HANDOFF` block exists. The latest Re-entry card, which closes design reply R3, is reproduced verbatim below. Prompt 4 is the user's reply to it; §C "Answers to R3 'Needs you'" records what that reply settled.

`````markdown
**Re-entry · harness-thread vocabulary**

Decided:
- **Where it lives:** in the SDK. Functions go in `vidbyte/harnesses/native/<host>/`, one tool per function in `vidbyte/tools/builtins/<host>/`, bundled in `toolsets/<host>.py`, and exposed over MCP through `mcp_server/`. Both hosts use their official SDK (openai-codex, claude-agent-sdk); features that only exist in a CLI run the CLI.
- **One host class per harness:** each owns its live processes and handles. Spawn returns a handle immediately, settings are spawn-request fields, and the existing Codex settings are reused.
- **Shared vocabulary:** shared verbs for cross-harness code, plus one `<host>.<problem>` error vocabulary with next steps. Tools return error results instead of raising.
- **Budgets:** Codex uses a goal budget plus our interrupt; Claude uses its built-in `max_budget_usd`, `max_turns`, `task_budget` and thinking budget.
- **⚑ group:** the TypeScript-only Claude controls are reachable from Python only through a private method (decision pending, below).

Open:
- The verify items above.
- The policy on plan-backed (subscription) usage in a paid product, for both OpenAI and Anthropic.

Needs you:
1. Should the ⚑ functions wait until the Python SDK exposes them? Building them now means using the private call under an exact pin plus contract tests. Default: leave them out of the first PRs.
2. Should PR 1 contain only CodexHost's ★ set, with PR 2 adding ClaudeHost's ★ set and extracting the shared pieces (error envelope, tool base, handle registry)? Default: yes.
3. Should both hosts default to the user's installed binary (`codex_bin` / `cli_path`, with a minimum-version check) instead of the SDK's bundled one? Default: yes.

*Reply "go" to accept all defaults.*

Next: on "go", I write the HANDOFF for PR 1: CodexHost's 14 ★ functions, their tools, the error mapper and contract tests.
`````

## C. Structured conversation notes

_Written by the orchestrator. This run builds **PR B: ClaudeHost** (slug `claude-host`, branch `feat/claude-host`). A second pipeline builds **PR A: CodexHost** (slug `codex-host`, branch `feat/codex-host`, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host`) at the same time from the same base commit. "R2" and "R3" below are the assistant's two design replies that the user accepted, reproduced verbatim in §E. R3 supersedes R2 wherever they differ. R2 is Codex-centric, but its reasoning on placement, host lifetime, non-blocking spawn and errors applies equally to Claude, and R3 states how ClaudeHost differs._

### Key decisions
- **This PR builds ClaudeHost's ★ set, not the full catalog.** R3's legend says "★ = first PR for that host". Prompt 4 asks for "the Codexhost and ClaudeHost functionality … in 2 seperate prs", one PR per host. So the scope is:
  - the 14 ★ rows of R3 "ClaudeHost: full list" (15 functions, because one row holds both `wait_claude_turn` and `get_claude_turn_result`);
  - the `ClaudeSpawnRequest` fields from R3;
  - the `ClaudeHost` class;
  - the error mapper (`claude.<problem>` codes with next steps);
  - one agent tool per ★ function and a toolset bundling them;
  - contract tests.
  Unstarred functions are later PRs and are not built here.
- **The ★ functions, verbatim from R3** (signature, then what it wraps in claude-agent-sdk, then the tool permission):
  - `check_claude_ready()`: CLI found, minimum version, signed in. Wraps `CLINotFoundError`, `initialize` → `claude_code_version`, `account`. R.
  - `list_claude_models()`: effort levels, adaptive thinking, fast/auto mode support per model. Wraps `initialize` → `models`. R.
  - `get_claude_rate_limits()`: five-hour, seven-day and per-model windows, utilization, reset time, overage. Wraps the latest `RateLimitEvent`. R. R3 also lists "⚑ `get_usage`" as a second source. ⚑ is excluded (Q1 default, below), so this PR reads only the latest `RateLimitEvent` this host has seen.
  - `spawn_claude_session(request)`. Wraps `ClaudeSDKClient(options)` → `connect()` + `query()`. W.
  - `continue_claude_session(session_id, prompt)`. Wraps `resume`. W.
  - `fork_claude_session(session_id, up_to_message_id, title)`. Wraps `fork_session()` (a file copy), or `resume` + `fork_session=True`. W.
  - `list_claude_sessions(directory, limit, offset, include_worktrees)`: summary, title, first prompt, branch, tag, timestamps. Wraps `list_sessions()`. R.
  - `get_claude_session_info(session_id)`. Wraps `get_session_info()`. R.
  - `get_claude_session_messages(session_id, limit, offset)`. Wraps `get_session_messages()`. R.
  - `wait_claude_turn(handle, timeout)` and `get_claude_turn_result(handle)`. Wrap `receive_response()` → `ResultMessage`. R.
  - `steer_claude_session(handle, message)`, after verifying whether a mid-turn message queues or interrupts. Wraps `client.query()` (TS `streamInput()`). W.
  - `interrupt_claude_turn(handle)`. Wraps `interrupt()`. W.
  - `track_claude_session_usage(handle)`: input, output, cache-read and cache-write tokens, web searches, dollars per model. Wraps `ResultMessage.usage`, `.model_usage`, `.total_cost_usd`, `TaskUsage`. R.
  - `launch_claude_subagents(prompts, request, limit)`: Vidbyte runs exactly N sessions or forks. Wraps spawn / fork × N. W.
- **`ClaudeSpawnRequest` fields, verbatim from R3:**
  - Input: `prompt` (text, or content blocks with images), `files` (`--file`), `cwd`, `add_dirs`.
  - Model: `model`, `fallback_model` (ordered list), `effort` (low to max), `thinking` (adaptive, a token budget, or off; display summarized or omitted), `betas` (API-key logins only).
  - Instructions: `system_prompt` (replace it, or keep the `claude_code` preset and append, or load from a file), `exclude_dynamic_system_prompt_sections`, `system_prompt_snapshot`.
  - Tools and permissions:
    - `builtin_tools`, plus `allowed_tools` and `disallowed_tools` (patterns like `Bash(git *)`);
    - `permission_mode` (default, acceptEdits, plan, bypassPermissions, dontAsk, auto), `permission_prompts` (`host` or `none`), `restricted`;
    - `sandbox` (on/off, auto-allow Bash, excluded commands, network allow/deny domains);
    - `can_use_tool`, `hooks`.
  - Extensions:
    - `tools` (Vidbyte `BaseTool`s, served through an in-process MCP server), `mcp_servers`, `strict_mcp_config`;
    - `skills`, `plugins` (folder, zip or URL);
    - `agents` (`AgentDefinition`: description, prompt, tools, disallowedTools, model, skills, memory, mcpServers, initialPrompt, maxTurns, background, effort, permissionMode);
    - `main_agent` (`--agent`).
  - Which config loads: `setting_sources` (user, project, local), `settings`, `bare`, `safe_mode`.
  - Budgets: `max_turns`, `max_budget_usd`, `task_budget`, `autocompact`, `max_output_tokens` (an environment variable; verify the name).
  - Session: `session_id` (choose it up front), `name`, `resume`, `continue_conversation`, `fork_session`, `resume_session_at`, `resume_drops_turn`, `persist_session`, `enable_file_checkpointing`, `session_store`, `worktree`.
  - Output: `output_schema` (passed as `output_format`), `include_partial_messages`, `include_hook_events`, `forward_subagent_text`, `prompt_suggestions`.
  - Process: `cli_path` (default: the user's installed `claude`), `env`, `user`, `load_timeout_ms`, `timeout_seconds`.
  - Some of these fields map only to CLI flags or to `extra_args` in claude-agent-sdk 0.2.165 rather than to a typed `ClaudeAgentOptions` field. The spec author must state the mapping for each field. Fields the Python SDK cannot carry without ⚑ private calls are listed as limitations, not built.
- **Location (user decision, Prompt 2; accepted in Prompt 3):** the abstraction lives in the SDK, under `vidbyte/harnesses/`. `vidbyte/harnesses/` already holds the `Harness` run envelope (YAML-configured `run()`, registry, trajectory datasets), so the host code goes in the subpackage `vidbyte/harnesses/native/claude/`.
- **One tool per function (user decision, Prompt 2):** "connect each individual function to the vidbyte/tools folder as well to give agents the functionalties in tools".
  - Tools go in `vidbyte/tools/builtins/claude/`. Copy the `vidbyte/tools/builtins/sessions/` layout: a `_base.py` holding shared state, one file per group of tools, and a `descriptions.py`.
  - The tools are bundled as `vidbyte/tools/toolsets/claude.py`, the way `toolsets/coding.py` bundles `CodingAgentTools`.
  - The "agent terminal toolset mcp" (Prompt 1) is reached through the existing `vidbyte/mcp_server/`, which already exposes SDK tools. Add code there only if it cannot already serve a toolset.
- **Official SDK:** Claude Code is reached through the Python `claude-agent-sdk`. That package is new to vidbyte-sdk, so it comes in through a new optional extra, `vidbyte-sdk[claude]`, in `pyproject.toml`. Choosing the official SDK pre-authorizes this dependency. Features that exist only in the `claude` CLI shell out to the CLI, but no ★ function needs one beyond what R3 names for readiness.
- **One host class, with Claude's process model (R3 "How ClaudeHost differs from CodexHost"):** `ClaudeHost` is an async context manager that owns the live `ClaudeSDKClient`s it started.
  - Claude runs one `claude` CLI process per live session, so fanning out 7 sessions means 7 processes.
  - Session history needs no process. `list_sessions`, `get_session_info`, `get_session_messages` and `fork_session` read and write session files directly, so the ★ history functions and fork are offline and instant.
  - Live functions (steer, interrupt, wait, track usage) only work through the `ClaudeHost` that started the session.
  - Tools hold one `ClaudeHost` per agent, the same way `_SessionBuiltinTool` holds a session store.
- **Spawn returns a handle immediately.** The session keeps running inside the host, and `wait_claude_turn` collects the result. A blocking spawn would hold the calling agent inside one tool call for minutes.
- **Knobs are spawn-request fields,** not separate functions. R3: "A function that only forwards one option adds a layer and nothing else."
- **Budgets are native on Claude:** `max_budget_usd`, `max_turns`, `task_budget`, and the thinking budget. `max_output_tokens` goes through an environment variable whose name must be verified.
- **Custom tools stay in our process.** Vidbyte `BaseTool`s become an in-process SDK MCP server via `create_sdk_mcp_server` + `tool()`.
- **Errors (user requirement, Prompt 2):** "return semantic error messages if something goes wrong, each funciton shoulllld make sure to handle errors".
  - The vocabulary is `claude.<problem>`, each code with a next step the caller is told. The problem names come from R3 "One error vocabulary for both hosts" and are shared with CodexHost, so cross-harness code can branch on the problem without caring which host raised it.
  - R3's "Claude detects it via" column is the mapping:
    - `CLINotFoundError` → `not_installed`;
    - `ProcessError(exit_code, stderr)` → `process_exited`;
    - `ResultError` with subtype `error_max_budget_usd` / `error_max_turns` → `budget_exhausted`;
    - `terminal_reason == "api_error"` → `api_error`;
    - `RateLimitEvent` rejected → `usage_limited`;
    - assistant error kinds (`authentication_failed`, `billing_error`, `rate_limit`) → the matching codes;
    - `CLIJSONDecodeError` / `MessageParseError` → `protocol_mismatch`;
    - `ResultMessage.permission_denials` → `permission_denied`;
    - `get_session_info()` returning `None` → `session_not_found`;
    - a second live client on one session → `session_busy`.
  - Tool wrappers return an error `ToolResult` instead of raising, matching the session tools' convention.
- **Tool permissions:** each tool declares the R or W shown in R3 (READ / WRITE). The default `PermissionPolicy` allows only SAFE and READ, so WRITE (spending) tools need an explicit opt-in. A ✗ function is never a model-facing tool; no ★ function is ✗.
- **Answers to R3 "Needs you", from Prompt 4:**
  - Q1, the ⚑ functions: default accepted, so they are left out of this PR. Nothing in this PR calls claude-agent-sdk's private `_send_control_request`.
  - Q2, sequential PRs: superseded by Prompt 4, which asks for two PRs in parallel. There is no shared base module or extraction in either PR, ClaudeHost is self-contained, and its names mirror CodexHost's through R3's "Shared vocabulary" table. Extracting the shared pieces (error envelope, tool base, handle registry) is a later PR.
  - Q3, installed binary: default accepted. `cli_path` defaults to the user's installed `claude`, not the SDK's bundled CLI, with a minimum-version check from `initialize` → `claude_code_version`.

### Rejected alternatives
- **vidbyte-cli `lib/threads/` placement and driving `claude -p` directly (R1, the first design reply, not reproduced):** superseded by Prompt 2's SDK placement and the official SDK.
- **Placing host code directly in `vidbyte/harnesses/<host>/`:** it would mix two meanings of "harness" with the existing `Harness` envelope. Hence `native/`.
- **A function per setting** (`set_claude_max_turns` and so on): settings are spawn-request fields (R3 "Rejected").
- **A shared base class or module for both hosts in these PRs:** it would have one implementation per PR, and the two PRs are built in parallel.
- **The SDK's bundled Claude CLI as the default:** claude-agent-sdk 0.2.165 bundles Claude Code 2.1.294, and `_find_cli()` checks the bundled copy before PATH. It differs from the user's install, which has their login, plugins and settings (R3 "Rejected").
- **⚑ functions through the private `_send_control_request`:** left out (Q1 default).
- **A blocking spawn tool:** see "Spawn returns a handle immediately".

### Constraints and assumptions
- **Parallel PRs.** Two pipelines run at the same time from base commit `678136bd4358bcf9f120504cecd818d36a3d46fe` (origin/main, 2026-10-12): this one (ClaudeHost) and the CodexHost one. Neither PR may depend on the other or reference code only the other creates. Whichever PR merges second catches up by merging origin/main into its branch, never by rebasing after the first push, and resolves the conflicts then.
- **Shared-file contract,** to keep that second merge trivial. These rules bind both PRs identically:
  - **`vidbyte/harnesses/native/__init__.py`** _(revised by the orchestrator after S0, 2026-10-12, because lint rule A001 requires its seven-field header in every tracked `.py` file, `__init__` files included, so the first four-line docstring would have failed the gate)_.
    - Both PRs create this file with exactly the content of the fenced block below, without the fence lines. That means LF line endings, a final newline after the closing `"""`, and nothing else: no imports and no `__all__`.
    - The file's SHA-256 must be `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`. The orchestrator checks this in both PRs.
    - Copy it byte for byte; do not reword, rewrap or reorder it.
    - If a gate still rejects these bytes, do not diverge silently. Report BLOCKED with the rule ID and its output, and the orchestrator will change both PRs together.
    - Host classes are imported from their own subpackage (`vidbyte.harnesses.native.codex` or `vidbyte.harnesses.native.claude`). This file never names a host.

`````python
"""FILE: vidbyte/harnesses/native/__init__.py

PURPOSE: Marks vidbyte/harnesses/native as the package of native coding-harness hosts: one subpackage per coding harness, each wrapping that harness's official SDK in small, atomic functions on a host class.
ROLE IN CODEBASE: A parent package only. Callers import a host from its own subpackage, never from this module, so this module imports nothing and names no harness.
ARCHITECTURE NOTE: Each harness subpackage owns its host class, its vendor SDK import, and its errors. Nothing here imports a vendor SDK, so importing this package never requires an optional extra.
COMMON MODIFICATION PATTERNS: A new harness adds its own subpackage beside the existing ones and leaves this module unchanged.
KNOWN EDGE CASES: None; the module defines no names.
RELATED DOCS: vidbyte/harnesses/README.md
TESTS: None of its own; each harness subpackage has its own tests.
"""
`````

  - **No `vidbyte/harnesses/native/README.md` in either PR.** The S0 scout verified that no lint rule requires a README in every folder: A009 only caps README size, and C015 forbids shipping a README in the wheel.
  - **No shared test files.**
    - Each PR's tests live only in files or folders whose names contain its own host, for example a feature pack `tests/features/codex_host/` or `tests/features/claude_host/`.
    - Feature packs under `tests/features/` carry no `__init__.py` in this repo.
    - Every new test `.py` needs its own A001 header.
  - **`vidbyte/lib/enums/failure.py`:** the Codex PR adds its new `CODEX_*` members immediately after the last existing `CODEX_*` member. This PR (Claude) adds its `CLAUDE_*` members as one block that is not adjacent to the end of the `CODEX_*` block. For example, put the block directly before the first existing `CODEX_*` member, or wherever the file's own ordering puts it, as long as it does not touch the lines right after the last `CODEX_*` member.
  - **Export lists and indexes: insert only your own entries, never reorder or remove existing ones.** This covers `vidbyte/lib/enums/__init__.py`, `vidbyte/__init__.py`, `vidbyte/tools/builtins/__init__.py`, `vidbyte/tools/toolsets/__init__.py`, `REPO_MAP.md`, `vidbyte/harnesses/README.md` and `contracts/sdk-public-api.json`.
    - Put each new entry where the file's own ordering puts it. Imports are isort-sorted (I001), and `contracts/sdk-public-api.json` is regenerated, never hand-edited; it keeps its exports sorted (`lint/core/public_api_contract.py:87`).
    - Expect a small conflict in these files when the second PR merges. _(Clarified by the orchestrator after S0, 2026-10-12.)_
  - **`pyproject.toml`:** only this PR changes it (the new `claude` extra). The Codex PR does not touch it.
- **The user's machine:**
  - `claude` 2.1.296 is installed at `C:/Users/422mi/.local/bin/claude`.
  - claude-agent-sdk 0.2.165, the version read from source in the conversation, bundles Claude Code CLI 2.1.294.
  - claude-agent-sdk is not installed in any vidbyte-sdk environment yet.
- **Shared plan window.** On the user's claude.ai login, every spawned session draws from the same five-hour and seven-day windows as the user's own interactive Claude Code sessions (R3 "What could go wrong"). Automated tests make no live calls, and CI has no Anthropic credentials.
- **Draft PR only.** Never merge, never mark ready.
- **AGENTS.md binds every change:** placement rules, the five coding principles, `docs/` opaque, and the full local gate `python scripts/run_ci.py` before anything is called complete.

### Clarifications and answers
- Q (R2): put the host code in `vidbyte/harnesses/native/<host>/`, reuse settings, make spawn non-blocking? A (Prompt 3): "yes the folder change the things that you pushed back on makes sense".
- Q (Prompt 3): "recommend the same "full implementation subspace of functions" for a similiar ClaudeHost class". A: R3 "ClaudeHost: full list".
- Q (R3 "Needs you" 1–3): A (Prompt 4): "great, using the spec-pipeline skill file do you think that you can implement the Codexhost and ClaudeHost functionality in the vidbyte-sdk/ in parallel in 2 seperate prs." That answer accepts the defaults for 1 and 3 and replaces 2 with two parallel PRs.

### Terminology
- **host:** `ClaudeHost` (or `CodexHost`), the class that owns a harness's live processes and the sessions or turns they run.
- **handle:** what spawn returns right away. It names a live session inside the host that started it.
- **★ / ⚑ / ✗ / R / W / internal:** the R3 legend.
  - ★ = first PR for that host.
  - ⚑ = reachable from Python only through the private `_send_control_request`.
  - ✗ = a plain function, never a model-facing tool.
  - R / W = the tool's READ or WRITE permission.
  - internal = not exported as a tool.
- **native:** the vendor's coding-agent executable (`claude`, `codex`), as opposed to the SDK's own `Harness` envelope.
- **session / turn:** Claude's nouns. A session is one conversation transcript, and a turn is one prompt through to its `ResultMessage`. Codex's equivalent noun is "thread".
- **Vidbyte-run subagents vs native subagents:** `launch_claude_subagents` makes Vidbyte itself start N sessions or forks. Native subagents are Claude's own `agents` (`AgentDefinition`) passed in the spawn request.
- **shared verbs:** R3's "Shared vocabulary" table. CodexHost uses the mirrored names (`check_codex_ready` ↔ `check_claude_ready`, …).

### Implementation hints
- **Nearest siblings:**
  - `vidbyte/agents/codex/`, the `CodexHarnessAgent` package, for wrapping a vendor coding-agent SDK. The vendor SDK is imported in exactly one module (`transport.py`), and the extra is optional with a clear `*_sdk_unavailable` failure when missing.
  - `vidbyte/lib/dataclasses/codex.py` and `vidbyte/lib/enums/codex.py`, for how harness settings records and enums are written and validated.
  - `vidbyte/tools/builtins/sessions/` for the tool layout: `_base.py` with `_SessionBuiltinTool` binding a store, and `descriptions.py`.
  - `vidbyte/tools/toolsets/coding.py` for the toolset.
  - `vidbyte/tools/README.md` sections on `PricedOperationTool` and the `PauseAgentTool(max_seconds)` bound.
- **New files by placement rule:**
  - records in `vidbyte/lib/dataclasses/claude.py`;
  - enums in `vidbyte/lib/enums/claude.py`, exported from `vidbyte/lib/enums/__init__.py` (for example permission mode, effort level, thinking mode, setting source, rate-limit status and type);
  - failure codes as new `CLAUDE_*` members of `FailureCode` in `vidbyte/lib/enums/failure.py`.
  Check first whether any Claude record or enum already exists (`git grep -n -i "claude"` over `vidbyte/lib/`).
- **claude-agent-sdk 0.2.165 source, read-only reference.** It is an extracted download: read it, never import from it and never execute it.
  - Location: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/claude-agent-sdk-x/claude_agent_sdk-0.2.165/src/claude_agent_sdk/`. Key files: `__init__.py` (exports), `types.py`, `client.py`, `query.py`, `_errors.py`, `_internal/` (`query.py` holds the private `_send_control_request`; sessions and session-mutation modules), `_internal/transport/subprocess_cli.py` (`_find_cli`), `_cli_version.py`.
  - `ClaudeSDKClient` methods: connect, query, receive_messages, receive_response, interrupt, set_permission_mode, set_model, rewind_files, reconnect_mcp_server, toggle_mcp_server, stop_task, get_mcp_status, get_context_usage, get_server_info, disconnect.
  - Session functions: list_sessions(directory, limit, offset, include_worktrees), get_session_info, get_session_messages(limit, offset), list_subagents, get_subagent_messages, rename_session, tag_session, delete_session, fork_session(session_id, directory, up_to_message_id, title) → ForkSessionResult.
  - Errors: CLINotFoundError, CLIConnectionError, ProcessError(exit_code, stderr), ResultError(subtype, terminal_reason, data), CLIJSONDecodeError, MessageParseError.
  - `ResultMessage` fields: subtype, duration_ms, duration_api_ms, is_error, num_turns, session_id, stop_reason, total_cost_usd, usage, result, structured_output, model_usage, permission_denials, deferred_tool_use, errors, api_error_status, uuid, terminal_reason, origin.
  - `RateLimitInfo` fields: status (allowed / allowed_warning / rejected), resets_at, rate_limit_type (five_hour / seven_day / seven_day_opus / seven_day_sonnet / overage), utilization, overage fields.
- **TypeScript SDK 0.3.296 type definitions, for cross-reference only:** `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/claude-agent-sdk-ts/x/package/sdk.d.ts`. They cover the `initialize` response shape (commands, agents, models, account, claude_code_version, hooks_applied, plugins_applied), `AccountInfo`, and `ModelInfo`.
- **Do not touch:** `docs/` beyond this run's `docs/spec/claude-host/` files; `lint/baseline.json` (never raise a number); the CodexHost worktree; `vidbyte/agents/codex/` (read it as a pattern only).

### Open questions (the spec author resolves each as an A- or Q-item)
- **Steering:** does `client.query()` sent mid-turn queue the message or start a new turn? This decides what `steer_claude_session` promises.
- **Output-token cap:** the exact environment variable for max output tokens (R3: "verify the name").
- **`initialize` contents:** does `get_server_info()` in Python 0.2.165 return the `initialize` response, including `claude_code_version`, `models` and `account`?
- **Readiness:** how `check_claude_ready` detects "signed in", via `account` from `initialize` or via `claude auth status` in the CLI, and at what process cost.
- **Rate limits before any event:** what `get_claude_rate_limits` returns before this host has seen any `RateLimitEvent` (⚑ `get_usage` is excluded).
- **Concurrency cap:** what default limit `launch_claude_subagents` uses. Each session is one `claude` process, so measure memory per process first and do not invent a threshold.
- **Version pin:** how `claude-agent-sdk` is pinned in the new extra. The Codex precedent `>=0.162.1,<0.163.0` is that narrow only because its tool bridge touches private attributes, and this PR uses no private API.
- **Busy sessions:** how the host refuses a second live client on one session id (`claude.session_busy`, suggest a fork). R3 "What could go wrong" lists two writers on one transcript as a risk.
- **Tool binding:** how a tool binds one `ClaudeHost` per agent, and who closes the host's processes when the agent finishes.
- **MCP:** whether `vidbyte/mcp_server/` needs any code to serve the toolset.
- **Root export:** whether `ClaudeHost` and the functions are exported from the root `vidbyte` package. Every root export changes `contracts/sdk-public-api.json`, which also conflicts at the second parallel merge.
- **CI install:** how `scripts/run_ci.py` and CI install extras, and therefore whether tests can import `claude_agent_sdk` in CI or must fake it at the transport seam.

## D. Weighted words
- "the function should have all the params needed to launch a codex thread according to their sdk and also return semantic error  messages if something goes wrong, each funciton shoulllld make sure to handle errors." — Prompt 2. ClaudeHost inherits this through Prompt 3's "the same".
- "then apply this same principle/philosophy of functions to other open source harnesses  (claude code, grok build, opencode, etc)." — Prompt 2
- "connect each individual function to the vidbyte/tools folder as well to give agents the functionalties in tools and not have to rely on them actually trying to do these things during their agent run." — Prompt 2
- "I want to create all types of small, atomic, rueusable, and helper functions for interacting with codex in this class" — Prompt 2
- "can you recommend the same "full implementation subspace of functions" for a similiar ClaudeHost class that implements everything that we can do with claude code." — Prompt 3
- "Then,  return to me all of the functions for the ClaudeHost and CodexHost, expecting a big list in this request." — Prompt 3
- "And coming up with very simple agents to be built inside of the vidbyte-cli/ like this." — Prompt 1
- "All of a sudden, "launching a codex thread with 3 codex subagents, 4 claude subagents, and then using a grok thread to merge the results is very easy,  it is only a few functions that we create" — Prompt 1
- "we could even package all of these into tools that other agents can use. we can even create like an "agent terminal toolset mcp" that packages all of these types of tools/functions" — Prompt 1
- "implement the Codexhost and ClaudeHost functionality in the vidbyte-sdk/ in parallel in 2 seperate prs." — Prompt 4

## E. The assistant's design replies the user accepted (verbatim)

_R2 answers Prompt 2. R3 answers Prompt 3 and supersedes R2 wherever they differ: R3's "CodexHost: full list (refreshed)" replaces R2's "Codex function checklist". The first reply (R1, answering Prompt 1) placed the work in vidbyte-cli; Prompt 2 superseded it, so it is not reproduced._

### R2 — reply to Prompt 2 (2026-10-12 21:00 UTC)

`````markdown
**vidbyte-sdk · main · harness-thread vocabulary**
Status: Decided. Each host gets small functions in `vidbyte/harnesses/native/codex/`, and each function gets a matching tool in `vidbyte/tools/builtins/codex/`. The Codex checklist below comes from the 105 client methods in openai-codex 0.162.1 plus the `codex` 0.161 CLI.

Changed since last turn:
- **Location:** this now lives in the SDK, not in vidbyte-cli's `lib/threads/`.
- **How we talk to Codex:** through the official openai-codex SDK instead of running `codex exec` (your call; it answers my first question from last turn). Features that only exist in the CLI (Cloud, doctor, queue, apply) still run the `codex` command.
- **Shape:** many small functions per host instead of one `launch(mode=…)`.

## Three decisions to settle before the catalog

**1. `vidbyte/harnesses/` already has a job.** It holds the `Harness` run envelope: a YAML-configured `run()`, a registry, and trajectory datasets. Codex functions placed directly beside it would mix two meanings of "harness".
- **Location:** `vidbyte/harnesses/native/codex/`. "Native" matches how `hosts.py` describes Codex and Claude: "native coding-agent executables".
- **They combine:** a `Harness.run()` can call `spawn_codex_thread`.
- **AGENTS.md placement rules:** new records go in the existing `vidbyte/lib/dataclasses/codex.py`, new enums in `vidbyte/lib/enums/codex.py`, and new failure codes extend the existing `CODEX_*` members of `FailureCode`.
- **Reuse the existing settings:** `CodexThreadSettings`, `CodexTurnSettings`, `CodexClientSettings`, `CodexSubagentSettings` and `CodexContentTranslator` already validate model, effort, sandbox, approvals, personality and service tier, and convert them to openai-codex arguments. Don't declare those fields a second time.
- **Tool layout:** copy `builtins/sessions/`: a `_base.py` that holds shared state, one file per group of tools, and a `descriptions.py`. Bundle them as `toolsets/codex.py`, like `toolsets/coding.py`.
- **The "agent terminal MCP" comes almost for free:** `mcp_server/` already exposes SDK tools.

**2. Small functions hide how long the Codex process lives, so the design has to make it explicit.**
- **One-shot functions** (list, read, fork, archive, models, account) can start a Codex app-server process, make one call, and close it.
- **Live functions** (steer, interrupt, track usage, answer approvals, custom tools, wait) need the turn to still be running inside a process that is still open. A new process can't steer a turn that another process started.
- **So the class is `CodexHost`:** an async context manager that owns one app-server connection and the turns it started. Each function is a method on it, and module-level functions wrap the one-shot methods.
- **Tools hold a host:** each tool keeps one `CodexHost` per agent, the same way `_SessionBuiltinTool` keeps a session store.
- **The spawn tool doesn't block:** it returns a handle right away while the turn keeps running in the host, and `wait_codex_turn` collects the result. A blocking spawn would hold the calling agent inside one tool call for minutes. `CodexHarnessAgent` already cancels its own custom-tool calls after 300 seconds.

**3. Codex has no output-token parameter.** Neither `ThreadStartParams` nor `TurnStartParams` has one in 0.162.1. Two real controls exist:
- `thread/goal/set` accepts a `token_budget`. When the budget runs out, the goal's status becomes `budgetLimited`.
- `thread/tokenUsage/updated` reports usage while the turn runs, so the host can call `turn/interrupt` once a cap is passed.

So Vidbyte enforces `max_output_tokens` itself, and the docstring must say so.

## `spawn_codex_thread`: inputs and errors

```python
@dataclass(frozen=True, slots=True)
class CodexSpawnRequest:                                  # vidbyte/lib/dataclasses/codex.py
    prompt: str | CodexRunInput                           # existing: text, images, skills, mentions
    thread: CodexThreadSettings = CodexThreadSettings()   # model, provider, cwd, sandbox, approvals,
                                                          # base instructions, personality, tier, ephemeral, config
    turn: CodexTurnSettings = CodexTurnSettings()         # effort, reasoning summary, per-turn overrides
    developer_instructions: str = ""
    approvals_reviewer: CodexApprovalsReviewer = CodexApprovalsReviewer.PROVIDER_DEFAULT  # user | auto_review | guardian_subagent
    output_schema: type[BaseModel] | Mapping[str, Any] | None = None
    tools: tuple[BaseTool, ...] = ()                      # dynamic tools: fixed at thread start
    subagents: CodexSubagentSettings | None = None
    goal: CodexGoal | None = None                         # objective + token_budget → thread/goal/set
    max_output_tokens: int | None = None                  # Vidbyte interrupts; Codex has no such field
    timeout_seconds: float = CodexLimit.TURN_TIMEOUT_SECONDS

async def spawn_codex_thread(self, request: CodexSpawnRequest) -> CodexTurnHandle: ...
```

All functions share one error mapper. It turns transport exceptions, JSON-RPC errors and failed precondition checks into `CodexOperationError(code, operation, message, next_step)`. The tool wrapper turns the same error into an error `ToolResult`, following the session tools' rule that bad input should "return an error result instead of raising into the agent loop". Precondition checks run before any money is spent:

| Code | Detected by | What the agent is told (what happened, then what to do) |
|---|---|---|
| `codex.sdk_unavailable` (exists) | import | openai-codex is missing → `pip install "vidbyte-sdk[codex]"` |
| `codex.binary_unsupported` | `initialize` metadata | Found Codex X, need ≥ Y → upgrade, or pass `codex_bin` |
| `codex.not_signed_in` | `account/read` | No Codex login → run `codex login`, or pass an API key |
| `codex.auth_mode_unsupported` | `account/read` | This needs ChatGPT sign-in (e.g. Cloud); an API-key login can't do it |
| `codex.usage_limited` | `account/rateLimits/read` | Plan window used up, resets at T → wait, or switch to an API key |
| `codex.model_unknown` | `model/list` | Model `m` isn't available; the available ones are a, b, c |
| `codex.sandbox_not_ready` | `windowsSandbox/readiness` | Windows sandbox isn't set up → `setup_codex_windows_sandbox` |
| `codex.thread_not_found` | `thread/read` | No thread `id` → find it with `list_codex_threads` |
| `codex.thread_busy` | the host's list of running turns | Turn `t` is still running → `steer_codex_turn` or `wait_codex_turn` |
| `codex.fork_failed` (exists) | precondition check | A thread can't be forked before its first completed turn |
| `codex.turn_timed_out` / `codex.token_cap_reached` | host guard | Stopped at N seconds / N tokens; the partial output is attached |
| `codex.host_exited` | process watch | The app-server died and turns `t1, t2` were lost → restart it, resume by thread id |
| `codex.schema_violation` | local check | The answer didn't match the schema; the raw text is attached for a repair turn |

`★ Insight ─────────────────────────────────────`
- The app-server has `mcpServer/tool/call` and `command/exec`. They call an MCP tool through Codex's configured servers, or run a command under Codex's sandbox rules, without any model turn. That's your point exactly: give agents the ability as a tool instead of hoping the model works out how to do it. These are predictable, cheap, and follow the same rules.
- `thread/fork` accepts `last_turn_id` and `exclude_turns`, so you can branch from any earlier turn, not just the latest one. The SDK's `CodexFork` only forks from the latest turn, so the new function is strictly more capable.
`─────────────────────────────────────────────────`

## Codex function checklist

Each row names the call behind it. **Tool** is the permission its tool wrapper would declare; Codex's default `PermissionPolicy` allows only SAFE and READ. ✗ means a plain function that should never be a tool. ★ marks my first-PR set.

**Readiness and account**
| Function | Backed by | Tool |
|---|---|---|
| ★ `check_codex_ready()`: binary, version, login and sandbox in one check | `initialize`, `account/read`, `windowsSandbox/readiness` | READ |
| `get_codex_version()` | `initialize` metadata | READ |
| `run_codex_doctor()` | CLI `codex doctor` | READ |
| `get_codex_account()`: login type, plan | `account/read` | READ |
| ★ `get_codex_rate_limits()`: usage windows, reset times, whether normal usage is allowed | `account/rateLimits/read` | READ |
| `get_codex_account_usage()` | `account/usage/read` | READ |
| `login_codex_api_key`, `start_codex_chatgpt_login`, `start_codex_device_login`, `cancel_codex_login`, `logout_codex` | `account/login/*`, `account/logout` | ✗ |
| `setup_codex_windows_sandbox()` | `windowsSandbox/setupStart` | ✗ |
| ★ `list_codex_models(include_hidden)` | `model/list` | READ |
| `get_codex_provider_capabilities()` | `modelProvider/capabilities/read` | READ |

**Threads**
| Function | Backed by | Tool |
|---|---|---|
| ★ `spawn_codex_thread(request)` | `thread/start` + `turn/start` | WRITE |
| ★ `continue_codex_thread(thread_id, input, overrides)` | `thread/resume` + `turn/start` | WRITE |
| ★ `fork_codex_thread(thread_id, from_turn_id, exclude_turns, overrides)` | `thread/fork` | WRITE |
| `fork_codex_thread_many(thread_id, prompts)`: N alternative branches | `thread/fork` × N | WRITE |
| `revert_codex_thread(thread_id, before_turn_id)` | `thread/revert` | WRITE |
| `compact_codex_thread(thread_id)` | `thread/compact/start` | WRITE |
| `rename_codex_thread`, `set_codex_thread_git_info` | `thread/name/set`, `thread/metadata/update` | WRITE |
| `archive_codex_thread`, `unarchive_codex_thread` | `thread/archive`, `thread/unarchive` | WRITE |
| `delete_codex_thread` | `thread/delete` | ✗ |
| ★ `list_codex_threads(cwd, search, archived, source_kinds, sort)` | `thread/list` | READ |
| ★ `read_codex_thread(thread_id, include_turns)` | `thread/read` | READ |
| `list_codex_turns`, `list_codex_items`: transcript, page by page | `thread/turns/list`, `thread/items/list` | READ |
| `export_codex_transcript(thread_id)` → Markdown or handoff | the two above | READ |
| `list_loaded_codex_threads()` | `thread/loaded/list` | READ |
| `find_or_spawn_codex_thread(name)` | `thread/list` search, then resume or start | WRITE |

**Live turn control** (only works through the `CodexHost` that started the turn)
| Function | Backed by | Tool |
|---|---|---|
| ★ `wait_codex_turn(handle, timeout)` / `get_codex_turn_result(handle)` | `TurnHandle.run()` / `turn/completed` | READ |
| ★ `steer_codex_turn(handle, input)`: add guidance mid-turn | `turn/steer` (with `expected_turn_id`) | WRITE |
| ★ `interrupt_codex_turn(handle)` | `turn/interrupt` | WRITE |
| `stream_codex_turn(handle)`: items, text deltas, plan updates | `TurnHandle.stream()` | READ |
| `get_codex_turn_diff(handle)`: the turn's current diff | `turn/diff/updated` | READ |
| `get_codex_turn_plan(handle)` | `turn/plan/updated` | READ |
| `inject_codex_items(thread_id, items)`: add context without a turn | `thread/inject_items` | WRITE |
| `run_codex_thread_shell(thread_id, command)`: output is saved in the thread's history | `thread/shellCommand` | WRITE |
| `queue_codex_message(session, text)` | CLI `codex queue` | WRITE |
| `set_codex_approval_handler(callback)`: answer approval requests in code | server requests `item/commandExecution/requestApproval`, `item/fileChange/requestApproval` | ✗ |
| `approve_codex_guardian_denied(thread_id, event)` | `thread/approveGuardianDeniedAction` | ✗ |

**Goals and budgets**
| Function | Backed by | Tool |
|---|---|---|
| `set_codex_goal(thread_id, objective, token_budget)` | `thread/goal/set` | WRITE |
| `get_codex_goal`, `pause_codex_goal`, `clear_codex_goal` | `thread/goal/get`, `goal/set` with status paused, `thread/goal/clear` | READ / WRITE |
| `cap_codex_tokens(handle, max_output_tokens)` | `thread/tokenUsage/updated` → `turn/interrupt` | internal |

**Usage and cost**
| Function | Backed by | Tool |
|---|---|---|
| ★ `track_codex_thread_usage(thread_id)`: input, cached, output and reasoning tokens per turn and in total, with prices | `thread/tokenUsage/updated` + the SDK's `CodexMetricsTranslator` | READ |
| `get_codex_turn_usage(handle)` | the turn result's usage | READ |
| `plan_codex_fan_out(n)`: how many threads fit in what's left of the usage window | `account/rateLimits/read` | READ |

**Subagents**
| Function | Backed by | Tool |
|---|---|---|
| ★ `launch_codex_subagents(prompts, settings, limit)`: Vidbyte runs exactly N threads or forks | `thread/start` / `thread/fork` × N | WRITE |
| `configure_codex_native_subagents(max_threads, roles, defaults)`: let Codex decide when to delegate | thread `config` (what `CodexSubagentSettings` sets) | option on spawn |
| `list_codex_subagent_threads(parent)` | `thread/list` with `source_kinds` = subAgent kinds | READ |

**Review**
| Function | Backed by | Tool |
|---|---|---|
| ★ `start_codex_review(thread_id, target, delivery)`: target is uncommitted changes, a base branch, a commit, or custom; result inline or in a separate thread | `review/start` | WRITE |
| `run_codex_review_cli(target)` | CLI `codex review` | WRITE |

**Deterministic operations through Codex (no model turn)**
| Function | Backed by | Tool |
|---|---|---|
| `exec_in_codex_sandbox(command, cwd, sandbox_policy, timeout_ms, env)`, plus write/resize/terminate | `command/exec*`, CLI `codex sandbox` | WRITE |
| `call_codex_mcp_tool(thread_id, server, tool, args)` | `mcpServer/tool/call` | WRITE |
| `read_codex_mcp_resource(server, uri)` | `mcpServer/resource/read` | READ |
| `fuzzy_find_codex_files(query, roots)` | `fuzzyFileSearch` | READ |

**Extensions and config**
| Function | Backed by | Tool |
|---|---|---|
| `list_codex_mcp_servers()`, with startup status | `mcpServerStatus/list` | READ |
| `reload_codex_mcp_servers()` | `config/mcpServer/reload` | WRITE |
| `login_codex_mcp_oauth(server)` | `mcpServer/oauth/login` | ✗ |
| `add_codex_mcp_server`, `remove_codex_mcp_server` | CLI `codex mcp`, or `config/value/write` | ✗ |
| `list_codex_skills(cwds)` | `skills/list` | READ |
| `add_codex_skill_roots(paths)`: point Codex at Vidbyte's skill folders | `skills/extraRoots/set` | WRITE |
| `configure_codex_skill(...)` | `skills/config/write` | ✗ |
| `list_codex_plugins`, `read_codex_plugin`, `read_codex_plugin_skill` | `plugin/list`, `plugin/read`, `plugin/skill/read` | READ |
| `install_codex_plugin`, `uninstall_codex_plugin` | `plugin/install`, `plugin/uninstall` | ✗ |
| `list_codex_apps`, `read_codex_app` | `app/list`, `app/read`, `app/installed` | READ |
| `list_codex_hooks()` | `hooks/list` | READ |
| `read_codex_config(cwd, include_layers)`, `read_codex_config_requirements()` | `config/read`, `configRequirements/read` | READ |
| `write_codex_config(key, value)`, batch version | `config/value/write`, `config/batchWrite` | ✗ |
| `list_codex_features()`, `set_codex_feature()` | `experimentalFeature/list`, `experimentalFeature/enablement/set` | READ / ✗ |
| `list_codex_permission_profiles(cwd)` | `permissionProfile/list` | READ |

**Organizing and linking threads**
| Function | Backed by | Tool |
|---|---|---|
| `create_codex_section`, `move_codex_thread_to_section`, …: group one run's threads together | `threadSection/*`, `thread/section/move` | WRITE |
| `attach_to_codex_thread(thread_id, type, key, payload)`: link a PR or a Linear issue | `thread/attachment/add`, `list`, `remove` | WRITE |

**Codex Cloud** (CLI only; this is the closest match to your `claude_thread_cloud()` example)
| Function | Backed by | Tool |
|---|---|---|
| `submit_codex_cloud_task(env, prompt)` | `codex cloud exec` | WRITE |
| `get_codex_cloud_task_status`, `list_codex_cloud_tasks`, `get_codex_cloud_task_diff` | `codex cloud status`, `list`, `diff` | READ |
| `apply_codex_cloud_task(task_id)` | `codex cloud apply` | WRITE |
| `apply_latest_codex_diff()` | `codex apply` | WRITE |

Cloud checks before running: the user signed in with ChatGPT (otherwise `auth_mode_unsupported`), a Cloud environment is configured, and the working tree is clean before `apply`.

**Left out on purpose:**
- `fs/*` duplicates `vidbyte/tools/filesystem/`.
- `thread/realtime/*` is audio.
- `feedback/upload`, `marketplace/*` and `plugin/share/*` aren't useful to an agent.
- `account/sendAddCreditsNudgeEmail` sends the user an email.
- `account/rateLimitResetCredit/consume` spends plan credits, so it must never be a tool.
- `externalAgentConfig/*` looks like it imports another harness's config and history into Codex. That's interesting for mixing harnesses, but check what it actually does first.

## The same approach for other harnesses

Every harness uses the same naming (`<verb>_<host>_<noun>`), one `<Host>Host` class, the same error mapper and the same tool base. Each catalog has to come from auditing that harness's own SDK, not from copying Codex's list.
- **Your `claude_thread_cloud()` example can mean two things:** routing Claude through a cloud provider (Bedrock or Vertex), or a remote web session. Each has different preconditions.
- **Verbs I've already confirmed on Claude Code's CLI:** resume (`--resume`), fork (`--fork-session`), a spending budget (`--max-budget-usd`, which Codex doesn't have), subagents (`--agents`) and typed output (`--json-schema`).
- **Not checked yet:** whether Grok Build has a public SDK or a headless mode.

## What could go wrong, and the guard for each

- **Runaway spawning:** an agent calls the spawn tool 20 times in a row, which means 20 parallel turns on the user's plan. *Guard:* the tool takes a cap on live turns, the way `PauseAgentTool(max_seconds=…)` takes its limit. `thread_busy` and `usage_limited` come back as error results.
- **The app-server dies mid-turn:** every `wait_codex_turn` must return `host_exited`, never hang. This exact kind of hang happened before (the 0.147 cancel-hang).
- **Agents sharing a host:** two agents could steer each other's turns. *Guard:* a handle only works for the tool that created it, like `SessionScope.own_runs()`.
- **Protocol changes:** there are 105 methods in a 13,240-line generated file, pinned below 0.163. *Guard:* a contract test per function against a fake transport, so upgrading the pin means running tests, not redoing this audit.

Checked: openai-codex 0.162.1 `api.py` and `generated/v2_all.py` (105 client methods and their parameter classes); `codex --help` and `codex cloud --help` (0.161); SDK `vidbyte/harnesses/README.md` and the registry/execution signatures; `vidbyte/tools/README.md`; `builtins/sessions/{_base,descriptions}.py`; `toolsets/coding.py`; `lib/dataclasses/codex.py`; `lib/enums/failure.py`.

Rejected:
- **Files directly in `vidbyte/harnesses/`:** clashes with the `Harness` envelope.
- **A new parallel set of settings and enums:** duplicates `CodexThreadSettings` and breaks the placement rules.
- **A spawn tool that blocks:** holds the calling agent in one tool call for minutes.

---
**Re-entry · harness-thread vocabulary**

Decided:
- **Where it lives:** the vocabulary is in vidbyte-sdk. Functions in `vidbyte/harnesses/native/<host>/`, one tool per function in `vidbyte/tools/builtins/<host>/`, bundled in `toolsets/<host>.py`, and exposed over MCP through the existing `mcp_server/`.
- **How it talks to Codex:** the official harness SDK (the openai-codex app-server). Features that only exist in the CLI run the `codex` command.
- **Process ownership:** each host gets a `CodexHost` that owns one app-server and its running turns. One-shot functions wrap it, and the spawn tool returns a handle.
- **Errors:** reuse the existing Codex settings, enums and `FailureCode`. One error mapper produces a typed error, or an error tool result, with a next step. Checks run before any money is spent.
- **Carried over:** `max_output_tokens` is enforced by Vidbyte through a goal budget or an interrupt. Mixing harnesses and the Grok merge step still stand from last turn.

Open:
- Does `thread/revert` undo only the conversation, or files too?
- What does `externalAgentConfig/*` actually do?
- Does Grok Build have an SDK?
- The policy question on using plan-backed (subscription) usage in a paid product is unchanged.

Needs you:
1. Should the subpackage be `vidbyte/harnesses/native/codex/`? Default: yes.
2. Should the first PR be the 14 ★ functions plus their tools, `CodexHost` and the error mapper, with the rest as follow-up PRs grouped by table? Default: yes.
3. Should the spawn tool return a handle right away, with `wait_codex_turn` to collect the result? Default: yes.

*Reply "go" to accept all defaults.*

Next: on "go", I'll run the same grounded audit for Claude Code (claude-agent-sdk plus the CLI) and opencode, check Grok Build, then write the HANDOFF for the Codex first PR.
`````

### R3 — reply to Prompt 3 (2026-10-12 21:30 UTC)

`````markdown
**vidbyte-sdk · main · harness-thread vocabulary**
Status: Decided. `ClaudeHost` mirrors `CodexHost`, with one structural difference: Claude Code runs one process per live session, but its session history is plain files the SDK can read, fork, rename and tag without starting anything. Both full function lists are below.

Changed since last turn:
- **Accepted:** you agreed to `native/<host>/`, reusing the existing Codex settings dataclasses, and the spawn tool that returns immediately.
- **Claude audit:** checked against Claude Code 2.1.296, the Python `claude-agent-sdk` 0.2.165 (read from source) and the TypeScript SDK 0.3.296 (type definitions).
- **Codex list:** re-issued with about 20 additions.
- **Settings are fields now:** knobs like max turns or budget are fields on the spawn request, not separate functions. A function that only forwards one option adds a layer and nothing else.

## How ClaudeHost differs from CodexHost

- **Process model.** Codex runs one app-server process that hosts many threads. Claude runs one `claude` process per live session (`ClaudeSDKClient`). Fanning out 7 Claude sessions means 7 processes.
- **Session history needs no process on Claude.** `list_sessions`, `get_session_messages`, `fork_session`, `rename_session`, `tag_session` and `delete_session` read and write session files directly. Those functions are instant and free; only live sessions cost a process.
- **Budgets are built in on Claude.** Claude Code accepts `max_budget_usd`, `max_turns`, `task_budget` and a thinking budget. Codex needed a goal budget plus our own interrupt.
- **The Python SDK covers only part of what the CLI supports.** It exposes 10 live-control methods. The TypeScript SDK exposes about 30, and the CLI binary understands the rest (I found them in the 2.1.296 binary). From Python, the remainder is reachable only through the SDK's private `_send_control_request`. Those functions are marked ⚑.
- **Custom tools stay in our process on both hosts.** Claude uses an in-process MCP server (`create_sdk_mcp_server` + `tool`); Codex uses dynamic tools. Either way the tool code runs in our Python process.

`★ Insight ─────────────────────────────────────`
- **Same bundled-binary problem as Codex.** `claude-agent-sdk` 0.2.165 ships Claude Code 2.1.294 and `_find_cli()` checks the bundled copy before PATH. You have 2.1.296 installed. This is the trap `same-host-ensemble` already works around for Codex with `codex_bin`. To use the user's own login, plugins and settings, `ClaudeHost` should set `cli_path` to the installed `claude` and check a minimum version from `initialize`.
- **Free link to agent-run-sync.** The Python SDK has a `SessionStore` protocol (with an in-memory reference and conformance tests) that copies Claude transcripts into a store as they are written. A Vidbyte store connects Claude sessions to the agent-run-sync routes in #667 with no extra plumbing. On Codex, the equivalent is paging through `thread/items/list`.
`─────────────────────────────────────────────────`

## Shared vocabulary: the verbs cross-harness code calls

Names keep each vendor's own noun (Codex says thread, Claude says session) so each function matches the docs it wraps. Cross-harness functions such as `mixed_ensemble` and `adversarial_review` call only these shared verbs.

| Verb | CodexHost | ClaudeHost | Difference |
|---|---|---|---|
| Readiness check | `check_codex_ready` | `check_claude_ready` | none |
| Spawn | `spawn_codex_thread` | `spawn_claude_session` | Claude needs a process per session |
| Continue | `continue_codex_thread` | `continue_claude_session` | none |
| Fork from an earlier point | `fork_codex_thread(from_turn_id)` | `fork_claude_session(up_to_message_id)` | Claude's fork is an offline file copy |
| Rewind | `revert_codex_thread` (conversation) | `resume_claude_session_at` (conversation), `rewind_claude_files` (files) | only Claude restores files |
| Steer, interrupt, wait | `steer_codex_turn`, `interrupt_codex_turn`, `wait_codex_turn` | `steer_claude_session`, `interrupt_claude_turn`, `wait_claude_turn` | none |
| Usage | `track_codex_thread_usage` | `track_claude_session_usage` | Claude reports dollars; Codex reports only tokens |
| Rate limits | `get_codex_rate_limits` (asked directly) | `get_claude_rate_limits` (read from session events) | none |
| Models | `list_codex_models` | `list_claude_models` | none |
| History | `list_codex_threads`, `read_codex_thread` | `list_claude_sessions`, `get_claude_session_messages` | Claude needs no process |
| Budgets | goal `token_budget` + our interrupt | `max_budget_usd`, `max_turns`, `task_budget` | built into Claude |
| Native subagents | thread `config` (`agents.*`) | `agents` (`AgentDefinition`) | none |
| Vidbyte-run subagents | `launch_codex_subagents` | `launch_claude_subagents` | none |
| Review | `start_codex_review` (runs locally) | `run_claude_ultrareview` (runs in the cloud) | none |
| Cloud | `submit_codex_cloud_task` | `create_claude_cloud_session` | none |
| Import another harness's config | `import_external_agent_config` (verify) | `import_into_claude(source="codex")` | none |

## ClaudeHost: full list

Legend:
- ★ = first PR for that host.
- ⚑ = reachable from Python only through the private `_send_control_request` (the TypeScript SDK exposes it publicly).
- R / W = the tool wrapper's permission, READ or WRITE. The default `PermissionPolicy` allows only READ, so WRITE (spending) tools need an explicit opt-in.
- ✗ = a plain function, never a tool the model can call.
- internal = used by other functions, not exported as a tool.

**Spawn request fields (`ClaudeSpawnRequest`)**
- **Input:** `prompt` (text, or content blocks with images), `files` (`--file`), `cwd`, `add_dirs`
- **Model:** `model`, `fallback_model` (ordered list), `effort` (low to max), `thinking` (adaptive, a token budget, or off; display summarized or omitted), `betas` (API-key logins only)
- **Instructions:** `system_prompt` (replace it, or keep the `claude_code` preset and append, or load from a file), `exclude_dynamic_system_prompt_sections`, `system_prompt_snapshot`
- **Tools and permissions:** `builtin_tools`, `allowed_tools` and `disallowed_tools` (patterns like `Bash(git *)`), `permission_mode` (default, acceptEdits, plan, bypassPermissions, dontAsk, auto), `permission_prompts` (`host` or `none`), `restricted`, `sandbox` (on/off, auto-allow Bash, excluded commands, network allow/deny domains), `can_use_tool`, `hooks`
- **Extensions:** `tools` (Vidbyte `BaseTool`s, served through an in-process MCP server), `mcp_servers`, `strict_mcp_config`, `skills`, `plugins` (folder, zip or URL), `agents` (`AgentDefinition`: description, prompt, tools, disallowedTools, model, skills, memory, mcpServers, initialPrompt, maxTurns, background, effort, permissionMode), `main_agent` (`--agent`)
- **Which config loads:** `setting_sources` (user, project, local), `settings`, `bare`, `safe_mode`
- **Budgets:** `max_turns`, `max_budget_usd`, `task_budget`, `autocompact`, `max_output_tokens` (an environment variable; verify the name)
- **Session:** `session_id` (choose it up front), `name`, `resume`, `continue_conversation`, `fork_session`, `resume_session_at`, `resume_drops_turn`, `persist_session`, `enable_file_checkpointing`, `session_store`, `worktree`
- **Output:** `output_schema` (passed as `output_format`), `include_partial_messages`, `include_hook_events`, `forward_subagent_text`, `prompt_suggestions`
- **Process:** `cli_path` (default: the user's installed `claude`), `env`, `user`, `load_timeout_ms`, `timeout_seconds`

**Readiness, install, account**
| Function | Backed by | Tool |
|---|---|---|
| ★ `check_claude_ready()`: CLI found, minimum version, signed in | `CLINotFoundError`, `initialize` → `claude_code_version`, `account` | R |
| `get_claude_version()` | `claude --version` / `initialize` | R |
| `run_claude_doctor()` | `claude doctor` | R |
| `install_claude(target)`, `update_claude()` | `claude install` (stable / latest / version), `claude update` | ✗ |
| `get_claude_auth_status()` | `claude auth status --json` | R |
| `get_claude_account()`: email, org, subscription type, token source | `initialize` → `account` (TS `accountInfo()`) | R |
| `get_claude_provider()`: Anthropic directly, or Bedrock / Vertex / Foundry (your "cloud provider" example) | `account.apiProvider` | R |
| `login_claude(mode)`, `logout_claude()` | `claude auth login --claudeai / --console / --sso`, `claude auth logout` | ✗ |
| `setup_claude_token()`: long-lived token, subscription only | `claude setup-token` | ✗ |
| ★ `list_claude_models()`: effort levels, adaptive thinking, fast/auto mode support per model | `initialize` → `models` | R |
| `list_claude_commands()`: slash commands and skills | `initialize` → `commands` | R |
| `list_claude_agents()`, `list_claude_output_styles()` | `initialize` → `agents`, `available_output_styles` | R |
| ★ `get_claude_rate_limits()`: five-hour, seven-day and per-model windows, utilization, reset time, overage | latest `RateLimitEvent`; ⚑ `get_usage` | R |
| `get_claude_auto_mode_config()`, `…_defaults()`, `critique_claude_auto_mode_rules()` | `claude auto-mode config / defaults / critique` | R |
| `reset_claude_auto_mode()` | `claude auto-mode reset` | ✗ |
| `prewarm_claude_session(request)`: start the process before the prompt exists | `ClaudeSDKClient.connect()` (TS `startup()` / `prewarm()`) | internal |

**Live sessions**
| Function | Backed by | Tool |
|---|---|---|
| ★ `spawn_claude_session(request)` | `ClaudeSDKClient(options)` → `connect()` + `query()` | W |
| `run_claude_once(request)`: one-shot, no control after it starts | `query()` | W |
| ★ `continue_claude_session(session_id, prompt)` | `resume` | W |
| `continue_latest_claude_session(cwd)` | `continue_conversation` (`-c`) | W |
| ★ `fork_claude_session(session_id, up_to_message_id, title)` | `fork_session()` (file copy), or `resume` + `fork_session=True` | W |
| `fork_claude_session_many(session_id, prompts)` | the above × N | W |
| `resume_claude_session_at(session_id, message_id, drop_turn)` | `resume_session_at`, `resume_drops_turn` | W |
| `resume_claude_session_for_pr(pr)` | `--from-pr` | W |
| `spawn_claude_session_in_worktree(name)` | `--worktree` | W |
| `close_claude_session(handle)` | `disconnect()` | internal |

**Background sessions (managed by Claude Code itself)**
| Function | Backed by | Tool |
|---|---|---|
| `spawn_claude_background_session(request)` | `--bg` (prints the id) | W |
| `list_claude_background_sessions(cwd, include_done)` | `claude agents --json [--all] [--cwd]` | R |
| `get_claude_background_logs(id)` | `claude logs <id>` | R |
| `stop_claude_background_session(id)`: the conversation is kept | `claude stop <id>` | W |
| `respawn_claude_background_sessions(id or all)`: restart on the current binary | `claude respawn` | W |
| `remove_claude_background_session(id)`: also removes its worktree when that's safe | `claude rm <id>` | ✗ |

**Session history (files on disk, no process needed)**
| Function | Backed by | Tool |
|---|---|---|
| ★ `list_claude_sessions(directory, limit, offset, include_worktrees)`: summary, title, first prompt, branch, tag, timestamps | `list_sessions()` | R |
| ★ `get_claude_session_info(session_id)` | `get_session_info()` | R |
| ★ `get_claude_session_messages(session_id, limit, offset)` | `get_session_messages()` | R |
| `list_claude_subagents(session_id)`, `get_claude_subagent_messages(session_id, agent_id)` | `list_subagents()`, `get_subagent_messages()` | R |
| `export_claude_transcript(session_id)` → Markdown or handoff | the functions above | R |
| `rename_claude_session(session_id, title)`, `tag_claude_session(session_id, tag)` | `rename_session()`, `tag_session()` | W |
| `delete_claude_session(session_id)` | `delete_session()` | ✗ |
| `mirror_claude_sessions(store)`: copy transcripts into a store as they're written | `session_store`, `import_session_to_store()`, and the `*_from_store` / `*_via_store` variants | internal |
| `purge_claude_project_state(path, dry_run)` | `claude purge` | ✗ |

**Live turn control (only through the host's connected client)**
| Function | Backed by | Tool |
|---|---|---|
| ★ `wait_claude_turn(handle, timeout)`, `get_claude_turn_result(handle)` | `receive_response()` → `ResultMessage` | R |
| ★ `steer_claude_session(handle, message)` (verify whether a mid-turn message queues or interrupts) | `client.query()` (TS `streamInput()`) | W |
| `cancel_claude_queued_message(handle, id)` | ⚑ `cancel_async_message` | W |
| ★ `interrupt_claude_turn(handle)` | `interrupt()` | W |
| `stream_claude_session(handle)`: messages, partial text, hook events, subagent text | `receive_messages()` | R |
| `send_claude_slash_command(handle, command)`, e.g. `/compact` (verify) | `client.query("/…")` | W |
| `set_claude_model(handle, model)` | `set_model()` | W |
| `set_claude_thinking_budget(handle, tokens, display)` | ⚑ `set_max_thinking_tokens` | W |
| `set_claude_permission_mode(handle, mode)` | `set_permission_mode()` | ✗ |
| `set_claude_mcp_permission_override(handle, server, mode)` | ⚑ `setMcpPermissionModeOverride` | ✗ |
| `get_claude_context_usage(handle)`: tokens by category, percent of the window used, auto-compact threshold | `get_context_usage()` | R |
| `get_claude_server_info(handle)`: includes which hooks and plugins actually loaded | `get_server_info()` | R |
| `rewind_claude_files(handle, user_message_id)` | `rewind_files()` (needs `enable_file_checkpointing`) | W |
| `list_claude_tasks(handle)`: background Bash commands and subagents, with status and usage | task started / progress / updated / notification messages | R |
| `get_claude_task_output(handle, task_id)` | `TaskNotificationMessage.output_file`; ⚑ `get_task_output` | R |
| `stop_claude_task(handle, task_id)` | `stop_task()` | W |
| `background_claude_tasks(handle, tool_use_id)` | ⚑ `backgroundTasks` | W |
| `reload_claude_skills / _plugins / _output_styles(handle)` | ⚑ `reload_skills`, `reload_plugins`, `reload_output_styles` | W |
| `get_claude_effective_settings(handle)` | ⚑ `get_settings` | R |
| `apply_claude_settings(handle, settings)` | ⚑ `apply_flag_settings`, `update_settings` | ✗ |
| `list_claude_permission_rules(handle)`, `list_claude_hooks(handle)` | ⚑ `list_permission_rules`, `get_hooks_listing` | R |
| `seed_claude_read_state(handle, path, mtime)`: tell Claude a file was already read | ⚑ `seedReadState` | internal |
| `set_claude_permission_handler(callback)`: allow (and optionally rewrite the input or add rules), or deny (and optionally interrupt) | `can_use_tool` | ✗ |
| `register_claude_hooks(event → callback)` | `hooks` (10 events in Python; the CLI defines 33) | ✗ |

**Usage, cost, subagents**
| Function | Backed by | Tool |
|---|---|---|
| ★ `track_claude_session_usage(handle)`: input, output, cache-read and cache-write tokens, web searches, dollars per model | `ResultMessage.usage`, `.model_usage`, `.total_cost_usd`, `TaskUsage` | R |
| `get_claude_session_cost(handle)` | `total_cost_usd`; ⚑ `get_session_cost` | R |
| `plan_claude_fan_out(n)`: how many sessions fit before the limit | `RateLimitInfo.utilization`, `resets_at` | R |
| ★ `launch_claude_subagents(prompts, request, limit)`: Vidbyte runs exactly N sessions or forks | spawn / fork × N | W |

**MCP**
| Function | Backed by | Tool |
|---|---|---|
| `list_claude_mcp_servers(handle)`: connected / failed / needs-auth / pending / disabled, with their tools | `get_mcp_status()`; without a session, `claude mcp list / get` | R |
| `set_claude_mcp_servers(handle, servers)`: add or remove servers mid-session | ⚑ `mcp_set_servers` | W |
| `reconnect_claude_mcp_server(handle, name)`, `toggle_claude_mcp_server(handle, name, on)` | `reconnect_mcp_server()`, `toggle_mcp_server()` | W |
| `read_claude_mcp_resource(handle, server, uri)` | ⚑ `readMcpResource` | R |
| `add_claude_mcp_server(name, transport, target, scope, headers, env)` | `claude mcp add / add-json` | ✗ |
| `remove_…`, `login_…`, `logout_claude_mcp_server(name)` | `claude mcp remove / login / logout` | ✗ |
| `reset_claude_mcp_project_choices()` | `claude mcp reset-project-choices` | ✗ |

**Plugins, marketplaces, importing from other harnesses**
| Function | Backed by | Tool |
|---|---|---|
| `list_claude_plugins()` | `claude plugin list` | R |
| `get_claude_plugin_details(name)`: its components and projected token cost | `claude plugin details` | R |
| `validate_claude_plugin(path)`, `test_claude_plugin(dir)` | `claude plugin validate / test` | R |
| `eval_claude_plugin(target, eval_dir)`: graded eval cases plus a run without the plugin for comparison | `claude plugin eval` | W |
| `install / uninstall / enable / disable / update / prune_claude_plugin` | `claude plugin …` | ✗ |
| `configure_claude_plugin(name, values)`, `scaffold_claude_plugin(name)`, `tag_claude_plugin_release(path)` | `claude plugin configure / init / tag` | ✗ |
| `list_claude_marketplaces()`; add / remove / update | `claude plugin marketplace …` | R / ✗ |
| `import_into_claude(source, dry_run)`: bring Codex, Gemini or Cursor config into Claude Code | `claude import codex / gemini / cursor` | R (dry run) / ✗ |

**Cloud, remote, review**
| Function | Backed by | Tool |
|---|---|---|
| `create_claude_cloud_session(description, environment)` | `--cloud`, `--environment ccpool_…` (self-hosted) | W |
| `attach_claude_cloud_session(id_or_url)` (verify it works without a terminal) | `--cloud <id or url>` | W |
| `teleport_claude_session(session)`: bring a cloud session to this machine | `--teleport` | W |
| `run_claude_ultrareview(target, post, timeout)`: multi-agent review in the cloud, returns `bugs.json` | `claude ultrareview --json [--post] [--timeout]` | W |
| `start_claude_remote_control(name)` | `--remote-control` | ✗ |
| `run_claude_gateway(config)` | `claude gateway` | ✗ |

**Left out on purpose:**
- `attach` needs an interactive terminal.
- `--desktop`, `--ide`, `--chrome`, `--tmux` and `--ax-screen-reader` are for a human at a terminal.
- The `readFile` control request duplicates `vidbyte/tools/filesystem/`.
- `onElicitation` and `onUserDialog` exist only in TypeScript; Python doesn't route those requests (verify).
- `mcp add-from-claude-desktop` only works on Mac and WSL.

## CodexHost: full list (refreshed)

**Spawn request fields (`CodexSpawnRequest`)**
- **Input:** `prompt` (text, local or remote images, skills, mentions via `CodexRunInput`), `cwd`
- **Model:** `model`, `model_provider`, `effort`, `summary`, `service_tier`, `personality`
- **Instructions:** `developer_instructions`, `base_instructions` (replaces Codex's own base prompt)
- **Sandbox and approvals:** `sandbox`, `approval_policy`, `approvals_reviewer` (user / auto_review / guardian_subagent)
- **Extensions:** `tools` (dynamic tools, fixed once the thread starts), `disabled_plugin_ids` (per turn), `config` (MCP servers, `agents.*` for native subagents, and other thread config), `config_overrides`
- **Budgets:** `goal` (objective + `token_budget`), `max_output_tokens` (enforced by our interrupt), `timeout_seconds`
- **Session:** `name`, `ephemeral`, `service_name`, `thread_source`, `session_start_source`
- **Output:** `output_schema`
- **Process:** `codex_bin` (default: the user's installed `codex`, as the ensemble does), `env`, `experimental_api`

**Readiness and account**
| Function | Backed by | Tool |
|---|---|---|
| ★ `check_codex_ready()`: binary, version, login, Windows sandbox | `initialize`, `account/read`, `windowsSandbox/readiness` | R |
| `get_codex_version()`, `run_codex_doctor()` | `initialize` metadata, `codex doctor` | R |
| `update_codex()` | `codex update` | ✗ |
| `get_codex_account()`: login type, plan | `account/read` | R |
| ★ `get_codex_rate_limits()`: usage windows, reset times, whether normal usage is allowed | `account/rateLimits/read` | R |
| `get_codex_account_usage()`, `read_codex_workspace_messages()` | `account/usage/read`, `account/workspaceMessages/read` | R |
| `login_codex_api_key`, `start_codex_chatgpt_login`, `start_codex_device_login`, `cancel_codex_login`, `logout_codex` | `account/login/*`, `account/logout` | ✗ |
| `login_codex_gateway_oauth`, `read_…`, `cancel_…` | `account/gatewayOAuth/*` | ✗ |
| `setup_codex_windows_sandbox()` | `windowsSandbox/setupStart` | ✗ |
| ★ `list_codex_models(include_hidden)` | `model/list` | R |
| `get_codex_provider_capabilities()` | `modelProvider/capabilities/read` | R |
| `list_codex_features()`, `set_codex_feature(name, on)` | `experimentalFeature/list`, `experimentalFeature/enablement/set` | R / ✗ |

**Threads**
| Function | Backed by | Tool |
|---|---|---|
| ★ `spawn_codex_thread(request)` | `thread/start` + `turn/start` | W |
| ★ `continue_codex_thread(thread_id, input, overrides)` | `thread/resume` + `turn/start` | W |
| ★ `fork_codex_thread(thread_id, from_turn_id, exclude_turns, overrides)` | `thread/fork` | W |
| `fork_codex_thread_many(thread_id, prompts)` | `thread/fork` × N | W |
| `find_or_spawn_codex_thread(name)` | `thread/list` search, then resume or start | W |
| `revert_codex_thread(thread_id, before_turn_id)` | `thread/revert` | W |
| `compact_codex_thread(thread_id)` | `thread/compact/start` | W |
| `rename_codex_thread`, `set_codex_thread_git_info` | `thread/name/set`, `thread/metadata/update` | W |
| `archive_codex_thread`, `unarchive_codex_thread` | `thread/archive`, `thread/unarchive` | W |
| `delete_codex_thread` | `thread/delete` | ✗ |
| ★ `list_codex_threads(cwd, search, archived, source_kinds, sort, cursor)` | `thread/list` | R |
| ★ `read_codex_thread(thread_id, include_turns)` | `thread/read` | R |
| `list_codex_turns`, `list_codex_items` | `thread/turns/list`, `thread/items/list` | R |
| `export_codex_transcript(thread_id)` → Markdown or handoff | the two above | R |
| `list_loaded_codex_threads()` | `thread/loaded/list` | R |
| `unsubscribe_codex_thread(thread_id)` | `thread/unsubscribe` | internal |
| `list_codex_daemon_sessions()`: sessions on the shared local daemon (experimental) | `codex agents` | R |
| `migrate_codex_rollouts()` | `codex migrate-rollouts` | ✗ |

**Live turn control (only through the `CodexHost` that started the turn)**
| Function | Backed by | Tool |
|---|---|---|
| ★ `wait_codex_turn(handle, timeout)`, `get_codex_turn_result(handle)` | `TurnHandle.run()`, `turn/completed` | R |
| ★ `steer_codex_turn(handle, input)` | `turn/steer` with `expected_turn_id` | W |
| ★ `interrupt_codex_turn(handle)` | `turn/interrupt` | W |
| `stream_codex_turn(handle)` | `TurnHandle.stream()` | R |
| `get_codex_turn_diff(handle)`, `get_codex_turn_plan(handle)` | `turn/diff/updated`, `turn/plan/updated` | R |
| `inject_codex_items(thread_id, items)` | `thread/inject_items` | W |
| `run_codex_thread_shell(thread_id, command)` | `thread/shellCommand` | W |
| `queue_codex_message(session, text)` | `codex queue` | W |
| `set_codex_approval_handler(callback)` | server requests `item/commandExecution/requestApproval`, `item/fileChange/requestApproval` | ✗ |
| `approve_codex_guardian_denied(thread_id, event)` | `thread/approveGuardianDeniedAction` | ✗ |

**Goals, usage, subagents, review**
| Function | Backed by | Tool |
|---|---|---|
| `set_codex_goal(thread_id, objective, token_budget)` | `thread/goal/set` | W |
| `get_codex_goal`, `pause_codex_goal`, `clear_codex_goal` | `thread/goal/get`, `goal/set` (paused), `thread/goal/clear` | R / W |
| `cap_codex_tokens(handle, max_output_tokens)` | `thread/tokenUsage/updated` → `turn/interrupt` | internal |
| ★ `track_codex_thread_usage(thread_id)` | `thread/tokenUsage/updated` + `CodexMetricsTranslator` | R |
| `get_codex_turn_usage(handle)`, `plan_codex_fan_out(n)` | turn result, `account/rateLimits/read` | R |
| ★ `launch_codex_subagents(prompts, request, limit)` | `thread/start` / `thread/fork` × N | W |
| `list_codex_subagent_threads(parent)` | `thread/list` filtered to subagent kinds | R |
| ★ `start_codex_review(thread_id, target, delivery)` | `review/start` | W |
| `run_codex_review_cli(target)` | `codex review` | W |

**Deterministic operations through Codex (no model turn)**
| Function | Backed by | Tool |
|---|---|---|
| `exec_in_codex_sandbox(command, cwd, sandbox_policy, timeout_ms, env)`, plus write / resize / terminate | `command/exec*`, `codex sandbox` | W |
| `call_codex_mcp_tool(thread_id, server, tool, args)` | `mcpServer/tool/call` | W |
| `read_codex_mcp_resource(server, uri)` | `mcpServer/resource/read` | R |
| `fuzzy_find_codex_files(query, roots)` | `fuzzyFileSearch` | R |

**MCP, skills, plugins, apps, hooks, config**
| Function | Backed by | Tool |
|---|---|---|
| `list_codex_mcp_servers()`, `reload_codex_mcp_servers()` | `mcpServerStatus/list`, `config/mcpServer/reload` | R / W |
| `login_codex_mcp_oauth(server)`, `add_codex_mcp_server`, `remove_codex_mcp_server` | `mcpServer/oauth/login`, `codex mcp`, `config/value/write` | ✗ |
| `list_codex_skills(cwds)`, `add_codex_skill_roots(paths)` | `skills/list`, `skills/extraRoots/set` | R / W |
| `configure_codex_skill(...)` | `skills/config/write` | ✗ |
| `list_codex_plugins`, `list_installed_codex_plugins`, `read_codex_plugin`, `read_codex_plugin_skill` | `plugin/list`, `plugin/installed`, `plugin/read`, `plugin/skill/read` | R |
| `install / uninstall / reconcile_codex_plugin`, `add / remove / upgrade_codex_marketplace` | `plugin/*`, `marketplace/*`, `codex plugin` | ✗ |
| `list_codex_apps`, `read_codex_app`, `list_codex_hooks()` | `app/list`, `app/installed`, `app/read`, `hooks/list` | R |
| `read_codex_config(cwd, include_layers)`, `read_codex_config_requirements()` | `config/read`, `configRequirements/read` | R |
| `write_codex_config(key, value)`, batch version | `config/value/write`, `config/batchWrite` | ✗ |
| `list_codex_permission_profiles(cwd)` | `permissionProfile/list` | R |
| `detect_external_agent_config()`, `import_external_agent_config()` (verify what they import) | `externalAgentConfig/*` | R / ✗ |

**Organizing, linking, cloud, remote**
| Function | Backed by | Tool |
|---|---|---|
| `create / list / update / delete_codex_section`, `move_codex_thread_to_section` | `threadSection/*`, `thread/section/move` | W |
| `attach_to_codex_thread`, `list_codex_thread_attachments`, `remove_codex_thread_attachment`, `list_codex_attachment_owners` | `thread/attachment/*`, `thread/attachmentOwner/list` | W / R |
| `submit_codex_cloud_task(env, prompt)` | `codex cloud exec` | W |
| `get_codex_cloud_task_status`, `list_codex_cloud_tasks`, `get_codex_cloud_task_diff` | `codex cloud status / list / diff` | R |
| `apply_codex_cloud_task(task_id)`, `apply_latest_codex_diff()` | `codex cloud apply`, `codex apply` | W |
| `start_codex_remote_control()`, `run_codex_exec_server()` (experimental) | `codex remote-control`, `codex exec-server` | ✗ |

**Left out on purpose:**
- `fs/*` duplicates `vidbyte/tools/filesystem/`.
- `thread/realtime/*` is audio.
- `feedback/upload`, `plugin/share/*`, `codex app / completion / debug` aren't useful to an agent.
- `account/sendAddCreditsNudgeEmail` sends the user an email.
- `account/rateLimitResetCredit/consume` spends plan credits, so it must never be a tool.

## One error vocabulary for both hosts

Each code is `<host>.<problem>`, so cross-harness code can branch on the problem without caring which host raised it.

| Problem | Codex detects it via | Claude detects it via | Next step the agent is told |
|---|---|---|---|
| `not_installed` | `codex_bin` / PATH, SDK import | `CLINotFoundError` | install it, or pass the binary path |
| `version_unsupported` | `initialize` metadata | `initialize` → `claude_code_version` | `codex update` / `claude update` |
| `not_signed_in` | `account/read` | `claude auth status`, `account.tokenSource` | `codex login` / `claude auth login` |
| `auth_mode_unsupported` | Cloud needs a ChatGPT login | `bare` needs `ANTHROPIC_API_KEY`; `betas` work with API keys only; `setup-token` needs a subscription | switch login type |
| `usage_limited` | `account/rateLimits/read` | `RateLimitEvent` rejected + `resets_at`; assistant error `rate_limit` | wait until the reset time, or use an API key |
| `billing_error` | turn error | assistant error `billing_error` | add credits |
| `model_unknown` | `model/list` | `initialize` → `models` | pick from the returned list |
| `session_not_found` | `thread/read` | `get_session_info()` returns `None` | `list_*` to find it |
| `session_busy` | the host's list of running turns | the host's list of live clients | steer it, or fork it |
| `budget_exhausted` | goal `budgetLimited`, our token cap | `ResultError` `error_max_budget_usd` / `error_max_turns` | raise the budget, or split the work |
| `api_error` | `turn/failed` | `terminal_reason == "api_error"` (overloaded, timeout) | retry with backoff |
| `permission_denied` | approval declined | `ResultMessage.permission_denials` | allow the tool, or change the permission mode |
| `mcp_server_failed` | `mcpServerStatus/list` | MCP status `failed` / `needs-auth` | log in to the MCP server |
| `checkpointing_disabled` | none | `rewind_files` without checkpointing | respawn with `enable_file_checkpointing` |
| `sandbox_not_ready` | `windowsSandbox/readiness` | none | `setup_codex_windows_sandbox` |
| `schema_violation` | our local check | `structured_output` missing | run a repair turn using the raw text |
| `process_exited` | the app-server exits | `ProcessError(exit_code, stderr)` | respawn, then resume by id |
| `protocol_mismatch` | the SDK rejects the translated content | `CLIJSONDecodeError`, `MessageParseError` | align the SDK and CLI versions |

`★ Insight ─────────────────────────────────────`
- **Two levels of errors on Claude.** `ResultError` carries `subtype` (`error_max_turns`, `error_max_budget_usd`, `error_during_execution`) and `terminal_reason` (`api_error`, …), and assistant messages carry their own error kinds (`authentication_failed`, `billing_error`, `rate_limit`, …). So Claude needs no string matching. Codex needs our own sorting, because only some of its failures have structured codes.
- **Claude reports permission denials explicitly.** `ResultMessage.permission_denials` lists every tool call that was refused. That's what makes "allow the tool or change the mode" a precise next step instead of a guess.
`─────────────────────────────────────────────────`

## What could go wrong with ClaudeHost (Codex's list from last turn still applies)

- **Memory per process.** 7 parallel sessions means 7 `claude` processes (the binary alone is 260 MB on disk). Measure memory per process before picking the concurrency cap.
- **Shared plan window.** On the user's claude.ai login, every spawned session draws from the same five-hour and seven-day windows as their own interactive Claude Code sessions, including this one. `plan_claude_fan_out` reads `utilization` before fanning out, and a `RateLimitEvent` with status `allowed_warning` stops new spawns.
- **Two writers on one session.** Two processes resuming the same session id both append to one transcript. The host refuses `continue` while a live handle exists, returns `claude.session_busy`, and suggests a fork.
- **Config that fails to load gives no error.** The `-p` help text says print mode skips the workspace-trust dialog and silently ignores settings files that fail validation. Put `hooks_applied` and `plugins_applied` from the `initialize` result on every handle, so callers can see what actually loaded. Also check whether SDK sessions run in the same mode.
- **⚑ functions depend on a private method.** An SDK upgrade can break them without any error at import. Pin the SDK version exactly and give each one a contract test. This is the same pattern as the Codex tool bridge, which depends on private attributes under its `<0.163` pin.
- **Permission escalation.** A model-callable `set_claude_permission_mode` could switch a child session to `bypassPermissions`, so it stays a plain function (✗). `restricted` mode refuses bypass outright.

**To verify before relying on them:**
- **Claude:** whether `client.query()` mid-turn queues the message or starts a new turn; slash commands sent as prompts; the max-output-token environment variable; the environment variables for Bedrock, Vertex and Foundry; `--cloud <id>` without a terminal; what `ultrareview` requires and costs.
- **Codex:** what `thread/revert` undoes, and what `externalAgentConfig/*` imports.

Checked:
- **Claude Code 2.1.296:** `claude --help`, plus help for agents, auth (login, status), auto-mode, import, ultrareview, purge, respawn, install, gateway, doctor, setup-token, logs, attach, mcp (and mcp add), plugin (and plugin marketplace).
- **claude-agent-sdk 0.2.165 source:** `__init__` exports, `types.py`, `client.py`, `_internal/query.py` (`_send_control_request`), `sessions.py`, `session_mutations.py`, `_errors.py`, `subprocess_cli.py` (`_find_cli`), `_cli_version.py`.
- **@anthropic-ai/claude-agent-sdk 0.3.296:** `sdk.d.ts` (Query methods, Options, `HOOK_EVENTS`, control subtypes, `AccountInfo`, `ModelInfo`, the `initialize` response) and `sdk-tools.d.ts`.
- **The Claude binary:** control-request names.
- **Codex:** `codex --help`, plus openai-codex 0.162.1 from last turn.

Rejected:
- **A function per setting** (`set_claude_max_turns` and so on): these are spawn-request fields; such a function only forwards one option.
- **A shared base class in PR 1:** it would have only one implementation; extract it once ClaudeHost exists.
- **The SDK's bundled Claude CLI as the default:** it differs from the user's install, which has their login, plugins and settings.

---
**Re-entry · harness-thread vocabulary**

Decided:
- **Where it lives:** in the SDK. Functions go in `vidbyte/harnesses/native/<host>/`, one tool per function in `vidbyte/tools/builtins/<host>/`, bundled in `toolsets/<host>.py`, and exposed over MCP through `mcp_server/`. Both hosts use their official SDK (openai-codex, claude-agent-sdk); features that only exist in a CLI run the CLI.
- **One host class per harness:** each owns its live processes and handles. Spawn returns a handle immediately, settings are spawn-request fields, and the existing Codex settings are reused.
- **Shared vocabulary:** shared verbs for cross-harness code, plus one `<host>.<problem>` error vocabulary with next steps. Tools return error results instead of raising.
- **Budgets:** Codex uses a goal budget plus our interrupt; Claude uses its built-in `max_budget_usd`, `max_turns`, `task_budget` and thinking budget.
- **⚑ group:** the TypeScript-only Claude controls are reachable from Python only through a private method (decision pending, below).

Open:
- The verify items above.
- The policy on plan-backed (subscription) usage in a paid product, for both OpenAI and Anthropic.

Needs you:
1. Should the ⚑ functions wait until the Python SDK exposes them? Building them now means using the private call under an exact pin plus contract tests. Default: leave them out of the first PRs.
2. Should PR 1 contain only CodexHost's ★ set, with PR 2 adding ClaudeHost's ★ set and extracting the shared pieces (error envelope, tool base, handle registry)? Default: yes.
3. Should both hosts default to the user's installed binary (`codex_bin` / `cli_path`, with a minimum-version check) instead of the SDK's bundled one? Default: yes.

*Reply "go" to accept all defaults.*

Next: on "go", I write the HANDOFF for PR 1: CodexHost's 14 ★ functions, their tools, the error mapper and contract tests.
`````
