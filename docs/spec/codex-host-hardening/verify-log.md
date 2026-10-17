# Verification log: CodexHost production hardening and missed settings (slice 1 of 2)

Gate set (from context/code-map.md §1, with this run's interpreter `V` = the `venv-codex163` editable install; every gate runs locally, and no workflow runs on push):
- **Area tests** (local): `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider`
- **Lint** (local, also inside the source stage): `"$V" lint/run.py`; the last line must be `SDK-LINT: PASS`
- **Ruff** (local): S051's selectors over the changed files, `"$V" -m ruff check <changed .py> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache`
- **Semgrep** (local): the bundled `semgrep-core.exe -rules .semgrep/<rule>.yml -lang python -json <file>`, one changed file per call, after the code is committed
- **Full gate, source stage** (local): `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source`
- **Full gate, package stage** (local): `"$V" scripts/run_ci.py --stage package`, with no PYTHONPATH
- **Test contract** (local): `git diff 6b59d390..HEAD -- tests` stays empty
- **Remote checks** (remote-only): `gh pr checks 1181`; the workflows run only on `workflow_dispatch`, so a push triggers none

## Iteration 1 — 2026-10-17 — agent report: reports/S5-repair-1.md
**Defects in:** R-1, R-2 and R-3 (Blockers); R-7 (code side), R-9 and R-10 (Majors); the minors m-1 to m-7, to be fixed only when trivial with a clear spec answer. R-4, R-5, R-6 and R-8 were test-only and already fixed in `75bfae7d`. Failing gates at `436b07c3`: the area tests gave `18 failed, 1029 passed, 3 skipped`, which was 17 of this slice's red tests plus the inherited `harness_threads` surface failure. Lint passed.

**Hypotheses and attempts:**
- **R-1.** The finding was six source comment lines at 73 columns. A scan of every comment line the PR added (the script `scratchpad/s5r1_wide_comments.py <base>`, which parses `git diff -U0 <base>...HEAD`) found exactly those six in `vidbyte/`. It also found 178 in `tests/`, which are S2's files and out of scope. I re-filled each block evenly, keeping its words and its `@intent` line. The scan now finds 0 in `vidbyte/`. Any comment added later has to be scanned again.
- **R-2.** I took the review's fix as written: two lib constants, sorted into `__all__`, and `_reject_experimental_fork_fields` walking the tuple with `getattr`. It worked first time.
- **R-3.** I wrapped the finish of an ended review in `try … except Exception: events.fail(turn, exc)`, which is the sibling pattern at `turn_events.py:84-89,105-111`. I renamed `_fail` to `fail`, which had two callers plus the header. It worked first time. Independent check: the S4 verifier's probe `ProbeRC1` (`scratchpad/s4-verify/probe_s4v_code.py`) now prints `RC1 FIRST REVIEW: returned`, `RC1 REGISTRY RUNNING: []` and `RC1-LATE SECOND REVIEW: returned`. `RC1 FORGET: … session_busy` is correct, because the probe's second review is still running when it forgets.
- **R-7.** I restored `_reject_goal_fields(owner, request)` and gave the message its `{owner}` slot. It worked first time.
- **R-9, the helper.** I wrote `LogToken.of` with str methods only (spec row 25 keeps the header's "str methods and math.ceil").
  - Rejected `re.sub`, because of that header.
  - Rejected `str.translate`, because it would need a table over every code point.
  - Chose to map only `value[:limit]`. The map turns each character into exactly one, so the result is identical to mapping the whole value and then cutting it, and a 100,000-character id costs 128 checks (about 0.07 ms).
- **R-9, the call sites.**
  - Rejected (a), cleaning the ids inside `_ids`. INV-10 says routing keeps the raw values.
  - Rejected (b), a `_tokens(*values)` helper unpacked into the log call. It only forwards, and the star hides the argument count from the log-format rules.
  - Chose (c), `LogToken.of(value, CODEX_HOST_LOG_TOKEN_MAX_CHARS)` written at each log call. I checked that all 19 `ThreadItem` variants in 0.163.0 have a `str` id and a `Literal[str]` type, so `observe` cannot raise on them. openai-codex only routes a server request whose `method` is a `str` (`client.py:886-893`), so the router cannot raise on it either.
  - Independent check: `ProbeRE1` now prints `RE1 LINES: 1`, a forged `itemId` logs as one token with the true `answer=decline`, and the 100,000-character id record is 268 characters.
- **R-10, `start`.**
  - Rejected (a), an unconditional log in `_land`. It double-records the timeout hand-over, which already logged (verifier note).
  - Rejected (b), letting `_post_late(record)` call the record itself. That makes `_post_late → _log_late → _log_call`, a three-deep chain in one class (AGENTS.md §1).
  - Chose (c). `_hand_over(…, record)` registers `record` as its own done-callback before `_post_late`'s. `concurrent.futures` runs done-callbacks in the order they were registered, on the worker, or at once in the caller when the future is already done. So the record is still written before the post, and a closed loop cannot drop it. The timeout hand-over passes `None`.
- **R-10, `call`.** `call` now runs `submit` and then `asyncio.wrap_future`, inside the same `wait_for`.
  - `submit` stays inside the `try`, so a shut-down executor's `RuntimeError` is still mapped and logged as it was before.
  - After the cancellation, `future.cancel()` tells the two cases apart. When it returns True, the call was still queued: it was withdrawn and writes nothing (EC-57). When it returns False, the call was running, and `_log_late` is attached.
  - The `wrap_future` chain has already tried that cancel by the time the `except` runs. That holds for 3.11's `wait_for` (`_cancel_and_wait`) and for 3.12's timeout-based one.
  - `_log_late` is wrapped in `suppress(Exception)`, because `concurrent.futures` would otherwise log a raise with its text.
  - Independent check: `ProbeRC2` now prints one record for `thread/read` and one for `turn/start`. The R-10 tests passed 8 runs out of 8.
- **m-1.** Two one-line docstrings that name NG-13's limits.
- **m-2.** The decline values only. Naming the four method keys would add config keys past §8.4.
- **m-3. Not done.** §9.1 asks for `details["field"]` only on input records and on two named rows. `CodexServerAnswer`'s other two raises, which go through `_reject_wrong_type` and `_reject_bad_tuple`, set no details either. The text half needs S1 to decide INV-47's scope.
- **m-4 to m-7.** Follow-ups as routed.
- **Not a regression.** Ruff with its own defaults (there is no `[tool.ruff]` here, and 0.16.4's defaults include BLE001) reports 15 findings on the changed files before this iteration and 16 after. The new one is BLE001 at `reviews.py:146`, which is R-3's prescribed `except Exception`, the same as its two flagged siblings in `turn_events.py`. The repo's own ruff configuration is clean.
- **Not run.** The S4 engineering mutation plugin. This iteration edited `_end_lost_turn` and `handle`, so its mutant strings may no longer match (briefing: a tool artifact).

**Changes:** `df460ec7` R-1 · `a54163dc` R-2 · `4a3dd334` R-3 · `7a7dbd69` R-7 · `e4d21a7f` R-9 (lib helper) · `4de7eb60` R-9 (log calls) · `4882cb66` R-10 · `8bf92f33` m-1 · `31622c00` m-2

**Gate matrix out:**
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (area) | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS (1 failure, inherited) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 1046 passed, 3 skipped in 66.20s (0:01:06)` |
| lint | `"$V" lint/run.py` | PASS | `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| ruff (repo config) | `ruff check <23 changed .py> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache` | PASS | `All checks passed!` |
| semgrep | `semgrep-core.exe -rules .semgrep/typed-mapping-boundary-policy.yml -lang python -json <file>` × 23 | PASS | `runs=23 results=0 errors=0`; positive control `runs=1 results=2 errors=0` |
| test contract | `git diff 6b59d390..HEAD -- tests` | PASS | 0 lines |
| full local gate (source) | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` | FAIL: 1, inherited (lint, compileall and the three check scripts pass) | `reasoning trace contracts: ok (182 tools, 55 shapes)` / `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `=========== 1 failed, 6577 passed, 27 skipped in 116.36s (0:01:56) ============` / `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| full local gate (package) | `"$V" scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| remote checks | `gh pr checks 1181` | none configured | `no checks reported on the 'feat/codex-host-first-class' branch` (exit 1), after pushing `c9150d63..31622c00` |

**Inherited failure.** `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` reads `vidbyte/lib/enums/failure.py` at the merge base with `origin/main` and expects 120 members. Main now has 167. `git diff origin/ai/resolve-pr-1055-comments...HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads/` is empty, so this branch cannot change the result. S0 recorded the same failure at the base.

**Still open:** none of R-1 to R-10. The minor follow-ups are m-2's method-key half, m-3, m-4, m-5, m-6 and m-7. None blocks.

## Iteration 2 — 2026-10-17 13:25 — agent report: reports/S5-repair-2.md
**Defects in:** R-11 (Blocker) and R-12 (Major), from "Post-repair re-review round 1" in review.md, against spec r6 (`a0c9b489`) and the 11 red rows at S2_HEAD `68562b22`. Failing gates at `40b517da`: the area tests gave `12 failed, 1046 passed, 3 skipped`. That is 5 R-11 rows, 6 R-12 rows, and the inherited `harness_threads` surface failure. Lint passed. The test-contract base for this iteration is `68562b22`, not the `6b59d390` named in the gate set above.

**Hypotheses and attempts:**
- **R-11, chosen: the spec's row 12 fix.** `start` now awaits `asyncio.wait_for(asyncio.wrap_future(future), bound)`, as `call` does, with no `asyncio.shield`.
  - On 3.11.0, `wait_for` cancels the wrapper itself on both hand-overs: `_cancel_and_wait` on a timeout, and the cancelled task on a cancel. So `_copy_future_state` returns at `if dest.cancelled()`, and `_call_set_state` returns early on a closed loop.
  - `_hand_over` is unchanged, so the R-10 order holds: the record is registered first, then `_post_late`.
  - A queued start is still withdrawn. The wrapper's `_call_check_cancel` cancels it, and `_hand_over`'s `future.cancel()` then returns True.
  - It worked first time.
- **Rejected before starting** (the test author's in-memory variant runs): Alternative A ("keep the shield plus `waited.cancel()`") fixes R-11 only, and Alternative B (the `_consume` done-callback) still leaks on the closed-loop row. I did not try either.
- **R-11, independent check.** My own probe, `scratchpad/s5-repair-2/probe_r11_start.py`, drives the real `start` on a hand-built connection. The verifier's `probe_s5v_model.py` and `probe_s5v_race.py` can no longer import, because they rewrite `start`'s source by matching the old shield line (a tool artifact).
  - **The matrix:** cancel or timeout, a late failure or a late success, the loop open or closed first, and the race window on or off (`wait_for` raises, then the worker lands and the loop runs 0.2 s before `start`'s `except`), plus a queued start.
  - **Fixed code:** each of the 16 rows writes exactly one INV-7 record. The queued start sends nothing and writes nothing. No row has an ERROR on `asyncio` or `concurrent.futures`.
  - **Positive control** (`R11_CONTROL=1` puts the shield back in memory): 10 rows leak. Six are `asyncio` "Future exception was never retrieved", each with the canary. Four are `concurrent.futures` "exception calling callback", two with the canary. The other two are late successes on a closed loop, which leak no text but are ERROR records all the same.
  - **The whole suite:** the verifier's session counter (`-p s5v_patch_plugin`, no variant) over `tests/features/codex_host` gives `S5V stray ERROR records on asyncio/concurrent.futures: 0`. The verifier counted 2 on the iteration-1 code.
- **The other shields.** I checked them: `host.py:461` shields `turn.ended`, and `connection.py:595` shields `reap()`. Each future only ever gets `set_result` (`turns.py:151`, `connection.py:586`), so neither can strand an exception. Both stay.
- **R-12, chosen: the spec's row 9 fix in `describe`.** `"_".join(origin.split())` runs over the whole `basename:function:line` string. The colons and the line number never hold whitespace, so this replaces exactly the runs inside the two names, except a run at the very start of the basename, which `split` drops. One more expression puts that run back as `_`, so the code matches "each run … becomes `_`" with no exception. It uses str methods only, with no `re` (row 9: "Stdlib `traceback` and `os.path` only").
  - **Rejected:** `LogToken.of` at the call sites, which rewrites `<module>` and fails the 2 unit rows (briefing).
- **R-12, independent check.** `scratchpad/s5-repair-2/probe_r12_origin.py`:
  - `<frozen_os>:__getitem__:678` and `<frozen_genericpath>:_check_arg_types:152`;
  - `my_script.py:<module>:1`, also with a tab-and-space run in the name;
  - a leading run gives `_lead.py`, a trailing one `trail.py_`, and in a function name `_f`, `f_` and `read_the_setting`;
  - `<lambda>` and `<genexpr>` are unchanged;
  - a re-raise through `Future.result()` still names `boom`, and a never-raised exception gives `""`.
- **Lint printed `S063 IMPROVED 4 -> 3`.** S063 checks `asyncio.gather(..., return_exceptions=True)`. Neither changed file contains `gather`, and this iteration changed only those two files, so the improvement comes from elsewhere. It is not a failure, and I did not lower the baseline (briefing: no `lint/` edits).
- **Ruff I001 over the whole `vidbyte` tree** (the field guide's check) finds 223 findings in 217 files. None is in a file this PR changes (`comm -12` gives 0), so they are inherited. lint's S051 ratchet passes.

**Changes:** `8e5c649b` R-11 · `b40b6562` R-12. Fix pushes: `0348766d..b40b6562`.

**Gate matrix out** (`V` as above; HEAD `b40b6562`):
| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests (area) | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS (1 failure, inherited) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 1057 passed, 3 skipped in 67.23s (0:01:07)` |
| lint | `"$V" lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline` / `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` / `SDK-LINT: PASS` |
| ruff (repo config) | `ruff check <23 changed .py> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache` | PASS | `All checks passed!` |
| semgrep | `semgrep-core.exe -rules .semgrep/typed-mapping-boundary-policy.yml -lang python -json <file>` × 23 (`scratchpad/s5-repair-2/run_semgrep.py`) | PASS | `runs=23 results=0 errors=0`; positive control `runs=1 results=2 errors=0` |
| comment width | `scratchpad/s5r1_wide_comments.py origin/ai/resolve-pr-1055-comments`, restricted to `vidbyte/` | PASS | 0 lines under `vidbyte/` (the 195 in `tests/` are S2's) |
| test contract | `git diff 68562b22..HEAD -- tests` | PASS | 0 lines |
| full local gate (source) | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` | FAIL: 1, inherited (lint, compileall and the three check scripts pass) | `reasoning trace contracts: ok (182 tools, 55 shapes)` / `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `=========== 1 failed, 6588 passed, 27 skipped in 117.49s (0:01:57) ============` / `CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| full local gate (package) | `"$V" scripts/run_ci.py --stage package` | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.3.0 passed smoke checks.` / `CI passed.` |
| remote checks | `gh pr checks 1181` | none configured | `no checks reported on the 'feat/codex-host-first-class' branch`, after pushing `0348766d..b40b6562` |

**Inherited failure.** It is unchanged from iteration 1. `git diff origin/ai/resolve-pr-1055-comments...HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads/` is still 0 lines, and the assertion is still `assert len(main_members) == 120` (main has 167).

**Still open:** none of R-1 to R-12. m-8's status cell in review.md still reads "open". The briefing says spec r6 fixed it, and this iteration may write only the R-11 and R-12 cells, so the orchestrator should close it. The minor follow-ups are unchanged: m-2's method-key half, m-3, m-4, m-5, m-6 and m-7.
