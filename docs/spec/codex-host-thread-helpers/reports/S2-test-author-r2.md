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

## r3 split

The orchestrator accepted open item 1 and asked for the fake to be split to 900 lines or fewer, with no change in behaviour. This is done in commit `72e34b81`, and open item 1 is now closed.

**What moved.** The code moved to `tests/features/codex_host/codex_host_helper_fakes.py` as `HelperHandlers`, a mixin that `FakeAppServer` inherits. It holds:

- the thread-helper switches;
- paged `thread/list` with `_listed_threads` and `_offset`;
- `thread/goal/get`, `thread/compact/start`, `thread/delete`, `thread/turns/list` with `_listed_turn`, and `skills/list`;
- the turn/start input recording, `source_kind`, `goal_record` and `skill_entry`.

`thread/goal/set` and `thread/goal/clear` were in the fake before this run, but they moved too. Moving only this run's additions left the file at 921 lines. The rest stays with its classes: the six `FakeThread` fields, `_status_wire`, `FakeTurn.hidden_reads`, and the resume step that clears `notLoaded`. Moving the three goal methods together brought the file to 894.

**What stayed the same.**

- No test file changed.
- `codex_host_fakes` re-exports `goal_record` and `skill_entry`.
- `__init__` sets the switches at the same point as before.
- The method table keeps its key order.
- The new module reaches `codex_host_fakes` only when it is used, through `_fakes()`. Because of that, importing either module first works without a circular import.

**No pin, so not BLOCKED.** No packaging, surface or contract test lists the test tree's files. Outside `docs/`, `git grep codex_host_fakes` finds only these:

- `FEATURE.md` and `README.md`;
- the lazy import in `codex_host_support.py`;
- the tests that import `FakeRpcError`.

| Check | Result |
|---|---|
| `wc -l` | `894 codex_host_fakes.py` (was 1071), `237 codex_host_helper_fakes.py` |
| Equivalence check, separate from the suite (`s2r3_equivalence.py`) | **Syntax trees:** each moved function, the switches block, the table and the recording block was compared between HEAD and the split; all 20 comparisons were the same. **Side-by-side run:** the HEAD fake and the split fake were both driven through 74 observations, and every one was equal (it covers thread/list in its plain, paged and endless modes, filters and bad cursors; the turn listing; the recording variants; goal set, get and clear; compact; delete; skills; attribute order; defaults; the table; counters; and the final thread wires). **Planted change:** `hidden_reads -= 2` was reported in both parts, so the check catches a real change. |
| Pytest gate | `1 failed, 678 passed, 2 skipped in 51.64s`; the one failure is the inherited one |
| Mutation harness, 10 probes | Identical to r2. V00 gave `869 passed`. Each other probe gave `1 failed, 868 passed`, and the same test as in r2 caught it (log: `s2r3_probes.log`) |
| CI view with openai-codex hidden | `57 passed, 140 skipped` |
| Lint, after `git add` | `SDK-LINT: PASS` |

## r4: R-17, the run re-raise keeps every CodexAgentError field

The orchestrator sent this finding after S5's two merges of main, at HEAD `00932996`. The tests are in commit `f9c987dc`, `test(codex): prove the run re-raise keeps every CodexAgentError field [R-17]`. They stay red until S5 applies the source fix.

**The defect.** When a check fails with a `CodexAgentError`, `CodexSkillFunctions._unchecked` (`vidbyte/harnesses/native/codex/skill_functions.py:247`) builds a new error. It passes only the message plus suffix, the code, the operation and the next step. Main's #1116 gave `CodexAgentError.__init__` a `thread_id` argument, and `error_type` was already there, so the new error has both empty. That breaks the "original exception propagates" promise of INV-22 and INV-35, cited with AC-27, AC-40, D-16 and D-17. Note that the spec's literal list ("keeps its code, operation and next step") predates #1116 and does not name these two fields.

**No real path sets either field today.** Every codex-host error comes from these sources, and none of them passes `error_type` or `thread_id`:

- `CodexErrorMapper.error` (`errors.py:61-65`), which puts the thread only in the message text (`Thread: <id>.`);
- `missing_sdk`;
- the validation error in `codex_host.py`;
- the busy refusal in `_base.py`;
- the batch rebuild at `host.py:476`.

So, over the real mapper alone, a test would compare `""` with `""` and pass. The defect is real but latent: it starts losing data as soon as any function the run reuses sets either field. The tests therefore swap the connection module's `CodexErrorMapper`, through the existing `patch_connection` helper, for `_FieldCarryingMapper`. It maps exactly as the real mapper does, then also sets `error_type=type(exc).__name__` and `thread_id`. Everything else is the real path: fake JSON-RPC −32603, the real SDK, `connection.call`, the host, and the run's `except`.

**Tests**, in `test_codex_host_goal_skills.py::CodexRunReRaiseTests`:

- `test_a_goal_check_error_keeps_every_field_it_carried` (`thread/goal/get` fails)
- `test_a_skill_read_back_error_keeps_every_field_it_carried` (`thread/turns/list` fails)

Each one does the following:

1. Checks that the original error carried both fields.
2. Checks that the re-raised message is exactly the original message plus the formatted `*_UNCHECKED_MESSAGE`.
3. Checks that none of the 11 kept fields changed: `failure_code`, `operation`, `thread_id`, `error_kind`, `expected`, `safe_runtime_details`, `likely_causes`, `next_step`, `repair_approaches`, `related_docs` and `relevant_tests`.

**Red on the current code, failing only on the two dropped fields:**

```
E   - {'safe_runtime_details': ({'error_type': '', 'operation': 'get_codex_goal'},
E   -                           {'error_type': 'InternalRpcError',
E   -                            'operation': 'get_codex_goal'}),
E   -  'thread_id': ('', 'thr-1')}
E   - {'safe_runtime_details': ({'error_type': '', 'operation': 'list_codex_turns'},
E   -                           {'error_type': 'InternalRpcError',
E   -                            'operation': 'list_codex_turns'}),
E   -  'thread_id': ('', 'thr-1')}
FAILED tests/features/codex_host/test_codex_host_goal_skills.py::CodexRunReRaiseTests::test_a_goal_check_error_keeps_every_field_it_carried
FAILED tests/features/codex_host/test_codex_host_goal_skills.py::CodexRunReRaiseTests::test_a_skill_read_back_error_keeps_every_field_it_carried
2 failed, 24 deselected in 1.23s
```

The message, code, operation and next step all match, so the failures come from those two fields alone. Five back-to-back runs of the module each gave `2 failed, 24 passed`.

**Green in a scratch copy.** The script `s4-verifier/s2r4_green.py` writes a copy of `skill_functions.py` to `mut/`, and `verifier_plugin` serves that copy, so the worktree is not touched. `CodexAgentError` has no `error_type` attribute: it stores the value only in `safe_runtime_details["error_type"]`. A literal `exc.error_type` would raise `AttributeError`, so the fix reads that key:

```python
return CodexAgentError(exc.message + sentence, failure_code=exc.failure_code, operation=exc.operation, error_type=exc.safe_runtime_details.get("error_type", ""), next_step=exc.next_step, thread_id=exc.thread_id)
```

```
X17_none_new_tests: exit=1 :: ============================== 2 failed in 1.25s ==============================
    VERIFIER-MUTANT vidbyte.harnesses.native.codex.skill_functions loaded_from_mutant=True
X17_fix_new_tests: exit=0 :: ============================== 2 passed in 1.11s ==============================
    VERIFIER-MUTANT vidbyte.harnesses.native.codex.skill_functions loaded_from_mutant=True
X17_fix_area: exit=0 :: ================ 890 passed, 2 skipped, 1 deselected in 53.18s ================
    VERIFIER-MUTANT vidbyte.harnesses.native.codex.skill_functions loaded_from_mutant=True
```

The control is a copy with only a no-op comment, and it stays red, so the green comes from the fix and not from the copy mechanism. With the fix, the whole area has no failures (the inherited test is deselected).

**Gates on the worktree:**

- **Area pytest:** `3 failed, 683 passed, 2 skipped in 52.58s`. The failures are the 2 new tests and the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`.
- **Lint:** `SDK-LINT: PASS`.
- **CI view with openai-codex hidden:** `57 passed, 142 skipped`. The 2 new tests skip there, which is the expected behaviour.

**Open items:**

1. **A second rebuild has the same defect.** `host.py:476` (spawn batch, after some turns started) rebuilds the error the same way and drops `error_type` and `thread_id` too. It is outside R-17's scope, and it has no test.
2. **The mapper does not fill `thread_id` either.** `CodexErrorMapper.error` receives `thread_id` but writes it only into the message. Whether it should also set the #1116 field is a design choice for S5 or the owner. If it does, R-17 stops being latent and the stand-in mapper becomes the real one.
3. **INV-22 and INV-35 could name every field.** Their spec text could say "every field" instead of listing code, operation and next step.

## r5: R-18, the spawn-batch rebuild keeps every CodexAgentError field

The orchestrator accepted r4's open item 1 as R-18, a sibling of R-17. The test is in commit `b769621c`, `test(codex): prove the spawn-batch rebuild keeps every CodexAgentError field [R-18]`. It stays red until S5 iteration 4 fixes both sites. The orchestrator ruled on r4's other open items: the mapper filling `thread_id` is a follow-up for the owner, with no test, and S5 rewords the spec text of INV-22 and INV-35.

**The defect.** When `launch_codex_subagents` fails after some turns started, it interrupts them and then rebuilds the error at `vidbyte/harnesses/native/codex/host.py:476`. The rebuild passes only the message plus a count sentence, the code, the operation and the next step, so `error_type` and `thread_id` arrive empty. The governing rules are INV-37, AC-18, EC-52 and D-22 of `docs/spec/codex-host/spec.md`. EC-52 promises "the mapped error, saying k turns were started and interrupted", which means the mapped error itself, with the count added.

**The test**, `test_codex_host_review_gaps.py::CodexHostLaunchRebuildFieldTests::test_a_launch_that_fails_midway_keeps_every_field_of_the_mapped_error`, uses the real path:

1. The host opens.
2. The connection's mapper is swapped for `FieldCarryingMapper`.
3. The test launches three prompts, and the third `turn/start` fails with −32603 over the fake app-server.

It then checks four things:

- the original carried both fields;
- the message is the original plus a sentence that names 2 turns as started and interrupted;
- the sentence's words are right (the spec gives no literal for it, so only its words are checked, not its wording);
- none of the 11 kept fields changed.

**Where it lives.** The test goes in `test_codex_host_review_gaps.py`, because that module already holds the review-found launch windows. It does not go in `test_codex_host_threads.py`: this run's AC-35 says that file stays unedited.

**Shared helper.** `FieldCarryingMapper`, `KEPT_ERROR_FIELDS` and `changed_error_fields` moved from `test_codex_host_goal_skills.py` to `codex_host_support.py`, because two modules now use them. The R-17 tests keep their names and fail exactly as they did in r4.

**Red on the current code, failing only on the two dropped fields:**

```
E       - {'safe_runtime_details': ({'error_type': '',
E       -                            'operation': 'launch_codex_subagents'},
E       -                           {'error_type': 'InternalRpcError',
E       -                            'operation': 'launch_codex_subagents'}),
E       -  'thread_id': ('', 'thr-3')}
FAILED tests/features/codex_host/test_codex_host_review_gaps.py::CodexHostLaunchRebuildFieldTests::test_a_launch_that_fails_midway_keeps_every_field_of_the_mapped_error
```

The message checks, which run first, pass. Five back-to-back runs of the module each gave `1 failed, 15 passed`.

**Green in a scratch copy** (`s4-verifier/s2r5_green.py`; the copy is written to `mut/`, and the worktree is not touched). The analogous fix is:

```python
raise CodexAgentError(message, failure_code=exc.failure_code, operation=exc.operation, error_type=exc.safe_runtime_details.get("error_type", ""), next_step=exc.next_step, thread_id=exc.thread_id) from None
```

```
X18_none: exit=1 :: ============================== 1 failed in 1.27s ==============================
    VERIFIER-MUTANT vidbyte.harnesses.native.codex.host loaded_from_mutant=True
X18_fix: exit=0 :: ============================== 1 passed in 1.11s ==============================
    VERIFIER-MUTANT vidbyte.harnesses.native.codex.host loaded_from_mutant=True
X17_X18_fix_area: exit=0 :: ================ 891 passed, 2 skipped, 1 deselected in 54.03s ================
    VERIFIER-MUTANT vidbyte.harnesses.native.codex.host loaded_from_mutant=True
    VERIFIER-MUTANT vidbyte.harnesses.native.codex.skill_functions loaded_from_mutant=True
```

`X18_none` is the control: a copy with only a no-op comment, and it stays red. With both fixes (R-17 and R-18), the whole area has no failures; the inherited test is deselected.

**Gates on the worktree:**

- **Area pytest:** `4 failed, 683 passed, 2 skipped in 52.22s`. The failures are the 2 R-17 tests, the R-18 test, and the inherited `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`.
- **Lint:** `SDK-LINT: PASS`.
- **CI view with openai-codex hidden:** `57 passed, 143 skipped`.
