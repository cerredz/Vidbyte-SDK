# S5 repair, iteration 1: claude-host

- Agent: S5 repair, iteration 1 of 8
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-claude-host`, branch `feat/claude-host`
- PR: https://github.com/cerredz/Vidbyte-SDK/pull/1044. It stays a draft; its title and body are untouched, because S6 owns them.
- Start: HEAD 3c1f9e4c (spec r5). The remote was at d9c5fea2, so the four docs commits cdf44876..3c1f9e4c went out with this iteration's push.
- Code head: 15124156, the merge of origin/main 8387d666. The docs commit for this iteration follows it.

## Gate matrix

Every gate below ran in this worktree, in this iteration, at 15124156.

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests, pack | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` | PASS | `177 passed in 5.34s` |
| new tests, CI view | the same pack with `sys.modules['claude_agent_sdk']=None` | PASS | `177 passed in 5.27s` |
| new tests, new file | `…/test_claude_host_review_gaps.py` | PASS | `12 passed in 0.99s` |
| source stage | `PYTHONPATH=$W $PY scripts/run_ci.py --stage source` | PASS | `tests\test_workflow_agent_forks.py ......  [100%]` / `====== 4178 passed, 27 skipped in 36.63s ======` / `CI passed.` / `exit=0` |
| package stage | `$PY scripts/run_ci.py --stage package` (no PYTHONPATH) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / `exit=0` |
| lint | `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s). …` / `S064 RATCHETED: 4 known finding(s). …` / `SDK-LINT: PASS` / `exit=0` |
| semgrep | `PATH="/c/Users/422mi/vidbyte-repos/.venvs/semgrep-1.170.1/Scripts:$PATH" semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `✅ Scan completed successfully.` / `• Findings: 0 (0 blocking)` / `Ran 1 rule on 915 files: 0 findings.` / `exit=0` |
| public API | `PYTHONPATH=$W $PY scripts/generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae175913f4ab1cd25d89bfce5ae78e86d0 (vidbyte-sdk 0.2.1, 606 exports).` / `exit=0` |
| remote static-policy | `gh workflow run static-policy.yml --ref feat/claude-host`, run 38501879287 | PASS | `conclusion: success` (head 15124156) |
| remote ci.yml | `gh workflow run ci.yml --ref feat/claude-host`, run 38501877252 | PASS | `conclusion: success` (head 15124156): Source / Python 3.12 `success` · Source / Python 3.11 `success` · Package `success` |

Notes on the gate runs:
- The source stage went from 4100 to 4178 passed because of the 12 new tests and the 41 commits merged from main. The 27 skips are unchanged.
- Lint reports IMPROVED rows: A002 703 → 579, C011, C012, S001, S010 5 → 0, S017, S025 263 → 261, S061. Most come from main's merged work. `lint/baseline.json` was not touched.
- Shared-file contract: the SHA-256 of `vidbyte/harnesses/native/__init__.py` is `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`, both in the working tree and in `git show HEAD:`.

## Per finding

| ID | Commit | What changed | Red before → green after |
|---|---|---|---|
| R-1 | dc9d1734 | `failures.py:179-184`: `ClaudeFailureMapper._reported` returns None when `not outcome.result_seen`. The check comes after the assistant-error loop, so rows 5–8 still apply across the whole turn, and rows 9–11 read only the prompt's own result. Header KNOWN EDGE CASES updated. | Both `SteeredTurnOwnResultTests` failed `'claude.api_error' != 'claude.process_exited'`, reason "…subtype error_during_execution, terminal_reason aborted_streaming…". They pass after the fix. |
| R-2 | 4ad8f35d | `CLAUDE_STEER_YIELD_SECONDS = 0` (`vidbyte/lib/constants/claude.py:54`). `session.py:231-237`: `if self._steered: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)` right after `self._prompts_sent += 1`. | Before: `5 not less than 4 : the steered prompt went out before its interrupt: [… 'query', 'receive_messages', 'query', 'interrupt', 'disconnect']`. After: the test passed 10 of 10 repeated runs, and `test_claude_host_stops.py` passed 5 of 5. |
| R-3 | 52a482d4 | Fields that the 0.2.165 dataclasses declare are read by attribute in history.py (`summary`, `message`) and in `session.py` (`_on_result`, `_on_assistant`, `_on_rate_limit`, `_on_task`). Converter parameters are typed `Any`, which matches the `_ClaudeClient` Protocol. `.get` stays only on dict payloads. `description` is read only for `TaskProgressMessage` (`progress = isinstance(...)`, `session.py:358`). `# @intent only-the-prompts-own-result-ends-the-turn` was added for A002. | Before: drifted result `'completed' != 'failed'`, and drifted session info `ClaudeOperationError not raised`. After: both give `claude.protocol_mismatch`. |
| R-4 | 3c1f9e4c (spec r5) | §17 deviation 12, with no code change. | n/a |
| R-5 | 303b8f8a | `host.py:196-199`: `self._guard(operation)` again, after `await ClaudeHistory.session_info(...)` in `continue_claude_session`. | `ClaudeOperationError not raised` → refused with `action.precondition_failed`, and no client was built. |
| R-6 | d52a1fc8 (code) after 3c1f9e4c (spec r5) | `failures.py:123-129`: `usage_limited` ignores `SEVEN_DAY_OPUS` and `SEVEN_DAY_SONNET` (`# @intent a-per-model-window-never-refuses`). `GET_CLAUDE_RATE_LIMITS_DESCRIPTION` now says a weekly Opus or Sonnet window never refuses new sessions. | Admission before: spawn raised "A rate-limit window refuses new sessions until it resets…". Turns before: `('failed', 'claude.usage_limited') != ('completed', None)`. Both pass after the fix. The five_hour control row still ends `failed claude.usage_limited`. |
| R-7 | 2e0a9482, plus the R-12 case in 3cf7b7c8 | New file `tests/features/claude_host/test_claude_host_review_gaps.py` with 12 tests. README.md gets +2 lines and FEATURE.md gets +17 lines, all additions. | The pre-fix run at 3c1f9e4c gave `8 failed, 3 passed in 1.25s`. The mutants, each in its own process, are listed below the table. |
| R-8, R-9, R-19 | 3c1f9e4c (spec r5) | Spec text only (deviation 1 wording, deviation 13, T-2 limitation with Q-13). | n/a |
| R-10 | 3ce56cd4 | Deleted the unused `_ClaudeFieldRules.whole`. | pack green; lint PASS |
| R-11 | c5d243a9 | `ClaudeHistory.message` dispatches on `match kind:` with `case _:`. | pack green; lint PASS |
| R-12 | 3cf7b7c8 | `_WINDOW_STATUSES` (`session.py:66`). `_on_rate_limit` returns early on an unknown type, status or overage (`:335-336`, EC-52). Test added. | Before: `FAILED (failures=2)`. Subtests `window='unknown status'` and `window='unknown overage status'` both ended `failed` with `claude.protocol_mismatch`, "receive_messages raised ValueError.". After: `completed`, "Parser fixed.". |
| R-13 | 5093e792 | Narration comments in the five ★ methods `get_claude_session_info`, `wait_claude_turn`, `get_claude_turn_result`, `interrupt_claude_turn` and `track_claude_session_usage`. | lint PASS |
| R-14 | 04e0254b | Every `@intent` rule now has one slug. `tool_server.py` uses `claude-code-approves-before-vidbyte-runs`. `sessions.py` (twice) and `toolsets/claude.py` use `the-developer-fixes-every-spawn-setting`, as `_base.py` does. The intent block in `_check_prompting` covers only the permission-prompt rule. | lint PASS (A002) |

R-7's mutants, each run against the fixed code in its own process:
- M1 → `1 failed, 10 passed in 0.32s`, killed by subtest `window='rejected, overage allowed_warning'`.
- M2 → `1 failed, 10 passed in 0.32s`, killed by subtest `window='rejected, no reset time'`.
- M3 → `1 failed, 10 passed in 0.32s`, `SteerWithdrawalTests`: "A steer is already pending on this turn; wait until it is sent."
- M4 → `1 failed, 10 passed in 0.38s`, `CancelledCloseTests`: "True is not false : the cancelled aclose returned before its close finished".

Attempts that failed are recorded in verify-log.md:
- R-3's first version, with an inline `isinstance`, failed S009 at 351/350.
- R-6's first commit had an unwrapped import, which failed S051 at 260/259. I amended that commit, which had not been pushed.

## Test-tree diff since S2_HEAD

`git diff 9a8ecc3c..HEAD --stat -- tests/features/claude_host`:
```
 tests/features/claude_host/FEATURE.md              |  17 ++
 tests/features/claude_host/README.md               |   2 +
 .../claude_host/test_claude_host_review_gaps.py    | 301 +++++++++++++++++++++
 3 files changed, 320 insertions(+)
```

- The 165 existing tests and `claude_host_fixtures.py` are byte-identical.
- The unscoped `git diff 9a8ecc3c..HEAD -- tests/` also lists test files that origin/main changed and that reached this branch through the catch-up merge. None of them is under `tests/features/claude_host`.

## Test changes proposed

None. No existing test needed to change.

## Findings disputed

None. Refuted R-E1 and the R-V2 interrupt chain were left alone, as the briefing said. D-29 still fails a turn that saw an account-wide refusing window even when its result is a success.

## Notes on scope

- **R-6's tool-description sentence.** I changed it because the model-facing text would otherwise state the old rule. It is the same rule change, not a new control.
- **Tests outside R-7's list.** R-3 and R-12 got regression tests that R-7 did not list. They sit in the granted file.
- **Catch-up merge.** `git merge origin/main --no-edit` brought in 41 commits from merge-base 678136bd, with 0 unmerged paths.
  - Among the PR's own paths, only `vidbyte/harnesses/stores/file.py` changed (+4/−1, from main).
  - The public-API contract needed no regeneration (`--check` current).
  - After `git fetch`, origin/main 8387d666 is an ancestor of HEAD.

## Still open

- **Follow-ups, not fixed per the briefing:** R-15, R-16, R-17, R-18, R-20 (scope-adding, NG-8) and R-21.
- **Hypothesis for R-21, if it is ever taken:** `aclose` keeps a set of in-flight probe tasks and waits for them, the same way it waits for session close tasks.
- **No confirmed finding is open.**
