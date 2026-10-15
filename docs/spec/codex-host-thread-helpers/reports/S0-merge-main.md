# S0 pre-step: merge origin/main into feat/codex-host

Status: **DONE**. The merge commit is `c181be65`. Its parents are 66558ee9f033f39be238d17c928f6630dd4e7fa4 and 72a4ade129d74bab45b4fc12764d951df6d1ec3b, and `git merge-base origin/main HEAD` is now 72a4ade1. All three gates are green except 1 inherited test that also fails on plain origin/main (see the end of this report). `git status --porcelain` shows only `?? docs/spec/codex-host-thread-helpers/`. Nothing is pushed.

## Final result (after the orchestrator approved Option A)

- I applied Option A: the patch `S0-proposed-test-fix.patch` (3 test files, +9/-7), with `git apply --index`, inside the merge resolution. Nothing else changed. Before the commit, `git diff --cached 7bc499c6 --stat` showed exactly those 3 files (+9/-7) against the simulated merge tree, and `git ls-files -u | wc -l` printed 0.
- The commit message is the briefing's message plus one body line before the trailer: "Test pins in codex_host packaging and two harness_threads branch-scope checks updated for the union (orchestrator-approved)."
- Option B (bringing `codex/` in line with #1036's INV-15 and INV-20) was not done. It goes to the spec author as an optional question.
- Final gates, run on the real merge commit c181be65 from the worktree root with VPY. `vidbyte` resolves to the worktree.
  - (a) `VPY -m pytest tests/features/codex_host tests/features/harness_threads -q`:
    ```
    tests\features\harness_threads\test_harness_threads_surface.py:193: AssertionError: assert 148 == 120
    FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
    1 failed, 551 passed, 2 skipped in 60.28s (0:01:00)
    ```
  - (b) `VPY lint/run.py`, run on the staged merge just before the commit: exit 0, no REGRESSED rule.
    ```
    S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

    S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

    SDK-LINT: PASS
    ```
    Gate (c) runs lint again on the commit, and it prints `SDK-LINT: PASS` there too.
  - (c) `VPY scripts/run_ci.py --stage source`: lint and the 4 check scripts pass. pytest:
    ```
    SDK-LINT: PASS
    FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
    =========== 1 failed, 5876 passed, 25 skipped in 112.73s (0:01:52) ============
    CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-codex-host-thread-helpers).
    ```
    The run exits with code 1 only because of that inherited test.

The rest of this report is the analysis from the blocked round, kept for the record.

## Why it was blocked (resolved by Option A)

The union resolution is clean: lint passes, and 5,869 tests pass. But 7 tests fail because of the merge itself, and each one can only be fixed by editing a test file. The briefing forbids test edits ("No edits to tests"). The 7 tests come in 3 groups:

1. **Pinned texts in the branch's own test** (`tests/features/codex_host/test_codex_host_packaging.py`, 3 tests). The test pins the exact SHA-256 of `vidbyte/harnesses/native/__init__.py`, which is the branch's 911-byte marker that exports nothing. It also pins the exact REPO_MAP `native/` section and the exact README `native/` bullet. Main's #1036 replaced that same file with a re-export module, and main's `test_harness_threads_surface.py::test_native_package_exports_exactly_the_nine_functions_and_their_records` requires `native.__all__` to equal 17 names. No single file can satisfy both tests. Any union of the REPO_MAP and README texts also changes the other two pinned texts.
   - `test_native_package_marker_has_the_fixed_bytes`
   - `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores`
   - `test_harnesses_readme_bullet_follows_the_serialization_bullet`
2. **#1036 static policy scans the whole `vidbyte/harnesses/native/` tree**, so it now also scans `codex/` (`tests/features/harness_threads/test_harness_threads_static_policy.py`, 3 tests). Its docstring says "Do not add allow-lists of files or literals".
   - `test_module_level_holds_only_docstring_imports_classes_all_and_init_bindings` (INV-15 rule 1). The codex modules have module-level constants, `if TYPE_CHECKING:` blocks, a TypeVar, and the 6 `async def` one-shot functions in `codex/oneshot.py`.
   - `test_only_docstrings_all_entries_and_empty_zero_one_are_literals` (INV-15 rule 2). It finds 165 string or number literals in `codex/*.py`.
   - `test_harness_modules_never_import_the_tools_layer` (INV-20). `codex/host.py` line 71 has `from vidbyte.tools.catalog import Tools`.
3. **A #1036 test that compares the branch with main** (`test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them`, 1 test). After the merge commit, the merge base becomes origin/main. The PR then differs from main in `vidbyte/tools`: it adds `builtins/codex/*` and `toolsets/codex.py`, and it changes `builtins/__init__.py` and `toolsets/__init__.py`. That breaks #1036's INV-21 ("no file of vidbyte.tools differs from main"). On plain main this test passes trivially. On any branch that touches `vidbyte/tools` it fails.

## Decision needed (answered: the orchestrator approved Option A as-is; Option B is deferred to the spec author)

QUESTION: May S0 make the smallest test edits needed for the merge, inside the merge commit?

- **Option A (recommended)**: apply the 3-file test patch (9 lines added, 7 removed). I tested it in a throwaway worktree at a simulated merge commit, where both packs then pass except for the 1 inherited test.
  1. `test_codex_host_packaging.py`: update `NATIVE_INIT_SHA256` to `0f77815ce4a68854b26f79420614caa1aa2f6c00ebb80b9c094398469d3989ef` (3855 LF bytes), set `REPO_MAP_SECTION` and `README_BULLET` to the merged texts, and change "911 LF bytes" to "3855 LF bytes" in two comments.
  2. `test_harness_threads_static_policy.py`: add `HOST_SUBPACKAGE = "codex"` and skip that top-level subpackage in `native_modules()`. INV-15 and INV-20 then apply to the thread-function modules (`__init__`, grok, opencode, muse, hostkit), and the codex host keeps its own rules in `tests/features/codex_host/`.
  3. `test_harness_threads_surface.py`: add `:(exclude)` pathspecs for the 4 codex tool paths to the `scoped` tuple of the INV-21 test.
- **Option B**: bring `codex/` into line with #1036's INV-15 and INV-20. That means moving about 40 module constants and messages into `vidbyte/lib/constants`/`enums`, binding the one-shot functions to a class, and removing the `vidbyte.tools` import from `host.py`. This is a refactor of PR #1055, not a merge fix. It might fit the larger goal of one `<verb>_<harness>_thread(s)` vocabulary, but it belongs in the spec stage, not S0.
- **Option C**: move the codex host out of `vidbyte/harnesses/native/`. This changes PR #1055's public import path, which is a large change.

RECOMMENDATION: Option A now. Then the spec author should decide whether codex modules must eventually meet INV-15 and INV-20 (Option B as a scoped spec item).

## Per-file union decisions

### `vidbyte/lib/enums/__init__.py` (content conflict, 1 hunk)
- Branch: inserted `"CodexAccountKind"` into `__all__` (plus 14 more Codex* imports and exports that auto-merged).
- Main: inserted `"CliOptionStyle"` at the same spot (plus the native_threads, outputs, process and skills imports and exports that auto-merged).
- Union: `"CliOptionStyle", "CodexAccountKind"`, in alphabetical order (`Cl` < `Co`).
- Check (AST): `__all__` has 129 names, with no duplicates and no duplicate imports. Every imported name is exported, and every exported name is imported. All of the branch's and main's `__all__` names are present.

### `vidbyte/harnesses/native/__init__.py` (add/add)
- Branch: a docstring-only marker that exports nothing ("callers import a host from its own subpackage").
- Main: the re-export module for the 9 thread functions, 4 records, `NativeThreadError` and 3 enums (17 names in `__all__`).
- Union: main's imports and `__all__` byte for byte (17 names; `test_harness_threads_surface` asserts exactly this list). The docstring now covers both: PURPOSE names the codex host and the thread functions. ROLE says the module does not re-export the Codex host; callers import it from `vidbyte.harnesses.native.codex`. ARCHITECTURE keeps the branch's promise that importing never needs an optional extra. WHAT NOT TO DO gains item 3: do not import codex or any vendor SDK here. TESTS names both packs.
- I deliberately did not add codex re-exports. The branch exported nothing from this module, the main-side test pins exactly 17 names, and re-exporting codex would change #1055's public surface.

### `vidbyte/harnesses/README.md` (content conflict, 1 hunk in "Key modules")
- Branch: a one-line `native/` bullet ("hosts for native coding-harness executables ... on a host class").
- Main: a long `native/` bullet that describes the thread functions, key handling, the EC-27/39/43/44 and T-6 notes, and `hostkit/`.
- Union: one `native/` bullet. It opens with "native coding-harness code ... in two shapes", then a codex sentence (`native/codex/`, `CodexHost`, the `vidbyte-sdk[codex]` extra, import from `vidbyte.harnesses.native.codex`), then main's full text without changes ("The other subpackages hold the harness thread functions, which run ..."). Two `native/` bullets would duplicate the key. The branch's text alone ("each wrapping that harness's official SDK") is false for grok, opencode and muse.

### `REPO_MAP.md` (content conflict, both sides added the same `##### vidbyte/harnesses/native/` heading)
- Branch: one paragraph about host classes, error codes, and no SDK at import.
- Main: one paragraph about the module thread functions and hostkit, ending "There are no host objects, model-facing tools or servers here".
- Union: one heading with two paragraphs. Paragraph 1 is the branch's text, reframed as "in two shapes. The first is a host: Codex gets its own host class, ...", with "each host loads" changed to "the host loads". Paragraph 2 is main's text, starting "The second is module functions ...". Its last sentence is narrowed to "Those three harnesses have no host objects, model-facing tools or servers", because the unscoped sentence would now be false. No other REPO_MAP text was touched. Main's other new sections (`agents/output`, `agents/skills`, `lib/outputs`, `lib/process`, the skills wording) auto-merged.

## Semantic checks on the auto-merged files

- `vidbyte/lib/enums/failure.py`: `FailureCode` has 163 members: the base members, plus 15 from the branch (CODEX_*), plus 28 from main (grok, opencode and muse problems, and MUSE_WSL_UNAVAILABLE). There are no duplicate names, no duplicate values, and no missing members from either side. The other 5 enums are unchanged. The codex codes come before `RULE_EVALUATION_FAILED`, so main's "tail after RULE_EVALUATION_FAILED is exactly the 28 codes" check still holds.
- `vidbyte/lib/errors/base.py`: there are no duplicate top-level names. The branch's change to `CodexAgentError.__init__` (the `next_step` kwarg, `self.next_step`, and `repair_approaches` from `next_step`) is at lines 152 and 160-161. Main's `OutputDeliveryError` (line 188) and `NativeThreadError` (line 559) are present. Main dropped the unused `from typing import Any`, but `Any` is still imported at line 57 (`from typing import TYPE_CHECKING, Any`) and used.
- `vidbyte/lib/errors/__init__.py`: `__all__` has 46 names, with no duplicates. Imports and exports are consistent, and both sides' names are present.
- `pyproject.toml`: auto-merged. The only change from main is the version, 0.2.1 to 0.3.0. The `codex` extra (`openai-codex>=0.162.1,<0.163.0`) was already on the merge base.

## Gates in the blocked round (before Option A; see the final result above)

Notes on how the gates ran:
- Gate (a) ran in this worktree with HEAD still at 66558ee9, so the merge base was the old 8387d666.
- I also built a throwaway merge commit object (`git write-tree` plus `git commit-tree -p HEAD -p origin/main`; SIM = 7bc499c6, on no branch) and ran the gates in a detached worktree at that commit with `PYTHONPATH` set to it. The tests that compare against the merge base only behave as they will after the real commit when HEAD is a merge commit, because only then is the merge base origin/main.

### (a) `VPY -m pytest tests/features/codex_host tests/features/harness_threads -q`
- Worktree, before the commit: `9 failed, 543 passed, 2 skipped in 83.46s`. The 9th failure, `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded`, only happens because the merge base is still the old commit. It passes in the simulated merge.
- Simulated merge (SIM 7bc499c6): `8 failed, 544 passed, 2 skipped in 81.56s`. These are the 7 interaction failures above plus 1 inherited failure.
- Simulated merge plus the Option A patch: `1 failed, 551 passed, 2 skipped in 76.79s`. Only the inherited failure remains.

### (b) `VPY lint/run.py`
- The repo's final line is `SDK-LINT: PASS`, not `AGENT-LINT`. Exit code 0, no REGRESSED rule. S061 improved from 6 to 5 and S063 from 4 to 3; I did not touch the baseline.
```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

### (c) `VPY scripts/run_ci.py --stage source` (run in the simulated merge worktree)
- Lint PASS. The `compileall`, `check_context_write_paths`, `check_context_primitive_introductions` and `check_reasoning_trace_contracts` steps passed, because the gate ran on to the final `pytest` step. Last lines of the full suite:
```
FAILED tests/features/harness_threads/test_harness_threads_static_policy.py::test_harness_modules_never_import_the_tools_layer
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_branch_leaves_the_tools_and_configs_packages_as_main_has_them
=========== 8 failed, 5869 passed, 25 skipped in 142.09s (0:02:22) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest
```
- No failures outside the two packs: the same 8 failures appear, and no others.

## Inherited (fails on plain origin/main 72a4ade1; do not fix here)

- `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, which fails with `assert 148 == 120` at line 193.
- Evidence: in a detached worktree at origin/main, `PYTHONPATH=<wt-main> VPY -m pytest tests/features/harness_threads -q` gives `1 failed, 435 passed, 2 skipped`.
- Cause: this test compares FailureCode with the merge base. Once #1036 was on main, the merge base has 148 members, not 120. The INV-21 test (group 3 above) also compares against the merge base; it passes on main only because main's diff with itself is empty.
- This should be fixed on main in its own PR. The sibling pipeline working on main's harness threads will hit it too.
