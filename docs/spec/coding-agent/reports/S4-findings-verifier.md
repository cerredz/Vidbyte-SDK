# S4 findings verifier — report

**Stage:** S4, step 2 (merge and verify)
**Code under review:** `origin/main...4e285d91`. HEAD `8234dd95` adds only `docs/`, and `git diff --stat 4e285d91 HEAD` touches only `docs/spec/coding-agent/*`.
**Output:** `docs/spec/coding-agent/review.md`
**Write policy:** Nothing else in the repo was written. All probe scripts lived in the session scratchpad, outside the repo: `C:/Users/422mi/AppData/Local/Temp/claude/C--Users-422mi-vidbyte-repos/4426ec87-fc85-4db1-bd08-64dcd6007841/scratchpad/`. `git status --short` was empty after every run.

## 1. Merge map

| Original | Lens / severity | Merged | Merged severity | Note |
|---|---|---|---|---|
| R-C1 | conformance / Blocker | **R-1** | Blocker | `_stop` close skipped on cancel during grace wait |
| R-E3 | engineering / Major | **R-1** | Blocker | same failure as R-C1 (second cancel) |
| R-C2 | conformance / Major | **R-1** | Blocker | `PermissionError` from `killpg` escapes `_stop` |
| R-E2 | engineering / Major | **R-1** | Blocker | same as R-C2 |
| — `[verifier]` | — | **R-1** | Blocker | `transport.close()` → `Popen.kill()` raises `PermissionError` when the leader is alive; the reviewers' fix is incomplete |
| R-E1 | engineering / Blocker | **R-2** | Blocker | EC-11 test cannot fail under fd capture |
| R-C3 | conformance / Major | **R-3** | Major | `root_dir=""` accepted |
| R-E5 | engineering / Major | **R-3** | Major | same |
| R-C4 | conformance / Minor | **R-4** | Major (raised) | "always the last line" false for error results |
| R-V3 | conventions / Minor | **R-4** | Major (raised) | "is stopped" false on Windows; EC-14 requires the statement |
| R-V6 | conventions / Minor | **R-4** | Major (raised) | 6 sentences against the field guide's 4–5 |
| R-C5 | conformance / Minor | **R-5** | Minor | README `restore()` text |
| R-V2 | conventions / Minor | **R-5** | Minor | same, plus the `coding.py:5` header |
| R-V4 | conventions / Minor | **R-6** | Minor | `spawn_failed` hint |
| R-E6 | engineering / Minor | **R-6** | Minor | same |
| R-V5 | conventions / Minor | **R-7** | Minor | tests README folder |
| R-V1 | conventions / Major | **R-8** | Minor (downgraded) | `_FetchedPagesView` placement |
| R-E4 | engineering / Major | **R-9** | Minor (downgraded, `[scope-adding]`) | Windows `which("git")` searches the current folder first |

**Totals:** confirmed 2 Blockers and 2 Majors; 5 Minors (2 of them downgraded); 0 refuted.

**Why the `_stop` findings are one merged finding.** R-C1, R-C2, R-E2, R-E3 and the verifier path share one root cause: `_stop`'s "never raises / always closes" contract is not structurally enforced. They also share one region (`bash.py:176-185`) and one fix, a single function body. Splitting them would invite a partial fix.

## 2. Verifications

### R-1 — `_stop` breaks "never raises / always closes" (CONFIRMED, Blocker)

**Spec text relied on:**
- INV-26: "`_stop` always ends by closing the subprocess transport, so no transport or pipe handle outlives the call".
- INV-12: "… and `CancelledError` always propagates".
- INV-11: "… returns an error result whose metadata `error` is `"timeout"`".
- §12.3 row 1: "`_stop` never raises".
- §12.4: "`_stop` never raises (an exception there would replace a propagating `CancelledError`)".
- D-14: "ignore `ProcessLookupError`". A grep of the spec for `PermissionError|EPERM` finds no hit, so no spec text requires a `PermissionError` to propagate, and suppressing it conflicts with nothing.

**Probe 1** (`probe_stop.py`, WSL MuseUbuntu1, Python 3.12.3).
- **Setup:** the real `BashTool` from the worktree; `BASH_TIMEOUT_SECONDS=1.0` and `BASH_KILL_GRACE_SECONDS=3.0` patched; `_spawn` wrapped only to record the process; holder command `setsid sleep 37.25 & sleep 37.25`.
- **Code as is:**
  ```
  python 3.12.3
  [CODE] timeout, then cancel during grace wait: raised CancelledError after 1.60s; transport is_closing=False
  [CODE] cancel, then second cancel during grace wait: raised CancelledError after 1.00s; transport is_closing=False
  [CODE] single cancel (control): raised CancelledError after 3.50s; transport is_closing=True
  [CODE] EPERM on timeout path: raised PermissionError after 1.00s; transport is_closing=False
  [CODE] EPERM on cancel path: raised PermissionError after 0.50s; transport is_closing=False
  ```
- **With the reviewers' fix in memory** (suppress `PermissionError` on the kill; close in `finally`):
  ```
  [FIX] timeout, then cancel during grace wait: raised CancelledError after 1.60s; transport is_closing=True
  [FIX] cancel, then second cancel during grace wait: raised CancelledError after 1.00s; transport is_closing=True
  [FIX] single cancel (control): raised CancelledError after 3.50s; transport is_closing=True
  [FIX] EPERM on timeout path: returned ERROR {'error': 'timeout', 'truncated': False} after 1.00s; transport is_closing=True
  [FIX] EPERM on cancel path: raised CancelledError after 0.50s; transport is_closing=True
  leftover processes: none
  ```
- **Simulation used:** EPERM was simulated the way the briefing prescribes, by patching `os.killpg` to kill and then raise `PermissionError(1, ...)`. The WSL user is root, so a real EPERM cannot be produced.

**Consequence of the escaped `PermissionError`, read from the code:**
- `runtime.py:1288-1297` (`_execute_tool`) catches `except Exception as exc` and raises `ToolExecutionError("Tool execution failed: …")`.
- `runtime.py:1149-1157` turns that into `ToolResult.error(...)`, and the loop continues.
- `CancelledError` is a `BaseException`, so it would not have been caught. A `PermissionError` that replaces it therefore converts a run-level cancellation into an ordinary tool error, and the agent keeps running an allow-all, unsandboxed shell. This is why R-C2/R-E2 sit in a Blocker finding.

**Probe 2 `[verifier]`** (`probe_eperm_alive.py`, WSL 3.12.3): the blind spot.
- **What earlier probes missed:** the reviewers' EPERM simulation (kill, then raise) leaves no process alive. Under a real EPERM, `killpg` kills nothing, so the direct child is still running when `_stop` reaches `transport.close()`.
- **The stdlib path** (source read via `inspect` on both 3.11.0 and 3.12.3):
  - `BaseSubprocessTransport.close()` closes the pipes, then runs `try: self._proc.kill() except ProcessLookupError: pass`.
  - POSIX `Popen.send_signal` runs `try: os.kill(self.pid, sig) except ProcessLookupError: pass`.
  - So `close()` raises `PermissionError` for an unsignallable leader.
- **Setup:** `os.killpg` and `os.kill` (SIGKILL to the recorded pid) both raise without killing, and the leader is `sleep 41.75`. bash execs a lone command, so `sleep` is the leader.
- **Output:**
  ```
  [CODE] timeout path, leader alive and unsignallable: raised PermissionError after 1.00s; transport is_closing=False
  [CODE] cancel path, leader alive and unsignallable: raised PermissionError after 0.50s; transport is_closing=False
  [REVIEWERS-FIX] timeout path, leader alive and unsignallable: raised PermissionError after 2.00s; transport is_closing=True
  [REVIEWERS-FIX] cancel path, leader alive and unsignallable: raised PermissionError after 1.50s; transport is_closing=True
  [FULL-FIX] timeout path, leader alive and unsignallable: returned ERROR {'error': 'timeout', 'truncated': False} after 2.00s; transport is_closing=True
  [FULL-FIX] cancel path, leader alive and unsignallable: raised CancelledError after 1.50s; transport is_closing=True
  leftover processes: none
  ```
- **Reachability:**
  - Linux `kill(2)` returns EPERM for a process group when no member can be signalled. This is the case when every remaining member runs with another real UID. A typical example is a non-root agent (a GitHub-hosted runner or a dev VM with passwordless sudo) running a lone `sudo …` command: bash execs `sudo`, so the group leader is `sudo` itself, running as root.
  - I could not produce a real EPERM here, because the WSL user is root. The kernel return code is the only simulated part.

**Fix verified in memory** (`drive_fixes.py`).
- **Method:** compile `bash.py` with the full-fix `_stop` body, graft only that code object onto the real class (bound to the real module globals, so the tests' `BASH_*` patches still apply), and run S024's `NestingAnalyzer` on the patched text.
- **S024 output:** `S024 on original bash.py source: no findings` / `S024 on patched bash.py source: no findings`.
- **Pack, Windows 3.11.0:** `87 passed, 11 skipped in 12.53s` (86 pack tests plus the proposed EC-11 test) / `RESULT python=3.11.0 platform=win32 pytest_exit=0`.
- **Pack, WSL 3.12.3:** `98 passed in 29.97s` / `RESULT python=3.12.3 platform=linux pytest_exit=0` / `no stray sleep/yes processes`.

**Classification:** code change only. A regression test (patch `os.killpg` and `os.kill` to raise, and a double cancel; assert re-raise or timeout and `transport.is_closing()`) is recommended, but it is an addition to the S2 pack, so it needs the orchestrator's grant.

### R-2 — EC-11 test cannot fail (CONFIRMED, Blocker: "a test that cannot fail")

**Why the gate cannot catch the mutation:**
- pytest 8.3.5, `_pytest/capture.py` `FDCaptureBase.__init__`: `if targetfd == 0: self.tmpfile = open(os.devnull, encoding="utf-8")`.
- `scripts/run_ci.py:93`: `self._run_command([sys.executable, "-m", "pytest"])`.
- `pyproject.toml` `addopts = ["--strict-config", "--strict-markers"]`, with no `-s`.
- So under the gate, fd 0 is the null device whether or not the tool passes `stdin=DEVNULL`.

**In-process mutation proof** (`drive_ec11.py`).
- **Method:** `pytest.main` runs in the same process; `asyncio.create_subprocess_exec` is wrapped to pop `stdin` and count spawns. No repo file was written. The proposed test lives at `scratchpad/test_ec11_proposed.py`, with a local `bash_module` fixture that mirrors the pack conftest.

| Case | WSL 3.12.3 | Windows 3.11.0 |
|---|---|---|
| existing test, mutant (stdin removed) | `1 passed in 0.06s` · `pytest_exit=0 mutant_spawns=1` | `1 passed in 0.09s` · `pytest_exit=0 mutant_spawns=1` |
| existing test, code | `1 passed in 0.06s` · `pytest_exit=0` | `1 passed in 0.09s` · `pytest_exit=0` |
| proposed test, mutant | `E ... output='\n[command stopped: it did not finish within the 10-second time limit]' ...` · `1 failed in 23.62s` · `pytest_exit=1` | `E ... 10-second time limit ...` · `10.01s call` · `1 failed in 17.86s` |
| proposed test, code | `1 passed` (`0.02s call`; the session's 13 s is collection of a file outside the rootdir on WSL1 `/mnt/c`) · `pytest_exit=0` | `1 passed in 7.59s` · `pytest_exit=0` |

**Classification:** test change only. It meets the orchestrator's grant rule (provably cannot fail). The before and after are in `review.md` under "Fix detail R-2".
- **Simplification:** the reviewer's `capfd.disabled()` step is not needed. The test's own `os.dup2` overrides pytest's null device for the duration of the call and then restores it. Pytest's fd-0 capture is not suspended between phases (`suspend_capturing(in_=False)`), so nothing re-dups fd 0 mid-call.
- **Orchestrator follow-up:** the test-plan's EC-11 row claims "An inherited stdin makes `read` wait for the time limit". That is false under the gate until R-2 lands.

### R-3 — `root_dir=""` accepted (CONFIRMED, Major)

**Probe** (Windows 3.11.0, `CodingAgent(..., root_dir=value)`):
```
'' ACCEPTED -> C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-coding-agent | equals cwd: True | policy: ['execute', 'read', 'safe', 'write']
WindowsPath('.') ACCEPTED -> ... | equals cwd: True
' ' REJECTED CodingAgent root_dir must be an existing directory.
'' os.path.isdir: False | Path.is_dir: True
```

**Spec:**
- FR-3: "rejects anything that is not an existing directory".
- §9.2: "`root_dir` must be path-like and an existing directory".
- D-8: "should not silently default to the process working directory".
- `""` is not an existing directory by OS semantics: `os.path.isdir("")` is False, and `os.stat("")` raises. Only pathlib normalises it to `.`. This is a conformance gap, not scope.

**Fix verified in memory:**
```
fixed _resolve_root('') -> ConfigurationError
fixed _resolve_root('.') -> accepted
fixed _resolve_root('<worktree>') -> accepted
```
The pack is green on both platforms (numbers above).

**Classification:**
- Code change only.
- The AC-11 `""` case is recommended but does not meet the grant rule, so the orchestrator decides. Proposed diff: add `"empty-string"` to the `bad_root` ids and `"empty-string": ""` to `candidates`.

**Limit of the fix:** `Path("")` is `Path(".")`, so a caller passing `Path(os.environ.get("X", ""))` still gets the current folder. No check can distinguish that.

**Fix choice (adjudicated):**
- Chosen: R-C3's `os.path.isdir`, a one-call swap that accepts PathLike.
- Rejected: R-E5's blank-string check. It is more code, and on POSIX it rejects a real folder literally named `" "`.

### R-4 — bash description literal (CONFIRMED, raised from Minor to Major)

**(a) The exit-code claim.**
- `bash.py:68` says: "The exit code of the command is always the last line of the result."
- `bash.py:117` makes the timeout result end with `\n[command stopped: ...]`.
- `bash.py:101` and `:148` build error results with no exit code.

**(b) The Windows stop claim.**
- `bash.py:68` says: "A command that has not finished after … seconds is stopped".
- `bash.py:176-180`: on `win32` only `process.kill()` of Git's launcher runs (EC-14, A-9).
- Spec EC-14, "Guarded by" column: "accepted limitation, stated in the tool description, the `bash.py` header, and the README".
- `bash.py:9` (header) states it, and `README.md:110` states it. The description does not; it states the opposite.

**(c) Length.**
- `SentenceCounter().count(BashTool(".").spec().description)` gives `current sentences: 6`.
- Field guide `model-facing-tool-contracts.md:3-7`:
  - When: "Adding or revising a model-callable builtin".
  - Do: "give the tool and every parameter a consistent 4–5 sentence general description".
  - Check: "description length, example-free prose, and validation/rendering parity".

**Why raised:**
- (b) is an explicit spec requirement that is missing on the user's own platform.
- (a) and (c) contradict a field-guide lesson. The rubric lists that as Blocker-class.
- I hold it at Major because nothing the tool *returns* is wrong; the defect is model-facing prose, and the fix is one literal.
- Upgrading Minor to Major costs no extra iteration: it is one string edit.

**Proposed literal:** in `review.md`. S025's counter on it gives `proposed sentences: 5`. It keeps every §12.3 row 1 content item: fresh process in the root, stdin closed, no carry-over, not confined, merged streams, first-bytes cap with filter advice, exit code last, the 600 s stop with the Windows caveat, and the background-redirect rule.

### R-5, R-6, R-7 — Minors, passed through

I spot-checked each and kept it as Minor.

**R-5 (README `restore()` text and header):**
- `README.md:109` reads "`fork()` and `restore()` give a `BaseAgent`: …".
- `coding.py:5` lists "restores" as behaving exactly as for a BaseAgent, while `coding.py:9` says `CodingAgent.restore(state)` raises `TypeError`.
- Note: the README text follows §12.3 row 7's own wording, so this is clarity, not conformance.

**R-6 (`spawn_failed` hint):** probe with the root removed, then `echo hi`:
```
removed root -> ERROR 'bash could not start this command (NotADirectoryError). Shorten the command or remove NUL characters from it.' {'error': 'spawn_failed'}
```

**R-7 (tests README folder):**
- `tests/features/coding_agent/README.md:7` says "The file, search and fetch tools … belong in `vidbyte/tools/builtins/`".
- `ls vidbyte/tools/filesystem/` lists `read_lines.py`, `replace_text.py` and `write_text.py`.

### R-8 (R-V1) — DOWNGRADED Major → Minor, follow-up

**Rule text, quoted:**
- AGENTS.md (Repository Map): "Read it before you create a file, move code, or search for where something lives, and put new code where it says that kind of code belongs."
- REPO_MAP.md:3: "The rules for where *new* code goes are not part of the Map: they are the binding [Placement Rules](AGENTS.md#placement-rules) in `AGENTS.md`."
- AGENTS.md Placement Rules cover exactly three things: "Dataclasses go in `vidbyte/lib/dataclasses/`", "Enums go in `vidbyte/lib/enums/`", and "New JEV code". Nothing covers tools or tool views.
- REPO_MAP.md:305 (`vidbyte/tools/`): "This is the layer to understand before writing any new tool, custom or otherwise". This is descriptive.
- REPO_MAP.md:61 (`vidbyte/agents/`): "Executable agent actors …". Also descriptive.

**Field guide:**
- The PR #399 lesson the reviewer cites (`blocking-lint-invariants.md:3-8`) concerns an A006 constraint on a sessions→middleware bridge class, not tool placement.
- `class-bound-helpers.md:5`: "Keep private wrapper types as nested or module-private classes". `_FetchedPagesView` is module-private.

**Precedent:**
- Grep of `vidbyte/agents/**/*.py` for tool classes (`class …(…Tool…|_ToolWrapper…)`, `ToolSpec(`, `ToolParameter(`, `@tool`) finds only `coding.py:132`. The only other match is a README example, `codex/README.md:375`.
- `ContinualTraceAgent` imports `UpdateTraceTool` from `vidbyte/tools/continual_trace.py`.
- So there is a sibling preference with no rule behind it.

**Spec:**
- D-16 settled the placement with a flip condition ("Another feature needs the same view").
- Moving the class adds a third file against §8.4 and hits §14 "Ask first: … exceeding §8.4 (a third new file)".
- AGENTS.md outranks the spec only where an AGENTS.md rule is actually broken; here none is.

### R-9 (R-E4) — DOWNGRADED Major → Minor, follow-up, `[scope-adding]`

**My probe** (Windows 3.11.0, cwd = a scratch folder holding empty `git.exe` and `bin\bash.exe`; the real git is on PATH):
```
git dirs on PATH: ['C:\\Program Files\\Git\\mingw64\\bin', 'C:\\Program Files\\Git\\cmd']
shutil.which('git') -> '.\\git.EXE'
BashTool._executable -> C:\Users\422mi\AppData\Local\Temp\claude\...\scratchpad\cwd-plant\bin\bash.exe
stdlib comment: includes checking relative to the | # current directory, e.g. ./script ...
```
The folder was deleted afterwards. So the behavior is real.

**Spec text, quoted:**
- FR-11: "on `win32`, the first existing `<P>/bin/bash.exe` where `<P>` is one of the first three parent folders of `Path(shutil.which("git")).resolve()`; otherwise none".
- D-13: "Windows the first existing `<P>/bin/bash.exe` among the first three parents of `Path(shutil.which("git")).resolve()`".
- §12.3 row 1: "on `win32`, return `None` when `git` is not on `PATH`, else the first `<P>/bin/bash.exe` that is a file among `Path(git).resolve().parents[:3]`".
- INV-15: "On `win32`, `BashTool` never runs the `bash` found on `PATH` …; it uses Git for Windows' `bin/bash.exe` found under one of the first three parent folders of the resolved `git` executable on `PATH`, or reports `bash_not_found`."

**Adjudication:**
- The mechanism is fixed by FR-11, D-13 and row 1 as `shutil.which("git")`, and the code is that mechanism, verbatim.
- The weighted "never" in INV-15 governs the PATH `bash`, and that holds.
- "On `PATH`" is the spec's paraphrase of `shutil.which`; AC-17 uses the same phrasing.
- §10 has no planted-executable attacker, and EC-13 and D-13 give the WSL launcher as the purpose.
- The S2 author already recorded the current-folder search (`test_bash_tool_contract.py:191-192`, "Windows also searches the current folder before PATH").
- An attacker who controls the agent's working folder already runs code through ordinary agent work there under accepted T-1/T-2.
- Conclusion: this is a hardening the spec never asked for. It is `[scope-adding]` and a follow-up. One-line fix if wanted: `if git is None or not os.path.isabs(git): return None`.

## 3. Disagreements between reviewers I adjudicated

1. **R-C1 (Blocker) vs R-E3 (Major), the same failure.** Blocker. INV-26's "always" is a weighted word, and the path is reachable on POSIX (`setsid` holder) and on Windows 3.12+ (EC-14 orphan).
2. **R-C2 / R-E2 (Major, "Blocker-class but simulated").** Folded into Blocker R-1. The simulated part is only the kernel return code, which is documented `kill(2)` behavior. The consequence (a swallowed run cancellation, `runtime.py:1293`) is unsafe.
3. **The reviewers' shared fix for R-C2/R-E2 is incomplete** (my probe 2). The full fix also suppresses `PermissionError` around `transport.close()`.
4. **R-C3 vs R-E5 fix.** `os.path.isdir` (R-C3), for the reasons in §2 R-3.
5. **R-V4 vs R-E6 fix.** R-V4's single neutral sentence. R-E6's per-errno branch is more code for the same model outcome.
6. **R-E1's `capfd.disabled()`.** Not needed; my simpler version was proven on both platforms.
7. **R-C4 / R-V3 / R-V6.** One literal, one edit. Raised to Major because of EC-14.
8. **R-V1 vs spec D-16.** D-16 stands: no AGENTS.md rule is broken.
9. **R-E4 vs FR-11.** FR-11 stands; the finding is a hardening.

## 4. Blind-spot check (step 6)

- **Added:** the R-1(c) `transport.close()` re-kill path (see above). This is the only cross-lens risk I could anchor to a `path:line` that changes the repair.
- **Fix interactions (for the repair agent):**
  - R-1, R-4 and R-6 all edit `bash.py`, at lines 176-185, 68 and 148.
  - R-1 must also update the `@intent` comment at `:167-175` (AGENTS.md Style 2; the header must describe the code).
  - The R-6 hint must not contain "embedded null", "argument list too long" or "extension is too long". `test_command_the_os_cannot_start_returns_spawn_failed_naming_only_the_exception_class` (`test_bash_tool_contract.py:150`) asserts those exception phrases are absent.
- **A convention fix that would break conformance:** R-V1's proposed move to `vidbyte/tools/builtins/operations/_fetched_pages.py` would breach §8.4 and §14 (ask-first). Because R-V1 is downgraded, no repair agent should act on it.
- **Considered and not raised:**
  - **CPython 3.11 `asyncio.wait_for` race.** It returns a completed inner result when the outer cancel arrives in the same loop iteration, which swallows the cancel; 3.12 reimplemented `wait_for`. This is a stdlib race in a one-iteration window, and D-17 mandates `wait_for`.
  - **PGID reuse by the unconditional `killpg`** (R-E2's side note). The group must be empty and its leader reaped between the timeout firing and the kill, and PIDs are allocated sequentially.
  - **The `[command stopped: …]` result line also says "stopped" on Windows.** EC-14 names only the description, the header and the README, so this is scope.
  - **The public `BashTool("missing")` does not validate its root.** Spec §8.5 does not require it, and R-6 makes the message accurate.

## 5. Test-change ledger (for the orchestrator's grant)

| Finding | Code change | Test change | Grant-eligible? |
|---|---|---|---|
| R-1 | yes (`bash.py:176-185` + `@intent` text) | optional regression test (EPERM with the leader alive; double cancel) | no (addition, not a broken test); orchestrator's call |
| R-2 | no | **yes**, `test_bash_tool_contract.py:126-134` + `import os` (before and after in `review.md`) | **yes**, provably cannot fail (proof in §2 R-2) |
| R-3 | yes (`coding.py:101`) | optional `""` case in the AC-11 parametrization | no; orchestrator's call |
| R-4 | yes (`bash.py:68`) | none (no test pins the description text) | — |
| R-7 | — | the pack README is doc, not test | orchestrator's call (S2 pack file) |

## 6. Commands run (final lines)

- **Show the reviewed code:** `git show 4e285d91:vidbyte/tools/builtins/bash.py | cat -n`; the same for `vidbyte/agents/coding.py`. I read both in full.
- **Confirm HEAD differs only in docs:** `git diff --stat 4e285d91 HEAD` → 4 files, all under `docs/spec/coding-agent/`.
- **Probe 1 (WSL):** `wsl.exe -d MuseUbuntu1 -- bash -lc '… /tmp/s2-coding-agent-venv/bin/python …/scratchpad/probe_stop.py'` → output quoted in §2 R-1; last line `leftover processes: none`.
- **Probe 2 (WSL):** `… probe_eperm_alive.py` → output quoted in §2 R-1; last line `leftover processes: none`.
- **Stdlib source (`show_close.py`):** on Windows 3.11.0 and WSL 3.12.3, prints `BaseSubprocessTransport.close` and `Popen.send_signal`. Both catch only `ProcessLookupError`.
- **R-2 proof (`drive_ec11.py <worktree> <scratch> existing|proposed mutant|code`):** run on WSL and Windows; results in the §2 R-2 table.
- **R-3 probe (Windows):** `PYTHONPATH=$(pwd) python - <<EOF … CodingAgent(root_dir=…)` → quoted in §2 R-3.
- **R-9 probe (Windows):** run from `scratchpad/cwd-plant` → quoted in §2 R-9; then `rm -rf` printed `cleaned`.
- **R-4 sentence count:** `SentenceCounter` probe → `current sentences: 6` / `proposed sentences: 5`.
- **All candidate fixes applied in memory (`drive_fixes.py`):** Windows → `87 passed, 11 skipped in 12.53s` / `RESULT python=3.11.0 platform=win32 pytest_exit=0`; WSL → `98 passed in 29.97s` / `RESULT python=3.12.3 platform=linux pytest_exit=0` / `no stray sleep/yes processes`.
- **Unpatched baseline (Windows):** `PYTHONPATH=$(pwd) python -m pytest -q -p no:cacheprovider tests/features/coding_agent/` → `86 passed, 11 skipped in 4.96s`.
- **Spawn-failure probe (Windows):** `removed root -> ERROR 'bash could not start this command (NotADirectoryError). Shorten the command or remove NUL characters from it.' {'error': 'spawn_failed'}`.
- **Grep checks:** `vidbyte/agents` for tool classes and tool APIs → only `coding.py:132` (plus `fork.py`'s `_ToolWrapper` isinstance check and a README example). REPO_MAP and field-guide lines quoted in §2 R-8.
- **Clean-up checks:**
  - `git status --short` → empty, after all runs.
  - Windows `Get-CimInstance Win32_Process` → only Claude Code's own shells. A `sleep.exe 20` seen once was not started by me (none of my Windows commands ran `sleep`), and it had exited by the next check.

## 7. Notes for the next agent

- **wsl.exe expands any `$NAME`, not only `$!`/`$$`.** `$S` came through empty. Use literal paths in the `-lc` string, or put the script in a file.
- **Collecting a test file outside the rootdir is slow on WSL1 `/mnt/c`** (about 13 s), so read `--durations` before calling a test slow.
- **The probe scripts stay in the scratchpad above** for reproduction. Each one restores every patch and kills its `sleep` processes.
