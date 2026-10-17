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
| S0 worktree + capture + recon | done | 2026-10-16 21:43 | 2026-10-16 | reports/S0-scout.md, reports/S0-vendor-scout.md | base_commit 845a4d9b; code-map.md (488 lines); vendor-facts.md (473 lines) |
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

- 2026-10-16 — Session restart stopped the vendor scout and the computer-use researcher mid-run; both resumed via SendMessage from their transcripts (partial scratch work intact, no leftover processes found). Checkpoint commit 77c97d0f made before resuming.
- 2026-10-16 — The computer-use researcher was blocked by the harness from writing `report.md` ("Subagents should return findings as text, not write report files"); the orchestrator extracted its final message into `scratchpad/computer-use/report.md` with `scratchpad/extract_last.py`. If a pipeline subagent hits the same block on `reports/S*-*.md`, extract the same way and commit it. Orchestrator re-verified 3 of its claims at source (cua SKILL.md:3, :78; codex models.rs:2427-2443).

- 2026-10-16 — Accepted the vendor scout's deviation: to observe real tool names and permission effects it ran `grok -p` and `opencode serve` against a scripted LOCAL stand-in endpoint (not a model; no traffic left the machine, no keys). Briefing forbade `opencode run`/xAI calls; the deviation honours the intent (free, offline, keyless) and the report names it. Spot-check: vendor-facts.md has 8 sections, 83 [V] / 12 [U] tags, raw logs in scratchpad/vendor-probe/logs; no key-shaped strings in any S0 artifact.

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
- Muse MCP: `$XDG_CONFIG_HOME/muse/settings.json` needs `"schema_version":1`; shape `{"mcpServers":{"<name>":{"command":"python3","args":[...],"env":{"K":"literal"}}}}`; remote transport is `streamable_http` (UNDERSCORE) — `streamable-http`/`http`/command-list/env-on-http silently disable EVERY server; no `${VAR}` expansion, no env inheritance (server env = HOME, LANG, LOGNAME, PATH, SHELL, TERM, USER + entry `env`) → secrets must be literal values in the per-call (deleted-in-finally) temp file; one bad entry disables all MCP but exits 0; every server is required (one startup failure fails the run); MCP diagnostics only in session.jsonl (hidden by `--no-session-log`); Windows Node via WSL interop does NOT work; a Windows HTTP MCP server on 127.0.0.1 IS reachable. — *source:* S0-vendor-scout (vendor-facts.md §1)
- Grok: headless MCP call with no allow rule cancels the whole turn yet exits 0; `--allow MCPTool(x__*)` works; deny wins even over `--always-approve`; model sees MCP only via `search_tool`/`use_tool`; startup grace ≈2 s (one sample) → slow servers unusable in a one-turn run; `--agent <file>` works with `-p` as a per-run mount route (frontmatter `mcpServers:` must be a LIST of `{name, command, args, env:[{name,value}]}`; no `${VAR}` there); `~` resolves from USERPROFILE; compat vars leave `~/.claude` hooks, `~/.agents/skills`, `~/.claude/settings.local.json` permissions active; 3 concurrent `grok -p` sharing one GROK_HOME succeeded. Grok calls the base URL for `/v1/models`, `/`, a `/v1/responses` title, plus one tool-less turn-summary call per turn — a fake must tolerate these (404 tolerated). — *source:* S0-vendor-scout (§2)
- opencode: tools named `<server>_<tool>`; a `deny` rule REMOVES the tool from the model's list (not reject-at-call); `debug config` prints expanded secrets; isolation vars `OPENCODE_DISABLE_PROJECT_CONFIG=1`, `OPENCODE_DISABLE_EXTERNAL_SKILLS=1`, `OPENCODE_DISABLE_CLAUDE_CODE=1`; `{"enabled":false}` per name disables a global server; user's `~/.claude/skills` and `~/.agents/skills` load even with private XDG; a malformed MCP entry fails the whole config. — *source:* S0-vendor-scout (§3)
- Tool packages: exact tool names for 13 npm + 2 uvx servers in vendor-facts.md §4; `@wdio/mcp` fails on Node 22.12; Linkup starts despite engines ≥24; Bright Data, Apify (+Sentry) and BrowserStack call home at startup. — *source:* S0-vendor-scout (§4)
- Playwright MCP: `--isolated` + `--user-data-dir` together is fatal; screenshots with an explicit filename land in the server's cwd, not `--output-dir`; on Windows `taskkill /T /F` leaks `%TEMP%\playwright_chromiumdev_profile-*` with `--isolated`, while closing stdin cleans up in ~100 ms; chrome-devtools-mcp needs `CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1`. Env-filter wrapper works (client + opencode) but on Windows killing only the wrapper leaves the real server running. — *source:* S0-vendor-scout (§5, §6)
