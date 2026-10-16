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
- 2026-10-16 16:05 — Item 10 (`recall`) is built opt-in, `DIRECT` default — the checklist said "only if measurement says so" but the user said "implement all of these in 1 pr"; opt-in builds it without changing any run's behavior (request.md §C Q-ORCH-1).
- 2026-10-16 16:05 — No run events in this PR — `vidbyte/agents/infinite/events.py` is not on main (unmerged #1159); confirmed by the scout.
- 2026-10-16 16:45 — Item 7 must also deal with the per-call iteration counter in the system string — the scout found `- max_iterations: {n}/{max}` (runtime.py:1690) rendered before the map in `_build_system_string`, so a frozen map alone leaves the system string different on every call and item 7 (and items 4 and 9) would save nothing. Under rule 11 this is the "requested behavior breaks without it" case, so the smallest fix that makes the InfiniteMemory root's prefix stable is in scope; making it SDK-wide for other agents is not (optional Q-n, default no).
- 2026-10-16 16:45 — Item 9 must survive the Vidbyte gateway — AUTO mode (InfiniteMemory default) goes through the gateway, and the SDK wire test calls any new top-level Anthropic key "a guaranteed 422". The spec author verifies, read-only in `C:/Users/422mi/vidbyte-repos/vidbyte/backend`, whether block-level `cache_control` inside `system`/`messages` passes through; if it does not, the spec states the limitation and sends caching only where it is safe, as a stated limitation, not a new gateway change (the gateway is another repo).
- 2026-10-16 16:45 — Gate command corrected — request.md says to run the gate with PYTHONPATH unset; the field guide `local-ci-verification.md` (which wins on how to verify from a worktree) says `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` with no PYTHONPATH. Every later briefing uses the field-guide commands.

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
