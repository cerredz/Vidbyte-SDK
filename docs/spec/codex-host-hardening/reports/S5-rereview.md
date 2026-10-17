LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — Every R-1…R-10, m-1 and m-2 fix holds against its own review.md evidence, and none introduced a behaviour regression. But the R-10 hand-over path still lets asyncio write exception text, including Codex's stderr tail, into an ERROR log record, which breaks INV-10's privacy rule; and an exception origin can still render as two tokens, which breaks INV-10's one-token rule.

Reviewed: `git diff origin/ai/resolve-pr-1055-comments...efb19043` (code unchanged at HEAD `0348766d`, which differs only in `pipeline.md`), with the full-review pass over `git diff c9150d63..efb19043 -- vidbyte` (14 files). Spec r5 read in full; request.md §A–§D, AGENTS.md, review.md, verify-log.md, the S3, S4-conformance and S5-repair reports read.

FIX CONFIRMATION (one row per fixed finding; each re-runs that finding's own check from review.md)

| Finding | Commit | Evidence re-run | Held |
|---|---|---|---|
| R-1 | `df460ec7` | review.md's check, `awk 'length($0) > 72' <file> \| grep -E '^\s*#'`, over the six files gives 0 in host, thread_helpers, turn_events and dataclasses/codex_host. base.py gives 11, and all 11 are pre-existing (base also has 11; c9150d63 had 12). A `git diff -U0 base...efb19043 -- vidbyte` scan of every PR-added comment line wider than 72 finds **0**. The re-filled blocks keep their words. | yes |
| R-2 | `a54163dc` | `CODEX_HOST_ANY_MODEL_TEXT` and `CODEX_HOST_FORK_EXPERIMENTAL_FIELDS` are in lib and its sorted `__all__`. preflight.py:206 and host.py:747-748 read them. An AST diff of every string literal in native function bodies (base vs efb19043) finds only wire keys, the INV-8 labels (m-4) and cast strings: no message text or field tuple. `lint/run.py --rule C021` gives `0 0 CLEAN`. | yes |
| R-3 | `4a3dd334` | The verifier's own probe (`s4-verify/probe_s4v_code.py::ProbeRC1`) now prints `RC1 FIRST REVIEW: returned`, `RC1 REGISTRY RUNNING: []`, `RC1-LATE PENDING TASKS: 0` and `RC1-LATE SECOND REVIEW: returned`. In-memory undo (`CodexTurnEvents.fail` re-raises) fails `CodexReviewCompletionFailureTests` 3/3; the control passes 3/3. | yes |
| R-4 | `75bfae7d` (test) | Passes in the area run (1046 passed). | yes |
| R-5 | `75bfae7d` (test) | `CodexForgetTurnsTests` passes 5 of 5 runs. | yes |
| R-6 | `75bfae7d` (test) | `CodexSpawnCleanupTests` passes 5 of 5 runs. | yes |
| R-7 | `7a7dbd69` (spec `be733a0b`, tests `75bfae7d`) | Built directly: `CodexGoalRunRequest(goal=…, request=CodexSpawnRequest(turn=CodexTurnSettings(model="m")))` raises `run_codex_goal request does not use the field turn, because Codex starts goal turns itself with the thread's settings; leave turn at its default, or set the matching thread setting.` with `field: turn`, which is §9.2's example verbatim. The spawn text is unchanged from r4. | yes |
| R-8 | `75bfae7d` (test) | `CodexLostWatcherTests` passes 5 of 5 runs. | yes |
| R-9 | `e4d21a7f`, `4de7eb60` | `ProbeRE1` now prints `RE1 LINES: 1` (the forged `itemId` is one token, with the true `handled_by=default answer=decline`) and `RE1 LONG RECORD CHARS: 268`. All 9 host and tool log calls pass every Codex- or caller-chosen id through `LogToken.of`. Both INV-10 examples reproduce exactly, and the function is idempotent. In-memory undo (`LogToken.of` = identity) fails `CodexLogTokenRecordTests` (22 subtest failures). | yes, for ids. The `origin` field is still not one token: see R-C2 |
| R-10 | `4882cb66` | `ProbeRC2` now prints one record each: `thread/read … records: [{'operation': 'read_codex_thread', …}]`, `turn/start … records: [{'operation': 'spawn_codex_thread', …}]`, `adopted turns: ['turn-2']`. In-memory undo (`_log_late` = no-op) fails exactly the two red-regression tests (4 subtests); the timeout and refused-before-send guards stay green. | yes, for the record. The same hand-over path still leaks text through asyncio: see R-C1 |
| m-1 | `8bf92f33` | `run_codex_skill` and `run_codex_openai_docs` docstrings name "no images, no mentions and no second skill" (NG-13). | yes |
| m-2 | `31622c00` | Both routed default rows read `CodexApprovalDecision.DECLINE.value`; the AC-40 dict comparison passes. | yes |

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **R-10's ordering is correct on every branch.** In `call`, the `wrap_future` chain has already tried `future.cancel()` when the `except asyncio.CancelledError` runs (3.11 `wait_for` → `_cancel_and_wait` → `_call_check_cancel`). So `not future.cancel()` cleanly separates a queued call (withdrawn; no record, EC-57) from a running or finished one (`_log_late` attached, or run at once). In `_hand_over`, the record is registered before `_post_late`, so `concurrent.futures` writes it first on the same thread. A closed loop cannot drop it, `_log_late` swallows everything (so `concurrent.futures` never logs a callback raise with its text), and the timeout branch passes `None`, so there is no second record.
- **R-3 cannot swallow a cancellation and ends the review exactly once.** The new `try` at reviews.py:144-147 wraps two synchronous calls with no `await`, so no `CancelledError` can arise inside it. `CodexTurnRegistry.finish` is first-wins, so `events.fail` cannot end the review twice. The late path returns its handle and leaves no task pending (ProbeRC1-LATE).
- **R-9's helper matches INV-10.** `LogToken.of` maps only `value[:limit]`. That gives the same result as mapping first and then cutting, because each character maps to exactly one. Routing (`self._handlers.get(thread_id)`), answers and errors keep the raw values. The claim that the router's `method` is always a `str` holds: openai-codex returns `{}` before calling the handler when it is not (`client.py:889`).
- **The budget and scope are exact.** 3 new files, 14 classes, 11 config keys plus 13 messages (by AST diff), 0 dependencies and 2 removals. The 25 changed non-test, non-docs files are exactly the 25 §12.3 rows. Nothing changed under lint, .semgrep, scripts or .github. `git diff 6b59d390..efb19043 -- tests` is empty. host.py is 927 lines, under 940.

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [request fidelity / INV-10 privacy] vidbyte/harnesses/native/codex/connection.py:413 — A spending start handed over on cancel or timeout that then fails makes asyncio log its exception text, including Codex's stderr tail, at ERROR
  Evidence:
  - `start` awaits `asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), bound)` (connection.py:413). On a hand-over (:417 on cancel, :423 on timeout), the shield's outer future is cancelled. CPython 3.11's `shield` then runs `_outer_done_callback`, which removes the inner future's callback. A late failure of the worker is copied onto the inner `wrap_future` future, and nothing retrieves it. When that future is collected, `Future.__del__` calls the loop's exception handler, which logs "Future exception was never retrieved" with `exc_info`, in debug mode or not.
  - Clean code, the R-10 test's own failure row: running `CodexCallRecordTests::test_a_spending_start_handed_over_on_cancel_writes_one_record_for_its_late_outcome` with a handler on the `asyncio` logger printed `asyncio record: ERROR 'Future exception was never retrieved…' | canary in exc_info text: True`, with the line `openai_codex.errors.InternalRpcError: JSON-RPC error -32603: store failed for rpc-canary-a3c5`. The test still passes, because `capture_logs(CONNECTION_LOGGER)` (test_codex_host_observability.py:372) and its `assert_no_canary` (:449) read only the connection logger.
  - Clean code, process death after a hand-over: an in-process HostTestCase probe held `turn/start`, cancelled the spawn, then ran `server.die("stderr-canary-user@example.com")`. It printed `PROBE asyncio record: ERROR 'Future exception was never retrieved' | stderr canary in record: True` and `openai_codex.errors.TransportClosedError: Codex process closed stdout. stderr_tail=stderr-canary-user@example.com`.
  - Minimal model of the same pattern, with `loop.set_debug(False)`: `[('ERROR', 'Future exception was never retrieved', True)]`.
  - The cause predates this PR: base `8baff351` connection.py:218 has the same line. But it sits on the exact hand-over path R-10 changed, and this PR is the one that makes logs a privacy surface (INV-10).
  Failure: A caller cancels, or a 300 s bound times out, `spawn_codex_thread`, `continue_codex_thread`, `launch_codex_subagents`, `start_codex_review` or a goal run while its spending start is in flight, and the start later fails. One case is a Codex JSON-RPC error. Another is the process dying, where `TransportClosedError` carries up to 2,000 characters of Codex stderr. The host's log pipeline then gets an ERROR record holding that exception's text and a traceback. That text is the stderr (and the account email) that codex-host INV-9 exists to keep out. It breaks INV-10 "No record carries … stderr …" and "never contain exception text", T-5's control "exc_info is never used", NFR-3, and NFR-1's "Zero exceptions escape … a loop callback": asyncio reports this exception as never retrieved. That is the user's weighted words, "exception handle everything that could potentially go wrong" (request.md §D).
  Smallest fix: In `start`, keep the wrapper (`waited = asyncio.wrap_future(future)`) and await `asyncio.shield(waited)`. When a start is handed over (both branches, only when `future.cancel()` returned False), also register a static `_consume(waited)` done-callback on `waited` that reads `waited.exception()` unless it was cancelled. `_land` already reads the concurrent future's outcome, so behaviour is otherwise unchanged. `call` needs nothing: its `wrap_future` has no shield, so `wait_for` cancels it.
  S2 row: in the R-10 failure row and in a death-after-hand-over row, also capture the `asyncio` logger, and assert no canary in `getMessage()` or in the formatted `exc_info`.
  Spec: one INV-10 (or INV-43) sentence: "a start handed over leaves no future whose exception is never retrieved".
  Spec IDs: INV-10, INV-42, INV-43, NFR-1, NFR-3, T-5, AC-18, FR-3, request.md §D

R-C2 [Major] [spec conformance / INV-10 record shape] vidbyte/lib/util/exception_origin.py:32 — An exception origin can render as two tokens, so four WARNING records split, against INV-10 "Each value renders as one token … That holds for … file.py:function:line"
  Evidence:
  - `return f"{os.path.basename(frame.f_code.co_filename)}:{frame.f_code.co_name}:{line}"`. On Python 3.11, the package's floor, `os`, `ntpath`, `genericpath`, `posixpath`, `stat`, `codecs`, `io`, `abc`, `_collections_abc` and `runpy` are frozen, and their `co_filename` is `<frozen os>` and so on. A developer script whose name has a space gives the same.
  - Run: `ExceptionOrigin.describe` of a `KeyError` from `os.environ[...]` gives `'<frozen os>:__getitem__:678'`. A `TypeError` from `os.path.join("a", None)` gives `'<frozen genericpath>:_check_arg_types:152'`.
  - Through the real `CodexServerRequestRouter`, with an async handler whose bug is `os.environ["…"]`, the record is `codex_host_server_request_fallback method=item/commandExecution/requestApproval thread_id=thr-1 reason=handler_failed error_type=KeyError origin=<frozen os>:__getitem__:678`. That is 6 tokens, one with no `=` (`os>:__getitem__:678`).
  - The spec exempts origins from `LogToken` as host-made (spec.md:293), and ExceptionOrigin's own header says "Keep the output one token with no spaces". Neither promise holds for these frames.
  - The tests' `log_fields` (codex_host_support.py:547) silently drops the orphan token, so it reads `origin` as `<frozen` and the suite stays green.
  Failure: A developer's approval handler, a host method under a tool (X8), an SDK call or a turn event raises from a frozen stdlib frame. The `codex_host_server_request_fallback`, `codex_host_tool_failed`, `codex_host_call_failed` or `codex_host_turn_event_failed` record then has a split `origin`, and any key=value log parser loses the root-cause location: the one field D-13 exists to keep. This is the same record-shape rule R-9 fixed for ids, and R-9's own calibration applies (Major: no forgery by a hostile peer, the answer is still correct).
  Smallest fix: Pass the origin through the existing helper at the four log calls: `LogToken.of(ExceptionOrigin.describe(exc), CODEX_HOST_LOG_TOKEN_MAX_CHARS)` at connection.py:195 (the fallback tuple's origin) and :456 (`_log_call`), turn_events.py:150, and tools/builtins/codex/_base.py:137. This needs no new constant or file. Normal origins (`connection.py:handle:171`) come back unchanged, so `CodexExceptionOriginTests` and the `count(":") == 2` checks stay green.
  Spec r6: drop "origins" from INV-10's "need not pass through it" list (spec.md:293), and note it in §12.3 rows 12, 17 and 22.
  S2 row: a handler raising `KeyError` from `os.environ[...]`; the fallback record's raw tokens all contain `=`, and its keys are exactly the five INV-8 keys.
  Spec IDs: INV-10, INV-8, INV-11, INV-23, D-13, T-5

R-C3 [Minor] [unrecorded deviation] vidbyte/harnesses/native/codex/connection.py:417, :493-495 — R-10's start record is its own done-callback, while row 12 and INV-7 say `_post_late` writes it, and the spec does not record the change
  Evidence:
  - Row 12 (spec.md:1330): "`start`'s cancel hand-over carries the operation, method and start time, and `_post_late` writes the record before it posts."
  - INV-7 (spec.md:261): "The done-callback that already posts the late outcome to the loop writes the record first."
  - The code passes `partial(self._log_late, …)` into `_hand_over`, which does `future.add_done_callback(record)` and then `future.add_done_callback(partial(self._post_late, …))`. `_post_late` is unchanged.
  - The reason (AGENTS.md §1: `_post_late → _log_late → _log_call` would be three deep) is recorded only in verify-log.md "R-10, start" (c) and the repair report. `grep -n "Implementation deviations" spec.md` finds only the S3 list (:1654).
  Failure: Behaviour is the same, because callbacks run in registration order on one thread. But the spec now describes a call shape the code does not have, and a later agent "fixing" the code to match row 12 would build the three-deep chain the repair rejected.
  Smallest fix: Add an "Implementation deviations (S5)" bullet that states the separate, earlier-registered callback and the §1 reason, or reword INV-7 and row 12 to say "a record callback registered before `_post_late`'s".
  Spec IDs: INV-7, §12.3 row 12

REGRESSION CHECKS (the three areas the briefing named)
- **R-10's done-callback path.**
  - Callback order relative to `_post_late`: record first (`_hand_over`: record, then post). Held.
  - An exception inside a callback: `_log_late` swallows `Exception`; `_post_late` swallows `RuntimeError`. Held.
  - A closed loop: `_log_late` never touches the loop. Held.
  - Double logging on the timeout path: `start` passes `None`; `call` attaches nothing on `TimeoutError`; the timeout guard test passes. Held.
  - Worker count, 1 in tests and 32 in production (`CODEX_HOST_WORKER_THREADS`): with more workers, a cancelled call is almost always running rather than queued, so it takes the `_log_late` branch, which the tests prove on the 1-worker host. `_log_late` runs on worker threads, and stdlib logging is thread-safe. Held.
  - `submit` stays inside the `try`, so a shut-down executor's `RuntimeError` is mapped as before. No regression.
  - Not a regression, but on this path: R-C1.
- **R-3's new `except` in reviews.py.** It does not swallow a cancellation (no `await` inside the `try`; `except Exception`). It ends the turn exactly once (first-wins `finish`; if `turn_snapshot` raised, no snapshot was set, so `fail` ends it). `fail` also sends one quiet interrupt to a review Codex already ended, which is INV-11's sequence and what INV-12 points to. Held.
- **R-9's `LogToken` application.** All 9 log calls were listed by grep. Every id that Codex or the caller chose is tokenized: the router's method and three ids, the `_log_call` thread id, the turn-item ids and type, and the handle ids in the turn-ended, lost and event-failed records. The answer label, operation, method constants, codes, status, reason and tool name are host-made. Raw values are still used for routing (`self._handlers.get(thread_id)`), answers and errors. Held for ids; `origin` is the gap (R-C2). Type names from a developer's handler (`type(reply).__name__`) are identifiers in practice and are exempt by spec.
- **m-3…m-7.** None made worse in kind. m-5's `handle` grew from 63 to 66 lines (the R-9 comment and `limit`), and S008 and the full lint still pass. Not re-raised.

VERIFIED CLAIMS:
1. S5 report: "the PR-added comment scan finds 0 lines in vidbyte/". HELD (my own diff scan: 0).
2. S5 report: "Budget … LogToken is the 14th class; 11 config keys; 13 messages; no new files". HELD (AST diff: 14 classes, 24 = 11 + 13 constants, 2 removed, 3 new files, all from S3).
3. S5 report: "25 non-test, non-docs files are changed: the 24 planned rows, plus text.py, which is row 25". HELD (25 = the 25 §12.3 paths; set differences are empty).
4. S5 report: "git diff 6b59d390..HEAD -- tests is empty". HELD. The tests changed in this window are S2's `75bfae7d` only; its removed lines are header refreshes and the R-7 `{owner}` pins.
5. S5 report: "openai-codex only routes a server request whose method is a str (client.py:886-893)". HELD (`if not isinstance(method, str): return {}` at :889).
6. S5 report: "a 100,000-character id gives a 268-character record; a forged itemId logs as one token". HELD (ProbeRE1 re-run).
7. S5 report: "ProbeRC1 prints the first review returned, RUNNING: []" and "ProbeRC2 prints one record each". HELD (re-run).
8. S5 report: "The wrap_future chain has already tried that cancel by the time the except runs (3.11 wait_for)". HELD, by reading 3.11 `wait_for`/`_cancel_and_wait`/`_chain_future`, and confirmed by the queued-call guard test.
9. Orchestrator gate: area tests `1 failed, 1046 passed, 3 skipped`, the 1 being the inherited harness_threads test. HELD (`1 failed, 1046 passed, 3 skipped in 65.96s`).
10. S5 report: lint `SDK-LINT: PASS`; ruff with the repo config clean; semgrep 0 results. HELD (lint, `--rule C021` CLEAN, `--rule S008` PASS; ruff `All checks passed!` on 23 files; semgrep-core 0 results and 0 errors on the 13 files changed since c9150d63; I did not re-run a positive control).
11. Test plan S4 additions: "each red regression fails by an assertion and turns green once the repair lands". HELD for R-3, R-9 and R-10, by in-memory undo of each fix (no file edits).
12. INV-10 "Each value renders as one token … That holds for … file.py:function:line". DID NOT HOLD (R-C2).
13. INV-10 "No record carries … stderr", and T-5 "exc_info is never used". DID NOT HOLD on the start hand-over path (R-C1).
14. AC-1: `CodexApprovalSnippetTests` drives the §4 `answer` and `main` verbatim apart from lazy imports, and asserts `["completed", "1"]`. HELD; it passes 5 of 5. I did not run §4 against a real `codex` (forbidden).
15. §5 diagram versus the call path: no edge changed since S4's match. R-10 changes only what happens inside `CodexConnection.call` and `start`. HELD.
16. NFR-6 and §14 size limits: host.py 927 (< 940); no other touched file is near 950 except the untouched-in-growth codex.py (1,205, value change only). HELD.

COMMANDS RUN:
- `git diff --stat origin/ai/resolve-pr-1055-comments...efb19043 -- . ':!docs'` → 53 files; `git diff --stat efb19043..HEAD` → only `docs/spec/codex-host-hardening/pipeline.md`
- `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider` → `FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 1046 passed, 3 skipped in 65.96s (0:01:05)`
- The 9 fix-specific classes (AC-1 snippet, R-3, R-10, R-9 records, LogToken, R-8, R-6, R-5, R-7), run 5 times → `33 passed in 4.2xs` each time
- `"$V" lint/run.py` → `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS`; `--rule C021` → `C021 native-host-constants-in-lib 0 0 CLEAN` / `SDK-LINT: PASS`; `--rule S008` → `SDK-LINT: PASS`
- `"$V" -m ruff check <23 changed .py> --config lint/ruff.toml --select I001,UP006,UP007,UP035,UP045,F --no-cache` → `All checks passed!`
- `semgrep-core.exe -rules .semgrep/typed-mapping-boundary-policy.yml -lang python -json <file>` × 13 → `0 0` (results, errors) on each
- R-1: the awk check per file, plus a `git diff -U0` scan of PR-added comment lines → `0`
- AST diffs (stdin scripts, base vs efb19043): classes and constants → 14 / 24 / 2 removed; native function-body string literals → wire keys and labels only
- `git diff --numstat c9150d63..efb19043 -- tests`, `git diff 6b59d390..efb19043 -- tests` (empty), `git diff … -- lint .semgrep scripts .github` (empty)
- `PYTHONDONTWRITEBYTECODE=1 … pytest -q -s s4-verify/probe_s4v_code.py` → `RC1 FIRST REVIEW: returned` … `RE1 LINES: 1` … `RE1 LONG RECORD CHARS: 268` / `4 passed in 20.22s`
- In-memory undo of each fix through `unittest` and `mock.patch` on stdin: R-10 → 4 subtest failures in the two red tests; R-9 → 22 failures; R-3 → 2 failures and 1 error; the controls pass
- R-C1 probes: the R-10 hand-over test with an `asyncio` log handler → `ERROR 'Future exception was never retrieved…' | canary in exc_info text: True`; HostTestCase probe (hold `turn/start`, cancel the spawn, `server.die(canary)`) → `TransportClosedError: Codex process closed stdout. stderr_tail=stderr-canary-user@example.com`; a minimal model with debug off → `[('ERROR', 'Future exception was never retrieved', True)]`
- R-C2 probe: `ExceptionOrigin.describe` → `'<frozen os>:__getitem__:678'`, `'<frozen genericpath>:_check_arg_types:152'`; the real router with a handler bug → `… error_type=KeyError origin=<frozen os>:__getitem__:678` / `tokens without key=: ['os>:__getitem__:678']`
- No command wrote a file other than this report, ran pip or the real `codex`, set `VIDBYTE_CODEX_LIVE_TESTS`, or changed git state.
