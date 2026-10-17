---
slug: browser-agent
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-browser-agent
branch: feat/browser-agent
base_commit: 08f67e7f4a6fb3e0c524d476965f82d28d89e941
pr:
until: none
started: 2026-10-16 17:17
---

# Pipeline: BrowserAgent: JevAgent-shaped agent and runtime for long-running browser tasks

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-16 17:17 | 2026-10-16 22:35 | reports/S0-scout.md | base_commit 08f67e7f; code-map.md (4 sections, 17 notes) |
| S1 spec + review | running | 2026-10-16 22:40 | | reports/S1-spec-author.md | |
| S2 tests | pending | | | | |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 1/2 (round 1 reviewer launched 2026-10-16 on r1 @85fe040a) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Fixed values
- REPO_ROOT: C:/Users/422mi/vidbyte-repos/vidbyte-sdk (origin https://github.com/cerredz/Vidbyte-SDK.git; gh logged in as cerredz)
- WORKTREE_PATH: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-browser-agent
- BRANCH: feat/browser-agent · PR_BASE: main · BASE_COMMIT: 08f67e7f4a6fb3e0c524d476965f82d28d89e941
- SLUG: browser-agent · TITLE: BrowserAgent: JevAgent-shaped agent and runtime for long-running browser tasks
- AGENTS_MD_PATH: C:/Users/422mi/vidbyte-repos/vidbyte-sdk/AGENTS.md (identical copy at <worktree>/AGENTS.md)
- REPO_MAP_PATH: C:/Users/422mi/vidbyte-repos/vidbyte-sdk/REPO_MAP.md · FIELD_GUIDE_INIT: C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/init.md
- CLAUDE_SKILL_DIR: C:/Users/422mi/.claude/skills/spec-pipeline · AGENTIC_ENGINEERING_DIR: C:/Users/422mi/.claude/skills/agentic-engineering
- request.md: copied byte-for-byte from the main agent's capture (sha1 a646269ebb8eace63bbb0fbeacb50c3f7189381c, diff identical)
- Scratchpad: C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/d4409101-4281-402b-989c-fb71871586cd/scratchpad/browser-agent

## Decisions the orchestrator made
- 2026-10-16 17:17 — request.md frontmatter kept exactly as captured (already in the report-formats.md shape) — byte identity to the capture mattered more than restating the invoked time.
- 2026-10-16 — S0 scout stopped at the session usage limit (HTTP 429) after writing partial notes to reports/S0-scout.md and no code-map.md; the session moved from Fable 5.1 to Opus 5.5; resumed the same scout (SendMessage) per the main agent, fallback is a fresh scout told to verify the partial report rather than trust it.
- 2026-10-16 22:35 — The Claude Code process restarted after the resumed scout wrote code-map.md (22:11) and its complete report (22:14) but before its STATUS block reached the orchestrator. Per the main agent, the scout was not relaunched; the two files were taken as its output and the S0 spot-check was run on them directly (4 `## ` headings; §2 paths `vidbyte/tools/toolsets/infinite.py`, `vidbyte/tools/mcp/client.py`, `vidbyte/lib/registries/runtimes.py` exist; §1.1 quotes `python scripts/run_ci.py` under "## Repository Map"; status shows only docs/spec/browser-agent/). Niche facts below were taken from code-map.md §3–§4 and report §5.
- 2026-10-16 22:35 — Two scout findings conflict with request.md and go to the S1 author as items to resolve against the repo, not as settled decisions: (a) code-map §4 note 9, field guide prebuilt-agents.md puts `<Agent>Tools(Tools)` in `vidbyte/tools/toolsets/<agent>.py` (Infinite and Coding follow it), which beats the areas hint's `vidbyte/agents/browser/tools.py`; (b) note 13, runtime-boundaries.md says numeric caps on tool calls are a middleware `deny_tool` and prompts carry no numbers, so the episode action and screenshot caps must follow it, not only `AgentLoopSettings.max_iterations`.

## User replies (verbatim)
- none yet

## Niche facts accumulated (carried into every later briefing)
- S1 author (r1 @85fe040a): `_budget_stop` checks `max_tool_calls` at the top of each iteration (`vidbyte/agents/runtime.py:2071-2080`), so a worker that hits the action cap gets no turn to report (EC-11, Q-9). — *source:* S1 author
- S1 author: the runtime's `max_tool_calls` count includes DENIED calls (`_non_internal_tool_contexts`); `ToolSettings` budgets skip denied calls. — *source:* S1 author
- S1 author: `BaseAgent` builds the runtime 3 times per run (`base.py:1280/1319/1388`), so the runtime `__init__` must have no side effects (INV-23); MCP connects at `base.py:916`, before `_runtime()`. — *source:* S1 author
- S1 author: on the final-text finish path the loop appends the assistant reply after the hook's user message (`runtime.py:598-601`), as with Jev. — *source:* S1 author
- S1 author: tests route scripted runners by agent name: `{name}`, `{name}-episode-{n}`, `{name}-recheck`, `{name}-done-when`; the MCP fake is patched at `vidbyte.tools.mcp.attach.McpStdioTransport`. — *source:* S1 author
- S1 author: the `vidbyte/lib/enums/prompts.py` header counts ("139 … 35") are hand-kept and already stale; recount from the tree. `vidbyte/middleware/compaction/strategies.py` is 1,020 lines, so the shared sliding window cannot be extended in this PR. — *source:* S1 author
- S1 author: baseline at 08f67e7f in the worktree: 1 failed, 6240 passed, 16 skipped; the failure is a pre-existing `harness_threads` surface test (recorded in spec §11). — *source:* S1 author
- MCP screenshots never reach a model as pixels: `McpClient._content_to_text` turns every image/audio block into the text `[image: <mime>, <n> base64 chars omitted]` and truncates each result to 8,000 chars (`vidbyte/tools/mcp/client.py:31`, `:109-115`, `:136-143`, @intent `mcp-binary-content-stays-out-of-prompts`); the loop stores provider-formatted text dicts only (`vidbyte/agents/runtime.py:1935-1953`). The observation diet prunes text tool results. — *source:* S0 scout (code-map §4.1)
- Preset keys: `McpPresetRegistry.build_config` checks `required_env` only against `preset.default_env` merged with the caller's `env` (`vidbyte/tools/mcp/presets.py:400-404`) and raises `McpPresetConfigurationError` (:104); the server subprocess gets an allowlisted env (`vidbyte/tools/mcp/transport.py:34-62`, `build_child_env` :80-89), so a key only in `os.environ` never reaches the server unless passed in `env`; `vidbyte/tools/toolsets/coding.py:8` says do not read keys from env vars. — *source:* S0 scout (§4.2)
- No event sink exists on main at 08f67e7f: no `InfiniteEvents`, `JevEvents`, or `on_event` on Jev/Infinite; the only `on_event` is `MultiAgent` (`vidbyte/agents/multi/agent.py:65`). — *source:* S0 scout (§4.3)
- Shared browser session: `BaseAgent.run()` closes every MCP server after each sync run (`vidbyte/agents/base.py:1107-1114` → `vidbyte/agents/mixins.py:246-262`); servers stay open only across `arun()`/`async with` (`mixins.py:387-388`); `fork()` starts new subprocesses and drops bridged tools (`vidbyte/agents/fork.py:98-99`, `:176-188`); `BaseAgent._own_tool` passes `McpBridgedTool` through unchanged (`base.py:473-493`), so a separately built `BaseAgent(tools=[bridged…])` reuses the same client; the transport is bound to the event loop that started it (`transport.py:152-170`); concurrent use of one stdio client is unverified. — *source:* S0 scout (§4.4)
- Tool-name collisions: bridged tools keep raw server names (no prefix); `Tools` raises `ToolRegistrationError("Tool already exists: …")` (`vidbyte/tools/catalog.py:37-38`); an attach whose tool name is taken attaches no server; the server→tools map is `McpServerHandle.bridged_tools`/`tool_names` (`vidbyte/tools/mcp/types.py:50-71`), `McpBridgedTool` has no server or role field; Infinite refuses reserved names (`vidbyte/agents/infinite/runtime.py:72`, `INFINITE_RESERVED_TOOL_NAMES`). — *source:* S0 scout (§4.5)
- Observation-diet prior art: `MessageHistoryCompactionMiddleware.tool_output_sliding_window(keep_recent=…)` keeps the newest results per tool name and compacts the outgoing call only, stored history unchanged (`vidbyte/middleware/compaction/context_compaction.py:173-175`, `strategies.py:683-695`, `runtime.py:1085-1094`); `trim_with_provider_boundaries` is used by Infinite workers (`vidbyte/agents/infinite/launch.py:277-291`). — *source:* S0 scout (§4.6, §4.12)
- Presets: `playwright` runs `python -m mcp_server_playwright`, `puppeteer` runs `npx -y @modelcontextprotocol/server-puppeteer`, both `required_env=()`; `browserbase` needs `BROWSERBASE_API_KEY`+`BROWSERBASE_PROJECT_ID`; `firecrawl` `FIRECRAWL_API_KEY`; `jina_reader` `JINA_API_KEY`; `brave_search` `BRAVE_API_KEY`; `tavily` `TAVILY_API_KEY`; `exa` `EXA_API_KEY`; `duckduckgo` none; `apify` `APIFY_API_TOKEN` (`vidbyte/lib/config/mcp_presets.py`); `McpPresetDefinition` has `category`, no role. — *source:* S0 scout (§4.7)
- Usage: MCP tool calls are unpriced (`McpBridgedTool(BaseTool)`, not a `PricedOperationTool`); `JevUsageAccount.require_accounted` fails closed on unpriced model calls only (`vidbyte/agents/jev/usage.py:39-58`); worker usage reaches the parent through the active ledger (`base.py:873-885`, `vidbyte/lib/usage_ledger.py:42-48`). — *source:* S0 scout (§4.8)
- Toolset placement: field guide `prebuilt-agents.md` puts `<Agent>Tools(Tools)` in `vidbyte/tools/toolsets/<agent>.py` (check: the agent module imports no tool classes except the toolset); Infinite (`vidbyte/tools/toolsets/infinite.py`) and Coding follow it. — *source:* S0 scout (§4.9)
- Folder README: Infinite's README has a File Index and `## Notes for agents` (`vidbyte/agents/infinite/README.md:91-115`); Jev's has neither; once a File Index exists, lint S020 enforces parity with the folder's files; A009 caps READMEs at 40,000 chars. — *source:* S0 scout (§4.10, §1.1)
- Structured fresh-context call prior art: a `BaseAgent(output_schema=…)` as in `vidbyte/agents/jev/done/reviewer.py:44-58`, resolved by `StructuredOutputRegistry.resolve` (`vidbyte/lib/registries/structured_output.py:45-54`); a schema miss raises `OutputSchemaViolationError` (`base.py:1060-1076`); side agents inherit system-prompt presets (`base.py:866-871`), `JevReviewer` passes `system_prompt_presets=()`. The `goals/` family is NOT a recheck prompt (it is a Codex `/goal` emulation system prompt, `Prompt.GOALS_GOAL_PROMPT`). — *source:* S0 scout (§4.11)
- Context size: `AgentLoopSettings.compaction_trigger_tokens`/`context_window_budget` are stored but have no consumer in the runtime or middleware; `TokenEstimate` (`vidbyte/lib/util/text.py:88-104`, 4 chars/token) and `TokenBudgetMiddleware` (aborts, does not rebuild) exist. — *source:* S0 scout (§4.12)
- Caps: field guide `runtime-boundaries.md` says a numeric cap on a tool call is a middleware `deny_tool`, and prompts carry no numbers; `AgentLoopSettings` counts iterations and `max_tool_calls` (`vidbyte/agents/settings/loop.py:49-67`), not screenshots; no screenshot counter exists on main. — *source:* S0 scout (§4.13)
- `InfiniteMemoryAgent` sets `session_persistence_supported = False` (`vidbyte/agents/infinite/agent.py:45`); `JevAgent` does not; the request is silent for `BrowserAgent`. — *source:* S0 scout (§4.14)
- Public API contract: `scripts/generate-sdk-public-api.py` refuses to regenerate `contracts/sdk-public-api.json` while `vidbyte/__init__.py` or `pyproject.toml` differ from HEAD, so commit the export change, regenerate, commit again; lint C016 fails until then. — *source:* S0 scout (report §5)
- Hand-kept counts to update when adding a prompt family or bundle: `vidbyte/lib/enums/prompts.py:7-8` ("139 static prompt assets across 35" families) and `REPO_MAP.md:361`. — *source:* S0 scout (§4.16)
- Test fakes (no paid calls): `MockMcpStdioTransport` (`tests/test_mcp_attachment.py:49-106`), activated with `@patch("vidbyte.tools.mcp.attach.McpStdioTransport", MockMcpStdioTransport)`; `TwoToolMcpTransport` (`tests/test_agent_fork_isolation.py:119`); `FakeTransport` with `McpClient(FakeTransport())` + `McpToolBridge(...).bridge()` (`tests/test_mcp_bridge.py:30`, `:165-166`); `build_test_agent(..., runner=DoneRunner())` (`tests/agent_test_support.py:68`); `FakeRunner`/`RecordingRunner` (`tests/test_agent_runtime.py:61`, `:67`); `RecordingTracer` (`tests/test_agent_fork_isolation.py:131`). Pack to model: `tests/features/infinite_memory_agent/` (FEATURE.md, README.md, `infinite_memory_fixtures.py`, `test_infinite_memory_{acceptance,contract,context,delegation,resume,verification,workspace}.py`). — *source:* S0 scout (§3)
- Test commands: one pack `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent -q`; one file `PYTHONPATH=$(pwd) python -m pytest tests/features/browser_agent/<file>.py -q`; neighbours `tests/test_mcp_attachment.py`, `tests/test_mcp_bridge.py`, `tests/test_agent_fork_isolation.py`, `tests/test_agent_runtime.py`, the infinite and jev packs. Pytest runs with `--strict-config --strict-markers`. — *source:* S0 scout (§3.3, §1.2)
- Gate extras from the field guide `local-ci-verification.md`: semgrep scans only tracked files, so `git add -A` then `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (`semgrep==1.170.1`); S051 import order `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`; two `harness_threads` surface tests fail locally on any branch touching `vidbyte/tools`, `vidbyte/lib/configs`, or root exports (pre-existing; confirm with a control on main); `tests/test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` is flaky on CI 3.11. — *source:* S0 scout (§1.4)
- Worktree gate: the shared Python env has an editable install resolving `vidbyte` to the canonical checkout; run `PYTHONPATH=<worktree> python scripts/run_ci.py --stage source` for the source stage and plain `python scripts/run_ci.py` (no leaked PYTHONPATH) for the package stage; check with `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"`; never `pip install -e` from the worktree; never modify the canonical checkout; other worktrees under worktrees/ belong to other runs. Read field-guide local-ci-verification.md before the first gate run. — *source:* main agent, 2026-10-16
- PR checks: opening a PR triggers no checks; dispatch `gh workflow run CI --ref feat/browser-agent` and `gh workflow run "Static policy" --ref feat/browser-agent`, then `gh run watch <id> --exit-status`; confirm check-runs attach to the head SHA via `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`; required checks `Source / Python 3.11`, `Source / Python 3.12`, `Package`. PR is a DRAFT and stays a draft. — *source:* main agent
- No paid calls: no test, gate, or agent may call a paid model or a real MCP server; use SDK fakes as tests/features/infinite_memory_agent/ does. — *source:* main agent
- Session limits: at most 4 stage agents in flight. — *source:* main agent
- Bash is Git Bash; long quoted heredocs fail with `unexpected EOF`; write helper scripts to the scratchpad or use Write/Edit; the Read tool truncates very large files, read in ranges. — *source:* main agent
- docs/ is opaque in vidbyte-sdk; stage agents read only docs/spec/browser-agent/* files named by absolute path. — *source:* main agent
- Prompt families live under vidbyte/prompts/prompts/<family>/ with keys in vidbyte/lib/enums/prompts.py; `infinite_memory/`, `jev_continuation/`, `goals/` exist on main. — *source:* main agent
- Commit trailer (from the Opus switch on, every commit): `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (it replaced the Fable 5.1 trailer); PR body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. — *source:* main agent, after the session moved to Opus 5.5
