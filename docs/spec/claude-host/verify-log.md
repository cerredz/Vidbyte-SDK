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

## Iteration 2 — 2026-10-14 05:55 UTC — agent report: reports/S5-repair-2.md
**Defects in:**
- R-22 (Major), a regression from iteration 1's R-2 fix: the pump took the steer out of its slot one loop pass before it sent it, so a stop or a failed steer interrupt in that pass could not withdraw it (INV-18, §9.2 steer row, row 7).
- R-23 (Minor, code): a steered prompt that ended before its own result published the interrupted prompt's result fields (D-3).
- R-24 (Minor, spec text): already settled by spec r6 (9211d4ef) before this iteration. It needed only a check that the code matches r6's deviation 14, row 7, row 14 and EC-52 once R-22 landed.
- No gate was failing on the way in. At 615fc54a every local gate and both remote runs were green, and the pack had 177 tests.

**Hypotheses and attempts** (in order; no code attempt failed, so the dead ends below are the designs I rejected):
- **R-22: three placements weighed before choosing.**
  - (a) **Used.** The yield moves into `_take_steer`, which becomes async and opens with `if self._steer is not None: await asyncio.sleep(CLAUDE_STEER_YIELD_SECONDS)`, before the take. `run` now calls `prompt = await self._take_steer() if await self._read(stream) else None`. The yield and its comment are gone from `_query`. This is the verifier's in-memory candidate, and r6 deviation 14 describes it.
  - (b) **Rejected.** Keep the yield in `_query` and re-check the slot or `_stopping` after it. It misses P3, because a failed steer interrupt sets neither. It would also have to un-count `_prompts_sent`, which is already 2 during the yield.
  - (c) **Rejected.** Yield inside `_read`, before `return True`. That nests four deep and breaks the blocking rule S024.
  - **Not retried:** a literal `asyncio.sleep(0)` (A007 rejects it, iteration 1), and awaiting the interrupt task before the query (it breaks AC-37(d), iteration 1).
- **R-22 tests, written first and run red.** Three cases in the new `StopInSteerWindowTests`, run against the unfixed session.py, which is byte-identical to 615fc54a's (`git diff 615fc54a -- vidbyte` was empty). Red run: `3 failed in 0.91s`.
  - P1, `test_an_interrupt_in_the_steer_window_discards_the_steer`: `AssertionError: None != 'action.precondition_failed'`.
  - P2b, `test_an_aclose_in_the_steer_window_discards_the_steer`, with `aclose` scheduled before `finish()`: `AssertionError: None != 'action.precondition_failed'`.
  - P3, `test_a_failed_steer_interrupt_in_the_window_withdraws_the_message`: `AssertionError: Lists differ: ['Summarize the repository layout.', 'focus on tests'] != ['Summarize the repository layout.']`.
  - Each case awaits the steer directly and catches `ClaudeOperationError` by hand. None wraps it in `asyncio.wait_for` or `self.raises`, because a wrapped steer starts after the pump read the result (the gaps file header, WHAT NOT TO DO 4).
  - P4, the time budget, has no test. To reach the pass, a test must start the session's private `_watch(client, 0)` by hand. The public `timeout_seconds` reaches the pass only by chance timing. The probe covers P4 instead (next item).
- **R-22 after the fix.** The three cases pass, the pack gives `180 passed`, and `gaps + stops` passed 5 of 5 repeated runs (`38 passed`). I ran my probe (`scratchpad/repair2/probe_fixed.py`) against the session.py on disk:
  - P1 → the steer `raised action.precondition_failed`; calls `[…,'receive_messages','interrupt','disconnect']`; final `('interrupted', None, 'The first answer.')`.
  - P2b → the steer `raised action.precondition_failed`, and no second query was sent.
  - P3 → the steer `raised claude.process_exited`; queries `[first only]`; final `('completed', None, 'The first answer.')`.
  - P4 → the steer `raised action.precondition_failed`; final `('failed', 'claude.budget_exhausted', 'The first answer.')`.
  - The R-2 control keeps its order: `[…,'receive_messages','interrupt','query','disconnect']` → `('completed', None, 'steered answer')`.
  - P2a (`aclose` scheduled after `finish()`) still sends the steered prompt, and the steer returns None. That is correct, because in that order the close starts only after the send (the verifier refuted this ordering as a defect).
- **R-23.** The reset sits inside `_take_steer`'s `if steer is not None:`, after `self._steered = self._steers`: `self._result = replace(self._result, result_text="", structured_output=None, num_turns=None, duration_ms=None, stop_reason="", terminal_reason="", permission_denials=())`. `session_id`, `hooks_applied` and `total_cost_usd` stay, and `_outcome` is untouched.
  - **Test design.** The verifier's draft case used the default interrupted result. In that result only 3 of the 7 fields differ from their defaults, so a reset that cleared only those 3 would still pass. The committed case sets `fake.interrupt_reply` to a full result instead: text, structured output, one permission denial, `stop_reason='end_turn'`, `terminal_reason='completed'`, 1 turn, 4200 ms and cost 0.008. All 7 fields are then non-default while the test is red.
  - **Red at b5989730** (R-22 only): `AssertionError: Tuples differ: ('The parser bug is fixed.', {'summary': 'P[113 chars]'),)) != ('', None, None, None, '', '', ())`.
  - **After the fix:** the case passes, and the pack and its CI view each give `181 passed`. The P2a probe now ends `('interrupted', None, '')`, which matches D-3 as the verifier adjudicated it.
- **All four new tests against 615fc54a's session.py.** I wrote that version over the working file, ran the tests, and restored the file with `git checkout`. `git status` then showed only the test file. Result: `4 failed in 0.93s`, with the same four assertion messages as above.
- **R-24.** No code change was needed:
  - The yield now runs once, inside `_take_steer`, before the take, and only while a steer is pending, as deviation 14 and row 7 say.
  - Row 14's constant is `CLAUDE_STEER_YIELD_SECONDS = 0`.
  - EC-52's skip of an unknown type, status or overage status is in `_on_rate_limit`.
  - No other file describes the old placement. A case-insensitive grep for `yield once`, `yields once`, `STEER_YIELD` and `_take_steer` over vidbyte, tests, lint and REPO_MAP.md finds only the constant outside session.py.
- **Gotcha, caught before commit.** I first changed the full stop that ends the last bullet of FEATURE.md's suite map to `;`, so that a new bullet could follow it. That edits an existing line, which counts as a deletion under the tests' additions-only contract. I reverted it, and the new bullets now follow the unchanged line. `git diff --numstat 9a8ecc3c..HEAD -- tests/features/claude_host` gives `23 0`, `4 0` and `377 0`.
- **Lint.** After each fix, the rule table matched iteration 1's `gate-lint.txt` row for row. Every new comment line is at most 71 columns. No `@intent` line was needed: A002 reads names and attributes, not keyword arguments, so `permission_denials=()` inside `replace()` does not trigger it.

**Changes:**
- b5989730 `fix(claude): yield before taking a steer so a stop can still withdraw it [R-22]`: session.py `+12/−11`, `StopInSteerWindowTests`, three FEATURE.md regression lines, one suite-map bullet and one README log line.
- 2c537b1a `fix(claude): clear the interrupted prompt's result fields when a steer is sent [R-23]`: session.py `+5/−1`, `SteeredResultFieldsTests`, one FEATURE.md regression line, one suite-map bullet and one README log line.
- No catch-up merge was needed. After `git fetch origin`, `git rev-list --count HEAD..origin/main` gave 0, and origin/main is still 8387d666.

**Gate matrix out** (every gate, local and remote, at 2c537b1a):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | the pack command above; the CI view; the four new cases alone | PASS | `181 passed in 5.58s` (177 + 4) · CI view `181 passed in 5.44s` · new cases `4 passed in 0.83s` |
| full local gate: source | `PYTHONPATH=$W $PY scripts/run_ci.py --stage source` | PASS | `4182 passed, 27 skipped in 39.25s` / `CI passed.` / exit=0 |
| full local gate: package | `$PY scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` / exit=0 |
| lint | `lint/run.py` | PASS | `S063 RATCHETED: 4 known finding(s).` / `S064 RATCHETED: 4 known finding(s).` / `SDK-LINT: PASS` / exit=0 |
| semgrep | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Ran 1 rule on 915 files: 0 findings.` / exit=0 |
| public API | `generate-sdk-public-api.py --check` | PASS | `contracts/sdk-public-api.json is current at f7a02bae… (vidbyte-sdk 0.2.1, 606 exports).` / exit=0 |
| shared file | `git show HEAD:vidbyte/harnesses/native/__init__.py \| sha256sum` | PASS | `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a` |
| remote checks | `gh workflow run` + `gh run watch --exit-status` (dispatch-only) | PASS (2/2) | ci.yml 38519021773 `success`: Source / Python 3.12 `4190 passed, 19 skipped, 19 warnings in 40.98s` / `CI passed.`; Source / Python 3.11 `4190 passed, 19 skipped in 45.27s` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` · static-policy 38519023850 `success` |

**Still open:** the follow-ups R-15, R-16, R-17, R-18, R-20 (scope-adding, NG-8) and R-21, which were not handed in. No confirmed finding and no gate is open.
