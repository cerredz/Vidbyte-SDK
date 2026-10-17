# Test plan: Composite thread functions across Grok, opencode and Muse

Spec: `docs/spec/native-thread-compose/spec.md` r3 (approved) · Framework: pytest 8.3.5 + pytest-asyncio 1.3.0 in strict mode (`@pytest.mark.asyncio` on every async test, `--strict-config --strict-markers`), the real `git`, and the base stand-in `tests/features/harness_threads/fake_harness.py` launched from its path · Prior art copied: `tests/features/harness_threads/conftest.py` (sandbox layout, `scenario`/`command`/`stand_in`, log readers, `fast_stop`, `wait_until`, `alive`, `pack`), `tests/features/harness_threads/test_harness_threads_acceptance.py` (the AC-1 shape), and `tests/features/harness_threads/test_harness_threads_static_policy.py` (unchanged; it reaches the compose modules through `rglob`)

## What the pack must accomplish

The pack has to stop a wrong compose from merging. It must let one through only if every composite returns the right record for each failure a model, a vendor CLI, git or the caller can cause, with no reader changing the workspace and no key leaking. The pack is `tests/features/harness_compose/`: 15 test files, 76 test functions and 276 collected cases. Five other fields solve the same problem, and each lent the pack its method:

- **Fault injection** (resilience engineering). Each failure is a scripted stand-in mode: `fail`, `key_rejected`, `hold`, a cut answer, a writer that runs `git init`, or a reader that writes.
- **Oracles** (differential testing). The expected trees and diffs come from the test's own `git`, using a temporary index outside the repository and the spec's exact `diff` flags. Expected prompts come from rendering the prompt files directly. Compose's own output is never the expected value.
- **Taint tracking** (security testing). Every key is random, and a leak is any 12-character fragment of it found in a prompt, an argv, an environment, an error or a `repr`.
- **Happens-before ordering** (concurrency testing). A `CliRunner` spy records enter and exit positions, so overlap is proven by order, never by clocks. Held stand-ins are released only after the expected starts. A "must not start" condition gets a bounded settle wait.
- **Boundary-value analysis.** Every bound is tested past the limit and again at the limit.

More cases than the usual 8 to 25 are justified, because the spec has 23 ACs (all P0 or P1), 36 invariants, 8 security rows and tables that are themselves the contract:

- 58 invalid inputs (AC-14);
- 22 prompt files, each tested twice;
- 25 record bounds (NFR-8);
- 7 command-line unit cases (INV-36);
- 10 function signatures and 9 alias signatures.

Each parametrized case is one row of one of those tables. The red run takes about 10 seconds. After implementation, the feature-level cases launch the same stand-in as the base pack, which runs its 438 cases in about 47 seconds on this host, so the pack is expected to stay well under the 3-minute target. S3 confirms this with a timed green run.

## Coverage map

File names drop the `test_harness_compose_` prefix and `.py`. **E2E** means the §4 snippet runs in a fresh interpreter against stand-ins on `PATH`. **Feature** means composites drive real child processes (the stand-in, launched from its path) and the real `git`. **Unit** means in-process records, decoders, signatures and helpers. **Static** means files and source are read without running compose.

| Spec ID | Test (file → name) | Level | Failure it catches (input + state → wrong output) | How it could pass vacuously, and why it does not |
|---|---|---|---|---|
| AC-1 | acceptance → `test_developer_snippet_runs_as_written_against_stand_ins_on_path` | E2E | The §4 snippet is run with placeholder `XAI_API_KEY`/`ZHIPU_API_KEY`, the home redirected, `.exe`/script stand-ins on `PATH` and a one-commit repository. A broken compose prints other thread ids, other decisions or another `failed_stage`, raises, or leaves a worktree, an index folder, a registration or extra files behind | The snippet is byte-identical to the spec §4 block (checked by script at S2). Expected line 1 is built from the session ids of the exact launches in the stand-in logs. The `git status` set is exact. The exit code is 0 with no traceback |
| AC-2 | chain → `test_opencode_then_grok_sends_the_answer_and_the_writers_diff`; surface → `test_each_alias_has_its_exact_signature_and_returns_a_coroutine` | Feature; Unit | opencode writes `notes.txt` and answers "done". Possible faults: Grok's prompt lacks the answer or the diff; opencode gets more than the prompt; outcome 1 carries a diff; the thread ids are swapped; the two steps overlap; a pair alias is missing or takes positional steps | The expected Grok prompt is `chain_turn`, rendered by the test from the file with the oracle's diff text, and compared whole. Diff files and text equal the oracle's. The six pair signatures are written out in the test |
| AC-3 | verify → `test_trio_runs_the_writer_alone_then_reviews_its_diff_in_place_and_in_a_worktree` | Feature | Possible faults: the writer overlaps a reader; Grok is relocated or lacks `--permission-mode=plan`; Muse runs in the workspace, or in a worktree missing the writer's file; a verifier sees the writer's answer; verdicts are out of order; agreement is wrong; the worktree or the registration survives | Muse logs the SHA-256 digests of the files it finds in its cwd (`observe_files`), compared with the bytes written. Approve plus reject must give `agreement is False`, so an always-true agreement fails. Order comes from the spy |
| AC-4 | handoff → `test_handoff_resumes_the_source_thread_and_seeds_a_new_target_thread` | Feature | A `bind_continue(continue_grok_thread)` source on a thread made earlier. Possible faults: the summary forks or starts a new thread; the seed lacks the summary; the target resumes a thread; git runs | The source thread is made by a real direct call, so `--resume` must equal its id. The seed is compared with `handoff_seed` rendered with a summary that holds braces. The workspace is not a repository, so a git child would also fail loudly |
| AC-5 | stages → `test_three_stages_on_three_harnesses_pass_each_answer_on` | Feature | Grok, opencode and Muse stages. Possible faults: stage k misses stage k−1's answer; braces in answers are parsed again; stage 1's `{{` is not unescaped; an attempt resumes a thread; git runs or a sleep happens | The prompts must be exactly equal. The answers hold `{one}` and `{{two}}`, so a second format pass changes them. Resume flags are checked per harness. Sleeps from compose modules are counted by a spy on `asyncio.sleep` |
| AC-6 | ensemble → `test_ensemble_plans_proposes_selects_and_implements_in_order` | Feature | Planner, three proposers (a Grok fork, opencode, Muse), selector and implementer. Possible faults: stages out of order; the fork does not branch the planner's thread; worktree proposers share a folder or run in place; a proposer sees another role; a block is missing; the implementer runs before the backstop or sees other proposals; an extra Grok home appears | The backstop `write-tree` must lie strictly between the selector's exit and the implementer's start. Blocks are rendered from `proposal_block`. Each role's isolation is checked by the absence of the other identities |
| AC-7 | chain → `test_failed_middle_step_ends_the_chain_with_the_functions_own_error` | Feature | A three-step chain whose middle opencode step fails with `run_failed`. Possible faults: the error escapes, or is wrapped or copied; the third step starts; the template is parsed again; git runs without `{diff}` | The traceback must pass through `vidbyte/harnesses/native/opencode/`, so a rebuilt error fails. `exit_code == 93` and the vendor text are set by the stand-in. "third" is absent from both the log and the spy |
| AC-8a | verify → `test_grok_reader_that_writes_raises_reader_changed_after_every_verifier` | Feature | A Grok `PLAN` verifier writes a file. Possible faults: the write is accepted; the error comes before the sibling finished; the error lacks the file, the workspace or the record | Both stand-ins logged an answer. The last `write-tree` enters after every verifier exit. `error.diff` comes from the real snapshots. The message order is checked by `check_compose_error` |
| AC-8b | verify → `test_worktree_readers_that_write_leave_the_workspace_untouched` | Feature | opencode and Muse verifiers write files. Possible faults: a write reaches the workspace; a worktree survives; a verdict is dropped | The stand-ins logged `wrote`, so the writes happened. The workspace digests must equal exactly the committed files plus the writer's file |
| AC-8c | ensemble → `test_single_proposer_that_writes_stops_the_ensemble_before_the_implementer` | Feature | A Grok proposer writes. Possible faults: no `READER_CHANGED_WORKSPACE`, or the implementer starts | The implementer must be absent from the log and from the spy. `error.diff` names the proposer's file. The selection was offered block 1 with no round (EC-70) |
| AC-9 | answers → `test_cut_verdicts_are_repaired_on_the_same_thread_and_never_graded` | Feature | The first answer is cut, but its prefix is a valid approve; separately, every answer is cut. Possible faults: the cut prefix is graded; the repair goes to a new thread or another worktree; a value comes from cut text; there are not exactly 3 turns | `NATIVE_RESULT_TEXT_MAX_CHARS` is lowered so that the cut prefix decodes to approve while the repair answers reject. The expected verdict is reject, so grading the cut answer fails |
| AC-10 | concurrency → `test_cancelling_a_verify_stops_both_trees_removes_the_worktree_and_frees_the_lock` | Feature | Cancellation while Grok and opencode verifiers and their grandchildren hold. Possible faults: `CancelledError` is swallowed or converted; a process survives; the worktree survives; the Grok lock stays held | The cancel happens only after both stand-ins and both grandchildren logged a start. All four pids must be dead within the base stop bound. A later composite's Grok step must finish within 30 s |
| AC-11 | concurrency → `test_grok_verifiers_on_one_workspace_take_turns_while_opencode_runs_beside_them`, `test_composites_serialize_grok_per_workspace_and_overlap_across_repositories` | Feature | Three held Grok verifiers plus opencode on one workspace, and composites across workspaces. Possible faults: two Grok steps overlap; opencode is serialized behind Grok; there is one lock per composite or one global lock | A negative check (no second Grok start within 1.5 s while the first holds for up to 30 s) is paired with positive overlaps read from spy positions, so neither "everything serial" nor "everything parallel" passes |
| AC-12 | stages → `test_failed_attempts_follow_the_decision_table` (4 cases) | Feature | `retries=2` with a ladder, for `run_failed`, `timed_out` and `key_rejected`, and `run_failed` with no ladder. Possible faults: wrong rungs or decisions; the ladder is not used from attempt 2; an attempt resumes; stage 2 starts; a sleep happens | `--reasoning-effort` in each launch's argv shows which config ran. `timed_out` uses real step timeouts under `fast_stop`. The no-ladder case pins EC-53 |
| AC-13a | git → `test_folder_outside_any_repository_is_not_a_git_repository` (5 calls); chain AC-7, handoff AC-4 and stages AC-5 tests for the git-free half | Feature | Each git-needing call outside any repository. Possible faults: a vendor launches first; the error is a different one; git's text is missing. Separately, a git-free composite refuses a non-repository | `GIT_CEILING_DIRECTORIES` at the sandbox root makes the case machine-independent. The observations "rev-parse" and "128" and git's own text are checked in order |
| AC-13b | git → `test_no_git_on_path_is_git_unavailable_before_any_launch` (5), `test_git_the_os_will_not_start_is_git_unavailable` (2) | Feature | `PATH` without git, or a git file that is not a program. Possible faults: a launch happens, or the problem is another one | `PATH` is only the sandbox bin. The broken file exists and is marked executable, so "not found" cannot be confused with "refused" |
| AC-14 | validation → `test_invalid_input_is_refused_before_any_git_launch_or_folder` (58 cases, the spec list and more) | Feature | Each invalid input. Possible faults: the refusal comes after a git child, a launch or a temporary folder; the field is wrong; the key appears in the message | The workspace is a repository with git reachable, so a composite that checked git first would show a child in the spy. The `CASES` and `FIELDS` keys must be equal. Status, files, refs and worktrees are compared before and after |
| AC-15 | keys → `test_chain_splices_answers_and_diffs_with_every_key_redacted`, `test_ensemble_splices_roles_proposals_and_guidance_with_every_key_redacted`, `test_errors_and_reprs_never_show_a_key_while_result_and_diff_stay_raw`, `test_git_text_and_file_names_that_hold_a_key_are_scrubbed_from_errors` | Feature | Stand-ins echo keys into answers, plans, proposals, guidance, files, file names and an untracked repository's folder name. A fragment then reaches a later prompt, git's argv or environment, an error's text or attributes, a `repr` or a `ConfigurationError`; or the records are scrubbed; or `os.environ` changes | Keys are random and searched as every 12-character fragment. `[redacted]` must appear, which proves the value was spliced. The raw text is asserted in `result`/`diff`. Git's text ("does not have a commit checked out") must still be in `git_message` |
| AC-16 | answers → `test_each_problem_gets_a_repair_naming_it_and_an_error_ends_the_answer` | Feature | Prose, then an extra member, then a valid verdict; three bad answers; an error on the first repair. Possible faults: the wrong number of turns; a repair that does not name its problem; a new thread; a crash; a turn after the error | The expected problem texts come from `JsonText` itself or from the member names, never from compose's wording. Turn counts and thread continuity come from the stand-in logs |
| AC-17 | workspace → `test_capture_diff_shows_only_the_blocks_change_without_line_ending_noise` | Feature | Earlier CRLF edits and an untracked file, then `core.autocrlf=true`, then a writer that edits the edited file and adds one. Possible faults: earlier edits show; the new file is missing; carriage returns appear; there is no cut at a lowered cap | The expected text is the oracle's diff taken just before and just after the block, compared exactly. The cap is lowered to 40 with the text proven longer than 40. The files cap is lowered to 1 with 2 files |
| AC-18 | workspace → `test_in_worktree_holds_the_working_content_isolates_writes_and_always_goes_away`, `test_capture_diff_is_none_after_a_raising_block_whose_error_propagates`, `test_repository_with_no_commit_refuses_in_worktree_but_captures_diffs` | Feature | Committed, edited, untracked and ignored files. Possible faults: the worktree misses content or holds the ignored file; it lies inside the repository; writes leak back; it survives a normal exit or a raise; the exception is replaced; the real index or refs change; `capture.diff` is wrong; an unborn repository runs the block | Contents are compared byte for byte. The absence of the ignored file is paired with the presence of the untracked one, so an empty folder fails. The exception is the same object (`is`). Registrations are counted from `git worktree list --porcelain` |
| AC-19 | chain → `test_long_answer_with_a_nul_is_shortened_to_fit_the_grok_step` | Feature | A 100,000-character answer with a NUL is passed into Grok. Possible faults: `configuration.invalid_argument`; the NUL is sent; the caller's prompt is cut; the note is missing or its count is wrong; the room is wasted | The record must keep the raw NUL, so an answer scrubbed in the record fails. The kept prefix is at least 12,000 characters and the prompt is within 100 of the cap. On win32 the units are checked too |
| AC-20 | ensemble → `test_ten_proposers_narrow_in_one_round_with_repairs_for_bad_answers`, `test_no_successful_proposal_stops_before_the_selector_but_the_backstop_runs` | Feature | Ten proposers; a wrong role count; unoffered kept or selected numbers; every proposer failing. Possible faults: no round, or a wrong target; the final turn offers unkept numbers; a repair is skipped or goes to a new thread; the selector or implementer starts after all proposals failed; the backstop is skipped | One fork step answers by the identity in its prompt, so a proposer that saw another role returns the wrong proposal. The repair prompts must hold the fixed chunks of the problem constants. The backstop `write-tree` follows the last proposer exit |
| AC-21 | prompts → `test_each_prompt_holds_exactly_its_bare_placeholders` (22), `test_each_prompt_loads_as_a_package_resource` (22), `test_ported_prompt_drops_its_own_output_contract_and_sandbox_wording` (10), `test_every_fixed_combination_leaves_half_the_argv_room`, `test_pyproject_ships_the_prompt_files`, `test_compose_prompt_fields_covers_every_prompt`, plus `test_prompt_folder_holds_exactly_the_22_markdown_files` | Static | A prompt file with an unexpected, missing, formatted or converted placeholder, a CLI contract text, a sandbox claim, a combination over 12,000 characters, no package-data entry, or a prompt with no `COMPOSE_PROMPT_FIELDS` entry | The field sets and the forbidden texts are written out from §9.2 and AC-21, not read from compose. The wheel install itself is left to the package stage (see below) |
| AC-22 | surface → `test_compose_exports_exactly_the_42_names_as_the_lib_objects`, `test_lib_packages_export_the_new_enums_error_and_decoder`, `test_compose_and_new_lib_modules_respect_the_layers`; base `test_harness_threads_static_policy.py` (unchanged, `rglob`) | Unit; Static | A missing or extra name; a re-export that is a copy rather than the lib object; an enum, the error or `JsonText` not exported; an import of hostkit, `vidbyte.tools`, `vidbyte.prompts` or the root package | The 42 names are a literal set in the test, and identity is checked with `is` against `vidbyte.lib`. The layering is read with `ast` |
| AC-23 | none (the gate) | — | — | S3/S5 run lint, both `run_ci.py` stages and semgrep |
| INV-1 | surface → the two AC-22 tests, `test_each_function_has_its_kind_and_exact_parameters` (10), `test_importing_compose_starts_no_process_reads_no_file_and_touches_no_folder` | Unit | A composite that is not a coroutine function; a binder that is async; `capture_diff` not returning an async context manager; an import that starts a process or reads a prompt file | The parameters are written out from §8.5. The import probe runs in a fresh `-B` interpreter, with spies on `subprocess`, `open` and folder creation |
| INV-2 | binding → `test_each_binder_accepts_exactly_its_six_functions` (3), `test_bound_step_stores_resolved_checked_values_and_hides_its_key`, `test_bad_argument_fails_at_binding_naming_it` (12), `test_direct_calls_run_the_bound_function_once_in_its_verbs_order`, `test_unanchored_fork_refuses_a_direct_call_and_errors_pass_through_unchanged` | Unit; Feature | Each binder must accept exactly six functions; a stranger, a partial or a lambda must be refused; an argument is checked late; the default config is wrong; the key shows in the `repr`; the call count or order is wrong | Every one of the nine functions is tried with both binders. The stand-in logs show exactly one launch per call, with the bound key's digest |
| INV-3 | binding → `test_step_without_invoker_refuses_direct_calls_yet_runs_in_a_composite`, `test_composite_never_calls_a_replaced_invoker`; validation cases "bare function in steps", "partial in steps", "key string in steps", "step of an unknown function", "string to parse_json_answer" | Unit; Feature | A composite calls a step's stored invoker, or accepts something that is not one of the nine | The replaced invoker records its calls. Its list must stay `["Direct."]` after the composite, and the stand-in must show the composite's launch |
| INV-4 | keys → the four AC-15 tests; binding → `test_bound_step_stores_resolved_checked_values_and_hides_its_key` | Feature | See AC-15 | See AC-15 |
| INV-5 | validation → the AC-14 test | Feature | See AC-14 | See AC-14 |
| INV-6 | git → the AC-13 tests and `test_nested_repository_without_a_commit_fails_the_snapshot_naming_add`; chain → `test_failed_middle_step_ends_the_chain_with_the_functions_own_error` (no git without `{diff}`) | Feature | Git is used when it is not needed, or not used when it is needed; a git failure is not a `ThreadComposeError` with the INV-6 message order; the record so far is missing | `check_compose_error` checks `likely_cause` and `next_step` verbatim against their constants, and the message parts in order |
| INV-7 | workspace → AC-17 test; git → `test_every_git_child_is_the_spec_command_in_the_spec_place_with_a_clean_environment`, `test_unborn_repository_allows_grok_readers_and_refuses_worktree_readers` | Feature | A snapshot built with the real index, from `HEAD` alone, without untracked files, or with `read-tree HEAD` in an unborn repository | The read-tree and diff tree ids must equal the oracle's trees, which compose never computed |
| INV-8 | workspace → AC-17 test; chain → AC-2 test | Feature | A diff with paths relative to a subfolder, a rename pair, a wrong cut, or text that is not git's | Exact equality with the oracle's `diff --no-color --no-ext-diff --no-textconv --no-renames` |
| INV-9 | verify → AC-3 and AC-8b tests; workspace → AC-18 and EC-74 tests; ensemble → AC-6 test; git → hygiene test (subfolder) | Feature | A worktree reader in place, a worktree inside the repository, a shared worktree, or a missing subfolder | The paths are compared after `resolve` and `normcase`, and the subfolder is `worktree/pkg` |
| INV-10 | verify → AC-3 test; ensemble → AC-6 test; validation cases "grok verifier with accept edits", "grok verifier with dont ask", "grok proposer with accept edits", "selector with accept edits" | Feature | A Grok reader relocated, or allowed with `ACCEPT_EDITS`/`DONT_ASK` | The argv flag and the cwd are read from the stand-in logs |
| INV-11 | verify → AC-8a test; ensemble → AC-8c and EC-51 tests | Feature | The backstop is missing, early, or skipped after an early stop | Its position is read from the spy against the readers' exits |
| INV-12 | chain → AC-2 test (no overlap); verify → AC-3 test (the writer alone, first); ensemble → AC-6 test (implementer last) | Feature | Two writers at once | Spy enter/exit positions |
| INV-13 | concurrency → both AC-11 tests; AC-10 test (lock freed) | Feature | See AC-11 | See AC-11 |
| INV-14 | concurrency → AC-10 test; verify → `test_failed_verifier_stops_no_sibling_and_one_verdict_can_agree` | Feature | A cancel does not reach both verifiers, or a failed verifier cancels its sibling | The sibling's verdict must be present and parsed |
| INV-15 | chain → AC-7; handoff → `test_failed_summary_never_starts_the_target_and_a_failed_target_is_step_one`; verify → EC-18 and EC-52 tests | Feature | A composite raises for a step failure instead of returning its record | Each test awaits the composite without `pytest.raises` and reads the error from the record |
| INV-16 | chain → AC-7; verify → EC-52; handoff → EC-64; ensemble → EC-51; stages → AC-12 (stage 2 empty) | Feature | A later step starts after a failure | The later step's label is absent from both the log and the spy |
| INV-17 | chain → AC-2, AC-7; handoff → AC-4; stages → AC-5 | Feature | A value is parsed as a template, or a placeholder is filled wrongly | The answers and summaries hold `{x}` and `{{y}}` |
| INV-18 | chain → AC-19 test, `test_quote_dense_answer_is_shortened_by_command_line_units_as_well`; ensemble → `test_ten_long_proposals_share_a_grok_selectors_room_fairly`; validation → the four "too long" cases | Feature | A prompt over the cap; a value sent blank or cut unfairly; a note missing; units ignored on win32; a too-long caller prompt not refused up front | The kept prefixes must be equal across ten proposals and at least 500 characters each. The prompt must be within 200 of its binding cap. The note's omitted count is recomputed by the test |
| INV-19 | answers → AC-9, AC-16, `test_parse_json_answer_never_passes_a_cut_answer_to_parse`, `test_parse_json_answer_repairs_deep_nesting_and_parse_errors_but_not_a_defect`, `test_json_text_accepts_one_object_with_whitespace_or_one_fence` (4), `test_json_text_refuses_everything_else_with_value_error` (16) | Unit; Feature | A cut answer reaches `parse`; a writable mapping; a fallback parse of prose; a `RecursionError`; a repair after a defect | `ParseSpy` records each mapping and whether it was read-only. The defect is the same object |
| INV-20 | prompts → `test_prompt_folder_holds_exactly_the_22_markdown_files` and the placeholder tests | Static | An extra or missing file (a README the wheel would refuse) | An exact sorted listing |
| INV-21 | stages → AC-12; surface → `test_no_compose_module_sleeps` | Feature; Static | Attempts beyond the budget, a reused thread, or a sleep | See AC-12. The `ast` scan covers every compose module |
| INV-22 | stages → AC-5, AC-12 (sleep spy); surface → `test_no_compose_module_sleeps` | Feature; Static | A sleep, a backoff or a second timeout | Sleeps are counted only from compose files |
| INV-23 | ensemble → AC-6, AC-20, `test_ten_long_proposals_share_a_grok_selectors_room_fairly` | Feature | A wrong stage order, target or offered set | See AC-6, AC-20 |
| INV-24 | surface → alias signatures (9); validation → `test_alias_keyword_mistakes_raise_type_error_before_anything_runs` | Unit; Feature | A hand-written alias, a missing bind, a misspelled keyword ignored | The spy and the log must stay empty |
| INV-25 | verify → AC-3 (False), AC-8b (True), EC-18 (False), EC-63 (True), EC-52 (False) | Feature | `agreement` computed other than "at least one verdict, all parsed, all equal" | Both truth values appear across the cases |
| INV-26 | git → `test_every_git_child_is_the_spec_command_in_the_spec_place_with_a_clean_environment` | Feature | A git argv outside §9.2; the wrong cwd; a location variable passed through; an overlay other than `GIT_INDEX_FILE`; a caret; a caller value or model text in an argv; a key; a decoy repository or the real index touched | Every child seen by the spy is classified. The test requires that all eleven kinds occurred, so a run that skipped the checks fails |
| INV-27 | surface → `test_existing_public_surfaces_are_unchanged`, `test_import_vidbyte_loads_neither_native_nor_compose`; base surface test | Unit | `native.__all__` changes, or `import vidbyte` loads compose | The 17 names are written out |
| INV-28 | binding → `test_composite_step_starts_exactly_the_process_a_direct_call_starts` (3) | Feature | A composite changes the argv, cwd, stdin or environment, or uses another Grok home | A direct call and a composite call with the same arguments are compared field by field |
| INV-29 | chain → AC-7; binding → `test_unanchored_fork_refuses_a_direct_call_and_errors_pass_through_unchanged` | Feature | A recorded error is a copy | Traceback origin |
| INV-30 | concurrency → AC-10; stages → AC-12 `timed_out` | Feature | A process survives a cancel or a timeout | `alive(pid)` for the four pids |
| INV-31 | binding → INV-28 test; ensemble → AC-6 (one Grok home) | Feature | Compose creates a Grok home of its own | The listing of `~/.vidbyte/grok-homes` |
| INV-32 | surface → layering test; base static-policy test | Static | See AC-22 | See AC-22 |
| INV-33 | surface → `test_existing_public_surfaces_are_unchanged`, `test_vocabularies_are_exactly_the_spec_members`, `test_contract_constants_hold_the_spec_values`; base surface test (unchanged) | Unit | A pinned vocabulary gains a member, or the process package changes | Written-out tables |
| INV-34 | binding → INV-28 test (a direct call starts no git); base pack | Feature | One of the nine functions starts computing a diff | `runs.git_calls() == []` around direct calls |
| INV-35 | the base pack itself (436 passed, 2 skipped) | — | An existing test changed or broken | Run unmodified at S2; only `.get` fields were added to the stand-in |
| INV-36 | validation → `test_command_line_units_is_the_count_require_command_line_units_enforces` (7) | Unit | `command_line_units` counts characters or skips the quoting, or `require_command_line_units` changes its result or error | The expected counts are worked out by hand from the Windows quoting rule. The same record is accepted at the count and refused one below it, with the old message verbatim |
| EC-1, EC-2, EC-3 | git → the AC-13 tests | Feature | See AC-13 | See AC-13 |
| EC-4, EC-73 | git → `test_nested_repository_without_a_commit_fails_the_snapshot_naming_add` | Feature | A writer leaves `nested/.git` with no commit. Possible faults: `--ignore-errors` is used; the failure is reported as something else; the add texts are missing; a verifier starts; the index folder is left | git's own text is required. The two `add` cause texts come from the constants. A control at S2 showed `add -A` exits 128 on this host |
| EC-5 | git → `test_unborn_repository_allows_grok_readers_and_refuses_worktree_readers`; workspace → `test_repository_with_no_commit_refuses_in_worktree_but_captures_diffs` | Feature | An unborn `HEAD` breaks snapshots, or a worktree reader is refused only after the writer ran | Launch counts are taken before and after the refusal |
| EC-6, EC-7 | workspace → AC-17 test | Feature | See AC-17 | See AC-17 |
| EC-10 | git → hygiene test (workspace `pkg/`); workspace → EC-74 test | Feature | Paths relative to the subfolder, or a reader placed at the worktree root | `pkg/new.py` and `worktree/pkg` |
| EC-17 | concurrency → AC-10 test | Feature | A worktree left after a cancel | `worktrees() == 1`, and the leftovers are empty |
| EC-18, EC-63 | verify → `test_failed_verifier_stops_no_sibling_and_one_verdict_can_agree` | Feature | A failed verifier cancels its sibling or gets a repair turn; a single verdict does not count as agreement | The turn count is 1 for the failed verifier |
| EC-20, EC-22 | concurrency → the AC-11 tests | Feature | See AC-11 | See AC-11 |
| EC-23 | ensemble → `test_ten_long_proposals_share_a_grok_selectors_room_fairly` | Feature | Ten proposals of 100,000 characters each. Possible faults: first come, first served cutting; a proposal reduced to its note alone; role names cut; a prompt over the cap; two kept proposals cut as hard as ten | The prefix lengths must be equal, at least 500, and more than double that with two kept. Each note's count is recomputed. A self-check at S2 showed the stand-in returns all 100,000 characters |
| EC-24 to EC-33 | answers → AC-9, AC-16, `parse_json_answer` and `JsonText` tests | Unit; Feature | See AC-9, AC-16, INV-19 | See INV-19 |
| EC-34, EC-37 | chain → AC-19 test | Feature | See AC-19 | See AC-19 |
| EC-35 | validation → "prompt too long for a grok planner/verifier/later grok step", "stage template too long for grok" | Feature | A caller prompt that cannot fit beside the fixed files is accepted, then fails mid-run | Refused before any child starts |
| EC-36 | chain → `test_quote_dense_answer_is_shortened_by_command_line_units_as_well` | Feature | 100,000 double quotes are passed into Grok. A cut by characters only gives about 47,000 units on win32, so the step fails with `configuration.invalid_argument` | At S2 the base was shown to refuse a 30,000-plus-unit Grok prompt and to accept a 29,820-unit one. The test requires the step to succeed, the units to fall within 200 of the ceiling, and the note to follow |
| EC-39 to EC-48, EC-62, EC-76 | validation → the matching named cases | Feature | See AC-14 | See AC-14 |
| EC-43, EC-44 | binding → the INV-2 tests | Unit; Feature | See INV-2 | See INV-2 |
| EC-49, EC-50 | ensemble → AC-20 ten-proposer test | Feature | See AC-20 | See AC-20 |
| EC-51 | ensemble → `test_no_successful_proposal_stops_before_the_selector_but_the_backstop_runs` | Feature | See AC-20 | See AC-20 |
| EC-52 | verify → `test_failed_writer_runs_no_verifier_but_keeps_its_diff` | Feature | A failed writer's edits are not diffed, or a verifier runs | The writer wrote `half.txt` before failing |
| EC-53, EC-54 | stages → AC-12 no-ladder case; `test_stage_decisions_are_the_spec_table` | Feature; Unit | An empty ladder moves the rung, or the decision table differs | The table is written out from §9.2 |
| EC-58 | git → hygiene test with decoy `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR` and `GIT_OBJECT_DIRECTORY` | Feature | Snapshots of the decoy repository | The decoy's index, refs and status are unchanged |
| EC-59 | git → `test_hostile_diff_drivers_never_run_under_compose` | Feature | `diff.external` or a textconv driver runs under compose | The control runs both drivers with the test's own git first, and the test skips only if this git will not run them. At S2 both ran on win32 |
| EC-64 | handoff → EC-64 test | Feature | The target starts after the summary turn fails | `failed_step == 0`, and "never" is absent |
| EC-65 | git → hygiene test (no caret, no caller text) | Feature | A caret or caller text in a git argv | Every argv word is checked |
| EC-69 | ensemble → AC-20 ten-proposer test (one fork step used as all ten proposers) | Feature | Reused steps are deduplicated or share one call | Ten launches with ten distinct `reply` indexes |
| EC-70 | ensemble → AC-8c test | Feature | A round with one proposer | `rounds == ()` and block 1 offered |
| EC-71 | keys → the chain and errors tests | Feature | The records are scrubbed | The raw keys are required in `text`/`diff` |
| EC-74 | workspace → `test_in_worktree_creates_an_empty_workspace_folder_no_snapshot_holds` | Feature | A reader is refused for a missing empty folder | The folder exists, is empty and sits at `pkg/empty` beside the worktree's `README.md` |
| EC-77 | validation → alias keyword test | Feature | A misspelled keyword is ignored or raises `KeyError` | The missing and unexpected names are both required in the `TypeError` |
| EC-78 | binding → the two invoker tests | Unit; Feature | See INV-3 | See INV-3 |
| T-1 | verify → AC-8a, AC-8b; ensemble → AC-8c; validation → the Grok reader-mode cases | Feature | A reader's write is accepted, or a writable Grok reader is bound | See those rows |
| T-2 | its controls: INV-9 to INV-11, INV-17 and T-5 rows | Feature | Injected text that is parsed as a template, or a reader able to write | The residual (a model's opinion steered by injected text) is an accepted limitation |
| T-3 | keys → the four AC-15 tests; git → hygiene test (key not in git argv or environment) | Feature | See AC-15 | See AC-15 |
| T-4 | none (N/A: no other tenant); the lock table is exercised by the AC-11 tests | — | — | — |
| T-5 | answers → deep nesting (EC-33), cut answers (AC-9), extra member (EC-27), `test_records_refuse_a_value_past_their_bound_naming_the_field` (25) | Unit; Feature | A JSON bomb crashes a composite; a cut answer is graded; an oversized answer becomes a record | Every bound is tried past and at the limit |
| T-6 | git → `test_hostile_diff_drivers_never_run_under_compose`; hygiene test (`-c core.fsmonitor=false -c core.safecrlf=false` and `--no-optional-locks` on every child) | Feature | A planted driver runs, or a `-c` setting is missing | See EC-59. The argv prefix is compared exactly |
| T-7 | verify → AC-3 and ensemble → AC-6 (worktrees under the sandbox temporary folder, outside the workspace); INV-31 rows | Feature | A worktree inside a Grok home or the repository | See INV-9 |
| T-8 | git → hygiene test | Feature | Caller text or a caret in a git argv | See INV-26 |
| NFR-2 | surface → function kinds test; stages → sleep spy | Unit | A sync wrapper, or a blocking sleep | See INV-1, INV-22 |
| NFR-3 | surface → layering test | Static | See AC-22 | See AC-22 |
| NFR-5 | base static-policy test | Static | A compose module breaks base INV-15 | It runs unmodified over `rglob` |
| NFR-6 | the whole pack (sandbox removes the vendor credential variables; stand-ins only) | — | A developer's real key reaches a stand-in | The `sandbox` fixture deletes `XAI_API_KEY`, `GROK_CODE_XAI_API_KEY`, `META_API_KEY`, `DEEPSEEK_API_KEY`, `ZAI_API_KEY`, `ZHIPU_API_KEY` and `OPENCODE_CONFIG_CONTENT` |
| NFR-7 | surface → `test_thread_compose_error_carries_the_a003_packet`; every `check_compose_error` call | Unit; Feature | An empty `likely_cause` or `next_step`, a missing A003 field, or the diff or result inside `details` | `details` must hold exactly the eight A003 fields of `DIAGNOSTIC_FIELDS`, and `likely_cause` and `next_step` are compared verbatim with their constants |
| NFR-8 | answers → `test_records_refuse_a_value_past_their_bound_naming_the_field` (25); validation → the count cases and "five ladder configs"; workspace → diff caps | Unit; Feature | A record accepts 51 findings, an 11-role plan, a duplicate or zero kept number, an 11th proposal, a 65-character or NUL role name, 2,001 diff files, 4 turns, an over-cap problem, or an outcome with both or neither of result and error | Each case also builds the same record at the bound, so a record that refuses everything fails |
| NFR-11 | prompts → `test_every_fixed_combination_leaves_half_the_argv_room` | Static | A combination over 12,000 characters | The counted numbers are at their largest, and the note holds `sys.maxsize` |

## Tests deliberately NOT written

| Candidate | Why |
|---|---|
| EC-16: a worktree that cannot be removed | It needs a file held open past the block on win32, or a read-only folder on POSIX, and a deliberately undeletable folder in the shared temporary folder is a flake and cleanup risk on CI. INV-9's removal is pinned after both a normal exit and a raise, on both platforms |
| EC-19: a fan-out child raising something other than `NativeThreadError` | No seam the repo mocks can make exactly one child raise a defect: the nine functions raise only `NativeThreadError`, and failing one sibling's worktree needs a git hook (T-6 accepts hooks). Mocking compose's own fan-out would test the mock |
| EC-54 behaviour (`configuration.invalid_argument` or `runtime.error` from a stage) | No valid stage can produce either code: compose refuses a prompt the step would refuse before any I/O (INV-18, INV-29). The rule is pinned as data: `STAGE_UNCLASSIFIED_DECISION == ABORT` and the full table |
| T-6: a `core.fsmonitor` hook and `core.safecrlf=true` run behaviourally | The hygiene test checks the exact `-c core.fsmonitor=false -c core.safecrlf=false` prefix on every git child. Whether a hook runs depends on git's index refresh path, which varies by version |
| EC-4: a git command passing `COMPOSE_GIT_TIMEOUT_SECONDS` after a step ran | The real git cannot be made slow at exactly that call, and lowering the constant times out the first `rev-parse` instead. EC-73 pins the `GIT_FAILED` shape and the record so far |
| EC-60: dubious ownership | It needs a repository owned by another OS user |
| EC-72: a writer that commits, switches branch or stashes | The stand-in runs no git. Content-based snapshots are pinned by AC-17, and a ref-based diff would be an unlisted command in the INV-26 classification |
| EC-55, EC-56: Muse in WSL inside a worktree, and a UNC temporary folder | They need WSL or a UNC temporary folder; both are accepted limitations |
| EC-57: continuing a reader's thread later | The stand-in keeps opencode and Muse threads in one state folder (spec §13 fact 5); this is an accepted limitation |
| EC-9, EC-66: huge files and 100,000-file repositories | Time budgets; accepted limitations |
| The other accepted limitations: EC-8, EC-11 to EC-15, EC-21, EC-38, EC-61, EC-67, EC-68, EC-75, and the T-2 and T-3 residuals | They have no control in this PR to test |
| AC-21: loading the prompts from an installed wheel | It needs a built wheel. Lint C015 (source stage) proves statically that the tracked files ship, and the package stage builds the wheel, so this part is left to S3/S5. The static parts are proven here |
| AC-23, NFR-1, NFR-4, NFR-9, NFR-10: lint, both `run_ci.py` stages, semgrep, file sizes, no new dependency, and the CI matrix | These are gate runs, not tests. They belong to S3/S5 and CI |
| INV-36 second bullet: the seven JSON sites and the four `Formatter().parse` sites stay unedited | This is a diff property, checked in review |
| EC-69 writer-and-verifier variant | The ten-proposer test already reuses one step object ten times. The verifier copy comes from `dataclasses.replace` on a frozen record, so it cannot change the writer's step |
| Q-1 to Q-11 | Not requested |

## Red run (before implementation)

Bootstrap: none. `python` on this host is `C:\Users\422mi\AppData\Local\Programs\Python\Python311\python.exe` (3.11.0), the same interpreter as `py -3.11`, with pytest 8.3.5 and pytest-asyncio 1.3.0 already installed. There was no install and no network. `PYTHONPATH=$(pwd)` makes the worktree's `vidbyte` importable. Every run below was made from the worktree root on HEAD `36fc0308` (the orchestrator's commits on this branch touch only `pipeline.md`), with the pack staged and `vidbyte/harnesses/native/compose/` absent.

`PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose` → exit 1, last lines:

```text
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_capture_diff_is_none_after_a_raising_block_whose_error_propagates
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_in_worktree_holds_the_working_content_isolates_writes_and_always_goes_away
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_in_worktree_creates_an_empty_workspace_folder_no_snapshot_holds
ERROR tests/features/harness_compose/test_harness_compose_workspace.py::test_repository_with_no_commit_refuses_in_worktree_but_captures_diffs
276 errors in 9.47s
```

The same command with `--tb=line` prints 276 `E` lines, every one `ModuleNotFoundError: No module named 'vidbyte.harnesses.native.compose'`, and ends `276 errors in 2.10s`. Every case fails at fixture setup for that one reason, because the `compose_api` fixture imports compose before anything else; no case can pass, skip or fail for another reason before the feature exists.

`PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_compose/<file>.py`, one run per file:

| File | Final line | Exit | Errors caused by the missing module (`--tb=line`) |
|---|---|---|---|
| `test_harness_compose_acceptance.py` | `1 error in 1.20s` | 1 | 1 of 1 |
| `test_harness_compose_answers.py` | `49 errors in 2.32s` | 1 | 49 of 49 |
| `test_harness_compose_binding.py` | `23 errors in 1.60s` | 1 | 23 of 23 |
| `test_harness_compose_chain.py` | `4 errors in 1.10s` | 1 | 4 of 4 |
| `test_harness_compose_concurrency.py` | `3 errors in 1.13s` | 1 | 3 of 3 |
| `test_harness_compose_ensemble.py` | `5 errors in 1.23s` | 1 | 5 of 5 |
| `test_harness_compose_git.py` | `16 errors in 1.44s` | 1 | 16 of 16 |
| `test_harness_compose_handoff.py` | `2 errors in 1.08s` | 1 | 2 of 2 |
| `test_harness_compose_keys.py` | `4 errors in 1.08s` | 1 | 4 of 4 |
| `test_harness_compose_prompts.py` | `58 errors in 2.38s` | 1 | 58 of 58 |
| `test_harness_compose_stages.py` | `6 errors in 1.22s` | 1 | 6 of 6 |
| `test_harness_compose_surface.py` | `29 errors in 1.93s` | 1 | 29 of 29 |
| `test_harness_compose_validation.py` | `66 errors in 2.89s` | 1 | 66 of 66 |
| `test_harness_compose_verify.py` | `5 errors in 1.20s` | 1 | 5 of 5 |
| `test_harness_compose_workspace.py` | `5 errors in 1.21s` | 1 | 5 of 5 |

Base pack (`-rs` only adds the skip reasons): `PYTHONPATH=$(pwd) python -m pytest -q tests/features/harness_threads -rs` → exit 0, last lines:

```text
SKIPPED [1] tests\features\harness_threads\test_harness_threads_launcher.py:100: Muse is looked up on PATH only outside win32 (EC-29)
SKIPPED [1] tests\features\harness_threads\test_harness_threads_runner.py:245: the execute permission bit exists only on POSIX
436 passed, 2 skipped in 47.53s
```

These are the base pack's 438 tests, unmodified, run with the extended stand-in. The two skips are platform skips in base tests this pack does not touch.

Lint: `python lint/run.py` → exit 0, last lines:

```text
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

No baseline was touched. The `IMPROVED` notices lint prints (for example `S063 IMPROVED 4 -> 3`) were already there before this pack.

Self-checks of the test design, run in throwaway files that were deleted and never committed:

- With the test's own git, the planted `diff.external` and textconv drivers both run, so EC-59's skip guard does not fire on win32.
- `add -A` with a nested `.git` that has no commit exits 128 with "does not have a commit checked out".
- `worktree add` in an unborn repository exits 128.
- The oracle's diff under `core.autocrlf=true` holds no carriage return.
- An empty subfolder is in no snapshot.
- A Grok stand-in returns a whole 100,000-character reply through `replies`, with `text_truncated` false.
- The opencode stand-in returns 100,000 double quotes whole, with `text_truncated` false.
- On win32 the base accepts a Grok prompt of 29,820 command-line units and refuses one of 30,220 units with `configuration.invalid_argument`.
- The INV-36 test fails a characters-only counter (5 of its 7 cases) and an unquoted UTF-16 counter (4 of 7), and passes the correct one.
- The AC-1 `SNIPPET` equals the one python block of spec §4 character for character (1,565 characters; re-checked at the end of S2 against r3).

## Notes for the implementer

- **Seams the tests depend on.** Each step runs through its config's `grok_command`/`opencode_command`/`muse_command`. Every git child goes through `CliRunner.run`, which the `runs` fixture wraps to record argv, cwd, `env_overlay`, `env_remove`, `stdin_text`, `timeout_seconds` and `max_output_bytes`. Build git children with those `CliInvocation` fields, and do not run git through any other path.
- **Constants are read at call time.** The tests lower `COMPOSE_DIFF_MAX_CHARS` and `COMPOSE_DIFF_MAX_FILES` on `vidbyte.lib.constants.native_compose`, and `NATIVE_RESULT_TEXT_MAX_CHARS` on the base constants module, with `monkeypatch.setattr` (spec §8.5, §13). Read them as module attributes, never with `from … import NAME` into compose.
- **Folders come from `tempfile`.** The sandbox sets `tempfile.tempdir` and `TMP`/`TEMP`/`TMPDIR` to `<root>/tmp`. Leftovers are counted there, and worktree and index folders must start with `COMPOSE_WORKTREE_PREFIX`/`COMPOSE_INDEX_PREFIX`. The temporary index file is named `index` inside its prefixed folder.
- **Interpretations the tests encode** (the spec allows these readings; change a test only if the spec changes):
  1. The truncation note's omitted count is measured after NUL removal.
  2. A cut diff is the exact prefix `text[:cap]`, and a cut file list is `files[:cap]`.
  3. `WorkspaceDiff.text` is git's raw output for the §9.2 command.
  4. The problem constants follow their names: `COMPOSE_TRUNCATED_PROBLEM` for a cut answer, `COMPOSE_ROLE_COUNT_PROBLEM`, `COMPOSE_KEPT_PROBLEM` and `COMPOSE_PROPOSAL_PROBLEM`. An extra member's problem names the member.
  5. An unanchored fork passed as `to_step` is refused naming `to_step`.
  6. Every git child's overlay is a subset of `{GIT_INDEX_FILE}`, and `rev-parse` runs with the workspace as its cwd.
  7. `likely_cause` and `next_step` are their constants verbatim. The `add` failure appends both cause texts.
  8. `ThreadVerdict.findings` and `EnsembleRound.kept` are tuples.
  9. A `JsonText` problem text contains `str(ValueError)` from `JsonText.decode`.
  10. In `run_ensemble` the selection runs before the backstop (INV-23 order), and no snapshot is taken after the implementer (NG-13).
  11. A refusal of "exactly one of `result`/`error`" names `StepOutcome.result` or `StepOutcome.error`.
- **Spec defect: D-5 asks for `asyncio.Lock`.** D-5 and §12.3 row 12 prescribe one `asyncio.Lock` per (loop, workspace) in `GrokWorkspaceLocks`. `lint/ruff.toml` bans `asyncio.Lock` (TID251, "Use the SDK-owned concurrency boundary."), and S039 is at its allowance (5 of 5). A new `asyncio.Lock` therefore fails `SDK-LINT`, and AC-23 forbids raising the baseline. `asyncio.Semaphore(1)` is not banned and is used across the SDK. The tests check only the behaviour (no overlap within a workspace, overlap across workspaces, freed after a cancel), so either primitive passes them.
- **Prompt rendering.** The tests render prompt files with `str.format_map` and strip the result. Spliced values must appear in the prompt exactly as rendered: no extra escaping, and no whitespace changes inside a value. The truncation note follows the kept prefix, and any whitespace between them is allowed.
- **Do not change** the stand-in's existing behaviour, the base pack, or any assertion here. If a test seems wrong, raise it against the spec first.
