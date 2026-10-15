# S5 Repair report, iteration 2 of 8: harness-thread-functions

Worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-harness-thread-functions`, branch `feat/native-grok-opencode-meta-hosts`, PR https://github.com/cerredz/Vidbyte-SDK/pull/1036. Started at `b3201a2c` (origin at `bb7d78bb`). S2_HEAD `b737f57f`; `git diff b737f57f..HEAD -- tests` is empty.

## Status

DONE. R-27, R-28, R-29 and R-30 are fixed, every local gate is green, and GitHub CI is 4/4 on `53d9f45a`, the last code commit; later commits change docs only. The first remote run (on `4dc11f2c`) failed the POSIX half of R-27's test, which no win32 run can exercise. The follow-up fix `53d9f45a` closes it.

## Starting point

The pack at `b3201a2c` gave `12 failed, 424 passed, 2 skipped` (orchestrator). My own `-k` run reproduced all 12: R-28 ×2, R-27 ×1, R-29 ×8 (4 prose prompts that must run, plus 4 dense prompts that must name the new constant), and R-30 ×1. The verify-log's iteration 1 entry exhausted no hypothesis that these findings need. R-11's `process_exited` design, R-4's `find_program` and R-10's shielded preparation were kept as they are.

## Per-finding actions

**R-28 (Blocker), `7ec71ec7`.** `ProcessStopper._start_taskkill` now launches `os.path.join(SystemRoot or "C:\Windows", "System32", "taskkill.exe")`, read at call time. A root that is not absolute returns `None`, so the leader-kill fallback runs, and `OSError` still returns `None`. New constants: `NATIVE_SYSTEM_ROOT_VARIABLE`, `NATIVE_WINDOWS_DEFAULT_SYSTEM_ROOT`, `NATIVE_TASKKILL_PATH_PARTS`; `NATIVE_TASKKILL_ARGUMENTS` became `("/T", "/F", "/PID")`. The runner header's KNOWN EDGE CASES says the same; the docstring avoids backslashes, because `\S` and `\W` are invalid escapes in a normal string. Evidence:
- Both `test_tree_stop_never_runs_a_taskkill_from_the_current_folder` cases pass, with the 34 other timeout, cancel and tree tests.
- `rr2_stop_tree.py "$(pwd)" head realpath|sandboxpath`, run under `env -u NoDefaultCurrentDirectoryInExePath`, gives `planted taskkill.exe started=0 (XAI_API_KEY present in its env: []); leader rc=1; grandchild alive after stop=False; stop took 0.1s` on 3.11 (both PATH modes) and on 3.13. Before the fix it gave `started=1`.
- `s5-repair-2/r28_root_probe.py` gives `unset: taskkill started=True`, `relative: taskkill started=False`, `real: taskkill started=True`, and `leader rc after stop=1` in all three cases.
- Other bare names: `git diff --name-only origin/main...HEAD -- vidbyte | xargs grep` for process launches finds only `runner.py`'s `loop.subprocess_exec`, which `CliRunner.find_program` feeds on win32 (`hostkit/launcher.py:41` falls back to the bare name, but `run` looks it up again and refuses it), and the taskkill launch. The verifier's claim holds.

**R-27 (Major), `4a352946` and `53d9f45a`.**
- `4a352946` is the prescribed fix. `CliRunner.run` now runs `if await self._finish_readers(readers): await ProcessStopper.stop_tree(...)` inside the guarded `try`, after the `asyncio.timeout` block, and the `TimeoutError` branch calls `_finish_readers` after its `stop_tree`. On win32 that made the test pass on 3.11 and 3.13, and `rr1_cancel_window.py` gives `CancelledError after 0.09s; stop_tree calls=1; reader tasks pending=0` on both versions, with the plain, held-pipe and timeout rows unchanged.
- GitHub CI on `4dc11f2c` then failed the test's POSIX-only assertion on 3.11 and 3.12: `AssertionError: INV-9 / R-27: the grandchild outlived the cancelled run`. `process_alive` counts `Z` and `X` as dead, so the grandchild was still running.
- Root cause: once the leader has been reaped, `stop_tree`'s only POSIX wait, `_bounded_wait(process)`, returns at once, so the stop ends microseconds after `killpg(SIGKILL)`. A KILL takes effect only when the kernel schedules the target, and a Python process's `do_exit` unmaps its address space before it becomes a zombie. The race is lost reliably on a CI runner.
- WSL1 cannot show this. I ran a standalone probe there (`MuseUbuntu1`, Python 3.12.3, `s5-repair-2/r27_posix_probe.py`; no pytest, path-only package stubs; only `python3` was run, never `muse`). Before the follow-up it gives `grandchild alive at CancelledError=0; states=['Z']`, because WSL1's kill finishes the exit synchronously. WSL2 cannot start: "virtualization is not enabled".
- `53d9f45a` adds `ProcessStopper._wait_group_gone(pid, seconds)`. It is guarded on win32 for mypy, as `_signal_group` is. It polls `os.killpg(pid, NATIVE_PROCESS_GROUP_PROBE_SIGNAL)` every `NATIVE_PROCESS_GROUP_POLL_SECONDS` (0.01) under `asyncio.timeout(seconds)`, and stops at `ProcessLookupError` or `PermissionError`. `stop_tree` calls it right after the group SIGKILL.
- After `53d9f45a`: the WSL1 probe gives `states=['gone']; max propagate=0.011s`, the win32 pack is unchanged (`436 passed`), and GitHub CI is 4/4.
- This also tightens INV-8: a timeout whose leader had already exited could likewise return while a descendant still ran.

**R-29 (Major), `5ee16c7d`.**
- New constant `NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS = 30000`. Its comment, in 72-column lines, gives the measured 32,766-unit limit and the 2,766-unit margin against the worst measured rest of line (608 units).
- `NativeThreadRequest.__post_init__` passes it as `max_units`. The `@intent argv-prompt-fits-the-windows-command-line` text and the record header say the ceiling sits above the character cap and that WinError 206 still maps to `launch_failed`.
- The 24,000-character cap is unchanged. The validator message already reads `prompt must take at most 30000 UTF-16 code units once quoted for the Windows command line; got 40000.`, which gives the order the test's `find_in_order` checks, so `validation.py` did not change.
- `rr3_cmdline.py` gives `24,000 chars of prose: … quoted_units=24002 -> accepted` and `23,999 chars, one space … 24001 -> accepted` for Grok and Muse, and `20,000 double quotes|astral chars … 40000 -> refused: … at most 30000 …`. The OS limit line still reads `32766 … one more -> launched=False (32767, 206)`.

**R-30 (Minor), `5f016773`.**
- `MuseThreadRun.execute`'s `except asyncio.CancelledError` now awaits `asyncio.shield(asyncio.ensure_future(MuseThreadRun._discard(preparing)))`, then `raise`. The shield sits in `execute`, not inside `_discard`, which keeps the call chain one level deep (AGENTS.md principle 1).
- `rr4_double_cancel.py "$(pwd)" head` on 3.11 and 3.13 gives `cancels=2: CancelledError; temp folders when CancelledError arrived=['tmp…']; 1.5s after the copy finished=[]`, and the `cancels=1` row is unchanged.
- Both preparing tests pass on 3.11 and 3.13.

**Docs.** `4dc11f2c` and the final docs commit update spec §17 (revision row, deviations 18, 20 and 21, new 23 and 24) and set R-27 to R-30 in `review.md` to `fixed @…`. R-27 reads `fixed @4a352946, 53d9f45a (POSIX group wait)`.

## Hypotheses tried and rejected

- R-28 via `CliRunner.find_program("taskkill")`: not tried, because the verifier had measured that it fails 9 tree-stop tests (the pack's sandbox `PATH` is one empty folder), and a real caller with a trimmed `PATH` would lose the stop.
- R-27 by the prescribed move alone: it fixes win32 but not POSIX, as the first remote run proved. The cause was the missing group wait, not the move.
- R-27 POSIX, approaches weighed: (a) poll `killpg(pid, 0)`, bounded by the grace — chosen. (b) Wait for the readers' natural EOF before closing the pipes — rejected: it covers only descendants that hold the pipes, and `exit_files` comes before `exit_notify`, so a window stays. (c) Scan `/proc` for the group's members — rejected: Linux-only and O(processes).
- The first version of (a) used a literal `0`, and lint A007 regressed (`256 finding(s), allowance 255`: "operational literal 0: operational context contains 'timeout'"). The fix is a named constant, not a baseline change.
- R-30, the loop that suppresses later cancels until the cleanup is done: not built. It would hold INV-9's order for any number of cancels, but it would leave a hung skill copy (for example on a stalled network share) with no way to cancel it. The review marks this as the owner's call, so I recorded it in deviation 20.

## Test changes proposed

None. No test contradicts the spec.

## Findings I believe are wrong

None.

## Gates (final lines)

| Gate | Result | Final lines |
|---|---|---|
| pack, 3.11 (`53d9f45a`) | PASS | `436 passed, 2 skipped in 48.45s` |
| pack, 3.13 | PASS | at `5f016773`: `436 passed, 2 skipped in 51.17s`; R-27 test at `53d9f45a`: `1 passed in 1.34s` |
| whole suite | PASS | `5609 passed, 16 skipped in 97.94s (0:01:37)` |
| `python lint/run.py` | PASS | `S009 350 350 RATCHETED`, `A007 255 255 RATCHETED`, `S064 RATCHETED: 4 known finding(s). Inspect with: python lint/run.py --rule S064 --all`, `SDK-LINT: PASS` |
| I001 over changed files | PASS (main's only) | `vidbyte\lib\errors\__init__.py:22:1: I001 [*] Import block is un-sorted or un-formatted` / `Found 1 error.` / `[*] 1 fixable with the --fix option.` (main's copy: `Found 1 error.`) |
| comment width | PASS | `vidbyte/lib/enums/failure.py now=6 main=6`, `vidbyte/lib/errors/base.py now=9 main=9`; every other changed file 0 |
| run_ci source | PASS | `SDK-LINT: PASS` / `================= 5609 passed, 16 skipped in 93.12s (0:01:33) =================` / `CI passed.` |
| run_ci package | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.1 passed smoke checks.` / `CI passed.` |
| Semgrep test | PASS | `1/1: ✓ All tests passed` / `No tests for fixes found.` |
| Semgrep scan | PASS | `Ran 1 rule on 958 files: 0 findings.` (exit 0) |
| remote, `4dc11f2c` | FAIL | runs 38783357799 and 38783362825: `Package skipped`, `Static policy success`, `Source / Python 3.12 failure`, `Source / Python 3.11 failure`. 3.12: `1 failed, 5568 passed, 56 skipped, 19 warnings`; 3.11: `2 failed, 5567 passed, 56 skipped` (the second failure is `test_coding_agent_environment.py::test_real_bash_reports_its_version_and_git`, "bash did not finish within 15 seconds", in files this branch does not touch) |
| remote, `53d9f45a` | PASS 4/4 | runs 38785332849 and 38785337323: `Package success` / `Static policy success` / `Source / Python 3.11 success` (`5569 passed, 56 skipped in 92.78s`, `CI passed.`) / `Source / Python 3.12 success` (`5569 passed, 56 skipped, 19 warnings in 104.79s`, `CI passed.`) |

## Open items

None blocking. Notes for the orchestrator:
- R-30's trade-off: under a second cancel, the removal ends in the background after `CancelledError`, so INV-9's literal order holds for the first cancel only. Deviation 20 records it for the owner.
- `_wait_group_gone` waits until the group is reaped, not just dead. Where a zombie is never reaped (Python as PID 1 in a container without an init), a POSIX stop takes up to one more `NATIVE_KILL_WAIT_SECONDS`. It is bounded, and the runner header and deviation 24 record it.
- The 3.11 `coding_agent` bash-probe failure did not recur on the second run. If it does, it is a flake: `gh run rerun <id> --failed`.
- R-32 (an unshielded WSL reap) is the same root cause as R-27 and R-30 in S3 code, and stays a follow-up.
