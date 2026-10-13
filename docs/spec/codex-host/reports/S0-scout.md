# S0 scout report: CodexHost

- **Stage:** S0 scout, 2026-10-12.
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host`.
- **HEAD:** `678136bd4358bcf9f120504cecd818d36a3d46fe`. No commits were made, and nothing was staged.
- **Produced:**
  - `docs/spec/codex-host/context/code-map.md`, which has exactly four level-2 headings (checked with `grep -c`);
  - this report.
- **Not done in this stage:** no gate, lint, pytest, pip or install was run. Nothing from `vidbyte` or `openai_codex` was imported or executed.

## Planned file list

These are the planned files, with the reasoning for each in code-map §2.

**New**
- `vidbyte/harnesses/native/__init__.py`: the shared bytes; A001 rejects them as written (code-map §4 C1).
- `vidbyte/harnesses/native/codex/__init__.py`.
- `vidbyte/harnesses/native/codex/*.py`: host, ★ functions, handles and error mapping. The spec author picks the module names.
- `vidbyte/harnesses/native/codex/README.md`: optional. No rule requires it, so `vidbyte/harnesses/native/README.md` is **not** created.
- `vidbyte/tools/builtins/codex/__init__.py`, `_base.py`, `descriptions.py`, and one module per group of tools.
- `vidbyte/tools/toolsets/codex.py`.
- Tests, either as flat `tests/test_codex_host*.py` modules or as a `tests/features/<pack>/` pack. Both layouts exist today.

**Edited**
- `vidbyte/lib/dataclasses/codex.py`
- `vidbyte/lib/enums/codex.py`
- `vidbyte/lib/enums/__init__.py` (shared)
- `vidbyte/lib/enums/failure.py` (shared insertion point after line 46)
- `vidbyte/lib/constants/codex.py`, which needs classification rows or a test fails
- `vidbyte/tools/builtins/__init__.py` (shared)
- `vidbyte/tools/toolsets/__init__.py` (shared)
- `REPO_MAP.md` (shared)
- `vidbyte/harnesses/README.md` (shared)

**Conditional** (edited only if the spec chooses that option)
- `vidbyte/lib/errors/base.py` and `vidbyte/lib/errors/__init__.py`, for a new error class (A003).
- `vidbyte/__init__.py` and `contracts/sdk-public-api.json`, for root exports (C016; regenerate, never hand-edit).
- `vidbyte/tools/README.md`.
- `vidbyte/agents/base.py`, if tools bind through the built-in lists. This file is not on the shared list.

**Must not change**
- `pyproject.toml`
- `lint/baseline.json`
- `vidbyte/agents/codex/*`, whose behaviour stays as is

## Files actually read

"Full" means the whole file was read. Otherwise the ranges are listed.

**Rules and inputs**
- `AGENTS.md` and `CLAUDE.md` (full).
- `docs/spec/codex-host/request.md` (full; re-read 76-231 after compaction).
- `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md` (full).

**Field guide** (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`)
- `init.md`, `local-ci-verification.md`, `blocking-lint-invariants.md`, `strict-config-dataclasses.md`, `class-bound-helpers.md`, `model-facing-tool-contracts.md`, `comment-format.md`, `provider-api-contracts.md`, `review-scope.md` (all full).

**Repository root and CI**
- `REPO_MAP.md`: full before compaction; 1-12, 69, 145-152 and 335-338 after.
- `README.md`: Layer Guide 49-80, Usage 95-110.
- `CONTRIBUTING.md`: 9-86.
- `.github/pull_request_template.md` (full).
- `.github/workflows/ci.yml`, `static-policy.yml`, `agents-md-placement.yml` (full).
- `pyproject.toml` (full).
- `scripts/run_ci.py` (full).
- `scripts/generate-sdk-public-api.py` (full).
- `contracts/README.md`, `contracts/.gitattributes` (full); `contracts/sdk-public-api.json` (header and codex ranges).
- `.semgrep/typed-mapping-boundary-policy.yml`.

**Lint**
- `lint/run.py` (options).
- `lint/baseline.json`, `lint/ruff.toml`, `lint/mypy.ini` (full).
- `lint/core/discovery.py`, `baseline.py`, `runner.py`, `report.py`, `public_api_contract.py`.
- `lint/core/ruff.py` (26-34, 68) and `lint/core/mypy.py` (40-80).
- Rules: a001, a002, a003, a005, a006, a007, a009, c001, c006, c007, c008 (header and diagnostics), c015, c016, s012, s015, s016, s017, s019, s020, s024, s025, s039, s045, s051, s060, s062, s063.
- The ruff codes of s001-s008 and s039-s047, via `grep`.

**`vidbyte/` modules**
- `vidbyte/__init__.py` (import and `__all__` ranges).
- `vidbyte/agents/__init__.py`.
- `vidbyte/agents/base.py` (418-500).
- `vidbyte/agents/fork.py` (178-200).
- `vidbyte/agents/codex/__init__.py`, `README.md`, `transport.py`, `tools.py`, `failures.py`, `result.py` (full before compaction).
- `vidbyte/agents/codex/config.py` (115-290 and the method index) and `metrics.py` (full).
- `vidbyte/agents/codex/agent.py` (grep, 84-86).
- `vidbyte/harnesses/__init__.py`, `README.md`, `errors.py`, and the listing.
- `vidbyte/lib/dataclasses/codex.py` (full before compaction; field indexes and 742-800, 845-867 after).
- `vidbyte/lib/dataclasses/tools.py` (47-53, 113-175, 270-340).
- `vidbyte/lib/dataclasses/security.py` (30-44).
- `vidbyte/lib/enums/__init__.py`, `codex.py`, `failure.py`.
- `vidbyte/lib/constants/codex.py`.
- `vidbyte/lib/errors/base.py` (1-260) and `__init__.py` (grep).
- `vidbyte/lib/tools/formatter.py` (ranges).
- `vidbyte/lib/registries/components.py` (60-127).
- `vidbyte/tools/base.py`, `catalog.py` (27-60), `README.md`.
- `vidbyte/tools/builtins/__init__.py`, `pause.py`.
- `vidbyte/tools/builtins/sessions/__init__.py`, `_base.py`, `fork.py` (full); `descriptions.py`.
- `vidbyte/tools/toolsets/__init__.py` (full), `coding.py` (1-60).
- `vidbyte/tools/mcp/transport.py` (through `git show d3389d80` and grep).
- `vidbyte/mcp_server/server/core.py`, `handlers.py`, `server/handlers/tools_call.py`, `tools_list.py`, `__main__.py`.

**Tests**
- `tests/__init__.py`, `tests/multi_agent/__init__.py`.
- `tests/test_codex_tools.py` (1-322, 636-683).
- `tests/test_codex_failure_recovery.py` (180-215).
- `tests/test_session_failures.py` (125-150).
- `tests/agent_test_support.py` (1-30 and an outline).
- `tests/features/coding_agent/conftest.py` (header) and `README.md`.

**openai-codex 0.162.1, read-only** (`C:/Users/422mi/vidbyte-repos/vidbyte-cli/.venv/Lib/site-packages/openai_codex/`)
- Full: `__init__.py`, `types.py`, `api.py`, `async_client.py`, `client.py`, `_run.py`, `_message_router.py`, `_approval_mode.py`, `_sandbox.py`, `_goal.py`, `_runtime_requirements.py`, `_initialize_metadata.py`, `errors.py`, `models.py`.
- `generated/notification_registry.py`: grep and 265-308.
- `generated/v2_all.py`: `grep -n` and targeted ranges only, never in full.

**Version metadata** (read, not executed)
- `openai_codex*-0.162.1.dist-info/METADATA`, in the vidbyte-cli venv and in the global Python 3.11.
- `C:/Users/422mi/AppData/Roaming/npm/node_modules/@openai/codex/package.json` (head).

## What the likely-areas guess got wrong

The likely-areas guess comes from request.md's Implementation hints (lines 188-205) and the R2 and R3 text it cites.

**Things that do not exist or say otherwise**
1. **`hosts.py`** (request.md:246) does not exist; `git ls-files` finds no `hosts.py`. The phrase "native coding-agent harnesses" appears only in `skills/runtime-primitives/references/runtime-primitives.md:5`.
2. **"Notes for agents"** are implied for the codex README, but none of the codex, harnesses, tools or mcp_server READMEs has that section.
3. **README per folder:** no rule requires one. A009 caps size, S020 is opt-in for READMEs with a File Index, and C015 forbids shipping READMEs. The request's default, not to create `native/README.md`, was right.
4. **Installed CLI version:** "`codex-cli` 0.161.0 is installed on PATH" is wrong. The npm `@openai/codex` package on PATH is 0.162.1, and PATH `codex` is an npm launcher (`codex`, `codex.cmd`, `codex.ps1`). The global Python's `openai_codex`, marked "unverified" in the request, is 0.162.1.
5. **Fork parameters:** the guess was `from_turn_id` and `exclude_turns`. The wire has `last_turn_id` (inclusive) and a bool `exclude_turns`. The high-level `thread_fork` exposes neither.

**Hints that are correct but incomplete**
6. **Generic `request()`:** "`client.py:327` and `async_client.py:132` have a generic `request()`" is correct. However:
   - `AsyncCodex` keeps its client private (`api.py:317`);
   - S012 (baseline 0) fails any `.request(` call without a `timeout`/`timeout_seconds` keyword, and openai-codex's `request()` accepts neither.
7. **Sessions layout:** "Copy the sessions layout" points at modules whose headers fail A001, whose descriptions use adjacent literals (S062), and whose `_caught` interpolates `exc` (S017).
8. **Translators:** "Reuse its translators" is possible only on their own terms. `CodexContentTranslator` takes `CodexAgentSettings` and produces kwargs for the high-level API. It knows only `approval_mode`; it has no `approvals_reviewer`, `disabled_plugin_ids`, `last_turn_id` or token budget.
9. **`CodexForkSettings`:** listed as reusable, but it is an agent-fork record (`context_manager`, `capabilities`, `system_prompt`) with no turn id.

**Stale repository docs**
10. **REPO_MAP drift:** the `vidbyte/tools/toolsets/` entry says "one such bundle", but there are two (REPO_MAP.md:337). There are no entries for `vidbyte/agents/codex/` or `vidbyte/tools/builtins/sessions/`.

**Areas the guess did not name but the change touches**
11. **Missed areas:**
    - `vidbyte/lib/constants/codex.py`: a classification row is required for every new code (`tests/test_codex_failure_recovery.py:192-202`).
    - `vidbyte/lib/errors/`: A003.
    - `vidbyte/agents/base.py`: explicit tool-binding lists.
    - `vidbyte/lib/registries/components.py`: builtins exports become YAML-nameable.
    - `vidbyte/tools/mcp/transport.py:197-201`: the Windows `shutil.which` precedent.
    - `openai_codex/_message_router.py:196-206`: event pruning for unsubscribed turns.

## What vidbyte-gates.md got wrong

The file is `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`.

1. **Final lint line.** It says "Final line must read `AGENT-LINT: PASS …`". The SDK lint prints `SDK-LINT: PASS` or `SDK-LINT: FAIL` (`lint/core/report.py:58`), and `run_ci` ends with `CI passed.` (`scripts/run_ci.py:282`).
2. **Remote checks.** It says "CI runs the same `run_ci.py`; semgrep is part of it". In fact:
   - Semgrep is not in `scripts/run_ci.py`. It runs only in `.github/workflows/static-policy.yml`.
   - `ci.yml`, `static-policy.yml` and `agents-md-placement.yml` are all manual-dispatch only.
   - `ci.yml` runs `--stage source` on 3.11 and 3.12, plus a package job on 3.11.
3. **Worktree gate.** The full-gate row (`run_ci --stage source`, then `run_ci`) leaves out the worktree split the field guide requires. That split is `PYTHONPATH=$(pwd)` for the source stage and none for the package stage (`field-guide/vidbyte-sdk/local-ci-verification.md`).
4. **Suppressions.** Its reason they "do nothing" ("backend rules read the AST, Next.js rules strip comments") describes the `vidbyte` repo. Many SDK rules are ruff- or mypy-backed (`lint/core/ruff.py`, `lint/core/mypy.py`). The SDK also has rule files named for suppressions: `s035_unused_noqa.py`, `s037_blanket_type_ignore.py` and `s038_blanket_noqa.py`, seen in the listing but not read. Whether a targeted `noqa` would hide an SDK finding is unverified. The instruction not to add suppressions still stands.

The gates file's other SDK claims match the repo: `pip install -e ".[dev]"`, the placement summary, `docs/` being opaque, the REGRESSED/ERRORED semantics, and the existence of the field-guide topic.

## Disclosures

1. **Accidental `docs/` grep (earlier in this session).**
   - An early `git grep -n -i "native coding"`, run without a `docs/` exclusion, printed one line from `docs/design/codex-harness-agent.md:374`.
   - That file was not opened, and nothing from that line is used in the code map.
   - Every later repository grep used `-- . ':!docs'` or a path scope outside `docs/`.
2. **Listing inside `docs/`.** I listed `docs/spec/codex-host/context/` and `docs/spec/codex-host/reports/` once before writing, to confirm both exist; both were empty. Nothing else under `docs/` was listed or read except `request.md`.
3. **Scratch file outside the repository.**
   - For the A001 approximation I wrote `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/a001_missing.txt` (643 lines).
   - It is outside the worktree and touches no tracked or untracked repository file.
   - Other entries in that scratchpad directory are not mine.
4. **PATH lookups.** `command -v codex` and `type -a codex` were run as lookups only; the binary was not executed.
5. **Unfollowed doc paths.** Several test and lint headers name `docs/design/...` documents in their RELATED DOCS lines. None was followed.

## Method notes

**A001 count**
- The count of files missing a header field came from read-only `git grep -L` runs, one per required field, over the 1,295 tracked `.py` files.
- The union is 643 files, which equals the baseline.
- This approximates the rule, which uses the module docstring or the first 80 lines, plus a multiline regex. It is not a lint run, so it is marked unverified in the code map.

**Commands used**
- Only read-only commands were used: `git grep`, `git ls-files`, `git log`, `git show`, `git status --porcelain`, `cat`, `sed -n`, `awk`, `grep`, `wc`, `ls`, `find`, `head`, `command -v`, `type -a`.

**Line numbers**
- Line numbers re-verified after the context compaction were corrected where they had drifted, for example the `sessions/_base.py` method lines and the `CodingAgentTools` class line.
