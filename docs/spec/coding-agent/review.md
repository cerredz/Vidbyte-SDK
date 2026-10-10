# Adversarial review: CodingAgent — a minimal BaseAgent with seven file-system and web tools

Diff reviewed: `origin/main...4e285d91` (code identical at HEAD `8234dd95`, which adds only `docs/`) · Lenses: conformance, conventions, engineering · Verifier: reports/S4-findings-verifier.md

## Verdict
MERGEABLE AFTER FIXES — The feature does what the user asked, and every main path holds. However, `_stop` breaks its "never raises / always closes" contract on three reachable paths, the EC-11 test cannot fail under the gate, `root_dir=""` silently means the current folder, and the model-facing bash description contradicts the result contract and EC-14. All four fixes are small and local.

## Confirmed findings (must fix) — 4
| ID | Severity | Lens | Where (path:line) | Finding (claim) | Evidence | Smallest fix | Status |
|---|---|---|---|---|---|---|---|
| R-1 | Blocker | conformance + engineering + [verifier] | `vidbyte/tools/builtins/bash.py:176-185` (and its `@intent` text at `:167-175`) | `_stop` breaks INV-26 ("always ends by closing the subprocess transport"), INV-12 ("`CancelledError` always propagates"), INV-11 (timeout result) and §12.3 row 1 / §12.4 ("`_stop` never raises") on three paths. **(a)** A cancellation during the grace wait skips the close, because the close is not in `finally`. **(b)** A `PermissionError` from `os.killpg` escapes, because only `ProcessLookupError` is suppressed. **(c) [verifier]** Even with (a) and (b) fixed as the reviewers proposed, `transport.close()` re-kills a still-running direct child through `Popen.kill()`, which suppresses only `ProcessLookupError`, so a real EPERM raises again from `close()`. Merges R-C1, R-C2, R-E2, R-E3. | All runs are mine, on WSL with Python 3.12.3, using the real `BashTool` with a 1 s limit. **(a)** With a 3 s grace and a `setsid` holder, a timeout followed by a cancel at 1.6 s gave `raised CancelledError after 1.60s; transport is_closing=False`; a cancel followed by a second cancel gave `raised CancelledError after 1.00s; transport is_closing=False`. The single-cancel control gave `is_closing=True`. **(b)** With `os.killpg` patched to kill and then raise EPERM, the timeout path gave `raised PermissionError ... is_closing=False` and the cancel path gave `raised PermissionError after 0.50s ... is_closing=False`. `runtime.py:1293` (`except Exception`) and `:1149-1157` turn that into an error result, so a run-level cancel is swallowed and the loop keeps going. **(c)** With `killpg` and `os.kill` both refusing and the leader still alive (the real EPERM shape, for example a root-owned `sudo` leader), the reviewers' fix still gave `raised PermissionError after 2.00s` (timeout) and `after 1.50s` (cancel). The stdlib `BaseSubprocessTransport.close` → `self._proc.kill()` path catches only `ProcessLookupError` (source read on 3.11.0 and 3.12.3). With the full fix the same runs gave `returned ERROR {'error': 'timeout', ...}` and `raised CancelledError`, both with `is_closing=True`. No spec text requires `PermissionError` to propagate; D-14 says only "ignore `ProcessLookupError`". | Apply the snippet under "Fix detail R-1" below: wrap the kill and the bounded wait in `try:`, suppress `PermissionError` next to `ProcessLookupError`, and move the close into `finally:` under `contextlib.suppress(PermissionError)`. Update the `@intent` comment so it says why `PermissionError` is tolerated: no group member can be signalled, and `close()` re-kills the direct child. Code-only change. A regression test (EPERM patch and double cancel, asserting the transport is closing) is optional and needs the orchestrator's grant. Applied in memory, S024 reports no findings and the pack passes (Windows 3.11: 87 passed, 11 skipped; WSL 3.12: 98 passed). | open |
| R-2 | Blocker | engineering | `tests/features/coding_agent/test_bash_tool_contract.py:126-134` | The EC-11 stdin test cannot fail under the gate. pytest's default fd capture already puts the null device on fd 0, so a spawn that inherits stdin still sees end-of-file. Removing `stdin=DEVNULL` (`bash.py:142`) leaves the test green. Merges R-E1. | pytest 8.3.5 `FDCaptureBase.__init__` has `if targetfd == 0: self.tmpfile = open(os.devnull, ...)`. The gate runs `[sys.executable, "-m", "pytest"]` (`scripts/run_ci.py:93`), and `pyproject.toml` addopts have no `-s`. With the in-memory mutation that drops `stdin` from `create_subprocess_exec`, the existing test gave `1 passed in 0.06s ... pytest_exit=0 mutant_spawns=1` on WSL 3.12.3 and `1 passed in 0.09s ... pytest_exit=0 mutant_spawns=1` on Windows 3.11.0. With the proposed test, the mutant gave `FAILED ... output='\n[command stopped: it did not finish within the 10-second time limit]' ... 1 failed ... pytest_exit=1` on WSL, and `1 failed`, call 10.01 s, on Windows. The real code gave `1 passed` (call 0.02 s) on both. | **Test-only change.** It qualifies for the orchestrator's grant because the test provably cannot fail. For the duration of the call, put a pipe that never reaches end-of-file on fd 0 and restore it in `finally`; see "Fix detail R-2" for before and after. No `capfd` is needed: the reviewer's `capfd.disabled()` step is unnecessary, because the test's own `dup2` overrides pytest's null device and then restores it. | open |
| R-3 | Major | conformance + engineering | `vidbyte/agents/coding.py:101` | `root_dir=""` passes validation and roots all seven tools, with allow-all WRITE and EXECUTE, at the process working directory. This breaks FR-3 ("rejects anything that is not an existing directory"), §9.2 ("must be path-like and an existing directory"), EC-6, and D-8's deciding reason ("should not silently default to the process working directory"). Merges R-C3, R-E5. | Windows 3.11.0 probe: `'' ACCEPTED -> C:\...\vidbyte-sdk-coding-agent \| equals cwd: True \| policy: ['execute', 'read', 'safe', 'write']`. `os.path.isdir('')` is `False` while `Path('').is_dir()` is `True`, and `' '` is rejected. With `os.path.isdir` swapped in (in memory), `''` raises `ConfigurationError`, `'.'` and an absolute path are accepted, and the whole pack passes on both platforms. AC-11's cases are missing, file, 42, None and omitted; none is `""`. Limit: `Path("")` *is* `Path(".")`, so no check can tell those two apart; the fix covers the string input. | **Code-only.** Replace `Path(root_dir).is_dir()` with `os.path.isdir(root_dir)`, a one-call change that already accepts PathLike (R-C3's fix). Alternative (R-E5): an explicit blank-string check. It is more code, and on POSIX it rejects a real folder named `" "`. A test addition (`"empty-string": ""` in the AC-11 parametrization) is recommended, but it does not meet the grant rule, because the existing test neither contradicts a spec ID nor provably cannot fail; the orchestrator decides. | open |
| R-4 | Major (raised from Minor) | conventions + conformance | `vidbyte/tools/builtins/bash.py:68` | The model-facing `bash` description is wrong in two clauses and too long. **(a)** It says "The exit code of the command is always the last line of the result", but the timeout result ends with `[command stopped: ...]` (`:117`), and `bash_not_found` and `spawn_failed` carry no exit code. **(b)** It says a command over the limit "is stopped", but on Windows `_stop` kills only Git's launcher (`:179-180`). EC-14 requires this limitation to be "stated in the tool description, the `bash.py` header, and the README"; the header (`:9`) and README (`:110`) state it, the description does not. **(c)** It has 6 sentences against the field guide's "consistent 4–5 sentence general description". Merges R-C4, R-V3, R-V6. | I read `:68`, `:117` and `:176-180` against EC-14's "Guarded by" column. Running `lint/rules/s025_model_facing_description_depth.SentenceCounter` on the live `spec().description` returned `current sentences: 6`. The field-guide entry `model-facing-tool-contracts.md` applies "When: Adding or revising a model-callable builtin". Its Do line is "4–5 sentence general description", and its Check line is "description length ... validation/rendering parity". **Why raised:** (b) is an explicit spec requirement (EC-14) that is missing, and the description asserts the opposite on the user's own platform; (a) and (c) contradict a field-guide lesson. The rubric would allow Blocker for the field-guide clause. It is held at Major because no tool result is wrong; only model-facing prose is. | **Code-only.** Rewrite the one f-string literal as the five sentences under "Fix detail R-4" below; S025's counter returns 5 for that text. It keeps every §12.3 row 1 content item, keeps one literal (S062) and uses no examples. | open |

### Fix detail R-1 — `BashTool._stop` body (`bash.py:176-185`)
```python
        try:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                if sys.platform != "win32":
                    os.killpg(process.pid, signal.SIGKILL)
                elif process.returncode is None:
                    process.kill()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), BASH_KILL_GRACE_SECONDS)
        finally:
            transport = getattr(process, "_transport", None)
            if transport is not None:
                with contextlib.suppress(PermissionError):
                    transport.close()
```
- **Nesting:** the deepest path is `try`, then `with`, then `if`, which is depth 3; S024's own `NestingAnalyzer` reports no findings on the patched source.
- **Lint:** no `CancelledError` handler is added, so S019 is unaffected.
- **Why both suppressions are needed:**
  - `finally` alone still lets `PermissionError` replace `CancelledError`.
  - The `killpg` suppression alone still raises from `close()` when the leader is alive.

### Fix detail R-2 — EC-11 test (`test_bash_tool_contract.py:126-134`; add `import os` to the module imports)
Before:
```python
@pytest.mark.asyncio
async def test_command_reading_stdin_sees_end_of_file_at_once(bash_module, tmp_path, monkeypatch) -> None:
    # EC-11 / D-10: stdin is the null device; an open stdin would hang this call until the (shortened) time limit.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", 10.0)

    result = await bash_module.BashTool(tmp_path).execute(_bash_call("read -r line; echo read-status:$?"))

    assert result.status is ToolStatus.SUCCESS
    assert result.output.splitlines()[0] == "read-status:1"
```
After:
```python
@pytest.mark.asyncio
async def test_command_reading_stdin_sees_end_of_file_at_once(bash_module, tmp_path, monkeypatch) -> None:
    # EC-11 / D-10: stdin is the null device; an open stdin would hang this call until the (shortened) time limit.
    # pytest's capture already puts the null device on fd 0, so give this process a stdin that never reaches end of
    # file: only the tool's own stdin=DEVNULL can then let the read see end of file.
    monkeypatch.setattr(bash_module, "BASH_TIMEOUT_SECONDS", 10.0)
    read_end, write_end = os.pipe()
    saved_stdin = os.dup(0)
    os.dup2(read_end, 0)
    try:
        result = await bash_module.BashTool(tmp_path).execute(_bash_call("read -r line; echo read-status:$?"))
    finally:
        os.dup2(saved_stdin, 0)
        for fd in (saved_stdin, read_end, write_end):
            os.close(fd)

    assert result.status is ToolStatus.SUCCESS
    assert result.output.splitlines()[0] == "read-status:1"
```

### Fix detail R-4 — `bash` tool description (`bash.py:68`, one f-string)
```python
f"Runs one command in a fresh bash process that starts in the agent's root folder with standard input closed, and returns what the command printed. Changes of directory and shell variables do not carry over from one call to the next, and the command is not confined to the root folder. Standard output and standard error come back together in the order they were written, and only the first {BASH_MAX_OUTPUT_BYTES:,} bytes are kept, so filter a long output or write it to a file and read that file in parts. When the command finishes, its exit code is the last line of the result; a command still running after {BASH_TIMEOUT_SECONDS:g} seconds is stopped instead, except that on Windows only Git's bash launcher is stopped and the command itself may keep running. A background process must redirect both its standard output and its standard error to a file, otherwise the call waits for the time limit and the process is killed."
```

## Refuted or downgraded by the verifier — 2
| ID | Original severity | Why refuted / downgraded (evidence) |
|---|---|---|
| R-V1 → R-8 | Major | **Downgraded to Minor, follow-up.** No binding rule is broken. AGENTS.md says: "Read it before you create a file … and put new code where it says that kind of code belongs". REPO_MAP.md:3 then says: "The rules for where *new* code goes are not part of the Map: they are the binding [Placement Rules](AGENTS.md#placement-rules) in `AGENTS.md`". Those Placement Rules cover only dataclasses, enums and new JEV code. REPO_MAP's `vidbyte/tools/` text is descriptive ("the layer to understand before writing any new tool"), not a placement rule. The PR #399 field-guide lesson (`blocking-lint-invariants.md:3-8`) is about an A006 middleware bridge, not tool placement. `class-bound-helpers.md:5` says "Keep private wrapper types as nested or module-private classes", which `_FetchedPagesView` satisfies. What remains is a sibling preference: no other tool class exists in `vidbyte/agents/` (my grep), and ContinualTraceAgent's `UpdateTraceTool` lives in `vidbyte/tools/`. Spec D-16 settled this with a flip condition ("Another feature needs the same view"). Moving the class would add a third file against §8.4 and trigger §14's ask-first rule. |
| R-E4 → R-9 | Major | **Downgraded to Minor, follow-up, `[scope-adding]`.** The behavior is real. My probe from a folder holding empty `git.exe` and `bin\bash.exe` stand-ins, with the real git on PATH, gave `shutil.which('git') -> '.\\git.EXE'` and `BashTool._executable -> <cwd>\bin\bash.exe`. But the code implements the spec to the letter: FR-11 says "on `win32`, the first existing `<P>/bin/bash.exe` where `<P>` is one of the first three parent folders of `Path(shutil.which("git")).resolve()`", D-13 says the same, and §12.3 row 1 says "return `None` when `git` is not on `PATH`, else the first `<P>/bin/bash.exe` … among `Path(git).resolve().parents[:3]`". INV-15's weighted "never" governs "the `bash` found on `PATH`", and that holds. INV-15, D-13 and EC-13 state the purpose as avoiding the WSL launcher. §10 lists no planted-executable attacker. The S2 test already records the current-folder search (`test_bash_tool_contract.py:191-192`). An attacker who controls the folder the agent runs in can already run code through ordinary agent work there (tests, build scripts) under the accepted T-1/T-2. This is a hardening the spec never asked for. Fix if wanted: `if git is None or not os.path.isabs(git): return None`. |

## Minor findings (fix if trivial, otherwise follow-ups)
| ID | Where | Finding | Status |
|---|---|---|---|
| R-5 | `vidbyte/agents/README.md:109`; `vidbyte/agents/coding.py:5` | The README bullet says "`fork()` and `restore()` give a `BaseAgent`". `CodingAgent.restore(state)` raises `TypeError` (EC-20 "documented in README"), so state that. In the header, drop "restores" from the "behave exactly as for a BaseAgent" list, because line 9 of the same header contradicts it. The README text follows §12.3 row 7's wording, so this is a clarity issue, not a conformance gap. Proposed bullet: "`fork()` returns a plain `BaseAgent`. `CodingAgent.restore(state)` raises `TypeError` (no `root_dir`), so restore with `BaseAgent.restore(state, tools=CodingAgent(...).tools.all())`." Merges R-C5, R-V2. | open — trivial |
| R-6 | `vidbyte/tools/builtins/bash.py:148` | Every `spawn_failed` result advises "Shorten the command or remove NUL characters from it", including a removed root folder. I verified this: with the root removed, `echo hi` gave `'bash could not start this command (NotADirectoryError). Shorten the command or remove NUL characters from it.'`. Use a neutral hint (R-V4): "Check that the root folder still exists, and that the command has no NUL characters and is not too long." Keep naming only the class (S017). R-E6's per-errno branching is the larger alternative. Merges R-V4, R-E6. | open — trivial |
| R-7 | `tests/features/coding_agent/README.md:7` | The pack README places the read, write and edit tools in `vidbyte/tools/builtins/`, but they live in `vidbyte/tools/filesystem/` (`read_lines.py`, `write_text.py`, `replace_text.py`; verified with `ls`). This file is in the S2 pack, so the orchestrator decides whether the no-test-edit rule covers it. Merges R-V5. | open — trivial (needs orchestrator OK) |
| R-8 | `vidbyte/agents/coding.py:132-174` | `_FetchedPagesView` (a `_ToolWrapper`) is the first tool class in `vidbyte/agents/`; the sibling preference is the tools layer. It was downgraded from Major; see the table above. It reopens D-16 and §8.4. Merges R-V1. | follow-up |
| R-9 | `vidbyte/tools/builtins/bash.py:57-61` | On Windows, `shutil.which("git")` finds a `git` in the current folder before PATH, so a planted `git.*` plus `bin\bash.exe` picks the bash. It was downgraded from Major; see the table above. Merges R-E4. | follow-up `[scope-adding]` |

## What the implementation gets right (so nobody "fixes" it)
- **INV-1 and INV-2 hold** (D-1 is deliberate; do not redeclare BaseAgent's parameters).
  - `CodingAgent` defines only `__init__`, `_resolve_root` and `_web_fetch_tool`, and it overrides no `BaseAgent` method.
  - `generate_reply is BaseAgent.generate_reply`.
  - Its seven explicit parameters are keyword-only, with the §8.5 defaults. The other 29 of BaseAgent's 31 parameters pass through `**kwargs`.
  - All six `AgentRuntimeType` values construct exactly as they do on `BaseAgent`, and `from_run_id` works.
- **The §4 snippet runs as written, and construction has no side effects.**
  - It prints the absolute `my-project` path and exactly `('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')`.
  - The policy is allow-all, and `system_prompt` is passed through unchanged.
  - Construction spawns nothing and opens no socket: `BashTool.__init__` does only `Path.resolve` and `shutil.which`.
  - The AC-1 test drives `run` through BaseAgent's loop.
- **Fetch keys are handled safely.**
  - Each key is validated without echoing it.
  - It is held only inside its provider client.
  - It selects exactly one provider.
  - It is absent from `export_state()` and `card()`.
- **The Bash spawn contract matches §8.5 / D-10.**
  - The command is exec'd as an argv list (S055) in its own session.
  - stdin is closed and stderr is merged.
  - Output is decoded as UTF-8 with replacement.
  - The cap keeps the first bytes, and the timeout marker and metadata are as specified.
- **One `asyncio.wait_for(self._collect(process, buffer), BASH_TIMEOUT_SECONDS)` covers both reading and waiting.**
  - The caller owns `buffer` (`bash.py:109-111`), so output captured before a timeout survives the cancellation of `_collect`.
  - The only `process.wait()` calls are bounded (`:163` under the limit, `:182` under the grace).
  - The `setsid` AC-25 and the AC-28 pipe-close cases are green on WSL 3.12.3.
- **The stop policy matches D-14 and INV-25.**
  - `_stop` is reached only from the `TimeoutError` and `CancelledError` handlers (`:114`, `:122`), and nothing is killed after a normal completion (`:126`).
  - On POSIX, `os.killpg` runs on every stop, even after the shell has exited (EC-29).
  - AC-15 and AC-26 fail for the right reason, and AC-13 and AC-29 catch a cap+1 off-by-one (mutation run).
- **The Windows lookup works on this host.** It picks `C:\Program Files\Git\bin\bash.exe` from `git` at `...\mingw64\bin\git.EXE` (EC-31), never the PATH `usr\bin\bash.EXE`, and a real call succeeded.
- **`_FetchedPagesView` changes only `output`,** and only for a SUCCESS result carrying a `FetchPayload` (`coding.py:168-174`).
  - Metadata stays the wrapped tool's object.
  - The runtime prices the unwrapped tool (`runtime.py:1200` → `activity.py:67-69` → `base.py:145-150`).
  - Fork returns the same view object (INV-23), and `fetch.py` is byte-identical (INV-20).
- **The lint ratchet is clean.**
  - Zero findings under any rule in `coding.py`, `bash.py` and all six pack modules.
  - Every rule count equals main's (A001 643, A002 682, A006 34, A007 255, S024 21, S025 261, …), and C016, S006, S052 and S055 are 0.
  - `generate-sdk-public-api.py --check` passes (`1bb1d3b4`, 594 exports).
- **Headers and style follow the repo.**
  - Both headers use the `jev/agent.py` A001 form and add FUNCTION INVENTORY and WHAT NOT TO DO. The `bash.py` claim "Python 3.12+ `Process.wait()` returns only after every pipe closes" is accurate (checked against the CPython 3.12.3 source).
  - AGENTS.md Styles 1 and 2 hold: `execute` calls a flat set of helpers (`_spawn`, `_collect`, `_stop`, `_render`), none of which calls another, and the main functions are narrated.
  - There are no nested functions or lambdas, and no new enum or dataclass.
  - Helpers are class-bound, and `__all__` lists only the classes.
- **Scope and budget are clean.**
  - Exactly the 8 §12.3 files change.
  - Tests are unchanged since S2, and `lint/` and the baseline are untouched.
  - There are no env reads, no renaming layer, no extra tools, and Q-2 to Q-6 are not built.
  - Files are 177 lines (`coding.py`, limit 200) and 194 lines (`bash.py`, limit 250).
  - Each §12.3 row is its own commit with IDs. The contract was regenerated after the root export was committed. There are no secrets or cache files.
- **Gates were green at `4c4a62ef`.**
  - Locally: 2715 passed and 12 skipped on the full pytest run.
  - Remotely: CI `38046509073` (Source 3.11/3.12, Package) and Static policy `38046510490` succeeded.
  - Pack: 86 passed and 11 skipped on Windows 3.11, and 97 passed on WSL 3.12 (re-run by the verifier).
