# S2 test author (amendment): harness-thread-helpers-skills

STATUS: DONE · Spec r5 · Findings `reports/S4-findings-verifier.md` (R-2 to R-6, R-16, R-23) · Branch `feat/harness-thread-helpers-skills` · base `b35d9276`

## Commits
| SHA | Message | Paths |
|---|---|---|
| `228b2a9e` | `test(harness-threads): make the sandbox fixture hermetic [R-4]` | `tests/features/harness_threads/conftest.py` (the fixture and its loader), and the one-line ROLE IN CODEBASE fix in `fake_harness.py`'s header that the by-path load makes necessary |
| `2d61818e` | `test(harness-threads): add failing tests for S4 findings [R-2, R-3, R-5, R-6, R-16, R-23; AC-17, AC-34, AC-35]` | 6 test files, `fake_harness_helpers.py`, `FEATURE.md`, `README.md`, `test-plan.md` |
| this commit | `docs(spec): record amendment test proof for harness-thread-helpers-skills` | `spec.md` (only the §6.2 Proof cells of AC-17, AC-34 and AC-35) and this report |

Nothing under `vidbyte/`, `lint/` or `scripts/` was touched; `lint/baseline.json` is unchanged. No push.

## Inventory
10 new test functions (30 cases) and 4 granted edits. 29 new cases are red; the 1 green one is a deliberate guard. The granted edits b and c turn 5 existing cases red.

| Finding | File → test | Cases | Today |
|---|---|---|---|
| R-4 | `conftest.py` → `sandbox` (edit a) | fixture | area 998 passed with and without the key (was 16 failed with it) |
| R-23 (AC-17, EC-82) | muse_commands.py → `test_a_read_skill_call_counts_only_when_its_parsed_id_is_the_skill` | 6 | red |
| R-23 guard | muse_commands.py → `test_a_read_skill_call_with_more_arguments_still_counts` | 1 | red (missing constant only) |
| R-2 (AC-34, EC-79) | muse_commands.py → `test_after_compaction_the_evidence_is_the_anchored_snapshots_tool_call` (edit d) | 2 | red |
| R-2 (AC-34, EC-83, EC-84) | muse_commands.py → `test_after_compaction_text_or_a_call_outside_the_fold_is_command_not_run` (edit d) | 5 | red |
| R-2 guard (D-33) | muse_commands.py → `test_an_unknown_history_mode_is_protocol_mismatch_naming_items` | 1 | green |
| R-2 (§12.4 r5) | helper_surface.py → `test_the_muse_command_not_run_cause_is_the_r5_text` | 1 | red |
| R-5 (AC-35, EC-85) | grok_commands.py → `test_a_malformed_own_summary_after_the_run_keeps_the_minted_id` | 2 | red |
| R-5 (AC-35, EC-85) | muse_commands.py → `test_an_evidence_folder_failure_after_the_run_carries_the_new_thread` | 2 | red |
| R-6 (D-35) | errors.py → `test_child_problem_maps_one_finished_child_in_the_d35_order` | 8 | red |
| R-3 (INV-7) | listing_properties.py → `draw_store` (edit b) → `test_search_matches_the_literal_case_insensitive_oracle` | seeds 1, 2, 3, 6 of 10 | red |
| R-3 (INV-7) | listing_properties.py → `test_search_never_matches_the_older_copy_of_a_duplicated_id` | 2 | red |
| R-16 (§12.4) | helper_surface.py → `test_new_and_widened_texts_name_what_the_spec_requires` (edit c) | 1 | red |

Withdrawn by edit d: `test_after_compaction_the_evidence_comes_from_the_export_transcript[plan, goal]` and `test_after_compaction_a_transcript_without_the_call_is_command_not_run_naming_compaction`. Their before and after are in test-plan.md, "Granted edits".

## Red run
Run with `"$PY" -m pytest -q -p no:cacheprovider tests/features/harness_threads -rf`, first with `DEEPSEEK_API_KEY` set and then under `env -u DEEPSEEK_API_KEY`:
```
with the key:    34 failed, 991 passed, 3 skipped in 86.42s (0:01:26)
without the key: 34 failed, 991 passed, 3 skipped in 86.47s (0:01:26)
```
The sorted FAILED ids of the two runs are identical. These are the per-file runs, without the key:
```
muse_commands: 16 failed, 16 passed in 5.82s
grok_commands: 2 failed, 58 passed in 8.60s
errors: 8 failed, 37 passed in 2.23s
listing_properties: 6 failed, 44 passed in 3.39s
helper_surface: 2 failed, 36 passed in 0.98s
muse_helpers: 23 passed in 3.66s
```
Each failure (`--tb=line`) fails for the following reason:
- **R-23, 6 + 1 cases, and `plan-reads-another-skill`:** `AttributeError: module 'vidbyte.lib.constants.native_threads' has no attribute 'MUSE_READ_SKILL_ID_MEMBER'`.
- **R-2 anchored positives:** `AssertionError: D-33: no export runs for evidence`.
- **R-2 anchored negatives, 4 rows:** `Failed: DID NOT RAISE <class 'vidbyte.lib.errors.base.NativeThreadError'>`. Today the code finds the text in the export.
- **R-2 r5 cause:** `AssertionError: §12.4 r5: "... or the run compacted and its transcript lacks the call."`.
- **R-5, Grok and Muse:** `AssertionError: thread_id None != '<new id>'`. Each case reaches this line only after `check_error` has matched the code (`grok.protocol_mismatch`, `muse.launch_failed` or `runtime.error`).
- **R-6:** `AttributeError: child_problem`.
- **R-3:** `AssertionError: seed 1, query ' FL'` (and seeds 2, 3 and 6), and `AssertionError: INV-7: the older copy is not the thread`.
- **R-16:** `AssertionError: R-16 / §12.4: ... 'Run opencode --version and install the opencode release named in this message, then retry; when the message names the scan cap, narrow the list with list_opencode_threads_since or archive old sessions.'`.

## Independent checks (scratch only, never committed)
I made four checks, each with code that is neither the SDK nor the tests. The scripts and plugins are in `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/8ba228e7-1bc7-41fd-a637-c0f10b927957/scratchpad/s2amend/`.
- **`inject_member.py`.** This pytest plugin sets the missing constant `MUSE_READ_SKILL_ID_MEMBER = "id"` in memory. With it, the 6 R-23 shapes and the 4 text negatives of R-2, `plan-reads-another-skill` among them, fail with `DID NOT RAISE` on today's code. The extra-arguments guard passes. So once the constant exists, these tests catch the substring rule and the export text search themselves.
- **`inject_child_problem.py`.** This plugin installs a reference D-35 mapping, which passes all 8 cases. It also installs three mutants, and each one is caught:
  - checking the marker before the timeout and the cap fails 2 cases;
  - searching the outcome instead of `texts` fails 1;
  - mapping the marker on a clean exit fails 1.
  The plugin also confirms every row's `CliOutcome` premise on win32.
- **`buggy_oracle.py`.** This plugin models R-3 as filter every copy, then dedupe. The SDK equals that model on all 10 search seeds, so the 4 red seeds are R-3 and nothing else.
- **`check_standin.py`.** This script checks the stand-in's served history:
  - inline mode returns every item;
  - `anchoredSnapshot` mode has `items` null, every item plus a `compaction` item before the last answer, and an anchor;
  - `anchored_drop_tools` removes the call;
  - an unknown mode has `items` and `snapshot` both null.
  The export's top-level keys equal the sorted keys of the real Muse 1.0.1 export, `muse-shape-data/export.json`, exactly.

## Fixtures and stand-in switches added or changed
- **`conftest.py`:**
  - `load_fake_harness()` (cached) loads `fake_harness.py` by path for `CREDENTIAL_NAMES`;
  - `sandbox` clears each of those names.
- **`fake_harness_helpers.py`:**
  - `muse_read` anchoredSnapshot now models MSP: every item plus `compaction(summarizedThrough, trigger, outcome)`, `history.items` null, and `anchor {boundaryCursor, summarizedThrough}`;
  - new switch `anchored_drop_tools` (EC-84);
  - new `muse_export_document`, the real event-log members with no `items`, used for every unseeded export. A seeded `.export` is still exported byte for byte;
  - removed switch `export_drop_tools`. Only the two withdrawn tests used it.
- **Test helpers:**
  - muse_commands.py: `skill_call`, `read_skill_args`, `LIST_CALL`, `ANCHORED`, `GRILL`, `NOT_EVIDENCE` and `COMPACTED_WITHOUT_EVIDENCE`;
  - errors.py: `CHILD_SOURCE`, `CHILD_CASES`, `CHILD_CAP` and `CHILD_TIMEOUT`;
  - helper_surface.py: `SCAN_CAP_STEP` and `MUSE_COMPACTION_CAUSE`, both copied from §12.4 and each found exactly once by `grep -c` in both files.
- **Existing seams, used as before:**
  - Muse evidence-folder faults: `monkeypatch.setattr(tempfile, "mkdtemp", ...)`. Spec §13 and INV-12 name `mkdtemp`, and the repo already patches `Path.home` and `os.makedirs` the same way. The fault fires only after `sandbox.answers("muse-exec")` is non-empty.
  - D-35 outcomes: built with the real `CliRunner` over an inline child, as `test_harness_threads_runner.py` does.
  - Not mocked: `CliRunner`, asyncio subprocesses, `NativeErrorFactory` and the validators.

## Pruned, and why
- **R-1, R-10, R-11, R-15, R-17, R-21:** code-only, and **R-9, R-12 to R-14, R-18 to R-20, R-22:** not tested now. Both per the briefing.
- **The refuted items:** DEEPSEEK/ZAI enum members, deleting README:179, and the PWD enum.
- **Grok `runtime.error` after a paid run:** this needs a mock of `CliRunner` or `GrokStore`. The Muse `unexpected` row proves the same `_call` fallback of D-34.
- **S4 repro case B (the export `mkdir`):** obsolete, because r5 runs no export for evidence.
- **Structural rules:** `remember_thread` is called exactly twice, and the three `child_problem` call sites. These are a review matter (§12.4 checklist), and the existing helper-bound and not-found tests cover what those sites do.
- **A committed stand-in self-test:** it would be a green test of a test double, so I ran `check_standin.py` once instead.
- **A stderr-only cut on a clean exit in D-35:** the spec lists only a stdout cut. I left this case out rather than encode a rule the spec states only through "otherwise None".

## Spec text that made a test hard to write
- **AC-35 says "whatever the code".** `check_error` pins a code. So I pinned only codes that other spec text fixes:
  - `protocol_mismatch` naming the member (INV-6) for a malformed own `summary.json`;
  - `launch_failed` for the evidence child's private folder (§9.2 "After the paid run" and §13);
  - `runtime.error` naming the exception class for an unexpected `KeyError` (EC-32).
- **§13 names the compaction item's fields but not their values.** It names `summarizedThrough`, `trigger` and `outcome`; the stand-in uses `trigger: "auto"` and `outcome: "compacted"`. No test reads those two values.
- **The real export's tool-call event shape is unobserved (D-33).** The stand-in puts each item in an event payload of its own kind, `item_recorded`. That way the prompt and call text is in the file, which is what lets the text-search defect show, but no test reads the events.
- **AC-17 r4 binds to a constant that does not exist yet.** 9 cases therefore fail first with `AttributeError`. The behaviour-level red is shown under "Independent checks" above.
- **INV-7 names no winner when two copies have the same `updated_at`.** `draw_store` therefore keeps a tied copy's texts, so the oracle never has to choose between them.

## Open items
- None blocking. `lint/run.py` ends `SDK-LINT: PASS`. It also prints `S063 IMPROVED 4 -> 3` (gather-exceptions-classified, in `vidbyte/`). The base `b35d9276` prints the same line (checked in a temporary detached worktree, since removed), so it is not mine, and I left the baseline alone as instructed.
- After S5, all 34 should be green with nothing else changed. If the evidence folder stops coming from `tempfile.mkdtemp`, the two `test_an_evidence_folder_failure_*` cases will fail with `DID NOT RAISE` rather than pass vacuously.
