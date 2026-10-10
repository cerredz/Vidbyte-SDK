VERDICT: SOUND WITH FIXES — the CodingAgent, WebFetch view, permission default, and export design hold up against the code, but BashTool's stop path hangs a run forever on the user's own Windows/Python 3.13 setup, and three other Bash decisions need correcting before the blind test author binds to them.

WHAT THE SPEC GETS RIGHT (max 4 bullets, concrete, so the author does not "fix" what works)

- **`_FetchedPagesView` is required by the request, not extra scope, and it does not break pricing. Keep it.** A keyed fetch tool shows the model only `"<label>: N pages.\n1. <url> (<len> chars)"` (`vidbyte/tools/builtins/operations/fetch.py:39-42`), so without the view, "WebFetch" fetches nothing the model can read. No smaller existing mechanism exists:
  - `customize()` changes descriptions only (`vidbyte/tools/base.py:61-76`).
  - `_ActivityBoundTool` only adds an annotation (`vidbyte/tools/activity.py`).
  - Editing `_render_fetched_pages` changes context cost for every caller.

  Pricing has exactly one recording site, `AgentRuntime._record_operation_usage` (`vidbyte/agents/runtime.py:1195-1214`). It unwraps every `_ToolWrapper` through `_unwrap_tool` and reads only `result.metadata`, which the view passes through by `dataclasses.replace(result, output=...)` (`ToolResult` is a frozen slotted dataclass, `vidbyte/lib/dataclasses/tools.py:274`).
- **The permission design is the minimal forced change.** It has three parts:
  - The default policy is `PermissionPolicy.allow_all()`, and a caller's `permission_policy` object wins.
  - One shared `FileSystemToolConfig(root, allow_write=True)` serves Read, Write, and Edit.
  - INV-19 and INV-21 pin the defaults of BaseAgent and the file config.

  The `restore` break is named honestly (EC-20, D-8, Q-5). `BaseAgent.restore` calls `cls(...)` without `root_dir` (`vidbyte/agents/base.py:479-503`). `from_run_id` still works, because `root_dir` travels in `**kwargs` (`base.py:268-269`). Cold session resume already calls `BaseAgent.restore` (`vidbyte/sessions/session.py:435`).
- **The key handling complies with AGENTS.md and does not leak.**
  - Four optional key parameters comply with AGENTS.md's enum rule. Their values are open-set secrets, not closed-set choices, and no string-keyed registry is introduced.
  - `export_state()` and `card()` record only tool names and permission values (`base.py:297-307`, `:449-477`).
  - Clients keep the key in a private `_api_key` with the default object repr (`operations/clients/_base.py:52-61`), and the key appears only in request headers.
  - Failing loudly on two keys is plain input validation, not an invented precedence rule.
- **Exports, imports, and gate commands are right as written.**
  - The rule of importing only concrete submodules is right, and the cycle the scout flagged does not exist. At base, both `import vidbyte.tools.builtins` first and `import vidbyte.agents` first succeed (run with `PYTHONDONTWRITEBYTECODE=1`), because `runtime.py:149` already imports a builtins submodule at module top. A006 also skips `__init__.py` façades (`lint/rules/a006_directed_dependency_graph.py`, `_is_concrete`).
  - The contract steps are in the right order: commit `vidbyte/__init__.py`, then regenerate the contract. This matches the generator's pin to HEAD.
  - The §11 gate commands match `local-ci-verification.md` and the workflows:
    - The source stage runs with `PYTHONPATH`, the package stage without it.
    - Semgrep runs only in `static-policy.yml`.
    - Every CI workflow is `workflow_dispatch` only.

FINDINGS (ranked, most severe first, max 15)

R-1 [Blocker] [L5] §8.1 D-14, INV-11, INV-12, EC-14, G-3 — On Windows, a timeout or cancellation stops only Git's `bash.exe` launcher; the command survives, and on Python 3.13 `_stop`'s `await process.wait()` then blocks until the orphan exits, so a timed-out long-running command hangs the run forever
  Evidence:
  - The spec says: D-14 "on Windows `process.kill()` … then `await process.wait()`". EC-14 says "Only `bash.exe` is killed; its children may keep running". G-3 promises Bash "cannot hang a run forever … runs on the user's Windows machine (Git Bash)".
  - Repo and machine: `C:\Program Files\Git\bin\bash.exe` is 47,000 bytes; `usr\bin\bash.exe` is 2,553,064 bytes. The process tree after a spawn is launcher → `Git\bin\..\usr\bin\bash.exe` → `sleep.exe`. The parent PID of `sleep.exe` was not the shell's PID: MSYS's exec emulation breaks the Windows parent chain.
  - Test 1: after `process.kill()` on the launcher, both new `sleep.exe` PIDs were still alive.
  - Test 2: `taskkill /F /T /PID <launcher>` returned 0, and all three new `sleep.exe` PIDs were still alive.
  - Test 3: under `py -3.13`, `await p.wait()` after killing the launcher took 7.0 s. That is the rest of `sleep 8`. Python 3.13's `asyncio/base_subprocess.py` wakes `wait()` waiters only in `_call_connection_lost`, after every pipe closes. Python 3.11.0 wakes them in `_process_exited`. `py -0` shows 3.13 as this machine's default interpreter.
  Failure: On Windows with Python 3.13, the model runs `npm run dev`, or any command that never exits.
  - At 600 s, `_stop` kills the launcher and then waits on a pipe the orphaned shell still holds. `execute` never returns.
  - With the default `ToolSettings.tool_timeout_seconds=None`, the run hangs forever.
  - With an agent-level tool timeout set, the cancel path's `finally` runs the same unbounded `wait()`, so that does not rescue the run either.
  - On 3.11 the call returns, but every timed-out command keeps running and holds ports and files.
  - INV-11 ("kills the command") and INV-12 are false on Windows, and EC-14 understates the problem: it is the command itself that survives, not just its children.
  Smallest fix:
  1. Bound the post-kill `await process.wait()` in `_stop` with a short named grace constant, for example `BASH_KILL_GRACE_SECONDS`. Return the `timeout` result, or re-raise `CancelledError`, whether or not that wait finished.
  2. Restate INV-11, INV-12, and EC-14 for Windows: only the launcher is stopped, and the command may outlive the call. Say the same in the README caveats (row 8) and the bash.py KNOWN EDGE CASES.
  3. Add an AC that CI can run on POSIX: "a command whose descendant has left the process group (`setsid`) and holds the output pipe → the timeout result still arrives within `BASH_TIMEOUT_SECONDS` + grace".
  4. Optional Q-6: "Kill the whole Windows process tree with a job object on timeout or cancellation?" Default: not built. `taskkill /T` is not a fix (verified above).

R-2 [Major] [L5] §12.3 row 2, §5 sequence, INV-11, INV-12 — The time limit covers only reading the output, so `process.wait()` after end-of-output is unbounded, and the cancel path kills only "while the process is still running", which misses a process group whose leader has already exited
  Evidence:
  - Row 2: "read under `asyncio.wait_for(..., BASH_TIMEOUT_SECONDS)` … on completion → `await process.wait()`".
  - Row 2: "a `try/finally` calls `_stop(process)` whenever the process is still running (covers cancellation)".
  - D-14 applies the kill "on timeout and, in a `finally`, whenever the call leaves while the process is still running".
  Failure: Two inputs break the invariants.
  - (a) Command `exec >/dev/null 2>&1; sleep 100000` on POSIX. The shell closes its end of the pipe, so the read gets end-of-output at once and returns inside the limit. `await process.wait()` then blocks about 28 h under default settings. This violates INV-11 ("No command runs longer than BASH_TIMEOUT_SECONDS") and EC-8.
  - (b) Command `python server.py &` (EC-9's own example). The shell exits at once, so asyncio sets `returncode`, while the server keeps the pipe open. When the agent-level tool timeout cancels the call, the `finally` sees a finished process and skips `_stop`. The server keeps running in its own session forever. This violates INV-12.
  Smallest fix:
  - Put "read to end of output, then wait for exit" inside one `asyncio.wait_for(..., BASH_TIMEOUT_SECONDS)`, for example a single `_collect` helper that returns the omitted byte count and the exit code.
  - On timeout and on cancellation, call `_stop` unconditionally. On POSIX that is `os.killpg` even when the leader has been reaped, still ignoring `ProcessLookupError`. On normal completion, still do not kill the group, so a process backgrounded with its output redirected to a file keeps running, as the tool description advises.
  - Add input (a) to §6.3.

R-3 [Major] [L5] §8.1 D-13, FR-11, INV-15, AC-22 — The Windows bash lookup returns `bash_not_found` when Python is started from a Git Bash terminal on the user's own machine
  Evidence:
  - The spec says: D-13 `Path(shutil.which("git")).parent.parent / "bin" / "bash.exe"`, justified by "`git` resolves to `C:\Program Files\Git\cmd\git.EXE`".
  - Machine, from PowerShell: `shutil.which("git")` = `C:\Program Files\Git\cmd\git.EXE`, so the lookup works there.
  - Machine, from a Git Bash–launched Python: `shutil.which("git")` = `C:\Program Files\Git\mingw64\bin\git.EXE`. Two parents up is `Git\mingw64`, and `Git\mingw64\bin\bash.exe` does not exist (`ls`: No such file).
  - In that same environment `shutil.which("bash")` = `Git\usr\bin\bash.EXE`, a working Git Bash, which INV-15 forbids using.
  Failure: Python started from a Git Bash terminal (the VS Code Git Bash profile, Claude Code's shell on Windows) builds a `CodingAgent` whose every `bash` call returns `bash_not_found`, while Git Bash is the parent shell. G-3 and EC-13 fail on the user's machine in that environment.
  Smallest fix:
  - On win32, check `bin/bash.exe` under each of the first three parents of `Path(shutil.which("git")).resolve()`. That covers `<G>/cmd/git.exe`, `<G>/bin/git.exe`, and `<G>/mingw64/bin/git.exe`, and it still never runs the PATH `bash`.
  - Add an AC-22 variant with `git` at `<G>/mingw64/bin/git.exe`.
  - Keep the loop flat (see R-8).

R-4 [Major] [L4] §8.1 D-11, NFR-3, EC-17 — A 1,000,000-byte Bash output cap goes straight into the model's context, about 20× the repo's own largest model-facing tool cap, and the spec's "matches max_file_bytes" justification compares unlike things
  Evidence:
  - The spec says: D-11 "`BASH_MAX_OUTPUT_BYTES = 1_000_000` … `1_000_000` matches `BaseCodeSearchTool`'s `max_file_bytes`". EC-17 concedes "The provider may reject the next request and the run ends with that error."
  - Repo: `max_file_bytes` is a threshold for skipping files during a search scan (`vidbyte/tools/builtins/code_search/base.py:95`), not an output cap.
  - The repo's model-facing caps are `GlobTool` `max_chars` default 10,000 and maximum 50,000 (`glob.py:44`), and `GrepTool` default 12,000 and maximum 50,000 (`grep.py:51`). The MCP stderr buffer is `64 * 1024` (`tools/mcp/transport.py:63`).
  Failure: 1 MB is about 250k tokens. The model runs `cat package-lock.json` (600 KB) or a verbose `pytest -vv` on a 128k–200k-token model. The single tool message exceeds the context window, the next request is rejected, and the run ends. That happens on the default path, because `ToolSettings.result_max_chars` defaults to `None`.
  Smallest fix:
  - Set `BASH_MAX_OUTPUT_BYTES` to the repo's existing model-output ceiling, for example `50_000`, the `max_chars` upper bound of `GlobTool` and `GrepTool`.
  - Rewrite D-11's rationale to cite those caps instead of `max_file_bytes`.
  - Update NFR-3 and the README numbers in row 8.
  - This adds no knob, and AC-13 is unchanged because it uses the constant.
  - Optional, the author's call: keep the last bytes instead of the first, since test summaries and errors print last. The code size is the same.

R-5 [Minor] [L2] §8.4, §12.3 row 1 — The third new file, `vidbyte/lib/constants/bash.py`, is not forced; the smaller design keeps the three bounds as module constants in `bash.py`
  Evidence:
  - The spec says: §8.4 "`vidbyte/lib/constants/bash.py` (named bounds required by A007 and kept under `vidbyte/lib` per `model-facing-tool-contracts.md`)".
  - A007 accepts any UPPERCASE assignment, in any module (`lint/rules/a007_operational_constants.py`, `_named_constant`).
  - REPO_MAP's `vidbyte/lib/constants/` entry: "if a literal value would otherwise need to appear in two places, it belongs here". These constants have one consumer.
  - The field-guide check says *shared* constants go under `vidbyte/lib`.
  - The spec's own exemplar, `code_execution.py:30-31` (`MAX_PRINT_EXPONENT`, `MAX_PRINT_INT_BITS`, PRs #569 and #644 from this week), and `tools/mcp/transport.py:63-65` both keep single-use bounds in the tool module.
  - 6 of the 8 existing constants modules are re-exported from `vidbyte/lib/constants/__init__.py`. The spec cites only the two that are not (`trace.py`, `jev.py`).
  Failure: The PR has one more file and module than the smallest design that meets every FR and INV. The §13 seam (patching `vidbyte.tools.builtins.bash.<NAME>`) works the same either way. With "very minimalistic" as the tie-breaker, the extra file loses.
  Smallest fix: Define the three constants at module level in `vidbyte/tools/builtins/bash.py`, delete row 1, and set the §8.4 budget to 2 files. If the author keeps the lib module, cite the field guide explicitly and decide the `__init__` re-export by the majority precedent.

R-6 [Minor] [L4] §8.1 D-16, §12.3 rows 8–9, §12.5 — `_FetchedPagesView` would be the first tool class in `vidbyte/agents/`, and the tools README would still say keyed fetch output is a compact summary
  Evidence:
  - No `BaseTool` or `_ToolWrapper` subclass exists under `vidbyte/agents/` today (`grep "class .*(BaseTool|_ToolWrapper|PricedOperationTool)" vidbyte/agents` finds only a README example).
  - The other tool views live in the tools layer: `_CustomizedTool` in `tools/base.py` and `_ActivityBoundTool` in `tools/activity.py`.
  - REPO_MAP gives `vidbyte/tools/` the job of turning a tool into "a result the model can read back".
  - `vidbyte/tools/README.md:119-123` says "`output` holds a compact summary for the model's context window". Row 9 only edits the `builtins/` bullet.
  - CONTRIBUTING.md asks to "Update nearby documentation when behavior, imports … change". The root `README.md` has per-agent sections (`JevAgent` at :32, `ContinualTraceAgent` at :820), and §12.5 is silent on it.
  Failure: A reviewer asks why a tool class lives in the agents package. A reader of the tools README expects summary-only output from CodingAgent's `firecrawl_fetch` and is wrong.
  Smallest fix:
  - Keep the class where it is, and give D-16 one sentence explaining why the agent module wins over `vidbyte/tools/` (single private consumer).
  - Add the caveat "on `CodingAgent`, a keyed fetch returns each page's text in `output`" to row 8, and one sentence to the tools README's Priced Operation Tools section.
  - State the root README decision in §12.5, either "no change" with a reason or one short section.

R-7 [Minor] [L10] §6.1 INV-3, INV-14, §6.3 EC-21 — Three statements are stronger than the code, and the blind test author will write tests against them
  Evidence:
  - EC-21 says "the view is re-wrapped around the same inner tool". `AgentForker._clone_tool` returns the *same* view object when the inner tool has no clone hook: `return tool if inner is tool.wrapped_tool else tool._rewrap(inner)` (`vidbyte/agents/fork.py:138-141`).
  - INV-14 says the retry policy "never retries it automatically". `_tool_permission_allows_retry` returns `True` for every permission when `retry_only_idempotent=False` (`vidbyte/middleware/builtins/tool_error_policy.py:142-147`). The default is `True` (`agents/settings/tool_error.py:45`).
  - INV-3 says "The tool count is always 7 + the number of caller tools". `add_tool` and MCP attach change the count later, and `_catalog_from_agent_tools` silently drops items that raise `TypeError` (`base.py:1283-1290`).
  Failure: A test asserting that the fork's view is a new object, or that EXECUTE is never retried under `retry_only_idempotent=False`, fails against a correct implementation.
  Smallest fix: Reword the three statements:
  - EC-21: "the same view object is reused".
  - INV-14: "under the default `retry_only_idempotent=True`".
  - INV-3: "at construction, for valid tool objects".

R-8 [Minor] [L8] §11 baseline, §12.4, §14 — S024 (control-flow nesting ≤ 3) is missing from the spec's lint lists, and main has unclaimed headroom there
  Evidence:
  - `python lint/run.py --rule S024` on base reports `S024 IMPROVED 25 -> 21`. `MAX_NESTING_DEPTH = 3` counts `if`, `for`, `with`, `try`, and `match` (`lint/rules/s024_maximum_control_flow_nesting.py:22`).
  - §11 lists IMPROVED rules as "A002, S017, S025, S051". §14's touched-rule list omits S024.
  Failure: A platform branch wrapped around a loop and a file check, which is exactly the shape of the R-3 fix (`if win32` → `for parent` → `if is_file`), reaches depth 4. S024 rises from 21 to 22, the full lint still prints `IMPROVED 25 -> 22` and passes, and the headroom the spec says not to consume is consumed unnoticed.
  Smallest fix: Add S024 (main count 21) to the §11 baseline and the §14 rule list, and add the §12.4 line "no function nests control flow deeper than 3 (S024)".

VERIFIED CLAIMS:

- Held: `vidbyte/tools/builtins/operations/fetch.py:39-42`. Keyed tools render a summary only. `LinkupFetchTool.execute` always returns the contract stub. `DirectHttpFetchTool` returns the full body, fetched by `HttpFetcher`, whose `request_bytes` has no `max_response_bytes` (`vidbyte/sources/fetches/http.py:44-49`).
- Held: the four clients (`FirecrawlClient`, `BrowserbaseClient`, `ParallelClient`, `TavilyClient`) need only `api_key`. There is no Linkup client.
- Held: pricing. The only recording site is `runtime.py:1195-1214`, which unwraps via `ActivityToolFormatter.unwrap` → `_unwrap_tool` and reads result metadata only.
- Held: permissions. `PermissionPolicy` defaults to SAFE+READ and `allow_all()` covers every level (`security.py:27-45`). `BaseAgent` uses `permission_policy or PermissionPolicy()` (`base.py:185`). `_check_permission` is at `runtime.py:1270`.
- Held: a duplicate tool name raises `ToolRegistrationError` (`catalog.py:38`). It is not swallowed, because `ToolRegistrationError` is not a `TypeError`.
- Held: `restore` builds `cls(...)` with no `root_dir`, so `CodingAgent.restore` raises `TypeError` (documented). `from_run_id` works. Session resume uses `BaseAgent.restore` (`session.py:435`). `AgentForker.fork` builds a plain `BaseAgent` with the same tools and policy (`fork.py:43-46`).
- Held: JevAgent checks only that `type(agent).generate_reply is BaseAgent.generate_reply` (`jev/agent.py:86-98`).
- Held: S055 matches only shell-style calls, so `create_subprocess_exec(bash, "-c", cmd)` passes.
- Held: A002 tokens include `subprocess`, `permission`, and `fetch`, with the window [def−4, def+20].
- Held: A007 exempts UPPERCASE assignments in any module.
- Held: S025 resolves f-strings, and wrappers without their own `ToolSpec(...)` call are not checked.
- Held: S039 bans `asyncio.Lock`, `typing.TypedDict`, and `typing.assert_never` (`lint/ruff.toml`). S045 is ASYNC109 only. S016 covers `vidbyte/tools/builtins/`. S017 covers `vidbyte/tools/`.
- Held: typeshed declares `os.killpg` Unix-only, and `start_new_session` exists in every `asyncio.subprocess` stub.
- Held: Windows argv quoting through `Git\bin\bash.exe -c` survived quotes, backslashes, and tabs (tested).
- Held: export positions in `vidbyte/agents/__init__.py` (after the codex block; `"CodingAgent"` between `"CodexUsageResponse"` and `"ContinualTraceAgent"`) and in `vidbyte/__init__.py` (after `CodexUsageResponse,` at line 97).
- Held: the generator pins its inputs to HEAD. No test pins an exact `__all__` list or iterates over every builtin.
- Held: CI runs on ubuntu-latest only, and every workflow is dispatch-only. Semgrep is absent from `run_ci.py`. The source stage runs with `PYTHONPATH` and the package stage pops it (`run_ci.py:226`).
- Held: REPO_MAP and `artifacts/file_index.md` are folder-level, `llms.txt` has no `JevAgent`, and there is no README in `builtins/` or `lib/constants/`.
- Held: the test-seam facts. `tests/test_agent_tool_loop.py::test_agent_denies_write_tool_by_default` exists at :116. `build_test_agent(..., agent_type=...)` exists. `tests/test_mcp_stdio_transport.py` has a win32 branch near :419.
- Held: the lint baselines A007 255/255, and baseline values A002 703, S017 79, S025 263, S051 259.
- Not verified: the cycle the scout flagged (`builtins/fork/fork.py` → `vidbyte.agents`) does not exist (see the fourth bullet under WHAT THE SPEC GETS RIGHT).
- Partly false: D-13's "git resolves to `…\Git\cmd\git.EXE`" is true from PowerShell and false from a Git Bash–launched process (`…\Git\mingw64\bin\git.EXE`) (R-3).
- False: D-14 and EC-14's "Only bash.exe is killed; its children may keep running". The killed process is a launcher, the command always survives, `taskkill /T` does not reach it, and on Python 3.13 `wait()` blocks (R-1).
- False: D-11's "`1_000_000` matches `max_file_bytes`" justification. The number matches, but that value is a scan-skip threshold, not an output cap (R-4).
- False: EC-21's "re-wrapped" (R-7).
- Overclaimed: INV-14's "never retries" (R-7).
- Minor inaccuracy: §12.4's "S052 (ASYNC220/221/222)". S052 covers ASYNC100/105/110/220/221. ASYNC222 is not in it.
- Incomplete: §11's list of IMPROVED rules omits S024 (25 → 21) (R-8).
