# S5 repair iteration 1 of 8 — coding-agent

Branch `feat/coding-agent`, start HEAD `a46c6f7b`, code HEAD `581fc272`. PR https://github.com/cerredz/Vidbyte-SDK/pull/690. Every gate was green going in; the work was the four confirmed findings (R-1 to R-4) and the trivial Minors (R-5 to R-7). R-8 and R-9 stay `follow-up`, as the orchestrator directed.

## Gate matrix (all run in this worktree, in this iteration, on the final code `581fc272`)

| Gate | Command | Result | Final lines |
|---|---|---|---|
| Feature pack, Windows 3.11 | `PYTHONPATH=$(pwd) python -m pytest -q tests/features/coding_agent/` | PASS | `86 passed, 11 skipped in 5.29s` |
| Feature pack, WSL 3.12 | the `wsl.exe -d MuseUbuntu1 … /tmp/s2-coding-agent-venv/bin/python -m pytest -q tests/features/coding_agent/` command | PASS | `97 passed in 17.33s` |
| Lint | `python lint/run.py` | PASS | `S062 RATCHETED: 889 known finding(s)…` / `SDK-LINT: PASS` |
| Full local gate, source | `PYTHONPATH=$(pwd) python scripts/run_ci.py --stage source` | PASS | `tests\test_web_operation_client_retry.py ..  [100%]` / `====== 2715 passed, 12 skipped in 20.51s ======` / `CI passed.` |
| Full local gate, package | `python scripts/run_ci.py --stage package` (PYTHONPATH unset) | PASS | `No broken requirements found.` / `Installed vidbyte-sdk 0.2.0 passed smoke checks.` / `CI passed.` |
| Remote CI | `gh workflow run ci.yml --ref feat/coding-agent` → run `38075705506` | PASS (success on `581fc272`) | Source 3.11 `2718 passed, 9 skipped in 27.53s` / `CI passed.`; Source 3.12 `2718 passed, 9 skipped, 12 warnings in 26.85s` / `CI passed.`; Package `Installed vidbyte-sdk 0.2.0 passed smoke checks.` / `CI passed.` |
| Remote Semgrep | `gh workflow run static-policy.yml --ref feat/coding-agent` → run `38075707127` | PASS (success on `581fc272`) | `1/1: ✓ All tests passed` / `Ran 1 rule on 857 files: 0 findings.` / `Findings: 0 (0 blocking)` |

Lint rows that moved, all still at or under baseline: A002 682/703, S009 340/350, S017 78/79, S024 21/25, S025 261/263 (it was 263 before R-4), S051 258/259, C016 0/0. A007 is 255/255.

## Per finding

### R-1 [Blocker] — `_stop` breaks "never raises / always closes" → fixed @415f7c22
- **Reproduced on WSL 3.12.3 with the verifier's probes, before the fix:**
  - `[CODE] timeout, then cancel during grace wait: raised CancelledError after 1.60s; transport is_closing=False`
  - `[CODE] EPERM on timeout path: raised PermissionError after 1.00s; transport is_closing=False`
  - `[CODE] timeout path, leader alive and unsignallable: raised PermissionError after 1.00s; transport is_closing=False`
- **Change:** applied "Fix detail R-1" exactly.
  - The kill and the bounded wait are now inside `try:`, and `PermissionError` is suppressed alongside `ProcessLookupError` on the kill.
  - `transport.close()` now runs in `finally:` under `contextlib.suppress(PermissionError)`.
  - The `@intent` comment now says why `PermissionError` is tolerated (no group member may be signalled; `close()` re-kills a still-running direct child) and why the close sits in `finally` (a second cancellation during the wait).
  - Added the one permitted bullet under spec §17 "Implementation deviations".
- **After the fix,** every `[CODE]` row of both probes ends `transport is_closing=True`; the timeout paths return `ERROR {'error': 'timeout', 'truncated': False}` and the cancel paths raise `CancelledError`. Leftover processes: none.
  - `[CODE] timeout path, leader alive and unsignallable: returned ERROR {'error': 'timeout', 'truncated': False} after 2.00s; transport is_closing=True`
  - `[CODE] cancel path, leader alive and unsignallable: raised CancelledError after 1.50s; transport is_closing=True`
- `python lint/run.py --rule S024` shows `21 25 IMPROVED` (nesting depth 3, as the verifier said), and S019 is unchanged at 5. No regression test was added (declined by the orchestrator).

### R-2 [Blocker] — the EC-11 test cannot fail → fixed @a49b7dd8 (test change granted)
- **Reproduced on Windows 3.11.0:** `drive_ec11.py … existing mutant` gave `1 passed` and `RESULT … pytest_exit=0 mutant_spawns=1`.
- **Change:** the test body is now review.md's "Fix detail R-2" After block, verbatim, plus `import os` placed first in the stdlib import block. Ruff I001 on the file: `All checks passed!`.
- **Proof that the new test fails the mutant** (the `existing` target is now the repo test as changed):
  - Windows 3.11: code `1 passed in 0.12s … pytest_exit=0 mutant_spawns=0`; mutant `1 failed in 10.28s … pytest_exit=1 mutant_spawns=1`.
  - WSL 3.12: code `1 passed in 0.07s … pytest_exit=0`; mutant `1 failed in 10.28s … pytest_exit=1 mutant_spawns=1`.
  - The verifier's scratch copy (`proposed`) gave the same verdicts: code passed, mutant `1 failed in 19.59s … pytest_exit=1`.
- `git diff d158d5f6..HEAD --stat -- tests/` lists exactly `tests/features/coding_agent/README.md` (R-7) and `tests/features/coding_agent/test_bash_tool_contract.py` (R-2).

### R-3 [Major] — `root_dir=""` passes validation → fixed @64df91ce
- **Reproduced (Windows 3.11):** `'' ACCEPTED -> C:\…\vidbyte-sdk-coding-agent | equals cwd: True`.
- **Change:** `Path(root_dir).is_dir()` became `os.path.isdir(root_dir)`, with a one-line comment that says why (`Path("")` is the current folder). The error type and message are unchanged.
- **After the fix:**
  - `''` raises `ConfigurationError: CodingAgent root_dir must be an existing directory.`
  - `'.'`, an absolute path and `Path('.')` are still accepted; `'missing-dir'` and `' '` are still rejected.
  - All five AC-11 cases (missing-folder, a-file, integer, none, omitted) pass, and `mypy vidbyte/agents/coding.py` reports `Success: no issues found`.
- No `""` test case was added (declined by the orchestrator).

### R-4 [Major] — the bash description is wrong → fixed @977c7d23
- **Reproduced:** S025's own `SentenceCounter` returned `tool description sentences: 6`, and the text said "always the last line" and "is stopped" with no Windows caveat.
- **Change:** the one f-string is now the "Fix detail R-4" text, verbatim.
- **After the fix:**
  - The counter returns 5.
  - `--rule S025` is `IMPROVED 263 -> 261`, and `--rule S025 --all` and `--rule S062 --all` show no finding in `bash.py` or `coding.py`.
  - The text has no "e.g.", "for example" or "such as".
  - No test reads the bash description (grepped the pack for `description`).

### R-5 [Minor, trivial] → fixed @15aed1e0
- **Change:** the README bullet now reads "`fork()` returns a plain `BaseAgent`. `CodingAgent.restore(state)` raises `TypeError` (no `root_dir`), so restore with `BaseAgent.restore(state, tools=CodingAgent(...).tools.all())`." "restores" is gone from the `coding.py` header's "behave exactly as" list.
- **Probe:** `restore: TypeError CodingAgent.__init__() missing 1 required keyword-only argument: 'root_dir'`, and `fork type: BaseAgent True`.

### R-6 [Minor, trivial] → fixed @388993f9
- **Reproduced:** with the root removed, the result was `bash could not start this command (NotADirectoryError). Shorten the command or remove NUL characters from it.`
- **Change:** the hint is now "Check that the root folder still exists, and that the command has no NUL characters and is not too long." There is no branching, and the result still names only the exception class. The `_spawn` `@intent` comment now lists the removed root folder as a cause.
- **Check:** EC-15 (`test_command_the_os_cannot_start_*`) still passes, because the text contains none of "embedded null", "argument list too long" or "extension is too long". S017 is `78 79 IMPROVED`.

### R-7 [Minor, trivial; edit granted] → fixed @581fc272
- **Change:** one line in `tests/features/coding_agent/README.md:7`. The file tools now point to `vidbyte/tools/filesystem/`, and the search and fetch tools to `vidbyte/tools/builtins/`.
- **Verified with `ls`:** `read_lines.py`, `write_text.py` and `replace_text.py` are in `vidbyte/tools/filesystem/`; `glob.py` and `grep.py` are in `vidbyte/tools/builtins/code_search/`; `fetch.py` is in `vidbyte/tools/builtins/operations/`.

### R-8, R-9 — not acted on (orchestrator: follow-ups for the user); status left `follow-up`.

## Test changes proposed
None beyond the two orchestrator grants (R-2, R-7). No test change is pending.

## Findings I believe are wrong
None.

## Observations outside the gates (not findings, not acted on)
- **Pre-existing import order in two S2 test files.** `ruff check vidbyte tests --select I001` reports I001 in `tests/features/coding_agent/test_coding_agent_contract.py:14` and `test_coding_agent_web_fetch.py:14`.
  - Both files are byte-identical to S2_HEAD `d158d5f6` (`git diff --quiet d158d5f6 HEAD -- <files>` succeeds).
  - S051 runs ruff only over `pyproject.toml vidbyte` (`lint/core/ruff.py:68`), so the lint gate does not count them, and CI does not fail on them.
  - Editing them is outside the two grants. If the orchestrator wants them sorted, it is a `ruff --fix`-sized change that needs its own grant.

## Still open
Nothing. Every gate is green locally and remotely, R-1 to R-7 are fixed, and R-8 and R-9 are `follow-up` by the orchestrator's decision. If a later iteration is needed, start from the I001 observation above, which is the only non-green signal I saw, and it is outside every gate.
