LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — R-11, R-12 and m-8 hold with no regression, and the budget, scope and boundaries match the spec exactly; one Minor docs gap is left (FR-36 against search_codex_threads), and the PR can merge without it.

Run: `codex-host-hardening`, slice 1 of 2, draft PR #1181. S5 re-review, round 2 of 2.
Reviewed: `127173b5`, which is the worktree HEAD `9c958640` minus two docs-only commits (`pipeline.md`, `review.md`).
Diff base: `origin/ai/resolve-pr-1055-comments`.

## ROUND-1 FIX CONFIRMATION

| Fix | Commit | Claimed in review.md | Independent check | Result |
|---|---|---|---|---|
| R-11 (Blocker): a handed-over start's late failure was logged by asyncio or concurrent.futures, with its stderr or RPC text | `8e5c649b` | `start` awaits `asyncio.wait_for(asyncio.wrap_future(future), bound)` with no shield (`connection.py:417`). A late outcome is read only from the worker's future. | (1) The repair probe matrix (`s5-repair-2/probe_r11_start.py`) gives one own record in all 16 rows and no stray record. The queued row gives `sent=[] starting_after=[] own=[]`. (2) With the shield put back in memory (`R11_CONTROL=1`), 10 rows leak: 6 are asyncio "Future exception was never retrieved" with the canary, and 4 are concurrent.futures "exception calling callback". (3) The verifier's host probe reports `RECORDS: 0` for RC1-A, RC1-B and RC1-C (`23 passed`). (4) The area run with the stray counter gives `S5V stray ERROR records on asyncio/concurrent.futures: 0`. (5) The tests can fail: with `RR2_REVERT=shield`, 5 tests fail, which are the five R-11 rows of `CodexCallRecordTests` (cancel-fail, timeout-fail, death, host close, loop closed). With no revert, all 20 pass. | **CONFIRMED** |
| R-12 (Major): `ExceptionOrigin.describe` could emit whitespace, which split the `origin=` token | `b40b6562` | Each whitespace run is joined with `_`, and a leading run is kept as `_` (`exception_origin.py:37-38`). | (1) Edge cases checked: plain, space, tab and newline, leading run, trailing run, NBSP, U+2028, `\x1f`, a whitespace function name, `<lambda>`, `<genexpr>`, frozen `os`, and an exception never raised. Each gives one token with no whitespace. `<module>`, `<lambda>` and `<genexpr>` stay unchanged. U+200B is not whitespace, so it is kept, and the result is still one token. (2) On the host, `origin=<frozen_os>:__getitem__:678` appears in both the router fallback and the tool failure, and no token lacks `=`. (3) With `RR2_REVERT=origin`, 6 tests fail: 4 origin rows of `CodexLogTokenRecordTests` and 2 of `CodexExceptionOriginTests`. (4) The module still imports only `os` and `traceback` (§12.3 row 9). | **CONFIRMED** |
| m-8 (Minor): the spec said the record was registered after `_post_late`, the reverse of the code | spec r6 `a0c9b489` | INV-7 (`spec.md:261`) and §12.3 row 12 now say the record's done-callback is registered before `_post_late`'s. | The code at `connection.py:494-499` does `cancel()` → `_starting.add` → `add_done_callback(record)` → `add_done_callback(_post_late)`. The spec text now matches it. review.md marks m-8 "fixed @a0c9b489". | **CONFIRMED** |

## REGRESSION CHECKS (R-11 removed the shield)

These rows come from my own host-level probe, `scratchpad/s5-rereview-2/probe_rr2_regressions.py`. It drives a real `CodexHost` on the fake app-server, with one worker thread, and also captures the asyncio and concurrent.futures loggers.

| Row | Requirement | Observed | Holds |
|---|---|---|---|
| Q: the start is still queued when its spawn is cancelled | EC-57: withdrawn, never sent, no record | `outcome=cancelled turn/start sent=0 records=[] starting=False tools before=True after=False strays=[]` | yes. `wait_for` cancels the wrapper, and `_chain_future._call_check_cancel` then cancels the source, so `_hand_over`'s `future.cancel()` returns True. The tools are released because the start never ran. |
| R: the start is running when its spawn is cancelled | INV-26 / EC-23: handed over, adopted, tools kept, one interrupt, one record | `starting_at_cancel=True tools_at_cancel=True adopted_tool_answer_success=True interrupts=1 records=[('codex_host_call','')] starting_after=False strays=[]` | yes |
| T: the start times out, then Codex accepts it late | INV-7: exactly one record; adopted and interrupted | `codex.api_error retryable=True`; `records_at_timeout` = `records_after_landing` = `[('codex_host_call_failed','codex.api_error')]`; `starting_at_timeout=True`, tools kept, `interrupts=1`, `strays=[]` | yes. The timeout path passes `record=None` (`connection.py:422`), because `_log_call` has already logged. |
| TF: the start times out, then Codex fails it late | INV-7, INV-10: one record, no stray | one record, `interrupts=0`, `strays=[]` (the canary RPC text appears nowhere) | yes |

## WHAT THE IMPLEMENTATION GETS RIGHT

- Without the shield, a caller that leaves cancels the loop-side wrapper. A late outcome then reaches only the worker's `concurrent.futures.Future`, which `_log_late` and `_post_late` read. This closes both leak routes (an open loop and a closed loop) while keeping the EC-57 withdrawal: `connection.py:410-422, 483-499`.
- Every start writes exactly one record. A cancelled start registers its record before the post. A timed-out start passes `None`, and a queued start writes none. These are all verified on the host (rows Q, R, T and TF), not only on the hand-built connection.
- `describe` gives a single token for every whitespace class, and it changes nothing in the normal case (`file.py:func:line`, `<module>`, `<lambda>`), so earlier INV-8 records keep their format.
- Budget and scope match exactly.
  - Budget: 3 new files, 14 new classes, 0 dependencies, 11 config keys and 13 messages (an AST diff against base). `codex.py` loses 2 constants and gains none.
  - Scope: the 25 changed non-doc, non-test files are exactly the 25 rows of §12.3. `lint`, `.semgrep`, `scripts`, `.github`, `REPO_MAP.md`, the harness README and `codex/__init__.py` are unchanged.
  - Tests: they were changed only by S2's commits. `git diff 68562b22..127173b5 -- tests` is empty.
  - §4 snippet: it runs verbatim and prints `completed`, `1`.

## FINDINGS

R-C1 [Minor] [spec conformance / docs] vidbyte/harnesses/native/codex/host.py:617 — `search_codex_threads`, the accepted row 16–18 for title-only search, has no docstring.
- **Evidence.**
  - FR-36 (`spec.md:664`) says the accepted rows, including "16–18", "are documented in the docstrings of their functions". request.md:226 names those functions: `list_recent_codex_threads`, `list_codex_threads_since` and `search_codex_threads`, with the note "Search matches titles only." NG-10 (`spec.md:99`) is "rows 16–18 match titles only".
  - At `127173b5`, all three report `__doc__ is None` (checked with `CodexHost.<name>.__doc__` in the venv).
  - The title-only limit appears only in a code comment at `host.py:618-619`, which was added in `6f5a7310`, a commit already in the base. It also appears in the tool's `SEARCH_CODEX_THREADS_DESCRIPTION` (`vidbyte/tools/builtins/codex/descriptions.py:31`).
  - AC-39 (`spec.md:551`) and its test (`test_codex_host_hardening_contract.py:610`) check NG-10 on `list_codex_threads`, not on `search_codex_threads`. The spec therefore disagrees with itself (FR-36 against AC-39), and the gate cannot catch the gap.
- **Failure.** A developer who calls `CodexHost.search_codex_threads` directly gets no `help()` text. Nothing tells them that the query matches titles only, which is the very limitation FR-36 accepted on the promise that it would be documented. Agents using the tool are covered by the tool description, but developers calling the method are not.
- **Smallest fix.** Turn the two-line comment at `host.py:618-619` into a one-line docstring, for example `"""The threads whose title matches query, newest first; Codex matches titles only, not content (NG-10, D-6)."""`. Optionally add an AC-39 row `("search_codex_threads (NG-10)", ..., ("title",))`. This is +0 lines, and the class and file budget is untouched.
- **Spec IDs:** FR-36, NG-10, AC-39, request.md row 16–18.

There are no other findings.

**Checked and not raised:**
- A queued start whose bound runs out still writes the timeout WARNING. This predates the round, and EC-57 covers cancellation only.
- In 3.11, `wait_for` swallows a cancellation when the inner future has already finished. This predates the PR, and the shield had the same behaviour.
- The `shield` at `connection.py:599` (`reap`) and at `host.py:461` (`turn.ended`) wraps futures that only ever receive `set_result`, so it cannot leak text.
- Blank-line nits around `class CodexHost` and `class CodexPreflight`.

## CONFORMANCE PASS (whole PR diff)

- **IDs.**
  - FR / NFR / INV / AC / EC: walked against the code at `127173b5`. No gaps beyond R-C1.
  - INV-26, the tool kept while a start is in flight: `_release_tools` unregisters only when `not connection.starting(thread_id)`.
  - INV-27 to INV-33 also checked: the continue goal guard and the reviewer check without a handler; the fork record, then `_reject_experimental_fork_fields`, then `threads.fork`; `forget_codex_turns` guard, ref, `require_idle`, forget; the review request substituted only when it is None; the skill relabel; the skill cwd.
  - Row 19's `_end_running_turns` calls `router.cancel_pending()` first.
- **§12.3.** Each of the 25 rows maps to one changed file, and no file is changed outside them.
  - Size limits: `connection.py` 604 lines, `host.py` 927 lines (NFR-6 < 1,000; under the 940 target).
  - No module-level constant in any native module (C021).
- **request.md §A/§D, §4 and §5.**
  - The §4 snippet, read out of spec.md and run with `exec` unchanged (asyncio.run included), prints `['completed', '1']` with no errors. The fake records `approvalsReviewer=['user']` and `started_closed=(1, 1)`. `CodexApprovalSnippetTests`: 2 passed.
  - Every §5 edge has a matching call path: guard → record → `reject_user_reviewer` or run → call or start → `retry_on_overload` → mapper; router → `from_params` → handler → fits → `server_answer` or `default_answer`; `on_event`; `on_lost`; `complete_review`.
- **§8.4 budget.** It matches exactly: 3 / 14 / 0 / 11 / 13. The 24 constants added to `codex_host.py` are 11 config keys and 13 messages, which matches §9.2 and §9.3.
- **§14 "Never".**
  - No path outside §12.3 is touched, no dependency is added, and the tests are unchanged after S2.
  - No shield is left on a future that can fail.
  - No PR-added source comment is longer than 72 columns (awk over the added lines: 0).
- **Deviations.** None found beyond the ones the spec records.

## VERIFIED CLAIMS

1. **The repair fixes R-11 in all 16 rows (start matrix), and the control shows the old code leaking.** Re-ran `probe_r11_start.py`: 16/16 rows give one own record and no stray, and the queued row gives none. The `R11_CONTROL=1` control leaks in 10 rows, 6 of them with the canary.
2. **The area gate result is 1 failed (inherited), 1057 passed, 3 skipped, with 0 stray asyncio or concurrent.futures ERROR records.** Re-ran with the counter plugin: `1 failed, 1057 passed, 3 skipped in 67.08s`, counter 0. The one failure is the excluded harness_threads test.
3. **The new tests prove R-11 and R-12.** In-memory reverts (`rr2_revert_plugin.py`): `shield` makes 5 tests fail, `origin` makes 6 fail, and no revert gives 20 passed.
4. **A queued start is withdrawn, and a running start is adopted with its tools kept (EC-57, INV-26).** Host rows Q and R above.
5. **A timed-out start writes exactly one record (INV-7).** Host rows T and TF above.
6. **R-12's origin is one token on the host (INV-8, INV-10).** Host probe: `origin=<frozen_os>:__getitem__:678`, and no record has a token without `=`.
7. **The spec now matches the code for m-8.** Read `spec.md:261` and §12.3 row 12, then `connection.py:494-499`.
8. **The budget is 3 / 14 / 0 / 11 / 13, and the 25 files are the 25 rows.** AST diff against base, and `git diff --name-only` compared with the §12.3 table.
9. **The tests are unchanged after S2.** `git diff 68562b22..127173b5 -- tests` gives 0 lines, and `git log -- tests` shows only ba4e9dfc, fadec47f, 75bfae7d and 48228a1d.
10. **The lint gate passes.** `lint/run.py` gives `SDK-LINT: PASS`. The ratchet notes are not findings.
11. **AC-1 holds.** The §4 snippet runs verbatim (see the conformance pass).

## COMMANDS RUN

`V=…/scratchpad/venv-codex163/Scripts/python.exe`. All probes live under `scratchpad/s5-rereview-2/` or are earlier stage scratch files. Every command was run with `PYTHONDONTWRITEBYTECODE=1`.
- `git diff efb19043..127173b5 -- vidbyte`
- `git diff origin/ai/resolve-pr-1055-comments...127173b5` (full, `--name-only`, `-U0`)
- `git diff 68562b22..127173b5 -- tests | wc -l` → 0
- `git log -- tests`
- `git diff origin/ai/resolve-pr-1055-comments...127173b5 -- lint .semgrep scripts .github REPO_MAP.md vidbyte/harnesses/README.md vidbyte/harnesses/native/codex/__init__.py` → empty
- `git merge-base --is-ancestor 6f5a7310 origin/ai/resolve-pr-1055-comments` → true
- `git diff 9c958640 127173b5 --stat` → only `pipeline.md` and `review.md`
- `"$V" scratchpad/s5-repair-2/probe_r11_start.py`, then `R11_CONTROL=1 "$V" scratchpad/s5-repair-2/probe_r11_start.py`
- `"$V" -m pytest scratchpad/s5-verify/probe_s5v_host.py -k probe_ -s` → 23 passed, RECORDS: 0
- `"$V" -m pytest -p s5v_patch_plugin tests/features/codex_host …` (area with the stray counter) → `1 failed, 1057 passed, 3 skipped`, counter 0 (`area_with_counter.txt`)
- `"$V" -m pytest scratchpad/s5-rereview-2/probe_rr2_regressions.py -s` → rows Q, R, T and TF as tabled
- `"$V" -m pytest scratchpad/s5-rereview-2/probe_rr2_snippet.py -s` → `SNIPPET lines=['completed', '1'] errors=[]`
- `RR2_REVERT=shield|origin|"" "$V" -m pytest -p rr2_revert_plugin tests/features/codex_host/test_codex_host_observability.py tests/features/codex_host/test_codex_host_hardening_contract.py -k "CodexCallRecordTests or CodexLogTokenRecordTests or CodexExceptionOriginTests" -rf` → 5 failed / 6 failed / 20 passed
- `"$V" -m pytest tests/features/codex_host/test_codex_host_approvals.py -k CodexApprovalSnippetTests` → 2 passed
- `"$V" -c` probes of `ExceptionOrigin.describe` (the whitespace classes) and of `CodexHost.<list/search>.__doc__`
- An AST budget diff of new files, classes and constants against base
- `"$V" lint/run.py` → `SDK-LINT: PASS`
- An awk count of PR-added source comment lines longer than 72 columns → 0
- `git status --short` → clean (the worktree is untouched, apart from this report)

Not re-run by me; these are the briefing's values: ruff (TID251), semgrep through `semgrep-core.exe`, source stage `1 failed, 6588 passed, 27 skipped`, package stage `CI passed.`
