# S6 PR author report: coding-agent

Stage S6 · 2026-10-10 · worktree `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent` · branch `feat/coding-agent` · PR https://github.com/cerredz/Vidbyte-SDK/pull/690 (still a draft, base `main`).

- **HEAD after this stage:** `00a1c8c2` (`docs(spec): finalize coding-agent for PR`), pushed.
- **Code:** unchanged since `581fc272`. I changed no source and no tests.
- **This report** is untracked in the worktree (see "Notes for the orchestrator").

## 1. What the code does (written from the diff before reading the spec)

**Construction: `vidbyte/agents/coding.py`**
- `CodingAgent(BaseAgent)` takes the keyword-only `root_dir`, four optional keys (`firecrawl_api_key`, `browserbase_api_key`, `parallel_api_key`, `tavily_api_key`), `tools` and `permission_policy`. Everything else goes to `BaseAgent.__init__` through `**kwargs`.
- `__init__` (`:54-96`) works in this order:
  1. `_resolve_root` (`:99-104`) requires a `str` or `os.PathLike` for which `os.path.isdir` is true. Otherwise it raises `ConfigurationError(details={"root_dir": ...})`. Then it resolves the path once.
  2. `_web_fetch_tool` (`:107-130`) walks an ordered table of (parameter, key, tool class, client class):
     - A supplied key that is blank or not a string raises `ConfigurationError`, naming only the parameters.
     - More than one key raises `ConfigurationError`, naming the parameters.
     - No key returns `DirectHttpFetchTool()`.
     - Exactly one key returns `_FetchedPagesView(ToolClass(client=ClientClass(key)))`.
  3. It builds `BashTool(root)`, then `ReadLinesTool`, `WriteTextTool` and `ReplaceTextTool` over one `FileSystemToolConfig(root=root, allow_write=True)`, then `GlobTool(root)`, `GrepTool(root)` and the fetch tool.
  4. It appends the caller's tools (a sequence or a `Tools` catalog) and sets `self.root_dir`.
  5. It calls `super().__init__` with the caller's policy or `PermissionPolicy.allow_all()`.
- `CodingAgent` overrides no `BaseAgent` method.

**`_FetchedPagesView` (`:133-175`)**
- It is a `_ToolWrapper`. It delegates `spec`, `validate_call` and `execute`.
- On a SUCCESS result whose metadata holds a `FetchPayload` under `PricedOperationTool._PAYLOAD_KEY`, it appends `"<i>. <final_url>\n<content>"` for each page to `output`, using `dataclasses.replace`.
- Every other result passes through unchanged. Metadata is never touched, so `AgentRuntime._record_operation_usage` prices the unwrapped tool exactly as before.

**Run time: `vidbyte/agents/runtime.py`, unchanged**
- `AgentRuntime` calls `_check_permission` (`:1119`, `:1270`). A denial becomes a DENIED result.
- Next it calls `_validate_tool_call` (`:1120`, `:1281`), then `_execute_tool`, then `_record_operation_usage` (`:1130`).

**`BashTool`: `vidbyte/tools/builtins/bash.py`**
- **Bounds.** Four module constants, read at call time: `BASH_TIMEOUT_SECONDS=600.0`, `BASH_MAX_OUTPUT_BYTES=50_000`, `BASH_READ_CHUNK_BYTES=65_536` and `BASH_KILL_GRACE_SECONDS=5.0` (`:33-36`).
- **Finding bash.** `__init__` resolves the root and runs `_find_bash` once (`:48-61`):
  - On POSIX it uses `shutil.which("bash")`.
  - On win32 it takes the first `bin/bash.exe` that is a file under the first three parents of the resolved `git`, or `None`.
- **Validation.** `validate_call` requires a non-blank `str` command.
- **`execute` (`:93-126`):**
  - No executable gives `bash_not_found`, with install advice for the platform.
  - `_spawn` (`:128-148`) calls `create_subprocess_exec(exe, "-c", command, cwd=root, stdin=DEVNULL, stdout=PIPE, stderr=STDOUT, start_new_session=True)`. An `OSError` or `ValueError` gives `spawn_failed`, naming only the class.
  - Then `asyncio.wait_for(_collect(...), BASH_TIMEOUT_SECONDS)`. `_collect` (`:150-163`) keeps the first 50,000 bytes in a buffer the caller owns, counts the rest, then waits for exit.
  - On `TimeoutError`: `_stop`, then the `timeout` error result. It holds the output so far, a truncation line when the buffer is full, and the time-limit line.
  - On `CancelledError`: `_stop`, then re-raise.
  - On normal completion: `_render` (`:193-197`) builds a success result. The output ends with `\nexit code: N`, and nothing is killed.
- **`_stop` (`:165-191`):**
  - Inside `try`, the kill: POSIX `os.killpg(pid, SIGKILL)` always; Windows `process.kill()` only while it is running. Both suppress `ProcessLookupError` and `PermissionError`.
  - Then a wait bounded by `BASH_KILL_GRACE_SECONDS` that swallows its `TimeoutError`.
  - In `finally`, `getattr(process, "_transport", None).close()` under `suppress(PermissionError)`.

**Wiring**
- `BashTool` is exported from `vidbyte.tools.builtins`.
- `CodingAgent` is exported from `vidbyte.agents` and `vidbyte`.
- The contract is regenerated.
- Both READMEs gain short sections.

## 2. Deviations: code against spec §4, §5, §8 and §12

| # | Spec said | Code does | Recorded where |
|---|---|---|---|
| 1 | §12.3 row 1: `_spawn(command)` | `_spawn(executable, command)`, so mypy sees the already-checked `str`. No behavior change. | spec §17 (S3); PR body |
| 2 | D-14 / §12.3 row 1: ignore `ProcessLookupError` | also ignores `PermissionError` on the kill and on `transport.close()`, and the close is in `finally` (R-1, `415f7c22`) | spec §17 (S5); PR body |
| 3 | §14: no test edits after S2 | two granted edits: the EC-11 test body (R-2, `a49b7dd8`) and the pack README line (R-7, `581fc272`) | review.md, verify-log; PR body |
| 4 | §5 sequence diagram: kill, wait, return | the code also closes the transport in `finally`, and `_stop` suppresses both errors | **fixed at S6**: §5 diagram plus one prose clause updated; §17 S6 row |

These are not deviations, because the code matches the spec:
- R-3's `os.path.isdir` (§12.3 does not name the call).
- R-4's five-sentence description. EC-14 required the Windows caveat. Sentence 5 is the spec's literal wording, which is R-C1.
- R-6's hint text.
- The blank line before `exit code:` when output ends in a newline (§8.5's literal format).

## 3. Spec §4 snippet: run as written

I used the scratch script `scratchpad/s6/run_snippet.py`, on Windows 11 with Python 3.11.0, run from Git Bash with `PYTHONPATH` set to the worktree, in a `TemporaryDirectory` holding `my-project`.
- The construction and print lines ran verbatim.
- For `agent.run(...)`, I bound the pack's `ScriptedToolRunner` (one `bash` call `echo snippet-ran`, then isDone) with `tests.agent_test_support.bind_test_runner`.
- No provider call was made, and no real key was used.
```
C:\Users\422mi\AppData\Local\Temp\tmpa5xwq7sc\my-project
('bash', 'read_lines', 'write_text', 'replace_text', 'glob', 'grep', 'firecrawl_fetch')
Fixed the first failure.
root is absolute and equals ./my-project: True
tool_call_states: ('succeeded', 'succeeded')
bash tool message seen by the model: 'snippet-ran\n\nexit code: 0'
policy: ['execute', 'read', 'safe', 'write']
```
AC-1 holds as written.

**Windows lookup on the real Git for Windows install** (extra evidence for AC-22 and EC-31):
- **From PowerShell:** `which git` gave `C:\Program Files\Git\cmd\git.EXE` and `which bash` gave `C:\WINDOWS\system32\bash.EXE`. `BashTool._executable` was `C:\Program Files\Git\bin\bash.exe`, and the call returned `success 'from-powershell\nMINGW64_NT-10.0-26200\n\nexit code: 0'`.
- **From Git Bash:** `which git` gave `...\Git\mingw64\bin\git.EXE` and `which bash` gave `...\Git\usr\bin\bash.EXE`. `BashTool._executable` was `C:\Program Files\Git\bin\bash.exe`, and the call returned `success 'from-git-bash\n...exit code: 0'`.
- The `<G>\bin\git.exe` layout was not tested on a real install.

## 4. Gates I ran at this stage

| Gate | Result |
|---|---|
| `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` at `7c341518` | `SDK-LINT: PASS` … `2715 passed, 12 skipped in 23.26s` / `CI passed.` |
| `python scripts/run_ci.py --stage package --dist-dir <scratch>` (PYTHONPATH unset) | `Installed vidbyte-sdk 0.2.0 passed smoke checks.` / `CI passed.` |
| Pack, Windows 3.11 | `86 passed, 11 skipped in 5.00s` |
| Pack, WSL 3.12 (`/tmp/s2-coding-agent-venv`) | `97 passed in 17.32s` |
| `python lint/run.py` after the S6 commit | `SDK-LINT: PASS` |
| Remote CI `38078804606` on `00a1c8c2` | Source 3.11 `2718 passed, 9 skipped` / `CI passed.`; Source 3.12 `2718 passed, 9 skipped, 12 warnings` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.0 passed smoke checks.` / `CI passed.` |
| Remote Static policy `38078806048` on `00a1c8c2` | `Ran 1 rule on 857 files: 0 findings.` |

**Scratch merge with `main`.**
- I exported `git merge-tree --write-tree HEAD origin/main` (tree `cf04415b`, with `origin/main` at `77084eb2` then) to the scratchpad. The contract conflict markers were left in.
- Results:
  - Pack on Windows: `86 passed, 11 skipped`.
  - Pack on WSL: `97 passed`.
  - Full pytest on Windows: `2857 passed, 12 skipped`.
- The first full run had `1 failed`: `tests/test_codex_tools.py::CodexSdkContractTests::test_cancelled_turn_releases_its_waiting_reader`. That test passed 4 times on its own and on a full re-run, so it is a flake unrelated to this PR.
- A per-file collection diff showed only the pack added. The `test_agent_tool_loop.py` 25-against-21 difference came from `origin/main` moving to `d7b25110` (#699) between my two exports. It is not a merge loss.

## 5. Final PR state

```
$ gh pr view https://github.com/cerredz/Vidbyte-SDK/pull/690 --json title,isDraft,baseRefName,url
{"baseRefName":"main","isDraft":true,"title":"feat(agents): add CodingAgent, a BaseAgent with bash, file, search, and web-fetch tools","url":"https://github.com/cerredz/Vidbyte-SDK/pull/690"}

$ gh pr checks https://github.com/cerredz/Vidbyte-SDK/pull/690
no checks reported on the 'feat/coding-agent' branch

$ gh api repos/cerredz/Vidbyte-SDK/commits/00a1c8c2651deb2179da4e9de223ce1df17dfe8c/check-runs --jq '.total_count, (.check_runs[] | "\(.name) \(.status) \(.conclusion)")'
4
Package completed success
Static policy completed success
Source / Python 3.11 completed success
Source / Python 3.12 completed success

$ gh pr view ... --json mergeable,mergeStateStatus
{"mergeStateStatus":"DIRTY","mergeable":"CONFLICTING"}
```

**Why `gh pr checks` says "no checks".**
- GraphQL `statusCheckRollup` is `null` for `00a1c8c2`, for `581fc272`, and for the heads of merged PRs #695, #696 and #699. `gh pr checks 696` also says "no checks reported".
- Runs started by `workflow_dispatch` are never linked to a PR in this repo, so `gh pr checks` cannot show them.
- The head commit's check runs (4 of 4 green) are the real signal.

**The title has no `[WIP]`, and the PR is still a draft.** The body ends with the required attribution line.

**The PR body differs from the committed `pr-body.md` in three places.** The briefing allows editing the body after the runs finish. The GitHub copy adds:
- two rows for the head runs `38078804606` and `38078806048`;
- the "12 warnings" detail on the `581fc272` Source 3.12 row;
- one paragraph that explains "no checks" and names the difference.

I could not put the head runs into the committed copy without moving the head off those runs.

## 6. Candidate field-guide lessons

These come from review.md: the conventions-lens findings, plus R-1, R-2 and R-3, which reflect repo-specific rules. They are drafts only. Nothing was written to `field-guide/`.

### Make every sentence of a model-facing description true on every result path and every OS (R-4, R-C1)
- **When:** Writing or revising a builtin's `ToolSpec.description` when the tool has several result shapes (success, error codes, timeout) or platform branches.
- **Do:** Check each sentence against each result the tool returns and each `sys.platform` branch. State any platform limit in the description itself, not only in the file header or the README. Keep 4–5 sentences.
- **Because:** The description is the model's only manual. In PR #690, "the exit code is always the last line" was false for timeout and errors, the Windows "not stopped" limit was missing (EC-14 required it), and after the fix "the process is killed" was still false on Windows.
- **Check:** For each sentence, name the code line that makes it true on POSIX and on win32. Run `lint/rules/s025_model_facing_description_depth.SentenceCounter` on `spec().description`.
- **Evidence:** PR #690 review R-4, fixed `977c7d23`; re-review R-C1 is a follow-up.

### Give each error code a hint that is true for every cause mapped to it (R-6)
- **When:** Several exception classes collapse into one `metadata["error"]` code, for example `spawn_failed` for `OSError` and `ValueError`.
- **Do:** Write one neutral remediation that covers every cause. Alternatively, split the codes. Keep naming only `type(exc).__name__` (S017).
- **Because:** In PR #690 a removed root folder (`NotADirectoryError`) told the model to "shorten the command or remove NUL characters", which sends it on a wrong repair loop.
- **Check:** List the exceptions caught by the handler and read the hint once for each.
- **Evidence:** PR #690 review R-6, fixed `388993f9`.

### State a README's or header's claims about behavior per method, and check each one (R-5, R-7)
- **When:** Adding a README section, a pack README, or an A001 header that says what a class does or where its code lives.
- **Do:** Write separate claims for separate methods ("`fork()` returns a `BaseAgent`; `CodingAgent.restore(state)` raises `TypeError`"), and check every path with `ls`.
- **Because:** In PR #690, "`fork()` and `restore()` give a `BaseAgent`" hid a `TypeError`, and the pack README put the filesystem tools in `builtins/`. Agents copy what docs say.
- **Check:** For each behavior claim run a one-line probe, and for each path run `ls`.
- **Evidence:** PR #690 review R-5 (`15aed1e0`) and R-7 (`581fc272`).

### Put new `_ToolWrapper` views in the tools layer, beside `_CustomizedTool` (R-8, pending human review)
- **When:** A feature needs a delegating view over an existing tool.
- **Do:** Define it in `vidbyte/tools/`, not in the agent module, even when only one agent uses it.
- **Because:** Every other tool class and wrapper lives in `vidbyte/tools/` (`base.py:_CustomizedTool`, `activity.py:_ActivityBoundTool`, ContinualTraceAgent's `UpdateTraceTool`). In PR #690 the verifier downgraded this to a sibling preference because no binding rule covers it. Promote it only if a human reviewer agrees.
- **Check:** Run `grep -rn "class .*(_ToolWrapper\|BaseTool)" vidbyte/agents/`. It should be empty.
- **Evidence:** PR #690 review R-8 (follow-up).

### A stop path inside a cancellation handler must never raise and must close the transport in `finally` (R-1)
- **When:** Writing cleanup that runs inside `except asyncio.CancelledError` or on a timeout for an asyncio subprocess.
- **Do:** Suppress `ProcessLookupError` and `PermissionError` on the kill. Bound the wait after the kill. Close `getattr(process, "_transport", None)` in `finally` under `suppress(PermissionError)`.
- **Because:** Any exception there replaces the propagating `CancelledError` (S019's intent). The stdlib `BaseSubprocessTransport.close()` re-kills a running child and lets `PermissionError` through. Without the close, `asyncio.run` prints "Event loop is closed" and a long-lived service leaks one pipe per timeout.
- **Check:** Probe with `os.killpg` patched to raise EPERM, and with a second cancel during the grace wait. The transport must report `is_closing()`.
- **Evidence:** PR #690 review R-1, fixed `415f7c22`.

### A test that relies on closed stdin must install its own never-ending stdin (R-2)
- **When:** Testing that a subprocess tool does not inherit stdin.
- **Do:** `os.dup2` a pipe that never reaches end of file onto fd 0 for the call, and restore it in `finally`.
- **Because:** `scripts/run_ci.py` runs `python -m pytest` with fd capture on, and pytest already puts the null device on fd 0. In PR #690 the stdin test therefore passed even with `stdin=DEVNULL` removed.
- **Check:** Remove `stdin=DEVNULL` in memory. The test must fail.
- **Evidence:** PR #690 review R-2, fixed `a49b7dd8`.

### Validate a `root_dir` with `os.path.isdir`, not `Path(...).is_dir()` (R-3)
- **When:** A constructor accepts a root folder for root-scoped tools.
- **Do:** Check `isinstance(root_dir, (str, os.PathLike)) and os.path.isdir(root_dir)` before `Path(root_dir).resolve()`.
- **Because:** `Path("")` is `Path(".")`, so `""` (for example from an unset environment variable) silently roots every tool at the process working directory. In PR #690 that agent also had write and execute permissions.
- **Check:** Parametrize the bad-root test with `""`.
- **Evidence:** PR #690 review R-3, fixed `64df91ce`. The test case is still a follow-up.

## 7. Things that looked wrong while reading (none fixed; no source changed)

1. **The merge with `main` conflicts.** This is the only real blocker to merging.
   - `contracts/sdk-public-api.json:3-5` conflicts with `main` (`d7b25110`, 45 commits past base `8f23fd67`). `main` bumped `version` to 0.2.1 and changed `source.commit`. GitHub reports `mergeable: CONFLICTING`.
   - To resolve it: merge `main`, run `python scripts/generate-sdk-public-api.py`, then re-run `python lint/run.py`. `main` added A009, C006–C015, S063 and S064, which this branch has never run.
   - `main` also touched `vidbyte/agents/base.py`, `fork.py`, `runtime.py`, `code_search/glob.py`, `grep.py`, `operations/fetch.py` and `filesystem/replace_text.py`. The scratch merge passed (§4).
2. `vidbyte/tools/builtins/bash.py:68`: sentence 5 says the process "is killed", which is false on Windows (R-C1, a known follow-up).
3. `vidbyte/tools/builtins/bash.py:115`: the timeout result sets `truncated=True` whenever the buffer holds exactly 50,000 bytes, even if the command printed exactly 50,000 bytes and nothing was dropped. This matches D-19 ("when the buffer is full"). It is harmless, and I did not raise it.
4. `vidbyte/tools/builtins/bash.py:197`: output that ends in a newline gives a blank line before `exit code: N` (`'snippet-ran\n\nexit code: 0'`). This is §8.5's literal format and is cosmetic.
5. `vidbyte/__init__.py:702`: `"CodingAgent"` sits between `"JudgeReportPayload"` and `"JevAgent"` in `__all__`. That matches §12.3 row 5 ("next to JevAgent"), and that part of the list is not sorted. Cosmetic.
6. `tests/features/coding_agent/test_bash_tool_process_bounds.py:83-93`: `_live_group_members` returns `[]` when `/proc` is missing (macOS). The "group is empty" assertions at `:172` and `:330` are therefore vacuous there. CI and WSL are Linux, so no gate is affected.
7. `tests/features/coding_agent/test_coding_agent_contract.py:14` and `test_coding_agent_web_fetch.py:14` fail ruff I001 (known; no gate scans `tests/`).
8. The private-attribute reads `coding.py:169` (`PricedOperationTool._PAYLOAD_KEY`) and `bash.py:188` (`_transport`) are deliberate and documented (D-18, §12.3 row 3).
9. No dead code was found. No test looked vacuous on Linux or Windows beyond item 6, and beyond R-2, which is already fixed.

## Notes for the orchestrator

- **This report is untracked** at `docs/spec/coding-agent/reports/S6-pr-author.md`, because the procedure writes it after the final push. Committing it moves the head to a commit with no runs. After pushing, re-dispatch `ci.yml` and `static-policy.yml`, or accept that the 4 green runs are on `00a1c8c2`, the parent docs-only commit.
- **The briefing's "origin/main (e6cdfa31)" is stale.** `main` is now `d7b25110`.
- **`gh pr checks` cannot be the gate here.** Use `gh api repos/cerredz/Vidbyte-SDK/commits/<sha>/check-runs`.
