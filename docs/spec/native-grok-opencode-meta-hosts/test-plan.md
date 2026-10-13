# Test plan: native Grok, opencode and Muse hosts, plus GLM and DeepSeek backend profiles

- **Spec:** `docs/spec/native-grok-opencode-meta-hosts/spec.md` r3.
- **Stage:** S2, test author. The tests were written before any implementation and are red for the right reason.
- **Base:** `aa8c380c4cd1d5791526dd545f5ef1020b28a5cc`. Spec head `f2894d03`.
- **Packs** (no `__init__.py`, A001 headers, `FEATURE.md`, and a `README.md` with `## File Index` and `## Logs`):
  - `tests/features/grok_host/`: GrokHost, plus the shared plumbing (the transport extension, `vidbyte.lib.process`, the validator, `NativeHostError`, hostkit, the vocabulary, enums, constants, INV-19, AC-18 and AC-20).
  - `tests/features/opencode_host/`: OpencodeHost.
  - `tests/features/muse_host/`: MuseHost and its WSL path.
  - `tests/features/native_backends/`: the backend profiles and their tools.
- **Seams** (spec §13 only):
  - `GrokHostSettings.grok_command` and `MuseHostSettings.muse_command` run scripted fake peers as real child processes.
  - `OpencodeHostSettings.opencode_command` runs a fake `opencode serve`.
  - `vidbyte.lib.http.transport.httpx.AsyncClient` is patched with a factory over the real class plus `httpx.MockTransport`.
  - `monkeypatch` controls the `*_API_KEY` variables.
  - `vidbyte.lib.constants.native_hosts.{NATIVE_STOP_GRACE_SECONDS, NATIVE_KILL_WAIT_SECONDS, OPENCODE_POLL_INTERVAL_SECONDS}` are patched to shrink timings.
  - Nothing patches `HttpTransport`, `McpStdioTransport`, `CliRunner` or any host class.

## Coverage map

Level key: A = acceptance, C = contract (an error row or a record), I = integration (real processes over real pipes), U = unit, P = property or exhaustive, S = security, X = concurrency or cancellation, R = regression.

How the error tables are covered. Each pack has one table-driven `test_*_error_row` (or `test_*_errors`) with one `pytest.param` per (function, code), driven through the §13 fakes. Each case asserts:
- `failure_code is FailureCode[<VALUE>]`;
- a non-empty `next_step` that contains the row's required token;
- the `operation`;
- every context value is a `str`, and every key is in the §13 list;
- what the fake saw: nothing sent or launched before a failed check (INV-5), and the expected launches.

The same row then runs through the matching tool, which must return `ToolResult.error` with `metadata["error"] == code`, `hint == next_step`, `operation` and `harness`, and output shaped `"<code>: … Next step: <next_step>"` (INV-7).

### Grok host and shared plumbing (`tests/features/grok_host/`)

| Spec ID | Test (file → name) | Level | Failure it catches | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | `test_grok_host_acceptance.py` → `test_snippet_prints_completed_text_when_grok_is_the_fake`, `test_snippet_prints_not_installed_line_when_no_grok_exists` | A | The §4 snippet does not run as written, prints the wrong line, or reaches a real `grok` | Both compare the exact stdout line. The first also requires the fake's log to show the `session/prompt`, so a different `grok` cannot satisfy it. PATH holds only a temporary shim folder (plus System32 on Windows), and HOME is a temporary folder. |
| AC-2 (grok), FR-6, FR-21 | `test_grok_host_errors.py` → `test_grok_error_row` (79 rows × host and tool mode) | C | A wrong code, a missing token, a raw exception, or a process or request started before a failed check | Exact enum identity, token substring, context types and keys, plus fake-log facts (`never_sent`, `never_launched`, `peer_launches`). The rows cover all 13 `grok.*` codes. |
| AC-3, NFR-2, EC-13 | `test_grok_host_process_bounds.py` → `test_unresponsive_peer_raises_server_unreachable_within_the_bound`, `test_unresponsive_peer_bound_holds_with_default_timings`, `test_unresponsive_peer_is_reaped_before_the_error_is_raised` | I | A silent `initialize` hangs, or the peer outlives the error | The peer ignores EOF and TERM (`ignore_eof`, `ignore_term`), so only a real tree stop ends it. The bounds are upper bounds with 2 s slack, and the default-timing case asserts the spec's 9 s. Liveness is checked on POSIX. |
| AC-4, EC-4, INV-2 | `test_grok_host_process_bounds.py` → `test_cancelling_a_call_propagates_and_stops_what_it_started` [spawn, continue, list, check], `test_cancelling_a_wait_leaves_the_turn_running` | X | Cancellation is swallowed, a process is left running, or a cancelled wait kills the turn | The task is cancelled only after the fake logs the request (or the `--version` launch). `CancelledError` must propagate, and a later wait must return `COMPLETED`. |
| AC-6, INV-11 | `test_grok_host_acceptance.py` → `test_spawn_returns_a_handle_while_the_turn_is_still_running` | A | Spawn blocks until the turn ends | The fake holds the turn until the test writes the release file. The test checks that no answer to the prompt id was sent before spawn returned. |
| AC-7 (grok), EC-25, EC-37 | `test_grok_host_errors.py` → EC-25 and EC-37 rows; `test_model_unknown_context_names_the_models_grok_offers` | C | A silent fallback model runs the turn | The fake echoes a known `--model` and falls back for an unknown one, as Grok does. The row asserts that no `session/new` or `session/prompt` was received, and that `available_models` lists the live ids. |
| AC-8, D-11, INV-10 | `test_grok_host_turns.py` → `test_edit_permission_is_rejected_then_allowed_by_policy`, `test_permission_without_a_reject_option_is_answered_cancelled`, `test_missing_or_unknown_tool_kind_counts_as_other`, `test_unknown_server_request_gets_method_not_found_and_is_recorded`, `test_recorded_decisions_are_capped_and_the_overflow_counted` | I | An `*_always` option is chosen, a request goes unanswered, or a decision is unrecorded | The fake records the exact `optionId` it got back, and offers both `*_always` options every time. |
| AC-11, AC-12, INV-12, INV-13, EC-44, EC-52 | `test_grok_host_acceptance.py` → `test_wait_times_out_then_returns_the_result`, `test_interrupting_a_finished_turn_twice_reports_not_running` | A | A timed-out wait touches the turn, or a second interrupt raises or sends | The fake log must show no `session/cancel`. |
| AC-15, EC-142 | `test_grok_host_tools.py` → `test_default_policy_denies_the_write_tool_and_runs_the_read_tool` | A | WRITE tools run under the default policy | It uses the real `ToolExecutor` and `PermissionPolicy()`, and the fake must show no launch after the denial. |
| AC-16 (hash), INV-19 | `test_grok_host_shared_contract.py` → `test_native_package_init_matches_the_fixed_bytes` | R | The fixed `native/__init__.py` bytes drift | It hashes the LF-normalised bytes against the INV-19 SHA-256. |
| AC-16 (transport), INV-18, FR-15, D-3 | `test_grok_transport_extension.py` → all 14 tests; the existing `tests/test_mcp_stdio_transport.py` and `tests/test_mcp_studio_server.py` stay unedited | I, R | The dispatch fix is missing, a callback kills the reader, per-call deadlines or invalid values are ignored, or the tree stop or close is unbounded | A real child peer over real pipes. The invalid values are checked against `McpProtocolError` reason `invalid_call`. |
| AC-17, INV-8 | `test_grok_host_shared_contract.py` → `test_next_steps_hold_every_code_verbatim`, `test_every_new_code_starts_with_its_host_prefix`, `test_native_host_error_*` (4) | C | A next step is missing or reworded, or a prefix is wrong | The 55 catalog texts are copied from §6.3.1 and compared verbatim, ignoring markdown backticks. The prefix counts are read from the live enum. |
| AC-18, INV-21, NFR-5 | `test_grok_host_shared_contract.py` → `test_import_vidbyte_starts_no_process_and_loads_no_vendor_sdk` | I | `import vidbyte` spawns a process or loads `acp`, `muse_code_sdk` or `opencode_ai` | A fresh interpreter with an audit hook on the process-creation events. It also requires the four new toolset modules to be loaded, so an import that skips them is not a pass. |
| AC-19 (grok), INV-9, T-2 | `test_grok_host_tools.py` → `test_no_grok_tool_offers_an_approve_everything_or_directory_parameter`; `test_grok_host_reads.py` → `test_one_shot_argv_carries_every_value_in_name_value_form`; `test_grok_host_turns.py` → `test_turn_peer_wire_shapes`, `test_peer_argv_carries_model_and_effort_in_name_value_form`; `test_grok_host_shared_contract.py` → `test_grok_permission_mode_has_no_approve_everything_member`; records → EC-23 and EC-33 dash rows | S | A prompt or id becomes a flag, an approve-everything value reaches argv, or `session/new` carries `_meta` | The prompt is literally `--always-approve`, and it must appear only as `--single=--always-approve`. Every argv the fake saw is scanned. |
| AC-20, D-3 | `test_grok_host_shared_contract.py` → `test_each_entry_module_imports_first_in_a_fresh_interpreter` [7], `test_all_entry_modules_import_in_reverse_order` | I | An import cycle that depends on order | Each case enters the chain with one module, then imports the other six, so the three modules that exist today are not a pass by themselves. |
| INV-20 | `test_grok_host_shared_contract.py` → `test_the_53_new_members_follow_rule_evaluation_failed_in_catalog_order`, `test_existing_failure_code_members_are_unchanged` | R | Members are inserted mid-enum, renamed, or a `codex.*` code is added | A SHA-256 fingerprint of the 120 base members, the codex count of 12, and the exact order of the 53. |
| INV-5, EC-23, EC-33, D-8 | `test_grok_host_records.py` → all 21 tests | C, P | A bool accepted as a number, a string accepted as an enum, a long value quoted, or a mutable record | One bad field per row on a known-good record. The message must name `<Record>.<field>`. The validator's 13 methods are each tried with accept and reject tables. |
| EC-1 to EC-3, EC-28, EC-32, EC-11 (PATH) | `test_grok_host_errors.py` → `test_invalid_primitive_arguments_fail_before_any_process` (EC-28 and EC-32 are its `session_id` and `new_session_id` cases), `test_unopened_or_closed_host_raises_process_exited`, `test_reentering_a_host_raises_invalid_argument`, `test_aenter_without_any_grok_raises_not_installed` | C | I/O before validation, a closed host that still works, or re-entry allowed | The fake's `start` records must be empty. PATH, HOME and USERPROFILE point at empty temporary folders. |
| EC-5 | `test_grok_host_shared_contract.py` → `test_error_factory_from_unexpected_names_only_the_class`; `test_grok_host_tools.py` → `test_unexpected_tool_exception_becomes_runtime_error_naming_only_the_class` | C | `str(exc)` leaks, or the class name is lost | The exception text is a unique phrase that must be absent. |
| EC-6 | `test_grok_host_reads.py` → `test_garbage_frames_before_an_answer_are_dropped`, `test_garbage_instead_of_an_answer_fails_at_the_deadline` | I | Garbage kills the reader, or resolves a request | Four kinds of garbage frame come before the real answer. A silent answer must still time out. |
| EC-7, EC-50, EC-53, D-10, INV-15, EC-148, EC-150 | `test_grok_host_turns.py` → `test_unknown_notifications_and_update_kinds_are_ignored`, `test_completed_stop_reasons_are_kept_verbatim`, `test_interrupt_*` (2), `test_turn_ceiling_interrupts_with_deadline_source`, `test_usage_is_none_when_grok_reports_none`, `test_a_failed_turn_raises_the_same_code_on_every_wait`, `test_text_over_the_cap_is_cut_and_flagged` | I | A wrong terminal state or source, usage reported as 0, or uncapped text | The status, source, stop reason and text are each compared exactly. |
| EC-8, INV-4 | `test_grok_host_process_bounds.py` → `test_aexit_interrupts_live_turns_as_host_closed_within_the_bound`, `test_aexit_leaves_no_process_running`, `test_aexit_never_suppresses_the_body_exception`, `test_aexit_on_cancellation_still_stops_the_turn` | X, I | `__aexit__` leaves turns running, closes peers one after another, swallows the body exception, or skips its stop under cancellation | Two stubborn peers. The bound for two is the bound for one, and HOST_CLOSED must be the source on both. |
| EC-9, INV-14, INV-17, EC-149 | `test_grok_host_turns.py` → `test_concurrent_continues_on_one_session_let_only_one_through`, `test_concurrent_spawns_respect_the_live_turn_cap`, `test_a_failed_spawn_releases_its_reservation`, `test_a_handle_is_scoped_to_the_host_that_issued_it`; `test_grok_host_shared_contract.py` → `test_turn_table_*` (4) | X | The busy check races, a failed spawn leaks its slot, a foreign handle is accepted, or the finished table never evicts | It uses `asyncio.gather` on one host. The table test fills 65 finished turns and expects the first handle to be gone. |
| EC-10, D-23, EC-38 | `test_grok_host_process_bounds.py` → `test_turn_end_stops_a_grandchild_of_the_peer`, `test_one_shot_timeout_stops_the_cli_tree`; `test_grok_host_process_helpers.py` → `test_stop_tree_*` (2), `test_cli_runner_timeout_stops_the_whole_tree` | I | A grandchild survives the leader | The grandchild pid is logged by the fake and checked through `/proc` (POSIX only). |
| EC-27, EC-51 | `test_grok_host_turns.py` → `test_spawn_raises_process_exited_when_the_prompt_write_fails`, `test_interrupt_raises_process_exited_when_the_cancel_write_fails` | I | A write failure escapes raw | The fake closes its stdin, so the next write really fails (POSIX only). |
| EC-138 to EC-141, EC-143 to EC-145 | `test_grok_host_tools.py` → `test_bad_arguments_return_invalid_argument_naming_the_parameter` [12], `test_missing_required_parameter_under_the_executor_is_its_validation_error`, `test_tool_waits_above_the_tool_cap_are_refused` [3], `test_tool_wait_at_exactly_the_cap_is_accepted`, `test_malformed_handle_argument_returns_invalid_argument` [5], `test_cancelling_a_tool_call_propagates_and_leaves_the_turn_running`, `test_large_output_is_clipped_at_a_utf8_boundary` | C | A tool raises, accepts 241 s, or cuts mid-character | The boundary pairs are 240 (accepted) and 240.5 or 241 (refused). The clipping uses three-byte characters, so a byte cut leaves U+FFFD, and `metadata["truncated"]` must be set. |
| FR-1, FR-5, §9.2 rows 1–10, T-5 | `test_grok_host_tools.py` → `test_grok_tools_match_the_spec_table`, `test_read_only_returns_exactly_the_read_tools`, `test_tool_classes_are_named_after_their_functions_and_exported`, `test_spawn_then_wait_round_trips_the_handle_as_json` | C | A wrong name, permission or parameter set, or a handle that does not round-trip | It compares the exact parameter-name to required map and the JSON type of every parameter. |
| FR-1 reads, D-12, FR-17 | `test_grok_host_reads.py` → the readiness, catalog, page, search (4), one-shot (5), fork (2) and child-environment tests; `test_grok_host_acceptance.py` → `test_module_level_run_grok_once_*` (2) | I | A dropped field, wrong casefolding, a missing page cap, a lost cursor, or spending before the fork check | Search uses "Straße" against "STRASSE", which passes only under `casefold`. The endless listing must take exactly 20 requests. |
| FR-9, FR-16, D-21, INV-3, INV-16 | `test_grok_host_process_helpers.py` → all 19 tests | I | Inheriting the caller's stdin, blocking on a full pipe, raising on a launch failure, ignoring the timeout, or a non-idempotent stop | fd 0 is swapped for a pipe that never reaches EOF, so an inherited stdin blocks and the run times out. A 2 MB write after the ready line must finish. |

### Backend profiles (`tests/features/native_backends/`)

The rows below are condensed from the pack's own inventory (138 tests).

| Spec ID | Test (file → name) | Level | Failure it catches | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-2 (backend), FR-6, EC-122 to EC-136 | `test_native_backends_errors.py` → `test_backend_error_row` (63 cases, host and tool mode) | C | A wrong code or token, a key in the output, or I/O before a check | The EC-123 and EC-127 rows assert the exact one-variable next step, because the default text names both variables. The default rows assert `next_step == NATIVE_HOST_NEXT_STEPS[code]`. Rows with no HTTP assert an empty endpoint log. |
| EC-132 shapes | same → 11 `get_deepseek_balance` shape variants | C, P | A silent fallback on a wrong body shape | Each variant breaks exactly one member. |
| AC-5 (API key), INV-6, T-3 | `test_native_backends_security.py` → `test_error_body_echoing_the_key_is_redacted_in_the_error`, `test_error_body_echoing_the_key_is_redacted_in_the_tool_result`, `test_classified_statuses_never_echo_the_key` [3], `test_unparseable_body_echoing_the_key_is_not_surfaced`, `test_transport_exception_text_is_never_surfaced`, `test_vendor_text_in_the_error_is_capped`, `test_missing_key_error_names_the_variable_and_no_other_key`, `test_no_backend_record_repr_shows_a_key` | S | The key leaks in a message, context, tool output, metadata or `repr` | The key is echoed in free text, not as `key=value`, so `HarnessRedactor` alone cannot hide it. Only the registered-value replacement does. |
| AC-13 | `test_native_backends_profiles.py` → `test_deepseek_env_has_exactly_the_spec_keys_and_hides_the_value` | A | Extra or missing env keys, or the key in `repr` | Exact dict equality, then the `not_signed_in` row after `delenv`. |
| AC-14 | `test_native_backends_profiles.py` → `test_compat_refuses_unsupported_features_then_disallowed_harness_without_network` | A | A network call, or the wrong code | No request is made and no client is built. |
| EC-135, EC-136 | `test_native_backends_profiles.py` → `test_compat_lists_every_offending_feature_sorted_for_every_subset` (all 2,048 subsets), `test_compat_refuses_every_harness_glm_does_not_allow_whatever_the_features` | P | Only the first offending feature reported, or an unsorted list | Exhaustive over the subsets. |
| §9.1 profiles, D-16, §12.3 rows 14–15 | `test_native_backends_profiles.py` → `test_declared_profile_matches_the_spec_table` [glm, deepseek], `test_harness_backends_is_declared_in_name_order_and_exported`, `test_module_functions_are_the_harness_backends_static_methods`, `test_every_declared_model_builds_the_exact_environment`, `test_env_reads_the_key_variable_on_every_call`, `test_opencode_provider_names_the_built_in_provider_without_a_key` [2] | C, P | A wrong profile field, a cached key, or a key copied into a provider record | Literal spec data, `is` identity, and exact equality for every model. |
| D-17, INV-3, EC-4 | `test_native_backends_balance.py` → `test_balance_is_one_bearer_get_to_the_fixed_url`, `test_balance_call_uses_the_backend_http_deadline`, `test_balance_parses_every_entry_as_decimals`, `test_glm_readiness_checks_the_key_and_makes_no_remote_call`, `test_deepseek_readiness_verifies_the_key_through_the_balance`, `test_cancelling_a_balance_call_propagates` [2] | I, X | A spending call, a GLM remote call, parsing through float, the wrong deadline, or a swallowed cancel | The exact request list. The real `AsyncClient` construction options are read. A held MockTransport request is cancelled. |
| EC-134, §9.1 records | `test_native_backends_records.py` → all 26 tests | C | A bad field accepted, a secret in `repr`, or a mutable collection | One field per row, and the message must name `<Record>.<field>`. |
| FR-5, §9.2 rows 41–43, EC-147 | `test_native_backends_tools.py` → all 14 tests | C | A wrong toolset, permission or JSON shape, or an unknown backend accepted | The default policy runs all three READ tools. The backend is tried as "kimi", "GLM", "", 7, a list, and missing. |

### opencode host (`tests/features/opencode_host/`)

The rows below are condensed from the pack's inventory (581 tests).
- **Fakes.** `FakeOpencodeServer` answers 22 routes through `httpx.MockTransport` and records every request: its method, path, query, body and basic-auth pair. `fake_opencode_serve.py` stands in for `opencode serve` through `opencode_command`, and logs its argv and a digest of its environment (never a value).
- **AC-3.** It uses a real loopback socket that accepts a connection and never answers.

| Spec ID | Test (file → name) | Level | Failure it catches | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-2 (opencode), FR-6, EC-55 to EC-93, EC-155 | `test_opencode_host_errors.py` → `test_opencode_error_row` (125 rows × host and tool mode) | C | A wrong code or token, a raw `ProviderRequestError` or `KeyError`, or a request sent after a failed check | Every HTTP-calling function (16) runs the host-wide rows EC-55, EC-57, EC-58 and EC-59. Each case checks the fake's request log, so a row that fails only after sending is caught. The rows cover 14 of the 16 `opencode.*` codes. The other two, `not_installed` and `process_exited`, are proved by the owned-server tests. |
| EC-59, EC-68 context; EC-60 | `test_api_error_context_names_the_vendor_error_and_status`, `test_model_unknown_context_lists_at_most_twenty_ids`, `test_aenter_error_row` [6] | C | The vendor error name or status is lost, the model list is unbounded, or a bad server is accepted at start | Exact context values. The model list has more than 20 ids. |
| EC-1, EC-2, EC-3, EC-64, EC-71, EC-74, EC-77 | `test_invalid_primitive_arguments_make_no_request` [128], `test_unopened_or_closed_host_raises_process_exited` [18], `test_reentering_a_host_raises_invalid_argument` | C | A request is sent before an argument is checked, a closed host still works, or re-entry is allowed | The request log must be empty after each case. |
| AC-3, NFR-2, EC-55 | `test_opencode_host_acceptance.py` → `test_unresponsive_server_raises_server_unreachable_within_the_timeout`, `test_unresponsive_server_fails_aenter_within_the_timeout` | I | A request to a server that never answers hangs | A real loopback socket accepts and never answers, so only the `HttpTransport` deadline can end the call. The test asserts `elapsed < request_timeout_seconds + slack` and the `request_timeout_seconds` token. |
| AC-4, EC-4, INV-2 | `test_cancelling_a_call_propagates_and_releases_its_reservation` [5], `test_cancelling_a_wait_leaves_the_turn_running`; `test_opencode_host_owned_server.py` → `test_cancelling_aenter_stops_the_server_it_started` | X | Cancellation is swallowed, a reservation leaks, or a cancelled wait aborts the turn | The fake holds the route until the test cancels. `max_live_turns=1`, then a later continue must succeed, which needs the slot released. No `prompt_async` may be sent. |
| AC-5 (opencode), INV-6, T-3 | `test_opencode_host_security.py` → `test_attached_server_password_in_a_vendor_error_is_redacted`, `test_owned_server_password_in_a_vendor_error_is_redacted`, `test_backend_key_in_a_vendor_error_is_redacted`, `test_mcp_environment_value_in_a_failed_status_is_redacted`, `test_mcp_header_value_in_a_vendor_error_is_redacted`, `test_vendor_text_in_an_error_is_capped`, `test_secret_fields_never_reach_a_repr`, `test_the_host_logs_nothing` | S | An injected secret reaches a message, context, tool output, metadata, a `repr` or a log | The owned-server password is read back from the basic-auth header the host really sent, so it is the live random value. The vendor echoes it in free text. |
| AC-6, AC-7, AC-11, AC-12 (opencode) | `test_opencode_host_acceptance.py` → `test_spawn_returns_a_handle_while_the_turn_is_still_running`, `test_unknown_model_is_refused_before_any_turn_starts` [spawn, continue], `test_wait_times_out_then_returns_the_result`, `test_interrupting_a_finished_turn_twice_reports_not_running` | A | Spawn blocks, a fallback model is used, a timed-out wait aborts, or a second interrupt raises | AC-7 asserts that no `POST /session` and no `prompt_async` were seen. AC-11 and AC-12 assert that no `abort` was seen. |
| AC-9, FR-18, D-18, T-4 | `test_opencode_host_owned_server.py` → `test_owned_server_starts_on_loopback_with_a_fresh_password_in_its_environment_only`, `test_each_owned_server_gets_its_own_password`, `test_owned_server_and_its_tree_are_stopped_on_exit_within_the_bound`, `test_owned_server_exit_returns_within_the_bound`; `test_opencode_host_security.py` → `test_provider_key_and_options_never_reach_a_result` | A, S | The server listens off loopback, the password is fixed, put on argv or put in the caller's environment, or the server outlives the host | The digest of the password the host sends must equal the digest of the one the child received. Two hosts must get different digests. On POSIX the server ignores TERM and has a grandchild. |
| EC-54, EC-56, EC-60, EC-61, EC-153, D-16 | `test_opencode_host_owned_server.py` → the remaining 9 tests | I | A failed start leaks the server, a missing key starts a server anyway, or a dead server is restarted silently | The fake logs every `start`. |
| EC-8, EC-82 to EC-89, EC-148, EC-150, EC-154, EC-155, D-10, D-14, INV-15 | `test_opencode_host_watcher.py` → all 22 tests | I | The wrong reply is taken as the turn's, an unfinished reply completes, retries never stop, a permission or question is left pending, or usage is wrong | The fake serves replies to earlier turns, replies still being written, and parentID replies that have left the message window. |
| AC-19 (opencode), INV-9, D-11, T-2 | `test_opencode_host_records.py` → `test_the_allow_everything_rule_is_refused`, `test_narrower_or_non_allow_wildcard_rules_are_accepted`; `test_opencode_host_security.py` → `test_no_allow_everything_rule_is_ever_sent`; `test_opencode_host_tools.py` → `test_no_opencode_tool_offers_a_permission_directory_or_mcp_shape_parameter`, `test_spawn_tool_sends_no_permission_rules` | S | `*`/`*`/`ALLOW` is accepted or sent, or a tool can carry rules | The near-miss rules must still be accepted, so a validator that refuses every wildcard fails. |
| EC-66, EC-91, EC-152, §9.1 | `test_opencode_host_records.py` → the remaining 11 tests (63 cases with the two above) | C | A bad field is accepted, or an env, header or password value is quoted in an error | One bad field per case, and the message must name `<Record>.<field>`. |
| EC-9, INV-14, EC-67 | `test_two_concurrent_continues_on_one_session_cannot_both_pass`, `test_two_concurrent_spawns_at_the_cap_cannot_both_pass`, `test_a_failed_spawn_releases_its_live_turn_slot` | X | The busy check or the cap races | Uses `asyncio.gather` on one host. |
| FR-1 reads, D-14, EC-79, EC-90 | `test_opencode_host_acceptance.py` → the 13 read, fork, revert, MCP, abort and request-shape tests | I | A dropped or renamed field, or a request without the workspace or basic auth | `test_every_request_names_the_workspace_and_carries_basic_auth` scans every request in the log. |
| FR-5, §9.2 rows 11–28, AC-15, EC-138, EC-142, EC-144 to EC-146 | `test_opencode_host_tools.py` → all 16 tests (37 cases) | C | A wrong tool name, permission or parameter set, a non-string `Decimal`, or an unregistered MCP name accepted | The exact parameter-to-required map. AC-15 uses the real `ToolExecutor`. |

### Muse host (`tests/features/muse_host/`)

The rows below are condensed from the pack's inventory (458 tests).
- **Fake peer.** `fake_muse_peer.py` speaks MSP through `muse_command`. It validates every frame against the spec's member sets, and answers a schema violation with -32600 or -32602.
- **Fake `wsl.exe`.** On win32, `make_wsl_host` builds a fake `wsl.exe` from pip's distlib `t64.exe` launcher and puts it first on PATH. It serves the distro `VidbyteFakeDistro`, so the real `wsl.exe -d MuseUbuntu1` is never launched.

| Spec ID | Test (file → name) | Level | Failure it catches | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-2 (Muse), FR-6, EC-95 to EC-120 | `test_muse_host_errors.py` → `test_muse_error_row` (101 rows × host and tool mode) | C | A wrong code or token, a raw JSON-RPC error, or a peer started before a failed check | EC-95 to EC-100 and EC-102 run once for each of the 9 peer-using functions. The fake's `start` log and `schema_violation` log are checked. The rows cover 14 of the 15 `muse.*` codes. The 15th, `wsl_unavailable`, is proved in `test_muse_host_wsl.py`. |
| EC-1, EC-2, EC-3, EC-95, EC-110 | `test_invalid_primitive_arguments_fail_before_any_process` [44], `test_unopened_or_closed_host_raises_process_exited`, `test_reentering_a_host_raises_invalid_argument`, `test_aenter_without_muse_on_path_raises_not_installed` | C | I/O before validation, or a closed host that still works | The fake's `start` records must be empty. |
| AC-3, NFR-2, EC-97 | `test_muse_host_process_bounds.py` → `test_unresponsive_peer_raises_server_unreachable_within_the_bound` [9], `test_unresponsive_peer_bound_holds_with_default_timings` | I | A silent peer hangs, or survives the error | The peer ignores EOF and TERM. With the defaults the bound is the control timeout plus 9 s. Liveness is checked on POSIX. |
| AC-4, EC-4, INV-2 | `test_cancelling_a_call_propagates_and_stops_what_it_started`, `test_cancelling_a_wait_leaves_the_turn_running` | X | Cancellation is swallowed, or a process is left behind | The task is cancelled only after the fake logs the request. No `turn/start` may follow, and the stubborn peers must be gone on POSIX. |
| AC-6, AC-11, AC-12 (Muse) | `test_muse_host_acceptance.py` → `test_spawn_returns_a_handle_while_the_turn_is_still_running`, `test_wait_times_out_without_touching_the_turn_and_a_later_wait_returns`, `test_interrupting_a_finished_turn_twice_reports_not_running` | A | Spawn blocks, a timed-out wait interrupts, or a second interrupt raises | The fake log must show no `turn/interrupt`. |
| AC-7 (Muse), EC-108 | `test_muse_error_row` EC-108 rows; `test_model_unknown_context_names_the_models_muse_offers` | C | A turn starts on an unknown model | No `session/start`, `session/resume` or `turn/start` may be received, and the context must list the live ids without the unknown one. |
| AC-10, FR-19, D-23, EC-94 | `test_muse_host_wsl.py` → `test_to_wsl_maps_a_drive_path_under_mnt`, `test_wsl_turn_peer_launch_workspace_overlay_and_reap`, the 4 `wsl_unavailable` tests, `test_missing_in_distro_muse_is_not_installed`, `test_check_in_wsl_mode_runs_version_through_the_distro`, `test_short_lived_read_peer_skips_the_reap`, `test_wslenv_gets_no_key_entry_when_meta_api_key_is_unset`, `test_reap_script_kills_marked_processes_and_their_children_only` | A, I | The `.cmd` shim is used, the workspace is not translated, the caller's WSLENV is lost, or the reap is skipped or runs with the peer's overlay | The fake `wsl.exe` logs its exact argv (`-d <distro> -e /usr/local/bin/muse serve`) and the reap script it received over stdin. The AC-10 literal path `C:/w/repo` is proved through `to_wsl`. |
| AC-8 analogue for Muse, D-11, INV-10, EC-121, EC-156 | `test_muse_host_turns.py` → the 8 approval, decide and request tests | I | An approval is allowed, a decide failure is ignored, or a request goes unanswered | The fake records the exact choice and requirement it got back. |
| EC-9, EC-109, EC-148, EC-150, D-10, D-14, INV-13 to INV-17 | `test_muse_host_turns.py` → the remaining 12 tests | I, X | A foreign turn's events counted, uncapped text, usage reported as 0, or a foreign handle accepted | Exact status, source and text comparisons. |
| EC-8, EC-10 | `test_muse_host_process_bounds.py` → the `test_aexit_*` (4) and grandchild tests | X, I | `__aexit__` leaves turns running or swallows the body exception | Stubborn peers, and HOST_CLOSED as the source. |
| D-13, D-19, AC-19 (Muse), INV-9 | `test_muse_host_wire.py` → all 15 tests (21 cases); `test_muse_host_records.py` → `test_no_request_or_settings_field_can_carry_an_approve_everything_value`; `test_muse_host_tools.py` → `test_no_muse_tool_offers_an_approval_launcher_or_directory_parameter` | C, S | Extra or missing wire members, a top-level `lastTurnId`, a non-v7 command id, or an approve-everything value | Exact member sets per method. The UUIDv7 version and variant bits are checked. |
| FR-1 reads, EC-105, EC-114 | `test_muse_host_reads.py` → all 11 tests | I | A dropped field, a wrong cursor, unbounded paging, or a retry loop on `session_not_loaded` | EC-114 asserts exactly one resume and one retry on the same peer. |
| EC-106, §9.1 | `test_muse_host_records.py` → the remaining 7 tests | C | A bad field accepted, or a mutable record | The message must name `<Record>.<field>`. |
| FR-5, §9.2 rows 29–40, AC-15, EC-138, EC-142, EC-144, EC-145 | `test_muse_host_tools.py` → all 13 tests (26 cases) | C | A wrong tool name, permission or parameter set, or WRITE tools running under the default policy | The real `ToolExecutor` and `PermissionPolicy()`. |

## Tests deliberately NOT written

### grok_host
- **Re-proving host-wide rows.** Rows EC-11 to EC-17 reached through the same short-lived `initialize` or `session/list` path are proved once per (function, code) where the function has its own path. These pairs are pruned because they re-prove the identical path already proved for a sibling function:
  - `run_grok_once` × EC-13 and EC-17: the model live-check peer, already proved for `spawn_grok_session`;
  - `fork_grok_session` × EC-17: proved for `list_grok_sessions`;
  - `list_grok_sessions` × EC-14 and EC-17: proved for `list_grok_models`;
  - `search_grok_sessions` × EC-14, EC-15 and EC-17: the same `session/list` path as `list_grok_sessions`;
  - `check_grok_ready` × EC-14, EC-15 and EC-17: the codes are already produced by EC-19, EC-21 and EC-18 on the same function.
- **The second EC-21 trigger** (a sign-in marker on `grok models` stderr). Same code, token and function as the stdout line.
- **EC-5 through a host method.** It needs an injected defect inside the host. It is proved at the factory, which every host method must use (§12.4), and at the tool base (EC-140).
- **EC-4's window between "prompt written" and "handle returned".** It cannot be hit deterministically. The windows before the prompt and during the wait are covered.
- **NFR-7 (spawn within 2 s).** It depends on the machine, so it would be flaky on a loaded CI runner. The functional AC-6 test covers that spawn does not wait for the turn.
- **The 240 s default `max_turn_seconds` of the one-shot tools.** Observing it needs a 240 s run or a mocked host. The EC-144 cap and its boundary are tested.
- **Windows process liveness.** §13 says Windows has no portable check. Windows runs assert outcomes and time bounds only.

### native_backends
- **EC-126 and EC-137.** No declared profile can reach them: both profiles allow `CLAUDE_CODE` and `OPENCODE`, and the profiles are not a §13 seam.
- **The order of the harness check and the feature check in `check_backend_compat`.** No profile both disallows a harness and lacks a feature.
- **EC-5 for each backend function.** It needs an injected defect. It is covered at the factory in grok_host.
- **Duplicates for `check_backend_ready`:** EC-127 on 403, EC-128 on 402, the other 10 EC-132 shapes, and the EC-131 read timeout. Each re-proves a `get_deepseek_balance` mapping that is already covered for that code.
- **Tool mode for 10 of the 11 EC-132 shapes.** The tool path is the same.
- **A wall-clock 15 s timeout test.** The deadline is read from the `AsyncClient` options instead.
- **A wrong-typed `request` argument to `check_backend_compat`.** No row specifies its code.

### opencode_host
- **EC-56 for each function.** A server that dies is proved at start-up and by EC-153 (`test_a_server_that_dies_between_calls_is_not_restarted`). Every function reaches the dead server through the same `HttpTransport` path that EC-55 already covers per function.
- **EC-58 on the abort body.** `abort` returns `200 true`, and the host checks the session first. A protocol error there re-proves the EC-58 path already covered by the `GET /session/{id}` row of `interrupt_opencode_turn`.
- **EC-62.** No declared backend profile can reach it, and the profiles are not a §13 seam.
- **EC-4's window between "prompt sent" and "handle returned".** It cannot be hit deterministically.
- **EC-140, EC-141, EC-143, EC-149 and the decision cap.** They live in the shared `NativeHostTool` base and hostkit, which grok_host proves once.
- **NFR-7 latency.** It depends on the machine.
- **Windows liveness of the owned server.** It has no portable check (§13). Windows asserts the exit bound only (`test_owned_server_exit_returns_within_the_bound`).
- **Where `agent`, `system` and `model` go in the spawn body.** §8.5 does not say. The continue body is tested (`test_continue_sends_the_model_agent_and_system_with_the_prompt`).
- **An empty `system` or a whitespace `provider_id`.** No row gives their outcome.
- **Tool-mode copies of the 128 EC-1 cases.** The tool path is proved by EC-138, which shares one argument check.

### muse_host
- **Pruned duplicates:**
  - EC-97 and EC-98 for every method of one function: each is proved once per function on its main method.
  - The extra variants of EC-102.
  - EC-111 with -32011 `notFound`: the same code and token as -32020, which the rows prove.
  - The other EC-119 kinds.
  - The extra EC-1 types already in grok_host.
- **EC-5.** It needs an injected defect, and is proved at the factory in grok_host.
- **EC-6, EC-7, EC-138 to EC-143 and EC-149.** The transport and the shared tool base are proved once in grok_host. `test_bad_muse_arguments_return_invalid_argument_naming_the_parameter` keeps the Muse-specific parameters.
- **EC-151 (the wall clock jumps), for every host.** No §13 seam moves the clock, and the rule "no wall clock" forbids patching `time`. The bounds tests would also fail if a deadline used the wall clock under load, but that is not a proof.
- **EC-4's window.** Same reason as grok.
- **AC-5 for Muse.** The host injects no secret of its own. `META_API_KEY` is the caller's variable, passed through `WSLENV` by name, and `test_wslenv_gets_no_key_entry_when_meta_api_key_is_unset` covers it.
- **These reap paths:**
  - the reap timing out or failing;
  - a mark mismatch;
  - the 26 s WSL stop bound.

  Reaching them needs a stuck distro, and a 26 s wall-clock test would be flaky.
- **`MuseLauncher` unit tests.** §8.5 names no method on it. It is covered through the host (`test_launch_argv_appends_only_serve_or_version`, `test_wsl_turn_peer_launch_workspace_overlay_and_reap`).
- **AC-10 with its literal settings.** These are `C:/w/repo` and `MuseUbuntu1`, and they need a real folder and the real distro, which the task forbids. The literal translation is proved by `to_wsl`, and the launch shape is proved with `VidbyteFakeDistro`.

## Red run

### Environment

The suite ran under the global Python 3.11.0 on win32. There was no `pip install`; the worktree was reached through `PYTHONPATH`.

```
$ PYTHONPATH=$(pwd) python -c "import vidbyte,inspect;print(inspect.getfile(vidbyte))"
<worktree>\vidbyte\__init__.py
$ python -m pytest --version
pytest 8.3.5            (pytest-asyncio 1.3.0, strict mode; httpx 0.28.1)
```

### Results

Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends -rfEs --tb=no`

```
94 failed, 19 skipped, 1522 errors in 16.48s        (1635 tests, 0 passed)
grok_host:       89 failed, 13 skipped, 356 errors   (458 tests)
opencode_host:    1 failed,  1 skipped, 579 errors   (581 tests)
muse_host:        4 failed,  5 skipped, 449 errors   (458 tests)
native_backends:                        138 errors   (138 tests)
```

Every error is a fixture that imports a missing feature module at setup. Every failure is the first assertion or call that reaches missing behaviour. No test errors at collection, and the whole suite still collects: `pytest --collect-only -q tests` reports `5604 tests collected`.

### Reasons, grouped (all 1616 non-skips)

| Count | Reason | Why it is the right reason |
|---|---|---|
| 1350 | `ModuleNotFoundError: No module named 'vidbyte.harnesses.native'` | The hosts, hostkit and backends do not exist yet. 1345 of these fail at fixture setup. The other 5 are module checks inside test bodies: 1 grok, plus 4 Muse `to_wsl` cases. |
| 63 | `ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.opencode'` | The opencode records are not written yet. |
| 35 / 27 / 23 | `AttributeError: module 'vidbyte.tools.toolsets' has no attribute 'OpencodeTools' / 'GrokTools' / 'MuseTools'` | The toolsets are not exported yet. |
| 15 | `ModuleNotFoundError: No module named 'vidbyte.lib.process'` | `CliRunner`, `ManagedProcess` and `ProcessStopper` do not exist yet. |
| 15 | `ModuleNotFoundError: No module named 'vidbyte.tools.builtins.harness_backends'` | The backend tools do not exist yet. |
| 10 | `AssertionError: Traceback …` | These are the AC-1 snippet (2), AC-20 (7 + reverse order) and fresh-interpreter runs. The child's stderr ends in `ModuleNotFoundError: No module named 'vidbyte.harnesses.native'`. |
| 10 / 9 / 9 | `AttributeError: 'McpStdioTransport' object has no attribute 'respond' / 'send_request' / 'notify'` | The transport extension is not written yet. |
| 9 / 9 / 5 / 2 | `TypeError: McpStdioTransport.request() got an unexpected keyword argument 'timeout_seconds'`; `__init__()` … `'exit_grace_seconds'` / `'stop_process_tree'` / `'on_message'` | The same. |
| 14 | `ModuleNotFoundError` for `vidbyte.lib.constants.native_hosts` (4), `.dataclasses.validation` (2), `.dataclasses.native_hosts` (2), `.enums.native_hosts` (2), `.dataclasses.grok`, `.dataclasses.process`, `.enums.harness_backends`, `.enums.process` | The shared records, enums and constants are not written yet. |
| 3 | `AttributeError: module 'vidbyte.lib.errors' has no attribute 'NativeHostError'` | The error type is not written yet. |
| 2 | `ModuleNotFoundError` for `vidbyte.tools.builtins.grok` and `vidbyte.tools.builtins.opencode` | These are module checks inside test bodies. |
| 1 | `AssertionError: assert [] == ['grok.not_in…t_found', ...]` | The 53 members are not appended yet. |
| 1 | `AssertionError: assert 120 >= (120 + 53)` | The same. |
| 1 | `AttributeError: GROK_NOT_INSTALLED` | The same. |
| 1 | `FileNotFoundError: … vidbyte\harnesses\native\__init__.py` | INV-19: the fixed file does not exist yet. |
| 1 | `AssertionError: []` | AC-18: the four toolset modules are not loaded by `import vidbyte` yet. |
| 1 | `McpProtocolError: MCP response result must be an object` | The dispatch bug the spec fixes: a server request with an `id` resolves a pending request. |

### Skips (19, all platform guards that the spec allows)

- 14 POSIX-only liveness or process-group checks: 11 in grok_host and 3 in muse_host. §13 says Windows has no portable check.
- 2 Windows async closed-pipe cases, EC-27 and EC-51. Windows reports a write to a closed pipe late.
- 1 Muse "no `muse_command` and no `wsl_distro`" case, which is win32-specific. The win32 path is EC-94 in `test_muse_host_wsl.py`.
- 1 Muse reap script, which needs `sh` and `/proc`.
- 1 POSIX-only opencode owned-server tree check.

On Linux CI all 19 run.

### Neighbours that must stay green, unedited

Command: `PYTHONPATH=$(pwd) python -m pytest -q tests/test_mcp_stdio_transport.py tests/test_mcp_studio_server.py tests/test_codex_failure_recovery.py tests/test_session_failures.py tests/test_http_transport_content_type.py tests/test_harness_redaction.py tests/features/coding_agent/test_coding_agent_contract.py`

Result: `171 passed in 4.15s`.

Note: earlier at HEAD the flake `test_cancelled_waiter_does_not_break_transport` failed once in 152. It is pre-existing and was not touched.

### Lint (run on the staged packs, since `lint/run.py` scans git-tracked files only)

- `python -m ruff check tests/features --config lint/ruff.toml` gives `All checks passed!`.
- `python lint/run.py --rule A001` gives no findings in the packs.
- `python lint/run.py` gives `SDK-LINT: PASS`.

## Notes for the implementer

### Shared
- **Read timing constants at call time.** The tests shrink stop timings by patching the attributes of `vidbyte.lib.constants.native_hosts`: `NATIVE_STOP_GRACE_SECONDS`, `NATIVE_KILL_WAIT_SECONDS` and `OPENCODE_POLL_INTERVAL_SECONDS`. Write `native_hosts.NATIVE_STOP_GRACE_SECONDS` when you need the value. A `from … import NATIVE_STOP_GRACE_SECONDS` binds at import time, so the patch is never seen and the bound tests time out.
- **Do not reconstruct the HTTP client.** HTTP goes through `HttpTransport`. The tests patch `vidbyte.lib.http.transport.httpx.AsyncClient`, so a client built any other way escapes the fake and the tests hit the network, which is refused.
- **Error shape.** `check_native_error` requires:
  - `failure_code is FailureCode.<MEMBER>`;
  - the row's token inside `next_step`;
  - the `operation`, when the row names one;
  - every context value is a `str`, and every key is from the §13 list.

  `check_tool_error` requires:
  - `metadata` keys `error`, `next_step`, `operation` and `harness`, with `hint == next_step`;
  - output exactly `"<code>: <message> Next step: <next_step>"`.
- **Records.** Construction errors must name `<Record>.<field>` in `str(error)`. A bool is never a number. A bare string is never an enum. Set fields become a `frozenset` of strings.
- **Catalog.** `NATIVE_HOST_NEXT_STEPS` is compared verbatim with §6.3.1, ignoring markdown backticks. Two cells end with an implementer note in parentheses:
  - `grok.turn_timed_out`: "(One-shot rows override this.)";
  - `backend.not_signed_in`: "(Rows put the backend's own variable first.)".

  Either form is accepted. The 53 members are appended after `RULE_EVALUATION_FAILED` in the §6.3.1 order. The 120 existing members are fingerprinted.
- **`import vidbyte` must load the four toolset modules** (`grok`, `opencode`, `muse` and `harness_backends`) and still start no process. The AC-18 probe fails if those modules are absent from `sys.modules`.
- **`native/__init__.py`** must hash to INV-19 after LF normalisation. Keep the file's bytes exact.

### Grok
- **Fake command.** The fake is `(sys.executable, "-u", fake_grok_peer.py, <scenario.json>)` as `grok_command`. The host appends `--version`, `models`, `agent --no-leader … stdio` or `--single=<prompt> …`. The fake picks its role from that argv. `models` and `agent` must be the first appended element. `--version` may be anywhere. A one-shot is recognised by `--single=`.
- **Name and value form.** Every caller value on a one-shot or fork argv must be a single `--flag=value` element. The prompt `--always-approve` must appear only as `--single=--always-approve`. Host-fixed flags (`--output-format json`, `--cwd`, `--permission-mode`) are accepted in either form.
- **AC-1 on Windows.** The shim is `grok.cmd` on a PATH that holds only the shim folder and System32. Resolve `grok` with `shutil.which`, which honours PATHEXT, and launch it so the `.cmd` runs. HOME and USERPROFILE both point at an empty folder, so `~/.grok/bin` holds nothing.
- **Readiness.** `GrokReadiness.version` is the bare semver (`"1.0.52"`) parsed from `grok 1.0.52 …`. The readiness peer must receive only `initialize`.
- **The transport dispatch fix** is observable today. `test_method_frames_are_dropped_without_a_callback` fails with `MCP response result must be an object` until a frame that has a `method` is never treated as a response.

### opencode
- **Missing sessions.** `abort` answers `200 true` and `diff` answers `200 []` even for a missing session. Call `GET /session/{id}` first to raise `session_not_found`.
- **Finding the turn's reply.** Take the baseline with `GET /session/{id}/message?limit=1` before `prompt_async`. Accumulate the parentID reply set across polls, because replies can leave the message window.
- **Owned server.** It must print its listening line. The fake prints noise lines first. The password is `secrets.token_urlsafe(32)`, put in the child's environment only and never in `os.environ`.

### Muse
- **Resolve `wsl.exe` with `shutil.which`.** System32 comes before PATH in `CreateProcess`, so a bare `"wsl.exe"` would launch the real one, and the fake `wsl.exe` would never be used.
- **EC-114.** The resume and the retry happen on the same short-lived peer.
- **Wire mistakes** come back from the fake as -32600 or -32602. Its `schema_violation` log names the member.
- **`MuseWire` parsers are static methods.** `MusePathTranslator.to_wsl` is a pure static method.
- **Stop order.** A turn peer's close runs the reap exactly once, with the caller's environment. The `wsl -l -q` list runs once, at `__aenter__`.

### Backends
- **Body overflow.** A body over 64 KiB arrives as `ProviderRequestError` with status 200, and maps to `backend.protocol_mismatch`.
- **Register the DeepSeek key** with the error factory before the request, so a body that echoes it is scrubbed.
- **Use `timeout_seconds=15.0`** and no redirects. GLM readiness builds no client.
- **Exact next steps.** EC-123 and EC-127 assert an exact next step that names one variable.

### Notes: S2 test fixes after S3 (commit `66d5c3bb`)

The S3 implementer found three test defects, and the coordinator confirmed them against spec r4. Each fix is test-only and changes no other assertion:
- **D-1.** `test_grok_host_records.py::test_validator_rejects_each_bad_value_naming_the_field` expected `require_enum_set` to refuse a plain set of members, `{AcpToolKind.EDIT}`. §9.1, EC-23, EC-134 and §16 S2-4 say that a `set` is converted. The row now uses a plain set holding the value string, `{"edit"}`, which is refused.
- **D-2.** `test_grok_host_process_helpers.py::test_cli_invocation_validates_and_hides_env_and_stdin` passed `argv` both by position and by keyword for the `argv` rows. `argv` now goes by keyword only, so every row reaches `CliInvocation`.
- **D-3.** `test_opencode_host_records.py::test_host_settings_reject_each_bad_field` passed `workspace` twice for the four `workspace-*` rows. `workspace` now goes by keyword, and a row's override replaces it.
- **D-4, D-5 and D-6** were found at S3 and fixed in commit `209c4085`:
  - **D-4.** The approve-everything guard in `test_grok_host_reads.py` matches a forbidden flag only as its own element or as a `--flag=` prefix. It no longer matches the suffix of another flag's value, so `--single=--always-approve`, the injection-safe form, holds.
  - **D-5.** The grok and Muse fakes name each log after a launch number they claim with an exclusive file create, and `records()` reads the logs in that order instead of PID order.
  - **D-6.** The expected opencode history ids now match the fake's shared counter: `msg_00000002` and `msg_00000004`, with part `prt_00000003`.

## Addendum r8 — S4 regression tests

The S4 review confirmed six failure paths (R-1, R-2, R-5, R-6, R-7, R-8) that no test guarded, plus the r8 INV-14/EC-157/EC-39 spec changes. This addendum adds one regression test per finding, binding to the r8 names. All new tests run through the §13 fakes; none reads `vidbyte/` source, sends a live prompt, or runs the real `grok`, `muse` or `wsl.exe`.

### Coverage map

| Finding / Spec ID | Test (file → name / row) | Level | Failure it catches | Why it cannot pass vacuously |
|---|---|---|---|---|
| R-1, EC-16, EC-41 | `test_grok_host_errors.py` → `test_grok_error_row[EC-16-spawn_grok_session-…-minus-32602-no-cursor]` and `[EC-16-list_grok_sessions-…-minus-32602-no-cursor]` (host + tool); `test_invalid_params_without_a_cursor_is_an_api_error_carrying_the_vendor_message` | C, R | A no-cursor `-32602` mapped to `grok.protocol_mismatch` with `vendor_error` dropped, instead of `grok.api_error` | The rows assert exact `grok.api_error` identity, `vendor_code == "-32602"` and a present `vendor_error`; the focused test asserts `"Invalid params"` is in `vendor_error`. The EC-41 cursor row still asserts `configuration.invalid_argument`, so the two paths are kept apart. Red now: the code returns `grok.protocol_mismatch`. |
| R-2, EC-157, D-19, T-2 | `test_grok_host_windows_launcher.py` → `test_grok_cmd_on_path_is_refused_at_aenter_and_never_runs[spawn_grok_session, run_grok_once]`, `test_explicit_batch_grok_command_is_refused_at_aenter[cmd, cmd-upper, bat, trailing-dot, trailing-space]` | S, I, R | A win32 batch Grok launcher is started, handing a prompt/model/rule to `cmd.exe` | win32-only. The shim writes a marker when it runs; the test asserts `__aenter__` raises `grok.not_installed` with EC-157's **exact** next step (which distinguishes it from EC-11's default text, same code and token) and that the marker is absent. The prompt and model carry `"&%^`. Red now: the host launches the `.cmd` (observed `grok.process_exited`). |
| R-5, NFR-2, EC-8 | `test_muse_host_process_bounds.py` → `test_aexit_returns_within_the_bound_when_a_peer_is_silent_on_decide` | X, I, R | `MuseHost.__aexit__` waits `control_timeout_seconds` for a peer silent on `approval/decide` | The decide is confirmed in-flight (`wait_until` on `received("approval/decide")`) before exit; `control_timeout_seconds=6.0` is set well above the NFR-2 bound `grace + (grace + 2·kill_wait) + slack = 3.6 s`. The timing assertion is first, so it fails on the stated reason. Red now: measured `__aexit__` = 6.02 s. |
| R-6, INV-10, INV-13, EC-87, EC-59 | `test_opencode_host_watcher.py` → `test_a_single_non_counted_poll_failure_aborts_before_failing_the_turn[session_status, permission_list]` | I, R | One 500 poll (EC-59, not counted by EC-87) fails the turn with no `POST …/abort`, orphaning the server turn | The turn is `plan("hold")` so the single 500 is reached; the abort is asserted inside the `async with` (before `__aexit__`, which sends none for an already-failed turn) as exactly `[handle.session_id]`; `wait` must still raise `opencode.api_error`. Red now: `aborts == []`. |
| R-7, §9.3, D-18 | `test_muse_host_wsl.py` → `test_read_peer_forwards_meta_api_key_through_wslenv` | I, R | A WSL short-lived read peer omits `META_API_KEY/u` from `WSLENV` | win32-only, over the `make_wsl_host` fake `wsl.exe`. `META_API_KEY` and `WSLENV` are set; the read peer's logged `WSLENV` must keep the caller's entries first and contain `META_API_KEY/u`. No real key is used (placeholder). Red now: the read peer's `WSLENV` is `WT_SESSION:WT_PROFILE_ID` only. |
| R-8 (i), INV-14, EC-29 | `test_grok_host_session_id_case.py` → `test_continue_on_the_upper_cased_id_of_a_live_session_is_busy` | X, R | The Grok busy check compares ids case-sensitively | A held turn on `KNOWN`, then a continue on `KNOWN.upper()`; must raise `grok.session_busy` (token `interrupt_grok_turn`) with one peer started. Red now: `DID NOT RAISE` (a second peer resumes the upper-cased id). |
| R-8 (i, Muse), INV-14, EC-112 | `test_muse_host_turns.py` → `test_continue_on_the_upper_cased_id_of_a_live_session_is_busy` | X, R | The Muse busy check compares ids case-sensitively | A held turn on `KNOWN`, then a continue on `KNOWN.upper()`; must raise `muse.session_busy` (token `interrupt_muse_turn`) with one `turn/start`. Red now: raises `muse.session_not_found`. |
| R-8 (ii), INV-14, EC-35 | `test_grok_host_session_id_case.py` → `test_fork_on_the_upper_cased_source_id_is_accepted` | C, R | The fork source listing check is case-sensitive | The default listing holds `KNOWN` (lower); a fork on `KNOWN.upper()` must find it and run the CLI once, with a new session id. Red now: raises `grok.session_not_found`. |
| R-8 (iii), INV-14, EC-36 | `test_grok_host_session_id_case.py` → `test_fork_new_session_id_that_collides_case_insensitively_is_refused` | C, R | The new-id collision check is case-sensitive | `new_session_id=OTHER.upper()` collides with the listed `OTHER`; must raise `configuration.invalid_argument` (token `new_session_id`) before the CLI run. Red now: `DID NOT RAISE` and the CLI runs. |
| R-8 (iv), INV-14, EC-39 | `test_grok_host_session_id_case.py` → `test_fork_accepts_a_returned_id_equal_to_the_request_ignoring_case` | C, **lock** | A returned id equal to the request only by case is wrongly refused | Lock: already green. The EC-39 target comparison is already case-insensitive in the current code, so the caller's `NEW.upper()` and the echoed `NEW_SESSION` match and the fork succeeds. It locks that against regression. |
| R-8 (v), EC-39 | `test_grok_host_session_id_case.py` → `test_fork_refuses_a_returned_id_that_differs_from_the_request` | C, **lock** | The EC-39 target-mismatch guard is dropped | Lock (the one the brief names): a returned id that differs from `new_session_id` even ignoring case must raise `grok.protocol_mismatch` (token `check_grok_ready`). Green now and after the fix; the guard is kept, not dropped. |

Grant (a): `test_grok_host_acceptance.py::test_snippet_prints_completed_text_when_grok_is_the_fake` on win32 now reaches the fake through `grok_command` (the §13 seam), because EC-157 refuses the `grok.cmd` shim. Its three assertions are unchanged; see "Granted test changes" below.

### Tests deliberately NOT written (r8)

- **R-8 EC-32 case-insensitive equality** (`new_session_id` equal to `session_id` ignoring case). Covered in substance by R-8 (iii) for EC-36 and by the same INV-14 rule; empirically it may already be handled (it would then be a second lock test). Per the brief it is omitted to avoid a near-duplicate. The INV-14 case rule it would exercise is already driven by (i)–(iii).
- **R-2 case (iii): the fallback to `~/.grok/bin/grok.exe` when a PATH `grok.cmd` is shadowed.** Not written. `__aenter__` starts no process, so the only way to observe which program the fallback resolved is to run a turn through a real, runnable `grok.exe` ACP peer at that path. The §13 seam provides a fake only through `grok_command` (an argv prefix), not through a resolved `grok.exe` on disk; a real `.exe` peer (e.g. via pip's bundled distlib launcher, as the Muse WSL fake does) would add a brittle dependency for a branch whose refusal half is already covered by cases (i) and (ii). A minimal "`__aenter__` does not raise when `grok.exe` exists" check is not red, because `__aenter__` succeeds under both the current code and the fix. Recorded as an OPEN ITEM for the repair agent: the fallback-selects-`grok.exe` branch has no regression test.

### Red run (r8)

Environment: global Python 3.11.0 on win32, reached through `PYTHONPATH`; `pytest 8.3.5` (pytest-asyncio 1.3.0, strict). Command:

```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
…
20 failed, 1618 passed, 19 skipped in 158.00s (0:02:37)
```

The 20 failures are exactly the 20 new non-lock tests (5 for R-1, 7 for R-2, 1 for R-5, 2 for R-6, 1 for R-7, 1+3 for R-8 across Grok and Muse). The two EC-39 locks pass. Every pre-existing test passes (1618 includes the grant-(a) test and the two locks). The 19 skips are the platform guards (POSIX-only liveness/process-group checks skip on win32); on Linux CI the win32-only R-2 and R-7 tests skip instead. Each failure's reason, verified from the traceback:

| Tests | Observed red reason |
|---|---|
| R-1 (5) | `grok.protocol_mismatch` where `grok.api_error` is required |
| R-2 (7) | `grok.process_exited` (the `.cmd` was launched) instead of an EC-157 refusal at `__aenter__` |
| R-5 (1) | `__aexit__` waited 6.02 s; NFR-2 bounds it at 3.60 s |
| R-6 (2) | `aborts == []`: no `POST …/abort` before the turn fails |
| R-7 (1) | read-peer `WSLENV` is `['WT_SESSION','WT_PROFILE_ID']`, no `META_API_KEY/u` |
| R-8 Grok (i) | `DID NOT RAISE` `grok.session_busy` for the upper-cased id |
| R-8 Grok (ii) | `grok.session_not_found` for the upper-cased source |
| R-8 Grok (iii) | `DID NOT RAISE` `configuration.invalid_argument`; the CLI runs |
| R-8 Muse (i) | `muse.session_not_found` instead of `muse.session_busy` |

Lint on the staged packs: `python lint/run.py` → `SDK-LINT: PASS` (S062 held at 889 after the EC-157 next step was written as one literal; S061 improved 6→5).

### Granted test changes (before → after)

Only grant (a) is used (AC-1's win32 branch moves to the §13 seam, per spec §12.3 r8 and D-19). No existing test's **assertions** change. CI-1's `test_interrupt_raises_process_exited_when_the_cancel_write_fails` is untouched.

`run_snippet` gained an optional keyword and one body line:

Before:
```python
def run_snippet(tmp_path: Path, path_entries: list[str]) -> subprocess.CompletedProcess[str]:
    …
    snippet = tmp_path / "snippet.py"
    snippet.write_text(SNIPPET, encoding="utf-8", newline="\n")
    env = dict(os.environ)
```
After:
```python
def run_snippet(tmp_path: Path, path_entries: list[str], *, grok_command: tuple[str, ...] | None = None) -> subprocess.CompletedProcess[str]:
    …
    snippet = tmp_path / "snippet.py"
    # r8 grant (a): on win32 the §4 snippet reaches the fake through GrokHostSettings.grok_command, because EC-157 refuses a .cmd shim.
    body = SNIPPET if grok_command is None else SNIPPET.replace("GrokHostSettings(workspace=Path.cwd())", f"GrokHostSettings(workspace=Path.cwd(), grok_command={tuple(grok_command)!r})")
    snippet.write_text(body, encoding="utf-8", newline="\n")
    env = dict(os.environ)
```

`test_snippet_prints_completed_text_when_grok_is_the_fake` — the setup branches on platform; the three assertions are byte-for-byte unchanged:

Before:
```python
    shim_folder = tmp_path / "shim"
    shim_folder.mkdir()
    scenario_path = tmp_path / "snippet-scenario.json"
    scenario_path.write_text(json.dumps(grok_fake.scenario()), encoding="utf-8")
    write_grok_shim(shim_folder, scenario_path)
    completed = run_snippet(tmp_path, [str(shim_folder), *system_folders()])
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "completed alpha-beta", completed.stdout + completed.stderr
    assert grok_fake.received("session/prompt"), "the snippet's prompt reached the fake, not a real grok"
```
After:
```python
    scenario_path = tmp_path / "snippet-scenario.json"
    scenario_path.write_text(json.dumps(grok_fake.scenario()), encoding="utf-8")
    if sys.platform == "win32":
        # r8 grant (a) / AC-1: EC-157 refuses a grok.cmd shim, so win32 reaches the fake through the §13 seam; only System32 is on PATH.
        command = (sys.executable, "-u", str(FAKE_GROK), str(scenario_path))
        completed = run_snippet(tmp_path, system_folders(), grok_command=command)
    else:
        shim_folder = tmp_path / "shim"
        shim_folder.mkdir()
        write_grok_shim(shim_folder, scenario_path)
        completed = run_snippet(tmp_path, [str(shim_folder), *system_folders()])
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "completed alpha-beta", completed.stdout + completed.stderr
    assert grok_fake.received("session/prompt"), "the snippet's prompt reached the fake, not a real grok"
```

The POSIX path still writes `grok` on PATH, so AC-1 holds unchanged there; `write_grok_shim` keeps its win32 branch but is no longer reached by this test on win32. The second AC-1 outcome (`test_snippet_prints_not_installed_line_when_no_grok_exists`) is unchanged.

## Addendum 2 — re-review round 1 regression tests

The post-repair re-review confirmed two Majors with no regression test (`review.md`, "Post-repair re-review round 1"):
- **R-16 (INV-14, §8.5 `NativeTurnTable.reserve`).** The busy check missed a session id that the vendor itself returned in upper case.
- **R-17 (§9.1 `NativeApprovalDecision.title` "scrubbed", INV-6).** Grok and Muse recorded approval titles without scrubbing them.

This addendum adds 11 test cases in 5 functions, bound to the r8 names. They run through the §13 fakes (`grok_command`, `muse_command`) as real child processes. No `vidbyte/` source was read. No real `grok`, `muse` or `wsl.exe` ran. No existing assertion changed, and no fixture changed: every scenario uses keys the fakes already read (`acp.session_new.result`, `acp.session_list.pages`, `acp.session_prompt.permissions[].title`, `new_session_id`, `sessions`, `turn.approvals[].tool_name`, `turn.user_inputs[].tool_name`).

### Coverage map

| Finding / Spec ID | Test (file → name [params]) | Level | Failure it catches | Why it cannot pass vacuously |
|---|---|---|---|---|
| R-16, INV-14, EC-29 | `grok_host/test_grok_host_session_id_case.py` → `test_continue_on_a_live_session_whose_vendor_id_is_upper_case_is_busy[handle-id, lower-cased-handle-id]` | X, R | Grok's `session/new` returns `ABCDEF01-…`. Spawn binds it verbatim, so a continue by `handle.session_id` (or by its lower-case form) starts a second live turn on the session. | It first asserts that the bound id, lower-cased, equals the scenario's id. The fake's default id is a random lower-case uuid4, so this check fails if the scenario did not apply. It then needs `grok.session_busy`, the token `interrupt_grok_turn` and the operation. Exactly one `peer` launch and one `session/prompt` must be logged. The handle id's case is never pinned, so either R-16 fix passes. A control copy with a lower-case vendor id passes against the current code, which proves the red comes from letter case alone. |
| R-16, INV-14, EC-34 | `grok_host/test_grok_host_session_id_case.py` → `test_fork_of_a_live_session_whose_vendor_id_is_upper_case_is_busy[handle-id, lower-cased-handle-id]` | X, R | A fork of the live session skips its busy check, lists the session and runs the paid fork CLI. | The scenario lists the vendor id in Grok's own spelling, so a missed busy check really reaches the CLI; it does not stop at `grok.session_not_found`. The test needs `grok.session_busy` from `fork_grok_session`, no `oneshot` launch and exactly one `peer` launch. That last check means the busy row must fire before the listing peer starts ("before anything is sent"). The lower-case control passes. |
| R-16, INV-14, EC-112 | `muse_host/test_muse_host_turns.py` → `test_continue_on_a_live_session_whose_vendor_id_is_upper_case_is_busy[handle-id, lower-cased-handle-id]` | X, R | Muse's `session/start` returns `0192F0C4-…`, and a continue by the handle's id (or its lower-case form) starts a second turn. | The vendor id differs from the fake's default `new_session_id`, so the bound-id check fails if the scenario did not apply. `sessions` lists both spellings, as a Muse that matches ids ignoring case would, so a missed check really starts a turn; it does not stop at `muse.session_not_found`. The test needs `muse.session_busy`, the token `interrupt_muse_turn`, one `peer` start and one `turn/start`. The lower-case control passes. |
| R-16, INV-14, EC-112 (fork) | `muse_host/test_muse_host_turns.py` → `test_fork_of_a_live_session_whose_vendor_id_is_upper_case_is_busy[handle-id, lower-cased-handle-id]` | X, R | `fork_muse_session` of the live session skips the local live-turn check and forks it. | It needs `muse.session_busy` from `fork_muse_session`, no `session/fork` frame and one `peer` start, matching the existing EC-112 `fork_busy` row (`peer_launches=1`). The lower-case control passes. |
| R-17, §9.1, INV-6 | `grok_host/test_grok_host_turns.py` → `test_a_credential_in_a_permission_title_is_scrubbed_from_the_result_and_the_wait_tool` | S, R | A permission titled `Run: export OPENAI_API_KEY=<sk-proj-FAKE+uuid4 hex> && make deploy` is recorded verbatim and reaches `wait_grok_turn`'s output. | The value is generated per test, so no key literal is committed. The test first asserts that exactly one `acp.permission:execute` decision was recorded and that the tool succeeded. The value must then be absent from the decision title, the tool output and the tool metadata, and the title must contain `<redacted>`, so a fix that drops the title does not pass. Assertion messages name only the surfaces that leaked. A scratch control applied `NativeErrorFactory.scrub` and then the cap to the recorded title, and got `Run: export OPENAI_API_KEY=<redacted> && make deploy`, which meets every assertion. The plain-title case is already pinned at `test_grok_host_turns.py:64` and is not duplicated. |
| R-17, §9.1, INV-6 | `muse_host/test_muse_host_turns.py` → `test_a_credential_in_a_request_title_is_scrubbed_from_the_result_and_the_wait_tool[approval-requested, user-input-requested]` | S, R | A credential in the `toolName` of `approval/requested` or `userInput/requested` is recorded verbatim (the two record sites) and reaches `wait_muse_turn`'s output. | The checks are the same as the Grok test's, once per request kind: one decision of the expected `request_kind`, the value absent from the title, the tool output and the metadata, and `<redacted>` present. The scrub-and-cap control gives `shell OPENAI_API_KEY=<redacted>` for both kinds. |

### Tests deliberately NOT written (addendum 2)

- **The opencode twin of R-16.** INV-14 says opencode `ses…` ids are compared exactly, and the R-16 fix must keep them exact. The brief scopes R-16 to Grok and Muse, so no opencode test was added. No existing test pins the exact comparison either: `opencode_host` has no case-variant test. A repair that folded case for every harness would therefore still pass all four packs. This is recorded as an open item.
- **R-M10 (a child session's 404 during the opencode tree walk) and R-M11 (spec ids in file headers).** The orchestrator decided against tests for both: R-M10 is a follow-up that needs a spec sentence first, and R-M11 changes text only.
- **A title near the 200-character cap with the secret across the boundary.** This would pin the scrub-then-cap order, which is a mechanism, not a §9.1 outcome. The brief says not to test the mechanism.

### Red run (addendum 2)

The environment is global Python 3.11.0 on win32, reached through `PYTHONPATH`, with `pytest 8.3.5`. HEAD is `341cf6fb`, and the new tests are staged.

```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
…
11 failed, 1638 passed, 19 skipped in 149.26s (0:02:29)
```

The 11 failures are exactly the 11 new cases. 1638 passed is the baseline, unchanged, so every existing test still passes. The 19 skips are the same platform guards. Each reason was checked in the traceback:

| Tests | Observed red reason |
|---|---|
| R-16 Grok continue (2), Grok fork (2), Muse continue (2), Muse fork (2) | `Failed: DID NOT RAISE NativeHostError`. The second turn or the fork went ahead on the live session. |
| R-17 Grok (1), Muse (2) | `AssertionError: INV-6: the credential leaked into ['decision title', 'tool output']` |

Lint ran on the staged files: `python lint/run.py` → `SDK-LINT: PASS`. A007 stays at 255, S062 at 889 and S024 at 25.

## Addendum 3 — RACE-1 regression tests

Remote CI run 38437336454 flaked once on Linux 3.11 in `test_interrupt_answered_interrupted_or_cancelled_counts_as_success[interrupted]`, with "The Muse Code process stopped before it answered." The verifier confirmed a class of races (`review.md`, "Post-SOUND finding — interrupt racing completion (RACE-1)"). In each one, an interrupt or steer raises a spurious "process exited" error, because the turn's own end beat it and the host's driver closed the peer:
- **R-18 (Muse, Major).** `turn/completed` reaches the host before the `turn/interrupt` answer, or the answer never comes.
- **R-19 (Grok, Minor).** Grok answers `end_turn` while `session/cancel` is still being drained.
- **R-20 (Grok, Minor).** The host reports `was_running=True` for an answered turn whose driver is still closing the peer.
- **R-21 (Muse, Minor).** A steer loses the same race.

The expected outcomes were decided by the orchestrator (INV-13, EC-52, EC-53, EC-115). An interrupt the host sent to a turn it found running returns `was_running=True` and raises nothing, and the recorded terminal state stands. An interrupt that finds the turn already answered sends nothing and returns `False`. EC-51, EC-96 and EC-97 still raise.

This addendum adds 10 test cases in 7 functions: 8 red cases and 2 green guards. It also adds one fake knob and makes one granted scenario change to an existing test. The tests bind to the spec names, plus the R-19 seam names that the verifier's prototype used: `NativePeer.notify` from `vidbyte.harnesses.native.hostkit`, and `asyncio.wait_for`. They run through the §13 fakes as real child processes. No `vidbyte/` source was read, and no real `grok`, `muse` or `wsl.exe` ran. No existing assertion changed, and no fake default changed.

### Coverage map

| Finding / Spec ID | Test (file → name [params]) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| R-18, INV-13, EC-52 | `muse_host/test_muse_host_turns.py` → `test_interrupt_that_loses_to_turn_completed_succeeds` | X, R | The turn is held, and the fake never answers `turn/interrupt` but ends the turn `cancelled` because of it. The driver closes the peer while the call is pending → `interrupt_muse_turn` raises `muse.process_exited` (reason `closed`). | It uses existing knobs only. The scenario differs from the EC-97 row (`test_muse_host_errors.py:364`) only by the absence of `on_interrupt: "ignore"`, and that row must still raise `muse.server_unreachable`. The test needs `was_running is True`, INTERRUPTED with `stop_reason == "cancelled"` and source CALLER, and exactly one `turn/interrupt`. So a fix that sends nothing, or reports `False`, fails it. A raise becomes a `pytest.fail` that names the code and the reason. |
| R-18, INV-13 (the CI frame order) | `muse_host/test_muse_host_turns.py` → `test_interrupt_answered_after_turn_completed_succeeds[minus-32013, minus-32014, minus-32030, accepted]` | X, R | The fake writes `turn/completed` first and then the answer, whatever the answer is → `muse.process_exited` today. If a host read the -32030 answer before its close, it would raise `muse.api_error` instead; the same assertion catches that. | It first asserts that the fake logged exactly one `interrupt_order` record with `completed_sent=True`. That proves the knob was read, and that this turn's own `turn/completed` went out before the answer: a foreign turn's completion never sets the event. The outcome assertions are the same as the row above. |
| R-18 guard, EC-102 | `muse_host/test_muse_host_turns.py` → `test_interrupt_rejected_with_32030_while_the_turn_still_runs_raises_api_error` | C, R, **guard** | A fix keyed on the answer code (-32030), or on `running`, instead of on this turn's own `turn/completed` silently swallows a real rejection of a running turn. | It is green today and must stay green. It needs `muse.api_error`, token `vendor_error`, operation `interrupt_muse_turn` and `vendor_code == "-32030"`. It also asserts that the fake sent no `turn/completed` at all, which proves the turn was still running when the answer arrived. No existing test covered -32030 on a running interrupt: the pack has only the EC-96, EC-97 and EC-115 interrupt rows. |
| R-18 (c), §6.3.5 `interrupt_muse_turn` | `muse_host/test_muse_host_turns.py` → `test_interrupt_answered_interrupted_or_cancelled_counts_as_success[interrupted, cancelled]` (granted scenario change) | C, **existing** | The CI flake itself. Without `order`, the fake set `interrupt_event` before answering, so the turn thread could write `turn/completed` first, and the test then tested the race instead of the -32013/-32014 mapping. | With `"order": "answer_first"`, the answer is written before the turn thread may end the turn. Every run therefore tests the mapping, and the race belongs to the two R-18 tests above. It is green before and after the fix, 5 of 5 here. |
| R-19, INV-13, EC-53 | `grok_host/test_grok_host_turns.py` → `test_interrupt_whose_cancel_write_loses_to_the_turn_end_succeeds` (fixture `cancel_drain_gate`, in the same file) | X, R | The cancel frame is in the pipe and Grok answers `end_turn`. The driver closes the peer before the cancel's drain finishes, so the post-drain check fails the write → `grok.process_exited` (reason `stdin_write_failed`), although the fake did receive the cancel. | No frame order through the fake can force this window, so a delegating seam does. When `NativePeer.notify` is called for `session/cancel`, the seam releases the held prompt. It then delays only that task's next `asyncio.wait_for` until the fake logs stdin `eof`, and then calls the real `wait_for`. Nothing is replaced. The test asserts two seam preconditions (`engaged`, `peer_closed_in_window`), so a seam that no longer engages fails loudly instead of passing. It then needs `was_running is True`, exactly one `session/cancel`, and COMPLETED with `end_turn` and no interrupt source. EC-51's POSIX test (`close_stdin_hold`: no answer, the peer stopped reading) stays the guard that a real peer failure still raises. |
| R-20, EC-52 | `grok_host/test_grok_host_turns.py` → `test_interrupt_after_grok_answered_while_the_driver_is_still_closing_sends_nothing` | X, R | Grok answered `end_turn`, and the fake ignores stdin EOF, so the driver sits in its close for the grace period. The interrupt sends nothing but returns `was_running=True` today. | It polls `grok_fake.records("eof")` every 10 ms, for at most 5 s. That record exists only once the host has closed the peer's stdin after the answer, and the fake then stays alive, so the driver is still closing for at least `NATIVE_STOP_GRACE_SECONDS` (0.3 s with `fast_stop`). It needs `was_running is False`, no `session/cancel`, and COMPLETED/`end_turn`. |
| R-20 Muse twin, EC-52 | `muse_host/test_muse_host_turns.py` → `test_interrupt_after_turn_completed_while_the_driver_is_still_closing_sends_nothing` | X, **guard** | It guards Grok/Muse parity in the same window: a Muse fix must not start sending `turn/interrupt` to a completed turn whose driver is closing. | It is green today and must stay green. It uses the same `eof` poll. It needs `was_running is False`, no `turn/interrupt`, and COMPLETED with no interrupt source. |
| R-21, EC-115 | `muse_host/test_muse_host_turns.py` → `test_steer_that_loses_to_turn_completed_raises_turn_not_found` | X, R | The fake is silent on `turn/steer`, and the test releases the turn while the steer is pending. The driver closes the peer after `turn/completed` → `muse.process_exited` (token `check_muse_ready`) instead of EC-115's `muse.turn_not_found`. | The steer runs as a task, and the release happens only once the fake has logged `turn/steer` (a bounded 10 ms poll), so the steer is pending when the turn ends. The test needs `muse.turn_not_found`, token `continue_muse_session` and operation `steer_muse_turn`, and the turn must record COMPLETED. The EC-96 and EC-97 steer rows in `test_muse_host_errors.py` still need `process_exited` and `server_unreachable` for a real exit or silence. |

### Tests deliberately NOT written (addendum 3)

| Candidate | Why it would not earn its keep |
|---|---|
| An opencode twin of any RACE-1 test | Decided out of scope. The verifier found opencode not affected: there is no peer to close, and abort answers `200 true` for an idle session. |
| A Grok twin of the -32030 guard | `session/cancel` is a notification and gets no answer, so Grok has no answer code a fix could key on. EC-51 is the Grok guard. |
| A second EC-51, EC-96 or EC-97 test | Those rows already exist (`test_grok_host_turns.py`, POSIX-only; `test_muse_host_errors.py:363-364` and the steer rows) and must stay green unchanged. A copy would prove nothing new. |
| R-21 with the steer answer written after `turn/completed` | That would need an `order` knob on `turn/steer`. The brief grants one fake extension (the interrupt knob), and the -32030-after-finish steer path is EC-115's own third clause, which the R-21 fix leaves as it is. |
| Asserting which exception fired inside R-19 (`BrokenPipeError` from the post-drain check, or an error from the drain itself) | That is a mechanism, and it differs by version: CPython 3.11 wraps the drain in a task and 3.12+ does not, while Windows Proactor raises in the drain. The test asserts outcomes only. |
| A unit test of the fake's `order` knob | The knob is proven where it is used. R-18 (b) asserts the `interrupt_order` record with `completed_sent=True`, and R-18 (c) turns a CI flake into 5 of 5 green runs. |
| Re-checking `driver.done()` after the opencode probe (the verifier's optional hardening) | It is not a finding and not in scope. |

### Red run (addendum 3)

Bootstrap: none. The environment is global Python 3.11.0 on win32, reached through `PYTHONPATH=$(pwd)`, with `pytest 8.3.5` and pytest-asyncio 1.3.0 in strict mode. No `pip install` ran. HEAD is `05d45151`, and the new tests are staged.

```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
…
8 failed, 1651 passed, 19 skipped in 155.03s (0:02:35)
```

The 8 failures are exactly the 8 new race cases. The 1651 passes are the 1649 baseline plus the two new guards, so every existing test still passes, including the two R-18 (c) cases. The 19 skips are the same platform guards; EC-51's test is among them on this Windows host.

**Determinism.** The new tests and R-18 (c) ran 5 times alone, with `-k "loses_to or answered_after_turn_completed or rejected_with_32030 or still_closing or interrupt_answered_interrupted_or_cancelled"`. Every run gave `8 failed, 4 passed`, and the reasons were identical in all 5 runs:

| Test | Runs | Observed red reason (or green) |
|---|---|---|
| R-18 (a) `test_interrupt_that_loses_to_turn_completed_succeeds` | 5 / 5 red | `Failed: INV-13: interrupt_muse_turn raised muse.process_exited (reason 'closed') …` |
| R-18 (b) `test_interrupt_answered_after_turn_completed_succeeds` ×4 | 20 / 20 red | the same, for -32013, -32014, -32030 and accepted |
| R-19 `test_interrupt_whose_cancel_write_loses_to_the_turn_end_succeeds` | 5 / 5 red | `Failed: INV-13: interrupt_grok_turn raised grok.process_exited (reason 'stdin_write_failed') …` |
| R-20 `test_interrupt_after_grok_answered_while_the_driver_is_still_closing_sends_nothing` | 5 / 5 red | `AssertionError: EC-52: Grok had answered, so the turn was finished and nothing is sent` (`was_running` is True) |
| R-21 `test_steer_that_loses_to_turn_completed_raises_turn_not_found` | 5 / 5 red | `expected muse.turn_not_found, got muse.process_exited` |
| R-18 (c) `…counts_as_success[interrupted, cancelled]` | 10 / 10 green | — |
| R-18 guard (-32030 on a running turn) | 5 / 5 green | — |
| R-20 Muse twin | 5 / 5 green | — |

**Can the tests pass?** In a scratch folder outside the worktree (nothing committed), a shim loaded both packs' conftests and the unchanged test modules. It applied the verifier's proposed-fix monkeypatches from `test_fix_probe_{muse,grok}.py`: the `_completed` guard in `MuseTurnDriver.interrupt`, and `GrokTurnDriver.ended` with its two uses. Over 5 runs, every R-18 (a), R-18 (b), R-18 (c), R-19 and R-20 case passed 5 of 5, and so did both guards. So did the EC-96, EC-97 and EC-115 `interrupt_muse_turn` rows (host and tool) and the existing Grok interrupt tests. The R-19 precondition assertions held, so the seam engaged and saw the peer close in every run. R-21 stayed red, because the probes carry no steer fix. Its passing was not checked.

**Lint.** `python lint/run.py` on the staged files gave `SDK-LINT: PASS`. A001 (643), A007 (255), S062 (889) and S024 (25) stay at their baselines.

### Granted test changes (before → after)

Only R-18 (c) is used: the scenario dict of `test_interrupt_answered_interrupted_or_cancelled_counts_as_success` (`test_muse_host_turns.py`) gains `"order": "answer_first"`. Its comment and its two assertions are byte-for-byte unchanged.

Before:
```python
    scenario = {"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"error": {"code": code, "message": "already stopping"}}}}
```
After:
```python
    scenario = {"turn": {"mode": "hold"}, "msp": {"turn/interrupt": {"order": "answer_first", "error": {"code": code, "message": "already stopping"}}}}
```

The fake extension in `fake_muse_peer.py` adds three things:
- `MspPeer.completed_sent`, a `threading.Event`;
- `TurnWorker.send_completed`, which sets that event after writing a `turn/completed` whose `turnId` is the ack's own turn;
- the `order` branch in `MspPeer.turn_interrupt`, which logs an `interrupt_order` record.

With `order` absent, the fake runs the same statements in the same order as before (it sets `interrupt_event`, then calls `step`), so no other test changes behavior. The 1649 baseline passes unchanged.

### Notes for the implementer (addendum 3)

- **The bound names and outcomes:**
  - `interrupt_muse_turn` and `interrupt_grok_turn` return `NativeInterruptResult.was_running`, and `steer_muse_turn` raises `muse.turn_not_found` (token `continue_muse_session`, operation `steer_muse_turn`).
  - `wait_*_turn` returns `NativeTurnResult.status`, `stop_reason` and `interrupt_source`.
  - The fake's `msp["turn/interrupt"]["order"]` and its `interrupt_order` log record are part of the test contract.
- **The R-19 seam depends on two paths staying as they are.** The host must send `session/cancel` through `NativePeer.notify`, in the task that called `interrupt_grok_turn`, and the transport must await the cancel's drain through `asyncio.wait_for` in that same task. The verifier's smallest fix (`GrokTurnDriver.ended`, plus `except NativeHostError: if not self.ended: raise` around the cancel write) keeps both. If a different fix sends the cancel from another task, or stops using `asyncio.wait_for`, the test fails with a message that starts with `seam:`. That means the window is no longer forced. It does not mean the fix is wrong, so ask the orchestrator; do not edit the test.
- **What must not change:**
  - EC-51 (Grok, POSIX), EC-96 and EC-97 (Muse, interrupt and steer) must still raise: their peer stopped before the vendor reported the turn's end.
  - A -32030 answer to a turn that Muse has not ended must still raise `muse.api_error`.
  - Key the Muse fix on this turn's own `turn/completed` having been read, not on `running` and not on the answer code.
- **The R-19 seam is a delegating wrapper, not a mock.** It wraps `NativePeer.notify` (hostkit) and `asyncio.wait_for`, and it always calls the real function. It patches no host class, `McpStdioTransport`, `HttpTransport` or `CliRunner`. This is the one place where the packs wrap an internal seam; it is narrow and deliberate.
- **A spec observation, with no change requested.** §6.3.5 lists EC-96 and EC-97 as host-wide rows for `interrupt_muse_turn`, with EC-115 for a foreign handle. The R-18 guard relies on EC-102 through §6.3.2's catch-all ("Any other JSON-RPC error"), as the review and the brief decided.

## Addendum 4 — post-S6 regression tests (R-22, R-24)

The S6 PR author noted one gap, and the post-S6 verifier found a second of the same class (`review.md`, "Post-S6 findings"). Both are Minors. No error is lost, but asyncio logs an ERROR with a traceback when an object that holds an unread exception is collected.
- **R-22 (Muse).** A failed turn that nobody waits on leaves its driver task's exception unretrieved, so asyncio logs "Task exception was never retrieved". Grok and opencode retrieve it when the turn finishes.
- **R-24 (Grok).** A host closed while a spawn is starting leaves the `session/prompt` answer future's exception unretrieved, so asyncio logs "Future exception was never retrieved".

This addendum adds 2 test functions, one per finding. Both are red against today's code, and the red is an assertion failure. They use only the public API and the §13 fakes, run as real child processes (`muse_command`, `grok_command`). They add no private seam, no fake change and no fixture change. No `vidbyte/` source was read, and no real `grok`, `opencode`, `muse` or `wsl.exe` ran. No existing assertion changed. As in addendum 3, each pack's FEATURE.md gained a failure-mode line, a regression line and a suite-map mention, and each README.md gained a log line.

Both tests read asyncio's own log record, and that record appears only when the object is collected. Each test therefore takes the same three steps:
1. Run `gc.collect()`, set `caplog` to ERROR for the `asyncio` logger, and clear `caplog`. Garbage left by an earlier test then cannot make this test red or green.
2. Run the scenario inside a helper coroutine, so every reference dies when the helper returns.
3. Run `await asyncio.sleep(0)` and `gc.collect()` before asserting, so the record lands in this test and not in the next one.

### Coverage map

| Finding / Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| R-22, EC-119, EC-148, D-9 | `muse_host/test_muse_host_turns.py` → `test_failed_turn_never_waited_logs_no_unretrieved_exception` (helper `leave_a_failed_turn_unwaited`) | R | The scenario is `turn: {terminal: failed, error: {kind: modelError, …}}`. A turn is spawned and ends `failed`, and nobody calls `wait_muse_turn` before the host exits → asyncio logs "Task exception was never retrieved" for the `muse-turn-…` driver task when the host is collected. | **Nothing failed.** A waited twin of the same scenario runs first, in the same host, and must raise `muse.api_error` with `vendor_kind == "modelError"` (EC-119). So the test turns red if a "fix" stops the driver from raising, or if the scenario no longer fails. Before the host exits, the fake must also log exactly two `turn/completed` frames with `terminal == "failed"` (a bounded poll of at most 30 s). **The record lands elsewhere.** The three steps above keep it in this test. The waited twin logs nothing by itself, so today's only record is the unwaited turn's. |
| R-24, EC-2, EC-8, INV-4 | `grok_host/test_grok_host_turns.py` → `test_host_closed_during_spawn_leaves_no_unretrieved_future` (helper `close_the_host_while_spawn_is_in_flight`) | R | The scenario is `acp.session_prompt: {mode: hold}`. `spawn_grok_session` runs as a task, the test yields one loop step, and then it calls `__aexit__`, which finds no live turn and closes the host. The spawn writes `session/prompt`, sees the host closed and raises. The peer close then fails the dropped answer future → asyncio logs "Future exception was never retrieved" when the future is collected. | **The error is swallowed.** The spawn must still raise `grok.process_exited`, with operation `spawn_grok_session`, the EC-2 token `async with`, and a message containing "closed while the turn was starting". **The window is missed.** The fake must have received exactly one `session/prompt`, which proves the answer future existed. A host that failed earlier would leave no future, and the test reports that as a failed precondition. **A reference survives.** The helper returns nothing, and every check on the error runs inside it. A returned exception would keep `_launch`'s frame alive past `gc.collect()`, and that frame holds the future. |

### Tests deliberately NOT written (addendum 4)

| Candidate | Why it would not earn its keep |
|---|---|
| (B), the literal `DEEPSEEK_API_KEY` at `profiles.py:286` | It was refuted. EC-127 requires that exact text, and `test_native_backends_errors.py` already asserts it. |
| An R-24 twin for `continue_grok_session` | Continue reaches the same `_launch` raise as spawn (review.md: spawn `:217`, continue `:294`), so a second test would prove the same line twice. The review row names the spawn test. |
| R-22 variants: `exit_before_complete` (EC-120), a turn that fails during `__aexit__`, and eviction from the 64-entry finished table while the host is open | The verifier showed that all of them log through the same missing retrieval (14 of 14), so one fix closes all of them. One deterministic scenario is enough. The others would add run time and timing sensitivity and catch nothing new. |
| Opencode twins | The verifier found opencode not affected: its `_forget` already retrieves the exception behind a `cancelled()` guard. |
| Asserting the mechanism: `task.exception()` in `_forget_driver`, `answer.cancel()` in `_launch`, or a wider retrieval in `NativeTurnTable._finish` | The brief says to assert outcomes. Any of these fixes passes both tests. |
| Capturing with a loop exception handler instead of `caplog` | The verifier's probes used a handler. A user, though, sees the default handler's record on the `asyncio` logger, and `caplog` reads exactly that record. Replacing the handler would test a setup that no caller has. |

### Red run (addendum 4)

Bootstrap: none. The environment is global Python 3.11.0 on win32, reached through `PYTHONPATH=$(pwd)`, with `pytest 8.3.5` and pytest-asyncio 1.3.0 in strict mode. No `pip install` ran. HEAD is `4ecd4012`, and the new tests are staged.

**Each new test alone, 5 runs.** Both tests were red in 5 of 5 runs, every time for the same reason:

| Test | Runs | Observed red reason |
|---|---|---|
| R-22 `test_failed_turn_never_waited_logs_no_unretrieved_exception` | 5 / 5 red | `AssertionError: R-22: a failed Muse turn that nobody waited on logged ['Task exception was never retrieved']; …`. The captured record names `MuseTurnDriver.run()` with `NativeHostError('The Muse turn failed with modelError.')`. The twin and precondition assertions passed. |
| R-24 `test_host_closed_during_spawn_leaves_no_unretrieved_future` | 5 / 5 red | `AssertionError: R-24: a GrokHost closed during spawn logged ['Future exception was never retrieved']; …`. The checks on the spawn's error (code, operation, token, message) and the one-`session/prompt` precondition all passed. |

**The four packs, once:**

```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
…
FAILED tests/features/grok_host/test_grok_host_turns.py::test_host_closed_during_spawn_leaves_no_unretrieved_future
FAILED tests/features/muse_host/test_muse_host_turns.py::test_failed_turn_never_waited_logs_no_unretrieved_exception
2 failed, 1659 passed, 19 skipped in 167.82s (0:02:47)
```

The 2 failures are exactly the 2 new tests, with the same reasons as above. The 1659 passes match the HEAD baseline, and the 19 skips are the same platform guards. Inside the full run, garbage from earlier tests changed neither result, because each test collects and clears before it starts.

**Can the tests pass?** A scratch folder outside the worktree held a shim (nothing committed). The shim loaded each pack's conftest and ran the unchanged test functions from the worktree, in three modes, 5 runs per mode:

| Mode | R-22 | R-24 | Neighbours run alongside |
|---|---|---|---|
| no patch | 5 / 5 red | 5 / 5 red | green |
| wrapper only: the patch in place, without the fix line | 5 / 5 red | 5 / 5 red | green |
| the review.md "Smallest fix" | 5 / 5 green | 5 / 5 green | green |

- **The R-22 fix.** `MuseHost._forget_driver` pops the driver, then calls `task.exception()` when `not task.cancelled()`.
- **The R-24 fix.** A wrapper records the futures that `NativePeer.send` returns. When `GrokHost._launch` raises `NativeHostError`, the wrapper cancels the last future if it is still pending. It drops every reference when `_launch` ends.
- **Why the "wrapper only" mode matters.** It proves that the scratch wrappers keep nothing alive that could hide the record, so the green comes from the fix line alone.
- **The neighbours.** These were `test_waiting_twice_on_a_failed_turn_raises_the_same_code` (Muse), and `test_turn_peer_wire_shapes` and `test_a_failed_spawn_releases_its_reservation` (Grok). They show that the fix does not change a waited failure, a normal spawn, or a failed spawn's released reservation.

**Lint.** `python lint/run.py` on the staged files gave `SDK-LINT: PASS`. A001 (643), A007 (255), S062 (889) and S024 (25) stay at their baselines.

### Notes for the implementer (addendum 4)

- **The bound names and outcomes:**
  - `spawn_muse_session`, `wait_muse_turn`, and EC-119's `muse.api_error` with `context["vendor_kind"]`;
  - `GrokHost.__aenter__`, `__aexit__` and `spawn_grok_session`;
  - `grok.process_exited` from the spawn, with operation `spawn_grok_session`, the EC-2 next step (token `async with`), and a message containing "closed while the turn was starting";
  - the fakes' `sent` and `frame` log records.
- **What must not change:**
  - A waited failed Muse turn still raises on every wait (EC-148).
  - The Grok spawn still raises `grok.process_exited` after it writes `session/prompt`.
  - Grok's normal turns still get their answer, so do not cancel the future on the success path.
- **Keep the `cancelled()` guard (R-22).** `task.exception()` raises `CancelledError` on a cancelled task, and loop teardown can cancel a driver.
- **A different R-24 fix moves the window.** Suppose you move the closed-host check before the `session/prompt` write instead of cancelling the future. The one-`session/prompt` precondition then fails, with a message that starts with `precondition:`. That failure means the window moved, not that the fix is wrong. Ask the orchestrator; do not edit the test.
- **Do not add `gc.collect()` or `caplog` handling to other tests.** The two new tests isolate themselves.

## Addendum 5 — 3.11 swallowed cancel in the bounded drain (AC-4, INV-2)

Repair iteration 7's full-suite run exposed a defect in this PR's transport (verify-log, "Iteration 7"). `McpStdioTransport._send` (`transport.py:323`) and `_write_frame` (`:423`) drain a write that has a deadline with `await asyncio.wait_for(stdin.drain(), seconds)`. On CPython 3.11, `wait_for` runs the drain in an inner task. Suppose the caller is cancelled after that inner task finished but before the caller resumes. Then `wait_for` returns the drain's result, and the cancel is lost (CPython gh-86296). The call goes on, waits out the control timeout on a silent fake, and raises `grok.server_unreachable` ("did not answer in time") instead of `CancelledError`. This breaks AC-4 and INV-2. The existing AC-4 test hits the window about 1 run in 12 to 40. Python 3.12+ builds `wait_for` on `asyncio.timeout` and has no such window.

This addendum adds 2 test functions (4 cases) to `test_grok_host_process_bounds.py`. They force the window every time. They use the public API, the §13 fakes as real child processes, and one delegating seam defined in the file. They change no fixture, no fake default and no existing assertion. As in addendum 4, the pack's FEATURE.md gained a failure-mode line, a regression line and a suite-map mention, and its README.md gained a log line.

**The seam, `drain_window_gate`.** It follows `cancel_drain_gate` (R-19, `test_grok_host_turns.py`): it wraps functions, always calls the real ones, and only chooses the moment of one cancel.
1. It wraps `NativePeer.call`, `send` and `notify` (spec §8.5 names). When the task under test writes the named frame, the gate is armed.
2. It wraps `asyncio.wait_for` through the module attribute. The first bounded `wait_for` in that task whose awaitable is a `StreamWriter.drain` coroutine is that frame's drain. The gate passes the real `wait_for` a small coroutine instead, which awaits the real drain and then cancels the caller.
3. **On 3.11**, that coroutine runs in `wait_for`'s inner task. So the cancel lands just as that task ends, while the caller waits to resume. That is the gh-86296 window, every time.
4. **On 3.12+**, the coroutine runs in the caller's own task. A task that cancels itself does not receive the cancel at once: the cancel stays pending until the task's next suspension. With the planned fix, the host's cleanup would then receive a second cancel. So on 3.12+ a loop callback cancels the caller, and the cancel is delivered inside the drain, as for a drain that blocks on a full pipe. A stdlib-only simulation (scratch `seam_sim.py`, run on 3.11.0 and 3.13) showed this: with a self-cancel and the fix, the cleanup logged "interrupted by a second cancel"; with the committed gate it did not.
5. The tests assert that the gate engaged, with a `seam:` message. A fix that stops draining through `asyncio.wait_for` therefore fails loudly instead of passing for nothing.

### Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-4, INV-2, EC-4 (request site, `_send`) | `grok_host/test_grok_host_process_bounds.py` → `test_cancel_landing_as_the_request_drain_finishes_still_propagates` [spawn_grok_session, continue_grok_session, list_grok_sessions] | R (concurrency, forced window) | The fake is stubborn, with `CANCEL_CASES`' silent `session/new`, `session/resume` or `session/list`, and `control_timeout_seconds=5`. The call is cancelled as the silent request's bounded drain finishes → on 3.11 the call waits 5 s and raises `grok.server_unreachable` instead of `CancelledError`. | **The window is missed.** `drain_window_gate.engaged` must be true: the gate found the bounded drain of that exact frame in the calling task. **A late cancel.** The outcome must be `CancelledError`, not a `NativeHostError` or a result, and it must arrive less than 5 s after the cancel (a stop under `fast_stop` takes at most 1.3 s). **A leak.** On POSIX, every process the call started is gone within `peer_bound`, as in the existing AC-4 test. |
| INV-2 (remedy step 3: the cancelled write drops its pending future) | the same test, its last assertion | R | A fix re-raises the cancel, but `_send` leaves the request's pending answer future in its map. The peer close then fails that future, and nobody reads it → asyncio logs "Future exception was never retrieved". | It uses addendum 4's technique: `gc.collect()` and `caplog.clear()` first, the call inside the helper coroutine `cancel_in_the_drain_window`, then `asyncio.sleep(0)` and `gc.collect()` before the check. The scratch run below shows the check red 3 of 3 times with the fix minus step 3. |
| INV-2, FR-7 (notification site, `_write_frame`) | `grok_host/test_grok_host_process_bounds.py` → `test_cancel_landing_as_the_session_cancel_drain_finishes_still_propagates` | R (concurrency, forced window) | A held turn. `interrupt_grok_turn` is cancelled as its `session/cancel` drain finishes → on 3.11 it returns a `NativeInterruptResult` to a cancelled caller. | It requires the same `seam:` engagement and the `CancelledError` outcome. A precondition requires that `session/cancel` reached the fake. A fix applied to `_send` only leaves this test red. |

### Tests deliberately NOT written (addendum 5)

| Candidate | Why it would not earn its keep |
|---|---|
| `check_grok_ready` | It runs the CLI and writes no JSON-RPC frame, so it has no bounded drain. |
| Muse twins of both tests | Muse reaches the same two lines through the same `NativePeer`. A twin would prove the same lines again and add about 20 s of red run. |
| **The answer wait in `McpStdioTransport.request`** (`await asyncio.wait_for(future, timeout=seconds)`, `transport.py:349`) | It has the same gh-86296 window: a cancel that lands after the answer future resolved, but before the caller resumes, is dropped. A scratch probe (`test_s2_probe_response_wait.py`, not committed) cancelled `list_grok_sessions` from a done-callback on its `session/list` answer future. The call returned a `GrokSessionPage` to the cancelled caller, today **and with the planned remedy**, because the remedy covers only the drains. The briefing requires these tests to pass with the planned remedy, so this test is not committed. It is routed to the orchestrator as an open item. **Superseded:** the orchestrator ruled that iteration 8 fixes it, and the test is now written; see "The answer wait" below. |
| The close path's bounded `wait_for(process.wait(), …)` (`transport.py:473`, `:499`, `:509`) | These may have the same window inside `NativePeer.close`, for example during a cancelled `__aexit__`. They were not probed: that is outside this brief, and `close()` never raises by design. Listed for the orchestrator. **Ruled out of scope;** see "The answer wait" below. |
| The default unbounded drain (INV-18) | Existing tests in `tests/test_mcp_stdio_transport.py` pin it, and the briefing rules it out. |
| Asserting the mechanism: the `_drain` helper, `task.cancelling()`, or `except CancelledError` in `_send` | The tests assert outcomes only. The seam relies on one detail that callers cannot see: the drain still goes through `asyncio.wait_for` with a `StreamWriter.drain` coroutine. The orchestrator already decided to keep `wait_for`, for R-19. |

### Red run (addendum 5)

Bootstrap: none. The environment is global Python 3.11.0 on win32, reached through `PYTHONPATH=$(pwd)`, with `pytest 8.3.5` and pytest-asyncio 1.3.0 in strict mode. No `pip install` ran. HEAD is `32d7ef51`, and the new tests are in the working tree.

**Each new test alone, 5 runs** (`PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q "tests/features/grok_host/test_grok_host_process_bounds.py::<node>"`):

| Test | Runs | Observed red reason |
|---|---|---|
| `…request_drain_finishes_still_propagates[continue_grok_session]` | 5 / 5 red, 6.4 to 6.6 s each | `AssertionError: AC-4 / INV-2: continue_grok_session was cancelled as its session/resume drain finished and raised NativeHostError grok.server_unreachable: The Grok Build process did not answer in time.` |
| `…[list_grok_sessions]` | 5 / 5 red, 6.4 to 6.8 s each | the same, for `session/list` |
| `…[spawn_grok_session]` | 5 / 5 red, 6.4 to 6.8 s each | the same, for `session/new` |
| `…session_cancel_drain_finishes_still_propagates` | 5 / 5 red, 1.0 to 1.2 s each | `AssertionError: INV-2: interrupt_grok_turn was cancelled as its session/cancel drain finished and returned NativeInterruptResult` |

In every run the `seam:` assertion passed, so the window was forced, not missed.

**The four packs, once:**

```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
…
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_request_drain_finishes_still_propagates[continue_grok_session]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_request_drain_finishes_still_propagates[list_grok_sessions]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_request_drain_finishes_still_propagates[spawn_grok_session]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_session_cancel_drain_finishes_still_propagates
4 failed, 1661 passed, 19 skipped in 182.08s (0:03:02)
```

The 4 failures are exactly the 4 new cases, with the reasons above. The 1661 passes and 19 skips match the iteration-7 baseline. The existing AC-4 test passed in this run.

**Can the tests pass?** A scratch copy outside the worktree (`git archive HEAD`, plus the new test file) held the verify-log remedy, applied to its copy of `transport.py`. Nothing from it was committed.
1. One helper, `_drain(process, seconds)`, keeps `asyncio.wait_for`. It reads `current_task().cancelling()` before the drain and raises `CancelledError` if the count rose.
2. Both bounded drain sites call it.
3. `_send` gains `except asyncio.CancelledError:`, which pops and cancels the pending future and then re-raises.

| Mode | Request site (3 cases) | Notification site | Other checks |
|---|---|---|---|
| today's code | 5 / 5 red (above) | 5 / 5 red | — |
| full remedy | 5 / 5 green (`4 passed, 15 deselected in 2.39s` to `3.43s`) | 5 / 5 green | R-19, `-k loses_to` on `test_grok_host_turns.py`: `1 passed`, 3 / 3. Both whole files: `43 passed, 7 skipped in 20.96s` |
| remedy without step 3 | 3 / 3 red, only on the never-retrieved check: `logged ['Future exception was never retrieved']` | 3 / 3 green | — |
| 3.12+ path emulated on 3.11 (the gate delivers the cancel inside the drain), today's code | the `CancelledError` check passes; the never-retrieved check is red in all 3 cases | — | — |
| the same emulation, full remedy | green | green | — |

**On 3.12+ (CI's 3.12 leg)** the gh-86296 window does not exist. So the `CancelledError` and timing checks pass before the fix, and so does the notification-site test. The request-site test's never-retrieved check, though, is expected to be **red before the fix** on 3.12+. There the gate delivers the cancel inside the drain, and today's `_send` lets `CancelledError` pass without dropping the pending future. The emulation row above shows this on the real pack, and the stdlib simulation on 3.13 shows it too. Remedy step 3 turns it green. CI's 3.11 leg is the regression guard for the swallow itself. No local 3.12+ interpreter has the test dependencies, so the pack itself was not run on 3.12+.

**Lint.** `python lint/run.py` on the staged files gave `SDK-LINT: PASS`. A001 (643), A007 (255), S024 (25) and S062 (889) stay at their baselines; A009 and S006 are clean.

### Notes for the implementer (addendum 5)

- **The bound names:**
  - `NativePeer.call`, `send` and `notify` (spec §8.5), called in the task that called the public method;
  - `asyncio.wait_for`, looked up through the `asyncio` module at call time, with a `StreamWriter.drain` coroutine and a timeout that is not `None`;
  - `GrokHostSettings.control_timeout_seconds`;
  - `spawn_grok_session`, `continue_grok_session`, `list_grok_sessions` and `interrupt_grok_turn`.
- **What must not change:**
  - Keep `asyncio.wait_for(stdin.drain(), seconds)` in both bounded paths. Do not wrap the drain in another coroutine first, and do not move the write into another task. This gate and R-19's gate both find the drain this way.
  - The default unbounded drain stays as it is (INV-18).
- **A `seam:` failure** means the fix stopped draining through `asyncio.wait_for`. Ask the orchestrator; do not edit the test.
- **Step 3 is required.** If the fix re-raises the cancel but does not pop and cancel the pending future, `_fail_all_pending` fails that future unseen. The request-site test then turns red, on 3.11 and on 3.12+.
- **Timing.** A red request-site case takes about 6.5 s, because it waits out the 5 s control timeout. A green one takes under 1 s.

### The answer wait (added after the orchestrator's ruling)

The orchestrator ruled that iteration 8 also fixes the answer wait. The function is `McpStdioTransport._answer` (`transport.py:349`), which `request` uses: `await asyncio.wait_for(future, timeout=seconds)`. After that wait, the fix raises `CancelledError` if `current_task().cancelling()` rose during it, with the same before/after count check as the drain helper. This part adds 1 test function (3 cases) to the same file. It supersedes the two rows above about the answer wait and the close path.

**The seam, `answer_window_gate`.** `install_window_gate` now installs either gate, so both share the same delegating wrappers on `NativePeer.call`, `send` and `notify` and on `asyncio.wait_for`. `AnswerWindowGate` is armed the same way, when the task under test writes the named request. It then takes the first bounded `wait_for` in that task whose awaitable is a plain future (not a coroutine, not a task); that future is the request's answer. The gate adds a done-callback to that future before it calls the real `wait_for`, so the callback runs before `wait_for`'s own callback. The callback cancels the caller at the instant the answer resolves.
- **On 3.11**, the cancel lands after the answer resolved and before the caller resumes, which is the gh-86296 window, every time.
- **On 3.12+**, the cancel comes from a loop callback, not from the caller's own task, so it is delivered once, at `await fut`. A stdlib-only simulation (scratch `answer_sim.py`) gave `returned {...}` on 3.11.0 without the check, and `CancelledError` with it. On 3.13 it gave `CancelledError` both with and without the check, and the cleanup ran once each time.

#### Coverage map (answer wait)

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-4, INV-2, EC-4 (answer site, `_answer`) | `grok_host/test_grok_host_process_bounds.py` → `test_cancel_landing_as_the_answer_arrives_still_propagates` [continue_grok_session, list_grok_sessions, spawn_grok_session] | R (concurrency, forced window) | The fake is stubborn, and the default scenario answers `session/resume`, `session/list` or `session/new` at once. The call is cancelled at the instant that answer resolves → on 3.11 `wait_for` returns the answer, and the cancelled caller receives a `NativeTurnHandle` (continue, spawn) or a `GrokSessionPage` (list). | **The window is missed.** `answer_window_gate.engaged` must be true, and `cancel_sent_at` must be set: the answer future of that exact request resolved in the calling task's bounded wait. **A result reaches the caller.** The outcome must be `CancelledError`, and any returned object fails the test with its type name. **A leak.** On POSIX, every process the call started is gone within `peer_bound`. **The drain fix alone passes it.** It does not: with only the iteration-7 drain remedy, all 3 cases stay red (below). |

#### Tests deliberately NOT written (answer wait)

| Candidate | Why it would not earn its keep |
|---|---|
| The close path's bounded `wait_for(process.wait(), …)` (`transport.py:473`, `:499`, `:509`) | **Out of scope by the orchestrator's ruling.** Cleanup should finish. Re-raising a cancel in the middle of a close could leave a child process unreaped, which is worse than finishing the close. |
| A never-retrieved check on the answer test | The answer future already holds a result when the cancel lands, so no exception can go unread. The check could not fail. |
| Asserting that a cancelled spawn or continue sends no `session/prompt` | EC-4 allows a host that already sent the prompt to interrupt that turn and close its peer. That would over-specify the fix. The POSIX process check covers a turn left running. |

#### Red run (answer wait)

**Each case alone, 5 runs** on Python 3.11.0, HEAD `5e4c3c34` plus the working tree:

| Case | Runs | Observed red reason |
|---|---|---|
| `[continue_grok_session]` | 5 / 5 red, 1.33 to 1.46 s each | `AssertionError: AC-4 / INV-2: continue_grok_session was cancelled as its session/resume answer arrived and returned NativeTurnHandle; the cancelled caller must get CancelledError, not a result (CPython 3.11, gh-86296)` |
| `[list_grok_sessions]` | 5 / 5 red, 1.34 to 1.57 s each | the same, `returned GrokSessionPage` |
| `[spawn_grok_session]` | 5 / 5 red, 1.34 to 1.55 s each | the same, for `session/new`, `returned NativeTurnHandle` |

The `seam:` assertions passed in every run.

**The four packs, once:**

```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
…
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_request_drain_finishes_still_propagates[continue_grok_session]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_request_drain_finishes_still_propagates[list_grok_sessions]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_request_drain_finishes_still_propagates[spawn_grok_session]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_session_cancel_drain_finishes_still_propagates
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_answer_arrives_still_propagates[continue_grok_session]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_answer_arrives_still_propagates[list_grok_sessions]
FAILED tests/features/grok_host/test_grok_host_process_bounds.py::test_cancel_landing_as_the_answer_arrives_still_propagates[spawn_grok_session]
7 failed, 1661 passed, 19 skipped in 183.39s (0:03:03)
```

The 7 failures are exactly the addendum's 7 cases: 4 drain cases and 3 answer cases. The ruling expected 5, which assumed list only, but spawn and continue reach a bounded answer wait just as cheaply. The 1661 passes and 19 skips match the baseline.

**Can the tests pass?** The scratch fix copy gained the ruling's answer check in `_answer`: it reads `cancelling()` before the wait and, after it, raises `CancelledError` if the count rose. That raise goes through the existing `except asyncio.CancelledError` branch, which pops the pending entry.

| Mode | Answer cases (3) | Drain cases (4) | Other checks |
|---|---|---|---|
| today's code | 5 / 5 red (above) | 5 / 5 red | — |
| drain fix plus answer check | 5 / 5 green (`7 passed, 15 deselected in 3.70s` to `3.96s`) | 5 / 5 green | R-19, `-k loses_to` on `test_grok_host_turns.py`: `1 passed`, 3 / 3. Both whole files: `46 passed, 7 skipped in 21.33s`. The final file alone: `17 passed, 5 skipped` |
| drain fix only (the iteration-7 proposal) | 3 / 3 red, `returned NativeTurnHandle` / `GrokSessionPage` | green | — |

**On 3.12+** the answer cases are expected to pass before the fix, because the cancel is delivered at `await fut` (see the simulation above).

**Lint.** `python lint/run.py` on the staged files gave `SDK-LINT: PASS`, with A001 (643), A007 (255), S024 (25) and S062 (889) at their baselines.

#### Notes for the implementer (answer wait)

- **Keep the answer wait as `asyncio.wait_for(future, timeout=seconds)`**, called through the `asyncio` module, with the answer future itself as the awaitable, in the caller's task. Do not wrap the future in a coroutine or a task first. A `seam:` failure means the wait changed shape; ask the orchestrator.
- **The check sits inside the existing `try`,** so the raise reuses the `except asyncio.CancelledError` cleanup.
- **Do not add the check to the close-path waits** (`:473`, `:499`, `:509`); that is the ruling.

## Addendum 6 — fake ordering fix (R-22 precondition flake)

**Symptom.** `test_failed_turn_never_waited_logs_no_unretrieved_exception` (R-22) sometimes failed after about 31 to 34 s with `precondition: the fake did not send a failed turn/completed for both turns`. It failed 1 run in 30 at `3917b49a` and 1 in 62 at `19582f13`, in fresh processes on Windows. Repair iteration 8 found the cause (`reports/S5-repair-8.md`). The product code is not involved.

**Cause.** The cause is a race inside the Muse test fake.
- `FrameWriter.send` wrote a frame to stdout under its lock, but logged the `sent` record after it released the lock.
- The turn thread writes `turn/completed`. The host reads it and closes the peer's stdin.
- The fake's main thread sees stdin EOF and calls `os._exit(0)`. That exit could run before the turn thread logged `sent`, so the record the precondition reads was lost.

**Change.** The orchestrator granted this fixture change. It reorders the write, the log and the exit, and nothing else. No assertion, scenario default or test changed.
- **The log moves under the lock.** `FrameWriter.send` now logs `sent` inside the same `with self.lock` block as the stdout write.
- **The exit waits for the lock.** The stdin-EOF exit first calls `self.writer.lock.acquire(timeout=EXIT_WRITER_WAIT_SECONDS)`, with the new constant `EXIT_WRITER_WAIT_SECONDS = 2.0`. A write and its log that are already in flight therefore finish before the process exits.
- **The wait is bounded.** If a writer is ever stuck on a full stdout pipe, the exit still happens after 2 s, as it did before the change.
- **It cannot deadlock.**
  - The EOF path runs on the main thread, which never holds the writer lock when it reaches EOF.
  - The lock order is always writer lock, then log lock. `FakeLog.write` never takes the writer lock, and no code sends while it holds `self.condition`.
  - The one `os._exit` inside the lock, on a failed write, ends the process.
- **The Grok fake gets the same fix.** `fake_grok_peer.py` had the same race. `FrameWriter.send` called `raw()` and logged afterwards, outside the lock, and `AcpPeer.after_eof` called `os._exit(0)` at once, while `TurnWorker` sends the `session/prompt` answer from another thread. No Grok failure was seen, because the only Grok test that reads `sent` (`test_spawn_returns_a_handle_while_the_turn_is_still_running`) checks that a record is absent. Now `raw()` takes an optional keyword `sent=`, which `send` passes, so the record is logged under the lock. `raw()` calls without `sent=` (the garbage lines) log nothing, as before. The same bounded acquire runs before the exit in `after_eof`.
- **Both file headers** gained one sentence under KNOWN EDGE CASES.

**Before → after.** In `fake_muse_peer.py`:
```python
# before
        with self.lock:
            try:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            except (OSError, ValueError):
                os._exit(0)
        self.log.write("sent", frame=frame)
...
                if self.scenario.get("ignore_eof"):
                    held(self.scenario)
                os._exit(0)
# after
        with self.lock:
            try:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            except (OSError, ValueError):
                os._exit(0)
            self.log.write("sent", frame=frame)
...
                if self.scenario.get("ignore_eof"):
                    held(self.scenario)
                # Wait, bounded, for a frame another thread is writing and logging, so the exit never drops its "sent" record.
                self.writer.lock.acquire(timeout=EXIT_WRITER_WAIT_SECONDS)
                os._exit(0)
```
In `fake_grok_peer.py`:
```python
# before
    def send(self, frame: dict[str, Any]) -> None:
        self.raw(json.dumps(frame))
        self.log.write("sent", frame=frame)

    def raw(self, text: str) -> None:
        ...
            except (OSError, ValueError):
                os._exit(0)
...
    def after_eof(self) -> None:
        if self.scenario.get("ignore_eof"):
            held(self.scenario)
        os._exit(0)
# after
    def send(self, frame: dict[str, Any]) -> None:
        self.raw(json.dumps(frame), sent=frame)

    def raw(self, text: str, *, sent: dict[str, Any] | None = None) -> None:
        ...
            except (OSError, ValueError):
                os._exit(0)
            if sent is not None:
                self.log.write("sent", frame=sent)
...
    def after_eof(self) -> None:
        if self.scenario.get("ignore_eof"):
            held(self.scenario)
        # Wait, bounded, for a frame another thread is writing and logging, so the exit never drops its "sent" record.
        self.writer.lock.acquire(timeout=EXIT_WRITER_WAIT_SECONDS)
        os._exit(0)
```

### Proof (addendum 6)

The environment is global Python 3.11.0 on win32, reached through `PYTHONPATH=$(pwd)`. HEAD is `2229bd5a`, and the fake changes are staged.

**1. A forced gap.** Scratch copies of the Muse pack sat outside the worktree. One copy had the HEAD fake and the other the fixed fake, and each had `time.sleep(0.2)` added just before the `sent` log write. R-22 ran 3 times against each copy:

| Fake | Runs | Result |
|---|---|---|
| HEAD fake, with the gap | 3 / 3 red | `AssertionError: precondition: the fake did not send a failed turn/completed for both turns`, after about 32.6 s each time. This is the flake's exact message and timing. |
| fixed fake, with the gap | 3 / 3 green | `1 passed` in about 3.4 s |

**2. Fresh-process loops.** Each run was a new `python -m pytest -p no:cacheprovider -q …` process:

| Test | Runs | Result |
|---|---|---|
| R-22 `test_failed_turn_never_waited_logs_no_unretrieved_exception` | 60 | **60 / 60 passed**: no precondition failure, and no other failure |
| R-24 `test_host_closed_during_spawn_leaves_no_unretrieved_future` (the Grok fake changed too) | 30 | **30 / 30 passed** |

**3. The four packs, once:**
```
$ PYTHONPATH=$(pwd) python -m pytest -p no:cacheprovider -q tests/features/grok_host tests/features/opencode_host tests/features/muse_host tests/features/native_backends
1668 passed, 19 skipped in 167.58s (0:02:47)
```

**4. Lint.** After `git add`, `python lint/run.py` gave `SDK-LINT: PASS`. A001 (643), A007 (255), S024 (25) and S062 (889) stay at their baselines.
