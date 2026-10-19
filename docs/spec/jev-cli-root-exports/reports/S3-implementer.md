# S3 implementer report: jev-cli-root-exports (R1)

**Status: BLOCKED at Phase 5 step 3 (lint loop) and step 4 (full gate source stage).** Rows 1 and 3 are built, committed and verified (commits A and B). The full lint gate fails with `S062 REGRESSED: 892 finding(s), allowance 889.`. All three new S062 findings are in the S2 test files, none is in production code, and the regression first appears at S2's commit `5c3aa147`, before any S3 commit. Fixing it means editing S2 tests, which needs approval; raising the baseline is forbidden. Per the template, nothing was pushed, no PR was opened, and row 2 (commit C) is pending. A 3-line fix is proven on a scratch tree (below). Every other gate is green.

## Commits (`git log origin/main..HEAD --oneline`, S3's own on top)

```
c0f40bfd chore(contracts): regenerate the SDK public-API contract for the four agent setting exports [W-2; FR-5, FR-9, AC-4, AC-13]
f0527b55 feat(exports): root-export AgentLoopSettings, PermissionPolicy, TextModelMode and JevDynamicComputeOption [W-1, W-3; FR-1..FR-4, FR-6, FR-8, AC-1..AC-3, AC-7, AC-8, AC-10, AC-11]
2c7958f1 docs(spec): record jev-cli-root-exports S2 done and S3 start
… (S0 to S2 docs and test commits, unchanged)
```

Commit A = `f0527b551140366bb145316bfe31c47bc2837e67` (row 1). Commit B = `c0f40bfd` (row 3). Not pushed.

## What exists now, in data-flow order

1. `vidbyte/__init__.py`: `from vidbyte.agents import (… AgentInput, AgentLoopSettings, AgentMessage, …)`; `from vidbyte.lib.dataclasses.security import PermissionPolicy` between the `prosecutor_defender_judge` block and `skills`; `JevDynamicComputeOption` and `TextModelMode` in the `from vidbyte.lib.enums import (…)` block. These are eager bindings of the defining objects (D-1, D-2, D-3).
2. `vidbyte/__init__.py` `__all__` (one literal list): `"JevDynamicComputeOption"` after `"JevComputeSettings"`; `"AgentLoopSettings"`, `"TextModelMode"` after `"AgentStopReason"`; `"PermissionPolicy"` after `"ToolPermission"` (D-4).
3. `vidbyte/__init__.py` header: the spec's verbatim `- Agent setting exports: …` bullet, directly after `- Agent exports:` (D-5). I checked its factual claim: `BaseAgent.__init__` takes `permission_policy: PermissionPolicy | None`, `agent_loop_settings: AgentLoopSettings | None` and `model_mode: TextModelMode`.
4. `contracts/sdk-public-api.json`: written by the generator at commit A. It has 668 exports at 0.4.0 and `source.commit` = commit A.

## §12.3 rows

- [x] Row 1, `vidbyte/__init__.py`: commit A `f0527b55`, +9/−0 (`git diff --numstat $MB HEAD -- vidbyte/__init__.py` → `9	0`).
- [x] Row 3, `contracts/sdk-public-api.json`: commit B `c0f40bfd`. Generator output: `wrote contracts/sdk-public-api.json at f0527b551140366bb145316bfe31c47bc2837e67 (vidbyte-sdk 0.4.0, 668 exports)`. The diff is exactly 4 export lines at the spec's predicted neighbours (`AgentInput`, `JevDoneResult`, `ParentPolicy`, `TextContextItem`) plus `source.commit`. It is LF-only (`CR bytes: 0`, `i/lf w/lf attr/text eol=lf`).
- [ ] Row 2, `docs/design/release-0-4-0.md`: **pending (needs the PR number)**. It is blocked behind the push, which is blocked behind S062. I confirmed that the three spec sentences (a), (b) anchor and (c) exist verbatim in the file. No placeholder was written anywhere.

## §12.4 obligations

- [x] Each name is imported once and listed once (`{'AgentLoopSettings': 1, 'JevDynamicComputeOption': 1, 'PermissionPolicy': 1, 'TextModelMode': 1}`). S015 = 13, and its 4 root findings are exactly NG-3's `ContinualTraceAgentDescriptor`, `FunctionTool`, `HandoffAgentDescriptor`, `ToolMixin`.
- [x] ruff I001 over the whole `vidbyte` tree prints 0 lines for `vidbyte\__init__.py`. S051 = 259 (`S051 RATCHETED: 259 known finding(s)`).
- [x] `__all__` is still one literal list. INV-3 probe: `head minus the four == base, same order: True`, `removed []`.
- [x] `PermissionPolicy` comes from `vidbyte.lib.dataclasses.security`, and no definition moved.
- [x] `vidbyte/lib/enums/__init__.py` is not edited.
- [x] The header line starts with `    - `, is one line, and sits after `- Agent exports:`. `- Error exports:` is intact.
- [x] The legacy header format is kept, and A001 = 642.
- [x] The contract was written only by the generator, after commit A. Commit B holds only that file. C016 is CLEAN, and `--check` exits 0.
- [ ] Commit C: pending (row 2).
- [x] Nothing changed under `vidbyte/tools/**`, `vidbyte/lib/configs/**`, any defining module or any sub-package `__init__.py`. AC-6 (2) printed nothing.
- [x] No version literal changed. AC-9 printed nothing, and the root diff has 0 `__version__` lines.
- [x] Under `docs/` I read only the named spec files and `docs/design/release-0-4-0.md`, and edited nothing there.
- [x] No tracked bytecode: `PYTHONDONTWRITEBYTECODE=1` throughout, and `git status --short` is empty after the gates.
- [x] Gates ran from the worktree root, with `PYTHONPATH=$(pwd)` inline for source-side commands and `env -u PYTHONPATH` for the package stage.
- [ ] **The S2 test files are not lint-clean: S062 (see BLOCKED).** A001 and S020 are fine.
- [x] Commit messages cite IDs and carry the Co-Authored-By line.
- N/A: narration, `@intent`, dataclasses and error packets. No function, rule, record or raise was written.

## §12.5 non-code actions

- Release-record entry: pending (row 2).
- Contract regeneration: done (row 3).
- README, llms.txt, REPO_MAP and `artifacts/file_index.md`: no action, per the spec.
- `contracts/README.md` Change Log: no entry, per the spec.
- Lint ratchet: none. The seven IMPROVED rules (A002 S001 S009 S010 S025 S061 S063) are the same seven the spec lists from earlier PRs, and `lint/baseline.json` is untouched.
- PR body follow-ups: for S6.

## Deviations

None in the code; row 1 is the spec text verbatim. Two facts differ from what the spec and briefing state:
- `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` now fails with **`assert 171 == 120`**, not `167 == 120`. It reads `failure.py` at the merge base, and `b7350ed6` has 171 `FailureCode` members. The field guide's 167 was measured on the older `6f5a7310`. It is the same inherited test, failing for the same reason.
- request.md §C says the PR "is therefore created as a normal (non-draft-blocking) PR", while the S3 template and briefing say draft `[WIP]`. This was not reached; when resumed, I will follow the template (draft) and S6 promotes it.

## Files outside §12.3

None. Only `vidbyte/__init__.py` and `contracts/sdk-public-api.json` differ from `$MB` outside the spec folder and the S2 pack. This report is the only new file.

## Budget

Files changed: 2 of 3 so far (the third is row 2). New files, classes, dependencies and config keys: 0. Root names added: 4 of 4.

## Gate results (final lines, quoted)

`$MB = b7350ed6423642c9c178361eef87f3d9cda5589b`. `origin/main` = `0cce5781`. The drift check over every §12.3 and §11 path, plus the contract machinery, lint baseline and version files (`git diff --stat b7350ed6..origin/main -- …`), printed nothing. main was not merged; it is optional per §12.6 P4.

1. **New tests** (`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports`):
   - After commit A: `FAILED …::test_public_api_contract_lists_the_four_names_at_the_package_version` / `1 failed, 20 passed in 3.51s`. This is red by design until B.
   - After commit B: `21 passed in 3.29s`.
2. **Contract**: `contracts/sdk-public-api.json is current at f0527b551140366bb145316bfe31c47bc2837e67 (vidbyte-sdk 0.4.0, 668 exports).` (exit 0). `lint/run.py --rule C016` → `C016   public-api-contract-current                 0      0 CLEAN` / `SDK-LINT: PASS`.
3. **Lint loop**, through `run_ci.py --stage source` (log `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3-source-stage.log`):
   ```
   A001   agent-readable-file-headers               642    642 RATCHETED
   C016   public-api-contract-current                 0      0 CLEAN
   S015   public-export-integrity                    13     13 RATCHETED
   S051   modernized-import-and-syntax-hygiene      259    259 RATCHETED
   S062   no-implicit-string-concatenation          892    889 REGRESSED
   SDK-LINT: FAIL
   CI failed: Command failed with exit code 1: …python.exe …\lint\run.py
   ```
   S062 is the only REGRESSED or ERRORED rule.
4. **The rest of the source stage**, run step by step with the same commands as `run_source` because the lint step stopped it (log `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3-source-rest.log`). `compileall -q vidbyte` gave exit=0, and so did `check_context_write_paths.py`, `check_context_primitive_introductions.py` and `check_reasoning_trace_contracts.py`. pytest (`-p no:cacheprovider -rf` added for the log; the selection is unchanged):
   ```
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded
   FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_every_native_export_is_listed_in_the_root_all
   FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_each_root_name_is_the_native_object_itself
   FAILED tests/features/root_native_thread_exports/test_root_native_thread_exports_contract.py::test_the_public_api_contract_lists_every_root_native_name_at_the_package_version
   5 failed, 6735 passed, 17 skipped in 227.19s (0:03:47)
   ```
   These are exactly NFR-2's five. The baseline's 6715 passed, plus the 21 new tests, minus the local-only test that moved to failed, gives 6735.
5. **Package stage** (`env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 py -3.11 scripts/run_ci.py --stage package`; log `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3-package-stage.log`): `Successfully built vidbyte_sdk-0.4.0.tar.gz and vidbyte_sdk-0.4.0-py3-none-any.whl`. twine check PASSED for both. Tail:
   ```
   No broken requirements found.
   Installed vidbyte-sdk 0.4.0 passed smoke checks.
   CI passed.
   package stage exit=0
   ```
6. **Ruff I001** (`py -3.11 -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache`): 0 lines for `vidbyte\__init__.py`. Tree total `Found 223 errors.`, the pre-existing S051 surface.
7. **Semgrep**: the global install breaks on import (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This is mcp 2.x …`), which is the known tooling issue. I ran the pinned `semgrep==1.170.1` from a throwaway scratch venv with `mcp<2` (1.23.3) first on `PATH`; nothing global or in the repo changed. `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` → `Ran 1 rule on 1018 files: 0 findings.` / `semgrep exit=0`. The tree was clean and fully tracked.

## Inherited reds, proven on a pristine merge-base worktree

The control worktree was `git worktree add --detach …/vidbyte-sdk-jev-cli-root-exports-mb-control b7350ed6`. Its merge base was `b7350ed6`. It was removed afterwards and pruned.
- `PYTHONPATH=<control> py -3.11 -m pytest -q tests/features/root_native_thread_exports <failure-codes test> <import test>` → the 3 `root_native_thread_exports` tests plus the failure-codes test FAILED, with `4 failed, 5 passed`. The failure-codes assertion is `E       AssertionError: assert 171 == 120`.
- `test_import_vidbyte_starts_no_process…`: on pristine `b7350ed6` it is `1 passed`. A one-line control edit (an added `"PermissionPolicy",` after `"ToolPermission",` in root `__all__`, never committed) turns it red the same way it is red here: `E             At index 611 diff: 'PermissionPolicy' != 'ToolRegistry'` / `1 failed`. The control tree was then restored (0 changes).
- S062 bisect: `c2b14e04` (before S2's tests) → `S062 RATCHETED: 889`. `5c3aa147`/`dc5108e6` and `2c7958f1` → `S062 REGRESSED: 892 finding(s), allowance 889.` On pristine `b7350ed6` it is `889` with `SDK-LINT: PASS`.

## One-time proofs (for the §6.2 "Proven once" cells; paste on resume)

- **AC-5** (right after commit A): `contracts/sdk-public-api.json is stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode` / `Run: python scripts/generate-sdk-public-api.py (after committing the source change).` (exit 1, no `exports removed` line). `git diff --numstat $MB HEAD -- vidbyte/__init__.py` → `9	0`. No changed line mentions `__version__`, `__getattr__`, `__dir__` or `_LAZY`.
- **AC-6** at `c0f40bfd`: `git diff --name-only $MB HEAD` lists `contracts/sdk-public-api.json`, `vidbyte/__init__.py`, the 5 S2 pack files and `docs/spec/jev-cli-root-exports/**` only. The protected-path diff printed nothing.
- **AC-9** at `c0f40bfd`: the version-file diff printed nothing, and the root diff has `0` `__version__` lines. The contract's `"version": "0.4.0"` appears only as unchanged context.
- **AC-12**: **FAIL** (S062, above). ruff I001 is clean on the root. C016 0, S015 13, A001 642, S051 259 all hold.
- **AC-13** at `c0f40bfd`:
  - `… is current at f0527b551140366bb145316bfe31c47bc2837e67 (vidbyte-sdk 0.4.0, 668 exports).` (exit 0).
  - `git merge-base --is-ancestor f0527b55 HEAD` exits 0.
  - `git show f0527b55:vidbyte/__init__.py` lists the four at `:830`, `:1060`, `:1061` and `:1382`.
- **AC-14** (`git archive $MB vidbyte pyproject.toml` in the scratchpad against the head, fresh `py -3.11` each; probe `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3_module_probe.py`): both trees give `count 948` and `sha256 ff657e9052f220c075abe1c9868b70abb44e3f8a7de82c87ed1e3866d38315a1`, with `native_loaded False`. `four_eager` is False at `$MB` and True at the head.
- **AC-15**: pending (row 2).

## BLOCKED

- **BLOCKED AT:** Phase 5 step 3/4. `lint/run.py` (and therefore `run_ci.py --stage source`) ends `SDK-LINT: FAIL` with `S062 REGRESSED: 892 finding(s), allowance 889.`
- **DONE SO FAR:**
  - Rows 1 and 3 are committed as commits A `f0527b55` and B `c0f40bfd`.
  - The pack is green: `21 passed`.
  - Every other gate is green: C016, S015, S051, I001, compileall, the three check scripts, pytest with exactly the 5 named inherited reds, the package stage, and semgrep.
  - The one-time proofs AC-5, 6, 9, 13 and 14 are captured.
  - No in-progress work, nothing pushed, no PR. The worktree is clean except this report.
- **QUESTION:** May the three S062 findings in the S2 pack be fixed by merging each pair of adjacent string literals into one literal, either as an S2 amendment or as an S3 `test(exports)` commit, given that S3 may not modify S2 tests?
- **The findings** (`lint/run.py --rule S062 --all --format json`, filtered):
  - `tests/features/jev_cli_root_exports/test_jev_cli_root_exports_contract.py:95` (`f"vidbyte.{name} must be {module_path}.{name} itself; bind it in "` + next line).
  - `…_contract.py:167` (`"commit vidbyte/__init__.py, then run "` + next line).
  - `…_import_time.py:93` (`"bind the four with ordinary imports in vidbyte/__init__.py, "` + next line).
- **OPTIONS:**
  1. The orchestrator (or an S2 re-run) applies the proven patch as a test commit, moves the test-tree baseline from `dc5108e6` to it, and resumes S3 at Phase 6. Consequence: the gate goes green, and the assertion logic and message text are unchanged.
  2. The orchestrator authorizes S3 to apply the same patch as `test(exports): merge adjacent literals in jev_cli_root_exports messages [S062; INV-14, AC-12]`. Consequence: the same result in one step. The test-tree diff against `dc5108e6` will show exactly these 3 hunks.
  3. Push as is and fix it in S5. Consequence: this breaks "do not push while a required gate fails", the reviewers see AC-12 red, and dispatched CI fails at lint.
  4. Raise the S062 baseline to 892. Consequence: forbidden, and it would ship the regression to main.
- **RECOMMENDATION:** Option 1 or 2. The orchestrator picks based on how it governs the test tree. The patch is proven.
- **The proven patch:** `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/r1-s062-test-fix.diff`. The applier script is `…/scratchpad/s3_s062_patch.py`. On a scratch checkout of `c0f40bfd` it gives:
  - `S062 RATCHETED: 889`;
  - full `lint/run.py` → `SDK-LINT: PASS` (exit 0);
  - `A001 RATCHETED: 642`;
  - `ruff format --check` → `5 files already formatted`;
  - `ruff check` (default config and `lint/ruff.toml`) → `All checks passed!`;
  - pack → `21 passed in 5.36s`.
- **EVIDENCE:** spec INV-14 and AC-12 require `SDK-LINT: PASS` with no rule gaining a finding. The template's hard rules say "Ask first: modifying any test file … written by S2" and "Never: … raise a lint baseline". Phase 5 says "Do not push while any required local gate fails". The S062 bisect is above.

## Resume plan (after the S062 fix lands)

1. Re-run `lint/run.py` (expect `SDK-LINT: PASS`) and the pack. Re-run the full source stage, since the head changed.
2. Push, then open the draft PR with the template's title and body file.
3. Read the number with `gh pr view … --json number -q .number` and apply row 2 (a), (b) and (c) with it as commit C.
4. Run `--check`, expecting `current at f0527b55` (neither a test commit nor commit C touches a generator input), and the AC-15 diff. Push.
5. Make the spec `pr:`/`status: implemented` commit, then the Proof cells (from the section above) and the §17 row. Push.

## Tricky parts (where reviewers should look first)

- **Eager versus lazy.** All four names are in `vars(vidbyte)` right after import (eager probe green, AC-14 `four_eager True`), and the module set is byte-identical to `$MB` (948, same hash). The binding adds no import work because every defining module was already loaded.
- **Provenance.** `source.commit` is commit A, the generator's stamp, never hand-edited. Any later test-only or docs-only commit leaves it correct, because the generator's inputs are only `pyproject.toml` and `vidbyte/__init__.py`.
- **CRLF.** The worktree checks files out CRLF (`core.autocrlf=true`, index LF). The edit kept every line CRLF (`bare_lf 0`), the index stays LF, and the contract is LF-only by `.gitattributes`.
- **S062 was missed by S2's lint pass**, which ran only A001 and S020 (test-plan "Lint on the new files"). The full `lint/run.py` catches it.
