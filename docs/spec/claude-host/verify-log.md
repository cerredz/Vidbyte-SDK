# Verification log: ClaudeHost: small atomic Claude Code functions with one agent tool per function

Gate set (from context/code-map.md §1.3 and §1.4). `W` is the worktree, and `PY` is the `sdk-claude-host` venv's Python 3.11.0, whose editable `vidbyte` points at `W`.
- **New tests (local):** `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/claude_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml`, plus the CI view of the same pack with `sys.modules['claude_agent_sdk']=None`.
- **Full local gate (local):** run in this order.
  1. `PYTHONPATH=$W $PY scripts/run_ci.py --stage source`
  2. `$PY scripts/run_ci.py --stage package`, with no PYTHONPATH
  3. `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py`
  4. `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte`, with semgrep 1.170.1 from its own venv
  5. `PYTHONPATH=$W $PY scripts/generate-sdk-public-api.py --check`
- **Remote checks (remote only, dispatch-only):** `gh workflow run ci.yml --ref feat/claude-host` (Source on 3.11 and 3.12, plus Package) and `gh workflow run static-policy.yml --ref feat/claude-host`. `gh pr checks` stays empty for dispatched runs, so read them with `gh run list` and `gh run watch`.

## Iteration 1 — 2026-10-14 02:40 UTC — agent report: reports/S5-repair-1.md
**Defects in:**
- The confirmed code findings: R-1, R-2 and R-3 (Blockers), and R-5, R-6 and R-7 (Majors). R-6's spec edit had already landed in spec r5 (3c1f9e4c).
- The trivial Minors R-10 to R-14.
- R-4, R-8, R-9 and R-19 are spec-only. Spec r5 (3c1f9e4c) settled them before this iteration, so they needed no code.
- No gate was failing on the way in. On d9c5fea2: source 4100 passed / 27 skipped; ci.yml 38468157942 and static-policy 38468160731 green.
- Follow-ups not handed in: R-15, R-16, R-17, R-18, R-20, R-21.

**Hypotheses and attempts** (in order; the failed ones are marked so no later iteration repeats them):
- **R-7 tests first, red against the pre-fix code at 3c1f9e4c.** The new file `test_claude_host_review_gaps.py` started with 11 tests. Red run: `8 failed, 3 passed in 1.25s`. The 3 that passed are the mutant guards M1–M4, which stay green on correct code by design. The 8 failures:
  - R-1, both tests: `AssertionError: 'claude.api_error' != 'claude.process_exited'`, reason "The turn ended with an error result: subtype error_during_execution, terminal_reason aborted_streaming, …".
  - R-2: `5 not less than 4 : the steered prompt went out before its interrupt: ['connect', 'get_server_info', 'query', 'receive_messages', 'query', 'interrupt', 'disconnect']`.
  - R-5: `ClaudeOperationError not raised`.
  - R-3, the result without its declared fields: `'completed' != 'failed'`.
  - R-3, the session info without a summary: `ClaudeOperationError not raised`.
  - R-6, admission: spawn raised `ClaudeOperationError: A rate-limit window refuses new sessions until it resets; get_claude_rate_limits shows when.`
  - R-6, turns: `('failed', 'claude.usage_limited') != ('completed', None)`.
- **R-1.** Two places could hold the fix:
  - (a) clear the interrupted prompt's stale result facts in `session._take_steer`;
  - (b) guard `ClaudeFailureMapper._reported` with `if not outcome.result_seen: return None`, after the assistant-error loop.

  **Chose (b).** It matches §9.2's grouping: rows 5–8 span the whole turn, rows 9–11 read the turn's own result, and row 12 decides when no result came. It also keeps all classification in the mapper. (a) was not tried.
- **R-2.**
  - The reviewer's literal `await asyncio.sleep(0)` was rejected: the in-memory A007 run in review.md shows it fails the blocking rule A007.
  - Awaiting the interrupt task instead was rejected: it breaks AC-37(d).
  - **Used:** `CLAUDE_STEER_YIELD_SECONDS = 0` in `vidbyte/lib/constants/claude.py`, and `if self._steered: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)` right after `self._prompts_sent += 1` in `_query`.
  - The race test passed 10 of 10 repeated runs, and `test_claude_host_stops.py` passed 5 of 5.
- **R-3.**
  - **Attempt 1 failed.** I read the SDK dataclass fields directly and called `isinstance(message, task_progress_message)` inline inside the `_on_task` expression. mypy then narrowed `Any` to `object`, and S009 regressed 351 → 350 baseline (FAIL).
  - **Fix:** bind `progress = isinstance(...)` to a bool first, and read `description` only when it is true. S009 is back to its baseline.
  - Converter parameters are now typed `Any` instead of `object`, which matches `_ClaudeClient.receive_messages() -> AsyncIterator[Any]`.
  - `.get` is kept only for dict payloads: origin, the `model_usage` values, the task usage, and `SessionMessage.message`.
  - A002 flagged the attribute read `message.permission_denials`. Fixed with `# @intent only-the-prompts-own-result-ends-the-turn`, the D-28 slug.
- **R-5.**
  - The reviewer's alternative, `_guard` as the first line of `_admit`, was rejected without trying it. It builds the `continue → _admit → _guard` chain that principle 1 and R-4 are about.
  - **Used:** `self._guard(operation)` again, right after `await ClaudeHistory.session_info(...)` in `continue_claude_session`.
- **R-6.**
  - `usage_limited` now returns False for `seven_day_opus` and `seven_day_sonnet`, as spec r5's D-29 says.
  - The model-facing `GET_CLAUDE_RATE_LIMITS_DESCRIPTION` sentence was updated so it stays true.
  - **Attempt 1 failed.** The new enum import was not wrapped, and S051 (I001) regressed 260/259. That commit was made while lint was red, because I had chained commands with `;`. I wrapped the import and amended my own unpushed commit. Every later commit was gated on `SDK-LINT: PASS`.
- **R-12** (added test, red against the pre-fix `session.py`, run through unittest to show subtest labels): `FAILED (failures=2)`. In both subtests, `window='unknown status'` and `window='unknown overage status'`, the turn ended `('failed', ClaudeFailure(code=CLAUDE_PROTOCOL_MISMATCH, reason='receive_messages raised ValueError.', …), '')` instead of `('completed', None, 'Parser fixed.')`.
- **R-7 mutants**, run against the fixed code, one process each (`scratchpad/mutant.py`). Each one kills exactly one test:
  - M1 (`allowed_warning` no longer counts as allowed): `1 failed, 10 passed in 0.32s`, killed by subtest `window='rejected, overage allowed_warning'`.
  - M2 (`resets_at is None` refuses): `1 failed, 10 passed in 0.32s`, killed by subtest `window='rejected, no reset time'`.
  - M3 (the steer's withdrawal removed): `1 failed, 10 passed in 0.32s`, `SteerWithdrawalTests`, `ClaudeOperationError: A steer is already pending on this turn; wait until it is sent.`
  - M4 (the close re-wait after a cancel removed): `1 failed, 10 passed in 0.38s`, `CancelledCloseTests`, `True is not false : the cancelled aclose returned before its close finished`.
- **Catch-up merge.** `git merge origin/main --no-edit` merged 41 commits from merge-base 678136bd with 0 unmerged paths. Among the PR's own paths, only `vidbyte/harnesses/stores/file.py` changed (+4/−1, from main). After the merge:
  - `native/__init__.py` SHA-256 is still `0374a2c8…942f497a`;
  - the public-API `--check` is current with no regeneration needed.

**Changes:**
- dc9d1734 `fix(claude): classify a steered prompt by its own result [R-1]`
- 4ad8f35d `fix(claude): write a steer's interrupt before its steered prompt [R-2]`
- 52a482d4 `fix(claude): read the pinned SDK record fields directly [R-3]`
- 303b8f8a `fix(claude): refuse a continue that outlived aclose [R-5]`
- d52a1fc8 `fix(claude): never refuse on a per-model rate-limit window [R-6]`
- 2e0a9482 `test(claude): pin the behaviours the S4 review found unguarded [R-7]`
- 3ce56cd4 `fix(claude): drop the unused _ClaudeFieldRules.whole [R-10]`
- c5d243a9 `fix(claude): dispatch transcript blocks with match [R-11]`
- 3cf7b7c8 `fix(claude): skip a rate-limit window with an unknown value [R-12]`, which also adds its test
- 5093e792 `fix(claude): narrate the five unnarrated star methods [R-13]`
- 04e0254b `fix(claude): give each @intent rule exactly one slug [R-14]`
- 15124156, the merge of origin/main (8387d666)

**Gate matrix out** (all at 15124156):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | pack command above; the CI view; the new file alone | PASS | `177 passed in 5.34s` (165 + 12) · CI view `177 passed in 5.27s` · new file `12 passed in 0.99s` |
| full local gate: source | `PYTHONPATH=$W $PY scripts/run_ci.py --stage source` | PASS | `4178 passed, 27 skipped in 36.63s` / `CI passed.` / exit=0 |
| full local gate: package | `$PY scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / exit=0 |
| lint | `lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` / exit=0 |
| semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Findings: 0 (0 blocking)` / `Ran 1 rule on 915 files: 0 findings.` / exit=0 |
| public API | `generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` |
| remote checks | `gh workflow run` + `gh run watch --exit-status` (dispatch-only; `gh pr checks` stays empty) | PASS (2/2) | static-policy 38501879287 `success` · ci.yml 38501877252 `success`: Source / Python 3.12, Source / Python 3.11 and Package, all at 15124156 |

**Still open:** the follow-ups R-15, R-16, R-17, R-18, R-20 (scope-adding, NG-8) and R-21. No confirmed finding and no gate is open.
