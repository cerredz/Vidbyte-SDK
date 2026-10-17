# S1 spec author report: browser-agent r1

- **Spec:** `docs/spec/browser-agent/spec.md`, committed as `85fe040a` ("docs(spec): add browser-agent spec r1"). Only that file is in the commit.
- **Shape:** 18 `## §` sections, 29 rows in §12.3, 33 new files for the implementer and 12 modified, plus the S2 test pack.
- **IDs:** 29 INV, 30 AC, 34 EC, 23 FR, 8 NFR, 28 D, 9 Q, 6 T, 8 A.

## What I read

**Briefing files**
- `request.md` in full: the prompts, the §B ledger, the §C notes, and the §D weighted words.
- `context/code-map.md` in full.
- `reports/S0-scout.md` in full.
- The spec template.

Under `docs/` I read nothing else.

**Rules**
- AGENTS.md: the style principles, the Placement Rules, and "Existing code".
- REPO_MAP rows for infinite, jev, constants, and toolsets.
- The infinite and agents READMEs.
- The field-guide entries quoted in code-map §1.7.

**Code, read at the cited lines**

| Area | Files |
|---|---|
| Linear loop | `vidbyte/agents/runtime.py`, read at every hook and budget point that §11 and §13 cite |
| Agent and MCP lifecycle | `vidbyte/agents/base.py`, `mixins.py`, `fork.py` |
| MCP layer | `vidbyte/tools/mcp/{types,presets,transport,client,attach,bridge,README}` |
| Infinite agent | `vidbyte/agents/infinite/{agent,runtime,settings,launch,__init__,README}` |
| Jev agent | `vidbyte/agents/jev/{runtime,usage,response}.py`, `jev/done/reviewer.py`, `jev/continuation/fresh.py` |
| Settings, validation, compaction | `vidbyte/agents/settings/{loop,tool}.py`, `vidbyte/lib/dataclasses/validation.py`, `vidbyte/middleware/compaction/*`, `vidbyte/middleware/builtins/{tool_policy,delegation_limits}.py` |
| Prompts | `vidbyte/prompts/catalog.py`, `vidbyte/lib/enums/prompts.py` |
| Structured output | `vidbyte/lib/registries/structured_output.py`, `vidbyte/providers/gemini.py:165-167` |
| MultiAgent events | `vidbyte/agents/multi/ledger_controller.py:163-172` |
| Toolsets | `vidbyte/tools/toolsets/{infinite,coding}.py` |

**Tests**
- The infinite feature pack's fixtures and contract test.
- `tests/test_mcp_attachment.py`.
- `tests/test_mcp_bridge.py`.

**Baseline run**
- I ran `run_ci.py --stage source` on the unchanged base `08f67e7f` in this worktree.
- Lint, compileall, and the three check scripts passed.
- pytest: 1 failed, 6240 passed, 16 skipped. The one failure is pre-existing: `harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`.
- The log is in my scratchpad as `baseline-source.log`.

## Approaches weighed

1. **Smallest design: a facade over a plain `BaseAgent`.** The MCP tools, a `patch_goal` FunctionTool, and history trimming, with no runtime type. Rejected (§8.3):
   - the orchestrator would hold the ACTION tools, so every observation would land in its history, which is the problem the user described;
   - no fresh-context finish check is possible without `_continue_finish_attempt`;
   - no stall stop is possible without `_budget_stop`.
2. **Repo mechanism (chosen).** An `AgentRuntimeType.BROWSER` runtime that only overrides `arun` setup and the three existing hooks. Every cap and diet reuses existing settings and middleware:
   - `max_tool_calls`;
   - `max_calls_per_tool`;
   - `tool_output_sliding_window`;
   - `trim_with_provider_boundaries`.

   This mirrors InfiniteMemory's root, which uses a run-local tools extension, a pinned card, and history trimming, and Jev, which uses the finish hook, usage, and response.
3. **The request's literal design.** Rejected in parts:
   - a `finish_episode` tool;
   - `context_rebuilt` built from `messages.clear()`;
   - keys read from `os.environ`;
   - a nested `BrowserToolSettings`;
   - a new middleware for the caps.

   The deviations are listed below.

## Where I disagree with the request or the scout, with evidence

1. **Keys from `os.environ`** (request §C). Refused, so a key in `os.environ` does not count (D-4).
   - `build_child_env` (`vidbyte/tools/mcp/transport.py:80-89`) passes only an allowlist to the server, so a key that is only in `os.environ` never reaches it.
   - `coding.py:8` says "Do not read fetch keys from environment variables".
   - The user said keys are uploaded "into the agent settings".
2. **The `finish_episode` tool** (request §C). Replaced by worker `output_schema=BrowserEpisodePayload` (D-8).
   - A tool cannot end the worker's loop.
   - Structured output beside tools is already supported, with provider fallback (`structured_output.py:62`, `gemini.py:167`).
3. **`context_rebuilt` built from `messages.clear()`** (request §C). Replaced by the pinned goal card plus `trim_with_provider_boundaries`, which is the infinite root's mechanism (D-11).
   - The field guide says to reuse the shared compaction infrastructure and to write no bespoke compaction.
   - The event and the rebuild counter are dropped, so there are 9 event kinds, not 10.
4. **"Keep the latest 2 observations"** (Q-4). The default becomes **1 per tool** (D-10).
   - The shared window counts per tool name (`strategies.py:683-695`).
   - An all-tools option would mean editing `strategies.py`, which is 1,020 lines. AGENTS.md principle 3 says to split such a file first, which is its own PR (Q-6).
5. **Card cap of 300 tokens** (§B sketch). Raised to 800 (D-25).
   - Harvest pages list many items.
   - It matches `INFINITE_CARD_TEXT_MAX_TOKENS`.
   - The full record stays on `agent.response`.
6. **Toolsets placement** (field guide, "`<Agent>Tools` in toolsets"). `BrowserAgentTools` stays in `vidbyte/agents/browser/tools.py` (D-6).
   - This agent has no preloaded static tools.
   - Its configs come from agent-layer settings, and toolsets may not import `vidbyte.agents` (`toolsets/infinite.py:5,8`).
7. **`InfiniteEvents` as the events sibling** (request §C). It is not on main. The MultiAgent `_emit_event` pattern is used instead (D-18).
8. **Screenshots** (request §C, "evidence such as screenshots goes to files"). The MCP client turns images into text placeholders (`client.py:136-143`), so neither the SDK nor any model ever holds the pixels (D-23, NG-6, Q-7).
9. **Nested `BrowserToolSettings`.** Replaced by three flat role fields (D-3). They read like the user's own example and need one import less. The user said "use judgement".
10. **Found during self-check, and not in the scout's map: an action-cap stop gives the worker no last turn.**
    - `_budget_stop` checks `max_tool_calls` at the top of each iteration (`runtime.py:2071-2080`), so a worker at the cap is stopped before it can write its card, and that episode's findings are lost.
    - The runtime's count includes denied calls (`_non_internal_tool_contexts`), so a denied screenshot spends one action.
    - No existing setting denies calls past a total count and lets the run continue. The fix is a small new middleware, the browser-use "final step allows only done" pattern, which NFR-2 rules out. Recorded as EC-11 and Q-9 (default no).

## Assumptions I am least sure of

- **A-4** (most consequential): every provider carries a worker `output_schema` beside tools. If one does not, every episode on that provider ends `stuck`, and D-8's runner-up, the `finish_episode` tool, becomes the design.
- **A-1**: real browser servers put "screenshot" in their screenshot tools' names. I verified no real server, because starting one was not allowed. If wrong, the screenshot cap misses them, while the action cap still bounds them.
- **A-3**: preset commands on main start working servers. For example, the `playwright` preset runs `python -m mcp_server_playwright`, which may not exist as a pip module. If wrong, the README must point developers at `command=("npx", "@playwright/mcp@latest")`.
- **A-6**: provider-boundary trimming keeps the task message and the system prompt. I checked the infinite README's claim, not each provider's placement.
- **The budget arithmetic** (NFR-4) assumes about 2,000 goal tokens and 8 ACTION tools per worker. Neither has been measured. A-7 asks for the user's 20-page measurement.

## Notes for S1.5 and S2

- The template says file paths appear only in §11 and §12, yet it asks for evidence paths in §1, in the must-not-regress INVs, in §8.2 (`path:symbol`), and in §13.
  - §8 now names design locations as dotted modules. The `file:line` evidence citations stay in the deciding reasons.
  - A reviewer who reads the rule literally may flag the remaining citations.
- **AC-1** depends on the test author routing scripts by agent name. The names are fixed by constants (§13).
- **AC-13**: on the final-text path, the loop appends the assistant reply after the hook's user message (§13).
