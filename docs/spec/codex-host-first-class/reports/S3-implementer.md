# S3 implementer report: codex-host-first-class

- **Date:** 2026-10-18
- **Status:** BLOCKED. All 39 §12.3 rows are implemented and committed. Seven S2 tests and one lint rule cannot pass without a decision the implementer may not make.
- **HEAD:** see the STATUS block (the last commit is this report).
- **Branch:** `feat/codex-host-first-class`. Nothing has been pushed.
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1181. It is still a draft, its body was not edited, and its title and base are unchanged.
- **S2_HEAD:** 625279c6. `git diff 625279c6..HEAD -- tests` is empty, with 0 lines.

## 1. Blockers

Each blocker below is a test, or a lint baseline, that disagrees with the spec, the installed openai-codex 0.163, or a slice-1 contract that INV-48 keeps unchanged. Everything else in the area passes.

| # | Where | Spec / contract | Failing output | Why the implementer cannot fix it |
|---|---|---|---|---|
| B-1 | `tests/features/codex_host/test_codex_host_hardening_records.py:356` (`test_the_new_fields_default_to_unset_and_build_with_the_sandbox_they_need`) | §12.3 row 7 and D-5: `collaboration_mode` is the **last** field of `CodexSpawnRequest`, appended after `writable_roots`. | `Lists differ: ['turn_service_tier', 'network_access', 'writable_roots', 'collaboration_mode'] != ['turn_service_tier', 'network_access', 'writable_roots']` | This slice-1 pin lists exactly the three fields that follow `name`. §13's superseded-pins table updates the goal-field literal but not this pin. Satisfying the pin means dropping or moving the spec's field. |
| B-2 | `tests/features/codex_host/test_codex_host_feature_records.py:309` (`CodexTurnEventRecordTests.test_a_snapshot_is_there_exactly_when_the_kind_is_ended`; its fixture `_snapshot()` is at `:308`) | The slice-1 `CodexTurnSnapshot` (`vidbyte/lib/dataclasses/codex_host.py:354`) refuses `COMPLETED` without a result. This slice does not change that record (INV-48). | `AssertionError: False is not true : ('snapshot', {}, 'Codex turn snapshot status COMPLETED requires a result.')` | The fixture builds `CodexTurnSnapshot(handle=..., status=COMPLETED)` with no result. That record raises before any `CodexTurnEvent` check runs, so `refused()` catches the wrong error, one that has no `field`. |
| B-3 | `tests/features/codex_host/test_codex_host_mcp_memory.py:159` (`test_a_paused_goal_thread_is_loaded_then_its_memory_set_then_status_and_reset_are_sent`) | §9.2: `set_codex_thread_memory_mode` sends `thread/read` through the existing `require_thread`, which calls openai-codex's typed `thread_read`. | `First differing element 0: ('thread/read', {'threadId': 'thr-1', 'includeTurns': False}) != ('thread/read', {'threadId': 'thr-1'})` | `openai_codex/client.py:498-503` always sends `includeTurns`. The other S2 tests already expect it (`test_codex_host_thread_helpers.py:299`, and the `KNOWN EDGE CASES` notes of `test_codex_host_threads.py` and `test_codex_host_fork_review.py`). Only element 0 differs. |
| B-4 | `tests/features/codex_host/codex_host_feature_support.py:334`, the stub `rename_codex_thread`, calls `self._enter("rename_codex_thread", thread_id=thread_id, name=name)`. `codex_host_support.py:630` declares `_enter(self, name, *args, **kwargs)`. | §8.5 and §9.2: `rename_codex_thread(thread_id, name)`, and `RenameCodexThreadTool` calls it once. | `TypeError` ("got multiple values for argument 'name'") raised inside the stub, so the tool answers `codex.api_error: rename_codex_thread failed with TypeError.` | Any call to the stub's `rename_codex_thread` raises before it records anything. Four tests fail on this one line: `test_codex_host_feature_tools.py::CodexFeatureToolCatalogTests::test_running_every_new_tool_never_reaches_a_function_that_has_no_tool`, `test_codex_host_feature_tools.py::CodexFeatureToolArgumentTests::test_the_settings_listing_and_memory_tools_pass_only_their_own_arguments`, `test_codex_host_tools.py::CodexHostToolErrorTests::test_every_tool_turns_host_errors_into_error_results` and `test_codex_host_tool_hardening.py::CodexToolLocalFailureTests::test_a_runtime_or_key_error_becomes_an_api_error_result_naming_only_the_tool_and_type`. In every one, the rename subtest is the only failing subtest. |
| B-5 | Lint S054 (`bandit-security-subset`) is at 4 against an allowance of 3, from `vidbyte/lib/enums/codex.py:288` `BEARER_TOKEN = "bearerToken"`. | §9.1 names the member `CodexMcpAuthStatus.BEARER_TOKEN = "bearerToken"`, and `test_codex_host_records.py:83` and `test_codex_host_mcp_memory.py:83` pin it. | `S054 REGRESSED: 4 finding(s), allowance 3.` (ruff S105: "Possible hardcoded password assigned to: BEARER_TOKEN"). The repo already counts `TRIM_TO_TOKEN_BUDGET` and `PASS = "pass"` the same way. | Raising `lint/baseline.json` and adding a suppression are both forbidden, and renaming the member changes a pinned public name. `run_ci.py --stage source` stops at lint, so neither gate stage can pass. |

### Options for the coordinator

1. **S2 repairs its tests and support files** (B-1 to B-4), and the user approves raising S054 to 4 (B-5).
   - B-1: add `"collaboration_mode"` to the pin at `:356`.
   - B-2: give `_snapshot()` a result, or use a status that needs none.
   - B-3: expect `{"threadId": ..., "includeTurns": False}`.
   - B-4: rename `_enter`'s first parameter, or record the rename under another key.
   - Consequence: no production change is needed. The implementer then runs both gate stages, pushes, and updates PR #1181.
2. **Change production to match the tests.** This would move `collaboration_mode`, relax `CodexTurnSnapshot`, send a raw `thread/read`, and rename `BEARER_TOKEN`. Consequence: it breaks D-5, INV-48, the `require_thread` behaviour other tests pin, and the §9.1 enum name. Not recommended.

**Recommendation:** option 1. Each test defect is a single line. B-5 is the same false positive the baseline already counts twice.

## 2. Rows to commits

| Rows | Commit(s) |
|---|---|
| 1 (enums, GitFlag) | 43ebb0bb |
| 4 (constants and messages) | ead9795a |
| 5 (git values) | ad71fb89 |
| 6, 7 (mode records, spawn field) | 6626ed0f |
| 8 (feature records) | e6a6514a |
| 9 (17 input records) | 98f1ccf5 |
| 10 (GitWorktreeSpec) | 6ff014f6 |
| 11, 12, 13 (GitWorktrees, `lib.process` export, lib README) | 7d761619 |
| 2, 3 (`enums/process.py`, `enums/__init__.py`) | 43ebb0bb |
| 14 (connection: unmodeled raw, parse step) | 37b88408, plus the `_log_call` tweak in 9d3e9966 |
| 15 (errors) | f192b538, plus the goal-resume naming in 9d3e9966 |
| 16 (wire: collaboration mode, plan-only turns) | 15ef339e |
| 17 (feature_wire) | 365e1594, plus the typing fix in c788a097 |
| 18 (turn_stream) | 294eb192, plus the typing and A007 fix in c788a097 |
| 19, 20 (turns, turn_events) | bba8c3aa |
| 21 to 25 (host_core, turn_starts, preflight, thread_helpers, skill_functions) | 7abf98ac |
| 26 to 29 (four mixins) | 9d3e9966 |
| 30 (host composition) | 068a812e |
| 31, 32 (tool base, descriptions) | 1dc5e129, plus 1226e06a |
| 33 to 36 (controls, thread_actions, live, tool skill functions) | ff2350eb |
| 37 to 39 (exports, CodexHostTools at 42) | 3a602eef |

The files changed since S2_HEAD match the §12.3 file list exactly. The only other file in that range is `pipeline.md`, from the coordinator's commit 84462e82.

## 3. Budget (§8.4)

| Item | Budget | Actual |
|---|---|---|
| New files | 13 | 13 |
| New classes | 69 | 69. 70 `+class` lines minus `CodexHost`, whose line changed only its bases. |
| New dependencies | 0 | 0 |
| New public endpoints | 42 | 42: 25 methods, the `collaboration_mode` field and 16 tools |

**INV-47 ceilings:**

| File | Lines | Ceiling |
|---|---|---|
| `host.py` | 786 | 900 |
| `wire.py` | 839 | 840 |
| `feature_wire.py` | 362 | 599 |
| `thread_methods.py` | 320 | 599 |
| `controls.py` | 206 | 599 |
| `thread_actions.py` | 303 | 599 |
| `turn_stream.py` | 277 | 599 |
| `turn_starts.py` | 258 | 599 |
| `settings_methods.py` | 245 | 599 |
| `goal_methods.py` | 172 | 599 |

## 4. Implementation deviations (for spec §17 once unblocked)

1. **Goal-resume error naming** (`errors.py` and `connection.py`). A JSON-RPC error inside the goal resume's start names `thread/goal/set`, the one request Codex refused, in the packet summary and on the `codex_host_call_failed` record. It does not name the call `resume_goal_operation`. EC-37 and the S2 test expect this.
2. **`host_core.py` holds a third shared helper.** Besides `_guard` and `_owned`, it holds `_change_idle`, the one idle-thread history change that archive, revert, inject and clear share (INV-34). It sits in the core because all four mixins need it.
3. **`CodexTurnStarts._resume_now`** suppresses a failing goal cancel, then still finishes, unregisters and raises the original error. A failed cleanup never hides the start's own failure.
4. **Defaults apply only to `None`.** `run_codex_plan`, `start_codex_side_chat` and `resume_codex_goal` replace `request` only when it is `None`, so a wrong-type value such as `{}` reaches the record and is refused, as `test_codex_host_inputs.py` requires.
5. **Gate feature words.** The `require_experimental_api` feature word is the wire method constant, or the literal `"collaboration_mode"` for a mode. For `run_codex_plan` that is `collaborationMode/list`, and for `list_codex_child_threads` it is `thread/list`.
6. **The stream translator narrows by type.** It narrows each payload to its openai-codex notification class and raises `TypeError(<payload type>)` for a delta openai-codex delivered as `UnknownNotification` (EC-20), which `record` logs once and shows as a GAP.
   - So `turn_stream` loads openai-codex at module level, as the §8.4 and INV-45 list of SDK modules allows.
   - The window checks were split into `_fits`, `_drop_oldest`, `_size` and `_log_drop`, so no bound literal sits beside a bound name (A007).
7. **`feature_wire` reads with `require_instance`.** `memory_status` and `hit_thread` read their members through `RecordFieldConverter.require_instance`, so a missing or wrong-type member is still a `ConfigurationError` and mypy sees typed values.
   - `hit_thread` now returns `CodexThreadInfo` and is no longer optional.
   - `mcp_server` and `hit_thread` are public helpers that the spec does not list.
   - `goal()` returns `CodexThreadGoal | None`.
8. **Records.**
   - `CodexPlanStep.step`, the search snippet, and the event's `item_id`, `item_type` and `text` allow blank text.
   - The rename record takes a one-line name.
   - `GitWorktreeSpec` bounds its timeout by `NATIVE_THREAD_MAX_SECONDS` and its output by `NATIVE_PROCESS_MAX_OUTPUT_BYTES`.
9. **Wire.**
   - `CodexParamsTranslator.collaboration_mode` is a public static method, so `feature_wire` reuses it.
   - `sandbox_policy` dumps through openai-codex's `SandboxPolicy` model.
   - `CodexLiveTurn.finish` closes the stream after `set_result`, so the ENDED event carries the final snapshot.
10. **Side chat.** The side chat's turn view is the request unchanged. The fork view carries the overrides.
11. **Tool texts.** `THREAD_SETTINGS_UPDATED_TEXT`, `THREAD_ARCHIVED_TEXT` and `THREAD_RENAMED_TEXT` are one sentence each. §9.2 gives only their role, so the wording is the implementer's.
    - `TURN_SETTINGS_STATUS_TEXT` is the §9.2 text, verbatim.
    - The tool modules' `__all__` lists the classes only, matching `COMPACT_STARTED_TEXT`.
12. **Resume tool.** `ResumeCodexGoalTool` clears from `spawn_defaults` every path in `CODEX_HOST_REJECTED_FIELDS[RESUME_CODEX_GOAL]` and `CODEX_HOST_GOAL_REJECTED_FIELDS`, reset to a fresh record's value, so it follows the host's own tables.
13. **Tool headers.** The tool headers and the `CodexHostTools` docstring name `forget_codex_turns` as well as `delete_codex_thread` and the nine INV-42 functions, because none of them has a tool.

## 5. Gates

**Area tests:** `tests/features/codex_host` and `tests/test_codex_*.py`, at `3a602eef`, plus the `_base` narrowing.

```
7 failed, 851 passed, 1 skipped in 48.40s
```

The 7 failures are exactly B-1, B-2, B-3 and the four B-4 tests.

**Lint:** `lint/run.py` with everything staged.

```
S009   staged-mypy-contracts                     347    350 IMPROVED   (346 after 1226e06a; none in touched modules)
A007   operational-constants                     255    255 RATCHETED
S054   bandit-security-subset                      4      3 REGRESSED
SDK-LINT: FAIL
```

S054 (B-5) is the only regression.

**Semgrep:** `.semgrep/typed-mapping-boundary-policy.yml` reports 0 results and 0 errors on every changed `.py` file.

**Full gate:**
- `run_ci.py --stage source` stops at lint on S054:

  ```
  SDK-LINT: FAIL
  CI failed: Command failed with exit code 1: ...lint\run.py
  ```

- The remaining source steps were run by hand after lint: compileall, the three `check_*` scripts and the full pytest. They are in the next section.
- The package stage was not run, because the source stage cannot pass.

## 6. Remaining source steps (run by hand)

These are the `run_source` steps after lint, run at `3a602eef` with `PYTHONPATH` set to the worktree. Their output:

```
compileall ok
write_paths exit=0
primitives exit=0
reasoning exit=0
9 failed, 6816 passed, 27 skipped in 153.02s (0:02:33)
```

The 9 failures:
- **The 7 blocker tests above.**
- **`tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes`:** this failure is inherited from the base branch. This slice adds no FailureCode.
- **`tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport`:** this test is flaky under full-suite load (`stdin_write_failed`). It passed 3 times out of 3 when its file ran alone (`22 passed in 2.19s`, `22 passed in 2.07s`, `22 passed in 2.11s`), and this branch touches no MCP code.

## 7. Not done, by rule

- The branch has not been pushed, and the PR #1181 body has not been updated (`gh pr edit`), because both gate stages must pass first.
- The `spec.md` frontmatter `status`, the §17 r4 row and "Implementation deviations" have not been written, so the spec does not claim it is implemented while it is blocked. Section 4 above holds the deviation text, ready to paste.
- §6.2 has no blank Proof cells to fill. Every AC row already names its test.
