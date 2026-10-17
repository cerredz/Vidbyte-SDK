# S1 spec author report — infinite-memory-context-economy r1

Spec: `docs/spec/infinite-memory-context-economy/spec.md`, committed as `6a5a7999` on `feat/infinite-memory-context-economy`, base `0f2aeb48`.

## What I read

**Orchestrator inputs:** `request.md` (all of it), `context/code-map.md` (all of it), `pipeline.md`, and the spec template.

**Rules:**
- `AGENTS.md` and `REPO_MAP.md`: the builtins, toolsets, and infinite entries.
- Folder READMEs: `vidbyte/agents/infinite/README.md`, `vidbyte/agents/README.md`, `vidbyte/tools/README.md`, `vidbyte/providers/README.md`, `vidbyte/lib/README.md`, and `vidbyte/prompts/README.md`.
- Lint rule headers for A002, A006, A007, C006, C007, C008, C015, S008, S020, and S025, plus `lint/baseline.json`.

**Code, item by item:**
- **Item 1:** `vidbyte/lib/dataclasses/filesystem.py`, `coding.py`, `tools/filesystem/read_lines.py`, and `write_text.py`.
- **Items 2 and 4:** `middleware/compaction/strategies.py`, `engine.py`, `context_compaction.py`, and `__init__.py`.
- **Items 3 and 8:** `tools/builtins/code_search/{base,grep,semantic,__init__}.py`, `lib/dataclasses/code_search.py`, and `lib/util/__init__.py`.
- **Item 6:** `tools/builtins/bash.py`, the whole file.
- **Item 9:** `providers/anthropic.py` and `agents/base.py:_runner_for_model`, which caches the runner per agent, so one adapter instance serves a whole run.
- **Item 7:** `agents/runtime.py`: the loop state, `:471`, `:670`, `:700`, `:925`, `:1596-1700`, and `:2118-2127`. Also `context/manager.py`, which confirms that TOP_OF_CONTEXT items render in the system zone.
- **InfiniteMemory:** every module in `agents/infinite/`, `tools/toolsets/infinite.py`, and `lib/{constants,enums,dataclasses,registries}/infinite.py`. The `infinite_memory` prompt family and its JSON.
- **Settings and validation:** `agents/settings/loop.py`, which shows that `AgentLoopSettings` is a plain class, so `dataclasses.replace` does not apply. `lib/dataclasses/validation.py:to_folder`, which accepts a missing folder, so the §4 snippet holds.

**Tests:**
- `test_infinite_memory_contract.py`: `BUDGET_MODULES`, the budget test, `EXPECTED_LEAVES`, `PRESET_TOOLS`, and the registry test.
- `test_infinite_memory_delegation.py`: `:63-65`, `:134`, `:305-316`, and `:535-549`.
- `infinite_memory_fixtures.py`: naming and the `ScriptedTree` seam.
- The coding-agent tests that read `["system"]`: they read runner kwargs or the first request.
- The two tests that build an `AnthropicProvider`.

**Backend (read only, before compaction):** the generative gateway `client.py` (`:119`, `:122`, `:259-277`) and its refusal and fake tests.

**Measured with a script:** the lines after the header for all 12 budget modules. `memory.py` has 149 lines of headroom, `launch.py` 32, and `workspace.py` 68; the infinite package already has 8 modules.

## Approaches weighed

**Smallest design (rejected, §8.3):** unscoped masking, a frozen map, a top-level `cache_control`, and the loop block left in place.
- Unscoped masking replaces `launch_subagent` cards, which exist only in history.
- `primitive_frozen` makes the existing re-upsert raise.
- The `max_iterations: n/500` line keeps the system string changing.
- The gateway refuses a top-level `cache_control`.

**Item 4: stateless quantized hysteresis (chosen) versus a `run_state` cut point.** The strategy is rebuilt on every call, and `run_state` is keyed by type, which collides when masking and trim are both `MessageHistoryCompactionMiddleware`. Dropping whole multiples of S = max − low gives the same "cut once per about 25K tokens" behavior as a pure function of the history, with no state and no reset rule. The fallback when low ≥ max keeps `test_infinite_memory_context.py:46`, which patches the cap to 250, green.

**Item 9: repeat-gated marks (chosen) versus "mark whenever there is history" versus "mark always".**
- Many agents set `max_iterations`, so their system string changes on every call: InfiniteMemory children, Jev subagents, critics. Any stateless rule would charge them 1.25× on every call for nothing.
- Gating on "this adapter already sent these exact tools and system" means a mark appears only on a prefix that can actually be read back. That also answers Q-ORCH-2: one-shot calls never pay the premium.

**Item 7: a status user message after tool results (chosen).** Rejected:
- the delta inside the newest tool result: three provider shapes, and "newest" is ambiguous in a parallel batch;
- END_OF_CONVERSATION: it renders as a trailing assistant message, which Anthropic treats as prefill.

The precedent is the review-feedback user message at `runtime.py:670`. The root's loop block is dropped by overriding `_build_system_string`, not `_render_loop_settings_block`, so the base renderer stays reusable for the status message.

**Item 8 placement: a code-search module (chosen) versus the toolset module.** REPO_MAP says the toolsets folder "is about convenience and consistency rather than introducing any new tool capability itself". `BaseCodeSearchTool` already supplies the ignore rules, the byte cap, the NUL skip, and grep-identical line numbering. This adds a third `.py` file (13 new files in total), where my earlier plan had 12.

**Item 10 citation parsing:** a `parse` classmethod on the record (precedent `lib/dataclasses/prompts.py:42`). Ranges are copied through the agent's own windowed `read_lines` and entries through `InfiniteWorkspace.entries`. This keeps `memory.py` under the 400-line budget and checks citations with the same scoping the retriever read with.

## Where I disagree with the request or the scout

1. **request.md §C says "a stateless view cannot trim to 65K once".** The stateless quantized rule (INV-4.2, D-5) shows that it can: the cut moves only when `ceil((N−B)/S)` changes. I proceeded as decided on the 65K value. The only thing I did not adopt is the implied need for run state.
2. **request.md §C: "the retriever is a fresh BaseAgent (new role RETRIEVER)".** I build the retriever without a role (D-14, NG-15, Q-9, default no). The registry grants preset tools (`remember`, `write_note`) to every role, and `test_infinite_memory_contract.py:383-387` asserts that for every `InfiniteAgentRole` member. A RETRIEVER member would either hold memory tools, which contradicts the settled tool list, or break that tested invariant. The substance of the decision is kept: a fresh agent, exactly `search_memory` + `grep` + `read_lines`, a cap of about 8 turns, and citations copied from disk. The code-map raised the same contradiction (§4, item 10).
3. **The footer in the handoff uses an en dash ("A–B").** The spec uses an ASCII hyphen (`lines 1-200`) for predictable tokenization and grep. This is cosmetic, but the §4 snippet pins it.
4. **Code-map line anchors.** `vidbyte/agents/README.md:122` is not the bash line; the bash line is `:146`. The request's anchors `agent.py:87` and `launch.py:313` are `:80` and `:290` on main. The spec uses the verified lines.
5. **Request: "the four BASH_* constants".** Item 6 adds a fifth (`BASH_TAIL_OUTPUT_BYTES`), because the head/tail split needs a named size (A007). The four existing values are unchanged, so the bounds-tuple test stays green.
6. **Request: "Reuse `ToolOutputSlidingWindowCompaction`".** `strategies.py` is already 1,020 lines, so the two edited classes move to a new `windows` module (D-3). AGENTS.md principle 3 forces this; it is not scope creep.

## Least-sure assumptions

- **A-1, FTS5 on Linux CI.** This is unverified. If it is absent, the FTS5 tests fail on CI, and the user must decide how CI gets FTS5. Never skip the tests.
- **A-6, the gateway forwards block-level marks unchanged.** Admission is verified in backend code; forwarding is not verified live. The real-key check in §12.5 settles it.
- **A-2, a user message right after tool results is accepted by every provider.** It rests on the `runtime.py:670` precedent and Anthropic's merging of consecutive user turns. I did not verify Gemini's behavior live.
- **A-3, the retriever's `AgentMessage.metadata["tool_calls"]`.** It is seen in the runtime's result metadata; I did not trace it through `BaseAgent.arun`. Only the card's searches list depends on it.
- **A-9, the recall quota of 10 and 8 terms.** The conversation fixed that a quota exists, not its value.
- **Budget risk.** `InfiniteRecallTool` must fit in about 149 lines of `memory.py` headroom. D-16 moves parsing and file reading out. If it still overflows, the implementer must report BLOCKED (§14), not grow the package.

## Addendum: r2 (S1 review round 1, commit 631fefbc)

The verdict was SOUND WITH FIXES with 12 findings (2 Blocker, 5 Major, 5 Minor). All 12 are accepted. None reversed a settled decision, and none was scope-adding. R-6's optional part, a monotone cut, is a review-suggested control, so it became Q-11 (default: not built). §16 records each disposition.

**What I re-verified before editing**
- **C006.** `python lint/run.py --rule C006 --all` passes at the baseline. The moved classes carry their existing findings at `strategies.py:599`, `:601`, and `:670`; moving them keeps the count. `MessageHistoryCompactionMiddleware._validate_options` is not a C006 site, so adding `low_watermark_tokens` to its key loop adds nothing. The safe shape is `RecordFieldValidator.require_int`/`require_bool`, or the inline `isinstance(x, bool) or not isinstance(x, int) or x < bound`.
- **Backend.** `_require_short_cache` spans `backend/provider/generative_models/client.py:260-278`. The review said `:276`; the last line is `pending.extend(node.values())` at `:278`. `plan()` builds `wire` at `:176`, and `send()` posts `plan.wire` at `:195`.
- **The R-5 precedent and seams.** `semantic.py:78-81` (`asyncio.to_thread`, `@intent semantic-search-runs-off-the-event-loop`) is the precedent. `InfiniteWorkspace` is built once, at `agent.py:58`. `launch.workspace` and `memory.workspace` reach it, so an attribute on the workspace needs no new plumbing. The only test reference to the toolset is `callable(InfiniteMemoryAgentTools.get_tools)` (`test_infinite_memory_contract.py:162`), so the new required `index` breaks no test.
- **Bash.** `_collect` is cancelled by `wait_for` on a timeout, which loses its local `omitted`. The count therefore moves into a one-item list that `execute` owns (§8.5). With that change the timeout marker can show the real count instead of a vague "middle not shown".

**Options I weighed for R-6**
- *Original-size measure:* count masked outputs at their `original_chars`. It is stateless and monotone, so it never dips. But the root's old history is mostly masked read outputs, so the trim would keep far less than B. That gives up history the context could hold and undercuts D-2. Rejected.
- *`run_state` cut that only moves forward, under a private key class:* this removes the dips. But the engine's strategy API is stateless (options in, view and stats out), so it needs plumbing through the middleware, the engine, and the strategy, plus a reset rule between runs. It is now Q-11, default no. The §12.5 real-key run counts cut moves to decide it.
- *Chosen:* state the cost, which is two full-history writes per dip at about net drop / S per masking event. Scope NFR-4.1 to the bare strategy. Pin the behavior with AC-4.4 (equal-size outputs: at most `ceil(G / S)` moves) and AC-4.5 (one dip: two moves).

**Choices inside the accepted fixes**
- **R-3.** The cap reuses the map's own rule and constants (`INFINITE_MAP_MAX_TOKENS`, `INFINITE_MORE_FILES`). The rule is lifted from `map_text` into `InfiniteWorkspace.fit_map_lines`, so one cut serves both (principle 5). This adds no constant and no mechanism. A new marker sentence in constants would break that file's WHAT NOT TO DO 2. The no-change status message is bounded at 150 tokens (NFR-7.2): about 60 for the header, 35 for the loop block, and the rest for the leaf text.
- **R-4.** `INFINITE_BOOKKEEPING_NAMES` matches any part of the resolved path, case-folded, so `Superseded.jsonl` on Windows and a link into `.runs/` are refused too. `search_memory` keeps the base class's exact-part ignore rule.
- **R-5.** `FullTextIndex()` now opens nothing, and FTS5 is probed on first use. Building it inside the workspace therefore never breaks agent construction (INV-8.7). Its lock is a public `RLock`, so one call can hold it across the refresh and the search. Two agents refreshing the same file at once can then never leave a stale row for the other's search.
- **R-7.** I chose the reorder, not a `{found}`-only cap: the same single cut at the end, with transcribed text last.

**Remaining risks**
- The root now appends a status message on every tool iteration. A no-change message carries the header and the loop block, about 110–150 tokens each. Over 50 retained iterations that is about 5–7K tokens of history. Sending only the loop block when nothing changed would save about 80 tokens an iteration, but EC-7.5 relies on the newest message carrying the totals. I kept the shape; it is a possible later trim, not built.
- §8, §8.5, §9, and §12.3 changed (new `index` parameters, `full_text`, `fit_map_lines`, `_collect`'s signature, `INFINITE_BOOKKEEPING_NAMES`, the card order). A focused round-2 review is warranted.

## Addendum: r3 (S1 review round 2, approved, commit 75789419)

The verdict was SOUND WITH FIXES, with 12 findings: 2 Blocker, 2 Major, 8 Minor. I accepted all 12. R-13's scope-adding idea, masking every status message except the newest, is recorded as Q-12 and not built. Per the orchestrator, the frontmatter now says `status: approved`, `revision: 3`. §16 records each finding and what I did with it.

**What I checked before editing**
- **`test_infinite_memory_context.py:46` (R-13).** Its four `fetch_page` iterations write nothing to the workspace. With the R-13 fix, each status message is the loop block alone. I measured that block with the default loop at 130 characters, or 33 tokens. The review found the test passes at 89 tokens, so it stays green. A loop that also sets `max_tokens` and `max_tool_calls` gives 48 tokens, so NFR-7.2's no-change bound is 40 tokens with the default loop.
- **`TokenEstimate.cap` (R-15).** It returns `text[:max*4] + marker`, so a cut card counts `max + ceil(len(marker)/4)` tokens. Capping at `CAP - TokenEstimate.count(MARKER)` keeps a cut card at most CAP while still using the one canonical helper. The cost is that a card within 2 tokens of the cap loses up to 8 characters it did not strictly need to lose.
- **The loop-block call (R-22).** `runtime.py:396-407` passes `tool_call_count=len(self._non_internal_tool_contexts(state.call_contexts))` under `@intent internal-tools-never-spend-the-tool-budget`. Row 25 copies that call.
- **`Tools.without` (`catalog.py:90`).** It removes exact tool objects, not names. Rows 22 and 23 and §11 now say to filter by `tool.name`.
- **The request's recall wording (R-24).** It reads "code pre-runs `search_memory(terms)`". One search per term honors that wording and the settled AND-of-quoted-words search, and adds no new mechanism. An OR retry would be a fallback, and that stays Q-8, default no.

**Choices inside the accepted fixes**
- **R-14.** I dropped `why` from `{found}`. The alternative was a labelled `why`, which would have meant amending INV-10.4, AC-10.3, and T-2. `{rejected}` now rebuilds each citation from its parsed fields, so no retriever prose reaches the card except the NOT FOUND reasons, which AC-10.3 allows.
- **R-16.** The record stays strict. `parse` lets `ConfigurationError` propagate, and the tool catches it per line and lists `- reply line {n}: {reason}`, so a hostile line cannot inject text there either.
- **R-19.** The engine now forwards the value unchanged. `_validate_options` builds the trim once, as it already does for the sliding window, so a bad watermark fails at construction through one guard.
- **R-20.** I moved the `search_memory` name constant into P3 instead of splitting `INFINITE_MASKED_TOOL_NAMES` across two phases. This edits one row and never has to be undone later.

**Remaining risks (unchanged unless noted)**
- **A-1.** FTS5 on Linux CI is unverified. The review notes that the CI matrix is 3.11 and 3.12 and that CPython ships FTS5.
- **A-6.** Gateway forwarding is verified in code only, not with a live key.
- **Q-11 and Q-12.** Each is decided by the §12.5 real-key trace: Q-11 by the cut-move count, Q-12 by how much of the kept history status messages take up.

## Addendum: r4 (S2 defects, status stays approved, commit fb702ba5)

The S2 test author found two defects. Per the orchestrator this is a defect fix, not a review round: `revision: 4`, `status: approved`, and the §6.2 Proof column is unchanged (no AC was renamed). §16 holds the rows "S2 defect 1", "S2 defect 2", and "S2 notes".

**How I checked defect 1 (independently of the test author)**
- I wrote a scratch prototype of INV-9.1–9.7: a patched `AnthropicProvider._create_payload` in the scratchpad, never committed. I ran the full suite (6,378 tests collected) three ways: unpatched, with the r3 rule (option a), and with "never convert a string content, move the mark to the nearest earlier list message" (option b).
- **r3 rule.** Exactly one existing test went from green to red: the compacted run-boundary test, Anthropic subtest. All 14 tests in `tests/test_anthropic_cache_breakpoints.py` went green, and nothing else changed result.
- **Option b.** The run-boundary test stays green, but three of the new cache tests stay red. A string-only history also gets no message breakpoint, which loses G-4's caching for plain chats.
- **The wire, dumped.** In requests 2–4 the payload messages are: the trace as a string, then the task as `[text* TASK]`, then `tool_use`, then `tool_result*`. The task is the message right before the newest assistant turn. The test's matcher compares `content == TASK`, so it finds no task.
- **Choice: option (a).** Anthropic documents a string content as shorthand for one text block, so the model reads the same input. The test checks the task's position, and only its matcher compares the shape. A-5 is restated with this evidence, and EC-9.10 is new.

**Defect 2: measured, then option (b)**
- **Lines after the header**, counted the way the budget test counts them (headroom in brackets): memory 251 (149), launch 368 (32), workspace 332 (68), runtime 106 (294), agent 111 (289), journal 157 (243), settings 196 (204).
- **Why not (a).** The modules with room each own another subsystem (AGENTS.md principle 3). The toolsets module sits in the tools layer, which cannot import the retriever's `BaseAgent`.
- **D-18.** `vidbyte/agents/infinite/recall.py` is CREATE row 57. `memory.py` keeps the builder entry and imports the class. `recall.py` imports `InfiniteAgentMemory` only under `TYPE_CHECKING`. A006 skips those edges (`a006_directed_dependency_graph.py:74`, `:138`), so there is no cycle.
- **Repo-forced follow-on.** The README File Index must list `recall.py` (S020, row 50).
- **The recall test's import.** `test_infinite_memory_recall.py:203` imports `InfiniteRecallTool` from `...memory`. That still resolves through `memory.py`'s import.

**Tests the test author must now update**
1. **The run-boundary test.** `tests/test_prompt_sits_at_run_boundary.py::CompactedRunBoundaryTests::test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire`, through its helper `_task_and_first_call` (`:128`). Also accept a task turn whose content is `[{"type": "text", "text": TASK, "cache_control": {"type": "ephemeral"}}]`. The assertions are unchanged: one task turn, before the first call turn (index 1 before 2 on requests 2–4).
2. **The budget test.** `tests/features/infinite_memory_agent/test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget`:
   - the bound becomes `<= 9` `.py` files;
   - `BUDGET_MODULES` (`:104-117`) gains `"vidbyte/agents/infinite/recall.py"`, giving 13 modules at `<= 400` lines each;
   - the docstring and comment change to match.
3. **Optional.** Switch `test_infinite_memory_recall.py:203` to import from `vidbyte.agents.infinite.recall`.

**S2 notes**
- I agree with them and pinned none. The open formats and accepted variants stay open.
- One fact went into §13 Per-area config. The POSIX-only endless-printer test is skipped on Windows, so INV-6.4 is proven only by the Linux CI run.
