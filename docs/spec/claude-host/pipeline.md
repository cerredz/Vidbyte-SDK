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
| S1 spec + review | done | 2026-10-13 01:45 UTC | 2026-10-13 08:15 UTC | reports/S1-spec-author.md, reports/S1-spec-review.md, reports/S1-spec-review-r2.md | spec r3 ba522bba, status: approved; 2 review rounds (SOUND WITH FIXES ×2), 18 findings applied, 0 disputed |
| S2 tests | done | 2026-10-13 08:20 UTC | 2026-10-13 15:40 UTC | reports/S2-test-author.md | S2_HEAD 9a8ecc3c (tests 8e116bc7, proof 9a8ecc3c); 165 tests in tests/features/claude_host/, all red on `ModuleNotFoundError: vidbyte.harnesses.native`; spec r4 55c233bf pins the S2 open items; spec status: tests-written |
| S3 implement | in progress | 2026-10-13 15:45 UTC | | reports/S3-implementer.md | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

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
- 2026-10-13 06:00 UTC — **Fixed the shared doc text in request.md §C (commit 978ebfa5).** The `REPO_MAP.md` native section and the `vidbyte/harnesses/README.md` bullet now have fixed text that is byte-identical in both runs' request.md (bullet-block SHA-256 `6da4fa77…51277b0`).
  *Why:* the two specs inserted different text at the same two spots, which would conflict at the second merge. The CodexHost draft text also broke the field guide's `agents-md-map.md` rule.
  The author was told with a queued SendMessage and adopted the text in r2.
- 2026-10-13 06:25 UTC — **r2 spot-check passed.** `revision: 2`, §16 holds a disposition row for each of R-1 to R-10, there are 18 sections and 31 §12.3 rows, and the commit is `docs(spec): revise claude-host spec r2 (review round 1 fixes and fixed shared doc texts)` (ac39bb46). The orchestrator committed the author's r2 report addendum.
- 2026-10-13 06:25 UTC — **Launched review round 2 (the last allowed), scoped to the sections r2 changed.**
  - It covers §8 (D-4 interrupt grace, D-5 CLI lookup), §8.5, §9.1–9.3, §10 T-3, and §12.1/12.3/12.4/12.5, plus what depends on them: §6, §13, §14, and §15 A-2/A-3/A-17.
  - Anything still disputed after round 2 becomes a Q-n with its stated default.
- 2026-10-13 07:05 UTC — **Review round 2: SOUND WITH FIXES, 8 findings** (1 Blocker, 2 Majors, 5 Minors).
  - Round-1 findings R-1 and R-3 to R-10 are confirmed resolved. R-2 is half resolved: the turn always ends now, but the `claude` process can outlive it.
  - All eight went to the author for the final revision r3, forwarded by path (lines 1–187 of reports/S1-spec-review-r2.md). In the same message the author was told to set `status: approved`, since the two review rounds are the approval.
  - R-7's optional `[scope-adding]` control is recorded as a Q-n, default not built: passing external MCP configs as the path of a 0600 temp file.
  - The S1 review cap (2/2) is reached. Anything the author disputes becomes a Q-n with a stated default.
- 2026-10-13 08:15 UTC — **Spec r3 approved; spot-check passed.**
  - The frontmatter has `revision: 3` and `status: approved`.
  - §16 has round-2 rows for R-1 to R-8, and the author disputed none.
  - There are 18 sections and 31 §12.3 rows.
  - The commit is `docs(spec): revise claude-host spec r3 (review round 2 fixes, approved)` (ba522bba).
  The "Spec ready" summary was printed to the user, and the run continued to S2 without waiting, as the skill requires.
- 2026-10-13 08:15 UTC — **Every Q-n takes its stated default of No:**
  - Q-1: stop spawns on an `allowed_warning` rate-limit window.
  - Q-2: a permission gate on McpStudioServer.
  - Q-3: limit history tools to the request's cwd.
  - Q-4: clip long outputs.
  - Q-5: a handle scope per toolset.
  - Q-6: support `prompt_suggestions`.
  - Q-7: let the model pick model/effort.
  - Q-8: default caps after measuring memory.
  - Q-9: forget finished handles before close.
  - Q-10: root exports.
  - Q-11: pass MCP configs as a 0600 temp file.
  None of these is built.

- 2026-10-13 15:40 UTC — **S2 spot-check passed.**
  - All of AC-1..AC-40 are cited in test-plan.md.
  - The red run is quoted.
  - I re-ran `test_claude_host_stops.py` myself and got `23 failed in 0.77s`, with every failure `ModuleNotFoundError: No module named 'vidbyte.harnesses.native'`.
  - There are two commits and the tree is clean.
  *Why:* the S2 spot-check rule.
- 2026-10-13 15:40 UTC — **Sent the S2 open items to the spec author in Revision mode (r4) before S3,** as S2-1..S2-10. Lines 272–301 of the S2 report and lines 246–284 of test-plan.md were forwarded by path.
  - r4 (55c233bf) pins S2-1..S2-8 and S2-10 as D-29..D-33 plus rows 3/14, and makes S2-9 a stated limitation (EC-61).
  - I verified that only spec.md and the author report changed, that the §6.2 Proof column hashes the same before and after, and that there is no test diff since S2_HEAD.
  *Why:* the skill resolves spec defects before the implementer meets them. Loose wording would otherwise become private choices in S3.
- 2026-10-13 15:40 UTC — **Accepted the S2-7 pin but flagged it for S4 engineering.** Under the pin, a turn whose result is `success` but which saw a refusing rate-limit window ends FAILED `usage_limited`. An example is a `seven_day_opus` window on a Sonnet turn.
  *Why:* it follows r3's reviewed D-20 order (rate-limit row before the result rows), and no frozen test pins the opposite. Whether it is wrong output belongs to the adversarial review, not to me.
- 2026-10-13 15:40 UTC — **`vidbyte/lib/errors/base.py` is edited by both PRs, outside the request.md §C contract.**
  - This PR inserts `ClaudeOperationError` before `class ConfigurationError` (:235 at base).
  - CodexHost changes `CodexAgentError.__init__` (:129–156).
  The hunks are about 80 lines apart, so no merge conflict is expected. The sorted export inserts (`enums/__init__`, `tools/builtins/__init__`, `toolsets/__init__`) may conflict trivially at the second merge because the Claude* and Codex* names sit next to each other. That is resolved at the catch-up merge.
- 2026-10-13 15:40 UTC — **Three HTTP 429 session-limit interruptions so far** (~05:30, ~10:30 and ~15:00 UTC). Each time I checked the worktree state and resumed the same agent through SendMessage with what was on disk. No work was lost.

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
- **Contract names new in spec r2:**
  - `ClaudeProbe.locate_cli(cli_path, *, windows, home) -> str`;
  - constants `CLAUDE_INTERRUPT_GRACE_SECONDS` (30.0), `CLAUDE_INVALID_ARGUMENT_NEXT_STEP`, `CLAUDE_UNSUPPORTED_COMBINATION_NEXT_STEP`, `CLAUDE_EMPTY_INPUT_NEXT_STEP`, `CLAUDE_PRECONDITION_NEXT_STEP`;
  - enum member `ClaudeCliFlag.PERMISSION_PROMPTS`.
  *source:* S1 author r2.
- **Interrupt grace test seam:** patch `vidbyte.harnesses.native.claude.session.CLAUDE_INTERRUPT_GRACE_SECONDS`. Interrupt and steer fakes must emit a result after `interrupt()`, or every such test waits the full 30 s. *source:* S1 author r2.
- **The Windows CLI lookup is testable on Linux CI:** call `locate_cli(..., windows=True, home=<tmp>)` and patch `shutil.which` through the probe module. On macOS and Linux the lookup is only `which("claude")`. *source:* S1 author r2.
- **S054 forbids** assigning a string to, or comparing a string with, any name whose words include token, password, pass, pwd or secret. *source:* S1 author r2.
- **How the SDK closes a client.** `disconnect()` runs a shielded `_close_impl`, which cancels the read task (whose `finally` sends `end`) before `transport.close()`.
  - A plain `task.cancel()` or `asyncio.wait_for` around it skips terminate/kill (`subprocess_cli.py:979-988`), so the process leaks.
  - The repo's cancellation-safe close pattern is `MultiAgentCleanup.shielded_close` (`vidbyte/agents/multi/cleanup.py:36-46`).
  *source:* S1 reviewer r2, R-1.
- **Interrupt and start timing.**
  - `Query.interrupt()` waits up to 60 s (`fail_after`), and closing never fails pending control requests.
  - The agent runtime's tool timeout is a plain `asyncio.wait_for` (`vidbyte/agents/runtime.py:1455`).
  - An unknown CLI flag fails `connect()` fast with `ProcessError` (`query.py:543-546`).
  - `open_process(user=...)` errors are wrapped as `CLIConnectionError`, so they map to `process_exited`.
  *source:* S1 reviewer r2.
- **Permission flag evidence.** CLI 2.1.296's `--help` treats non-TTY stdout as print mode. `sdk.d.ts:2018-2025` documents `permissionPrompts: 'none'` ("canUseTool is never called"), and `sdk.d.ts:5572` calls `permission_denials` authoritative. *source:* S1 reviewer r2.
- **Test isolation on this machine.** `~/.local/bin/claude.exe` exists, so a test that patches only `shutil.which` still finds the real CLI. Tests must also point `home` at a temp dir. *source:* S1 reviewer r2, R-8.
- **pytest 8.3.5 prints secrets in dataclass assertion diffs.** It picks fields by `compare` and prints their `repr`, so `repr=False` does not hide secrets there. Tests must not assert whole records that carry secrets. *source:* S1 reviewer r2.
- **`.venvs/lint-sdk` has ruff 0.16.4 and pytest 8.3.5.** Run S105 checks with `ruff --isolated --select S105,S106,S107`. Its regex uses underscore word boundaries: `CLAUDE_CREDENTIAL_SOURCE_FIELDS` passes, while `CLAUDE_TOKEN_SOURCE_FIELD = "..."` and `token_source = "..."` are flagged. *source:* S1 reviewer r2.
- **Closing and interrupting (spec r3).**
  - Each session has one close task that nothing cancels, awaited through `asyncio.shield`, following the `MultiAgentCleanup.shielded_close` pattern.
  - The terminal status, done, the session id and the cap slot are released only after the close finishes. The probe closes the same way.
  - Caller interrupts and steers run `interrupt()` in a task the session owns.
  - The grace timer is tied to the prompt being interrupted (prompt and result counters) and is cleared when that prompt's result arrives.
  - AC-25, AC-31 and AC-37 need a slow fake `disconnect()` that is never cancelled.
  *source:* S1 author r3.
- **Start failures.** A `ProcessError` or `CLIConnectionError` from `connect` maps to `CLAUDE_START_FAILURE_NEXT_STEP`, which points to `check_claude_ready`, never "Respawn". A steer whose message is discarded before its call returns raises `action.precondition_failed`. *source:* S1 author r3.
- **CLI lookup on POSIX** checks the SDK's six locations, held in `CLAUDE_POSIX_CLI_LOCATIONS`. `/usr/local/bin/claude` is absolute, so `home / entry` leaves it unchanged; on Windows it resolves to `C:\usr\local\bin\claude`. A request `cli_path` that screens to `""` reports `not_installed` and never falls back to the host's path. For the host-level empty-path case, tests patch `ClaudeProbe.locate_cli` to return `""`. *source:* S1 author r3.
- **Test layer (spec §13).**
  - pytest 8.3.5 with pytest-asyncio 1.3.0 (`pyproject.toml:78-81`, `--strict-config --strict-markers`, no `asyncio_mode`).
  - Most async tests use `unittest.IsolatedAsyncioTestCase`.
  - The feature pack is `tests/features/claude_host/`, with no `__init__.py` and unique basenames (`test_claude_host_<area>.py`).
  - A001 and S062 scan tests; ruff rules do not.
  - Run one file with `PYTHONPATH=$(pwd) python -m pytest tests/features/claude_host/test_claude_host_<area>.py`.
  *source:* spec r3 §13.
- **C016 is unaffected by the new extra and the submodule exports.** It reads only the root `__all__` and the pyproject name and version, so `contracts/sdk-public-api.json` does not change. New packages ship through `packages.find`. *source:* S1 reviewer.
- **S2 seam, from the test author.**
  - `mock.patch.object(ClaudeSdkLoader, "load", return_value=FakeClaudeSdk().types())`.
  - `ClaudeSdkTypes` has exactly the 21 §9.1 field names.
  - `load()` runs on every ★ call (row 3; r4 adds history and fork) and never at import.
  - `load()` must import `claude_agent_sdk` inside its `try`, because the missing-extra tests use `patch.dict(sys.modules, {"claude_agent_sdk": None})`.
  *source:* S2 test author.
- **The patch targets fix the module shapes.**
  - `vidbyte.harnesses.native.claude.session.CLAUDE_INTERRUPT_GRACE_SECONDS` must be a module global, read at call time.
  - The tests patch `vidbyte.harnesses.native.claude.probe.shutil.which`, so the probe must `import shutil` and call `shutil.which`.
  - `__aenter__` calls `ClaudeProbe.locate_cli(settings.cli_path, windows=sys.platform == "win32", home=Path.home())`, with keywords.
  *source:* S2 test author.
- **What the fakes model.**
  - A client stays connected until its `disconnect()` finishes. Until then the turn stays RUNNING and keeps its session id busy and its slot.
  - A disconnect is never cancelled.
  - A client whose `connect()` raised is still disconnected once.
  - The options fake rejects any keyword that 0.2.165 lacks.
  - The probe passes only `cli_path`.
  *source:* S2 test author.
- **SDK 0.2.165 `Literal` types omit `model_not_found` and `seven_day_overage_included`,** but its parser passes raw strings through. The fakes emit both, so map the raw strings. *source:* S2 test author.
- **The test most likely to catch a real bug** is `test_claude_host_stops.py::CloseTests::test_the_turn_ends_only_after_its_one_disconnect_finishes`. A natural pump marks the turn COMPLETED and frees the session id when the result arrives, before the disconnect has finished. *source:* S2 test author.
- **How to run the pack:** `PYTHONPATH=$(pwd) C:/Users/422mi/vidbyte-repos/.venvs/sdk-claude-host/Scripts/python -m pytest tests/features/claude_host`, from the worktree root. It needs no claude-agent-sdk. The fixtures import feature symbols lazily, so collection never errors. *source:* S2 test author.
- **r4 pins.**
  - D-29: overage is allowed only for `allowed` or `allowed_warning`; an absent value refuses.
  - D-30: a `continue_conversation` template without fork and N>1 gives `claude.session_busy`. A launch prompt gets spawn semantics.
  - D-31: a missing required value gives `invalid_argument`, and a forbidden pair gives `unsupported_combination`.
  - D-32: a history `OSError` gives `claude.session_not_found` plus a new `CLAUDE_HISTORY_READ_NEXT_STEP`. No new FailureCode.
  - D-33: cwds compare as `normcase(abspath())`.
  - Sandbox `network` is sent only with non-empty domain lists.
  - EC-61: there is no re-entry guard; calls after `aclose` stay refused.
  *source:* spec r4.
