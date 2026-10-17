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

## Addendum: revision r2 (review round 1), commit f09bf057

I accepted all eight findings and verified each against the code before changing the spec.

- **R-1 (rebuild).** I restored the user's rebuild.
  - `_after_tool_iteration` deletes, in place, every stored message before the last assistant turn once the stored history passes `BROWSER_HISTORY_MAX_TOKENS`.
  - It is safe because the task never sits in `messages`. The provider inserts it at `prompt_index` (runtime.py:1611-1615, prompt_placement.py:29-48, gemini.py:81-103).
  - I also checked the alternatives. No compaction mode on main changes stored history (context_compaction.py:217-229). `compaction_trigger_tokens` is only passed through config. The one in-loop summarizer (trajectory_checkpoints) calls a model.
  - My r1 disagreement no. 3 is withdrawn: the user's decision outranks the field guide.
- **R-2 (stuck card).** The stuck card now carries evidence.
  - It is built from `worker.last_reply.metadata["tool_calls"]`; `last_reply` is set at base.py:1009, before the raise at :1022.
  - The worker sees `max_tool_calls: n/N` in its prompt (runtime.py:1679-1701), and its rules say to return its card before the budget runs out.
  - `BROWSER_EPISODE_FINAL_TURNS` is renamed `BROWSER_EPISODE_REPLY_TURNS = 4`. The slack is real: a schema miss is repaired in the loop up to 3 times (base.py:1494, runtime.py:523-543).
- **R-3 (refused finish).** The finish hook now upserts the card, with the verdict and gap, before the loop continues. This is needed because a refused finish skips `_after_tool_iteration` (runtime.py:680-688). The orchestrator leaf now says to finish through `isDone`, and EC-36 records the order of messages on main.
- **R-4 (progress cap).**
  - EC-37 records the outcome: about 480–800 progress lines, then the run ends `goal_stalled`.
  - A new `progress_full` leaf makes 19 leaves and 34 new files.
  - Q-10 is a [scope-adding] question, default no.
- **R-5 (screenshots).** The worker leaf now says screenshots cannot be seen and are taken only to save evidence. A-9 covers whether a server names the saved file.
- **R-6 (kept observations).**
  - `keep_observations` is back to the user's 2, applied per tool. An all-tools count is blocked by the 1,020-line strategies.py, and Q-6 asks the user to confirm.
  - A new worker `trim_with_provider_boundaries(max_tokens=BROWSER_WORKER_HISTORY_MAX_TOKENS=32_000)`, the Infinite children pattern, now bounds the worker budget.
  - My r1 disagreement no. 4 is replaced by this.
- **R-7 (configs).** Servers are now queued with `with_preset_mcp_server` or `with_mcp_server`. `BrowserAgentTools` holds role names only.
- **R-8 (stop codes).** Row 5 now states why no `_STOP_CODES` row is added.

Least sure in r2:
- A-6 is now verified in code, but not exercised against a live provider.
- The rebuild trigger (60,000) and the worker trim (32,000) are untested starting values, like the other caps (A-7).

## Addendum: revision r3 (review round 2), commit 0adeae0b

I accepted all four Majors after checking each against the code. The spec is now `status: approved`, revision 3.

- **r2 R-1 (seam-observable ACs).** The test seam records the task apart from the messages. `ModelCall.prompt` holds the task, and `messages` holds `options["messages"]`; `prompt_index` is dropped (fixtures :253-262, :320-335).
  - AC-22 and AC-31 now assert `messages` and `prompt` separately.
  - AC-31 sums each message's string content, which is the trim's own measure (strategies.py:50-68). The trim's count is never lower, so a correct trim passes.
  - INV-11 now allows the trim to drop a whole turn.
  - The evidence on a stuck card is now exact: the first 400 characters, with no marker (INV-12, AC-7, EC-11, row 15).
  - §13 now gives recipes for reaching both caps. For the orchestrator, results are cut to 20,000 characters, about 5,070 tokens per turn, so 11 turns stay under the cap and the 12th passes it. For the worker, 17 distinct tools at the MCP client's 8,000-character cap pass 32,000 tokens.
- **r2 R-2 (EC-12).** EC-12 now matches INV-12: stop reason `contract_unsatisfied`, exact `actions`, and evidence.
  - `stuck_summary` takes `{reason}` only, so a card with `actions` None never shows "None". The leaf count is still 19.
  - An error card fills the reason with the error type name.
- **r2 R-3 (refused finish).** Verified: the `isDone` refusal is stored at runtime.py:656-657 before the hook runs at :673. The refused branch continues at :680-688, before `_after_tool_iteration` at :700.
  - One private step, `_rebuild_history`, now runs from both hooks. On a refusal it runs before the gap message.
  - A rebuild is counted only when something was removed (EC-35).
  - New AC-33 covers this path.
  - NFR-4 and the budget now include what a refused finish appends after its check.
- **r2 R-4 (engine).** The step calls `ContextCompactionEngine().compact_provider_messages(messages, mode=TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_messages": 1})`, then `messages[:] = list(kept)`.
  - Verified: with `max_messages=1` the trim keeps exactly the group that holds the last message (strategies.py:613-622).
  - The engine classifies all three provider shapes, and every result shape in formatter.py is classified as a result (engine.py:311-330).
  - Precedent for the call: context/algorithms/tool_results.py:78.
  - `BROWSER_ASSISTANT_ROLES` is deleted.
  - D-11's "no seam" reason is corrected: `TOP_OF_CONVERSATION` exists, but it renders assistant-role messages.
  - No file under `vidbyte/middleware/` changes.

Final counts: FR 23, NFR 8, INV 30, AC 33, EC 37, D 28, W 10, T 6, A 9, Q 10, and 29 rows in §12.3. The budget is 34 new files (19 leaves) and 12 modified files.

Least sure in r3:
- The orchestrator recipe's arithmetic: about 5,070 tokens per turn, leaving 11 turns about 4,000 tokens under the cap. It rests on the JSON overhead and the ToolSettings suffix. The test author should assert the first call whose `messages` shrink, not a fixed call index.

## Addendum: revision r4 (S2 test-author spec defects)

These were raised by the S2 test author, not by a review round. I accepted all four after checking each against the code. The status stays approved. I added no field, knob, or behavior, and every Proof cell in §6.2 is byte-identical to the test author's (checked by a script).

- **S2 defect 1 (snippet model).** The §4 snippet now uses `model_name="gpt-5.4-mini"`. I checked it by calling both registries offline, with no model call:
  - `ProviderModelRegistry.validate_provider_model_pair("openai", "gpt-5.4-mini")` passes (models.py:344-361; catalogued at runners.py:54 and 213).
  - `ModelPricingRegistry.default().resolve(OPENAI, "gpt-5.4-mini")` returns the row at pricing.py:168.
  - For `gpt-4.1` the pair check passes but `resolve` returns None. That is the defect: my A-5 had checked only the pair.
  - A-5 is restated. No pricebook row was added.
- **S2 defect 2 (`isDone`).** `AgentRuntime.__init__` wraps every catalog with `with_internal_agent_tools` (runtime.py:194, _internal.py:51-53). INV-7, INV-15, AC-5, AC-12, FR-6, FR-12 and D-13 now say "no tool but the loop's `isDone`".
- **S2 defect 3 (stop reason of a provider error).** `stop_reason` is `type(error).__name__` of the caught exception. `BaseAgent` wraps a provider error in `AgentExecutionError` (base.py:976-979), so the value is `AgentExecutionError`. The change is in INV-12 and row 15.
- **S2 defect 4 (runtime set).** INV-27 now says `_LINEAR_LOOP_RUNTIMES` holds exactly four members, including BROWSER, as row 21 adds.

Counts are unchanged: FR 23, NFR 8, INV 30, AC 33, EC 37, D 28, W 10, Q 10, 29 rows in §12.3, and a budget of 34 new and 12 modified files.

Open: test_browser_agent_acceptance.py:89 still has `"gpt-4.1"`. The test passes either way, because the fake replies report PRICED_MODEL, but it should copy the snippet byte for byte. The test author will change it to `"gpt-5.4-mini"`.
