# Test plan: CodexHost production hardening (slice 1 of 2)

- **Stage:** S2 test author, pipeline `codex-host-hardening`, from `spec.md` r3 (approved).
- **Branch:** `feat/codex-host-first-class`, written on top of `24351c30`.
- **Date:** 2026-10-17.
- **Pack:** `tests/features/codex_host/`. Its `FEATURE.md` has the failure inventory these tests were chosen from, and its `README.md` has the boundary.

In the tables below, a test is written `<file>::<Class>::<test>`. `<file>` is the module name without its `test_codex_host_` prefix, so `approvals` means `tests/features/codex_host/test_codex_host_approvals.py`.

**Levels**

| Level | What runs | Where it runs |
|---|---|---|
| **R** (record) | lib records, enums, constants and errors, with no host and no SDK | CI and locally |
| **T** (tool) | `CodexHostTools` over `StubCodexHost` | CI and locally |
| **H** (host) | a real `CodexHost` over the in-memory app-server, at the spec §13 seam (`connection.CodexClient`, plus `shutil.which`). The SDK's reader thread, router, `retry_on_overload` and `CodexErrorMapper` all run for real. | locally, with the `codex` extra (openai-codex 0.163.0) |
| **C** (contract) | the installed openai-codex surface | locally, with the extra |
| **L** (live) | a real signed-in `codex app-server` | only with `VIDBYTE_CODEX_LIVE_TESTS=1` |

## Coverage map

### Acceptance criteria

| Spec ID | Test | Level | Failure caught | Why not vacuous |
|---|---|---|---|---|
| AC-1, EC-51 | `approvals::CodexApprovalSnippetTests::test_the_section_4_snippet_prints_completed_then_1`; `::test_the_snippet_handler_allows_git_status_and_declines_terminal_input` | H | The §4 snippet does not run as documented. Or a `writeStdin` approval reaches a handler that checks only `command`, and is treated as a command approval. | The snippet's `answer` and `main` are copied verbatim, with lazy imports. Its printed lines must be exactly `completed`, `1`; the one `thread/start` must carry `approvalsReviewer: "user"`; one process starts and closes. The handler accepts `git status`, but declines it typed into a terminal (`writeStdin`). Red today because `CodexHost(approval_handler=…)` is a TypeError. |
| AC-2, INV-1, INV-26 | `resilience::CodexSpawnCleanupTests::test_a_spawn_whose_turn_or_name_fails_names_the_thread_and_unregisters_its_tools` | H | #1178 regression: the error has no thread id, or the dead thread's tool registration stays. | There are two rows, a failing `turn/start` and a failing `thread/name/set`. Each checks `error.thread_id`, the `The thread id was <id>.` sentence, and a later `item/tool/call` that must get the unregistered-tool answer. Red today because the call still succeeds (`success: True`). |
| AC-3 | `resilience::CodexSpawnCleanupTests::test_a_launch_whose_third_turn_fails_stops_the_two_started_turns_and_unregisters_the_third` | H | A launch whose third turn fails loses that thread's id, leaves two turns unstopped, or keeps the third thread's tools. | The failure is scripted with a predicate on `thr-3`. The test counts one interrupt on each of the two started turns, then makes a real tool call. Red today: the tool still answers. |
| AC-4, INV-3, EC-12, EC-13 | `resilience::CodexOverloadRetryTests::test_each_idempotent_read_is_retried_after_one_overload_and_succeeds`; `::test_each_spending_or_state_changing_call_is_sent_once_and_raises_a_retryable_api_error` | H | An idempotent read is not retried, so the call fails for no reason. Or a spending call is retried, so a paid call is sent twice. | Each method's request count is read before and after the call. For the four reads the delta must be exactly 2. For the six spending calls it must be exactly 1, with `retryable is True`. The fake answers with the SDK's real `-32001 server_overloaded` shape. Red today: `account/read` raises after one attempt. |
| AC-5, INV-2, D-6 | `hardening_contract::CodexAgentErrorHardeningTests::test_retryable_is_true_exactly_for_the_five_codes_and_never_in_details` | R | `retryable` is stored, guessed, or wrong for one code. | The test walks every code in `CODEX_FAILURE_CLASSIFICATION` plus the configuration codes. It also checks that `retryable` survives `with_sentence`, cannot be assigned, and is not a key of `details`. |
| AC-6, INV-4, INV-5, D-8, EC-15 | `resilience::CodexThreadReadFailureTests::test_an_internal_or_lasting_overload_error_is_an_api_error_and_a_refusal_is_not_found`; `::test_an_exhausted_overload_is_read_three_times_and_ends_a_lineage_walk_with_an_error`; `hardening_contract::CodexHardeningClassificationTests::test_thread_read_means_not_found_only_when_refused_and_steer_refusals_are_not_found` | H, C | A `thread/read` that fails with -32603, or stays overloaded, is reported as not found. Or a lineage walk ends early and looks complete. | The H test covers 4 error kinds across 5 functions. -32600 and -32602 must still be not found. An exhausted overload must make exactly 3 attempts, and lineage must raise. The C test maps each JSON-RPC class through the real mapper. Red today: -32603 maps to `codex.session_not_found`. |
| AC-7, INV-11, INV-14, EC-17 | `liveness::CodexEventFailureTests::test_a_plain_turn_whose_completion_cannot_be_processed_fails_with_one_interrupt`; `::test_a_goal_run_whose_update_cannot_be_processed_fails_with_one_goal_cancel_and_closes_its_stream` | H | An exception in a loop callback leaves the turn running forever, and `wait_codex_turn()` with no timeout hangs. | The fault is injected at the §13 seam (`CodexResponseTranslator.turn_snapshot` or `goal_snapshot`). The wait is bounded by `WAIT_SECONDS`, so a hang fails. The test counts exactly one interrupt or goal cancel, the stream closing, and one `codex_host_turn_event_failed` WARNING with no canary in it. Red today: TimeoutError. |
| AC-8, INV-13, INV-45, EC-16, EC-18, EC-53 | `liveness::CodexLostWatcherTests::test_a_watcher_whose_read_fails_on_a_live_host_ends_the_turn_after_the_grace`; `::test_a_lost_turn_whose_cleanup_interrupt_fails_still_ends_failed`; `::test_a_process_death_ends_the_turn_as_exited_and_is_not_logged_as_a_lost_turn`; `::test_a_goal_run_that_ends_normally_sends_no_stop_and_its_wait_does_not_sit_out_the_grace` | H | A lost watcher leaves the turn running. A death is logged as a lost turn and writes after close. A normal goal end is stopped, or waits out the grace. | The grace is patched where `turn_events` reads it: 0.05 s for a loss, and 30 s for the goal end, so a wait that sat it out fails. The death test drains every watcher thread and asserts one positive `codex_host_turn_ended` record, so a silent logger cannot make "no `turn_lost`" pass. Red today: `turn_events` is missing, and the death writes no `turn_ended`. |
| AC-9, INV-12 | `liveness::CodexReviewCompletionFailureTests::test_a_review_whose_completion_read_back_raises_ends_failed_and_its_wait_returns` | H | A review whose completion read-back raises a non-Codex error never ends. | `stored_turn` returns `None` on the registration read-back and raises on the completion read-back, exactly as §13 prescribes. The wait is bounded. Red today: TimeoutError. |
| AC-10, INV-15, INV-16, D-3, EC-10 | `approvals::CodexDefaultAnswerTests::test_a_host_without_a_handler_answers_every_server_request_with_its_default`; superseded A1 `router::CodexHostRouterTests::test_the_router_answers_every_server_request_and_never_raises` | H | An approval on a host without a handler is accepted. An unknown request crashes the reader. | Every INV-15 method gets its exact answer through the real reader thread (`ask`). `currentTimeAt` is bracketed by `int(time.time())` before and after, so it must fall inside that window. `item/somethingNew/request` gets `{}`, and a later request is still answered. Red today: `{'decision': 'accept'}`. |
| AC-11, INV-17, INV-18, D-4, EC-5, EC-6 | `approvals::CodexHandlerRoutingTests::test_the_handler_sees_each_request_as_sent_and_its_answer_is_encoded`; `hardening_records::CodexServerRequestParseTests::*` (5 tests) | H, R | The handler sees altered fields, runs off the host's loop, or gets an answer encoded wrongly. Object decisions leak. Absent and null values break parsing. | The test compares the full record with `==` against a record built from the wire params, and checks that the handler's loop is the test's loop. The three encodings are compared exactly. The R tests parse the full, sparse and broken params on CI. Red today: the `approval_handler` keyword and `CodexServerRequest` are missing. |
| AC-12, INV-17, EC-4, EC-48 | `approvals::CodexHandlerFallbackTests::test_every_misbehaving_handler_gets_the_default_answer_and_one_warning`; `::test_a_request_that_cannot_be_parsed_is_declined_without_calling_the_handler` | H | A misbehaving handler kills the reader, leaves the request unanswered, or sends an answer that does not fit. | There are 10 rows, one per misfit, and each has its own fallback reason. Each must produce exactly one fallback WARNING and leave the next request answered. The handler bound is patched small through `patch_connection("CODEX_TOOL_CALL_TIMEOUT_SECONDS", 0.2)`, which fails today with AttributeError because row 12 has not imported the name yet. Parse rows log `parse_failed` and never call the handler. |
| AC-13, INV-19, D-1 | `hardening_contract::CodexHostSetupTests::*` (3); `approvals::CodexHostSetupHostTests::test_a_bad_handler_or_settings_starts_no_client_and_no_process` | R, H | A sync callable, a lambda or a non-callable is accepted, or is refused only after a process started. | `inspect` pins `approval_handler` as KEYWORD_ONLY with default `None`. The H test counts client constructions and `which` calls: both must be zero. Red today: `CodexHostSetup` and the keyword are missing. |
| AC-14, INV-20, D-5, EC-46, EC-49 | `approvals::CodexUserReviewerTests::test_without_a_handler_each_operation_refuses_a_user_reviewer_before_any_request`; `::test_with_a_handler_a_user_reviewer_starts_and_continues_and_its_approvals_reach_the_handler`; superseded A2 `records::CodexHostRecordValidationTests::test_user_reviewer_is_refused_when_any_spawn_request_is_built`; `tool_hardening::CodexToolUserReviewerTests::test_spawn_and_launch_tools_return_unsupported_combination_and_send_nothing` | H, R | A `user` reviewer is accepted without a handler, or is refused at construction, so no handler host can use it. | Each of the 7 operations is checked: its own operation, `CODEX_HOST_USER_REVIEWER_MESSAGE` with the new text, and a request count of zero. On the handler host, spawn sends `approvalsReviewer: "user"`. Red today: the record refuses at construction. |
| AC-15, EC-9 | `approvals::CodexDefaultAnswerTests::test_a_host_with_a_handler_never_routes_the_fixed_methods` | H | Permission, elicitation or legacy approvals reach the handler. | A recording handler must see zero calls, and each method gets its fixed answer. Red today: the keyword is missing. |
| AC-16, INV-22, D-10, EC-20 to EC-22 | `function_rows::CodexForgetTurnsTests::test_forget_drops_ended_turns_refuses_a_busy_thread_and_sends_nothing`; `::test_forget_works_on_a_closed_host`; superseded I1 | H | Forget drops a running turn, sends a request, unregisters tools, or keeps handles. | The test checks the returned count of 2, then 0 on a second call (EC-22). It checks the old handles and usage for not found, a busy thread for `session_busy` with its turn kept, `""` naming `forget_codex_turns thread_id`, and a request count of zero. A real tool call still succeeds afterwards. Red today: the method is missing. |
| AC-17, INV-23, EC-43 | `tool_hardening::CodexToolLocalFailureTests::test_a_runtime_or_key_error_becomes_an_api_error_result_naming_only_the_tool_and_type`; `::test_cancellation_still_propagates_and_logs_nothing` (guard) | T | A stack trace or the exception text reaches the model. Or a cancel is swallowed. | The test covers 9 tools × `RuntimeError`/`KeyError`, with exact output, metadata and "Next step:" stated once. It requires one WARNING whose origin is the innermost frame (`codex_host_support.py:_enter:`), and no canary in any record. Red today: the canary RuntimeError escapes. |
| AC-18, INV-7 to INV-10, D-12, D-13 | `observability::CodexObservabilityTests::test_a_spawn_a_failed_call_server_requests_and_a_tool_failure_log_each_event_with_its_fields`; `::test_a_handler_answer_and_a_fallback_are_logged_with_their_labels` | H | An event is missing or logged twice, has the wrong level or logger, or carries a prompt, command, email or exception text. | Every record must be %-style, with args and no `exc_info`, sit under one of the two logger prefixes, and contain no canary. Canaries are seeded in the email, env, prompt, approval command and cwd, and error text. Field values are exact. Red today: no records exist. |
| AC-19, INV-24, D-25 | `function_rows::CodexReadinessUsageTests::test_used_up_usage_is_a_problem_in_its_place`; `::test_unknown_usage_or_a_failed_usage_read_adds_no_problem` | H | Used-up usage is not reported, is out of order, or a failed read makes the host unready. | The order sign-in, usage, sandbox is pinned with all three problems present. The failed-read row requires the usage read to have happened (count +1), so skipping the read cannot pass. Red today: `ready is True`. |
| AC-20, INV-25, D-26 | `function_rows::CodexModelRefreshTests::test_a_model_added_after_the_cache_passes_after_one_walk_and_a_missing_one_fails_after_one`; `::test_a_fresh_host_walks_the_list_once_for_a_missing_model` | H | A model enabled later is refused for the life of the host. Or the refresh walks twice. | `model/list` counts are exact (one walk is 2 pages). No `thread/start` is sent after a miss. The fresh-host row is red today only through the changed next step. It then stays as a guard against a double walk. |
| AC-21, INV-27, D-20 | `function_rows::CodexContinueGoalGuardTests::test_an_unfinished_stored_goal_is_refused_after_two_reads_and_the_thread_stays_unloaded_and_free`; `::test_a_complete_goal_or_no_goal_resumes_and_starts_a_turn` | H | Continue resumes a thread with an active goal, so the goal runs as untracked turns. Or the thread's reservation is kept. | The thread's methods are exactly `["thread/read", "thread/goal/get"]`. The status stays `notLoaded`. A second continue is refused for the goal again, not as busy. Red today: the error is not raised. |
| AC-22, INV-28, D-19, D-21, EC-25, EC-54, EC-56 | `fork_review::CodexForkHardeningTests::*` (4); `hardening_contract::CodexHardeningInputRecordTests::test_fork_takes_one_fork_point_and_refuses_both`; superseded B1 | H, R | Wrong fork point. Experimental fields sent without the capability. An unknown model found only after the fork. A fork's tools left registered. | The sent params are asserted exactly (`beforeTurnId` without `lastTurnId`, `deferGoalContinuation: true`). Refusals count zero requests. The name-set failure's error carries the fork id, and a real tool call on the fork gets the unregistered answer while the parent's still works. Red today: the keywords are missing. |
| AC-23, INV-29, INV-40, EC-41 | `function_rows::CodexListingArgumentTests::test_the_host_sends_a_limit_and_refuses_a_bad_one_before_any_request`; `::test_the_one_shot_mirrors_the_limit`; `hardening_contract::CodexHardeningInputRecordTests::test_the_thread_list_limit_is_none_or_an_int_in_range` | H, R | A limit is dropped or `True` passes. The one-shot does not mirror the host. | The 4 bad values must send zero requests. `None` must send no `limit` key. Red today: TypeError. |
| AC-24, INV-6, D-23, EC-40 | `resilience::CodexSteerStoppingTests::test_a_turn_whose_interrupt_is_in_flight_is_refused_without_a_request`; `::test_a_steer_codex_refuses_as_invalid_is_not_found_and_a_malformed_one_is_a_protocol_mismatch` | H | A steer is sent into a turn being stopped. Codex's refusal maps to the wrong code. | `turn/interrupt` is held so the window is deterministic. The `turn/steer` count must stay 0. Red today: no error is raised. |
| AC-25, INV-30, D-18 | `fork_review::CodexReviewRequestTests::test_a_review_with_a_time_cap_is_interrupted_once_and_labelled_timed_out`; `::test_a_review_request_with_a_turn_is_refused_before_any_request`; `hardening_contract::CodexHardeningInputRecordTests::test_a_review_request_takes_only_time_and_token_caps` | H, R | A review cannot be capped, or takes turn settings it ignores. | The test counts exactly one interrupt and pins `codex.turn_timed_out`. `request=None` keeps today's review. The refusal text names the field. Red today: TypeError. |
| AC-26, INV-31, D-22, EC-55 | `resilience::CodexWrapperOperationTests::test_a_spawn_failure_inside_each_wrapper_is_relabelled`; `::test_a_skill_listing_failure_is_relabelled_and_starts_no_thread`; superseded G1 to G5; `hardening_contract::CodexAgentErrorHardeningTests::test_with_operation_changes_the_operation_and_message_and_keeps_the_rest`, `::test_relabel_rewrites_the_head_and_returns_an_error_already_carrying_the_operation` | H, R | A wrapper error names the inner call. Or relabelling drops a field. | `FieldCarryingMapper` finds the original error by its own operation. Every field except operation, the head and the derived `expected`/`safe_runtime_details["operation"]` must be equal. `relabel` returns the same object when the operation is unchanged. Red today: the operation is `spawn_codex_thread`. |
| AC-27, INV-32, D-30 | `function_rows::CodexListingArgumentTests::test_force_reload_is_sent_only_when_asked`; `hardening_contract::CodexHardeningInputRecordTests::test_skill_listing_takes_a_bool_force_reload`; superseded A8 | H, R | `forceReload` is always sent, or never sent. | The params lists are compared exactly. An absolute path stands in for the spec's `"C:/w"`, so the test also holds on POSIX. Red today: TypeError. |
| AC-28, INV-33 | `function_rows::CodexSkillFolderTests::test_the_skill_is_resolved_in_the_turn_folder_else_the_thread_folder` | H | The skill is resolved in the thread's folder while the turn runs elsewhere. | Both folders hold the skill, so only the `cwds` sent can tell them apart. Red today: `[['…thread-folder']]`. |
| AC-29, INV-34, D-15, EC-32, EC-33 | `turn_settings::CodexGoalRunFieldTests::test_each_turn_only_field_is_refused_before_any_request_and_thread_settings_still_start`; `hardening_records::CodexSpawnRequestHardeningTests::test_a_goal_request_refuses_each_turn_only_field_naming_the_first_one_set`, `::test_a_goal_request_with_thread_settings_and_vidbyte_caps_still_builds` (guard); `hardening_contract::CodexHardeningInputRecordTests::test_a_goal_run_request_applies_the_goal_rule_to_its_request`; superseded T1; `tool_hardening::CodexToolGoalEffortTests::*` | H, R, T | Turn-only fields are silently ignored on goal turns. | The exact `CODEX_HOST_GOAL_FIELD_MESSAGE` and `details["field"]` are checked for the first field set, with zero requests. The thread-settings goal still reaches `thread/start` with its model. Red today: the request builds. |
| AC-30, INV-35 | `turn_settings::CodexEffortWireTests::test_max_and_ultra_reach_turn_start`; `tool_hardening::CodexToolSurfaceGuardTests::test_the_spawn_and_continue_tools_offer_max_and_ultra`; `hardening_records::CodexHardeningEnumTests::test_max_and_ultra_follow_xhigh_and_forget_follows_track_usage` | H, T, R | The new efforts cannot be sent or offered. | Wire strings and enum order are exact. The schema enum must end `["max", "ultra"]` and keep the six existing efforts in order. Red today: `AttributeError: MAX`. |
| AC-31, INV-36, D-16, EC-34, EC-35 | `turn_settings::CodexServiceTierTests::*` (4); `hardening_records::CodexModelInfoTierTests::test_the_tier_fields_are_appended_with_defaults_and_validated` | H, R | Tiers are not mirrored. An unlisted tier is caught only after `thread/start`. A custom provider or tierless model is wrongly checked. | The fake model lists `fast`/`flex` (default `flex`). `warp` is refused through all three fields, with the `thread/start` count unchanged. The custom-provider and tierless rows must send `warp`. Red today: TypeError. |
| AC-32, INV-37, D-17, EC-37, EC-38 | `turn_settings::CodexSandboxAccessTests::*` (2); `hardening_records::CodexSpawnRequestHardeningTests::test_network_access_needs_a_read_only_or_workspace_write_turn_sandbox`, `::test_writable_roots_need_workspace_write_and_absolute_paths`, `::test_the_new_fields_default_to_unset_and_build_with_the_sandbox_they_need` | H, R | Network or writable roots are dropped, or accepted where Codex ignores them. | The three named keys are pinned, and every other key must be `false` (S2 report, spec defect 2). Read-only is `{"type": "readOnly", "networkAccess": true}` exactly. Fork and review refuse with zero requests. |
| AC-33, INV-38, D-18 | `fork_review::CodexReviewRequestTests::test_a_completed_inline_review_is_read_back_by_two_one_item_pages_and_never_by_full_history`; every `fork_review` test (`assert_no_full_history_read`); superseded B1, C1, C2, C3 | H | Full-history `thread/read` stays on the review or fork path. | The test needs exactly two `thread/turns/list` pages matching `is_review_read_back` (desc, full, limit 1), and no `thread/read` with `includeTurns` true. Red today: 0 pages. |
| AC-34, INV-39, D-24 | `hardening_contract::CodexHardeningPinAndDocsTests::test_the_extra_pins_openai_codex_0_163_and_the_client_reports_it`; `sdk_contract::CodexHardeningSdkContractTests::*` (4); the existing `sdk_contract::CodexHostSdkContractTests` | R, C | The pin or `client_version` is not moved. The SDK surface the host reaches has drifted. | `tomllib` reads the real `pyproject.toml`. The C tests pin `retry_on_overload` identity and its default, the wire aliases, `ModelServiceTier` fields, and `ThreadForkParams` lacking the experimental fields. Red today: `<0.163.0`, and `connection` does not bind `retry_on_overload`. |
| AC-35, FR-17, D-28, EC-45 | `live_smoke::CodexLiveGateTests::*` (2, CI); `live_smoke::CodexLiveSmokeTests::test_a_real_host_answers_the_non_spending_reads_and_sends_nothing_else` | R, L | A live run spends, or prints account data. Or the gate opens by accident. | The gate is closed for unset, `""`, `"0"`, `"true"` and `"yes"`, and skips without the CLI or the SDK. The live class spies on `CodexClient._write_message`, so a forbidden method fails by name. Its assertions read shapes only. |
| AC-36, INV-44, D-29 | `tool_hardening::CodexToolSurfaceGuardTests::test_the_toolset_holds_26_tools_and_offers_no_forbidden_parameter` (guard) | T | A tool gains a handle on the reviewer, policy, sandbox, network, roots, tier, handler, `before_turn_id`, `defer_goal_continuation`, `force_reload` or a fork `limit`. | Every tool's `input_schema` properties are read, so a new parameter anywhere is seen. It is green today and must stay green. |
| AC-37 | the whole pack plus `tests/test_codex_*.py` | all | A superseded or collateral test is left red, or `CodexHarnessAgent` regresses. | See the run commands under **Red run**. `tests/test_codex_*.py` is 269 passed today and must stay so. |
| AC-38, INV-21, EC-3 | `approvals::CodexCloseHandlerTests::test_close_cancels_a_pending_handler_and_declines_a_late_request_for_a_turn_awaiting_cleanup` | H | Close leaves a handler running. Or a late request reaches the handler. | The handler hangs on an event the test controls, and its cancellation is observed. The late request's answer is its default, with handler calls unchanged and exactly one interrupt. Close is bounded by `CLOSE_SECONDS`. |
| AC-39, FR-35, FR-36 | `hardening_contract::CodexHardeningPinAndDocsTests::test_each_documented_limitation_is_named_in_its_docstring` | R | A §3 limitation, a 0.163 deprecation or EC-1/EC-2 goes undocumented. | Keywords are checked per docstring. An empty docstring fails, as it does today for `spawn_codex_thread` (NG-20). |
| AC-40, INV-47, D-31 | `hardening_contract::CodexHardeningConstantTests::*` (4) | R | A fixed value lives in the native host, or a constant drifts from §9.2/§9.3. | Values are compared verbatim, and `__all__` is checked as sorted. An `ast` scan of `vidbyte/harnesses/native/**` finds any top-level constant. The two new modules must exist with `__all__` and no openai-codex import at module level. The C021 lint command is also run (see **Tests deliberately NOT written**). |
| AC-41, INV-48 | `function_rows::CodexNewArgumentRefusalTests::test_each_new_bad_argument_names_its_method_and_field_and_sends_nothing`; superseded I1, I2; `hardening_contract::CodexHardeningInputRecordTests::*` | H, R | A new argument reaches Codex unchecked, or the refusal does not name `"<method> <field>"`. | 6 rows, each matched against its own label and `details["field"]`, with zero requests. Red today: the method and keywords are missing. |

### Invariants and edge cases with their own tests

| Spec ID | Test | Level | Failure caught |
|---|---|---|---|
| INV-41 | `hardening_contract::CodexHardeningConstantTests::test_the_two_new_codex_modules_export_one_class_and_import_no_sdk_at_module_level` | R | `turn_events.py` or `reviews.py` imports openai-codex at load. |
| INV-7, D-13 | `hardening_contract::CodexExceptionOriginTests::test_a_raised_exception_names_its_innermost_frame_and_a_fresh_one_names_nothing` | R | The origin names the wrong frame, or carries the message. |
| §8.5 records | `hardening_records::CodexServerRecordTests::*` (2), `CodexHardeningEnumTests::test_the_three_server_request_enums_have_exactly_the_spec_members_in_order` | R | A record is not frozen or slotted, lacks a default, or accepts a bad value. An enum member is missing or out of order. |
| EC-33 | `tool_hardening::CodexToolGoalEffortTests::test_a_goal_spawn_with_an_effort_is_an_invalid_argument_naming_turn` | T | The spawn tool lets a goal run take an effort. |
| EC-32 | superseded T1 `tools::CodexHostToolArgumentTests::test_spawn_takes_the_posture_from_defaults_and_six_values_from_the_model` | T | A `spawn_defaults.turn` posture is silently dropped from a goal run. |

### Test counts

The pack gains 106 tests in 12 files: 11 new files, plus `test_codex_host_sdk_contract.py`, which was extended.

| File | Tests | Red now | Green guards | Skipped |
|---|---|---|---|---|
| `test_codex_host_hardening_records.py` | 15 | 14 | 1 | 0 |
| `test_codex_host_hardening_contract.py` | 20 | 20 | 0 | 0 |
| `test_codex_host_approvals.py` | 11 | 11 | 0 | 0 |
| `test_codex_host_resilience.py` | 10 | 10 | 0 | 0 |
| `test_codex_host_liveness.py` | 7 | 7 | 0 | 0 |
| `test_codex_host_observability.py` | 2 | 2 | 0 | 0 |
| `test_codex_host_function_rows.py` | 13 | 13 | 0 | 0 |
| `test_codex_host_fork_review.py` | 7 | 7 | 0 | 0 |
| `test_codex_host_turn_settings.py` | 8 | 8 | 0 | 0 |
| `test_codex_host_tool_hardening.py` | 6 | 4 | 2 | 0 |
| `test_codex_host_live_smoke.py` | 3 | 0 | 2 | 1 |
| `test_codex_host_sdk_contract.py` (4 new) | 4 | 1 | 3 | 0 |
| **Total** | **106** | **97** | **8** | **1** |

41 of the 106 run on CI without the extra: 39 at level R or T, and the 2 live-gate tests. The live class and the host and SDK classes are skipped there.

## Tests deliberately NOT written

- **A paid live turn (AC-1 live half, NG-13).** It spends the user's plan. AC-1 is proven at the seam, and the live module is read-only by construction.
- **EC-1, EC-2 and EC-50: a handler that calls its own host, a slow handler, and back-to-back requests.** These need a 300 s stall, or a second turn racing the SDK's single reader thread. The spec accepts them (D-2), so AC-39 checks that the `CodexHost` docstring names EC-1 and EC-2.
- **EC-14: the retry backoff running past the request bound.** This needs the SDK's real backoff sleeps. The bound itself is the existing one, and its timeout path is already pinned by the codex-host pack with the bound patched small.
- **EC-10, EC-27, EC-28, EC-36 and EC-47: Codex's or the SDK's behaviour after an accepted request.** The cases are the schema-invalid `{}` for token refresh, an unknown `before_turn_id`, a goal continuing on a fork, an unversioned CLI's runtime-field check, and a retried delete. The fake would only replay the spec's assumption. The `{}` answer itself is pinned in AC-10.
- **EC-19: `forget_codex_turns` racing a handed-over start.** The window is a few instructions wide. The AC-16 busy row proves the same `require_idle` refusal deterministically.
- **EC-29 and EC-30: a fork with used-up usage, and continue on an `idle` thread with an active goal.** Both assert that nothing new happens. The existing `test_codex_host_threads.py::CodexHostContinueTests::test_continue_reads_resumes_without_turns_then_starts_a_turn`, a §13 pin that stays green by construction, already covers EC-30's "no goal read on idle".
- **EC-31: the goal read failing during continue.** It propagates through the same `CodexConnection.call` path that AC-6 covers. A dedicated row would duplicate AC-21's request-sequence check with a scripted failure. Its reservation release is covered by AC-21's second continue.
- **EC-39: the newest stored turn is not the review turn.** The fake's `thread/turns/list` returns the stored order, so the test would replay the read-back's own filter. AC-9 covers the "watched, not completed" branch through `stored_turn` returning `None`.
- **EC-42 and EC-44: `force_reload` on a large repo, and stdlib logging when a handler raises.** These are performance and standard-library behaviour, not host behaviour.
- **AC-40's lint half.** The focused C021 lint is a command the implementer and reviewer run: `python lint/run.py --rule C021`, which must end in a PASS line. The pack scans the same rule with `ast`. On this tree, today, the full `lint/run.py` with the new tests staged ends `SDK-LINT: PASS`.
- **AC-37 as a test.** It is the run itself (see **Red run**).
- **Property-based and fuzz tests.** `hypothesis` is not a dependency. The record rules are exhaustive tables over small domains, such as the AC-12 misfit rows and the `from_params` rows.
- **Windows sandbox readiness on a real host.** The test uses `patch_platform("win32")` and the fake's `sandbox_status`, as the codex-host pack does.

## Red run

**Interpreter.** Nothing was installed. All runs used the pipeline's prepared venv, which has this worktree installed in editable mode plus openai-codex 0.163.0:

```
V=C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/bc193043-e6a6-4003-b534-2ea6e3af726a/scratchpad/venv-codex163/Scripts/python.exe
PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads -q -p no:cacheprovider
```

**Baseline before S2** (`24351c30`, same command): `1 failed, 650 passed, 2 skipped`. The one failure is the inherited `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (`assert 167 == 120`).

**After S2:** `125 failed, 631 passed, 3 skipped`, with no collection errors. The 125 failures break down as follows:

- **97 new tests**, each red for its feature's reason. The table below gives one reason per group.
- **20 superseded tests (§13).** Each is red for its new expectation.
- **7 collateral reds.** These are existing tests that compare against a support literal §13 changes (`USER_REVIEWER_TEXT` or `NEXT_STEPS`). They turn green once lib's §9.3 values change, with no test edit:
  - `test_codex_host_error_details.py::CodexErrorMessageTests::test_a_threadless_error_has_no_thread_sentence`
  - `test_codex_host_error_details.py::CodexErrorMessageTests::test_each_builder_names_its_operation_code_cause_and_next_step`
  - `test_codex_host_thread_helpers.py::CodexThreadCompactTests::test_a_not_loaded_thread_with_an_unfinished_goal_is_refused_before_any_resume`
  - `test_codex_host_threads.py::CodexHostReviewerTests::test_a_user_reviewer_reported_after_thread_start_stops_spawn_goal_and_launch`
  - `test_codex_host_threads.py::CodexHostReviewerTests::test_continue_checks_the_reviewer_resume_reports_and_an_override_fixes_it`
  - `test_codex_host_threads.py::CodexHostReviewerTests::test_the_reported_policy_decides_whether_a_user_reviewer_may_start`
  - `test_codex_host_turns.py::CodexHostSpawnTests::test_a_failed_preflight_check_stops_every_spending_operation_before_it_spends`
- **1 inherited `harness_threads` failure**, unchanged.

The count checks out: 650 − 27 = 623 previously passing tests stay green, and 623 + 8 new guards = 631 passed. The 3 skips are the 2 earlier ones plus the live class.

`PYTHONPATH=$(pwd) "$V" -m pytest tests/test_codex_*.py -q -p no:cacheprovider` → `269 passed`.

**Red reasons by group** (from `-rf` with a wide terminal):

| Group | Typical first error |
|---|---|
| handler, setup, snippet | `TypeError: CodexHost.__init__() got an unexpected keyword argument 'approval_handler'`; `ImportError: cannot import name 'CodexServerRequest'` / `'CodexHostSetup'` |
| default answers, router A1 | `AssertionError: {'decision': 'accept'} != {'decision': 'decline'}` |
| handler bound | `AttributeError: <module '…codex.connection'> does not have the attribute 'CODEX_TOOL_CALL_TIMEOUT_SECONDS'` |
| USER reviewer | `CodexAgentError: Codex spawn request approvals_reviewer=USER sends approval requests to a human…` (raised at construction) |
| spawn/launch/fork cleanup | `AssertionError: {'success': True, …} != {'success': False, …}` (tool still registered) |
| retries, retryable | `CodexAgentError: check_codex_ready failed with codex.api_error … -32001`; `AttributeError: 'CodexAgentError' object has no attribute 'retryable'` |
| thread/read classification | `AssertionError: 'codex.session_not_found' != 'codex.api_error'` |
| liveness | `TimeoutError` (the bounded wait); `AttributeError: module 'vidbyte.harnesses.native.codex' has no attribute 'turn_events'` |
| observability | `AssertionError: Lists differ: [] != [('spawn_codex_thread', 'thr-1')]` |
| wrapper operation, G1 to G5 | `AssertionError: 'spawn_codex_thread' != 'run_codex_goal'`; `'get_codex_goal' != 'run_codex_goal'`; `'list_codex_turns' != 'run_codex_skill'`; `'list_codex_skills' != 'run_codex_skill'` |
| new arguments and methods | `TypeError: … unexpected keyword argument 'before_turn_id'` / `'limit'` / `'force_reload'` / `'request'` / `'turn_service_tier'` / `'network_access'`; `AttributeError: 'CodexHost' object has no attribute 'forget_codex_turns'` |
| read-backs B1, C1 to C3, AC-33 | `AssertionError: thread/turns/list never reached the fake app-server`; `Lists differ: ['thread/read', 'thread/fork'] != ['thread/read', 'thread/turns/list', 'thread/fork']` |
| constants, pin, docs | `AttributeError: module 'vidbyte.lib.constants.codex_host' has no attribute 'CODEX_HOST_RETRIED_METHODS'`; `Lists differ: ['openai-codex>=0.162.1,<0.163.0'] != ['openai-codex>=0.163.0,<0.164.0']`; `spawn_codex_thread (NG-20) docstring names none of ('preflight',)` |
| SDK contract | `AttributeError: module 'vidbyte.harnesses.native.codex.connection' has no attribute 'retry_on_overload'` |
| tools | `RuntimeError: tool-canary-e83a` (escapes the tool); `Lists differ: ['high', 'xhigh'] != ['max', 'ultra']`; `<ToolStatus.SUCCESS> != <ToolStatus.ERROR>` |

**Green guards (8).** These pass now and must stay green:

- `tool_hardening::CodexToolSurfaceGuardTests::test_the_toolset_holds_26_tools_and_offers_no_forbidden_parameter`
- `tool_hardening::CodexToolLocalFailureTests::test_cancellation_still_propagates_and_logs_nothing`
- `live_smoke::CodexLiveGateTests::test_the_gate_is_closed_unless_the_variable_is_exactly_1`
- `live_smoke::CodexLiveGateTests::test_an_enabled_gate_still_skips_without_the_cli_or_the_sdk`
- `sdk_contract::CodexHardeningSdkContractTests::test_the_installed_sdk_is_the_pinned_0_163_release`
- `sdk_contract::CodexHardeningSdkContractTests::test_the_generated_models_carry_each_field_the_slice_sends`
- `sdk_contract::CodexHardeningSdkContractTests::test_the_fork_params_lack_the_experimental_fields_so_they_are_added_after_validation`
- `hardening_records::CodexSpawnRequestHardeningTests::test_a_goal_request_with_thread_settings_and_vidbyte_caps_still_builds`

## Notes for the implementer

- **Never edit a test (§14).** If a test looks wrong, report it, quoting its id and the spec line it binds to.
- **Start with lib.** Build the records, enums, constants (§9.2/§9.3 verbatim), `retryable`, `with_operation`, `relabel` and `ExceptionOrigin` first. That turns `hardening_records`, most of `hardening_contract` and the 7 collateral reds green on CI before any host code exists.
- **Patch seams the tests use.** Each must exist under exactly these names, or its test fails with AttributeError:
  - `vidbyte.harnesses.native.codex.turn_events.CODEX_HOST_LOST_TURN_GRACE_SECONDS`, imported by name and read at call time;
  - `vidbyte.harnesses.native.codex.connection.CODEX_TOOL_CALL_TIMEOUT_SECONDS`, imported by name and read inside the router's `handle`;
  - `vidbyte.harnesses.native.codex.connection.retry_on_overload`, which must be bound at module level and be the SDK's own object.
- **Watcher threads must be named `codex-host-watcher`.** `liveness.drain` joins threads by that name before it reads the logs. A different name makes the death test read logs early.
- **Log records are matched by the first word of the format string.** That word is the event name, as in `codex_host_turn_ended thread_id=%s turn_id=%s status=%s failure_code=%s`. Fields are read as `key=value` tokens split on spaces. Every value must be one token, so use `""` for an empty value and never a phrase. Use `logging.getLogger(__name__)` under `vidbyte.harnesses.native.codex` or `vidbyte.tools.builtins.codex`. Never pass `exc_info`, and never format the message yourself: records must be %-style with args.
- **`codex_host_turn_ended` status is the wire value** (`snapshot.status.value`), and `failure_code` is the code string. `handled_by` on a server-request record is `default`, `tool` or `handler`. A host without a handler writes no fallback WARNING (S2 report, spec defect 11).
- **The tool-failure origin is the innermost frame of the raised exception,** as `ExceptionOrigin.describe` returns it, `<file>:<function>:<line>`. Do not use the tool's own frame.
- **The SDK's `thread_read` always sends `includeTurns`, as `false` when not asked.** The tests accept `false` and refuse only `true`, so you do not need to strip the key.
- **The fake ignores `beforeTurnId` and `deferGoalContinuation`.** Add them to the dumped dict after validation (D-19). `test_codex_host_sdk_contract.py` pins that `ThreadForkParams` lacks them.
- **`experimental_api=False` refusals are local and send nothing at all.** Not even the `thread/read` of fork step 3 may follow.
- **The forget tests read handles and usage through the public API only.** `forget_codex_turns` on a closed host must still work and return the count, and it must keep the thread's dynamic-tool registration.
- **Run order:** `tests/features/codex_host/test_codex_host_sdk_contract.py` first, after the S10 bump; then the pack; then `tests/test_codex_*.py`; then the full gate.

## Orchestrator-granted corrections (S3)

The orchestrator granted these two edits on 2026-10-17, after S3 was blocked on them. Each was checked against the spec and a test run. No other test line changed.

1. **`test_codex_host_function_rows.py::CodexForgetTurnsTests::test_forget_drops_ended_turns_refuses_a_busy_thread_and_sends_nothing`** (AC-41, D-33)
   - **Before:** `self.assertEqual(caught.exception.details.get("field"), "thread_id")`
   - **After:** `self.assertTrue(str(caught.exception.details.get("field", "")).endswith("thread_id"), caught.exception.details)`
   - **Why:** D-33 makes forget reuse `CodexThreadRef`, which labels the field `"forget_codex_turns thread_id"`. This now matches I1 and `_field_named`.
2. **`test_codex_host_approvals.py::CodexCloseHandlerTests::test_close_cancels_a_pending_handler_and_declines_a_late_request_for_a_turn_awaiting_cleanup`** (AC-38, INV-15, INV-16)
   - **Before:** `self.assertEqual((self.server.closed, self.server.reader_errors), (1, []))`
   - **After:** `self.assertEqual(self.server.closed, 1)`, plus a check that every entry in `reader_errors` is the SDK's `TransportClosedError`. The check compares the type itself, not its name.
   - **Why:** close ends the process, so the SDK reader always records that end-of-file error (`codex_host_fakes.py` `reader_failed`). Any other entry still means the router raised. The `turn/interrupt` count of 1 is kept.

Run: `PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host/test_codex_host_function_rows.py tests/features/codex_host/test_codex_host_approvals.py -q -p no:cacheprovider` gives `24 passed in 2.20s`.

## S4 additions

- **Stage:** S2 test author, S4 round, from the verified review (`review.md`, `0c040d1f`) and spec r5 (`be733a0b`). Written on top of `b63c4b01`. Production code has not changed since S3's `c9150d63`.
- **What this round adds:** 22 new tests, plus 2 changed pins and 3 new constant rows.
  - **6 mutant-killing tests** (R-4, R-5, R-6, R-8). They pass today, and each fails under the mutant the old suite let live.
  - **14 red regressions** (R-3, R-9, R-10). Each fails today by an assertion, not by an error, and turns green once the repair lands.
  - **2 green guards** for R-10. They already hold and must stay green.
  - **R-7 and section D.** Two existing assertions now expect the r5 `{owner}` text. `NEW_CONSTANTS` gains the three r5 constants.
- **How the mutants were run.** Each mutant comes from `scratchpad/s4-eng/s4_mutants.py` and is applied in the module's own globals:

```
S4_MUTANT=<M> PYTHONPATH="$(pwd);<scratchpad>/s4-eng" "$V" -B -m pytest tests/features/codex_host -q -p no:cacheprovider -p s4_mutants
```

- **Mutant results.**
  - With no mutant, `tests/features/codex_host` gives `17 failed, 325 passed, 1 skipped`. The 17 are the red set below.
  - Under each mutant, the run gives exactly the 17 plus that mutant's test (M20 adds two). No other test changes.
  - Full logs are in `scratchpad/s2-s4/`.
- **Stability.** The six mutant-killing tests and the two guards passed 6 times in a row on the clean tree, in 3.9 s per run.

| Finding | Test | Kind | Proof |
|---|---|---|---|
| R-4 | `observability::CodexObservabilityTests::test_a_handler_answer_to_a_secret_question_reaches_codex_and_no_record` | mutant-kill (M40) | M40: `AssertionError: 'answer-canary-91f3' unexpectedly found in 'codex_host_server_answer item_id=item-secret answers=answer-canary-91f3'`. Clean: passes; Codex received the canary. |
| R-5 | `function_rows::CodexForgetTurnsTests::test_a_forgotten_thread_that_continues_counts_only_its_new_turn` | mutant-kill (M1) | M1: `AssertionError: 0.0033 != 0.0022 within 12 places`. The forgotten turn's 0.0011 is counted again. Clean: passes; the cost equals a fresh thread with the same usage. |
| R-6 | `resilience::CodexSpawnCleanupTests::test_a_cancelled_spawn_whose_start_codex_adopts_keeps_its_tools_for_that_turn` | mutant-kill (M31) | M31: `AssertionError: {'success': False, 'contentItems': [...]} != {'success': True, 'contentItems': [{'type': 'inputText', 'text': 'echo: hi'}]}`. Clean: passes, with one interrupt on the adopted turn. |
| R-8 (a) | `liveness::CodexLostWatcherTests::test_a_lost_turn_whose_stop_was_already_sent_gets_no_second_interrupt` | mutant-kill (M2) | M2: `AssertionError: 2 != 1` (`test_codex_host_liveness.py:217`). Clean: passes. |
| R-8 (b) | `liveness::CodexLostWatcherTests::test_the_cleanup_interrupt_of_a_lost_turn_waits_out_the_grace` | mutant-kill (M20) | M20: `AssertionError: 0.0 not greater than or equal to 0.30000000000000004`. Clean: passes, with the grace patched to 0.4 s. |
| R-8 (c) | `liveness::CodexLostWatcherTests::test_a_close_that_starts_inside_the_grace_wins_and_the_lost_turn_sends_nothing` | mutant-kill (M21, and M20) | M21: `AssertionError: 2 != 1` (the interrupts sent while close was held, past the grace). M20 fails this test too, with `2 != 1`. Clean: passes. |
| R-3 | `liveness::CodexReviewCompletionFailureTests::test_a_review_read_back_as_ended_whose_snapshot_cannot_be_built_ends_failed_through_the_failure_path` | red-regression | `AssertionError: start_codex_review raised RuntimeError instead of returning the review's handle` |
| R-3 | `liveness::CodexReviewCompletionFailureTests::test_a_late_review_read_back_as_ended_whose_snapshot_cannot_be_built_ends_failed` | red-regression | `AssertionError: the unbounded wait on turn turn-2 was still pending after 10.0 seconds` |
| R-9 | `observability::CodexLogTokenRecordTests::test_hostile_ids_from_codex_log_as_one_token_in_each_record` | red-regression | `AssertionError: Lists differ: [..., 'thread_id', 'handled_by', '%s', 'answer', 'duration_ms'] != [..., 'thread_id', 'duration_ms']`. The `turn/start` record is split by the hostile thread id. |
| R-9 | `observability::CodexLogTokenRecordTests::test_a_hostile_id_in_a_fallback_or_passed_by_a_caller_logs_as_one_token` | red-regression | `AssertionError: Lists differ: [..., 'handled_by', '%s', 'answer', 'reason', ...] != [..., 'reason', 'error_type', 'origin']` (the fallback WARNING) |
| R-9 | `observability::CodexLogTokenRecordTests::test_hostile_handle_ids_log_as_one_token_when_a_turn_event_fails` | red-regression | `AssertionError: '\n' unexpectedly found in 'codex_host_call operation=spawn_codex_thread method=turn/start thread_id=thr-2\r\nthread_id=forged turn_id=forged duration_ms=0'` |
| R-9 | `observability::CodexLogTokenRecordTests::test_hostile_handle_ids_log_as_one_token_when_a_watcher_is_lost` | red-regression | the same line as the row above |
| R-9 | `hardening_contract::CodexLogTokenTests::*` (6 tests, CI-visible) | red-regression | `AssertionError: False is not true : spec r5 row 25 adds the LogToken class to vidbyte.lib.util.text` |
| R-10 | `observability::CodexCallRecordTests::test_a_call_cancelled_after_it_was_sent_writes_one_record_once_its_worker_returns` | red-regression | `AssertionError: Lists differ: [] != [('codex_host_call', 10)]` (its success row; its failure row expects the WARNING) |
| R-10 | `observability::CodexCallRecordTests::test_a_spending_start_handed_over_on_cancel_writes_one_record_for_its_late_outcome` | red-regression | `AssertionError: Lists differ: [] != [('codex_host_call', 10)]` |
| R-10 | `observability::CodexCallRecordTests::test_a_call_whose_bound_ran_out_writes_one_record_even_after_its_worker_returns` | green guard | Passes today. A second record from the late outcome would fail it ("exactly one", not two). |
| R-10, EC-57 | `observability::CodexCallRecordTests::test_a_call_refused_before_it_was_sent_writes_no_record` | green guard | Passes today. It has four rows: a queued call withdrawn, the call guard on another loop, the dead check, and the call guard of a closed host. |
| R-7 | `hardening_contract::CodexHardeningInputRecordTests::test_a_goal_run_request_applies_the_goal_rule_to_its_request`; `turn_settings::CodexGoalRunFieldTests::test_each_turn_only_field_is_refused_before_any_request_and_thread_settings_still_start` | red pin (changed assertion) | `AssertionError: "Codex spawn request goal does not use the[138 chars]ing." != "run_codex_goal request does not use the f[136 chars]ing."` |
| R-2, R-9, R-7 (section D) | `hardening_contract::CodexHardeningConstantTests::test_every_new_constant_holds_its_spec_value_and_is_exported_in_order` | red literal | `AssertionError: 'CODEX_HOST_FORK_EXPERIMENTAL_FIELDS' not found in [...]`. Its other subtests fail on `CODEX_HOST_LOG_TOKEN_MAX_CHARS`, `CODEX_HOST_ANY_MODEL_TEXT` and the `{owner}` value of `CODEX_HOST_GOAL_FIELD_MESSAGE`. |

**How the tests are built**

- **Barrier, not sleep (R-10).** `CodexCallRecordTests` opens its host with `CODEX_HOST_WORKER_THREADS` patched to 1. A later call that returns therefore proves that every earlier worker has returned and run its done-callbacks. The records are read after that call, never after a sleep.
- **Owned, not polled (R-3, late path).** The late-path review is registered before it is read back. So the arrival of its read-back request (`is_review_read_back`) is the sign that the host owns it.
- **Literal tokens (R-9).** The hostile ids are named through the new `FakeAppServer.name_next(thread_suffix=..., turn_suffix=...)`, so the ids from Codex keep the fake's `thr-` and `turn-` prefixes. Every expected token is a literal worked out by hand from the two `LogToken.of` rules. A regex was used once, while writing the tests, to check them; it is not in the tests.
- **Every R-9 record is checked twice.**
  - Its whole shape: one line, with exactly its event's keys in order (`EVENT_KEYS`).
  - Its values: the token in each field that INV-10 names.
- **Errors become assertion failures (R-3).** What escapes `start_codex_review`, a wait still pending at its bound, and a refused next review are each converted to a test failure.
- **Missing names fail as assertions.** The `LogToken` unit rows check `hasattr` first. `CodexHardeningConstantTests` now checks the export before it reads the attribute.
- **Negative checks bounded by time (R-8).**
  - The close-inside-the-grace row sleeps until 2.5 graces after the read failed, then counts the interrupts sent meanwhile.
  - The grace-gap row keeps a quarter of the 0.4 s grace in hand for the coarse Windows clock.
- **What the owner pins say (R-7).** `GOAL_FIELD_MESSAGE` is now the r5 template, with `GOAL_SPAWN_OWNER` and `GOAL_RUN_OWNER` beside it in `codex_host_support.py`. The `CodexSpawnRequest` rows (`hardening_records`, `tools` T1, `tool_hardening`) pass `GOAL_SPAWN_OWNER` and stay green. The two `run_codex_goal` rows pass `GOAL_RUN_OWNER`, and the contract row also pins r5's whole text for `turn`.
- **Export pins (section D).** No `__all__` pin for `vidbyte.lib.util.text` existed. The new `CodexLogTokenTests` pins three things:
  - row 25's order: `["TOKEN_ESTIMATE_CHARS_PER_TOKEN", "LogToken", "SubstringCounter", "TokenEstimate"]`;
  - row 10's re-export from `vidbyte.lib.util`;
  - that the `vidbyte.lib.util` `__all__` stays sorted.

  `RECORD_EXPORTS` does not change in r5, so it is untouched.

**The red set after this round (17 in `tests/features/codex_host`, plus the inherited `harness_threads` failure):**

- R-3: the 2 liveness rows.
- R-9: the 4 `CodexLogTokenRecordTests` rows and the 6 `CodexLogTokenTests` rows.
- R-10: the 2 red `CodexCallRecordTests` rows.
- R-7: the 2 goal-run pins.
- Section D: `CodexHardeningConstantTests::test_every_new_constant_holds_its_spec_value_and_is_exported_in_order`.

**Runs**

| Run | Before (`b63c4b01`) | After |
|---|---|---|
| `tests/features/codex_host` | `320 passed, 1 skipped` | `17 failed, 325 passed, 1 skipped` |
| `tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py` | `1 failed, 1024 passed, 3 skipped` | `18 failed, 1029 passed, 3 skipped` |

- The count checks out. 1025 tests ran before, and 22 are new, so 1047 run now.
  - **Failed:** 18 = 1 inherited + 14 new red + 3 existing tests turned red (the 2 R-7 pins and the constants row).
  - **Passed:** 1029 = 1024 − 3 + 6 mutant-killing + 2 guards.
- `lint/run.py` ends `SDK-LINT: PASS`.
- `ruff check` on the edited files adds no finding.

**For the repair agent.** Never edit these tests.
- **R-9:** route each value through `LogToken.of(value, CODEX_HOST_LOG_TOKEN_MAX_CHARS)` at the logging call only. The tests read `handle.thread_id` back raw, and they route and answer on the raw ids.
- **R-10:** the cancelled-call record must be written by the time the next call on the same single worker returns. The spec says the worker's done-callback writes it, before any post to the loop, and that satisfies this.
- **R-3:** the tests do not name the renamed `fail`. They read only the outcome:
  - `failed` / `codex.protocol_mismatch` with `CODEX_HOST_EVENT_FAILED_MESSAGE`;
  - one `codex_host_turn_event_failed` WARNING with `error_type=RuntimeError`;
  - at most one interrupt;
  - and the thread taking the next review.
