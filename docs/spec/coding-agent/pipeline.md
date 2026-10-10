---
slug: coding-agent
repo: C:/Users/422mi/vidbyte-repos/vidbyte-sdk
worktree: C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent
branch: feat/coding-agent
base_commit: 8f23fd676d60f413e0353281dd73e60dc719407a
pr: https://github.com/cerredz/Vidbyte-SDK/pull/690
until: none
started: 2026-10-10 00:51
---

# Pipeline: CodingAgent — a minimal BaseAgent with seven file-system and web tools

| Stage | Status | Started | Finished | Agent report | Key output |
|---|---|---|---|---|---|
| S0 worktree + capture + recon | done | 2026-10-10 00:51 | 2026-10-10 01:08 | reports/S0-scout.md | base_commit 8f23fd67; code-map.md (4 sections, 329 lines) |
| S1 spec + review | done | 2026-10-10 01:09 | 2026-10-10 | reports/S1-spec-author.md, S1-spec-review.md, S1-spec-review-r2.md | spec r3 @8f669933 approved; r1 SOUND WITH FIXES (1B/3M/4m), r2 SOUND WITH FIXES (0B/1M/2m), all 11 applied |
| S2 tests | done | 2026-10-10 | 2026-10-10 | reports/S2-test-author.md | S2_HEAD d158d5f6 (tests a25a3c41, proof d158d5f6); 42 fns / 97 cases in tests/features/coding_agent/; red: 86 = 67 ImportError(CodingAgent) + 19 ModuleNotFoundError(bash), 11 POSIX-only skipped on win32; spec status tests-written @0b2b4f56 |
| S3 implement | done | 2026-10-10 | 2026-10-10 | reports/S3-implementer.md | S3_HEAD 4e285d91; draft PR #690 https://github.com/cerredz/Vidbyte-SDK/pull/690; 8 rows in 9 code commits (25b5260b..4c4a62ef); pack 86 pass/11 skip win 3.11, 97/97 WSL 3.12 (orchestrator re-ran both); test diff vs S2_HEAD empty; budget 2/2 files, 0/0 enums+dataclasses, 2/2 public names; remote CI 38046509073 + static-policy 38046510490 success @4c4a62ef |
| S4 adversarial review | running | 2026-10-10 | | reports/S4-review-{conformance,conventions,engineering}.md | 3 reviewers launched in parallel on 4e285d91; all hit HTTP 429 mid-run, resumed via SendMessage after reset |
| S5 repair loop | pending | | | | |
| S5 re-review | pending | | | | |
| S6 PR | pending | | | | |

## Counters and caps
- S2_HEAD: d158d5f6 · S3_HEAD: 4e285d91 · PR: #690 · S1 review rounds: 2/2 · S5 repair iterations: 0/8 · S5 re-review rounds: 0/2

## Decisions the orchestrator made
- 2026-10-10 00:51 — Unset the branch upstream (`git branch --unset-upstream`) — `git worktree add -b … origin/main` made `feat/coding-agent` track `origin/main`; pushes must use `git push -u origin feat/coding-agent`.
- 2026-10-10 00:51 — Recorded the unanswered Edit-tool choice as an open question with default `ReplaceTextTool` (the assistant's recommendation in the conversation) — the user replied to the other four decisions but not this one.
- 2026-10-10 00:51 — Recorded "tool names I dont care" as: keep existing model-facing names, build no renaming layer — smallest reading; rule 11.
- 2026-10-10 — Launched scoped S1 review round 2 — r2 changed §8 decisions (D-11, D-13, D-14, D-17) and the shape of §12 (row removed, budget 3→2 new files).
- 2026-10-10 — S1 round-2 reviewer hit an API rate limit mid-run; resumed the same agent after the reset (no report had been written) rather than relaunching fresh.
- 2026-10-10 — Applied every open question's stated default (spec §15): Q-1 ReplaceTextTool; Q-2 no configurable timeout/cap; Q-3 no env allow-list; Q-4 no default result_max_chars; Q-5 no CodingAgent.restore; Q-6 no Windows job-object tree kill. Assumptions A-1..A-9 stand (notably A-1 keyed WebFetch shows page text; A-3 Bash inherits env; A-9 Windows timed-out command may keep running).

- 2026-10-10 — All three S4 reviewers hit the API session limit (HTTP 429) mid-run; resumed each via SendMessage after the reset instead of relaunching (conformance had already written its report but not returned STATUS). Same handling as the S1 r2 reviewer.

## User replies (verbatim)
- (none yet during the run)

## Niche facts accumulated (carried into every later briefing)
- Keyed fetch tools (Firecrawl, Browserbase, Parallel, Tavily) return only "N. url (len chars)" to the model (`fetch.py:39-42`); page bodies live in `metadata["operation_payload"]`. Only `direct_http_fetch` returns the body as output, and it is unbounded (`sources/fetches/http.py:44-49`). — *source:* S0 scout
- `LinkupFetchTool` is always a stub and there is no Linkup client; working keyed providers are Firecrawl, Browserbase, Parallel, Tavily, each client needs only `api_key`. — *source:* S0 scout
- Duplicate tool names raise `ToolRegistrationError` at BaseAgent construction; `_catalog_from_agent_tools` catches only TypeError (`base.py:1288`). — *source:* S0 scout
- `BaseAgent.restore` and `from_run_id` call `cls(...)` with only BaseAgent's kwargs (`base.py:479`, `:270`); a subclass constructor must cope. Forks are always plain `BaseAgent` (`fork.py:43`). — *source:* S0 scout
- Writes are double-gated: default policy SAFE+READ (`base.py:185`, `security.py:33`) and `FileSystemToolConfig.allow_write` (`filesystem.py:31`). A denied call becomes a DENIED tool result; nothing raises. `PatchTool` has no `allow_write`. — *source:* S0 scout
- Subprocess lint rules: S052, S055 (no `shell=True`, no `create_subprocess_shell`), S019, S006, S039 (`asyncio.Lock` banned), A002 (token "subprocess" needs an `@intent` comment), A007 (timeout/byte numbers must be named constants), S025 (model-facing descriptions need 4+ sentences). S012/S013 do NOT match subprocess calls. The only subprocess precedent in `vidbyte/` is `vidbyte/tools/mcp/transport.py:168` (`asyncio.create_subprocess_exec`). — *source:* S0 scout
- A001 header: copy the `FILE:/PURPOSE:/ROLE IN CODEBASE:/…` format of `vidbyte/agents/jev/agent.py`; the "Context Protocol Header" style in `base.py`, `handoff.py`, `continual_trace.py` is non-compliant. Lint counts only git-tracked files: `git add` new files before running `python lint/run.py`. — *source:* S0 scout
- Semgrep is NOT in `run_ci.py`; it runs only in `.github/workflows/static-policy.yml` (dispatch only, `semgrep==1.170.1`). All CI is manual dispatch on ubuntu-latest (Python 3.11 and 3.12); Windows bash behaviour is never exercised by CI. — *source:* S0 scout
- Workspace gotchas: run `scripts/run_ci.py` with `PYTHONPATH` unset (it breaks the package smoke step); Semgrep needs its own venv/pipx because the SDK pulls `mcp` 2.x; dispatch CI with `gh workflow run ci.yml --ref feat/coding-agent` or PR checks never appear. — *source:* orchestrator memory of earlier runs
- Unverified (S0): which `bash` Python's subprocess resolves on Windows (Git Bash, WSL launcher, and WindowsApps bash are all on PATH); whether importing `vidbyte.tools.builtins` from `vidbyte/agents/__init__.py` cycles (`tools/builtins/fork/fork.py` imports `vidbyte.agents`). — *source:* S0 scout
- `BaseAgent.__init__` has 31 keyword-only params; `name` and `system_prompt` have no default. Setting `self.root_dir` before `super().__init__` is safe (no slots, no clash). — *source:* S1 author
- A002 also matches the function's own name and annotation names: `_web_fetch_tool` and anything annotated `asyncio.subprocess.Process` need `# @intent`. Check with `python lint/run.py --rule A002`. — *source:* S1 author
- Use `sys.platform == "win32"` branches (not `os.name`): typeshed declares `os.killpg`/`signal.SIGKILL` only for non-Windows and S009 runs mypy on the host OS. — *source:* S1 author
- Pricing reads only `metadata["operation_usage"]` (`_billable_attempts`, `units_used`, `mode_used`, `attempts_used`), so replacing `output` in a wrapper does not change billing. — *source:* S1 author
- Test seams: patch `HttpTransport._send_once` on the class (covers clients built from a key); bash constants are imported by name, so patch `vidbyte.tools.builtins.bash.BASH_*`. — *source:* S1 author
- A returned `ToolResult.error` does not set the runtime's `timed_out` flag; only a raised `ToolExecutionError(error="timeout")` does. — *source:* S1 author
- `C:\Program Files\Git\bin\bash.exe` is a 47 KB launcher for `usr\bin\bash.exe`; killing it leaves the command running; MSYS breaks the parent chain so `taskkill /F /T` does not reach it. — *source:* S1 review r1
- asyncio `Process.wait()` returns at process exit on 3.11.0 but only after all pipes close on 3.13. `python` here is 3.11.0, `py` defaults to 3.13.1; CI is ubuntu-latest 3.11/3.12. — *source:* S1 review r1
- `shutil.which` from Git Bash: git=`<G>\mingw64\bin\git.EXE`, bash=`<G>\usr\bin\bash.EXE`; from PowerShell: git=`<G>\cmd\git.EXE`, bash=WSL launcher `C:\WINDOWS\system32\bash.EXE`. — *source:* S1 review r1
- No import cycle between `vidbyte.tools.builtins` and `vidbyte.agents`. Pricing recorded only at `vidbyte/agents/runtime.py:1195-1214`, unwrapping any `_ToolWrapper`. — *source:* S1 review r1
- S024 caps control-flow nesting at 3 (if/for/with/try/match); main shows S024 IMPROVED 25→21. — *source:* S1 review r1
- r2 contract: `process.wait()` may be called only in `_collect` (under `BASH_TIMEOUT_SECONDS`) and `_stop` (under `BASH_KILL_GRACE_SECONDS=5.0`, swallowing only that wait's TimeoutError). Bash output cap `BASH_MAX_OUTPUT_BYTES=50_000` (head kept). Constants are module-level in `vidbyte/tools/builtins/bash.py`. §12.3 rows: 1 bash.py, 2 builtins `__init__`, 3 coding.py, 4 agents `__init__`, 5 root `__init__`, 6 contract, 7 agents README, 8 tools README. — *source:* S1 author r2
- `_stop` order: kill (POSIX `killpg` always; Windows `kill` only while `returncode is None`; ignore ProcessLookupError) → grace `wait_for` (swallow only its TimeoutError) → `getattr(process, "_transport", None)` close. Never raises. Nesting exactly at S024's limit of 3. — *source:* S1 author r3
- A007 walks up from any `read(...)` to the enclosing `while`: `_collect`'s read loop must contain no numeric literal at all. — *source:* S1 review r2
- Without the transport close, an orphan holding the pipe yields `Exception ignored … Event loop is closed` after `asyncio.run`; pytest reports PytestUnraisableExceptionWarning but has no `filterwarnings=error`, so AC-28 needs an explicit check. `BaseAgent.run` is `asyncio.run(...)` (`base.py:924`). — *source:* S1 review r2 / author r3
- On Windows keep Git's `binash.exe` launcher (from a PowerShell-launched Python, `usrinash.exe` cannot find ls/grep/sleep). — *source:* S1 review r2
- Test tree for the no-edit diff: `tests/features/coding_agent/` (conftest.py, 5 test modules, FEATURE.md, README.md). `git diff d158d5f6..HEAD --stat -- tests/` must stay empty after S2. — *source:* S2 test author
- Tests import `vidbyte.CodingAgent`, `vidbyte.agents.CodingAgent`, `vidbyte.agents.coding.CodingAgent`, `vidbyte.tools.builtins.BashTool`, module `vidbyte.tools.builtins.bash` (BashTool + 4 BASH_* constants); each must be in its package `__all__`. Keyed fetch view needs public `wrapped_tool`. — *source:* S2 test author
- BASH_* constants must be read at call time (tests monkeypatch timeout 2.0, grace 1.0, cap 1000). AC-22 patches `sys.platform` and `shutil.which` during `BashTool(root)` construction only: read them as module attributes, not `os.name` / `from shutil import which`. — *source:* S2 test author
- Missing bash must not raise in `BashTool.__init__` or `CodingAgent.__init__` (AC-17 builds with PATH pointed at an empty folder). Timeout result's last line contains the patched limit; `spawn_failed` names `ValueError`/`OSError` without the exception message. — *source:* S2 test author
- Highest-value test: `test_bash_tool_process_bounds.py::test_cancellation_kills_the_process_group_even_after_the_shell_has_exited` fails a natural `if process.returncode is None` guard around POSIX `killpg`. AC-28 detects open `BaseSubprocessTransport` via gc after `execute`. — *source:* S2 test author
- POSIX-only tests skip on win32; run them in WSL with `/tmp/s2-coding-agent-venv/bin/python` (distro MuseUbuntu1; `MSYS_NO_PATHCONV=1` from Git Bash). AC-27's Python 3.13 half is manual. AC-29 truncation line's only digits must be the cap. — *source:* S2 test author
- S3 deviation: `_spawn(executable, command)` takes the already-None-checked executable (mypy S009); recorded in spec §17. Code reads two private attributes: `process._transport` (D-18) and `PricedOperationTool._PAYLOAD_KEY` in coding.py. — *source:* S3 implementer
- S3 limitation: `_stop` suppresses only ProcessLookupError and the grace TimeoutError, so an EPERM from `killpg` could replace CancelledError. `bash_not_found` hint reads `sys.platform` at call time. A blank line precedes `exit code: N` when output ends with a newline (spec literal format). — *source:* S3 implementer
- origin/main moved to e6cdfa31 and adds lint rules A009, C006, C007, C008 that this branch lacks; none of the 8 §12.3 files changed upstream. Re-lint after any rebase/merge of main. — *source:* S3 implementer
- AC-27 (Python 3.13) not run: `py -3.13` lacks pytest_asyncio and PyYAML; installing into it is off-limits. AC-22 against a real Git for Windows layout not run (manual per test plan). — *source:* S3 implementer
