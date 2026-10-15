# S0 merge report

Status: DONE (merge committed d8ef24f5, not pushed)

## Merge inputs

- Branch: `feat/claude-host` at `75e5ba89e10ba2379f6b36157291aa0f9963f547` (= origin/feat/claude-host before the merge).
- Merged ref: `origin/feat/native-grok-opencode-meta-hosts` at `5c08c35edcb1827e190ca4e2b2b1370808ef24be` (unchanged after `git fetch origin --quiet` on 2026-10-15). It is PR #1036's head.
- Merge base: `8387d66680951766f02b0d740d78eb6450cb6419`.
- Merge commit: `d8ef24f540efbd499bf857c04cc4df444e2bef41`. Parents: `75e5ba89`, `5c08c35e`. Message: `Merge remote-tracking branch 'origin/feat/native-grok-opencode-meta-hosts' into feat/claude-host` (git default).
- Command: `git merge --no-ff --no-commit origin/feat/native-grok-opencode-meta-hosts`, then resolve, `git add` of the four paths only, then `git -c core.editor=true commit --no-edit`. Not pushed.

Git reported exactly the four predicted conflicts. `pyproject.toml`, `vidbyte/lib/enums/failure.py`, `vidbyte/lib/errors/__init__.py` and `vidbyte/lib/errors/base.py` auto-merged. No other conflicts.

## Conflicts and resolutions

### 1. `vidbyte/harnesses/native/__init__.py` (add/add)

Resolution: `git checkout --theirs -- vidbyte/harnesses/native/__init__.py`. The file is now byte-identical to #1036's version (`git diff --quiet origin/feat/native-grok-opencode-meta-hosts -- <path>` returned 0).

- Dropped (#1044, ours): the 10-line package marker docstring ("Marks vidbyte/harnesses/native as the package of native coding-harness hosts ... this module imports nothing and names no harness."). It had no code.
- Kept (#1036, theirs): the docstring plus re-exports of the nine thread functions (`run_/continue_/fork_` × `grok`, `opencode`, `muse`), `GrokThreadConfig`, `MuseThreadConfig`, `NativeThreadResult`, `OpencodeThreadConfig`, `GrokPermissionMode`, `GrokReasoningEffort`, `MuseReasoningEffort`, `NativeThreadError`, and a literal 17-name `__all__`.
- Consequence: importing `vidbyte.harnesses.native` now imports the grok, muse and opencode subpackages. `vidbyte.harnesses.native.claude` still imports on its own (checked below).

### 2. `REPO_MAP.md` (content, 1 hunk)

The hunk sat under the shared heading `##### \`vidbyte/harnesses/native/\`` (both sides added the same heading; git merged it once). Both sides added one paragraph describing that same folder.

- Dropped (#1044, ours): "Hosts for the coding agents that vendors ship as their own executables, kept apart from the trajectory envelope above even though both use the word harness. Each coding harness gets its own host class, ... semantic error code ..." (the ClaudeHost description).
- Kept (#1036, theirs): "Module functions that run, continue and fork Grok Build, opencode and Muse Code threads by driving each vendor's installed command-line tool headless once per call with the caller's own API key, and return the thread id and the final answer. Each harness has its own subpackage with three functions, ..." (full paragraph, unedited).
- #1036's `vidbyte/lib/process/` entry auto-merged (no conflict) and is present.
- #1044 made no other change to this file (`git diff 8387d666 75e5ba89 -- REPO_MAP.md` = the heading + the one paragraph), so the resolved file is byte-identical to #1036's `REPO_MAP.md` (`git diff origin/feat/native-grok-opencode-meta-hosts -- REPO_MAP.md` empty).

### 3. `vidbyte/harnesses/README.md` (content, 1 hunk)

Both sides added one `native/` bullet to the module list after the `serialization.py` bullet.

- Dropped (#1044, ours): "- `native/`: hosts for native coding-harness executables, one subpackage per harness, each wrapping that harness's official SDK in small, atomic functions on a host class; unrelated to the `Harness` envelope above."
- Kept (#1036, theirs): "- `native/`: the harness thread functions, which run an installed vendor coding CLI headless once per call with the caller's API key: `run_grok_thread`, ... returns a `NativeThreadResult(harness, thread_id, text, text_truncated)` ..." (full bullet, unedited).
- #1044 made no other change to this file (1 line), so the resolved file is byte-identical to #1036's `vidbyte/harnesses/README.md`.

Both doc hunks were resolved with a script that keeps the theirs side of each hunk and leaves all text outside the hunks untouched (scratchpad `take_theirs_hunks.py`; CRLF line endings preserved).

### 4. `vidbyte/lib/enums/__init__.py` (content, 1 hunk)

The import lines auto-merged: `from vidbyte.lib.enums.claude import (... 17 names ...)` (from #1044) and `from vidbyte.lib.enums.native_threads import (... 15 names ...)` plus `from vidbyte.lib.enums.process import CliOptionStyle, ProcessLaunchFailure` (from #1036) are all present. The only conflict was in `__all__`, between `"CircularityVerdict",` and `"CodexApprovalMode",`:

- ours: the 17 `"Claude*"` names (`ClaudeBeta` … `ClaudeTurnStatus`); theirs: `"CliOptionStyle",`.
- Resolution (union, sorted as the file sorts, since "Cla" < "Cli"):

```python
    "CircularityVerdict",
    "ClaudeBeta",
    "ClaudeCliFlag",
    "ClaudeEffort",
    "ClaudeHookEvent",
    "ClaudeImageMediaType",
    "ClaudeMcpTransport",
    "ClaudeMemoryScope",
    "ClaudeMessageKind",
    "ClaudePermissionMode",
    "ClaudePermissionPrompts",
    "ClaudeRateLimitStatus",
    "ClaudeRateLimitType",
    "ClaudeSettingSource",
    "ClaudeSystemPromptMode",
    "ClaudeThinkingDisplay",
    "ClaudeThinkingMode",
    "ClaudeTurnStatus",
    "CliOptionStyle",
    "CodexApprovalMode",
```

- Mechanical check (scratchpad `check_enums_union.py`, AST-based): ours `__all__` 109, theirs 116, merged 133 (= exact set union; 92 shared). Imports 109 / 116 / 133, exact union. No duplicates. Imported names == `__all__` names. The Claude block sits in sorted order between `CircularityVerdict` and `CliOptionStyle`. (The file's older order is not strictly sorted elsewhere, e.g. `DocumentType` before `DecisionModelMode`; I did not touch that.)
- `python -m ruff check vidbyte/lib/enums/__init__.py vidbyte/harnesses/native/__init__.py --config lint/ruff.toml --select I001 --no-cache` → `All checks passed!`

## Verification

All commands from the worktree root, each with a timeout and `< /dev/null`. Test packs and lint ran on the committed merge (`d8ef24f5`). The order was chosen on purpose: #1036's git-based tests use `git merge-base origin/main HEAD`, which only reaches #1036's main (`77fef0e5`) once the merge commit exists. Before the commit it is the older base `8387d666`, so those tests would have measured the wrong thing.

1. Unmerged paths: `git ls-files -u` → empty (0 lines), before and after the commit.
2. Conflict markers: `git grep -n -E '^(<<<<<<<|>>>>>>>|=======)$' -- vidbyte REPO_MAP.md` → no output (rc=1).
   `git diff --check HEAD` (before the commit) → 0 conflict-marker findings. It listed two trailing-whitespace lines, both inherited unchanged from #1036's branch (the same two lines appear in `git diff --check 8387d666 origin/feat/native-grok-opencode-meta-hosts`):
   ```
   docs/spec/agent-output-connectors/spec.md:965: trailing whitespace.
   docs/spec/harness-thread-functions/request.md:50: trailing whitespace.
   ```
3. Imports: `PYTHONPATH=$(pwd) timeout 120 python -c "import vidbyte, vidbyte.harnesses.native, vidbyte.harnesses.native.claude, vidbyte.tools.builtins, vidbyte.tools.toolsets; from vidbyte.harnesses.native import run_grok_thread; import inspect; print(inspect.getfile(vidbyte))"`
   ```
   C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-claude-thread-functions\vidbyte\__init__.py
   rc=0
   ```
   Extra check: `vidbyte.lib.enums.__all__` has 133 names and every one resolves. `vidbyte.harnesses.native.claude.__file__` is inside this worktree.
4. Enums union: `python -X utf8 <scratchpad>/check_enums_union.py` (AST, compares HEAD, MERGE_HEAD and the working file)
   ```
   ours __all__: 109 theirs __all__: 116 merged __all__: 133
   ours imports: 109 theirs imports: 116 merged imports: 133
   Claude block + neighbours sorted: True CircularityVerdict ... CliOptionStyle
   OK: exact union, no duplicates, imports match __all__
   ```
5. Import order: `python -m ruff check vidbyte/lib/enums/__init__.py vidbyte/harnesses/native/__init__.py --config lint/ruff.toml --select I001 --no-cache` → `All checks passed!`
6. Commit: `git add REPO_MAP.md vidbyte/harnesses/README.md vidbyte/harnesses/native/__init__.py vidbyte/lib/enums/__init__.py`, then `git -c core.editor=true commit --no-edit`. Nothing under `docs/spec/claude-thread-functions/` was staged (checked: 0 cached paths there).
   ```
   [feat/claude-host d8ef24f5] Merge remote-tracking branch 'origin/feat/native-grok-opencode-meta-hosts' into feat/claude-host
   parents: 75e5ba89e10ba2379f6b36157291aa0f9963f547 5c08c35edcb1827e190ca4e2b2b1370808ef24be
   ```
7. #1036's pack: `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/harness_threads < /dev/null | tail -n 15`
   ```
   FAILED tests/features/harness_threads/test_harness_threads_static_policy.py::test_module_level_holds_only_docstring_imports_classes_all_and_init_bindings
   FAILED tests/features/harness_threads/test_harness_threads_static_policy.py::test_only_docstrings_all_entries_and_empty_zero_one_are_literals
   FAILED tests/features/harness_threads/test_harness_threads_static_policy.py::test_harness_modules_never_import_the_tools_layer
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
   5 failed, 431 passed, 2 skipped in 76.48s (0:01:16)
   ```
8. #1044's pack: `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/claude_host < /dev/null | tail -n 15`
   ```
   FAILED tests/features/claude_host/test_claude_host_contract.py::MarkerContractTests::test_marker_bytes_match_the_contract_in_lf_and_crlf_checkouts
   FAILED tests/features/claude_host/test_claude_host_contract.py::DocumentationInsertTests::test_harnesses_readme_ends_key_modules_with_the_native_bullet
   FAILED tests/features/claude_host/test_claude_host_contract.py::DocumentationInsertTests::test_repo_map_has_the_native_entry_between_harnesses_and_stores
   3 failed, 178 passed in 8.16s
   ```
9. Lint (PYTHONPATH unset): `timeout 900 python lint/run.py < /dev/null | tail -n 8`
   ```
   S062 RATCHETED: 889 known finding(s). Inspect with: python lint/run.py --rule S062 --all
   S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline
   S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all
   SDK-LINT: PASS
   ```
   Final line: `SDK-LINT: PASS` (rc=0). Status column: 47 CLEAN, 35 RATCHETED, 8 IMPROVED, 0 regressed. `lint/baseline.json` untouched.
10. Merge-content cross-check (independent of the tests):
    - `git diff --name-only 5c08c35e HEAD` (merge vs #1036) = 66 paths, all of them in #1044's own 69 changed paths (`git diff --name-only 8387d666 75e5ba89`). The 3 paths #1044 changed whose content now equals #1036's are exactly the policy-resolved ones: `REPO_MAP.md`, `vidbyte/harnesses/README.md`, `vidbyte/harnesses/native/__init__.py`.
    - `git diff --name-only 75e5ba89 HEAD` (merge vs #1044) = 343 paths, exactly #1036's 343 changed paths (`git diff --name-only 8387d666 5c08c35e`). Nothing else entered.
11. Push state: `git status -sb` → `## feat/claude-host...origin/feat/claude-host [ahead 281]`; origin/feat/claude-host is still `75e5ba89`. Not pushed. Working tree clean apart from untracked `docs/spec/claude-thread-functions/`.

## Failing tests

All 8 failures come from #1044's ClaudeHost code, tests and docs still being in the tree, or from the policy replacing #1044's marker and doc entries. None is a merge defect. Each was checked at the assertion level.

#1036's pack (`tests/features/harness_threads`), 5 failures:

1. `test_harness_threads_static_policy.py::test_module_level_holds_only_docstring_imports_classes_all_and_init_bindings`: INV-15 rule 1 scans every `.py` under `vidbyte/harnesses/native/`, which now includes #1044's `claude/` subpackage. Recount with the test's own helpers (scratchpad `static_policy_by_folder.py`): 13 offenders, all in `claude/` (failures.py, host.py, options.py, session.py); 0 in grok/opencode/muse/hostkit/root.
2. `test_harness_threads_static_policy.py::test_only_docstrings_all_entries_and_empty_zero_one_are_literals`: INV-15 rule 2, same scan. 266 literals, all 266 in `claude/` (the test prints only the first 60; the untruncated recount confirms it).
3. `test_harness_threads_static_policy.py::test_harness_modules_never_import_the_tools_layer`: INV-20. 3 imports of `vidbyte.tools.*`, all in `claude/tool_server.py` (lines 23–24: `vidbyte.tools.base`, `vidbyte.tools.catalog`, ...).
4. `test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`: #1044 inserted its 16 `CLAUDE_*` codes near the top of `FailureCode` (line 35, before `CODEX_SDK_UNAVAILABLE`), so main's first 120 members are no longer in main's order (`At index 10 diff: ('CLAUDE_SDK_UNAVAILABLE', ...) != ('CODEX_SDK_UNAVAILABLE', ...)`). The test's first two asserts passed: the 28 harness codes still follow `RULE_EVALUATION_FAILED` exactly. The `failure.py` auto-merge is correct; the cause is #1044's placement.
5. `test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`: `git diff --name-only $(git merge-base origin/main HEAD) -- vidbyte/tools vidbyte/lib/configs docs/spec/native-grok-opencode-meta-hosts` lists 10 paths. They match, byte for byte, #1044's own changes there (`vidbyte/tools/builtins/__init__.py`, `vidbyte/tools/builtins/claude/{__init__,_base,descriptions,history,readiness,sessions,turns}.py`, `vidbyte/tools/toolsets/__init__.py`, `vidbyte/tools/toolsets/claude.py`). #1036 itself changes 0 paths there.

#1044's pack (`tests/features/claude_host`), 3 failures (the expected marker-hash and doc-insert contract tests):

6. `test_claude_host_contract.py::MarkerContractTests::test_marker_bytes_match_the_contract_in_lf_and_crlf_checkouts`: pins the 10-line marker bytes of `vidbyte/harnesses/native/__init__.py`, which the policy replaced with #1036's re-export module (`'... PURPOSE: The package of harness thread functions ...' != '... PURPOSE: Marks vidbyte/harnesses/native as the pac...'`).
7. `test_claude_host_contract.py::DocumentationInsertTests::test_harnesses_readme_ends_key_modules_with_the_native_bullet`: pins #1044's `native/` bullet in `vidbyte/harnesses/README.md`; the bullet is now #1036's.
8. `test_claude_host_contract.py::DocumentationInsertTests::test_repo_map_has_the_native_entry_between_harnesses_and_stores`: pins #1044's `native/` paragraph in `REPO_MAP.md`; the paragraph is now #1036's.

All of these go away once a later stage deletes the ClaudeHost code (claude/, tools/builtins/claude, toolsets/claude.py, the `CLAUDE_*` failure codes and their `claude_host` tests) or moves the Claude codes to the tail of `FailureCode`.

## Notes for later stages

- `vidbyte.lib.enums.__init__` still exports the 17 Claude enums. Removing `vidbyte/lib/enums/claude.py` means removing that import block and those 17 `__all__` entries too.
- `vidbyte/lib/errors/{__init__,base}.py` and `pyproject.toml` auto-merged with #1044's additions intact: `ClaudeOperationError` (in `base.py`, exported from `errors/__init__.py`) and the `claude = ["claude-agent-sdk>=0.2.165,<0.3.0"]` optional extra. Later stages must delete or reshape them.
- `merge_base()` in #1036's surface tests now resolves to `77fef0e5` (#1036's main). The live `origin/main` is at `f216fdcf`, which is newer and not merged here.

## Second merge: origin/main into feat/claude-host

Status: DONE (merge committed 81833363, not pushed). This supersedes the last "Notes for later stages" bullet above: the branch is now grounded on current main.

### Inputs

- `git fetch origin --quiet` on 2026-10-15. origin/main = `72a4ade129d74bab45b4fc12764d951df6d1ec3b`, as the coordinator expected; it had not moved. That is #1027 ("agents take vidbyte_api_key and a list of api_keys ...") on top of `f216fdcf` (#1036 squash).
- `git diff 5c08c35e f216fdcf` is empty, so the squash tree equals the #1036 head merged in the first merge.
- Branch before: `d8ef24f5` (the first merge). Dry run `git merge-tree --write-tree --name-only HEAD origin/main` → exactly one conflict, `vidbyte/lib/enums/__init__.py`.
- Command: `git merge --no-ff --no-commit origin/main`. Auto-merged: `vidbyte/lib/enums/failure.py`, `vidbyte/lib/errors/__init__.py` and `vidbyte/lib/errors/base.py`; each result equals HEAD's version (#1027 does not touch them: `git diff --stat f216fdcf origin/main -- vidbyte/lib/enums/failure.py vidbyte/lib/errors contracts` is empty). `contracts/sdk-public-api.json` did not conflict and is not changed by the merge, so no regen commit was needed.
- Merge commit: `818333634dd94f34dd8e192f1f93e36e70a09067`. Parents: `d8ef24f5`, `72a4ade1`. Message: `Merge remote-tracking branch 'origin/main' into feat/claude-host` (default). Staged: only `vidbyte/lib/enums/__init__.py` plus git's own auto-merged paths (126 paths from #1027). 0 paths under `docs/spec/claude-thread-functions/`.

### Conflict: `vidbyte/lib/enums/__init__.py` (1 hunk, in `__all__`)

The new merge base is `77fef0e5`. From there both sides add #1036's names; main does it through the squash, the branch through the first merge. The branch also adds the 17 Claude names. The hunk sat between `"CircularityVerdict",` and `"CliOptionStyle",`. The ours side held the 17 `"Claude*"` names; the theirs side was empty, because main's `"CliOptionStyle",` was already in the shared context below the hunk. #1027 does not change this file (`git diff f216fdcf origin/main -- vidbyte/lib/enums/__init__.py` is empty).

Resolution (union): keep the 17 Claude names, drop the markers. The result is byte-identical to HEAD's file (`git diff --quiet HEAD -- vidbyte/lib/enums/__init__.py` → 0). The kept hunk is the same block shown in conflict 4 above (`"CircularityVerdict"`, 17 × `"Claude*"`, `"CliOptionStyle"`).

`check_enums_union.py`:
```
ours __all__: 133 theirs __all__: 116 merged __all__: 133
ours imports: 133 theirs imports: 116 merged imports: 133
Claude block + neighbours sorted: True CircularityVerdict ... CliOptionStyle
OK: exact union, no duplicates, imports match __all__
```
Ruff I001 on the file: `All checks passed!`

### Verification

1. `git ls-files -u` → 0 lines. `git grep -n -E '^(<<<<<<<|>>>>>>>|=======)$' -- vidbyte REPO_MAP.md` → no output (rc=1). `git diff --check HEAD` before the commit → no findings.
2. Import check (same command as before):
   ```
   C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-claude-thread-functions\vidbyte\__init__.py
   import_rc=0
   ```
3. `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/harness_threads < /dev/null | tail -n 15`
   ```
   FAILED tests/features/harness_threads/test_harness_threads_static_policy.py::test_module_level_holds_only_docstring_imports_classes_all_and_init_bindings
   FAILED tests/features/harness_threads/test_harness_threads_static_policy.py::test_only_docstrings_all_entries_and_empty_zero_one_are_literals
   FAILED tests/features/harness_threads/test_harness_threads_static_policy.py::test_harness_modules_never_import_the_tools_layer
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
   FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
   5 failed, 431 passed, 2 skipped in 66.16s (0:01:06)
   ```
4. Extra check: `PYTHONPATH=$(pwd) timeout 900 python -m pytest -q -p no:cacheprovider tests/features/claude_host` → `3 failed, 178 passed in 9.04s`. These are the same 3 marker and doc-insert tests as before.
5. Lint (PYTHONPATH unset): `timeout 900 python lint/run.py < /dev/null | tail -n 8`
   ```
   S062 RATCHETED: 889 known finding(s). Inspect with: python lint/run.py --rule S062 --all
   S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline
   S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all
   SDK-LINT: PASS
   ```
   rc=0. Status column: 47 CLEAN, 34 RATCHETED, 9 IMPROVED, 0 regressed.
6. `git diff --stat origin/main HEAD -- . ':!docs'` → `42 files changed, 10296 insertions(+)`. Including docs, the count is 66 paths (the 42, plus #1044's 24 `docs/spec/claude-host/` files).
   - Every one of the 42 is one of #1044's own 45 non-docs paths (`git diff --name-only 8387d666 75e5ba89 -- . ':!docs'`). The 3 missing are the first merge's policy-resolved files (`REPO_MAP.md`, `vidbyte/harnesses/README.md`, `vidbyte/harnesses/native/__init__.py`), which now equal main.
   - Line-level check: the +/- lines of `git diff origin/main HEAD -- <the 42>` and of `git diff 8387d666 75e5ba89 -- <the 42>` are identical (10,296 lines each). The 24 docs paths are exactly #1044's own docs set.
7. Push state: `## feat/claude-host...origin/feat/claude-host [ahead 284]`. origin/feat/claude-host is still `75e5ba89`. Not pushed.

### Failing tests after the second merge (category per the coordinator: a = already explained, b = new because main now holds #1036's 28 codes, c = merge defect)

1. `test_module_level_holds_only_docstring_imports_classes_all_and_init_bindings`: (a). A recount with the test's helpers finds 13 offenders, all in `claude/`.
2. `test_only_docstrings_all_entries_and_empty_zero_one_are_literals`: (a). 266 literals, all in `claude/`.
3. `test_harness_modules_never_import_the_tools_layer`: (a). 3 imports, all in `claude/tool_server.py`.
4. `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`: now (b), and (a) still applies behind it. It fails at `test_harness_threads_surface.py:193`, `assert 148 == 120`. The merge base is now `72a4ade1`, whose `FailureCode` already has 148 str members (120 + #1036's 28); `count_failure_codes.py` gives 77fef0e5 = 120, origin/main = 148, HEAD = 164. This assert fails on origin/main itself, independent of this branch. If the Claude codes were deleted, line 193 would still fail. Line 194 (main's order) would also fail while the 16 `CLAUDE_*` codes sit at indexes 10–25 (a). Line 195 expects 148 + 28 = 176 members, which can never hold now that main contains the 28. The test needs a spec-level change (main's count is now 148 and the 28 are already in main), not a code fix.
5. `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`: (a). The 10 changed paths under `vidbyte/tools` equal #1044's 10 tools files exactly.

No (c) failures. The 3 `claude_host` failures are unchanged (marker bytes, README bullet, REPO_MAP paragraph).
