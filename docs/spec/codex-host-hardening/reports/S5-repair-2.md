# S5 repair, iteration 2 of 8: codex-host-hardening (slice 1 of 2)

- **Branch and PR:** `feat/codex-host-first-class`, draft PR #1181. It stacks on `origin/ai/resolve-pr-1055-comments` (#1178).
- **The run:** it started at HEAD `40b517da` and ended at `b40b6562` for the fixes, plus one docs commit after that. The contract was spec r6 (`a0c9b489`) and the tests at S2_HEAD `68562b22`.
- **The interpreter:** `V` = `scratchpad/venv-codex163/Scripts/python.exe`, CPython 3.11.0 with openai-codex 0.163.0, editable from this worktree.

## Result

Both open confirmed findings are fixed, each with the fix the spec prescribes, one commit each, and no test changed. Every gate is green apart from the one inherited failure, which this branch cannot affect.

| ID | Severity | Commit | Root cause | Fix |
|---|---|---|---|---|
| R-11 | Blocker | `8e5c649b` | The `asyncio.shield` around `start`'s `wrap_future`. On a cancel or timeout hand-over, `wait_for` cancelled only the shield's outer future, so a late failure was copied onto the inner wrapper, which nothing read. asyncio then logged "Future exception was never retrieved" with the text in `exc_info`. On a closed loop, `concurrent.futures` logged a callback error with the same text. | `start` awaits `asyncio.wait_for(asyncio.wrap_future(future), bound)`, the shape `call` has (spec row 12). The FILE header and the `@intent` narration drop "shielded", and a short comment and a KNOWN EDGE CASES line say why there is no shield. |
| R-12 | Major | `b40b6562` | `ExceptionOrigin.describe` wrote the file basename and the function name as they are. So `<frozen os>`, or any name with whitespace, split `origin=` into two tokens. | `describe` turns each whitespace run in either name into one `_`, using str methods only, inside the helper that owns the format (spec row 9, INV-7). The KNOWN EDGE CASES line row 9 names is added. |

## Gate matrix (all run in this worktree, this iteration, at `b40b6562`)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| area tests | `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` | PASS (1 failure, inherited) | `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`<br>`1 failed, 1057 passed, 3 skipped in 67.23s (0:01:07)` |
| lint | `"$V" lint/run.py` | PASS | `S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline`<br>`S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`<br>`SDK-LINT: PASS` |
| ruff (S051 selectors, the 23 changed `.py`) | `"$V" -m ruff check <files> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache` | PASS | `All checks passed!` |
| semgrep (per file) | `semgrep-core.exe -rules .semgrep/typed-mapping-boundary-policy.yml -lang python -json <file>` × 23, through `scratchpad/s5-repair-2/run_semgrep.py`, which strips the progress dots | PASS | `runs=23 results=0 errors=0`<br>positive control on `.semgrep/typed-mapping-boundary-policy.py`: `runs=1 results=2 errors=0` |
| comment width (72 columns, no lint rule) | `scratchpad/s5r1_wide_comments.py origin/ai/resolve-pr-1055-comments` | PASS for `vidbyte/` | 0 lines under `vidbyte/`. The 195 lines are all in `tests/`, which S2 owns and this agent may not edit. |
| test contract | `git diff 68562b22..HEAD -- tests` | PASS | 0 lines |
| full gate, source stage | `PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` | FAIL: 1, inherited | `reasoning trace contracts: ok (182 tools, 55 shapes)`<br>`FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`<br>`=========== 1 failed, 6588 passed, 27 skipped in 117.49s (0:01:57) ============`<br>`CI failed: Command failed with exit code 1: …python.exe -m pytest` |
| full gate, package stage | `"$V" scripts/run_ci.py --stage package` (no PYTHONPATH, run after the source stage) | PASS | `No broken requirements found.`<br>`Installed vidbyte-sdk 0.3.0 passed smoke checks.`<br>`CI passed.` |
| remote checks | `gh pr checks 1181` | none configured | `no checks reported on the 'feat/codex-host-first-class' branch`. The push was `0348766d..b40b6562`, and the workflows run only on `workflow_dispatch`. |

**Notes on the matrix**
- **The area totals.** 1057 passed is iteration 1's 1046 plus the 11 new rows, the target the briefing named.
- **The source-stage totals.** 6588 passed is iteration 1's 6577 plus the same 11 rows.
- **Lint, compileall and the three check scripts** all pass inside the source stage.

**The inherited failure.** It reads `vidbyte/lib/enums/failure.py` at the merge base with `origin/main`, and asserts `len(main_members) == 120`, where main has 167. `git diff origin/ai/resolve-pr-1055-comments...HEAD -- vidbyte/lib/enums/failure.py tests/features/harness_threads/` is 0 lines, re-checked this iteration. S0 and iteration 1 recorded the same failure at the base.

## R-11: what I did, with evidence

**Reproduced.** `-k "CodexCallRecordTests"` at `40b517da`: the 5 R-11 rows failed, as did the 6 R-12 rows in the same selection (`11 failed, 9 passed`).

**Choosing the fix.** The spec prescribes it (row 12, INV-10, EC-58), and the log shows the two alternatives already failed:
- "shield + `waited.cancel()`" fixes R-11 only.
- `_consume` still leaks on the closed-loop row.

So the three candidates were the spec's no-shield await, A and B. I chose the no-shield await. A and B were rejected on the test author's recorded runs, and I did not try them again.

**Why it works on 3.11.0.** `wait_for` cancels the `wrap_future` wrapper itself on both hand-overs:
- **timeout:** `_cancel_and_wait(fut)`;
- **cancel:** the cancelled task cancels `fut`.

When the worker later lands:
- `_copy_future_state` returns at `if dest.cancelled()`;
- `_call_set_state` returns early, because a cancelled destination on a closed loop never reaches `call_soon_threadsafe`.

So no exception is ever stored on an asyncio future, and no callback raises.

**What is unchanged.**
- **`_hand_over`.** The record callback is still registered before `_post_late` (R-10's order, AGENTS.md §1).
- **A queued start.** The wrapper's `_call_check_cancel` cancels the worker future, and `_hand_over`'s `future.cancel()` then returns True. Nothing was sent and nothing is written (EC-57).

**Tests.**
- `-k "CodexCallRecordTests or InFlightStart"` over the observability and review-gaps files gives `11 passed`. That includes #1178's `test_a_failed_in_flight_start_frees_its_thread_when_it_returns`, which used to trip the leak silently.

**Independent check 1: my probe of the real `start`** (`scratchpad/s5-repair-2/probe_r11_start.py`, hand-built connection).
- **The matrix:**
  - cancel or timeout;
  - a late failure or a late success;
  - the loop open or closed first;
  - the race window on or off (`wait_for` raises, then the worker lands and the loop runs 0.2 s before `start`'s `except`);
  - plus a queued start.
- **On the fixed code, each of the 16 rows** writes exactly one INV-7 record:
  - the cancel hand-over's late DEBUG or WARNING;
  - or, for a timeout, the timeout's WARNING alone.

  The queued start gives `sent=[] own=[]`. No row has a stray ERROR. The only stray is asyncio's DEBUG `Using proactor: IocpProactor`, which carries no text.
- **Positive control** (`R11_CONTROL=1` rebuilds the shielded await in memory): 10 rows leak.
  - Six are `('asyncio', 'Future exception was never retrieved', True)`.
  - Four are `('concurrent.futures', 'exception calling callback for <Future …', True/False)` on the closed loop. The two `False` rows are late successes: no text, but still an ERROR record.

**Independent check 2: the whole suite.** The verifier's session counter, `-p s5v_patch_plugin` with no `S5V_VARIANT`, ran over `tests/features/codex_host` on the real code and printed `S5V stray ERROR records on asyncio/concurrent.futures: 0`. The verifier counted 2 on the iteration-1 code.

**The other shields.** I checked the other two `asyncio.shield` uses for the same pattern:
- `host.py:461` shields `turn.ended`;
- `connection.py:595` shields `reap()`.

Their futures only ever get `set_result` (`turns.py:151`, `connection.py:586`), so neither can strand an exception. Both stay: they protect a future other readers share, and the spec does not touch them.

**What the change touched** (connection.py, +9/−5):
- the await itself;
- a four-line comment above it saying why there is no shield (72-column check: 69, 70, 70 and 54);
- the `@intent` text, now "awaited the way every call is" (72 and 72);
- the header PURPOSE, where "shielded spending starts" became "spending starts";
- one KNOWN EDGE CASES sentence.

## R-12: what I did, with evidence

**Reproduced.** At `40b517da` the 2 unit rows and 4 record rows failed: `'my script.py:<module>:1' != 'my_script.py:<module>:1'`, and `origin=my` / `handler.py:read_setting:2` split into two words.

**Choosing the fix.**
- **(a) `"_".join(origin.split())` over the whole `basename:function:line` string.** This is the review's suggestion. The colons and the line number never hold whitespace, so it replaces exactly the runs inside the two names, but it drops a run at the very start of the basename instead of replacing it.
- **(b) (a) plus putting a leading run back as `_`.** One expression.
- **(c) `LogToken.of` at the call sites.** Rejected: it rewrites `<module>` and fails the 2 unit rows.

I chose (b). INV-7 and row 9 say "each run of whitespace … becomes `_`", and (b) matches that with no exception for one more line. It uses str methods only, with no `re`, which keeps row 9's "Stdlib `traceback` and `os.path` only".

**Tests.** `test_codex_host_hardening_contract.py` and `test_codex_host_observability.py` together give `48 passed`.

**Independent check** (`scratchpad/s5-repair-2/probe_r12_origin.py`). Every row is one token, and none carries the exception's text:

| Frame | Origin |
|---|---|
| `os.environ[...]` | `<frozen_os>:__getitem__:678` |
| `os.path.join("a", None)` | `<frozen_genericpath>:_check_arg_types:152` |
| file `my script.py` | `my_script.py:<module>:1` |
| file `my \t  script.py` | `my_script.py:<module>:1` |
| a leading run in the file name | `_lead.py:<module>:1` |
| a trailing run in the file name | `trail.py_:<module>:1` |
| runs in the function name | `plain.py:_f:2`, `plain.py:f_:2` and `plain.py:read_the_setting:2` |
| `<lambda>` and `<genexpr>` | unchanged |
| a re-raise through `concurrent.futures.Future.result()` | names `boom` |
| never raised | `""` |

**What the change touched** (exception_origin.py, +10/−4):
- `describe`'s body: the origin is built, then joined, with a four-line comment;
- its docstring, which now says "one … token";
- the FUNCTION INVENTORY, which says "one … token";
- the KNOWN EDGE CASES line row 9 names.

**Budget.** §8.4 is unchanged: 0 new files, classes, config keys, messages or dependencies.

## "Gets right" items the fixes touched, re-checked

- **R-10's done-callback order.** `_hand_over` is unchanged, so the record is registered before `_post_late`.
- **`ExceptionOrigin`.** It is still a static-method class in `lib/util/` with no new import, and A006 passes inside lint.
- **File sizes.** `connection.py` is 604 lines and `host.py` is still 927, both under 1,000. `host.py` is untouched.
- **The 72-column rule.** No `vidbyte/` comment line the PR added is over 72 columns. Each `@intent` stays on the first comment line of its `def`, and A002 passes.
- **No suppression, baseline or config change.** No lint, semgrep, scripts or CI file changed.

## Test changes proposed

None. No test contradicts the spec. `git diff 68562b22..HEAD -- tests` is 0 lines.

## Disputed findings

None.

## Observations, none of them a failure

- **Lint's `S063 IMPROVED 4 -> 3`.** S063 checks `asyncio.gather(..., return_exceptions=True)`. Neither file this iteration changed contains `gather`, so the improvement is not from this iteration. I left the baseline alone (no `lint/` edits). Lowering it is a separate ratchet-down someone could take later.
- **Ruff I001 over the whole `vidbyte` tree.** It reports 223 findings in 217 files. None is in a file this PR changes (the `comm -12` intersection is 0), so they are inherited. lint's S051 ratchet passes.
- **The verifier's in-memory candidates no longer import.** `probe_s5v_model.py` and `probe_s5v_race.py` rewrite `start`'s source by matching the old shield line, so they fail at import now that the line is gone. That is a tool artifact. `probe_r11_start.py` replaces them, and its `R11_CONTROL=1` switch keeps a working positive control.
- **m-8.** Its status cell in review.md still reads "open: trivial …". The briefing says spec r6 fixed it, and this iteration may write only the R-11 and R-12 cells, so the orchestrator should close it.

## What remains open

- **Confirmed findings:** none. R-1 to R-12 are all fixed.
- **Gates:** only the inherited `harness_threads` surface failure.
- **Minor follow-ups:** unchanged as routed: m-2's method-key half, m-3, m-4, m-5, m-6 and m-7.
