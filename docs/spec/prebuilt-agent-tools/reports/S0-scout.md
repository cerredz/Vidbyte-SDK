# S0 Scout report: prebuilt-agent-tools

- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-prebuilt-agent-tools`
- **Branch:** `feat/prebuilt-agent-tools`
- **Base HEAD:** `8387d66680951766f02b0d740d78eb6450cb6419`
- **Stage HEAD:** no commits
- **Produced:** `docs/spec/prebuilt-agent-tools/context/code-map.md`, with four numbered `##` sections.
- **Tree state:** only the untracked `docs/spec/prebuilt-agent-tools/` changed. No commit, no install, no gate or lint run, no file outside the two outputs modified.

## Planned list (before reading)

1. `AGENTS.md`, `CLAUDE.md`, `REPO_MAP.md` (header, tools, lib, and tests sections), `docs/spec/prebuilt-agent-tools/request.md`.
2. Tool mechanism: `vidbyte/tools/{base,function_tool,decorators,catalog,types,executor,adapters,mixins,customization,_internal,__init__}.py`, plus `vidbyte/lib/dataclasses/tools.py` and `vidbyte/lib/tools/formatter.py`.
3. Existing builtins, from the request's hint: `vidbyte/tools/builtins/__init__.py`, `calculator.py`, `code_execution.py`, `document_retrieval.py`, and `bash.py`.
4. Toolsets: `vidbyte/tools/toolsets/*`.
5. Discovery and attachment: `vidbyte/lib/registries/components.py`, `vidbyte/lib/registries/tools.py`, and `vidbyte/agents/base.py`.
6. Placement homes: `vidbyte/lib/enums/__init__.py`, `vidbyte/lib/dataclasses/__init__.py`, `vidbyte/lib/errors/base.py`, and `vidbyte/lib/constants/`.
7. Gates: `scripts/run_ci.py`, the `lint/` core plus the rules relevant to new tool modules, `lint/baseline.json`, `pyproject.toml`, and `.github/workflows/*`.
8. Tests from the hint: `tests/test_tools_catalog.py`, `tests/test_tool_core.py`, `tests/test_custom_function_tools.py`, `tests/test_function_tool_parameter_types.py`, and `tests/conftest.py`.
9. The field guide entries named in the hint.

## Files actually read

Full or relevant sections unless marked otherwise.

- **Rules and request:** `AGENTS.md`, `CLAUDE.md`, `docs/spec/prebuilt-agent-tools/request.md`, `REPO_MAP.md` (header, `tests/`, `vidbyte/lib/*`, `vidbyte/tools/*` sections), and the orchestrator's gates reference.
- **`vidbyte/tools/`:** `README.md`, `base.py`, `function_tool.py`, `decorators.py`, `types.py`, `mixins.py`, `_internal.py`, `catalog.py`, `__init__.py`, `adapters.py`, `executor.py`, `customization.py`, `client.py`.
- **`vidbyte/lib/`:**
  - Full: `dataclasses/tools.py`, `registries/components.py`, `registries/tools.py`, `enums/__init__.py`.
  - Partial: `tools/formatter.py` (lines 1–182 and 660–844), `dataclasses/__init__.py`, `errors/base.py`, `dataclasses/config.py` (located lines 69–81, 478–480, 589, 755 by grep), `dataclasses/agent_descriptor.py` (49, 284–286).
  - Located by grep: `constants/codex.py:183-185`.
- **`vidbyte/tools/builtins/`:**
  - `__init__.py`, `calculator.py`, `document_retrieval.py`, `pause.py`, `code_execution.py`.
  - `reasoning/__init__.py`, `reasoning/_base.py`, `reasoning/_parsing.py`, `reasoning/swot_trace.py`, `reasoning/fermi_estimate.py`.
  - `memory/__init__.py`, `memory/base.py`, `editing/__init__.py`, `code_search/__init__.py`.
- **`vidbyte/tools/filesystem/`:** `__init__.py`, `_base_tool.py`, `base.py`, `checksum.py`, `diff.py`, `exists.py`. Every other filesystem tool name was confirmed by a `git grep` of its `name=` line.
- **`vidbyte/tools/toolsets/`:** `__init__.py`, `coding.py`, `paradigm_minimal.py`.
- **Root package:** `vidbyte/__init__.py` (full, 1,297 lines).
- **Agents:** `vidbyte/agents/base.py` (180–200, 325–350, 1388–1420).
- **Config:** `vidbyte/config/README.md` (1–40).
- **Scripts:** `scripts/run_ci.py` and `scripts/check_reasoning_trace_contracts.py` in full. Headers only: `scripts/check_context_write_paths.py`, `scripts/check_context_primitive_introductions.py`, `scripts/generate-sdk-public-api.py`.
- **`lint/`:**
  - Core and config: `README.md`, `baseline.json`, `run.py`, `ruff.toml`, `mypy.ini`, `__init__.py`, `core/registry.py`, `core/discovery.py`, `core/ruff.py`.
  - Rules in full: A001, A002, A003, A006, A007, A009, S007, S008, S015, S016, S017, S020, S021, S024, S025, S062. C006 head only.
  - Rule headers only: C001, C002, C007, C008, C015, C016, A005, S042, S051, S060, S061.
- **Packaging and CI:** `pyproject.toml`, the `contracts/` listing, `.semgrep/*`, `.github/workflows/ci.yml`, `.github/workflows/static-policy.yml`.
- **Tests:**
  - Full: `tests/test_tools_catalog.py`, `tests/test_tool_core.py`, `tests/test_custom_function_tools.py`, `tests/test_function_tool_parameter_types.py`.
  - The `tests/features/` listing; `tests/features/sdk_operation_costs/` `FEATURE.md`, `README.md`, and the head of one test; the head of `tests/features/coding_agent/conftest.py`.
  - By grep: `tests/features/coding_agent/test_coding_agent_contract.py:102-109`.
- **Field guide (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`):** `init.md`, `model-facing-tool-contracts.md`, `prebuilt-agents.md`, `strict-config-dataclasses.md`, `blocking-lint-invariants.md`, `local-ci-verification.md`, `review-scope.md`, `comment-format.md`, `class-bound-helpers.md`, `agents-md-map.md`, `declarative-config-resolution.md`, `runtime-boundaries.md`.

### Planned but not read

- `vidbyte/tools/builtins/bash.py` was not opened. It exists: `tests/features/coding_agent/test_coding_agent_contract.py:103` imports `vidbyte.tools.builtins.bash.BashTool`.
- `tests/conftest.py` does not exist.

## What the request's areas hint got wrong or left out

1. **Builtins as a small set.** The hint (request.md:40) lists `calculator.py`, `bash.py`, `code_execution.py`, and `document_retrieval.py` as the existing builtins. In fact `vidbyte/tools/builtins/reasoning/` already holds 218 tool classes, behind a CI script that hard-codes 182. That package, not the four files listed, is the precedent for shipping hundreds of tools.
2. **`calculator.py` and `document_retrieval.py` are not exported** from `vidbyte/tools/builtins/__init__.py`, so they are not YAML-declarable. This is deliberate, per field guide `declarative-config-resolution.md`.
3. **`vidbyte/tools/catalog.py` is not a registry.** It is an agent-local `Tools` collection that rejects duplicate names. YAML discovery is `ComponentRegistry` scanning `vidbyte.tools.builtins` for `BaseTool` subclasses, which excludes `@tool` functions.
4. **Filesystem tools are missing from the hint.** The many-small-tools family lives in `vidbyte/tools/filesystem/`, outside `builtins/`, and already claims generic names such as `diff`, `checksum`, `find`, `stat`, and `zip`.
5. **Test files.** `tests/test_tools_catalog.py` is an 80-line generic unittest file. There is no `tests/conftest.py`. Newer tests follow the `tests/features/<pack>/` convention (`FEATURE.md`, `README.md` with a File Index, A001-headed pytest functions).
6. **Field guide coverage.** The hint omits field guide entries that apply directly: `comment-format.md`, `class-bound-helpers.md`, `agents-md-map.md`, and `declarative-config-resolution.md`.
7. **Missing constraints.** The hint does not mention:
   - The 128-entry cap on declarative tool lists.
   - S025's 4-sentence rule for class-based tools.
   - A001's header requirement on every new `.py`, tests included.
   - The C016 contract regeneration if the root `__all__` changes.

## What the gates reference got wrong

1. **Semgrep is not part of `scripts/run_ci.py`.** It runs only in `.github/workflows/static-policy.yml:24-30` (`semgrep==1.170.1`), against git-tracked files. A local `run_ci.py` pass does not cover it.
2. **Worktree invocation.** The reference omits the worktree-specific invocation that field guide `local-ci-verification.md` requires: `PYTHONPATH=$(pwd)` for the source stage, and no PYTHONPATH for the package stage.
3. **Reasoning contract script.** The reference does not mention that the source stage runs `scripts/check_reasoning_trace_contracts.py` with a hard-coded 182. Any change to the reasoning catalog fails there before pytest.

## Deviations from instructions

- None. All shell calls were read-only (`git grep`, `git ls-files`, `wc`, `sed -n`, `head`, `ls`).
- One `head` and `ls` call read the S0 task output path and listed the spec folder to confirm no stray files existed.
- No file under `docs/` was read except `request.md`.
