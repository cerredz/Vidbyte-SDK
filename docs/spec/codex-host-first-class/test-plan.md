# Test plan: CodexHost first-class features (slice 2 of 2)

- **Stage:** S2 test author, pipeline `codex-host-first-class`, from `spec.md` r3 (approved). Round 2 follows r4 (`d0529d15`), which answered the eight spec defects and ambiguities below.
- **Branch:** `feat/codex-host-first-class`, written on top of `5c16c588` (slice base `a7730107`).
- **Date:** 2026-10-17.
- **Pack:** `tests/features/codex_host/`. Its `FEATURE.md` has the failure inventory these tests were chosen from, and its `README.md` has the boundary.

In the tables below, a test is written `<file>::<Class>::<test>`, or `<file>::<test>` where the class adds nothing. `<file>` is the module name without its `test_codex_host_` prefix, so `side_chat` means `tests/features/codex_host/test_codex_host_side_chat.py`. Spec section 6.2's Proof column carries the same tests as full node ids.

**Levels**

| Level | What runs | Where it runs |
|---|---|---|
| **R** (record) | lib records, enums, constants and docstrings, with no host and no SDK | CI and locally |
| **S** (structure) | a fresh interpreter's import probe, `ast` scans of the source, line counts and frozen-file digests | CI and locally, except one class that needs the SDK |
| **T** (tool) | `CodexHostTools` over `StubCodexHost` | CI and locally |
| **H** (host) | a real `CodexHost` over the in-memory app-server at the §13 seam (`connection.CodexClient`, plus `shutil.which` and `sys.platform`); the SDK's reader thread, router, retries and `CodexErrorMapper` run for real | locally, with the `codex` extra (openai-codex 0.163.0) |
| **C** (contract) | the installed openai-codex surface the new code reaches | locally, with the extra |
| **G** (git) | the canonical `GitWorktrees` helper and `create_codex_worktree` against the real `git` on temporary repositories, with `Path.home` patched and the user's git config shut out | the helper class everywhere git is installed; the host class with the extra |

## Coverage map

### Acceptance criteria

| Spec ID | Test | Level | Failure caught |
|---|---|---|---|
| AC-1 | `first_class_snippet::CodexFirstClassSnippetTests::test_the_section_4_snippet_prints_the_streamed_plan_then_both_statuses_then_the_server_names` | H | The §4 snippet does not run as written: a missing name, a stream that misses the plan deltas, or statuses or server names out of order. The snippet is copied verbatim into `main()`, and the plan turn ends only after a stdout recorder has seen the whole plan, so the stream is certainly open when the deltas arrive. |
| AC-2 | `settings_modes::CodexThreadSettingsUpdateHostTests::test_an_update_sends_one_settings_call_holding_only_the_fields_that_were_set`; `settings_modes::CodexThreadSettingsUpdateHostTests::test_each_other_setting_reaches_its_own_wire_key_and_nothing_else_is_sent` | H | An update sends an unset field, drops one, or sends two calls, or a cleared tier does not reach the wire as JSON null. The whole params dict is compared. |
| AC-3 | `settings_modes::CodexThreadSettingsUpdateHostTests::test_a_not_loaded_thread_with_an_active_goal_is_refused_before_any_resume` | H | A not-loaded thread whose goal is active is resumed, so the goal runs as untracked paid turns. The requests must be exactly `thread/read` then `thread/goal/get`. |
| AC-4 | `feature_records::CodexThreadSettingsUpdateTests::test_an_update_that_sets_nothing_is_refused_naming_settings`; `feature_records::CodexThreadSettingsUpdateTests::test_a_tier_set_together_with_a_clear_is_refused`; `feature_records::CodexThreadSettingsUpdateTests::test_writable_roots_must_be_absolute_and_need_a_workspace_write_sandbox` | R | An empty or contradictory update is built and sent instead of refused. Each row checks `details["field"]`. |
| AC-5 | `settings_modes::CodexCollaborationModeTurnHostTests::test_a_plan_mode_spawn_sends_the_model_codex_resolved_and_is_priced_as_it`; `settings_modes::CodexCollaborationModeTurnHostTests::test_the_mode_settings_take_the_first_model_set_and_any_named_effort` | H | The SDK's model dump drops `collaborationMode`, the mode carries the wrong model, or the turn is priced as the spawn model. The `turn/start` params and the priced cost are compared exactly. |
| AC-6 | `feature_records::CodexSpawnRequestModeTests::test_a_mode_whose_model_or_effort_differs_from_the_turns_is_refused_when_built`; `feature_records::CodexCollaborationModeRecordTests::test_a_conflicting_model_is_refused_naming_the_owner_and_an_equal_or_empty_one_is_not`; `feature_records::CodexCollaborationModeRecordTests::test_a_conflicting_effort_is_refused_and_a_providers_default_never_conflicts`; `feature_records::CodexCollaborationModeRecordTests::test_a_mode_kind_of_none_is_refused_with_the_kind_message` | R | A conflicting model or effort, or a `NONE` kind, is built. Equal values and the provider default are rows that must build, so a rule that refuses everything fails too. |
| AC-7 | `settings_modes::CodexModeRefusalHostTests::test_every_call_that_cannot_send_a_mode_refuses_it_before_any_request`; `feature_records::CodexSpawnRequestModeTests::test_a_goal_request_refuses_a_collaboration_mode_naming_the_field` | H, R | A mode reaches a fork, review, goal, plan or resume call that cannot send it. Every row needs zero requests. |
| AC-8 | `feature_contract::CodexFeatureExperimentalGateTests::test_without_the_experimental_api_the_eleven_functions_and_any_mode_are_refused_with_no_request`; `feature_contract::CodexFeatureExperimentalGateTests::test_without_the_experimental_api_the_stable_functions_still_talk_to_codex` | H | The gate is skipped, fires after a request, or also blocks the stable functions. Each of the 11 functions and the 4 mode rows is refused locally, naming `experimental_api`. |
| AC-9 | `settings_modes::CodexCollaborationModeListHostTests::test_the_presets_come_back_in_codex_order_with_nulls_read_as_blank` | H | Presets are reordered, or Codex's null model or effort is not read as blank. Both presets are compared field by field. |
| AC-10 | `settings_modes::CodexPlanRunHostTests::test_a_plan_run_lists_the_presets_then_spawns_one_plan_turn_whose_plan_is_the_answer`; `settings_modes::CodexFinalAnswerPlanFallbackTests::test_the_last_plan_answers_only_when_no_agent_message_does` | H, R | The plan run skips the preset list, spawns without the mode, or its answer is not the plan item. The fallback is pinned both ways: a plan answers only when no agent message exists. |
| AC-11 | `settings_modes::CodexPlanRunHostTests::test_a_preset_list_without_a_plan_mode_spawns_nothing` | H | A preset list without a plan mode still starts a thread. `thread/start` must never be sent. |
| AC-12 | `stream_wait::CodexTurnStreamHostTests::test_a_streamed_turn_yields_each_event_in_order_then_one_ended` | H | Events arrive out of order, are lost or renumbered, or ENDED's snapshot differs from `wait_codex_turn`'s. Nine kinds and sequences 1 to 9 are compared. |
| AC-13 | `stream_wait::CodexTurnStreamHostTests::test_raw_reasoning_text_never_reaches_a_stream_or_a_log` | H | Raw reasoning text reaches an event or a log. A canary is searched in every event's repr and every log record. |
| AC-14 | `stream_wait::CodexTurnStreamHostTests::test_a_stalled_subscriber_gets_one_gap_then_the_kept_window_and_never_delays_the_turn` | H | A stalled subscriber delays the turn, or the GAP count is wrong. The limit is patched to 3, and the arithmetic is in the test's comment. |
| AC-15 | `stream_wait::CodexTurnStreamHostTests::test_an_ended_turn_streams_only_ended_and_an_unknown_handle_is_refused_at_the_call` | H | An ended turn streams more than ENDED, or an unknown handle is refused only when iterated. |
| AC-16 | `stream_wait::CodexTurnsWaitHostTests::test_a_first_completed_wait_returns_every_snapshot_in_order_and_touches_no_turn` | H | FIRST_COMPLETED returns out of order, returns only the finished turn, or interrupts the others. |
| AC-17 | `stream_wait::CodexTurnsWaitHostTests::test_an_all_completed_wait_returns_running_snapshots_at_its_timeout_and_sends_nothing` | H | ALL_COMPLETED ignores its timeout or touches the turns. The 0.2 s timeout elapses by design. |
| AC-18 | `feature_records::CodexFeatureInputRecordTests::test_a_wait_takes_one_to_1024_distinct_handles_and_stores_them_as_a_tuple`; `stream_wait::CodexTurnsWaitHostTests::test_bad_handle_tuples_are_refused_before_any_wait` | R, H | An empty, duplicated or oversized tuple is accepted, or an unknown handle is found only after waiting. |
| AC-19 | `mcp_memory::CodexMcpServerHostTests::test_one_server_page_maps_its_tools_resources_and_statuses`; `mcp_memory::CodexMcpServerHostTests::test_the_listing_works_on_a_host_without_the_experimental_api` | H | A server is mapped wrongly (unsorted tools, or an absent runtime status not read as NOT_REPORTED), or the stable listing is gated as experimental. |
| AC-20 | `settings_modes::CodexTurnSettingsHostTests::test_a_running_turn_takes_one_settings_update_and_returns_codexs_status`; `settings_modes::CodexTurnSettingsHostTests::test_an_ended_or_unknown_turn_is_refused_locally_and_sends_nothing` | H | A turn-settings update reaches an ended or unowned turn, or Codex's status is lost. |
| AC-21 | `mcp_memory::CodexMemoryHostTests::test_a_paused_goal_thread_is_loaded_then_its_memory_set_then_status_and_reset_are_sent` | H | The memory calls skip the load guard on a paused-goal thread, or send extra requests. The exact order is compared. |
| AC-22 | `side_chat::CodexSideChatFlowTests::test_a_side_chat_forks_the_last_completed_turn_injects_the_boundary_and_starts_its_turn_on_the_fork` | H | The side chat names, unsubscribes or injects into the parent, forks from the wrong turn, or skips the boundary item or the instructions. The fork, inject and turn params are compared exactly. |
| AC-23 | `side_chat::CodexSideChatRefusalTests::test_a_failed_inject_names_the_fork_releases_its_tools_and_registers_no_turn` | H | A failed inject leaves the fork's tool handler or a turn behind. A later tool call on the fork must get the unregistered answer while the parent's still works. |
| AC-24 | `worktree::CodexWorktreeHostTests::test_a_worktree_is_made_under_the_vidbyte_root_on_a_new_branch_from_head_and_codex_hears_nothing`; `worktree::CodexWorktreeHostTests::test_an_existing_target_folder_is_refused_before_git_runs`; `worktree::CodexWorktreeHostTests::test_without_git_on_path_the_call_reports_that_git_could_not_start` | H, G | The worktree lands outside the root or on the wrong branch, an existing folder is reused, or a missing git is not a clear packet. Real git runs on temporary repositories, and a branch's absence proves git never ran. |
| AC-25 | `goal_control::CodexGoalPauseHostTests::test_pausing_a_tracked_goal_run_sends_one_user_set_and_the_run_ends_paused` | H | Pause sends the wrong set, or leaves the tracked goal run open. |
| AC-26 | `goal_control::CodexGoalResumeHostTests::test_a_resumable_goal_is_resumed_with_a_status_only_set_and_its_run_is_tracked`; `goal_control::CodexGoalResumeHostTests::test_an_active_or_complete_goal_is_refused_before_thread_resume`; `goal_control::CodexGoalResumeHostTests::test_a_spent_budget_is_refused_until_edit_raises_it_then_the_goal_resumes` | H | A goal that cannot resume, or a spent budget, reaches `thread/resume`, or a resumed goal run is not tracked. |
| AC-27 | `goal_control::CodexGoalResumeHostTests::test_a_resume_whose_start_window_elapses_is_cancelled_once_and_cleaned_up` | H | A resume whose start window elapses is not cancelled exactly once, or its cleanup is skipped. The window is patched to 0.2 s. |
| AC-28 | `goal_control::CodexGoalEditClearHostTests::test_an_edit_sends_only_the_objective_or_the_budget_with_the_user_origin`; `goal_control::CodexGoalEditClearHostTests::test_a_budget_codex_did_not_keep_is_a_protocol_mismatch` | H | An edit carries `status`, or a budget Codex did not keep passes. |
| AC-29 | `goal_control::CodexGoalEditClearHostTests::test_clearing_an_idle_threads_goal_returns_codexs_cleared`; `goal_control::CodexGoalEditClearHostTests::test_clearing_a_running_thread_is_refused_and_no_clear_is_sent` | H | A clear is sent on a running thread, or the idle clear's answer is lost. |
| AC-30 | `thread_admin::CodexArchiveRenameHostTests::test_archive_unarchive_and_rename_send_their_one_call_each`; `thread_admin::CodexArchiveRenameHostTests::test_an_overloaded_rename_is_retried_and_an_overloaded_archive_is_not`; `thread_admin::CodexHistoryChangeHostTests::test_history_changing_calls_refuse_a_thread_this_host_is_running_before_any_request` | H | Archive, unarchive or rename send extra calls or retry the wrong method, or a busy thread is archived. |
| AC-31 | `thread_admin::CodexHistoryChangeHostTests::test_revert_sends_one_call_after_the_read_and_returns_codexs_thread` | H | Revert is sent without its read, or returns the wrong record. |
| AC-32 | `feature_records::CodexFeatureInputRecordTests::test_injected_items_are_json_objects_with_a_type_stored_as_copies`; `thread_admin::CodexHistoryChangeHostTests::test_inject_sends_the_items_exactly_as_given_and_logs_none_of_them`; `thread_admin::CodexHistoryChangeHostTests::test_inject_refuses_bad_item_lists_before_any_request` | R, H | Inject alters the items, logs them, or sends a bad list. |
| AC-33 | `thread_admin::CodexTerminalSearchChildHostTests::test_background_terminals_are_listed_and_cleaned_after_one_exists_check`; `thread_admin::CodexTerminalSearchChildHostTests::test_search_names_every_top_level_source_and_finds_this_hosts_threads`; `thread_admin::CodexTerminalSearchChildHostTests::test_child_listing_names_the_parent_or_ancestor_and_every_source_kind` | H | Search omits `sourceKinds` (so app-server threads are never found), a listing loads the thread, or extra requests are sent. |
| AC-34 | `feature_contract::CodexFeatureFailureTests::test_a_json_rpc_error_on_each_functions_own_method_is_its_own_packet_with_one_failed_call_record` | H | A JSON-RPC error is reported under another operation, without its thread sentence, logged twice, or with private text. There are 22 rows, one per talking function. |
| AC-35 | `tools::CodexHostToolsShapeTests::test_toolset_holds_the_fifteen_tools_with_their_spec_schemas`; `tool_hardening::CodexToolSurfaceGuardTests::test_the_toolset_holds_26_tools_and_offers_no_forbidden_parameter`; `feature_tools::CodexFeatureToolCatalogTests::test_the_sixteen_tools_follow_the_old_ones_in_function_order_and_none_is_a_no_tool_function`; `feature_tools::CodexFeatureToolCatalogTests::test_no_new_schema_offers_a_posture_parameter` | T | The catalog is not the 42 tools in order, offers a posture parameter, or names a developer-only function. |
| AC-36 | `feature_tools::CodexFeatureToolArgumentTests::test_the_side_chat_tool_narrows_the_scope_posture_to_read_only_and_never_asking`; `feature_tools::CodexFeatureToolHostTests::test_the_side_chat_tool_sends_never_and_no_reviewer_on_the_fork_and_the_turn`; `feature_tools::CodexFeatureToolHostTests::test_the_side_chat_tool_starts_on_a_user_reviewer_parent_because_its_fork_never_asks` | T, H | The side-chat tool inherits a writable sandbox or a person-approval posture. It is checked on a stub host and on the real wire. |
| AC-37 | `feature_tools::CodexFeatureToolScopeTests::test_a_full_cap_refuses_the_plan_side_chat_and_resume_tools_before_the_host`; `tools::CodexHostToolErrorTests::test_every_tool_turns_host_errors_into_error_results`; `tool_hardening::CodexToolLocalFailureTests::test_a_runtime_or_key_error_becomes_an_api_error_result_naming_only_the_tool_and_type`; `feature_tools::CodexFeatureToolScopeTests::test_the_turn_settings_tool_answers_the_status_text_and_sends_no_tier_or_reviewer`; `feature_tools::CodexFeatureToolScopeTests::test_the_multi_wait_returns_one_json_snapshot_per_handle_without_items_and_caps_its_wait` | T | A cap slot leaks, an error escapes as an exception, or the turn-settings or multi-wait output is wrong. |
| AC-38 | `feature_structure::CodexFeatureImportSafetyTests::test_importing_the_host_and_each_mixin_loads_no_sdk_and_no_sdk_collaborator`; `feature_structure::CodexFeatureImportSafetyTests::test_the_five_sdk_free_modules_import_openai_codex_only_under_type_checking`; `packaging::CodexHostImportSafetyTests::test_imports_never_load_the_sdk_and_entering_reports_the_pip_extra` | S | Importing the host loads openai-codex, or an SDK-free module imports it at module level. A fresh interpreter and an AST scan check it. |
| AC-39 | the run itself: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py`, then `python scripts/run_ci.py`; every test passes except the inherited `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` | all | A superseded or collateral test stays red, or another area regresses. This is the run itself, not a test. |
| AC-40 | `python lint/run.py` ends `SDK-LINT: PASS` with no baseline raised; `tests/features/codex_host/test_codex_host_feature_structure.py::CodexFeatureFileSizeTests::test_every_touched_or_new_file_stays_within_its_ceiling`; `tests/features/codex_host/test_codex_host_hardening_contract.py::CodexHardeningConstantTests::test_no_native_host_module_binds_a_top_level_constant` (C021 by AST) | S | Lint fails, a baseline is raised, or a file passes its ceiling. `host.py` is 937 lines today against a ceiling of 900, so the ceiling test is red now. |
| AC-41 | `feature_contract::CodexFeatureFailureTests::test_an_unmodeled_answer_missing_a_member_or_with_a_wrong_type_is_a_protocol_mismatch_inside_the_call`; `settings_modes::CodexCollaborationModeListHostTests::test_a_malformed_preset_answer_is_a_protocol_mismatch_naming_the_method` | H | A malformed unmodeled answer escapes as a KeyError or AttributeError, or is recorded as a success. |
| AC-42 | `side_chat::CodexSideChatRefusalTests::test_a_fork_codex_routes_to_a_user_reviewer_is_refused_before_the_inject_on_a_host_without_a_handler` | H | A side chat runs on a fork whose approvals go to a person, on a host without a handler. |
| AC-43 | `stream_wait::CodexTurnStreamHostTests::test_a_subscription_never_iterated_holds_nothing_and_reads_one_gap_then_ended` | H | A never-iterated subscription holds the window, or reads more than one GAP and ENDED. |
| AC-44 | `stream_wait::CodexTurnStreamHostTests::test_the_host_bound_drops_each_turns_own_oldest_events_and_refunds_them_on_release` | H | The host bound drops another turn's events, or is not refunded on release. |

### Invariants, edge cases, requirements and threats

Each row lists the tests that name the ID in their own comment or docstring, plus the tests a reader would look for that the scan cannot see. A row with "—" is a gate or an N/A, and its note says which.

| Spec ID | Tests | Note |
|---|---|---|
| INV-1 | `stream_wait::test_stream_codex_turn_checks_its_argument_at_the_call`; `inputs::test_every_public_method_refuses_a_bad_argument_before_any_request` |  |
| INV-2 | `feature_contract::test_a_json_rpc_error_on_each_functions_own_method_is_its_own_packet_with_one_failed_call_record`; `mcp_memory::test_a_server_answer_the_sdk_model_rejects_is_a_protocol_mismatch`; `mcp_memory::test_codex_refusing_the_memory_mode_names_the_thread`; `settings_modes::test_codex_refusing_the_update_is_an_api_error_with_codexs_own_message`; `stream_wait::test_streaming_without_a_running_loop_raises_pythons_own_runtime_error` |  |
| INV-3 | `feature_contract::test_a_json_rpc_error_on_each_functions_own_method_is_its_own_packet_with_one_failed_call_record` |  |
| INV-4 | `feature_contract::test_without_the_experimental_api_the_stable_functions_still_talk_to_codex`; `mcp_memory::test_the_listing_works_on_a_host_without_the_experimental_api` |  |
| INV-5 | `settings_modes::test_a_plan_mode_spawn_sends_the_model_codex_resolved_and_is_priced_as_it`; `settings_modes::test_an_update_sends_one_settings_call_holding_only_the_fields_that_were_set`; `goal_control::test_an_edit_sends_only_the_objective_or_the_budget_with_the_user_origin`; `thread_admin::test_child_listing_names_the_parent_or_ancestor_and_every_source_kind`; `sdk_contract::test_the_experimental_fields_are_missing_from_the_generated_params_so_they_are_added_after_validation` | The mode and the lineage filters on the wire, and JSON null for a cleared tier and a removed budget. |
| INV-6 | `feature_contract::test_an_unmodeled_answer_missing_a_member_or_with_a_wrong_type_is_a_protocol_mismatch_inside_the_call`; `mcp_memory::test_a_server_answer_the_sdk_model_rejects_is_a_protocol_mismatch`; `settings_modes::test_a_malformed_preset_answer_is_a_protocol_mismatch_naming_the_method` |  |
| INV-7 | `goal_control::test_an_overloaded_goal_set_is_sent_once`; `goal_control::test_an_overloaded_clear_is_retried`; `thread_admin::test_an_overloaded_rename_is_retried_and_an_overloaded_archive_is_not`; `thread_admin::test_an_unknown_parent_stops_at_the_exists_check_and_an_overloaded_listing_is_retried` |  |
| INV-8 | `goal_control::test_a_resume_whose_start_window_elapses_is_cancelled_once_and_cleaned_up`; `worktree::test_a_git_run_that_outlives_the_bound_is_stopped_and_reported_as_timed_out`; `stream_wait::test_an_all_completed_wait_returns_running_snapshots_at_its_timeout_and_sends_nothing` | The request bound itself is slice 1's, already proven with the bound patched small. |
| INV-9 | `feature_contract::test_a_json_rpc_error_on_each_functions_own_method_is_its_own_packet_with_one_failed_call_record`; `mcp_memory::test_a_servers_error_text_is_returned_to_the_caller_but_reaches_no_log_record` |  |
| INV-10 | `feature_records::test_a_goal_request_refuses_a_collaboration_mode_naming_the_field`; `feature_records::test_the_plan_side_chat_and_resume_records_refuse_every_field_their_row_names`; `settings_modes::test_each_other_setting_reaches_its_own_wire_key_and_nothing_else_is_sent`; `hardening_contract::test_the_changed_texts_and_rejected_field_rows_hold_their_new_values` |  |
| INV-11 | `settings_modes::test_each_other_setting_reaches_its_own_wire_key_and_nothing_else_is_sent`; `settings_modes::test_the_sandbox_policy_is_built_exactly_as_a_turn_builds_it` |  |
| INV-12 | `feature_constants::test_the_goal_status_sets_are_the_resumable_and_the_load_safe_statuses`; `mcp_memory::test_a_not_loaded_thread_with_an_active_goal_is_refused_before_any_resume`; `settings_modes::test_a_running_turn_keeps_running_while_its_thread_settings_change`; `settings_modes::test_a_not_loaded_thread_with_an_active_goal_is_refused_before_any_resume`; `settings_modes::test_a_user_reviewer_is_refused_locally_on_a_host_without_an_approval_handler`; `settings_modes::test_an_unknown_thread_is_refused_by_its_existence_read`; `settings_modes::test_a_mode_model_codex_does_not_list_is_refused_before_the_thread_starts`; `settings_modes::test_an_unknown_model_or_a_user_reviewer_is_refused_before_the_update` |  |
| INV-13 | `settings_modes::test_the_mode_settings_take_the_first_model_set_and_any_named_effort`; `settings_modes::test_a_mode_model_is_checked_by_preflight_and_prices_the_turn`; `settings_modes::test_a_mode_turn_on_a_thread_without_a_reported_model_is_refused_before_turn_start`; `side_chat::test_the_side_chat_is_priced_as_the_forks_model_and_a_mode_takes_that_model` |  |
| INV-14 | `feature_records::test_a_mode_whose_model_or_effort_differs_from_the_turns_is_refused_when_built`; `feature_records::test_a_mode_that_conflicts_with_the_updates_model_is_refused_naming_the_method`; `feature_records::test_a_mode_kind_of_none_is_refused_with_the_kind_message` |  |
| INV-15 | `settings_modes::test_the_presets_come_back_in_codex_order_with_nulls_read_as_blank`; `settings_modes::test_a_malformed_preset_answer_is_a_protocol_mismatch_naming_the_method` | Named in the class docstring; every test of the class serves it. |
| INV-16 | `feature_records::test_from_preset_never_conflicts_with_the_turn_it_was_built_for`; `settings_modes::test_the_callers_turn_model_and_effort_win_over_the_preset`; `settings_modes::test_a_user_reviewer_is_refused_before_the_presets_are_listed` |  |
| INV-17 | `settings_modes::test_a_plan_run_lists_the_presets_then_spawns_one_plan_turn_whose_plan_is_the_answer` |  |
| INV-18 | `feature_constants::test_the_stream_table_is_read_only_and_never_streams_raw_reasoning`; `stream_wait::test_a_streamed_turn_yields_each_event_in_order_then_one_ended`; `stream_wait::test_goal_runs_and_reviews_end_their_streams_with_ended` |  |
| INV-19 | `stream_wait::test_a_slow_approval_handler_holds_an_open_stream_and_every_event_arrives_once_it_answers`; `stream_wait::test_a_stalled_subscriber_gets_one_gap_then_the_kept_window_and_never_delays_the_turn`; `stream_wait::test_a_notification_that_cannot_be_translated_is_logged_once_and_shown_as_a_gap` |  |
| INV-20 | `stream_wait::test_a_stalled_subscriber_gets_one_gap_then_the_kept_window_and_never_delays_the_turn`; `stream_wait::test_an_event_larger_than_the_text_bound_is_dropped_and_counted` |  |
| INV-21 | `stream_wait::test_a_streamed_turn_yields_each_event_in_order_then_one_ended`; `stream_wait::test_an_abandoned_subscription_releases_the_window_once_asyncio_finalizes_it`; `stream_wait::test_goal_runs_and_reviews_end_their_streams_with_ended`; `stream_wait::test_a_dead_app_server_ends_every_stream_with_ended` |  |
| INV-22 | `stream_wait::test_an_ended_turn_streams_only_ended_and_an_unknown_handle_is_refused_at_the_call`; `stream_wait::test_a_stream_called_or_iterated_on_another_loop_is_refused`; `stream_wait::test_a_fast_and_a_stalled_subscriber_keep_their_own_positions` |  |
| INV-23 | `stream_wait::test_an_all_completed_wait_returns_running_snapshots_at_its_timeout_and_sends_nothing`; `stream_wait::test_a_turn_that_already_ended_returns_a_first_completed_wait_at_once` |  |
| INV-24 | `mcp_memory::test_every_filter_and_page_field_reaches_the_wire_and_the_optional_members_map` |  |
| INV-25 | `feature_tools::test_the_turn_settings_tool_answers_the_status_text_and_sends_no_tier_or_reviewer`; `settings_modes::test_an_ended_or_unknown_turn_is_refused_locally_and_sends_nothing`; `settings_modes::test_a_goal_run_is_targeted_through_its_current_physical_turn`; `settings_modes::test_an_unknown_model_or_a_user_reviewer_is_refused_before_the_update` |  |
| INV-26 | `mcp_memory::test_a_loaded_thread_is_not_loaded_again_and_an_unknown_one_stops_at_its_read`; `mcp_memory::test_a_not_loaded_thread_with_an_active_goal_is_refused_before_any_resume`; `mcp_memory::test_the_status_minimum_is_optional_and_bounded_by_the_schema_range`; `mcp_memory::test_a_memory_status_codex_reports_as_not_ready_is_returned_as_is` |  |
| INV-27 | `side_chat::test_the_requests_own_developer_instructions_come_first_then_a_blank_line_then_the_side_chat_text`; `side_chat::test_the_parents_vidbyte_tools_stay_callable_from_the_side_chat`; `side_chat::test_the_side_chat_is_priced_as_the_forks_model_and_a_mode_takes_that_model`; `side_chat::test_a_user_reviewer_with_policy_never_or_a_host_with_a_handler_starts_the_side_chat` |  |
| INV-28 | `side_chat::test_a_failed_turn_start_names_the_fork_releases_its_tools_and_registers_no_turn`; `side_chat::test_a_parent_with_no_completed_turn_is_refused_before_the_fork_with_the_side_chats_operation`; `side_chat::test_an_unknown_parent_an_unknown_model_or_a_user_reviewer_request_sends_no_fork` |  |
| INV-29 | `worktree::test_a_worktree_is_made_under_the_vidbyte_root_on_a_new_branch_from_head_and_codex_hears_nothing`; `worktree::test_a_base_ref_is_given_to_git_and_unsafe_branch_characters_become_dashes_in_the_folder_name` |  |
| INV-30 | `goal_control::test_a_thread_without_a_stored_goal_is_refused_after_the_goal_read` |  |
| INV-31 | `feature_constants::test_the_goal_status_sets_are_the_resumable_and_the_load_safe_statuses`; `goal_control::test_an_active_or_complete_goal_is_refused_before_thread_resume`; `goal_control::test_a_resume_whose_start_window_elapses_is_cancelled_once_and_cleaned_up`; `goal_control::test_a_thread_this_host_is_running_is_refused_before_any_request` |  |
| INV-32 | `goal_control::test_an_edit_sends_only_the_objective_or_the_budget_with_the_user_origin`; `goal_control::test_a_budget_codex_did_not_keep_is_a_protocol_mismatch` |  |
| INV-33 | `goal_control::test_clearing_an_idle_threads_goal_returns_codexs_cleared` |  |
| INV-34 | `goal_control::test_clearing_a_running_thread_is_refused_and_no_clear_is_sent`; `thread_admin::test_history_changing_calls_refuse_a_thread_this_host_is_running_before_any_request`; `thread_admin::test_history_changing_calls_refuse_a_thread_codex_reports_running`; `thread_admin::test_a_second_history_change_on_the_same_thread_is_refused_while_the_first_waits` |  |
| INV-35 | `thread_admin::test_archive_unarchive_and_rename_send_their_one_call_each` |  |
| INV-36 | `thread_admin::test_revert_sends_one_call_after_the_read_and_returns_codexs_thread` |  |
| INV-37 | `feature_records::test_injected_items_are_json_objects_with_a_type_stored_as_copies`; `thread_admin::test_inject_sends_the_items_exactly_as_given_and_logs_none_of_them`; `thread_admin::test_inject_sends_a_copy_so_a_later_change_by_the_caller_changes_nothing` |  |
| INV-38 | `thread_admin::test_background_terminals_are_listed_and_cleaned_after_one_exists_check` |  |
| INV-39 | `thread_admin::test_search_names_every_top_level_source_and_finds_this_hosts_threads`; `thread_admin::test_an_archived_search_sends_its_flag_and_page_fields` |  |
| INV-40 | `thread_admin::test_child_listing_names_the_parent_or_ancestor_and_every_source_kind` |  |
| INV-41 | `feature_tools::test_every_new_description_has_four_or_five_sentences_and_each_write_one_names_paid_codex_work`; `packaging::test_imports_never_load_the_sdk_and_entering_reports_the_pip_extra`; `tool_hardening::test_the_toolset_holds_26_tools_and_offers_no_forbidden_parameter`; `tools::test_toolset_holds_the_fifteen_tools_with_their_spec_schemas` |  |
| INV-42 | `feature_tools::test_running_every_new_tool_never_reaches_a_function_that_has_no_tool` |  |
| INV-43 | `feature_tools::test_the_side_chat_tool_narrows_the_scope_posture_to_read_only_and_never_asking`; `feature_tools::test_the_plan_tool_passes_the_scope_posture_and_the_resume_tool_drops_the_fields_resume_refuses`; `feature_tools::test_the_multi_wait_returns_one_json_snapshot_per_handle_without_items_and_caps_its_wait` |  |
| INV-44 | `feature_tools::test_a_tool_over_a_host_without_the_experimental_api_returns_the_gate_as_an_error_result` |  |
| INV-45 | `feature_structure::test_the_host_module_imports_no_sdk_collaborator_at_module_level` |  |
| INV-46 | `hardening_contract::test_no_native_host_module_binds_a_top_level_constant`; `feature_constants::test_no_new_name_goes_into_the_shared_codex_constants` | The AST scan walks every module of `vidbyte/harnesses/native`, so it covers the new mixins; C021 in `lint/run.py` checks the same rule. |
| INV-47 | `feature_structure::test_every_touched_or_new_file_stays_within_its_ceiling`; `feature_structure::test_the_shared_codex_records_and_the_codex_agent_config_keep_their_bytes` |  |
| INV-48 | `feature_structure::test_the_changed_signatures_take_the_new_parameters`; `settings_modes::test_the_last_plan_answers_only_when_no_agent_message_does` | Every pre-existing test of the pack and `tests/test_codex_*.py` (1,040 passing today) must stay green; NFR-10's rows check that a request without a mode sends no `collaborationMode` key. |
| INV-49 | `tools::test_toolset_holds_the_fifteen_tools_with_their_spec_schemas`; `helper_tools::test_the_toolset_appends_eleven_tools_and_none_is_delete`; `feature_tools::test_the_sixteen_tools_follow_the_old_ones_in_function_order_and_none_is_a_no_tool_function` | The first 26 rows of `TOOL_TABLE` are unchanged, so the older shape tests still pin them. |
| INV-50 | `feature_structure::test_no_new_method_is_defined_on_codex_host_itself` |  |
| INV-51 | `feature_constants::test_both_goal_start_calls_map_their_window_to_an_api_error` | The goal-run tests of `test_codex_host_goal_skills.py` and `test_codex_host_review_goals.py` are unchanged and pass. |
| INV-52 | `feature_constants::test_the_goal_status_sets_are_the_resumable_and_the_load_safe_statuses` | The compact, delete and continue guard tests of `test_codex_host_thread_helpers.py`, `test_codex_host_function_rows.py` and the `helper_surface` text pins are unchanged and pass. |
| INV-53 | `feature_constants::test_the_process_package_export_list_does_not_gain_the_git_helper` |  |
| INV-54 | `feature_structure::test_the_shared_codex_records_and_the_codex_agent_config_keep_their_bytes` | `tests/test_codex_*.py` is unchanged and passes. |
| INV-55 | `settings_modes::test_a_plan_question_on_a_host_without_a_handler_gets_slice_ones_empty_answer` |  |
| EC-1 | `feature_contract::test_every_new_method_on_a_host_never_entered_is_refused_as_not_open_before_its_record`; `feature_contract::test_every_talking_method_on_a_closed_host_reports_process_exited_and_sends_nothing` |  |
| EC-2 | `feature_contract::test_every_new_method_called_from_another_loop_is_refused_with_the_other_loop_text`; `stream_wait::test_a_stream_called_or_iterated_on_another_loop_is_refused` |  |
| EC-3 | `stream_wait::test_streaming_without_a_running_loop_raises_pythons_own_runtime_error` |  |
| EC-4 | `feature_contract::test_an_app_server_that_dies_during_a_new_call_ends_it_with_process_exited_naming_the_thread`; `stream_wait::test_a_dead_app_server_ends_every_stream_with_ended` |  |
| EC-5 | `settings_modes::test_a_running_turn_keeps_running_while_its_thread_settings_change` |  |
| EC-6 | `feature_docs::test_each_documented_limit_is_in_its_methods_docstring` | Docstring row: a running turn keeps its price. |
| EC-7 | `feature_records::test_a_collaboration_mode_needs_a_model_in_the_mode_or_the_update` |  |
| EC-8 | `settings_modes::test_an_unknown_model_is_refused_before_the_thread_is_read` |  |
| EC-9 | `settings_modes::test_a_user_reviewer_is_refused_locally_on_a_host_without_an_approval_handler`; `settings_modes::test_a_user_reviewer_is_sent_when_the_host_has_an_approval_handler` |  |
| EC-10 | `settings_modes::test_codex_refusing_the_update_is_an_api_error_with_codexs_own_message` |  |
| EC-11 | `settings_modes::test_a_cli_without_the_preset_list_is_relabelled_as_the_plan_run` |  |
| EC-12 | `feature_records::test_from_preset_uses_the_providers_effort_for_an_effort_the_enum_lacks`; `settings_modes::test_a_preset_effort_vidbyte_lacks_leaves_the_effort_to_codex` |  |
| EC-13 | `feature_records::test_from_preset_takes_the_presets_model_and_effort_only_where_the_turn_sets_none`; `settings_modes::test_the_callers_turn_model_and_effort_win_over_the_preset` |  |
| EC-14 | `settings_modes::test_a_mode_turn_on_a_thread_without_a_reported_model_is_refused_before_turn_start` |  |
| EC-15 | `feature_docs::test_each_documented_limit_is_in_its_methods_docstring` | Docstring row: how to leave plan mode. |
| EC-16 | `settings_modes::test_a_plan_question_on_a_host_without_a_handler_gets_slice_ones_empty_answer` |  |
| EC-17 | `stream_wait::test_a_subscriber_that_leaves_early_through_aclosing_releases_at_once` |  |
| EC-18 | `stream_wait::test_a_fast_and_a_stalled_subscriber_keep_their_own_positions` |  |
| EC-19 | `stream_wait::test_an_event_larger_than_the_text_bound_is_dropped_and_counted` |  |
| EC-20 | `stream_wait::test_a_notification_that_cannot_be_translated_is_logged_once_and_shown_as_a_gap` |  |
| EC-21 | `stream_wait::test_bad_handle_tuples_are_refused_before_any_wait` |  |
| EC-22 | `stream_wait::test_cancelling_the_waiter_leaves_every_turn_running` |  |
| EC-23 | `settings_modes::test_a_turn_model_change_leaves_the_turn_priced_as_its_start_model` |  |
| EC-24 | `settings_modes::test_a_goal_run_is_targeted_through_its_current_physical_turn` |  |
| EC-25 | `settings_modes::test_codex_rejecting_an_unsupported_turn_setting_keeps_its_message` |  |
| EC-26 | `mcp_memory::test_an_unknown_thread_filter_is_codexs_own_refusal_with_no_read_first` |  |
| EC-27 | `mcp_memory::test_servers_waiting_to_start_or_for_sign_in_report_their_statuses` |  |
| EC-28 | `feature_records::test_the_memory_threshold_is_the_schemas_range`; `mcp_memory::test_the_status_minimum_is_optional_and_bounded_by_the_schema_range` |  |
| EC-29 | `mcp_memory::test_a_not_loaded_thread_with_an_active_goal_is_refused_before_any_resume` |  |
| EC-30 | `side_chat::test_a_side_chat_forks_the_last_completed_turn_injects_the_boundary_and_starts_its_turn_on_the_fork`; `side_chat::test_a_fork_codex_routes_to_a_user_reviewer_is_refused_before_the_inject_on_a_host_without_a_handler` |  |
| EC-31 | `side_chat::test_a_parent_with_no_completed_turn_is_refused_before_the_fork_with_the_side_chats_operation` |  |
| EC-32 | `feature_records::test_the_plan_side_chat_and_resume_records_refuse_every_field_their_row_names`; `side_chat::test_a_name_tools_an_ephemeral_setting_a_prompt_or_a_goal_in_the_request_is_refused_before_any_request` |  |
| EC-33 | `side_chat::test_a_side_chat_cancelled_after_codex_accepted_its_turn_has_that_turn_interrupted_once` |  |
| EC-34 | `worktree::test_a_folder_outside_git_a_branch_that_exists_or_an_unknown_base_ref_reports_gits_exit_code_and_first_stderr_line`; `worktree::test_a_first_stderr_line_longer_than_the_cap_is_cut_to_500_characters_and_never_logged` |  |
| EC-35 | `worktree::test_a_bad_branch_base_ref_or_repository_is_refused_before_git_runs_or_the_root_is_made` |  |
| EC-36 | `worktree::test_a_git_run_that_outlives_the_bound_is_stopped_and_reported_as_timed_out` |  |
| EC-37 | `goal_control::test_a_refused_resume_set_sends_no_cancel_and_still_cleans_up` |  |
| EC-38 | `goal_control::test_a_resume_cancelled_after_its_set_was_sent_adopts_the_late_run_and_stops_it_once` |  |
| EC-39 | `goal_control::test_a_thread_this_host_is_running_is_refused_before_any_request` |  |
| EC-40 | `goal_control::test_a_thread_without_a_stored_goal_is_refused_after_the_goal_read` |  |
| EC-41 | `feature_records::test_a_goal_edit_changes_something_and_never_sets_and_clears_the_budget_together`; `goal_control::test_an_edit_that_changes_nothing_or_sets_and_clears_the_budget_is_refused` |  |
| EC-42 | `thread_admin::test_history_changing_calls_refuse_a_thread_codex_reports_running` |  |
| EC-43 | `thread_admin::test_unarchiving_a_thread_that_is_not_archived_is_codexs_refusal` |  |
| EC-44 | `thread_admin::test_revert_leaves_the_snapshots_this_host_tracked_and_codex_lists_the_new_history` |  |
| EC-45 | `thread_admin::test_revert_with_an_unknown_turn_is_codexs_refusal` |  |
| EC-46 | `feature_records::test_injected_items_are_json_objects_with_a_type_stored_as_copies`; `thread_admin::test_inject_refuses_bad_item_lists_before_any_request` |  |
| EC-47 | `thread_admin::test_terminals_of_a_not_loaded_thread_are_listed_without_loading_it` |  |
| EC-48 | `feature_records::test_a_search_query_must_not_be_blank_and_a_rename_needs_a_one_line_name`; `thread_admin::test_bad_page_and_query_arguments_are_refused_before_any_request` |  |
| EC-49 | `thread_admin::test_child_listing_names_the_parent_or_ancestor_and_every_source_kind` |  |
| EC-50 | `thread_admin::test_an_unknown_parent_stops_at_the_exists_check_and_an_overloaded_listing_is_retried` |  |
| EC-51 | `feature_records::test_page_requests_refuse_a_limit_outside_one_to_a_thousand_and_a_cursor_that_is_not_text`; `thread_admin::test_bad_page_and_query_arguments_are_refused_before_any_request` |  |
| EC-52 | `feature_tools::test_the_wait_and_turn_settings_tools_refuse_a_handle_this_scope_does_not_own` |  |
| EC-53 | `feature_tools::test_a_mode_in_the_scope_defaults_makes_the_plan_tool_return_an_error_naming_it` |  |
| EC-54 | `feature_tools::test_a_tool_over_a_host_without_the_experimental_api_returns_the_gate_as_an_error_result` |  |
| EC-55 | `stream_wait::test_a_slow_approval_handler_holds_an_open_stream_and_every_event_arrives_once_it_answers` |  |
| EC-56 | `thread_admin::test_search_names_every_top_level_source_and_finds_this_hosts_threads` |  |
| EC-57 | `thread_admin::test_a_safe_goal_or_no_goal_loads_the_thread_and_keeps_its_status`; `thread_admin::test_an_active_goal_is_refused_before_the_thread_is_loaded` | Named in the class docstring; every test of the class serves it. |
| EC-58 | `goal_control::test_a_spent_budget_is_refused_until_edit_raises_it_then_the_goal_resumes` |  |
| EC-59 | `feature_tools::test_the_side_chat_tool_starts_on_a_user_reviewer_parent_because_its_fork_never_asks`; `side_chat::test_a_fork_codex_routes_to_a_user_reviewer_is_refused_before_the_inject_on_a_host_without_a_handler` |  |
| EC-60 | `stream_wait::test_a_subscription_never_iterated_holds_nothing_and_reads_one_gap_then_ended`; `stream_wait::test_an_abandoned_subscription_releases_the_window_once_asyncio_finalizes_it` |  |
| EC-61 | `feature_docs::test_each_documented_limit_is_in_its_methods_docstring` | Docstring row: the fork may carry an active goal. |
| EC-62 | `stream_wait::test_the_host_bound_drops_each_turns_own_oldest_events_and_refunds_them_on_release` |  |
| NFR-1 | `feature_structure::test_every_touched_or_new_file_stays_within_its_ceiling`; `feature_structure::test_the_shared_codex_records_and_the_codex_agent_config_keep_their_bytes` | See INV-47. Named in the class docstring; every test of the class serves it. |
| NFR-2 | `feature_structure::test_importing_the_host_and_each_mixin_loads_no_sdk_and_no_sdk_collaborator`; `feature_structure::test_the_five_sdk_free_modules_import_openai_codex_only_under_type_checking`; `feature_structure::test_the_host_module_imports_no_sdk_collaborator_at_module_level` | Named in the class docstring; every test of the class serves it. |
| NFR-3 | `stream_wait::test_a_stalled_subscriber_gets_one_gap_then_the_kept_window_and_never_delays_the_turn`; `stream_wait::test_the_host_bound_drops_each_turns_own_oldest_events_and_refunds_them_on_release`; `stream_wait::test_an_event_larger_than_the_text_bound_is_dropped_and_counted` | The four bounds are patched small where §13 says they are read at call time; their full values are pinned in `feature_constants`. |
| NFR-4 | `goal_control::test_a_resume_whose_start_window_elapses_is_cancelled_once_and_cleaned_up`; `worktree::test_a_git_run_that_outlives_the_bound_is_stopped_and_reported_as_timed_out`; `feature_constants::test_every_git_value_holds_its_spec_value_and_the_environment_is_read_only` |  |
| NFR-5 | `feature_contract::test_without_the_experimental_api_the_eleven_functions_and_any_mode_are_refused_with_no_request`; `feature_contract::test_without_the_experimental_api_the_stable_functions_still_talk_to_codex` | Named in the class docstring; every test of the class serves it. |
| NFR-6 | — | Gate, not a test: `python lint/run.py` ends `SDK-LINT: PASS` on this tree with the tests staged (see **Red run**). |
| NFR-7 | `feature_contract::test_a_json_rpc_error_on_each_functions_own_method_is_its_own_packet_with_one_failed_call_record`; `side_chat::test_the_side_chats_prompt_reaches_no_log_record`; `thread_admin::test_inject_sends_the_items_exactly_as_given_and_logs_none_of_them`; `worktree::test_a_first_stderr_line_longer_than_the_cap_is_cut_to_500_characters_and_never_logged` |  |
| NFR-8 | — | Gate, not a test: the source stage's pytest step is red by design until S3 lands, and the package stage installs a wheel with pip, which S2 may not run. |
| NFR-9 | `feature_tools::test_every_new_description_has_four_or_five_sentences_and_each_write_one_names_paid_codex_work` | The sentence count is checked; that the sentences are general and carry no example is left to review. |
| NFR-10 | `settings_modes::test_the_mode_settings_take_the_first_model_set_and_any_named_effort`; `side_chat::test_the_side_chat_is_priced_as_the_forks_model_and_a_mode_takes_that_model` |  |
| NFR-11 | `feature_constants::test_every_new_number_and_fixed_value_holds_its_spec_value`; `feature_records::test_a_wait_takes_one_to_1024_distinct_handles_and_stores_them_as_a_tuple`; `mcp_memory::test_the_status_minimum_is_optional_and_bounded_by_the_schema_range` |  |
| NFR-12 | — | By construction: no test runs `codex`; every host test drives the in-memory app-server, the worktree tests run the real `git`, and the tool tests use a stub host. |
| T-1 | `feature_docs::test_each_documented_limit_is_in_its_methods_docstring`; `feature_tools::test_running_every_new_tool_never_reaches_a_function_that_has_no_tool`; `thread_admin::test_history_changing_calls_refuse_a_thread_this_host_is_running_before_any_request` |  |
| T-2 | `feature_tools::test_running_every_new_tool_never_reaches_a_function_that_has_no_tool` |  |
| T-3 | `feature_tools::test_the_sixteen_tools_follow_the_old_ones_in_function_order_and_none_is_a_no_tool_function`; `side_chat::test_a_side_chat_forks_the_last_completed_turn_injects_the_boundary_and_starts_its_turn_on_the_fork` | No tool injects items, and the side-chat boundary is the fixed Vidbyte item. |
| T-4 | — | N/A in the spec: a host runs one account's private app-server. |
| T-5 | `feature_records::test_option_injection_dot_dot_spaces_and_overlong_refs_are_refused`; `worktree::test_a_bad_branch_base_ref_or_repository_is_refused_before_git_runs_or_the_root_is_made` |  |
| T-6 | — | See NFR-7 and INV-9: the canary tests read every log record. |
| T-7 | — | Out of scope in the spec: Codex owns sign-in, and no new function touches auth. |
| T-8 | `mcp_memory::test_a_servers_error_text_is_returned_to_the_caller_but_reaches_no_log_record` |  |

### Test counts

The slice adds 236 tests: 232 in 14 new modules, and 4 in a new class of `test_codex_host_sdk_contract.py`. It also rewrites the §13 pins in 11 older modules: 9 in round 1, and the two catalog-count pins r4 added to §13 in round 2.

| File | Tests | Red now | Green guards | Without the extra: red / pass / skipped |
|---|---|---|---|---|
| `test_codex_host_feature_records.py` | 42 | 42 | 0 | 42 / 0 / 0 |
| `test_codex_host_feature_constants.py` | 18 | 17 | 1 | 17 / 1 / 0 |
| `test_codex_host_feature_structure.py` | 10 | 9 | 1 | 7 / 1 / 2 |
| `test_codex_host_feature_docs.py` | 1 | 1 | 0 | 1 / 0 / 0 |
| `test_codex_host_feature_tools.py` | 17 | 17 | 0 | 13 / 0 / 4 |
| `test_codex_host_feature_contract.py` | 10 | 9 | 1 | 0 / 0 / 10 |
| `test_codex_host_settings_modes.py` | 32 | 32 | 0 | 0 / 0 / 32 |
| `test_codex_host_stream_wait.py` | 22 | 22 | 0 | 0 / 0 / 22 |
| `test_codex_host_mcp_memory.py` | 13 | 13 | 0 | 0 / 0 / 13 |
| `test_codex_host_side_chat.py` | 13 | 13 | 0 | 0 / 0 / 13 |
| `test_codex_host_worktree.py` | 13 | 13 | 0 | 4 / 0 / 9 |
| `test_codex_host_goal_control.py` | 18 | 18 | 0 | 0 / 0 / 18 |
| `test_codex_host_thread_admin.py` | 22 | 22 | 0 | 0 / 0 / 22 |
| `test_codex_host_first_class_snippet.py` | 1 | 1 | 0 | 0 / 0 / 1 |
| `test_codex_host_sdk_contract.py` (4 new) | 4 | 4 | 0 | 0 / 0 / 4 |
| **Total** | **236** | **233** | **3** | **84 / 2 / 150** |

The three green guards pass today and must keep passing; each can fail:

- `feature_constants::CodexFeatureTextTests::test_no_new_name_goes_into_the_shared_codex_constants` fails if a new constant lands in `vidbyte.lib.constants.codex` instead of `codex_host`.
- `feature_contract::CodexFeatureGuardTests::test_the_guard_table_names_every_new_method` fails if the guard table in the test drifts from the 25 method names, so the guard rows cannot silently skip a method.
- `feature_structure::CodexFeatureFileSizeTests::test_the_shared_codex_records_and_the_codex_agent_config_keep_their_bytes` fails if `vidbyte/lib/dataclasses/codex.py` or `vidbyte/agents/codex/config.py` changes by one byte (D-5, INV-54).

## Tests deliberately NOT written

- **Anything the conversation decided not to build:** the queue, the P2 items, the one-shot mirrors, a stream tool, turn-less notification watching, a new FailureCode, tools for the 9 NG-17/INV-42 functions, and Q-10 and Q-11. No test asks for them; the catalog test pins that no tool exists for the 9 functions.
- **A paid live run of any new function (NFR-12, NG-13).** It spends the user's plan. AC-1 is proven at the seam.
- **How long a slow approval handler pauses a stream (EC-55).** A timed pause needs a wall clock. The test writes the later events while the handler holds the reader, then releases it and requires every event, in order, with no GAP.
- **T-4 and T-7.** The spec marks T-4 N/A and T-7 out of scope; neither has a control to test.
- **NFR-6 and NFR-8 as tests.** They are gates. Lint passes on this tree (see **Red run**); the package stage installs a wheel with pip, which S2 may not run.
- **The generality of the new tool descriptions (NFR-9).** The sentence count and the paid-work sentence are tested; whether a sentence is general is left to review.
- **Property-based testing with hypothesis.** It is not a dependency. `GIT_REF_PATTERN` gets a seeded property test instead (`feature_records::GitWorktreeSpecTests`), which draws refs from a fixed `random.Random` seed and checks the record against the spec's own pattern.

## Red run

**Interpreter.** Nothing was installed. All runs used the pipeline's prepared venv (Python 3.11.0, this worktree importable through `PYTHONPATH`, openai-codex 0.163.0). The global `python` was not used.

**The new modules alone.**

```
PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider tests/features/codex_host/test_codex_host_feature_*.py tests/features/codex_host/test_codex_host_first_class_snippet.py tests/features/codex_host/test_codex_host_goal_control.py tests/features/codex_host/test_codex_host_mcp_memory.py tests/features/codex_host/test_codex_host_settings_modes.py tests/features/codex_host/test_codex_host_side_chat.py tests/features/codex_host/test_codex_host_stream_wait.py tests/features/codex_host/test_codex_host_thread_admin.py tests/features/codex_host/test_codex_host_worktree.py
...
229 failed, 3 passed in 7.33s
```

**The area** (the pack, `harness_threads` and `tests/test_codex_*.py`):

```
PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider --tb=line
FAILED tests/features/codex_host/test_codex_host_worktree.py::GitWorktreesHelperTests::test_add_makes_the_worktree_on_a_new_branch_and_git_runs_with_terminal_prompts_off
FAILED tests/features/codex_host/test_codex_host_worktree.py::GitWorktreesHelperTests::test_add_starts_the_branch_at_the_base_ref_when_one_is_given
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
253 failed, 1041 passed, 3 skipped in 75.50s (0:01:15)
```

The 1,041 that pass are every pre-existing test outside the 19 tests red through rewritten pins (1,038) plus the 3 guards. The 253 failures are the 233 new red tests, the 19 tests red through §13 pins (17 from round 1, plus the two snippet tests r4 added), and the inherited `harness_threads` test, which fails on the slice base too.

**Why each test is red.** One line per failing test, from the `--tb=line` output above:

| Count | Exception |
|---|---|
| 128 | `AttributeError` |
| 48 | `ImportError` |
| 45 | `AssertionError` |
| 28 | `ModuleNotFoundError` |
| 2 | `FileNotFoundError` |
| 1 | `TypeError` |
| 1 | `RuntimeError` |

Every `ImportError`, `ModuleNotFoundError` and `AttributeError` names a module, class, function or constant from spec §8.5, §9.2, §9.3 or §12.3. Every `AssertionError` compares against a spec value the code does not have yet: the 42-tool catalog (also the count the two section-4 snippets print, `26` today), the fifteen method-name constants r4 names, the new enum members and export lists, the seventh goal-rejected field, the fork row's new tail, `host.py`'s 937 lines against its ceiling of 900, the `parse` parameter of `CodexConnection.raw`, the plan fallback of `final_answer`, and the modeled raw answers the connection does not map yet. `TypeError` is `CodexSpawnRequest` refusing the new `collaboration_mode` keyword, `RuntimeError: coroutine raised StopIteration` is `tool_hardening`'s row lookup finding no tool for a new name, and `FileNotFoundError` is `host_core.py`, which does not exist yet. One `AssertionError` is the inherited `harness_threads` test (`assert 167 == 120`).

**Without the extra** (CI's view), with `openai_codex` blocked by a plugin that sets `sys.modules["openai_codex"] = None`:

```
PYTHONPATH="$(pwd);<scratch>/nosdk" "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider -p nosdk_plugin --collect-only
...
1297 tests collected in 1.18s

PYTHONPATH="$(pwd);<scratch>/nosdk" "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider -p nosdk_plugin --tb=line
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
100 failed, 803 passed, 394 skipped in 51.21s
```

Every module collects without the SDK, and every host class is skipped rather than broken.

**The whole repository suite:**

```
PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider --tb=line
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
253 failed, 6572 passed, 27 skipped in 129.26s (0:02:09)
```

All 253 failures are in `tests/features/codex_host/` plus the inherited `harness_threads` test, the same set as the area run, so nothing outside the area was disturbed.

**Lint**, with the new files staged so C021 and the header rules see them:

```
git add tests/features/codex_host && "$V" lint/run.py
...
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

## Superseded pins rewritten (spec §13)

Each change follows §13's "After this spec" column, with a comment that cites it. No other existing assertion was changed.

| File | What changed |
|---|---|
| `codex_host_support.py` | `TOOL_TABLE` gains the 16 §9.2 rows, so `TOOL_NAMES` has 42; `GOAL_REJECTED_FIELDS` gains `"collaboration_mode"` as its seventh entry; `StubCodexHost` inherits `FeatureStubMethods` (one stub method per new tool). |
| `test_codex_host_tools.py` | `_valid_arguments` gains one row per new tool; `len(tools) == 42` in `test_toolset_holds_the_fifteen_tools_with_their_spec_schemas`. `test_default_policy_allows_the_read_tools_and_denies_the_write_tools`, `test_every_tool_turns_host_errors_into_error_results` and `test_mcp_server_lists_and_runs_the_toolset` are red through `TOOL_TABLE`. |
| `test_codex_host_helper_tools.py` | `NEW_ROWS = TOOL_TABLE[15:26]`; `len(tools) == 42`. |
| `test_codex_host_tool_hardening.py` | `NO_HANDLE_ARGUMENTS` gains the 14 new tools that take no handle; `len(tools) == 42`. |
| `test_codex_host_records.py` | `EXPECTED_ENUMS` gains the 9 no-tool operations and the 9 new enums verbatim from §8.5; `SDK_WIRE_SOURCES` gains the 6 wire enums they mirror. |
| `test_codex_host_packaging.py` | `ENUMS_CODEX_ORDER` has 35 names, ASCII-sorted; the import probe expects `(42, "check_codex_ready")`. `test_new_packages_export_exactly_their_spec_lists` is red through `ENUMS_CODEX_ORDER`. |
| `test_codex_host_hardening_contract.py` | The fork row's tail gains `"collaboration_mode"`; `test_every_new_constant_holds_its_spec_value_and_is_exported_in_order` is red through `GOAL_REJECTED_FIELDS`. |
| `test_codex_host_hardening_records.py` | The goal-request test refuses `collaboration_mode` as the seventh field, with `GOAL_FIELD_MESSAGE` naming it. |
| `test_codex_host_inputs.py` | `VALID_RECORDS` has 34 records; the boundary test gains the 22 new coroutine methods that take an argument. `stream_codex_turn`'s own boundary test is `stream_wait::test_stream_codex_turn_checks_its_argument_at_the_call`. |
| `test_codex_host_lifecycle.py` | Round 2 (r4, S2-1): `:101` (`:102` after the cited comment), the snippet's last printed line `"26 check_codex_ready"` → `"42 check_codex_ready"`. `CodexHostSnippetTests::test_the_section_4_snippet_prints_its_three_lines` is red until the sixteen tools exist. |
| `test_codex_host_helper_lifecycle.py` | Round 2 (r4, S2-1): `:109` (`:110` after the cited comment), `"26 False"` → `"42 False"`. `CodexHelperSnippetTests::test_the_section_4_snippet_prints_its_seven_lines` is red until the sixteen tools exist. |
| `test_codex_host_sdk_contract.py` | `CALL_LIST` gains the typed calls and goal-state hooks §13 lists (they exist in 0.163.0, so the old contract tests stay green); the new class `CodexFirstClassSdkContractTests` pins the fork response, the goal-state hooks, the experimental params and the modeled raw answers. |

## Notes for the implementer

- **Patch points the tests use, all read at call time as §13 says:** `vidbyte.harnesses.native.codex.turn_stream.CODEX_HOST_STREAM_EVENT_LIMIT`, `CODEX_HOST_STREAM_TEXT_LIMIT_CHARS` and `CODEX_HOST_STREAM_HOST_EVENT_LIMIT`; `vidbyte.harnesses.native.codex.turn_starts.CODEX_HOST_GOAL_RESUME_START_SECONDS`; `vidbyte.harnesses.native.codex.thread_methods.CODEX_HOST_WORKTREE_TIMEOUT_SECONDS`. A module-level `from ... import` copy taken at import time defeats the patch.
- **The worktree tests run the real `git`.** `CliRunner.find_program` walks `PATH` on Windows, so "git missing" is `PATH` set to an empty folder. They patch `pathlib.Path.home` and check that a failed run left no branch, which proves git never ran. They also check that `GIT_TERMINAL_PROMPT=0` wins over a caller's `1`, through a hook that records the variable.
- **The fake answers every slice-2 method** (the 15 §13 lists, plus the child filters of `thread/list` and the edit and resume forms of `thread/goal/set`) through `codex_host_feature_fakes.FeatureHandlers`. `feature_answers[method]` scripts a malformed answer (AC-41). `thread/fork` copies the parent's reviewer, policy and model unless the params name them.
- **Literal texts come from `codex_host_feature_support.py`,** written from §9.2 and §9.3, never read from production. A changed text therefore fails a test.
- **Do not edit any test.** If a test looks wrong, raise it with the orchestrator.
- **The two section-4 snippet tests print the catalog size.** `lifecycle::CodexHostSnippetTests::test_the_section_4_snippet_prints_its_three_lines` and `helper_lifecycle::CodexHelperSnippetTests::test_the_section_4_snippet_prints_its_seven_lines` expect 42 (r4 §13), so they stay red until all sixteen new tools exist.
- **Names r4 settled are pinned by name:** the fifteen `CODEX_*_METHOD` constants of §9.3 (in `vidbyte.lib.constants.codex_host`, each in `__all__`, none in `vidbyte.lib.constants.codex`). So is `CODEX_HOST_NO_STORED_GOAL_MESSAGE`, with its text and its place in `__all__`; pause, resume and edit check the same text in their packets. `CODEX_HOST_NO_GOAL_MESSAGE` must keep its thread-helpers text.

## Spec defects and ambiguities

All eight are resolved by spec r4 (`d0529d15`, §16 rows S2-1 to S2-8). The r3 finding is kept for the record; the resolution and the round-2 test change follow it.

1. **`CODEX_HOST_NO_GOAL_MESSAGE` was already taken (major).** It exists with the text "Codex reports no goal on the thread after the goal run started.", `run_codex_goal` uses it (`skill_functions.py:217`), and `test_codex_host_helper_surface.py:94` pins it; r3's §9.2 reused the name for pause, resume and edit (EC-40). **Resolved by r4 (S2-2):** the new message is `CODEX_HOST_NO_STORED_GOAL_MESSAGE`, with the same text; `CODEX_HOST_NO_GOAL_CAUSE` and `CODEX_HOST_NO_GOAL_NEXT_STEP` keep their names, and the old message is untouched. Tightened in round 2, at the coordinator's request: `TEXT_NAMES` gains `NO_STORED_GOAL_MESSAGE`, and the support literal is renamed to match. `feature_constants::CodexFeatureTextTests::test_every_new_message_cause_next_step_and_side_chat_text_holds_its_spec_value` now pins the name with its text, and the export-list test requires it in `__all__`. `goal_control` still checks the text through `assert_packet`.
2. **Two 26-tool pins were missing from §13's superseded list (major).** `test_codex_host_lifecycle.py:101` expected `"26 check_codex_ready"` and `test_codex_host_helper_lifecycle.py:109` expected `"26 False"`. **Resolved by r4 (S2-1):** both are in §13 (26 → 42), and the spec author's sweep found no third pin. Rewritten in round 2; see **Superseded pins rewritten**.
3. **13 of the 15 new method-name constants were unnamed.** **Resolved by r4 (S2-3):** §9.3 names all fifteen. Tightened: `feature_constants::CodexFeatureTableTests::test_the_fifteen_method_names_are_named_constants_that_hold_their_wire_strings` (renamed from `..._and_the_first_and_last_are_named`) pins each name to its wire string and its place in `__all__`, through `FEATURE_METHOD_CONSTANTS` in `codex_host_feature_support.py`. The export-list test checks all fifteen names, and the green guard `test_no_new_name_goes_into_the_shared_codex_constants` checks that none lands in `vidbyte.lib.constants.codex`.
4. **The `{name}` of an effort conflict in `CODEX_HOST_MODE_CONFLICT_MESSAGE`.** **Resolved by r4 (S2-4):** `reasoning_effort`. Tightened: the three effort rows (`feature_records::CodexCollaborationModeRecordTests::test_a_conflicting_effort_is_refused_and_a_providers_default_never_conflicts`, `CodexSpawnRequestModeTests::test_a_mode_whose_model_or_effort_differs_from_the_turns_is_refused_when_built`, `CodexThreadSettingsUpdateTests::test_a_mode_that_conflicts_with_the_updates_model_is_refused_naming_the_method`) check the whole text with `reasoning_effort`.
5. **The `{sandbox}` slot of the network-access message.** **Resolved by r4 (S2-5):** the member's `.name`. Tightened: `feature_records::CodexThreadSettingsUpdateTests::test_network_access_needs_a_read_only_or_workspace_write_sandbox` checks the whole text with `PROVIDER_DEFAULT` and `FULL_ACCESS`.
6. **`CodexBackgroundTerminal`'s `command` and `cwd`** were required in §8.5 and defaulted in §9.1. **Resolved by r4 (S2-6):** required. No test change: the tests always pass both, and a refusal row for a missing one would be a new assertion, not a tightening.
7. **Whether the ended-turn packet ends with the thread sentence.** **Resolved by r4 (S2-7):** it does. Tightened: `settings_modes::CodexTurnSettingsHostTests::test_an_ended_or_unknown_turn_is_refused_locally_and_sends_nothing` checks the summary equals the text plus "The thread id was <id>.", for the ended and the unregistered handle.
8. **Whether content search omits `archived` when it is false.** **Resolved by r4 (S2-8):** omitted. Tightened: `thread_admin::CodexTerminalSearchChildHostTests::test_search_names_every_top_level_source_and_finds_this_hosts_threads` checks that `archived` is not in the params.

## Round 3 (spec r5, `5f6c4fc4`): fixes from the S3 block

S3 built every row and was blocked on 7 tests. Two of the five fixes are §13 r5 pins and three are test defects. In each case the spec or the SDK decides, not the implementation.

1. **B-1 (§13 r5, S3-1).** `hardening_records::CodexSpawnRequestHardeningTests::test_the_new_fields_default_to_unset_and_build_with_the_sandbox_they_need`: the fields after `name` now end with `"collaboration_mode"`.
2. **B-2 (test defect).** `feature_records::CodexTurnEventRecordTests._snapshot` built a COMPLETED snapshot with no result, which the slice-1 record refuses (INV-48). It now builds one with a minimal `CodexRunResult`. The test's intent is unchanged: ENDED carries a snapshot, and no other kind does.
3. **B-3 (test defect).** `mcp_memory::CodexMemoryHostTests::test_a_paused_goal_thread_is_loaded_then_its_memory_set_then_status_and_reset_are_sent` now expects `thread/read` with `{"threadId": ..., "includeTurns": False}`, because openai-codex's `thread_read` always sends the key (`client.py:498-503`).
4. **B-4 (fixture defect).** `StubCodexHost._enter` in `codex_host_support.py` now takes its own `name` positional-only. Without that, the `rename_codex_thread` stub could not record its `name` keyword (a `TypeError` before recording), and `feature_tools` checks that keyword. This was the only clean fix: every caller passes the name positionally, and the alternatives either copy `_enter`'s gate and raise logic or drop the keyword. The 4 tool tests it blocked now pass.
5. **B-5 (§13 r5, D-40, S3-2).** `CodexMcpAuthStatus.BEARER_TOKEN` is now `BEARER`, with the value `"bearerToken"` unchanged, in `records`' `EXPECTED_ENUMS` and at `mcp_memory`'s `:83`. No other `BEARER_TOKEN` is left in the test tree. Both tests stay red until production renames the member.
