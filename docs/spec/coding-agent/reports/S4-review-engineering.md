LENS: engineering
VERDICT: MERGEABLE AFTER FIXES — the process-control core is sound on the main paths and the pack is strong, but `_stop` breaks its own "never raises / always closes" contract on two reachable paths, the Windows bash lookup trusts the current folder, `root_dir=""` silently means the current folder, and the EC-11 stdin test cannot fail under the gate.

Reviewed: `git diff origin/main...4e285d91` (code identical at HEAD `6345baa2`; that commit changes only `docs/spec/coding-agent/pipeline.md`).

WHAT THE IMPLEMENTATION GETS RIGHT
- One `asyncio.wait_for(self._collect(process, buffer), BASH_TIMEOUT_SECONDS)` over reading and waiting, with the caller-owned `buffer` (bash.py:109-111), so output captured before a timeout survives cancellation of `_collect`. The only `process.wait()` calls are bounded (bash.py:163 under the 600 s limit, bash.py:182 under the grace). WSL 3.12.3 runs the setsid AC-25 and the AC-28 pipe-close cases green.
- The stop policy matches D-14. On POSIX, `os.killpg` runs on every stop, even after the shell has exited (bash.py:177-178). Nothing is stopped after a normal completion (bash.py:126). AC-15 and AC-26 fail for the right reason, and AC-13/AC-29 catch a cap+1 off-by-one (mutation run below).
- `_FetchedPagesView` changes only `output`, and only for a SUCCESS result carrying a `FetchPayload` (coding.py:168-174). Metadata stays the wrapped tool's object. The runtime prices the unwrapped tool (runtime.py:1200 → activity.py:67-69 → base.py:145-150). Fork returns the same view object, because the priced tools have no `clone_for_fork` or `_manager` (fork.py:138-141), so INV-23 holds.
- Each key is validated without echoing it, is held only inside its provider client, and selects exactly one provider. Construction spawns nothing and opens no socket: `BashTool.__init__` does only `Path.resolve` and `shutil.which`.

FINDINGS

R-E1 [Blocker] [test quality] tests/features/coding_agent/test_bash_tool_contract.py:127-134 — The EC-11 stdin test cannot fail under the gate: removing `stdin=DEVNULL` (bash.py:142) still passes.
  Evidence: pytest's default `--capture=fd` puts the null device on fd 0 for every test, so a child that inherits stdin already sees end-of-file. `scripts/run_ci.py:93` runs plain `python -m pytest`, and `pyproject.toml` addopts set no `-s`. Mutation in-process (patched `asyncio.create_subprocess_exec` to drop `stdin`):
    Windows 3.11: `1 passed in 0.09s  PYTEST EXIT 0`
    WSL 3.12.3, fd 0 = a live pipe that never closes: default capture → `1 passed in 0.06s  PYTEST EXIT (default fd capture) 0 mutant spawns: 1`; with `-s` → `FAILED ... output='\n[command stopped: it did not finish within the 10-second time limit]'  PYTEST EXIT (-s, live stdin) 1`
  Failure: an implementer drops `stdin=DEVNULL`. CI stays green. In an IDE, a service, or Jupyter, where fd 0 is a live pipe or TTY, `read`, `cat`, or a password prompt then hangs each call for 600 s (EC-11 regressed). The test plan's claim "An inherited stdin makes `read` wait for the time limit" is false under the gate.
  Smallest fix: (test only) for the duration of the test, give the process a stdin that never reaches end-of-file. Do `r, w = os.pipe(); saved = os.dup(0); os.dup2(r, 0)` inside `capfd.disabled()` or after it, and restore `os.dup2(saved, 0)` in `finally`. The pytest-managed fd 0 is the null device, so the redirect must happen after capture is suspended. Then assert `read-status:1` arrives well under the limit.
  Spec IDs: EC-11, D-10, FR-9

R-E2 [Major] [failure modes] vidbyte/tools/builtins/bash.py:176-180 — `_stop` lets a `PermissionError` from `os.killpg` escape. It replaces `CancelledError` (INV-12), replaces the timeout result (INV-11), and skips the transport close (INV-26).
  Evidence: `with contextlib.suppress(ProcessLookupError): ... os.killpg(process.pid, signal.SIGKILL)`. Spec §12.3 row 1 and D-18 say "`_stop` never raises", and S3 "tricky part" 2 concedes the gap. I simulated EPERM in WSL 3.12.3 by patching `os.killpg` to kill and then raise `PermissionError` (the WSL user is root, so a real EPERM cannot be produced there):
    `timeout path: execute RAISED PermissionError instead of returning the timeout result`
    `timeout path: transports left open -> 1` (followed by asyncio's `Loop ... that handles pid 20 is closed`)
    `cancel path: task returned -> loop continued after PermissionError | task.cancelled() = False` (wrapper shaped like `AgentRuntime._execute_tool`, runtime.py:1287-1297, which turns any `Exception` into a `ToolExecutionError`)
  Failure: the setup is a POSIX host where the agent runs as a non-root user with passwordless sudo (GitHub-hosted runners, dev VMs). The model runs `sudo tail -f /var/log/app.log &`, and the shell exits. Only root-owned processes are left in the group and they hold the pipe, so the call reaches the limit or is cancelled. `killpg` then returns EPERM, because Linux reports EPERM when no member could be signalled.
  - Timeout path: `execute` raises, and the model sees "Tool execution failed: [Errno 1] Operation not permitted" instead of the timeout result with output so far.
  - Cancel path: the caller's cancellation is swallowed and the agent loop keeps running.
  - Both paths: the grace wait and the transport close are skipped, so the pipe leaks.
  Same line, lower probability: once a group is empty and its leader has been reaped, the unconditional `killpg` can hit a reused PGID.
  Smallest fix: `contextlib.suppress(ProcessLookupError, PermissionError)` (or `OSError`) around the kill. Nothing more can be done for an unsignallable group, and the bounded wait plus the close still run. Add one pack test that patches `os.killpg` to raise `PermissionError` and asserts both that the cancel re-raises and that `left_open == []`.
  Spec IDs: INV-12, INV-11, INV-26, D-18, §12.4 ("`_stop` never raises")

R-E3 [Major] [failure modes] vidbyte/tools/builtins/bash.py:181-185 — A second cancellation during `_stop`'s grace wait skips the transport close, so INV-26 ("always") breaks.
  Evidence: the close comes after an awaited wait, with no `try/finally`. WSL 3.12.3, setsid descendant holding the pipe, grace 2 s:
    `1 cancel(s): CancelledError after 2.01s; transports left open -> []`
    `2 cancel(s): CancelledError after 0.51s; transports left open -> ['<_UnixSubprocessTransport pid=63 returncode=-9 stdout=<_UnixReadPipeTransport fd=7 polling>>']`
  Failure: `ToolSettings.tool_timeout_seconds` cancels the call (runtime.py:1307). While `_stop` waits, a second cancellation arrives from a run-level timeout, a caller `task.cancel()`, or `asyncio.run` shutdown. The grace wait always lasts the full 5 s in two cases: on Windows with Python 3.12+ (EC-14 orphan), and on POSIX with a setsid holder. In those cases the window is the whole grace. Effects: the read-pipe fd stays registered and open, a long-lived service leaks one pipe per occurrence, and `asyncio.run` prints "Event loop is closed" at shutdown. This is exactly the R-9 defect D-18 was written to remove.
  Smallest fix: `try: <kill>; <bounded wait> finally: <getattr(process, "_transport", None) close>`. This also covers the R-E2 escape. Add a pack test: cancel, sleep briefly, cancel again, assert `left_open == []`.
  Spec IDs: INV-26, D-18, AC-28

R-E4 [Major] [security] vidbyte/tools/builtins/bash.py:57-61 — On Windows, `shutil.which("git")` searches the process's current folder before PATH. A `git.exe` or `git.cmd` planted in the current folder therefore chooses the bash executable for every call. This breaks INV-15/FR-11 ("git executable on PATH").
  Evidence: Python 3.11's `which()` source says "The current directory takes precedence on Windows." Probe from `C:\Program Files\Git\cmd` with `PATH=/c/Windows/System32`, which holds no git:
    `git on PATH entries? False`
    `shutil.which('git') -> '.\\git.EXE'`
    `BashTool._executable -> C:\Program Files\Git\bin\bash.exe`
  The lookup was satisfied from the current folder, not from PATH.
  Failure: a developer on Windows (the user's platform) runs an agent from inside a cloned, untrusted repository, for example `cd repo && python agent.py` with `root_dir="."`. If the repo contains `git.cmd` (PATHEXT) and `bin\bash.exe`, `_find_bash` returns `<repo>\bin\bash.exe`. Every bash call then runs the attacker's binary, including a command a human or approval middleware accepted as `git status`. This is a shorter path to harm than T-2: no prompt injection or model decision is needed, and the command text no longer predicts what runs. A real git on PATH does not help, because the current folder wins.
  Smallest fix: `if git is None or not os.path.isabs(git): return None`. A current-folder hit comes back relative (`.\git.EXE`), so this keeps lookups to PATH only, as INV-15 states. A POSIX-host test can simulate it the way AC-22 does, by having `which` answer `".\\git.exe"`.
  Spec IDs: INV-15, FR-11, D-13, T-2

R-E5 [Major] [failure modes / input validation] vidbyte/agents/coding.py:101-103 — `root_dir=""` passes validation and silently roots all seven tools, with allow-all WRITE and EXECUTE, at the process's current folder.
  Evidence: `not Path(root_dir).is_dir()` is False for `""`, because `Path("")` is `.`. Probe: `root_dir='' -> C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-coding-agent | equals cwd: True | policy allowed: ['execute', 'read', 'safe', 'write']`.
  Failure: `CodingAgent(..., root_dir=os.environ.get("PROJECT_DIR", ""))` with the variable unset is the same input as EC-2, which the spec rejects for keys. Write, edit, and bash then operate on whatever folder the service was started in. D-8 rejects this outcome by name: "should not silently default to the process working directory". AC-11's cases (missing, file, 42, None, omitted) have no `""` case, so no test catches it.
  Smallest fix: in `_resolve_root`, also reject `isinstance(root_dir, str) and not root_dir.strip()` with the same `ConfigurationError`, and add `""` to the AC-11 parametrization.
  Spec IDs: FR-3, D-8, EC-6, AC-11

R-E6 [Minor] [error handling] vidbyte/tools/builtins/bash.py:147-148 — The `spawn_failed` hint always reads "Shorten the command or remove NUL characters from it." The same branch also catches a missing or removed root folder, a bash removed after construction, and EACCES.
  Evidence: `BashTool("C:/no-such-root-folder-s4-probe")` → `error {'error': 'spawn_failed'} | bash could not start this command (NotADirectoryError). Shorten the command or remove NUL characters from it.`
  Failure: when the root folder is deleted mid-run, the model is told to rewrite a command that is fine, and it spends iterations shortening commands.
  Smallest fix: choose the hint by exception class. `ValueError`, or `OSError` with errno E2BIG, keeps the current hint. Any other `OSError` says the root folder or the bash executable could not be used. The text still names only the class (S017).
  Spec IDs: EC-15 (it lists only NUL and the argument limit), S017

VERIFIED CLAIMS
1. S3: "Windows 3.11: 86 passed, 11 skipped" — HELD (`86 passed, 11 skipped in 4.94s`).
2. S3: "WSL 3.12: 97 passed" — HELD (`97 passed in 17.18s`).
3. §12.4 / INV-20 / INV-21: fetch.py, the filesystem and code-search tools, base.py, security.py, filesystem.py, lint/, and tests outside the pack are byte-identical to main — HELD (the scoped `git diff --stat` is empty).
4. AC-20 / C016: `generate-sdk-public-api.py --check` passes — HELD (`contracts/sdk-public-api.json is current ... 594 exports`, exit 0).
5. D-18 / §12.3 row 1: "`_stop` never raises" — NOT HELD for `PermissionError` (R-E2).
6. INV-26: "always ends by closing the subprocess transport" — NOT HELD under a second cancellation (R-E3).
7. Test plan EC-11 row: "An inherited stdin makes `read` wait for the time limit" — NOT HELD under the gate's pytest capture (R-E1).
8. Test plan AC-29 row: it catches a result that "keeps more than the cap" — HELD. The cap+1 mutant fails AC-29 (`assert 1002 == 1000`) and AC-13.
9. FR-3: "rejects anything that is not an existing directory" — NOT HELD for `""` (R-E5).
10. INV-15: bash comes from git "on PATH" — NOT HELD on Windows, where the current folder is consulted first (R-E4).
11. INV-23: fork reuses the same `_FetchedPagesView` — HELD (priced tools have no `clone_for_fork`/`_manager`; fork.py:141 returns `tool`).
12. INV-16 pricing: the runtime unwraps the view before pricing — HELD (runtime.py:1200; activity.py:67-69).
13. NFR-1 size budget: coding.py 177 ≤ 200 and bash.py 194 ≤ 250 — HELD.
14. INV-7: an explicit `permission_policy=None` gets allow-all, and a deny-all caller policy is kept as the same object — HELD (`deny-all policy kept as same object: True []`).

Hypotheses I tried and refuted (not findings): a multi-byte split at the cap gives one U+FFFD and never raises (the whole buffer is decoded once); a page with empty content is still listed by the view; a caller tool named `bash` is rejected (AC-8); explicit `None` and an omitted policy behave the same (claim 14); the stream buffer stays bounded at 64 KiB per read plus the cap.

COMMANDS RUN
- `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/ -p no:cacheprovider` (Windows 3.11.0) → `86 passed, 11 skipped in 4.94s`
- `wsl.exe -d MuseUbuntu1 ... /tmp/s2-coding-agent-venv/bin/python -m pytest -q -p no:cacheprovider tests/features/coding_agent/` (3.12.3) → `97 passed in 17.18s`
- In-process mutation, `stdin` dropped from `create_subprocess_exec`, EC-11 test (Windows) → `1 passed ... PYTEST EXIT 0`
- Same mutation in WSL with fd 0 = live pipe → default capture `PYTEST EXIT ... 0 mutant spawns: 1`; with `-s` → `FAILED ... 10-second time limit ... PYTEST EXIT (-s, live stdin) 1`
- WSL probe, setsid holder, single vs double cancel → `1 cancel(s): ... left open -> []` / `2 cancel(s): ... left open -> ['<_UnixSubprocessTransport pid=63 returncode=-9 ...>']`
- WSL probe, `os.killpg` patched to raise `PermissionError` after killing → `execute RAISED PermissionError` / `transports left open -> 1` / `loop continued after PermissionError | task.cancelled() = False`
- Windows probe from `C:\Program Files\Git\cmd`, PATH without git → `shutil.which('git') -> '.\\git.EXE'`, `BashTool._executable -> C:\Program Files\Git\bin\bash.exe`
- Windows probe `CodingAgent(..., root_dir="")` → `equals cwd: True | policy allowed: ['execute', 'read', 'safe', 'write']`
- Windows probe `BashTool("C:/no-such-root-folder-s4-probe")` → `spawn_failed ... (NotADirectoryError). Shorten the command or remove NUL characters from it.`
- WSL cap+1 `_collect` mutant against AC-29 and AC-13 → both fail (`assert 1002 == 1000`)
- `git diff --stat origin/main...4e285d91 -- <untouchable paths>` → empty
- `python scripts/generate-sdk-public-api.py --check` (PYTHONPATH unset) → `is current at 1bb1d3b4 ... 594 exports`, exit 0
- Leftover check: `pgrep -a "sleep|yes"` in WSL → `no stray processes`. On Windows, `Get-CimInstance Win32_Process` for bash.exe/sleep.exe → none. No background commands were started.
