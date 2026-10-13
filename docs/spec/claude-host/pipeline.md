---
slug: claude-host
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host
branch: feat/claude-host
base_commit: 678136bd4358bcf9f120504cecd818d36a3d46fe
pr:
until: none
started: 2026-10-13 00:45 UTC
---

# Pipeline: ClaudeHost: small atomic Claude Code functions with one agent tool per function

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-13 00:45 UTC | 2026-10-13 01:35 UTC | reports/S0-scout.md | base_commit 678136bd; code-map.md, 4 sections |
| S1 spec + review | in progress | 2026-10-13 01:45 UTC | | reports/S1-spec-author.md, reports/S1-spec-review.md | spec r1 21a947a7 (18 sections, §12.3 31 rows); review r1: SOUND WITH FIXES, 3 Blockers, 3 Majors, 4 Minors; author revising to r2 |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 1/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Parallel run
- **Sibling pipeline:** `codex-host`, in worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host` on branch `feat/codex-host`, from the same base commit. Each run follows the shared-file contract in its request.md §C.
- **The orchestrator checks byte-identity** of `vidbyte/harnesses/native/__init__.py` in both PRs. Its SHA-256 must be `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.

## Decisions the orchestrator made
- 2026-10-13 00:45 UTC — **Scope is ClaudeHost's ★ set only** (14 rows, 15 functions), plus the spawn request, the host class, the error mapper, one tool per function, the toolset, contract tests, and the new `claude` extra. *Why:* R3's legend says "★ = first PR for that host", and Prompt 4 asks for one PR per host (request.md §C).
- 2026-10-13 00:45 UTC — **Answers to the R3 "Needs you" questions.**
  - Q1 (⚑ functions): default, left out, so there is no `_send_control_request`.
  - Q3 (installed `claude` as `cli_path`): default.
  - Q2 (sequential PRs): superseded by Prompt 4's parallel PRs.
  *Why:* Prompt 4 ("great, …") is the reply to R3's card.
- 2026-10-13 01:40 UTC — **Revised the shared-file contract in request.md §C after S0.**
  - `native/__init__.py` now carries the A001 seven-field header (fixed bytes, SHA above).
  - No `native/README.md`.
  - No shared test files.
  - Export lists take inserts in sorted position, never reorders.
  *Why:* both scouts found that A001 has no empty-file exemption and its baseline (643) has no headroom. This scout also found that I001 and the contract generator keep the lists sorted, so "append-only" was inaccurate. The CodexHost request.md got the same `native/__init__.py` revision; its export-list wording is carried in briefings.
- 2026-10-13 01:40 UTC — **Environments.**
  - The dedicated Semgrep venv `C:/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1` (semgrep 1.170.1) is shared by both runs.
  - This run's Python venv is `C:/Users/422mi/vidbyte-repos/.venvs/sdk-claude-host`, created at S2 with the `claude` extra once it exists.
  *Why:* never pip-install into the global Python. Its editable `vidbyte` install points at the canonical checkout, and claude-agent-sdk could move the global `mcp` version under the other run.

- 2026-10-13 03:35 UTC — **S1 r1 spot-check passed.** The frontmatter `base_commit` and `worktree` match, there are 18 `## §` sections, §12.3 (`### 12.3 File-by-file actions`, line 1087) has 31 numbered rows, and the last commit is `docs(spec): add claude-host spec r1` (21a947a7). The orchestrator committed the author's untracked report with this pipeline update.
- 2026-10-13 03:35 UTC — **Checked the failure.py insertion spots against the shared-file contract.** At the base commit, `CONFIGURATION_INVALID_ARGUMENT` is line 34, the `CODEX_*` block runs from line 35 to line 46, and `CODEX_RUN_OPTION_UNSUPPORTED` (line 46) is last.
  - Spec r1 puts the `CLAUDE_*` block between lines 34 and 35.
  - CodexHost appends after line 46.
  - Lines 35–46 are untouched by both, so the second merge has no conflict there.
- 2026-10-13 05:30 UTC — **An API session limit (HTTP 429) killed the S1 reviewer** before it wrote its report. Once the limit reset, the orchestrator resumed the same agent with SendMessage rather than relaunching it.
- 2026-10-13 05:40 UTC — **Review round 1: SOUND WITH FIXES, 10 findings.**
  - Every finding (R-1 to R-10) went to the author; none is tagged `[scope-adding]`, and none was declined.
  - They were forwarded by report path and line range (FINDINGS, lines 23–186 of reports/S1-spec-review.md), not pasted into the message, to keep the orchestrator's context small. The author reads the verbatim text from disk.
  - The orchestrator added one instruction under rule 11: R-2's bounded stop after an interrupt is a module constant, not a new spawn-request field.
  - R-2, R-3 and R-5 change §8, §8.5, §9.2 and §10, so a scoped round 2 follows the r2 revision.

## User replies (verbatim)
- none yet

## Niche facts accumulated (carried into every later briefing)
- **A001** requires a seven-field header (PURPOSE, ROLE IN CODEBASE, ARCHITECTURE NOTE, COMMON MODIFICATION PATTERNS, KNOWN EDGE CASES, RELATED DOCS, TESTS) in every tracked `.py`, tests included. The baseline is 643 with no headroom. Copy the header form of `vidbyte/tools/toolsets/coding.py:1-12`. *source:* S0 code-map §1.6, §4.1.
- **Other rules likely to bite:**
  - A002 `# @intent` markers near identifiers such as request, permission, mcp, fallback, persist;
  - A007 (any literal, even 0, next to limit/timeout/budget names);
  - C008 (new validators outside `validation.py`);
  - S017 (no `str(exc)` into errors);
  - S045 (`async def` with a `timeout` parameter);
  - S039 (`asyncio.Lock` banned);
  - S062 (adjacent string literals);
  - S053/B023;
  - A003 (only if errors go in `lib/errors`).
  The lint final line reads `SDK-LINT: PASS`, not AGENT-LINT. *source:* S0.
- **No Claude record, enum, failure code, extra or adapter exists today.** Neither the repo nor claude-agent-sdk 0.2.165 has a max-output-token env var. *source:* S0.
- **CLI selection:** `_find_cli` picks the bundled CLI 2.1.294 before PATH, so `cli_path` must be passed explicitly. `claude_code_version` in the initialize response is optional. *source:* S0.
- **CI and the package smoke install only `.[dev]`, never extras.** Tests must fake the SDK at one lazy-import seam, as `tests/test_codex_tools.py:298-312` does, and skip real-SDK tests when `importlib.util.find_spec` returns None. *source:* S0.
- **How the SDK reports results and failures:**
  - During a live client turn, budget and turn caps arrive as `ResultMessage(is_error, subtype)`, not `ResultError`.
  - `ProcessError`'s stderr is a placeholder.
  - `MessageParseError` is not exported.
  - `fallback_model` is a single string.
  - `load_timeout_ms` is the session_store timeout, not process start.
  - Plugins are local folders only.
  - `system_prompt=None` sends an empty prompt.
  - One `RateLimitEvent` covers one window and is sent only when the status changes.
  - Python's `query()` sends no priority, and the parser drops `queued_turn_count`.
  *source:* S0.
- **Agent lifetime:**
  - `agents/base.py:421-490` binds tools per agent through hard-coded class lists, and any `bind_session` attribute gets called with a Vidbyte Session.
  - `BaseAgent.run()` calls `asyncio.run` on every call and closes subprocesses at the end, so a live session cannot survive from one sync run to the next.
  - The runtime's `wait_for` timeout can orphan the claude child.
  - `agents/base.py` is shared with the CodexHost PR, so any edit there must be minimal.
  *source:* S0.
- **Session history functions are synchronous file readers.** They may run `git worktree list` with a 5 s timeout (`_internal/sessions.py:388-413`), so they block the event loop when called from `async def` tools. *source:* S0 §4.1 item 31.
- **The MCP server runs tools with no `PermissionPolicy`,** so WRITE tools are ungated over MCP. *source:* S0.
- **Contract names (spec §4, §8.5).** Rename none of them.
  - `ClaudeHost`.
  - `ClaudeSpawnRequest`, with 58 fields in §9.2 order.
  - `ClaudeSessionHandle`, `ClaudeTurnResult`, `ClaudeUsageSnapshot`, `ClaudeTurnOutcome`.
  - `ClaudeOperationError(reason, *, failure_code, operation, next_step)`.
  - `ClaudeTools(host, request=None)`.
  - Tools are named `<Verb>Claude<Noun>Tool`.
  - There are 15 coroutines, 15 tools, and 16 `claude.*` codes.
  *source:* S1 author.
- **Test seam:** `mock.patch.object(ClaudeSdkLoader, "load", return_value=<fake ClaudeSdkTypes>)`, with `ClaudeSdkLoader` in `vidbyte/harnesses/native/claude/sdk.py`. Copy the pattern of `tests/test_codex_tools.py:264-319`. Skip real-SDK tests when `find_spec("claude_agent_sdk")` is None. *source:* S1 author.
- **Sibling:** `vidbyte/agents/codex/` is a pattern only. The tool layout copies `vidbyte/tools/builtins/sessions/`, and the toolset copies `vidbyte/tools/toolsets/coding.py`. *source:* S1 author.
- **Errors:** records raise `ClaudeOperationError` with `configuration.invalid_argument` or `configuration.unsupported_combination` and operation `validate_request`, never `ConfigurationError`. Tool wrappers return an error `ToolResult` and never raise. *source:* S1 author.
- **D-28:** a `ResultMessage` ends the turn only when its `origin` is absent or `human`. Other origins only update cumulative cost (AC-36, EC-56). *source:* S1 author.
- **Design (spec r1).**
  - Each turn owns exactly one `claude` process, from connect to its result, inside the host.
  - Spawn returns a handle immediately.
  - Steer interrupts the turn and resends the message after the result.
  - The time budget is a watchdog that interrupts.
  - Readiness and models read one initialize probe.
  - History and fork read session files and start no process.
  *source:* S1 author.
- **The S1 author contradicts S0 on three facts.** It says it verified them in the installed CLI 2.1.296, so the minimum CLI version is 2.1.296 and `cli_path` comes from `shutil.which("claude")`.
  - The CLI reads the env variable `CLAUDE_CODE_MAX_OUTPUT_TOKENS`. The SDK still has no field for it.
  - `--fallback-model` accepts a comma-separated list.
  - Plugins can come from a URL or a .zip.
  These `extra_args` flags exist: `file`, `restricted`, `autocompact`, `name`, `agent`, `bare`, `safe-mode`, `no-session-persistence`, `worktree`, `plugin-url`.
  *source:* S1 author report §3. Not yet re-verified by a reviewer.
- **The S1 author's least-sure assumptions:**
  - A-8/A-9: steer and interrupt run concurrently on one client.
  - A-6: the initialize probe is free.
  - A-2: with no prompt handler, a tool needing permission is denied.
  - A-3: `--no-session-persistence` works in SDK mode.
  - A-1: images are accepted over `query`.
  - A-13: `--bare` with no API key reports `apiKeySource` absent or `none`.
  *source:* S1 author.
- **The rule most likely to be violated is A001.** After it, in order:
  - A002;
  - A007;
  - C002 and C008 (bool guards written once in `_ClaudeFieldRules`; no verb+primitive helper names);
  - S012 (name no method `request`);
  - S045 (parameters are named `timeout_seconds`).
  *source:* S1 author.
- **Line endings.** `core.autocrlf=true` is set in the system gitconfig, and there is no root `.gitattributes`, so every tracked file is stored with LF and checked out with CRLF.
  - Any test that checks exact file bytes must hash the committed blob, or the bytes after converting line endings to LF.
  - For byte-exact files the repo uses a `.gitattributes` in that folder, for example `contracts/.gitattributes` with `*.json text eol=lf`.
  *source:* S1 reviewer R-1.
- **S054 (ruff S105, hardcoded passwords) has zero headroom:** baseline 3, current 3. A string constant whose name contains TOKEN, such as `CLAUDE_TOKEN_SOURCE_NONE = "none"`, trips it, and so does a comparison like `token_source != "none"`. `CLAUDE_MAX_OUTPUT_TOKENS_ENV` does not. *source:* S1 reviewer (ruff 0.16.4, run with `--no-cache --isolated`).
- **Permissions without a prompt handler (CLI 2.1.296).** `--permission-prompts host|none` defaults to `host`, and `none` means a local deny. Without `can_use_tool`, the SDK answers a permission request with an error control_response (`_internal/query.py:590-591`). Permission mode `default` is right: the help lists `manual`, which is an alias of `default`. *source:* S1 reviewer.
- **Every interrupt kills background tasks,** and so does every steer, because steer interrupts. The Python SDK never sends `perTaskStopAffordance` (TS d.ts:4571). *source:* S1 reviewer.
- **Results from a crash or a startup error may report zero cost:** `total_cost_usd` and `modelUsage` can come back as zero (TS d.ts:5738/5746). *source:* S1 reviewer.
- **Finding the CLI on Windows.** The SDK's `_find_cli` prefers a native exe and then `~/.local/bin/claude.exe`, and refuses `.cmd`/`.bat` shims with a `CLIConnectionError` at connect. On this machine `which("claude")` returns `C:\users\422mi\.local\bin\claude.EXE`. *source:* S1 reviewer.
- **The package smoke imports only the root package,** so spec r1's NFR-1 claim about it was false. *source:* S1 reviewer R-7.
- **C016 is unaffected by the new extra and the submodule exports.** It reads only the root `__all__` and the pyproject name and version, so `contracts/sdk-public-api.json` does not change. New packages ship through `packages.find`. *source:* S1 reviewer.
