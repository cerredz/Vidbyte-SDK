# S3 implementer report: codex-host-first-class

- **Date:** 2026-10-18
- **Status:** DONE. All 39 §12.3 rows are implemented and committed, and D-40 (spec r5) is applied. Lint passes. `run_ci.py --stage source` fails only on the inherited harness_threads FailureCode-count test, and `--stage package` passes.
- **HEAD:** see the STATUS block. The last commit is this report.
- **Branch:** `feat/codex-host-first-class`, pushed to `origin` with `git push -u origin feat/codex-host-first-class`.
- **Draft PR:** https://github.com/cerredz/Vidbyte-SDK/pull/1181.
  - Its body was replaced with `gh pr edit 1181 --body-file` using the placeholder body.
  - It is still a draft (`isDraft: true`).
  - Its title (`[WIP] feat: CodexHost production hardening and first-class Codex features`) and base (`ai/resolve-pr-1055-comments`) are unchanged.
- **S2_HEAD:** e3d41513. `git diff e3d41513..HEAD -- tests` is empty, with 0 lines. Over the whole run, no byte under `tests/` was written by S3.

## 1. Blockers and how they were resolved

The first pass stopped on five blockers. The coordinator ruled on each one, and none of the fixes changed production behaviour.

| # | What failed | Ruling | Fixed in |
|---|---|---|---|
| B-1 | `test_codex_host_hardening_records.py:356` pinned the three fields after `name` in `CodexSpawnRequest`, but D-5 and row 7 append `collaboration_mode`. | A missed §13 pin. Spec r5 adds it (§16 S3-1). | S2, 32e1a404 (spec 5f6c4fc4) |
| B-2 | The `_snapshot()` fixture in `test_codex_host_feature_records.py` built a `COMPLETED` `CodexTurnSnapshot` with no result. The slice-1 record refuses that before any `CodexTurnEvent` check runs. | A test defect. | S2, 32e1a404 |
| B-3 | `test_codex_host_mcp_memory.py:159` expected `thread/read` without `includeTurns`. openai-codex's typed `thread_read` always sends it (`openai_codex/client.py:498-503`). | A test defect. | S2, 32e1a404 |
| B-4 | The stub's `self._enter("rename_codex_thread", ..., name=name)` collided with `_enter(self, name, *args, **kwargs)`. It failed 4 tests, in each case on the rename subtest only. | A support-file defect. `_enter(self, name, /, *args, **kwargs)` is now positional-only. | S2, 32e1a404 |
| B-5 | Lint S054 rose from 3 to 4. ruff S105 flags `BEARER_TOKEN = "bearerToken"` on the member name alone. | Raising the baseline was refused. Spec r5 D-40 renames the member to `BEARER` and keeps the value `"bearerToken"`. | S3, b5ffd64d (spec 5f6c4fc4; S2 updated its two pins) |

## 2. Rows to commits

| Rows | Commit(s) |
|---|---|
| 1 (enums, GitFlag) | 43ebb0bb, plus the D-40 rename `CodexMcpAuthStatus.BEARER` in b5ffd64d |
| 2, 3 (`enums/process.py`, `enums/__init__.py`) | 43ebb0bb |
| 4 (constants and messages) | ead9795a |
| 5 (git values) | ad71fb89 |
| 6, 7 (mode records, spawn field) | 6626ed0f |
| 8 (feature records) | e6a6514a |
| 9 (17 input records) | 98f1ccf5 |
| 10 (GitWorktreeSpec) | 6ff014f6 |
| 11, 12, 13 (GitWorktrees, `lib.process` export, lib README) | 7d761619 |
| 14 (connection: unmodeled raw, parse step) | 37b88408, plus the `_log_call` change in 9d3e9966 |
| 15 (errors) | f192b538, plus the goal-resume naming in 9d3e9966 |
| 16 (wire: collaboration mode, plan-only turns) | 15ef339e |
| 17 (feature_wire) | 365e1594, plus the typing fix in c788a097 |
| 18 (turn_stream) | 294eb192, plus the typing and A007 fix in c788a097 |
| 19, 20 (turns, turn_events) | bba8c3aa |
| 21 to 25 (host_core, turn_starts, preflight, thread_helpers, skill_functions) | 7abf98ac |
| 26 to 29 (the four mixins) | 9d3e9966 |
| 30 (host composition) | 068a812e |
| 31, 32 (tool base, descriptions) | 1dc5e129, plus the `_resolve_handles` narrowing in 1226e06a |
| 33 to 36 (controls, thread_actions, live, tool skill functions) | ff2350eb |
| 37 to 39 (exports, CodexHostTools at 42) | 3a602eef |
| Spec frontmatter, §17 row, deviations | the docs commit after b5ffd64d |

The files S3 changed match the §12.3 file list exactly. The only other files in the range are the coordinator's and S2's docs and tests commits.

## 3. Budget (§8.4)

| Item | Budget | Actual |
|---|---|---|
| New files | 13 | 13 |
| New classes | 69 | 69: 70 `+class` lines, less `CodexHost`, whose line changed only its bases |
| New dependencies | 0 | 0 |
| New public endpoints | 42 | 42: 25 methods, the `collaboration_mode` field and 16 tools |
| New FailureCodes | 0 | 0 |

**INV-47 ceilings,** rechecked at the final HEAD:

| File | Lines | Ceiling |
|---|---|---|
| `host.py` | 786 | 900 |
| `wire.py` | 839 | 840 |
| `feature_wire.py` | 362 | 599 |
| `thread_methods.py` | 320 | 599 |
| `thread_actions.py` | 303 | 599 |
| `turn_stream.py` | 277 | 599 |
| `turn_starts.py` | 258 | 599 |
| `settings_methods.py` | 245 | 599 |
| `controls.py` | 206 | 599 |
| `goal_methods.py` | 172 | 599 |

`wire.py` is one line under its ceiling, so any later change there needs a split first.

## 4. Implementation deviations

These are also in spec §17, under the S3 row. D-40 is not a deviation: the spec asked for it in r5.

1. **Goal-resume error naming** (`errors.py`, `connection.py`). A JSON-RPC error inside the goal resume's start names `thread/goal/set`, the one request Codex refused, in two places: the packet summary and the `codex_host_call_failed` record. It does not name `resume_goal_operation` (EC-37).
2. **`host_core.py` holds a third shared helper,** `_change_idle`. It is the one idle-thread history change that archive, revert, inject and clear share (INV-34), and all four mixins need it.
3. **`CodexTurnStarts._resume_now` suppresses a failing goal cancel.** It then still finishes, unregisters and raises the original error, so a failed cleanup never hides the start's own failure.
4. **Defaults apply only to `None`.** `run_codex_plan`, `start_codex_side_chat` and `resume_codex_goal` replace `request` only when it is `None`. A wrong-type value such as `{}` reaches the record and is refused.
5. **Gate feature words.** The `require_experimental_api` feature word is the wire method constant, or the literal `"collaboration_mode"` for a mode.
   - `run_codex_plan` uses `collaborationMode/list`.
   - `list_codex_child_threads` uses `thread/list`.
6. **The stream translator narrows by type.** It narrows each payload to its openai-codex notification class. A delta delivered as `UnknownNotification` raises `TypeError(<payload type>)` (EC-20), which `record` logs once and shows as a GAP.
   - So `turn_stream` loads openai-codex at module level, which INV-45's list of SDK modules allows.
   - The window checks are split into `_fits`, `_drop_oldest`, `_size` and `_log_drop`, to satisfy A007.
7. **`feature_wire` reads with `RecordFieldConverter.require_instance`.**
   - `memory_status` and `hit_thread` read their members this way, so a missing or wrong-type member is still a `ConfigurationError` and mypy sees typed values.
   - `hit_thread` returns `CodexThreadInfo` and is not optional.
   - `mcp_server` and `hit_thread` are public helpers that the spec does not list.
   - `goal()` returns `CodexThreadGoal | None`.
8. **Records.**
   - Blank text is allowed in `CodexPlanStep.step`, the search snippet, and the event's `item_id`, `item_type` and `text`.
   - The rename record takes a one-line name.
   - `GitWorktreeSpec` bounds its timeout by `NATIVE_THREAD_MAX_SECONDS` and its output by `NATIVE_PROCESS_MAX_OUTPUT_BYTES`.
9. **Wire.**
   - `CodexParamsTranslator.collaboration_mode` is a public static method, so `feature_wire` can reuse it.
   - `sandbox_policy` dumps through openai-codex's `SandboxPolicy` model.
   - `CodexLiveTurn.finish` closes the stream after `set_result`, so the ENDED event carries the final snapshot.
10. **Side chat.** Its turn view is the request unchanged, and the fork view carries the overrides.
11. **Tool texts.**
    - `THREAD_SETTINGS_UPDATED_TEXT`, `THREAD_ARCHIVED_TEXT` and `THREAD_RENAMED_TEXT` are one sentence each. §9.2 gives only their role, so the wording is the implementer's.
    - `TURN_SETTINGS_STATUS_TEXT` is the §9.2 text, verbatim.
    - The tool modules' `__all__` lists only classes.
12. **Resume tool.** `ResumeCodexGoalTool` resets every path in `CODEX_HOST_REJECTED_FIELDS[RESUME_CODEX_GOAL]` and `CODEX_HOST_GOAL_REJECTED_FIELDS` to a fresh record's value, so it follows the host's own tables.
13. **Tool headers.** The tool headers and the `CodexHostTools` docstring name `forget_codex_turns`, `delete_codex_thread` and the nine INV-42 functions, because none of them has a tool.

## 5. Gates

All gates ran at b5ffd64d, one at a time, using `venv-codex163`.

**Area suite:** `pytest -q tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py`

```
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
1 failed, 1293 passed, 3 skipped in 84.98s (0:01:24)
```

**Lint:** `lint/run.py`. These are the lines for the rules this slice touched, and the last line.

```
S009 IMPROVED 350 -> 346. Lower it with: python lint/run.py --rule S009 --update-baseline
S015 RATCHETED: 13 known finding(s). Inspect with: python lint/run.py --rule S015 --all
S025 IMPROVED 263 -> 261. Lower it with: python lint/run.py --rule S025 --update-baseline
S054 RATCHETED: 3 known finding(s). Inspect with: python lint/run.py --rule S054 --all
A007 RATCHETED: 255 known finding(s). Inspect with: python lint/run.py --rule A007 --all
SDK-LINT: PASS
```

**Semgrep:** `.semgrep/typed-mapping-boundary-policy.yml`, run through `semgrep-core`. It found 0 results and 0 errors on every changed `.py` file, including the two the rename touched (`vidbyte/lib/enums/codex.py` and `vidbyte/tools/builtins/codex/_base.py`).

**`PYTHONPATH=$(pwd) run_ci.py --stage source`,** run alone:

```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 6824 passed, 27 skipped in 153.20s (0:02:33) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-codex-host-first-class).
```

The one failure is inherited from the base branch. It asserts `len(main_members) == 120`, and this slice adds no FailureCode. The MCP stdio test that flaked in the first pass passed this time.

**`run_ci.py --stage package`,** run alone with no `PYTHONPATH`:

```
Successfully built vidbyte_sdk-0.3.0.tar.gz and vidbyte_sdk-0.3.0-py3-none-any.whl
...vidbyte_sdk-0.3.0-py3-none-any.whl: PASSED
...vidbyte_sdk-0.3.0.tar.gz: PASSED
No broken requirements found.
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

## 6. Tricky parts, for the next agent

- **A007's context rule.** A numeric literal within seven ancestor nodes of a name holding an operational token (`timeout`, `limit`, `token`, `char` and others) counts as a finding, even a literal `1` in `sequence + 1`.
  - Writing the constant out does not help.
  - Moving the arithmetic into a small helper method, away from the bound name, does.
- **S009 is a whole-file mypy ratchet.** openai-codex's notification payloads are wide unions, so one unnarrowed `.delta` produced 483 findings.
  - Use `isinstance` narrowing with a `TypeError` tail.
  - On raw mappings, use `RecordFieldConverter.require_instance`.
  - Narrow in the same condition, not in a later statement. `_resolve_handles` needed this.
- **S015 reads `__all__` literally.** A script that rewrote a long `__all__` turned the `# Memory providers` comment into a string entry. Check the diff of every `__all__` you regenerate.
- **openai-codex's `thread_read` always sends `includeTurns`.** Any test or fake that matches `thread/read` params must expect it (B-3).
- **Name-only security hits.** ruff S105 flags any name holding "token" or "password" that is assigned a string. Name enum members for what they are, not for the wire value (D-40).
- **The test support's `_enter` takes `name` as a positional-only parameter.** A stub that passes `name=` as a keyword needs that signature (B-4).
- **The semgrep-core JSON output starts with a "." progress line.** Parse it from the first `{`.
- **Test flakiness.** `test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` can fail under full-suite load (`stdin_write_failed`). It passes when its file runs alone, so re-run the stage if it flakes.

## 7. Open items

- **The inherited harness_threads failure** (`main_members == 120`) still makes `--stage source` exit 1. It predates this branch, and fixing it is outside §12.3.
- **Lint reports several IMPROVED rules:** A002, S001, S009, S010, S025, S061 and S063. Lowering their baselines means editing `lint/`, which S3 may not do. Someone allowed to edit `lint/` can lower them with `--update-baseline`.
- **The §17 row date.** The brief said `2026-10-19`, but the row is dated `2026-10-18`, the system date when the row was written.
- **§6.2 had no blank Proof cells.** Every AC row already names its test.
