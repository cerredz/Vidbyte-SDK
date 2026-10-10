# S0 scout report: coding-agent

- Date: 2026-10-10
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent`
- Output: `docs/spec/coding-agent/context/code-map.md`, with four `## ` sections
- Files created: only this report and the output. No commits, installs, gate runs, or pytest runs.

## Planned file list (before reading)

- **Rules:** `AGENTS.md`, `REPO_MAP.md`, field guide `C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/*.md`, skill reference `vidbyte-gates.md`.
- **Agent:** `vidbyte/agents/base.py`, `vidbyte/agents/jev/agent.py`, `vidbyte/agents/fork.py`, `vidbyte/agents/__init__.py`, `vidbyte/__init__.py`, `vidbyte/agents/README.md`, `vidbyte/agents/client.py`.
- **Tools:**
  - `vidbyte/tools/base.py`, `vidbyte/tools/catalog.py`, `vidbyte/tools/types.py`, `vidbyte/lib/dataclasses/tools.py`, `vidbyte/lib/dataclasses/security.py`;
  - `vidbyte/tools/builtins/code_search/{base,glob,grep}.py`, `vidbyte/tools/filesystem/*`, `vidbyte/lib/dataclasses/filesystem.py`, `vidbyte/tools/builtins/editing/patch.py`;
  - `vidbyte/tools/builtins/operations/{base,fetch}.py`, `operations/clients/*`, `vidbyte/tools/builtins/__init__.py`.
- **Bash precedent:** any subprocess use in `vidbyte/`.
- **Runtime:** `vidbyte/agents/runtime.py` (permission check, tool timeout, priced usage).
- **Gate:** `scripts/run_ci.py`, `lint/run.py` + `lint/rules/*`, `lint/baseline.json`, `.github/workflows/*.yml`, `pyproject.toml`.
- **Tests:** `tests/agent_test_support.py`, `tests/test_agent_tool_loop.py`, `tests/test_agent_base.py`, and the code-search/filesystem/patch/security/fork/jev test files.

## Files actually read

- **Rules and docs:**
  - `AGENTS.md` (full, 73 lines);
  - `docs/spec/coding-agent/request.md` (full; the only file read under `docs/`);
  - `REPO_MAP.md` (384 lines);
  - field-guide entries `local-ci-verification.md`, `blocking-lint-invariants.md`, `model-facing-tool-contracts.md`, `priced-operation-execution.md`, `provider-api-contracts.md`, `cli-backed-source-integrations.md`, `strict-config-dataclasses.md`, `runtime-boundaries.md`, `review-scope.md`, `agents-md-map.md`, `class-bound-helpers.md`;
  - `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md`.
- **Agents:**
  - `vidbyte/agents/base.py` (1600 lines);
  - `vidbyte/agents/jev/agent.py` (105);
  - `vidbyte/agents/fork.py` (186);
  - `vidbyte/agents/__init__.py` (523);
  - `vidbyte/agents/README.md` (210);
  - `vidbyte/agents/client.py` (56);
  - `vidbyte/agents/handoff.py` and `vidbyte/agents/continual_trace.py` (constructor and headers);
  - `vidbyte/agents/runtime.py` (2020 lines: imports, permission check, tool execute/timeout, priced usage);
  - `vidbyte/__init__.py` (1272 lines: imports and `__all__`).
  - I located the other `(BaseAgent)` subclasses with `git grep`.
- **Tools core:** `vidbyte/tools/base.py`, `vidbyte/tools/catalog.py`, `vidbyte/tools/types.py`, `vidbyte/tools/executor.py`, `vidbyte/tools/README.md`, `vidbyte/lib/dataclasses/tools.py`, `vidbyte/lib/dataclasses/security.py`, `vidbyte/tools/security/{__init__,permissions,sandbox}.py`.
- **File tools:**
  - `vidbyte/tools/builtins/code_search/{base,glob,grep}.py`;
  - `vidbyte/tools/builtins/editing/patch.py`;
  - `vidbyte/tools/filesystem/{_base_tool,read_text,read_lines,write_text,replace_text,__init__}.py`;
  - `vidbyte/lib/dataclasses/filesystem.py`;
  - `vidbyte/lib/tools/filesystem/permissions.py`.
- **Fetch:**
  - `vidbyte/tools/builtins/operations/{base,fetch}.py`;
  - `operations/clients/{_base,firecrawl,browserbase,parallel,tavily}.py` and `clients/README.md`;
  - `vidbyte/sources/fetches/http.py`;
  - `vidbyte/lib/registries/operation_pricing.py` (fetch entries);
  - `vidbyte/lib/dataclasses/operations.py` (FetchedPage/FetchPayload).
- **Subprocess and other builtins:**
  - `vidbyte/tools/mcp/transport.py`;
  - `vidbyte/tools/builtins/code_execution.py` (spec and permission);
  - `vidbyte/tools/builtins/__init__.py` (322);
  - `vidbyte/tools/builtins/fork/fork.py` (imports);
  - `vidbyte/tools/builtins/mcp/attach_tool.py:93`.
- **Gate:**
  - `scripts/run_ci.py` (full);
  - `pyproject.toml`;
  - `.github/workflows/{ci,static-policy,agents-md-placement,actionlint,publish}.yml`;
  - `lint/baseline.json`;
  - lint rules A001, A002, A003, A006, A007, A008, C001, C016, S006, S007, S008, S012, S013, S015, S016, S017, S019, S020, S025, S039, S041, S045, S047, S051, S052, S054, S055, S061.
- **Tests:**
  - `tests/agent_test_support.py`, `tests/test_agent_tool_loop.py`, `tests/test_agent_base.py`;
  - `tests/test_code_search_tools.py`, `tests/test_filesystem_tools.py`, `tests/test_patch_tool.py`;
  - `tests/test_security_executor.py`, `tests/test_restore_permission_policy.py`;
  - `tests/test_agent_fork_isolation.py`, `tests/test_jev_agent.py`;
  - `tests/test_mcp_stdio_transport.py` (subprocess parts), `tests/test_web_operation_client_retry.py` (setup).
- **Listings:** `vidbyte/lib/constants/`, `vidbyte/lib/enums/`, `vidbyte/lib/runners/`, `vidbyte/agents/`, `operations/clients/`. I also ran `which -a bash`.

## What the areas hint got wrong or left out

- There is no tools or operations module in `vidbyte/lib/constants/`. Existing modules: codex, cot_events, failure, jev, reasoning_strategies, runners, speed, trace.
- There is no tools enum module in `vidbyte/lib/enums/`. `ToolPermission` lives in `vidbyte/lib/dataclasses/tools.py:47`, not under enums.
- Fetch-tool tests are `tests/test_web_operation_client_retry.py`, `tests/features/sdk_operation_costs/`, and `tests/test_agent_runtime.py`. There is no dedicated fetch tool test file.
- The hint's fetch-tool line references were accurate: `fetch.py:67-68` and `operations/base.py:42`. It did not mention that keyed fetch tools hide page bodies from the model (`fetch.py:39-42`).
- Linkup: the hint asked me to check. There is no client, and the tool is always a stub (`fetch.py:193-196`).

## What vidbyte-gates got wrong

- It claims "CI runs the same `run_ci.py`; semgrep is part of it". This is wrong. Semgrep (`semgrep==1.170.1`, `.semgrep/typed-mapping-boundary-policy.yml`) runs only in `.github/workflows/static-policy.yml`. `scripts/run_ci.py:79-93` has no semgrep step.
- It leaves out that every workflow is workflow_dispatch/workflow_call only, and that ci.yml runs on ubuntu-latest only.
- Its install-then-gate sequence (`pip install -e ".[dev]"`, then `run_ci.py --stage source`, then `run_ci.py`) matches the code.

## Open items

- unverified: which Windows `bash` a Python subprocess resolves.
- unverified: whether importing the `vidbyte.tools.builtins` package root from `vidbyte/agents/__init__.py` creates an import cycle.
- unverified: which parameter names ASYNC109 treats as timeout-like.
- unverified: the runtime line where `ToolResult.output` reaches the model.
