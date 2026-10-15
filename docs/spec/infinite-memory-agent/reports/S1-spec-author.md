# S1 spec author report — infinite-memory-agent r1

Spec: `docs/spec/infinite-memory-agent/spec.md`, committed `45d3cc9d` (`docs(spec): add infinite-memory-agent spec r1`). This report is written to the worktree but not committed, because the Stage F sequence commits only `spec.md`.

## What I read

- **Pipeline references:**
  - `house-style.md`
  - `spec-template.md`
  - `vidbyte-gates.md`
  - the field-guide index
- **Field-guide entries:**
  - `runtime-boundaries.md`
  - `prebuilt-agents.md`
  - `strict-config-dataclasses.md`
  - `jev-capability-layout.md`
  - `blocking-lint-invariants.md`
  - `model-facing-tool-contracts.md`
  - `comment-format.md`
  - `class-bound-helpers.md`
  - `agents-md-map.md`
  - `local-ci-verification.md`
  - `review-scope.md`
- **Pipeline inputs:**
  - `request.md`, all sections
  - `context/code-map.md`, in full
  - `reports/S0-scout.md`
  - AGENTS.md, in full
  - No other file under `docs/`.
- **Code opened and verified:** the agent and runtime layer; tools, pipelines and context; lib modules; prompts and READMEs; lint, pyproject and baselines. The sibling files are listed separately below.
  - **Agent and runtime layer:**
    - `vidbyte/agents/base.py`:
      - `_LINEAR_LOOP_RUNTIMES` at line 78
      - `__init__` params
      - per-instance ContextVars at 259/280
      - `generate_reply` at 814-845
      - `AgentMessage` construction at 936-952
      - `arun`/`run` at 1044-1060
      - `_runtime` / `_runtime_extension_kwargs` at 1350-1403
    - `vidbyte/agents/runtime.py`:
      - `__init__` at 188
      - `_arun_once` at 300
      - `_continue_finish_attempt`, `_after_tool_iteration`, `_adopt_agent_catalog` at 908-934
      - `_render_context_managers` at 1610
      - `_runtime_metadata` at 2045
      - token heuristic at 2104
    - JevAgent:
      - `vidbyte/agents/jev/agent.py`: whole constructor and `_runtime_extension_kwargs`.
      - `vidbyte/agents/jev/runtime.py`: refusal at 50-80, `_offer_bulk_work` at 171-180.
      - `vidbyte/agents/jev/bulk_work.py`: the whole file.
    - `vidbyte/agents/README.md`: structure and the coding Key Modules line.
    - `vidbyte/sessions/session.py:102`.
    - `vidbyte/agents/codex/agent.py:58` and `multi/agent.py:52`: `session_persistence_supported`.
  - **Tools, pipelines and context:**
    - `vidbyte/tools/toolsets/coding.py` and `__init__.py`.
    - `vidbyte/tools/catalog.py`: the method list.
    - `vidbyte/tools/builtins/code_search/base.py`: ignore semantics.
    - `vidbyte/tools/filesystem/read_lines.py`.
    - `vidbyte/pipelines/parallel.py` and `base.py`.
    - `vidbyte/context/manager.py`: `copy`/`upsert`/`render_primitives_zone`.
    - `vidbyte/context/primitives/documents.py`: `TextContextItem`.
    - `vidbyte/context/runtime.py`: `ContextWindowPlacement`.
  - **Lib modules:**
    - `vidbyte/lib/dataclasses/`:
      - `agents.py`: `AgentStopReason`, `AgentMessage`.
      - `tools.py`: `ToolStatus`, `ToolPermission`, `ToolResult`.
      - `security.py`: `PermissionPolicy`.
      - `filesystem.py`: `FileSystemToolConfig`.
    - `vidbyte/lib/errors/base.py`.
    - `vidbyte/lib/registries/runtimes.py`.
    - `vidbyte/lib/enums/agent_runtime.py`, `prompts.py` (header and members) and `__init__.py`.
    - `vidbyte/lib/util/__init__.py` and `text.py`.
    - `vidbyte/lib/tools/filesystem/permissions.py`.
    - `vidbyte/lib/constants/coding.py` and `__init__.py`.
  - **Prompts and READMEs:**
    - `vidbyte/prompts/prompts/jev_bulk_work/*`.
    - `vidbyte/prompts/README.md`: rows 66-70 and 244-250.
    - `vidbyte/prompts/__init__.py`: direct exports are generated, so no edit is needed.
    - `REPO_MAP.md`: entries at lines 83 and 343.
  - **Lint, pyproject and baselines:**
    - `lint/rules/`: A001 required fields, A002 token list and name-only matching, A007 tokens and its uppercase-name exemption, C008 grammar, S063, C007.
    - `lint/baseline.json` counts.
    - `pyproject.toml`: Python version, pytest pins, package-data.

## Approaches weighed

1. **Smallest: a `JevBulkWorkTool` clone.** One prebuilt `BaseAgent` with a launch tool that runs fresh `BaseAgent`s through `ParallelPipeline`, and `write_text` over a folder as memory. It has no journal, staging, verifier, or limits. **Rejected:** it fails "Unattended, resumable … without redoing finished subagents", "sparse and limited", "deterministic guardrails", and "launch 2 prompts" (spec §8.3).
2. **CodingAgent style.** A prebuilt agent with no runtime type, whose tools are all built at construction. **Runner-up (D-1):** it works functionally, but the run id, journal, and quotas are per run, so they would leak between concurrent runs of one agent instance. It also goes against `runtime-boundaries.md` ("a specialized agent's runtime is its own `AgentRuntimeType`") and the user's "a new runtime" (Prompt 4).
3. **Chosen: JevAgent pattern with the smallest runtime.** `InfiniteMemoryRuntime` only does per-run setup: journal, run-bound tools, map, then `super().arun`, then `run_finished`. All delegation is one tool that runs `BasePipeline` stages of plain `BaseAgent`s under `ParallelPipeline` (the `bulk_work` pattern). The rest is reuse:
   - Usage roll-up comes free from `generate_reply`.
   - The map survives compaction through `ContextManager.upsert` at `TOP_OF_CONTEXT`, which the runtime renders into the system string on every call.
   - The system adds no middleware, scheduler, store, or dependency, and touches `base.py` only for one frozenset member.

Alternatives I considered for sub-parts and dropped:
- **Resume through SDK `Session`s.** `Session.resume` rebuilds a plain `BaseAgent`, whose runtime refuses (D-8).
- **One file per entry.** Harder to grep and to cap.
- **Journaling staged entries.** Deferred under simplicity (D-4).
- **A second, project-scoped grep.** `Tools.add` raises on the duplicate name `grep` (D-15).
- **A bash-bypass scan via middleware.** Deferred; usage is recomputed from disk instead (D-10).

## Where I disagree with the scout or the request (with evidence)

- **New-file count.** The scout estimated "~8 new" files. The spec has 18: 12 `.py`, 1 README, and 5 prompt assets. Each `.py` is one subsystem, so no module passes 400 lines (NFR-1). The prompt assets are forced by S025 and by the enum↔asset sync in `Prompts._load`.
- **Existing files to edit.** The scout listed 12; the spec edits 14. It adds `vidbyte/lib/util/text.py` and `vidbyte/lib/util/__init__.py` for `TokenEstimate`, as AGENTS.md principle 5 requires.
  - The scout said `_approximate_token_count` in `compaction/strategies.py:50` is "the only heuristic found".
  - There are actually three identical chars/4 copies: `vidbyte/agents/runtime.py:2106` (`_approx_output_tokens`), `vidbyte/middleware/compaction/strategies.py:52`, and `vidbyte/middleware/compaction/trace_render.py:149`.
  - The helper goes into the existing `text.py`, whose own header says "Add another general text helper … here". That avoids a new file and keeps A007 satisfied through an uppercase module constant.
- **The request's v1 cut.** It includes the ~75% save reminder, the cost cap, and budget slicing. All three are deferred with recorded reasons, as the briefing allows for suggested items.
  - Nothing knows the context size: `AgentLoopSettings.to_runtime_config` drops `context_window_budget`.
  - There is no live tree ledger: `base.py:838-842` merges child usage only when the child finishes.
- **Compaction-proof system prompt.** Request.md §C says content in the system prompt survives compaction. It does, except when a caller passes `system=`, because the runtime uses `setdefault` at `runtime.py:1561`. This is recorded as D-27, an accepted limitation.
- **Request list H.** It says "root checkpointed after every tool iteration (SDK sessions)". That is not reachable with the stock `Session` restore. Resume instead restarts the root with a fresh conversation listing the finished cards (INV-28). Within a run, this is effectively the compaction the user wanted to survive.
- **Request list D's "grep with a scope".** Infeasible without a second tool name (D-15). `bash` covers project search.
- **Agent count on re-runs.** Request.md counts `max_agents` per agent started. On resume I count re-runs of interrupted pairs too, which is honest about spend. A reviewer may prefer not to count them.

## Assumptions I am least sure of

1. **A-4: the root's `remember` quota.** It is the same 5 per run as any agent. A root that runs for hours may need more, and this could be the first thing a real run hits. The fix is cheap: a separate constant.
2. **D-19: no compaction or middleware wiring.** On a very long run the root's own bash output, not the cards, could overflow the provider context. Resume recovers, but the run is no longer unattended. Q-1 carries this with default no.
3. **A-1: three of the default numbers are mine.** These are 200 files, 250k total tokens, and 20k tokens per file. The 250k figure comes from the conversation's "182k/250k" example.
4. **The 400-line module budget for `launch.py`.** It holds batch validation, replay, pair execution, and commit. With A001 headers and narration it should fit, but it is the tightest file.
5. **`Tools(settings.tools)` as the settings check for "accepted tool objects".** This is the Jev precedent at `bulk_work.py` `for_agent`. Whether `Tools` accepts every object `BaseAgent` accepts (for example decorated functions) was not traced further. If not, the settings check could reject something `BaseAgent` would take.
6. **The `ContextVar` that marks a resume.** It is set before `self.run(...)` and is visible inside `asyncio.run`, because `asyncio.run` copies the caller's context into its main task. This is standard asyncio behavior, but no SDK code exercises it today.

## Self-check (Stage E)

- `grep -c "^## §"` = 18.
- §12.3 has 32 numbered rows: 18 CREATE, matching the §8.4 budget of 18 new files, and 14 MODIFY. Every row has a governing standard, a Serves entry, and a phase.
- The ID series are contiguous with no dangling references:

  | Prefix | Count |
  |---|---|
  | G | 6 |
  | NG | 15 |
  | INV | 37 |
  | AC | 32 |
  | EC | 45 |
  | FR | 16 |
  | NFR | 8 |
  | D | 27 |
  | T | 4 |
  | W | 12 |
  | A | 8 |
  | Q | 7 (0 blocking) |

- Coverage: every FR and every AC appears in §12. Every EC names an INV or D guard, or is marked as an accepted limitation. Every T names a control.
- All 17 weighted words from request.md §D appear verbatim in an INV or NFR.
- The §4 names, the §8.5 names, and the §12.3 symbols match (checked by script).
- Repo file paths appear only in §11 – §14, plus §8.2 (whose template requires `path:symbol`) and the verbatim quotes in §0.1 and INV-1.
- No test cases appear; §13 holds facts only.
- No gate or baseline was run, because S1 forbids install and gate runs. The implementer records the baseline before P1.

## Addendum — r2 (review round 1)

The S1 review of r1 returned SOUND WITH FIXES with 15 findings: 1 Blocker, 7 Major, and 7 Minor. I checked every finding's evidence against the repo, found each one true, and accepted all 15. None was rejected or turned into a blocking question. The per-finding dispositions are in spec §16.

**Changes in r2:**
- **R-1, history trimming.** Every agent gets the existing `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS)` (60,000) through `BaseAgent`'s `middleware` argument. The task now sits beside the map in the system-string item (new `context_item` leaf). D-19 and EC-35 are withdrawn; D-28, FR-17, AC-33, EC-48, and A-9 are added. Resume lists finished pairs as short lines.
- **R-2.** `max_file_tokens` applies to notes only (AC-34).
- **R-3.** `loop` defaults to `max_iterations=INFINITE_DEFAULT_MAX_ITERATIONS` (100), and D-9 is restated. EC-47 and AC-39 are added, Q-5 is withdrawn, and Q-9 [scope-adding] is added.
- **R-4.** `launch_subagent` carries internal metadata (INV-38, D-29, AC-35).
- **R-5.** One `VidbyteSdkError` guard spans the whole pair, and card `summary`/`review` may be empty (AC-37).
- **R-6.** Extras pass through `_clone_tool`, so ordinary tools are shared by identity. AC-28 now checks names only.
- **R-7.** Extras come from the root's catalog at run start, so MCP tools and `add_tool` tools count (AC-36, EC-49). The way skills reach every agent is stated.
- **R-8.** S009 is the type check. The S004, S009, S041, and S047 ceilings are listed, and §12.4 gains lines for them.
- **R-9 – R-15.**
  - A001 applies to new files only, and the base.py header line is updated. P4 runs in the order 24 → 20 → 21 → 22 → 23 → 25 → 26.
  - Row 33 covers the tools README.
  - The full "compaction for file policy" quote is restored and becomes Q-8.
  - EC-30 is restated, and EC-46 is added.
  - The Markdown-tolerant verdict pattern was tested against 10 cases (AC-38).
  - §8.3 now weighs commit-at-once, and the unreachable running-key set is removed.
  - Seven task-card field description leaves are added.

**Self-check (r2):**
- The spec has 18 `## §` sections and 33 rows in §12.3: 18 CREATE and 15 MODIFY.
- The ID counts below are live IDs. The only gaps are the struck-through withdrawals EC-35, D-19, and Q-5.

  | Prefix | Count |
  |---|---|
  | INV | 38 |
  | AC | 39 |
  | EC | 48 live of 49 |
  | FR | 17 |
  | D | 28 live of 29 |
  | A | 9 |
  | Q | 8 live of 9, 0 blocking |

- Every FR and AC appears in §12. The §4, §8.5, and §12.3 names match.
- Paths appear only where allowed, and all 17 weighted words appear.
- The prompt family has 41 leaves, which brings the enum header to 139 assets across 34 families.

## Addendum — r3 (review round 2, final)

Round 2 returned SOUND WITH FIXES. It found 14 round-1 findings resolved and 1 partly resolved (R-5), plus 8 new findings: 4 Major (R-16 – R-19) and 4 Minor (R-20 – R-23). I checked the evidence in the repo, accepted all 8, and added no new questions. Status is now `approved`, at revision 3.

**Changes in r3:**
- **R-16, a clean context per run.** Row 21 replaces the context with `tool_calls=()` and `history=()`, which adds INV-39, AC-40, and EC-50.
  - I extended the reviewer's fix to cover `history` too. `BaseAgentContext.build_context_body` also renders the agent's earlier prompts and replies as `History:` in the system string, which trimming cannot reach.
- **R-17.** `map_text` never raises on file content, and a commit's `ToolExecutionError` now drops only that entry (INV-16). EC-24 is restated, and AC-37 now uses `entries.jsonl` and checks that the run continues.
- **R-18.**
  - Grep's `max_file_bytes` is now derived from `max_tokens`, using `INFINITE_UTF8_MAX_BYTES_PER_CHAR`.
  - The `loop` default now cuts tool results with the existing `result_max_chars` at `INFINITE_TOOL_RESULT_MAX_CHARS` (100,000).
  - EC-48 and D-3 are restated, AC-39 is extended, and AC-42 is added.
- **R-19.** The pair guard now catches `(VidbyteSdkError, OSError, ValueError)`, a wrong-shape line raises `ToolExecutionError`, and the verdict value is lowercased. EC-41 and D-22 now state the duplicate-key consequence.
- **R-20.** No pipeline is built for a batch that holds only replays.
- **R-21.** The map item holds only the map again. The `context_item` leaf is dropped, giving 40 leaves and 138 assets. INV-23 and D-28 now state the real reasons: the task is the re-sent prompt, and the trim scans newest to oldest.
- **R-22.** `edit_file` now follows INV-20's path rules.
- **R-23.** The runtime checks for reserved names before the journal starts (AC-41).
- **D-9.** Its limits are now counted in loop iterations rather than model calls.

**Self-check (r3):**
- The spec has 18 sections and 33 rows in §12.3: 18 CREATE and 15 MODIFY.
- The ID counts below are live IDs. The only gaps are the struck-through withdrawals EC-35, D-19, and Q-5.

  | Prefix | Count |
  |---|---|
  | INV | 39 |
  | AC | 42 |
  | EC | 49 live of 50 |
  | FR | 17 |
  | D | 28 live of 29 |
  | A | 9 |
  | Q | 8 live of 9 |

- Every FR and AC appears in §12. The §4, §8.5, and §12.3 names match, and all paths sit where they are allowed.
