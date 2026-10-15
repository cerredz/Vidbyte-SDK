# Test plan: InfiniteMemory agent — a delegating agent with a shared, guarded file workspace for memory

Spec: `docs/spec/infinite-memory-agent/spec.md` r3 · Framework: pytest 8.3.5 + pytest-asyncio 1.3.0 (Python 3.11.0) · Prior art copied: `tests/features/jev_bulk_work/test_jev_bulk_work.py` (fake runners routed by agent name to agents built inside a tool), `tests/features/sdk_managed_text/managed_text_fixtures.py` (a shared fixture module with no feature imports at module level), `tests/test_jev_compute_situations.py:255` (the tool-call response shape), `tests/test_jev_agent.py:441-450` (registry and refusal)

Pack: `tests/features/infinite_memory_agent/`. It holds `README.md`, `FEATURE.md`, `infinite_memory_fixtures.py`, and 7 test modules with 89 test cases. In the table below, `acceptance`, `contract`, `delegation`, `verification`, `workspace`, `resume` and `context` stand for `test_infinite_memory_<name>.py`.

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
- **Fixtures added:** only the pack's own `infinite_memory_fixtures.py`. No shared fixture, conftest, or existing test was changed.
- **Must not change:** the tests. If one looks wrong against the spec, report it rather than editing it.
