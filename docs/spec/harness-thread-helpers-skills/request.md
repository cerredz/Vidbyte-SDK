---
slug: harness-thread-helpers-skills
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-15 18:12 (local, UTC-4; 22:12 UTC)
flags: none
---

# Request: Thread helpers and built-in skill functions for the Grok, opencode and Muse harnesses

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (2026-10-15 21:40 UTC, opens the conversation; PR #1036 was then still open):
pr #1036 question for the vidbyte-sdk/, do you think that there are any  simple functions that we missed out on implementng  for each harness, given what is possible with each?

**Prompt 2** (21:41 UTC, sent while the assistant was still answering Prompt 1):
like besides just "continue, fork, and run" grok threads, are these any simple actions inside of grok build that exist that we should add as functions inside of  this pr?

**Prompt 3** (21:46 UTC, after the assistant answered with export/delete functions and new flags):
No this is not what i am talking about, what i am talking about is actually using the capabilities of grok build AND also maybe adding some helper functions (view recent sessions, view sessions in last N time period, etc).

**Prompt 4** (22:02 UTC, after the assistant's reply R3, quoted verbatim in §E.1):
I like all of your thread helpers, can you list out all of the thread helpers for each harness. And also, maybe for the goal/deep research functions we have a function like: "run_grok_goal" that simply runs the user's request with the built in "/goal" skill attached to their prompt. If so, can you like all of the functions like this using each harnesses "built in" first-class skills?

**Prompt 5** (22:11 UTC, the `/spec-pipeline` invocation, after the assistant's catalog reply R4, quoted verbatim in §E.2):
great, can you implement all of these helper functions/skill functions in grok, opencode, muse, and whichever other harnesses we have in the repo/sdk. Make sure the local main is up to date as we recently merged pr 1036 into main

**Prompt 6** (~22:25 UTC, sent while this pipeline was in S0):
note, ccan you also in a subagent launch this "spec-pipeline" process for pr #1055 and explain the changes that we want to make with the implementation of the existing pr

## B. Handoff block and decision ledger (verbatim, if present)
none

## C. Structured conversation notes

### Key decisions
- **KD-1 Scope is the catalog the user accepted.** Prompt 4 ("I like all of your thread helpers") accepted the thread helpers of R3 (§E.1, its section "A. Thread helpers" only; its section B — worktrees, memory, structured output and other Grok parameters — was not accepted). Prompt 5 ("implement all of these helper functions/skill functions") accepted R4 (§E.2): §1 the thread helpers per harness, §2 the built-in command/skill functions per harness, and "How I'd build it" (two building blocks per harness plus thin named wrappers; verify the command actually ran).
- **KD-2 Harnesses in this PR: Grok (`grok`), opencode (`opencode`), Muse (`muse`).** "whichever other harnesses we have in the repo/sdk" (Prompt 5) was resolved as follows:
  - **Codex** is handled by a separate spec-pipeline run on the existing PR #1055 (branch `feat/codex-host`), launched in response to Prompt 6. That PR's `CodexHost` already owns the Codex thread vocabulary over `codex app-server` (`list_codex_threads`, `read_codex_thread`, `fork_codex_thread`, `start_codex_review`, a goal path in `spawn_codex_thread`), and its own catalog lists compact/delete/goal-get as deferred rows. Building Codex helpers in this PR on main's `CodexHarnessAgent` (`vidbyte/agents/codex/`) would create a second, competing Codex thread surface. This PR does not touch Codex.
  - **Claude Code** is not on main (draft PR #1044 is open), so it is out of scope.
  - Any other harness the scout finds on main at f216fdcf that has a thread concept must be reported in code-map.md §4 so the spec author can record it as in or out with a reason.
- **KD-3 Function naming is the owner's one literal requirement** (from PR #1036, `docs/spec/harness-thread-functions/request.md` KD-1: "only thing I definately want is the actual function naming the way i said"). PR #1036 established `run_/continue_/fork_<harness>_thread`. New functions follow the same `<verb>_<harness>_thread` / `<verb>_<harness>_threads` pattern as proposed in §E.2: `list_grok_threads`, `list_recent_grok_threads`, `list_grok_threads_since`, `get_grok_thread`, `read_grok_thread`, `get_grok_thread_lineage`, `search_grok_threads`, `delete_grok_thread`, `compact_grok_thread`, and the same shapes for `opencode` and `muse` where the harness supports them; skill functions `run_<harness>_<skill>` (`run_grok_goal`, `run_opencode_review`, `run_muse_plan`, …) plus the two building blocks `run_<harness>_command` and `run_<harness>_skill`.
- **KD-4 Each function takes what it needs plus, where a model call or the vendor needs it, the caller's API key** (PR #1036 KD-2: "each function has the parameters needed for the function and then the api key that the user is providing"). The thread helpers read local stores and do not call a model; the spec decides per helper whether a key is needed at all (for example `grok sessions search` mixes in results from xAI's servers).
- **KD-5 This request supersedes PR #1036's NG-3 for exactly these helpers.** NG-3 listed "session listing/search/read/page" among non-goals; the user now asks for them (Prompts 3–5). Everything else NG-3 excludes stays out: usage, cost, balance, readiness, version checks, model lists, revert/unrevert, diff, MCP-server management. `get_grok_thread_usage` was marked "optional, since you pushed back on usage" in §E.1 and is NOT in scope (owner, PR #1036 Prompt 2: "why do we even need usage or balance checks inside of the pr?").
- **KD-6 A skill function must prove its command or skill actually ran.** Verified for Muse: `muse exec "/goal ship the thing"` with `--provider echo` returned `echo: /goal ship the thing` with exactly the same event sequence (`command_kind` `turn.submit`) as a plain `hello`, so headless Muse passes slash commands to the model as plain text. A wrapper that only prefixes the prompt would silently run an ordinary thread. Each wrapper checks the thread for evidence (goal state, workflow record, review artifact, or similar) and raises a failure coded `<harness>.command_not_run` when the evidence is absent (§E.2 "How I'd build it").
- **KD-7 One shared summary record for every list/get helper:** `NativeThreadSummary(harness, thread_id, title | None, created_at, updated_at, parent_thread_id, model)` in `vidbyte/lib/dataclasses/native_threads.py` (§E.2 notes), so a cross-harness merge is a sort.
- **KD-8 Only Grok needs `scope=SDK|USER`** on its list/get helpers, because PR #1036 runs Grok under a private per-workspace home (`~/.vidbyte/grok-homes/<sha256(normcase(resolved workspace))[:16]>`); the scout must confirm from the code where opencode and Muse threads created by PR #1036's functions land (see Open questions).
- **KD-9 House rules from PR #1036 still bind** (its request.md KD-7, KD-8): constants and hardcoded strings live in `vidbyte/lib/constants/native_threads.py`, flags and closed sets are enums in `vidbyte/lib/enums/native_threads.py`; error messages are detailed ("error messages need to be in much more detail"); "extensively handle errors for every single function".
- **KD-10 Keep it simple.** Prompt 4: a function "that simply runs the user's request with the built in "/goal" skill attached to their prompt". Each named skill function is a 3–5 line wrapper over the harness's two building blocks and returns PR #1036's `NativeThreadResult`, so the caller can `continue_`/`fork_` the resulting thread.

### Rejected alternatives
- **Export/delete plus extra CLI flags as "the" answer to Prompt 1–2** — Prompt 3: "No this is not what i am talking about"; the user wants the harnesses' real capabilities (built-in commands/skills) and thread-browsing helpers.
- **Bare slash-command prefixing without verification** — disproved for Muse (KD-6); unverified for Grok `-p`.
- **Codex helpers on main's `CodexHarnessAgent` in this PR** — KD-2.
- **Usage/balance helpers** — KD-5.
- **Long-running sessions (`grok agent stdio`/ACP, `muse serve` as a persistent host)** — PR #1036 removed host machinery (its spec NG-2, G-2 "simply"); helpers that need MSP use one short-lived `muse serve` per call, as PR #1036's `session/read` already does.

### Constraints and assumptions
- Base: `main` at f216fdcf71bf44d1a99b1dee87d0d4fdfcd9c67c (PR #1036 merged). Local main was fast-forwarded to it before the worktree was created.
- Installed CLIs used for research: Grok Build 1.0.52, opencode 1.18.31, Muse 1.0.1 (inside WSL; launched by PR #1036's `MuseLauncher`), codex-cli 0.162.1. No API key was used and no model was called during research; Muse runs used its offline `echo` provider.
- Tests may not spend money or need keys: PR #1036's tests use `tests/features/harness_threads/fake_harness.py`. Live runs are manual QA for the user, who runs any key-bearing probe in their own shell (`! python probe.py`) so the key never enters the agent's context.
- The API key never goes on argv, into a file, or into an error message (PR #1036 invariant).
- AGENTS.md: dataclasses in `vidbyte/lib/dataclasses/<domain>.py`; enums in `vidbyte/lib/enums/<domain>.py` exported from `vidbyte/lib/enums/__init__.py`; constants in `vidbyte/lib/constants/<domain>.py`; `vidbyte/lib/` imports nothing above it; call chains one level deep; narrated main functions; files well under 1,000 lines; folder READMEs ≤ 40,000 characters (lint A009); `docs/` is opaque; full gate `python scripts/run_ci.py`; lint `python lint/run.py` must end `AGENT-LINT: PASS`, never raise its baseline.
- SDK CI: `ci.yml` automatic triggers are paused; dispatch with `gh workflow run ci.yml --ref feat/harness-thread-helpers-skills` and `gh workflow run static-policy.yml --ref feat/harness-thread-helpers-skills`, read via `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`. Never merge; `gh pr merge --admin` needs the user's approval per PR.
- The worktree branch's upstream is unset on purpose; push with `git push -u origin feat/harness-thread-helpers-skills`.
- A concurrent pipeline (PR #1055, worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-thread-helpers`) is running. The global `vidbyte-sdk` editable install points at the main checkout `C:/Users/422mi/vidbyte-repos/vidbyte-sdk`; never `pip install -e` into the global Python. Use a dedicated venv at `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills`.

### Clarifications and answers
- Q (assistant, R2): export/delete functions and new flags? — A: Prompt 3, "No this is not what i am talking about, what i am talking about is actually using the capabilities of grok build AND also maybe adding some helper functions (view recent sessions, view sessions in last N time period, etc)."
- Q (assistant, R3): which helpers and capability functions? — A: Prompt 4, "I like all of your thread helpers" plus the `run_grok_goal` pattern for every harness's built-in first-class skills.
- Q (assistant, R4): ship helpers and verified CMD functions first, Grok CMD functions after a live probe? — A: Prompt 5, "implement all of these helper functions/skill functions". So the Grok `CMD ?` functions are in scope; the spec must make them safe without a live probe (KD-6 guard) and hand the user a probe script for manual QA.

### Terminology
- **Harness** — a vendor coding-agent CLI the SDK drives: Grok Build (`grok`), opencode (`opencode`), Muse Code (`muse`, Meta's CLI, run inside WSL on Windows).
- **Thread** — a harness session (Grok/opencode/Muse all call it a session). PR #1036's functions return `NativeThreadResult` with the thread id.
- **Thread helper** — a function that browses or manages existing threads (list, recent, since, get, read transcript, lineage, search, delete, compact). No model call.
- **Skill function / built-in command function** — a function that runs the caller's request through a harness's built-in first-class command or skill (for example Grok `/goal`, opencode `run --command review`, Muse `bundled:plan`).
- **Mechanism legend (§E.2):** CMD ✅ = documented headless way to run the command (reliable); CMD ? = `grok -p "/<cmd> …"`, slash expansion unverified; SKILL = the prompt names a built-in skill or tool and the model loads it; ✗ = needs a person or keeps running after a one-shot run exits — not wrapped.
- **SDK scope vs USER scope (Grok only)** — threads in the SDK's private Grok home vs the user's normal `~/.grok`.
- **Building blocks** — `run_<harness>_command(name, args, …)` and `run_<harness>_skill(skill, prompt, …)`; every named skill function wraps one of them.

### Implementation hints
- PR #1036 code to extend (on main): `vidbyte/harnesses/native/{grok,opencode,muse,hostkit}/`; `vidbyte/lib/process/{argv.py (CliArgv), runner.py (CliRunner, ProcessStopper)}`; `vidbyte/lib/dataclasses/native_threads.py` (`NativeThreadRequest`, `GrokThreadConfig`, `OpencodeThreadConfig`, `MuseThreadConfig`, `NativeThreadResult`); `vidbyte/lib/dataclasses/process.py`; `vidbyte/lib/dataclasses/validation.py` (`RecordFieldValidator`, `RecordFieldConverter`); `vidbyte/lib/enums/native_threads.py` (NativeHarness, NativeThreadVerb, NativeThreadOperation, NativeThreadProblem, GrokFlag, OpencodeFlag, MuseFlag, WslFlag, ShellFlag, NativeEnvironmentVariable, MuseMethod, OpencodeEventType, …); `vidbyte/lib/constants/native_threads.py`; `NativeThreadError` in `vidbyte/lib/errors/base.py`; `NativeErrorFactory` (`hostkit/errors.py`), `NativeLauncher` (`hostkit/launcher.py`), `NativeSkillFolders` (`hostkit/skills.py`), `MuseLauncher` (WSL); 28 `FailureCode` members named `<harness>.<problem>` in `vidbyte/lib/enums/failure.py`; tests in `tests/features/harness_threads/` with `fake_harness.py`; per-harness static classes (e.g. `GrokThreads`, `<H>ThreadRun.execute`) bound to module-level function names.
- PR #1036's own spec, request and review are at `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-helpers-skills/docs/spec/harness-thread-functions/{request.md,spec.md,review.md,pr-body.md}` — the source for its invariants (INV-*), non-goals (NG-*) and edge cases (EC-*).
- **Verified data sources per harness** (detail in §E.2 §1):
  - Grok: `<home>/sessions/<encoded-cwd>/<id>/summary.json` (documented fields: id, title, summary, last-turn summary, created/updated, model, message count, `parent_session_id`), `plan.json`, `plan.md`; `grok export <id>` (Markdown; unknown id → `Session '…' not found.`, verified); `grok sessions search` (text only, mixes in xAI server results); `grok sessions delete <id>` (help text only). The exact `summary.json` shape is UNVERIFIED (no local Grok threads on the research machine).
  - opencode: `opencode session list --format json -n N` run inside the workspace (sessions are scoped per project; verified) → `{id, title, created, updated, projectId, directory}`; `opencode export <id>` JSON (`info` block: title, agent, model, tokens, cost, times; messages with text/tool/reasoning parts; `--sanitize`; verified); `opencode session delete <id>`; lineage from the `session.parent_id` column via `opencode db "<sql>"`; `opencode run --command <name>` is the documented headless command path (verified in help); built-in commands `review` and `init`; agents `plan` (read-only primary), `build`, `explore`/`general` (subagent-only).
  - Muse: MSP `session/list {workspaceRoot, updatedAfter, limit ≤ 200}` over `muse serve` (schema only); `session/read {excludeItems: true}` (PR #1036 already calls it); `session/compact`; `muse export --session <id> --out <file>` (JSON with tool calls, approvals, fork history; `--redacted`; verified offline); `Session.forkedFrom`; no titles; no delete in CLI or MSP; 14 bundled skills (`bundled:plan`, `bundled:import`, `bundled:greenfield-project-scaffolding`, `bundled:browser-app-delivery`, …); tools `create_goal`/`update_goal`; `muse init [--dry-run] [--force]`.
- **Raw research captures** (reference only; they may contain the user's real session content, so never commit them; build synthetic fixtures with the same shape): `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/` → `msp.schema.json` (full Muse MSP schema), `muse-skills.json`, `oc-export.json` (one real opencode export), `oc-config.json`, `inspect*.json` (Grok `inspect` output under a private home).
- **Grok private home does not isolate** (verified with `grok inspect`): under a private `GROK_HOME` Grok still loads `~/.claude/Claude.md` as project instructions, 16 hooks from `~/.claude` (including `user_prompt_submit`), 148 skills from `~/.agents/skills` and `~/.claude/skills` (including `.trash`), and the `wmux` MCP server from `~/.claude.json`; `compat.claude.*`/`compat.cursor.*` report `enabled: false` yet inspect still lists the items. This contradicts PR #1036 spec EC-44. It matters here because SDK-scope listing reads that private home; the spec should state it as a known limitation, not fix it (out of scope).
- **Grok background workflows:** `/goal` and `/deep-research` run on Grok's background workflow engine by default and "return right away"; `GROK_WORKFLOWS=0` makes `/goal` run in-turn (`update_goal` driver), which suits a one-shot run. `implement` and `code-review` set `disable-model-invocation: true` (slash-command only). Grok sandbox is enforced only on Linux/macOS; on Windows it warns and continues.
- Windows shell gotchas for tests that shell out: Git Bash mangles `/usr/...` paths passed to `wsl.exe` (set `MSYS_NO_PATHCONV=1`); `/tmp` from Git Bash is not the Windows temp dir.

### Open questions (the spec author resolves each as an A- or Q-item)
- Where do opencode and Muse threads created by PR #1036's `run_/continue_/fork_` land? PR #1036's spec says Muse runs with a private per-call `XDG_CONFIG_HOME` and `MUSE_AUTH_PATH`; confirm from the code whether its session store is under that private folder (then list/get helpers need the same scope treatment as Grok) or in the user's normal store.
- Grok `-p "/goal …"`: does `-p` expand slash commands, and does `/goal` finish before the one-shot process exits? Unverified; the design must be safe either way (KD-6) and the PR should ship a key-in-your-own-shell probe script for manual QA.
- Which §E.2 rows are ✗ after the spec's own analysis (background-only, needs a person), and which named wrappers ship.
- Whether `compact_<harness>_thread` for Grok (slash `/compact`, CMD ?) and opencode (interactive only) exist at all, or only Muse (`session/compact`).
- Exact `FailureCode` members to add (at minimum `<harness>.command_not_run`, unknown thread id, store unreadable) and how they map onto `NativeThreadProblem`.
- File budget: `vidbyte/harnesses/native/<harness>/` modules for helpers and skills vs one shared helper module in `hostkit/`; keep every file well under 1,000 lines.

## D. Weighted words

- "any  simple functions that we missed out on implementng  for each harness" — Prompt 1
- "are these any simple actions inside of grok build that exist" — Prompt 2
- "actually using the capabilities of grok build AND also maybe adding some helper functions (view recent sessions, view sessions in last N time period, etc)" — Prompt 3
- "I like all of your thread helpers, can you list out all of the thread helpers for each harness" — Prompt 4
- "a function like: "run_grok_goal" that simply runs the user's request with the built in "/goal" skill attached to their prompt" — Prompt 4
- "can you like all of the functions like this using each harnesses "built in" first-class skills?" — Prompt 4
- "implement all of these helper functions/skill functions in grok, opencode, muse, and whichever other harnesses we have in the repo/sdk" — Prompt 5
- "Make sure the local main is up to date as we recently merged pr 1036 into main" — Prompt 5
- Carried from PR #1036 (`docs/spec/harness-thread-functions/request.md` §D): "only thing I definately want is the actual function naming the way i said"; "why do we even need usage or balance checks inside of the pr?"; "Make sure to extensively handle errors for every single function."; "error messages need to be in much more detail"; "i wanted the pr to simply do the following".

## E. The assistant's replies the user accepted (verbatim)

### E.1 — R3, reply to Prompt 3 (2026-10-15 ~21:55 UTC). Prompt 4 accepted its thread helpers (its section "A. Thread helpers") only; section B (Grok features as functions or parameters) was not accepted.

`````markdown
I misread you the first time. Here are the two lists you asked for: **(A)** helper functions for browsing threads, and **(B)** functions built on Grok Build's own features. Everything comes from Grok 1.0.52's `--help`, its user guide (installed under `~/.grok/docs/`), and test runs of `grok inspect`, `export`, `models` and `sessions` in an empty Grok folder with no API key, so no model was called.

`★ Insight ─────────────────────────────────────`
- **Each thread has a small metadata file.** Grok writes `sessions/<encoded-cwd>/<id>/summary.json` for every thread. Its documented fields include `created_at`, `updated_at`, `generated_title`, `session_summary`, `last_turn_summary`, `parent_session_id`, `current_model_id`, `num_messages` and `agent_name`. "Recent threads" and "threads from the last N hours" are just a folder scan plus a sort, with no key and no model call.
- **The built-in list command is a poor fit.** `grok sessions list` exists but has no `--json` option and prints rows meant for people to read.
- **The PR's threads are hidden from plain `grok`.** The PR runs Grok with its own home folder, `~/.vidbyte/grok-homes/<key>`. So these helpers are the only way to see threads the SDK created. They should also be able to read your own `~/.grok` threads.
`─────────────────────────────────────────────────`

## A. Thread helpers (all local: no key, no model call)

| Function | Reads | Returns | Checked? |
|---|---|---|---|
| `list_grok_threads(workspace, *, since=None, limit=20, scope=SDK)` | every `summary.json` | newest first: id, title, summary, last-turn summary, created/updated times, model, message count, parent id | The layout and fields are documented. The exact JSON format needs one real thread, and this machine has none. |
| `list_recent_grok_threads(workspace, limit=10)` and `list_grok_threads_since(workspace, timedelta(hours=24))` | thin wrappers around the function above | the two views you named | n/a |
| `get_grok_thread(thread_id, workspace)` | `summary.json`, `plan.json` (to-do list), `plan.md` (plan mode) | one thread's metadata, task list and plan | documented |
| `read_grok_thread(thread_id, workspace)` | `grok export <id>` | Markdown transcript, including tool calls | Ran it. An unknown id returns `Session '…' not found.` |
| `get_grok_thread_lineage(thread_id, workspace)` | the `parent_session_id` chain | which thread was forked from which | documented |
| `search_grok_threads(workspace, query)` | `grok sessions search` | matches on titles and prompts | Weakest of the set: text output only, and it mixes in results from xAI's servers. |
| `delete_grok_thread(thread_id, workspace)` | `grok sessions delete <id>` | nothing | help text only |
| `get_grok_thread_usage(thread_id, workspace)` | `grok usage <id>` (JSON) | tokens and cost per turn | Optional, since you pushed back on usage. It only reports after the fact; it is not a balance check. |

`scope` picks which threads to read: the SDK's private folder for that workspace (`SDK`), or your own `~/.grok` (`USER`).

```python
day = await list_grok_threads(repo, since=timedelta(hours=24))
for t in day:
    print(t.updated_at, t.thread_id, t.title, "forked from", t.parent_thread_id)
```

## B. Grok Build features as functions or parameters

Ranked by value against effort. Each one works with `grok -p`, which fits the PR's one-process-per-call design.

1. **Run in a separate git worktree.** `--worktree [NAME]` with `--ref <branch>` makes Grok create a git worktree (uncommitted changes included) and run the thread there. The JSON `cwd` then points inside it.
   - Proposed: `run_grok_thread(..., worktree="feat-x", base_ref="main")`, plus `list_grok_worktrees` (`grok worktree list --json`) and `remove_grok_worktree`.
   - This lets several Grok threads work on one repo at once without clashing. It can't be combined with fork.
2. **Structured output.** `--json-schema` gives `run_grok_thread(..., output_schema={...})`, which returns a parsed object. Grok retries when the answer doesn't match the schema. One real run is needed to see where the object sits in the `json` output.
3. **Custom agents and subagents.**
   - `--agent <name|file.md>` runs the thread as an agent you define in a Markdown file (its tools, MCP servers and prompt).
   - `--agents <JSON>` defines subagents inline, and `--no-subagents` turns them off.
   - `grok inspect` confirms three built-in agents: `general-purpose`, `explore` (read-only) and `plan` (read-only, writes a plan).
   - Proposed: `agent=Path(...)` and `subagents={...}`. I haven't confirmed the `--agents` JSON format; it is probably the same as Claude Code's.
4. **Access levels.** Grok can limit a thread in three ways:
   - `--tools` / `--disallowed-tools` (headless only);
   - six permission modes (the PR exposes four and is missing `bypassPermissions` and `auto`);
   - `--sandbox read-only|workspace|strict`.

   Proposed: one `access=READ_ONLY|EDIT|FULL` setting. ⚠ The sandbox only works on Linux and macOS. On Windows Grok "logs a warning and continues without enforcement", so the SDK should refuse `sandbox` on Windows instead of passing it through.
5. **Memory per repo.** Setting `GROK_MEMORY=1` turns on Grok's memory between threads. Notes are saved under `<home>/memory-v2/workspaces/<repo>-<hash>/topics/*.md`. The PR already keeps one private home per workspace, so memory stays tied to that repo across SDK threads. Proposed: `memory=True` in the config, `read_grok_memory(workspace)`, and `clear_grok_memory(workspace)` (`grok memory clear --workspace --yes`).
6. **`inspect_grok_workspace(workspace)`.** Runs `grok inspect --json`, which I ran with no key. It returns every skill, hook, MCP server, agent and instruction file a thread will load. That's how I found the problem described below.
7. **Small settings.**
   - `--max-turns` caps how many turns the agent takes.
   - `--rules` adds text to the system prompt, and `--system-prompt-override` replaces it.
   - `--disable-web-search` turns off web search.
   - `-s <uuid>` lets the SDK choose the thread id up front, so a run that times out keeps its id.

**Grok's headline features aren't simple to wrap yet:**

| Feature | What it does | Why it isn't a one-call function |
|---|---|---|
| `/goal` | Keeps working across rounds, and only marks the goal done after a separate review checks the evidence. | It's a slash command, and I couldn't confirm that `grok -p "/goal …"` works headless. My tests stopped at the login check before Grok read the prompt. |
| `/deep-research` | Plans questions, collects claims with sources, and has a separate verifier check each claim. | It runs in the background and returns immediately, but `grok -p` exits when its turn ends. |
| `/workflow <name>` | Runs saved multi-agent `.rhai` workflows (for example `review-changes`), with agent budgets and pause/resume. | Same background problem. |
| `/loop`, `/imagine`, `/imagine-video` | Scheduled prompts, image generation, video generation. | Slash commands; headless use not confirmed. |

These need a long-running `grok agent stdio` session, which the reshape removed (spec NG-2). They fit a second PR, for example `start_grok_goal`, `get_grok_goal_status` and `run_grok_deep_research`. xAI's docs point Python users to `agent-client-protocol-python` for that kind of session.

## ⚠ Side finding: the private Grok home doesn't isolate the run

I ran `grok inspect --json` with a brand-new, empty `GROK_HOME`. Grok still loaded:
- `~/.claude/Claude.md` as project instructions;
- **16 hooks from `~/.claude`**, including your `user_prompt_submit` hooks, so your next-steps hook would fire inside SDK Grok threads;
- 148 skills from `~/.agents/skills` and `~/.claude/skills`, including `.trash` folders;
- the `wmux` MCP server from `~/.claude.json`.

Grok has `compat.claude.*` settings meant to turn this off. I put them in the private home's `config.toml`, and `inspect` reported them as `enabled: false`, yet it still listed the same hooks and skills. Only a run with a real key can show whether they actually load. Spec EC-44 says SDK runs read "nothing from `~/.grok`". That's true, but they do read `~/.claude`, which is worse because hooks run code. This also answers open question 4 in the PR's research notes.

`★ Insight ─────────────────────────────────────`
- **Helpers in A are cheap to test.** They only read files Grok has already written, so the existing offline tests can cover them with fake `summary.json` files.
- **Features in B change how a run behaves.** Each needs one real run to confirm its output before you build on it.
- **That split suggests the PR order.** Ship the helpers (A) and `inspect` in this PR, the parameters (B1–B5) in the next, and goal, deep research and workflows in a third.
`─────────────────────────────────────────────────`

**Still unconfirmed, needing one real run (a few cents with your key):** the exact `summary.json` format, where `--json-schema` output appears, worktree behavior, the `--agents` JSON format, whether slash commands work in `-p`, and whether the `~/.claude` hooks fire. I can write a short test script for you to run with `! python probe.py`, so your key never passes through me. Once these are confirmed, the spec needs updates: EC-44, open question 4, and an exception to NG-3 for the browsing helpers.

## Next steps
1. [ ] **Build a thread explorer covering all your agent tools.** One per-repo timeline of Grok, opencode, Muse and Claude Code threads, with fork history, so you can see everything your agents did. *Builds on:* the `summary.json` helpers plus `opencode export`. *First step:* map each tool's thread storage onto one shared summary record. (ask Claude)
2. [ ] **Launch long-running Grok jobs over Grok's agent protocol (ACP).** Run `/goal` and `/deep-research` as background jobs you can check on later, for multi-hour autonomous work. *Builds on:* this feature map plus the Python ACP SDK. *First step:* a small test that starts `grok agent stdio`, sets a goal, and polls its status. (ask Claude)
3. [ ] **Build a parallel worktree fleet.** Run N Grok threads on N worktrees of one repo and keep the ones whose tests pass. *Builds on:* `--worktree` plus the worktree helpers. *First step:* try 3 threads on one vidbyte-sdk issue.
4. [ ] **Productize repo-expert agents.** Memory scoped per workspace means each repo builds up knowledge across threads, sold as "agents that know your codebase". *Builds on:* the per-workspace home plus `GROK_MEMORY`. *First step:* run 10 memory-on threads on vidbyte-sdk and read what they saved.
5. [ ] **Sell clean-room agent runs.** Isolation that strips inherited hooks, skills and MCP servers from agent runs, for teams running agents in CI on shared machines. *Builds on:* the `inspect` finding. *First step:* check what each tool inherits on 3 developer machines (guess: they all leak in similar ways).
6. [ ] **Publish a pack of Grok agents and personas.** Agent files and personas with defined inputs and outputs (reviewer, migrator, test writer) that run through `agent=`. *Builds on:* `--agent` files. *First step:* write 3 agent files and run each headless.
7. [ ] **Build typed CI checks on structured output.** PR checks that ask a coding agent for a verdict that must match a schema, offered to teams. *Builds on:* `--json-schema`. *First step:* one GitHub Action that calls `run_grok_thread(output_schema=...)` on vidbyte-sdk PRs.
8. [ ] **Turn exported threads into eval sets in `vidbyte-evals`.** Use transcripts plus structured verdicts as graded examples of agent work. *Builds on:* `read_grok_thread` plus output schemas. *First step:* export 20 threads and grade them.
9. [ ] **Pitch Vidbyte to xAI as the Python layer for Grok Build.** xAI's docs send Python users to a third-party ACP SDK, so a higher-level SDK may fill a gap (guess). *Builds on:* the thread functions and helpers. *First step:* a one-page pitch with a 60-second demo.
10. [ ] **Bet on Vidbyte owning one thread index across all vendors.** Over 6–12 months, threads become Vidbyte objects stored in `vidbyte.sessions` that you can search and fork across agent tools. *Builds on:* reading each vendor's thread storage. *First step:* a design doc linking Grok's `summary.json` to `SessionStore`.
`````

### E.2 — R4, reply to Prompt 4 (2026-10-15 ~22:10 UTC). Prompt 5 asked to implement all of its helper and skill functions.

`````markdown
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
10. [ ] **Bet on Vidbyte as the command layer across agent CLIs.** Over 6–12 months, every vendor's best built-in skill becomes callable from one SDK with one result type. *Builds on:* the two building blocks (`run_<h>_command`, `run_<h>_skill`). *First step:* list each vendor's release notes for new built-ins and set up a monthly catalog refresh.
`````
