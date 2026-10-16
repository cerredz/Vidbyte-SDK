# S3 implementer report: codex-host-thread-helpers

Stage: S3 implementer · Spec: `docs/spec/codex-host-thread-helpers/spec.md` r3, now `status: implemented` · Branch: `feat/codex-host`, started at `65ff889b` (origin was `66558ee9`) · PR: https://github.com/cerredz/Vidbyte-SDK/pull/1055 (still a draft; title and body untouched) · Date: 2026-10-16

## Outcome

- All 18 rows of §12.3 are implemented in phase order P1 to P5, with one commit per row and three small follow-ups.
- `CodexHost` gains the 12 functions of §8.5. `CodexHostTools` holds 26 tools, and `delete_codex_thread` has no tool.
- The S2 tests are green. The area suite (`tests/features/codex_host`, `tests/features/harness_threads`, `test_codex_output_contracts.py`, `test_session_failures.py`, `test_codex_failure_recovery.py`) ends `1 failed, 764 passed, 2 skipped`. The one failure is the inherited `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, which reads main's `failure.py` at the merge base (`assert 148 == 120`).
- Nothing under `tests/` changed: `git diff 33787d9a..HEAD --stat -- tests/` is empty.
- Exactly the 18 §12.3 files changed under `vidbyte/`, plus this spec folder.
- The GitHub `CI` run passed on `7980ebbb` (run 38892848824: Source 3.11, Source 3.12 and Package), and so did `Static policy` (run 38892851887).

## Commits

| # | SHA | Row | Message |
|---|---|---|---|
| 1 | `34a73836` | 1 | feat(enums): add the four codex helper failure codes [W-9; FR-15, AC-36] |
| 2 | `575467b2` | 2 | feat(enums): add CodexSkillScope and the twelve helper operations [W-8; FR-11, FR-14, INV-3] |
| 3 | `12b076d5` | 3 | feat(enums): export CodexSkillScope from vidbyte.lib.enums [W-8; FR-11] |
| 4 | `3aebb0a6` | 4 | feat(constants): add the thread-helper bounds, methods, classifications and next steps [W-8, W-9; FR-15, NFR-5, AC-36] |
| 5 | `96d6d484` | 5 | feat(dataclasses): add the five thread-helper records [W-8; FR-13, INV-15, AC-10] |
| 6 | `e221ab1e` | 6 | feat(codex): add CodexResultSerializer.items for stored turn items [W-11; FR-5, INV-17, INV-32] |
| 7 | `b65d0e0f` | 7 | feat(codex-host): register the four thread-helper raw responses [W-11; INV-19, INV-20, INV-23, INV-17] |
| 8 | `48a160a1` | 8 | feat(codex-host): translate the thread-helper params and answers [W-11; INV-11, INV-15, INV-17, INV-20, INV-23] |
| 9 | `8520600c` | 9 | feat(codex-host): add CodexThreadHelpers for listings, lineage, turns, compact and delete [W-1..W-6; FR-1..FR-8, AC-2..AC-23, AC-38] |
| 10 | `32edb6f2` | 10 | feat(codex-host): add CodexSkillFunctions for goal and skill runs [W-6, W-7; FR-9, FR-11, FR-12, AC-25..AC-32, AC-39..AC-43] |
| 11 | `b55ece4e` | 11 | feat(codex-host): add the twelve thread-helper and skill functions to CodexHost [W-1..W-7; FR-1..FR-12, FR-17, AC-1..AC-32] |
| 12 | `96b572d9` | 9 (fix) | fix(codex-host): let RecordFieldValidator own the listing limit check [W-1; FR-1, AC-9, INV-6] |
| 13 | `80e0f308` | 12 | feat(tools): add the model-facing texts of the eleven thread-helper tools [W-10; FR-14, NFR-7, AC-33] |
| 14 | `1ce73fcf` | 13 | feat(tools): add the _resolve_timestamp argument reader [W-10; FR-2, AC-33] |
| 15 | `f8496128` | 14 | feat(tools): add the six thread-helper tools [W-10; FR-14, AC-33, AC-41] |
| 16 | `94a2cc34` | 15 | feat(tools): add the five goal and skill tools [W-10; FR-14, AC-33, INV-27] |
| 17 | `bafd0264` | 16 | feat(tools): export the eleven thread-helper tools from builtins.codex [W-10; FR-14, AC-33] |
| 18 | `4de1ee99` | 17 | feat(tools): re-export the eleven thread-helper tools from builtins [W-10; FR-14, AC-33] |
| 19 | `864648d2` | 18 | feat(toolsets): append the eleven thread-helper tools to CodexHostTools [W-10; FR-14, INV-2, AC-33] |
| 20 | `7980ebbb` | 2, 6 (§12.5) | docs(codex): link the thread-helpers spec from the result and enum headers [W-8, W-11; FR-5, FR-11] |
| 21 | `e35a57c4` | — | docs(spec): record implementation for codex-host-thread-helpers (`status: implemented`) |
| 22 | `0533eafc` | — | docs(spec): record implementation proof for codex-host-thread-helpers (§6.2 note, §17 row, deviations) |
| 23 | `e46509e3` | 6 (§12.4) | style(codex): wrap the CodexResultSerializer.items comment to 72 columns [W-11; FR-5] |
| 24 | this commit | — | docs(spec): add the S3 implementer report |

## Rows ticked (§12.3)

All 18 rows are ticked.

- **P1 (rows 1 to 5).** Four `FailureCode`s between `CODEX_TURN_TIMED_OUT` and `INPUT_EMPTY`. `CodexSkillScope` plus 12 `CodexHostOperation` members, with the enum exported in sorted position. Sixteen host constants, five method constants, four classification rows and four exact next steps, appended to `__all__`. Five frozen, slotted records using the file's own validators.
- **P2 (rows 6 to 8).**
  - `CodexResultSerializer.items`.
  - Four `RAW_RESPONSES` rows.
  - Translators:
    - params: `thread_list(limit)`, `thread_params`, `turns_page` and `skills_list`;
    - answers: `summary`, `goal`, `skills` and `turn_page`.
- **P3 (rows 9 to 11).** `CodexThreadHelpers` (279 lines). `CodexSkillFunctions` plus the `CodexSkillHost` Protocol (251 lines; the module never imports `host.py`). Twelve guard-then-delegate host methods; `host.py` is 891 lines, within the 900 limit.
- **P4 (rows 12 to 18).** 22 description constants, each of 4 sentences. `_resolve_timestamp`. Six plus five tool classes (238 and 211 lines). Exports, and `CodexHostTools` now holds 26 tools in §9.2 order.

## Budget (§8.4)

- **New files: 4**, which is the budget. They are rows 9, 10, 14 and 15.
- **New classes: 20**, which is the budget:
  - `CodexThreadHelpers`: 1;
  - `CodexSkillFunctions` and `CodexSkillHost`: 2;
  - records: 5;
  - `CodexSkillScope`: 1;
  - tools: 11.
- **New error classes, dependencies, public contract changes outside §9.2 and lint baseline changes:** none.
- **`contracts/sdk-public-api.json`:** not regenerated.

## Files outside §12.3

None. `git diff --name-only 65ff889b..HEAD -- vidbyte` lists exactly the 18 row files. The only other changes are in this spec folder: the spec itself and this report.

## Deviations

These are also recorded in spec §17 ("Implementation deviations (S3)").

1. **The listing `limit` check now goes through a canonical owner.**
   - In P3, lint passed only because `git ls-files` did not yet list the new files.
   - Once they were tracked, C002 regressed from 9 to 11 findings: the inline `isinstance(limit, bool)` in `CodexThreadHelpers._reject_listing` duplicated `vidbyte/lib/dataclasses/coding.py:143`.
   - The fix (`96b572d9`) calls `RecordFieldValidator.require_int` and re-raises the exact `LIMIT_MESSAGE` `from None`. Behavior and text are unchanged, and the AC-9 tests pass.
2. **`since` and `query` are checked by operation.** `_reject_listing` checks `since` only for `list_codex_threads_since` and `query` only for `search_codex_threads`, because the recent and search wrappers legitimately pass `since=None` and `search=""`.
3. **The skill-argument helper is `_reject_skill_arguments`, not `..._request`.** This avoids A002's `request` token. Its order follows row 10: the own-input check, then the ephemeral check, then `SKILL_NAME_MESSAGE`.
4. **`CODEX_HOST_INPUT_CHECK_ATTEMPTS` keeps its spec name.** The briefing advised against `*_ATTEMPTS` names, but §12.4 forbids renaming it. S064 is satisfied by the in-loop `loop.time()` deadline comparison, and lint passes.
5. **The `CodexHostTools` class docstring is unchanged.** It still reads "Catalog of one agent tool per CodexHost function over one host."
   - It mirrors the pinned `toolsets/__init__.py:11` bullet, which the orchestrator kept.
   - The header and the narrated `__init__` comment now say that `delete_codex_thread` has no tool.
6. **Three follow-up commits** sit outside the one-commit-per-row shape:
   - `96b572d9` (C002).
   - `7980ebbb`: the §12.5 RELATED DOCS links for `result.py` and `enums/codex.py`.
   - `e46509e3`: a 75-column comment that row 6 added to `result.py`, now wrapped to 72 columns.

## Gate outputs (final lines, quoted)

- **Lint.** `$VPY lint/run.py` on final HEAD prints `SDK-LINT: PASS`.
- **ruff I001** on the 18 touched files prints `All checks passed!`. The first P4 run flagged the import order in `tools/builtins/codex/__init__.py`, which ruff's own sort fixed before the commit.
- **Comment width.** No comment line this branch added is longer than 72 columns. The check was awk over the `+` lines of `git diff 65ff889b -- vidbyte`. Over-wide comments that predate the branch remain in `result.py`, `constants/codex.py` and `failure.py`.
- **Public API.** `$VPY scripts/generate-sdk-public-api.py --check` prints `contracts/sdk-public-api.json is current at 998dc0da01d5f4519e76a3d92f08c4cd9d59d0df (vidbyte-sdk 0.3.0, 639 exports).`
- **Source stage.** `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source`:
  - Every step before pytest passed (bytecode check, `SDK-LINT: PASS`, compileall, and the three contract scripts).
  - pytest ended `============ 1 failed, 5952 passed, 25 skipped in 95.54s (0:01:35) ============`, then `CI failed: Command failed with exit code 1: ...python.exe -m pytest`.
  - The one failure is the inherited merge-base test.
- **Package stage.** `$VPY scripts/run_ci.py --stage package`, with no PYTHONPATH, ended:
  - `No broken requirements found.`
  - `Installed vidbyte-sdk 0.3.0 passed smoke checks.`
  - `CI passed.`
- **Semgrep 1.170.1** (in VPY):
  - `semgrep --test ...` prints `1/1: ✓ All tests passed`.
  - `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` exits 0 and prints `Ran 1 rule on 980 files: 0 findings.`
- **mypy** (`--follow-imports=silent`) on `host.py`, `skill_functions.py`, `thread_helpers.py` and `wire.py` prints `Success: no issues found in 4 source files`. This shows that `CodexSkillFunctions(self)` satisfies `CodexSkillHost`.
- **Area suite** on final code: `1 failed, 764 passed, 2 skipped in 52.03s`. The failure is the inherited test.
- **GitHub, on `7980ebbb`:**
  - `CI` run 38892848824 `completed success` (Source / Python 3.11, Source / Python 3.12, Package).
  - `Static policy` run 38892851887 `completed success`.
  - Both were re-dispatched on the final HEAD after this report was pushed.

## Tricky parts for the next agent

- **Lint sees only tracked files.** `lint/run.py` and semgrep discover files with `git ls-files`, so an untracked new module is invisible to every rule. Run `git add -N` on it, or commit it, before you trust `SDK-LINT: PASS`.
- **Installing semgrep changes VPY.** `pip install semgrep==1.170.1` rewrote about 40 packages in VPY at 07:14:58, `mcp` 1.23.3 among them.
  - Every gate above except semgrep ran before that install. The area suite was re-run afterwards and passed.
  - The bare `semgrep.exe` launcher finds `pysemgrep` through PATH, and the global Python's copy crashes on mcp 2.x. Put the venv's `Scripts` directory first on PATH before you run semgrep.
- **The run wrappers rely on the host's own guard.** `CodexSkillFunctions` calls the host's public methods, so every inner call also passes `_guard`, as D-2 intends.
- **`list_codex_skills` sits inline in `host.py`**, as row 11 says. It is the only new host method that does not delegate.

## Drift note

- `origin/feat/codex-host` was `66558ee9` at the start. Every push was a fast-forward.
- Against `origin/main` (merge base `72a4ade1`), the only §12.3 path that drifted is `vidbyte/lib/enums/__init__.py`. That change is a non-conflicting `SystemPromptPreset` hunk.
- Main was not merged, as instructed.
