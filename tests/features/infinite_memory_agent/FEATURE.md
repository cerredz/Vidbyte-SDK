# Feature: InfiniteMemory agent — delegation, guarded memory, and resume

## High-Level Feature Description

A developer hands one long task of any kind to `InfiniteMemoryAgent`. Its root agent keeps its own context small by handing work to generator→verifier *pairs* of fresh `BaseAgent`s through one `launch_subagent` tool. The parent sees only one capped result card per pair. Every agent in the tree shares one workspace folder. Memory is written only as small, typed entries and append-only notes, under fixed limits that are checked against the disk before every tool write. A pair's entries are staged in memory and committed only after its verifier returns a verdict. Every run, pair start and pair finish goes into an append-only journal, so `resume()` continues a crashed or Ctrl-C'd run without re-running finished pairs.

If this feature regresses, the failure is usually silent: unverified memories land on disk as if verified, a child's transcript floods the root's context, a crashed run re-does finished work (and pays for it again), the workspace grows past its caps, or one failing pair throws away every sibling's finished card. The tests here are written to make each of those failures loud.

## Contract

- `from vidbyte import InfiniteMemoryAgent, InfiniteMemoryAgentSettings, InfiniteWorkspaceSettings, InfiniteMemoryPreset` works. The agent is built only from a validated `InfiniteMemoryAgentSettings`. Construction creates or attaches the workspace, creates `entries.jsonl`, `superseded.jsonl` and `files.jsonl`, copies seeds to `seed/<basename>`, and refuses a workspace already over a cap.
- `run()`/`arun()` open a journal (`.runs/<run_id>.jsonl`): `run_started`, then `pair_started` per new pair before any agent of its batch starts, `pair_finished` after its commit, and `run_finished` only when the root's loop returns normally. Every record is one fsynced JSON line.
- Every agent holds exactly the preset tools for its role (spec INV-6): `bash`, `grep`, `read_lines`, `remember`, `write_note`, plus `edit_file` under FULL, `launch_subagent` for the root and generators below `max_depth`, `drop_entry` for verifiers only, and the developer's extras (the root all of them; a pair exactly the ones its task card names).
- `launch_subagent` validates the whole batch before starting anything. A bad batch returns `ToolResult.error`, starts no agent, writes no journal record, and leaves the tool usable.
- A pair's verifier starts after its generator returns and sees the generator's status, capped summary, staged entries and written paths, never its transcript. The verdict is the last `VERDICT:` line; no line, or a verifier error, is `unchecked`, and then every staged entry is dropped.
- A pair turns `VidbyteSdkError`, `OSError` and `ValueError` into its own card; siblings and the parent keep going. Cancellation propagates and leaves the journal resumable.
- `resume(run_id=None)` continues the newest unfinished run (or the named one), replays finished pairs from the journal and re-runs interrupted ones; it refuses unsafe, unknown, finished or absent runs before any model call.
- Each run starts from a clean context; the task, the rules and the workspace map reach every model call while old tool exchanges are trimmed past `INFINITE_HISTORY_MAX_TOKENS`.

## Actors / Callers

SDK callers that build `InfiniteMemoryAgent` and call `run`, `arun`, `resume`, `aresume`, `add_tool`, `get_usage`. The model inside every agent of the tree, which calls the preset tools. A developer or `bash` editing workspace files between tool writes. `vidbyte.sessions.Session`, which must refuse the agent.

## Inputs and Preconditions

An existing `root_dir`; a workspace root that is not an existing file; existing seed files with unique basenames; caps within the bounds of spec §9.3. The tests use `tmp_path` for every path, scripted model runners, and the real filesystem. `bash` needs a POSIX bash (Linux CI) or Git for Windows bash locally.

## Observable Outcomes

The model calls each agent makes (its `prompt`, `system`, `messages` and offered `tools`), tool results as the next call's tool messages, `reply.content` and `reply.metadata["stop_reason"]`, files under the workspace root, `.runs/<run_id>.jsonl`, `agent.workspace.map_text()`, `agent.get_usage()`, and raised `ConfigurationError` / `SessionError` / `CancelledError`.

## State Transitions

Entry: staged (in a pair's memory) → live (`entries.jsonl`) → superseded (`superseded.jsonl`), or staged → dropped (never written). Run: started → finished, or started → interrupted (no `run_finished`) → resumed → finished. Pair key: started → finished; a finished key is replayed, never re-run, within the run and after a resume.

## Invariants

- The parent's conversation receives only result cards; a card's summary and review are each at most `INFINITE_CARD_TEXT_MAX_TOKENS` tokens, cut text ending in `INFINITE_TRUNCATION_MARKER`, and the rendered card cuts its joined `dropped` and `files` text the same way (NFR-7 as amended in spec r5), while the journal keeps both lists whole.
- Nothing a pair stages reaches disk before its verifier returns; nothing reaches disk on `unchecked`.
- No tool write leaves the workspace above `max_files` or `max_tokens`, or a note above `max_file_tokens`; usage is recomputed from disk, so files `bash` wrote count. The bookkeeping files are bounded only by `max_tokens`.
- A rejected tool call writes nothing and the tool stays usable.
- A finished pair key is never run twice in one run.
- Child usage reaches the root's ledger exactly once.

## External Dependencies

The local filesystem (real, under `tmp_path`); `bash` (real subprocess); the model runner (the only fake, at `BaseAgent._runner_for_model`); the prompt catalog (real); `asyncio` scheduling, controlled with gates instead of sleeps.

## Known Failure Modes

Each line is *input + state → wrong output if unguarded*, with the test that catches it.

- Generators launched in one call run one after another → the batch is slow and the "parallel" cap means nothing (`test_two_tasks_run_concurrently_and_each_verifier_follows_its_own_generator`).
- Cards returned in completion order → the parent pairs the wrong card with the wrong task (same test).
- A child's tool calls or replies copied into the parent's conversation → the root's context fills (same test; `test_a_long_generator_reply_is_cut_in_its_card_and_the_rest_never_reaches_the_root`).
- One bad task in a batch starts the good ones, or writes a journal record → orphaned pairs and a corrupt journal (`test_an_invalid_batch_starts_nothing_and_the_tool_stays_usable`).
- `max_agents` checked per task instead of per batch → two of three pairs start and the third fails (`test_a_batch_that_would_pass_max_agents_is_refused_whole`).
- Verifier holds `launch_subagent`, or a depth-`max_depth` generator does → unbounded trees (`test_depth_cap_and_role_decide_who_holds_launch_subagent_and_drop_entry`).
- A card names a tool its parent lacks → privilege escalation; extras added with `add_tool` (the MCP path) never reach children (`test_a_task_card_grants_exactly_the_extras_it_names`).
- Staged entries written at `remember` time → siblings act on unverified facts (`test_staged_entries_reach_disk_only_after_the_verifier_returns`).
- Missing verdict treated as passed → unreviewed memory committed as verified (`test_no_verdict_or_a_failing_verifier_drops_every_staged_entry`).
- Bold or upper-case verdict lines unrecognized, or the first verdict line wins → wrong verdict; a FAILED verdict dropping entries contrary to INV-15 (`test_verdict_is_read_from_the_last_matching_line_in_any_markdown_or_case`).
- A generator exception escapes `ParallelPipeline` → every sibling's finished card is lost (`test_a_failed_or_blank_generator_skips_its_verifier_and_its_sibling_still_reports`).
- A malformed bookkeeping line crashes a commit or the map → the run dies mid-batch (`test_a_malformed_entries_line_drops_each_pairs_entries_but_the_run_finishes`).
- Rejected `remember` calls counted against the quota, case/whitespace duplicates accepted, or the quota unenforced (`test_root_remember_rejects_each_rule_breaking_entry_and_enforces_the_quota`).
- A supersede that copies instead of moves → grep still finds the stale fact (`test_root_supersede_moves_the_old_entry_out_of_entries_and_out_of_grep`).
- `write_note` escaping the root, writing seeds, journals or bookkeeping files, or code files (`test_write_note_refuses_every_path_and_size_breach_and_changes_nothing`).
- Usage cached instead of recomputed from disk → bash fills the workspace and tools keep writing (`test_write_note_counts_files_bash_wrote_toward_the_token_cap`).
- `max_file_tokens` applied to `entries.jsonl` → memory goes read-only after a few hundred entries (`test_entries_file_is_bounded_by_the_workspace_total_not_the_note_cap`).
- Grep skips files over 1 MB → a large `entries.jsonl` becomes invisible (`test_grep_finds_a_live_entry_in_an_entries_file_over_one_megabyte`).
- Map rendered once per run, or never into children → agents work from a stale picture (`test_every_agent_sees_the_map_and_the_roots_map_refreshes_after_each_tool_iteration`).
- Journal records buffered and fsynced late → a crash loses records the run already acted on (`test_every_journal_record_is_fsynced_before_the_next_one_is_written`).
- A torn final journal line blocks resume, or a run_finished appended onto the torn fragment corrupts the journal (`test_resume_skips_a_torn_final_journal_line`); a malformed earlier line is silently skipped instead of refused (`test_resume_rejects_a_malformed_middle_journal_line`).
- The workspace fills between staging and commit and the commit writes past `max_tokens` anyway (`test_an_entry_that_no_longer_fits_at_commit_is_dropped_with_the_cap_reason`).
- `resume("../x")` reads outside `.runs/`; resume of a finished run re-runs it (`test_resume_refuses_unsafe_unknown_finished_or_missing_runs_before_any_model_call`).
- Resume re-runs finished pairs, or pastes their full cards into the root's first message (`test_resume_replays_finished_pairs_and_reruns_interrupted_ones`).
- A run-time tool named `remember` (MCP) fails the run after `run_started` → an unfinished journal that every `resume()` then trips on (`test_a_run_time_tool_named_like_a_run_bound_tool_fails_before_the_journal_starts`).
- History never trimmed → a long root overflows; trimming drops the task or the map (`test_root_history_is_trimmed_past_the_cap_while_task_and_map_survive`).
- A second `run()` on the same object replays the first run's tool calls and reply in the system string (`test_a_second_run_on_the_same_agent_starts_from_a_clean_context`).
- `launch_subagent` cut by `tool_timeout_seconds` or `result_max_chars` → whole batches lost (`test_launch_subagent_is_exempt_from_the_tool_timeout_and_result_cap`).
- The API key in a settings `repr`, the journal, or a workspace file (`test_api_key_stays_out_of_the_settings_repr_the_journal_and_the_workspace`).
- A note path holding U+2028 or U+0085, or a lone surrogate in a reply, makes building the card or writing `pair_finished` raise outside the pair's guard → `launch_subagent` fails, every sibling's card is lost, and the key re-runs on relaunch (`test_a_pair_whose_card_or_record_cannot_be_written_as_given_still_finishes_beside_its_sibling`).
- `dropped` and `files` rendered uncapped → one unchecked pair puts thousands of tokens into the parent's context (`test_an_unchecked_card_with_long_dropped_and_files_lists_stays_inside_the_nfr7_bound`).
- Replayed keys checked like new ones → a finished pair whose context entry was since superseded is refused instead of replayed, and the new tasks beside it never start (`test_a_finished_pair_replays_after_its_context_entry_was_superseded_and_new_pairs_still_run`).
- A pair agent's `remember` staged without the entry rules → over-cap text, live duplicates and repeats wait in the pair until commit, using quota and misleading the verifier (`test_a_pair_agents_remember_is_checked_against_the_entry_rules_when_it_stages`).
- A verifier's own entry stamped with the generator's key → memory misattributes who wrote it (`test_an_entry_the_verifier_stages_is_committed_under_the_verifiers_own_key`).
- `edit_file` without the size caps → one edit grows a note or the workspace past its cap (`test_edit_file_refuses_an_edit_that_would_pass_a_cap_and_changes_nothing`).
- A failed atomic replace, or text UTF-8 cannot encode, leaks a `.tmp` copy that counts toward the caps and escapes the tool as a raw error with no quota line (`test_a_memory_write_that_fails_on_disk_is_a_refusal_and_leaves_no_temp_file`); a colon in a note path leaves a stray NTFS stream base file (`test_a_note_path_with_a_colon_is_saved_or_refused_without_leaving_stray_files`).
- A pasted log refused without saying where the content belongs → the model retries the paste instead of writing a note (`test_remember_tells_the_model_to_keep_a_long_paste_in_a_note_or_a_pointer`).
- A read-only seed copied with its mode bits → the next agent that attaches to the workspace cannot overwrite the copy and fails with a raw `PermissionError` (`test_a_read_only_seed_is_copied_again_each_time_an_agent_attaches`).
- A two-file memory write that fails on its second file after the first was written → the model is told nothing was saved while `superseded.jsonl` already holds the old entry, so a retry duplicates it (`test_a_supersede_whose_new_text_cannot_be_written_changes_neither_entry_file`), or a new note stays on disk with no description and spends the new-file allowance (`test_a_new_note_whose_description_cannot_be_written_leaves_no_note_and_keeps_the_allowance`).
- One staged entry UTF-8 cannot encode reaches the commit → the pair's verdict turns `unchecked` and its valid entries are lost with it (`test_an_entry_text_that_cannot_be_written_never_costs_the_pair_its_verdict_or_other_entries`).

What an easy generated test would miss: concurrency proven by timing instead of a gate; "no leak" checked only on the final reply instead of every root call; quota checked without interleaved rejections; resume tested only from a journal the implementation wrote itself (never hand-written in the documented shape); a torn line without its missing trailing newline.

## Historical Regressions

The pack was written red before the implementation (spec r3, S2). Spec review rounds R-1…R-23 shaped several tests: R-16 (AC-40 second run), R-17 (AC-37 malformed line), R-18 (AC-42 grep over 1 MB), R-19 (AC-38 upper-case verdict), R-20 (AC-31 replay-only batch), R-21 (AC-33 equal-size groups), R-23 (AC-41 reserved name at run time).

The S4 code review (`docs/spec/infinite-memory-agent/review.md`, a separate R- numbering) found bugs that the 89 original tests let through, and the tests named above now pin them: R-1 (card build and `pair_finished` outside the pair guard), R-3 (uncapped `dropped` and `files`), R-4 (replay refused by the context check), R-6 (EC-18 refusal without advice), R-8 (leaked temp files and raw write errors), and R-11 (stage-time entry rules, `edit_file` caps, and the verifier's `by` stamp could each be deleted with the pack still green).

The S5 re-review found two more that the 107 tests at that point let through: R-26 (the R-7 fix copied a read-only seed's mode bits, so a second attach raised `PermissionError`) and R-27 (a refused two-file memory write could leave its first file changed, and one unwritable staged entry turned a pair's verdict `unchecked`). The four tests named above for those lines pin them.

## Test Suite Map

- `test_infinite_memory_acceptance.py` — the §4 snippet as written, staging-then-commit, the usage roll-up, and a second agent attaching to the same workspace. Start here for a caller-visible regression.
- `test_infinite_memory_contract.py` — exports, enum values, prompt-family membership, runtime registry and refusal, session refusal, loop defaults, settings validation, the exact tools and schemas the model is offered, `TokenEstimate`, prompt text free of coding-only rules, and the complexity budget.
- `test_infinite_memory_delegation.py` — `launch_subagent`: concurrency, ordering, batch validation, depth and role tools, `max_agents`, failure isolation, partial generators, card caps, extras by name, context pasting, replay, verifier input, and tool-limit exemption.
- `test_infinite_memory_verification.py` — verdict parsing, `unchecked` handling, `drop_entry`, and commit re-checks against a corrupted `entries.jsonl` or a workspace that filled up.
- `test_infinite_memory_workspace.py` — `remember`, supersede, `write_note`, `edit_file`, the caps (including bash bypass), large bookkeeping files, and the workspace map.
- `test_infinite_memory_resume.py` — journal order and durability, `resume` replay and refusals, torn and malformed journals, cancellation, the reserved-name check before the journal, and key secrecy.
- `test_infinite_memory_context.py` — history trimming and a clean context per run.
- `infinite_memory_fixtures.py` — the scripted model tree, builders, and readers every module uses.

Run: `PYTHONPATH=$(pwd) python -m pytest tests/features/infinite_memory_agent -q` from the repository root.

## Omitted Testing Strategies

- Live provider calls: offline by NFR-2; the runner is the only fake.
- Cross-process races (two processes on one workspace, EC-30) and a process kill between commit and `pair_finished` (EC-46): accepted limitations with no control to test (D-23, D-4).
- Windows bash cancellation leaving a stray process (EC-31): a known `BashTool` limitation owned by `tests/features/coding_agent/test_bash_tool_process_bounds.py`.
- Stress at the default caps (200 files, 250,000 tokens, 200 agents): the caps are exercised with small values passed through settings; the 1 MB grep test covers the one size-shaped bug the spec names.
- Hypothesis-style property tests: `hypothesis` is not a dependency; `TokenEstimate`'s algebra is checked over a seeded sample instead.
- MCP servers: tools added with `add_tool` take the same path into the catalog (spec §13), so no MCP server is started.
- Sibling commit races (EC-15 duplicate text, EC-16 double supersede): no hook runs between one pair's commit and another's, so forcing the order would need polling. Both go through the commit re-check that the AC-37 and EC-17 tests drive, and the duplicate and supersede rules themselves are pinned by the AC-14 and AC-15 tests.
- Rubber-stamp verifiers (EC-14), a root that never delegates (EC-40), and an explicit `system=` option (EC-32): accepted behaviors with nothing to assert.
- Accessibility, browser, migration: no UI and no earlier on-disk format.
- Case-folded protected names (S4 R-2, macOS): Windows `resolve()` returns the on-disk case, so `Entries.jsonl` or `SEED/brief.md` is already refused here and a test would pass at HEAD for the wrong reason. Making it fail would mean replacing `FileSystemPermissions.resolve_scoped_path`, which is not a seam this pack fakes.
