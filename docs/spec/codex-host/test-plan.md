# Test plan: CodexHost, small atomic Codex functions with one agent tool per function

Spec: `docs/spec/codex-host/spec.md` r3 · Framework: pytest 8.3.5 with pytest-asyncio 1.3.0, written as unittest classes (`TestCase`, `IsolatedAsyncioTestCase`) like the rest of `tests/` · Prior art copied: `tests/test_codex_tools.py` (a fake openai-codex client, and the `skipUnless(find_spec("openai_codex"))` gate), `tests/features/coding_agent/` (pack layout: README.md, FEATURE.md, a support module, no `__init__.py`), `tests/test_mcp_studio_server.py` (in-process `McpStudioServer._dispatch`)

The pack is `tests/features/codex_host/`. It has 101 tests in 11 modules, plus `codex_host_support.py`, `codex_host_fakes.py`, `README.md` and `FEATURE.md`.

**File keys.** `records` stands for `tests/features/codex_host/test_codex_host_records.py`. The same pattern holds for `packaging`, `bridge`, `tools`, `lifecycle`, `turns`, `threads`, `review_goals`, `failures`, `router` and `sdk_contract`.

**Levels:**

| Level | What runs |
|---|---|
| unit | Records, constants and enums, the bridge, or the fifteen tools over `StubCodexHost`. No host runs. |
| integration | A real `CodexHost` and the real openai-codex `CodexClient` over the in-memory app-server at the §13 seam. The client's reader thread, router, retry helper and goal routing all run. |
| packaging | A fresh `python -I` child process, or the committed files' bytes. |
| contract | The installed openai-codex package itself. |

"gated" marks a test that needs the `codex` extra, so CI skips it.

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | lifecycle → `test_the_section_4_snippet_prints_its_three_lines`. The live half is manual QA (NG-13). | integration, gated | The §4 snippet runs against a fake that finishes the turn at once. Wrong output: readiness prints False (the account is misread), the bounded wait returns RUNNING, or the toolset's first name is not `check_codex_ready`. | It compares the exact list of printed lines, so a snippet that prints nothing fails. |
| AC-2 | packaging → `test_imports_never_load_the_sdk_and_entering_reports_the_pip_extra` (CI); `test_imports_leave_an_installed_sdk_unloaded` (gated) | packaging | A module-level `import openai_codex` in the new packages or the toolset makes the child's import fail, or leaves an `openai_codex*` module loaded. A host that resolves the binary before it loads the SDK reports the CLI next step instead of `pip install "vidbyte-sdk[codex]"`. | In the blocked child, `loaded` is always empty. That test therefore relies on two things: a non-zero exit of the child fails it, and it checks the exact code and next step. `which` is also None there, so the next step tells the two failures apart. The gated twin runs with the SDK installed, where `loaded == []` is a real check. |
| AC-3 | lifecycle → `test_a_missing_codex_binary_is_not_installed_and_starts_nothing`, `test_the_resolved_path_is_launched_and_a_launch_override_skips_resolution`, `test_a_process_that_cannot_start_is_not_installed_naming_the_path` | integration, gated | Wrong outputs: when `which` returns None (default or custom name), the client starts anyway, or the message lacks the name. The resolved path is not passed as `codex_bin`. `launch_args_override` still calls `which`. A FileNotFoundError or PermissionError at start escapes raw. | `which` is a recorder, so "not consulted" is an empty call list. `server.started` counts real `start()` calls on the client at the seam. |
| AC-4 | lifecycle → `test_versions_below_the_minimum_or_unparseable_are_refused_and_the_client_closed` | integration, gated | `initialize` reports `0.150.9`, `0.0.0`, an empty version or `garbage`. Wrong outputs: the host opens, the message lacks the found or minimum version, or the client is left running. | Each refusal must close the client exactly once. `0.151.0`, `0.162.1` and a version taken from the user agent must open and read back through `check_codex_ready().version`, so a gate that refuses everything fails too. |
| AC-5 | turns → `test_spawn_sends_the_section_9_2_params_and_returns_while_the_turn_runs` | integration, gated | A spawn with model, effort, a read-only sandbox, developer instructions, name, plugin ids and a schema. Wrong outputs: a missing or renamed wire field; approval defaults other than `on-request` plus `auto_review`; a `config.agents` key; `thread/name/set` after `turn/start`; or a handle that comes back only after the turn ends. | The fake logs every request in order. It completes nothing unless the test tells it to, so the turn is still `inProgress` there when the handle returns. |
| AC-6 | turns → `test_a_failed_preflight_check_stops_every_spending_operation_before_it_spends`, `test_preflight_passes_on_unknown_states_and_skips_checks_that_do_not_apply` | integration, gated | One check fails at a time: no account, ordinary usage False, a win32 sandbox that is `notConfigured`, or an unknown model. Spawn, continue, review or launch then sends a spending request, or raises the wrong code. A `model_unknown` message omits the listed ids. The twin catches a preflight that blocks on states D-28 says must pass: allowance None, a rate-limit read failing -32603, no sandbox method, a full-access sandbox, a custom provider, hidden or later-page models, or a cursor that repeats. | Each of the 15 operation-by-check pairs compares the spending-request count before and after. Review skips only the model check, as §9.2 says. The pass twin means "always refuse" cannot pass. |
| AC-7 | turns → `test_a_bounded_wait_returns_running_and_never_touches_the_turn` | integration, gated | A wait bounded at 0.05 s sends an interrupt, returns a terminal snapshot, or hangs. A cancelled wait interrupts the turn. A timeout of 0, -1 or NaN is accepted. | "No interrupt" is read after the one-worker barrier: with `CODEX_HOST_WORKER_THREADS` patched to 1, a later `read_codex_thread` cannot return before an interrupt queued earlier was sent. The turn is then completed and waited to COMPLETED. |
| AC-8 | turns → `test_a_completed_turn_reports_its_answer_and_usage_and_get_never_waits` | integration, gated | A completed turn with an answer and usage. Wrong outputs: no `final_response`; the last delta given as usage instead of the thread totals; a get that waits on a running turn. | The cumulative values (250, 45) differ from the last-turn values (150, 25). The get on a running turn is bounded at 1 s. |
| AC-9 | turns → `test_a_timeout_sends_one_interrupt_and_labels_only_a_turn_codex_reports_interrupted` | integration, gated | A turn timeout of 0.2 s sends zero or two interrupts, or leaves the snapshot without INTERRUPTED and `turn_timed_out`. A failed interrupt is retried, or labels a turn that Codex then completes. | Counts are read after the barrier. The second half fails the interrupt and requires COMPLETED with no problem. |
| AC-10 | turns → `test_the_output_cap_counts_only_the_turns_own_tokens_and_interrupts_once` | integration, gated | A cap of 50 on a thread whose earlier turn produced 90 output tokens. Wrong outputs: an interrupt right away (thread totals counted); an interrupt at exactly 50; a second interrupt after more usage; or tokens after the crossing dropped from usage. | The boundary turn reaches exactly 50 and must see no interrupt. The crossing turn gets more usage after its interrupt and must still show one. The per-turn outputs `[90, 50, 130]` pin the arithmetic. |
| AC-11 | turns → `test_process_death_fails_the_running_turn_and_later_calls_without_leaking_stderr`, `test_a_non_json_stdout_line_kills_the_host_without_leaking_the_line` | integration, gated | The transport dies with stderr text, or a stdout line is not JSON. Wrong outputs: the wait hangs; the snapshot is not FAILED with `process_exited`; later calls send requests or write after close; or a message carries the stderr or line canary. | A precondition waits until the real SDK reader's own error carries the canary, so its absence from the host's texts means the host removed it. The texts include each error's visible exception chain. |
| AC-12 | turns → `test_a_failed_turn_maps_each_codex_error_info_to_its_code` | integration, gated | A failed turn with a §9.2 `codexErrorInfo` (string or object variant), or an unknown value, maps to the wrong code or loses Codex's message. | Every table row runs as a subTest, and the unknown value must map to `api_error`. |
| AC-13 | turns → `test_structured_output_is_validated_and_a_missing_answer_is_invalid` | integration, gated | With an output schema, a valid, wrongly shaped, non-JSON or missing answer gives the wrong outcome: `structured` unset, a bad answer marked FAILED, the raw text dropped, or a missing answer reported COMPLETED. | Each case compares the exact status, code and `structured` value. |
| AC-14 | threads → `test_continue_reads_resumes_without_turns_then_starts_a_turn`, `test_continue_and_review_refuse_a_busy_or_unknown_thread`, `test_two_concurrent_continues_on_one_idle_thread_start_one_turn`, `test_fields_an_operation_cannot_apply_are_rejected_before_any_request` | integration, gated | Wrong outputs from continue: the read, resume and turn/start order is broken; resume lacks `excludeTurns` or carries approval fields. A busy thread gets any request. An unknown thread reaches resume. Two concurrent continues both start turns. Overrides with tools, goal or name are dropped or sent. | Request counts are compared before and after each refusal, and the method list is checked per thread. The concurrent case gathers two real calls and needs exactly one `session_busy`. |
| AC-15 | threads → `test_fork_reads_the_turns_first_and_forks_through_a_completed_turn`, `test_fork_maps_codex_refusals_and_unknown_threads` | integration, gated | Wrong outputs: the wrong `lastTurnId`, a missing `excludeTurns`, or no read first. An empty `from_turn_id` while a turn runs forks through the running turn. No completed turn, an unknown turn or an in-progress turn reaches `thread/fork`. -32600 or -32602 is not mapped to `fork_failed`. | Each refusal compares the `thread/fork` count before and after. A fork without `exclude_turns` must omit `excludeTurns`. |
| AC-16 | turns → `test_steer_and_interrupt_act_only_on_a_running_turn_this_host_returned` | integration, gated | Wrong outputs: steer lacks `expectedTurnId` or returns a new handle. Interrupt sends twice or labels the turn. Steer on a finished turn succeeds, or interrupt on one sends. A foreign handle is accepted by wait, get, steer or interrupt. | The request count stays unchanged across every refusal. |
| AC-17 | turns → `test_usage_tracking_lists_terminal_turns_with_their_own_deltas_and_rollup_cost` | integration, gated | Two completed turns and one running. Wrong outputs: the running turn is listed; cumulative values appear instead of per-turn deltas; the cost is computed by hand instead of by the repo rollup; a custom provider gets a cost; `cost_complete` is true when a turn reported no usage; an unknown thread is accepted. | The expected cost comes from the repo's own pricing classes (D-19) and must be above 0. The deltas differ from the cumulative values. |
| AC-18 | threads → `test_launch_starts_one_thread_per_prompt_in_order_after_one_preflight`, `test_a_launch_that_fails_midway_interrupts_each_turn_it_started_once`, plus the limit and prompt/goal cases of `test_fields_an_operation_cannot_apply_are_rejected_before_any_request` | integration, gated | Three prompts give starts out of order, shared threads, a preflight per prompt, or a name missing from a thread. When the third start fails: the started turns are not interrupted, are interrupted twice, or the error does not say 2. `limit=2` with three prompts sends anything. | The interrupt set is compared after the barrier, and the `account/read` delta must be exactly 1. |
| AC-19 | review_goals → `test_a_review_is_sent_once_with_its_target_and_tracked_to_completion`, `test_a_review_turn_that_finished_before_registration_is_read_back`, `test_a_review_whose_final_item_was_dropped_is_completed_from_the_completion_read_back`, `test_a_detached_review_is_tracked_on_the_new_review_thread` | integration, gated | A COMMIT target gives the wrong target JSON, a model check, or a retry after an overloaded answer. A review whose events landed before registration never ends. A dropped final item leaves `final_response` empty. A detached review is tracked on the parent thread. | The fake writes the events before its `review/start` answer, so the real router drops them. The dropped-item case holds the registration read-back until it has seen the turn running. |
| AC-20 | review_goals → `test_a_goal_spawn_starts_goal_mode_then_sets_the_budget_once`, `test_a_failed_budget_set_cleans_up_in_openai_codex_start_failure_order`, `test_a_finished_goal_run_maps_the_goal_table_and_closes_its_stream`, `test_a_goal_update_after_the_last_completion_finishes_the_run`, `test_a_runtime_that_never_activates_goal_mode_fails_the_run`; records → `test_each_invalid_record_raises_configuration_error_naming_the_field` (goal plus an ephemeral thread) | integration, gated (+ unit) | A goal with a budget sends a `turn/start`, sets the budget before goal start, or sends the budget twice or without a budget. On an echo mismatch or a failed budget request: the wrong code, cleanup out of order, a started watcher, or a thread left busy. The goal table is mapped wrongly; a stream is left open; a completion while the goal is active is taken as final. | Cleanup order is read per thread from the fake client's call log: `cancel_goal_operation`, `finish`, `unregister_goal_operation`. Watchers are joined and must be dead. Limit: the update-after-completion case expects RUNNING from a 0.2 s wait. A host slower than that could let a wrong rule pass, but a right rule never fails. |
| AC-21 | threads → `test_list_sends_every_set_argument_and_omits_the_empty_ones`, `test_read_returns_turn_summaries_only_when_asked` | integration, gated | A list with every argument has a missing or renamed param, sends `archived` when False, or loses `next_cursor`. Turn summaries are missing fields or appear unasked. An unknown id is not `session_not_found`. | The test compares exact param dicts, and translates field by field against the fake's stored threads. |
| AC-22 | threads → `test_readiness_reports_account_and_sandbox_without_the_email`, `test_rate_limits_and_models_are_translated_across_pages` | integration, gated | Readiness carries the email, ignores the win32 sandbox, or raises problems instead of reporting them. A None allowance turns into False. Only the first model page is read, or hidden models are listed by default. | The fake account's email is a unique canary. The two pages carry distinct ids. |
| AC-23 | tools → `test_toolset_holds_the_fifteen_tools_with_their_spec_schemas`, `test_default_policy_allows_the_read_tools_and_denies_the_write_tools` | unit | A tool has the wrong order, name, class, permission, parameters or required list. A WRITE tool is allowed by default, or reaches the host. | The expected table is the spec's 15 rows. Every tool runs through the real `ToolExecutor` and `PermissionPolicy`. |
| AC-24 | tools → `test_every_tool_turns_host_errors_into_error_results`, `test_cancellation_propagates_and_frees_the_reserved_slot` | unit | A host `CodexAgentError`, `ConfigurationError` or `ToolExecutionError` escapes `execute`, or comes back without the `<code>: <message> Next step: <next_step>` form or its metadata. Cancellation is swallowed, or keeps its slot. | All 45 tool-and-error pairs compare exact output strings. A spawn after the cancellation proves the slot is free. |
| AC-25 | tools → `test_cap_refuses_turn_starting_tools_without_reaching_the_host`, `test_launch_counts_every_new_turn_against_the_cap`, `test_two_concurrent_spawns_never_exceed_the_cap`, `test_a_failed_start_releases_its_slot`, `test_handle_tools_accept_only_their_own_scope_while_thread_tools_accept_any_thread` | unit | With the cap full: spawn, continue, launch or review reaches the host. A launch counts as one turn. Two concurrent spawns both reserve. A failed start keeps its slot. A foreign handle is accepted, or a thread tool refuses another scope's thread. | The stub logs every call, so "never reached" means an empty log. The concurrent case holds the first spawn inside the host while the second runs. |
| AC-26 | tools → `test_spawn_takes_the_posture_from_defaults_and_six_values_from_the_model`, `test_spawn_needs_exactly_one_of_prompt_and_goal_objective`, `test_continue_fork_and_launch_carry_only_what_their_operation_applies` | unit | A model value overrides the sandbox, approvals, cwd, tools or developer instructions. JSON null replaces a default. Both, or neither, of prompt and `goal_objective` is accepted. | The request the stub receives is compared whole with `dataclasses.replace(defaults, …)`. |
| AC-27 | tools → `test_mcp_server_lists_and_runs_the_toolset` | unit | `McpStudioServer(tools=CodexHostTools(...))` does not list the 15 tools, a READ call does not reach the host, or the cap does not apply over MCP. | The stub logs exactly one `check_codex_ready`, and the second spawn must be refused with `session_busy`. |
| AC-28 | `tests/test_codex_tools.py`, unchanged and passing; bridge → `test_validate_names_raises_the_two_existing_messages`, `test_handler_runs_tools_under_the_bridge_policy_and_falls_back_otherwise` | unit | Extracting `validate_names` and `handler` changes the messages from `translate` or the `attach` fallback, or the handler no longer falls back to the SDK approval handler. | The bridge tests compare the existing messages verbatim. The existing suite is untouched (NG-5) and passes. |
| AC-29 | records → `test_new_failure_codes_sit_right_after_run_option_unsupported`, `test_each_new_code_has_its_classification_row_and_next_step`, `test_section_9_3_constants_hold_their_spec_values` | unit | A new code is misplaced or misvalued, an existing code changes, a classification row or `CODEX_NEXT_STEPS` entry is missing, or a §9.3 constant drifts from its spec value. | The whole `FailureCode` list of (name, value) pairs is compared, so a change to an old member fails as well. |
| AC-30 | router → `test_the_router_answers_every_server_request_and_never_raises` | integration, gated | A registered tool does not run. An unregistered thread raises, or gets the wrong text. Approvals are not accepted, or an unknown method does not get `{}`. A handler that raises kills the reader thread. | The real SDK reader thread gives every answer. The test ends with another host call, which needs that reader alive. |
| AC-31 | lifecycle → `test_each_module_function_opens_and_closes_one_host_whether_it_succeeds_or_fails`, `test_module_check_codex_ready_reports_a_missing_binary_instead_of_raising` | integration, gated | A module function leaks its host on failure or opens twice. The module `check_codex_ready` raises instead of reporting. | The started and closed deltas must be exactly (1, 1) for every call, on success and on failure. |
| AC-32 | failures → `test_a_spawn_cancelled_while_turn_start_is_in_flight_owns_the_turn`, `test_a_spawn_whose_start_outlives_the_request_bound_gets_api_error_and_the_turn_is_owned`, `test_a_review_cancelled_in_flight_is_interrupted_once_and_read_back`, `test_a_start_still_queued_behind_a_blocked_worker_is_never_sent`, `test_a_start_that_returns_after_close_began_is_registered_failed_and_sends_nothing` | integration, gated | A start cancelled or timed out leaves a late turn that is never interrupted (a paid orphan), is interrupted twice, or is not registered. A late review is not read back. A queued start is still sent after its cancel. A start answered during close is interrupted, or written after close. | Holds on the fake keep the start unanswered at the exact moment, and counts are read after the barrier. Limit: the queued-start case cannot see the executor queue. If the spawn had not queued its `turn/start` before the cancel, the test passes without exercising the withdrawal. It never fails falsely. |
| AC-33 | lifecycle → `test_a_host_answers_only_while_open_and_opens_at_most_once`, `test_a_closed_host_answers_local_reads_and_refuses_calls_that_talk_to_codex`, `test_a_call_from_another_event_loop_is_refused`, `test_close_interrupts_a_running_turn_once_then_closes_on_a_daemon_thread`, `test_close_cancels_a_running_tool_call_before_sending_interrupts`, `test_close_ends_a_goal_run_in_openai_codex_order_and_its_watcher_exits` | integration, gated | A call before open, or from another loop, reaches Codex. A second enter, even a concurrent one, opens another process. A closed host sends requests. The turn running at close is not FAILED, or is interrupted twice or after close. A running tool call holds close. The goal cleanup runs out of order, or a watcher is stranded. | The tool-call case sets the close-interrupt bound to 60 s, so the wrong order runs into the test's own bound instead of passing. The fake's log is ordered and per thread. |
| AC-34 | failures → `test_no_error_record_or_tool_output_carries_a_private_value`; turns → the two AC-11 tests; threads → `test_readiness_reports_account_and_sandbox_without_the_email` | integration, gated | An email, env secret, stderr or raw-line canary appears in some error text (message, repr, details, next step, visible chain), record repr or tool output. | The canaries are unique strings planted where Codex would put them. Preconditions prove that the SDK's own texts carry them, and that the env value reached the fake's config. |
| AC-35 | records → `test_valid_baselines_construct_frozen_slotted_records`, `test_each_invalid_record_raises_configuration_error_naming_the_field`, `test_user_reviewer_is_refused_when_any_spawn_request_is_built`, `test_review_target_fields_follow_their_kind_exhaustively`, `test_snapshot_status_result_and_problem_rule_exhaustively` | unit (CI) | An invalid record constructs, or its error does not name the field. A USER reviewer is accepted, or raises the wrong type, code, operation or next step. | The valid baselines must construct first. Each invalid case changes one field from a baseline. The kind-by-field and status-by-result-by-problem grids are exhaustive. |
| AC-36 | packaging → `test_native_package_marker_has_the_fixed_bytes`, `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores`, `test_harnesses_readme_bullet_follows_the_serialization_bullet`, `test_new_packages_export_exactly_their_spec_lists`, `test_existing_export_lists_gain_only_the_new_names_in_place`. The gate covers the rest (S3–S5). | packaging (CI) | The marker's bytes differ from request.md's SHA-256. The REPO_MAP section or README bullet is misplaced or reworded. An export list is missing a name or reordered. | The marker check hashes the working copy with CRLF folded to LF, so it is safe under autocrlf. The §11 git-blob command in the gate stays the authority. |
| AC-37 | threads → `test_a_user_reviewer_reported_after_thread_start_stops_spawn_goal_and_launch`, `test_the_reported_policy_decides_whether_a_user_reviewer_may_start`, `test_continue_checks_the_reviewer_resume_reports_and_an_override_fixes_it` | integration, gated | Codex reports a `user` reviewer with `on-request` or a granular policy. Wrong outputs: `thread/name/set`, `turn/start` or a goal request is sent; the wrong code; no thread id; the wrong next step. `never`, or `auto_review`, is blocked. The override is not sent on resume. | The fake's default reviewer is set to `user`, as an interactive install's can be, so the check must act on what Codex reports and not on what the host sent. |
| D-29 | threads → `test_a_fork_answers_tool_calls_with_its_parent_threads_tools` | integration, gated | Forking a thread that has dynamic tools leaves the fork without a handler, so Codex's tool call on the fork gets the unregistered-tool text. | The call goes through the real router with the fork's thread id and must return the echo output. The tool's own call log must show exactly that one call. |
| INV-29, D-18, EC-49, T-8 | threads → `test_dynamic_tools_need_the_experimental_api_and_valid_names_before_any_request`, `test_dynamic_tools_are_registered_on_thread_start_and_answer_codex` | integration, gated | Tools are sent without the experimental API or with invalid names. A tool call runs outside `ToolExecutor`, or its output never reaches Codex. | The request count must stay unchanged on a refusal. The output text is compared exactly. |
| INV-30, D-17 | threads → `test_the_agents_config_is_written_only_when_subagents_are_set` | integration, gated | An empty `config` is sent, the caller's own config is altered, or the agents section differs from what the existing `CodexContentTranslator` builds. | Three spawns compare `config` exactly: absent, the caller's dict as given, and the translator's agents section. |
| §8.5 and §9.1 enums | records → `test_new_enums_have_exactly_the_spec_members_and_values` (CI), `test_wire_values_match_openai_codex` (gated) | unit, contract | A new enum gains, loses or renames a member, is not a str enum, or carries a wire value that openai-codex does not accept. | Member maps are compared whole. The gated twin checks the values against the installed SDK's own types. |
| INV-35 | tools → `test_outputs_are_the_returned_records_as_json` | unit | A tool output is not the record's JSON (enum values, nested records), or wait and get leak `result.items`. | It compares whole JSON documents. |
| EC-57, D-11, INV-32 | tools → `test_bad_caps_and_defaults_are_refused_at_construction` | unit | A missing, zero, negative, boolean, float or string cap is accepted, or `spawn_defaults` carries a prompt or a goal. | Each bad value is tried on both `CodexHostTools` and `CodexToolScope`. |
| INV-25, §12.3 row 13, D-32, D-1 | sdk_contract → `test_the_connection_binds_the_client_seam_and_every_call_it_makes_still_fits`, `test_the_private_goal_cursor_and_goal_state_still_offer_the_hooks_the_host_calls`, `test_thread_start_and_resume_responses_still_require_the_reviewer_and_policy` | contract, gated | An openai-codex upgrade renames a method or parameter the host calls, changes `_GoalStreamCursor.process`, `finish` or `wake_notification_reader`, or makes the reviewer optional. The fakes would keep passing while the real host broke. | The test reads the installed SDK's real signatures and models, not the fakes. |
| INV-1, D-1, INV-7 | lifecycle → `test_close_interrupts_a_running_turn_once_then_closes_on_a_daemon_thread` | integration, gated | A request runs on the loop thread or the default executor, or the client's `close()` runs on a non-daemon thread. | The fake logs the thread name of every request, and checks each one. |
| INV-2, INV-6, EC-58 to EC-60 | lifecycle guard tests (AC-33 row) | integration, gated | Calls before open, after close or from another loop are not refused, or a closed host reopens. | Each refusal's request count is compared before and after. |
| INV-11, EC-67, EC-78, EC-79 | failures late-acceptance tests (AC-32 row) | integration, gated | No turn that Codex accepts may be left without an owner. | See AC-32. |
| INV-41 | records → `test_next_step_is_the_repair_approach_and_old_calls_keep_their_packet` | unit (CI) | An old `CodexAgentError(message, failure_code=…, operation=…)` call changes its packet, or `next_step` does not become the repair approach. | It compares the whole packet of an old-style call. |
| INV-34, T-2, D-31, EC-53 to EC-55 | tools → `test_toolset_holds_the_fifteen_tools_with_their_spec_schemas`, `test_spawn_takes_the_posture_from_defaults_and_six_values_from_the_model`, `test_list_review_and_wait_tools_translate_their_arguments`, `test_wrong_argument_types_are_refused_before_the_host` | unit | A tool schema carries a posture field. JSON null replaces a default. The wait tool waits past 240 s. A wrong type reaches the host. | The schema test compares exact property sets. The type test lets only a local status read through. |
| D-28, D-20, EC-14 | turns preflight tests (AC-6 row) | integration, gated | The preflight blocks on unknown states, or loops on a cursor that repeats. | Both models must come back from the second host. |
| EC-39 | review_goals → `test_a_runtime_that_never_activates_goal_mode_fails_the_run` | integration, gated | A runtime that never activates goal mode completes as COMPLETED. | It needs FAILED with `protocol_mismatch`. |
| EC-44, D-23, EC-46 | review_goals review tests (AC-19 row) | integration, gated | See AC-19. | See AC-19. |
| EC-72, INV-9, T-3, §12.3 row 10 | failures privacy test and the turns AC-11 tests | integration, gated | A chained SDK exception that carries a canary is a leak, because every caller must raise `from None`. | `error_texts` follows `__cause__`, and `__context__` unless it is suppressed. |
| T-1 | tools cap tests (AC-25 row); turns AC-9 and AC-10 tests; tools default-policy test | unit + integration | A looping agent starts paid turns past the cap, or past the timeout or output limit. | See those rows. |
| T-6, D-32, EC-63, EC-75, EC-76 | threads reviewer tests (AC-37 row); records USER-reviewer test | integration + unit | A `user` reviewer starts a turn, whether it was asked for or reported by Codex. | See AC-37 and AC-35. |

## Tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| A live Codex run of the §4 snippet (the live half of AC-1) | It spends the user's Codex plan (NG-13) and needs a signed-in CLI. The scripted run checks the same printed lines, so the live run is manual QA. |
| Re-testing `CodexToolTranslator.translate` and `CodexToolBridge.attach` (AC-28, INV-39) | `tests/test_codex_tools.py` already pins both, and must pass unchanged (NG-5). It passes now, inside the 247 below, so a copy would only duplicate it. |
| Re-testing that every existing `FailureCode` value has a dot and a classification row (INV-40) | `tests/test_session_failures.py::FailureContractsTests::test_every_code_has_category_prefix` and `tests/test_codex_failure_recovery.py::ClassificationCoverageTests` already enforce both rules, as INV-40 says. The records test adds only the insertion point and the exact old list. |
| Semgrep, the public-API contract check, the git-blob SHA-256 and the full gate (the rest of AC-36) | They are gate steps: `python scripts/run_ci.py`, the static-policy workflow and the §11 command, run in S3–S5. A pytest wrapper would run the gate inside the gate. The packaging tests give the early signal. |
| Waiting out the real 300 s bounds (EC-5, EC-35, EC-68, EC-70) | §13 says the bounds are read at call time from the connection module, so the AC-32 test patches the request bound to 0.3 s. Waiting 300 s proves nothing more. |
| Windows npm `.cmd` launcher trees and lingering Node processes (EC-3, EC-69, T-7) | They need a real npm-installed codex and real child processes, which the no-live-Codex rule forbids. T-7 is covered by structure: the exact-schema test shows that no tool parameter carries `config_overrides` or `env`. |
| Memory growth over many turns (EC-65) | The spec accepts it (released at close), and no deterministic check exists without timing. |
| T-4, another tenant on the machine | Stdio-only transport comes from the SDK's launch args, and the host adds no listener, so there is no host behaviour to test. |
| EC-77, a review on a thread whose reviewer is `user` | The spec accepts this residual (A-7, T-6). A test would only pin a gap the spec already records. |
| Q-7, Q-8 and Q-9 controls | They are open questions and are not built. The brief forbids tests that expect them. |
| Hypothesis property tests over the records | Hypothesis is not a repo dependency. The finite input spaces (review kinds by fields, snapshot status by result by problem) are enumerated exhaustively instead. |
| Direct unit tests of `CodexGoalFinishRule` | The spec names the class (§12.3 row 13) but gives it no API of its own. Its triggers are proven through the host's goal tests, and `sdk_contract` pins the SDK hook it mirrors. |
| `limit_reached` as read from Codex | §9.2 does not say which wire field fills it, so only the record's JSON shape is checked (tools output test). |

## Red run (before implementation)

Bootstrap: one venv outside the worktree; nothing was installed globally.

```
python -m venv C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host
C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python -m pip install -e "C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host[dev,codex]"
```

It resolved openai-codex 0.162.1, pytest 8.3.5, pytest-asyncio 1.3.0 and pydantic 2.14.1. Every command below runs from the worktree root, with `PY=C:/Users/422mi/vidbyte-repos/.venvs/sdk-codex-host/Scripts/python`.

**1. The pack in the `[dev,codex]` venv.** Command: `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider -rfE tests/features/codex_host`

```
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_steer_and_interrupt_act_only_on_a_running_turn_this_host_returned - ModuleNotFoundError: No module named 'vidbyte.harnesses.native'
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_usage_tracking_lists_terminal_turns_with_their_own_deltas_and_rollup_cost - ModuleNotFoundError: No module named 'vidbyte.harnesses.native'
101 failed in 4.55s
```

Every failure is "the feature is missing":

| Count | Reason |
|---|---|
| 65 | `ModuleNotFoundError: No module named 'vidbyte.harnesses.native'` |
| 12 | `ImportError: cannot import name 'CodexHostTools'` |
| 6 | `ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.codex_host'` |
| 2 | `ModuleNotFoundError: No module named 'vidbyte.tools.builtins.codex'` |
| 2 | `ImportError: cannot import name 'codex_host'` |
| 2 | `AttributeError: … 'vidbyte.lib.enums.codex' has no attribute 'CodexApprovalPolicy'` |
| 2 | the import probe failed: the child cannot import `vidbyte.harnesses.native` |
| 1 | `TypeError: CodexAgentError.__init__() got an unexpected keyword argument 'next_step'` |
| 1 | `ImportError: cannot import name 'CodexApprovalsReviewer'` |
| 1 | `ImportError: cannot import name 'CODEX_NEXT_STEPS'` |
| 1 | `FileNotFoundError: … vidbyte\harnesses\native\__init__.py` |
| 1 | `AttributeError: type object 'CodexToolTranslator' has no attribute 'validate_names'` |
| 1 | `AttributeError: … 'vidbyte.lib.constants.codex' has no attribute 'CODEX_HOST_REQUEST_TIMEOUT_SECONDS'` |
| 1 | `AttributeError: 'CodexToolBridge' object has no attribute 'handler'` |
| 1 | `AssertionError` in the `FailureCode` order (the new codes are absent) |
| 1 | `AssertionError` in the harnesses README bullet (absent) |
| 1 | `AssertionError` in the REPO_MAP section (absent) |

Per file, with the same command on one file each:

| File | Result |
|---|---|
| records | `11 failed in 0.80s` |
| packaging | `7 failed in 2.06s` |
| bridge | `2 failed in 0.73s` |
| tools | `17 failed in 0.94s` |
| lifecycle | `13 failed in 1.43s` |
| turns | `13 failed in 1.42s` |
| threads | `19 failed in 1.57s` |
| review_goals | `9 failed in 1.30s` |
| failures | `6 failed in 1.21s` |
| router | `1 failed in 1.07s` |
| sdk_contract | `3 failed in 1.05s` |

**2. The CI view, with `openai_codex` unimportable as in CI's `.[dev]` install.** Command: `PYTHONPATH=$(pwd) $PY -c "import sys; sys.modules['openai_codex']=None; import pytest; sys.exit(pytest.main(['-q','-p','no:cacheprovider','-rfEs','tests/features/codex_host']))"`

```
FAILED tests/features/codex_host/test_codex_host_tools.py::CodexHostToolsMcpTests::test_mcp_server_lists_and_runs_the_toolset - ImportError: cannot import name 'CodexHostTools' from 'vidbyte.tools.toolsets' (…)
SKIPPED [1] tests\features\codex_host\test_codex_host_turns.py:413: requires the optional openai-codex extra
35 failed, 66 skipped in 1.75s
```

**3. The whole suite, confined to the new files.** Command: `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider -rfE tests`

```
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_steer_and_interrupt_act_only_on_a_running_turn_this_host_returned
FAILED tests/features/codex_host/test_codex_host_turns.py::CodexHostSteerAndUsageTests::test_usage_tracking_lists_terminal_turns_with_their_own_deltas_and_rollup_cost
101 failed, 3940 passed, 22 skipped in 37.92s
```

All 101 FAILED lines are under `tests/features/codex_host/`. `grep "^FAILED" | grep -v tests/features/codex_host/` prints nothing.

**4. The existing Codex suites (NG-5).** Command: `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider` over the nine `tests/*.py` files that mention codex: `test_codex_agent_input_bridge`, `test_codex_failure_recovery`, `test_codex_middleware`, `test_codex_output_contracts`, `test_codex_pipelines`, `test_codex_tools`, `test_codex_usage_tracking`, `test_readme_size_limit` and `test_skills_interface`.

```
247 passed in 1.98s
```

**5. Collection.** Command: `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider --collect-only tests`

```
4063 tests collected in 1.29s
```

That is the 3962 tests from before, plus the 101 new ones.

**6. Lint.** Stage the files with explicit paths, then run `PYTHONPATH=$(pwd) $PY lint/run.py`; the output ends `SDK-LINT: PASS`. The final lines are quoted in `reports/S2-test-author.md`.

## Which tests run in CI, and which skip

CI installs only `.[dev]` (`.github/workflows/ci.yml`) and runs `python scripts/run_ci.py`, which runs the full pytest discovery, so `openai_codex` is not importable there.

**Run in CI: 35 tests, red now.**

| File | Tests that run |
|---|---|
| records | 10 of 11: every test except `test_wire_values_match_openai_codex` |
| packaging | 6 of 7: every test except `test_imports_leave_an_installed_sdk_unloaded` |
| bridge | 2 of 2 |
| tools | 17 of 17 |

**Skipped in CI: 66 tests**, each with the reason "requires the optional openai-codex extra".

| File | Tests that skip |
|---|---|
| lifecycle | 13 |
| turns | 13 |
| threads | 19 |
| review_goals | 9 |
| failures | 6 |
| router | 1 |
| sdk_contract | 3 |
| records | `test_wire_values_match_openai_codex` |
| packaging | `test_imports_leave_an_installed_sdk_unloaded` |

These run only where the `codex` extra is installed, as in this worktree's venv. S3–S5 must run them there, because CI never will.

## Notes for the implementer

**The seam and the patches.**
- The seam is `vidbyte.harnesses.native.codex.connection.CodexClient`. `connection.py` binds `CodexClient` and `CodexConfig` at module level with `from openai_codex.client import CodexClient, CodexConfig` (§12.3 row 12).
- Only the host's open may import `connection`. The package `__init__`, the records, the tools and the toolset must not import it, or AC-2 fails.
- The fake client subclasses the real `CodexClient`. Call only the methods and parameters in `sdk_contract`'s `CALL_LIST`, with `response_model` and `max_attempts` as keywords.
- The tests patch `CODEX_HOST_WORKER_THREADS`, `CODEX_HOST_REQUEST_TIMEOUT_SECONDS` and `CODEX_HOST_CLOSE_INTERRUPT_SECONDS` in the connection module's namespace. Import them by name there, and read them at call time. The worker count is read when the host opens.
- `shutil.which` is patched on the `shutil` module, and `sys.platform` on `sys`. Call `shutil.which(...)` and read `sys.platform` at call time, never through a name bound at import.

**Threads and goal runs.**
- Every request runs on the host's own workers. None may run on `MainThread` or on a thread whose name starts with `asyncio_` (the default executor). The client's `close()` runs on a daemon thread.
- The goal watcher reads through `client.next_goal_notification(state)`.
- A start failure cleans up in this order: `cancel_goal_operation`, `finish`, `unregister_goal_operation`.
- A finished run closes its stream with `finish`, `wake_notification_reader`, `unregister_goal_operation`.
- Close runs `cancel_goal_operation`, `finish`, `wake_notification_reader`, `unregister_goal_operation`.

**Errors.**
- Raise every mapped error `from None` (§12.3 row 10). The privacy tests read the visible exception chain, so `raise … from exc` leaks the SDK's text and fails AC-34.
- The tests require these messages:
  - `model_unknown` lists the available ids (the fake's are `gpt-5.5` and `gpt-5.5-codex-latest`).
  - A launch that fails midway contains the standalone number of turns it started (`2`).
  - The user-reviewer refusal names the thread id.
  - The request-bound `api_error` names the thread already created.
  - The close-wins `process_exited` names the thread id.
  - A `RuntimeError` mapped to `api_error` names the type, never its text.

**Handles.** A handle is owned by value, as `(thread_id, turn_id)` of a turn this host registered. That includes late-accepted turns, which the tests rebuild from ids (see OPEN ITEMS in the S2 report).

**Fixed tests.** Do not edit any test's assertions. If a name must change, change the spec first.

**Run commands.** Run the pack with `PYTHONPATH=$(pwd) $PY -m pytest -q -p no:cacheprovider tests/features/codex_host` in a venv that has the `codex` extra. Then run the CI view (step 2 above), which must show the 66 skips and no failures.
