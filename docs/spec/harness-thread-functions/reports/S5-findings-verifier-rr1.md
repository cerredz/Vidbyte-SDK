# S4 findings verifier, re-review round 1: harness thread functions

Scope: the four findings of `reports/S5-rereview.md` (R-RR1 to R-RR4) against the repair diff `d5581a24..72671402 -- vidbyte` (code last changed at `bb7d78bb`). Worktree HEAD `72671402`, tree clean before and after; only `review.md` and this report were written. No vendor CLI ran: every child was a python stand-in (the pack's `fake_harness.py`, or `python -c`), with a dummy key.

`<scratch>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4ff2472d-322f-4998-ab71-29f9489aa59a/scratchpad`. My probes are in `<scratch>/s5-verifier-rr1/`.

## Mapping

| Re-review | Result | Severity (re-review → verified) | review.md row |
|---|---|---|---|
| R-RR1 post-exit cancel hole | CONFIRMED | Major → Major | R-27 |
| R-RR2 bare `taskkill` | CONFIRMED | Major → **Blocker** | R-28 |
| R-RR3 prompt cap counted in quoted units | CONFIRMED | Minor → **Major** | R-29 |
| R-RR4 double cancel leaves the Muse temp folder | CONFIRMED | Minor → Minor | R-30 |
| [verifier] R-4 tests cannot fail on 3.12+ with the variable set | CONFIRMED | Minor (test only) | R-31 (Minor table, do with R-28's test) |
| [verifier] Muse WSL reap can be cancelled | code reading | Minor follow-up | R-32 (Minor table) |

Nothing was refuted or downgraded. Two severities went up; the reasons are under each finding. The confirmed heading count went from 11 to 15. I did not change the Verdict line or any existing row. The Verdict line still describes the S4 state, so the orchestrator may want to refresh it.

## R-RR1 → R-27 (Major): cancel inside the post-exit reader wait

**Code.** At `vidbyte/lib/process/runner.py:180-198` the `try` covers `_feed_stdin` and `exited.wait()` inside `asyncio.timeout`. Its `except asyncio.CancelledError` stops the tree, finishes the readers and re-raises. The post-exit step at `:199-205` (`if await self._finish_readers(readers) and not timed_out: await ProcessStopper.stop_tree(...)`) sits after the `try`. A cancel during `_finish_readers`'s `asyncio.wait(readers, timeout=NATIVE_KILL_WAIT_SECONDS)` interrupts that wait. The reader tasks are not cancelled, `stop_tree` is skipped, and `CancelledError` leaves `run`. Before the repair, this wait was `await asyncio.wait(readers)` inside the guarded `try` (`git diff d5581a24..72671402 -- vidbyte/lib/process/runner.py`).

**My probe** (`rr1_cancel_window.py`). It drives `CliRunner.run` directly. The leader is `python -c` that starts a grandchild on the same pipes, prints, and exits. The kill wait is 3 s, and the cancel comes 0.3 s after `CliExitProtocol.process_exited`. A spy counts `stop_tree` calls. `FixedRunner` is a scratch subclass with the proposed fix; the source was not touched.

```
python 3.11.0 win32
[HEAD 72671402] cancel 0.3s after leader exit (kill wait 3.0s): CancelledError after 0.00s; stop_tree calls=0; reader tasks pending=2
[proposed fix] cancel 0.3s after leader exit (kill wait 3.0s): CancelledError after 0.08s; stop_tree calls=1; reader tasks pending=0
[HEAD 72671402] plain: exit=0 stdout='answer' timed_out=False stop_tree calls=0
[HEAD 72671402] grandchild holds pipes: stdout tail='answer' timed_out=False in 1.1s stop_tree calls=1
[HEAD 72671402] timeout: timed_out=True stdout='partial' stop_tree calls=1
[proposed fix] plain: exit=0 stdout='answer' timed_out=False stop_tree calls=0
[proposed fix] grandchild holds pipes: stdout tail='answer' timed_out=False in 1.2s stop_tree calls=1
[proposed fix] timeout: timed_out=True stdout='partial' stop_tree calls=1
python 3.13.1 win32
[HEAD 72671402] cancel 0.3s after leader exit (kill wait 3.0s): CancelledError after 0.00s; stop_tree calls=0; reader tasks pending=2
[proposed fix] cancel 0.3s after leader exit (kill wait 3.0s): CancelledError after 0.24s; stop_tree calls=1; reader tasks pending=0
(the other six lines match 3.11)
```

**Reviewer's probe** (`probes.py r11`) on 3.11 and 3.13 gives the same result: `R11 cancel-window: CancelledError reached the caller` / `stop_tree calls after cancel=0; reader tasks still pending=2`.

**Spec.** INV-9 says `CancelledError` propagates "after the process tree is stopped". FR-11 (P0) says cancellation "leaves no process behind", and AC-11 says "no process from the call is left". On POSIX only `stop_tree → _signal_group` (`:53`, `:55`, `:63`) signals the leader's group, which outlives the leader. So the descendant is never signalled. That is a code-reading conclusion, because no POSIX host was available here. On Windows the descendant cannot be reached anyway (a documented KNOWN EDGE CASE), so the Windows effect is two pending reader tasks plus an open transport until the descendant exits. No other guard exists: the callers (`grok/threads.py`, `opencode/threads.py`, `muse/threads.py:231-235`) only re-raise, or reap in WSL mode.

**Severity.** Major. It is a regression of a P0 requirement in R-11's own scenario, but it needs a cancel within the kill wait (1 s by default) after the leader's exit.

**Smallest fix.** The re-reviewer's move into the `try` is right, but it is incomplete as written. The `except TimeoutError` branch must also gain `await self._finish_readers(readers)` after its `stop_tree`, because the moved line no longer runs after a timeout. The `not timed_out` condition goes away. My `FixedRunner` is exactly that change, and its plain, held-pipe and timeout results equal HEAD's.

## R-RR2 → R-28 (Blocker, raised from Major): bare `taskkill`

**Code.** `runner.py:87`: `asyncio.create_subprocess_exec(*native_threads.NATIVE_TASKKILL_ARGUMENTS, str(pid), ...)` with `NATIVE_TASKKILL_ARGUMENTS = ("taskkill", "/T", "/F", "/PID")` (`constants:66`). No `env=` is passed, so taskkill inherits the caller's `os.environ`. `stop_tree` reaches it on a timeout (`:192`), a cancel (`:196`) and a post-exit held pipe (`:204`).

**Reviewer's probe** (`taskkill_cwd.py`):
```
--- with variable
taskkill exit 0 | stdout head: b'\r\nTASKKILL [/S system [/U username [/P [password]]]]\r\n      '
planted stand-ins started: 0
NoDefaultCurrentDirectoryInExePath set: True
--- without variable (env -u NoDefaultCurrentDirectoryInExePath)
taskkill exit 2 | stdout head: b''
planted stand-ins started: 2
NoDefaultCurrentDirectoryInExePath set: False
```

**My probe** (`rr2_stop_tree.py`) drives the real `ProcessStopper.stop_tree` on a live leader and grandchild. It runs from a folder holding a pack stand-in named `taskkill.exe`. `os.environ` holds a dummy `XAI_API_KEY`, and the stand-in logs only its digest. Variants: `head`, `sysroot` (taskkill from `%SystemRoot%\System32`), and `findprog` (`CliRunner.find_program("taskkill")`). PATH is either the real one or the pack's sandbox PATH (an empty folder).
```
variant=head path=realpath NDCD set=True: planted taskkill.exe started=0 (XAI_API_KEY present in its env: []); leader rc=1; grandchild alive after stop=False; stop took 0.1s
variant=head path=realpath NDCD set=False: planted taskkill.exe started=1 (XAI_API_KEY present in its env: [True]); leader rc=1; grandchild alive after stop=True; stop took 0.1s
variant=head path=sandboxpath NDCD set=False: planted taskkill.exe started=1 (XAI_API_KEY present in its env: [True]); leader rc=1; grandchild alive after stop=True; stop took 0.1s
variant=sysroot path=sandboxpath NDCD set=False: planted taskkill.exe started=0 (XAI_API_KEY present in its env: []); leader rc=1; grandchild alive after stop=False; stop took 0.1s
variant=findprog path=realpath NDCD set=False: planted taskkill.exe started=0 (XAI_API_KEY present in its env: []); leader rc=1; grandchild alive after stop=False; stop took 0.1s
variant=findprog path=sandboxpath NDCD set=False: planted taskkill.exe started=0 (XAI_API_KEY present in its env: []); leader rc=1; grandchild alive after stop=True; stop took 0.0s
=== 3.13 head, NDCD unset
variant=head path=realpath NDCD set=False: planted taskkill.exe started=1 (XAI_API_KEY present in its env: [True]); leader rc=1; grandchild alive after stop=True; stop took 2.1s
```
The planted program runs **and** the real tree stop does not happen. The second effect is new: the re-review did not report it.

**Spec and existing guards.** The risk is T-6's code-execution class: R-4 (Blocker) was "a program in the current folder runs". D-16, and deviation 15 ("never in the current folder") covers only `find_program` and its callers. The runner header (`:9`) claims "a bare program name is looked up only in the absolute PATH folders … and one found in none of them is not started", which is false for taskkill. No guard exists: `find_program` is not on this path. INV-2 holds, because the per-call key is in the vendor child's overlay only, not in `os.environ`.

**Severity.** I raised it to Blocker. The result is unsafe: a planted binary runs with the caller's environment on ordinary events (any timeout, any cancel, and any exit with held pipes). The INV-8/INV-9 tree stop also fails in that case. The trigger is the same as R-4's, which was a Blocker, and the repair commit claims to close this class. The SDK key not leaking is the only mitigation, and it does not change the code-execution impact.

**Other bare names (blind-spot sweep).** `git diff --name-only --diff-filter=AM origin/main...HEAD -- vidbyte | xargs grep -n "create_subprocess_exec|create_subprocess_shell|subprocess_exec|subprocess.(run|Popen|call|check_output|check_call)|os.system|os.exec|os.spawn|startfile|shutil.which|CliInvocation("` finds only two launches: `runner.py:87` (taskkill) and `runner.py:250` (`loop.subprocess_exec` in `CliRunner.launch`, fed by `find_program` on win32 at `:165`). Every `CliInvocation` (`grok/threads.py:107`, `opencode/threads.py:99`, `muse/threads.py:193`, `:217`, `muse/launcher.py:134`, `:151`) runs through `CliRunner.run`. The WSL reap and listing use `self._wsl_program`, which `find_program` resolved. No other site exists.

**Fix choice.** The re-review offers two options. The first is `CliRunner.find_program`. I ran the pack's tree-stop files (process_bounds, runner, wsl) with each variant patched in through a scratch pytest plugin (`<scratch>/s5-verifier-rr1/plugins/`), with the variable unset:
```
=== baseline HEAD
45 passed, 1 skipped in 31.04s
=== rr2_findprog
FAILED …test_run_past_its_timeout_is_timed_out_with_its_tree_stopped[grok-hold-False]   (and 4 more parametrizations)
FAILED …test_cancellation_propagates_after_the_tree_is_stopped[grok|opencode|muse]
FAILED …test_harness_threads_wsl.py::test_wsl_run_past_its_timeout_is_reaped_with_the_calls_mark
9 failed, 36 passed, 1 skipped in 34.80s
=== rr2_sysroot
45 passed, 1 skipped in 30.58s
```
The `sandbox` fixture sets PATH to one empty folder, so `find_program` finds no taskkill, the fallback kills only the leader, and the grandchild survives. CreateProcess's own search reaches System32 regardless of PATH, which is why HEAD passes. A real caller with a trimmed PATH would lose the tree stop in the same way. So the fix is the `%SystemRoot%` path, with the `None` fallback, as written in R-28. Its constants (`NATIVE_SYSTEM_ROOT_VARIABLE`, `NATIVE_TASKKILL_PATH_PARTS`, and `NATIVE_TASKKILL_ARGUMENTS` without the program name) need a §17 deviation note (row 30). This touches R-13's tuple but does not conflict with it.

**R-4 tests with and without the variable** (`-k current_folder`, 9 cases):
```
HEAD, NDCD set:    9 passed, 28 deselected in 1.05s
HEAD, NDCD unset:  9 passed, 28 deselected in 1.22s
pre-repair export (git archive d5581a24 vidbyte; current tests), run from the export folder:
  3.11 NDCD set:    9 failed, 28 deselected in 2.59s
  3.11 NDCD unset:  9 failed, 28 deselected in 1.70s
  3.13 NDCD set:    9 passed, 28 deselected in 1.94s   <- cannot see R-4
  3.13 NDCD unset:  9 failed, 28 deselected in 1.90s
```
3.11's `shutil.which` adds the current folder unconditionally. From 3.12 it honors the variable, and CreateProcess does too. So on 3.12+ in this shell the R-4 tests are blind. CI is `ubuntu-latest` only (`.github/workflows/ci.yml:17`, `:44`), so these Windows regressions can fail only in a local Windows run. That is recorded as R-31. The fix is one `monkeypatch.delenv` in the `decoy_log` fixture (`test_harness_threads_launcher.py:44-51`), which R-28's new test should use too.

## R-RR3 → R-29 (Major, raised from Minor): prompt cap counted in quoted units

**Code.** `vidbyte/lib/dataclasses/native_threads.py:98-99` calls `RecordFieldValidator.require_command_line_units(self.prompt, "prompt", max_units=NATIVE_ARGV_PROMPT_MAX_CHARS)` on win32 for Grok and Muse. `validation.py:64-74` counts `subprocess.list2cmdline([value])` in UTF-16 units. List2cmdline wraps any value that holds a space in two quotes, so any prose prompt of 23,999 characters or more is refused.

**My probe** (`rr3_cmdline.py`). It builds records only; the launches are `python -c pass`.
```
1. OS limit: largest command line that launched = 32766 UTF-16 units; one more -> launched=False (32767, 206) (units, winerror)
2. grok  24,000 chars of prose: chars=24000 quoted_units=24002 -> refused: prompt must take at most 24000 UTF-16 code units once quoted for the Windows command line; got 24002.
2. muse  24,000 chars of prose: … -> refused (same)
2. grok  23,999 chars, one space: chars=23999 quoted_units=24001 -> refused …
2. grok  12,000 chars of prose: chars=12000 quoted_units=12002 -> accepted
2. grok  24,000 chars, no space: chars=24000 quoted_units=24000 -> accepted
2. grok  20,000 double quotes: chars=20000 quoted_units=40000 -> refused …
2. grok  20,000 astral chars: chars=20000 quoted_units=40000 -> refused …
3. grok fork argv (workspace 45 chars, launcher 35 chars): rest-of-line = 525 units
3. muse WSL fork exec argv, default muse_path: rest-of-line = 608 units
3. muse WSL fork exec argv, 4,096-char muse_path (MUSE_PATH_MAX_CHARS): rest-of-line = 4685 units
```
"Rest-of-line" is the whole argv's units minus the quoted prompt's units, for a fork with a 160-character model and thread id, the longest reasoning-effort value and a 64-character distro (Muse). The reviewer's `probes.py r8` repeats the refusals (`24000 chars, prose with spaces quoted_units=24002 -> configuration.invalid_argument`, `23999 chars, one space -> configuration.invalid_argument`, `23000 chars incl 1001 quotes -> configuration.invalid_argument`, `23000 chars incl 1000 quotes … -> ran`, `opencode 24001 quotes -> ran`).

**Spec.** §9.1 says the prompt is "at most … `NATIVE_ARGV_PROMPT_MAX_CHARS` for Grok and Muse". The EC-3 trigger is "Prompt longer than `NATIVE_ARGV_PROMPT_MAX_CHARS` (24,000)". D-20 calls 24,000 "the PR's existing bound under the Windows command-line limit". The reading is correct: a 24,000-character prose prompt is spec-valid and is refused. Deviation 18 records the stricter rule, but the orchestrator has decided that the code must conform. The existing boundary test `test_prompt_at_the_harness_cap_still_runs` uses `"p" * cap` (`test_harness_threads_arguments.py:121`), which has no space.

**Severity.** I raised it to Major. The calibration scale says Minor means clarity, and this is not a clarity issue. Spec-valid input at the stated boundary is refused deterministically on every Windows call that carries such a prompt. That would surface both in review and in production. A large code prompt with a few thousand `"` characters hits it well below 24,000 characters. It is not a Blocker, because the refusal is accurate and nothing unsafe happens.

**Fix simulation.** The scratch plugin `rr3_units30000` replaces `max_units=24000` with 30000 inside the validator call, and the source is not touched.
```
R8 grok [24000 chars, prose with spaces] chars=24000 quoted_units=24002 -> ran (e7111fd8)
R8 grok [23999 chars, one space] chars=23999 quoted_units=24001 -> ran (61f50374)
R8 grok [23000 chars incl 1001 quotes] chars=23000 quoted_units=24001 -> ran (fcfa238a)
R8 grok [16000 chars JSON-ish, 4001 quotes] chars=16000 quoted_units=21334 -> ran (da16fe6b)
R8 opencode 24001 quotes -> ran
```
Against the existing argument tests (`-k prompt`):
```
FAILED …test_prompt_whose_quoted_form_passes_the_argv_cap_is_refused[quotes-grok]
FAILED …[quotes-muse]  FAILED …[astral-grok]  FAILED …[astral-muse]
4 failed, 18 passed, 167 deselected in 0.66s
AssertionError: INV-5: prompt cap ('24000') is missing from the message … prompt must take at most 30000 UTF-16 code units once quoted …
```
**The fix in the orchestrator's terms.**
- *Units constant:* `NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS = 30000` in `vidbyte/lib/constants/native_threads.py`, read by the record, not by the validator, which keeps R-22's coupling where it is. The 24,000-character `require_text` cap stays.
- *Where to measure:* the prompt alone, in the record. The record has no launcher. A Muse fork's new id exists only after the temp folder is made. Grok prepares its home before it builds the argv. So a whole-command-line check could not refuse before anything is created (INV-4). The whole line is already covered after the fact: WinError 206 maps to `OS_ERROR`, giving `launch_failed` (R-8 part 2, `runner.py:261-265`).
- *Overhead margin:* 32,766 (measured) − 30,000 = 2,766 units. The measured rest of the line is 525 to 608 units with short paths, and under 1,000 with 260-character workspace and launcher paths. The residual is a `muse_path` over about 2,000 characters, or workspace plus launcher paths over about 2,200, together with a prompt that close to the ceiling. It fails as `launch_failed`, never as `not_installed`. A ceiling of 27,000 would also cover a 4,096-character `muse_path`, but it would refuse more dense prompts that fit. Choose it only if the owner wants every bounded configuration guaranteed.
- *Tests (route: S2):* (a) a 24,000-character prose prompt runs for Grok and Muse on win32 and reaches the stand-in unchanged; (b) the dense-prompt test's cap observation becomes the unit ceiling, read from the constants module. Its refusals stay, because each prompt is 40,000 units. If (b) is not acceptable, the refusal must also name 24,000, through an optional message-only argument of the validator. On ubuntu CI the record check is skipped, so (a) can fail only on win32.

## R-RR4 → R-30 (Minor): a double cancel leaves the Muse temp folder

**Code.** `muse/threads.py:109-114`: the preparation is shielded, and the `except asyncio.CancelledError` branch calls `_discard`. `_discard` (`:162-171`) runs `await asyncio.wait({preparing})` unshielded, then removes the folder. A second cancel interrupts the wait, the removal never starts, and the worker thread still creates and fills the folder.

**My probe** (`rr4_double_cancel.py`). It uses the pack sandbox and stand-in, and holds the skill copy on a `threading.Event` gate. `shielded` simulates the fix by wrapping `_discard` in `asyncio.shield(asyncio.ensure_future(...))`.
```
[head] cancels=1: CancelledError; temp folders when CancelledError arrived=[]; 1.5s after the copy finished=[]; muse starts=0
[head] cancels=2: CancelledError; temp folders when CancelledError arrived=['tmpyf4sk_qi']; 1.5s after the copy finished=['tmpyf4sk_qi']; muse starts=0
[shielded] cancels=1: CancelledError; temp folders when CancelledError arrived=[]; 1.5s after the copy finished=[]; muse starts=0
[shielded] cancels=2: CancelledError; temp folders when CancelledError arrived=['tmpu7u0lzmk']; 1.5s after the copy finished=[]; muse starts=0
=== 3.13: same four outcomes (tmpep1oiccr left by head; [] for shielded after the copy)
```
The reviewer's `probes.py r9`: `R10 temp leftovers right after: []`, `R10 double-cancel leftovers after 1.5s: ['tmpmmt1__x7']`.

**Spec.** INV-9 and AC-11 say "the Muse temp folder is gone", and EC-34 excuses only a removal that fails. The reading is correct, and no other guard exists: the `finally` at `:139-143` is not reached, because the cancel comes before the `try`.

**Severity.** Minor. The result is a leftover temp folder, which EC-34 already accepts in another case. It holds skill copies and no key, and it needs two cancels within the copy window.

**Fix.** The re-reviewer's shield closes the leak. Its limit: under a double cancel, `CancelledError` arrives before the removal, so INV-9's ordering holds for one cancel only. A strict alternative re-awaits the shielded cleanup in a loop that suppresses `CancelledError` until the cleanup is done, then raises. The S2 test must poll after it opens the gate, not check when `CancelledError` arrives. Otherwise it would fail the shield fix too.

## Blind spots and fix interactions

1. **R-27 with R-28.** R-27's fix adds one more path into `stop_tree` (a cancel during the post-exit wait), so until R-28 lands it adds one more way to start the planted taskkill. Land them in the same iteration, with R-28 first or together.
2. **R-27's fix must cover the timeout branch** (`_finish_readers` after its `stop_tree`). The re-review's text leaves that out.
3. **R-28's fix choice decides whether 9 existing tree-stop tests stay green on win32.** `find_program` fails them under the sandbox PATH, and `%SystemRoot%` keeps them green (measured).
4. **R-28's and R-31's tests need `monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)`**, put in the shared `decoy_log` fixture. Without it, the taskkill test can never fail in this shell, and the R-4 tests are blind on 3.12+.
5. **R-29's ceiling changes the refusal text**, so 4 existing dense-prompt cases fail unless S2 changes their cap observation, or the message also names 24,000 (measured `4 failed, 18 passed`). R-8's part (2) mapping (WinError 206 to `OS_ERROR`) must stay, because it is the safety net for the residual.
6. **R-30 and R-27** share a root cause: a cleanup await that a cancel can interrupt. The same shape exists in S3 code the repair did not touch, the Muse WSL reap (`muse/threads.py:233-237`), recorded as R-32 (follow-up, code reading only; the stand-in reap finishes at once, so it cannot be shown here). The CliRunner timeout branch has the same shape, but `stop_tree`'s own `finally` (`runner.py:61-69`) kills the group and closes the pipes, so a cancel there leaks nothing lasting.
7. **R-1…R-11 interactions.** No new conflicts. R-29 keeps R-8's part (2). R-27 keeps R-11's exit signal and post-exit tree stop: the plain, held-pipe and timeout results are unchanged in my `FixedRunner`. R-30 keeps R-10's single-cancel order. R-28 changes the constant that R-13's follow-up discusses (`NATIVE_TASKKILL_ARGUMENTS`), with no conflict.

## Commands run (final lines)

- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `428 passed, 2 skipped in 46.83s`
- `PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-rereview/probes.py "$(pwd)" r11` (3.11 and venv313 3.13.1) → `R11 cancel-window: CancelledError reached the caller` / `R11 cancel-window: stop_tree calls after cancel=0; reader tasks still pending=2`
- `… probes.py "$(pwd)" r8 r9` → the R8 lines quoted above; `R9 grok call 1..3 -> ok`; `R10 CancelledError propagated after 0.69s`; `R10 double-cancel leftovers after 1.5s: ['tmpmmt1__x7']`
- `PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-verifier-rr1/rr1_cancel_window.py "$(pwd)"` (3.11, 3.13) → quoted above
- `[env -u NoDefaultCurrentDirectoryInExePath] PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-rereview/taskkill_cwd.py "$(pwd)"` → `planted stand-ins started: 0` / `planted stand-ins started: 2`
- `[env -u …] PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-verifier-rr1/rr2_stop_tree.py "$(pwd)" <head|sysroot|findprog> <realpath|sandboxpath>` → quoted above
- `env -u NoDefaultCurrentDirectoryInExePath PYTHONPATH="$(pwd);<scratch>/s5-verifier-rr1/plugins" python -m pytest -q -p no:cacheprovider [-p rr2_findprog|-p rr2_sysroot] tests/features/harness_threads/test_harness_threads_{process_bounds,runner,wsl}.py` → `45 passed, 1 skipped` / `9 failed, 36 passed, 1 skipped` / `45 passed, 1 skipped`
- `[env -u …] PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads/test_harness_threads_launcher.py -k current_folder` → `9 passed, 28 deselected` (both)
- `git archive d5581a24 vidbyte pyproject.toml | tar -x -C <scratch>/s5-verifier-rr1/old-d5581a24` plus `git archive 72671402 tests/features/harness_threads tests/__init__.py | tar -x …`; the same `-k current_folder` run from that folder on 3.11 and 3.13, with and without the variable → `9 failed` / `9 failed` / `9 passed` / `9 failed`
- `PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-verifier-rr1/rr3_cmdline.py "$(pwd)"` → quoted above
- `PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-verifier-rr1/rr3_fix_e2e.py "$(pwd)" <scratch>/s5-verifier-rr1/plugins <scratch>/s5-rereview/probes.py` → the R8 `-> ran` lines quoted above
- `PYTHONPATH="$(pwd);<scratch>/s5-verifier-rr1/plugins" python -m pytest -q -p no:cacheprovider -p rr3_units30000 tests/features/harness_threads/test_harness_threads_arguments.py -k prompt` → `4 failed, 18 passed, 167 deselected in 0.66s`
- `PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-verifier-rr1/rr4_double_cancel.py "$(pwd)" <head|shielded>` (3.11, 3.13) → quoted above
- `git status --short` after the edits → ` M docs/spec/harness-thread-functions/review.md` (and this new report)
