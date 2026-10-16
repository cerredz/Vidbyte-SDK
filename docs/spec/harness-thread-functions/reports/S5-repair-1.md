# S5 Repair report, iteration 1 of 8: harness-thread-functions

Start HEAD `b21d17f4` on `feat/native-grok-opencode-meta-hosts` (origin at `01b20447`, origin/main `179d8adc`, an ancestor of HEAD, so no catch-up merge was needed). S2_HEAD `91625f11`; `git diff 91625f11..HEAD -- tests` is empty. Last fix commit `b8305b44`; spec and review status commit `de8d1592`.

## Status

**DONE.** All 14 findings in scope are fixed, one commit each (`74114bd1`…`b8305b44`), with no test, lint rule, baseline or config changed. The feature pack, lint, import order, comment width, both run_ci stages, Semgrep and the four remote checks on `de8d1592` are green.

## Starting point

The feature pack started at `33 failed, 395 passed, 2 skipped in 76.18s`. The 33 failures were the S4 regression tests for the confirmed findings, by file: launcher 9, errors 9, process_bounds 8, arguments 4, skills 2, runner 1. The review had 11 confirmed findings (R-1 to R-11) plus three tagged `trivial` (R-15, R-16, R-17). Findings tagged `follow-up` (R-12, R-13, R-14, R-18 to R-26) were left as they are.

## Per-finding actions

| ID | Commit | What changed | Evidence after the fix |
|---|---|---|---|
| R-1 | `b8305b44` | Rewrapped the five new comment lines over 72 columns (grok/wire.py, hostkit/errors.py, constants x2, dataclasses/native_threads.py). The 124 test lines were already wrapped by S4 in `1f6fc22e`. | Width check over every changed file under `vidbyte/` lists only `vidbyte/lib/errors/base.py` (9) and `vidbyte/lib/enums/failure.py` (6), the same counts as origin/main. |
| R-2 | `74114bd1` | New `ShellFlag(StrEnum)` with `READ_STDIN = "-s"`; the reap passes `operands=(ShellFlag.READ_STDIN, mark)`; `MUSE_REAP_STDIN_SWITCH` deleted. | WSL and launcher tests green; lint PASS. |
| R-3 | `3466a6fc` | `failure`, `from_configuration_error` and `from_launch_failure` scrub the workspace, thread id and searched text themselves; `_context_sentences` and `_observed_sentences` only format. | Call-depth scan of the changed modules finds only main's `FailureCode.from_exception` chain. |
| R-4 | `f64ba4b8` | `CliRunner.find_program` walks only absolute PATH folders (PATHEXT on win32), never the current folder. `NativeLauncher.resolve`, `MuseLauncher.resolve` and `CliRunner.run` (win32) use it; `launch` returns `NOT_FOUND` for an unfound bare name. | `exp8_cwd_lookup.py` and `exp8b_cwd_grok.py`: the planted `grok.exe`, `opencode.exe` and `wsl.exe` never ran. 9 launcher tests green. |
| R-5 | `efae78a5` | `CliRunner.json_objects`, `RecordFieldValidator.accepts_text` and `NativeErrorFactory.wrong_thread` (with `NATIVE_WRONG_THREAD_DETAILS`) replace the duplicated JSONL loops and thread-id checks. Muse keeps its exact comparisons (EC-45). | Pack green; lint PASS, S009 350/350. |
| R-6 | `bdc8cd7a` | The 8 timeout and output-cap `failure` calls pass `vendor_text=outcome.stderr`. | `exp10_timeout_stderr.py` now shows `vendor_message`; process_bounds tests green. |
| R-7 | `cdf4efde` | `from_unexpected(exc, request)` adds the workspace and thread sentences and `thread_id=request.thread_id`; all three call sites pass the request. | Probe E1: `thread_id 'abc123'`, workspace and thread named in the message. |
| R-8 | `2e8ae979` | `RecordFieldValidator.require_command_line_units` refuses, on win32, a Grok or Muse prompt whose `list2cmdline` form passes `NATIVE_ARGV_PROMPT_MAX_CHARS` UTF-16 units; `launch` maps WinError 206 to `OS_ERROR` (`launch_failed`, not `not_installed`). | Arguments tests green. Behavior change: a 15,000-character backslash and quote mix (30,001 quoted units) that ran before is now refused on Windows. |
| R-9 | `69c3f9a5` | `NativeSkillFolders.remove` restores the owner's write bit (and a folder's search bit) on the copy, skipping links, then removes it; used by `replace` and both Muse removals. | `exp5_readonly.py`: calls 2 and 3 succeed. Skills tests green. |
| R-10 | `9e09b9b1` | Muse prepares its config folder in a shielded task; on cancel, `MuseThreadRun._discard` waits for it, removes the folder, then re-raises. | `exp2_muse_cancel.py` and probe E3: no temp folder left. |
| R-11 | `1583ee8c` | `CliExitProtocol` sets an event in `process_exited`; `run` waits for that, gives the readers one kill wait, and stops the tree if a reader is still open. | `exp1b.py` now returns `NativeThreadResult(thread_id='abc123', text='done')` instead of `grok.timed_out`. Checked on Python 3.11 and 3.13 (no 3.12 locally; the remote Source / Python 3.12 job covers it). As the review notes, on Windows the grandchild still survives because `taskkill /T` cannot reach it once the leader has exited (runner KNOWN EDGE CASES). |
| R-15 | `d8e838bb` | `NATIVE_VENDOR_TEXT_SENTENCE = 'The vendor printed: "{vendor_text}".'` | Errors tests green. |
| R-16 | `250692ad` | `GROK_HOME_UNKNOWN_DETAIL` ends "; set HOME (POSIX) or USERPROFILE (Windows) for this process." | Credentials tests green. |
| R-17 | `17650ceb` | The validation.py and dataclasses/native_threads.py headers now match the code. | Read-through. |

No test was changed, and no change to a test is proposed. No finding is disputed.

## Hypotheses tried and rejected

- R-5: a raising helper inside `NativeErrorFactory` would have recreated the two-level call chain R-3 removes; cross-harness imports and new classes were out of bounds; an `is_thread_id` method on the validator would have tied the canonical validator to the feature more tightly (R-22).
- R-4: adding `PATH` and `PATHEXT` to `NativeEnvironmentVariable` was dropped because the surface test pins its members, so they are plain constants.
- R-11: `Process.wait()` cannot be the exit signal, because on Python 3.12+ it resolves only after every pipe closes; the signal comes from `process_exited`, which both 3.11 and 3.13 call at the exit.

## Spec deviations recorded

Spec §17 gained the row `r4 | 2026-10-15 | S5 repair 1` and deviations 13 to 22: the `ShellFlag` enum, `from_unexpected(exc, request)`, `find_program` replacing `shutil.which` (and `launch` gaining `program`), the shared reading helpers, stderr on timeouts and caps, the quoted-prompt rule and WinError 206 mapping, `NativeSkillFolders.remove`, `MuseThreadRun._discard`, `CliExitProtocol` (and `launch` gaining `exited`), and the two trivial texts. New constants: `NATIVE_PATH_VARIABLE`, `NATIVE_PATHEXT_VARIABLE`, `NATIVE_WINDOWS_DEFAULT_PATHEXT`, `NATIVE_WINDOWS_COMMAND_LINE_ENCODING`, `NATIVE_UTF16_UNIT_BYTES`, `NATIVE_COMMAND_LINE_TOO_LONG_WINERROR`, `NATIVE_PROCESS_STREAM_LIMIT_BYTES`, `NATIVE_WRONG_THREAD_DETAILS`. No file was added: the branch still adds 24 Python files under `vidbyte/` against origin/main, as at the start.

## Gates

| Gate | Command | Result | Final lines |
|---|---|---|---|
| new tests | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` | PASS (was 33 failed) | `428 passed, 2 skipped in 47.03s` (the 2 skips are platform skips, e.g. "Muse is looked up on PATH only outside win32 (EC-29)") |
| whole suite | `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider` | PASS on the run_ci re-run; the standalone run hit the known flake | standalone: `FAILED tests/test_mcp_stdio_transport.py::McpStdioTransportHardeningTests::test_cancelled_waiter_does_not_break_transport` / `1 failed, 5600 passed, 16 skipped, 1 warning in 97.74s`. Alone afterwards: failed, failed, passed, then 5 of 5 passed. The run_ci source re-run below runs the same `python -m pytest`: `5601 passed, 16 skipped in 92.72s` |
| custom lint | `python lint/run.py` | PASS | `S009 RATCHETED: 350 known finding(s)` · `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all` · `SDK-LINT: PASS` (IMPROVED, not rebaselined: A002 703→585, C011 2→1, C012 24→23, S001 59→56, S010 5→0, S025 263→261, S061 6→5) |
| import order (I001) | `python -m ruff check vidbyte --config lint/ruff.toml --select I001 --no-cache` | PASS (no new finding) | Over the branch's changed files: `vidbyte\lib\errors\__init__.py:22:1: I001 [*] Import block is un-sorted or un-formatted` / `Found 1 error.`, which origin/main's copy of that file also gives (`Found 1 error.`); S051 `259 259 RATCHETED` |
| comment width | `awk 'length($0) > 72' <file> \| grep -E '^\s*#'` over every changed `vidbyte/` file | PASS | only `vidbyte/lib/enums/failure.py now=6 main=6` and `vidbyte/lib/errors/base.py now=9 main=9` (unchanged from main) |
| full gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS (2nd run) | 1st run: `1 failed, 5600 passed, 16 skipped` (same MCP flake) / `CI failed: Command failed with exit code 1: ... -m pytest`. 2nd run: `SDK-LINT: PASS` ... `================= 5601 passed, 16 skipped in 92.72s (0:01:32) =================` / `CI passed.` |
| full gate, package | `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Semgrep test | `semgrep --test --config .semgrep/typed-mapping-boundary-policy.yml .semgrep/typed-mapping-boundary-policy.py` (semgrep venv, `PYTHONUTF8=1`) | PASS | `1/1: ✓ All tests passed` / `No tests for fixes found.` |
| Semgrep scan | `semgrep scan --error --config .semgrep/typed-mapping-boundary-policy.yml vidbyte` | PASS | `Ran 1 rule on 958 files: 0 findings.` (exit 0) |
| remote checks | `gh workflow run ci.yml` (run 38771195576) and `static-policy.yml` (run 38771198811) on `de8d1592`, read via `gh api repos/cerredz/Vidbyte-SDK/commits/de8d1592.../check-runs` | PASS 4/4 | `Package success` · `Static policy success` · `Source / Python 3.11 success` · `Source / Python 3.12 success` |

The MCP test is a timing race in a file this branch does not touch (`vidbyte/tools/mcp/transport.py` and its test are identical to origin/main): it cancels the first request after 50 ms, so when starting the child takes longer the first line is never written and the second request waits out its 5 s timeout. An origin/main export passed it 5 of 5 times, and the branch passed it 5 of 5 times once the machine was idle.

## Open items

None. All gates are green and no confirmed finding is open. Follow-ups R-12 to R-14 and R-18 to R-26 are untouched, as tagged.
