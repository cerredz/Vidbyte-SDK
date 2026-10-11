# S3 · Implementer report — coding-agent

- Stage: S3 implementer
- Date: 2026-10-10
- Worktree: `C:/Users/422mi/vidbyte-repos/worktrees/vidbyte-sdk-coding-agent`, branch `feat/coding-agent`, upstream `origin/feat/coding-agent`
- Base: `8f23fd67`. S2_HEAD: `d158d5f6`. The last code commit is `4c4a62ef`.
- Draft PR: https://github.com/cerredz/Vidbyte-SDK/pull/690. It is a draft with the placeholder body.
- Remote CI was dispatched on `4c4a62ef` and not waited for. Both were queued at dispatch:
  - CI run `38046509073`
  - Static policy run `38046510490`

## Commits

`git log origin/main..HEAD --oneline`. Only the S3 commits are shown; the commits up to `4df5615e` came from S0 to S2 and the orchestrator.

```
b0efce08 docs(spec): record implementation proof for coding-agent
371346e5 docs(spec): record draft PR for coding-agent
4c4a62ef docs(agents): narrate _FetchedPagesView.execute steps [W-5; FR-6]
19cb42db docs(tools): list bash under builtins and note CodingAgent page text [W-7; FR-13]
fc94616f docs(agents): document CodingAgent in the agents README [W-7; FR-13]
5d71a9f4 chore(contracts): regenerate SDK public API for CodingAgent [W-6; FR-14, AC-20]
1bb1d3b4 feat(sdk): export CodingAgent from the root vidbyte package [W-6; FR-1, AC-20]
d56de6a6 feat(agents): export CodingAgent from vidbyte.agents [W-6; FR-1, AC-20]
72edd483 feat(agents): add CodingAgent with seven tools over one root [W-4, W-5; FR-1..FR-8, AC-1..AC-11, AC-21, AC-23]
76429eaf feat(tools): export BashTool from vidbyte.tools.builtins [W-3; FR-12, AC-20]
25b5260b feat(tools): add minimal subprocess BashTool [W-2; FR-9, FR-10, FR-11, AC-12..AC-18, AC-22, AC-24..AC-29]
```

## What exists now, in data-flow order

1. `CodingAgent(...)` validates `root_dir` and resolves it once. It raises `ConfigurationError` if `root_dir` is not an existing directory. Code: `vidbyte/agents/coding.py`, `_resolve_root`.
2. It validates the four fetch keys, which come only from parameters:
   - A blank or non-string key is rejected, and so is passing two keys. The errors name only the parameters.
   - With no key, the fetch tool is `DirectHttpFetchTool()`.
   - With one key, it is `_FetchedPagesView(<Provider>Tool(client=<Provider>Client(key)))`.

   Code: `coding.py`, `_web_fetch_tool`.
3. It builds `BashTool(root)` plus `ReadLinesTool`, `WriteTextTool` and `ReplaceTextTool`, which share `FileSystemToolConfig(root, allow_write=True)`. It adds `GlobTool(root)`, `GrepTool(root)` and the fetch tool, then the caller's tools in the caller's order. Everything goes to `BaseAgent.__init__`, with `PermissionPolicy.allow_all()` unless the caller passed a policy. Code: `coding.py`, `CodingAgent.__init__`.
4. `BashTool` resolves bash once at construction. On POSIX that is `shutil.which("bash")`. On win32 it is the first `<P>/bin/bash.exe` that exists under `Path(which("git")).resolve().parents[:3]`; otherwise it is `None`. A missing bash never raises. Code: `vidbyte/tools/builtins/bash.py`, `_find_bash`.
5. A call is checked by `validate_call` (a non-blank string `command`). `execute` then returns `bash_not_found` or `spawn_failed`, or `_spawn` runs `create_subprocess_exec(bash, "-c", command, cwd=root, stdin=DEVNULL, stdout=PIPE, stderr=STDOUT, start_new_session=True)`. Code: `bash.py`.
6. `_collect` runs under one `asyncio.wait_for(..., BASH_TIMEOUT_SECONDS)`. It reads chunks of up to `BASH_READ_CHUNK_BYTES` and keeps the first `BASH_MAX_OUTPUT_BYTES`. Anything past that is still read but only counted. It then calls `await process.wait()` and returns `(omitted, exit_code)`. Code: `bash.py`.
7. On timeout or cancellation, `_stop` does three things in order:
   1. It kills: `os.killpg(pid, SIGKILL)` always on POSIX, or `process.kill()` on Windows only if `returncode is None`. `ProcessLookupError` is ignored.
   2. It waits at most `BASH_KILL_GRACE_SECONDS`.
   3. It closes `getattr(process, "_transport", None)` if that is present.

   After `_stop`, a timeout returns an error with `{"error": "timeout", "truncated": ...}` and the output so far. A cancellation re-raises. Code: `bash.py`.
8. A command that finishes returns success: `<text>[\n[output truncated: N bytes not shown]]\nexit code: N` with metadata `{"exit_code", "truncated"}`. Nothing is killed. Code: `bash.py`, `_render`.
9. When a keyed fetch succeeds with a `FetchPayload`, `_FetchedPagesView.execute` appends `\n\n` followed by `N. <final_url>\n<content>` for each page, joined by blank lines. Metadata, spec, validation, permission and pricing stay the wrapped tool's. A non-success result passes through unchanged. Code: `coding.py`.
10. Exports and documentation:
    - `BashTool` is exported from `vidbyte.tools.builtins`.
    - `CodingAgent` is exported from `vidbyte.agents` and from the root `vidbyte`.
    - The contract was regenerated: 594 exports, adding `CodingAgent`.
    - The agents README has a "Coding Agent" section and a Key Modules bullet. The tools README mentions bash under builtins and adds a note about page text.

## §12.3 rows

| Row | Action | File | Commit | Done |
|---|---|---|---|---|
| 1 | CREATE | `vidbyte/tools/builtins/bash.py` | `25b5260b` | [x] |
| 2 | MODIFY | `vidbyte/tools/builtins/__init__.py` | `76429eaf` | [x] |
| 3 | CREATE | `vidbyte/agents/coding.py` | `72edd483`, then `4c4a62ef` (step comments only) | [x] |
| 4 | MODIFY | `vidbyte/agents/__init__.py` | `d56de6a6` | [x] |
| 5 | MODIFY | `vidbyte/__init__.py` | `1bb1d3b4` | [x] |
| 6 | REGENERATE | `contracts/sdk-public-api.json` | `5d71a9f4` | [x] |
| 7 | MODIFY | `vidbyte/agents/README.md` | `fc94616f` | [x] |
| 8 | MODIFY | `vidbyte/tools/README.md` | `19cb42db` | [x] |

Row 5 was committed before row 6 was regenerated. `python scripts/generate-sdk-public-api.py --check` exits 0, and lint reports C016 0 CLEAN.

Spec bookkeeping:
- `371346e5` sets frontmatter `pr:` and `status: implemented`.
- `b0efce08` adds the §17 S3 row and the deviations list.
- No §6.2 Proof cell was blank, so none was filled.

## Deviations

1. **`_spawn(executable, command)` instead of `_spawn(command)`** (row 1).
   - `execute` already narrows `self._executable` (`str | None`) to a local `str` for the `bash_not_found` check, and it passes that local to `_spawn`.
   - Reading the attribute again inside `_spawn` would hand `create_subprocess_exec` a `str | None`, which is a new S009 mypy finding, or would need a second check.
   - This changes no behavior. `_spawn` still calls no other helper.
2. **Row 3 has two commits.** `4c4a62ef` adds step comments to `_FetchedPagesView.execute` only, with no code change. AGENTS.md Style 2 asks for narrated main functions.

Both deviations are recorded under spec §17.

## Files outside §12.3

None.
- `git diff 4df5615e..4c4a62ef --stat` lists exactly the 8 §12.3 files: 412 insertions and 4 deletions.
- `git diff d158d5f6..HEAD --stat -- tests/ pyproject.toml` is empty.
- Unchanged: `vidbyte/tools/builtins/operations/fetch.py`, the filesystem and code-search tools, `vidbyte/agents/base.py`, `lint/` and `lint/baseline.json`.

## Budget (§8.4)

| Item | Allowed | Used |
|---|---|---|
| New source files | 2 | 2 (`bash.py`, `coding.py`) |
| New enums or dataclasses | 0 | 0 |
| New public names | 2 | 2 (`CodingAgent`, `BashTool`) |
| New dependencies | 0 | 0 |

`_FetchedPagesView` is private. It is not in any `__all__` or in the contract. The four `BASH_*` constants are globals of `vidbyte.tools.builtins.bash` and are not package exports.

## Gates (final lines)

- **Lint**, `python lint/run.py`, inside the source stage:
  - The run ends `SDK-LINT: PASS` and has 0 REGRESSED rows.
  - These rule counts equal main's counts in §11:
    - A001 643, A002 682, A003 36, A005 33, A006 34, A007 255, A008 3
    - S001 57, S009 340, S015 13, S016 50, S017 78, S019 5, S024 21, S025 261
    - S039 5, S045 2, S051 258, S062 889
  - C016, S052 and S055 are 0 CLEAN.
  - "IMPROVED" means below this branch's older `lint/baseline.json`. No baseline was touched.
- **Source stage**, `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source`:
  ```
  SDK-LINT: PASS
  context write-path integrity: ok
  context primitive introductions: ok
  ====================== 2715 passed, 12 skipped in 17.81s ======================
  CI passed.
  ```
  The known flake `test_mcp_stdio_transport.py::test_cancelled_waiter_does_not_break_transport` did not fail.
- **Package stage**, `python scripts/run_ci.py --stage package` with PYTHONPATH unset:
  ```
  No broken requirements found.
  Installed vidbyte-sdk 0.2.0 passed smoke checks.
  CI passed.
  ```
  The build left `vidbyte_sdk.egg-info/` in the worktree root. It is gitignored and I removed it.
- **Coding-agent pack on Windows**, Python 3.11.0, `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/`: `86 passed, 11 skipped in 4.91s`.
  - All 11 skips are the spec's POSIX-only cases.
  - The AC-27 case `test_command_past_the_time_limit_returns_timeout_with_output_so_far` ran and passed on win32.
- **Coding-agent pack in WSL**, Python 3.12.3, venv `/tmp/s2-coding-agent-venv`: `97 passed in 17.19s`.
- **AC-27 on Python 3.13**: not run. Under `py -3.13`, `pytest` 8.3.5 imports, but `pytest_asyncio` is missing. PyYAML, which the SDK needs at import, is also missing (`ModuleNotFoundError: No module named 'yaml'` when importing `vidbyte`). Installing into 3.13 is forbidden, so this half is open.

## Where the tricky parts are (read these first)

1. **`_stop` kills the POSIX group with no `returncode` guard** (D-14). This is deliberate: `test_cancellation_kills_the_process_group_even_after_the_shell_has_exited` fails with the natural guard. The Windows branch does guard on `returncode is None`.
2. **`_stop` "never raises" holds only for `ProcessLookupError` and the grace `TimeoutError`**, which are exactly the exceptions D-14 lists. A `PermissionError` from `os.killpg` (EPERM) would escape, and in the cancellation path it would replace `CancelledError`. This is the spec's literal design; I did not widen the suppression.
3. **Closing the transport goes through the private `process._transport`, read with `getattr`** (D-18). `PricedOperationTool._PAYLOAD_KEY` is also private and is read from `coding.py`, as the spec says. Both are private-API couplings that a reviewer may flag.
4. **`_collect` loops on `while output is not None and (chunk := await output.read(...))`.** The `is not None` part is only there for mypy, because `process.stdout` is typed Optional; with `stdout=PIPE` it is never `None`. The loop has no numeric literal (A007), so the cap slice is `chunk[: BASH_MAX_OUTPUT_BYTES - len(buffer)]`.
5. **`bash_not_found` picks its hint from `sys.platform` at call time, not at construction.** AC-22 patches `sys.platform` only during construction, and no test checks the hint per platform. On a real host the two moments agree.
6. **Output format details.**
   - When the output ends with a newline, the success text has a blank line before `exit code: N`. This is the literal `text + "\nexit code: N"` format.
   - The timeout marker prints the cap with thousands separators (`1,000` when the cap is patched), so its only digits are still the cap (AC-29).
7. **The test that was hardest to satisfy was lint, not a pytest test.**
   - A002 requires each `# @intent` comment within def-3 to def+20 lines. It also matches tokens in annotations such as `asyncio.subprocess.Process`, so `_collect` and `_stop` carry intents and every intent sits inside the function body (the jev pattern).
   - The S051 whole-tree ruff I001 check forced the wrapped `vidbyte.tools.types` import.
8. **Main has moved to `e6cdfa31`** and added lint rules A009, C006, C007 and C008, which are not on this branch. None of the 8 §12.3 files changed upstream. A rebase at S5/S6 should run lint again for those rules.

## Limitations seen, not built (scope rule)

- The win32 bash lookup and the Windows stop path were checked only with simulated layouts (AC-22, POSIX host) and the Windows 3.11 run. Running against a real Git for Windows layout is a manual check, per the test plan.
- `_stop` could replace a `CancelledError` on a non-`ProcessLookupError` `OSError` from `killpg` (see tricky part 2). The spec has no control for this, so nothing was built.
