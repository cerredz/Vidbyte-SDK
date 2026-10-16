# S2 test author report r2: the S4 test findings R-1, R-4 and R-8

Stage: S2 test author (r2, after the S4 review) · Spec: `docs/spec/codex-host-thread-helpers/spec.md` r3 · Review: `docs/spec/codex-host-thread-helpers/review.md` rows R-1, R-4 and R-8 · Branch: `feat/codex-host`, started at `aaaac67a` · Date: 2026-10-16

## Outcome

Five new tests close the three findings.

- **On the current code:** all five pass.
- **On the matching verifier mutant:** each one fails. Before these tests, every one of those mutants passed the whole codex set (864 passed).
- **What changed:** only files under `tests/` and `docs/spec/`. No source changed. The verifier harness builds its mutants as copies in its own `mut/` folder, so the worktree was never edited, and `git status --porcelain` is empty.

Commits, each ending with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer:

| Commit | Finding | Message |
|---|---|---|
| `6c5eca2a` | R-1 | `test(codex): prove a failed or cancelled goal-run tool call frees its cap slot [R-1]` |
| `6a434afd` | R-4 | `test(codex): prove delete holds the thread and releases it on failure or cancel [R-4]` |
| `30a0a0ac` | R-8 | `test(codex): prove the skill read-back needs the sent name on the handle's own turn [R-8]` |
| this report | — | `docs(spec): add S2 test author r2 report` |

## Tests added

| Finding | Invariant | Test | What it proves |
|---|---|---|---|
| R-1 | INV-27, AC-33 | `tests/features/codex_host/test_codex_host_helper_tools.py::CodexHelperToolScopeTests::test_a_failed_or_cancelled_goal_run_releases_its_slot` | The scope has `max_live_turns=1`. A `run_codex_goal` tool call whose host call raises `codex.command_not_run` gives the slot back, and a `run_codex_skill` call then takes it. A goal run cancelled while the stub host holds it gives the slot back too, and a `run_codex_openai_docs` call then takes it. The stub's call log is exact. It runs on CI (stub host). |
| R-4 | INV-9, AC-23 (delete half) | `tests/features/codex_host/test_codex_host_thread_helpers.py::CodexThreadReservationTests::test_a_delete_in_flight_holds_the_thread_until_it_ends` | While the fake holds `thread/delete`, four calls on that thread each raise `codex.session_busy`: `continue_codex_thread`, `start_codex_review`, `compact_codex_thread` and a second `delete_codex_thread`. Each has its own operation and the exact `BUSY_TEXT` plus the thread suffix, and nothing is sent. After the release, the delete returns None and the thread is gone. A continue then passes the idle check: one `thread/read` for the thread, no resume and no `turn/start`, then `session_not_found`. A second delete sends exactly `["thread/read"]`. |
| R-4 | INV-9 | `…::test_a_failed_or_cancelled_delete_releases_the_thread` | A `thread/delete` failed once with −32603 gives `codex.api_error` with operation `delete_codex_thread`, and the thread stays stored. A compact then goes through as `[thread/read, thread/compact/start]`. Next, a delete is cancelled while the fake holds its request; Codex then refuses that request, so the thread stays stored. A compact and a delete still go through, and the thread is gone at the end. |
| R-8 | INV-34, AC-39 | `tests/features/codex_host/test_codex_host_goal_skills.py::CodexSkillReadBackTests::test_a_skill_recorded_under_another_name_stops_the_run_once` | The sent name is `s`; Codex records the skill entry as `other-skill`, or as `S`. Each case gives `codex.command_not_run` with the exact `SKILL_DROPPED_MESSAGE` plus the suffix, 1 `thread/turns/list`, and exactly 1 interrupt before and after the one-worker barrier. The test first asserts that the fake recorded the entry under that name, so only the name clause can explain the miss. |
| R-8 | INV-34, AC-39 | `…::test_input_recorded_on_another_turn_does_not_confirm_the_run` | Every page shows an earlier turn that holds the exact skill input sent, never the started turn. The result is `codex.command_not_run` with the exact `INPUT_NOT_RECORDED_MESSAGE` (seconds `600.0`) plus the suffix, after exactly `CODEX_HOST_INPUT_CHECK_ATTEMPTS` reads. There is one interrupt, aimed at the started turn's id, and still one after the barrier. |

Fake extension for R-8, in `tests/features/codex_host/codex_host_fakes.py`. Both switches default to off, so every older answer is unchanged:

- **`recorded_skill_name`:** when set, each recorded skill entry carries this name instead of the one sent.
- **`input_on_earlier_turn`:** `turn/start` records the input on a completed turn placed before the started one. The started turn gets no `userMessage`.

R-4 needed no fake change, because `server.hold(method)` already holds any method. The hold waits before the handler runs, and a failure rule is taken after the release. So a `fail()` set while the delete is held makes Codex refuse the delete that was already sent.

Docs:

- **`test-plan.md`:** the coverage map gains the rows INV-27 (R-1), INV-9 (R-4) and INV-34 (R-8). Each row went in with its finding's commit.
- **`FEATURE.md`, Known Failure Modes:** delete's reservation, the read-back's name and turn-id clauses, and "or a cancel (the goal tool included)" for the run tools.
- **The pack's `README.md`:** one Logs line.

Every existing test, pin and name is unchanged.

## Mutation proof

Command: from the verifier harness folder, `<venv python> probe.py V00_noop V01_since_exclusive V36_goal_tool_slot_leak V36b_skill_tool_slot_leak V36c_docs_tool_slot_leak V05_delete_no_reserve V05b_delete_release_only_on_success V02_any_turn V03_any_skill_name V04_casefold_name`. The harness folder is `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s4-verifier`.

It runs the whole codex set, deselects the one inherited failure, and loads each mutated module from a copy through `verifier_plugin.py`. Each run reported `loaded_from_mutant=True`.

| Probe | Before (S4 log) | Now | Killed by |
|---|---|---|---|
| V00_noop (control) | — | `exit=0 :: 869 passed, 2 skipped, 1 deselected in 54.24s` | — (passes, as it must) |
| V01_since_exclusive (control) | killed | `exit=1 :: 1 failed, 868 passed …` | `test_since_returns_the_inclusive_window_and_stops_at_the_first_older_thread` |
| V36_goal_tool_slot_leak | `exit=0 :: 864 passed` | `exit=1 :: 1 failed, 868 passed … in 54.65s` | `test_a_failed_or_cancelled_goal_run_releases_its_slot` |
| V36b_skill_tool_slot_leak (control) | killed | `exit=1 :: 1 failed, 868 passed … in 56.52s` | `test_a_failed_or_cancelled_run_releases_its_slot` |
| V36c_docs_tool_slot_leak (control) | killed | `exit=1 :: 1 failed, 868 passed … in 55.38s` | `test_a_failed_or_cancelled_run_releases_its_slot` |
| V05_delete_no_reserve | `exit=0 :: 864 passed` | `exit=1 :: 1 failed, 868 passed … in 54.68s` | `test_a_delete_in_flight_holds_the_thread_until_it_ends` |
| V05b_delete_release_only_on_success | `exit=0 :: 864 passed` | `exit=1 :: 1 failed, 868 passed … in 54.18s` | `test_a_failed_or_cancelled_delete_releases_the_thread` |
| V02_any_turn | `exit=0 :: 864 passed` | `exit=1 :: 1 failed, 868 passed … in 54.55s` | `test_input_recorded_on_another_turn_does_not_confirm_the_run` |
| V03_any_skill_name | `exit=0 :: 864 passed` | `exit=1 :: 1 failed, 868 passed … in 53.95s` | `test_a_skill_recorded_under_another_name_stops_the_run_once` |
| V04_casefold_name | `exit=0 :: 864 passed` | `exit=1 :: 1 failed, 868 passed … in 54.03s` | `test_a_skill_recorded_under_another_name_stops_the_run_once` (the `S` case) |

869 = 864 + the 5 new tests. Each surviving mutant is now killed by exactly the test written for it. The controls behave as before. The full output is in `s2r2_probes.log` in the session scratchpad.

## Gates

- **Pytest:** `PYTHONPATH=$(pwd) <venv python> -m pytest -q -p no:cacheprovider tests/features/codex_host tests/features/harness_threads tests/test_codex_output_contracts.py` at `30a0a0ac` gives `1 failed, 678 passed, 2 skipped in 52.37s`. The one failure is `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, the inherited one.
- **Lint:** `PYTHONPATH=$(pwd) <venv python> lint/run.py` at `30a0a0ac` exits 0 and ends with `SDK-LINT: PASS`. The changed files were already tracked, so lint saw them.
- **Determinism:** 6 back-to-back runs of the 5 new tests gave `5 passed` each time, in about 1.3 s. The tests use no sleeps and no wall clock. Holds, the stub's gates and the one-worker barrier set the order, and every wait is bounded.

## Files touched

- `tests/features/codex_host/test_codex_host_helper_tools.py` (R-1)
- `tests/features/codex_host/test_codex_host_thread_helpers.py` (R-4)
- `tests/features/codex_host/codex_host_fakes.py` and `tests/features/codex_host/test_codex_host_goal_skills.py` (R-8)
- `tests/features/codex_host/FEATURE.md`, `tests/features/codex_host/README.md` and `docs/spec/codex-host-thread-helpers/test-plan.md`
- `docs/spec/codex-host-thread-helpers/reports/S2-test-author-r2.md` (this report)

## Open items

1. **`codex_host_fakes.py` is 1071 lines.** It passed 1000 lines in S2 r1 (899 → 1059), and r2 adds 12. AGENTS.md principle 3 asks for files well below 1,000 lines, and no lint rule gates test files. A follow-up could move the thread-helper handlers (thread/list paging, goal/get, compact, delete, turns/list, skills/list) into a mixin module beside the fake, plus its README File Index bullet. That is a refactor of its own, so this round leaves it.
2. **R-8's protected case does not happen today.** The verifier showed that the current code cannot produce it, because a skill run always reads the first turn of a brand-new thread. The tests guard against a future Codex that renames, re-cases or reorders the recorded input, and against a regression in the two clauses.
