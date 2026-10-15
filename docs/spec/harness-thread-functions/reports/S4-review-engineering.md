LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the layering, key hygiene and error table are sound, but on Windows the program lookup hands the caller's key to an executable planted in the current folder, and six bounded-run, cleanup and diagnosis paths give wrong results that the test pack does not exercise.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- The key reaches a child only through the environment overlay. `CliInvocation.env_overlay`/`stdin_text` and `NativeThreadRequest.api_key` are `repr=False`, the validator never quotes `api_key`, and `NativeErrorFactory.scrub` replaces registered secrets before the redactor and before the 1,000-char cap. The AC-4 echo test that straddles that cap passes.
- Muse serve gets `env_remove=(META_API_KEY,)`, and `MuseLauncher.environment` (`muse/launcher.py:96-109`) forwards only the overlay names through WSLENV, after the caller's own entries. A META_API_KEY of the caller's own is never forwarded.
- Each public function has one guarded try: CancelledError and NativeThreadError are re-raised, ConfigurationError becomes `configuration.invalid_argument`, and anything else becomes `runtime.error` naming only the class. Every code comes from the closed `NATIVE_THREAD_FAILURE_CODES` table.
- The prompt never reaches an interpreter: `CliArgv` puts it inside `--single=`, after `--`, or on stdin, and batch launchers are refused on win32. The runner gives POSIX children a new session plus `killpg` and runs Windows `taskkill /T` with a leader-kill fallback. Each stream has its own byte cap with a truncation probe. taskkill finishes in about 0.1 s, so the 1 s kill wait is enough.

FINDINGS (ranked, most severe first, max 15)
R-E1 [Blocker] [security] vidbyte/harnesses/native/hostkit/launcher.py:41,48 (same at vidbyte/harnesses/native/muse/launcher.py:79, vidbyte/lib/process/runner.py:198) — On Windows the launcher looks in the process's current folder before PATH, so an `opencode.exe`, `grok.exe` or `wsl.exe` shipped in a cloned repository receives the caller's key
  Evidence: `found = shutil.which(program)` (launcher.py:48), `first = shutil.which(first) or first` (:41), `found = shutil.which(native_threads.WSL_PROGRAM)` (muse/launcher.py:79), `program = shutil.which(program) or program` (runner.py:198). On Windows, Python 3.11 `shutil.which` always prepends `os.curdir`, and pyproject says `requires-python = ">=3.11"`. Scratch run `exp8_cwd_lookup.py` used stand-in t64-launcher programs that record only whether a name is set, with PATH set to an empty sandbox `bin`, and the process cwd and the workspace both set to the "repo" folder. Output: `shutil.which('opencode') -> .\opencode.EXE | shutil.which('wsl.exe') -> .\wsl.exe`, `run_opencode_thread -> opencode.run_failed exit 3`, `run_muse_thread (WSL mode) -> muse.run_failed exit 3`, and planted records `"has_inline_config": true` and `"has_meta_key": true, "wslenv": "...META_API_KEY/u:..."`. `exp8b_cwd_grok.py`: `shutil.which('grok') -> .\grok.EXE`, `run_grok_thread -> grok.run_failed exit 3`, record `"has_xai_key": true, "grok_home_set": true`. `exp8c` put a `grok.exe` in a PATH folder as well, and the planted one still won: `shutil.which("grok") -> .\grok.EXE`.
  Failure: A user clones a repository and runs their script from it with `workspace="."`. The repository ships `grok.exe`, `opencode.exe` or `wsl.exe`, and that program runs instead of the real CLI, with `XAI_API_KEY`, `OPENCODE_CONFIG_CONTENT` (which holds the apiKey) or `META_API_KEY` in its environment. This is the T-6 attacker ("a cloned or prompt-injected repository passed as workspace"), and it bypasses the private-home control entirely. It also contradicts D-16's order, which is "explicit command, then PATH, then fallback".
  Smallest fix: Add one lib helper that on win32 searches only the `os.environ["PATH"]` entries, with PATHEXT, and never the implicit current folder. A name containing a path separator is kept as given. Python 3.11's `shutil.which(path=...)` still prepends cwd, so the helper must walk PATH itself. Use it at the four call sites, and add a test that plants a stand-in `grok.exe` in the cwd.
  Spec IDs: T-6, INV-2, NFR-3, D-16, FR-16

R-E2 [Major] [failure modes] vidbyte/lib/process/runner.py:159-162 — A run that finished is reported as `<h>.timed_out` after the whole timeout when a descendant keeps stdout/stderr open, and on Windows that descendant is left running
  Evidence: Inside `async with asyncio.timeout(...)` the runner does `await asyncio.wait(readers)` and only then `await process.wait()`, so the end of the run depends on EOF, not on the leader's exit. Scratch run `exp1b.py`: the stand-in `grandchild_grok2.py` prints `{"text":"done","sessionId":"abc123"}`, starts a child with `stdout=sys.stdout, stderr=sys.stderr` and exits 0. Output: `ERROR grok.timed_out 3.3 s; exit_code None` and `grandchild 19720 after the call: python.exe 19720 Console`. The same with timeout 5 gave `grok.timed_out 5.1 s`.
  Failure: Any vendor child that inherits stdio and outlives the CLI turns a completed answer into a timeout after the full `timeout_seconds` (default minutes), and the answer is discarded. Examples are an MCP stdio server whose stderr is inherited, or an `npx` chain on Windows. On Windows, `taskkill /T` on the already-exited leader cannot reach the descendant, so INV-8's "the whole process tree is stopped" also fails.
  Smallest fix: Once the leader has exited, end the bounded wait. Then give the readers one `NATIVE_KILL_WAIT_SECONDS` through the existing `_finish_readers`, stop the tree, and build the outcome from what was read. Add a runner test where the leader exits 0 while a grandchild holds the pipes.
  Spec IDs: INV-8, FR-12, AC-2

R-E3 [Major] [security/observability] vidbyte/lib/process/runner.py:239 with vidbyte/harnesses/native/hostkit/errors.py:57-60 — stderr keeps its first N bytes while the error keeps the last 1,000 characters of those, so the vendor's final error is lost and a key that straddles the byte cap leaks as a prefix
  Evidence: `buffer.extend(chunk[: limit_bytes + ... - len(buffer)])` keeps the head of the stream, and `scrub` returns `str(self._redactor.redact(text))[-limit:]`. The errors.py header says "a cap cannot cut a secret in half". Scratch run `exp6_straddle.py` used a stand-in that writes 4,194,292 filler bytes, then `key=<XAI_API_KEY>`, 1,000 log lines and `FATAL: the real final error` to stderr, and exits 1. Output: `code grok.run_failed`, `vendor_message tail: '...dddkey=xai-SECR'`, `final error present: False`, `key prefix 'xai-SECR' in str(error): True`.
  Failure: When a run writes more stderr than the cap (4 MiB for Grok, 64 MiB for the others), the error shows filler from the cap boundary instead of the error the vendor printed last. If the key happens to sit at the boundary, its leading characters appear in `str(error)` and `vendor_message`, and the redactor cannot recognise a partial key.
  Smallest fix: In the runner, keep stderr's tail rather than its head (a trimmed bytearray). In `scrub`, when the source text was truncated, drop `max(len(secret))` characters at the cut edge before replacing secrets. Correct the errors.py header claim.
  Spec IDs: INV-2, NFR-3, EC-10, INV-5 (item 6)

R-E4 [Major] [cancellation/cleanup] vidbyte/harnesses/native/muse/threads.py:106-107 — Cancelling while the private config folder is being prepared leaks the temp folder and its skill copies
  Evidence: `folder = await asyncio.to_thread(MuseThreadRun._prepare_config, request, errors)` comes before the `try:` whose `finally` removes the folder at :132. Cancelling the await does not stop the worker thread. Scratch run `exp2_muse_cancel.py` (one skill of 4,000 × 4 KB files, cancelled after 0.3 s): `CancelledError reached the caller`, `temp folder entries after the cancelled call: ['tmphnzzz3c6']`, `tmphnzzz3c6 holds 4004 entries`.
  Failure: A caller that cancels early, for example with a request timeout or by shutting down, leaves a full copy of every skill in the system temp folder on each cancelled call. INV-9 requires the folder to be removed before CancelledError propagates. EC-34 accepts only a leftover folder when its removal fails.
  Smallest fix: Run the preparation as a task. On CancelledError, `await asyncio.shield(task)` (suppressing its errors), remove the returned folder, then re-raise. An equivalent fix is to create the folder before the `try` and copy inside it, waiting for the copy before removing. Add a cancel-during-prepare test.
  Spec IDs: INV-9, AC-11, EC-16

R-E5 [Major] [observability] vidbyte/harnesses/native/grok/wire.py:42,44 (also muse/wire.py:96,98,157,159; opencode/wire.py:61,63) — timed_out and output_too_large errors drop what the vendor printed on stderr
  Evidence: `raise errors.failure(NativeThreadProblem.TIMED_OUT, request=request, outcome=outcome, seconds=timeout_seconds)` passes no `vendor_text`, and `failure` uses only `vendor_text` (errors.py: `vendor = None if vendor_text is None ...`). Scratch run `exp10_timeout_stderr.py` used a stand-in that writes "Waiting for the device login to finish at https://example.invalid/device" to stderr and then hangs, with timeout 2. Output: `code grok.timed_out | vendor_message None | 'device login' in str(error): False`.
  Failure: A vendor that hangs on a login, update or confirmation prompt explains why on stderr, but the caller sees only "waited N seconds". A hang is exactly the case where the vendor's text is the diagnosis. INV-5 item 6 requires the vendor's text "when the vendor printed any", and G-4 requires every failure to explain itself.
  Smallest fix: Pass `vendor_text=outcome.stderr` at these eight call sites. It is already scrubbed and capped by `failure`.
  Spec IDs: INV-5 (item 6), G-4, AC-10

R-E6 [Major] [failure modes] vidbyte/lib/constants/native_threads.py:27 with vidbyte/lib/process/runner.py:210-211 — The 24,000-char argv cap does not keep the Windows command line under 32,767, and the overflow is reported as `<h>.not_installed` with a false "launcher does not exist"
  Evidence: `NATIVE_ARGV_PROMPT_MAX_CHARS = 24000` counts Python characters before `list2cmdline` escaping. CreateProcess counts UTF-16 units, and WinError 206 arrives as `FileNotFoundError`, which `except FileNotFoundError: return None, ProcessLaunchFailure.NOT_FOUND` turns into not-installed. Scratch run `exp3_cmdline.py`: `quotes prompt chars 20000 list2cmdline chars 40009`, `20000 double quotes -> grok.not_installed | ... The launcher C:\...\Python311\python.exe does not exist.`, `emoji prompt chars 20000 utf-16 units 40000`, `20000 emoji -> grok.not_installed`.
  Failure: Prompts within the cap can overflow the command line. Examples are a prompt carrying escaped JSON or tool output (each `\"` becomes 4 characters) or one dense in non-BMP characters. Grok, and Muse with `-- <prompt>`, then fail as "not installed", and the next step tells the user to install a CLI that is installed. EC-3 and A-18 claim the cap prevents this.
  Smallest fix: In the record check for Grok and Muse prompts, measure `len(subprocess.list2cmdline([prompt]).encode("utf-16-le")) // 2` against the cap, so the refusal is `configuration.invalid_argument` naming `prompt`. Also map `winerror == 206` to a launch failure rather than NOT_FOUND.
  Spec IDs: EC-3, A-18, D-20, INV-6

R-E7 [Major] [failure modes] vidbyte/harnesses/native/hostkit/skills.py:38-39 — A read-only file in a skill makes every later rebuild of the private Grok skills folder fail, and a retry never recovers
  Evidence: `shutil.copytree(skill, ..., symlinks=True)` copies modes, and `shutil.rmtree(destination)` has no error handler. Scratch run `exp5_readonly.py` (a skill holding a read-only `data.txt`): `call 1 skills=[ro-skill] -> ok abc123`, `call 2 skills=[] -> grok.launch_failed`, `call 3 skills=[] -> grok.launch_failed`. The next step for `grok.launch_failed` reads "Check that grok runs from a terminal and that ~/.vidbyte/grok-homes is a writable folder, then retry". The folder is writable, and retrying fails the same way.
  Failure: A skill from a read-only source (Windows read-only attribute, Perforce checkout, Nix store directories on POSIX) blocks every later Grok call in that workspace that uses a different skill set, until someone deletes a file under `~/.vidbyte/grok-homes/<key>` by hand. For Muse, the same copy leaves a temp folder behind on every call.
  Smallest fix: Give `rmtree` an `onerror` handler (Python 3.11 does not have `onexc`) that clears the read-only bit with `os.chmod(path, stat.S_IWRITE)`, plus owner-write on the parent on POSIX, and retries. Use it in `replace` and in Muse's temp-folder removal. Add a test with a read-only skill file.
  Spec IDs: INV-12, AC-16, EC-14

R-E8 [Minor] [error classification] vidbyte/harnesses/native/muse/launcher.py:125 — In WSL mode, any non-zero exit whose stderr contains "No such file or directory" is classified as `muse.not_installed`
  Evidence: `if outcome.exit_code == native_threads.NATIVE_COMMAND_NOT_FOUND_EXIT_CODE or native_threads.MUSE_NO_SUCH_FILE_MARKER in text:` runs before `MuseExecOutput.read`. A scratch pytest (`pt/test_s4_wsl_enoent.py`, stand-in mode `fail`, stderr "error: tool read_file failed: open /mnt/c/ws/notes.md: No such file or directory", exit 1) gave `AssertionError: assert 'muse.not_installed' == 'muse.run_failed'`, `1 failed, 1 passed`.
  Failure: A Muse run that fails because a tool could not open a file is reported as "Muse is not installed in the distro" and tells the user to reinstall it. EC-30 prescribes this marker, hence Minor.
  Smallest fix: Match the wsl.exe launch text specifically, for example the `execvpe(<muse_path>) failed` line together with `muse_path`, rather than the bare ENOENT phrase.
  Spec IDs: INV-6, EC-30

R-E9 [Minor] [test quality] tests/features/harness_threads/test_harness_threads_process_bounds.py:123 — The cancellation test cannot tell "stopped before CancelledError" from "stopped afterwards", and four of the failure paths above have no test
  Evidence: `assert await wait_until(lambda: not any(alive(pid) for pid in pids), fast_stop.kill_wait + 1.0), "INV-9: the tree is stopped before CancelledError propagates"` polls for up to 2 s after `await task` has already raised. A stop running in the background after propagation would pass.
  Failure: A regression that re-raises before `stop_tree` finishes stays green. There is also no test for: a leader that exits while a descendant holds the pipes (R-E2), a cancel during Muse preparation (R-E4), a read-only skill copy (R-E7), a WSL vendor failure whose stderr contains the ENOENT text (R-E8), a cwd-planted launcher (R-E1), or a skill whose source lost a file since the copy (`wanted != present` in `_matches`).
  Smallest fix: Check `alive` once, without polling, right after `await task`, then add the listed tests next to their neighbours.
  Spec IDs: INV-9, AC-11

VERIFIED CLAIMS:
- Test pack passes: HELD (395 passed, 2 skipped).
- Repository lint loop: HELD (`SDK-LINT: PASS`, exit 0).
- Tests unchanged since the S2 helper fix: HELD (`git diff --stat 4da73cf3..01b20447 -- tests` printed nothing).
- Key only through the env overlay; records hide it in repr; validator never quotes it: HELD (code, plus the AC-4 test passes).
- Muse serve gets no META_API_KEY, and WSLENV forwards only overlay names: HELD (code at muse/launcher.py:96-109, plus tests).
- AC-16 no rebuild for unchanged skills: HELD (test passes). A read-only copy breaks the rebuild: R-E7.
- taskkill finishes within NATIVE_KILL_WAIT_SECONDS (1.0): HELD (exp7: 0.079–0.188 s).
- D-16 order "explicit, then PATH, then fallback" on Windows: DID NOT HOLD (the current folder comes first; R-E1).
- errors.py "a cap cannot cut a secret in half": DID NOT HOLD for the runner byte cap (R-E3).
- INV-9 / AC-11 "Muse temp folder removed before CancelledError": DID NOT HOLD when cancelled during preparation (R-E4).
- INV-8 "whole tree stopped on timeout" and "success within bound": DID NOT HOLD when the leader has already exited and a descendant holds the pipes (R-E2).
- INV-5 item 6 "vendor text when the vendor printed any": DID NOT HOLD for timed_out and output_too_large (R-E5).
- EC-3 / A-18 "24,000 chars keep the command line under 32,767": DID NOT HOLD (R-E6).
- INV-6 WSL not_installed only for a missing muse: DID NOT HOLD for a vendor failure that mentions ENOENT (R-E8).
- Dropped hypotheses: a planted `taskkill.exe` in the current folder was not run (exp9: `planted taskkill ran: never`). No realistic path was found for exception chaining or opencode JSON-escaping to leak the key.

COMMANDS RUN:
- `git rev-parse HEAD` → `01b20447382964132f6a11e0cbca2b0a8dce40f0` (Python 3.11.0, win32).
- `PYTHONPATH=$(pwd) timeout 600 python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `395 passed, 2 skipped in 37.97s`.
- `timeout 900 python lint/run.py < /dev/null` → `S061 IMPROVED 6 -> 5 ...`, `SDK-LINT: PASS`, `exit 0`.
- `git diff --stat 4da73cf3..01b20447 -- tests` → (empty).
- Scratch experiments in C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4ff2472d-322f-4998-ab71-29f9489aa59a/scratchpad/s4-engineering/, each run as `cd <scratch> && timeout 120 python -X utf8 <exp>.py < /dev/null`. Every run used a sandboxed HOME/USERPROFILE/PATH/TEMP, a dummy key and stand-ins only:
  - `exp1b.py` → `ERROR grok.timed_out 3.3 s; exit_code None` / `grandchild 20248 after the call: python.exe 20248 Console`
  - `exp2_muse_cancel.py` → `CancelledError reached the caller` / `tmphnzzz3c6 holds 4004 entries`
  - `exp3_cmdline.py` → `20000 double quotes -> grok.not_installed` / `20000 emoji -> grok.not_installed` / `15000 backslash/quote mix -> ran`
  - `exp5_readonly.py` → `call 1 ... ok abc123` / `call 2 skills=[] -> grok.launch_failed` / `call 3 skills=[] -> grok.launch_failed`
  - `exp6_straddle.py` → `final error present: False` / `key prefix 'xai-SECR' in str(error): True`
  - `exp7_taskkill.py` → `[0.094, 0.125, 0.094, 0.188, 0.079]`
  - `exp8_cwd_lookup.py` → `.\opencode.EXE` / `.\wsl.exe` / planted records `has_inline_config: true`, `has_meta_key: true`
  - `exp8b_cwd_grok.py` → `.\grok.EXE` / `"has_xai_key": true`
  - `exp8c` (inline) → `PATH has a grok.exe too; shutil.which("grok") -> .\grok.EXE`
  - `exp9_taskkill_cwd.py` → `call -> grok.timed_out` / `planted taskkill ran: never`
  - `exp10_timeout_stderr.py` → `code grok.timed_out | vendor_message None | 'device login' in str(error): False`
- `PYTHONPATH="<repo>;<repo>\tests\features\harness_threads" timeout 300 python -m pytest -q -p no:cacheprovider -p conftest --rootdir <scratch>/pt -o asyncio_default_fixture_loop_scope=function <scratch>/pt/test_s4_wsl_enoent.py` → `AssertionError: assert 'muse.not_installed' == 'muse.run_failed'` / `1 failed, 1 passed in 1.03s`.
