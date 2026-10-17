---
slug: harness-browser-tools
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-browser-tools
branch: feat/harness-browser-tools
base_commit: 845a4d9bd5f144b1e083b5dc3c76bff17c75b235
pr:
until: none
started: 2026-10-16 21:43
---

# Pipeline: Browser tools for every harness thread — run_<harness>_with_browser

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | running | 2026-10-16 21:43 | | reports/S0-scout.md, reports/S0-vendor-scout.md | base_commit 845a4d9b |
| S1 spec + review | pending | | | | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 0/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-16 21:43 — Slug `harness-browser-tools`, not `browser-agent` — another session's unrelated run already owns `worktrees/vidbyte-sdk-browser-agent` (branch `feat/browser-agent`, "BrowserAgent: JevAgent-shaped agent"); no subagent may read it or use the name `BrowserAgent`.
- 2026-10-16 21:50 — Added a second S0 agent, a vendor scout, beside the code scout — the design rests on vendor behavior the code scout cannot see (Muse MCP schema entirely unverified; Grok compat/skills switches; opencode permission merge; exact tool names per package; whether Chrome survives a tree kill on Windows). It runs only free, local, model-free probes and writes `context/vendor-facts.md` + `reports/S0-vendor-scout.md`.
- 2026-10-16 21:50 — Harness scope = the three on main (grok, opencode, muse); Claude (#1044) and Codex (#1055) out because not on main; CodexAgent (`vidbyte/agents/codex/`) default not built, surfaced as Q-n — request.md §C KD-2 and Open questions.
- 2026-10-16 21:50 — The computer-use question (Prompt 3, second half) is answered to the user in the conversation, not built; a separate research agent (outside the pipeline, report in the session scratchpad) gathers evidence for it.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- `docs/` is opaque (AGENTS.md "Repository Map"); briefings name exact `docs/spec/harness-browser-tools/*` files. — *source:* AGENTS.md
- Python is `py -3.11`, not `python`; never export PYTHONPATH before an SDK `scripts/run_ci.py` run. — *source:* orchestrator memory (local env traps)
- SDK CI is dispatch-only: `gh workflow run CI --ref feat/harness-browser-tools` (+ "Static policy" workflow); merges need `--admin` (never merge — PR stays draft). — *source:* orchestrator memory (vidbyte release gates)
- Known-red on pristine main: a harness failure-code merge-base test and an MCP stdio flake; a real-bash test times out on GitHub runners. — *source:* orchestrator memory (SDK main known-red tests, 2026-10-16)
- Field guide: `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/init.md`; relevant entries: blocking-lint-invariants (modules under `vidbyte/harnesses/native/`), local-ci-verification (harness_threads surface test on feature branches), strict-config-dataclasses, declarative-config-resolution (registries), class-bound-helpers, cli-backed-source-integrations, comment-format, review-scope. — *source:* orchestrator
- Verified in conversation: Grok scans Claude + Cursor MCP sources by default (`~/.grok/docs/user-guide/07-mcp-servers.md:292`); `GrokThreadRun._environment` sets neither `GROK_CLAUDE_MCPS_ENABLED=0` nor `GROK_CURSOR_MCPS_ENABLED=0`. — *source:* request.md §C Implementation hints
- Verified in conversation: Playwright launches Chrome `detached: process.platform !== "win32"` (playwright-core 1.56.1 `processLauncher.js:108-111`) — POSIX group SIGKILL misses Chrome. — *source:* request.md §C
- The harness_threads tests pin closed sets exactly: `EXPECTED_EXPORTS`, the nine signatures, `EXPECTED_ENUMS`, the FailureCode tail (`test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, surface.py:176 — any appended FailureCode fails it everywhere; its merge-base `len == 120` part is the known-red one, only where origin/main exists), cause/next-step tables (exactly 30 codes), `lib.process.__all__ == [CliArgv, CliRunner, ProcessStopper]` (surface.py:212). New public names/codes REQUIRE the S2 test author to extend these pins; no one else may. — *source:* S0-scout (verified by orchestrator at surface.py:176-212)
- Error factory resolves codes only via `NATIVE_THREAD_FAILURE_CODES[(harness, problem)]` (`hostkit/errors.py:100`); `NativeThreadError.expected` hard-wired to "... returning a NativeThreadResult" (`lib/errors/base.py:601`); `check_error` asserts operation `{verb}_{harness}_thread`. — *source:* S0-scout
- No #1036 `execute` accepts extra env/argv/config patch/private files; every plain shape is pinned by a test. — *source:* S0-scout
- `GrokWire._answer` parses whole stdout as one JSON object; `CliRunner.run` buffers whole (no streaming); Grok output cap pinned at 4 MiB; fake grok has no streaming-json mode. — *source:* S0-scout
- Grok private home keyed only by workspace hash, shared, never removed → a `config.toml` written there leaks into later plain `run_grok_thread` calls; credentials test allows only `skills/` and `sessions/` in it. — *source:* S0-scout
- `MuseLauncher.environment` forwards every overlay name via WSLENV (plain set pinned to 5 names); per-call `XDG_CONFIG_HOME` deleted in `finally` (artifacts there would be lost). — *source:* S0-scout
- `native/` rules INV-15/INV-20: module-level classes only, no literals, no `vidbyte.tools` import, no allow-lists; lint A006: lib may not import tools → `McpServerConfig`/`McpPresetRegistry` (tools layer) unusable from native/ or lib; `McpPresetDefinition` (lib) lacks version/transport/url/tool names; 18 web presets (not 15); `vidbyte/lib/dataclasses/mcp.py` already exists. — *source:* S0-scout
- Semgrep is NOT in run_ci.py; it runs in `.github/workflows/static-policy.yml`. Editable install points at the main clone → run tests from the worktree root or with `PYTHONPATH=$(pwd)` for pytest only (never before run_ci.py package runs). — *source:* S0-scout + orchestrator memory
