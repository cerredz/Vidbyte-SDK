---
slug: codex-host-thread-helpers
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-thread-helpers
branch: feat/codex-host (existing PR #1055, draft)
invoked: 2026-10-15 22:30 UTC
flags: none (existing-PR run: no new branch, no new PR; adds to PR #1055)
---

# Request: CodexHost thread helpers and built-in skill functions

This run adds the Codex half of a cross-harness catalog of thread helpers and built-in skill functions to the EXISTING open draft PR #1055 (https://github.com/cerredz/Vidbyte-SDK/pull/1055, "feat(harnesses): add CodexHost with one agent tool per Codex function", branch `feat/codex-host`, author cerredz = the user, base `main`). A sibling pipeline adds the same catalog for Grok, opencode and Muse on a different branch (`feat/harness-thread-helpers-skills`). The conversation below happened in the parent session; Prompts 1-5 were about PR #1036 (Grok/opencode/Muse thread functions, merged to main as f216fdcf), and Prompt 6 asked for this run on PR #1055. Section E holds the catalog reply the user accepted (Prompt 5 refers to it as "all of these helper functions/skill functions").

## A. Every user prompt in this conversation, verbatim and in order

All on 2026-10-15, times UTC.

**Prompt 1** (21:40):
pr #1036 question for the vidbyte-sdk/, do you think that there are any  simple functions that we missed out on implementng  for each harness, given what is possible with each?

**Prompt 2** (21:41, sent mid-turn):
like besides just "continue, fork, and run" grok threads, are these any simple actions inside of grok build that exist that we should add as functions inside of  this pr?

**Prompt 3** (21:46):
No this is not what i am talking about, what i am talking about is actually using the capabilities of grok build AND also maybe adding some helper functions (view recent sessions, view sessions in last N time period, etc).

**Prompt 4** (22:02):
I like all of your thread helpers, can you list out all of the thread helpers for each harness. And also, maybe for the goal/deep research functions we have a function like: "run_grok_goal" that simply runs the user's request with the built in "/goal" skill attached to their prompt. If so, can you like all of the functions like this using each harnesses "built in" first-class skills?

**Prompt 5** (22:11, /spec-pipeline args):
great, can you implement all of these helper functions/skill functions in grok, opencode, muse, and whichever other harnesses we have in the repo/sdk. Make sure the local main is up to date as we recently merged pr 1036 into main

**Prompt 6** (~22:25, sent mid-turn):
note, ccan you also in a subagent launch this "spec-pipeline" process for pr #1055 and explain the changes that we want to make with the implementation of the existing pr

## B. Handoff block and decision ledger (verbatim, if present)

none

## C. Structured conversation notes

### What PR #1055 is today (before this run)
- `CodexHost` is an async context manager in `vidbyte/harnesses/native/codex/host.py` (771 lines at 66558ee9) that drives one `codex app-server` through openai-codex 0.162.1's sync `CodexClient`. It exposes 15 functions: `check_codex_ready`, `get_codex_rate_limits`, `list_codex_models`, `spawn_codex_thread`, `continue_codex_thread`, `fork_codex_thread`, `list_codex_threads(cwd, search, archived, source_kinds, sort)`, `read_codex_thread(thread_id, include_turns)`, `wait_codex_turn`, `get_codex_turn_result`, `steer_codex_turn`, `interrupt_codex_turn`, `track_codex_thread_usage`, `launch_codex_subagents`, `start_codex_review`.
- Every function is also exactly one READ or WRITE agent tool in `CodexHostTools` (`vidbyte/tools/builtins/codex/`, `vidbyte/tools/toolsets/codex.py`). That one-tool-per-function rule is the PR's own invariant.
- Failures are `CodexAgentError` with `codex.*` FailureCodes and a next step.
- PR #1055's own catalog lives at `docs/spec/codex-host/request.md` (unstarred rows were deferred; it marks delete as ✗ = plain function, never an agent tool). Its spec, test plan, review and PR body are under `docs/spec/codex-host/`.
- PR #1055's S6 notes say openai-codex 0.162.1 lacks high-level calls for several app-server methods, so the PR sends them through its own wire layer (`vidbyte/harnesses/native/codex/wire.py`, `connection.py`).

### The changes we want made to PR #1055 (the spec author owns the final list)
Add, as the Codex half of the cross-harness catalog (names follow the existing host's `<verb>_codex_...` style; reuse an existing function instead of duplicating it):

1. Thread helpers
   - `list_recent_codex_threads(cwd, limit)` → `thread/list` with sortKey `updated_at`, sortDirection desc.
   - `list_codex_threads_since(cwd, since, limit)` → same, paging `nextCursor` and stopping at the first `updatedAt` older than `since` (thread/list has NO server-side time filter in 0.162.1; verify against the schema).
   - `get_codex_thread_lineage(thread_id)` → walk `Thread.forkedFromId` (fork parent) and `Thread.parentThreadId` (subagent parent) via `thread/read`.
   - `search_codex_threads(cwd, query)` → `thread/list` `searchTerm`. The existing `list_codex_threads(search=...)` may already cover it; the spec decides between a thin same-named wrapper (for cross-harness name parity: the sibling PR ships `search_grok_threads`, `search_opencode_threads`) or reuse.
   - `compact_codex_thread(thread_id)` → `thread/compact/start` (WRITE tool).
   - `delete_codex_thread(thread_id)` → `thread/delete`. PR #1055's own catalog marks delete as ✗ = plain function, never an agent tool. Keep that.
   - "get" and "read transcript": the existing `read_codex_thread(include_turns=False/True)` may already cover both. If `include_turns=True` does not return the full transcript, the spec decides whether a transcript reader over `thread/turns/list` (the deferred `export_codex_transcript` / `list_codex_turns` rows of the codex-host catalog) is needed.
2. Built-in first-class skill / command functions
   - `run_codex_goal(objective, token_budget=None, ...)` → a named wrapper over the goal path `spawn_codex_thread` already has (`thread/goal/set`), plus `get_codex_goal(thread_id)` (`thread/goal/get`) so the caller (and the wrapper) can verify the goal actually took. The user's words (Prompt 4): a function "that simply runs the user's request with the built in "/goal" skill attached to their prompt".
   - Review: the existing `start_codex_review` (`review/start`) already covers review. Do not duplicate or rename it.
   - `list_codex_skills(cwd)` → `skills/list`; `run_codex_skill(skill, prompt, ...)` → a turn whose input carries a first-class `SkillUserInput` item (present in the 0.162.1 schema), refusing an unknown skill name with a detailed error.
   - Named wrappers for Codex's bundled system skills in `C:/Users/422mi/.codex/skills/.system/` (expected: imagegen, openai-docs, skill-creator, skill-installer; verify the list and read each SKILL.md). Apply the catalog's rule (§E legend): wrap a skill only if it can complete headless without a person answering questions; mark the rest ✗ with the reason.
   - Codex TUI slash commands (`/init`, `/compact`, ...) have no app-server method except where listed above. Do not prefix prompts with slash commands: the sibling research proved Muse's headless mode passes `/goal ...` to the model as plain text, a silent failure mode.
3. Every new function is also a READ or WRITE tool in `CodexHostTools`, following the PR's own invariant, except delete (✗). Tool-count tests (currently 15) change accordingly.

### Key decisions
- Naming is `<verb>_<harness>_thread(s)` with `codex` as the harness, matching the existing host. Owner: "only thing I definately want is the actual function naming the way i said".
- Simple wrappers ("simply", Prompt 4). Reuse existing CodexHost functions; do not duplicate review, read or list behavior that already exists.
- Delete is a plain function, never an agent tool (PR #1055's own catalog).
- Every function maps every failure to a `CodexAgentError` with a specific `codex.*` FailureCode and a next step. Owner: "extensively handle errors for every single function". Expected cases include unknown thread id, unknown skill, thread busy, compact on a running turn, delete of a loaded thread, empty since-window.
- "Check that the command actually ran" (§E rule): a skill/goal wrapper verifies in the thread that the feature took (for goal: `thread/goal/get`) and raises a specific error if not, instead of reporting success.
- The helpers' summary record mirrors the cross-harness `NativeThreadSummary(harness, thread_id, title|None, created_at, updated_at, parent_thread_id, model)` field set (§E), so a later cross-harness merge is mechanical, WITHOUT importing that record (it lives only on the sibling branch, not on main).
- The read-only helpers must not run the spend preflight that `spawn_codex_thread` uses. Owner: "why do we even need usage or balance checks inside of the pr?"
- This run merges `origin/main` into `feat/codex-host` (a merge commit, never a rebase: the PR history is already pushed) so the branch contains #1036 before any feature work.

### Rejected alternatives / out of scope (each is an optional Q-n with default NO, never built)
- archive/unarchive, rename, revert, `list_codex_subagent_threads`, set/pause/clear goal, any other unstarred row of `docs/spec/codex-host/request.md` not named above.
- ClaudeHost (PR #1044); any shared base class across hosts.
- Any usage/balance/rate-limit check added to the new helpers.
- Slash-command prefixes in prompts (silent failure mode, see above).
- Importing anything from the sibling branch `feat/harness-thread-helpers-skills` (e.g. `NativeThreadSummary`); it is not on main.

### Constraints and assumptions
- Constants and flags go in `vidbyte/lib/constants/codex.py`; enums in `vidbyte/lib/enums/codex.py`, exported from `vidbyte/lib/enums/__init__.py`; dataclasses in `vidbyte/lib/dataclasses/codex_host.py`. Never in feature files.
- `host.py` is 771 lines; AGENTS.md wants files well under 1,000. New functions go in new modules (e.g. a threads/skills split) rather than growing host.py past ~900.
- Security: never put an API key or token on argv, in files, or in error text. No live paid Codex turns in tests: tests use the in-memory fake app-server `tests/features/codex_host/codex_host_fakes.py` behind a real `CodexClient` subclass. Live runs are manual QA only.
- Never merge PR #1055, never `gh pr merge --admin`, never mark it ready, never push to main, never force-push, never touch the main checkout or the sibling worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-helpers-skills`.
- Python: an isolated venv for this worktree only, `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python` (editable install of this worktree with `.[dev,codex]`). Never `pip install -e` into the global Python (it points at the main checkout and a sibling pipeline runs concurrently).
- CI: `ci.yml` automatic triggers are paused. Dispatch with `gh workflow run ci.yml --ref feat/codex-host` and `gh workflow run static-policy.yml --ref feat/codex-host`; read results via `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`. Actions billing may block runs; then record the API output and rely on the local full gate `python scripts/run_ci.py` (green required).
- Push with `git push origin feat/codex-host` (fast-forward only). PR #1055 stays draft and keeps its title unless it no longer fits; it is not retitled `[WIP]`.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The PR body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

### Verified vendor facts (codex-cli 0.162.1, openai-codex 0.162.1, both installed; schema generated 2026-10-15)
- Regenerate the protocol schema yourself (rawest source): `codex app-server generate-json-schema --out <dir>`. A copy is at `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/codex-schema/` (`ClientRequest.json` holds all request param definitions).
- `ThreadListParams`: archived, cursor, cwd, limit, modelProviders, originators, searchTerm, sectionId, sortDirection, sortKey (`created_at|updated_at|recency_at|section_position`), sourceKinds, useStateDbOnly. Response: data, nextCursor, backwardsCursor.
- `Thread` fields include id, name, preview, createdAt, updatedAt, recencyAt, cwd, model, modelProvider, forkedFromId, parentThreadId, source, threadSource, status, turns, agentNickname, agentRole, path, sessionId.
- `ThreadDeleteParams{threadId}`, `ThreadArchiveParams{threadId}`, `ThreadCompactStartParams{threadId}`, `ThreadReadParams{threadId, includeTurns}`, `ThreadTurnsListParams{threadId, cursor, limit, itemsView, sortDirection}`, `ThreadGoalSetParams{threadId, objective, tokenBudget, status, origin}`, `ThreadGoalGetParams{threadId}`, `SkillsListParams{cwds, forceReload}`, `ReviewStartParams{threadId, target, delivery}`.
- `UserInput` variants: Text, Image, LocalImage, Audio, LocalAudio, Skill, Mention.
- Check which of the new methods the installed `openai_codex` package (site-packages of the venv above) exposes as high-level calls before choosing between it and the PR's own wire layer.

### Clarifications and answers
- Q (Prompt 2): besides continue/fork/run, are there simple actions to add? — A (Prompt 3): "actually using the capabilities of grok build AND also maybe adding some helper functions (view recent sessions, view sessions in last N time period, etc)."
- Q (Prompt 4): a goal function? — A: "a function like: "run_grok_goal" that simply runs the user's request with the built in "/goal" skill attached to their prompt", and "all of the functions like this using each harnesses "built in" first-class skills".
- Q (Prompt 5): which harnesses? — A: "grok, opencode, muse, and whichever other harnesses we have in the repo/sdk" (Codex is in PR #1055, hence this run, Prompt 6).

### Terminology
- Thread = one Codex conversation (app-server `Thread`); turn = one user input and the agent's work on it.
- Thread helper = a read/manage function over existing threads (list recent, since, lineage, search, compact, delete, get/read).
- Built-in skill function = a named function that runs one of the harness's first-class features (goal, review, a skill) through its real protocol surface, not a slash-command prefix.
- READ / WRITE tool = the permission class of the agent tool in `CodexHostTools`; ✗ = plain function only, never an agent tool.
- Sibling pipeline / sibling branch = `feat/harness-thread-helpers-skills`, the Grok/opencode/Muse half of the catalog.

### Implementation hints
- Model new code on the existing host: `vidbyte/harnesses/native/codex/host.py`, `wire.py`, `connection.py`; tools in `vidbyte/tools/builtins/codex/` and `vidbyte/tools/toolsets/codex.py`; tests in `tests/features/codex_host/` with the fake app-server `codex_host_fakes.py` (its request log lets tests pin the exact JSON-RPC method and params each function sends).
- PR #1055's design artifacts (`docs/spec/codex-host/request.md`, `spec.md`, `pr-body.md`) are the prior art for naming, error codes and tool shape.

### Open questions (the spec resolves each as an A-/Q- item)
- Is `search_codex_threads` a thin wrapper over `list_codex_threads(search=...)` or a reuse with no new name?
- Does `read_codex_thread(include_turns=True)` return the full transcript, or is a `thread/turns/list` reader needed?
- Which bundled Codex system skills can run headless, and which are ✗?
- Which app-server methods does openai-codex 0.162.1 expose high-level, and which go through `wire.py`?
- How does `run_codex_goal` verify the goal took, and what error does it raise when it did not?

## D. Weighted words

- "do you think that there are any  simple functions that we missed out on implementng  for each harness, given what is possible with each?" — Prompt 1
- "are these any simple actions inside of grok build that exist that we should add as functions" — Prompt 2
- "what i am talking about is actually using the capabilities of grok build AND also maybe adding some helper functions (view recent sessions, view sessions in last N time period, etc)." — Prompt 3
- "can you list out all of the thread helpers for each harness." — Prompt 4
- "a function like: "run_grok_goal" that simply runs the user's request with the built in "/goal" skill attached to their prompt." — Prompt 4
- "can you like all of the functions like this using each harnesses "built in" first-class skills?" — Prompt 4
- "can you implement all of these helper functions/skill functions in grok, opencode, muse, and whichever other harnesses we have in the repo/sdk." — Prompt 5
- "Make sure the local main is up to date as we recently merged pr 1036 into main" — Prompt 5
- Owner preferences carried into this run from earlier review of these PRs (settled, quoted verbatim):
  - "only thing I definately want is the actual function naming the way i said"
  - "extensively handle errors for every single function"
  - "why do we even need usage or balance checks inside of the pr?"

## E. The assistant's design reply the user accepted (verbatim)

_This is the catalog reply that Prompt 5 refers to. It covers Grok, opencode and Muse; this run applies its helper list, its CMD/SKILL/✗ legend, its "check that the command actually ran" rule, and its `NativeThreadSummary` field set to Codex._

````markdown
I've listed the thread helpers for all three harnesses, plus every built-in command or skill function I could find. One thing to know first: **simply putting `/goal` in front of the prompt is not reliable.** I tested it on Muse, and its headless `exec` mode sends `/goal …` to the model as ordinary text. For Grok it's still unconfirmed. Everything below was checked against the installed CLIs (Grok 1.0.52, opencode 1.18.31, Muse 1.0.1) using help text, vendor docs, Muse's protocol schema and offline runs. No API key was used and no model was called; for Muse I used its offline `echo` provider.

`★ Insight ─────────────────────────────────────`
- **All three keep enough thread data for the same helpers.** Grok writes a documented `summary.json` for each thread. opencode has `session list --format json` and `export`. Muse has `session/list` in its serve protocol (MSP), which already filters by workspace and `updatedAfter`, plus `export`. So one shared summary record can cover all three.
- **On Muse, `muse exec "/goal ship the thing"` came back as `echo: /goal ship the thing`,** with exactly the same events as a plain `hello`. Slash commands only work in Muse's interactive screen. A wrapper that just adds the prefix would quietly run a normal thread instead.
`─────────────────────────────────────────────────`

## 1. Thread helpers for each harness

None of these needs an API key or calls a model. ✅ means I ran it on this machine. The Grok rows come from the vendor docs, because this machine has no Grok threads to test on.

| Helper | Grok | opencode | Muse |
|---|---|---|---|
| `list_<h>_threads(workspace, *, since=None, limit=20)` | Read each `sessions/<encoded-cwd>/*/summary.json` and sort by `updated_at`. | `opencode session list --format json -n N`, run in the workspace. Returns `{id, title, created, updated, projectId, directory}` ✅ | MSP `session/list {workspaceRoot, updatedAfter, limit ≤200}` over `muse serve`, newest first. Checked in the schema only. |
| `list_recent_<h>_threads` / `list_<h>_threads_since` | Wrappers around the above | Wrappers | Wrappers |
| `get_<h>_thread(id, workspace)` | `summary.json`, plus `plan.json` (to-do list) and `plan.md` | `opencode export <id>`, using its `info` block (title, agent, model, tokens, cost, times) ✅ | MSP `session/read {excludeItems: true}`, which the PR already calls |
| `read_<h>_thread(id, workspace)`, the full transcript | `grok export <id>` gives Markdown ✅ | `opencode export <id>` gives JSON messages with text, tool and reasoning parts ✅. `--sanitize` hides sensitive data. | `muse export --session <id> --out <file>` gives JSON with tool calls, approvals and fork history ✅. `--redacted` hides sensitive data. |
| `get_<h>_thread_lineage(id, workspace)`, which thread forked from which | `parent_session_id` in `summary.json` | The `session.parent_id` database column, read with `opencode db "<sql>"`. It also marks subagent threads. | `Session.forkedFrom` |
| `search_<h>_threads(workspace, query)` | `grok sessions search`. Text output only, and it includes results from xAI's servers. | No search command; match titles from the list | Skip: Muse threads have no titles |
| `delete_<h>_thread(id, workspace)` | `grok sessions delete <id>` | `opencode session delete <id>` | No delete command found in the CLI or MSP |
| `compact_<h>_thread(id, workspace)` | `/compact` (has the slash-command question from §2) | Interactive screen only | MSP `session/compact` |

Notes:
- **Only Grok needs a `scope=SDK|USER` option.** It's the only harness the PR runs under a private home folder. opencode and Muse threads created by the SDK land in the user's normal storage, so they also show up in plain `opencode` and `muse`.
- **Muse threads have no title.** A Muse list can only show the id, times, model, turn count and fork parent.
- **All helpers should return one shared record:** `NativeThreadSummary(harness, thread_id, title | None, created_at, updated_at, parent_thread_id, model)`. Then a later `list_threads(workspace)` across all three harnesses is just merge and sort.

## 2. Functions that run built-in commands and skills

How each function calls its feature:
- **CMD ✅**: the CLI has a documented way to run the command without the interactive screen. Reliable.
- **CMD ?**: `grok -p "/<cmd> <args>"`. I couldn't confirm that `-p` expands slash commands, because offline it stops at the login check. One run with a real key settles it.
- **SKILL**: the prompt names a built-in skill or tool and the model loads it. Works without the screen, but the model decides whether to use it.
- **✗**: needs a person to answer questions, or keeps running in the background after a one-shot run has exited.

### Grok Build

`~/.grok/bundled/` holds 24 skills, 3 agents, 7 personas and 1 workflow.

| Function | Runs | What it does | How |
|---|---|---|---|
| `run_grok_goal(objective, *, budget_tokens=None)` | `/goal <objective> [--budget N]` | Works over several rounds. The goal only counts as done after a separate review checks the evidence. | CMD ?. By default the goal runs on Grok's background workflow engine. `GROK_WORKFLOWS=0` makes it run inside the turn instead (the `update_goal` path), which fits a one-shot run. |
| `run_grok_deep_research(query, *, breadth=4)` | `/deep-research` (the bundled `deep-research.rhai`; `breadth` 2–6) | Plans questions, researches in parallel, checks each claim separately, and writes a cited report | CMD ?. It also runs in the background and "returns right away", so it probably needs a long-running Grok session. |
| `run_grok_workflow(name, args, *, agent_budget=None, effort=None)` | `/workflow <name> --agent-budget N --effort E {json}` | Runs any built-in, project or user workflow | CMD ?, same background caveat |
| `run_grok_implement(task, *, effort=None)` | `/implement [--effort N] <task>` | Implements, has 1–5 reviewer personas check the work, and fixes until reviewers find 0 issues | CMD ? only. The skill sets `disable-model-invocation: true`, so the model can't start it from a normal prompt. |
| `run_grok_design(description)` | `/design` | A writer and a reviewer iterate on a design doc until they agree; ends with a PR plan | CMD ? or SKILL |
| `run_grok_execute_plan(design_doc, *, effort, concurrency, dry_run, auto_pr)` | `/execute-plan <path> …` | Builds a design doc's PR plan in parallel, one worktree subagent per PR | CMD ? or SKILL. Long-running. |
| `run_grok_review(*, local=False, branch=None, pr=None)` | `/review [--local\|--branch\|--pr]` | A reviewer subagent reviews the changes. On a PR, it posts a **pending** GitHub review for you to submit. | CMD ? or SKILL |
| `run_grok_code_review()` | `/code-review` | A very strict maintainability audit | CMD ? only (`disable-model-invocation`) |
| `run_grok_resume_claude(session)`, `_codex`, `_cursor` | `/resume-claude <id or words>` | Picks up a Claude Code, Codex or Cursor session inside Grok | CMD ? or SKILL |
| `run_grok_imagine(desc)`, `run_grok_imagine_video(desc)` | `/imagine`, `/imagine-video` | Generates images or video | CMD ?. Where the output files land is unconfirmed. |
| `run_grok_plan(task)`, `run_grok_explore(question)` | `--agent plan` / `--agent explore` | Read-only agents for planning or investigating | The `--agent` flag exists. Picking the bundled agents by name is unconfirmed. |
| ✗ Skip | `/pr-babysit`, `/loop`, `/create-skill`, `/create-workflow` | — | Run in the background or need a person |

`docx`, `pdf`, `pptx` and `game-*` can't be invoked by name (`user-invocable: false`). Grok loads them automatically when a normal prompt asks for a deck or a PDF, so they don't need wrappers.

### opencode

opencode ships 2 commands, 4 agents and 1 skill.

| Function | Runs | What it does | How |
|---|---|---|---|
| `run_opencode_review(target=None)` | `opencode run --command review [commit\|branch\|pr]` | Reviews changes as a subagent task; uncommitted changes by default | CMD ✅ |
| `run_opencode_init()` | `opencode run --command init` | Guided setup of `AGENTS.md` | CMD ✅ |
| `run_opencode_command(name, args)` | `opencode run --command <name>` | Runs any custom command. Your config already has 15, for example `pr-explain` and `design-doc`. | CMD ✅ |
| `run_opencode_plan(task)` | `--agent plan` | The built-in read-only main agent | The flag and agent list are confirmed |

I'd skip the rest. `explore` and `general` can only run as subagents, and the `customize-opencode` skill only edits opencode's own configuration.

### Muse Code

Muse ships 14 bundled skills. Its `exec` mode does not run slash commands (tested).

| Function | Runs | What it does | How |
|---|---|---|---|
| `run_muse_goal(objective)` | The prompt tells the model to use its `create_goal` tool | Sets a pinned objective with a progress percentage | SKILL (steers the model to a tool). Reading the goal back afterward works through `muse export`; MSP only partly exposes it today. |
| `run_muse_plan(task)` | `bundled:plan` | Writes a grounded plan, then stops for approval. Follow up with `continue_muse_thread(id, "approved, build it")`. | SKILL |
| `run_muse_import(session_ref)` | `bundled:import` | Picks up a Claude Code or Codex session from its transcript, path or id | SKILL |
| `run_muse_scaffold(description)` | `bundled:greenfield-project-scaffolding` | Scaffolds a new project. Only fires when the prompt says to start now. | SKILL |
| `run_muse_browser_app(description)` | `bundled:browser-app-delivery` | Delivers a local browser app you can run | SKILL |
| `init_muse_workspace(workspace, *, dry_run=False)` | `muse init [--dry-run] [--force]` | Sets up Muse configuration in the repo | A CLI subcommand; I only checked its help text |
| ✗ Skip | `/deep-research`, `/goal` as commands, `grill`, `grill-and-record` | — | Slash commands only work in the interactive screen. MSP has no `workflow/*` methods yet. `grill` needs a person to answer its questions. |

## How I'd build it

- **Start with two building blocks per harness.**
  - `run_<h>_command(name, args, …)` sends a command: the slash-command form for Grok, `--command` for opencode.
  - `run_<h>_skill(skill, prompt, …)` puts "Use the `<skill>` skill." in front of the prompt.

  Each named function above then becomes a 3–5 line wrapper that returns `NativeThreadResult`, so you can still continue or fork the thread.
- **Check that the command actually ran.** An unexpanded slash command fails without any error, so each wrapper should look for proof in the thread, such as goal state in `summary.json` or `export`, or a workflow-run record. If it isn't there, raise `<harness>.command_not_run`.
- **Order:**
  1. Ship the helpers for all three harnesses and the opencode CMD ✅ functions first; those are verified.
  2. Then add the Muse SKILL functions.
  3. Add the Grok CMD functions after one run with a real key answers two questions: does `-p` expand slash commands, and does `/goal` finish before the process exits?

`★ Insight ─────────────────────────────────────`
- **Two Grok skills only start from a slash command.** `implement` and `code-review` set `disable-model-invocation`. If Grok's `-p` turns out not to expand slash commands, those two can't run headless and would need a long-running Grok session (Grok's ACP protocol) instead.
- **Both Grok and Muse can pick up another tool's session** (`resume-claude` and `bundled:import`). Combined with `read_*_thread`, the SDK can hand a task from one harness to another with very little new code.
`─────────────────────────────────────────────────`

**Follow-ups:**
- I can write a 6-call test script you run with `! python probe.py`, so your key stays in your shell. It would try `-p "/goal …"`, `/deep-research`, `/implement`, `--agent plan` and `/compact`, and dump one `summary.json`.
- The spec then needs three updates: an exception to NG-3 for the helpers, the `command_not_run` failure code, and the Muse slash-command result recorded as verified.
- I deleted the temporary probe folder I made inside WSL.

## Next steps
1. [ ] **Build a skill router agent.** It picks the best harness and built-in skill for a task (Grok `/implement`, opencode `review`, Muse `plan`) and runs it. *Builds on:* the cross-harness command and skill catalog. *First step:* a decision table from 20 past tasks to the function that should have handled each. (ask Claude)
2. [ ] **Launch agent session portability.** Move a live Claude Code or Codex session into Grok (`resume-claude`) or Muse (`bundled:import`) without losing context. *Builds on:* `read_*_thread` plus the import skills. *First step:* hand one real Claude Code session to Grok and grade how much context survives.
3. [ ] **Productize `/implement` as a bring-your-own-key autonomous PR service.** Customers run Grok's implement-and-review loop on their repos with their own key. *Builds on:* `run_grok_implement` plus thread lineage. *First step:* run it on 10 open vidbyte-sdk issues and measure how many get merged.
4. [ ] **Launch a reviewer leaderboard in `vidbyte-evals`.** Score Grok `/review`, `/code-review`, opencode `review` and Muse `plan` on the same seeded-bug PRs. *Builds on:* the built-in review functions. *First step:* seed 15 PRs with known bugs.
5. [ ] **Spin up a goal operations console.** Track every running agent goal (objective, % complete, evidence review) across harnesses. *Builds on:* `run_grok_goal`, `run_muse_goal` and the goal state in threads. *First step:* sketch the goal record merged from Grok and Muse.
6. [ ] **Open-source a thread schema that works across harnesses.** Publish `NativeThreadSummary` and a transcript format with an adapter per vendor, so other tools can build on it. *Builds on:* the three sets of thread helpers. *First step:* draft the schema from the fields confirmed today.
7. [ ] **Pilot a nightly deep-research digest product.** Scheduled cited reports from Grok's research workflow on topics the customer picks. *Builds on:* `run_grok_deep_research`, once a long-running session works. *First step:* run 5 queries by hand and judge the citation quality.
8. [ ] **Build portable workflows.** Turn Grok `.rhai` workflows and opencode custom commands into one workflow format that runs on any harness. *Builds on:* `run_grok_workflow` plus `run_opencode_command`. *First step:* port `deep-research.rhai` to opencode by hand.
9. [ ] **Bet a week on self-serve repo onboarding.** Run `run_opencode_init`, `init_muse_workspace` and Grok's design loop on a new repo, then measure how far a fresh agent gets. *Builds on:* the init and design functions. *First step:* run it on 3 unfamiliar open-source repos.
````
