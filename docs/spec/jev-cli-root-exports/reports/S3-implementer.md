# S3 implementer report: jev-cli-root-exports (R1)

**Status: DONE.** Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/1190 (#1190). All three §12.3 rows are built.

1. Round 1 stopped BLOCKED on S062 in the S2 pack. The orchestrator chose option 1, and S2 applied my proven patch unchanged as `09b4ef23`. The test baseline is now `09b4ef23`.
2. While resuming, `main` moved twice with new root exports: #1189 and then #1159. Per spec EC-7 and A-4, I merged `main` each time, never rebasing. I committed each merge with main's contract and then regenerated it in a new commit.
3. The full gate is green on `e332e43c` apart from the two named inherited reds.
4. Commit C cites #1190 and recomputes its counts from the committed contracts.

## Commits (this stage, oldest first)

```
f0527b55 feat(exports): root-export AgentLoopSettings, PermissionPolicy, TextModelMode and JevDynamicComputeOption [W-1, W-3; …]   commit A (row 1)
c0f40bfd chore(contracts): regenerate the SDK public-API contract for the four agent setting exports [W-2; …]                        commit B (row 3)
05062e73 docs(spec): add jev-cli-root-exports S3 implementer report (blocked on S062 in the S2 pack)
  (09b4ef23 test(exports): S062 fix, by S2;  53b58409 docs(spec): adjudication, by the orchestrator)
4c2fae0f Merge origin/main (b21fd94e, #1189 browser root exports) [EC-7, A-4]
1c4452fc chore(contracts): regenerate the SDK public-API contract after merging main [W-2; …, EC-7]
76c61ffb Merge origin/main (181f1992, #1159 InfiniteMemoryAgent run events) [EC-7, A-4]
e332e43c chore(contracts): regenerate the SDK public-API contract after merging main again [W-2; …, EC-7]
29cac984 docs(release): record the four agent setting root exports in the 0.4.0 release note (#1190) [W-3; FR-7, AC-15, INV-17]   commit C (row 2)
b37f5101 docs(spec): record draft PR and implementation proof for jev-cli-root-exports
```

## What exists, in data-flow order

1. `vidbyte/__init__.py` binds the four eagerly, from modules `import vidbyte` already loads:
   - `AgentLoopSettings` in the `from vidbyte.agents import (…)` block, between `AgentInput` and `AgentMessage`.
   - `from vidbyte.lib.dataclasses.security import PermissionPolicy`, between the `prosecutor_defender_judge` block and `skills`.
   - `JevDynamicComputeOption` and `TextModelMode` in the `vidbyte.lib.enums` block.
2. The single literal `__all__` lists each name once, beside its sibling (D-4).
3. The header gets the spec's verbatim `- Agent setting exports:` bullet after `- Agent exports:` (D-5). Its claim that `BaseAgent` takes the three types is verified: `permission_policy`, `agent_loop_settings` and `model_mode`.
4. `contracts/sdk-public-api.json` is generator output: 682 exports at 0.4.0, with `source.commit` = `76c61ffb`.
5. `docs/design/release-0-4-0.md` carries the three row 2 edits, citing #1190.

Against `main` (`181f1992`), `vidbyte/__init__.py` differs by exactly the 9 added lines of row 1 (`9	0`). The contract differs by the 4 names plus `source.commit`, and the release note by 3 lines.

## §12.3 rows

- [x] Row 1 `vidbyte/__init__.py`: commit A `f0527b55`.
- [x] Row 3 `contracts/sdk-public-api.json`: commit B `c0f40bfd`, regenerated after each main merge (`1c4452fc`, `e332e43c`). No version of it was hand-edited or hand-merged.
- [x] Row 2 `docs/design/release-0-4-0.md`: commit C `29cac984`, made right after `gh pr create` with the number from `gh pr view … --json number -q .number` → `1190`.

## §12.4 obligations

- [x] Each name is imported once and listed once. S015 = 13; its 4 root findings are exactly NG-3's names.
- [x] ruff I001 over `vidbyte` prints 0 `vidbyte\__init__.py` lines. S051 = 259.
- [x] `__all__` is one literal list. At `$MB` `181f1992`: `head minus the four == base, same order: True`, `removed []`, 678 → 682.
- [x] `PermissionPolicy` is imported from `vidbyte.lib.dataclasses.security`. No definition moved, and `vidbyte/lib/enums/__init__.py` is untouched.
- [x] The header bullet is one line, starts with `    - `, and is identical to commit A's text after the conflict resolution. `- Error exports:` is intact, and A001 = 642.
- [x] The contract is generator-only, LF (`CR bytes: 0`). C016 is CLEAN, and `--check` exits 0 at the head.
- [x] Commit C contains only the release note, with the real number in both places and 0 placeholders. It changes no generator input: `--check` reports `current at 76c61ffb` before and after it.
- [x] Nothing changed under `vidbyte/tools/**`, `vidbyte/lib/configs/**`, any defining module or any sub-package `__init__.py` (AC-6 (2) empty). No version literal changed (AC-9 empty).
- [x] Under `docs/` I read and edited only the named release note and this spec folder.
- [x] No tracked bytecode, and the tree is clean after the gates. Source-side commands used inline `PYTHONPATH=$(pwd)`, and the package stage used `env -u PYTHONPATH`.
- [x] Commit messages cite IDs and carry the Co-Authored-By line.
- N/A: narration, `@intent`, dataclasses and error packets. No function, rule, record or raise was written.

## §12.5

- Release record: done (row 2). Contract regeneration: done.
- README, llms.txt, REPO_MAP, `contracts/README.md` Change Log and lint ratchet: no action, per the spec. The seven IMPROVED rules (A002 S001 S009 S010 S025 S061 S063) are unchanged and come from earlier PRs, and `lint/baseline.json` is untouched.
- The PR body follow-ups are for S6. The Q-1 follow-up is moot now, because main's #1189 root-exported the 11 browser names.

## Deviations (also under spec §17)

1. **Main merged twice (EC-7; A-4 was wrong).** #1189 (`b21fd94e`, the 11 browser names) and #1159 (`181f1992`, `InfiniteEvent`, `InfiniteEventKind`, `InfiniteHandoff`) both landed root exports during S3.
   - First merge: only the contract's `source.commit` line conflicted, and `vidbyte/__init__.py` auto-merged.
   - Second merge: #1159 rewrote the `- Agent exports:` header line directly above my bullet. I resolved it with a checked script, keeping main's line and then my bullet; the bullet is byte-identical to commit A's.
   - Each time, the merge commit took main's generator-written contract, and the generator then wrote the merged one in its own commit.
   - Result: 682 exports, not 668, with `source.commit` = `76c61ffb`, not commit A (INV-15 allows this when the derived data changes).
2. **Row 2 (c) recomputed.** The committed contracts give `v0.3.0 639 HEAD 682 added 43 removed 0`, `#1189 added 11`, `#1159 added 3`, and 3+4+17+11+3+4+1 = 43. The sentence therefore reads "682 exports … 43 added … 3 from #1099, 4 from #1084, 17 from #1179, 11 from #1189, 3 from #1159, 4 from #1190, and `SystemPromptPreset` from #1095". Rows (a) and (b) are the spec text verbatim.
3. **NFR-2: 2 inherited reds, not 5.** #1189 fixed the NG-1 trio.
4. **The failure-code test reads `assert 171 == 120`**, not 167: `failure.py` at the merge base has 171 members.
5. **The S062 adjudication** (round 1): option 1, S2 commit `09b4ef23`, hunk-for-hunk my patch `r1-s062-test-fix.diff`.
6. **AC-14's numbers on main moved** to 950 modules and `bcad6b19…` after #1159. The module set is still identical between `$MB` and the head.

## Files outside §12.3

None. Outside the spec folder, the diff against `main` contains only `vidbyte/__init__.py`, `contracts/sdk-public-api.json`, `docs/design/release-0-4-0.md` and the 5 S2 pack files. The test tree equals `origin/main` plus the S2 pack, and the pack equals `09b4ef23`. The 12 test files that differ from `09b4ef23` are all byte-identical to `origin/main`; they came in with #1184, #1188 and #1189, and the check found 0 that are not main's.

## Budget

- Files changed by the implementer: 3 of 3.
- New files, classes, dependencies and config keys: 0.
- Root names added: 4 of 4.

## Final gate results, head `e332e43c` (commit C and the spec commit change only docs)

- **New pack**: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(pwd) py -3.11 -m pytest -q -p no:cacheprovider tests/features/jev_cli_root_exports` → `21 passed` (3.39s at `53b58409`; area suites at `e332e43c`: `519 passed in 10.91s`).
- **Source stage**: `PYTHONIOENCODING=utf-8 PYTHONPATH=$(pwd) py -3.11 scripts/run_ci.py --stage source` (log `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/7cce0f21-8bce-4370-a202-c24813fdc8ab/scratchpad/s3-source-stage-4.log`):
  ```
  C016   public-api-contract-current                 0      0 CLEAN
  S015   public-export-integrity                    13     13 RATCHETED
  A001   agent-readable-file-headers               642    642 RATCHETED
  S051   modernized-import-and-syntax-hygiene      259    259 RATCHETED
  S062   no-implicit-string-concatenation          889    889 RATCHETED
  SDK-LINT: PASS
  FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
  FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded
  =========== 2 failed, 6958 passed, 17 skipped in 225.47s (0:03:45) ============
  ```
  - No rule is REGRESSED or ERRORED.
  - compileall and the three check scripts ran inside the stage before pytest.
  - The stage exits 1 only because of the two inherited reds.
  - `lint/run.py` again at `29cac984` → `SDK-LINT: PASS`.
- **Package stage**: `env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 py -3.11 scripts/run_ci.py --stage package` (log `…/scratchpad/s3-package-stage-3.log`): `Successfully built vidbyte_sdk-0.4.0.tar.gz and vidbyte_sdk-0.4.0-py3-none-any.whl`, twine check PASSED for both, then:
  ```
  No broken requirements found.
  Installed vidbyte-sdk 0.4.0 passed smoke checks.
  CI passed.
  package stage exit=0
  ```
- **Semgrep**: the global install breaks on mcp 2.x (`No module named 'mcp.server.fastmcp'`), so I used a scratch venv with `semgrep==1.170.1` and `mcp<2` on `PATH`. `semgrep scan --error --metrics=off --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` at `e332e43c` → `Ran 1 rule on 1020 files: 0 findings.` / `semgrep exit=0`.
- **Ruff I001**: 0 `vidbyte\__init__.py` lines. The tree-wide `Found 223 errors.` is the pre-existing S051 surface.
- **Contract**: `contracts/sdk-public-api.json is current at 76c61ffbd61632af5c96e472e00208a87109abaf (vidbyte-sdk 0.4.0, 682 exports).`

The coordinator expected the earlier package and semgrep results to stand, but both merges brought new source, so I reran both on `e332e43c` (results above).

## Inherited reds, proven on a pristine `$MB` = `181f1992` worktree (removed afterwards)

- `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` → `E       AssertionError: assert 171 == 120` / `1 failed, 1 passed`. It is red on main itself, and CI's shallow clone skips it.
- `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` passes on pristine main.
  - A one-line control edit (an added `"PermissionPolicy",` in root `__all__`) turns it red the same way: `E             At index 625 diff: 'PermissionPolicy' != 'ToolRegistry'` / `1 failed`.
  - Here it reads `At index 65 diff: 'JevDynamicComputeOption' != 'JevContinualSettings'`.
  - It is red by design on any branch that adds a root export, and CI skips it.
- The same two were also proven at `b7350ed6` and `b21fd94e`. The NG-1 trio failed at `b7350ed6` and passes from `b21fd94e` on.

## One-time proofs

These are pasted into spec §6.2 (AC-5, 6, 9, 12, 13, 14, 15). Highlights:
- AC-5: right after commit A, and again after each merge, `--check` printed `stale: exports added: AgentLoopSettings, JevDynamicComputeOption, PermissionPolicy, TextModelMode` with no removal.
- AC-13: `--check` current at `76c61ffb`; `76c61ffb` is an ancestor of HEAD; its `__all__` lists the four.
- AC-14: 950 vs 950 modules, the same hash, and native unloaded.

## Tricky parts (where reviewers should look first)

- **The contract's provenance across merges.** `source.commit` = `76c61ffb` (the second merge) is correct under the generator's rule: the merge changed the derived data, and the generator stamped the commit it read. Every committed version of the contract is verbatim generator output, either main's or mine. The intermediate merge commits deliberately hold main's contract, which is stale by our four names for one commit each.
- **The header conflict resolution** in `76c61ffb`. Check it with `git diff origin/main HEAD -- vidbyte/__init__.py`, which should show only the 9 added lines.
- **The release-note sentence** now names #1189 and #1159 to keep its arithmetic true. That goes slightly beyond row 2's literal text, under A-4. If `main` gains more root exports before the merge, the counts and the contract must be redone: merge, regenerate, recount.
- **CRLF.** The worktree is CRLF and the index LF (`core.autocrlf=true`); every edit kept consistent endings.
