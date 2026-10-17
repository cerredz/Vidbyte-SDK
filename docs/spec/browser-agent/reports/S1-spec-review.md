VERDICT: SOUND WITH FIXES — The decomposition is lean and fits the repo. But the spec quietly swaps out two behaviors the user settled: the orchestrator rebuild from the goal card, and a stuck card that carries evidence. It also leaves the refused-finish path, the progress cap, and the screenshot prompt unsafe. Each fix is local, and none changes the module plan.

Reviewed: spec.md r1 (unchanged from 85fe040a at HEAD 34a9434b), against the worktree code at base 08f67e7f. Lenses L1–L11, full review.

WHAT THE SPEC GETS RIGHT

- **No over-engineering against the user's words. Do not trim the class plan.**
  - Every class beyond the user's seven is forced by a requirement or by a repo rule:
    - `BrowserServerSettings` holds the keys for each server (the request's own `BrowserMcpServer` proposal).
    - `BrowserEpisodeTool` is the episode tweak, `BrowserGoal`/`_PatchGoalTool` is the goal card and patch tool, and `BrowserGoalCheck` is the fresh-context recheck plus the Q-3 derivation.
    - `BrowserResponse` must exist because the placement rule puts the `BrowserAgentResponse` record in `vidbyte/lib/dataclasses/`, so its one writer has to live in the agent package (the `JevResponse` → `JevAgentResponse` precedent, `vidbyte/lib/dataclasses/jev.py:3856`).
  - All 24 settings fields trace to request.md §C or to an Infinite or Jev field.
  - The 18 leaves follow the prompt-family rule (Infinite has 40).
  - The `vidbyte/agents/base.py` edit is registration-only, and it is required: `_runtime()` passes `usage_tracker`, `speed_tracker`, `output_contract` and `agent_catalog` only to `_LINEAR_LOOP_RUNTIMES` members (`base.py:1435-1442`). Without the edit, INV-21 breaks.
  - I found nothing the conversation did not ask for. The one duplicated helper is R-7.
- **D-4 is correct and matches the user's words** ("required to upload their api keys into the agent settings"): keys come only from the settings `env`.
  - The child process gets an allowlist only (`vidbyte/tools/mcp/transport.py:34-62`, `build_child_env` at :78-88), so a key that exists only in `os.environ` never reaches the server.
  - `McpPresetRegistry.build_config` checks only `default_env` merged with `env` (`presets.py:395-404`).
- **The shared-session mechanism needs no new lifecycle code.**
  - `_own_tool` passes `McpBridgedTool` objects through unchanged (`base.py:473-493`).
  - `_ensure_mcp_connected` runs at `base.py:916`, before both runtime builds in a direct run (`:1280` through `_build_context` and `:1319` in `_run_direct`). So the runtime that runs `arun` sees the live handles.
  - A sync `run()` closes the servers after each call (`mixins.py:246-262`), which EC-22 and AC-23 already document.
  - `Tools.without` and `extend` exist at `catalog.py:90` and `:83`.
  - `_adopt_agent_catalog` (`runtime.py:933-943`) applies only differences, so it does not put the ACTION tools back into the narrowed catalog.
- **D-6 (the role mapper in the agent package) and D-8 (`output_schema` on the worker) are sound.**
  - The toolsets layer may not import `vidbyte.agents` (`vidbyte/tools/toolsets/infinite.py:5,8`), and there are no static preloaded browser tools, so the `prebuilt-agents.md` entry's "When" does not apply.
  - The SDK already declares which models can carry a schema beside tools, with a fallback (`structured_output.py:62-66`; `NATIVE_SCHEMA_WITHOUT_TOOLS` lists only gemini-1/2; `providers/gemini.py:167`).
  - A-4 correctly names what is still unverified: the JSON_MODE tier (DeepSeek, GLM, Kimi, MiniMax).

FINDINGS (ranked, most severe first)

R-1 [Blocker] [L1] §8.1 D-11, FR-15, AC-22, §8.5 BrowserEventKind — The spec drops the user's settled "rebuild from the goal card plus progress" and puts an outgoing-only trim in its place.
  Evidence:
  - Spec D-11: "The in-run "rebuild" of the orchestrator is the goal card pinned at `TOP_OF_CONTEXT` on every call, plus `trim_with_provider_boundaries(...)`… There is no `context_rebuilt` event and no rebuild count."
  - request.md §B ledger: "orchestrator compaction and resume are the same rebuild".
  - request.md §C: "when the orchestrator's history passes a token cap, the runtime starts a fresh conversation whose first message is the goal card plus progress".
  - request.md §C lists `context_rebuilt` among the events, and the response carries a "context rebuild count".
  - request.md §B diagram: the orchestrator's context is "goal card + progress + last result card".
  - Code: `MessageHistoryCompactionMiddleware.before_model_call` rewrites `ctx.provider_messages` for one outgoing call only (`vidbyte/middleware/compaction/context_compaction.py:217-229`). No compaction mode on main has a token trigger. `clear_except_system_and_log` would clear on every call.
  Failure:
  - What happens: hour 6 of a run. The stored `messages` still holds every exchange since the start, and every call re-trims it. The orchestrator keeps a sliding window of raw transcript, including FETCH results of up to 8,000 characters each, instead of the thin "card + last result card" the user chose.
  - What the developer misses: `on_event` never receives `context_rebuilt`, and `agent.response` has no rebuild count.
  - What the follow-up loses: the Q-2 resume PR cannot reuse the in-run mechanism. That is the exact coupling the ledger asked for.
  - The §11 conflict note (e) misstates the choice. It calls it "clearing the conversation" versus the field guide. But the field guide is not AGENTS.md, and the user decided this point.
  Smallest fix:
  - In `_after_tool_iteration`, when `TokenEstimate.count` of the stored `messages` passes `BROWSER_HISTORY_MAX_TOKENS`, delete every message before the last assistant turn, in place. This is a tool-iteration boundary, so the last call/result group stays whole.
  - The next call then holds the pinned card (goal, done_when, plan, progress, blockers) and the last result card. The task reaches the provider through `prompt_index` (`runtime.py:318-321`, `:1612-1615`), not through `messages`.
  - Emit `context_rebuilt`, add `rebuilds: int` to `BrowserAgentResponse`, and remove the orchestrator trim middleware.
  - Rewrite FR-15, AC-22, D-11, the §9.1 budget, and the event enum to match.
  - If the author still believes the field guide's "no bespoke compaction" entry forbids this, record it as a Q-n whose default is the user's rebuild.

R-2 [Blocker] [L1/L3] §6.3 EC-11, D-9, Q-9, §9.1 `BROWSER_EPISODE_FINAL_TURNS` — When the action cap is hit, the stuck card carries no evidence. The user asked for a "stuck" card with evidence, and the spec's claim that the findings "are lost" is false.
  Evidence:
  - Spec EC-11: "the worker gets no turn to report… a `stuck` card is built with `actions = max_actions`. What the worker found during that episode is lost."
  - Spec §9.1: "`BROWSER_EPISODE_FINAL_TURNS = 1` (worker `max_iterations = max_actions + BROWSER_EPISODE_FINAL_TURNS`)".
  - request.md §B: "an action cap and a screenshot cap per episode, so a stuck worker returns a "stuck" card with evidence instead of burning the run."
  - Code, the stops:
    - `_budget_stop` stops at the top of every iteration once the non-internal calls reach `max_tool_calls` (`runtime.py:2073`). That check fires before `max_iterations` can matter, so the "final turn" never runs.
    - A batched turn is stopped mid-turn at the cap (`runtime.py:1864-1870`).
  - Code, the evidence that survives:
    - `last_reply` is set at `base.py:1007-1009`, before `_assert_schema_satisfied` raises at `:1022`.
    - That reply's metadata keeps `"tool_calls"`, the executed calls with their results (`runtime.py:2125`).
  - Code, the budget the model sees: the runtime renders `max_tool_calls: n/N` into every worker call (`runtime.py:1679-1701`). The spec never mentions this.
  - Field guide `runtime-boundaries.md`, Check line: "A test calls the tool past each cap and sees `Tool denied by middleware`". The loop-stop design fails it.
  Failure:
  - A worker at 28/30 batches five form fills. Call 31 stops the run mid-turn and `OutputSchemaViolationError` is raised.
  - The card's summary is only "stopped: max_tool_calls", with no facts, URLs, evidence, or recipe.
  - The orchestrator re-runs the same page blind and burns another 30 actions. That is the "burning the run" the user's sentence rules out.
  Smallest fix (no new middleware, so NFR-2 holds):
  - (a) On a cap stop, build the stuck card from `worker.last_reply.metadata["tool_calls"]`. The recipe is the executed calls. The evidence is the newest successful observation, cut to `BROWSER_STALE_OBSERVATION_CHARS`.
  - (b) The `worker_system_prompt` leaf tells the worker to return its card when the loop-settings block shows the tool-call budget nearly spent. This is behavior only, with no number.
  - (c) Delete `BROWSER_EPISODE_FINAL_TURNS`, or rename it to what it really is: slack for schema-repair turns.
  - Update EC-11, INV-12 and AC-7. Keep the field-guide `deny_tool` middleware as the Q-9 runner-up.

R-3 [Major] [L5] §6.1 INV-14, INV-16; §12.3 row 16; §13 — After a refused finish, the gap reaches the model before its own final answer, and the pinned card is stale.
  Evidence:
  - Spec INV-16: "the runtime appends exactly one user message carrying the verdict and gap".
  - Spec INV-14: "From the second orchestrator model call onward, the system prompt carries the current goal card".
  - Spec §13: "the hook's user message comes before that reply in `messages`, as with `JevRuntime`".
  - Code, final-text path: the loop appends the assistant's reply after the hook returns True (`runtime.py:598-601`).
  - Code, refused finish: the loop `continue`s without calling `_after_tool_iteration` (`runtime.py:680-688`, and the `continue` at `:601`). So row 16's re-pin, which happens only in that hook, does not run.
  - Code, isDone path: the order is right there. The refusal tool result comes first, then the gap (`runtime.py:656-675`).
  Failure:
  - The orchestrator answers "Here are 14 programs…", and the recheck returns continue with the gap "6 more needed".
  - The messages become `[…, user(gap), assistant("Here are 14 programs…")]`. The next call's newest message is the model's own final answer, and the card's verdict line still shows the old verdict.
  - The model repeats its answer, progress stays unchanged, and that counts as a stall. After `max_stalls`, the run ends `goal_stalled` with work still left. INV-14 is false on the call right after any refused finish.
  Smallest fix:
  - `_continue_finish_attempt` upserts the card, with the new verdict and gap, before it returns True.
  - The `orchestrator_system_prompt` leaf says to finish by calling `isDone`.
  - Add an EC row that names the final-text order as a loop limitation already on main and shared with Jev, together with its consequence.

R-4 [Major] [L6/L5] §9.1 `BROWSER_PROGRESS_MAX_CHARS`, EC-16, INV-17 — At the progress cap, a run that is still productive ends `goal_stalled`. The user's own scale examples hit that cap.
  Evidence:
  - Spec: "`BROWSER_PROGRESS_MAX_CHARS = 96_000`". Progress is append-only (D-12). EC-16 refuses an over-cap patch and leaves the card unchanged.
  - Spec INV-17: a `continue` verdict "and `progress` is unchanged" counts as a stall.
  - request.md §A Prompt 1: "finding 1,000 vc applications", "finding 100 research papers".
  Failure:
  - A progress line with a name, URL and deadline runs about 120–200 characters, so the card fills at roughly 480–800 items.
  - From then on, every `patch_goal(progress, …)` is refused, and progress never changes.
  - Episodes keep returning `done`, but every recheck counts as a stall. The run ends `goal_stalled` about three rechecks later, at roughly item 700 of 1,000.
  - No EC row names this outcome, so the test author and the implementer will not see it.
  Smallest fix:
  - Add the EC row: the trigger (the progress cap is reached), what the system does (refusal, then stalls, then `goal_stalled`), and what the user sees.
  - Have the `patch_refused` text at the cap say that progress is full.
  - State the card's capacity in items in the constants header and in the README notes.
  - Optional [scope-adding] Q-n: "Should bulk tasks above the card's capacity be supported in this PR (for example, progress lines carry counts, and items live on `agent.response.episodes`)?" Default: no. The bulk harvest runtime is NG-1.

R-5 [Major] [L1/L4] §9.1 `worker_system_prompt` leaf, D-23 — The worker prompt says to verify with screenshots, but the worker can never see a screenshot.
  Evidence:
  - Spec leaf text: "prefer text snapshots and screenshot only to verify".
  - Spec NG-6: images stay text placeholders.
  - Spec D-23: "`evidence` holds references the model reports (… file paths a server returned)".
  - Code: every image block becomes `[image: <mime>, <n> base64 chars omitted]` (`vidbyte/tools/mcp/client.py:136-143`).
  - Field guide `prompt-families.md`: a leaf "states only behavior the code has… Verify each described behavior against the code".
  Failure:
  - A worker "verifies" a filled form by screenshot. It reads only the placeholder, then reports `done` on a check it never made, or reports `ready_to_submit` on a wrong form.
  - Each screenshot call also spends a slot of `max_actions` (INV-10) and returns nothing usable.
  - The settled rule "evidence goes to files and cards carry paths" now depends on a fact the spec never states: that a server's screenshot tool names its saved file in the text it returns.
  Smallest fix:
  - The leaf says screenshots cannot be seen and that the worker verifies from text snapshots.
  - The worker takes a screenshot only to save evidence, and copies the file path the tool's text names into `evidence`.
  - Add A-9: "a screenshot tool's text result names the saved file; if wrong, cards carry no screenshot paths".

R-6 [Major] [L1/L10] §8.1 D-10, INV-11, Q-4, NFR-4 — The settled "2 observations kept" becomes "1 per tool", and the worker budget relies on a number nothing enforces.
  Evidence:
  - Spec D-10: "It counts per tool name, so the default `keep_observations` is **1** (Q-4 said 2 overall)".
  - Spec §9.1 worker budget: "Kept observations, one per tool, at most 8 tools × 2,000".
  - request.md §B: "Keep only the latest one or two observations and drop the rest" ("the biggest token saver").
  - Q-4's default of "2 observations kept" is in the settled list.
  - Code: `ToolOutputSlidingWindowCompaction.compact` keys its window on the tool name (`strategies.py:683-695`). No setting bounds how many distinct tools a worker uses.
  Failure:
  - Picture a server where clicks, typing and navigation each return a page snapshot (the spec's fakes assume `browser_navigate`, `browser_snapshot`, `browser_take_screenshot`).
  - A worker that has used 12 distinct tools sends 12 full observations of about 2,000 tokens each on every call. That is 6–12× what the user specified.
  - NFR-4's "8 tools" is an assertion that no code enforces, so a test author cannot pin the budget.
  - The mechanism itself is defensible. AGENTS.md principle 3 forbids growing the 1,020-line `strategies.py` before it is split, and the intro says that rewrite belongs in its own PR.
  Smallest fix:
  - Keep D-10.
  - State the real bound in INV-11 and in the NFR-4 worker sum: one full observation per distinct ACTION tool used, up to the size of the server's catalog.
  - Present Q-4/Q-6 as a deviation from a settled default that needs the user's confirmation, not as a changed default.
  - Optionally bound the worker the way Infinite bounds its children, with `trim_with_provider_boundaries(max_tokens=…)` on the worker (`vidbyte/agents/infinite/launch.py:290`).

R-7 [Minor] [L2/L4] §12.3 rows 10 and 17, §8.5 `BrowserAgentTools.configs` — `configs()` re-implements a canonical helper that already exists, and it keeps keys on an extra object.
  Evidence:
  - Row 10: "Presets go through `McpPresetRegistry.build_config(...)`, then `dataclasses.replace(config, name=...)`. Commands use `McpServerConfig(...)`".
  - Row 17: "queues each config with `self.with_mcp_server(config.command, name=config.name, env=config.env, timeout=config.timeout)`".
  - Code: `McpAttachableMixin.with_preset_mcp_server(preset_name, *, name, permission, env, timeout, extra_args)` already builds, renames, and queues a preset (`vidbyte/agents/mixins.py:180-196`). §11's "Reusable pieces" does not list it.
  Failure:
  - Two paths now build preset configs, which AGENTS.md principle 5 asks you to avoid.
  - `BrowserAgentTools` holds every `McpServerConfig` with its `env` for the agent's lifetime. That is one more object carrying keys (T-3).
  Smallest fix:
  - `BrowserAgent.__init__` queues each server with `with_preset_mcp_server(...)` or `with_mcp_server(...)`, using the `browser-<role>-<n>` name.
  - `BrowserAgentTools` keeps only the role split (`tools(servers, role)`) and holds no key. Drop `configs()` from §8.5.

R-8 [Minor] [L8] §12.3 row 5, §8.4 "registration only" — Adding `GOAL_STALLED` touches an `@intent` invariant that §12 does not list.
  Evidence:
  - Row 5: "add `GOAL_STALLED`… with no other change".
  - Code, `vidbyte/sessions/failure/router.py:52-54`: "@intent stop-codes-cover-agentstopreason — Every … AgentStopReason member is accounted for here except FINAL_RESPONSE and IS_DONE".
  - Without a row, `_STOP_CODES.get` maps an unknown value to `FailureCode.RUNTIME_ERROR` (`:118`).
  Failure: A reviewer who applies the intent comment flags the new member. If a stalled stop ever reaches the normalizer, it is reported as a runtime error.
  Smallest fix:
  - State in row 5 why no `_STOP_CODES` row is added: `Session` refuses `BrowserAgent` (INV-22), and `FINISH_REVIEW_REJECTED` is already unmapped on main.
  - Alternatively, map it to an existing `FailureCode`. Adding a new `FailureCode` would trip the harness_threads count test noted in §11.

VERIFIED CLAIMS

1. **Hooks and their signatures.** `_continue_finish_attempt` (`runtime.py:917`), `_after_tool_iteration` (`:925`) and `_budget_stop(*, iteration_count, tokens_used, contexts, started_at)` (`:2046`) exist with the signatures in §8.5. `_stopped_result` is at `:2091`. HELD.
2. **The action cap stops the run.** The `max_tool_calls` check runs at the top of every iteration (`:367-374`, `:2071-2080`) and stops mid-turn (`:1862-1870`). `ToolSettings.max_calls` feeds the same stop (`:1865`), so no existing setting denies a call past a total count and lets the run continue. HELD.
3. **"`_runtime()` builds the runtime 3 times per run" (INV-23).** PARTLY HELD. A direct run builds it twice, at `:1280` and `:1319`. Line `:1388` belongs to `_run_with_tools`, a separate path. MCP connects at `:916`, before both builds. INV-23 still holds.
4. **Shared session.** `_own_tool` passes `McpBridgedTool` through (`base.py:473-493`). A sync `run()` closes the servers and re-queues them (`mixins.py:246-262`). The transport is bound to its event loop (`transport.py:152-160`). HELD.
5. **MCP output.** Image placeholder at `client.py:136-143`; 8,000-character cap at `:31` and `:109-111`. HELD.
6. **Compaction helpers.** The sliding window is per tool (`strategies.py:683-695`), and the file is 1,020 lines. Compaction is outgoing-only (`context_compaction.py:217-229`). The constructors `trim_with_provider_boundaries` and `tool_output_sliding_window(keep_recent, window_mode, max_chars)` match the spec. HELD.
7. **Tool settings.** `ToolSettings.max_calls_per_tool` is a name-to-int map that denies and continues by default (`tool.py:39`, `:58-60`). HELD.
8. **MCP presets and environment.** `McpPresetRegistry.get` is at `:370` and `build_config` at `:384`; the `build_child_env` allowlist is unchanged. HELD. The spec does not cite `with_preset_mcp_server` (`mixins.py:180`); see R-7.
9. **Lint rules.** A001, A002, A003, A006, A007, A009, C001, C007, C008, C011, C012, C015, C016, S009, S015, S019, S020, S025, S027, S039, S051 and S060 all exist in `lint/rules/`. `lint/run.py` takes `--rule`. HELD.
10. **Gate and contract commands.** `scripts/run_ci.py --stage all|source|package` (`:260-262`). `generate-sdk-public-api.py --check`, and its refusal while inputs are uncommitted (`:9`, `:129`). HELD.
11. **"`llms.txt`/`artifacts/file_index.md` mention no agent package."** Mostly HELD: "infinite" appears 0 times in both. `llms.txt` mentions JevAgent once. Neither the touched lib folders nor `vidbyte/agents/README.md` has a `## File Index`, so S020 applies only to the new package README.
12. **Tests that iterate `AgentStopReason` (INV-29).** All three exist at the cited lines. HELD. `router.py:52-54` was missed; see R-8.
13. **Usage helpers.** `JevUsageAccount.failures` is a classmethod and `unpriced` a staticmethod (`jev/usage.py:72-91`). HELD. Note: this would be the first time one agent package imports another agent package's internals (`git grep "from vidbyte.agents.jev"` finds only `agents/client.py`, `agents/__init__.py` and the registry), and importing `jev.usage` loads all of `vidbyte/agents/jev/__init__.py`. That is acceptable under D-19's flip condition. Moving the helpers to lib would rewrite untouched Jev code.
14. **Infinite's patterns.** The root uses `trim_with_provider_boundaries` (`infinite/agent.py:80`). The run-local copy of the context manager, the TOP_OF_CONTEXT upsert, the popped tools option and the reserved-name clash check are at `infinite/runtime.py:70-93` and `:104-115`. HELD.
15. **Events.** `InfiniteEvents` is not cited as existing code (§11 (d)). HELD. D-18's MultiAgent precedent is PARTLY HELD: `ledger_controller.py:171` awaits async callbacks through `AgentTransfer.maybe_await`, the opposite of D-18's refusal of async sinks. The refusal is still a defensible choice.
16. **Test seams.** `MockMcpStdioTransport` (`tests/test_mcp_attachment.py:49`), its patch at `:119`, `build_test_agent` (`tests/agent_test_support.py:68`), `ScriptedTree`/`ModelCall`/`reply`/`tool_call`/`fail` (`infinite_memory_fixtures.py:135-288`), and `_runner_for_model` (`base.py:1659`). HELD. Every INV and AC can be tested with fakes. AC-1 is the §4 snippet. The spec contains no test cases.
17. **Placement.** Pydantic payloads live in `vidbyte/lib/dataclasses/` (`JevReviewPayload`, `jev.py:3981`). `UsageRollup` is imported under TYPE_CHECKING (`jev.py:99-100`). HELD.
18. **Internal counts.** 33 new files and 12 modified files match the rows in §12.3. §5, §8.5 and §12.3 use the same names. Every §9.3 key is used. HELD.
