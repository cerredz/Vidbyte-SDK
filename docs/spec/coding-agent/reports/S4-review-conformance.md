LENS: conformance
VERDICT: MERGEABLE AFTER FIXES — The PR does what the user asked: 7 tools, keys only from parameters, no sandbox, no default prompt, existing tool names, and BaseAgent's whole surface. Two "always/never" guarantees in `_stop` fail on reachable paths, and `root_dir=""` silently roots the agent at the process working directory, which D-8 forbids.

WHAT THE IMPLEMENTATION GETS RIGHT (max 4 bullets, concrete, so nobody "fixes" what works)
- **INV-1 and INV-2 hold.** `CodingAgent` defines only `__init__`, `_resolve_root` and `_web_fetch_tool`. Its seven explicit parameters are keyword-only with the §8.5 defaults, and the other 29 of BaseAgent's 31 parameters pass through `**kwargs`. `generate_reply is BaseAgent.generate_reply`. All six `AgentRuntimeType` values construct exactly as they do on `BaseAgent`, and `from_run_id` works. Do not redeclare BaseAgent's parameters; D-1 is deliberate.
- **The §4 snippet runs as written.** It prints the absolute `my-project` path and exactly `('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')`. The policy is allow-all. Construction opens no socket. The key is absent from `export_state()` and `card()`, and `system_prompt` is unchanged. The AC-1 test drives `run` through BaseAgent's loop with a scripted runner.
- **The Bash contract matches §8.5 / D-10 to D-19.**
  - It uses argv exec in its own session with stdin closed and stderr merged.
  - One `wait_for` covers reading and waiting. Output is capped at the first bytes, and the timeout marker and metadata are as specified.
  - `_stop` is reached only from the `TimeoutError` and `CancelledError` handlers (INV-25), and the POSIX `killpg` is unconditional (EC-29).
  - On this Windows host, with `git` at `...\Git\mingw64\bin\git.EXE`, the lookup picks `C:\Program Files\Git\bin\bash.exe` (EC-31), never the PATH `usr\bin\bash.EXE`.
- **Scope and budget are clean.**
  - Exactly the 8 §12.3 files changed, plus `docs/spec/coding-agent/` and the S2 pack.
  - The tests are byte-identical since `a25a3c41`, and `lint/` and `lint/baseline.json` are untouched.
  - `4c4a62ef` adds comments only.
  - There are no env reads, no renaming layer, no extra tools, and no enums or dataclasses.
  - The contract adds only `CodingAgent`; `BashTool` is added only to `vidbyte.tools.builtins.__all__`.
  - Files: `coding.py` is 177 lines (limit 200) and `bash.py` is 194 lines (limit 250).

FINDINGS (ranked, most severe first, max 15)

R-C1 [Blocker] [every-ID / weighted word] vidbyte/tools/builtins/bash.py:181-185 — A cancellation that arrives during `_stop`'s grace wait skips the transport close, so INV-26's "always ends by closing" fails.
  Evidence: The close is the last plain statement after an await that can raise `CancelledError`, and nothing wraps it in `finally`:
  ```
  with contextlib.suppress(TimeoutError):
      await asyncio.wait_for(process.wait(), BASH_KILL_GRACE_SECONDS)
  transport = getattr(process, "_transport", None)
  if transport is not None:
      transport.close()
  ```
  Reproduced in WSL, Python 3.12.3, with real processes:
  - Setup: limit 1 s, grace 3 s, command `setsid sleep 20 & echo $!; sleep 20`. The outer task is cancelled at 1.6 s, while `_stop` is in its grace wait.
  - Output: `second cancel during grace wait -> raised CancelledError` and `transport is_closing after call left execute: False`.
  - It is followed by `Exception ignored in: <function BaseSubprocessTransport.__del__ ...> RuntimeError: Event loop is closed`. That is the exact symptom AC-28 / D-18 exist to prevent.
  Failure: A bash call times out while a descendant still holds the pipe: a POSIX `setsid` child, or on Windows with Python 3.12+ any still-running command (EC-14). If the agent-level `ToolSettings.tool_timeout_seconds` (any value in (600, 605]), a run cancellation, or Ctrl-C under `agent.run` lands inside the ≤5 s grace window:
  - the call re-raises with the parent's pipe still open;
  - a long-lived service leaks one pipe handle;
  - `asyncio.run` prints "Event loop is closed".
  INV-26 says "`_stop` always ends by closing the subprocess transport, so no transport or pipe handle outlives the call". §12.3 row 1 says "`_stop` never raises".
  Smallest fix: Wrap the kill and the bounded wait in `try:` and move the three transport lines into `finally:`. Cancellation still propagates, and the close always runs. The nesting depth stays at 3 (S024).
  Spec IDs: INV-26, INV-12, AC-28, D-18, §12.3 row 1, §12.4 "`_stop` ... never raises"

R-C2 [Major] [every-ID / weighted word] vidbyte/tools/builtins/bash.py:176-180 — A `PermissionError` from `os.killpg` escapes `_stop`. On cancellation it replaces `CancelledError`; on timeout it replaces the `timeout` result. Both skip the bounded wait and the transport close.
  Evidence: Only `ProcessLookupError` is suppressed: `with contextlib.suppress(ProcessLookupError): if sys.platform != "win32": os.killpg(process.pid, signal.SIGKILL)`.
  Reproduced in WSL, Python 3.12.3, with `os.killpg` patched to kill and then raise EPERM, as Linux `kill(2)` does when no group member can be signalled:
  - `timeout path -> RAISED PermissionError ; transport closing: False`
  - `cancel path -> RAISED PermissionError (spec: CancelledError); transport closing: False`
  The implementer disclosed this as "tricky part 2" and as a limitation.
  Failure: Bash execs a lone simple command; `MSYS_NO_PATHCONV=1 wsl.exe -- bash -c '...'` showed pid 8 turning into `ps`. So `bash -c "sudo -n make install"` (passwordless sudo is the GitHub Actions default) makes root-owned `sudo` the group leader. At the 600 s limit, or on cancellation, `killpg` raises EPERM, and then:
  - the runtime sees an `execution_error` naming PermissionError instead of `error == "timeout"` (INV-11);
  - a cancelled run ends with PermissionError instead of `CancelledError` (INV-12 "CancelledError always propagates");
  - the pipe stays open (INV-26).
  This is rated Major rather than Blocker only because the OS condition was simulated, not produced on a host with sudo. Under the weighted-word rule it is Blocker-class.
  Smallest fix: `contextlib.suppress(ProcessLookupError, PermissionError)` around the kill. This pairs with R-C1's `finally`. Record the widened tolerance under D-14 and §17.
  Spec IDs: INV-11, INV-12, INV-26, §12.3 row 1 ("`_stop` never raises"), D-14

R-C3 [Major] [every-ID] vidbyte/agents/coding.py:101 — `root_dir=""` is accepted and silently becomes the process working directory. This contradicts FR-3 and D-8's stated reason.
  Evidence: `if not isinstance(root_dir, (str, os.PathLike)) or not Path(root_dir).is_dir():`. `Path("")` normalises to `Path(".")`. The probe printed:
  - `os.path.isdir(''): False  Path('').is_dir(): True`
  - `'' ACCEPTED -> C:\Users\422mi\vidbyte-repos\worktrees\vidbyte-sdk-coding-agent`
  - `'   '` is rejected.
  The AC-11 test cases (missing, file, 42, None, omitted) do not cover `""`.
  Failure: A caller writes `root_dir=os.environ.get("REPO_DIR", "")` with the variable unset, or passes `Path("")`. The result is an allow-all agent whose `write_text`, `replace_text` and unsandboxed `bash` operate in whatever folder the process started in. D-8's deciding reason is "An agent that writes files and runs commands should not silently default to the process working directory". FR-3 and EC-6 say anything that is not an existing directory is rejected. EC-2 treats the same empty-value mistake for keys as an error.
  Smallest fix: Use `os.path.isdir(root_dir)` in place of `Path(root_dir).is_dir()`. It returns False for `""` and accepts PathLike. An explicit `"."` still works.
  Spec IDs: FR-3, D-8, EC-6, AC-11

R-C4 [Minor] [user's words / contract text] vidbyte/tools/builtins/bash.py:68 — The model-facing description says the exit code is "always the last line", which is false for every error result.
  Evidence: The description says "The exit code of the command is always the last line of the result." The timeout result ends with `\n[command stopped: it did not finish within the ...-second time limit]` (line 117). `bash_not_found` and `spawn_failed` carry no exit code. §12.3 row 1's required content is "the exit code is the last line", and §8.5 says "(always the final line)" only for the success shape.
  Failure (convention): A reviewer would write: "Don't tell the model 'always' when the timeout result has no exit code; it may parse the last line as one." The model-facing contract should match the result shape (`model-facing-tool-contracts.md`).
  Smallest fix: Say "When the command finishes, its exit code is the last line of the result."
  Spec IDs: §12.3 row 1 (description content), INV-13

R-C5 [Minor] [user's words / docs] vidbyte/agents/README.md:109 — The README says `restore()` gives a `BaseAgent`, but `CodingAgent.restore(state)` raises `TypeError`. D-8 and EC-20 say this is "accepted and documented", and it is not documented.
  Evidence: README: "`fork()` and `restore()` give a `BaseAgent`: restore a saved state with `BaseAgent.restore(...)`". Probe: `CodingAgent.restore -> TypeError CodingAgent.__init__() missing 1 required keyword-only argument: 'root_dir'`. The module header (`coding.py:9`) does say it correctly.
  Failure (convention): A human reviewer would write: "This reads as if `agent.restore(state)` works. Say that calling it on `CodingAgent` raises `TypeError`, then give the `BaseAgent.restore` path."
  Smallest fix: Reword to "`fork()` returns a `BaseAgent`; `CodingAgent.restore(state)` raises `TypeError` (no `root_dir`), so restore with `BaseAgent.restore(state, tools=CodingAgent(...).tools.all())`."
  Spec IDs: D-8, EC-20, §12.3 row 7

VERIFIED CLAIMS:

Implementer, test-plan and spec claims checked:
1. **Windows 3.11 pack: 86 passed, 11 skipped. HELD.**
2. **WSL 3.12.3 pack: 97 passed. HELD.**
3. **`SDK-LINT: PASS` with no rule above main. HELD.**
   - A001 643, A002 682, A006 34, A007 255, S009 340, S015 13, S016 50, S017 78, S019 5, S024 21, S025 261, S039 5, S045 2, S062 889.
   - C016, S006, S052 and S055 are 0 CLEAN.
   - The full run had 0 REGRESSED rows.
4. **`run_ci.py --stage source`: 2715 passed, 12 skipped, "CI passed." HELD.**
5. **Remote CI. HELD.**
   - Run `38046509073` (CI: Source 3.11, Source 3.12, Package) succeeded at `4c4a62ef`.
   - Run `38046510490` (Static policy) succeeded at `4c4a62ef`.
   - `4c4a62ef..4e285d91` changes only `docs/`.
6. **`generate-sdk-public-api.py --check`. HELD:** "current at 1bb1d3b4 ... 594 exports". The contract adds only `"CodingAgent"`.
7. **Budget. HELD.**
   - 2 new source files, 3 classes, 0 dependencies, 0 enums or dataclasses.
   - 5 constructor parameters and 4 module constants.
   - 2 public names: `CodingAgent` in root and `vidbyte.agents`; `BashTool` in `vidbyte.tools.builtins`.
8. **Files outside §12.3: none. HELD.** `git diff 4df5615e..4c4a62ef --stat` shows 8 files, +412/−4.
9. **Tests unchanged since S2. HELD.**
   - `git log a25a3c41..4e285d91 -- tests/` is empty.
   - `--diff-filter=MDR` on `tests/` is empty, so there are additions only.
   - The `lint/` diff is empty.
10. **`4c4a62ef` changes no behavior. HELD.** It adds 6 comment or blank lines in `_FetchedPagesView.execute`.
11. **The `_spawn(executable, command)` deviation is behavior-neutral. HELD.** `execute` reads `self._executable` once, checks it for `None`, and passes the same value. It is recorded in §17.
12. **INV-25 (`_stop` only on the timeout and cancel paths). HELD.** The only two call sites are lines 114 and 122. The completion path returns `_render`.
13. **INV-6, no env reads. HELD.** No `environ` or `getenv` appears in `coding.py`, `bash.py`, `operations/clients/`, `fetch.py`, `operations/base.py` or `lib/http/`.
14. **Real Git for Windows lookup (AC-22 manual half). HELD on this host.** A real call returned `SUCCESS 'hi\n.\n\nexit code: 4'`.
15. **AC-27 on Python 3.13: NOT VERIFIED.** It is still open; `py -3.13` lacks pytest-asyncio and PyYAML, and installing is forbidden.
16. **"`_stop` never raises" (§12.3 row 1): DID NOT HOLD.** See R-C1 and R-C2.

ID walk:
- **Held, with evidence in code or tests:**
  - INV-1 to INV-10, INV-13 to INV-25, except INV-11, INV-12 and INV-26 (R-C1, R-C2).
  - FR-1, FR-2, FR-4 to FR-14. FR-3 is the exception (R-C3).
  - NFR-1, NFR-2, NFR-3, NFR-5, NFR-6. NFR-4 holds except on R-C2's path.
  - AC-1 to AC-29. AC-11 has the R-C3 gap. AC-27 has its 3.13 half open.
  - EC-1 to EC-31 as specified, except EC-6 (R-C3).
- **INV-24, checked by probe:** all 6 runtimes construct as on BaseAgent.
- **EC-20, checked by probe:** `CodingAgent.restore` raises `TypeError`.

User's words (request.md §A, §D):
- **Every decision is honoured:** 7 tools; keys only from parameters; no `SandboxTransport`; an argv subprocess; `system_prompt` required and passed through unchanged; existing tool names; ReplaceTextTool for Edit (Q-1).
- **No §C decision was reversed.** Q-2 to Q-6 were correctly not built.

Spec §5 against the code:
- The construction order (`_resolve_root`, `_web_fetch_tool`, tools, `super().__init__` with the caller policy or allow-all) matches the diagram.
- The runtime path is unchanged: `_check_permission`, then `execute`.
- The view is unwrapped only for pricing and binding (`runtime.py:1200`, `base.py:403`), so `_FetchedPagesView.execute` runs.
- There is no code divergence. The spec's sequence diagram omits D-18's transport close, which is a spec-side omission.

Deviations:
- Reported: `_spawn` signature, and the second row-3 commit. Both were necessary and minimal, and both are recorded in §17.
- Not reported, cosmetic only: `coding.py:31` imports `WebOperationClient` from the `vidbyte.tools.builtins.operations.clients` package root, which row 3's import list does not name. It is used only for a type annotation, and A006 is unchanged at 34. No action needed.

Upstream:
- `origin/main` (`e6cdfa31`) changed `agents/base.py`, `fork.py`, `runtime.py` and `fetch.py` since the base.
- I reviewed the base, fetch and fork hunks. There is no new BaseAgent keyword, and `_render_fetched_pages` is unchanged, so INV-2 and INV-16 survive a rebase.
- The `runtime.py` hunk changes none of `_check_permission`, tool execution or `_record_operation_usage`. It does three things:
  - re-resolves tool schemas when a runtime hook replaces the catalog;
  - narrows the trace credential scrub;
  - keeps middleware-appended notes when `result_max_chars` truncates.

  None of these touches a CodingAgent guarantee.

COMMANDS RUN:
- `git log --oneline 8f23fd67..HEAD`; `git diff --stat origin/main...4e285d91` → 27 files, +4069/−4. Merge base is `8f23fd676d…`.
- `git show 4e285d91:vidbyte/tools/builtins/bash.py | cat -n` and the same for `vidbyte/agents/coding.py` → I read both in full.
- `git diff origin/main...4e285d91 -- vidbyte/__init__.py vidbyte/agents/__init__.py vidbyte/tools/builtins/__init__.py contracts/sdk-public-api.json vidbyte/agents/README.md vidbyte/tools/README.md` → every row 2, 4, 5, 6, 7 and 8 text matches §12.3.
- `git diff origin/main...4e285d91 --diff-filter=MDR --name-status -- tests/` → (empty). `git log --oneline a25a3c41..4e285d91 -- tests/` → (empty). `git diff origin/main...4e285d91 --stat -- lint/` → (empty).
- `git show 4c4a62ef` → `1 file changed, 6 insertions(+)`, comments only.
- Python `inspect.signature` comparison → `BaseAgent params (excl self): 31`; the CodingAgent explicit parameters are the 7 in §8.5; `overrides of BaseAgent names: []`; `generate_reply is base: True`.
- §4 snippet construction run verbatim in a temporary folder containing `my-project`, with `socket.connect` blocked → `('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')`, absolute True, policy `['execute','read','safe','write']`, key in state/card False.
  - **Not run:** the `agent.run(...)` line, because it needs a real OpenAI key and network.
  - Its loop half is covered by `test_spec_snippet_builds_seven_tools_over_an_absolute_root_and_runs_through_the_loop` (passed).
- `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/` (Windows 3.11.0) → `86 passed, 11 skipped in 4.90s`.
- `wsl.exe -d MuseUbuntu1 ... /tmp/s2-coding-agent-venv/bin/python -m pytest -q tests/features/coding_agent/` (3.12.3) → `97 passed in 17.18s`.
- `python lint/run.py` → `SDK-LINT: PASS`, 0 REGRESSED. Per rule: `--rule A001|A002|A006|A007|C016|S006|S052|S055` → 643, 682, 34, 255, 0, 0, 0, 0.
- `python scripts/generate-sdk-public-api.py --check` → `current at 1bb1d3b4… (vidbyte-sdk 0.2.0, 594 exports).` exit 0.
- `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` → `2715 passed, 12 skipped in 18.38s` / `CI passed.`
  - The package stage was not re-run. Remote run `38046509073`'s Package job succeeded.
- `gh run view 38046509073` / `38046510490` → completed/success at `4c4a62ef…`. `gh pr view 690` → draft, OPEN, head `6345baa2`.
- Probe `BashTool(".")` on Windows → `which git C:\Program Files\Git\mingw64\bin\git.EXE`, executable `C:\Program Files\Git\bin\bash.exe`. Then `ls` → `mingw64/bin/bash.exe`: No such file.
- Probe `CodingAgent(root_dir="")` → `'' ACCEPTED -> <cwd>` (R-C3).
- Probe all `AgentRuntimeType` values, `from_run_id`, `CodingAgent.restore` → all ok / `CodingAgent run-x` / `TypeError ... 'root_dir'`.
- WSL probe with `os.killpg` patched to raise EPERM → `timeout path -> RAISED PermissionError ; transport closing: False` and `cancel path -> RAISED PermissionError (spec: CancelledError); transport closing: False` (R-C2).
- WSL probe cancelling during the grace wait (`setsid sleep 20 & ...; sleep 20`, limit 1, grace 3, cancel at 1.6 s) → `raised CancelledError`, `transport is_closing ... False`, then `RuntimeError: Event loop is closed` (R-C1).
- `wsl.exe -- bash -c 'bash -c "ps -o pid=,comm= -p \$\$"; bash -c "true; ps -o pid=,comm= -p \$\$"'` → `8 bash` / `8 ps`. The shell's own pid became `ps`, showing that bash execs a trailing lone command.
- `git status --short` after all runs → (empty). Nothing was written except this report.
