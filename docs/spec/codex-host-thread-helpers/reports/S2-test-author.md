# S2 test author report: codex-host-thread-helpers

Stage: S2 test author · Spec: `docs/spec/codex-host-thread-helpers/spec.md` r3 (approved) · Branch: `feat/codex-host`, started at `5a37caf1` · Date: 2026-10-16

## Outcome

- The tests fail now, and they fail only because the spec's names do not exist yet.
- Five new test files hold 76 tests: 20 run on CI, and 56 need the `codex` extra.
- 14 existing tests go red through the §13 pins, which were authorized and edited only where §13 says.
- The one inherited failure stays failing for its existing reason.
- Nothing under `vidbyte/` changed: `git diff --stat 5a37caf1 HEAD -- vidbyte/` is empty.
- No prototype is on the worktree's `sys.path`. The venv's only `.pth` entries are the editable finder for this worktree and the distutils shim, and `vidbyte.__file__` resolves to `<worktree>/vidbyte/__init__.py`.

Commits:

1. `aeeee55b` — `test(codex-host): add failing tests for codex-host-thread-helpers [AC-1..AC-43]`. It holds the tests, the fake and support extensions, the §13 pins, FEATURE.md, README.md and `test-plan.md`.
2. `50463bb6` — `docs(spec): record test proof for codex-host-thread-helpers`. It changes only the 43 Proof cells of §6.2.
3. This report.

## Inventory

| File | Tests | CI | What it proves |
|---|---|---|---|
| `tests/features/codex_host/test_codex_host_helper_surface.py` | 10 | runs | The 5 records: field order, frozen and slotted, validation, and `harness` fixed. `CodexSkillScope`. The 12 `CodexHostOperation` members in method order. The 4 codes between `CODEX_TURN_TIMED_OUT` and `INPUT_EMPTY`. The §9.3 constants and `__all__`. The §9.2 message and tool texts in their modules. The 12 host signatures and their order. |
| `tests/features/codex_host/test_codex_host_helper_tools.py` | 10 | runs | 26 tools and no delete tool. Schemas, permissions and types. Argument refusals before the host (28 rows). Default limits 20 and 3. `spawn_defaults`. The cap, ownership, and the slot released after a failure or a cancel. Error results with the new next steps. JSON and text outputs. |
| `tests/features/codex_host/test_codex_host_thread_helpers.py` | 29 | skipped | The listing walk: params, cursors, remaining limit, repeated cursor, page bound, since, search and bad arguments. The summary mapping. Lineage: depth, cycle, missing or refused ancestor, timeout. The turn listing: items, reasoning privacy, running, `notLoaded`. Compact: the goal check and the resume oracle. Delete. Busy and unknown. The reservation. |
| `tests/features/codex_host/test_codex_host_goal_skills.py` | 22 | skipped | `get_codex_goal` for every status. The goal run: its sequence, mismatch, check failure, cancel, completed goal, bad arguments and posture. The skill listing. The skill run: input, posture, duplicates, not-found and disabled, the 50-name bound, the docs run, bad arguments. The read-back: late input, never recorded, dropped, failed interrupt, failed read, cancel, deadline. |
| `tests/features/codex_host/test_codex_host_helper_lifecycle.py` | 5 | skipped | The §4 snippet (7 lines). The guards: before open, another loop, after close. No preflight, and no resume on reads. −32601 for each of the 5 methods. The privacy canaries. |

The failure inventory, one line per input + state → wrong output, is in `tests/features/codex_host/FEATURE.md` under "Known Failure Modes" ("The thread helpers add these"). The full AC/EC/INV coverage map, with the vacuity defense of each row, is in `docs/spec/codex-host-thread-helpers/test-plan.md`.

## Pruned or not written

Pruned during authoring:

- **A `"   "` skill-name row.** The spec says only "empty" for `SKILL_NAME_MESSAGE`, so a whitespace row would bind to behavior the spec does not state.
- **Substring name checks in the not-found message.** A skill path also contains the name, so a path leak could pass. They were replaced by regex tokens taken after the exact prefix.
- **A not-found prefix built with `format(names="")`.** It kept the trailing `.`, so the message's own end could satisfy it. It was replaced by a split at `{names}`, plus a separate `endswith(".")` check.
- **Coroutine tuples built before `await`.** They gave "never awaited" warnings and leaked when a subtest failed. They became lambdas.

Not written, with reasons: EC-49, EC-36, EC-24, the accepted ECs (19, 20, 21, 33, 41, 43, 44), NFR-2/7/8/9, R-7, Q-13/16/19, a tool-layer `limit` upper bound, property tests, and live runs. The test plan's "Tests deliberately NOT written" table gives each reason.

## Red output (exact)

Baseline at `5a37caf1`: `PYTHONPATH=$(pwd) <venv python> -m pytest -q tests/features/codex_host tests/features/harness_threads` → `1 failed, 551 passed, 2 skipped`.

After S2, from the worktree root:

```
test_codex_host_helper_surface.py   → 10 failed in 0.85s
test_codex_host_helper_tools.py     → 10 failed in 0.91s
test_codex_host_thread_helpers.py   → 29 failed in 1.88s
test_codex_host_goal_skills.py      → 22 failed in 1.75s
test_codex_host_helper_lifecycle.py → 5 failed in 1.21s
tests/features/codex_host tests/features/harness_threads → 91 failed, 537 passed, 2 skipped in 48.13s
```

The failures by file:

| File | Failed |
|---|---|
| `test_codex_host_goal_skills.py` | 22 |
| `test_codex_host_helper_lifecycle.py` | 5 |
| `test_codex_host_helper_surface.py` | 10 |
| `test_codex_host_helper_tools.py` | 10 |
| `test_codex_host_lifecycle.py` | 1 |
| `test_codex_host_packaging.py` | 3 |
| `test_codex_host_records.py` | 6 |
| `test_codex_host_thread_helpers.py` | 29 |
| `test_codex_host_tools.py` | 4 |
| `harness_threads/test_harness_threads_surface.py` | 1 (the inherited failure) |

The reasons of the 76 new failures, from `--tb=line` and grouped:

| Count | Reason |
|---|---|
| 10 | `AttributeError: 'CodexHost' object has no attribute 'run_codex_skill'` |
| 9 | the same for `list_recent_codex_threads` |
| 9 | the same for `compact_codex_thread` |
| 7 | the same for `run_codex_goal` |
| 5 | the same for `get_codex_thread_lineage` |
| 4 | the same for `list_codex_turns` |
| 2 each | the same for `search_codex_threads` and `list_codex_threads_since` |
| 1 each | the same for `run_codex_openai_docs`, `get_codex_goal` and `delete_codex_thread` |
| 1 | `type object 'CodexHost' has no attribute 'list_recent_codex_threads'` |
| 9 | `the toolset has no tool named …` |
| 3 | `module 'vidbyte.harnesses.native.codex' has no attribute 'skill_functions'` |
| 6 | `ImportError` for `CodexStoredTurn` (2), `CodexThreadSummary`, `CodexThreadGoal`, `CodexSkillInfo` and `CodexSkillScope` |
| 1 | `ModuleNotFoundError: No module named 'vidbyte.harnesses.native.codex.thread_helpers'` |
| 1 | `module 'vidbyte.lib.constants.codex' has no attribute 'CODEX_THREAD_COMPACT_METHOD'` |
| 4 | empty-vs-expected diffs: the operation order, the code order, the 12 host methods after `start_codex_review`, and the 26 tool names |

No failure comes from a fake handler, a timeout, or the test code's own `KeyError`.

The 14 red existing tests:

- `test_codex_host_lifecycle.py::CodexHostSnippetTests::test_the_section_4_snippet_prints_its_three_lines` gives `'15 check_codex_ready'` where `'26 …'` is expected.
- `test_codex_host_packaging.py`:
  - `test_imports_never_load_the_sdk_and_entering_reports_the_pip_extra` gives (15, …) where (26, …) is expected;
  - `test_existing_export_lists_gain_only_the_new_names_in_place` lacks `CodexSkillScope`;
  - `test_new_packages_export_exactly_their_spec_lists` lacks the 5 records.
- `test_codex_host_records.py`:
  - `test_valid_baselines_construct_frozen_slotted_records` and `test_each_invalid_record_raises_configuration_error_naming_the_field` hit `ImportError CodexStoredTurn` in `_valid_kwargs`;
  - `test_each_new_code_has_its_classification_row_and_next_step` gives `KeyError 'codex.command_not_run'`;
  - `test_new_failure_codes_sit_right_after_run_option_unsupported` gives a diff;
  - `test_new_enums_have_exactly_the_spec_members_and_values` gives a `CodexHostOperation` diff;
  - `test_wire_values_match_openai_codex` has no `CodexSkillScope`.
- `test_codex_host_tools.py`:
  - `test_toolset_holds_the_fifteen_tools_with_their_spec_schemas` gives 15 != 26;
  - `test_default_policy_allows_the_read_tools_and_denies_the_write_tools`, `test_every_tool_turns_host_errors_into_error_results` and `test_mcp_server_lists_and_runs_the_toolset` find no new tool.

Each is an authorized §13 pin or a direct consequence of one.

The inherited failure: `tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`, unchanged.

**CI without the extra.** With `openai_codex` hidden from every meta-path finder, the pack gives `32 failed, 24 passed, 136 skipped`. The 3 SDK files skip whole. The failures are the 20 CI-visible new tests plus 12 of the pinned tests. One packaging probe ran only because it starts a child interpreter that sees the SDK.

**Lint.** `PYTHONPATH=$(pwd) <venv python> lint/run.py`, with the files staged, gives `SDK-LINT: PASS`. The one S020 finding is `vidbyte/agents/multi/README.md:26`, which was already there. S062 has 0 hits in the pack.

## Proof the tests can pass, and that each can fail

These checks ran in the session scratchpad only, never under `vidbyte/`:

- **Green.** A spec-conforming scratch implementation passed the whole codex_host pack: `1 failed, 191 passed`. The one failure is `test_repo_map_section_sits_between_the_harnesses_paragraph_and_stores`, which fails because the scratch copy has no `REPO_MAP.md`.
- **Mutation.** 45 single-rule mutants of the prototype were run against the committed tests, byte-identical copies. All 45 were killed. One mutant, "no duplicate filter", had a stale pattern in the batch and was rerun with the real indentation; it was killed by `test_a_repeated_cursor_ends_the_walk_without_duplicates`. The mutants cover:
  - the listing rules: source kinds, since, remaining limit, cursor repeat, duplicates, page bound, limit bound, blank query;
  - lineage: cycle, depth, timeout;
  - the summary mapping: parent precedence, empty title;
  - the turns listing: host-side default limit, reasoning leak;
  - compact: goal check and its status gating, resume, reservation;
  - delete on an `active` thread;
  - the goal run: cancel, budget, unchecked suffix, cancel on cancellation;
  - the skill run: path, names cap, ephemeral, read-back presence, skill entry, deadline and attempts, miss interrupt, skills `cwd`, docs name;
  - the tools: turns default, cap, ownership, spawn defaults, compact text, since bool;
  - the guard, preflight, skill-listing operation, and path leak.
- **Determinism.** 6 back-to-back runs of the 76 new tests against the prototype gave `76 passed` every time, in about 5.26 s each. The tests use no sleeps, wall-clock checks or network. Holds and the one-worker barrier set the order, and every wait is bounded by `WAIT_SECONDS`. Paths are built with `os.path`, and text is compared after `splitlines()`.

## Fixtures added or extended

Every new switch defaults to off. 537 of the 551 tests that passed before still pass; the other 14 are the pins above.

`tests/features/codex_host/codex_host_fakes.py`:

- **`FakeThread` per-thread fields:** `created_at`, `updated_at`, `source` (a str or a `{"subAgent": …}` dict), `parent_thread_id`, `status` (`notLoaded` or `systemError`), `explicit_name` (send `name: null` or `""`) and `hidden_reads`. It also gains `_status_wire()` and `source_kind()`.
- **`FakeAppServer` switches:**
  - `paged_thread_list`: honor `sourceKinds`, `cwd`, `searchTerm`, `sortKey` and `limit`, with `threads-after-N` cursors and a null cursor at the end;
  - `thread_page_size`;
  - `endless_thread_list`: empty pages with fresh cursors;
  - `skills`: cwd → entries;
  - `record_turn_input`, `drop_skill_input` and `input_hidden_reads`;
  - `goal_get_answer`;
  - `turn_cursors`.
- **New handlers:** `thread/goal/get`, `thread/compact/start`, `thread/delete`, `thread/turns/list` (`itemsView`, cursor and limit, empty for ephemeral threads) and `skills/list`. `thread/goal/get` leaves a `notLoaded` thread's status unchanged.
- **Helpers:** `goal_record(...)` and `skill_entry(...)`.
- **What did not change:** the legacy `thread/list` answer (all threads, `nextCursor: "cursor-after-page"`), `thread/resume` logging, and every existing answer.

`tests/features/codex_host/codex_host_support.py`:

- `NEXT_STEPS` gains 4 entries, copied verbatim from §9.2.
- `NEW_FAILURE_CODES` grows from 15 to 19, and `CLASSIFICATION_ROWS` gains 4 rows.
- `TOOL_TABLE` gains rows 16 to 26.
- `HELPER_METHODS` lists the 12 methods.
- The §9.2 message texts, plus `COMPACT_STARTED_TEXT`, `NO_GOAL_TEXT`, `APP_SERVER_PLACE`, `SKILL_FUNCTIONS_MODULE`, `BUSY_TEXT` and `thread_suffix()`.
- `HostTestCase.patch_skill_functions(name, value)`.
- `StubCodexHost` gains the 12 new methods and the `goal_missing` switch.

## Pins changed

Each was authorized in spec §13. Line numbers are in the committed files; each change is shown before → after.

| File:line | Before → after | Spec ID |
|---|---|---|
| `test_codex_host_tools.py:153` (was 141) | `assertEqual(len(tools), 15)` → `26` | §13; AC-33 |
| `test_codex_host_tools.py:58-69` | `_valid_arguments` gains one valid argument set per new tool (11). There is no `KeyError` in `test_every_tool_turns_host_errors_into_error_results` once the tools exist. | §13 (r2, R-2) |
| `test_codex_host_lifecycle.py:101` | `"15 check_codex_ready"` → `"26 check_codex_ready"` | §13; AC-1 of codex-host |
| `test_codex_host_packaging.py:172` (was 165) | `(15, "check_codex_ready")` → `(26, "check_codex_ready")` | §13 |
| `test_codex_host_packaging.py:38-47` | `RECORD_EXPORTS` goes from 15 to 20: `CodexSkillInfo`, `CodexStoredTurn`, `CodexThreadGoal`, `CodexThreadSummary` and `CodexTurnPage`, in sorted places | §13; §12.3 |
| `test_codex_host_packaging.py:62`, `:87` | `NEW_ENUMS` and `ENUMS_CODEX_ORDER` (22 → 23) gain `CodexSkillScope` between `CodexSandboxReadiness` and `CodexSortDirection` | §13 |
| `test_codex_host_records.py:61-62` | `CodexHostOperation` expectation: `{…TOOL_NAMES}` → `{…TOOL_NAMES, "DELETE_CODEX_THREAD": "delete_codex_thread"}`, with a comment | §13; INV-2 |
| `test_codex_host_records.py:79` | `SDK_WIRE_SOURCES` gains `"CodexSkillScope": ("SkillScope", "enum")` | §13 |
| `test_codex_host_records.py:98-103` | `RECORD_NAMES` goes from 15 to 20 | §13 |
| `test_codex_host_records.py:123-127, 147-148, 183-196` | `_valid_kwargs` gains 5 baselines and their lazy imports | §13 (r2, R-2) |
| `test_codex_host_sdk_contract.py:46-47` | `CALL_LIST` gains `"thread_compact": ("thread_id",)`, with a comment | §13 |
| `codex_host_support.py` (`NEXT_STEPS`, `NEW_FAILURE_CODES`, `CLASSIFICATION_ROWS`, `TOOL_TABLE`, `StubCodexHost`) | as listed under fixtures | §13 |
| `tests/features/codex_host/README.md`, `FEATURE.md` | "fifteen" → twenty-seven methods and twenty-six tools, plus the 5 File Index bullets, the Logs line and the Test Suite Map rows | §13 |

These stay untouched:

- `NATIVE_CODEX_EXPORTS`, `NATIVE_INIT_SHA256`, `REPO_MAP_SECTION`, `README_BULLET` and `toolsets.__all__`;
- the `list_codex_threads` exact params and the spawn goal order;
- every file in `tests/features/harness_threads/`;
- the §9.3 constants dict in `test_codex_host_records.py`, because the new constants are tested in `test_codex_host_helper_surface.py`.

## Spec defects and notes for S3 and S4

1. **`{status}` in `GOAL_UNFINISHED_MESSAGE` is unspecified as wire value or enum.** The tests take the wire value (`usageLimited`). On Python 3.11, `CodexGoalStatus(str, Enum)` formats as `CodexGoalStatus.USAGE_LIMITED`, so S3 must pass `.value`. Minor: the spec should say "the wire status".
2. **`{seconds}` in `INPUT_NOT_RECORDED_MESSAGE`.** The tests expect plain `str.format` of the module-global deadline (`600.0`, `0.25`). A `:g` format would fail. This is consistent with §9.2.
3. **The `{names}` separator.** §9.2 says the list is comma-separated, but its exact text is not pinned. The tests read the names as tokens after the exact prefix, and take the tail (`" and N more."` or `"none"`) exactly.
4. **The `CALL_LIST` pin cannot go red.** openai-codex 0.162.1 already has `thread_compact`, so the pin is green at once. It still guards a future SDK bump.
5. **The records pins turn 2 existing record tests red** until the records exist, because `_valid_kwargs` imports `CodexStoredTurn`. This is expected under §13 (R-2), and they go green with §12.3's records.
6. **Text drift outside `tests/`, which is not mine to change:**
   - `test_codex_host_tools.py::test_toolset_holds_the_fifteen_tools_with_their_spec_schemas` keeps its name and docstring, because §13 does not authorize a rename. After this change the test checks 26 tools.
   - `vidbyte/tools/toolsets/__init__.py:11` says "One tool per CodexHost function", which is no longer true: `delete_codex_thread` has none. S3 should reword it.
7. **AC-37 and the skill run.** A `skills/list` failure inside `run_codex_skill` keeps the operation `list_codex_skills`, because the run calls the host's public method (D-2). A not-found or disabled refusal carries the run's own operation (AC-32). The tests pin both.
8. **NFR-5** says each read-back round is one `thread/read` plus one `thread/turns/list`. The tests count only `thread/turns/list` and interrupts, so the existence read inside `list_codex_turns` is free to stay.
