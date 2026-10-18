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

## Round 2 (spec r4, `d0529d15`)

r4 answered both blocking questions with option (a) and settled the six ambiguities. Tests commit: `ab13e1e7`.

**Pins rewritten (§13, r4 S2-1).** Each line now carries a comment citing §13 r4.

| File:line (before → after) | Before | After |
|---|---|---|
| `test_codex_host_lifecycle.py:101` → `:102` | `"26 check_codex_ready"` | `"42 check_codex_ready"` |
| `test_codex_host_helper_lifecycle.py:109` → `:110` | `"26 False"` | `"42 False"` |

Both passed before the rewrite and fail now for one reason: the only element that differs is the printed count, `26` against `42`. They stay red until S3 adds the sixteen tools.

**Stale 26-tool prose, now 42.**

- `FEATURE.md:190` and `:207`, and `README.md:51`, as asked.
- Also the same staleness in four more places: `README.md:26` ("twenty-six tools" → "forty-two"), the docstrings at `test_codex_host_helper_tools.py:3` and `:126`, and `test_codex_host_tool_hardening.py:3`. These are prose only, with no assertion change.
- Left alone: `FEATURE.md:5` and `:40`, which describe the shipped host (26 tools today), and the test name `test_the_toolset_holds_26_tools_and_offers_no_forbidden_parameter`. Renaming it would change a node id the plan cites.

**Tightenings.** Each one picks r4's side of an ambiguity the test used to accept either way. All were red before and are still red for the right reason.

1. S2-3, `feature_constants::CodexFeatureTableTests`: the method-name test is renamed `test_the_fifteen_method_names_are_named_constants_that_hold_their_wire_strings`. It pins each of the fifteen names to its wire string and its place in `__all__`, through the new `FEATURE_METHOD_CONSTANTS`, which replaces `FEATURE_METHOD_NAMES` in `codex_host_feature_support.py`. It is now red with an `AssertionError` listing all fifteen missing names; before, it was an `AttributeError` on the first one. No plan or spec row cited the old name.
2. S2-3: `test_the_export_list_stays_ascii_sorted_and_names_every_new_constant` now checks all fifteen names, and is still red. The green guard `test_no_new_name_goes_into_the_shared_codex_constants` now checks that none of the fifteen is in `vidbyte.lib.constants.codex`. It is still green. It catches a plausible slip: `CODEX_GOAL_SET_METHOD` lives in that module.
3. S2-4: three `feature_records` effort rows check the whole text with `name="reasoning_effort"`. They are still red with `ImportError` (`codex_host_modes` or `codex_host_features`).
4. S2-5: `test_network_access_needs_a_read_only_or_workspace_write_sandbox` checks the whole text with `sandbox.name`, and `NETWORK_PREFIX` is gone. It is still red with `ImportError`.
5. S2-7: `settings_modes::test_an_ended_or_unknown_turn_is_refused_locally_and_sends_nothing` requires `summary == TEXT + thread_suffix(thread_id)`. It is still red with `AttributeError` (`update_codex_turn_settings`).
6. S2-8: `thread_admin::test_search_names_every_top_level_source_and_finds_this_hosts_threads` requires `"archived" not in params`. It is still red with `AttributeError` (`search_codex_thread_content`).

The two `KNOWN EDGE CASES` headers (`feature_constants`, `feature_records`) now describe r4.

Not tightened:

- S2-6: the tests always pass both `command` and `cwd`, and a refusal row for a missing one would be a new test.
- S2-2: the coordinator said no change is needed. The new text is checked by value, and nothing pins the name `CODEX_HOST_NO_STORED_GOAL_MESSAGE` itself (see Open items).

**Runs.**

```
area:     253 failed, 1041 passed, 3 skipped in 75.50s (0:01:15)
no SDK:   100 failed, 803 passed, 394 skipped in 51.21s
full:     253 failed, 6572 passed, 27 skipped in 129.26s (0:02:09)
```

Area failures break down as follows:

- 233 new red tests, the same count as before;
- 19 tests red through rewritten §13 pins (17 from round 1, plus these 2);
- 1 inherited `harness_threads` test.

By exception, the area failures are now 128 `AttributeError`, 48 `ImportError`, 45 `AssertionError`, 28 `ModuleNotFoundError`, 2 `FileNotFoundError`, 1 `TypeError` and 1 `RuntimeError`. Compared with round 1, `AssertionError` is up 3 (the two pins and the method test) and `AttributeError` is down 1. The full suite's only failure outside `tests/features/codex_host/` is the inherited one. The no-SDK view is unchanged, because both snippet modules need the extra.

**Lint**, with the changes staged:

```
S063 IMPROVED 4 -> 3. Lower it with: python lint/run.py --rule S063 --update-baseline

S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
```

The S063 line was already there in round 1. Lowering it means editing `lint/`, which S2 may not touch.

**test-plan.md.**

- The two rows are added under "Superseded pins rewritten".
- Spec defects 1 to 8 are each marked "Resolved by r4", with the matching S2 row and the test change.
- The run numbers, the exception table and the implementer notes are refreshed.

The spec's §6.2 Proof column is unchanged, because no cited node id changed.

**Open items.**

- `CODEX_HOST_NO_STORED_GOAL_MESSAGE` is pinned only by text. A by-name pin would mean adding `NO_STORED_GOAL_MESSAGE` to `TEXT_NAMES`, with the support literal renamed to match. That takes about six lines and is the coordinator's call.
- The pack README's change log has no round-2 entry, because the task limited doc edits.

**Round 2b (coordinator follow-up, commit `893f1df4`).** All three open items above are now closed in the test tree.
- Name pin: `TEXT_NAMES` gains `NO_STORED_GOAL_MESSAGE`, and the support literal is renamed to match (goal_control updated, imports kept sorted). The test fails because `vidbyte.lib.constants.codex_host` has no attribute `CODEX_HOST_NO_STORED_GOAL_MESSAGE`, which is the right reason. The shared-constants guard stays green.
- `FEATURE.md:5` now describes 53 methods: the 25 slice-2 functions, `collaboration_mode`, and 42 tools, with the nine INV-42 functions kept from the model. `:40` now says forty-two tools. `:230` now says eleven older modules. I also fixed the stale "named only first and last" header in `codex_host_feature_support.py`. The pack README gains a round-2 change-log entry.
- Area: `253 failed, 1041 passed, 3 skipped in 75.52s (0:01:15)`, with the same failing set and exception mix as round 2, so test-plan counts did not move. Only defect 1 and the implementer note were updated. Lint: `SDK-LINT: PASS`.

## Round 3 (spec r5, `5f6c4fc4`)

Tests commit: `32e1a404`. I fixed the five items from the S3 block against the spec and the SDK, not against the implementation:
- B-1: the §13 r5 field-tail pin now ends with `collaboration_mode`.
- B-2: the ENDED event's snapshot is now COMPLETED with a minimal `CodexRunResult`, because the slice-1 record refuses COMPLETED without a result (INV-48).
- B-3: `thread/read` now expects `includeTurns: False`, which openai-codex's `thread_read` always sends (`client.py:498-503`).
- B-4: `StubCodexHost._enter` now takes its own `name` positional-only (`name, /, *args, **kwargs`), so the rename stub can record a `name` keyword. This is the only clean fix: every caller passes the name positionally, and the alternatives copy `_enter`'s gate and raise logic or drop the keyword that `feature_tools` asserts.
- B-5: the bearer member is now `BEARER` (D-40) in both pins, and no `BEARER_TOKEN` remains in the test tree.

Results:
- Before the fixes the area run was `8 failed, 1286 passed, 3 skipped`.
- After them it is `3 failed, 1291 passed, 3 skipped in 95.04s (0:01:35)`. The three failures are:
  - the two B-5 tests: `AttributeError: BEARER`, and the `EXPECTED_ENUMS` diff `BEARER_TOKEN` against `BEARER`;
  - the inherited `harness_threads` test.
- Lint shows `SDK-LINT: FAIL` from one cause, S054 REGRESSED (4 against an allowance of 3). That finding is production's `vidbyte/lib/enums/codex.py:288 BEARER_TOKEN = "bearerToken"`, which S3 must rename. Lint reports no finding in the test tree.

## Round 4 (S4 review, spec r6 `4d972438`)

Tests commit: `9ad2771e`. It adds 9 tests for review rows R-1 and R-3 to R-7, updates `_side_chat_view` to r6 row 34, and adds the r6 worktree-root triple to the support module and `TEXT_NAMES`. It also corrects the NFR-3 row of `test-plan.md` (R-7) and adds the R-6 tests to the INV-22 row. No production file was touched, and no worktree file was edited to make a mutant or apply a fix: every fix check and mutant runs in memory.

New tests, and what they show on `8ea8734f`:
- R-6 (INV-22): `stream_wait::test_a_subscription_made_mid_turn_starts_at_the_oldest_kept_event` and `…_over_a_full_window_starts_at_the_oldest_event_still_kept`. Both pass now. Each one kills S7 (`TimeoutError` at the bounded first read).
- R-7 (NFR-3): `stream_wait::test_the_turn_character_bound_counts_every_kept_event_not_only_the_new_one` and `stream_wait::test_the_host_character_bound_drops_each_turns_own_oldest_events`. Every event is under the bound. Both pass now. They kill S3c (`(600, 6) != (300, 3)`) and S3b (`1000 not less than or equal to 300`).
- R-3 (EC-19): `stream_wait::test_an_oversize_event_costs_a_lagging_subscriber_only_its_own_gap`, which uses the shared `patch_stream`. It is red now: it gets `[md, gap, md, ended]`, because `GAP(2, 3)` loses b and c. It is green under `fixcheck2.py RE3` and under the S9 fix mutant (2 passed with the existing oversize test).
- R-4 (INV-31, EC-64): `goal_control::…::test_a_resume_set_codex_applied_but_answered_badly_is_cancelled_once_and_cleaned_up`, built on `before_response("thread/goal/set", …)`. It is red now: goal calls are `['finish', 'unregister_goal_operation']`, with no cancel. It is green under `fixcheck2.py RE2`, and EC-37's refusal test stays green with no cancel.
- R-1 (EC-63): `worktree::…::test_a_worktree_root_that_cannot_be_prepared_is_refused_by_type_without_the_home_path_and_git_never_runs`. It has three subtests: no home folder (RuntimeError), home not writable (simulated PermissionError, since a read-only folder does not stop `mkdir` on Windows), and `~/.vidbyte` as a file (the type comes from the real `mkdir`: FileExistsError on Windows, NotADirectoryError on POSIX). It is red now: each subtest raises the raw exception. It is green under S2's in-memory version of the review's fix (`scratchpad/round4/fixcheck_r1.py`: 32 passed across worktree and constants). Two existing constants tests are now red by design, because `TEXT_NAMES` names the triple: the value test (attribute missing) and the `__all__` test.
- R-5 (AC-36 extended): `feature_tools::…::test_the_side_chat_tool_resets_the_fields_a_side_chat_refuses_before_it_narrows` (stub) and `…::test_the_side_chat_tool_starts_under_defaults_that_set_tools_a_name_and_a_personality` (host). They are red now: the stub keeps tools, name and personality, and the host refuses with `does not use the CodexSpawnRequest field name`. Both are green under `fixcheck_re6.py`.

Proof:
- Mutant runner, run on `tests/features/codex_host` with the 7 red tests deselected:

  | Run | Exit | Result |
  |---|---|---|
  | NONE | 0 | 591 passed, 1 skipped |
  | S7 | 1 | killed |
  | S3b | 1 | killed |
  | S3c | 1 | killed |

  The outputs are in `scratchpad/round4/mut-*.txt`.
- Area run: `8 failed, 1295 passed, 3 skipped in 85.03s (0:01:25)`. The failures are the 7 red tests above (5 new and 2 constants) plus the inherited `harness_threads::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`.
- Lint: `SDK-LINT: PASS`, with no `tests/features` findings.
- Test files: the largest is `test_codex_host_stream_wait.py` at 651 lines.

**Niche facts.**
- `mutant.py` runs with `-x`, and unittest methods run in alphabetical order. A kill therefore names the first failing test only, so the second R-6 kill was proven with `-k`.
- The stream tests call `wait_done` before `drain`. A suspended async generator does not interleave, so this is how they make a subscriber lag deterministically.

**Open items.** None for S2. The repair agent's fixes for R-1, R-3, R-4 and R-5 should turn the 7 red tests green, with no test edits.
