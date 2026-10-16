LENS: conformance (post-repair re-review, round 2)
VERDICT: SOUND — R-27 to R-30 are fixed on the paths their evidence names, the round-1 fixes still hold, and nothing in iteration 2 breaks a spec ID or the user's words; two Minor follow-ups remain: deviation 20 claims more than the code delivers, and a Windows cancel window sits in the runner's timeout handler.

Scope: `git diff bb7d78bb..386e1044 -- vidbyte` (runner.py, constants/native_threads.py, dataclasses/native_threads.py, muse/threads.py), read in full, plus the iteration-2 regression tests and spec §17 deviations 18, 20, 21, 23 and 24. HEAD `386e1044`, worktree clean.

WHAT THE IMPLEMENTATION GETS RIGHT
- R-28: taskkill now starts from an absolute path. The code reads `SystemRoot` at call time and uses `C:\Windows` when it is unset or empty. Every failure falls back to the leader kill: a relative root returns `None`, a missing file raises `OSError` → `None`, and a taskkill that fails still lets the leader kill run. The PR's `vidbyte/` files now launch processes in only two places: `runner.py:118` (taskkill, absolute) and `runner.py:283` (`loop.subprocess_exec`, fed by `find_program` on win32). `wsl.exe` goes through `find_program` (`muse/launcher.py:79`).
- R-27:
  - The post-exit reader wait and its tree stop now sit inside the guarded `try` (`runner.py:223-224`), so a cancel there reaches the full cancel handler.
  - A plain run never calls `stop_tree`, so `_wait_group_gone` adds no latency to normal runs (rr1: `plain … stop_tree calls=0`).
  - The group wait has a bound: `asyncio.timeout(seconds)` under `suppress(TimeoutError, ProcessLookupError, PermissionError)`. It runs only after the group KILL on POSIX.
- R-29: the unit ceiling applies only on win32 and only to argv prompts (Grok and Muse; opencode is exempt). The 24,000-character `require_text` cap is unchanged on every platform. The refusal names `prompt`, `30000` and the Windows command line.
- R-30: the wait and the removal run as one shielded task. The shield sits in `execute`, which keeps principle 1 (the depth scan finds 0 new chains). A single cancel still removes the folder before `CancelledError` propagates. `CancelledError` is never swallowed or turned into a `NativeThreadError`.

FINDINGS (ranked, most severe first)
R-RRB1 [Minor] [deviation honesty / INV-9, AC-11] `vidbyte/harnesses/native/muse/threads.py:113-117`, `:171-174`; header `:9`; `docs/spec/harness-thread-functions/spec.md:1040` (deviation 20) — Under a second cancel the folder is not always removed "in the background": if the caller's event loop ends first, the temp folder with the skill copies stays for good.
  Evidence: deviation 20 says "the removal ends in the background after `CancelledError` has reached the caller". The header says "a second cancel stops only that waiting, never the removal, which then ends in the background". I ran `s5-rereview-2/r30_shutdown.py <worktree> <cancels> <mode>`. The skill copy is held on a `threading.Event` that a timer opens 0.3 s after the cancels, and `muse` is never started. Results on 3.11.0:
    `cancels=1 mode=shutdown: CancelledError; temp folders when it arrived=[]; 1.5s after asyncio.run returned=[]`
    `cancels=2 mode=alive: CancelledError; temp folders when it arrived=['tmpuop7d4ue']; 1.5s after asyncio.run returned=[]`
    `cancels=2 mode=shutdown: CancelledError; temp folders when it arrived=['tmpt6j68udx']; 1.5s after asyncio.run returned=['tmpt6j68udx']`
  3.13 gives the same last row (`['tmpkkiyjys_']` kept). The leftover holds `tmp/tmpt6j68udx/muse/skills/held-skill/SKILL.md`.
  Failure: two cancels land during the skill copy, and then `main()` returns, which is the normal end of an `asyncio.run` script. At shutdown, `asyncio.run` cancels every pending task (`_cancel_all_tasks`), including the shielded `_discard` task. That task is still parked in `asyncio.wait({preparing})` (`:171`), so it never reaches the removal. `preparing` is cancelled too, so `preparing.exception()` would raise anyway. The worker thread is still joined by `shutdown_default_executor`, finishes the copy, and leaves the folder. In the `finally` path (`:145-146`) a second cancel behaves differently: the removal runs inside the worker thread, so it survives the loop's end. Only the R-30 path depends on a task outliving the caller.
  Smallest fix: doc only. Amend deviation 20 and the `:9` header to say "…ends in the background while the caller's event loop keeps running; if the loop ends first, the folder stays (as EC-34)". Code option (follow-up): make the abandoned-folder removal independent of a task. For example, the cancel path sets a `threading.Event` that `_prepare_config` checks after its copy, and the worker removes its own folder; keep `_discard` for the case where the copy already returned.
  Spec IDs: INV-9, AC-11, EC-34; §17 deviation 20.
  Weighted words: none of §D's words is in INV-9 or AC-11. "every single function" is about error handling, and every function still handles cancellation. This finding concerns the accuracy of a stated limitation. It is not a new break of a weighted word.

R-RRB2 [Minor] [INV-9, AC-11 / R-27 class] `vidbyte/lib/process/runner.py:225-230` with `:65-73` (`stop_tree`'s `finally`; `_close_pipes(killer)` at `:73` → `transport.close()` at `:160-163`) — On Windows, one cancel that lands while the runner's own timeout handler is running taskkill aborts the tree stop, and a live grandchild survives the cancelled call. This code predates iteration 2. It is not a regression of the fixes.
  Evidence: I ran `s5-rereview-2/r27_timeout_cancel.py <worktree> <delay>`. The leader is a `python -c` that starts a sleeping grandchild on the same pipes and sleeps, with `timeout_seconds=1.0`. Hooks only observe (they call the originals), and the cancel lands `<delay>` s after the timeout handler's `stop_tree` enters `_wait_taskkill`. Results:
    3.11 run 1 and run 2, and 3.13: `delay=0 … CancelledError after 0.00s; stop_tree entered=1 finished=0; reader tasks pending at CancelledError=2; grandchild alive at CancelledError=True` / `grandchild alive 2s later=True`
    3.11 control: `delay=0.3 … returned; stop_tree entered=1 finished=1; … grandchild alive at CancelledError=False`. So the window is the taskkill run, about 0.1 s.
  Failure: the caller's `CancelledError` is raised inside `except TimeoutError:` (`:225`). The sibling `except asyncio.CancelledError:` (`:231`) therefore never runs, along with its full `stop_tree` and `_finish_readers`. `stop_tree`'s `finally` kills the leader and closes the killer's transport. asyncio's `BaseSubprocessTransport.close()` kills a child that is still running, so taskkill dies before it reaches the grandchild. Here the leader was alive, so this is not the documented "leader already exited" limit. A second cancel during the cancel handler's own taskkill hits the same path.
  This refutes for win32 the verifier's note (`reports/S5-findings-verifier-rr1.md:183`, item 6): "a cancel there leaks nothing lasting". On POSIX that note holds, because the `finally` sends SIGKILL to the group. That path still skips `_wait_group_gone`, though, which is R-27's POSIX race again (deviation 24).
  Smallest fix (follow-up, same class as R-32): run the stop and the reader collection of the `except TimeoutError` branch as one task under `asyncio.shield`, the R-30 pattern. Do the same in the `except CancelledError` branch, so a cancel stops only the waiting, never the stop. Alternatively, do not close a killer that is still running in `stop_tree`'s `finally`.
  Spec IDs: INV-9, AC-11, FR-11 (and INV-8 for the "after the stop" order).

FIX CONFIRMATIONS
- R-27: confirmed. The post-exit wait and stop are inside the guarded `try`.
  - rr1 on HEAD: `CancelledError after 0.08s; stop_tree calls=1; reader tasks pending=0`. Plain, held-pipe (`'answer'`, `stop_tree calls=1`) and timeout (`timed_out=True stdout='partial'`) runs are unchanged.
  - The POSIX half (`_wait_group_gone`) has a bound and runs only on a stop. It is proven by GitHub CI: `4dc11f2c` failed Source 3.11 and 3.12, while `53d9f45a` and `ac8c8cdb` are 4/4 success (check-runs API).
  - The regression test passes for the right reason on 3.11 and 3.13: on POSIX the grandchild is dead at `CancelledError`; on win32 no reader task is left. Residual window: R-RRB2.
- R-28: confirmed.
  - With `NoDefaultCurrentDirectoryInExePath` unset, `rr2_stop_tree.py head realpath|sandboxpath` gives `planted taskkill.exe started=0 (XAI_API_KEY present in its env: []); … grandchild alive after stop=False` in both PATH modes.
  - `r28_root_probe.py` gives `unset: started=True`, `relative: started=False` and `real: started=True`, with `leader rc after stop=1` every time. `r28_missing.py`: `absolute root without taskkill.exe: leader rc after stop=1` and `taskkill that fails at once: leader rc after stop=1`.
  - The test removes the shell variable (`decoy_log`), so it can fail in this shell.
- R-29: confirmed. `rr3_cmdline.py` gives 24,000 prose (24,002 units) and 23,999 with one space (24,001) → accepted for Grok and Muse, and 20,000 quotes or astral characters (40,000 units) → `refused: … at most 30000 UTF-16 code units once quoted for the Windows command line`.
  - `r29_msg.py`: opencode with 20,000 or 100,000 quotes → accepted; Grok or Muse at 24,001 characters → `at most 24000 characters` (the raw cap still applies); 15,001 quotes → refused at 30002; 14,999 quotes → accepted.
  - Public error: `run_grok_thread failed with configuration.invalid_argument. … The argument prompt was refused: prompt must take at most 30000 UTF-16 code units once quoted for the Windows command line; got 40000. Likely cause: … Next step: Fix the argument named in this message and call again; nothing ran and nothing was written.`
- R-30: confirmed while the loop runs. `rr4_double_cancel.py head` gives `cancels=1: … temp folders when CancelledError arrived=[]` and `cancels=2: … arrived=['tmpvtk6s_30']; 1.5s after the copy finished=[]`. It does not hold when the loop ends first (R-RRB1).
- R-1: holds; 0 comment lines over 72 columns in the 4 iteration-2 files.
- R-2: holds; `ShellFlag.READ_STDIN` at `muse/launcher.py:150`, and `MUSE_REAP_STDIN_SWITCH` is absent.
- R-3: holds; the depth scan over every changed module finds only main's `FailureCode.from_exception` chain.
- R-4: holds; `find_program` is unchanged, the explicit-command fallback to the bare name is refused again in `run`, and the 9 current-folder tests pass.
- R-5, R-6, R-7: untouched by iteration 2; the pack is green.
- R-8: holds with the new ceiling; WinError 206 → `OS_ERROR` is unchanged (`runner.py:294-298`).
- R-9: holds; `NativeSkillFolders.remove` is still used by `_discard` and the `finally`.
- R-10: holds; the single-cancel order is unchanged (rr4, and r30 `cancels=1 mode=shutdown`).
- R-11: holds; `'answer'` is returned with a grandchild on the pipes (rr1).
- R-15, R-16, R-17: hold (`constants:283`, `:326`; headers untouched).

DEVIATIONS 20 AND 24 AGAINST INV-9, INV-8 AND AC-11
- Deviation 20 (a second cancel leaves the removal in the background): acceptable as a stated limitation, but only once its wording is corrected (R-RRB1).
  - Prosecution: INV-9 says `CancelledError` propagates "after … the Muse temp folder is removed", and AC-11 says "the Muse temp folder is gone".
  - Defense: the only way to keep that order for any number of cancels is to swallow later cancels. That contradicts INV-9's own "propagates unchanged", and it would trap a caller behind a hung copy. The trigger needs two cancels inside the copy window, and the folder holds no key (`MUSE_AUTH_PATH` is never created).
  - No §D weighted word is in these IDs. The owner is told and keeps the choice. The defect is the claim that the removal always ends, which the loop-shutdown case breaks.
- Deviation 24 (an unreaped zombie holds the POSIX stop to its grace): acceptable, not a defect.
  - The wait has a bound (`NATIVE_KILL_WAIT_SECONDS`, default 1 s) and runs only on a stop.
  - A zombie runs no code, so INV-8's "runs for at most" and AC-11's "no process … is left" still hold in substance. The pack's own `alive` counts Z as dead.
  - The zombie exists because the container has no init, not because of the SDK. The extra second stays inside AC-9's "timeout plus the stop bound".
  - Side note: on Python 3.11.0–3.11.2, `asyncio.timeout` converts its expiry only when `uncancel() == 0`. If the group wait times out inside the cancel handler (the zombie case), it ends with `CancelledError` through `stop_tree`'s `finally` instead of returning. The caller still gets `CancelledError`, so the behavior is unchanged.

VERIFIED CLAIMS
- S5-repair-2: "no other bare program name is launched". Held: a grep over the PR's added and changed `vidbyte/` files finds exactly `runner.py:118` and `runner.py:283`.
- S5-repair-2: "`hostkit/launcher.py:41` falls back to the bare name, but `run` looks it up again". Held (`launcher.py:41`, `runner.py:196`, `:270-271`).
- Deviation 23: "a root that is not absolute starts nothing, and the leader kill still runs". Held (r28 probes). The code also treats an empty `SystemRoot` as unset.
- Deviation 21: the timeout branch collects its readers after its stop. Held (`runner.py:229-230`).
- Deviation 24 and the verify-log: CI on `4dc11f2c` failed Source 3.11 and 3.12, and `53d9f45a` passed 4/4. Held (check-runs API). `ac8c8cdb` is also 4/4.
- Deviation 18: "every prose prompt the character cap allows still runs" held. "measured worst case 608 units" holds only with the default `muse_path`: rr3 measures `4,096-char muse_path … rest-of-line = 4685 units`. The deviation's next sentence covers that residual (WinError 206 → `launch_failed`), but the constant's comment (`constants:28-31`) has no qualifier.
- review.md statuses: R-27 `fixed @4a352946, 53d9f45a`, R-28 `@7ec71ec7`, R-29 `@5ee16c7d` and R-30 `@5f016773` all match `git log`. R-31's row (`review.md:55`) still reads "open (do with R-28's test)", although `decoy_log` removes the variable since `4b5eacad`. It is a stale status that S6 should not repeat.
- Budget and boundaries: 24 added `.py` files; class counts in the 4 iteration-2 files are unchanged (runner 3, muse/threads 2, dataclasses 5); no enum file changed. `git diff origin/main...386e1044 -- lint/` is empty, and `git diff b737f57f..386e1044 -- tests` is empty. INV-21 and C016 files have 0 diff lines. `vidbyte.harnesses.native.__all__` holds 17 names with the 9 functions. Iteration 2 adds no public name, control or field.
- AC-1: the spec §4 snippet, run verbatim against PATH stand-ins, prints 3 lines; the fork id differs, the return code is 0, and the workspace is untouched.

COMMANDS RUN
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `436 passed, 2 skipped in 52.62s`
- `… venv313 python -m pytest … -k "taskkill_from_the_current_folder or cancel_after_the_leader_exits or prose_prompt_within or quoted_form_passes or cancelled_twice or cancelled_while_preparing or cancellation_propagates"` → `16 passed, 422 deselected in 5.04s`
- `python lint/run.py` → `A007 255 255 RATCHETED`, `S009 350 350 RATCHETED`, `SDK-LINT: PASS` (exit 0)
- `s4-conformance/snippet_ac1.py` → `test SNIPPET == spec section 4: True`, `returncode: 0`, `lines: 3 fork id differs: True`, `workspace entries after run: []`
- `s4-conformance/static_checks.py` → `INV-15 violations: none`, `constants: 211 with no reader: none`
- `s5-rereview/depth.py 386e1044 <changed vidbyte .py>` → `vidbyte/lib/enums/failure.py: FailureCode.from_exception -> …` / `chains: 1` (main's)
- `s5-verifier-rr1/rr1_cancel_window.py` → `[HEAD …] cancel 0.3s after leader exit (kill wait 3.0s): CancelledError after 0.08s; stop_tree calls=1; reader tasks pending=0` (the label is stale; it runs the worktree code)
- `env -u NoDefaultCurrentDirectoryInExePath … rr2_stop_tree.py "$(pwd)" head realpath` and `… sandboxpath` → `planted taskkill.exe started=0 … grandchild alive after stop=False; stop took 0.1s` (both)
- `s5-repair-2/r28_root_probe.py` → `unset: … started=True` / `relative: … started=False` / `real: … started=True`, `leader rc after stop=1` each
- `s5-rereview-2/r28_missing.py` → `absolute root without taskkill.exe: leader rc after stop=1; stop took 0.00s` / `taskkill that fails at once: leader rc after stop=1; stop took 0.05s`
- `s5-verifier-rr1/rr3_cmdline.py` → `32766 … one more -> launched=False (32767, 206)`; prose accepted; dense → `refused: … at most 30000 …`; `muse WSL fork exec argv, 4,096-char muse_path … = 4685 units`
- `s5-rereview-2/r29_msg.py` → the lines quoted under R-29 above
- `s5-verifier-rr1/rr4_double_cancel.py "$(pwd)" head` → `cancels=1: … arrived=[] …=[]` / `cancels=2: … arrived=['tmpvtk6s_30']; 1.5s after the copy finished=[]`
- `s5-rereview-2/r30_shutdown.py "$(pwd)" {1,2} {alive,shutdown}` (3.11; `2 shutdown` also on 3.13) → the R-RRB1 lines
- `s5-rereview-2/r27_timeout_cancel.py "$(pwd)" {0,0.3}` (3.11 ×2 at 0, 3.13 at 0, 3.11 at 0.3) → the R-RRB2 lines
- `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs` → 53d9f45a and ac8c8cdb: `Package: completed/success`, `Static policy: completed/success`, `Source / Python 3.11: completed/success`, `Source / Python 3.12: completed/success`; 4dc11f2c: `Package: completed/skipped`, `Source / Python 3.12: completed/failure`, `Source / Python 3.11: completed/failure`
- `git diff --stat origin/main...386e1044 -- lint/` → empty; `git diff --stat b737f57f..386e1044 -- tests` → empty; `git status --short` → clean
- Probe processes: `Get-CimInstance Win32_Process … '*time.sleep(20)*'` → none left; the temp sandboxes the probes created under `%TEMP%` were removed.
