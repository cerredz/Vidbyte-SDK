# S0 scout report: ClaudeHost (PR B, `feat/claude-host`)

- **Date:** 2026-10-12.
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host`.
- **HEAD:** `678136bd4358bcf9f120504cecd818d36a3d46fe`.
- **Produced:** `docs/spec/claude-host/context/code-map.md`, which has exactly four lines starting with `## `, checked with `grep -c "^## "` = 4.
- **Commits, installs, gates:** no commits, no installs, no gate runs. Nothing was imported from `vidbyte` or from the extracted SDK, and `claude` was not run.

## 1. Planned file list (before reading code)

The plan came from the briefing items a–j and the orchestrator's likely-areas guess. Each entry was confirmed with `git ls-files`, `git grep` or a directory listing before reading.

- **a. Existing Claude code.** `git grep -n -i claude` over `vidbyte/`, `tests/`, `pyproject.toml`, `scripts/` and `lint/`. The hits are model names, pricing, prose and an MCP-client docstring (`vidbyte/mcp_server/server/core.py:7`). There is no Claude record, enum, failure code, extra or adapter.
- **b. `vidbyte/harnesses/`.** All 10 modules, `stores/` (4 modules) and the README.
- **c. `vidbyte/agents/codex/`.** All 13 modules and the README (1,121 lines).
- **d. Records, enums and failures:**
  - `vidbyte/lib/dataclasses/codex.py`, `vidbyte/lib/enums/codex.py`, `vidbyte/lib/enums/failure.py` and `vidbyte/lib/enums/__init__.py`;
  - added after reading: `vidbyte/lib/constants/codex.py`, `vidbyte/lib/constants/__init__.py`, `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`.
- **e. Tools layer:**
  - `vidbyte/tools/base.py`, `vidbyte/lib/dataclasses/tools.py`, `vidbyte/lib/dataclasses/security.py`, `vidbyte/tools/executor.py` and `vidbyte/tools/catalog.py`;
  - `vidbyte/tools/builtins/sessions/` (all 11 files), `vidbyte/tools/builtins/__init__.py` and `vidbyte/tools/builtins/pause.py`;
  - `vidbyte/tools/toolsets/` (all 3 files) and `vidbyte/tools/README.md`.
- **f. MCP server.** `vidbyte/mcp_server/` (README, `__init__`, `__main__`, `handlers.py`, `schema.py`, `server/core.py`).
- **g. Public API.** Root `vidbyte/__init__.py`, `contracts/sdk-public-api.json` and `scripts/generate-sdk-public-api.py`; added after reading: `lint/core/public_api_contract.py` and `lint/rules/c016_public_api_contract_current.py`.
- **h. Packaging, gates and lint:**
  - `pyproject.toml`, `scripts/run_ci.py`, `.github/workflows/ci.yml` and `.github/workflows/static-policy.yml`;
  - `lint/run.py`, `lint/core/{discovery,baseline,report,ruff}.py`, `lint/mypy.ini`, `lint/ruff.toml`, `lint/baseline.json` and `lint/rules/README.md`;
  - the rules likely to bite, and every README-rule candidate (A009, S020, C015, `scripts/test-github-content-readmes.py`).
- **i. Tests:**
  - `tests/test_codex_tools.py`, `tests/test_codex_failure_recovery.py`, `tests/test_durable_sessions.py`, `tests/test_fork_tool.py` and `tests/test_session_failures.py`;
  - for line counts: `tests/test_mcp_studio_server.py` and the harness tests;
  - `scripts/test-codex-tools.py`.
- **j. Vendor.**
  - **claude-agent-sdk 0.2.165:** `__init__.py`, `client.py`, `query.py`, `_errors.py`, `types.py`, `_internal/client.py`, `_internal/message_parser.py`, `_internal/sdk_mcp_bridge.py`, `_cli_version.py` and `_internal/transport/subprocess_cli.py`;
    - the regions the briefing named in `_internal/query.py`, `_internal/sessions.py` and `_internal/session_mutations.py`;
    - the vendor `pyproject.toml`.
  - **`sdk.d.ts`:** grep only.

## 2. Files actually read

A context compaction happened mid-run. This list was rebuilt from the session transcript. "Full" means read top to bottom; "part" means the named regions plus a `grep -n` outline.

### 2.1 Rules and context

- **Full:**
  - `AGENTS.md`, `CLAUDE.md` and `CONTRIBUTING.md`;
  - `.github/pull_request_template.md`;
  - `docs/spec/claude-host/request.md` (all 916 lines, twice);
  - `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md`.
- **Field guide** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`): `init.md`, `local-ci-verification.md`, `comment-format.md`, `cli-backed-source-integrations.md`, `blocking-lint-invariants.md`, `model-facing-tool-contracts.md`, `strict-config-dataclasses.md` and `class-bound-helpers.md`.
- **Repo skill:** `skills/runtime-primitives/SKILL.md`, plus `references/claude-agent-sdk.md`, `references/control-matrix.md` and `references/runtime-primitives.md`. `references/codex-sdk.md` was not read.
- **Part:** `REPO_MAP.md` (folder entries for agents, harnesses and tools) and `skills/failure/vocabulary.md` (grep only).

### 2.2 Repo code

- **Full:**
  - `vidbyte/agents/codex/*` (13 modules) and its README, read in 3 chunks;
  - `vidbyte/lib/enums/codex.py`, `vidbyte/lib/enums/failure.py`, `vidbyte/lib/enums/__init__.py` and `vidbyte/lib/constants/codex.py`;
  - `vidbyte/tools/builtins/sessions/*` (11 files), `vidbyte/tools/toolsets/*` (3 files) and `vidbyte/tools/README.md`;
  - `vidbyte/harnesses/__init__.py` and its README;
  - `vidbyte/mcp_server/server/core.py` and `vidbyte/mcp_server/handlers.py`;
  - `scripts/run_ci.py` and `scripts/generate-sdk-public-api.py`;
  - `pyproject.toml`, `.github/workflows/ci.yml` and `.github/workflows/static-policy.yml`;
  - `.semgrep/typed-mapping-boundary-policy.yml`;
  - `lint/ruff.toml`, `lint/mypy.ini`, `lint/baseline.json` and `lint/rules/README.md`.
- **Part:**
  - `vidbyte/lib/dataclasses/codex.py`: header, imports, validators, `CodexClientSettings`, the class outline and the records named in the code map;
  - `vidbyte/lib/dataclasses/{tools,security}.py`, `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/constants/__init__.py` and `vidbyte/lib/errors/{base,__init__}.py`;
  - `vidbyte/tools/{base,executor,catalog}.py`, `vidbyte/tools/builtins/__init__.py` and `vidbyte/tools/builtins/pause.py`;
  - `vidbyte/__init__.py`: header, import blocks and `__all__` positions;
  - `vidbyte/agents/base.py:419-492,1018-1075`, `vidbyte/agents/mixins.py:236-300,368-380`, and `vidbyte/agents/runtime.py:151,1268-1311,1436-1460`;
  - `vidbyte/agents/settings/tool.py` (grep), `vidbyte/lib/tools/formatter.py:37-131`, `vidbyte/sessions/session.py:22-43` and `vidbyte/harnesses/execution.py:63-71`;
  - `contracts/sdk-public-api.json:1-8,91`.
- **Workflows, part:** `.github/workflows/agents-md-placement.yml:1-30` and `.github/prompts/agents-md-placement.md`.

### 2.3 Lint and tests

- **Lint infrastructure, part:** `lint/run.py`, `lint/core/{discovery,baseline,report,ruff,public_api_contract}.py`.
- **Lint rules, headers plus detection code:** A001, A002, A003, A005, A006, A007, A009, C008, C011, C015, C016, S008, S009, S015, S016, S017, S020, S024, S025, S045, S055, S060 and S061.
- **Lint rules, headers only:** S006, S010, S012, S013, S019, S021, S053, S058, S059, S062, S064, C003 and C018.
- **Tests and scripts, part:**
  - `tests/test_codex_tools.py` (fakes, seam patch, skip guard, class list);
  - `tests/test_codex_failure_recovery.py:140-201`;
  - `tests/test_durable_sessions.py:58,1380+`;
  - `tests/test_fork_tool.py` and `tests/test_session_failures.py:130-150`;
  - `scripts/test-codex-tools.py`, `scripts/test-github-content-readmes.py` and `scripts/test-session-failure-vocabulary.py`.

### 2.4 Vendor and d.ts

- **claude-agent-sdk 0.2.165, read-only:**
  - `_errors.py`, `client.py`, `query.py` and `_cli_version.py`;
  - `__init__.py`: imports, exports, `tool`, the schema builder and `create_sdk_mcp_server`;
  - `types.py`: the options, message, rate-limit, session, usage, plugin and sandbox regions;
  - `_internal/message_parser.py`;
  - `_internal/query.py`: initialize, `_read_messages`, `_send_control_request`, interrupt and `stamp_user_message`;
  - `_internal/sessions.py` and `_internal/session_mutations.py`: the public functions;
  - `_internal/sdk_mcp_bridge.py`, `_internal/_task_compat.py` and `_internal/client.py`;
  - `_internal/transport/subprocess_cli.py`: `_find_cli`, `_build_command`, `connect`, `close` and the version check;
  - the vendor `pyproject.toml`.
- **`sdk.d.ts`:** grep only (`Options`, `AccountInfo`, `ModelInfo`, the initialize response, `system/init`, interrupt receipts, priorities, error kinds, CLI flag mentions).

### 2.5 Line-number hygiene

After compaction, every `path:line` in the code map was re-checked with `grep -n` before writing. The pre-compaction notes were off by 1–3 lines in several places, and the code map uses the re-checked numbers:

- decorator lines versus class lines in `lib/dataclasses/codex.py`;
- `vidbyte/tools/builtins/pause.py:87-102`;
- `_ScriptedTransport` at :140, not :170;
- the vendor `close()` caveat at `subprocess_cli.py:978-987`;
- the generator usage lines at :13-15.

## 3. What the likely-areas guess got wrong or missed

### 3.1 Wrong or weaker than assumed

- **"Notes for agents".** None of the touched folder READMEs has this section (harnesses, tools, codex, lib, mcp_server). The only one in the repo is `vidbyte/agents/coding_context/README.md:35`, so there were no review notes to quote.
- **`vidbyte/lib/dataclasses/codex.py` as the pattern.** It is 1,205 lines, already past AGENTS.md's "well below 1,000". Its private validators (:55-79) are C008 debt, and its `__all__` is dynamic (:1205). Copy the record style, not the module wholesale.
- **The sessions tools as the layout to copy.** Their `_caught` (`_base.py:85-90`) is S017 debt. Their "Context Protocol Header" lacks A001's `ROLE IN CODEBASE:`, and `descriptions.py` builds strings from adjacent literals (S062).
- **The README question in the request (request.md:175).** No rule requires a README per package folder, so `native/README.md` stays uncreated. A different shared-file problem was not anticipated: the contract bytes of `native/__init__.py` lack the A001 header fields that every tracked `.py` file needs.
- **"Append-only" export lists.** They are partly impossible:
  - imports must stay isort-sorted (S051/I001);
  - the contract JSON's exports must be sorted (`lint/core/public_api_contract.py:87`).
- **`mcp_server/` "already exposes SDK tools".** True, but it calls `tool.execute` without any `PermissionPolicy` (`vidbyte/mcp_server/handlers.py:84-88`), so WRITE tools are ungated there.
- **R2's `hosts.py`** (request.md:278) does not exist in this repo.

### 3.2 Missed areas that bind the change

- **`vidbyte/agents/base.py:421-490`.** Per-agent tool binding and copying are hard-coded class lists. This file is not in the shared-file contract.
- **`vidbyte/agents/mixins.py:242-293,375-376` and `vidbyte/agents/base.py:1024`.** A sync `run()` uses `asyncio.run` per call and tears down agent-owned subprocesses before its loop closes, so a live session cannot outlive one sync run.
- **`vidbyte/agents/runtime.py`:**
  - how error `ToolResult` metadata is read (:1274-1279, `"error"` / `"error_type"`);
  - `tool_timeout_seconds` wrapping `tool.execute` in `asyncio.wait_for` (:1448-1460);
  - a module-level import of `vidbyte.tools.builtins` (:151), which creates the circular-import risk through `harnesses/__init__.py` → `execution.py:69` → `sessions/session.py:25`.
- **`vidbyte/lib/errors/base.py:129-154`.** `CodexAgentError` carries `failure_code` and all eight A003 fields. `ConfigurationError` is at :235.
- **`vidbyte/lib/constants/codex.py`.** It holds `CODEX_SDK_EXTRA` and the classification table. `tests/test_codex_failure_recovery.py:188-201` checks the table is complete in both directions.
- **`vidbyte/lib/tools/formatter.py:111-118`.** `ToolsFormatter.to_anthropic_tool` is the canonical schema helper for the `BaseTool` → SDK `tool()` conversion; Codex uses `to_codex_tool` at `agents/codex/tools.py:82`.
- **Placement enforcement.** No lint rule enforces placement; only `.github/workflows/agents-md-placement.yml`, which is manual-only.
- **`.github/workflows/static-policy.yml` and `.semgrep/`.** Semgrep is a separate, manual-only workflow.
- **`skills/runtime-primitives/`.** A repo skill written for exactly this kind of adapter.
- **CONTRIBUTING.md and the PR template.**

### 3.3 Vendor facts the request did not anticipate

The code map's §4.1 has these with `path:line`:

- `_find_cli` prefers the bundled CLI;
- `fallback_model` is a single string;
- `load_timeout_ms` belongs to `session_store`;
- plugins are local only;
- `MessageParseError` is not exported;
- `ProcessError` stderr is a placeholder;
- no max-output-token env var exists;
- one `RateLimitEvent` covers one window;
- `system_prompt=None` sends an empty prompt;
- control failures raise a bare `Exception`;
- the extra pulls `mcp`, `anyio` and `jsonschema`.

## 4. What `vidbyte-gates.md` got wrong

The file is `C:/Users/422mi/.claude-work/skills/spec-pipeline/references/vidbyte-gates.md`.

- **Line 19, "CI runs the same `run_ci.py`; semgrep is part of it".**
  - Semgrep is **not** part of `run_ci.py`; `run_source` is at `scripts/run_ci.py:79-93`. It runs in the separate `.github/workflows/static-policy.yml` (:24-30).
  - Both CI workflows are `workflow_dispatch`-only today (`ci.yml:3-9`, "TEMPORARILY DISABLED"; `static-policy.yml:3-6`).
- **Line 19, the full-gate sequence "`--stage source`, then `python scripts/run_ci.py`".** From a worktree, no single `python scripts/run_ci.py` invocation is correct:
  - without `PYTHONPATH`, the source stage tests the canonical checkout's code;
  - with `PYTHONPATH`, the package stage's clean install fails.
  The working sequence is `PYTHONPATH=$(pwd) … --stage source`, then `… --stage package` with no `PYTHONPATH` (field guide `local-ci-verification.md`). The file points to that guide but its own command misleads.
- **Line 28, "Final line must read `AGENT-LINT: PASS …`".** For vidbyte-sdk the final line is `SDK-LINT: PASS` or `SDK-LINT: FAIL` (`lint/core/report.py:58`).
- **Line 36, the placement summary.** It is correct, but it omits two facts:
  - no lint rule enforces placement, and the enforcing LLM workflow is manual-only;
  - `lib/constants/<domain>.py` is the established home for constants (A007 pushes numeric policy values there).

## 5. Process deviations

1. **Some shell calls did not start in the worktree.** Before the compaction, several read-only shell calls started with a `cd` into another directory, or used absolute paths, instead of the required `cd` into the worktree. They covered the vendor SDK, the d.ts, the field guide, `vidbyte-gates.md`, `ls ~/.local/bin` and a transcript grep. Nothing was written or executed. Every later call starts with the worktree `cd`.
2. **One grep matched lines under `docs/`.** A `git grep` without a `':!docs'` exclusion printed match lines from `docs/design/github-content-readmes.md` (lines 546, 611, 621-623). That file was not opened, and none of its content is used.
3. **Recovering from the compaction.** The briefing and the list of files read were recovered from this subagent's own transcript JSONL with read-only `python -I -c` one-liners. No file was created.
4. **Reading the lint baseline.** `python -I -c` was used read-only to print `lint/baseline.json`. This is not a gate run and imports nothing from `vidbyte`.
5. **Files created.** Exactly two: `context/code-map.md` and this report. Nothing was staged or committed, and `git status` still shows only `?? docs/spec/claude-host/`.
