# Test plan: InfiniteMemoryAgent context economy

Spec: `docs/spec/infinite-memory-context-economy/spec.md` r3 · Framework: pytest 8.3.5 + pytest-asyncio 1.3.0 (`--strict-config --strict-markers`), `unittest.TestCase` for the root-level shared-piece modules, plain pytest functions in the two feature packs · Prior art copied: `tests/test_filesystem_tools.py` (item 1), `tests/test_deterministic_compaction_middleware.py` and `tests/test_context_compaction_middleware.py` (items 2 and 4), `tests/test_code_search_tools.py` (item 3), `tests/features/coding_agent/test_bash_tool_contract.py` and `test_bash_tool_process_bounds.py` (item 6), `tests/test_folder_usage.py` (item 8 helper), `tests/test_output_schema_provider_dialect.py:143` and `tests/features/sdk_managed_text/test_managed_text_wire_contract.py` (item 9), `test_infinite_memory_delegation.py` and `test_infinite_memory_workspace.py` (items 5, 7, 8, 10).

Files, by short name:

| Short name | File |
|---|---|
| RLW | `tests/test_read_lines_window.py` |
| CW | `tests/test_compaction_windows.py` |
| GSC | `tests/test_grep_smart_case.py` |
| FTI | `tests/test_fulltext_index.py` |
| ACB | `tests/test_anthropic_cache_breakpoints.py` |
| BHT | `tests/features/coding_agent/test_bash_tool_head_tail.py` |
| ECO | `tests/features/infinite_memory_agent/test_infinite_memory_economy.py` |
| STP | `tests/features/infinite_memory_agent/test_infinite_memory_stable_prefix.py` |
| SRCH | `tests/features/infinite_memory_agent/test_infinite_memory_search.py` |
| RCL | `tests/features/infinite_memory_agent/test_infinite_memory_recall.py` |
| changed | the deliberately changed existing tests of spec §13, each marked in code with a comment citing its spec ID |

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | RLW → `test_section_4_snippet_prints_exactly_the_three_documented_lines` | e2e (subprocess) | the §4 snippet raises, or prints other text, on this checkout | It runs the snippet in a fresh interpreter from an empty folder with this worktree first on `PYTHONPATH`, and compares the whole stdout with the three lines. An installed older `vidbyte` cannot satisfy it, because the snippet uses names main lacks. |
| AC-1.1 | RLW → `test_a_long_file_returns_the_window_then_a_footer_naming_the_next_start` | unit | a 1,000-line read with only `path` returns every line, or a footer with the wrong numbers | The expected output is built from the file's own lines plus the literal footer. Main returns 1,000 lines, so the test is red now. |
| AC-1.2 | RLW → `test_a_range_within_the_window_is_identical_to_main_with_no_footer` | unit | a short read gains a footer or a changed metadata value | Compared with main's output rebuilt from the same lines, at 50 lines and at exactly 200. The `truncated` and `next_start` keys must be present with `False` and `None`; main has neither key, so the test is red now. |
| AC-1.3 | RLW → `test_a_range_running_past_the_end_returns_the_rest_without_a_footer` | unit | `start=950, end=2000` is refused or footed | Exact lines 950–1000 and the metadata of INV-1.4. |
| AC-1.4 | RLW → `test_without_a_window_output_metadata_and_spec_equal_main` | unit | the new option changes a caller without a window | Compares output, metadata keys, and the spec description with main's literal values copied into the test, so a changed default fails. |
| AC-1.5 | RLW → `test_a_bad_window_is_refused_naming_the_field`; ECO → `test_the_workspace_read_window_validates_and_reaches_read_lines` | unit + agent | 0, −1, `True`, 2.5 accepted, or refused without the field name; a custom window never reaches the root | `FileSystemToolConfig` must refuse each bad value with LineLimit's shared text naming `max_read_lines`. `InfiniteWorkspaceSettings` must refuse each with an error naming `InfiniteWorkspaceSettings.max_read_lines`. A window of 50 must show in the root's actual `read_lines` result. |
| AC-1.6 | ECO → `test_every_agent_reads_a_long_note_in_a_200_line_window_with_a_footer` | agent | a generator or verifier reads without a window | The whole result string for the root, the generator, and the verifier is compared with 200 lines plus the footer. |
| FR-1.3 | ECO → `test_a_custom_read_window_reaches_every_agents_read_lines_including_the_retrievers` | agent | a child or the retriever keeps 200 when the workspace says 50 | In DELEGATED mode with `max_read_lines=50`, the root, the generator, the verifier, and the retriever each read from line 101. Each result must be lines 101–150 plus the footer; a fixed 200 gives 101–300. |
| AC-2.1 | CW → `test_a_scope_compacts_only_the_named_tools_and_keeps_the_newest_per_tool`; ECO → `test_the_root_masks_the_two_oldest_of_five_grep_outputs_and_keeps_every_call` | unit + agent | the wrong outputs are masked, or a call input is changed | The agent case compares the sixth call's five grep outputs with `[leaf, leaf, out3, out4, out5]`, where each `out` is what the call right after it saw. It also checks the five call arguments. The placeholder is the catalog leaf, never a literal. |
| AC-2.2 | ECO → `test_only_read_lines_outputs_are_masked_among_launch_bash_and_remember_results` | agent | masking hides launch cards, bash, or remember replies | The root makes `INFINITE_MASK_KEEP_RECENT + 1` launch, bash, and remember calls each, so main's unscoped window (`tools=()`) would mask the oldest of each. Each such result in the final call must equal the result the call right after it saw. A reference with an unscoped root window fails it. |
| AC-2.3 | CW → `test_the_builder_with_no_new_arguments_equals_main` | unit | the builder's defaults change | The oldest output must be cut at 600 characters with main's marker (keep 2 per tool), and the explicit default keywords must give the same view. |
| AC-2.4 | ECO → `test_masking_runs_before_the_trim_so_a_masked_view_under_the_cap_keeps_every_call` | agent | the trim runs on the raw view and drops calls masking would have kept | A precondition asserts that the raw outputs alone exceed 90,000 tokens. All ten calls must survive, the oldest seven masked. |
| AC-3.1 | GSC → `test_a_lowercase_pattern_ignores_case_and_an_uppercase_one_matches_exactly`; ECO → `test_every_agents_workspace_grep_is_smart_case_with_no_context_lines` | unit + agent | a lowercase pattern misses `Enterprise plan`, or context lines appear | The exact result `notes/plans.md:3\n3: Enterprise plan 999 USD` for the root, plus the generator's and verifier's own exact hits. |
| AC-3.2 | same two tests | unit + agent | an uppercase pattern ignores case | `ENTERPRISE` must give exactly `No matches found.` |
| AC-3.3 | GSC → `test_a_letter_after_a_regex_backslash_does_not_count_as_uppercase` | unit | `\S` makes the search case-sensitive | `\Senterprise`, `\Aenterprise`, and other escapes must match the capitalised line. |
| AC-3.4 | GSC → `test_grep_built_without_the_new_options_equals_main` | unit | the defaults change grep's output or spec | Compared with main's spec sentence and outputs, including two context lines. |
| AC-4.1 | CW → `test_a_91k_history_keeps_one_suffix_between_65_5k_and_66k` | unit | the cut is not quantized, or the suffix is not contiguous | Groups of at most 500 tokens are measured by the trim's own counter. The kept set must be one contiguous suffix in (65,500, 66,000]; main keeps about 90,000. |
| AC-4.2 | CW → `test_appending_up_to_24k_more_keeps_the_same_first_message` | unit | the cut moves within one band | The first kept message is compared by identity before and after 24,000 appended tokens. |
| AC-4.3 | CW → `test_without_a_low_watermark_the_trim_equals_main` | unit | the fallback changes main's non-contiguous keep | Main's algorithm is copied into the test as `_main_trim` and compared over 200 seeded histories. The test also checks that some of them really keep a non-contiguous set. |
| AC-4.4 | ECO → `test_with_equal_outputs_the_cut_moves_at_most_once_per_s_tokens_appended` | middleware pair | the root's pair moves its cut on almost every call | Uses the root's own two middleware objects. The test needs at least two moves, so it cannot pass with no trimming. Main moves 118 times against a bound of 27; a scratch INV-4.2 reference passes it. |
| AC-4.5 | ECO → `test_one_masking_dip_moves_the_cut_back_once_and_forward_once` | middleware pair | a dip never returns, or moves the cut more than twice | The dip point is found by probing a copy, then made real. It must move the cut back, then exactly one forward move must follow. This fails on main and passes against the reference. |
| AC-5.1 | ECO → `test_passed_and_fixed_cards_are_compact_while_failed_unchecked_and_partial_cards_stay_whole`; changed → `test_infinite_memory_delegation.py::test_two_tasks_run_concurrently_and_each_verifier_follows_its_own_generator` | agent | a passed card still carries its review and files | The whole launch result is compared with the five cards rebuilt from the journal. A literal check pins `- alpha: done, verdict passed, entries #1\nALPHA-SUMMARY`. |
| AC-5.2 | same ECO test | agent | a failed, unchecked, or partial card is compacted | The full cards are rebuilt from the `result_card` leaf. The partial pair has a `passed` verdict, so a rule that only reads the verdict fails. |
| AC-5.3 | ECO → `test_a_replayed_passed_card_is_the_label_then_the_compact_card` | agent | a replay shows the full card, or drops the label | Both launch results are compared as whole strings. |
| AC-6.1 | BHT → `test_sixty_thousand_bytes_keep_the_first_and_last_25000_with_10000_counted_between` | unit (real bash) | the tail is dropped or the count is wrong | The bytes are known 12-byte numbered lines, so the head, marker, and tail are exact slices. |
| AC-6.2 | changed → `test_bash_tool_contract.py::test_large_output_keeps_the_first_bytes_counts_the_rest_and_memory_stays_bounded` | unit (real bash) | 20 MB is held in memory, or the last line is lost | The peak-memory bound is kept, the whole output is compared, and `splitlines()[-2]` is the command's last line. |
| AC-6.3 | BHT → `test_output_within_the_cap_equals_main_even_with_a_character_across_the_head_tail_edge` | unit | a short output changes, or a split character is mangled | A two-byte character sits across bytes H−1..H at exactly the cap. |
| AC-6.4 | BHT → `test_timeout_after_exactly_the_cap_shows_every_byte_then_the_stopped_line_and_no_marker` | unit (real bash) | a marker with a count of 0 appears | The whole error output is compared. |
| AC-6.5 | BHT → `test_small_caps_split_into_a_head_and_a_tail_by_the_spec_formula` (3 cases) | unit (real bash) | the split ignores `BASH_MAX_OUTPUT_BYTES // 2` | Covers (1000, 500/500), (1001, 501/500), and a patched tail of 100 (900/100). |
| AC-7.1 | STP → `test_one_root_run_keeps_one_system_string_and_one_tool_list_while_children_keep_their_block` | agent | the root's system or tool schemas change between calls | The set of system strings and the `raw_tools` lists must each hold one element, across note, entry, bash, and launch iterations, and none may contain `max_iterations:`. |
| AC-7.2 | STP → `test_each_tool_iteration_appends_one_status_message_with_the_changed_map_lines_and_the_loop_block` | agent | no status message, or a wrong change line or counter | Exact messages are rebuilt from the `map_update` leaf, the workspace's own map lines, `INFINITE_MAP_REMOVED_LINE`, and the loop block rendered by `AgentRuntime._render_loop_settings_block`. |
| AC-7.3 | STP → `test_one_root_run_keeps_one_system_string_and_one_tool_list_while_children_keep_their_block` | agent | children lose their loop block or their map | The generator's and verifier's first systems must hold `- max_iterations: 0/500` and the map header. |
| AC-7.4 | STP → `test_a_report_over_the_map_cap_is_cut_by_the_maps_rule_and_its_left_out_lines_are_never_repeated` | agent | one 1,000-file iteration sends an uncapped report | The report must equal main's cut (copied as `_main_cut`) of the change lines. A precondition asserts the overflow. The next report must name only the newer change. |
| AC-7.5 | STP → `test_each_tool_iteration_appends_one_status_message_with_the_changed_map_lines_and_the_loop_block` | agent | a quiet iteration sends a map update, or nothing | The message after `echo_text` must be exactly the loop block. |
| AC-8.1 | SRCH → `test_an_entry_hit_comes_first_as_id_and_kind_and_the_last_line_counts_shown_and_total` | tool | an entry ranks below a long note line, or the totals are wrong | bm25 ranks the shorter row first. The hit order and the integers of the last line are both checked. |
| AC-8.2 | SRCH → `test_fts5_syntax_in_a_query_is_searched_as_text_and_never_raises` | tool | FTS5 syntax raises, or acts as an operator | `price:59` must hit its line, and `zeta OR acme` must match nothing (OR is a word). |
| AC-8.3 | SRCH → `test_a_note_bash_writes_after_a_search_is_found_by_the_next_search` | agent | the index is stale after a bash write | The first search must miss and the second must hit the exact line. |
| AC-8.4 | SRCH → `test_without_fts5_the_tool_returns_fts5_unavailable_naming_fts5_and_the_version`, `test_without_fts5_the_agent_still_runs_and_grep_still_works` | tool + agent | a missing FTS5 raises, or kills the run | FTS5 is refused only at table creation, through FTI's `without_fts5()`. Building the workspace and the tool must still succeed. |
| AC-8.5 | SRCH → `test_at_most_ten_hits_are_shown_with_snippets_of_at_most_twelve_tokens` | tool | more than 10 hits, or long snippets | 30 matching rows; the word tokens after each hit label are counted. |
| AC-8.6 | SRCH → `test_a_word_no_row_holds_gives_only_the_total_line_with_zero_of_zero` | tool | the words are ORed | Exactly one output line, with 0 of 0. |
| AC-8.7 | SRCH → `test_one_index_serves_the_whole_tree_and_every_search_sees_the_disk_at_call_time` | agent | each agent builds its own index | `FullTextIndex.__init__` is counted at the class; each agent's search sees a file written just before it. |
| AC-9.1 | ACB → `test_a_repeat_marks_the_system_the_last_message_and_the_message_before_the_newest_assistant` | adapter | a first body differs from main, or a repeat is marked wrongly | The first body's JSON equals main's literal body (`MAIN_BODY_JSON`). Every mark position is compared. |
| AC-9.2 | ACB → `test_an_agent_whose_system_changes_every_call_sends_no_marks`, `test_adapter_level_a_system_that_changes_every_call_is_never_marked` | agent + adapter | marks on a per-call system | A positive control in the same test shows that a real repeat is marked. |
| AC-9.3 | ACB → `test_caller_supplied_cache_control_anywhere_stops_all_marking` | adapter | marks added beside a caller's | Covers `extra_body`, a message block, and a tool. |
| AC-9.4 | ACB → `test_a_repeat_body_passes_the_gateway_rule_and_adds_no_top_level_key`, `test_a_gateway_run_forwards_the_marked_repeat_body` | adapter + runner | a mark the gateway refuses, or a new top-level key | `_require_short_cache` is restated from the backend, `EMITTED_KEYS` is imported, and the AUTO-mode envelope is read at the transport. |
| AC-9.5 | ACB → `test_the_callers_messages_are_never_marked_and_marks_never_pile_up` | adapter | caller lists mutated, so marks pile up | Four payloads from one config; deep snapshots before and after. |
| AC-10.1 | RCL → `test_each_agent_is_offered_its_modes_tools[direct]` | agent | `recall` offered by default, or `search_memory` missing | Exact offered sets for the root, the generator, and the verifier. |
| AC-10.2 | RCL → `test_each_agent_is_offered_its_modes_tools[delegated]` | agent | grep kept or recall missing for the root and generators; the verifier changed | The same exact sets, with grep swapped for recall in two roles. |
| AC-10.3 | RCL → `test_a_recall_card_holds_only_text_copied_from_disk_under_its_code_built_labels` | agent | the retriever's words or reasons reach the card | The card is parsed field by field through the `recall_card` leaf. After the two disk blocks are removed, the found section must be empty, and why text and prose must be absent. |
| AC-10.4 | RCL → `test_every_invalid_citation_is_listed_as_rejected_and_only_the_valid_one_is_transcribed` | agent | a bookkeeping, outside, missing, or overlong citation is transcribed, or one bad line fails the recall | Eleven rejected lines must each be named once. The found section must equal the one valid block. |
| AC-10.5 | RCL → `test_a_recall_refused_for_validation_costs_nothing_and_the_quota_counts_failed_attempts` | agent | the quota is unenforced, refused calls cost quota, or errors are free | Exactly `INFINITE_RECALLS_PER_AGENT` retriever calls. The 11th recall is refused, and its problem text names the quota. |
| AC-10.6 | RCL → `test_the_registry_names_main_tools_in_direct_and_adds_recall_and_withholds_grep_in_delegated` | unit | DIRECT changes a registry row | Main's table is copied as literals for every preset and role. |
| AC-10.7 | RCL → `test_a_card_over_its_cap_cuts_the_found_text_to_a_prefix_of_the_disk_and_keeps_the_other_sections` | agent | the card is over the cap, or the cut drops the not-found and search lines | A precondition asserts that the range alone exceeds the cap. The found text must be a non-empty prefix of the disk text. |
| AC-10.8 | RCL → `test_terms_are_searched_one_by_one_in_order_before_the_retriever_starts` | agent | the terms are ANDed together, or run out of order | Oracle hits come from a fresh `search_memory` over the same disk. Each must follow its own term in the retriever's first message. |
| INV-0.4, INV-4.5, FR-2.2, NFR-2.1 | ECO → `test_every_agent_masks_first_then_trims_with_the_low_watermark_then_limits_delegation`; RCL (retriever middleware, inside the AC-10.3 test) | agent objects | wrong order, missing masking, or a trim at 90K | Proved by behaviour on each agent's own middleware objects: the leaf placeholder and scope, and 182 messages of 500 tokens trimmed to exactly 132 (main keeps 180). |
| INV-1.2–1.7 | RLW (the window, range, error, and spec tests above) | unit | footer arithmetic, metadata, spec sentence | Literal expectations. |
| INV-2.1–2.5 | CW → `test_without_a_scope_every_tools_older_outputs_are_compacted_as_on_main`, `test_masking_is_a_pure_function_of_its_input`, `test_a_blank_scope_name_is_refused_at_construction`, `test_the_builder_forwards_the_placeholder_and_the_scope`, `test_the_engine_forwards_tools_and_placeholder_options` | unit | scope leaks, impure view, forwarding gaps | A deep copy of the input is compared after the call. |
| INV-3.3, EC-3.2 | GSC (context-line, clamp, non-ASCII, option, and spec tests) | unit | context default, clamping, `isupper` on non-ASCII | Literal outputs. |
| INV-4.2, INV-4.3, EC-4.5 | CW → `test_the_quantized_cut_matches_inv_4_2_on_random_histories` | unit (seeded property) | any group split, or a wrong prefix | A direct transcription of INV-4.2 is the oracle over 300 seeded histories with tool groups, parallel results, system groups, and B < 0. |
| INV-5.4 | ECO compact-card test | agent | the journal loses the review or files | `pair_finished` must still hold the review and `notes/alpha.md`. |
| INV-6.3 | changed bash contract test (traced peak) | unit | unbounded buffer | The peak-memory bound from main is kept. |
| INV-6.4, EC-6.3 | BHT → `test_timeout_after_more_than_the_cap_shows_the_head_the_count_so_far_the_tail_and_the_stopped_line`; changed → `test_bash_tool_process_bounds.py::test_endless_printer_times_out_with_the_first_bytes_and_a_truncation_marker` | unit (real bash) | the count is lost on timeout | The changed endless-printer test is POSIX-only and is skipped on this Windows host (see below). |
| INV-6.5, INV-6.6 | BHT → `test_bash_constants_keep_their_values_and_the_tail_constant_is_25000`, `test_bash_spec_rewords_one_sentence_to_say_the_first_and_last_bytes_are_kept_and_the_rest_counted` | unit | changed constants, or the spec still says "first bytes" | Main's four unchanged sentences must survive word for word. |
| INV-7.6 | STP → `test_a_caller_system_option_still_replaces_the_root_prompt_and_status_messages_still_arrive` | agent | the `system=` option is ignored, or status messages stop | Every system equals `CALLER-SYSTEM`. |
| FR-7.2, §9.1 | STP → `test_the_map_snapshot_and_the_lifted_cut_render_map_text_unchanged`, `test_a_map_snapshot_refuses_duplicate_paths_and_a_non_text_header`, `test_the_removed_line_label_is_the_spec_format` | unit | `map_text` changes, or the snapshot is capped | `fit_map_lines` must equal main's copied cut on 1,200 notes, with the overflow line asserted. |
| INV-8.1, 8.4, 8.5, 8.8, 8.9, FR-8.5–8.7 | SRCH (spec, refresh, exclusion, malformed-line, read-only, worker-thread, reserved-name tests) | tool + agent | writes, stale index, leaked bookkeeping, a crash on a bad line, the event loop blocked, the refresh and the search under two holds of the lock | A byte snapshot of the workspace. `RecordingIndex` probes the lock from a third thread, and its lock is a `CountingRLock` that counts outermost holds. A worker pool reuses its thread, so a thread id alone cannot show one span; one search must add exactly one hold. |
| EC-8.7, INV-8.2 | SRCH → `test_a_blank_query_is_refused_and_a_punctuation_only_query_matches_nothing` | tool | a word with no letter or digit is quoted into the MATCH | SQLite 3.38 matches nothing for an empty phrase, so results alone cannot show the drop. The real `match_expression` is wrapped, unchanged, to record each expression it builds, and every quoted phrase must hold a letter or digit. |
| INV-8.2, 8.3, 8.6, §9.1 | FTI (query, ranking, limit, snippet, refresh, lifecycle, record tests) | unit | the helper's contract | FTS5 runs for real; a missing FTS5 is simulated only at `sqlite3.connect`. |
| INV-9.2, 9.6, EC-9.2, 9.8, FR-9.1 | ACB (seen-memory, limit, stable-system, thinking-block, empty-system, stream tests) | adapter | the repeat gate and its bound | Exact JSON comparisons. |
| INV-10.3, FR-10.5, NFR-10.3 | RCL AC-10.3 test | agent | the retriever gets bash or memory tools, the wrong system, no map, or no window | The offered set, the system substring, the map header, the 200-line read result, and its two middleware objects are all checked. |
| INV-10.6, INV-10.7, NFR-10.2, EC-10.1, EC-10.3 | RCL quota test; `test_the_retriever_stops_after_its_iteration_cap_and_its_searches_are_listed` | agent | an unbounded retriever, an unlisted search, an error that costs nothing | Eight scripted greps; a ninth call would be unscripted and fail `assert_complete`. |
| INV-10.8, FR-10.6 | RCL → `test_a_recall_adds_its_usage_to_the_run_but_never_counts_toward_max_agents_or_the_journal` | agent | the recall counts as an agent, writes the journal, or its usage is lost | `max_agents` is at its minimum of 2, with one pair after the recall. Every scripted call carries its own usage, and the run's totals must be the sum of the six calls; without the retriever's call they would be (3,230, 323). |
| INV-10.9, EC-10.4, rows 36–40 | RCL → `test_the_recall_spec_is_internal_read_only_and_built_from_the_five_leaves` | unit | the spec is not internal, or the descriptions are not the leaves | The schema the model receives is read through `ToolsFormatter.input_schema`. |
| §9.1 records, D-16, EC-10.7 | RCL → `test_a_recall_request_refuses_blank_text_and_too_many_or_blank_terms`, `test_a_citation_parses_the_three_reply_forms_and_refuses_bad_numbers` | unit | loose parsing, or a refused number that crashes | Decorations, case-sensitivity, an anchored keyword, and refused numbers. |
| EC-10.5, FR-10.9 | RCL → `test_a_developer_tool_named_recall_is_refused`; SRCH → `test_a_developer_tool_named_search_memory_is_refused` | settings | a developer tool shadows a reserved name | `ConfigurationError` naming the tool. |
| INV-10.7 (leaf order) | RCL → `test_the_recall_card_leaf_renders_its_fields_in_the_spec_order` | unit | `{found}` not last, so the cap cuts the wrong section | Placeholder order read from the catalog. |
| FR-8.1, FR-10.7 | changed → `test_infinite_memory_contract.py::test_prompt_family_has_exactly_the_fifty_documented_leaves`, `test_root_is_offered_exactly_the_preset_tools_plus_its_extra`; `test_infinite_memory_delegation.py` `MEMORY_TOOLS` | contract | a missing leaf or tool | Exact sets, as before. |
| INV-7.2, INV-7.3 | changed → `test_infinite_memory_workspace.py::test_every_agent_sees_the_map_and_the_roots_map_refreshes_after_each_tool_iteration` | agent | the root map redrawn, or the change never reported | The set of root systems has one element, and the status message names the new note and its description. |
| NFR-0.2, D-18 (r4) | changed → `test_infinite_memory_contract.py::test_new_modules_stay_inside_the_complexity_budget`; RCL → `test_the_recall_spec_is_internal_read_only_and_built_from_the_five_leaves` (imports `InfiniteRecallTool` from `vidbyte.agents.infinite.recall`) | contract | `recall.py` is missing; the package has a 10th `.py` file; or any of the 13 listed modules is over 400 lines after its header | The test reads the real files and counts lines after the AST docstring. It is red on main only because `recall.py` is missing (the HEAD version passed on main). A scratch reference shaped as D-18 passes it: 9 files, with `memory.py` at 271 lines and `recall.py` at 182 after their headers. |
| INV-9.3, EC-9.10 (r4) | changed → `tests/test_prompt_sits_at_run_boundary.py::CompactedRunBoundaryTests::test_a_top_note_replaced_by_the_trace_keeps_the_task_before_the_run_on_every_wire` | agent + adapter (scripted transport) | on any of the three wires, the task turn moves behind the first call or appears twice | The helper accepts exactly two forms: the plain string, and the one text block with `cache_control: {"type": "ephemeral"}`. Any other shape is not the task, so `len(tasks) == 1` fails. The assertions are unchanged. The test is green on main, because main sends no marks and the string form matches. Against the Anthropic reference, the HEAD helper fails and the new helper passes. |

## Tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| NFR-0.5 and G-1's real-key `cache_read_input_tokens > 0` | It needs a live Anthropic key and a paid call; the spec puts it after merge (§12.5). The offline proof is ACB: the repeat body carries the marks the vendor documents. |
| NFR-8.1 search latency and NFR-8.3 benchmark | Timing on a shared CI host is noise, and the briefing forbids wall-clock tests. Correctness of each refresh is covered by SRCH. |
| EC-8.5 a same-size rewrite within one timestamp tick | Excluded by the briefing; every SRCH edit changes the file size. |
| The INV-8.4 stat/read race (a file changing between stat and read) | It would need a hook inside the helper between two syscalls, which is not a seam §13 allows. |
| EC-7.3 (an MCP tool added mid-run changes the tool list) | No MCP server runs in this pack (prior spec §13). The add path is the same as `add_tool`, and INV-7.1 is proven for the unchanged catalog. |
| INV-0.1 raw history append-only | Raw history is not observable through `ScriptedTree` (§13 "Where new behavior is observable"). Masking purity (CW) and every agent-level view test cover what can be observed. |
| FR-10.8 the root and generator prompts mention `recall` | Prompt wording, not behaviour; the contract test's coding-only-words scan and INV-0.3's number check already read every leaf. |
| Q-1…Q-12 options, NG-1…NG-8 | Not specified (Q-1 is built and tested as DELEGATED; Q-2…Q-12 are "no"). |
| Running `test_bash_tool_process_bounds.py::test_endless_printer_times_out_with_the_first_bytes_and_a_truncation_marker` here | It is POSIX-only and skipped on this Windows host. WSL1 has no pytest, and installs are forbidden. Its new regex was checked against synthetic head-and-tail text; Linux CI runs it. |

## Red run (before implementation)

Bootstrap: nothing is installed. Run from the worktree root on Python 3.11.0 with SQLite 3.38.4 (FTS5 compiled in) and pytest 8.3.5. Set `PYTHONPATH="$(pwd)"` and pass `-p no:cacheprovider`. The checkout is `f3c42ba4` with only the test changes applied.

| Command (`python -m pytest -p no:cacheprovider -q …`) | Final line |
|---|---|
| `tests/test_read_lines_window.py tests/test_compaction_windows.py tests/test_grep_smart_case.py tests/test_fulltext_index.py tests/test_anthropic_cache_breakpoints.py` | `60 failed in 2.49s` |
| `tests/features/coding_agent` | `12 failed, 297 passed, 12 skipped in 16.91s` |
| `tests/features/infinite_memory_agent` | `59 failed, 106 passed in 7.33s` |
| `tests/test_deterministic_compaction_middleware.py tests/test_context_compaction_middleware.py tests/test_filesystem_tools.py tests/test_code_search_tools.py tests/features/sdk_managed_text` | `258 passed in 2.30s` |

What each red count is made of:

- **Row 1 (60).** RLW 10, CW 14, GSC 10, FTI 12, and ACB 14. They fail on names main lacks: `max_read_lines`, `tools=`/`placeholder=`, `low_watermark_tokens`, `smart_case`/`context_lines`, and `FullTextIndex`. ACB fails because main's Anthropic adapter adds no `cache_control` marks.
- **Row 2 (12).** The 10 BHT tests, plus the changed `test_bash_tool_contract.py::test_large_output_…` and `test_coding_agent_verify_command.py::test_output_over_the_cap_…`. All fail on `BASH_TAIL_OUTPUT_BYTES` or main's spec sentence. The 12 skips are the existing POSIX-only and case-sensitive-filesystem skips, which are the same on main. One of them is the changed endless-printer test.
- **Row 3 (59).**
  - ECO 12, STP 8, SRCH 16, and RCL 16. These fail on missing names (`INFINITE_MASK_KEEP_RECENT`, `FullTextIndex`, `InfiniteRecallMode`, `InfiniteMapSnapshot`, and the new leaves), or on `max_read_lines`/`recall_mode` refused by `InfiniteWorkspaceSettings`.
  - The 3 changed contract tests fail on the 50-leaf set and the tool sets.
  - The 3 changed delegation tests fail on the `search_memory` tool sets and on `assert 2 == 0` result_card renderings.
  - The changed workspace map test fails with "the root's system string changed between calls".
- **Row 4.** The shared suites the changes extend stay green on main.

### Addendum: spec r4 (S2 defects 1–2)

The checkout is `e9bfddf6` with only the r4 test changes applied; the bootstrap is the same.

| Command (`python -m pytest -p no:cacheprovider -q …`) | Final line |
|---|---|
| `tests/test_prompt_sits_at_run_boundary.py` | `13 passed in 1.34s` |
| `tests/features/infinite_memory_agent/test_infinite_memory_contract.py` | `4 failed, 23 passed in 1.01s` |
| `tests/features/infinite_memory_agent/test_infinite_memory_recall.py` | `16 failed in 1.15s` |
| `tests/features/infinite_memory_agent` | `60 failed, 105 passed in 6.71s` |

- **The run-boundary test is green on main.** The helper only widened: it also accepts the one marked text block, and main's adapter sends the plain string. It is green under the Anthropic reference too, where the HEAD helper fails, so the widening is what INV-9.3 needs. The DeepSeek and Gemini subtests and the assertions are unchanged.
- **The budget test is red on main** with `vidbyte/agents/infinite/recall.py is missing`. The HEAD version passed on main, which is why the pack goes from 59 to 60 failed. The contract file's 4 failures are the 3 earlier ones plus this test.
- **The recall spec test** still fails, now on `No module named 'vidbyte.agents.infinite.recall'`, so the recall file count stays at 16.
- **Against the scratch reference reshaped per D-18** (`InfiniteRecallTool` moved to `recall.py`, which imports `InfiniteAgentMemory` only under `TYPE_CHECKING`): the InfiniteMemory pack plus RLW, CW, GSC, and FTI give `211 passed in 9.96s`.

## Notes for the implementer

- **The names the tests bind to.**
  - Every name the tests import is a §4, §8.5, or §12.3 name. The tests import feature symbols inside each test body, so the pack collects before the feature exists.
  - The retriever must be named exactly `f"{settings.name}/{memory.key}/recall"`, which is `analyst/root/recall` for the root.
  - `ScriptedTree.agents[name]` is how the tests read each agent's middleware, so build the middleware on the agent object itself.
- **Masking, compaction, and the trim.**
  - The masking placeholder is read from the `masked_output` leaf, never a literal.
  - `masked_output` must be at most 60 tokens.
  - The trim test checks 182 messages of 500 tokens trimmed to exactly `long_history[50:]` (INV-4.2 at 90,000 with the 66,000 watermark).
- **Search.**
  - `FullTextIndex.lock` is replaced in one test by a counting re-entrant lock, so assign `self.lock` in `__init__` (do not make it a read-only property). Take it with `with self.lock:` or `acquire()`/`release()`.
  - `search_memory` must hold the lock once across the refresh and the search.
  - `FullTextIndex.match_expression` is wrapped in one test to read the phrases it builds, so the query path must call it through the class attribute, and punctuation-only words must be dropped before it quotes them.
- **Recall.**
  - Found blocks hold the disk text only, with no `read_lines` footer.
  - In the pre-search `{hits}`, each term's result must follow that term, in order.
  - The quota refusal's problem text must name the number `INFINITE_RECALLS_PER_AGENT` above the leaf's last (quota) line.
  - The recall tool spec may use `parameters` or `input_schema`; the tests read it through `ToolsFormatter.input_schema`.
  - `reply line {n}` may count from 0 or from 1; both are accepted.
  - A retriever that raises may surface as `AgentExecutionError` or as the raised class; both are accepted.
- **Cards.** The five-card test runs its `slow` pair with `max_iterations=3`, so the pair ends `partial` with a `passed` verdict and must keep the full card.
- **Lint.** Run lint with the files staged (S020 reads tracked files) and with `PYTHONIOENCODING=utf-8` (otherwise `lint/run.py` crashes on cp1252).
- **The complexity budget (r4, D-18).**
  - `InfiniteRecallTool` belongs in `vidbyte/agents/infinite/recall.py`.
  - The recall spec test imports it from there; `memory.py` imports it for its builder table.
  - The budget test allows 9 package files and checks 13 modules at ≤400 lines after the header each.
  - `recall.py` must import `InfiniteAgentMemory` only under `TYPE_CHECKING`.
- **The run-boundary test (r4, EC-9.10).** The helper accepts the task as a plain string or as exactly `[{"type": "text", "text": TASK, "cache_control": {"type": "ephemeral"}}]`. A mark with any other shape, such as one carrying `ttl`, extra keys, or a second block, is not found as the task.

## S5 test-pack additions (spec r5; review R-8, R-9, R-10, R-11, R-24)

The S4 review (`review.md`) found defects that the 331 related tests let through. These 15 tests pin them at HEAD `c3ecd466` before any fix. Each defect-pinning test is red at HEAD for the reason the review names, and green under a scratch fix plugin that is never committed. Each guard is green at HEAD and red under a named mutation plugin. The plugins are loaded with `-p <module>` from three scratch folders: `s4-verify` (`fix_mask_batch`, `fix_anth_digest`, `fix_r1`), `s4-eng` (`mut_delete`, `mut_mask_batch`), and `s5-tests` (`fix_r2_r5`, `fix_r7`, `mut_mask_unscoped`).

`fix_r2_r5` is `fix_r1` with its `execute` reordered to spec r5: it runs the FR-8.6 blank check on the query as given, then turns NULs into spaces and drops lone surrogates. `fix_r7` is `fix_r2_r5` plus the R-7 `_lookup`, which lists the files once with `os.scandir`, fingerprints each from that stat, opens only sources whose fingerprint changed, and passes `retain` a set. `mut_mask_unscoped` applies the unread rule even when `tools=()`.

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| INV-8.2, EC-8.1, T-1 (r5), FR-8.6 (review R-2a, R-8) | SRCH → `test_a_query_holding_a_nul_or_a_lone_surrogate_gives_the_result_of_its_clean_words` | agent tool, real FTS5 | A query word holding a NUL raises `sqlite3.OperationalError: unterminated string`, and a word holding a lone surrogate raises `UnicodeEncodeError`. A query made only of NULs and surrogates is refused, or raises. | Each dirty query must give the same output and metadata as its clean twin (`alpha\x00beta` and `alpha beta`, and so on), and each clean twin must find at least one hit first, so two empty results cannot match. Queries made only of NULs and surrogates must succeed with 0 of 0. FR-8.6's blank check reads the query as given, and `"\x00".strip()` is not blank. |
| INV-8.8, EC-8.8 (review R-2b, R-8) | SRCH → `test_an_entry_line_holding_a_lone_surrogate_is_left_out_and_every_later_search_still_works` | agent tool | One `entries.jsonl` line whose `text` or `kind` holds a `\ud800` escape makes every later search raise, for every agent. | A precondition counts the two `\ud800` escapes in the file, so the bad input really is on disk. Entries 1 and 4 must still be found (total 2), and a note must still match, so skipping the whole file fails. Two passes and a fresh `FullTextIndex` must agree, so a fix that only works on the first call fails. |
| INV-8.5 (r5), EC-8.8 (review R-2b, R-8) | SRCH → `test_a_note_whose_name_utf8_cannot_encode_is_left_out_and_every_other_search_works` | agent tool | A note named `bad\udcff.md` makes every search raise until the note is removed. | The name must be listed back from the folder (a precondition), so a filesystem that silently renamed it cannot make the test pass. It skips only if the OS refuses to create the name, as macOS APFS does. Windows (surrogatepass) and Linux (byte 0xFF) both create it. `kappa` must give exactly 1 of 1, from `notes/plans.md`, and `hidden` must give 0. |
| INV-10.10, INV-8.2, EC-8.8 (review R-2c, R-8) | RCL → `test_a_term_holding_a_nul_or_a_lone_surrogate_is_searched_and_the_retriever_still_starts` | agent (`ScriptedTree`) | The pre-search raises on the term `acme\x00price` after the quota is spent, so the retriever never starts and the card is the runtime's generic failure. | The retriever must run exactly once, and its prompt must hold `notes/acme.md:1: Acme price sheet for this quarter`, which only a pre-search that ran on the cleaned term can produce. The card must not be an error, and its not-found section must carry the retriever's line. |
| INV-2.3 (r5), AC-2.5, EC-2.5 (review R-3, R-9) | ECO → `test_a_parallel_batch_of_reads_stays_whole_until_the_model_has_answered_it[openai, anthropic, gemini]` | agent middleware (the root's own masking) over each wire's real shapes | When one model turn makes 5 parallel `read_lines` calls, the next view masks the oldest 2 before the model has read any of them. | `ScriptedTree` takes one tool call per step and cannot script a parallel batch, so the history is built in each wire's call shape, with results from `ToolsFormatter.format_tool_result`, the formatter the runtime uses. The first view must keep all 5 outputs whole. After a `bash` turn and its result, it must show exactly the oldest 2 as the `masked_output` leaf text and the rest whole, so a strategy that never masks fails. Every input is unchanged in both views. |
| INV-2.3 guard, AC-2.1 shape (review R-3, R-9) | ECO → `test_reads_made_one_per_model_turn_still_mask_all_but_the_newest_three[openai, anthropic, gemini]` | agent middleware | The fix stops masking ordinary reads made one per turn, or treats only `assistant` as a model turn, which turns masking off on Gemini. | Green at HEAD. It goes red under `mut_mask_batch` (S4 engineering's `assistant`-only fix) on `[gemini]`. |
| INV-2.3, EC-2.5 at strategy level (review R-3, R-9) | CW → `ScopedWindowTests::test_a_scope_keeps_outputs_after_the_newest_model_turn_whole_on_every_wire_role` | unit | The same defect in `ToolOutputSlidingWindowCompaction(tools=...)`, for each `(role, kind)` pair in §13. | The answered view must equal main's window (`_window`) and also the literal content list. A history with no model turn must come back unchanged. Under `mut_mask_batch` it is red on the `("model", "user")` subtest. |
| INV-2.1 under r5 INV-2.3 (review R-3, R-9) | CW → `ScopedWindowTests::test_without_a_scope_an_unanswered_batch_is_compacted_exactly_as_on_main` | unit | A fix that applies the unread rule with `tools=()` changes main's window for every other caller. | A precondition requires that main's window really compacts the batch (`expected != pending`). Green at HEAD; red under `mut_mask_unscoped`, which also fails 3 existing `DeterministicStrategyTests`. |
| NFR-8.1 stand-in, INV-8.4 (review R-7, R-10) | SRCH → `test_a_warm_search_opens_no_unchanged_file_and_reads_a_changed_one_again` | agent tool, with a `sys.addaudithook` "open" recorder | A warm search opens all 13 workspace files again (HEAD: "a search with nothing changed opened 13 workspace files"). | No timing is involved. Opens are counted from the interpreter's own audit events: `builtins.open`, `io.open`, `os.open`, and the `pathlib` reads. Stat, resolve and scandir raise no "open" event. Positive control: the cold search must open `entries.jsonl` and all 12 notes, so a recorder that hears nothing fails. After one note is rewritten and one entry appended, exactly those two files must open and the new text must be found, so a fix that never reads again fails. A further search must open nothing. |
| INV-9.2, INV-0.2 (review R-6, R-11) | ACB → `LoneSurrogateTests::test_a_lone_surrogate_in_the_system_or_a_tool_sends_mains_body_first_and_marks_the_repeat` | adapter (`_create_payload`) | A lone surrogate in the system or in a tool description raises `UnicodeEncodeError` (at `anthropic.py:189`) on the first Anthropic request, which main builds. | The first body must equal main's body (`MAIN_BODY_JSON` with the same system and tools), both as an object and as `json.dumps` text, with no marks. The repeat must equal the expected three-mark body, so a fix that skips marking fails. |
| §9.1 Refresh, row 12 (review R-24) | FTI → `FullTextRefreshTests::test_replace_and_retain_delete_by_recorded_rowid_never_by_source` | unit, real `sqlite3` with `set_trace_callback` | `replace` or `retain` deletes by the UNINDEXED `source` column, which scans the whole table while holding the lock. | It wraps `sqlite3.connect`, the same seam `without_fts5()` uses, only to attach the trace. The trace must show the helper's own inserts, and at least 2 deletes must be seen (one replaced source, one dropped). Each delete must name `rowid` and none may name `source`. The search results are checked afterwards, so a fix that stops deleting fails. Green at HEAD; red under `mut_delete`. |

### Red run (S5, before the repair)

The bootstrap is as in "Red run" above. The checkout is `c3ecd466` with only the S5 test changes applied. Every command is `python -m pytest -p no:cacheprovider -q` over the same 7 paths: `tests/test_compaction_windows.py tests/test_fulltext_index.py tests/test_anthropic_cache_breakpoints.py tests/features/infinite_memory_agent tests/test_context_compaction_middleware.py tests/test_deterministic_compaction_middleware.py tests/test_code_search_tools.py`. Plugin folders go on `PYTHONPATH` after the worktree, separated by `;` on Windows.

| Run | Final line |
|---|---|
| HEAD before the S5 edits | `331 passed in 9.04s` |
| HEAD with the S5 tests | `10 failed, 336 passed in 9.87s` |
| `-p fix_r7 -p fix_mask_batch -p fix_anth_digest` (every proven fix together) | `346 passed in 9.43s` |
| `-p mut_delete` | `11 failed, 335 passed in 9.97s`: the 10 HEAD reds plus the FTI rowid test |
| `-p mut_mask_batch` | `9 failed, 337 passed in 11.08s`: AC-2.5 turns green on `[openai]` and `[anthropic]` only; the kills are AC-2.5 `[gemini]`, the sequential guard `[gemini]`, and the CW scope test |
| `-p mut_mask_unscoped` | `10 failed, 336 passed in 10.98s`: the 4 R-9 reds turn green; the kills are the CW unscoped guard and 3 existing `DeterministicStrategyTests` |

What the 10 HEAD reds are made of:

- **R-8 (4).**
  - The SRCH query test: `fulltext.py:104: sqlite3.OperationalError: unterminated string`.
  - The SRCH entry-line test: `fulltext.py:69: UnicodeEncodeError` on `'\ud800'`.
  - The SRCH note-name test: `fulltext.py:69: UnicodeEncodeError` on `'\udcff'`.
  - The RCL test: "the pre-search raised, so the retriever never started" (`assert 0 == 1`).
- **R-9 (4).** The 3 ECO AC-2.5 cases fail with "masking hid an output the model has not read yet", and the CW scope test with "an output after the newest model turn was masked".
- **R-10 (1).** "a search with nothing changed opened 13 workspace files". This test stays red under `fix_r2_r5` alone and turns green only under `fix_r7`.
- **R-11 (1).** `anthropic.py:189: UnicodeEncodeError` in both subtests.
- **Green at HEAD (5).** The 3 ECO sequential guards, the CW unscoped guard, and the FTI rowid test.

The verifier's `fix_r1` fails one of these tests on purpose. It normalizes before the blank check, so `"\x00"` comes back `invalid_argument`. Spec r5 INV-8.2 says a NUL is read as whitespace, and FR-8.6 tests the query as given, so the answer must be 0 of 0. `fix_r2_r5` follows the spec order and passes.

### S5 tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| R-8 at helper level (FTI with NUL or surrogate words) | The orchestrator placed R-2's guard in `search_memory`, not in `FullTextIndex`. A helper-level test would pin the guard to the wrong layer and fail a correct repair. |
| Whether a skipped binary (NUL) file is sniffed again on every warm search | The spec does not say. R-10's workspace holds text files only, so a repair may keep re-sniffing skipped binaries or remember them. |
| R-19 (the pre-search raising outside the recall `try`) | After R-2 nothing known makes the pre-search raise. Driving it would need a fault inside `FullTextIndex.search`, which is not a seam §13 allows. |
| R-17, R-18, R-20, R-21, R-22 | The orchestrator ruled them not tested: they are follow-ups, or the spec is silent. R-20 heals itself once R-2 removes the deterministic failure. |
| R-3 through a full `ScriptedTree` run | `ScriptedTree` takes one tool call per step. ECO drives the root's own middleware with messages from the runtime's formatter instead, which is the shape the runtime appends. |
| The exact wording of the FR-8.6 refusal | The wording is not behaviour, and the blank check's outcome is pinned by the R-8 query test. |
| New file-header lines (FUNCTION INVENTORY) for the five touched test files | The existing header lines cannot be changed: comment-only edits are forbidden and R-23 is waived. The new tests are listed in `FEATURE.md` (Known Failure Modes and Historical Regressions) instead. |

## S5 re-review pin (R-25)

Re-review round 1 (`review.md`, "Re-review round 1 — verified findings") found that the R-7 fix's row helpers sniff a changed file through `is_text_file` (`code_search/base.py:110-118`), which swallows `OSError`. One failed read of a changed file therefore stores the new fingerprint with no rows, and every later search skips the file until it changes again. These 2 tests pin INV-8.4 and the S3 deviation for row 20 ("a file that raises `OSError` mid-refresh is skipped for that call") at HEAD `bb1f9306` (code `72d1ca7f`), before the fix.

**The seam.** A second `sys.addaudithook` on the `"open"` event, armed by the context manager `_one_open_fails(target, error)`, raises the given `OSError` from the first open of the target and then disarms itself. The R-10 recorder is the precedent, and the arming follows the same rule: a hook cannot be removed, so it is added once per process and does nothing unless armed. The hook fires for `open`, `io.open`, `os.open`, and every `pathlib` read, in the worker thread that opens. So the test does not depend on how a fix opens the file, and it needs no real lock, which Linux CI could not make. Nothing else is mocked: the filesystem, `InfiniteWorkspace`, the toolset, and SQLite FTS5 are real (§13).

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| INV-8.4, §17 S3 deviation row 20 (review R-25) | SRCH → `test_a_changed_note_whose_read_fails_once_is_found_by_the_next_search` | agent tool, real FTS5, audit-hook fault | A note is indexed. It is rewritten with a new size, and the next search's first open of it raises `PermissionError(EACCES)`. Then the next search and every later one return 0 of 0 for its new line (HEAD: `next search after one failed read: '0 of 0 matching entries and note lines shown.'`). | A precondition requires exactly one failed open, so a seam that never fires, or a search that never reads the changed note, fails the test. The rewrite changes the size, so no timestamp tick is involved (EC-8.5). The query `costs` is only on the new line, so the old rows cannot satisfy it. The failing call itself must return SUCCESS, but its hits are not asserted, so skipping the file and keeping its old rows are both allowed. Two later searches must both show the exact hit line. |
| INV-8.4, INV-8.5, §17 S3 deviation row 20 (review R-25; G-2) | SRCH → `test_a_changed_entries_file_whose_read_fails_once_has_every_entry_found_by_the_next_search` | agent tool, real FTS5, audit-hook fault | Entry #1 is indexed, then `entries.jsonl` gains entry #2, and the next search's first open of it raises `OSError(EMFILE)`. After that, every remembered entry is hidden, the old one included (HEAD: 0 of 0 for `basic`). | The same precondition and SUCCESS check as the note test. The error is a plain `OSError` (`EMFILE`), not a `PermissionError`, so a fix that handles only lock errors fails. Both entries must be found with metadata `{"hits": 2, "total": 2}`, on the next search and on the one after it. |

### Red run (S5 re-review, before the repair)

Commands run from the worktree, as `PYTHONPATH="<worktree>[;<plugin dir>]" python -m pytest <paths> -q -p no:cacheprovider [-p <plugin>]`. Related suites: `tests/features/infinite_memory_agent tests/test_fulltext_index.py tests/test_code_search_tools.py`. `fix_rr1` is the verifier's proven fix, in scratch `s5-rrverify/`. The variant plugins are in scratch `s5-pin-r25/`, built by `make_variants.py`, and are never committed.

| Run | Final line |
|---|---|
| Related suites at HEAD, before the edit | `205 passed in 8.07s` |
| The 2 pins at HEAD (`-k read_fails_once`) | `2 failed, 20 deselected in 0.98s`. Both fail on the `next` search with `'0 of 0 matching entries and note lines shown.'`, after their preconditions pass. |
| Related suites at HEAD with the pins | `2 failed, 205 passed in 8.27s` |
| The 2 pins, `-p fix_rr1` | `2 passed, 20 deselected in 0.11s` |
| Related suites, `-p fix_rr1` | `207 passed in 7.50s` |
| Whole `tests/`, `-p fix_rr1` | `3 failed, 6582 passed, 16 skipped in 113.49s`. The 3 failures are the `harness_threads` surface tests, which fail in this environment with or without the change (S5-rereview-verifier §3.2). |
| The 2 pins, `-p fixv_builtin_open` (the sniff uses builtin `open`) | `2 passed, 20 deselected in 0.11s` |
| The 2 pins, `-p fixv_os_open` (the sniff uses `os.open` and `os.read`) | `2 passed, 20 deselected in 0.11s` |
| The 2 pins, `-p fixv_keep_rows` (a read error keeps the old rows; verifier §3.4 option) | `2 passed, 20 deselected in 0.11s` |
| The 2 pins, `-p mutv_swallow` (a wrong fix: the sniff uses builtin `open` and swallows `OSError`) | `2 failed, 20 deselected in 0.27s` |
| The 2 pins, the R-10 warm test, and the INV-8.5 test in one process, in both orders, at HEAD and with `-p fix_rr1` | At HEAD the 2 pins fail and the others pass; with the fix all pass. The raising hook does not disturb the recorder. |
| The 2 pins plus the R-10 warm test on 84e566bb (`PYTHONPATH="v84;<worktree>" --import-mode=append`) | `1 failed, 2 passed, 19 deselected in 1.73s`. The pins pass on the commit before the R-7 fix, and only the R-10 warm test fails, by design, which shows the old tree was the one loaded. |
| Cross-check: the verifier's real Windows share-mode-0 lock pin (`s5-rrverify/test_rr1_pin.py -k share_mode`) | At HEAD: `1 failed, 4 deselected in 16.34s`. With `-p fix_rr1`: `1 passed, 4 deselected in 15.00s`. The real lock and the hook give the same verdict. |

**What a repair must keep for these tests to pass.**

- A changed file whose open raises `OSError` during the refresh must not have its new fingerprint stored with no rows. The error must reach `_lookup`'s skip, or the old rows must stay, so that the next search reads the file again.
- The failing call itself must still return SUCCESS.
- The tests do not care which API opens the file, or how often. Only the first open of the target fails.

### R-25 tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| A real Windows share-mode-0 lock in the repository | It is not portable: Linux CI would skip it, so it cannot be the pin (hard rule 2). The cross-check above ran the verifier's scratch version instead. |
| What the failing call itself returns for the changed file | Row 20 says only "skipped for that call". Keeping the old rows for that call is an open question for the owner (verifier §3.4), so neither 0 hits nor the old line is asserted. |
| R-26, R-27, R-28 | The orchestrator ruled them out of scope for this pin. R-28 (the Windows `scandir` size lag while a writer holds the file open) is a follow-up. |
