# S2 test author report — codex-host-hardening (slice 1 of 2)

> Saved verbatim by the orchestrator from the S2 agent's final message: the agent's harness refused its own report-file write ("Subagents should return findings as text, not write report files").

Commits: `ba4e9dfc` test(codex-host): add failing tests for codex-host-hardening [AC-1..AC-41] (test tree + FEATURE.md + README.md + test-plan.md) and `09524ff4` docs(spec): record test proof for codex-host-hardening (§6.2 Proof cells only, 41). No production code, no installs, no real `codex`, live test not enabled, nothing pushed.

## 1. Inventory
`FEATURE.md` "The hardening slice adds these" = 24 hardening failure modes, mapped in `test-plan.md` coverage map. 106 new tests in 12 files (97 red, 8 green guards, 1 live-skipped class); 41 run on CI. Methods: fault injection at §13's named seams only; request-count deltas around every refusal; planted privacy markers in logs and errors; `WAIT_SECONDS`-bounded waits so a hang fails fast.

## 2. Pruned / not written
In `test-plan.md` with reasons: EC-1/2/50, EC-14, EC-10/27/28/36/47, EC-19, EC-29/30/31/39/42/44, AC-40's lint half, AC-37 (the run itself), a paid live turn. Pruned over-specification: the observability `handled_by` value; the lineage error `thread_id` (now method + exactly 3 attempts); death `interrupts == 0` (replaced by a positive `codex_host_turn_ended` check); the live `0.163.` prefix (now "a version is reported"); field names on the network/writable-root refusals for fork/review/goal (defect 7). Added late: EC-22 (second forget → 0), EC-35 (a model with no listed tiers is not checked), EC-18 (a failed cleanup interrupt still ends the turn `FAILED`). Several docstring EC/D references corrected to r3 numbering.

## 3. Red run
`PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads -q -p no:cacheprovider` with `$V` = the `venv-codex163` interpreter.
- Baseline at `24351c30`: `1 failed, 650 passed, 2 skipped`.
- After S2: `125 failed, 631 passed, 3 skipped in 113.89s`. `tests/test_codex_*.py`: `269 passed`. `lint/run.py` ends `SDK-LINT: PASS` (C021 clean); `ruff check` clean. No collection errors, no never-awaited/never-retrieved warnings.
- The 125 = 97 new + 20 superseded + 7 collateral (go green once the lib §9.3 texts change, no test edit: two in `test_codex_host_error_details.py`, the compact goal test in `test_codex_host_thread_helpers.py`, three `CodexHostReviewerTests` in `test_codex_host_threads.py`, the preflight test in `test_codex_host_turns.py`) + 1 inherited (`harness_threads` `assert 167 == 120`).
- Full `-rfs` log: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/s2/red_final.txt`. Per-group red reasons in `test-plan.md` "Red run".

## 4. Fixtures added (`codex_host_support.py`; no fake changed)
`HostTestCase.open_host(settings=None, approval_handler=None)` (passes the handler keyword only when given); `HostTestCase.capture_logs(*names)`; `LogRecorder`, `log_events`, `log_fields`; `is_review_read_back`; the §9.2/§9.3 literal block (`APPROVAL_HANDLER_MESSAGE` … `FORK_EXPERIMENTAL_MESSAGE`, `REVIEWER_MESSAGE`, `CHANGED_LIKELY_CAUSES`, `RETRYABLE_CODES`, `RETRIED_METHODS`, `GOAL_REJECTED_FIELDS`, `DEFAULT_ANSWERS`, `TURN_EVENTS_MODULE`, `HOST_LOGGER`, `TOOLS_LOGGER`). Per-file base classes in the test modules; `HARDENING_WIRE_FIELDS` in the SDK contract test.

## 5. Superseded edits (§13; old → new)
- **A1** `router::CodexHostRouterTests::test_the_router_answers_every_server_request_and_never_raises` (INV-15/16, D-3): approval answers `accept` → `decline`.
- **A2** `records::CodexHostRecordValidationTests::test_user_reviewer_is_refused_when_any_spawn_request_is_built` (INV-20, D-5): construction raised → it now builds; a non-enum reviewer is still refused (name kept).
- **A3** `records::...::test_section_9_3_constants_hold_their_spec_values` (D-3): `CODEX_APPROVAL_ACCEPT_DECISION` and `CODEX_ACCEPTED_APPROVAL_METHODS` asserted absent from the module and `__all__`.
- **A4** `...::test_each_new_code_has_its_classification_row_and_next_step`: via the `NEXT_STEPS` literal.
- **A5** `records::CodexHostEnumTests::test_new_enums_have_exactly_the_spec_members_and_values`: `EXPECTED_ENUMS` gains `FORGET_CODEX_TURNS`.
- **A6** `packaging::...::test_new_packages_export_exactly_their_spec_lists`: `RECORD_EXPORTS` +6 names, alphabetical.
- **A7** `packaging::...::test_existing_export_lists_gain_only_the_new_names_in_place`: `ENUMS_CODEX_ORDER` +3.
- **A8** `helper_surface::...::test_each_method_has_its_section_8_5_signature`: `list_codex_skills` gains `("force_reload", False)`.
- **B1** `threads::...::test_fork_reads_the_turns_first_and_forks_through_a_completed_turn`: `[read, fork]` with `includeTurns` true → `[read, turns/list, fork]`, `includeTurns` falsy, scan `desc`/`notLoaded`.
- **C1** `review_goals::...::test_a_review_whose_final_item_was_dropped...`, **C2** `review_gaps::...::test_a_review_cancelled_during_its_read_back...`, **C3** `failures::...::test_a_review_cancelled_in_flight...`: hold/wait on `thread/turns/list` with `is_review_read_back` instead of `thread/read` + `includeTurns`. C1 still counts 2.
- **G1, G2** (`goal_skills::CodexRunReRaiseTests` ×2), **G3, G4**: operation `get_codex_goal`/`list_codex_turns` → `run_codex_goal`/`run_codex_skill`; the original error is found by its inner operation; the head is rewritten; the tail and every non-derived field kept.
- **G5** (`helper_lifecycle::...protocol_mismatch...`): second loop `list_codex_skills` → the run's own name.
- **I1**: row `forget_codex_turns("")` → `forget_codex_turns thread_id`.
- **I2**: a `CodexHostSetup()` baseline, read lazily.
- **T1** `tools::...::test_spawn_takes_the_posture_from_defaults...`: a goal call with a non-default turn → `configuration.invalid_argument` naming `turn`, host never called; a posture without a turn still reaches the host.
- **Support literals (7):** `USER_REVIEWER_TEXT` (its §9.3 value); `NEXT_STEPS` (`model_unknown`, `goal_unfinished`); `EXPECTED_ENUMS`; `RECORD_EXPORTS`; `ENUMS_CODEX_ORDER`; `HOST_SIGNATURES`; `StubCodexHost.list_codex_skills(cwd="", force_reload=False)` (records `force_reload` only when set).

## 6. Spec defects (none blocking)
1. AC-22/B1 say "no includeTurns", but the SDK always sends `includeTurns: false`; tests check falsy.
2. AC-32's exact `sandboxPolicy` is not what the SDK sends (it adds `excludeSlashTmp`/`excludeTmpdirEnvVar` false); tests pin the 3 named keys and require every other key false.
3. The order of the goal rule versus the network/writable-roots rules is unspecified.
4. How `{sandbox}` renders in `NETWORK_ACCESS_MESSAGE` is unspecified.
5. AC-39's wording is loose; docstrings checked by keyword only.
6. AC-40's lint half is a command, not a test; an `ast` scan stands in.
7. Network access / writable roots on fork, review and `run_codex_goal` need a non-default turn, which is refused first; those rows assert `ConfigurationError` with zero requests, not the field name.
8. The fallback reason for a pending handler cancelled at close is unspecified; only the late request's `closing` reason is asserted.
9. INV-8 is ambiguous about `handled_by` after a handler fails; the test accepts `handler` or `default`.
10. The `codex_host_turn_ended` status format is unspecified; tests assume the wire value.
11. A host without a handler is assumed to write no fallback WARNING.
12. Two values changed for speed/portability: AC-25 uses 0.2 s instead of 1.0 s; AC-27 uses an absolute path instead of `"C:/w"`.
13. The formatting of `{models}`/`{tiers}` in `UNKNOWN_TIER_MESSAGE` is unspecified; tests check by keyword.
14. AC-20's fresh-host row passes on today's code once the §9.3 text changes; it only guards a double walk. The cached-list row proves INV-25.

## Niche facts for the next agent
- Patch seams must exist by these exact names: `turn_events.CODEX_HOST_LOST_TURN_GRACE_SECONDS`; `connection.CODEX_TOOL_CALL_TIMEOUT_SECONDS` (read inside the router's `handle`); `connection.retry_on_overload` (the SDK's own object).
- Watcher threads must be named `"codex-host-watcher"`; `liveness.drain` joins by that name before reading logs.
- Log events are matched by the first word of a %-style format; fields are `key=value` tokens split on spaces (one token per value; `""` when empty); no `exc_info`.
- The SDK `thread_read` always sends `includeTurns=false`; tests reject only `true`.
- The fake ignores `beforeTurnId`/`deferGoalContinuation`; `experimental_api=False` refusals must send nothing, not even fork's `thread/read`.
- AC-20's fresh-host row and the 8 guards pass today; the 7 collateral reds need only the lib §9.3 values.
- Use the `venv-codex163` interpreter, never pip; the `harness_threads` failure is inherited.
- New test files are LF in the working tree; `core.autocrlf=true` normalizes on commit.

## STATUS (as returned)
```
STATUS: DONE
STAGE: S2 test author
HEAD: 09524ff4
SUMMARY: 106 new tests (97 red, 8 green guards, 1 live-skipped); red confirmed 125 failed / 631 passed / 3 skipped (baseline 1/650/2), no collection errors; 97 new + 20 superseded + 7 collateral + 1 inherited; 20 deliberately omitted; 20 superseded tests + 7 support literals edited. Most likely to catch a real bug: test_codex_host_approvals.py::CodexHandlerFallbackTests::test_every_misbehaving_handler_gets_the_default_answer_and_one_warning.
OPEN ITEMS: spec defects 1–14 (none blocking); report file not written by the agent (harness block).
```

## S4 additions

This round worked from the verified S4 review (`review.md`, `0c040d1f`) and spec r5 (`be733a0b`), on top of `b63c4b01`. Production code is unchanged since `c9150d63`.

**Commits**
- `75bfae7d` `test(codex-host): add S4 finding tests for codex-host-hardening [R-3..R-10]`, which also carries the test plan's "S4 additions" section and the pack README's log line.
- `89c641aa` `docs(spec): record S4 test proof for codex-host-hardening`, which changes the §6.2 Proof cells only (AC-2 and AC-18).

Nothing was pushed or installed, and nothing under `vidbyte/`, `lint/` or `scripts/` changed.

### 1. What was added
There are 22 new tests: 6 kill a mutant, 14 are red regressions, and 2 are green guards. Two existing pins also changed (R-7), and three constant rows were added (section D). The full id-by-id table, with each proof line, is in `test-plan.md` under "S4 additions".

- **R-4 (M40)** — `observability::CodexObservabilityTests::test_a_handler_answer_to_a_secret_question_reaches_codex_and_no_record`.
- **R-5 (M1)** — `function_rows::CodexForgetTurnsTests::test_a_forgotten_thread_that_continues_counts_only_its_new_turn`. It compares the cost with a fresh thread given the same usage.
- **R-6 (M31)** — `resilience::CodexSpawnCleanupTests::test_a_cancelled_spawn_whose_start_codex_adopts_keeps_its_tools_for_that_turn`.
- **R-8** — three tests in `liveness::CodexLostWatcherTests`:
  - (a) M2: `test_a_lost_turn_whose_stop_was_already_sent_gets_no_second_interrupt`;
  - (b) M20: `test_the_cleanup_interrupt_of_a_lost_turn_waits_out_the_grace`;
  - (c) M21: `test_a_close_that_starts_inside_the_grace_wins_and_the_lost_turn_sends_nothing`.
- **R-3 (red)** — two rows in `liveness::CodexReviewCompletionFailureTests`: the inline review and the late review.
- **R-9 (red)** — four host rows in `observability::CodexLogTokenRecordTests`. They cover:
  - the router's method and its three ids, and the fallback's thread_id;
  - `_log_call`'s thread_id, both from Codex and from a caller;
  - the turn item, and the turn end;
  - both `turn_events` warnings.

  There are also six CI-visible unit rows in `hardening_contract::CodexLogTokenTests`. They cover the spec examples, the allowed set (the look-alike digits included), the cut at limit + `...`, `""`, idempotence, and the row 10 and row 25 exports.
- **R-10** — four rows in `observability::CodexCallRecordTests`:
  - two red: a cancelled `thread/read` (success and failure rows), and a handed-over `turn/start` (accepted and failed rows);
  - two green guards: a timed-out call writes exactly one record, and EC-57's four refusals write none.
- **R-7** — `GOAL_FIELD_MESSAGE` now has an `{owner}` slot, with `GOAL_SPAWN_OWNER` and `GOAL_RUN_OWNER` beside it. The two `run_codex_goal` pins are red, and the contract row also pins r5's whole `turn` text. The three `CodexSpawnRequest` uses stay green.
- **Section D** — `NEW_CONSTANTS` gains three constants: `CODEX_HOST_ANY_MODEL_TEXT`, `CODEX_HOST_FORK_EXPERIMENTAL_FIELDS` and `CODEX_HOST_LOG_TOKEN_MAX_CHARS`.
  - The row now checks the export before it reads the value, so a missing constant fails as an assertion, not an `AttributeError`.
  - No `__all__` pin for `vidbyte.lib.util.text` existed, so `CodexLogTokenTests` pins row 25's order.
  - `RECORD_EXPORTS` does not change in r5.
- **Fake** — `FakeAppServer.name_next(thread_suffix=..., turn_suffix=...)` names the next thread and turn, as a hostile Codex could.

### 2. Mutant proof
The mutants came from `scratchpad/s4-eng/s4_mutants.py`, run with `-p s4_mutants` over `tests/features/codex_host`. Without a mutant, the run gives `17 failed, 325 passed, 1 skipped`. Under each mutant, the failures are those 17 plus the mutant's own test, and no other test changes.

| Mutant | Run | Failure line | Without the mutant |
|---|---|---|---|
| M1 | `18 failed, 324 passed` | `AssertionError: 0.0033 != 0.0022 within 12 places` | passes |
| M2 | `18 failed` | `AssertionError: 2 != 1` (`test_codex_host_liveness.py:217`) | passes |
| M20 | `19 failed` | `AssertionError: 0.0 not greater than or equal to 0.30000000000000004`. Test (c) also fails, with `2 != 1`. | passes |
| M21 | `18 failed` | `AssertionError: 2 != 1` | passes |
| M31 | `18 failed` | `AssertionError: {'success': False, ...} != {'success': True, 'contentItems': [{'type': 'inputText', 'text': 'echo: hi'}]}` | passes |
| M40 | `18 failed` | `AssertionError: 'answer-canary-91f3' unexpectedly found in 'codex_host_server_answer item_id=item-secret answers=answer-canary-91f3'` | passes |

The 6 mutant-killing tests and the 2 guards then passed 6 times in a row on the clean tree.

### 3. Runs
**Full run** (`tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py`):
- before: `1 failed, 1024 passed, 3 skipped`;
- after: `18 failed, 1029 passed, 3 skipped in 76.44s`.

The 18 failures are:
- 14 B regressions (R-3 ×2, R-9 ×10, R-10 ×2);
- 2 R-7 pins;
- 1 section D row;
- the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`167 != 120`).

**Checks**
- `lint/run.py` ends `SDK-LINT: PASS`.
- `ruff check` finds nothing new in the edited files.
- The one "Task exception was never retrieved" in the log is R-3 itself: the late-accept task dies with the `RuntimeError`, inside the red late-review row.

### Niche facts for the next agent
- **R-10's barrier.** `CodexCallRecordTests` opens its host with `CODEX_HOST_WORKER_THREADS=1`. Records are read once a later call on the same worker returns, so the cancelled call's record must be written by the worker's done-callback, or by a post that runs before that later call ends. Do not log a second time on the timeout path.
- **R-9's hostile ids.**
  - Caller ids that pass through `CodexThreadReadRequest` must be on one line. So the caller row uses only spaces, `=` and `%`, while the Codex-made ids and the router ids carry CR/LF.
  - The hostile thread from Codex is read back raw with `read_codex_thread`, so only log arguments may change.
- **R-3's checks.** The tests never name `_fail` or `fail`. A late review is found through its read-back request (`is_review_read_back`) and a `CodexTurnHandle` built from the fake's last turn.
- **Running the mutants after the repair.** The mutant strings in `s4_mutants.py` match today's source lines. Once the repair edits `_end_lost_turn`, `handle` or `forget`, a mutant may no longer apply, and `pytest_configure` will assert on that. Re-derive the mutant from the new line rather than reading that as a test failure.

### Open items
- Two uncovered risks are left to S5 rather than built here:
  - the connection's closing check, as opposed to its dead check, refusing a call while a close is in progress (EC-57, second bullet);
  - a late start whose loop has already closed, which spec INV-7 says still writes its record.

## Re-review round 1 additions

This round worked from the post-repair re-review (`review.md`, "Post-repair re-review round 1"; verifier `reports/S5-findings-verifier.md`) and spec r6 (`a0c9b489`), on top of `a0c9b489`. Production code is the repair's `efb19043`.

**Commits**
- `48228a1d` `test(codex-host): add re-review round 1 regression tests for codex-host-hardening [R-11, R-12]`. It also carries the test plan's "Re-review round 1 additions" section, the pack README's log line, and the strict `log_fields`.
- `b4127a6a` `docs(spec): record re-review round 1 test proof for codex-host-hardening`, which changes the AC-18 Proof cell only.

Nothing was pushed or installed, and nothing under `vidbyte/`, `lint/` or `scripts/` changed.

### 1. What was added
There are 11 new tests, all red today, plus one stricter helper. The id-by-id table, with each red reason, is in `test-plan.md` under "Re-review round 1 additions".

- **R-11.** Five rows in `observability::CodexCallRecordTests`, one per path. Each row:
  - plants a canary in the error that ends a handed-over start;
  - records the `asyncio` and `concurrent.futures` loggers and collects garbage;
  - asserts that no record carries the canary in its message or its traceback;
  - checks that the start keeps exactly one INV-7 WARNING.

  The paths are:
  - a cancel hand-over (R-10's path), with Codex's RPC error text;
  - a timeout hand-over;
  - a process death after a cancel hand-over, with the stderr tail;
  - an ordinary host close after a cancel hand-over, with a stderr line written earlier;
  - a loop that closed before the start failed, where the leak is `concurrent.futures`' callback error.
- **R-12.** Six rows:
  - Two unit rows in `hardening_contract::CodexExceptionOriginTests`, which run on CI: the spec's `my script.py` example, and whitespace runs in a file name and a function name.
  - Four record rows in `observability::CodexLogTokenRecordTests`, one for each origin field: the router fallback, the tool failure, the turn event failure and the failed call. They compare raw words.
- **Section C, adopted.** `log_fields` now raises when a word has no `=`. With only that change, `tests/features/codex_host` stayed at `342 passed, 1 skipped`.
- **The R-10 row and #1178's in-flight-start row** still trip R-11 today and stay green. Neither was changed; the new cancel row is a separate test.

### 2. Proof against the candidate fixes
These runs used the verifier's in-memory plugin, `s5v_patch_plugin`, over `tests/features/codex_host`.

| Variant | Result | Stray ERROR records |
|---|---|---|
| as is | `11 failed, 342 passed, 1 skipped` | 7 |
| `no_shield,origin_split` (the planned fix) | `353 passed, 1 skipped` | 0 |
| `cancel_wrapper` (alternative A) | `6 failed, 347 passed, 1 skipped`: the R-12 rows only | 0 |
| `consume` (alternative B) | `7 failed, 346 passed, 1 skipped`: R-12 and the closed-loop row | 1 |
| `origin_logtoken` | `7 failed, 346 passed, 1 skipped`: R-11 and the two unit rows | 7 |

What this shows:
- Every new row turns green under the planned fix.
- The closed-loop row is the one that rejects the re-reviewer's `_consume` callback.
- The unit rows reject the `LogToken.of` route, which rewrites `<module>` as `_module_`.

The observability and contract files ran 5 times as is and 5 times under the fix, with the same result each time.

### 3. Runs
**Full run** (`tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py`):
- before: `1 failed, 1046 passed, 3 skipped`;
- after: `12 failed, 1046 passed, 3 skipped in 67.92s`.

The 12 failures are the 11 new rows and the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`.

**Checks**
- `lint/run.py` ends `SDK-LINT: PASS`.
- `ruff check` finds nothing new in the edited files. The three `exec` calls each carry `noqa: S102` with a reason.

### Niche facts for the next agent
- **Collect before you read.** asyncio reports an unread failure from `Future.__del__`. So a row must drop its references and run `gc.collect()` before it reads the records.
  - `cancel_while_held` and `cancel_mid_start` consume the `CancelledError` through `assertRaises`, which clears the traceback's frames.
  - A traceback held anywhere keeps the wrapper alive, and that hides the leak.
- **The closed-loop path.** `run_in_other_loop` runs the caller under `asyncio.run`, so the loop is closed when it returns.
  - The host it opened can never be closed, so a cleanup calls `server.die("")` to end the fake process.
  - The monitor thread is a daemon, and it suppresses the closed loop's `RuntimeError`.
- **What the timeout record says.** The timeout WARNING reads `failure_code=codex.api_error error_type=TimeoutError origin=tasks.py:wait_for:492`. The rows pin only its event and level.
- **R-12 without frozen modules.** `compile` names the frame's file. So the rows never touch the disk or `os`, and they do not depend on whether the build freezes the stdlib.

### Open items
- Round 3's open item, "a late start whose loop has already closed, which spec INV-7 says still writes its record", is now covered: the closed-loop row asserts that record.
- The connection's closing check, as opposed to its dead check, still has no row (EC-57, second bullet). It is left to S5.
- m-8 is a spec wording item, so it has no test.
