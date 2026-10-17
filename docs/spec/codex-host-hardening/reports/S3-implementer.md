# S3 implementer report: codex-host-hardening (spec r4)

STATUS: DONE (first run BLOCKED; unblocked by the orchestrator at 13:30, see §7)
STAGE: S3 implementer
BRANCH: feat/codex-host-first-class (worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-codex-host-first-class`)
START: c8c5e128 (S2 tests written) · S2_HEAD: fadec47f · last code commit: 2f31b1fc · spec record: b09e10bd
PUSHED: yes, `git push -u origin feat/codex-host-first-class` · PR: https://github.com/cerredz/Vidbyte-SDK/pull/1181 (draft, base `ai/resolve-pr-1055-comments`)

Sections 2 to 4 describe the first, blocked run. Section 7 has the final results.

## 1. What was built

All 24 rows of spec §12.3 are implemented, in phase order P1 → P2 → P3 → P4, one or more commits per row, each citing its IDs. No test file, fixture or test config was touched (`git diff c8c5e128..HEAD -- tests` is empty). No file outside §12.3 changed: the branch diff is exactly the 24 §12.3 paths.

| §12.3 row | File | Commits |
|---|---|---|
| 1 | `vidbyte/lib/enums/codex.py` | ea3fad66 |
| 2 | `vidbyte/lib/enums/__init__.py` | b133485e |
| 3 | `vidbyte/lib/constants/codex_host.py` | 58ede6d8 |
| 4 | `vidbyte/lib/constants/codex.py` | 82210507 (values), 02581f1a (removal, with row 12) |
| 5 | `vidbyte/lib/dataclasses/codex_host.py` | d5036edb (P1), 9aaf47b5 (goal rule), 739eb299 (USER removal, with row 14) |
| 6 | `vidbyte/lib/dataclasses/codex_host_inputs.py` | 7c5af022 (P1), 9aaf47b5 (goal call) |
| 7 | `vidbyte/lib/dataclasses/codex.py` | 4658bf99 |
| 8 | `vidbyte/lib/errors/base.py` | 2643bc72 |
| 9 | `vidbyte/lib/util/exception_origin.py` (new) | 10d95af3 |
| 10 | `vidbyte/lib/util/__init__.py` | ebdcacd6 |
| 11 | `vidbyte/harnesses/native/codex/errors.py` | a20349d0 |
| 12 | `vidbyte/harnesses/native/codex/connection.py` | 02581f1a, 2f31b1fc (S008/S024 refactor) |
| 13 | `vidbyte/harnesses/native/codex/wire.py` | 02581f1a, 739eb299, 74837c68, 91cc7d4d |
| 14 | `vidbyte/harnesses/native/codex/preflight.py` | 739eb299 |
| 15 | `vidbyte/harnesses/native/codex/turns.py` | 67973d2b |
| 16 | `vidbyte/harnesses/native/codex/thread_helpers.py` | 74837c68 |
| 17 | `vidbyte/harnesses/native/codex/turn_events.py` (new) | 67973d2b |
| 18 | `vidbyte/harnesses/native/codex/reviews.py` (new) | 5dda8707 |
| 19 | `vidbyte/harnesses/native/codex/host.py` | 739eb299, 74837c68, 67973d2b, 5dda8707, 91cc7d4d |
| 20 | `vidbyte/harnesses/native/codex/skill_functions.py` | df06739b |
| 21 | `vidbyte/harnesses/native/codex/oneshot.py` | ba384f60 |
| 22 | `vidbyte/tools/builtins/codex/_base.py` | 61956356 |
| 23 | `pyproject.toml` | fd6404b4 |
| 24 | `vidbyte/lib/README.md` | 2b9a42a9 |

Budget (§8.4): 3 new files (reviews.py, turn_events.py, exception_origin.py), 13 new classes (exactly the §8.4 list), 0 dependencies, 9 config keys. File sizes: host.py 923 lines (under the 940 Ask-first line), every touched file under 950 except `vidbyte/lib/dataclasses/codex.py` (1,205 at base; this branch changes one value line and does not grow it).

## 2. Test results

Area suite (`tests/features/codex_host`, `tests/features/harness_threads`, `tests/test_codex_*.py`), run with openai-codex 0.163.0:

```
FAILED tests/features/codex_host/test_codex_host_approvals.py::CodexCloseHandlerTests::test_close_cancels_a_pending_handler_and_declines_a_late_request_for_a_turn_awaiting_cleanup
FAILED tests/features/codex_host/test_codex_host_function_rows.py::CodexForgetTurnsTests::test_forget_drops_ended_turns_refuses_a_busy_thread_and_sends_nothing
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
3 failed, 1022 passed, 3 skipped in 65.08s (0:01:05)
```

The failing count fell 69 → 64 → 57 → 46 → 39 → 34 → 15 → 7 → 3 across the P3/P4 commits, and no commit introduced a new failure (each run was diffed against the previous one with `comm`). None of the three remaining failures can be fixed in production code:

### 2.1 `CodexForgetTurnsTests` (test vs spec contradiction)

- `tests/features/codex_host/test_codex_host_function_rows.py:85` asserts `caught.exception.details.get("field") == "thread_id"`.
- The spec makes `forget_codex_turns` build #1178's `CodexThreadRef` (INV-22, D-33, §12.3 row 19: "with the record after the guard"). `CodexThreadRef.__post_init__` (`vidbyte/lib/dataclasses/codex_host_inputs.py:137`) calls `RecordFieldValidator.require_text(self.thread_id, f"{self.operation.value} thread_id", ...)`, and `vidbyte/lib/dataclasses/validation.py:47` sets `details={"field": field_name}`, so the value is `"forget_codex_turns thread_id"`, exactly as for the 7 other `CodexThreadRef` methods.
- The spec only requires the text to name `"<method> <field>"` and `details["field"]` to be set (§12.4 third bullet; AC-41). S2's own contract module says the same thing: `tests/features/codex_host/test_codex_host_hardening_contract.py:7` ("RecordFieldValidator puts the whole "<method> <field>" label in details["field"]") and `:110` ("bare or as "<method> <field>"").
- Every other assertion in this test passes (line 84 included); only line 85 fails.

### 2.2 `CodexCloseHandlerTests` (test asserts something no close can satisfy)

- `tests/features/codex_host/test_codex_host_approvals.py:463` asserts `(self.server.closed, self.server.reader_errors) == (1, [])` after `await closing`.
- The fake records every exception raised by the real SDK reader's `_read_message` (`tests/features/codex_host/codex_host_fakes.py:394-399`). On close, openai-codex's `CodexClient.close()` terminates the process, the fake closes stdout, and the reader's blocked `readline()` returns `""`, so `_read_message` raises `TransportClosedError("Codex process closed stdout. ...")` (`openai_codex/client.py:903-911`). This happens on every host close.
- Evidence, from a scratch probe outside the repo (`scratchpad/probe/test_probe_reader.py`): a plain open-then-close host records `[TransportClosedError('Codex process closed stdout. stderr_tail=')]`, both on this branch and on an extracted copy of the base commit c8c5e128.
- A scratch copy of the test with only line 463 reduced to `self.server.closed == 1` passes, including line 464 (exactly one `turn/interrupt`). Every AC-38 behaviour holds: the pending handler call is cancelled and its request answered `{"decision": "decline"}`, the late request is declined without the handler, and its fallback reason is `closing`.

### 2.3 `test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes` (pre-existing)

- The test reads `vidbyte/lib/enums/failure.py` at `git merge-base origin/main HEAD` (6f5a7310, the #1055 merge) and asserts it has 120 members. It has 167. This branch does not touch `failure.py`, so the result is the same at c8c5e128 in this worktree. It passes only where `origin/main` is missing (in an extracted copy without `.git`, it returns early). It is stale against the current main, and it belongs to neither S2 nor S3.

## 3. Lint and gate

Full lint (`lint/run.py` inside `scripts/run_ci.py --stage source`), first run: `S008 bounded-function-complexity 21 vs 19 REGRESSED` and `S024 maximum-control-flow-nesting 27 vs 25 REGRESSED`, both from `CodexServerRequestRouter.handle` (row 12, P2). Commit 2f31b1fc fixes this without changing behaviour: the close check, the parse and the scheduling stay under one lock and one `try` with the single `finally` (INV-17). On the rerun, every rule is at or under its baseline, ending in `SDK-LINT: PASS`.

`PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source` at 2f31b1fc: lint, compileall and the three check scripts all pass, and pytest fails on exactly the three tests in §2. The final lines:

```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
FAILED tests/features/codex_host/test_codex_host_approvals.py::CodexCloseHandlerTests::test_close_cancels_a_pending_handler_and_declines_a_late_request_for_a_turn_awaiting_cleanup
FAILED tests/features/codex_host/test_codex_host_function_rows.py::CodexForgetTurnsTests::test_forget_drops_ended_turns_refuses_a_busy_thread_and_sends_nothing
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 3 failed, 6553 passed, 27 skipped in 116.17s (0:01:56) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-codex-host-first-class).
```

`"$V" scripts/run_ci.py --stage package` (no PYTHONPATH; builds, runs twine, and installs into a throwaway temp venv) passes:

```
> ...vidbyte-sdk-install-ug8habrm\venv\Scripts\python.exe -m pip check
No broken requirements found.
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
```

Focused rules after each phase: A001 A002 A003 A005 A006 A007 A008 C021 S012 S015 S017 S019 S043 S044 S051 S058 S060 S064, each ending `SDK-LINT: PASS`.

Semgrep (`.semgrep/typed-mapping-boundary-policy.yml`): the global `semgrep` CLI is broken in this environment (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`, because mcp 2.x is installed globally, and pip is forbidden). I ran the same policy with the bundled `semgrep-core.exe -rules .semgrep/typed-mapping-boundary-policy.yml -lang python -json <file>` on each of the 23 changed `.py` files: 0 results and 0 errors for each one. A scratch file holding the forbidden pattern gave 1 result, so the run does detect violations.

Direct ruff (not part of the gate): BLE001 for `except Exception` at three new sites that the spec requires (turn_events.py ×2, `_base.py` row 22); the rest are pre-existing. PYI034 on host.py is pre-existing.

## 4. Why nothing was pushed

The brief says to run the full gate before pushing, and the gate's pytest step fails on the three tests above. Two of them need S2 to change a test file, which S3 may not do; the third is a pre-existing environmental failure. All work is committed locally on `feat/codex-host-first-class`. When the orchestrator unblocks, the remaining steps are mechanical:

1. `git push -u origin feat/codex-host-first-class`;
2. `gh pr create --repo cerredz/Vidbyte-SDK --base ai/resolve-pr-1055-comments --head feat/codex-host-first-class --draft --title "[WIP] feat: CodexHost production hardening and first-class Codex features" --body-file <scratchpad>/s3-placeholder-pr-body.md`;
3. update the spec frontmatter (`pr:`, `status: implemented`), the AC-40 proof SHA, the §17 row and the deviations below, then commit and push.

## 5. Implementation deviations (for §17)

- Row 13's `readiness`, `fork_point` and `stored_turn` changes landed in P3 (739eb299, 74837c68), each with its caller, rather than in P2, so no commit left an unused or uncalled helper.
- `_reject_bad_list_limit` is shared in `codex_host_inputs.py` (P1) by the records that take a `limit`.
- `_reject_goal_fields(request)` takes no `owner` argument: `CODEX_HOST_GOAL_FIELD_MESSAGE` has only a `{name}` slot.
- The tier problem's "any model" text is a call-site literal in `preflight.py`, following §9.2's slot text; no constant was added.
- Interim commit 739eb299 passed `approvals_answered=False` to `CodexPreflight`; 91cc7d4d wires `approvals_answered=handler is not None`.
- Row 19 (host.py) is split across 739eb299, 74837c68, 67973d2b, 5dda8707 and 91cc7d4d. The handler wiring and the docstrings landed last, after the review and event moves shrank the file, which kept host.py under 940 lines at every commit.
- Row 12, 2f31b1fc: `CodexServerRequestRouter._schedule(coroutine)` holds `run_coroutine_threadsafe` plus the pending add, so `handle` stays within S008 and S024. A coroutine that was never scheduled is still closed in `handle`'s single `finally`.
- Row 22: the code is a local `code = FailureCode.CODEX_API_ERROR.value` rather than a new module-level alias.
- AC-40 says the C021 run ends `AGENT-LINT: PASS`; the runner actually prints `SDK-LINT: PASS`.
- `CodexHostOperation.VALIDATE_SPAWN_REQUEST` is no longer referenced after the USER removal. It is left in place (removing an enum member is a public contract change).

## 6. Niche facts

- `lint/run.py` is ratcheted per rule. The focused rules can all pass while the full run fails on S008/S024 (complexity ≤10, branches ≤12, nesting ≤3, where `try`, `if` and `with` each add a level and `elif` does not). Run the full `lint/run.py` before any push.
- Ruff C901 here counts `if`, `elif` and `except`, not boolean operators or conditional expressions.
- The fake app-server records the SDK reader's `TransportClosedError` on every close, so `reader_errors` is only meaningful before close.
- `harness_threads` surface tests read `origin/main` through git, so their results depend on the checkout.
- The global `semgrep` is broken (mcp 2.x); use `.../site-packages/semgrep/bin/semgrep-core.exe` with one target per call.
- Files are LF and git warns about CRLF on add; this is harmless.

## 7. Unblocked run (after the S2 correction at fadec47f)

The orchestrator granted both test corrections and accepted the `harness_threads` surface failure as inherited (pipeline.md, 13:30). In fadec47f, S2 changed `function_rows.py:85` to `endswith("thread_id")` and `approvals.py:463` to `closed == 1` plus "every reader error is the SDK's close-time `TransportClosedError`". No code changed for this. `git diff fadec47f..HEAD -- tests` is empty.

Area suite (`PYTHONPATH=$(pwd) "$V" -m pytest -q -p no:cacheprovider tests/features/codex_host tests/features/harness_threads tests/test_codex_*.py`):

```
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
1 failed, 1024 passed, 3 skipped in 63.48s (0:01:03)
```

Full lint (`PYTHONPATH=$(pwd) "$V" lint/run.py`, exit 0). `lint/run.py` does not invoke semgrep; its only mention is a comment in `lint/core/discovery.py`. Its pass line is `SDK-LINT: PASS`, and no `AGENT-LINT` string exists anywhere under `lint/`:

```
S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all

SDK-LINT: PASS
EXIT=0
```

Gate source stage (`PYTHONPATH=$(pwd) "$V" scripts/run_ci.py --stage source`). Only the one inherited failure remains:

```
SDK-LINT: PASS
context write-path integrity: ok
context primitive introductions: ok
reasoning trace contracts: ok (182 tools, 55 shapes)
FAILED tests/features/harness_threads/test_harness_threads_surface.py::test_failure_codes_keep_main_and_append_exactly_the_28_harness_codes
=========== 1 failed, 6555 passed, 27 skipped in 114.21s (0:01:54) ============
CI failed: Command failed with exit code 1: ...python.exe -m pytest (cwd=...vidbyte-sdk-codex-host-first-class)
```

Gate package stage (`"$V" scripts/run_ci.py --stage package`, no PYTHONPATH; it installs only into its own temp venv):

```
No broken requirements found.
> ...vidbyte-sdk-install-udxg9cde\venv\Scripts\python.exe -c from importlib.metadata import entry_points, version; import vidbyte; ...
Installed vidbyte-sdk 0.3.0 passed smoke checks.
CI passed.
EXIT=0
```

Semgrep evidence. The global CLI fails at import (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`, because mcp 2.x is installed globally). Nothing was installed or repaired. The exact command, once per changed file:

```
SC=C:/Users/422mi/AppData/Local/Programs/Python/Python311/Lib/site-packages/semgrep/bin/semgrep-core.exe
"$SC" -rules .semgrep/typed-mapping-boundary-policy.yml -lang python -json <file>
```

Result: `0 results 0 errors` on each of the 23 changed `vidbyte/**/*.py` files. A positive control (`scratchpad/semprobe/bad.py`, an `Any` parameter with a non-Mapping fallback) gave `1 results 0 errors`, so the run does detect violations.

Publish:

```
$ git push -u origin feat/codex-host-first-class
 * [new branch]        feat/codex-host-first-class -> feat/codex-host-first-class
branch 'feat/codex-host-first-class' set up to track 'origin/feat/codex-host-first-class'.
$ gh pr create --repo cerredz/Vidbyte-SDK --base ai/resolve-pr-1055-comments --head feat/codex-host-first-class --draft --title "[WIP] feat: CodexHost production hardening and first-class Codex features" --body-file <scratchpad>/s3-placeholder-pr-body.md
https://github.com/cerredz/Vidbyte-SDK/pull/1181
$ gh pr view 1181 --json isDraft,baseRefName,headRefName,state
{"baseRefName":"ai/resolve-pr-1055-comments","headRefName":"feat/codex-host-first-class","isDraft":true,"number":1181,"state":"OPEN",...}
```

Spec record in b09e10bd:
- the frontmatter has `pr: https://github.com/cerredz/Vidbyte-SDK/pull/1181` and `status: implemented`;
- the AC-40 command proof says it "ends `SDK-LINT: PASS` at `2f31b1fc`";
- §17 gains the row `r4 | 2026-10-17 | S3 implement | …` and a "### Implementation deviations (S3)" list (§5 above, plus the semgrep note).

All of it was pushed again with `git push -u origin feat/codex-host-first-class`. Repository workflows are `workflow_dispatch`-only, so the pushes triggered nothing.
