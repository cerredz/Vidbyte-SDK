---
spec: infinite-memory-derived-events
spec_revision: 3
stage: S2 test author
base_commit: 181f1992ce936f139b7d18f9ae999c97dcd3b005
written: 2026-10-20
---

# Test plan: InfiniteMemoryAgent derived run events

This plan maps every requirement of `spec.md` r3 to the tests that prove it. All tests are in `tests/features/infinite_memory_agent/` and follow that pack's rules:

- Only the model runner is scripted (`ScriptedTree` patches `BaseAgent._runner_for_model`). The workspace, journal, `ParallelPipeline`, `DelegationLimitsMiddleware`, the permission policy, the loop's `call_contexts`, `bash`, and the disk are real.
- Sinks only record what they receive. Every assertion runs after the run.
- Feature symbols are imported inside the test functions. Each new-name import is placed after the first behaviour assert where one exists, so a red test reports the missing behaviour rather than the missing import.
- Nothing sleeps or reads the wall clock. `Gate` and `Signal` order concurrent agents, and paths are built with `tmp_path` and `Path`.

**Files** (aliases used in the tables):

| Alias | File | Tests (items) |
|---|---|---|
| DP | `test_infinite_memory_derived_pairs.py` (new) | 17 functions (21 items; 15 functions and 17 items before the S4 strengthening) |
| DF | `test_infinite_memory_derived_refusals.py` (new) | 10 functions (41 items: 32 refusal cases + 9) |
| DN | `test_infinite_memory_derived_run.py` (new) | 15 functions (18 items) |
| DR | `test_infinite_memory_derived_records.py` (new) | 11 functions (11 items) |
| ES, EP, EL, ER | `test_infinite_memory_events_{stream,pairs,lifecycle,records}.py` (PR #1159, updated where this spec changes them) | see "Existing tests updated" |
| HO, CT | `test_infinite_memory_handoff.py`, `test_infinite_memory_contract.py` (updated pins) | |
| fixtures | `infinite_events_fixtures.py` (`AC2_KINDS`, `AC7_LIMITS`, `ac7_tree`), `infinite_memory_fixtures.py` (`tool_calls`/`ToolsStep`) | |

**Levels:**
- *run*: a scripted `agent.run`, `arun`, `resume`, or `run_handoff` over a real workspace.
- *component*: real `InfiniteLaunchTool`, `InfinitePair`, `InfiniteRunJournal`, `InfiniteWorkspace`, and `InfiniteEvents` objects driven directly.
- *unit*: one function, record, or enum.
- *contract*: names, signatures, fields, and constants checked against §8.5, §9.2, and §9.3.

## Coverage map

### Acceptance criteria

| Spec ID | Test | Level | Failure caught | How it could pass vacuously and why it does not |
|---|---|---|---|---|
| AC-1 | DN::`test_the_section_4_snippet_prints_the_refusal_the_commit_and_the_totals_and_its_asserts_hold` | run | A snippet attribute that is missing, renamed, or mistyped (`MEMORY_COMMITTED`, `details.source/.rule/.passed/.committed/.events_failed`, `HANDOFF_WRITTEN` last, `details.path`). | The snippet's loop prints nothing if no event matches. The test therefore pins the exact stdout (3 lines: the tool's `duplicate_task` refusal, `#1 committed by root/p/ver: …`, `1 1 0`) and re-checks each read attribute's type and the handoff file on disk. The snippet is pasted verbatim from §4 between markers. |
| AC-2 | ES::`test_a_one_pair_run_delivers_eleven_events_in_order_with_their_envelopes_summaries_and_details` (updated); `AC2_KINDS`; DN::`test_a_sink_changes_nothing_the_model_or_the_disk_sees[ac2]` | run | A missing, extra, or reordered kind; the verifier's events under the wrong agent; a summary not built from its template. | It compares by equality with the 11-kind list, not by subset, and pins the envelope tuple and summary of all 11 events. A `workspace_usage` or `agent_progress` firing under default caps would also break the equality. |
| AC-3 | DP::`test_an_entry_a_sibling_committed_first_is_dropped_by_rule_while_the_rest_commit` | run | A rule drop that is missing, attributed to the generator, carries the wrong note, or arrives after `subagent_finished`. | Without the race the drop never happens. `Signal`s force pair a to commit before b's verifier replies, and the card's `dropped` line (`s1 (…): This text is already recorded as #N…`) is read back as proof that the drop occurred. The note is compared with that card text, not a literal. |
| AC-4 | DP::`test_unchecked_entries_drop_under_the_last_agent_that_ran[no-verdict, blank-generator]` | run | Unchecked drops that are missing, from the wrong agent, or out of order; verifier events for a failed generator (D-20). | Both cases pin the whole kinds list (case b lists no verifier events) and check that the number of drops equals the card's `dropped` list. |
| AC-5 | DP::`test_each_committed_entry_is_announced_in_staged_order_after_it_is_on_disk` | run | A commit announced before its line is in `entries.jsonl`, out of staged order, with a wrong id, from a non-verifier, or missing `supersedes`. | The sink records at delivery time whether the id is already in `entries.jsonl`. Ids are compared with the file, and `verified_by` with the envelope. Three entries, one of which supersedes a seeded #7, exclude a trivial single-entry pass. |
| AC-6 | DF::`test_each_tool_refusal_names_its_rule_and_source_and_keeps_the_problem_the_model_read[32 cases]`; DF::`test_the_refusal_cases_cover_every_rule_a_tool_can_raise` | run | A wrong or missing `rule` or `source`; a `problem` other than the text the model read; a refusal from the wrong agent. | Each case first asserts that the model's tool result was an error. The expected problem is cut out of that result with the catalog's `memory_rejected_prompt`/`launch_rejected_prompt` template, so it comes from what the model saw rather than from the code under test. The coverage test fails when an `InfiniteRefusalRule` value has no case. |
| AC-7 | DF::`test_middleware_denials_name_their_limit_as_rule_and_the_reason_as_problem`; EP::`test_middleware_denials_deliver_one_batch_rejected_each_and_the_run_still_finishes` (updated); DN::`…sink_changes_nothing…[ac7]` | run | A denial that is not announced, announced twice, at the wrong point, under the wrong agent, or with a rule or problem other than the middleware's `limit`/`reason`. | `_denial` asserts that each result is a real middleware denial. The sink records the root's model-call count at delivery, which pins "after the first iteration". The journal has no `pair_started` for x, y, z, or b. |
| AC-8 | DF::`test_a_denial_in_the_turn_the_run_finishes_is_announced_once_before_run_finished` | run | The catch-up after the loop is missing, or reports the denial twice. | A precondition reads the denial from the root result's `tool_calls`. The finish and the denial are in one scripted turn (`tool_calls(...)`), so `_after_tool_iteration` really is skipped. |
| AC-9 | DP::`test_each_quota_carrying_event_equals_the_quota_line_the_model_read` | run | Quota fields that differ from the model's quota line, for example an off-by-one before or after the change. | The quota line is parsed from each tool result with the catalog's `quota_line` template. A precondition pins the parsed values (24/25/10/10, 24/25/10/10, 24/25/9/10), so a parse that fails or returns nothing cannot match the event. |
| AC-10 | DP::`test_a_batch_beside_a_replay_announces_its_offset_index_counters_and_verdict_totals` | run | Wrong `batch`, `batch_index`, `batch_size`, `attempt`, `agents_started`, `max_agents`, or `in_flight`; batch totals that miscount; a `batch_finished` for a batch made only of a replay (EC-5). | It pins every counter of three launches, `in_flight` on every finish, both batch totals and summaries, and the stream boundaries around each batch. |
| AC-11 | DP::`test_a_pair_launched_again_after_a_resume_counts_a_second_attempt_and_continues_the_offset` | run | `attempt` 1 after a resume; `batch` restarting at 0; whole-run totals that come from the session instead (EC-16). | The journal is written by hand with two starts and one finish, so the expected 2/2/6 come from the journal and not from the code. Session counts are compared with the result metadata. |
| AC-12 | DP::`test_a_cancelled_flat_generator_announces_its_abort_before_run_stopped`; EL::`test_a_cancelled_run_ends_with_run_stopped_and_its_resume_opens_with_run_resumed` (updated); its verifier-step sibling DP::`test_a_run_cancelled_while_the_verifier_waits_announces_its_abort_in_the_verifier_step` (S4, R-6) | run (async) | No abort; an abort after `run_stopped`; a wrong phase or `staged`; a swallowed `CancelledError`. The sibling catches an abort during verification reported as `generator` (mutation M1). | `pytest.raises(CancelledError)` wraps the awaited run, and `Signal`s cancel only after two entries are staged and the generator is waiting. The sibling cancels only once the verifier's model call is waiting, and pins `verifier_started` before the abort, so the pair has provably entered verification. |
| AC-13 | DP::`test_an_error_in_the_pairs_own_commit_step_is_announced_and_the_run_goes_on[first-commit-fails, second-commit-fails, first-commit-fails-from-a-key-error]`; DP::`test_an_aborted_pair_re_raises_the_very_error_it_announced` | run; component | A missing abort; a wrong phase or `staged` count; a `batch_finished` or `subagent_finished` for the aborted batch; the error swallowed or wrapped. The third item (S4, R-12) catches `error_type` naming the wrapper instead of its `__cause__` (D-22, mutation M11). All three items pin the template summary. | It asserts that the injected fault fired (`len(calls) == fail_on`) and that the root saw "Tool execution failed: …". The component test checks `raised.value is injected`. In the third item the error's type (`RuntimeError`) and its cause (`KeyError`) differ, so a rule that reads either one alone gives a different answer. |
| AC-14 | DP::`test_a_child_agents_error_becomes_the_card_and_names_its_original_class` | run | `error_type` naming `AgentExecutionError` (the wrapper), or a child error raised as `subagent_aborted`. | Two different original classes plus a clean sibling (`""`) exclude a constant answer. It also asserts that no `subagent_aborted` arrives. |
| AC-15 | DN::`test_run_finished_carries_this_sessions_loop_counts_and_the_whole_runs_card_totals` | run | Totals from the wrong source; `committed` counting root saves; `files` counting another run's notes (mutation M10, caught since the S4 strengthening, R-4); a wrong `deepest`. | A precondition reads the verdicts, entries, and notes from the cards and `files.jsonl`. The iteration and tool counts are compared with the result metadata and pinned (5, 4). Correction (review R-4): at S2 the workspace was fresh, so `files.jsonl` held only this run's records and the "another run's notes" catch could not happen. The test now seeds `notes/earlier.md` and its `files.jsonl` record under run `RUN_A` before the run. A second precondition checks that this record survived and names a third path, so all-runs counting would give 3 instead of 2. |
| AC-16 | DN::`test_the_terminal_event_counts_the_events_the_sink_failed_on[finished, stopped]` | run | `events_failed` missing or wrong on either terminal event; a sink failure that changes the result. | A precondition checks that each failing kind was offered exactly once. The stopped case pins `run_stopped` as the last event. |
| AC-17 | DN::`test_workspace_usage_arrives_exactly_when_the_level_crosses_up_or_down`; DN::`test_workspace_usage_arrives_when_the_map_is_cut_and_again_when_it_is_whole` | run | Usage on every iteration, never on the way down, at the wrong level, or with counts or an omitted count other than the disk's. | It pins exact (iteration, level) pairs (2,50 5,75 6,90 7,100 8,50 9,0). Expected counts are read from `workspace.usage()` and the map text at the root's next call, not from the event. The cut case asserts as a precondition that the map was cut. |
| AC-18 | DN::`test_agent_progress_arrives_every_tenth_root_iteration_with_the_roots_own_counts`; DN::`test_agent_progress_has_no_max_iterations_when_the_loop_sets_none` (EC-18) | run | Progress off its tenth iterations, from a child, or carrying the children's tokens. | The child spends 1,000 tokens per call and the root 10, so mixing them breaks the 100/200 pin. A precondition pins 26 root iterations. |
| AC-19 | DN::`test_handoff_written_is_the_last_event_and_names_the_saved_file_and_its_sections`; DN::`test_handoff_written_names_the_sections_cut_at_their_caps`; DN::`test_handoff_written_arrives_for_an_unfinished_run_with_no_terminal_event` (EC-14) | run | Announced before the write; an absolute path; wrong section lengths or order; wrong cut titles. | The sink checks that the file exists at delivery. The lengths come from the returned `InfiniteHandoff`, and a precondition checks that two sections really hit their caps. |
| AC-20 | DN::`test_without_a_sink_no_event_is_built_no_usage_is_scanned_and_nothing_is_logged`; ES::`test_without_a_sink_no_event_method_builds_an_event_or_logs` (updated to 22) | run; contract | A record built, a `usage()`/`descriptions()` call from `events.py`, a `map_omitted` call, or a log line without a sink. | A positive-control run with a sink must trip all three counters, so a broken counter cannot pass. Scans are attributed to their caller's file. |
| AC-21 | DN::`test_a_sink_changes_nothing_the_model_or_the_disk_sees[ac2, ac7, wide]` | run | A sink that changes tool results, cards, the map, prompts, the journal, `entries.jsonl`, `files.jsonl`, or the handoff. | Each sink run must also deliver its exact kinds (or `WIDE_KINDS`), so a run whose sink silently received nothing cannot pass. |
| AC-22 | DN::`test_a_sink_that_raises_on_every_kind_changes_nothing_and_logs_each_failure_once` | run | A raising sink that changes the run, skips later events, or logs twice or without the class. | The attempted kinds must equal a list sink's 19-kind stream, and the warnings are compared one for one. |
| AC-23 | DR::`test_every_public_events_method_takes_the_spec_parameters_by_position`; ES NFR-2 test (22 kinds) | contract | An extra or missing public method; a keyword-only or defaulted parameter; a wrong parameter order. | The parameter lists are written out from §8.5, not read from the module. |
| AC-24 | DR::`test_the_kinds_and_three_new_enums_hold_exactly_the_spec_values_in_order`; ER::`test_the_public_names_are_one_object_wherever_they_are_exported` (updated) | contract | Missing or reordered members (D-19); enums missing from `vidbyte.lib.enums.__all__` or leaking into `vidbyte.__all__`. | It compares ordered lists written from §8.5. |
| AC-25 | DR::`test_the_new_and_enriched_records_have_the_spec_fields_in_order_with_no_defaults`, `…small_valid_shapes…`, `…every_count_field_refuses…`, `…every_enum_field_refuses…`, `…section_9_1_rules_that_are_not_plain_counts`; ER worst-case and field tables (updated) | unit | A field that is missing, defaulted, or out of order; a rule that accepts a bad value; a worst case over 32,768 bytes. | Each refusal must name the qualified field, and each valid shape must be accepted, so a record that refuses everything fails too. `_FIGURES` pins exact byte totals. |
| AC-26 | DN::`test_two_runs_of_one_script_give_equal_streams_once_ids_stamps_and_durations_are_normalized` | run | A decision that reads a clock; unordered iteration; a leaked tmp path. | A precondition requires the 19-kind stream, so two empty streams cannot compare equal. Only `run_id`, the folder, and `duration_ms` are normalized. |

### Invariants

| Spec ID | Test | Level | Failure caught | How it could pass vacuously and why it does not |
|---|---|---|---|---|
| INV-1 | as AC-20 | run | A new path that builds or scans without a sink. | Positive control, as above. |
| INV-2 | as AC-22; DN::`…terminal_event_counts…` | run | An `Exception` from the sink that changes control flow. | It compares against a no-sink run. |
| INV-3 | DP::`test_an_aborted_pair_re_raises_the_very_error_it_announced`; DP::`test_an_interrupt_the_sink_raises_on_subagent_finished_gives_one_abort_in_the_commit_phase`; DP::`test_an_interrupt_the_sink_raises_on_an_error_cards_finish_still_aborts_in_the_commit_phase[generator-fails, verifier-fails]` (S4, R-5); DP::`test_a_sink_interrupt_while_an_abort_is_announced_propagates_in_place_of_the_error`; DP AC-12 and its verifier-step sibling (S4, R-6) | component; run | A swallowed or replaced exception; the one allowed replacement (a `BaseException` from the sink on `subagent_aborted`) not propagating. | Every check is an identity check (`is`) against an object the test created. |
| INV-4 | DP AC-5 (on-disk check at delivery); DP AC-3/AC-4 (drops before `subagent_finished`, matched to the card); DN AC-19 (file exists at delivery); existing ES `test_each_event_is_delivered_after_the_change_it_reports_is_on_disk` | run | An event before its change. | The sinks read the disk at delivery time. |
| INV-5 | DN AC-21 (`calls_view` over every model call, `run_view` over every file); DF AC-6 (problem equals the model's text) | run | A model-visible byte changed. | It compares against a no-sink run. |
| INV-6 | DN AC-26 | run | Non-determinism. | See AC-26. |
| INV-7 | DR AC-23; ES NFR-2 test | contract | Public helpers or properties. | See AC-23. |
| INV-8 | ER worst-case sizes (`_FIGURES`, 21 records); `assert_portable` on every collected stream (summary ≤ 280 and one line, key ≤ 512, leaf types, size); DP::`test_an_aborted_pair_with_a_long_key_carries_the_key_its_launch_carried` (EC-24) | unit; run | A record over 32,768 bytes; a summary that is too long or spans lines; an unshortened key. | `_worst` builds each record at every cap. Absolute paths are checked only by the existing envelope test. See OPEN ITEM 2 for the disk refusal. |
| INV-9 | DP AC-5 (`card["entries"]` equals the committed ids); DP AC-4 (drops equal the card's `dropped`) | run | A count mismatch. | It compares with the card on disk. |
| INV-10 | DP AC-13 (abort, no finish); DP EC-10 (finish then abort, on the normal and, since S4, the error-card branch); DP AC-14 (finish, no abort) | run | Zero or two endings for one launch. | Each test pins the pair's full subsequence. |
| INV-11 | DF AC-7, AC-8, EC-8, EC-19 | run | Missing or duplicate denials. | It pins exact lists. |
| INV-12 | DF AC-6 (32 cases); DF::`test_a_rule_comes_from_the_errors_details_then_its_type_then_the_denials_limit` (15 inputs); DF::`test_batch_rejected_takes_a_raised_error_or_a_denied_context` | run; unit | A wrong rule precedence (details, then type, then `limit`). | The rule is named in `details` even where the type would give another rule, so precedence is exercised. |
| INV-13 | DN AC-17 (two tests); DN::`test_a_seeded_workspace_over_half_full_is_announced_after_the_first_root_tool_iteration_only` (EC-12) | run | Repeats, missed downward moves, a wrong first state. | It pins exact (iteration, level) lists, including a no-iteration run with no usage event. |
| INV-14 | DN AC-18, EC-18 | run | Wrong iterations; a child heartbeat. | See AC-18. |
| INV-15 | Exact kinds lists in DP AC-3/AC-5/AC-13, DF AC-7/EC-8/EC-19, ES AC-2, DN AC-19 | run | Order violations. | It compares by equality. Sibling interleaving is never pinned, only each pair's own order and the batch boundaries. |
| INV-16 | DP::`test_in_flight_counts_each_pair_once_and_never_goes_below_zero` (strengthened in S4, R-3); DP AC-10 (`in_flight` on launches and finishes) | component; run | A double decrement on an abort after a finish; a negative value; no increment when the sink raises on a launch; no decrement when the sink raises on a finish, for example a decrement moved after delivery (D-9, R-17, mutation M7). | It uses a real journal with and without a finished record for the pair. The sink raises on b's launch and on a's finish, and d's launch must read 2, which is 3 if a's raised-on finish skipped its decrement. |
| INV-17 | Existing `test_infinite_memory_resume.py` (unchanged, green); DR::`test_the_journal_lists_every_pair_start_in_order_with_repeats` | run; unit | A journal format change. | The existing tests are unchanged. |
| INV-18 | Updated PR #1159 lists only insert new kinds; DR record-field test (enriched records keep PR #1159's fields first); EP AC-36 reversal | run; contract | A changed old field, value, or order. | Only insertions were made (see "Existing tests updated"). |
| INV-19 | DP AC-14 (child errors become cards); DP AC-13 (a pair-owned defect escapes, siblings and parent go on) | run | A child error aborting the pair. | See AC-14. |
| INV-20 | Not a test (see "Tests deliberately NOT written"). | | | |

### Edge cases

| Spec ID | Test | Level | Failure caught | How it could pass vacuously and why it does not |
|---|---|---|---|---|
| EC-1 | DF::`test_a_generator_that_fails_after_a_denied_launch_announces_no_denial` | run | A denial invented for a failed generator; `error_type` naming the wrapper. | A precondition checks that the generator's launch result was an error. |
| EC-2 | as AC-13 | run | | |
| EC-5 | DP AC-10 (third launch is a lone replay; stream ends `batch_finished, subagent_replayed, run_finished`) | run | A `batch_finished` for a batch of replays. | It pins the stream tail. |
| EC-6 | DF AC-8 | run | | |
| EC-8 | DF::`test_a_root_denial_beside_a_batch_in_one_iteration_follows_that_batch` | run | A middleware denial announced inline, or before the batch's events. | Three launches in one turn (`tool_calls`) pin the order. |
| EC-9 | DF::`test_only_launch_denials_that_name_a_limit_are_announced` | run; unit | A permission denial announced; `denials` keeping the wrong records. | A precondition checks that the permission denial carries no `limit`. The unit part checks `is` identity and order over 9 mixed records. |
| EC-10 | DP::`test_an_interrupt_the_sink_raises_on_subagent_finished_gives_one_abort_in_the_commit_phase`; DP::`test_an_interrupt_the_sink_raises_on_an_error_cards_finish_still_aborts_in_the_commit_phase[generator-fails, verifier-fails]` (S4, R-5); DP INV-16 test | run; component | No abort after a finish; a double decrement. The S4 test catches the error-card branch reporting the abort in phase `generator` or `verifier` instead of `commit` (review R-2). It is red at `2d8f8341` and green under the R-2 fix (FIX-RC1). | The journal must already hold `pair_finished`. In the S4 test, a precondition requires the finish to carry the child's `RuntimeError` with verdict `unchecked` (status `failed` for a failing generator, `done` for a failing verifier), so the interrupt really lands on an error card's finish. |
| EC-12 | DN seeded-workspace test | run | | Precondition: 6 files. |
| EC-13 | DN AC-17 level test (90 → 100 → 50 → 0 on deletions) | run | | |
| EC-14 | DN::`test_handoff_written_arrives_for_an_unfinished_run_with_no_terminal_event` (unfinished-run part) | run | No event for an unfinished run's handoff. | A precondition checks that the file was written. |
| EC-16 | DP AC-11 | run | | |
| EC-17 | Not separately tested (see below). | | | |
| EC-18 | DN::`test_agent_progress_has_no_max_iterations_when_the_loop_sets_none` | run | `max_iterations` reported as 0 or 500. | A precondition checks that the loop has no limit. |
| EC-19 | DF::`test_a_blank_generator_reply_still_announces_its_denied_launch_first` | run | | |
| EC-20 | DP AC-3 | run | | |
| EC-21 | DF AC-6 cases `remember-lone-surrogate` (text_encoding), `write-note-disk` (disk), `remember-bad-tag` / `launch-malformed-card` (invalid_arguments); DF `_rule` unit | run; unit | | |
| EC-22 | DF `_rule` unit (`limit="budget"`); DF::`test_batch_rejected_takes_a_raised_error_or_a_denied_context` | unit; component | | Covered at the component level, not with a scripted developer middleware. |
| EC-24 | DP::`test_an_aborted_pair_with_a_long_key_carries_the_key_its_launch_carried`; ER::`test_keys_over_508_characters_are_shortened_by_digest_and_stay_distinct` (updated call) | component | An unshortened or differently shortened key. | The shortened key is restated with `hashlib`. |
| EC-26 | DP AC-13 (no `batch_finished` for the raising pipeline) | run | | |
| EC-27 | DP AC-14 | run | | |

### Functional and non-functional requirements

| Spec ID | Test | Level | Failure caught | How it could pass vacuously and why it does not |
|---|---|---|---|---|
| FR-1 | DP AC-3, AC-4 | run | | |
| FR-2 | DP AC-5 | run | | |
| FR-3 | DF AC-6, `_rule`; HO malformed-entry pin (`details["rule"]`) | run; unit | | |
| FR-4 | DP AC-9 | run | | |
| FR-5 | DP AC-10, AC-11 | run | | |
| FR-6, FR-7 | DN AC-15, AC-16; DP AC-11 | run | | |
| FR-8 | DP AC-14 | run | | |
| FR-9, FR-10 | DP::`test_verifier_started_and_finished_carry_the_staged_count_the_notes_the_verdict_and_the_usage`; DP AC-4 (unchecked verdict) | run | Wrong staged count, wrong file list, missing `files_omitted`, wrong verdict or usage, wrong envelope. | 7 notes exceed the 5-item cap, so the cut is exercised. The verifier's usage (33) is different from the generator's. |
| FR-11 | DP AC-12, AC-13, EC-10; since S4: DP verifier-step cancellation (R-6, phase `verifier`), DP EC-10 error-card branch (R-5, phase `commit`), DP AC-13 cause item (R-12) | run | Since S4, all three D-10 phases are pinned at run level: `generator` (AC-12), `verifier` (R-6), and `commit` (AC-13, EC-10, R-5). | |
| FR-12 | DP AC-10 | run | | |
| FR-13 | DN AC-19 | run | | |
| FR-14 | DN AC-17 | run | | |
| FR-15 | DF AC-7, AC-8 | run | | |
| FR-16 | DN AC-18 | run | | |
| FR-17 | DR AC-23 (one method per kind); call sites are covered by the order tests | contract | | |
| NFR-1 | DN AC-26 | run | | |
| NFR-2 | DN AC-21, AC-22 | run | | |
| NFR-3 | ER `_FIGURES` (largest record `InfiniteSubagentFinishedDetails` 27,909 bytes); `assert_portable` | unit | | |
| NFR-4 | DN AC-20 | run | | |
| NFR-5 | DN AC-20 positive-control run: `usage()` from `events.py` at most once per root tool iteration (10), and `descriptions()` once (for `run_finished`) | run | An extra scan per iteration. | A bound with an equality on `descriptions`. |
| NFR-6 | CT::`test_new_modules_stay_inside_the_complexity_budget` (caps 660/470/870) | contract | A module over its cap. | Green now. It goes red only if the implementation overshoots. |
| NFR-7, NFR-8 | NFR-7 is the S3/S5 gate run. NFR-8 is covered by `assert_portable` and the AC-16/AC-22 log checks (class only, no message). | | | |

## Tests deliberately NOT written

| Spec ID | Why no test |
|---|---|
| EC-3 | A nested pair that announces after `run_stopped` is an accepted limitation (A-6). Its timing depends on when the inner batch ends during the loop's shutdown, and the spec gives no control to pin it. |
| EC-4 | A cancellation between task creation and the task's first step has no listener (NG-7). Forcing that window needs control over `asyncio` scheduling that the pack does not take. |
| EC-7 | Denials lost when the run raises before the catch-up are an accepted limitation. A test would pin a missing event as wanted behaviour. |
| EC-11 | `bash` changing files between the map render and `usage()` inside one hook needs a second writer inside the hook. There is no seam for that, and the spec accepts the drift (D-12). |
| EC-14 (other process) | A run still going in another process needs a second process. The unfinished-run half is tested. |
| EC-15 | An uncut section exactly at its cap that ends with the marker is an accepted false positive. A test would pin the defect. |
| EC-17 | Pair events after `run_finished` (PR #1159 EC-12) appear only when a sibling outlives an aborted batch. `events_failed` covering "this session up to that event" is pinned by AC-16. A late failure would need sibling timing the spec leaves open (EC-26). |
| EC-23 | Two threads on one agent (A-3) interleave nondeterministically. Separate `InfiniteEvents` per run follow from construction in `arun`, which AC-11 and EC-16 already exercise. |
| EC-25 | A journal write that fails twice in the error branch needs fault injection inside `InfiniteRunJournal`, which the spec does not name as a seam. Its `in_flight` rule (decrement when the journal has no finished record) is pinned by the INV-16 component test. |
| EC-28 | A note name that forges the map's closing line is an accepted, event-only limitation (T-2). `map_omitted`'s parser and its near-misses are pinned by DR::`test_map_omitted_reads_a_cut_maps_closing_line_and_never_raises`. |
| INV-20 | "No code in `vidbyte.agents.runtime`, `.base`, `vidbyte.middleware`, or `vidbyte.pipelines` changes" is a property of the diff, not of behaviour. S4 checks it with `git diff 181f1992 -- vidbyte/agents/runtime.py vidbyte/agents/base.py vidbyte/middleware vidbyte/pipelines`. |
| NFR-7 | The CI gate (`scripts/run_ci.py`, agent lint) is run by S3 and S5, not encoded as a test. |
| Out of scope | C1, C2, E2, and generator or verifier progress are out of scope (§3, pipeline decisions), so no test asserts their absence or presence. |
| Permission denials beyond EC-9 | Q-3 says these are not announced. EC-9 pins the silence for the one realistic case. |

## Red run

**Bootstrap:** none. The worktree already imports `vidbyte` from source with `PYTHONPATH=$(pwd)`. `pip install -e` is not used.

**Commands** (repository root, Git Bash):

```
PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider --tb=line
PYTHONPATH=$(pwd) python -m pytest --collect-only -q -p no:cacheprovider
PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider --tb=no -rf
python lint/run.py
```

**Result at `33cfda07` plus these tests:**
- **Pack:** `120 failed, 294 passed`. The output is identical over three runs once addresses and run ids are masked.
- **Red in the new files:** 87 items.
  - DP: 17
  - DF: 41
  - DN: 18
  - DR: 11
- **Red in spec-mandated updated tests:** 33 items.
  - ER: 22
  - EP: 5
  - ES: 4
  - EL: 1
  - HO: 1
- **Green:** the contract budget test (it only raises caps).
- **Full suite:** collects 7,051 tests and ends `121 failed, 6913 passed, 17 skipped`: the 120 pack items above plus one other. The only failure outside the pack is `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`. That test compares `FailureCode` at `git merge-base HEAD main`, and this checkout's `main` has moved (171 members against 120). It is unrelated to this change: no file it reads was touched.
- **`python lint/run.py`:** `SDK-LINT: PASS` once the new files are tracked. Before staging, S020 (README File Index parity) counts untracked files as stale.

Every red item fails for a missing spec name or behaviour:
- `ImportError`/`AttributeError` on `InfiniteRefusalRule`, `InfinitePairPhase`, the new records, `map_omitted`, `InfiniteRunJournal.started`, or `InfiniteLaunchTool.denials`;
- `TypeError` on the 5-argument `subagent_launched` or on new record fields;
- `ValueError` on a new kind value;
- `AssertionError` on a kinds list, which lacks the new kinds;
- a missing constant (`INFINITE_EVENT_PROGRESS_ITERATIONS = '<missing>'`).

None fails on a fixture error, a timeout, or an import of the test module itself.

## Notes for the implementer

1. **Seams the tests patch at call time.** Look each one up through the class or instance at call time; never capture it at import:
   - `InfiniteWorkspace.commit_entry` (AC-13, INV-3) is replaced on the class, so `_commit` must call `workspace.commit_entry(...)`.
   - `InfiniteWorkspace.map_omitted`, `usage`, and `descriptions` (AC-20) are replaced on the class too.
   - AC-20 attributes `usage()` and `descriptions()` to the file of their *direct* caller. Call them from `vidbyte/agents/infinite/events.py`, as §8.5's signatures imply. A scan made in `runtime.py` and passed in would not be attributed to the events module and breaks the positive control.
2. **AC-20 counts constructions** with `__post_init__` wrappers on every `Infinite*Details` record and `InfiniteEvent`. With `on_event=None`, no record may be built anywhere, including in `runtime.py`. With a sink, the wide run must build an `InfiniteWorkspaceUsageDetails`. With `max_files` 7, the run crosses 50 %.
3. **NFR-5 is bounded in that same test:** `usage()` from `events.py` at most once per root tool iteration (10 in the wide script), and `descriptions()` exactly once.
4. **Pinned byte figures.** Row 3 of §12.3 asks the constants comment to state the measured worst case. Use the figures `_FIGURES` pins: largest record `InfiniteSubagentFinishedDetails` 27,909 bytes, and a whole event at most 31,987 bytes (280-character summary, 512-character key). The other new records are listed in `_FIGURES` in ER.
5. **Default caps give no new run-level events.** Under default caps the AC-2, quiet-tools, AC-3 (stream :250), and refusal scripts expect no `workspace_usage` and no `agent_progress`. The baseline workspace already holds 3 files (`entries.jsonl`, `superseded.jsonl`, `files.jsonl`), and the level starts at `(0, False)`.
6. **Refusal problems are the text the model read.** For memory tools that is `str(error)`, and for the launch tool `exc.message`. The disk case's problem therefore names an absolute path the OS put in the `OSError` message (OPEN ITEM 2). The surrogate case reaches the workspace as `UnicodeEncodeError`, so its rule comes from the type. A malformed task card fails in `ToolArguments.records` as a `ConfigurationError` with no rule, so it is `invalid_arguments`. On Windows, `notes/a:b.md` is refused as "outside the workspace", which is still `note_path`.
7. **Envelopes and fallbacks.**
   - `subagent_aborted`'s envelope is the launcher (`root`, depth 0, for a root-level pair), like `subagent_launched` and `subagent_finished`. Its summary is `"<name> aborted (<reason>) in its <phase> step: <error_type>"`.
   - `batch_rejected` for a denied context uses the result's `reason`. When the metadata has no `reason`, it uses the result's `output`.
8. **`verifier_started`'s summary.** The test accepts either count of notes (written 7 or shown 5) for `{files}` (OPEN ITEM 1). `details.files` must be the first 5 notes in write order, with `files_omitted` 2.
9. **EC-10.** A `KeyboardInterrupt` raised in a pair task makes `asyncio` cancel the root task. Its `run_stopped` names `CancelledError`, and the test does not pin that event's details.
10. **Scripted usage** carries `total_tokens` wherever a token count is asserted. The default fixture usage has none and counts 0, so `agent_progress.tokens` is `state.tokens_used or 0`.
11. **The P2 checkpoint is atomic.** Records, events, launch, memory, and runtime must land together before the pack is run (pipeline note). Most red tests turn green only when all of them exist.

## Existing tests updated (spec-mandated)

Line numbers are at `33cfda07`, the S2 start. Each change makes an existing pin follow a behaviour this spec changes. No test was skipped, marked xfail, deleted, or loosened. Every list keeps the old kinds in their old order and only inserts the new ones.

| File:line | Old → new | Spec ID |
|---|---|---|
| `infinite_events_fixtures.py:75` | `AC2_KINDS` 7 kinds → 11 (`+verifier_started, verifier_finished, memory_committed, batch_finished`). New helpers `AC7_LIMITS` and `ac7_tree()` added after it (no assertion). Header ROLE line names the new modules. | AC-2, §13 stream |
| `infinite_memory_fixtures.py:132, :345` | Added `ToolsStep` and `tool_calls(...)`: one model turn asking for several tool calls. A new step type only; existing steps are unchanged. | AC-8, EC-8 (needs a finish and a denial, or three launches, in one turn) |
| `test_infinite_memory_contract.py:475, :481` | Caps `{launch.py: 410, lib dataclasses: 620}` → `{launch.py: 470, lib dataclasses: 870, events.py: 660}`. Docstring cites D-15. | D-15, §8.4, §12.3 row 13, NFR-6 |
| `test_infinite_memory_events_lifecycle.py:88` | `[run_started, subagent_launched, run_stopped]` → `[run_started, subagent_launched, subagent_aborted, run_stopped]`. Docstring :81 names AC-12. | AC-12, INV-15, §13 lifecycle :88 |
| `test_infinite_memory_events_lifecycle.py:102` | Resumed list → `+verifier_started, verifier_finished` before `subagent_finished`, and `+batch_finished` after it. | FR-9, FR-10, FR-12, §13 :102 |
| `test_infinite_memory_events_pairs.py:128-137` | Replay test list: each pair gains `verifier_started, verifier_finished` and its batch gains `batch_finished`. | FR-9, FR-10, FR-12. Spec gap: §13 cites :106, whose list does not change. |
| `test_infinite_memory_events_pairs.py:178` | Drop list → `[…, generator_finished, verifier_started, memory_dropped, verifier_finished, memory_committed, subagent_finished, batch_finished, run_finished]` | FR-2, FR-9, FR-10, FR-12, §13 :178 |
| `test_infinite_memory_events_pairs.py:328` | Refusal list → `+verifier_started` before and `+verifier_finished` after the verifier's `tool_refused`, and `+batch_finished` | FR-9, FR-10, FR-12, §13 :328 |
| `test_infinite_memory_events_pairs.py:479` | `[run_started, subagent_launched, memory_staged, subagent_finished, run_finished]` → `[…, memory_staged, memory_dropped, subagent_finished, batch_finished, run_finished]` | FR-1, FR-12, §13 :479 |
| `test_infinite_memory_events_pairs.py:542-543` | `test_middleware_denials_deliver_no_event_and_the_run_still_finishes` → `test_middleware_denials_deliver_one_batch_rejected_each_and_the_run_still_finishes`. The docstring now states the reversal. | AC-7, FR-15, §13 AC-36 |
| `test_infinite_memory_events_pairs.py:560` | `[run_started, subagent_launched, generator_finished, subagent_finished, run_finished]` → the AC-7 list `[run_started, batch_rejected, subagent_launched, batch_rejected, generator_finished, verifier_started, verifier_finished, subagent_finished, batch_finished, run_finished]` | AC-7, §13 :560 |
| `test_infinite_memory_events_pairs.py:3, :6` | Header PURPOSE and FUNCTION INVENTORY name the renamed test and the denial events. | (docs) |
| `test_infinite_memory_events_records.py:53-67` | `_FIGURES`: 8 enriched records re-measured (RunFinished 6,930 → 7,296; RunStopped 6,824 → 6,862; Refusal 6,795 → 6,852; SubagentLaunched 25,201 → 25,442; SubagentFinished 27,015 → 27,909; MemorySaved 18,023 → 18,165; MemoryStaged 6,147 → 6,289; FileWritten 13,544 → 13,686). 8 new figures added (MemoryCommitted 6,174; VerifierStarted 7,300; VerifierFinished 950; SubagentAborted 1,461; BatchFinished 225; HandoffWritten 10,120; WorkspaceUsage 180; AgentProgress 175). | AC-25, NFR-3, §12.3 row 3, §13 records |
| `test_infinite_memory_events_records.py:69-84, :87-128, :132` | `_RECORD_OF_KIND` + 8 kinds; `_FIELDS` + the new and appended field rules; `_COST_RECORDS` + `InfiniteVerifierFinishedDetails` | AC-24, AC-25, §13 records |
| `test_infinite_memory_events_records.py:144-228` (`_worst`) | Shapes gain the new required fields and the 8 new records. Shapes are built lazily per record, so an unchanged record never needs a new enum. | AC-25, §13 `_worst` |
| `test_infinite_memory_events_records.py:275` | Docstring "exactly the 14 values" → "the 22 values of §8.5". The assertion is the existing `set(_RECORD_OF_KIND)` comparison. | AC-24, §13 records :274-300 |
| `test_infinite_memory_events_records.py:488` | `events.subagent_launched(launch, card)` → `events.subagent_launched(launch, card, 0, 0, 1)` | §8.5 signature, §13 records :488 |
| `test_infinite_memory_events_records.py:5` | ARCHITECTURE NOTE says where the new figures come from. | (docs) |
| `test_infinite_memory_events_stream.py:165-166, :188, :194-195` | Rename `…delivers_seven_events…` → `…delivers_eleven_events…`. Envelope list + 3 verifier envelopes. Summaries + `verifier_started`, `verifier_finished`, `memory_committed`, `batch_finished` (from §9.2). | AC-2, §9.2. Spec gap: §13 cites only :183 (`AC2_KINDS`). |
| `test_infinite_memory_events_stream.py:388` | No text change. `len(tasks) == len(AC2_KINDS)` now expects 11. | §13 :388 |
| `test_infinite_memory_events_stream.py:419, :436` | Docstring 14 → 22. Added `assert public == sorted(DERIVED_KINDS)` (22 values, `DERIVED_KINDS` at :84). The existing equality with the enum stays. | NFR-2 (PR #1159), AC-23, INV-7, §13 :435-436 |
| `test_infinite_memory_events_stream.py:493` | Quiet-tools list → `+verifier_started, verifier_finished` and `+batch_finished` | FR-9, FR-10, FR-12. Spec gap: §13 cites :493 only for "no heartbeat". |
| `test_infinite_memory_events_stream.py:6` | FUNCTION INVENTORY names the renamed test. | (docs) |
| `test_infinite_memory_handoff.py:248` | `{"file": "entries.jsonl", "line": 2}` → `{"file": "entries.jsonl", "line": 2, "rule": InfiniteRefusalRule.MALFORMED_MEMORY}`. Docstring :239 cites R-14. | §9.1, R-14, §13 handoff :248 |
| `FEATURE.md:20, :102, :107` + new "Derived events" block + 4 Test Suite Map entries + Omitted bullet | 14 → 22 kinds; "seven" → "eleven"; the AC-36 line now names the renamed test and its `batch_rejected`. | §13 FEATURE.md :107 |
| `README.md` (pack) | Intro paragraph, 4 File Index entries (S020), Logs line. | §13 README |

**Cited by §13 but no change needed (green at S2; each script was read to confirm that no new kind can fire in it):**
- lifecycle :155, :182, :193, :209. These runs end before any new event can fire.
- pairs :106 (refused batch), :291 (root notes only), :458 (the deep generator's own events). New events go to other agents or never fire.
- handoff :339-372 calls `file_written` through a real `InfiniteAgentMemory`, so the new quota fields are computed.

## Open items

1. **`verifier_started` summary `{files}`.** §9.2 does not say whether it counts the notes written (7) or the notes shown (5). The test accepts both. The spec owner should settle this.
2. **INV-8 against AC-6 for the disk refusal.**
   - AC-6 says `problem` equals the text at `181f1992`. For `write-note-disk`, that text is the `OSError` message, which names an absolute path the OS built from the SDK's workspace path, for example `[WinError 183] … 'C:\…\notes\a.md'`.
   - INV-8 forbids "an absolute path the SDK built" on events.
   - The test follows AC-6, which is the model-visible text. If S3 strips the path, this case goes red, and the spec owner decides which rule wins.
3. **AC-13 seam.** The only way to make pair-owned code raise is to wrap `InfiniteWorkspace.commit_entry` on the class (§13). The implementation must keep calling it through the instance.
4. **Spec §13 gaps (pins this spec changes that §13 does not cite).** All are listed above:
   - pairs :128-137 (replay list);
   - stream :188/:194 (AC-2 envelopes and summaries);
   - stream :493 (quiet-tools list);
   - stream :388 (follows `AC2_KINDS`);
   - the two test renames;
   - the new `ToolsStep` fixture.
5. **Wide script coverage.** It reaches 19 of 22 kinds. `run_resumed`, `run_stopped`, and `subagent_aborted` cannot occur in a finished run, so AC-20 to AC-22 and AC-26 do not cover the abort and resume paths. AC-21 asks only for the AC-2 and AC-7 scripts.
6. **EC-22 is covered at the component level only.** No scripted developer middleware denies with an unknown `limit`.
7. **A pre-existing, unrelated failure** remains in the full suite: `harness_threads` `FailureCode` count against local `main`.
8. **The R-5 pin is red until the R-2 fix lands** (see the next section). Its two items fail at `test_infinite_memory_derived_pairs.py:736` until the inner `except` branch of `InfinitePair.run` sets `phase = InfinitePairPhase.COMMIT`. This is the code fix for review R-2.

## S4 strengthening (review R-3..R-6, R-12)

**Why this section exists.** S4's adversarial review of `c1c3ecc0` (PR #1191), in `review.md` and `reports/S4-findings-verifier.md`, found two kinds of gap in this pack:
- **Surviving mutations.** M1, M7, M10, and M11 each left the pack at `414 passed`.
- **An unpinned phase.** No test pinned the phase that review R-2 reports wrong.

This pass only adds tests or tightens them, on base `2d8f8341`:
- No assertion was loosened, and no test was skipped, marked xfail, or deleted.
- No code under `vidbyte/` changed.
- No file was added, so the pack README File Index is unchanged.
- The FEATURE.md failure bullets and its Test Suite Map entry for `derived_pairs.py` name the new cases.

**Changes** (exact test names; DP and DN as in the files table):

| Review row | Test | Change | Gap it closes |
|---|---|---|---|
| R-3 (Major) | DP::`test_in_flight_counts_each_pair_once_and_never_goes_below_zero` (changed) | The recording sink now also raises `ValueError` on a's `subagent_finished`, beside the raise on b's `subagent_launched`. No assertion changed, and the docstring states the new case. | D-9 and R-17 say the decrement must survive a raising sink. With the decrement moved after delivery (M7), a's finish is never subtracted, so d's launch reads 3 instead of the pinned 2. |
| R-4 (Major) | DN::`test_run_finished_carries_this_sessions_loop_counts_and_the_whole_runs_card_totals` (changed) | Before the run, the test writes `notes/earlier.md` and its `files.jsonl` record under run `RUN_A`. A new precondition checks three things: `run_id != RUN_A`, the earlier record survived as line 1, and the file names 3 distinct paths. The AC-15 row above is corrected. | `files` must count only this run's notes (AC-15, D-16). Counting every run's records (M10) gives 3 instead of 2. Before this change the workspace was fresh, so the plan's claim to catch this was false. |
| R-5 (Major) | DP::`test_an_interrupt_the_sink_raises_on_an_error_cards_finish_still_aborts_in_the_commit_phase[generator-fails, verifier-fails]` (new) | alpha's generator (or its verifier) fails with `RuntimeError`, so that error becomes the pair's card. The sink then raises `KeyboardInterrupt` on the first `subagent_finished`. The test pins:<ul><li>the kinds list, ending `subagent_finished, subagent_aborted, run_stopped`;</li><li>one key for the finish and the abort;</li><li>a precondition: the finish names `RuntimeError` with verdict `unchecked`;</li><li>the journal `[run_started, pair_started, pair_finished]`;</li><li>`raised.value is` the sink's interrupt;</li><li>the abort `(cancelled, KeyboardInterrupt, commit, 0)` and its summary.</li></ul> | EC-10, D-10, and §12.3 row 6 say the abort is in phase `commit`. At `2d8f8341` it names `generator` or `verifier` (review R-2). The test is red until the R-2 fix lands. |
| R-6 (Major) | DP::`test_a_run_cancelled_while_the_verifier_waits_announces_its_abort_in_the_verifier_step` (new) | `_cancel_while_alpha_waits` takes `step` (default `"generator"`, so the AC-12 test is unchanged). With `"verifier"`, the generator stages one entry and replies, and the run is cancelled while the verifier's model call waits. The test pins:<ul><li>the kinds through `verifier_started, subagent_aborted, run_stopped`;</li><li>the root envelope;</li><li>`(alpha, root/alpha, cancelled, CancelledError, verifier, 1)` and the summary;</li><li>no `pair_finished`.</li></ul> | D-10 and FR-11 require the `verifier` phase during verification. Without the VERIFIER assignment (M1), the abort names `generator`. |
| R-12 (Minor) | DP::`test_an_error_in_the_pairs_own_commit_step_is_announced_and_the_run_goes_on[first-commit-fails-from-a-key-error]` (new item of a changed test) | The parametrization gains `(1, "KeyError")`: the injected `RuntimeError` carries `__cause__ = KeyError("s1")`, the object `raise … from KeyError(…)` builds, and `error_type` must be `KeyError`. All three items now also pin the summary `"p aborted (failed) in its commit step: <error_type>"`. | D-22's cause rule on `subagent_aborted`. Naming the wrapper's own class (M11) gives `RuntimeError`. |

**Pack at HEAD** (`2d8f8341` plus these tests, worktree):

```
FAILED tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py::test_an_interrupt_the_sink_raises_on_an_error_cards_finish_still_aborts_in_the_commit_phase[generator-fails]
FAILED tests/features/infinite_memory_agent/test_infinite_memory_derived_pairs.py::test_an_interrupt_the_sink_raises_on_an_error_cards_finish_still_aborts_in_the_commit_phase[verifier-fails]
2 failed, 416 passed in 9.29s
```

- **Both failures are the R-5 pin, for the R-2 reason.** They are its two parametrized items, and both fail at `:736`:
  - `assert (<InfiniteSto...enerator'>, 0) == (<InfiniteSto... 'commit'>, 0)`
  - `assert (<InfiniteSto...verifier'>, 0) == (<InfiniteSto... 'commit'>, 0)`
- **Why the pin has two items.** It is one test function, parametrized `[generator, verifier]` as review R-5's sandbox test was. The two branches reach the inner `except` in different phases. A fix that set `commit` on only one branch would therefore leave the other item red.
- **The pack.** It now has 418 items, up from 414: 1 for R-6, 1 for R-12, and 2 for R-5.
- **Determinism.** The 8 new or changed items, run 3 times, gave `2 failed, 6 passed` each time.
- **Full suite and lint.** `--collect-only` gives `7055 tests collected`, and `python lint/run.py` gives `SDK-LINT: PASS`.

**Mutation proof.** Each edit comes from `EDITS` in the S4 verifier's `vmutate.py` and is applied to a private sandbox copy of this worktree (`vidbyte/`, `contracts/`, `pyproject.toml`, `tests/`). The pack is run, and the edited file is restored byte for byte and compared. After the runs, the sandbox's `vidbyte/` was identical to the worktree's.

The edits:
- **M1** (`launch.py`): `phase, last = InfinitePairPhase.VERIFIER, checker` → `last = checker`.
- **M7** (`events.py`): the `in_flight` decrement on `subagent_finished` moves after `_deliver`, inside the shield, and the record shows `max(in_flight - 1, 0)`.
- **M10** (`events.py`): `len(workspace.descriptions(journal.run_id))` → `len(workspace.descriptions())`.
- **M11** (`events.py`): `type(error.__cause__ or error).__name__` → `type(error).__name__`.
- **FIX-RC1** (`launch.py`): `phase = InfinitePairPhase.COMMIT` inserted before `self.error = exc` in the inner `except` branch. This is the R-2 fix as the review describes it.

| Variant | Pack line | Failed items (failure line) |
|---|---|---|
| BASE | `2 failed, 416 passed in 8.74s` | R-5 `[generator-fails]` and `[verifier-fails]` (`:736`, as above) |
| FIX-RC1 | `418 passed in 10.15s` | none: the R-5 pin goes green under the fix |
| FIX-RC1+M1 | `1 failed, 417 passed in 10.18s` | R-6 test (`:460`, `assert ('alpha', 'ro...enerator'>, 1) == ('alpha', 'ro...verifier'>, 1)`) |
| FIX-RC1+M7 | `1 failed, 417 passed in 8.83s` | R-3 test (`:664`, `assert [('a', 1), ('... 3), ('e', 1)] == [('a', 1), ('... 2), ('e', 1)]`) |
| FIX-RC1+M10 | `1 failed, 417 passed in 8.92s` | R-4 test (`test_infinite_memory_derived_run.py:307`, `assert (3, 3, 2, 0) == (3, 2, 2, 0)`) |
| FIX-RC1+M11 | `1 failed, 417 passed in 8.33s` | R-12 item `[first-commit-fails-from-a-key-error]` (`:493`, the details tuple) |
| M1 | `3 failed, 415 passed in 8.28s` | R-6 test, plus the two R-5 items |
| M7 | `3 failed, 415 passed in 9.60s` | R-3 test, plus the two R-5 items |
| M10 | `3 failed, 415 passed in 9.72s` | R-4 test, plus the two R-5 items |
| M11 | `3 failed, 415 passed in 9.95s` | R-12 item, plus the two R-5 items |

**The control.** The same sandbox was rerun with the two files as they were at `2d8f8341`, then restored. Under M1, M7, M10, and M11 the pack gave `414 passed in 8.35s`, `414 passed in 8.65s`, `414 passed in 8.69s`, and `414 passed in 8.94s`. Each mutation survived before this pass and is caught by exactly one new or changed test after it.

**Commands** (repository root, Git Bash; the sandbox runner is a private scratch script):

```
PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider --tb=line -rf
PYTHONPATH=$(pwd) python -m pytest --collect-only -q -p no:cacheprovider
python lint/run.py
python srun.py BASE FIX-RC1 FIX-RC1+M1 FIX-RC1+M7 FIX-RC1+M10 FIX-RC1+M11 M1 M7 M10 M11   # in the sandbox
```
