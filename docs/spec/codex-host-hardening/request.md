---
slug: codex-host-hardening
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
invoked: 2026-10-17
flags: none
---

# Request: CodexHost production hardening and missed settings (slice 1 of 2)

> **This is slice 1 of 2** of one run on branch `feat/codex-host-first-class`, which ships as one PR.
>
> **Slice 1 (`codex-host-hardening`, this spec) covers:**
> - everything in §C.9: the cross-cutting gaps X1–X9 and the per-function table;
> - the settings gaps S1–S10 in §C.10;
> - the P0 item "an approval / user-input handler on `CodexHost`", because it is the fix for X6 and S5;
> - X7, closed in this slice by the smallest sufficient retention/eviction mechanism (for example `forget_codex_turns`). Slice 2 will not redo it.
>
> Slice 1 makes the existing 27 functions, the 6 one-shot functions and the 26 tools production-grade, and completes their settings.
>
> **Slice 2 (`codex-host-first-class`, a later separate spec) covers** every other P0 and P1 new function in §C.10, built on slice 1's commits: `update_codex_thread_settings`, plan-mode functions, `stream_codex_turn`, `wait_codex_turns`, `list_codex_mcp_servers`, and all of P1.
>
> P2 is not built (Open questions).

## A. Every user prompt in this conversation, verbatim and in order

**Prompt 1** (start of the conversation):
````
what are all the functions we implemented in pr #1055 for vidbyte-sdk/?
````

**Prompt 2** (after the assistant listed the 27 CodexHost functions, the 6 one-shot functions, the 26 agent tools and the internals of PR #1055):
````
great, 2 things I want to clarify: 1) are there any things we missed in the end to end implementation of each function. Want each function to kind of have "all layers" required to push to production and exception handle everything that could potentially go wrong. (include maybe checklist of things that were missing from each function and 2) are there any other "first class codex feature functions that were missing" or any settings that we did not handle in each function (read all codex documentation for second part in subagent). For example, I know that codex has a '/fast' (not just a skill, this can be enforced via setting), a "/memories", "/review", "/forkk", "/worktree", "/app", "/compact", "/plan",   "/side", "/mcp", "/plugin". Some of these might be settings,  but some may also be first class codex features (like they are skills provided by codex where there probable more than just a prompt to them. Do you think that with these you can brainstorm the functions that we might have missed in the pr and with a subagent can you repeat this same process for pr #1044 for claude and leave comments on the pr of functions for claude code we might have missed/apply all this feedback to that pr as well (launch subagent for this part as well, subagent should leave comments on the pr not change the pr)
````

**Prompt 3** (the invocation of this pipeline, after the assistant delivered the audit in §C.9 and §C.10 below):
````
great, I am going to merge pr #1055 into the repo,  before you kick off what I am about to say can you make sure to wait that pr #1055 is merged into main. then I want you to create the codex functions that you thought about. Also, the comments that you left on pr #1044, i dont think  that they were clear about what to change/add to the claude code commands, I wanted the same 'first class claude code features" that you added for codex in the list above, using all of claude code's built in skills/settings/functionalities, can you think about all of these and then add some more comments on pr #1044 (do all of this after #1055 merged, just so you are on the same page)
````

## B. Handoff block and decision ledger (verbatim, if present)
No handoff block.

### B.1 The user's own review comments on PR #1055 (verbatim; added at S1)
The user (GitHub `cerredz`, the repo owner) left five inline review comments on PR #1055 on 2026-10-17. Their open PR **#1178** "fix: resolve review comments from PR #1055" (branch `ai/resolve-pr-1055-comments`, head `8baff351`, one commit on top of `6f5a7310`) applies them.

These comments are the user's stated conventions for this exact code. They bind every new or changed line in this run just as much as §A does.

- `vidbyte/harnesses/native/codex/connection.py:91` (4301484278):
  ````
  wrong file location, put inside of lib
  ````
- `vidbyte/harnesses/native/codex/errors.py:45` (4301488494):
  ````
  wrong file location, shold be in lib folder, also error messages need to go into way more details, the way we havve them formatted in erorr folder in lib folder
  ````
- `vidbyte/harnesses/native/codex/host.py:114` (4301489517):
  ````
  same feedback for error messages here
  ````
- `vidbyte/harnesses/native/codex/host.py:323` (4301496612):
  ````
  all these functions in this file should have dataclasses with strict input validation
  ````
- `vidbyte/harnesses/native/codex/preflight.py:78` (4301744297):
  ````
  wrong file locations, in lib folder
  ````

**What #1178 turned them into** (the conventions this run follows):
- Every fixed value the native host reads goes in `vidbyte/lib/constants/codex_host.py`. Lint **C021** `native-host-constants-in-lib` blocks any top-level UPPER_CASE binding under `vidbyte/harnesses/native/`, with a baseline of 0.
- Every `CodexAgentError` reads `<operation> failed with <code>. <summary> The thread id was <id>. Likely cause: <cause> Next step: <step>`, with the lib error-packet fields filled in.
- Every public `CodexHost` method that takes input builds a frozen, validated record from `vidbyte/lib/dataclasses/codex_host_inputs.py` right after `_guard`. `REJECTED_FIELDS` now lives in those records.

## C. Structured conversation notes

### Key decisions
- **Start only after PR #1055 merged into main.** The user asked for this explicitly (Prompt 3). The base commit of this run is `origin/main` after the merge, which contains the whole CodexHost package from #1055.
- **The run is stacked on the user's open PR #1178** (decided at S1 review round 1, orchestrator decision, logged in pipeline.md).
  - The branch was rebased from `6f5a7310` onto #1178's head `8baff351`, so the base commit is now `8baff3514640a5c5f110c1e2c7cea996d1640ecb`.
  - #1178 applies the user's own #1055 review comments (§B.1) to 11 of the files this slice changes. Building beside it would conflict in every one of them and would fail C021 once it merges.
  - When #1178 merges into main, the branch takes main by merge, never by force-push.
- **"The codex functions that you thought about" means the ranked P0 and P1 proposals in §C.10**, plus the settings that were missed inside existing functions (S1–S10 in §C.10). Each proposal names its Codex app-server method; build each one over that protocol method, never by sending slash-command text. #1055 set this precedent for goal and skill runs.
- **The production bar is the user's own words in Prompt 2:** "each function to kind of have 'all layers' required to push to production and exception handle everything that could potentially go wrong". Every new function must meet the L1–L16 layer list in §C.9. Because new and old functions share one connection, error mapper, registry and tool base, the cross-cutting gaps X1–X9 and the per-function gaps in §C.9 are fixed as well.
  - This is an orchestrator decision: the user asked for the checklist and stated the bar, but did not say "fix them" in Prompt 3. It is logged in pipeline.md, and the user can interrupt.
- **Two slices on one branch and one PR.**
  - Slice 1 `codex-host-hardening`: §C.9 (X1–X9 plus the per-function gaps) and the settings gaps S1–S10 in existing functions, including the server-request / approval / user-input handler (it fixes X6 and S5).
  - Slice 2 `codex-host-first-class`: every P0 and P1 new function in §C.10, with its agent tool where the tool rules allow one.
  - The precedent is PR #1055, which shipped `docs/spec/codex-host/` and `docs/spec/codex-host-thread-helpers/` in one PR. Slice 2 builds on slice 1's commits.
- **Destructive or unsandboxed functions are never agent tools.** #1055's INV-2 precedent is that `delete_codex_thread` has no tool. The same applies to `reset_codex_memories`, revert, and any `process/spawn`.
  - Tools must never let a model widen approvals or the sandbox.
  - The service tier (Fast costs about 2.5x) stays developer-only and is not exposed to models.
- **The binary is ground truth.** Every protocol claim is checked against the schema generated from the installed `codex-cli 0.163.0` (`codex app-server generate-json-schema --out <dir>`, plus the experimental flag the CLI offers). Where the docs disagree, the binary wins.
- **Experimental protocol fields are added after the openai-codex model validation**, the way #1055 already adds `dynamicTools` (`CodexParamsTranslator.thread_start`). openai-codex's generated Pydantic models cover only the stable schema and silently drop unknown fields: `TurnStartParams.model_validate({..., "collaborationMode": ...})` drops `collaborationMode` (verified).

### Rejected alternatives
- **Slash-command text** for plan, compact, review, memories or side runs. Rejected because #1055 established protocol-level runs that are read back and confirmed.
- **Building the P2 items** (open in Desktop app, recap, voice/realtime, hooks, feedback, marketplaces, `process/spawn`): ranked niche in the conversation, so not built by default (see Open questions).
- **Separate PRs per slice.** Each would need a user merge before the next could start.

### Constraints and assumptions
- Python `>=3.11`. The optional extra `openai-codex` is pinned `>=0.162.1,<0.163.0`. 0.163.0 is on PyPI and matches the installed CLI; its hand-written modules are byte-identical to 0.162.1, and only generated models differ (research report §8). Raising the pin is S10.
- Tests use the fake app-server from #1055 (`tests/features/codex_host/codex_host_fakes.py` and related). Any live test against a real `codex app-server` must be opt-in, gated by an environment variable, skipped by default, and must never run a paid turn in CI.
- `docs/` is opaque in this repo (AGENTS.md). Agents read only the `docs/spec/...` files their briefing names.
- PR #1044 (Claude Code thread functions) is handled separately by review comments only. Nothing in this run touches its code.

### Clarifications and answers
- Q (assistant, implicit): which Codex features are settings and which are first-class features? A: answered by the research in §C.10 (table "Your named features").

### Terminology
- **CodexHost**: the async context manager from #1055 (`vidbyte/harnesses/native/codex/host.py`) running one `codex app-server` process.
- **Handle / snapshot**: `CodexTurnHandle` (thread id + turn id) and `CodexTurnSnapshot` (status, result, problem).
- **L1–L16**: the production layer list in §C.9.
- **X1–X9**: cross-cutting gaps.
- **S1–S10**: settings gaps.
- **P0/P1/P2**: proposal priorities.
- **Slice**: one pipeline pass with its own `docs/spec/<slug>/`.

### Implementation hints
- **#1055's files** (all on main after the merge):
  - `vidbyte/harnesses/native/codex/{host,connection,errors,preflight,turns,wire,thread_helpers,skill_functions,oneshot,__init__}.py`
  - `vidbyte/lib/dataclasses/codex_host.py`, `vidbyte/lib/dataclasses/codex.py` (`CodexThreadSettings`, `CodexTurnSettings`, `CodexClientSettings`)
  - `vidbyte/lib/enums/codex.py`, `vidbyte/lib/constants/codex.py`
  - `vidbyte/tools/builtins/codex/{_base,readiness,threads,live,delegation,thread_helpers,skill_functions,descriptions}.py`, `vidbyte/tools/toolsets/codex.py`
  - `vidbyte/agents/codex/{tools,result}.py`, `vidbyte/lib/errors/base.py` (`CodexAgentError`)
  - tests in `tests/features/codex_host/`
- **#1055's specs** (readable when a briefing names them): `docs/spec/codex-host/spec.md`, `docs/spec/codex-host-thread-helpers/spec.md`. Their INV-/D-/EC- IDs are cited throughout §C.9.
- **The Codex research report**, produced by a research subagent from the installed binary, is committed with this run at `docs/spec/codex-host-hardening/context/codex-gap-report.md` with the generated method table `docs/spec/codex-host-hardening/context/coverage-matrix.md`. It holds the exact protocol mapping, params, failure modes and tool class for every proposal.
- **Pattern to follow for a new thin helper:** `CodexThreadHelpers` (`thread_helpers.py`): guard, then argument checks, then busy/exists checks, then one call through `CodexConnection`, then a record from `CodexResponseTranslator`.
- **Pattern to follow for a run wrapper:** `CodexSkillFunctions` (`skill_functions.py`): go through the host's public functions, read the result back, interrupt once on failure.
- **Pattern to follow for a tool:** one `_CodexHostTool` subclass per function, registered in `CodexHostTools` in function order.
- **Raw calls:** a protocol method the SDK has no typed method for goes through `CodexConnection.raw()` with its generated response model added to `RAW_RESPONSES`. A raw call that spends usage goes in `SPENDING_RAW_METHODS` so it is sent once.

### Open questions (resolve as A-/Q-items)
- **Q:** build any P2 item? Default: **no**, listed as a follow-up.
- **Q:** name of the environment variable gating the live smoke test (X9). Default: pick one in the repo's existing style, skipped unless it is set.
- **Q:** do `thread.config` overrides apply when resuming an already-loaded thread, and is `review_model` read from thread config? (Research report §10, UNVERIFIED.) Resolve against the binary or the source at the `rust-v0.163.0` tag; otherwise state as an assumption.

## D. Weighted words
- "Want each function to kind of have **"all layers"** required to push to production and **exception handle everything that could potentially go wrong**." (Prompt 2)
- "read **all** codex documentation for second part in subagent" (Prompt 2)
- "can you **make sure to wait** that pr #1055 is merged into main" (Prompt 3)
- "create **the** codex functions that you thought about" (Prompt 3)
- "using **all** of claude code's built in skills/settings/functionalities" (Prompt 3; applies to the PR #1044 comments, not to this run)
- "do **all** of this after #1055 merged" (Prompt 3)

---

## C.9 Conversation finding: the production layer audit of PR #1055 (assistant's reply, verbatim)
Line references were taken at PR head `ea473f63`, before the merge. **Re-verify every reference against the merged main**, since later commits may have moved or fixed lines.

### Part 1: production layer audit (X1–X9 and per-function gaps)

Audited at PR head `ea473f63` against merge-base `f7f32b19`. Every path below is relative to the repo root at that commit.

## Layer legend (the same framework is used for the #1044 review)
- L1 contract
- L2 input validation
- L3 environment preflight
- L4 lifecycle/state
- L5 wire translation
- L6 transport robustness
- L7 response validation
- L8 error taxonomy
- L9 retry/idempotency
- L10 cost/limits
- L11 concurrency/cleanup
- L12 security
- L13 observability
- L14 agent-tool exposure
- L15 tests
- L16 docs

## What is already done well (no action)
- Host lifecycle: it opens once on one loop and a failed open is cleaned up. `__aexit__` closes in a fixed order and is cancel-safe. A liveness monitor ends every running turn when the process dies.
- Any call that spends is sent once, through a shield. A start that outlives its caller is adopted and given one interrupt (INV-11). Every call is bounded at 300 s on the host's own executor.
- Spawn requests are validated thoroughly when they are built, and the per-operation `reject_unusable_fields` means no setting is silently ignored.
- Before anything spends, a preflight checks sign-in, the usage allowance, the Windows sandbox and that each named model exists.
- No SDK text, stderr or email ever reaches an error message (INV-9).

## Cross-cutting gaps (fix once, fixes all 27)
- [ ] **X1 L8: the structured thread_id is dropped.** `CodexErrorMapper.error()` (`vidbyte/harnesses/native/codex/errors.py:61-65`) writes the thread id into the message text but never passes `thread_id=` to `CodexAgentError`. Reproduced: `reviewer_refusal(..., "thr_123").thread_id == ''`. As a result:
  - a spawn whose `thread/start` succeeded but whose name-set or turn start failed leaves a thread the caller can find only by parsing the message;
  - `launch_codex_subagents` re-raises with `thread_id=exc.thread_id`, which is always `''`.
- [ ] **X2 L13: no observability at all.** There are zero logger, trace or metric references in `harnesses/native/codex/` or `tools/builtins/codex/` (grep).
  - Nothing is wired to `vidbyte/trace/`, `vidbyte/sessions/trace_capture.py` or middleware hooks. The older `CodexHarnessAgent` does support `before_run`/`after_run`/`on_model_error` hooks.
  - `raise … from None` (INV-9) combined with no debug log means the root cause of "X failed with KeyError" cannot be recovered in production.
  - Needs a redacted debug log for each call (method, duration, thread/turn id, failure code) and trace capture of turn items.
- [ ] **X3 L6: turns can end up stuck as RUNNING.**
  - `_on_turn_event` (`host.py:842`) and `_complete_review` (`host.py:829`) have no exception guard. An exception there goes to the loop's handler, so `finish()` never runs.
  - `CodexTurnWatcher._relay` (`turns.py:301-309`) exits silently on any read error without ending the turn.
  - Together with `wait_codex_turn`'s default `timeout_seconds=None`, the caller hangs forever. A `timeout_seconds` timer does not save it either: the interrupt is sent, but nothing reads the completion.
  - Fix: if a watcher ends before its turn completes, finish the turn with a problem, and guard both callbacks.
- [ ] **X4 L9: retry behavior is inconsistent.** The typed SDK methods (`thread_start`, `thread_resume`, `thread_read`, `thread_list`, `account_read`, `thread_compact`, `turn_steer`) call `CodexClient.request` with no overload retry (`openai_codex/client.py:465-535`). Only the raw path uses `request_with_retry_on_overload` (`connection.py:209`).
  - So `get_codex_rate_limits` retries an overload, but `read_codex_thread`, every list helper and spawn's preflight account read do not.
  - `CodexAgentError` has no `retryable` attribute, so callers cannot tell a transient failure from a permanent one.
- [ ] **X5 L8: errors on `thread/read` are misclassified.** Any JSON-RPC error on `thread/read` becomes `codex.session_not_found` (`errors.py:101-102`). An overload or internal error therefore looks like "not found":
  - lineage silently truncates;
  - delete, compact, goal and continue report a thread they could not read as missing.
- [ ] **X6 L12: approval requests are auto-accepted.** The router accepts every `item/commandExecution/requestApproval` and `item/fileChange/requestApproval` that reaches the host (`connection.py:127-128`), and answers every other server request with `{}` (`connection.py:129-130`).
  - There is no approval callback for the developer and no audit record of what was approved.
  - `approval_policy=UNTRUSTED` or `ON_REQUEST` cannot gate anything inside this process.
- [ ] **X7 L11: memory grows without bound.** `CodexTurnRegistry._turns` keeps every `CodexLiveTurn`, with its full `items` list, for the life of the host (`turns.py:82`, `turns.py:320`). A long-lived service host grows without limit, and there is no function to forget or evict turns.
- [ ] **X8 L14: tools can still raise.** `_CodexHostTool._run` (`tools/builtins/codex/_base.py:112-125`) catches only `CodexAgentError`, `ConfigurationError` and `ToolExecutionError`. Any other exception escapes into the agent loop, despite INV-10's "tools never raise".
- [ ] **X9 L15: no live smoke test.** All 20 test files use the fake app-server. There is no gated test against a real `codex app-server`, so drift between the pinned openai-codex SDK 0.162.1 and the installed CLI 0.163.0 is never exercised.

## Per-function gaps (beyond X1–X9)

| # | Function | Missing |
|---|---|---|
| 1 | `check_codex_ready` | L3: `ready=True` even when `ordinary_usage_allowed=False`, so every spawn then fails with `codex.usage_limited` (`wire.py` `readiness` skips the preflight's step 2). |
| 2 | `get_codex_rate_limits` | Only X2. |
| 3 | `list_codex_models` | L4: preflight caches the model list for the whole life of the host (`preflight.py:131`). A model added later reads as `codex.model_unknown` until restart; there is no TTL. |
| 4 | `spawn_codex_thread` | L11: when the name-set or turn start fails after `thread/start`, the thread is orphaned (see X1) and its tool handler stays registered until close (`host.py:667-670`). L10: 3–4 uncached preflight round trips run before every spawn. |
| 5 | `continue_codex_thread` | L4: **no unfinished-goal guard.** `compact_codex_thread` refuses to load a thread with an unfinished goal because Codex could resume it as untracked paid turns (INV-18, `thread_helpers.py:164-166`). Continue loads the same kind of thread unchecked (`host.py:302-306`). |
| 6 | `fork_codex_thread` | Reads the entire thread with all its turns just to pick a fork point (`host.py:334`), which is heavy on long threads. Preflight is skipped, so a mistyped override model surfaces as `codex.fork_failed` rather than `codex.model_unknown`. A name-set failure after the fork orphans it (X1). |
| 7 | `list_codex_threads` | L2: `cwd`, `search`, `cursor` and `source_kinds` are not validated, and falsy values are silently dropped (`wire.py:300`). There is no `limit` parameter. |
| 8 | `read_codex_thread` | X5. |
| 9 | `wait_codex_turn` | X3, and its timeout is unbounded by default. There is no way to wait on several handles (first-completed or all) for fan-out. |
| 10 | `get_codex_turn_result` | Works only for turns this host instance started. After a restart a handle is unknown, with no fallback to the stored turn through `thread/turns/list`. |
| 11 | `steer_codex_turn` | Race: if the turn ends between the snapshot check and `turn/steer`, the result is `codex.api_error` rather than "already ended" (`host.py:409-413`). It does not refuse while a stop is pending. |
| 12 | `interrupt_codex_turn` | No option to wait until Codex confirms the turn was interrupted. |
| 13 | `track_codex_thread_usage` | Counts only turns this host saw end, and resets with each host. It cannot read stored or past usage. Plausible but unverified: spend by Codex's own subagents (`CodexSubagentSettings`) is not counted. |
| 14 | `launch_codex_subagents` | Starts turns serially (`host.py:465-469`), so latency is N × 3 round trips, and there is no concurrency control. A thread whose turn failed to start is left behind. There is no default fan-out cap. |
| 15 | `start_codex_review` | L10: `REVIEW_REQUEST = CodexSpawnRequest()` (`host.py:114`), so a review cannot be capped by time or tokens, and the caller cannot choose the reviewer's model or effort. |
| 16–18 | `list_recent_codex_threads`, `list_codex_threads_since`, `search_codex_threads` | X4 and X5. Search matches titles only. |
| 19 | `get_codex_thread_lineage` | Because of X5, an overloaded parent read looks like a deleted parent, and the chain is silently cut short (`thread_helpers.py:236-246`). |
| 20 | `list_codex_turns` | Fine apart from the cross-cutting gaps. |
| 21 | `compact_codex_thread` | Returns `None` as soon as Codex accepts. There is no way to wait for or confirm the compaction, and closing the host right afterwards kills it silently (its own docstring says so). |
| 22 | `delete_codex_thread` | No soft-delete (archive) alternative, and no check for forks or subagent threads whose `parent_thread_id` would dangle. |
| 23 | `get_codex_goal` | Fine. |
| 24 | `run_codex_goal` | Failures from the inner spawn are labelled `spawn_codex_thread`, not `run_codex_goal` (`skill_functions.py:105`), which misattributes telemetry. |
| 25 | `list_codex_skills` | Takes a single `cwd`, and cannot force a reload. |
| 26 | `run_codex_skill` | Takes `prompt: str` only, so no images or mentions can go with a skill, and only one skill per run. The skill is resolved against `thread.cwd` while `turn.cwd` may differ. Its errors are labelled `spawn_codex_thread`, as in #24. |
| 27 | `run_codex_openai_docs` | Inherits everything from #26. |
| — | the 6 one-shot functions | Each starts and initializes a whole app-server process per call. That is acceptable but should be documented as unsuitable for loops. |

## C.10 Conversation finding: missed first-class Codex features and settings (P0/P1/P2 and S1–S10) (checked against the codex-cli 0.163.0 schema)

Full evidence is in `scratchpad/codex-research/codex-gap-report.md`. I re-checked three claims myself:
- goal runs ignore `turn.*` and `output_schema`, because `REJECTED_FIELDS` has no spawn or goal entry;
- `CodexReasoningEffort` stops at `xhigh`;
- `TurnStartParams.model_validate` silently drops `collaborationMode`.

### Settings gaps inside the existing functions
- [ ] **S1 (goal runs, including `run_codex_goal`):** `turn.*`, `output_schema` and `disabled_plugin_ids` are silently ignored, which breaks INV-27.
- [ ] **S2 (every turn):** effort is missing `max` and `ultra`.
- [ ] **S3 (fast mode):** `service_tier` is free text that is neither discoverable nor validated. Also missing: `serviceTierForTurn`, any tier info on `CodexModelInfo`, and any tier for reviews.
- [ ] **S4 (plan mode):** `collaborationMode` cannot be sent. The stable-only SDK models drop it, so it has to be added after validation, the same way `dynamicTools` is.
- [ ] **S5 (server requests):** every request other than approvals and tool calls is answered with `{}`. That is not schema-valid for `item/tool/requestUserInput`, `mcpServer/elicitation/request` or `item/permissions/requestApproval`.
- [ ] **S6 (`fork_codex_thread`):** no `before_turn_id` and no `defer_goal_continuation`.
- [ ] **S7 (`start_codex_review`):** cannot be configured at all: no model, effort, tier or limits.
- [ ] **S8 (sandbox):** no `networkAccess` or `writableRoots`, and no permission profiles.
- [ ] **S9 (deprecations):** detached review delivery, the friendly/pragmatic personalities and full-history `thread/read includeTurns` are deprecated in 0.163, and fork and review read-back both rely on the last one.
- [ ] **S10 (SDK pin):** `openai-codex>=0.162.1,<0.163.0` is one version behind the CLI.

### Proposed new functions, ranked

**P0**
- `update_codex_thread_settings` → `thread/settings/update`.
- Plan mode: `list_codex_collaboration_modes`, `run_codex_plan`, and `collaboration_mode` on turn settings.
- `stream_codex_turn(handle) -> AsyncIterator[CodexTurnEvent]`.
- An approval / user-input handler on `CodexHost`, which also fixes S5.
- `wait_codex_turns(handles, return_when=...)`.
- `list_codex_mcp_servers` → `mcpServerStatus/list`.

**P1**
- `update_codex_turn_settings`.
- Memories: `set_codex_thread_memory_mode`, `get_codex_memory_status`, and `reset_codex_memories` (never a tool).
- `start_codex_side_chat`.
- `create_codex_worktree`.
- Goal control: pause, resume, edit and clear.
- `archive_codex_thread` / `unarchive_codex_thread`, `revert_codex_thread`, `rename_codex_thread`, `inject_codex_items`.
- Queue: `queue_codex_message` and the `thread/queue/*` methods.
- Background terminals: `list_codex_background_terminals` and `clean_codex_background_terminals`.
- `search_codex_thread_content`, `list_codex_child_threads`, `forget_codex_turns` (eviction).

**P2**
- `open_codex_thread_in_app` (deep link).
- Recap, voice, hooks, feedback, marketplaces, and `process/spawn` (never a tool).

