# S5 findings verifier: post-repair re-review round 1

Scope: the three findings in `reports/S5-rereview.md` (R-C1 Blocker, R-C2 Major, R-C3 Minor), verified against code `efb19043`. HEAD `28dc292a` is the same for `vidbyte/` and `tests/`: `git diff --quiet efb19043 HEAD -- vidbyte tests` exits 0. The verdict stays **MERGEABLE AFTER FIXES**:

- 1 Blocker confirmed: R-11, which is R-C1 plus a `[verifier]` extension;
- 1 Major confirmed: R-12, which is R-C2;
- 1 Minor passed through: m-8, which is R-C3;
- 0 refuted, 0 downgraded.

Interpreter: `venv-codex163` (Python 3.11.0, MSC v.1933 64-bit, openai-codex 0.163.0). `pytest-randomly` is absent. Every probe lives under `scratchpad/s5-verify/`:

- `probe_s5v_host.py`: the host-level probes, a real CodexHost on the fake app-server;
- `probe_s5v_model.py`: the real `CodexConnection.start`, `_hand_over`, `_log_late`, `_post_late` and `_land`, on a hand-built connection, with three in-memory candidate fixes;
- `probe_s5v_race.py`: a forced landing in the window between `wait_for` giving up and `start`'s `except`;
- `s5v_patch_plugin.py`: a pytest plugin that swaps a candidate fix in memory for a whole run and counts ERROR records on `asyncio` and `concurrent.futures`;
- `s5v_strict_fields.py`: a pytest plugin with a `log_fields` that refuses tokens without `=`.

No worktree file was changed except `review.md` (append only) and this report.

## Merge

R-C1, R-C2 and R-C3 have three different root causes, so none of them merge. The verifier's own closed-loop finding has the same root cause as R-C1, so it merges into it as R-11.

## R-C1 → R-11: CONFIRMED, Blocker

**Claim.** A spending start handed over on cancel or timeout, which then fails, leaves an exception that nothing retrieves. asyncio then logs it at ERROR with its text, and that text can include Codex's stderr tail.

**Mechanism, read from the interpreter's own source.**

- **Shield.** `asyncio/tasks.py:898-900`: once the outer future is done, `_outer_done_callback` runs `inner.remove_done_callback(_inner_done_callback)`. That removes the only reader that would otherwise mark the inner result as retrieved (`:884`).
- **wait_for.** On both a caller cancel and a timeout, `wait_for` cancels the shield's outer future through `_cancel_and_wait`.
- **The chain.** `asyncio/futures.py:394-401`: `_chain_future`'s `_call_set_state` copies the worker's outcome onto the inner `wrap_future` wrapper with `dest_loop.call_soon_threadsafe(_set_state, …)`, unless the wrapper is cancelled and the loop is closed. The wrapper here is never cancelled, so:
  - on a live loop, it gets `set_exception` and nothing reads it. `Future.__del__` then hands it to the loop's exception handler, which logs ERROR on the `asyncio` logger (`base_events.py:1757`, `logger.error(…, exc_info=exc_info)`);
  - on a closed loop, `call_soon_threadsafe` raises `RuntimeError` inside a `concurrent.futures` done-callback. That logs through `LOGGER.exception('exception calling callback for %r')` (`concurrent/futures/_base.py:342`), and the worker's own exception is chained as `__context__`.
- **The stderr text.** openai-codex 0.163.0, `client.py:909-910`: `TransportClosedError(f"Codex process closed stdout. stderr_tail={self._stderr_tail()[:2000]}")`.

**Probes on the real host** (`probe_s5v_host.py`, run as `PYTHONPATH=<worktree> "$V" -m pytest <probe> -k probe_ -q -s -p no:cacheprovider`):

```
RC1-A RECORD: logger=asyncio level=ERROR msg='Future exception was never retrieved' exc_info=True
RC1-A   last line: 'openai_codex.errors.InternalRpcError: JSON-RPC error -32603: store failed for rpc-canary-a3c5'
RC1-A   canary 'rpc-canary-a3c5' in record text: True
RC1-A connection-logger records carrying the canary: 0
RC1-B RECORD: logger=asyncio level=ERROR msg='Future exception was never retrieved' exc_info=True
RC1-B   last line: 'openai_codex.errors.TransportClosedError: Codex process closed stdout. stderr_tail=stderr-canary-user@example.com'
RC1-B   canary 'stderr-canary-user@example.com' in record text: True
RC1-C RECORD: logger=asyncio level=ERROR msg='Future exception was never retrieved' exc_info=True
RC1-C   last line: 'openai_codex.errors.TransportClosedError: Codex process closed stdout. stderr_tail=stderr-canary-user@example.com'
RC1-C   canary 'stderr-canary-user@example.com' in record text: True
13 passed in 16.42s
```

- **RC1-A** is the committed row `CodexCallRecordTests::test_a_spending_start_handed_over_on_cancel_writes_one_record_for_its_late_outcome`, run unchanged, with recorders added.
- **RC1-B** holds `turn/start`, cancels the spawn, then calls `server.die(canary)`.
- **RC1-C is new, and it is the common path.** It writes one stderr line, holds `turn/start`, cancels the spawn, then closes the host normally. No crash is needed.
- **The leak is in `getMessage()` too, not only in `exc_info`.** The model probe prints `msg="Future exception was never retrieved\nfuture: <Future finished exception=RuntimeError('Codex process closed stdout. stderr_tail=stderr-canary-user@example.com')>"`, so the future's repr carries the text. A handler that formats only messages still leaks it.

**The committed suite already trips it.** `s5v_patch_plugin` counts ERROR records on `asyncio` and `concurrent.futures` across the unchanged area run:

```
1 failed, 1046 passed, 3 skipped in 65.90s (0:01:05)
S5V stray ERROR records on asyncio/concurrent.futures: 2
  S5V stray: asyncio Future exception was never retrieved | during: tests/features/codex_host/test_codex_host_observability.py::CodexCallRecordTests::test_a_spending_start_handed_over_on_cancel_writes_one_record_for_its_late_outcome (call) | last: openai_codex.errors.InternalRpcError: JSON-RPC error -32603: store failed for rpc-canary-a3c5
  S5V stray: asyncio Future exception was never retrieved | during: tests/features/codex_host/test_codex_host_review_gaps.py::CodexHostInFlightStartTests::test_a_failed_in_flight_start_frees_its_thread_when_it_returns (call) | last: openai_codex.errors.InternalRpcError: JSON-RPC error -32603: Codex could not start the turn.
```

The second test exists at base: `test_codex_host_review_gaps.py:206` on `8baff351`.

**The closed loop, `[verifier]`** (`probe_s5v_model.py`: the real `start` and `_hand_over`, with the loop closed before the start lands):

```
=== loop_closed_first=True logger=concurrent.futures msg='exception calling callback for <Future at 0x24c831a0910 state=finished raised RuntimeError>'
Traceback (most recent call last):
RuntimeError: Codex process closed stdout. stderr_tail=stderr-canary-user@example.com
During handling of the above exception, another exception occurred:
Traceback (most recent call last):
RuntimeError: Event loop is closed
```

It is reachable whenever a handed-over start's worker wakes after `__aexit__` has returned and the loop has closed. That happens in either of these cases:

- the close thread posts `_mark_closed` before the blocked worker sees the end of the file;
- `CODEX_HOST_CLOSE_WAIT_SECONDS` runs out.

**Question 1: is it real at `efb19043`?** Yes, on all four paths above.

**Question 2: inherited, or caused by this PR?** Inherited. Base `8baff351` `connection.py:218` is `return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), bound)`, with the same `_hand_over`. It is still in scope on both grounds the briefing names:

- this slice changed that exact path: R-10 rewrote `start`'s hand-over, adding `started`, `_hand_over(…, record)` and `_log_late`;
- this slice's spec governs it:
  - INV-10, spec.md:300-303: "No record uses `exc_info`" and "No record carries … stderr";
  - INV-10, :282: messages "never contain exception text";
  - NFR-3, :671;
  - T-5, :1125;
  - NFR-1, :669: "Zero exceptions escape … a loop callback", which is request.md §D's weighted "exception handle everything that could potentially go wrong".

**Spec adjudication.** One could argue that AC-18 captures only the package's loggers, so the spec does not reach asyncio's record. I reject that:

- INV-10's privacy list is phrased "No record carries …", without a logger scope;
- T-5's threat is "an operator or log pipeline with access to logs", and that pipeline receives asyncio's records through the same root handlers;
- an exception that asyncio reports as "never retrieved" escaped its handling by definition, which is exactly what NFR-1 forbids.

The spec already requires the behaviour, so the owner is code, and no spec change comes first. A one-line clarification may go into the repair's S5 deviation note, but it is optional.

**Severity: Blocker.** It is an unsafe result: the stderr text that codex-host INV-9 keeps out of errors (request.md:179: "No SDK text, stderr or email ever reaches an error message") lands in an ERROR log with a traceback. It also violates the user's weighted words. And it is reachable on an ordinary path, RC1-C.

**Smallest fix: adjudicated.** Three candidates were built in memory by exact text replacement of `start`'s own source, each replacement asserted to match once:

| Candidate | live loop, cancel / timeout | closed loop, cancel / timeout | forced race window (`probe_s5v_race.py`) | codex_host suite | area |
|---|---|---|---|---|---|
| as is | ERROR, canary True / ERROR, canary True | `concurrent.futures` ERROR, canary True / same | ERROR, canary True | 342 passed, 2 stray | 1046 passed, 2 stray |
| **no_shield**: `wait_for(asyncio.wrap_future(future), bound)` | none / none | none / none | none | 342 passed, 0 stray | `1 failed (inherited), 1046 passed, 3 skipped`, 0 stray |
| cancel_wrapper: keep the shield; `waited.cancel()` after each `_hand_over` | none / none | none / none | none | 342 passed, 0 stray | `1 failed (inherited), 1046 passed, 3 skipped`, 0 stray |
| consume (the re-reviewer's `_consume` callback) | none / none | **ERROR, canary True** / **ERROR, canary True** | none | not run | not run |

- **Recommended: no_shield.** It is one expression, and it gives `start` the exact shape `call` already has (`connection.py:348`).
  - **The race.** It is race-free without relying on an implementation detail, because `wait_for` itself cancels the wrapper, or else reads a wrapper that has already landed through `fut.result()`.
  - **A queued start.** It is still withdrawn: the wrapper's cancel reaches `future.cancel()` through `_call_check_cancel`, and `_hand_over`'s `future.cancel()` then returns True.
  - **A running start.** It keeps both of `_hand_over`'s callbacks.
  - **Comments.** The `@intent` narration ("awaited through a shield") and the FILE header PURPOSE ("the shielded spending starts") must change, per AGENTS.md §2.
  - **The spec.** `grep -n -i shield` over the slice's spec.md and test-plan.md finds nothing, and no test references `shield`.
  - **When the choice would flip.** If a reviewer insists on keeping the shield as documentation of intent, take cancel_wrapper.
- **cancel_wrapper also covers the race window.** It does so only because `Future.cancel()` clears `__log_traceback` before its state check (`asyncio/futures.py:153`), so cancelling an already-landed wrapper silences it. Proof, with the C Future in use: `cancel() on a done future returned: False`, then `cancel called=True: asyncio records=[]`, against `['Future exception was never retrieved']` without the cancel. It works, but it leaves a shield whose protection is undone two lines later.
- **The re-reviewer's `_consume` is insufficient.** It never runs when the loop is closed, because the state copy itself raises first.

**The test owner first.** Today's rows capture only `CONNECTION_LOGGER` (`test_codex_host_observability.py:372`), so a repair could pass vacuously. Proposed S2 rows:

- in `CodexCallRecordTests`, also capture `asyncio` and `concurrent.futures`;
- once the late outcome lands, run `gc.collect()` and then `await asyncio.sleep(0)`. My probe used three rounds of `gc.collect()` plus `sleep(0.05)`, and the record appeared every time;
- assert there is no ERROR record on those loggers, and no canary in `getMessage()` or the formatted `exc_info`;
- three rows: the R-10 failure row, death after a hand-over, and an ordinary close after a hand-over with one stderr line written. A closed-loop row is optional, because it needs the loop closed under a held worker, which `HostTestCase` does not do.

**Owner, in order:** test, then code.

## R-C2 → R-12: CONFIRMED, Major

**Claim.** `ExceptionOrigin.describe` renders frozen-stdlib frames as `<frozen os>:__getitem__:678`, which splits each of four WARNING records into two tokens.

**Evidence.**

```
RC2-A describe(os.environ) = '<frozen os>:__getitem__:678'
RC2-A describe(os.path.join) = '<frozen genericpath>:_check_arg_types:152'
RC2-B answer sent: {'decision': 'decline'}
RC2-B RECORD: codex_host_server_request_fallback method=item/commandExecution/requestApproval thread_id=thr-1 reason=handler_failed error_type=KeyError origin=<frozen os>:__getitem__:678
RC2-B tokens without '=': ['os>:__getitem__:678']
RC2-B log_fields origin: '<frozen' keys: ['error_type', 'method', 'origin', 'reason', 'thread_id']
RC2-C RECORD: codex_host_tool_failed tool=check_codex_ready error_type=KeyError origin=<frozen os>:__getitem__:678
RC2-C tokens without '=': ['os>:__getitem__:678']
```

- **The paths.** RC2-B goes through the real router, with an async approval handler that reads a missing `os.environ` key. RC2-C goes through the real `check_codex_ready` tool, with the host method patched to do the same.
- **Why `os` is frozen.** On this build, `os.__spec__.origin` is `frozen`, so its frames carry `co_filename` `<frozen os>`.
- **Deterministic without frozen modules.** `exec(compile("raise KeyError('k')", "my script.py", "exec"))` describes as `'my script.py:<module>:1'`, and a tab in the file name gives `'a\tb.py:<module>:1'`.
- **Why the suite is green.** `log_fields` drops tokens without `=` (`codex_host_support.py:547`). With `s5v_strict_fields`, a `log_fields` that refuses them, the unchanged codex_host suite gives `342 passed, 1 skipped in 23.82s`, and the router probe fails with `AssertionError: record splits into tokens without '=': ['os>:__getitem__:678']`. So that one helper change would make every existing record assertion a shape guard.

**Question 1: is it real?** Yes, at both a router site and a tool site. The other two sites, `_log_call` (`connection.py:456`) and `turn_events.py:150`, call the same helper.

**Question 2: inherited, or caused by this PR?** Caused by this PR. `ExceptionOrigin` is new in it (§12.3 row 9).

**Question 3: who owns the fix?** Code, after a test. No spec change is needed:

- INV-10 at spec.md:286 says "Each value renders as one token with no spaces. That holds for … `file.py:function:line`";
- the exemption at spec.md:293 says origins "need not pass through" `LogToken`. That names a helper that is not required; it does not allow an origin to split;
- the helper's own header says "Keep the output one token with no spaces".

**Smallest fix: adjudicated, against the §8.4 budget** (3 files, 14 classes, 0 dependencies, 11 config keys, 13 messages).

- **Recommended.** In `exception_origin.py:32`, `return "_".join(f"{…}:{…}:{line}".split())`, plus one KNOWN EDGE CASES line in its header.
  - It is one line in one file, and that file is already row 9.
  - The budget does not move: 0 files, 0 classes, 0 config keys, 0 messages, 0 dependencies.
  - It fixes all four call sites, and any future one.
  - Ordinary origins and the names `<module>`, `<lambda>` and `<genexpr>` come back unchanged: `'<stdin>:<genexpr>:13'` stays as it is.
  - In memory: `origin=<frozen_os>:__getitem__:678`, with no orphan token; codex_host `342 passed, 1 skipped`; area `1 failed (inherited), 1046 passed, 3 skipped`.
- **Alternative** (the re-reviewer's): `LogToken.of(…, CODEX_HOST_LOG_TOKEN_MAX_CHARS)` at the four call sites. It is also green (342), but larger:
  - it touches 3 files, plus a new import pair in `_base.py`;
  - it rewrites ordinary origins: `'_stdin_:_genexpr_:13'`, `'my_script.py:_module_:1'`;
  - it cuts an origin longer than 128 characters before its line number;
  - the re-reviewer's own note says it needs spec r6 to keep INV-10's exemption list true.
- **When the choice would flip.** If the user wants origins bounded in length as well as space-free, take the alternative and spec r6.

**Severity: kept at Major.** It is the same record-shape rule R-9 fixed for ids, at R-9's tier: no forgery and no wrong answer. But logfmt and key=value pipelines lose the root-cause location (D-13) on a common developer bug, a missing environment variable. And the suite's parser hides it.

**Test owner rows.**

1. `CodexExceptionOriginTests`: the "my script.py" origin has no whitespace and exactly 2 colons. This is deterministic whether or not the build freezes `os`. Debug builds and source checkouts run with frozen modules off.
2. A router row: a handler reads a missing `os.environ` key, and every token after the event name contains `=`. Read the tokens raw, or tighten `log_fields`.

**Owner, in order:** test, then code.

## R-C3 → m-8: passed through, Minor

`_hand_over` (`connection.py:493-495`) registers `record`, then `_post_late`. `_post_late` (`:497-501`) is the same as at base `8baff351` :241-245. The spec's wording does not match:

- INV-7 (spec.md:261): "The done-callback that already posts the late outcome to the loop writes the record first";
- row 12 (spec.md:1330): "`_post_late` writes the record before it posts".

The reason for the actual shape (AGENTS.md §1: `_post_late → _log_late → _log_call` would be three deep) is recorded only in verify-log.md:32-33. `grep -n "Implementation deviations"` finds only the S3 list, at :1654.

Behaviour is identical. It is tagged **trivial**, owner spec text, which the repair agent can write as a docs edit together with R-11's change to the same hand-over.

## Blind spots checked on the same paths

- **The R-10 hand-over.** The asyncio and closed-loop leaks are R-11. Other checks held:
  - No other site has the pattern. `grep` for `asyncio.shield`, `wrap_future` and `run_in_executor` across `native/codex` and `tools/builtins/codex` finds:
    - `call` (:348): no shield, so the wrapper is cancelled and the state copy is skipped;
    - `launch` (:311): the same;
    - `close` (:595), which shields `reap()`, and `host.py:461`, which shields `turn.ended`. Both futures only ever get `set_result` (`turns.py:151`; `_mark_closed`).
  - The record-before-post order holds, including when `add_done_callback` runs at once on a future that is already done.
- **The R-3 `except`** (`reviews.py:144-147`). There is no `await` inside the `try`, so it never catches a cancellation; it is `except Exception`, never `BaseException`; and `CodexTurnRegistry.finish` is first-wins, so `events.fail` (`turn_events.py:142-154`) ends the review once. `fail` logs, stops quietly, finishes and closes the goal stream; none of those steps is new code that raises. It holds. Its origin field inherits R-12, and R-12's fix covers it.
- **The `LogToken` application.** I listed all 9 logger calls in the files the PR changed. Every Codex- or caller-chosen id goes through `LogToken.of`. The rest are host-made: operation, method constants, `failure_code`, `status.value`, `handled_by`, `_label` (a closed set, or `empty`), the tool name and type names. The only gap is `origin`, which is R-12.
- **Considered, not raised.**
  - `_log_late` (`connection.py:469-472`) maps a non-`Exception` `BaseException` outcome to a DEBUG success record. A host worker that runs openai-codex's synchronous calls cannot get `KeyboardInterrupt`, and nothing there raises `SystemExit` or `CancelledError`. Spending caution there would be guarding a state that does not occur.
  - A type name with a space needs a dynamically built class, and the spec exempts type names.

## Commands run (final lines)

- `git diff --quiet efb19043 HEAD -- vidbyte tests && echo "code identical efb19043..HEAD"` → `code identical efb19043..HEAD`
- `git show origin/ai/resolve-pr-1055-comments:vidbyte/harnesses/native/codex/connection.py | grep -n shield` → `218: return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), bound)`
- `PYTHONPATH=$(pwd) "$V" -m pytest scratchpad/s5-verify/probe_s5v_host.py -k probe_ -q -s -p no:cacheprovider` → the probe lines above, ending `13 passed in 16.42s`. The 8 extra items are the imported `CodexCallRecordTests` rows, because the module name matches `-k`.
- `"$V" scratchpad/s5-verify/probe_s5v_model.py` → 32 rows. The as-is rows show `('asyncio', 'ERROR', 'Future', True, True)` on a live loop and `('concurrent.futures', 'ERROR', 'exception', True, True)` on a closed loop. no_shield and cancel_wrapper show no ERROR rows. consume shows the closed-loop ERROR, canary True.
- `"$V" scratchpad/s5-verify/probe_s5v_race.py` → `race cancel as_is ERROR records: [('asyncio', 'Future exception was never retrieved', True)]`. no_shield, consume and cancel_wrapper give `[]`, and the timeout rows match.
- `S5V_VARIANT=<v> … -m pytest tests/features/codex_host -q -p no:cacheprovider -p s5v_patch_plugin -s`, for each variant:
  - `as_is` → `342 passed, 1 skipped in 27.45s` / `S5V stray … 2`;
  - `cancel_wrapper` → `342 passed, 1 skipped in 26.44s` / `… 0`;
  - `no_shield` → `342 passed, 1 skipped in 25.61s` / `… 0`;
  - `origin_split` → `342 passed, 1 skipped in 26.85s`;
  - `origin_logtoken` → `342 passed, 1 skipped in 26.64s`.
- The area run, `tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py`:
  - as is → `FAILED …test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` / `1 failed, 1046 passed, 3 skipped in 65.90s (0:01:05)` / `S5V stray … 2`;
  - `S5V_VARIANT=no_shield,origin_split` → `1 failed, 1046 passed, 3 skipped in 64.95s (0:01:04)` / `S5V stray … 0`;
  - `S5V_VARIANT=cancel_wrapper,origin_split` → `1 failed, 1046 passed, 3 skipped in 64.95s (0:01:04)` / `S5V stray … 0`.
- `S5V_VARIANT=cancel_wrapper,origin_split …probe_s5v_host.py` → `RC1-A RECORDS: 0`, `RC1-C RECORDS: 0`. RC1-B leaves only an asyncio debug-mode WARNING, `Executing <Task …> took 0.172 seconds`, with no canary. The RC2 lines read `origin=<frozen_os>:__getitem__:678` / `tokens without '=': []`. Final lines: `5 passed, 8 deselected in 14.44s` / `S5V stray … 0`.
- `-p s5v_strict_fields`, on the unchanged code → `342 passed, 1 skipped in 23.82s`. The router probe gives `AssertionError: record splits into tokens without '=': ['os>:__getitem__:678']`.
- No command edited a worktree file other than `review.md` and this report. None ran pip or the real `codex`, set `VIDBYTE_CODEX_LIVE_TESTS` or changed git state.
