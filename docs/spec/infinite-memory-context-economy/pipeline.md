---
slug: infinite-memory-context-economy
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-context-economy
branch: feat/infinite-memory-context-economy
base_commit: 0f2aeb48382b49ecb179b3f3ca94f3807cd1edcc
pr:
until: none
started: 2026-10-16 16:05
---

# Pipeline: InfiniteMemoryAgent context economy

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-16 16:05 | 2026-10-16 16:45 | reports/S0-scout.md | base_commit 0f2aeb48; code-map.md (4 sections, ~60 files) |
| S1 spec + review | done | 2026-10-16 16:50 | 2026-10-16 20:40 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | spec r3 (75789419), approved; round 1 SOUND WITH FIXES (12 accepted), round 2 SOUND WITH FIXES (12 accepted) |
| S2 tests | running (defect fix) | 2026-10-16 20:45 | | reports/S2-test-author.md | 133 new tests in 10 files + §13 changed tests; red confirmed (orchestrator re-ran test_read_lines_window.py 10 failed, test_infinite_memory_stable_prefix.py 8 failed, right reasons); test commit 0d265474, proof 5e930f3b; 2 spec defects → spec r4 |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-16 16:05 — Item 10 (`recall`) is built opt-in, `DIRECT` default — the checklist said "only if measurement says so" but the user said "implement all of these in 1 pr"; opt-in builds it without changing any run's behavior (request.md §C Q-ORCH-1).
- 2026-10-16 16:05 — No run events in this PR — `vidbyte/agents/infinite/events.py` is not on main (unmerged #1159); confirmed by the scout.
- 2026-10-16 16:45 — Item 7 must also deal with the per-call iteration counter in the system string — the scout found `- max_iterations: {n}/{max}` (runtime.py:1690) rendered before the map in `_build_system_string`, so a frozen map alone leaves the system string different on every call and item 7 (and items 4 and 9) would save nothing. Under rule 11 this is the "requested behavior breaks without it" case, so the smallest fix that makes the InfiniteMemory root's prefix stable is in scope; making it SDK-wide for other agents is not (optional Q-n, default no).
- 2026-10-16 16:45 — Item 9 must survive the Vidbyte gateway — AUTO mode (InfiniteMemory default) goes through the gateway, and the SDK wire test calls any new top-level Anthropic key "a guaranteed 422". The spec author verifies, read-only in `C:/Users/422mi/vidbyte-repos/vidbyte/backend`, whether block-level `cache_control` inside `system`/`messages` passes through; if it does not, the spec states the limitation and sends caching only where it is safe, as a stated limitation, not a new gateway change (the gateway is another repo).
- 2026-10-16 16:45 — Gate command corrected — request.md says to run the gate with PYTHONPATH unset; the field guide `local-ci-verification.md` (which wins on how to verify from a worktree) says `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH. Every later briefing uses the field-guide commands.

- 2026-10-16 19:55 — Round-2 reviewer hit an API session limit mid-run; resumed the same agent after the reset rather than relaunching — its verified claims were in its context, nothing on disk had changed.
- 2026-10-16 20:40 — Spec Q-1…Q-12 take their stated defaults: Q-1 yes (recall built opt-in, DIRECT default); Q-2…Q-12 no / not built (Q-12 is the round-2 reviewer's scope-adding suggestion). Logged per playbook; the user can interrupt.
- 2026-10-16 20:40 — S2 test author may edit existing tests, but only those spec §13 lists as "deliberately changed" (bash head-only group, `test_infinite_memory_delegation.py:134` card count, exact tool-set pins, `EXPECTED_LEAVES` 40→50, `test_infinite_memory_workspace.py:340-372` map refresh, registry signature tests), updating each to the spec's new behavior and citing the spec ID; it may not weaken, skip or delete any other assertion — the template's "never modify an existing test" rule cannot hold for a PR whose requested behavior changes those pins (request.md §C Q-ORCH-5 planned exactly this). The implementer stays forbidden from touching any test.

- 2026-10-17 — S2 reported two spec defects before S3 (playbook: resolve now, never let the implementer discover them): (1) INV-9.3 turns `tests/test_prompt_sits_at_run_boundary.py::CompactedRunBoundaryTests::test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire` red (A-5 wrong); (2) the infinite package's complexity-budget test (≤400 lines/module, ≤8 files) is not in §13 and `InfiniteRecallTool` does not fit `memory.py`. Sent both to the spec author for r4; then the test author updates the named tests. Open formats the spec leaves loose (rejection reasons, `{searches}` wording, `reply line {n}` base, error class) are accepted as content/order checks.

## User replies (verbatim)
- (none during the run)

## Niche facts accumulated (carried into every later briefing)
- Hysteresis has nowhere to keep state in the strategy: `vidbyte/middleware/compaction/engine.py:161` builds a new strategy on every call. The per-run store is `MiddlewareContext.run_state: dict[type, Any]` (`vidbyte/lib/dataclasses/middleware.py:190-191`); the precedent keys it by `type(self)` (`verify_command.py:81`), which collides if masking and trim are two `MessageHistoryCompactionMiddleware` instances on one agent. The root's middleware instance persists across runs (`agent.py:80`); children rebuild per pair (`launch.py:290`). — *source:* S0 scout
- `_trim_groups_to_tokens` can keep an older small group after skipping a newer large one (`strategies.py:632-635`), so its output is not always a suffix; it contains a nested function (principle 1 forbids it in changed code). — *source:* S0 scout
- `AgentLoopSettings.compaction_trigger_tokens` / `compaction_target_tokens` already exist (`vidbyte/agents/settings/loop.py:60-61`) with no consumer. — *source:* S0 scout
- A RETRIEVER `InfiniteAgentRole` member breaks `test_infinite_memory_contract.py:383-387` (every role gets `remember` and `write_note`); registry preset rows always grant both (`lib/registries/infinite.py:34-39`); `launch.py:268-274` sends every non-GENERATOR role to verifier rules. — *source:* S0 scout
- The sliding window has no scope today, so unscoped it would strip `launch_subagent` cards and `bash` output (`strategies.py:683-696`); its builder exposes only `keep_recent, window_mode, max_chars` (`context_compaction.py:173-175`). `strategies.py` is already 1,020 lines. — *source:* S0 scout
- `GrepTool` has no constructor of its own (inherits `code_search/base.py:27`); case-sensitivity and `context_lines=2` are literals in `execute` (`grep.py:49`, `:54`); its description is one sentence while S025 wants ≥ 4 (baseline 263). — *source:* S0 scout
- `BashTool` is shared with CodingAgent (`toolsets/coding.py:86`) and `VerifyCommandMiddleware`; head-only output is pinned by `test_bash_tool_contract.py:173`, `test_bash_tool_process_bounds.py:241`, `test_coding_agent_verify_command.py:367`, `tests/features/coding_agent/FEATURE.md:23`, `vidbyte/agents/README.md:122`; bounds tuple pinned at `test_bash_tool_contract.py:74`. Three head/tail implementations exist with no lib helper (`strategies.py:121`, `setup_commands.py:113-120`, HEAD_TAIL preview). — *source:* S0 scout
- `TextContextItem.primitive_frozen` already means "a later upsert raises" (`vidbyte/context/manager.py:82-85`); "freeze the map" must not reuse it. — *source:* S0 scout
- `launch_subagent` is `metadata={"internal": True}` (`launch.py:114`), exempting it from the tool timeout (`runtime.py:1500`) and the result cap (`runtime.py:1985`); a new `recall` tool gets neither unless its spec sets it. — *source:* S0 scout
- The infinite package already has 8 `.py` modules, the maximum `test_infinite_memory_contract.py:475` allows; `launch.py` is 368 lines after its header against a 400 cap (`:479`); `PRESET_TOOLS`, `MEMORY_TOOLS`/`GENERATOR_TOOLS`/`VERIFIER_TOOLS` and the 40 prompt leaves (`EXPECTED_LEAVES`) are pinned exactly. — *source:* S0 scout
- Request line anchors are from #1159: `agent.py:87` → 80, `launch.py:313` → 290, `launch.py:309` → 276/286, `strategies.py:649` → 663. `InfiniteWorkspace.relative()` does not exist. — *source:* S0 scout
- `FolderUsage` forbids caching (`vidbyte/lib/tools/filesystem/usage.py`, WHAT NOT TO DO 1). `compact_context` (`vidbyte/tools/builtins/context/compaction.py`) exposes compaction options to the model. — *source:* S0 scout
- Tests that pin behavior this PR changes: `test_infinite_memory_delegation.py:134` (2 `result_card` renderings for a passing batch), `test_infinite_memory_workspace.py:340-372` (root map refreshes after each tool iteration), the bash head-only tests above. — *source:* S0 scout
- Gate from a worktree: `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH; check `PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"` prints the worktree. Semgrep only scans git-tracked files (`git add -A` first; `semgrep==1.170.1` in its own venv). Two `harness_threads` surface tests fail locally on any branch touching `vidbyte/tools` (pre-existing; do not edit). — *source:* field guide local-ci-verification.md
- SDK CI is dispatch-only: `gh workflow run ci.yml --ref <branch>` and `static-policy.yml`; read results via the check-runs API (`gh pr checks` stays empty). — *source:* orchestrator memory
- No `.venv` in the worktree: use the global Python 3.11.0 (SQLite 3.38.4, FTS5 present) with `PYTHONPATH=$(pwd)`; CI tests 3.11 and 3.12. — *source:* S1 review r2
- C006 (baseline 104): guards in the `x < 0 → ValueError` shape add findings; use `RecordFieldValidator.require_int`/`require_bool` or `isinstance(x, bool) or not isinstance(x, int) or x < bound`. S047/S052 do not cover sqlite3. — *source:* S1 review r1
- `TokenEstimate.cap` returns `cut + marker` (overshoots by the marker); the recall card subtracts the marker's count first. — *source:* S1 review r2 / spec r3
- `test_infinite_memory_context.py:46` patches the history cap to 250 and stays green only because a no-change status message is the ~33-token loop block (fails at ~110). — *source:* S1 review r2
- `test_bash_tool_process_bounds.py:244` patches `BASH_MAX_OUTPUT_BYTES` to 1,000 → head 500 + tail 500 under `T = min(TAIL, MAX // 2)`; tests must patch both constants. — *source:* spec r3
- One runner/adapter per BaseAgent (`_runner_cache`, `base.py:1659-1674`); children and retrievers start cold for the Anthropic repeat gate. The Anthropic adapter makes shallow copies, so marked content lists must be copied (INV-9.5). — *source:* S1 review r1/r2
- FTS rows are deleted by recorded rowid, never by the UNINDEXED `source` column (full-table scan under the shared lock); fingerprint taken before the read. — *source:* spec r3
- `Tools.without` (`tools/catalog.py:90`) takes tool objects, not names. Engine `:195-198` and `_validate_options` coerce options with `int()`. — *source:* S1 review r2
- S2 test facts: retriever named exactly `analyst/root/recall` (`{settings.name}/{memory.key}/recall`), tests read middleware via `ScriptedTree.agents[name]`; `FullTextIndex.lock` is a plain attribute set in `__init__` (a test replaces it) and `search_memory` holds it once across refresh+search; the query path calls `FullTextIndex.match_expression` through the class (a test wraps it), dropping punctuation-only words before quoting; the masking placeholder comes from the `masked_output` leaf (≤ 60 tokens); found blocks carry no `read_lines` footer; the quota refusal names `INFINITE_RECALLS_PER_AGENT`; `test_infinite_memory_recall.py` imports `_view` from `test_infinite_memory_economy.py`; FTS5-missing tests use `without_fts5()` from `tests/test_fulltext_index.py`. — *source:* S2 test author
- Run `lint/run.py` with `PYTHONIOENCODING=utf-8` (cp1252 crash otherwise) and with new files staged (S020 reads tracked files). Run pytest with `-p no:cacheprovider`. — *source:* S2 test author
- `tests/features/coding_agent/test_bash_tool_process_bounds.py`'s changed endless-printer test is POSIX-only (skipped on Windows); only Linux CI proves it — dispatch CI in S5. — *source:* S2 test author
- Contract names (spec r3 §4/§8.5): `FileSystemToolConfig.max_read_lines`, `LineLimit`, `InfiniteWorkspaceSettings.max_read_lines`/`.recall_mode`, `InfiniteRecallMode` (exported from `vidbyte`), `ToolOutputSlidingWindowCompaction(tools=, placeholder=)`, `TrimWithProviderBoundariesCompaction(low_watermark_tokens=)` in new `vidbyte/middleware/compaction/windows.py`, `FullTextIndex` (lib helper, `.lock` RLock), `InfiniteWorkspace.full_text`/`.fit_map_lines`, `INFINITE_BOOKKEEPING_NAMES`, `InfiniteSearchMemoryTool(workspace_root, *, index, max_file_bytes)`, `InfiniteRecallTool`, `InfiniteRecallCitation.parse`, `AnthropicProvider._attach_cache_breakpoints`, `BashTool._collect(process, head, tail, omitted: list[int]) -> int`. — *source:* S1 author
