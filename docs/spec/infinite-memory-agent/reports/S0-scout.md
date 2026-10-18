# S0 scout report: infinite-memory-agent

Base `d9c01461b9e5d8a1265ee85128416b986841ce90`, branch `feat/infinite-memory-agent`. No commits, installs, gate runs, or pytest runs. Two files were created: this report and `context/code-map.md` (exactly four `## ` headings, checked with `grep -c`).

## Planned list (files the change will touch)

Existing files that change:
- `vidbyte/lib/enums/agent_runtime.py`, `vidbyte/lib/registries/runtimes.py`, `vidbyte/agents/base.py` (line 78 only)
- `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/enums/prompts.py`, `vidbyte/prompts/README.md`
- `vidbyte/tools/toolsets/__init__.py` (if a toolset catalog is added)
- `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `contracts/sdk-public-api.json` (regenerated)
- `vidbyte/agents/README.md`, `REPO_MAP.md`

New files: `vidbyte/agents/infinite/` (facade, runtime, launch tool, settings or not, README), `vidbyte/lib/dataclasses/infinite.py`, `vidbyte/lib/enums/infinite.py`, `vidbyte/lib/constants/infinite.py`, `vidbyte/prompts/prompts/<family>/`, optional `vidbyte/tools/toolsets/infinite.py`, `tests/features/<pack>/`, optional `scripts/test-<pack>.py`.

## Files actually read

Read in full:
- AGENTS.md, CLAUDE.md, CONTRIBUTING.md, REPO_MAP.md, `docs/spec/infinite-memory-agent/request.md`, `.github/pull_request_template.md`, pyproject.toml (pytest and dev-extra sections), `scripts/run_ci.py`, `lint/README.md`, `scripts/test-jev-bulk-work.py`
- `vidbyte/agents/README.md`, `vidbyte/agents/jev/README.md`, `vidbyte/prompts/README.md`, `vidbyte/lib/README.md`, `vidbyte/lib/registries/README.md`
- `vidbyte/agents/jev/{agent,runtime,bulk_work,settings,usage,__init__}.py`, `vidbyte/agents/coding.py`, `vidbyte/agents/fork.py`
- `vidbyte/lib/registries/runtimes.py`, `vidbyte/lib/enums/{agent_runtime,prompts,__init__}.py`, `vidbyte/lib/constants/coding.py`, `vidbyte/lib/usage_ledger.py`, `vidbyte/lib/tools/filesystem/permissions.py`
- `vidbyte/tools/{base,catalog,types,_internal}.py`, `vidbyte/tools/toolsets/{coding,__init__}.py`, `vidbyte/tools/builtins/bash.py`, `vidbyte/tools/builtins/code_search/{base,grep}.py`, `vidbyte/tools/builtins/fork/fork.py`
- `vidbyte/pipelines/{base,parallel,types}.py`, `vidbyte/sessions/{session,store}.py`, `vidbyte/sessions/stores/file.py`, `vidbyte/middleware/builtins/cost_budget.py`, `vidbyte/prompts/catalog.py`, `vidbyte/prompts/prompts/jev_bulk_work/jev_bulk_work.json`, `vidbyte/harnesses/stores/file.py`
- `tests/features/jev_bulk_work/{README.md,FEATURE.md,test_jev_bulk_work.py}`, `tests/features/coding_agent/{README.md,conftest.py}`, `tests/agent_test_support.py`, `tests/test_prompts_interface.py`
- Field guide (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`): `init.md` and the entries cited in code-map §1; gates reference `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`

Read in part (ranges or grep hits only):
- `vidbyte/agents/base.py` (78, 86-121, 229, 340, 414-475, 521-589, 770-842, 1055-1075, 1350-1416), `vidbyte/agents/runtime.py` (158-703 loop, 908-922, 1552-1624, 1980-2023, 2117-2133)
- `vidbyte/__init__.py` and `vidbyte/agents/__init__.py` (export sections), `vidbyte/lib/dataclasses/jev.py` (header, 3699-3757), `vidbyte/lib/dataclasses/coding.py` (1-140), `vidbyte/lib/dataclasses/security.py` (25-56), `vidbyte/agents/settings/loop.py` (1-212)
- `vidbyte/agents/pricing/{tracker,records}.py`, `vidbyte/lib/constants/__init__.py`, `vidbyte/middleware/compaction/{strategies,context_compaction}.py`, `vidbyte/lib/tools/filesystem/backends/local.py`, `vidbyte/tools/builtins/memory/{base,__init__}.py`
- `tests/test_jev_agent.py` (438-460), `tests/features/coding_agent/test_coding_agent_contract.py` (grep, 200-210), `tests/test_jev_compute_situations.py` (255-256)
- `scripts/check_context_write_paths.py` (1-30, 135-230), `scripts/check_context_primitive_introductions.py` (1-25), `.github/workflows/{ci,static-policy,agents-md-placement}.yml` (grep)

Listed but not opened: `middleware/builtins/{token_budget,runtime_limits,loop_detection,retry,exponential_backoff_retry,circuit_breaker}.py`, `vidbyte/context/manager.py`, `contracts/sdk-public-api.json` (grepped only), the session tests, and the fork tests.

## What the areas hint or gates reference got wrong

Gates reference (`vidbyte-gates.md`):
- It says "CI runs the same `run_ci.py`; semgrep is part of it". Semgrep is not in `scripts/run_ci.py` (source stage 79-93). It runs only in `.github/workflows/static-policy.yml:30` and scans git-tracked files only.
- The gate line leaves out the worktree requirement: the source stage needs `PYTHONPATH=$(pwd)`, and the package stage must run without it (field guide `local-ci-verification.md`).
- It says "every new enum ... exported". AGENTS.md says every *public* enum.

Request implementation hints (request.md:205-218):
- "content in the system prompt survives compaction" is only partly true. `_build_iteration_call_options` uses `setdefault("system", ...)` (runtime.py:1561), so an explicit `system` option wins. Whether a `trace_as_system_suffix` compaction mode edits the system text is unverified.
- `_after_tool_iteration` runs only after a normal tool iteration (runtime.py:696). It does not run on finish attempts.
- "settings object → the agent's own `settings.py`": AGENTS.md allows this. CodingAgent and `strict-config-dataclasses.md` use `vidbyte/lib/dataclasses/<agent>.py` instead.
- `FileSystemPermissions.resolve_scoped_path` takes a `FileSystemToolConfig`, not a bare root.
- Grep "with a scope (workspace/project/both)" has no support in `GrepTool`, which is single-root with a fixed name.
- The listed budget middleware does not give a tree-wide cost cap. `CostBudgetMiddleware` is a per-run blended-rate estimate, and child usage reaches the parent ledger only when the child finishes.
- Verified as stated: the JevAgent/JevRuntime structure, `_runtime_extension_kwargs`, the registry, `_compaction_event_delta`, the bulk_work precedent, ForkConversationTool non-escalation, BashTool's Windows caveat, and the hosted-only memory tools.
