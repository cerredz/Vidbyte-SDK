---
spec: harness-thread-helpers-skills
title: Thread helpers and built-in skill functions for the Grok, opencode and Muse harnesses
status: approved         # draft | approved | tests-written | implemented | reviewed | verified | pr-open | abandoned
revision: 3
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-helpers-skills
branch: feat/harness-thread-helpers-skills
base_commit: 0f69f7b75346369b3d004fcded64758c213caa8e   # r1 was written on 72a4ade1; the branch was rebased onto origin/main 0f69f7b7 (#1095, #1103), which touches no native file
created: 2026-10-15
updated: 2026-10-15
pr:                      # filled at S3 (draft) and finalized at S6
---

# Spec: Thread helpers and built-in skill functions for the Grok, opencode and Muse harnesses

> **TL;DR** — PR #1036 gave `vidbyte.harnesses.native` nine functions that run, continue and fork Grok Build, opencode and Muse Code threads. This PR adds 47 more under the same `<verb>_<harness>_thread(s)` naming. 22 are keyless thread helpers (list, recent, since, get, read, lineage, search, delete) that all return one shared `NativeThreadSummary`. 25 are skill functions (`run_grok_goal`, `run_opencode_review`, `run_muse_plan`, …) that run a harness's built-in command or skill and return #1036's `NativeThreadResult`. The decision that matters most: **a skill function returns only when that run's own record proves the command or skill ran** (Grok streaming tool calls or, for code-review, the run's own transcript; Muse session items; opencode's own command dispatch). Otherwise it raises `<harness>.command_not_run` carrying the new thread id, because a slash command that does not expand fails silently (verified on Muse).

## §0 User prompts

### 0.1 Invoking request (verbatim)
great, can you implement all of these helper functions/skill functions in grok, opencode, muse, and whichever other harnesses we have in the repo/sdk. Make sure the local main is up to date as we recently merged pr 1036 into main

The rest of the conversation, verbatim, from `request.md` §A, in order. Prompt 5 above is the invocation. "all of these" refers to the catalogs quoted verbatim in `request.md` §E.1 (section A only) and §E.2.

- **Prompt 1:** pr #1036 question for the vidbyte-sdk/, do you think that there are any  simple functions that we missed out on implementng  for each harness, given what is possible with each?
- **Prompt 2:** like besides just "continue, fork, and run" grok threads, are these any simple actions inside of grok build that exist that we should add as functions inside of  this pr?
- **Prompt 3:** No this is not what i am talking about, what i am talking about is actually using the capabilities of grok build AND also maybe adding some helper functions (view recent sessions, view sessions in last N time period, etc).
- **Prompt 4:** I like all of your thread helpers, can you list out all of the thread helpers for each harness. And also, maybe for the goal/deep research functions we have a function like: "run_grok_goal" that simply runs the user's request with the built in "/goal" skill attached to their prompt. If so, can you like all of the functions like this using each harnesses "built in" first-class skills?
- **Prompt 6** (sent during S0; it started the sibling run on PR #1055 and is not in scope here): note, ccan you also in a subagent launch this "spec-pipeline" process for pr #1055 and explain the changes that we want to make with the implementation of the existing pr

### 0.2 User replies during the run
_None yet. The orchestrator appends any reply the user sends during the run here verbatim, labeled with the revision it produced._

---

## Part A — Framing

## §1 Goal

Today a developer using PR #1036 can start, continue and fork Grok, opencode and Muse threads, but nothing more:

- **They cannot see their threads.** `vidbyte/harnesses/native/` has no list or read operation; #1036 INV-19 forbade one.
- **SDK-created Grok threads are hidden from the developer's own `grok`.** They live in a private home under `~/.vidbyte/grok-homes/` (`grok/threads.py:_prepare_home`), so plain `grok` cannot show them.
- **They cannot run a harness's built-in command with one call.** Examples are Grok's `/goal` and `/implement`, opencode's `review`, and Muse's `bundled:plan`.
- **A naive wrapper would silently do the wrong thing.** `muse exec "/goal ship the thing"` came back as `echo: /goal ship the thing`, with the same events as a plain prompt (request.md KD-6). A function that only adds the slash prefix would run an ordinary thread and report success.

The owner asked for "view recent sessions, view sessions in last N time period" (Prompt 3), "all of your thread helpers … for each harness" (Prompt 4), a `run_grok_goal` "that simply runs the user's request with the built in "/goal" skill" (Prompt 4), and "all of these helper functions/skill functions" (Prompt 5).

| ID | Goal (outcome) | How we will know | Source |
|---|---|---|---|
| G-1 | A developer browses and manages any harness's threads with one keyless call per question: recent threads, threads from the last N hours, one thread, its transcript, its fork lineage, a title search, and deleting a thread. Every list and get answer is the same `NativeThreadSummary`, so merging harnesses is a sort. | AC-1 to AC-11, AC-19, AC-27, AC-28, AC-31 and AC-32 pass | Prompt 3, Prompt 4, KD-1, KD-7, §E.1 A, §E.2 §1 |
| G-2 | A developer runs a harness's built-in first-class command or skill with one call that returns a thread they can continue or fork. The call never reports success for a run in which the command or skill did not happen. | AC-13 to AC-18, AC-24, AC-29, AC-30, AC-33 and AC-34 pass | Prompt 4, Prompt 5, KD-6, KD-10, §E.2 §2 and "How I'd build it" |
| G-3 | Every new function fails with exactly one detailed `NativeThreadError` whose closed code, likely cause and next step say what to do. | AC-12, AC-19, AC-23 and AC-25 pass | KD-9; #1036 "extensively handle errors for every single function", "error messages need to be in much more detail" |
| G-4 | Nothing #1036 shipped changes behavior. The public surface grows only by the functions and types this spec names. | AC-20 to AC-22 pass, and every #1036 test passes unchanged except the surface pins that §13 lists | KD-3, Prompt 5 ("we recently merged pr 1036") |

## §2 Objective

When this PR merges, `vidbyte.harnesses.native` exports the following, with all the new code under `vidbyte/harnesses/native/{grok,opencode,muse,hostkit}/` and `vidbyte/lib/{dataclasses,enums,constants,errors}/`:

- **47 new async functions (56 in all):**
  - **22 thread helpers:**
    - Grok: list, recent, since, get, read, lineage, search and delete.
    - opencode: the same eight.
    - Muse: list, recent, since, get, read and lineage.
  - **25 command and skill functions:**
    - Grok: the building block `run_grok_command` plus 13 named functions.
    - opencode: the building block `run_opencode_command` plus 3 named functions.
    - Muse: the building block `run_muse_skill`, 5 named functions and `init_muse_workspace`. `init_muse_workspace` is keyless, so in code it lives on the Muse helper class (§12.3 row 26).
- **4 new exported types:**
  - `NativeThreadSummary`, the shared summary record.
  - `NativeCommandOutput`, what `init_muse_workspace` returns.
  - `GrokThreadScope`, which chooses the SDK's private Grok home (`SDK`) or the user's `~/.grok` (`USER`).
  - `GrokCommand`, the closed set of Grok commands that `run_grok_command` runs.
- **Error vocabulary:**
  - 2 new `NativeThreadProblem` members, `command_not_run` and `store_unreadable`.
  - 4 new `FailureCode` members: `grok.command_not_run`, `opencode.command_not_run`, `muse.command_not_run` and `grok.store_unreadable`.
- **Docs:** the harnesses README and the repo map describe the new functions, and they correct #1036's false EC-44 claim.

PR #1036's run, continue and fork keep their argv, environment, home path and errors exactly. Two internal pieces move so the new flows can share them: the Grok home preparation goes to `grok/store.py:GrokHome`, and the Muse private-folder and child handling goes to `muse/children.py:MuseChildren`.

This is the whole accepted catalog. Every catalog row that is not built is listed in §3 with its reason. Deep research, workflows and compaction need a long-running vendor session, which belongs in a later PR.

## §3 Non-goals

- **NG-1** — `get_grok_thread_usage` and any usage, cost, balance, readiness, version or model-list helper. *Why not:* KD-5. In #1036 the owner asked: "why do we even need usage or balance checks inside of the pr?"
- **NG-2** — `run_grok_deep_research` and `run_grok_workflow`. *Why not:* `/deep-research` and `/workflow` run on Grok's background workflow engine and "return right away" (Grok user guide). A one-shot `grok --single` exits when its turn ends, so no record of the work exists when the function would return. They need a long-running `grok agent stdio` (ACP) session, and #1036 NG-2 removed host machinery. They belong in a later PR, for example `start_grok_goal` / `get_grok_goal_status` (§E.1).
- **NG-3** — `compact_grok_thread`, `compact_opencode_thread` and `compact_muse_thread`. *Why not:*
  - **Grok:** `/compact` is CMD ?. When `-p` does not expand it, the call appends a literal "/compact" turn to the user's real thread, which cannot be undone, and no evidence rule can stop that before it happens.
  - **opencode:** compaction exists only in the interactive screen (E.2 §1).
  - **Muse:** MSP `session/compact` is "admission only". Its ack arrives before the work, which "runs asynchronously", and completion arrives only as a later view notification. The summarizer needs a model key inside `serve`, which #1036 runs without one. A short batch `serve` cannot wait for that notification.
  - Optional after a key-bearing probe: Q-1.
- **NG-4** — The ✗ rows of §E.2:
  - Grok: `/pr-babysit`, `/loop`, `/create-skill`, `/create-workflow`.
  - Muse: `/deep-research`, `/goal` as a slash command, `grill`, `grill-and-record`.
  - opencode: the `explore` and `general` agents (subagent-only) and the `customize-opencode` skill (edits opencode's own config).
  - *Why not:* they need a person, run in the background, or (for the opencode rows) E.2 already said "I'd skip the rest".
- **NG-5** — *Withdrawn in r2 (review R-4).* r1 excluded `run_grok_code_review` and `run_grok_imagine_video` on two false claims:
  - `/imagine-video` is documented, and it animates with the `image_to_video` tool (Grok user guide `04-slash-commands.md:275-277`; `features.video_gen` in `26-config-reference.md:290`).
  - The code-review SKILL.md is a 192-line review rubric with no "call no tool" instruction.
  - Both are in the accepted §E.2 catalog, and both are now built (FR-12, D-28).
- **NG-6** — `search_muse_threads` and `delete_muse_thread`. *Why not:*
  - Muse sessions have no title (MSP `Session` has none), so there is nothing to search.
  - Muse has no delete: the CLI has no delete command, and none of the 31 MSP methods deletes (§E.2 §1, verified in `msp.schema.json`).
- **NG-7** — The generic building blocks `run_grok_skill`, `run_opencode_skill` and `run_muse_command`. *Why not:*
  - **Grok:** every user-invocable Grok skill *is* a slash command named after the skill, so `run_grok_command` already is that building block. A "Use the `<skill>` skill." prefix for an arbitrary skill has no evidence rule (KD-6).
  - **opencode:** opencode ships one skill, and E.2 skips it.
  - **Muse:** `muse exec` is verified not to expand slash commands (KD-6), so `run_muse_command` could only ever raise `muse.command_not_run`.
  - Optional: Q-6.
- **NG-8** — Codex and Claude Code. *Why not:* KD-2. Codex belongs to the PR #1055 sibling run, and Claude Code is not on main.
- **NG-9** — Fixing the isolation of the private Grok home, and changing any #1036 default (permission mode, timeout). *Why not:* out of scope per the orchestrator briefing and request.md §C. The false EC-44 statement becomes a documented limitation (§6.3 EC-63, §12.5).
- **NG-10** — Everything in §E.1 section B: worktrees, `--json-schema`, `--agents` JSON, access levels, memory, `inspect`, and the small settings. *Why not:* not accepted (KD-1).
- **NG-11** — Root `vidbyte` exports and any SDK CLI command. *Why not:* this keeps #1036 NG-10 and D-22. Import from `vidbyte.harnesses.native` only.
- **NG-12** — A cross-harness `list_threads(workspace)`. *Why not:* §E.2 says "a later `list_threads` … is just merge and sort", so it is not in this PR. The shared record makes it a one-line caller-side sort (§4).
- **NG-13** — Grok plan, to-do list and goal state in `get_grok_thread`. *Why not:* the shared record is fixed by KD-7. Optional: Q-3.
- **NG-14** — Pagination past one call (cursors) and limits above `NATIVE_LIST_MAX_LIMIT` (200, Muse's own `session/list` maximum). *Why not:* not requested. One bounded page per call.
- **NG-15** — Sanitized or redacted transcripts (`opencode export --sanitize`, `muse export --redacted`). *Why not:* not requested. Optional: Q-5.

## §4 Developer usage

```python
import asyncio
from datetime import timedelta
from pathlib import Path

from vidbyte.harnesses.native import (
    NativeThreadError,
    get_grok_thread_lineage,
    list_grok_threads_since,
    list_recent_opencode_threads,
    run_grok_goal,
)


async def main() -> None:
    repo = Path.cwd()
    try:
        goal = await run_grok_goal("Make the auth test suite pass without changing public endpoints.", api_key="xai-your-key", workspace=repo)
    except NativeThreadError as error:
        print(error.failure_code.value, error.next_step)  # e.g. grok.command_not_run and what to do next
        return
    print(goal.thread_id, goal.text[:200])

    # Every list helper returns the same NativeThreadSummary, so a cross-harness view is one sort.
    day = [*await list_grok_threads_since(repo, timedelta(hours=24)), *await list_recent_opencode_threads(repo)]
    for thread in sorted(day, key=lambda summary: summary.updated_at, reverse=True):
        print(thread.harness.value, thread.updated_at.isoformat(), thread.thread_id, thread.title, thread.parent_thread_id)

    print([summary.thread_id for summary in await get_grok_thread_lineage(goal.thread_id, repo)])


asyncio.run(main())
```

The developer gets back the goal thread's id and answer, or one `NativeThreadError` naming what went wrong. They also get one merged, newest-first list of the last day's Grok threads and recent opencode threads, and the chain of threads the goal thread descends from (root first). They no longer parse `grok sessions list` text, look inside `~/.vidbyte/grok-homes/`, or guess whether `/goal` actually ran.

## §5 Flow diagram

```mermaid
flowchart TD
  subgraph Helpers["Thread helpers (no key, no model)"]
    H1[public helper e.g. list_grok_threads] -->|raw args| H2[Harness ThreadHelpers._call]
    H2 -->|NativeHelperRequest| H3{harness}
    H3 -->|Grok: scope home| G1[GrokStore.threads for list and search<br/>GrokStore.thread for one id<br/>reads summary.json in to_thread]
    H3 -->|Grok read/delete| G2[CliRunner: grok export / sessions delete<br/>GROK_HOME=scope home, no key]
    H3 -->|opencode| O1[CliRunner: opencode session list / db / export / session delete<br/>cwd+PWD=workspace]
    H3 -->|Muse| M1[MuseChildren: private config folder<br/>muse serve session/list or session/read<br/>muse export --out temp]
    G1 -->|GrokThreadFile| L[NativeThreadListing<br/>since, sort, limit, match, chain]
    G2 -->|CliOutcome| W[harness wire readers]
    O1 -->|CliOutcome| W
    M1 -->|CliOutcome| W
    W -->|NativeThreadSummary| L
    L --> R1[(tuple of NativeThreadSummary / NativeThreadSummary)]
    W --> R2[(NativeThreadResult with whole transcript / None after delete)]
  end
  subgraph Skills["Skill functions (caller's key)"]
    S1[named wrapper e.g. run_grok_goal] -->|text + options| S2[Harness Commands._call]
    S2 -->|NativeThreadRequest + GrokCommandArguments| S3{harness}
    S3 -->|Grok| K1[GrokCommandRun: grok --output-format=streaming-json --session-id=minted uuid4 --single=/goal ...]
    S3 -->|opencode| K2[OpencodeThreadRun.execute with --command=name]
    S3 -->|Muse| K3[MuseThreadRun.execute with skill prompt, then serve session/read items]
    K1 -->|tool calls / agent_name / export text for code-review| E[NativeCommandEvidence.require]
    K3 -->|tool call items| E
    K2 -->|Command not found marker| X[opencode.command_not_run]
    E -->|evidence found| R3[(NativeThreadResult)]
    E -->|missing| X2[harness.command_not_run with new thread id]
  end
```

**Helpers.** Every public function validates all its arguments in one record (`NativeHelperRequest` for helpers; `NativeThreadRequest` plus `GrokCommandArguments` for skill functions) inside the single guarded `_call`, before any file is read or any process starts (INV-3). After that:

- **Grok list, get, lineage and search** read files only, inside `asyncio.to_thread`. List and search scan every `summary.json` in scope. Get and lineage read only the named thread's file, plus each parent's file for lineage (D-27).
- **Grok read and delete, and every opencode and Muse helper,** start one short-lived vendor child per vendor request. Each child is bounded by `NATIVE_CONTROL_TIMEOUT_SECONDS`, and its environment holds no key.
- **Wire readers** turn each child's outcome into a `NativeThreadSummary`, a whole-document `NativeThreadResult`, or a mapped failure.

**Skill functions** run through the same launch path as #1036 runs:

- **Grok:** a streaming JSON run in the private home.
- **opencode:** #1036's own run flow, with `--command`.
- **Muse:** #1036's own exec flow, with the skill named in the prompt.

`NativeCommandEvidence` then checks that run's own record. **Failures:**

- Every failure is caught where it is observed and raised as a `NativeThreadError` built by `NativeErrorFactory`.
- `_call` re-raises those errors unchanged and passes cancellation through.
- `_call` maps a refused argument to `configuration.invalid_argument`, and any defect to `runtime.error`.

---

## Part B — Behavior (this is the spec; everything else is framing)

## §6 Behavior

### 6.1 Invariants

- **INV-1** — **Exact public surface.**
  - **Native package.** `vidbyte.harnesses.native.__all__` is exactly #1036's 17 names plus the 47 functions of §8.5 plus `NativeThreadSummary`, `NativeCommandOutput`, `GrokThreadScope` and `GrokCommand`: 68 names, in a literal sorted list.
  - **Subpackages.** `grok.__all__` holds exactly its 25 functions, `opencode.__all__` its 15 and `muse.__all__` its 16.
  - **Root.** No name is added to `vidbyte`'s or `vidbyte.harnesses`' `__all__`, and `import vidbyte` still leaves `vidbyte.harnesses.native` unloaded.
  - This amends #1036 INV-1 and keeps its INV-23.
- **INV-2** — **Helpers are keyless and model-free.** No thread helper takes an `api_key` parameter, reads a key, or calls a model:
  - **Grok children** run with `XAI_API_KEY` and `GROK_CODE_XAI_API_KEY` removed from the inherited environment.
  - **Muse children** (serve, export, init) run with `META_API_KEY` removed.
  - **opencode children** get no `OPENCODE_CONFIG_CONTENT`.
- **INV-3** — **Validation comes first.** Every argument of every new function is validated before any process starts and before any file is read, created or removed. A refusal is `NativeThreadError` with `failure_code == FailureCode.CONFIGURATION_INVALID_ARGUMENT`, and its message names the public parameter exactly as spelled in the §8.5 signature. That covers `limit`, `since`, `query`, `scope`, `thread_id`, `workspace`, `objective`, `task`, `effort`, `branch`, `skill`, `command`, `config` and so on.
- **INV-4** — **Read helpers write nothing.** The read helpers are `list_*`, `list_recent_*`, `*_since`, `get_*`, `read_*`, `get_*_lineage` and `search_*`. They never create, modify or remove a file in the workspace, in `~/.vidbyte/grok-homes/`, or in `~/.grok`, with two exceptions:
  - `read_muse_thread` creates one SDK temp folder and removes it before returning.
  - A vendor child (`grok export`, `opencode export`, `muse serve`) may write its own logs or state.
  - A Grok private home that does not exist is reported as an empty list or as `grok.thread_not_found`, and it is never created.
- **INV-5** — **Error contract.** Every failure of a new function surfaces as exactly one `NativeThreadError`:
  - `operation` is that function's own `NativeThreadOperation` member (value equals the function's name), and `harness` is its harness.
  - `failure_code` comes from the closed tables.
  - The message is in #1036 INV-5 order: summary, workspace, thread id when known, observation and detail, scrubbed vendor text (at most `NATIVE_VENDOR_MESSAGE_MAX_CHARS`), likely cause, next step.
  - `CancelledError` propagates unchanged.
  - No other exception type escapes any new function.
- **INV-6** — **Vendor data is read strictly.** Vendor data the SDK cannot read raises `<harness>.protocol_mismatch` whose message names the member, and for Grok also the `summary.json` path. That covers:
  - a missing required member, or a member of the wrong type;
  - a timestamp that is not RFC 3339 with an offset (or, for opencode, an integer of epoch milliseconds);
  - an unusable thread id, a title over `NATIVE_TITLE_MAX_CHARS`, or a model id the pattern refuses;
  - a `summary.json` over `GROK_SUMMARY_MAX_BYTES`, and a JSON-RPC `-32601` (method not found) answer.
  - Such data is never silently skipped, never yields a partial result, and is never reported as `configuration.invalid_argument`. The only exceptions are:
    - the skip rule of EC-11, which EC-67 bounds;
    - the skip rule of EC-12;
    - the non-session entries of EC-66.
  - **Scope of the strict read (D-27):**
    - List, recent, since and search read the whole store in scope strictly.
    - An operation on one id reads only that id's `summary.json`, plus each parent's file for lineage. These operations are get, read, delete and lineage, and the plan and explore evidence.
    - So another thread's corrupt, oversize or half-written file cannot fail an operation on one id (EC-68).
- **INV-7** — **Listing.** Every list and search helper returns a tuple of `NativeThreadSummary`:
  - **Order:** newest `updated_at` first; ties broken by `thread_id` in descending string order.
  - **Uniqueness:** no `thread_id` appears twice. A duplicate keeps the entry with the newer `updated_at`.
  - **Limit:** at most `limit` items.
  - **Since:** when `since` is given, only threads with `updated_at >= now - since`, where `now = datetime.now(UTC)` is taken once per call.
  - **Wrapper equivalence:** `list_recent_<h>_threads(ws, limit=n)` returns exactly what `list_<h>_threads(ws, limit=n)` returns, and `list_<h>_threads_since(ws, d, limit=n)` exactly what `list_<h>_threads(ws, since=d, limit=n)` returns, for the same store state. The other parameters (`scope`, `config`) take their defaults or the same values in both calls.
- **INV-8** — **Skill evidence.** A Grok or Muse command or skill function returns only when the evidence rule of §9.2 matched in the record of the run it just made:
  - For Grok, the record is that run's streaming JSON tool calls. For the plan and explore agents it is the run's own `summary.json` `agent_name`, and for code-review its own `grok export` transcript (D-28).
  - For Muse, the record is that thread's `session/read` items.
  - Otherwise it raises `<harness>.command_not_run`, whose `thread_id` is the new thread's id, so the caller can read, continue or delete it.
  - opencode functions rely on opencode's own command dispatch (D-8): an unknown `--command` raises `opencode.command_not_run`.
- **INV-9** — **No caller value becomes a flag.**
  - Every thread id passes `NATIVE_THREAD_ID_PATTERN` (first character alphanumeric, no `/`, `\`, `.` or whitespace) before it is placed on argv or used as a folder name.
  - Command and skill names pass `NATIVE_COMMAND_PATTERN`.
  - A search query never reaches argv.
  - The only caller value inside the `opencode db` SQL is a thread id that passed `NATIVE_THREAD_ID_PATTERN` (`^[A-Za-z0-9][A-Za-z0-9_-]*$`, so no quote, space or semicolon). The rest of the query is the constant `OPENCODE_SESSION_QUERY` (D-26, T-9).
  - Prompts and slash-command arguments travel only inside `--single=`, on stdin, or after a literal `--`, exactly as in #1036.
  - **Inside the slash-command line (D-30).** The text of a named Grok wrapper cannot become a slash-command option. The wrapper refuses:
    - a whitespace-separated token equal to one of *that command's* option flags (`GROK_TEXT_OPTION_FLAGS`: `--budget` for goal, `--effort` for implement, none for the others), or starting with `<flag>=`;
    - a `design_doc` containing whitespace;
    - an `objective` whose stripped, casefolded value is a reserved `/goal` word (`GROK_GOAL_RESERVED_WORDS`: status, pause, resume, clear).
    - `run_grok_command`'s raw `arguments` skip these checks, because they are the caller's own command line.
- **INV-10** — **Lineage.** `get_<h>_thread_lineage(id, ws)` returns a non-empty tuple, root first and ending with the summary of `id`:
  - **Linkage:** for every `i`, `chain[i + 1].parent_thread_id == chain[i].thread_id`.
  - **Root:** `chain[0].parent_thread_id` is `None`, or names a thread that the store no longer has; that case is not an error.
  - **Length:** at most `NATIVE_LINEAGE_MAX_DEPTH`.
  - **Cycles:** a cycle raises `<harness>.protocol_mismatch`.
- **INV-11** — **Delete is exact.** `delete_<h>_thread(id, ws)` returns `None` only after the vendor reported success, and for Grok only after the thread's session folder no longer exists. An id the store does not have raises `<harness>.thread_not_found`, and no delete command is started for a Grok id the store lookup did not find. The SDK itself never removes a vendor file.
- **INV-12** — **Writes** (amends #1036 INV-12 and AC-19). The SDK process itself writes only two kinds of place:
  - the Grok private home of the workspace, which only Grok skill functions and #1036 runs prepare;
  - temp folders it creates with `tempfile.mkdtemp` and removes before returning.
  - Changes to the workspace come only from vendor processes the caller started on purpose: #1036 runs, skill functions, and `init_muse_workspace` with `dry_run=False`.
- **INV-13** — **SDK scope is the runs' home.** `GrokThreadScope.SDK` reads exactly the private home that `run_/continue_/fork_grok_thread` and the Grok skill functions use for the same workspace (`~/.vidbyte/grok-homes/<sha256(normcase(str(resolved workspace)))[:16]>`). `GrokThreadScope.USER` reads `~/.grok`.
- **INV-14** — **Cancellation.** Cancelling any new function:
  - stops its running child;
  - in Muse WSL mode, reaps the child's marked in-distro processes;
  - removes every temp folder the call created;
  - re-raises `CancelledError`.
  - This is the same as #1036 INV-9.
- **INV-15** — **No literals in native modules** (kept from #1036). Every module under `vidbyte/harnesses/native/`, new ones included, holds only docstrings, imports, classes, a literal `__all__` and `name = Class.attr` bindings. The only literals it may use are `""`, `0` and `1`. Every other value comes from `vidbyte/lib/constants/native_threads.py` or an enum.
- **INV-16** — **Bounds.**
  - Every helper child (and the Muse evidence read) runs within `NATIVE_CONTROL_TIMEOUT_SECONDS` and `NATIVE_PROCESS_MAX_OUTPUT_BYTES`.
  - Skill runs use `config.timeout_seconds`, with `NATIVE_PROCESS_MAX_OUTPUT_BYTES` for every harness. For Grok skill runs this cap replaces #1036's `GROK_CLI_MAX_OUTPUT_BYTES`, because the stream carries tool calls.
  - A `summary.json` or `.cwd` file is read only up to its byte cap.
  - A lineage walk takes at most `NATIVE_LINEAGE_MAX_DEPTH` steps.
- **INV-17** — **Self-update off.** Every child has its vendor's self-update disabled: `GROK_DISABLE_AUTOUPDATER=1`, `OPENCODE_DISABLE_AUTOUPDATE=1` or `MUSE_NO_AUTO_UPDATE=1`.
- **INV-18** — **No blocking file I/O on the event loop.** Every directory scan, file read, `mkdtemp`, existence check and removal runs in `asyncio.to_thread`.
- **INV-19** — **Only these thread operations exist** (amends #1036 INV-19). The list, search, read and delete operations in `vidbyte/harnesses/native/` are exactly the helpers of §8.5. No compact, usage, page or other thread-management operation exists.
- **INV-20** — **Layering.**
  - `vidbyte/lib/` imports nothing above `vidbyte.lib`.
  - `hostkit` imports no harness subpackage.
  - The `grok`, `opencode` and `muse` subpackages do not import one another.
- **INV-21** — **A transcript is whole.** `read_<h>_thread` returns the vendor's whole document as `NativeThreadResult.text` with `text_truncated=False`, or it raises `<harness>.output_too_large`. It never returns a cut document.
- **INV-22** — **FailureCode growth.** `FailureCode` keeps every member that the merge base `0f69f7b7` has (148, the same as #1036's `72a4ade1`; verified with the surface test's own `ast` logic), in the same order, and appends exactly `GROK_COMMAND_NOT_RUN`, `OPENCODE_COMMAND_NOT_RUN`, `MUSE_COMMAND_NOT_RUN` and `GROK_STORE_UNREADABLE`, in that order, after `MUSE_WSL_UNAVAILABLE`.
- **INV-23** — **Muse helper children carry no login.** Every Muse helper or evidence child (`serve`, `export`, `init`) runs with a fresh private config folder from `MuseChildren.open_config`: `XDG_CONFIG_HOME` points at it, and `MUSE_AUTH_PATH` points at a file inside it that never exists. `META_API_KEY` is removed and never forwarded through `WSLENV`.
- **INV-24** — **Skill runs launch like #1036 runs.**
  - **Grok:** skill functions run under the private Grok home with the caller's skills. The key travels only in `XAI_API_KEY` and `GROK_CODE_XAI_API_KEY` of the child.
  - **opencode:** the key travels only in the inline config.
  - **Muse:** the key travels only as `META_API_KEY` of the exec child.
  - **All:** the key is registered for scrubbing before any child output is read, and it never appears on argv, in a file, or in an error.
- **INV-25** — **Named wrappers forward.** Each named skill function calls its harness's `_call` exactly once, with the command or skill, text and options of the §9.2 table, and adds no logic of its own.
- **INV-29** — **A Grok command run knows its thread id before it starts (D-29):**
  - `GrokCommandRun` mints a UUID4 and passes it as `--session-id=<id>`.
  - Every error raised after the child started carries that id in `error.thread_id`: it is the id the run *asked* Grok to use.
  - **When the thread is known to exist.** The SDK treats it as existing only in these cases:
    - after the stream showed an `end` or `tool_call` event;
    - for `command_not_run`, `timed_out` and `output_too_large`.
  - **When it may not exist.** In every other case, for example `key_rejected` or a `run_failed` before the session started, the error's detail sentence says "the thread may not exist" (`GROK_THREAD_MAY_NOT_EXIST_DETAIL`; EC-81).
  - An `end.sessionId` that differs from it raises `grok.protocol_mismatch` (`sessionId`).
  - #1036's `run_grok_thread` is unchanged (INV-26).

**Must not regress:**
- **INV-26** — `run_/continue_/fork_<harness>_thread` keep #1036 behavior exactly: argv, environment overlay, private home path and its skills folder, timeouts, caps, codes and behavior. Message texts change only per FR-17 and D-20:
  - the widened texts of FR-17: `THREAD_NOT_FOUND`, `TIMED_OUT` and `OUTPUT_TOO_LARGE` for all three harnesses, plus `OPENCODE_PROTOCOL_MISMATCH`;
  - the generic `expected` of D-20. Today that behavior lives in `vidbyte/harnesses/native/grok/threads.py:GrokThreadRun`, `opencode/threads.py:OpencodeThreadRun`, and `muse/threads.py:MuseThreadRun` with `muse/wire.py:MuseWire.read_answer`. Moving `GrokThreadRun._fallback`, `_prepare_home` and `_environment` into `GrokHome`, and `MuseThreadRun._prepare_config`, `_discard`, `_overlay`, `_serve_invocation` and `_run` into `MuseChildren`, changes no observable value.
- **INV-27** — #1036 INV-1 to INV-23 hold as written, except for the amendments in INV-1, INV-12 and INV-19 above.
- **INV-28** — `tests/test_session_failures.py` keeps passing (every `FailureCode` value contains "."), and so does `tests/test_codex_failure_recovery.py` (only `codex.*` codes).

### 6.2 Acceptance criteria

| ID | Given | When | Then | Priority | Proof |
|---|---|---|---|---|---|
| AC-1 | a clean checkout of this branch. Stand-in `grok` and `opencode` programs are first on PATH: the Grok one answers a streaming run that calls `update_goal` and keeps a real-layout store; the opencode one lists sessions. The workspace is the current directory | the §4 snippet runs | it prints the goal's thread id and text, one line per Grok and opencode thread in newest-first order with `harness`, ISO `updated_at`, id, title and parent, and the lineage list ending with the goal's thread id. It raises nothing | P0 | `test_harness_threads_acceptance_helpers.py::test_the_helpers_example_runs_as_written_against_stand_ins_on_path` |
| AC-2 | a store per harness holding threads with known `updated_at` values (some older than the window, two with equal times, one duplicated id for Grok) | `list_<h>_threads(ws, since=…, limit=…)` | the result obeys INV-7 exactly: window, order, tie-break, uniqueness and limit. With no threads, or no Grok home, the result is `()` | P0 | `test_harness_threads_grok_helpers.py::test_sdk_list_is_newest_first_ties_by_id_descending_window_and_limit`; `test_harness_threads_opencode_helpers.py::test_list_keeps_the_workspace_rows_newest_first_with_ties_by_id_descending`; `test_harness_threads_muse_helpers.py::test_list_sends_session_list_for_the_workspace_and_reorders_ties`; `test_harness_threads_listing_properties.py::test_list_matches_the_inv7_oracle_for_generated_stores` |
| AC-3 | the same stores | `list_recent_<h>_threads` and `list_<h>_threads_since` are called with default and explicit limits | they equal the corresponding `list_<h>_threads` calls (INV-7). The default limits are `NATIVE_RECENT_DEFAULT_LIMIT` and `NATIVE_LIST_DEFAULT_LIMIT` | P0 | `test_harness_threads_grok_helpers.py::test_recent_and_since_wrappers_equal_the_base_list_with_named_default_limits`; `test_harness_threads_opencode_helpers.py::test_recent_and_since_wrappers_equal_the_base_list`; `test_harness_threads_muse_helpers.py::test_recent_and_since_wrappers_equal_the_base_list`; `test_harness_threads_listing_properties.py::test_wrappers_equal_the_base_list_for_generated_stores` |
| AC-4 | a known thread and an unknown well-formed id | `get_<h>_thread` | the known id returns its `NativeThreadSummary`, with fields mapped per §9.1. The unknown id raises `<harness>.thread_not_found`, with that id in the message and `error.thread_id` | P0 | `test_harness_threads_grok_helpers.py::test_get_maps_summary_json_and_an_unknown_id_is_thread_not_found`; `test_harness_threads_opencode_helpers.py::test_get_runs_one_db_query_for_the_id_and_maps_its_row`; `test_harness_threads_muse_helpers.py::test_get_reads_one_session_without_items_and_unknown_is_thread_not_found` |
| AC-5 | a known thread | `read_<h>_thread` | it returns `NativeThreadResult(harness, thread_id, text=<the vendor document byte-for-byte as UTF-8 text>, text_truncated=False)`. A document over the cap raises `<harness>.output_too_large`. An unknown id raises `thread_not_found` | P0 | `test_harness_threads_grok_helpers.py::test_read_returns_the_export_document_whole_through_a_keyless_child`; `test_harness_threads_opencode_helpers.py::test_read_returns_the_export_document_whole`; `test_harness_threads_muse_helpers.py::test_read_exports_into_an_empty_temp_folder_and_returns_the_file_whole` |
| AC-6 | a chain root ← fork ← fork-of-fork (for opencode, a subagent chain root ← child ← grandchild, because opencode forks record no parent: EC-76), plus a thread whose parent is missing, and corrupt data forming a cycle | `get_<h>_thread_lineage` | the chain is root-first and ends with the requested thread (INV-10). A missing parent ends the chain without error. A cycle raises `protocol_mismatch` | P0 | `test_harness_threads_grok_helpers.py::test_lineage_is_root_first_linked_and_ends_at_a_missing_parent`; `test_harness_threads_grok_helpers.py::test_lineage_cycle_and_a_chain_past_the_depth_cap_are_protocol_mismatch`; `test_harness_threads_opencode_helpers.py::test_lineage_follows_parent_id_through_subagent_children_lists_never_show`; `test_harness_threads_muse_helpers.py::test_lineage_follows_forked_from_objects_one_serve_per_step`; `test_harness_threads_acceptance_helpers.py::test_threads_made_by_the_run_functions_are_the_ones_the_helpers_see` |
| AC-7 | Grok threads whose title, summary or last-turn summary contain a query in a different letter case, and opencode threads whose titles do | `search_grok_threads` / `search_opencode_threads` | exactly the matching threads come back, ordered and limited per INV-7. Regex characters in the query match literally | P0 | `test_harness_threads_grok_helpers.py::test_search_is_a_literal_case_insensitive_match_over_title_and_both_summaries`; `test_harness_threads_opencode_helpers.py::test_search_matches_titles_literally_and_case_insensitively`; `test_harness_threads_listing_properties.py::test_search_matches_the_literal_case_insensitive_oracle` |
| AC-8 | a known thread | `delete_<h>_thread` | it returns `None` and the thread no longer lists. For Grok, a stand-in that exits 0 but leaves the folder raises `grok.run_failed`. An unknown id raises `thread_not_found`, and for Grok no delete child starts | P0 | `test_harness_threads_grok_helpers.py::test_delete_removes_the_session_folder_and_checks_that_it_is_gone`; `test_harness_threads_opencode_helpers.py::test_delete_runs_session_delete_and_the_thread_no_longer_lists` |
| AC-9 | Grok threads in the private home of `ws`, in `~/.grok` for `ws`, and in `~/.grok` for another workspace | the Grok helpers run with `scope=GrokThreadScope.SDK` and with `scope=GrokThreadScope.USER` | SDK sees only the private-home threads. USER sees only `~/.grok` threads whose group folder decodes (or whose `.cwd` names) to `ws` | P0 | `test_harness_threads_grok_helpers.py::test_sdk_scope_reads_the_private_home_and_user_scope_the_users_own_store` |
| AC-10 | the caller's environment holds `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY` and `META_API_KEY` | any helper starts a child | the child's environment holds none of them, and no helper signature has an `api_key` parameter | P0 | `test_harness_threads_helper_credentials.py::test_helper_children_carry_no_key_even_when_the_caller_has_one`; `test_harness_threads_muse_helpers.py::test_every_helper_child_gets_a_fresh_private_config_and_no_login` |
| AC-11 | a snapshot of the workspace, `~/.vidbyte` and `~/.grok` | any read helper runs (including on a workspace with no Grok home) | the snapshot is unchanged afterwards, apart from what the stand-in vendor wrote in its own store, and no temp folder remains | P0 | `test_harness_threads_helper_credentials.py::test_read_helpers_write_nothing_and_leave_no_temp_folder`; `test_harness_threads_helper_credentials.py::test_user_scope_without_a_grok_store_lists_nothing_and_creates_nothing` |
| AC-12 | each new function, and each invalid value of its parameters listed in §9.2 (wrong type, `True` for an int, out of range, blank, NUL, pattern miss, both `branch` and `pr`, relative `design_doc`, a `design_doc` with whitespace, `run_grok_goal` text with `--budget 9` or `--budget=9`, `run_grok_implement` text with `--effort 5`, a reserved `/goal` word as `objective`, `config` of another harness; on win32, Grok or Muse text whose quoted command-line units exceed the D-25 budget) | it is called | it raises `configuration.invalid_argument` naming that parameter, no child process starts, and nothing is written. Text that names another command's flag passes, for example `run_grok_implement("Add a --dry-run flag")` and `run_grok_design("Design --local and --branch modes")` (R-19) | P0 | `test_harness_threads_helper_arguments.py::test_every_skill_function_refuses_its_invalid_arguments`; `test_harness_threads_helper_arguments.py::test_one_id_helpers_refuse_a_bad_thread_id`; `test_harness_threads_helper_arguments.py::test_text_that_names_another_commands_flag_still_runs` |
| AC-13 | a stand-in grok | each Grok command function runs | grok gets one `--single=` prompt equal to the §9.2 line for that function, plus `--output-format=streaming-json`, one `--session-id=<uuid4>`, the #1036 options, and `--agent=<name>` for plan and explore. `GROK_WORKFLOWS=0` appears only for `run_grok_goal` / `GrokCommand.GOAL`. The key is in the environment only | P0 | `test_harness_threads_grok_commands.py::test_each_command_function_sends_its_line_with_a_minted_session_id`; `test_harness_threads_grok_commands.py::test_run_grok_command_sends_the_raw_line` |
| AC-14 | a stand-in grok stream with, and then without, the §9.2 evidence | a Grok command function runs | with evidence it returns `NativeThreadResult` with the minted id (equal to the stream's `end.sessionId`) and the final text. Without it, it raises `grok.command_not_run`, whose `thread_id` is that id and whose message lists the tools the run did call. An `end.sessionId` that differs from the minted id raises `grok.protocol_mismatch` | P0 | `test_harness_threads_grok_commands.py::test_missing_evidence_is_command_not_run_with_the_minted_id_and_the_tools_seen`; `test_harness_threads_grok_commands.py::test_evidence_variants_that_count` |
| AC-15 | a store whose new thread's `summary.json` has `agent_name` equal to `plan`, then a different one, then none | `run_grok_plan` / `run_grok_explore` | it returns when the value is equal; otherwise it raises `grok.command_not_run` | P0 | `test_harness_threads_grok_commands.py::test_agent_runs_need_the_agent_name_in_the_new_threads_summary` |
| AC-16 | a stand-in opencode | `run_opencode_command("name", "args")`, `run_opencode_review`, `run_opencode_init` and `run_opencode_plan` run | argv carries `run --command=<name>` (or `--agent=plan` for plan) with #1036's options. The arguments arrive on stdin, and stdin is empty when there are no arguments. An error event whose message starts with `Command not found: "<name>"` (opencode 1.18.31's text, followed by "Available commands: …"), or that text on stderr, raises `opencode.command_not_run` | P0 | `test_harness_threads_opencode_commands.py::test_command_functions_send_the_command_on_argv_and_the_arguments_on_stdin`; `test_harness_threads_opencode_commands.py::test_an_unknown_command_is_command_not_run` |
| AC-17 | a stand-in muse whose thread items do, and then do not, include the §9.2 tool call | `run_muse_skill` and each named Muse function run | exec gets the §9.2 prompt after `--`. With evidence the call returns the exec thread's result; without it, it raises `muse.command_not_run` with that thread id. A history in mode `none` also raises `muse.command_not_run`, naming its `noneReason` | P0 | `test_harness_threads_muse_commands.py::test_skill_functions_send_the_prompt_and_return_after_the_evidence_read`; `test_harness_threads_muse_commands.py::test_missing_evidence_is_command_not_run_with_the_new_thread`; `test_harness_threads_muse_commands.py::test_history_mode_none_fails_closed_naming_the_reason` |
| AC-18 | a stand-in muse | `init_muse_workspace(ws)` and `init_muse_workspace(ws, dry_run=True)` | the child runs `muse init` (plus `--dry-run`) in `ws` with no key, and the call returns `NativeCommandOutput(harness=MUSE, text=<stdout>)`. A non-zero exit raises `muse.run_failed` with Muse's message | P1 | `test_harness_threads_muse_helpers.py::test_init_runs_muse_init_in_the_workspace_and_returns_its_stdout`; `test_harness_threads_muse_helpers.py::test_init_where_muse_is_already_set_up_is_run_failed_with_muses_text` |
| AC-19 | vendor data with a missing or mistyped member, a naive or garbled timestamp, an oversize `summary.json`, a non-JSON answer, and a `-32601` answer | the reading helper runs | it raises `<harness>.protocol_mismatch` naming the member (and the file for Grok), and never returns a partial list | P0 | `test_harness_threads_grok_helpers.py::test_unreadable_summary_json_is_protocol_mismatch_naming_the_file_and_member`; `test_harness_threads_opencode_helpers.py::test_malformed_list_output_is_protocol_mismatch_naming_the_member`; `test_harness_threads_muse_helpers.py::test_unusable_session_shapes_are_protocol_mismatch_never_a_partial_list` |
| AC-20 | this branch | the surface is inspected | the INV-1 export lists, the §9.1 enum members in order, and INV-22 (148 + 4) hold. Each new code has its own likely-cause and next-step texts, unique within its harness. The widened `TIMED_OUT` and `OUTPUT_TOO_LARGE` texts (FR-17) name the fixed control timeout for helpers and the transcript case, and the Grok `OUTPUT_TOO_LARGE` cause names both caps. No new text tells a helper caller to raise `timeout_seconds` | P0 | `test_harness_threads_surface.py::test_native_package_exports_exactly_the_thread_functions_helpers_skills_and_their_records`; `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_32_harness_codes`; `test_harness_threads_helper_surface.py::test_new_codes_have_their_own_complete_texts` |
| AC-21 | this branch | the #1036 test files run | every #1036 test passes. The only #1036 assertions edited are the surface and errors pins of §13 (exports, enum lists, codes, the stale `120` at line 193 and the stale total at line 195), and they are edited by S2 only | P0 | the 431 unedited #1036 tests in `tests/features/harness_threads/` (red run: 0 of them fail) |
| AC-22 | this branch | `python lint/run.py`, then `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package`, then the semgrep policy scan | lint ends `AGENT-LINT: PASS` with `lint/baseline.json` unchanged, and every stage passes | P0 | gate, not a test: `python lint/run.py` and `scripts/run_ci.py` at S3/S4 |
| AC-23 | any helper or skill function mid-child (Muse in WSL mode included) | the awaiting task is cancelled | `CancelledError` propagates, the child is stopped (and reaped in WSL), and no temp folder remains (INV-14) | P0 | `test_harness_threads_helper_bounds.py::test_cancelling_a_helper_mid_child_stops_it_and_removes_its_temp_folder`; `test_harness_threads_helper_bounds.py::test_cancelling_a_skill_run_mid_child_stops_it`; `test_harness_threads_helper_bounds.py::test_cancelling_a_muse_helper_in_wsl_mode_reaps_with_its_mark` |
| AC-24 | a skill function run with a recognisable fake key whose stand-in vendor echoes its environment and argv into every output | the call fails and succeeds | the key appears in no argv element, no file the SDK wrote, and no error message or attribute (INV-24) | P0 | `test_harness_threads_helper_credentials.py::test_an_echoed_key_reaches_no_error_text_argv_or_file_when_the_run_fails`; `test_harness_threads_helper_credentials.py::test_a_successful_skill_run_puts_the_key_in_no_argv_and_no_file` |
| AC-25 | a missing vendor program, a Windows batch launcher, a hung child, an output flood and a non-zero exit | any helper runs | it raises `not_installed`, `launcher_refused`, `timed_out` (after `NATIVE_CONTROL_TIMEOUT_SECONDS`), `output_too_large` and `run_failed` respectively, for its harness, with #1036's message order | P0 | `test_harness_threads_helper_bounds.py::test_a_missing_program_is_not_installed`; `test_harness_threads_helper_bounds.py::test_a_batch_launcher_is_refused_and_never_runs`; `test_harness_threads_helper_bounds.py::test_a_hung_helper_child_is_timed_out_after_the_control_timeout`; `test_harness_threads_helper_bounds.py::test_a_helper_child_past_the_output_cap_is_output_too_large`; `test_harness_threads_helper_bounds.py::test_a_failing_helper_child_is_run_failed_with_the_vendor_text` |
| AC-26 | this branch | `vidbyte/harnesses/README.md` and `REPO_MAP.md` are read | the `native/` bullet names the helper families, the Grok scopes, the skill functions, the evidence rule, `command_not_run`, the excluded rows, and that subagent child threads list as ordinary threads (EC-72). The sentence "SDK Grok runs read nothing from `~/.grok`" (#1036 EC-44) is gone and is replaced by the verified limitation (EC-63, T-6). The README stays ≤ 40,000 characters (A009). The `REPO_MAP.md` `vidbyte/harnesses/native/` entry names listing, reading, lineage, search, delete and verified command runs. Proven by review (S4), not by a test | P1 | review (S4) |
| AC-27 | a real-layout Grok store per scope that also holds `sessions/session_search.sqlite`, a `<group>/permission.toml`, a `<group>/permission_cli.toml` and a `<group>/.cwd` file | every Grok list, search, get, read, lineage and delete helper runs | the files are ignored and the results equal those of the same store without them. A store whose session folders all lack `summary.json`, the newest older than `GROK_SUMMARY_GRACE_SECONDS`, raises `grok.protocol_mismatch` naming the expected layout. The same store with its newest folder younger than that returns `()` | P0 | `test_harness_threads_grok_helpers.py::test_non_session_files_in_a_real_store_change_no_result`; `test_harness_threads_grok_helpers.py::test_store_whose_folders_all_lack_summary_json_is_a_layout_mismatch_after_the_grace_period` |
| AC-28 | a Grok store holding thread A and a sibling B whose `summary.json` is invalid JSON, then oversize | `get_grok_thread(A)`, `read_grok_thread(A)`, `get_grok_thread_lineage(A)`, `delete_grok_thread(A)`, and the evidence step of `run_grok_plan` whose new thread is A | each succeeds as if B were absent. `list_grok_threads` and `search_grok_threads` on the same store raise `grok.protocol_mismatch` naming B's file (INV-6) | P0 | `test_harness_threads_grok_helpers.py::test_one_id_operations_read_only_their_own_file_while_scans_stay_strict`; `test_harness_threads_grok_commands.py::test_agent_evidence_ignores_a_corrupt_sibling_thread` |
| AC-29 | a stand-in grok that never ends, then one that floods stdout past `NATIVE_PROCESS_MAX_OUTPUT_BYTES` before `end` | a Grok command function runs with a short `config.timeout_seconds` | it raises `grok.timed_out`, then `grok.output_too_large`, each with `error.thread_id` equal to the `--session-id` value on argv (INV-29). A stand-in that prints an `error` event with a not-signed-in marker before any session event raises `grok.key_rejected`, with that id and a detail saying the thread may not exist | P0 | `test_harness_threads_grok_commands.py::test_a_run_past_its_timeout_is_timed_out_with_the_minted_id`; `test_harness_threads_grok_commands.py::test_a_stream_past_the_output_cap_is_output_too_large_with_the_minted_id`; `test_harness_threads_grok_commands.py::test_a_failure_before_the_session_exists_says_the_thread_may_not_exist` |
| AC-30 | a stand-in grok for `run_grok_imagine_video` whose stream does, then does not, call `image_to_video`; and one for `run_grok_code_review` whose `grok export` transcript does, then does not, contain `GROK_CODE_REVIEW_FRAGMENT` | each runs | the line is `/imagine-video <t>`, or `/code-review`. With evidence each returns the run's result. Without it each raises `grok.command_not_run` with the minted id. The code-review export child carries no key and runs under the run's private home | P0 | `test_harness_threads_grok_commands.py::test_code_review_reads_its_own_export_through_a_keyless_child`; `test_harness_threads_grok_commands.py::test_a_failed_code_review_export_carries_the_minted_id`; `test_harness_threads_grok_commands.py::test_missing_evidence_is_command_not_run_with_the_minted_id_and_the_tools_seen` |
| AC-31 | an opencode stand-in that logs each child and keeps sessions in a SQLite file with opencode's `session` columns (`id`, `title`, `time_created`, `time_updated`, `parent_id`, `directory`); a subagent chain of depth 3 whose children are absent from `session list` (roots only) | `get_opencode_thread` and `get_opencode_thread_lineage` | get starts exactly one `opencode db --format=json <OPENCODE_SESSION_QUERY>` child, and lineage one per step. Neither starts a `session list` or `export` child. A child id is found, and the chain follows `parent_id` root-first (INV-10). An id with no row raises `opencode.thread_not_found` | P0 | `test_harness_threads_opencode_helpers.py::test_get_runs_one_db_query_for_the_id_and_maps_its_row`; `test_harness_threads_opencode_helpers.py::test_lineage_follows_parent_id_through_subagent_children_lists_never_show` |
| AC-32 | an opencode stand-in whose `session list` honours `--max-count` (default 100) and lists roots only | `list_opencode_threads(ws, limit=150)` on a project with 300 roots, then on a project with exactly `NATIVE_OPENCODE_SCAN_MAX` roots | the child gets `--max-count=NATIVE_OPENCODE_SCAN_MAX`, and the first call returns 150 threads. The second raises `opencode.protocol_mismatch`, whose detail names the cap (EC-75), never a short list | P0 | `test_harness_threads_opencode_helpers.py::test_list_asks_for_the_scan_cap_and_refuses_a_list_cut_at_it` |
| AC-33 | `run_grok_review(..., skills=[<folder named "review">])` and `run_grok_design(..., skills=[<folder named "design">])` | each is called | each raises `configuration.invalid_argument` naming `skills`, and no child starts (D-32). A `skills` folder with any other name passes | P0 | `test_harness_threads_grok_commands.py::test_a_skills_folder_named_like_the_command_is_refused_before_any_run`; `test_harness_threads_grok_commands.py::test_a_skills_folder_with_another_name_passes` |
| AC-34 | a stand-in muse whose evidence `session/read` returns history mode `anchoredSnapshot` without the `read_skill` item, and whose `muse export` transcript does, then does not, contain the `read_skill` call with the skill id | `run_muse_plan` runs | with the call in the transcript it returns the run's result. Without it, it raises `muse.command_not_run`, whose cause names compaction (D-33) | P0 | `test_harness_threads_muse_commands.py::test_after_compaction_the_evidence_comes_from_the_export_transcript`; `test_harness_threads_muse_commands.py::test_after_compaction_a_transcript_without_the_call_is_command_not_run_naming_compaction` |

### 6.3 Edge cases and failure modes

| ID | Trigger (input + state) | System behavior | User sees | Guarded by (INV-/D-) |
|---|---|---|---|---|
| EC-1 | `list_grok_threads(ws)` on a workspace the SDK never ran Grok in, so no private home exists | Returns `()` without calling `mkdir`. Without the guard, every browsed path would leave an empty `~/.vidbyte/grok-homes/<key>` behind | `()` | INV-4, D-11 |
| EC-2 | `limit` = `0`, `-1`, `201`, `2.5`, `"5"` or `True` | Refused before any read. Without the guard, `True` passes an `isinstance(int)` check as 1 | `configuration.invalid_argument` naming `limit` | INV-3, D-1 |
| EC-3 | `since` = `24` (an int), `timedelta(0)` or a negative timedelta | Refused. Without the guard, `24` is ambiguous (hours or seconds), and `0` silently lists nothing | invalid_argument naming `since` | INV-3 |
| EC-4 | `since=timedelta.max` | Refused above `NATIVE_SINCE_MAX`. Without the guard, `now - since` raises `OverflowError`, which would surface as `runtime.error` | invalid_argument naming `since` | INV-3 |
| EC-5 | `thread_id` = `"../../etc"`, `"-rf"`, `"a b"`, `""` or `"x' OR '1'='1"` | Refused by `NATIVE_THREAD_ID_PATTERN`. Without the guard, a Grok id becomes a path outside the store, an opencode or grok id becomes a flag, and a quote would change the `opencode db` SQL (T-9) | invalid_argument naming `thread_id` | INV-9 |
| EC-6 | `query` = `""`, `"   "`, one containing NUL, or longer than `NATIVE_QUERY_MAX_CHARS` | Refused | invalid_argument naming `query` | INV-3 |
| EC-7 | `query="fix.*bug"` | Matched as a literal, case-insensitive substring | only threads containing `fix.*bug` literally | D-3 |
| EC-8 | a `summary.json` without `created_at` | Raises. Without the guard, the thread silently disappears from every list | `grok.protocol_mismatch` naming the file and `created_at` | INV-6 |
| EC-9 | a `summary.json` holding a JSON array, invalid JSON, or invalid UTF-8 | Raises | `grok.protocol_mismatch` naming the file | INV-6 |
| EC-10 | a `summary.json` larger than `GROK_SUMMARY_MAX_BYTES` | Its size is taken with `os.fstat` and the file is not parsed. Without the guard, a corrupted multi-GB file is read into memory | `grok.protocol_mismatch` naming the file and its size | INV-6, INV-16 |
| EC-11 | a session folder with no `summary.json` yet (grok is still creating it) | That folder is skipped, within the bound of EC-67. Without the skip, every list fails while any run is starting | the thread is absent until grok writes it | INV-6 (stated exception) |
| EC-12 | a session folder removed between the directory scan and the read (`FileNotFoundError`) | Skipped | the thread is absent | INV-6 (stated exception) |
| EC-13 | a `summary.json` or `.cwd` that raises `PermissionError` or another `OSError`, or `Path.home()` raising `RuntimeError` | Raises | `grok.store_unreadable` naming the path (or the unknown home) and the error class | D-12 |
| EC-14 | a naive timestamp such as `"2026-10-15T12:00:00"` | Refused by `to_utc_datetime`. Without the guard, comparing naive and aware datetimes raises `TypeError`, which would surface as `runtime.error` | `<h>.protocol_mismatch` naming the member | INV-6, D-13 |
| EC-15 | timestamps in different offsets (`+02:00` and `Z`) | Normalized to UTC, then compared. Without that, string order would misorder the threads | correct newest-first order | INV-7, D-13 |
| EC-16 | two threads with equal `updated_at` | Ordered by `thread_id`, descending | a deterministic order across calls | INV-7 |
| EC-17 | USER scope where the same id appears under two group folders (two encodings of one path) | Kept once, with the newer `updated_at` | one entry | INV-7 |
| EC-18 | USER scope while `~/.grok/sessions` does not exist | Returns `()` and creates nothing | `()` | INV-4 |
| EC-19 | USER scope on Windows with a group whose decoded path differs from `ws` only in letter case or slash direction | Matched, because both sides go through `os.path.normcase` (on POSIX, case still matters) | the thread is listed on Windows | D-21, A-4 |
| EC-20 | `get_grok_thread(id, ws)` where `id` exists only in `~/.grok` but the scope is SDK | Not found in scope. The detail names the scope and the home that was searched | `grok.thread_not_found` | INV-13 |
| EC-21 | `read_grok_thread`, where the thread is deleted after the store check but before `grok export` runs, so export prints `Session '<id>' not found.` | Mapped | `grok.thread_not_found` | D-16 |
| EC-22 | a transcript export larger than `NATIVE_PROCESS_MAX_OUTPUT_BYTES` | Raises and never returns a cut document | `<h>.output_too_large` | INV-21 |
| EC-23 | `grok sessions delete` exits 0 but the session folder still exists (it asked for confirmation, or talked to a leader of another home) | The post-check fails. Without it, the caller believes the thread is deleted | `grok.run_failed`, whose detail names the folder that still exists | INV-11, D-16 |
| EC-24 | `delete_*` of a thread that a concurrent `continue_*` is using | Vendor behavior; the SDK takes no lock | whatever the vendor does; documented limitation | limitation (vendor-owned; the SDK adds no lock) |
| EC-25 | lineage where a parent was deleted | The chain stops. `chain[0].parent_thread_id` names the missing id | a shorter chain whose head shows a dangling parent | INV-10, D-23 |
| EC-26 | lineage over corrupt data where A's parent is B and B's parent is A | Detected when an id repeats. Without the check, the walk never ends | `<h>.protocol_mismatch`, whose detail names the repeated id | INV-10 |
| EC-27 | a lineage deeper than `NATIVE_LINEAGE_MAX_DEPTH` | Stops and raises | `<h>.protocol_mismatch` naming the depth cap | INV-10, INV-16 |
| EC-28 | opencode helpers in a directory outside any git project (opencode's "global" project) | opencode lists the global project's sessions. The SDK keeps rows whose `directory` equals `ws` | only `ws`'s threads | D-19 |
| EC-29 | `opencode session list` prints nothing, or `[]` | Treated as no threads | `()` | A-12 |
| EC-30 | an opencode list row whose `updated` is a string, or whose `id` is missing | Raises | `opencode.protocol_mismatch` naming the member | INV-6 |
| EC-31 | the caller's inherited `PWD` names another project | `PWD` is overlaid with `ws`, and cwd is `ws`. Without that, opencode would list another project's threads | `ws`'s threads | D-22 |
| EC-32 | opencode `read` or `delete` of an unknown id (stderr contains `Session not found: <id>`), or `get` / `lineage` whose `db` query returns `[]` | Mapped | `opencode.thread_not_found` | INV-11, D-26 |
| EC-33 | opencode or grok is not installed, or the program found first is a `.cmd` shim | #1036 launcher resolution | `<h>.not_installed` / `<h>.launcher_refused` | INV-5 |
| EC-34 | Muse helpers on Windows with neither `wsl_distro` nor `muse_command` set in config | `MuseLauncher.resolve` refuses | `muse.wsl_unavailable` | INV-5 |
| EC-35 | `get_muse_thread` / `read_muse_thread` of an unknown id (JSON-RPC `-32020`) | Mapped; `muse export` never starts | `muse.thread_not_found` | D-17 |
| EC-36 | an installed Muse that lacks `session/list` (answers `-32601`) | Mapped to a version mismatch | `muse.protocol_mismatch` naming `session/list` | INV-6 |
| EC-37 | `muse serve` hangs (WSL cold start or a stuck distro) | Stopped after `NATIVE_CONTROL_TIMEOUT_SECONDS`, then reaped in the distro | `muse.timed_out` | INV-16, INV-14 |
| EC-38 | `muse export` exits non-zero, or writes no file | Raises, and the temp folder is removed | `muse.run_failed`, or `muse.protocol_mismatch` naming the missing file | D-17 |
| EC-39 | the export file is larger than `NATIVE_PROCESS_MAX_OUTPUT_BYTES` | Its size is taken with `os.fstat` and it is not read | `muse.output_too_large` | INV-21 |
| EC-40 | a file named like the thread id exists in the caller's cwd (`muse export --session` prefers an existing path over an id) | Export runs with cwd set to an empty SDK temp folder, so no such file can exist there | the right thread | D-17 |
| EC-41 | `run_grok_goal` on a Grok whose `-p` does not expand slash commands | The model answers "/goal …" as text. No `update_goal` call appears, so the SDK raises. Without the guard, an ordinary thread is reported as a goal | `grok.command_not_run`. Its `thread_id` is the new thread; that run's cost is spent | INV-8, A-7 |
| EC-42 | `run_grok_goal("status")`, or `" Clear "`, `"pause"`, `"resume"` | Refused before any paid run. Without the guard, `/goal clear` would clear the session's goal and then raise `command_not_run` after a paid run | invalid_argument naming `objective` | INV-9, D-30 |
| EC-43 | `run_grok_implement` with the default `GrokPermissionMode.DEFAULT` | Grok refuses edits headless (#1036 A-3). The persona read still happens, so the call returns, and its text reports the refused edits | a result that says nothing was changed. The docstrings and README say to pass `permission_mode=ACCEPT_EDITS` | NG-9, A-20 |
| EC-44 | `run_grok_review(local=True, branch="x")`, or `branch` and `pr` together | Refused | invalid_argument naming `branch` (or `pr`) | INV-3 |
| EC-45 | `run_grok_implement(effort=6)`; `run_grok_execute_plan(effort=3)` or `concurrency=9`; `budget_tokens=0` | Refused against the per-command bounds | invalid_argument naming the field | INV-3 |
| EC-46 | `run_grok_execute_plan(design_doc="docs/plan.md")` (relative), or an absolute path that does not exist | Refused | invalid_argument naming `design_doc` | INV-3 |
| EC-47 | `run_grok_execute_plan(..., auto_pr=True)` or `run_grok_review(pr=12)` | Grok pushes branches and opens draft PRs, or posts a pending GitHub review. This happens only on the caller's explicit opt-in (the defaults are off) | external effects on GitHub | T-7 |
| EC-48 | a Grok stream that exits 0 without an `end` event | Raises | `grok.protocol_mismatch` naming `end` | INV-6 |
| EC-49 | a Grok stream whose `error` event message contains a `GROK_NOT_SIGNED_IN_MARKERS` text | Mapped | `grok.key_rejected` | INV-5 |
| EC-50 | a Grok command run that passes `config.timeout_seconds`, or whose stream passes the output cap (the runner keeps the first bytes, so `end` is lost) | The tree is stopped, or the cap is reported. The id is still known, because the SDK minted it (`--session-id`) | `grok.timed_out` / `grok.output_too_large` with `error.thread_id` = the minted id, so the caller can read, continue or delete the paid thread | INV-16, INV-29 |
| EC-51 | `run_grok_plan` where the new thread's `summary.json` lacks `agent_name`, or no `summary.json` exists for the minted id | Fails closed | `grok.command_not_run` | INV-8, A-10 |
| EC-52 | `run_opencode_command("no-such")` | opencode emits an error event `Command not found: "no-such". Available commands: …` and exits 1. The prefix `OPENCODE_COMMAND_NOT_FOUND_TEXT` is matched in the event's message or stderr | `opencode.command_not_run` | D-8, A-15 |
| EC-53 | `run_opencode_command("-x")`, `"a b"` or `""` | Refused | invalid_argument naming `command` | INV-9 |
| EC-54 | `run_opencode_plan(task, config=OpencodeThreadConfig(agent="build"))` | Refused, because the config contradicts the function | invalid_argument naming `config` | INV-3 |
| EC-55 | `run_muse_plan`, where the model never calls `read_skill` for `bundled:plan` | Raises after reading the thread's items | `muse.command_not_run` with the thread id | INV-8 |
| EC-56 | the Muse evidence read returns history mode `none` (`historyBudget`, `projectionUnavailable`, …) | Fails closed; the detail names the `noneReason` | `muse.command_not_run` | INV-8, A-16 |
| EC-57 | `run_muse_skill("bundled plan", …)` or `run_muse_skill("", …)` | Refused | invalid_argument naming `skill` | INV-9 |
| EC-58 | `init_muse_workspace(ws)` where Muse config already exists | Muse refuses (`--force` is not exposed) | `muse.run_failed` with Muse's text | §9.2, INV-5 |
| EC-59 | `init_muse_workspace(ws, dry_run=True)` | Muse prints its plan and writes nothing | `NativeCommandOutput` holding the plan | AC-18 |
| EC-60 | the caller's own `XAI_API_KEY` or `META_API_KEY` in the parent environment | Removed from helper children | not used | INV-2 |
| EC-61 | a skill function's evidence read fails after the run succeeded (serve timeout, `-32020`) | Raises with the new thread id attached | `muse.timed_out` / `muse.thread_not_found` with `error.thread_id` set to the new thread | INV-5, INV-8 |
| EC-62 | a list or search while a Grok run rewrites a `summary.json` in place (if Grok does not write it atomically) | The JSON may be partial, which raises; a retry succeeds. Operations on one id are affected only by their own thread's file (EC-68) | intermittent `grok.protocol_mismatch` naming the file | A-3 (accepted limitation), D-27 |
| EC-63 | SDK-scope Grok threads were run in a private home that still loads `~/.claude` hooks, skills and MCP servers (#1036 EC-44 is false; verified with `grok inspect`) | No fix here. The README states it | documented limitation | NG-9 |
| EC-64 | 10,000 Grok threads in scope | Each `summary.json` is read once, and memory grows with the thread count. Only the top `limit` are returned | a slower but correct list | NFR-12 |
| EC-65 | a Muse session whose `forkedFrom` names a session that `session/read` cannot find | The chain stops (as in EC-25) | shorter chain | INV-10 |
| EC-66 | a Grok store holding files beside the session folders: `sessions/session_search.sqlite` (Grok's search index), `<group>/permission.toml`, `<group>/permission_<client>.toml`, `<group>/.cwd` | Only directories are groups, and only directories inside a group are session candidates. Files at both levels are ignored (`.cwd` is still read for the USER match). Without this, `session_search.sqlite` is treated as a group and raises `NotADirectoryError`, so every SDK-scope list on a real store would raise `grok.store_unreadable` | normal results | INV-6, D-27 |
| EC-67 | a scope whose session folders all lack `summary.json`, the newest folder last modified more than `GROK_SUMMARY_GRACE_SECONDS` ago (Grok renamed or moved the file) | Raises instead of returning `()`. A store whose newest such folder is younger than the grace period is a run that is still starting, and EC-11 applies | `grok.protocol_mismatch` naming the expected layout `sessions/<group>/<id>/summary.json` and the home | INV-6, D-31, A-1 |
| EC-68 | `get_grok_thread(A)`, `read`, `delete`, `lineage`, or the evidence step of `run_grok_plan` / `run_grok_explore`, while a sibling thread B's `summary.json` is corrupt, oversize or half-written | Only A's file (and A's parents' files, for lineage) is read | the normal result for A | INV-6, D-27 |
| EC-69 | `run_grok_execute_plan(design_doc=r"C:\Users\Jane Doe\plan.md")`, or a design doc named `x --auto-pr.md` | Refused. Without the guard, the skill splits the path at the space and fails after a paid run, or reads `--auto-pr` as a flag and pushes branches without the opt-in that T-7 promises | invalid_argument naming `design_doc` | INV-9, D-30 |
| EC-70 | `run_grok_goal("ship it --budget 99999999")`, `run_grok_implement("fix --effort=5")` | Refused, because a token equals one of that command's own option flags in `GROK_TEXT_OPTION_FLAGS` (or starts with `<flag>=`). `run_grok_implement("Add a --dry-run flag")` passes, because implement reads only `--effort` (R-19). Without the guard, caller text sets a budget above `GROK_GOAL_MAX_BUDGET_TOKENS` or an unvalidated effort. `run_grok_command(GrokCommand.GOAL, "x --budget 5")` passes, because its raw arguments are the caller's own | invalid_argument naming `objective` / `task` | INV-9, D-30 |
| EC-71 | `run_grok_goal("clear the stale cache entries")` | Not refused: only the whole stripped value is compared with the reserved words. If Grok treats a leading reserved word as the subcommand, no `update_goal` appears | the goal result, or `grok.command_not_run` (fails closed) | INV-8, A-7 |
| EC-72 | `list_recent_grok_threads(ws)` after `run_grok_execute_plan` started implementer and reviewer subagents (Grok keeps child sessions in the normal sessions tree), or Muse items with `childSessionId` | Grok and Muse list subagent child threads as ordinary threads. Their `parent_thread_id` is set only if the vendor records a parent, so a child's lineage may stop at itself. opencode lists root sessions only, so its subagent children never appear in lists; get, read and lineage still reach them by id (EC-77) | the caller's own threads can fall below `limit`; the README says so | Q-7 (filtering is optional, default no) |
| EC-73 | `run_grok_code_review` where the `grok export` of the new thread fails (timeout, not found, cap) after the paid run | Raises with the minted id | `grok.timed_out` / `grok.thread_not_found` / `grok.output_too_large` with `error.thread_id` set | INV-8, INV-29, D-28 |
| EC-74 | `run_grok_imagine_video` where video tools are off (`features.video_gen = false`, or no video endpoint for a custom model) | The model cannot call `image_to_video`, so no evidence appears | `grok.command_not_run`; the next step names `features.video_gen` | INV-8, A-24 |
| EC-75 | an opencode project with `NATIVE_OPENCODE_SCAN_MAX` or more root sessions | `session list --max-count=NATIVE_OPENCODE_SCAN_MAX` returns exactly the cap, so the list may be cut. The SDK raises instead of returning a short list. Without the flag, opencode stops at 100 rows across the project, which silently drops older in-window threads | `opencode.protocol_mismatch` whose detail names the cap (`OPENCODE_SCAN_CAP_DETAIL`) | D-19, A-12 |
| EC-76 | `get_opencode_thread_lineage` of a thread made by `fork_opencode_thread` | opencode's `Session.fork` records no parent, so the chain is the thread alone | a 1-element chain; the README says opencode lineage shows subagent nesting only | D-26, A-22 (documented limitation) |
| EC-77 | `get_opencode_thread(<subagent child id>)`, a session that `session list` never shows (roots only) | Found through the `opencode db` query by id, with its `parent_id` | the child's summary | D-26 |
| EC-78 | a same-named skill or command shadows a bundled Grok skill: `.claude/commands/review.md` or `.grok/skills/design/` in the workspace, `~/.claude/skills/implement`, or a `skills=` folder named `review` (`08-skills.md:213`: "A same-named local, repo, or user skill overrides the bundled copy") | A `skills=` folder named like the command is refused before any run (D-32). A workspace or user-level shadow cannot be refused: the run reads no persona, and the call fails closed | `configuration.invalid_argument` naming `skills`; otherwise `grok.command_not_run`, whose cause names shadowing and whose next step says to run `grok inspect --json` and look for `collidesWith` | INV-8, D-32, Q-8 |
| EC-79 | a Muse skill run that compacted, so the evidence `session/read` answers in mode `anchoredSnapshot` (its items start at a compaction boundary, after the early `read_skill` call) | The evidence is read from the `muse export` transcript instead (D-33) | the run's result, or `muse.command_not_run` whose cause names compaction | INV-8, D-33, A-28 |
| EC-80 | on win32, `run_grok_goal(json.dumps(spec))` with about 20,000 characters, 40 % of them `"` | `require_command_line_units` on the text under its public name, with the budget `NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS - NATIVE_COMMAND_RESERVED_CHARS` (D-25). Without it, `NativeThreadRequest` would refuse the built prompt under the name `prompt` | invalid_argument naming `objective` | INV-3, D-25 |
| EC-81 | a Grok command run that fails before the session exists (`key_rejected`, or "Couldn't start session") | Raises with the requested id and the detail "the thread may not exist" | `grok.key_rejected` / `grok.run_failed`; a `delete_grok_thread(error.thread_id, ws)` may raise `thread_not_found` | INV-29 |

**Rollback of the user action:**

- **Read helpers:** they change nothing, so there is nothing to undo.
- **`delete_*`:** irreversible. The vendor removes the thread, and the SDK keeps no copy; call `read_*` first to keep a transcript.
- **Skill functions:** they create a thread. Remove it with `delete_grok_thread` / `delete_opencode_thread`; Muse has no delete. Undo any workspace edits with git. For `auto_pr=True`, close the draft PRs and delete the pushed branches on GitHub.
- **`init_muse_workspace`:** remove the files Muse created; its returned output lists them.

## §7 Requirements

**Functional**
| ID | Requirement | Priority | Source (request.md / G-) |
|---|---|---|---|
| FR-1 | Grok thread helpers with the §8.5 signatures: `list_grok_threads`, `list_recent_grok_threads`, `list_grok_threads_since`, `get_grok_thread`, `read_grok_thread`, `get_grok_thread_lineage`, `search_grok_threads`, `delete_grok_thread` | P0 | §E.1 A, §E.2 §1, KD-1, G-1 |
| FR-2 | opencode thread helpers: `list_opencode_threads`, `list_recent_opencode_threads`, `list_opencode_threads_since`, `get_opencode_thread`, `read_opencode_thread`, `get_opencode_thread_lineage`, `search_opencode_threads`, `delete_opencode_thread` | P0 | §E.2 §1, G-1 |
| FR-3 | Muse thread helpers: `list_muse_threads`, `list_recent_muse_threads`, `list_muse_threads_since`, `get_muse_thread`, `read_muse_thread`, `get_muse_thread_lineage` | P0 | §E.2 §1, G-1 |
| FR-4 | Every list, get, lineage and search helper returns `NativeThreadSummary(harness, thread_id, title, created_at, updated_at, parent_thread_id, model)`, with UTC-aware datetimes and the per-harness mapping of §9.1 | P0 | KD-7, G-1 |
| FR-5 | List semantics: `since` window, `limit` (default `NATIVE_LIST_DEFAULT_LIMIT` = 20, recent default `NATIVE_RECENT_DEFAULT_LIMIT` = 10, maximum `NATIVE_LIST_MAX_LIMIT` = 200), and newest first; the recent and since wrappers equal the base call | P0 | Prompt 3 ("view recent sessions, view sessions in last N time period"), §E.1 A |
| FR-6 | `get_<h>_thread` returns one summary, or raises `thread_not_found` | P0 | §E.2 §1 |
| FR-7 | `read_<h>_thread` returns the whole transcript in `NativeThreadResult.text`: Grok Markdown from `grok export`, opencode JSON from `opencode export`, Muse JSON from `muse export` | P0 | §E.2 §1 |
| FR-8 | `get_<h>_thread_lineage` returns the root-first chain of INV-10 | P0 | §E.2 §1 |
| FR-9 | `search_grok_threads` matches the query case-insensitively against the title, summary and last-turn summary; `search_opencode_threads` against the title. Both are ordered and limited like lists | P0 | §E.2 §1 |
| FR-10 | `delete_grok_thread` and `delete_opencode_thread` delete one thread (INV-11) | P0 | §E.2 §1 |
| FR-11 | Every Grok helper takes `scope: GrokThreadScope = GrokThreadScope.SDK`, where SDK is the private home of `workspace` and USER is `~/.grok` | P0 | KD-8, §E.1 A |
| FR-12 | Grok command functions: `run_grok_command(command: GrokCommand, arguments="", …)` plus `run_grok_goal`, `run_grok_implement`, `run_grok_design`, `run_grok_execute_plan`, `run_grok_review`, `run_grok_code_review`, `run_grok_resume_claude`, `run_grok_resume_codex`, `run_grok_resume_cursor`, `run_grok_imagine`, `run_grok_imagine_video`, `run_grok_plan`, `run_grok_explore` | P0 | Prompt 4, Prompt 5, §E.2 §2 Grok (request.md:267, :269) |
| FR-13 | opencode command functions: `run_opencode_command(command, arguments="", …)` plus `run_opencode_review`, `run_opencode_init`, `run_opencode_plan` | P0 | §E.2 §2 opencode |
| FR-14 | Muse functions: `run_muse_skill(skill, prompt, …)` plus `run_muse_goal`, `run_muse_plan`, `run_muse_import`, `run_muse_scaffold`, `run_muse_browser_app`, and `init_muse_workspace(workspace, *, dry_run=False, config=None) -> NativeCommandOutput` | P0 | §E.2 §2 Muse |
| FR-15 | Every Grok and Muse command or skill function verifies its evidence (§9.2) and raises `<harness>.command_not_run` with the new thread id when the evidence is missing. Every opencode one maps opencode's unknown-command answer to `opencode.command_not_run` | P0 | KD-6, §E.2 "How I'd build it" |
| FR-16 | Every new function raises only `NativeThreadError` (or `CancelledError`), with its own `operation`, the closed code, and #1036's message order. A refused argument names the public parameter | P0 | KD-9 ("extensively handle errors for every single function") |
| FR-17 | New problems `command_not_run` and `store_unreadable`, and the codes of INV-22, each with a summary, an observation, and its own likely cause and next step. Today's `thread_not_found`, `timed_out` and `output_too_large` likely-cause and next-step texts (all three harnesses), and `opencode.protocol_mismatch`'s, are widened to cover the helpers, the fixed control timeout, whole transcripts, the Grok stream cap and the opencode scan cap (review R-18) | P0 | KD-9 ("error messages need to be in much more detail"), request.md §C open question 5 |
| FR-18 | Naming: helpers `<verb>_<harness>_thread(s)`, skill functions `run_<harness>_<skill>`, building blocks `run_<harness>_command` / `run_muse_skill`, exported exactly per INV-1 | P0 | KD-3 ("only thing I definately want is the actual function naming the way i said") |
| FR-19 | Skill functions take `api_key`, `workspace`, `model`, `skills` and `config` exactly as #1036's `run_<harness>_thread` does: keyword-only; `model` required for opencode and optional otherwise; `config` the harness's config record | P0 | KD-4, KD-10 |
| FR-20 | Docs: `vidbyte/harnesses/README.md` (native bullet) and `REPO_MAP.md` (`vidbyte/harnesses/native/` entry) name the new functions, the Grok scopes, the evidence rule and the excluded rows, and replace the false EC-44 sentence with the verified limitation. They also state that opencode forks record no parent (EC-76), that skill shadowing makes Grok commands fail closed (EC-78), and that subagent children list as ordinary threads (EC-72) | P1 | AGENTS.md "Repository Map"; request.md §C (EC-44 side finding) |

**Non-functional**
| ID | Requirement | Priority | Target |
|---|---|---|---|
| NFR-1 | The API key never goes on argv, in a file, or into an error | P0 | 0 occurrences across all argv, files written and error attributes in the credentials tests (AC-24) |
| NFR-2 | Helpers need no key and make no model call | P0 | No `api_key` parameter on any helper; the key variables are removed in every helper child (AC-10) |
| NFR-3 | Every call is bounded | P0 | Helper child ≤ `NATIVE_CONTROL_TIMEOUT_SECONDS` (30 s) and ≤ `NATIVE_PROCESS_MAX_OUTPUT_BYTES` (64 MiB); `summary.json` ≤ `GROK_SUMMARY_MAX_BYTES` (1 MiB); lineage ≤ `NATIVE_LINEAGE_MAX_DEPTH` (64) steps; list ≤ 200 items |
| NFR-4 | No blocking I/O on the event loop | P0 | lint S052 stays at baseline 0; every file operation runs in `asyncio.to_thread` (INV-18) |
| NFR-5 | Lint is clean with no baseline change | P0 | `python lint/run.py` ends `AGENT-LINT: PASS`; `git diff lint/baseline.json` is empty; no suppression is added |
| NFR-6 | File sizes | P0 | Every new module ≤ 600 lines; every touched file < 1,000 lines (`vidbyte/lib/constants/native_threads.py` ≤ 900) |
| NFR-7 | Detailed errors | P0 | Every message has the six #1036 INV-5 parts. Each new code's likely cause and next step are non-empty, end with a period, and are unique within the harness's codes (AC-20) |
| NFR-8 | Tests run offline | P0 | No network, real key, real vendor CLI or WSL distro in `tests/features/harness_threads` |
| NFR-9 | "Simply": thin wrappers | P0 | Each named skill function and each `list_recent_*` / `*_since` body is a docstring plus one `return await <Class>._call(...)` statement (≤ 5 lines), per Prompt 4 "simply runs" and KD-10 |
| NFR-10 | The full gate is green | P0 | Both `run_ci.py` stages pass; the semgrep `typed-mapping-boundary-policy` scan reports 0 findings |
| NFR-11 | No import-time side effects | P0 | Importing `vidbyte.harnesses.native` starts no process and touches no file |
| NFR-12 | Scale | P1 | A Grok list reads each `summary.json` at most once per call; a Grok operation on one id reads only that id's files (D-27). opencode get starts one `opencode db` child and lineage one per step, with no transcript moved (D-26). Muse lineage starts one serve per step |

---

## Part C — Design

## §8 Architecture and decisions

The design adds three things to each harness subpackage, all inside #1036's existing structure:

- **A helpers module:** a static class of public functions plus a flow class.
- **A commands module:** the same shape.
- **New readers** in the harness's existing wire module.

Two small shared classes go in `hostkit`: listing (window, order, limit, match, lineage step) and evidence. The lib layer gains the vocabulary: records, enums, constants, codes and one timestamp converter. #1036's flows are reused directly: `OpencodeThreadRun.execute` for opencode commands, and `MuseThreadRun.execute` for Muse skills. They are shared, not copied: the Grok home code moves to `GrokHome`, and the Muse child code moves to `MuseChildren`.

### 8.1 Decisions
| ID | Decision | Deciding reason | Runner-up | Flips if |
|---|---|---|---|---|
| D-1 | Helpers validate their arguments in a new lib record `NativeHelperRequest(harness, operation, workspace, thread_id, since, limit, query, scope, dry_run)`. Closed per-operation tables in constants decide which fields each operation requires. `NativeErrorFactory`, `NativeLauncher.resolve` and `MuseLauncher.resolve`/`launch_failure` widen their `request` type to `NativeThreadRequest \| NativeHelperRequest`; they read only `.workspace` and `.thread_id` | `NativeThreadRequest` requires a prompt and a key, and helpers have neither (INV-2). One record keeps every refusal inside the one guarded try with the public field name (INV-3) | Make `prompt`/`api_key` optional on `NativeThreadRequest` | A future operation needs fields beyond these 8, which would split the record per shape |
| D-2 | Grok list, get, lineage and search read `<home>/sessions/<group>/<id>/summary.json` directly. **This reverses #1036 D-17** ("Grok's storage layout is a vendor detail the SDK should not read") for these helpers only | `grok sessions list/search` print text only, with no JSON and no `--cwd` (code-map §4.5). The owner accepted the `summary.json` catalog (§E.1 A, Prompt 4). The layout is documented in Grok's user guide. A mismatch fails loudly (INV-6) | Parse `grok sessions list` text | Grok ships a JSON listing (`--json` on `sessions list`) that also names created, updated, parent and model |
| D-3 | `search_grok_threads` is a local, case-insensitive substring match over `generated_title`, `session_summary` and `last_turn_summary` | `grok sessions search` prints text only, mixes in results from xAI's servers, and takes the query as an unchecked positional operand (`vidbyte/lib/process/argv.py:9`), against INV-9 | `grok sessions search <query>` | Grok adds a local-only, JSON search |
| D-4 | Grok and Muse evidence comes from the run's **own** record. For Grok, the `tool_call` events of `--output-format=streaming-json` (documented fields `toolName`, `rawInput`), or the new thread's `summary.json` `agent_name` for `--agent`. For Muse, the `toolCall` items (`tool`, `args`) of MSP `session/read {excludeItems: false}`. Missing evidence fails closed (INV-8). Code-review, which leaves no tool trace, uses the run's own transcript instead (D-28) | KD-6: an unexpanded slash command looks like success. The streaming event and MSP item member names are documented (vendor docs; `msp.schema.json`), while `chat_history.jsonl` / `updates.jsonl` are not | Search the session's `chat_history.jsonl` for the literal command echo | The manual probe (PR test plan) shows `tool_call` events omit the skill's tool calls (for example, they come only from subagents). Then switch Grok evidence to the session folder files |
| D-5 | `run_grok_command` takes `command: GrokCommand` (a closed enum of the 11 wrapped slash commands), not a free string | Evidence is only known per command (D-4). A free name could only pass unverified, which KD-6 forbids | `command: str` plus a caller-supplied evidence rule | Q-6 is answered yes |
| D-6 | The §3 exclusions (NG-1 to NG-4, NG-6, NG-7, NG-13; NG-5 was withdrawn in r2) | Each fails either "one call returns a finished, verifiable result" or KD-5 | Ship them as always-`command_not_run` wrappers | A key-bearing probe shows evidence for a row: Q-1 |
| D-7 | `read_<h>_thread` returns #1036's `NativeThreadResult(harness, thread_id, text=<whole vendor document>, text_truncated=False)` | Reuses the record callers already handle (KD-10). A transcript is a document to parse, so a cut is worse than an error (INV-21) | A new transcript record with parsed messages | Callers need a parsed, cross-harness transcript, which would be a new record and its own PR |
| D-8 | opencode command functions reuse `OpencodeThreadRun.execute`. `NativeThreadRequest` gains `command: str \| None`, and when it is set, `--command=<name>` is added and an empty prompt sends no stdin. Verification is opencode's own dispatch: an error event or stderr text starting `Command not found: "<name>"` (A-15, verified in the 1.18.31 bundle) maps to `opencode.command_not_run` | `opencode run --command` is the documented headless command path (CMD ✅). Without a prefix there is no silent-text failure mode, so the vendor's refusal of an unknown name is the evidence that matters | Export the thread after the run and look for the command template in the first user message | opencode changes the unknown-command text (then `run_failed` is raised instead, which is loud). Then update `OPENCODE_COMMAND_NOT_FOUND_TEXT` |
| D-9 | Muse skill functions reuse `MuseThreadRun.execute` with the prompt `MUSE_SKILL_PROMPT_TEMPLATE` ("Use the `{skill}` skill.\n\n{prompt}") or `MUSE_GOAL_PROMPT_TEMPLATE`. They then read the thread's items through one short `muse serve` batch for `read_skill`/`create_goal` evidence | `muse exec` does not expand slash commands (verified). Skills load through `read_skill` per the bundled descriptions ("call read_skill for bundled:<id>") | `muse export` for evidence | A-16 or A-17 is false for the installed Muse |
| D-10 | Extract `GrokHome` (`grok/store.py`) and `MuseChildren` (`muse/children.py`) from #1036's flow classes, with unchanged behavior (INV-26) | AGENTS.md principle 5 (write shared logic once). Helpers, commands and runs all need the private home and environment, or the private config folder, the serve invocation and the reaping run | Call `GrokThreadRun._prepare_home` and others from the new classes | — (a refactor with no flip condition; review-scope: main's behavior stays byte-identical) |
| D-11 | Read paths never create a Grok home. A missing home or `sessions` folder means "no threads" | INV-4. Browsing must not leave `grok-homes/<key>` folders for every path a caller lists | Create it as runs do | — |
| D-12 | New problems: `COMMAND_NOT_RUN` (codes for all three harnesses) and `STORE_UNREADABLE` (Grok only, the only harness whose files the SDK reads itself). An unknown id reuses `THREAD_NOT_FOUND`; its observation and the three likely-cause and next-step texts are widened to cover helpers | Smallest set that gives every new failure its own accurate code (request.md §C open question 5). opencode and Muse store failures surface through their CLIs as `run_failed` | One `store_unreadable` per harness | opencode or Muse gain direct file reads |
| D-13 | Timestamps are UTC-aware `datetime`s. A new lib helper, `RecordFieldConverter.to_utc_datetime(value, field_name)`, accepts an aware `datetime` or an RFC 3339 string with an offset (`datetime.fromisoformat`), refuses naive values, and returns `value.astimezone(UTC)` | AGENTS.md principle 5: three harnesses parse timestamps, and `vidbyte/lib` has no such helper (briefing §4). Aware UTC values make the sort and the window correct across offsets (EC-15) | Keep strings and sort them | — |
| D-14 | Helper children use `NATIVE_CONTROL_TIMEOUT_SECONDS`. A helper's `config` only locates the program (`grok_command`, `opencode_command`, `muse_command`/`wsl_distro`/`muse_path`); its `timeout_seconds` and run options are ignored, as the docstrings say | Listing, exporting and deleting are control operations, like #1036's `session/read` pre-check | Honor `config.timeout_seconds` | A real store makes export exceed 30 s. Then add a `NATIVE_EXPORT_TIMEOUT_SECONDS` |
| D-15 | Helpers take `workspace` positionally, and `(thread_id, workspace)` for single-thread helpers, as sketched in §E.1/§E.2. Skill functions take `api_key` and `workspace` keyword-only, like #1036 | Matches the accepted sketches (`list_grok_threads(workspace, *, since=None, limit=20, scope=SDK)`, `get_grok_thread(thread_id, workspace)`) and #1036 (`run_grok_thread(prompt, *, api_key, workspace, …)`) | All keyword-only | — |
| D-16 | `delete_grok_thread` finds the thread in the scope's store first, runs `grok sessions delete <id>` with `GROK_HOME=<scope home>`, then checks that the session folder is gone. `read_grok_thread` also finds the thread first, then runs `grok export <id>` | `grok sessions delete` is "help text only" (§E.1). The post-check turns a confirmation prompt or a leader of another home into a loud failure (EC-23) | Trust the exit code | A-6 is verified (then the post-check stays as a cheap guard) |
| D-17 | `read_muse_thread` first checks the id with `session/read`, then runs `muse export --session <id> --out <temp>/export/thread.json` with cwd `<temp>/export` (an empty SDK temp folder, `/mnt/...` in WSL), reads the file with a byte cap, and removes the folder | `muse export` writes into cwd without `--out`, and `--session` prefers an existing path over an id. #1036 forbids writing into the workspace (AC-19/INV-12). `-32020` is the known not-found signal | Run export with cwd set to the workspace | — |
| D-18 | Helper children carry no key (INV-2) | Least privilege: listing and exporting need no key | Inherit the caller's environment | — |
| D-19 | `list_opencode_threads` runs `opencode session list --format=json --max-count=NATIVE_OPENCODE_SCAN_MAX` (10,000), then keeps rows whose `directory` normcase-equals the resolved workspace, then applies the window, order and limit. A list of exactly the cap raises `opencode.protocol_mismatch` naming the cap (EC-75) | Verified in the 1.18.31 bundle (review R-16): without `-n` the list stops at 100 rows (`limit??100`) across the whole project, roots only, so older in-window threads vanish silently. `session list` has no `--dir`, and a project spans subdirectories. 10,000 rows is about 3 MB, far below `NATIVE_PROCESS_MAX_OUTPUT_BYTES` | No `--max-count` (r1/r2, silently capped at 100) | A project reaches the cap in practice. Then page by `--max-count` growth or move lists to `opencode db` with a bound directory parameter |
| D-20 | `NativeThreadError.expected` becomes `f"{operation.value} finishing with its documented result"` | Helpers return summaries, tuples, `None` or `NativeCommandOutput`, not only `NativeThreadResult` (`vidbyte/lib/errors/base.py:599`). No test pins the text | One text per operation | — |
| D-21 | `GrokThreadScope.USER` reads literally `Path.home() / ".grok"` and ignores an inherited `GROK_HOME` | KD-8 and §E.1 say "your own `~/.grok`" | Honor `GROK_HOME` | Q-4 is answered yes |
| D-22 | opencode helper children run with cwd = workspace and `PWD` = workspace (overlay) | #1036 INV-18 made the project explicit with `--dir`, and `session list`/`export`/`session delete` take no `--dir`. Overlaying `PWD` keeps an inherited `PWD` from choosing the project (EC-31) | cwd only | — |
| D-23 | Lineage is built root first by walking parents from the requested thread. A missing parent ends the walk (EC-25) | "Which thread forked from which" reads naturally oldest first. A deleted ancestor must not hide the rest | Raise on a missing parent | — |
| D-24 | opencode summaries have `model=None` | Neither `session list` rows nor the `OPENCODE_SESSION_QUERY` columns carry a model (the 1.18.31 session record may hold one, in a shape this spec does not verify); per-message models differ | The last assistant message's model | opencode adds a session model |
| D-25 | Each skill function validates its own text argument under its public name (the `NATIVE_TEXT_ARGUMENTS` table) with cap `NATIVE_COMMAND_TEXT_MAX_CHARS` = `NATIVE_ARGV_PROMPT_MAX_CHARS - NATIVE_COMMAND_RESERVED_CHARS`, before the final prompt is built. On win32, for Grok and Muse, it also runs `RecordFieldValidator.require_command_line_units(text, <public name>, max_units=NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS - NATIVE_COMMAND_RESERVED_CHARS)` (review R-24; `validation.py:64`) | INV-3 says the refusal names the parameter (`objective`, not `prompt`), and the reserve keeps the built prompt within `NativeThreadRequest`'s cap | Let `NativeThreadRequest` refuse `prompt` | — |
| D-26 | *(r3; reverses r2.)* `get_opencode_thread` and `get_opencode_thread_lineage` use the request's own mechanism (request.md:236): one `opencode db --format=json "<OPENCODE_SESSION_QUERY>"` child per id, where the query is the constant `SELECT id, title, time_created, time_updated, parent_id, directory FROM session WHERE id = '{thread_id}'`. get runs it once. lineage runs it once per step and follows `parent_id` with `check_step`. `[]` → `opencode.thread_not_found`; more than one row → `protocol_mismatch`. The lookup is database-wide, with no project or `directory` filter, because the id is exact. Only `read_opencode_thread` runs `opencode export` | Review R-15 and R-10, verified in the 1.18.31 bundle. `session list` returns roots only (`roots:!0`), and its rows are exactly `{id, title, updated, created, projectId, directory}` with no `parentID`, so r2's in-memory walk always gave a 1-element chain and never found a child. `db [query] --format json` runs in-process (`instance:!1`, `C.all(k1.raw(u))`, no sqlite3 binary). The `session` table has `parent_id` and the `time_*` columns. Unlike `export`, it moves no transcript, which was R-10's concern. It is injection-safe because the only variable is a pattern-checked id (INV-9, T-9) | `opencode export <id>` `info` block per step (r1; moves whole transcripts) | opencode removes or renames `db`, the `session` table, or its `parent_id` / `time_*` columns (probe f; a mismatch is loud: `run_failed` or `protocol_mismatch`). Then fall back to `export` `info` |
| D-27 | Grok operations on one id (get, read, delete, lineage, and the plan and explore evidence) read only `sessions/<group>/<id>/summary.json` for the groups in scope (`GrokStore.thread`), and lineage reads each parent's file the same way. Whole-scope strict scans (`GrokStore.threads`) serve only list, recent, since and search. In both, only directories are groups and only directories inside a group are session candidates; files at both levels are ignored (EC-66) | Review R-7 and R-2. A corrupt, oversize or half-written sibling must not fail a paid run's evidence check or a delete of another thread. Grok keeps `sessions/session_search.sqlite` and `<group>/permission*.toml` in the store (`17-sessions.md:416`, `22-permissions-and-safety.md:426`; this machine's `~/.grok/sessions/` holds only `session_search.sqlite`) | One whole-store scan for every operation (r1) | — |
| D-28 | `run_grok_code_review` takes no text. Its evidence is its own `grok export <minted id>` transcript (the read-helper child: keyless, the run's private home, control timeout, cap) containing `GROK_CODE_REVIEW_FRAGMENT` = `"deep code quality audit of the current branch's changes"`, a sentence of the skill's Core Prompt (`code-review/SKILL.md`). The run's Markdown export is the record. The model can produce that sentence only if the skill text reached it, and the caller cannot supply it because the function takes no text | The skill is a pure prompt rubric (`disable-model-invocation: true`; no persona file and no distinctive tool), so the stream holds no tool trace that INV-8 could check. The owner's own rule names `export` as a valid proof ("goal state in `summary.json` or `export`", request.md "How I'd build it"). It fails closed if the expansion is not in the transcript (A-27) | Defer code-review to a Q (review R-4's smallest fix); or read `chat_history.jsonl` (undocumented members, D-4) | The probe shows the export omits the expanded skill text. Then the function always raises `command_not_run`, the PR body says so, and Q-2 reopens |
| D-29 | `GrokCommandRun` mints `str(uuid.uuid4())` and passes `--session-id=<id>` (`GrokFlag.SESSION_ID`, JOINED) on every Grok command run. That id is the thread id in every post-launch error and in the result. `end.sessionId` must equal it | Grok headless documents `-s, --session-id <ID>`: "Create a **new** session with this **UUID**" (`14-headless-mode.md:25`, `:354`). Without it, a run that times out (1800 s default) or overflows the cap loses `end`, and the caller paid for a thread it cannot name (review R-6). The flag is internal; no public parameter is added, and #1036's `run_grok_thread` is unchanged (INV-26) | Report `thread_id=None` (r1 EC-50) | A-25 is false (`--session-id` conflicts with `--single`). Then drop the flag and restore r1's EC-50 |
| D-30 | The named Grok wrappers refuse text that the skill would read as an option: a token equal to one of that command's own option flags (`GROK_TEXT_OPTION_FLAGS`: GOAL → `--budget`, IMPLEMENT → `--effort`, every other command → none; review R-19), or `<flag>=`, a `design_doc` with whitespace, and a reserved `/goal` word as the whole `objective`. The check lives in `GrokCommandArguments` (`named=True`), and the refusal names the public parameter (`text_field`). `run_grok_command` passes its raw `arguments` unchecked | Review R-5. INV-9 protected argv but not the slash-command line that Grok tokenizes. The execute-plan argument hint splits on whitespace (`--instructions \"...\"`), and `/goal` reserves `status\|pause\|resume\|clear` (`04-slash-commands.md:328`). Without the refusals, caller text could set `--auto-pr` without T-7's opt-in, set a budget above the cap, or clear a goal after a paid run | Quote the text inside the line (Grok's quoting rules are undocumented) | Grok documents a quoting or `--` rule for slash arguments. Then quote instead of refusing |
| D-31 | A Grok scope whose session folders all lack `summary.json`, with the newest folder older than `GROK_SUMMARY_GRACE_SECONDS` (60), is a layout mismatch, not an empty store (EC-67) | Review R-9. EC-11's skip would otherwise turn a renamed or nested `summary.json` into a silent `()` that synthetic fixtures never catch. The grace period keeps a run that is still starting (one fresh folder, no summary yet) from raising | Raise whenever no folder has a summary (review R-9's form, which fails a list during a fresh home's first run) | Grok documents when `summary.json` is first written. Then size the grace period from it |
| D-32 | `run_grok_command` and the named Grok wrappers refuse a `skills=` entry whose folder name equals the command's skill name (`command.value`), naming `skills`. Workspace and user-level shadows cannot be refused; they make the call fail closed, and the `grok.command_not_run` cause names shadowing and points to `grok inspect --json` (`collidesWith`) | Review R-20. `08-skills.md:213`: "A same-named local, repo, or user skill overrides the bundled copy". #1036 copies `skills=` folders into the private home's user tier. Every Grok evidence marker is bundled-only, so a shadow turns a paid run into a `command_not_run` whose r2 cause blamed slash expansion. The refusal closes the SDK's own path and adds no parameter | A `grok inspect --json` pre-flight before each run (Q-8, scope-adding, default no) | Q-8 is answered yes |
| D-33 | Muse evidence in history mode `anchoredSnapshot` comes from the run's own `muse export` transcript (D-17's keyless child). The transcript must contain the evidence tool name and, for `read_skill`, the skill id (`NativeCommandEvidence.require_text`, twice). Modes `inline` and `snapshot` read the items as before, and mode `none` still fails closed | Review R-25. MSP `SnapshotAnchor` is "the compaction boundary an anchored snapshot is anchored at", so the early `read_skill` call is gone from the items exactly on the longest, most expensive runs | An EC plus a cause naming compaction only (the call would still fail closed on long runs) | A-28 is false (the export omits pre-compaction tool calls). Then the call fails closed, and the cause already names compaction |

### 8.2 Patterns inherited
- **Static class bound to module names**: the public functions are `@staticmethod`s on one class per module, bound in the subpackage `__init__` with `name = Class.attr`. It keeps INV-15's "no top-level functions" policy and groups the functions. Used by `vidbyte/harnesses/native/grok/__init__.py` (`run_grok_thread = GrokThreads.run_grok_thread`); field guide `class-bound-helpers.md`.
- **One guarded `_call` per public class**: the order is `CancelledError` re-raised, `NativeThreadError` re-raised, `ConfigurationError` mapped to `from_configuration_error`, and `Exception` mapped to `from_unexpected`. This gives one error contract for every function (INV-5). Source: `grok/threads.py:GrokThreads._call`.
- **Narrated flow class with a main `execute`**: AGENTS.md principle 2. Source: `grok/threads.py:GrokThreadRun.execute`.
- **CLI-backed integration through canonical process helpers**: fixed subcommand words, argv only via `CliArgv.build`, runs only via `CliRunner().run(CliInvocation(...))`, and the runner owns the deadline and the output cap. Field guide `cli-backed-source-integrations.md`; `vidbyte/lib/process/{argv,runner}.py`.
- **Closed failure table**: code = `NATIVE_THREAD_FAILURE_CODES[(harness, problem)]`, with texts per code. Source: `vidbyte/lib/constants/native_threads.py`, `hostkit/errors.py:NativeErrorFactory.failure`.
- **Validated frozen slotted records with coercion before construction**: field guide `strict-config-dataclasses.md`; `vidbyte/lib/dataclasses/native_threads.py:NativeThreadRequest`.
- **Capped file read sized with `os.fstat`**: the A007-safe form. Field guide `blocking-lint-invariants.md`; `vidbyte/agents/coding_context/agents_md.py`.
- **Fail-closed verification (allow-list evidence)**: a command counts as run only on positive evidence, never on the absence of an error. This is the same stance as #1036's wrong-thread checks (`NativeErrorFactory.wrong_thread`).
- **Short-lived batch MSP exchange**: initialize, initialized, one request, EOF. Source: `muse/wire.py:MuseWire.batch_frames`.

### 8.3 Smaller design rejected

- **Prefix-only wrappers.** Each named function would call #1036's run with the command in the prompt: `run_grok_goal(o)` = `run_grok_thread("/goal " + o)`, and `run_muse_plan(t)` = `run_muse_thread("Use the bundled:plan skill. " + t)`. That is 25 one-line wrappers and no new readers. It fails **INV-8 / FR-15**: on Muse it is verified to run an ordinary thread and report success (KD-6), and on Grok it is unverified. The request names exactly this as a rejected alternative ("Bare slash-command prefixing without verification").
- **Helpers on `NativeThreadRequest`, with a dummy prompt and key.** It fails **INV-2 / NFR-2**: helpers would carry an `api_key` or invent one. It also fails **INV-3**: refusals would name `prompt`.
- **Grok helpers that parse `grok sessions list` text.** It fails **FR-4**: the text has no created time, parent or model. It also fails **INV-6**: human-oriented text has no member names to check.

### 8.4 Complexity budget
| Item | Count | Justification for each |
|---|---|---|
| New files | 10 (source). Test files are S2's, outside this budget | `grok/store.py` (GrokHome and GrokStore are shared by threads, helpers and commands, D-10); `grok/helpers.py`; `grok/commands.py`; `opencode/helpers.py`; `opencode/commands.py`; `muse/children.py` (shared by threads, helpers and commands, D-10); `muse/helpers.py`; `muse/commands.py`; `hostkit/listing.py` (window, order, limit, match and lineage step, shared by 3 harnesses); `hostkit/evidence.py` (evidence check shared by Grok and Muse). Helpers and commands are split per harness so that each module stays ≤ 600 lines (NFR-6) and each has one job |
| New classes/modules | 20 harness-layer classes; 6 lib records; 6 lib enums; 1 lib converter method | Classes: `GrokHome`, `GrokStore`, `GrokThreadHelpers`, `GrokHelperRun`, `GrokCommands`, `GrokCommandRun`, `GrokStreamWire`, `GrokHelperWire`, `OpencodeThreadHelpers`, `OpencodeHelperRun`, `OpencodeHelperWire`, `OpencodeCommands`, `MuseChildren`, `MuseThreadHelpers`, `MuseHelperRun`, `MuseSessionWire`, `MuseCommands`, `MuseCommandRun`, `NativeThreadListing`, `NativeCommandEvidence`. Records (§9.1): `NativeThreadSummary`, `NativeHelperRequest`, `NativeCommandOutput`, `NativeToolCall`, `GrokCommandArguments`, `GrokThreadFile`. Enums (§9.1): `GrokThreadScope`, `GrokCommand`, `GrokAgent`, `GrokCommandFlag`, `GrokEventType`, `MuseSkill`. Each closed set is an enum per AGENTS.md "Enums go in `vidbyte/lib/enums/`" |
| New dependencies | 0 | stdlib only (`urllib.parse`, `datetime`, `json`, `os`, `tempfile`, `uuid`) |
| New config keys | 0 | No config record gains a field. `GrokThreadScope` is a parameter, and `NativeThreadRequest.command` is an internal record field |
| New collections/tables | 0 | Nothing persists |
| New public endpoints/commands | 47 functions plus 4 exported types | §8.5; 68 exported names in total (INV-1) |

_The implementer may not exceed this budget without stopping and reporting BLOCKED._

### 8.5 Key interfaces

Public functions (exported from `vidbyte.harnesses.native`). `Path` is `pathlib.Path`, `timedelta` is `datetime.timedelta`, and the constants come from `vidbyte.lib.constants.native_threads`. The defaults below are named constants (lint A007).

```python
# ---- Grok thread helpers (no key, no model; scope chooses the store)
async def list_grok_threads(workspace: str | Path, *, since: timedelta | None = None, limit: int = NATIVE_LIST_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]
async def list_recent_grok_threads(workspace: str | Path, *, limit: int = NATIVE_RECENT_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]
async def list_grok_threads_since(workspace: str | Path, since: timedelta, *, limit: int = NATIVE_LIST_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]
async def get_grok_thread(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK) -> NativeThreadSummary
async def read_grok_thread(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK, config: GrokThreadConfig | None = None) -> NativeThreadResult
async def get_grok_thread_lineage(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]
async def search_grok_threads(workspace: str | Path, query: str, *, limit: int = NATIVE_LIST_DEFAULT_LIMIT, scope: GrokThreadScope = GrokThreadScope.SDK) -> tuple[NativeThreadSummary, ...]
async def delete_grok_thread(thread_id: str, workspace: str | Path, *, scope: GrokThreadScope = GrokThreadScope.SDK, config: GrokThreadConfig | None = None) -> None

# ---- opencode thread helpers (no key, no model; every one starts opencode)
async def list_opencode_threads(workspace: str | Path, *, since: timedelta | None = None, limit: int = NATIVE_LIST_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def list_recent_opencode_threads(workspace: str | Path, *, limit: int = NATIVE_RECENT_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def list_opencode_threads_since(workspace: str | Path, since: timedelta, *, limit: int = NATIVE_LIST_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def get_opencode_thread(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> NativeThreadSummary
async def read_opencode_thread(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> NativeThreadResult
async def get_opencode_thread_lineage(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def search_opencode_threads(workspace: str | Path, query: str, *, limit: int = NATIVE_LIST_DEFAULT_LIMIT, config: OpencodeThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def delete_opencode_thread(thread_id: str, workspace: str | Path, *, config: OpencodeThreadConfig | None = None) -> None

# ---- Muse thread helpers (no key, no model; WSL on Windows through config)
async def list_muse_threads(workspace: str | Path, *, since: timedelta | None = None, limit: int = NATIVE_LIST_DEFAULT_LIMIT, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def list_recent_muse_threads(workspace: str | Path, *, limit: int = NATIVE_RECENT_DEFAULT_LIMIT, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def list_muse_threads_since(workspace: str | Path, since: timedelta, *, limit: int = NATIVE_LIST_DEFAULT_LIMIT, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]
async def get_muse_thread(thread_id: str, workspace: str | Path, *, config: MuseThreadConfig | None = None) -> NativeThreadSummary
async def read_muse_thread(thread_id: str, workspace: str | Path, *, config: MuseThreadConfig | None = None) -> NativeThreadResult
async def get_muse_thread_lineage(thread_id: str, workspace: str | Path, *, config: MuseThreadConfig | None = None) -> tuple[NativeThreadSummary, ...]

# ---- Grok command functions (caller's key; private home as #1036 runs)
# Shared keyword tail K_GROK = *, api_key: str, workspace: str | Path, model: str | None = None,
#                           skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None
async def run_grok_command(command: GrokCommand, arguments: str = "", *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult
async def run_grok_goal(objective: str, *, api_key: str, workspace: str | Path, budget_tokens: int | None = None, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult
async def run_grok_implement(task: str, *, api_key: str, workspace: str | Path, effort: int | None = None, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult
async def run_grok_design(description: str, K_GROK) -> NativeThreadResult
async def run_grok_execute_plan(design_doc: str | Path, *, api_key: str, workspace: str | Path, effort: int | None = None, concurrency: int | None = None, dry_run: bool = False, auto_pr: bool = False, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult
async def run_grok_review(*, api_key: str, workspace: str | Path, local: bool = False, branch: str | None = None, pr: int | str | None = None, model: str | None = None, skills: Sequence[str | Path] = (), config: GrokThreadConfig | None = None) -> NativeThreadResult
async def run_grok_code_review(K_GROK) -> NativeThreadResult
async def run_grok_resume_claude(session: str, K_GROK) -> NativeThreadResult
async def run_grok_resume_codex(session: str, K_GROK) -> NativeThreadResult
async def run_grok_resume_cursor(session: str, K_GROK) -> NativeThreadResult
async def run_grok_imagine(description: str, K_GROK) -> NativeThreadResult
async def run_grok_imagine_video(description: str, K_GROK) -> NativeThreadResult
async def run_grok_plan(task: str, K_GROK) -> NativeThreadResult
async def run_grok_explore(question: str, K_GROK) -> NativeThreadResult

# ---- opencode command functions (caller's key; model required as in #1036)
# K_OPENCODE = *, api_key: str, workspace: str | Path, model: str, skills: Sequence[str | Path] = (),
#              config: OpencodeThreadConfig | None = None
async def run_opencode_command(command: str, arguments: str = "", K_OPENCODE) -> NativeThreadResult
async def run_opencode_review(target: str | None = None, K_OPENCODE) -> NativeThreadResult
async def run_opencode_init(K_OPENCODE) -> NativeThreadResult
async def run_opencode_plan(task: str, K_OPENCODE) -> NativeThreadResult

# ---- Muse skill functions (caller's key; WSL on Windows through config)
# K_MUSE = *, api_key: str, workspace: str | Path, model: str | None = None, skills: Sequence[str | Path] = (),
#          config: MuseThreadConfig | None = None
async def run_muse_skill(skill: str, prompt: str, K_MUSE) -> NativeThreadResult
async def run_muse_goal(objective: str, K_MUSE) -> NativeThreadResult
async def run_muse_plan(task: str, K_MUSE) -> NativeThreadResult
async def run_muse_import(session_ref: str, K_MUSE) -> NativeThreadResult
async def run_muse_scaffold(description: str, K_MUSE) -> NativeThreadResult
async def run_muse_browser_app(description: str, K_MUSE) -> NativeThreadResult
async def init_muse_workspace(workspace: str | Path, *, dry_run: bool = False, config: MuseThreadConfig | None = None) -> NativeCommandOutput   # keyless; bound from MuseThreadHelpers
```

`K_GROK`, `K_OPENCODE` and `K_MUSE` are shorthand in this block only. The real signatures spell out the keyword-only tail in full, exactly as #1036's `run_<harness>_thread` does.

Public records and enums (lib layer; exported from `vidbyte.harnesses.native` where noted):

```python
@dataclass(frozen=True, slots=True)
class NativeThreadSummary:                       # exported
    harness: NativeHarness
    thread_id: str                               # NATIVE_THREAD_ID_PATTERN, <= NATIVE_THREAD_ID_MAX_CHARS
    title: str | None                            # None, or non-blank NUL-free text <= NATIVE_TITLE_MAX_CHARS
    created_at: datetime                         # UTC-aware (to_utc_datetime)
    updated_at: datetime                         # UTC-aware
    parent_thread_id: str | None                 # pattern as thread_id; != thread_id
    model: str | None                            # NATIVE_MODEL_PATTERN, <= NATIVE_MODEL_MAX_CHARS

@dataclass(frozen=True, slots=True)
class NativeCommandOutput:                       # exported
    harness: NativeHarness
    text: str

class GrokThreadScope(StrEnum):                  # exported
    SDK = "sdk"
    USER = "user"

class GrokCommand(StrEnum):                      # exported; value = the slash command name
    GOAL = "goal"; IMPLEMENT = "implement"; DESIGN = "design"; EXECUTE_PLAN = "execute-plan"; REVIEW = "review"
    CODE_REVIEW = "code-review"; RESUME_CLAUDE = "resume-claude"; RESUME_CODEX = "resume-codex"; RESUME_CURSOR = "resume-cursor"
    IMAGINE = "imagine"; IMAGINE_VIDEO = "imagine-video"
```

Internal names. They are not exported, and tests reach them only through the public functions or `vidbyte.lib`. The implementer must use these names, and reviewers check them:

```python
# vidbyte.lib.dataclasses.native_threads
class NativeHelperRequest: harness; operation: NativeThreadOperation; workspace: Path | str; thread_id: str | None = None
                           since: timedelta | None = None; limit: int | None = None; query: str | None = None
                           scope: GrokThreadScope | None = None; dry_run: bool = False
class NativeToolCall: name: str; arguments: str
class GrokCommandArguments: command: GrokCommand | None = None; agent: GrokAgent | None = None; text: str = ""
                            design_doc: Path | str | None = None; budget_tokens: int | None = None; effort: int | None = None
                            concurrency: int | None = None; dry_run: bool = False; auto_pr: bool = False
                            local: bool = False; branch: str | None = None; pr: int | str | None = None
                            named: bool = False; text_field: str = "arguments"; skill_names: tuple[str, ...] = ()   # D-30, D-32
class GrokThreadFile: summary: NativeThreadSummary; search_text: tuple[str | None, ...]; agent_name: str | None; path: Path
NativeThreadRequest.command: str | None = None    # new last field (opencode --command name / Muse skill id)
# vidbyte.lib.dataclasses.validation
RecordFieldConverter.to_utc_datetime(value: object, field_name: str) -> datetime

# vidbyte.harnesses.native.hostkit
NativeThreadListing.cutoff(since: timedelta | None, now: datetime) -> datetime | None
NativeThreadListing.newest(summaries: Iterable[NativeThreadSummary], *, cutoff: datetime | None, limit: int) -> tuple[NativeThreadSummary, ...]
NativeThreadListing.matches(texts: Sequence[str | None], query: str) -> bool
NativeThreadListing.check_step(chain: tuple[NativeThreadSummary, ...], parent_id: str, errors: NativeErrorFactory, request: NativeHelperRequest) -> None
NativeCommandEvidence.require(calls: tuple[NativeToolCall, ...], *, tools: tuple[str, ...], fragment: str | None, errors, request: NativeThreadRequest, thread_id: str) -> None
NativeCommandEvidence.require_value(actual: str | None, *, expected: str, member: str, errors, request: NativeThreadRequest, thread_id: str) -> None
NativeCommandEvidence.require_text(document: str, *, fragment: str, errors, request: NativeThreadRequest, thread_id: str) -> None

# vidbyte.harnesses.native.grok
GrokHome.private(workspace: Path) -> Path; GrokHome.user() -> Path; GrokHome.of(scope: GrokThreadScope, workspace: Path) -> Path
GrokHome.prepare(request: NativeThreadRequest, errors) -> Path; GrokHome.fallback() -> Path | None
GrokHome.environment(home: Path, api_key: str | None) -> dict[str, str]
GrokStore.threads(home: Path, request: NativeHelperRequest, errors) -> tuple[GrokThreadFile, ...]   # sync; via to_thread; whole scope, strict (list/search)
GrokStore.thread(home: Path, request: NativeHelperRequest | NativeThreadRequest, errors, *, thread_id: str) -> GrokThreadFile | None   # sync; one id only (D-27); a NativeThreadRequest has no scope, so it means SDK scope: every group of the run's private home
GrokStreamWire.read(outcome, request: NativeThreadRequest, errors, *, timeout_seconds: float, thread_id: str) -> NativeThreadResult   # thread_id = the minted id (D-29)
GrokStreamWire.tool_calls(stdout: str) -> tuple[NativeToolCall, ...]
GrokHelperWire.thread_file(data: bytes, path: Path, errors, request) -> GrokThreadFile
GrokHelperWire.document(outcome, request: NativeHelperRequest, errors) -> NativeThreadResult
GrokHelperWire.deleted(outcome, request: NativeHelperRequest, errors) -> None
GrokHelperRun.export(home: Path, request: NativeHelperRequest | NativeThreadRequest, config: GrokThreadConfig, errors, *, thread_id: str) -> NativeThreadResult   # async; the keyless `grok export` child, shared by read_grok_thread and code-review evidence; builds its CliInvocation inline from GrokHome.environment(home, None) and calls no other GrokHelperRun method (R-22)
GrokCommandRun.execute(request: NativeThreadRequest, arguments: GrokCommandArguments, config: GrokThreadConfig, errors) -> NativeThreadResult
# vidbyte.harnesses.native.opencode
OpencodeHelperWire.sessions(outcome, request: NativeHelperRequest, errors) -> tuple[tuple[NativeThreadSummary, str], ...]   # `session list` rows (roots only, parent None) with their directory; lists filter by directory
OpencodeHelperWire.rows(outcome, request: NativeHelperRequest, errors) -> tuple[NativeThreadSummary, ...]   # `opencode db` rows of OPENCODE_SESSION_QUERY, with parent_id (D-26)
OpencodeHelperWire.document(outcome, request, errors) -> NativeThreadResult; OpencodeHelperWire.deleted(outcome, request, errors) -> None
# vidbyte.harnesses.native.muse
MuseChildren.open_config(skills: tuple[Path, ...], request, errors) -> Path            # async, shielded
MuseChildren.close_config(folder: Path) -> None                                        # async
MuseChildren.overlay(launcher: MuseLauncher, folder: Path) -> dict[str, str]
MuseChildren.serve(prefix: tuple[str, ...], frames: str, launcher, overlay, mark: str | None, cwd: Path) -> CliInvocation
MuseChildren.run(invocation, launcher, request, errors, *, mark: str | None, thread_id: str | None) -> CliOutcome  # async
MuseSessionWire.list_params(workspace_root: str, limit: int, cutoff: datetime | None) -> dict[str, object]
MuseSessionWire.read_items_params(thread_id: str) -> dict[str, object]
MuseSessionWire.result(outcome, request, errors) -> Mapping[str, object]
MuseSessionWire.sessions(result, request, errors) -> tuple[NativeThreadSummary, ...]
MuseSessionWire.session(result, request, errors) -> NativeThreadSummary
MuseSessionWire.tool_calls(result, request, errors, *, thread_id: str) -> tuple[NativeToolCall, ...] | None   # None in history mode anchoredSnapshot (D-33)
MuseHelperRun.transcript(request, config, errors, *, thread_id: str) -> str   # async flow; the D-17 export child, sharing the private _export helper with read (D-33)
MuseCommandRun.execute(request: NativeThreadRequest, config: MuseThreadConfig, errors, *, template: str, tool: str, fragment: str | None) -> NativeThreadResult
```

## §9 Data, API, configuration, migration

### 9.1 Data model

Nothing persists in the SDK. Every record is a frozen, slotted, in-memory dataclass that validates in `__post_init__` and raises `ConfigurationError(details={"field": <public name>})`.

**Int and bool checks (review R-3).**

- **The rule.** Every int and bool field in these records goes through `RecordFieldValidator.require_int` / `require_bool` (`vidbyte/lib/dataclasses/validation.py:85` / `:92`). No field uses an inline `isinstance(x, bool)` guard.
- **Why.** Lint C002 is blocking, with a baseline of 9. It flags any non-generic name guarded inline by `isinstance(x, bool)` in two functions, and `limit`, `concurrency` and `status` already have such guards elsewhere.
- **`pr`.** Check `isinstance(pr, str)` first. Otherwise call `require_int(pr, "pr", minimum=1, maximum=GROK_PR_MAX_NUMBER)`.
- **The opencode epoch-millisecond conversion.** It is one private converter, used by `OpencodeHelperWire.sessions`, and it calls `require_int`.

**`NativeThreadSummary`** (exported). Fields are as in §8.5.

- **Rules:**
  - `harness` goes through `to_enum`.
  - The ids follow the `NATIVE_THREAD_ID_PATTERN` rules, and `parent_thread_id != thread_id`.
  - `title` is `None` or non-blank text without NUL, at most `NATIVE_TITLE_MAX_CHARS`. Readers map an empty or whitespace title to `None`.
  - `created_at` and `updated_at` go through `RecordFieldConverter.to_utc_datetime`.
  - `model` is `None` or matches `NATIVE_MODEL_PATTERN` and is at most `NATIVE_MODEL_MAX_CHARS`.
  - Readers convert any `ConfigurationError` from this record into `<harness>.protocol_mismatch` (INV-6).
- **Mapping per harness:**

| Field | Grok (`summary.json`, A-2) | opencode (`session list` row / `db` row, A-12/A-29) | Muse (MSP `Session`, `msp.schema.json`) |
|---|---|---|---|
| thread_id | the session folder name | `id` / `id` | `sessionId` |
| title | `generated_title` (null or absent → None) | `title` / `title` | always `None` (no title in MSP) |
| created_at | `created_at` (RFC 3339) | `created` / `time_created` (epoch ms int) | `createdAt` (RFC 3339) |
| updated_at | `updated_at` | `updated` / `time_updated` | `updatedAt` |
| parent_thread_id | `parent_session_id` | `None` (list rows are roots and carry no parent) / `parent_id` (null → None) | `forkedFrom.sessionId` (`forkedFrom` null → None) |
| model | `current_model_id` | `None` (D-24) | `modelId` |

**`NativeHelperRequest`** (internal; D-1). `__post_init__` runs these checks in order:

1. `harness` goes through `to_enum`, then `operation` goes through `to_enum`. `operation ∈ NATIVE_HELPER_OPERATIONS[harness]`, else field `operation`.
2. `workspace` is checked and resolved exactly as `NativeThreadRequest._checked_workspace` does (field `workspace`).
3. `thread_id` is required, with the pattern and cap, iff `operation ∈ NATIVE_THREAD_ID_OPERATIONS`; otherwise it must be `None` (field `thread_id`).
4. `since`:
   - It is required iff the operation is in `NATIVE_SINCE_REQUIRED_OPERATIONS`, optional iff it is in `NATIVE_SINCE_OPTIONAL_OPERATIONS`, and otherwise `None`.
   - When given it must be a `timedelta` (not a number), with `timedelta(0) < since <= NATIVE_SINCE_MAX`.
5. `limit` is required iff the operation is in `NATIVE_LIMIT_OPERATIONS`, checked with `require_int(limit, "limit", minimum=1, maximum=NATIVE_LIST_MAX_LIMIT)` (which refuses `bool`); otherwise `None`.
6. `query` is required iff the operation is in `NATIVE_QUERY_OPERATIONS`: non-blank text without NUL, at most `NATIVE_QUERY_MAX_CHARS`. Otherwise `None`.
7. `scope` is required (`to_enum(GrokThreadScope)`) iff `harness is GROK`; otherwise `None`.
8. `dry_run` passes `require_bool`, and it may be `True` only for `INIT_MUSE_WORKSPACE`.

**`NativeThreadRequest.command`** (new last field, default `None`):

- It must be `None` for Grok.
- For opencode and Muse, when it is set:
  - the verb must be `RUN`;
  - the value matches `NATIVE_COMMAND_PATTERN` (`^[A-Za-z0-9][A-Za-z0-9._/:-]*$`) and is at most `NATIVE_COMMAND_MAX_CHARS`;
  - the field name used in errors is `NATIVE_COMMAND_ARGUMENTS[harness]` (`"command"` for opencode, `"skill"` for Muse).
- The prompt rule changes for opencode only: with `command` set, `prompt` may be `""`. Every other case keeps #1036's non-empty prompt rule.

**`GrokCommandArguments`** (internal):

1. Exactly one of `command` and `agent` is set (field `command`).
2. `text` is a string without NUL, at most `NATIVE_COMMAND_TEXT_MAX_CHARS`. It must be non-blank for an agent, and for every command except `REVIEW` and `CODE_REVIEW` unless `design_doc` is set. The error field is `text_field`: `arguments` for `run_grok_command`, and the public parameter (`objective`, `task`, `description`, `session`, `question`) for a named wrapper (D-25).
3. `design_doc` is allowed only with `EXECUTE_PLAN`. It must be an absolute path to an existing file, and its text must contain no whitespace (field `design_doc`; D-30).
4. `budget_tokens` is allowed only with `GOAL`, as an int in `1..GROK_GOAL_MAX_BUDGET_TOKENS`.
5. `effort` is allowed only with `IMPLEMENT` (`1..GROK_IMPLEMENT_MAX_EFFORT` = 5) or `EXECUTE_PLAN` (`1..GROK_EXECUTE_PLAN_MAX_EFFORT` = 2).
6. `concurrency` (`1..GROK_EXECUTE_PLAN_MAX_CONCURRENCY` = 8), `dry_run` and `auto_pr` are allowed only with `EXECUTE_PLAN`.
7. `local`, `branch` and `pr` are allowed only with `REVIEW`, at most one of them set:
   - `branch` matches `GROK_BRANCH_PATTERN` and is at most `GROK_BRANCH_MAX_CHARS`;
   - `pr` is an int ≥ 1 (not a `bool`), or a string matching `GROK_PR_PATTERN` (`^([1-9][0-9]*|https://\S+)$`) and at most `GROK_PR_MAX_CHARS`.
8. Every int check refuses `bool` (lint C006), through `require_int` (C002).
9. When `named` is `True` (every named wrapper; `False` only for `run_grok_command`) and `command` is set:
   - `text` has no whitespace-separated token that equals a flag in `GROK_TEXT_OPTION_FLAGS[command]` (goal: `--budget`; implement: `--effort`; every other command: none) or starts with `<flag>=` (review R-19);
   - for `GOAL`, `text.strip().casefold()` is not in `GROK_GOAL_RESERVED_WORDS`;
   - both refusals name `text_field` (D-30).
10. When `command` is set, `skill_names` (the folder names of the request's `skills`, filled by `GrokCommands._call`) must not contain `command.value` (field `skills`; D-32).

**`NativeToolCall`** (internal). `name` is a non-blank string of at most `NATIVE_TOOL_NAME_MAX_CHARS`. `arguments` is a string: the JSON text of Grok's `rawInput`, or Muse's verbatim `args`. Readers skip a tool event without a usable name, because such an event cannot be evidence.

**`GrokThreadFile`** (internal):

- `summary` is the record above.
- `search_text` is the tuple `(generated_title, session_summary, last_turn_summary)`, `None` where absent. It is passed as is to `NativeThreadListing.matches(texts, query)` (review R-12).
- `agent_name` is `str | None`.
- `path` is the `summary.json` path.

**`NativeCommandOutput`** (exported). `harness` goes through `to_enum`; `text` must be a `str`.

**Enums** (append order is part of the contract). New members are added in the order listed after the existing ones:

- `NativeThreadOperation` gets 47 new members. The value of each equals its function name; the member name is the upper-case value.
  - **Grok helpers:** `list_grok_threads`, `list_recent_grok_threads`, `list_grok_threads_since`, `get_grok_thread`, `read_grok_thread`, `get_grok_thread_lineage`, `search_grok_threads`, `delete_grok_thread`.
  - **opencode helpers:** the same eight, with `opencode`.
  - **Muse helpers:** `list_muse_threads`, `list_recent_muse_threads`, `list_muse_threads_since`, `get_muse_thread`, `read_muse_thread`, `get_muse_thread_lineage`.
  - **Grok commands:** `run_grok_command`, `run_grok_goal`, `run_grok_implement`, `run_grok_design`, `run_grok_execute_plan`, `run_grok_review`, `run_grok_code_review`, `run_grok_resume_claude`, `run_grok_resume_codex`, `run_grok_resume_cursor`, `run_grok_imagine`, `run_grok_imagine_video`, `run_grok_plan`, `run_grok_explore`.
  - **opencode commands:** `run_opencode_command`, `run_opencode_review`, `run_opencode_init`, `run_opencode_plan`.
  - **Muse functions:** `run_muse_skill`, `run_muse_goal`, `run_muse_plan`, `run_muse_import`, `run_muse_scaffold`, `run_muse_browser_app`, `init_muse_workspace`.
- `NativeThreadProblem` gains `COMMAND_NOT_RUN = "command_not_run"` and `STORE_UNREADABLE = "store_unreadable"`.
- **Existing flag and vocabulary enums:**
  - `GrokFlag` gains `AGENT = "--agent"` and `SESSION_ID = "--session-id"` (D-29).
  - `OpencodeFlag` gains `COMMAND = "--command"` and `MAX_COUNT = "--max-count"` (D-19).
  - `MuseFlag` gains `SESSION = "--session"`, `OUT = "--out"` and `DRY_RUN = "--dry-run"`.
  - `NativeEnvironmentVariable` gains `GROK_WORKFLOWS = "GROK_WORKFLOWS"` and `PWD = "PWD"`.
  - `MuseMethod` gains `SESSION_LIST = "session/list"`.
- **New enums:**
  - `GrokThreadScope` and `GrokCommand` (§8.5).
  - `GrokAgent(PLAN = "plan", EXPLORE = "explore")`.
  - `GrokCommandFlag(BUDGET = "--budget", EFFORT = "--effort", CONCURRENCY = "--concurrency", DRY_RUN = "--dry-run", AUTO_PR = "--auto-pr", LOCAL = "--local", BRANCH = "--branch", PR = "--pr")`. These are the flags written inside the slash-command line, not on argv.
  - `GrokEventType(TEXT = "text", TOOL_CALL = "tool_call", TOOL_CALL_UPDATE = "tool_call_update", END = "end", ERROR = "error")`.
  - `MuseSkill(PLAN = "bundled:plan", IMPORT = "bundled:import", SCAFFOLD = "bundled:greenfield-project-scaffolding", BROWSER_APP = "bundled:browser-app-delivery")`.
- `FailureCode`: INV-22.

**Lifecycle.** There is none. Records live for one call.

**Volume.** Lists are bounded by `limit` (≤ 200). Lineage holds ≤ 64 entries. The tool-call tuples are bounded by the 64 MiB output cap. No array is unbounded.

### 9.2 API and interface surface

Public library functions only. There are no routes or CLI commands, and no auth beyond the caller's own vendor key on the skill functions.

**Validation at the boundary:** INV-3 for every function. **Errors:** INV-5, with the codes listed per row.

**Helpers.** The vendor mechanism and the codes each one can raise. `grok` / `opencode` / `muse` means the resolved launcher. The child environment always has self-update off and no key.

| Function(s) | Mechanism | Codes beyond `configuration.invalid_argument` / `runtime.error` |
|---|---|---|
| `list_grok_threads`, `list_recent_grok_threads`, `list_grok_threads_since`, `search_grok_threads` | `GrokStore.threads` in `to_thread`: `home = GrokHome.of(scope, workspace)`. **Groups** are the *directories* directly under `home/sessions/`; **session candidates** are the *directories* inside a group; every file at either level (`session_search.sqlite`, `permission*.toml`, `.cwd`) is ignored (EC-66). SDK reads all groups of the private home; USER reads the groups whose `urllib.parse.unquote(name)` (or the stripped `.cwd` file, capped at `GROK_CWD_MAX_BYTES`) normcase-equals `str(workspace)`. Each candidate's `summary.json`: regular file only; `path.open("rb")`, then the `os.fstat` size check against `GROK_SUMMARY_MAX_BYTES`. Strict over the whole scope (INV-6), with the layout bound of EC-67 (D-31) | `grok.store_unreadable`, `grok.protocol_mismatch` |
| `get_grok_thread`, `get_grok_thread_lineage` | `GrokStore.thread(home, …, thread_id=id)` in `to_thread`: the same groups in scope, then only `<group>/<id>/summary.json` (D-27). No hit in any group → not found. Lineage repeats the lookup for each `parent_session_id`, with `NativeThreadListing.check_step` | `grok.store_unreadable`, `grok.protocol_mismatch` (that id's file only), `grok.thread_not_found` |
| `read_grok_thread` | store lookup (`GrokStore.thread`, as get), then `GrokHelperRun.export`: `grok export <id>`. Environment `{GROK_HOME: home, GROK_DISABLE_AUTOUPDATER: "1"}`; `env_remove` = both key variables; cwd = workspace; control timeout; cap `NATIVE_PROCESS_MAX_OUTPUT_BYTES`. stdout → `text`. stderr or stdout containing `GROK_SESSION_NOT_FOUND_TEXT.format(thread_id=id)` → not found | `grok.not_installed`, `grok.launcher_refused`, `grok.launch_failed`, `grok.thread_not_found`, `grok.timed_out`, `grok.output_too_large`, `grok.run_failed`, `grok.store_unreadable`, `grok.protocol_mismatch` |
| `delete_grok_thread` | store lookup (`GrokStore.thread`), then `grok sessions delete <id>` (same environment), then a `to_thread` check that `GrokThreadFile.path.parent` no longer exists | as `read_grok_thread`; a folder that still exists → `grok.run_failed` |
| `list_opencode_threads`, recent, since, `search_opencode_threads` | `opencode session list --format=json --max-count=NATIVE_OPENCODE_SCAN_MAX` (roots only, project-wide); cwd = workspace; overlay `{OPENCODE_DISABLE_AUTOUPDATE: "1", PWD: str(workspace)}`; control timeout. Empty stdout → `()`; rows filtered by `directory` (D-19). Exactly the cap → `protocol_mismatch` naming it (EC-75) | `opencode.not_installed`, `opencode.launcher_refused`, `opencode.launch_failed`, `opencode.timed_out`, `opencode.output_too_large`, `opencode.run_failed`, `opencode.protocol_mismatch` |
| `get_opencode_thread`, `get_opencode_thread_lineage` | `opencode db --format=json "<OPENCODE_SESSION_QUERY with the id>"` (same environment; D-26): one child for get, one per step for lineage, following `parent_id` with `check_step`. A parent with no row ends the chain (EC-25). Database-wide by exact id, with no `directory` filter. Rows are read by `OpencodeHelperWire.rows` | as list, plus `opencode.thread_not_found` (`[]`) and `opencode.protocol_mismatch` (more than one row, or a bad member) |
| `read_opencode_thread` | `opencode export <id>` (same environment); stdout returned whole | as list, plus `opencode.thread_not_found` (`OPENCODE_SESSION_NOT_FOUND_MARKER` in stderr) |
| `delete_opencode_thread` | `opencode session delete <id>` (same environment); exit 0 and no marker → `None` | as get |
| `list_muse_threads`, recent, since | `MuseChildren.open_config((), …)`, then one `muse serve` batch: `session/list {workspaceRoot: launcher.visible_path(workspace), limit, updatedAfter?}`. `env_remove META_API_KEY`; control timeout; folder removed in `finally` | `muse.not_installed`, `muse.launcher_refused`, `muse.launch_failed`, `muse.wsl_unavailable`, `muse.timed_out`, `muse.output_too_large`, `muse.protocol_mismatch` (`-32601` or bad shape), `muse.run_failed` (other JSON-RPC errors) |
| `get_muse_thread`, `get_muse_thread_lineage` | `session/read {sessionId, excludeItems: true}`, one serve per step | as list, plus `muse.thread_not_found` (`-32020`) |
| `read_muse_thread` | `session/read` check, then `muse export --session <id> --out <visible(folder/export/thread.json)>`, cwd = `folder/export`; the file is read in `to_thread` with the `os.fstat` cap (D-17) | as get; no file → `muse.protocol_mismatch`; oversize → `muse.output_too_large` |

**Command and skill functions.** All of them validate, then run, then verify. Every Grok command run also carries `--session-id=<minted uuid4>` (D-29). "Line" is the text grok receives in `--single=`. Option parts appear only when set, in the order shown, each as ` <flag> <value>`. `<t>` is the function's text argument.

| Function | Building block call | Grok line / opencode argv / Muse exec prompt | Evidence (INV-8) |
|---|---|---|---|
| `run_grok_command(c, a)` | itself | `/<c.value>` when `a == ""`, else `/<c.value> <a>` | by `c` (rows below) |
| `run_grok_goal(t, budget_tokens=b)` | `GOAL`, `GROK_WORKFLOWS=0` in the child environment | `/goal <t>[ --budget <b>]` | a `tool_call` with `toolName == "update_goal"` |
| `run_grok_implement(t, effort=e)` | `IMPLEMENT` | `/implement[ --effort <e>] <t>` | a `read_file` call whose `rawInput` contains `shared/personas/implementer.md` |
| `run_grok_design(t)` | `DESIGN` | `/design <t>` | `read_file` + `shared/personas/design-doc-writer.md` |
| `run_grok_execute_plan(d, …)` | `EXECUTE_PLAN` | `/execute-plan <d>[ --effort <e>][ --concurrency <n>][ --dry-run][ --auto-pr]` | `read_file` + `shared/personas/implementer.md` |
| `run_grok_review(local/branch/pr)` | `REVIEW` | `/review`, `/review --local`, `/review --branch <b>` or `/review --pr <p>` | `read_file` + `shared/personas/reviewer.md` |
| `run_grok_code_review()` | `CODE_REVIEW` | `/code-review` | the run's own `grok export <minted id>` transcript contains `GROK_CODE_REVIEW_FRAGMENT` (D-28) |
| `run_grok_resume_claude/codex/cursor(t)` | `RESUME_CLAUDE/CODEX/CURSOR` | `/resume-claude <t>` (and so on) | `read_file` + `shared/resume-session/CORE.md` |
| `run_grok_imagine(t)` | `IMAGINE` | `/imagine <t>` | a `tool_call` named `image_gen` or `image_edit` |
| `run_grok_imagine_video(t)` | `IMAGINE_VIDEO` | `/imagine-video <t>` | a `tool_call` named `image_to_video` (`04-slash-commands.md:277`; A-24) |
| `run_grok_plan(t)` / `run_grok_explore(t)` | agent `PLAN` / `EXPLORE` | line = `<t>`; argv adds `--agent=plan` / `--agent=explore` | the new thread's `summary.json` `agent_name` equals the agent value |
| `run_opencode_command(c, a)` | itself | argv `run --format=json --dir=<ws> --model=<m> [#1036 options] --command=<c>`; stdin = `a`, or none when `a == ""` | opencode dispatch (D-8) |
| `run_opencode_review(target)` | `command="review"`, arguments = `target` or `""` | as above | as above |
| `run_opencode_init()` | `command="init"`, arguments `""` | as above | as above |
| `run_opencode_plan(t)` | #1036 run with `config.agent = "plan"` (a `config.agent` that is neither `None` nor `"plan"` → invalid_argument `config`) | `run … --agent=plan`, stdin `t` | opencode refuses unknown agents (A-15 note) |
| `run_muse_skill(s, t)` | itself | `MUSE_SKILL_PROMPT_TEMPLATE.format(skill=s, prompt=t)` | a `toolCall` item with `tool == "read_skill"` whose `args` contains `s`; in history mode `anchoredSnapshot`, the run's `muse export` transcript contains `read_skill` and `s` (D-33) |
| `run_muse_plan` / `run_muse_import` / `run_muse_scaffold` / `run_muse_browser_app(t)` | `run_muse_skill(MuseSkill.PLAN / IMPORT / SCAFFOLD / BROWSER_APP, t)` | as above | as above |
| `run_muse_goal(t)` | Muse goal template | `MUSE_GOAL_PROMPT_TEMPLATE.format(prompt=t)` | a `toolCall` item with `tool == "create_goal"` (in `anchoredSnapshot` mode, `create_goal` in the export transcript; D-33) |
| `init_muse_workspace(ws, dry_run=d)` | helper path | `muse init[ --dry-run]`, cwd = ws, no key, private config, control timeout | none; returns `NativeCommandOutput(MUSE, stdout)`, and a non-zero exit → `muse.run_failed` |

**Evidence matching rules:**

- The `rawInput` (Grok) or `args` (Muse) text is matched after every run of backslashes is replaced with `/` (pattern `NATIVE_BACKSLASH_RUN_PATTERN`), so that Windows paths match.
- The `command_not_run` detail lists the distinct tool names the run did call, through `NativeErrorFactory.listing`, or says that it called none.

**Codes:**

- **Grok command functions:** #1036's `run_grok_thread` codes, every post-launch one carrying the minted id. `grok.output_too_large` uses cap `NATIVE_PROCESS_MAX_OUTPUT_BYTES`. `grok.protocol_mismatch` covers a missing `end`, or an `end.sessionId` that is missing or differs from the minted id. Before any run, a `skills=` folder named like the command → `configuration.invalid_argument` naming `skills` (D-32). Add `grok.command_not_run`, plus `grok.store_unreadable` (plan and explore), plus the export child's `grok.timed_out` / `grok.thread_not_found` / `grok.output_too_large` / `grok.run_failed` (code-review, EC-73).
- **opencode command functions:** #1036's codes plus `opencode.command_not_run`.
- **Muse skill functions:** #1036's codes plus `muse.command_not_run`, plus the evidence read's own `muse.timed_out` / `muse.thread_not_found` / `muse.protocol_mismatch`, each with the new thread id.

**Grok stream reading order** (`GrokStreamWire.read`, mirroring `GrokWire.read`):

1. `timed_out` → `timed_out` (thread id = the minted id).
2. `stdout_truncated` → `output_too_large` (thread id = the minted id).
3. The first `error` event: key markers → `key_rejected`; otherwise → `run_failed` with its `message`.
4. A non-zero exit → `run_failed` with stderr.
5. No `end` event → `protocol_mismatch` (`end`).
6. An `end.sessionId` that is not usable, or differs from the minted id → `protocol_mismatch` (`sessionId`).
7. Text = the `data` of every `text` event after the last `tool_call` or `tool_call_update` event, joined with `""` and cut at `NATIVE_RESULT_TEXT_MAX_CHARS`, with `text_truncated` set (A-11).

### 9.3 Configuration and flags
| Variable / key | Required | Default | Purpose | Lives in |
|---|---|---|---|---|
| `GROK_WORKFLOWS` (child environment) | set by the SDK | `"0"` (`GROK_WORKFLOWS_OFF`) for `GrokCommand.GOAL` runs only | runs `/goal` in-turn with the `update_goal` driver instead of the background engine | `NativeEnvironmentVariable.GROK_WORKFLOWS`, `vidbyte/lib/constants/native_threads.py` |
| `PWD` (child environment) | set by the SDK | the resolved workspace | stops an inherited `PWD` from choosing the opencode project for helper children (D-22) | `NativeEnvironmentVariable.PWD` |
| `GROK_HOME` (child environment) | set by the SDK | scope home | the store that `grok export`/`sessions delete` read | existing member |
| `scope` (function parameter) | no | `GrokThreadScope.SDK` | which Grok store helpers read | `GrokThreadScope` |
| `NATIVE_LIST_DEFAULT_LIMIT` / `NATIVE_RECENT_DEFAULT_LIMIT` / `NATIVE_LIST_MAX_LIMIT` | — | 20 / 10 / 200 | list defaults and ceiling | constants |
| `NATIVE_SINCE_MAX` | — | `timedelta(days=3650)` | ceiling for `since` (EC-4) | constants |
| `NATIVE_QUERY_MAX_CHARS`, `NATIVE_TITLE_MAX_CHARS`, `NATIVE_TOOL_NAME_MAX_CHARS`, `NATIVE_COMMAND_MAX_CHARS` | — | 1000, 4096, 256, 128 | text caps | constants |
| `NATIVE_LINEAGE_MAX_DEPTH` | — | 64 | lineage bound | constants |
| `GROK_SUMMARY_MAX_BYTES`, `GROK_CWD_MAX_BYTES` | — | 1048576, 65536 | Grok file read caps | constants |
| `GROK_SUMMARY_GRACE_SECONDS` | — | 60 | age after which a store with no `summary.json` at all is a layout mismatch (D-31, EC-67) | constants |
| `GROK_GOAL_RESERVED_WORDS`, `GROK_CODE_REVIEW_FRAGMENT`, `GROK_IMAGE_TO_VIDEO_TOOL` | — | (`status`, `pause`, `resume`, `clear`); `deep code quality audit of the current branch's changes`; `image_to_video` | D-30, D-28, §9.2 | constants |
| `NATIVE_COMMAND_RESERVED_CHARS` | — | 1024 | room left in the argv prompt cap for the slash line and options (D-25) | constants |
| `GROK_GOAL_MAX_BUDGET_TOKENS`, `GROK_IMPLEMENT_MAX_EFFORT`, `GROK_EXECUTE_PLAN_MAX_EFFORT`, `GROK_EXECUTE_PLAN_MAX_CONCURRENCY`, `GROK_BRANCH_MAX_CHARS`, `GROK_PR_MAX_CHARS` | — | 100000000, 5, 2, 8, 255, 2048 | Grok command option bounds (from the skills' argument hints) | constants |
| `GROK_PR_MAX_NUMBER` | — | 999999999 | upper bound for an int `pr` (`require_int` needs one; R-3) | constants |
| `NATIVE_OPENCODE_SCAN_MAX` | — | 10000 | `--max-count` for `opencode session list`; exactly this many rows is an error (D-19, EC-75) | constants |
| `GROK_TEXT_OPTION_FLAGS` | — | `{GOAL: (BUDGET,), IMPLEMENT: (EFFORT,)}`, every other command `()` | the option flags each named wrapper's text may not carry (D-30, R-19) | constants |
| `OPENCODE_SESSION_QUERY`, `OPENCODE_COMMAND_NOT_FOUND_TEXT` | — | `SELECT id, title, time_created, time_updated, parent_id, directory FROM session WHERE id = '{thread_id}'`; `Command not found: "{command}"` (a prefix) | D-26; D-8 | constants |

No user-facing configuration file, environment variable, or config-record field is added.

### 9.4 Migrations and compatibility

These public contracts change, all additively:

- `vidbyte.harnesses.native.__all__` grows from 17 names to 68.
- Enums gain members, appended only.
- `FailureCode` gains 4 members, appended only.
- `NativeThreadError.expected` text becomes generic (D-20).
- The texts of the `thread_not_found` observation and of the three `*_THREAD_NOT_FOUND` likely-cause and next-step entries are widened (FR-17).

Callers that compare codes or members keep working. No deprecation path is needed: nothing is renamed or removed. The private methods `GrokThreadRun._fallback`, `_prepare_home` and `_environment`, and `MuseThreadRun._prepare_config`, `_discard`, `_overlay`, `_serve_invocation` and `_run`, move to `GrokHome` and `MuseChildren` (internal names; no test imports them). There is no data migration.

## §10 Security and tenancy
| ID | Attacker | Shortest path to harm | Control | Where the control sits |
|---|---|---|---|---|
| T-1 | Careless user | passes `thread_id="../../.ssh"` to `get_grok_thread` or `delete_grok_thread`, and the SDK reads or deletes outside the store; or passes `"-rf"`, which becomes a flag | the `NATIVE_THREAD_ID_PATTERN` fullmatch in `NativeHelperRequest` before any path join or argv build; the Grok delete runs only for an id found by the store lookup (INV-9, INV-11) | `vidbyte/lib/dataclasses/native_threads.py:NativeHelperRequest`, `grok/helpers.py:GrokHelperRun` (SDK process, before any child) |
| T-2 | Hostile user (a crafted `summary.json`, `.cwd` or vendor output in a store the user browses) | a multi-GB or deeply nested file exhausts memory, or crafted text lands in an error and is then logged | byte caps with `os.fstat` before reading; strict member checks; vendor text scrubbed and capped at `NATIVE_VENDOR_MESSAGE_MAX_CHARS`; error messages name members and paths, never file contents (INV-6, INV-16) | `GrokStore`, `GrokHelperWire`, `NativeErrorFactory` |
| T-3 | Compromised teammate / leaked credential | the key leaks through argv (visible in `ps`), through a file, through an error, or reaches a helper child that does not need it | the key travels only in the child environment (or the inline config for opencode); it is registered for scrubbing before any output is read; helper children strip all key variables (INV-2, INV-24, NFR-1) | `GrokCommandRun.execute`, `OpencodeThreadRun.execute`, `MuseThreadRun.execute`, helper invocations (`env_remove`) |
| T-4 | Another tenant (another OS user on the same machine) | reads another user's threads | none needed: every store is under the calling user's home or WSL user. The SDK adds no shared location and no cross-user path | the OS file permissions of `~/.vidbyte`, `~/.grok` and the opencode and Muse stores |
| T-5 | Hostile workspace (an untrusted repo's `opencode.json` or plugins) | `opencode session list` or `export` in that workspace loads the repo's opencode config and plugins, which can run code | an accepted limitation, kept from #1036 T-6: "pass only trusted workspaces to the opencode functions", now also stated for the helpers in the README | documentation (README native bullet) |
| T-6 | Inherited local configuration | Grok skill runs in the private home still load `~/.claude` hooks, skills and MCP servers (verified with `grok inspect`; #1036 EC-44 is false), so the user's hooks run inside SDK Grok runs | an accepted limitation (NG-9): the README replaces the false EC-44 sentence with this fact | `vidbyte/harnesses/README.md` |
| T-7 | Careless user (external side effects) | `run_grok_execute_plan(auto_pr=True)` pushes branches and opens PRs, and `run_grok_review(pr=…)` posts a pending review | off by default; enabled only by the explicit keyword argument; the docstrings name the effect | `GrokCommandArguments` defaults; `grok/commands.py` docstrings |
| T-8 | Careless user, or hostile text the caller forwards (a design-doc file name, an issue title used as a goal) | text in a named Grok wrapper becomes a slash-command option: `--auto-pr` pushes branches without T-7's opt-in, `--budget 99999999` spends past `GROK_GOAL_MAX_BUDGET_TOKENS`, or `clear` wipes the session's goal | the D-30 refusals in `GrokCommandArguments` (`named=True`) before any child starts (INV-9, EC-69, EC-70, EC-42) | `vidbyte/lib/dataclasses/native_threads.py:GrokCommandArguments` (SDK process) |
| T-9 | Careless or hostile caller | passes `thread_id="x' OR '1'='1"` (or `'; DROP TABLE session; --`) to `get_opencode_thread`, so the `opencode db` query reads or changes other rows | `NATIVE_THREAD_ID_PATTERN` (`^[A-Za-z0-9][A-Za-z0-9_-]*$`) in `NativeHelperRequest` refuses every quote, space and semicolon before the SQL is built. The SQL is the constant `OPENCODE_SESSION_QUERY`, a single `SELECT` whose only variable is that id (INV-9, EC-5) | `vidbyte/lib/dataclasses/native_threads.py:NativeHelperRequest` (SDK process, before any child) |

Every new function is a local library call. There is no endpoint to authenticate. Secrets follow #1036's convention: the key is a `field(repr=False)` on `NativeThreadRequest` and is registered with `NativeErrorFactory.register_secret`, and `HarnessRedactor` scrubs all vendor text.

## §11 Codebase grounding

- **Rules read:**
  - `AGENTS.md` (all sections): Repository Map; "Do not grep … `docs/`"; full gate before done; principles 1–5; Placement Rules for dataclasses and enums; "Existing code".
  - `CLAUDE.md` (`@AGENTS.md`).
  - `REPO_MAP.md`: the `vidbyte/harnesses/native/` entry (lines 159–161) and `vidbyte/lib/process/` (line 215).
  - `contracts/sdk-public-api.json` (changed by #1095): it has no entry for `vidbyte.harnesses.native`, so lint C016 does not pin these exports and no contract file changes. The surface is pinned by INV-1 and the surface test instead.
  - Grok's user guide (`~/.grok/docs/user-guide/`, Grok Build 1.0.52): `04-slash-commands.md`, `08-skills.md`, `14-headless-mode.md`, `17-sessions.md`, `22-permissions-and-safety.md` and `26-config-reference.md`; the bundled skills under `~/.grok/bundled/skills/` (`code-review`, `execute-plan`, `implement`, `review`, `design`, `resume-*`, `imagine`, `shared/`).
  - `vidbyte/harnesses/README.md` (native bullet, line 178), `vidbyte/lib/README.md`, `lint/README.md`.
  - `tests/features/harness_threads/{FEATURE.md, README.md}`.
- **Field-guide entries applied** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`):
  - `comment-format.md` — every multi-line `#` comment is a ≤ 72-column block directly above its line; `# @intent` sits on its own first line.
  - `class-bound-helpers.md` — group related helpers as static methods on a class, not as free functions.
  - `strict-config-dataclasses.md` — records validate in `__post_init__`; coerce loose vendor types before construction; bounds are named constants; caps are generous.
  - `blocking-lint-invariants.md` — A007 flags `read(CAP + 1)`, so size a capped read with `os.fstat`; S060/S039 forbid `dict[str, Any]` / `TypedDict` in lib records; S012 forbids a method named `request`.
  - `cli-backed-source-integrations.md` — fixed subcommand words, argv via `CliArgv`, and the runner owns the bounds.
  - `review-scope.md` — keep merged behavior byte-identical where this PR must touch a shared file (INV-26).
  - `local-ci-verification.md` — `PYTHONPATH=$(pwd)` for the source stage only; `git add` new files before lint and semgrep, because both scan only tracked files.
- **Stack (from manifests):**
  - Python `>=3.11` (`pyproject.toml`); package version 0.3.0. CI runs on ubuntu with Python 3.11 and 3.12 (`.github/workflows/ci.yml`).
  - pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml:48-49`).
  - No database.
  - Vendor CLIs as tested: Grok Build 1.0.52, opencode 1.18.31, Muse Code 1.0.1 (WSL `MuseUbuntu1`).
- **Commands (exact, from `context/code-map.md` §1.2 / §3 and `FEATURE.md:64`):**
  - **Install:** none into the global Python (request.md §C). Use the existing venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills` (its `Scripts/python` shadows `vidbyte` with this worktree).
  - **Lint:** `python lint/run.py`. It must end `AGENT-LINT: PASS`. One rule: `python lint/run.py --rule A007`. `git add` new files first.
  - **Typecheck:** no separate command. Mypy debt is the lint rule S009 inside `lint/run.py`.
  - **Test (focused):** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/<file>.py`, or with the venv: `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python -m pytest tests/features/harness_threads/<file> -q`.
  - **Test (area):** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads`.
  - **Test (full):** `PYTHONPATH=$(pwd) python -m pytest -q`.
  - **Full local gate:** `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` (stages `all|source|package`, `scripts/run_ci.py:261-262`).
  - **Remote-only checks:**
    - semgrep, in `.github/workflows/static-policy.yml:30`: `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` with `semgrep==1.170.1`. It is not part of `run_ci.py`.
    - CI dispatch: `gh workflow run ci.yml --ref feat/harness-thread-helpers-skills` and `gh workflow run static-policy.yml --ref feat/harness-thread-helpers-skills`. Automatic triggers are paused.
- **Baseline on clean `origin/main`.** S1 ran `tests/features/harness_threads` with the venv:
  - **r2:** this branch at `39eaa7f4`, which adds docs only to `0f69f7b7`. The result was **1 failed, 435 passed, 2 skipped in 61.86 s**.
  - **r1:** the branch at `4d51c40f` on `72a4ade1`. The result was the same, in 60.49 s. The failure is pre-existing and stale. In `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, line 193 says `assert len(main_members) == 120`, but `FailureCode` at the merge base has 148 members (`assert 148 == 120`). The full gate was not re-run by S1.
- **Directory layout relevant to this change:**
  ```
  vidbyte/harnesses/native/
    __init__.py                  (re-exports; 17 → 68 names)
    grok/      __init__.py threads.py wire.py   + store.py helpers.py commands.py
    opencode/  __init__.py threads.py wire.py   + helpers.py commands.py
    muse/      __init__.py threads.py wire.py launcher.py   + children.py helpers.py commands.py
    hostkit/   __init__.py errors.py launcher.py skills.py  + listing.py evidence.py
  vidbyte/lib/
    dataclasses/native_threads.py  dataclasses/validation.py
    enums/native_threads.py  enums/failure.py  enums/__init__.py
    constants/native_threads.py  errors/base.py
    process/{argv,runner}.py      (reused, unchanged)
  tests/features/harness_threads/  (S2: FEATURE.md README.md conftest.py fake_harness.py test_harness_threads_*.py)
  ```
- **Nearest sibling feature (the template to copy):** PR #1036's run, continue and fork. That means `vidbyte/harnesses/native/grok/threads.py` (`GrokThreads` + `GrokThreadRun`), `opencode/threads.py`, `muse/threads.py` and the three `wire.py` readers. Copy:
  - the static public class with one guarded `_call`;
  - the narrated `execute`;
  - `CliInvocation` / `CliRunner().run` / `launch_failure`;
  - the reader order (timeout, cap, vendor error, exit, shape);
  - the `name = Class.attr` bindings and the literal `__all__`;
  - the module header fields.
- **Reusable pieces:**
  - `vidbyte/lib/process/argv.py:CliArgv.build(launcher, *, command=(), options=(), style, operands=())` — every argv. Operands are unchecked, hence INV-9.
  - `vidbyte/lib/process/runner.py:CliRunner().run(CliInvocation)`, which returns `CliOutcome`; also `CliRunner.json_objects(stdout)` (JSON lines) and `CliRunner.find_program`.
  - `vidbyte/lib/dataclasses/process.py:CliInvocation(argv, env_overlay, timeout_seconds, max_output_bytes, cwd=None, stdin_text=None, env_remove=())` and `CliOption`.
  - `hostkit/errors.py:NativeErrorFactory`: `failure(problem, *, request, thread_id, outcome, vendor_text, seconds, cap_bytes, missing_member, searched)`, `from_configuration_error`, `from_unexpected`, `from_launch_failure`, `register_secret`, `listing`.
  - `hostkit/launcher.py:NativeLauncher.resolve`.
  - `hostkit/skills.py:NativeSkillFolders.replace/remove`.
  - `muse/launcher.py:MuseLauncher`: `resolve`, `visible_path`, `new_mark`, `environment`, `launch_failure`, `reap`.
  - `muse/wire.py:MuseWire.batch_frames`, `_answer`, `new_command_id`.
  - `vidbyte/lib/dataclasses/validation.py:RecordFieldValidator` (`require_text`, `accepts_text`, `require_optional_text`, `require_int`, `require_bool`, `require_directory`) and `RecordFieldConverter` (`to_enum`, `to_path`, `require_instance`).
- **Code-style exemplar** (`vidbyte/harnesses/native/grok/threads.py`, `GrokThreads._call`):
  ```python
        # One guarded try per call: cancellation and the feature's own
        # errors pass through, a refused argument names the argument,
        # and anything else is a defect named only by its class.
        errors = NativeErrorFactory(NativeHarness.GROK, operation)
        request: NativeThreadRequest | None = None
        try:
            request = NativeThreadRequest(harness=NativeHarness.GROK, verb=verb, prompt=prompt, api_key=api_key, workspace=workspace, model=model, skills=skills, thread_id=thread_id)
            settings = GrokThreadConfig() if config is None else RecordFieldConverter.require_instance(config, native_threads.NATIVE_CONFIG_ARGUMENT, GrokThreadConfig)
            return await GrokThreadRun.execute(request, settings, errors)
        except asyncio.CancelledError:
            raise
        except NativeThreadError:
            raise
        except ConfigurationError as exc:
            raise errors.from_configuration_error(exc, request) from exc
        except Exception as exc:
            raise errors.from_unexpected(exc, request) from exc
  ```
- **Domain glossary:**
  - **harness**: a vendor coding CLI (`NativeHarness`: grok, opencode, muse).
  - **thread**: a vendor session.
  - **private Grok home**: `~/.vidbyte/grok-homes/<sha16>` used as `GROK_HOME`.
  - **group folder**: `<home>/sessions/<encoded-cwd>`.
  - **helper**: a keyless browse or manage function.
  - **skill function**: runs a built-in command or skill with the caller's key.
  - **evidence**: a tool call or agent record that proves the command or skill ran.
  - **control timeout**: `NATIVE_CONTROL_TIMEOUT_SECONDS`, the bound for non-model children.
  - **MSP**: Muse's JSON-RPC serve protocol.
- **Prior specs / design docs / ADRs that constrain this:** `docs/spec/harness-thread-functions/{request.md, spec.md, review.md, pr-body.md}` (PR #1036). This spec keeps:
  - INV-1 to INV-23 (amending INV-1, INV-12 and INV-19);
  - NG-2 (no host machinery);
  - NG-10 / D-22 (no root exports);
  - A-3 (permission default refuses edits).

  It supersedes NG-3 for exactly the helpers here (KD-5) and D-17 for Grok `summary.json` reads (D-2). It records EC-44 as false (EC-63).
- **Conflicts between house style and AGENTS.md:** none. The house style's "~40–50 lines per function" is tighter than AGENTS.md and is followed. The repo's own lint (S008 complexity, S024 nesting ≤ 3) governs.

## §12 Work breakdown — everything this PR has to do

### 12.1 Feature list
| ID | Feature (capability this PR adds) | Serves | Visible to |
|---|---|---|---|
| W-1 | Lib vocabulary: the §9.1 enums and members, the 4 `FailureCode`s, the constants and texts, `NativeThreadSummary`, `NativeHelperRequest`, `NativeToolCall`, `NativeCommandOutput`, `GrokCommandArguments`, `GrokThreadFile`, `NativeThreadRequest.command`, `RecordFieldConverter.to_utc_datetime`, and the generic `expected` | FR-4, FR-16, FR-17, FR-18, AC-12, AC-19, AC-20 | developer |
| W-2 | Shared plumbing refactor: `GrokHome`, `MuseChildren`, widened request types; #1036 behavior unchanged | INV-26, AC-21 | none (internal) |
| W-3 | hostkit `NativeThreadListing` and `NativeCommandEvidence` | FR-5, FR-8, FR-9, FR-15, AC-2, AC-6, AC-7, AC-14, AC-17 | none (internal) |
| W-4 | Grok helpers (store scan, one-id lookup, export, delete, scope) | FR-1, FR-4 to FR-11, AC-1 to AC-11, AC-19, AC-25, AC-27, AC-28 | developer |
| W-5 | opencode helpers | FR-2, FR-4 to FR-10, AC-2 to AC-8, AC-10, AC-11, AC-19, AC-25, AC-31, AC-32 | developer |
| W-6 | Muse helpers and `init_muse_workspace` | FR-3, FR-4 to FR-8, FR-14, AC-2 to AC-6, AC-10, AC-11, AC-18, AC-19, AC-23, AC-25 | developer |
| W-7 | Grok command functions (streaming reader, minted session id, evidence, agents, code-review export) | FR-12, FR-15, FR-19, AC-1, AC-12 to AC-15, AC-23, AC-24, AC-29, AC-30, AC-33 | developer |
| W-8 | opencode command functions | FR-13, FR-15, FR-19, AC-16, AC-24 | developer |
| W-9 | Muse skill functions | FR-14, FR-15, FR-19, AC-17, AC-23, AC-24, AC-34 | developer |
| W-10 | Exports and naming | FR-18, INV-1, AC-20 | developer |
| W-11 | Docs: harnesses README native bullet and the REPO_MAP entry | FR-20, AC-26 | developer, operator |
| W-12 | (S2) Test pack: new tests, fake vendor paths, the surface and errors pins, the stale lines 193 and 195 rewrite (gate-forced) | AC-1 to AC-25, AC-27 to AC-34, NFR-8 | none (tests) |

### 12.2 Folder and module map
| Folder | Kind of code (per repo rules) | New? | README / header obligation | May import from |
|---|---|---|---|---|
| `vidbyte/lib/dataclasses/` | validated records (Placement Rules) | no | A001 module header updated (PURPOSE, FUNCTION INVENTORY, …); no folder README exists | `vidbyte.lib.*` only (A006) |
| `vidbyte/lib/enums/` | every enum, exported from `__init__` | no | A001 header; `__init__` export list | stdlib only |
| `vidbyte/lib/constants/` | named values, texts and tables (A007, INV-15) | no | A001 header; "Do not import from vidbyte above vidbyte.lib.enums" | `vidbyte.lib.enums` |
| `vidbyte/lib/errors/` | error classes | no | A001 header; A003 `DIAGNOSTIC_FIELDS` kept | `vidbyte.lib.*` |
| `vidbyte/harnesses/native/hostkit/` | plumbing shared by the harness subpackages | no | A001 header for each new module; no README exists (none required for an existing folder without one) | `vidbyte.lib.*`, `vidbyte.harnesses.serialization`; never a harness subpackage |
| `vidbyte/harnesses/native/{grok,opencode,muse}/` | one harness's functions, flows and readers | no | A001 header for each module; INV-15 policy; README none | `hostkit`, `vidbyte.lib.*`; not each other |
| `vidbyte/harnesses/` | harness layer docs | no | `README.md` native bullet (A009 ≤ 40,000 characters; today 10,972) | — |
| repo root | `REPO_MAP.md` | no | entry for `vidbyte/harnesses/native/` | — |
| `tests/features/harness_threads/` | feature test pack (S2) | no | `README.md` `## File Index` (S020), `FEATURE.md` Test Suite Map | — |

### 12.3 File-by-file actions
| # | Action | Path | Kind of code | What exactly changes (symbols, signatures, exports, registrations) | Governing standard (AGENTS.md § / placement rule / field-guide file / lint rule ID) | Serves | Phase |
|---|---|---|---|---|---|---|---|
| 1 | MODIFY | `vidbyte/lib/enums/native_threads.py` | enum | Append the §9.1 members, in order, to `NativeThreadOperation` (47), `NativeThreadProblem` (2), `GrokFlag`, `OpencodeFlag`, `MuseFlag`, `NativeEnvironmentVariable` and `MuseMethod`. Add the classes `GrokThreadScope`, `GrokCommand`, `GrokAgent`, `GrokCommandFlag`, `GrokEventType` and `MuseSkill`. Update the docstrings of `OpencodeFlag` and `MuseFlag` ("run options" → the subcommands now used). Extend the literal `__all__` (sorted). Update the header (PURPOSE, FUNCTION INVENTORY) | AGENTS.md "Enums go in `vidbyte/lib/enums/`" (StrEnum, closed sets); A001; S015 (literal `__all__`) | W-1, FR-17, FR-18 | P1 |
| 2 | MODIFY | `vidbyte/lib/enums/__init__.py` | enum exports | Import and export the 6 new enums: in the native import block (lines 111–126) and in the sorted `__all__` (lines 172–290). #1095 changed this file after r1 (`vidbyte/__init__.py`, this file and `contracts/sdk-public-api.json`), so re-read it before editing | AGENTS.md "every public enum is added to the export list in `vidbyte/lib/enums/__init__.py`"; S015 | W-1 | P1 |
| 3 | MODIFY | `vidbyte/lib/enums/failure.py` | enum | Append `GROK_COMMAND_NOT_RUN = "grok.command_not_run"`, `OPENCODE_COMMAND_NOT_RUN = "opencode.command_not_run"`, `MUSE_COMMAND_NOT_RUN = "muse.command_not_run"` and `GROK_STORE_UNREADABLE = "grok.store_unreadable"` after `MUSE_WSL_UNAVAILABLE` (INV-22) | AGENTS.md Placement Rules; `tests/test_session_failures.py` (every value contains "."); INV-22 | W-1, FR-17 | P1 |
| 4 | MODIFY | `vidbyte/lib/constants/native_threads.py` | constants | Add, by group, every new value used by name: the §9.3 limits and caps; the patterns `NATIVE_COMMAND_PATTERN`, `GROK_BRANCH_PATTERN`, `GROK_PR_PATTERN` and `NATIVE_BACKSLASH_RUN_PATTERN`; subcommand words (`GROK_EXPORT_COMMAND`, `GROK_SESSIONS_COMMAND`, `GROK_DELETE_COMMAND`, `OPENCODE_SESSION_COMMAND`, `OPENCODE_LIST_COMMAND`, `OPENCODE_DELETE_COMMAND`, `OPENCODE_EXPORT_COMMAND`, `OPENCODE_REVIEW_COMMAND`, `OPENCODE_INIT_COMMAND`, `OPENCODE_PLAN_AGENT`, `MUSE_EXPORT_COMMAND`, `MUSE_INIT_COMMAND`); `GROK_STREAMING_OUTPUT_FORMAT = "streaming-json"`; `GROK_WORKFLOWS_OFF = "0"`; the store names (`GROK_SESSIONS_DIR`, `GROK_SUMMARY_FILE`, `GROK_CWD_FILE`, `GROK_USER_HOME_PARTS`); every JSON member name of §9.1/§9.2; `GROK_SESSION_NOT_FOUND_TEXT = "Session '{thread_id}' not found."`; `OPENCODE_COMMAND_NOT_FOUND_TEXT = 'Command not found: "{command}"'` (a prefix; opencode appends "Available commands: …"); `OPENCODE_DB_COMMAND = "db"`, `OPENCODE_SESSION_QUERY` and its column names (`time_created`, `time_updated`, `parent_id`), `NATIVE_OPENCODE_SCAN_MAX`, `OPENCODE_SCAN_CAP_DETAIL`; `GROK_TEXT_OPTION_FLAGS: MappingProxyType[GrokCommand, tuple[GrokCommandFlag, ...]]`; `GROK_THREAD_MAY_NOT_EXIST_DETAIL`; `MUSE_METHOD_NOT_FOUND_CODE = -32601`; the tool names (`GROK_UPDATE_GOAL_TOOL`, `GROK_READ_FILE_TOOL`, `GROK_IMAGE_TOOLS`, `GROK_IMAGE_TO_VIDEO_TOOL`, `MUSE_READ_SKILL_TOOL`, `MUSE_CREATE_GOAL_TOOL`, `MUSE_TOOL_CALL_KIND`); `GROK_CODE_REVIEW_FRAGMENT`, `GROK_GOAL_RESERVED_WORDS`, `GROK_SUMMARY_GRACE_SECONDS` and `GROK_PR_MAX_NUMBER` (§9.3); the evidence tables `GROK_EVIDENCE_TOOLS: MappingProxyType[GrokCommand, tuple[str, ...]]` and `GROK_EVIDENCE_FRAGMENTS: MappingProxyType[GrokCommand, str]` (§9.2); the templates `GROK_SLASH_TEMPLATE`, `GROK_COMMAND_PART_SEPARATOR`, `MUSE_SKILL_PROMPT_TEMPLATE`, `MUSE_GOAL_PROMPT_TEMPLATE`; the export file parts `MUSE_EXPORT_PARTS = ("export", "thread.json")`; the operation tables `NATIVE_HELPER_OPERATIONS`, `NATIVE_THREAD_ID_OPERATIONS`, `NATIVE_SINCE_REQUIRED_OPERATIONS`, `NATIVE_SINCE_OPTIONAL_OPERATIONS`, `NATIVE_LIMIT_OPERATIONS`, `NATIVE_QUERY_OPERATIONS`, `NATIVE_TEXT_ARGUMENTS` (operation → public text parameter name) and `NATIVE_COMMAND_ARGUMENTS`; detail templates (store path unreadable, summary unusable member, summary oversize, store layout mismatch (D-31), delete left the folder, evidence missing (tools seen), transcript fragment missing (D-28), agent mismatch, session id mismatch (D-29), history unavailable (`noneReason`), lineage cycle, lineage depth, method not found, export file missing, slash-option token refused, reserved goal word refused, design doc with whitespace (D-30)). Table rows: `NATIVE_THREAD_SUMMARIES` and `NATIVE_THREAD_OBSERVATIONS` for the 2 new problems; the 4 `NATIVE_THREAD_FAILURE_CODES` rows; 4 likely-cause and 4 next-step texts (content in §12.4). Widen the `THREAD_NOT_FOUND` observation and the 3 `*_THREAD_NOT_FOUND` likely-cause and next-step texts to cover a helper's unknown id. Also widen the likely-cause and next-step texts of `GROK_/OPENCODE_/MUSE_TIMED_OUT` and `*_OUTPUT_TOO_LARGE` (`native_threads.py:390-445`; review R-18), and of `OPENCODE_PROTOCOL_MISMATCH` (scan cap), per §12.4. Texts stay unique per harness. Update the header | INV-15; A007; AGENTS.md principle 5; NFR-6 (≤ 900 lines; it is 452 today); header rule 2 (no credential word followed by ":"/"=") | W-1, FR-17, D-12 | P1 |
| 5 | MODIFY | `vidbyte/lib/dataclasses/validation.py` | lib helper | Add `RecordFieldConverter.to_utc_datetime(value: object, field_name: str) -> datetime`. It takes an aware `datetime`, or a `str` parsed with `datetime.fromisoformat`. It refuses naive values, other types and parse failures with `ConfigurationError(details={"field": field_name})`, and returns `astimezone(UTC)`. Update the header inventory | AGENTS.md principle 5 (canonical lib helper); A001; strict-config-dataclasses.md | W-1, D-13, FR-4 | P1 |
| 6 | MODIFY | `vidbyte/lib/dataclasses/native_threads.py` | dataclass | Add `NativeThreadSummary`, `NativeHelperRequest`, `NativeToolCall`, `NativeCommandOutput`, `GrokCommandArguments` (with `named`, `text_field` and `skill_names`, rules 9 and 10) and `GrokThreadFile` (`search_text` a tuple) with the §9.1 rules (frozen, slots, `__post_init__`). Every int and bool check calls `RecordFieldValidator.require_int` / `require_bool`, never an inline `isinstance(x, bool)` guard (C002). Add `NativeThreadRequest.command` (last field, default `None`) with its rules. Extend `__all__`. Update the header (PURPOSE, ROLE, FUNCTION INVENTORY, KNOWN EDGE CASES) | AGENTS.md principle 4 and "Dataclasses go in `vidbyte/lib/dataclasses/`"; C006 (bool/NaN in numeric guards); C002 (blocking, baseline 9: no inline bool guard on `limit`, `concurrency`, `pr` and so on); S060/S039 (no `dict[str, Any]`, no TypedDict); C012 (no model field on a `*Config`; `NativeThreadSummary` is not a config owner); A001; NFR-6 (≤ 600 lines; 228 today) | W-1, FR-4, D-1, D-25 | P1 |
| 7 | MODIFY | `vidbyte/lib/errors/base.py` | error class | `NativeThreadError.expected = f"{operation.value} finishing with its documented result"` (D-20); nothing else | A003 (`DIAGNOSTIC_FIELDS` kept); D-20 | W-1 | P1 |
| 8 | MODIFY | `vidbyte/harnesses/native/hostkit/errors.py` | service | Widen the type of `request` in `failure`, `from_configuration_error` and `from_unexpected`, and of `from_launch_failure(..., request=...)`, to `NativeThreadRequest \| NativeHelperRequest` (they read only `.workspace` and `.thread_id`; `wrong_thread` stays `NativeThreadRequest`). Header: RELATED and TESTS lines | D-1; INV-26; A001 | W-2 | P2 |
| 9 | MODIFY | `vidbyte/harnesses/native/hostkit/launcher.py` | service | Widen `NativeLauncher.resolve(..., request: NativeThreadRequest \| NativeHelperRequest)` | D-1; INV-26 | W-2 | P2 |
| 10 | MODIFY | `vidbyte/harnesses/native/muse/launcher.py` | service | Widen `MuseLauncher.resolve(request)` and `launch_failure(outcome, request, *, thread_id)` to `NativeThreadRequest \| NativeHelperRequest` | D-1; INV-26 | W-2 | P2 |
| 11 | CREATE | `vidbyte/harnesses/native/grok/store.py` | service | `GrokHome`: `private` (the sha16 key code moved from `_prepare_home`), `user`, `of`, `prepare` (moved `_prepare_home`, same errors), `fallback` (moved `_fallback`), `environment(home, api_key)` (moved `_environment`; key variables only when `api_key` is not `None`). `GrokStore.threads(home, request, errors)` (sync; list and search): groups are directories only, session candidates are directories only, and files at both levels are ignored (EC-66); groups per scope (SDK = every group; USER = decoded name or `.cwd` match); capped reads; parsing through `GrokHelperWire.thread_file`; the skip rules of EC-11 and EC-12 with the layout bound of EC-67 (folder `st_mtime` against `GROK_SUMMARY_GRACE_SECONDS`); `OSError` → `store_unreadable`. `GrokStore.thread(home, request, errors, *, thread_id)` (sync; D-27): the same groups, then only `<group>/<id>/summary.json`; it returns `None` when no group has it; used by get, read, delete, lineage and the plan and explore agent lookup. Given a `NativeThreadRequest` (which has no scope), it reads SDK scope: every group of the run's private home (R-21). `__all__ = ["GrokHome", "GrokStore"]` | AGENTS.md principles 1–3 and 5; INV-15; S061 (use `path.open("rb")` / `path.iterdir()`, never builtin `open(var)` or `read_bytes(var)`); A007 (`os.fstat` cap); comment-format.md; A001 header incl. WHAT NOT TO DO ("never create a home on a read path") | W-2, W-4, D-2, D-10, D-11, D-21 | P2 (GrokHome) / P4 (GrokStore) |
| 12 | MODIFY | `vidbyte/harnesses/native/grok/threads.py` | service | `GrokThreadRun.execute` calls `GrokHome.fallback()`, `GrokHome.prepare(...)` and `GrokHome.environment(home, request.api_key)`. Remove `_fallback`, `_prepare_home` and `_environment` from this class. Argv and behavior are unchanged. Update the header inventory and remove the now-unused imports | INV-26; review-scope.md; D-10; A001 | W-2 | P2 |
| 13 | MODIFY | `vidbyte/harnesses/native/grok/wire.py` | codec | Add `GrokStreamWire` (`read` with the minted `thread_id`, `tool_calls`, private `_events`) per §9.2. Add `GrokHelperWire` (`thread_file`, `document`, `deleted`). `GrokWire` is unchanged. Update `__all__` and the header | AGENTS.md principle 5 (reuse `CliRunner.json_objects`); semgrep `no-untyped-mapping-fallback` (raise on a non-mapping, never return a default); INV-6; NFR-6 | W-4, W-7 | P3 |
| 14 | CREATE | `vidbyte/harnesses/native/grok/helpers.py` | service | `GrokThreadHelpers`: the 8 public static async helpers (§8.5) and the generic `_call(operation, flow, *, workspace, thread_id=None, since=None, limit=None, query=None, scope, config=None)`, a guarded try that builds the `NativeHelperRequest` and the `GrokThreadConfig` (`require_instance` on `config`). `GrokHelperRun`: narrated flows `list`, `get`, `read`, `lineage`, `search` and `delete`, plus the shared static `export(home, request, config, errors, *, thread_id)` (the keyless `grok export` child, also called by `GrokCommandRun` for code-review evidence). `export` and `delete` each build their `CliInvocation` inline from `GrokHome.environment(home, None)` and the key-variable `env_remove` tuple; `export` calls no other `GrokHelperRun` method, so `read → export` stays one level deep (review R-22). Store reads run in `to_thread`: `GrokStore.threads` for list and search, `GrokStore.thread` for the rest. **No flow calls a sibling flow** (review R-1): `read` calls `GrokStore.thread`, then `export`; `lineage` loops `GrokStore.thread` with `NativeThreadListing.check_step` and never calls `get`. `__all__ = ["GrokHelperRun", "GrokThreadHelpers"]` | AGENTS.md principles 1–2; class-bound-helpers.md; INV-3, INV-4, INV-11, INV-15, INV-18; A007 (defaults named); S052; A002 (`# @intent` on the scope-home and no-create rules); A001 | W-4, FR-1, FR-5 to FR-11 | P4 |
| 15 | CREATE | `vidbyte/harnesses/native/grok/commands.py` | service | `GrokCommands`: `run_grok_command` plus the 13 named wrappers (each one `return await GrokCommands._call(...)`), and `_call(operation, *, arguments fields…, text, api_key, workspace, model, skills, config)`, which validates the text under `NATIVE_TEXT_ARGUMENTS[operation]` and then builds `GrokCommandArguments(named=<operation is not RUN_GROK_COMMAND>, text_field=<public name>, skill_names=tuple(path.name for path in request.skills))` and `NativeThreadRequest(verb=RUN, prompt=<line>)`. `GrokCommandRun.execute` (narrated): launcher, `GrokHome.prepare`, `register_secret`, mint the session id (`uuid.uuid4()`, D-29), argv (`--output-format=streaming-json`, `--session-id=<id>`, `--cwd`, `--permission-mode`, `--model`, `--reasoning-effort`, `--agent`, `--single=<line>`, JOINED), environment (`GrokHome.environment` + `GROK_WORKFLOWS=0` for GOAL), run, launch failure, `GrokStreamWire.read(..., thread_id=<id>)`, evidence: `NativeCommandEvidence.require` for tools, `require_value` with `GrokStore.thread(...).agent_name` for agents, or `require_text` over `GrokHelperRun.export(...)` for `CODE_REVIEW`. Docstrings name `permission_mode=ACCEPT_EDITS` for editing commands, and the external effects of `auto_pr` and `pr` (T-7). `__all__ = ["GrokCommandRun", "GrokCommands"]` | AGENTS.md principles 1–2; NFR-9 (≤ 5-line wrappers); INV-8, INV-9, INV-24; A002 `# @intent` (evidence fails closed; workflows off for goal); A007; A001 | W-7, FR-12, FR-15, FR-19 | P5 |
| 16 | MODIFY | `vidbyte/harnesses/native/grok/__init__.py` | package init | Bind the 22 new names (`name = GrokThreadHelpers.name` / `GrokCommands.name`), and make the literal sorted `__all__` hold all 25. Header FUNCTION INVENTORY | INV-1; S015; INV-15 | W-10 | P4/P5 |
| 17 | MODIFY | `vidbyte/lib/dataclasses/process.py` | — | **No change** (listed to rule it out: `CliInvocation` already has `env_remove` and `stdin_text`) | none found — checked `process.py:CliInvocation` | — | — |
| 18 | MODIFY | `vidbyte/harnesses/native/opencode/threads.py` | service | `OpencodeThreadRun._argv` appends `CliOption(OpencodeFlag.COMMAND, request.command)` when it is set. `execute` passes `stdin_text=None` when `request.prompt == ""`. Header | INV-26 (no change when `command is None`); D-8; A001 | W-8 | P5 |
| 19 | MODIFY | `vidbyte/harnesses/native/opencode/wire.py` | codec | `OpencodeWire.read`: before the generic run_failed checks, when `request.command` is set and `OPENCODE_COMMAND_NOT_FOUND_TEXT.format(command=request.command)` appears in an error event or in stderr, raise `COMMAND_NOT_RUN` (thread id = session if known). The text is a prefix match in the error event's `error.data.message`, as `_error` already reads it, or in stderr (review R-17). Add `OpencodeHelperWire` (`sessions`, `rows` for `opencode db` rows, `document`, `deleted`). The epoch-ms → UTC conversion is one private converter: `RecordFieldValidator.require_int` (which refuses bool), then `datetime.fromtimestamp(ms / OPENCODE_MILLISECONDS_PER_SECOND, UTC)` (C002). Update `__all__` and the header | INV-6; semgrep `no-untyped-mapping-fallback`; AGENTS.md principle 5; A007 | W-5, W-8 | P3 |
| 20 | CREATE | `vidbyte/harnesses/native/opencode/helpers.py` | service | `OpencodeThreadHelpers`: the 8 public helpers and a generic `_call`. `OpencodeHelperRun`: narrated flows with one private `_child(request, config, errors, *, command, operands)` that builds `CliInvocation(argv=CliArgv.build(launcher, command=…, options=…, style=JOINED, operands=…), env_overlay={OPENCODE_DISABLE_AUTOUPDATE: "1", PWD: ws}, timeout_seconds=NATIVE_CONTROL_TIMEOUT_SECONDS, max_output_bytes=NATIVE_PROCESS_MAX_OUTPUT_BYTES, cwd=ws)` and runs it. Lists call `_child` once for `session list --max-count=NATIVE_OPENCODE_SCAN_MAX`, then `OpencodeHelperWire.sessions`. `get` calls `_child` once for `opencode db --format=json <OPENCODE_SESSION_QUERY>`, then `OpencodeHelperWire.rows`. `lineage` loops `_child` + `rows` per step, following `parent_id` with `NativeThreadListing.check_step` (D-26). `read` calls `_child` for `export`. **No flow calls a sibling flow** (review R-1). `__all__` | AGENTS.md principles 1–2; INV-2, INV-9, INV-16; D-19, D-22; A007; A001 | W-5, FR-2 | P4 |
| 21 | CREATE | `vidbyte/harnesses/native/opencode/commands.py` | service | `OpencodeCommands`: `run_opencode_command`, `run_opencode_review`, `run_opencode_init` and `run_opencode_plan`, plus `_call` (validates the text under its public name, builds `NativeThreadRequest(harness=OPENCODE, verb=RUN, prompt=text, command=…)`, and resolves the plan config per §9.2), then `OpencodeThreadRun.execute`. `__all__ = ["OpencodeCommands"]` | NFR-9; INV-25; FR-19; A001 | W-8, FR-13 | P5 |
| 22 | MODIFY | `vidbyte/harnesses/native/opencode/__init__.py` | package init | Bind 12 new names; the `__all__` holds 15 | INV-1; S015 | W-10 | P4/P5 |
| 23 | CREATE | `vidbyte/harnesses/native/muse/children.py` | service | `MuseChildren`: `open_config` (moved shielded preparation: `_prepare_config` + `_discard`), `close_config` (moved `finally` removal), `overlay` (moved `_overlay`), `serve(prefix, frames, launcher, overlay, mark, cwd)` (moved `_serve_invocation` minus frame building) and `run` (moved `_run`). Same texts, same codes. `__all__ = ["MuseChildren"]` | D-10; INV-14, INV-23, INV-26; A002 (keep the moved `# @intent` blocks verbatim); A001 | W-2 | P2 |
| 24 | MODIFY | `vidbyte/harnesses/native/muse/threads.py` | service | `MuseThreadRun.execute` calls `MuseChildren.*`, building the serve frames with `MuseWire.batch_frames` as today. Remove the moved methods. Behavior is identical. Header | INV-26; review-scope.md | W-2 | P2 |
| 25 | MODIFY | `vidbyte/harnesses/native/muse/wire.py` | codec | Add `MuseSessionWire` (`list_params`, `read_items_params`, `result` (timeout / cap / no answer / `-32020` → thread_not_found / `-32601` → protocol_mismatch / other error → run_failed), `sessions`, `session`, `tool_calls` (items from `history.items` in mode `inline`, or `history.snapshot.state.items` in `snapshot`; `None` in `anchoredSnapshot`, whose items start at a compaction boundary (D-33); mode `none` raises `COMMAND_NOT_RUN` naming `noneReason`)). `MuseWire.read_answer` is unchanged. `__all__` and header | INV-6; semgrep rule; `msp.schema.json` shapes (A-16); NFR-6 | W-6, W-9 | P3 |
| 26 | CREATE | `vidbyte/harnesses/native/muse/helpers.py` | service | `MuseThreadHelpers`: the 6 public helpers plus `init_muse_workspace` (moved here from row 27 because it is keyless and takes a `NativeHelperRequest`, so `MuseCommands` keeps exactly one guarded `_call`; review R-12), and one `_call`. `MuseHelperRun`: narrated flows (`list`, `get`, `lineage`, `read`, `init`, `tool_calls`), each opening one private config folder per call and closing it in `finally`. A step that two flows share (one `session/read` serve) is a private helper that calls only `MuseChildren` and `MuseSessionWire`. `lineage` loops that helper with `check_step` and never calls `get` (review R-1). A `transcript` flow (D-33) runs the export child for Muse evidence; `read` and `transcript` share the private `_export` helper, which calls only `MuseChildren` and the stdlib. `read` builds the export invocation and reads the file in `to_thread` with the `os.fstat` cap. `init` returns `NativeCommandOutput`. `__all__` | INV-2, INV-4, INV-14, INV-18, INV-23; D-17; S061; A007; A001 | W-6, FR-3 | P4 |
| 27 | CREATE | `vidbyte/harnesses/native/muse/commands.py` | service | `MuseCommands`: `run_muse_skill`, `run_muse_goal`, `run_muse_plan`, `run_muse_import`, `run_muse_scaffold` and `run_muse_browser_app`, with one guarded `_call` (`init_muse_workspace` is in row 26). `MuseCommandRun.execute`: `dataclasses.replace` with the template prompt, then `MuseThreadRun.execute`, then `MuseHelperRun.tool_calls(...)` with the new thread id, then `NativeCommandEvidence.require`. When `tool_calls` returns `None` (`anchoredSnapshot`), it runs `MuseHelperRun.transcript(...)` and calls `NativeCommandEvidence.require_text` for the tool name and, for skills, the skill id (D-33). `__all__` | NFR-9; INV-8, INV-24, INV-25; A002 (`# @intent` muse-exec-does-not-expand-slash-commands); A001 | W-9, FR-14 | P5 |
| 28 | MODIFY | `vidbyte/harnesses/native/muse/__init__.py` | package init | Bind 13 new names (7 from `MuseThreadHelpers`, 6 from `MuseCommands`); the `__all__` holds 16 | INV-1; S015 | W-10 | P4/P5 |
| 29 | CREATE | `vidbyte/harnesses/native/hostkit/listing.py` | service | `NativeThreadListing.cutoff`, `newest` (dedupe keeping the newer entry, window, sort key `(updated_at, thread_id)` descending, cut at `limit`), `matches` (casefold substring over non-null texts), `check_step` (raises protocol_mismatch on a repeated id or a depth over `NATIVE_LINEAGE_MAX_DEPTH`). `__all__` | AGENTS.md principle 5 (shared by 3 harnesses); INV-7, INV-10; hostkit header "Plumbing that a second harness needs goes here"; A001 | W-3 | P3 |
| 30 | CREATE | `vidbyte/harnesses/native/hostkit/evidence.py` | service | `NativeCommandEvidence.require`, `require_value` and `require_text` (§8.5). The match uses `NATIVE_BACKSLASH_RUN_PATTERN` normalization. The raise is `errors.failure(NativeThreadProblem.COMMAND_NOT_RUN, request=…, thread_id=…, searched=<detail with the tools seen>)`. `__all__` | INV-8; A002 `# @intent evidence-fails-closed`; A001 | W-3 | P3 |
| 31 | MODIFY | `vidbyte/harnesses/native/hostkit/__init__.py` | package init | Export `NativeThreadListing` and `NativeCommandEvidence`, and update the header | S015; hostkit header rule | W-3 | P3 |
| 32 | MODIFY | `vidbyte/harnesses/native/__init__.py` | package init | Re-export the 47 functions plus `NativeThreadSummary`, `NativeCommandOutput`, `GrokThreadScope` and `GrokCommand`; the literal sorted `__all__` has 68 names; header PURPOSE and FUNCTION INVENTORY | INV-1; S015; NG-11 (no root export); C016 (root `__all__` untouched) | W-10, FR-18 | P4/P5 |
| 33 | MODIFY | `vidbyte/harnesses/README.md` | doc | Extend the `native/` bullet (or add a sub-bullet): the helpers, the scopes, the skill functions and the evidence rule, `command_not_run`, the excluded rows in one sentence, and "pass `permission_mode=ACCEPT_EDITS` for editing Grok commands". Replace the EC-44 sentence ("SDK Grok runs read nothing from `~/.grok` …") with the verified limitation (EC-63), and restate T-6 for the helpers. Add one sentence: subagent child threads (Grok, Muse) list as ordinary threads (EC-72); and one: `run_grok_imagine_video` needs video tools on (`features.video_gen`, EC-74). Also: "opencode lineage shows subagent nesting only; a thread made by `fork_opencode_thread` is its own root" (EC-76). And: a same-named skill or command in the workspace, in `~/.claude` or `~/.grok`, or in `skills=` replaces Grok's bundled one, and the call then fails with `command_not_run` (EC-78) | A009 (≤ 40,000 characters); AGENTS.md "Each folder's own README.md documents that folder"; FR-20 | W-11 | P6 |
| 34 | MODIFY | `REPO_MAP.md` | doc | `vidbyte/harnesses/native/` entry: it now also lists, gets, reads, traces lineage, searches and deletes threads, and runs built-in commands and skills with verification. Keep "no host objects, model-facing tools or servers" | AGENTS.md "Repository Map … regenerate a wrong entry"; FR-20 | W-11 | P6 |
| 35 | MODIFY (S2) | `tests/features/harness_threads/test_harness_threads_surface.py` | test | **S2 only.** Update `EXPECTED_EXPORTS` (68), the subpackage export expectations (25/15/16), `EXPECTED_ENUMS` (§9.1 order), `NEW_FAILURE_CODES` (32) and `CONTRACT_CONSTANTS` as S2 decides. Rewrite the stale `len(main_members) == 120` (line 193) and the stale total `len(members) == len(main_members) + len(NEW_FAILURE_CODES)` (line 195: 152 ≠ 148 + 32), for example as `len(members) == len(main_members) + 4` for this PR's appended codes, so neither hardcodes a main count that #1036 itself invalidated (gate-forced: `run_ci.py` runs every test, and this PR appends codes) | §13; INV-22; gate (`scripts/run_ci.py` runs `pytest` over `tests/`) | W-12, AC-20 | S2 |
| 36 | MODIFY (S2) | `tests/features/harness_threads/test_harness_threads_errors.py` | test | **S2 only.** `test_every_code_has_its_own_likely_cause_and_next_step` key set: 32 codes + 2 | §13; FR-17 | W-12 | S2 |
| 37 | MODIFY (S2) | `tests/features/harness_threads/fake_harness.py` (and, if needed to stay < 1,000 lines, one new sibling fake module) | fixture | **S2 only.** Stand-in paths: grok `export` (a transcript that can include `GROK_CODE_REVIEW_FRAGMENT`), `sessions delete`, `--session-id` (the session takes that id), `--output-format=streaming-json` events (`image_to_video` among the tools) and a real-layout store that also holds `sessions/session_search.sqlite`, `<group>/permission.toml` and `<group>/.cwd` (EC-66); opencode `session list` (roots only, rows exactly `{id, title, updated, created, projectId, directory}` with no `parentID`, honouring `--max-count` with a default of 100), `db [query] --format json` (answer the query against a SQLite file with opencode's `session` columns, for example through the stdlib `sqlite3`), `export`, `session delete`, and `--command` (an unknown name prints exactly `Command not found: "<name>". Available commands: …` as an error event and exits 1); muse serve `session/list` and `session/read` with `excludeItems: false`, including history mode `anchoredSnapshot` (with `forkedFrom` as an object `{sessionId, …}` per MSP, not the string that today's fork reply returns at line 562), `export --out`, `init` | §13; AGENTS.md principle 3 (< 1,000 lines; 683 today) | W-12 | S2 |
| 38 | MODIFY / CREATE (S2) | `tests/features/harness_threads/{conftest.py, FEATURE.md, README.md, test_harness_threads_static_policy.py, new test files}` | test / doc | **S2 only.** Fixtures for helper calls and errors (the existing `check_error` derives `f"{verb}_{harness}_thread"`); FEATURE.md Test Suite Map and Invariants; README `## File Index` for every new file; optionally add the new modules to `NAMED_MODULES` (the `rglob` already polices them) | S020 (File Index matches tracked files); feature test pack practice | W-12 | S2 |

New source files in §12.3: rows 11, 14, 15, 20, 21, 23, 26, 27, 29 and 30, which is **10** and matches §8.4. Row 17 is a recorded no-op.

### 12.4 Standards checklist for this change

- [ ] Every new module opens with the house A001 header: `FILE:`, `PURPOSE:`, `ROLE IN CODEBASE:`, `ARCHITECTURE NOTE:`, `FUNCTION INVENTORY:`, `COMMON MODIFICATION PATTERNS:`, `WHAT NOT TO DO IN THIS FILE:`, `KNOWN EDGE CASES:`, `RELATED DOCS:` and `TESTS:`, within the first 80 lines. Every modified module's header is updated to match its new contents — *source:* lint A001 (`lint/rules/a001_agent_readable_file_headers.py`), the existing headers in `native/`.
- [ ] Every module under `vidbyte/harnesses/native/` holds only a docstring, imports, classes, a literal `__all__` and `name = Class.attr` bindings, and uses no literal except `""`, `0` and `1`. Templates are constants filled with `.format`, with no f-strings that have literal parts — *source:* #1036 INV-15, `test_harness_threads_static_policy.py`.
- [ ] Every new dataclass is in `vidbyte/lib/dataclasses/native_threads.py`, is `@dataclass(frozen=True, slots=True)`, validates in `__post_init__`, and raises `ConfigurationError` with `details={"field": <public name>}` — *source:* AGENTS.md principle 4 and Placement Rules; strict-config-dataclasses.md.
- [ ] Every new enum is in `vidbyte/lib/enums/native_threads.py` and exported from `vidbyte/lib/enums/__init__.py`; every closed set (scope, command, agent, event type, command flag, Muse skill id) is an enum, not a `str` — *source:* AGENTS.md "Enums go in `vidbyte/lib/enums/`".
- [ ] Every number and text is a named constant in `vidbyte/lib/constants/native_threads.py`; numeric parameter defaults (`limit=`) are named constants — *source:* lint A007; INV-15.
- [ ] Every public class has exactly one guarded `_call` with the #1036 except-order; every flow has a narrated `execute` or flow method, with ≤ 72-column comment blocks directly above the lines they explain — *source:* AGENTS.md principles 1–2; comment-format.md; `grok/threads.py:GrokThreads._call`.
- [ ] Call chains stay one level deep inside a class: a flow method calls its own helpers, and those helpers call only other classes, lower layers or the stdlib; no nested `def` — *source:* AGENTS.md principle 1 (#1036 review R-3 was a Blocker for this).
- [ ] No flow calls a sibling flow that calls a private helper. `lineage` never calls `get`, and `read` never calls `get`. A step that two flows share is a private helper that calls only other classes, lower layers or the stdlib — *source:* AGENTS.md principle 1; this spec's review R-1.
- [ ] Domain rules carry a `# @intent <name>` block within 20 lines of their `def`. That covers: read paths never create a Grok home; SDK scope equals the run home; evidence fails closed; `GROK_WORKFLOWS=0` only for goal; Muse exec does not expand slash commands; export runs in an empty temp cwd; `PWD` is overlaid; helper children carry no key — *source:* lint A002.
- [ ] No blocking call inside `async def`: file scans, reads, `mkdtemp`, `exists` and removals go through `asyncio.to_thread` — *source:* lint S052; INV-18.
- [ ] File reads use `path.open("rb")` with `os.fstat(handle.fileno()).st_size` checked against the cap, then `handle.read(CAP)`. Never builtin `open(variable)`, `read_bytes(variable)`, or `read(CAP + 1)` — *source:* lint S061, A007; blocking-lint-invariants.md.
- [ ] Vendor parsers raise on a non-mapping or a wrong type; they never `return <default>` when an `isinstance(x, Mapping)` check fails — *source:* `.semgrep/typed-mapping-boundary-policy.yml` rule `no-untyped-mapping-fallback` (zero tolerance; static-policy.yml).
- [ ] No lib record field is typed `dict[str, Any]` / `Mapping[str, Any]` or is a `TypedDict` — *source:* lint S060, S039.
- [ ] No method is named `request` — *source:* lint S012.
- [ ] Every int guard refuses `bool`, and every float guard refuses NaN and ±inf — *source:* lint C006.
- [ ] Every int and bool check goes through `RecordFieldValidator.require_int` / `require_bool`, never an inline `isinstance(x, bool)` guard. `python lint/run.py --rule C002` stays at its baseline of 9 — *source:* lint C002 (blocking); `lint/baseline.json:11`; review R-3.
- [ ] `vidbyte/lib/` imports nothing above lib; `hostkit` imports no harness subpackage; the harness subpackages do not import one another — *source:* AGENTS.md principle 3; lint A006; hostkit header.
- [ ] Every `__all__` is a literal list whose names are statically bound and unique — *source:* lint S015.
- [ ] No name is added to the root `vidbyte.__all__` or to `vidbyte.harnesses.__all__` — *source:* lint C016; #1036 NG-10.
- [ ] Each file stays < 1,000 lines (new modules ≤ 600; the constants file ≤ 900); import order passes ruff over the whole `vidbyte` tree — *source:* AGENTS.md principle 3; lint S051; NFR-6.
- [ ] Function complexity and nesting: C901, PLR0912 and PLR0915 stay at baseline, with nesting ≤ 3 — *source:* lint S008, S024.
- [ ] New code changes nothing in `lint/baseline.json` and adds no `noqa` or suppression; lint is run after `git add` — *source:* AGENTS.md; vidbyte-gates; local-ci-verification.md.
- [ ] Error texts. Each new code has a likely cause and a next step that are complete sentences, unique within the harness, end with ".", and contain no credential word followed by ":" or "=":
  - **`grok.command_not_run`:** the cause names three possibilities:
    - grok ran the prompt as ordinary text, because `-p` did not expand the slash command or the `--agent`;
    - a same-named skill or command replaced the bundled one, from the workspace (`.grok`, `.claude`, `.agents`, `.cursor`), from `~/.claude` or `~/.grok`, or from `skills=` (review R-20);
    - the skill left no trace (for `/imagine-video`, video tools may be off: `features.video_gen`).
    - The next step adds: run `grok inspect --json` and look for `collidesWith`. The next step says to read the thread with `read_grok_thread(error.thread_id, workspace)` and check the Grok release (tested 1.0.52), or to run the command in the Grok TUI.
  - **`opencode.command_not_run`:** the cause says opencode has no command of that name in this workspace or the user config. The next step says to pass an existing command name.
  - **`muse.command_not_run`:** the cause says `muse exec` sends slash commands as text and the model did not call `read_skill` or `create_goal`, or the history could not be read back, or the run compacted and its transcript lacks the call (D-33). The next step says to read the thread with `read_muse_thread` and name the skill in the prompt.
  - **Widened `TIMED_OUT` / `OUTPUT_TOO_LARGE` texts** (review R-18; one cause and one next step per code, unique per harness):
    - The timeout cause names both bounds: `timeout_seconds` for runs, and the fixed `NATIVE_CONTROL_TIMEOUT_SECONDS` for helper children, which `config` does not change. The timeout next step says to raise `timeout_seconds` only for a run; for a helper it says to retry, or to run the vendor CLI's own `export` / `session list` directly.
    - The output cause names the transcript case: a transcript over `NATIVE_PROCESS_MAX_OUTPUT_BYTES` cannot be returned whole. The Grok cause names both caps (`GROK_CLI_MAX_OUTPUT_BYTES` for `run_/continue_/fork_grok_thread`; `NATIVE_PROCESS_MAX_OUTPUT_BYTES` for command runs and `grok export`). The output next step says to export the transcript with the vendor CLI for a read, and to ask for a shorter answer for a run.
    - `OPENCODE_PROTOCOL_MISMATCH` adds the scan cap: the project has `NATIVE_OPENCODE_SCAN_MAX` or more root sessions; narrow with `list_opencode_threads_since` or archive old sessions.
  - **`grok.store_unreadable`:** the cause names the unreadable folder or file under the home. The next step says to fix its permissions, or to set HOME / USERPROFILE.
  - *source:* KD-9; constants header "KNOWN EDGE CASES"; `test_harness_threads_errors.py`.
- [ ] Helpers have no `api_key` parameter; helper children list the key variables in `env_remove` — *source:* INV-2; T-3.
- [ ] READMEs: the `vidbyte/harnesses/README.md` native bullet is updated in the same PR, and the README stays ≤ 40,000 characters — *source:* AGENTS.md "Each folder's own README.md …"; lint A009.

### 12.5 Non-code actions

- Update the native bullet: add the helper and skill functions, the scopes, the evidence rule and the exclusions, and replace the EC-44 sentence — `vidbyte/harnesses/README.md` — *source:* AGENTS.md (folder README documents the folder); FR-20.
- Update the `vidbyte/harnesses/native/` entry — `REPO_MAP.md` — *source:* AGENTS.md "Repository Map".
- Add exports to `__init__` files: the native package, grok, opencode, muse and hostkit (rows 16, 22, 28, 31, 32), and `vidbyte/lib/enums/__init__.py` (row 2) — *source:* AGENTS.md Placement Rules; INV-1.
- Test pack docs (S2): the `tests/features/harness_threads/FEATURE.md` Test Suite Map and Invariants, and the `README.md` File Index — *source:* lint S020; feature test pack practice.
- PR body (S6): a manual QA section that the user runs in their own shell with their own key (`! python probe.py`, written in the PR body, **not** committed as a repo file). It checks:
  - (a) the SDK's own path, not a bare `grok` in the user's shell (review R-8):
    - the script calls `run_grok_goal`, `run_grok_implement`, `run_grok_imagine`, `run_grok_imagine_video` and `run_grok_code_review` itself;
    - for each, it prints `thread_id`, the distinct tool names in the stream, and `error.failure_code` on failure;
    - these run under the private `GROK_HOME`, with `GROK_WORKFLOWS=0` for goal, `--single=` and `--output-format=streaming-json`;
    - **negative control:** the script runs the same argv and environment with the goal text *without* the leading `/`, and confirms that no `update_goal` call appears, which shows the evidence discriminates;
    - **bundled skills:** the script confirms that bundled skills and `shared/personas` resolve under a fresh private `GROK_HOME` (A-26).
  - (b) one real `summary.json` shape (A-1 to A-4);
  - (c) the streaming `tool_call` fields and the evidence markers (A-8, A-9), `image_to_video` with the default `features.video_gen` (A-24), the code-review fragment in the run's `grok export` (A-27), and `--session-id` with `--single` (A-25: `end.sessionId` equals the minted id);
  - (d) `--agent plan` and `agent_name` (A-10);
  - (e) `grok export` / `sessions delete` under a private `GROK_HOME` (A-5, A-6);
  - (f) `opencode session list --format json --max-count 5` (roots-only rows), `opencode db --format json "SELECT id, title, time_created, time_updated, parent_id, directory FROM session WHERE id = '<a subagent child id>'"` (one row with `parent_id`), the export shape, and the unknown `--command` text `Command not found: "<name>"` (A-12 to A-15, A-29);
  - (g) the Muse `session/list`, `session/read {excludeItems:false}` items, `read_skill`, `create_goal` and `export --out` (A-16 to A-19), and, for a long run that compacted, that the export transcript still holds the early `read_skill` call (A-28).
  - *source:* request.md §C ("Live runs are manual QA for the user"); orchestrator briefing.
- No `.env.example`, changelog or `llms.txt` change: there is no new environment variable for users, and #1036 added none of those either. No lint baseline ratchet change.

### 12.6 Phases and dependency order

- **P1 — Lib vocabulary.** Rows 1–7. *Ships:* the new records, enums, codes and constants import cleanly, and every #1036 test still passes except the surface and errors pins that S2 has already updated to the final surface (those stay red until P5).
- **P2 — Shared plumbing refactor.** Rows 8–10, 11 (GrokHome only), 12, 23 and 24. *Ships:* identical #1036 behavior on the new structure. The #1036 tests pass.
- **P3 — Readers and shared helpers.** Rows 13, 19, 25, 29, 30 and 31. *Ships:* the parsers, listing and evidence, each usable in isolation.
- **P4 — Thread helpers.** Rows 11 (GrokStore), 14, 20 and 26, plus the helper exports in rows 16, 22, 28 and 32. *Ships:* all 22 helpers.
- **P5 — Command and skill functions.** Rows 15, 18, 21 and 27, plus the command exports in rows 16, 22, 28 and 32. *Ships:* all 25 command and skill functions; the surface tests go green.
- **P6 — Docs and gate.** Rows 33 and 34, then `python lint/run.py`, both `run_ci.py` stages, and the semgrep scan.

**Dependency order:** P1 → P2 → P3 → (P4, P5) → P6. Inside P3, rows 13, 19 and 25 depend on row 29 only for the lineage step, so they can be written in parallel. P4 and P5 depend on P3. Grok's P5 row 15 also depends on P4 rows 11 (`GrokStore.thread`) and 14 (`GrokHelperRun.export`), and Muse's row 27 on row 26 (`tool_calls`, `transcript`), so those P5 rows start after their P4 rows (review R-21).

**Independent:**
- Within P4, the three harness helper modules (14, 20, 26) are independent of one another, and so are their wires.
- Within P5, rows 15, 21 and 27 are independent, but row 27 depends on row 26 (`MuseHelperRun.tool_calls`).
- Row 18 depends only on row 6 (`NativeThreadRequest.command`).

## §13 Test seams (facts for the test author — no tests here)

- **Framework:** pytest 8.3.5 and pytest-asyncio 1.3.0 (`pyproject.toml:48-49`).
  - Settings: `testpaths=["tests"]`, `addopts=["--strict-config","--strict-markers"]`, `asyncio_default_fixture_loop_scope="function"`. Async tests use `@pytest.mark.asyncio`.
  - CI runs on Linux with Python 3.11 and 3.12; the local machine is win32. Offline only, per `FEATURE.md`: "No real key, network, vendor CLI or WSL distro is used".
- **Layout and naming:** the pack is `tests/features/harness_threads/`. Each file is named `test_harness_threads_<topic>.py`.
  - The `README.md` `## File Index` must list every tracked file (lint S020).
  - `FEATURE.md` (68 lines) has a `## Test Suite Map` (lines 47–62) and an `## Invariants` section citing #1036 INV-1 to INV-23.
  - The existing files run from 114 to 269 lines.
- **Prior art to copy:**
  - `tests/features/harness_threads/test_harness_threads_threads.py`: real child processes through the fake, for continue and fork.
  - `test_harness_threads_credentials.py`: an AC-19 workspace and home snapshot (the "nothing written" pattern).
  - `test_harness_threads_arguments.py`: the `refuse` helper (nothing written when an argument is refused).
  - `test_harness_threads_errors.py`: message order and code tables.
  - `test_harness_threads_wsl.py`: the WSL launcher and reap.
- **Fixtures / factories** (`tests/features/harness_threads/conftest.py`, 414 lines):
  - `lib_api`: lazy imports of the records, enums, constants, `FailureCode` and errors.
  - `api` (line 242): `functions[(harness, verb)] = getattr(native, f"{verb}_{harness}_thread")`. It covers only the 9 #1036 functions.
  - `sandbox` (line 251): it sets `USERPROFILE` and `HOME` to a sandbox home that is a sibling of the workspace, sets `PATH` to `sandbox.bin` only, and sets `tempfile.tempdir`.
  - `call` (line 263): runs one #1036 function against the stand-in through `config.<harness>_command = sandbox.command(...)`.
  - `check_error` (line 296): asserts `error.operation == NativeThreadOperation(f"{verb}_{harness}_thread")` (line 305). It **cannot** derive the new operation names: those are the function names themselves, such as `list_grok_threads` and `run_grok_goal`.
  - Also `fast_stop`, `wait_until`, `alive`, `wsl_ready` and `pack`.
  - `Sandbox` methods: `command(program, **fields)` (line 116) returns `(sys.executable, "-u", fake_harness.py, scenario.json)`; `stand_in(...)` (line 119) builds an `.exe` on win32 with distlib's `t64.exe`, needed for the PATH lookups that the helpers use when `config` is `None`; plus `records`, `starts`, `answers`, `snapshot` and `grok_home` (line 203).
  - `private_home(home, workspace)` (line 62) mirrors the SDK home key.
- **The fake vendor** (`tests/features/harness_threads/fake_harness.py`, 683 lines / 33,740 characters) is a stdlib program run as a real child and driven by a scenario JSON (`program`, `mode`, `serve_mode`, `log_dir`, `state_dir`, …). It logs argv, stdin, and the presence and length of the key variables (never their values). Today:
  - **Fake grok** handles only `--single` runs with `--output-format=json`. A real store also holds non-session files (`sessions/session_search.sqlite`, `<group>/permission*.toml`, `<group>/.cwd`); the real-layout fixture must include them (EC-66). Its sessions are `GROK_HOME/sessions/<sha256(normcase(abspath(cwd)))[:16]>/<id>.json` (lines 306–309). That is **not** the real layout `GROK_HOME/sessions/<url-encoded cwd>/<id>/summary.json`. It has no `export`, no `sessions delete` and no `streaming-json`.
  - **Fake opencode** accepts only `run` (line 359), stores sessions at `state_dir/opencode/<id>` (line 365), and has no `session list`, `db`, `export`, `session delete` or `--command` handling. Model the 1.18.31 facts (review r2):
    - `session list` lists **roots only**, emits **no `parentID`**, and stops at `--max-count` (default 100);
    - `db [query] --format json` prints the query's rows as a JSON array (`[]` when none), with columns `id`, `title`, `time_created`, `time_updated`, `parent_id`, `directory`;
    - forks record no parent, and only subagent children (created with a parent) have `parent_id`;
    - an unknown `--command` emits an `error` event whose `error.data.message` is `Command not found: "<name>". Available commands: …`, then exits 1;
    - an unknown id for `export` / `session delete` prints `Session not found: <id>`.
  - **Fake muse** handles `exec` and `serve` (lines 606–608), with sessions at `state_dir/muse/<id>`. Its fork reply returns `"forkedFrom": source` as a **string** (line 562), while MSP `Session.forkedFrom` is an object `{sessionId, …}` that the spec reads as `forkedFrom.sessionId`. New Muse fixtures must model it as an object; do not copy the fork fake, and do not make the reader lenient. Serve refuses any frame without `excludeItems is True` and a string `sessionId`, with `-32602`, *before* it dispatches on the method (lines 548–550). So `session/list` and `session/read {excludeItems:false}` fail there today. An unknown method gets `-32601` (line 564). There is no `export` or `init`.
  - **Fake wsl** handles `-l -q`, `-d X -e path` and the reap.
  - Extending the fake for every new path will push it past 1,000 lines (AGENTS.md principle 3), so plan a split.
- **Tests that pin today's surface** (S2 owns these edits; the implementer never touches them):
  - In `test_harness_threads_surface.py`:
    - `EXPECTED_EXPORTS` (line 31), compared exactly at line 127, is 17 names today and 68 after this PR.
    - Each subpackage `__all__` is asserted to be exactly 3 functions (25, 15 and 16 after this PR).
    - `EXPECTED_ENUMS` (line 35) lists exact member values, in order, for every native enum, and for `NativeEnvironmentVariable` also the member names.
    - `NEW_FAILURE_CODES` (line 52) and the tail after `RULE_EVALUATION_FAILED` must equal the 28 codes (32 after this PR, in INV-22 order).
    - `CONTRACT_CONSTANTS` (line 53).
    - `test_thread_functions_are_coroutines_with_the_contract_signature` (line 140) covers only `FUNCTIONS = f"{verb}_{harness}_thread"`.
  - The stale assertion `assert len(main_members) == 120` (line 193) fails today with `148 == 120`. It compares the merge base's `FailureCode` (read with `git show <merge-base>:vidbyte/lib/enums/failure.py`) against a literal. The merge base of this branch and `origin/main` has 148 members. The test returns early when no merge base is found, which is why shallow-clone CI skips it. Line 195, `assert len(members) == len(main_members) + len(NEW_FAILURE_CODES)`, is stale too: after this PR it reads 152 ≠ 148 + 32. Row 35 rewrites both (review R-13).
  - `test_harness_threads_errors.py::test_every_code_has_its_own_likely_cause_and_next_step` (line 193): the table keys must be exactly the native codes plus `CONFIGURATION_INVALID_ARGUMENT` and `RUNTIME_ERROR` (line 198).
  - `test_harness_threads_static_policy.py`: `PACKAGE.rglob("*.py")` (line 29) polices every new module automatically. `NAMED_MODULES` (line 20) lists 14 existing modules, which must still exist.
- **Other tests that read `FailureCode`:** `tests/test_session_failures.py` (every value contains ".") and `tests/test_codex_failure_recovery.py` (only `codex.*`).
- **Real seams (do not mock):**
  - Child processes go through the real `CliRunner` and the fake vendor program, as #1036's tests do.
  - The file system is the real sandbox home and workspace. Write real Grok store files there; the helpers read `Path.home()`, which the `sandbox` fixture redirects through `HOME` / `USERPROFILE`.
  - Do not mock `CliRunner`, `asyncio` subprocesses, `NativeErrorFactory` or the record validators.
  - Time: helpers use `datetime.now(UTC)` once per call, so build fixture timestamps relative to the current time with margins.
- **Per-area config:** none beyond `pyproject.toml`. The `wsl_ready` fixture gates the WSL tests.
- **Run one file:** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads/<file>.py`, or `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills/Scripts/python -m pytest tests/features/harness_threads/<file> -q`.
- **Run all:** `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads` (about 60 s on this machine today). The whole suite runs as part of `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`.

## §14 Agent boundaries

- **Always:**
  - Work only in the worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-helpers-skills`, on branch `feat/harness-thread-helpers-skills`.
  - Use the venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/harness-thread-helpers-skills` for every Python command.
  - Run the focused tests after each §12.3 row, and the area suite after each phase.
  - `git add` new files before `python lint/run.py` and semgrep.
  - Run `python lint/run.py` and both `run_ci.py` stages (source with `PYTHONPATH=$(pwd)`, package without) before reporting done, and quote their final lines.
  - Cite the spec IDs (W-, FR-, INV-, D-) in commit messages, and end each commit with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Catch up with main by merging, never by rebasing.
  - Keep #1036 behavior identical (INV-26).
- **Ask first (stop and report BLOCKED):**
  - **Modifying any test file, fixture or fake under `tests/`.** The test author (S2) owns `tests/`, and the implementer never edits a test file.
  - Exceeding the §8.4 budget (a new file, class, dependency or exported name).
  - Touching a file not listed in §12.3.
  - Changing a public contract beyond §9.2/§9.4.
  - Changing any #1036 default (permission mode, timeouts, caps).
  - Adding a parameter or function the conversation did not ask for.
  - Running any vendor CLI with a real key.
  - Writing to `~/.grok` or a real opencode or Muse store outside a test sandbox.
- **Never:**
  - Commit secrets, keys, or the raw research captures (`oc-export.json`, `oc-config.json`, `inspect*.json`).
  - Delete, skip, xfail or weaken a failing test.
  - Raise `lint/baseline.json` or add a `noqa` or suppression.
  - `pip install` into the global Python (a concurrent pipeline uses it).
  - Push to `main`, force-push, merge the PR, or run `gh pr merge --admin`.
  - Read files under `docs/` other than this spec's folder and `docs/spec/harness-thread-functions/`.
  - Implement anything §3 excludes, including Codex, Claude Code, compaction, deep research and workflows.
  - Put the key on argv, in a file or in an error message.

## §15 Assumptions and open questions

**Assumptions** (stand unless the user corrects them). Every vendor assumption is checked by the manual QA of §12.5.

- **Loud if wrong:** most assumptions are guarded so that being wrong produces a loud error (`protocol_mismatch`, or a fail-closed `command_not_run`).
- **Silent if wrong:** three are not, and a §12.5 probe item settles each one. A-12 left this list in r3: it is verified from the 1.18.31 binary, and the scan cap is loud (EC-75).
  - **A-1, one variant:** Grok stops using session folders at all, so lists return `()` (probe b). EC-67 makes the other variant loud: folders that no longer hold a `summary.json`.
  - **A-4:** USER scope misses threads (probe b).
  - **A-21:** the Muse helpers miss the SDK's threads (probe g).

- **A-1** — Grok keeps each thread at `<GROK_HOME>/sessions/<group>/<session-id>/summary.json`, and the session folder name is the thread id. Source: Grok user guide; no local Grok thread exists to confirm. — *If wrong:* session folders without `summary.json` raise `protocol_mismatch` after the grace period (EC-67); if Grok stops using session folders entirely, lists return `()` (silent; probe b). Fix the layout constants in `GrokStore`. The layout is documented in `17-sessions.md:20-42`, and the `summary.json` members at `:420-431`. Those lines also list `info` and say `agent_name` is kept only for "named agents", which plan and explore are (review r2: HELD).
- **A-2** — In `summary.json`:
  - `created_at` and `updated_at` are RFC 3339 strings with an offset;
  - `generated_title`, `session_summary`, `last_turn_summary`, `parent_session_id`, `current_model_id` and `agent_name` are strings, null, or absent.
  - Source: the documented member list. — *If wrong:* `grok.protocol_mismatch` names the member. Adjust the mapping in `GrokHelperWire.thread_file`.
- **A-3** — Grok replaces `summary.json` atomically. — *If wrong:* EC-62 (an intermittent mismatch while a run writes). The fix would be one retry.
- **A-4** — A group folder's name is the URL-encoded cwd. A long cwd becomes a slug plus a hash, with the original path in a `.cwd` file. — *If wrong:* USER scope misses threads. The SDK scope is unaffected, because it reads every group.
- **A-5** — `grok export <id>` is keyless, honors `GROK_HOME`, finds the thread from cwd = workspace, and prints Markdown on stdout. An unknown id prints `Session '<id>' not found.` (verified offline for an unknown id). — *If wrong:* `read_grok_thread` raises `run_failed` or `thread_not_found`.
- **A-6** — `grok sessions delete <id>` is non-interactive, honors `GROK_HOME`, and removes the session folder without a running leader. — *If wrong:* the post-check raises `grok.run_failed` (EC-23). Nothing is silently left behind.
- **A-7** — `grok --single` expands a leading slash command. UNVERIFIED (offline runs stop at the login check). — *If wrong:* every Grok command function except plan and explore raises `grok.command_not_run` (INV-8). The PR body says so, and the functions then need a long-running session (NG-2).
- **A-8** — `--output-format=streaming-json` prints one JSON object per line with `type`:
  - `tool_call` carries `toolName` and `rawInput`;
  - `text` carries `data`;
  - `error` carries `message`;
  - `end` comes last and carries `sessionId`.
  - Source: Grok user guide. — *If wrong:* `grok.protocol_mismatch` names the missing member.
- **A-9** — The evidence markers hold:
  - With `GROK_WORKFLOWS=0`, `/goal` drives the model-facing `update_goal` tool in the main stream.
  - The `implement`, `design`, `execute-plan`, `review` and `resume-*` skills read their persona or CORE file with `read_file` in the main agent's stream.
  - `/imagine` calls `image_gen` or `image_edit`.
  - Source: the bundled SKILL.md bodies and the docs. — *If wrong:* the affected function raises `grok.command_not_run` (it fails closed). Update `GROK_EVIDENCE_*`.
- **A-10** — `--agent plan|explore` selects the bundled agents, and `summary.json` records `agent_name` for them. — *If wrong:* `run_grok_plan` / `run_grok_explore` raise `grok.command_not_run`.
- **A-11** — The final answer of a streaming run is the text events after the last tool event. — *If wrong:* `text` holds extra narration. The thread id and the evidence are unaffected.
- **A-12** — *Verified in r3 from the opencode 1.18.31 bundle (review R-15, R-16).* `opencode session list --format json`:
  - lists **root sessions only**, as a JSON array of exactly `{id, title, updated, created, projectId, directory}` with epoch-millisecond integers and **no `parentID`**;
  - prints empty output or `[]` when there are none;
  - stops at `--max-count`, which defaults to **100**, across the whole project;
  - chooses the project from cwd/`PWD`.
  - — *If a later version differs:* a changed shape is loud (`opencode.protocol_mismatch`), and hitting the cap is loud (EC-75). Probe f.
- **A-13** — `opencode export <id>` prints `{info: {id, title, time: {created, updated}, parentID?}, messages: [...]}` on stdout. An unknown id puts `Session not found` on stderr. *Verified in r3 (bundle: `{info, messages}`; an unknown id prints `Session not found: <id>`).* Only `read_opencode_thread` uses export, and it returns stdout whole. — *If wrong:* `read_opencode_thread` returns the vendor's new document unchanged, or raises `run_failed`.
- **A-14** — `opencode session delete <id>` is non-interactive, and an unknown id prints `Session not found`. — *If wrong:* `run_failed` with opencode's text.
- **A-15** — *Verified in r3 (review R-17).* `opencode run --command <unknown>` throws `UnknownError` with the message `Command not found: "<unknown>". Available commands: …`, emits it as an `error` event, and exits 1. Stdin text becomes the command's arguments, and an empty stdin is allowed. `--agent plan` is a built-in primary agent. — *If a later version changes the text:* the call raises `opencode.run_failed` instead of `command_not_run` (loud, wrongly coded). Update `OPENCODE_COMMAND_NOT_FOUND_TEXT`.
- **A-16** — A batch `muse serve` answers `session/list` and `session/read {excludeItems:false}` before exiting at EOF. Inline history holds the `toolCall` items, with `tool` and `args`. Source: `msp.schema.json` 1.0.1. — *If wrong:* the Muse helpers raise `protocol_mismatch`, and the skill functions raise `muse.command_not_run` (they fail closed, EC-56).
- **A-17** — The `args` of a Muse `read_skill` tool call contain the skill id. `create_goal` is available in `exec` runs. Source: the bundled skill descriptions ("call read_skill for bundled:<id>"), §E.2. — *If wrong:* the Muse skill functions raise `muse.command_not_run`.
- **A-18** — `muse export --session <id> --out <path>` writes JSON to `<path>`, exits 0, and works with no key under a private config (help text; an offline run in §E.2). — *If wrong:* `read_muse_thread` raises `run_failed` or `protocol_mismatch`.
- **A-19** — `muse init [--dry-run]` is keyless and non-interactive, writes only into cwd, and prints a summary (help text only). — *If wrong:* `init_muse_workspace` raises `muse.run_failed` or `muse.timed_out`.
- **A-20** — #1036 A-3 holds: Grok's default permission mode refuses edits in a headless run. — *If wrong:* the docstring advice (EC-43) is unnecessary but harmless.
- **A-21** — Muse keeps sessions in the user's normal data store, which a private `XDG_CONFIG_HOME` does not move. So helpers and #1036 runs see the same threads (code plus #1036 A-20). — *If wrong:* the Muse helpers miss the SDK's threads. The private config would then have to be dropped for helpers.
- **A-22** — *Settled in r3 (review R-15).* Only subagent children (`Session.create({parentID})`) record a parent. `Session.fork` records none, so a thread made by `fork_opencode_thread` is its own root (EC-76; documented limitation in the README).
- **A-23** — The USER scope is literally `~/.grok` (KD-8). — *If wrong:* Q-4.
- **A-24** — `features.video_gen` is on by default for a key-authenticated headless run, and `/imagine-video` calls the model-facing `image_to_video` tool in the main stream (`04-slash-commands.md:277`, `26-config-reference.md:290`; the default is not documented). — *If wrong:* `run_grok_imagine_video` raises `grok.command_not_run` naming `features.video_gen` (EC-74). Probe c.
- **A-25** — `--session-id=<uuid4>` combines with `--single` and creates the session under `GROK_HOME` with exactly that id, and `end.sessionId` echoes it (`14-headless-mode.md:25`, `:354`). — *If wrong:* every Grok command run raises (grok refuses the flag → `run_failed`, or the ids differ → `protocol_mismatch`). D-29 then flips back to r1. Probe c.
- **A-26** — Bundled skills and `shared/personas` resolve under a fresh private `GROK_HOME`. Grok distributes them separately and caches them under `~/.grok/bundled/skills/` (`08-skills.md:213`); the private home would fetch or point to its own copy. — *If wrong:* every skill-backed Grok command function raises `grok.command_not_run` on every paid call. The PR body says so, and the fix is to link the bundled cache into the private home. Probe a.
- **A-27** — The expanded `/code-review` skill text reaches the session transcript that `grok export` prints, so `GROK_CODE_REVIEW_FRAGMENT` appears in it. — *If wrong:* `run_grok_code_review` always raises `grok.command_not_run` (fails closed; D-28 flip). Probe c.
- **A-28** — `muse export --session <id>` writes the whole session, including tool calls from before an automatic compaction, with the tool name and its arguments as text. — *If wrong:* a compacted Muse skill run raises `muse.command_not_run`, whose cause names compaction (fails closed; D-33). Probe g.
- **A-29** — *Verified in the 1.18.31 bundle (review r2).* `opencode db "<query>" --format json` runs the query in-process against opencode's database (`instance:!1`) and prints a JSON array of row objects. The `session` table has `id`, `title`, `time_created`, `time_updated` (epoch ms), `parent_id` and `directory`. — *If a later version differs:* get and lineage raise `opencode.run_failed` or `protocol_mismatch` (loud). D-26 then flips to `export` `info`. Probe f.

**Open questions** (max 5 blocking):
| ID | Question | Blocking? | Default if unanswered |
|---|---|---|---|
| Q-1 | Add `compact_grok_thread` (and a Muse compaction over a long-running session) once the manual probe shows `/compact` expands headless? | non-blocking | No; NG-3 stands |
| Q-2 | *Closed in r2 (review R-4):* `run_grok_code_review` and `run_grok_imagine_video` are built. It reopens only if A-27 fails (code-review always `command_not_run`). | — | — |
| Q-3 | Should `get_grok_thread` also return the plan, to-do list and goal state (`plan.json`, `plan.md`) in a separate record? | non-blocking | No; the record is KD-7's fixed `NativeThreadSummary` |
| Q-4 | Should `GrokThreadScope.USER` honor an inherited `GROK_HOME` instead of literally `~/.grok`? | non-blocking | No (D-21) |
| Q-5 | Add a sanitized or redacted option to `read_opencode_thread` / `read_muse_thread`? | non-blocking | No (NG-15) |
| Q-6 | Add the generic `run_grok_skill`, `run_opencode_skill` and `run_muse_command`, or a free-name `run_grok_command`, with a caller-supplied evidence rule? | non-blocking | No (NG-7, D-5) |
| Q-7 | [scope-adding] Filter subagent child threads out of the list helpers (EC-72)? | non-blocking | No; they list as ordinary threads, and the README says so |
| Q-8 | [scope-adding] Run a `grok inspect --json` pre-flight before each Grok command run, to refuse a workspace or user-level skill that shadows the bundled one (EC-78)? | non-blocking | No; the run fails closed, and the `command_not_run` texts name shadowing and `collidesWith` (D-32) |

No question blocks this spec.

## §16 Review log
| Round | ID | Severity | Section | Finding (one line) | Disposition | Change made / reason |
|---|---|---|---|---|---|---|
| 1 | R-1 | Blocker | §12.3 rows 14, 20, 26 | opencode lineage looped `get`, which calls `_child`: a two-deep same-class chain | accepted | Rows 14, 20 and 26 now state that `lineage` and `read` call the lower-layer step directly (`GrokStore.thread`; `_child` + wire; a shared private serve helper), never `get`. Added the §12.4 line "No flow calls a sibling flow" |
| 1 | R-2 | Major | §9.2, row 11 | the Grok scan treats `sessions/session_search.sqlite` and `<group>/permission*.toml` as groups or sessions | accepted | Verified: `~/.grok/sessions/` here holds only `session_search.sqlite`. Only directories are groups or session candidates, and files at both levels are ignored (§9.2, row 11, D-27). Added EC-66, AC-27, and §13 and row 37 fixture notes |
| 1 | R-3 | Major | §9.1, §12.4 | inline `isinstance(x, bool)` guards on `limit`, `concurrency`, `pr` and the epoch value would push blocking C002 past its baseline of 9 | accepted | Verified `lint/baseline.json:11` and `validation.py:85/:92`. §9.1 routes every int and bool through `require_int` / `require_bool`. Added `GROK_PR_MAX_NUMBER`. One private epoch converter (row 19). Added the §12.4 C002 line |
| 1 | R-4 | Major | NG-5 | the exclusion of `run_grok_imagine_video` and `run_grok_code_review` rested on false vendor facts | accepted (wider than the smallest fix, per the orchestrator: both are in the accepted §E.2 catalog, request.md:267/:269) | Verified `04-slash-commands.md:275-277`, `26-config-reference.md:290` and the 192-line code-review SKILL.md. Both are built: `GrokCommand.CODE_REVIEW`/`IMAGINE_VIDEO`; imagine-video evidence is `image_to_video`; code-review evidence is the run's own `grok export` containing a skill-body sentence (D-28), because the skill has no tool trace. NG-5 withdrawn, Q-2 closed. Added A-24, A-27, EC-73, EC-74 and AC-30. Counts: 47 functions, 68 exports, grok 25 |
| 1 | R-5 | Major | §9.1, §9.2, INV-9 | caller text inside the slash-command line could become an option (`--auto-pr`, `--budget`), split a path at a space, or hit a reserved `/goal` word | accepted | `GrokCommandArguments` rule 9 (`named`, `text_field`) and rule 3 (no whitespace in `design_doc`). Added D-30, the INV-9 bullet and T-8. EC-42 is now a refusal, and EC-69, EC-70 and EC-71 were added. `run_grok_command`'s raw arguments stay unchecked |
| 1 | R-6 | Major | EC-50, §9.2 | a timed-out or capped Grok command run lost its thread id | accepted (internal flag only) | Verified `14-headless-mode.md:25/:354`. `GrokCommandRun` mints a UUID4 and passes `--session-id` (`GrokFlag.SESSION_ID`). Every post-launch error carries it, and a mismatched `end.sessionId` raises `protocol_mismatch`. Added INV-29, D-29, A-25 and AC-29; EC-50 rewritten. No public parameter; #1036's `run_grok_thread` unchanged |
| 1 | R-7 | Major | §9.2, row 11, INV-6 | an operation on one id inherited the whole-store strict parse, so a sibling's bad file failed it | accepted | `GrokStore.thread` reads only `<group>/<id>/summary.json` (and each parent's, for lineage). Whole-scope strictness applies to list and search only. Added D-27, the INV-6 scope bullet, EC-68 and AC-28; EC-62 narrowed |
| 1 | R-8 | Major | §12.5, A-7 | the probe ran bare `grok` in the user's shell, not the SDK path, and bundled-skill resolution under a private home was unstated | accepted | Probe (a) now calls the SDK functions, prints thread id, tools and code, and includes a slash-less negative control. Added A-26 (bundled skills under a private `GROK_HOME`; the reviewer's "A-22" is taken, so it is A-26) |
| 1 | R-9 | Major | §15 preamble, EC-11 | "never a silent wrong answer" was false for A-1, A-4, A-12 and A-21 | accepted (refined) | Added the EC-67 layout bound with a `GROK_SUMMARY_GRACE_SECONDS` (60 s) grace on the newest folder, so a fresh home's first run does not raise mid-start (D-31). The preamble now names the silent-if-wrong items and their probes |
| 1 | R-10 | Major | §9.2 opencode | get and lineage ran full exports per step, and the request's `opencode db` mechanism was dropped without a D- | accepted | get and lineage use the one `session list` child and walk `parentID` in memory; only read exports. Added D-26 (records the move from `opencode db` and r1's export) and AC-31; removed `OpencodeHelperWire.info`; updated NFR-12 |
| 1 | R-11 | Minor | INV-26 | "codes and messages unchanged" contradicted FR-17 and D-20 | accepted | INV-26 now reads "codes and behavior unchanged; message texts change only per FR-17 and D-20" |
| 1 | R-12 | Minor | rows 26, 27; §9.1 | `MuseCommands` would have two guarded `_call`s, and `search_text: str` fed a `Sequence[str \| None]` | accepted | `init_muse_workspace` moved to `MuseThreadHelpers` (rows 26, 27 and 28 counts). `GrokThreadFile.search_text` is a `tuple[str \| None, ...]` |
| 1 | R-13 | Minor | row 35, §13 | line 195 is also stale, and the fake's `forkedFrom` is a string, not the MSP object | accepted | Verified both (line 195; `fake_harness.py:562`). Row 35 names line 195, and §13 and row 37 require object-shaped `forkedFrom` in new fixtures |
| 1 | R-14 | Minor | §6.3 | subagent child threads list as ordinary threads with no EC or README line | accepted | Added EC-72, the README sentence (row 33, AC-26) and Q-7 [scope-adding], default no |
| 2 | R-10 (re-disposition) | Major | D-26 | r2's "one `session list`, walk `parentID`" cannot work, because the list is roots only and has no `parentID` | accepted; resolved by R-15 | get and lineage now use `opencode db` with a constant query by id (one child per id). That keeps R-10's goal of moving no transcript |
| 2 | R-15 | Blocker | D-26, §9.2, AC-31, A-12, A-22 | opencode get and lineage read a list that never holds a child and never carries `parentID` | accepted | Verified in the 1.18.31 binary: `roots:!0`; the row writer has no `parentID`; `db [query] --format json` has `instance:!1`; the `session` table has `parent_id` and `time_*`. D-26 rewritten to the request's `opencode db` mechanism, with a flip to `export` `info`. Added `OpencodeHelperWire.rows`, T-9, EC-76 (forks record no parent: limitation and README), EC-77 and A-29. AC-6, AC-31, §9.1 mapping, NFR-12, rows 19 and 20, A-12, A-22 and §13 updated |
| 2 | R-16 | Major | D-19, §9.2, A-12 | `session list` without `-n` stops at 100 rows across the project | accepted | Verified `limit??100`. Lists always pass `--max-count=NATIVE_OPENCODE_SCAN_MAX` (10,000; `OpencodeFlag.MAX_COUNT`). Exactly the cap raises `opencode.protocol_mismatch` naming it (EC-75, AC-32), never a short list. This is an error, not a public parameter |
| 2 | R-17 | Major | A-15, row 4, D-8, EC-52 | opencode prints `Command not found: "<name>"`, not the text the spec matched | accepted | Verified in the binary. `OPENCODE_COMMAND_NOT_FOUND_TEXT = 'Command not found: "{command}"'` is a prefix match on `error.data.message` or stderr. A-15 is restated as verified, and AC-16, EC-52, D-8 and §13 are updated |
| 2 | R-18 | Major | FR-17, row 4, §12.4 | helpers reuse #1036's run-only `timed_out` and `output_too_large` texts ("raise timeout_seconds", "ask for a shorter answer") | accepted | FR-17, row 4 and §12.4 widen `TIMED_OUT` / `OUTPUT_TOO_LARGE` (all 3 harnesses) and `OPENCODE_PROTOCOL_MISMATCH`. The texts name the control timeout, whole transcripts, and both Grok caps. INV-26's exception lists them, and AC-20 checks them. No code path changes |
| 2 | R-19 | Major | §9.1 rule 9, D-30, INV-9, EC-70, AC-12 | every named wrapper refused all eight flag tokens, which blocks ordinary text such as "Add a --dry-run flag" | accepted | The refused set is now per command: `GROK_TEXT_OPTION_FLAGS` (goal `--budget`, implement `--effort`, others none). T-8 keeps its protection, because execute-plan carries no caller text. EC-70 and AC-12 show passing examples |
| 2 | R-20 | Major | D-4, §9.2, §12.4 | a same-named workspace, user or `skills=` skill shadows the bundled one, and the cause blamed slash expansion | accepted (refusal plus texts; the pre-flight is a Q) | D-32: refuse a `skills=` folder named like the command (rule 10, field `skills`, AC-33). EC-78 added. The `grok.command_not_run` cause and next step name shadowing and `grok inspect --json` (`collidesWith`), and there is a README sentence. The pre-flight is Q-8 [scope-adding], default no |
| 2 | R-21 | Minor | §5, §9.1, §12.6, §15 | r1 leftovers and gaps around the r2 changes | accepted | P5 now ships 25. A-13 now refers to read only. The §9.1 opencode mapping is fixed, and §5 G1 names `GrokStore.thread`. A-1 now cites `17-sessions.md:420-431` for the members. Row 15 now depends on rows 11 and 14 (§12.6). `GrokStore.thread` with a `NativeThreadRequest` means SDK scope (§8.5, row 11) |
| 2 | R-22 | Minor | row 14, §8.5 | `GrokHelperRun.export` is both a helper and an entry point, so a shared `_child` would make it two deep | accepted | Row 14 and §8.5: `export` and `delete` build their `CliInvocation` inline from `GrokHome.environment(home, None)`, and `export` calls no other `GrokHelperRun` method |
| 2 | R-23 | Minor | INV-29, AC-29 | the minted id was promised as an existing thread even for pre-session failures | accepted | INV-29: the id is the one requested. It is known to exist only after `end` or `tool_call`, or for `command_not_run`, `timed_out` and `output_too_large`. Otherwise the detail says "the thread may not exist" (`GROK_THREAD_MAY_NOT_EXIST_DETAIL`). Added EC-81, and AC-29 covers `key_rejected` |
| 2 | R-24 | Minor | D-25, INV-3 | on win32 the built prompt could be refused under the name `prompt` | accepted | D-25 also runs `require_command_line_units` on the text under its public name, with the budget `NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS - NATIVE_COMMAND_RESERVED_CHARS` (Grok and Muse). Added EC-80 and the AC-12 case |
| 2 | R-25 | Minor | row 25 | in `anchoredSnapshot` mode the early `read_skill` item is gone, so long Muse runs fail closed | accepted | D-33: in `anchoredSnapshot`, evidence comes from the run's own `muse export` transcript (D-17's child). This uses `MuseSessionWire.tool_calls → None` and the `MuseHelperRun.transcript` flow, which shares `_export` with `read`. Added A-28, EC-79 and AC-34; the `muse.command_not_run` cause names compaction |

## §17 Revision history
| Revision | Date | Stage | Summary |
|---|---|---|---|
| r1 | 2026-10-15 | S1 spec | Initial spec: 22 helpers and 23 command/skill functions for Grok, opencode and Muse; shared `NativeThreadSummary`; skill functions verify their own run's record (or fail with `command_not_run`); 10 new source files |
| r2 | 2026-10-15 | S1 review round 1 | All 14 findings accepted (R-1 to R-14). Restored `run_grok_code_review` (export-transcript evidence) and `run_grok_imagine_video` (47 functions, 68 exports). Internal `--session-id` for Grok command runs. One-id Grok reads and directories-only store scan with a layout bound. Option-injection refusals in the slash line. opencode get/lineage from one `session list`. C002-safe validators. No flow-to-flow calls. Rebased base to `0f69f7b7`. Still 10 new source files |
| r3 | 2026-10-15 | S1 review round 2 (final; approved) | All 11 findings accepted (R-15 to R-25), and R-10 re-disposed through R-15. opencode get and lineage use the request's `opencode db` query by id, and forks record no parent (limitation). opencode lists pass `--max-count=10000` and raise at the cap. Fixed the opencode unknown-command text. Widened the timeout and output-cap error texts. Per-command flag refusals. A `skills=` shadow refusal plus shadowing texts. INV-29 says when the thread may not exist. Windows command-line units checked under the public name. Muse `anchoredSnapshot` evidence comes from the export. Status approved. Still 47 functions, 68 exports, 10 new source files |
