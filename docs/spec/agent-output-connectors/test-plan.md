# Test plan: Agent output connectors

Spec: `docs/spec/agent-output-connectors/spec.md` r3 · Framework: pytest 8.3.5 + pytest-asyncio 1.3.0 (httpx 0.28.1 for `MockTransport`) · Prior art copied: `tests/features/coding_agent/` (pack layout, A001 headers, lazy feature fixtures), `tests/test_web_operation_client_retry.py` (`HttpTransport._send_once` + `transport_module.asyncio.sleep` seam), `tests/agent_test_support.py` (`build_test_agent`, `bind_test_runner`), `tests/test_restore_output_schema.py` (scripted structured runs, `restore`).

Pack: `tests/features/agent_output_connectors/` — `FEATURE.md`, `README.md`, `conftest.py`, `factories.py`, and nine test modules. In the table, `acceptance.py` means `test_output_connectors_acceptance.py`, and likewise for `agent_wiring`, `dispatch`, `wire_contract`, `http_failures`, `email`, `configuration`, `security`, and `contract`. 86 test functions, 313 collected cases (destination and boundary tables are parametrized).

## Coverage map
| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | acceptance.py → `test_spec_snippet_delivers_one_validated_reply_to_slack_and_a_github_issue_and_prints_both_receipts` | acceptance | The §4 snippet run as written (env vars set, Slack 200 `ok`, GitHub 201) → wrong or missing printed lines, extra request, or an exception. | It asserts the exact printed stdout and both exact wire requests; the snippet's `except` path would print `failed:` lines that break the equality. |
| AC-2 | configuration.py → `test_slack_credential_from_the_environment_is_stripped`, `test_slack_credential_prefers_a_non_blank_explicit_argument_over_the_environment`, `test_slack_credential_missing_everywhere_raises_the_documented_message` | integration | Padded `SLACK_WEBHOOK_URL` → POST to `" https://…\n"`; env beats explicit; blank explicit not falling back; missing credential → wrong or secret-bearing message. | The URL is read from the recorded wire request, not the connector; the missing-credential message is compared exactly. |
| AC-3 | security.py → `test_no_surface_shows_the_credential_even_when_the_destination_echoes_it` (×11 destinations) | security | A destination that echoes the credential in its error body / SMTP reply → the credential in `repr`/`str` of connector, `agent.outputs`, `JevAgentSettings`, receipts, `str(err)`, `err.details`, metadata, or `export_state()`. | It first asserts a FAILED receipt exists (the echo path really ran) and scans for the marker, the raw credential, and the wire form (Jira's base64 Basic value). |
| AC-4 | acceptance.py → `test_reply_that_fails_its_output_schema_raises_and_sends_nothing` | integration | Invalid structured reply → a post goes out before `OutputSchemaViolationError`, or a `deliveries` key is written. | Outputs are configured and no response is scripted, so any send also fails as an unscripted request; `pytest.raises` pins the schema error. |
| AC-5 | acceptance.py → `test_partial_failure_attempts_every_output_then_raises_with_the_recorded_reply_and_one_receipt_each` | acceptance | Slack 404 `no_service` + GitHub 201 → GitHub skipped, silent return, error without the recorded reply, wrong receipt order or message. | Both URLs must appear on the wire; identity checks on `err.reply`, `last_reply`, `history[-1]`; exact message string. |
| AC-6 | http_failures.py → `test_slack_answer_maps_to_one_receipt_and_only_a_429_is_retried` (a–d); dispatch.py → `test_destination_that_never_answers_is_failed_network_at_the_deadline_without_holding_back_the_others` (e) | integration | (a) 429 then 200 not retried; (b) 429×3 → wrong attempt count; (c) 500 retried; (d) network error retried; (e) a hung endpoint holds the run or fails other connectors. | Attempt counts are literal and read from recorded sends; scripted queues never repeat, so an extra retry fails loudly; the deadline test first pins the module constant at 35.0 and wraps the call in a 10 s safety timeout. |
| AC-7 | http_failures.py → `test_mixed_failures_give_their_codes_in_configured_order_and_no_url_leaks` | integration | Webhook network error whose excerpt holds the URL, Slack 404 `channel_not_found`, Discord 400 JSON → URL in a code, the message, or `details`; JSON body kept as a token. | Exact code list and exact message; the URL and host are searched in three surfaces. |
| AC-8 | dispatch.py → `test_stopped_or_blank_reply_is_skipped_for_every_output_with_no_request_and_no_error` (whitespace, empty, `middleware_abort`, `max_iterations` notice, and every other non-finishing `AgentStopReason`) | integration | A stop notice or blank reply → posted, raised, or not marked SKIPPED. | No destination is scripted, so any request fails; receipts must be SKIPPED for both connectors and written to metadata. |
| AC-9 | wire_contract.py → `test_channel_wide_mentions_are_neutralized_for_each_chat_destination`, `test_notion_mention_tags_in_the_markdown_body_are_neutralized` | contract / security | `<!channel> & @everyone <users/all>` → Slack unescaped or double-escaped, Discord without `allowed_mentions`, Google Chat with `<users/`, Telegram with `parse_mode`; Notion `<mention-` kept. | Slack text is compared exactly (wrong escape order gives `&amp;lt;`); the others assert both presence of the replacement and absence of the token. |
| AC-10 | wire_contract.py → `test_long_reply_is_capped_for_discord_and_its_long_first_line_becomes_a_250_character_one_line_title` | integration | 5,000-char reply → Discord 400 (not capped) or split; 400-char first line → GitHub title / email Subject over 250, multi-line, or ending in `[truncated]`. | The paragraph is 400 chars with no trailing space, so `paragraph[:250]` is only matched by the single-line rule; both the HTTP and the SMTP path are asserted. |
| AC-11 | dispatch.py → `test_default_shaping_turns_each_reply_into_one_title_and_one_body` (8 rows), `test_render_replaces_the_shaping_rule_for_its_own_connector_only`, `test_render_that_returns_anything_but_output_content_fails_only_its_connector` | integration | (a) structured `BaseModel` or dict ignored; (b) heading not used, Slack text duplicates the title; (c) no-title structure titled from JSON; (d) render ignored; (e) bad render return crashes delivery or sends. | Exact GitHub JSON body and exact Slack text per row; render identity is asserted (`seen[0] is reply`); bad render rows assert no GitHub request. |
| AC-12 | agent_wiring.py → `test_fork_and_agent_tool_children_never_deliver_the_parents_outputs` | integration | `fork()` copies outputs → each `as_tool()` call posts. | The child really runs (tool result `child finding` is asserted), so a fork that carried outputs would post. |
| AC-13 | agent_wiring.py → `test_export_and_restore_never_serialize_outputs_and_reattach_only_what_the_caller_passes` | integration | `RunState` gains an outputs field, restore keeps or drops outputs wrongly. | The re-attached connector's own URL must receive the restored agent's reply. |
| AC-14 | agent_wiring.py → `test_jev_agent_takes_outputs_from_its_settings_and_delivers_the_finished_reply`, `test_jev_agent_settings_reject_a_bare_string_outputs_value` | integration | Settings not normalized/validated, JevAgent not wired, constructor signature changed, `outputs="slack"` accepted. | The Slack wire text must equal the Jev reply; the signature tuple is compared exactly. |
| AC-15 | agent_wiring.py → `test_coding_agent_accepts_outputs_through_its_base_options_and_delivers`; plus existing `tests/features/coding_agent/test_coding_agent_contract.py` (unmodified) | integration | `CodingAgent` rejects or drops `outputs`. | The coding agent's own reply must appear on the Slack wire. |
| AC-16 | email.py → `test_default_port_uses_starttls_then_login_then_one_plain_text_message_off_the_event_loop` (a), `test_port_465_uses_implicit_tls_with_a_verified_context_and_no_starttls` (b), `test_smtp_failure_maps_to_its_code_after_one_connection_and_stops_at_that_step` (c, e, f + extras), `test_partial_refusal_returned_by_send_message_is_failed_recipients_refused` (d), `test_username_without_an_at_sign_and_no_sender_is_rejected_naming_sender` | integration / security | Plaintext login, unverified TLS, SMTP on the event loop, wrong codes, retries, `apikey` as `From`. | The fakes keep smtplib's real constructor signatures (passing `context=` to `SMTP` raises); every row asserts one connection and the steps that must never run. |
| AC-17 | wire_contract.py → `test_each_http_connector_sends_its_documented_request` (×10), `test_created_object_link_that_is_missing_or_unsafe_makes_a_2xx_response_failed_invalid_response` (×9) | contract | Wrong URL, auth form (`Bearer` on Linear), missing version header, wrong body keys, missing `max_response_bytes`/timeout, wrong receipt link; Linear 200 without `issue.url` → SENT. | Each row's expected request is written literally from §9.2 (no constants imported), header names must be lowercase, the JSON body is compared whole. |
| AC-18 | agent_wiring.py → `test_cancellation_during_delivery_propagates_unwrapped_and_clears_the_runs_queued_prompts` | concurrency | `CancelledError` turned into a receipt or `OutputDeliveryError`; queued follow-up runs anyway. | It holds the list object the run claims (see Notes) and asserts `runner.calls == 1`; checking `agent._queued_prompts` after the run would be vacuous. |
| AC-19 | dispatch.py → `test_sends_run_concurrently_and_receipts_keep_configured_order_not_finish_order` | concurrency | Sequential sends, or receipts in finish order. | The first connector waits for an event only the second sets, so sequential delivery hits the (shortened) deadline and FAILS; finish order is recorded and differs from configured order. |
| AC-20 | configuration.py → `test_invalid_connector_argument_is_rejected_at_construction_naming_the_parameter_and_no_secret` (30 rows), `test_invalid_outputs_value_is_rejected_when_the_agent_is_built` (8 rows) | unit / integration | Invalid input accepted, error names a record field instead of the parameter, or echoes a credential. | Word-boundary match on the parameter name; every secret-bearing row carries the marker. |
| AC-21 | acceptance.py → `test_agent_without_outputs_runs_exactly_as_before_and_writes_no_deliveries_key`; plus the full existing suite | integration | Agents without outputs gain a `deliveries` key or a send. | Also asserts `agent.outputs == ()` (red now) and no request. |
| AC-22 | not pytest: `python lint/run.py`, `python scripts/run_ci.py`, `python scripts/generate-sdk-public-api.py --check`, Semgrep (§11) | gate | Lint/mypy/contract regressions. | Gate commands, run by S3/S5. |
| AC-23 | acceptance.py → `test_session_records_the_turn_and_captures_the_delivery_failure_before_it_reaches_the_caller` | integration | Turn not checkpointed before delivery; failure not in the ledger; secret in the ledger. | Head checkpoint content and exact ledger summaries are asserted. |
| AC-24 | dispatch.py → `test_resending_only_the_failed_connectors_makes_one_new_request_to_that_destination` (succeeds / fails again) | integration | Resend recipe re-posts GitHub, or returns the wrong receipts. | Only sends after the first run are counted, and must be exactly `[SLACK_URL]`. |
| AC-25 | http_failures.py → `test_redirect_is_not_followed_so_the_token_never_reaches_the_location_host` | security | 302 followed → `Authorization` sent to the Location host. | Uses the real `_send_once` over `httpx.MockTransport`, so `follow_redirects` is actually exercised; the Location host has a scripted 200 that would make a followed redirect look SENT. |
| AC-26 | contract.py → `test_docs_provider_reference_has_one_dated_row_with_an_official_link_per_destination`, `test_docs_describe_outputs_in_the_agent_readme_and_both_folders_in_the_repo_map`, `test_docs_new_folder_readmes_stay_within_40000_characters` | contract | Missing provider rows, links, dates, `outputs=` docs, or map entries. | Rows are found by each destination's env var and must also carry `https://` and `2026-10-11`. |
| INV-1 | acceptance.py → AC-4 test | integration | See AC-4. | See AC-4. |
| INV-2 | agent_wiring.py → `test_each_drained_follow_up_reply_is_delivered_once_on_its_own_pass_after_the_reply_that_queued_it`; configuration.py → `test_two_connectors_for_the_same_destination_are_allowed_and_each_gets_its_own_request`; duplicate-instance row of AC-20 | integration | Follow-up delivered before its parent, twice, or not at all; one instance posting twice. | Ordered wire texts and one receipt per reply. |
| INV-3 | security.py → `test_model_output_cannot_change_where_a_reply_goes` | security | Structured `url`/`repo`/`webhook_url`/`to` fields steer the request. | The model fills every steering field with an attacker host; sends and the SMTP `To` are checked. |
| INV-4 | security.py → AC-3 test, `test_records_mask_their_secret_fields_in_repr`, `test_each_credential_travels_only_in_its_own_destinations_request`; http_failures.py → AC-25 test | security | Credential in a repr, or in another destination's request. | Ten connectors on one agent; each request is scanned for every other credential. |
| INV-5 | configuration.py → AC-2 tests, `test_every_connector_reads_its_own_environment_variable_and_strips_it` (×10), `test_every_connector_without_a_credential_names_its_parameter_and_variable` (×22), `test_explicit_credential_is_stripped_before_it_reaches_a_header`, `test_credential_rotated_in_the_environment_after_construction_is_not_picked_up` | integration | Wrong order, no strip, whitespace counted as present, lazy resolution. | The wire request carries the stripped secret; the message is exact per destination. |
| INV-6 | acceptance.py → AC-5 test; dispatch.py → AC-19 test, `test_connector_bug_inside_send_becomes_an_unexpected_receipt_and_the_others_still_send` | integration | One failure stops the others; order lost. | See AC-5 / AC-19. |
| INV-7 | acceptance.py → AC-5, AC-23 tests, `test_agent_bound_to_a_session_reports_its_own_delivery_failure_when_run_directly`; agent_wiring.py → `test_delivery_failure_drops_the_runs_queued_follow_ups_instead_of_running_them_later` | integration | Error raised before recording; agent does not notify its bound session; queued prompts survive a failure. | `session.run` re-notifies on its own, so the direct `agent.run` test is the one that sees the agent's own notification. |
| INV-8 | acceptance.py → AC-1 test; dispatch.py → AC-8 and `test_finished_reply_is_delivered_whether_its_stop_reason_is_absent_or_a_normal_finish` | integration | All-SENT/SKIPPED still raises. | No `pytest.raises` around them; any raise fails the test. |
| INV-9 | dispatch.py → AC-8 tests; agent_wiring.py → `test_run_stopped_by_max_iterations_is_skipped_for_every_output_and_returns_normally` | integration | See AC-8, EC-43. | The EC-43 test runs a real capped loop and asserts the runtime's `stop_reason`. |
| INV-10 | http_failures.py → AC-6 table incl. 408/409/425/502/503/504 rows; email.py → one-connection assertion | integration | Transport default retry set used → duplicate posts. | Each row scripts exactly one response, so a retry is an unscripted request. |
| INV-11 | http_failures.py → `test_error_body_becomes_a_token_only_when_the_whole_body_is_one_safe_token` (13 rows), AC-7 test; email.py → SMTP table | contract / security | `re.match` instead of `fullmatch`, unstripped body, echoed secret kept. | Boundary rows: 64/65 chars, leading digit, hyphen, token followed by a secret, second line. |
| INV-12 | wire_contract.py → AC-9 tests | security | See AC-9. | See AC-9. |
| INV-13 | dispatch.py → AC-11 tests | integration | See AC-11. | See AC-11. |
| INV-14 | wire_contract.py → `test_body_at_its_cap_is_sent_whole`, `test_body_over_its_cap_is_cut_to_exactly_the_cap_with_the_marker_in_one_request` (one over / far over), `test_jira_description_paragraphs_come_from_the_body_capped_at_32767_characters`, `test_destinations_without_a_documented_cap_get_the_full_body`, `test_slack_escapes_after_truncation_so_no_entity_is_cut_in_half` | contract | Off-by-one at the cap, marker added past the cap, invented caps, escape before truncation. | Exactly-at-cap and one-over rows for each of the seven capped destinations. |
| INV-15 | wire_contract.py → AC-10 test, `test_title_newlines_collapse_to_one_line_so_they_cannot_inject_an_email_header` | security | Multi-line subject / `Bcc:` injection, marker in titles. | `message["Bcc"] is None` and the exact collapsed subject. |
| INV-16 | agent_wiring.py → AC-12 test | integration | See AC-12. | See AC-12. |
| INV-17 | agent_wiring.py → AC-13 test | integration | See AC-13. | See AC-13. |
| INV-18 | email.py → AC-16 (a), (b), STARTTLS-unsupported and certificate-rejected rows | security | Plaintext fallback, unverified context. | Context type, `verify_mode`, and `check_hostname` are asserted; login must never run after a TLS failure. |
| INV-19 | email.py → AC-16 (a) | concurrency | SMTP on the event loop. | The fake records `threading.get_ident()` of the SMTP session. |
| INV-20 | agent_wiring.py → AC-18 test | concurrency | See AC-18. | See AC-18. |
| INV-21 | configuration.py → AC-20 tests; agent_wiring.py → `test_jev_agent_settings_reject_a_bare_string_outputs_value`; security.py → `test_path_shaped_repo_or_site_is_rejected_before_it_can_build_a_credentialed_url` | unit | See AC-20. | See AC-20. |
| INV-22 | acceptance.py → AC-21 test; full existing suite | regression | See AC-21. | See AC-21. |
| INV-23 | agent_wiring.py → AC-14 signature assert; existing `tests/test_jev_agent.py:504-509` | contract | Constructor keyword added. | Existing pin is unmodified. |
| INV-24 | existing `tests/features/coding_agent/test_coding_agent_contract.py` | contract | `CodingAgent` signature changed. | Existing, unmodified. |
| INV-25 | existing `tests/test_restore_output_schema.py` | regression | Restore round trip broken. | Existing, unmodified. |
| INV-26 | acceptance.py → AC-4, AC-23 tests; agent_wiring.py → INV-2 drain test | integration | Delivery moved before the schema check, before recording, or after the drain. | Each position has its own observable consequence asserted. |
| INV-27, INV-28 | not pytest (AC-22 gates) | gate | Dependency or lint regressions. | Gate commands. |
| EC-1, EC-2, EC-4, EC-5 | AC-5 and AC-6 tests | integration | See AC-5, AC-6. | See AC-5, AC-6. |
| EC-3, EC-23 | AC-6 (b) row; INV-10 table (status 400 is never retried) | integration | `Retry-After` honoured or 400 retried. | Literal attempt counts. |
| EC-6 | AC-9 tests | security | See AC-9. | See AC-9. |
| EC-7 | AC-10 test | integration | See AC-10. | See AC-10. |
| EC-8, EC-9, EC-10 | AC-4, AC-8 tests | integration | See AC-4, AC-8. | See AC-4, AC-8. |
| EC-11, EC-12, EC-13, EC-14, EC-15 | AC-2, AC-20 tests, EC-15 two-instance test | unit / integration | See AC-2, AC-20. | See AC-2, AC-20. |
| EC-16 | dispatch.py → `test_render_that_raises_fails_its_connector_and_chains_the_delivery_error_from_that_exception`, AC-11 (e) | integration | Render `KeyError` crashes delivery or is not the cause. | `__cause__ is failure` (identity). |
| EC-17 | dispatch.py → AC-11 `structured-without-title` row | integration | No-title schema titled from JSON. | Exact title and body. |
| EC-18 | wire_contract.py → INV-15 test, AC-10 test | security | See INV-15. | See INV-15. |
| EC-20 | agent_wiring.py → `test_drained_follow_up_delivery_failure_is_recorded_on_the_first_reply_without_failing_it` | integration | Drained failure crashes the first run, or the stored repr carries a secret or no code. | Asserts the type name, the `slack (http_404:no_service)` fragment, and the marker's absence. |
| EC-21 | AC-12 test (every listed path runs `fork()`) | integration | See AC-12. | See AC-12. |
| EC-22 | AC-17 link table (`linear-graphql-errors`) | contract | See AC-17. | See AC-17. |
| EC-24, EC-25, EC-26 | email.py → AC-16 (c)–(e) rows | integration | See AC-16. | See AC-16. |
| EC-27 | dispatch.py → `test_two_replies_delivered_at_once_through_the_same_connector_each_post_their_own_text` | concurrency | Per-send state on the connector mixes replies. | Two different texts must both reach the wire. |
| EC-31, EC-32, EC-33 | http_failures.py → INV-11 token table and success-range test (4xx → `http_<status>`) | integration | 4xx reported as SENT or with text. | Exact codes. |
| EC-34 | http_failures.py → `test_response_over_the_size_ceiling_is_refused_as_a_network_failure` | security | 1,000,001-byte body read into memory and reported SENT. | A 2-byte row through the same MockTransport path must be SENT. |
| EC-35 | AC-25 test | security | See AC-25. | See AC-25. |
| EC-36 | dispatch.py → `test_connector_bug_inside_send_becomes_an_unexpected_receipt_and_the_others_still_send` | integration | `TypeError` in `send` aborts delivery. | Exact message and `__cause__` identity. |
| EC-37 | configuration.py → rotation test | integration | Credential re-read at send time. | Both URLs asserted on the wire. |
| EC-38 | dispatch.py → `test_finished_reply_is_delivered_…` (`no-stop-reason` row) | integration | Reply without `stop_reason` skipped. | One SENT receipt and one request. |
| EC-40 | wire_contract.py → `test_webhook_structured_mapping_with_a_non_json_value_is_failed_unexpected_type_error`, `test_webhook_structured_field_is_a_json_value_or_none` | integration | Structured payload dropped, python-mode dump, or a crash. | `datetime` serialized as `2026-10-11T09:30:00Z` only in JSON mode. |
| EC-41 | AC-7 test | security | See AC-7. | See AC-7. |
| EC-42 | AC-24 test | integration | See AC-24. | See AC-24. |
| EC-43 | agent_wiring.py → INV-9 capped-run test | integration | Capped run posts the stop notice. | Real `max_iterations=1` loop with a tool-calling model. |
| EC-47 | AC-6 (e) test | concurrency | See AC-6. | See AC-6. |
| T-1 | AC-20 no-echo rows, AC-3 test | security | See AC-3, AC-20. | See AC-3, AC-20. |
| T-2 | AC-9, INV-3, INV-15 tests | security | See those rows. | See those rows. |
| T-3 | AC-25 test | security | See AC-25. | See AC-25. |
| T-4 | INV-4 isolation test, EC-27 test | security | See those rows. | See those rows. |
| T-5 | EC-34, AC-6 (e), INV-11, AC-25 tests | security | See those rows. | See those rows. |
| D-19 | security.py → `test_path_shaped_repo_or_site_is_rejected_before_it_can_build_a_credentialed_url` (11 rows) | security | `repo` with `../`, `?`, `#`; `site` with a path, port, suffix attack, userinfo. | Each row must raise at construction and name its parameter. |
| D-20 | dispatch.py → `test_delivery_error_carries_the_full_diagnostic_packet_with_no_secret` | contract | Missing or wrong A003 packet; `details` out of sync. | Exact packet values and `details[name] == getattr(err, name)` for all eight fields. |
| D-21 | AC-17 link table | contract | See AC-17. | See AC-17. |
| FR-5 | agent_wiring.py → `test_caller_written_connector_that_only_satisfies_the_protocol_is_accepted_and_delivered`; contract.py → `test_protocol_accepts_a_caller_written_connector_and_rejects_a_plain_object`, `test_base_output_is_abstract_and_render_is_a_read_only_property`, `test_every_connector_is_a_base_output_that_satisfies_the_protocol_and_masks_its_repr` | contract | A non-`BaseOutput` connector rejected; render writable; repr not masked. | The custom connector records the exact `OutputContent` it received. |
| FR-11, FR-12 | contract.py → `test_operational_constants_hold_the_values_the_requirements_name` | contract | Named bounds drift from the requirement text. | Values compared literally; env-var map is read-only. |
| FR-18 | contract.py → `test_public_names_are_exported_from_the_agent_output_package_and_the_root`, `test_public_names_live_in_their_placement_modules`, `test_destination_and_status_values_are_the_documented_strings` | contract | Missing or extra exports; helpers exported at the root; wrong home module. | Exact name sets and object identity. |
| §9.1 | contract.py → `test_records_reject_an_invalid_receipt_naming_the_field`, `test_records_accept_valid_receipts_and_content_and_are_frozen`, `test_records_reject_blank_or_non_text_content_naming_the_field`, `test_records_reject_invalid_requests_and_smtp_settings_naming_the_field` | unit | A receipt FAILED without a code or SENT with an http URL; mutable records. | Each row names its field. |
| NFR-2 | AC-6 (e), AC-19 tests | concurrency | See those rows. | See those rows. |
| NFR-4 | AC-3 test | security | See AC-3. | See AC-3. |
| NFR-6 | AC-1 test | acceptance | See AC-1. | See AC-1. |
| NFR-7 | contract.py → `test_lib_output_modules_never_import_a_higher_layer_or_raw_http`, `test_agent_side_output_modules_import_only_the_standard_library_and_vidbyte_lib` | contract | `vidbyte/lib` importing `vidbyte.agents` (even inside a function); `agents/output` importing `vidbyte.agents.base` (cycle); raw `httpx`. | AST scan of every module (not just module level); the expected module files must exist first. |
| NFR-8 | AC-26 tests | contract | See AC-26. | See AC-26. |

## Tests deliberately NOT written
| Candidate | Why it would not earn its keep |
|---|---|
| Live requests to any destination or SMTP server | Forbidden (no network, no real credential); every seam is scripted per §13. |
| AC-19 wall-clock bound ("under 0.35 s" with two 0.2 s sends) | Timing assertions are flaky on Windows CI; the event-gated test proves concurrency structurally and fails deterministically when sends are sequential. |
| `KeyboardInterrupt` during delivery (INV-20, EC-19) | Raising it inside a loop task tears down the test's event loop; `CancelledError` exercises the same `BaseException` branch. |
| SMTP worker thread still sending after cancellation (EC-19, EC-47) | Accepted limitation (Python cannot cancel a thread); no new code to guard. |
| EC-28 receipts dropped from later checkpoints | Accepted, existing serializer behavior (D-15); asserting `__dropped__` markers would pin `SessionSerializer`, not this feature. |
| EC-29 GitHub silently dropping labels, EC-30 Teams 202 false SENT, EC-46 SES port 2465 | Destination-side behavior the SDK cannot observe; README footguns, not code. |
| EC-39 `run_sequentially` stopping on the first failure | Existing `run_sequentially` behavior for any raised error; no new code. |
| EC-44, EC-45 user agents with outputs used as Jev specialists, aggregate proposers, pipeline/workflow stages, MCP-served agents | Accepted; each runs the user's own agent, which `AC-1`/`AC-5` already cover. Rejecting such agents is Q-8 (not built). |
| INV-16 Jev bulk-work, clone, swarm, continuation agents and `Session.resume`/`fork_from` | They construct agents without `outputs=`, so the default `()` applies; a test would only re-prove the default. `restore(state).outputs == ()` (AC-13) covers the session rebuild path. |
| Q-1 to Q-10 options (Codex harness outputs, `as_tool` delivery, HMAC, session `outputs=`, render `None` skip, checkpointed receipts, YAML, specialist rejection, `implicit_tls`, `@` neutralizing) | Not built (defaults apply); the Q-5 default (non-`OutputContent` render → `unexpected:ConfigurationError`) is tested as part of AC-11 (e). |
| NG-1 to NG-12 | Non-goals. |
| `idempotency_key` presence | Not visible at `_send_once`; a missing key makes `HttpTransport` raise before any send, which AC-6 (a) catches as a `network` receipt with zero attempts. |
| `retry_count` / `retry_status_codes` / `follow_redirects` arguments directly | Not visible at `_send_once`; their behavior is asserted instead (AC-6 table, AC-25 via `MockTransport`). |
| Size checks on the existing edited READMEs (`vidbyte/agents/README.md`, `vidbyte/agents/jev/README.md`, `vidbyte/lib/README.md`) | Already enforced by `tests/test_readme_size_limit.py`; a new test would pass today (not red). |
| NFR-3 line counts, A002 intents, I001 ordering, mypy, Semgrep, `contracts/sdk-public-api.json`, `pyproject.toml` dependencies (AC-22, INV-27, INV-28, NFR-1, NFR-5) | Enforced by `python lint/run.py`, `python scripts/run_ci.py`, and `python scripts/generate-sdk-public-api.py --check`. |
| Property-based tests | No property library is a dependency; boundary tables cover the algebraic rules (cap, single line, token grammar). |
| `outputs` on each `AgentRuntimeType` (A-13) | Every runtime replies through `_generate_reply`; the linear runtime path is exercised end to end, and a per-runtime matrix would only re-run the same block. |

## Red run (before implementation)
Bootstrap: none (deps present globally); PYTHONPATH=$(pwd)

```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/features/agent_output_connectors
21 failed, 292 errors in 1.43s
```

Failure reasons, grouped (from `--tb=line`):
```
292 E   ModuleNotFoundError: No module named 'vidbyte.agents.output'
 12 ModuleNotFoundError: No module named 'vidbyte.lib.dataclasses.outputs'
  2 AssertionError: vidbyte/lib/outputs/README.md is missing
  1 AssertionError: vidbyte/agents/output/README.md is missing
  1 AssertionError: spec 12.3 rows 4-18 modules missing from vidbyte/lib/outputs: ['__init__', 'base', ...]
  1 AssertionError: assert ['__init__', ... 'dispatcher'] == []
  1 AssertionError: assert 'outputs=' in '# Agents ...'
  1 TypeError: JevAgentSettings.__init__() got an unexpected keyword argument 'outputs'
  1 ImportError: cannot import name 'GitHubIssueOutput' from 'vidbyte'
  1 AttributeError: 'OfflineTestAgent' object has no attribute 'outputs'
```

Per file (`PYTHONPATH=$(pwd) python -m pytest -q <file>`):
```
test_output_connectors_acceptance.py: 2 failed, 4 errors
test_output_connectors_agent_wiring.py: 1 failed, 10 errors
test_output_connectors_configuration.py: 81 errors
test_output_connectors_contract.py: 17 failed, 30 errors
test_output_connectors_dispatch.py: 42 errors
test_output_connectors_email.py: 15 errors
test_output_connectors_http_failures.py: 33 errors
test_output_connectors_security.py: 1 failed, 24 errors
test_output_connectors_wire_contract.py: 53 errors
```

Focused existing suites (pinned contracts) still pass:
```
$ PYTHONPATH=$(pwd) python -m pytest -q tests/test_jev_agent.py tests/features/coding_agent tests/test_restore_output_schema.py tests/test_agent_tool.py tests/test_agent_fork_isolation.py tests/test_custom_exception_constructors.py tests/test_readme_size_limit.py
202 passed, 11 skipped in 5.95s
```

Whole suite (every failure and error is in the new pack; no other test fails):
```
$ PYTHONPATH=$(pwd) python -m pytest -q
21 failed, 3203 passed, 12 skipped, 292 errors in 24.27s
```

Lint (new files staged first): `python lint/run.py` → `SDK-LINT: PASS` (A001 stays at its 643 allowance).

## Notes for the implementer
- **Names the tests import** (spec §8.5, §9.2, §12.3): `vidbyte.agents.output` (18 names in `__all__`, incl. `OutputDispatcher`), `vidbyte.agents.output.connector.OutputShaping`, `vidbyte.agents.output.dispatcher` (module attribute `OUTPUT_DELIVERY_DEADLINE_SECONDS`, imported by name), `vidbyte.lib.outputs` (`BaseOutput`, `OutputArguments`, `OutputText`, `OutputHttp`, `OutputSmtp`, 11 connectors), `vidbyte.lib.outputs.delivery.smtplib` (import `smtplib` as a module), `vidbyte.lib.dataclasses.outputs` (`OutputContent`, `DeliveryReceipt`, `OutputRequest`, `SmtpSettings`), `vidbyte.lib.enums` (`OutputDestination`, `DeliveryStatus`), `vidbyte.lib.errors.OutputDeliveryError`, `vidbyte.lib.constants.outputs`, the 17 root exports, `BaseAgent(outputs=)`, `BaseAgent.restore(outputs=)`, `JevAgentSettings(outputs=)`.
- **Files the layering test expects**: `vidbyte/lib/outputs/{__init__,base,text,delivery,slack,discord,teams,google_chat,telegram,email,github,linear,jira,notion,webhook}.py` and `vidbyte/agents/output/{__init__,connector,dispatcher}.py` (§12.3 rows 4–18, 20–22).
- **Seams**: HTTP is scripted at `HttpTransport._send_once` (kwargs `url`, `headers`, `json_body`, `timeout_seconds`, `max_response_bytes` are asserted); pass header names in lowercase. The redirect and size-ceiling tests replace `httpx.AsyncClient` with a `MockTransport`-backed client, so keep using `HttpTransport().request(...)` with `follow_redirects=False` and `max_response_bytes=OUTPUT_MAX_RESPONSE_BYTES`. SMTP is scripted by replacing `smtplib.SMTP`/`SMTP_SSL` on the module `delivery.py` imports; the fakes keep the real signatures (`SMTP(host, port, timeout=…)`, `SMTP_SSL(host, port, timeout=…, context=…)`, `starttls(context=…)`), and use the client as a context manager.
- **Exact strings the tests compare**: `f"Missing credential for {destination.value} output. Pass {parameter} or set {env_var}."`; `f"{n} of {m} outputs failed: " + ", ".join(f"{dest} ({code})")`; `repr(connector) == f"{ClassName}(credential='***')"`; error codes per INV-11; the OutputDeliveryError packet values in §12.3 row 25.
- **Parameter names in errors**: every `ConfigurationError` from a connector must name the constructor parameter (`webhook_url`, `url`, `repo`, `labels`, `team_id`, `parent_page_id`, `site`, `email`, `project`, `to`, `sender`, `port`, `host`, `chat_id`, `render`); `outputs` errors must contain the word `outputs`. Record errors (`DeliveryReceipt`, `OutputContent`, `OutputRequest`, `SmtpSettings`) must name the field.
- **Queue semantics**: outside a run, `agent._queued_prompts` is the pending list the next run claims; the AC-18 and INV-7 tests hold that list object and assert it is emptied. Clear it in the inline `except BaseException` block for every exception, not only cancellation.
- **Shaping details the tests pin**: `structured_field` reads a `Mapping` with `.get` and anything else with `getattr`; a non-`str` or blank field counts as missing; `chat_text` returns the body alone when `OutputText.first_line(body) == title`; Slack escapes after truncation; Jira paragraphs come from the truncated body's non-blank lines.
- **Validated against a throwaway prototype** written outside the repo from the spec alone: all 313 cases pass on it, the full suite passes with it (3516 passed), and 72 single-point mutations of it were run, 71 caught (the survivor, dropping the explicit single-connector check, is equivalent because a connector is not iterable and still raises the `outputs` error). Nothing from the prototype is committed.
