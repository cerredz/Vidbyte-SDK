# S0 scout report: native-thread-compose

- **Stage:** S0 scout.
- **Output:** `docs/spec/native-thread-compose/context/code-map.md`. It has exactly four `## ` headings; `grep -c "^## "` returns 4.
- **Worktree:** `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-native-thread-compose`, HEAD `5c08c35edcb1827e190ca4e2b2b1370808ef24be`. That is the same commit as `origin/feat/native-grok-opencode-meta-hosts`.
- **CLI checkout:** `abd31b4`.
- **Changes made:** none outside the two output files. No commits, no `git add`, no installs, no pytest, no lint, no gate runs.
- **One stdlib-only `python -I -c` check:** whether `functools.partial` shows bound keyword arguments in its repr. It does.
- **Path check:** a script resolved every path cited in the code-map, using its short-form table. All resolve, except names that are meant not to exist: `types.py`, `models.py`, `records.py`, `schemas.py`, `opencode.json`, and the deleted `vidbyte/lib/constants/native_hosts.py`.

## Planned file list

### Existing files the change may modify

Each entry says what pulls the file in. Details are in code-map §2.1.

| # | File | Touched when |
|---|---|---|
| 1 | `vidbyte/harnesses/native/__init__.py` | composites are exported from `vidbyte.harnesses.native` (pinned by the surface test and INV-1) |
| 2 | `vidbyte/lib/enums/__init__.py` | always, for every new public enum |
| 3 | `vidbyte/lib/enums/native_threads.py` or a new `vidbyte/lib/enums/<domain>.py` | always |
| 4 | `vidbyte/lib/dataclasses/native_threads.py` or a new `vidbyte/lib/dataclasses/<domain>.py` | always |
| 5 | `vidbyte/lib/constants/native_threads.py` or a new `vidbyte/lib/constants/<domain>.py` | always, because INV-15 allows no literals in `native/` |
| 6 | `vidbyte/lib/enums/prompts.py` | catalog prompt route |
| 7 | `vidbyte/prompts/README.md` | catalog prompt route |
| 8 | `pyproject.toml` | local prompt route |
| 9 | `vidbyte/harnesses/README.md` | always (line 178 native bullet) |
| 10 | `REPO_MAP.md` | always (lines 159–161) |
| 11 | `vidbyte/lib/README.md` | a lib helper is added |
| 12 | `tests/features/harness_threads/fake_harness.py` | the fake needs workspace-write and fail-then-succeed modes |
| 13 | `tests/features/harness_threads/README.md` and `FEATURE.md` | files are added to the base pack, or its contract changes |
| 14 | `tests/features/harness_threads/test_harness_threads_surface.py` | a pinned export, enum, or `lib.process.__all__` changes |
| 15 | `vidbyte/lib/process/__init__.py` and its modules | diff capture becomes a lib helper |

### New files

- `vidbyte/harnesses/native/compose/__init__.py` and `vidbyte/harnesses/native/compose/*.py`. The subpackage name is the spec's choice under ledger 9.
- Prompt assets, by route:
  - catalog route: `vidbyte/prompts/prompts/<family>/<family>.json` plus its `.md` files;
  - local route: `vidbyte/harnesses/native/compose/prompts/*.md`.
- Optionally `vidbyte/lib/{dataclasses,enums,constants}/<domain>.py`.
- `tests/features/<pack>/` with `FEATURE.md`, `README.md`, `conftest.py` and `test_<pack>_<topic>.py` files.

### Files read for reuse, not modified

- The nine functions and their modules.
- `hostkit/` (`errors.py`, `skills.py`, `launcher.py`).
- `vidbyte/lib/process/`, `vidbyte/lib/dataclasses/process.py`, `vidbyte/lib/dataclasses/validation.py`.
- `vidbyte/lib/errors/base.py`, `vidbyte/lib/enums/failure.py`.
- `vidbyte/prompts/catalog.py`, `vidbyte/prompts/__init__.py`, `vidbyte/prompts/prompts/__init__.py`.

## Files actually read

"Full" means read top to bottom. "Partial" means the named sections or line ranges only. "Header" means the docstring header and function inventory only.

**Rules and briefing**
- Full: `AGENTS.md` (81 lines); worktree `CLAUDE.md`; `docs/spec/native-thread-compose/request.md` (183 lines, read twice); `.github/pull_request_template.md`; `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`.
- Partial: `CONTRIBUTING.md` (lines 9–90).
- Partial: `REPO_MAP.md` (the entries for native, lib/process, lib constants, dataclasses, enums and errors, and prompts; plus `git diff origin/main...HEAD` of the map and both READMEs).

**Base PR spec files**
- Full: `docs/spec/harness-thread-functions/spec.md` (1,046 lines), `test-plan.md` (165), `context/vendor-facts.md` (265).
- Partial: `context/code-map.md` (lines 1–120, the heading list, §2.11, the §3 intro and §4).
- No other file under `docs/` was opened.

**Native package**
- Full: `vidbyte/harnesses/native/__init__.py`.
- Full: `grok/__init__.py`, `opencode/__init__.py`, `muse/__init__.py`.
- Full: `grok/threads.py`, `grok/wire.py`, `opencode/threads.py`, `opencode/wire.py`, `muse/threads.py`, `muse/launcher.py`, `muse/wire.py`.
- Full: `hostkit/__init__.py`, `hostkit/errors.py`, `hostkit/launcher.py`, `hostkit/skills.py`.

**Lib**
- Full: `vidbyte/lib/dataclasses/native_threads.py`, `vidbyte/lib/enums/native_threads.py`, `vidbyte/lib/constants/native_threads.py`.
- Full: `vidbyte/lib/process/__init__.py`, `argv.py`, `runner.py`; `vidbyte/lib/dataclasses/process.py`; `vidbyte/lib/enums/process.py`; `vidbyte/lib/dataclasses/validation.py`.
- Full: `vidbyte/lib/README.md`, `vidbyte/lib/registries/prompts.py`.
- Partial: `vidbyte/lib/errors/base.py` (the class list, `NativeThreadError` from line 558, and `OutputSchemaViolationError`).
- Partial: `vidbyte/lib/enums/failure.py` (the members that matter here and the tail).
- Partial: `vidbyte/lib/dataclasses/__init__.py` and `vidbyte/lib/enums/__init__.py` (exports only).

**Prompts**
- Full: `vidbyte/prompts/catalog.py`, `vidbyte/prompts/__init__.py`, `vidbyte/prompts/prompts/__init__.py`, `vidbyte/prompts/prompts/handoff/handoff.md`.
- Header: `vidbyte/lib/enums/prompts.py`.
- Partial: `vidbyte/prompts/README.md` (headings and family rows) and `vidbyte/paradigms/context_minimal_fanout/prompts/__init__.py` (grep).

**Build, CI and lint**
- Full: `pyproject.toml`, `scripts/run_ci.py`, `.github/workflows/ci.yml`, `.github/workflows/static-policy.yml`.
- Full: `lint/README.md` sections "Running the suite" and "Baseline ratchet"; `lint/baseline.json` (counts).
- Partial: `lint/core/report.py` (the final-line grep).
- Lint rules, full or detection logic: A001, A002, A003, A006, A007, A009, C002, C006, C007, C008, C015, S006, S008, S015, S019, S020, S042, S051, S052, S061, S063, S064.
- Lint rules, header and summary only: A005, A008, S016, S017, S024, S045, S055, S062.

**Tests**
- Full, in `tests/features/harness_threads/`: `FEATURE.md`, `README.md`, `conftest.py`, `fake_harness.py`, and the files `_acceptance`, `_threads`, `_process_bounds`, `_credentials`, `_skills`, `_runner`, `_records`, `_static_policy`, `_surface`.
- Header and inventory only: the files `_arguments`, `_argv`, `_errors`, `_launcher`, `_wsl`.
- Full: `tests/test_prompts_interface.py`.
- Listings only: the `conftest.py` files and the pack folders under `tests/features/`.

**Other SDK code**
- Partial, as targeted excerpts or greps:
  - `vidbyte/__init__.py` (line 539 and the harness import);
  - `vidbyte/harnesses/__init__.py`;
  - `vidbyte/harnesses/README.md` (line 178 and its size);
  - `vidbyte/agents/coding_context/environment.py` (git-head code);
  - `vidbyte/providers/output_schema.py` (lines 95–135);
  - `vidbyte/agents/handoff.py` (lines 170–195);
  - `vidbyte/evals/graders/llm_judge.py` (lines 110–135).
- Package-wide greps: worktree, `"git"`, `TaskGroup`/`gather`, JSON parsers, retry helpers, and `vidbyte.prompts` imports.

**CLI port sources** (`C:/Users/422mi/vidbyte-repos/vidbyte-cli/`)
- Full: `src/vidbyte_cli/lib/runtime_primitives/stages.py`, `stage_failures.py`.
- Full: `src/vidbyte_cli/services/ensemble/service.py`, `settings.py`, `sdk.py`, `runner.py`, `__init__.py`, `prompts/__init__.py`, `prompts/library.py`.
- Full: the six turn prompts and `src/vidbyte_cli/types/ensemble.py`.
- Full: `skills/harnesses/runtime-primitives/SKILL.md`.
- Partial: `src/vidbyte_cli/types/runtime.py` (lines 770–1107 and the class list).
- Partial: `planner_system.md`, `role_system.md`, `selector_system.md` (the JSON contract and identity parts). `implementer_system.md` by grep.
- Every one of the ten prompt files was measured and its placeholders counted by script.

**Field guide**
- Full, SDK (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-sdk/`): `init.md`, `blocking-lint-invariants.md`, `strict-config-dataclasses.md`, `class-bound-helpers.md`, `comment-format.md`, `review-scope.md`, `local-ci-verification.md`, `fallback-coordination.md`, `cli-backed-source-integrations.md`, `prebuilt-agents.md`, `provider-api-contracts.md`, `diagnostic-context.md`.
- Not read, judged not relevant from their `init.md` descriptions: `jev-capability-layout.md`, `runtime-boundaries.md`, `model-facing-tool-contracts.md`, `context-primitives.md`, `tracing-shape-contracts.md`, `declarative-config-resolution.md`, `operation-pricebook-rates.md`, `priced-operation-execution.md`, `cloud-trajectory-sinks.md`, `agents-md-map.md`.
- CLI (`C:/Users/422mi/vidbyte-repos/field-guide/vidbyte-cli/`): `init.md` full. Headings plus sections for `agent-stage-prompts.md` (35–58, 117–153), `runtime-execution.md` (36–42) and `third-party-credentials.md` (headings only).

## What the areas hint or the workspace-facts file got wrong

### Request implementation hints and terminology (`docs/spec/native-thread-compose/request.md`)

1. **Line 123:** "eleven `.md` files". The CLI `services/ensemble/prompts/` folder holds **10**. Ledger 10 names the same ten.
2. **Lines 117 and 122:** "`NativeThreadError` carries a closed `FailureCode` of the form `<harness>.<problem>`". Argument refusals carry `configuration.invalid_argument` (`hostkit/errors.py:142`), and defects carry `runtime.error` (`:159`). There is no `problem` attribute on the error.
3. **Line 120:** lists `CliInvocation` and `CliOutcome` under `vidbyte/lib/process/`. They are defined in `vidbyte/lib/dataclasses/process.py` (lines 51 and 73). `vidbyte.lib.process.__all__` holds only `CliArgv`, `CliRunner` and `ProcessStopper`, and the surface test pins that list.
4. **Line 114 / ledger 4:** treat `GrokPermissionMode.PLAN` as a read-only mode. The member exists, but vendor-facts documents only `default`, `acceptEdits`, `dontAsk` and `bypassPermissions` (vendor-facts lines 51–55). Headless behaviour is unverified.
5. **Ledger 9 and line 60:** "Exported from `vidbyte.harnesses.native`". INV-1 and the surface test pin that `__all__` exactly.
6. **Ledger 11:** offers two Grok fan-out options. The base spec's EC-27 already documents a third safe pattern: concurrent calls whose skill set an earlier call prepared.
7. **Lines 29 and 52:** "direct port of the CLI stages primitive" with an "effort ladder" and "raise effort". The CLI has a fixed effort per stage and no ladder. Its classifier keys on Codex provider codes, not on a problem enum.
8. **Line 124:** the "existing `vidbyte/prompts/prompts/handoff/` family" is correct, but it is a system prompt that turns a run digest into JSON `sections`. It is not a thread-handoff summary prompt.

### Workspace-facts file (`C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`)

1. **Line 19:** "CI runs the same `run_ci.py`; semgrep is part of it". `scripts/run_ci.py:79–93` runs no semgrep. Semgrep runs only in `.github/workflows/static-policy.yml:24–30`, which is dispatch-only.
2. **Line 28:** "Final line must read `AGENT-LINT: PASS …`". The SDK lint prints `SDK-LINT: PASS` or `SDK-LINT: FAIL` (`lint/core/report.py:58`).
3. **Line 19:** the gate sequence leaves out the worktree split. From a worktree, run the source stage as `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`, and the package stage with no `PYTHONPATH` (field guide `local-ci-verification.md:3–8`).

### Other stale facts in briefing files

- Base `spec.md:625` says package "0.2.1". `pyproject.toml:7` is now `0.3.0`.

### Corrections to this stage's own earlier notes

- An interim note said the CLI prompts folder holds "11 .md files, library.py, SKILL.md". The folder holds 10 `.md` files. `SKILL.md` is at `skills/harnesses/runtime-primitives/SKILL.md`.
- Interim prompt sizes were byte counts (for example 59,506 for `planner_system.md`). The code-map reports characters as `Path.read_text` reads them: `planner_system.md` 58,578, `implementer_system.md` 35,852. These are what the SDK caps measure.
- An interim count said 13 enums are pinned by `EXPECTED_ENUMS`. There are **14**. `ShellFlag` is the only class in `vidbyte/lib/enums/native_threads.py` that is not pinned.

### Process note

- Several early shell calls began with `cd` into the CLI checkout instead of the worktree. They were read-only. Every later call starts with the worktree `cd` and reads CLI files by absolute path.
