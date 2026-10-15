---
slug: infinite-memory-agent
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-agent
branch: feat/infinite-memory-agent
base_commit: d9c01461b9e5d8a1265ee85128416b986841ce90
pr:
until: none
started: 2026-10-15 02:49
---

# Pipeline: InfiniteMemory agent

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-15 02:49 | 2026-10-15 03:05 | reports/S0-scout.md | base_commit d9c01461; code-map.md (4 sections) |
| S1 spec + review | done | 2026-10-15 03:06 | 2026-10-15 04:52 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-2.md | spec r3 approved @a375758f (33 §12.3 rows: 18 CREATE, 15 MODIFY; 17 FR, 39 INV, 42 AC, 49 EC, 28 D, 9 A, 8 Q) |
| S2 tests | done | 2026-10-15 04:55 | 2026-10-15 05:52 | reports/S2-test-author.md | S2_HEAD c2f91ebd; 89 red cases in 7 modules under tests/features/infinite_memory_agent/; AC-1..AC-42 all mapped; spec r4 @ff634998 fixed the 2 S2 open items |
| S3 implement | pending | | | | |
| S4 adversarial review | pending | | | | |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S1 review rounds: 2/2 (both SOUND WITH FIXES; R-1..R-23 all dispositioned in §16) · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-15 02:49 — Unset the upstream of `feat/infinite-memory-agent` (git worktree add had set it to track origin/main) — a bare `git push` could otherwise target main; agents push with `git push -u origin feat/infinite-memory-agent`.
- 2026-10-15 02:49 — Scope rule for the spec: the user's explicit choices (request.md §C "Key decisions") are REQUIRED; the assistant's v1-cut suggestions (request.md §C "The v1 cut …") are in scope only in their simplest form and may be simplified or deferred with a stated reason, because the user's last instruction is "try to keep implementation of all features … very simple and elegant, dont overengineer anthing". Everything outside the v1 cut (lists I, J, K, consolidation, read tracking, final run verifier, multi-round verification) is a non-goal.

- 2026-10-15 03:58 — Resumed the S1 author with the reviewer's findings by path (reports/S1-spec-review.md lines 1–266) plus a summary, instead of pasting the 26 KB block inline — same verbatim content on disk, keeps the orchestrator context lean.

- 2026-10-15 04:20 — Launched S1 review round 2 (the last allowed): r2 accepted all 15 round-1 findings but changed §8 (D-28 history trimming, D-29 internal launch tool), §8.5 (extras from live catalog), §9 (caps) and the shape of §12 (row 33, P4 order), which the playbook says requires a scoped re-review.
- 2026-10-15 04:53 — Applied every open-question default from spec r3 §15 (none blocking): Q-1 no `middleware` settings field; Q-2 no bash-bypass scan/restore; Q-3 verifiers cannot launch; Q-4 no run-wide skills/extras for children; Q-6 no run-wide USD/token cap; Q-7 no per-run cross-process lock; Q-8 no "compaction for file policy" (over-cap writes are refused, D-26); Q-9 no separate root/child loop settings. Q-5 was withdrawn in r2. Spec summary printed to the user; continuing to S2 without waiting (playbook rule 8).
- 2026-10-15 05:53 — Routed the two S2 OPEN ITEMS (AC-41 wrapping; INV-29 review text) to the S1 author in Revision mode per the playbook, instead of leaving them for the implementer. r4: AC-41 callers see `AgentExecutionError` with the `ConfigurationError` as `__cause__` (no BaseAgent change); INV-29 had no hole (`AgentExecutionError` subclasses `VidbyteSdkError`), review = `__cause__` text → own text → class name. No re-review: wording-only, no §8/§9/§10 or §12-shape change.
- 2026-10-15 05:53 — Accepted the S2 author's bootstrap deviation (no `pip install -e` from the worktree): the global editable install points at the canonical checkout and other sessions share it. Gates run with `PYTHONPATH=$(pwd)`; `run_ci.py --stage package` builds its own wheel into a temp venv, so it needs no editable install.

## User replies (verbatim)
- (none yet)

## Niche facts accumulated (carried into every later briefing)
- No tree-wide live cost/usage cap exists today: a child's usage reaches the parent ledger only when the child finishes (`vidbyte/agents/base.py:838-842`); `CostBudgetMiddleware` is a per-run estimate from a blended rate. — *source:* S0 scout
- `Session` restore rebuilds the agent as a plain `BaseAgent` (`vidbyte/sessions/session.py:479-482`), so a custom runtime type cannot be resumed through the stock Session path. — *source:* S0 scout
- `BashTool` needs EXECUTE permission, but BaseAgent's default `PermissionPolicy` allows only SAFE and READ; CodingAgent uses `allow_all()`. — *source:* S0 scout
- `GrepTool` has a fixed name `"grep"` and one root; `Tools.add` raises on duplicate names (no workspace/project/both scope as-is). — *source:* S0 scout
- A new runtime type must be added to `_LINEAR_LOOP_RUNTIMES` (`vidbyte/agents/base.py:78`) and must refuse to build without its settings because the type is selectable by string (precedent `vidbyte/agents/jev/runtime.py:59-67`). — *source:* S0 scout
- `_after_tool_iteration` runs only after normal tool iterations (`vidbyte/agents/runtime.py:696`); there is no per-tool-call runtime hook — the per-call seam is middleware `after_tool_call`. — *source:* S0 scout
- The system prompt is rebuilt every call but set with `setdefault` (`vidbyte/agents/runtime.py:1561`), so an explicit `system` option replaces it. — *source:* S0 scout
- `ParallelPipeline` has no concurrency cap and its `gather` does not use `return_exceptions`; each stage must catch its own errors (bulk_work precedent). — *source:* S0 scout
- `context_window_budget` is never passed to the runtime config and nothing in the runtime knows the model's context size — a "~75% of context" trigger has nothing to measure today. — *source:* S0 scout
- Fake models in tests: patch `BaseAgent._runner_for_model` and route by agent name (`tests/features/jev_bulk_work/test_jev_bulk_work.py:186-193`); this reaches child agents built inside tools; async tests need `@pytest.mark.asyncio`. — *source:* S0 scout
- Lint: A001 header on every new .py (tests too); S025 tool descriptions ≥ 4 sentences or loaded via `Prompts().get`; C016 requires regenerating the public-API contract (`sdk-public-api.json`); prompt enum keys and JSON prompt assets must match. — *source:* S0 scout
- Gates in this worktree: install `python -m pip install -e ".[dev]"`; `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py --stage package` without PYTHONPATH; semgrep is CI-only and scans tracked files only (stage new files first). — *source:* S0 scout / field guide local-ci-verification.md
- Contract names (spec r1): `InfiniteMemoryAgent(settings)` with `.resume()`/`.aresume()`; `InfiniteMemoryAgentSettings`, `InfiniteWorkspaceSettings` (agents/infinite/settings.py); `InfiniteMemoryPreset`; `InfiniteMemoryRuntime`; `InfiniteMemoryAgentTools`; `AgentRuntimeType.INFINITE_MEMORY`; tools bash, grep, read_lines, launch_subagent, remember, write_note, edit_file (FULL preset only), drop_entry (verifiers only). — *source:* S1 author
- Agent names are `<settings.name>/<key>` (e.g. `analyst/root/a/gen`, `analyst/root/a/ver`); root = settings.name; the map appears in the runner's `system=` kwarg as `### [infinite_memory_map] …`. — *source:* S1 author
- The registry must import through the facade (`from vidbyte.agents.infinite import InfiniteMemoryRuntime`) — a concrete-module import trips lint A006; toolsets may not import from vidbyte.agents. — *source:* S1 author
- A007: every limit/default must be a named `INFINITE_` constant; S025: tool text via `Prompts().get`; prompt enum ↔ JSON leaves one-to-one (header counts 98→131 assets, 33→34 families); C016 regenerate public-API contract after committing `vidbyte/__init__.py`; `TokenEstimate` goes into existing `vidbyte/lib/util/text.py` (AGENTS.md principle 5). — *source:* S1 author
- Journal at `<workspace>/.runs/<run_id>.jsonl`; resume replays finished pairs by key. — *source:* S1 author
- Lint runs pinned mypy as S009 (ceiling 350, `lint/mypy.ini`, `disallow_any_generics`, `check_untyped_defs`); S041 = 0 (`open()` needs `encoding=`), S047 = 0 (no `open()` inside `async def`), S004 = 1 (naive datetime). — *source:* S1 reviewer
- `ToolSpec(metadata={"internal": True})` exempts a tool from `tool_timeout_seconds`, `result_max_chars`, tool budgets and `allowed_tools` (runtime.py:1405-1414, 1469-1476, 1780-1783, 1926-1931); `JevBulkWorkTool` uses it. — *source:* S1 reviewer
- One agent's tool calls run sequentially (runtime.py:607-608); `ParallelPipeline.run` uses `asyncio.gather` without `return_exceptions` (parallel.py:43); MCP tools from `with_mcp_server` land in the agent's own catalog (mixins.py:371-382), not `settings.tools`; `AgentForker._clone_tool(tool, None, None)` returns ordinary tools unchanged (fork.py:199-216). — *source:* S1 reviewer
- r2 facts: every agent trims its own history via `MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS)` (60,000); `INFINITE_DEFAULT_MAX_ITERATIONS` = 100; `launch_subagent` is `metadata={"internal": True}`; extras come from the root's live catalog at run start minus reserved/internal tools; run deadline ends the loop normally with stop reason `timeout` (runtime.py:2015-2018); `AgentLoopSettings.compaction_trigger_tokens/target_tokens` are stored but never acted on. — *source:* S1 author r2
- S2 tests bind exact catalog text: rejection messages, quota lines, cards, the replayed label and the resume prompt are matched against the prompt templates (literal text exact, placeholders wildcard) — render with `str.format`, no post-editing; each `launch_<field>_description` must fullmatch its schema property's description. — *source:* S2 test author
- S2 error-text obligations: name `max_parallel`; `max_agents` + started count; `already recorded as #N`; quota numbers `0` and `5` after five accepted calls; `entries.jsonl` + line number on a commit drop; line number in a journal refusal; bad task name + `INFINITE_TASK_NAME_PATTERN`. Card summary/review = `text[:1600] + INFINITE_TRUNCATION_MARKER` (kept part a prefix of the reply). Map: one line per file containing its path, ending with `INFINITE_MORE_FILES` when cut. After a torn journal tail, `run_finished` starts on its own line; the journal calls `os.fsync` (or a module-level `fsync` in journal.py) once per record. The verifier's first message contains the status value (e.g. `done`) and staged key `s1`. — *source:* S2 test author
- Tests import `InfiniteWorkspace` from `vidbyte.agents.infinite.workspace` and patch `vidbyte.agents.infinite.agent.INFINITE_HISTORY_MAX_TOKENS`; collection succeeds today (imports deferred into tests). Run: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q`. Baseline full suite: 4767 passed, 13 skipped (+89 new red). — *source:* S2 test author
- r4: errors before a run starts (construction, `resume` journal checks) reach the caller as raised; errors inside a run arrive as `AgentExecutionError` with the original as `__cause__`; `CancelledError`/`KeyboardInterrupt` are not wrapped. `AgentExecutionError` subclasses `VidbyteSdkError` (vidbyte/lib/errors/base.py:131); `AllModelsFailedError` is an `AgentExecutionError` with `__cause__` = first error. — *source:* S1 author r4
