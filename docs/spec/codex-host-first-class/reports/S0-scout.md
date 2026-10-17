# S0 scout report: codex-host-first-class (slice 2)

| Field | Value |
|---|---|
| Stage | S0 scout |
| Date | 2026-10-17 |
| Branch | `feat/codex-host-first-class` |
| HEAD | `a7730107` (no commits made) |
| Output | `docs/spec/codex-host-first-class/context/code-map.md` |
| Writes | the two files above only. No installs, no gate runs, no `codex` binary, no change to the canonical checkout. |

## Planned list

The plan was the file set from the briefing and request.md:141-145, widened as the reading found more:

1. AGENTS.md, plus the READMEs of each folder to be touched.
2. The CodexHost package, `vidbyte/harnesses/native/codex/*`, all 12 modules.
3. Lib records, constants and enums:
   - `lib/constants/codex_host.py`, `lib/constants/codex.py`
   - `lib/dataclasses/codex_host.py`, `codex_host_inputs.py`, `codex.py`
   - `lib/enums/codex.py`, `lib/enums/__init__.py`, `lib/enums/failure.py`
   - `lib/errors/base.py` (the Codex part)
4. `agents/codex/config.py` (`turn_kwargs`) and `agents/codex/tools.py`, which the hint names.
5. The tool layer:
   - `tools/builtins/codex/*`
   - `tools/toolsets/codex.py`, `tools/toolsets/__init__.py`
   - `tools/builtins/__init__.py`, `tools/base.py`
   - `lib/dataclasses/tools.py` (`ToolPermission`)
6. Tests:
   - `tests/features/codex_host/*`: fakes, support, every pinning module, FEATURE.md and README.
   - `tests/features/harness_threads/test_harness_threads_surface.py` and `test_harness_threads_static_policy.py`.
   - The `tests/test_codex_*.py` inventory.
7. Lint and gate:
   - `lint/baseline.json`, `lint/core/report.py`, `lint/rules/a009_readme_size_limit.py`
   - `scripts/run_ci.py`, `pyproject.toml`
8. Field guide `vidbyte-sdk/`:
   - `model-facing-tool-contracts.md`, `comment-format.md`
   - `blocking-lint-invariants.md`, `class-bound-helpers.md`, `local-ci-verification.md`
9. The allowed docs:
   - `docs/spec/codex-host-first-class/request.md`
   - `docs/spec/codex-host-hardening/context/codex-gap-report.md`
   - `docs/spec/codex-host-hardening/context/code-map.md`
   - `docs/spec/codex-host-hardening/spec.md` §8.5, §9 and §12.3 only
10. Protocol ground truth:
    - the scratchpad 0.163.0 schemas (`schema-exp`, `schema-stable`, `methods.txt`, `coverage-matrix.md`)
    - TUI source `codex-src/codex-rs/tui/src/app/side.rs`
    - SDK `openai_codex` 0.163.0 (`client.py`, `api.py`, `_message_router.py`, `async_client.py`, `generated/v2_all.py`), read through the scratchpad venv with `-I`
11. `~/.claude/skills/spec-pipeline/references/vidbyte-gates.md`

## Files actually read

**Read in full:**
- AGENTS.md (81)
- `native/codex/`: host.py (937), connection.py (604), wire.py (797), turns.py (456), thread_helpers.py (351), errors.py (240), skill_functions.py (225), preflight.py (210), turn_events.py (157), reviews.py (156), oneshot.py (137), `__init__.py` (30)
- `lib/constants/`: codex_host.py (475), codex.py (640)
- `lib/dataclasses/`: codex_host.py (873), codex_host_inputs.py (424)
- `lib/enums/`: codex.py (330), `__init__.py` (341), failure.py (344)
- `agents/codex/`: config.py (295), tools.py (198)
- `tools/builtins/codex/`: `_base.py` (251), `__init__.py` (82), descriptions.py (84), threads.py (335), thread_helpers.py (240), skill_functions.py (212), live.py (190), delegation.py (134), readiness.py (97)
- `tools/toolsets/codex.py` (105), `tools/base.py` (181)
- `tests/features/codex_host/`: codex_host_fakes.py (902), codex_host_helper_fakes.py (237), codex_host_support.py (828)
- request.md
- The field-guide entries listed in the plan; vidbyte-gates.md (38)

**Read in the relevant parts:**
- `lib/dataclasses/codex.py` (1,205): `CodexClientSettings`, `CodexThreadSettings`, `CodexTurnSettings`, `__all__`
- `lib/errors/base.py` (`CodexAgentError`)
- `tools/builtins/__init__.py` (380): imports, `__all__`, docstring
- `lib/dataclasses/tools.py:47-53`
- Test modules, at their pinning literals and assertions: packaging, helper_surface, records, hardening_contract, hardening_records, inputs, sdk_contract, tools, helper_tools, tool_hardening, error_details, helper_lifecycle, live_smoke
- FEATURE.md and README.md of `codex_host`
- The two harness_threads tests named above
- `lint/baseline.json`, `lint/core/report.py`, the a009 rule, `scripts/run_ci.py` (the stages)
- The gap report (whole file, by sections)
- The hardening code-map
- `spec.md` §8.5, §9 and §12.3
- SDK `client.py`, `api.py` and `_message_router.py` at the cited lines; `v2_all` was checked by introspection

**Inventoried only (line counts and roles, not read in full):** the other `tests/features/codex_host/test_*.py` modules, the 8 `tests/test_codex_*.py` files, and the folder READMEs (character counts, and a check for a `## Notes for agents` section).

**Checked in the scratchpad venv, read-only `-I`, no files created:**
- `TurnStartParams.model_validate` drops `collaborationMode`.
- `ThreadListParams` drops `parentThreadId`.
- The SDK `model_config` is `{'populate_by_name': True}`.
- Which `v2_all` Params and Response classes exist for each slice-2 method.
- `inspect.iscoroutinefunction` is False for an async generator.

## What the hint or vidbyte-gates.md got wrong

1. **`vidbyte/agents/codex/tools.py` is not the CodexHost tool layer.** It is the dynamic-tool bridge (`CodexToolTranslator`, `CodexToolBridge`, `CodexToolCallHandler`) for Codex harness agents. The model-facing tools are `vidbyte/tools/builtins/codex/*`, catalogued by `vidbyte/tools/toolsets/codex.py`.
2. **`lib/enums/codex*.py` is a single file**, `vidbyte/lib/enums/codex.py`. No other `codex*` enum module exists.
3. **The raw-call names in the request are stale.** request.md:145 says `RAW_RESPONSES` and `SPENDING_RAW_METHODS`; the code has `CODEX_HOST_RAW_RESPONSE_MODELS` and `CODEX_HOST_SPENDING_RAW_METHODS` (`lib/constants/codex_host.py:46,59`).
4. **The lint pass line is wrong.** vidbyte-gates.md:28 says it reads `AGENT-LINT: PASS`. This repo prints `SDK-LINT: PASS` (`lint/core/report.py:58`).
5. **The full gate in vidbyte-gates.md is incomplete.** vidbyte-gates.md:19 gives `pip install -e ".[dev]"`, then `--stage source`, then a bare `python scripts/run_ci.py`. It leaves out two things: the worktree's `PYTHONPATH=$(pwd)` for the source stage, and the separate `--stage package` run without PYTHONPATH (field guide `local-ci-verification.md:3-8`; `scripts/run_ci.py:74-76,261-262`). Its install step also conflicts with the "no pip" rule of this run, since the scratchpad venv is already installed.
6. **Slice-1's code map overstates the SDK.** The hardening `code-map.md:131` says SDK 0.163.0 `ThreadListParams` has `parentThreadId` and `ancestorThreadId`. Only the app-server schema has them, as exp-only fields. The SDK model lacks both, and validation drops them.
7. **Gap report errors:**
   - Line 24 attributes the drop to `extra="ignore"`; the SDK sets no `extra`, and pydantic's default gives the same effect.
   - Line 271 leaves `personality` and `multiAgentMode` out of `thread/settings/update`.
   - Line 282's `wire.py:203-205` has moved to `wire.py:207-209`.
8. **"Is a git repository: false" in the environment note is wrong.** The worktree is on `feat/codex-host-first-class` at `a7730107`. `git status` shows only the untracked `docs/spec/codex-host-first-class/`.
9. **Source headers have stale counts.**
   - `tools/builtins/codex/__init__.py:3` and `tools/toolsets/codex.py:3,5` say every host function except `delete_codex_thread` has a tool; `forget_codex_turns` has none either.
   - `codex_host_fakes.py:3,33` still describes app-server 0.162.1.

## Not done in this stage

The following were left out on purpose:
- No gate, test or lint run.
- No live binary.
- No `generate-json-schema` run; the existing 0.163.0 scratchpad schemas were used.

The items marked "unverified" are listed in code-map §4.4.
