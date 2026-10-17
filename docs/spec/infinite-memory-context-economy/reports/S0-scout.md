# S0 scout report: infinite-memory-context-economy

Stage S0 (recon). Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-infinite-memory-context-economy`, branch `feat/infinite-memory-context-economy`, HEAD `0f2aeb48`. No commits, installs or gate runs were made. The only files written are this report and `context/code-map.md`.

## Planned file list (before reading code)

This list comes from the AREAS_HINT in the briefing and the request's §B.1 and §C.
- **Rules:** `AGENTS.md`, `REPO_MAP.md`, `scripts/run_ci.py`, `lint/baseline.json`, `pyproject.toml`, the field-guide index, and the entries that apply.
- **Request:** `docs/spec/infinite-memory-context-economy/request.md`, the only file read under `docs/`.
- **Infinite agent:** every file in `vidbyte/agents/infinite/`, plus its README.
- **Filesystem tools:** `read_lines.py`, `write_text.py`, `lib/dataclasses/filesystem.py`, and the filesystem README if one exists.
- **Shared tools:** `grep.py` and the code_search package, `bash.py`, and the three toolsets (`infinite`, `coding`, `paradigm_minimal`).
- **Compaction:** `strategies.py`, `engine.py`, `context_compaction.py`, and the folder README.
- **Runtime and context:** `middleware/pipeline.py`; in `agents/runtime.py`, `_apply_before_model_call_transform`, `_build_system_string` and `_after_tool_iteration`; and the `ContextWindowPlacement`, `ContextManager` and `TextContextItem` classes.
- **Providers:** `providers/anthropic.py`, `agents/pricing/anthropic.py`, the providers README, and OpenAI's caching fields.
- **Infinite lib modules:** constants, enums (infinite, `__init__`, prompts), the registry, dataclasses, and `usage_ledger.py`.
- **Prompts:** every leaf in `prompts/prompts/infinite_memory/` and the manifest.
- **Tests:** `tests/test_filesystem_tools.py`, the infinite pack, and the grep, bash, compaction and Anthropic tests.
- **Contracts:** `contracts/sdk-public-api.json` and the lint rules.

## Files actually read

Every file below was read in full, or the cited ranges were read where the file is very large (`agents/runtime.py`, 2,304 lines: the transform, system-string, loop-block, internal-tool, tool-execution and result-cap regions). There are about 75 source and test paths in all, and code-map §2 has about 60 entries, grouped by item.

Files added beyond the hint:
- `vidbyte/lib/dataclasses/coding.py`: the second user of `OverwriteLineLimit`.
- `vidbyte/tools/filesystem/_base_tool.py`: the `EDIT_DIFF_MAX_LINES` precedent.
- `vidbyte/tools/builtins/code_search/base.py` and `vidbyte/tools/base.py`: GrepTool's inherited constructor and argument helpers.
- `vidbyte/tools/builtins/context/compaction.py`: the model-callable `compact_context` tool, which exposes the same options.
- `vidbyte/lib/dataclasses/middleware.py`: `run_state`.
- `vidbyte/lib/tools/formatter.py`: the tool-result shapes per provider.
- `vidbyte/middleware/builtins/verify_command.py`: a second BashTool consumer, and the `run_state[type(self)]` precedent.
- `vidbyte/agents/coding_context/setup_commands.py` and `vidbyte/lib/constants/coding.py`: a tail-read precedent.
- `vidbyte/lib/util/text.py` (`TokenEstimate`), `vidbyte/lib/tools/filesystem/usage.py` (`FolderUsage`, "no cache") and `vidbyte/lib/util/jsonl.py`.
- `vidbyte/agents/settings/loop.py`: the unused `compaction_trigger_tokens` and `compaction_target_tokens`.
- `vidbyte/context/runtime.py`, `vidbyte/context/manager.py`, `vidbyte/context/primitives/documents.py` and `vidbyte/lib/dataclasses/context.py`.
- `vidbyte/lib/dataclasses/model_configs.py`, `vidbyte/lib/runners/text.py` and `vidbyte/lib/http/vidbyte_gateway.py`: AUTO mode goes through the gateway.
- `vidbyte/providers/gemini.py`: the `_attach_cache` precedent.
- `vidbyte/lib/providers/sqlite.py`, `vidbyte/evals/registry.py` (grep only) and `vidbyte/lib/dataclasses/validation.py`.
- `vidbyte/middleware/builtins/delegation_limits.py`, `vidbyte/__init__.py` and `vidbyte/lib/registries/__init__.py`.
- The `vidbyte/agents/README.md`, `vidbyte/tools/README.md`, `vidbyte/middleware/README.md` and `vidbyte/prompts/README.md` READMEs.
- Tests: `tests/features/sdk_managed_text/test_managed_text_wire_contract.py` (the gateway key allowlist), `tests/features/coding_agent/` (bash contract, process bounds, verify command, conftest, FEATURE.md), and `tests/test_context_compaction_middleware.py`.

Field-guide entries read (from `field-guide/vidbyte-sdk/`):
- `init.md`
- `local-ci-verification.md`
- `runtime-boundaries.md`
- `strict-config-dataclasses.md`
- `blocking-lint-invariants.md`
- `prompt-families.md`
- `comment-format.md`
- `model-facing-tool-contracts.md`
- `provider-api-contracts.md`
- `class-bound-helpers.md`
- `prebuilt-agents.md`
- `agents-md-map.md`, `context-primitives.md` and `review-scope.md`, headings only. The last two do not apply.

Not found: `vidbyte/tools/filesystem/README.md`, a README in `vidbyte/middleware/compaction/`, and any Anthropic-provider-specific unit test beyond the managed wire contract.

## What AREAS_HINT got wrong or missed

- **Line anchors from the #1159 branch** (as the briefing warned):
  - `agent.py:87` is now `agent.py:80`.
  - `launch.py:313` is now `launch.py:290`.
  - `launch.py:309` is now `launch.py:276` (map) and `launch.py:286` (tools).
  - `strategies.py:649` is now `strategies.py:663`.
  - `lib/dataclasses/filesystem.py:75` is now `lib/dataclasses/filesystem.py:74-75`.
  - `bash.py:34` is correct.
- **"Compaction is a per-call view":** confirmed (`runtime.py:1085-1110`). The hint did not mention that the engine also rebuilds the strategy object on every call (`engine.py:161`), so a strategy cannot hold state between calls. The only per-run store is `ctx.run_state`.
- **The cache-prefix framing (items 7 and 9):** the hint treats the map as the per-call change to the system string. It missed the loop-settings block `- max_iterations: n/500` (`runtime.py:1690`), which sits before the map and changes on every call.
- **Item 9 is not a one-file fix:** the hint scopes it to the adapter. It missed that InfiniteMemory's default AUTO mode always goes through the Vidbyte gateway (`model_configs.py:152-169`), whose allowed Anthropic keys are pinned in `test_managed_text_wire_contract.py:49/173/181`.
- **The RETRIEVER role conflicts with the registry test:** `test_infinite_memory_contract.py:383-387` asserts that every `InfiniteAgentRole` member holds `remember` and `write_note`.
- **The complexity budget:** the hint said to read the lint rules for file length. It missed the feature's own budget test: at most 8 modules in `vidbyte/agents/infinite/` (there are exactly 8 now), and at most 400 lines after the header per module (`launch.py` is at 368).
- **BashTool is shared:** the hint said "SDK-wide" but did not list `VerifyCommandMiddleware` or the coding-agent tests that pin head-only output (`test_bash_tool_contract.py:173`, `test_bash_tool_process_bounds.py:241`, `test_coding_agent_verify_command.py:367`, `FEATURE.md:23`).
- **Confirmed as stated:**
  - `pair_started` journals only `{"key": key}` (`journal.py:95`).
  - `events.py` and `context/handoff/infinite.py` are absent.
  - `cache_control` appears nowhere under `vidbyte/`.
  - No provider sends an OpenAI-style caching field.
  - The only `sqlite3` users are `lib/providers/sqlite.py` and `evals/registry.py`.
- **"The `TextContextItem` freeze":** not in the hint. `primitive_frozen` already exists with lock semantics (`manager.py:82-85`), which collides with the request's word "freeze".

## What vidbyte-gates.md got wrong or overstated (AGENTS.md wins)

- **Install step:** gates lists `python -m pip install -e ".[dev]"` as the first gate step. AGENTS.md states no install command at all.
- **`--stage source` as a gate step:** gates lists `python scripts/run_ci.py --stage source` before the full run. The stage exists (`run_ci.py` accepts `all`/`source`/`package`), but AGENTS.md says "none of the narrow verification scripts beside it substitutes for it". Only the bare `python scripts/run_ci.py` counts as the gate.
- **PYTHONPATH:** gates does not mention it. The request says to run the gate with `PYTHONPATH` unset. The field guide says to run the source stage with `PYTHONPATH=$(pwd)` and the package stage without it. The infinite pack README runs pytest with `PYTHONPATH=$(pwd)`. This contradiction is recorded in code-map §4.
- **Lint description:** "`lint/run.py` exits non-zero when a rule REGRESSED" is consistent with `lint/baseline.json` being a count ratchet. The rule texts for S047 and S052 were not opened.

## Verification of five sampled path:line facts

Each was re-checked with a read-only `sed -n`, `grep -n` or `git grep` in this session after the map was drafted:

1. `vidbyte/agents/runtime.py:1690`: `lines.append(f"- max_iterations: {iteration_count}/{self.config.max_iterations}")`. Matches.
2. `vidbyte/agents/infinite/launch.py:290`: `middleware=(MessageHistoryCompactionMiddleware.trim_with_provider_boundaries(max_tokens=INFINITE_HISTORY_MAX_TOKENS), *limits),`. Matches.
3. `vidbyte/middleware/compaction/strategies.py:663`: `class ToolOutputSlidingWindowCompaction(BaseCompaction):`. Matches.
4. `vidbyte/providers/anthropic.py:95`: `payload["system"] = instructions` (inside `_attach_instructions`, 91-95). Matches.
5. `tests/features/sdk_managed_text/test_managed_text_wire_contract.py:173`: "a key outside the list is a guaranteed 422 at the gateway". Matches. Line `:49` holds the Anthropic `EMITTED_KEYS` set, which has no `cache_control`.

The same pass also corrected several ranges in the draft before it was final:
- `engine.py` branch lines: now 195-198, 203-206 and 207-208.
- `context_compaction.py` builders: now 163-165 and 173-175.
- `strategies.py` trim internals: now 607, 624, 626 and 632-635.
- `strategies.py` window loop: now 683-696.
- The wire-test subset assertion: now `:181`.
- `workspace.py` map counts: now 213-217.

## Unverified items carried forward

- Gateway pass-through of `cache_control`, either top-level or block-level.
- Whether Anthropic's automatic caching works with the `anthropic-version: 2023-06-01` header.
- FTS5 availability in the CI and dev Python builds.
- Whether S047 and S052 flag synchronous `sqlite3` inside `async def`.
