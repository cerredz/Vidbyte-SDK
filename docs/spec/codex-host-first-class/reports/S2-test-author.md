# S2 test author report: codex-host-first-class

- **Status:** BLOCKED on two spec decisions. All the work is done and committed; the decisions only change which older pins S2 may rewrite and which constant name S3 uses.
- **Spec:** `docs/spec/codex-host-first-class/spec.md` r3 (approved).
- **Branch:** `feat/codex-host-first-class`. Commits `fa27a3ad` (tests and test plan) and `f8146997` (spec §6.2 Proof column), on top of `5c16c588`. Nothing was pushed.
- **Test plan:** `docs/spec/codex-host-first-class/test-plan.md`. It holds the ID-to-test map, the counts, the red run, the pins and the spec defects. This report repeats only what the orchestrator needs to act on.

## What was produced

- **14 new test modules, 232 tests,** in `tests/features/codex_host/`:
  - `test_codex_host_feature_records.py` (42), `test_codex_host_feature_constants.py` (18), `test_codex_host_feature_structure.py` (10), `test_codex_host_feature_docs.py` (1) and `test_codex_host_feature_tools.py` (17);
  - `test_codex_host_feature_contract.py` (10), `test_codex_host_settings_modes.py` (32), `test_codex_host_stream_wait.py` (22), `test_codex_host_mcp_memory.py` (13), `test_codex_host_side_chat.py` (13), `test_codex_host_worktree.py` (13), `test_codex_host_goal_control.py` (18), `test_codex_host_thread_admin.py` (22) and `test_codex_host_first_class_snippet.py` (1).
- **4 more tests** in a new class of `test_codex_host_sdk_contract.py`, `CodexFirstClassSdkContractTests`.
- **Two support modules:**
  - `codex_host_feature_support.py` holds the §8.5, §9.2 and §9.3 literals, written from the spec and never read from production. It also holds `assert_packet`, `packet_text`, `priced_cost`, the canaries and `FeatureStubMethods`.
  - `codex_host_feature_fakes.py` is a `FeatureHandlers` mixin that answers the slice-2 methods as codex app-server 0.163.0 does.
- **Changes to existing support:**
  - `FakeAppServer` inherits `FeatureHandlers`.
  - `StubCodexHost` inherits `FeatureStubMethods`.
  - `codex_host_support.py` gains `FeatureHostCase`, with `opened`, `remark`, `sent`, `sent_methods`, `call`, `refused_locally`, `codex_error` and `call_records`.
- **The §13 pins** are rewritten in 9 older modules. The list is below.
- **`FEATURE.md`:**
  - the failure inventory gains 15 slice-2 failure modes;
  - the Test Suite Map gains the slice;
  - Omitted Testing Strategies gains 3 entries.
- **`README.md`:**
  - the File Index gains 16 files;
  - the intent paragraph now says 53 functions and 42 tools;
  - a `## Logs` entry is added.
- **Spec §6.2:**
  - every one of the 44 Proof cells holds full test node ids (AC-39 and AC-40 name their gate commands);
  - nothing else in the spec changed, which a line-by-line comparison with `HEAD~2` confirmed.

**Levels:**

- 86 of the 236 new tests run on CI without the `codex` extra:
  - the records, constants and docs;
  - most of the structure tests;
  - the stub-host tool classes;
  - the `GitWorktrees` helper class.
- The rest need the extra and are skipped on CI.

**The test most likely to catch a real bug** is `side_chat::CodexSideChatFlowTests::test_a_side_chat_forks_the_last_completed_turn_injects_the_boundary_and_starts_its_turn_on_the_fork`. It pins the exact six-step `/side` sequence and every param. That includes `lastTurnId` at the latest *completed* turn, `excludeTurns`, the appended developer instructions and the one boundary item. It also pins that nothing reaches the parent.

## Red evidence

Every command used the prepared venv `V` (Python 3.11.0, openai-codex 0.163.0). The global `python` was not used, and nothing was installed.

**Lint**, with the tests and the plan staged, before commit 1. It passed:

```
$ git add tests/features/codex_host docs/spec/codex-host-first-class/test-plan.md && "$V" lint/run.py
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

No baseline was raised or lowered. The two IMPROVED lines predate this run, and lowering them would touch `lint/`.

**The area, on the committed tree.** It is red by design:

```
$ PYTHONPATH=$(pwd) "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider --tb=line
FAILED tests/features/codex_host/test_codex_host_worktree.py::GitWorktreesHelperTests::test_add_makes_the_worktree_on_a_new_branch_and_git_runs_with_terminal_prompts_off
FAILED tests/features/codex_host/test_codex_host_worktree.py::GitWorktreesHelperTests::test_add_starts_the_branch_at_the_base_ref_when_one_is_given
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
251 failed, 1043 passed, 3 skipped in 75.01s (0:01:15)
```

The 251 failures break down as follows:

- 233 are new tests;
- 17 are rewritten pins;
- 1 is the inherited `harness_threads` failure.

The 1,043 passes are the 1,040 pre-existing tests outside the pins plus 3 green guards. One line per failure, by exception:

| Exception | Count |
|---|---|
| `AttributeError` | 129 |
| `ImportError` | 48 |
| `AssertionError` | 42 |
| `ModuleNotFoundError` | 28 |
| `FileNotFoundError` | 2 |
| `TypeError` | 1 |
| `RuntimeError` | 1 |

Each exception names a missing §8.5/§9 name, or compares against a spec value the code lacks. The test plan has the breakdown. The failing set is identical to the one before the docs edits and the commits (checked with `diff`).

**The new modules alone.** Red by design:

```
$ PYTHONPATH=$(pwd) "$V" -m pytest <the 14 new modules> -q -p no:cacheprovider --tb=no -rp
PASSED tests/features/codex_host/test_codex_host_feature_constants.py::CodexFeatureTextTests::test_no_new_name_goes_into_the_shared_codex_constants
PASSED tests/features/codex_host/test_codex_host_feature_contract.py::CodexFeatureGuardTests::test_the_guard_table_names_every_new_method
PASSED tests/features/codex_host/test_codex_host_feature_structure.py::CodexFeatureFileSizeTests::test_the_shared_codex_records_and_the_codex_agent_config_keep_their_bytes
229 failed, 3 passed in 7.33s
```

**Collection without the SDK** (CI's view). A `-p nosdk_plugin` plugin sets `sys.modules["openai_codex"] = None`. Collection passed:

```
$ PYTHONPATH="$(pwd);<scratch>/nosdk" "$V" -m pytest tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py -q -p no:cacheprovider -p nosdk_plugin --collect-only
tests/test_codex_usage_tracking.py::CodexHarnessAgentUsageIntegrationTests::test_three_turns_report_only_the_last_turn_delta

1297 tests collected in 1.18s
```

The same run with tests executing:

```
FAILED tests/features/codex_host/test_codex_host_worktree.py::GitWorktreesHelperTests::test_add_starts_the_branch_at_the_base_ref_when_one_is_given
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
100 failed, 803 passed, 394 skipped in 49.89s
```

**The whole repository suite.** Red only in the area:

```
$ PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider --tb=line
FAILED tests/features/codex_host/test_codex_host_worktree.py::GitWorktreesHelperTests::test_add_starts_the_branch_at_the_base_ref_when_one_is_given
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
251 failed, 6574 passed, 27 skipped in 130.05s (0:02:10)
```

Its failing set equals the area's, so nothing outside `tests/features/codex_host/` changed state.

**The commits:**

```
$ git log --oneline -3
f8146997 docs(spec): record test proof for codex-host-first-class
fa27a3ad test(codex-host): add failing tests for codex-host-first-class [AC-1..AC-44]
5c16c588 docs(spec): record codex-host-first-class S1 approval (r3)
```

`python scripts/run_ci.py` was not run, for two reasons:

- its source stage ends in the full pytest, which is red by design until S3;
- its package stage installs a wheel with pip, which this stage may not run.

Its lint step and its pytest step were run on their own above.

## §13 pins rewritten (file:line, before → after, in `fa27a3ad`)

| File | Before | After | Change |
|---|---|---|---|
| `codex_host_support.py` | :192 | :194-210 | `TOOL_TABLE` gains the 16 §9.2 rows (42 in all) |
| `codex_host_support.py` | :265 | :283-284 | `GOAL_REJECTED_FIELDS` gains `"collaboration_mode"` (7) |
| `codex_host_support.py` | :584-585 | :603-607 | `StubCodexHost(FeatureStubMethods)` |
| `test_codex_host_tools.py` | :71 | :72-88 | `_valid_arguments` gains 16 rows |
| `test_codex_host_tools.py` | :155 | :172-173 | `len(tools) == 42` |
| `test_codex_host_helper_tools.py` | :33 | :33-34 | `NEW_ROWS = TOOL_TABLE[15:26]` |
| `test_codex_host_helper_tools.py` | :133 | :134-135 | `len(tools) == 42` |
| `test_codex_host_tool_hardening.py` | :47 | :48-62 | `NO_HANDLE_ARGUMENTS` gains 14 rows |
| `test_codex_host_tool_hardening.py` | :127 | :142-143 | `len(tools) == 42` |
| `test_codex_host_records.py` | :68-69 | :69-111 | `EXPECTED_ENUMS` gains the 9 no-tool operations and the 9 new enums |
| `test_codex_host_records.py` | :86 | :129-135 | `SDK_WIRE_SOURCES` gains the 6 wire enums |
| `test_codex_host_packaging.py` | :78-105 | :78-115 | `ENUMS_CODEX_ORDER` has 35 names, ASCII-sorted |
| `test_codex_host_packaging.py` | :183 | :193-194 | the import probe expects `(42, "check_codex_ready")` |
| `test_codex_host_hardening_contract.py` | :547 | :547-548 | the fork row's tail gains `"collaboration_mode"` |
| `test_codex_host_hardening_records.py` | :430 | :430-438 | the goal request refuses `collaboration_mode` as the seventh field |
| `test_codex_host_inputs.py` | :50, :72 | :54-66, :89-106 | `VALID_RECORDS` has 34 records |
| `test_codex_host_inputs.py` | :184, :212 | :219-220, :249-271 | the boundary test gains the 22 new coroutine methods |
| `test_codex_host_sdk_contract.py` | :47 | :48-58 | `CALL_LIST` gains the §13 typed calls and goal-state hooks |

Four more tests go red only through the literals above:

- `tools::test_default_policy_allows_the_read_tools_and_denies_the_write_tools`, `tools::test_every_tool_turns_host_errors_into_error_results` and `tools::test_mcp_server_lists_and_runs_the_toolset`, through `TOOL_TABLE`;
- `packaging::test_new_packages_export_exactly_their_spec_lists`, through `ENUMS_CODEX_ORDER`.

`hardening_contract::test_every_new_constant_holds_its_spec_value_and_is_exported_in_order` goes red the same way, through `GOAL_REJECTED_FIELDS`. No assertion outside §13 was changed. Nothing was skipped, xfailed or weakened.

## Pruned or not written

- **The decided non-features:** the queue, the P2 items, the one-shot mirrors, a stream tool, turn-less watching, a new FailureCode, tools for the 9 INV-42 functions, and Q-10 and Q-11.
- **A paid live run.**
- **The pause duration in EC-55.** The test checks that every event arrives in order once the handler answers.
- **T-4 and T-7.** The spec marks them N/A and out of scope.
- **NFR-6 and NFR-8 as tests.** Both are gates.
- **The generality of the tool descriptions.** This is left to review; the sentence count and the paid-work sentence are tested.
- **Hypothesis.** It is not a dependency. A seeded `random.Random` property test covers `GIT_REF_PATTERN` instead.

## Spec defects

**Blocking decision 1: two 26-tool pins are missing from §13.**

- `tests/features/codex_host/test_codex_host_lifecycle.py:101` expects `"26 check_codex_ready"`.
- `tests/features/codex_host/test_codex_host_helper_lifecycle.py:109` expects `"26 False"`.
- Both pass today. Both go red the moment S3 adds the 16 tools.
- Rule 5 forbids S2 from changing them, and S3 may not edit tests. As committed, the suite cannot go fully green with a correct implementation.

The options:

- **(a)** Add both to §13's superseded table (26 → 42), and let S2 rewrite the two literals. This is a two-line test change.
- **(b)** Let S3 leave them red as accepted failures. This breaks AC-39.

**Recommendation:** (a).

**Blocking decision 2: the `CODEX_HOST_NO_GOAL_MESSAGE` name is taken.**

- The name exists with the text "Codex reports no goal on the thread after the goal run started.". It is used by `run_codex_goal` (`vidbyte/harnesses/native/codex/skill_functions.py:217`) and pinned at `test_codex_host_helper_surface.py:94`, which §13 keeps.
- §9.2 reuses the name for the new no-goal text of pause, resume and edit.
- The tests bind the new text, cause and next step by value through `assert_packet` and never import the message name. The new `CODEX_HOST_NO_GOAL_CAUSE` and `CODEX_HOST_NO_GOAL_NEXT_STEP` are pinned by name.

The options:

- **(a)** Rename the new message in the spec, for example to `CODEX_HOST_GOAL_MISSING_MESSAGE`. No test changes.
- **(b)** Supersede the `helper_surface:94` pin and `run_codex_goal`'s text. S2 must then rewrite that pin and the goal-run tests that check the old text.

**Recommendation:** (a).

**Ambiguities the tests tolerate.** Details are in the test plan.

- §9.3 names only 2 of the 15 method constants. The other 13 are pinned by value.
- The effort `{name}` in `CODEX_HOST_MODE_CONFLICT_MESSAGE` is unspecified. Either `effort` or `reasoning_effort` passes.
- The `{sandbox}` slot of the network-access message is unspecified. The name, the value or the str all pass.
- `CodexBackgroundTerminal`'s `command` and `cwd` defaults differ between §8.5 and §9.1. The tests always pass both.
- Whether the ended-turn turn-settings packet carries the thread sentence is unspecified. The test uses `startswith`.
- Whether search omits `archived` when it is false is unspecified. Absent or `false` both pass.

**Risks without a control.** None found beyond the residual risks the spec already accepts. One is T-2: a side chat can still call the parent's Vidbyte dynamic tools. It is documented in D-22, and the docstring test checks that the docstring says so.

## Niche facts for the next agent

- **Patch points, read at call time:**
  - `vidbyte.harnesses.native.codex.turn_stream.CODEX_HOST_STREAM_EVENT_LIMIT`, `CODEX_HOST_STREAM_TEXT_LIMIT_CHARS` and `CODEX_HOST_STREAM_HOST_EVENT_LIMIT`;
  - `vidbyte.harnesses.native.codex.turn_starts.CODEX_HOST_GOAL_RESUME_START_SECONDS`;
  - `vidbyte.harnesses.native.codex.thread_methods.CODEX_HOST_WORKTREE_TIMEOUT_SECONDS`.

  A module-level copy defeats the patch.
- **Modules the tests import by path:**
  - `vidbyte.lib.dataclasses.codex_host_modes` and `codex_host_features`;
  - `vidbyte.lib.process.git_worktree`;
  - `vidbyte.harnesses.native.codex.host_core`, `turn_stream`, `turn_starts`, `thread_methods` and `feature_wire`.

  `CodexConnection.raw` gains a `parse` keyword, and `CodexJsonObjectResponse` lives in `connection`.
- **`host.py` is 937 lines today against its INV-47 ceiling of 900,** so the ceiling test stays red until code moves into `host_core.py`.
- **The worktree tests run the real git:**
  - "git missing" is `PATH` set to an empty folder, because `CliRunner.find_program` walks `PATH` on Windows;
  - `Path.home` is patched;
  - a missing branch proves git never ran;
  - `GIT_TERMINAL_PROMPT=0` must override a caller's `1`.
- **Fake facts:**
  - `thread/fork` copies the parent's reviewer, policy and model unless the params name them;
  - `feature_answers[method]` scripts a malformed answer;
  - `autocomplete` completes turns as they start.
- **The slow-handler stream test (EC-55)** holds the SDK reader with an `asyncio.Event`, writes the later events, then releases. Every event must arrive with consecutive sequences.
- **The report file is not committed.** Slice 1's orchestrator saved its S2 report in a commit of its own.
