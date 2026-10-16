# S5 repair report, iteration 3 of 8 (`[gate:mergeable]`)

Stage: S5 repair · Branch `feat/codex-host` · PR https://github.com/cerredz/Vidbyte-SDK/pull/1055 (draft) · Start HEAD `13453ea3` (origin at `867d6f0c`) · Merged in origin/main `cb554ed3` · Venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers/Scripts/python`

## Outcome

PR #1055 is mergeable again. At the start, GitHub reported `CONFLICTING DIRTY`, because origin/main had moved from `72a4ade1` to `cb554ed3` (54 commits, #1095 and #1103 to #1157). I merged `cb554ed3` with a merge commit, `b96b64cc`, and resolved the one conflict as a union. I checked every auto-merged file and every interaction I could find between main's changes and this PR's code. Then I ran the full gate set on the merged tree, pushed fast-forward (`867d6f0c..b96b64cc`) and dispatched both workflows.

GitHub now answers `"mergeable":"MERGEABLE"`, with `mergeStateStatus` `BLOCKED`. BLOCKED is expected: dispatched runs never enter the PR's check rollup, so branch protection never sees them, and the owner merges with `--admin` (field guide `local-ci-verification.md`, "Dispatched checks never unblock the merge").

The merge needed no test change, no source change beyond the conflict line, and no baseline change. Every gate matches iteration 2. The only differences are the counts that main's new tests add, plus one lint row that moved because of main's own files.

Main moved once more while the gates ran: #1158, `8da41971`, which has no conflict with this PR. I merged that too, so that the tree the owner squashes is the tree that was tested. See "Second merge" below.

| Commit | Defect | Subject |
|---|---|---|
| `b96b64cc` | `[gate:mergeable]` | `merge: bring origin/main cb554ed3 into feat/codex-host [gate:mergeable]` |
| `2e60369c` | — | `docs(spec): verify-log iteration 3 for codex-host-thread-helpers` (verify-log entry and header line, this report) |
| `0ded7dc7` | `[gate:mergeable]` | `merge: bring origin/main 8da41971 into feat/codex-host [gate:mergeable]` |
| next | — | `docs(spec): record the second main merge of S5 iteration 3 for codex-host-thread-helpers` |

## The conflict: `vidbyte/lib/errors/base.py`

`git merge-tree --write-tree --name-only HEAD origin/main` and the real merge agree: this file is the only content conflict, and the conflict is one line, the signature of `CodexAgentError.__init__`.

- **Main's intent (#1116, `b2077e91`):** "a fallback attempt continues on the thread the failed first turn opened". `CodexAgentError` gains a keyword-only `thread_id: str = ""` and sets `self.thread_id`. The transport fills it on a failed `turn_run`. `CodexHarnessAgent._run_turn` then reuses that thread for the next attempt (`agent.py:302-305`), so the fallback model does not orphan the first thread.
- **This PR's intent (`ad9eef7c`, original #1055 W-3, FR-20/AC-29):** a keyword-only `next_step: str = ""`, stored as `self.next_step`. It also replaces the generic `repair_approaches` when it is given. `CodexErrorMapper.error` passes `CODEX_NEXT_STEPS[code]` on every host error (`errors.py:65`), and the tools show it as "Next step: …".
- **Resolution:** `error_type: str = "", next_step: str = "", thread_id: str = ""`. Everything outside the signature line had merged cleanly: main's comment and `self.thread_id`, and the PR's `self.next_step` and `repair_approaches`.
  - Why this order: all three parameters are keyword-only and have defaults, so their order cannot change any call site. No test inspects this signature (`git grep "signature(CodexAgentError\|CodexAgentError.__init__"` over `tests` at both parents: 0 hits).
  - Line endings: the file is CRLF in the working copy and LF in the index. The resolution script refuses mixed endings and keeps CRLF (616 of 616 lines).
- **Proof the union is exact:**
  - `git diff --cached origin/main -- vidbyte/lib/errors/base.py` shows only the PR's three lines.
  - `git diff --cached HEAD -- vidbyte/lib/errors/base.py` shows only main's three lines.
  - A probe (`C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s5i3_union_probe.py`) printed `keyword-only: ['failure_code', 'operation', 'error_type', 'next_step', 'thread_id']`.
    - Both fields set: `th_1 | Do Y. | ('Do Y.',)`.
    - Neither set: `'' | '' | ('Inspect the operation …',)`.
    - Main-style: `th_2 | ''`.
    - PR-style: `'' | Do Z. | ('Do Z.',)`.
  - Main's thread-reuse tests (`tests/test_codex_failure_recovery.py`, which pass `thread_id=`) and this PR's `next_step` tests (`test_codex_host_records.py`) all pass in the source stage.

## Auto-merged files, checked for meaning

| File | Main's change | This PR's change | Clash? | Evidence |
|---|---|---|---|---|
| `REPO_MAP.md` | 2 rows of the JEV File Locations table (#1005): `JevReadOnly` and `PermissionCeiling` rows; `bulk_work.py`, `read_only.py` | the `##### vidbyte/harnesses/native/` section (S0 union) | No | `git diff --cached HEAD -- REPO_MAP.md` touches only lines 387-404. The byte-pinned native/ section is unchanged, and `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores` passes. |
| `vidbyte/agents/codex/tools.py` | #1121: `CodexToolCallHandler.__init__` stores `contextvars.copy_context()`, and `handle()` runs `run_coroutine_threadsafe` inside a copy of it. The header ARCHITECTURE NOTE says so. | W-4: `validate_names()` and `CodexToolBridge.handler()`, which `attach()` and `CodexHost._open_thread` (`host.py:667`) call | No | The capture lives in the handler's `__init__`, so both builders get it. `attach()` builds the handler inside the run's turn, as main intends. For the host, see "Interactions" below. `tests/test_codex_tools.py` and the codex_host bridge and router tests pass. |
| `vidbyte/lib/enums/__init__.py` | #1095: `SystemPromptPreset` import and export | 14 `Codex*` enums including `CodexSkillScope`; R-16 TESTS block | No | AST check (`…/scratchpad/s5i3_enums_check.py`): 131 names, 131 unique, no duplicate imports, `ours missing: []`, `main missing: []`, every export imported, `Codex*` order identical to HEAD's (the `ENUMS_CODEX_ORDER` pin). |

Pinned files that the merge leaves exactly as at HEAD: `vidbyte/harnesses/native/__init__.py` (SHA-256 pin), `vidbyte/harnesses/README.md` (bullet pin), `vidbyte/lib/enums/failure.py` (the 28-code tail pin), `vidbyte/lib/constants/codex.py` (the `__all__` order pin at `test_codex_host_helper_surface.py:288`), `vidbyte/lib/enums/codex.py` and `vidbyte/agents/codex/result.py`. Main did not touch `tests/features/harness_threads/`, so S0's branch-scope pins still apply. The merge base is now `cb554ed3`, and `test_branch_leaves_the_tools_and_configs_packages_as_main_has_them` and `test_import_vidbyte_starts_no_process_and_leaves_the_native_package_unloaded` both pass.

**The PR's net change is preserved.** I compared `git diff -U0 cb554ed3 b96b64cc` with `git diff -U0 72a4ade1 13453ea3`, both outside `docs/`, with index lines and hunk headers removed. They are identical except for the resolved signature line. Both show 57 files, +14590/-23. In the other direction, the merge brought in exactly main's 135 files, +8075/-265.

## Interactions outside the shared files (read for meaning; no change made)

1. **#1129 `vidbyte/agents/codex/metrics.py`.** An explicit `model_provider="openai"` is now priced like the default. The host uses this translator (`turns.py:403`), so host turns on an explicit `"openai"` provider now record usage too. That is main's intent, and it now holds for the host as well. The host's custom-provider tests (`ollama`, no usage) still pass.
2. **#1005 and #1121 `PermissionCeiling`.**
   - The CodexHostTools run through `ToolExecutor`, which calls `PermissionPolicy.check`, so a READ_ONLY ceiling refuses every WRITE host tool (spawn, continue, review, compact, run_goal, run_skill, run_openai_docs).
   - A host thread's dynamic-tool handler is built in `_open_thread` and keeps the context of the `spawn_codex_thread` call. A ceiling active at spawn therefore binds that thread's tool calls for its whole life, including turns started later by `continue_codex_thread`. Before the merge, the handler ran tool calls in the SDK reader thread's empty context, so no ceiling bound them. The merge only tightens this.
   - Candidate follow-up, not a defect: rebuild the handler's context on each turn, so that the ceiling of the run that continues a thread binds it. That would change `vidbyte/agents/codex/tools.py`, which is outside this run's §12.3.
3. **`thread_id` on the host path.** `CodexSkillFunctions._unchecked` (`skill_functions.py:247`) rebuilds a `CodexAgentError` and does not copy `thread_id`. No host code sets `thread_id`: `CodexErrorMapper.error` puts the thread id in the message instead (`errors.py:64`). So the field is always `""` there, and nothing is lost today. If the host ever sets `thread_id`, that line should copy it.

## Gate matrix (local gates at `b96b64cc`, clean tree, `git ls-files -u` empty)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| 1 area tests | `PYTHONPATH=$(pwd) $VPY -m pytest -q tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py` | PASS (inherited only) | `tests\features\harness_threads\test_harness_threads_surface.py:193: AssertionError` · `=========================== short test summary info ===========================` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 683 passed, 2 skipped in 52.51s` |
| 2 lint | `$VPY lint/run.py` | PASS (exit 0, no REGRESSED, no ERRORED) | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| 3 public API | `PYTHONPATH=$(pwd) $VPY scripts/generate-sdk-public-api.py --check` | PASS; nothing regenerated | `contracts/sdk-public-api.json is current at d08e89ef75ff4a6ee07465ee5097363e7d0d26c4 (vidbyte-sdk 0.3.0, 640 exports).` |
| 4 source stage | `PYTHONPATH=$(pwd) $VPY scripts/run_ci.py --stage source` | PASS (inherited only) | `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6223 passed, 26 skipped in 101.35s (0:01:41) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest (cwd=…vidbyte-sdk-codex-host-thread-helpers).` |
| 5 package stage | `env -u PYTHONPATH $VPY scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 6 static policy | `git add -A` (nothing staged); `pysemgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py`; `pysemgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` (semgrep 1.170.1, `codex-host-semgrep` venv) | PASS | `1/1: ✓ All tests passed` · `Scan was limited to files tracked by git` · `Ran 1 rule on 986 files: 0 findings.` |
| extra: mypy | `PYTHONPATH=$(pwd) $VPY -m mypy --follow-imports=silent` on 11 modules (the 4 host modules, the 2 new tool modules, toolsets/codex, constants/codex, errors/base, agents/codex/tools, agents/codex/agent) | PASS | `Success: no issues found in 11 source files` |
| inherited proof | that test in a detached scratch worktree at `cb554ed3`, with `vidbyte` loaded from it | FAIL, as on main | `E       AssertionError: assert 148 == 120` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed in 0.88s` |
| mergeable | `gh pr view 1055 --repo cerredz/Vidbyte-SDK --json mergeable,mergeStateStatus,headRefOid,isDraft` | PASS | `{"headRefOid":"b96b64cc11c4ae1e34867c37cc4593095fd0395f","isDraft":true,"mergeStateStatus":"BLOCKED","mergeable":"MERGEABLE"}` |
| 7 remote checks | dispatched `ci.yml` 38934876157 and `static-policy.yml` 38934879502 on `b96b64cc` | PASS 4/4 | `gh api repos/cerredz/Vidbyte-SDK/commits/b96b64cc…/check-runs`: `Package completed success` · `Static policy completed success` · `Source / Python 3.11 completed success` · `Source / Python 3.12 completed success`. The docs commit after this one is dispatched again; its result is in the S5 STATUS block. |

### How this matrix compares with iteration 2

- **Area: 678 → 683 passed.** Main added 5 tests to `tests/test_codex_output_contracts.py`: `git grep -c "def test_"` gives 46 at `72a4ade1` and 51 at `cb554ed3`.
- **Source: 5957 + 25 + 1 = 5983 tests → 6223 + 26 + 1 = 6250.** The +267 matches main's own growth, measured independently of the gate: `pytest --collect-only` collects 5786 tests at `72a4ade1` and 6053 at `cb554ed3`.
- **Public API: 639 → 640 exports.** This is main's regenerated contract (`SystemPromptPreset`). It needed no regeneration here.
- **Semgrep: 980 → 986 files.** Main added 6 `vidbyte` modules.
- **Lint: A001 moved from IMPROVED (642 → 640) to RATCHETED (642/642).**
  - The cause is main. `lint/run.py --rule A001 --all --format json` writes byte-identical output on the merged tree and on plain `cb554ed3`.
  - The +2 are two header-less test files that main added: `tests/test_algorithms_honor_middleware_abort.py` and `tests/test_independent_critic_algorithm.py`.
  - The other 7 IMPROVED rows are the same as before. The A007, C008, S008, S024 and S064 ratchets are unchanged. Main did not touch `lint/`, and `lint/baseline.json` is untouched.

## Second merge: `8da41971` (#1158)

- **When it happened:** right after `2e60369c` was pushed, `git fetch` showed origin/main at `8da41971`, one commit past `cb554ed3`. GitHub answered `"mergeStateStatus":"BEHIND","mergeable":"MERGEABLE"`.
- **What #1158 changes:** only `vidbyte/agents/codex/fork.py` (a fork rebinds inherited context tools with `AgentForker._clone_tool`), one line of `vidbyte/agents/codex/README.md`, and `tests/test_codex_fork_inheritance.py`. This PR touches none of them. `git merge-tree --write-tree` was clean, and the real merge `0ded7dc7` had no conflict.
- **Where it meets this PR:** the fork then calls `CodexVidbyteTranslator().translate_agent`, which runs this PR's `CodexToolTranslator.validate_names`. `tests/test_codex_fork_inheritance.py tests/test_codex_tools.py` gives `61 passed in 1.52s`.
- **The PR's net diff is unchanged:** `git diff -U0 8da41971 0ded7dc7` is identical to `git diff -U0 cb554ed3 b96b64cc` outside `docs/` (57 files, +14590/-23).
- **The inherited proof still holds:** #1158 changes neither `failure.py` nor `tests/features/harness_threads` (`git diff --quiet` succeeds), so the proof at `cb554ed3` carries over.
- **Superseded runs:** I cancelled the runs already dispatched on `2e60369c` (38935602952 and 38935606171).

| Gate at `0ded7dc7` | Result | Final lines |
|---|---|---|
| 1 area tests | PASS (inherited only) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `1 failed, 683 passed, 2 skipped in 52.44s` |
| 2 lint | PASS | All 133 rule rows identical to `b96b64cc` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` |
| 3 public API | PASS | `contracts/sdk-public-api.json is current at d08e89ef75ff4a6ee07465ee5097363e7d0d26c4 (vidbyte-sdk 0.3.0, 640 exports).` |
| 4 source stage | PASS (inherited only) | `reasoning trace contracts: ok (182 tools, 55 shapes)` · `FAILED …::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` · `=========== 1 failed, 6229 passed, 26 skipped in 100.90s (0:01:40) ============` · `CI failed: Command failed with exit code 1: …python.exe -m pytest` (+6 tests = #1158's; `def test_` count 7 → 13) |
| 5 package stage | PASS | `No broken requirements found.` · `Installed vidbyte-sdk 0.3.0 passed smoke checks.` · `CI passed.` |
| 6 static policy | PASS | `1/1: ✓ All tests passed` · `Scan was limited to files tracked by git` · `Ran 1 rule on 986 files: 0 findings.` |
| 7 remote checks and mergeable | on the final docs commit | reported in the S5 STATUS block |

## The inherited failure at the new merge base

After the merge, `git merge-base origin/main HEAD` is `cb554ed3`. In a detached scratch worktree at `cb554ed3`, HEAD, origin/main and their merge base are all `cb554ed3`. There, `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` still fails with `assert 148 == 120`. Main has not changed `vidbyte/lib/enums/failure.py` since `72a4ade1`, so main's FailureCode still has 148 members while the test expects the pre-#1036 120. The failure is still inherited: a fix belongs on main in its own PR. Remote CI still passes it, because its shallow checkout has no `origin/main`. The scratch worktree was removed with `git worktree remove`; it was clean, so no `--force` was needed.

## Test changes

None. The pre-granted re-pin rule was not used: no test failed on the merged tree except the inherited one, and `git diff 13453ea3 b96b64cc -- tests/features/codex_host tests/features/harness_threads` is empty.

## Findings

No finding was handed in, and none moved. review.md is unchanged. R-1 to R-9 and R-16 stay fixed. R-10 to R-15 stay follow-ups for the PR body.

## For the S6 PR author

- The PR body can say that the branch merges origin/main up to `8da41971` (#1158) and is green on the merged tree: source `1 failed (inherited), 6229 passed, 26 skipped`, package `CI passed.`, lint `SDK-LINT: PASS`, API 640 exports.
- The owner merges with `gh pr merge 1055 --squash --admin --match-head-commit <final sha>`, because dispatched checks never clear BLOCKED. If main moves first, main must be merged again and the checks re-dispatched (field guide).
- The `PermissionCeiling` interaction (Interactions, item 2) is worth one line under follow-ups.

## Open items

None. All gates are green apart from the one inherited test, no finding is open, and the PR is MERGEABLE.
