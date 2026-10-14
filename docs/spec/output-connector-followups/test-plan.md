# Test plan: Output connector follow-ups

Spec: `docs/spec/output-connector-followups/spec.md` r3 · Framework: pytest 8.3.5 + pytest-asyncio 1.3.0 · Prior art copied: `tests/features/agent_output_connectors/test_output_connectors_wire_contract.py` (exact wire rows), `test_output_connectors_http_failures.py` (scripted status and network outcomes, `httpx_destination` redirects and ceilings), `test_output_connectors_email.py` (worker-thread checks), `test_output_connectors_security.py` (request-log test)

All files are under `tests/features/agent_output_connectors/`. File prefixes are shortened below: `rendering` means `test_output_connectors_rendering.py`, and so on.

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | followup_acceptance → `test_followup_spec_snippet_reaches_five_destinations_and_prints_the_documented_lines` | acceptance | The §4 snippet → a missing or reordered receipt line, a POST without the GET, a summary not appended, an unsigned webhook | The printed lines are compared whole, and each destination's recorded request is checked (GET then POST, file text, `thread_name`, `sendRichMessage`, a recomputed HMAC) |
| AC-2 | rendering → `test_discord_forum_post_adds_a_one_line_thread_name_and_its_tags` | contract | A 300-character, multi-line title → `thread_name` over 100 or with newlines; tags missing; `forum=False` body changed | Exact JSON body per case, including the unchanged `forum=False` body |
| AC-3 | rendering → `test_discord_forum_arguments_are_checked_at_construction` | unit | Tags without `forum=True`, a non-digit or blank tag, a string for tags, or a non-bool `forum` → accepted, then 400 on every send | Each row must raise `ConfigurationError` naming the parameter |
| AC-4, EC-6, INV-5 | rendering → `test_slack_reply_up_to_12000_characters_is_a_markdown_block_with_an_escaped_one_line_title`, `test_slack_switches_to_todays_escaped_text_above_12000_characters`; wire_contract → `test_each_http_connector_sends_its_documented_request[slack]` | contract | At 12,000 → no block, or a block with a live `<!here>`; at 12,001 → a block Slack rejects | Exact bodies at 12,000 and 12,001; the 12,001 case is an allowed-green regression guard (unchanged path) |
| AC-5, INV-18, EC-43, EC-44 | rendering → `test_telegram_sends_rich_markdown_with_no_html_tag_and_no_media_block`, `test_telegram_neutralization_changes_only_tag_starts_and_media_brackets` | contract | `<tg-button>` or `![](…)` → a real button or fetched file; `topic_id` dropped; a `$`, a link, or a `tg://user` mention changed | Exact URL and body, plus a table of inputs that must stay untouched |
| AC-6 | rendering → `test_telegram_topic_id_must_be_a_positive_int` | unit | `True`, `0`, `-1`, `"7"` → accepted | Each must raise naming `topic_id` |
| AC-7, D-9 | rendering → `test_teams_card_has_a_bold_title_block_and_the_body_without_a_repeated_title`; wire_contract `WIRE_ROWS["teams"]`, `CAPPED["teams"]` | contract | A body that repeats its title, an empty body block, a multi-line title | Exact `body` block lists for cases a to e, and the full-width flag |
| AC-8, D-10, EC-12 to EC-14 | rendering → `test_jira_description_is_built_with_adf_blocks_in_order`, `test_jira_description_cut_inside_an_open_fence_ends_its_code_block_with_the_marker`, `test_adf_document_follows_the_block_rules_and_never_emits_empty_text` | unit + contract | `##`, `-`, `1.`, and fences sent as raw text; an empty text node Jira rejects; a heading parsed inside a code block | 16-row block table on the real `OutputAdf.document`, plus a validity check (no empty text, no marks) on every row |
| AC-9 | wire_contract → `test_each_http_connector_sends_its_documented_request[google_chat]`; followup_acceptance → `test_first_batch_connectors_keep_their_headers_and_send_no_raw_bytes[google_chat]` | regression | Google Chat gains `markupSyntax` or another field | Exact body and exact headers; green by design (behavior must not change) |
| AC-10, INV-3, INV-11, EC-15 | webhook_options → `test_webhook_sends_fixed_headers_lowercased_and_keeps_the_envelope`, `test_invalid_webhook_headers_are_refused_naming_only_safe_parts`, `test_webhook_header_values_never_reach_a_rendered_surface_when_the_receiver_echoes_them` | contract + security | A CRLF value injects a header; an error echoes a value or an invalid name; duplicates after lowercasing both sent | Each row lists names that must appear and fragments that must not |
| AC-11, EC-18, EC-19 | webhook_options → `test_webhook_payload_replaces_the_envelope_and_receives_the_reply_and_content`, `test_webhook_payload_that_raises_or_returns_a_non_mapping_fails_only_that_output`, `test_webhook_payload_with_a_value_json_cannot_encode_is_failed_unexpected_type_error`, `test_webhook_payload_must_be_callable` | contract | The payload ignored; a raising payload kills the other outputs; a non-mapping sent | The payload is a recording function whose arguments are checked; the other output's receipt must be SENT |
| AC-12, INV-8 | webhook_options → `test_signed_webhook_puts_exact_bytes_on_the_wire_with_a_verifiable_signature`, `test_signing_headers_replace_the_callers_content_type_and_signature_headers` | contract + security | A signature over re-serialized JSON; a caller's content-type or signature header kept | The signature is recomputed from the bytes httpx actually sent, with the timestamp bracketed by the clock before and after |
| AC-13 | webhook_options → `test_signed_webhook_retry_after_429_repeats_the_same_bytes_and_signing_headers`, `test_each_signed_send_gets_a_new_webhook_id` | idempotency | A 429 retry re-signs with a new id; two sends share an id | Both attempts' recorded `content` and headers are compared |
| AC-14 | webhook_options → `test_invalid_webhook_secret_is_refused_naming_secret_without_echoing_it`, `test_webhook_secret_of_24_to_64_bytes_is_accepted_with_or_without_the_prefix` | unit + security | A 23- or 65-byte key or non-base64 text accepted; the secret echoed | Boundary rows at 23/24/64/65 bytes, with and without `whsec_` |
| AC-15 | webhook_options → `test_transport_sends_content_bytes_verbatim_without_adding_a_content_type`, `test_transport_refuses_json_body_and_content_together_before_any_request` | unit (canonical helper) | Bytes re-encoded or given a content-type; both bodies sent | Real `_send_once` over `httpx.MockTransport`; asserts zero requests for the both case |
| AC-16, D-11 | comments → `test_github_comment_on_posts_the_chat_text_and_links_the_comment` | contract | A comment sent without its title, uncapped, or to `/issues` | Exact URL, body at and over the 65,536 cap, and the receipt link |
| AC-17, EC-23 | comments → `test_linear_comment_on_uses_comment_create_and_links_the_comment`, `test_linear_comment_answered_with_graphql_errors_is_failed_invalid_response`, `test_linear_labels_add_label_ids_to_the_issue_input`; wire_contract `WIRE_ROWS["linear_issue"]` | contract | `errors[]` on 200 reported SENT; a reference reformatted; labels added when none were given | Exact mutation and variables; the unchanged no-labels row stays exact |
| AC-18, EC-24, D-12 | comments → `test_jira_comment_on_posts_an_adf_comment_and_links_it_by_focused_comment_id`, `test_jira_comment_created_without_an_id_is_failed_invalid_response`, `test_jira_labels_are_added_to_the_issue_fields` | contract | A link without `focusedCommentId`; a 201 without `id` reported SENT; `issue_type` sent in comment mode | Exact ADF body, link, and fields |
| AC-19, D-13 | comments → `test_notion_append_to_patches_the_page_markdown_with_mentions_neutralized` | contract | A replace instead of an insert; a live `<mention-`; a compact id used in the URL | Exact PATCH URL (dashed id from a compact one), body, and headers |
| EC-22, EC-25 | comments → `test_comment_or_append_target_that_does_not_exist_is_failed_http_404` | contract | A 404 followed by a new issue or page | Exactly one FAILED `http_404` receipt |
| AC-20, FR-23, INV-11 | comments → `test_forbidden_or_missing_mode_combinations_name_both_parameters` | unit | `team_id` + `comment_on` accepted (ambiguous target); neither accepted, then `TypeError` | Every row requires both parameter names as whole words |
| §9.2(b), EC-41 | comments → `test_invalid_comment_targets_and_labels_name_their_parameter` | unit | A compact UUID, `PROJ12`, `proj-12`, a path, or a label with a space accepted | One row per rule |
| AC-21, D-21 | new_destinations → `test_gitlab_issue_posts_title_description_and_labels_and_links_web_url`, `test_gitlab_merge_request_note_posts_the_chat_text_and_is_sent_without_a_link`, `test_gitlab_self_managed_host_with_port_and_nested_group_path`, `test_gitlab_text_is_cut_to_its_documented_cap`; wire_contract `WIRE_ROWS["gitlab_issue"]` | contract | The path not URL-encoded; labels sent as a list; the note link invented; a cap off by one | Exact URL, header, and body; caps at and one past 1,048,576 and 1,000,000 |
| EC-26 | new_destinations → `test_gitlab_http_web_url_is_failed_invalid_response` | contract | An `http://` link reported as SENT | Exact receipt row |
| EC-27, INV-10, T-3 | new_destinations → `test_gitlab_invalid_arguments_name_their_parameter` | unit + security | `gitlab.com/evil`, `bot@gitlab.com`, `https://…`, port 0, 080, or 99999 → the token goes elsewhere or fails late | 19 rows, each named |
| AC-22, EC-30, EC-31, INV-12, D-18 | new_destinations → `test_job_summary_appends_the_chat_text_and_a_blank_line_after_what_is_there`, `test_job_summary_path_comes_from_github_step_summary`, `test_job_summary_concurrent_appends_run_off_the_loop_one_after_the_other`, `test_job_summary_text_is_cut_so_the_block_is_at_most_262144_characters`, `test_job_summary_os_error_is_failed_file_error_and_creates_nothing` | integration (real file) | An overwrite; a write on the event loop; two threads interleaving; a created directory; an `OSError` escaping | A Python audit hook records the thread that opens the file. A scratch check (not committed) confirmed that the loop and `asyncio.to_thread` variants both fail it |
| AC-36, FR-35 | new_destinations → `test_delivery_error_lists_file_error_among_codes_that_may_already_be_delivered` | contract | The resend caution omits `file_error`, so a partial append is resent blindly | Requires one item containing both `file_error` and the caution phrase |
| AC-23, D-10 | new_destinations → `test_confluence_creates_a_v2_page_with_an_adf_body_and_links_it`, `test_confluence_body_is_cut_at_500000_characters_before_it_becomes_adf`, `test_confluence_invalid_arguments_name_their_parameter`; wire_contract `WIRE_ROWS["confluence_page"]` | contract | `value` sent as an object; int ids sent as numbers; `parentId` sent as null; a link missing `/wiki` | `json.loads(value)` compared with the expected ADF; exact remaining body |
| AC-24, INV-7 | new_destinations → `test_typefully_creates_one_draft_for_the_chosen_platforms_and_never_schedules`, `test_typefully_duplicate_platforms_are_dropped_in_order_and_ids_may_be_strings`, `test_typefully_invalid_arguments_name_their_parameter` | contract | `publish_at`, `plan_at`, or `share` sent; duplicate platforms; an unknown platform accepted | Exact body equality forbids every extra key |
| AC-25, D-20 | new_destinations → `test_hubspot_creates_a_task_stamped_with_the_send_time_in_utc`, `test_hubspot_task_body_is_cut_at_65536_characters` | contract | A local-time or second-precision `hs_timestamp`; an uncapped body | Full-match pattern plus a UTC bracket around the send |
| INV-13 | new_destinations → `test_new_connector_titles_are_one_line_of_at_most_250_characters` | contract | A multi-line or 330-character title sent raw | Exact expected title per destination |
| AC-26, EC-28 | configuration → `test_every_connector_without_a_credential_names_its_parameter_and_variable`; contract → `test_every_connector_is_a_base_output_that_satisfies_the_protocol_and_masks_its_repr`, `test_public_names_are_exported_from_the_agent_output_package_and_the_root`, `test_public_names_live_in_their_placement_modules` | contract | A wrong message, a leaking repr, a missing export | The existing tests now cover the five new `CONNECTOR_CASES` rows. `--check` is a gate, not pytest |
| AC-27, D-15, INV-1 | update_in_place → `test_sticky_marked_comment_on_page_two_is_edited_after_both_reads`, `test_sticky_without_a_marker_on_a_short_page_posts_one_marked_comment` | contract | A POST after finding the marker; a write before page 2 is read | The ordered (method, URL) list is compared whole |
| AC-28 | update_in_place → `test_read_failure_is_that_reads_receipt_and_nothing_is_written` | contract | A read failure followed by a POST (a duplicate); 500 retried | 6 outcomes × 2 modes; the exact GET count and no write |
| AC-29 | update_in_place → `test_sticky_search_stops_after_ten_full_pages_then_posts` | contract | An eleventh read, or paging forever | An eleventh GET finds no scripted answer and fails the test |
| EC-39 | update_in_place → `test_sticky_marked_comment_deleted_before_the_patch_is_failed_http_404_without_a_post` | contract | A POST fallback after a failed PATCH | Exact (method, URL) list |
| D-14 | update_in_place → `test_marker_match_is_the_exact_marker_in_the_oldest_comment` | unit | `ci-review-2`, a quoted marker, or another key matched; the newest match edited | Each row names the one write it must cause |
| AC-30, FR-32 | update_in_place → `test_keyed_issue_found_skips_pull_requests_and_comments_on_the_oldest_issue`, `test_keyed_issue_missing_creates_the_issue_with_the_key_label_added` | contract | A PR commented on; the key label missing; a search endpoint used | Exact list URL and write body |
| AC-31, FR-33, D-16, T-2 | update_in_place → `test_marker_forged_in_the_reply_is_neutralized_and_only_the_own_marker_ends_the_body`, `test_marker_in_reply_text_is_neutralized_even_without_a_key`, `test_marker_is_neutralized_before_truncation_and_appended_after_it` | security | A planted marker that another key's search edits; a marker cut off by the cap; a cap overrun by the longer quoted form | Exact body; length exactly 65,536 with the marker first in the kept text |
| AC-32 | update_in_place → `test_invalid_key_or_comment_on_names_its_parameter`, `test_longest_valid_key_is_accepted_and_used_in_the_marker` | unit | A 43-character key, a slash, a colon, or `comment_on=True` accepted | Boundary at 42/43 |
| AC-33, INV-4, D-22, EC-40 | update_in_place → `test_reads_and_patches_use_the_output_transport_rules`, `test_reads_and_patches_accept_a_page_above_the_write_ceiling`, `test_reads_and_patches_refuse_a_page_over_16000000_bytes_as_network_and_write_nothing`, `test_reads_and_patches_never_follow_a_redirect`, `test_reads_and_patches_drop_the_httpx_request_log_while_the_callers_own_requests_still_log` | contract + security | A body on GET; the 1 MB ceiling on reads; no ceiling; a redirect followed; the request log left on | The real `_send_once` over MockTransport for ceilings, redirects, and the log; the 16,000,001-byte page is invalid JSON, so a missing ceiling gives `invalid_response`, not `network` |
| FR-30, §9.1 | update_in_place → `test_output_http_read_returns_parsed_json_or_a_failed_receipt`, `test_output_http_patch_sends_one_patch_and_links_the_response`, `test_output_request_holds_a_json_body_or_content_or_neither_and_hides_content`, `test_output_request_refuses_a_bad_body_naming_the_field`, `test_output_read_holds_data_or_a_failed_receipt_and_hides_data`, `test_output_read_refuses_an_inconsistent_record_naming_the_field` | unit | Both bodies set; a SENT receipt as `failure`; `data` shown in repr | The record rules are checked one at a time. The list-body case is an allowed-green regression guard |
| AC-34, INV-2 | followup_acceptance → `test_first_batch_connectors_keep_their_headers_and_send_no_raw_bytes`; wire_contract first-batch `WIRE_ROWS` | regression | A first-batch connector gains a header, loses one, or sends `content` | Exact header dicts; green by design |
| AC-35, NFR-8 | followup_contract → `test_docs_changed_and_new_provider_rows_carry_their_facts_a_link_and_the_new_date`, `test_docs_webhook_row_no_longer_says_the_request_is_unsigned`, `test_docs_teams_note_names_the_legacy_trigger_and_the_group_chat_template`, `test_docs_new_readme_sections_cover_every_named_tool_with_official_links`, `test_docs_first_spec_catalog_carries_the_corrections_and_a_revision_row`, `test_docs_no_module_header_or_readme_still_counts_eleven_connectors`; contract → `test_docs_provider_reference_has_one_dated_row_with_an_official_link_per_destination`, `test_docs_new_folder_readmes_stay_within_40000_characters` | contract (docs) | A stale row, a missing section, an undated row, "eleven connectors" left behind | Each check looks for the names and dates the spec lists, never for free prose |
| FR-29, D-2, D-19 | followup_contract → `test_new_enums_have_the_documented_members_and_live_in_lib_enums`, `test_new_classes_live_in_their_modules_and_only_the_documented_ones_are_re_exported`, `test_output_responses_read_errors_and_links_as_the_first_batch_did` | contract | An enum outside `vidbyte/lib/enums`; a helper re-exported; the moved readers changed | Module names and export lists are compared to the spec |
| INV-16 | contract → `test_lib_output_modules_never_import_a_higher_layer_or_raw_http` (now with the 7 new modules) | contract | A new module importing `httpx` or a higher layer | Red until the 7 modules exist, so the check cannot pass on files it never read |

## Tests that turn red because the shared tables grew

The extension of `factories.py`, and the §13 changes to the first-batch files, make these existing tests fail until the follow-ups are built. All failures are confined to the listed tests (55 cases).

- **New `CONNECTOR_CASES` rows:**
  - `configuration.py::test_every_connector_without_a_credential_names_its_parameter_and_variable` (10 cases);
  - `configuration.py::test_every_connector_reads_its_own_environment_variable_and_strips_it` (4);
  - `contract.py::test_every_connector_is_a_base_output_that_satisfies_the_protocol_and_masks_its_repr` (5);
  - `security.py::test_no_surface_shows_the_credential_even_when_the_destination_echoes_it` (5);
  - `security.py::test_each_credential_travels_only_in_its_own_destinations_request` (1);
  - `wire_contract.py::test_each_http_connector_sends_its_documented_request` (4 new keys).
- **§13 Slack, Teams, and Telegram shapes:**
  - `wire_contract.py::test_each_http_connector_sends_its_documented_request` (slack, teams, telegram);
  - `wire_contract.py::test_body_at_its_cap_is_sent_whole` (2);
  - `wire_contract.py::test_body_over_its_cap_is_cut_to_exactly_the_cap_with_the_marker_in_one_request` (4);
  - `wire_contract.py::test_channel_wide_mentions_are_neutralized_for_each_chat_destination`;
  - `dispatch.py::test_default_shaping_turns_each_reply_into_one_title_and_one_body` (8);
  - `dispatch.py::test_render_replaces_the_shaping_rule_for_its_own_connector_only`;
  - `acceptance.py::test_spec_snippet_delivers_one_validated_reply_to_slack_and_a_github_issue_and_prints_both_receipts`.
- **§13 contract changes:**
  - `contract.py::test_public_names_are_exported_from_the_agent_output_package_and_the_root`;
  - `test_public_names_live_in_their_placement_modules`;
  - `test_destination_and_status_values_are_the_documented_strings`;
  - `test_operational_constants_hold_the_values_the_requirements_name`;
  - `test_lib_output_modules_never_import_a_higher_layer_or_raw_http`;
  - `test_docs_provider_reference_has_one_dated_row_with_an_official_link_per_destination`.

## First-batch expectations updated (spec §13 exception)

| File:line (after the edit) | Old | New | Spec ID |
|---|---|---|---|
| `test_output_connectors_wire_contract.py:62` `WIRE_ROWS["slack"]` | `{"text": CHAT}` | `{"text": TITLE, "blocks": [{"type": "markdown", "text": CHAT}]}` | AC-4, FR-7, D-7 |
| `test_output_connectors_wire_contract.py:64` `WIRE_ROWS["teams"]` | one `TextBlock` holding `CHAT` | title block (`Bolder`, `Medium`, `wrap`), then `{"type": "TextBlock", "text": BODY, "wrap": True}`, plus `"msteams": {"width": "Full"}` | AC-7, FR-10, D-9 |
| `test_output_connectors_wire_contract.py:66` `WIRE_ROWS["telegram"]` | `…/sendMessage`, `{"chat_id", "text": CHAT}` | `…/sendRichMessage`, `{"chat_id": TELEGRAM_CHAT_ID, "rich_message": {"markdown": CHAT}}` | AC-5, FR-8, D-8 |
| `test_output_connectors_wire_contract.py:72-75` `WIRE_ROWS` | (no rows) | `gitlab_issue`, `confluence_page` (`value` is `ANY`), `typefully_draft`, `hubspot_task` (`hs_timestamp` is `ANY`), per §9.2(a) | AC-21, AC-23 to AC-25 |
| `test_output_connectors_wire_contract.py:18` and the import block | — | `from unittest.mock import ANY`; factory constants for the new rows | §13 |
| `test_output_connectors_wire_contract.py:82` `CAPPED["teams"]` | `(7_000, body[0].text, True)` | `(7_000, …["body"][1]["text"], False)` | AC-7, D-9 |
| `test_output_connectors_wire_contract.py:84` `CAPPED["telegram"]` | `(4_096, body["text"], True)` | `(32_768, body["rich_message"]["markdown"], True)` | AC-5, D-8 |
| `test_output_connectors_wire_contract.py:164` mentions test, Slack | `{"text": "&lt;!channel&gt; &amp; @everyone &lt;users/all&gt;"}` | the same `text` plus `"blocks": [{"type": "markdown", "text": "＜!channel> & @everyone <users/all>"}]` | INV-5, D-7 |
| `test_output_connectors_wire_contract.py:169` mentions test, Telegram | `{"chat_id", "text"}` | `{"chat_id", "rich_message"}` | AC-5 |
| `test_output_connectors_dispatch.py:125` | `{"text": slack_text}` | `{"text": title, "blocks": [{"type": "markdown", "text": slack_text}]}` | AC-4 |
| `test_output_connectors_dispatch.py:148` | `{"text": "# Heading\nrest"}` | `{"text": "Heading", "blocks": [{"type": "markdown", "text": "# Heading\nrest"}]}` | AC-4 |
| `test_output_connectors_acceptance.py:97` | `{"text": f"{BUG_TITLE}\n\n{BUG_BODY}"}` | `{"text": BUG_TITLE, "blocks": [{"type": "markdown", "text": f"{BUG_TITLE}\n\n{BUG_BODY}"}]}` | AC-4 |
| `test_output_connectors_contract.py:41` `ROOT_NAMES` | 18 names | `TypefullyPlatform` inserted after `OutputDestination` | FR-29 |
| `test_output_connectors_contract.py:55-59` `ROOT_NAMES` | — | the 5 connectors appended | FR-29 |
| `test_output_connectors_contract.py:61` | `CONNECTOR_NAMES = ROOT_NAMES[7:]` | `ROOT_NAMES[8:]`, so the slice still holds only connectors after `TypefullyPlatform` (§13 "must still hold only connectors") | FR-29 |
| `test_output_connectors_contract.py:63` `LIB_OUTPUT_MODULES` | 15 modules | plus `adf`, `github_api`, `gitlab`, `github_job_summary`, `confluence`, `typefully`, `hubspot` | INV-16 |
| `test_output_connectors_contract.py:72,74` | "18 root names"; `len(...) == 18` | "24 root names (follow-ups FR-29)"; `== 24` | FR-29 |
| `test_output_connectors_contract.py:104` | 11 destination values | plus the 5 new values in order | §8.5 |
| `test_output_connectors_contract.py:317` docs date | `"2026-10-11" in row` | `("2026-10-11" in row or "2026-10-14" in row)` | AC-35 |
| `factories.py` | 11 cases, 10 HTTP keys, 11 env vars | 16 cases (Confluence on `acme-wiki.atlassian.net`; job summary path in a missing `S3CRET` directory), 14 HTTP keys, 16 env vars; `HttpxRequests` routes may be callables | §13 factories |

No expectation outside the §13 list was changed.

## Tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| Plain-text fallback after a Telegram 400 or a Slack 4xx | Q-1 to Q-8 are not built; a test would pin behavior the spec rejects |
| Google Chat `markupSyntax` | D-24: not built; AC-9 pins its absence |
| Live vendor checks L-1 to L-n (Slack block mentions, Telegram channel posts, Confluence and Typefully acceptance) | They need real workspaces and credentials, which are forbidden |
| The 35-second deadline cutting a sticky read, a write, or a job-summary append (EC-38, EC-45, EC-46) | The dispatcher deadline is already proven for every connector by `dispatch.py`; these rows are documented limits with no new code |
| Sticky and per-key races, the planted-marker branches, and labels dropped without push access (EC-35 to EC-37, EC-42) | They are vendor-side or concurrency limits the spec documents rather than prevents |
| Vendor rejections (EC-32 to EC-34) | These are status mappings that `http_failures.py` already proves for every destination |
| `OutputHttp.read` of a JSON object | Ambiguous: FR-30 says `read` returns the parsed JSON, while §9.2(c) puts "not a list of objects" among the read failures. The sticky and keyed tests (AC-28, json-object row) pin the observable result, `invalid_response`, whichever layer checks it |
| `GITHUB_JOB_SUMMARY_WRITERS == 1` and other constant getters | A getter test cannot fail independently of the behavior tests that use the constants |
| `scripts/generate-sdk-public-api.py --check`, Semgrep, and lint (AC-26 part, §12.4) | These are gates run by their own commands |
| Property-based generation | `hypothesis` is not installed and must not be added; boundary tables cover the same rules |

## Red run (before implementation)

Bootstrap: none needed.

```text
PYTHONPATH=$(pwd) timeout 600 python -m pytest -q tests/features/agent_output_connectors/test_output_connectors_rendering.py
55 failed, 1 passed in 0.71s        (the passing case is the allowed-green Slack 12,001 regression guard)
… test_output_connectors_webhook_options.py      → 41 failed in 0.45s
… test_output_connectors_comments.py             → 36 failed in 0.40s
… test_output_connectors_new_destinations.py     → 67 failed in 0.76s
… test_output_connectors_update_in_place.py      → 55 failed, 1 passed in 0.77s   (the OutputRequest list-body guard)
… test_output_connectors_followup_acceptance.py  → 1 failed, 10 passed in 0.30s   (the 10 AC-34 header guards)
… test_output_connectors_followup_contract.py    → 24 failed in 0.34s

PYTHONPATH=$(pwd) timeout 900 python -m pytest -q tests/features/agent_output_connectors
334 failed, 326 passed in 6.33s
  = 279 new-file failures + 55 existing-file failures listed above; 326 = 314 untouched or still-valid first-batch cases + 12 allowed-green guards

PYTHONPATH=$(pwd) timeout 600 python -m pytest -q tests/test_web_operation_client_retry.py
3 passed in 0.71s

timeout 900 python lint/run.py | tail -n 15
SDK-LINT: PASS   (no finding in the new or edited test files for A001, A002, S001, S017, S025, S051, S054, S060, S061, S062, S063, S064 with --all)
```

Every new failure is a `TypeError` for an unknown keyword (`forum`, `topic_id`, `headers`, `payload`, `secret`, `comment_on`, `labels`, `append_to`, `key`, `content`). Some are an `AttributeError` for a missing class or method (`OutputAdf`, `GitLabIssueOutput`, `OutputHttp.read`, `OutputRead`, `OutputResponses`, `OutputMethod`). The rest are an `AssertionError` on today's request shape (Slack, Telegram, Teams, Jira bodies, GitHub markers) or on today's docs. No failure comes from a test's own setup.

## Notes for the implementer

- **Names the tests bind to:**
  - `vidbyte.agents.output`: `GitLabIssueOutput`, `GitHubJobSummaryOutput`, `ConfluencePageOutput`, `TypefullyDraftOutput`, `HubSpotTaskOutput`, `TypefullyPlatform`.
  - `vidbyte.lib.enums`: `OutputMethod`, `TypefullyPlatform`.
  - `vidbyte.lib.outputs`: `OutputAdf.document`.
  - `vidbyte.lib.outputs.delivery`: `OutputHttp.read`, `OutputHttp.patch`, `OutputResponses.error_code`, `OutputResponses.link`, each in its module's `__all__`.
  - `vidbyte.lib.outputs.github_api`: `GitHubRequests`, `GitHubResponses`.
  - `vidbyte.lib.dataclasses.outputs`: `OutputRead(failure=, data=)`; `OutputRequest(..., content=)`.
  - `HttpTransport.request(content=)`.
  - The connector keywords of §8.5, and the module paths in `NEW_CONNECTOR_MODULES`.
- **Errors:** every record and constructor error must be `ConfigurationError` naming the parameter or field as a whole word (`\b<name>\b`). Combination errors must name both parameters.
- **Fixtures relied on:** `fake_http` (keyed by URL fragment, consumed in order), `httpx_destination` (routes keyed by host, optionally callable), `tmp_path`, `caplog`, `capsys`, `monkeypatch`, and the five new `CONNECTOR_CASES` rows. Keep Confluence on a site distinct from Jira's, and keep the job-summary case path in a missing directory.
- **The job-summary thread check:** it uses a Python audit hook on `open`. It works with any implementation that opens the file through `LocalFileSystemBackend.append_text` on the single-worker `_SUMMARY_EXECUTOR`. Do not open the file on the event loop, and do not use `asyncio.to_thread`: both fail the test (checked in scratch).
- **GitHub reads:** the sticky tests script `"/issues/412/comments?per_page"` for GETs, `"/issues/comments/"` for PATCHes, and `"/issues/412/comments"` for the POST. The read URL must carry `?per_page=100&page=<n>` exactly, and the keyed list query must be exactly the §9.2 string.
- **The HubSpot timestamp** must be UTC with milliseconds and `Z`, taken at send time.
- **Do not change** `WIRE_ROWS` first-batch rows, the `ANY` cells, or any test file. If a test looks wrong, report it with the test name and the spec line (§14).
