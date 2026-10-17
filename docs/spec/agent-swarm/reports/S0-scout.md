# S0 scout report: agent-swarm

- Stage: S0 scout. Read-only.
- Branch: `feat/agent-swarm`, head `7e529671`, which is `origin/main` `0f2aeb48` plus one request-capture commit.
- Written this stage: this report and `context/code-map.md`. Nothing else was created or changed.
- Not done this stage: no commits, installs, gate runs, `lint/run.py`, or pytest.
- One read-only Python one-liner counted the prompt-family JSON files and their leaves, to check the header claim in `vidbyte/lib/enums/prompts.py:7`.

## Planned list (from the briefing's AREAS_HINT and the request)

1. `AGENTS.md` and `REPO_MAP.md`.
2. `docs/spec/agent-swarm/request.md` (the only file read under `docs/`).
3. `vidbyte/agents/runtime.py`: `_after_tool_iteration` and the loop around it.
4. `vidbyte/agents/base.py`: how a runtime plugs into an agent.
5. The Jev runtime and agent.
6. The InfiniteMemory package, as precedent.
7. The actor runtime.
8. The MultiAgent `on_event` callback.
9. Tools:
   - bash;
   - grep and glob;
   - the filesystem tools;
   - patch;
   - `ParadigmMinimalToolset`;
   - the coding and infinite toolsets;
   - the operations search tools.
10. Placement targets:
    - `lib/dataclasses`;
    - `lib/enums/__init__`;
    - `agents/settings`;
    - `lib/registries`;
    - `vidbyte/__init__`;
    - `agents/__init__`;
    - `contracts/sdk-public-api.json`.
11. The prompt layer: the `Prompt` enum, the catalog, the README, and the family descriptors.
12. Tests and the fake model clients.
13. The lint rules, read from `lint/` only.
14. `scripts/run_ci.py` stage names.
15. The field guide: `init.md` plus the 10 named files.
16. The known gotchas.
17. `vidbyte/lib/dataclasses/validation.py`, `vidbyte/lib/constants/infinite.py`, and `vidbyte/lib/dataclasses/agents.py`.
18. `vidbyte/tools/_internal.py` (`isDone`).
19. The tools, lib, registries, and agents folder READMEs.

## Files actually read

Most files were read in full. A few were read in focused ranges, each found with a grep and given in parentheses.

**Rules and maps**

- `AGENTS.md`
- `REPO_MAP.md` (:52-112, and the grep hits at :398-403)
- `docs/spec/agent-swarm/request.md`
- `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md` (:19-34)

**Runtime and agent core**

- `vidbyte/agents/runtime.py` (the loop :297-707, the hooks :917-931, and anchors :160-273, :2046, :2111, :2303)
- `vidbyte/agents/base.py` (:76-90, :214, :268-299, :840-905, :996-1012, :1098-1107, :1275-1325, :1408-1475)
- `vidbyte/lib/registries/runtimes.py`
- `vidbyte/lib/enums/agent_runtime.py`
- `vidbyte/lib/enums/infinite.py`

**InfiniteMemory package**

- `vidbyte/agents/infinite/__init__.py`
- `vidbyte/agents/infinite/agent.py`
- `vidbyte/agents/infinite/runtime.py`
- `vidbyte/agents/infinite/settings.py`
- `vidbyte/agents/infinite/launch.py`
- `vidbyte/agents/infinite/memory.py`
- `vidbyte/agents/infinite/workspace.py`
- `vidbyte/agents/infinite/README.md`
- `vidbyte/lib/dataclasses/infinite.py` (header and class list)
- `vidbyte/lib/constants/infinite.py` (header and constant names)

**Jev**

- `vidbyte/agents/jev/runtime.py`
- `vidbyte/agents/jev/agent.py` (anchors)
- `vidbyte/agents/jev/continuation/base.py` (:30-39)
- `vidbyte/agents/jev/continuation/done.py` (:84-100)

**Actor runtime**

- `vidbyte/agents/runtimes/__init__.py`
- `vidbyte/agents/runtimes/actor/__init__.py`
- `vidbyte/agents/runtimes/linear.py`
- `vidbyte/agents/runtimes/configs.py`
- `vidbyte/agents/runtimes/actor/message.py`
- `vidbyte/agents/runtimes/actor/inbox.py`
- `vidbyte/agents/runtimes/actor/broker.py`
- `vidbyte/agents/runtimes/actor/actor.py`

**MultiAgent**

- `vidbyte/agents/multi/agent.py`
- `vidbyte/agents/multi/ledger_controller.py`
- `vidbyte/agents/multi/README.md`
- `vidbyte/agents/multi/transfer.py` (`maybe_await`)
- `vidbyte/lib/dataclasses/multi_agent.py` (event types)

**Tools**

- Toolsets:
  - `vidbyte/tools/toolsets/paradigm_minimal.py`
  - `vidbyte/tools/toolsets/infinite.py`
  - `vidbyte/tools/toolsets/coding.py`
  - `vidbyte/tools/toolsets/__init__.py`
- Builtins:
  - `vidbyte/tools/builtins/bash.py`
  - `vidbyte/tools/builtins/editing/patch.py`
  - `vidbyte/tools/builtins/editing/__init__.py`
  - `vidbyte/tools/builtins/code_search/__init__.py`
  - `vidbyte/tools/builtins/code_search/base.py`
  - `vidbyte/tools/builtins/code_search/grep.py`
  - `vidbyte/tools/builtins/code_search/glob.py`
- Filesystem:
  - `vidbyte/lib/dataclasses/filesystem.py`
  - `vidbyte/tools/filesystem/_base_tool.py`
  - `vidbyte/tools/filesystem/base.py`
  - `vidbyte/tools/filesystem/read_lines.py`
  - `vidbyte/tools/filesystem/write_text.py`
  - `vidbyte/tools/filesystem/replace_text.py`
  - `vidbyte/tools/filesystem/read_text.py`
  - `vidbyte/tools/filesystem/list_dir.py`
  - `vidbyte/tools/filesystem/__init__.py`
- Core:
  - `vidbyte/tools/base.py`
  - `vidbyte/tools/types.py`
  - `vidbyte/tools/catalog.py`
  - `vidbyte/tools/_internal.py`
- Operations (search):
  - `vidbyte/tools/builtins/operations/search.py`
  - `vidbyte/tools/builtins/operations/base.py`
  - `vidbyte/tools/builtins/operations/clients/brave.py`
  - `vidbyte/tools/builtins/operations/__init__.py`

**Settings, security, and validation**

- `vidbyte/lib/dataclasses/security.py`
- `vidbyte/lib/dataclasses/validation.py` (header, method list, :93-123)
- `vidbyte/lib/dataclasses/agents.py` (`AgentStopReason` and the class list)
- `vidbyte/agents/settings/loop.py` (:1-100)

**Prompt layer**

- `vidbyte/lib/enums/prompts.py`
- `vidbyte/prompts/README.md`
- `vidbyte/prompts/catalog.py`
- `working_principles/working_principles.json`
- `jev_swarm/jev_swarm.json`
- the directory listings of the prompt families

**Export lists** (the infinite and swarm entries, by grep)

- `vidbyte/lib/enums/__init__.py`
- `vidbyte/lib/dataclasses/__init__.py`
- `vidbyte/__init__.py`
- `vidbyte/agents/__init__.py`

**Usage, sessions, and middleware**

- `vidbyte/sessions/session.py` (:90-115)
- `vidbyte/agents/pricing/tracker.py` (header)
- The locations of `usage_ledger.py`, `context_compaction.py`, `delegation_limits.py`, and `parallel.py`, found by grep.

**Contracts, CI, and lint**

- `contracts/README.md`
- `contracts/sdk-public-api.json` (head and grep)
- `scripts/run_ci.py`
- `lint/README.md`
- `lint/baseline.json`
- Rule docstrings:
  - A001, A002, A006, A007;
  - S006, S008, S015, S019, S020, S021, S024, S025, S055, S061, S063;
  - C001, C006, C007, C008, C011, C015, C016.
- Policy constants of A002, A006, A007, S024, S025, and C011.
- `lint/core/report.py:58`

**Folder READMEs**

- `vidbyte/agents/README.md`
- `vidbyte/lib/README.md`
- `vidbyte/tools/README.md`
- `vidbyte/lib/registries/README.md`

**Tests**

- `tests/agent_test_support.py`
- `tests/features/infinite_memory_agent/infinite_memory_fixtures.py`
- `tests/features/infinite_memory_agent/README.md`
- `tests/features/infinite_memory_agent/test_infinite_memory_contract.py` (the header, test names, :141-232, :466-481)
- `tests/features/coding_agent/conftest.py` (header and definitions)
- `tests/test_agent_tool_loop.py` (:28-60)
- `tests/multi_agent/test_behavior.py` (the `on_event` hits)
- `tests/test_jev_compute.py` (header)
- `tests/test_prompts_interface.py` (test names)
- `pyproject.toml` (the pytest block)
- The `tests/` and `tests/features/` listings.

**Field guide**

- `init.md`
- `runtime-boundaries.md`
- `strict-config-dataclasses.md`
- `prebuilt-agents.md`
- `model-facing-tool-contracts.md`
- `prompt-families.md`
- `comment-format.md`
- `blocking-lint-invariants.md`
- `review-scope.md`
- `local-ci-verification.md`
- `class-bound-helpers.md`

**Git (read-only)**

- `rev-parse`, `merge-base --is-ancestor 2c84049c HEAD` (true), `log`, `status`, `ls-files`, and `check-ignore`.

**Not read**

- Anything else under `docs/`.
- `origin/feat/infinite-memory-agent` and every other unmerged branch.
- `field-guide/vidbyte-sdk/agents-md-map.md`.
- The `.semgrep/` policy.
- `tests/features/infinite_memory_agent/FEATURE.md`. Its role was taken from the pack README.

## What AREAS_HINT got wrong

1. **The InfiniteMemoryAgent dependency.** The hint and request say InfiniteMemoryAgent (#1084) is unmerged and nothing may depend on it (request.md:49, :152).
   - It is merged: `2c84049c` is an ancestor of HEAD.
   - It is wired into `RuntimeRegistry`, `_LINEAR_LOOP_RUNTIMES`, the root exports, and the public-API contract.
   - The unmerged branch is still off-limits. The merged package is now the main precedent.
2. **The PatchTool location.** The hint gives `vidbyte/tools/editing/patch.py`, which does not exist.
   - The real path is `vidbyte/tools/builtins/editing/patch.py`.
   - The model-facing name is `patch_file`.
3. **`ParadigmMinimalToolset` "may already be most of AgentSwarmTools".**
   - It has no `bash` and no `write_text`.
   - It adds `CodeExecutionTool`, and includes `PatchTool` only with `include_write=True`.
   - `CodingAgentTools.get_tools` is the closer match, but it uses `replace_text` rather than `patch_file`.
4. **The `_after_tool_iteration` drain point.** The hint presents it as the place to drain the inbox and says it is "called after `middleware.after_iteration`".
   - It runs only after an iteration that ran tools and continues (runtime.py:690-700).
   - Both finish points call `_continue_finish_attempt` instead (:598, :673).
   - There is no seam between the individual tool calls of one batch.
5. **"Tests and the fake model client".**
   - There is no single fake client, no `tests/fakes/`, and no root `tests/conftest.py`.
   - The offline fakes are three helpers: `tests/agent_test_support.py`, `tests/features/coding_agent/conftest.py`, and `infinite_memory_fixtures.py` (`ScriptedTree`, which patches `BaseAgent._runner_for_model`).
   - `REPO_MAP.md:61` describes a "shared layer of fakes" that is spread across those files.
6. **The `agents/settings` placement target.** The precedent agent keeps its settings in its own package (`vidbyte/agents/infinite/settings.py`), as AGENTS.md:56 allows. `vidbyte/agents/settings/` holds only general loop, tool, and fallback settings.
7. **The `lib/dataclasses/__init__` placement target.** It does not re-export the infinite records, and no rule requires dataclass exports there. Only enums must be exported (AGENTS.md:61).
8. **The `on_event` "pattern MultiAgent already uses".** MultiAgent's callback takes two arguments, `(LedgerEvent, TaskLedgerSnapshot)` (multi_agent.py:525), and its event kind is a plain string. A single-argument callback with an enum kind would differ from that precedent.

## What vidbyte-gates.md got wrong for vidbyte-sdk

1. **The lint pass marker.** gates.md:28 says the final line must read `AGENT-LINT: PASS …`. The SDK's lint prints `SDK-LINT: PASS` or `SDK-LINT: FAIL` (`lint/core/report.py:58`).
2. **Where semgrep runs.** gates.md:19 says "semgrep is part of it" (of `run_ci.py`). `scripts/run_ci.py` runs no semgrep: the source stage is `run_ci.py:79-93`. Semgrep appears in `.github/workflows/static-policy.yml` and is run separately, after `git add` (local-ci-verification.md:10-15).
3. **The gate sequence.** gates.md:19 runs `python scripts/run_ci.py --stage source`, then `python scripts/run_ci.py`, with no `PYTHONPATH` guidance.
   - In a worktree, the editable install points `vidbyte` at the canonical checkout, so the source stage would test old code. Run the source stage as `PYTHONPATH=$(pwd) … --stage source` (local-ci-verification.md:3-8; lint/README.md:38-44).
   - Run the package stage without `PYTHONPATH`. `run_ci.py` clears `PYTHONPATH` only for the smoke command (:194, :225-226) and not for the `pip install` step (:187-189).
4. **The sparse-checkout note.** gates.md:31 (`backend next-app docs lint`) describes the `vidbyte` repo layout, not this one.

## Known gotchas from the briefing, checked against files

| Gotcha | Status | Basis |
|---|---|---|
| `PYTHONPATH` breaks the package smoke | Consistent | local-ci-verification.md:3-8 and run_ci.py:187-194 |
| A `source.commit` merge conflict in the contract: take ours and regenerate | Consistent with the generator, not exercised | The generator records `HEAD` as `source.commit` and keeps it when the data is unchanged (contracts/README.md:31-32) |
| Semgrep needs its own venv | unverified in-repo | The repo only pins `semgrep==1.170.1` (local-ci-verification.md:12) |
| `NoDefaultCurrentDirectoryInExePath` | unverified in-repo | It is a shell-environment fact; no repo file mentions it |
