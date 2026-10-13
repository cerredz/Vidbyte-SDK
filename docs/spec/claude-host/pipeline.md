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
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

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
