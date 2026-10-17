VERDICT: SOUND WITH FIXES — All eight round-1 fixes landed and hold against the code. Four new Majors remain: two acceptance criteria a blind test cannot observe, an r1 remnant in EC-12, and two gaps in the rebuild. Each is a local text edit to the spec, and none touches a settled decision.

Reviewed: spec.md r2 (commit f09bf057; HEAD faec6cb3 changes no spec text), against the worktree code at base 08f67e7f. Scoped round-2 review: the r1→r2 diff, every section the diff touched, and the dependents named in the brief. Each of R-1..R-8 from round 1 was checked against the code.

R-1..R-8 STATUS (round 1 → r2)

- R-1 rebuild — FIXED, with two gaps (R-3, R-4 below). The in-place cut is safe on the path it covers. The task survives through `prompt_index` on every chat provider. `context_rebuilt` and `rebuilds` are wired through §8.5, row 13, FR-19 and AC-22.
- R-2 stuck-card evidence — FIXED. `last_reply` is set before the schema check raises, and its metadata carries the raw call contexts. `BROWSER_EPISODE_REPLY_TURNS` has a real consumer: it is a hard bound that never binds first. EC-12 was not updated (R-2 below).
- R-3 card re-pinned after a refused finish — FIXED (INV-14, INV-16, AC-13, row 16, EC-36, `{gap}` on `goal_card`).
- R-4 progress capacity — FIXED (EC-37, `progress_full`, AC-32, Q-10 marked [scope-adding] with default no).
- R-5 screenshot prompt — FIXED (worker leaf, D-23, A-9).
- R-6 kept observations — FIXED. The per-tool reading is disclosed, not silent (see below). One test-measure gap is in R-1 below.
- R-7 `configs()` — FIXED. No `configs()` remains outside the §16 log. The mixin builders and handle naming work as D-7 says.
- R-8 stop-code intent — FIXED. Row 5's rationale matches the code.

WHAT THE SPEC GETS RIGHT

- **The rebuild cut is correct on the path it covers. Do not move the card into a message.**
  - The loop keeps one `messages` list, which `state.messages` also points to. With `history=()`, `caller_messages` is empty, so deleting in place reaches both (`vidbyte/agents/runtime.py:314-321`).
  - A tool iteration appends only the assistant call turn and its tool results (`:606-612`, `:1952`). So "everything before the last assistant turn" never separates a call from its results.
  - The task is never stored. Every chat provider puts it in front of a list that opens with a call turn: `anthropic.py:82`, `compatible.py:76` (xAI and OpenRouter subclass it), `openai.py:269`, and `gemini.py:74,81-103`, which moves the task ahead of a leading `model` turn.
  - The card in the system prompt matches the user's own §B words, "re-rendered at the top of the orchestrator's context".
- **R-2's evidence path is real, so keep it.**
  - `last_reply` is set at `vidbyte/agents/base.py:1007-1009`, before `_assert_schema_satisfied` raises at `:1022`.
  - A cap stop's metadata carries `tool_calls` as `ToolCallContext` records with the raw `result` (`runtime.py:2091-2127`, `lib/dataclasses/tools.py:342-357`).
  - AC-7's count holds: three calls, then `_budget_stop` fires before a fourth model call (`runtime.py:2072-2080`).
  - `max_iterations` defaults to None (`settings/loop.py:52`), so `max_actions + BROWSER_EPISODE_REPLY_TURNS` is a real backstop, not dead code.
- **R-6's per-tool reading is honest, not a silent substitution.**
  - It is disclosed in D-10, §11 (f), Q-4 and Q-6.
  - Its reason is grounded in the code and the rules: the window keys on the tool name (`strategies.py:683-695`), the engine also names Anthropic results through their `tool_use` ids (`engine.py:144-154`), and AGENTS.md principle 3 applies to the 1,020-line `strategies.py`.
  - `BROWSER_WORKER_HISTORY_MAX_TOKENS` is a constant, not a settings knob. It enforces the bounded worker that the user asked for, by the Infinite children's pattern (`infinite/launch.py:290`). So it is not [scope-adding]. Keep Q-6 visible in the summary to the user.
- **The internal counts reconcile.**
  - New files: 10 modules, the README, 3 lib modules, 1 JSON descriptor, and 19 leaves, for 34 in all. This matches §8.4, §12.3 and §11's layout.
  - §9.1 lists exactly 19 leaves.
  - Modified files: 12.
  - Every new constant has a consumer.
  - `grep "configs()\|FINAL_TURNS"` finds them only in the §16 log, and the orchestrator trim middleware appears only as §8.3's rejected design.
  - No test pins the counts of prompt families or leaves.

FINDINGS (ranked, most severe first)

R-1 [Major] [L10] §6.2 AC-22, AC-31, AC-7; §6.1 INV-11; §13 — AC-22 and AC-31 assert where the task sits "in the call's messages", which the seam named in §13 never shows. A blind test written from them fails against a correct implementation.
  Evidence:
  - What the ACs say:
    - AC-22: "the call's messages are the task, then the last assistant tool-call turn and its results, and nothing older."
    - AC-31: "the outgoing messages fit `BROWSER_WORKER_HISTORY_MAX_TOKENS` by `TokenEstimate`, … and the task is still the first message".
    - §13: "The task is never in the stored `messages`. The provider inserts it at `prompt_index`".
  - What the seam records:
    - `ModelCall(agent, prompt, system, messages, tools, tool_schemas)`. `_record` copies `prompt` and `options["messages"]` separately and drops `prompt_index` (`tests/features/infinite_memory_agent/infinite_memory_fixtures.py:253-262`, `:320-335`).
    - `ScriptedTree` replaces the runner, so no provider ever inserts the task.
  - What the trim counts:
    - `TrimWithProviderBoundariesCompaction` counts each message's content text at ceil(len/4) (`vidbyte/middleware/compaction/strategies.py:50-68`, `:624-635`). It does not count JSON.
    - INV-30 counts the orchestrator "over their JSON text", so the spec uses two different measures.
  - INV-11 says each tool's newest results "are sent in full". But the trim keeps or drops whole groups, newest first (`strategies.py:629-635`).
  - AC-7: "Its `evidence` holds the third call's observation text, cut to `BROWSER_STALE_OBSERVATION_CHARS`". It does not say whether the cut adds a marker, while AC-9's cut does ("with the truncation note").
  Failure:
  - **AC-22.** The test author asserts `call.messages[0]["content"] == task`. That is red against a correct implementation. §14 forbids the implementer from changing the test, so the build stops BLOCKED.
  - **AC-31.** A test that sums `TokenEstimate.count(json.dumps(m))` adds JSON keys, quotes, and escaped snapshot newlines (roughly 10–30% more). A correct trim near its edge then reads as over budget.
  - **INV-11.** A test pinning INV-11 with many tools contradicts AC-31 as soon as the trim drops an old turn.
  - **AC-7.** A test of `evidence == (output[:400],)` fails if the implementer adds a cut marker.
  Smallest fix:
  - AC-22: "the recorded orchestrator call's `messages` are exactly the last assistant tool-call turn and its results; its `prompt` is the task". If the placement itself matters, add "and its options carry `prompt_index == 0`", and say the fixture must record that key.
  - AC-31: "the recorded worker call's `messages`, summed as `TokenEstimate.count` of each message's content text (the trim's own measure), fit …; its `prompt` is the task".
  - INV-11: add "unless the history trim dropped that result's whole turn".
  - INV-12 and AC-7: state the evidence cut exactly. For example: "the first `BROWSER_STALE_OBSERVATION_CHARS` characters, with no marker".
  - §13: add one line on how fakes reach the caps:
    - the orchestrator's 60,000 tokens take about 13 calls of a `settings.tools` extra that returns `BROWSER_TOOL_RESULT_MAX_CHARS` characters;
    - the worker cap needs enough distinct fake ACTION tools, with `keep_observations=1`, that their newest full results pass 32,000 tokens.

R-2 [Major] [L9] §6.3 EC-12 — EC-12 still carries the r1 text "`actions` is None", which contradicts r2's INV-12, EC-11 and row 15 for the same code branch.
  Evidence:
  - The spec, three ways:
    - EC-12 (spec.md:346): "`stuck` card. Its summary is the `stuck_summary` leaf naming the stop reason. `actions` is None." This is word for word r1's EC-12 (r1 spec.md:329).
    - INV-12: "A `stuck` card built after the worker ran (cap stop or schema miss) carries evidence…: `actions` is the exact number of browser calls the worker made".
    - Row 15, step 4: "On `OutputSchemaViolationError` (caught first), build the `stuck` card from `worker.last_reply`, with the exact `actions`, `evidence`…".
  - The code: a free-text reply goes through `max_contract_rejections` repairs, ends `contract_unsatisfied` (`runtime.py:523-535`), and raises `OutputSchemaViolationError` after `last_reply` is set (`base.py:1007-1022`). That is the same branch as the cap stop.
  - A related gap: `stuck_summary` takes `{reason}` `{actions}` (§9.1). The one card whose `actions` really is None, from a worker that raised before replying (row 15 step 4), has no rule for what `{actions}` renders.
  Failure:
  - The test author writes one test from EC-12 (`actions is None`) and one from INV-12 and AC-7 (an exact count) for the same branch. One of them is red whatever the code does.
  - A provider-error card renders "None" into the summary text the orchestrator reads.
  Smallest fix:
  - Rewrite EC-12's behavior cell: "a `stuck` card built from `worker.last_reply` as in INV-12: summary is the `stuck_summary` leaf with stop reason `contract_unsatisfied`; `actions` is exact; `evidence` is the newest successful observation".
  - In row 15, say what an error card's summary is. Either fill `{actions}` from a named constant for "unknown", or give error cards a summary that does not use `stuck_summary`.

R-3 [Major] [L5] §6.1 INV-30, D-11, NFR-4, §12.3 row 16 — The rebuild runs only in `_after_tool_iteration`, and the loop skips that hook after every refused finish. So NFR-4's history bound fails on a reachable path.
  Evidence:
  - The spec:
    - INV-30: "rebuilt after a tool iteration when its stored messages pass `BROWSER_HISTORY_MAX_TOKENS`".
    - Row 16 places the rebuild only in `_after_tool_iteration`.
    - NFR-4's sum: "Stored history at most 60,000, because a rebuild runs after any tool iteration that passes it".
  - The code: a refused `isDone` sets `finish_attempt_continued` and reaches `continue` at `runtime.py:680-688`, before `_after_tool_iteration` at `:700`. §13 states this skip itself.
  - INV-17: a recheck is not a stall when progress changed.
  Failure:
  - Picture an orchestrator whose every turn is `run_episode`, `patch_goal(progress, …)`, `isDone`. Each recheck returns `continue` with a gap. Progress grows, so no stall is counted.
  - No iteration reaches `_after_tool_iteration`. Stored history grows by one card, one patch result, one refusal and one gap, about 1,000–1,500 tokens per turn, with no rebuild and no `context_rebuilt` event.
  - Some 60–80 such turns past the cap, the call exceeds a 128,000-token window, and the provider refuses it, hours into the run.
  - Separately, EC-35's first-iteration case: when the only exchange already passes the cap, nothing is deleted, yet row 16 still counts a rebuild and emits `context_rebuilt`.
  Smallest fix:
  - Make the rebuild one private step that both hooks call: `_after_tool_iteration` as now, and `_continue_finish_attempt` on its refusal branch, before it appends the `continue_prompt` message.
  - At that point, the last assistant turn is the refused `isDone` turn, or, on the final-text path, the previous call turn. So the cut stays whole on both paths.
  - Emit `context_rebuilt` and call `response.rebuilt()` only when a message was actually removed.
  - Update INV-30 ("after a tool iteration or a refused finish"), row 16, NFR-4, and EC-35.

R-4 [Major] [L4] D-11, INV-30, §9.1 `BROWSER_ASSISTANT_ROLES`, §11 (e) — The rebuild's own role scan re-implements the compaction engine's provider grouping. The field guide's "Reuse shared context compaction infrastructure" check flags exactly that.
  Evidence:
  - The spec:
    - Row 16: "find the last message whose role is in `BROWSER_ASSISTANT_ROLES`, `del messages[:index]`".
    - §9.1: `BROWSER_ASSISTANT_ROLES = ("assistant", "model")`.
    - §11 (e) argues the user's decision overrides the field guide.
  - Field guide `runtime-boundaries.md:3-8`:
    - When: "A direct runtime needs to trim provider-visible history for a context budget".
    - Do: "Call `ContextCompactionEngine` through the provider-boundary-aware compaction path".
    - Check: "no bespoke compaction algorithm is introduced".
  - What the engine already does:
    - `ContextCompactionEngine.compact_provider_messages` (`vidbyte/middleware/compaction/engine.py:56-68`) classifies call and result turns by shape for OpenAI, Anthropic and Gemini (`:311-330`).
    - It groups each call with its results (`strategies.py:23-34`).
    - Under `TRIM_WITH_PROVIDER_BOUNDARIES` with `max_messages=1`, it keeps exactly the newest whole group (`strategies.py:613-622`).
    - It repairs call/result pairing, and it returns untouched messages as plain copies (`engine.py:300-307`).
  - AGENTS.md principle 5 asks for one canonical helper per job.
  Failure:
  - A reviewer who applies the entry asks for the engine, and the author has no round left to answer.
  - The role constant is a second definition of "where a tool exchange starts". It must be kept in step with the engine's shape rules by hand.
  - The user's decision fixes what the rebuild keeps, not the helper that computes it, so §11 (e) does not answer the check.
  Smallest fix (in the same edit as R-3):
  - In that one private step, compute `kept, stats = await ContextCompactionEngine().compact_provider_messages(messages, mode=CompactionMode.TRIM_WITH_PROVIDER_BOUNDARIES, options={"max_messages": 1})`, then assign `messages[:] = list(kept)` in place. `stats` can feed the event detail.
  - Delete `BROWSER_ASSISTANT_ROLES`.
  - Restate D-11 and §11 (e): the user's rebuild (stored history, nothing summarized, the last exchange kept whole) is applied through the shared engine, so the field-guide entry holds too.
  - This edits no file under `vidbyte/middleware/`, so NG-12 and NFR-2 still hold.

VERIFIED CLAIMS

1. **The in-place rebuild is safe for the loop (brief R-1a).** HELD.
   - `messages` is one list that `state.messages` also holds, and `caller_messages` is a tuple of the empty initial list (`runtime.py:314-321`).
   - The loop and its fallback re-read the list each iteration (`:447-448`).
2. **The cut keeps each call with its results (brief R-1b).** HELD on the `_after_tool_iteration` path.
   - Only assistant turns and tool results are appended (`runtime.py:542-608`, `:1952`).
   - Call turns have role `assistant` (`lib/tools/formatter.py:381,396`) or Gemini's candidate content. Results have role `tool` or `user` (`:476`, `:484-498`).
   - Not held on the refused-finish path, which never runs the rebuild (R-3).
3. **The task survives the cut on every provider (brief R-1c).** HELD.
   - `_run_boundary` returns the index of the first stored message (`runtime.py:1645-1653`).
   - `PromptPlacement.index` honors it (`lib/util/prompt_placement.py:29-48`). Gemini puts the task ahead of a leading `model` turn (`providers/gemini.py:81-103`).
   - The providers that place the task are `anthropic.py:82`, `compatible.py:76`, `openai.py:269` and `gemini.py:74`. `xai.py` and `openrouter.py` subclass the compatible provider, and `typesafe.py` is not a chat provider.
4. **The card is in the system prompt (brief R-1d).** HELD.
   - It renders in the primitives zone of the system string (`runtime.py:1667-1676`, `context/manager.py:208-240`).
   - PARTLY HELD: D-11's reason "the loop has no seam to put a message ahead of the task" is not accurate. `TOP_OF_CONVERSATION` renders primitives as assistant-role messages ahead of the stored ones (`runtime.py:1655-1661`, `manager.py:219-226`). The system placement is still the better choice, so only the reason is off.
5. **A refused finish skips `_after_tool_iteration` (brief R-1e).** HELD (`runtime.py:680-688` versus `:700`). This is the source of R-3.
6. **The stuck-card evidence exists (R-2).** HELD.
   - `last_reply` is set before the schema check raises (`base.py:1007-1022`), and `_runtime_metadata` carries `tool_calls` (`runtime.py:2111-2127`).
   - `ToolCallState.SUCCEEDED` is at `lib/dataclasses/tools.py:60`. Every worker call shows `max_tool_calls: n/N` (`runtime.py:1693-1694`).
   - `_budget_stop` checks `max_iterations` before `max_tool_calls` (`:2055-2080`). `max_contract_rejections` defaults to 3 (`settings/loop.py:66`).
7. **The mixin builders and handle names (R-7).** HELD.
   - `with_preset_mcp_server(preset_name, *, name, permission, env, timeout, extra_args)` builds through `McpPresetRegistry.build_config` and renames (`mixins.py:180-196`). `with_mcp_server` is at `:147-170`.
   - `McpServerHandle.name` returns `config.name` (`tools/mcp/types.py:61-64`).
   - Tool-name clashes raise `ToolRegistrationError` (`tools/catalog.py:37-38`) inside the all-or-nothing attach (`mixins.py:97-145`).
8. **The worker middleware composes as stated (R-6).** HELD.
   - The sliding window counts per tool (`strategies.py:683-695`), and that file is 1,020 lines.
   - Stacked transforms compose (`middleware/pipeline.py:155-185`). The runtime keeps the task's position after a rewritten head (`runtime.py:1094-1109`).
   - Infinite's children use `trim_with_provider_boundaries(max_tokens=…)` at `infinite/launch.py:290`.
   - The trim's measure is content text, not JSON (R-1).
9. **The stop-code intent (R-8).** HELD.
   - The intent comment is at `sessions/failure/router.py:52-54`, and `finish_review_rejected` is missing from `_STOP_CODES`.
   - `FailureMetadataNormalizer` is used only from `vidbyte/sessions` and exports.
10. **Row anchors.** HELD.
    - `lib/enums/__init__.py:80-86` (the infinite block), `agent_runtime.py:52`, and `runtimes.py:30-34` (lazy `resolve`).
    - `agents/__init__.py:84-89`, `base.py:83`, and `base.py` lines 916, 923, 1280, 1319, 1388, 1494 and 1659.
    - The agents README is 29,527 characters and the prompts README 31,924. `REPO_MAP.md:83` is the infinite row.
11. **Test seam.** PARTLY HELD.
    - `ScriptedTree` and `ModelCall` exist as §13 says.
    - But `ModelCall` keeps the task in `prompt`, not in `messages`, and drops `prompt_index` (fixtures `:253-262`, `:320-335`). This is the source of R-1.
12. **Counts and remnants.** HELD.
    - 34 new files, 19 leaves and 12 modified files.
    - No `configs()` or `FINAL_TURNS` remains outside §16.
    - No test pins prompt-family counts.
    - EC-12 is unchanged from r1 (R-2).
