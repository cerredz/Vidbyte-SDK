LENS: conformance (post-repair re-review)
VERDICT: MERGEABLE AFTER FIXES — all 14 repairs hold against their review evidence, but the R-11 fix opened a cancellation hole in the new post-exit wait, and the R-4 claim "never look up a program in the current folder" still fails for the bare `taskkill` launch on default Windows settings.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- R-11's exit signal works. `CliExitProtocol.process_exited` ends the run when the leader exits. A Grok stand-in that prints its answer and leaves a grandchild holding the pipes now returns `text='grok answer to: hi'` in 1.2 s, on Python 3.11 and 3.13 alike. A plain run still reads all output, and nothing calls `stop_tree` for it (probe r11: `stop_tree calls=0`). Do not go back to `Process.wait()`.
- R-4's lookup is now one canonical walk. `CliRunner.find_program` is the only lookup for `NativeLauncher.resolve`, `MuseLauncher.resolve` (wsl.exe) and `CliRunner.run`. Planted `grok.exe`, `opencode.exe` and `wsl.exe` files in the current folder never start (0 starts). Default, explicit bare and WSL lookups give `not_installed` or `wsl_unavailable`, and an explicit absolute command still runs.
- The new error paths scrub the key. Timeouts and output caps now carry the vendor's stderr, with the key replaced by `<redacted>` (probe r6: Grok, opencode and Muse timeouts, and the Grok cap). `runtime.error` names the workspace and the caller's thread on all three harnesses, and it never copies the exception text, even a `KeyError(<key>)`.
- The repair stays inside its bounds. It adds 24 files (unchanged), plus exactly the pre-authorized `CliExitProtocol` and `ShellFlag`, with no dependency. It changed no test since `91625f11`, made no `lint/` change, and added no suppression. It changed the spec only in §17. Every touched code file is a §12.3 row, and the AC-1 snippet runs green.

FINDINGS (ranked, most severe first, max 15)
R-RR1 [Major] [fix regression: INV-9 / FR-11] vidbyte/lib/process/runner.py:199-205 — a cancel that lands during the new post-exit reader wait skips the tree stop and leaks both reader tasks
  Evidence: The post-exit wait sits outside the `try` that handles `asyncio.CancelledError`:
  ```
  # Give the readers one kill wait to reach the end of the
  # output. A reader still open after it means a descendant holds
  # the pipes, so the whole tree is stopped; ...
  if await self._finish_readers(readers) and not timed_out:
      await ProcessStopper.stop_tree(...)
  ```
  Only the `try` above it (feed stdin, `exited.wait()`) has the `except asyncio.CancelledError: stop_tree … _finish_readers … raise` branch. `probes.py r11` uses a Grok stand-in with `grandchild=True` and cancels 0.3 s after `process_exited`. On 3.11 and on 3.13 (venv313) it prints `R11 cancel-window: CancelledError reached the caller` and then `stop_tree calls after cancel=0; reader tasks still pending=2`.
  Failure: This happens in R-11's own scenario: the CLI exits while a descendant, such as an MCP server with inherited stderr, holds the pipes. If the caller cancels within `NATIVE_KILL_WAIT_SECONDS` of the exit, `CancelledError` propagates without `ProcessStopper.stop_tree`. On POSIX, the descendant in the leader's process group is never signalled, so the call leaves a process behind (FR-11, AC-11). On both platforms, the two `_drain` tasks stay pending and the transport stays open until the descendant exits. Before the repair, the run was still inside the guarded `asyncio.wait(readers)` here, so a cancel did stop the tree.
  Smallest fix: Move `held = await self._finish_readers(readers)` and its conditional `stop_tree` into the existing `try`, after the `async with asyncio.timeout(...)` block. The existing `except asyncio.CancelledError` then covers it, and `TimeoutError` cannot come from there.
  Spec IDs: INV-9, FR-11, AC-11, INV-8

R-RR2 [Major] [verified claim does not hold: R-4 coverage] [partly out-of-lens] vidbyte/lib/process/runner.py:87 — `ProcessStopper` still starts `taskkill` by bare name, so default Windows runs a `taskkill.exe` from the caller's current folder on every timeout, cancel and post-exit tree stop
  Evidence: The code is `return await asyncio.create_subprocess_exec(*native_threads.NATIVE_TASKKILL_ARGUMENTS, str(pid), ...)`, with `NATIVE_TASKKILL_ARGUMENTS = ("taskkill", "/T", "/F", "/PID")` (constants:66). The same file's R-4 header says: "On Windows a bare program name is looked up only in the absolute PATH folders with PATHEXT, and one found in none of them is not started, because CreateProcess would search the current folder". Commit `f64ba4b8` is titled "never look up a program in the current folder". `taskkill_cwd.py` plants stand-ins named `taskkill.exe` and `whoami.exe` in the current folder and starts each by bare name, as `_start_taskkill` does. In the agent shell, which sets `NoDefaultCurrentDirectoryInExePath`, it prints `planted stand-ins started: 0`. With `env -u NoDefaultCurrentDirectoryInExePath`, which is the Windows default, it prints `taskkill exit 2 | stdout head: b''` and `planted stand-ins started: 2`.
  Failure: A caller runs a script from a cloned repository that ships a `taskkill.exe`. Every Grok, opencode or Muse call that times out, is cancelled, or (new with R-11) ends while a descendant holds the pipes then runs the repository's program, with the caller's full environment. In the §4 usage, that environment holds `XAI_API_KEY` and `DEEPSEEK_API_KEY`. The SDK's per-call key is not in `os.environ`, so INV-2 holds. This is the T-6 / R-4 code-execution class. S4's exp9 ("planted taskkill ran: never") and the verifier's decision not to widen R-4 rested on a shell with `NoDefaultCurrentDirectoryInExePath` set.
  Smallest fix: Start taskkill by an absolute path. One way is `CliRunner.find_program(<taskkill name constant>)`, because System32 is on PATH. Another is `%SystemRoot%\System32\taskkill.exe`. When it is not found, `_start_taskkill` returns `None`, which keeps the leader-kill fallback. A regression test must `monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)`, or it cannot fail in this shell.
  Spec IDs: T-6, D-16, §17 deviation 15 ("never in the current folder")

R-RR3 [Minor] [user's words and spec boundary: EC-3, §9.1, D-20] vidbyte/lib/dataclasses/native_threads.py:99, vidbyte/lib/dataclasses/validation.py:64 — on Windows the Grok and Muse prompt cap became "24,000 quoted UTF-16 units", which refuses prompts at the cap that §9.1 and EC-3 allow
  Evidence: The record calls `RecordFieldValidator.require_command_line_units(self.prompt, "prompt", max_units=NATIVE_ARGV_PROMPT_MAX_CHARS)`. `probes.py r8` (win32) gives:
  - `24000 chars, prose with spaces quoted_units=24002 -> configuration.invalid_argument | prompt must take at most 24000 UTF-16 code units once quoted for the Windows command line; got 24002.`
  - `23999 chars, one space -> configuration.invalid_argument`
  - `23000 chars incl 1001 quotes -> configuration.invalid_argument`
  - `23000 chars incl 1000 quotes (24000 units) -> ran`
  - `opencode 24001 quotes -> ran`

  §9.1 says the prompt is "at most … NATIVE_ARGV_PROMPT_MAX_CHARS for Grok and Muse". EC-3's trigger is a "Prompt longer than NATIVE_ARGV_PROMPT_MAX_CHARS (24,000)". D-20 calls the 24,000-character cap the bound "under the Windows command-line limit". `test_prompt_at_the_harness_cap_still_runs` uses `"p" * cap`, which has no space, so it cannot see this.
  Failure: On win32, a 23,999- or 24,000-character prose prompt is refused. So is a prompt heavy in code or JSON, once its characters plus its `"` count pass 24,000, even though the command line would fit the OS's 32,767 units with about 8,700 to spare. The refusal itself is clear: it names `prompt`, the cap 24000 and the cause. opencode is unaffected.
  Decision (asked by the orchestrator): The spec's cap is a character cap, and its headroom under 32,767 is what protects the launch (D-20). The repaired rule is a stricter rule that the spec does not state: it reuses the character number as a unit cap. The rule was prescribed by review R-8, recorded as deviation 18, and refuses with an accurate message, so it does not block the merge.
  Smallest fix: Keep the 24,000-character check, and compare the quoted units with a separate named ceiling, for example `NATIVE_WINDOWS_ARGV_PROMPT_MAX_UNITS = 30000`, which leaves about 2,700 units for the launcher, workspace and options. If the owner prefers the stricter rule instead, amend EC-3 and §9.1 to say "on Windows, at most 24,000 UTF-16 units once quoted".
  Spec IDs: EC-3, §9.1, D-20, AC-5

R-RR4 [Minor] [fix completeness: R-10, INV-9] vidbyte/harnesses/native/muse/threads.py:162-171 — a second cancel while `_discard` waits leaves the Muse temp folder, with its skill copies, behind for good
  Evidence: `_discard` runs `await asyncio.wait({preparing})` unshielded, and the removal comes only after it. `probes.py r9` cancels `run_muse_thread` mid-copy (a 1 s `replace`) at 0.3 s, then again at 0.5 s. It prints `R10 double-cancel leftovers after 1.5s: ['tmpj2nkxlxu']`. With a single cancel it prints `R10 temp leftovers right after: []`.
  Failure: Nested timeouts, `wait_for` inside a cancelled task, or a second Ctrl-C can cancel twice. The second cancel interrupts the wait before the removal is scheduled. INV-9 and AC-11 say "the Muse temp folder is gone", and EC-34 excuses only a removal that fails.
  Smallest fix: In the `except asyncio.CancelledError` branch, wrap the wait-then-remove in one task and `await asyncio.shield(...)` it, as the preparation already is.
  Spec IDs: INV-9, AC-11, EC-34

FIX CONFIRMATIONS:
- R-1: confirmed. Width check over every changed `vidbyte/` file leaves only `lib/errors/base.py` (9) and `lib/enums/failure.py` (6), which equal origin/main.
- R-2: confirmed. `git grep MUSE_REAP_STDIN_SWITCH` finds nothing, and the reap passes `ShellFlag.READ_STDIN`, which `CliArgv.build` turns into `"-s"`. The WSL tests are green.
- R-3: confirmed. A call-depth scan of every changed `vidbyte/` module at dcc30e74 finds 1 chain, main's `FailureCode.from_exception`.
- R-4: confirmed for the four named sites (probe r4: planted programs started 0; explicit absolute command runs). It is incomplete for `ProcessStopper`'s taskkill (R-RR2).
- R-5: confirmed. No `json.loads(line)` or inline thread-id `fullmatch` remains outside `CliRunner.json_objects`. `accepts_text` is `_text_problem(..., allow_blank=False) is None`, the same rule. Muse keeps its exact comparisons.
- R-6: confirmed. All 8 timeout and cap sites pass `vendor_text=outcome.stderr`. Probe r6: `vendor_message` holds the stderr text, the key is absent from `str`, the args and `vendor_message`, and `<redacted>` is shown.
- R-7: confirmed. Probe r7 (fork Grok, continue opencode, continue Muse): `thread_id='abc123'`, and the workspace and thread are named before the observation. `KeyError(<key>)` text is not copied.
- R-8: confirmed for its evidence: dense prompts become `configuration.invalid_argument` naming `prompt` and 24000, and WinError 206 maps to `OS_ERROR`. The prompt-cap boundary is stricter than the spec (R-RR3).
- R-9: confirmed. Probe r9: Grok calls 1 to 3 return ok, Muse leaves no temp folder, and the caller's file stays read-only.
- R-10: confirmed for a single cancel (`CancelledError` after 0.70 s, no leftovers). The double-cancel gap is R-RR4.
- R-11: confirmed. The answer comes back on 3.11 and 3.13, and a plain run has no tree stop. The new cancel window is R-RR1.
- R-15: confirmed. `NATIVE_VENDOR_TEXT_SENTENCE = 'The vendor printed: "{vendor_text}".'`
- R-16: confirmed. `GROK_HOME_UNKNOWN_DETAIL` ends with "set HOME (POSIX) or USERPROFILE (Windows) for this process."
- R-17: confirmed. The dataclass header's "three rules … raise ConfigurationError inline" matches lines 131, 146 and 149. The validator's ROLE line is now true through `accepts_text`, but it still leaves out the three `threads.py` callers of `require_instance` (cosmetic).

VERIFIED CLAIMS:
- "No file was added; 24 added Python files vs origin/main": HELD (`git diff --name-status --diff-filter=A origin/main...dcc30e74 -- 'vidbyte/*.py' | wc -l` gives 24).
- "No test changed": HELD (`git diff 91625f11..dcc30e74 -- tests` is empty, and the test tree vs main holds only `A` entries, 18). `lint/` diff is empty, and the repair added no `noqa`, `type: ignore` or `nosec`: HELD.
- Each `fixed @sha` touches the files its review row names: HELD (14 `git show --stat`).
- The repair edited the spec only to add §17 rows: HELD.
- Deviation 15, "never in the current folder": HELD for `find_program` and its three callers. NOT HELD for the runner module as a whole, because `_start_taskkill` uses a bare name (R-RR2).
- Deviation 16, the shared helpers' callers (json_objects ×3 readers, accepts_text ×4, wrong_thread for Grok and opencode): HELD.
- Deviation 17, "every timeout and output-cap failure passes stderr": HELD (8 sites, `git grep TIMED_OUT|OUTPUT_TOO_LARGE`).
- Deviation 18, quoted-units refusal and "15,000-char backslash/quote mix now refused": HELD, and it is stricter than §9.1 and EC-3 (R-RR3).
- Deviation 20, a cancel mid-preparation removes the folder: HELD for one cancel, NOT HELD for two (R-RR4).
- Deviation 21, "run ends at the leader's exit": HELD on 3.11 and 3.13. Its cancellation path is unguarded (R-RR1).
- Budget: +1 class (`CliExitProtocol`), +1 enum (`ShellFlag`), 0 dependencies, all touched code files are §12.3 rows, every new constant has a reader, and `runner.py` has 339 lines (under 500). HELD.
- S4's exp9, "a planted taskkill.exe never runs": NOT HELD outside the agent shell, because the shell sets `NoDefaultCurrentDirectoryInExePath`.
- AC-1: HELD. The test SNIPPET equals spec §4, the run prints 3 lines, the fork id differs, and the workspace is untouched.

COMMANDS RUN:
- `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/harness_threads` → `428 passed, 2 skipped in 42.16s`
- `python lint/run.py` → `S009 RATCHETED: 350 known finding(s)` … `SDK-LINT: PASS`
- `python -X utf8 <scratch>/s4-conformance/snippet_ac1.py "$(pwd)"` (stand-ins on PATH, redirected home) → `test SNIPPET == spec section 4: True` / `returncode: 0` / 3 lines / `fork id differs: True` / `workspace entries after run: []`
- `python <scratch>/s5-rereview/depth.py dcc30e74 <changed vidbyte .py>` → `vidbyte/lib/enums/failure.py: FailureCode.from_exception -> _from_exception_name -> _from_exception_fallback` / `chains: 1`
- `awk 'length($0) > 72' | grep -cE '^\s*#'` per changed file, now vs main → `failure.py now=6 main=6`, `base.py now=9 main=9`
- `git diff --stat origin/main...dcc30e74 -- lint/` → empty; `git diff --stat 91625f11..dcc30e74 -- tests` → empty; `git diff --name-status origin/main...dcc30e74 -- tests | grep -v '^A'` → empty
- `git grep -n "MUSE_REAP_STDIN_SWITCH\|shutil.which(\|fullmatch(native_threads.NATIVE_THREAD_ID\|json.loads(line)" dcc30e74 -- vidbyte` → only `lib/process/runner.py:281` (json_objects) and main's `tools/` files
- `PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-rereview/probes.py "$(pwd)" r8 r7 r4` → R8 lines above; `R7 grok/opencode/muse: runtime.error thread_id='abc123' ws in msg=True thread in msg=True key in msg=False`; `R4 planted programs started: 0`; `R4 explicit absolute -> a8e4d94d`
- `… probes.py "$(pwd)" r11 r9` → `R11 normal: … in 1.2s; stop_tree calls=1`; `R11 plain run: … stop_tree calls=0`; `R11 cancel-window: stop_tree calls after cancel=0; reader tasks still pending=2`; `R9 grok call 1..3 -> ok`; `R10 CancelledError propagated after 0.70s`; `R10 double-cancel leftovers after 1.5s: ['tmpj2nkxlxu']`
- `<scratch>/s5-repair-1/venv313/Scripts/python.exe … probes.py r11` (3.13.1) → same four R11 lines
- `… probes.py "$(pwd)" r6` → `grok.timed_out | vendor_message has 'device login': True | key in str: False | key in vendor_message: False | … redacted shown: True` (also `grok.output_too_large`, `opencode.timed_out`, `muse.timed_out`)
- `PYTHONPATH=$(pwd) python -X utf8 <scratch>/s5-rereview/taskkill_cwd.py "$(pwd)"` → `planted stand-ins started: 0` / `NoDefaultCurrentDirectoryInExePath set: True`; the same run with `env -u NoDefaultCurrentDirectoryInExePath` → `taskkill exit 2` / `planted stand-ins started: 2`

(`<scratch>` = `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4ff2472d-322f-4998-ab71-29f9489aa59a/scratchpad`)
