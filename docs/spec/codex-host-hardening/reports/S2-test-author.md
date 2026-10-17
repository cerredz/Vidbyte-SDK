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
