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
