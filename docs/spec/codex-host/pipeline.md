---
slug: codex-host
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host
branch: feat/codex-host
base_commit: 678136bd4358bcf9f120504cecd818d36a3d46fe
pr:
until: none
started: 2026-10-13 00:45 UTC
---

# Pipeline: CodexHost: small atomic Codex functions with one agent tool per function

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-13 00:45 UTC | 2026-10-13 01:27 UTC | reports/S0-scout.md | base_commit 678136bd; code-map.md, 4 sections |
| S1 spec + review | in progress | 2026-10-13 01:35 UTC | | reports/S1-spec-author.md, reports/S1-spec-review.md, reports/S1-spec-review-r2.md | spec r1 a1ee792a → review r1 SOUND WITH FIXES (2B/7M/4m) → spec r2 b38d573a (all 13 applied); scoped review round 2 launched 07:40 UTC |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Parallel run
- **Sibling pipeline:** `claude-host`, in worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host` on branch `feat/claude-host`, from the same base commit. Each run follows the shared-file contract in its request.md §C.
- **The orchestrator checks byte-identity** of `vidbyte/harnesses/native/__init__.py` in both PRs. Its SHA-256 must be `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.

## Decisions the orchestrator made
- 2026-10-13 00:45 UTC — **Scope is CodexHost's ★ set only** (14 rows, 15 functions), plus the spawn request, the host class, the error mapper, one tool per function, the toolset and contract tests. *Why:* R3's legend says "★ = first PR for that host", and Prompt 4 asks for one PR per host (request.md §C).
- 2026-10-13 00:45 UTC — **Answers to the R3 "Needs you" questions.**
  - Q1 (⚑ functions): default, left out.
  - Q3 (installed binary): default.
  - Q2 (sequential PRs): superseded by Prompt 4's parallel PRs.
  *Why:* Prompt 4 ("great, …") is the reply to R3's card.
- 2026-10-13 01:30 UTC — **Revised the shared-file contract in request.md §C after S0.**
  - `native/__init__.py` now carries the A001 seven-field header (fixed bytes, SHA above).
  - No `native/README.md`.
  - No shared test files; tests go in per-host feature packs, which carry no `__init__.py`.
  *Why:* the S0 scout's C1 finding. A001 has no empty-file exemption, and its baseline (643) has no headroom. No lint rule requires a folder README.
- 2026-10-13 01:30 UTC — **Environments.**
  - The dedicated Semgrep venv `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1` (semgrep 1.170.1) is created and shared by both runs.
  - This run's Python venv for tests and gates is `C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host`, created at S2.
  *Why:* never pip-install into the global Python. Its editable `vidbyte` install points at the canonical checkout, and two parallel runs would clobber each other. Semgrep breaks next to the SDK's mcp 2.x.

- 2026-10-13 05:32 UTC — **An API session limit (HTTP 429) killed the S1 author** after it had written spec.md but before it committed. Once the limit reset, the orchestrator resumed the same agent with SendMessage. The resume message carried three corrections:
  - export lists take sorted inserts;
  - S045 forbids a `timeout` parameter on async methods;
  - every raw `request` call must stay S012-compliant without suppressing the rule.
- 2026-10-13 05:55 UTC — **S1 r1 spot-check passed.** The frontmatter `base_commit` and `worktree` match, there are 18 `## §` sections, §12.3 (lines 1190–1222) has 28 numbered rows, and the last commit is `docs(spec): add codex-host spec r1` (a1ee792a).
- 2026-10-13 05:55 UTC — **Two revisions to request.md §C, the shared-file contract,** with the same change made to the ClaudeHost request.md:
  1. The export-list bullet now says "insert only your own entries, in the file's own sorted order; never reorder or remove existing ones", replacing "append-only".
  2. A new bullet fixes byte-identical text for the `REPO_MAP.md` native section and the `vidbyte/harnesses/README.md` bullet. The bullet block is byte-identical in both request.md files (SHA-256 `6da4fa77…51277b0`).
  *Why:* spec r1 §12.5 proposed its own REPO_MAP text and asked the orchestrator to give PR B identical text, but ClaudeHost spec r1 had different text at the same two insertion points, which would conflict at the second merge. Spec r1's REPO_MAP text also broke the field guide's `agents-md-map.md` rule, which forbids backtick-quoted names and child-folder paths in a folder description. The fixed text is host-neutral and follows that rule. The spec author must adopt it in revision.
- 2026-10-13 06:35 UTC — **Review round 1: SOUND WITH FIXES, 13 findings.**
  - Every finding (R-1 to R-13) went to the author; none is tagged `[scope-adding]`, and none was declined.
  - They were forwarded by report path and line range (lines 1–278 of reports/S1-spec-review.md), not pasted into the message.
  - R-4, R-5 and R-6 change §8, §9 and §10, so a scoped round 2 follows the r2 revision.
- 2026-10-13 06:35 UTC — **R-5: the orchestrator accepted the fail-closed fix.**
  - The `approvals_reviewer` field and its `USER` member stay, because they are R3's spawn-field vocabulary.
  - Validation rejects `USER` with the spec's unsupported-combination configuration code. Its next step says that answering approvals in code comes with `set_codex_approval_handler`, which R3 marks ✗ and which is not in this PR.
  - The handler is not built (rule 11).
  *Why:* openai-codex 0.162.1 has no decline decision, and its default handler answers `accept`. In this PR, a `USER` reviewer with no handler would silently approve every escalation, the opposite of what that setting asks for. Rejecting the value narrows nothing the user can safely use today.
- 2026-10-13 06:35 UTC — **R-9: new records go in a new domain module,** not into the 1,205-line `vidbyte/lib/dataclasses/codex.py`. *Why:* AGENTS.md:31 says to split before adding more once a file heads toward four digits. So this is repo-forced, and Q-1 is no longer a question.
- 2026-10-13 07:40 UTC — **r2 spot-check passed.** `revision: 2`, §16 holds a disposition row for each of R-1 to R-13, there are 18 sections and 28 §12.3 rows (18 CREATE, 10 MODIFY), and the commit is `docs(spec): revise codex-host spec r2 (apply review round 1, R-1 to R-13)` (b38d573a).
  - The spec contains the request.md §C REPO_MAP paragraph and README bullet byte for byte (checked with `grep -F`).
  - The orchestrator committed the author's r2 report addendum.
- 2026-10-13 07:40 UTC — **Launched review round 2 (the last allowed), scoped to what r2 changed and what depends on it.** That covers §8, §8.5, §9.1–9.4, §10 T-3/T-6, §12, and the new INV/EC items. It also covers three calls the author made beyond the review:
  - INV-25/EC-74: a failed goal-budget request cancels the goal;
  - Q-3 resolved instead of left open;
  - the §11 hash command form.

## User replies (verbatim)
- none yet

## Niche facts accumulated (carried into every later briefing)
- **A001** requires a seven-field header (PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS, TESTS) in every tracked `.py`: tests, `__init__` files, everything. Its baseline is 643 with no headroom.
  - Copy the header form of `vidbyte/tools/toolsets/coding.py:1-12`.
  - The `vidbyte/tools/builtins/sessions/` modules fail A001, S062 and S017, so copy their structure, not their headers, descriptions or error strings.
  *source:* S0 code-map §2.6, §4 C1–C2.
- **S012** (baseline 0) fails any call in `vidbyte/**` to a method named `request` (and similar) without a `timeout=` or `timeout_seconds=` keyword. openai-codex's `request(method, params, *, response_model)` has no timeout parameter, and `AsyncCodex._client` is private (api.py:317). *source:* S0 §4 C3–C4.
- **Operations with no high-level wrapper in openai-codex 0.162.1:**
  - `thread/fork` takes `last_turn_id` (fork through that turn, inclusive; it must not be running) and a bool `exclude_turns` (v2_all.py:9859-9904), but `AsyncCodex.thread_fork` exposes neither. `CodexForkSettings` is an agent-fork record with no turn id.
  - `token_budget` exists only in the raw `ThreadGoalSetParams` (v2_all.py:9938). An active goal starts its own turn on an idle, persisted thread and blocks `_start_turn` (client.py:549-671).
  - Also without a wrapper: rate limits, sandbox readiness, `review/start`, `approvalsReviewer` user/guardian, and `disabledPluginIds`.
  *source:* S0.
- **The message router drops events for a turn with no subscriber** (_message_router.py:196-206). Only `_start_turn` pre-registers, so a `review/start` handle created later can miss `turn/completed` and hang. Each handle's stream can be read only once. *source:* S0.
- **`codex_bin`:** the empty default means the bundled binary, and a set value must be an existing path (client.py:176-186). The PATH `codex` is an npm launcher whose package metadata says 0.162.1, not request.md's 0.161.0 (not executed). The Windows precedent resolves launchers with `shutil.which` (tools/mcp/transport.py:197-201). *source:* S0.
- **Settings and failure codes:**
  - The existing settings carry only `approval_mode` ("", auto_review, deny_all). `developer_instructions`, `approvals_reviewer`, `disabled_plugin_ids` and `name` are new fields, and `ThreadStartParams` has no `name`.
  - New `CODEX_*` codes go after failure.py:46, each with a classification row in `vidbyte/lib/constants/codex.py:95-174`. A test enforces the rows.
  *source:* S0.
- **Permissions are not enforced everywhere:**
  - openai-codex auto-accepts command and file-change approvals by default (client.py:833-839).
  - The MCP tool registry runs tools without a `PermissionPolicy` check (mcp_server/handlers.py:88).
  - `BaseAgent` gives each agent its own tool copy only for classes in explicit lists (agents/base.py:421-482). `agents/base.py` is shared with the ClaudeHost PR, so any edit there must be minimal and append-only.
  *source:* S0.
- **Design (spec r1, approach B).**
  - `CodexHost`, in `vidbyte.harnesses.native.codex`, is an async context manager that owns one Codex app-server.
  - It calls openai-codex's public sync `CodexClient` through `asyncio.wait_for(asyncio.to_thread(...), CODEX_HOST_REQUEST_TIMEOUT_SECONDS=300)`.
  - Typed client methods carry the full params.
  - Five raw calls go through `request_with_retry_on_overload`. The two that spend money (`review/start`, the goal budget set) get a single attempt (`CODEX_HOST_SINGLE_ATTEMPT`).
  - Runner-up A (AsyncCodex plus the private `_client`) was rejected: it uses a private attribute, and its raw `request` fails S012.
  - Budget: 17 new files, 30 classes, 15 records, 13 enums, 0 dependencies, 0 root exports.
  *source:* S1 author.
- **Contract names:**
  - `CodexHost`, `CodexToolScope`, `CodexHostTools`;
  - `CodexTurnSnapshot` (not `CodexTurnOutcome`, which already exists);
  - `CodexTurnStatus.RUNNING = "inProgress"`;
  - new failure codes directly after `CODEX_RUN_OPTION_UNSUPPORTED`.
  *source:* S1 author.
- **Test seam.** Patch the module attribute `vidbyte.harnesses.native.codex.connection.CodexClient` before entering the host; it is imported lazily in `__aenter__`. Also patch `shutil.which` and `sys.platform`. The fake needs no `request` or `model_list`, and the five raw calls go through `request_with_retry_on_overload`, keyed by method name. *source:* S1 author.
- **S012 matches any call to a name `request`, bare or as a method.** Passing `client.request` uncalled to `to_thread` is forbidden too. A002 `# @intent` comes next: it applies to identifiers containing request, retry, attempt, fallback, provider and similar words. *source:* S1 author.
- **The S1 author's least-sure assumptions:**
  - A-1: the Windows npm `.cmd` launcher works and stops at close.
  - A-2: a goal can start before the first turn.
  - A-3: usage totals are cumulative.
  - A-6: setting only the budget leaves the goal alone.
  - A-7: approvals arrive only when the reviewer is `user`.
  - A-12: the version reported at `initialize` can be parsed.
  Q-1 to Q-9 all have defaults:
  - Q-1: no split of the 1,205-line dataclass module.
  - Q-2: minimum CLI version 0.151.0.
  - Q-3: accept approvals.
  - Q-4: no root exports.
  - Q-5: refusal cap, default `None`.
  *source:* S1 author.
- **Line endings.** `core.autocrlf=true` is set and there is no root `.gitattributes`, so working copies are CRLF. Hash `native/__init__.py` from the blob (`git show HEAD:<path>` or `git cat-file -p :<path>`): the LF blob hash is `0374a2c8…`, and the CRLF working-copy hash is `fbf12a15…`. *source:* S1 reviewer R-8.
- **S054 (ruff S105, zero headroom: baseline 3, current 3).** S105 flags a string literal assigned to, or compared with, any name, attribute or subscript key with an `_`-separated segment `token`, `secret`, `pass`, `pwd` or `password`.
  - Safe: `tokens`, `tokenBudget`, `CODEX_USAGE_UPDATED_NOTIFICATION`.
  - Unsafe: `GOAL_TOKEN_BUDGET_DESCRIPTION`.
  - The three existing findings are `token_budget.py:28`, `compaction/base.py:28` and `workflows/contracts.py:73`.
  *source:* S1 reviewer R-1.
- **One reader thread.** openai-codex's `_reader_loop` (`client.py:863-881`) answers server requests synchronously on its single reader thread, so a slow dynamic tool stalls every notification and response on that app-server for up to 300 s. *source:* S1 reviewer R-3.
- **Closing on Windows.** `shutil.which("codex")` finds the npm `codex.cmd`. The chain is cmd.exe, then node `codex.js`, then `codex.exe` with stdio inherited. `CodexClient.close()` terminates cmd.exe only (`client.py:291-297`, plain Popen, no job object). *source:* S1 reviewer R-4.
- **Not public API.**
  - `CodexClient` is not in `openai_codex.__all__`; only `CodexConfig` is imported from `.client`.
  - Goal operations return the private `_GoalOperationState`.
  - The SDK's `ApprovalMode` offers only `deny_all` and `auto_review`, and 0.162.1 has no decline decision value.
  *source:* S1 reviewer.
- **Tool-call timeout.** `CodexToolCallHandler.handle` returns "Tool call timed out after 300 seconds." at `CODEX_TOOL_CALL_TIMEOUT_SECONDS`. `ToolExecutor` has no timeout of its own, so the wait tool's clamp must stay below 300 s. *source:* S1 reviewer R-7.
- **Precedent for a dedicated executor:** `openai_codex/async_client.py:53-54` uses `_TURN_START_EXECUTOR = ThreadPoolExecutor(...)`, and its cancelled-start cleanup runs on daemon threads (:258-261, :283-286). *source:* S1 reviewer R-6.
- **Stale and checked facts.**
  - The installed binary reports `codex-cli 0.162.1`; request.md's "0.161.0" is stale.
  - No test enumerates `ComponentRegistry`.
  - No lint rule caps file length.
  *source:* S1 reviewer.
- **Contract import paths (spec r2).** New records come from `vidbyte.lib.dataclasses.codex_host`. Settings records and helpers still come from `vidbyte.lib.dataclasses.codex`, which is not edited.
  - The new module's `__all__` is a list literal. Copying `codex.py`'s `Codex*` comprehension would re-export the imported records.
  - ruff `F` (unused imports) is in the lint selectors, so `codex_host.py` must not import `CodexClientSettings`.
  *source:* S1 author r2.
- **Executor and close constants.**
  - Host calls run on a host-owned executor, `CODEX_HOST_WORKER_THREADS=32`; there is no `to_thread`.
  - `close()` runs on a daemon thread, with 5 s and 10 s bounds.
  - The wait clamp is 240 s, below the 300 s tool-call cancel bound.
  - The connection module reads the request-timeout and close constants at call time, and the worker count when it builds the executor.
  *source:* S1 author r2.
- **Close order (INV-7):** finalize the turns, send each a single bounded interrupt, close the client on a daemon thread, then shut the executor down. *source:* S1 author r2.
- **A PowerShell trap.** Windows PowerShell 5.1 changes bytes piped between programs, so the `git cat-file | python` form prints a wrong hash there. The §11 hash command uses a Python `subprocess` form, which gives the same hash in both shells. *source:* S1 author r2 (verified).
- **openai_codex must load lazily.** Nothing reachable from `import vidbyte`, or from `vidbyte.tools.builtins` (which the YAML component registry scans), may import openai_codex at module level. The precedent is `CodexTransport._load_sdk` (transport.py:215-259). CI installs only `.[dev]`, so SDK-dependent tests skip there (`skipUnless`). The global Python 3.11 has openai-codex 0.162.1. *source:* S0.
