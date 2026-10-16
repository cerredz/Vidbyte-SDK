# Test plan: CodexHost thread helpers and built-in skill functions
Spec: `docs/spec/codex-host-thread-helpers/spec.md` r3 · Framework: pytest 8.3.5 with pytest-asyncio 1.3.0, running `unittest.IsolatedAsyncioTestCase` classes on `HostTestCase` (`tests/features/codex_host/codex_host_support.py`) · Prior art copied: `tests/features/codex_host/test_codex_host_threads.py` (exact params at 246-268), `test_codex_host_review_goals.py` (goal request order), `test_codex_host_tools.py` (stub host, cap, error results), `test_codex_host_lifecycle.py` (section 4 snippet, guards)

Five new files sit in `tests/features/codex_host/`. Two run on CI: `test_codex_host_helper_surface.py` (10 tests) and `test_codex_host_helper_tools.py` (10). Three need the `codex` extra, so CI skips them and they run locally: `test_codex_host_thread_helpers.py` (29), `test_codex_host_goal_skills.py` (22) and `test_codex_host_helper_lifecycle.py` (5). Host tests drive a real `CodexHost` over the real openai-codex `CodexClient` subclass `client_class(server)` at the §13 seam, with `shutil.which` patched. Nothing else is mocked. Tool tests use `StubCodexHost`.

Below, "the log" means `server.requests`: the fake records every request the real client writes, in order. "Exact" means `assertEqual` on the whole list or dict, never a subset check.

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | helper_lifecycle → `test_the_section_4_snippet_prints_its_seven_lines` | integration (fake app-server) | The §4 snippet, verbatim → a wrong line: an unsorted listing, a title of `""` instead of None, a goal without its budget, a docs run without its final answer, a turn page missing items, or a delete tool counted (27, or `True`) | The 7 printed lines are compared exactly. The docs thread must be gone from the fake's store afterwards. |
| AC-2 | thread_helpers → `test_recent_threads_come_newest_first_without_sub_agents_or_a_preflight` | integration | 8 threads, and the 2 subagent threads are the newest → they head the result when `sourceKinds` is dropped. A preflight call is sent. | The subagent threads are the newest on purpose, so an unfiltered list fails the exact result. The params are an exact one-element list, and the log is exactly `["thread/list"]`. |
| AC-3 | thread_helpers → `test_a_cwd_goes_on_every_page_and_an_empty_cwd_sends_none` | integration | A walk of 2-thread pages in `WORK_A` → `cwd` is missing from page 2, or `cwd: ""` is sent for every folder | Both pages' params are exact. The `""` case first asserts that requests were sent, then checks each one. |
| AC-4 | thread_helpers → `test_the_walk_asks_for_the_remaining_count_with_each_cursor` | integration | 10 threads, 2 per page, `limit=5` → the caller's `limit` is resent on every page, or the cursor is dropped | Exact params `[limit 5; limit 3 + cursor; limit 1 + cursor]`. The mutant "limit sent as total, not remaining" is killed. |
| AC-5 | thread_helpers → `test_a_repeated_cursor_ends_the_walk_without_duplicates` | integration | The legacy fake repeats `cursor-after-page` and returns every thread on every page → an endless walk, or duplicates | Exact result (3 summaries, each once) and exactly 2 requests. The mutants "repeated cursor not detected" and "no duplicate filter" are killed. |
| AC-6 | thread_helpers → `test_since_returns_the_inclusive_window_and_stops_at_the_first_older_thread` | integration | Threads at T+100, T+50, T, T−1… → T is dropped (exclusive filter), or a page after T−1 is read | Exact result of 3, and exactly 2 requests. The mutant "since exclusive" is killed. |
| AC-7 | thread_helpers → `test_an_empty_window_is_an_empty_tuple_and_milliseconds_lie_in_the_future` | integration | `since` one day ahead, or in milliseconds → an error is raised, or threads are returned | The test asserts `()` and that one `thread/list` request was sent, so the call did run. |
| AC-8 | thread_helpers → `test_search_sends_the_search_term_and_refuses_a_blank_query` | integration | `"fix"` → `searchTerm` is missing. `""` or `"   "` → accepted. | Exact params, and an exact `QUERY_MESSAGE` with no requests. The mutant "blank query accepted" is killed. |
| AC-9 | thread_helpers → `test_bad_limits_and_timestamps_are_refused_before_any_request`; helper_tools → `test_bad_arguments_are_refused_before_the_host` | integration; unit | `limit` 0, −1, `True` or 1001, or `since` −1, `True` or 1.5 → a request is sent, or `True` passes as 1 | `LIMIT_MESSAGE` and `SINCE_MESSAGE` must match exactly. The bounds 1 and 1000 must then succeed, so a guard that refuses everything fails. The mutant "limit upper bound unchecked" is killed. |
| AC-10 | thread_helpers → `test_titles_parents_and_models_map_as_section_6_1_says`; helper_surface → `test_the_summary_harness_is_fixed_to_codex` | integration; unit | `name` null or `""` → `""`. The spawn parent wins over the fork parent. A null `model` stays None. | Field-by-field lists are checked through the listing and again through lineage. The mutants "empty title kept" and "parent prefers spawn parent" are killed. |
| AC-11 | thread_helpers → `test_the_lineage_walks_fork_and_spawn_parents_to_the_root` | integration | A → B → C → reads with turns, the wrong order, or no spawn-parent hop | Exact read params `{"threadId", "includeTurns": False}` ×3, plus a 4-hop mixed chain. |
| AC-12 | thread_helpers → `test_an_unknown_or_refused_ancestor_ends_the_walk_without_an_error` | integration | A missing ancestor, or a −32602 ancestor read → an error is raised, or the dangling parent id is lost | The last summary's `parent_thread_id` must equal the missing id, so a walk that drops the parent fails. |
| AC-13 | thread_helpers → `test_an_unknown_start_is_not_found_and_a_cycle_reads_each_thread_once` | integration | An unknown start → `()`. A 2-cycle → an endless walk. | Exactly 2 reads. The mutant "lineage revisits a cycle" is killed. |
| AC-14 | thread_helpers → `test_a_chain_deeper_than_the_bound_returns_exactly_the_bound` | integration | A 102-thread chain → 101 or unbounded reads | Exactly 100 summaries and 100 reads, and the last parent is not None. The mutant "lineage depth off by one" is killed. |
| AC-15 | thread_helpers → `test_turns_come_with_their_items_and_the_cursor_and_limit_pass_through` | integration | 2 stored turns → a default `limit` is sent, reasoning `content` leaks, the turn order is wrong, or a null cursor becomes None | Exact params with no `limit`, exact turn fields, reasoning fields `== {"summary": [...]}`, and the canary absent. The mutants "reasoning content leaks" and "turns default limit sent by host" are killed. |
| AC-16 | thread_helpers → `test_an_unknown_thread_is_not_found_before_any_turn_listing` | integration | An unknown id → `thread/turns/list` is sent | The log is exactly `["thread/read"]`. |
| AC-17 | thread_helpers → `test_an_idle_or_failed_thread_is_compacted_without_a_goal_check_or_resume`; helper_lifecycle → `test_helpers_send_no_check_and_reads_leave_a_not_loaded_thread_unloaded` | integration | idle or `systemError` → a goal check, a resume or a preflight is sent | The log is exactly `[read, compact/start]` with params `{"threadId"}`. The mutant "compact goal checks every status" is killed. |
| AC-18 | thread_helpers → `test_a_not_loaded_thread_without_a_goal_is_checked_then_resumed_as_continue_resumes` | integration | `notLoaded` without a goal → no resume, or resume params that differ from those a continue sends. `get_codex_goal` → it resumes. | Exact method order. The resume params are compared with those of a real `continue_codex_thread` on another `notLoaded` thread, an oracle independent of the code under test. The mutant "compact never resumes" is killed. |
| AC-19 | thread_helpers → `test_this_hosts_own_running_turn_refuses_compact_and_delete_before_any_request`; `test_a_thread_codex_reports_active_refuses_compact_and_delete_after_one_read` | integration | A turn of its own → a request is sent. An `active` read → compact or delete is sent. | The exact `BUSY_TEXT` or `RUNNING_THREAD_MESSAGE` with the thread suffix, an empty log or exactly `["thread/read"]`, and the thread still stored. The mutant "delete ignores active" is killed. |
| AC-20, AC-22 | thread_helpers → `test_an_unknown_thread_is_not_found_and_a_second_delete_finds_nothing` | integration | An unknown id → compact, delete or `goal/get` is sent. A second delete → success. | The log is exactly `["thread/read"]` per method, and `[read, delete, read]` for the double delete. |
| AC-21 | thread_helpers → `test_delete_never_resumes_and_a_deleted_thread_is_gone_but_its_usage_stays`; helper_tools → `test_the_toolset_appends_eleven_tools_and_none_is_delete`, `test_no_tool_reaches_delete_codex_thread` | integration; unit | `notLoaded` delete → a resume is sent. A delete tool exists, or a tool calls the host's delete. | Exact `[read, delete]` with params `{"threadId"}`. The stub host records each call, so a delete tool is visible. |
| AC-23 | thread_helpers → `test_a_compact_in_flight_holds_the_thread_until_it_ends`; `test_a_failed_or_cancelled_compact_releases_the_thread` | integration | A held `compact/start` → continue, review, compact or delete slips through. A failed or cancelled compact → the thread stays busy. | The four refusals send nothing, the continue after release succeeds, and compact then delete succeed after the failure and the cancel. The mutants "compact does not reserve" and "compact keeps its reservation on error" are killed. |
| AC-24 | goal_skills → `test_the_goal_record_mirrors_the_stored_goal_for_every_status` | integration | Every one of the 6 statuses, with no budget, without a goal (loaded or `notLoaded`), or unknown → a wrong field, an enum missing, or a resume | Whole-record equality per status, the log exactly `[read, goal/get]`, and the status unchanged. |
| AC-25 | goal_skills → `test_a_goal_run_starts_goal_mode_sets_the_budget_and_reads_the_goal_back` | integration | `run_codex_goal("ship it", 500)` → a `/goal` text turn, no budget set, no read-back | The exact per-thread method list, exact budget params, zero `turn/start`, and zero cancels. |
| AC-26, EC-29 | goal_skills → `test_a_goal_that_did_not_take_is_cancelled_once_and_reported` | integration | A different objective, a different budget or no goal → no cancel, two cancels, or the wrong message. A failing pause and interrupt → the mismatch is hidden. | Exact messages. The one-worker barrier makes a late second cancel visible. The mutants "goal mismatch not cancelled" and "budget not compared" are killed. |
| AC-27 | goal_skills → `test_a_goal_check_that_fails_cancels_the_run_and_keeps_its_error` | integration | `goal/get` −32603 → no cancel, the operation renamed, or no `GOAL_UNCHECKED` suffix | `endswith` the formatted suffix, the operation `get_codex_goal`, and 1 cancel after the barrier. The mutant "goal check error loses its suffix" is killed. |
| AC-28, EC-26 | goal_skills → `test_bad_goal_arguments_are_refused_before_any_request` | integration | `""`, budget 0 or `True`, an ephemeral thread, or a request carrying a prompt or goal → requests are sent | The log is empty. `OWN_INPUT_MESSAGE` must match exactly. |
| AC-29 | goal_skills → `test_skills_are_listed_for_a_folder_or_for_the_app_servers_own` | integration | `"/w"` or `""` → wrong `cwds`, the order changed, scope as a str, or a preflight | Tuple equality of `CodexSkillInfo` and exact params. The mutant "skills listed without cwd" is killed. |
| AC-30, INV-27 | goal_skills → `test_a_skill_run_sends_the_skill_as_input_and_confirms_it_once`; `test_a_skill_run_keeps_the_callers_posture_and_lists_skills_for_its_folder` | integration | An enabled `s` → the skill is sent as text, the path is wrong, there is no read-back, the read-back is not limited to 1 turn, or the request's folder and model are ignored | The exact 2-item input, exactly one `turns/list` with exact params after `turn/start`, and 0 interrupts. The mutant "no read-back" is killed. |
| AC-31, EC-30, EC-32, EC-34 | goal_skills → `test_an_unknown_or_disabled_skill_is_refused_before_any_thread_starts`; `test_the_not_found_message_names_the_folder_and_bounds_the_list` | integration | `zz`, `OpenAI-Docs` (case), disabled `rv`, or 55 enabled skills → the wrong code, disabled names listed, an unbounded list, or `thread/start` sent | The prefix and tail are exact, and names are extracted as tokens, so a substring of a path cannot pass. The `"none"` message is exact. The mutants "names not capped" and "skill path leaks into not-found" are killed. |
| AC-32 | goal_skills → `test_the_docs_run_is_the_skill_run_for_openai_docs` | integration | `run_codex_openai_docs` → another skill name, or the errors carry `run_codex_skill` | The not-found, disabled, success and dropped cases each check the operation. The mutant "docs runs another skill" is killed. |
| AC-33, EC-38 | helper_tools → `test_the_toolset_appends_eleven_tools_and_none_is_delete`, `test_a_full_cap_refuses_every_run_tool_without_reaching_the_host`, `test_new_codes_become_error_results_with_their_next_steps`; tools → `test_toolset_holds_the_fifteen_tools_with_their_spec_schemas`, `test_every_tool_turns_host_errors_into_error_results` | unit (stub host) | 26 tools in the wrong order, a wrong schema, a run tool that skips the cap or does not own its handle, or a host error that raises | `names()` equals `TOOL_NAMES`, the cap refusal reaches no host call, and the error output is the whole formatted text. The mutants "run tool skips the cap" and "run tool does not own its handle" are killed. |
| AC-34 | helper_lifecycle → `test_every_new_method_refuses_before_open_after_close_and_from_another_loop` | integration | Each of the 12 methods before open, from another loop, or after close → a request, the wrong error, or a write after close | The method dict is asserted to equal `HELPER_METHODS` first, so no method is skipped. The request count is unchanged, and the fake logs `write_after_close`. The mutant "host guard skipped" is killed. |
| AC-35 | the whole pack run (see the Red run) | regression | A helper changes `list_codex_threads` params or `read_codex_thread` output | `test_codex_host_threads.py` is unedited. Only the §13 pins changed. |
| AC-36 | helper_surface → `test_the_four_codes_sit_between_turn_timed_out_and_input_empty`; records → `test_new_failure_codes_sit_right_after_run_option_unsupported`, `test_each_new_code_has_its_classification_row_and_next_step` | unit | The 4 codes are misplaced, or a classification row or next step is missing | Exact slices of the `FailureCode` member order, and the rows equal the spec's text. |
| AC-37, EC-35 | helper_lifecycle → `test_a_missing_method_is_protocol_mismatch_with_the_functions_own_operation` | integration | −32601 for each of the 5 methods → `api_error`, or the wrong operation | One row per method. The skill run's `skills/list` −32601 keeps `list_codex_skills` and sends no `thread/start`. The mutant "skill listing error renamed" is killed. |
| AC-38, EC-42 | thread_helpers → `test_a_not_loaded_thread_with_an_unfinished_goal_is_refused_before_any_resume` | integration | `notLoaded` with any of the 5 unfinished statuses → it is resumed, the message is wrong, or the reservation is kept | The exact message with the wire status, the log exactly `[read, goal/get]`, and a second compact must hit the goal check again, not `session_busy`. The mutant "compact skips the goal check" is killed. |
| AC-39, EC-46 | goal_skills → `test_input_never_recorded_or_recorded_without_the_skill_stops_the_run_once` | integration | No `userMessage` ever, or one without the skill entry → the wrong read count, 0 or 2 interrupts, or the wrong message | Exactly 10 reads, then exactly 1. One interrupt is checked before and after the one-worker barrier. The mutants "read-back one attempt short", "read-back ignores the skill entry" and "skill miss not interrupted" are killed. |
| AC-40 | goal_skills → `test_a_read_back_that_fails_interrupts_once_and_keeps_its_error` | integration | `turns/list` −32603 → no interrupt, the operation renamed, or no `SKILL_UNCHECKED` suffix | The operation `list_codex_turns`, `endswith` the suffix, and 1 interrupt after the barrier. |
| AC-41, EC-47 | helper_tools → `test_the_turns_tool_asks_for_a_small_page_unless_given_a_limit`; thread_helpers → AC-15's test | unit; integration | The turns tool with no `limit` → the host gets None. The host method → it sends a `limit`. | The stub records `limit=3`, then 7. The host's exact params have no `limit`. The mutant "turns tool default limit missing" is killed. |
| AC-42, EC-37, EC-48 | goal_skills → `test_bad_skill_arguments_are_refused_before_any_request` | integration | An ephemeral thread, a request with a prompt or goal, an empty name, or an empty prompt → `skills/list` or `thread/start` sent | Exact `EPHEMERAL_SKILL_MESSAGE`, `OWN_INPUT_MESSAGE` and `SKILL_NAME_MESSAGE`, and an empty log. The mutant "ephemeral not refused" is killed. |
| AC-43, EC-50 | goal_skills → `test_a_deadline_shorter_than_the_interval_allows_one_read` | integration | A deadline below the interval → a second read, a sleep past the deadline, or a `TimeoutError` | The thread's read and interrupt methods are exactly `[turns/list, turn/interrupt]`, and `{seconds}` is the patched 0.25. The mutant "read-back without deadline" is killed. |
| EC-5 | thread_helpers → `test_endless_cursors_end_after_the_page_bound` | integration | Empty pages with fresh cursors → an endless walk | Exactly 1000 `thread/list` requests. The mutant "page bound ignored" is killed. |
| EC-14 | thread_helpers → `test_an_ancestor_read_that_times_out_propagates` | integration | A held ancestor read past `CODEX_HOST_REQUEST_TIMEOUT_SECONDS` (patched to 0.3) → a short chain returned as complete | It must raise `api_error` with the lineage operation. The mutant "lineage swallows a timeout" is killed. |
| EC-15, EC-16 | thread_helpers → `test_a_running_turn_is_listed_with_its_items_so_far`; `test_a_not_loaded_thread_is_read_without_loading_it` | integration | A running turn → a completed status. A `notLoaded` thread → resumed. | `RUNNING` with `completed_at` None. No resume or `turn/start`, and the next read still says `NOT_LOADED`. |
| EC-27, EC-28 | goal_skills → `test_a_goal_that_completed_before_the_check_still_returns_the_handle`; `test_a_goal_run_cancelled_during_its_check_is_cancelled_once` | integration | A complete goal → refused. A cancel during `goal/get` → no cancel. | 0 cancels with a handle. `CancelledError` and exactly 1 cancel after the barrier. The mutant "goal check cancel not stopped" is killed. |
| EC-31, EC-45 | goal_skills → `test_the_first_enabled_skill_of_a_shared_name_is_used`; `test_input_recorded_late_is_found_on_a_later_read` | integration | A disabled duplicate listed first → its path is sent. Input visible only on the 3rd read → refused. | The exact input path. Exactly 3 reads and 0 interrupts. The mutant "skill path from first match, even disabled" is killed. |
| INV-35 | goal_skills → `test_a_failed_interrupt_does_not_hide_the_miss`; `test_a_skill_run_cancelled_during_its_read_back_is_interrupted_once` | integration | A failing interrupt → its error replaces the miss. A cancel during the read-back → no interrupt. | The exact dropped message. The interrupt waited for, then exactly 1 after the barrier. |
| INV-10, INV-33 | helper_lifecycle → `test_helpers_send_no_check_and_reads_leave_a_not_loaded_thread_unloaded` | integration | One of the nine non-spending helpers sends a preflight, or a READ helper loads a `notLoaded` thread that has a paused goal | All nine run: the 7 READ helpers, then compact and delete. The reads' log must hold no `thread/resume` and no `turn/start`, and a later read still reports `NOT_LOADED`. The whole log must hold none of the 4 preflight methods. The mutant "listing sends a preflight" is killed. |
| INV-29 | helper_lifecycle → `test_skill_paths_descriptions_and_goal_objectives_stay_out_of_error_texts` | integration | Canaries in a skill path, a skill description or a goal objective → they reach the error text | `error_texts` walks the message and the visible chain. |
| INV-27, INV-28 | helper_tools → `test_listing_tools_pass_their_arguments_and_the_default_limit`, `test_run_tools_pass_the_scope_posture_and_their_own_input`, `test_a_failed_or_cancelled_run_releases_its_slot`, `test_outputs_are_the_returned_records_as_json_or_the_spec_texts` | unit | No default limit 20, the run tools without `spawn_defaults`, a leaked slot, or compact as JSON instead of `COMPACT_STARTED_TEXT` | Exact stub call records and exact outputs. The mutants "goal tool ignores spawn defaults", "compact tool returns JSON" and "since tool accepts bool" are killed. |
| §8.5, §9.1 to §9.3 | helper_surface → the 8 record, enum, constant and signature tests | unit | Wrong names, field order, validation, enum values, operation order, constants, message texts or host signatures | Exact `inspect.signature` and `dataclasses.fields` order, and the texts copied verbatim from the spec. |

## Tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| EC-49: listing the turns of an ephemeral thread | The fake can only repeat assumption A-21, so the test would prove the fake, not Codex. |
| EC-36: a close during a listing or lineage walk | The guard test proves `process_exited` for every method on a closed host. The existing pack's close tests prove that an in-flight call ends with `process_exited`. A close-mid-walk race adds timing risk and no new branch. |
| EC-24: overload retries on `thread/delete` | The retry belongs to openai-codex's `request_with_retry_on_overload`, which `test_codex_host_sdk_contract.py` already pins. |
| EC-19, EC-20, EC-21, EC-33, EC-41, EC-43, EC-44 | These are accepted limitations about what Codex does after it accepts a request. A fake would only replay the assumption. |
| NFR-2, NFR-7, NFR-8 and NFR-9: file sizes, description sentence counts, house style and wrapper size | Lint (A001, A002, S024, S064) and review check these. A sentence count says nothing about meaning. |
| R-7: `skill_functions` never imports `host.py` | §8.5 marks it as a design seam, not test-facing. Lint and mypy see the import graph. |
| Unbuilt Q-n behavior (Q-13, Q-16, Q-19) | Not built. The briefing says not to test it. |
| A `limit` upper bound at the tool layer | The bound is the host's check, and it is proven over the fake in AC-9. A stub host would accept anything. |
| Property-based tests | `hypothesis` is not a dependency. The domains (statuses, scopes, bad-argument rows) are small, so exhaustive tables cover them. |
| Live Codex runs (goal, skill, `openai-docs`) | They spend the user's plan (NG-15). AC-1 is proven at the seam. |

## Red run (before implementation)

Bootstrap: none needed — orchestrator-built venv `C:/Users/422mi/vidbyte-repos/worktrees/.venvs/codex-host-thread-helpers`, `pip install -e .[dev,codex]` from the worktree (Python 3.11.0, openai-codex 0.162.1).

Baseline at `5a37caf1`, before S2: `PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host tests/features/harness_threads` → `1 failed, 551 passed, 2 skipped`.

```
PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host/test_codex_host_helper_surface.py   → 10 failed in 0.85s
PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host/test_codex_host_helper_tools.py     → 10 failed in 0.91s
PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host/test_codex_host_thread_helpers.py   → 29 failed in 1.88s
PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host/test_codex_host_goal_skills.py      → 22 failed in 1.75s
PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host/test_codex_host_helper_lifecycle.py → 5 failed in 1.21s
PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host tests/features/harness_threads      → 91 failed, 537 passed, 2 skipped in 48.13s
```

91 = 76 new tests + 14 existing tests that the §13 pins turn red + 1 inherited failure. 537 = 551 − 14.

- **The 76 new tests fail for the right reason.** Each fails because a spec name is missing:
  - `AttributeError: 'CodexHost' object has no attribute '<method>'` for all 12 methods;
  - `ImportError` for `CodexThreadSummary`, `CodexThreadGoal`, `CodexSkillInfo`, `CodexStoredTurn` and `CodexSkillScope`;
  - `ModuleNotFoundError: vidbyte.harnesses.native.codex.thread_helpers`, and no attribute `skill_functions`;
  - the missing constant `CODEX_THREAD_COMPACT_METHOD`;
  - `the toolset has no tool named <tool>`;
  - empty-vs-expected order diffs for the operations and the codes.

  None fails from a fake handler error, a timeout, or a `KeyError` in the test code.
- **The 14 existing tests that go red are each an authorized §13 pin or its direct consequence:**
  - `test_codex_host_lifecycle.py::test_the_section_4_snippet_prints_its_three_lines`: "15" becomes "26".
  - `test_codex_host_packaging.py::test_imports_never_load_the_sdk_and_entering_reports_the_pip_extra`: (15 → 26).
  - `test_codex_host_packaging.py::test_existing_export_lists_gain_only_the_new_names_in_place`: `ENUMS_CODEX_ORDER` gains `CodexSkillScope`.
  - `test_codex_host_packaging.py::test_new_packages_export_exactly_their_spec_lists`: `RECORD_EXPORTS` now has 20 names, and `builtin_codex.__all__` follows `TOOL_TABLE`.
  - `test_codex_host_records.py`, 6 tests:
    - `test_valid_baselines_construct_frozen_slotted_records` and `test_each_invalid_record_raises_configuration_error_naming_the_field`: `_valid_kwargs` imports `CodexStoredTurn`;
    - `test_each_new_code_has_its_classification_row_and_next_step` and `test_new_failure_codes_sit_right_after_run_option_unsupported`: 19 codes;
    - `test_new_enums_have_exactly_the_spec_members_and_values`: `CodexHostOperation`, with `DELETE_CODEX_THREAD`;
    - `test_wire_values_match_openai_codex`: `CodexSkillScope`.
  - `test_codex_host_tools.py`, 4 tests, all driven by `TOOL_TABLE`:
    - `test_toolset_holds_the_fifteen_tools_with_their_spec_schemas` (15 != 26);
    - `test_default_policy_allows_the_read_tools_and_denies_the_write_tools`;
    - `test_every_tool_turns_host_errors_into_error_results`;
    - `test_mcp_server_lists_and_runs_the_toolset`.
- **The inherited failure** is `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, for its existing reason.
- **CI without the extra.** With openai-codex hidden from import, the pack gives `32 failed, 24 passed, 136 skipped`. The three SDK files skip whole. The two CI-visible files fail for the same missing names. One packaging probe still ran here, because it starts a child interpreter that sees the SDK; on real CI it skips.
- **Lint.** `PYTHONPATH=$(pwd) <venv python> lint/run.py` with the new files staged gives `SDK-LINT: PASS`. S020 has no finding in this pack.

**Proof the tests can pass, and that each can fail.** A scratch prototype implementation lived only in the session scratchpad, never under `vidbyte/` and never on this worktree's `sys.path`. Against it:
- the pack passed 191 tests. The 1 failure was environmental: the scratch copy has no `REPO_MAP.md`.
- 45 of 45 single-rule mutants of it were killed by the new tests.
- 6 back-to-back runs of the 76 new tests all passed.

## Notes for the implementer

The tests may not change (S3 may not touch `tests/`), so these are the readings they commit to:

1. **The read-back bounds.** `skill_functions.py` must import `CODEX_HOST_INPUT_CHECK_INTERVAL_SECONDS` and `CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS` by name, and read them as module globals at call time. The tests patch them there (§13). `INPUT_NOT_RECORDED_MESSAGE` takes `seconds=CODEX_HOST_INPUT_CHECK_DEADLINE_SECONDS` through plain `str.format`. The tests expect `600.0` and `0.25` exactly, so do not use `:g` or an `int()`.
2. **`{status}` in `GOAL_UNFINISHED_MESSAGE` is the wire value**, for example `usageLimited`. On Python 3.11, `"{status}".format(status=CodexGoalStatus.USAGE_LIMITED)` gives `CodexGoalStatus.USAGE_LIMITED`, so pass `.value`.
3. **Errors go through `CodexErrorMapper.error(code, message, operation, thread_id)`.** The tests compare `message + " Thread: <id>."` exactly for `BUSY_MESSAGE`, `RUNNING_THREAD_MESSAGE`, the goal mismatch texts, `SKILL_DROPPED_MESSAGE` and `INPUT_NOT_RECORDED_MESSAGE`. `SKILL_DISABLED_MESSAGE` and the `"none"` not-found text are compared with no suffix, because no thread exists yet.
4. **The `{names}` list.** The not-found test reads the names list separator-agnostically: tokens after the prefix, with `" and N more."` at the end. Comma-separated, as §9.2 says, passes. Name only enabled skills, and never a path.
5. **The listing walk.**
   - Send `limit - len(collected)` on each page.
   - Stop when you have `limit` threads, when `nextCursor` is null or empty, when a cursor was already sent, or after `CODEX_HOST_THREAD_LIST_MAX_PAGES` pages.
   - The legacy fake gives exactly 2 requests for AC-5: the first cursor is new, and the second repeats.
   - For `since`, return at the first thread with `updated_at < since`, without reading another page.
   - Leave `cwd` out when it is `""`. Send `searchTerm` only for search.
6. **The turns listing and lineage.**
   - `list_codex_turns` sends `{"threadId", "itemsView": "full", "sortDirection": "asc"}`, plus `cursor` and `limit` only when the caller gives them. The existence read comes first: the log is `[thread/read, thread/turns/list]`.
   - Lineage reads with `includeTurns: False`. It catches only `session_not_found` from ancestors. Any `thread/read` JSON-RPC error maps to not found, through `_rpc_code`. A timeout must propagate as `api_error`.
7. **Compact and delete.**
   - Both call `require_idle` before any request. Both reserve the thread in the registry, and release it in `finally`, on success, failure, cancel and `goal_unfinished` alike.
   - Compact reads the goal only for `notLoaded`. It refuses every status except `complete` and None. It resumes with the same params `continue_codex_thread` sends: the test compares them.
   - Delete never resumes.
8. **The goal run.** It sends the existing spawn goal sequence, then `get_codex_goal`'s `[thread/read, thread/goal/get]`. A goal cancel is counted from the SDK's `cancel_goal_operation`, so use `host.interrupt_codex_turn(handle)` once. The tests run with one host worker and then do a barrier read, so a second stop queued in the background is caught.
9. **The skill run.**
   - It calls `host.list_codex_skills(spawn.thread.cwd)`, so a `skills/list` failure keeps the operation `list_codex_skills` (AC-37). A not-found or disabled refusal carries the run's own operation.
   - The read-back calls `host.list_codex_turns(thread_id, limit=CODEX_HOST_INPUT_CHECK_TURN_LIMIT)`. Its error keeps `list_codex_turns` and gains `SKILL_UNCHECKED_MESSAGE`.
   - Check `ephemeral` and own input before any request.
10. **The tools.**
    - The listing tools default `limit` to 20, and JSON `null` counts as omitted. The turns tool sends `CODEX_HOST_TURNS_TOOL_DEFAULT_LIMIT` (3) when no limit is given.
    - The run tools reserve one slot, call the host with `request=self._scope.spawn_defaults`, release the slot in `finally`, then `own((handle,))`.
    - Compact returns `COMPACT_STARTED_TEXT.format(thread_id=...)`, and a missing goal returns `NO_GOAL_TEXT`.
11. **`CodexThreadSummary` mapping.** `title = name or None`. `parent_thread_id = forkedFromId or parentThreadId or None`. `model = model or ""`. `harness` is fixed to `"codex"`.
