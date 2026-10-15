# Test plan: InfiniteMemory agent — a delegating agent with a shared, guarded file workspace for memory

Spec: `docs/spec/infinite-memory-agent/spec.md` r3 (the S4 additions bind to r5, whose only test-relevant change is NFR-7) · Framework: pytest 8.3.5 + pytest-asyncio 1.3.0 (Python 3.11.0) · Prior art copied: `tests/features/jev_bulk_work/test_jev_bulk_work.py` (fake runners routed by agent name to agents built inside a tool), `tests/features/sdk_managed_text/managed_text_fixtures.py` (a shared fixture module with no feature imports at module level), `tests/test_jev_compute_situations.py:255` (the tool-call response shape), `tests/test_jev_agent.py:441-450` (registry and refusal)

Pack: `tests/features/infinite_memory_agent/`. It holds `README.md`, `FEATURE.md`, `infinite_memory_fixtures.py`, and 7 test modules with 107 test cases: the original 89, plus 18 added after the S4 review (see [S4 additions](#s4-additions)). In the table below, `acceptance`, `contract`, `delegation`, `verification`, `workspace`, `resume` and `context` stand for `test_infinite_memory_<name>.py`.

Every agent-level test drives a real `InfiniteMemoryAgent`. A `ScriptedTree` is patched in at `BaseAgent._runner_for_model` (spec §13). It routes each model call by agent name and records each call's `prompt`, `system`, `messages` and offered `tools`. Any call with no scripted step left is recorded as unscripted and fails `assert_complete()`, so an agent that must not run cannot pass silently. Concurrency and ordering use `Gate` and `Signal` (asyncio events). Their timeout only turns a hang into a failure; no test sleeps.

## Coverage map

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | acceptance → `test_section_4_snippet_prints_the_root_answer_and_leaves_the_documented_workspace` | e2e | §4 snippet in a folder with `brief.md`, and a root that answers at once → the answer is not printed, the seed is not copied, a bookkeeping file is missing, or the journal does not end with `run_finished` | The snippet could be edited to fit an implementation. Instead it is pasted verbatim under `chdir(tmp_path)`. The printed text must equal the scripted answer, and `assert_complete` proves the scripted root was the one that answered. |
| AC-2 | contract → `test_construction_rejects_each_invalid_setting[reserved-tool-name, missing-root-dir, missing-seed, duplicate-seed-basename, max-depth-0, max-parallel-0, max-agents-1, file-cap-above-total]`, `test_construction_rejects_a_non_settings_object` | unit | Each invalid setting → accepted, refused without naming the field and value, or `memory/` created anyway | A test that only checks for some `ConfigurationError` passes for any refusal. Each case here requires its own field name and value token, with word boundaries around numbers, and checks that no workspace folder exists. |
| AC-3 | contract → `test_runtime_type_resolves_and_refuses_outside_its_agent` | unit | Registry row missing, or a plain `BaseAgent(runtime="infinite_memory")` or a fork builds the runtime without settings | The test uses INV-3's exact message prefix. The fork case must also raise naming `InfiniteMemoryAgent`. |
| AC-4 | contract → `test_root_is_offered_exactly_the_preset_tools_plus_its_extra[SPARSE-extra0, FULL-extra1]` | integration | The root is offered a missing, extra or duplicated tool, or `edit_file` under SPARSE | A subset check would pass with extra tools. The test compares the set of names the runner received, checks for duplicates, and covers both presets. |
| AC-5 | delegation → `test_two_tasks_run_concurrently_and_each_verifier_follows_its_own_generator` | integration | Two tasks → pairs run one after another; a verifier starts before its generator returns; cards come back in completion order; child text leaks into the root | A timing-based check could pass by luck. Here `Gate(2)` opens only when both generators are inside a model call at once. Alpha is held until beta has its verdict, so completion order is the reverse of task order. Six child-only markers are searched for in every root call's prompt, system string and history. |
| AC-6 | delegation → `test_an_invalid_batch_starts_nothing_and_the_tool_stays_usable[more-than-max-parallel, duplicate-name, blank-verifier-prompt, missing-generator-prompt, tool-the-root-lacks, unknown-context-id, superseded-context-id, name-fails-pattern, unknown-field]` | integration | A bad batch → some pairs start, a journal record is written, the tool stops working after the rejection, or the error does not say what is wrong | Checking only `is_error` passes when every batch fails. Here a valid batch must then succeed. The agents called must be exactly the root and that pair, and the journal must hold exactly 4 records. The error must name the case's token and match the `launch_rejected_prompt` template. |
| AC-7 | delegation → `test_depth_cap_and_role_decide_who_holds_launch_subagent_and_drop_entry` | integration | `max_depth=2` → the depth-2 generator holds `launch_subagent`, or a verifier holds it, or a verifier lacks `drop_entry` | The test compares exact tool sets on all four agents, including the nested pair, which really runs; its finished key `root/a/gen/b` is checked. |
| AC-8 | delegation → `test_a_batch_that_would_pass_max_agents_is_refused_whole` | integration | `max_agents=4` → the cap is checked per task, `z` starts, or the error does not name `max_agents` | The set of agents called must be exact, and the `pair_started` keys must be exactly `root/x`, `root/y`. |
| AC-9 | acceptance → `test_staged_entries_reach_disk_only_after_the_verifier_returns` | integration | A generator's `remember` → the entry is written at once, or committed with the wrong `by`, `verified_by`, `run` or `at` | `entries.jsonl` is read at four model calls during the pair, and every read must be empty. Afterwards the two lines are checked field by field, and the card's ids must equal the committed ids. |
| AC-10 | verification → `test_no_verdict_or_a_failing_verifier_drops_every_staged_entry[no-verdict-line, verifier-raises]` | integration | No verdict line, or a verifier error → the entry is committed as verified | `entries.jsonl` bytes are compared before and after. The verdict must be exactly `unchecked`, and `dropped` must name the entry. |
| AC-11 | verification → `test_drop_entry_removes_only_the_named_staged_entry` | integration | `drop_entry("s1")` → the wrong entry or every entry is dropped | The list of committed texts must be exact. `dropped` must name `s1` and not `s2`, and the drop result must list `s2`. |
| AC-12 | delegation → `test_a_failed_or_blank_generator_skips_its_verifier_and_its_sibling_still_reports[raises, blank]` | integration | The generator raises or answers blank → the exception sinks the sibling, or the verifier runs | The verifier has no script, so any call to it fails. The sibling's card must be `done`/`passed`, and the launch result must not be an error. |
| AC-13 | delegation → `test_a_generator_stopped_by_max_iterations_is_partial_and_still_verified` | integration | A generator stopped at `max_iterations` → its work is discarded, or it is marked `done` | The status must be exactly `partial`, and the verifier's scripted step must be used. |
| AC-14 | workspace → `test_root_remember_rejects_each_rule_breaking_entry_and_enforces_the_quota` | integration | One INV-17 rule is not enforced; rejections use up quota; an error lacks the quota line; a rejected call writes to disk | Six rejections come before five valid calls, so a rejection that used up quota would cause a valid call to be refused. A workspace byte snapshot is compared around every call. The ids must be exactly 42–46, and the sixth refusal must read `0 of 5`. |
| AC-15 | workspace → `test_root_supersede_moves_the_old_entry_out_of_entries_and_out_of_grep` | integration | `supersedes=1` → the line is copied instead of moved, rewritten, or still found by grep | The line in `superseded.jsonl` must equal the original line exactly, and the grep result must be exactly `No matches found.` |
| AC-16 | workspace → `test_write_note_refuses_every_path_and_size_breach_and_changes_nothing`, `test_write_note_refuses_a_new_file_at_the_file_cap`, `test_write_note_counts_files_bash_wrote_toward_the_token_cap` | integration | A path escape, a write to a protected path, a code suffix, a second new file, a size cap, the file cap, or a cached usage figure → a write goes through | Byte snapshots, `.runs/` included, are compared around every refused call. The two outside paths are checked to be absent. A real bash writes the large file. |
| AC-17 | workspace → `test_edit_file_replaces_a_unique_match_and_refuses_an_ambiguous_one`; SPARSE clause: delegation → `test_depth_cap_and_role_decide_who_holds_launch_subagent_and_drop_entry` and contract AC-4 | integration | An ambiguous edit replaces the first match; FULL pairs lack `edit_file`; SPARSE agents hold it | Both files' contents are compared exactly, and the refusal must state 2. |
| AC-18 | workspace → `test_every_agent_sees_the_map_and_the_roots_map_refreshes_after_each_tool_iteration`, `test_a_map_over_its_cap_ends_with_the_remaining_file_count` | integration, unit | The map is stale after a write, missing from children, uncapped, or shows a wrong remaining count | The map is read from the `system` keyword of every call. The remaining count must equal the unlisted files, within the three bookkeeping files. |
| AC-19 | resume → `test_journal_records_the_run_in_order_as_json_lines` | integration | Records out of order, a non-JSON line, a wrong key or stop reason, or a non-UTC stamp | Every line is parsed. The event list must be exact, and the card must have exactly the 9 fields. |
| AC-20 | resume → `test_resume_replays_finished_pairs_and_reruns_interrupted_ones` | integration | Resume re-runs a finished pair, pastes its full card into the briefing, picks the wrong run, or writes a second `run_started` | The journal is hand-written in the §9.1 shape, not written by the implementation. Alpha's generator has no script, so running it fails. The older journal must stay byte-identical. |
| AC-21 | resume → `test_resume_refuses_unsafe_unknown_finished_or_missing_runs_before_any_model_call[all-runs-finished, path-escape, unknown-well-formed-id, finished-id, no-runs-at-all]` | integration | `resume("../x")` reads outside `.runs/`; a finished or unknown run resumes | The path-escape case plants a valid unfinished journal at `memory/x.jsonl`, so following the path would resume instead of raising. The runner must receive no call, and every journal must stay byte-identical. |
| AC-22 | resume → `test_resume_skips_a_torn_final_journal_line`, `test_resume_rejects_a_malformed_middle_journal_line` | integration | A torn tail blocks resume or corrupts `run_finished`; a malformed middle line is skipped | The torn fragment has no trailing newline, which is the real failure shape. The last line must then parse as `run_finished`, and the refusal must name line 3. |
| AC-23 | resume → `test_cancelling_a_run_mid_pair_leaves_a_resumable_journal` | integration | Cancellation is swallowed, `run_finished` is written, the child keeps running, or resume fails | The test is driven by a Signal, with no sleep. The generator must observe `CancelledError`. |
| AC-24 | acceptance → `test_root_usage_includes_every_generator_and_verifier_exactly_once` | integration | Child usage is missing or counted twice | Each runner reports a different magnitude (1,000, 200 and 30), so any double count shows. The totals are compared exactly. |
| AC-25 | contract → `test_session_refuses_the_agent` | unit | `Session(agent)` succeeds | The `SessionError` message must match. |
| AC-26 | delegation → `test_a_long_generator_reply_is_cut_in_its_card_and_the_rest_never_reaches_the_root` | integration | The card is uncut, or the tail reaches the root or the verifier | The tails are unique markers. The kept prefix is checked to be a prefix of the reply, and its size is checked with `TokenEstimate`. |
| AC-27 | contract → `test_public_names_import_from_every_documented_path`, `test_prompt_family_has_exactly_the_forty_documented_leaves`, `test_enum_values_are_the_documented_lowercase_strings` | unit | An export is missing, the contract is not regenerated, or a prompt member or asset is missing or extra | Both the 40 members and the family are compared for equality, not checked as subsets. |
| AC-28 | delegation → `test_a_task_card_grants_exactly_the_extras_it_names` | integration | `calc` leaks to a child, or a named extra is missing or does not work | Exact tool sets are compared, and the child's actual tool results are checked. |
| AC-29 | delegation → `test_context_pastes_named_entries_and_lists_named_paths` | integration | The named entry is not pasted, the file content is pasted, or unnamed entries are pasted | Negative markers are checked for the note body and for both unnamed entries. |
| AC-30 | acceptance → `test_a_second_agent_on_the_same_workspace_sees_the_first_agents_entry` | integration | B's map is stale or does not count entries, or grep misses the entry | Blanking `entries.jsonl` to the same length keeps the file and token figures identical, so only the entry count can change the map. B's system string must carry `workspace.map_text()`. |
| AC-31 | delegation → `test_relaunching_a_finished_name_replays_its_card_without_building_agents` | integration | The pair runs a second time, the label is missing, or usage is added | Each child has a one-step script, so a re-run is an unscripted call. The usage count must be exactly 5. |
| AC-32 | delegation → `test_the_verifier_gets_the_generators_outcome_but_never_its_transcript` | integration | The verifier misses an input, or the generator's transcript leaks into it | The grep pattern and the note body are unique markers carried only by the generator's tool calls. |
| AC-33 | context → `test_root_history_is_trimmed_past_the_cap_while_task_and_map_survive` | integration | History is not trimmed, or the task or the map is dropped | The cap is patched to 250 tokens in `vidbyte.agents.infinite.agent` (§13). Four groups of about 100 tokens each mean the oldest cannot fit. |
| AC-34 | workspace → `test_entries_file_is_bounded_by_the_workspace_total_not_the_note_cap` | integration | `max_file_tokens` is applied to `entries.jsonl` | The setup asserts that `entries.jsonl` starts above the note cap. |
| AC-35 | delegation → `test_launch_subagent_is_exempt_from_the_tool_timeout_and_result_cap` | integration | `launch_subagent` is timed out or truncated | A 1 ms timeout plus a Gate wait guarantees a suspension, and the two cards total more than 600 characters against a 200-character cap. |
| AC-36 | delegation → `test_a_task_card_grants_exactly_the_extras_it_names` (`lookup` comes from `add_tool`) | integration | An extra added with `add_tool` cannot be granted | `lookup` is not in `settings.tools`. |
| AC-37 | verification → `test_a_malformed_entries_line_drops_each_pairs_entries_but_the_run_finishes` | integration | A commit-time parse error sinks the batch or changes a verdict | The malformed line is written during the first verifier's call, after staging and before any commit. Both cards must name `entries.jsonl` and line 3. |
| AC-38 | verification → `test_verdict_is_read_from_the_last_matching_line_in_any_markdown_or_case[bold-line, bold-value, trailing-period, mixed-case, backticks, underscores, last-line-wins]` | integration | A Markdown or case variant is not recognized, the first verdict line wins, or a `failed` verdict drops entries | Each case has an exact verdict and an exact committed entry. |
| AC-39 | contract → `test_loop_and_limit_defaults_match_the_spec` | unit | The default loop is unbounded, results are uncapped, or a default is wrong | The literal spec numbers are compared as well as the constants. |
| AC-40 | context → `test_a_second_run_on_the_same_agent_starts_from_a_clean_context` | integration | The first run leaks into the second run's system string | A probe showed that a plain `BaseAgent`'s second run does contain `Tool calls:` and `History:`, so this assertion can fail. |
| AC-41 | resume → `test_a_run_time_tool_named_like_a_run_bound_tool_fails_before_the_journal_starts` | integration | The run goes ahead or writes a journal, or the error does not name the reserved list | The runner must receive no call, and `.runs/` must hold no journal. The test accepts the `ConfigurationError` raised directly, or as the cause of `BaseAgent`'s `AgentExecutionError` wrapper (see Notes). |
| AC-42 | workspace → `test_grep_finds_a_live_entry_in_an_entries_file_over_one_megabyte` | integration | Grep silently skips files over 1 MB | The setup asserts the file is over 1,000,000 bytes, and the needle is on its last line. |
| §9.2, INV-9, INV-11 | contract → `test_launch_and_remember_schemas_follow_the_documented_shape` | integration | The launch schema allows more than `max_parallel` tasks, open task cards, or optional prompts; descriptions do not come from the catalog; `kind` is not the enum | The schema is read from what the model is sent, with `max_parallel=3` so the default 10 cannot pass. Each description must fully match its leaf. |
| INV-2 | contract → `test_construction_rejects_a_non_settings_object` | unit | A dict is accepted as settings | The refusal must name the value it got. |
| INV-21, EC-3 | contract → `test_attaching_a_workspace_already_over_a_cap_is_refused[over-max-files, seed-over-file-cap]` | unit | A workspace already over a cap is attached | The error must name the cap. |
| INV-19, INV-22, EC-24 | workspace → `test_map_labels_and_usage_read_the_disk_and_never_fail_on_bad_lines` | unit | The seed or no-description label is missing, a bad bookkeeping line crashes the map, or `.runs/` is counted | Usage files and tokens are recomputed independently with `TokenEstimate`. |
| INV-28 | resume → `test_a_rerun_generator_hears_about_its_own_finished_children` | integration | A re-run generator is not told which of its own children finished | The child card comes from a hand-written journal. |
| EC-17, INV-19 | verification → `test_an_entry_that_no_longer_fits_at_commit_is_dropped_with_the_cap_reason` | integration | The workspace fills before commit and the commit passes `max_tokens` | `entries.jsonl` must stay empty. |
| D-15 | workspace → `test_grep_hides_superseded_entries_and_journals` | integration | Grep returns superseded facts or journal text | The result must be exactly `No matches found.` |
| §9.1 | contract → `test_entries_written_by_hand_in_the_documented_shape_are_accepted` | unit | The documented line shape is not read back | Every field is compared. |
| INV-33, NFR-5 | contract → `test_prompt_family_text_carries_no_coding_only_rules` | unit | A prompt mentions worktrees, pull requests, git, repositories or single-writer rules | The test checks every leaf of the family. |
| FR-15, D-17 | contract → `test_token_estimate_counts_characters_and_cuts_to_a_prefix` | unit | Counting by bytes, a cut that is not a prefix, or a cut over budget | 300 seeded random cases are checked, including multi-byte characters. |
| NFR-1 | contract → `test_new_modules_stay_inside_the_complexity_budget` | unit | The package has more than 8 modules, or a module has more than 400 lines after its header | The test fails while the folder is missing. |
| NFR-3, INV-25 | resume → `test_every_journal_record_is_fsynced_before_the_next_one_is_written` | integration | Records are buffered and fsynced late | A spy on `os.fsync` (and on `journal.fsync` if that name exists) records the journal's size at each fsync; sizes 1–4 must all be seen. |
| T-3 | resume → `test_api_key_stays_out_of_the_settings_repr_the_journal_and_the_workspace` | integration | The key appears in `repr` or on disk | Every file, `.runs/` included, is scanned after a run with one pair. |
| INV-29, INV-32 (S4 R-1) | delegation → `test_a_pair_whose_card_or_record_cannot_be_written_as_given_still_finishes_beside_its_sibling[u2028-in-a-note-path, u0085-in-a-note-path, lone-surrogate-in-the-reply]` | integration | A note path that `splitlines()` breaks, or a lone surrogate in a generator's reply → building the card or writing `pair_finished` raises outside the pair's guard; `launch_subagent` fails, the sibling's card is lost, and the key never gets `pair_finished` | Both keys need exactly one `pair_finished`, both summaries must reach the root, and every scripted step must run. The path cases accept both spec-conformant outcomes: the path is refused at write time (the refusal needs the quota line, and no file may remain), or it is accepted and INV-29 turns the card error into an `unchecked` card whose status stays `done`. RED at HEAD. |
| NFR-7 (r5), INV-4, EC-12 (S4 R-3) | delegation → `test_an_unchecked_card_with_long_dropped_and_files_lists_stays_inside_the_nfr7_bound` | integration | Ten dropped entries of about 185 tokens and 60 written paths rendered uncapped → a 3,467-token card | All four free-text fields are over the cap, so the bound (the template's literal text, the short fields, and 4 × (cap + marker)) is close to tight. The marker must appear exactly 4 times, and the journal card must still hold every dropped entry and every path, so a fix cannot meet the bound by losing data. RED at HEAD. |
| INV-26, INV-9 (S4 R-4) | delegation → `test_a_finished_pair_replays_after_its_context_entry_was_superseded_and_new_pairs_still_run` | integration | Pair `a` names `#1` and supersedes it → relaunching `a` alone, or beside a new `b`, is refused by the context check instead of replayed, and `b` never starts | A precondition checks that `#1` was really replaced by `#2`. `a`'s generator has exactly two scripted steps, so a re-run is an unscripted call. `a` and `b` must each start and finish exactly once, and the cards must come back in task order. RED at HEAD. |
| INV-17, INV-15, INV-32 (S4 R-11) | verification → `test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages` | integration | `check_entry` skipped for pair agents → over-cap text, a live entry's text, a missing `supersedes` id, or a reworded repeat is staged, uses quota, and reaches the verifier | The commit re-check would drop these entries anyway, so the test reads the stage-time results, the quota line (exactly 4 of 5 left), and the verifier's first message (no `s2`). The verifier's own repeat must be refused with "already staged as s1". GREEN at HEAD; fails under `vmut V1`, `mutplug M1` and `s2mut S1`. |
| INV-16 (S4 R-11) | verification → `test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key` | integration | A verifier's entry is committed with the generator's key as `by` | The `(text, by, verified_by)` tuples are compared exactly, in commit order. GREEN at HEAD; fails under `vmut V3` and `mutplug M3`. |
| INV-19, INV-32, AC-17 (S4 R-11) | workspace → `test_edit_file_refuses_an_edit_that_would_pass_a_cap_and_changes_nothing[note-over-max-file-tokens, workspace-over-max-tokens]` | integration | `edit_file` without its caps → one edit grows a note past `max_file_tokens`, or the workspace past `max_tokens` | Each case trips exactly one cap: in the `max_tokens` case the note stays under `max_file_tokens`. The test compares byte snapshots and then makes a small edit. GREEN at HEAD; both cases fail under `vmut V2` and `mutplug M2`. `s2mut E1` fails only the first case, and `E2` only the second. |
| INV-32, INV-19, §12.4 (S4 R-8) | workspace → `test_a_memory_write_that_fails_on_disk_is_a_refusal_and_leaves_no_temp_file[remember, write_note, edit_file × replace-fails, lone-surrogate]` | integration | The atomic replace fails, or the text cannot be encoded as UTF-8 → a `.tmp` copy is left (it counts toward the caps), and the error escapes `execute` raw, with no quota line | `replace-fails` checks that the injected fault actually fired. Each case needs the rejection template and the quota line, no `*.tmp` anywhere, an unchanged byte snapshot, and a working next call. This is the only filesystem fault injection in the pack, granted for R-8 alone: a one-shot `os.replace` failure on the tool's target file. RED at HEAD. |
| INV-32, INV-19, INV-20 (S4 R-8) | workspace → `test_a_note_path_with_a_colon_is_saved_or_refused_without_leaving_stray_files` | integration | `notes/standup 10:30.md` on NTFS → the colon names a data stream, the write fails raw, and a stray `notes/.standup 10` remains | The test asserts either an exact save or a clean refusal with an unchanged snapshot. It is RED at HEAD on NTFS, and green on POSIX, where a colon is a legal file-name character. |
| EC-18, INV-17, INV-32 (S4 R-6) | workspace → `test_remember_tells_the_model_to_keep_a_long_paste_in_a_note_or_a_pointer[multi-line-log, one-line-over-the-cap]` | integration | A pasted log, or one line over the cap, is refused without saying where the content belongs (and the multi-line refusal repeats the paste) | A precondition checks that the paste contains neither advice word. The literal text of the rejection template and of the quota line is removed before the search, so only the problem text can supply "pointer" or "note". RED at HEAD. |

## Tests deliberately NOT written

| Candidate | Why it would not earn its keep |
|---|---|
| EC-15 (a sibling commits the same text first) and EC-16 (two pairs supersede `#5`) | No hook runs between one pair's commit and another's, so forcing the order needs polling (wall clock). Both go through the commit re-check that AC-37 and EC-17 drive, and the duplicate and supersede rules are pinned by AC-14 and AC-15. |
| `__post_init__` unit tests for each record in `vidbyte.lib.dataclasses.infinite` | They duplicate AC-2, AC-6 and AC-14, which reach the same validation through the model-facing boundary the spec promises, and they would pin internal error wording. |
| EC-30, EC-31, EC-36, EC-41, EC-45, EC-46, EC-47, EC-48, EC-49 | These are accepted limitations with no control to assert. EC-31 is owned by `tests/features/coding_agent/test_bash_tool_process_bounds.py`. |
| EC-14 (rubber-stamp verifier), EC-32 (`system=` option), EC-40 (root never delegates) | These are allowed behaviors with nothing to assert beyond the inherited loop. |
| EC-37 (two runs in the same second) | `resume(None)` may pick either run by design, and the explicit-id path is covered by AC-21. |
| EC-44 (`permission_policy` without EXECUTE) | This is unchanged `BaseAgent` permission behavior, owned by the existing permission tests. |
| EC-50 (a caller passes `history=`) | It goes through the same clean-context reset as AC-40. |
| An MCP server attached with `with_mcp_server` | That needs a live server. §13 says `add_tool` takes the same catalog path, and AC-36 and AC-41 use it. |
| NFR-4 (bounded write cost) and stress at the default caps | Read volume cannot be measured deterministically without instrumenting the implementation. The one size-shaped bug the spec names is covered by AC-42. |
| INV-34 (LINEAR and JEV unchanged) and INV-37 (`vidbyte.__all__` parity) | These are owned by the existing suite and by lint C016. This pack checks only the new names. |
| NFR-6 (repo gates), and live provider calls (NFR-2) | The gate is CI's job, and the spec forbids network access. |
| Any test of the non-goals NG-1 – NG-15 or Q-1 – Q-9 additions | Out of scope by rule (every Q defaults to no). |
| S4 R-2: protected names compared case-folded (INV-20, INV-21) | On this Windows host `Path.resolve()` returns the on-disk case of every existing protected name, so `Entries.jsonl`, `SEED/brief.md` and `.RUNS/x.jsonl` are already refused at HEAD, and the test would pass without proving anything. Making it fail here means replacing `FileSystemPermissions.resolve_scoped_path`, which is not a seam this pack fakes. The verifier's probe `v6_case_fold.py` remains the evidence. |
| S4 R-13 alternative: drop the `sleep(0)` yield and gate AC-37 with `Gate(2)` | This was not granted for S4; it would change an existing test's script. The yield stays, and the R-13 fix is a production comment. |

## Red run (before implementation)

Bootstrap: none run. `python -m pip install -e ".[dev]"` was deliberately skipped. This machine's global Python 3.11.0 already has `vidbyte-sdk` installed in editable mode from the canonical checkout, and other worktrees and tools depend on that install, so reinstalling from here would repoint it machine-wide. Every dev pin was verified present instead: pytest 8.3.5, pytest-asyncio 1.3.0, ruff 0.16.4, mypy 2.3.1, build 1.5.0, twine 6.2.0. Every command used `PYTHONPATH=$(pwd)`, as spec §13 directs.

Baseline at `1bc5c857`, before the pack: `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` → `4767 passed, 13 skipped in 38.37s`

```
PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider
→ 89 failed in 1.86s   (89 collected, 0 collection errors, 0 skipped)
  failure reasons (--tb=line, counted):
     73 ModuleNotFoundError: No module named 'vidbyte.agents.infinite'
      3 ModuleNotFoundError: No module named 'vidbyte.lib.constants.infinite'
      3 ImportError: cannot import name 'InfiniteMemoryPreset' from 'vidbyte.lib.enums'
      2 ImportError: cannot import name 'InfiniteMemoryAgent' from 'vidbyte'
      1 ImportError: cannot import name 'TokenEstimate' from 'vidbyte.lib.util'
      1 ImportError: cannot import name 'InfiniteMemoryRuntime' from 'vidbyte.agents'
      1 ImportError: cannot import name 'InfiniteEntryKind' from 'vidbyte.lib.enums'
      1 ImportError: cannot import name 'InfiniteAgentRole' from 'vidbyte.lib.enums'
      1 ConfigurationError: Prompt family does not exist: 'infinite_memory'
      1 ImportError: import error in vidbyte.agents.infinite (monkeypatch target of AC-33)
      1 AssertionError: vidbyte/agents/infinite does not exist (NFR-1 budget)
      1 AssertionError: assert {} == {'INFINITE_ME...ription', ...} (no Prompt.INFINITE_MEMORY_* members)

PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider
→ 89 failed, 4767 passed, 13 skipped in 47.47s
  FAILED/ERROR lines outside tests/features/infinite_memory_agent/: 0   (4868 collected = 4780 + 89)

python lint/run.py --rule A001 / --rule S020 / --rule A009 → SDK-LINT: PASS each, no finding in the new files
```

## S4 additions

After S3 the original 89 tests passed, and the S4 review (`review.md`) found bugs they let through. On spec r5 (HEAD `8d6c230a`), 18 cases in 9 new tests were added to the subject modules, and two non-assertion edits were made:

- **R-5:** the three adjacent literals in `test_map_labels_and_usage_read_the_disk_and_never_fail_on_bad_lines` are now one string. An AST comparison against HEAD confirms the value is byte-identical, and no assertion changed. S062 drops from 889 to 888, so S5 can restore `vidbyte/lib/registries/runtimes.py`.
- **R-18:** the pack README no longer says every test fails.

| Finding | Test | At HEAD |
|---|---|---|
| R-1 | `test_a_pair_whose_card_or_record_cannot_be_written_as_given_still_finishes_beside_its_sibling` × 3 | RED |
| R-3 | `test_an_unchecked_card_with_long_dropped_and_files_lists_stays_inside_the_nfr7_bound` | RED |
| R-4 | `test_a_finished_pair_replays_after_its_context_entry_was_superseded_and_new_pairs_still_run` | RED |
| R-6 | `test_remember_tells_the_model_to_keep_a_long_paste_in_a_note_or_a_pointer` × 2 | RED |
| R-8 | `test_a_memory_write_that_fails_on_disk_is_a_refusal_and_leaves_no_temp_file` × 6 | RED |
| R-8 | `test_a_note_path_with_a_colon_is_saved_or_refused_without_leaving_stray_files` | RED on NTFS (green on POSIX) |
| R-11 | `test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages` | GREEN |
| R-11 | `test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key` | GREEN |
| R-11 | `test_edit_file_refuses_an_edit_that_would_pass_a_cap_and_changes_nothing` × 2 | GREEN |

Red at HEAD, each failing for the right reason (`--tb=line`):

```
PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q -p no:cacheprovider
→ 14 failed, 93 passed
  R-1 u2028/u0085: launch_subagent failed instead of returning both cards: "[tool_error kind=execution_error]
       Tool execution failed: Each item of InfiniteResultCard.files must be one line of non-blank text; got 'notes/acme\u2028prices.md'."
  R-1 surrogate:   ... Tool execution failed: 'utf-8' codec can't encode character '\ud83d' in position 185: surrogates not allowed
  R-3:             the card is 3467 tokens, over the NFR-7 bound of 1642
  R-4:             relaunching the finished pair a was refused: [tool_error ...] No task was started ... Memory entry #1 is not a live entry
  R-8 ×6:          <tool> let the failed write out as a raw error: "... Tool execution failed: [Errno 13] Access is denied ..." / "... surrogates not allowed"
  R-8 colon:       the failed write escaped as a raw error: "... Tool execution failed: [WinError 87] The parameter is incorrect ..."
  R-6 ×2:          the refusal does not tell the model to store a pointer or a note
```

Mutation proof for R-11. The four R-11 cases are selected with `-k "when_it_stages or verifiers_own_key or edit_file_refuses_an_edit"`. The verifier's `vmut.py` and the engineering reviewer's `mutplug.py` are used as given, and `s2mut.py` (S2 scratch) adds finer mutants:

```
HEAD          4 passed
VMUT=V1       1 failed (test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages), 3 passed
VMUT=V2       2 failed (test_edit_file_refuses_..._changes_nothing[note-over-max-file-tokens], [workspace-over-max-tokens]), 2 passed
VMUT=V3       1 failed (test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key), 3 passed
VMUT=V4       4 passed   (the yield mutant; it is not an R-11 rule)
MUT=M1        1 failed (…_when_it_stages), 3 passed
MUT=M2        2 failed (both edit_file cases), 2 passed
MUT=M3        1 failed (…_verifiers_own_key), 3 passed
S2MUT=E1      1 failed ([note-over-max-file-tokens] only), 3 passed       (max_file_tokens check removed)
S2MUT=E2      1 failed ([workspace-over-max-tokens] only), 3 passed       (_room removed)
S2MUT=S1      1 failed (…_when_it_stages: "Staged as s2"), 3 passed       (stage check ignores the pair's staged list)
```

The red tests turn green under the review's proposed fixes, so they pin behavior rather than one implementation. Each VFIX fix in `vfix.py` turns only its own tests green: NOTEPATH fixes the two R-1 path cases, JOURNAL the R-1 surrogate case, CARDCAP R-3, REPLAY R-4, REPLACE the six R-8 write cases, and EC18 the multi-line R-6 case. `s2fix.py` applies all of them together, plus the over-cap advice and the colon refusal that the review described but did not code. Under it the whole pack gives `107 passed`.

Gates after the additions:

- `python lint/run.py` → `SDK-LINT: PASS`, with `S062 888 889 IMPROVED`, `S041 0 0 CLEAN`, `S047 0 0 CLEAN`, and `A001 642 642 RATCHETED`. No rule has a finding in the pack.
- `ruff check --select F,E9,B,ASYNC,DTZ` on the pack is clean.
- The full suite gives `14 failed, 5266 passed, 14 skipped`. All 14 failures are the new red tests in the pack; none is outside it.

## Notes for the implementer

- **Names the tests bind to:**
  - Exports: `vidbyte.{InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings, InfiniteMemoryPreset}`, `vidbyte.agents.{same three, InfiniteMemoryRuntime}`, `vidbyte.agents.infinite.{InfiniteMemoryAgent, InfiniteMemoryRuntime, InfiniteWorkspaceSettings, InfiniteMemoryAgentSettings}`, `vidbyte.tools.toolsets.InfiniteMemoryAgentTools`, `vidbyte.lib.util.TokenEstimate`, and the six enums in `vidbyte.lib.enums` with `AgentRuntimeType.INFINITE_MEMORY`.
  - Internal modules: `InfiniteWorkspace` in `vidbyte.agents.infinite.workspace` (`map_text`, `usage`, `entries`), and `vidbyte.agents.infinite.journal`.
  - Constants: `vidbyte.lib.constants.infinite.{INFINITE_DEFAULT_MAX_ITERATIONS, INFINITE_TOOL_RESULT_MAX_CHARS, INFINITE_CARD_TEXT_MAX_TOKENS, INFINITE_TRUNCATION_MARKER, INFINITE_MAP_MAX_TOKENS, INFINITE_MORE_FILES, INFINITE_NO_DESCRIPTION, INFINITE_SEED_LABEL, INFINITE_FINISHED_PAIR_LINE, INFINITE_RESERVED_TOOL_NAMES}`.
  - The 40 `Prompt.INFINITE_MEMORY_*` members.
  - The patch target `vidbyte.agents.infinite.agent.INFINITE_HISTORY_MAX_TOKENS`.
- **Agent names and keys are asserted** exactly as in §9.1 and §13: root `analyst`; `analyst/root/<name>/gen|ver`; nested `analyst/root/a/gen/b/gen`. Keys are `root/<name>` and `root/a/gen/b`; `by` and `verified_by` are `root/<name>/gen|ver` (and `root` for root entries).
- **Rendered text is matched against the catalog's own templates.** These are `result_card`, `replayed_label`, `launch_rejected_prompt`, `memory_rejected_prompt`, `quota_line`, `remember_saved_prompt`, `note_saved_prompt`, `entry_dropped_prompt`, `resume_prompt`, and `verifier_system_prompt`. Placeholders match anything; the literal text must appear as written. Render with `str.format` on the catalog text, and do not post-edit it. Each `launch_<field>_description` must be the `description` of its task-card schema property.
- **Error text must name** each of the following:
  - the case's field or value (`max_parallel`; the duplicate name; `verifier_prompt`; `generator_prompt`; the unknown tool; `99` or `40` for context ids; the bad task name and `INFINITE_TASK_NAME_PATTERN`; `budget_share`);
  - `max_agents` with the started count;
  - `already recorded as #N`;
  - a quota line whose numbers read `0` and `5` after five accepted calls;
  - `entries.jsonl` and the line number in a commit drop;
  - the journal line number in a resume refusal;
  - for caps, the cap's name or value.
- **On disk:**
  - After a torn tail, `run_finished` must start on its own line.
  - A card's summary and review are `text[: 400 * 4] + INFINITE_TRUNCATION_MARKER`; the kept part must be a prefix of the reply.
  - The map has one line per file that contains its path, with the seed or no-description label on that line, and ends with `INFINITE_MORE_FILES.format(count=...)` when cut.
  - The verifier's first message must contain the status value (for example `done`) and the staged key (`s1`).
  - The journal must call `os.fsync`, or a module-level `fsync` name in `journal.py`, once per record.
- **AC-41 and `BaseAgent` wrapping:** `BaseAgent.generate_reply` wraps any `Exception` from the runtime in `AgentExecutionError` (`vidbyte/agents/base.py`, the `except Exception` in `_generate_reply`). If the reserved-name check runs inside `InfiniteMemoryRuntime.arun`, as §12.3 row 21 places it, the `ConfigurationError` arrives as the wrapper's `__cause__`, which the test accepts. Either way, no runner call and no journal are allowed.
- **Fixtures added:** only the pack's own `infinite_memory_fixtures.py`. No shared fixture, conftest, or existing test was changed. The S4 additions use the same fixtures; their only edit to an existing test is R-5's literal join, which changes no value.
- **S4 tests bind to these behaviors:**
  - A failed workspace write must leave no file whose name ends in `.tmp`.
  - The R-8 fault is a one-shot `os.replace` failure on the tool's target file. A different atomic-write mechanism that never calls `os.replace` would fail the test's precondition, not pass it silently.
  - Every refused memory write needs the `memory_rejected_prompt` rendering and the quota line.
  - The R-3 bound counts the template's literal text, the name, key, status, verdict, and `-` for the empty entries field, plus 4 × (cap + marker). It also expects exactly four markers.
  - EC-18's advice must contain "pointer" or "note" outside the template and the quota line.
- **Must not change:** the tests. If one looks wrong against the spec, report it rather than editing it.
