---
slug: coding-agent
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-10 00:51
flags: none
---

# Request: CodingAgent — a minimal BaseAgent with seven file-system and web tools

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (opening request, before any analysis):

````
I want to make a CodingAgent class inside of the vidbyte-sdk/. i want to make it inside of the vidbyte/agents folder, and just create a new CodingAgent class. Under the hood, i want it to be a BaseAgent, have the same settings and functionality as it, but just add the following tools: Bash, Edit, WebFetch (can change provide based on key), Glob. A very minimalistic coding agent that has all of the tools to interact with the file system. Can you do 2 things: 1) create a checklist of any other tools that are absolutely necessary for a coding agent to have (dont want to add a lot, just want to add the main coding agents tools that i might have missed and 2) create a checklist of all the things we have to think about/do for the implementation of this feature in teh vidbyte-sdk/ repo
````

**Prompt 2** (the invocation of this pipeline, sent after the assistant answered Prompt 1 with two checklists and five open decisions, summarized in §C):

````
the 7 tools sound good, and you can fetch the keys from the parameter. for bash I dont want to use the sandbox, just implement a miniamlistic subprocess bash, no default system prompt, tool names I dont care.
````

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### What the assistant told the user between Prompt 1 and Prompt 2 (the user replied to this)

The assistant answered Prompt 1 after reading the repo. Its answer, condensed:

- **Missing tools checklist.** Add **Read** (Edit needs exact current text; Glob returns only paths; without Read the model must `cat` through Bash), **Write** (both existing edit tools refuse to create new files), and **Grep** (content search; Glob is name search; works when Bash is denied and on Windows where grep is absent). Explicitly *not* added: web search, todo list, multi-edit, list-directory, notebook edit. Resulting set of **seven tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch** — the same core set Claude Code uses.
- **Existing tools found in the repo** (the assistant's map; verify each):
  - Glob → `GlobTool(root_dir)` in `vidbyte/tools/builtins/code_search/glob.py` (model-facing name `glob`, permission READ).
  - Grep → `GrepTool(root_dir)` in `vidbyte/tools/builtins/code_search/grep.py` (name `grep`).
  - Read → `ReadLinesTool` (`read_lines`, line ranges) / `ReadTextTool` (`read_text`) in `vidbyte/tools/filesystem/`, constructed from `FileSystemToolConfig` (`vidbyte/lib/dataclasses/filesystem.py:27`: `root`, `allow_write=False`, `encoding`, `platform`, `backend`).
  - Write → `WriteTextTool` (`write_text`) in `vidbyte/tools/filesystem/write_text.py`.
  - Edit → two candidates: `ReplaceTextTool` (`replace_text`, `vidbyte/tools/filesystem/replace_text.py`, `FileSystemToolConfig`, exact-once replacement, WRITE) and `PatchTool` (`patch_file`, `vidbyte/tools/builtins/editing/patch.py`, its own `root_dir`, returns a unified diff, WRITE).
  - WebFetch → six fetch tools in `vidbyte/tools/builtins/operations/fetch.py`: `FirecrawlFetchTool`, `BrowserbaseFetchTool`, `ParallelExtractTool`, `TavilyExtractTool`, `LinkupFetchTool`, `DirectHttpFetchTool`. All subclass `PricedOperationTool(client=...)` (`operations/base.py:42`). Only `DirectHttpFetchTool` performs a real fetch with no client and no key; the keyed ones return a priced contract **stub** when no client is injected (e.g. `fetch.py` around line 67, `if self._client is None: return self._contract_result(...)`). Provider clients live in `vidbyte/tools/builtins/operations/clients/` (e.g. `FirecrawlClient(api_key, ...)`).
  - Bash → **does not exist** anywhere in `vidbyte/`. Must be built.
- **Implementation checklist the assistant raised** (the user answered some of these in Prompt 2):
  - Default `PermissionPolicy()` allows only `SAFE` and `READ` (`vidbyte/lib/dataclasses/security.py:33`); `PermissionPolicy.allow_all()` exists. With BaseAgent defaults, Edit/Write (WRITE) and Bash (EXECUTE) would be denied. CodingAgent must default to a policy that lets its own tools run, while still accepting a caller's stricter policy. `FileSystemToolConfig.allow_write=True` is a second, independent switch for Write/Edit.
  - Bash is not root-scoped the way the filesystem tools are (they reject paths outside the root; a shell can `cd ..`). Document it.
  - `AgentFork.fork` constructs a plain `BaseAgent(...)` (`vidbyte/agents/fork.py:43`): a fork keeps the tools and policy but is not a `CodingAgent` instance.
  - JevAgent rejects specialists whose `generate_reply` is overridden (`vidbyte/agents/jev/agent.py`, `_require_metered_specialists`); CodingAgent must not override it.
  - Exports: `vidbyte/agents/__init__.py`, `vidbyte/__init__.py` (JevAgent is exported there), `vidbyte/tools/builtins/__init__.py`; regenerate `contracts/sdk-public-api.json` with `python scripts/generate-sdk-public-api.py` after committing the `vidbyte/__init__.py` change (lint C016).
  - Repo placement rules (dataclasses, enums, constants under `vidbyte/lib/`), lint rules (A001 headers, A002 intent comments, A003 error packets, A007 constants, A008 no stdout, S006 async task ownership, S012 explicit timeout, S013 bounded responses, S015 export integrity), REPO_MAP.md and `vidbyte/agents/README.md` entries, tests, `python scripts/run_ci.py`.
- **Five open decisions the assistant asked the user**: (1) ReplaceTextTool or PatchTool for Edit; (2) fetch keys from a parameter or env vars; (3) Bash shell on Windows, and SandboxTransport now or later; (4) a default system prompt or required from caller; (5) stable tool names or existing ones.

### Key decisions
- **Seven tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch.** — User: "the 7 tools sound good". No other tools.
- **CodingAgent is a BaseAgent, in `vidbyte/agents/`, with the same settings and functionality as BaseAgent, plus the tools.** — Prompt 1: "Under the hood, i want it to be a BaseAgent, have the same settings and functionality as it, but just add the following tools".
- **WebFetch provider is chosen by which API key is supplied, and keys come from a constructor parameter, not from environment variables.** — Prompt 1 "(can change provide based on key)"; Prompt 2 "you can fetch the keys from the parameter".
- **Bash is a minimal subprocess implementation and does not use `SandboxTransport`.** — Prompt 2: "for bash I dont want to use the sandbox, just implement a miniamlistic subprocess bash".
- **No default system prompt.** The caller supplies `system_prompt` exactly as with BaseAgent (which rejects an empty one). — Prompt 2: "no default system prompt".
- **Tool names: the user does not care.** — Prompt 2: "tool names I dont care". Consequence for scope: keep the existing model-facing names; do not build a renaming/wrapping layer (it was offered as an option and not asked for).
- **Very minimal.** — Prompt 1: "A very minimalistic coding agent".

### Rejected alternatives
- Running Bash through the existing unused `SandboxTransport` protocol (`vidbyte/lib/dataclasses/sandbox.py`) — rejected by the user ("I dont want to use the sandbox").
- Reading fetch API keys from environment variables — rejected; keys come from the parameter.
- Shipping a default coding system prompt — rejected ("no default system prompt").
- Wrapping tools under stable names like `web_fetch` / `edit` — not requested ("tool names I dont care"); not built.
- Adding tools beyond the seven (web search, todo list, multi-edit, list-dir, notebook edit) — the assistant recommended against; the user accepted the seven.
- A JevAgent-style closed settings object — inference from "have the same settings and functionality as it": CodingAgent should accept BaseAgent's construction surface, not a narrowed one. (Inference by the orchestrator; the user did not address it directly.)

### Constraints and assumptions
- Target repo is `vidbyte-sdk`; code goes under `vidbyte/agents/` (Prompt 1).
- Every AGENTS.md placement rule and lint rule applies; full gate `python scripts/run_ci.py` before complete.
- The user's machine is Windows 11 (win32); Git Bash is installed there. CI also runs (see `.github/workflows/`), on whatever OS the workflow specifies — unverified.
- Assumption (forced by the request, not discussed further): the agent's own WRITE and EXECUTE tools must actually be permitted to run by default, otherwise "add the following tools" would yield tools that are always denied.

### Clarifications and answers
- Q: Which other tools are absolutely necessary? — A (assistant): Read, Write, Grep. User: "the 7 tools sound good".
- Q: Fetch keys from a parameter or env vars? — A: "you can fetch the keys from the parameter".
- Q: Which shell for Bash, and use the sandbox protocol now or later? — A: "for bash I dont want to use the sandbox, just implement a miniamlistic subprocess bash". (Which executable on Windows was not answered.)
- Q: Default system prompt or required? — A: "no default system prompt".
- Q: Stable tool names or existing ones? — A: "tool names I dont care".
- Q: ReplaceTextTool or PatchTool for Edit? — **not answered.** The assistant recommended `ReplaceTextTool`, so Read/Write/Edit share one `FileSystemToolConfig` and one `allow_write` switch.

### Terminology
- **CodingAgent** — the new class; a `BaseAgent` subclass that comes pre-loaded with the seven tools.
- **The seven tools** — Bash, Read, Write, Edit, Glob, Grep, WebFetch (conceptual names; the model-facing names are whatever the underlying tool classes already declare, plus whatever the new Bash tool declares).
- **WebFetch "provider based on key"** — the fetch tool attached to the agent is the one whose provider matches the API key the developer passed; with no key, the key-free `DirectHttpFetchTool`.
- **"subprocess bash"** — a tool that runs one shell command via Python's subprocess machinery and returns its output; no sandbox.
- **BaseAgent** — `vidbyte/agents/base.py`, class `BaseAgent`, keyword-only `__init__` at line 79.

### Implementation hints
- Subclass pattern to study: `vidbyte/agents/jev/agent.py` (`JevAgent(BaseAgent)` calls `super().__init__(...)`). Note JevAgent deliberately *narrows* the surface; CodingAgent should not.
- BaseAgent constructor: `vidbyte/agents/base.py:79-113` (name, system_prompt, runtime, tools, permission_policy, agent_loop_settings, …, api_key, provider, model_name, …, fallback).
- Tool constructors: `GlobTool(root_dir)`, `GrepTool(root_dir)` (`BaseCodeSearchTool.__init__` in `vidbyte/tools/builtins/code_search/base.py`); filesystem tools take `FileSystemToolConfig`; `PatchTool(root_dir)`; fetch tools take `client=`.
- Fetch clients: `vidbyte/tools/builtins/operations/clients/` (`brave.py`, `browserbase.py`, `exa.py`, `firecrawl.py`, `parallel.py`, `tavily.py`, `_base.py` with `WebOperationClient(api_key, ...)`). Linkup has a fetch tool but check whether a Linkup client exists.
- Permission: `PermissionPolicy` and `allow_all()` in `vidbyte/lib/dataclasses/security.py`; `ToolPermission` (SAFE/READ/WRITE/EXECUTE) in `vidbyte/lib/dataclasses/tools.py:47`.
- Tool base: `vidbyte/tools/base.py` (`BaseTool`), `vidbyte/tools/types.py` (`ToolSpec`, `ToolParameter`, `ToolCall`, `ToolResult`).
- Similar fetch-tool precedent for a no-key real fetch: `DirectHttpFetchTool` in `fetch.py`.
- Things not to touch: `SandboxTransport` (user said no sandbox); no default prompt files.
- Workspace gotchas (from the orchestrator's memory of earlier runs in this repo): running `scripts/run_ci.py` with `PYTHONPATH` set breaks the package smoke step; Semgrep needs its own venv/pipx because the SDK pulls `mcp` 2.x; vidbyte-sdk CI does not trigger automatically — `ci.yml` must be dispatched manually per branch (`gh workflow run ci.yml --ref <branch>`) or PR checks never appear.

### Open questions
- Edit tool: `ReplaceTextTool` (recommended, unanswered) vs `PatchTool`.
- WebFetch: exact parameter shape for the key(s); which keyed providers are supported (Firecrawl, Browserbase, Parallel, Tavily, Linkup — check which have clients and what each client needs besides a key); what happens when more than one key is passed; no key → `DirectHttpFetchTool`.
- Bash: which executable on Windows vs POSIX for "bash"; working directory; timeout and output limits (lint S012/S013 may force them); exit code and stderr in the result.
- How the caller's own `tools=` combine with the seven, and what a duplicate name does.
- Name of the working-folder parameter (e.g. `root_dir`) and whether it is required.

## D. Weighted words

- "just create a new CodingAgent class" — Prompt 1
- "have the same settings and functionality as it, but just add the following tools" — Prompt 1
- "A very minimalistic coding agent that has all of the tools to interact with the file system." — Prompt 1
- "any other tools that are absolutely necessary for a coding agent to have (dont want to add a lot, just want to add the main coding agents tools that i might have missed" — Prompt 1
- "create a checklist of all the things we have to think about/do" — Prompt 1
- "for bash I dont want to use the sandbox, just implement a miniamlistic subprocess bash" — Prompt 2
- "no default system prompt" — Prompt 2
