# S0 Scout report: harness browser tools

- Stage: S0 scout. Status: DONE.
- Output: `docs/spec/harness-browser-tools/context/code-map.md` (4 sections, 488 lines).
- Worktree HEAD: `845a4d9b` (= origin/main), no commits made. Files created: this report and code-map.md only.
- Nothing was installed and no gate or pytest was run. The only Python run was a read-only `ast` count of `FailureCode` members, plus `import vidbyte` path probes with `py -3.11`.

## Planned file list (before reading code)

The list started from the areas hint and the PR #1036 file list (`gh pr view 1036`, read-only), then grew as files led to others.

1. Rules:
   - `AGENTS.md`
   - `REPO_MAP.md`
   - the folder READMEs (`vidbyte/harnesses/README.md`, `vidbyte/lib/README.md`, `vidbyte/lib/registries/README.md`, `tests/features/harness_threads/README.md` and `FEATURE.md`)
   - the gates reference
   - field guide `init.md` plus 8 entries
2. Request: `docs/spec/harness-browser-tools/request.md`.
3. Thread functions: `vidbyte/harnesses/native/**` (14 modules).
4. lib layer:
   - `vidbyte/lib/{constants,dataclasses,enums}/native_threads.py`
   - `vidbyte/lib/dataclasses/{process,validation}.py`
   - `vidbyte/lib/enums/{process,failure,__init__}.py`
   - `vidbyte/lib/errors/{__init__,base}.py`
   - `vidbyte/lib/process/{__init__,argv,runner}.py`
5. Registries: `vidbyte/lib/registries/{README.md,__init__.py,runtimes.py}`, plus the header of `provider_keys.py`.
6. MCP stack:
   - `vidbyte/lib/config/mcp_presets.py`
   - `vidbyte/tools/mcp/{presets,types}.py`
   - `vidbyte/lib/dataclasses/mcp.py`
   - `vidbyte/lib/configs/__init__.py`
7. Root: `vidbyte/__init__.py` (native imports only).
8. Tests:
   - `tests/features/harness_threads/*` (18 files)
   - `tests/test_session_failures.py`
   - `tests/test_mcp_stdio_transport.py` (the flake)
9. Gates and lint:
   - `scripts/run_ci.py`
   - `scripts/test-session-failure-vocabulary.py`
   - `scripts/generate-sdk-public-api.py`
   - `lint/rules/README.md`
   - lint rules A001, A002, A006, A007, A009, C016, C019
   - `.github/workflows/{ci,static-policy,agents-md-placement}.yml`
   - `pyproject.toml` (pytest config)

## Files actually read

### Read in full

- `AGENTS.md`
- `docs/spec/harness-browser-tools/request.md` (§A–§D)
- `C:/Users/422mi/.claude/skills/spec-pipeline/references/vidbyte-gates.md`
- Field guide `init.md`, `blocking-lint-invariants.md`, `local-ci-verification.md`, `strict-config-dataclasses.md`, `declarative-config-resolution.md`, `class-bound-helpers.md`, `cli-backed-source-integrations.md`, `comment-format.md` and `review-scope.md`
- All 14 modules under `vidbyte/harnesses/native/`
- `vidbyte/lib/constants/native_threads.py`
- `vidbyte/lib/dataclasses/{native_threads,process,validation}.py`
- `vidbyte/lib/enums/{native_threads,process,failure}.py`
- `vidbyte/lib/process/{__init__,argv,runner}.py`
- `vidbyte/lib/registries/{README.md,__init__.py,runtimes.py}`
- `vidbyte/lib/configs/__init__.py`
- `vidbyte/tools/mcp/presets.py`
- `vidbyte/tools/mcp/types.py`
- `vidbyte/harnesses/README.md`
- `vidbyte/lib/README.md`
- `lint/rules/README.md`
- All 18 files in `tests/features/harness_threads/`

### Read in part

These are large files where the relevant regions were enough.

- `vidbyte/lib/config/mcp_presets.py` (1,833 lines): header, `McpPresetDefinition`, every "Search & Web Research" preset, the system-utilities head, the catalog. The briefing said to list the web/browser presets only.
- `vidbyte/lib/errors/base.py` (615 lines): header, lines 480–615 including `NativeThreadError`.
- `vidbyte/lib/errors/__init__.py`.
- `vidbyte/lib/enums/__init__.py` (304 lines): header and the native/process import and export lines.
- `vidbyte/__init__.py` (1,376 lines): grep for `harnesses` and `native` only.
- `REPO_MAP.md`: index, `vidbyte/harnesses/`, `harnesses/native/` and every `vidbyte/lib/*` entry.
- `scripts/run_ci.py`: header, the `run`, `run_source` and `run_package` stages, `parse_args`.
- `lint/rules/a006_directed_dependency_graph.py`: lines 1–140.
- Headers of `a001`, `a002`, `a007`, `c019`, `a009` (ceiling line), `c016` (grep).
- `vidbyte/lib/dataclasses/mcp.py`: header and record.
- `vidbyte/lib/registries/provider_keys.py`: header and imports.
- Imports of the other registry modules (grep).
- `tests/test_session_failures.py`: grep.
- `tests/test_mcp_stdio_transport.py`: class and test location.
- `scripts/test-session-failure-vocabulary.py`: header.
- `scripts/generate-sdk-public-api.py`: purpose line.
- `.github/workflows/ci.yml`, `static-policy.yml`, `agents-md-placement.yml`: the relevant lines.
- `pyproject.toml`: the pytest config lines.

### Located only (path and symbol confirmed, body not read)

- `vidbyte/harnesses/serialization.py:65` (`HarnessRedactor`)
- `vidbyte/lib/util/credential_keys.py:52` (`CredentialKeyPolicy`)
- `vidbyte/tools/builtins/operations/clients/{browserbase,firecrawl}.py`

### Not read, by rule

- Anything else under `docs/`, including `docs/spec/harness-browser-tools/pipeline.md` and `docs/spec/harness-thread-functions/`.
- The `vidbyte-sdk-browser-agent` worktree.
- PRs #1044 and #1055.

## What the areas hint got wrong or left out

- **Lint/script checks that target native/.** The hint expected "any `lint/` rule or `scripts/` check that targets `vidbyte/harnesses/native/` or pins public names". There are none: `git grep` over `lint/`, `scripts/` and `.semgrep/` finds no reference to `harnesses.native`. Only A006 names `vidbyte.harnesses`. Every native pin lives in tests: `test_harness_threads_static_policy.py` (INV-15, INV-20) and `test_harness_threads_surface.py` (exports, signatures, enums, failure codes, `lib.process.__all__`).
- **Root exports.** `vidbyte/__init__.py` "if harness functions are exported there": they are not. The root never imports `native`, a test pins that, and changing the root `__all__` turns a branch-scoped test red locally and needs a C016 contract update.
- **`vidbyte/tools/mcp/` as a reuse candidate.** It sits in the tools layer:
  - native/ may not import it (INV-20);
  - lib/ may not import its concrete modules (A006);
  - any edit there turns `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` red locally.
- **Files the hint missed:**
  - `vidbyte/lib/dataclasses/process.py` (`CliInvocation`) and `vidbyte/lib/dataclasses/validation.py` (the canonical field validators, which the field guide requires).
  - `vidbyte/lib/enums/process.py`.
  - `vidbyte/lib/dataclasses/mcp.py`, an existing MCP domain module. That matters for AGENTS.md's "add to the existing domain module" rule.
  - `vidbyte/harnesses/serialization.py` (`HarnessRedactor`, used by the error scrubber).
  - `tests/test_session_failures.py:143` (every FailureCode value needs a ".").
  - `.github/workflows/static-policy.yml` (the semgrep job).
- **Notes for agents.** None of the hinted folder READMEs has a "Notes for agents" section.

## What the gates reference got wrong

- **Semgrep.** The reference (`vidbyte-gates.md:19`) says "CI runs the same `run_ci.py`; semgrep is part of it". `scripts/run_ci.py:79-93` does not run semgrep. It runs only in `.github/workflows/static-policy.yml:24-30` (`semgrep==1.170.1`, `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`). The full local gate therefore does not cover semgrep; it has to be run separately (field guide `local-ci-verification.md`).
- **Editable install.** Not stated in the reference: the editable install points at the main clone `C:\Users\422mi\vidbyte-repos\vidbyte-sdk`. `import vidbyte` loads the worktree copy only when the cwd is the worktree root or `PYTHONPATH` is set. This was checked with `py -3.11`.
- **The rest checks out.** The install command, `--stage source` / `--stage package` / `all` (`run_ci.py:255-272`), `lint/run.py` and the `AGENT-LINT: PASS` line all match.

## Briefing claims checked

- **Known-red merge-base test.** Confirmed: `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` asserts `len(main_members) == 120` at merge-base, and main now has 148 members (AST count). A second part of the same test fails on any appended FailureCode, independent of merge-base and including CI. This matters for the request's new `browser.*` codes.
- **MCP stdio flake.** Located at `tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` (:360).
- **Grok compat leak.** Confirmed in code: `grok/threads.py:155-165` sets neither `GROK_*_MCPS_ENABLED` variable.
