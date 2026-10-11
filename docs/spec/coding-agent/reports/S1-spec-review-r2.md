VERDICT: SOUND WITH FIXES — r2 resolves all eight round-1 findings. The Bash stop path now returns in bounded time on Python 3.11.0 and 3.13.1 (measured on the user's machine), but when the command outlives the kill it leaves the pipe transport open, and two model-facing wording gaps remain.

WHAT THE SPEC GETS RIGHT (max 4 bullets, concrete, so the author does not "fix" what works)

- **The r2 timing design holds on both interpreters, so keep it as written.** One `asyncio.wait_for(_collect, BASH_TIMEOUT_SECONDS)` covers the read and the wait. `_stop` runs on timeout and on cancellation, then waits at most `BASH_KILL_GRACE_SECONDS` and swallows only that `TimeoutError`. I reproduced the design with Git's `bin\bash.exe -c "sleep 8"`, a 2 s limit, and a 1 s grace:
  - Timeout path: 3.11.0 returned at 2.02 s, because the grace wait finished when the launcher exited. 3.13.1 returned at 3.02 s, because the grace wait timed out.
  - Cancel path, under an outer `wait_for` like `AgentRuntime._run_tool_execute` (`runtime.py:1300-1312`): `CancelledError` left `execute` at 2.01 s on 3.11 and 3.01 s on 3.13, and the outer call turned it into its own timeout.

  `except TimeoutError` catches `asyncio.wait_for`'s timeout on 3.11, because they are aliases from 3.11. In 3.12+, nested `asyncio.timeout` uses `uncancel()` counting, so a grace timeout inside the cancel handler still surfaces as `TimeoutError` and the original cancellation still propagates.
- **The lint fit of the Bash design is right.**
  - S019: the AST check needs only an `ast.Raise` inside a `CancelledError`/`BaseException`/bare handler (`s019_cancellation_propagation.py`, `visit_ExceptHandler`). The specified `except asyncio.CancelledError: await self._stop(process); raise` passes.
  - S006 is RUF006 only, and no `create_task` is used.
  - S052 is ASYNC100/105/110/220/221. `os.killpg` and `asyncio.wait_for` are not flagged.
  - S045 is ASYNC109, and no async helper takes a timeout parameter.
  - S024 counts only `if`/`for`/`with`/`try`/`match` (not `while`), with a maximum of 3. `_stop`'s try → if win32 → if returncode reaches exactly 3, and `_find_bash` is flat.
  - A007 accepts any UPPERCASE assignment in any module (`_named_constant`, `_uppercase`), so module-level `BASH_*` constants in `vidbyte/tools/builtins/bash.py` are compliant, and `vidbyte/lib/constants/` is not required.
- **D-13's choice of Git's `bin\bash.exe` launcher is correct, so do not switch to `usr\bin\bash.exe`.** I tested the real shell from a PowerShell-started Python:
  - PATH has no `<G>\usr\bin`, so the real shell cannot find `ls`, `grep`, or `sleep` ("type: ls: not found"). The launcher finds all three in `/usr/bin`.
  - Killing `usr\bin\bash.exe` directly also left `/usr/bin/sleep 8` running: the 3.13 grace wait timed out.

  The real shell would break basic commands and would not shorten the R-1 limitation. Three parents also cover all three `git` locations (`cmd`, `bin`, `mingw64\bin`), and neither `<G>\mingw64\bin\bash.exe` nor `<G>\cmd\bin\bash.exe` exists, so no wrong match is possible.
- **The R-5 to R-8 fixes are complete and internally consistent.**
  - The §8.4 budget is 2 new files, which equals the two CREATE rows in §12.3 (rows 1 and 3).
  - §9.3 lists exactly the four constants, and §8.4 counts 4.
  - Rows 1–8 match the §12.6 phases and dependency order.
  - `vidbyte/lib/constants/bash.py` and the 1,000,000 figure survive only in the §16 review log.
  - S024 appears in §11, AC-19, §12.4, and §14, and the S052 code list matches `s052_async_blocking_io.py:26`.

FINDINGS (ranked, most severe first, max 15)

R-9 [Major] [L5] §8.1 D-14, §12.3 row 1 (`_stop`), EC-14, EC-30 — When the command outlives the kill, `_stop` returns with the subprocess pipe transport still open, so every Windows timeout or cancellation under `agent.run()` prints `RuntimeError: Event loop is closed` tracebacks and leaks a pipe handle until the command exits
  Evidence:
  - The spec says `_stop` does "`os.killpg` … / `process.kill()` …; ignore `ProcessLookupError`; then `await asyncio.wait_for(process.wait(), BASH_KILL_GRACE_SECONDS)`, ignoring its `TimeoutError`". Nothing closes the transport. EC-14 says the pipe "is released only then", meaning when the command exits, but it does not name the consequence.
  - `BaseAgent.run` is `asyncio.run(self.generate_reply(...))` (`vidbyte/agents/base.py:924`), so the loop closes right after each sync run.
  - Experiment: the spec's design on 3.13.1 with default warning filters, run against `bin\bash.exe -c "sleep 6"`. After `asyncio.run` returned, stderr showed `Exception ignored in: <function BaseSubprocessTransport.__del__> … RuntimeError: Event loop is closed` and `Exception ignored in: <function _ProactorBasePipeTransport.__del__> … ValueError: I/O operation on closed pipe`.
  - The same happens on 3.11.0 even though the grace wait finished there. The launcher exited, but the orphaned command still holds the pipe, so `_try_finish` never closes the transport (`asyncio/base_subprocess.py:237-246` on 3.11).
  - With one added `process._transport.close()` after the grace wait, both versions printed nothing.
  - Typeshed's `asyncio/subprocess.pyi` `Process` declares no `_transport`, so writing `process._transport` adds a mypy error (S009 ratchet). `lint/ruff.toml` selects only TID251, so there is no private-access lint.
  - The MCP precedent never hits this, because its child does not leave a descendant holding the pipe.
  Failure: These inputs break it:
  - Windows, any Python, `agent.run("start the dev server")`, and the model runs `npm run dev`. At 600 s the `timeout` result arrives, which is correct. When `run()` returns, the developer sees two tracebacks that look like an SDK crash.
  - In a long-lived `arun` service, every timed-out command keeps a transport and pipe handle open until the orphan exits, which is never for a dev server.
  - A chatty orphan blocks once asyncio's reader pauses at about 128 KiB. If the parent's end were closed, it would instead fail its next write with a broken pipe.
  - On POSIX the same happens for EC-30 (a `setsid` descendant). The S2 tests for AC-25 and AC-27 will raise `PytestUnraisableExceptionWarning` in whatever test is running at the next GC.
  Smallest fix:
  - Make the last step of `_stop` close the process's subprocess transport, unconditionally. Closing an already finished transport is a no-op.
  - Because `asyncio.subprocess.Process` exposes no public close, reach it as `getattr(process, "_transport").close()` under an `# @intent` comment that names this leak. That form stays clean under mypy, while `process._transport` does not.
  - Add one §12.4 line ("`_stop` ends by closing the subprocess transport, so the parent never holds the pipe after the call"). Update EC-14 and EC-30 to say the parent's end is closed when the call returns.
  - Alternative, if the author rejects private access: spawn the way `asyncio.create_subprocess_exec` does internally, with `loop.subprocess_exec(<SubprocessStreamProtocol factory>, …)` then `asyncio.subprocess.Process(transport, protocol, loop)`. That keeps the public transport handle but costs a factory callback and a stream-limit constant.
  - Minimum if neither is accepted: state the leak and the stderr tracebacks in EC-14, EC-30, the `bash.py` KNOWN EDGE CASES, and the README, so the test author does not assert a clean teardown.

R-10 [Minor] [L9] §6.3 EC-10 vs §8.5 timeout contract, §12.3 row 1 — EC-10 promises an omitted-byte count for a command that prints forever, but such a command always ends in a `timeout` result, and that result has neither the count nor any truncation marker
  Evidence:
  - EC-10's trigger is "`yes`, `cat` of a huge log", and its "User sees" is "A truncated output with the omitted byte count".
  - §8.5 says the timeout result is "output = output captured so far + a final line naming BASH_TIMEOUT_SECONDS", and `metadata["error"]` is its only specified key.
  - Row 1: `_collect(process, buffer) -> tuple[int, int]` returns "(bytes not kept, exit code)". The count is a local of `_collect`, and it is lost when `wait_for` cancels `_collect`. `execute` holds only `buffer`.
  Failure:
  - `yes` never exits, so at the limit the model receives 50,000 bytes of `y` and "timed out", with no sign that output was cut. The same happens with a chatty `npm run dev` log that hides the error line the model needed.
  - A test author who binds to EC-10, or reads AC-13 as covering the time-limit case, writes a test that a correct-to-§12 implementation fails. An implementer who honors EC-10 instead has to invent a mutable counter that the spec does not describe.
  Smallest fix:
  - In the timeout result, append a truncation line without a count, for example "[output truncated at BASH_MAX_OUTPUT_BYTES bytes]", whenever `len(buffer) == BASH_MAX_OUTPUT_BYTES`. Also set `metadata["truncated"]`.
  - Reword EC-10's "User sees" so that the omitted count appears only when the command exits, and a timeout result says only that the output was cut.
  - Add both to the §8.5 result contract.

R-11 [Minor] [L5] §12.3 row 1 (description content), EC-9, AC-26 — The tool description tells the model to redirect a background process's "output" to a file, but standard error goes to the same pipe (`stderr=STDOUT`), so `server > log &` still holds the pipe and costs a 600-second wait plus a killed server
  Evidence:
  - Row 1's description content says: "a background process must redirect its output to a file, or the call waits for the time limit and the process is killed".
  - EC-9 says: "The tool description tells the model to redirect a background process's output to a file".
  - FR-9 and D-10 specify `stdout=PIPE, stderr=STDOUT`, so file descriptor 2 of every child is the same pipe.
  - AC-26 says: "a command that starts a background process with its output redirected to a file and then exits".
  Failure:
  - The model runs `python -m http.server 8000 > server.log &`. Only stdout is redirected, so the server still holds the pipe through stderr. The call blocks for the full 600 s, and then INV-11 kills the server the model wanted to keep.
  - The blind test author may write AC-26 as `sleep 100 > /dev/null &`. `sleep` holds stderr, so the test waits for the time limit, and AC-26 ("arrives as soon as the shell exits") fails against a correct implementation.
  Smallest fix: Change the wording in row 1's description content, EC-9, AC-26, and the README caveat (row 7) to "redirect both its standard output and its standard error (for instance to a file)". This changes the text only, not the code.

Round-1 findings, re-checked against r2:
- R-1 resolved. The grace bound is in D-14, §8.5, §9.3, and §12.3 row 1, and I measured it on 3.11 and 3.13. INV-11, INV-12, EC-14, A-9, Q-6, AC-25, and AC-27 are restated honestly for Windows. The new defect is R-9.
- R-2 resolved. D-17, the unconditional `_stop`, INV-25, EC-28, EC-29, AC-24, AC-26, and the §5 sequence all agree. The new defect is R-10.
- R-3 resolved, and verified against the file layout (see the third bullet of WHAT THE SPEC GETS RIGHT).
- R-4 resolved. 50,000 is the `max_chars` ceiling at `glob.py:44` and `grep.py:51`.
- R-5 resolved, with A007 verified.
- R-6 resolved. `vidbyte/tools/README.md:102` "## Priced Operation Tools" exists. The root README has no `HandoffAgent` section, so §12.5's "no change" reason holds.
- R-7 resolved. `fork.py:141` returns the same view, and `tool_error_policy.py:28` and `:142-147` match the INV-14 wording.
- R-8 resolved.

VERIFIED CLAIMS:

- Held:
  - A007 exempts UPPERCASE assignments in any module (`lint/rules/a007_operational_constants.py`, `_named_constant`). Module-level constants in `vidbyte/tools/builtins/bash.py` are compliant.
    - Implementer caution: `OPERATIONAL_CALLS` contains `read`, and `_context` walks up to the enclosing `while`. Any numeric literal inside `_collect`'s read loop (such as `max(0, …)`) is therefore flagged.
  - S019 passes `except asyncio.CancelledError: …; raise`. S006 is RUF006 only. S052 is ASYNC100/105/110/220/221 (`s052_async_blocking_io.py:26`). S045 is ASYNC109. S024 has `MAX_NESTING_DEPTH = 3` and does not count `while`.
  - Python 3.11.0 wakes `wait()` waiters in `_process_exited` (`asyncio/base_subprocess.py:221`). 3.13.1 wakes them only in `_call_connection_lost` (`:264`). 3.12 is not installed here, and CI runs 3.11 and 3.12.
    - On CI 3.11 the grace bound is never observable: `wait()` returns at shell exit even in the AC-25 `setsid` case.
    - AC-25 is an upper bound, so it still passes.
  - AC-27 timing holds on Windows for both 3.11 and 3.13, in both the timeout and cancel paths (measured, scaled down).
  - The D-13 file layout holds:
    - `C:\Program Files\Git\bin\bash.exe` is 47,000 bytes, and `usr\bin\bash.exe` is 2,553,064 bytes.
    - `mingw64\bin\bash.exe` and `cmd\bin\bash.exe` do not exist.
    - `usr\bin\bash.exe` started from a PowerShell-launched Python cannot find `ls`, `grep`, or `sleep`.
    - Killing `usr\bin\bash.exe` does not stop `/usr/bin/sleep`.
  - D-11 cites the right caps: `glob.py:44` (`max_chars`, max 50000) and `grep.py:51` (max 50000). The single-use constant precedent `code_execution.py:30-31` (`MAX_PRINT_EXPONENT`, `MAX_PRINT_INT_BITS`) holds. `_DEFAULT_SHUTDOWN_TIMEOUT = 5.0` is at `tools/mcp/transport.py:65`.
  - INV-14 matches `tool_error_policy.py:28` (`_IDEMPOTENT_PERMISSIONS = ("safe","read")`) and `:142-147` (`retry_only_idempotent=False` → retry everything).
  - INV-23 matches `fork.py:141`: `return tool if inner is tool.wrapped_tool else tool._rewrap(inner)`.
  - EC-17 matches `runtime.py:1713-1718` (`_truncate_for_tool_settings` → `ToolSettings.truncate`). EC-26 matches `runtime.py:1288-1298` (`_execute_tool` wraps any `Exception`) and `:1149-1157` (the `ToolExecutionError` error code becomes `metadata["error"]`).
  - AC-15 wording matches `runtime.py:1300-1312`: the runtime's tool timeout is `asyncio.wait_for(tool.execute(call), timeout)`, re-raised as `ToolExecutionError` with `error="timeout"`.
  - The export anchors exist:
    - `vidbyte/tools/builtins/__init__.py:8` (Architecture) and `:27` (`code_execution` import, so `bash` sorts before it);
    - `vidbyte/agents/__init__.py:8`, `:28` (codex block), and `:61` (`context_algorithms`), with `"CodexUsageResponse"` and `"ContinualTraceAgent"` adjacent at `:358-359`;
    - `vidbyte/__init__.py:12` ("Agent exports" line) and `:97-98` (`CodexUsageResponse,` then `FinalizationContext,`).
  - The README anchors exist. `vidbyte/agents/README.md` has "## Usage" (:30) and "## Key Modules" (:195). `vidbyte/tools/README.md` has the `builtins/` bullet (:89), "## Priced Operation Tools" (:102), and the "compact summary" text (:120).
  - pytest config has no `filterwarnings = error`, so R-9's warnings do not fail the gate. They are noise and a leak, not a red build.
- Partly true: §8.2 "bounded shutdown wait — `McpStdioTransport.close`". The wait after `terminate()` is bounded, but the wait after `kill()` is not (`transport.py:295-296`, `await process.wait()`). r2's `_stop` is stricter than the precedent it cites. The implementer must not copy the second wait, and §12.4's "No unbounded wait on the child" line already forbids it.
- Boundary of A-2, not verified because scoop is not installed here: a scoop or `git.portable` shim `git.exe` is a small exe, not a symlink, so `Path.resolve()` does not follow it. The lookup then returns `bash_not_found` even though Git is installed. A-2's "standard layout" already excludes this, and the stock Chocolatey `git` and winget packages use the standard installer layout.
- Not reproduced (no POSIX host here, and WSL is broken): the POSIX `killpg` behavior. I reasoned it from the stdlib source only. Linux keeps a PID number unallocated while it is still a process-group id, so `killpg` after the leader is reaped targets the right group for EC-29.
