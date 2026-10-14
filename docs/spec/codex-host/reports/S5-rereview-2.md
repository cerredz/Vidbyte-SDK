LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — R-26, R-27 and R-28 hold, spec r6 matches the code, and iteration 1's fixes still hold, with one exception: R-27's commit gives `interrupt_codex_turn` a `send` token with no `# @intent` line. That reopens R-9, and two reports claim it does not. The fix is two comment lines.

Scope: post-repair re-review, round 2 of 2 (final). It covers 30109e89, 736d4a58, ad363725 and 3d26abfe; the five tests added to `test_codex_host_review_gaps.py` after bbaa5a8b; spec r6 (130dd828) against the code; and a re-check of iteration 1's fixes at 7b05e68b. Local HEAD 4b9935d7 has the same `vidbyte/` and `tests/` trees as 7b05e68b, and so does 77c92838, the commit remote CI ran on. Counts: 0 Blocker, 1 Major, 2 Minor.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **R-26 refuses every unusable schema on every path, and leaves the shared formatter alone.**
  - My probe ran 11 schema shapes through spawn, continue and launch, on both the host and the tool path. The shapes were: a cycle under `properties`, `items` or `anyOf`; 5000-deep nesting; a cycle at a skipped key; a lock value; invalid UTF-8 bytes; a model with a field that has no JSON schema; and a non-model type.
  - Each one is refused with a `ConfigurationError` that ends `Got <TypeName>.` (`RecursionError`, `ValueError`, `TypeError`, `UnicodeDecodeError`, `PydanticInvalidForJsonSchema`), with `cause=None` and `sent=[]`. Every tool returns `configuration.invalid_argument`, and nothing escapes (INV-8, INV-9, INV-10, EC-82).
  - `vidbyte/providers/` has 0 diff lines (NG-5).
- **R-27 brings back the caller's retry and keeps R-16 for Vidbyte's own stops.**
  - Each probe gives one `turn/interrupt` and no problem:
    - A: the user's stop is held and the timeout passes;
    - B: the user's stop is held and the cap is crossed;
    - D: a second user call arrives while the first is held;
    - F: a late-acceptance stop is held and the user interrupts.
  - C: the user's stop fails, the timeout passes, and the turn stays `inProgress`, because D-7 says the first stop wins. The retry then gives 2 requests and INTERRUPTED with no problem.
  - `stop()`'s `stop_sent` check and `over_cap()` are byte-unchanged.
  - Leave `stop()` setting `stop_pending` before it spawns `send_stop`. My `stop_no_pending` mutant fails the in-flight test with `2 != 1`.
- **Spec r6's §9.3 is complete.** Every one of the 45 constants the branch adds to `vidbyte/lib/constants/codex.py` appears in §9.3, and the 11 new values equal the code (constants:446-457).
- **The boundaries and the budget are intact.**
  - The branch adds 18 files under `vidbyte/`. They hold 45 classes (30 classes plus 15 records), and 13 enums are added.
  - Every modified file outside docs and tests is a §12.3 row.
  - The native blob hashes to `0374a2c8…942f497a`.
  - `lint/baseline.json`, `pyproject.toml`, `contracts/` and `vidbyte/__init__.py` have 0 diff lines.
  - The test tree has 0 deleted lines, all inside the pack.
  - 0 of the 740 added comment lines are over 72 columns, and the chain scan finds 0 chains.
  - The §4 snippet, extracted from spec.md and run at the fake seam, prints exactly `['True', 'completed The readme describes the SDK.', '15 check_codex_ready']`.

FINDINGS (ranked, most severe first, max 15)

R-C5 [Major] [spec conformance — iteration-1 fix R-9 no longer holds; false claim in two reports] `vidbyte/harnesses/native/codex/host.py:400` — `interrupt_codex_turn` now calls `turn.send_stop` but has no `# @intent` line. That breaks the §12.4 A002 checklist item, which R-9 fixed.
  Evidence:
  - **The trigger.** The R-27 hunk (ad363725) replaced `await self._connection.interrupt(operation, handle, turn.state)` with `await turn.send_stop(self._connection, operation)`. A002 splits identifiers on `_` and `.`, and `send` is one of its policy tokens (`lint/rules/a002_intent_comments.py:44`, `:69-75`). The function's window, lines 397-420 (`_has_intent`, `:77-80`), holds no `@intent` marker.
  - **The rule's own analyzer**, run on `git show <rev>:…/host.py`, `turns.py` and `wire.py`:
    ```
    bbaa5a8b none
    30109e89 none
    ad363725 ['host.py:400 interrupt_codex_turn [external boundaries]']
    7b05e68b ['host.py:400 interrupt_codex_turn [external boundaries]']
    ```
  - **The gate's own output.** `lint/run.py --all --format json`, filtered to the branch's new paths, lists `A002 580 703 IMPROVED` with `vidbyte/harnesses/native/codex/host.py 400 interrupt_codex_turn`. The round-1 re-review measured 579 at bbaa5a8b, with 0 findings under the new paths.
  - **The claims that do not hold.**
    - S5-repair-2.md §1: "A002 lists nothing under the branch's paths."
    - verify-log.md:229: "`lint/run.py --rule A002 --all` lists nothing under the branch's paths."
    - The text form of `--rule A002 --all` prints only the summary row when the verdict is IMPROVED, which hides the finding.
  Failure:
  - **The rules.** §12.4 says: "Every function whose identifiers contain … send … carries `# @intent <name>` … within 4 lines before to 20 lines after `def`". Its source is A002, a rule declared `severity = "blocking"`.
  - **Why the gate passes.** The gate passes only because A002 has 123 findings of slack under its baseline. That is the exact defect review.md R-9 confirmed as Major ("The gate passes only because A002's baseline (703) has slack"). R-9's fix said "Afterwards `lint/run.py --rule A002 --all` lists nothing under the new paths", and that no longer holds.
  - **What changes.** Behaviour does not change.
  Smallest fix:
  - Add one `# @intent <slug>` block to `interrupt_codex_turn`, for example `# @intent a-user-stop-is-sent-once-at-a-time`, above the existing narration at host.py:401.
  - Keep it at or under 72 columns, and give the reason for the rule, not a narration.
  - Re-check with `lint/run.py --rule A002 --all --format json`, filtered to `vidbyte/harnesses/native/`; it should list nothing.
  - Correct S5-repair-2 §1 and verify-log.md:229 when the next log is written.
  Spec IDs: §12.4 (A002 bullet), review.md R-9, NFR-5

R-C6 [Minor] [R-16 intent — residual rated against the spec] `vidbyte/harnesses/native/codex/turns.py:181-188` (and the narration at `host.py:402-403`) — the user path's in-flight mark clears when the caller's await ends, not when the request ends, so a second call can send a second `turn/interrupt` while the first is still on a worker
  Evidence:
  - The comment says "clear the mark when the request ends, failed or not", but the code clears it in `finally:` around `await connection.interrupt(...)`.
  - The repair agent's probe `codex-repair2/probe_cancelled_interrupt.py` holds `turn/interrupt`, cancels the first `interrupt_codex_turn`, then calls again:
    ```
    first call cancelled
    turn/interrupt count after retry while first still held: 2
    final: interrupted problem=None
    ```
  - By reading, the 300 s bound has the same effect. `connection.call` (connection.py:184-187) maps the `TimeoutError` while the worker stays blocked (EC-70), and `finally` clears the mark.
  Failure:
  - **The rating, by the spec: Minor, and no spec ID is violated.**
    - §9.2's interrupt row and EC-25 make the call a no-op only for a finished turn.
    - AC-16 is a single call.
    - INV-11 asks only that the cancellation reach the caller, which it does.
    - The final snapshot is right: INTERRUPTED with no problem.
  - **R-16's own case still holds.** R-16's row covers Vidbyte's timeout, cap and late-acceptance stops in flight, and those still send one request: probes A, B and F, and the verifier's D.
  - **What breaks is the comment.** The cancelled-caller window brings back pre-R-16 behaviour for the user's own abandoned call. The worst outcome is that Codex rejects the second interrupt, and that caller gets a mapped `codex.api_error`. What is actually wrong is the comment: host.py:402-403 says a turn "whose earlier stop is still in flight" gets nothing, and that is false in this window. AGENTS.md principle 2 asks that comments never describe behaviour that is gone.
  Smallest fix:
  - Record this as an accepted residual beside R-1's.
  - Reword turns.py:182-183 to "clear the mark when this await ends, failed, timed out or cancelled", and host.py:402-403 to match.
  - Closing the window would mean tracking the worker future past cancellation inside `CodexConnection.call`, which is out of proportion for a Minor.
  Spec IDs: n/a (R-16 row; §9.2 interrupt row and EC-25 checked, and they hold)

R-C7 [Minor] [test coverage of a fix line] `vidbyte/harnesses/native/codex/host.py:414` — no test pins `turn.stop_pending = True` on the user path, so the "user call while the user's own stop is in flight" case (the verifier's case E) can regress silently
  Evidence: `my_mutants.py`, run over all 116 pack tests with each line replaced by `pass` in memory:
  ```
  none: ran 116 failed 0 errors 0
  user_no_pending: ran 116 failed 0 errors 0
  stop_no_pending: ran 116 failed 1 errors 0
     test_a_user_interrupt_while_the_timeout_stop_is_in_flight_sends_nothing_more | AssertionError: 2 != 1
  ```
  Under `user_no_pending`, two concurrent user interrupts send 2 requests. On the fixed code my probe D gives `second call returned None while first held: sent=1`.
  Failure:
  - The class docstring says "a user interrupt is skipped only while another stop is in flight", and FEATURE.md says the pack covers "a user interrupt … while one is in flight".
  - Only Vidbyte's own stop in flight is tested. The line that applies the same rule to the user path's own stop is unpinned.
  - This is the same class as R-24's surviving mutants.
  Smallest fix (tests-only, granted file): hold `turn/interrupt`, start one `interrupt_codex_turn` task, wait until the request arrives, call `interrupt_codex_turn` again, and assert `count("turn/interrupt") == 1`. After release, assert INTERRUPTED with no problem.
  Spec IDs: review.md R-27 (fix line), R-16

VERIFIED CLAIMS:
1. **"116 passed" for the pack: holds.** The pack gives `116 passed in 7.59s`.
2. **"36 passed, 80 skipped" in the CI view: holds.** With `sys.modules['openai_codex'] = None`: `36 passed, 80 skipped in 1.68s`.
3. **"SDK-LINT: PASS": holds.** The full `lint/run.py` ends `SDK-LINT: PASS`.
4. **"A002 lists nothing under the branch's paths" (S5-repair-2 §1; verify-log.md:229): does not hold.** host.py:400 is listed. See R-C5.
5. **The other lint rows hold.** C011 is 2/2, at turns.py:357 `UsageTracker()`. That finding predates this round, and S4 settled it under D-19, so it is not re-reported. No other rule lists a finding under the new paths.
6. **The native blob SHA-256: holds.** `git cat-file -p 7b05e68b:…/native/__init__.py` hashes to `0374a2c899318e4fdb31c065d951266feaffff5aa736ecde616c4a66942f497a`.
7. **"0 same-class chains of depth 2 or more": holds.** `chains.py` prints `chains of depth >= 2: 0`. `stop → send_stop → connection.interrupt` is one level.
8. **"0 of 740 added comment lines are over 72 columns": holds**, for the branch and for the repair-2 hunks alike.
9. **Remote CI success on 77c92838: holds.**
   - `gh run view` gives `CI completed success 77c92838` and `Static policy completed success 77c92838`.
   - `git diff --quiet 77c92838 7b05e68b -- vidbyte tests` is clean.
10. **R-26, "refused before any request, type name only, no cause": holds** on spawn, continue and launch, and on the host and tool paths (probe_r26_paths). The briefing's claim that "a cycle at a key the formatter skips fails as ValueError" holds: `Got ValueError.`, `sent=[]`.
11. **R-27: the verifier's probe `probe_rc1` with `VARIANT=current` prints exactly the `pending` lines.** These are A 2/none, B 2/`turn_timed_out`, C 2/`budget_exhausted`, D 1, and E 1.
12. **"The new tests fail for the right reason": holds.**
    - `text_kept` fails 2 subtests, on the library-text assertion.
    - `no_recursion` raises 2 `RecursionError` errors.
    - `revert_guard` fails with `2 != 1`.
    - `pending_sticks` fails A and B with `1 != 2`.
    - My `stop_no_pending` fails with `2 != 1`.
    - My `user_no_pending` survives. See R-C7.
13. **Spec r6: holds.** The §9.3 row's 11 values equal constants:446-457, and all 45 new constants appear in §9.3.
14. **The AC Proof column: holds.** All 78 test names cited in AC-1 to AC-37 exist and pass. The existing `tests/test_codex_tools.py`, `test_codex_failure_recovery.py` and `test_session_failures.py` give `130 passed` (AC-28, INV-39, INV-40).
15. **R-28: holds.** `CodexReviewTarget` accepts `title` only on COMMIT and `instructions` only on CUSTOM, as the new sentences say, and S025 passes.
16. **Iteration 1's fixes hold, except R-9 (R-C5).**
    - **R-2.** The refusal comes before any request, and for continue it comes before the busy check and reservation (host.py:277 vs :281).
    - **R-16.** Vidbyte's own stops in flight still turn away a user call (probes A, B and F).
    - **R-4, R-5 and R-11** hold: 0 chains, 0 wide comments, and the constants are used.
    - **R-1, R-6, R-7, R-10, R-13, R-14 and R-17** are covered by the 10 iteration-1 gap tests in the 116 passing.
    - **NG-5.** `CodexHarnessAgent` is changed only by row 7: `vidbyte/agents/codex/tools.py` 16+/2-, and 0 diff lines in repair 2.
17. **The repair agent's R-27 residual reproduces exactly.** It shows 2 interrupts, then `interrupted problem=None`. It is rated in R-C6.

COMMANDS RUN:
- **The pack.** `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$W $PY -P -m pytest $W/tests/features/codex_host -q -p no:cacheprovider --rootdir=$W -c $W/pyproject.toml` gave `116 passed in 7.59s`.
- **The CI view.** The same run with `sys.modules['openai_codex']=None` set before `pytest.main` gave `36 passed, 80 skipped in 1.68s`.
- **Lint.** `PYTHONDONTWRITEBYTECODE=1 MYPY_CACHE_DIR=nul PYTHONPATH=$W $PY lint/run.py` ended `S064 RATCHETED: 4 known finding(s)…` / `SDK-LINT: PASS`.
- **Lint JSON, filtered to new paths.** `lint/run.py --all --format json` gave `A002 580 703 IMPROVED` → `host.py 400 interrupt_codex_turn` and `C011 2 2 RATCHETED` → `turns.py 357`.
- **The A002 analyzer at four revisions.** `IntentAnalyzer().analyze(...)` gave `bbaa5a8b none` / `30109e89 none` / `ad363725 ['host.py:400 interrupt_codex_turn …']` / `7b05e68b [same]`.
- **The R-27 path probes.** `cd $S && W=$W PYTHONPATH="$W;$S" $PY -P -m unittest probe_r27_paths` gave `Ran 6 tests … OK`. The lines are A, B, D and F `sent=1 … interrupted problem=None`; C `sent=1 status=inProgress`, then `sent=2 … interrupted problem=None`; and E `sent=2`, with close's own INV-7 step-3 interrupt, `failed problem=codex.process_exited`.
- **The R-26 path probe.** `… -m unittest probe_r26_paths` gave `Ran 1 test … OK`, with the lines quoted in the first bullet. Tuple keys and a non-str description serialize, so they are accepted, which matches the turn's own conversion.
- **The §4 snippet from spec.md.** `… -m unittest probe_snippet` gave `SNIPPET OUTPUT: ['True', 'completed The readme describes the SDK.', '15 check_codex_ready']`. The `thread/start` sandbox is `read-only`, with `on-request` and `auto_review`.
- **The residual probe.** `codex-repair2/probe_cancelled_interrupt.py` gave `turn/interrupt count after retry while first still held: 2` / `final: interrupted problem=None`.
- **The verifier probe.** `VARIANT=current … -m unittest probe_rc1` printed lines A to E, as quoted in claim 11.
- **The repair mutants.** `$PY -P codex-repair2/mutant_run.py <m> <class>`, for each of the four, gave `FAILED (failures=2)`, `FAILED (errors=2)`, `FAILED (failures=1)` and `FAILED (failures=2)`.
- **My mutants.** `W=$W $PY -P $S/my_mutants.py none|user_no_pending|stop_no_pending` gave `116/0`, `116/0` and `116/1`.
- **The constants against §9.3.** The 45 added constants were grepped against spec.md:1017-1047, and none was missing.
- **The native blob.** `$PY -I -c "…git cat-file -p 7b05e68b:vidbyte/harnesses/native/__init__.py…"` gave `0374a2c8…942f497a`.
- **The boundaries.**
  - `git diff origin/main...7b05e68b -- lint/baseline.json pyproject.toml contracts vidbyte/__init__.py | wc -l` gave `0`.
  - The test-tree numstat lists 16 files, with 0 deletions and all of them inside the pack.
  - `vidbyte/providers` has 0 diff lines.
- **The budget.** `git diff --diff-filter=A` lists 18 files, and an AST count gives 45 classes. `+class` in `enums/codex.py` gives 13.
- **Remote runs.** `gh run view 38526282824` / `38526285681` gave `success 77c92838` for both.
- **The proof map.** The 78 test names cited in spec.md:370-408 were matched against `pytest -rA` PASSED names; none was missing.
- **Existing tests.** `pytest tests/test_codex_tools.py tests/test_codex_failure_recovery.py tests/test_session_failures.py` gave `130 passed in 1.56s`.
- **R-28.** `CodexReviewTarget` across kinds: title is accepted only on `commit`, and instructions are refused on every kind other than custom.
- **The worktree.** `git status --short` is empty after every run.

$S is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/05e7ca2a-3fef-4c41-9b0a-b2de520e33f0/scratchpad/codex-rereview2`; $W is the worktree; $PY is the run venv's python.exe. Every mutant was compiled in memory, no real `codex` was started, and nothing in the worktree changed except this report.
