# S2 test author report: InfiniteMemoryAgent context economy

Stage: S2 · Spec: r3 · Branch: `feat/infinite-memory-context-economy` · Start HEAD: `f3c42ba4` (base `0f2aeb48`)

## Inventory

New test files (10), all red before implementation:

| File | Tests | Spec items |
|---|---|---|
| `tests/test_read_lines_window.py` | 10 | 1 (AC-1, AC-1.1–1.5, INV-1.x, FR-1.2) |
| `tests/test_compaction_windows.py` | 14 | 2 and 4 at strategy and builder level (AC-2.1, AC-2.3, AC-4.1–4.3, INV-2.x, INV-4.1–4.4, INV-R.3) |
| `tests/test_grep_smart_case.py` | 10 | 3 at tool level (AC-3.1–3.4, INV-3.1–3.3, EC-3.2) |
| `tests/test_fulltext_index.py` | 12 | 8, the `FullTextIndex` lib helper (INV-8.2, 8.3, 8.6, 8.7, 8.9, §9.1) |
| `tests/test_anthropic_cache_breakpoints.py` | 14 | 9 (AC-9.1–9.5, INV-9.1–9.7, EC-9.x, FR-9.1) |
| `tests/features/coding_agent/test_bash_tool_head_tail.py` | 10 | 6 (AC-6.1, 6.3–6.5, INV-6.1, 6.2, 6.4–6.6) |
| `tests/features/infinite_memory_agent/test_infinite_memory_economy.py` | 12 | 1, 2, 3, 4, 5 wiring (AC-1.5, 1.6, FR-1.3, 2.1, 2.2, 2.4, 3.1, 3.2, 4.4, 4.5, 5.1–5.3, INV-0.4, INV-4.5) |
| `tests/features/infinite_memory_agent/test_infinite_memory_stable_prefix.py` | 8 | 7 (AC-7.1–7.5, INV-7.1–7.6, FR-7.2) |
| `tests/features/infinite_memory_agent/test_infinite_memory_search.py` | 16 | 8, the tool and the tree (AC-8.1–8.7, INV-8.x, EC-10.5) |
| `tests/features/infinite_memory_agent/test_infinite_memory_recall.py` | 16 | 10 (AC-10.1–10.8, INV-10.x, §9.1 records, D-16) |

Deliberately changed existing tests (spec §13), each with a comment citing its spec ID:

- `test_bash_tool_contract.py::test_large_output_keeps_the_first_bytes_counts_the_rest_and_memory_stays_bounded` (INV-6.2, INV-6.3, AC-6.2).
- `test_bash_tool_process_bounds.py::test_endless_printer_times_out_with_the_first_bytes_and_a_truncation_marker` (INV-6.4).
- `test_coding_agent_verify_command.py::test_output_over_the_cap_reaches_the_model_truncated_by_bash` (EC-6.4).
- `tests/features/coding_agent/FEATURE.md:23` (INV-6.2).
- `test_infinite_memory_delegation.py`: `MEMORY_TOOLS` gains `search_memory` (FR-8.1). The two-pair batch now expects zero `result_card` renderings and the exact compact cards (INV-5.1).
- `test_infinite_memory_contract.py`: `EXPECTED_LEAVES` grows from 40 to 50, and the test is renamed `..._fifty_documented_leaves` (FR-10.7). `PRESET_TOOLS` gains `search_memory` (FR-8.1).
- `test_infinite_memory_workspace.py::test_every_agent_sees_the_map_and_the_roots_map_refreshes_after_each_tool_iteration` (INV-7.2, INV-7.3).
- `tests/features/infinite_memory_agent/FEATURE.md` and `README.md` (the tool set, the map, the cards, and the new files). `tests/features/coding_agent/README.md` (File Index and Logs).

## Pruning

- The pure "first body equals main" Anthropic test passed on main. It was merged into the repeat test, whose first half is that check and whose second half is red.
- The stand-alone partial-card test (`partial`/`passed` renders full) passed on main. It was folded into the five-card batch test as its fifth pair, so that test is red only for the compact cards.
- No test was written for unspecified options (Q-2…Q-12), timing (NFR-8.1, NFR-8.3), the timestamp tick (EC-8.5), or a live key (NFR-0.5). See the test plan's "deliberately NOT written".
- Over-pinning was avoided where the spec gives no literal. Rejection reasons, the `{searches}` line wording, the pre-search `{hits}` layout, and the rendering of an empty `known` are checked by content and order, not by exact text.

## Red output

These runs use no install. Each was run from the worktree root with `PYTHONPATH="$(pwd)"` and `python -m pytest -p no:cacheprovider -q`:

```
tests/test_read_lines_window.py tests/test_compaction_windows.py tests/test_grep_smart_case.py tests/test_fulltext_index.py tests/test_anthropic_cache_breakpoints.py
60 failed in 2.49s

tests/features/coding_agent
12 failed, 297 passed, 12 skipped in 16.91s

tests/features/infinite_memory_agent
59 failed, 106 passed in 7.33s

tests/test_deterministic_compaction_middleware.py tests/test_context_compaction_middleware.py tests/test_filesystem_tools.py tests/test_code_search_tools.py tests/features/sdk_managed_text
258 passed in 2.30s
```

Each failure was read and fails for the right reason:

- **A missing spec name.** For example:
  - `ImportError: cannot import name 'FullTextIndex' from 'vidbyte.lib.util'`
  - `cannot import name 'INFINITE_MASK_KEEP_RECENT'`
  - `module 'vidbyte.tools.builtins.bash' has no attribute 'BASH_TAIL_OUTPUT_BYTES'`
  - `cannot import name 'ANTHROPIC_CACHE_SEEN_PREFIX_LIMIT'`
- **A field main refuses.** `InfiniteWorkspaceSettings.__init__() got an unexpected keyword argument 'max_read_lines'` (or `'recall_mode'`).
- **A missing catalog leaf.** For example `KeyError: 'INFINITE_MEMORY_MAP_UPDATE'`. In the INV-7.6 test it is raised inside a scripted step, so the run wraps it in `AgentExecutionError`. The changed contract test also shows the 50-leaf set mismatch.
- **A wrong value.** For example:
  - main's bash spec sentence (`'only the first bytes are kept' not in …`);
  - Anthropic bodies with no `cache_control` (`[] != ['messages[3].content[0]', 'messages[5].content[0]', 'system[0]']`);
  - `assert 2 == 0` result_card renderings in the changed delegation test;
  - set mismatches on `search_memory` in the changed tool-set tests;
  - "the root's system string changed between calls" in the changed workspace test.

No test is skipped or xfailed to stand in for red. The 12 coding-agent skips are main's own POSIX-only and case-sensitive-filesystem skips.

## Fixtures added or extended

- `tests/features/infinite_memory_agent/infinite_memory_fixtures.py`:
  - `ModelCall.raw_tools` holds the tool dicts exactly as the runner received them, for INV-7.1's byte-identical check.
  - `ScriptedTree.agents` keeps every `BaseAgent` the tree served, by name, so a test reads a child's or the retriever's middleware.
  - The header mentions both.
- `tests/test_fulltext_index.py` exports `without_fts5()`, which refuses FTS5 only at table creation through `sqlite3.connect`. `test_infinite_memory_search.py` imports it.
- `test_infinite_memory_recall.py` imports `_view` from `test_infinite_memory_economy.py`, the one-hook middleware runner.

## Verification beyond the red run

- **Scratch reference implementations.** The scratchpad held throwaway references, never committed:
  - items 6 (bash), 9 (Anthropic), and 8's `FullTextIndex`, loaded as pytest plugins over the unchanged tree;
  - for items 2 and 4, an INV-4.2 transcription patched into main's trim, with main's window.
- **Results against the references.** Every BHT, ACB, and FTI test passes against its reference. The AC-4.4 and AC-4.5 growth tests pass under the INV-4.2 reference and fail under main's trim: 118 cut moves against a bound of 27, and no single forward move after a dip.
- **Other suites under the references.**
  - The bash reference ran the coding-agent pack and the four other suites that touch bash output. Only the new and changed tests differ from main: 12 red before, 0 red after.
  - The Anthropic reference ran all 55 test files that touch the Anthropic provider. One existing test turns red; see Spec defects.
- **Agent-level reference run.**
  - **The reference.** A verification agent built a scratch reference of items 1–5, 7, 8, and 10 in a copy of the tree (`git archive HEAD` plus these tests). It was never committed, and it did not touch the worktree.
  - **First run.** The InfiniteMemory pack had one unsatisfiable test: the usage sum forgot that the unscripted launch step bills `DEFAULT_USAGE`. Three tests also passed for the wrong reason:
    - the INV-8.9 test compared thread ids, and a worker pool reuses its thread;
    - the AC-2.2 test had one result per out-of-scope tool, which even an unscoped window keeps;
    - the EC-8.7 test relied on SQLite 3.38 ignoring empty phrases.
  - **Fixes.**
    - Every root step in the usage test now carries its own usage.
    - A `CountingRLock` counts holds of the lock.
    - The AC-2.2 test makes `INFINITE_MASK_KEEP_RECENT + 1` launch, bash, and remember calls.
    - The real `match_expression` is wrapped, unchanged, to read its quoted phrases.
    - A coverage gap was closed with `test_a_custom_read_window_reaches_every_agents_read_lines_including_the_retrievers` (FR-1.3).
    - No assertion was weakened.
  - **After the fixes.** All current tests against the reference: InfiniteMemory pack plus RLW, CW, GSC, FTI, `210 passed, 1 failed`. The one failure is the complexity-budget test below.
  - **Mutation check.** 35 single-behaviour mutations of the reference were each run against the tests that should catch them, and all 35 were killed. They include unscoped masking, the trim before masking, no watermark, a split lock, punctuation kept, unquoted words, terms ANDed, the retriever holding bash, an uncapped retriever, a missing card cap, and children or the retriever reading at a fixed 200 lines.
  - **Not covered by the reference.** Items 6 and 9 were checked by their own references, above. The reference's 10 leaf texts are its own wording. Lint, file headers, and docs were not checked.

## Spec defects

1. **A run-boundary test turns red under INV-9.3, and §13 does not list it.**
   - The test is `tests/test_prompt_sits_at_run_boundary.py::CompactedRunBoundaryTests::test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire`, Anthropic subtest.
   - Under the Anthropic reference, requests 2–4 send the TASK message as `[{"type": "text", "text": TASK, "cache_control": {...}}]`, because it is the last message before the newest assistant (INV-9.1, INV-9.3). The test's helper `_task_and_first_call` matches `turn.get("content") == TASK`, so it no longer finds the task.
   - Assumption A-5 checked only the tests that read `system` from a repeat body. This test reads message content from repeat bodies built by one `AnthropicProvider`, and INV-9.3 changes that content too.
   - A-5's "If wrong" clause fits: the test should join §13's deliberately changed list, matching the text block as well as the string. I did not edit it.
2. **The complexity budget versus item 10.**
   - The test is `test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget`: ≤400 lines after the header per module, and ≤8 files in `vidbyte/agents/infinite`. §13 does not list it.
   - A bare, comment-free reference `InfiniteRecallTool` in `memory.py`, where §12.3 row 27 puts it and the recall test imports it, already reaches 402 lines. A version in house style would be about 450.
   - NFR-0.2 and §8.4 forbid a ninth file, and `launch.py` has about 25 lines to spare. `runtime.py` and `workspace.py` have room.
   - Unless the spec moves the transcription and retriever building there, or raises the cap for `memory.py`, S3 cannot satisfy both.
3. **Literal formats the spec leaves open.** The tests check these by content and order only:
   - the rejection reasons;
   - the `{searches}` line wording;
   - the pre-search `{hits}` layout;
   - how an empty `known` renders (`-` is assumed only where §9.2 states it).
4. **Two ambiguities, each accepted both ways.**
   - The numbering base of `reply line {n}` is not stated (0 or 1).
   - A retriever that raises can reach the root as `AgentExecutionError` (BaseAgent's wrapper) or as the raised class.
5. **One changed test this host cannot run.** `test_bash_tool_process_bounds.py::test_endless_printer_times_out_with_the_first_bytes_and_a_truncation_marker` is POSIX-only and skipped on Windows. Its new pattern was checked only against synthetic head-and-tail text. CI on Linux runs it.

## Addendum: spec r4 alignment

Spec r4 (`fb702ba5`) resolved defects 1 and 2 and put both tests on §13's deliberately changed list. Each edit carries a comment citing its spec ID.

- **`tests/test_prompt_sits_at_run_boundary.py::CompactedRunBoundaryTests::test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire`** (INV-9.3, EC-9.10, option (a)).
  - **Change.** `_task_and_first_call` now accepts the task as the plain string, or as exactly `[{"type": "text", "text": TASK, "cache_control": {"type": "ephemeral"}}]`. Its assertions and the DeepSeek and Gemini subtests are unchanged.
  - **On main: green** (`13 passed` for the file). The helper only widened, and main's adapter sends the string form.
  - **Under the Anthropic reference:** the HEAD helper fails and the new helper passes (27 passed with ACB).
- **`test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget`** (NFR-0.2, D-18, option (b)).
  - **Change.** The package bound is `<= 9`. `BUDGET_MODULES` gains `vidbyte/agents/infinite/recall.py`, so 13 modules are checked at 400 lines each. The docstring and the comment say so.
  - **On main: red** with `vidbyte/agents/infinite/recall.py is missing`. The HEAD version passed on main.
- **`test_infinite_memory_recall.py::test_the_recall_spec_is_internal_read_only_and_built_from_the_five_leaves`** (D-18, the optional step).
  - **Change.** It imports `InfiniteRecallTool` from `vidbyte.agents.infinite.recall`, its canonical home.
  - **On main:** still red, now with `No module named 'vidbyte.agents.infinite.recall'`.
  - **Other tests.** No test was added for what `memory.py` re-exports: §13 says `memory.py` imports the class for its builder table, and neither §13 nor §8.5 asks for a re-export check.
- **Red run.** The InfiniteMemory pack gives `60 failed, 105 passed` (was 59/106; the +1 is the budget test).
- **Reference check.** The scratch reference was reshaped per D-18, with the tool moved to `recall.py` and `InfiniteAgentMemory` imported only under `TYPE_CHECKING`. The InfiniteMemory pack plus RLW, CW, GSC, and FTI give `211 passed`, with 9 package files, `memory.py` at 271 lines after its header, and `recall.py` at 182. Nothing from the reference is committed.
